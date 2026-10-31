// The diagrams of the Markdown editor. A diagram is an image block that points
// to an SVG file made by the diagram editor (see diagram_svg.js):
//
//   - a button of the toolbar draws a new diagram and inserts it, or opens
//     the selected diagram;
//   - a double click on the image of a diagram opens it again;
//   - handles on the selected diagram change its width and its height.
//
// Opening a diagram and resizing it overwrite the SVG file (the same name), so
// the text of the field does not change. The diagram editor (maxGraph, about
// 430 KB) loads on first use.
import { editorViewCtx } from '@milkdown/kit/core';
import { $prose } from '@milkdown/kit/utils';
import { NodeSelection, Plugin, PluginKey } from '@milkdown/kit/prose/state';
import { loadDiagramEditor } from './diagram_loader.js';
import { keepScale, writeSize } from './diagram_size.js';

const KEY = new PluginKey('SDOC_DIAGRAM');
const IMAGE_BLOCK = 'image-block';
const DIAGRAM_MARKER = 'id="sdoc-diagram"';
const MIN_SIZE = 40;
const HANDLES = ['e', 's', 'se'];

const DIAGRAM_ICON =
  '<svg class="sdoc-diagram-icon" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true">' +
  '<rect x="1.5" y="2" width="5" height="4"/><rect x="9.5" y="10" width="5" height="4"/>' +
  '<path d="M4 6v3.5a1.5 1.5 0 0 0 1.5 1.5H9.5M8 9.5l1.5 1.5L8 12.5"/></svg>';

// options.upload(file) sends a file to the server and gives its address,
// options.showError(message) tells the user.
export function createDiagramSupport(options) {
  const { upload, showError } = options;
  // Address of an SVG file -> its text when it is a diagram, null when it is
  // not. Forgotten when the file is written.
  const known = new Map();

  async function readDiagram(address, image) {
    if (known.has(address)) return known.get(address);
    const response = await fetch(image.currentSrc || image.src, { cache: 'no-cache' });
    const text = response.ok ? await response.text() : '';
    const diagram = text.includes(DIAGRAM_MARKER) ? text : null;
    known.set(address, diagram);
    return diagram;
  }

  async function writeDiagram(view, address, svg) {
    const name = decodeURIComponent(address.split('/').pop());
    await upload(new File([svg], name, { type: 'image/svg+xml' }));
    known.delete(address);
    await reloadImages(view, address);
  }

  // false when the image is not a diagram.
  async function editDiagram(view, node, image) {
    try {
      const address = node.attrs.src;
      const text = await readDiagram(address, image);
      if (text === null) return false;
      const diagramEditor = await loadDiagramEditor();
      const drawn = await diagramEditor.open({ svg: text });
      if (drawn === null || view.isDestroyed) return true;
      await writeDiagram(view, address, keepScale(drawn, text));
    } catch (error) {
      showError(`Diagram failed: ${error.message}`);
    }
    return true;
  }

  async function insertDiagram(ctx) {
    const view = ctx.get(editorViewCtx);
    try {
      // The button opens the diagram that is selected.
      const selected = selectedSvgBlock(view);
      if (selected !== null && (await editDiagram(view, selected.node, selected.image))) return;

      const diagramEditor = await loadDiagramEditor();
      const svg = await diagramEditor.open({ svg: null });
      if (svg === null || view.isDestroyed) return;
      const address = await upload(new File([svg], newFileName(), { type: 'image/svg+xml' }));
      if (view.isDestroyed) return;
      insertImageBlock(view, address);
    } catch (error) {
      showError(`Diagram failed: ${error.message}`);
    }
  }

  const plugin = $prose(() =>
    new Plugin({
      key: KEY,
      props: {
        handleDOMEvents: {
          dblclick: (view, event) => {
            if (!view.editable) return false;
            // The target is a wrapper of the image as often as the image.
            const found = view.posAtCoords({ left: event.clientX, top: event.clientY });
            const node =
              found === null || found.inside < 0 ? null : view.state.doc.nodeAt(found.inside);
            if (node === null || node.type.name !== IMAGE_BLOCK) return false;
            if (!/\.svg$/i.test(node.attrs.src)) return false;
            const image = view.nodeDOM(found.inside)?.querySelector?.('img') ?? null;
            if (image === null) return false;
            // Whether the file is a diagram is known after reading it.
            editDiagram(view, node, image);
            return true;
          },
        },
      },
      view: (view) =>
        new ResizeHandles(view, {
          isDiagram: async (address, image) => (await readDiagram(address, image)) !== null,
          isKnown: (address) => known.get(address),
          resize: async (address, image, width, height) => {
            try {
              const text = await readDiagram(address, image);
              if (text === null) return;
              await writeDiagram(view, address, writeSize(text, width, height));
            } catch (error) {
              showError(`Diagram failed: ${error.message}`);
            }
          },
        }),
    })
  );

  // The button of the toolbar (Crepe top bar).
  function buildButton(builder) {
    builder.addGroup('sdoc-diagram', 'Diagram').addItem('sdoc-diagram-insert', {
      icon: DIAGRAM_ICON,
      active: () => false,
      onRun: (ctx) => {
        insertDiagram(ctx);
      },
    });
  }

  return { plugin, buildButton };
}

// The selected image block of an SVG file: {node, image}, or null.
function selectedSvgBlock(view) {
  const selection = view.state.selection;
  if (!(selection instanceof NodeSelection)) return null;
  if (selection.node.type.name !== IMAGE_BLOCK) return null;
  if (!/\.svg$/i.test(selection.node.attrs.src)) return null;
  const image = view.nodeDOM(selection.from)?.querySelector?.('img') ?? null;
  return image === null ? null : { node: selection.node, image };
}

// Handles around the selected diagram: right edge, bottom edge and corner. The
// corner keeps the proportions unless Shift is held. The size is written to
// the SVG file when the pointer is released.
class ResizeHandles {
  constructor(view, callbacks) {
    this.view = view;
    this.callbacks = callbacks;
    this.target = null;
    this.element = document.createElement('div');
    this.element.className = 'sdoc-diagram-resize';
    this.element.dataset.testid = 'diagram-resize';
    this.element.hidden = true;
    for (const name of HANDLES) {
      const handle = document.createElement('div');
      handle.className = `sdoc-diagram-resize__handle sdoc-diagram-resize__handle--${name}`;
      handle.dataset.testid = `diagram-resize-${name}`;
      handle.addEventListener('pointerdown', (event) => this.start(event, name));
      this.element.append(handle);
    }
    document.body.append(this.element);
    this.reposition = () => this.place();
    window.addEventListener('scroll', this.reposition, true);
    window.addEventListener('resize', this.reposition);
    this.sync();
  }

  update(view) {
    this.view = view;
    this.sync();
  }

  destroy() {
    window.removeEventListener('scroll', this.reposition, true);
    window.removeEventListener('resize', this.reposition);
    this.element.remove();
  }

  // Shows the handles when a diagram is selected.
  sync() {
    const selected = this.view.editable ? selectedSvgBlock(this.view) : null;
    this.target = null;
    if (selected !== null) {
      const address = selected.node.attrs.src;
      const state = this.callbacks.isKnown(address);
      if (state === undefined) {
        // Not read yet: the handles appear once the file is known.
        this.callbacks.isDiagram(address, selected.image).then(() => this.sync());
      } else if (state !== null) {
        this.target = { address, image: selected.image };
      }
    }
    this.place();
  }

  place() {
    const image = this.target?.image;
    if (image === undefined || !image.isConnected) {
      this.element.hidden = true;
      return;
    }
    const rect = image.getBoundingClientRect();
    Object.assign(this.element.style, {
      left: `${rect.left}px`,
      top: `${rect.top}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
    });
    this.element.hidden = false;
  }

  start(event, name) {
    if (this.target === null) return;
    event.preventDefault();
    event.stopPropagation();
    const { address, image } = this.target;
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const origin = image.getBoundingClientRect();
    const host = image.closest('.milkdown-image-block');
    const maxWidth = host === null ? Infinity : host.getBoundingClientRect().width;
    const startX = event.clientX;
    const startY = event.clientY;
    let width = origin.width;
    let height = origin.height;

    const move = (moveEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      width = origin.width + (name.includes('e') ? deltaX : 0);
      height = origin.height + (name.includes('s') ? deltaY : 0);
      if (name === 'se' && !moveEvent.shiftKey) {
        const scale = Math.max(width / origin.width, height / origin.height);
        width = origin.width * scale;
        height = origin.height * scale;
      }
      width = Math.min(Math.max(width, MIN_SIZE), maxWidth);
      height = Math.max(height, MIN_SIZE);
      // A preview: the file is written on release.
      image.style.maxWidth = 'none';
      image.style.objectFit = 'fill';
      image.style.width = `${width}px`;
      image.style.height = `${height}px`;
      this.place();
    };
    const end = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', end);
      handle.removeEventListener('pointercancel', end);
      this.callbacks.resize(address, image, width, height);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', end);
    handle.addEventListener('pointercancel', end);
  }
}

// The fields of a node share one asset folder: the name must differ from the
// ones of the other fields and of the other diagrams of the field.
function newFileName() {
  return `diagram_${Date.now().toString(36)}.svg`;
}

function insertImageBlock(view, address) {
  const { state } = view;
  const type = state.schema.nodes[IMAGE_BLOCK];
  if (type === undefined) throw new Error('The editor has no image block.');
  const node = type.create({ src: address, caption: '', ratio: 1 });
  const { $from } = state.selection;
  const transaction = state.tr;
  if ($from.depth === 0) {
    transaction.insert(state.selection.to, node);
  } else if ($from.depth === 1 && $from.parent.type.name === 'paragraph' && $from.parent.content.size === 0) {
    // An empty paragraph makes room for the diagram.
    transaction.replaceWith($from.before(1), $from.after(1), node);
  } else {
    transaction.insert($from.after(1), node);
  }
  view.dispatch(transaction.scrollIntoView());
  view.focus();
}

// The browser keeps the old picture of a file that was overwritten: it is
// fetched again, then the images that show it are given their address again.
// The sizes set while resizing go away: the editor sets them again on load.
async function reloadImages(view, address) {
  const images = [...view.dom.querySelectorAll('img')].filter(
    (image_) => image_.getAttribute('src') === address
  );
  if (images.length === 0) return;
  await fetch(images[0].src, { cache: 'reload' }).catch(() => undefined);
  for (const image of images) {
    image.addEventListener(
      'load',
      () => {
        image.style.removeProperty('width');
        image.style.removeProperty('max-width');
        image.style.removeProperty('object-fit');
      },
      { once: true }
    );
    image.removeAttribute('src');
    image.setAttribute('src', address);
  }
}
