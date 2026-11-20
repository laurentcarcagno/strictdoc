# 01 - CLI et commandes

Fichiers : `strictdoc/cli/`, `strictdoc/commands/`, `strictdoc/core/actions/`,
`strictdoc/features/export/export_action.py`.

## Chaîne d'appel

```
strictdoc <cmd> ...
  cli/main.py:main()                 mesure le temps total, appelle _main()
    SDocArgsParser.create_sdoc_args_parser(COMMAND_REGISTRY)   argparse
    parser.run(parallelizer)         instancie la commande, appelle command.run()
```

`_main()` (`cli/main.py`) fait aussi :

- active `environment.is_debug_mode`, `is_development_mode`, `is_test_env`
  (variable `STRICTDOC_ENV=test`) ;
- force le démarrage de processus `fork` hors Windows (performances macOS) ;
- force la sortie standard en UTF-8 ;
- crée le `Parallelizer` (multiprocessing, désactivé par `--no-parallelization`) ;
- attrape toute exception, affiche un message court, et la trace avec `--debug`.

## Registre des commandes

`create_command_registry()` dans `cli/main.py` renvoie un dictionnaire
`nom -> classe`. Une valeur qui est elle-même un dictionnaire est une famille
de sous-commandes (`manage`).

| Commande | Classe | Rôle |
|---|---|---|
| `export` | `ExportCommand` (`commands/export.py`) | exporte un projet vers un ou plusieurs formats |
| `server` | `ServerCommand` (`commands/server.py`) | serveur web, un projet ou un registre de projets |
| `convert` | `ConvertCommand` (`commands/convert.py`) | convertit un fichier externe (DOCX, ReqIF, Excel, ...) vers `.sdoc` ou Markdown |
| `format` | `FormatCommand` | réécrit les `.sdoc` et `.md` à la largeur de ligne configurée |
| `manage assets` | `ManageAssetsCommand` | gère les images (`--clean-unused-images`) |
| `manage auto-uid` | `ManageAutoUIDCommand` | génère les UID manquants |
| `manage new` | `ManageNewCommand` | crée un nœud avec MID et UID uniques (`--document-path`, `--parent-uid-or-mid`, `--node-type`) |
| `new` | `NewCommand` | crée un projet initial |
| `about`, `version` | | informations |
| `launcher` | `LauncherCommand` | fenêtre Tk, seulement si `tkinter` est disponible |

L'ancienne commande `import` n'existe plus : `convert` la remplace (tâches
`20260711_3_convert_command_replaces_import`).

Note : `ExportCommand.HELP` contient le texte « Print the version of
StrictDoc. » (copie d'un autre fichier). C'est un défaut connu de l'amont, sans
effet fonctionnel.

## Modèle d'une commande

Chaque commande est une paire de fichiers.

| Fichier | Contenu |
|---|---|
| `commands/<nom>_command.py` ou `<nom>.py` | classe `BaseCommand` : `HELP`, `DETAILED_HELP`, `add_arguments(parser)`, `__init__(args)`, `run(parallelizer)` |
| `commands/<nom>_config.py` | `<Nom>CommandConfig(**vars(args))` avec `validate()` qui lève `CLIValidationError` |

`BaseCommand` (`cli/base_command.py`) est abstraite. `commands/_shared.py`
fournit `_SilentArgumentParser` et la validation des profils ReqIF.

La plupart des commandes finissent par `ProjectConfigLoader.load_using_<x>_config()`
qui construit la `ProjectConfig` à partir du fichier de configuration et des
options de la ligne de commande (voir [04](04-core-index-et-tracabilite.md)).

## `export`

Fichier : `commands/export.py`. Options principales : `input_paths` (un ou
plusieurs dossiers), `--output-dir`, `--formats` (liste séparée par des virgules),
`--project-title`, `--config`, `--generate-bundle-document`, `--included-documents`,
`--filter-nodes`, `--view`, `--generate-diff-git "A..B"`, `--generate-diff-dirs`,
options ReqIF (`--reqif-profile`, `--reqif-multiline-is-xhtml`, `--reqif-enable-mid`),
options html2pdf (`--chromedriver`, `--chrome-binary`, `--disable-ssl-check`),
`--no-parallelization`, `--enable-mathjax` (déprécié).

Formats acceptés : `html`, `html2pdf`, `markdown`, `rst`, `json`, `excel`,
`reqif-sdoc`, `reqifz-sdoc`, `sdoc`, `doxygen`, `spdx`, plus les poignées des
`Format` personnalisés déclarés dans la configuration. Comme la validation
d'`--formats` se fait pendant le parsing argparse, avant le chargement de la
configuration, `_preparse_config_path()` ré-analyse `sys.argv` pour trouver la
configuration et lister ces poignées.

Séquence de `ExportCommand.run()` :

1. `export_config.validate()`.
2. `ProjectConfigLoader.load_using_export_config(export_config)`.
3. `ExportAction(project_config, parallelizer)` : le constructeur appelle
   `build_index()` (donc `TraceabilityIndexBuilder.create`).
4. `ExportAction.export()` (`features/export/export_action.py`) :
   - crée `HTMLTemplates` seulement si `html` ou `html2pdf` est demandé ;
   - crée le document « bundle » si `--generate-bundle-document` ;
   - construit un `ExportContext` ;
   - parcourt `project_config.formats` dans l'ordre fixe d'enregistrement (pas
     l'ordre de `--formats`) et appelle `format_.export_complete_tree(context, handle)` ;
   - si `html` est demandé, exporte les `Feature` qui `supports_export()`
     (statistiques de projet, tree map), sauf si tout est à jour.

## `server`

Fichier : `commands/server.py`. Deux modes exclusifs.

| Mode | Arguments | Fonction appelée |
|---|---|---|
| un projet | `input_path`, `--port`, `--host`, `--output-path`, `--watch`, `--config` | `run_strictdoc_server` |
| plusieurs projets | `--projects <registre.py>`, `--root-host`, `--data-root` | `run_strictdoc_projects_server` |

`--reload` et `--no-reload` servent au développement de StrictDoc et sont cachés.
`--watch` active le rechargement des navigateurs quand un fichier change sur le
disque (`server/document_watcher.py`). Détails dans
[05-serveur-web.md](05-serveur-web.md).

## `convert`

`commands/convert.py` délègue à `core/actions/convert_action.py` :

1. trouve le `Format` d'entrée par `--input-format` ou par l'extension du fichier
   (`Format.handle_for_extension`) ;
2. vérifie `supports_import()` et, pour la sortie, `supports_convert_output()` ;
3. `input_format.build_import_options(args)` puis `import_file(options, project_config)` ;
4. `output_format.write_converted_document(...)` pour chaque document obtenu.

Chaque `Format` d'import ajoute ses propres drapeaux via
`add_import_arguments(parser)` (par exemple `--docx-profile`, `--docx-overwrite`,
`--docx-dry-run`, `--docx-tracked-changes`, `--excel-parser`, `--reqif-profile`).
`convert` ne connaît donc aucun format en particulier.

## `format`, `manage`, `new`

- `format` relit tout l'arbre via `TraceabilityIndexBuilder` et réécrit chaque
  document avec `SDWriter` ou `SDMarkdownWriter`, à la largeur
  `document_line_width`.
- `manage auto-uid` : voir `commands/manage_autouid_command.py` (utilise
  `core/analyzers/document_uid_analyzer.py` pour trouver le prochain UID, option
  `--include-sections`).
- `manage new` : crée un nœud dont les champs obligatoires valent `TBD`.
- `new` : crée `strictdoc_config.py` et deux documents d'exemple dans `docs/`
  (`high_level_requirements.sdoc`, `low_level_requirements.sdoc`).

## Où ajouter une commande

1. `commands/<nom>_command.py` (classe `BaseCommand`) et `commands/<nom>_config.py`.
2. L'ajouter dans `create_command_registry()` de `cli/main.py`.
3. Un test d'intégration dans `tests/integration/features/commands/<nom>/`.
4. Documenter dans `docs/strictdoc_01_user_guide.sdoc` et les notes de version.
