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
