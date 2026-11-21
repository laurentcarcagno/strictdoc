# 12 - Conventions, workflow et recettes

Sources : `CLAUDE.md`, `AGENTS.md`, `docs/strictdoc_11_developer_guide.sdoc` (SDG,
**lecture seule**), `developer/skills/`, `developer/tasks/`.

## Règles pour un agent

1. Première sortie texte d'une session : la déclaration de conformité à
   `AGENTS.md` et au SDG. Avant tout appel d'outil.
2. Suivre le SDG pour tout le code et la rédaction. En cas de doute ou d'écart :
   le SDG fait foi, et on signale l'écart.
3. Ne pas inventer d'exigence. Demander quand un détail change le comportement,
   l'interface, la sécurité, la portée ou ce que voit l'utilisateur.
4. Rester dans la portée : demander avant de supprimer des fichiers, de changer
   une interface publique ou de lancer un grand refactoring.
5. **Composants partagés** : ne pas les modifier pour une fonction locale sans
   accord. Préférer des templates, scripts et styles propres à la feature. Si
   un changement partagé paraît nécessaire, s'arrêter et demander.
6. `developer/tasks/<tâche>/` : ne modifier que `Context.md` (mémoire de travail
   partagée avec d'autres agents, pas source de vérité). Le lire avant tout
   travail important, le créer s'il manque, le tenir à jour.
7. Tests : préférer `invoke test-*`. Toujours `--headless` pour end2end. Sous
   Windows, dans Docker (`developer/docker_tests/run_tests.ps1`). Pas de test
   jetable.
8. Prose écrite dans le dépôt (commits, PR, docs, commentaires, fichiers de
   tâche) : appliquer `developer/skills/humanizer/SKILL.md`.
9. Compétences : `developer/skills/<nom>/SKILL.md` (`asd-ste100`, `crystal`,
   `humanizer`, `technical-writing-guide`). Après modification, lancer
   `python developer/skills/install_skills.py` pour régénérer les pointeurs
   Claude et Codex (ignorés par Git).
10. Revue de code : juger contre le SDG et signaler tout écart.

## Conventions de code (SDG)

| Règle | Détail |
|---|---|
| Python | 3.10 minimum, le plus bas possible compte tenu des dépendances |
| Longueur de ligne | 80 pour le code ; un littéral long devient multiligne |
| Types | annotations sur tout code nouveau (mypy) |
| Ordre | style journal : fonctions publiques au-dessus des privées (préfixe `_`) |
| Noms | complets (`document`, pas `doc` ; `buffer`, pas `buf` ; `length`, pas `len`) |
| Variables temporaires | boucles et lambdas : suffixe `_` (`for item_ in items`) |
| Tests de valeur | `if foo is not None`, jamais `if foo` ; chaîne non vide : `if foo is not None and len(foo) > 0` |
| Fichiers | `file_open_read_utf8`, `file_open_read_bytes` (retirent le BOM), pas `open()` |
| Traçabilité | marqueurs `@relation(SDOC-..., scope=...)` dans le code vers `docs/` et `spec/` |
| Documentation | chaque changement de fonction ou d'infrastructure est documenté ; lignes de 80 caractères |
| Notes de version | `docs/strictdoc_04_release_notes.md`, section « Unreleased », phrase d'ouverture `This release contains the following enhancements:`, seulement les `feat:` et `fix:` visibles, ne pas toucher aux versions passées, ignorer `CHANGELOG.md` |

## Git

- Un commit autonome par PR. Plusieurs commits : chacun autonome et qui passe
  `invoke check`.
- Réécrire avec `git rebase` sur `main`, ne pas fusionner `main` dans la branche.
- Message : Conventional Commits, `<type>(<portée>): <description>`.
  Types : `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `release`,
  `test` (vérifié par `invoke lint-commit`). Portée : dossier ou fonction
  (`feat(html2pdf):`, `fix(backend/docx):`). Plusieurs portées séparées par une
  virgule.
- Fork : `develop` est la branche de référence (elle suit `fork/develop`) ; les
  travaux se font sur des branches `feature/<sujet>` créées depuis elle ; pousser
  sur `origin` et `fork`, jamais sur l'amont, et garder les deux remotes dans le
  même état ; les branches `feature/isis-release` et `feature/isis-integration`
  ont été supprimées le 2026-11-20 (leur contenu est dans `develop`) ; le
  clone ne doit pas être superficiel (GitLab refuse) ; auteur unique des
  commits, sans ligne `Co-Authored-By` (règles de `HISTORY.md`).

## Exigences de StrictDoc lui-même

Trois niveaux (QUOI/POURQUOI/COMMENT) dans `docs/` :

| Niveau | Fichier | Préfixe | Contenu |
|---|---|---|---|
| L1 (pourquoi) | `strictdoc_20_l1_system_requirements.md` | `SDOC-SSS-` | besoins envers « un outil d'exigences », sans référence à StrictDoc |
| L2 (quoi) | `strictdoc_21_l2_high_level_requirements.md` | `SDOC-SRS-` | exigences de haut niveau envers StrictDoc, organisées par fonction (*Feature*) et capacité |
| L3 (comment) | `strictdoc_22_l3_low_level_requirements.md` | `SDOC-LLR-` | exigences de bas niveau par composant logiciel |

Objectif : traçabilité bidirectionnelle complète L1, L2, L3, puis code et
tests. Une exigence se retrouve dans le code par un marqueur
`@relation(SDOC-SRS-n, scope=...)` ; `grep -rn "SDOC-SRS-126" strictdoc` donne
l'implémentation (par exemple 126 = serveur web, 155 = recherche, 119 =
abstractions `Format` et `Feature`).

## Tâches (`developer/tasks/<date>_<sujet>/`)

Un dossier par tâche, avec `task.md` (WHY, WHAT, HOW, statut) et un `Context.md`
facultatif écrit par l'agent. Les tâches datées avant 2026-10-09 viennent de
l'amont (`Format`, `Feature`, `convert`, `api_layer`, table, TOC, Markdown, nœud
et type de nœud, `stimulus_free`, ...). Celles qui suivent concernent le fork
(`20261012_hemeria_ui`, `20261031_milkdown_diagram_editor_maxgraph`). Les plans de fonctions du fork sont à part
dans `developer/design/`.

## Pièges connus

| Piège | Conséquence | Voir |
|---|---|---|
| Route sans entrée dans `ROUTE_ROLES` | le serveur refuse de démarrer | [05](05-serveur-web.md) |
| `HTML_TEMPLATE_DIRS` ou `HTML_STATIC_DIRS` oubliés | `TemplateNotFound` ou ressource absente de l'export | [04](04-core-index-et-tracabilite.md) |
| Options de données PyInstaller ou Nuitka oubliées | exécutable sans les templates de la feature | [11](11-tests-qualite-build.md) |
| `export_action.traceability_index` copié dans une variable locale à long terme | l'index est réaffecté à chaque reconstruction (`--watch`, rechargements) : lire à chaque requête | [05](05-serveur-web.md) |
| Objets textX dans un pickle ou entre processus | échec ; appeler `drop_textx_meta` et garder les classes de modèle sans état textX | [02](02-modele-sdoc-et-grammaire.md) |
| Rendu Jinja dans un processus fils | `PicklingError` : l'arbre du projet est exporté **après** l'export parallèle des documents | `html_generator.py` |
| `ProjectConfig` non picklable (lambda, objet de socket) | le serveur ne démarre plus : la configuration passe par un fichier pickle | [05](05-serveur-web.md), [10](10-donnees-et-persistance.md) |
| Ouvrir un verrou fin en tenant déjà un verrou global | blocage : le gestionnaire n'est pas réentrant | [05](05-serveur-web.md) |
| Écrire un document sans passer par `write_document_to_file` | l'observateur recharge, Git ne commite pas, la révision n'avance pas | [05](05-serveur-web.md) |
| Modifier `developer/milkdown/src` sans reconstruire le bundle | l'interface ne change pas | [06](06-frontend-et-export-html.md) |
| Changer le schéma de classes de modèle sans vider le cache | `pickle_load` renvoie `None` (relecture, sans erreur) ; vider `output/_cache` si un comportement étrange persiste | [10](10-donnees-et-persistance.md) |
| Page HTML écrite à la main dans une route de feature | hors du cadre du projet : ni barre latérale, ni en-tête ; utiliser `render_app_screen` | [06](06-frontend-et-export-html.md) |
| Nouvelle action réservée à un rôle, absente de `GATED` dans `role_gating.js` | le bouton reste actif pour un rôle trop faible (le serveur refuse quand même, 403) | [08](08-features-fork-isis.md) |
| Nouvel écran de feature sans entrée dans un groupe de `nav.jinja.html` | écran sans lien dans la barre latérale | [06](06-frontend-et-export-html.md) |
| Ajouter un texte d'interface sans le traduire | reste en anglais en `fr` | [06](06-frontend-et-export-html.md) |
| Fournisseur LLM cloud sans `allow_cloud` | refusé (403) | [09](09-assistant-llm-et-kb.md) |
| `deploy.sh up` sans les options `--projects --llm-relay --kb` | relais supprimés, l'assistant répond 405 | `HISTORY.md` |

## Recettes

### Ajouter un champ de configuration

1. Paramètre et attribut dans `ProjectConfig.__init__` (`core/project_config.py`).
2. Validation dans `validate_and_finalize`.
3. Si elle vient du TOML (obsolète) : `_load_from_dictionary`. Ne pas en
   ajouter pour du nouveau code : le format est déprécié.
4. Méthode `is_activated_*` si c'est une fonction (`ProjectFeature`).
5. Documentation (`strictdoc_01_user_guide.md`) et test d'intégration.

### Ajouter une option de commande

Voir [01](01-cli-et-commandes.md) : `add_arguments`, `<Nom>CommandConfig`, test
dans `tests/integration/features/commands/`.

### Ajouter un format

Voir [03](03-formats-et-backends.md) : sous-classe de `Format`, ajout à
`default_formats()`, drapeaux d'import par `add_import_arguments`, tests
`tests/integration/features/<format>/`.

### Ajouter un type de champ ou un élément de grammaire

1. Grammaire textX (`backend/sdoc/grammar/*.py`) et classe de modèle
   (`backend/sdoc/models/grammar_element.py`), enregistrement dans
   `models/constants.py`.
2. Validation (`validations/sdoc_validator.py`), écriture (`writer.py`).
3. Formulaire (`RequirementFormObject`, `GrammarElementFormObject`) et templates
   `components/form/field/*`.
4. Autres writers : Markdown, ReqIF, Excel, DOCX, JSON.
5. Tests : unitaires du backend et intégration d'export.

### Ajouter une feature (écran ou action)

1. Dossier `strictdoc/features/<nom>/` : `templates/features/<nom>/`,
   `assets/<nom>/`, code Python.
2. Ajouter `templates` à `HTML_TEMPLATE_DIRS` et `assets` à `HTML_STATIC_DIRS`
   (`core/environment.py`) et aux options de données de `tasks.py` pour les
   exécutables.
3. Valeur de `ProjectFeature` et `is_activated_<nom>()` si l'utilisateur doit
   pouvoir l'activer, ou une classe `Feature` ([04](04-core-index-et-tracabilite.md)).
4. Routes : `create_<nom>_routers(context)` renvoyant `(read_router,
   write_router)`, inclus dans `create_main_router`, entrées dans `ROUTE_ROLES`.
5. Écran : un objet vue et un template qui hérite de `base.jinja.html` ; réponse
   412 si la fonction n'est pas activée.
6. Test d'intégration ou end2end, ligne dans `docs/strictdoc_02_feature_map.md`
   et dans les notes de version.

### Ajouter un écran de feature dans le cadre du projet

1. Un template de contenu `features/<nom>/templates/features/<nom>/<page>.jinja.html`
   (le contenu seulement, sans `extends`).
2. Dans la route : `render_app_screen(jinja_environment=context.env(),
   project_config=..., title=gettext("..."), viewtype="<nom>", content_template=...,
   **variables)` puis `HTMLResponse`.
3. Une entrée dans le bon groupe de `export/html/templates/_shared/nav.jinja.html`
   (le `data-viewtype` du corps marque l'entrée courante).
4. La route dans `ROUTE_ROLES`, le template dans les dossiers de
   `HTML_TEMPLATE_DIRS`, les textes dans le catalogue `fr`.
5. Un test end2end sous `tests/end2end/navigation/` ou `tests/end2end/screens/`.

Modèle à suivre : `features/item_page/router.py`.

### Modifier un écran existant

Template dans `export/html/templates/` ou la feature, méthode de l'objet vue,
éventuellement un `RequirementFormObject`. Si la modification concerne une feature
du fork, rester dans `features/<nom>/` (règle des composants partagés).

### Ajouter un texte traduit

`{% trans %}` ou `_()` dans le template, `gettext()` dans le code,
`window.sdocT()` dans le JS ; puis `python developer/i18n/update_catalogs.py` et
la traduction dans `features/i18n/locales/fr/LC_MESSAGES/strictdoc.po`.

### Ajouter un outil de la base de connaissances

Seuls les outils de `READ_ONLY_TOOLS` (`features/kb/config.py`) sont acceptés. La
liste vient du serveur MCP, qui est dans le dépôt `kb-platform`. Ajouter l'outil
là-bas, puis à `READ_ONLY_TOOLS` et `DEFAULT_TOOLS`, puis une consigne dans
`features/llm/prompts/kb_gather.md` (incrémenter sa version).

### Ajouter une commande à l'assistant

Une entrée `Command(...)` dans `assist/commands.py` (portée, rôle minimal, type de
sortie, fichier de prompt), un `prompts/<nom>.md` commençant par `version: 1`,
un convertisseur dans `assist/converters.py`, des cas dans
`assist/golden.py`, des tests dans `tests/unit/strictdoc/features/llm` et `llm_assist`.
