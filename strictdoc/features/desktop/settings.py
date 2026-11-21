"""
The settings of the desktop application, in a JSON file of the user.

The file holds no secret: the keys of the AI servers are in a SecretStore.

@relation(SDOC-SRS-1223, scope=file)
@relation(SDOC-SRS-1224, scope=file)
"""

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from strictdoc.features.desktop.paths import get_config_dir
from strictdoc.features.desktop.secret_store import SecretStore
from strictdoc.helpers.file_system import file_open_read_utf8

SETTINGS_FILE_NAME = "settings.json"
SETTINGS_SCHEMA_VERSION = 1
DEFAULT_CATALOG_PROVIDER = "gitlab"
DEFAULT_KEPT_SERVERS = 3
DEFAULT_GITLAB_PROJECTS_ROOT = "HERMES/DOCUMENTATION/PROJETS"

_INVALID_FILE_SUFFIX = ".invalid"
_AI_SECRET_PREFIX = "ai/"


@dataclass
class AiServer:
    """An AI server. Its key, if any, is in the SecretStore."""

    server_id: str
    name: str = ""
    url: str = ""
    # Internal: a server of the company (Ollama, vLLM, STRATA). External: a
    # service outside the company (Mistral, Anthropic).
    is_internal: bool = False
    model: str = ""

    @classmethod
    def create(cls, **fields: Any) -> "AiServer":
        """A server with a new stable identifier."""
        return cls(server_id=uuid.uuid4().hex, **fields)


@dataclass
class DesktopSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    catalog_provider: str = DEFAULT_CATALOG_PROVIDER
    gitlab_url: str = ""
    # The GitLab group whose projects, sub-groups included, form the catalog.
    gitlab_projects_root: str = DEFAULT_GITLAB_PROJECTS_ROOT
    # The JSON file of the "fake" catalog provider. Empty: none.
    fake_catalog_path: str = ""
    # How many project servers stay open at the same time.
    kept_servers: int = DEFAULT_KEPT_SERVERS
    # Identifier of a project -> the folder of the project on the disk.
    project_folders: Dict[str, str] = field(default_factory=dict)
    ai_servers: List[AiServer] = field(default_factory=list)


def get_settings_path() -> Path:
    return get_config_dir() / SETTINGS_FILE_NAME


def get_ai_secret_name(server_id: str) -> str:
    """The name of the key of an AI server in the SecretStore."""
    return f"{_AI_SECRET_PREFIX}{server_id}"


def is_ai_server_complete(server: AiServer, secret_store: SecretStore) -> bool:
    """
    Tell whether the AI buttons can use the server.

    An external server needs a URL and a key. An internal server needs a URL
    and its key is optional.
    """
    if len(server.url.strip()) == 0:
        return False
    if server.is_internal:
        return True
    key = secret_store.get(get_ai_secret_name(server.server_id))
    return key is not None and len(key.strip()) > 0


def load_settings(path: Optional[Path] = None) -> DesktopSettings:
    """
    Read the settings. This never fails because of the content of the file.

    A missing file gives the default settings. So does a file that is not a
    JSON object: it is first renamed with the suffix ".invalid", so that the
    next save does not destroy it. Unknown fields are ignored.
    """
    settings_path = path if path is not None else get_settings_path()
    if not settings_path.is_file():
        return DesktopSettings()
    try:
        with file_open_read_utf8(str(settings_path)) as file_:
            content = json.load(file_)
    except (ValueError, RecursionError):
        # ValueError covers the JSON errors and UnicodeDecodeError. A file
        # of deeply nested brackets raises RecursionError.
        content = None
    if not isinstance(content, dict):
        os.replace(
            settings_path,
            settings_path.with_name(settings_path.name + _INVALID_FILE_SUFFIX),
        )
        return DesktopSettings()
    return _settings_from_dict(content)


def save_settings(
    settings: DesktopSettings, path: Optional[Path] = None
) -> None:
    """
    Write the settings atomically.

    The content goes to a temporary file in the same folder, then replaces the
    settings file. A failure leaves the previous file as it was. The temporary
    file is private to the user on POSIX systems.
    """
    settings_path = path if path is not None else get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(_settings_to_dict(settings), indent=2) + "\n"

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=settings_path.parent, prefix=settings_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file_:
            file_.write(content)
            file_.flush()
            os.fsync(file_.fileno())
        os.replace(temporary_name, settings_path)
    except BaseException:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise


def _settings_to_dict(settings: DesktopSettings) -> Dict[str, Any]:
    return {
        "schema_version": settings.schema_version,
        "catalog_provider": settings.catalog_provider,
        "gitlab_url": settings.gitlab_url,
        "gitlab_projects_root": settings.gitlab_projects_root,
        "fake_catalog_path": settings.fake_catalog_path,
        "kept_servers": settings.kept_servers,
        "project_folders": dict(settings.project_folders),
        "ai_servers": [
            {
                "server_id": server_.server_id,
                "name": server_.name,
                "url": server_.url,
                "is_internal": server_.is_internal,
                "model": server_.model,
            }
            for server_ in settings.ai_servers
        ],
    }


def _settings_from_dict(content: Dict[str, Any]) -> DesktopSettings:
    defaults = DesktopSettings()
    kept_servers = content.get("kept_servers")
    project_folders = content.get("project_folders")
    ai_servers = content.get("ai_servers")
    return DesktopSettings(
        schema_version=SETTINGS_SCHEMA_VERSION,
        catalog_provider=_get_str(
            content, "catalog_provider", defaults.catalog_provider
        ),
        gitlab_url=_get_str(content, "gitlab_url", defaults.gitlab_url),
        gitlab_projects_root=_get_str(
            content, "gitlab_projects_root", defaults.gitlab_projects_root
        ),
        fake_catalog_path=_get_str(
            content, "fake_catalog_path", defaults.fake_catalog_path
        ),
        kept_servers=(
            kept_servers
            if isinstance(kept_servers, int)
            and not isinstance(kept_servers, bool)
            and kept_servers >= 1
            else defaults.kept_servers
        ),
        project_folders=(
            {
                key_: value_
                for key_, value_ in project_folders.items()
                if isinstance(key_, str) and isinstance(value_, str)
            }
            if isinstance(project_folders, dict)
            else {}
        ),
        ai_servers=(
            [
                server_
                for server_ in (
                    _ai_server_from_dict(item_) for item_ in ai_servers
                )
                if server_ is not None
            ]
            if isinstance(ai_servers, list)
            else []
        ),
    )


def _ai_server_from_dict(content: Any) -> Optional[AiServer]:
    if not isinstance(content, dict):
        return None
    server_id = content.get("server_id")
    if not isinstance(server_id, str) or len(server_id) == 0:
        return None
    is_internal = content.get("is_internal")
    return AiServer(
        server_id=server_id,
        name=_get_str(content, "name", ""),
        url=_get_str(content, "url", ""),
        is_internal=is_internal if isinstance(is_internal, bool) else False,
        model=_get_str(content, "model", ""),
    )


def _get_str(content: Dict[str, Any], key: str, default: str) -> str:
    value = content.get(key)
    return value if isinstance(value, str) else default
