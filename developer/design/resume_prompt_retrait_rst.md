# Prompt de reprise : retrait de RST dans le fork StrictDoc

Coller le texte ci-dessous au début d'une nouvelle session, à la racine du dépôt
`/home/laurent/DEV/TOOLS/STRICTDOC/strictdoc`.

---

Tu reprends un chantier sur le fork ISIS de StrictDoc (dépôt
`/home/laurent/DEV/TOOLS/STRICTDOC/strictdoc`, version 0.30.2 plus le fork). Réponds en français.

## Règles à suivre avant tout

1. `AGENTS.md` impose que ton tout premier texte de la session soit une déclaration de conformité à
   `AGENTS.md` et au guide du développeur (`docs/strictdoc_11_developer_guide.sdoc`, en lecture
   seule). Écris-la avant tout appel d'outil.
2. Lis `CLAUDE.md` puis `architecture/INDEX.md` (documents d'architecture écrits pour toi, en français ;
   lis un seul document à la fois).
3. Tout texte écrit dans le dépôt (docs, commits, commentaires) passe par
   `developer/skills/humanizer/SKILL.md`.
4. Ne modifie pas les composants partagés pour une fonction locale sans accord. Ne modifie pas
   `developer/tasks/<tâche>/` sauf `Context.md`.
5. Tests : utilise `invoke test-*`, toujours `--headless` pour end2end.
6. Messages de commit : Conventional Commits (`type(portée): description`), un commit autonome qui
   passe `invoke check`, rebase plutôt que merge. Aucune ligne `Co-Authored-By`.
7. Git n'a pas d'identité globale. Pour commiter, utilise seulement pour la commande :
   `git -c user.name="Laurent Carcagno" -c user.email="laurent.carcagno@hemeria-group.com" commit ...`
   Ne modifie pas la configuration Git.
8. Ne pousse jamais vers l'amont strictdoc-project. Tu peux pousser sur `origin` (GitLab) et `fork`
   (GitHub), et les deux doivent rester dans le même état. Ne pousse, ne supprime de branche et ne
   commite rien sans demande explicite de l'utilisateur.
9. Le suivi de travail est `.claude/sprints.json` (ignoré par Git). Mets-le à jour dès qu'une tâche
   démarre (`doing`) ou se termine (`done`, avec un `summary` de 2 à 5 lignes).

## État du dépôt (au 2026-11-20)

- Branches locales : `develop`, `feature/refactor-ui`, `main`. Sur `origin` et `fork` : `develop`,
  `feature/refactor-ui` et `main` (identiques sur les deux). `develop` est à `89e41acee` et suit
  `fork/develop`, c'est la branche de référence. `feature/refactor-ui` est en avance sur `develop` des
  commits qui ajoutent ce plan et ce prompt ; `develop` n'a volontairement pas été mise à jour.
- Les branches `feature/isis-release` et `feature/isis-integration` ont été supprimées (local, `origin`,
  `fork`). `main` reste la copie de l'amont à `cc8be7913`.
- `refs/remotes/upstream/main` est une référence locale vers l'amont (e43af1a97, version 0.31.0, sans
  remote configuré). Pour la rafraîchir : `git fetch --no-tags https://github.com/strictdoc-project/strictdoc.git main:refs/remotes/upstream/main`.
- Fichier non suivi (non commité) : `HISTORY.md`.
- Le dossier `architecture/` (13 documents plus `INDEX.md`) est commité. Les chemins et noms qu'il
  cite ont été vérifiés par script.
- Mémoire de projet : `~/.claude/projects/-home-laurent-DEV-TOOLS-STRICTDOC-strictdoc/memory/`.

## Le chantier : ne conserver que Markdown

L'utilisateur veut supprimer RST de StrictDoc : (A) l'export RST (`--formats=rst`) et (B) le balisage RST
des champs (`MARKUP: RST`, qui est aussi le défaut actuel). Le balisage Text est retiré aussi. Il reste
Markdown et HTML. Le conteneur `.sdoc` est conservé.

**Le plan est figé et validé : `developer/design/plan_retrait_rst.md`.** Lis-le en entier avant d'agir.
Il contient : décisions retenues, ordre d'exécution, estimation (environ 94 jours, 85 tâches), préalables,
tâches transverses, détail de chaque tâche.

Ordre : préalables, phase 1 (export RST), phase 2 (alternatives HTML, P2-00 d'abord), phase 3
(convertisseur), migration des contenus, phase 4 (retrait du code RST et Text), phase 5 (écrire un plan
de passage au `.md` natif). Aucune suppression de RST avant que le dépôt n'ait plus aucun document RST.

Décisions qui orientent le travail :
- `MARKUP` devient facultatif, Markdown est implicite, `MARKUP: Markdown` est accepté et ignoré, le
  script de conversion ne l'écrit pas. Le détecteur de contenu RST résiduel (P4-13) avertit à la lecture.
- Retrait direct, sans période de dépréciation. P4-01 et P4-12 sont supprimées.
- Convertisseur : script jetable `developer/tools/rst_to_markdown.py` (pas de commande `manage`), visiteur
  docutils maison, supprimé avec docutils en phase 4 (il reste dans l'étiquette `pre-markdown-only`).
- Tableaux convertis toujours en HTML ; encadrés en bloc HTML `sdoc-admonition` (nœud WYSIWYG dans
  l'éditeur Milkdown, effort L) ; liste blanche de balises HTML ; export Word : style « Note » ou
  « Avertissement » du modèle.
- Divergence assumée avec l'amont : plus de fusion globale, cherry-pick des correctifs utiles
  (`e9183ab39`, `b9163da37`, `b74372e08`, correctifs ReqIF et Excel).
- Q-08 : annuler le commit `e45fcba42` en entier (arm64 et montage du disque amovible).

## Préalables (déduits des décisions, à valider avec l'utilisateur)

PRE-1 branche `feature/markdown-only` depuis `develop` et étiquette `pre-markdown-only` ; PRE-2 retrait
arm64 (Q-08) ; PRE-3 renuméroter nos SDOC-SRS-208 à 216, qui entrent en collision avec l'amont
(widgets, Ada, Modelica, annulation, alignement de tables) ; PRE-4 cherry-pick des correctifs amont ;
PRE-5 mesures de référence (export HTML de REQ_02 et de `docs/`) ; PRE-6 inventaire des projets réels.

**Ne commence pas le travail sans l'accord de l'utilisateur.** Demande-lui s'il veut commencer par PRE-1 et
PRE-2, puis travaille tâche par tâche.

## Faits utiles déjà établis

- Données réelles : `~/strictdoc-data` contient REQ_02 (PUS 18, OBAP), déjà `MARKUP: Markdown`, sans
  directive RST ; son profil Word `word/req02_profile.py` a déjà `markup="Markdown"`. Le travail pèse sur
  StrictDoc lui-même : 15 documents de `docs/` en RST implicite, 94 `.sdoc` avec directives, environ
  1 770 `.sdoc` de tests sans balisage déclaré, 3 en `MARKUP: Text`, 11 en `MARKUP: HTML`.
- Usage RST dans les `.sdoc` du dépôt : `.. code::` 208, `.. image::` 98 (14 avec joker `.*`),
  `.. note::` 51, `.. code-block::` 41, `.. math::` 24, `.. list-table::` 23, `.. raw::` 16,
  `.. warning::` 8, `.. admonition::` 5, `.. csv-table::` 2 ; rôles `:code:` 14, `:eq:` 7, `:math:` 5 ;
  aucune note de bas de page ni tableau en grille.
- Le réglage `syntax_highlight_opts` de StrictDoc n'a aucun effet (vérifié avec docutils 0.23) : les
  numéros de ligne n'existent que pour `:number-lines:`, dans un seul fichier.
- Le drapeau MATHJAX n'a déjà plus d'effet (`is_activated_mathjax()` renvoie toujours vrai).
- Le lexeur `strictdoc_lexer.py` (dans `backend/rst`) colore aussi la syntaxe `sdoc` des blocs de code
  Markdown : le déplacer avant de supprimer le paquet.
- La conversion change le texte des exigences : tous les liens suspects (empreinte du contenu) et les
  barres de changement du PDF seraient touchés ; d'où l'étiquette de version avant et le recalcul de la
  ligne de base après (P3-15).
- Toute nouvelle route doit figurer dans `ROUTE_ROLES` (`strictdoc/features/roles/route_roles.py`), sinon
  le serveur ne démarre pas.
- Après tout changement de `developer/milkdown/src`, reconstruire et commiter le bundle de
  `strictdoc/features/milkdown/assets/milkdown/`.

## Environnement

- Pas d'`uv` sur la machine, pas de navigateur Chrome pour Playwright, Node 22 disponible.
- Un environnement `docutils` 0.23 et `pygments` 2.21.0 avait été créé dans le dossier temporaire de la
  session précédente. Il a peut-être disparu : recrée-en un avec `python3 -m venv` si besoin.

## Comment travailler avec l'utilisateur

Il aime les réponses courtes en français, des décisions présentées avec une recommandation, et valide par
formulaire quand un plan est long. Dis ce que tu n'as pas vérifié. Quand un point change le plan, mets à
jour `plan_retrait_rst.md` et `.claude/sprints.json`.
