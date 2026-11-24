"""
@relation(SDOC-SRS-1235, scope=file)
@relation(SDOC-SRS-1239, scope=file)
"""

import json
import logging
import os
import re
import socket
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from strictdoc.features.desktop.home_app import create_home_app
from strictdoc.features.desktop.oauth_gitlab import (
    GitLabSession,
    GitLabSignIn,
    GitLabTokens,
    GitLabUser,
    OAuthError,
    OAuthRejectedError,
    refresh_tokens,
)
from strictdoc.features.desktop.secret_store import (
    MemorySecretStore,
    SecretStoreError,
)
from strictdoc.features.desktop.settings import DesktopSettings, save_settings
from strictdoc.features.desktop.token_store import (
    MINIMUM_RENEWAL_INTERVAL_SECONDS,
    RENEWAL_MARGIN_SECONDS,
    RETRY_SECONDS,
    SignInStatus,
    TokenKeeper,
    get_token_secret_name,
    parse_session,
    serialize_session,
)
from strictdoc.features.i18n import i18n
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    EMAIL,
    REFRESH_INVALID_GRANT,
    USERNAME,
    FakeGitLab,
)

GITLAB_URL = "https://gitlab.example.org"
SECRET_NAME = "gitlab/gitlab.example.org"
PORT = 18082
LIFETIME = 7200.0


class Clock:
    def __init__(self) -> None:
        self.now: float = 100000.0

    def __call__(self) -> float:
        return self.now


class CountingStore(MemorySecretStore):
    """A store that counts its writes and can refuse them."""

    def __init__(self) -> None:
        super().__init__()
        self.set_calls: List[str] = []
        self.is_refusing: bool = False

    def set(self, name: str, value: str) -> None:
        if self.is_refusing:
            raise SecretStoreError("refused")
        self.set_calls.append(value)
        super().set(name, value)


class Refresher:
    """
    The function that renews the tokens, in place of the call to GitLab. Each
    call gives tokens of numbers 1, 2, ... and records the refresh token that
    it received.
    """

    def __init__(self, clock: Clock) -> None:
        self.clock: Clock = clock
        self.received: List[str] = []
        self.error: Optional[Exception] = None
        self.gate: Optional[threading.Event] = None
        # Set when a call reaches GitLab, before it waits for the gate.
        self.entered: threading.Event = threading.Event()
        # The life of the tokens that it gives, in seconds.
        self.lifetime: float = LIFETIME

    def __call__(
        self,
        *,
        gitlab_url: str,
        client_id: str,
        refresh_token: str,
        clock: Any,
    ) -> GitLabTokens:
        assert gitlab_url == GITLAB_URL
        assert client_id == "the-client"
        self.entered.set()
        if self.gate is not None:
            assert self.gate.wait(10)
        self.received.append(refresh_token)
        if self.error is not None:
            raise self.error
        number = len(self.received)
        return GitLabTokens(
            access_token=f"access-{number}",
            refresh_token=f"refresh-{number}",
            expires_at=clock() + self.lifetime,
        )


def _create_session(
    clock: Clock, *, expires_in: float = LIFETIME
) -> GitLabSession:
    return GitLabSession(
        tokens=GitLabTokens(
            access_token="access-0",
            refresh_token="refresh-0",
            expires_at=clock() + expires_in,
        ),
        user=GitLabUser(
            username="jdupont", display_name="Jeanne Dupont", email="j@x.org"
        ),
    )


class Setup:
    def __init__(self) -> None:
        self.clock: Clock = Clock()
        self.store: CountingStore = CountingStore()
        self.refresher: Refresher = Refresher(self.clock)
        self.keeper: TokenKeeper = TokenKeeper(
            self.store,
            clock=self.clock,
            refresh=self.refresher,
            use_timer=False,
        )

    def sign_in(self, *, expires_in: float = LIFETIME) -> None:
        self.keeper.adopt(
            gitlab_url=GITLAB_URL,
            client_id="the-client",
            session=_create_session(self.clock, expires_in=expires_in),
        )

    def restart(self) -> TokenKeeper:
        """A new launch of the application, with the same store."""
        self.keeper.close()
        self.keeper = TokenKeeper(
            self.store,
            clock=self.clock,
            refresh=self.refresher,
            use_timer=False,
        )
        self.keeper.restore(gitlab_url=GITLAB_URL, client_id="the-client")
        return self.keeper


@pytest.fixture(name="setup")
def fixture_setup() -> Iterator[Setup]:
    setup = Setup()
    yield setup
    setup.keeper.close()


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Iterator[None]:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture(name="fake_gitlab")
def fixture_fake_gitlab() -> Iterator[FakeGitLab]:
    with FakeGitLab() as fake_gitlab:
        yield fake_gitlab


def _get_unused_port() -> int:
    with socket.socket() as probe_:
        probe_.bind(("127.0.0.1", 0))
        port: int = probe_.getsockname()[1]
    return port


# The record.


def test_001_the_record_holds_the_tokens_the_end_and_the_identity() -> None:
    clock = Clock()
    session = _create_session(clock)

    record = json.loads(serialize_session(session))

    assert record == {
        "version": 1,
        "access_token": "access-0",
        "refresh_token": "refresh-0",
        "expires_at": clock() + LIFETIME,
        "username": "jdupont",
        "name": "Jeanne Dupont",
        "email": "j@x.org",
        "user_id": 0,
        "public_email": "",
        "commit_email": "",
    }
    assert parse_session(serialize_session(session)) == session


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        json.dumps({"version": 2}),
        json.dumps({"version": 1, "access_token": "a", "username": "u"}),
        json.dumps(
            {
                "version": 1,
                "access_token": "a",
                "refresh_token": None,
                "expires_at": True,
                "username": "u",
            }
        ),
        json.dumps(
            {
                "version": 1,
                "access_token": "a",
                "refresh_token": None,
                "expires_at": 1.0,
                "username": "",
            }
        ),
    ],
)
def test_002_a_record_that_is_not_good_is_not_a_session(content: str) -> None:
    assert parse_session(content) is None


def test_003_the_name_of_the_record_follows_the_host_of_gitlab() -> None:
    assert get_token_secret_name("https://GitLab.Karka.lan/") == (
        "gitlab/gitlab.karka.lan"
    )
    assert get_token_secret_name("http://localhost:8080") == (
        "gitlab/localhost:8080"
    )


# The keeper: sign-in, restore.


def test_004_a_sign_in_writes_one_record_and_no_variable(
    setup: Setup,
) -> None:
    setup.sign_in()

    assert setup.keeper.status is SignInStatus.SIGNED_IN
    assert len(setup.store.set_calls) == 1
    stored = setup.store.get(SECRET_NAME)
    assert stored is not None
    assert parse_session(stored) == setup.keeper.session
    assert setup.keeper.get_access_token() == "access-0"
    assert not _is_token_in_environment("access-0")


def test_005_a_token_that_is_still_good_is_used_with_no_network_call(
    setup: Setup,
) -> None:
    setup.sign_in()

    keeper = setup.restart()

    assert keeper.session == _create_session(setup.clock)
    assert keeper.status is SignInStatus.SIGNED_IN
    assert keeper.get_access_token() == "access-0"
    assert not _is_token_in_environment("access-0")
    assert setup.refresher.received == []
    # The renewal is due 5 minutes before the end.
    assert keeper.get_seconds_until_renewal() == (
        LIFETIME - RENEWAL_MARGIN_SECONDS
    )


def test_006_without_a_record_the_user_is_signed_out(setup: Setup) -> None:
    keeper = setup.restart()

    assert keeper.session is None
    assert keeper.status is SignInStatus.SIGNED_OUT
    assert keeper.get_seconds_until_renewal() is None


def test_007_a_record_that_is_not_good_is_ignored(setup: Setup) -> None:
    setup.store.set(SECRET_NAME, "not json")

    keeper = setup.restart()

    assert keeper.status is SignInStatus.SIGNED_OUT
    # It is not deleted: the user may have a newer version of the program.
    assert setup.store.get(SECRET_NAME) == "not json"


# The renewal.


def test_008_the_renewal_replaces_both_tokens_in_one_write(
    setup: Setup,
) -> None:
    setup.sign_in()
    setup.clock.now += LIFETIME - RENEWAL_MARGIN_SECONDS

    setup.keeper.renew()

    assert setup.refresher.received == ["refresh-0"]
    session = setup.keeper.session
    assert session is not None
    assert session.tokens.access_token == "access-1"
    assert session.tokens.refresh_token == "refresh-1"
    assert session.tokens.expires_at == setup.clock() + LIFETIME
    assert session.user.username == "jdupont"
    # Writes: the sign-in, then the renewal with both new tokens.
    assert len(setup.store.set_calls) == 2
    stored = parse_session(setup.store.set_calls[-1])
    assert stored == session
    assert setup.keeper.get_access_token() == "access-1"
    assert not _is_token_in_environment("access-1")


def test_009_a_token_that_is_not_due_is_not_renewed(setup: Setup) -> None:
    setup.sign_in()
    setup.clock.now += LIFETIME - RENEWAL_MARGIN_SECONDS - 1

    setup.keeper.renew()

    assert setup.refresher.received == []


def test_010_a_token_that_has_ended_is_renewed_at_the_launch(
    setup: Setup,
) -> None:
    setup.sign_in()
    setup.clock.now += LIFETIME + 3600

    keeper = setup.restart()
    # The token of the record has ended: it is the old one.
    assert keeper.session is not None
    assert keeper.session.tokens.access_token == "access-0"
    assert keeper.session.tokens.expires_at <= setup.clock()
    assert keeper.get_seconds_until_renewal() == 0
    keeper.renew()

    assert setup.refresher.received == ["refresh-0"]
    assert keeper.get_access_token() == "access-1"
    assert not _is_token_in_environment("access-1")
    assert keeper.status is SignInStatus.SIGNED_IN


def test_011_a_refusal_of_gitlab_ends_the_session_and_deletes_the_record(
    setup: Setup,
) -> None:
    setup.sign_in()
    setup.clock.now += LIFETIME
    setup.refresher.error = OAuthRejectedError("invalid_grant")

    setup.keeper.renew()

    assert setup.keeper.session is None
    assert setup.keeper.status is SignInStatus.SIGNED_OUT
    assert setup.keeper.is_refused
    assert setup.store.get(SECRET_NAME) is None


def test_012_a_network_failure_keeps_the_session_and_the_record(
    setup: Setup,
) -> None:
    setup.sign_in()
    setup.clock.now += LIFETIME - 60
    setup.refresher.error = OAuthError("cannot be reached")

    with pytest.raises(OAuthError):
        setup.keeper.renew()

    # The token is still good for a minute: the user is not offline yet.
    assert setup.keeper.status is SignInStatus.SIGNED_IN
    assert setup.store.get(SECRET_NAME) is not None
    assert not setup.keeper.is_refused
    assert setup.keeper.get_access_token() == "access-0"
    assert not _is_token_in_environment("access-0")
    # No new try before the pause: GitLab is not asked again at once.
    setup.keeper.renew()
    assert len(setup.refresher.received) == 1

    setup.clock.now += 61
    assert setup.keeper.status is SignInStatus.OFFLINE
    assert setup.keeper.session is not None
    # The token has ended and cannot be renewed: there is none to give.
    assert setup.keeper.get_access_token() is None

    # The network comes back.
    setup.refresher.error = None
    setup.clock.now += RETRY_SECONDS
    setup.keeper.renew()
    assert setup.keeper.status is SignInStatus.SIGNED_IN
    # The third call of the refresher: the second was the one of the check
    # above, which failed like the first.
    assert setup.keeper.get_access_token() == "access-3"
    assert not _is_token_in_environment("access-3")


def test_013_a_token_that_ends_in_the_margin_is_not_asked_for_in_a_loop(
    setup: Setup,
) -> None:
    # GitLab gives a token that lives less than the margin.
    setup.clock.now = 0.0
    setup.refresher.lifetime = 100
    setup.sign_in(expires_in=100)

    setup.keeper.renew()
    setup.keeper.renew()
    setup.keeper.renew()

    assert len(setup.refresher.received) == 1
    setup.clock.now += MINIMUM_RENEWAL_INTERVAL_SECONDS
    setup.keeper.renew()
    assert len(setup.refresher.received) == 2


def test_014_two_renewals_at_once_make_one_call(setup: Setup) -> None:
    setup.sign_in()
    setup.clock.now += LIFETIME
    gate = threading.Event()
    setup.refresher.gate = gate
    errors: List[BaseException] = []

    def renew() -> None:
        try:
            setup.keeper.renew()
        except BaseException as exception_:  # noqa: BLE001
            errors.append(exception_)

    first = threading.Thread(target=renew)
    second = threading.Thread(target=renew)
    first.start()
    # The first call is inside GitLab, the second waits for the lock.
    deadline = time.monotonic() + 5
    while setup.keeper._renew_lock.locked() is False:  # noqa: SLF001
        assert time.monotonic() < deadline
        time.sleep(0.01)
    second.start()
    time.sleep(0.1)
    gate.set()
    first.join(10)
    second.join(10)

    assert errors == []
    assert setup.refresher.received == ["refresh-0"]
    session = setup.keeper.session
    assert session is not None
    assert session.tokens.access_token == "access-1"


def test_015_get_access_token_renews_first_and_gives_a_good_token(
    setup: Setup,
) -> None:
    assert setup.keeper.get_access_token() is None
    setup.sign_in()
    assert setup.keeper.get_access_token() == "access-0"

    setup.clock.now += LIFETIME
    assert setup.keeper.get_access_token() == "access-1"

    # Ended, and GitLab cannot be reached: no token.
    setup.clock.now += LIFETIME + RETRY_SECONDS
    setup.refresher.error = OAuthError("cannot be reached")
    assert setup.keeper.get_access_token() is None
    assert setup.keeper.session is not None


def test_016_the_timer_renews_before_the_end_of_the_token() -> None:
    store = CountingStore()
    received: List[str] = []

    def refresh(**arguments: Any) -> GitLabTokens:
        received.append(arguments["refresh_token"])
        return GitLabTokens(
            access_token="access-new",
            refresh_token="refresh-new",
            expires_at=time.time() + 1000,
        )

    keeper = TokenKeeper(
        store,
        refresh=refresh,
        margin_seconds=0.5,
    )
    try:
        keeper.adopt(
            gitlab_url=GITLAB_URL,
            client_id="the-client",
            session=GitLabSession(
                tokens=GitLabTokens(
                    access_token="access-0",
                    refresh_token="refresh-0",
                    expires_at=time.time() + 0.8,
                ),
                user=GitLabUser("jdupont", "Jeanne Dupont", ""),
            ),
        )
        deadline = time.monotonic() + 10
        while len(received) == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert received == ["refresh-0"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            session = keeper.session
            if (
                session is not None
                and session.tokens.access_token == "access-new"
            ):
                break
            time.sleep(0.05)
        assert keeper.session is not None
        assert keeper.session.tokens.refresh_token == "refresh-new"
    finally:
        keeper.close()


def test_017_the_sign_out_deletes_the_record(
    setup: Setup,
) -> None:
    setup.sign_in()

    setup.keeper.sign_out()

    assert setup.keeper.status is SignInStatus.SIGNED_OUT
    assert not setup.keeper.is_refused
    assert setup.store.get(SECRET_NAME) is None


def test_018_a_store_that_refuses_the_write_keeps_the_session_in_memory(
    setup: Setup,
) -> None:
    setup.store.is_refusing = True

    setup.sign_in()

    assert setup.keeper.status is SignInStatus.SIGNED_IN
    assert setup.keeper.get_access_token() == "access-0"
    assert not _is_token_in_environment("access-0")
    assert setup.keeper.storage_error is not None
    assert "did not save the sign-in" in setup.keeper.storage_error
    assert setup.store.get(SECRET_NAME) is None


def test_019_no_token_is_in_a_log_or_a_message(
    setup: Setup, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    setup.sign_in()
    setup.clock.now += LIFETIME
    setup.keeper.renew()
    setup.refresher.error = OAuthError("cannot be reached")
    setup.clock.now += LIFETIME + RETRY_SECONDS
    with pytest.raises(OAuthError):
        setup.keeper.renew()

    for token_ in ("access-0", "access-1", "refresh-0", "refresh-1"):
        assert token_ not in caplog.text
    session = setup.keeper.session
    assert session is not None
    assert "access-1" not in repr(session)
    assert "refresh-1" not in repr(session)


# No variable of the process holds a token.


def _is_token_in_environment(token: str) -> bool:
    return token in os.environ.values()


def test_020_no_variable_of_the_process_holds_a_token(setup: Setup) -> None:
    tokens = ["access-0", "refresh-0", "access-1", "refresh-1"]

    setup.sign_in()
    assert not any(_is_token_in_environment(token_) for token_ in tokens)
    setup.clock.now += LIFETIME - 60
    setup.keeper.renew()
    assert setup.keeper.get_access_token() == "access-1"
    assert not any(_is_token_in_environment(token_) for token_ in tokens)
    setup.restart()
    assert not any(_is_token_in_environment(token_) for token_ in tokens)


# The renewal against the fake GitLab.


def test_022_gitlab_gives_new_tokens_and_the_old_refresh_token_is_spent(
    fake_gitlab: FakeGitLab,
) -> None:
    sign_in = GitLabSignIn()
    session = _sign_in(fake_gitlab, sign_in)
    refresh_token = session.tokens.refresh_token
    assert refresh_token is not None

    tokens = refresh_tokens(
        gitlab_url=fake_gitlab.url,
        client_id=CLIENT_ID,
        refresh_token=refresh_token,
    )

    assert tokens.access_token != session.tokens.access_token
    assert tokens.refresh_token not in (None, refresh_token)
    (request,) = fake_gitlab.refresh_requests
    assert request == {"client_id": CLIENT_ID, "grant_type": "refresh_token"}
    # GitLab replaces the refresh token at each renewal.
    with pytest.raises(OAuthRejectedError, match="invalid_grant"):
        refresh_tokens(
            gitlab_url=fake_gitlab.url,
            client_id=CLIENT_ID,
            refresh_token=refresh_token,
        )


def test_023_only_invalid_grant_is_a_refusal_and_the_network_is_not(
    fake_gitlab: FakeGitLab,
) -> None:
    fake_gitlab.refresh_mode = REFRESH_INVALID_GRANT
    with pytest.raises(OAuthRejectedError):
        refresh_tokens(
            gitlab_url=fake_gitlab.url,
            client_id=CLIENT_ID,
            refresh_token="a-token",
        )

    unused_url = f"http://127.0.0.1:{_get_unused_port()}"
    with pytest.raises(OAuthError) as error_info:
        refresh_tokens(
            gitlab_url=unused_url,
            client_id=CLIENT_ID,
            refresh_token="a-token",
        )
    assert not isinstance(error_info.value, OAuthRejectedError)


# The home screen.


class Home:
    def __init__(
        self, tmp_path: Path, gitlab_url: str, keeper: TokenKeeper
    ) -> None:
        self.settings_path: Path = tmp_path / "config" / "settings.json"
        catalog_path = tmp_path / "catalog.json"
        catalog_path.write_text("[]", encoding="utf-8")
        save_settings(
            DesktopSettings(
                catalog_provider="fake",
                fake_catalog_path=str(catalog_path),
                gitlab_url=gitlab_url,
                oauth_client_id=CLIENT_ID,
            ),
            self.settings_path,
        )
        self.application = create_home_app(
            settings_path=self.settings_path, keeper=keeper
        )


def test_024_the_home_names_the_user_from_the_record_with_no_network(
    tmp_path: Path,
) -> None:
    clock = Clock()
    store = CountingStore()
    # The address of GitLab answers nothing: any call would fail.
    gitlab_url = f"http://127.0.0.1:{_get_unused_port()}"
    store.set(
        get_token_secret_name(gitlab_url),
        serialize_session(_create_session(clock)),
    )
    calls: List[str] = []

    def refresh(**arguments: Any) -> GitLabTokens:
        calls.append(arguments["refresh_token"])
        raise AssertionError("The network must not be used.")

    keeper = TokenKeeper(store, clock=clock, refresh=refresh)
    home = Home(tmp_path, gitlab_url, keeper)
    try:
        with TestClient(home.application) as client:
            page = client.get("/").text
    finally:
        keeper.close()

    assert "Jeanne Dupont" in page
    assert 'data-testid="sign-in"' not in page
    assert 'data-testid="offline-notice"' not in page
    assert calls == []


def test_025_the_home_says_offline_when_the_token_has_ended_without_network(
    tmp_path: Path,
) -> None:
    clock = Clock()
    store = CountingStore()
    gitlab_url = f"http://127.0.0.1:{_get_unused_port()}"
    session = _create_session(clock)
    store.set(get_token_secret_name(gitlab_url), serialize_session(session))
    clock.now += LIFETIME + 10
    # The real call: nobody listens at the address.
    keeper = TokenKeeper(
        store,
        clock=clock,
        refresh=refresh_tokens,
        use_timer=False,
    )
    home = Home(tmp_path, gitlab_url, keeper)
    try:
        with TestClient(home.application) as client:
            with pytest.raises(OAuthError):
                keeper.renew()
            page = client.get("/").text
            i18n.set_language("fr")
            french_page = client.get("/").text
    finally:
        keeper.close()

    assert "Jeanne Dupont" in page
    assert 'data-testid="offline-notice"' in page
    assert "You are offline" in page
    assert "Vous êtes hors ligne" in french_page
    # The tokens are kept: the user is not signed out.
    assert store.get(get_token_secret_name(gitlab_url)) is not None


def test_026_the_home_offers_the_sign_in_again_after_a_refusal(
    tmp_path: Path, fake_gitlab: FakeGitLab
) -> None:
    clock = Clock()
    store = CountingStore()
    store.set(
        get_token_secret_name(fake_gitlab.url),
        serialize_session(_create_session(clock)),
    )
    clock.now += LIFETIME + 10
    fake_gitlab.refresh_mode = REFRESH_INVALID_GRANT
    keeper = TokenKeeper(
        store,
        clock=clock,
        refresh=refresh_tokens,
        use_timer=False,
    )
    home = Home(tmp_path, fake_gitlab.url, keeper)
    try:
        with TestClient(home.application) as client:
            keeper.renew()
            page = client.get("/").text
    finally:
        keeper.close()

    assert 'data-testid="sign-in"' in page
    assert 'data-testid="sign-in-expired"' in page
    assert "Jeanne Dupont" not in page
    assert store.get(get_token_secret_name(fake_gitlab.url)) is None
    assert len(fake_gitlab.refresh_requests) == 1


def test_027_a_sign_in_keeps_its_record_in_the_store_and_not_in_the_settings(
    tmp_path: Path, fake_gitlab: FakeGitLab
) -> None:
    store = CountingStore()
    keeper = TokenKeeper(store, use_timer=False)
    sign_in = GitLabSignIn(session_listener=keeper.adopt_sign_in)
    home = Home(tmp_path, fake_gitlab.url, keeper)
    try:
        session = _sign_in(fake_gitlab, sign_in)
        with TestClient(home.application) as client:
            page = client.get("/").text
    finally:
        keeper.close()

    stored = store.get(get_token_secret_name(fake_gitlab.url))
    assert stored is not None
    record = json.loads(stored)
    assert record["access_token"] == session.tokens.access_token
    assert record["refresh_token"] == session.tokens.refresh_token
    assert record["username"] == USERNAME
    assert record["name"] == DISPLAY_NAME
    assert record["email"] == EMAIL
    assert not _is_token_in_environment(session.tokens.access_token)
    assert DISPLAY_NAME in page
    # The settings hold none of it.
    settings_text = home.settings_path.read_text(encoding="utf-8")
    assert session.tokens.access_token not in settings_text
    assert session.tokens.refresh_token not in settings_text
    assert "token" not in settings_text


# The renewal and the changes of the session.


def _create_other_session(clock: Clock) -> GitLabSession:
    return GitLabSession(
        tokens=GitLabTokens(
            access_token="access-B",
            refresh_token="refresh-B",
            expires_at=clock() + LIFETIME,
        ),
        user=GitLabUser(username="pmartin", display_name="Paul", email=""),
    )


def _start_renewal_during_which(setup: Setup) -> "RenewalInProgress":
    setup.sign_in()
    setup.clock.now += LIFETIME
    return RenewalInProgress(setup)


class RenewalInProgress:
    """A renewal that waits inside GitLab, until the test lets it go."""

    def __init__(self, setup: Setup) -> None:
        self.setup: Setup = setup
        self.gate: threading.Event = threading.Event()
        setup.refresher.gate = self.gate
        self.errors: List[BaseException] = []
        self.thread: threading.Thread = threading.Thread(target=self._run)
        self.thread.start()
        assert setup.refresher.entered.wait(10)

    def finish(self) -> None:
        self.gate.set()
        self.thread.join(10)
        assert not self.thread.is_alive()
        assert self.errors == []

    def _run(self) -> None:
        try:
            self.setup.keeper.renew()
        except BaseException as exception_:  # noqa: BLE001
            self.errors.append(exception_)


def test_028_a_sign_out_during_a_renewal_is_not_undone(setup: Setup) -> None:
    renewal = _start_renewal_during_which(setup)

    setup.keeper.sign_out()
    renewal.finish()

    # The tokens that GitLab gave after the sign-out are dropped.
    assert setup.keeper.session is None
    assert setup.keeper.status is SignInStatus.SIGNED_OUT
    assert setup.store.get(SECRET_NAME) is None


def test_029_a_new_sign_in_during_a_renewal_is_not_replaced(
    setup: Setup,
) -> None:
    renewal = _start_renewal_during_which(setup)

    other_session = _create_other_session(setup.clock)
    setup.keeper.adopt(
        gitlab_url=GITLAB_URL, client_id="the-client", session=other_session
    )
    renewal.finish()

    assert setup.keeper.session == other_session
    stored = setup.store.get(SECRET_NAME)
    assert stored is not None
    assert parse_session(stored) == other_session
    assert setup.keeper.get_access_token() == "access-B"
    assert not _is_token_in_environment("access-B")


def test_030_a_refusal_during_a_new_sign_in_does_not_end_the_new_session(
    setup: Setup,
) -> None:
    setup.refresher.error = OAuthRejectedError("invalid_grant")
    renewal = _start_renewal_during_which(setup)

    other_session = _create_other_session(setup.clock)
    setup.keeper.adopt(
        gitlab_url=GITLAB_URL, client_id="the-client", session=other_session
    )
    renewal.finish()

    assert setup.keeper.session == other_session
    assert not setup.keeper.is_refused
    stored = setup.store.get(SECRET_NAME)
    assert stored is not None
    assert parse_session(stored) == other_session
    assert setup.keeper.get_access_token() == "access-B"
    assert not _is_token_in_environment("access-B")


def test_031_a_network_failure_during_a_new_sign_in_spares_the_new_session(
    setup: Setup,
) -> None:
    setup.refresher.error = OAuthError("cannot be reached")
    setup.sign_in()
    setup.clock.now += LIFETIME
    gate = threading.Event()
    setup.refresher.gate = gate
    errors: List[BaseException] = []

    def renew() -> None:
        try:
            setup.keeper.renew()
        except OAuthError as exception_:
            errors.append(exception_)

    thread = threading.Thread(target=renew)
    thread.start()
    assert setup.refresher.entered.wait(10)
    setup.keeper.adopt(
        gitlab_url=GITLAB_URL,
        client_id="the-client",
        session=_create_other_session(setup.clock),
    )
    gate.set()
    thread.join(10)

    assert len(errors) == 1
    assert setup.keeper.get_access_token() == "access-B"
    # The new session is not marked as failed, and is due when its time comes.
    assert setup.keeper.get_seconds_until_renewal() == (
        LIFETIME - RENEWAL_MARGIN_SECONDS
    )
    setup.clock.now += LIFETIME + 1
    assert setup.keeper.status is SignInStatus.SIGNED_IN


def test_032_the_listeners_hear_each_change_of_the_session_and_not_a_renewal(
    setup: Setup,
) -> None:
    calls: List[str] = []
    setup.keeper.add_session_listener(lambda: calls.append("changed"))

    setup.sign_in()
    assert calls == ["changed"]
    setup.clock.now += LIFETIME
    setup.keeper.renew()
    assert calls == ["changed"]
    setup.keeper.sign_out()
    assert calls == ["changed", "changed"]
    setup.sign_in()
    setup.clock.now += LIFETIME
    setup.refresher.error = OAuthRejectedError("invalid_grant")
    setup.keeper.renew()
    assert calls == ["changed"] * 4


class SlowStore(CountingStore):
    """A store whose write waits until the test lets it go."""

    def __init__(self) -> None:
        super().__init__()
        self.entered: threading.Event = threading.Event()
        self.gate: threading.Event = threading.Event()

    def set(self, name: str, value: str) -> None:
        self.entered.set()
        assert self.gate.wait(10)
        super().set(name, value)


def test_033_a_slow_keyring_does_not_hold_up_the_readers_of_the_session() -> (
    None
):
    store = SlowStore()
    clock = Clock()
    keeper = TokenKeeper(store, clock=clock, use_timer=False)
    thread = threading.Thread(
        target=keeper.adopt,
        kwargs={
            "gitlab_url": GITLAB_URL,
            "client_id": "the-client",
            "session": _create_session(clock),
        },
    )
    try:
        thread.start()
        assert store.entered.wait(10)

        started_at = time.monotonic()
        session = keeper.session
        status = keeper.status
        url = keeper.gitlab_url
        token = keeper.get_access_token()
        elapsed = time.monotonic() - started_at

        # The write is still waiting: the readers did not wait for it.
        assert thread.is_alive()
        assert elapsed < 1.0
        assert session is not None
        assert status is SignInStatus.SIGNED_IN
        assert url == GITLAB_URL
        assert token == "access-0"
    finally:
        store.gate.set()
        thread.join(10)
        keeper.close()
    assert store.get(SECRET_NAME) is not None


def test_034_the_token_is_current_until_it_ends_also_in_the_margin(
    setup: Setup,
) -> None:
    setup.sign_in()
    # The token ends in 100 seconds: it is due for renewal, and still good.
    setup.clock.now += LIFETIME - 100

    keeper = setup.restart()
    assert keeper.session is not None
    assert keeper.session.tokens.access_token == "access-0"
    assert keeper.status is SignInStatus.SIGNED_IN
    assert not _is_token_in_environment("access-0")
    # Once it has ended, and cannot be renewed, there is none to give.
    setup.clock.now += 100
    setup.refresher.error = OAuthError("cannot be reached")
    keeper = setup.restart()
    assert keeper.get_access_token() is None
    assert not _is_token_in_environment("access-0")


def _sign_in(fake_gitlab: FakeGitLab, sign_in: GitLabSignIn) -> GitLabSession:
    """Go through the authorization page of the fake GitLab, as a window."""
    settings = DesktopSettings(
        gitlab_url=fake_gitlab.url, oauth_client_id=CLIENT_ID
    )
    authorization_url = sign_in.start(settings=settings, port=PORT)
    with urllib.request.urlopen(authorization_url, timeout=10) as answer_:
        page = answer_.read().decode("utf-8")
    found = re.search(r'window\.location = "([^"]+)";', page)
    assert found is not None
    query: Dict[str, str] = {
        name_: values_[0]
        for name_, values_ in parse_qs(urlparse(found.group(1)).query).items()
    }
    return sign_in.complete(state=query["state"], code=query["code"])
