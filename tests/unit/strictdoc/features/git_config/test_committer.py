import subprocess
from pathlib import Path

from strictdoc.features.git_config.committer import GitCommitter
from strictdoc.features.git_config.git_service import Author, GitService

DEFAULT = Author("StrictDoc", "strictdoc@localhost")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "config", "user.name", "i")
    _git(tmp_path, "config", "user.email", "i@e")
    (tmp_path / "d.sdoc").write_text(
        "[DOCUMENT]\nTITLE: D\n\n[REQUIREMENT]\nUID: REQ-1\nSTATEMENT: a\n"
    )
    _git(tmp_path, "add", "d.sdoc")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _committer(root: Path) -> GitCommitter:
    return GitCommitter(GitService(str(root)), lambda: DEFAULT)


def test_save_is_committed_with_the_uid(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    doc = root / "d.sdoc"
    doc.write_text(doc.read_text().replace("STATEMENT: a", "STATEMENT: b"))
    _committer(root).on_document_written(str(doc))
    assert _git(root, "log", "-1", "--format=%s") == (
        "feat(doc): update requirement [REQ-1]"
    )


def test_unchanged_save_makes_no_commit(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _committer(root).on_document_written(str(root / "d.sdoc"))
    assert _git(root, "rev-list", "--count", "HEAD") == "1"


def test_assets_wait_for_the_next_save(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    committer = _committer(root)
    asset = root / "_assets" / "m" / "a.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"png")
    committer.on_asset_written(str(asset))
    assert _git(root, "rev-list", "--count", "HEAD") == "1"
    assert committer.pending_paths == [str(asset)]

    doc = root / "d.sdoc"
    doc.write_text(doc.read_text().replace("STATEMENT: a", "STATEMENT: b"))
    committer.on_document_written(str(doc))
    assert "_assets/m/a.png" in _git(root, "show", "--name-only", "HEAD")
    assert committer.pending_paths == []


def test_flush_commits_pending_assets(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    committer = _committer(root)
    asset = root / "_assets" / "a.svg"
    asset.parent.mkdir()
    asset.write_text("<svg/>")
    committer.on_asset_written(str(asset))
    assert committer.flush() is True
    assert (
        _git(root, "log", "-1", "--format=%s") == "feat(doc): add asset a.svg"
    )
    assert committer.flush() is False


def test_failure_never_raises_and_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "not_a_repo"
    root.mkdir()
    doc = root / "d.sdoc"
    doc.write_text("x")
    committer = _committer(root)
    committer.on_document_written(str(doc))
    assert committer.last_error != ""


def test_lfs_attributes_are_written_and_committed(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    committer = GitCommitter(
        GitService(str(root)), lambda: DEFAULT, use_lfs=True
    )
    asset = root / "_assets" / "a.png"
    asset.parent.mkdir()
    asset.write_bytes(b"png")
    committer.on_asset_written(str(asset))
    committer.on_asset_written(str(asset))
    assert committer.flush() is True
    attributes = (root / ".gitattributes").read_text()
    assert attributes.count("_assets/** filter=lfs") == 1
    assert ".gitattributes" in _git(root, "show", "--name-only", "HEAD")


def test_large_asset_gives_a_warning(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    committer = GitCommitter(
        GitService(str(root)), lambda: DEFAULT, asset_warning_bytes=10
    )
    asset = root / "_assets" / "big.png"
    asset.parent.mkdir()
    asset.write_bytes(b"x" * 100)
    committer.on_asset_written(str(asset))
    assert len(committer.warnings) == 1


def test_assets_of_a_deleted_node_are_removed_and_committed(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    assets = root / "_assets"
    for name in ("mid1", "uid_1", "other"):
        (assets / name).mkdir(parents=True)
        (assets / name / "a.png").write_bytes(b"png")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "assets")

    committer = _committer(root)
    removed = committer.on_node_deleted(str(assets), ["mid1", "uid_1", "", "x"])
    assert removed == 2
    assert not (assets / "mid1").exists()
    assert (assets / "other" / "a.png").exists()

    doc = root / "d.sdoc"
    doc.write_text(doc.read_text().replace("STATEMENT: a", "STATEMENT: b"))
    committer.on_document_written(str(doc))
    files = _git(root, "show", "--name-only", "--format=", "HEAD")
    assert "_assets/mid1/a.png" in files
    assert _git(root, "status", "--porcelain") == ""


def test_names_that_leave_the_assets_folder_are_refused(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    (root / "_assets").mkdir()
    (root / "secret").mkdir()
    committer = _committer(root)
    assert (
        committer.on_node_deleted(str(root / "_assets"), ["../secret", ".."])
        == 0
    )
    assert (root / "secret").exists()
