import os
import sys
from pathlib import Path
from typing import Optional

from strictdoc.backend.docx.docx_profile import DocxProfile, load_docx_profile
from strictdoc.backend.docx.export.docx_template import DocxTemplate
from strictdoc.backend.docx.export.docx_tracked_update import DocxUpdater
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    DocxGenerator,
    effective_profile,
    items_from_document,
)
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.features.hierarchy.applicable_table import (
    applicable_documents_items,
)
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.exception import StrictDocException


class DocxExport:
    @staticmethod
    def export_tree(
        traceability_index: TraceabilityIndex,
        output_docx_root: str,
        project_config: ProjectConfig,
    ) -> None:
        Path(output_docx_root).mkdir(parents=True, exist_ok=True)
        profile = effective_profile(load_project_profile(project_config))
        assert profile.requirement_table is not None
        template: Optional[DocxTemplate] = None
        if project_config.docx_base is None:
            template = (
                DocxTemplate.load(profile.template, profile)
                if profile.template is not None
                else DocxTemplate.minimal(profile)
            )

        document: SDocDocument
        for document in traceability_index.document_tree.document_list:
            document_meta = assert_cast(document.meta, DocumentMeta)
            items = items_from_document(
                document, profile.requirement_table, profile.comments
            )
            if (
                project_config.docx_base is None
                and profile.applicable_documents_table
            ):
                items = (
                    applicable_documents_items(
                        project_config, traceability_index
                    )
                    + items
                )
            output_path = os.path.join(
                output_docx_root, f"{document_meta.document_filename_base}.docx"
            )
            if project_config.docx_base is not None:
                base_path = _base_path(
                    project_config, document_meta.document_filename_base
                )
                package, report = DocxUpdater.update(base_path, items, profile)
                sys.stdout.write(report.format() + "\n")
            else:
                assert template is not None
                package = DocxGenerator.generate(items, profile, template)
            DocxGenerator.write(package, output_path)


def _base_path(project_config: ProjectConfig, document_name: str) -> str:
    base = project_config.docx_base
    assert base is not None
    if not os.path.isabs(base):
        base = os.path.join(project_config.get_project_root_path(), base)
    if os.path.isdir(base):
        base = os.path.join(base, f"{document_name}.docx")
    if not os.path.isfile(base):
        raise StrictDocException(
            f"The Word document to update is missing: {base}."
        )
    return base


def resolve_profile_path(project_config: ProjectConfig) -> Optional[str]:
    """The profile file of the project, or None for the generic profile."""
    profile_path: Optional[str] = project_config.docx_profile
    if profile_path is None:
        return None
    if not os.path.isabs(profile_path):
        profile_path = os.path.join(
            project_config.get_project_root_path(), profile_path
        )
    return profile_path


def load_project_profile(project_config: ProjectConfig) -> DocxProfile:
    profile_path = resolve_profile_path(project_config)
    if profile_path is None:
        return DocxProfile.generic()
    return load_docx_profile(profile_path)
