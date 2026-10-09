import argparse
import os
import sys
from typing import List

from strictdoc.backend.docx.docx_export import DocxExport
from strictdoc.backend.docx.docx_import import DocxImport, DocxImportOptions
from strictdoc.backend.docx.import_.docx_reader import TrackedChangesMode
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.commands.convert_config import ConvertCommandConfig
from strictdoc.core.format import ExportContext, Format
from strictdoc.core.project_config import ProjectConfig


class DocxFormat(Format):
    @staticmethod
    def handles() -> List[str]:
        return ["docx"]

    @staticmethod
    def supported_extensions() -> List[str]:
        return [".docx"]

    @staticmethod
    def supports_import() -> bool:
        return True

    @staticmethod
    def supports_export() -> bool:
        return True

    @staticmethod
    def supports_read() -> bool:
        return False

    @staticmethod
    def supports_edit() -> bool:
        return False

    @staticmethod
    def supports_grammar() -> bool:
        return False

    @classmethod
    def add_import_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--docx-profile",
            type=str,
            default=None,
            help=(
                "Path to a Python file that defines create_profile() and "
                "describes how the Word document is organized."
            ),
        )
        parser.add_argument(
            "--docx-tracked-changes",
            choices=[mode_.value for mode_ in TrackedChangesMode],
            default=TrackedChangesMode.ACCEPT.value,
            help=(
                "How to read tracked changes: accept them (default) or "
                "reject them."
            ),
        )
        parser.add_argument(
            "--docx-overwrite",
            action="store_true",
            default=False,
            help=(
                "Replace the SDoc file in the output directory. By default, "
                "the Word document is merged into it by UID."
            ),
        )
        parser.add_argument(
            "--docx-dry-run",
            action="store_true",
            default=False,
            help="Read the Word document and print the report, write nothing.",
        )

    @classmethod
    def build_import_options(
        cls, args: argparse.Namespace
    ) -> DocxImportOptions:
        return DocxImportOptions(
            input_path=args.input_path,
            profile_path=args.docx_profile,
            tracked_changes=TrackedChangesMode(args.docx_tracked_changes),
            dry_run=args.docx_dry_run,
            output_path=args.output_path,
            overwrite=args.docx_overwrite,
        )

    def import_file(  # type: ignore[override]
        self,
        import_options: DocxImportOptions,
        project_config: ProjectConfig,  # noqa: ARG002
    ) -> List[SDocDocument]:
        document, report = DocxImport.import_from_file(import_options)
        sys.stdout.write(report.format() + "\n")
        if import_options.dry_run:
            sys.stdout.write("Dry run: no file written.\n")
            return []
        return [document]

    def import_output_filename_stem(
        self,
        document: SDocDocument,  # noqa: ARG002
        convert_config: ConvertCommandConfig,
    ) -> str:
        return os.path.splitext(os.path.basename(convert_config.input_path))[0]

    def export_complete_tree(self, context: ExportContext, handle: str) -> None:
        assert handle in self.handles(), handle
        DocxExport.export_tree(
            context.traceability_index,
            os.path.join(context.project_config.output_dir, "docx"),
            context.project_config,
        )
