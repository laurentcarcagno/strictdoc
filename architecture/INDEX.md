# Index de l'architecture

Point d'entrée. Lire ce fichier, puis **un seul** document selon la question. Les
documents renvoient les uns aux autres par numéro. Les chemins sont relatifs à la
racine du dépôt.

Produit à partir du code au commit `5198d0f1a` (alors la branche
`feature/isis-release`, supprimée depuis ; StrictDoc 0.30.2 plus le fork ISIS),
puis mis à jour pour la branche `feature/refactor-ui` jusqu'au commit `0c4566ad6` (page d'un item, versions d'un
document, barre latérale en groupes, petit écran). Si le code a beaucoup changé
depuis, vérifier les chemins cités avant de s'y fier.

## Les documents

| N° | Fichier | Thème | À lire quand |
|---|---|---|---|
| 00 | [00-vue-ensemble.md](00-vue-ensemble.md) | produit, pipeline, carte du dépôt, pile, règles | première fois, ou pour situer un fichier |
| 01 | [01-cli-et-commandes.md](01-cli-et-commandes.md) | CLI, commandes, export, convert | ajouter ou modifier une commande ou une option |
| 02 | [02-modele-sdoc-et-grammaire.md](02-modele-sdoc-et-grammaire.md) | format `.sdoc`, grammaire textX, modèle objet, lecture, écriture | toucher au modèle de données ou à la syntaxe |
| 03 | [03-formats-et-backends.md](03-formats-et-backends.md) | classe `Format`, Markdown, ReqIF, Excel, DOCX, JSON, SPDX, code source | un format d'import ou d'export, les marqueurs `@relation` |
| 04 | [04-core-index-et-tracabilite.md](04-core-index-et-tracabilite.md) | `ProjectConfig`, découverte des fichiers, index, graphe, requêtes, transformations | configuration, traçabilité, droits d'édition |
| 05 | [05-serveur-web.md](05-serveur-web.md) | FastAPI, middlewares, `ProjectContext`, verrous, routes | une route, un problème de concurrence, un écran serveur |
| 06 | [06-frontend-et-export-html.md](06-frontend-et-export-html.md) | Jinja, objets vue, objets de formulaire, Turbo, JS/CSS, Milkdown, i18n | tout ce qui s'affiche |
| 07 | [07-features-amont.md](07-features-amont.md) | recherche, statistiques, tree map, diff, PDF, couverture source, lanceur | une fonction d'origine, câblage d'une feature |
| 08 | [08-features-fork-isis.md](08-features-fork-isis.md) | rôles, commentaires, relecteurs, hiérarchie, dossiers, multi-projet, Git, SVG, vue en pages | une fonction ajoutée par le fork |
| 09 | [09-assistant-llm-et-kb.md](09-assistant-llm-et-kb.md) | assistant LLM, politique, audit, base de connaissances | l'assistant, un fournisseur de modèle, la base |
| 10 | [10-donnees-et-persistance.md](10-donnees-et-persistance.md) | fichiers, caches, journaux, navigateur, services externes | « où est stocké X ? », cache, invalidation |
| 11 | [11-tests-qualite-build.md](11-tests-qualite-build.md) | Invoke, niveaux de test, lint, CI, distribution | lancer ou écrire un test, publier |
| 12 | [12-conventions-et-recettes.md](12-conventions-et-recettes.md) | règles AGENTS et SDG, Git, pièges, recettes pas à pas | avant de coder ; « comment ajouter... » |

## Je cherche...

| Question | Document, section | Fichiers de départ |
|---|---|---|
| Ce qui se passe quand je lance `strictdoc export` | 01 « export » | `strictdoc/cli/main.py`, `commands/export.py`, `features/export/export_action.py` |
| Comment un `.sdoc` devient des objets | 02 « Lecture » | `backend/sdoc/reader.py`, `processor.py`, `grammar/grammar.py` |
| La syntaxe d'un `.sdoc` | 02 « Le format » | `backend/sdoc/grammar/grammar.py` |
| Les champs d'un nœud, les relations | 02 « Modèle objet » | `backend/sdoc/models/node.py`, `reference.py`, `grammar_element.py` |
| Écrire un nouveau format | 03 « L'abstraction Format » | `core/format.py`, `core/project_config.py` (`default_formats`) |
| Lien code source vers exigence (`@relation`) | 03 « sdoc_source_code » ; 04 « FileTraceabilityIndex » | `backend/sdoc_source_code/`, `core/file_traceability_index.py` |
| Import ou export Word | 03 « docx » ; 08 « Word » | `backend/docx/`, `server/routers/docx_router.py` |
| Lire la configuration, ajouter une option | 04 « Configuration » ; 12 « Ajouter un champ de configuration » | `core/project_config.py`, `strictdoc_config.py` |
| Retrouver les parents d'un nœud, les enfants | 04 « TraceabilityIndex » | `core/traceability_index.py`, `core/graph_database.py` |
| Qui a le droit de modifier quoi | 04 `can_edit_*` ; 08 « Rôles » ; 05 « Verrous » | `features/roles/route_roles.py`, `core/traceability_index.py` |
| Ajouter une route | 05 « Où ajouter une route » | `server/routers/main_router.py`, `features/roles/route_roles.py` |
| Pourquoi mon serveur ne démarre pas | 05 `check_routes_classified` ; 12 « Pièges » | `features/roles/route_roles.py` |
| Interblocage ou page périmée | 05 « Verrous » | `server/helpers/hierarchical_rw_lock_manager.py`, `main_router.py` (`get_document`) |
| Ce que renvoie un POST d'édition | 05 « Anatomie » ; 06 « Turbo » | `main_router.py:938`, `export/html/templates/actions/` |
| Ajouter un écran de feature avec barre latérale et en-tête | 06 « Écrans de feature dans le cadre du projet » ; 12 « Ajouter un écran de feature dans le cadre du projet » | `export/html/generators/view_objects/app_screen_view_object.py`, `features/item_page/router.py` |
| Entrées et groupes de la barre latérale | 06 « Barre latérale en groupes » | `export/html/templates/_shared/nav.jinja.html` |
| Page d'un item (liens, commentaires, historique) | 08 « Page d'un item » | `features/item_page/` |
| Versions d'un document (étiquettes Git, comparaison) | 08 « Versions d'un document » | `features/document_versions/`, `features/git_config/git_service.py` |
| Recherche par UID exact, facettes | 07 « search » | `features/search/facets.py` |
| Action grisée selon le rôle, page 403 | 08 « Rôles et identité » | `features/roles/assets/roles/role_gating.js`, `enforcement.py` |
| Affichage sur téléphone | 06 « Petit écran » | `export/html/_static/responsive.css`, `mobile_nav.js` |
| Tests dans Docker (Windows) | 11 « Invoke » | `developer/docker_tests/`, `tasks.py` |
| Modifier un écran ou un formulaire | 06 « Où modifier quoi » | `export/html/templates/`, `export/html/form_objects/`, `generators/view_objects/` |
| Un script JS ou un style | 06 « Turbo et JavaScript » | `export/html/_static/`, `features/<x>/assets/` |
| L'éditeur Markdown | 06 « Milkdown » | `developer/milkdown/`, `features/milkdown/assets/milkdown/` |
| Traduire un texte | 06 « Internationalisation » | `features/i18n/`, `developer/i18n/update_catalogs.py` |
| Écran de recherche | 07 « search » | `features/search/`, `_static/static_html_search.js` |
| PDF | 07 « html2pdf » | `features/html2pdf/` |
| Statistiques, tree map | 07 « project_statistics et tree_map » | `features/project_statistics/`, `features/tree_map/`, `core/feature.py` |
| Comparer deux versions (diff) | 07 « diff_and_changelog » | `features/diff_and_changelog/` |
| Commentaires de relecture | 08 « Commentaires » | `features/comments/`, `features/reviewers/` |
| Hiérarchie, documents d'entrée, liens suspects | 08 « hiérarchie » | `features/hierarchy/` |
| Plusieurs projets, portail, membres | 08 « Plusieurs projets » | `features/projects/`, `server/app.py` (`strictdoc_projects_app`) |
| Commit à l'enregistrement, tags de version | 08 « Git » | `features/git_config/` |
| Synchronisation et conflits | 08 « Synchronisation » | `features/git_sync/` |
| SVG et sécurité des images | 08 « SVG » | `features/svg/` |
| Politique d'usage d'un modèle, audit | 09 « Garde-fous » | `features/llm/policy.py`, `audit.py`, `context.py` |
| Commandes `/rewrite`, `/req`, `/review`... | 09 « Barre de l'assistant » | `features/llm/assist/commands.py`, `service.py` |
| Citer la base de connaissances | 09 « Base de connaissances » | `features/kb/`, `features/llm/assist/agent_loop.py` |
| Où est la donnée, que supprimer pour repartir propre | 10 | `output/_cache`, `backend/sdoc/pickle_cache.py` |
| Lancer un test précis | 11 « Invoke » | `tasks.py`, `tests/` |
| Écrire un test d'intégration ou end2end | 11 « Les quatre niveaux » | `tests/integration/lit.cfg.py`, `tests/end2end/` |
| Règles de style, messages de commit | 12 | `docs/strictdoc_11_developer_guide.sdoc` |
| État du déploiement et reprise de travail | `HISTORY.md` (hors dossier) | `developer/design/` |

## Vocabulaire

| Terme | Sens | Où |
|---|---|---|
| SDoc | format texte des documents (`.sdoc`) | 02 |
| Nœud (*node*) | un élément de document : exigence, texte, section, cas de test... ; `SDocNode` | 02 |
| MID | identifiant machine stable d'un nœud ou d'un document (32 hex) | `helpers/mid.py` |
| UID | identifiant humain d'un nœud (`REQ-001`) | 02 |
| Grammaire | schéma des types de nœuds et de leurs champs, dans le document ou un `.sgra` | 02 |
| Relation | `Parent` ou `Child` entre deux nœuds, avec un rôle | 02, 04 |
| `Format` | lecture, écriture, import, export d'un type de fichier | 03 |
| `Feature` | capacité qui se branche sur l'export et le serveur | 04, 07 |
| `ProjectFeature` | interrupteur de la configuration (`project_features`) | 04 |
| `DocumentTree` | documents découverts et leurs fichiers | 04 |
| `TraceabilityIndex` | tout le modèle en mémoire avec son graphe | 04 |
| `GraphDatabase` | liens typés entre nœuds (parents, enfants, UID, MID, liens en ligne) | 04 |
| `FileTraceabilityIndex` | liens entre exigences et fichiers source | 04 |
| `@relation(...)` | marqueur dans un commentaire de code | 03 |
| Source node | nœud SDoc écrit dans un commentaire de code | 03, 04 |
| `ProjectContext` | état serveur d'un projet (index, gabarits, révisions, Git) | 05 |
| `Principal`, rôle | identité et droit de l'utilisateur de la requête | 08 |
| `render_app_screen` | rend un écran de feature dans le cadre du projet (barre latérale, en-tête) | 06 |
| Item | un nœud normatif vu par sa page `/item/<uid>` | 08 |
| Objet vue (*view object*) | objet passé à un template, avec les méthodes de rendu | 06 |
| Objet de formulaire | lit, valide et rend un formulaire | 06 |
| Turbo stream | réponse HTML qui dit quel élément remplacer | 05, 06 |
| Document d'entrée (*input*) | document du client, en lecture seule | 08 |
| Lien suspect | enfant dont le parent a changé depuis la revue | 08 |
| Base de connaissances (KB) | index PostgreSQL de documents de mission, via MCP | 09 |
| *Golden set* | cas d'évaluation de l'assistant | 09 |

## Fichiers qui portent le plus de poids

À ouvrir en premier pour comprendre, par ordre d'importance.

| Fichier | Lignes | Rôle |
|---|---|---|
| `strictdoc/core/traceability_index.py` | 1 640 | modèle en mémoire, droits, mutations |
| `strictdoc/core/traceability_index_builder.py` | 990 | construction du graphe |
| `strictdoc/core/project_config.py` | 1 760 | toute la configuration |
| `strictdoc/backend/sdoc/models/node.py` | 900 | un nœud |
| `strictdoc/backend/sdoc/grammar/grammar.py` | 240 | syntaxe `.sdoc` |
| `strictdoc/server/routers/main_router.py` | 5 700 | routes du serveur |
| `strictdoc/server/project_context.py` | 190 | état d'un projet |
| `strictdoc/export/html/html_generator.py` | 870 | export HTML |
| `strictdoc/export/html/generators/view_objects/document_screen_view_object.py` | 1 200 | rendu de l'écran document |
| `strictdoc/export/html/form_objects/requirement_form_object.py` | 1 170 | formulaire d'un nœud |
| `strictdoc/core/transforms/update_requirement.py` | 590 | création et mise à jour d'un nœud |
| `strictdoc/core/file_traceability_index.py` | 1 430 | code source vers exigences |
| `strictdoc/features/roles/route_roles.py` | 250 | rôle de chaque route |
| `strictdoc/core/format.py`, `core/feature.py` | 200, 110 | abstractions d'extension |
| `strictdoc/core/environment.py` | 170 | dossiers de templates et de ressources |

## Invariants à garder en tête

1. Le fichier texte du projet est la seule donnée durable ; tout le reste se
   recalcule ([10](10-donnees-et-persistance.md)).
2. Un seul `TraceabilityIndex` par projet vivant, réaffecté à chaque
   reconstruction ; l'écrire ou le lire se fait sous verrou
   ([05](05-serveur-web.md)).
3. Toute écriture du serveur passe par `ProjectContext.write_document_to_file`.
4. Toute route a un rôle dans `ROUTE_ROLES`, sinon le serveur ne démarre pas.
5. L'export statique et le serveur partagent les mêmes templates.
6. Le texte de document donné à un modèle est une donnée, jamais une consigne
   ([09](09-assistant-llm-et-kb.md)).
7. Aucun secret dans la configuration : on nomme la variable d'environnement.
8. Une fonction du fork reste dans son dossier `features/<nom>/` ; un
   composant partagé ne change pas sans accord ([12](12-conventions-et-recettes.md)).

## Commandes utiles

```
invoke --list                                  toutes les tâches
invoke server --input-path <dossier>           serveur depuis les sources
invoke check                                   lint + unitaires + intégration
invoke test-unit --focus <mot>                 un sous-ensemble de tests unitaires
invoke test-integration --focus <mot>          idem pour LIT
invoke test-end2end --headless --focus <mot>   idem pour Selenium (toujours --headless)
invoke docs                                    exporte les docs de StrictDoc
python developer/skills/install_skills.py      régénère les pointeurs de compétences
cd developer/milkdown && npm ci && npm run build   reconstruit l'éditeur Markdown
```

## Entretien de ce dossier

Mettre à jour le document concerné quand on change une structure décrite ici :
un chemin, un nom de classe, une route, un paramètre de configuration, un
format. Le script de contrôle des chemins cités est dans la section ci-dessous.

Vérifier que chaque chemin cité existe encore :

```
python3 - <<'EOF'
import re, pathlib
for doc_ in sorted(pathlib.Path("architecture").glob("*.md")):
    for path_ in set(re.findall(r"`((?:strictdoc|tests|developer|docs|spec|tools)/[\w./{}*<>-]+)`", doc_.read_text(encoding="utf8"))):
        if "<" in path_ or "*" in path_ or "{" in path_:
            continue
        if not pathlib.Path(path_.split(":")[0]).exists():
            print(doc_.name, path_)
EOF
```
