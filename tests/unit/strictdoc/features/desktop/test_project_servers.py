"""
@relation(SDOC-SRS-1232, scope=file)
@relation(SDOC-SRS-1233, scope=file)
"""

import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

import pytest

from strictdoc.features.desktop.project_servers import ProjectServerManager
from strictdoc.features.desktop.settings import DesktopSettings, save_settings
from strictdoc.features.desktop.workspace import WorkspaceError


class FakeServer:
    def __init__(self, folder: str, number: int) -> None:
        self.folder: str = folder
        self.start_url: str = f"http://127.0.0.1:{6000 + number}/start"
        self.direct_url: str = f"http://127.0.0.1:{6000 + number}/"
        self.is_bootstrapped: bool = False
        self.is_running: bool = False
        self.listener: Optional[Callable[[], None]] = None

    def set_bootstrap_listener(
        self, listener: Optional[Callable[[], None]]
    ) -> None:
        self.listener = listener

    def start(self) -> None:
        self.is_running = True

    def wait_until_ready(self) -> None:
        pass

    def stop(self) -> None:
        self.is_running = False

    def follow_start_url(self) -> None:
        """What the window does: it loads the start URL, and gets the cookie."""
        self.is_bootstrapped = True
        assert self.listener is not None
        self.listener()


class Context:
    def __init__(
        self,
        tmp_path: Path,
        *,
        kept_servers: int = 2,
        updater: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.settings_path: Path = tmp_path / "settings.json"
        save_settings(
            DesktopSettings(kept_servers=kept_servers), self.settings_path
        )
        self.servers: List[FakeServer] = []
        self.updated: List[str] = []
        self.manager = ProjectServerManager(
            server_factory=self._create_server,
            updater=updater if updater is not None else self._update,
            settings_path=self.settings_path,
            eviction_delay_seconds=0,
        )

    def _create_server(
        self, folder: str, principal_provider: object = None
    ) -> FakeServer:
        del principal_provider
        server = FakeServer(folder, len(self.servers))
        self.servers.append(server)
        return server

    def _update(self, folder: str) -> bool:
        self.updated.append(folder)
        return False


def _wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 10
    while not condition():
        assert time.monotonic() < deadline, "The condition was not met."
        time.sleep(0.01)


@pytest.fixture(name="context")
def fixture_context(tmp_path: Path) -> Context:
    return Context(tmp_path)


def test_001_first_open_starts_the_server_and_gives_the_start_url(
    context: Context,
) -> None:
    url = context.manager.open("a", "/projects/a")

    assert url == context.servers[0].start_url
    assert context.servers[0].is_running
    assert context.manager.get_open_identifiers() == {"a"}


def test_002_open_project_is_joined_without_starting_a_server(
    context: Context,
) -> None:
    context.manager.open("a", "/projects/a")

    start_url = context.manager.get_open_url("a", "/projects/a")
    context.servers[0].follow_start_url()
    direct_url = context.manager.get_open_url("a", "/projects/a")
    opened_url = context.manager.open("a", "/projects/a")

    assert len(context.servers) == 1
    # Before the window follows the start URL, the window has no cookie.
    assert start_url == context.servers[0].start_url
    assert direct_url == context.servers[0].direct_url
    assert opened_url == context.servers[0].direct_url


def test_003_unknown_project_or_other_folder_is_not_joined(
    context: Context,
) -> None:
    context.manager.open("a", "/projects/a")

    assert context.manager.get_open_url("b", "/projects/b") is None
    assert context.manager.get_open_url("a", "/elsewhere") is None


def test_004_oldest_server_stops_when_the_window_has_the_new_project(
    context: Context,
) -> None:
    context.manager.open("a", "/projects/a")
    context.manager.open("b", "/projects/b")
    context.manager.open("c", "/projects/c")

    # The window did not load the page of the new project yet: no server stops.
    assert [server_.is_running for server_ in context.servers] == [
        True,
        True,
        True,
    ]

    context.servers[2].follow_start_url()

    _wait_until(lambda: not context.servers[0].is_running)
    assert [server_.is_running for server_ in context.servers] == [
        False,
        True,
        True,
    ]
    assert context.manager.get_open_identifiers() == {"b", "c"}


def test_005_use_of_a_project_makes_it_the_most_recent(
    context: Context,
) -> None:
    context.manager.open("a", "/projects/a")
    context.manager.open("b", "/projects/b")
    context.manager.open("a", "/projects/a")
    context.manager.open("c", "/projects/c")
    context.servers[2].follow_start_url()

    _wait_until(lambda: not context.servers[1].is_running)

    assert context.manager.get_open_identifiers() == {"a", "c"}


def test_006_number_of_servers_comes_from_the_settings(
    tmp_path: Path,
) -> None:
    context = Context(tmp_path, kept_servers=1)
    context.manager.open("a", "/projects/a")
    context.manager.open("b", "/projects/b")
    context.servers[1].follow_start_url()

    _wait_until(lambda: not context.servers[0].is_running)
    save_settings(DesktopSettings(kept_servers=3), context.settings_path)
    context.manager.open("c", "/projects/c")
    context.manager.open("d", "/projects/d")
    context.servers[3].follow_start_url()

    _wait_until(
        lambda: context.manager.get_open_identifiers() == {"b", "c", "d"}
    )


def test_007_new_folder_of_a_project_replaces_its_server(
    context: Context,
) -> None:
    context.manager.open("a", "/projects/a")

    url = context.manager.open("a", "/elsewhere/a")

    assert not context.servers[0].is_running
    assert context.servers[1].is_running
    assert url == context.servers[1].start_url
    assert context.manager.get_open_identifiers() == {"a"}


def test_008_stop_all_stops_every_server(context: Context) -> None:
    context.manager.open("a", "/projects/a")
    context.manager.open("b", "/projects/b")

    context.manager.stop_all()

    assert [server_.is_running for server_ in context.servers] == [False, False]
    assert context.manager.get_open_identifiers() == set()


def test_009_same_project_opened_by_two_threads_starts_one_server(
    context: Context,
) -> None:
    urls: List[str] = []

    def open_project() -> None:
        urls.append(context.manager.open("a", "/projects/a"))

    threads = [threading.Thread(target=open_project) for _ in range(5)]
    for thread_ in threads:
        thread_.start()
    for thread_ in threads:
        thread_.join()

    assert len(context.servers) == 1
    assert len(urls) == 5


def test_010_open_and_return_update_the_project_in_the_background(
    context: Context,
) -> None:
    context.manager.open("a", "/projects/a")
    _wait_until(lambda: len(context.updated) == 1)

    context.manager.get_open_url("a", "/projects/a")

    _wait_until(lambda: len(context.updated) == 2)
    assert context.updated == ["/projects/a", "/projects/a"]


def test_011_project_that_was_just_cloned_is_not_updated(
    context: Context,
) -> None:
    context.manager.open("a", "/projects/a", is_update_needed=False)
    time.sleep(0.1)

    assert context.updated == []


def test_012_open_does_not_wait_for_the_update(tmp_path: Path) -> None:
    release = threading.Event()
    started = threading.Event()

    def slow_update(folder: str) -> bool:
        del folder
        started.set()
        release.wait(10)
        return True

    context = Context(tmp_path, updater=slow_update)

    started_at = time.monotonic()
    context.manager.open("a", "/projects/a")
    context.manager.get_open_url("a", "/projects/a")
    duration = time.monotonic() - started_at

    assert started.wait(10)
    assert duration < 2
    release.set()


def test_013_only_one_update_at_a_time_for_a_project(tmp_path: Path) -> None:
    release = threading.Event()
    calls: List[str] = []

    def slow_update(folder: str) -> bool:
        calls.append(folder)
        release.wait(10)
        return False

    context = Context(tmp_path, updater=slow_update)
    context.manager.open("a", "/projects/a")
    _wait_until(lambda: len(calls) == 1)

    context.manager.get_open_url("a", "/projects/a")
    context.manager.get_open_url("a", "/projects/a")
    release.set()
    _wait_until(lambda: not context.manager._updating)  # noqa: SLF001

    assert calls == ["/projects/a"]


def test_014_failed_update_is_logged_and_nothing_else(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def offline_update(folder: str) -> bool:
        del folder
        raise WorkspaceError("fatal: unable to access the remote")

    context = Context(tmp_path, updater=offline_update)

    with caplog.at_level(logging.INFO):
        url = context.manager.open("a", "/projects/a")
        _wait_until(lambda: not context.manager._updating)  # noqa: SLF001

    assert url == context.servers[0].start_url
    assert context.servers[0].is_running
    assert "not updated from its remote" in caplog.text
    assert "unable to access the remote" in caplog.text


def test_015_unexpected_error_of_the_update_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def broken_update(folder: str) -> bool:
        del folder
        raise RuntimeError("boom")

    context = Context(tmp_path, updater=broken_update)

    with caplog.at_level(logging.INFO):
        context.manager.open("a", "/projects/a")
        _wait_until(lambda: not context.manager._updating)  # noqa: SLF001

    assert "the update failed" in caplog.text
