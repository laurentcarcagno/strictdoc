# Plan 3: SVG images, in the web interface and in Word

Part of the [master plan](master_plan.md). Size: about 5 days. Branch prefix `feature/svg-`. No dependency on the other plans.

## 1. Why

Requirement documents are full of diagrams (architecture, state machines, timing) and engineers draw them as vector files. An SVG stays sharp
at any zoom, is small and diffable. The web interface already accepts SVG, but the Word deliverable cannot show it: the export writes
`[image: diagram.svg]` as text, because Word shows an SVG only with a raster fallback and an extension element. The goal: an SVG added in the
editor appears as a drawing in the Word file, vector in current Word and as a picture everywhere else, and a hostile SVG file can do no harm.

## 2. Current state

- `strictdoc/core/image_formats.py` lists `.svg` (`image/svg+xml`) among the supported formats (with PNG, GIF, JPEG, WebP, AVIF) and the 10 MB
  limit (`MAX_IMAGE_SIZE_BYTES`).
- The upload route `/actions/document/upload_asset` (`strictdoc/server/routers/main_router.py`) stores the file under `_assets/<mid or uid>/`, and
  returns a Sphinx-style wildcard (`name.*`) when an SVG and a raster file share a stem; the Markdown editor (`strictdoc/features/milkdown/`)
  turns a wildcard into the real extension.
- HTML shows images as `<img src=...>`. **Nothing inspects the SVG content**: an uploaded file can contain `<script>`, event attributes, or
  references to local files or remote addresses, and the file is served from the application's own origin, so opening its address directly would
  run the script in that origin.
- Word: `strictdoc/backend/docx/export/docx_images.py` embeds PNG, JPEG and GIF (reads the size from the header, builds the inline drawing,
  `embed_images` adds the media part, the relationship and the content type). Any other format stays text. The reader gives
  `[image: name]` for pictures that StrictDoc wrote (docPr name prefix `sdoc-image:`).

## 3. Design

### 3.1 Sanitise first

A function `sanitize_svg(data) -> bytes` (new module `strictdoc/features/svg/sanitizer.py`) parses the file with the standard XML parser in a
configuration that refuses entities and DTDs (no billion laughs, no external entities) and rewrites it keeping an **allow-list** of elements and
attributes (shapes, paths, text, groups, gradients, `defs`, `use` to a local `#id` only, `style` with a filtered subset). It removes:
`script`, `foreignObject`, `iframe`, `object`, `embed`, `animate*` that target `href`, every `on*` attribute, every `href` or `xlink:href` that is
not a local `#id` or a `data:image/png|jpeg|gif` URI, every `url(...)` that is not local, and any `@import`. The size of the file, the number
of elements and the nesting depth are limited. A file that cannot be made safe is rejected with a clear message in the editor.

It runs in the upload route (so the stored file is already clean) and again just before rasterizing (a file placed in `_assets` by hand is not
trusted).

### 3.2 Serve safely

Assets served by the application get `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox` and
`X-Content-Type-Options: nosniff`, so that an SVG opened directly cannot run script and an `<img>` use is unaffected.

### 3.3 Word: raster fallback plus the SVG extension

Word 2016 and later (Microsoft 365) read an SVG through an extension of the picture element; every other reader needs the PNG:

```xml
<a:blip r:embed="rIdPng">
  <a:extLst>
    <a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">
      <asvg:svgBlip xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main" r:embed="rIdSvg"/>
    </a:ext>
  </a:extLst>
</a:blip>
```

- Two media parts per SVG (`word/media/sdoc_<hash>.svg` and `.png`), two relationships, a `svg` default content type (`image/svg+xml`).
- The PNG is the SVG rasterized at twice the display size (a 14 cm cap like other images, at 192 dpi), transparent background.
- The display size comes from `width` and `height` (units `px`, `pt`, `mm`, `cm`, `in`) or, without them, the `viewBox`.
- `embed_images` in `docx_images.py` is generalised from "one part per image" to "a list of parts per image"; `ExportImage` gets an optional
  `fallback_png` field.
- The reader and the update comparison are unchanged: the drawing name `sdoc-image:diagram.svg` still reads back as `[image: diagram.svg]`.

### 3.4 Rasterizer: chosen by a spike (step S0)

| Candidate | For | Against |
|---|---|---|
| CairoSVG | Python, good coverage, option to refuse external access (`unsafe=False`) | Needs the system library `libcairo2` in the server image (about 10 MB); the dev image has none |
| A self-contained resvg build (wheel or static binary) | Fast, strict, no system dependency | Availability of a wheel behind the corporate proxy to be checked; a binary is a separate process |
| LibreOffice headless | Already in the repository as image `isis-libreoffice` | Heavy (hundreds of MB), slow start, not in the server image |

Criteria: no network or file access, fidelity on a fixed test set (state machine, timing diagram, text with fonts), size added to the image,
licence compatible with Apache-2.0 distribution, behaviour behind the TLS-inspecting proxy during `pip install` or download. The spike writes its
result into this plan before S2 starts. Fonts: text in an SVG uses the fonts of the server; the fallback may differ from the vector in Word, which
is stated in the user guide.

## 4. Steps

| Step | Content | Tests |
|---|---|---|
| S0 | Rasterizer spike on five test diagrams (state machine, timing, text, gradient, large); record the results here | A table of renders and timings in this document |
| S1 | `sanitize_svg`, called by the upload route; safe asset headers | Unit: a corpus of hostile files (script, `onload`, external `href`, `file:` reference, entity bomb, huge file, deep nesting, `foreignObject`) is neutralised or rejected, a corpus of normal diagrams is unchanged in appearance; `unit_server`: upload of a hostile file returns 400, headers present on the asset |
| S2 | Rasterize and embed in Word (fresh export); size parsing | Package test (two media parts, relationships, content types, `svgBlip`); LibreOffice renders the fallback; the PDF contains the image; XML well-formed |
| S3 | Update mode: SVG as a tracked insertion; stable second update | Update of REQ_02 with an SVG changes one requirement; reject-all equals the base; second update gives 0 changes |
| S4 | Editor: SVG upload in the Markdown editor and display in the page | End2end: upload an SVG, see it, save; the Word dialog export contains it |
| S5 | User guide and plan status | Docs build |

## 5. Files touched

New: `strictdoc/features/svg/` (sanitizer, rasterizer wrapper, its tests data), `tests/unit/.../test_svg_sanitizer.py`, `test_docx_svg.py`,
a test corpus folder `tests/unit/strictdoc/features/svg/corpus/`.
Edited: `strictdoc/core/image_formats.py` (no format change; helper for the SVG policy), the upload route in `main_router.py` (call the sanitizer),
the static file response (headers), `strictdoc/backend/docx/export/docx_images.py`, `markdown_to_paragraphs.py` (SVG now loadable),
`rst_to_paragraphs.py` (`ExportImage.fallback_png`), `ISIS/strictdoc-deploy/Containerfile` (rasterizer dependency).

## 6. Security and risks

- SVG is an active format. The sanitiser is the control; it is an allow-list, not a block-list, and has a hostile corpus in the test suite.
- A rasterizer that follows external references is a server-side request and file-read risk: the chosen one is run with external access
  disabled, after sanitising, with a time and memory limit (a subprocess with limits if the library offers no option).
- Fidelity: Word's SVG renderer and the rasterizer may differ on fonts and filters.
- Image size in the package grows (an SVG and a PNG per drawing); the 10 MB limit applies to the upload.

## 7. Open questions

1. Rasterizer choice (S0).
2. Do we also convert existing WebP and AVIF images to PNG for Word the same way? Proposal: yes, later and by the same fallback path (Word reads neither).
3. Do we offer the PNG fallback as a separate downloadable asset? Proposal: no.

## 8. Verification

- All tests above; `screens/document/update_node/update_requirement_upload_image*` end2end family stays green.
- A real SVG diagram in a REQ_02 requirement: export, open in LibreOffice (fallback visible), inspect the package (two media parts).
- The user opens the sample in Word 365 to confirm that the vector shows and that zooming stays sharp.
