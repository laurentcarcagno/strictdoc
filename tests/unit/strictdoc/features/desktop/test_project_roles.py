"""
@relation(SDOC-SRS-1236, scope=file)
@relation(SDOC-SRS-1237, scope=file)
@relation(SDOC-SRS-1240, scope=file)
"""

import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import pytest
from git import Actor, Repo
from starlette.applications import Starlette
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from strictdoc.features.desktop.gitlab_client import (
    create_catalog_client,
    get_system_ca_bundle,
)
from strictdoc.features.desktop.home_app import create_home_app
from strictdoc.features.desktop.local_server import (
    LocalServerError,
    create_desktop_project_config,
    give_principal_provider,
)
from strictdoc.features.desktop.oauth_gitlab import (
    GitLabSession,
    GitLabSignIn,
    GitLabTokens,
    GitLabUser,
)
from strictdoc.features.desktop.project_opener import ProjectOpener
from strictdoc.features.desktop.project_principals import ProjectPrincipals
from strictdoc.features.desktop.project_servers import ProjectServerManager
from strictdoc.features.desktop.secret_store import MemorySecretStore
from strictdoc.features.desktop.settings import (
    DesktopSettings,
    load_settings,
    save_settings,
)
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.i18n import i18n
from strictdoc.features.project_catalog.catalog import CatalogRole
from strictdoc.features.roles.principal import Principal, PrincipalProvider
from strictdoc.features.roles.route_roles import ROUTE_ROLES
from strictdoc.server.app import create_app
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DEVELOPER,
    GUEST,
    MAINTAINER,
    REPORTER,
    USERNAME,
    FakeGitLab,
)

PORT = 18083
IDENTIFIER = "1"
TOKEN_ENV = "STRICTDOC_TEST_ROLES_TOKEN"


class FakeProjectServer:
    def __init__(
        self, folder: str, principal_provider: Optional[PrincipalProvider]
    ) -> None:
        self.folder: str = folder
        self.principal_provider: Optional[PrincipalProvider] = (
            principal_provider
        )
        self.is_running: bool = False
        self.is_bootstrapped: bool = False
        self.start_url: str = "http://127.0.0.1:5999/__desktop/start?code=a"
        self.direct_url: str = "http://127.0.0.1:5999/"

    def set_bootstrap_listener(self, listener: Any) -> None:
        del listener

    def start(self) -> None:
        self.is_running = True

    def wait_until_ready(self) -> None:
        pass

    def stop(self) -> None:
        self.is_running = False


class Environment:
    """
    The home application with the catalog of the fake GitLab, a user who has
    signed in, and project servers that are fakes.
    """

    def __init__(self, tmp_path: Path, fake_gitlab: FakeGitLab) -> None:
        self.tmp_path: Path = tmp_path
        self.fake_gitlab: FakeGitLab = fake_gitlab
        self.settings_path: Path = tmp_path / "config" / "settings.json"
        self.clone_url: str = self._create_bare_repository()
        fake_gitlab.add_project(
            1, "ISIS", self.clone_url, REPORTER, subgroup="satellites"
        )
        fake_gitlab.add_project(
            2, "Hidden", self.clone_url, GUEST, subgroup="satellites"
        )
        save_settings(
            DesktopSettings(
                catalog_provider="gitlab",
                gitlab_url=fake_gitlab.url,
                oauth_client_id=CLIENT_ID,
                gitlab_projects_root="demo",
            ),
            self.settings_path,
        )
        self.servers: List[FakeProjectServer] = []
        self.keeper: TokenKeeper = TokenKeeper(
            MemorySecretStore(), token_env=TOKEN_ENV, use_timer=False
        )
        self.principals: ProjectPrincipals = ProjectPrincipals(self.keeper)
        self.manager: ProjectServerManager = ProjectServerManager(
            server_factory=self._create_server,
            updater=lambda _: False,
            settings_path=self.settings_path,
            eviction_delay_seconds=0,
            principal_provider_factory=self.principals.create_provider,
        )
        self.opener: ProjectOpener = ProjectOpener(
            manager=self.manager, settings_path=self.settings_path
        )
        self.application = create_home_app(
            settings_path=self.settings_path,
            opener=self.opener,
            keeper=self.keeper,
            principals=self.principals,
        )

    def sign_in(self) -> None:
        """Sign in through the authorization page of the fake GitLab."""
        sign_in = GitLabSignIn(session_listener=self.keeper.adopt_sign_in)
        authorization_url = sign_in.start(
            settings=load_settings(self.settings_path), port=PORT
        )
        with urllib.request.urlopen(authorization_url, timeout=10) as answer_:
            page = answer_.read().decode("utf-8")
        found = re.search(r'window\.location = "([^"]+)";', page)
        assert found is not None
        query = parse_qs(urlparse(found.group(1)).query)
        sign_in.complete(state=query["state"][0], code=query["code"][0])

    def open_project(self, client: TestClient, folder: Path) -> Any:
        """Open the project of the catalog in the folder, and wait for it."""
        response = client.post(
            "/projects/folder",
            data={"identifier": IDENTIFIER, "folder": str(folder)},
        )
        assert response.status_code == 303
        deadline = time.monotonic() + 20
        job_url = response.headers["location"]
        while time.monotonic() < deadline:
            status = client.get(job_url + "/status").json()
            if status["state"] != "running":
                assert status["state"] == "done", status
                return status
            time.sleep(0.05)
        raise AssertionError("The job did not end.")

    def get_principal(self, server_index: int = -1) -> Optional[Principal]:
        provider = self.servers[server_index].principal_provider
        assert provider is not None
        return provider()

    def _create_server(
        self, folder: str, principal_provider: Optional[PrincipalProvider]
    ) -> FakeProjectServer:
        server = FakeProjectServer(folder, principal_provider)
        self.servers.append(server)
        return server

    def _create_bare_repository(self) -> str:
        work_path = self.tmp_path / "work"
        work_path.mkdir()
        (work_path / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
        work_repo = Repo.init(work_path)
        work_repo.index.add(["doc.sdoc"])
        actor = Actor("Test", "test@example.org")
        work_repo.index.commit("Add", author=actor, committer=actor)
        work_repo.close()
        bare_path = self.tmp_path / "remote.git"
        Repo.clone_from(str(work_path), str(bare_path), bare=True).close()
        return f"file://{bare_path}"


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Iterator[None]:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.fixture(name="fake_gitlab")
def fixture_fake_gitlab() -> Iterator[FakeGitLab]:
    with FakeGitLab() as fake_gitlab:
        yield fake_gitlab


@pytest.fixture(name="environment")
def fixture_environment(
    tmp_path: Path, fake_gitlab: FakeGitLab
) -> Iterator[Environment]:
    environment = Environment(tmp_path, fake_gitlab)
    yield environment
    environment.keeper.close()
    os.environ.pop(TOKEN_ENV, None)


def _create_client(environment: Environment) -> TestClient:
    return TestClient(environment.application, follow_redirects=False)


# The principals.


def test_001_the_principal_is_the_user_with_the_role_of_the_project() -> None:
    keeper = TokenKeeper(MemorySecretStore(), token_env=TOKEN_ENV)
    principals = ProjectPrincipals(keeper)
    provider = principals.create_provider("1")

    # Nobody is signed in, and no role is known.
    assert provider() is None
    keeper.adopt(
        gitlab_url="https://g",
        client_id="c",
        session=GitLabSession(
            tokens=GitLabTokens("a", "r", time.time() + 7200),
            user=GitLabUser("jdupont", "Jeanne", "j@x.org"),
        ),
    )
    try:
        assert provider() is None
        principals.set_role("1", CatalogRole.READER)
        principal = provider()
        assert principal is not None
        assert (principal.user, principal.email) == ("jdupont", "j@x.org")
        assert principal.role == "reader"
        assert principal.authenticated
        # The role is per project.
        assert principals.create_provider("2")() is None
        principals.set_role("1", CatalogRole.ADMINISTRATOR)
        administrator = provider()
        assert administrator is not None
        assert administrator.role == "administrator"
        principals.set_role("1", None)
        assert provider() is None
        keeper.sign_out()
        principals.set_role("1", CatalogRole.READER)
        assert provider() is None
    finally:
        keeper.close()


# The catalog of GitLab.


def test_002_the_catalog_of_gitlab_is_used_once_the_user_is_signed_in(
    environment: Environment,
) -> None:
    client = _create_client(environment)

    # Before the sign-in: no call to GitLab, an invitation.
    page = client.get("/").text
    assert 'data-testid="catalog-sign-in-required"' in page
    assert 'data-testid="catalog-error"' not in page
    assert environment.fake_gitlab.project_request_count == 0

    environment.sign_in()
    page = client.get("/").text

    assert 'data-testid="catalog-sign-in-required"' not in page
    assert "ISIS" in page
    # A Guest does not see the project.
    assert "Hidden" not in page
    assert 'data-role="reader"' in page


def test_003_the_role_follows_the_access_level_of_gitlab(
    environment: Environment,
) -> None:
    fake_gitlab = environment.fake_gitlab
    environment.sign_in()
    client = _create_client(environment)
    for level_, role_ in (
        (REPORTER, "reader"),
        (DEVELOPER, "author"),
        (MAINTAINER, "administrator"),
    ):
        fake_gitlab.access_levels[1] = level_
        assert f'data-role="{role_}"' in client.get("/").text


def test_004_the_client_of_the_catalog_needs_the_sign_in(
    environment: Environment,
) -> None:
    settings = load_settings(environment.settings_path)
    assert create_catalog_client(settings, environment.keeper) is None

    environment.sign_in()

    assert create_catalog_client(settings, environment.keeper) is not None
    # Another catalog has no GitLab client.
    settings.catalog_provider = "fake"
    assert create_catalog_client(settings, environment.keeper) is None


def test_005_the_certificates_of_the_system_are_used() -> None:
    bundle = get_system_ca_bundle()

    assert bundle is True or Path(str(bundle)).exists()


# The server of a project.


def test_006_the_role_is_read_again_at_each_opening_of_the_project(
    environment: Environment, tmp_path: Path
) -> None:
    environment.sign_in()
    client = _create_client(environment)
    folder = tmp_path / "workspace"
    folder.mkdir()

    environment.open_project(client, folder)
    principal = environment.get_principal()
    assert principal is not None
    assert (principal.user, principal.role) == (USERNAME, "reader")

    # GitLab gives more rights; the project is opened again.
    environment.fake_gitlab.access_levels[1] = DEVELOPER
    response = client.post("/projects/open", data={"identifier": IDENTIFIER})
    assert response.status_code == 303
    assert len(environment.servers) == 1
    principal = environment.get_principal()
    assert principal is not None and principal.role == "author"


def test_007_a_project_that_is_not_visible_any_more_is_not_opened(
    environment: Environment, tmp_path: Path
) -> None:
    environment.sign_in()
    client = _create_client(environment)
    folder = tmp_path / "workspace"
    folder.mkdir()
    environment.open_project(client, folder)
    server = environment.servers[0]
    assert server.is_running

    # The rights are removed.
    del environment.fake_gitlab.access_levels[1]
    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert response.status_code == 200
    assert "You no longer have access to this project." in response.text
    # Its server stops, and would refuse a request that it still got.
    assert not server.is_running
    assert server.principal_provider is not None
    assert server.principal_provider() is None
    assert environment.manager.get_open_identifiers() == set()
    i18n.set_language("fr")
    response = client.post("/projects/open", data={"identifier": IDENTIFIER})
    assert "Vous n&#39;avez plus accès à ce projet." in response.text


def test_008_a_project_that_was_never_opened_is_not_in_the_catalog(
    environment: Environment,
) -> None:
    environment.sign_in()
    client = _create_client(environment)

    response = client.post("/projects/open", data={"identifier": "999"})

    assert "The project is not in the catalog." in response.text


def test_009_without_the_sign_in_the_project_is_not_opened(
    environment: Environment,
) -> None:
    client = _create_client(environment)

    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert "Sign in to see your projects." in response.text
    assert environment.servers == []


def test_010_a_signed_out_user_is_refused_by_the_server_of_the_project(
    environment: Environment, tmp_path: Path
) -> None:
    environment.sign_in()
    client = _create_client(environment)
    folder = tmp_path / "workspace"
    folder.mkdir()
    environment.open_project(client, folder)
    assert environment.get_principal() is not None

    environment.keeper.sign_out()

    assert environment.get_principal() is None


# The real server of a project, in the desktop mode.


@pytest.fixture(name="project_app")
def fixture_project_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "doc.sdoc").write_text(
        "[DOCUMENT]\nTITLE: Doc\n\n[REQUIREMENT]\nUID: REQ-1\n"
        "TITLE: Braking\nSTATEMENT: The system shall brake.\n"
    )
    return project_path


def _get_routes_of_role(role: str) -> List[Tuple[str, str]]:
    """Some routes that need the role, with a path that the route matches."""
    routes = [
        (
            method_,
            re.sub(r"\{[^}]+\}", "x", path_.replace("{full_path:path}", "x/y")),
        )
        for (method_, path_), required_ in ROUTE_ROLES.items()
        if required_ == role and method_ in ("POST", "DELETE")
    ]
    assert len(routes) > 0
    return routes[:5]


class MutableProvider:
    def __init__(self, role: Optional[str]) -> None:
        self.role: Optional[str] = role

    def __call__(self) -> Optional[Principal]:
        if self.role is None:
            return None
        return Principal(user=USERNAME, subject=USERNAME, role=self.role)


def _create_project_client(
    project_path: Path, provider: MutableProvider
) -> TestClient:
    config = create_desktop_project_config(
        input_path=str(project_path), port=None, principal_provider=provider
    )
    application = create_app(project_config=config)
    give_principal_provider(application, provider)
    return TestClient(application, raise_server_exceptions=False)


def test_011_the_server_of_a_project_knows_the_user_and_the_role(
    project_app: Path,
) -> None:
    provider = MutableProvider("reader")
    client = _create_project_client(project_app, provider)

    whoami = client.get("/whoami").json()

    assert whoami["user"] == USERNAME
    assert whoami["role"] == "reader"
    assert whoami["auth_mode"] == "desktop"
    # The rules of the routes are those of the proxy mode: a reader reads.
    assert client.get("/").status_code == 200
    for method_, path_ in _get_routes_of_role("administrator"):
        assert client.request(method_, path_).status_code == 403, path_
    provider.role = "administrator"
    assert client.get("/whoami").json()["role"] == "administrator"


def test_012_the_server_refuses_when_nobody_is_signed_in(
    project_app: Path,
) -> None:
    provider = MutableProvider(None)
    client = _create_project_client(project_app, provider)

    assert client.get("/whoami").status_code == 401
    assert client.get("/").status_code == 401


def test_013_the_websocket_of_the_server_gets_the_role_too(
    project_app: Path,
) -> None:
    provider = MutableProvider("reader")
    client = _create_project_client(project_app, provider)

    with client.websocket_connect("/ws/1"):
        pass
    provider.role = None
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect("/ws/1"):
            pass  # pragma: no cover
    assert refused.value.code == 4401


def test_014_the_provider_must_find_the_principal_middleware() -> None:
    provider = MutableProvider("reader")

    with pytest.raises(LocalServerError, match="no principal middleware"):
        give_principal_provider(Starlette(), provider)


def test_015_the_provider_must_come_before_the_first_request(
    project_app: Path,
) -> None:
    provider = MutableProvider("reader")
    config = create_desktop_project_config(
        input_path=str(project_app), port=None
    )
    application = create_app(project_config=config)
    # The first request builds the stack of the middleware.
    TestClient(application, raise_server_exceptions=False).get("/whoami")

    with pytest.raises(LocalServerError, match="already built"):
        give_principal_provider(application, provider)
