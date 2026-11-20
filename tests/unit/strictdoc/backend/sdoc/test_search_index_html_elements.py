"""
@relation(SDOC-SRS-155, scope=file)
"""

from strictdoc.backend.sdoc.reader import SDReader

ADMONITION = """\
[DOCUMENT]
TITLE: Document
OPTIONS:
  MARKUP: {markup}

[TEXT]
STATEMENT: >>>
<div class="sdoc-admonition sdoc-note" role="note">
<p class="sdoc-admonition-title">Remark</p>

Voltage limit.

</div>
<<<
"""


def _words(markup: str):
    document = SDReader().read(ADMONITION.format(markup=markup))
    document.build_search_index()
    return document.search_index.document_index


def test_001_the_words_of_an_html_element_are_searchable():
    index = _words("Markdown")

    assert "remark" in index
    assert "voltage" in index


def test_002_the_tags_and_attributes_of_a_markdown_field_are_not_searchable():
    index = _words("Markdown")

    assert "admonition" not in index
    assert "sdoc" not in index
    assert "role" not in index
    assert "div" not in index


def test_003_a_field_of_an_html_document_is_indexed_as_it_is():
    index = _words("HTML")

    assert "admonition" in index
