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
from strictdoc.backend.docx.import_.sdoc_requirement_blocks import (
    CarryOver,
    build_carry_over,
)
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.features.hierarchy.references import ResolverFunction
from strictdoc.helpers.file_system import file_open_read_utf8


@dataclass
class DocxImportOptions:
    input_path: str
    profile_path: Optional[str]
    tracked_changes: TrackedChangesMode
    dry_run: bool
    # The directory that convert writes to. An SDoc file with the same name
    # in it is merged with the Word document, unless overwrite is set.
    output_path: str
    overwrite: bool
    # Turns the text of a relation column into links to applicable documents.
    reference_resolver: Optional[ResolverFunction] = None


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
        carry_over = _read_existing_file(
            import_options, profile, fallback_title
        )
        return DocxToSDocConverter.convert(
            blocks,
            profile,
            fallback_title,
            carry_over,
            import_options.reference_resolver,
        )


def _read_existing_file(
    import_options: DocxImportOptions,
    profile: DocxProfile,
    stem: str,
) -> Optional[CarryOver]:
    if import_options.overwrite or profile.requirement_table is None:
        return None
    existing_path = os.path.join(import_options.output_path, stem + ".sdoc")
    if not os.path.isfile(existing_path):
        return None
    with file_open_read_utf8(existing_path) as file_:
        existing_text = file_.read()
    return build_carry_over(existing_text, profile.requirement_table)
