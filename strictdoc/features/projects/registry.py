"""
The registry of the projects that one server process serves.

A Python file, like strictdoc_config.py, defines ``create_projects()``:

    def create_projects():
        return [
            ProjectSpec(
                slug="revalto",
                title="Revalto flight software",
                path="/data/revalto",
                roles={"administrator": ["revalto-admins"],
                       "author": ["revalto-authors"],
                       "reviewer": ["revalto-reviewers"],
                       "reader": ["revalto-readers"]},
            ),
        ]

Each project is served at <slug>.<root host>; the root host shows the portal.
"""

import importlib.util
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import (
    ProjectConfig,
    ProjectConfigLoader,
    ProjectFeature,
)
from strictdoc.features.roles.roles import validate_roles
from strictdoc.helpers.exception import StrictDocException

SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")


@dataclass
class ProjectSpec:
    slug: str
    title: str
    # The folder of the project (its documents).
    path: str
    # A strictdoc_config.py or strictdoc.toml; default: the one in the folder.
    config: Optional[str] = None
    # The groups of each role, as the option `roles` of a project.
    roles: Dict[str, List[str]] = field(default_factory=dict)
    # Read-only for everybody.
    archived: bool = False


def load_registry(
    path: str, data_root: Optional[str] = None
) -> List[ProjectSpec]:
    """The validated specs of a registry file. Raises StrictDocException."""
    if not os.path.isfile(path):
        raise StrictDocException(f"Project registry not found: {path}.")
    specification = importlib.util.spec_from_file_location(
        "strictdoc_projects_registry", path
    )
    if specification is None or specification.loader is None:
        raise StrictDocException(f"Could not load the registry: {path}.")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    create_projects = getattr(module, "create_projects", None)
    if create_projects is None:
        raise StrictDocException(
            f"The registry {path} has no create_projects() function."
        )
    specs = list(create_projects())
    base = os.path.dirname(os.path.abspath(path))
    for spec_ in specs:
        if isinstance(spec_, ProjectSpec) and not os.path.isabs(spec_.path):
            spec_.path = os.path.join(base, spec_.path)
    validate_specs(specs, data_root)
    return specs


def validate_specs(
    specs: List[ProjectSpec], data_root: Optional[str] = None
) -> None:
    if len(specs) == 0:
        raise StrictDocException("The registry lists no project.")
    seen: Dict[str, ProjectSpec] = {}
    paths: Dict[str, str] = {}
    root = os.path.realpath(data_root) if data_root else None
    for spec_ in specs:
        if not isinstance(spec_, ProjectSpec):
            raise StrictDocException(
                f"The registry holds '{spec_}', which is not a ProjectSpec."
            )
        if SLUG_PATTERN.match(spec_.slug) is None:
            raise StrictDocException(
                f"Invalid slug '{spec_.slug}': use 1 to 32 characters among "
                "lower case letters, digits and '-', not starting or ending "
                "with '-'."
            )
        if spec_.slug in seen:
            raise StrictDocException(f"The slug '{spec_.slug}' is used twice.")
        seen[spec_.slug] = spec_
        if not os.path.isdir(spec_.path):
            raise StrictDocException(
                f"Project '{spec_.slug}': the folder does not exist: "
                f"{spec_.path}."
            )
        real_path = os.path.realpath(spec_.path)
        if root is not None and os.path.commonpath([root, real_path]) != root:
            raise StrictDocException(
                f"Project '{spec_.slug}': {spec_.path} is outside the data "
                f"root {data_root}."
            )
        if real_path in paths:
            raise StrictDocException(
                f"Projects '{paths[real_path]}' and '{spec_.slug}' use the "
                "same folder."
            )
        paths[real_path] = spec_.slug
        if spec_.config is not None and not os.path.isfile(spec_.config):
            raise StrictDocException(
                f"Project '{spec_.slug}': the configuration file does not "
                f"exist: {spec_.config}."
            )
        try:
            validate_roles(spec_.roles)
        except ValueError as exception_:
            raise StrictDocException(
                f"Project '{spec_.slug}': roles: {exception_}"
            ) from exception_


def build_project_config(
    spec: ProjectSpec,
    *,
    output_root: str,
    audit_root: Optional[str],
    proxy: bool,
) -> ProjectConfig:
    """
    The configuration of one project. Its output (caches, generated files) and
    its audit log are in folders of its own, and its roles are its own: the
    environment variables of a single-project deployment (STRICTDOC_ROLES,
    STRICTDOC_AUDIT_DIR) do not apply to a project of a registry, except that
    the audit variable names the folder that holds one folder per project.
    """
    roles = validate_roles(spec.roles)
    if spec.archived and len(roles) > 0:
        every_group = sorted({g for groups in roles.values() for g in groups})
        roles = {"reader": every_group}
    if proxy and len(roles) == 0:
        raise StrictDocException(
            f"Project '{spec.slug}': behind a login proxy it needs roles."
        )
    # The configuration reads its roles from this variable first; the roles of
    # the spec are the ones of the project, whatever the deployment set.
    saved_roles = os.environ.get("STRICTDOC_ROLES")
    os.environ["STRICTDOC_ROLES"] = json.dumps(roles)
    try:
        config = ProjectConfigLoader.load_using_server_config(
            ServerCommandConfig(
                debug=False,
                command="server",
                input_path=spec.path,
                output_path=os.path.join(output_root, spec.slug),
                config=spec.config,
                reload=False,
                host=None,
                port=None,
            )
        )
    finally:
        if saved_roles is None:
            del os.environ["STRICTDOC_ROLES"]
        else:
            os.environ["STRICTDOC_ROLES"] = saved_roles
    # Word import and export are on in every project, whatever its file says.
    if ProjectFeature.DOCX not in config.project_features:
        config.project_features.append(ProjectFeature.DOCX)
    config.project_title = spec.title
    config.roles = roles
    audit_dir = os.path.join(audit_root or output_root, spec.slug)
    os.makedirs(audit_dir, exist_ok=True)
    config.audit_dir = audit_dir
    return config
