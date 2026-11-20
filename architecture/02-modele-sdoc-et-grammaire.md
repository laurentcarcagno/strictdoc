# 02 - Modèle SDoc, grammaire, lecture et écriture

Fichiers : `strictdoc/backend/sdoc/`. C'est le coeur du modèle de données. Tous
les autres formats (Markdown, RST, ReqIF, DOCX, ...) produisent ou consomment
les mêmes objets.

## Le format `.sdoc`

Exemple minimal (grammaire réelle : `backend/sdoc/grammar/grammar.py`) :

```
[DOCUMENT]
MID: 5a2c...                    # optionnel, identifiant stable (hex 32)
TITLE: Exigences système
UID: SYS                        # le bloc DocumentConfig est optionnel
OPTIONS:
  MARKUP: Markdown              # RST | Text | HTML | Markdown
  ENABLE_MID: True

[GRAMMAR]                       # optionnel
ELEMENTS:
- TAG: REQUIREMENT
  FIELDS:
  - TITLE: UID
    TYPE: String
    REQUIRED: True
  - TITLE: STATEMENT
    TYPE: String
    REQUIRED: True
  RELATIONS:
  - TYPE: Parent

[REQUIREMENT]
UID: SYS-001
STATUS: Active
TITLE: Titre
STATEMENT: >>>
Le système doit ...
<<<
RELATIONS:
- TYPE: Parent
  VALUE: SYS-000
  ROLE: refines
```

Éléments de la syntaxe :

| Bloc | Rôle |
|---|---|
| `[DOCUMENT]` | une fois, en tête. `MID`, `TITLE`, `DocumentConfig`, `VIEWS`, `GRAMMAR` |
| `OPTIONS:` | `ENABLE_MID`, `RELATION_FIELD`, `MARKUP`, `AUTO_LEVELS`, `LAYOUT`, `VIEW_STYLE`, `NODE_IN_TOC`, `DEFAULT_VIEW` |
| `METADATA:` | paires clé/valeur libres (le fork y range `KIND`, `REVIEWERS`, `CREATED_BY`, voir [08](08-features-fork-isis.md)) |
| `[GRAMMAR]` | schéma propre au document, ou `IMPORT_FROM_FILE: x.sgra` |
| `[<TYPE>]` | un nœud (`SDocNode`). Le type est un nom en majuscules (`REQUIREMENT`, `TEXT`, `SECTION`, `TEST_CASE`, ...) |
| `[[<TYPE>]] ... [[/<TYPE>]]` | nœud composite, qui contient d'autres nœuds |
| `[DOCUMENT_FROM_FILE]` | inclut un autre `.sdoc` (`FILE: autre.sdoc`) |
| `RELATIONS:` | `Parent`, `Child` (avec `ROLE`) et `File` (expérimental) |
| `[LINK: uid]`, `[ANCHOR: id, titre]` | liens et ancres dans le texte multiligne |

Le multiligne s'écrit entre `>>>` et `<<<`. Le `[SECTION]` de l'ancienne syntaxe
n'est plus lu : `process_section` lève une erreur qui renvoie au guide de
migration, et les sections sont des nœuds composites.

Les champs réservés (`model.py`, `RequirementFieldName`) sont `MID`, `UID`,
`PREFIX`, `LEVEL`, `STATUS`, `TAGS`, `TITLE`, `STATEMENT`/`DESCRIPTION`/`CONTENT`
(alias), `RATIONALE`, `COMMENT`. Tout autre champ est un champ « meta ».

## Construction du métamodèle

```
SDocGrammarBuilder.create_grammar()          grammar/grammar_builder.py
  = DOCUMENT_GRAMMAR + GRAMMAR_GRAMMAR + SECTION_GRAMMAR
    + FREE_TEXT_PARSER_GRAMMAR + TEXT_TYPES_GRAMMAR
    + STRICTDOC_BASIC_TYPE_SYSTEM
```

Trois métamodèles textX existent au chargement du module :

| Lecteur | Grammaire | Classes |
|---|---|---|
| `SDReader.meta_model` (`reader.py`) | complète | `DOCUMENT_MODELS` (`models/constants.py`) |
| `SDocGrammarReader.meta_model` (`grammar_reader.py`) | `[GRAMMAR]` seul, fichiers `.sgra` | `GRAMMAR_MODELS` |
| `SDFreeTextReader` (`free_text_reader.py`) | texte libre | `FreeTextContainer`, `InlineLink`, `Anchor` |

La grammaire est une suite de chaînes Python avec des expressions régulières ;
`REGEX_UID` y est défini. Les types de champs (`BooleanChoice`, `Reference`,
`ParentReqReference`, `FileEntry`, ...) sont dans `grammar/type_system.py`.

Pour changer la syntaxe : modifier la grammaire, la classe de modèle
correspondante dans `models/`, l'enregistrer dans `models/constants.py`, le
processeur (`processor.py`) si besoin, le `writer.py`, puis les tests
`tests/integration/features/sdoc/` et `tests/unit/strictdoc/backend/sdoc/`.

## Lecture : `SDReader`

`SDReader.read_from_file(path, project_config)` (`reader.py`) :

1. `PickleCache.read_from_cache(path, config, "sdoc")` : si le fichier n'a pas
   changé (mtime et taille, sinon MD5), renvoie l'objet déjà analysé.
2. Sinon lit le fichier (`file_open_read_utf8`), retire un éventuel BOM, appelle
   `meta_model.model_from_str`. Une erreur textX devient `StrictDocException`.
3. `SDocParsingProcessor` (`processor.py`) s'exécute pendant le parsing
   (processeurs d'objets textX) : crée la grammaire par défaut si absente,
   relie chaque nœud à sa `DocumentReference`, marque `ng_has_requirements`
   (monte dans l'arbre jusqu'à la racine), garde positions ligne/colonne,
   vérifie les `DOCUMENT_FROM_FILE` (extension `.sdoc`, fichier existant),
   interdit `..` et `/` dans `IMPORT_FROM_FILE`.
4. `fixup_composite_requirements` ajoute l'élément de grammaire `SECTION` si le
   document contient un nœud composite.
5. `drop_textx_meta(sdoc)` retire les champs textX non picklables
   (`helpers/textx.py`). Sans cela le document ne passerait pas entre processus.
6. `sdoc.build_search_index()` précalcule l'index de recherche du document.
7. `PickleCache.save_to_cache(...)`.

`ParseContext` porte l'état de la lecture : fichier, grammaire courante,
fragments `DOCUMENT_FROM_FILE`, `migrate_sections`.

## Modèle objet (`models/`)

| Classe | Fichier | Rôle |
|---|---|---|
| `SDocDocument` | `document.py` | racine : `title`, `config`, `view`, `grammar`, `section_contents`, `meta` (`DocumentMeta`), `reserved_mid`, `included_documents`, `search_index` |
| `DocumentConfig` | `document_config.py` | UID, VERSION, DATE, CLASSIFICATION, PREFIX, options (`markup`, `enable_mid`, `auto_levels`, ...), `custom_metadata` |
| `DocumentView` | `document_view.py` | vues nommées : quels champs afficher par type de nœud |
| `DocumentGrammar` | `document_grammar.py` | éléments (`GrammarElement`), `create_default()` (REQUIREMENT, TEXT, SECTION), `create_for_test_report()` |
| `GrammarElement` | `grammar_element.py` | un type de nœud : champs typés, relations autorisées, propriétés (`IS_COMPOSITE`, `PREFIX`, `VIEW_STYLE`) |
| champs de grammaire | `grammar_element.py` | `GrammarElementFieldString`, `...SingleChoice`, `...MultipleChoice`, `...Tag` ; relations `GrammarElementRelationParent/Child/File` |
| `SDocNode` | `node.py` | un nœud : `node_type`, `ordered_fields_lookup` (nom de champ vers liste de `SDocNodeField`), `relations`, `section_contents`, `reserved_mid`, `autogen` |
| `SDocCompositeNode` | `node.py` | sous-classe de `SDocNode` avec enfants |
| `SDocNodeField` | `node.py` | une valeur : `field_name`, `parts` (texte, `InlineLink`, `Anchor`), origine document ou code source |
| `Reference`, `ParentReqReference`, `ChildReqReference`, `FileReference` | `reference.py` | relations ; chacune porte un `ref_uid`, un `role` et un `mid` |
| `InlineLink`, `Anchor` | `inline_link.py`, `anchor.py` | liens `[LINK: ]` et ancres `[ANCHOR: ]` dans le texte |
| `DocumentFromFile` | `document_from_file.py` | fragment inclus |
| `SDocObjectFactory` | `object_factory.py` | `create_document`, `create_requirement`, `create_requirement_from_dict` : construit documents et nœuds par programme (convertisseurs, serveur) |
| interfaces | `model.py` | `SDocNodeIF`, `SDocDocumentIF`, `RequirementFieldName` |

Points d'attention :

- **Identifiants.** `MID` (`helpers/mid.py`) est une chaîne hexadécimale de 32
  caractères, créée avec `MID.create()`. Elle est stable et sert de clé interne
  (URL du serveur, verrous, formulaires). L'`UID` est l'identifiant humain, qui
  peut changer. `mid_permanent` dit si le MID est écrit dans le fichier.
- **Champs dynamiques.** Un nœud n'a pas d'attributs par champ : tout passe par
  `ordered_fields_lookup`. `reserved_uid`, `reserved_title`, `reserved_statement`
  sont des propriétés qui lisent ce dictionnaire. `set_field_value()` met à jour
  un champ (et la liste d'ordre).
- **`ng_*`.** Les attributs préfixés `ng_` sont calculés après lecture
  (positions, document d'origine, niveau résolu, `ng_has_requirements`).
- **`autogen`.** Un nœud créé à partir d'un rapport de test ou de commentaires de
  code n'est pas écrit sur disque par `SDWriter` et n'est pas modifiable
  (`TraceabilityIndex.can_edit_node` répond non).
- **Documents inclus.** Un document peut en inclure un autre via
  `DOCUMENT_FROM_FILE`. `get_parent_or_including_document()` donne le document
  qui possède le nœud, `get_including_document()` celui qui l'affiche.

## Validation

`validations/sdoc_validator.py`, classe `SDocValidator` :

| Méthode | Vérifie |
|---|---|
| `validate_document` | configuration, vues, grammaire, puis chaque nœud |
| `validate_grammar_from_file` | un `.sgra` |
| `validate_grammar_element` | cohérence d'un élément de grammaire |
| `validate_node` | type connu, composite ou non selon la grammaire, champs déclarés, champs obligatoires, types de relations autorisés |
| `validate_requirement_field` | valeur d'un champ à choix (simple, multiple, tags) |

Les erreurs sont des `StrictDocSemanticError` (`error_handling.py`, 560 lignes de
fabriques de messages) qui s'impriment avec fichier, ligne et extrait.

## Écriture : `SDWriter`

`writer.py` : `SDWriter(project_config, node_filter=None)`.

| Méthode | Rôle |
|---|---|
| `write(document)` | texte `.sdoc` |
| `write_with_fragments(document)` | texte et dictionnaire des fragments `DOCUMENT_FROM_FILE` à écrire à côté |
| `write_to_file(document)` | écrit `document.meta.input_doc_full_path` et les fragments |

Le writer saute les nœuds `autogen` et applique le filtre de nœuds de l'export.
Il écrit les champs dans l'ordre de `ordered_fields_lookup`. Le serveur passe par
`ProjectContext.write_document_to_file` (voir [05](05-serveur-web.md)), qui
choisit `SDWriter` ou `SDMarkdownWriter` selon l'extension.

## Fichiers voisins

| Fichier | Rôle |
|---|---|
| `sdoc_format.py` | `SDocFormat` : lecture, grammaire `.sgra`, export `sdoc`, sortie de `convert` |
| `pickle_cache.py` | cache disque des documents et des fichiers source (voir [10](10-donnees-et-persistance.md)) |
| `node_filter.py` | `NodeFilter` : nœuds retenus par `--filter-nodes` |
| `document_reference.py` | `DocumentReference` : pointeur différé vers le document, rempli après le parsing |
| `errors/document_tree_error.py` | `DocumentTreeError` : erreur qui arrête l'export avec un message imprimé |
