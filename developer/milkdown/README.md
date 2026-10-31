# Milkdown editor bundle

The WYSIWYG Markdown editor of the web interface (`<sdoc-markdown-editor>`, built on Milkdown Crepe). It edits the content
field (STATEMENT, DESCRIPTION or CONTENT) of the nodes of a document whose `MARKUP` is `Markdown`. Other documents keep the
plain editor. The bundle is committed under `strictdoc/features/milkdown/assets/milkdown/` (like `turbo.min.js`), so the
installed package needs no Node.js.

## Rebuild

```
cd developer/milkdown
npm ci
npm run build
```

Behind a TLS-inspecting proxy, prefix the `npm ci` command with `NODE_TLS_REJECT_UNAUTHORIZED=0` (for that command only).
Commit `milkdown.js`, `milkdown.css` and `milkdown.js.LEGAL.txt` together with any change of `src/`.

## Content

| File | Role |
|---|---|
| `src/entry.js` | the custom element: mounts and destroys the editor, keeps the hidden textarea in step, uploads images |
| `src/sdoc_markers.js` | keeps `[LINK: UID]` and `[ANCHOR: ...]` intact (otherwise they are written as `\[LINK: UID\]` and stop being links) |
| `src/tables.js` | the table nodes (header rows, merged cells, cell colours), read from and written to a pipe table or an HTML `<table>` |
| `src/table_commands.js`, `src/table_bar.js` | the commands and the bar under the top bar: insert, rows, columns, header rows, merge and split, selection, fill, alignment (they replace the table block of Crepe, which is off) |
| `src/diagram_node.js`, `src/diagram_loader.js` | the toolbar button, the double click and the resize handles of a diagram; the loader fetches `diagram.js` on first use |
| `src/diagram_size.js` | reads and writes the display size (`width`, `height`) of a diagram SVG |
| `src/image_caption.js` | gives an image without title an empty caption, so that Crepe keeps the image block when a field is opened again |
| `src/alignment.js` | the alignment of paragraphs (left, centre, right, justified), images and diagrams (left, centre, right): an attribute of the node, the four toolbar buttons, and the HTML they are written as. The alignment of a table is in `src/tables.js` |
| `src/toolbar_tooltips.js` | the tooltips of the toolbar buttons (top bar and table bar), and their accessible names |
| `src/languages.js` | code block languages (replaces the 100+ grammars of `@codemirror/language-data`, about 1 MB) |
| `src/katex_stub.js`, `src/empty.css` | formulas are switched off, so KaTeX (about 1.7 MB with its fonts) is left out |
| `src/sdoc_editor.css` | StrictDoc rules on top of the Crepe theme |

Size: about 1.5 MB of JavaScript and 55 KB of CSS.

## Diagram editor

A second bundle, `diagram.js` with `diagram.css` (about 430 KB, maxGraph), holds the diagram editor. `milkdown.js` loads it
the first time the user clicks the diagram button of the toolbar, from the folder of `milkdown.js`.

| File | Role |
|---|---|
| `src/diagram_entry.js` | entry of `diagram.js`: sets `window.sdocDiagram` (`open`, `isDiagram`) |
| `src/diagram_editor.js` | the modal: graph, palette, property bar, keyboard |
| `src/diagram_styles.js` | the shapes of the palette and the default styles |
| `src/diagram_svg.js` | the SVG of a diagram: export, and reading the model back |
| `src/diagram.css` | rules of the modal |

A diagram is an image block that points to `diagram_<id>.svg` in the assets folder of the node. The SVG holds the model of
the diagram in `<desc id="sdoc-diagram">` as `sdoc-diagram:v1:` and the base64 of the maxGraph XML. The server keeps the text
of `<desc>` when it sanitizes the upload. A double click on the image of such a file opens it again, and Save overwrites the
file. The button of the toolbar opens the selected diagram, or draws a new one when no diagram is selected. An SVG without
that element (an uploaded logo) is a plain image.

The handles on the selected diagram (right edge, bottom edge, corner) change its display size. The size is the `width` and
`height` of the `<svg>` element: the viewBox stays, and `preserveAspectRatio="none"` lets the two axes scale on their own.
The corner keeps the proportions unless Shift is held. A diagram that is drawn again keeps the scale it had. Every renderer
of the SVG shows the size, so the server needs no change. The display ratio of the image block of Crepe is not used for a
diagram, and its handle is hidden.

`diagram.js.LEGAL.txt` is written by `build.mjs` and holds the license of maxGraph (Apache-2.0).

`playwright/` holds a browser check of the diagram editor, see `playwright/README.md`.

Limits of the diagram editor:

- Labels are plain text, without wrapping: a long label is split with line breaks. The server removes `foreignObject`, which
  HTML labels need.
- No groups, layers, swimlanes or images inside a diagram.
- The SVG is written when the user clicks Save in the modal, not when the form of the node is saved. Cancelling the form
  leaves the file in the assets folder, like an uploaded image.

## What the editor does to the text

A field that was not edited is sent back byte for byte. A field that was edited is written again by Milkdown. Observed on a
text with headings, lists, a quote, a code block, a table, a link and a `[LINK: UID]`:

- a hard break written as two trailing spaces becomes a backslash at the end of the line (the same break in CommonMark);
- a table is re-aligned: columns are padded and the separator row becomes `| - | :-: |`; the alignment is kept;
- a table with a merged cell, a coloured cell, no header row or several header rows is written as an HTML `<table>` without
  blank line, and read back as a table only if its tags and attributes are `table`, `thead`, `tbody`, `tr`, `th`, `td`,
  `colspan`, `rowspan`, `style` (`background-color`, `text-align`), `align`, `bgcolor` and, in a cell, `strong`, `em`, `del`,
  `code`, `a`, `br`, `img`; any other HTML table stays raw HTML and is not touched;
- two cells that are merged join their paragraphs with a line break;
- an empty paragraph is written as `<br />`;
- a paragraph that is centred, right aligned or justified is written as an HTML paragraph, `<p style="text-align: center">...</p>`, with its content as inline HTML (`strong`, `em`, `del`, `code`, `a`, `br`, `img`). It is read back as an aligned paragraph only if its tags and attributes are `p`, `style` (`text-align`), `align` and those inline tags; any other `<p>` stays raw HTML. A left paragraph stays a Markdown paragraph;
- an image or a diagram that is centred or on the right is written as an HTML paragraph that holds an `<img>`, `<p style="text-align: right"><img src="./pic.png" alt="1.00" /></p>`, and read back as an image block. A left image stays a Markdown image. The editor shows an image on the left unless it is aligned (the image block of Crepe centres it, the document does not);
- a table that is aligned is an HTML `<table>` with `style="width: fit-content; margin-left: auto"` (right), `margin-right: auto` (left) or both margins (centre). An aligned table has the width of its content, because the document shows a table as a block that is as wide as its container. The button that is already on puts the table back to the full width (a pipe table);
- the alt text of an image inserted by the editor is its display ratio, for example `![1.00](./_assets/.../pic.png)`.

Unchanged: bullets (`*` and `-`), numbered lists, `*emphasis*` and `_emphasis_`, headings, code fences and block quotes.

The server removes trailing spaces on every line when it saves a multiline field, with or without this editor, so a hard
break written with two trailing spaces does not survive a save through the web form.

## Not supported

- The alignment of a heading or a list item, and the justification of an image or a table. The paragraph buttons do not act on a table cell: a cell has its own alignment in the table bar, and the buttons act on the table. The Word export keeps the text, the bold and italic and the picture of an aligned paragraph or image, not their alignment; an aligned table is written as text there, like any HTML table.

- A header column, and the width of a column (the column resizing is not kept).
- A cell holds inline content only (no list or code block in a cell).
- Task lists (`- [ ]`): the Markdown renderer of StrictDoc shows them as plain text.
- Formulas.
- An image can only be uploaded for a node that exists; with `ENABLE_MID: False` a new node must be saved first.
