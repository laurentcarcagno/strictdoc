"""
Updates the catalogs of the interface (strictdoc/features/i18n/locales).

Collects the texts to translate:
- templates: _("...") and {% trans %} (the i18n extension of Jinja),
- Python: gettext("...") and ngettext(...) of strictdoc/features/i18n,
- scripts: sdocT("...") (window.sdocT of the pages),
and merges them into the catalog of each language: a new text arrives empty,
a text that is gone is removed, the translations are kept.

    python developer/i18n/update_catalogs.py

Needs Babel and Jinja (the environment of StrictDoc).
"""

import os
import sys
from typing import Any, Dict, List, Tuple

from babel.messages.catalog import Catalog

ROOT_FOR_IMPORTS = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
sys.path.insert(0, ROOT_FOR_IMPORTS)
from babel.messages.extract import extract_from_dir
from babel.messages.pofile import read_po, write_po

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SOURCE = os.path.join(ROOT, "strictdoc")
LOCALES = os.path.join(SOURCE, "features", "i18n", "locales")
DOMAIN = "strictdoc"

# Third-party bundles are not ours to translate.
SKIP = ("milkdown", "mathjax", "mermaid", "plantuml", ".min.js")

METHODS: List[Tuple[str, str]] = [
    ("**/templates/**.jinja", "jinja2"),
    ("**/templates/**.jinja.html", "jinja2"),
    ("**/templates/**.html", "jinja2"),
    ("**.py", "python"),
    ("**.js", "javascript"),
]
# The templates use {% assert %} of StrictDoc: without its extension, Jinja
# cannot parse them and Babel skips them.
JINJA_EXTENSIONS = (
    "jinja2.ext.i18n,"
    "strictdoc.export.html.jinja.assert_extension.AssertExtension"
)
OPTIONS: Dict[str, Dict[str, Any]] = {
    # silent=false: a template that Jinja cannot parse stops the update.
    "**/templates/**.jinja": {
        "extensions": JINJA_EXTENSIONS,
        "silent": "false",
    },
    "**/templates/**.jinja.html": {
        "extensions": JINJA_EXTENSIONS,
        "silent": "false",
    },
    "**/templates/**.html": {"extensions": JINJA_EXTENSIONS, "silent": "false"},
}
KEYWORDS = {
    "_": None,
    "gettext": None,
    "ngettext": (1, 2),
    "sdocT": None,
}


def collect() -> Catalog:
    template = Catalog(domain=DOMAIN)
    for filename, lineno, message, comments, context in extract_from_dir(
        SOURCE,
        method_map=METHODS,
        options_map=OPTIONS,
        keywords=KEYWORDS,
        comment_tags=("i18n:",),
        callback=None,
        strip_comment_tags=True,
        # Babel skips the folders that start with "_" by default; StrictDoc
        # keeps templates in _shared and scripts in _static.
        directory_filter=lambda path_: (
            not os.path.basename(path_).startswith((".", "__pycache__"))
        ),
    ):
        if any(skip_ in filename for skip_ in SKIP):
            continue
        location = (
            os.path.join("strictdoc", filename).replace("\\", "/"),
            lineno,
        )
        template.add(
            message,
            None,
            [location],
            auto_comments=comments,
            context=context,
        )
    return template


def main() -> int:
    template = collect()
    for language in sorted(os.listdir(LOCALES)):
        path = os.path.join(LOCALES, language, "LC_MESSAGES", f"{DOMAIN}.po")
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as file_:
            catalog = read_po(file_, locale=language, domain=DOMAIN)
        catalog.update(template, no_fuzzy_matching=True)
        catalog.obsolete.clear()
        with open(path, "wb") as file_:
            write_po(
                file_, catalog, width=79, sort_output=True, omit_header=False
            )
        untranslated = sum(
            1 for message_ in catalog if message_.id and not message_.string
        )
        print(  # noqa: T201
            f"{language}: {len(catalog)} texts, {untranslated} to translate."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
