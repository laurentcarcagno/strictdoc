import subprocess
from pathlib import Path
from typing import Tuple

import pytest

from strictdoc.features.git_config.config import GitConfig
from strictdoc.features.git_config.git_service import Author, GitService
from strictdoc.features.git_sync.sync_service import (
    CONFLICTS,
    ERROR,
    MERGED,
    NO_REMOTE,
    PULLED,
    UP_TO_DATE,
    SyncService,
)
from strictdoc.helpers.exception import StrictDocException

AUTHOR = Author("Laurent Carcagno", "laurent@example.com")
HEADER = "[DOCUMENT]\nTITLE: Spec\n\n"


def _req(uid: str, statement: str) -> str:
    return (
        f"[REQUIREMENT]\nUID: {uid}\nTITLE: {uid}\n"
        f"STATEMENT: >>>\n{statement}\n<<<\n\n"
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repos(tmp_path: Path) -> Tuple[Path, Path, Path]:
    """An origin (bare) and two clones, with a document committed."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    first = tmp_path / "first"
    _git(tmp_path, "init", "-q", "-b", "main", str(first))
    (first / "a.sdoc").write_text(
        HEADER + _req("R-1", "one") + _req("R-2", "two"), encoding="utf8"
    )
    _git(first, "add", "-A")
    _git(first, "commit", "-q", "-m", "init")
    _git(first, "remote", "add", "origin", str(origin))
    _git(first, "push", "-q", "-u", "origin", "main")
    second = tmp_path / "second"
    _git(tmp_path, "clone", "-q", str(origin), str(second))
    return origin, first, second


def _service(root: Path) -> SyncService:
    return SyncService(GitService(str(root)), GitConfig(), AUTHOR)


def _commit(root: Path, name: str, text: str, message: str) -> None:
    (root / name).write_text(text, encoding="utf8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _change(root: Path, old: str, new: str, message: str) -> None:
    path = root / "a.sdoc"
    _commit(
        root,
        "a.sdoc",
        path.read_text(encoding="utf8").replace(old, new),
        message,
    )


def test_001_no_remote(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "a.sdoc").write_text(HEADER, encoding="utf8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "x")
    assert _service(tmp_path).sync().status == NO_REMOTE


def test_002_up_to_date_pushes_nothing_new(
    repos: Tuple[Path, Path, Path],
) -> None:
    _, first, _ = repos
    result = _service(first).sync()
    assert result.status == UP_TO_DATE and result.pushed


def test_003_a_local_commit_is_pushed(repos: Tuple[Path, Path, Path]) -> None:
    origin, first, _ = repos
    _change(first, "one", "one local", "local")
    assert _service(first).sync().pushed
    assert "one local" in _git(origin, "show", "main:a.sdoc")


def test_004_the_server_is_ahead_and_a_fast_forward_pulls(
    repos: Tuple[Path, Path, Path],
) -> None:
    _, first, second = repos
    _change(first, "two", "two server", "server")
    _git(first, "push", "-q")
    result = _service(second).sync()
    assert result.status == PULLED and result.pulled == 1
    assert "two server" in (second / "a.sdoc").read_text(encoding="utf8")


def test_005_changes_on_different_nodes_merge_and_push(
    repos: Tuple[Path, Path, Path],
) -> None:
    origin, first, second = repos
    _change(first, "two", "two server", "server")
    _git(first, "push", "-q")
    _change(second, "one", "one local", "local")
    result = _service(second).sync()
    assert result.status == MERGED and result.pushed
    merged = _git(origin, "show", "main:a.sdoc")
    assert "one local" in merged and "two server" in merged
    assert _git(second, "rev-list", "--merges", "--count", "HEAD") == "1"


def test_006_the_same_node_changed_on_both_sides_waits_for_a_person(
    repos: Tuple[Path, Path, Path],
) -> None:
    origin, first, second = repos
    _change(first, "one", "one server", "server")
    _git(first, "push", "-q")
    _change(second, "one", "one local", "local")
    service = _service(second)
    result = service.sync()
    assert result.status == CONFLICTS and result.conflicts == ["a.sdoc"]
    assert not result.pushed
    assert service.service.merge_in_progress(str(second))
    # The server still has its own version.
    assert "one server" in _git(origin, "show", "main:a.sdoc")

    loaded = service.conflict_file("a.sdoc")
    [index] = loaded.conflict_indexes
    assert "one server" in loaded.regions[index].server_text
    assert "one local" in loaded.regions[index].local_text

    done = service.finish(
        {"a.sdoc": {index: loaded.regions[index].choice_text("server")}}
    )
    assert done.status == MERGED and done.pushed
    merged = _git(origin, "show", "main:a.sdoc")
    assert "one server" in merged and "one local" not in merged
    assert not service.service.merge_in_progress(str(second))


def test_007_finish_refuses_a_missing_choice_and_a_broken_document(
    repos: Tuple[Path, Path, Path],
) -> None:
    _, first, second = repos
    _change(first, "one", "one server", "server")
    _git(first, "push", "-q")
    _change(second, "one", "one local", "local")
    service = _service(second)
    service.sync()
    with pytest.raises(StrictDocException, match="without a choice"):
        service.finish({})
    [index] = service.conflict_file("a.sdoc").conflict_indexes
    with pytest.raises(StrictDocException, match="not a valid document"):
        service.finish({"a.sdoc": {index: "[REQUIREMENT]\nUID: R-1\nBROKEN"}})
    assert service.service.merge_in_progress(str(second))


def test_008_abort_goes_back_to_the_local_state(
    repos: Tuple[Path, Path, Path],
) -> None:
    _, first, second = repos
    _change(first, "one", "one server", "server")
    _git(first, "push", "-q")
    _change(second, "one", "one local", "local")
    service = _service(second)
    service.sync()
    service.abort()
    assert not service.service.merge_in_progress(str(second))
    assert "one local" in (second / "a.sdoc").read_text(encoding="utf8")


def test_009_a_conflict_outside_a_document_abandons_the_merge(
    repos: Tuple[Path, Path, Path],
) -> None:
    _, first, second = repos
    _commit(first, "notes.txt", "server\n", "server notes")
    _git(first, "push", "-q")
    _commit(second, "notes.txt", "local\n", "local notes")
    service = _service(second)
    result = service.sync()
    assert result.status == ERROR and "notes.txt" in result.message
    assert not service.service.merge_in_progress(str(second))


def test_010_uncommitted_changes_are_saved_first(
    repos: Tuple[Path, Path, Path],
) -> None:
    origin, _, second = repos
    (second / "b.sdoc").write_text(
        HEADER + _req("R-9", "nine"), encoding="utf8"
    )
    assert _service(second).sync().pushed
    assert "R-9" in _git(origin, "show", "main:b.sdoc")


def test_011_conflicts_of_two_documents_are_listed(
    repos: Tuple[Path, Path, Path],
) -> None:
    _, first, second = repos
    for root, word in ((first, "server"), (second, "local")):
        _change(root, "one", f"one {word}", word)
        _change(root, "two", f"two {word}", word + "2")
    _git(first, "push", "-q")
    service = _service(second)
    assert service.sync().status == CONFLICTS
    assert service.conflict_paths() == ["a.sdoc"]
    assert len(service.conflict_file("a.sdoc").conflict_indexes) >= 1


def test_012_keeping_both_sides_of_the_same_node_is_refused(
    repos: Tuple[Path, Path, Path],
) -> None:
    _, first, second = repos
    _change(first, "one", "one server", "server")
    _git(first, "push", "-q")
    _change(second, "one", "one local", "local")
    service = _service(second)
    service.sync()
    [index] = service.conflict_file("a.sdoc").conflict_indexes
    region = service.conflict_file("a.sdoc").regions[index]
    with pytest.raises(StrictDocException, match="twice"):
        service.resolve("a.sdoc", {index: region.choice_text("both")})
    assert service.service.merge_in_progress(str(second))


def test_013_resolve_then_complete_handles_one_document_at_a_time(
    repos: Tuple[Path, Path, Path],
) -> None:
    origin, first, second = repos
    _change(first, "one", "one server", "server")
    _git(first, "push", "-q")
    _change(second, "one", "one local", "local")
    service = _service(second)
    service.sync()
    loaded = service.conflict_file("a.sdoc")
    [index] = loaded.conflict_indexes
    edited = loaded.regions[index].server_text.replace(
        "one server", "edited by hand"
    )
    service.resolve("a.sdoc", {index: edited})
    result = service.complete()
    assert result.status == MERGED and result.pushed
    assert "edited by hand" in _git(origin, "show", "main:a.sdoc")
