# 11 - Tests, qualité, build, CI, déploiement

Fichiers : `tasks.py` (1 380 lignes), `tests/`, `pyproject.toml`, `ruff.toml`,
`mypy.ini`, `.github/workflows/`, `developer/`, `Dockerfile`, `flake.nix`.

## Invoke (`tasks.py`)

Toute tâche de développement est une tâche Invoke (`invoke --list`). Chacune
tourne dans un environnement virtuel `uv` propre (`build/uv/<groupe>`), un par
groupe de dépendances de `pyproject.toml` : `development`, `check`,
`documentation`, `release`, `release-local`, `pyinstaller`
(`UvEnvironment`, `run_invoke_with_uv`). Amorçage : `pip install -r
requirements.bootstrap.txt` (invoke et uv).

| Tâche | Alias | Rôle |
|---|---|---|
| `server` | `s` | serveur depuis les sources : `--debug --development --reload --watch`, option `--input-path`, `--config`, `--port` ; libère le port avant |
| `check` | `c` | tout sauf end2end : lint et tests |
| `lint` | | `lint-ruff-format`, `lint-ruff`, `lint-mypy`, `lint-format-js` (jsbeautifier), `lint-fixit` ; `lint-commit` valide les messages |
| `test` | | unitaires + intégration |
| `test-all` | | tout, y compris end2end |
| `test-unit` | | pytest sur `tests/unit` ; `--focus <sous-chaîne>`, `--path`, `--coverage` |
| `test-unit-server` | | pytest sur `tests/unit_server` |
| `test-integration` | | LIT + FileCheck sur `tests/integration` ; `--focus`, `--debug`, `--no-parallelization`, `--fail-first`, `--coverage`, `--strictdoc <commande>`, `--html2pdf`, `--shard` |
| `test-end2end` | | Selenium sur `tests/end2end` ; **toujours `--headless`** ; `--focus`, `--test-path`, `--exit-first`, `--parallelize`, `--long-timeouts`, `--shard`, `--coverage` |
| `test-screencast`, `screencast-server`, `screencast-optimize-video` | | vidéos de démonstration (`tests/screencast`, Playwright) |
| `docs` | | exporte la documentation de StrictDoc (`docs/*.sdoc`) avec lui-même |
| `changelog`, `check-dead-links` | | notes de version, liens morts |
| `release`, `release-local`, `release-pyinstaller`, `nuitka` | | publication PyPI, exécutables |
| `build-docker`, `run-docker`, `test-docker` | | image `Dockerfile` |
| `performance`, `performance-snakeviz`, `watch`, `run`, `clean`, `qualification`, `drawio` | | divers |

Sous Windows, les tests passent par Docker (`developer/docker_tests/run_tests.ps1
invoke test-unit`) car les outils de protection du poste prennent Chrome et les
centaines de processus Python pour une attaque. Le conteneur est construit par
`developer/docker_tests/Dockerfile` (Python 3.10, git, libtidy, gcc, navigateur,
certificats d'un proxy TLS). L'image est construite pour amd64 seulement ;
`run_tests.ps1` garde les environnements uv dans le volume Docker
`strictdoc-tests-build`. La prise en charge d'arm64 et le montage d'un disque
amovible ont été retirés (annulation du commit `e45fcba42`) : l'arbre de
travail doit se trouver sur un disque fixe.

## Les quatre niveaux de test

| Niveau | Dossier | Outil | Nombre | Quand l'utiliser |
|---|---|---|---|---|
| Unitaire | `tests/unit/strictdoc/...` (miroir du paquet) | pytest, pyfakefs | environ 161 fichiers `test_*.py` | logique pure, fonctions |
| Unitaire serveur | `tests/unit_server/strictdoc/server` | pytest, `fastapi.testclient.TestClient` (httpx) | 41 fichiers `test_*.py` | routes et middlewares sans navigateur |
| Intégration | `tests/integration/**/*.itest` | LIT + FileCheck | environ 570 | commandes CLI, formats, exports |
| End2end | `tests/end2end/**/test_*.py` | SeleniumBase (Chrome) | 430 fichiers | comportement du serveur dans un navigateur |
| Screencast | `tests/screencast` | Playwright | | vidéos de documentation |

La règle du dépôt : une nouvelle fonction demande **au moins un test
d'intégration ou end2end**. Pas de test jetable : un contrôle utile devient un
vrai test.

### Intégration (LIT)

Un dossier de test contient un `test.itest` et ses entrées. `tests/integration/lit.cfg.py`
définit les substitutions :

```
RUN: %strictdoc export %S --output-dir %T | filecheck %s --dump-input=fail
CHECK: Export completed.
RUN: %cat %T/html/%THIS_TEST_FOLDER/input.html | filecheck %s --check-prefix CHECK-HTML
```

`%strictdoc` est `python -m strictdoc.cli.main`, `%S` le dossier du test, `%T` un
dossier de sortie, `%cat`, `%cp`, `%mkdir`, `%rm`, `%touch`, `%diff`,
`%expect_exit`, `%chromedriver` sont des aides portables (`tests/integration/*.py`). L'exécution interne
de LIT (lit 18.1.8) est utilisée. Un test de l'export HTML valide aussi la
conformité avec `pytidylib`. Les tests PDF demandent Chrome (`--html2pdf`).
Arborescence : tout est sous `tests/integration/features/<sujet>/` (html, markdown, reqif, excel, docx, json,
spdx, source_code_traceability, ...), dont `commands/<commande>/`, `deprecations` et `options` ;
`tests/integration/self_testing` est à côté.

### End2end (Selenium)

`tests/end2end/` :

| Élément | Rôle |
|---|---|
| `conftest.py`, `e2e_case.py` | `E2ECase` (SeleniumBase `BaseCase`) avec relance sur `ERR_CONNECTION_REFUSED` |
| `server.py` | `SDocTestServer` : lance `strictdoc server` en sous-processus sur un port libre, lit sa sortie d'erreur, l'arrête proprement (psutil) |
| `end2end_test_setup.py` | `End2EndTestSetup` : copie le dossier `input/` dans un bac à sable, compare à `expected_output/` |
| `helpers/screens/...`, `helpers/components/...` | objets de page (`Screen_ProjectIndex`, `Form_EditGrammarElements`, `Node`, ...) |
| `helpers/document_fixtures.py` | génère de gros documents |
| `screens/<écran>/<cas>/test_case.py` | un cas par dossier avec `input/` et parfois `expected_output/` |
| `cli_options`, `navigation`, `performance`, `project_options`, `stable_url_links`, `static_html_search` | autres familles |

Bac à sable et `.gitignore` : un test qui contient un dépôt Git n'est pas suivi
(`chore: do not track the sandbox of an end-to-end test that holds a repository`).

## Qualité statique

| Outil | Configuration | Remarque |
|---|---|---|
| ruff format | `ruff.toml` (`line-length = 80`, `target-version = "py38"`, cache `build/ruff_cache`) | |
| ruff | `ruff.toml` `[lint] select = [A, ARG, B, C, C4, D, EXE, ERA, F, G, I, ISC, ICN, PGH, PL, Q, ...]` | |
| mypy | `mypy.ini` (cache `build/mypy_cache`) | annotations exigées pour tout code nouveau |
| fixit | `developer/fixit/check_comments.py`, `check_docstrings.py` (activés dans `pyproject.toml`) | règles de commentaires |
| jsbeautifier | `lint-format-js` | style des scripts JS |
| `developer/git/commit_validator.py` | `lint-commit` | types de commit : `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `release`, `test` |

Marqueurs de traçabilité : les fichiers de code portent `@relation(SDOC-SRS-n,
scope=file|class|function|line|range_start|range_end)`. StrictDoc s'applique
à lui-même sa traçabilité (`strictdoc_config.py` active
`REQUIREMENT_TO_SOURCE_TRACEABILITY` et déclare les chemins source) ; `invoke
docs` produit le site de documentation avec ces liens.

## CI (`.github/workflows/`)

| Workflow | Contenu |
|---|---|
| `ci-linux-ubuntu-latest.yml` | Python 3.10 et 3.12 ; `invoke lint`, puis `invoke test` ou `invoke test-integration --html2pdf` (deux groupes) |
| `ci-mac.yml`, `ci-windows.yml`, `ci-windows-powershell.yml` | autres plateformes |
| `end2end-tests.yml` | Selenium |
| `screencast-tests.yml` | vidéos |
| `codeql-analysis.yml`, `dead_links.yml` | sécurité et liens |
| `docker.yml`, `release.yml` | image et publication |
| `periodic-integration-test.yml`, `periodic-release-test.yml` | tests périodiques |

Le fork est hébergé sur un GitLab interne (`origin`) ; ces workflows sont ceux de
l'amont GitHub. Les scripts de déploiement et de test du fork vivent hors du
dépôt (`~/DEV/TOOLS/STRICTDOC/strictdoc-deploy`, `strictdoc-dev`), voir
`HISTORY.md`.

## Distribution

| Forme | Source |
|---|---|
| Paquet PyPI | hatchling ; `[tool.hatch.build]` exclut `/developer` ; sdist et wheel n'incluent que `/strictdoc/` et les fichiers de licence |
| Exécutable PyInstaller | `invoke release-pyinstaller` ; options de données `get_pyinstaller_html_template_data_options` et `..._static_data_options` ; hooks dans `developer/pyinstaller_hooks/` (`html2pdf4doc`, `spdx_tools`, `yaml`) |
| Exécutable Nuitka | `invoke nuitka` |
| Image Docker | `Dockerfile` (Ubuntu 24.04, Chrome, installe StrictDoc depuis PyPI ou Git, `entrypoint.sh` règle l'UID) |
| Snap | `developer/snap/snapcraft.yaml` |
| Nix | `flake.nix`, `bootstrap_nix.sh` |

Dans un exécutable, les templates et fichiers statiques ne sont plus dans
l'arborescence du paquet : `core/environment.py` renvoie alors `templates/html`
et `_static` (`BINARY_HTML_TEMPLATES_DIR`, `BINARY_HTML_STATIC_DIR`). Toute
nouvelle feature avec templates doit aussi être ajoutée aux options de
données PyInstaller et Nuitka de `tasks.py`.

## Documentation et exigences

| Chemin | Contenu |
|---|---|
| `docs/strictdoc_01_user_guide.md` | guide utilisateur |
| `docs/strictdoc_02_feature_map.md`, `03_faq`, `05_troubleshooting` | |
| `docs/strictdoc_04_release_notes.md` | notes de version (mettre à jour pour chaque changement visible) |
| `docs/strictdoc_10_contributing.md`, `11_developer_guide.sdoc` | contribution et **guide du développeur (SDG), lecture seule pour les agents** |
| `docs/strictdoc_20_l1_system_requirements.md`, `21_l2_high_level_...`, `22_l3_low_level_...` | exigences de StrictDoc (préfixes `SDOC-SSS-`, `SDOC-SRS-`, `SDOC-LLR-`) |
| `docs/strictdoc_24_development_plan.md`, `25_design`, `28_Backlog`, `40_DO178`, `41_Zephyr` | plans et profils |
| `spec/Markdown.md`, `spec/Markdown.gra.md`, `spec/Formatting.md` | spécification du format Markdown |
| `developer/tasks/<date>_<sujet>/task.md` | tâches de développement (amont) |
| `developer/design/*.md` | plans du fork |
