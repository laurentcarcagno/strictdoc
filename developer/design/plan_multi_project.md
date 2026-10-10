# Plan 5: several projects in one server

Part of the [master plan](master_plan.md). Size: about 10 days. Branch prefix `feature/projects-`. Depends on plan 1 (`ProjectContext`, per-project roles)
and plan 4 (a project is a hierarchy of documents).

Decision D2: several projects in **one server process**, not one instance per project.

## 1. Why

The same team works on several programs, each with its own documents, Word profile, people and rights. One process, one login, one place to
back up and update, and a portal where a person sees only the projects they belong to. The tool must keep projects apart: the data, the
traceability index, the output, the roles and the audit log of one project never show in another.

## 2. Current state

- `strictdoc server <input_path>` takes **one** folder (`strictdoc/commands/server.py`, positional `input_path`). The configuration is pickled
  to a temporary file and read back by the worker through the environment variable `PATH_TO_CONFIG` (`strictdoc/server/config.py`,
  `strictdoc_production_app` in `strictdoc/server/app.py`).
- `create_app(project_config=...)` (`strictdoc/server/app.py`) builds a complete FastAPI application (middleware, lifespan with the document
  watcher, the lock manager, the routers). One application is one project: `create_main_router` builds one traceability index
  (`ExportAction`), one template environment with its cache, one writer and one `revisions` dictionary.
- `ProjectConfig.input_paths[0]` is used by the router and by the Word service; the output folder is `project_config.output_dir`.
- Pages and forms use **absolute URLs** (`/actions/...`, `/_static/...`, `/fragments/...`, `/UID/...`). A path prefix per project
  (`/p/<slug>/...`) would require rewriting hundreds of links in templates and scripts and would break every future upstream merge.
- Name resolution: the home DNS container (`dns`, dnsmasq) answers `*.karka.lan` with the host address, so any new host name under the domain
  resolves from other devices. The server itself resolves names from `/etc/hosts` (no wildcard there). Caddy (`~/INFRA/proxy/Caddyfile`, `local_certs`
  with its own CA) serves one site block per name.

## 3. Design

### 3.1 One application per project, chosen by host name

The existing per-project application is reused as it is: for each project the server builds `create_app(project_config=...)`. A small ASGI
dispatcher (`strictdoc/features/projects/dispatcher.py`) sits in front and picks the application by the `Host` header:

```
strictdoc.karka.lan            -> portal (list of projects)
<slug>.strictdoc.karka.lan     -> application of the project <slug>
```

Because each project has its own host name, every absolute URL keeps working unchanged. The cookie-based alternative (one host, a
`project` cookie chosen in a switcher) is rejected: two browser tabs on two projects would share the cookie and silently switch each other.

The dispatcher also drives what Starlette does not do for sub-applications: it runs each project's lifespan (start and stop of its
`DocumentWatcher`, `app.state.event_loop`) when the server starts and stops.

### 3.2 Project registry

A Python file, like `strictdoc_config.py`, listed on the command line: `strictdoc server --projects strictdoc_projects.py`
(the positional `input_path` becomes optional when `--projects` is given). It defines `create_projects() -> List[ProjectSpec]`:

```python
ProjectSpec(slug="revalto", title="Revalto flight software", path="/data/revalto", config="strictdoc_config.py",
            roles={"administrator": ["revalto-admins"], "author": ["revalto-authors"],
                   "reviewer": ["revalto-reviewers"], "reader": ["revalto-readers"]})
```

Each spec loads its own `strictdoc_config.py` from its folder (the profile, features, hierarchy of plan 4) and gets its own output folder
`<output>/<slug>/`, so caches, generated assets and the audit log are separate. The roles of plan 1 are stored in the spec (or in the project's own
config) and are evaluated per project: the dispatcher builds the `Principal` once, the project context maps groups to a role.

### 3.3 Portal

`https://strictdoc.karka.lan/` shows the projects the user can open: those whose role mapping contains one of the user's groups, with the
role, the title, the number of documents and the last change. A user in no project group sees a clear message. The portal is a feature-local
template; it needs no project context.

### 3.4 Authentication across hosts

- oauth2-proxy keeps its single callback on the root host (`https://strictdoc.karka.lan/oauth2/callback`) and sets the cookie for the parent domain:
  `--cookie-domain=.strictdoc.karka.lan` and `--whitelist-domain=.strictdoc.karka.lan`; a login started on a project host returns to it.
- Caddy gets a wildcard site `*.strictdoc.karka.lan` next to the root name, with the same upstream. The wildcard certificate comes from Caddy's
  internal CA (`tls internal`); whether the internal issuer accepts a wildcard name is checked in step P5.
- The Keycloak client keeps one redirect URI. Nothing changes in Keycloak except the group names.

### 3.5 What is shared and what is not

Per project (own copy): traceability index, templates and their cache, writer, `revisions`, lock manager, watcher, output folder, audit log,
roles, Word profile, feature options. Shared: the process, the Python modules, the static StrictDoc assets (identical files, served from each
project's output folder; deduplication is a later optimisation), the portal and the dispatcher.

Memory is the cost of per-project indexes. P4 measures it (a 131-requirement document and a 3,000-node synthetic project) and writes the
numbers here.

### 3.6 Word import and export

`docx_web_service.py` and `docx_router.py` already take everything from the project's `project_config` (`input_paths`, `docx_profile`,
`docx_base`); they work per project with no change once each project has its own config and context.

## 4. Steps

| Step | Content | Tests |
|---|---|---|
| P1 | `ProjectSpec`, registry loading and validation (duplicate slugs, path outside the data root, missing config), context factory that builds one application per spec using plan 1's `ProjectContext` | Unit: registry errors; two specs give two independent contexts (changing a node in A does not change the index of B) |
| P2 | ASGI dispatcher by host, lifespan handling, unknown host answers 404 with no information, `strictdoc server --projects` | `unit_server`: two hosts return their own documents; unknown host 404; both watchers start and stop |
| P3 | Portal and per-project role evaluation | `unit_server` with fixed headers: user of A sees only A in the portal and gets 403 on B; user of both sees both |
| P4 | Isolation of output, cache and watcher; memory measurement | A test that writes in A and checks B's folder is untouched; a script that records RSS for 1, 2 and 5 projects |
| P5 | `deploy.sh`: generate the registry, the data folders, the wildcard Caddy block, `/etc/hosts` entries (or a resolver) for the server itself, oauth2-proxy cookie domain | `check_login.py` for two projects: login on one host, open the other without a second login, each shows only its documents |
| P6 | End2end on two projects, no data leaks, parallel edits in both | SeleniumBase with two hosts (the test server learns to start with a registry) |

## 5. Files touched

New: `strictdoc/features/projects/` (registry, dispatcher, portal, templates), tests `tests/unit_server/strictdoc/server/43_projects*/`.
Edited (shared, small): `strictdoc/commands/server.py` (`--projects`, positional optional), `strictdoc/server/config.py` and `app.py` (load a registry in
the worker), `strictdoc/commands/server_config.py`, `strictdoc/core/project_config.py` (slug), `ISIS/strictdoc-deploy/deploy.sh`,
`~/INFRA/proxy/Caddyfile` (managed block).

## 6. Security and risks

- **Cross-project leakage** is the main risk. Each context is built from its own config; the dispatcher never passes a request to a project
  other than the one named by the host; every project route enforces the project's roles (plan 1); a test requests B's paths with A's host name
  and with A's cookies.
- **Host header trust**: only the exact names of registered projects are served; everything else is 404. Caddy only forwards the known wildcard.
- **Resource use**: N indexes, N template caches, N watchers in one process; one project's long operation holds only that project's lock,
  but the Python process is shared (the GIL), so a heavy export in A slows B. Measured in P4; the fall-back (separate processes behind the same
  dispatcher) is possible because the project application is already self-contained.
- **A crash or a stuck loop** takes every project down. Mitigation: health endpoint, restart policy, and the P4 measurement of a failing project's
  effect on the others.
- **Rebase cost**: small, because the shared edits are the command, the worker start and the config; the routers are untouched.

## 7. Open questions

1. Wildcard certificate from Caddy's internal CA, and the name resolution of `<slug>.strictdoc.karka.lan` on the server itself (it does not use
   the dnsmasq container): proposal, a local resolver entry per project written by `deploy.sh`. To check in P5.
2. Project creation: file-based only (an administrator edits the registry and restarts), or a "create project" screen? Proposal: file-based first.
3. Should a project be able to be archived (read-only for everyone)? Proposal: a registry flag `archived=True`, simple to add.

## 8. Verification

- The tests above; the whole end2end families still pass with a one-project registry (equivalent to today).
- Deployed with two projects: three users in different groups, checked with a headless browser; no cross-over; the journal shows no secret.
- Memory table in section 3.5 filled with measured numbers.

## 9. Delivered

P1 to P4 are done on branch `feature/projects`; the deploy support of P5 is written and partly checked; P6 is covered by server tests, not by a browser.

- P1 `features/projects/registry.py`: `ProjectSpec`, `load_registry`, validation (slug, duplicate slug, missing folder or configuration, folder outside the
  data root including links that leave it, two projects on one folder, bad roles), `build_project_config` (own output folder, own audit folder, own roles; the
  `STRICTDOC_ROLES` of a one-project deployment does not apply). `archived=True` is implemented (open question 3): every group becomes `reader`.
- P2 `dispatcher.py`: host to application, lifespan of every project started and stopped, bare 404 on an unknown host (and a closed WebSocket), `/healthz` on
  every host. `strictdoc server --projects FILE --root-host HOST [--data-root DIR]`; the input path is optional then.
- P3 `portal.py`: lists the projects whose roles contain a group of the user, with role, documents and last change; a message for a user in no project.
  Each project enforces its own roles (a user of alpha gets 403 on beta).
- P4 tests: a change in alpha leaves the files and the output folder of beta untouched; one audit log per project, a refusal is audited in the project that refused;
  a real `strictdoc server --projects` process serves two projects on one port.
- Memory (`developer/design/measure_projects_memory.py`, resident memory of the server process after one page request per project, Python 3.12, Linux):

| Projects | 131 nodes each (size of REQ_02) | 3,000 nodes each |
|---|---|---|
| 1 | 150 MB | 327 MB |
| 2 | 160 MB | 404 MB |
| 5 | 181 MB | 533 MB |

  One more small project costs about 8 MB; one more 3,000-node project about 45 to 75 MB. The host has about 8 GB free: not a limit for this use.
- P5 `strictdoc-deploy/deploy.sh --projects`: registry in `~/strictdoc-projects/projects.py` (seeded with one project, `isis`), Keycloak groups and oauth2-proxy
  allowed groups taken from the registry, `--cookie-domain` and `--whitelist-domain` on the parent domain, Caddy block with `strictdoc.<domain>, *.strictdoc.<domain>`,
  `/etc/hosts` entries per project for the server itself, a `/healthz` check. Checked: `bash -n`, the generated Caddy block validates with Caddy, and
  **open question 1 is answered: Caddy's internal CA signs the wildcard name** (checked with a throwaway Caddy, SAN `*.strictdoc.<domain>`).
  Not checked live: the whole script in `--projects` mode, the login across two hosts (`check_login.py` for two projects).
- Not done: the SeleniumBase end2end on two hosts (the unit_server tests and the real-process test cover the isolation).
- Limits: all projects share the Python process (a heavy export in one slows the others, a crash stops all); `auth_mode` is the same for every project.

### Delivered later: projects and members created in the portal, reviewers per document

Branch `feature/membership`. The "create project" screen that was left out is done, with members and reviewers:

- `features/projects/store.py`: `ProjectStore`, one JSON file `projects.json` next to the registry (projects created by administrators, members of every project,
  atomic write). A member is a user name (lower case) with one of the four roles.
- `manager.py`: `ProjectManager` creates the folder and a `strictdoc.toml` (tables, traceability, search, `COMMENTS`), builds the application, adds it to the
  dispatcher and starts its lifespan, with no restart. Platform administrators: the groups that are administrators of every registry project, or
  `STRICTDOC_PLATFORM_ADMINS`. A project created this way takes the groups of the platform administrators as its administrators plus its member list.
- `PrincipalMiddleware` takes the highest of the role of the groups and the role of the member list. `members_router.py`: `/members` and
  `/actions/members/set|remove`, administrator only. The portal has a "New project" form (platform administrators) and a Members link.
- `features/reviewers/`: the reviewers of a document are the custom metadata `REVIEWERS: ann, bob`. The comment routes now accept any member and check
  `can_comment` (author or above, a project-wide reviewer, or a reviewer named on the document); the Comment button of a reader appears only on the
  documents that name them. Creating a document needs the author role (it was administrator) and its form has a Reviewers field with the COMMENTS feature.
- Tests: `tests/unit_server/.../49_membership`, `tests/unit/.../membership`, and an end2end test of the form (`create_document_with_reviewers`).
- Not done: member names are not checked against Keycloak (a typo gives a member who never logs in); no invitation by e-mail; the live instance still runs one
  project (`--projects` is not deployed yet).
