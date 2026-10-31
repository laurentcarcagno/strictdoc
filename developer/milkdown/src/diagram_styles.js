// The shapes of the palette and the default styles of the diagram editor.
// The keys are the style keys of maxGraph. Every label is plain text (no
// HTML label), so that the exported SVG has <text> elements and no
// foreignObject, which the SVG sanitizer of the server would remove.

export const FONT_FAMILY = 'IBM Plex Sans, sans-serif';
export const INK = '#12293a';
export const PAPER = '#ffffff';

export const SHAPES = [
  { id: 'rectangle', label: 'Rectangle', size: [120, 60], style: { shape: 'rectangle' } },
  { id: 'rounded', label: 'Rounded rectangle', size: [120, 60], style: { shape: 'rectangle', rounded: true } },
  { id: 'ellipse', label: 'Ellipse', size: [120, 70], style: { shape: 'ellipse', perimeter: 'ellipsePerimeter' } },
  { id: 'diamond', label: 'Diamond', size: [110, 80], style: { shape: 'rhombus', perimeter: 'rhombusPerimeter' } },
  { id: 'triangle', label: 'Triangle', size: [80, 80], style: { shape: 'triangle', perimeter: 'trianglePerimeter' } },
  { id: 'cylinder', label: 'Cylinder', size: [80, 100], style: { shape: 'cylinder' } },
  { id: 'note', label: 'Note', size: [120, 70], style: { shape: 'rectangle', fillColor: '#fff2cc', strokeColor: '#bf9000' } },
  { id: 'text', label: 'Text box', size: [120, 30], style: { shape: 'rectangle', fillColor: 'none', strokeColor: 'none' } },
];

export const SHAPE_ICONS = {
  rectangle: '<rect x="2" y="4" width="12" height="8"/>',
  rounded: '<rect x="2" y="4" width="12" height="8" rx="3"/>',
  ellipse: '<ellipse cx="8" cy="8" rx="6" ry="4"/>',
  diamond: '<path d="M8 2 14 8 8 14 2 8z"/>',
  triangle: '<path d="M8 3 14 13H2z"/>',
  cylinder: '<ellipse cx="8" cy="4" rx="5" ry="2"/><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4"/>',
  note: '<path d="M2 3h12v10H2z" fill="currentColor" fill-opacity=".2"/>',
  text: '<path d="M3 4h10M8 4v9M6 13h4"/>',
};

export const ARROWS = [
  { value: 'none', label: 'None' },
  { value: 'classic', label: 'Arrow' },
  { value: 'open', label: 'Open arrow' },
  { value: 'diamond', label: 'Diamond' },
  { value: 'oval', label: 'Circle' },
];

export const EDGE_TYPES = [
  { value: 'straight', label: 'Straight' },
  { value: 'elbow', label: 'Elbow' },
];

export const FONT_SIZES = [10, 12, 14, 16, 20, 24, 32];
export const LINE_WIDTHS = [1, 2, 3, 4, 6];

// The style the cells have until the user changes it.
export function applyDefaultStyles(graph) {
  const stylesheet = graph.getStylesheet();
  Object.assign(stylesheet.getDefaultVertexStyle(), {
    fillColor: PAPER,
    strokeColor: INK,
    strokeWidth: 1.5,
    fontColor: INK,
    fontFamily: FONT_FAMILY,
    fontSize: 14,
    align: 'center',
    verticalAlign: 'middle',
  });
  Object.assign(stylesheet.getDefaultEdgeStyle(), {
    strokeColor: INK,
    strokeWidth: 1.5,
    fontColor: INK,
    fontFamily: FONT_FAMILY,
    fontSize: 13,
    endArrow: 'classic',
    startArrow: 'none',
    labelBackgroundColor: PAPER,
  });
}

// The style keys of an edge type.
export function edgeTypeStyle(type) {
  return type === 'elbow'
    ? { edgeStyle: 'orthogonalEdgeStyle', rounded: true }
    : { edgeStyle: undefined, rounded: false };
}
