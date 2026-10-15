"""
The project option ``git``: configuration management of the documents.

The token of the GitLab instance is named, never written: ``token_env`` is the
NAME of an environment variable.
"""

import urllib.parse
from dataclasses import dataclass

from strictdoc.helpers.exception import StrictDocException


@dataclass
class GitConfig:
    # The one author of every commit and tag made by StrictDoc.
    author_name: str = "Laurent Carcagno"
    author_email: str = "laurent.carcagno@hemeria-group.com"
    gitlab_url: str = "https://gitlab.karka.lan"
    token_env: str = "GITLAB_TOKEN"
    # The group (with its parents) where the repositories of the projects that
    # the web interface creates are made on the GitLab instance.
    group_path: str = "documentation/projects"
    # Push the commits and the new tag when a version tag is created.
    push_on_tag: bool = True
    # Path of a CA bundle for an instance behind TLS inspection. The
    # verification is never switched off.
    ca_bundle: str = ""
    # Write .gitattributes so that _assets/ goes through Git LFS.
    use_lfs: bool = False
    # Warn when an uploaded asset is larger than this, in bytes.
    asset_warning_bytes: int = 5 * 1024 * 1024

    def validate(self) -> None:
        parsed = urllib.parse.urlparse(self.gitlab_url)
        if parsed.scheme not in ("https", "http") or parsed.netloc == "":
            raise StrictDocException(
                f"config: git: gitlab_url is not a URL: {self.gitlab_url!r}."
            )
        if self.author_name.strip() == "" or "@" not in self.author_email:
            raise StrictDocException(
                "config: git: author_name and author_email are needed."
            )
        if self.token_env.strip() == "":
            raise StrictDocException("config: git: token_env is empty.")
        if self.asset_warning_bytes < 0:
            raise StrictDocException(
                "config: git: asset_warning_bytes is negative."
            )
