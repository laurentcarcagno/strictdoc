# Word flow in the StrictDoc web interface: plan

Branch: `feature/docx-m6-gui`, on top of `feature/docx-m5-polish`.

## Scope

The command line already imports a Word document (`convert`), exports one (`export --formats=docx`) and updates one with
tracked changes (`docx_base`). The web interface (`strictdoc server`) gets the same three actions as dialogs in the project
tree menu, in the style of the ReqIF import. Nothing else in the web interface changes.

## Decisions

1. **Switch**: project feature `DOCX`, off by default, like `REQIF`. Without it the routes answer 412 and the menu shows nothing.
2. **Profile**: always the one named by `docx_profile` in `strictdoc_config.py`, or the generic profile when none is set. A profile is
   Python code, so the interface never accepts an uploaded profile (it would run arbitrary code on the server).
3. **Preview before write**: import and update both have a "Preview" step that shows the report (added, changed, removed,
   unchanged, warnings) and writes nothing. The write is a second, explicit click.
4. **Import**: upload a `.docx`, choose how tracked changes are read, merge (default) or overwrite. The SDoc file is
   `<name>.sdoc` in the first input folder. The tree refreshes after a write.
5. **Export**: pick one document, then either a fresh Word file (profile template) or an update of an uploaded base `.docx`
   (tracked changes by `revision_author`). The result is a download. The update has the same preview.
6. **Safety**: uploads go to a temporary folder that is removed after the request; the file name is reduced to
   `[A-Za-z0-9_-]`; size limit 50 MB; a file that is not a Word package gives an error in the dialog, not a 500.
   Writes take the global write lock, reads and previews the read lock.
7. **Code placement**: the logic is in `strictdoc/backend/docx/docx_web_service.py` (no web types, unit tested). Routes are in
   `strictdoc/server/routers/docx_router.py`, templates in `strictdoc/features/docx/templates/`. `main_router.py` only gets one
   `include_router` call, and the menu one block, both behind the feature switch.

## Steps

| # | Deliverable | Check |
|---|---|---|
| G1 | `ProjectFeature.DOCX`, `is_activated_docx()`, service module | unit tests for import preview/write, export fresh/update |
| G2 | Router and templates: import dialog | `unit_server` test with `TestClient`: form, preview, write, errors |
| G3 | Export dialog and download | `unit_server` test: fresh download opens and re-imports to the same model; update report equals CLI |
| G4 | Menu entries, user guide, feature map | repo docs build |

## Delivered state

G1 to G4 are done. Checks: 10 HTTP tests (`tests/unit_server/strictdoc/server/30_docx_word_flow`), 7 service tests, and a manual
check in headless Chromium (13 steps: both dialogs, preview, import, merge, fresh download, update preview and download), kept in
`ISIS/strictdoc-dev/browser/` (image `isis-strictdoc-browser`). It is not part of the StrictDoc end2end suite, which needs
SeleniumBase.

The browser check found one defect that the HTTP tests could not: Turbo ignored the Preview button's `data-turbo="true"` inside a
`data-turbo="false"` form. The export form is now a Turbo form and only the Download button opts out.

## Not in this plan

Choosing a profile in the browser, several documents in one export, a SeleniumBase end2end test. Only Chromium was tried, not Firefox
or Word's own handling of the downloaded file.
