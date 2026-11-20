# 06 - Frontend et export HTML

Fichiers : `strictdoc/export/html/` (5 800 lignes Python, 300 fichiers de
templates et de ressources), `strictdoc/features/*/templates` et
`features/*/assets`, `developer/milkdown/`.

Il n'y a pas de frontend séparé. Le HTML est rendu côté serveur par Jinja2, les
mises à jour partielles passent par Turbo, et le JavaScript est du JS simple, sans
framework ni étape de build (sauf le bundle de l'éditeur Markdown).

## Rendu : de l'objet au fichier HTML

```
HTMLGenerator (export/html/html_generator.py)
  export_complete_tree()      export statique : assets, index de recherche, documents en parallèle,
                              arbre du projet, carte, matrice, couverture source
  export_single_document()    un document : jusqu'à 5 pages
      DocumentType.DOCUMENT   <doc>.html           generators/document.py
      DocumentType.TABLE      <doc>-TABLE.html     generators/document_table.py
      DocumentType.TRACE      <doc>-TRACE.html     features/trace/generator.py
      DocumentType.DEEPTRACE  <doc>-DEEP-TRACE.html features/deep_trace/generator.py
      DocumentType.PDF        <doc>-PDF.html       features/html2pdf/generator.py
  export_project_tree_screen, export_project_map, export_requirements_coverage_screen,
  export_source_files_screens, export_source_coverage_screen, export_static_html_search_index
```

Chaque page est produite par un **objet vue** (`view object`) passé au template.
Le template appelle ses méthodes (`view_object.render_node_link(...)`,
`render_static_url(...)`, `table_of_contents()`, ...).

| Objet vue | Fichier | Pour |
|---|---|---|
| `DocumentScreenViewObject` | `generators/view_objects/document_screen_view_object.py` (1 200 lignes) | pages document, table, trace ; aussi les réponses Turbo (`render_updated_nodes_and_toc`, `render_update_document_content_with_moved_node`) ; découpage en tranches (`document_content_chunks`) pour les gros documents |
| `AppScreenViewObject` | `generators/view_objects/app_screen_view_object.py` | le cadre (barre latérale et en-tête du projet) autour d'un écran qu'une feature rend elle-même ; voir plus bas |
| `ProjectTreeViewObject` | `features/project_index/view_object.py` | arbre du projet (`index.html`) |
| `ServerErrorViewObject` | `generators/view_objects/server_error_view_object.py` | pages d'erreur |
| `ProjectStatisticsViewObject`, `TraceabilityMatrixViewObject`, `SourceCoverageViewObject`, `SourceFileViewObject`, `SearchScreenViewObject`, `TreeMapViewObject`, `DiffScreenViewObject`, `DiffScreenResultsViewObject`, `NestorViewObject` | dans leur feature | écrans propres |

### Écrans de feature dans le cadre du projet (`AppScreenViewObject`)

Les écrans que le serveur rend sans passer par un document (liens suspects,
hiérarchie, commentaires, gestion de configuration, journal d'audit, page d'un
item, versions d'un document, page 403) étaient des pages HTML nues. Ils passent
maintenant par `render_app_screen(...)` (même fichier) :

```
render_app_screen(jinja_environment=, project_config=, title=, viewtype=,
                  content_template="features/<x>/<page>.jinja.html", **variables)
  1. rend le template de la feature : le contenu de la page seulement
  2. AppScreenViewObject(title, viewtype, content).render_screen()
     -> _shared/app_screen.jinja.html (hérite de base.jinja.html) :
        barre latérale (_shared/nav.jinja.html), en-tête (components/header),
        puis le contenu dans <div class="app_screen" data-testid="app-screen">
```

`viewtype` devient `data-viewtype` du `<body>` et marque l'entrée courante de la
barre latérale. `get_document_level()` renvoie 0 (les URL sont à la racine).
Un nouvel écran de feature utilise cette fonction plutôt qu'une page HTML écrite
à la main.

### Barre latérale en groupes

`_shared/nav.jinja.html` construit quatre groupes ; un groupe sans entrée
n'est pas affiché.

| Groupe | Entrées (conditions) |
|---|---|
| Analysis | recherche (`SEARCH`), matrice de traçabilité (`TRACEABILITY_MATRIX_SCREEN`), hiérarchie des documents (serveur et `document_hierarchy` non vide), couverture des sources (`REQUIREMENT_TO_SOURCE_TRACEABILITY`), statistiques et carte du projet (l'ancien « Tree map ») si la `Feature` est activée |
| Review | commentaires (serveur et `COMMENTS`), liens suspects (serveur et `suspect_links`) |
| Versions | comparer les versions (l'ancien « Diff », `DIFF`), gestion de configuration (serveur et `GIT`) |
| Administration | membres (serveur avec `members_admin`), journal d'audit (serveur avec `auth_mode="proxy"`) ; groupe caché aux autres rôles que l'administrateur |

« All projects » (`/_projects`) et la déconnexion sont sous les groupes.

### En-tête d'un document

`components/header/document_context.jinja` : projet, puis dossiers du document
(`DocumentScreenViewObject.get_document_folders()`), puis, avec la fonction `GIT`,
la dernière étiquette de version du dépôt qui contient le document
(`get_document_version()` lit `features/git_config/document_version.py`,
`latest_version_of_file`, une fois par page) ou « No version ». Avec un serveur,
l'étiquette est un lien vers `/versions/<mid>` (`get_versions_url()`). Le nom du
projet garde son `id` et n'est pas un lien : les tests end2end cliquent dessus
pour sortir d'un éditeur.

### Petit écran

Jusqu'à 768 px (`_static/responsive.css`, `_static/mobile_nav.js`) la page montre
soit le contenu soit le menu (barre latérale, arbre, table des matières), selon
le bouton `#layout-menu-toggle` de `base.jinja.html`. La balise `viewport` a été
ajoutée. La barre latérale est toujours dépliée sur petit écran ; l'état replié
mémorisé (`sdoc-nav-collapsed`) revient au-dessus du seuil. Les tableaux des
écrans du cadre défilent dans leur boîte.

### Rendeurs

| Classe | Rôle |
|---|---|
| `LinkRenderer` (`renderers/link_renderer.py`) | tous les liens : `render_url`, `render_static_url`, `render_node_link`, ancres locales, liens vers fichiers source et plages, liens Doxygen. Prend `root_path` (profondeur du document) et `static_path` |
| `MarkupRenderer` (`renderers/markup_renderer.py`) | rend un champ selon le balisage du document : `RstToHtmlFragmentWriter`, `MarkdownToHtmlFragmentWriter` ou texte brut ; gère `[LINK:]` et `[ANCHOR:]` |

### Gabarits Jinja

`html_templates.py` : `HTMLTemplates.create(...)` renvoie `NormalHTMLTemplates`
(petits projets) ou `CompiledHTMLTemplates` (les templates sont précompilés dans
`<cache>/jinja/<hash>` et rechargés avec `ModuleLoader`, invalidés quand le
code StrictDoc est plus récent). L'environnement a `StrictUndefined` (une
variable absente est une erreur), `autoescape=True`, l'extension
`AssertExtension` et l'extension i18n (`{% trans %}`, `_()`).

Chemins de recherche : `HTML_TEMPLATE_DIRS` (`core/environment.py`) : le dossier
commun puis un dossier `templates` par feature. Les noms de templates ne sont pas
préfixés par feature : ils sont `features/<nom>/...` par convention, à l'intérieur
du dossier de la feature.

Organisation de `export/html/templates/` :

| Dossier | Contenu |
|---|---|
| `base.jinja.html` | squelette : métadonnées, feuilles de style communes, scripts conditionnels (rôles, LLM, commentaires), `{% block head_css %}` |
| `screens/document/{document,table,_shared}` | écrans : contenu du document, vue table, barre latérale, TOC, menu des vues |
| `components/` | composants réutilisables : `node`, `node_content`, `node_field`, `form` (champs, lignes), `modal`, `field`, `button`, `badge`, `confirm`, `header`, `section`, `text_node`, `grammar_form`, `static_search`, `switch`, ... |
| `actions/` | réponses Turbo : `document/*` (créer, éditer, déplacer, supprimer un nœud ; config ; grammaire), `table/*` (édition de cellule), `node/show_full_node`, `project_index/*` |
| `_shared/` | navigation latérale (`nav.jinja.html`), arbre, favicon, étiquettes |
| `autocomplete`, `error`, `markup`, `rst`, `website`, `websocket.jinja.html` | divers |

Les noms `stream_*.jinja.html` contiennent des `<turbo-stream>`. Les éléments
HTML personnalisés (`<sdoc-node>`, `<sdoc-form>`, `<sdoc-form-row>`,
`<sdoc-modal>`, `<sdoc-tab-content>`, ...) sont des balises de structure
stylées en CSS, sans JavaScript d'enregistrement, sauf les cas notés plus bas.

## Formulaires : les objets de formulaire

`export/html/form_objects/` : un objet par formulaire. Il lit la requête,
valide, et se rend lui-même ou fournit les valeurs au template. Tous héritent
de `ErrorObject` (`server/error_object.py`).

| Objet | Formulaire |
|---|---|
| `RequirementFormObject` (1 165 lignes) | création, édition, clonage d'un nœud : `create_from_request`, `create_new`, `create_from_requirement`, `clone_from_requirement`, `validate(...)` (UID unique, champs obligatoires, choix valides, cycles de relations, révision concurrente, politique de hiérarchie du fork) |
| `GrammarFormObject`, `GrammarElementFormObject` | édition de la grammaire d'un document |
| `DocumentConfigFormObject` | options du document |
| `IncludedDocumentFormObject` | document inclus |
| `rows/*` | lignes de formulaire de grammaire (champ réservé, champ personnalisé, relation) |

Schéma : `POST` -> `FormObject.create_from_request` -> `validate` -> erreurs :
réponse Turbo avec statut 422 ; sinon une commande de `core/transforms` modifie
le modèle.

## Turbo et JavaScript

`_static/turbo.min.js` (Hotwired Turbo, copié tel quel). Les formulaires
envoient des requêtes ; le serveur répond `text/vnd.turbo-stream.html`, et Turbo
remplace les éléments ciblés. `server/helpers/turbo.py` : `render_turbo_stream(content, action, target)`
avec `action` dans `append`, `replace`, `update`.

`_static/app_core.js` définit `window.StrictDoc` (racine partagée : `events`,
`bus`, `onInsert`, `config`, `contentViewport`, `search`, `project`). Les autres
scripts restent locaux et ne communiquent que par ce contrat (bus
d'évènements `toc:state-changed`, `toc:fragment-resolved`, ...). Le dépôt a
retiré Stimulus (tâche `20260724_stimulus_free`) ; `autocompletable_field.js`
en est un portage.

| Script | Rôle |
|---|---|
| `collapsible_toc.js`, `collapsible_tree.js`, `toc_highlighting.js`, `toc_chunk_navigation.js` | table des matières, arbre du projet, surbrillance, navigation par tranches |
| `content_viewport_restoration.js` | garde la position de lecture quand le contenu au-dessus change de hauteur |
| `editable_field.js`, `restorable_field.js`, `deletable_field.js`, `movable_field.js`, `autocompletable_field.js` | champs de formulaire |
| `table_view.js`, `table_view_edit.js` | vue table : colonnes masquées (localStorage et paramètre d'URL), édition de cellule avec gestion des réponses tardives |
| `mobile_nav.js` | bouton du menu sur petit écran |
| `modal.js`, `dropdown_menu.js`, `tabs.js`, `resizable_bar.js`, `nav.js`, `scroll_into_view.js`, `action_button_guard.js`, `copy_to_clipboard.js` | composants d'interface par écouteurs délégués |
| `draggable_list.js`, `move_node_tree.js` | déplacement de nœuds |
| `media_zoom.js`, `zoomable.js`, `pan_with_space.js` | zoom d'images et de diagrammes, déplacement |
| `static_html_search.js` | recherche du site statique : index chargé depuis `static_html_search_index.js`, stocké dans IndexedDB, invalidé par `search_index_timestamp` |
| `project_tree_preserve_scroll.js` | mémorise le défilement de l'arbre |

CSS : `base.css`, `layout.css`, `responsive.css`, `content.css`, `node.css`, `node_content.css`,
`element.css`, `form.css`, `table_view.css`, `pygments.css`, `autogen.css`,
`requirement__temporary.css`, `move_node_tree.css`, `media_zoom.css`.
Polices IBM Plex Sans et Mono (woff2 sous `_static/fonts`), qui remplacent
Orbitron et Ubuntu dans le fork. Les décisions de design sont dans
`developer/design/DESIGN.md`, `DESIGN.json` et `PRODUCT.md`.

Les ressources d'une feature vivent dans `features/<nom>/assets/<nom>/` et sont
copiées dans `output/html/_static/` par `HTMLGenerator.export_strictdoc_assets`
(liste `HTML_STATIC_DIRS`).

## Export statique ou serveur : une seule base de code

La balise `<meta name="strictdoc-export-type" content="webserver|static">` et
`project_config.is_running_on_server` pilotent les différences : en mode
statique les boutons d'édition sont absents et les documents longs sont
exportés en tranches (`document_chunk_lazy_placeholder_static.jinja.html`,
`static_chunk_relative_path`).

Chargement paresseux (`lazy_document_loading_threshold`, 200 nœuds par défaut) :
`DocumentScreenViewObject.is_chunked_rendering()` découpe le contenu ;
la route `/fragments/document/{mid}/chunk` sert les tranches au serveur.

## Internationalisation

`features/i18n` : un seul langage par processus (`language` de la configuration,
ou `STRICTDOC_LANGUAGE`), `en` par défaut, `fr` fourni
(`locales/fr/LC_MESSAGES/strictdoc.po`). Le texte source est anglais, dans les
templates (`_()`, `{% trans %}`) et le code (`gettext`). Les scripts lisent
`window.sdocT("Texte")` ; `base.jinja.html` y injecte le catalogue.
`developer/i18n/update_catalogs.py` met à jour les `.po`. Un texte non traduit
reste anglais.

## Éditeur Markdown (Milkdown), ajout du fork

Élément `<sdoc-markdown-editor>` (Milkdown Crepe), utilisé pour les champs de
contenu (`STATEMENT`, `DESCRIPTION`, `CONTENT`) des documents `MARKUP: Markdown`.
Les autres documents gardent le champ texte simple.

- Sources : `developer/milkdown/src/*.js` (point d'entrée `entry.js`) ; build :
  `cd developer/milkdown && npm ci && npm run build` (`build.mjs`).
- Résultat **commité** dans `strictdoc/features/milkdown/assets/milkdown/`
  (`milkdown.js` environ 1,6 Mo, `milkdown.css`, `milkdown_fonts.css`, `milkdown.js.LEGAL.txt`, et
  `diagram.js`/`diagram.css`), pour que le paquet installé n'ait pas besoin de
  Node. **Toute modification de `src/` impose de reconstruire et de commiter le bundle.**
- Modules : `sdoc_markers.js` (garde `[LINK:]` et `[ANCHOR:]`), `tables.js`,
  `table_commands.js`, `table_bar.js` (tableaux : en-têtes, fusion, couleurs,
  alignement ; un tableau simple s'écrit en pipe table, sinon en `<table>`
  HTML), `alignment.js`, `image_caption.js`, `toolbar_tooltips.js`,
  `languages.js`, `katex_stub.js`.
- Éditeur de diagrammes (maxGraph, chargé à la demande) : `diagram_*.js`. Un
  diagramme est une image `diagram_<id>.svg` dans les assets du nœud, dont le
  modèle est stocké dans `<desc id="sdoc-diagram">`.
- Un champ non modifié est renvoyé à l'octet près ; un champ modifié est
  ré-écrit par Milkdown. Les limites sont dans `developer/milkdown/README.md`.
- Inclusion : `components/form/field/markdown_editor/index.jinja` et
  `screens/document/document/index.jinja`.

## Autres bibliothèques embarquées

`features/mathjax` (formules, déprécié), `features/mermaid`,
`features/plantuml` (diagrammes), `features/nestor` (graphe Nestor,
`bundle.umd.js`). Les trois premières sont des fichiers statiques chargés selon
les options du document et du projet.

## Où modifier quoi

| Je veux | Je touche |
|---|---|
| un nouvel écran de lecture | un objet vue + un générateur dans la feature, un `Feature` ou une branche de `generate_document`, un template, l'entrée dans `HTML_TEMPLATE_DIRS` |
| un écran de feature hors document (liste, page d'item, formulaire plein écran) | `render_app_screen(...)` avec un template de contenu dans `features/<x>/templates/features/<x>/`, une entrée dans le groupe voulu de `nav.jinja.html` |
| un champ de formulaire | `RequirementFormObject`, `components/form/field/...`, le transform `update_requirement.py` |
| un comportement JS | un fichier `_static/*.js` ou `features/<x>/assets`, chargé depuis `base.jinja.html` ou le template de l'écran ; passer par `StrictDoc.onInsert` pour les formulaires insérés par Turbo |
| un texte traduit | le template (`_()`) puis `developer/i18n/update_catalogs.py` |
| l'éditeur Markdown | `developer/milkdown/src`, puis build et commit du bundle |
