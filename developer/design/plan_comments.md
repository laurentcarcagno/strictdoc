# Plan 2: review comments, visible in the web interface and in Word

Part of the [master plan](master_plan.md). Size: about 8 days. Branch prefix `feature/comments-`. Depends on plan 1 (reviewer role, author name).

## 1. Why

Review is where most of the human work on a requirement happens: a reviewer says "this is not testable", the author answers, a customer reviewer
adds a remark in Word. Today a `COMMENT` is an anonymous block of text: no author, no date, no state, and it never reaches the Word deliverable
that the reviewers actually read. The goal: a comment has an author, a date and a state (open or resolved); the web interface shows and filters
them; the Word export carries them as **native Word comments**, so they show in the review pane and in "Show Markup"; and comments written in
Word come back.

## 2. Current state

- The grammar defines a multi-instance, multiline `COMMENT` field for requirements (`strictdoc/backend/sdoc/models/document_grammar.py`, near
  line 118). `SDocNode.get_comment_fields()` (`strictdoc/backend/sdoc/models/node.py`) returns the fields.
- The form edits comments in a dedicated tab (`export/html/templates/screens/document/document/frame_requirement_form.jinja`, row
  `components/form/row/row_with_comment.jinja`); the table view has an inline editor
  (`actions/table/get_node_comments_inline`, `update_node_comments`, `strictdoc/server/routers/main_router.py`); a document has an
  "add comment" action (`/actions/document/new_comment`).
- The HTML render shows the text only. The Word export (`strictdoc/backend/docx/export/`) ignores comments; `ExportRequirement` has no comment
  field. The reader ignores Word comments.
- No identity (plan 1 supplies it), no state, no date.

## 3. Design

### 3.1 Storage: a header line inside the existing `COMMENT` value (no grammar change)

A comment keeps its place and shape in the `.sdoc` file. Its first line is a one-line **machine header** that renders as nothing:

- RST document: `.. sdoc-comment: id=c7f3a9 author=laurent.carcagno date=2026-10-10T12:00:00Z status=open`
- Markdown document: `<!-- sdoc-comment id=c7f3a9 author=laurent.carcagno date=2026-10-10T12:00:00Z status=open -->`

followed by the body in the document's markup. A `COMMENT` without a header (all existing ones) is a legacy comment: shown with author
"unknown", no date, status open, and left as it is until someone edits it (then it gets a header).

Alternatives considered:

| Option | For | Against |
|---|---|---|
| (a) header line in `COMMENT` (chosen) | No grammar change, travels with the node, readable in diffs and in git blame, upstream-compatible | The value is no longer pure text: the editing UI must split header and body; a hand edit can break the header (parsed leniently) |
| (b) real sub-fields in the grammar | Clean model | Changes grammar, writer, parser and the form; large divergence from upstream |
| (c) sidecar file `<document>.comments.json` | Nothing in the `.sdoc` | Comments no longer travel with the document, merge conflicts on a second file, orphans when a node is deleted |

### 3.2 Behaviour

- Add: reviewer or above; the header is written by the server (user and time from the `Principal`, plan 1), never by the browser.
- Edit or delete: the author of the comment, or an author or administrator.
- Resolve and reopen: author role or above; keeps the comment and sets `status=resolved` with `resolved_by` and `resolved_on` in the header.
- Display: author, date, state badge; an "open comments" filter in the document view and the table view; a count per document in the project tree.
- Markdown WYSIWYG editor: not involved; comments have their own small form (plain Markdown or RST text, as the document's markup).

### 3.3 Word export

Native comments, not text pasted into the table:

- New package part `word/comments.xml`, a relationship of type `.../relationships/comments` in `word/_rels/document.xml.rels`, and a content type
  override `application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml`. Same mechanism as the media parts of
  `strictdoc/backend/docx/export/docx_images.py` (`embed_images` is the pattern: collect, add parts, fill placeholders).
- One `<w:comment w:id w:author w:date w:initials>` per SDoc comment, body paragraphs built with `docx_xml.paragraph_xml` from the comment text
  (markup converted like a statement).
- Anchor: `w:commentRangeStart` before the first run of the requirement ID paragraph and `w:commentRangeEnd` plus a run with `w:commentReference`
  after it, so the comment attaches to the requirement as a whole; free-text nodes anchor on their first paragraph.
- Resolved comments: option in the profile `comments="open"` (default), `"all"`, or `"none"`. For `all`, `word/commentsExtended.xml`
  (`w15:commentEx w15:done="1"`) marks the resolved ones.
- Update mode (`docx_tracked_update.py`): comments already in the Word file are kept untouched; a comment of the model that is not in the file is
  added (a comment is itself a review mark, so it needs no tracked change); identity rules in 3.4.

### 3.4 Reading comments back (Word to SDoc)

Reviewers who work in Word (the customer) must reach the model. The reader (`import_/docx_reader.py`) learns `word/comments.xml` and the anchors;
the converter writes a `COMMENT` with a header (`author`, `date` from Word, `status` from `commentsExtended`, `source=word`) on the requirement the
anchor sits in. **Identity** is the hard part: a comment that went from SDoc to Word and is read back must not be duplicated. Writing the SDoc `id` into the
Word comment would show it to the reviewers, so the plan compares comments by (author, date to the minute, SHA-1 of the plain text), which Word
keeps when the file is saved. A round-trip test fixes the rule (step C5, open question 1).

## 4. Steps

| Step | Content | Tests |
|---|---|---|
| C1 | Comment model: parse and write the header, legacy comments, `Comment` dataclass, helpers on the node | Unit: round trip of header and body in RST and Markdown; legacy comments; a malformed header is read leniently and not lost |
| C2 | Web UI: add, edit, delete, resolve, reopen; show author, date and state; "open comments" filter; count in the project tree | `unit_server` routes; end2end: add then resolve; table view inline editor keeps working (existing `_comments` end2end family stays green) |
| C3 | Permissions with plan 1: the reviewer can add and edit own comments only | `unit_server` per role; end2end with two users |
| C4 | Word export, fresh: `comments.xml`, relationship, content type, anchors, profile option | Package test (XML well-formed, relationship targets exist, ids unique); LibreOffice converts the file and the PDF has comment marks (export with comments in margin); reject-all text unchanged |
| C5 | Word update keeps and adds comments; reading comments from Word with the identity rule; `commentsExtended` for resolved ones | Round trip SDoc to Word to SDoc gives the same comments, no duplicates; a comment added in Word appears in the model; update on the real REQ_02 with one comment per requirement is stable (0 changes on the second run) |
| C6 | User guide, plan status | Docs build |

## 5. Files touched

New: `strictdoc/features/comments/` (model, router, templates), `strictdoc/backend/docx/export/docx_comments.py` (parts and anchors),
`strictdoc/backend/docx/import_/docx_comments_reader.py`, tests `tests/unit/.../test_comments.py`, `test_docx_comments.py`, server tests
`tests/unit_server/strictdoc/server/41_comments*/`.
Edited: `strictdoc/backend/docx/export/sdoc_to_docx_generator.py` and `docx_tracked_update.py` (comments on `ExportRequirement` and `ExportText`),
`strictdoc/backend/docx/import_/docx_reader.py` and `docx_to_sdoc_converter.py`, the comment rows in the form templates, the node and project
tree templates (counts), `strictdoc/backend/docx/docx_profile.py` (option `comments`).

## 6. Security and risks

- The author and time come from the server; a forged field in a form is ignored.
- Comment text goes through the same markup rendering as other text, so the same sanitising rules apply (the Markdown renderer allows raw HTML:
  existing behaviour, noted in the master plan; comment text from a customer through Word is plain text and is escaped on import).
- Word compatibility of comment XML is tested with LibreOffice only; one sample is opened in Word by the user.
- Duplicates on round trip: covered by the identity rule and its test.

## 7. Open questions

1. Identity of a comment across Word and SDoc: the plan proposes (author, date to the minute, text hash). Alternative: keep Word's `w:id`
   in the header (`wid=`); it is stable inside one Word file but Word renumbers ids when it saves. To be decided in C5 with a real Word sample.
2. Should resolved comments appear in the Word export by default? Proposal: no (`comments="open"`).
3. Threads (replies) are out of scope for this plan; Word's `commentsExtended` has the parent link if wanted later.

## 8. Verification

- Unit and server tests; end2end `screens/document/update_node/_comments*` and `screens/table/view_table_edit/_comments` stay green.
- A Word export of REQ_02 with a comment on three requirements opens in LibreOffice with the comments in the review pane (PDF export with
  margin comments shows them), and the XML check passes.
- Deployed: two users (reviewer, author) comment and resolve; the audit log (plan 1) names them.
