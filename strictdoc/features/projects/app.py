"""
Builds the application of a server with several projects: one application per
project (create_app, as for a single project), the portal, and the dispatcher
in front of them.
"""

import os
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI

from strictdoc.features.projects.dispatcher import ProjectDispatcher
from strictdoc.features.projects.portal import create_portal
from strictdoc.features.projects.registry import (
    ProjectSpec,
    build_project_config,
    validate_specs,
)
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
) -> ProjectDispatcher:
    validate_specs(specs, data_root)
    configs = {}
    for spec_ in specs:
        configs[spec_.slug] = build_project_config(
            spec_,
            output_root=output_root,
            audit_root=audit_root,
            proxy=_proxy(),
        )
    auth_modes = {config_.auth_mode for config_ in configs.values()}
    if len(auth_modes) != 1:
        raise StrictDocException(
            "The projects do not agree on auth_mode: "
            f"{', '.join(sorted(auth_modes))}."
        )
    auth_mode = auth_modes.pop()
    proxy = auth_mode == "proxy"
    first = next(iter(configs.values()))

    apps: Dict[str, FastAPI] = {}
    contexts: Dict[str, Any] = {}
    for spec_ in specs:
        app = create_app(project_config=configs[spec_.slug])
        apps[spec_.slug] = app
        contexts[spec_.slug] = app.state.project_context

    # The portal needs to know who the user is, not what they may do in a
    # project: every group of the registry stands for "reader" here.
    every_group = sorted(
        {g for spec_ in specs for gs in spec_.roles.values() for g in gs}
    )
    portal = PrincipalMiddleware(
        create_portal(
            specs=specs, contexts=contexts, root_host=root_host, proxy=proxy
        ),
        auth_mode=auth_mode,
        trusted_proxies=first.trusted_proxies,
        roles={"reader": every_group} if proxy else {},
    )
    return ProjectDispatcher(root_host=root_host, portal=portal, projects=apps)


def _proxy() -> bool:
    return os.environ.get("STRICTDOC_AUTH_MODE", "none") == "proxy"
