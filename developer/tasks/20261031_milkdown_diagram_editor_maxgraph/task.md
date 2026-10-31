# Diagram editor in the Markdown editor (maxGraph)

## WHAT

The Markdown editor of the web interface lets a user draw a diagram and keep it as an SVG image.

### Behavior

- A button of the editor toolbar inserts a diagram. It opens a modal diagram editor over the page.
- The diagram editor has:
  - shapes: rectangle, rounded rectangle, ellipse, diamond, triangle, cylinder, note, text box;
  - connectors between shapes: straight or elbow, with an arrowhead at none, one or both ends, solid or dashed;
  - a text label on every shape and every connector, edited in place with a double click;
  - move and resize of shapes, with a grid the shapes snap to;
  - fill colour, line colour, line width, font size, bold, italic and text alignment;
  - align (left, centre, right, top, middle, bottom) and distribute (horizontally, vertically) the selected shapes;
  - bring to front, send to back, copy, paste, duplicate and delete;
  - undo, redo, zoom in, zoom out and fit to window;
  - keyboard shortcuts for delete, copy, paste, undo and redo.
- Save stores the diagram as an SVG file in the assets folder of the node, like an uploaded image, and puts an image block in the text: `![1.00](./_assets/<node>/diagram_<id>.svg)`.
- A double click on a diagram in the editor reopens the diagram editor. Save overwrites the same SVG file. The text of the field does not change.
- The toolbar button also opens the diagram that is selected in the editor. It draws a new diagram when no diagram is selected.
- Handles on the selected diagram change its width and its height on their own. The corner keeps the proportions unless Shift is held. The size shows in the editor, the document view and every export.
- Cancel changes nothing. An empty diagram is not inserted.
- An SVG image that has no stored diagram (for example an uploaded logo) is not editable. A double click on it does nothing.

### Constraints

- The SVG file is the only copy of the diagram. The SVG carries the diagram model inside, so the editor needs no other file or database.
- The SVG displays as a plain image in the web interface, the page view, the static HTML export, the PDF export and the Word export. Those paths need no change.
- The SVG passes `sanitize_svg` (`strictdoc/features/svg/sanitizer.py`) byte for byte. The editor writes plain SVG text for labels, with no `foreignObject`, no script and no external reference.
- The diagram editor is available where the Markdown editor is: documents with `MARKUP: Markdown`, on the server. A node that has no saved MID has the same limit as image upload.
- The editor bundle `milkdown.js` does not grow. The diagram editor loads on the first click on the button.
- maxGraph is pinned to an exact version (0.25.1, Apache-2.0). The bundle ships its license text.

### Out of scope

- HTML labels, images inside a diagram, groups, swimlanes and layers.
- Import of draw.io, Visio or other diagram files.
- Translated labels of the diagram editor. The table bar has English labels only, and the diagram editor follows it.
- Diagrams in documents with other markups.

### Success criteria

- A user draws two shapes, joins them with an arrow, labels all three, saves, and sees the diagram in the field, in the saved node, in the static HTML export and in the Word export.
- The user reopens the diagram, moves a shape, saves, and the same file shows the change after a reload.
- The new tests pass and the existing Markdown editor tests still pass.

## WHY

Requirements documents need small diagrams: a context view, a state machine, a data flow. Users now draw them in another tool, export an image, and upload it. Each change repeats the round trip, and the source of the drawing lives outside the project.

Word and similar tools let the author draw in place. StrictDoc stores Markdown, so the natural result is an image file next to the document. SVG stays sharp in every export, and the project already handles SVG: the sanitizer, the rasterizer for Word and PDF, and the asset upload.

Mermaid and PlantUML cover diagrams written as text. They do not cover a drawing a user wants to place and connect with the mouse.

## HOW

### Summary

A second bundle, `diagram.js`, holds the diagram editor and maxGraph. The Markdown editor bundle gets a toolbar button and a double click handler. Both load `diagram.js` on first use and call one function, `openDiagramEditor({ svg, upload })`. The function shows the modal and returns the new SVG text, or `null` after Cancel. The Markdown editor uploads the SVG through the existing image upload, and inserts or updates an image block.

The diagram model travels inside the SVG, in a `<desc>` element, as base64 of the maxGraph XML. The sanitizer keeps the text of `<desc>`.

### Why maxGraph

- maxGraph is the engine of draw.io, so it has connectors that follow shapes, elbow routing, perimeters, undo and a model that serializes to XML.
- maxGraph is a library without a user interface. The toolbar of the diagram editor is ours, like the table bar, and it follows the IBM Plex design of the Markdown editor.
- The license of maxGraph is Apache-2.0, the same as StrictDoc.
- draw.io embed needs an iframe, a message protocol, and either a copy of the whole webapp or a call to a public server. Excalidraw needs React and draws sketch style. SVG-Edit has no connectors.

### Files

New files in `developer/milkdown/src/`:

| File | Role |
|---|---|
| `diagram_entry.js` | entry of the `diagram.js` bundle. Registers `window.sdocDiagramEditor = { open }`. |
| `diagram_editor.js` | the modal: builds the graph, the toolbar, the property bar, the keyboard shortcuts, and resolves the result. |
| `diagram_styles.js` | the shape and connector styles, the default style of a vertex and an edge. |
| `diagram_svg.js` | `exportSvg(graph)` and `importSvg(text)`: the SVG with the model in `<desc>`, and the way back. |
| `diagram_loader.js` | loads `diagram.js` and `diagram.css` once, from the folder of `milkdown.js`. |
| `diagram_size.js` | reads and writes the `width` and `height` of the SVG, and keeps the user's scale when a diagram is drawn again. |
| `diagram_node.js` | Milkdown plugin: the toolbar button, the double click, the resize handles, the insert and the update of the image block. |
| `image_caption.js` | gives an image without title an empty caption, so that the image block survives when the field is opened again. |
| `diagram.css` | rules of the modal and its bars. |

Changed files:

- `developer/milkdown/build.mjs` builds a second entry (`diagram`) next to `milkdown`.
- `developer/milkdown/src/entry.js` registers the plugin and hands it the upload function of the element.
- `developer/milkdown/package.json` and `package-lock.json` add `@maxgraph/core` 0.25.1.
- `developer/milkdown/README.md` documents the files, the SVG format and the limits.
- `strictdoc/features/milkdown/assets/milkdown/` receives `diagram.js`, `diagram.css` and the updated legal file. The directory is already copied as a whole (`strictdoc/core/environment.py`), so the assets need no Python change.

### SVG format

- The root `<svg>` has `width`, `height` and `viewBox` set to the bounds of the cells plus a margin. A diagram displays at its natural size.
- The model is in `<desc id="sdoc-diagram">` as `sdoc-diagram:v1:<base64>`, where the base64 text is the UTF-8 maxGraph XML (`ModelXmlSerializer.export()`). The version prefix lets a later format change be detected.
- The drawing comes from `ImageExport` on an `SvgCanvas2D`. Every cell has `html=0` in its style, so labels become `<text>` elements. The sanitizer would remove a `foreignObject`.
- The font family is `IBM Plex Sans, sans-serif`. The Word and PDF exports bundle IBM Plex. A browser without it falls back to `sans-serif`.
- A file is a diagram of this editor if its `<desc id="sdoc-diagram">` starts with `sdoc-diagram:v1:` and decodes to valid maxGraph XML. Any other file is not editable.

### Insert flow

1. The user clicks the diagram button of the toolbar (Crepe top bar group, next to the table button).
2. `diagram_node.js` calls the loader, then `open({ svg: null, upload })`.
3. On Save, the editor builds the SVG and a file name `diagram_<id>.svg`. `id` is the current time in base 36. The fields of a node share one asset folder, so a counter per field could overwrite the diagram of another field.
4. The Markdown editor sends the file with `_upload`. The upload endpoint sanitizes it and returns the path.
5. The plugin inserts an `image-block` node with that path after the selection.

### Edit flow

1. A double click on an `img` inside an `image-block` whose source ends with `.svg` calls `fetch` for the file.
2. If the file is a diagram, `open({ svg, upload })` shows the modal with the model.
3. On Save, the editor sends the SVG under the same file name. The endpoint overwrites the file.
4. The plugin reloads the `img` elements of that path. It fetches the file with `cache: 'reload'`, then assigns the source again. The Markdown does not change.

### Resize

- The display size of a diagram is the `width` and `height` of its `<svg>` element. The `viewBox` stays.
- A size that differs from the `viewBox` scales the drawing. `preserveAspectRatio="none"` lets the two axes scale on their own, and the attribute is removed when the proportions are the original ones.
- The editor draws three handles over the selected diagram (right edge, bottom edge, corner) in an element fixed to the page. The preview changes the `img` while the pointer moves. The pointer release writes the SVG and sends it under the same file name.
- The HTML export, the document view, the PDF export and the Word export read the SVG, so they show the size without a change on the server.
- The image block of Crepe stores a display ratio in the alt text. The HTML export ignores it, so it cannot carry a size. The handle of Crepe is hidden for diagrams.
- A diagram drawn again keeps the scale of the previous drawing: the new width is the new `viewBox` width times the previous scale.

### Diagram editor

- The modal covers the page, traps focus, and closes on Esc after a confirmation when the diagram changed.
- The graph uses `Graph` with: `setConnectable(true)`, `setCellsResizable(true)`, `setGridEnabled(true)`, `setHtmlLabels(false)`, `RubberBandHandler`, `KeyHandler`, `UndoManager`.
- The connect handle on hover comes from `ConnectionHandler.connectImage`, an inline SVG data URL. Dragging from the handle to a shape or to empty space creates an edge.
- Align uses `graph.alignCells` on the selected shapes. Distribute orders the selected shapes by position, keeps the first and the last edge, and makes the gaps equal. Align needs two shapes, distribute needs three.
- The shape palette adds a vertex at the centre of the visible area, offset by 20 px for each insert, and selects it.
- A property bar reflects the selection (fill, line, width, font, alignment, arrowheads, line type) and applies changes with `graph.setCellStyles` in one undoable step.
- Styles use maxGraph style keys and live in `diagram_styles.js`, so the palette and the property bar share them.

### Tests

- Browser: `developer/milkdown/playwright/check_diagrams.py` runs the editor in Chromium (Playwright in Docker) and covers align, distribute, resize, reopen and a reloaded form.
- Unit: `tests/unit/strictdoc/features/svg/test_svg_sanitizer.py` gets a case with a `<desc>` payload and with the element mix of the maxGraph export (`g`, `rect`, `ellipse`, `path`, `text`, `tspan`). The sanitizer returns the bytes unchanged.
- Integration: a Markdown document that references a diagram SVG exports to HTML and to Word without error, and the Word file contains the picture. The test reuses the existing SVG corpus conventions (`tests/integration/features/docx`).
- End-to-end (`tests/end2end/screens/document/update_node/markdown_diagram_editor/`): open the form of a node, click the diagram button, add two shapes and a connector, set labels, save, submit the form, assert that the SVG file exists in the sandbox and the node shows it. Open the form again, double click the diagram, move a shape, save, assert that the file changed.
- Tests run in Docker on Windows with `--headless` (`developer/docker_tests/run_tests.ps1`).

### Trade-offs

- Two bundles instead of one: the cost is a loader and a second request. The gain is that the Markdown editor stays at about 1.5 MB for users who never draw.
- The model lives in `<desc>`: editing the SVG by hand in another tool can drop it. The picture still displays, and the diagram becomes not editable.
- Each diagram is one file. Copying a node copies its asset folder, so the copy gets its own file.
- The browser cache is forced to reload after an edit. Another open tab can show the old picture until reload.

### Delivery plan

1. This task file and `Context.md`.
2. maxGraph dependency, second bundle, loader, empty modal opened by the button.
3. Diagram editor: shapes, connectors, labels, properties.
4. SVG export and import, insert and edit flows.
5. Tests, README, rebuilt assets.

Each step is a commit that builds and passes the lint and the tests that exist at that point.
