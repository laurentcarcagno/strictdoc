// The SVG file of a diagram: the drawing, and the model of the diagram in a
// <desc> element, so that the file can be opened in the diagram editor again.
//
//   <svg ...>
//     <desc id="sdoc-diagram">sdoc-diagram:v1:BASE64 OF THE MAXGRAPH XML</desc>
//     ...the drawing...
//   </svg>
//
// The server keeps the text of <desc> when it sanitizes an uploaded SVG.
import {
  Graph,
  ImageExport,
  ModelXmlSerializer,
  SvgCanvas2D,
  xmlUtils,
} from '@maxgraph/core';
import { applyDefaultStyles } from './diagram_styles.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const DESC_ID = 'sdoc-diagram';
const PAYLOAD_PREFIX = 'sdoc-diagram:v1:';
const MARGIN = 16;

export function serializeModel(graph) {
  return new ModelXmlSerializer(graph.getDataModel()).export();
}

export function loadModel(graph, xml) {
  new ModelXmlSerializer(graph.getDataModel()).import(xml);
}

// The XML of the model stored in an SVG text, or null when the text is not
// the SVG of a diagram.
export function readModel(svgText) {
  const document_ = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  if (document_.querySelector('parsererror') !== null) return null;
  const description = document_.querySelector(`desc[id="${DESC_ID}"]`);
  const text = description?.textContent?.trim() ?? '';
  if (!text.startsWith(PAYLOAD_PREFIX)) return null;
  try {
    return fromBase64(text.slice(PAYLOAD_PREFIX.length));
  } catch (error) {
    return null;
  }
}

// The SVG text of the diagram of a graph.
export function exportSvg(graph) {
  const xml = serializeModel(graph);
  // The drawing comes from a graph of its own: scale 1, no translation, so
  // that the bounds are the ones of the diagram whatever the zoom of the editor.
  const host = document.createElement('div');
  host.style.cssText =
    'position:fixed;left:-10000px;top:0;width:1000px;height:1000px;overflow:hidden;visibility:hidden';
  document.body.append(host);
  const scratch = new Graph(host);
  try {
    applyDefaultStyles(scratch);
    scratch.setHtmlLabels(false);
    loadModel(scratch, xml);
    scratch.getView().revalidate();
    const bounds = contentBounds(scratch);

    const svgDocument = xmlUtils.createXmlDocument();
    const root = svgDocument.createElementNS(SVG_NS, 'svg');
    svgDocument.appendChild(root);
    const width = Math.ceil(bounds.width + 2 * MARGIN);
    const height = Math.ceil(bounds.height + 2 * MARGIN);
    root.setAttribute('version', '1.1');
    root.setAttribute('width', String(width));
    root.setAttribute('height', String(height));
    root.setAttribute('viewBox', `0 0 ${width} ${height}`);

    const canvas = new SvgCanvas2D(root, false);
    canvas.foEnabled = false;
    canvas.translate(MARGIN - bounds.x, MARGIN - bounds.y);
    const exporter = new ImageExport();
    exporter.includeOverlays = false;
    exporter.drawState(
      scratch.getView().getState(scratch.getDataModel().getRoot()),
      canvas
    );

    const description = svgDocument.createElementNS(SVG_NS, 'desc');
    description.setAttribute('id', DESC_ID);
    description.textContent = PAYLOAD_PREFIX + toBase64(xml);
    root.insertBefore(description, root.firstChild);
    return new XMLSerializer().serializeToString(root);
  } finally {
    scratch.destroy();
    host.remove();
  }
}

// What the drawing covers: the bounds of the view (shapes with their lines,
// arrowheads and labels), widened to the rectangle of every cell.
function contentBounds(graph) {
  const view = graph.getView();
  const graphBounds = graph.getGraphBounds();
  let left = graphBounds.x;
  let top = graphBounds.y;
  let right = graphBounds.x + graphBounds.width;
  let bottom = graphBounds.y + graphBounds.height;
  for (const cell_ of graph.getDefaultParent().children ?? []) {
    const state = view.getState(cell_);
    if (state === null || state === undefined) continue;
    left = Math.min(left, state.x);
    top = Math.min(top, state.y);
    right = Math.max(right, state.x + state.width);
    bottom = Math.max(bottom, state.y + state.height);
  }
  return { x: left, y: top, width: right - left, height: bottom - top };
}

function toBase64(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (let at = 0; at < bytes.length; at += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  }
  return btoa(binary);
}

function fromBase64(base64) {
  const binary = atob(base64);
  const bytes = Uint8Array.from(binary, (character_) => character_.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}
