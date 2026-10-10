import os
from pathlib import Path
from typing import List

from fastapi.testclient import TestClient

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.server.app import create_app
from strictdoc.server.helpers.hierarchical_rw_lock_manager import (
    HierarchicalRWLockManager,
)
from strictdoc.server.project_context import ProjectContext

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent


def _project_config(root: Path, name: str = "project") -> ProjectConfig:
    input_path = root / name / "input"
    input_path.mkdir(parents=True)
    (input_path / "document.sdoc").write_text(
        (PATH_TO_THIS_TEST_FOLDER / "document.sdoc").read_text(encoding="utf8"),
        encoding="utf8",
    )
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(input_path),
        output_path=str(root / name / "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    return ProjectConfigLoader.load_using_server_config(server_config)


def _document(context: ProjectContext) -> SDocDocument:
    return context.export_action.traceability_index.document_tree.document_list[
        0
    ]


def test_001_a_context_holds_the_state_of_its_project(tmp_path):
    project_config = _project_config(tmp_path)
    context = ProjectContext.create(project_config)

    assert context.project_config is project_config
    assert project_config.is_running_on_server is True
    assert (
        len(
            context.export_action.traceability_index.document_tree.document_list
        )
        == 1
    )
    assert context.revisions["unknown"] == 0
    assert context.env() is context.html_templates.jinja_environment()
    assert context.document_watcher is None
    assert (
        "project_statistics.html" in context.server_features_by_screen_filename
    )


def test_002_two_contexts_do_not_share_state(tmp_path):
    first = ProjectContext.create(_project_config(tmp_path, "first"))
    second = ProjectContext.create(_project_config(tmp_path, "second"))

    assert first.export_action is not second.export_action
    assert first.revisions is not second.revisions
    assert first.connections is not second.connections
    assert first.html_templates is not second.html_templates
    assert (
        first.project_config.export_output_html_root
        != second.project_config.export_output_html_root
    )

    first.revisions["a5c6b14d5ee443149687fb9be69a7ede"] += 1
    assert second.revisions["a5c6b14d5ee443149687fb9be69a7ede"] == 0
    assert _document(first) is not _document(second)


class _FakeWatcher:
    def __init__(self) -> None:
        self.inhibited: List[str] = []

    def inhibit_next_change(self, path: str) -> None:
        self.inhibited.append(path)


def test_003_writing_a_document_inhibits_the_watcher_and_writes_the_file(
    tmp_path,
):
    context = ProjectContext.create(_project_config(tmp_path))
    watcher = _FakeWatcher()
    context.document_watcher = watcher  # type: ignore[assignment]
    document = _document(context)
    assert document.meta is not None
    path = document.meta.input_doc_full_path

    context.write_document_to_file(document)

    assert watcher.inhibited == [path]
    assert "The system shall start." in Path(path).read_text(encoding="utf8")


def test_004_writing_without_a_watcher_still_writes(tmp_path):
    context = ProjectContext.create(_project_config(tmp_path))
    document = _document(context)
    assert document.meta is not None
    os.remove(document.meta.input_doc_full_path)

    context.write_document_to_file(document)

    assert os.path.isfile(document.meta.input_doc_full_path)


def test_005_rebuild_index_replaces_the_index_or_reports_the_error(tmp_path):
    context = ProjectContext.create(_project_config(tmp_path))
    lock_manager = HierarchicalRWLockManager()
    before = context.export_action.traceability_index

    assert context.rebuild_index(lock_manager) is None
    assert context.export_action.traceability_index is not before

    document = _document(context)
    assert document.meta is not None
    Path(document.meta.input_doc_full_path).write_text(
        "[DOCUMENT]\nTITLE: Broken\n\n[REQUIREMENT\nSTATEMENT: x\n",
        encoding="utf8",
    )
    kept = context.export_action.traceability_index
    error = context.rebuild_index(lock_manager)
    assert error is not None and len(error) > 0
    assert context.export_action.traceability_index is kept


def test_006_the_application_serves_the_pages_of_its_context(tmp_path):
    client = TestClient(create_app(project_config=_project_config(tmp_path)))
    response = client.get("/input/document.html")
    assert response.status_code == 200
    assert "The system shall start." in response.text
