# 05 - Serveur web

Fichiers : `strictdoc/server/` (7 450 lignes dont `routers/main_router.py`
5 700), `strictdoc/commands/server.py`, `features/*/router.py`.

## Démarrage

```
strictdoc server <dossier>            commands/server.py : ServerCommand.run
  ProjectConfigLoader.load_using_server_config()
  server/server.py : run_strictdoc_server()
      pickle de la ProjectConfig dans un fichier temporaire
      variable d'environnement PATH_TO_CONFIG = ce fichier
      uvicorn.run("strictdoc.server.app:strictdoc_production_app", factory=True)
        app.py : strictdoc_production_app()   relit la config (pickle_load)
          create_app(project_config=...)       construit l'application FastAPI
```

Le passage par un fichier pickle vient du fait qu'uvicorn instancie
l'application avec une fabrique sans argument. `server/config.py` donne les noms
des variables d'environnement (`PATH_TO_CONFIG`, `STRICTDOC_PROJECTS_FILE`,
`STRICTDOC_ROOT_HOST`, `STRICTDOC_DATA_ROOT`, `STRICTDOC_OUTPUT_ROOT`).
`reload_config.py` règle le rechargement d'uvicorn pour `--reload`
(développement de StrictDoc uniquement).

Mode plusieurs projets : `run_strictdoc_projects_server` puis
`strictdoc_projects_app()` (voir [08](08-features-fork-isis.md)).

## `create_app()` (`server/app.py`)

Ordre des middlewares, du plus externe au plus interne (Starlette applique
l'inverse de l'ordre d'ajout) :

| # | Middleware | Rôle |
|---|---|---|
| 1 | `SvgHeadersMiddleware` (`features/svg/headers.py`) | en-têtes sûrs sur tout fichier SVG servi |
| 2 | `PrincipalMiddleware` (`features/roles/middleware.py`) | décide qui agit (en-têtes oauth2-proxy), refuse avec 401 si la requête ne vient pas d'un réseau de confiance |
| 3 | `AuditMiddleware` (`features/roles/audit.py`) | journal JSON-lines des requêtes qui modifient |
| 4 | `RoleMiddleware` (`features/roles/enforcement.py`) | refuse si le rôle ne suffit pas pour la route (table `route_roles.py`). Un navigateur refusé reçoit la page 403 dans le cadre du projet (`render_app_screen`, gabarit `features/roles/refused.jinja.html`) ; un client JSON reçoit `{"detail": ...}`. Reçoit `project_config` et `env` (fonction qui rend l'environnement Jinja du projet) |
| 5 | `CORSMiddleware` | origines localhost |
| 6 | middleware HTTP de temps | affiche `PERF: GET /x 0.012s` sur la sortie standard |

Ensuite :

- sans `auth_mode="proxy"`, les rôles sont désactivés (tout le monde est
  administrateur) ; avec `proxy`, la documentation `/docs` d'OpenAPI est coupée ;
- un `HierarchicalRWLockManager` unique pour l'application ;
- routeurs inclus : membres (si `members_admin`), `other_router`, puis, une fois
  le `ProjectContext` créé, le routeur des rôles (`/whoami`, `/audit` :
  `create_roles_router(project_config=, env=context.env, audit_log=)`, qui rend
  l'écran d'audit dans le cadre du projet) et `main_router` ;
- `ProjectContext.create(project_config)` : tout l'état d'un projet (voir
  ci-dessous), mis aussi dans `app.state.project_context` ;
- `check_routes_classified(app.router.routes)` : **le serveur refuse de démarrer
  si une route n'a pas de rôle** dans `ROUTE_ROLES`. Toute nouvelle route doit y
  être déclarée.

## `ProjectContext` (`server/project_context.py`)

Un objet par projet. Il remplace ce qui vivait auparavant dans la fermeture de
`create_main_router`.

| Attribut | Rôle |
|---|---|
| `project_config` | configuration, `is_running_on_server = True` |
| `export_action` | `ExportAction` ; `export_action.traceability_index` est l'index courant, **réaffecté** à chaque reconstruction |
| `html_templates`, `html_generator` | rendu des pages ; assets exportés au démarrage (`export_strictdoc_assets`, `export_project_assets`) |
| `revisions` | `Dict[MID, int]` : compteur de version par nœud, pour détecter l'édition concurrente |
| `sdoc_writer` | `SDWriter` |
| `git_committer` | `GitCommitter` si l'option `git` est active |
| `connections` | `ConnectionManager` WebSocket (rechargement des navigateurs) |
| `document_watcher` | observateur de fichiers si `--watch` |
| `server_features_by_screen_filename` | écrans portés par une `Feature` (statistiques de projet, tree map) |

Méthodes : `write_document_to_file(document)` (inhibe l'observateur, écrit via
`SDMarkdownWriter` pour `.md` et `.markdown`, sinon `SDWriter`, puis prévient le
committer Git), `rebuild_index(lock_manager)` (reconstruit l'index sous verrou
d'écriture global, renvoie le message d'erreur ou `None`), `env()`.

Le dispatch d'écriture est codé en dur sur l'extension (voir le `FIXME` de
`write_document_to_file`) : un troisième format éditable serait mal écrit.

## Verrous

`server/helpers/rw_lock.py` : `RWLock` lecteurs/écrivain avec priorité aux
écrivains. `hierarchical_rw_lock_manager.py` : `HierarchicalRWLockManager`.

| Méthode | Usage |
|---|---|
| `acquire_global_read()` | lecture de l'index et des pages |
| `acquire_global_write()` | toute modification de l'index |
| `acquire_subset(read_ids=..., write_ids=...)` | verrous fins par ressource (clé `document:<chemin>`) ; prend d'abord le verrou global en lecture, puis les ressources dans l'ordre trié (pas d'interblocage) |

Non réentrant : ne pas appeler `acquire_subset` en tenant déjà un verrou global.
Les routeurs de `main_router` sont séparés en `read_router` (dépend de
`read_lock`) et `write_router` (dépend de `write_lock`, `merge_guard`,
`input_guard`, `baseline_sync`). **Cette séparation concerne le verrouillage,
pas les droits** : plusieurs `GET` qui ouvrent un formulaire d'édition sont dans
`read_router` ; leur rôle est dans `route_roles.py`.

Dépendances du `write_router` :

| Garde | Fichier | Effet |
|---|---|---|
| `merge_guard` | `features/git_sync/guard.py` | 423 tant qu'une fusion Git attend la résolution de ses conflits |
| `input_guard` | `features/hierarchy/guard.py` | 403 si la requête nomme (MID dans la requête ou le formulaire) un nœud ou document d'entrée en lecture seule |
| `baseline_sync` | `features/item_page/router.py` | `GET /item/{uid_or_mid}` (paramètres `tab`, `role`) |
| `features/document_versions/router.py` | `GET /versions/{document_mid}`, `/versions/{document_mid}/compare`, `/versions/{document_mid}/{tag}` ; 412 si `GIT` ou l'option `git` manque |
| `features/hierarchy/router.py` | maintient la ligne de base des liens suspects |

## Les routes

Environ 130 routes. Inventaire par groupe.

### Pages et ressources (`main_router.py`)

| Route | Rôle |
|---|---|
| `GET /` | page d'accueil, arbre du projet (`index.html`) |
| `GET /{full_path:path}` | **route fourre-tout** : `.html` vers `get_document`, sans extension 404, sinon `get_asset` |
| `GET /{full_path:path}/static_html_search_index.js` | index de recherche statique, régénéré si périmé |
| `GET /UID/{uid_or_mid}` | redirection stable vers le nœud dans son document (les liens stables en dépendent) |
| `GET /item/{uid_or_mid}` | page d'un item (`features/item_page`) |
| `GET /versions/{document_mid}`, `.../compare`, `.../{tag}` | versions d'un document (`features/document_versions`) |
| `GET /fragments/document/{mid}/chunk` | tranche d'un grand document (chargement paresseux) |
| `GET /search`, `/autocomplete/uid`, `/autocomplete/field` | recherche et complétion. `/search` prend `q`, `kind`, `status`, `links` ; un `q` qui est exactement un UID redirige (302) vers `/item/<uid>` |
| `GET /export_html2pdf/{mid}`, `/reqif/export_document/{mid}`, `/reqif/export_tree` | exports |
| `GET /__nestor` | écran Nestor |
| `WEBSOCKET /ws/{client_id}` | diffuse `reload` ou `error:<message>` aux navigateurs |

`get_document(url)` : si la page HTML existe et est plus récente que
`traceability_index.index_last_updated`, la sert (304 si l'ETag correspond,
`Cache-Control: no-cache`). Sinon prend
`acquire_subset(write_ids={document:<chemin>})`, puis `generate_document()`
choisit le générateur selon le chemin : `_source_files/...` (vue d'un fichier
source), `index.html`, `traceability_matrix.html`, `source_coverage.html`, un
écran de `Feature`, ou un document avec suffixe `-TABLE`, `-TRACE`,
`-DEEP-TRACE`, `-PDF` (`DocumentType`). Une fonction désactivée répond 412
(précondition non remplie).

### Édition d'un nœud (`/actions/document/...`)

`GET new_requirement`, `clone_requirement`, `edit_requirement`,
`cancel_new_requirement`, `cancel_edit_requirement`, `show_move_node` ;
`POST create_requirement`, `update_requirement`, `move_node`,
`move_node_across_documents`, `upload_asset` ; `DELETE delete_requirement`,
`delete_document` ; `GET /reset_uid`, `/actions/show_full_node`.

### Édition en table (`/actions/table/...`)

`POST add_node`, `update_node_field`, `update_node_field_multiline`,
`update_node_comments`, `update_node_relations`, `update_document_config_field`,
`update_document_custom_meta` ; `DELETE delete_node` ; plusieurs `GET get_*_inline`
qui renvoient le fragment d'édition d'une cellule.

### Document, configuration, grammaire

`GET edit_config`, `new_metadata`, `new_comment`, `new_relation`,
`edit_included_document`, `edit_grammar`, `add_grammar_element`,
`edit_grammar_element`, `add_grammar_field`, `add_grammar_relation`,
`cancel_edit_config`, `cancel_edit_included_document` ; `POST save_config`,
`save_included_document`, `save_grammar`, `save_grammar_element`.

### Index du projet (`/actions/project_index/...`)

`new_document`, `create_document`, `edit_project_title_form`,
`save_project_title`, `import_reqif_document_form`, `import_document_reqif`,
plus les routes des dossiers (`features/folders`) et Word (`docx_router.py`).

### Autres routeurs

| Fichier | Routes |
|---|---|
| `other_router.py` | `GET /diff`, `/diff_result` (diff et changelog Git) |
| `docx_router.py` | `/actions/project_index/import_docx_form`, `export_docx_form`, `import_docx_preview`, `import_docx`, `export_docx_preview`, `POST /docx/export` |
| `features/comments/router.py` | `/actions/comments/add\|edit\|delete\|resolve\|reopen`, `GET /comments` |
| `features/folders/router.py` | création, renommage, déplacement, suppression de dossiers et de documents |
| `features/git_config/router.py` | `GET /git`, `/actions/git/overview`, `commit_pending`, `tag`, `version_document`, `push`, `create_repository`, `submodule_add`, `submodule_update` |
| `features/git_sync/router.py` | `/actions/git/sync_dialog`, `sync`, `sync_conflicts`, `sync/resolve`, `sync/abort` |
| `features/hierarchy/router.py` | `GET /suspect_links`, `/hierarchy` ; `POST /actions/suspect/clear`, `baseline`, `/actions/hierarchy/resolve_references` |
| `features/llm/router.py` | `GET /llm/draft`, `/llm/drafts` ; `POST /actions/llm/draft`, `create` |
| `features/llm/assist/router.py` | `POST /actions/llm/assist`, `apply` ; `GET /llm/assist/commands`, `/llm/assist/mentions`, `/actions/llm/jobs/{id}` ; `DELETE /actions/llm/jobs/{id}` |
| `features/reviewers/router.py` | `GET /actions/reviewers/form`, `POST /actions/reviewers/set` |
| `features/project_index/sidebar.py` | `GET /fragments/project_tree` |
| `features/roles/router.py` | `GET /whoami`, `/audit` |
| `features/projects/members_router.py` | `GET /members`, `POST /actions/members/set\|remove` |

## Anatomie d'une route qui modifie (exemple : `update_requirement`)

`main_router.py:938`. Les autres suivent le même schéma.

```
1. lit le formulaire (FormData) et retrouve le nœud par MID
2. refuse si traceability_index.can_edit_node(node) est faux (403)
3. RequirementFormObject.create_from_request(...) puis .validate(index, ..., existing_revision)
   -> erreurs : rend le flux Turbo stream du formulaire, statut 422
4. CreateOrUpdateNodeCommand(...).perform()      core/transforms/update_requirement.py
   modifie les objets SDoc et l'index
5. write_document_to_file(document)              réécrit le .sdoc (ou .md), commit Git éventuel
6. revisions[requirement_mid] += 1
7. html_generator.export_single_document_with_performance(...)
   ré-exporte la page HTML du document (plus récente que l'index)
8. DocumentScreenViewObject.render_updated_nodes_and_toc(...)
   réponse : flux Turbo (Content-Type text/vnd.turbo-stream.html)
```

Concurrence : `revisions[mid]` détecte qu'un autre onglet a enregistré depuis
l'ouverture du formulaire.

Les réponses sont des **Turbo streams** (`<turbo-stream action="replace|update|append"
target="...">`). `server/helpers/turbo.py` en fournit le gabarit et
`export/html/templates/actions/**/stream_*.jinja.html` les contenus. Voir
[06](06-frontend-et-export-html.md).

## Observateur de fichiers (`--watch`)

`server/document_watcher.py`, `DocumentWatcher` (watchdog) : surveille les
chemins d'entrée, filtre sur les extensions que lisent les `Format`
(`get_document_extensions`), ignore le dossier de sortie et les dossiers cachés,
temporise 0,3 s, compare un hash SHA-256 du contenu pour ne pas réagir à une
simple modification de date. `inhibit_next_change(path)` est appelé **avant**
chaque écriture du serveur lui-même. À un changement réel,
`notify_clients_after_file_change` reconstruit l'index et diffuse `reload` ou
`error:<message>` par le WebSocket.

## Erreurs

`ServerErrorViewObject` (`export/html/generators/view_objects`) rend la page
d'erreur (404, 412, 500) avec le gabarit commun. Les handlers 404 et 500 sont
enregistrés dans `create_main_router`. `server/error_object.py` : `ErrorObject`
(dictionnaire champ vers liste de messages) sert de base aux objets de
formulaire.

## Où ajouter une route

1. Écrire la route dans le routeur de la feature (`create_<x>_routers(context=...)`
   renvoie `(read_router, write_router)`), ou dans `main_router.py` si elle
   concerne le coeur.
2. Inclure ce routeur dans `create_main_router` (bloc `include_router`, vers la fin du fichier).
3. **Ajouter `(méthode, chemin)` dans `ROUTE_ROLES`** (`features/roles/route_roles.py`)
   avec le rôle minimal. Sinon le serveur ne démarre pas.
4. Si la route modifie le projet : passer par `write_router`, appeler
   `write_document_to_file`, incrémenter `revisions`, ré-exporter la page.
5. Un test end2end (`tests/end2end/screens/...`) ou unitaire serveur
   (`tests/unit_server`).
