import json
from datetime import datetime, timezone

import pytest

from strictdoc.features.llm.audit import LLMAudit, LLMCall
from strictdoc.features.llm.config import (
    Anthropic,
    LLMConfig,
    OpenAICompatible,
)
from strictdoc.features.llm.policy import Policy, PolicyError
from strictdoc.helpers.exception import StrictDocException


def _config(**kwargs) -> LLMConfig:
    values = {
        "default": "local",
        "providers": {
            "local": OpenAICompatible(
                base_url="http://ollama:11434/v1", model="q", is_local=True
            ),
            "claude": Anthropic(model="c", api_key_env="K"),
        },
    }
    values.update(kwargs)
    return LLMConfig(**values)


def _call(**kwargs) -> LLMCall:
    values = {
        "user": "anna",
        "role": "author",
        "project": "p",
        "provider": "claude",
        "model": "c",
        "is_local": False,
        "prompt": "the prompt",
        "answer": "the answer",
        "node_uids": ["R-1"],
        "latency": 1.2345,
        "status": "ok",
        "input_tokens": 100,
        "output_tokens": 50,
    }
    values.update(kwargs)
    return LLMCall(**values)


def _policy(tmp_path, **kwargs):
    audit = LLMAudit(str(tmp_path / "llm_audit.jsonl"))
    return Policy(_config(**kwargs), audit), audit


def _check(
    policy, provider="local", classifications=(), confirmed=False, user="anna"
):
    policy.check(
        user=user,
        provider_name=provider,
        classifications=classifications,
        cloud_confirmed=confirmed,
    )


def test_001_a_local_provider_is_allowed(tmp_path):
    policy, _ = _policy(tmp_path)
    _check(policy)


def test_002_a_cloud_provider_is_closed_by_default(tmp_path):
    policy, _ = _policy(tmp_path)
    with pytest.raises(PolicyError) as raised:
        _check(policy, "claude", confirmed=True)
    assert raised.value.status == 403 and "closed" in raised.value.message


def test_003_an_open_cloud_provider_needs_a_confirmation(tmp_path):
    policy, _ = _policy(tmp_path, allow_cloud=True)
    with pytest.raises(PolicyError) as raised:
        _check(policy, "claude")
    assert raised.value.status == 409
    _check(policy, "claude", confirmed=True)


def test_004_a_blocked_classification_never_goes_to_the_cloud(tmp_path):
    policy, _ = _policy(
        tmp_path, allow_cloud=True, cloud_blocked_classifications=["Restricted"]
    )
    with pytest.raises(PolicyError) as raised:
        _check(policy, "claude", classifications={"restricted"}, confirmed=True)
    assert (
        raised.value.status == 403
        and "Restricted".lower() in raised.value.message.lower()
    )
    # The same context is fine for a local model.
    _check(policy, "local", classifications={"Restricted"})
    # And another classification is fine for the cloud.
    _check(policy, "claude", classifications={"Internal"}, confirmed=True)


def test_005_an_unknown_provider_is_refused(tmp_path):
    policy, _ = _policy(tmp_path)
    with pytest.raises(PolicyError) as raised:
        _check(policy, "whatever")
    assert raised.value.status == 400


def test_006_the_monthly_budget_closes_the_cloud(tmp_path):
    policy, audit = _policy(
        tmp_path, allow_cloud=True, cloud_token_budget_per_month=1000
    )
    _check(policy, "claude", confirmed=True)
    audit.record(_call(input_tokens=700, output_tokens=300))
    with pytest.raises(PolicyError, match="budget"):
        _check(policy, "claude", confirmed=True)
    # A local call does not count, and does not need the budget.
    audit.record(_call(is_local=True, provider="local"))
    _check(policy, "local")


def test_007_an_old_month_does_not_count(tmp_path):
    audit = LLMAudit(str(tmp_path / "a.jsonl"))
    audit.record(_call(), now=datetime(2020, 1, 15, tzinfo=timezone.utc))
    assert audit.cloud_tokens_in_month() == 0
    assert (
        audit.cloud_tokens_in_month(datetime(2020, 1, 20, tzinfo=timezone.utc))
        == 150
    )


def test_008_the_rate_limit_is_per_user_and_per_minute(tmp_path):
    now = [0.0]
    audit = LLMAudit(str(tmp_path / "a.jsonl"))
    policy = Policy(
        _config(rate_limit_per_minute=2), audit, clock=lambda: now[0]
    )
    _check(policy)
    _check(policy)
    with pytest.raises(PolicyError) as raised:
        _check(policy)
    assert raised.value.status == 429
    _check(policy, user="ben")
    now[0] = 61.0
    _check(policy)


def test_009_the_page_only_offers_the_providers_that_are_allowed(tmp_path):
    closed, _ = _policy(tmp_path)
    assert closed.allowed_providers() == {"local": "q"}
    opened, _ = _policy(
        tmp_path, allow_cloud=True, cloud_blocked_classifications=["Restricted"]
    )
    assert opened.allowed_providers() == {"local": "q", "claude": "c"}
    assert opened.allowed_providers({"Restricted"}) == {"local": "q"}


def test_010_the_audit_line_holds_a_hash_and_sizes_not_the_text(tmp_path):
    audit = LLMAudit(str(tmp_path / "a.jsonl"))
    audit.record(_call())
    entry = json.loads((tmp_path / "a.jsonl").read_text())
    assert entry["prompt_chars"] == len("the prompt")
    assert entry["answer_chars"] == len("the answer")
    assert len(entry["prompt_sha256"]) == 64
    assert "prompt" not in entry and "the prompt" not in json.dumps(entry)
    assert (
        entry["node_uids"] == ["R-1"] and entry["latency_s"] == 1.234 or 1.235
    )
    assert entry["is_local"] is False and entry["status"] == "ok"
    assert (tmp_path / "a.jsonl").stat().st_mode & 0o777 == 0o600


def test_011_the_prompt_is_stored_only_when_the_project_asks(tmp_path):
    audit = LLMAudit(str(tmp_path / "a.jsonl"), store_prompts=True)
    audit.record(_call())
    assert (
        json.loads((tmp_path / "a.jsonl").read_text())["prompt"] == "the prompt"
    )


def test_012_the_config_refuses_what_would_open_the_cloud_by_mistake():
    with pytest.raises(
        StrictDocException, match="cloud provider but allow_cloud"
    ):
        _config(default="claude").validate()
    _config(default="claude", allow_cloud=True).validate()
    with pytest.raises(StrictDocException, match="not declared"):
        _config(default="nope").validate()
    with pytest.raises(StrictDocException, match="no provider"):
        LLMConfig(providers={}).validate()
    with pytest.raises(StrictDocException, match="https"):
        _config(
            providers={
                "x": OpenAICompatible(base_url="http://api.example", model="m")
            },
            default="x",
            allow_cloud=True,
        ).validate()
    with pytest.raises(StrictDocException, match="api_key_env"):
        _config(
            providers={
                "local": OpenAICompatible(
                    base_url="http://o:1/v1", model="m", is_local=True
                ),
                "a": Anthropic(model="m", api_key_env=""),
            }
        ).validate()
    with pytest.raises(StrictDocException, match="http or https"):
        _config(
            providers={
                "local": OpenAICompatible(
                    base_url="file:///etc", model="m", is_local=True
                )
            }
        ).validate()
