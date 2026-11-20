# Plan de retrait de RST

Plan figé le 2026-11-20, révision 2, validé par l'utilisateur (97 tâches : 96 validées, 1 à discuter, tranchée ci-dessous).

## 1. Objectif

Ne conserver que le balisage Markdown (et HTML) dans StrictDoc. Cela couvre deux chantiers :

- le cas A, retirer l'export RST (`--formats=rst`) ;
- le cas B, retirer le balisage RST des champs (`MARKUP: RST`, qui est aussi le défaut actuel), avec un convertisseur RST vers Markdown, des alternatives HTML pour les fonctions que Markdown n'a pas, et la migration des contenus.

Le balisage Text est retiré aussi (C-03). Le conteneur `.sdoc` reste ; un plan de passage au `.md` natif est le dernier livrable (P5-01).

## 2. Décisions retenues

| Tâche | Sujet | Décision |
|---|---|---|
| C-01 | Ordre des phases | Export RST d'abord, balisage ensuite (ordre ci-dessus) |
| C-03 | Balisages conservés | Markdown et HTML |
| C-04 | Conteneur des documents | Garder .sdoc avec MARKUP: Markdown ; commentaire : « On commence par garder .SDOC avec MARKUP mais tu ajouteras à la fin du plan un tache pour ecrire un plan de  passage au markdown natif avec des conseils pour le faire. » |
| C-05 | Balisage par défaut après retrait, et utilité de l'option MARKUP | MARKUP facultatif, Markdown implicite. La clé ne sert que pour HTML ; MARKUP: Markdown reste accepté et ignoré ; le script ne l'écrit pas ; commentaire : « Il n'y aura plus d'autre format que matkdown, cette fonction teste-t'elle utile ? » |
| C-06 | Période de dépréciation | Retrait direct |
| C-07 | Politique vis-à-vis de l'amont | Divergence assumée : plus de fusion globale, cherry-pick des correctifs utiles |
| P1-01 | Retirer le format rst de la CLI et de la configuration | Erreur claire : « le format rst a été retiré » |
| P1-06 | Alternative pour qui utilisait Sphinx | Aucune documentation |
| P2-00 | Étude préalable : l'éditeur Milkdown garde-t-il le HTML ? | Faire l'étude avant toute autre tâche de cette phase |
| P2-01 | Politique de sécurité du HTML brut | Liste blanche de balises et d'attributs, comme pour les SVG |
| P2-10 | Encadrés : note, warning, tip, important, caution, danger, attention, hint, error, admonition | Bloc HTML avec classes sdoc-admonition |
| P2-11 | Notes de bas de page et citations | Ancre [ANCHOR: fn-1, "1"] et lien [LINK: fn-1] |
| P2-12 | Listes de définitions | Balises dl, dt, dd |
| P2-13 | Rôles RST en ligne | Équation numérotée écrite \tag{n} dans $$…$$, renvoi remplacé par le numéro en texte |
| P2-14 | Numéros de ligne dans les blocs de code | Accepter la perte (Markdown n'en a pas) |
| P2-16 | Blocs de mise en page : epigraph, pull-quote, rubric, sidebar, topic, container, compound | Correspondance minimale par classes |
| P2-20 | Export Word des éléments HTML | Encadré = paragraphe avec style Word « Note » ou « Avertissement » du modèle |
| P3-02 | Moteur de conversion | Visiteur docutils maison |
| P3-03 | Dépendance docutils pendant et après la migration | Convertisseur supprimé avec docutils après la migration |
| P3-07 | Règles : tableaux | Toujours en HTML |
| P3-08 | Règles : csv-table | Supprimer le CSV converti |
| P3-09 | Règles : images | Résoudre le joker vers l'extension réelle trouvée dans _assets (SVG, sinon PNG) |
| P3-11 | Que faire d'une construction non convertible | Repli HTML sinon commentaire, avec avertissement ; --strict fait échouer |
| P3-15 | Effets de la conversion sur les liens suspects, les PDF et les comparaisons | Étiquette de version avant ; recalcul de la ligne de base juste après la conversion |
| P4-07 | Validation à l'enregistrement | Aucune validation de syntaxe |
| P4-08 | Fonction MATHJAX | Retrait net : une configuration qui liste MATHJAX échoue |
| P4-13 | Détecteur de contenu RST résiduel | Avertissement à la lecture |
| M-02 | Convertir la documentation de StrictDoc | Convertir sur place |
| F-01 | Contrat de format entre convertisseur et éditeur Milkdown | Accepter la réécriture en tableau à barres à la première édition |
| Q-02 | Référence de rendu avant et après | Comparaison automatique du texte visible |
| Q-06 | CI, packaging et durée (arm64 retiré) | commentaire : « Supprimer la version arm64 » |
| R-05 | Arrêt et retour en arrière | Seuil de 5 % |
| Q-08 | Retirer la prise en charge d'arm64 des tests Docker | Annuler le commit `e45fcba42` en entier : arm64 et montage du disque amovible. Commentaire : « On ne doit plus utiliser le disque amovible ». |
| P4-01, P4-12 | Avertissement de dépréciation, erreur finale | Tâches supprimées (sans objet depuis C-06) |

## 3. Ordre d'exécution

Une demande de fusion par étape, un commit autonome qui passe `invoke check` (guide du développeur). Aucune suppression de RST avant que le dépôt n'ait plus aucun document en RST (M-06).

| Étape | Contenu | Condition de sortie |
|---|---|---|
| Préalables | PRE-1 à PRE-6 | branche et étiquette créées, numérotation corrigée, références mesurées |
| Phase 1 | retrait de l'export RST (P1-01 à P1-07) | `--formats=rst` donne une erreur claire, suites vertes |
| Phase 2 | alternatives HTML (P2-00 d'abord, puis P2-01, P2-02, P2-10 à P2-23) | P2-00 conclut que l'éditeur garde le HTML ; encadrés rendus en HTML, PDF et Word |
| Phase 3 | convertisseur et sa vérification (P3-01 à P3-18) | moins de 5 % de champs divergents sur le corpus (R-05) |
| Migration | M-01 à M-07 | plus aucun `MARKUP: RST` ni `MARKUP: Text` dans le dépôt, `invoke docs` OK |
| Phase 4 | retrait du balisage RST et Text du code (P4-02 à P4-14, sauf P4-01 et P4-12) | critères de fin C-09 |
| Phase 5 | plan de passage au Markdown natif (P5-01) | document `developer/design/plan_markdown_natif.md` écrit |

Tâches transverses, à placer au bon moment : voir la section 6.

## 4. Estimation

Ordres de grandeur pour une personne : S 0,5 j, M 1,5 j, L 4 j. Les tâches de cadrage et les notes de risque sont des décisions, pas du travail, donc non comptées.

| Ensemble | Tâches | Jours |
|---|---|---|
| Préalables | 6 | 4,0 |
| Phase 1 | 7 | 5,5 |
| Phase 2 | 16 | 19,0 |
| Phase 3 | 18 | 28,0 |
| Migration des contenus | 7 | 12,5 |
| Phase 4 | 12 | 9,0 |
| Fonctions du fork | 10 | 7,0 |
| Tests, documentation, CI | 8 | 7,0 |
| Phase 5 | 1 | 1,5 |
| Total | 85 | 93,5 |

## 5. Préalables

Déduits des décisions, absents de la liste des 97 tâches. À valider si vous voulez les changer.

| N° | Tâche | Vient de | Effort |
|---|---|---|---|
| PRE-1 | Créer la branche `feature/markdown-only` depuis `develop` et l'étiquette `pre-markdown-only` | C-08 | S (½ j) |
| PRE-2 | Retirer arm64 et le disque amovible des tests Docker (Q-08) | Q-08 | S (½ j) |
| PRE-3 | Renuméroter les exigences SDOC-SRS-208 à 216 du fork, qui entrent en collision avec l'amont. Fait : elles deviennent SDOC-SRS-1208 à 1216 | Q-03 | S (½ j) |
| PRE-4 | Cherry-pick des correctifs utiles de l'amont : cycles avec rôle (`e9183ab39`), commentaires multiples en Markdown (`b9163da37`), restriction du clone (`b74372e08`), correctifs Excel (`82316b358`) et ReqIF (`c7b1e0879`, `bbbc23f31`, `423475562`). Fait, avec `-x` | C-07 | M (1 à 2 j) |
| PRE-5 | Mesures de référence : export HTML de REQ_02 et de `docs/`, temps d'export | Q-02, Q-07 | S (½ j) |
| PRE-6 | Inventaire des projets réels (M-01), pour confirmer qu'aucun projet RST ne manque | M-01 | S (½ j) |

## 6. Tâches transverses

| Tâche | Titre | Quand |
|---|---|---|
| F-01 | Contrat de format entre convertisseur et éditeur Milkdown | Phase 2 après P2-00, vérifié en phase 3 |
| F-02 | Commentaires de relecture | Phase 3 (réécriture des en-têtes), retrait en phase 4 |
| F-03 | Word : import, export et mise à jour | Phase 4 |
| F-04 | Assistant LLM | Phase 4 |
| F-05 | Interface en français | À chaque phase |
| F-06 | Rôles et routes | Seulement si une route est ajoutée (aucune prévue) |
| F-07 | Base de connaissances (kb-platform) | Avant M-05 |
| F-08 | Écrans qui rendent des champs | Phase 4, test de bout en bout |
| F-09 | Documentation d'architecture | Fin de la phase 4 |
| F-10 | CLAUDE.md et AGENTS.md | Fin de la phase 4 |
| Q-01 | Stratégie de test par phase | Toutes les phases |
| Q-02 | Référence de rendu avant et après | Référence avant la phase 1, comparaison après chaque phase |
| Q-03 | Exigences et traçabilité | Préalable (renumérotation), puis à chaque phase |
| Q-04 | Guide utilisateur et FAQ | Phases 2 et 4 |
| Q-05 | Notes de version et ruptures | À chaque phase |
| Q-06 | CI, packaging et durée (arm64 retiré) | Phase 4 |
| Q-07 | Mesure de performance | Avant la phase 1 et après la phase 4 |
| Q-08 | Retirer la prise en charge d'arm64 des tests Docker | Préalable, en premier |
| Q-09 | Corriger les tests qui échouent déjà sur `develop` (10 tests d'intégration, 1 unitaire, 1 serveur, liste dans la mémoire du projet) | Quand une phase touche ce qu'un test vérifie, tous avant la fin |

## 7. Détail des tâches

### Cadrage et décisions préalables

#### C-01 Ordre des phases

Effort et risque : effort S (½ j) ; risque faible.

Variante retenue : Export RST d'abord, balisage ensuite (ordre ci-dessus).

Phase 1 : retrait de l'export RST. Phase 2 : alternatives HTML. Phase 3 : convertisseur. Migration des contenus. Phase 4 : retrait du balisage RST du code. Le balisage RST n'est supprimé qu'après la migration complète, pour ne jamais casser un document existant.

#### C-02 Constat sur vos données réelles

Effort et risque : effort S (½ j) ; risque faible ; usage : REQ_02 : 0 directive RST.

Dans `~/strictdoc-data` le document REQ_02 est déjà en `MARKUP: Markdown` : 131 exigences, 23 textes, aucune directive RST, aucun tableau RST. Son profil Word déclare déjà `markup="Markdown"`. Un fichier `.rst.bak` traîne à côté (sauvegarde d'un ancien import).

Le poids du retrait se trouve donc surtout dans StrictDoc lui-même : 15 documents de `docs/` en RST implicite, 94 fichiers `.sdoc` avec directives RST, environ 1 770 `.sdoc` de tests sans balisage déclaré (donc RST par défaut).

Y a-t-il d'autres projets ISIS que REQ_02 écrits en RST ? Dites-le en commentaire ; la tâche M-01 les inventorie.

#### C-03 Balisages conservés

Effort et risque : effort S (½ j) ; risque moyen.

Variante retenue : Markdown et HTML.

« Ne conserver que Markdown » peut vouloir dire Markdown seul, ou Markdown plus les deux balisages simples déjà présents. `HTML` sert à l'import ReqIF XHTML (`--reqif-import-markup HTML`) et `Text` à des rendus internes ; 14 `.sdoc` de tests les utilisent.

#### C-04 Conteneur des documents

Effort et risque : effort S (½ j) ; risque faible.

Variante retenue : Garder .sdoc avec MARKUP: Markdown.

Commentaire : « On commence par garder .SDOC avec MARKUP mais tu ajouteras à la fin du plan un tache pour ecrire un plan de  passage au markdown natif avec des conseils pour le faire. »

Le formulaire d'édition riche (Milkdown) ne s'applique qu'aux champs de contenu d'un document dont le balisage est Markdown. Deux façons de « garder Markdown » : le conteneur `.sdoc` avec `MARKUP: Markdown`, ou des fichiers `.md` natifs. Les deux existent déjà.

#### C-05 Balisage par défaut après retrait, et utilité de l'option MARKUP

Effort et risque : effort M (1 à 2 j) ; risque élevé.

Variante retenue : MARKUP facultatif, Markdown implicite. La clé ne sert que pour HTML ; MARKUP: Markdown reste accepté et ignoré ; le script ne l'écrit pas.

Commentaire : « Il n'y aura plus d'autre format que matkdown, cette fonction teste-t'elle utile ? »

Une fois RST et Text retirés, il reste deux balisages : Markdown et HTML (choix C-03). L'option `MARKUP` ne sert plus qu'à dire « ce document est en HTML », utile à l'import ReqIF XHTML. Écrire `MARKUP: Markdown` dans chaque document n'apporte rien et ajoute du bruit dans environ 1 800 fichiers.

Contrepartie : sans cette ligne, un ancien document RST implicite ne se distingue plus d'un document Markdown. Les parades sont la conversion complète avant le retrait (M-06) et un détecteur de contenu RST résiduel (P4-13).

#### C-06 Période de dépréciation

Effort et risque : effort S (½ j) ; risque moyen.

Variante retenue : Retrait direct.

Vous êtes seul utilisateur de ce fork. Une dépréciation en deux versions protège pourtant le temps de convertir et de relire.

#### C-07 Politique vis-à-vis de l'amont

Effort et risque : effort M (1 à 2 j) ; risque élevé.

Variante retenue : Divergence assumée : plus de fusion globale, cherry-pick des correctifs utiles.

L'amont continue à développer RST : alignement des tableaux en grille, liens dans les tableaux RST, widgets de champ pour RST. Supprimer RST rend ce travail inutile et fait entrer chaque fusion en conflit avec le code retiré.

#### C-08 Branche, étiquette et rythme de livraison

Effort et risque : effort S (½ j) ; risque faible.

Branche `feature/markdown-only` depuis `develop`, une demande de fusion par phase (P1, P2, P3, migration, P4). Étiquette Git `pre-markdown-only` sur `develop` avant la première phase, car la conversion RST vers Markdown est irréversible. Chaque commit passe `invoke check` (règle du guide du développeur).

#### C-09 Critères de fin

Effort et risque : effort S (½ j) ; risque faible.

- Suites unitaires, d'intégration et end2end vertes.

- `invoke docs` produit le site de documentation.

- L'export HTML de REQ_02 est identique, au texte près, avant et après.

- Plus aucun `MARKUP: RST` dans le dépôt, plus de `docutils` à l'exécution.

- Aucune régression de performance sur l'export de `docs/`.

### Phase 1 : retirer l'export RST (cas A)

#### P1-01 Retirer le format rst de la CLI et de la configuration

Effort et risque : effort S (½ j) ; risque faible.

Variante retenue : Erreur claire : « le format rst a été retiré ».

Enlever `"rst"` de `EXPORT_FORMATS`, `RSTFormat()` de `ProjectConfig.default_formats()`, et vérifier que le lanceur graphique (qui importe `EXPORT_FORMATS`) ne propose plus le format.

Fichiers :

- `strictdoc/commands/export.py`
- `strictdoc/core/project_config.py`
- `strictdoc/features/launcher/launcher_frame.py`

#### P1-02 Supprimer le code de l'export RST

Effort et risque : effort S (½ j) ; risque faible.

Supprimer `RSTFormat`, `DocumentRSTGenerator`, `RSTWriter`, `RSTTemplates` et le template `requirement.jinja.rst`. Garder pour l'instant `formatter.py` (utilisé par l'écriture des `.sdoc`), le rendu HTML RST, le lexeur et les directives : ils partent en phase 4.

Fichiers :

- `strictdoc/backend/rst/rst_format.py`
- `strictdoc/backend/rst/document_rst_generator.py`
- `strictdoc/backend/rst/writer.py`
- `strictdoc/backend/rst/rst_templates.py`
- `strictdoc/backend/rst/templates/requirement.jinja.rst`

#### P1-03 Nettoyer les chemins de gabarits et le packaging

Effort et risque : effort S (½ j) ; risque faible.

Retirer `get_path_to_rst_templates()` de l'environnement et les références aux gabarits RST dans les options de données PyInstaller et Nuitka, si elles existent. À vérifier avec une recherche `git grep` avant de supprimer.

Fichiers :

- `strictdoc/core/environment.py`
- `tasks.py`

#### P1-04 Supprimer ou adapter les tests de l'export RST

Effort et risque : effort M (1 à 2 j) ; risque faible.

Supprimer `tests/integration/features/rst/` (17 tests d'intégration). Trois autres tests utilisent `--formats=rst` et sont à adapter : `html/rst_markup_to_html/20_csv_table`, `html/utf8/01_utf8_in_sdoc` et `tests/unit/strictdoc/cli/test_cli_arg_parser.py`.

Fichiers :

- `tests/integration/features/rst/`
- `tests/integration/features/html/rst_markup_to_html/20_csv_table/test.itest`
- `tests/integration/features/html/utf8/01_utf8_in_sdoc/test.itest`
- `tests/unit/strictdoc/cli/test_cli_arg_parser.py`

#### P1-05 Mettre à jour le guide utilisateur et les exigences

Effort et risque : effort M (1 à 2 j) ; risque faible.

Retirer les sections « HTML export via Sphinx » et « Wildcard image paths for RST/Sphinx export », la ligne de la carte des fonctions, les exigences SDOC-SRS de l'export RST, et les marqueurs `@relation` des fichiers supprimés pour garder la traçabilité propre.

Fichiers :

- `docs/strictdoc_01_user_guide.sdoc`
- `docs/strictdoc_02_feature_map.sdoc`
- `docs/strictdoc_21_l2_high_level_requirements.sdoc`
- `docs/strictdoc_22_l3_low_level_requirements.sdoc`

#### P1-06 Alternative pour qui utilisait Sphinx

Effort et risque : effort S (½ j) ; risque faible.

Variante retenue : Aucune documentation.

Documenter ce que l'on fait à la place : l'export Markdown existe déjà. Une page « Migrer de Sphinx » dirait comment passer par `--formats=markdown` puis un outil externe. Si vous n'utilisez pas Sphinx, cette tâche est inutile.

#### P1-07 Notes de version et commit de rupture

Effort et risque : effort S (½ j) ; risque faible.

Entrée dans « Unreleased » des notes de version, et message de commit `feat!(export): remove the RST export`.

Fichiers :

- `docs/strictdoc_04_release_notes.sdoc`

### Phase 2 : alternatives HTML pour les fonctions RST perdues

#### P2-00 Étude préalable : l'éditeur Milkdown garde-t-il le HTML ?

Effort et risque : effort M (1 à 2 j) ; risque élevé.

Variante retenue : Faire l'étude avant toute autre tâche de cette phase.

Tout le plan suppose qu'un document Markdown contenant un encadré HTML survit à une édition dans Milkdown. Aujourd'hui seuls les tableaux HTML aux balises connues sont relus comme tableaux ; le HTML inconnu est peut-être perdu ou enveloppé.

Livrable : un rapport sur des échantillons (`div` avec classe, `dl`, `sup`, `sub`, `aside`, commentaires HTML) et, si besoin, une extension de l'éditeur qui les conserve octet pour octet.

Fichiers :

- `developer/milkdown/src/`
- `developer/milkdown/playwright/`
- `strictdoc/features/milkdown/assets/milkdown/`

#### P2-01 Politique de sécurité du HTML brut

Effort et risque : effort M (1 à 2 j) ; risque élevé.

Variante retenue : Liste blanche de balises et d'attributs, comme pour les SVG.

Le rendu Markdown actuel laisse passer n'importe quel HTML, scripts compris. Des relecteurs ne modifient pas le texte, mais des auteurs et des imports Word ou ReqIF peuvent en écrire. En s'appuyant davantage sur le HTML, il faut décider de ce qui est permis.

Cette faille existe déjà aujourd'hui pour les documents Markdown ; le retrait de RST la rend plus visible, il ne la crée pas.

Fichiers :

- `strictdoc/backend/markdown/markdown_to_html_fragment_writer.py`
- `strictdoc/features/svg/sanitizer.py (modèle à suivre)`

#### P2-02 Feuille de style commune des éléments de remplacement

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Un fichier CSS `sdoc-markup.css` : encadrés (une couleur et une icône par type), listes de définitions, notes de bas de page, thème clair et sombre, styles d'impression pour le PDF. Classes préfixées `sdoc-` pour ne pas entrer en conflit.

**Accord requis :** ce fichier est chargé par `base.jinja.html`, un composant partagé. Les règles du dépôt demandent votre accord avant de le toucher.

Fichiers :

- `strictdoc/export/html/_static/`
- `strictdoc/export/html/templates/base.jinja.html`
- `strictdoc/core/environment.py`

#### P2-10 Encadrés : note, warning, tip, important, caution, danger, attention, hint, error, admonition

Effort et risque : effort M (1 à 2 j) ; risque moyen ; usage : 51 note, 8 warning, 5 admonition.

Variante retenue : Bloc HTML avec classes sdoc-admonition.

Équivalent des directives RST `.. note::` et voisines. Forme recommandée :

```
<div class="sdoc-admonition sdoc-note" role="note">
<p class="sdoc-admonition-title">Note</p>

Texte en **Markdown**.

</div>
```

Les lignes vides laissent Markdown fonctionner à l'intérieur. Le titre est écrit dans le document, donc dans la langue du document ; il est exportable et indexé.

#### P2-11 Notes de bas de page et citations

Effort et risque : effort S (½ j) ; risque faible ; usage : 0 occurrence.

Variante retenue : Ancre [ANCHOR: fn-1, "1"] et lien [LINK: fn-1].

Aucun usage dans le dépôt. Si on garde une alternative : ancres StrictDoc natives, qui sont vérifiées par l'index et donnent des liens entrants.

#### P2-12 Listes de définitions

Effort et risque : effort S (½ j) ; risque faible ; usage : non mesuré.

Variante retenue : Balises dl, dt, dd.

HTML : `<dl><dt>Terme</dt><dd>Définition</dd></dl>`. Le convertisseur compte les occurrences réelles dans son rapport ; si elles sont rares, on les convertit en liste à puces avec le terme en gras.

#### P2-13 Rôles RST en ligne

Effort et risque : effort S (½ j) ; risque faible ; usage : 14 :code:, 7 :eq:, 5 :math:.

Variante retenue : Équation numérotée écrite \tag{n} dans $$…$$, renvoi remplacé par le numéro en texte.

- `:code:` devient des apostrophes inverses ; `:math:` devient `$…$`.

- `:sup:` et `:sub:` deviennent `<sup>` et `<sub>`.

- `:rawhtml:` (rôle maison) devient le HTML brut.

- `:ref:` et `:doc:` (Sphinx) deviennent `[LINK: uid]` quand la cible est un nœud, sinon un lien Markdown.

- `:eq:` renvoie à une équation numérotée par `.. math:: :label:`. Markdown n'a pas d'étiquettes.

#### P2-14 Numéros de ligne dans les blocs de code

Effort et risque : effort S (½ j) ; risque faible ; usage : 249 blocs de code, 1 seul fichier avec :number-lines:.

Variante retenue : Accepter la perte (Markdown n'en a pas).

Vérifié avec docutils 0.23 : le réglage `syntax_highlight_opts = {linenos: inline}` de StrictDoc n'a aucun effet. Un bloc de code RST n'a de numéros de ligne que si l'on écrit `:number-lines:`. Seul un fichier du dépôt le fait (`docs/strictdoc_22_l3_low_level_requirements.sdoc`, 3 blocs). Ce que Markdown perd est donc minime.

#### P2-15 Blocs raw, HTML et autres cibles

Effort et risque : effort S (½ j) ; risque faible ; usage : 16 .. raw::.

`.. raw:: html` devient du HTML brut : équivalent natif. Les autres cibles (`latex`, `pdf`, ...) n'ont pas de sens dans un nœud : supprimées avec un avertissement dans le rapport. À vérifier sur les 16 occurrences du dépôt avant de trancher.

#### P2-16 Blocs de mise en page : epigraph, pull-quote, rubric, sidebar, topic, container, compound

Effort et risque : effort S (½ j) ; risque faible ; usage : 0 occurrence.

Variante retenue : Correspondance minimale par classes.

Correspondance minimale : `blockquote` pour les citations, `aside class="sdoc-sidebar"` pour les encadrés latéraux, `div class="…"` pour `container`. Aucun usage dans le dépôt.

#### P2-17 Listes de champs, blocs de lignes, listes d'options

Effort et risque : effort S (½ j) ; risque faible ; usage : non mesuré.

Blocs de lignes (`| ligne`) : lignes séparées par deux espaces ou `<br>`. Listes de champs (`:Auteur: x`) : liste à puces « Auteur : x ». Listes d'options : liste à puces.

#### P2-18 Directives de structure sans équivalent

Effort et risque : effort S (½ j) ; risque faible ; usage : non mesuré.

`.. contents::`, `.. sectnum::`, `.. header::`, `.. footer::`, `.. include::`, `.. only::`, `.. toctree::` n'ont pas de sens dans un nœud : retirées avec avertissement. Dites si vous voulez une liste précise de ce que le rapport doit signaler en erreur plutôt qu'en avertissement.

#### P2-20 Export Word des éléments HTML

Effort et risque : effort L (3 à 5 j) ; risque moyen.

Variante retenue : Encadré = paragraphe avec style Word « Note » ou « Avertissement » du modèle.

L'export Word lit le Markdown puis traite surtout paragraphes, tableaux et images ; les alignements HTML sont déjà gérés. Il faut décider ce que devient un encadré dans Word : paragraphe encadré ou style « Note », liste de définitions, exposant et indice.

C'est la tâche qui compte le plus pour un livrable contractuel Word.

Fichiers :

- `strictdoc/backend/docx/export/markdown_to_paragraphs.py`
- `strictdoc/backend/docx/export/docx_template.py`
- `strictdoc/backend/docx/export/sdoc_to_docx_generator.py`

#### P2-21 Export PDF et impression

Effort et risque : effort S (½ j) ; risque faible.

Styles `@media print` et règles d'éclatement de page pour les encadrés, vérifiés avec l'export html2pdf (Chrome).

Fichiers :

- `strictdoc/features/html2pdf/templates/`
- `strictdoc/export/html/_static/`

#### P2-22 Éditeur Milkdown : insertion d'un encadré

Effort et risque : effort L (3 à 5 j) ; risque élevé ; dépend de P2-00.

Un nœud de l'éditeur qui affiche l'encadré et s'écrit exactement comme le HTML de P2-10. Il faut un test d'aller-retour sur les 10 types d'encadré, la reconstruction du bundle (`developer/milkdown`) et le commit des fichiers générés (`milkdown.js`, `milkdown.css`, mentions légales).

#### P2-23 Recherche, page d'un item, versions et assistant LLM

Effort et risque : effort S (½ j) ; risque faible.

Vérifier que le texte des blocs HTML entre dans l'index de recherche, s'affiche sur la page d'un item et dans la comparaison de versions, et que l'assistant ne reçoit pas de balises en vrac (nettoyage dans `features/llm/context.py`).

Fichiers :

- `strictdoc/backend/sdoc/models/document.py (build_search_index)`
- `strictdoc/features/item_page/`
- `strictdoc/features/llm/context.py`

### Phase 3 : convertisseur RST vers Markdown

#### P3-01 Forme de l'outil : script jetable

Effort et risque : effort S (½ j) ; risque faible.

Un script `developer/tools/rst_to_markdown.py`, hors du paquet StrictDoc. Il tourne dans l'environnement du dépôt (il importe StrictDoc et docutils). Arguments : chemin, `--dry-run`, `--report`, `--strict`, `--force`.

Ce n'est pas une commande de la CLI : pas de test d'intégration de CLI, pas de documentation de commande. Il est supprimé en phase 4 avec docutils (P4-11) ; l'étiquette `pre-markdown-only` le garde.

Fichiers :

- `developer/tools/rst_to_markdown.py (nouveau)`
- `tests/unit/developer/ (nouveaux tests)`

#### P3-02 Moteur de conversion

Effort et risque : effort L (3 à 5 j) ; risque élevé.

Variante retenue : Visiteur docutils maison.

Parcourir l'arbre docutils (déjà utilisé pour le rendu) avec un visiteur qui écrit du Markdown. Les directives et rôles propres à StrictDoc sont enregistrés comme aujourd'hui (image avec joker, mathématiques, `rawhtml`).

Fichiers :

- `strictdoc/backend/rst/rst_to_markdown.py (nouveau)`

#### P3-03 Dépendance docutils pendant et après la migration

Effort et risque : effort S (½ j) ; risque moyen ; dépend de P3-02.

Variante retenue : Convertisseur supprimé avec docutils après la migration.

Le convertisseur a besoin de docutils, que la phase 4 retire de l'exécution. Il faut donc décider où docutils vit.

#### P3-04 Pipeline de lecture et d'écriture d'un document

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Lire avec `SDReader`, convertir chaque champ multiligne (`STATEMENT`, `RATIONALE`, `COMMENT`, champs personnalisés multilignes, nœuds `TEXT`), mettre `MARKUP: Markdown`, réécrire avec `SDWriter`. Traiter aussi les fragments inclus par `DOCUMENT_FROM_FILE`. Objectif : un diff Git où seuls ces champs et la ligne `MARKUP` changent.

Fichiers :

- `strictdoc/backend/sdoc/reader.py`
- `strictdoc/backend/sdoc/writer.py (wrap_rst_text)`
- `strictdoc/backend/sdoc/models/document_config.py`

#### P3-05 Règles : texte en ligne

Effort et risque : effort M (1 à 2 j) ; risque moyen.

- Emphase, gras, littéral (le double accent grave devient un seul, avec échappement si le texte contient un accent grave).

- Liens `texte <url>_`, liens anonymes, références nommées, substitutions `|nom|` résolues à la conversion.

- Échapper les caractères spéciaux Markdown (`* _ # < | [ ]`) dans le texte normal.

- **Ne jamais échapper** `[LINK: UID]` ni `[ANCHOR: id, "titre"]`.

#### P3-06 Règles : blocs

Effort et risque : effort M (1 à 2 j) ; risque moyen.

- Paragraphes, listes à puces et numérotées imbriquées, citations, blocs littéraux `::`.

- `.. code::` et `.. code-block::` (249 occurrences) : clôtures avec langage.

- `.. math::` (24) : `$$…$$`.

- Titres de section dans un champ : `#` ; transitions : `---` ; commentaires RST : commentaires HTML.

- Encadrés et rôles : selon les choix de la phase 2.

#### P3-07 Règles : tableaux

Effort et risque : effort L (3 à 5 j) ; risque élevé ; usage : 23 list-table dans 9 fichiers.

Variante retenue : Toujours en HTML.

Les tableaux ne sont pas dans la phase 2, mais la conversion doit les traiter : `list-table`, tableaux en grille, tableaux simples.

Format cible : tableau à barres verticales quand toutes les cellules tiennent sur une ligne, sans fusion ni bloc ; sinon tableau HTML (que l'éditeur sait relire quand toutes les balises et attributs sont connus). Gérer `:header-rows:`, `:widths:`, `:align:` et le titre (`caption`).

#### P3-08 Règles : csv-table

Effort et risque : effort S (½ j) ; risque faible ; usage : 2 occurrences.

Variante retenue : Supprimer le CSV converti.

Lire le CSV à la conversion (contenu en ligne ou fichier relatif aux ressources), appliquer `:header:`, `:delim:`, `:widths:`, puis écrire comme un tableau (tâche précédente). Le fichier CSV d'origine n'est plus nécessaire : le supprimer ou le garder.

#### P3-09 Règles : images

Effort et risque : effort M (1 à 2 j) ; risque moyen ; usage : 98 .. image::, 14 avec joker.

Variante retenue : Résoudre le joker vers l'extension réelle trouvée dans _assets (SVG, sinon PNG).

`.. image::` et `.. figure::` deviennent `![alt](chemin)`. Avec `:width:` ou `:align:`, écrire le HTML que l'éditeur sait relire (il gère l'alignement des images). Une légende de figure devient une ligne en italique ou `figcaption`.

Les chemins avec joker (`schema.*`) n'existent pas en Markdown.

#### P3-10 Commentaires de relecture

Effort et risque : effort S (½ j) ; risque moyen.

L'en-tête RST `.. sdoc-comment: …` devient `<!-- sdoc-comment … -->`. Les champs `anchor` et `anchor_n` désignent des mots du texte : vérifier qu'ils sont encore retrouvés après conversion, sinon avertir.

Fichiers :

- `strictdoc/features/comments/model.py`

#### P3-11 Que faire d'une construction non convertible

Effort et risque : effort S (½ j) ; risque moyen.

Variante retenue : Repli HTML sinon commentaire, avec avertissement ; --strict fait échouer.

Chaque construction qui ne se traduit pas fidèlement est signalée dans le rapport avec le document, le nœud, le champ et la ligne.

#### P3-12 Rapport de conversion

Effort et risque : effort S (½ j) ; risque faible.

Rapport Markdown et JSON : champs convertis ou inchangés, histogramme des constructions rencontrées, avertissements, échecs. `--dry-run` n'écrit rien.

#### P3-13 Vérification sémantique automatique

Effort et risque : effort L (3 à 5 j) ; risque élevé ; dépend de P3-02.

Pour chaque champ : rendre l'ancien RST avec docutils, rendre le Markdown converti, normaliser les deux (texte, titres, listes, tableaux, liens, images) et comparer. Les écarts sont listés. Sert de test sur tout le corpus (`docs/` et tests).

#### P3-14 Sécurité d'exécution

Effort et risque : effort S (½ j) ; risque faible.

Ne convertit que les documents en RST ou sans balisage ; une seconde exécution ne change rien (idempotente) ; refuse un arbre Git non propre sauf `--force` ; un commit par document ou par projet.

#### P3-15 Effets de la conversion sur les liens suspects, les PDF et les comparaisons

Effort et risque : effort M (1 à 2 j) ; risque élevé.

Variante retenue : Étiquette de version avant ; recalcul de la ligne de base juste après la conversion.

La conversion change le texte de `STATEMENT` : l'empreinte des liens suspects change, donc tous les liens deviennent suspects. Les barres de changement du PDF et l'écran de versions montrent tout comme modifié.

#### P3-16 Tests du convertisseur

Effort et risque : effort L (3 à 5 j) ; risque moyen.

Tests unitaires par construction (cas d'or) dans `tests/unit/developer/`, qui existe déjà (`git/`). Un contrôle sur tout le corpus de `.sdoc` du dépôt avec la vérification sémantique (P3-13). Pas de test d'intégration de CLI, puisque le script n'est pas une commande.

#### P3-17 Guide de migration

Effort et risque : effort S (½ j) ; risque faible.

Page du guide utilisateur : table de correspondance RST vers Markdown, limites, comment lire le rapport, comment relancer.

#### P3-18 Conversion des documents Text vers Markdown

Effort et risque : effort S (½ j) ; risque moyen ; dépend de P3-02.

Trois fichiers de test sont en `MARKUP: Text` : `options_per_document/MARKUP/02_options_markup_is_text` et les deux fichiers de `10_linux_spdx_req_id_autogen`. Le rendu Text échappe le HTML et transforme chaque retour à la ligne en `<br/>`.

Le script les convertit : échapper les caractères spéciaux de Markdown, garder les retours à la ligne (deux espaces ou barre oblique inverse en fin de ligne), puis vérifier le rendu.

### Phase 4 : retirer le balisage RST du code (cas B)

#### P4-02 Grammaire : retirer RST de MARKUP

Effort et risque : effort S (½ j) ; risque moyen.

`MarkupChoice` devient `'Markdown' | 'HTML'` et `SDocMarkup.RST` et `SDocMarkup.TEXT` disparaissent. Une ligne `MARKUP: Markdown` reste acceptée et ignorée. `MARKUP: RST` et `MARKUP: Text` donnent une erreur claire qui cite le script de conversion et l'étiquette `pre-markdown-only`.

Fichiers :

- `strictdoc/backend/sdoc/grammar/grammar.py`
- `strictdoc/backend/sdoc/constants.py`

#### P4-03 Valeurs par défaut en dur

Effort et risque : effort M (1 à 2 j) ; risque élevé ; dépend de C-05.

Remplacer le repli RST dans `DocumentConfig.get_markup()`, dans `MarkupRenderer` (3 endroits), dans `RequirementFormObject` (3 endroits) et dans `editable_field.js` (défaut 'RST', syntaxe d'insertion d'image).

Fichiers :

- `strictdoc/backend/sdoc/models/document_config.py`
- `strictdoc/export/html/renderers/markup_renderer.py`
- `strictdoc/export/html/form_objects/requirement_form_object.py`
- `strictdoc/export/html/_static/editable_field.js`

#### P4-04 Rendus internes qui passent markup="RST"

Effort et risque : effort S (½ j) ; risque moyen.

Ce sont des titres et noms générés par StrictDoc, pas du RST rédigé. À passer en Texte ou en Markdown selon le cas.

Fichiers :

- `strictdoc/features/traceability_matrix/generator.py`
- `strictdoc/features/source_file_view/generator.py`
- `strictdoc/features/source_file_view/view_object.py`
- `strictdoc/features/nestor/view_object.py`
- `strictdoc/features/search/view_object.py`

#### P4-05 Supprimer le paquet backend/rst

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Rendu HTML RST, directives (image avec joker, mathématiques, `rawhtml`), `formatter.py` et son utilisation dans `sdoc/writer.py`, `helpers/rst.py`, gabarit `rst/anchor.jinja`, branche RST de `MarkupRenderer`.

**Attention :** `strictdoc_lexer.py` colore la syntaxe `sdoc` dans les blocs de code. Le déplacer (par exemple dans `backend/sdoc/`) et l'enregistrer pour les clôtures `sdoc` en Markdown (trois apostrophes inverses suivies de sdoc), sinon la coloration disparaît.

Fichiers :

- `strictdoc/backend/rst/`
- `strictdoc/helpers/rst.py`
- `strictdoc/export/html/templates/rst/anchor.jinja`
- `strictdoc/backend/sdoc/writer.py`

#### P4-06 Gestion des images

Effort et risque : effort S (½ j) ; risque moyen.

`manage assets --clean-unused-images` lit les directives RST des images. Il ne doit plus lire que les images Markdown et HTML. Adapter aussi le commentaire de `core/image_formats.py`.

Fichiers :

- `strictdoc/commands/manage_assets_command.py`
- `strictdoc/core/image_formats.py`

#### P4-07 Validation à l'enregistrement

Effort et risque : effort S (½ j) ; risque moyen.

Variante retenue : Aucune validation de syntaxe.

Le serveur valide aujourd'hui la syntaxe RST avant d'enregistrer un nœud (`RstToHtmlFragmentWriter` dans `update_requirement.py` et `requirement_form_object.py`). À remplacer : Markdown n'a pas d'erreur de syntaxe fatale.

Fichiers :

- `strictdoc/core/transforms/update_requirement.py`
- `strictdoc/export/html/form_objects/requirement_form_object.py`

#### P4-08 Fonction MATHJAX

Effort et risque : effort S (½ j) ; risque faible.

Variante retenue : Retrait net : une configuration qui liste MATHJAX échoue.

Le drapeau `MATHJAX` est déjà inutile : MathJax est toujours chargé (`is_activated_mathjax()` renvoie toujours vrai) et la configuration ne fait qu'afficher un avertissement de dépréciation. Supprimer le drapeau veut dire : retirer `ProjectFeature.MATHJAX`, l'avertissement, l'option `--enable-mathjax` de `export`, `is_activated_mathjax()` et ses conditions dans les gabarits, et le commentaire de `new_command.py`. Le chargement de MathJax ne change pas.

Une configuration qui liste encore `"MATHJAX"` échouerait (valeur inconnue).

Fichiers :

- `strictdoc/core/project_config.py`
- `strictdoc/commands/export_config.py`
- `strictdoc/commands/export.py`
- `strictdoc/commands/new_command.py`
- `strictdoc/export/html/templates/screens/document/document/index.jinja`
- `strictdoc/export/html/templates/screens/document/table/index.jinja`

#### P4-09 Importeurs et exporteurs : balisage par défaut

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Profil Word par défaut (`MARKUP_RST` devient Markdown), `docx_comments.py` (`markup = "RST"`), suppression de `rst_to_paragraphs.py` et de ses branches, option `--reqif-import-markup` (valeurs possibles : `Markdown` et `HTML` ; la liste vient de `SDocMarkup.ALL`), défaut des importeurs Excel et ReqIF, `strictdoc new` et ses gabarits.

Fichiers :

- `strictdoc/backend/docx/docx_profile.py`
- `strictdoc/backend/docx/export/docx_comments.py`
- `strictdoc/backend/docx/export/rst_to_paragraphs.py`
- `strictdoc/backend/docx/import_/docx_to_sdoc_converter.py`
- `strictdoc/commands/_shared.py`
- `strictdoc/commands/new_command.py`

#### P4-10 Cache et version

Effort et risque : effort S (½ j) ; risque faible.

Supprimer le sous-dossier `<cache>/rst`. Les classes de modèle changent (constante supprimée) : la version du cache augmente pour invalider les fichiers pickle.

#### P4-11 Dépendances et packaging

Effort et risque : effort S (½ j) ; risque faible.

Retirer `docutils` de `pyproject.toml` sans groupe de remplacement, supprimer `developer/tools/rst_to_markdown.py` (il reste dans l'étiquette `pre-markdown-only`), régénérer `uv.lock`, supprimer `[mypy-docutils.*]` de `mypy.ini`, vérifier les hooks PyInstaller, `Dockerfile` et `flake.nix`.

Fichiers :

- `pyproject.toml`
- `uv.lock`
- `mypy.ini`
- `developer/pyinstaller_hooks/`
- `Dockerfile`
- `flake.nix`

#### P4-13 Détecteur de contenu RST résiduel

Effort et risque : effort S (½ j) ; risque moyen ; dépend de C-05.

Variante retenue : Avertissement à la lecture.

Sans ligne `MARKUP` obligatoire, un ancien document RST ne se distingue plus d'un document Markdown. À la lecture, un avertissement signale un champ qui contient une ligne `.. directive::`, un double accent grave, un titre souligné ou un tableau en grille. Les blocs de code sont ignorés pour limiter les faux positifs. C'est un avertissement, jamais une erreur.

Fichiers :

- `strictdoc/backend/sdoc/processor.py`
- `strictdoc/helpers/deprecation_engine.py`

#### P4-14 Retirer le balisage Text

Effort et risque : effort S (½ j) ; risque faible ; dépend de C-03, P3-18.

Retirer `TextToHtmlWriter` (`text_to_html_writer.py`) et ses deux usages dans `MarkupRenderer`, la valeur `Text` de la grammaire, et le test `02_options_markup_is_text` (il teste l'option elle-même). Un `MARKUP: Text` donne l'erreur de P4-02.

Fichiers :

- `strictdoc/export/html/renderers/text_to_html_writer.py`
- `strictdoc/export/html/renderers/markup_renderer.py`
- `strictdoc/backend/sdoc/constants.py`
- `tests/integration/features/options/options_per_document/MARKUP/02_options_markup_is_text/`

### Migration des contenus

#### M-01 Inventaire des projets réels (lecture seule)

Effort et risque : effort S (½ j) ; risque faible.

Scanner `~/strictdoc-data`, `~/strictdoc-projects` et les dépôts GitLab de documents (`kb-isis`, projets créés par le portail) : nombre de `.sdoc` sans `MARKUP: Markdown`, directives RST, tableaux, images avec joker. Livrable : un rapport que vous validez avant toute conversion.

#### M-02 Convertir la documentation de StrictDoc

Effort et risque : effort L (3 à 5 j) ; risque moyen ; dépend de P3-13.

Variante retenue : Convertir sur place.

15 documents dans `docs/`, tous en RST implicite : guide utilisateur (254 lignes de directives), notes de version, exigences L1 à L3, guide du développeur... Conversion par l'outil, relecture à la main, comparaison avant et après du site (`invoke docs`).

Ces fichiers sont aussi modifiés par l'amont : conflits garantis en cas de fusion ultérieure.

#### M-03 Corpus de tests

Effort et risque : effort L (3 à 5 j) ; risque élevé ; usage : ~1 770 .sdoc sans balisage, 94 avec directives.

Appliquer le script à tous les `.sdoc` de tests. Un fichier sans mise en forme ne change pas (aucun diff, pas de ligne `MARKUP` ajoutée). Les 94 fichiers avec directives sont convertis et relus. Les résultats attendus qui changent sont régénérés.

Risque : un texte brut qui contient `*`, `_`, `#`, `[`, `<`, `|` peut changer d'aspect en Markdown. Le script échappe ces caractères et la vérification sémantique le confirme.

#### M-04 Tests propres à RST

Effort et risque : effort M (1 à 2 j) ; risque faible.

Supprimer ou porter vers Markdown : `tests/integration/features/html/rst_markup_to_html/`, les tests unitaires de `tests/unit/strictdoc/export/rst/` (writer, lexeur, rôle `rawhtml`) et `test_rst_to_paragraphs.py`. Pour chaque test, un équivalent Markdown quand la fonction existe encore (code, mathématiques, images, tableaux).

#### M-05 Données de production

Effort et risque : effort M (1 à 2 j) ; risque moyen ; dépend de M-01, P3-15.

REQ_02 est déjà en Markdown : vérifier seulement. Pour tout autre document RST trouvé en M-01 : étiquette de version avant, conversion, vérification de l'export Word avec le profil, recalcul de la ligne de base des liens suspects, reconstruction de l'index de la base de connaissances (`kb-isis`, hors dépôt) si le texte indexé change.

#### M-06 Ordre de bascule

Effort et risque : effort S (½ j) ; risque faible.

Livrer P3 ; convertir `docs/` et les tests dans des commits séparés ; vérifier ; seulement alors lancer P4. Aucun commit de P4 ne doit entrer avant que le dépôt ne contienne plus aucun `MARKUP: RST`.

#### M-07 Documents de test en Text et en HTML

Effort et risque : effort S (½ j) ; risque faible ; dépend de P3-18.

Trois documents en `MARKUP: Text` sont convertis (P3-18). Onze documents en `MARKUP: HTML` restent : vérifier leurs résultats attendus après les changements de `MarkupRenderer`.

### Effets sur les fonctions du fork ISIS

#### F-01 Contrat de format entre convertisseur et éditeur Milkdown

Effort et risque : effort M (1 à 2 j) ; risque élevé ; dépend de P2-00.

Variante retenue : Accepter la réécriture en tableau à barres à la première édition.

Le script écrit du Markdown, des tableaux HTML et des blocs HTML ; l'éditeur doit les relire sans les altérer. Un test automatique charge un document converti dans l'éditeur, enregistre sans modification, et compare le texte, avec au moins un tableau HTML aux balises connues.

Point à décider : l'éditeur écrit un tableau simple en tableau à barres. À la première édition d'un tableau converti, il le réécrirait donc en barres, ce qui fait un diff Git.

Fichiers :

- `developer/milkdown/src/tables.js`
- `developer/milkdown/src/sdoc_markers.js`
- `developer/milkdown/playwright/`

#### F-02 Commentaires de relecture

Effort et risque : effort S (½ j) ; risque faible.

Le script réécrit les en-têtes `.. sdoc-comment: …` en `<!-- sdoc-comment … -->`. Sans période de dépréciation (C-06), la variante RST (`_RST_HEADER`) est retirée dans la phase 4 sans lecture tolérante.

Fichiers :

- `strictdoc/features/comments/model.py`
- `strictdoc/features/comments/assets/comments/comments.js`

#### F-03 Word : import, export et mise à jour

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Le profil Word passe en Markdown par défaut. Vérifier la mise à jour d'un Word existant avec modifications suivies (`docx_tracked_update.py`) : elle compare du texte ; après conversion, les textes diffèrent sans que le fond change. Prévoir un cas de test avec REQ_02.

Fichiers :

- `strictdoc/backend/docx/export/docx_tracked_update.py`
- `strictdoc/backend/docx/docx_profile.py`

#### F-04 Assistant LLM

Effort et risque : effort S (½ j) ; risque faible.

Les prompts ne parlent pas de RST (recherche faite dans le code Python ; les 23 fichiers de prompts restent à relire). L'assistant écrit dans le balisage du document : vérifier `create_text_node`, `/glossary`, `/translate` sur un document Markdown, et les cas du jeu d'évaluation.

Fichiers :

- `strictdoc/features/llm/service.py`
- `strictdoc/features/llm/prompts/`
- `strictdoc/features/llm/golden/`

#### F-05 Interface en français

Effort et risque : effort S (½ j) ; risque faible.

Nouveaux textes (rapport du convertisseur, messages de dépréciation, aides d'insertion d'encadré) ajoutés au catalogue français ; textes devenus inutiles retirés. Mise à jour par `developer/i18n/update_catalogs.py`.

#### F-06 Rôles et routes

Effort et risque : effort S (½ j) ; risque faible.

La commande est en ligne de commande : aucune route. Si le bouton web de P3-01 est retenu, chaque nouvelle route doit figurer dans `ROUTE_ROLES` (rôle administrateur) sinon le serveur ne démarre pas.

Fichiers :

- `strictdoc/features/roles/route_roles.py`

#### F-07 Base de connaissances (kb-platform)

Effort et risque : effort S (½ j) ; risque moyen.

L'indexeur de la base de connaissances lit des `.sdoc` ; je ne peux pas voir s'il suppose du RST (dépôt hors de celui-ci). À vérifier avant de convertir des documents de mission.

#### F-08 Écrans qui rendent des champs

Effort et risque : effort S (½ j) ; risque faible.

Page d'un item, vue en pages, comparaison de versions, page des liens suspects et des commentaires : tous passent par `MarkupRenderer`. Test de bout en bout après P4.

#### F-09 Documentation d'architecture

Effort et risque : effort S (½ j) ; risque faible.

Mettre à jour `architecture/` (documents 02, 03, 04, 06, 08, 11, 12 et l'index) : retirer RST, ajouter le convertisseur et les éléments HTML.

Fichiers :

- `architecture/`

#### F-10 CLAUDE.md et AGENTS.md

Effort et risque : effort S (½ j) ; risque faible.

CLAUDE.md décrit les lectures « .sdoc, Markdown, RST, ReqIF » : retirer RST. Rien à changer dans AGENTS.md à part vérifier la mention des formats.

Fichiers :

- `CLAUDE.md`
- `AGENTS.md`

### Tests, documentation, packaging et CI

#### Q-01 Stratégie de test par phase

Effort et risque : effort M (1 à 2 j) ; risque faible.

P1 : tests d'intégration de la CLI. P2 : tests de rendu des éléments HTML, tests Milkdown, tests d'export Word et PDF. P3 : corpus et vérification sémantique. P4 : suite complète (`invoke check`, puis end2end avec `--headless`).

#### Q-02 Référence de rendu avant et après

Effort et risque : effort S (½ j) ; risque faible.

Variante retenue : Comparaison automatique du texte visible.

Exporter REQ_02 et `docs/` en HTML avant la phase 1 ; comparer le texte visible après chaque phase. C'est le test le plus parlant pour vous.

#### Q-03 Exigences et traçabilité

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Nouvelles exigences (convertisseur, éléments HTML, retrait de RST), marqueurs `@relation`, retrait des exigences RST. Les numéros SDOC-SRS-208 à 216 du fork entrent en collision avec ceux de l'amont : à renuméroter avant toute fusion de l'amont.

Fichiers :

- `docs/strictdoc_21_l2_high_level_requirements.sdoc`
- `docs/strictdoc_22_l3_low_level_requirements.sdoc`

#### Q-04 Guide utilisateur et FAQ

Effort et risque : effort M (1 à 2 j) ; risque faible.

Section « Markdown » complétée (HTML autorisé, éléments de remplacement), section « Migrer de RST », retrait des sections RST (directives, rôles, Sphinx).

#### Q-05 Notes de version et ruptures

Effort et risque : effort S (½ j) ; risque faible.

Ruptures à lister : `MARKUP: RST`, `--formats=rst`, balisage par défaut, `--reqif-import-markup RST`, profil Word par défaut, API Python (vérifier si `strictdoc.api` exporte des classes RST).

Fichiers :

- `docs/strictdoc_04_release_notes.sdoc`
- `strictdoc/api/__init__.py`

#### Q-06 CI, packaging et durée (arm64 retiré)

Effort et risque : effort S (½ j) ; risque faible.

Commentaire : « Supprimer la version arm64 »

Options de données PyInstaller et Nuitka, `Dockerfile`, durée de la suite. Le retrait doit raccourcir la suite : plus de tests RST, un cache en moins. La prise en charge d'arm64 des tests Docker est retirée (Q-08).

Fichiers :

- `tasks.py`
- `Dockerfile`
- `developer/docker_tests/`

#### Q-07 Mesure de performance

Effort et risque : effort S (½ j) ; risque faible.

Temps d'export de `docs/` et d'un gros document, avant et après (docutils et son cache disparaissent). Critère : aucune régression.

#### Q-08 Retirer la prise en charge d'arm64 des tests Docker

Effort et risque : effort S (½ j) ; risque faible.

Décision : Annuler le commit `e45fcba42` en entier : arm64 et montage du disque amovible. Commentaire : « On ne doit plus utiliser le disque amovible ».

Le commit `e45fcba42` a ajouté arm64 : image construite pour l'architecture du moteur (`TARGETARCH`), Chromium et pilote Debian hors amd64, variable `STRICTDOC_SELENIUM_CHROMEDRIVER`, volumes par architecture, lien symbolique du pilote dans `test_end2end` (`tasks.py`). Le même commit corrige aussi le montage d'un disque amovible sous WSL 2, sans lien avec arm64.

Ce retrait enlève aussi le bloc de `tasks.py` qui entrerait en conflit avec l'amont.

Fichiers :

- `developer/docker_tests/Dockerfile`
- `developer/docker_tests/entrypoint.sh`
- `developer/docker_tests/run_tests.ps1`
- `tasks.py`
- `architecture/11-tests-qualite-build.md`

### Risques, livraison et ce qui reste hors périmètre

#### R-01 Contenu RST lu comme du Markdown, sans erreur

Effort et risque : effort M (1 à 2 j) ; risque élevé.

Le plus grave : un ancien document sans `MARKUP` s'afficherait faux. Parades : migration complète avant P4 (M-06), erreur sur `MARKUP: RST` (P4-02), avertissement sur tout champ qui contient une directive ou un double accent grave.

#### R-02 Dérive de rendu

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Parade : vérification sémantique automatique (P3-13) et comparaison avant et après (Q-02).

#### R-03 Conflits avec l'amont

Effort et risque : effort M (1 à 2 j) ; risque moyen ; dépend de C-07.

Parade : cherry-pick des correctifs utiles avant P4 ; liste des fichiers supprimés pour les fusions futures ; renumérotation des exigences (Q-03).

#### R-04 Irréversibilité

Effort et risque : effort S (½ j) ; risque faible.

Il n'y a pas de conversion Markdown vers RST. Parade : étiquette `pre-markdown-only`, branche dédiée, sauvegarde des projets de production avant conversion.

#### R-05 Arrêt et retour en arrière

Effort et risque : effort S (½ j) ; risque faible.

Variante retenue : Seuil de 5 %.

Critère proposé : si la vérification sémantique signale plus de 5 % de champs divergents sur le corpus, on ne lance pas P4 et on corrige le convertisseur. Précisez le seuil.

#### R-06 Hors périmètre déclaré

Effort et risque : effort S (½ j) ; risque faible.

- L'affichage des fichiers `.rst` du code source dans l'écran « fichier source » (coloration Pygments) reste : c'est la lecture d'un fichier, pas le balisage d'un nœud.

- Le format de document `.md` natif n'est pas touché : voir P5-01.

- Le balisage `HTML` reste ; `Text` part avec RST (C-03).

#### R-07 Estimation globale

Effort et risque : effort S (½ j) ; risque faible.

La page Synthèse additionne les charges des tâches validées (S 0,5 j ; M 1,5 j ; L 4 j). Ce sont des ordres de grandeur pour une personne, pas des engagements.

### Plan de passage au Markdown natif (livrable de fin de projet)

#### P5-01 Écrire le plan de passage du .sdoc au .md natif, avec des conseils

Effort et risque : effort M (1 à 2 j) ; risque moyen.

Livrable : `developer/design/plan_markdown_natif.md`, écrit après la phase 4, pour faire passer les documents `.sdoc` au format `.md` décrit par `spec/Markdown.md`.

Contenu prévu :

- État des lieux : ce que le format `.md` exprime déjà (titre, métadonnées, préfixe, grammaire `.gra.md`, nœuds par titres, nœuds composites, MID, type de nœud, étiquettes LINK et ANCHOR) et ce qui reste à vérifier (relations avec rôle, fragments `DOCUMENT_FROM_FILE`, métadonnées du fork comme `KIND` et `REVIEWERS`, en-têtes de commentaires).

- Convertisseur : l'export `--formats=markdown` écrit déjà des fichiers `.md` depuis les `.sdoc`. À valider comme base de départ, sinon un second script jetable.

- Essai sur REQ_02 d'abord, avec comparaison du rendu, de l'export Word et des liens.

- Étapes, estimations, risques, critères de fin.

Premiers conseils :

- Migrer un document pilote (REQ_02) avant les autres, en gardant les MID : ils servent de clés aux liens, aux commentaires et à la base de connaissances.

- Deux commits Git : le renommage (`git mv x.sdoc x.md`), puis la conversion du contenu, pour que l'historique suive.

- Étiquette de version avant, recalcul de la ligne de base des liens suspects après (comme P3-15).

- Le serveur sait déjà écrire un `.md` (`SDMarkdownWriter` dans `ProjectContext.write_document_to_file`) et liste les extensions modifiables avec `get_editable_document_extensions()`.

- Vérifier le profil Word et la base de connaissances (`kb-platform`, hors dépôt) : les chemins de fichiers changent.

- Test d'aller-retour : `.sdoc` vers `.md`, relecture, comparaison des deux arbres (UID, relations, champs).

Fichiers :

- `spec/Markdown.md`
- `spec/Markdown.gra.md`
- `strictdoc/backend/markdown/`
- `strictdoc/server/project_context.py`
- `strictdoc/core/project_config.py`

### Tâches supprimées

- P4-01 Avertissement de dépréciation : sans objet, le retrait est direct (C-06).
- P4-12 Erreur ou avertissement final : sans objet pour la même raison.
