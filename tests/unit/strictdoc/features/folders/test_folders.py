import os

import pytest

from strictdoc.features.folders.folders import (
    MARKER,
    clean_folder_path,
    create_folder,
    delete_folder,
    move_document,
    move_folder,
    rename_document,
    rename_folder,
    tree_path,
)
from strictdoc.helpers.exception import StrictDocException


def test_001_a_path_is_cleaned():
    assert clean_folder_path(" /specs/ ") == "specs"
    assert clean_folder_path("a\\b/c") == "a/b/c"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "  ",
        "..",
        "a/../b",
        ".hidden",
        "a b",
        "a/_assets",
        "output",
        "x" * 70,
        "a/b/c/d/e/f/g/h/i",
        "name.",
        "<x>",
    ],
)
def test_002_a_bad_path_is_refused(bad):
    with pytest.raises(StrictDocException):
        clean_folder_path(bad)


def test_003_every_new_level_gets_the_marker(tmp_path):
    (tmp_path / "specs").mkdir()
    created = create_folder(str(tmp_path), "specs/system/icd")
    assert created == ["specs/system", "specs/system/icd"]
    assert not (tmp_path / "specs" / MARKER).exists()  # it existed already
    assert (tmp_path / "specs" / "system" / MARKER).is_file()
    assert (tmp_path / "specs" / "system" / "icd" / MARKER).is_file()


def test_004_an_existing_folder_or_a_file_in_the_way_is_refused(tmp_path):
    create_folder(str(tmp_path), "a")
    with pytest.raises(StrictDocException):
        create_folder(str(tmp_path), "a")
    (tmp_path / "f").write_text("x")
    with pytest.raises(StrictDocException):
        create_folder(str(tmp_path), "f/sub")


def test_005_a_link_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside, root / "link")
    with pytest.raises(StrictDocException):
        create_folder(str(root), "link/inside")
    assert list(outside.iterdir()) == []


def _doc(path, text="[DOCUMENT]\nTITLE: T\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


def test_010_a_folder_is_renamed_with_its_content(tmp_path):
    create_folder(str(tmp_path), "specs/sub")
    _doc(tmp_path / "specs" / "a.sdoc")
    assert rename_folder(str(tmp_path), "specs", "requirements") == (
        "requirements"
    )
    assert not (tmp_path / "specs").exists()
    assert (tmp_path / "requirements" / "a.sdoc").is_file()
    assert (tmp_path / "requirements" / "sub" / MARKER).is_file()


@pytest.mark.parametrize("bad", ["", "a/b", "..", "_assets", "a b", "x" * 70])
def test_011_a_bad_new_name_is_refused(tmp_path, bad):
    create_folder(str(tmp_path), "specs")
    with pytest.raises(StrictDocException):
        rename_folder(str(tmp_path), "specs", bad)
    assert (tmp_path / "specs").is_dir()


def test_012_a_rename_onto_an_existing_name_is_refused(tmp_path):
    create_folder(str(tmp_path), "a")
    create_folder(str(tmp_path), "b")
    with pytest.raises(StrictDocException, match="exists"):
        rename_folder(str(tmp_path), "a", "b")


def test_013_a_folder_moves_into_another_one_or_to_the_root(tmp_path):
    create_folder(str(tmp_path), "a/sub")
    create_folder(str(tmp_path), "b")
    assert move_folder(str(tmp_path), "a/sub", "b") == "b/sub"
    assert (tmp_path / "b" / "sub" / MARKER).is_file()
    assert move_folder(str(tmp_path), "b/sub", "") == "sub"
    assert (tmp_path / "sub").is_dir()


def test_014_a_folder_cannot_move_into_itself_or_stay_where_it_is(tmp_path):
    create_folder(str(tmp_path), "a/sub")
    with pytest.raises(StrictDocException, match="itself"):
        move_folder(str(tmp_path), "a", "a/sub")
    with pytest.raises(StrictDocException, match="itself"):
        move_folder(str(tmp_path), "a", "a")
    with pytest.raises(StrictDocException, match="already"):
        move_folder(str(tmp_path), "a/sub", "a")


def test_015_a_move_that_is_too_deep_or_to_a_missing_folder_is_refused(
    tmp_path,
):
    create_folder(str(tmp_path), "a/b/c/d/e/f/g")
    create_folder(str(tmp_path), "x/y")
    with pytest.raises(StrictDocException, match="levels"):
        move_folder(str(tmp_path), "x", "a/b/c/d/e/f/g")
    with pytest.raises(StrictDocException, match="does not exist"):
        move_folder(str(tmp_path), "x", "nowhere")


def test_016_paths_outside_the_project_are_refused(tmp_path):
    (tmp_path / "root").mkdir()
    create_folder(str(tmp_path / "root"), "a")
    (tmp_path / "other").mkdir()
    for call in (
        lambda: move_folder(str(tmp_path / "root"), "../other", "a"),
        lambda: move_folder(str(tmp_path / "root"), "a", "../other"),
        lambda: rename_folder(str(tmp_path / "root"), "../other", "z"),
        lambda: delete_folder(str(tmp_path / "root"), "../other"),
    ):
        with pytest.raises(StrictDocException):
            call()
    assert (tmp_path / "other").is_dir()


def test_017_a_document_moves_and_the_emptied_folder_stays(tmp_path):
    create_folder(str(tmp_path), "b")
    _doc(tmp_path / "a" / "one.sdoc")
    assert move_document(str(tmp_path), "a/one.sdoc", "b") == "b/one.sdoc"
    assert (tmp_path / "b" / "one.sdoc").is_file()
    assert (tmp_path / "a" / MARKER).is_file()  # the tree still shows it


def test_018_a_document_move_refuses_a_name_clash_or_a_non_document(tmp_path):
    create_folder(str(tmp_path), "b")
    _doc(tmp_path / "a" / "one.sdoc")
    _doc(tmp_path / "b" / "one.sdoc")
    (tmp_path / "a" / "notes.txt").write_text("x")
    with pytest.raises(StrictDocException, match="exists"):
        move_document(str(tmp_path), "a/one.sdoc", "b")
    with pytest.raises(StrictDocException, match="document"):
        move_document(str(tmp_path), "a/notes.txt", "b")
    with pytest.raises(StrictDocException, match="already"):
        move_document(str(tmp_path), "a/one.sdoc", "a")


def test_019_a_move_rewrites_the_include_of_a_moved_target_or_includer(
    tmp_path,
):
    create_folder(str(tmp_path), "b")
    _doc(
        tmp_path / "main.sdoc",
        "[DOCUMENT]\nTITLE: M\n\n[DOCUMENT_FROM_FILE]\nFILE: part.sdoc\n",
    )
    _doc(tmp_path / "part.sdoc")
    move_document(str(tmp_path), "part.sdoc", "b")
    assert "FILE: b/part.sdoc\n" in (tmp_path / "main.sdoc").read_text()
    move_document(str(tmp_path), "main.sdoc", "b")
    assert "FILE: part.sdoc\n" in (tmp_path / "b" / "main.sdoc").read_text()
    assert (tmp_path / "b" / "part.sdoc").is_file()


def test_020_documents_that_move_together_keep_their_includes(tmp_path):
    create_folder(str(tmp_path), "dest")
    text = "[DOCUMENT]\nTITLE: M\n\n[DOCUMENT_FROM_FILE]\nFILE: part.sdoc\n"
    _doc(tmp_path / "pack" / "main.sdoc", text)
    _doc(tmp_path / "pack" / "part.sdoc")
    assert move_folder(str(tmp_path), "pack", "dest") == "dest/pack"
    assert (tmp_path / "dest" / "pack" / "part.sdoc").is_file()
    assert (tmp_path / "dest" / "pack" / "main.sdoc").read_text() == text


def test_021_a_folder_move_rewrites_a_grammar_import_and_keeps_the_rest(
    tmp_path,
):
    create_folder(str(tmp_path), "dest")
    _doc(
        tmp_path / "pack" / "main.sdoc",
        "[DOCUMENT]\r\nTITLE: M\r\n\r\n[GRAMMAR]\r\n"
        "IMPORT_FROM_FILE: ../shared.sgra\r\n",
    )
    _doc(
        tmp_path / "pack" / "other.sdoc",
        "[DOCUMENT]\nTITLE: O\n\n[GRAMMAR]\nIMPORT_FROM_FILE: @x.sgra\n",
    )
    (tmp_path / "shared.sgra").write_text("x")
    move_folder(str(tmp_path), "pack", "dest")
    moved = (tmp_path / "dest" / "pack" / "main.sdoc").read_bytes()
    assert b"IMPORT_FROM_FILE: ../../shared.sgra\r\n" in moved
    assert b"TITLE: M\r\n" in moved
    other = (tmp_path / "dest" / "pack" / "other.sdoc").read_text()
    assert "IMPORT_FROM_FILE: @x.sgra\n" in other


def test_023_an_include_from_another_folder_follows_a_folder_rename(tmp_path):
    _doc(
        tmp_path / "a" / "main.sdoc",
        "[DOCUMENT]\nTITLE: M\n\n[DOCUMENT_FROM_FILE]\nFILE: ../parts/p.sdoc\n",
    )
    _doc(tmp_path / "parts" / "p.sdoc")
    rename_folder(str(tmp_path), "parts", "pieces")
    assert (
        "FILE: ../pieces/p.sdoc\n" in (tmp_path / "a" / "main.sdoc").read_text()
    )


def test_024_several_input_folders_name_their_paths_by_the_folder(tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    roots = [str(one), str(two)]
    assert create_folder(roots, "two/x/y") == ["two/x", "two/x/y"]
    _doc(
        one / "main.sdoc",
        "[DOCUMENT]\nTITLE: M\n\n[DOCUMENT_FROM_FILE]\nFILE: part.sdoc\n",
    )
    _doc(one / "part.sdoc")
    assert move_document(roots, "one/part.sdoc", "two/x") == "two/x/part.sdoc"
    assert "FILE: ../two/x/part.sdoc\n" in (one / "main.sdoc").read_text()
    assert move_folder(roots, "two/x", "one") == "one/x"
    assert "FILE: x/part.sdoc\n" in (one / "main.sdoc").read_text()
    assert tree_path(roots, str(one / "x" / "y")) == "one/x/y"
    with pytest.raises(StrictDocException, match="several"):
        move_folder(roots, "one/x", "")
    with pytest.raises(StrictDocException, match="input folder"):
        rename_folder(roots, "one", "uno")
    with pytest.raises(StrictDocException, match="input folder"):
        delete_folder(roots, "two")


def test_022_only_an_empty_folder_is_deleted(tmp_path):
    create_folder(str(tmp_path), "a/b")
    delete_folder(str(tmp_path), "a")
    assert not (tmp_path / "a").exists()
    _doc(tmp_path / "c" / "d" / "one.sdoc")
    with pytest.raises(StrictDocException, match="one.sdoc"):
        delete_folder(str(tmp_path), "c")
    assert (tmp_path / "c" / "d" / "one.sdoc").is_file()
    with pytest.raises(StrictDocException, match="does not exist"):
        delete_folder(str(tmp_path), "gone")


def test_025_a_document_is_renamed_and_the_includes_follow(tmp_path):
    _doc(
        tmp_path / "main.sdoc",
        "[DOCUMENT]\nTITLE: M\n\n[DOCUMENT_FROM_FILE]\nFILE: part.sdoc\n",
    )
    _doc(tmp_path / "part.sdoc")
    assert rename_document(str(tmp_path), "part.sdoc", "piece") == "piece.sdoc"
    assert (tmp_path / "piece.sdoc").is_file()
    assert "FILE: piece.sdoc\n" in (tmp_path / "main.sdoc").read_text()
    assert rename_document(str(tmp_path), "main.sdoc", "root.sdoc") == (
        "root.sdoc"
    )
    assert (tmp_path / "root.sdoc").is_file()


@pytest.mark.parametrize(
    "bad", ["", ".sdoc", "a b", "a/b", "..", "_assets", "x" * 130, "name..sdoc"]
)
def test_026_a_bad_document_name_is_refused(tmp_path, bad):
    _doc(tmp_path / "one.sdoc")
    with pytest.raises(StrictDocException):
        rename_document(str(tmp_path), "one.sdoc", bad)
    assert (tmp_path / "one.sdoc").is_file()


def test_027_a_document_rename_refuses_a_clash_or_a_non_document(tmp_path):
    _doc(tmp_path / "one.sdoc")
    _doc(tmp_path / "two.sdoc")
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(StrictDocException, match="exists"):
        rename_document(str(tmp_path), "one.sdoc", "two")
    with pytest.raises(StrictDocException, match="same"):
        rename_document(str(tmp_path), "one.sdoc", "one.sdoc")
    with pytest.raises(StrictDocException, match="document"):
        rename_document(str(tmp_path), "notes.txt", "x")
