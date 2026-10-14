# Plan: configuration management with Git and GitLab

## 1. Why
A document is a Git repository, a project is a repository whose documents are submodules, every saved change is a commit, and versions are tags (`A1`, `A2`, `A`, `B1`, ...). The GitLab instance of the project (default `gitlab.karka.lan`) hosts the repositories.

## 2. Design
- Feature `GIT` plus option `git` (`GitConfig`), off by default. Package `strictdoc/features/git_config/`.
- Save interceptor: `ProjectContext.write_document_to_file` calls `GitCommitter.on_document_written` after the write; the asset upload route calls `on_asset_written`. A failure never loses a save (`last_error`, log).
- Only the saved paths are committed, in the repository that owns them. After a commit in a submodule, each parent commits the new pointer.
- Assets (`_assets/`) wait in `pending_paths` and join the next commit; "Commit now" and tag creation flush them. Optional Git LFS rule and size warning.
- Commit messages come from `git diff -U0` and the new text: the UIDs of the changed blocks (`commit_message.py`).
- Tags: `versioning.py`. After `Z` come `ZA` ... `ZZ`, `ZZA`. Major needs a draft; foreign tags are ignored.
- Push: never per save. On request and on tag creation. Fetch, fast-forward only, refuse a diverged branch, never force. Submodules first. A remote tag with another commit is refused.
- GitLab: `python-gitlab`, token from the environment variable named by `token_env`, optional `ca_bundle`, groups created on the way.
- Submodule add accepts `https`/`ssh` only and checks the path.
- Routes: `GET /git`; author: commit pending; administrator: tag, push, create repository, submodule add/update. All in `route_roles.py`.

## 3. Shared files touched
`project_config.py` (feature, option, validate), `environment.py` (templates), `project_context.py` (committer, hook), `main_router.py` (include, upload and delete hooks), the two menu templates (`project_index/action_list.jinja`, `document/action_list.jinja`), `route_roles.py`, `pyproject.toml` (GitPython, python-gitlab).

## 4. Decisions and open points
- One author for every commit and tag: `GitConfig.author_name` / `author_email`, default Laurent Carcagno. The signed-in user is not used, so `features/roles` is not touched. Who acted is in the audit log of the roles feature.
- Menu entry "Configuration management" in the project-index menu and the document menu, only on the server with the feature on.
- When a node is deleted, `_assets/<MID>` and `_assets/<UID>` of the node and its children are removed (only with the feature on, because Git keeps the files) and the removal joins the next commit. A name that would leave `_assets/` is refused.
- Open: no end-to-end test of the page.

## 5. Verification
`tests/unit/strictdoc/features/git_config/` (versioning, messages, service on temporary repositories with submodules and a bare remote, committer, GitLab with a fake client) and `tests/unit_server/strictdoc/server/53_git_config/` (roles, tags, a real save and an upload committed).
