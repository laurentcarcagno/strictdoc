# Plan de passage au Markdown natif

Rédigé le 2026-11-21, à la fin du plan de retrait de RST (tâche P5-01). Il n'est pas encore validé.

## 1. Objectif

Faire passer les documents `.sdoc` au format `.md` décrit par `spec/Markdown.md` et `spec/Markdown.gra.md`. Les champs sont déjà en Markdown depuis le retrait de RST : il reste à changer le conteneur, c'est-à-dire les en-têtes `[DOCUMENT]`, `[GRAMMAR]`, `[[SECTION]]`, `[REQUIREMENT]` et les champs `>>>`/`<<<`.

Hors périmètre :

- les fichiers `.sdoc` des tests de StrictDoc, qui testent le format SDoc ;
- le retrait du format SDoc lui-même, qui reste lisible et modifiable.

## 2. Ce qui a été essayé

J'ai écrit un convertisseur prototype, gardé hors du dépôt. Il lit chaque `.sdoc` avec `SDReader`, écrit la grammaire avec `MarkdownGrammarWriter` dans un `.gra.md` et le document avec `SDMarkdownWriter`. J'ai ensuite relu le résultat avec StrictDoc et comparé les deux arbres dans l'export JSON (type, champs, relations de chaque nœud), le texte visible de l'export HTML et les paragraphes de l'export Word.

Trois corpus :

| Corpus | Contenu | Résultat |
|---|---|---|
| REQ_02 (copie de `~/strictdoc-data`) | 1 document, grammaire en ligne, 131 exigences, 56 sections, 23 textes, 8 relations Parent, 1 commentaire de relecture | 131 exigences et 56 sections identiques. Les 15 textes consécutifs se fondent en 1. Export Word identique, sauf 14 paragraphes parasites « Type : TEXT MID : … » |
| `docs/` de StrictDoc | 15 documents et 2 `.md` de `spec/`, environ 1 200 nœuds | Tous les nœuds identiques, sauf l'attribut `FORMAT: Sourcecode` de 10 relations File et 1 fusion de textes consécutifs dans le guide utilisateur |
| Document synthétique | Métadonnées du fork (`KIND`, `REVIEWERS`), options, nœud composite, relation avec rôle, relation File, en-tête de commentaire, `[ANCHOR]`, `[LINK]`, encadré HTML, `[DOCUMENT_FROM_FILE]` | Tout est gardé, sauf le MID du document, les `OPTIONS` et l'inclusion du fragment |

Le temps d'export de REQ_02 est le même en `.md` qu'en `.sdoc` : 1,45 s contre 1,52 s.

L'essai a mis au jour deux erreurs de Markdown dans notre documentation, que j'ai corrigées (commit `734b79600`) :

- les exemples Mermaid et PlantUML du guide utilisateur imbriquaient deux blocs de code de même longueur, ce qui fermait le bloc extérieur trop tôt et passait la suite du champ en code ;
- il restait une double ligne vide dans SDOC-LLR-214.

Il faudra aussi relire le rendu HTML des deux exemples corrigés.

## 3. Écarts constatés

### 3.1 Ce que le format `.md` exprime déjà

- Le titre, les métadonnées `UID`, `Version`, `Date`, `Classification`, `Prefix`, et toute autre clé comme métadonnée libre. Les clés `KIND` et `REVIEWERS` du fork sont donc gardées.
- La grammaire dans un fichier `.gra.md` (`**Grammar**: x.gra.md`), avec les types de champs, les rôles de relations, `Composite`, `Prefix`, `View style`.
- Les nœuds par titres, les nœuds composites, `**Type**:` pour les types de nœuds de la grammaire.
- Le MID des nœuds dès que la grammaire déclare un champ `MID` (MD-24).
- `[LINK: …]`, `[ANCHOR: …]`, les relations Parent, Child et File avec rôle.
- Les champs Markdown et les éléments HTML qui remplacent les directives RST.

### 3.2 Écarts du convertisseur (à corriger dans le convertisseur)

| Id | Écart | Correction |
|---|---|---|
| E-01 | `--formats=markdown` n'écrit pas la grammaire. Un document à grammaire en ligne ne se relit pas (« Invalid requirement field: VERSION »). | Écrire un `.gra.md` par grammaire en ligne et le citer dans `**Grammar**:`. Une grammaire déjà dans un `.sgra` devient un `.gra.md` commun. |
| E-02 | Le lecteur Markdown place le TITLE du titre juste après les champs `MID`, `UID`, `LEVEL`, `STATUS`, `TAGS`. Une grammaire qui les range autrement donne « Wrong field order ». | **Corrigé dans le lecteur (E-07, SDOC-MD-38)** : les champs d'un nœud sont remis dans l'ordre de leur élément de grammaire avant la validation. Le convertisseur ne réordonne plus rien, donc l'ordre des colonnes de la vue tableau ne change pas. |
| E-03 | `**Prefix**: None` dans la grammaire du guide utilisateur. **Corrigé à l'usage : ce n'est pas une erreur.** `PREFIX: None` est la valeur littérale « None » que StrictDoc teste (`== "None"`) pour dire « pas d'UID automatique ». Le writer la garde telle quelle. | Aucune ; un test le fixe (N-03). |
| E-04 | Avec une grammaire propre au document, une section qui contient du texte se relit comme une exigence (tout titre qui a des champs devient un nœud), et ses sous-sections disparaissent : 131 exigences deviennent 97 sur REQ_02 sans champ `MID`. Le marqueur `**Type**: SECTION` n'était écrit qu'avec un champ `MID` ou un élément hors SECTION, TEXT, REQUIREMENT. | Le writer écrit le marqueur dès qu'une section contient un TEXT sous une grammaire propre au document (SDOC-MD-37). **Fait.** |

### 3.3 Écarts du format (à décider)

| Id | Écart | Effet sur REQ_02 | Options |
|---|---|---|---|
| E-05 | Deux nœuds TEXT qui se suivent sous un même titre ne se relisent pas séparément. Le second marqueur `**Type**: TEXT \ **MID**: …` reste dans le texte du premier et s'affiche (HTML, Word). La spécification (MD-27, MD-28) ne prévoit qu'un texte par corps de titre. **Décidé : option b, fait (SDOC-MD-36).** | 5 suites de textes, dont la page de garde (15 textes) | a) fusionner les textes consécutifs à la conversion ; b) étendre le lecteur et la spécification : plusieurs enregistrements `**Type**: TEXT` dans un corps, comme MD-35 le fait pour les exigences |
| E-06 | Les `OPTIONS` du document sont perdues : `ENABLE_MID`, `VIEW_STYLE`, `NODE_IN_TOC` (`REQUIREMENT_IN_TOC`), `ROOT`, `AUTO_LEVELS`, `LAYOUT`, `DEFAULT_VIEW`. Le MID du document est perdu aussi. | REQ_02 n'a que `MARKUP: Markdown`, donc aucun effet | a) accepter la perte document par document ; b) ajouter ces clés aux métadonnées reconnues (spécification, lecteur, rédacteur). `ENABLE_MID` est déjà couvert par le champ `MID` de la grammaire, et `VIEW_STYLE` par `View style` par élément. |
| E-07 | Le classement des champs méta est figé dans le lecteur (`requirement_meta_fields`), d'où E-02. | Contourné par E-02 | Corriger le lecteur : garder l'ordre des champs du bloc méta et placer TITLE selon la grammaire |
| E-08 | `[DOCUMENT_FROM_FILE]` n'existe pas en `.md`. Le fragment devient un document séparé et le point d'inclusion disparaît sans avertissement. | Aucun fragment dans REQ_02 | a) laisser en `.sdoc` les documents qui incluent des fragments ; b) recopier le fragment dans le document ; c) ajouter l'inclusion au format (travail de spécification) |
| E-09 | L'attribut `FORMAT` d'une relation File (`FORMAT: Sourcecode`) n'est pas écrit. | Aucun | Vérifier l'usage de `FORMAT`. S'il ne sert qu'à l'affichage, l'accepter ; sinon l'ajouter à MD-14. |

Je recommande :

- **E-05 :** l'option b, qui ne perd ni MID ni commentaire, puisque les commentaires de relecture sont attachés aux MID. L'option a suffit si l'on accepte de perdre la granularité des textes de la page de garde.
- **E-06 :** l'option a pour REQ_02 et les documents du fork ; l'option b seulement si un document en a besoin.
- **E-08 :** l'option a.

## 4. Code du fork qui suppose `.sdoc`

L'essai ne couvre pas ces points. Ce sont les endroits trouvés par recherche de l'extension :

| Fichier | Effet avec un `.md` |
|---|---|
| `strictdoc/features/document_versions/router.py:84` | les versions d'un document `.md` à une étiquette ne s'affichent pas (« pas un .sdoc ») |
| `strictdoc/features/git_sync/sync_service.py:202` | les conflits d'un `.md` ne sont pas proposés à la résolution |
| `strictdoc/features/folders/folders.py:126`, `router.py:207` | renommer ajoute `.sdoc` ; déplacer un `.md` le traite comme un dossier |
| `strictdoc/backend/docx/docx_import.py:72`, `docx_web_service.py:145` | l'import Word écrit toujours un `.sdoc` |
| `strictdoc/features/project_index/templates/.../project_map_folder.jinja:10`, `features/diff_and_changelog/.../diff_content.jinja:13` | l'arbre du projet et le diff ne reconnaissent pas un `.md` comme document |
| `strictdoc/commands/format_command.py:76`, `manage_new_command.py:316`, `manage_autouid_command.py:186` | `format`, `manage new` et `manage auto-uid` ignorent les `.md` |

Ce qui marche déjà :

- le serveur écrit un `.md` (`SDMarkdownWriter` dans `ProjectContext.write_document_to_file`) ;
- `get_editable_document_extensions()` liste `.md` ;
- le surveillant de fichiers suit `.md` et `.gra.md`.

**Base de connaissances (`kb-platform`, hors dépôt) :** `sdoc_reader.py` ne lit que les `.sdoc`, avec `SDReader` de `strictdoc==0.30.2`. Son `markdown_reader` lit un autre format (Markdown à en-tête YAML). Pour un `.md` de StrictDoc, il faudra lire avec `SDMarkdownReader` et `MarkdownGrammarReader`, et changer les chemins `sdoc_sources` de `mission.yaml`.

## 5. Tâches

Charges : S ½ j, M 1,5 j, L 4 j, comme dans le plan de retrait de RST.

| Id | Tâche | Charge | Risque |
|---|---|---|---|
| N-01 | Décider E-05, E-06, E-08, E-09 (section 3.3) | S | faible |
| N-02 | Convertisseur `developer/tools/sdoc_to_markdown.py` : E-01 à E-04, fusion ou marquage des textes selon N-01, refus clair des fragments, `--check` qui relit et compare les deux arbres (JSON) | M | moyen |
| N-03 | Corriger `MarkdownGrammarWriter` (E-03), avec un test unitaire | S | faible |
| N-04 | Lecteur et rédacteur Markdown : plusieurs textes par corps (E-05 b), ordre des champs méta (E-07), avec mise à jour de `spec/Markdown.md` et des tests d'intégration | L | moyen |
| N-05 | Code du fork qui suppose `.sdoc` (section 4), un test par écran ou commande | M | moyen |
| N-06 | Essai sur une copie de REQ_02 : rendu HTML, export Word ouvert dans Word, liens, commentaires, versions, édition dans le serveur (Milkdown) | M | moyen |
| N-07 | Migration de REQ_02 (section 6), recalcul de la ligne de base des liens suspects | S | moyen |
| N-08 | Profil Word et `kb-platform` : chemins, lecteur `.md` | M | moyen |
| N-09 | Documentation : guide utilisateur (le format `.md` devient le format conseillé), notes de version, `architecture/` | S | faible |
| N-10 | Documentation de StrictDoc elle-même en `.md` : optionnel, à décider | M | faible |

Total sans N-10 : environ 12 jours, avec N-04 pour le plus gros morceau.

Ordre : N-01, puis N-03 et N-02, N-04, N-05, N-06, N-07 et N-08, puis N-09. N-04 et N-05 peuvent se faire en parallèle.

## 6. Conseils pour la migration

1. **Garder les MID.** Ils servent de clés aux liens, aux commentaires de relecture et à la base de connaissances. REQ_02 n'a pas encore de MID : ajouter le champ `MID` aux éléments de sa grammaire et laisser StrictDoc les créer en `.sdoc` d'abord, dans un commit à part. Les MID existent alors avant le changement de format, et l'historique des commentaires suit.
2. **Un document pilote d'abord.** REQ_02, puis les autres documents un par un, chacun dans sa demande de fusion.
3. **Deux commits Git par document.** Le renommage d'abord (`git mv x.sdoc x.md`), puis la conversion du contenu, pour que `git log --follow` suive le fichier. Le commit de conversion contient aussi le `.gra.md`.
4. **Une étiquette de version avant la conversion.** Puis le recalcul de la ligne de base des liens suspects juste après, comme pour le retrait de RST (P3-15).
5. **Comparer avant de valider,** avec trois comparaisons :
   - **les arbres :** les deux exports JSON nœud par nœud ;
   - **le texte visible :** de l'export HTML (`visible_text.py` de `~/strictdoc-baseline-markdown-only`) ;
   - **l'export Word :** les paragraphes.

   Le prototype le fait en quelques lignes : N-02 doit l'intégrer (`--check`).
6. **Ne pas convertir un document qui inclut des fragments** tant que E-08 n'est pas tranché.
7. **Vérifier la page de garde.** C'est elle qui porte les textes consécutifs dans les documents importés de Word.
8. **Vérifier `kb-platform` avant de pousser la migration d'un document de mission.** L'indexeur ne lira plus le document tant que N-08 n'est pas fait.

## 7. Critères de fin

- Le convertisseur relit chaque document converti sans erreur, et `--check` ne signale aucune différence de nœud, sauf celles acceptées en N-01.
- Le texte visible de l'export HTML et les paragraphes de l'export Word sont identiques avant et après, pour REQ_02.
- Le serveur ouvre, modifie et enregistre le `.md` ; les écrans de la section 4 marchent sur un `.md`.
- `kb-platform` indexe REQ_02 en `.md`.
- `invoke check` passe, et les tests end2end du serveur qui touchent les documents passent avec `--headless`.

## 8. Non vérifié

- L'export Word du document converti n'a pas été ouvert dans Word : seuls les paragraphes ont été comparés.
- L'édition d'un `.md` dans le serveur (Milkdown, enregistrement, commentaires, versions) n'a pas été essayée.
- Les écrans de la section 4 ont été trouvés par recherche de texte, pas testés.
- `kb-platform` n'a pas été essayé avec un `.md`.
- Le convertisseur prototype est resté hors du dépôt : N-02 le réécrit avec des tests.

## 9. Avancement

Branche `feature/markdown-native`, créée à partir de `feature/markdown-only`.

### Décisions de N-01

Prises sur mes recommandations de la section 3.3, puisque vous avez demandé de commencer le développement. Dites-moi si l'une d'elles ne vous convient pas.

| Écart | Décision |
|---|---|
| E-05 | Étendre le lecteur, le rédacteur et la spécification : plusieurs `**Type**: TEXT` par corps (SDOC-MD-36). |
| E-06 | Accepter la perte des `OPTIONS` et du MID du document. Le convertisseur la signale document par document. |
| E-08 | Laisser en `.sdoc` les documents qui incluent des fragments, et les fragments. Le convertisseur les saute et le dit. |
| E-09 | Accepter : `FORMAT` n'a qu'une valeur (`Sourcecode`, la valeur par défaut) et ne sert qu'à l'export JSON. Le convertisseur ignore cette clé dans sa comparaison. |

### Tâches

| Tâche | État | Détail |
|---|---|---|
| N-01 | fait | voir ci-dessus |
| N-02 | fait | `developer/tools/sdoc_to_markdown.py` : `--output-dir`, `--in-place`, `--rename-only` (le `git mv` seul, pour deux commits), `--check` (relit les deux arbres avec StrictDoc dans un dossier de travail et compare documents, nœuds, champs, relations ; n'écrit rien en cas de différence sans `--force`), `--strict`, `--dry-run`. Le convertisseur laisse les documents avec fragments ou avec une grammaire `.sgra`. Tests : `tests/unit/developer/test_sdoc_to_markdown_script.py` (10 tests) |
| N-03 | fait | sans objet pour le writer (E-03 n'est pas une erreur) ; un test garde `**Prefix**: None` |
| N-04 | fait | plusieurs TEXT par corps (E-05, SDOC-MD-36), marqueur SECTION (E-04, SDOC-MD-37), un `**Type**: TEXT` du corps n'est plus le type du titre, champs remis dans l'ordre de la grammaire (E-07, SDOC-MD-38). Tests unitaires et d'intégration |
| N-05 | fait | voir ci-dessous |
| N-06 | fait | comparaison automatique et édition dans le serveur sur une copie de REQ_02 (voir ci-dessous) |
| N-07 | en attente de votre accord | modifie vos données (`~/strictdoc-data`) |
| N-08 | fait en partie | profil Word : rien à changer ; import Word : arrêt si un `.md` du même nom existe ; `kb-platform` : non modifié (hors dépôt) |
| N-09 | fait | section du guide utilisateur, entrée 13 des notes de version, `architecture/03` |
| N-10 | à décider | documentation de StrictDoc en `.md` : le guide utilisateur et son fragment ne peuvent pas être convertis tant que E-08 n'est pas réglé |

### N-05 : code du fork qui suppose `.sdoc`

| Endroit | Résultat |
|---|---|
| `manage auto-uid` | écrit les UID dans un `.md` (il sautait tout ce qui n'était pas `.sdoc`) ; test d'intégration `auto-uid/requirement_uids/13_markdown_document` |
| versions d'un document (`document_versions`) | lit un `.md` à une étiquette et compare deux versions ; message d'erreur français mis à jour à la main dans le catalogue ; tests unitaires et serveur |
| arbre du projet (`folders`) | renomme et déplace un `.md` (l'extension du document est gardée), refuse un `.gra.md`, et réécrit la ligne `**Grammar**:` d'un document déplacé comme pour un include ; tests unitaires |
| carte du projet, diff de deux arbres | listent les `.md` (deux gabarits) |
| conflits de fusion (`git_sync`) | **non fait** : la fusion nœud par nœud coupe le texte aux marqueurs SDoc. Pour un `.md`, Git fusionne par lignes et le message dit de résoudre avec Git. À faire si les documents `.md` sont édités à plusieurs (décision à prendre : tâche N-11) |
| import Word (`docx_import.py`, `docx_web_service.py`) | écrit toujours un `.sdoc` : laissé tel quel ; à convertir ensuite avec le convertisseur |
| création d'un document dans l'interface | non regardée |
| `strictdoc format`, `manage new`, surveillant de fichiers | déjà en ordre |

### N-06 : essai sur REQ_02 (comparaison automatique)

Copie de `~/strictdoc-data` convertie avec le convertisseur, puis exportée en HTML et en Word :

- le texte visible des quatre vues (document, tableau, traçabilité, traçabilité profonde) est identique mot pour mot ;
- les 2 129 paragraphes de l'export Word sont identiques ;
- `--check` ne signale aucune différence de nœud : 131 exigences, 56 sections, 23 textes.

Édition dans le serveur réel (Chromium, Playwright) sur une copie convertie :

- un texte de la page de garde et l'exigence PUS18-SRV-0010, modifiés avec l'éditeur Milkdown puis enregistrés : le fichier `.md` change aux seules lignes du nœud modifié (le tableau de la page de garde est réécrit en tableau à barres alignées, comme décidé en F-01 ; `[DA1]` devient `\[DA1]`, comme dans un document `.sdoc`) ; relu avec StrictDoc, seul ce nœud diffère dans l'arbre (210 nœuds sur 210) ;
- le commentaire de relecture est lu et affiché (le texte visible est identique) ; l'ajout d'un commentaire par l'interface n'a pas été essayé.

Liens suspects : sur REQ_02, 35 des 131 exigences changent de hash à la conversion (une fin de ligne en plus ou en moins). Sans recalcul, les liens vers elles deviendraient suspects : c'est le rôle de `--baseline`, testé par des tests unitaires (REQ_02 n'a pas de ligne de base).

Non fait : l'ouverture du `.docx` dans Word, la création d'un commentaire par l'interface, `--baseline` sur un vrai projet.

### Résultats de l'essai avec le convertisseur

| Corpus | Résultat de `--check` |
|---|---|
| Copie de REQ_02 | arbre identique : 131 exigences, 56 sections, 23 textes (avant : 15 textes fondus en 1) |
| `docs/` de StrictDoc | arbre identique, 14 documents convertis ; le guide utilisateur et son fragment restent en `.sdoc` (E-08) |
| Document synthétique | les deux documents sont sautés (fragment) |

