# Plan 6: assistant for drafting requirements with a language model

Part of the [master plan](master_plan.md). Size: about 12 days. Branch prefix `feature/llm-`. Depends on plan 1 (author role, audit) and plan 4
(context from parent requirements and input documents). Plan 2 (comments) is reused to record where a draft came from.

Decision D1: local model by default; cloud providers optional **per project**; API keys in OpenBao; warning before anything leaves the network; log
of what is sent.

## 1. Why

Writing a first draft of requirements from a customer paragraph or a parent requirement is slow and repetitive: restate in "shall" form, split
into atomic requirements, propose a verification method, keep the project's style. A model can produce a draft in seconds. The author stays
responsible: the model proposes, the author edits and accepts, and nothing is saved without that decision. Data leaving the network is a real
concern in this domain, hence local first and an explicit, logged, per-project opening of cloud providers.

## 2. Current state

- Nothing in StrictDoc. The requirement form (`export/html/templates/screens/document/document/frame_requirement_form.jinja`) and the node
  creation routes (`create_requirement`, `table/add_node`) are the integration points; a feature-local router following `docx_router.py`
  (feature switch answering 412, locks taken by the including router) is the pattern.
- Host: Ollama listens on `127.0.0.1:11434` with `qwen3-coder:30b` (18.6 GB) and `devstral-small-2` (15.2 GB), both tuned for code. The host has
  30 GB of RAM (about 8 GB free with the stack running) and no GPU (`nvidia-smi` absent). **The server container cannot reach a
  service bound to the host loopback.**
- Context sources that exist: parent and child relations (`traceability_index`), the document `CLASSIFICATION` header field, document and node
  `STATUS` (`Draft`, `Active`, `Deleted`), and from plan 2 the comment header with `source=`.
- Secrets pattern: OpenBao for storage, Podman secrets for transport (`strictdoc-deploy/deploy.sh`).

## 3. Design

### 3.1 Providers

```python
class LLMProvider(Protocol):
    name: str
    is_local: bool
    def complete(self, request: LLMRequest) -> LLMResponse: ...
```

- `OpenAICompatibleProvider(base_url, model, api_key_env=None)`: the chat-completions protocol, which Ollama, OpenAI and many gateways speak.
  Structured output through the provider's JSON-schema option when available, otherwise a strict JSON instruction plus validation and one retry.
- `AnthropicProvider(model, api_key_env)`: the Messages API with a tool whose input schema is the output schema.
- A `FakeProvider` that returns canned answers, used by every test and by the golden-set run in CI.

Configuration in `strictdoc_config.py`, secrets by **name**, never by value:

```python
llm=LLMConfig(
    default="local",
    providers={
        "local":  OpenAICompatible(base_url="http://ollama:11434/v1", model="qwen3-coder:30b", is_local=True),
        "claude": Anthropic(model="claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY"),
    },
    allow_cloud=False,                          # per project, default False
    cloud_blocked_classifications=["Restricted"],
    audit_store_prompts=False,
    cloud_token_budget_per_month=0,
)
```

`deploy.sh` reads the keys from OpenBao paths named in the project (`secret/strictdoc/llm/<provider>`) and gives them to the container as Podman
secrets exposed as environment variables; the base URL of a provider is read only from this configuration, never from a request.

### 3.2 The assistant in the interface

An author opens "Draft with AI" in the requirement form (and from a section or document menu). The panel asks for:

1. **Instruction** (free text) and a **template** (EARS patterns: ubiquitous, event-driven, state-driven, unwanted behaviour, optional feature;
   or "free").
2. **Context** to include, chosen from checkboxes: the current node, its parent requirements, a section of an input document (picked by UID or
   section number), neighbouring requirements for style.
3. **Provider** (default local; cloud ones appear only when `allow_cloud` is true).

The server builds the prompt from a versioned template (`strictdoc/features/llm/prompts/*.md`), calls the provider and returns **proposals**: a
list of `{title, statement, rationale, verification_method, linked_to}` validated against a schema (`verification_method` one of the project's
choices, for REQ_02 T, A, R, I; `linked_to` only UIDs that exist). The panel shows each proposal in an editable card (the Milkdown editor when the document is
Markdown). The author edits, ticks and clicks "Create"; the server creates the nodes through the normal creation code, so every
validation of the form applies.

Marks left on a created node: `STATUS: Draft`, and one comment (plan 2 format) `source=llm model=<model> provider=<name> date=<ISO>
prompt=<template>@<version> accepted_by=<user>`. A project filter lists "Draft nodes generated by a model that no human has moved to Active".

### 3.3 Policy, gate and audit

- Cloud is closed by default. With `allow_cloud=true` for the project, choosing a cloud provider shows a **confirmation** that lists what will
  be sent (the prompt text, sizes, the provider) and requires a click.
- **Classification gate**: if any included node or its document carries a classification listed in `cloud_blocked_classifications`, a cloud
  provider cannot be chosen (the server refuses, whatever the browser sends).
- **Audit** (`<output>/llm_audit.jsonl`, same rules as plan 1's audit): time, user, role, project, provider, model, is_local, SHA-256 of the
  prompt, prompt and answer sizes, node UIDs included, latency, token counts when the provider returns them, status. The prompt text is stored
  only when `audit_store_prompts=true`, in files readable by administrators.
- Monthly **token budget** for cloud providers: counted from the audit; over the budget the cloud choice is refused.
- Rate limit per user and a request timeout.

### 3.4 Prompt injection and output handling

Input documents and requirements are data from outside; their text can contain instructions to the model. The model output is therefore:
validated against the schema, never executed, never trusted for UIDs (checked against the index), rendered like any user text (escaped or sanitised
as in the editor), and only ever a **proposal**. The prompt marks document text as quoted material. No tool or network access is given to the model.

### 3.5 Quality evaluation

- A **golden set** (about 20 cases from REQ_02 and a small customer-spec excerpt): an input, the context, and rule checks on the output
  (contains "shall", one requirement per statement, no "and/or" chains over a limit, a verification method from the allowed set, references only
  to existing UIDs, no invention of numeric values absent from the input). Run in CI with `FakeProvider` (tests the plumbing and the checks) and
  on demand against real models, producing a report.
- The spike (L0) decides whether the two installed models are good enough and fit in memory; a smaller general-purpose instruction model may be needed.

## 4. Steps

| Step | Content | Tests |
|---|---|---|
| L0 | Spike: run both installed models on a fixed set of five tasks on this host; record memory, latency, quality; decide how the container reaches Ollama (see open question 1); choose or add a model | A table in this document; the decision recorded |
| L1 | `LLMProvider`, request and response types, output schema and validator, `FakeProvider`, project option `llm` | Unit: schema accepts and rejects; invalid JSON retried once then reported |
| L2 | OpenAI-compatible client for Ollama (JSON-schema output, timeout, errors) | Unit against a local fake HTTP server; one manual run against the real Ollama |
| L3 | Context builder (node, parents, input section, neighbours), prompt templates and their versions | Unit: the prompt contains exactly the chosen context; nothing else; template version is recorded |
| L4 | Router and panel, proposal cards, creation through the normal code, marks (`Draft`, comment) | `unit_server`: author only (403 for others); proposals not saved until "Create"; created nodes validated like manual ones; end2end: draft, edit, create |
| L5 | Policy: `allow_cloud`, confirmation, classification gate, audit, budget, rate limit | Unit and `unit_server`: forced cloud call refused when closed or classified; every call writes an audit line; the browser cannot choose the base URL |
| L6 | Cloud providers: OpenAI-compatible and Anthropic, keys through environment variables from Podman secrets, `deploy.sh` support | Unit against fake servers; a deployment check that no key appears in the journal, an image layer or `podman inspect` |
| L7 | Golden set and report, user guide, status | CI run with the fake provider; report from the real model attached to the plan |

## 5. Files touched

New: `strictdoc/features/llm/` (providers, schema, context builder, prompts, router, policy, audit, templates, CLI script for the golden-set report),
tests `tests/unit/.../test_llm_*.py`, `tests/unit_server/strictdoc/server/44_llm*/`, end2end `screens/document/llm/`, a golden-set data folder.
Edited (shared, small): `strictdoc/core/project_config.py` (option `llm`, project feature `LLM`), `strictdoc/server/routers/main_router.py` (one
`include_router`), the requirement form and project menu templates (one block each), `strictdoc/core/environment.py` (template folder),
`ISIS/strictdoc-deploy/deploy.sh` and `Containerfile`.

## 6. Security and risks

- **Data leaving the network**: closed by default, per project, gated by classification, confirmed by a click, logged. The gate is enforced on the
  server.
- **Keys**: never in configuration, images or command lines (OpenBao, Podman secrets, environment variable inside the container); the base URL
  is fixed by configuration, so a user cannot turn the assistant into a request forwarder (no SSRF).
- **Prompt injection**: treated in 3.4; the only effect an injection can have is a bad proposal that a human reads.
- **Quality and trust**: a draft can look plausible and be wrong (a number invented, a missed constraint). The `Draft` status, the comment mark
  and the report of nodes not yet reviewed keep it visible.
- **Resources**: a 30-billion-parameter model on a CPU-only host with 30 GB of RAM shared with the other services may be slow or may push
  the machine into memory pressure (the host restarted once and OpenBao died during this work, cause not found). L0 measures before anything is
  built on it; Ollama is configured to unload the model after a short idle time.
- **Cost**: cloud calls cost money; the monthly token budget and the audit make it visible.

## 7. Open questions

1. **How does the container reach Ollama?** It listens on host loopback only. Options: (a) bind it to the host address and restrict the port with a
   firewall rule to the Podman network, (b) run Ollama as a container on `infra_default` with the models in a volume, (c) a small relay bound to the
   bridge address. Proposal: (b), decided in L0 with the memory results.
2. **Which local model?** The two installed models are code-oriented. Proposal: test them first, then one 7 to 14 billion parameter general instruction model;
   keep the choice in configuration.
3. **Review mode**: "Review with AI" on an existing requirement (ambiguity, atomicity, testability), returning comments in the plan 2 format. Out of this
   plan; proposed as a follow-up once drafting works.
4. **Should the audit store full prompts for local calls?** Proposal: no (`audit_store_prompts=false`), a project may turn it on.
5. **Languages**: REQ_02 is in French; the prompts must work in both languages. The golden set includes French cases.

## 8. Verification

- All tests above with the fake provider; the real-model golden-set report attached to this plan.
- Deployed: an author drafts from a parent requirement with the local model and creates two nodes, both `Draft` with the mark comment; a reader
  gets 403; a forced cloud call is refused with `allow_cloud=false`; the audit shows each call; no key or prompt in the system journal.
