# 04 - Core : configuration, arbre de documents, index de traçabilité

Fichiers : `strictdoc/core/` (10 800 lignes), `strictdoc/helpers/`,
`strictdoc/api/`.

## Configuration (`core/project_config.py`, 1 760 lignes)

### Source de la configuration

`ProjectConfigLoader.load_from_path_or_get_default(path_to_config=...)` :

1. chemin absent : `ProjectConfig.default_config()` ;
2. dossier : prend `strictdoc_config.py` s'il existe, sinon `strictdoc.toml` ;
3. `.py` : `load_from_python` importe le fichier (`helpers/module.import_from_path`)
   et appelle sa fonction `create_config()` qui doit renvoyer une `ProjectConfig` ;
4. `.toml` : lu avec `toml.load`, converti par `_load_from_dictionary`, et
   enregistre un message de dépréciation (`DEPRECATED_CONFIG_TOML`).

Le format Python est la voie principale (`strictdoc_config.py` à la racine du
dépôt en est un exemple). Il importe tout depuis `strictdoc.api` :

```python
from strictdoc.api import ProjectConfig

def create_config() -> ProjectConfig:
    return ProjectConfig(project_title="...", project_features=[...], ...)
```

`strictdoc/api/__init__.py` réexporte les classes publiques utiles à un
utilisateur (`ProjectConfig`, `ProjectFeature`, `SDocDocument`, `SDocNode`,
`TraceabilityIndex`, `TraceabilityIndexBuilder`, `StrictDocPlugin`, `Metric`,
`MetricSection`, `MID`, `GitClient`, ...). C'est la frontière de
compatibilité à ne pas casser sans raison.

### Chargeurs par commande

`ProjectConfigLoader.load_using_export_config`, `..._server_config`,
`..._convert_config`, `..._manage_autouid_config`, `..._format_config`,
`..._manage_new_config`, `..._manage_assets_config`. Chacun charge la
configuration puis la complète avec les options de la commande
(`integrate_export_config`, `integrate_server_config`) et appelle
`validate_and_finalize()` (chemins, favicon, CSS personnalisé, grammaires
`@alias`, `.gitignore` ajouté aux exclusions, rôles, hiérarchie, langue).

### Paramètres de `ProjectConfig(...)`

Regroupés par thème (voir le constructeur, lignes 182-320) :

| Thème | Paramètres |
|---|---|
| Projet | `project_title`, `dir_for_sdoc_assets` (`_static`), `dir_for_sdoc_cache` (`output/_cache`), `language` |
| Fonctions | `project_features` (liste de chaînes de `ProjectFeature` ou d'instances de `Feature`) |
| Entrées | `include_doc_paths`, `exclude_doc_paths`, `source_root_path`, `include_source_paths`, `exclude_source_paths`, `grammars` (alias `@nom` vers fichier), `test_report_root_dict`, `source_nodes` |
| Serveur | `server_host`, `server_port` (1024 à 65000), `lazy_document_loading_threshold` (200) |
| PDF | `html2pdf_strict`, `html2pdf_template`, `html2pdf_forced_page_break_nodes`, `chromedriver`, `chrome_binary` |
| Bundle | `bundle_document_uid`, `bundle_document_version`, `bundle_document_date` |
| Matrice | `traceability_matrix_relation_columns` |
| ReqIF | `reqif_profile`, `reqif_multiline_is_xhtml`, `reqif_enable_mid`, `reqif_import_markup` |
| Apparence | `launcher_logo_path`, `favicon_path`, `custom_css_path`, `document_line_width` |
| Extensibilité | `user_plugin` (`StrictDocPlugin`), `custom_node_prefix_function`, `custom_node_uid_function`, `formats` (liste de `Format`) |
| Fork : identité | `auth_mode` (`none` ou `proxy`), `trusted_proxies`, `roles`, `audit_dir` |
| Fork : hiérarchie | `document_hierarchy` (liste de `Level`), `relation_policy` (`off`, `warn`, `enforce`), `input_documents_editable`, `applicable_documents`, `suspect_links`, `suspect_fields` |
| Fork : docx | `docx_profile`, `docx_base` |
| Fork : assistant et Git | `llm` (`LLMConfig`), `git` (`GitConfig`) |

Attributs d'exécution (pas des paramètres) : `export_formats`, `output_dir`
(`output` par défaut, `output/server` pour le serveur),
`export_output_html_root` (`<output_dir>/html`), `is_running_on_server`,
`watch_enabled`, `member_role`, `members_admin`, `hierarchy_levels`.

Variables d'environnement lues par la configuration : `STRICTDOC_AUTH_MODE`,
`STRICTDOC_LANGUAGE`, `STRICTDOC_CACHE_DIR` (tests uniquement).

### Fonctions activables (`ProjectFeature`)

Enum de chaînes. `DEFAULT_FEATURES` = `TABLE_SCREEN`, `TRACEABILITY_SCREEN`,
`DEEP_TRACEABILITY_SCREEN`, `SEARCH`. Les autres : `MATHJAX`, `HTML2PDF`,
`REQIF`, `DOCX`, `COMMENTS`, `LLM`, `GIT`, `DIFF`, `PROJECT_STATISTICS_SCREEN`,
`TREE_MAP_SCREEN`, `TRACEABILITY_MATRIX_SCREEN`,
`REQUIREMENT_TO_SOURCE_TRACEABILITY`, `SOURCE_FILE_LANGUAGE_PARSERS`, `MERMAID`,
`NESTOR`, `ALL_FEATURES`. Des méthodes `is_activated_*()` (lignes 1180-1250)
répondent par fonction. `ALL_FEATURES` se développe en toutes les valeurs.

### Deux abstractions d'extension

| Abstraction | Fichier | Rôle |
|---|---|---|
| `Format` | `core/format.py` | contenu : lire, écrire, importer ([03](03-formats-et-backends.md)) |
| `Feature` | `core/feature.py` | capacité transverse qui se branche sur `export` et `server` : `HANDLE`, `supports_export()`/`export()`, `supports_server()`/`screen_filename()`/`render_screen()`, `screen_icon()` |

Aujourd'hui deux `Feature` seulement implémentent l'interface :
`ProjectStatisticsFeature` (`features/project_statistics/feature.py`) et
`TreeMapFeature` (`features/tree_map/feature.py`). `ProjectConfig._builtin_features_by_handle()`
les enregistre ; `get_features()` résout `project_features` en instances. Les
autres entrées de l'enum restent câblées à la main (tâche
`20260712_1_feature_abstraction`). Le plugin `StrictDocPlugin`
(`core/plugin.py`) n'a qu'un crochet : `traceability_index_build_finished`.

## Découverte des fichiers (`core/file_system/`)

| Fichier | Rôle |
|---|---|
| `file_tree.py` | `File`, `Folder`, `FileTree`, `FileFinder.find_files_with_extensions` (parcours avec inclusions/exclusions), `PathFinder` |
| `document_finder.py` | `DocumentFinder.find_sdoc_content(project_config, parallelizer)` renvoie `(DocumentTree, AssetManager)` |
| `source_files_finder.py`, `source_tree.py` | `SourceFilesFinder.find_source_files`, `SourceFile` (type par extension), `SourceTree` |

`DocumentFinder` :

1. `_build_file_tree` : un `FileTree` par chemin d'entrée, repère les dossiers
   `_assets` (`AssetManager`) et les fichiers dont l'extension est lue par un
   `Format`.
2. `_build_document_tree` : lit chaque fichier en parallèle
   (`_process_worker_parse_document` : choisit le `Format` par extension et
   appelle `read_from_file` ou `read_grammar`), fabrique un `DocumentMeta` par
   document (chemins d'entrée et de sortie, niveau, dossier d'assets) et
   range les grammaires `.sgra` dans `map_grammars_by_filenames` (le builder
   d'index les applique ensuite aux documents qui les importent).
3. `get_document_extensions(project_config)` sert aussi à l'observateur de
   fichiers du serveur pour rester aligné.

`DocumentTree` (`core/document_tree.py`) : `file_tree`, `document_list`,
`map_docs_by_paths`, `map_docs_by_rel_paths`, `map_grammars_by_filenames`,
`source_tree` (attaché plus tard).

`DocumentMeta` (`core/document_meta.py`) : tout ce qui situe un document sur le
disque et dans les URL : `input_doc_full_path`, `input_doc_rel_path`,
`output_document_full_path`, `get_html_link(document_type, depth)`,
`get_root_path_prefix()`.

Itérateurs : `SDocDocumentIterator` (`core/document_iterator.py`) parcourt les
nœuds d'un document (`all_content`, `all_node_content`, `table_of_contents`) en
calculant les niveaux ; `DocumentTreeIterator` fait de même sur l'arbre.

## Index de traçabilité

### Construction : `TraceabilityIndexBuilder.create()`

(`core/traceability_index_builder.py`, 990 lignes)

```
1. strictdoc_last_update   date du fichier .py/.html/.jinja/.svg le plus récent du paquet
                           (invalide les pages exportées quand le code change)
2. DocumentFinder.find_sdoc_content  -> DocumentTree, AssetManager
3. create_from_document_tree         -> TraceabilityIndex (graphe)
4. node_filter                       si --filter-nodes (QueryObject)
5. si REQUIREMENT_TO_SOURCE_TRACEABILITY :
     SourceFilesFinder -> pour chaque fichier SourceFileTraceabilityCachingReader
     -> traceability_index.create_traceability_info(...)
     -> FileTraceabilityIndex.validate_and_resolve(...)
6. résolution des InlineLink en attente (lève une erreur si l'UID n'existe pas)
7. FileDependencyManager.resolve_modification_dates
8. user_plugin.traceability_index_build_finished(index)
```

`create_from_document_tree` (annoté `SDOC-SRS-32`, `SDOC-SRS-102`) :

1. valide les grammaires `.sgra` ;
2. pour chaque document : ajoute les dépendances fichier d'entrée vers fichier de
   sortie, résout les grammaires importées, valide (`SDocValidator`), crée les
   liens `MID_TO_NODE`, `UID_TO_NODE`, collecte les tags ;
3. pour chaque nœud : enregistre MID et UID (une collision lève une erreur),
   enregistre les ancres, met les `InlineLink` en attente ;
4. deuxième passe : résout les relations `Parent` et `Child` (les UID sont connus),
   crée les liens de parenté dans les deux sens, détecte les cycles
   (`tree_cycle_detector.py`), calcule les profondeurs.

### `GraphDatabase` et ses buckets

`core/graph_database.py` expose une API de liens (`create_link`, `get_link_values`,
`has_link`, `get_link_values_reverse`, `delete_link`, ...) sur des « buckets »
typés (`core/graph/`).

| `GraphLinkType` (`core/constants.py`) | Bucket | Clé vers valeur |
|---|---|---|
| `MID_TO_NODE` | `OneToOneDictionary` | `MID` vers nœud, document, lien, ancre |
| `UID_TO_NODE` | `OneToOneDictionary` | UID vers document, nœud, ancre |
| `NODE_TO_PARENT_NODES` | `ManyToManySet` | nœud vers ses parents (avec arête = rôle) |
| `NODE_TO_CHILD_NODES` | `ManyToManySet` | nœud vers ses enfants |
| `NODE_TO_INCOMING_LINKS` | `ManyToManySet` | MID vers `InlineLink` entrants |
| `DOCUMENT_TO_TAGS` | `OneToOneDictionary` | MID de document vers dictionnaire de tags |

`ALL_EDGES = ".all"` désigne toutes les étiquettes. `GraphEdgeLabel`
(`implements`, `verifies`, `has result`, `satisfies`, ...) qualifie les liens
automatiques entre exigences, tests et résultats.

### `TraceabilityIndex` (`core/traceability_index.py`, 1 640 lignes)

L'objet central : tout ce que les générateurs et les routes lisent. Il porte
`graph_database`, `document_tree`, `asset_manager`, `file_dependency_manager`,
`validation_index`, `node_filter`, `index_last_updated`,
`strictdoc_last_update`, `search_index_timestamp`.

| Famille | Méthodes |
|---|---|
| Accès | `get_node_by_mid`, `get_node_by_uid`, `get_linkable_node_by_uid`, `get_document_by_title`, `get_document_iterator`, `get_grammar_element` |
| Relations | `get_parent_requirements`, `get_children_requirements`, `get_parent_relations_with_roles`, `get_child_relations_with_roles`, `get_display_role_for_*_relation` (rôle ou rôle inverse selon la grammaire), `has_parent_requirements`, `get_incoming_links` |
| Code source | `get_source_file_reqs`, `get_requirement_file_links`, `get_coverage_info`, `has_source_file_reqs` |
| Mutation (serveur) | `create_document`, `create_requirement`, `update_requirement_uid`, `update_requirement_parent_uid`, `update_requirement_child_uid`, `update_node_mid`, `update_with_anchor`, `delete_requirement`, `delete_document`, `remove_requirement_parent_uid`, `remove_inline_link`, `remove_anchor_by_uid`, `update_last_updated` |
| Validation avant mutation | `validate_can_remove_node`, `validate_can_remove_document`, `validate_node_against_anchors` |
| Droits fins | `can_edit_document`, `can_edit_node`, `can_comment_node`, `can_delete_node`, `can_clone_node`, `can_add_node`, `can_create_node_at`, `can_move_node`, `can_move_node_to`, `can_move_node_across_documents`, `input_allows_edit` (fork : documents d'entrée en lecture seule), `subtree_has_autogenerated_content`, `is_move_grammar_compatible` |
| Statut | `is_small_project()`, `is_up_to_date()` |
| Bundle | `clone_to_bundle_document()` : copie du projet en un document unique |

`can_edit_node` dépend du rôle de la requête courante : le fork utilise la
variable de contexte `CURRENT_ROLE` (`features/roles/principal.py`) car ces
prédicats n'ont pas la requête sous la main.

### Traçabilité code vers exigences : `FileTraceabilityIndex`

`core/file_traceability_index.py` (1 430 lignes). Après lecture de tous les
fichiers source, `validate_and_resolve()` :

1. indexe les fonctions publiques par nom ;
2. crée les nœuds générés à partir des commentaires (« source nodes ») et les
   fusionne avec les nœuds SDoc existants (`merge_sdoc_node_with_source_node`) ;
3. valide chaque marqueur `@relation` (UID inconnu, plage non fermée, ...) ;
4. relie exigences et fichiers dans les deux sens (`connect_sdoc_node_with_file_path`,
   `forward_*` pour les liens déclarés dans le `.sdoc` avec `File`) ;
5. calcule la couverture de code (`calculate_code_coverage_and_sort_nodes`) :
   plages couvertes, fusionnées, fonctions sans lien.

### Requêtes (`core/query_engine/`)

Mini-langage de filtrage de nœuds : `grammar.py` (textX), `query_reader.py`
(`QueryReader.read`), `query_object.py` (`QueryObject.evaluate`). Exemple :
`(node.is_requirement and node["STATUS"] == "Active")`. Expressions :
`and`, `or`, `not`, `==`, `!=`, `in`, `not in`, `any(...) in`, `all(...) in`,
`none(...) in`, `node["CHAMP"]`, `node.contains("x")`, `node.contains_any_text`,
`node.has_parent_requirements`, `node.has_child_requirements`,
`node.is_requirement`, `node.is_root`, `node.is_section`,
`node.is_source_file()` et ses variantes de couverture. Utilisé par `--filter-nodes` et par l'écran de
recherche du serveur (`/search`).

### Dépendances entre fichiers

`FileDependencyManager` (`core/file_dependency_manager.py`) mémorise, dans
`<cache>/dependencies`, quel fichier d'entrée produit quel fichier de sortie. À
la fin de la construction, `resolve_modification_dates` décide quelles pages
HTML sont à régénérer. `must_generate(path)` répond par fichier. C'est ce qui
rend un second `export` presque instantané.

## Transformations (`core/transforms/`)

Commandes qui modifient le modèle pour le serveur. Chacune valide, puis agit sur
les objets et sur l'index.

| Fichier | Commande |
|---|---|
| `update_requirement.py` (590 lignes) | `CreateOrUpdateNodeCommand` : crée ou met à jour un nœud depuis un `RequirementFormObject` (champs, relations, UID, ancres, liens) ; renvoie `CreateOrUpdateNodeResult` avec les nœuds à rafraîchir |
| `delete_requirement.py` | `DeleteRequirementCommand` |
| `move_node_across_documents.py` | déplacement d'un nœud d'un document à un autre |
| `update_document_config.py` | options du document |
| `update_grammar.py`, `update_grammar_element.py` | édition de la grammaire |
| `update_included_document.py` | document inclus |
| `validation_error.py` | `SingleValidationError`, `MultipleValidationErrorAsList` |
| `constants.py` | `NodeCreationOrder` |

## Analyseurs (`core/analyzers/`)

`document_stats.py` (`DocumentTreeStats` : compte nœuds et documents),
`document_uid_analyzer.py` (prochain UID selon le préfixe, utilisé par
`manage auto-uid`, `manage new` et le serveur).

## Utilitaires (`strictdoc/helpers/`)

| Fichier | Rôle |
|---|---|
| `parallelizer.py` | `Parallelizer`, `NullParallelizer` : multiprocessing avec contexte de travail partagé (`run_parallel_with_context`) |
| `timing.py` | `measure_performance`, `timing_decorator`, `measure_performance_loop` (barres de progression) |
| `file_system.py` | `file_open_read_utf8`, `file_open_read_bytes` (à utiliser à la place d'`open`) |
| `pickle.py` | `pickle_dump`, `pickle_load` (gère un changement de schéma en renvoyant `None`) |
| `exception.py` | `StrictDocException`, `ExceptionInfo`, `StrictDocChildProcessException` |
| `mid.py` | classe `MID` |
| `git_client.py` | lecture Git (version, branche, date de commit) pour les en-têtes de document |
| `deprecation_engine.py` | `DEPRECATION_ENGINE.add_message(...)`, affiché une fois |
| `paths.py` | `SDocRelativePath`, conversions URL et chemin |
| `textx.py` | `drop_textx_meta`, `preserve_source_location_data` |
| `cast.py`, `string.py`, `list.py`, `sorting.py`, `ordered_set.py`, `md5.py`, `sha256.py`, `lxml.py`, `net.py`, `shard.py`, `path_filter.py` | petits utilitaires |
| `auto_described.py` | décorateur `__repr__` automatique |
| `cargo_nextest.py`, `google_test.py`, `file_stats.py`, `diff.py`, `math.py`, `html_table.py`, `coverage.py` | rapports de test, statistiques de fichiers, diff, hook de couverture |

## Environnement (`core/environment.py`)

`SDocRuntimeEnvironment` (`strictdoc.environment`) : chemins du paquet, détection
PyInstaller et Nuitka (`is_binary_dist`), drapeaux `is_debug_mode`,
`is_development_mode`, `is_test_env`. Il liste aussi `HTML_TEMPLATE_DIRS` et
`HTML_STATIC_DIRS` : **toute nouvelle feature qui apporte des templates ou des
fichiers statiques doit ajouter son dossier ici**, sinon Jinja ne les trouve pas
et l'export n'embarque pas les ressources.
