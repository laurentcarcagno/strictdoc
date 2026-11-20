# 03 - Formats et backends

Fichiers : `strictdoc/core/format.py` (abstraction), `strictdoc/backend/*`,
`strictdoc/export/html/html_format.py`, `strictdoc/features/html2pdf`,
`strictdoc/features/doxygen`.

## L'abstraction `Format`

`core/format.py` définit la classe abstraite `Format`. Chaque format déclare ce
qu'il sait faire. La `ProjectConfig` garde la liste des instances
(`project_config.formats`, construite par `ProjectConfig.default_formats()`),
et un utilisateur peut y ajouter les siennes dans `strictdoc_config.py`.

| Méthode | Sens |
|---|---|
| `handles()` | poignées de la CLI et de la configuration (`["html"]`) |
| `supported_extensions()` | extensions associées |
| `supports_read()` + `read_extensions()` + `read_from_file()` | `DocumentFinder` lit ces fichiers pour construire l'arbre |
| `supports_edit()` | le serveur peut créer et modifier des documents de ce format |
| `supports_grammar()` + `grammar_extensions()` + `read_grammar()` | fichiers de grammaire (`.sgra`, `.gra.md`) |
| `supports_export()` + `export_complete_tree(context, handle)` | export de tout le projet |
| `export_single_document(...)` | export d'un document (utilisé par le serveur) |
| `supports_import()` + `add_import_arguments()` + `build_import_options()` + `import_file()` | entrée de `convert` |
| `supports_convert_output()` + `write_converted_document()` | sortie de `convert` |

`ExportContext` transporte `project_config`, `traceability_index`,
`parallelizer`, et, pour les formats HTML, `html_templates` et le document
« bundle ».

### Matrice des formats intégrés

| Format (classe) | Poignées | Extensions | Lecture | Édition serveur | Export | Import (`convert`) |
|---|---|---|---|---|---|---|
| `SDocFormat` | `sdoc` | `.sdoc` | oui | oui | oui | non, mais sortie de `convert` |
| `MarkdownFormat` | `markdown` | `.md`, `.markdown` | oui | oui | oui | non |
| `ReqIFFormat` | `reqif-sdoc`, `reqifz-sdoc` | `.reqif`, `.reqifz` | oui (`.reqif`) | non | oui | oui |
| `ExcelFormat` | `excel` | `.xlsx` | non | non | oui | oui |
| `DocxFormat` | `docx` | `.docx` | non | non | oui | oui |
| `RSTFormat` | `rst` | `.rst` | non | non | oui | non |
| `HTMLFormat` | `html` | `.html` | non | non | oui | non |
| `HTML2PDFFormat` | `html2pdf` | `.pdf` | non | non | oui | non |
| `JSONFormat` | `json` | `.json` | non | non | oui | non |
| `SPDXFormat` | `spdx` | `.spdx` | non | non | oui | non |
| `DoxygenFormat` | `doxygen` | `.tag` | non | non | oui | non |
| `JUnitXMLFormat` | aucune | `.junit.xml` | oui (rapport de test) | non | non | non |
| `RobotXMLFormat` | aucune | `.robot.xml` | oui (rapport de test) | non | non | non |
| `GCovJSONFormat` | aucune | `.gcov.json` | oui (couverture) | non | non | non |

La liste fait foi dans `ProjectConfig.default_formats()`. Le répartiteur par
extension de `DocumentFinder` (`_build_extension_dispatch_table`) trie les
extensions de la plus longue à la plus courte pour que `.gra.md` soit reconnu
avant `.md`.

Pour ajouter un format : sous-classer `Format`, l'ajouter à
`default_formats()`, ajouter sa poignée à `EXPORT_FORMATS` dans
`commands/export.py` si l'export doit être validé par défaut, et ses tests dans
`tests/integration/features/<format>/`. La tâche
`developer/tasks/20260711_1_format_abstraction/task.md` en explique l'histoire.

## Backend `sdoc`

Voir [02-modele-sdoc-et-grammaire.md](02-modele-sdoc-et-grammaire.md).

## Backend `markdown` (`backend/markdown`, 3 800 lignes)

Format Markdown de StrictDoc, défini par `spec/Markdown.md` et
`spec/Markdown.gra.md` (écrits dans ce format même). Un document commence par un
titre H1, chaque titre inférieur est un nœud, les champs s'écrivent
`**Statement**:`. Fichiers :

| Fichier | Rôle |
|---|---|
| `reader.py` (2 030 lignes) | `SDMarkdownReader` : markdown-it-py vers `SDocDocument` ; détecte les styles de métadonnées, découpe les enregistrements plats, applique la grammaire |
| `writer.py` | `SDMarkdownWriter` : `SDocDocument` vers Markdown, à la largeur `document_line_width` |
| `grammar_reader.py`, `default_grammar.py` | grammaire `.gra.md` et grammaire par défaut des documents Markdown (titres en casse « titre ») |
| `lax_heading.py` | analyseur de titres tolérant |
| `markdown_to_html_fragment_writer.py` | rendu Markdown vers HTML pour les pages |
| `formatter.py` | commande `format` |
| `markdown_format.py` | `MarkdownFormat` |

Un nœud de document Markdown est tout de même un `SDocNode` : les deux formats
sont interchangeables pour tout ce qui est en aval.

## Backend `rst` (`backend/rst`)

Export RST (`RSTFormat`, `writer.py`, templates `requirement.jinja.rst`) et rendu
RST vers HTML (`rst_to_html_fragment_writer.py`, docutils). Directives et rôles
maison : `directives/wildcard_enhanced_image.py` (images par motif),
`directives/sphinx_style_math.py`, `directives/raw_html_role.py`.
`strictdoc_lexer.py` est le lexeur Pygments du format `.sdoc`.

## Backend `reqif` (`backend/reqif`)

Passe par la bibliothèque `reqif`. Profil unique : `p01_sdoc`
(`sdoc_reqif_fields.py`).

| Fichier | Rôle |
|---|---|
| `p01_sdoc/sdoc_to_reqif_converter.py` | `SDocDocument` vers objets ReqIF |
| `p01_sdoc/reqif_to_sdoc_converter.py` | ReqIF vers `SDocDocument` (profil, MID, XHTML/markup) |
| `reqif_export.py`, `reqif_import.py`, `reqif_reader.py` | pilotes |

Options : `--reqif-profile`, `--reqif-multiline-is-xhtml`, `--reqif-enable-mid`,
`--reqif-import-markup`. Le serveur expose un import ReqIF
(`/actions/project_index/import_document_reqif`) et des exports
(`/reqif/export_document/{mid}`, `/reqif/export_tree`).

## Backend `excel` (`backend/excel`)

Export (`export/excel_generator.py`, XlsxWriter) des champs choisis par
`--fields` (défaut `uid,statement,parent`) et import
(`import_/excel_to_sdoc_converter.py`, `excel_sheet_proxy.py`, drapeau
`--excel-parser`).

## Backend `docx` (`backend/docx`, 4 700 lignes) - ajout du fork

Pas de python-docx : le fichier Word est un zip de WordprocessingML écrit et lu
à la main.

| Zone | Fichiers | Rôle |
|---|---|---|
| profil | `docx_profile.py` | `DocxProfile` : styles de titres, `DocxRequirementTable` (tableau d'une exigence : style de l'identifiant, lignes meta, note, champs de relation). Un profil est un fichier Python avec `create_profile()` |
| import | `import_/docx_reader.py`, `docx_to_sdoc_converter.py`, `sdoc_requirement_blocks.py` | lecture des paragraphes et tableaux, modes `TrackedChangesMode` (accepter ou rejeter les modifications suivies), fusion par UID dans un `.sdoc` existant, rapport `DocxImportReport` |
| export neuf | `export/sdoc_to_docx_generator.py`, `docx_template.py`, `markdown_to_paragraphs.py`, `rst_to_paragraphs.py`, `text_to_paragraphs.py`, `docx_xml.py`, `docx_images.py` | génération à partir d'un modèle Word (PNG, JPEG, GIF, SVG avec repli PNG via `features/svg/rasterizer.py`) |
| export mise à jour | `export/docx_tracked_update.py` | met à jour un Word existant en modifications suivies (`DocxUpdater`, `DocxUpdateReport`) |
| commentaires | `export/docx_comments.py` | commentaires de relecture vers Word |
| web | `docx_web_service.py`, routeur `server/routers/docx_router.py`, templates `features/docx/templates` | formulaires d'import et d'export avec aperçu |
| pilotes | `docx_import.py`, `docx_export.py`, `docx_format.py` | CLI et API |

Options de `convert` : `--docx-profile`, `--docx-tracked-changes`,
`--docx-overwrite`, `--docx-dry-run`. Le plan est dans
`developer/design/docx_import_export_plan.md`.

## Backends `json`, `spdx`, `gcov`

- `json/json_generator.py` : export JSON de l'arbre.
- `spdx/spdx_generator.py` et `spdx_to_sdoc_converter.py` : export SPDX.
- `gcov/reader.py` : lit la couverture gcov JSON (`gcovr`) et produit un
  document de nœuds liés aux fichiers source par des `FileReference`
  (`GCovStatsObject` compte les fonctions couvertes). `gcov/helpers.py`
  normalise les chemins.
- `features/doxygen/generator.py` : écrit `strictdoc.tag`, un fichier de tags
  Doxygen qui pointe vers les pages HTML des nœuds.

## Backend `sdoc_source_code` (`backend/sdoc_source_code`, 4 800 lignes)

Lit des fichiers source et en tire la traçabilité exigence vers code.

Syntaxe d'un marqueur, dans un commentaire :

```
@relation(UID-1, UID-2, scope=function, role=implements)
```

| `scope` | Portée |
|---|---|
| `file` | le fichier |
| `function`, `class` | l'élément qui suit |
| `line` | la ligne |
| `range_start`, `range_end` | un bloc entre deux marqueurs |

Chaîne de lecture :

```
SourceFilesFinder (core/file_system) liste les fichiers
  -> SourceFileTraceabilityCachingReader.read_from_file()      (cache pickle "source_file")
       SourceCodeReaderRegistry.get_reader(path)
         .py   SourceFileTraceabilityReader_Python   (tree-sitter)
         .c .h .cc .hh .cpp .hpp   ..._C             (tree-sitter)
         .rs   ..._Rust                              (tree-sitter)
         .robot ..._Robot
         autre  SourceFileTraceabilityReader         (grammaire textX, lignes)
       MarkerParser.parse() (lark + MarkerLexer) -> LineMarker, RangeMarker, LanguageItemMarker
       processors/general_language_marker_processors.py -> SourceFileTraceabilityInfo
```

`SourceFileTraceabilityInfo` (`models/source_file_info.py`) garde les marqueurs
par UID (`ng_map_reqs_to_markers`), les fonctions et classes
(`LanguageItem`), les nœuds source (`SourceNode`) et les plages fusionnées pour
calculer la couverture. Les « source nodes » sont des nœuds SDoc écrits dans les
commentaires (balises personnalisées déclarées dans `source_nodes` de la
configuration) ; `source_writer.py` et `marker_writer.py` les réécrivent dans le
fichier.

Sous-dossier `test_reports/` : `junit_xml_reader.py` et `robot_xml_reader.py`
produisent des nœuds `TEST_RESULT` (grammaire
`DocumentGrammar.create_for_test_report()`), rattachés aux exigences par les
marqueurs des tests. Dossiers déclarés par `test_report_root_dict`.

La résolution finale (marqueur vers exigence, couverture, nœuds source
fusionnés) est dans `core/file_traceability_index.py`
([04](04-core-index-et-tracabilite.md)).

## Exports portés par des features

| Format | Code | Voir |
|---|---|---|
| `html` | `export/html/html_generator.py` | [06](06-frontend-et-export-html.md) |
| `html2pdf` | `features/html2pdf/` | [07](07-features-amont.md) |
| `doxygen` | `features/doxygen/` (`generator.py`) | [07](07-features-amont.md) |
