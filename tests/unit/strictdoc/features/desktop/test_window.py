"""
@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1234, scope=file)
"""

import queue
import threading
import time
from typing import Callable, Iterator, List, Optional

import pytest

from strictdoc.features.desktop import window


def test_windows_uses_webview2() -> None:
    assert window.get_window_engine("win32") == "edgechromium"


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_other_platforms_use_qt(platform: str) -> None:
    assert window.get_window_engine(platform) == "qt"


def test_check_follows_the_engine_of_the_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_engines = []
    monkeypatch.setattr(window, "_import_webview", checked_engines.append)

    monkeypatch.setattr(window.sys, "platform", "win32")
    window.check_window_available()
    monkeypatch.setattr(window.sys, "platform", "linux")
    window.check_window_available()

    assert checked_engines == ["edgechromium", "qt"]


def test_missing_requirement_of_the_engine_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        window._ENGINE_REQUIREMENTS, "qt", "module_that_does_not_exist"
    )
    monkeypatch.setattr(window.sys, "platform", "linux")

    with pytest.raises(window.DesktopWindowError, match="with Qt"):
        window.check_window_available()


def test_message_for_windows_names_webview2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        window._ENGINE_REQUIREMENTS,
        "edgechromium",
        "module_that_does_not_exist",
    )
    monkeypatch.setattr(window.sys, "platform", "win32")

    with pytest.raises(window.DesktopWindowError, match="WebView2"):
        window.check_window_available()


# The cookies of the window are cleared in the thread of the window.


class FakeGuiThread:
    """A thread that runs the jobs one after the other, as the loop of Qt."""

    def __init__(self) -> None:
        self.jobs: queue.Queue[Optional[Callable[[], None]]] = queue.Queue()
        self.thread: threading.Thread = threading.Thread(
            target=self._run, name="fake-gui"
        )
        self.thread.start()

    def post(self, job: Callable[[], None]) -> None:
        self.jobs.put(job)

    def stop(self) -> None:
        self.jobs.put(None)
        self.thread.join(10)

    def _run(self) -> None:
        while True:
            job = self.jobs.get()
            if job is None:
                return
            job()


class FakeWindow:
    def __init__(self, events: List[str]) -> None:
        self.events: List[str] = events
        self.error: Optional[Exception] = None

    def clear_cookies(self) -> None:
        self.events.append(f"clear starts in {threading.current_thread().name}")
        time.sleep(0.2)
        if self.error is not None:
            raise self.error
        self.events.append("clear ends")


@pytest.fixture(name="gui")
def fixture_gui(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeGuiThread]:
    gui = FakeGuiThread()
    monkeypatch.setattr(window, "_post_to_gui_thread", gui.post)
    yield gui
    gui.stop()


def _call_in_request_thread(function: Callable[[], object]) -> object:
    """The sign-out runs in a thread of the server, not in the main one."""
    results: List[object] = []
    thread = threading.Thread(target=lambda: results.append(function()))
    thread.start()
    thread.join(20)
    assert not thread.is_alive()
    return results[0]


def test_the_cookies_are_cleared_in_the_gui_thread_and_awaited(
    gui: FakeGuiThread, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    @relation(SDOC-SRS-1234, scope=function)
    """
    events: List[str] = []
    monkeypatch.setattr(window, "_window", FakeWindow(events))

    def clear_then_load() -> object:
        cleared = window.clear_window_cookies()
        events.append("the caller goes on")
        # What the window loads next is a job of its thread, after the clear.
        gui.post(lambda: events.append("the window loads the start path"))
        return cleared

    assert _call_in_request_thread(clear_then_load) is True
    gui.stop()

    assert events == [
        "clear starts in fake-gui",
        "clear ends",
        "the caller goes on",
        "the window loads the start path",
    ]


def test_without_a_window_nothing_is_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(window, "_window", None)

    assert window.clear_window_cookies() is False


def test_a_gui_thread_that_does_not_answer_is_false_and_not_a_hang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[str] = []
    monkeypatch.setattr(window, "_window", FakeWindow(events))
    # The thread of the window takes no job.

    def take_no_job(job: Callable[[], None]) -> None:
        del job

    monkeypatch.setattr(window, "_post_to_gui_thread", take_no_job)
    monkeypatch.setattr(window, "GUI_THREAD_TIMEOUT_SECONDS", 0.1)
    started = time.monotonic()

    def run() -> object:
        return window.run_on_gui_thread(
            lambda: events.append("ran"), timeout_seconds=0.1
        )

    assert _call_in_request_thread(run) is False
    assert time.monotonic() - started < 5
    assert events == []


@pytest.mark.usefixtures("gui")
def test_an_error_of_the_gui_thread_comes_back_to_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_window = FakeWindow([])
    fake_window.error = RuntimeError("the store is closed")
    monkeypatch.setattr(window, "_window", fake_window)

    def run() -> object:
        try:
            window.clear_window_cookies()
        except RuntimeError as error_:
            return str(error_)
        return None

    assert _call_in_request_thread(run) == "the store is closed"


def test_without_a_qt_poster_the_call_runs_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: List[str] = []
    monkeypatch.setattr(window, "_window", FakeWindow(events))
    monkeypatch.setattr(window, "_post_to_gui_thread", None)

    assert window.clear_window_cookies() is True
    assert events[0] == f"clear starts in {threading.current_thread().name}"
