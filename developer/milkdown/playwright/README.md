# Browser checks of the Markdown editor

Three scripts drive the editor in Chromium with Playwright. The first two:

- `check_diagrams.py` draws a diagram, aligns and distributes the shapes, resizes the image with its handles, opens the
  diagram again by a double click and by the toolbar button, saves the form, and reads the SVG file that the server stored.
- `check_toolbar.py` checks the tooltips of the toolbar buttons, the alignment of a paragraph (left, centre, right,
  justified), its round trip through the saved text, and the document view.

Both save the form, so they change the sample project.

A third script, `check_html_blocks.py`, needs no server and no sample project. It puts HTML samples (`div`, `dl`, `sup`,
comments...) into the editor and checks that the Markdown written back keeps the HTML, with and without an edit. It
loads the committed bundle, so run it after `npm run build` and before committing the bundle:

```
pip install playwright==1.49.1 && playwright install chromium
python developer/milkdown/playwright/check_html_blocks.py
```

Set `CHROMIUM` to the path of a browser when the default one of Playwright is not installed.

The project end-to-end tests use Selenium. These checks run in a container, so the host needs neither Playwright nor a
browser. The image has the architecture of the Docker host: Chromium runs natively on arm64 and on x86-64.

## Run

Build the image once:

```
docker build --tag sdoc-playwright developer/milkdown/playwright
```

Copy the sample project to a folder outside the repository (the server writes the assets next to the document), start a
server on it, and run the check:

```
cp -r developer/milkdown/playwright/sample /tmp/diagram_sample
python -m strictdoc.cli.main server /tmp/diagram_sample --port 5113

docker run --rm --add-host host.docker.internal:host-gateway \
  -e SDOC_URL=http://host.docker.internal:5113/diagram_sample/document.html \
  -e SDOC_SHOTS=/shots \
  -v "$PWD/developer/milkdown/playwright:/work/src:ro" \
  -v /tmp/diagram_shots:/shots \
  sdoc-playwright python /work/src/check_diagrams.py
```

Run `check_toolbar.py` the same way.

The server must be restarted after `npm run build`: it copies the assets when it starts. The check keeps its changes in the
sample project, so a second run adds a second diagram. The check works with that.

The exit code is 1 when a check fails. The screenshots in `SDOC_SHOTS` show the aligned shapes, the selected diagram with its
handles, the resized diagram and the document view.
