# Word (.docx) import and export for StrictDoc: implementation plan

Branch: `feature/docx-import-export`, based on upstream `cc8be79` (StrictDoc 0.30.2). Pushed to the fork only, never to upstream.
Written 2026-10-09 from the ISIS PUS18/OPAL pilot (`ISIS/traceability-pilot/`) and a reading of this repository.

## Summary

Add Word import (as built: `strictdoc convert --input-format docx`, see section 11) and `strictdoc export --formats=docx`, driven by one mapping profile.
The export has an update mode that writes only the differences as Word tracked changes.
Five milestones, about 19 days. The hard part is the update mode (M4). The first open decision is upstream or fork.

## 1. Why

The ISIS PUS18 requirements are contractual Word documents. They are in French, with one table per requirement and tracked
changes under a named author. StrictDoc traces requirements to source and tests and reports gaps. It cannot read or write Word.
Its only bridges are ReqIF and Excel. Two capabilities are needed:

1. **Import**: build and refresh the StrictDoc model from the Word documents. Traceability then comes from the contractual text.
2. **Export**: generate or update the Word documents from the model. StrictDoc can then become the single source and the Word
   deliverable and its revision history survive.

Non-goals: pixel-perfect rendering, macros, comments, equations, and PDF (already exported through HTML2PDF and Sphinx).
Images are kept but not interpreted in v1.

## 2. What the pilot showed (facts)

- `ISIS/traceability-pilot/docx2sdoc.py` (170 lines, standard library only) extracts the 131 requirement tables and 56 headings of a real
  document into a StrictDoc document with a custom grammar; `strictdoc export` accepts it, links requirements to `@relation`-marked
  functions and tests, and reports gaps (126 requirements without parent, 8 of 31 source files partially covered).
- It skips 30 running-text paragraphs and 11 free tables. An importer must keep them as TEXT nodes or report them.
- `tools/word_redline.py` (ISIS) writes tracked insertions as Word does. Rejecting all changes must restore the original text.
  The export update mode needs this technique.
- A `.docx` is a zip whose `word/document.xml` is plain OOXML. Reading needs no dependency.
- python-docx cannot write tracked changes, so a writer needs raw OOXML anyway.
- Revisions, styles, headers, footers and table-of-contents fields share one package and must survive a round trip.

## 3. Where it goes in this repository

(Paths checked in this checkout.)

| Concern | Existing model to follow | New code |
|---|---|---|
| CLI `import` / `export --formats=docx` | `strictdoc/cli/main.py` (command registry), `strictdoc/commands/export.py`, `strictdoc/commands/convert.py` | `strictdoc/commands/import_docx_command.py` (+ `_config.py`), a `docx` entry in the export formats |
| Reader (docx to SDoc model) | `strictdoc/backend/excel/import_/`, `strictdoc/backend/reqif/reqif_import.py` | `strictdoc/backend/docx/import_/` |
| Writer (SDoc model to docx) | `strictdoc/backend/excel/export/`, `strictdoc/backend/reqif/reqif_export.py` | `strictdoc/backend/docx/export/` |
| Options | `ProjectConfig` and `ProjectFeature` in `strictdoc/core/project_config.py` (Python config since 2025) | `DocxProfile` (below), feature `DOCX` |
| Tests | `tests/unit/`, `tests/integration/features/<feature>/` (lit `test.itest` + filecheck) | `tests/unit/strictdoc/backend/docx/`, `tests/integration/features/docx/` |
| Docs | `docs/strictdoc_01_user_guide.sdoc`, `docs/strictdoc_02_feature_map.sdoc` | a "Word support" section in both |
| Lint/type/test tasks | `tasks.py` (invoke), `ruff.toml`, `mypy.ini` | none; the new code must pass them |

No new third-party dependency: `zipfile` and `xml.etree.ElementTree` (as used by the pilot). Python 3.10 compatible.

## 4. The mapping profile

A Word project is described by a profile, because every organisation structures its documents differently. It is Python, like the
rest of the configuration:

```python
DocxProfile(
    heading_styles={"Heading1": 1, "Heading2": 2, "Heading3": 3},      # paragraph style -> section depth
    requirement_tables=RequirementTable(
        id_style="RefExig", title_style="RefExigtitle",                 # first rows of the table
        meta_rows={"Version:": "VERSION", "Applicable to:": "APPLICABLE_TO",
                   "Verified by:": "VERIFIED_BY", "Linked Req:": "LINKED_REQ"},
        text_style="RequirementText", note_label="Note :",
        uid_from="id", relations={"LINKED_REQ": "Parent"}),            # which field carries the UID, which become relations
    free_text="text",                    # "text" = keep running paragraphs as TEXT nodes, "drop" = report only
    revision_author="Laurent Carcagno",  # used by the export in update mode
    template="template.docx",            # styles, headers, footers, numbering for a fresh export
)
```

One profile drives both import and export. This makes a round trip possible. The REQ_02 profile is the first test case.

## 5. Import (`strictdoc import docx`)

1. Read `word/document.xml`; resolve tracked changes with `--tracked-changes accept|reject` (default `accept`); ignore TOC and
   table-of-figures paragraphs.
2. Walk the body in order: headings become sections; tables matching `requirement_tables` become `[REQUIREMENT]` nodes; other
   paragraphs become TEXT nodes (or are reported); other tables become TEXT nodes holding an RST grid table.
3. Inline formatting: bold, italic and monospace runs map to RST `**`, `*`, ```` `` ````; anything else is plain text with a warning count.
4. **Identity**: the UID is the requirement id. A second import into an existing `.sdoc` tree updates fields by UID, adds new nodes, and lists
   UIDs that disappeared from the Word file (never deletes silently). `--dry-run` prints the change list.
5. Output: `.sdoc` files (one per top-level heading, or one per input file), plus a report: counts, unmapped content, duplicate UIDs,
   `Linked Req` values that name no known requirement.

## 6. Export (`strictdoc export --formats=docx`)

Two modes, the second being the one that matters for a contractual document.

- **Fresh**: build a new `.docx` from the template: styles, headers, footers and numbering are taken from `template`; headings, requirement
  tables (the skeleton is cloned from the template's first requirement table so the look is the customer's) and TEXT nodes are written;
  table-of-contents fields are marked dirty so Word offers to update them.
- **Update** (`--docx-base existing.docx`): compare the model with the existing document by UID and write only the differences as tracked
  changes by `revision_author`:
  - new requirement: a tracked inserted table (rows, paragraph marks and runs all inserted);
  - changed field or statement: tracked deletion of the old runs and insertion of the new ones, at paragraph level in v1;
  - requirement removed from the model: tracked deletion of its table (the user decides whether to keep it);
  - unchanged requirement: not touched, byte for byte.
  The result keeps every earlier revision and comment.

## 7. Verification strategy

- **Rejecting all changes of an update must give back the base document's text** (the check `word_redline.py` already does), and
  **accepting all changes must give the model's text**: both are property checks that run on every integration test.
- Round trip: `import` then `export (fresh)` then `import` gives the same `.sdoc` (modulo order of unmapped content).
- Validity: a container image with LibreOffice converts each generated `.docx` to PDF in CI as a "file opens" check. Real Word fidelity can
  only be confirmed by a person with Word: every milestone ends with a manual check list on the ISIS documents.
- Fixtures: small synthetic `.docx` files generated by a script (committed), never customer documents.

## 8. Milestones

Effort figures are rough single-person estimates, to be revised after M1.

| # | Deliverable | Acceptance | Estimate |
|---|---|---|---|
| M1 | Reader and `import docx` with the profile, report, `--dry-run`, tracked-change resolution | the REQ_02 profile imports the 131 requirements and 56 sections with no crash; unit + itest green; ruff/mypy clean | 4 days |
| M2 | Idempotent re-import by UID, relations from `LINKED_REQ`, free-text as TEXT nodes | importing twice changes nothing; a modified Word file yields exactly the expected change list | 2 days |
| M3 | Fresh export from a template | output opens in LibreOffice; re-import gives the same model; TOC fields dirty | 5 days |
| M4 | Update mode with tracked changes | reject-all equals base text, accept-all equals model text, on a corpus of edits (add, change, remove, reorder) | 6 days |
| M5 | Docs (user guide, feature map), CLI help, examples, performance on a 2 MB document | `strictdoc docs` builds; export of REQ_02 under 2 s | 2 days |

Order of risk: M4 is the hard one (Word's markup rules); M1-M3 alone already allow "Word to traceability" and a regenerated document.

## 9. Open decisions

1. **Upstream or fork.** A feature this size needs the maintainers' agreement. Open an issue that describes sections 1 and 4 first.
   Meanwhile the work stays on this branch, and ISIS runs a pinned fork in its container image. Apache-2.0 allows both.
   Decide before M3: upstream may prefer a ReqIF route.
2. **Source of truth.** Until M4 exists, the Word file is the master and `import` is one-way. After M4 the model can become the master.
   This is a project decision.
3. **Profile format**: Python (consistent with `strictdoc_config.py`) or TOML. Python proposed.
4. **Language of generated labels**: keep the template's French labels (profile-driven), never hard-code strings.

## 10. Related item (separate branch)

The pilot also showed that test **results** cannot be imported for C/Unity projects: the `.ctest.junit.xml` dialect maps every test case to a
GoogleTest function (`TEST_F(Suite, Name)`) and stops with an error when it finds none (`strictdoc/helpers/google_test.py`,
`strictdoc/core/file_traceability_index.py`). A small `unity` dialect (case name is the C function name; resolve through the C reader) would
close that gap. Proposed branch: `feature/unity-junit-dialect`, about 2 days, independent of the work above.

## 11. Delivered state (M1 to M5)

One branch per milestone, each on top of the previous one, all on the fork: `feature/docx-m1-reader`,
`feature/docx-m2-reimport-by-uid`, `feature/docx-m3-export-fresh`, `feature/docx-m4-update-tracked-changes`,
`feature/docx-m5-polish`.

Differences from the plan:

- Import is a `Format` plugin, so the command is `strictdoc convert --input-format docx` (options `--docx-profile`,
  `--docx-tracked-changes`, `--docx-dry-run`, `--docx-overwrite`), not `strictdoc import docx`.
- The profile is a Python file (decision 3). It also carries `template` and `revision_author`.
- Update mode is switched on by `docx_base` in `strictdoc_config.py`; without it the export is a fresh document.
- Only the standard library reads and writes the Word package (no python-docx, no lxml).

Checks on the real document REQ_02 (131 requirements):

- Word to SDoc to Word (template = REQ_02) to SDoc gives the same model.
- Update with an unchanged model: `document.xml` is byte-identical to the base.
- Update with one added, one edited and one deleted requirement: reported as such, 129 unchanged; reject-all equals the base text.
- The exported and updated files open in LibreOffice (PDF produced). They have not been opened in Word.
- Time for the whole update command on REQ_02 (200 KB): 0.9 s including start-up.

Not covered: reordering of requirements in update mode, images, comments, footnotes, Word itself.
