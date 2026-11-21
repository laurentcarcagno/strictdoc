"""
The sign-in of the user to GitLab, by the OAuth authorization code flow.

The flow follows RFC 6749 and RFC 7636 (PKCE) for a public client, as RFC 8252
describes it for a native application: the window opens the authorization page
of GitLab, GitLab calls back an address of the loopback interface with a code,
and the application exchanges the code for tokens with the code verifier. The
application keeps no client secret.

The tokens are never written in a message, a log or a representation of an
object.

@relation(SDOC-SRS-1234, scope=file)
@relation(SDOC-SRS-1235, scope=file)
"""

import base64
import hashlib
import json
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from email.message import Message
from http.client import HTTPException
from typing import IO, Any, Callable, Dict, List, Optional

from strictdoc.features.desktop.settings import DesktopSettings
from strictdoc.features.i18n.i18n import gettext

# The path that GitLab calls back, on the loopback address of the home server.
# GitLab accepts any port for a loopback address (RFC 8252, section 7.3).
CALLBACK_PATH = "/__desktop/oauth/callback"
OAUTH_SCOPES = "openid read_user read_api read_repository write_repository"
# How long the user has to sign in on the page of GitLab and Keycloak.
STATE_LIFETIME_SECONDS = 600.0
# The sign-ins that wait for their callback. A larger number only comes from a
# program that starts sign-ins without ending them.
MAXIMUM_PENDING_SIGN_INS = 16
REQUEST_TIMEOUT_SECONDS = 20.0
# The lifetime of a GitLab access token when the answer does not give one.
DEFAULT_TOKEN_LIFETIME_SECONDS = 7200.0

_CODE_VERIFIER_BYTES = 64
_STATE_BYTES = 32
_MAXIMUM_ANSWER_BYTES = 1_000_000


class OAuthError(Exception):
    """The sign-in failed. The message is for the user and holds no secret."""


class OAuthRejectedError(OAuthError):
    """
    GitLab refused the grant on purpose ("invalid_grant"): the code or the
    refresh token is not good any more. It is not a network failure: the
    sign-in is lost and the user has to start it again.
    """


@dataclass(frozen=True)
class GitLabTokens:
    # The fields stay out of the representation: a token in a log is a leak.
    access_token: str = field(repr=False)
    refresh_token: Optional[str] = field(repr=False)
    # Seconds since the epoch.
    expires_at: float


@dataclass(frozen=True)
class GitLabUser:
    username: str
    display_name: str
    email: str


@dataclass(frozen=True)
class GitLabSession:
    tokens: GitLabTokens
    user: GitLabUser


@dataclass(frozen=True)
class PendingSignIn:
    """A sign-in that waits for the callback of GitLab."""

    state: str
    code_verifier: str
    redirect_uri: str
    gitlab_url: str
    client_id: str
    created_at: float


def is_sign_in_configured(settings: DesktopSettings) -> bool:
    """
    Tell whether the settings allow the sign-in: the address of GitLab and
    the identifier of the OAuth application are both given.
    """
    return (
        len(settings.gitlab_url.strip()) > 0
        and len(settings.oauth_client_id.strip()) > 0
    )


def create_code_verifier() -> str:
    """A random code verifier of 86 characters (RFC 7636 asks 43 to 128)."""
    return secrets.token_urlsafe(_CODE_VERIFIER_BYTES)


def create_code_challenge(code_verifier: str) -> str:
    """The S256 code challenge: the SHA-256 of the verifier, in base64url."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_redirect_uri(port: int) -> str:
    """The callback address of the home server that listens on the port."""
    return f"http://127.0.0.1:{port}{CALLBACK_PATH}"


def build_authorization_url(
    *,
    gitlab_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": OAUTH_SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{_normalize_gitlab_url(gitlab_url)}/oauth/authorize?{query}"


def exchange_code(
    pending: PendingSignIn,
    code: str,
    *,
    clock: Callable[[], float] = time.time,
) -> GitLabTokens:
    """
    Give the code and the code verifier to GitLab, and get the tokens.
    Raise OAuthError.
    """
    answer = _request_json(
        f"{_normalize_gitlab_url(pending.gitlab_url)}/oauth/token",
        data=urllib.parse.urlencode(
            {
                "client_id": pending.client_id,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": pending.redirect_uri,
                "code_verifier": pending.code_verifier,
            }
        ).encode("ascii"),
        access_token=None,
        gitlab_url=pending.gitlab_url,
    )
    return _parse_tokens(answer, clock)


def refresh_tokens(
    *,
    gitlab_url: str,
    client_id: str,
    refresh_token: str,
    clock: Callable[[], float] = time.time,
) -> GitLabTokens:
    """
    Give the refresh token to GitLab and get new tokens. GitLab replaces the
    refresh token at each renewal: the old one does not work any more. Raise
    OAuthRejectedError when GitLab refuses the refresh token, and OAuthError
    for any other failure, the network included.
    """
    answer = _request_json(
        f"{_normalize_gitlab_url(gitlab_url)}/oauth/token",
        data=urllib.parse.urlencode(
            {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }
        ).encode("ascii"),
        access_token=None,
        gitlab_url=gitlab_url,
    )
    return _parse_tokens(answer, clock)


def fetch_user(gitlab_url: str, access_token: str) -> GitLabUser:
    """Read the user that the token belongs to. Raise OAuthError."""
    answer = _request_json(
        f"{_normalize_gitlab_url(gitlab_url)}/api/v4/user",
        data=None,
        access_token=access_token,
        gitlab_url=gitlab_url,
    )
    username = answer.get("username")
    if not isinstance(username, str) or len(username) == 0:
        raise OAuthError(gettext("GitLab did not tell who the user is."))
    name = answer.get("name")
    email = answer.get("email")
    return GitLabUser(
        username=username,
        display_name=name if isinstance(name, str) and name != "" else username,
        email=email if isinstance(email, str) else "",
    )


class PendingSignIns:
    """
    The sign-ins that wait for the callback of GitLab.

    A state is random, belongs to one sign-in, works once and for a limited
    time. The code verifier of the sign-in stays here: only the callback that
    carries the right state gets it.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        lifetime_seconds: float = STATE_LIFETIME_SECONDS,
    ) -> None:
        self._clock: Callable[[], float] = clock
        self._lifetime_seconds: float = lifetime_seconds
        self._pending: Dict[str, PendingSignIn] = {}
        self._lock: threading.Lock = threading.Lock()

    def create(
        self, *, gitlab_url: str, client_id: str, redirect_uri: str
    ) -> PendingSignIn:
        now = self._clock()
        pending = PendingSignIn(
            state=secrets.token_urlsafe(_STATE_BYTES),
            code_verifier=create_code_verifier(),
            redirect_uri=redirect_uri,
            gitlab_url=gitlab_url,
            client_id=client_id,
            created_at=now,
        )
        with self._lock:
            self._remove_expired(now)
            while len(self._pending) >= MAXIMUM_PENDING_SIGN_INS:
                oldest_state = min(
                    self._pending,
                    key=lambda state_: self._pending[state_].created_at,
                )
                del self._pending[oldest_state]
            self._pending[pending.state] = pending
        return pending

    def is_valid_state(self, state: str) -> bool:
        """Tell whether a sign-in waits for this state. It does not use it."""
        with self._lock:
            pending = self._pending.get(state)
            return pending is not None and not self._is_expired(
                pending, self._clock()
            )

    def take(self, state: str) -> Optional[PendingSignIn]:
        """
        The sign-in of the state, which cannot be taken again. None when the
        state is unknown, already used or expired.
        """
        with self._lock:
            pending = self._pending.pop(state, None)
            if pending is None or self._is_expired(pending, self._clock()):
                return None
            return pending

    def _is_expired(self, pending: PendingSignIn, now: float) -> bool:
        return now - pending.created_at >= self._lifetime_seconds

    def _remove_expired(self, now: float) -> None:
        for state_ in [
            state_
            for state_, pending_ in self._pending.items()
            if self._is_expired(pending_, now)
        ]:
            del self._pending[state_]


class GitLabSignIn:
    """
    The sign-in of the user in this run of the application: the sign-ins that
    wait, and the session once one succeeded.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        session_listener: Optional[
            Callable[[PendingSignIn, GitLabSession], None]
        ] = None,
    ) -> None:
        self._clock: Callable[[], float] = clock
        # Called with each session that a sign-in gives: it keeps the tokens.
        self._session_listener: Optional[
            Callable[[PendingSignIn, GitLabSession], None]
        ] = session_listener
        self._pending_sign_ins: PendingSignIns = PendingSignIns(clock=clock)
        self._session: Optional[GitLabSession] = None
        self._lock: threading.Lock = threading.Lock()

    @property
    def session(self) -> Optional[GitLabSession]:
        with self._lock:
            return self._session

    @property
    def user(self) -> Optional[GitLabUser]:
        session = self.session
        return session.user if session is not None else None

    def start(self, *, settings: DesktopSettings, port: int) -> str:
        """
        Prepare a sign-in and return the address of the authorization page,
        where the window goes. Raise OAuthError when the settings are not
        complete.
        """
        if not is_sign_in_configured(settings):
            raise OAuthError(
                gettext(
                    "The sign-in needs the address of GitLab and the "
                    "identifier of the OAuth application in the settings."
                )
            )
        pending = self._pending_sign_ins.create(
            gitlab_url=settings.gitlab_url.strip(),
            client_id=settings.oauth_client_id.strip(),
            redirect_uri=create_redirect_uri(port),
        )
        return build_authorization_url(
            gitlab_url=pending.gitlab_url,
            client_id=pending.client_id,
            redirect_uri=pending.redirect_uri,
            state=pending.state,
            code_challenge=create_code_challenge(pending.code_verifier),
        )

    def is_valid_state(self, state: str) -> bool:
        return self._pending_sign_ins.is_valid_state(state)

    def refuse(self, state: str) -> None:
        """GitLab called back with an error: the sign-in is over."""
        self._pending_sign_ins.take(state)

    def complete(self, *, state: str, code: str) -> GitLabSession:
        """
        Finish the sign-in of the state with the code that GitLab gave. Raise
        OAuthError.
        """
        pending = self._pending_sign_ins.take(state)
        if pending is None:
            raise OAuthError(
                gettext(
                    "The sign-in is not valid or has expired. Start it again."
                )
            )
        tokens = exchange_code(pending, code, clock=self._clock)
        user = fetch_user(pending.gitlab_url, tokens.access_token)
        session = GitLabSession(tokens=tokens, user=user)
        with self._lock:
            self._session = session
        if self._session_listener is not None:
            self._session_listener(pending, session)
        return session


def parse_callback_query(query: Dict[str, List[str]]) -> Dict[str, str]:
    """
    The parameters of the callback that appear once. A parameter given twice
    is dropped: the callback is then not valid.
    """
    return {
        name_: values_[0]
        for name_, values_ in query.items()
        if len(values_) == 1
    }


def _parse_tokens(
    answer: Dict[str, Any], clock: Callable[[], float]
) -> GitLabTokens:
    access_token = answer.get("access_token")
    refresh_token = answer.get("refresh_token")
    expires_in = answer.get("expires_in")
    if not isinstance(access_token, str) or len(access_token) == 0:
        raise OAuthError(gettext("GitLab did not give an access token."))
    return GitLabTokens(
        access_token=access_token,
        refresh_token=refresh_token if isinstance(refresh_token, str) else None,
        expires_at=clock()
        + (
            float(expires_in)
            if isinstance(expires_in, (int, float))
            and not isinstance(expires_in, bool)
            else DEFAULT_TOKEN_LIFETIME_SECONDS
        ),
    )


def _normalize_gitlab_url(gitlab_url: str) -> str:
    return gitlab_url.strip().rstrip("/")


def _request_json(
    url: str,
    *,
    data: Optional[bytes],
    access_token: Optional[str],
    gitlab_url: str,
) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if access_token is not None:
        headers["Authorization"] = f"Bearer {access_token}"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as answer_:
            content = json.loads(answer_.read(_MAXIMUM_ANSWER_BYTES))
    except urllib.error.HTTPError as exception_:
        reason = _read_error_reason(exception_)
        error_class = (
            OAuthRejectedError if reason == "invalid_grant" else OAuthError
        )
        raise error_class(
            gettext("GitLab refused the request (%(reason)s).")
            % {"reason": reason}
        ) from None
    except (OSError, HTTPException) as exception_:
        # URLError, timeouts and refused connections are OSError. The message
        # of the exception can name the address: it holds no token.
        raise OAuthError(
            gettext("GitLab cannot be reached at %(url)s.")
            % {"url": _normalize_gitlab_url(gitlab_url)}
        ) from exception_
    except ValueError:
        raise OAuthError(
            gettext("GitLab sent an answer that cannot be read.")
        ) from None
    if not isinstance(content, dict):
        raise OAuthError(gettext("GitLab sent an answer that cannot be read."))
    return content


def _read_error_reason(exception: urllib.error.HTTPError) -> str:
    """The "error" field of an answer in OAuth style, else the HTTP status."""
    try:
        content = json.loads(exception.read(_MAXIMUM_ANSWER_BYTES))
    except (OSError, ValueError):
        content = None
    if isinstance(content, dict):
        reason = content.get("error")
        if isinstance(reason, str) and 0 < len(reason) <= 80:
            return reason
    return f"HTTP {exception.code}"


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """
    Do not follow a redirect: the request carries the token, which must not
    go to another address.
    """

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> Optional[urllib.request.Request]:
        del req, fp, code, msg, headers, newurl
        return None


_OPENER = urllib.request.build_opener(_RefuseRedirects)
