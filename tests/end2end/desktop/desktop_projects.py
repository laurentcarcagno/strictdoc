"""
The projects that the end2end tests of the desktop application open: remotes
on the disk (bare repositories) and the catalog file that lists them.

@relation(SDOC-SRS-1230, scope=file)
"""

import json
import os
from pathlib import Path
from typing import Dict, List

from git import Actor, Repo

from strictdoc.features.desktop.settings import load_settings


def create_remote(root: str, name: str, document_title: str) -> str:
    """
    A bare repository with one document. It returns the URL of the remote,
    which is the "clone_url" of the project in the catalog.
    """
    work_path = os.path.join(root, f"{name}_work")
    os.makedirs(work_path)
    with open(
        os.path.join(work_path, "doc.sdoc"), "w", encoding="utf-8"
    ) as file_:
        file_.write(
            "[DOCUMENT]\n"
            f"TITLE: {document_title}\n"
            "\n"
            "[REQUIREMENT]\n"
            "UID: REQ-1\n"
            "TITLE: Braking\n"
            "STATEMENT: The system shall brake.\n"
        )
    work_repo = Repo.init(work_path)
    work_repo.index.add(["doc.sdoc"])
    actor = Actor("Test", "test@example.org")
    work_repo.index.commit("Add the document", author=actor, committer=actor)
    work_repo.close()
    bare_path = os.path.join(root, f"{name}.git")
    Repo.clone_from(work_path, bare_path, bare=True).close()
    return f"file://{bare_path}"


def add_document_to_remote(
    remote_url: str, work_path: str, file_name: str, document_title: str
) -> None:
    """Push a new document to the remote, as a colleague would."""
    repo = Repo.clone_from(remote_url, work_path)
    with open(
        os.path.join(work_path, file_name), "w", encoding="utf-8"
    ) as file_:
        file_.write(f"[DOCUMENT]\nTITLE: {document_title}\n")
    repo.index.add([file_name])
    actor = Actor("Colleague", "colleague@example.org")
    repo.index.commit("Add a document", author=actor, committer=actor)
    repo.remotes.origin.push()
    repo.close()


def write_catalog(catalog_path: str, projects: List[Dict[str, str]]) -> None:
    """
    Write the catalog file of the "fake" provider. A project is a dictionary
    with the keys "identifier", "title", "display_path" and "clone_url".
    """
    entries = [
        {"description": "", "role": "author", **project_}
        for project_ in projects
    ]
    with open(catalog_path, "w", encoding="utf-8") as file_:
        json.dump(entries, file_)


def get_project_folders(user_path: str) -> Dict[str, str]:
    """The folders that the application remembers, read in its settings."""
    settings_path = os.path.join(
        user_path, "config", "StrictDoc", "settings.json"
    )
    return load_settings(Path(settings_path)).project_folders
