"""
The state of one project in the web server.

Everything that belongs to one project (its traceability index, its
templates, its writer, its revision counters and its connected browsers) is
held here instead of in the closure of create_main_router(), so that the
routers can later work for several projects, each with its own context.
"""

import asyncio
from collections import defaultdict
from typing import Dict, List, Optional

from starlette.websockets import WebSocket

from strictdoc.backend.markdown.writer import SDMarkdownWriter
from strictdoc.backend.sdoc.errors.document_tree_error import DocumentTreeError
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.writer import SDWriter
from strictdoc.core.feature import Feature
from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index_builder import TraceabilityIndexBuilder
from strictdoc.export.html.html_generator import HTMLGenerator
from strictdoc.export.html.html_templates import HTMLTemplates, JinjaEnvironment
from strictdoc.features.export.export_action import ExportAction
from strictdoc.features.git_config.committer import GitCommitter
from strictdoc.features.git_config.setup import create_committer
from strictdoc.helpers.parallelizer import NullParallelizer
from strictdoc.server.document_watcher import DocumentWatcher
from strictdoc.server.helpers.hierarchical_rw_lock_manager import (
    HierarchicalRWLockManager,
)


# Websockets solution based on:
# https://fastapi.tiangolo.com/advanced/websockets/
class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        async with self._lock:
            connections = list(self.active_connections)
        for connection in connections:
            await connection.send_text(message)


class ProjectContext:
    """The state of one project served by the web server."""

    def __init__(self, project_config: ProjectConfig) -> None:
        self.project_config: ProjectConfig = project_config
        self.parallelizer = NullParallelizer()

        # This dictionary is used to track conflicts between concurrently
        # edited versions of the same nodes. If a saved node has a version
        # that is older than one tracked in this dictionary, StrictDoc raises
        # a validation to a user.
        # Type signature: [MID, version number]
        self.revisions: Dict[str, int] = defaultdict(int)

        project_config.is_running_on_server = True

        # Commits what is written, when the project option "git" is on.
        self.git_committer: Optional[GitCommitter] = create_committer(
            project_config
        )

        self.export_action = ExportAction(
            project_config=project_config,
            parallelizer=self.parallelizer,
        )

        self.is_small_project: bool = (
            self.export_action.traceability_index.is_small_project()
        )

        self.html_templates: HTMLTemplates = HTMLTemplates.create(
            project_config=project_config,
            enable_caching=not self.is_small_project,
            strictdoc_last_update=self.export_action.traceability_index.strictdoc_last_update,
        )

        self.html_generator = HTMLGenerator(project_config, self.html_templates)

        # Server screens contributed by built-in Features (e.g.
        # ProjectStatisticsFeature), keyed by the screen_filename() each one
        # owns. Built from *all* built-in Features regardless of activation
        # (not just project_config.get_features(), which only resolves
        # activated ones) so that a request for a known-but-not-activated
        # screen can be told apart from an unknown path: the former must
        # still return 412, the latter 404. Dispatched from within
        # generate_document(), so every Feature-contributed screen still goes
        # through the same shared caching/locking machinery as every other
        # document.
        self.server_features_by_screen_filename: Dict[str, Feature] = {
            feature_.screen_filename(): feature_
            for feature_ in ProjectConfig._builtin_features_by_handle().values()
            if feature_.supports_server()
        }

        self.html_generator.export_strictdoc_assets(
            project_config=project_config,
            html_templates=self.html_templates,
            export_output_html_root=project_config.export_output_html_root,
        )

        self.html_generator.export_project_assets(
            traceability_index=self.export_action.traceability_index,
            export_output_html_root=project_config.export_output_html_root,
        )

        self.sdoc_writer = SDWriter(project_config)

        # The browsers that are connected to this project (live reload).
        self.connections = ConnectionManager()

        # Set by the router when the project watches its files.
        self.document_watcher: Optional[DocumentWatcher] = None

    @staticmethod
    def create(project_config: ProjectConfig) -> "ProjectContext":
        return ProjectContext(project_config)

    def env(self) -> JinjaEnvironment:
        return self.html_templates.jinja_environment()

    def write_document_to_file(self, document: SDocDocument) -> None:
        """
        FIXME: The writer dispatch below is hardcoded to ".md"/".markdown"
        vs. everything else, not derived from project_config.formats /
        Format.supports_edit(). Document creation now accepts any editable
        format's extension (see ProjectConfig.get_editable_document_extensions()),
        so a third editable format would pass creation validation but get
        silently mis-written here.
        """

        assert isinstance(document, SDocDocument)

        # Inhibit before writing so the watcher's debounce always fires into
        # an already-suppressed state — no race window between write and hash.
        if document.meta is not None and self.document_watcher is not None:
            self.document_watcher.inhibit_next_change(
                document.meta.input_doc_full_path
            )

        if (
            document.meta is not None
            and document.meta.input_doc_full_path.lower().endswith(
                (".md", ".markdown")
            )
        ):
            SDMarkdownWriter.write_to_file(
                document, line_width=self.project_config.document_line_width
            )
        else:
            self.sdoc_writer.write_to_file(document)

        if self.git_committer is not None and document.meta is not None:
            self.git_committer.on_document_written(
                document.meta.input_doc_full_path
            )

    def rebuild_index(
        self, lock_manager: HierarchicalRWLockManager
    ) -> Optional[str]:
        """
        Builds the traceability index again, for example after a file changed.
        Returns None, or the message of the error that stopped the build.
        """
        try:
            with lock_manager.acquire_global_write():
                self.export_action.traceability_index = (
                    TraceabilityIndexBuilder.create(
                        project_config=self.project_config,
                        parallelizer=self.parallelizer,
                    )
                )
            return None
        except DocumentTreeError as document_tree_error:
            return document_tree_error.to_print_message()
        except Exception as build_error:  # noqa: BLE001
            return str(build_error)
