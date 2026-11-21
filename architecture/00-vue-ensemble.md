# 00 - Vue d'ensemble

Lire d'abord. Les autres documents détaillent chaque couche. L'index est dans
[INDEX.md](INDEX.md).

## Ce que fait le logiciel

StrictDoc gère des exigences et de la documentation technique. Il lit des
fichiers texte (`.sdoc`, Markdown, ReqIF, Excel, annotations dans le code
source), construit en mémoire un graphe de traçabilité, puis soit l'exporte
(HTML, PDF, DOCX, Excel, ReqIF, JSON, SPDX, Markdown), soit le sert comme
application web éditable.

Ce dépôt est un fork de StrictDoc 0.30.2 (`strictdoc/__init__.py`) pour le pilote
ISIS. Branche de référence : `develop` (elle suit `fork/develop`). Remotes : `origin` (GitLab
interne) et `fork` (GitHub). Le fork part du commit amont `cc8be7913` (2026-10-09)
et ajoute des fonctions absentes de l'amont : import et export Word, éditeur
Markdown Milkdown, rôles et identité, commentaires de relecture, hiérarchie
documentaire, plusieurs projets par serveur, Git, SVG, interface en français,
navigation par groupes avec page d'un item et versions d'un document, mise en page
pour petit écran, assistant LLM et base de connaissances. Voir
[08-features-fork-isis.md](08-features-fork-isis.md) et
[09-assistant-llm-et-kb.md](09-assistant-llm-et-kb.md).

## Pipeline

```
fichiers du projet                      strictdoc_config.py / strictdoc.toml
  .sdoc .md .reqif                            |
  sources annotées @relation                      v
        |                                 ProjectConfig  (core/project_config.py)
        v                                         |
 1. Backends (strictdoc/backend)   <--- Format.read_from_file(), un par extension
    texte -> objets SDocDocument / SDocNode
        |
        v
 2. Core (strictdoc/core)
    DocumentFinder -> DocumentTree
    TraceabilityIndexBuilder -> TraceabilityIndex + GraphDatabase
    (+ FileTraceabilityIndex pour code source <-> exigences)
        |
        +---------------------------+
        v                           v
 3a. CLI export                 3b. Serveur web
    ExportAction                   FastAPI + uvicorn
    Format.export_complete_tree    routes qui modifient le modèle en mémoire,
    (HTML, PDF, DOCX, ...)         réécrivent le .sdoc, ré-exportent la page
        |                           |
        +----------> templates Jinja2 (strictdoc/export/html + features/*/templates)
```

Les templates Jinja2 sont communs au site statique et au serveur : le serveur
réutilise le générateur HTML et écrit les pages dans `output/server/html`.

## Carte du dépôt

| Chemin | Contenu | Document |
|---|---|---|
| `strictdoc/cli`, `strictdoc/commands` | point d'entrée, sous-commandes | [01](01-cli-et-commandes.md) |
| `strictdoc/backend` | lecture et écriture de chaque format | [02](02-modele-sdoc-et-grammaire.md), [03](03-formats-et-backends.md) |
| `strictdoc/core` | configuration, arbre de documents, index de traçabilité, transformations | [04](04-core-index-et-tracabilite.md) |
| `strictdoc/server` | application FastAPI, routeurs, verrous | [05](05-serveur-web.md) |
| `strictdoc/export/html` | générateur HTML, templates, objets de formulaire, JS/CSS statiques | [06](06-frontend-et-export-html.md) |
| `strictdoc/features` | tranches verticales (amont et fork) | [07](07-features-amont.md), [08](08-features-fork-isis.md), [09](09-assistant-llm-et-kb.md) |
| `strictdoc/helpers` | utilitaires (fichiers, git, parallélisation, MID, tri, ...) | [04](04-core-index-et-tracabilite.md) |
| `strictdoc/api` | façade d'import pour les configurations Python | [04](04-core-index-et-tracabilite.md) |
| `tests/` | unitaires, intégration LIT, end2end Selenium, screencast | [11](11-tests-qualite-build.md) |
| `docs/`, `spec/` | documentation et exigences de StrictDoc (écrites en `.sdoc`) | [12](12-conventions-et-recettes.md) |
| `developer/` | tâches, plans de design du fork, skills, bundle Milkdown, Docker de test | [11](11-tests-qualite-build.md), [12](12-conventions-et-recettes.md) |
| `tasks.py` | toutes les tâches de développement (Invoke) | [11](11-tests-qualite-build.md) |

## Taille (fichiers Python suivis par Git, hors tests)

| Paquet | Lignes Python | Remarque |
|---|---|---|
| `backend` | 25 300 | `docx` 4 700, `markdown` 3 800, `sdoc_source_code` 4 800, `sdoc` 6 300 |
| `features` | 25 700 | `llm` 8 700, `launcher` 2 100, `diff_and_changelog` 2 000 |
| `core` | 10 800 | `project_config.py` 1 760, `traceability_index.py` 1 640 |
| `server` | 7 450 | `main_router.py` 5 700 lignes à lui seul |
| `export/html` | 5 900 | |
| `commands` | 2 400 | |
| `helpers` | 1 900 | |
| `cli` | 320 | |

Le dépôt contient 570 tests d'intégration (`.itest`), 430 fichiers de test
end2end, 161 fichiers de test unitaires et 41 de test serveur.

## Pile technique

| Rôle | Bibliothèque |
|---|---|
| Parseur du format `.sdoc` | textX 4 (grammaire en chaînes Python) |
| Parseur des commentaires de code (marqueurs) | lark, tree-sitter (C, C++, Python, Rust) |
| Markdown | markdown-it-py (CommonMark) |
| Templates | Jinja2 (compilés et mis en cache hors petits projets) |
| Serveur web | FastAPI, uvicorn, WebSockets |
| Interface | HTML rendu côté serveur, Turbo (`turbo.min.js`), JS simple sans framework |
| Éditeur Markdown | Milkdown Crepe, bundle commité (voir [06](06-frontend-et-export-html.md)) |
| PDF | html2pdf4doc (Chrome headless), pypdf |
| Autres formats | reqif, XlsxWriter/openpyxl/xlrd, spdx-tools, resvg-py (SVG vers PNG). Le DOCX est écrit à la main en WordprocessingML (zipfile + XML), sans python-docx |
| Git | GitPython, python-gitlab |
| LLM | clients HTTP maison (Ollama/OpenAI compatible, Anthropic) |
| i18n | Babel (catalogues `.po`) |
| Qualité | ruff, mypy, fixit, pytest, LIT + FileCheck, SeleniumBase, Playwright |

Python 3.10 minimum. Paquet construit avec hatchling, point d'entrée
`strictdoc = strictdoc.cli.main:main`.

## Lancer

```
invoke server --input-path <dossier>      # serveur depuis les sources, port 5111
strictdoc export <dossier> --formats=html # export statique, sortie dans ./output/html
strictdoc server <dossier> --watch        # serveur avec rechargement sur changement de fichier
```

Tout le travail de développement passe par `invoke` (voir
[11-tests-qualite-build.md](11-tests-qualite-build.md)).

## Règles qui s'appliquent à tout le dépôt

- `AGENTS.md` : l'agent commence chaque session par une déclaration de
  conformité à AGENTS.md et au guide du développeur
  (`docs/strictdoc_11_developer_guide.sdoc`, en lecture seule).
- Ne pas toucher un composant partagé pour une fonction locale sans accord.
- Ne pas modifier `developer/tasks/<tâche>/` sauf `Context.md`.
- Toute prose écrite dans le dépôt passe par `developer/skills/humanizer/SKILL.md`.

Détails dans [12-conventions-et-recettes.md](12-conventions-et-recettes.md).
