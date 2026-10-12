"""
The language of the interface.

One language per process: the project option `language` ("en", the default,
or "fr"), which the environment variable STRICTDOC_LANGUAGE overrides. The
texts of the interface are English in the templates and in the code; a
catalog per language (locales/<language>/LC_MESSAGES/strictdoc.po) gives
their translation. A text that a catalog does not translate stays English.

Templates use _() and {% trans %} (the i18n extension of Jinja), the code
uses gettext() of this module, and the scripts of the pages use
window.sdocT(), which reads the catalog that the page embeds.
"""

import gettext as gettext_module
import io
import os
from functools import lru_cache
from typing import Dict

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from jinja2 import Environment

from strictdoc.features.i18n.languages import (  # noqa: F401 (re-exported)
    DEFAULT_LANGUAGE,
    LANGUAGES,
    get_language,
    set_language,
    validate_language,
)

DOMAIN = "strictdoc"
LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")


@lru_cache(maxsize=None)
def _translations(language: str) -> gettext_module.NullTranslations:
    """The translations of a language, read from its .po catalog."""
    path = os.path.join(LOCALES_DIR, language, "LC_MESSAGES", f"{DOMAIN}.po")
    if not os.path.isfile(path):
        return gettext_module.NullTranslations()
    with open(path, "rb") as file_:
        catalog = read_po(file_, locale=language, domain=DOMAIN)
    buffer = io.BytesIO()
    write_mo(buffer, catalog)
    buffer.seek(0)
    return gettext_module.GNUTranslations(buffer)


def gettext(message: str) -> str:
    return _translations(get_language()).gettext(message)


def ngettext(singular: str, plural: str, number: int) -> str:
    return _translations(get_language()).ngettext(singular, plural, number)


def js_catalog() -> Dict[str, str]:
    """The translated texts of the current language, for window.sdocT()."""
    translations = _translations(get_language())
    catalog = getattr(translations, "_catalog", {})
    return {
        key_: value_
        for key_, value_ in catalog.items()
        if isinstance(key_, str) and key_ and value_ and key_ != value_
    }


def install(environment: Environment) -> None:
    """
    Adds the i18n extension to a Jinja environment. The callables read the
    current language when a template is rendered, so compiled templates
    follow the language too.
    """
    environment.add_extension("jinja2.ext.i18n")
    environment.install_gettext_callables(  # type: ignore[attr-defined]
        gettext, ngettext, newstyle=True
    )
    environment.globals["sdoc_language"] = get_language
    environment.globals["sdoc_js_catalog"] = js_catalog
