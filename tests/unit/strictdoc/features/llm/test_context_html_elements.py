from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.features.llm.context import _item

DOCUMENT = """\
[DOCUMENT]
TITLE: Document
OPTIONS:
  MARKUP: {markup}

[TEXT]
STATEMENT: >>>
<div class="sdoc-admonition sdoc-note" role="note">
<p class="sdoc-admonition-title">Remark</p>

The voltage shall not exceed <UID> volts.

</div>
<<<
"""


def _context_text(markup: str) -> str:
    document = SDReader().read(DOCUMENT.format(markup=markup))
    return _item("node", document.section_contents[0]).text


def test_001_a_model_reads_the_words_not_the_tags_of_a_markdown_field():
    text = _context_text("Markdown")

    assert "Remark" in text
    assert "The voltage shall not exceed <UID> volts." in text
    assert "<div" not in text
    assert "sdoc-admonition" not in text


def test_002_a_field_of_an_html_document_is_sent_as_it_is():
    assert "<div" in _context_text("HTML")
