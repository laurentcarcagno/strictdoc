import secrets
from typing import Dict, Optional, Tuple, Union

from markupsafe import Markup

from strictdoc.backend.markdown.markdown_to_html_fragment_writer import (
    MarkdownToHtmlFragmentWriter,
)
from strictdoc.backend.sdoc.constants import SDocMarkup
from strictdoc.backend.sdoc.models.anchor import Anchor
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.inline_link import InlineLink
from strictdoc.backend.sdoc.models.model import RequirementFieldName
from strictdoc.backend.sdoc.models.node import SDocNode, SDocNodeField
from strictdoc.core.project_config import ProjectConfig
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.export.html.document_type import DocumentType
from strictdoc.export.html.html_templates import HTMLTemplates
from strictdoc.export.html.renderers.html_fragment_writer import (
    HTMLFragmentWriter,
)
from strictdoc.export.html.renderers.link_renderer import LinkRenderer

FragmentWriterType = Union[MarkdownToHtmlFragmentWriter, HTMLFragmentWriter]


def _create_fragment_writer(
    markup: Optional[str], flat_assets: bool
) -> FragmentWriterType:
    if markup == SDocMarkup.HTML:
        return HTMLFragmentWriter()
    return MarkdownToHtmlFragmentWriter(flat_assets=flat_assets)


class MarkupRenderer:
    @staticmethod
    def create(
        *,
        markup: Optional[str],
        traceability_index: TraceabilityIndex,
        link_renderer: LinkRenderer,
        html_templates: HTMLTemplates,
        config: ProjectConfig,  # noqa: ARG004 (the callers pass it)
        context_document: Optional[SDocDocument],
        flat_assets: bool = False,
    ) -> "MarkupRenderer":
        assert isinstance(html_templates, HTMLTemplates)
        html_fragment_writer = _create_fragment_writer(markup, flat_assets)
        return MarkupRenderer(
            fragment_writer=html_fragment_writer,
            traceability_index=traceability_index,
            link_renderer=link_renderer,
            html_templates=html_templates,
            context_document=context_document,
            flat_assets=flat_assets,
            primary_markup=markup,
        )

    def __init__(
        self,
        *,
        fragment_writer: FragmentWriterType,
        traceability_index: TraceabilityIndex,
        link_renderer: LinkRenderer,
        html_templates: HTMLTemplates,
        context_document: Optional[SDocDocument],
        flat_assets: bool = False,
        primary_markup: Optional[str] = None,
    ) -> None:
        assert isinstance(traceability_index, TraceabilityIndex)
        assert isinstance(link_renderer, LinkRenderer)
        assert context_document is None or isinstance(
            context_document, SDocDocument
        ), context_document
        assert isinstance(html_templates, HTMLTemplates)

        self.fragment_writer: FragmentWriterType = fragment_writer
        self.traceability_index: TraceabilityIndex = traceability_index
        self.link_renderer: LinkRenderer = link_renderer
        self.context_document: Optional[SDocDocument] = context_document
        self.flat_assets: bool = flat_assets

        # Cache of fragment writers keyed by markup string. Pre-populated with
        # the primary writer so the dispatch method reuses it without creating
        # duplicates for the common case.
        primary_key: str = primary_markup or SDocMarkup.MARKDOWN
        self._writers_by_markup: Dict[str, FragmentWriterType] = {
            primary_key: fragment_writer
        }

        self.cache: Dict[Tuple[DocumentType, SDocNodeField], Markup] = {}

        self.template_anchor = html_templates.jinja_environment().get_template(
            "markup/anchor.jinja"
        )

    def _get_writer_for_node_field(
        self, node_field: SDocNodeField
    ) -> FragmentWriterType:
        """
        Return the fragment writer appropriate for the node field's markup.

        When the bundle document (Markdown by default) contains sub-documents
        with another markup (HTML), nodes from those sub-documents must be
        rendered with the correct writer, not the primary one of the bundle.
        """
        if node_field.parent is None:
            return self.fragment_writer
        doc = node_field.parent.get_document()
        if doc is None or doc.config is None:
            return self.fragment_writer
        key = doc.config.get_markup()
        if key not in self._writers_by_markup:
            self._writers_by_markup[key] = _create_fragment_writer(
                key, self.flat_assets
            )
        return self._writers_by_markup[key]

    def render_node_statement(
        self, document_type: DocumentType, node: SDocNode
    ) -> Markup:
        assert isinstance(node, SDocNode)
        return self.render_node_field(document_type, node.get_content_field())

    def render_truncated_node_statement(
        self, document_type: DocumentType, node: SDocNode
    ) -> Markup:
        assert isinstance(node, SDocNode)
        # FIXME: Double-check and switch to truncating using CSS.
        # https://github.com/strictdoc-project/strictdoc/issues/1925
        return self.render_node_field(document_type, node.get_content_field())

    def render_node_rationale(
        self, document_type: DocumentType, node: SDocNode
    ) -> Markup:
        assert isinstance(node, SDocNode)
        return self.render_node_field(
            document_type,
            node.get_field_by_name(RequirementFieldName.RATIONALE),
        )

    def render_node_field(
        self, document_type: DocumentType, node_field: SDocNodeField
    ) -> Markup:
        assert isinstance(node_field, SDocNodeField), node_field

        if (document_type, node_field) in self.cache:
            return self.cache[(document_type, node_field)]

        fragment_writer = self._get_writer_for_node_field(node_field)

        parts_output = ""
        # The HTML that StrictDoc writes itself (the anchors) goes through the
        # Markdown writer as a comment and is put back afterwards, so that the
        # allow-list of the raw HTML of the author does not touch it.
        trusted_html: Dict[str, str] = {}
        nonce = secrets.token_hex(8)
        keep_trusted_html = isinstance(
            fragment_writer, MarkdownToHtmlFragmentWriter
        )
        for part in node_field.parts:
            if isinstance(part, str):
                parts_output += part
            elif isinstance(part, InlineLink):
                linkable_node = (
                    self.traceability_index.get_linkable_node_by_uid(part.link)
                )
                href = self.link_renderer.render_node_link(
                    linkable_node, self.context_document, document_type
                )
                parts_output += fragment_writer.write_anchor_link(
                    linkable_node.get_display_title(), href
                )
            elif isinstance(part, Anchor):
                anchor_html = self.template_anchor.render(
                    anchor=part,
                    traceability_index=self.traceability_index,
                    link_renderer=self.link_renderer,
                    document_type=DocumentType.DOCUMENT,
                )
                if keep_trusted_html:
                    placeholder = (
                        f"<!--sdoc-trusted-{nonce}-{len(trusted_html)}-->"
                    )
                    # The blank lines around the anchor stay where they are:
                    # they end the HTML block that the anchor opens.
                    stripped_html = anchor_html.strip()
                    leading = anchor_html[: anchor_html.index(stripped_html)]
                    trailing = anchor_html[len(leading) + len(stripped_html) :]
                    trusted_html[placeholder] = stripped_html
                    parts_output += leading + placeholder + trailing
                else:
                    parts_output += anchor_html
            else:
                raise NotImplementedError

        output = fragment_writer.write(parts_output)
        if len(trusted_html) > 0:
            text = str(output)
            for placeholder, html in trusted_html.items():
                text = text.replace(placeholder, html)
            output = Markup(text)
        self.cache[(document_type, node_field)] = output

        return output
