from strictdoc.export.html.renderers.html_fragment_writer import (
    HTMLFragmentWriter,
)


def test_write_anchor_link():
    result = HTMLFragmentWriter.write_anchor_link(
        "REQ-001", "../requirements/REQ-001.html#REQ-001"
    )
    assert (
        result
        == '<a href="../requirements/REQ-001.html#REQ-001">🔗&nbsp;REQ-001</a>'
    )


def test_write_keeps_the_allowed_html():
    html = '<p class="note">A <b>bold</b> <a href="https://x.org/">link</a></p>'

    assert str(HTMLFragmentWriter.write(html)) == html


def test_write_does_not_let_scripts_and_handlers_through():
    result = str(
        HTMLFragmentWriter.write(
            '<p onclick="alert(1)">Hi</p><script>alert(2)</script>'
            '<a href="javascript:alert(3)">x</a>'
            '<iframe src="https://x.org"></iframe>'
        )
    )

    assert "onclick" not in result
    assert "<script" not in result and "&lt;script" in result
    assert "javascript:" not in result
    assert "<iframe" not in result
    assert "<p>Hi</p>" in result
