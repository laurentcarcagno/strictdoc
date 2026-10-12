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
from typing import Any, Dict, Tuple

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from jinja2 import Environment
from jinja2.runtime import Context
from jinja2.utils import pass_context
from markupsafe import Markup

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
def _load(
    language: str,
) -> Tuple[gettext_module.NullTranslations, Dict[str, str]]:
    """
    The translations of a language, read from its .po catalog, and the
    translated texts that the scripts use (the texts found in a .js file).
    """
    path = os.path.join(LOCALES_DIR, language, "LC_MESSAGES", f"{DOMAIN}.po")
    if not os.path.isfile(path):
        return gettext_module.NullTranslations(), {}
    with open(path, "rb") as file_:
        catalog = read_po(file_, locale=language, domain=DOMAIN)
    scripts: Dict[str, str] = {}
    for message_ in catalog:
        if (
            isinstance(message_.id, str)
            and isinstance(message_.string, str)
            and message_.id
            and message_.string
            and any(
                location_[0].endswith(".js") for location_ in message_.locations
            )
        ):
            scripts[message_.id] = message_.string
    buffer = io.BytesIO()
    write_mo(buffer, catalog)
    buffer.seek(0)
    return gettext_module.GNUTranslations(buffer), scripts


def _translations(language: str) -> gettext_module.NullTranslations:
    return _load(language)[0]


def gettext(message: str) -> str:
    return _translations(get_language()).gettext(message)


def ngettext(singular: str, plural: str, number: int) -> str:
    return _translations(get_language()).ngettext(singular, plural, number)


def js_catalog() -> Dict[str, str]:
    """The translated texts of the scripts, for window.sdocT()."""
    return _load(get_language())[1]


@pass_context
def _template_gettext(context: Context, message: str, **variables: Any) -> str:
    """
    gettext() of the templates: the "new style" of Jinja (escaping, named
    placeholders). A function of the module, not a closure of Jinja, so that
    an environment can be pickled: the HTML export renders in several
    processes.
    """
    translated = gettext(message)
    if context.eval_ctx.autoescape:
        translated = Markup(translated)
    return translated % variables  # type: ignore[no-any-return]


@pass_context
def _template_ngettext(
    context: Context,
    singular: str,
    plural: str,
    number: int,
    **variables: Any,
) -> str:
    """ngettext() of the templates, as _template_gettext()."""
    variables.setdefault("num", number)
    translated = ngettext(singular, plural, number)
    if context.eval_ctx.autoescape:
        translated = Markup(translated)
    return translated % variables  # type: ignore[no-any-return]


def install(environment: Environment) -> None:
    """
    Adds the i18n extension to a Jinja environment. The callables read the
    current language when a template is rendered, so compiled templates
    follow the language too.
    """
    environment.add_extension("jinja2.ext.i18n")
    # {% trans %} and _() compile to calls with named variables.
    environment.newstyle_gettext = True  # type: ignore[attr-defined]
    environment.globals["gettext"] = _template_gettext
    environment.globals["ngettext"] = _template_ngettext
    environment.globals["sdoc_language"] = get_language
    environment.globals["sdoc_js_catalog"] = js_catalog
