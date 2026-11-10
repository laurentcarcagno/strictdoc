"""
The version of a document that the page header shows: the latest version
tag (A1, A2, A, B1... see versioning.py) of the git repository that holds
the document file.

@relation(SDOC-SRS-210, scope=file)
"""

import os
from typing import Optional

from git import InvalidGitRepositoryError, NoSuchPathError, Repo

from strictdoc.features.git_config.versioning import latest_valid_tag


def latest_version_of_file(path: str) -> Optional[str]:
    """
    The latest version tag of the repository that holds the file, or None
    when the file is in no repository or the repository has no version tag.
    """
    folder = os.path.dirname(os.path.abspath(path))
    try:
        repo = Repo(folder, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError, OSError):
        return None
    tag = latest_valid_tag(tag_.name for tag_ in repo.tags)
    if len(tag) == 0:
        return None
    return tag
