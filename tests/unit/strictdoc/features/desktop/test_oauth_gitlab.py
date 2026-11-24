"""
@relation(SDOC-SRS-1234, scope=file)
"""

import json
import re
import socket
import urllib.request
from pathlib import Path
from typing import Dict, Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from strictdoc.features.desktop.home_app import create_home_app
from strictdoc.features.desktop.oauth_gitlab import (
    CALLBACK_PATH,
    MAXIMUM_PENDING_SIGN_INS,
    OAUTH_SCOPES,
    GitLabSignIn,
    OAuthError,
    PendingSignIn,
    PendingSignIns,
    build_authorization_url,
    create_code_challenge,
    create_code_verifier,
    create_redirect_uri,
    exchange_code,
    fetch_user,
    is_sign_in_configured,
)
from strictdoc.features.desktop.session_token import (
    BOOTSTRAP_PATH,
    PUBLIC_PATHS_STATE_NAME,
    DesktopSessionMiddleware,
    SessionCredentials,
)
from strictdoc.features.desktop.settings import (
    TEST_GITLAB_URL,
    TEST_OAUTH_CLIENT_ID,
    DesktopSettings,
    load_settings,
    save_settings,
)
from strictdoc.features.i18n import i18n
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    MODE_DENY,
    MODE_WRONG_STATE,
    USERNAME,
    FakeGitLab,
)

PORT = 18081
HOME_URL = f"http://127.0.0.1:{PORT}"
REDIRECT_URI = create_redirect_uri(PORT)
# The example of RFC 7636, appendix B.
RFC_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


class Clock:
    def __init__(self) -> None:
        self.now: float = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Iterator[None]:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture(name="fake_gitlab")
def fixture_fake_gitlab() -> Iterator[FakeGitLab]:
    with FakeGitLab() as fake_gitlab:
        yield fake_gitlab


def _create_pending(fake_gitlab: FakeGitLab) -> PendingSignIn:
    return PendingSignIns().create(
        gitlab_url=fake_gitlab.url,
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
    )


def _get_unused_port() -> int:
    with socket.socket() as probe_:
        probe_.bind(("127.0.0.1", 0))
        port: int = probe_.getsockname()[1]
    return port


# The PKCE verifier and challenge.


def test_001_code_verifier_is_random_and_has_the_length_of_rfc_7636() -> None:
    verifiers = {create_code_verifier() for _ in range(20)}

    assert len(verifiers) == 20
    for verifier_ in verifiers:
        assert 43 <= len(verifier_) <= 128
        assert re.fullmatch(r"[A-Za-z0-9\-._~]+", verifier_) is not None


def test_002_code_challenge_is_the_s256_of_the_verifier() -> None:
    assert create_code_challenge(RFC_VERIFIER) == RFC_CHALLENGE
    # No padding, no character that needs an escape in a URL.
    assert "=" not in create_code_challenge(create_code_verifier())


# The addresses.


def test_003_authorization_url_carries_the_parameters_of_the_flow() -> None:
    url = build_authorization_url(
        gitlab_url="https://gitlab.example.org/",
        client_id="the-client",
        redirect_uri="http://127.0.0.1:5000/__desktop/oauth/callback",
        state="the-state",
        code_challenge=RFC_CHALLENGE,
    )

    parts = urlparse(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == (
        "https://gitlab.example.org/oauth/authorize"
    )
    assert {
        name_: values_[0] for name_, values_ in parse_qs(parts.query).items()
    } == {
        "client_id": "the-client",
        "redirect_uri": "http://127.0.0.1:5000/__desktop/oauth/callback",
        "response_type": "code",
        "scope": OAUTH_SCOPES,
        "state": "the-state",
        "code_challenge": RFC_CHALLENGE,
        "code_challenge_method": "S256",
    }


def test_004_redirect_uri_is_on_the_loopback_with_the_port() -> None:
    assert create_redirect_uri(51234) == (
        "http://127.0.0.1:51234/__desktop/oauth/callback"
    )


# The state of a sign-in.


def test_005_a_state_is_random_and_works_once() -> None:
    pending_sign_ins = PendingSignIns()

    first = pending_sign_ins.create(
        gitlab_url="https://g", client_id="c", redirect_uri=REDIRECT_URI
    )
    second = pending_sign_ins.create(
        gitlab_url="https://g", client_id="c", redirect_uri=REDIRECT_URI
    )

    assert first.state != second.state
    assert first.code_verifier != second.code_verifier
    assert pending_sign_ins.is_valid_state(first.state)
    # Asking does not use the state.
    assert pending_sign_ins.is_valid_state(first.state)
    assert pending_sign_ins.take(first.state) == first
    assert not pending_sign_ins.is_valid_state(first.state)
    assert pending_sign_ins.take(first.state) is None
    assert pending_sign_ins.take(second.state) == second


def test_006_a_state_expires_after_ten_minutes() -> None:
    clock = Clock()
    pending_sign_ins = PendingSignIns(clock=clock)
    pending = pending_sign_ins.create(
        gitlab_url="https://g", client_id="c", redirect_uri=REDIRECT_URI
    )

    clock.now += 599
    assert pending_sign_ins.is_valid_state(pending.state)
    clock.now += 1
    assert not pending_sign_ins.is_valid_state(pending.state)
    assert pending_sign_ins.take(pending.state) is None


def test_007_unknown_state_and_limit_of_waiting_sign_ins() -> None:
    pending_sign_ins = PendingSignIns()
    assert not pending_sign_ins.is_valid_state("unknown")
    assert not pending_sign_ins.is_valid_state("")
    assert pending_sign_ins.take("unknown") is None

    created = [
        pending_sign_ins.create(
            gitlab_url="https://g", client_id="c", redirect_uri=REDIRECT_URI
        )
        for _ in range(MAXIMUM_PENDING_SIGN_INS + 1)
    ]

    # The oldest sign-in is dropped to make room.
    assert not pending_sign_ins.is_valid_state(created[0].state)
    assert pending_sign_ins.is_valid_state(created[-1].state)


# The settings of the sign-in.


def test_008_client_id_defaults_to_the_application_of_the_test_gitlab(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"

    def load(content: Dict[str, str]) -> DesktopSettings:
        path.write_text(json.dumps(content), encoding="utf-8")
        return load_settings(path)

    assert load({"gitlab_url": TEST_GITLAB_URL}).oauth_client_id == (
        TEST_OAUTH_CLIENT_ID
    )
    assert load({"gitlab_url": TEST_GITLAB_URL + "/"}).oauth_client_id == (
        TEST_OAUTH_CLIENT_ID
    )
    assert (
        load({"gitlab_url": "https://gitlab.example.org"}).oauth_client_id == ""
    )
    assert load({}).oauth_client_id == ""
    assert (
        load(
            {"gitlab_url": TEST_GITLAB_URL, "oauth_client_id": "mine"}
        ).oauth_client_id
        == "mine"
    )


def test_009_the_sign_in_needs_the_address_and_the_client_id() -> None:
    assert not is_sign_in_configured(DesktopSettings())
    assert not is_sign_in_configured(DesktopSettings(gitlab_url="https://g"))
    assert not is_sign_in_configured(DesktopSettings(oauth_client_id="c"))
    assert not is_sign_in_configured(
        DesktopSettings(gitlab_url=" ", oauth_client_id="c")
    )
    assert is_sign_in_configured(
        DesktopSettings(gitlab_url="https://g", oauth_client_id="c")
    )


# The exchange of the code, with the fake GitLab.


def test_010_the_code_gives_tokens_and_the_user(
    fake_gitlab: FakeGitLab,
) -> None:
    sign_in = GitLabSignIn(clock=Clock())
    settings = DesktopSettings(
        gitlab_url=fake_gitlab.url, oauth_client_id=CLIENT_ID
    )

    authorization_url = sign_in.start(settings=settings, port=PORT)
    callback_path = _authorize(authorization_url)
    session = sign_in.complete(
        state=_get_query(callback_path)["state"],
        code=_get_query(callback_path)["code"],
    )

    assert session.user.username == USERNAME
    assert session.user.display_name == DISPLAY_NAME
    assert session.tokens.refresh_token is not None
    assert session.tokens.expires_at == 1000.0 + 7200
    assert sign_in.user == session.user
    # The token endpoint got the verifier, the redirect address and no secret.
    (token_request,) = fake_gitlab.token_requests
    assert token_request["grant_type"] == "authorization_code"
    assert token_request["redirect_uri"] == REDIRECT_URI
    assert "client_secret" not in token_request
    assert (
        create_code_challenge(token_request["code_verifier"])
        == (parse_qs(urlparse(authorization_url).query)["code_challenge"][0])
    )
    # A token never appears in the representation of an object.
    assert session.tokens.access_token not in repr(session)
    assert session.tokens.refresh_token not in repr(session)


def test_011_a_code_works_once_and_needs_its_verifier(
    fake_gitlab: FakeGitLab,
) -> None:
    pending = _create_pending(fake_gitlab)
    callback_path = _authorize(
        build_authorization_url(
            gitlab_url=fake_gitlab.url,
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            state=pending.state,
            code_challenge=create_code_challenge(pending.code_verifier),
        )
    )
    code = _get_query(callback_path)["code"]

    exchange_code(pending, code)
    with pytest.raises(
        OAuthError, match=r"refused the request \(invalid_grant\)"
    ):
        exchange_code(pending, code)

    other_pending = _create_pending(fake_gitlab)
    other_path = _authorize(
        build_authorization_url(
            gitlab_url=fake_gitlab.url,
            client_id=CLIENT_ID,
            redirect_uri=REDIRECT_URI,
            state=other_pending.state,
            code_challenge=create_code_challenge(other_pending.code_verifier),
        )
    )
    # The verifier of another sign-in does not go with this code.
    with pytest.raises(OAuthError, match="invalid_grant"):
        exchange_code(pending, _get_query(other_path)["code"])


def test_012_gitlab_that_cannot_be_reached_is_an_error_without_token() -> None:
    unused_url = f"http://127.0.0.1:{_get_unused_port()}"
    pending = PendingSignIns().create(
        gitlab_url=unused_url, client_id=CLIENT_ID, redirect_uri=REDIRECT_URI
    )

    with pytest.raises(OAuthError) as error_info:
        exchange_code(pending, "a-code")

    assert (
        str(error_info.value)
        == f"The server cannot be reached at {unused_url}."
    )
    with pytest.raises(OAuthError, match="cannot be reached"):
        fetch_user(unused_url, "a-token")


def test_013_the_user_is_not_given_to_an_unknown_token(
    fake_gitlab: FakeGitLab,
) -> None:
    with pytest.raises(OAuthError, match=r"refused the request \(HTTP 401\)"):
        fetch_user(fake_gitlab.url, "not-a-token")


def test_014_the_state_that_is_not_waiting_is_refused(
    fake_gitlab: FakeGitLab,
) -> None:
    sign_in = GitLabSignIn()

    with pytest.raises(OAuthError, match="not valid or has expired"):
        sign_in.complete(state="unknown", code="a-code")

    # GitLab was not asked anything.
    assert fake_gitlab.token_requests == []
    assert sign_in.session is None


def test_015_the_sign_in_without_settings_says_what_is_missing() -> None:
    with pytest.raises(OAuthError, match="address of the server"):
        GitLabSignIn().start(settings=DesktopSettings(), port=PORT)


# The home screen, behind the session middleware.


class HomeClients:
    """
    The home application with the middleware of the session, as the server
    runs it. "window" is the client that has the session cookie. A callback
    of GitLab comes from another site: "from_another_site" has no cookie.
    """

    def __init__(self, tmp_path: Path, fake_gitlab: FakeGitLab) -> None:
        self.fake_gitlab: FakeGitLab = fake_gitlab
        self.settings_path: Path = tmp_path / "config" / "settings.json"
        catalog_path = tmp_path / "catalog.json"
        catalog_path.write_text("[]", encoding="utf-8")
        self.save_settings(
            DesktopSettings(
                catalog_provider="fake",
                fake_catalog_path=str(catalog_path),
                gitlab_url=fake_gitlab.url,
                oauth_client_id=CLIENT_ID,
            )
        )
        credentials = SessionCredentials.create()
        self.application = create_home_app(settings_path=self.settings_path)
        self.application.add_middleware(
            DesktopSessionMiddleware,
            credentials=credentials,
            port=PORT,
            allowed_hosts=frozenset({f"127.0.0.1:{PORT}"}),
            public_paths=getattr(
                self.application.state, PUBLIC_PATHS_STATE_NAME
            ),
        )
        self.window = TestClient(self.application, base_url=HOME_URL)
        self.window.__enter__()
        self.window.get(
            f"{BOOTSTRAP_PATH}?code={credentials.bootstrap_code}",
            follow_redirects=False,
        )
        self.from_another_site = TestClient(self.application, base_url=HOME_URL)

    def save_settings(self, settings: DesktopSettings) -> None:
        save_settings(settings, self.settings_path)

    def start_sign_in(self) -> str:
        """Press "Sign in": the callback path that GitLab gives back."""
        response = self.window.post("/sign-in", follow_redirects=False)
        assert response.status_code == 303
        return _authorize(response.headers["location"])

    def close(self) -> None:
        self.window.__exit__()


@pytest.fixture(name="home")
def fixture_home(
    tmp_path: Path, fake_gitlab: FakeGitLab
) -> Iterator[HomeClients]:
    home = HomeClients(tmp_path, fake_gitlab)
    yield home
    home.close()


def test_020_home_offers_the_sign_in_only_when_the_settings_are_complete(
    home: HomeClients,
) -> None:
    page = home.window.get("/").text
    assert 'data-testid="sign-in"' in page
    assert 'data-testid="signed-in-user"' not in page

    home.save_settings(DesktopSettings(catalog_provider="fake"))
    # Settings without the address of the server: no button.
    assert 'data-testid="sign-in"' not in home.window.get("/").text


def test_021_the_sign_in_goes_through_gitlab_and_names_the_user(
    home: HomeClients,
) -> None:
    callback_path = home.start_sign_in()

    # GitLab called back the home server, from another site, without cookie.
    response = home.from_another_site.get(callback_path)

    assert response.status_code == 200
    assert 'data-testid="signed-in"' in response.text
    assert 'window.location.replace("/")' in response.text
    (authorization_request,) = home.fake_gitlab.authorization_requests
    assert authorization_request["redirect_uri"] == REDIRECT_URI
    assert authorization_request["code_challenge_method"] == "S256"
    page = home.window.get("/").text
    assert DISPLAY_NAME in page
    assert USERNAME in page
    assert 'data-testid="sign-in"' not in page
    # The code and the tokens are not in the pages.
    assert _get_query(callback_path)["code"] not in page


def test_022_a_callback_without_cookie_needs_a_state_that_waits(
    home: HomeClients,
) -> None:
    callback_path = home.start_sign_in()
    query = _get_query(callback_path)

    other_site = home.from_another_site
    assert other_site.get(CALLBACK_PATH).status_code == 403
    assert (
        other_site.get(f"{CALLBACK_PATH}?code=x&state=unknown").status_code
        == 403
    )
    # A state that is given twice is not a state.
    assert (
        other_site.get(
            f"{CALLBACK_PATH}?code=x&state={query['state']}&state=y"
        ).status_code
        == 403
    )
    # Only a GET request passes, and only on the callback path.
    assert (
        other_site.post(f"{CALLBACK_PATH}?state={query['state']}").status_code
        == 403
    )
    assert other_site.get(f"/?state={query['state']}").status_code == 403
    assert other_site.get("/jobs/x/status").status_code == 403
    # None of this used the state.
    assert other_site.get(callback_path).status_code == 200
    # It works once: the same callback is refused the second time.
    assert other_site.get(callback_path).status_code == 403


def test_023_a_state_that_was_used_is_a_message_in_the_window(
    home: HomeClients,
) -> None:
    callback_path = home.start_sign_in()
    # The window has the cookie: it reaches the page that says what happened.
    first = home.window.get(callback_path)
    assert first.status_code == 200
    second = home.window.get(callback_path)

    assert second.status_code == 200
    assert "not valid or has expired" in second.text
    assert 'data-testid="back-to-catalog"' in second.text


def test_024_a_forged_state_is_a_message_and_no_sign_in(
    home: HomeClients,
) -> None:
    home.fake_gitlab.mode = MODE_WRONG_STATE
    callback_path = home.start_sign_in()

    response = home.window.get(callback_path)

    assert "not valid or has expired" in response.text
    assert DISPLAY_NAME not in home.window.get("/").text
    assert home.fake_gitlab.token_requests == []


def test_025_a_refusal_of_the_user_is_a_message_and_the_way_back(
    home: HomeClients,
) -> None:
    home.fake_gitlab.mode = MODE_DENY
    callback_path = home.start_sign_in()

    # GitLab sends the state back with the error: the callback gets in.
    response = home.from_another_site.get(callback_path)

    assert response.status_code == 200
    assert "The server refused the sign-in (access_denied)." in response.text
    assert 'data-testid="back-to-catalog"' in response.text
    page = home.window.get("/").text
    assert 'data-testid="sign-in"' in page
    assert DISPLAY_NAME not in page
    assert home.fake_gitlab.token_requests == []
    # The sign-in is over: its state does not work again.
    assert home.from_another_site.get(callback_path).status_code == 403


def test_026_gitlab_that_cannot_be_reached_is_a_message(
    home: HomeClients,
) -> None:
    callback_path = home.start_sign_in()
    gitlab_url = home.fake_gitlab.url
    # GitLab goes away between the authorization and the exchange.
    home.fake_gitlab.stop()

    response = home.from_another_site.get(callback_path)

    assert response.status_code == 200
    assert f"The server cannot be reached at {gitlab_url}." in response.text
    assert DISPLAY_NAME not in home.window.get("/").text


def test_027_the_sign_in_without_settings_is_a_message(
    home: HomeClients,
) -> None:
    home.save_settings(DesktopSettings(catalog_provider="fake"))

    response = home.window.post("/sign-in", follow_redirects=False)

    assert response.status_code == 200
    assert "address of the server" in response.text


def test_028_the_texts_of_the_sign_in_follow_the_language(
    home: HomeClients,
) -> None:
    i18n.set_language("fr")
    assert "Se connecter" in home.window.get("/").text

    home.fake_gitlab.mode = MODE_DENY
    response = home.from_another_site.get(home.start_sign_in())

    assert "Le serveur a refusé la connexion (access_denied)." in response.text


def _authorize(authorization_url: str) -> str:
    """
    Open the authorization page like the window does and follow its script:
    the path and the query of the callback.
    """
    with urllib.request.urlopen(authorization_url, timeout=10) as answer_:
        assert answer_.status == 200
        page = answer_.read().decode("utf-8")
    found = re.search(r'window\.location = "([^"]+)";', page)
    assert found is not None, page
    parts = urlparse(found.group(1))
    assert parts.netloc == f"127.0.0.1:{PORT}"
    return f"{parts.path}?{parts.query}"


def _get_query(path: str) -> Dict[str, str]:
    return {
        name_: values_[0]
        for name_, values_ in parse_qs(urlparse(path).query).items()
    }
