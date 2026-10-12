"""
The languages of the interface and the language of the process.

No third-party import here: the project configuration imports this module,
and tasks.py imports the project configuration before any dependency of
StrictDoc is installed. The translation itself is in i18n.py.
"""

from typing import Tuple

LANGUAGES: Tuple[str, ...] = ("en", "fr")
DEFAULT_LANGUAGE = "en"

_current_language = DEFAULT_LANGUAGE


def validate_language(language: str) -> str:
    """The language, or ValueError when it is not one of LANGUAGES."""
    if language not in LANGUAGES:
        raise ValueError(
            f"expected one of {', '.join(LANGUAGES)}, got '{language}'."
        )
    return language


def set_language(language: str) -> None:
    global _current_language  # noqa: PLW0603
    _current_language = validate_language(language)


def get_language() -> str:
    return _current_language
