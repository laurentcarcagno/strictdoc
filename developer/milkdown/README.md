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
| `src/languages.js` | code block languages (replaces the 100+ grammars of `@codemirror/language-data`, about 1 MB) |
| `src/katex_stub.js`, `src/empty.css` | formulas are switched off, so KaTeX (about 1.7 MB with its fonts) is left out |
| `src/sdoc_editor.css` | StrictDoc rules on top of the Crepe theme |

Size: about 1.5 MB of JavaScript and 53 KB of CSS.

## What the editor does to the text

A field that was not edited is sent back byte for byte. A field that was edited is written again by Milkdown. Observed on a
text with headings, lists, a quote, a code block, a table, a link and a `[LINK: UID]`:

- a hard break written as two trailing spaces becomes a backslash at the end of the line (the same break in CommonMark);
- a table is re-aligned: columns are padded and the separator row becomes `| - | :-: |`; the alignment is kept;
- an empty paragraph is written as `<br />`;
- the alt text of an image inserted by the editor is its display ratio, for example `![1.00](./_assets/.../pic.png)`.

Unchanged: bullets (`*` and `-`), numbered lists, `*emphasis*` and `_emphasis_`, headings, code fences and block quotes.

The server removes trailing spaces on every line when it saves a multiline field, with or without this editor, so a hard
break written with two trailing spaces does not survive a save through the web form.

## Not supported

- Task lists (`- [ ]`): the Markdown renderer of StrictDoc shows them as plain text.
- Formulas.
- An image can only be uploaded for a node that exists; with `ENABLE_MID: False` a new node must be saved first.
