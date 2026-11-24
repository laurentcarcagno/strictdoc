"""
The words of the application: the texts of the shared templates that say
"commit", "tag" or "revision" are said in words of work in the pages of a
project of the desktop application, and the web server keeps its own.

The templates are shared, so they are not changed. The Jinja environment of
the project of the application gets another "gettext" function: for a text
that is in the table below, it translates the text of the table instead. The
table holds English texts and the .po catalog has their translations. A text
that is not in the table goes through the usual function.

The pages of the application show the versions of the project (a letter and a
number, "A1", "B"), never a tag, a commit or an identifier of a commit.

@relation(SDOC-SRS-1248, scope=file)
"""

from typing import Any, Dict

from jinja2 import Environment, pass_context
from jinja2.runtime import Context

from strictdoc.features.i18n.i18n import _template_gettext

# The text of the shared template -> the text that the application shows.
APPLICATION_TEXTS: Dict[str, str] = {
    "No commit changed this item yet.": (
        "No change has been saved for this item yet."
    ),
    "This document has no version tag yet.": (
        "This document has no version yet."
    ),
    "Export to PDF without revision marks": (
        "Export to PDF without change marks"
    ),
    "Latest version tag of the repository that holds this document": (
        "Latest version of the project"
    ),
    "Configuration management is not activated, so the history is not "
    "recorded.": "The history of this project is not recorded.",
}


def install_application_wording(environment: Environment) -> None:
    """Use the words of the application in the templates of this environment."""
    environment.globals["gettext"] = _get_application_text


@pass_context
def _get_application_text(
    context: Context, message: str, **variables: Any
) -> str:
    return _template_gettext(
        context, APPLICATION_TEXTS.get(message, message), **variables
    )
