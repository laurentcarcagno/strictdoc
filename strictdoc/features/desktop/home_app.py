"""
The home screen of the desktop application: the catalog of the projects.

It is a small web application of its own, served by a LocalServer and
protected by the session middleware of that server. The window opens it when
the user starts the application without a project.

@relation(SDOC-SRS-1229, scope=file)
@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1231, scope=file)
@relation(SDOC-SRS-1232, scope=file)
@relation(SDOC-SRS-1234, scope=file)
@relation(SDOC-SRS-1235, scope=file)
@relation(SDOC-SRS-1236, scope=file)
@relation(SDOC-SRS-1237, scope=file)
@relation(SDOC-SRS-1240, scope=file)
"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    AbstractSet,
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Union,
)

from fastapi import FastAPI, Form, Request
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.staticfiles import StaticFiles

from strictdoc.features.desktop import window
from strictdoc.features.desktop.commit_author import create_author_provider
from strictdoc.features.desktop.gitlab_client import create_catalog_client
from strictdoc.features.desktop.oauth_gitlab import (
    CALLBACK_PATH,
    GitLabSignIn,
    GitLabUser,
    OAuthError,
    is_sign_in_configured,
    parse_callback_query,
)
from strictdoc.features.desktop.project_opener import (
    JobState,
    ProjectOpener,
)
from strictdoc.features.desktop.project_principals import ProjectPrincipals
from strictdoc.features.desktop.project_servers import (
    ProjectIdentity,
    ProjectServerFactory,
    ProjectServerManager,
)
from strictdoc.features.desktop.secret_store import MemorySecretStore
from strictdoc.features.desktop.session_token import (
    PUBLIC_PATHS_STATE_NAME,
    PublicPathChecker,
)
from strictdoc.features.desktop.settings import DesktopSettings, load_settings
from strictdoc.features.desktop.token_store import SignInStatus, TokenKeeper
from strictdoc.features.desktop.workspace import (
    FolderStatus,
    check_folder,
)
from strictdoc.features.i18n import i18n
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.i18n.languages import DEFAULT_LANGUAGE, set_language
from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    CatalogProject,
    DesktopIdentity,
)
from strictdoc.features.project_catalog.registry import (
    GITLAB_PROVIDER_NAME,
    create_catalog,
)

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


def create_home_app(
    *,
    settings_path: Optional[Path] = None,
    opener: Optional[ProjectOpener] = None,
    sign_in: Optional[GitLabSignIn] = None,
    keeper: Optional[TokenKeeper] = None,
    principals: Optional[ProjectPrincipals] = None,
    server_factory: Optional[ProjectServerFactory] = None,
) -> FastAPI:
    # The tokens of the user. Without a keeper, they stay in memory.
    token_keeper = (
        keeper
        if keeper is not None
        else TokenKeeper(MemorySecretStore(), use_timer=False)
    )
    if principals is None:
        principals = ProjectPrincipals(token_keeper)

    def create_identity(identifier: str) -> ProjectIdentity:
        # The projects of a GitLab catalog belong to the signed-in user, with
        # the role that GitLab gives. The other catalogs have no user for the
        # roles. In both cases, the commits are signed by the signed-in user,
        # and are refused when nobody is signed in.
        if (
            load_settings(settings_path).catalog_provider
            == GITLAB_PROVIDER_NAME
        ):
            return principals.create_identity(identifier)
        return ProjectIdentity(
            principal_provider=None,
            author_provider=create_author_provider(token_keeper),
        )

    project_opener = (
        opener
        if opener is not None
        else ProjectOpener(
            manager=ProjectServerManager(
                server_factory=server_factory,
                settings_path=settings_path,
                identity_factory=create_identity,
            ),
            settings_path=settings_path,
        )
    )
    manager = project_opener.manager
    gitlab_sign_in = (
        sign_in
        if sign_in is not None
        else GitLabSignIn(session_listener=token_keeper.adopt_sign_in)
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        del application
        # The user who signed in at a previous launch is signed in again, with
        # no network call when the access token is still good.
        settings = load_settings(settings_path)
        if is_sign_in_configured(settings):
            token_keeper.restore(
                gitlab_url=settings.gitlab_url.strip(),
                client_id=settings.oauth_client_id.strip(),
            )
        yield
        token_keeper.close()
        # The web servers of the projects belong to the home server: they end
        # with it.
        manager.stop_all()

    application = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    application.mount(
        ASSETS_URL, StaticFiles(directory=ASSETS_DIR), name="assets"
    )

    # The callback of GitLab comes from another site: the browser does not
    # send the session cookie. The middleware lets it pass, only with the state
    # of a sign-in that this application started and that waits.
    public_paths: Dict[str, PublicPathChecker] = {
        CALLBACK_PATH: lambda query_: _is_callback_expected(
            gitlab_sign_in, query_
        )
    }
    setattr(application.state, PUBLIC_PATHS_STATE_NAME, public_paths)

    @application.get("/", response_class=HTMLResponse)
    def home() -> HTMLResponse:
        settings = load_settings(settings_path)
        return render_home(
            settings,
            running_identifiers=manager.get_open_identifiers(),
            gitlab_client=create_catalog_client(settings, token_keeper),
            identity=_get_identity(token_keeper),
            user=_get_user(token_keeper),
            sign_in_status=token_keeper.status,
            is_sign_in_refused=token_keeper.is_refused,
            storage_error=token_keeper.storage_error,
        )

    @application.post("/sign-in")
    def start_sign_in(request: Request) -> Response:
        port = request.url.port
        if port is None:
            return _render_page(
                "message.jinja.html",
                notice=gettext("The address of the home screen is not known."),
            )
        try:
            authorization_url = gitlab_sign_in.start(
                settings=load_settings(settings_path), port=port
            )
        except OAuthError as exception_:
            return _render_page("message.jinja.html", notice=str(exception_))
        return RedirectResponse(authorization_url, status_code=303)

    @application.post("/sign-out")
    def sign_out() -> Response:
        """
        End the session: the tokens are forgotten (the record of the keyring,
        the variable of Git), and so are the roles. The servers of the projects
        stop: they would keep the documents of the user on the screen.
        """
        token_keeper.sign_out()
        principals.clear()
        manager.stop_servers()
        return RedirectResponse("/", status_code=303)

    @application.get(CALLBACK_PATH)
    def finish_sign_in(request: Request) -> Response:
        parameters = parse_callback_query(
            {
                name_: request.query_params.getlist(name_)
                for name_ in request.query_params
            }
        )
        state = parameters.get("state", "")
        if "error" in parameters:
            # The user refused, or GitLab could not sign the user in.
            gitlab_sign_in.refuse(state)
            return _render_page(
                "message.jinja.html",
                notice=gettext("GitLab refused the sign-in (%(reason)s).")
                % {"reason": parameters["error"][:80]},
            )
        try:
            gitlab_sign_in.complete(
                state=state, code=parameters.get("code", "")
            )
        except OAuthError as exception_:
            return _render_page("message.jinja.html", notice=str(exception_))
        # The answer is the page that GitLab called back, from another site.
        # The page goes to the home screen: that navigation is of the same
        # site, so the browser sends the session cookie again.
        return _render_page("signed_in.jinja.html")

    @application.post("/projects/open")
    def open_project(identifier: str = Form(...)) -> Response:
        settings = load_settings(settings_path)
        project = _find_project(
            settings,
            identifier,
            keeper=token_keeper,
            principals=principals,
            manager=manager,
        )
        if isinstance(project, HTMLResponse):
            return project
        folder = settings.project_folders.get(identifier)
        if folder is None:
            return _choose_folder(project_opener, project)
        if not os.path.isdir(folder):
            return _render_ask_folder(
                project,
                notice=gettext(
                    "The folder %(folder)s of this project no longer exists. "
                    "Choose a new folder."
                )
                % {"folder": folder},
            )
        # The server of the project runs: back to it, at once.
        open_url = manager.get_open_url(identifier, folder)
        if open_url is not None:
            return RedirectResponse(open_url, status_code=303)
        return _use_folder(project_opener, project, folder)

    @application.post("/projects/folder")
    def choose_project_folder(
        identifier: str = Form(...), folder: str = Form("")
    ) -> Response:
        settings = load_settings(settings_path)
        project = _find_project(
            settings,
            identifier,
            keeper=token_keeper,
            principals=principals,
            manager=manager,
        )
        if isinstance(project, HTMLResponse):
            return project
        folder = folder.strip()
        if len(folder) == 0:
            if window.is_window_open():
                return _choose_folder(project_opener, project)
            return _render_ask_folder(
                project, notice=gettext("Enter the path of a folder.")
            )
        return _use_folder(
            project_opener, project, os.path.abspath(os.path.expanduser(folder))
        )

    @application.get("/jobs/{job_id}")
    def show_job(job_id: str) -> Response:
        job = project_opener.get_job(job_id)
        if job is None:
            return RedirectResponse("/", status_code=303)
        return _render_page(
            "open_project.jinja.html", job=job, project_title=job.project_title
        )

    @application.get("/jobs/{job_id}/status")
    def get_job_status(job_id: str) -> Response:
        job = project_opener.get_job(job_id)
        if job is None:
            return JSONResponse(
                {"state": JobState.FAILED.value}, status_code=404
            )
        return JSONResponse(
            {
                "state": job.state.value,
                "step": job.step.value,
                "message": job.message,
                "url": job.url,
            },
            headers={"Cache-Control": "no-store"},
        )

    return application


def render_home(
    settings: DesktopSettings,
    running_identifiers: AbstractSet[str] = frozenset(),
    user: Optional[GitLabUser] = None,
    sign_in_status: SignInStatus = SignInStatus.SIGNED_OUT,
    is_sign_in_refused: bool = False,
    storage_error: Optional[str] = None,
    gitlab_client: Optional[Any] = None,
    identity: DesktopIdentity = ANONYMOUS_IDENTITY,
) -> HTMLResponse:
    """
    The home page. A catalog that fails is an error shown in the page. The
    projects whose server runs are marked. The user that signed in is named;
    without one, the page offers the sign-in when the settings allow it. A
    user whose access token has ended with no network is told that the
    application is offline.
    """
    projects: List[CatalogProject] = []
    error: Optional[str] = None
    # The catalog of GitLab lists what the user can see: it needs the user.
    is_sign_in_required = (
        settings.catalog_provider == GITLAB_PROVIDER_NAME
        and gitlab_client is None
    )
    # The sign-in is for a user who is signed out, or whose sign-in is for
    # another GitLab than the one of the settings.
    is_sign_in_offered = is_sign_in_configured(settings) and (
        user is None or is_sign_in_required
    )
    if not is_sign_in_required:
        try:
            projects = create_catalog(settings, gitlab_client).list_projects(
                identity
            )
        except CatalogError as exception_:
            error = str(exception_)
    output = TEMPLATES.get_template("home.jinja.html").render(
        assets=ASSETS_URL,
        # The first launch: no project has ever been opened.
        has_opened_project=len(settings.project_folders) > 0,
        error=error,
        is_sign_in_required=is_sign_in_required,
        project_count=len(projects),
        root=build_catalog_tree(projects),
        running_identifiers=running_identifiers,
        user=user,
        is_offline=sign_in_status is SignInStatus.OFFLINE,
        is_sign_in_refused=is_sign_in_refused and user is None,
        storage_error=storage_error,
        is_sign_in_offered=is_sign_in_offered,
    )
    return HTMLResponse(output, headers={"Cache-Control": "no-store"})


def _get_identity(token_keeper: TokenKeeper) -> DesktopIdentity:
    user = _get_user(token_keeper)
    if user is None:
        return ANONYMOUS_IDENTITY
    return DesktopIdentity(
        username=user.username, display_name=user.display_name
    )


def _get_user(token_keeper: TokenKeeper) -> Optional[GitLabUser]:
    session = token_keeper.session
    return session.user if session is not None else None


def _is_callback_expected(
    sign_in: GitLabSignIn, query: Dict[str, List[str]]
) -> bool:
    states = query.get("state", [])
    return len(states) == 1 and sign_in.is_valid_state(states[0])


def _find_project(
    settings: DesktopSettings,
    identifier: str,
    *,
    keeper: TokenKeeper,
    principals: ProjectPrincipals,
    manager: ProjectServerManager,
) -> Union[CatalogProject, HTMLResponse]:
    """
    The project of the catalog, or the page that says it cannot be used.

    The catalog is read at each opening, and the role that it gives goes to the
    server of the project. A project that the user cannot see any more (the
    rights were removed) is not opened, and its server, if it runs, stops.
    """
    gitlab_client = create_catalog_client(settings, keeper)
    if (
        settings.catalog_provider == GITLAB_PROVIDER_NAME
        and gitlab_client is None
    ):
        return _render_page(
            "message.jinja.html",
            notice=gettext("Sign in to see your projects.")
            if is_sign_in_configured(settings)
            else gettext(
                "The GitLab settings are incomplete: the address of GitLab "
                "and the OAuth application are needed."
            ),
        )
    try:
        projects = create_catalog(settings, gitlab_client).list_projects(
            _get_identity(keeper)
        )
    except CatalogError as exception_:
        return _render_page("message.jinja.html", notice=str(exception_))
    for project_ in projects:
        if project_.identifier == identifier:
            principals.set_role(identifier, project_.role)
            return project_
    principals.set_role(identifier, None)
    manager.stop_project(identifier)
    if identifier in settings.project_folders:
        notice = gettext("You no longer have access to this project.")
    else:
        notice = gettext("The project is not in the catalog.")
    return _render_page("message.jinja.html", notice=notice)


def _choose_folder(opener: ProjectOpener, project: CatalogProject) -> Response:
    """The dialog of the window, or else the field of the screen."""
    if not window.is_window_open():
        return _render_ask_folder(project)
    chosen = window.choose_folder(str(Path.home()))
    if chosen is None:
        # The user cancelled the dialog: back to the catalog.
        return RedirectResponse("/", status_code=303)
    return _use_folder(opener, project, os.path.abspath(chosen))


def _use_folder(
    opener: ProjectOpener, project: CatalogProject, folder: str
) -> Response:
    """Check the folder, then clone into it or use it, and open the project."""
    check = check_folder(folder, project.clone_url)
    if check.status is FolderStatus.REFUSED:
        return _render_ask_folder(
            project, notice=check.reason, folder_value=folder
        )
    job = opener.start_job(
        project,
        folder,
        is_clone_needed=check.status is FolderStatus.EMPTY,
    )
    return RedirectResponse(f"/jobs/{job.job_id}", status_code=303)


def _render_ask_folder(
    project: CatalogProject,
    *,
    notice: Optional[str] = None,
    folder_value: str = "",
) -> HTMLResponse:
    return _render_page(
        "ask_folder.jinja.html",
        project=project,
        notice=notice,
        folder_value=folder_value,
        has_dialog=window.is_window_open(),
    )


def _render_page(template_name: str, **context: object) -> HTMLResponse:
    output = TEMPLATES.get_template(template_name).render(
        assets=ASSETS_URL, **context
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
