"""
The tokens of the signed-in user: where they are kept, and how they are
renewed.

The access token, the refresh token, the end of the access token and the
minimal identity of the user (name, user name, email) are one record in the
SecretStore, under the name "gitlab/<host of GitLab>". The settings file holds
none of it. The identity lets the home screen name the user without a network
call.

GitLab gives a new refresh token at each renewal. The two tokens are replaced
together, in one write. The renewal runs before the access token ends, from a
timer thread at the launch and during the session. Only one renewal runs at a
time: a second caller waits for it and uses its result.

The tokens are in no variable of the environment of the application: a
program that the application starts would read them. Git gets the access
token in the environment of its own process only (git_access.py). The value is
never logged.

@relation(SDOC-SRS-1235, scope=file)
@relation(SDOC-SRS-1239, scope=file)
"""

import json
import threading
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from strictdoc.features.desktop.oauth_gitlab import (
    GitLabSession,
    GitLabTokens,
    GitLabUser,
    OAuthError,
    OAuthRejectedError,
    PendingSignIn,
    refresh_tokens,
)
from strictdoc.features.desktop.secret_store import (
    SecretStore,
    SecretStoreError,
)
from strictdoc.features.i18n.i18n import gettext

# The access token is renewed this long before it ends.
RENEWAL_MARGIN_SECONDS = 300.0
# After a renewal that failed for lack of network, the next try comes later.
RETRY_SECONDS = 60.0
# A renewal gives a token that lives longer than the margin, in practice. If
# GitLab gave a shorter one, the next renewal would be due at once: this wait
# keeps the application from asking GitLab again and again.
MINIMUM_RENEWAL_INTERVAL_SECONDS = 10.0

_SECRET_NAME_PREFIX = "gitlab/"
_STORED_VERSION = 1


class SignInStatus(Enum):
    SIGNED_OUT = "signed_out"
    SIGNED_IN = "signed_in"
    # The access token has ended and GitLab cannot be reached to renew it.
    OFFLINE = "offline"


def get_token_secret_name(gitlab_url: str) -> str:
    """The name of the record of a GitLab in the SecretStore."""
    return f"{_SECRET_NAME_PREFIX}{urlsplit(gitlab_url.strip()).netloc.lower()}"


def serialize_session(session: GitLabSession) -> str:
    return json.dumps(
        {
            "version": _STORED_VERSION,
            "access_token": session.tokens.access_token,
            "refresh_token": session.tokens.refresh_token,
            "expires_at": session.tokens.expires_at,
            "username": session.user.username,
            "name": session.user.display_name,
            "email": session.user.email,
            "user_id": session.user.user_id,
            "public_email": session.user.public_email,
            "commit_email": session.user.commit_email,
        }
    )


def parse_session(content: str) -> Optional[GitLabSession]:
    """The session of a record, or None when the record is not a good one."""
    try:
        record = json.loads(content)
    except (ValueError, RecursionError):
        return None
    if not isinstance(record, dict) or record.get("version") != _STORED_VERSION:
        return None
    access_token = record.get("access_token")
    refresh_token = record.get("refresh_token")
    expires_at = record.get("expires_at")
    username = record.get("username")
    if (
        not isinstance(access_token, str)
        or len(access_token) == 0
        or not (refresh_token is None or isinstance(refresh_token, str))
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, (int, float))
        or not isinstance(username, str)
        or len(username) == 0
    ):
        return None
    name = record.get("name")
    email = record.get("email")
    user_id = record.get("user_id")
    return GitLabSession(
        tokens=GitLabTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=float(expires_at),
        ),
        user=GitLabUser(
            username=username,
            display_name=name
            if isinstance(name, str) and name != ""
            else username,
            email=email if isinstance(email, str) else "",
            user_id=(
                user_id
                if isinstance(user_id, int) and not isinstance(user_id, bool)
                else 0
            ),
            public_email=_get_stored_text(record, "public_email"),
            commit_email=_get_stored_text(record, "commit_email"),
        ),
    )


class TokenKeeper:
    """
    The session of the signed-in user, its record in the SecretStore and its
    renewal. The home server owns one.
    """

    def __init__(
        self,
        secret_store: SecretStore,
        *,
        clock: Callable[[], float] = time.time,
        refresh: Callable[..., GitLabTokens] = refresh_tokens,
        margin_seconds: float = RENEWAL_MARGIN_SECONDS,
        retry_seconds: float = RETRY_SECONDS,
        use_timer: bool = True,
    ) -> None:
        self._secret_store: SecretStore = secret_store
        self._clock: Callable[[], float] = clock
        self._refresh: Callable[..., GitLabTokens] = refresh
        self._margin_seconds: float = margin_seconds
        self._retry_seconds: float = retry_seconds
        self._use_timer: bool = use_timer
        # The state, under the state lock.
        self._state_lock: threading.RLock = threading.RLock()
        self._session: Optional[GitLabSession] = None
        self._gitlab_url: str = ""
        self._client_id: str = ""
        self._has_failed_renewal: bool = False
        self._next_attempt_at: float = 0.0
        self._is_refused: bool = False
        self._storage_error: Optional[str] = None
        self._timer: Optional[threading.Timer] = None
        self._is_closed: bool = False
        # One renewal at a time.
        self._renew_lock: threading.Lock = threading.Lock()
        # The access to the SecretStore, one at a time, and never under the
        # state lock: a slow keyring does not hold up the readers of the state.
        self._io_lock: threading.Lock = threading.Lock()
        # Counts the changes of the session. A write or a delete of the record
        # is for one change; if a newer change came, it is not done any more.
        self._generation: int = 0
        self._session_listeners: List[Callable[[], None]] = []

    @property
    def session(self) -> Optional[GitLabSession]:
        with self._state_lock:
            return self._session

    @property
    def status(self) -> SignInStatus:
        with self._state_lock:
            if self._session is None:
                return SignInStatus.SIGNED_OUT
            if (
                self._has_failed_renewal
                and self._clock() >= self._session.tokens.expires_at
            ):
                return SignInStatus.OFFLINE
            return SignInStatus.SIGNED_IN

    @property
    def gitlab_url(self) -> str:
        """The GitLab of the session, "" when nobody is signed in."""
        with self._state_lock:
            return self._gitlab_url

    @property
    def is_refused(self) -> bool:
        """True when GitLab refused the renewal: the sign-in was lost."""
        with self._state_lock:
            return self._is_refused

    @property
    def storage_error(self) -> Optional[str]:
        """The text for the user when the SecretStore failed, else None."""
        with self._state_lock:
            return self._storage_error

    def add_session_listener(self, listener: Callable[[], None]) -> None:
        """
        Call the function after each change of the session: a sign-in, the end
        of the session, a refusal of GitLab. The renewal of the tokens is not a
        change of the session.
        """
        with self._state_lock:
            self._session_listeners.append(listener)

    def restore(self, *, gitlab_url: str, client_id: str) -> None:
        """
        Read the record of the GitLab in the SecretStore. A token that is not
        ended is used with no network call. A token that must be renewed is
        renewed by the timer thread at once, so that the launch does not wait
        for GitLab.
        """
        content = self._read_record(gitlab_url)
        session = parse_session(content) if content is not None else None
        if session is None:
            return
        with self._state_lock:
            if self._session is not None:
                # The user signed in while the record was read.
                return
            self._gitlab_url = gitlab_url
            self._client_id = client_id
            self._session = session
            self._has_failed_renewal = False
            self._is_refused = False
            self._next_attempt_at = 0.0
            self._generation += 1
        self._notify_session_changed()
        self._schedule()

    def adopt(
        self, *, gitlab_url: str, client_id: str, session: GitLabSession
    ) -> None:
        """Keep the session that a sign-in gave."""
        with self._state_lock:
            self._gitlab_url = gitlab_url
            self._client_id = client_id
            self._is_refused = False
            generation = self._install_locked(session, next_attempt_at=0.0)
        self._write_record(session, gitlab_url, generation)
        self._notify_session_changed()
        self._schedule()

    def adopt_sign_in(
        self, pending: PendingSignIn, session: GitLabSession
    ) -> None:
        """The listener of GitLabSignIn."""
        self.adopt(
            gitlab_url=pending.gitlab_url,
            client_id=pending.client_id,
            session=session,
        )

    def renew(self) -> None:
        """
        Renew the tokens when the access token ends soon. One renewal runs at
        a time; a caller that waits for it finds the work done.

        GitLab that refuses the refresh token ends the session (the record is
        deleted). Any other failure, a network that does not answer for
        example, keeps the session and the record, and raises OAuthError.
        """
        with self._renew_lock:
            with self._state_lock:
                session = self._session
                gitlab_url = self._gitlab_url
                client_id = self._client_id
            if session is None or not self._is_renewal_allowed(session):
                return
            old_refresh_token = session.tokens.refresh_token
            if old_refresh_token is None:
                self._end_session(is_refused=True, expected_session=session)
                return
            try:
                tokens = self._refresh(
                    gitlab_url=gitlab_url,
                    client_id=client_id,
                    refresh_token=old_refresh_token,
                    clock=self._clock,
                )
            except OAuthRejectedError:
                # Only the session that was refused ends: not one that a
                # sign-in made while GitLab answered.
                self._end_session(is_refused=True, expected_session=session)
                return
            except OAuthError:
                with self._state_lock:
                    if self._session is session:
                        self._has_failed_renewal = True
                        self._next_attempt_at = (
                            self._clock() + self._retry_seconds
                        )
                raise
            new_session = GitLabSession(
                tokens=GitLabTokens(
                    access_token=tokens.access_token,
                    refresh_token=(
                        tokens.refresh_token
                        if tokens.refresh_token is not None
                        else old_refresh_token
                    ),
                    expires_at=tokens.expires_at,
                ),
                user=session.user,
            )
            # The check and the change are one step: a sign-out or a new
            # sign-in cannot come between them.
            with self._state_lock:
                if self._session is not session:
                    return
                generation = self._install_locked(
                    new_session,
                    next_attempt_at=(
                        self._clock() + MINIMUM_RENEWAL_INTERVAL_SECONDS
                    ),
                )
                gitlab_url = self._gitlab_url
            self._write_record(new_session, gitlab_url, generation)
            self._schedule()

    def get_access_token(self) -> Optional[str]:
        """
        An access token that works now, renewed first if it ends soon. None
        when the user is signed out or when no good token can be had.
        """
        try:
            self.renew()
        except OAuthError:
            pass
        with self._state_lock:
            session = self._session
            if session is None or self._clock() >= session.tokens.expires_at:
                return None
            return session.tokens.access_token

    def sign_out(self) -> None:
        """End the session: delete the record."""
        self._end_session(is_refused=False, expected_session=None)

    def close(self) -> None:
        """Stop the timer. The record stays: the next launch finds it."""
        with self._state_lock:
            self._is_closed = True
            self._cancel_timer()

    def get_seconds_until_renewal(self) -> Optional[float]:
        """The wait before the next renewal, None without a session."""
        with self._state_lock:
            if self._session is None:
                return None
            due_at = self._session.tokens.expires_at - self._margin_seconds
            due_at = max(due_at, self._next_attempt_at)
            return max(0.0, due_at - self._clock())

    def _needs_renewal(self, session: GitLabSession) -> bool:
        return self._clock() >= session.tokens.expires_at - self._margin_seconds

    def _is_renewal_allowed(self, session: GitLabSession) -> bool:
        """Due, and not too soon after the last try."""
        with self._state_lock:
            return (
                self._needs_renewal(session)
                and self._clock() >= self._next_attempt_at
            )

    def _install_locked(
        self, session: GitLabSession, *, next_attempt_at: float
    ) -> int:
        """
        Make the session current. Call it with the state lock. It returns the
        number of the change.
        """
        self._session = session
        self._has_failed_renewal = False
        self._next_attempt_at = next_attempt_at
        self._generation += 1
        return self._generation

    def _end_session(
        self, *, is_refused: bool, expected_session: Optional[GitLabSession]
    ) -> None:
        """
        End the session. With an expected session, only if it is still the
        current one: the check and the end are one step.
        """
        with self._state_lock:
            if (
                expected_session is not None
                and self._session is not expected_session
            ):
                return
            gitlab_url = self._gitlab_url
            self._session = None
            self._has_failed_renewal = False
            self._is_refused = is_refused
            self._generation += 1
            generation = self._generation
            self._cancel_timer()
        self._delete_record(gitlab_url, generation)
        self._notify_session_changed()

    def _notify_session_changed(self) -> None:
        with self._state_lock:
            listeners = list(self._session_listeners)
        for listener_ in listeners:
            listener_()

    def _read_record(self, gitlab_url: str) -> Optional[str]:
        with self._io_lock:
            try:
                return self._secret_store.get(get_token_secret_name(gitlab_url))
            except (SecretStoreError, ImportError):
                return None

    def _write_record(
        self, session: GitLabSession, gitlab_url: str, generation: int
    ) -> None:
        """
        One write for both tokens, so that they are never apart. The write is
        done when it is the last change of the session, and with no state lock:
        a slow keyring does not block the readers of the session.
        """
        with self._io_lock:
            if not self._is_last_change(generation):
                return
            error: Optional[str] = None
            try:
                self._secret_store.set(
                    get_token_secret_name(gitlab_url),
                    serialize_session(session),
                )
            except (SecretStoreError, ImportError):
                # The session goes on in the memory of the process.
                error = gettext(
                    "The keyring did not save the sign-in. "
                    "You will have to sign in again at the next launch."
                )
            with self._state_lock:
                if generation == self._generation:
                    self._storage_error = error

    def _delete_record(self, gitlab_url: str, generation: int) -> None:
        with self._io_lock:
            if not self._is_last_change(generation):
                return
            try:
                self._secret_store.delete(get_token_secret_name(gitlab_url))
            except (SecretStoreError, ImportError):
                with self._state_lock:
                    if generation == self._generation:
                        self._storage_error = gettext(
                            "The keyring did not delete the sign-in."
                        )

    def _is_last_change(self, generation: int) -> bool:
        with self._state_lock:
            return generation == self._generation

    def _schedule(self) -> None:
        if not self._use_timer:
            return
        with self._state_lock:
            self._cancel_timer()
            delay = self.get_seconds_until_renewal()
            if self._is_closed or delay is None:
                return
            timer = threading.Timer(delay, self._on_timer)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timer(self) -> None:
        try:
            self.renew()
        except OAuthError:
            # The session stays and the timer tries again later.
            pass
        finally:
            self._schedule()


def _get_stored_text(record: Dict[str, Any], name: str) -> str:
    value = record.get(name)
    return value if isinstance(value, str) else ""
