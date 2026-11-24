"""
The settings of the desktop application, in a JSON file of the user.

The file holds no secret: the keys of the AI servers are in a SecretStore.

@relation(SDOC-SRS-1223, scope=file)
@relation(SDOC-SRS-1224, scope=file)
@relation(SDOC-SRS-1234, scope=file)
@relation(SDOC-SRS-1252, scope=file)
"""

import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from strictdoc.features.desktop.paths import get_config_dir
from strictdoc.features.desktop.secret_store import SecretStore
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.i18n.languages import LANGUAGES
from strictdoc.helpers.file_system import file_open_read_utf8

SETTINGS_FILE_NAME = "settings.json"
SETTINGS_SCHEMA_VERSION = 1
DEFAULT_CATALOG_PROVIDER = "gitlab"
DEFAULT_KEPT_SERVERS = 3
# How often an open project looks for the changes of the others, in minutes.
DEFAULT_SYNC_INTERVAL_MINUTES = 5
MINIMUM_SYNC_INTERVAL_MINUTES = 1
MAXIMUM_SYNC_INTERVAL_MINUTES = 120
DEFAULT_GITLAB_PROJECTS_ROOT = "HERMES/DOCUMENTATION/PROJETS"
# The test GitLab of the project and its OAuth application "strictdoc-desktop".
# The identifier is public (a native application has no secret).
TEST_GITLAB_URL = "https://gitlab.karka.lan"
TEST_OAUTH_CLIENT_ID = (
    "7504d842ee0753347afde76f167a6c3cbf81fc6434f758dd920691aad0b32787"
)

_INVALID_FILE_SUFFIX = ".invalid"
_AI_SECRET_PREFIX = "ai/"


AI_KIND_OPENAI = "openai"
AI_KIND_ANTHROPIC = "anthropic"
AI_KINDS = (AI_KIND_OPENAI, AI_KIND_ANTHROPIC)


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
    # The protocol: "openai" (the chat completions of OpenAI, spoken by
    # Ollama, vLLM, STRATA and Mistral) or "anthropic".
    kind: str = AI_KIND_OPENAI

    @classmethod
    def create(cls, **fields: Any) -> "AiServer":
        """A server with a new stable identifier."""
        return cls(server_id=uuid.uuid4().hex, **fields)


@dataclass
class DesktopSettings:
    schema_version: int = SETTINGS_SCHEMA_VERSION
    catalog_provider: str = DEFAULT_CATALOG_PROVIDER
    gitlab_url: str = ""
    # The identifier of the OAuth application of the sign-in to GitLab. The
    # loader gives the application of the test GitLab to the test GitLab only.
    oauth_client_id: str = ""
    # The GitLab group whose projects, sub-groups included, form the catalog.
    gitlab_projects_root: str = DEFAULT_GITLAB_PROJECTS_ROOT
    # The JSON file of the "fake" catalog provider. Empty: none.
    fake_catalog_path: str = ""
    # How many project servers stay open at the same time.
    kept_servers: int = DEFAULT_KEPT_SERVERS
    # The minutes between two synchronizations of an open project (1 to 120).
    sync_interval_minutes: int = DEFAULT_SYNC_INTERVAL_MINUTES
    # The language of the application: "en", "fr", or "" for the default (the
    # variable STRICTDOC_LANGUAGE, else English).
    language: str = ""
    # Identifier of a project -> the folder of the project on the disk.
    project_folders: Dict[str, str] = field(default_factory=dict)
    ai_servers: List[AiServer] = field(default_factory=list)


def get_settings_path() -> Path:
    return get_config_dir() / SETTINGS_FILE_NAME


def get_default_oauth_client_id(gitlab_url: str) -> str:
    """The application of the test GitLab for the test GitLab, else none."""
    if gitlab_url.strip().rstrip("/") == TEST_GITLAB_URL:
        return TEST_OAUTH_CLIENT_ID
    return ""


def get_ai_secret_name(server_id: str) -> str:
    """The name of the key of an AI server in the SecretStore."""
    return f"{_AI_SECRET_PREFIX}{server_id}"


def is_ai_server_internal(server: AiServer) -> bool:
    """
    Tell whether the data of the server stay in the company. The choice of the
    user counts, except for the services that are always outside: Anthropic,
    and Mistral (known by its host).
    """
    if server.kind == AI_KIND_ANTHROPIC or is_mistral_url(server.url):
        return False
    return server.is_internal


def is_mistral_url(url: str) -> bool:
    """True for an address of the service of Mistral."""
    hostname = urlsplit(url.strip()).hostname
    host = hostname.lower() if hostname is not None else ""
    return host == "mistral.ai" or host.endswith(".mistral.ai")


def is_ai_server_complete(server: AiServer, secret_store: SecretStore) -> bool:
    """
    Tell whether the AI buttons can use the server.

    An external server needs a URL and a key. An internal server needs a URL
    and its key is optional.
    """
    if len(server.url.strip()) == 0:
        return False
    if is_ai_server_internal(server):
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


@dataclass
class SettingsForm:
    """
    What the user typed in the screen of the settings, checked: the values to
    save, or a text for the user by field. Nothing is saved while a field has
    an error.
    """

    language: str = ""
    sync_interval_minutes: int = DEFAULT_SYNC_INTERVAL_MINUTES
    errors: Dict[str, str] = field(default_factory=dict)


def parse_settings_form(
    language: str, sync_interval_minutes: str
) -> SettingsForm:
    """
    Check the fields of the screen of the settings. The language is one of the
    languages, or empty for the default. The interval is a whole number of
    minutes from 1 to 120, with no sign and no fraction.
    """
    form = SettingsForm()
    if language.strip() in LANGUAGES or language.strip() == "":
        form.language = language.strip()
    else:
        form.errors["language"] = gettext("Choose English or French.")
    text = sync_interval_minutes.strip()
    if (
        len(text) <= len(str(MAXIMUM_SYNC_INTERVAL_MINUTES))
        and text.isascii()
        and text.isdigit()
        and MINIMUM_SYNC_INTERVAL_MINUTES
        <= int(text)
        <= MAXIMUM_SYNC_INTERVAL_MINUTES
    ):
        form.sync_interval_minutes = int(text)
    else:
        form.errors["sync_interval_minutes"] = gettext(
            "The time between two updates is a whole number of minutes, from "
            "1 to 120."
        )
    return form


def _settings_to_dict(settings: DesktopSettings) -> Dict[str, Any]:
    return {
        "schema_version": settings.schema_version,
        "catalog_provider": settings.catalog_provider,
        "gitlab_url": settings.gitlab_url,
        "oauth_client_id": settings.oauth_client_id,
        "gitlab_projects_root": settings.gitlab_projects_root,
        "fake_catalog_path": settings.fake_catalog_path,
        "kept_servers": settings.kept_servers,
        "sync_interval_minutes": settings.sync_interval_minutes,
        "language": settings.language,
        "project_folders": dict(settings.project_folders),
        "ai_servers": [
            {
                "server_id": server_.server_id,
                "name": server_.name,
                "url": server_.url,
                "is_internal": server_.is_internal,
                "model": server_.model,
                "kind": server_.kind,
            }
            for server_ in settings.ai_servers
        ],
    }


def _settings_from_dict(content: Dict[str, Any]) -> DesktopSettings:
    defaults = DesktopSettings()
    kept_servers = content.get("kept_servers")
    project_folders = content.get("project_folders")
    ai_servers = content.get("ai_servers")
    gitlab_url = _get_str(content, "gitlab_url", defaults.gitlab_url)
    return DesktopSettings(
        schema_version=SETTINGS_SCHEMA_VERSION,
        catalog_provider=_get_str(
            content, "catalog_provider", defaults.catalog_provider
        ),
        gitlab_url=gitlab_url,
        oauth_client_id=_get_str(
            content, "oauth_client_id", get_default_oauth_client_id(gitlab_url)
        ),
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
        sync_interval_minutes=_get_sync_interval(
            content.get("sync_interval_minutes"), defaults
        ),
        language=_get_language(content.get("language"), defaults),
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


def _get_language(value: Any, defaults: DesktopSettings) -> str:
    """The language of the user, or the default one for what is not one."""
    if isinstance(value, str) and value in LANGUAGES:
        return value
    return defaults.language


def _get_sync_interval(value: Any, defaults: DesktopSettings) -> int:
    """
    The minutes between two synchronizations. A number out of the limits is
    brought back to the nearest limit, and what is not a whole number gives
    the default: a file that someone edited never stops the application.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return defaults.sync_interval_minutes
    minutes: int = value
    return max(
        MINIMUM_SYNC_INTERVAL_MINUTES,
        min(minutes, MAXIMUM_SYNC_INTERVAL_MINUTES),
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
        kind=(
            content["kind"]
            if content.get("kind") in AI_KINDS
            else AI_KIND_OPENAI
        ),
    )


def _get_str(content: Dict[str, Any], key: str, default: str) -> str:
    value = content.get(key)
    return value if isinstance(value, str) else default
