import os
from pathlib import Path
from typing import Optional

from strictdoc.backend.docx.docx_profile import DocxProfile, load_docx_profile
from strictdoc.backend.docx.export.docx_template import DocxTemplate
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    DocxGenerator,
    effective_profile,
    items_from_document,
)
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.helpers.cast import assert_cast


class DocxExport:
    @staticmethod
    def export_tree(
        traceability_index: TraceabilityIndex,
        output_docx_root: str,
        project_config: ProjectConfig,
    ) -> None:
        Path(output_docx_root).mkdir(parents=True, exist_ok=True)
        profile = effective_profile(_load_profile(project_config))
        template = (
            DocxTemplate.load(profile.template, profile)
            if profile.template is not None
            else DocxTemplate.minimal(profile)
        )
        assert profile.requirement_table is not None

        document: SDocDocument
        for document in traceability_index.document_tree.document_list:
            document_meta = assert_cast(document.meta, DocumentMeta)
            items = items_from_document(document, profile.requirement_table)
            package = DocxGenerator.generate(items, profile, template)
            DocxGenerator.write(
                package,
                os.path.join(
                    output_docx_root,
                    f"{document_meta.document_filename_base}.docx",
                ),
            )


def _load_profile(project_config: ProjectConfig) -> DocxProfile:
    profile_path: Optional[str] = project_config.docx_profile
    if profile_path is None:
        return DocxProfile.generic()
    if not os.path.isabs(profile_path):
        profile_path = os.path.join(
            project_config.get_project_root_path(), profile_path
        )
    return load_docx_profile(profile_path)
