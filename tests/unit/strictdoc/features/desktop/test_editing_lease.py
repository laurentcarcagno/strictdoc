"""
The lease of a page that has an editor open.

@relation(SDOC-SRS-1246, scope=file)
"""

import threading
from pathlib import Path
from typing import List

import pytest

from strictdoc.features.desktop.project_runtime import (
    LEASE_SECONDS_VARIABLE,
    EditingLeases,
    ProjectRuntime,
    get_lease_seconds,
    get_project_runtime,
)


class Clock:
    def __init__(self) -> None:
        self.now: float = 100.0

    def __call__(self) -> float:
        return self.now


def test_001_nobody_edits_without_a_lease() -> None:
    leases = EditingLeases(ttl_seconds=10, clock=Clock())

    assert leases.is_editing() is False
    assert leases.get_page_count() == 0


def test_002_a_lease_ends_when_its_time_runs_out_and_a_renewal_extends_it() -> (
    None
):
    clock = Clock()
    leases = EditingLeases(ttl_seconds=10, clock=clock)
    leases.renew("page-1")

    clock.now += 9
    assert leases.is_editing() is True
    leases.renew("page-1")
    clock.now += 9
    # Renewed: it lives 10 seconds from the renewal.
    assert leases.is_editing() is True
    clock.now += 2

    assert leases.is_editing() is False
    leases.close()


def test_003_two_pages_hold_their_own_lease() -> None:
    clock = Clock()
    leases = EditingLeases(ttl_seconds=10, clock=clock)
    ended: List[int] = []
    leases.add_listener(lambda: ended.append(1))
    leases.renew("page-1")
    leases.renew("page-2")

    leases.release("page-1")
    # The other page still edits: nothing ended.
    assert leases.is_editing() is True
    assert leases.get_page_count() == 1
    assert ended == []

    leases.release("page-2")
    assert leases.is_editing() is False
    assert ended == [1]
    leases.close()


def test_004_the_listeners_hear_the_end_of_the_last_lease_once() -> None:
    clock = Clock()
    leases = EditingLeases(ttl_seconds=10, clock=clock)
    ended: List[int] = []
    leases.add_listener(lambda: ended.append(1))
    leases.renew("page-1")
    leases.renew("page-2")

    # Nothing to release for a page that has none: no end.
    leases.release("page-3")
    assert ended == []
    clock.now += 11
    assert leases.is_editing() is False
    assert leases.is_editing() is False
    leases.release("page-1")

    assert ended == [1]
    leases.close()


def test_005_a_lease_that_runs_out_tells_the_listeners_by_itself() -> None:
    leases = EditingLeases(ttl_seconds=0.2)
    ended = threading.Event()
    leases.add_listener(ended.set)

    leases.renew("page-1")

    # No page asks: the timer of the lease does.
    assert ended.wait(10)
    assert leases.get_page_count() == 0
    leases.close()


def test_006_a_listener_that_fails_does_not_stop_the_others(
    caplog: pytest.LogCaptureFixture,
) -> None:
    leases = EditingLeases(ttl_seconds=10, clock=Clock())
    ended: List[int] = []

    def fail() -> None:
        raise RuntimeError("broken")

    leases.add_listener(fail)
    leases.add_listener(lambda: ended.append(1))
    leases.renew("page-1")

    with caplog.at_level("ERROR"):
        leases.release("page-1")

    assert ended == [1]
    # The failure is in the log: nobody sees a listener that never works.
    assert "listener" in caplog.text
    assert "broken" in caplog.text
    leases.close()


def test_007_the_time_of_a_lease_can_be_set_for_the_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LEASE_SECONDS_VARIABLE, raising=False)
    # A hidden window wakes its timers once a minute: the lease outlives it.
    assert get_lease_seconds() >= 90.0
    monkeypatch.setenv(LEASE_SECONDS_VARIABLE, "2.5")
    assert get_lease_seconds() == 2.5
    monkeypatch.setenv(LEASE_SECONDS_VARIABLE, "none")
    assert get_lease_seconds() >= 90.0
    monkeypatch.setenv(LEASE_SECONDS_VARIABLE, "-1")
    assert get_lease_seconds() >= 90.0


def test_008_the_runtime_is_the_same_for_a_folder_and_raises_the_revision(
    tmp_path: Path,
) -> None:
    runtime = get_project_runtime(str(tmp_path))
    assert get_project_runtime(str(tmp_path)) is runtime
    assert get_project_runtime(str(tmp_path / "other")) is not runtime
    first = runtime.revision

    assert runtime.bump_revision() == first + 1
    assert runtime.revision == first + 1


def test_009_an_update_inhibits_raises_the_revision_and_rebuilds() -> None:
    runtime = ProjectRuntime()
    calls: List[str] = []
    runtime.inhibit_change = lambda path: calls.append(f"inhibit {path}")
    runtime.rebuild_and_notify = lambda: calls.append(
        f"rebuild at {runtime.revision}"
    )

    runtime.apply_update(["/a.sdoc", "/b.sdoc"])

    assert calls == ["inhibit /a.sdoc", "inhibit /b.sdoc", "rebuild at 1"]
    runtime.clear_hooks()
    runtime.apply_update(["/a.sdoc"])
    assert runtime.revision == 2


def test_010_an_update_inhibits_only_what_was_not_inhibited_before() -> None:
    runtime = ProjectRuntime()
    calls: List[str] = []
    runtime.inhibit_change = lambda path: calls.append(f"inhibit {path}")
    runtime.release_change = lambda path: calls.append(f"release {path}")
    inhibition = runtime.inhibit_paths(["/a.sdoc", "/b.sdoc"])

    runtime.apply_update(["/a.sdoc", "/c.sdoc"], inhibition=inhibition)

    # "/a.sdoc" was inhibited before the change, "/b.sdoc" did not change.
    assert calls == [
        "inhibit /a.sdoc",
        "inhibit /b.sdoc",
        "inhibit /c.sdoc",
        "release /b.sdoc",
    ]
    runtime.clear_hooks()
    assert runtime.release_change is None


def test_011_an_inhibition_that_was_there_before_is_not_taken_back() -> None:
    runtime = ProjectRuntime()
    released: List[str] = []
    # "/saved.sdoc" waits for the event of a save: it is not ours.
    runtime.inhibit_change = lambda path: path != "/saved.sdoc"
    runtime.release_change = released.append

    inhibition = runtime.inhibit_paths(["/saved.sdoc", "/other.sdoc"])
    runtime.apply_update([], inhibition=inhibition)

    assert inhibition.paths == ["/saved.sdoc", "/other.sdoc"]
    assert inhibition.owned == ["/other.sdoc"]
    assert released == ["/other.sdoc"]
