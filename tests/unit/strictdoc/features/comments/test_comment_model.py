from strictdoc.features.comments.model import (
    STATUS_RESOLVED,
    Comment,
    clean_anchor,
    format_comment,
    initials,
    parse_comment,
)


def _comment(**overrides):
    values = {
        "body": "This is not testable.",
        "id": "c7f3a9",
        "author": "anna.durand",
        "date": "2026-10-10T12:00:00Z",
    }
    values.update(overrides)
    return Comment(**values)


def test_001_rst_round_trip():
    comment = _comment()
    value = format_comment(comment, "RST")
    assert value.startswith(".. sdoc-comment: id=c7f3a9 author=anna.durand ")
    assert value.endswith("\n\nThis is not testable.")
    assert parse_comment(value) == comment


def test_002_markdown_round_trip():
    comment = _comment(
        status=STATUS_RESOLVED,
        resolved_by="paul",
        resolved_on="2026-10-11T08:00:00Z",
    )
    value = format_comment(comment, "Markdown")
    assert value.startswith("<!-- sdoc-comment id=c7f3a9 ")
    assert " -->\n\nThis is not testable." in value
    parsed = parse_comment(value)
    assert parsed == comment
    assert parsed.is_resolved


def test_003_a_comment_without_header_is_a_legacy_comment():
    comment = parse_comment("An old remark.\n\nOn two paragraphs.")
    assert comment.legacy
    assert comment.author == "" and comment.author_label == "unknown"
    assert comment.status == "open" and comment.date == ""
    assert comment.body == "An old remark.\n\nOn two paragraphs."


def test_004_unusual_characters_in_the_header_survive():
    comment = _comment(author="Éloïse d'Arc <e@x.fr>")
    for markup in ("RST", "Markdown"):
        assert parse_comment(format_comment(comment, markup)).author == (
            "Éloïse d'Arc <e@x.fr>"
        )
    # No space or "-->" can end the header early.
    value = format_comment(_comment(author="a --> b c"), "Markdown")
    assert value.splitlines()[0].count("-->") == 1


def test_005_a_damaged_header_is_read_leniently_and_the_text_is_kept():
    comment = parse_comment(
        ".. sdoc-comment: id=abc status=weird nonsense author=x unknown=1\n\nText."
    )
    assert (comment.id, comment.author, comment.status) == ("abc", "x", "open")
    assert comment.body == "Text."
    assert not comment.legacy


def test_006_the_body_may_contain_markup_and_blank_lines():
    body = "First.\n\n- one\n- two\n\n`code`"
    comment = _comment(body=body)
    for markup in ("RST", "Markdown"):
        assert parse_comment(format_comment(comment, markup)).body == body


def test_007_a_new_comment_gets_an_id_an_author_and_a_date():
    comment = Comment.new("anna", "  Needs a number.  ")
    assert comment.body == "Needs a number."
    assert len(comment.id) == 8 and comment.author == "anna"
    assert comment.date.endswith("Z") and comment.source == "web"
    assert Comment.new("anna", "x").id != comment.id


def test_008_initials():
    assert initials("anna.durand") == "AD"
    assert initials("laurent.carcagno") == "LC"
    assert initials("infra-admin") == "IA"
    assert initials("x") == "X"
    assert initials("") == "?"
    assert initials("a.b.c.d") == "ABC"


def test_anchor_is_stored_in_the_header_and_read_back():
    comment = Comment.new(
        "anna", "Why?", anchor="start  within\n2 s", anchor_n=2
    )
    assert comment.anchor == "start within 2 s" and comment.anchor_n == "2"
    for markup in ("RST", "Markdown"):
        read = parse_comment(format_comment(comment, markup))
        assert (read.anchor, read.anchor_n) == ("start within 2 s", "2")
    plain = Comment.new("anna", "Why?")
    assert plain.anchor == "" and plain.anchor_n == ""
    assert "anchor" not in format_comment(plain, "RST")
    assert len(clean_anchor("x" * 500)) == 200
