# Hemeria interface, single address, French

## WHAT

The web interface of the ISIS fork of StrictDoc shall:

- use the Hemeria design system (`developer/design/DESIGN.md`,
  `DESIGN.json`, `PRODUCT.md`) on every screen, with no footer;
- keep the original look of StrictDoc in the PDF export (HTML2PDF);
- serve every project at one address: the first visit shows the projects of
  the user (`/_projects`), a picker at the top of the sidebar changes the
  current project, and the browser remembers it (cookie `sdoc_project`);
- speak English or French: the project option `language` (`en`, the
  default, or `fr`), which the environment variable `STRICTDOC_LANGUAGE`
  overrides.

The tests shall run in a Linux container on a Windows workstation, never on
the host.

## WHY

The ISIS and REVALTO teams use the server through a login proxy (Keycloak,
oauth2-proxy) and work in French. One address per project was rejected: the
users want one address and a project picker.

On the Windows workstation of the developer, SentinelOne stopped a test
campaign. A Selenium script logged in to a test Keycloak with headless
Chrome; the behavioral engine took it, with the hundreds of Python processes
of the tests, for an attack, and killed every process of the terminal (one
detection, more than 600 kills). The tests now run in Docker.

## HOW

The work is on the branch `feature/hemeria-ui`, made from
`feature/membership`. Every commit has `laurent.carcagno
<laurent.carcagno@hemeria-group.com>` as its only author.

| Commit | Content |
|---|---|
| `5698adb` | Design system and product context (`developer/design/`) |
| `27963bf` | Hemeria restyle: app shell, document view, portal, members, log out; footer removed |
| `7c4a76e` | One address: `sdoc_project` cookie, `/_projects`, picker, `/_projects/mine.json`, `/_projects/select/<slug>` |
| `0145701` | PDF keeps the original look (`html2pdf_original_look.css`) |
| `6c0cb69` | Hemeria design on the other screens |
| `00b9b97` | `language` option, `strictdoc/features/i18n` (Babel `.po`, no `.mo` in the repository) |
| `debbc72`, `014ba82` | French texts of the templates and the scripts (`window.sdocT`) |
| `3e9ca6a` | A template no longer binds `_` (it hid `_()`); a test guards it |
| `be07dec` | French texts of the server messages |
| `24192ed` | Template gettext functions can be pickled: the HTML export renders in several processes |
| `d05b4d9` | Tests in Docker: `developer/docker_tests/`, rule in `AGENTS.md` |
| `e301829` | Translated sidebar subtitle of the portal; avatar initials as `role_gating.js` |

### i18n

- The texts stay English in the code. `strictdoc/features/i18n/locales/fr/LC_MESSAGES/strictdoc.po` translates them.
- `python developer/i18n/update_catalogs.py` collects the texts: `_()` and
  `{% trans %}` in templates, `gettext()` in Python, `sdocT()` in scripts.
- A unit test checks that every text of the French catalog is translated and keeps
  its `%(name)s` placeholders.
- A page embeds only the texts of the scripts (`window.SDOC_I18N`).

### Tests in Docker

    powershell -File developer/docker_tests/run_tests.ps1 invoke test-unit
    powershell -File developer/docker_tests/run_tests.ps1 invoke test-unit-server --focus test_french
    powershell -File developer/docker_tests/run_tests.ps1 invoke test-integration
    powershell -File developer/docker_tests/run_tests.ps1 invoke test-end2end --headless --test-path screens/project_statistics

- **What runs:** the container tests a copy of the working tree in `/strictdoc`, uncommitted changes included.
- **Proxy certificates:** behind the HEMERIA proxy (Olfeo, TLS inspection),
  `developer/docker_tests/certs/` needs the HEMERIA root CAs (`*.crt`). Git
  ignores them: copy them on each new machine. They are also in
  `C:\projects\HEMERIA\TOOLS\INFRA\strictdoc-keycloak\image\certs`.
- **`--focus`:** it takes one keyword (pytest `-k`); a space breaks it.

### Test status (Docker, 12 October 2026)

| Suite | Result | Failures |
|---|---|---|
| Unit | 1146 passed, 1 failed | `test_docx_svg::test_010` |
| Server | 258 passed, 2 failed | `42_roles` "no group", `test_server_process` |
| Integration | 532 passed | 10 failures |
| HTML2PDF | 16 passed, 1 failed | `05_generate_bundle_document` |
| End-to-end | `screens/project_statistics` only | none |

**Unit failure:** `test_docx_svg::test_010` was skipped on Windows. resvg loads the system
fonts by default, so the render "without fonts" already has text.

**Server failures:**
- `42_roles` "no group": stale since `ed639ba`.
- `test_server_process`: the subprocess cannot import `strictdoc`.

**Integration failures:** they also fail on Windows.
- `missing_input_path_no_duplicate_error`
- four `docx` import/export tests
- `html/escaping/01`
- `--formats/01_incorrect_format`: `docx` is now in the list.
- two `sdoc/markup` LINK tests
- `self_testing/.../passthrough/01_hello_world`: the user guide has lines that the SDoc writer wraps differently.

**HTML2PDF failure:** `05_generate_bundle_document` came from the container
(no Git information). It passes after the container fixes; the whole
HTML2PDF group has not run again since.

**Lint:** `ruff` reformats four `developer/design/plan_*.md` files, and
`test_docx_comments.py` has an unsorted import.

The full end-to-end suite has not run since the single address (`7c4a76e`).

### Test stack (outside the repository)

`C:\projects\HEMERIA\TOOLS\INFRA\strictdoc-keycloak` is a Docker Compose stack: Caddy, oauth2-proxy,
StrictDoc built from the working tree, and Keycloak with the realm `infra`.
Its `README.md` describes the users (`admin1`, `alice`, `bob`, `carol`,
`dave`, `erin`, password `test`), the projects (`demo`, `isis`, `revalto`) and
the commands. Copy that folder to the new machine to keep the stack.

### Remaining work

1. Run the full end-to-end suite in Docker, in shards:
   `invoke test-end2end --headless --long-timeouts --shard=1/4` up to `4/4`.
   Fix the failures that the branch caused.
2. Map the coverage gradient of the tree map (`#AAFFAA` and the other values
   in `strictdoc/features/tree_map/data_generator.py`, checked by exact value
   in tests) to the Hemeria palette.
3. Translate the issue banner
   (`strictdoc/export/html/templates/components/issue/banner.jinja`).
4. Decide about the failures listed above that the branch did not cause:
   `test_docx_svg::test_010`, `42_roles`, `passthrough/01_hello_world`, the
   lint findings.
5. Open a pull request of `feature/hemeria-ui` when the suites are green.
