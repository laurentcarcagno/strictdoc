# Prompt to resume the work on another machine

Paste the text below into a new session, at the root of the StrictDoc
repository.

---

Resume the work of the branch `feature/hemeria-ui` (ISIS fork of
StrictDoc). Read first:

1. `AGENTS.md` and the developer guide
   `docs/strictdoc_11_developer_guide.sdoc`;
2. `developer/tasks/20261012_hemeria_ui/task.md`: the goals, the commits, the
   test status and the remaining work;
3. `developer/design/DESIGN.md` and `PRODUCT.md`: the Hemeria design system.

Rules for this work:

- Commit with `laurent.carcagno <laurent.carcagno@hemeria-group.com>` as the
  only author (`GIT_AUTHOR_*` and `GIT_COMMITTER_*`), with no co-author line.
  Commit when it is useful, without asking first.
- Run every test in Docker with
  `powershell -File developer/docker_tests/run_tests.ps1 invoke test-...`,
  never on the Windows host: SentinelOne kills the terminal when it sees
  headless Chrome and the test processes. Do not run Selenium scripts on the
  host either.
- Before the first test run, put the HEMERIA root certificates (`*.crt`) in
  `developer/docker_tests/certs/`; Git does not keep them.
- Keep the original StrictDoc look in the PDF export.
- One address for every project, with the project picker; no address per
  project.
- The texts of the interface stay English in the code; the French
  translation goes in `strictdoc/features/i18n/locales/fr/LC_MESSAGES/strictdoc.po`
  (`python developer/i18n/update_catalogs.py` collects new texts).

Start with item 1 of "Remaining work" in `task.md`: the full end-to-end suite
in Docker, in four shards (`invoke test-end2end --headless --long-timeouts
--shard=1/4`, then 2/4, 3/4, 4/4), one shard at a time. Compare the
failures with the list in `task.md`, fix those that the branch caused, then
go on with the next items. Keep `developer/tasks/20261012_hemeria_ui/Context.md`
as your working notes.
