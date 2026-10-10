"""
The Word actions of the web interface, without any web type.

The routes upload a file, call one function of this module and show the
report. Uploaded bytes are copied to a temporary folder for the call.
"""

import io
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from strictdoc.backend.docx.docx_export import (
    load_project_profile,
    resolve_profile_path,
)
from strictdoc.backend.docx.docx_import import DocxImport, DocxImportOptions
from strictdoc.backend.docx.export.docx_template import DocxTemplate
from strictdoc.backend.docx.export.docx_tracked_update import (
    DocxUpdater,
    DocxUpdateReport,
)
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    DocxGenerator,
    effective_profile,
    items_from_document,
)
from strictdoc.backend.docx.import_.docx_reader import TrackedChangesMode
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    DocxImportReport,
)
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.core.document_meta import DocumentMeta
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.hierarchy.references import ResolverFunction
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.paths import SDocRelativePath

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


@dataclass
class DocxImportResult:
    document: SDocDocument
    report: DocxImportReport
    # The name of the SDoc file without its extension.
    stem: str


def safe_stem(filename: Optional[str]) -> str:
    """The upload name reduced to letters, digits, '-' and '_'."""
    base = os.path.basename((filename or "").replace("\\", "/"))
    stem = os.path.splitext(base)[0]
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem).strip("_")
    return stem if len(stem) > 0 else "word_document"


def check_upload(data: bytes) -> None:
    """Rejects an empty, too large or non-Word upload with a clear message."""
    if len(data) == 0:
        raise StrictDocException("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise StrictDocException(
            f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package_:
            if "word/document.xml" not in package_.namelist():
                raise StrictDocException(
                    "The file is not a Word document (word/document.xml is "
                    "missing)."
                )
    except zipfile.BadZipFile as exception_:
        raise StrictDocException(
            "The file is not a Word document (.docx)."
        ) from exception_


def import_upload(
    data: bytes,
    filename: Optional[str],
    project_config: ProjectConfig,
    input_dir: str,
    tracked_changes: TrackedChangesMode,
    overwrite: bool,
    reference_resolver: Optional[ResolverFunction] = None,
) -> DocxImportResult:
    """Converts the Word file. Nothing is written to the project."""
    check_upload(data)
    stem = safe_stem(filename)
    with tempfile.TemporaryDirectory() as temporary_dir_:
        input_path = os.path.join(temporary_dir_, stem + ".docx")
        with open(input_path, "wb") as file_:
            file_.write(data)
        document, report = DocxImport.import_from_file(
            DocxImportOptions(
                input_path=input_path,
                profile_path=resolve_profile_path(project_config),
                tracked_changes=tracked_changes,
                dry_run=False,
                output_path=input_dir,
                overwrite=overwrite,
                reference_resolver=reference_resolver,
            )
        )
    return DocxImportResult(document=document, report=report, stem=stem)


def describe_profile(project_config: ProjectConfig) -> str:
    profile_path = project_config.docx_profile
    if profile_path is None:
        return (
            "Profile: generic (no docx_profile in the configuration). The "
            "generic profile does not know requirement tables."
        )
    return f"Profile: {profile_path}"


def import_warning(
    report: DocxImportReport, project_config: ProjectConfig
) -> str:
    """A hint when the file gives no requirement, empty when all is fine."""
    if report.requirement_count > 0:
        return ""
    if project_config.docx_profile is None:
        return (
            "No requirement found. Set docx_profile in strictdoc_config.py to "
            "a profile that describes the requirement tables."
        )
    return (
        "No requirement found. Check that the table styles and row labels of "
        "the profile match this document."
    )


def attach_meta(document: SDocDocument, input_dir: str, stem: str) -> str:
    """Gives the document the meta that the SDoc writer needs."""
    file_name = stem + ".sdoc"
    full_path = os.path.join(os.path.abspath(input_dir), file_name)
    document.meta = DocumentMeta(
        level=0,
        file_tree_mount_folder="NOT_RELEVANT",
        document_filename=file_name,
        document_filename_base=stem,
        input_doc_full_path=full_path,
        input_doc_rel_path=SDocRelativePath(file_name),
        input_doc_dir_rel_path=SDocRelativePath(""),
        input_doc_assets_dir_rel_path=SDocRelativePath("_assets"),
        output_document_dir_full_path="NOT_RELEVANT",
        output_document_dir_rel_path=SDocRelativePath("FIXME"),
    )
    return full_path


def export_fresh(
    document: SDocDocument, project_config: ProjectConfig
) -> bytes:
    """A new Word file for the document, built from the profile template."""
    profile = effective_profile(load_project_profile(project_config))
    assert profile.requirement_table is not None
    template = (
        DocxTemplate.load(profile.template, profile)
        if profile.template is not None
        else DocxTemplate.minimal(profile)
    )
    items = items_from_document(
        document, profile.requirement_table, profile.comments
    )
    return _zip(DocxGenerator.generate(items, profile, template))


def export_update(
    document: SDocDocument, base: bytes, project_config: ProjectConfig
) -> Tuple[bytes, DocxUpdateReport]:
    """The base Word file with the differences as tracked changes."""
    check_upload(base)
    profile = effective_profile(load_project_profile(project_config))
    assert profile.requirement_table is not None
    items = items_from_document(
        document, profile.requirement_table, profile.comments
    )
    with tempfile.TemporaryDirectory() as temporary_dir_:
        base_path = os.path.join(temporary_dir_, "base.docx")
        with open(base_path, "wb") as file_:
            file_.write(base)
        package, report = DocxUpdater.update(base_path, items, profile)
    return _zip(package), report


def _zip(package: Dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as output_:
        for name_, data_ in package.items():
            output_.writestr(name_, data_)
    return buffer.getvalue()
