import os.path
import re
from typing import Any, Callable, Dict, List, Optional, Union, cast

from textx import TextXSyntaxError, get_model

from strictdoc.backend.sdoc.constants import SDocMarkup
from strictdoc.backend.sdoc.document_reference import DocumentReference
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.document_config import DocumentConfig
from strictdoc.backend.sdoc.models.document_from_file import DocumentFromFile
from strictdoc.backend.sdoc.models.document_grammar import DocumentGrammar
from strictdoc.backend.sdoc.models.document_view import DocumentView
from strictdoc.backend.sdoc.models.grammar_element import GrammarElement
from strictdoc.backend.sdoc.models.model import (
    SDocDocumentFromFileIF,
    SDocDocumentIF,
    SDocNodeIF,
)
from strictdoc.backend.sdoc.models.node import (
    SDocNode,
    SDocNodeField,
)
from strictdoc.backend.sdoc.residual_rst import find_residual_rst
from strictdoc.helpers.deprecation_engine import DEPRECATION_ENGINE
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.textx import (
    SupportsTxPosition,
    preserve_source_location_data,
)


class ParseContext:
    def __init__(
        self, path_to_sdoc_file: Optional[str], migrate_sections: bool = False
    ):
        self.path_to_sdoc_file: Optional[str] = path_to_sdoc_file
        self.path_to_sdoc_dir: Optional[str] = None
        if path_to_sdoc_file is not None:
            self.path_to_sdoc_dir = os.path.dirname(path_to_sdoc_file)
        self.document_grammar: Optional[DocumentGrammar] = None
        self.document_reference: DocumentReference = DocumentReference()
        self.context_document_reference: DocumentReference = DocumentReference()
        self.document_config: Optional[DocumentConfig] = None
        self.document_view: Optional[DocumentView] = None
        self.document_has_requirements = False

        self.fragments_from_files: List[SDocDocumentFromFileIF] = []
        self.migrate_sections: bool = migrate_sections


class SDocParsingProcessor:
    def __init__(self, parse_context: ParseContext) -> None:
        self.parse_context: ParseContext = parse_context

    def process_document(self, document: SDocDocument) -> None:
        document.grammar = (
            self.parse_context.document_grammar
            or DocumentGrammar.create_default(
                document,
                enable_mid=document.config.enable_mid or False,
            )
        )
        document.ng_including_document_reference = (
            self.parse_context.context_document_reference
        )

    def get_default_processors(self) -> Dict[str, Callable[..., None]]:
        return {
            "SDocDocument": self.process_document,
            "DocumentConfig": self.process_document_config,
            "DocumentGrammar": self.process_document_grammar,
            "GrammarElement": self.process_document_grammar_element,
            "DocumentView": self.process_document_view,
            "SDocSection": self.process_section,
            "DocumentFromFile": self.process_document_from_file,
            "SDocCompositeNode": self.process_requirement,
            "SDocNode": self.process_requirement,
            "SDocNodeField": self.process_node_field,
        }

    def process_document_config(self, document_config: DocumentConfig) -> None:
        if document_config.markup in SDocMarkup.REMOVED:
            raise StrictDocException(
                f"MARKUP: {document_config.markup} is no longer supported: "
                "StrictDoc reads Markdown and HTML only. Convert the document "
                "with developer/tools/rst_to_markdown.py, which stays in the "
                "git tag rst-to-markdown-converter."
            )
        the_model = get_model(document_config)
        line_start, col_start = the_model._tx_parser.pos_to_linecol(
            cast(SupportsTxPosition, document_config)._tx_position
        )
        document_config.ng_line_start = line_start
        document_config.ng_col_start = col_start
        self.parse_context.document_config = document_config

    def process_document_grammar(
        self, document_grammar: DocumentGrammar
    ) -> None:
        assert self.parse_context.document_config is not None

        if (import_from_file_ := document_grammar.import_from_file) is not None:
            if re.search(r"\.\.|[/\\]", import_from_file_):
                raise StrictDocException(
                    "[GRAMMAR]: "
                    "IMPORT_FROM_FILE must not contain any '..', '/', '\\' characters: "
                    f"{import_from_file_}."
                )

        preserve_source_location_data(document_grammar)
        # FIXME: It would be great to move forward and remove this.
        if not document_grammar.has_text_element():
            document_grammar.add_element_first(
                DocumentGrammar.create_default_text_element(
                    document_grammar,
                    enable_mid=self.parse_context.document_config.enable_mid
                    is True,
                )
            )
        self.parse_context.document_grammar = document_grammar

    def process_document_grammar_element(
        self, grammar_element: GrammarElement
    ) -> None:
        preserve_source_location_data(grammar_element)

    def process_document_view(self, document_view: DocumentView) -> None:
        self.parse_context.document_view = document_view

        the_model = get_model(document_view)
        line_start, col_start = the_model._tx_parser.pos_to_linecol(
            cast(SupportsTxPosition, document_view)._tx_position
        )
        document_view.ng_line_start = line_start
        document_view.ng_col_start = col_start

    def process_section(self, _: Any) -> None:
        raise StrictDocException("""
[SECTION] elements are no longer supported by StrictDoc. See the migration guide for more details:\n"
"https://strictdoc.readthedocs.io/en/latest/latest/docs/strictdoc_01_user_guide.html#SECTION-UG-NODE-MIGRATION."
""")

    def process_document_from_file(
        self, document_from_file: DocumentFromFile
    ) -> None:
        assert isinstance(document_from_file, DocumentFromFile), (
            document_from_file
        )

        # Windows paths are backslashes, so using abspath in addition.
        assert self.parse_context.path_to_sdoc_dir is not None
        resolved_path_to_fragment_file = os.path.abspath(
            os.path.join(
                self.parse_context.path_to_sdoc_dir, document_from_file.file
            )
        )
        if not resolved_path_to_fragment_file.endswith(".sdoc"):
            raise StrictDocException(
                '[DOCUMENT_FROM_FILE]: A document file name must have ".sdoc" extension: '
                f"{document_from_file.file}."
            )
        if not os.path.isfile(resolved_path_to_fragment_file):
            raise StrictDocException(
                "[DOCUMENT_FROM_FILE]: Path to a document file does not exist: "
                f"{document_from_file.file}."
            )

        document_from_file.ng_document_reference = (
            self.parse_context.document_reference
        )
        document_from_file.resolved_full_path_to_document_file = (
            resolved_path_to_fragment_file
        )

        self.parse_context.fragments_from_files.append(document_from_file)

    def process_requirement(self, requirement: SDocNode) -> None:
        requirement.ng_document_reference = (
            self.parse_context.document_reference
        )
        requirement.ng_including_document_reference = (
            self.parse_context.context_document_reference
        )

        if requirement.is_normative_node():
            self.parse_context.document_has_requirements = True

            cursor: Union[SDocDocumentIF, SDocNodeIF] = requirement.parent
            while (
                isinstance(cursor, (SDocNodeIF))
                and not cursor.ng_has_requirements
            ):
                cursor.ng_has_requirements = True
                cursor = cursor.parent

        assert self.parse_context.document_config is not None
        if (
            requirement.reserved_title is None
            or not self.parse_context.document_config.is_requirement_in_toc()
        ) and self.parse_context.document_config.auto_levels:
            requirement.ng_resolved_custom_level = "None"

        preserve_source_location_data(requirement)

        # FIXME: Refactor to eliminate the need in such assert.
        assert self.parse_context.document_config is not None

        if not self.parse_context.document_config.auto_levels:
            if not requirement.ng_resolved_custom_level:
                raise StrictDocException(
                    f"[{requirement.node_type}].LEVEL field is not provided. "
                    "This contradicts to the option "
                    "[DOCUMENT].OPTIONS.AUTO_LEVELS set to Off. "
                    f"Node: {requirement}"
                )

    def process_node_field(self, node_field: SDocNodeField) -> None:
        self._warn_about_residual_rst(node_field)
        node_field_parts = node_field.parts
        if (
            isinstance(node_field_parts[0], str)
            and node_field_parts[0].strip() == ""
        ):
            the_model = get_model(node_field)
            line_start, col_start = the_model._tx_parser.pos_to_linecol(
                cast(SupportsTxPosition, node_field)._tx_position
            )
            raise TextXSyntaxError(
                "Node statement cannot be empty.",
                line=line_start,
                col=col_start,
                filename=self.parse_context.path_to_sdoc_file,
            )

    def _warn_about_residual_rst(self, node_field: SDocNodeField) -> None:
        """A field that still holds RST is read as Markdown: say so, once."""
        document_config = self.parse_context.document_config
        if (
            document_config is None
            or document_config.get_markup() != SDocMarkup.MARKDOWN
            or not node_field.is_multiline()
        ):
            return
        text = "".join(
            part_ for part_ in node_field.parts if isinstance(part_, str)
        )
        reason = find_residual_rst(text)
        if reason is None:
            return
        path = self.parse_context.path_to_sdoc_file or "<string>"
        DEPRECATION_ENGINE.add_message(
            f"residual_rst_{path}",
            f"The document {path} has a field that looks like RST: {reason}. "
            "StrictDoc reads Markdown only, so the field is not rendered as "
            "it was written. Convert the document with "
            "developer/tools/rst_to_markdown.py, which stays in the git tag "
            "rst-to-markdown-converter.",
        )
