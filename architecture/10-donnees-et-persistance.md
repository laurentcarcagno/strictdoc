# 10 - Données et persistance

StrictDoc n'a **pas de base de données**. La source de vérité est un ensemble de
fichiers texte du projet, rangés dans Git. Tout le reste (index de traçabilité,
HTML, caches) se recalcule. Ce document dit où chaque chose vit.

## Vue d'ensemble

| Donnée | Où | Durée de vie | Reconstructible |
|---|---|---|---|
| Documents | fichiers du projet : `.sdoc`, `.md`, `.markdown`, grammaires `.sgra` et `.gra.md` | permanente | non (c'est la donnée) |
| Images et pièces jointes | dossier `_assets/` voisin des documents ; sous-dossier par nœud | permanente | non |
| Marqueur de dossier | `.sdoc-folder` dans un dossier vide | permanente | non |
| Ligne de base des liens suspects | `trace_baseline.json` à la racine du projet | permanente | non |
| Configuration | `strictdoc_config.py` (ou `strictdoc.toml`, obsolète) à la racine | permanente | non |
| Registre des projets | un fichier Python avec `create_projects()` | permanente | non |
| Projets et membres créés à chaud | `projects.json` à côté du registre | permanente | non |
| Journal d'audit | `audit.jsonl` dans `audit_dir` ou `output_dir` | rotation par taille | non |
| Journal d'audit LLM | `llm_audit.jsonl` à côté du précédent | rotation | non |
| Réglages du lanceur Tk | `.strictdoc_launcher.json` | permanente | oui |
| Index de traçabilité, graphe | mémoire du processus | processus | oui |
| Documents analysés | cache pickle `<cache>/sdoc/`, `/grammar/`, `/source_file/` | jusqu'à changement du fichier | oui |
| Dépendances fichier | `<cache>/dependencies` | permanente | oui |
| Templates compilés | `<cache>/jinja/<hash>/` | jusqu'à mise à jour du code | oui |
| Pages HTML | `output/html/` (export) ou `output/server/html/` (serveur) | | oui |
| PDF | `output/html2pdf/{html,pdf}/` | | oui |
| Autres exports | `output/<format>/` (`sdoc`, `excel`, `reqif`, `json`, `spdx`, `markdown`...) | | oui |
| Jobs de l'assistant, résultats récents, compteurs de révision, limites de débit | mémoire | processus (jobs : 1 h après la fin) | oui |
| Index de recherche statique | `static_html_search_index.js`, copie en IndexedDB du navigateur | | oui |

## Formats de fichiers de projet

Voir [02](02-modele-sdoc-et-grammaire.md) pour `.sdoc` et
[03](03-formats-et-backends.md) pour Markdown. Règles de rangement :

- Un document appartient à un dossier d'entrée. `DocumentFinder` calcule pour
  chacun un `DocumentMeta` : `input_doc_rel_path`, `input_doc_assets_dir_rel_path`
  (`<montage>/_assets`), `output_document_dir_rel_path`.
- Les images d'un nœud : sous-dossier de `_assets` nommé d'après le MID du nœud
  (si les MID sont activés ou si le MID est permanent), sinon d'après son UID,
  sinon directement dans `_assets` (`resolve_uploaded_asset_subfolder` dans
  `main_router.py`). Un nœud qui n'existe pas encore n'a pas de sous-dossier.
  `features/git_config/asset_names.py` retrouve les dossiers d'un nœud et de ses
  enfants pour les valider et les supprimer avec lui.
- Les fichiers non documents du projet restent ignorés (`exclude_doc_paths`) ;
  le `.gitignore` est ajouté aux exclusions par `validate_and_finalize`.
- Une suppression de dossier ou de document déplace ou efface les fichiers
  (voir `features/folders/folders.py` ; noms réservés : `_assets`, `output`,
  `Output`, `word`).

Le serveur protège ses écritures par les verrous mémoire de
[05](05-serveur-web.md), pas par des verrous de fichier (seul le cache des
copies Git de `diff_and_changelog` utilise `flock`). Il suppose être le seul à
écrire ; l'observateur `--watch` relit un fichier modifié par un tiers. Deux
serveurs sur le même dossier se marcheraient dessus.

## Caches

Le chemin est `project_config.dir_for_sdoc_cache` + version de StrictDoc
(`output/_cache/0.30.2`), ou `<TMPDIR>/strictdoc_cache/<md5 du cwd>` si la
configuration dit `$TMPDIR`. Un dossier par version évite les incompatibilités
de schéma.

### Cache des documents (`backend/sdoc/pickle_cache.py`)

`PickleCache` stocke `PickleCacheEntry(mtime_ns, size, md5, content)` dans
`<cache>/<sdoc|grammar|source_file|...>/<nom>_<md5 du chemin>`. Lecture :

1. même mtime et même taille : renvoie le contenu sans lire le fichier ;
2. sinon compare le MD5 du contenu ; identique : « guérit » l'entrée et renvoie ;
3. sinon `None` (relecture complète).

`helpers/pickle.pickle_load` renvoie `None` si le schéma des classes a changé
(`AttributeError`) : c'est un échec de cache silencieux. Toute autre exception
est une erreur franche qui demande d'effacer le cache.

Utilisateurs : `SDReader`, `SDocGrammarReader`, `SDMarkdownReader` et son lecteur
de grammaire, `SourceFileTraceabilityCachingReader`.

### Dépendances et régénération

`FileDependencyManager` : graphe « ce fichier d'entrée produit ces sorties »,
sauvegardé à chaque export. Au lancement suivant, `resolve_modification_dates`
compare les dates et marque ce qui doit être régénéré. `strictdoc_last_update`
(date du fichier Python, Jinja, HTML ou SVG le plus récent du paquet) invalide
tout si le code de StrictDoc a changé.

### Pickle de configuration du serveur

`server/server.py` écrit `ProjectConfig` dans un fichier temporaire et passe son
chemin dans `PATH_TO_CONFIG`. Le fichier est supprimé à la fermeture (Windows :
ouverture avec `O_TEMPORARY`). La configuration doit donc rester picklable.

## Fichiers JSON et JSON-lines du serveur

| Fichier | Écrit par | Contenu |
|---|---|---|
| `audit.jsonl` | `AuditLog` (`features/roles/audit.py`) | `time`, utilisateur, rôle, route, MID, statut ; jamais le corps de la requête |
| `llm_audit.jsonl` | `LLMAudit` (`features/llm/audit.py`) | un appel de modèle : fournisseur, modèle, local ou non, SHA-256 du prompt, tailles, UID, latence, jetons, statut |
| `projects.json` | `ProjectStore` (`features/projects/store.py`) ; à côté du fichier de registre en production, sinon dans le dossier de sortie | `{"projects": {slug: {title, created_by, created}}, "members": {slug: {utilisateur: rôle}}}` ; écriture atomique (fichier temporaire puis renommage), verrou `RLock` |
| `trace_baseline.json` | `features/hierarchy/suspect.py` | une ligne par lien parent/enfant : SHA-1 du contenu du parent relu. Un fichier hors des nœuds pour que modifier un parent ne touche pas ses enfants et que les conflits Git restent sur une ligne |

## Persistance côté navigateur

| Clé ou base | Script | Contenu |
|---|---|---|
| IndexedDB | `static_html_search.js` | index de recherche, invalidé par `search_index_timestamp` |
| `strictdoc.table.hidden_cols...`, `...hidden_rows...` | `table_view.js` | colonnes et lignes masquées de la vue table |
| `sdoc-page-view` | `page_view.js` | mode de la vue en pages |
| dossiers ouverts (`FOLDERS_KEY`) et défilement de l'arbre | `features/project_index/assets/sidebar_tree.js`, `project_tree_preserve_scroll.js` | état de l'arbre du projet |
| état de la barre latérale | `nav.js` | réduite ou non |

Toutes les lectures sont protégées par `try/catch` (stockage indisponible).

## Git comme historique

Avec l'option `git` ([08](08-features-fork-isis.md)), chaque écriture de
document est commitée par le serveur (auteur unique de la configuration,
messages conventionnels). Les étiquettes `A1`, `A`, `B1`... marquent les
versions d'un document et servent de référence au PDF avec barres de changement.
Les merges sont faits nœud par nœud (`features/git_sync`). L'historique est aussi
lu : la page d'un item lance `git log -L` sur les lignes de son bloc, et les
versions d'un document lisent `git show <étiquette>:<fichier>` et analysent le
texte en mémoire, sans rien extraire ni écrire (`features/item_page`,
`features/document_versions`).

## Hors de ce dépôt

Le fork s'appuie sur des services qui conservent des données ailleurs :

| Service | Données | Interface depuis StrictDoc |
|---|---|---|
| PostgreSQL `kb-postgres` (conteneur) | index de la base de connaissances (exigences, sections, interfaces, termes), sécurité par ligne ; construit depuis les dépôts Git `kb-<mission>` | serveur MCP `kb-mcp` en lecture seule, via `features/kb/client.py` |
| Keycloak | comptes, groupes (`strictdoc-admins`, `strictdoc-authors`, `strictdoc-reviewers`, `strictdoc-readers`, `infra-admins`, `kb-isis`) | en-têtes d'oauth2-proxy ; annuaire (`features/projects/directory.py`) avec le client `strictdoc-directory` |
| GitLab | dépôts des projets | `features/git_config/gitlab_service.py` (jeton nommé par `token_env`) |
| OpenBao | secrets (`secret/strictdoc`, `secret/strictdoc/kb`, clés LLM) | transmis au conteneur par des secrets Podman puis des variables d'environnement |
| Ollama | modèles locaux | relais `strictdoc-llm` vers `10.89.0.1:11434` |
| Volumes hôte | `~/strictdoc-data`, `~/strictdoc-projects` (avec `projects.json`) | données de l'instance déployée, hors Git |

Les scripts de déploiement (`strictdoc-deploy/`, `strictdoc-dev/`) sont dans
`~/DEV/TOOLS/STRICTDOC/`, hors du dépôt `strictdoc`. `HISTORY.md` décrit l'état
déployé, les pièges et la reprise.
