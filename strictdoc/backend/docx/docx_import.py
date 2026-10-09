import os
from dataclasses import dataclass
from typing import Optional, Tuple

from strictdoc.backend.docx.docx_profile import DocxProfile, load_docx_profile
from strictdoc.backend.docx.import_.docx_reader import (
    DocxReader,
    TrackedChangesMode,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    DocxImportReport,
    DocxToSDocConverter,
)
from strictdoc.backend.sdoc.models.document import SDocDocument


@dataclass
class DocxImportOptions:
    input_path: str
    profile_path: Optional[str]
    tracked_changes: TrackedChangesMode
    dry_run: bool


class DocxImport:
    @staticmethod
    def import_from_file(
        import_options: DocxImportOptions,
    ) -> Tuple[SDocDocument, DocxImportReport]:
        profile = (
            load_docx_profile(import_options.profile_path)
            if import_options.profile_path is not None
            else DocxProfile.generic()
        )
        blocks = DocxReader.read(
            import_options.input_path, import_options.tracked_changes
        )
        fallback_title = os.path.splitext(
            os.path.basename(import_options.input_path)
        )[0]
        return DocxToSDocConverter.convert(blocks, profile, fallback_title)
