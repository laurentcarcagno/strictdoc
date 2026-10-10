"""
Builds the application of a server with several projects: one application per
project (create_app, as for a single project), the portal, and the dispatcher
in front of them.
"""

import os
from typing import Callable, List, Optional, Sequence

from fastapi import FastAPI

from strictdoc.features.projects.directory import KeycloakDirectory
from strictdoc.features.projects.dispatcher import ProjectDispatcher
from strictdoc.features.projects.manager import ProjectManager
from strictdoc.features.projects.portal import create_portal
from strictdoc.features.projects.registry import (
    ProjectSpec,
    validate_specs,
)
from strictdoc.features.projects.store import ProjectStore
from strictdoc.features.roles.middleware import PrincipalMiddleware
from strictdoc.helpers.exception import StrictDocException


def create_projects_app(
    *,
    create_app: Callable[..., FastAPI],
    specs: List[ProjectSpec],
    root_host: str,
    output_root: str,
    audit_root: Optional[str] = None,
    data_root: Optional[str] = None,
    store: Optional[ProjectStore] = None,
    platform_admin_groups: Optional[Sequence[str]] = None,
    directory: Optional[KeycloakDirectory] = None,
) -> ProjectDispatcher:
    validate_specs(specs, data_root)
    manager = ProjectManager(
        create_app=create_app,
        store=store or ProjectStore(os.path.join(output_root, "projects.json")),
        specs=specs,
        output_root=output_root,
        audit_root=audit_root,
        data_root=data_root,
        proxy=_proxy(),
        platform_admin_groups=platform_admin_groups,
        directory=directory,
    )
    for spec_ in specs:
        manager.build(spec_)
    configs = [
        context_.project_config for context_ in manager.contexts.values()
    ]
    auth_modes = {config_.auth_mode for config_ in configs}
    if len(auth_modes) != 1:
        raise StrictDocException(
            "The projects do not agree on auth_mode: "
            f"{', '.join(sorted(auth_modes))}."
        )
    auth_mode = auth_modes.pop()
    proxy = auth_mode == "proxy"
    manager.proxy = proxy
    first_config = configs[0]
    manager.load_stored_projects()

    # The portal needs to know who the user is, not what they may do in a
    # project: every group of the registry stands for "reader" here.
    every_group = sorted(
        {g for spec_ in specs for gs in spec_.roles.values() for g in gs}
        - set(manager.admin_groups)
    )
    portal_roles = {}
    if every_group:
        portal_roles["reader"] = every_group
    if manager.admin_groups:
        portal_roles["administrator"] = list(manager.admin_groups)
    portal = PrincipalMiddleware(
        create_portal(manager=manager, root_host=root_host),
        auth_mode=auth_mode,
        trusted_proxies=first_config.trusted_proxies,
        roles=portal_roles if proxy else {},
        # Members that no group names open the portal too.
        member_role=_reader if proxy else None,
    )
    dispatcher = ProjectDispatcher(
        root_host=root_host, portal=portal, projects=manager.apps
    )
    manager.dispatcher = dispatcher
    return dispatcher


def _reader(_user: str) -> str:
    return "reader"


def _proxy() -> bool:
    return os.environ.get("STRICTDOC_AUTH_MODE", "none") == "proxy"
