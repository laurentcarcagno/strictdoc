"""
The home screen of the desktop application: the catalog of the projects.

It is a small web application of its own, served by a LocalServer and
protected by the session middleware of that server. The window opens it when
the user starts the application without a project.

@relation(SDOC-SRS-1229, scope=file)
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from fastapi import FastAPI
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from strictdoc.features.desktop.settings import DesktopSettings, load_settings
from strictdoc.features.i18n import i18n
from strictdoc.features.i18n.languages import DEFAULT_LANGUAGE, set_language
from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    CatalogProject,
    DesktopIdentity,
)
from strictdoc.features.project_catalog.registry import create_catalog

_DESKTOP_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(_DESKTOP_DIR, "assets")
ASSETS_URL = "/assets"

TEMPLATES = Environment(
    loader=FileSystemLoader(os.path.join(_DESKTOP_DIR, "templates")),
    autoescape=select_autoescape(["html"]),
)
i18n.install(TEMPLATES)

# Until the connection of the user exists, nobody is identified.
ANONYMOUS_IDENTITY = DesktopIdentity(username="", display_name="")


@dataclass
class CatalogFolder:
    """A folder of the tree of the catalog: sub-folders, then projects."""

    name: str
    folders: List["CatalogFolder"] = field(default_factory=list)
    projects: List[CatalogProject] = field(default_factory=list)


def set_language_from_environment() -> None:
    """
    Set the language of the interface like a project does: the environment
    variable STRICTDOC_LANGUAGE, or English. Raise ValueError for an unknown
    language.
    """
    set_language(os.environ.get("STRICTDOC_LANGUAGE") or DEFAULT_LANGUAGE)


def build_catalog_tree(projects: List[CatalogProject]) -> CatalogFolder:
    """
    Group the projects in folders by the segments of their display path: the
    project "Satellites/ISIS" is in the folder "Satellites". Folders and
    projects are sorted by name.
    """
    root = CatalogFolder(name="")
    for project_ in projects:
        folder = root
        segments = [
            segment_
            for segment_ in project_.display_path.split("/")
            if len(segment_) > 0
        ]
        for segment_ in segments[:-1]:
            folder = _get_or_add_folder(folder, segment_)
        folder.projects.append(project_)
    _sort_folder(root)
    return root


def create_home_app() -> FastAPI:
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    application.mount(
        ASSETS_URL, StaticFiles(directory=ASSETS_DIR), name="assets"
    )

    @application.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        return render_home(load_settings())

    return application


def render_home(settings: DesktopSettings) -> HTMLResponse:
    """The home page. A catalog that fails is an error shown in the page."""
    projects: List[CatalogProject] = []
    error: Optional[str] = None
    try:
        projects = create_catalog(settings).list_projects(ANONYMOUS_IDENTITY)
    except CatalogError as exception_:
        error = str(exception_)
    output = TEMPLATES.get_template("home.jinja.html").render(
        assets=ASSETS_URL,
        # The first launch: no project has ever been opened.
        has_opened_project=len(settings.project_folders) > 0,
        error=error,
        project_count=len(projects),
        root=build_catalog_tree(projects),
    )
    return HTMLResponse(output, headers={"Cache-Control": "no-store"})


def _get_or_add_folder(parent: CatalogFolder, name: str) -> CatalogFolder:
    for folder_ in parent.folders:
        if folder_.name == name:
            return folder_
    folder = CatalogFolder(name=name)
    parent.folders.append(folder)
    return folder


def _sort_folder(folder: CatalogFolder) -> None:
    folder.folders.sort(key=lambda folder_: folder_.name.casefold())
    folder.projects.sort(key=lambda project_: project_.title.casefold())
    for sub_folder_ in folder.folders:
        _sort_folder(sub_folder_)
