# 07 - Features d'origine (amont StrictDoc)

Fichiers : `strictdoc/features/<nom>/`. Une feature est une tranche verticale
qui possède ses templates (`templates/features/<nom>/`), ses ressources
(`assets/<nom>/`) et son code Python. Les features ajoutées par le fork sont dans
[08](08-features-fork-isis.md) et [09](09-assistant-llm-et-kb.md).

Câblage d'une feature, en pratique : voir « Comment une feature se branche »
en bas de ce document.

## Tableau récapitulatif

| Dossier | Fonction (`ProjectFeature`) | Quoi | Écran ou sortie |
|---|---|---|---|
| `export` | | `ExportAction` : orchestre l'export (voir [01](01-cli-et-commandes.md)) | |
| `search` | `SEARCH` | recherche plein texte, requêtes, facettes (type, statut, liens) | `SearchScreenViewObject`, route `/search`, `static_html_search.js` |
| `trace` | `TRACEABILITY_SCREEN` | vue traçabilité d'un document | `<doc>-TRACE.html` |
| `deep_trace` | `DEEP_TRACEABILITY_SCREEN` | traçabilité profonde (jusqu'aux feuilles) | `<doc>-DEEP-TRACE.html` |
| `traceability_matrix` | `TRACEABILITY_MATRIX_SCREEN` | matrice exigences vers exigences | `traceability_matrix.html` |
| `project_statistics` | `PROJECT_STATISTICS_SCREEN` | métriques du projet | `project_statistics.html` |
| `tree_map` | `TREE_MAP_SCREEN` | carte arborescente de la couverture (« Project map » dans la barre latérale) | `tree_map.html` |
| `source_coverage` | `REQUIREMENT_TO_SOURCE_TRACEABILITY` | couverture du code par les exigences | `source_coverage.html` |
| `source_file_view` | `REQUIREMENT_TO_SOURCE_TRACEABILITY` | un fichier source avec ses marqueurs | `_source_files/<chemin>.html` |
| `diff_and_changelog` | `DIFF` | différences entre deux révisions Git ou deux dossiers (« Compare versions » dans la barre latérale) | `/diff`, `/diff_result`, `--generate-diff-*` |
| `html2pdf` | `HTML2PDF` | export PDF | `output/html2pdf/pdf/*.pdf` |
| `doxygen` | | fichier de tags Doxygen | `strictdoc.tag` |
| `project_index` | | arbre du projet, carte du projet, barre latérale | `index.html`, `/fragments/project_tree` |
| `nestor` | `NESTOR` | graphe Nestor (bundle JS) | `/__nestor` |
| `launcher` | | fenêtre Tk de lancement (`strictdoc launcher`) | |
| `mathjax`, `mermaid`, `plantuml` | `MATHJAX`, `MERMAID` | ressources JS pour formules et diagrammes | |
| `milkdown` | | bundle de l'éditeur Markdown | voir [06](06-frontend-et-export-html.md) |

## `search`

`view_object.py` : `SearchScreenViewObject`. Deux modes. Sur le serveur, la route
`/search` (`main_router.py`) évalue soit une requête du langage de
`core/query_engine` (si le texte contient des marqueurs de requête), soit un
texte simple, sur les nœuds de l'index. En export statique,
`HTMLGenerator.export_static_html_search_index` écrit
`static_html_search_index.js` (index inversé : mots vers numéros de nœuds, carte
nœuds vers titres et liens) et `static_html_search.js` l'interroge dans le
navigateur, avec IndexedDB. Chaque `SDocDocument.build_search_index()` calcule
l'index par document ; l'index est régénéré seulement si un document a changé
(`FileDependencyManager.must_generate`).

Ajouts du fork dans `search/facets.py` (`SDOC-SRS-1214`) :

- `find_item_by_exact_uid` : si le texte est exactement l'UID d'un nœud normatif
  (un seul mot), `/search` redirige (302) vers `/item/<uid>`.
- `SearchFacets(kind, status, links)` et `build_facet_query` : les trois choix de
  l'écran (`requirement` ou `section`, une valeur de `STATUS`, avec ou sans
  parent) deviennent une requête du langage de `core/query_engine`, par exemple
  `(node.is_requirement and node["STATUS"] == "Active")`. La requête des
  facettes se combine par ET avec le texte ; une valeur inconnue est ignorée.
- `collect_statuses` liste les valeurs de `STATUS` du projet pour le menu.

## `trace`, `deep_trace`, `traceability_matrix`

Générateurs minces (`generator.py`, 40 lignes) qui produisent la page du
document avec le gabarit « trace » ou « deep trace ». La matrice
(`traceability_matrix/generator.py`, `view_object.py`) croise les documents deux
à deux selon `traceability_matrix_relation_columns`.

## `project_statistics` et `tree_map` (les deux `Feature` migrées)

Seules features qui implémentent `core/feature.Feature`
(`feature.py` : `HANDLE`, `supports_export`, `export`, `supports_server`,
`screen_filename`, `render_screen`, `screen_icon`).

- `project_statistics` : `generator.py` calcule des `MetricSection` (`metric.py`)
  sur l'index, en quatre sections : informations générales, sections,
  exigences, fichiers source ; `statistics_generator` du `ProjectConfig` peut pointer vers
  un générateur personnalisé. Écran rendu par `screen.py`.
- `tree_map` : `data_generator.py` (500 lignes) construit un `TreeMap`
  (`models.py`) : un rectangle par document, nœud ou fichier, colorié par ratio
  de couverture (`_get_coverage_color`) ; le navigateur le dessine
  (`assets/tree_map/*.js`). `plotly` et `pandas` sont listés dans les
  dépendances de `pyproject.toml`, mais aucun module Python ne les importe.

## `source_coverage` et `source_file_view`

Alimentées par `FileTraceabilityIndex` ([04](04-core-index-et-tracabilite.md)).
`source_file_view/generator.py` colore les fichiers avec Pygments (lexeurs C,
C++, Python, JS, TOML, YAML, RST, TeX, Jinja), insère les liens des marqueurs
vers les nœuds et affiche les plages couvertes. `source_coverage` dresse la liste
des fichiers avec leur couverture. Le serveur les génère à la demande (branche
`_source_files` de `generate_document`).

## `diff_and_changelog` (2 050 lignes)

Compare deux versions d'un projet.

| Fichier | Rôle |
|---|---|
| `git_client.py` | `GitClient` : crée des copies de travail de révisions Git (worktrees en cache, verrou de fichier), `check_revision`, `get_tags_for_revision` |
| `change_generator.py` | `ChangeGenerator.generate_from_paths`, `generate_from_revisions` : construit deux index (ancien et nouveau) |
| `project_diff_analyzer.py` (900 lignes) | compare nœuds et documents par MID, par hash et par ressemblance de texte (`calculate_similarity` sur `TITLE`, `STATEMENT`, `RATIONALE`) ; produit `DocumentChange`, `RequirementChange`, `RequirementFieldChange` (`change.py`) |
| `change_container.py`, `diff_screen_*_view_object.py` | contenu et rendu de l'écran |

Deux entrées : l'option d'export `--generate-diff-git "A..B"` ou
`--generate-diff-dirs OLD NEW`, et les routes serveur `/diff` et `/diff_result`
(`other_router.py`).

## `html2pdf`

Chaîne d'export :

```
HTMLFormat export (pages DOCUMENT) -> HTML2PDFGenerator.export_tree()      features/html2pdf/html2pdf_generator.py
  1. copie les assets dans output/html2pdf/html/
  2. pour chaque document : DocumentHTML2PDFGenerator.export -> <doc>-PDF.html
  3. PDFPrintDriver : lance html2pdf4doc (Chrome headless) -> output/html2pdf/pdf/<doc>.pdf
  4. PDFPostprocessor.rewrite_cross_document_links : réécrit les liens entre PDF (actions GoToR)
```

`pdf_print_driver.py` traduit les erreurs (Chrome introuvable, délai dépassé)
en messages (`PDFPrintDriverException`). Options : `html2pdf_strict`,
`html2pdf_template`, `html2pdf_forced_page_break_nodes`, `--chromedriver`,
`--chrome-binary`, `--disable-ssl-check`. Le mode « bundle »
(`--generate-bundle-document`) assemble tous les documents en un seul PDF avec
des assets à plat (`flat_assets`).

Ajout du fork : `changes.py` calcule les nœuds modifiés depuis la dernière
étiquette de version Git du document (`features/git_config/versioning.py`) pour
tracer des barres de changement dans le PDF.

## `project_index`

Écran d'accueil et barre latérale. `view_object.py` (`ProjectTreeViewObject`),
`generator.py` (`index.html`), `project_map_generator.py` (carte JS de l'arbre),
`sidebar.py` (route `/fragments/project_tree`, ajoutée par le fork pour que
chaque écran serveur montre l'arbre).

## `launcher`

`strictdoc launcher` ouvre une application Tk (`launcher_frame.py`, 1 930
lignes) qui choisit un dossier de travail, lit le titre du projet dans
`strictdoc_config.py` ou `strictdoc.toml`, mémorise ses réglages dans
`.strictdoc_launcher.json` et lance l'export ou le serveur par un sous-processus
`strictdoc.cli.main`. `git_action.py` : actions Git de la fenêtre. Disponible seulement si
`tkinter` est installé (`is_launcher_available()`).

## Bibliothèques JS

`mathjax` (déprécié, tâche `20260614_deprecate_features_mathjax_mermaid`),
`mermaid` et `plantuml` : fichiers statiques chargés quand le document les
utilise (`is_activated_mathjax`, `is_activated_mermaid`,
`is_activated_plantuml`).

## Comment une feature se branche

| Étape | Où |
|---|---|
| activation par l'utilisateur | `project_features=[...]` (`ProjectFeature` ou instance de `Feature`) |
| test dans le code | `project_config.is_activated_<x>()` ou `is_feature_activated(ProjectFeature.X)` |
| templates | dossier `features/<nom>/templates` ajouté à `HTML_TEMPLATE_DIRS` (`core/environment.py`) |
| ressources | dossier `features/<nom>/assets` ajouté à `HTML_STATIC_DIRS` |
| export statique | soit `Feature.export()`, soit un appel dans `HTMLGenerator.export_complete_tree` |
| écran serveur | soit `Feature.screen_filename()`/`render_screen()`, soit une branche de `generate_document` dans `main_router.py` ; réponse 412 si la fonction n'est pas activée |
| routes d'action | `create_<x>_routers(...)` inclus dans `create_main_router` + entrées dans `ROUTE_ROLES` |
| lien dans le menu | `Feature.screen_icon()` ou un lien dans `_shared/nav.jinja.html` |

Règle du dépôt : une feature reste dans son dossier ; ne pas modifier un
composant partagé pour un besoin local sans accord (`AGENTS.md`).
