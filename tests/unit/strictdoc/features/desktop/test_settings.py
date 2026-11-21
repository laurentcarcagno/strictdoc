"""
@relation(SDOC-SRS-1223, scope=file)
@relation(SDOC-SRS-1224, scope=file)
"""

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import platformdirs
import pytest

from strictdoc.features.desktop.secret_store import MemorySecretStore
from strictdoc.features.desktop.settings import (
    AiServer,
    DesktopSettings,
    get_ai_secret_name,
    get_settings_path,
    is_ai_server_complete,
    load_settings,
    save_settings,
)


@pytest.fixture(name="settings_path")
def fixture_settings_path(tmp_path: Path) -> Path:
    return tmp_path / "config" / "settings.json"


def test_001_settings_path_is_in_the_config_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # platformdirs reads XDG_* only on Linux, so the function is replaced.
    def get_config_folder(appname: str, *args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return str(tmp_path / "config" / appname)

    monkeypatch.setattr(platformdirs, "user_config_dir", get_config_folder)

    assert get_settings_path() == (
        tmp_path / "config" / "StrictDoc" / "settings.json"
    )


def test_002_missing_file_gives_the_defaults(settings_path: Path) -> None:
    settings = load_settings(settings_path)

    assert settings == DesktopSettings()
    assert settings.catalog_provider == "gitlab"
    assert settings.gitlab_url == ""
    assert settings.kept_servers == 3
    assert settings.project_folders == {}
    assert settings.ai_servers == []
    assert not settings_path.exists()


def test_003_round_trip(settings_path: Path) -> None:
    settings = DesktopSettings(
        gitlab_url="https://gitlab.example.org",
        kept_servers=5,
        project_folders={"group/project": "/data/project"},
        ai_servers=[
            AiServer(
                server_id="id-1",
                name="Ollama",
                url="http://ollama.local:11434/v1",
                is_internal=True,
                model="qwen",
            ),
            AiServer.create(name="Mistral", url="https://api.mistral.ai/v1"),
        ],
    )

    save_settings(settings, settings_path)

    assert load_settings(settings_path) == settings


def test_004_unknown_fields_and_wrong_types_are_ignored(
    settings_path: Path,
) -> None:
    settings_path.parent.mkdir(parents=True)
    content: Any = {
        "schema_version": 99,
        "future_option": True,
        "gitlab_url": "https://gitlab.example.org",
        "kept_servers": "many",
        "project_folders": {"a": "/a", "b": 3},
        "ai_servers": [
            "not a server",
            {"name": "no identifier"},
            {"server_id": "id-1", "url": "http://x", "extra": 1},
        ],
    }
    settings_path.write_text(json.dumps(content), encoding="utf-8")

    settings = load_settings(settings_path)

    assert settings.gitlab_url == "https://gitlab.example.org"
    assert settings.kept_servers == 3
    assert settings.project_folders == {"a": "/a"}
    assert settings.ai_servers == [AiServer(server_id="id-1", url="http://x")]


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '"text"', ""])
def test_005_invalid_json_is_renamed_and_gives_the_defaults(
    settings_path: Path, text: str
) -> None:
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(text, encoding="utf-8")

    settings = load_settings(settings_path)

    assert settings == DesktopSettings()
    assert not settings_path.exists()
    invalid_path = settings_path.with_name("settings.json.invalid")
    assert invalid_path.read_text(encoding="utf-8") == text


def test_005b_deeply_nested_json_is_renamed(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("[" * 200000, encoding="utf-8")

    assert load_settings(settings_path) == DesktopSettings()
    assert not settings_path.exists()
    assert settings_path.with_name("settings.json.invalid").exists()


def test_006_file_that_is_not_utf8_is_renamed(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True)
    settings_path.write_bytes(b"\xff\xfe\x00{")

    assert load_settings(settings_path) == DesktopSettings()
    assert settings_path.with_name("settings.json.invalid").exists()


def test_007_failed_replace_keeps_the_previous_file_and_no_partial_file(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_settings(
        DesktopSettings(gitlab_url="https://old.example.org"), (settings_path)
    )
    previous_content = settings_path.read_text(encoding="utf-8")

    def failing_replace(*arguments: Any) -> None:  # noqa: ARG001
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="replace failed"):
        save_settings(
            DesktopSettings(gitlab_url="https://new.example.org"),
            settings_path,
        )
    monkeypatch.undo()

    assert settings_path.read_text(encoding="utf-8") == previous_content
    assert [path_.name for path_ in settings_path.parent.iterdir()] == [
        "settings.json"
    ]


def test_008_failed_first_write_leaves_no_file(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_fsync(*arguments: Any) -> None:  # noqa: ARG001
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="disk full"):
        save_settings(DesktopSettings(), settings_path)
    monkeypatch.undo()

    assert list(settings_path.parent.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_009_file_is_private_to_the_user(settings_path: Path) -> None:
    save_settings(DesktopSettings(), settings_path)

    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600


def test_010_key_of_an_ai_server_is_not_in_the_settings_file(
    settings_path: Path,
) -> None:
    secret_store = MemorySecretStore()
    server = AiServer.create(name="Mistral", url="https://api.mistral.ai/v1")
    secret_store.set(get_ai_secret_name(server.server_id), "sk-very-secret")

    save_settings(DesktopSettings(ai_servers=[server]), settings_path)

    assert "sk-very-secret" not in settings_path.read_text(encoding="utf-8")
    assert get_ai_secret_name(server.server_id) == f"ai/{server.server_id}"
    assert secret_store.get(f"ai/{server.server_id}") == "sk-very-secret"


def test_011_external_server_needs_a_url_and_a_key() -> None:
    secret_store = MemorySecretStore()
    server = AiServer(server_id="id-1", url="https://api.example.org")

    assert is_ai_server_complete(server, secret_store) is False

    secret_store.set("ai/id-1", "  ")
    assert is_ai_server_complete(server, secret_store) is False

    secret_store.set("ai/id-1", "sk-key")
    assert is_ai_server_complete(server, secret_store) is True

    no_url = AiServer(server_id="id-1", url=" ")
    assert is_ai_server_complete(no_url, secret_store) is False

    secret_store.delete("ai/id-1")
    assert is_ai_server_complete(server, secret_store) is False


def test_012_internal_server_needs_only_a_url() -> None:
    secret_store = MemorySecretStore()
    server = AiServer(
        server_id="id-2", url="http://ollama.local:11434", is_internal=True
    )

    assert is_ai_server_complete(server, secret_store) is True
    assert (
        is_ai_server_complete(
            AiServer(server_id="id-2", url="", is_internal=True), secret_store
        )
        is False
    )
