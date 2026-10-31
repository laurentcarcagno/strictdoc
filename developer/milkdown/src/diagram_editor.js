// The diagram editor: a modal over the page, built on maxGraph.
//
//   openDiagramEditor({ svg }) -> Promise<string | null>
//
// svg is the text of the SVG file of an existing diagram, or null for a new
// one. The promise gives the SVG text of the diagram after Save, and null
// after Cancel.
import {
  Graph,
  ImageBox,
  InternalEvent,
  RubberBandHandler,
  UndoManager,
  getDefaultPlugins,
} from '@maxgraph/core';
import {
  ARROWS,
  EDGE_TYPES,
  FONT_SIZES,
  LINE_WIDTHS,
  SHAPES,
  SHAPE_ICONS,
  applyDefaultStyles,
  edgeTypeStyle,
} from './diagram_styles.js';
import { exportSvg, loadModel, readModel, serializeModel } from './diagram_svg.js';
import './diagram.css';

const FONT_BOLD = 1;
const FONT_ITALIC = 2;
const FONT_UNDERLINE = 4;
const PASTE_OFFSET = 20;

const ICONS = {
  connect: '<circle cx="3.5" cy="8" r="1.8"/><circle cx="12.5" cy="8" r="1.8"/><path d="M5.5 8h4.5M8.5 6l2 2-2 2"/>',
  undo: '<path d="M5 4 2.5 6.5 5 9M3 6.5h6.5a3.5 3.5 0 0 1 0 7H6"/>',
  redo: '<path d="M11 4l2.5 2.5L11 9M13 6.5H6.5a3.5 3.5 0 0 0 0 7H10"/>',
  duplicate: '<rect x="2" y="5" width="8" height="8"/><path d="M6 5V2.5h7.5V10H10"/>',
  trash: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 9h5.6l.7-9M7 7v4M9 7v4"/>',
  front: '<rect x="2" y="2" width="7" height="7" opacity=".5"/><rect x="7" y="7" width="7" height="7" fill="currentColor" fill-opacity=".3"/>',
  back: '<rect x="7" y="7" width="7" height="7" opacity=".5"/><rect x="2" y="2" width="7" height="7" fill="currentColor" fill-opacity=".3"/>',
  zoomIn: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14M7 5v4M5 7h4"/>',
  zoomOut: '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5 14 14M5 7h4"/>',
  fit: '<path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/>',
  alignLeft: '<path d="M2 4h12M2 7h8M2 10h12M2 13h8"/>',
  alignCenter: '<path d="M2 4h12M4 7h8M2 10h12M4 13h8"/>',
  alignRight: '<path d="M2 4h12M6 7h8M2 10h12M6 13h8"/>',
  dashed: '<path d="M2 8h2.5M6.75 8h2.5M11.5 8H14"/>',
  boxLeft: '<path d="M2.5 1.5v13"/><rect x="4" y="3" width="9" height="3.5"/><rect x="4" y="9.5" width="5.5" height="3.5"/>',
  boxCenter: '<path d="M8 1.5v13"/><rect x="3" y="3" width="10" height="3.5"/><rect x="5" y="9.5" width="6" height="3.5"/>',
  boxRight: '<path d="M13.5 1.5v13"/><rect x="3" y="3" width="9" height="3.5"/><rect x="6.5" y="9.5" width="5.5" height="3.5"/>',
  boxTop: '<path d="M1.5 2.5h13"/><rect x="3" y="4" width="3.5" height="9"/><rect x="9.5" y="4" width="3.5" height="5.5"/>',
  boxMiddle: '<path d="M1.5 8h13"/><rect x="3" y="3" width="3.5" height="10"/><rect x="9.5" y="5" width="3.5" height="6"/>',
  boxBottom: '<path d="M1.5 13.5h13"/><rect x="3" y="3" width="3.5" height="9"/><rect x="9.5" y="6.5" width="3.5" height="5.5"/>',
  distributeHorizontally: '<path d="M2 1.5v13M14 1.5v13"/><rect x="6.2" y="4" width="3.6" height="8"/>',
  distributeVertically: '<path d="M1.5 2h13M1.5 14h13"/><rect x="4" y="6.2" width="8" height="3.6"/>',
};

function icon(paths) {
  return `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true">${paths}</svg>`;
}

function element(tag, className, attributes = {}) {
  const created = document.createElement(tag);
  if (className) created.className = className;
  for (const [name, value] of Object.entries(attributes)) {
    created.setAttribute(name, value);
  }
  return created;
}

export function openDiagramEditor({ svg = null } = {}) {
  return new Promise((resolve) => {
    new DiagramEditor(svg, resolve);
  });
}

class DiagramEditor {
  constructor(svg, resolve) {
    this.resolve = resolve;
    this.controls = [];
    this.pasteCount = 0;
    this.clipboard = [];
    this.insertCount = 0;
    this.previousFocus = document.activeElement;

    this.buildDialog();
    this.buildGraph();
    this.buildToolbar();
    this.buildProperties();
    this.bindKeys();

    const xml = svg === null ? null : readModel(svg);
    if (xml !== null) {
      try {
        loadModel(this.graph, xml);
      } catch (error) {
        console.error('sdoc-diagram: the model could not be read', error);
      }
    }
    this.graph.getView().revalidate();
    this.showTopLeft();
    this.undoManager.clear();
    this.initialXml = serializeModel(this.graph);
    this.refresh();
    this.canvas.focus();
  }

  // ---- Dialog ----

  buildDialog() {
    this.root = element('div', 'sdoc-diagram', {
      role: 'dialog',
      'aria-modal': 'true',
      'aria-label': 'Diagram editor',
      'data-testid': 'diagram-editor',
    });
    const panel = element('div', 'sdoc-diagram__panel');
    const header = element('div', 'sdoc-diagram__header');
    const title = element('span', 'sdoc-diagram__title');
    title.textContent = 'Diagram';
    const hint = element('span', 'sdoc-diagram__hint');
    hint.textContent =
      'Double click to type. Drag the arrow of a shape to connect it.';
    this.saveButton = element('button', 'sdoc-diagram__text-button sdoc-diagram__text-button--primary', {
      type: 'button',
      'data-testid': 'diagram-save',
    });
    this.saveButton.textContent = 'Save';
    this.saveButton.addEventListener('click', () => this.save());
    const cancelButton = element('button', 'sdoc-diagram__text-button', {
      type: 'button',
      'data-testid': 'diagram-cancel',
    });
    cancelButton.textContent = 'Cancel';
    cancelButton.addEventListener('click', () => this.requestClose());
    header.append(title, hint, this.saveButton, cancelButton);

    this.toolbar = element('div', 'sdoc-diagram__bar', { role: 'toolbar', 'aria-label': 'Diagram tools' });
    this.properties = element('div', 'sdoc-diagram__bar', { role: 'toolbar', 'aria-label': 'Properties' });
    this.canvas = element('div', 'sdoc-diagram__canvas', {
      tabindex: '0',
      'data-testid': 'diagram-canvas',
    });
    panel.append(header, this.toolbar, this.properties, this.canvas);
    this.root.append(panel);
    document.body.append(this.root);
    document.documentElement.classList.add('sdoc-diagram-open');
  }

  close(result) {
    this.removeKeys();
    this.graph.destroy();
    this.root.remove();
    document.documentElement.classList.remove('sdoc-diagram-open');
    if (this.previousFocus instanceof HTMLElement) this.previousFocus.focus();
    this.resolve(result);
  }

  save() {
    if (this.isEmpty()) return;
    this.graph.stopEditing(false);
    let svg;
    try {
      svg = exportSvg(this.graph);
    } catch (error) {
      console.error('sdoc-diagram: export failed', error);
      window.alert('The diagram could not be exported.');
      return;
    }
    this.close(svg);
  }

  requestClose() {
    this.graph.stopEditing(true);
    const changed = serializeModel(this.graph) !== this.initialXml;
    if (changed && !window.confirm('Discard the changes of this diagram?')) {
      return;
    }
    this.close(null);
  }

  // ---- Graph ----

  buildGraph() {
    const graph = new Graph(this.canvas, undefined, [
      ...getDefaultPlugins(),
      RubberBandHandler,
    ]);
    this.graph = graph;
    applyDefaultStyles(graph);
    graph.setHtmlLabels(false);
    graph.setTooltips(false);
    graph.setConnectable(true);
    graph.setPanning(true);
    graph.setGridEnabled(true);
    graph.setGridSize(10);
    graph.setAllowDanglingEdges(true);
    graph.setDisconnectOnMove(false);
    graph.setEnterStopsCellEditing(false);
    graph.setAutoSizeCells(false);

    const connection = graph.getPlugin('ConnectionHandler');
    if (connection) {
      const arrow = encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"><circle cx="9" cy="9" r="8" fill="#12293a"/><path d="M5 9h7M9.5 6l3 3-3 3" stroke="#fff" stroke-width="1.6" fill="none"/></svg>'
      );
      connection.connectImage = new ImageBox(`data:image/svg+xml;utf8,${arrow}`, 18, 18);
    }

    // Undo and redo.
    const undoManager = new UndoManager();
    this.undoManager = undoManager;
    const listener = (_sender, event) => {
      undoManager.undoableEditHappened(event.getProperty('edit'));
    };
    graph.getDataModel().addListener(InternalEvent.UNDO, listener);
    graph.getView().addListener(InternalEvent.UNDO, listener);

    graph.getSelectionModel().addListener(InternalEvent.CHANGE, () => this.refresh());
    graph.getDataModel().addListener(InternalEvent.CHANGE, () => this.refresh());

    // Ctrl and the wheel zoom, the wheel alone scrolls.
    this.canvas.addEventListener(
      'wheel',
      (event) => {
        if (!event.ctrlKey && !event.metaKey) return;
        event.preventDefault();
        if (event.deltaY < 0) graph.zoomIn();
        else graph.zoomOut();
      },
      { passive: false }
    );
  }

  // The scrollable area starts at the top left of the content.
  showTopLeft() {
    const bounds = this.graph.getGraphBounds();
    if (bounds.width === 0 && bounds.height === 0) return;
    this.canvas.scrollLeft = Math.max(0, bounds.x - 24);
    this.canvas.scrollTop = Math.max(0, bounds.y - 24);
  }

  isEmpty() {
    return this.graph.getDefaultParent().getChildCount() === 0;
  }

  // The model coordinates of the middle of what the user sees.
  visibleCenter() {
    const view = this.graph.getView();
    const scale = view.scale;
    const x = (this.canvas.scrollLeft + this.canvas.clientWidth / 2) / scale - view.translate.x;
    const y = (this.canvas.scrollTop + this.canvas.clientHeight / 2) / scale - view.translate.y;
    return { x, y };
  }

  // ---- Commands ----

  addShape(shape) {
    const graph = this.graph;
    const [width, height] = shape.size;
    const center = this.visibleCenter();
    const shift = (this.insertCount % 8) * 20;
    this.insertCount += 1;
    const snap = (value) => graph.snap(value);
    let cell;
    graph.batchUpdate(() => {
      cell = graph.insertVertex({
        parent: graph.getDefaultParent(),
        value: '',
        position: [snap(center.x - width / 2 + shift), snap(center.y - height / 2 + shift)],
        size: [width, height],
        style: { ...shape.style },
      });
    });
    graph.setSelectionCell(cell);
    this.canvas.focus();
  }

  connectSelected() {
    const graph = this.graph;
    const vertices = graph.getSelectionCells().filter((cell_) => cell_.isVertex());
    if (vertices.length !== 2) return;
    let edge;
    graph.batchUpdate(() => {
      edge = graph.insertEdge({
        parent: graph.getDefaultParent(),
        value: '',
        source: vertices[0],
        target: vertices[1],
      });
    });
    graph.setSelectionCell(edge);
  }

  deleteSelection() {
    const graph = this.graph;
    if (graph.isSelectionEmpty()) return;
    graph.removeCells(graph.getSelectionCells(), true);
  }

  copySelection() {
    const graph = this.graph;
    if (graph.isSelectionEmpty()) return;
    this.clipboard = graph.cloneCells(graph.getSelectionCells(), false, null, true);
    this.pasteCount = 0;
  }

  paste() {
    if (this.clipboard.length === 0) return;
    const graph = this.graph;
    this.pasteCount += 1;
    const shift = PASTE_OFFSET * this.pasteCount;
    let cells = [];
    graph.batchUpdate(() => {
      cells = graph.importCells(
        graph.cloneCells(this.clipboard, false, null, true),
        shift,
        shift,
        graph.getDefaultParent()
      );
    });
    graph.setSelectionCells(cells);
  }

  duplicate() {
    this.copySelection();
    this.paste();
  }

  selectedVertices() {
    return this.graph.getSelectionCells().filter((cell_) => cell_.isVertex());
  }

  // edge is left, center, right, top, middle or bottom.
  alignShapes(edge) {
    const vertices = this.selectedVertices();
    if (vertices.length < 2) return;
    const graph = this.graph;
    graph.batchUpdate(() => graph.alignCells(edge, vertices));
  }

  // The shapes keep their order and the outer two stay where they are: the
  // gaps between neighbours become equal.
  distribute(direction) {
    const vertices = this.selectedVertices();
    if (vertices.length < 3) return;
    const horizontal = direction === 'horizontal';
    const start = (cell_) => (horizontal ? cell_.getGeometry().x : cell_.getGeometry().y);
    const size = (cell_) => (horizontal ? cell_.getGeometry().width : cell_.getGeometry().height);
    const ordered = [...vertices].sort((a, b) => start(a) - start(b));
    const first = start(ordered[0]);
    const last = Math.max(...ordered.map((cell_) => start(cell_) + size(cell_)));
    const total = ordered.reduce((sum, cell_) => sum + size(cell_), 0);
    const gap = (last - first - total) / (ordered.length - 1);
    const model = this.graph.getDataModel();
    this.graph.batchUpdate(() => {
      let position = first;
      for (const cell_ of ordered) {
        const geometry = cell_.getGeometry().clone();
        if (horizontal) geometry.x = position;
        else geometry.y = position;
        model.setGeometry(cell_, geometry);
        position += size(cell_) + gap;
      }
    });
  }

  nudge(dx, dy) {
    const graph = this.graph;
    if (graph.isSelectionEmpty()) return;
    graph.moveCells(graph.getSelectionCells(), dx, dy);
  }

  order(back) {
    const graph = this.graph;
    if (graph.isSelectionEmpty()) return;
    graph.orderCells(back, graph.getSelectionCells());
  }

  style(key, value) {
    this.styles({ [key]: value });
  }

  // Sets style keys on the selection; an undefined value removes the key.
  styles(values) {
    const graph = this.graph;
    if (graph.isSelectionEmpty()) return;
    const model = graph.getDataModel();
    graph.batchUpdate(() => {
      for (const cell_ of graph.getSelectionCells()) {
        const style = cell_.getClonedStyle();
        for (const [key, value] of Object.entries(values)) {
          if (value === undefined) delete style[key];
          else style[key] = value;
        }
        model.setStyle(cell_, style);
      }
    });
  }

  fontFlag(flag) {
    const graph = this.graph;
    if (graph.isSelectionEmpty()) return;
    graph.toggleCellStyleFlags('fontStyle', flag, graph.getSelectionCells());
  }

  // ---- Bars ----

  addControl(parent, control, { needs = 'any' } = {}) {
    parent.append(control);
    this.controls.push({ control, needs });
    return control;
  }

  group(parent, label) {
    const group = element('div', 'sdoc-diagram__group', { role: 'group', 'aria-label': label });
    parent.append(group);
    return group;
  }

  button(parent, testid, paths, title, onClick, options = {}) {
    const created = element('button', 'sdoc-diagram__button', {
      type: 'button',
      title,
      'aria-label': title,
      'data-testid': `diagram-${testid}`,
    });
    created.innerHTML = options.html ?? icon(paths);
    // The canvas keeps its selection and focus.
    created.addEventListener('mousedown', (event) => event.preventDefault());
    created.addEventListener('click', onClick);
    // The buttons that are always on are not in the list of controls.
    if (options.always === true) parent.append(created);
    else this.addControl(parent, created, { needs: options.needs ?? 'any' });
    return created;
  }

  select(parent, testid, label, choices, onChange, needs) {
    const wrapper = element('label', 'sdoc-diagram__select');
    const text = element('span');
    text.textContent = label;
    const created = element('select', '', { 'data-testid': `diagram-${testid}`, title: label });
    for (const choice of choices) {
      const option = element('option');
      option.value = String(choice.value ?? choice);
      option.textContent = choice.label ?? String(choice);
      created.append(option);
    }
    created.addEventListener('change', () => {
      onChange(created.value);
      this.canvas.focus();
    });
    wrapper.append(text, created);
    this.addControl(parent, wrapper, { needs });
    wrapper.field = created;
    return wrapper;
  }

  color(parent, testid, label, onChange, needs) {
    const wrapper = element('label', 'sdoc-diagram__select');
    const text = element('span');
    text.textContent = label;
    const created = element('input', 'sdoc-diagram__color', {
      type: 'color',
      'data-testid': `diagram-${testid}`,
      title: label,
    });
    created.addEventListener('change', () => onChange(created.value));
    wrapper.append(text, created);
    this.addControl(parent, wrapper, { needs });
    wrapper.field = created;
    return wrapper;
  }

  buildToolbar() {
    const shapes = this.group(this.toolbar, 'Shapes');
    for (const shape of SHAPES) {
      this.button(shapes, `shape-${shape.id}`, SHAPE_ICONS[shape.id], `Add a ${shape.label.toLowerCase()}`, () => this.addShape(shape), { always: true });
    }
    const connect = this.group(this.toolbar, 'Connector');
    this.connectButton = this.button(connect, 'connect', ICONS.connect, 'Connect the two selected shapes', () => this.connectSelected(), { needs: 'two-vertices' });

    const edit = this.group(this.toolbar, 'Edit');
    this.undoButton = this.button(edit, 'undo', ICONS.undo, 'Undo', () => this.undoManager.undo(), { always: true });
    this.redoButton = this.button(edit, 'redo', ICONS.redo, 'Redo', () => this.undoManager.redo(), { always: true });
    this.button(edit, 'duplicate', ICONS.duplicate, 'Duplicate', () => this.duplicate());
    this.button(edit, 'delete', ICONS.trash, 'Delete', () => this.deleteSelection());

    const align = this.group(this.toolbar, 'Align');
    for (const [name, title] of [
      ['left', 'Align left'],
      ['center', 'Align centres'],
      ['right', 'Align right'],
      ['top', 'Align top'],
      ['middle', 'Align middles'],
      ['bottom', 'Align bottom'],
    ]) {
      const icon_ = `box${name[0].toUpperCase()}${name.slice(1)}`;
      this.button(align, `align-shapes-${name}`, ICONS[icon_], title, () => this.alignShapes(name), { needs: 'vertices-2' });
    }
    this.button(align, 'distribute-horizontally', ICONS.distributeHorizontally, 'Distribute horizontally', () => this.distribute('horizontal'), { needs: 'vertices-3' });
    this.button(align, 'distribute-vertically', ICONS.distributeVertically, 'Distribute vertically', () => this.distribute('vertical'), { needs: 'vertices-3' });

    const arrange = this.group(this.toolbar, 'Arrange');
    this.button(arrange, 'front', ICONS.front, 'Bring to front', () => this.order(false));
    this.button(arrange, 'back', ICONS.back, 'Send to back', () => this.order(true));

    const view = this.group(this.toolbar, 'View');
    this.button(view, 'zoom-out', ICONS.zoomOut, 'Zoom out', () => this.graph.zoomOut(), { always: true });
    this.button(view, 'zoom-in', ICONS.zoomIn, 'Zoom in', () => this.graph.zoomIn(), { always: true });
    this.button(view, 'zoom-fit', ICONS.fit, 'Fit to window', () => this.fit(), { always: true });
  }

  fit() {
    this.graph.getPlugin('fit')?.fitCenter({ margin: 20 });
  }

  buildProperties() {
    const fill = this.group(this.properties, 'Fill');
    this.fillInput = this.color(fill, 'fill', 'Fill', (value) => this.style('fillColor', value), 'vertex');
    this.button(fill, 'fill-none', null, 'No fill', () => this.style('fillColor', 'none'), {
      needs: 'vertex',
      html: '<span class="sdoc-diagram__glyph">&#8709;</span>',
    });

    const line = this.group(this.properties, 'Line');
    this.strokeInput = this.color(line, 'stroke', 'Line', (value) => this.style('strokeColor', value), 'any');
    this.widthSelect = this.select(line, 'width', 'Width', LINE_WIDTHS, (value) => this.style('strokeWidth', Number(value)), 'any');
    this.dashedButton = this.button(line, 'dashed', ICONS.dashed, 'Dashed line', () => {
      this.style('dashed', this.dashedButton.getAttribute('aria-pressed') === 'true' ? undefined : true);
    });

    const text = this.group(this.properties, 'Text');
    this.fontColorInput = this.color(text, 'font-color', 'Text', (value) => this.style('fontColor', value), 'any');
    this.sizeSelect = this.select(text, 'font-size', 'Size', FONT_SIZES, (value) => this.style('fontSize', Number(value)), 'any');
    this.boldButton = this.button(text, 'bold', null, 'Bold', () => this.fontFlag(FONT_BOLD), { html: '<b>B</b>' });
    this.italicButton = this.button(text, 'italic', null, 'Italic', () => this.fontFlag(FONT_ITALIC), { html: '<i>I</i>' });
    this.underlineButton = this.button(text, 'underline', null, 'Underline', () => this.fontFlag(FONT_UNDERLINE), { html: '<u>U</u>' });
    this.alignButtons = {
      left: this.button(text, 'align-left', ICONS.alignLeft, 'Align left', () => this.style('align', 'left'), { needs: 'vertex' }),
      center: this.button(text, 'align-center', ICONS.alignCenter, 'Align centre', () => this.style('align', 'center'), { needs: 'vertex' }),
      right: this.button(text, 'align-right', ICONS.alignRight, 'Align right', () => this.style('align', 'right'), { needs: 'vertex' }),
    };

    const connector = this.group(this.properties, 'Connector');
    this.edgeTypeSelect = this.select(connector, 'edge-type', 'Type', EDGE_TYPES, (value) => this.styles(edgeTypeStyle(value)), 'edge');
    this.startArrowSelect = this.select(connector, 'start-arrow', 'Start', ARROWS, (value) => this.style('startArrow', value), 'edge');
    this.endArrowSelect = this.select(connector, 'end-arrow', 'End', ARROWS, (value) => this.style('endArrow', value), 'edge');
  }

  // Enables the controls that fit the selection and shows its style.
  refresh() {
    if (this.graph === undefined || this.graph.destroyed) return;
    const graph = this.graph;
    const cells = graph.getSelectionCells();
    const vertices = cells.filter((cell_) => cell_.isVertex());
    const edges = cells.filter((cell_) => cell_.isEdge());
    for (const { control, needs } of this.controls) {
      let enabled = cells.length > 0;
      if (needs === 'vertex') enabled = vertices.length > 0;
      if (needs === 'edge') enabled = edges.length > 0;
      if (needs === 'two-vertices') enabled = vertices.length === 2;
      if (needs === 'vertices-2') enabled = vertices.length >= 2;
      if (needs === 'vertices-3') enabled = vertices.length >= 3;
      if (control instanceof HTMLButtonElement) control.disabled = !enabled;
      else control.field.disabled = !enabled;
    }
    this.undoButton.disabled = !this.undoManager.canUndo();
    this.redoButton.disabled = !this.undoManager.canRedo();
    this.saveButton.disabled = this.isEmpty();

    if (cells.length === 0) return;
    const style = graph.getCurrentCellStyle(cells[0]);
    const hex = (value, fallback) =>
      typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value : fallback;
    this.fillInput.field.value = hex(style.fillColor, '#ffffff');
    this.strokeInput.field.value = hex(style.strokeColor, '#12293a');
    this.fontColorInput.field.value = hex(style.fontColor, '#12293a');
    this.widthSelect.field.value = String(style.strokeWidth ?? 1.5);
    this.sizeSelect.field.value = String(style.fontSize ?? 14);
    const fontStyle = style.fontStyle ?? 0;
    this.boldButton.setAttribute('aria-pressed', String((fontStyle & FONT_BOLD) !== 0));
    this.italicButton.setAttribute('aria-pressed', String((fontStyle & FONT_ITALIC) !== 0));
    this.underlineButton.setAttribute('aria-pressed', String((fontStyle & FONT_UNDERLINE) !== 0));
    this.dashedButton.setAttribute('aria-pressed', String(style.dashed === true));
    for (const [name, button] of Object.entries(this.alignButtons)) {
      button.setAttribute('aria-pressed', String((style.align ?? 'center') === name));
    }
    if (edges.length > 0) {
      const edgeStyle = graph.getCurrentCellStyle(edges[0]);
      this.edgeTypeSelect.field.value = edgeStyle.edgeStyle ? 'elbow' : 'straight';
      this.startArrowSelect.field.value = edgeStyle.startArrow ?? 'none';
      this.endArrowSelect.field.value = edgeStyle.endArrow ?? 'none';
    }
  }

  // ---- Keyboard ----

  bindKeys() {
    this.onKeyDown = (event) => this.handleKey(event);
    this.root.addEventListener('keydown', this.onKeyDown);
  }

  removeKeys() {
    this.root.removeEventListener('keydown', this.onKeyDown);
  }

  handleKey(event) {
    const graph = this.graph;
    const key = event.key;
    // The keys never reach the Markdown editor or the page below.
    event.stopPropagation();

    if (key === 'Tab') {
      this.trapFocus(event);
      return;
    }
    if (graph.isEditing()) return;
    if (key === 'Escape') {
      event.preventDefault();
      this.requestClose();
      return;
    }
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement) return;

    const command = event.ctrlKey || event.metaKey;
    if (command && key.toLowerCase() === 'z') {
      event.preventDefault();
      if (event.shiftKey) this.undoManager.redo();
      else this.undoManager.undo();
    } else if (command && key.toLowerCase() === 'y') {
      event.preventDefault();
      this.undoManager.redo();
    } else if (command && key.toLowerCase() === 'c') {
      event.preventDefault();
      this.copySelection();
    } else if (command && key.toLowerCase() === 'v') {
      event.preventDefault();
      this.paste();
    } else if (command && key.toLowerCase() === 'd') {
      event.preventDefault();
      this.duplicate();
    } else if (command && key.toLowerCase() === 'a') {
      event.preventDefault();
      graph.selectAll();
    } else if (key === 'Delete' || key === 'Backspace') {
      event.preventDefault();
      this.deleteSelection();
    } else if (key.startsWith('Arrow')) {
      event.preventDefault();
      const step = event.shiftKey ? 1 : graph.getGridSize();
      const dx = key === 'ArrowLeft' ? -step : key === 'ArrowRight' ? step : 0;
      const dy = key === 'ArrowUp' ? -step : key === 'ArrowDown' ? step : 0;
      this.nudge(dx, dy);
    } else if (key === 'Enter' && graph.getSelectionCount() === 1) {
      event.preventDefault();
      graph.startEditingAtCell(graph.getSelectionCell());
    }
  }

  trapFocus(event) {
    const focusable = [
      ...this.root.querySelectorAll('button:not(:disabled), select:not(:disabled), input:not(:disabled), [tabindex="0"]'),
    ].filter((node_) => node_.offsetParent !== null);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
}
