"""
The AI servers of the application: the form, the keys, the configuration of
the assistant that follows, the policy of the external servers, and the list
of the models.

@relation(SDOC-SRS-1253, scope=file)
@relation(SDOC-SRS-1254, scope=file)
@relation(SDOC-SRS-1255, scope=file)
"""

import json
import os
import sys
import threading
from dataclasses import dataclass, fields
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from starlette.testclient import TestClient

from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.features.desktop.ai_policy import (
    POLICY_FILE_NAME,
    AiPolicy,
    PolicyState,
    configure_policy_paths,
    get_policy_message,
    get_policy_paths,
    load_ai_policy,
)
from strictdoc.features.desktop.ai_settings import (
    AiRuntime,
    build_llm_config,
    delete_ai_server,
    get_key_variable,
    get_provider_environment,
    list_models,
    parse_ai_server_form,
    save_ai_server,
)
from strictdoc.features.desktop.home_app import create_home_app
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
)
from strictdoc.features.desktop.secret_store import (
    MemorySecretStore,
    SecretStoreError,
)
from strictdoc.features.desktop.session_token import (
    DesktopSessionMiddleware,
    SessionCredentials,
    get_session_cookie_name,
)
from strictdoc.features.desktop.settings import (
    AI_KIND_ANTHROPIC,
    AI_KIND_OPENAI,
    AiServer,
    DesktopSettings,
    get_ai_secret_name,
    load_settings,
    save_settings,
)
from strictdoc.features.i18n import i18n
from strictdoc.features.llm.audit import LLMAudit, LLMCall
from strictdoc.features.llm.config import Anthropic, LLMConfig, OpenAICompatible
from strictdoc.features.llm.policy import Policy, PolicyError
from strictdoc.features.llm.providers import create_provider
from strictdoc.features.llm.types import LLMRequest

KEY = "sk-secret-0123456789"
VALID_POLICY = AiPolicy(
    PolicyState.VALID,
    blocked_classifications=["Secret"],
    monthly_token_budget=1000,
)
ABSENT_POLICY = AiPolicy(PolicyState.ABSENT)
INVALID_POLICY = AiPolicy(PolicyState.INVALID)


def _parse(**fields: Any) -> Any:
    values: Dict[str, Any] = {
        "server_id": "",
        "name": "Ollama",
        "kind": AI_KIND_OPENAI,
        "url": "http://ollama.company.lan:11434/v1",
        "model": "llama3",
        "is_internal": True,
        "key": "",
        "clear_key": False,
        "other_names": [],
    }
    values.update(fields)
    return parse_ai_server_form(**values)


def _server(**fields: Any) -> AiServer:
    values: Dict[str, Any] = {
        "name": "Ollama",
        "url": "http://ollama.company.lan:11434/v1",
        "is_internal": True,
        "model": "llama3",
    }
    values.update(fields)
    return AiServer.create(**values)


# The form.


def test_001_a_server_of_the_company_may_use_http_and_has_no_key() -> None:
    form = _parse()

    assert form.errors == {}
    assert form.url == "http://ollama.company.lan:11434/v1"


@pytest.mark.parametrize(
    "fields",
    [
        {"is_internal": False},
        {"kind": AI_KIND_ANTHROPIC, "url": "http://api.anthropic.com"},
        {"url": "http://api.mistral.ai/v1", "is_internal": True},
        {"url": "http://eu.api.mistral.ai/v1", "is_internal": True},
    ],
)
def test_002_an_external_server_needs_https(fields: Dict[str, Any]) -> None:
    form = _parse(**fields)

    assert list(form.errors) == ["url"]
    assert "https" in form.errors["url"]


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": AI_KIND_ANTHROPIC, "url": "https://api.anthropic.com"},
        {"url": "https://api.mistral.ai/v1", "is_internal": True},
        {"url": "https://api.example.org/v1", "is_internal": False},
    ],
)
def test_003_https_is_accepted_for_an_external_server(
    fields: Dict[str, Any],
) -> None:
    assert _parse(**fields).errors == {}


def test_004_anthropic_has_its_address_by_default() -> None:
    form = _parse(kind=AI_KIND_ANTHROPIC, url="", is_internal=True)

    assert form.errors == {}
    assert form.url == "https://api.anthropic.com"


@pytest.mark.parametrize(
    ("fields", "field_name"),
    [
        ({"name": ""}, "name"),
        ({"name": "x" * 61}, "name"),
        ({"name": "ollama", "other_names": ["Ollama"]}, "name"),
        ({"kind": "gemini"}, "kind"),
        ({"url": ""}, "url"),
        ({"url": "ftp://server/v1"}, "url"),
        ({"url": "http://"}, "url"),
        ({"url": "http://user:pass@server/v1"}, "url"),
        ({"url": "http://server:notaport/v1"}, "url"),
        ({"url": "http://ser ver/v1"}, "url"),
        ({"model": ""}, "model"),
        ({"model": "two words"}, "model"),
        ({"model": "m" * 101}, "model"),
        ({"key": "with space"}, "key"),
        ({"key": "k" * 501}, "key"),
    ],
)
def test_005_a_wrong_field_is_refused_with_a_text(
    fields: Dict[str, Any], field_name: str
) -> None:
    form = _parse(**fields)

    assert list(form.errors) == [field_name]
    assert form.errors[field_name] != ""


def test_006_the_texts_of_the_errors_are_in_french() -> None:
    i18n.set_language("fr")

    form = _parse(url="ftp://x", model="")

    assert "avec http ou https" in form.errors["url"]
    assert "Choisissez le modèle" in form.errors["model"]


# The keys.


def _save(
    settings: DesktopSettings, store: MemorySecretStore, **fields: Any
) -> AiServer:
    return save_ai_server(settings, _parse(**fields), store)


def test_007_the_key_goes_to_the_keyring_and_nowhere_else(
    tmp_path: Path,
) -> None:
    settings = DesktopSettings()
    store = MemorySecretStore()

    server = _save(settings, store, key=KEY)
    path = tmp_path / "settings.json"
    save_settings(settings, path)

    assert store.get(get_ai_secret_name(server.server_id)) == KEY
    assert KEY not in path.read_text(encoding="utf-8")
    assert settings.ai_servers == [server]


def test_008_an_empty_field_keeps_the_key_and_a_button_removes_it() -> None:
    settings = DesktopSettings()
    store = MemorySecretStore()
    server = _save(settings, store, key=KEY)
    name = get_ai_secret_name(server.server_id)

    _save(settings, store, server_id=server.server_id, model="llama4")
    assert store.get(name) == KEY
    assert settings.ai_servers[0].model == "llama4"

    _save(settings, store, server_id=server.server_id, clear_key=True)
    assert store.get(name) is None


def test_009_a_new_address_erases_the_key() -> None:
    settings = DesktopSettings()
    store = MemorySecretStore()
    server = _save(settings, store, key=KEY)
    name = get_ai_secret_name(server.server_id)

    # The same address, written another way: the key stays.
    _save(
        settings,
        store,
        server_id=server.server_id,
        url="HTTP://Ollama.company.lan:11434/v1/",
    )
    assert store.get(name) == KEY

    # Another address: the key would go there.
    _save(
        settings,
        store,
        server_id=server.server_id,
        url="http://other.company.lan:11434/v1",
    )
    assert store.get(name) is None

    # A key typed with the new address is for the new address.
    _save(
        settings,
        store,
        server_id=server.server_id,
        url="http://third.company.lan/v1",
        key="sk-new-key",
    )
    assert store.get(name) == "sk-new-key"


def test_010_a_deleted_server_takes_its_key() -> None:
    settings = DesktopSettings()
    store = MemorySecretStore()
    server = _save(settings, store, key=KEY)

    assert delete_ai_server(settings, server.server_id, store) is True
    assert delete_ai_server(settings, server.server_id, store) is False

    assert settings.ai_servers == []
    assert store.get(get_ai_secret_name(server.server_id)) is None


def test_011_a_keyring_that_refuses_changes_nothing() -> None:
    class RefusingStore(MemorySecretStore):
        def set(self, name: str, value: str) -> None:
            del name, value
            raise SecretStoreError("refused")

    settings = DesktopSettings()

    with pytest.raises(SecretStoreError):
        _save(settings, RefusingStore(), key=KEY)  # type: ignore[arg-type]

    assert settings.ai_servers == []


# The configuration of the assistant.


def test_012_a_complete_server_is_a_provider_and_the_internal_is_default() -> (
    None
):
    store = MemorySecretStore()
    settings = DesktopSettings()
    external = _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        model="mistral-large",
        key=KEY,
        is_internal=False,
    )
    _save(settings, store, name="Ollama", url="http://a.lan/v1", model="m1")
    _save(settings, store, name="Second", url="http://b.lan/v1", model="m2")

    llm = build_llm_config(settings, store, VALID_POLICY)

    assert list(llm.providers) == ["mistral", "ollama", "second"]
    assert llm.default == "ollama"
    ollama = llm.providers["ollama"]
    assert isinstance(ollama, OpenAICompatible)
    assert ollama.is_local is True and ollama.api_key_env == ""
    mistral = llm.providers["mistral"]
    assert isinstance(mistral, OpenAICompatible)
    assert mistral.is_local is False
    assert mistral.api_key_env == get_key_variable(external.server_id)
    assert llm.allow_cloud is True
    assert llm.cloud_blocked_classifications == ["Secret"]
    assert llm.cloud_token_budget_per_month == 1000
    llm.validate()


def test_013_with_no_internal_server_the_first_complete_one_is_default() -> (
    None
):
    store = MemorySecretStore()
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name="Claude",
        kind=AI_KIND_ANTHROPIC,
        url="https://api.anthropic.com",
        model="claude-x",
        key=KEY,
    )

    llm = build_llm_config(settings, store, VALID_POLICY)

    assert llm.default == "claude"
    claude = llm.providers["claude"]
    assert isinstance(claude, Anthropic)
    assert claude.is_local is False
    assert llm.allow_cloud is True
    llm.validate()


def test_014_an_incomplete_server_is_not_a_provider() -> None:
    store = MemorySecretStore()
    settings = DesktopSettings(
        ai_servers=[
            _server(name="No model", model=""),
            _server(name="No address", url=""),
            _server(
                name="External without key",
                url="https://api.example.org/v1",
                is_internal=False,
            ),
            _server(
                name="External over http",
                url="http://api.example.org/v1",
                is_internal=False,
            ),
        ]
    )
    store.set(get_ai_secret_name(settings.ai_servers[3].server_id), KEY)

    llm = build_llm_config(settings, store, VALID_POLICY)

    assert llm.providers == {}
    assert llm.default == ""
    assert llm.allow_cloud is False


@pytest.mark.parametrize("policy", [ABSENT_POLICY, INVALID_POLICY])
def test_015_without_a_valid_policy_no_external_server_is_used(
    policy: AiPolicy,
) -> None:
    store = MemorySecretStore()
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        is_internal=False,
        key=KEY,
    )
    _save(settings, store, name="Ollama", url="http://a.lan/v1")

    llm = build_llm_config(settings, store, policy)

    assert list(llm.providers) == ["ollama"]
    assert llm.allow_cloud is False
    assert llm.cloud_blocked_classifications == []
    assert llm.cloud_token_budget_per_month == 0


def test_016_the_names_of_the_providers_are_valid_and_unique() -> None:
    store = MemorySecretStore()
    settings = DesktopSettings(
        ai_servers=[
            _server(name="Mon Serveur n°1 !"),
            _server(name="mon serveur n 1"),
            _server(name="É é"),
        ]
    )

    llm = build_llm_config(settings, store, VALID_POLICY)

    assert list(llm.providers) == [
        "mon-serveur-n-1",
        "mon-serveur-n-1-2",
        "server",
    ]
    llm.validate()


def test_017_the_keys_are_given_in_a_private_environment_only() -> None:
    store = MemorySecretStore()
    settings = DesktopSettings()
    server = _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        is_internal=False,
        key=KEY,
    )
    llm = build_llm_config(settings, store, VALID_POLICY)

    environment = get_provider_environment(settings, store)
    provider = create_provider("mistral", llm, environment)

    assert environment == {get_key_variable(server.server_id): KEY}
    assert provider._key == KEY  # type: ignore[attr-defined]  # noqa: SLF001
    # No key in the environment of the process.
    assert KEY not in os.environ.values()
    assert get_key_variable(server.server_id) not in os.environ


# The policy.


def _write_policy(path: Path, content: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        content if isinstance(content, str) else json.dumps(content),
        encoding="utf-8",
    )
    return path


def test_018_a_policy_that_is_absent_is_no_rule(tmp_path: Path) -> None:
    policy = load_ai_policy([tmp_path / POLICY_FILE_NAME])

    assert policy.state is PolicyState.ABSENT
    assert "not installed" in get_policy_message(policy)


def test_019_a_valid_policy_gives_the_classifications_and_the_budget(
    tmp_path: Path,
) -> None:
    path = _write_policy(
        tmp_path / POLICY_FILE_NAME,
        {
            "version": 1,
            "cloud_blocked_classifications": [" Secret ", "Restricted"],
            "cloud_token_budget_per_month": 5000,
        },
    )

    policy = load_ai_policy([path])

    assert policy.is_valid
    assert policy.blocked_classifications == ["Secret", "Restricted"]
    assert policy.monthly_token_budget == 5000
    assert get_policy_message(policy) == ""


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '"text"',
        {},
        {"version": 2},
        {"version": 1, "cloud_blocked_classifications": "Secret"},
        {"version": 1, "cloud_blocked_classifications": [""]},
        {"version": 1, "cloud_blocked_classifications": [3]},
        {"version": 1, "cloud_blocked_classifications": ["x"] * 101},
        {"version": 1, "cloud_token_budget_per_month": -1},
        {"version": 1, "cloud_token_budget_per_month": "9"},
        {"version": 1, "cloud_token_budget_per_month": True},
        {"version": 1, "cloud_token_budget_per_month": 1.5},
    ],
)
def test_020_a_policy_that_is_invalid_is_no_rule(
    tmp_path: Path, content: Any
) -> None:
    path = _write_policy(tmp_path / POLICY_FILE_NAME, content)

    policy = load_ai_policy([path])

    assert policy.state is PolicyState.INVALID
    assert "cannot be read" in get_policy_message(policy)
    assert policy.blocked_classifications == []


def test_021_a_policy_that_is_too_large_is_invalid(tmp_path: Path) -> None:
    path = _write_policy(tmp_path / POLICY_FILE_NAME, " " * (70 * 1024))

    assert load_ai_policy([path]).state is PolicyState.INVALID


def test_022_the_first_file_is_the_policy_and_no_other_takes_its_place(
    tmp_path: Path,
) -> None:
    first = _write_policy(tmp_path / "first" / POLICY_FILE_NAME, "{bad")
    second = _write_policy(
        tmp_path / "second" / POLICY_FILE_NAME, {"version": 1}
    )

    assert load_ai_policy([first, second]).state is PolicyState.INVALID
    assert load_ai_policy([tmp_path / "none.json", second]).is_valid


def test_023_the_places_are_the_ones_of_a_deployment_and_not_the_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    configure_policy_paths(None)
    monkeypatch.setenv("STRICTDOC_AI_POLICY", str(tmp_path / "mine.json"))
    monkeypatch.setenv("STRICTDOC_AI_POLICY_PATH", str(tmp_path / "mine.json"))

    development = get_policy_paths()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    frozen = get_policy_paths()

    assert all(path_.name == POLICY_FILE_NAME for path_ in development)
    assert frozen == development
    assert len(frozen) == 1
    # Not in the folders of the user, not in the project.
    for path_ in frozen:
        assert "config" not in path_.parts[-3:-1]
        assert str(tmp_path) not in str(path_)


def test_023b_a_file_next_to_a_frozen_program_is_not_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    program_folder = tmp_path / "Programs" / "StrictDoc"
    _write_policy(program_folder / POLICY_FILE_NAME, {"version": 1})
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        sys, "executable", str(program_folder / "strictdoc"), raising=False
    )
    configure_policy_paths(None)

    assert program_folder / POLICY_FILE_NAME not in get_policy_paths()
    policy = load_ai_policy(get_policy_paths())
    assert policy.path != str(program_folder / POLICY_FILE_NAME)


def test_024_the_tests_give_the_places_to_the_code(tmp_path: Path) -> None:
    path = _write_policy(tmp_path / POLICY_FILE_NAME, {"version": 1})
    configure_policy_paths([path])
    try:
        assert get_policy_paths() == [path]
        assert load_ai_policy().is_valid
    finally:
        configure_policy_paths(None)


# What the runtime gives to the projects.


def _create_project_config() -> ProjectConfig:
    config = ProjectConfig(
        project_title="Project",
        project_features=[],
    )
    return config


def _create_runtime(
    tmp_path: Path, store: MemorySecretStore, policy: AiPolicy
) -> AiRuntime:
    return AiRuntime(
        settings_path=tmp_path / "settings.json",
        secret_store=store,
        audit_directory=tmp_path / "audit",
        get_policy=lambda: policy,
    )


def test_025_a_project_has_no_ai_button_until_a_server_is_complete(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    runtime = _create_runtime(tmp_path, store, VALID_POLICY)
    config = _create_project_config()
    runtime.attach(config)
    llm = config.llm
    assert llm is not None
    assert config.is_activated_llm() is False

    # A server is declared: the same project follows, with no restart.
    settings = load_settings(runtime.settings_path)
    _save(settings, store, name="Ollama")
    save_settings(settings, runtime.settings_path)
    runtime.apply()

    assert config.llm is llm
    assert config.is_activated_llm() is True
    assert list(llm.providers) == ["ollama"] and llm.default == "ollama"

    # The server is deleted: the buttons go.
    settings = load_settings(runtime.settings_path)
    delete_ai_server(settings, settings.ai_servers[0].server_id, store)
    save_settings(settings, runtime.settings_path)
    runtime.apply()

    assert config.is_activated_llm() is False
    assert llm.providers == {}


def test_026_the_assistant_of_a_project_is_replaced_by_the_one_of_the_user(
    tmp_path: Path,
) -> None:
    from strictdoc.features.llm.config import Fake, LLMConfig  # noqa: PLC0415

    runtime = _create_runtime(tmp_path, MemorySecretStore(), VALID_POLICY)
    config = _create_project_config()
    config.project_features.append(ProjectFeature.LLM)
    config.llm = LLMConfig(
        default="fake",
        providers={"fake": Fake(answers=["x"])},
        allow_cloud=True,
    )

    runtime.attach(config)

    assert config.llm.providers == {}
    assert config.llm.allow_cloud is False
    assert config.llm.kb is None
    assert config.is_activated_llm() is False


def test_027_every_project_that_is_open_follows_a_change(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    runtime = _create_runtime(tmp_path, store, VALID_POLICY)
    first = _create_project_config()
    second = _create_project_config()
    runtime.attach(first)
    runtime.attach(second)
    settings = DesktopSettings()
    _save(settings, store, name="Ollama")
    save_settings(settings, runtime.settings_path)

    runtime.apply()

    assert first.is_activated_llm() and second.is_activated_llm()
    # Each project has its own object, and the audit log is shared.
    assert first.llm is not second.llm
    assert first.audit_dir == second.audit_dir == str(tmp_path / "audit")


def test_028_the_project_reads_its_assistant_from_the_application(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "doc.sdoc").write_text(
        "[DOCUMENT]\nTITLE: Doc\n\n[TEXT]\nSTATEMENT: Text.\n",
        encoding="utf-8",
    )
    runtime = _create_runtime(tmp_path, MemorySecretStore(), VALID_POLICY)

    config = create_desktop_project_config(
        input_path=str(project), port=None, ai_runtime=runtime
    )

    assert config.llm is not None
    assert config.is_activated_llm() is False
    assert config.audit_dir == str(tmp_path / "audit")


def test_029_the_budget_of_the_month_is_the_one_of_the_user_for_all_projects(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    runtime = _create_runtime(tmp_path, store, VALID_POLICY)
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        is_internal=False,
        key=KEY,
    )
    save_settings(settings, runtime.settings_path)
    project_a = _create_project_config()
    project_b = _create_project_config()
    runtime.attach(project_a)
    runtime.attach(project_b)
    assert project_a.llm is not None and project_b.llm is not None
    audit_a = LLMAudit(str(tmp_path / "audit" / "llm_audit.jsonl"))
    audit_b = LLMAudit(str(tmp_path / "audit" / "llm_audit.jsonl"))
    policy_b = Policy(project_b.llm, audit_b)
    # The project A spends the whole budget of the month on its own.
    audit_a.record(
        LLMCall(
            user="jdupont",
            role="author",
            project="A",
            provider="mistral",
            model="m",
            is_local=False,
            prompt="p",
            answer="a",
            node_uids=[],
            latency=0.1,
            status="ok",
            input_tokens=900,
            output_tokens=200,
        )
    )

    with pytest.raises(PolicyError) as error:
        policy_b.check(
            user="jdupont",
            provider_name="mistral",
            classifications=[],
            cloud_confirmed=True,
        )

    assert error.value.status == 403
    assert "budget" in error.value.message


def test_030_a_classified_context_never_goes_to_an_external_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import strictdoc.features.llm.http as llm_http  # noqa: PLC0415

    store = MemorySecretStore()
    runtime = _create_runtime(tmp_path, store, VALID_POLICY)
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        is_internal=False,
        key=KEY,
    )
    _save(settings, store, name="Ollama", url="http://a.lan/v1")
    save_settings(settings, runtime.settings_path)
    config = _create_project_config()
    runtime.attach(config)
    assert config.llm is not None
    policy = Policy(
        config.llm, LLMAudit(str(tmp_path / "audit" / "llm_audit.jsonl"))
    )

    def no_network(*_: Any, **__: Any) -> Any:
        raise AssertionError("A call reached the network.")

    monkeypatch.setattr(llm_http._OPENER, "open", no_network)  # noqa: SLF001

    with pytest.raises(PolicyError) as error:
        policy.check(
            user="jdupont",
            provider_name="mistral",
            classifications=["secret"],
            cloud_confirmed=True,
        )
    with pytest.raises(PolicyError) as unconfirmed:
        policy.check(
            user="jdupont",
            provider_name="mistral",
            classifications=[],
            cloud_confirmed=False,
        )

    assert error.value.status == 403
    assert "classification" in error.value.message
    # What the user is shown is confirmed first, as before.
    assert unconfirmed.value.status == 409
    # The internal server is offered whatever the classification.
    assert list(policy.allowed_providers(["secret"])) == ["ollama"]
    assert list(policy.allowed_providers()) == ["mistral", "ollama"]


def test_031_without_a_valid_policy_the_external_server_is_refused(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    runtime = _create_runtime(tmp_path, store, ABSENT_POLICY)
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        is_internal=False,
        key=KEY,
    )
    save_settings(settings, runtime.settings_path)
    config = _create_project_config()
    runtime.attach(config)
    assert config.llm is not None
    policy = Policy(config.llm, LLMAudit(str(tmp_path / "llm_audit.jsonl")))

    with pytest.raises(PolicyError) as error:
        policy.check(
            user="u",
            provider_name="mistral",
            classifications=[],
            cloud_confirmed=True,
        )

    assert error.value.status == 400
    assert config.is_activated_llm() is False
    overview = runtime.get_overview()
    assert overview.servers[0].problem != ""
    assert "not installed" in overview.policy_message


# The list of the models.


class _Handler(BaseHTTPRequestHandler):
    requests: List[Dict[str, str]] = []
    behaviour: str = "models"
    redirect_to: str = ""

    def do_GET(self) -> None:  # noqa: N802
        type(self).requests.append(
            {
                "path": self.path,
                **{k_.lower(): v_ for k_, v_ in self.headers.items()},
            }
        )
        if self.behaviour == "redirect":
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
            self.end_headers()
            return
        if self.behaviour == "unauthorized":
            body = json.dumps({"error": f"bad key {KEY}"}).encode()
            self.send_response(401)
        elif self.behaviour == "huge":
            body = b'{"data": [' + b'{"id": "m"},' * 100000 + b'{"id": "z"}]}'
            self.send_response(200)
        else:
            body = json.dumps(
                {"data": [{"id": "b-model"}, {"id": "a-model"}, {"x": 1}]}
            ).encode()
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: Any) -> None:
        pass


@pytest.fixture(name="models_server")
def fixture_models_server() -> Iterator[Any]:
    _Handler.requests = []
    _Handler.behaviour = "models"
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _base(server: Any) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}/v1"


def test_032_the_models_are_the_ones_of_the_server(models_server: Any) -> None:
    listing = list_models(
        kind=AI_KIND_OPENAI,
        url=_base(models_server),
        key=KEY,
        is_internal=True,
    )

    assert listing.models == ["a-model", "b-model"]
    assert listing.message == ""
    assert _Handler.requests[0]["path"] == "/v1/models"
    assert _Handler.requests[0]["authorization"] == f"Bearer {KEY}"


def test_033_anthropic_is_asked_with_its_own_headers(
    models_server: Any,
) -> None:
    # The server of the test is http: a key goes there only for an internal
    # server, so the key is not sent here, and the headers are the ones of
    # the API of Anthropic.
    listing = list_models(
        kind=AI_KIND_ANTHROPIC,
        url=_base(models_server).removesuffix("/v1"),
        key="",
        is_internal=True,
    )

    assert listing.models == ["a-model", "b-model"]
    assert _Handler.requests[0]["path"] == "/v1/models?limit=100"
    assert _Handler.requests[0]["anthropic-version"] == "2023-06-01"


def test_034_a_redirection_is_not_followed(models_server: Any) -> None:
    other = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=other.serve_forever, daemon=True).start()
    try:
        _Handler.behaviour = "redirect"
        _Handler.redirect_to = f"http://127.0.0.1:{other.server_address[1]}/x"

        listing = list_models(
            kind=AI_KIND_OPENAI,
            url=_base(models_server),
            key=KEY,
            is_internal=True,
        )
    finally:
        other.shutdown()
        other.server_close()

    assert listing.models == []
    assert "redirects" in listing.message
    # Only the first server was asked: the key did not follow.
    assert len(_Handler.requests) == 1


def test_035_the_key_is_never_in_a_message(models_server: Any) -> None:
    _Handler.behaviour = "unauthorized"

    listing = list_models(
        kind=AI_KIND_OPENAI,
        url=_base(models_server),
        key=KEY,
        is_internal=True,
    )

    assert listing.models == []
    assert KEY not in listing.message
    assert "refused the key" in listing.message


def test_036_a_huge_answer_is_refused(models_server: Any) -> None:
    _Handler.behaviour = "huge"

    listing = list_models(
        kind=AI_KIND_OPENAI,
        url=_base(models_server),
        key="",
        is_internal=True,
    )

    assert listing.models == []
    assert "too long" in listing.message


def test_037_nothing_is_sent_when_the_server_is_not_there() -> None:
    listing = list_models(
        kind=AI_KIND_OPENAI,
        url="http://127.0.0.1:9/v1",
        key="",
        is_internal=True,
    )

    assert listing.models == []
    assert listing.message == "The server cannot be reached."


def test_038_a_key_never_goes_over_http_to_an_external_server(
    models_server: Any,
) -> None:
    listing = list_models(
        kind=AI_KIND_OPENAI,
        url=_base(models_server),
        key=KEY,
        is_internal=False,
    )

    assert listing.models == []
    assert "https" in listing.message
    assert _Handler.requests == []


# The screen.

PORT = 18082
HOST = f"127.0.0.1:{PORT}"
OWN = {"Origin": f"http://{HOST}"}


def _create_client(
    tmp_path: Path, store: Optional[MemorySecretStore] = None
) -> TestClient:
    credentials = SessionCredentials.create()
    application = create_home_app(
        settings_path=tmp_path / "settings.json",
        secret_store=store if store is not None else MemorySecretStore(),
    )
    application.add_middleware(
        DesktopSessionMiddleware,
        credentials=credentials,
        port=PORT,
        allowed_hosts=frozenset({HOST}),
    )
    client = TestClient(application, base_url=f"http://{HOST}")
    client.cookies.set(get_session_cookie_name(PORT), credentials.token)
    return client


def _form(**fields: str) -> Dict[str, str]:
    values = {
        "server_id": "",
        "name": "Ollama",
        "kind": "openai",
        "url": "http://ollama.company.lan:11434/v1",
        "model": "llama3",
        "is_internal": "on",
        "key": "",
    }
    values.update(fields)
    return values


def test_039_the_screen_adds_a_server_and_never_shows_its_key(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    client = _create_client(tmp_path, store)

    answer = client.post(
        "/settings/ai/save",
        data=_form(key=KEY),
        headers=OWN,
        follow_redirects=False,
    )

    assert answer.status_code == 303
    settings = load_settings(tmp_path / "settings.json")
    assert [server_.name for server_ in settings.ai_servers] == ["Ollama"]
    server = settings.ai_servers[0]
    assert store.get(get_ai_secret_name(server.server_id)) == KEY
    assert KEY not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    page = client.get("/settings").text
    assert "Ollama" in page and "llama3" in page
    assert KEY not in page
    assert "A key is saved" in page
    assert 'data-testid="ai-clear-key"' in page
    assert KEY not in "".join(os.environ.values())


def test_040_a_wrong_server_writes_nothing_and_says_why(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    client = _create_client(tmp_path, store)

    answer = client.post(
        "/settings/ai/save",
        data=_form(url="http://api.example.org/v1", is_internal="", key=KEY),
        headers=OWN,
    )

    assert answer.status_code == 422
    assert 'data-testid="ai-url-error"' in answer.text
    assert "https" in answer.text
    assert KEY not in answer.text
    assert not (tmp_path / "settings.json").exists()
    assert store.get("ai/anything") is None


def test_041_the_screen_deletes_a_server_and_its_key(tmp_path: Path) -> None:
    store = MemorySecretStore()
    client = _create_client(tmp_path, store)
    client.post("/settings/ai/save", data=_form(key=KEY), headers=OWN)
    server = load_settings(tmp_path / "settings.json").ai_servers[0]

    answer = client.post(
        "/settings/ai/delete",
        data={"server_id": server.server_id},
        headers=OWN,
        follow_redirects=False,
    )

    assert answer.status_code == 303
    assert load_settings(tmp_path / "settings.json").ai_servers == []
    assert store.get(get_ai_secret_name(server.server_id)) is None


def test_042_the_models_come_from_the_server_with_the_key_that_is_saved(
    tmp_path: Path, models_server: Any
) -> None:
    store = MemorySecretStore()
    client = _create_client(tmp_path, store)
    url = _base(models_server)
    client.post("/settings/ai/save", data=_form(url=url, key=KEY), headers=OWN)
    server = load_settings(tmp_path / "settings.json").ai_servers[0]

    answer = client.post(
        "/settings/ai/models",
        data={
            "server_id": server.server_id,
            "kind": "openai",
            "url": url,
            "is_internal": "on",
            "key": "",
        },
        headers=OWN,
    )
    other_address = client.post(
        "/settings/ai/models",
        data={
            "server_id": server.server_id,
            "kind": "openai",
            "url": url.replace("127.0.0.1", "localhost"),
            "is_internal": "on",
            "key": "",
        },
        headers=OWN,
    )

    assert answer.json()["models"] == ["a-model", "b-model"]
    assert _Handler.requests[0]["authorization"] == f"Bearer {KEY}"
    # Another address: the saved key does not go there.
    assert other_address.json()["models"] == ["a-model", "b-model"]
    assert "authorization" not in _Handler.requests[1]
    assert KEY not in answer.text and KEY not in other_address.text


def test_043_a_page_of_another_port_cannot_change_the_servers(
    tmp_path: Path,
) -> None:
    client = _create_client(tmp_path)

    answer = client.post(
        "/settings/ai/save",
        data=_form(),
        headers={"Origin": "http://127.0.0.1:18999"},
    )

    assert answer.status_code == 403
    assert not (tmp_path / "settings.json").exists()


def test_044_the_screen_says_when_the_policy_is_missing(
    tmp_path: Path,
) -> None:
    client = _create_client(tmp_path)
    client.post(
        "/settings/ai/save",
        data=_form(
            name="Mistral",
            url="https://api.mistral.ai/v1",
            is_internal="",
            key=KEY,
        ),
        headers=OWN,
    )

    page = client.get("/settings").text

    assert 'data-testid="ai-policy-message"' in page
    assert "not installed" in page
    assert "Not used: the rules for external servers are missing." in page


def test_045_the_type_of_a_server_is_read_without_failing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "ai_servers": [
                    {"server_id": "a", "kind": "anthropic"},
                    {"server_id": "b", "kind": "gemini"},
                    {"server_id": "c", "kind": 3},
                    {"server_id": "d"},
                ]
            }
        ),
        encoding="utf-8",
    )

    kinds = [server_.kind for server_ in load_settings(path).ai_servers]

    assert kinds == ["anthropic", "openai", "openai", "openai"]


# The key of an external server reaches its provider (TLS is not simulated: the
# request that the provider would send is read where it is made).


def _capture_requests(
    monkeypatch: pytest.MonkeyPatch, module: str
) -> List[Dict[str, Any]]:
    sent: List[Dict[str, Any]] = []

    def post_json(**fields: Any) -> bytes:
        sent.append(fields)
        if module == "anthropic":
            return json.dumps(
                {"content": [{"type": "text", "text": "{}"}]}
            ).encode()
        return json.dumps(
            {"choices": [{"message": {"content": "{}"}}]}
        ).encode()

    monkeypatch.setattr(f"strictdoc.features.llm.{module}.post_json", post_json)
    return sent


def _create_external(
    kind: str, url: str, name: str
) -> "tuple[DesktopSettings, MemorySecretStore]":
    store = MemorySecretStore()
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name=name,
        kind=kind,
        url=url,
        model="m",
        is_internal=False,
        key=KEY,
    )
    return settings, store


def test_046_an_external_server_of_openai_gets_its_key_as_a_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture_requests(monkeypatch, "openai_compatible")
    settings, store = _create_external(
        AI_KIND_OPENAI, "https://api.mistral.ai/v1", "Mistral"
    )
    llm = build_llm_config(settings, store, VALID_POLICY)
    assert llm.providers["mistral"].is_local is False

    # What the routes do: the provider is made with the configuration.
    provider = create_provider("mistral", llm, llm.environment)
    provider.complete(LLMRequest(system="s", user="u"))

    assert sent[0]["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert sent[0]["headers"] == {"Authorization": f"Bearer {KEY}"}
    assert KEY not in os.environ.values()


def test_047_anthropic_gets_its_key_in_its_own_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _capture_requests(monkeypatch, "anthropic")
    settings, store = _create_external(
        AI_KIND_ANTHROPIC, "https://api.anthropic.com", "Claude"
    )
    llm = build_llm_config(settings, store, VALID_POLICY)

    provider = create_provider("claude", llm, llm.environment)
    provider.complete(LLMRequest(system="s", user="u"))

    assert sent[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert sent[0]["headers"]["x-api-key"] == KEY
    assert KEY not in os.environ.values()


def test_048_the_keys_are_in_the_configuration_of_the_application_only(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    runtime = _create_runtime(tmp_path, store, VALID_POLICY)
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        is_internal=False,
        key=KEY,
    )
    _save(settings, store, name="Ollama", url="http://a.lan/v1", key="sk-lan")
    # A server that is not used does not give its key.
    _save(
        settings,
        store,
        name="Unused",
        url="https://api.example.org/v1",
        model="m",
        is_internal=False,
        key="sk-unused",
    )
    settings.ai_servers[2].model = ""
    save_settings(settings, runtime.settings_path)
    config = _create_project_config()
    runtime.attach(config)
    assert config.llm is not None

    environment = config.llm.environment

    assert environment is not None
    assert sorted(environment.values()) == sorted([KEY, "sk-lan"])
    assert KEY not in repr(config.llm)
    assert KEY not in (tmp_path / "settings.json").read_text(encoding="utf-8")
    assert KEY not in os.environ.values()
    # The key follows the change of the settings, in place.
    delete_ai_server(settings, settings.ai_servers[0].server_id, store)
    save_settings(settings, runtime.settings_path)
    runtime.apply()
    assert config.llm.environment is not None
    assert KEY not in config.llm.environment.values()


MISSING_KEYS: List[str] = []


@dataclass
class _WatchedLLMConfig(LLMConfig):
    """An assistant configuration that notes a provider that has no key."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        environment = getattr(self, "environment", None)
        for provider_ in getattr(self, "providers", {}).values():
            key_name = provider_.api_key_env
            if key_name != "" and (
                environment is None or key_name not in environment
            ):
                MISSING_KEYS.append(f"{name}: {key_name}")


def test_049_a_provider_never_exists_without_its_key_while_the_settings_apply(
    tmp_path: Path,
) -> None:
    store = MemorySecretStore()
    runtime = _create_runtime(tmp_path, store, VALID_POLICY)
    settings = DesktopSettings()
    _save(
        settings,
        store,
        name="Mistral",
        url="https://api.mistral.ai/v1",
        is_internal=False,
        key=KEY,
    )
    save_settings(settings, runtime.settings_path)
    config = _create_project_config()
    runtime.attach(config)
    assert config.llm is not None
    config.llm = _WatchedLLMConfig(
        **{
            field_.name: getattr(config.llm, field_.name)
            for field_ in fields(LLMConfig)
        }
    )
    MISSING_KEYS.clear()

    # A server comes with its key: its provider does not come before it.
    _save(settings, store, name="Ollama", url="http://a.lan/v1", key="sk-lan")
    save_settings(settings, runtime.settings_path)
    runtime.apply()
    assert sorted(config.llm.providers) == ["mistral", "ollama"]
    assert MISSING_KEYS == []

    # A server leaves with its key: its provider does not stay after it.
    delete_ai_server(settings, settings.ai_servers[0].server_id, store)
    save_settings(settings, runtime.settings_path)
    runtime.apply()
    assert sorted(config.llm.providers) == ["ollama"]
    assert config.llm.environment is not None
    assert KEY not in config.llm.environment.values()
    assert MISSING_KEYS == []
