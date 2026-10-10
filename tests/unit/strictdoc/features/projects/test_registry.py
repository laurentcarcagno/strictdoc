import json
import os
from pathlib import Path

import pytest

from strictdoc.features.projects.registry import (
    ProjectSpec,
    build_project_config,
    load_registry,
    validate_specs,
)
from strictdoc.helpers.exception import StrictDocException

ROLES = {
    "administrator": ["a-admins"],
    "author": ["a-authors"],
    "reviewer": ["a-reviewers"],
    "reader": ["a-readers"],
}


def _folder(root: Path, name: str) -> str:
    path = root / name
    path.mkdir(parents=True)
    (path / "document.sdoc").write_text(
        "[DOCUMENT]\nTITLE: Doc\n\n[TEXT]\nSTATEMENT: x\n", encoding="utf8"
    )
    return str(path)


def _spec(root: Path, slug: str, **kwargs) -> ProjectSpec:
    return ProjectSpec(
        slug=slug,
        title=slug.title(),
        path=_folder(root, slug),
        roles=kwargs.pop("roles", ROLES),
        **kwargs,
    )


def test_001_valid_specs_are_accepted(tmp_path):
    validate_specs([_spec(tmp_path, "alpha"), _spec(tmp_path, "beta-2")])


@pytest.mark.parametrize(
    "slug", ["", "Alpha", "-a", "a-", "a_b", "a.b", "a b", "x" * 33, "é"]
)
def test_002_an_invalid_slug_is_refused(tmp_path, slug):
    spec = ProjectSpec(slug=slug, title="T", path=str(tmp_path))
    with pytest.raises(StrictDocException, match="Invalid slug"):
        validate_specs([spec])


def test_003_a_duplicate_slug_is_refused(tmp_path):
    first = _spec(tmp_path, "alpha")
    second = ProjectSpec(
        slug="alpha", title="Other", path=_folder(tmp_path, "other")
    )
    with pytest.raises(StrictDocException, match="used twice"):
        validate_specs([first, second])


def test_004_a_missing_folder_or_config_is_refused(tmp_path):
    with pytest.raises(StrictDocException, match="folder does not exist"):
        validate_specs(
            [ProjectSpec(slug="a", title="A", path=str(tmp_path / "none"))]
        )
    spec = _spec(tmp_path, "b")
    spec.config = str(tmp_path / "none.py")
    with pytest.raises(StrictDocException, match="configuration file"):
        validate_specs([spec])


def test_005_a_folder_outside_the_data_root_is_refused(tmp_path):
    inside = _spec(tmp_path / "data", "alpha")
    outside = _spec(tmp_path / "elsewhere", "beta")
    validate_specs([inside], str(tmp_path / "data"))
    with pytest.raises(StrictDocException, match="outside the data root"):
        validate_specs([inside, outside], str(tmp_path / "data"))


def test_006_a_link_that_leaves_the_data_root_is_refused(tmp_path):
    (tmp_path / "data").mkdir()
    target = _folder(tmp_path / "elsewhere", "secret")
    os.symlink(target, tmp_path / "data" / "alpha")
    spec = ProjectSpec(
        slug="alpha", title="A", path=str(tmp_path / "data" / "alpha")
    )
    with pytest.raises(StrictDocException, match="outside the data root"):
        validate_specs([spec], str(tmp_path / "data"))


def test_007_two_projects_cannot_share_a_folder(tmp_path):
    first = _spec(tmp_path, "alpha")
    second = ProjectSpec(slug="beta", title="B", path=first.path)
    with pytest.raises(StrictDocException, match="same folder"):
        validate_specs([first, second])


def test_008_roles_are_validated(tmp_path):
    spec = _spec(tmp_path, "alpha", roles={"boss": ["x"]})
    with pytest.raises(StrictDocException, match="roles"):
        validate_specs([spec])
    spec = _spec(tmp_path, "beta", roles={"reader": ["g"], "author": ["g"]})
    with pytest.raises(StrictDocException, match="roles"):
        validate_specs([spec])


def test_009_an_empty_registry_is_refused():
    with pytest.raises(StrictDocException, match="no project"):
        validate_specs([])


def test_010_a_registry_file_is_loaded_with_relative_paths(tmp_path):
    _folder(tmp_path, "alpha")
    registry = tmp_path / "projects.py"
    registry.write_text(
        "from strictdoc.features.projects.registry import ProjectSpec\n"
        "def create_projects():\n"
        "    return [ProjectSpec(slug='alpha', title='Alpha', path='alpha')]\n",
        encoding="utf8",
    )
    specs = load_registry(str(registry), str(tmp_path))
    assert [s.slug for s in specs] == ["alpha"]
    assert specs[0].path == str(tmp_path / "alpha")


def test_011_a_registry_without_the_function_is_reported(tmp_path):
    registry = tmp_path / "projects.py"
    registry.write_text("X = 1\n", encoding="utf8")
    with pytest.raises(StrictDocException, match="create_projects"):
        load_registry(str(registry))
    with pytest.raises(StrictDocException, match="not found"):
        load_registry(str(tmp_path / "none.py"))


def test_012_each_project_gets_its_own_output_audit_and_roles(
    tmp_path, monkeypatch
):
    # A single-project deployment sets these; a registry project ignores them.
    monkeypatch.setenv("STRICTDOC_ROLES", json.dumps({"reader": ["global"]}))
    alpha = _spec(tmp_path, "alpha")
    beta = _spec(tmp_path, "beta", roles={"reader": ["b-readers"]})
    out = tmp_path / "out"
    config_a = build_project_config(
        alpha, output_root=str(out), audit_root=None, proxy=False
    )
    config_b = build_project_config(
        beta,
        output_root=str(out),
        audit_root=str(tmp_path / "audit"),
        proxy=False,
    )
    assert config_a.output_dir == str(out / "alpha")
    assert config_b.output_dir == str(out / "beta")
    assert config_a.get_path_to_cache_dir() != config_b.get_path_to_cache_dir()
    assert config_a.audit_dir == str(out / "alpha")
    assert config_b.audit_dir == str(tmp_path / "audit" / "beta")
    assert config_a.roles == ROLES
    assert config_b.roles == {"reader": ["b-readers"]}
    assert config_a.project_title == "Alpha"
    # The environment of the process is as it was.
    assert os.environ["STRICTDOC_ROLES"] == json.dumps({"reader": ["global"]})


def test_013_an_archived_project_is_read_only_for_everybody(tmp_path):
    spec = _spec(tmp_path, "alpha", archived=True)
    config = build_project_config(
        spec, output_root=str(tmp_path / "o"), audit_root=None, proxy=True
    )
    assert list(config.roles) == ["reader"]
    assert set(config.roles["reader"]) == {
        "a-admins",
        "a-authors",
        "a-reviewers",
        "a-readers",
    }


def test_014_behind_a_proxy_a_project_needs_roles(tmp_path):
    spec = _spec(tmp_path, "alpha", roles={})
    with pytest.raises(StrictDocException, match="needs roles"):
        build_project_config(
            spec, output_root=str(tmp_path / "o"), audit_root=None, proxy=True
        )
