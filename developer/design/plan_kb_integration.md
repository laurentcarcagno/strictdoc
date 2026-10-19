# Plan 7: the knowledge base for the assistant

Part of the [master plan](master_plan.md). Branch prefix `feature/kb-`. Depends on plan 6 ([assistant](plan_llm_assistant.md)), plan 1 (roles, audit)
and plan 3 ([Git configuration](plan_git_configuration.md)). The knowledge base itself (Git repositories `kb-<mission>`, PostgreSQL index, MCP server,
compiled wiki, CI) is specified in `plan-docdatabase.md` at the root of the ISIS workspace; this plan covers what StrictDoc and its deployment must do to use it.

Decisions: (D1) the assistant uses the base through a **tool loop**: the model chooses the MCP tools; (D2) StrictDoc authenticates with a Keycloak **service
account** and passes the user on whose behalf it calls; (D3) the server, the indexer and the images live in a new repository `kb-platform`; (D4) every component
is a **Podman container**.

## 1. Why

The assistant drafts and reviews requirements from the context the author selects: parents and input documents of the same project. It does not know the
ICDs, the system specifications or the other requirements of the mission, which are in the knowledge base. A model that can search that base and quote it
exactly writes better drafts and finds more inconsistencies, and the author gets the source of every claim. The base stays read-only for the assistant: only a
merge request changes it.

## 2. Current state

- `features/llm` makes one call per command (`LLMProvider.complete(LLMRequest)` returns text); the request has a system prompt, a user prompt and an optional
  schema. No tools, no multi-turn exchange. Providers: `OpenAICompatibleProvider` (Ollama, OpenAI), `AnthropicProvider`, `FakeProvider`.
- `policy.py` decides before each call (cloud closed unless `allow_cloud`, blocked classifications, monthly budget, rate limit); `audit.py` logs every call.
  `context.py` puts every piece of context between `BEGIN`/`END` lines and neutralises markers.
- The application runs on the internal network `strictdoc_internal` and reaches nothing else. It gets to the model, GitLab and Keycloak through relays
  (`strictdoc-llm`, `strictdoc-gitlab`, `strictdoc-kc`, made with `relay.py`), and its secrets are Podman secrets filled from OpenBao.
- Ollama runs on the host with `gpt-oss` as the default provider; the host has 30 GB of memory with about 8 GB free.

## 3. Design

### 3.1 Architecture

```
browser -> Caddy -> strictdoc-auth -> strictdoc (internal network)
                                         | https://kb.internal
                                      kb-relay -> kb-mcp -> kb-postgres
                                         ^ token of the service account strictdoc-kb
```

The model never reaches the MCP server. StrictDoc runs the tool calls that the model asks for, inside a bounded loop, and sends the results back to the
model as data.

### 3.2 Containers

| Container | Image | Role |
|---|---|---|
| `kb-postgres` | `postgres:17` + `pg_trgm` | the index, row-level security; internal network only; data in `~/kb-data/pg` |
| `kb-migrate` | `localhost/kb-platform` | migrations and roles; runs once |
| `kb-mcp` | `localhost/kb-platform` | read-only MCP server over HTTP; Caddy site `kb.karka.lan` |
| `kb-indexer` | `localhost/kb-platform` | rebuilds the index from Git (CI or `podman run --rm`) |
| `kb-tools` | `localhost/kb-tools` | image of the CI jobs (validators, lint, Docling, Pandoc, CA) |
| `kb-wiki-agent` | `localhost/kb-tools` | converts, compiles and lints the wiki with a local model; opens merge requests only |
| `kb-relay` | `localhost/infra-strictdoc` | alias `kb.internal` on the internal network of StrictDoc, towards `kb-mcp` |

Secrets: OpenBao `secret/kb/postgres` (database passwords) and `secret/strictdoc/kb` (secret of the Keycloak client `strictdoc-kb`), turned into Podman
secrets by `deploy.sh`; never on a command line, in an image or in `podman inspect`.

### 3.3 Identity

- Keycloak client `strictdoc-kb` (service account, client credentials), role `kb-reader`, allowed only for the missions that projects name in their `kb` option.
- Each call carries `Authorization: Bearer <token>` and `X-On-Behalf-Of: <user of StrictDoc>`. The MCP server accepts the header only from declared service
  accounts and answers only for the missions that the account and the user share (Keycloak groups). Both identities go to its `audit_log`.
- StrictDoc already knows the user (oauth2-proxy) and the project role; `reader` has no assistant. The tool loop runs with the role of the command.

### 3.4 In StrictDoc

New feature `strictdoc/features/kb/` and small extensions of `features/llm`. No shared component changes.

- `config.py`: project option `kb=KBConfig(url, mission, client_id, secret_env="KB_CLIENT_SECRET", tools=[...], max_steps=6, max_tool_chars=6000,
  timeout=15)`. The URL is `https://…` or `http://kb.internal`; it comes only from the configuration. `tools` is an allow-list of read-only tools.
- `client.py`: MCP client on the standard library (`initialize`, `tools/list`, `tools/call` over HTTP), token cache until expiry, the CA bundle of the
  platform (`KB_CA_BUNDLE`), a `request_id` per call.
- `features/llm/types.py`, `openai_compatible.py`, `anthropic.py`, `fake.py`: `LLMRequest.tools`, `LLMResponse.tool_calls`, multi-turn messages; the
  chat-completions `tools` field (Ollama accepts it), the Messages API `tool_use`/`tool_result`, scripted turns for the fake provider. Without tools nothing
  changes.
- `assist/agent_loop.py`: `ask_with_tools` makes at most `max_steps` rounds with a total timeout. It refuses any tool outside the allow-list, wraps each result
  between `BEGIN KB-DATA`/`END KB-DATA` lines with its citation after `neutralise`, cuts it to `max_tool_chars`, and stops on the first answer without a tool
  call. When the model makes no tool call on the first round of a command that needs the base (a model without tool calling), the loop falls back to
  **retrieval**: one `search` with the question before the call, the results added to the context as a `kb` item like a parent.
- `policy.py`: a result of the base carries the classification of its mission. A cloud provider is refused when the classification is blocked, when the
  mission's `allowed_models` (read through `list_missions`) does not list it, or when `allow_cloud` is off. The confirmation before a cloud call lists the
  citations that are included. Budget and rate limit count each round.
- `audit.py`: each tool call is logged (tool, mission, arguments as a hash, or in full when `audit_store_prompts` is on, characters returned, `request_id` of the
  MCP server); the result of a command lists the sources consulted.
- `assist/commands.py`: `/ask` and `/draft` use the base when the project has `kb` and the option "Use the knowledge base" is on (default on). New
  `/kb <question>` (reviewer): a search without a model, the result is exact citations. New `/cite <ID>` (author): inserts the text of a requirement of the base
  word for word, with its source, into the field.
- References to the base: `kb://<mission>/<doc_ref>/<edition>/<section>` links in the text, rendered as links to `kb.karka.lan`; a local check reports a
  citation whose requirement no longer exists or changed (reuses `assist/gaps.py`).
- UI: the bar shows "Base: <mission>" and lists the sources after an answer (DESIGN.md: sharp corners, no shadows); French catalogue entries; user guide section
  "Knowledge base".

### 3.5 Deployment (`strictdoc-deploy`)

`./deploy.sh --kb` (with `--projects`): network `kb_internal`; `kb-postgres`; `kb-migrate` then `kb-mcp`; Keycloak client `strictdoc-kb`; `kb-relay`
(alias `kb.internal`); Caddy block `# BEGIN kb`/`# END kb` for `kb.karka.lan` (a change restarts the proxy); `--add-host` if the host name is not
reachable from the internal network, as for GitLab. Images are built from `kb-platform` the way the StrictDoc image is built from the fork
(`Containerfile.kb`, `Containerfile.kb-tools`, the CA `~/INFRA/pki/root.crt` in the system store). Every container has a `--memory` limit. `check_kb.sh` tests
the network, the row-level security (a user outside the group gets nothing), the refusal of `X-On-Behalf-Of` from an undeclared client, and a tool call
through the application. The README gets a "Knowledge base" section and a row in "What the users get".

### 3.6 The repository `kb-platform`

`src/kb_indexer/` (Markdown, `.sdoc`, `fields.yaml`, `@req` tags; idempotent), `src/kb_mcp/` (tools, authentication, `SET LOCAL kb.user_groups` for row-level
security), `migrations/`, `containers/`, `tests/` (contract of each tool, identical index on two runs, row-level security, an instruction hidden in a section
is returned as data). First mission: ISIS.

## 4. Phases

1. `kb-platform`: migrations, indexer, Postgres container (phases 1 and 2 of `plan-docdatabase.md`).
2. `kb-mcp`, authentication, audit, relay, `deploy.sh --kb` (phase 3).
3. MCP client and tool loop in StrictDoc, `/kb`, `/cite`, policy and audit (phase 3b); deploy the fork.
4. Compiled wiki and lint in `kb-wiki-agent`, the `wiki_search` tool (phase 4).

## 5. Verification

- Unit: MCP client against a fake MCP server; the tool loop with the fake provider (a tool call, a tool outside the list, too many rounds, a result that
  imitates an instruction, a cut result); fallback to retrieval; cloud policy with mission classification; audit. `unit_server`: routes and roles. End to
  end: `screens/assistant_kb` (bar, `/kb`, citation).
- `kb-platform`: contract tests, two identical indexings, row-level security, `diff_versions` detects an injected sign change.
- Deployed: `./deploy.sh --kb`, `check_kb.sh`, `check_assistant.sh`, `CHECK_PROJECT=isis ./check_roles.sh`; a question about an ISIS requirement with
  `gpt-oss` returns the exact citation; nothing goes to a cloud provider without the confirmation.

## 6. Risks

- Tool calling depends on the model: measure `gpt-oss`, `qwen3-coder` and `devstral` before fixing the default; retrieval stays the safety net.
- Memory of the host: PostgreSQL and the MCP server are small; compiling the wiki runs on demand.
- A tool result is untrusted text: neutralised, bounded, never an instruction, read-only tools only.

## 7. Status and differences from the design

Phases 1 to 3b are done and deployed (`deploy.sh --kb`, `check_kb.sh` passes with `gpt-oss:20b`, `devstral-small-2` and `qwen2.5:3b`, which all call tools).
What changed while building:

- The loop is a step before the command, not the command itself. A model with the tools collects the context (`assist/agent_loop.py`, prompt
  `kb_gather`), then the usual call with the JSON schema of the command writes the answer. So the parsing, the repair retry and the typed operations
  of every command are unchanged, and no provider has to combine tools and a schema. The commands that look in the base are the `commands` of `KBConfig`
  (default `ask`, `req`, `verify`).
- The option is `llm=LLMConfig(kb=KBConfig(...))`, not a new option of `ProjectConfig`: no shared component changed except `llm/config.py`, `types.py`,
  the three providers, `audit.py` and the bar.
- The rate limit counts a command once; the rounds are bounded by `max_steps` and a total time. The cloud budget is not touched by the loop because a
  cloud provider never runs it: it gets one plain search (no model), the user confirms what is sent, and the confirmation lists the citations. The mission must
  name the model in `allowed_models` and its classification must not be blocked.
- The token endpoint is reached through the relay `strictdoc-kc` (`http://keycloak-admin:8080`), the base through `kb-relay` (`http://kb.internal:8080`);
  both addresses may be plain http only with these names.
- The bar shows the sources under "Base: <mission>"; `/cite` replaces the selection or adds a quoted block (`> text` and `> — ID, document ed. section (kb:// link)`)
  at the end of the field. A requirement that the server cut is not cited.
- The proxy of the login waited 30 s for the app by default; a loop takes 10 to 40 s, so `--upstream-timeout=300s`.
- Not done: the check of `kb://` links in a text (`check-kb`, drift), the `screens/assistant_kb` end-to-end test (`check_kb.sh` covers the deployed path), the French
  catalogue (the bar is in English), `/kb` in the document bar.
