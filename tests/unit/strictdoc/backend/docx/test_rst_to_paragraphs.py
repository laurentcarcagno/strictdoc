from strictdoc.backend.docx.export.rst_to_paragraphs import (
    ExportParagraph,
    ExportRun,
    rst_to_paragraphs,
)


def _texts(paragraphs):
    return ["".join(run_.text for run_ in p_.runs) for p_ in paragraphs]


def test_001_blank_lines_separate_paragraphs():
    paragraphs = rst_to_paragraphs("One.\n\nTwo.")
    assert _texts(paragraphs) == ["One.", "Two."]


def test_002_wrapped_lines_are_joined_with_a_space():
    paragraphs = rst_to_paragraphs("A long\nsentence.")
    assert _texts(paragraphs) == ["A long sentence."]


def test_003_bullets_become_paragraphs_starting_with_a_dash():
    paragraphs = rst_to_paragraphs("Intro:\n\n- one\n- two\n  continued")
    assert _texts(paragraphs) == ["Intro:", "- one", "- two continued"]


def test_004_inline_markup_becomes_formatted_runs():
    paragraphs = rst_to_paragraphs("a **b** *c* ``d`` e")
    assert paragraphs[0].runs == [
        ExportRun("a "),
        ExportRun("b", bold=True),
        ExportRun(" "),
        ExportRun("c", italic=True),
        ExportRun(" "),
        ExportRun("d", monospace=True),
        ExportRun(" e"),
    ]


def test_005_escapes_give_literal_characters():
    paragraphs = rst_to_paragraphs("2\\*3 \\`x\\` name\\_ back\\\\slash")
    assert _texts(paragraphs) == ["2*3 `x` name_ back\\slash"]


def test_006_unbalanced_markers_stay_literal():
    paragraphs = rst_to_paragraphs("a * b and ** c")
    assert _texts(paragraphs) == ["a * b and ** c"]


def test_007_empty_input_gives_no_paragraph():
    assert rst_to_paragraphs("") == []
    assert rst_to_paragraphs("\n\n") == []


def test_008_a_paragraph_is_an_export_paragraph():
    assert isinstance(rst_to_paragraphs("x")[0], ExportParagraph)
