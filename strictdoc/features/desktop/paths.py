"""
Folders of the desktop application.

@relation(SDOC-SRS-1225, scope=file)
"""

import hashlib
import os
from pathlib import Path

import platformdirs

APPLICATION_NAME = "StrictDoc"

_PROJECTS_FOLDER_NAME = "projects"
_OUTPUT_FOLDER_NAME = "output"
_SDOC_CACHE_FOLDER_NAME = "_cache"
_FINGERPRINT_LENGTH = 16


def get_config_dir() -> Path:
    """The folder of the settings of the user."""
    return Path(platformdirs.user_config_dir(APPLICATION_NAME, appauthor=False))


def get_cache_dir() -> Path:
    """The folder of the generated files of the user."""
    return Path(platformdirs.user_cache_dir(APPLICATION_NAME, appauthor=False))


def get_data_dir() -> Path:
    """The folder of the data of the application (the profile of the window)."""
    return Path(platformdirs.user_data_dir(APPLICATION_NAME, appauthor=False))


def get_project_fingerprint(project_path: str) -> str:
    """
    A short name that is stable for a folder and differs between folders.

    The name comes from the absolute path with the symbolic links resolved, so
    that a relative path and an absolute path give the same name.
    """
    absolute_path = os.path.normcase(os.path.realpath(project_path))
    digest = hashlib.sha256(absolute_path.encode("utf-8")).hexdigest()
    return digest[:_FINGERPRINT_LENGTH]


def get_project_cache_dir(project_path: str) -> Path:
    """The folder of the generated files of one project."""
    return (
        get_cache_dir()
        / _PROJECTS_FOLDER_NAME
        / get_project_fingerprint(project_path)
    )


def get_project_output_dir(project_path: str) -> Path:
    """The HTML output of one project."""
    return get_project_cache_dir(project_path) / _OUTPUT_FOLDER_NAME


def get_project_sdoc_cache_dir(project_path: str) -> Path:
    """The cache of the documents of one project."""
    return get_project_cache_dir(project_path) / _SDOC_CACHE_FOLDER_NAME
