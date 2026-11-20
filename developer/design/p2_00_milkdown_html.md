# P2-00 : l'éditeur Milkdown garde-t-il le HTML ?

Étude du 2026-11-20, branche `feature/markdown-only`. Conclusion : oui, sans extension. L'éditeur conserve le HTML
de bout en bout. Il l'affiche en revanche comme du texte source, pas comme un encadré rendu.

## Méthode

`developer/milkdown/playwright/check_html_blocks.py` charge le bundle commité
(`strictdoc/features/milkdown/assets/milkdown/`) dans Chromium 131 avec Playwright 1.49.1. Pour chaque échantillon, il
met le Markdown dans la zone de texte cachée d'un `<sdoc-markdown-editor>`, comme le fait le formulaire, puis lit :

1. le Markdown que l'éditeur écrit à l'ouverture du champ ;
2. le Markdown après une modification ailleurs dans le champ (un paragraphe ajouté) ;
3. la valeur envoyée par le formulaire.

Aucun serveur StrictDoc n'est nécessaire. 21 échantillons, 84 contrôles, tous passent.

## Résultats

- **Champ non modifié :** le formulaire renvoie le texte d'origine octet pour octet (comportement existant de
  `entry.js`, la base de comparaison est ce que l'éditeur écrit à l'ouverture).
- **Champ modifié :** tout le HTML des échantillons ressort identique : `div` avec classes et attributs, `p` interne,
  `dl`/`dt`/`dd` sur une ligne ou plusieurs, `aside`, `details`/`summary`, `figure`, `table` inconnue (avec liste dans
  une cellule), `sub`, `sup`, `span class`, `kbd`, `mark`, `br`, commentaires HTML en bloc et en ligne (dont
  `<!-- sdoc-comment: ... -->`), `<script>`.
- **Marqueurs StrictDoc :** `[LINK: UID]` et `[ANCHOR: id, "titre"]` restent intacts, y compris dans un `div`. Une
  équation `$$ ... \tag{1} $$` reste intacte.
- **Markdown dans un bloc HTML :** quand l'ouverture du `div` est suivie d'une ligne vide, le contenu est du Markdown
  normal, lu et réécrit par l'éditeur. Le bloc de code et la liste à l'intérieur sont conservés.

## Ce que l'éditeur change autour du HTML

Jamais le HTML lui-même, seulement le Markdown voisin :

- une nouvelle ligne finale est ajoutée au texte ;
- une liste `- a` est réécrite `* a` ;
- des crochets dans du texte sont échappés : `<sup>[1]</sup>` devient `<sup>\[1]</sup>` (même rendu).

Le premier enregistrement d'un champ modifié produit donc un diff Git sur ces points, comme avant pour du Markdown
ordinaire (F-01).

## Comment l'éditeur l'affiche

Chaque balise HTML devient un nœud en ligne, non éditable (`data-type="html"`), qui montre sa source : `<div class="...">`.
Un encadré est donc trois blocs : la ligne d'ouverture, le contenu en Markdown rendu, la ligne de fermeture `</div>`.
Une balise en ligne (`<sub>`, `<sup>`) devient deux petits nœuds de part et d'autre du texte. L'auteur peut déplacer ou
supprimer ces nœuds, pas modifier les attributs d'une balise.

Il n'y a pas de perte, mais ce n'est pas un rendu WYSIWYG. Un encadré qui s'affiche comme un encadré est le travail de
P2-22.

## Conséquences pour le plan

- P2-00 conclut que l'éditeur garde le HTML : la condition de sortie de la phase 2 est remplie, P2-10 peut commencer.
- Aucune extension n'est nécessaire pour la conservation. P2-22 reste facultatif pour le confort (encadré rendu,
  insertion d'un type d'encadré). Je propose de le garder à l'effort L et de le décider après P2-10, quand les encadrés
  existeront dans les documents.
- F-01 : le diff Git à la première édition (liste `*`, ligne finale, crochets) est confirmé. Aucun risque pour le HTML.

## Non vérifié

- La saisie à la main à l'intérieur d'un nœud HTML ou autour de lui : seule une modification programmatique
  (`replaceRange`) est simulée.
- Le collage depuis Word, un texte avec des lignes indentées de 4 espaces (qui deviennent un bloc de code en
  Markdown), et le comportement sur un très gros champ.
- Firefox et Safari : seul Chromium a été utilisé.
