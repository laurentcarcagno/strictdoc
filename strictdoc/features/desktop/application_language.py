"""
The language of the desktop application: one for the home screen and for every
project, the one that the user chose in the settings.

A process has one language (features/i18n), and a project sets it when its
configuration is read (ProjectConfig.validate_and_finalize), so opening a
project of another language would change the language of the whole
application. The language of a project is not used here: the application
publishes its language in the variable STRICTDOC_LANGUAGE, which the
configuration of a project reads before the language of the project file, so
every project is read in the language of the application.

The variable STRICTDOC_LANGUAGE that the application started with is the
default, for a user who chose no language.

@relation(SDOC-SRS-1252, scope=file)
"""

import os
import threading
from typing import Optional

from strictdoc.features.desktop.settings import DesktopSettings
from strictdoc.features.i18n.languages import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    set_language,
)

LANGUAGE_VARIABLE = "STRICTDOC_LANGUAGE"

_lock: threading.Lock = threading.Lock()
# The value of the variable before the application changed it, and the value
# that the application gave it.
_default_language: Optional[str] = None
_published_language: Optional[str] = None


def get_default_language() -> str:
    """The language when the user chose none: the variable, else English."""
    _remember_default()
    assert _default_language is not None
    return (
        _default_language
        if _default_language in LANGUAGES
        else DEFAULT_LANGUAGE
    )


def get_application_language(settings: DesktopSettings) -> str:
    """The language of the user, or else the default one."""
    if settings.language in LANGUAGES:
        return settings.language
    return get_default_language()


def apply_application_language(settings: DesktopSettings) -> str:
    """
    Make the language of the settings the one of the process and of every
    project that is read from now on. It returns the language.
    """
    global _published_language  # noqa: PLW0603
    # Before the variable is changed: it is the default of the user.
    _remember_default()
    language = get_application_language(settings)
    with _lock:
        os.environ[LANGUAGE_VARIABLE] = language
        _published_language = language
        set_language(language)
    return language


def restore_application_language() -> None:
    """
    Give the process the language of the application again, whatever a
    configuration read since. Nothing happens before the application chose.
    """
    with _lock:
        if _published_language is not None:
            set_language(_published_language)


def _remember_default() -> None:
    global _default_language  # noqa: PLW0603
    with _lock:
        value = os.environ.get(LANGUAGE_VARIABLE, "")
        if _default_language is None or value != _published_language:
            # The variable is not the one that the application gave: it is
            # what the user or the deployment set.
            _default_language = value
