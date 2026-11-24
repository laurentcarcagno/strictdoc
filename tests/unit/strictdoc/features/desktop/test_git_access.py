"""
The Git commands of the desktop application use the token of the signed-in
user, for the GitLab of the session only, and no other credential. The
tests run the real Git. They use made-up secrets and a home folder of their
own: nothing reads a credential of the computer.

@relation(SDOC-SRS-1239, scope=file)
@relation(SDOC-SRS-1241, scope=file)
"""

import base64
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import pytest
from git import Actor, Repo
from starlette.testclient import TestClient

from strictdoc.features.desktop.git_access import (
    GIT_TOKEN_VARIABLE,
    NO_GITLAB_TOKEN_VARIABLE,
    DesktopGitService,
    GitAccess,
    build_git_environment,
    create_git_access,
    get_credential_origin,
)
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
    create_project_application,
)
from strictdoc.features.desktop.oauth_gitlab import (
    GitLabSession,
    GitLabTokens,
    GitLabUser,
)
from strictdoc.features.desktop.secret_store import MemorySecretStore
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.desktop.workspace import (
    WorkspaceError,
    clone_project,
    pull_project,
)
from strictdoc.features.git_config.git_service import Author, GitServiceError
from strictdoc.features.git_config.gitlab_service import (
    GitLabService,
    GitLabServiceError,
)
from strictdoc.features.git_config.setup import ensure_remote_repository
from strictdoc.features.roles.principal import Principal
from tests.unit.strictdoc.features.desktop.git_http_server import (
    GitHttpServer,
)

TOKEN = "made-up-token-of-the-user"
MACHINE_SECRET = "made-up-secret-of-the-computer"
HOST_SECRET = "made-up-secret-of-one-host"
GITLAB_URL = "https://gitlab.example.org"
ACTOR = Actor("Seed", "seed@example.org")
AUTHOR = Author("Jeanne Dupont", "jeanne@example.org")


@dataclass
class Machine:
    """A computer whose Git is set up to store credentials, in a folder."""

    home: Path

    @property
    def store_path(self) -> Path:
        return self.home / ".git-credentials"

    def read_store(self) -> bytes:
        return self.store_path.read_bytes() if self.store_path.exists() else b""

    def write_store(self, *lines: str) -> None:
        self.store_path.write_text("".join(f"{line_}\n" for line_ in lines))

    def add_configuration(self, text: str) -> None:
        with open(self.home / ".gitconfig", "a", encoding="utf8") as file_:
            file_.write(text)


@pytest.fixture(name="machine")
def fixture_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Machine]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / "xdg"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / ".gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # The files that the application writes for Git go in the folder of the
    # test, not in the data folder of the user.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "xdg-data"))
    for name_ in (
        "GIT_CONFIG_COUNT",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_ALLOW_PROTOCOL",
        "GITLAB_TOKEN",
        GIT_TOKEN_VARIABLE,
    ):
        monkeypatch.delenv(name_, raising=False)
    (home / ".gitconfig").write_text("[credential]\n\thelper = store\n")
    yield Machine(home)


@pytest.fixture(name="server_factory")
def fixture_server_factory(tmp_path: Path) -> Iterator["ServerFactory"]:
    factory = ServerFactory(tmp_path)
    yield factory
    factory.stop_all()


class ServerFactory:
    def __init__(self, tmp_path: Path) -> None:
        self._tmp_path: Path = tmp_path
        self._servers: List[GitHttpServer] = []

    def create(self, name: str) -> GitHttpServer:
        repositories = self._tmp_path / f"served-{name}"
        repositories.mkdir()
        server = GitHttpServer(repositories, "oauth2", TOKEN)
        server.start()
        self._servers.append(server)
        return server

    def stop_all(self) -> None:
        for server_ in self._servers:
            server_.stop()


def _create_access(url: str, token: Optional[str] = TOKEN) -> GitAccess:
    return GitAccess(get_gitlab_url=lambda: url, get_access_token=lambda: token)


def _run_git(folder: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout.strip()


def _publish_repository(
    server: GitHttpServer, name: str, work_path: Path
) -> str:
    """Make the repository of a working folder the bare one of the server."""
    Repo.clone_from(
        str(work_path), str(server.repositories / f"{name}.git"), bare=True
    ).close()
    return f"{server.url}/{name}.git"


def _create_work_repository(path: Path, text: str = "one") -> Repo:
    path.mkdir()
    (path / "doc.sdoc").write_text(f"[DOCUMENT]\nTITLE: {text}\n")
    repo = Repo.init(path, initial_branch="main")
    repo.index.add(["doc.sdoc"])
    repo.index.commit("Seed", author=ACTOR, committer=ACTOR)
    return repo


def _create_remote_project(
    server: GitHttpServer, tmp_path: Path, name: str = "project"
) -> str:
    work_repo = _create_work_repository(tmp_path / f"work-{name}")
    work_repo.close()
    return _publish_repository(server, name, tmp_path / f"work-{name}")


def _store_line(url: str, secret: str) -> str:
    """The line of the store of Git for the server, with a made-up secret."""
    authority = url.split("://", 1)[1]
    return f"{url.split('://', maxsplit=1)[0]}://oauth2:{secret}@{authority}"


def _run_credential(
    operation: str,
    fields: str,
    environment: Dict[str, str],
    folder: Path,
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        ["git", "credential", operation],
        input=fields,
        env={**os.environ, **environment},
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


GITLAB_FIELDS = "protocol=https\nhost=gitlab.example.org\n\n"


# The environment of a Git command.


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://gitlab.example.org", "https://gitlab.example.org"),
        ("https://GitLab.Example.org/", "https://gitlab.example.org"),
        ("https://gitlab.example.org:443/x", "https://gitlab.example.org"),
        ("https://gitlab.example.org:8443", "https://gitlab.example.org:8443"),
        ("http://127.0.0.1:5000/api", "http://127.0.0.1:5000"),
        ("http://gitlab.example.org:80", "http://gitlab.example.org"),
        ("https://[::1]:8443", "https://[::1]:8443"),
        ("ssh://git@gitlab.example.org", None),
        ("file:///data/remote.git", None),
        ("https://*.example.org", None),
        ("gitlab.example.org", None),
        ("", None),
    ],
)
def test_001_the_origin_has_the_scheme_the_host_and_the_port(
    url: str, expected: Optional[str]
) -> None:
    assert get_credential_origin(url) == expected


def _get_entries(environment: Dict[str, str]) -> List[Tuple[str, str]]:
    """The entries of the configuration that the environment gives to Git."""
    count = int(environment["GIT_CONFIG_COUNT"])
    return [
        (
            environment[f"GIT_CONFIG_KEY_{index_}"],
            environment[f"GIT_CONFIG_VALUE_{index_}"],
        )
        for index_ in range(count)
    ]


def test_002_the_helpers_are_cleared_before_the_helper_of_the_token() -> None:
    environment = build_git_environment(
        "https://gitlab.example.org:8443", TOKEN
    )

    entries = _get_entries(environment)
    assert entries[0] == ("credential.helper", "")
    assert entries[1][0] == "credential.https://gitlab.example.org:8443.helper"
    # The headers are reset, and Git stops at an address with a password.
    assert ("http.extraHeader", "") in entries[2:]
    assert ("transfer.credentialsInUrl", "die") in entries[2:]
    # The helper reads the token when Git runs it: the value of the
    # configuration holds the name of the variable, not the token.
    assert environment[GIT_TOKEN_VARIABLE] == TOKEN
    assert TOKEN not in entries[1][1]
    assert GIT_TOKEN_VARIABLE in entries[1][1]
    assert [
        name_ for name_, value_ in environment.items() if TOKEN in value_
    ] == [GIT_TOKEN_VARIABLE]


def test_003_git_never_asks_the_user() -> None:
    environment = build_git_environment(GITLAB_URL, TOKEN)

    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_ASKPASS"] == ""
    assert environment["SSH_ASKPASS"] == ""
    assert environment["GCM_INTERACTIVE"] == "never"
    # The limit of the network does not rest on the kill of a process.
    assert environment["GIT_HTTP_LOW_SPEED_TIME"] == "30"


@pytest.mark.parametrize(
    ("url", "token"),
    [
        (GITLAB_URL, None),
        ("", TOKEN),
        ("ssh://gitlab.example.org", TOKEN),
        (GITLAB_URL, "token\nusername=attacker"),
        (GITLAB_URL, ""),
    ],
)
def test_004_without_a_good_session_the_helpers_are_cleared_and_none_is_added(
    url: str, token: Optional[str]
) -> None:
    environment = build_git_environment(url, token)

    entries = _get_entries(environment)
    assert entries[0] == ("credential.helper", "")
    assert not any(
        key_.startswith("credential.") and key_ != "credential.helper"
        for key_, _ in entries
    )
    assert GIT_TOKEN_VARIABLE not in environment


@pytest.fixture(name="keeper")
def fixture_keeper() -> Iterator[TokenKeeper]:
    keeper = TokenKeeper(MemorySecretStore(), use_timer=False)
    yield keeper
    keeper.close()


def test_005_the_access_of_the_keeper_follows_the_session(
    keeper: TokenKeeper,
) -> None:
    access = create_git_access(keeper)
    assert GIT_TOKEN_VARIABLE not in access.build_environment()

    keeper.adopt(
        gitlab_url=GITLAB_URL,
        client_id="client",
        session=GitLabSession(
            tokens=GitLabTokens(TOKEN, "refresh", time.time() + 7200),
            user=GitLabUser(
                username="jdupont", display_name="Jeanne", email="", user_id=1
            ),
        ),
    )
    environment = access.build_environment()
    assert environment[GIT_TOKEN_VARIABLE] == TOKEN
    assert environment["GIT_CONFIG_KEY_1"] == (
        "credential.https://gitlab.example.org.helper"
    )

    keeper.sign_out()
    assert GIT_TOKEN_VARIABLE not in access.build_environment()


# What Git does with the environment: the real "git credential".


def test_006_the_token_wins_over_the_identifier_of_the_computer(
    machine: Machine, tmp_path: Path
) -> None:
    machine.write_store(_store_line(GITLAB_URL, MACHINE_SECRET))
    store_before = machine.read_store()
    environment = build_git_environment(GITLAB_URL, TOKEN)

    filled = _run_credential("fill", GITLAB_FIELDS, environment, tmp_path)

    assert filled.returncode == 0, filled.stderr
    assert f"password={TOKEN}" in filled.stdout
    assert MACHINE_SECRET not in filled.stdout
    # Git approves a credential that worked: nothing keeps the token.
    approved = _run_credential("approve", filled.stdout, environment, tmp_path)
    assert approved.returncode == 0, approved.stderr
    assert machine.read_store() == store_before
    assert TOKEN not in machine.read_store().decode("utf8")
    assert not (machine.home / "xdg" / "git" / "credentials").exists()


def test_007_the_store_of_the_computer_never_keeps_the_token(
    machine: Machine, tmp_path: Path
) -> None:
    # The store is empty: the old way wrote the token there after a success.
    environment = build_git_environment(GITLAB_URL, TOKEN)
    filled = _run_credential("fill", GITLAB_FIELDS, environment, tmp_path)

    _run_credential("approve", filled.stdout, environment, tmp_path)

    assert machine.read_store() == b""
    assert not (machine.home / "xdg" / "git" / "credentials").exists()


def test_008_a_helper_of_the_host_in_the_global_file_gets_nothing(
    machine: Machine, tmp_path: Path
) -> None:
    log_path = tmp_path / "helper-log"
    machine.add_configuration(
        '[credential "https://gitlab.example.org"]\n'
        f'\thelper = "!f() {{ cat >> {log_path}; '
        f'echo username=host; echo password={HOST_SECRET}; }}; f"\n'
    )
    environment = build_git_environment(GITLAB_URL, TOKEN)

    filled = _run_credential("fill", GITLAB_FIELDS, environment, tmp_path)
    _run_credential("approve", filled.stdout, environment, tmp_path)

    assert f"password={TOKEN}" in filled.stdout
    assert HOST_SECRET not in filled.stdout
    assert not log_path.exists()


def test_009_a_helper_of_the_cloned_repository_gets_nothing(
    machine: Machine, tmp_path: Path
) -> None:
    del machine
    repository = tmp_path / "clone"
    repository.mkdir()
    _run_git(repository, "init", "-q")
    log_path = tmp_path / "helper-log"
    for key_ in (
        "credential.helper",
        "credential.https://gitlab.example.org.helper",
    ):
        _run_git(
            repository,
            "config",
            key_,
            f"!f() {{ cat >> {log_path}; echo username=repo; "
            f"echo password={HOST_SECRET}; }}; f",
        )
    environment = build_git_environment(GITLAB_URL, TOKEN)

    filled = _run_credential("fill", GITLAB_FIELDS, environment, repository)
    _run_credential("approve", filled.stdout, environment, repository)

    assert f"password={TOKEN}" in filled.stdout
    assert HOST_SECRET not in filled.stdout
    assert not log_path.exists()


@pytest.mark.parametrize(
    "fields",
    [
        "protocol=https\nhost=other.example.org\n\n",
        "protocol=https\nhost=gitlab.example.org:8443\n\n",
        "protocol=http\nhost=gitlab.example.org\n\n",
        "protocol=https\nhost=gitlab.example.org.evil.org\n\n",
        "protocol=https\nhost=evil.org\npath=gitlab.example.org/x.git\n\n",
    ],
)
def test_010_another_origin_gets_no_token_and_no_identifier(
    machine: Machine, tmp_path: Path, fields: str
) -> None:
    machine.write_store(
        f"https://oauth2:{MACHINE_SECRET}@other.example.org",
        f"https://oauth2:{MACHINE_SECRET}@evil.org",
    )
    environment = build_git_environment(GITLAB_URL, TOKEN)

    filled = _run_credential("fill", fields, environment, tmp_path)

    assert filled.returncode != 0
    assert TOKEN not in filled.stdout + filled.stderr
    assert MACHINE_SECRET not in filled.stdout + filled.stderr
    assert "password" not in filled.stdout


def test_011_without_a_session_no_credential_is_given(
    machine: Machine, tmp_path: Path
) -> None:
    machine.write_store(_store_line(GITLAB_URL, MACHINE_SECRET))
    environment = build_git_environment(GITLAB_URL, None)

    filled = _run_credential("fill", GITLAB_FIELDS, environment, tmp_path)

    assert filled.returncode != 0
    assert "password" not in filled.stdout
    assert MACHINE_SECRET not in filled.stdout + filled.stderr


# The commands of the application, against a server that asks for the token.


def test_012_the_clone_of_a_private_project_uses_the_token_only(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    machine.write_store(_store_line(server.url, MACHINE_SECRET))
    store_before = machine.read_store()
    folder = tmp_path / "workspace"

    clone_project(url, str(folder), git_access=_create_access(server.url))

    assert (folder / "doc.sdoc").is_file()
    assert server.seen_credentials == {f"oauth2:{TOKEN}"}
    assert machine.read_store() == store_before
    # No secret stays in the repository.
    configuration = (folder / ".git" / "config").read_text(encoding="utf8")
    assert TOKEN not in configuration
    assert MACHINE_SECRET not in configuration
    assert "oauth2" not in configuration


def test_013_the_clone_without_a_session_does_not_use_the_computer(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    # The store of the computer holds the good credential: the clone must not
    # find it.
    machine.write_store(_store_line(server.url, TOKEN))
    folder = tmp_path / "workspace"

    with pytest.raises(WorkspaceError):
        clone_project(url, str(folder))
    with pytest.raises(WorkspaceError):
        clone_project(
            url, str(folder), git_access=_create_access(server.url, None)
        )

    assert server.seen_credentials == set()
    assert not folder.exists()


def test_014_the_update_uses_the_token_and_the_update_without_it_fails(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    folder = tmp_path / "workspace"
    access = _create_access(server.url)
    clone_project(url, str(folder), git_access=access)
    work_repo = Repo(tmp_path / "work-project")
    (tmp_path / "work-project" / "doc.sdoc").write_text(
        "[DOCUMENT]\nTITLE: 2\n"
    )
    work_repo.index.add(["doc.sdoc"])
    work_repo.index.commit("Change", author=ACTOR, committer=ACTOR)
    work_repo.git.push(str(server.repositories / "project.git"), "main")
    work_repo.close()
    machine.write_store(_store_line(server.url, TOKEN))
    server.seen_credentials.clear()

    with pytest.raises(WorkspaceError):
        pull_project(str(folder))
    assert server.seen_credentials == set()

    assert pull_project(str(folder), git_access=access) is True
    assert server.seen_credentials == {f"oauth2:{TOKEN}"}
    assert "TITLE: 2" in (folder / "doc.sdoc").read_text()


def test_015_fetch_push_and_tag_of_the_service_use_the_token_only(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    machine.write_store(_store_line(server.url, MACHINE_SECRET))
    store_before = machine.read_store()
    folder = tmp_path / "workspace"
    access = _create_access(server.url)
    clone_project(url, str(folder), git_access=access)
    service = DesktopGitService(str(folder), access)
    (folder / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Changed\n")

    assert service.commit_paths([str(folder / "doc.sdoc")], "Change", AUTHOR)
    service.fetch(str(folder))
    service.create_tag(str(folder), "v1", AUTHOR)
    service.push(str(folder), tag="v1")
    assert service.push_tags(str(folder)) == ""

    bare = Repo(server.repositories / "project.git")
    assert bare.head.commit.author.name == "Jeanne Dupont"
    assert "v1" in [tag_.name for tag_ in bare.tags]
    bare.close()
    assert server.seen_credentials == {f"oauth2:{TOKEN}"}
    assert machine.read_store() == store_before


def test_016_a_submodule_of_another_origin_gets_no_token(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    del machine
    session_server = server_factory.create("session")
    other_server = server_factory.create("other")
    submodule_work = _create_work_repository(tmp_path / "work-sub", "sub")
    submodule_sha = submodule_work.head.commit.hexsha
    submodule_work.close()
    _publish_repository(other_server, "sub", tmp_path / "work-sub")
    url = _create_project_with_submodule(
        session_server, tmp_path, f"{other_server.url}/sub.git", submodule_sha
    )
    folder = tmp_path / "workspace"
    access = _create_access(session_server.url)
    clone_project(url, str(folder), git_access=access)

    with pytest.raises(GitServiceError):
        DesktopGitService(str(folder), access).submodule_update(str(folder))

    assert other_server.seen_credentials == set()
    assert other_server.unauthenticated_request_count > 0
    assert session_server.seen_credentials == {f"oauth2:{TOKEN}"}


def test_017_a_submodule_of_the_session_origin_gets_the_token(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    del machine
    server = server_factory.create("session")
    submodule_work = _create_work_repository(tmp_path / "work-sub", "sub")
    submodule_sha = submodule_work.head.commit.hexsha
    submodule_work.close()
    _publish_repository(server, "sub", tmp_path / "work-sub")
    url = _create_project_with_submodule(
        server, tmp_path, f"{server.url}/sub.git", submodule_sha
    )
    folder = tmp_path / "workspace"
    access = _create_access(server.url)
    clone_project(url, str(folder), git_access=access)

    DesktopGitService(str(folder), access).submodule_update(str(folder))

    assert (folder / "sub" / "doc.sdoc").is_file()
    assert server.seen_credentials == {f"oauth2:{TOKEN}"}


def _create_project_with_submodule(
    server: GitHttpServer, tmp_path: Path, submodule_url: str, sha: str
) -> str:
    work_path = tmp_path / "work-project"
    work_repo = _create_work_repository(work_path)
    (work_path / ".gitmodules").write_text(
        f'[submodule "sub"]\n\tpath = sub\n\turl = {submodule_url}\n'
    )
    work_repo.git.update_index("--add", "--cacheinfo", f"160000,{sha},sub")
    work_repo.index.add([".gitmodules"])
    work_repo.index.commit("Add the submodule", author=ACTOR, committer=ACTOR)
    work_repo.close()
    return _publish_repository(server, "project", work_path)


def test_018_a_remote_that_does_not_answer_ends_the_update(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    del machine
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    folder = tmp_path / "workspace"
    clone_project(url, str(folder), git_access=_create_access(server.url))
    # A server that takes the connection and never answers.
    silent_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    silent_socket.bind(("127.0.0.1", 0))
    silent_socket.listen(5)
    try:
        silent_url = f"http://127.0.0.1:{silent_socket.getsockname()[1]}"
        repo = Repo(folder)
        repo.git.remote("set-url", "origin", f"{silent_url}/project.git")
        repo.close()
        access = GitAccess(
            get_gitlab_url=lambda: silent_url,
            get_access_token=lambda: TOKEN,
            network_timeout_seconds=1,
        )
        start = time.monotonic()

        with pytest.raises(WorkspaceError):
            pull_project(str(folder), timeout_seconds=1, git_access=access)

        assert time.monotonic() - start < 20
    finally:
        silent_socket.close()


# The routes of the project do not create anything on GitLab.


class _RecordingGitLab:
    """A server that answers 404 to everything and notes the requests."""

    def __init__(self) -> None:
        self.requests: List[str] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                owner.requests.append(
                    f"{self.command} {self.path} "
                    f"{self.headers.get('PRIVATE-TOKEN', '')}"
                )
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "20")
                self.end_headers()
                self.wfile.write(b'{"message":"404 Nope"}')

            do_GET = _answer  # noqa: N815
            do_POST = _answer  # noqa: N815

            def log_message(
                self,
                format: str,  # noqa: A002
                *args: object,
            ) -> None:
                del format, args

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def _create_desktop_project(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    configuration: str = "",
    remote_url: Optional[str] = None,
) -> Path:
    monkeypatch.setenv("XDG_CACHE_HOME", str(root / "xdg-cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(root / "xdg-data"))
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    project_path = root / "project"
    work_repo = _create_work_repository(project_path)
    if configuration != "":
        (project_path / "strictdoc_config.py").write_text(configuration)
        work_repo.index.add(["strictdoc_config.py"])
        work_repo.index.commit("Configure", author=ACTOR, committer=ACTOR)
    if remote_url is not None:
        work_repo.create_remote("origin", remote_url)
    work_repo.close()
    return project_path


def test_019_the_application_sends_no_token_to_the_gitlab_of_the_project(
    machine: Machine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del machine
    gitlab = _RecordingGitLab()
    try:
        monkeypatch.setenv("GITLAB_TOKEN", TOKEN)
        project_path = _create_desktop_project(
            tmp_path,
            monkeypatch,
            configuration=(
                "from strictdoc.core.project_config import ProjectConfig\n"
                "from strictdoc.features.git_config.config import GitConfig\n"
                "def create_config():\n"
                "    return ProjectConfig(\n"
                '        project_title="P",\n'
                '        project_features=["GIT"],\n'
                f'        git=GitConfig(gitlab_url="{gitlab.url}",\n'
                "                      push_on_tag=False),\n"
                "    )\n"
            ),
            remote_url=f"{gitlab.url}/team/project.git",
        )
        config = create_desktop_project_config(
            input_path=str(project_path), port=None
        )
        application = create_project_application(
            config, lambda: AUTHOR, _create_access(gitlab.url)
        )
        context = application.state.project_context
        committer = context.git_committer
        assert committer is not None
        assert isinstance(committer.service, DesktopGitService)
        git_configuration = context.project_config.git

        # The synchronization and the push call this function: it would look
        # for the repository of the project on GitLab and create it.
        problem = ensure_remote_repository(
            committer.service, str(project_path), git_configuration
        )
        with pytest.raises(GitLabServiceError):
            GitLabService(git_configuration).create_repository(
                "team", "another"
            )

        assert problem == ""
        assert gitlab.requests == []
    finally:
        gitlab.stop()


def test_020_a_project_without_the_feature_git_commits_a_save(
    machine: Machine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del machine
    project_path = _create_desktop_project(tmp_path, monkeypatch)
    config = create_desktop_project_config(
        input_path=str(project_path), port=None
    )
    # The feature is on for the application, whatever the project says.
    assert config.is_activated_git() is True

    application = create_project_application(config, lambda: AUTHOR)
    committer = application.state.project_context.git_committer
    assert committer is not None
    path = project_path / "doc.sdoc"
    path.write_text("[DOCUMENT]\nTITLE: Saved\n")
    committer.on_document_written(str(path))

    assert committer.last_error == ""
    repo = Repo(project_path)
    assert repo.head.commit.author.name == "Jeanne Dupont"
    assert repo.head.commit.committer.name == "Jeanne Dupont"
    repo.close()


def test_021_a_project_outside_of_a_repository_has_no_committer(
    machine: Machine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del machine
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    project_path = tmp_path / "project"
    project_path.mkdir()
    (project_path / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
    config = create_desktop_project_config(
        input_path=str(project_path), port=None
    )

    application = create_project_application(config, lambda: AUTHOR)

    assert application.state.project_context.git_committer is None


# The commands of the application ignore the personal setup of the computer.


def _clone_with_session(
    server: GitHttpServer, tmp_path: Path, name: str = "workspace"
) -> Path:
    """A clone of the project of the server, made with the token."""
    url = _create_remote_project(server, tmp_path)
    folder = tmp_path / name
    clone_project(url, str(folder), git_access=_create_access(server.url))
    return folder


def _get_address_with_credentials(server: GitHttpServer, user: str) -> str:
    authority = server.url.split("://", 1)[1]
    return f"http://{user}@{authority}/project.git"


def _forget_requests(server: GitHttpServer) -> None:
    server.seen_credentials.clear()
    server.unauthenticated_request_count = 0


def test_022_the_netrc_of_the_computer_is_not_read(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    (machine.home / ".netrc").write_text(
        f"machine 127.0.0.1 login machine password {MACHINE_SECRET}\n"
    )

    clone_project(
        url, str(tmp_path / "workspace"), git_access=_create_access(server.url)
    )

    assert server.seen_credentials == {f"oauth2:{TOKEN}"}


@pytest.mark.parametrize(
    "user", [f"machine:{MACHINE_SECRET}", "machine"], ids=["password", "name"]
)
def test_023_an_address_with_credentials_is_refused_before_any_request(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
    user: str,
) -> None:
    del machine
    server = server_factory.create("a")
    _create_remote_project(server, tmp_path)
    folder = tmp_path / "workspace"

    with pytest.raises(WorkspaceError) as exception_info:
        clone_project(
            _get_address_with_credentials(server, user),
            str(folder),
            git_access=_create_access(server.url),
        )

    assert MACHINE_SECRET not in str(exception_info.value)
    assert server.seen_credentials == set()
    assert server.unauthenticated_request_count == 0
    assert not folder.exists()


def _set_local_address(folder: Path, kind: str, server: GitHttpServer) -> None:
    """Make the repository of a folder reach the server with credentials."""
    authority = server.url.split("://", 1)[1]
    with_credentials = f"http://machine:{MACHINE_SECRET}@{authority}/"
    if kind == "url":
        _run_git(
            folder, "remote", "set-url", "origin", with_credentials + "p.git"
        )
    elif kind == "push-url":
        _run_git(
            folder, "remote", "set-url", "--push", "origin", with_credentials
        )
    else:
        _run_git(
            folder,
            "config",
            f"url.{with_credentials}.insteadOf",
            f"{server.url}/",
        )


@pytest.mark.parametrize("kind", ["url", "push-url", "instead-of"])
def test_024_a_folder_whose_remote_holds_credentials_is_not_used(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
    kind: str,
) -> None:
    del machine
    server = server_factory.create("a")
    folder = _clone_with_session(server, tmp_path)
    _set_local_address(folder, kind, server)
    _forget_requests(server)
    access = _create_access(server.url)
    service = DesktopGitService(str(folder), access)

    with pytest.raises(WorkspaceError) as update_info:
        pull_project(str(folder), git_access=access)
    with pytest.raises(GitServiceError) as fetch_info:
        service.fetch(str(folder))
    with pytest.raises(GitServiceError) as push_info:
        service.push(str(folder))

    for info_ in (update_info, fetch_info, push_info):
        assert MACHINE_SECRET not in str(info_.value)
    assert server.seen_credentials == set()
    assert server.unauthenticated_request_count == 0


def test_025_an_instead_of_of_the_global_file_is_not_applied(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    authority = server.url.split("://", 1)[1]
    machine.add_configuration(
        f'[url "http://machine:{MACHINE_SECRET}@{authority}/"]\n'
        f"\tinsteadOf = {server.url}/\n"
    )

    clone_project(
        url, str(tmp_path / "workspace"), git_access=_create_access(server.url)
    )

    assert server.seen_credentials == {f"oauth2:{TOKEN}"}


@pytest.mark.parametrize(
    "is_per_url", [False, True], ids=["general", "per-url"]
)
def test_026_a_header_of_the_global_file_is_not_sent(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
    is_per_url: bool,
) -> None:
    server = server_factory.create("a")
    url = _create_remote_project(server, tmp_path)
    header = "Authorization: Basic " + base64.b64encode(
        f"machine:{MACHINE_SECRET}".encode()
    ).decode("ascii")
    section = f'[http "{server.url}"]' if is_per_url else "[http]"
    machine.add_configuration(f"{section}\n\textraHeader = {header}\n")

    clone_project(
        url, str(tmp_path / "workspace"), git_access=_create_access(server.url)
    )

    assert server.seen_credentials == {f"oauth2:{TOKEN}"}


def test_027_a_header_of_the_repository_is_reset_or_refused(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    del machine
    server = server_factory.create("a")
    folder = _clone_with_session(server, tmp_path)
    access = _create_access(server.url)
    header = "Authorization: Basic " + base64.b64encode(
        f"machine:{MACHINE_SECRET}".encode()
    ).decode("ascii")

    # A header for every address: reset, the update goes on with the token.
    _run_git(folder, "config", "http.extraHeader", header)
    _forget_requests(server)
    assert pull_project(str(folder), git_access=access) is False
    assert server.seen_credentials == {f"oauth2:{TOKEN}"}

    # A header for one address: refused, nothing is sent.
    _run_git(folder, "config", "--unset-all", "http.extraHeader")
    _run_git(folder, "config", f"http.{server.url}.extraHeader", header)
    _forget_requests(server)
    with pytest.raises(WorkspaceError) as exception_info:
        pull_project(str(folder), git_access=access)
    with pytest.raises(GitServiceError):
        DesktopGitService(str(folder), access).fetch(str(folder))
    assert MACHINE_SECRET not in str(exception_info.value)
    assert server.seen_credentials == set()
    assert server.unauthenticated_request_count == 0


def test_028_a_signing_key_or_a_hook_of_the_user_does_not_stop_a_save(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    server = server_factory.create("a")
    folder = _clone_with_session(server, tmp_path)
    hooks = tmp_path / "global-hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    machine.add_configuration(
        "[commit]\n\tgpgsign = true\n"
        "[gpg]\n\tprogram = /nonexistent/gpg\n"
        f"[core]\n\thooksPath = {hooks}\n"
    )
    service = DesktopGitService(str(folder), _create_access(server.url))
    (folder / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Saved\n")

    assert service.commit_paths([str(folder / "doc.sdoc")], "Save", AUTHOR)

    repo = Repo(folder)
    assert repo.head.commit.author.name == "Jeanne Dupont"
    repo.close()


def test_029_a_local_command_does_not_get_the_token(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
) -> None:
    del machine
    server = server_factory.create("a")
    folder = _clone_with_session(server, tmp_path)
    dump = tmp_path / "hook-environment"
    hook = folder / ".git" / "hooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\nenv > {dump}\n")
    hook.chmod(0o755)
    service = DesktopGitService(str(folder), _create_access(server.url))
    (folder / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Saved\n")

    assert service.commit_paths([str(folder / "doc.sdoc")], "Save", AUTHOR)

    assert dump.exists()
    assert TOKEN not in dump.read_text()


@pytest.mark.parametrize(
    "remote",
    [
        "ssh://git@127.0.0.1:2222/team/project.git",
        "git@127.0.0.1:team/project.git",
        "git://127.0.0.1:1/team/project.git",
        "ext::sh -c 'touch {marker}'",
    ],
    ids=["ssh", "scp", "git", "ext"],
)
def test_030_only_https_http_and_file_are_allowed(
    machine: Machine,
    server_factory: "ServerFactory",
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    remote: str,
) -> None:
    del machine
    marker = tmp_path / "program-ran"
    sentinel = tmp_path / "ssh-sentinel"
    sentinel.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
    sentinel.chmod(0o755)
    monkeypatch.setenv("GIT_SSH_COMMAND", str(sentinel))
    server = server_factory.create("a")
    folder = _clone_with_session(server, tmp_path)
    _run_git(
        folder, "remote", "set-url", "origin", remote.format(marker=marker)
    )
    access = _create_access(server.url)

    with pytest.raises(WorkspaceError):
        pull_project(str(folder), git_access=access)
    with pytest.raises(GitServiceError):
        DesktopGitService(str(folder), access).fetch(str(folder))
    if "ext::" not in remote:
        with pytest.raises(WorkspaceError):
            clone_project(remote, str(tmp_path / "other"), git_access=access)

    assert not marker.exists()


def _create_config_project(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    configuration: str = "",
) -> Path:
    project_path = _create_desktop_project(
        root, monkeypatch, configuration=configuration
    )
    return project_path


@pytest.mark.parametrize(
    "configuration",
    [
        "",
        (
            "from strictdoc.core.project_config import ProjectConfig\n"
            "def create_config():\n"
            "    return ProjectConfig(project_title='P')\n"
        ),
        (
            "from strictdoc.core.project_config import ProjectConfig\n"
            "from strictdoc.features.git_config.config import GitConfig\n"
            "def create_config():\n"
            "    return ProjectConfig(\n"
            "        project_title='P',\n"
            "        project_features=['GIT'],\n"
            "        git=GitConfig(token_env='MY_GITLAB_TOKEN'),\n"
            "    )\n"
        ),
    ],
    ids=["no-file", "no-feature", "own-token-variable"],
)
def test_031_the_git_feature_is_on_for_every_project_of_the_application(
    machine: Machine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    configuration: str,
) -> None:
    del machine
    project_path = _create_config_project(tmp_path, monkeypatch, configuration)

    config = create_desktop_project_config(
        input_path=str(project_path),
        port=None,
        principal_provider=lambda: Principal(
            user="jdupont", role="administrator"
        ),
    )

    assert config.is_activated_git()
    assert config.git is not None
    assert config.git.token_env == NO_GITLAB_TOKEN_VARIABLE
    application = create_project_application(config, lambda: AUTHOR)
    response = TestClient(application).get("/actions/git/sync_dialog")
    assert response.status_code == 200, response.text[:200]


def _get_helper_script(environment: Dict[str, str]) -> str:
    return environment["GIT_CONFIG_VALUE_1"].removeprefix("!")


@pytest.mark.parametrize("operation", ["store", "erase"])
def test_032_the_helper_answers_to_get_only(
    operation: str, tmp_path: Path
) -> None:
    environment = build_git_environment(GITLAB_URL, TOKEN)
    script = _get_helper_script(environment)
    process_environment = {**os.environ, **environment}

    stored = subprocess.run(
        ["sh", "-c", f"{script} {operation}"],
        input="protocol=https\nhost=gitlab.example.org\n\n",
        env=process_environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    got = subprocess.run(
        ["sh", "-c", f"{script} get"],
        input="protocol=https\nhost=gitlab.example.org\n\n",
        env=process_environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert stored.stdout == ""
    assert stored.returncode == 0
    assert got.stdout == f"username=oauth2\npassword={TOKEN}\n"


def _get_configuration(
    environment: Dict[str, str], folder: Path, *arguments: str
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        ["git", "config", *arguments],
        env={**os.environ, **environment},
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_033_the_settings_of_the_network_of_the_user_are_kept(
    machine: Machine, tmp_path: Path
) -> None:
    machine.add_configuration(
        "[http]\n"
        "\tproxy = http://proxy.example.org:3128\n"
        "\tnoProxy = internal.example.org\n"
        "\tsslCAInfo = /etc/company/ca.pem\n"
        "\tsslCAPath = /etc/company/cas\n"
        "\tsslBackend = schannel\n"
        "\tschannelCheckRevoke = false\n"
        "\tschannelUseSSLCAInfo = true\n"
        '[http "https://gitlab.example.org"]\n'
        "\tproxy = http://gitlab-proxy.example.org:8080\n"
        "\tsslCAInfo = /etc/company/gitlab-ca.pem\n"
        "\tnoProxy = gitlab.example.org\n"
        "\tsslCAPath = /etc/company/gitlab-cas\n"
        "\tsslBackend = openssl\n"
        "\tschannelCheckRevoke = true\n"
        "\tschannelUseSSLCAInfo = false\n"
        # What must not be kept.
        "\textraHeader = X-Machine: yes\n"
        "\tcookieFile = /home/user/cookies\n"
        "\tsslVerify = false\n"
        "[core]\n\tsshCommand = ssh -i /home/user/key\n"
        "[user]\n\tname = Machine\n"
    )
    environment = GitAccess().build_environment()
    url = "https://gitlab.example.org/team/project.git"

    def get(*arguments: str) -> str:
        result = _get_configuration(environment, tmp_path, *arguments)
        return result.stdout.strip()

    assert get("--get", "http.proxy") == "http://proxy.example.org:3128"
    assert get("--get", "http.noproxy") == "internal.example.org"
    assert get("--get", "http.sslcainfo") == "/etc/company/ca.pem"
    assert get("--get", "http.sslcapath") == "/etc/company/cas"
    assert get("--get", "http.sslbackend") == "schannel"
    assert get("--get", "http.schannelcheckrevoke") == "false"
    assert get("--get", "http.schannelusesslcainfo") == "true"
    assert get("--get-urlmatch", "http.proxy", url) == (
        "http://gitlab-proxy.example.org:8080"
    )
    assert get("--get-urlmatch", "http.sslcainfo", url) == (
        "/etc/company/gitlab-ca.pem"
    )
    assert get("--get-urlmatch", "http.noproxy", url) == "gitlab.example.org"
    assert get("--get-urlmatch", "http.sslcapath", url) == (
        "/etc/company/gitlab-cas"
    )
    assert get("--get-urlmatch", "http.sslbackend", url) == "openssl"
    assert get("--get-urlmatch", "http.schannelcheckrevoke", url) == "true"
    assert get("--get-urlmatch", "http.schannelusesslcainfo", url) == "false"
    # The rest of the personal setup is not read.
    assert get("--get-all", "http.extraheader") == ""
    assert get("--get", "http.cookiefile") == ""
    assert get("--get", "http.sslverify") == ""
    assert get("--get", "core.sshcommand") == ""
    assert get("--get", "user.name") == ""


def test_034_a_change_of_the_settings_of_the_user_is_seen_at_the_next_command(
    machine: Machine, tmp_path: Path
) -> None:
    access = GitAccess()
    machine.add_configuration("[http]\n\tproxy = http://first.example.org:1\n")
    first = _get_configuration(
        access.build_environment(), tmp_path, "--get", "http.proxy"
    )
    time.sleep(0.05)
    (machine.home / ".gitconfig").write_text(
        "[http]\n\tproxy = http://second.example.org:2\n"
    )

    second = _get_configuration(
        access.build_environment(), tmp_path, "--get", "http.proxy"
    )

    assert first.stdout.strip() == "http://first.example.org:1"
    assert second.stdout.strip() == "http://second.example.org:2"


def test_035_the_system_configuration_is_still_read(
    machine: Machine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del machine
    system_file = tmp_path / "system-gitconfig"
    system_file.write_text(
        '[filter "lfs"]\n\tclean = git-lfs clean -- %f\n'
        "[credential]\n\thelper = store\n"
    )
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(system_file))
    environment = build_git_environment(GITLAB_URL, TOKEN)
    access_environment = GitAccess().build_environment()

    clean = _get_configuration(
        access_environment, tmp_path, "--get", "filter.lfs.clean"
    )
    filled = _run_credential("fill", GITLAB_FIELDS, environment, tmp_path)

    assert clean.stdout.strip() == "git-lfs clean -- %f"
    # The helpers of the system file are reset like the others.
    assert f"password={TOKEN}" in filled.stdout


# The file of the profile may hold the password of a proxy.


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="The modes of a file are not those of POSIX.",
)
def test_036_the_profile_is_private_to_the_user(
    machine: Machine, tmp_path: Path
) -> None:
    profile_directory = tmp_path / "profile"
    access = GitAccess(profile_directory=profile_directory)
    machine.add_configuration(
        "[http]\n"
        "\tproxy = http://user:made-up-password@proxy.example.org:3128\n"
    )
    previous_mask = os.umask(0)
    try:
        environment = access.build_environment()
        configuration_path = Path(environment["GIT_CONFIG_GLOBAL"])
        assert "made-up-password" in configuration_path.read_text()
        assert stat.S_IMODE(configuration_path.stat().st_mode) == 0o600
        assert stat.S_IMODE(profile_directory.stat().st_mode) == 0o700
        assert (
            stat.S_IMODE((profile_directory / "home").stat().st_mode) == 0o700
        )

        # A file of an older version, open to the group, is made again.
        configuration_path.chmod(0o664)
        time.sleep(0.05)
        machine.add_configuration("[http]\n\tnoProxy = internal.example.org\n")
        access = GitAccess(profile_directory=profile_directory)
        access.build_environment()
        assert stat.S_IMODE(configuration_path.stat().st_mode) == 0o600
    finally:
        os.umask(previous_mask)


def test_037_the_push_follows_origin_when_another_remote_comes_first(
    tmp_path: Path,
) -> None:
    work = _create_work_repository(tmp_path / "work")
    work.close()
    bare = tmp_path / "remote.git"
    backup = tmp_path / "backup.git"
    Repo.clone_from(str(tmp_path / "work"), str(bare), bare=True).close()
    Repo.clone_from(str(tmp_path / "work"), str(backup), bare=True).close()
    # The remote "backup" is the first of the list of the repository.
    project = tmp_path / "project"
    repo = Repo.init(project, initial_branch="main")
    repo.create_remote("backup", str(backup))
    repo.create_remote("origin", str(bare))
    repo.git.fetch("origin")
    repo.git.checkout("-B", "main", "origin/main", "--track")
    assert repo.remotes[0].name == "backup"
    repo.close()
    # A colleague sends a change, the project is behind.
    colleague = tmp_path / "colleague"
    Repo.clone_from(str(bare), str(colleague)).close()
    (colleague / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Colleague\n")
    colleague_repo = Repo(colleague)
    colleague_repo.index.add(["doc.sdoc"])
    colleague_repo.index.commit("Change", author=ACTOR, committer=ACTOR)
    colleague_repo.git.push("origin", "main")
    colleague_repo.close()

    DesktopGitService(str(project), GitAccess()).push(str(project))

    assert "Colleague" in (project / "doc.sdoc").read_text()
    assert _run_git(project, "rev-parse", "HEAD") == _run_git(
        bare, "rev-parse", "main"
    )
