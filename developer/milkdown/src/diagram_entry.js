// Entry of the diagram.js bundle. The Markdown editor loads this bundle the
// first time the user draws a diagram (see diagram_loader.js) and calls:
//   window.sdocDiagram.open({ svg })   the modal; the SVG text, or null
//   window.sdocDiagram.isDiagram(svg)  true for the SVG of this editor
import { openDiagramEditor } from './diagram_editor.js';
import { readModel } from './diagram_svg.js';

window.sdocDiagram = {
  open: openDiagramEditor,
  isDiagram: (svg) => readModel(svg) !== null,
};
