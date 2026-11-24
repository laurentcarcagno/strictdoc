"""
The publication of a version of the project, in the desktop application.

A version is a name that marks the whole project at one moment: a draft
(A1, A2, ...) or a major version (A, then B). The names follow
git_config/versioning.py, and the user reads them as versions.

A version is published only when the project is as the server has it, so that
the version means the same to everybody:

- the user is online (the version tags of the server are read first, so that
  the next name is the next one of the server too);
- no merge waits for a choice;
- no change waits to be sent, and the server has nothing that the project
  lacks (the commit that the version marks is already on the server);
- the files are saved, and the index is the one of the files.

Each refusal has a text for the user. The version is created on the computer
under the exclusion of the project, then sent alone (the tag, with the
credential of GitAccess, without force) outside of it. If it cannot be sent, or
if the server has a version of that name already (another administrator
published at the same time), the version of the computer is removed and the
user is told: no version stays on the computer without being on the server.

Only an administrator publishes (permissions.can_publish).

@relation(SDOC-SRS-1249, scope=file)
@relation(SDOC-SRS-1250, scope=file)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Form, Request
from starlette.responses import HTMLResponse, Response

from strictdoc.features.desktop.git_access import DesktopGitService, GitAccess
from strictdoc.features.desktop.permissions import can_publish
from strictdoc.features.desktop.project_gate import ProjectGate
from strictdoc.features.desktop.project_runtime import ProjectRuntime
from strictdoc.features.git_config.git_service import (
    Author,
    GitServiceError,
)
from strictdoc.features.git_config.versioning import latest_valid_tag
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.roles.router import get_principal
from strictdoc.server.project_context import ProjectContext

logger = logging.getLogger(__name__)

PUBLISH_PATH = "/actions/git/version_document"
KIND_DRAFT = "draft"
KIND_MAJOR = "major"
HTTP_PRECONDITION_FAILED = 412


@dataclass(frozen=True)
class PublicationPlan:
    """What can be published now, or why nothing can."""

    # "" when a version can be published.
    refusal: str = ""
    latest: str = ""
    next_draft: str = ""
    # "" when there is no draft to freeze yet.
    next_major: str = ""


def plan_publication(
    folder: str,
    *,
    git_access: GitAccess,
    gate: ProjectGate,
    runtime: ProjectRuntime,
    kind: str = "",
    author: Optional[Author] = None,
) -> "tuple[PublicationPlan, str]":
    """
    Read the tags of the server, check the conditions, and give the next
    names. With a kind ("draft" or "major"), the version is also created on the
    computer, in the same exclusion as the checks, and its name is returned
    with the plan ("" when nothing was created).
    """
    service = DesktopGitService(folder, git_access)
    try:
        if service.is_operation_in_progress(folder):
            return PublicationPlan(get_merge_refusal()), ""
        try:
            service.fetch_tags(folder)
        except GitServiceError:
            return PublicationPlan(get_offline_refusal()), ""
        with gate.hold():
            plan = _check_conditions(service, folder, runtime)
            if plan.refusal != "" or kind == "":
                return plan, ""
            name = plan.next_major if kind == KIND_MAJOR else plan.next_draft
            if name == "":
                return (
                    PublicationPlan(
                        gettext("A draft version is needed first."),
                        plan.latest,
                        plan.next_draft,
                        plan.next_major,
                    ),
                    "",
                )
            service.create_tag(folder, name, author)
            return plan, name
    except GitServiceError as error:
        logger.warning("The version could not be prepared: %s", error)
        return PublicationPlan(get_failure_refusal()), ""


def send_version(
    folder: str, name: str, *, git_access: GitAccess
) -> "tuple[bool, str]":
    """
    Send the version that was created, alone. It returns (True, "") when the
    server has it now, and (False, the text for the user) when it does not: the
    version of the computer is then removed.
    """
    service = DesktopGitService(folder, git_access)
    message = ""
    try:
        if service.push_only_tag(folder, name):
            return True, ""
        message = get_concurrent_refusal()
    except GitServiceError as error:
        logger.warning("The version could not be sent: %s", error)
        message = gettext(
            "The version could not be sent to the server, so it is not "
            "published. Try again when the connection is back."
        )
    try:
        service.delete_local_tag(folder, name)
    except GitServiceError:
        logger.exception("The version %s could not be removed.", name)
    return False, message


def get_merge_refusal() -> str:
    return gettext(
        "Choose which version to keep for the items that you and a colleague "
        "changed, then publish the version."
    )


def get_offline_refusal() -> str:
    return gettext(
        "A version can be published only when the server answers. Check your "
        "network and try again."
    )


def get_concurrent_refusal() -> str:
    return gettext(
        "Another administrator has just published this version. Update the "
        "project, then publish again."
    )


def get_failure_refusal() -> str:
    return gettext(
        "The version could not be prepared for now. Nothing was published."
    )


def create_publish_routes(
    *,
    context: ProjectContext,
    folder: str,
    git_access: GitAccess,
    gate: ProjectGate,
    runtime: ProjectRuntime,
) -> APIRouter:
    """
    The routes of the publication, which take the place of the ones of the web
    server for the version of a document (the same paths, the same role: an
    administrator). The version is the one of the whole project.
    """
    router = APIRouter()

    def render(
        request: Request,
        plan: PublicationPlan,
        *,
        message: str = "",
        done: str = "",
    ) -> Response:
        output = context.env().render_template_as_markup(
            "stream_publish.jinja.html",
            plan=plan,
            message=message,
            done=done,
            can_publish=can_publish(get_principal(request).role),
        )
        return HTMLResponse(
            content=output,
            headers={"Content-Type": "text/vnd.turbo-stream.html"},
        )

    def plan(
        kind: str = "", author: Optional[Author] = None
    ) -> "tuple[PublicationPlan, str]":
        return plan_publication(
            folder,
            git_access=git_access,
            gate=gate,
            runtime=runtime,
            kind=kind,
            author=author,
        )

    @router.get(PUBLISH_PATH, response_class=Response)
    def publish_dialog(request: Request, for_mid: str = "") -> Response:
        del for_mid
        found, _ = plan()
        return render(request, found)

    @router.post(PUBLISH_PATH, response_class=Response)
    def publish(request: Request, kind: str = Form(KIND_DRAFT)) -> Response:
        committer = context.git_committer
        if committer is None or not can_publish(get_principal(request).role):
            return render(
                request,
                PublicationPlan(),
                message=gettext("Only an administrator publishes a version."),
            )
        if kind not in (KIND_DRAFT, KIND_MAJOR):
            kind = KIND_DRAFT
        # Nobody signed in: refused like every commit (409).
        author = committer.author_provider()
        found, name = plan(kind, author)
        if name == "":
            return render(request, found, message=found.refusal)
        is_sent, message = send_version(folder, name, git_access=git_access)
        if not is_sent:
            return render(request, found, message=message)
        return render(request, found, done=name)

    return router


def _check_conditions(
    service: DesktopGitService, folder: str, runtime: ProjectRuntime
) -> PublicationPlan:
    """Every condition that a version needs. Call it with the gate."""
    if runtime.is_index_outdated:
        return PublicationPlan(
            gettext(
                "The project files cannot be read. Repair them, then publish "
                "the version."
            )
        )
    if len(service.list_changed_paths(folder)) > 0:
        return PublicationPlan(
            gettext(
                "Some changes are not saved yet. Save them, then publish the "
                "version."
            )
        )
    unsent = service.read_unsent_commits(folder)
    if unsent is not None and unsent.count > 0:
        return PublicationPlan(
            gettext(
                "Your changes are not shared yet. Wait until they are sent, "
                "then publish the version."
            )
        )
    branch = service.current_branch(folder)
    if service.remote_branch_exists(folder, branch):
        behind, _ = service.ahead_behind(folder, branch)
        if behind > 0:
            return PublicationPlan(
                gettext(
                    "Your colleagues shared changes that you do not have "
                    "yet. Update the project first."
                )
            )
    tags = service.list_tags(folder)
    try:
        next_major = service.next_major_tag(folder)
    except GitServiceError:
        next_major = ""
    return PublicationPlan(
        latest=latest_valid_tag(tags),
        next_draft=service.next_intermediate_tag(folder),
        next_major=next_major,
    )
