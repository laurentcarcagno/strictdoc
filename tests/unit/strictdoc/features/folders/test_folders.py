import os

import pytest

from strictdoc.features.folders.folders import (
    MARKER,
    clean_folder_path,
    create_folder,
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
