# Plan 4: document hierarchy and input documents

Part of the [master plan](master_plan.md). Size: about 12 days. Branch prefix `feature/hierarchy-`. Depends on plan 1 (read-only protection and roles).

## 1. Why

A space software project is a chain of documents: the customer specification and the equipment interface control documents (ICD) come in from
outside, the system and software requirements answer them, design and tests answer those. Qualification asks three questions that StrictDoc
cannot answer today: which requirement of ours answers which line of the customer document, what is not covered, and what must be re-checked
when the customer document changes. REQ_02 shows the need: its `Linked Req` column holds `[DA1] §5.14.1 ; [DA2] REQ-106005, REQ-106006, REQ-0280`,
references to applicable documents that exist only as text.

## 2. Current state

- Documents live in a folder tree; `[DOCUMENT_FROM_FILE]` includes a document into another
  (`strictdoc/backend/sdoc/grammar/grammar.py`). Relations (`Parent`, `Child`, `File`) cross documents and carry optional `ROLE` and
  `REVERSE_ROLE` (`strictdoc/backend/sdoc/grammar/grammar_grammar.py`).
- A document header has a free `METADATA:` block of key-value pairs (`DocumentCustomMetadata` in `grammar.py`, edited through the
  `update_document_custom_meta` routes). `VERSION`, `DATE` and `CLASSIFICATION` exist as header fields. **No grammar change is needed to
  store a kind, an issuer or a reference**: custom metadata does it.
- Read-only exists for generated content only: `SDocDocument.autogen`, used by `TraceabilityIndex.can_edit_document`, `can_edit_node` and
  `can_delete_node` (`strictdoc/core/traceability_index.py`), which the routes already call and answer 403 on.
- Screens: traceability matrix (`strictdoc/features/traceability_matrix/`), deep traceability (`strictdoc/features/deep_trace/`), a tree map and
  project statistics. They follow relations; none knows levels, kinds or "suspect".
- The Word import turns names of a `relation_fields` column that match a requirement **of the same document** into `Parent` relations
  (`strictdoc/backend/docx/import_/docx_to_sdoc_converter.py`, `_resolve_uids`); everything else stays text.

## 3. Design

### 3.1 Kind of document and project hierarchy (no grammar change)

- A document declares its kind in custom metadata: `KIND: input`, plus for inputs `ISSUER`, `REFERENCE`, `REVISION` (the standard `VERSION` and
  `DATE` are reused).
- The project declares the hierarchy in `strictdoc_config.py`:

```python
document_hierarchy=[
    Level("input",          label="Applicable documents"),
    Level("system",         label="System requirements",   parents=["input"]),
    Level("software",       label="Software requirements", parents=["system", "input"]),
    Level("design",         label="Design",                parents=["software"]),
    Level("test",           label="Tests",                 parents=["software", "design"]),
]
```

  `parents` lists the levels a node of this level may point its `Parent` relations to. A document without a `KIND` is unconstrained (today's behaviour).
- **Relation policy** (step H2): when a relation is saved (`update_requirement`, `table/update_node_relations`, Word import), a `Parent` to a node
  whose level is not allowed gives a validation error in the form, and a warning in the import report. The policy is a project option
  `relation_policy = "off" | "warn" | "enforce"`, default `"off"`.

### 3.2 Input documents

An input document is a normal SDoc document, imported from Word or ReqIF with a profile, whose `KIND` is `input`:

- **Read-only in the interface**: `can_edit_document`, `can_edit_node` and `can_delete_node` also refuse a node of a document of kind `input`
  unless the user is administrator and the project option `input_documents_editable` is true (default false). The edit controls disappear
  with the same predicate the templates already use. Re-import is the only normal way to change it.
- **Metadata screen**: a small header block shows issuer, reference, revision and date.
- **Re-import by UID** reuses the existing merge (`import_/sdoc_requirement_blocks.py`, `CarryOver`): the report already lists added, changed and
  removed UIDs. For an input document this report is saved (below).

### 3.3 Suspect links and impact analysis

When an input (or any parent) changes, the nodes that answer it must be reviewed. Mechanism:

- A **baseline file** `trace_baseline.json` at the project root (sorted keys, one line per link, committed with the documents) records, for each
  `(child UID, parent UID)` link, the SHA-1 of the parent's reviewed content (title, statement, and the fields the project names).
- A link is **suspect** when the parent's current hash differs from the baseline. The traceability screens, the node view and the project
  statistics show a badge; a "Suspect links" screen lists them grouped by parent.
- An **author** clears a suspect link after review (button, audit logged by plan 1); it rewrites the baseline entry. Creating a link
  writes its baseline entry at once.
- The re-import report of an input document ends with the **impact list**: for each changed or removed parent, the children now suspect.

Why a sidecar file and not a field in the node: a hash inside every relation would change the grammar (as in plan 2, option b) and would
change the child node whenever the parent changes, producing noise in review. The sidecar is one place, easy to diff, and merge conflicts
are line-local.

### 3.4 Resolving applicable-document references (the REQ_02 case)

- The project option `applicable_documents = {"DA1": "inputs/pus-standard", "DA2": "inputs/customer-spec"}` names the input documents
  by their path in the project.
- A resolver (new module `strictdoc/features/hierarchy/references.py`) parses a `Linked Req` value into references:
  `[DA1] §5.14.1` (a section number), `[DA2] REQ-106005` (a UID), `REQ-0280` (continuation, same document as the previous reference). A
  section number is matched against the section numbering of the input document (the TOC numbering that StrictDoc computes); a UID is matched
  against the input document's UIDs.
- The Word import calls the resolver for `relation_fields` and writes `Parent` relations to the resolved nodes, with the role the project
  names (`ROLE: derived from`). References that cannot be resolved stay in the text column and appear in the report (the same "unresolved
  link" line as today).
- Migration of the live REQ_02: import DA1 and DA2 as input documents, run a one-off "resolve references" action over the project, review the
  report.

### 3.5 Hierarchy screen

A new feature screen `hierarchy.html` (same mechanism as the project statistics screen, `strictdoc/features/project_statistics/feature.py`)
shows, per level, the number of documents, nodes, nodes with a parent in an allowed level (**coverage**), orphans, and suspect links, with
links to the lists. It reuses the relation index the traceability screens already build.

### 3.6 Word export

The export of a document with a Word template can fill an "Applicable documents" table from the input documents' metadata (`DA` key, title,
reference, issuer, revision, date). Profile option `applicable_documents_table`, off by default; the table is written into a placeholder
table of the template (the same skeleton mechanism as requirement tables, `docx_template.py`).

## 4. Steps

| Step | Content | Tests |
|---|---|---|
| H1 | `Level`, `document_hierarchy`, `KIND` and the input metadata read from custom metadata; level of a node; project option validation | Unit: levels, parents, document without kind, invalid hierarchy (cycle, unknown parent) rejected at config load |
| H2 | Relation policy (`off`, `warn`, `enforce`) in the form validation and in the Word import report | `unit_server`: allowed and refused relations; import report lines; `off` changes nothing (existing end2end green) |
| H3 | Read-only input documents: predicates, templates, option to unlock | `unit_server`: 403 on every write route for an input document (uses the route list of plan 1); end2end: no edit control on an input document; an administrator with the option can edit |
| H4 | Baseline file, suspect computation, badge, "Suspect links" screen, clear action, impact list in the re-import report | Unit: hash stability, suspect after a parent edit, cleared after review, new link baseline; end2end: edit a parent, see the child suspect, clear it |
| H5 | Reference resolver and its use in the Word import; one-off action; REQ_02 migration | Unit: the parser on the real strings of REQ_02 (all 131 `Linked Req` values are parsed, none crashes); import of REQ_02 with two small input documents gives the expected `Parent` relations; unresolved ones reported |
| H6 | Hierarchy screen | `unit_server`: counts on a fixture with three levels; end2end: the screen loads and links work |
| H7 | Applicable-documents table in the Word export | Package and LibreOffice rendering test; reject-all unchanged in update mode |

## 5. Files touched

New: `strictdoc/features/hierarchy/` (levels, kinds, relation policy, baseline, suspect, references, screen, templates), tests
`tests/unit/.../test_hierarchy.py`, `test_references.py`, `tests/unit_server/strictdoc/server/42_hierarchy*/`, end2end `screens/hierarchy/`.
Edited: `strictdoc/core/traceability_index.py` (three predicates), `strictdoc/core/project_config.py` (options),
`strictdoc/export/html/form_objects/requirement_form_object.py` (relation validation),
`strictdoc/backend/docx/import_/docx_to_sdoc_converter.py` (resolver call, report),
`strictdoc/backend/docx/export/` (applicable-documents table), the node templates (suspect badge, read-only state),
`strictdoc/core/environment.py` (template folder).

## 6. Security and risks

- The baseline file is trusted data in the repository; a manual edit can hide a suspect link, which is the same trust as editing a document.
  Clearing is an author action and is audit logged.
- Hash scope: which fields count as "the parent changed" is a project decision (title and statement by default); too wide gives noise, too
  narrow hides changes. It is a config list and is documented.
- Section-number matching is fragile when an input document is renumbered; the resolver reports a section that no longer exists instead of
  guessing, and the impact list shows renumbering as a change.
- Large projects: the suspect computation hashes every parent once per request; it is cached in the traceability index lifetime and
  rebuilt on index rebuild; a measurement on a 3,000-node project is part of H4.

## 7. Open questions

1. `KIND` and the hierarchy are stored in custom metadata and in the project config. If upstream later adds a first-class document type, the
   migration is a metadata rename. Acceptable? Proposal: yes.
2. Should the baseline be per document instead of one file? Proposal: one file per project at first; split by document if conflicts become
   frequent.
3. Do input documents need versioning (keep revision 1 and revision 2 side by side)? Proposal: no, git history and the import report are the record.
4. `ROLE` names for derived-from links: proposal `derived from` / `derives`; to be confirmed with the project's traceability vocabulary.

## 8. Verification

- All tests above, plus `screens/document`, `screens/table` and the trace-related end2end families green with every option off.
- REQ_02 migrated on a copy: the number of `Linked Req` references, resolved, unresolved, and the coverage of the input documents are
  reported and reviewed by the user.
- A deliberate change to a DA2 requirement shows the downstream requirements as suspect in the deployed instance.

## 9. Delivered

H1 to H7 are done on branch `feature/hierarchy`. Unit and `unit_server` tests cover each step (levels and config validation; relation policy;
403 on every write route of an input document; baseline, badge, screen and clearing; the parser on the 131 real `Linked Req` values of REQ_02;
the Word import, the index-backed resolver and the one-off action; the hierarchy screen; the applicable-documents table).

Differences from the plan:

- **Input documents**: the can_edit predicates of the traceability index carry the rule, and a guard on the write router covers the routes that do not call a
  predicate. "Administrator" is known to the predicates through a context variable set by the identity middleware. Review comments stay possible.
- **Relation policy `warn`** has no effect in the form. The Word import creates relations to applicable documents only through the resolver, which
  does not check levels; the check of imported relations is not done.
- **Suspect links**: a link without baseline entry is not suspect (the baseline is created by an administrator and then kept up to date after each write).
  A parent changed on disk by a re-import is expected to show at the next read once the file watcher has rebuilt the index (not tested). The re-import report does not list the impact: the page `/suspect_links` grouped by parent
  is the impact list.
- **References**: roles on relations (`ROLE: derived from`) are not written, because the importer generates its own grammar. A reference to a section
  whose heading has no UID is reported ("has no UID to link to"); importing the input documents with UIDs on sections is a profile matter.
- **Word table**: written in fresh exports only, as a heading and a table at the start; update mode does not touch it.
- Not verified: the migration of the live REQ_02 (needs DA1 and DA2 imported as input documents); the end2end browser tests of the new screens.
