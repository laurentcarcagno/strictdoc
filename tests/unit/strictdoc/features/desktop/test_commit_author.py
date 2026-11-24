"""
@relation(SDOC-SRS-1238, scope=file)
"""

import re
import time
import urllib.request
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import parse_qs, urlparse

import pytest
from git import Actor, Repo
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from strictdoc.features.desktop.commit_author import (
    CommitAuthorError,
    create_author_provider,
    get_commit_author,
    get_commit_email,
)
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
    create_project_application,
    give_author_provider,
)
from strictdoc.features.desktop.oauth_gitlab import (
    GitLabSession,
    GitLabSignIn,
    GitLabTokens,
    GitLabUser,
    fetch_user,
)
from strictdoc.features.desktop.secret_store import MemorySecretStore
from strictdoc.features.desktop.settings import DesktopSettings
from strictdoc.features.desktop.token_store import (
    TokenKeeper,
    parse_session,
    serialize_session,
)
from strictdoc.features.git_config.git_service import Author, GitServiceError
from strictdoc.features.roles.principal import Principal
from strictdoc.server.app import create_app
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    EMAIL,
    USER_ID,
    USERNAME,
    FakeGitLab,
)

GITLAB_URL = "https://gitlab.example.org"


def _create_user(**fields: object) -> GitLabUser:
    values = {
        "username": "jdupont",
        "display_name": "Jeanne Dupont",
        "email": "",
        "user_id": 77,
        **fields,
    }
    return GitLabUser(**values)  # type: ignore[arg-type]


def test_001_the_author_is_the_name_and_the_email_of_the_user() -> None:
    user = _create_user(email="jeanne@example.org")

    assert get_commit_author(user, GITLAB_URL) == Author(
        "Jeanne Dupont", "jeanne@example.org"
    )


def test_002_a_private_email_gives_the_public_email_first() -> None:
    user = _create_user(
        email="", public_email="public@example.org", commit_email="c@x.org"
    )

    assert get_commit_email(user, GITLAB_URL) == "public@example.org"


def test_003_then_the_commit_email() -> None:
    user = _create_user(email="  ", public_email="", commit_email="c@x.org")

    assert get_commit_email(user, GITLAB_URL) == "c@x.org"


def test_004_the_email_of_the_user_comes_before_the_others() -> None:
    user = _create_user(
        email="main@x.org", public_email="p@x.org", commit_email="c@x.org"
    )

    assert get_commit_email(user, GITLAB_URL) == "main@x.org"


def test_005_with_no_address_the_author_has_the_noreply_address_of_gitlab() -> (
    None
):
    user = _create_user()

    assert get_commit_email(user, "https://gitlab.karka.lan/") == (
        "77-jdupont@users.noreply.gitlab.karka.lan"
    )
    # The port is not part of the host name.
    assert get_commit_email(user, "http://localhost:8080") == (
        "77-jdupont@users.noreply.localhost"
    )
    # A record without the number of the user.
    assert get_commit_email(_create_user(user_id=0), GITLAB_URL) == (
        "jdupont@users.noreply.gitlab.example.org"
    )


def _create_session(user: GitLabUser) -> GitLabSession:
    return GitLabSession(
        tokens=GitLabTokens("access", "refresh", time.time() + 7200),
        user=user,
    )


@pytest.fixture(name="keeper")
def fixture_keeper() -> Iterator[TokenKeeper]:
    keeper = TokenKeeper(MemorySecretStore(), use_timer=False)
    yield keeper
    keeper.close()


def test_006_the_author_is_read_at_the_time_of_the_commit(
    keeper: TokenKeeper,
) -> None:
    provider = create_author_provider(keeper)

    # No default author: nobody signed in is an error.
    with pytest.raises(CommitAuthorError, match="Nobody is signed in"):
        provider()

    keeper.adopt(
        gitlab_url=GITLAB_URL,
        client_id="c",
        session=_create_session(_create_user(email="jeanne@example.org")),
    )
    assert provider() == Author("Jeanne Dupont", "jeanne@example.org")

    # Another user signs in: the next commit has the other author.
    keeper.adopt(
        gitlab_url=GITLAB_URL,
        client_id="c",
        session=_create_session(
            _create_user(
                username="pmartin", display_name="Paul Martin", user_id=5
            )
        ),
    )
    assert provider() == Author(
        "Paul Martin", "5-pmartin@users.noreply.gitlab.example.org"
    )

    keeper.sign_out()
    with pytest.raises(GitServiceError):
        provider()


def test_007_the_addresses_are_kept_with_the_tokens() -> None:
    session = _create_session(
        _create_user(
            email="a@x.org", public_email="p@x.org", commit_email="c@x.org"
        )
    )

    assert parse_session(serialize_session(session)) == session


def test_008_a_record_of_before_has_no_address_but_the_email() -> None:
    session = parse_session(
        '{"version": 1, "access_token": "a", "refresh_token": null, '
        '"expires_at": 1.0, "username": "u", "name": "U", "email": "u@x.org"}'
    )

    assert session is not None
    assert session.user == GitLabUser("u", "U", "u@x.org")


def _sign_in(fake_gitlab: FakeGitLab) -> GitLabSession:
    sign_in = GitLabSignIn()
    authorization_url = sign_in.start(
        settings=DesktopSettings(
            gitlab_url=fake_gitlab.url, oauth_client_id=CLIENT_ID
        ),
        port=18084,
    )
    with urllib.request.urlopen(authorization_url, timeout=10) as answer_:
        page = answer_.read().decode("utf-8")
    found = re.search(r'window\.location = "([^"]+)";', page)
    assert found is not None
    query = parse_qs(urlparse(found.group(1)).query)
    return sign_in.complete(state=query["state"][0], code=query["code"][0])


def test_009_gitlab_gives_the_number_and_the_addresses_of_the_user() -> None:
    with FakeGitLab() as fake_gitlab:
        fake_gitlab.user_email = ""
        fake_gitlab.public_email = "public@example.org"
        fake_gitlab.commit_email = "commit@example.org"
        session = _sign_in(fake_gitlab)

        user = fetch_user(fake_gitlab.url, session.tokens.access_token)

        assert (user.username, user.display_name) == (USERNAME, DISPLAY_NAME)
        assert user.user_id == USER_ID
        assert user.email == ""
        assert (user.public_email, user.commit_email) == (
            "public@example.org",
            "commit@example.org",
        )
        assert get_commit_author(user, fake_gitlab.url) == Author(
            DISPLAY_NAME, "public@example.org"
        )
        fake_gitlab.public_email = ""
        fake_gitlab.commit_email = ""
        user = fetch_user(fake_gitlab.url, session.tokens.access_token)
        assert get_commit_email(user, fake_gitlab.url) == (
            f"{USER_ID}-{USERNAME}@users.noreply.localhost"
        )
        fake_gitlab.user_email = EMAIL
        user = fetch_user(fake_gitlab.url, session.tokens.access_token)
        assert get_commit_email(user, fake_gitlab.url) == EMAIL


# The committer of a project server.


def _create_project_application(
    root: Path, monkeypatch: pytest.MonkeyPatch, *, is_git_on: bool
) -> Starlette:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(root / "xdg-cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(root / "xdg-data"))
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    project_path = root / "project"
    project_path.mkdir()
    (project_path / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
    if is_git_on:
        from git import Repo  # noqa: PLC0415

        Repo.init(project_path).close()
        (project_path / "strictdoc_config.py").write_text(
            "from strictdoc.core.project_config import ProjectConfig\n"
            "from strictdoc.features.git_config.config import GitConfig\n"
            "def create_config():\n"
            "    return ProjectConfig(\n"
            '        project_title="P",\n'
            '        project_features=["GIT"],\n'
            "        git=GitConfig(push_on_tag=False),\n"
            "    )\n"
        )
    config = create_desktop_project_config(
        input_path=str(project_path), port=None
    )
    return create_app(project_config=config)


def test_010_the_committer_of_the_project_signs_with_the_given_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = _create_project_application(
        tmp_path, monkeypatch, is_git_on=True
    )
    committer = application.state.project_context.git_committer
    assert committer is not None
    configured_author: Optional[Author] = committer.author_provider()
    author = Author("Jeanne Dupont", "jeanne@example.org")

    give_author_provider(application, lambda: author)

    assert committer.author_provider() == author
    assert committer.author_provider() != configured_author


def test_011_a_project_that_does_not_commit_has_no_committer_to_sign(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = _create_project_application(
        tmp_path, monkeypatch, is_git_on=False
    )
    assert application.state.project_context.git_committer is None

    give_author_provider(
        application, lambda: Author("Jeanne Dupont", "jeanne@example.org")
    )


# The author of GitConfig is never used in the desktop mode.

DEFAULT_AUTHOR_NAME = "Laurent Carcagno"
SEED_ACTOR = Actor("Seed", "seed@example.org")


def _create_desktop_project(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A repository of a project with the feature GIT, with one commit."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(root / "xdg-cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(root / "xdg-data"))
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    project_path = root / "project"
    project_path.mkdir()
    (project_path / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
    (project_path / "strictdoc_config.py").write_text(
        "from strictdoc.core.project_config import ProjectConfig\n"
        "from strictdoc.features.git_config.config import GitConfig\n"
        "def create_config():\n"
        "    return ProjectConfig(\n"
        '        project_title="P",\n'
        '        project_features=["GIT"],\n'
        "        git=GitConfig(push_on_tag=False),\n"
        "    )\n"
    )
    repo = Repo.init(project_path)
    repo.index.add(["doc.sdoc", "strictdoc_config.py"])
    repo.index.commit("Seed", author=SEED_ACTOR, committer=SEED_ACTOR)
    repo.close()
    return project_path


def _create_desktop_application(
    project_path: Path, author_provider: object = None
) -> Starlette:
    config = create_desktop_project_config(
        input_path=str(project_path),
        port=None,
        principal_provider=lambda: Principal(
            user="jdupont", role="administrator"
        ),
    )
    return create_project_application(config, author_provider)  # type: ignore[arg-type]


def _get_commit_authors(project_path: Path) -> list[str]:
    repo = Repo(project_path)
    try:
        return [str(commit_.author.name) for commit_ in repo.iter_commits()]
    finally:
        repo.close()


def _change_document(project_path: Path) -> str:
    path = project_path / "doc.sdoc"
    path.write_text("[DOCUMENT]\nTITLE: Doc changed\n")
    return str(path)


def test_012_a_server_without_the_author_function_commits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_desktop_project(tmp_path, monkeypatch)
    # The injection of the author failed: the application got no function.
    application = _create_desktop_application(project_path, None)
    committer = application.state.project_context.git_committer
    assert committer is not None

    committer.on_document_written(_change_document(project_path))

    assert "no author" in committer.last_error
    # Nothing was committed, and the author of GitConfig was not used.
    assert _get_commit_authors(project_path) == ["Seed"]
    with pytest.raises(CommitAuthorError):
        committer.author_provider()


def test_013_nobody_signed_in_commits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keeper: TokenKeeper
) -> None:
    project_path = _create_desktop_project(tmp_path, monkeypatch)
    application = _create_desktop_application(
        project_path, create_author_provider(keeper)
    )
    committer = application.state.project_context.git_committer
    assert committer is not None

    committer.on_document_written(_change_document(project_path))

    assert "Nobody is signed in" in committer.last_error
    assert _get_commit_authors(project_path) == ["Seed"]


def test_014_the_commit_of_a_server_has_the_signed_in_user_as_author(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, keeper: TokenKeeper
) -> None:
    project_path = _create_desktop_project(tmp_path, monkeypatch)
    keeper.adopt(
        gitlab_url=GITLAB_URL,
        client_id="c",
        session=_create_session(_create_user(email="jeanne@example.org")),
    )
    application = _create_desktop_application(
        project_path, create_author_provider(keeper)
    )
    committer = application.state.project_context.git_committer
    assert committer is not None

    committer.on_document_written(_change_document(project_path))

    assert committer.last_error == ""
    assert _get_commit_authors(project_path) == ["Jeanne Dupont", "Seed"]
    assert DEFAULT_AUTHOR_NAME not in _get_commit_authors(project_path)


def test_015_a_project_with_no_gitlab_user_has_no_author_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A project of the fake catalog, or opened by its path: no principal
    # provider, and no author function either.
    project_path = _create_desktop_project(tmp_path, monkeypatch)
    config = create_desktop_project_config(
        input_path=str(project_path), port=None
    )
    application = create_project_application(config)
    committer = application.state.project_context.git_committer
    assert committer is not None

    committer.on_document_written(_change_document(project_path))

    assert "no author" in committer.last_error
    assert _get_commit_authors(project_path) == ["Seed"]


def test_016_a_tag_and_a_sync_without_an_author_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_desktop_project(tmp_path, monkeypatch)
    application = _create_desktop_application(project_path, None)
    client = TestClient(application, raise_server_exceptions=False)

    tag = client.post(
        "/actions/git/tag", data={"repository": ".", "kind": "draft"}
    )
    sync = client.post("/actions/git/sync")

    for response_ in (tag, sync):
        assert response_.status_code == 409
        assert "no author" in response_.json()["detail"]
    repo = Repo(project_path)
    try:
        assert len(repo.tags) == 0
    finally:
        repo.close()


def test_017_the_error_of_the_author_is_clear_where_nobody_catches_it() -> None:
    def route(request: object) -> PlainTextResponse:
        del request
        raise CommitAuthorError("No author.")

    client = TestClient(Starlette(routes=[Route("/", route)]))

    response = client.get("/")

    assert response.status_code == 409
    assert response.text == "No author."
    error = CommitAuthorError("No author.")
    assert isinstance(error, GitServiceError)
    assert isinstance(error, HTTPException)
    assert str(error) == "No author."
