"""
The list of the applicable documents at the start of a fresh Word export.
"""

from typing import Any, List

from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    ExportInfoTable,
    ExportItem,
    ExportSection,
)
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.hierarchy.levels import input_info
from strictdoc.features.hierarchy.source import IndexReferenceSource

TITLE = "Applicable documents"
HEADER = ["Ref", "Title", "Reference", "Issuer", "Revision", "Date"]


def applicable_documents_items(
    project_config: ProjectConfig, traceability_index: Any
) -> List[ExportItem]:
    """A heading and a table; nothing when the project names no document."""
    source = IndexReferenceSource(
        traceability_index, project_config.applicable_documents
    )
    rows: List[List[str]] = []
    for key_ in project_config.applicable_documents:
        document = source.documents.get(key_)
        if document is None:
            continue
        info = input_info(document)
        rows.append(
            [
                key_,
                info.title,
                info.reference,
                info.issuer,
                info.revision or info.version,
                info.date,
            ]
        )
    if len(rows) == 0:
        return []
    return [ExportSection(1, TITLE), ExportInfoTable([HEADER, *rows])]
