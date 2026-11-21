"""
A catalog read from a JSON file, for the tests and the demonstration.

The file holds a list of objects with the fields of CatalogProject. The role
is one of "reader", "author" and "administrator".

@relation(SDOC-SRS-1226, scope=file)
"""

import json
from typing import Any, Dict, List

from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    CatalogProject,
    CatalogRole,
    DesktopIdentity,
)
from strictdoc.helpers.file_system import file_open_read_utf8

_TEXT_FIELDS = (
    "identifier",
    "title",
    "display_path",
    "description",
    "clone_url",
)


class FakeCatalog:
    def __init__(self, path: str) -> None:
        self.path: str = path

    def list_projects(self, identity: DesktopIdentity) -> List[CatalogProject]:
        del identity
        try:
            with file_open_read_utf8(self.path) as file_:
                content = json.load(file_)
        except (OSError, ValueError) as exception_:
            raise CatalogError(
                f"The catalog file {self.path} cannot be read: {exception_}"
            ) from exception_
        if not isinstance(content, list):
            raise CatalogError(
                f"The catalog file {self.path} must hold a list of projects."
            )
        return [
            self._project_from_dict(item_, index_)
            for index_, item_ in enumerate(content)
        ]

    def _project_from_dict(self, item: Any, index: int) -> CatalogProject:
        if not isinstance(item, dict):
            raise CatalogError(
                f"Project {index} of the catalog file {self.path} must be an "
                "object."
            )
        values: Dict[str, str] = {}
        for field_ in _TEXT_FIELDS:
            value = item.get(field_)
            if not isinstance(value, str):
                raise CatalogError(
                    f"Project {index} of the catalog file {self.path} has no "
                    f"text field '{field_}'."
                )
            values[field_] = value
        try:
            role = CatalogRole(item.get("role"))
        except ValueError as exception_:
            raise CatalogError(
                f"Project {index} of the catalog file {self.path} has an "
                f"unknown role: {item.get('role')!r}."
            ) from exception_
        return CatalogProject(role=role, **values)
