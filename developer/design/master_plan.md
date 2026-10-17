# Master plan: from a Word-capable editor to a shared requirements tool

Branch: `feature/plans`, based on `feature/isis-integration`. Written 2026-10-10. Status: plan only, nothing implemented.

Dedicated plans (same folder): [roles and identity](plan_roles_and_identity.md), [comments](plan_comments.md),
[SVG images](plan_svg_images.md), [document hierarchy and input documents](plan_document_hierarchy_and_inputs.md),
[multi-project](plan_multi_project.md), [LLM assistant](plan_llm_assistant.md),
[configuration management with Git and GitLab](plan_git_configuration.md),
[knowledge base for the assistant](plan_kb_integration.md). The Word import and export plan
(`docx_import_export_plan.md`) is on branch `feature/docx-import-export`; the web dialogs plan is `docx_gui_plan.md`.

## 1. Where we are

The ISIS fork of StrictDoc 0.30.2 (branch `feature/isis-integration`, deployed at https://strictdoc.karka.lan) already has:

- Word import (RST and Markdown), fresh Word export from a template, update of an existing Word file with tracked changes, images
  (PNG, JPEG, GIF) embedded in Word, web dialogs for all of it (feature `DOCX`).
- A WYSIWYG Markdown editor (Milkdown) for the content of nodes of `MARKUP: Markdown` documents; a table view limited to requirements.
- A deployment script (`strictdoc-deploy/deploy.sh`): rootful Podman, Caddy site, Keycloak client and OpenBao secrets, oauth2-proxy login limited
  to one Keycloak group.

What it does **not** have: any notion of a user (everybody who gets in can edit everything), any structure above "a folder of documents",
review comments with an author, SVG in Word, input documents, or help from a language model.

## 2. Vision

One server where several projects live side by side, each with a document hierarchy (customer specification, equipment ICD, system, software,
design, test), where people have a role, reviewers comment and the comments reach the Word deliverable, and where an author can ask a model for
a first draft of requirements that a human then edits and approves. The Word document remains the contractual deliverable; StrictDoc is the
working copy that keeps traceability.

## 3. Decisions taken

| # | Topic | Decision | Plan |
|---|---|---|---|
| D1 | LLM policy | Local by default (Ollama on the host), cloud providers (OpenAI, Claude, ...) optional **per project**, API keys in OpenBao, warning before anything leaves the network, log of what is sent | LLM |
| D2 | Multi-project | **Several projects in one server process**, selected by host name | Multi-project |
| D3 | Roles | reader, reviewer, author, administrator, carried by Keycloak groups and enforced by the server | Roles |
| D4 | Order | roles, comments, SVG, hierarchy and input documents, multi-project, LLM | this plan |
| D5 | Language | English for every document | all |

## 4. Features, order and dependencies

| # | Feature | Depends on | Size (days, one person, rough) | Branch prefix |
|---|---|---|---|---|
| 1 | Roles and identity (includes the `ProjectContext` refactor R0) | none | 6 | `feature/roles-` |
| 2 | Comments, visible in the web interface and in Word | 1 (reviewer role, author name) | 8 | `feature/comments-` |
| 3 | SVG images in Word | none (placed third by choice) | 5 | `feature/svg-` |
| 4 | Document hierarchy and input documents | 1 (read-only kind, author role) | 12 | `feature/hierarchy-` |
| 5 | Multi-project in one server | 1 (`ProjectContext`, per-project roles), 4 (projects have a hierarchy) | 10 | `feature/projects-` |
| 6 | LLM assistant | 1 (author role, audit), 4 (context from parents and inputs) | 12 | `feature/llm-` |
| 7 | Configuration management with Git and GitLab (commit on save, submodules, version tags) | 1 (roles for tag and push), 3 (assets are committed with the document) | 6 | `feature/git-` |

Total about 59 days. The figures are estimates to be revised after each milestone, as in the Word plan.

Why this order:

- `ProjectContext` is built first (step R0 of the roles plan). Today the per-project state (traceability index, writer, templates, revision
  counters) lives in the closure of `create_main_router` in `strictdoc/server/routers/main_router.py`. Moving it into one object, with no
  behaviour change, lets roles be per project from the start and lets multi-project later only create several contexts.
- Roles before comments and LLM: both need to know who is acting and whether they may.
- Hierarchy before multi-project: a project is "a hierarchy of documents", so the structure is settled first.
- LLM last: it consumes relations, input documents and roles, and its quality needs the other features to give it context.
- SVG is independent and small; it fits anywhere without blocking the others.
- Git configuration management is last: it commits what the other features write (documents, comments, assets) and uses the roles for tag and push. It touches only the save path, the upload and delete routes and two menu templates, so it does not block them.

## 5. Cross-cutting rules

1. **Trust boundary.** The application is reachable only through oauth2-proxy (it sits on the private Podman network `strictdoc_internal`).
   Identity comes from the headers that the proxy adds. The application trusts them only in this configuration, never in `--no-auth` mode,
   and Caddy removes any identity header that a client sends.
2. **Secrets.** Never in a configuration file, a command line (sudo writes command lines to the system journal) or an image. OpenBao for
   storage, Podman secrets or a private temporary file for transport. API keys of LLM providers follow the same rule.
3. **Every feature is a project option, off by default**, and its code is feature-local (`strictdoc/features/<name>/`, one router, one template
   folder), as `docx` and `milkdown` already are. The only edits to shared files are one `include_router` call, one menu block and one line in
   `strictdoc/core/environment.py`. This keeps the fork rebasable on upstream.
4. **No change to the SDoc grammar** unless a plan says so and says why. Where data must be stored in a node, the plans use existing means (the
   `COMMENT` field, document custom metadata) before adding syntax.
5. **Fail closed.** A route, a menu entry or a screen without an explicit permission is refused, and a test enumerates the routes to prove it.
6. **Qualification friendliness.** Every change of a requirement keeps a trace (who, when); the Word export stays the deliverable; nothing generated
   by a model is saved without a human decision.

## 6. Test strategy (all already available)

| Level | Tool | Where it runs |
|---|---|---|
| Unit and service | pytest | `tests/unit`, dev container `strictdoc-dev/run.sh` |
| HTTP behaviour | FastAPI `TestClient` | `tests/unit_server/strictdoc/server/` |
| Browser behaviour | SeleniumBase end2end | `strictdoc-dev/browser/run_e2e.sh <path>` (about 400 tests; `screens/document` takes 15 minutes) |
| Word output | LibreOffice rendering, reject-all and accept-all comparison | image `isis-libreoffice` |
| Deployed instance | login and Word preview check | `strictdoc-deploy/check_login.py` |

Known limits: the 5 `_export_to_pdf` end2end tests fail in the container (html2pdf4doc finds no Chrome); Word itself is never available, so
every Word-visible change is checked with LibreOffice and by reading the package, and the user opens one sample in Word.

Definition of done for every step of every plan: unit or server tests, the relevant end2end family green (and `screens/document` before a
milestone merge), user guide updated, `HANDOFF.md` updated, no secret in the system journal, deployment checked.

## 7. ISIS-specific need that drives feature 4

REQ_02 holds `Linked Req` values such as `[DA1] §5.14.1 ; [DA2] REQ-106005, REQ-106006, REQ-0280`. `DA1` and `DA2` are applicable documents
(the PUS standard and the customer specification). Today the import turns only the names that match a requirement of the same document into
Parent relations; the rest stays text. Feature 4 makes `DA1` and `DA2` real input documents in the project, so that these references become
relations that the traceability screens can follow.

## 8. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Fork divergence from upstream StrictDoc | Rebase effort grows with every touched shared file | Rule 3; feature-local code; a rebase rehearsal at each milestone merge |
| Size of the end2end suite | Slow feedback | Run the family concerned, the whole `screens/document` before merge, the rest nightly |
| Local model quality and memory | The assistant may be unusable | Spike first (LLM plan L0): the host has 30 GB of RAM with about 8 GB free; the two installed models need 15 to 19 GB each and are tuned for code |
| Ollama listens on `127.0.0.1` only | The container cannot reach it | Decide in the LLM plan how it is exposed (see its open questions) |
| SVG from users | Script or file access through a hostile file | Sanitise on upload and again before rasterizing; serve assets with a sandboxing policy |
| Header-based identity | Spoofing if the proxy is bypassed | Network isolation, Caddy header stripping, a test that a direct request without the proxy is refused |
| Word comments identity | Duplicates when comments travel Word to SDoc and back | Identity rules in the comments plan, with a round-trip test |
| Host stability | The machine restarted during a deployment and OpenBao died; deployments depend on it | Deployment script checks and reports; investigate the cause separately |

## 9. Milestones and acceptance

| Milestone | Accepted when |
|---|---|
| M-R (roles) | A reader cannot reach any edit form or write route (test over all routes); the four roles work with Keycloak groups on the deployed instance; the audit log names the user of every write; the whole `screens/document` suite is green with the feature on and off |
| M-C (comments) | A reviewer adds a comment, an author resolves it; both are visible in the web interface; a Word export shows the comments in the review pane of LibreOffice and in the XML as native comments; an update keeps comments added in Word |
| M-S (SVG) | An SVG uploaded in the editor shows in the web page and in Word (PNG fallback plus vector extension); a hostile SVG file is neutralised (tests); the package opens in LibreOffice |
| M-H (hierarchy) | REQ_02 `Linked Req` references to DA1 and DA2 become relations to imported input documents; changing an input document lists the suspect downstream requirements; input documents cannot be edited in the interface |
| M-P (projects) | Two projects run in one process on two host names with separate data, roles and output; a user of project A gets 403 on project B; memory per project is measured and documented |
| M-G (Git) | A save makes one commit by the configured author, in the repository that owns the file (a submodule commit is followed by the pointer commit of the project); an uploaded image and the removal of the assets of a deleted node are committed with the next save; tags go `A1`, `A2`, `A`, `B1`; a diverged push is refused; the page is in the menu only with the feature on |
| M-L (LLM) | An author drafts requirements from a parent and an input section with the local model; the proposals are saved only after editing; a cloud call needs the project option and a confirmation and is logged; the golden set passes with a mocked provider |

## 10. Open decisions (consolidated)

Each dedicated plan lists its own questions; the ones that block a milestone are:

1. Where comment identity lives when a comment goes to Word and back (comments plan, section 7).
2. How the `KIND` and the hierarchy are stored without touching the grammar (hierarchy plan, section 7).
3. How the container reaches Ollama, and whether a smaller general model is added (LLM plan, section 7).
4. Wildcard certificate for `*.strictdoc.karka.lan` with the private CA, and the name resolution on the server itself (multi-project plan, section 7).
5. Whether the rasterizer for SVG is a library or LibreOffice (SVG plan, spike S0).
