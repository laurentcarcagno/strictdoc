import json

from developer.tools import rst_to_markdown as script

RST_DOCUMENT = """\
[DOCUMENT]
TITLE: Document
OPTIONS:
  ENABLE_MID: False
  VIEW_STYLE: Inline

[TEXT]
STATEMENT: >>>
A ``code`` word and a *stress*.

.. note::

    Careful.
<<<

[REQUIREMENT]
UID: REQ-1
TITLE: Requirement
STATEMENT: The system shall use ``x``.
"""


def _run(tmp_path, *arguments):
    return script.main([str(tmp_path), "--force", *arguments])


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf8", newline="")
    return path


def test_001_scan_finds_multiline_and_single_line_content_fields():
    spans = script.scan_fields(RST_DOCUMENT.splitlines(keepends=True))

    assert [(s_.name, s_.multiline, s_.uid) for s_ in spans] == [
        ("STATEMENT", True, ""),
        ("STATEMENT", False, "REQ-1"),
    ]


def test_002_markup_is_written_after_enable_mid_in_the_options():
    lines = RST_DOCUMENT.splitlines(keepends=True)

    new_lines = script.set_markup(lines, "\n")

    assert new_lines[2:6] == [
        "OPTIONS:\n",
        "  ENABLE_MID: False\n",
        "  MARKUP: Markdown\n",
        "  VIEW_STYLE: Inline\n",
    ]


def test_003_an_options_section_is_added_when_there_is_none():
    lines = ["[DOCUMENT]\n", "TITLE: T\n", "\n", "[TEXT]\n"]

    assert script.set_markup(lines, "\n")[:4] == [
        "[DOCUMENT]\n",
        "TITLE: T\n",
        "OPTIONS:\n",
        "  MARKUP: Markdown\n",
    ]


def test_004_markup_rst_is_replaced():
    lines = ["[DOCUMENT]\n", "OPTIONS:\n", "  MARKUP: RST\n", "\n"]

    assert script.set_markup(lines, "\n")[2] == "  MARKUP: Markdown\n"


def test_005_a_document_is_converted_and_the_rest_is_kept(tmp_path):
    path = _write(tmp_path, "a.sdoc", RST_DOCUMENT)

    assert _run(tmp_path) == 0

    text = path.read_text(encoding="utf8")
    assert "  MARKUP: Markdown\n" in text
    assert "A `code` word and a *stress*." in text
    assert 'class="sdoc-admonition sdoc-note"' in text
    assert "STATEMENT: The system shall use `x`.\n" in text
    assert text.startswith("[DOCUMENT]\nTITLE: Document\nOPTIONS:\n")


def test_006_a_second_run_changes_nothing(tmp_path):
    path = _write(tmp_path, "a.sdoc", RST_DOCUMENT)
    _run(tmp_path)
    first = path.read_text(encoding="utf8")

    _run(tmp_path)

    assert path.read_text(encoding="utf8") == first


def test_007_a_file_without_markup_to_change_is_not_touched(tmp_path):
    text = "[DOCUMENT]\nTITLE: T\n\n[TEXT]\nSTATEMENT: >>>\nPlain text.\n<<<\n"
    path = _write(tmp_path, "plain.sdoc", text)

    _run(tmp_path)

    assert path.read_text(encoding="utf8") == text


def test_008_dry_run_writes_nothing(tmp_path):
    path = _write(tmp_path, "a.sdoc", RST_DOCUMENT)

    _run(tmp_path, "--dry-run")

    assert path.read_text(encoding="utf8") == RST_DOCUMENT


def test_009_markdown_html_and_text_documents_are_skipped(tmp_path):
    for markup_ in ("Markdown", "HTML", "Text"):
        _write(
            tmp_path,
            f"{markup_}.sdoc",
            f"[DOCUMENT]\nTITLE: T\nOPTIONS:\n  MARKUP: {markup_}\n\n"
            "[TEXT]\nSTATEMENT: >>>\nA ``word``.\n<<<\n",
        )

    _run(tmp_path, "--report", str(tmp_path / "report"))

    report = json.loads(
        (tmp_path / "report" / "conversion_report.json").read_text()
    )
    assert {file_["status"] for file_ in report["files"]} == {"skipped"}
    assert "``word``" in (tmp_path / "Text.sdoc").read_text(encoding="utf8")


def test_010_line_endings_are_kept(tmp_path):
    path = _write(tmp_path, "crlf.sdoc", RST_DOCUMENT.replace("\n", "\r\n"))

    _run(tmp_path)

    data = path.read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_011_an_included_document_has_the_markup_of_its_includer(tmp_path):
    _write(
        tmp_path,
        "root.sdoc",
        "[DOCUMENT]\nTITLE: Root\nOPTIONS:\n  MARKUP: Markdown\n\n"
        "[DOCUMENT_FROM_FILE]\nFILE: part.sdoc\n",
    )
    part = _write(
        tmp_path,
        "part.sdoc",
        "[DOCUMENT]\nTITLE: Part\n\n[TEXT]\nSTATEMENT: >>>\nA ``word``.\n<<<\n",
    )

    _run(tmp_path)

    assert "``word``" in part.read_text(encoding="utf8")


def test_012_strict_fails_on_a_warning_and_the_report_lists_it(tmp_path):
    _write(
        tmp_path,
        "a.sdoc",
        "[DOCUMENT]\nTITLE: T\n\n[REQUIREMENT]\nUID: R-1\nSTATEMENT: >>>\n"
        ".. raw:: latex\n\n    \\newpage\n<<<\n",
    )

    code = _run(
        tmp_path, "--strict", "--dry-run", "--report", str(tmp_path / "r")
    )

    assert code == 1
    report = (tmp_path / "r" / "conversion_report.md").read_text()
    assert "R-1 STATEMENT: raw: the raw latex block is dropped" in report


def test_013_verify_reports_a_field_whose_words_change(tmp_path, monkeypatch):
    _write(tmp_path, "a.sdoc", RST_DOCUMENT)
    monkeypatch.setattr(script, "words_of_markdown", lambda _text: ["other"])

    code = _run(tmp_path, "--verify", "--strict", "--dry-run")

    assert code == 1


def test_014_a_dirty_git_tree_stops_the_conversion(tmp_path, monkeypatch):
    path = _write(tmp_path, "a.sdoc", RST_DOCUMENT)
    monkeypatch.setattr(script, "git_is_clean", lambda _paths: False)

    code = script.main([str(tmp_path)])

    assert code == 2
    assert path.read_text(encoding="utf8") == RST_DOCUMENT


def test_015_a_single_line_field_that_becomes_long_is_written_as_a_block(
    tmp_path,
):
    path = _write(
        tmp_path,
        "a.sdoc",
        "[DOCUMENT]\nTITLE: T\n\n[REQUIREMENT]\nUID: R-1\n"
        "STATEMENT: .. note:: A short note\n",
    )

    _run(tmp_path)

    text = path.read_text(encoding="utf8")
    assert "STATEMENT: >>>\n<div" in text
    assert "<<<\n" in text


PARENT_CHILD = """\
[DOCUMENT]
TITLE: Document

[REQUIREMENT]
UID: REQ-1
TITLE: Parent
STATEMENT: >>>
The system shall use ``x`` and *y*.
<<<

[REQUIREMENT]
UID: REQ-2
TITLE: Child
STATEMENT: Child text.
RELATIONS:
- TYPE: Parent
  VALUE: REQ-1

[REQUIREMENT]
UID: REQ-3
TITLE: Other child
STATEMENT: Other child text.
RELATIONS:
- TYPE: Parent
  VALUE: REQ-1
"""


def test_016_the_baseline_follows_the_conversion_of_a_reviewed_parent(
    tmp_path,
):
    path = _write(tmp_path, "a.sdoc", PARENT_CHILD)
    fields = ["TITLE", "STATEMENT"]
    before = script.node_hashes(str(path), fields)["REQ-1"]
    baseline = script.Baseline(
        {
            "REQ-2 < REQ-1": before,
            # This link was already suspect: its parent changed after review.
            "REQ-3 < REQ-1": "0" * 40,
        }
    )
    baseline_path = tmp_path / "trace_baseline.json"
    baseline.save(str(baseline_path))

    code = _run(tmp_path, "--baseline", str(baseline_path))

    assert code == 0
    after = script.node_hashes(str(path), fields)["REQ-1"]
    assert after != before
    saved = script.Baseline.load(str(baseline_path)).entries
    assert saved["REQ-2 < REQ-1"] == after
    assert saved["REQ-3 < REQ-1"] == "0" * 40


def test_017_a_baseline_in_the_given_folder_is_found_without_the_option(
    tmp_path,
):
    path = _write(tmp_path, "a.sdoc", PARENT_CHILD)
    before = script.node_hashes(str(path), ["TITLE", "STATEMENT"])["REQ-1"]
    script.Baseline({"REQ-2 < REQ-1": before}).save(
        str(tmp_path / "trace_baseline.json")
    )

    _run(tmp_path)

    saved = script.Baseline.load(str(tmp_path / "trace_baseline.json"))
    assert saved.entries["REQ-2 < REQ-1"] != before


TEXT_DOCUMENT = """\
[DOCUMENT]
TITLE: Text document
OPTIONS:
  MARKUP: Text

[TEXT]
STATEMENT: >>>
First line with *stars* and <tags>.
Second line.

New paragraph.
<<<
"""


def test_018_text_documents_are_converted_with_the_text_option_only(tmp_path):
    path = _write(tmp_path, "t.sdoc", TEXT_DOCUMENT)

    _run(tmp_path)
    assert path.read_text(encoding="utf8") == TEXT_DOCUMENT

    _run(tmp_path, "--text", "--verify", "--strict")
    text = path.read_text(encoding="utf8")
    assert "  MARKUP: Markdown\n" in text
    assert (
        "First line with \\*stars\\* and \\<tags>.\\\nSecond line.\n\n"
        "New paragraph.\n"
    ) in text
