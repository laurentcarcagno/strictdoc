"""
@relation(SDOC-SRS-24, scope=file)
"""

from markupsafe import Markup

from strictdoc.backend.markdown.html_sanitizer import sanitize_html_fragment


class HTMLFragmentWriter:
    @staticmethod
    def write(text_fragment: str) -> Markup:
        # The field is HTML written by an author: only the allowed elements
        # and attributes are kept, as for the raw HTML of a Markdown field.
        return Markup(sanitize_html_fragment(text_fragment))

    @staticmethod
    def write_anchor_link(title: str, href: str) -> str:
        return f'<a href="{href}">🔗&nbsp;{title}</a>'
