# 08 - Features ajoutées par le fork ISIS

Le fork (StrictDoc 0.30.2, branche `develop`) est déployé pour un
pilote de gestion d'exigences. Chaque feature a un plan dans
`developer/design/plan_*.md` ; le plan d'ensemble est `master_plan.md`. Ce
document décrit le code livré. L'assistant LLM et la base de connaissances sont
traités à part dans [09](09-assistant-llm-et-kb.md).

Ordre de dépendance voulu par le plan : rôles, commentaires, SVG, hiérarchie,
multi-projet, LLM, Git. `ProjectContext` ([05](05-serveur-web.md)) a été
extrait en premier pour que tout soit par projet.

## Rôles et identité (`features/roles`, plan 1)

Quatre rôles, chacun inclut les précédents : `reader` < `reviewer` < `author` <
`administrator` (`roles.py` : `role_allows`, `resolve_role`, `validate_roles`).

| Fichier | Rôle |
|---|---|
| `principal.py` | `Principal(user, subject, email, groups)` lu des en-têtes d'oauth2-proxy (`X-Forwarded-User` = UUID Keycloak, `X-Forwarded-Preferred-Username`, `X-Forwarded-Email`, `X-Forwarded-Groups` avec préfixe `role:` pour les rôles de realm). `CURRENT_ROLE` : variable de contexte pour le code sans requête |
| `middleware.py` | `PrincipalMiddleware`. `auth_mode="none"` (défaut) : anonyme et administrateur ; `"proxy"` : n'accepte que les requêtes venant de `trusted_proxies` avec les en-têtes, sinon 401. Les en-têtes `X-Auth-Request-*` ne sont jamais lus |
| `enforcement.py` | `RoleMiddleware` : cherche la route (`match_route_key`) et refuse (403) si le rôle est insuffisant. Un navigateur (en-tête `Accept` HTML) reçoit la page `templates/features/roles/refused.jinja.html` dans le cadre du projet, avec la raison et un lien de retour ; si le rendu échoue, une page nue |
| `route_roles.py` | table `ROUTE_ROLES` : `(méthode, chemin)` vers rôle minimal ; `check_routes_classified` ; **aucun défaut, une route sans entrée empêche le démarrage** |
| `audit.py` | `AuditLog`, `AuditMiddleware` : une ligne JSON par requête POST/PUT/PATCH/DELETE (et `GET /__nestor`) : utilisateur, rôle, route, MID, statut, y compris les refus. Fichier tournant, dans `audit_dir` ou `output_dir` |
| `router.py` | `GET /whoami`, `GET /audit` (l'écran d'audit est rendu dans le cadre du projet, `templates/features/roles/audit.jinja.html`) |
| `assets/roles/role_gating.{css,js}` | renseigne `data-role` sur `<html>` d'après `/whoami`. Une action que le rôle ne permet pas **reste affichée, grisée** : `aria-disabled`, un `title` qui nomme le rôle requis (« Needs the author role ») et un clic ignoré. Les sélecteurs `data-testid` des actions concernées sont listés dans `role_gating.js` (tableau `GATED`, rôles `author` et `administrator`) : **une nouvelle action réservée y est ajoutée**. Le serveur refuse de toute façon |

Règles de la table : lecture, page d'un item, versions d'un document, export, recherche, assistant (`/actions/llm/assist`,
vérifié ensuite commande par commande) et commentaires sont au niveau `reader`
(les commentaires vérifient le relecteur du document dans leur propre routeur) ;
création, édition, déplacement, suppression de nœuds, imports Word, brouillons LLM
et résolution de commentaires sont `author` ; configuration et grammaire d'un
document, titre du projet, suppression de documents, import ReqIF, Git
(tag, push, synchronisation), membres, audit et Nestor sont `administrator`.

Configuration :

```python
ProjectConfig(auth_mode="proxy", trusted_proxies=["10.89.0.0/24"],
              roles={"administrator": ["strictdoc-admins"], "author": ["strictdoc-authors"],
                     "reviewer": ["strictdoc-reviewers"], "reader": ["strictdoc-readers"]})
```

## Commentaires de relecture (`features/comments`, plan 2)

Pas de changement de grammaire : un commentaire est un champ `COMMENT` dont la
première ligne est un en-tête qui ne s'affiche pas.

- `<!-- sdoc-comment id=c7f3a9 author=anna date=... status=open -->` (l'ancien en-tête RST n'est plus lu)

Un `COMMENT` sans en-tête est un commentaire « ancien » (sans auteur ni date,
ouvert). Clés d'en-tête (`model.py`) : `id`, `author`, `date`, `status`
(`open`, `resolved`), `resolved_by`, `resolved_on`, `source`, puis `model`,
`provider`, `prompt`, `accepted_by` (nœud rédigé par un modèle), `anchor`,
`anchor_n` (mots du texte auxquels le commentaire se rapporte).

`service.py` : `comments_of`, `find_comment`, `save_comments` (reconstruit le
formulaire du nœud et passe par la même commande que l'édition, donc validations
et compteur de révision). `router.py` : ajouter, modifier, supprimer, résoudre,
rouvrir, écran `/comments`. Le panneau (`comments.js`) s'affiche dans la marge du
document. Export Word : `backend/docx/export/docx_comments.py` ; lecture Word
vers SDoc : l'import crée des `COMMENT` avec `source=word`.

## Relecteurs (`features/reviewers`)

Les relecteurs d'un document sont dans ses métadonnées :

```
[DOCUMENT]
METADATA:
  REVIEWERS: ann, bob
  CREATED_BY: laurent
```

Peut commenter : un `author` ou `administrator`, un utilisateur de rôle
`reviewer` sur le projet, ou un relecteur nommé du document
(`reviewers.py`). Routes : `/actions/reviewers/form` et `set`.

## Documents d'entrée, hiérarchie, liens suspects (`features/hierarchy`, plan 4)

| Notion | Où |
|---|---|
| Niveaux (`Level(name, label, parents)`) et type de document | `levels.py`. Le projet déclare `document_hierarchy=[Level("customer"), Level("system", parents=["customer"]), ...]`. Un document déclare son type par la métadonnée `KIND: <niveau>` ; `KIND: input` est un document d'entrée (spécification du client), en lecture seule sauf `input_documents_editable` |
| Politique de relations | `policy.py` : `relation_policy` = `off`, `warn`, `enforce` ; `policy_message(...)` vérifie qu'un `Parent` ou `Child` pointe vers un niveau autorisé. Appelée par `RequirementFormObject.validate` |
| Protection en écriture | `guard.py` : `create_input_guard` (403 sur toute route d'écriture qui nomme un document d'entrée) ; `TraceabilityIndex.input_allows_edit` |
| Liens suspects | `suspect.py` : un enfant répond à un parent tel qu'il était à la revue du lien. L'état est `trace_baseline.json` à la racine du projet (SHA-1 du contenu du parent par lien ; champs par défaut `TITLE` et `STATEMENT`, option `suspect_fields`). Un lien est suspect si le parent a changé depuis. `SuspectLink`, `content_hash`. Option `suspect_links=True` |
| Écrans | `router.py` : `/suspect_links`, `/hierarchy` ; actions `suspect/clear`, `suspect/baseline`, `hierarchy/resolve_references` ; `stats.py` : `compute_hierarchy_stats` (documents et nœuds par niveau, couverture, orphelins) |
| Références à des documents applicables | `references.py` parse `[DA1] §5.14.1 ; [DA2] REQ-106005, REQ-0280` ; `source.py` : `IndexReferenceSource`, `build_reference_resolver` (option `applicable_documents={"DA1": "inputs/pus-standard"}`) ; `resolve_action.py` : crée les relations `Parent` manquantes à partir des colonnes Word ; `applicable_table.py` : tableau d'ouverture d'un export Word neuf |

## Dossiers (`features/folders`)

Un dossier vide n'apparaît pas dans l'arbre du projet StrictDoc. Le fork en crée
par l'interface : un fichier marqueur `.sdoc-folder` (jamais lu comme document)
rend le dossier visible. `folders.py` : noms nettoyés (`clean_folder_path`,
profondeur maximale 8, noms réservés `_assets`, `output`, `word`), création,
renommage, déplacement, suppression. `router.py` : routes
`/actions/project_index/*`.

## Plusieurs projets dans un serveur (`features/projects`, plan 5)

Un processus, plusieurs applications : chaque projet garde sa propre
`create_app(...)`, donc ses URL absolues restent valides.

```
strictdoc server --projects registre.py --root-host strictdoc.karka.lan [--data-root /data]
  server.py : run_strictdoc_projects_server  -> uvicorn strictdoc_projects_app
    registry.py   load_registry(registre.py) -> [ProjectSpec(slug, title, path, config, roles, archived)]
    app.py        create_projects_app : une application par projet + portail + dispatcher
    dispatcher.py ProjectDispatcher (ASGI) :
        /_projects...      -> portail
        autre chemin       -> application du projet nommé par le cookie sdoc_project
                              (sans projet connu : redirection vers le portail)
        autre hôte         -> 404
    portal.py     liste des projets, rôle de l'utilisateur dans chacun, création (administrateur de plateforme)
    manager.py    projets créés à chaud (dossier + strictdoc.toml, application ajoutée sans redémarrage)
    store.py      ProjectStore : projects.json (projets créés, membres et rôles), écriture atomique
    members_router.py  page des membres d'un projet
    directory.py  KeycloakDirectory : annuaire des comptes pour choisir un membre
```

Rôle effectif : le plus haut entre le rôle de la liste des membres
(`projects.json`) et celui des groupes (`roles` de la spec). Les groupes
`STRICTDOC_PLATFORM_ADMINS` créent des projets et sont administrateurs partout.
Le cookie choisit seulement l'application, chaque projet revérifie le rôle à
chaque requête. Un slug suit `^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$`.

## Git : gestion de configuration (`features/git_config`, plan Git)

Option `git=GitConfig(...)` (`config.py` : `author_name`, `author_email`,
`gitlab_url`, `token_env`, `group_path`, `push_on_tag`, `ca_bundle`, `use_lfs`,
`asset_warning_bytes`). Le jeton GitLab n'est jamais écrit : `token_env` est le
**nom** de la variable d'environnement.

| Fichier | Rôle |
|---|---|
| `setup.py` | `create_committer(project_config)` (retrouve la racine du dépôt, `find_project_root`), `provision_repository`, `ensure_remote_repository`, `collect_node_assets`, `remove_node_assets` |
| `committer.py` | `GitCommitter` : appelé après chaque écriture de document (`on_document_written`) ou d'asset (`on_asset_written` : mis en attente et joint au commit suivant, avertit pour les gros fichiers) ; une erreur n'empêche jamais la sauvegarde (`last_error`) ; `flush` |
| `git_service.py` | `GitService` sur GitPython : `commit_paths`, tags, `push` (avec jeton https), sous-modules, `fetch`, `ahead_behind`, fusion (`start_merge`, `stage_text`, `commit_merge`, `abort_merge`), `describe_repositories`. Lecture de l'historique : `history_of_lines` (`git log -L` sur les lignes d'un bloc, avec le patch ; `LineRevision`), `version_tags_of` (étiquettes de version, la plus récente d'abord, avec date et sujet ; `TagInfo`), `text_at_tag` (`git show <tag>:<fichier>`, sans extraire) |
| `commit_message.py` | messages de commit conventionnels : `changed_uids` repère les UID modifiés par les numéros de ligne d'un `git diff -U0` |
| `versioning.py` | étiquettes de version d'un document : `A1`, `A2` (brouillons), `A` (majeure), `B1`, ... `Z`, `ZA`... ; `next_intermediate_tag`, `next_major_tag`, `latest_valid_tag`, `sorted_version_tags` |
| `document_version.py` | `latest_version_of_file(path)` : dernière étiquette du dépôt qui contient le fichier, ou `None` ; lue par l'en-tête des écrans de document (`SDOC-SRS-1210`) |
| `gitlab_service.py` | création de dépôts sur GitLab |
| `asset_names.py` | dossiers `_assets` qui appartiennent à un nœud et à ses enfants |
| `router.py` | page `/git`, aperçu, commit en attente, tag, version de document, push, création de dépôt, sous-modules |

## Synchronisation Git avec résolution des conflits (`features/git_sync`)

`SyncService.sync` : `fetch`, avance rapide si possible, sinon fusion. L'état
d'une fusion en cours est celui de Git (`MERGE_HEAD`, fichiers non fusionnés),
donc un redémarrage du serveur ne perd rien. Les `.sdoc` que Git ne fusionne
pas par lignes le sont **nœud par nœud** :

| Fichier | Rôle |
|---|---|
| `blocks.py` | un `.sdoc` comme liste de blocs (un par nœud), identifiés par MID, sinon UID, sinon hash du texte |
| `merge3.py` | fusion à trois voies (`merge3(base, local, server)`) : régions `same`, `local`, `server`, `conflict` |
| `fragments.py` | prépare l'affichage des conflits (chaque région comme des nœuds de chaque côté) |
| `sync_service.py` | `SyncService`, `SyncResult`, `ConflictFile` |
| `guard.py` | `create_merge_guard` : 423 sur les routes d'écriture tant qu'une fusion attend |
| `router.py`, templates, `assets` | boîte de synchronisation et vue des conflits |

## SVG (`features/svg`, plan 3)

SVG est un format actif (script, références distantes). `sanitizer.py` :
liste blanche d'éléments et d'attributs, analyse sans DTD, supprime toute
référence qui sort du fichier ; limites : 10 Mo, 50 000 éléments, profondeur 64 ;
un fichier qui ne peut être assaini est rejeté (`SvgRejected`). `headers.py` :
`SvgHeadersMiddleware` ajoute `Content-Security-Policy: default-src 'none';
style-src 'unsafe-inline'; sandbox` et `nosniff` à tout SVG servi. `rasterizer.py` :
SVG vers PNG avec resvg-py, pour le repli de l'image dans Word. L'envoi
(`upload_asset`) assainit avant d'écrire.

## Navigation, cadre des écrans et page d'un item (branche `feature/refactor-ui`, SRS-208 à 216)

Lot de travaux d'interface (commits de `e45fcba42` à `0c4566ad6`). Les exigences
sont dans la section « Navigation » de `docs/strictdoc_21_l2_high_level_requirements.sdoc`.

| Exigence | Sujet | Où |
|---|---|---|
| `SDOC-SRS-1208` | barre latérale en groupes (Analysis, Review, Versions, Administration) | `_shared/nav.jinja.html`, [06](06-frontend-et-export-html.md) |
| `SDOC-SRS-1209` | emplacement d'un document : projet puis dossiers, dans l'en-tête | `components/header/document_context.jinja`, `DocumentScreenViewObject.get_document_folders` |
| `SDOC-SRS-1210` | version d'un document : dernière étiquette Git | `features/git_config/document_version.py` |
| `SDOC-SRS-1211` | écrans du projet dans le cadre (barre latérale et en-tête) | `AppScreenViewObject`, `render_app_screen`, `_shared/app_screen.jinja.html` |
| `SDOC-SRS-1212` | actions interdites au rôle : grisées avec la raison, page 403 dans le cadre | `features/roles` |
| `SDOC-SRS-1213` | page d'un item | `features/item_page` |
| `SDOC-SRS-1214` | recherche simple : UID exact et facettes | `features/search/facets.py` |
| `SDOC-SRS-1215` | versions d'un document | `features/document_versions` |
| `SDOC-SRS-1216` | mise en page sur petit écran | `responsive.css`, `mobile_nav.js` |

Écrans qui passent maintenant par le cadre : liens suspects (l'ancienne « baseline » devient
« reviewed state »), hiérarchie, gestion de configuration (le lien « Synchronize »
ouvre la boîte de synchronisation au lieu de `/git/sync`, qui n'existe pas),
commentaires, audit, page 403, page d'un item, versions.

### Page d'un item (`features/item_page`)

`GET /item/{uid_or_mid}` (`router.py`, `create_item_page_router(context=)`, rôle
`reader`). Un `uid_or_mid` qui n'est pas un nœud normatif redirige vers le
document. Paramètres : `tab` (`content`, `links`, `comments`, `history`), `role`
(filtre des liens). `/UID/{uid_or_mid}` reste une redirection vers le nœud dans
son document, car les liens stables en dépendent ; les listes de la hiérarchie,
des liens suspects, des commentaires et des brouillons LLM pointent vers la page.

| Onglet | Source |
|---|---|
| contenu | `content_of(node)` : énoncé, justification et autres champs, rendus en HTML par le `MarkupRenderer` du document |
| liens | `service.relation_groups(index, node)` : parents et enfants groupés par rôle d'affichage (`RelationGroup`) |
| commentaires | `comments_of(node)` ; désactivé avec la raison si `COMMENTS` est inactif ou si le type de nœud n'a pas de champ `COMMENT` |
| historique | `service.block_lines_of_uid(path, uid)` trouve les lignes du bloc dans le fichier, puis `GitService.history_of_lines` ; désactivé avec la raison sans configuration Git ou sans UID dans le fichier |

Un onglet que le projet ne peut pas remplir est désactivé et dit pourquoi.

### Versions d'un document (`features/document_versions`)

Avec `GIT` et l'option `git`, dans un dépôt Git (sinon 412 par la dépendance
`require_feature`). Routes de lecture : `GET /versions/{document_mid}` (étiquettes
de version, la plus récente d'abord), `/versions/{document_mid}/{tag}` (les items
tels qu'ils étaient, en lecture seule), `/versions/{document_mid}/compare` (deux
étiquettes). Le texte vient de `git show` et est analysé en mémoire par
`SDReader.read` : rien n'est extrait. `service.py` : `read_snapshots(text)` donne
des `ItemSnapshot` (clé = UID, sinon MID ; titre ; champs), un item sans l'un ni l'autre n'est pas suivi ; `compare_snapshots` donne un
`VersionComparison` : ajoutés, supprimés, modifiés (`ItemChange`,
`FieldChange`). Seuls les documents `.sdoc` sont lus à une version ; une étiquette
qui ne suit pas le format (`parse_version_tag`) donne 404.

### Petit écran

Voir [06](06-frontend-et-export-html.md#petit-écran).

## Vue en pages (`features/page_view`)

Bascule « Normal », « 1 page », « 2 pages » sur l'écran document. Pure
présentation en JS (`page_view.js`) : les éléments restent dans le DOM, chacun est
déplacé par `transform` sur une feuille A4 (210 par 297 mm, marge 15 mm). Un
nœud est découpé en parties, un paragraphe se coupe entre deux lignes (deux
lignes au moins par feuille). Le choix est mémorisé dans `localStorage`. Le
nombre de pages peut différer du PDF (taille de texte et marges différentes).

## Internationalisation (`features/i18n`)

Voir [06](06-frontend-et-export-html.md#internationalisation).

## Word dans l'interface (`backend/docx`, `server/routers/docx_router.py`)

Fonction `DOCX` : modales d'import (avec aperçu du rapport, sans écriture) et
d'export (neuf à partir d'un modèle, ou mise à jour d'un Word existant en
modifications suivies). Le profil Word est `docx_profile` de la configuration.
Détails dans [03](03-formats-et-backends.md).

## Ce que le fork modifie dans le coeur amont

Point de départ du fork : le commit `cc8be7913` du 2026-10-09 (fusion de la
PR amont n°3231, release 0.30.2). Sur la branche `feature/refactor-ui`, 132
commits depuis, 758 fichiers touchés, environ 72 200 lignes ajoutées et 1 800
supprimées, presque toutes dans des
dossiers nouveaux. Les fichiers de l'amont que le fork modifie :

| Fichier | Pourquoi |
|---|---|
| `core/project_config.py` | nouveaux paramètres (`auth_mode`, `roles`, `document_hierarchy`, `llm`, `git`, `docx_*`, ...) et validations |
| `core/environment.py` | dossiers de templates et de ressources des nouvelles features |
| `core/traceability_index.py`, `traceability_index_builder.py` | droits fins (`can_*`, `input_allows_edit`), relation avec les niveaux |
| `server/app.py`, `project_context.py`, `server.py`, `config.py`, `commands/server*.py` | middlewares de rôles, `ProjectContext`, mode `--projects` |
| `server/routers/main_router.py` | gardes, inclusion des routeurs des features, extension des routes existantes |
| `export/html/*` (templates, formulaires, view objects) | panneaux de commentaires, barre de l'assistant, éditeur Markdown, vue en pages, polices IBM Plex |
| `features/html2pdf`, `trace`, `deep_trace`, `traceability_matrix`, `source_file_view`, `project_index` | PDF sans marques de révision et barres de changement, barre latérale commune |

Les tâches de `developer/tasks/<date>_<sujet>/` datées avant le 2026-10-09
(format et feature, convert, API, table, TOC, etc.) sont des travaux de
l'amont, pas du fork. Les décisions du fork sont dans `developer/design/` et
`HISTORY.md`.
