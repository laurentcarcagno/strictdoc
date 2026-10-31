# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

AGENTS.md is mandatory: print its compliance statement first, follow the Developer Guide (`docs/strictdoc_11_developer_guide.sdoc`, read-only), and do not edit `developer/tasks/<task_id>/` files other than `Context.md`.

## Commands

All development tasks are Invoke tasks in `tasks.py` (`invoke --list`). Python 3.10+.

- `invoke server` (alias `s`): run the web server from source (`--input-path`, `--port`).
- `invoke check` (alias `c`): all lint and test tasks except end-to-end tests.
- `invoke lint`: ruff format, ruff, mypy, JS format, fixit. Single linters: `lint-ruff`, `lint-mypy`, `lint-ruff-format`.
- `invoke test-unit [--focus <substring>] [--path tests/unit/...]`: pytest unit tests. `test-unit-server` covers `tests/unit_server`.
- `invoke test-integration [--focus <substring>]`: LIT/FileCheck command-line tests in `tests/integration` (each test dir holds `.itest` files).
- `invoke test-end2end --headless [--focus <substring>] [--test-path ...]`: Selenium web tests in `tests/end2end`. Always pass `--headless`.
- `invoke docs`: export StrictDoc's own docs (`docs/*.sdoc`).

On a Windows workstation, run tests in Docker, not on the host (endpoint protection flags the test processes):

    powershell -File developer/docker_tests/run_tests.ps1 invoke test-unit

Do not write throw-away smoke tests. A new feature needs at least one integration or end-to-end test.

## Code conventions that are easy to miss

- Line length 80. Full descriptive names (`document`, not `doc`). Type annotations on all new code.
- Explicit checks: `if foo is not None`, never `if foo`.
- Public functions above private (`_`-prefixed) ones in a module.
- Loop and lambda variables end in `_` (`for item_ in items`).
- Open files with `file_open_read_utf8` / `file_open_read_bytes`, not `open()`.
- Code carries `@relation(SDOC-..., scope=...)` markers that trace to requirements in `docs/` and `spec/`.
- Commits: one self-contained commit per PR, rebase on `main` rather than merging it. Apply `developer/skills/humanizer/SKILL.md` to any prose written into commits, PRs, docs, comments or task files.
- Skills live in `developer/skills/<name>/SKILL.md`. After changing one, run `python developer/skills/install_skills.py` to regenerate the (gitignored) Claude/Codex stubs.
- Work on `developer/tasks/<task_id>/` tasks keeps notes in that task's `Context.md` (read it first, create it if missing).
- Do not change shared components for a local feature without approval. Prefer feature-local templates, scripts and styles.

## Architecture

StrictDoc is a requirements and documentation tool. It reads `.sdoc` files (plus Markdown, RST, ReqIF and source-code annotations), builds an in-memory traceability graph, and either exports it (HTML, PDF, DOCX, Excel, ReqIF, JSON, SPDX) or serves it as an editable web app.

Pipeline, in order:

1. **Backends** (`strictdoc/backend/`): one package per format. `backend/sdoc` is the main one: a textX grammar (`grammar/`) parsed into model classes (`models/`: document, node, grammar_element, free_text, ...), with `reader.py`, `writer.py` and validations. Documents can define their own grammar, so node fields are dynamic. `backend/sdoc_source_code` parses `@relation` markers in source files (tree-sitter).
2. **Core** (`strictdoc/core/`): `traceability_index_builder.py` loads all documents into a `DocumentTree` and builds the `TraceabilityIndex` / `GraphDatabase` that holds requirement-to-requirement and requirement-to-file links. `project_config.py` holds `strictdoc.toml` / `strictdoc_config.py` settings. `actions/` run the export and convert flows.
3. **CLI** (`strictdoc/cli/main.py`): dispatches subcommands, each a pair of `commands/<name>_command.py` and `<name>_config.py` (export, server, convert, format, manage, new, ...).
4. **Export** (`strictdoc/export/html`): Jinja2 templates and generators for the static HTML site. Static HTML and the server share these templates.
5. **Server** (`strictdoc/server/`): FastAPI app (`app.py`, `routers/`) served by uvicorn. It re-renders the same Jinja templates, mutates the document model in memory, writes `.sdoc` back, and uses reader/writer locks (`helpers/rw_lock.py`) around the index. The UI is server-rendered HTML updated via Turbo-style partial responses (`helpers/turbo.py`) with form objects under `export/html/form_objects`.
6. **Features** (`strictdoc/features/`): self-contained vertical slices (search, tree_map, page_view, milkdown Markdown editor, i18n, html2pdf, docx, trace, ...). Each owns its templates and assets, so a feature change should stay inside its directory.

Frontend assets and vendored JS (for example Milkdown) are built from `developer/milkdown` and committed under the feature's `assets` directory.

Tests: `tests/unit` (pytest), `tests/integration` (LIT), `tests/end2end` (Selenium, page-object style helpers in `tests/end2end/helpers` and `screens`), `tests/screencast` (recorded UI demos).
