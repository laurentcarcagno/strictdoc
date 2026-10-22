// The table bar: a row of buttons under the top bar of the editor, to make a
// table and to work on it as in a word processor. The buttons that need the
// cursor in a table are disabled outside of one.
import { $prose } from '@milkdown/kit/utils';
import { editorViewCtx } from '@milkdown/kit/core';
import { Plugin, PluginKey } from '@milkdown/kit/prose/state';
import {
  addColumnAfter,
  addColumnBefore,
  addRowAfter,
  addRowBefore,
  alignCells,
  cellFill,
  deleteColumn,
  deleteTable,
  fillCells,
  headerState,
  insertTable,
  isInTable,
  mergeCells,
  removeRows,
  selectCell,
  selectColumn,
  selectRow,
  selectTable,
  splitCell,
  toggleHeaderRows,
} from './table_commands.js';

const KEY = new PluginKey('SDOC_TABLE_BAR');
const MAX_ROWS = 10;
const MAX_COLUMNS = 8;

// Light fills first, then the stronger ones.
const COLORS = [
  '#fff2cc', '#fce4d6', '#e2efd9', '#deeaf6', '#ededed', '#e4dff0',
  '#ffd966', '#f4b183', '#a9d18e', '#9dc3e6', '#bfbfbf', '#b4a7d6',
  '#f4cccc', '#c9daf8', '#d0e0e3', '#ffe599', '#e6b8af', '#ffffff',
];

const ICONS = {
  table: '<rect x="2" y="3" width="12" height="10"/><path d="M2 7h12M2 10h12M6 3v10M10 3v10"/>',
  rowAbove: '<rect x="2" y="8" width="12" height="5"/><path d="M8 2v4M6 4h4"/>',
  rowBelow: '<rect x="2" y="3" width="12" height="5"/><path d="M8 10v4M6 12h4"/>',
  rowDelete: '<rect x="2" y="5" width="12" height="6"/><path d="M5 8h6"/>',
  columnLeft: '<rect x="8" y="2" width="5" height="12"/><path d="M2 8h4M4 6v4"/>',
  columnRight: '<rect x="3" y="2" width="5" height="12"/><path d="M10 8h4M12 6v4"/>',
  columnDelete: '<rect x="5" y="2" width="6" height="12"/><path d="M8 5v6"/>',
  merge: '<rect x="2" y="3" width="12" height="10"/><path d="M2 8h3M11 8h3M4 6.5 5.5 8 4 9.5M12 6.5 10.5 8 12 9.5"/>',
  split: '<rect x="2" y="3" width="12" height="10"/><path d="M8 3v10M5 6.5 3.5 8 5 9.5M11 6.5 12.5 8 11 9.5"/>',
  header: '<rect x="2" y="3" width="12" height="10"/><path d="M2 6.5h12" /><path d="M2 3h12v3.5H2z" fill="currentColor"/>',
  cell: '<rect x="2" y="3" width="12" height="10" stroke-dasharray="2 1.5"/><rect x="5" y="6" width="6" height="4"/>',
  selectRow: '<rect x="2" y="3" width="12" height="10"/><path d="M2 8h12" /><path d="M2 6.5h12v3H2z" fill="currentColor"/>',
  selectColumn: '<rect x="2" y="3" width="12" height="10"/><path d="M8 3v10" /><path d="M6.5 3h3v10h-3z" fill="currentColor"/>',
  selectTable: '<rect x="2" y="3" width="12" height="10" fill="currentColor" fill-opacity=".35"/><path d="M2 7h12M2 10h12M6 3v10M10 3v10"/>',
  fill: '<path d="M3 9 8 4l4 4-5 5z"/><path d="M13 10c1 1.5 1 2.5 0 3-1-.5-1-1.5 0-3z" fill="currentColor"/>',
  alignLeft: '<path d="M2 4h12M2 7h8M2 10h12M2 13h8"/>',
  alignCenter: '<path d="M2 4h12M4 7h8M2 10h12M4 13h8"/>',
  alignRight: '<path d="M2 4h12M6 7h8M2 10h12M6 13h8"/>',
  tableDelete: '<rect x="2" y="3" width="12" height="10"/><path d="M5 6l6 4M11 6l-6 4"/>',
};

function icon(name) {
  return `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true">${ICONS[name]}</svg>`;
}

class TableBar {
  constructor(view) {
    this.view = view;
    this.buttons = [];
    this.popup = null;

    this.bar = document.createElement('div');
    this.bar.className = 'sdoc-table-bar';
    this.bar.dataset.testid = 'table-bar';
    this.bar.setAttribute('role', 'toolbar');
    this.bar.setAttribute('aria-label', 'Table');

    this.addGroup('Table', [
      this.menu('insert', 'table', 'Insert a table', () => this.gridPicker(), false),
      this.button('table-delete', 'tableDelete', 'Delete the table', deleteTable),
    ]);
    this.addGroup('Rows', [
      this.button('row-above', 'rowAbove', 'Insert a row above', addRowBefore),
      this.button('row-below', 'rowBelow', 'Insert a row below', addRowAfter),
      this.button('row-delete', 'rowDelete', 'Delete the row', removeRows),
      this.button('header-row', 'header', 'Header row (repeated as a title row)', toggleHeaderRows, headerState),
    ]);
    this.addGroup('Columns', [
      this.button('column-left', 'columnLeft', 'Insert a column on the left', addColumnBefore),
      this.button('column-right', 'columnRight', 'Insert a column on the right', addColumnAfter),
      this.button('column-delete', 'columnDelete', 'Delete the column', deleteColumn),
    ]);
    this.addGroup('Cells', [
      this.button('merge', 'merge', 'Merge the selected cells', mergeCells),
      this.button('split', 'split', 'Split the merged cell', splitCell),
    ]);
    this.addGroup('Select', [
      this.button('select-cell', 'cell', 'Select the cell', selectCell),
      this.button('select-row', 'selectRow', 'Select the row', selectRow),
      this.button('select-column', 'selectColumn', 'Select the column', selectColumn),
      this.button('select-table', 'selectTable', 'Select the table', selectTable),
    ]);
    this.addGroup('Fill', [this.menu('fill', 'fill', 'Fill colour of the selected cells', () => this.palette(), true)]);
    this.addGroup('Align', [
      this.button('align-left', 'alignLeft', 'Align left', alignCells('left')),
      this.button('align-center', 'alignCenter', 'Align centre', alignCells('center')),
      this.button('align-right', 'alignRight', 'Align right', alignCells('right')),
    ]);

    const root = view.dom.parentElement;
    const topBar = root?.querySelector(':scope > .milkdown-top-bar');
    root?.insertBefore(this.bar, topBar ? topBar.nextSibling : root.firstChild);
    this.onOutside = (event) => {
      if (this.popup && !this.popup.contains(event.target) && !event.target.closest?.('[data-popup]')) this.closePopup();
    };
    document.addEventListener('mousedown', this.onOutside, true);
    this.update(view);
  }

  addGroup(label, items) {
    const group = document.createElement('div');
    group.className = 'sdoc-table-bar__group';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', label);
    group.append(...items);
    this.bar.append(group);
  }

  // A button never takes the focus: the selection of the editor stays.
  base(testid, name, title) {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = 'sdoc-table-bar__button';
    element.dataset.testid = `table-${testid}`;
    element.title = title;
    element.setAttribute('aria-label', title);
    element.innerHTML = icon(name);
    element.addEventListener('mousedown', (event) => event.preventDefault());
    return element;
  }

  button(testid, name, title, command, pressed) {
    const element = this.base(testid, name, title);
    element.addEventListener('click', () => {
      this.closePopup();
      this.run(command);
    });
    this.buttons.push({ element, command, pressed, needsTable: true });
    return element;
  }

  menu(testid, name, title, build, needsTable) {
    const element = this.base(testid, name, title);
    element.dataset.popup = testid;
    element.addEventListener('click', () => {
      if (this.popup?.dataset.for === testid) {
        this.closePopup();
        return;
      }
      this.closePopup();
      const popup = build();
      popup.dataset.for = testid;
      popup.className += ' sdoc-table-bar__popup';
      popup.style.left = `${element.offsetLeft}px`;
      this.bar.append(popup);
      this.popup = popup;
    });
    this.buttons.push({ element, command: null, needsTable });
    return element;
  }

  run(command) {
    const { view } = this;
    try {
      command(view.state, view.dispatch);
    } catch (error) {
      console.error('sdoc table bar:', error);
    }
    view.focus();
  }

  closePopup() {
    this.popup?.remove();
    this.popup = null;
  }

  // Rows and columns of the new table are chosen on a grid, as in Word.
  gridPicker() {
    const popup = document.createElement('div');
    const grid = document.createElement('div');
    grid.className = 'sdoc-table-bar__grid';
    const label = document.createElement('div');
    label.className = 'sdoc-table-bar__grid-label';
    label.textContent = 'Insert a table';
    const cells = [];
    for (let row = 1; row <= MAX_ROWS; row += 1) {
      for (let column = 1; column <= MAX_COLUMNS; column += 1) {
        const cell = document.createElement('button');
        cell.type = 'button';
        cell.className = 'sdoc-table-bar__grid-cell';
        cell.dataset.testid = `table-grid-${row}x${column}`;
        cell.setAttribute('aria-label', `${row} rows, ${column} columns`);
        cell.addEventListener('mousedown', (event) => event.preventDefault());
        cell.addEventListener('mouseenter', () => {
          label.textContent = `${row} rows x ${column} columns`;
          cells.forEach(({ element, r, c }) => element.classList.toggle('is-on', r <= row && c <= column));
        });
        cell.addEventListener('click', () => {
          this.closePopup();
          this.run(insertTable(row, column));
        });
        cells.push({ element: cell, r: row, c: column });
        grid.append(cell);
      }
    }
    grid.style.gridTemplateColumns = `repeat(${MAX_COLUMNS}, 1fr)`;
    popup.append(label, grid);
    return popup;
  }

  palette() {
    const popup = document.createElement('div');
    const swatches = document.createElement('div');
    swatches.className = 'sdoc-table-bar__swatches';
    for (const color of COLORS) {
      const swatch = document.createElement('button');
      swatch.type = 'button';
      swatch.className = 'sdoc-table-bar__swatch';
      swatch.dataset.testid = `table-color-${color.slice(1)}`;
      swatch.style.backgroundColor = color;
      swatch.title = color;
      swatch.setAttribute('aria-label', `Fill ${color}`);
      swatch.addEventListener('mousedown', (event) => event.preventDefault());
      swatch.addEventListener('click', () => {
        this.closePopup();
        this.run(fillCells(color));
      });
      swatches.append(swatch);
    }
    const none = document.createElement('button');
    none.type = 'button';
    none.className = 'sdoc-table-bar__text-button';
    none.dataset.testid = 'table-color-none';
    none.textContent = 'No fill';
    none.addEventListener('mousedown', (event) => event.preventDefault());
    none.addEventListener('click', () => {
      this.closePopup();
      this.run(fillCells(null));
    });
    const custom = document.createElement('label');
    custom.className = 'sdoc-table-bar__text-button';
    custom.textContent = 'Other colour ';
    const input = document.createElement('input');
    input.type = 'color';
    input.dataset.testid = 'table-color-custom';
    input.value = cellFill(this.view.state) ?? '#ffd966';
    // The editor keeps its selection while the picker is open.
    input.addEventListener('change', () => {
      this.closePopup();
      this.run(fillCells(input.value));
    });
    custom.append(input);
    popup.append(swatches, none, custom);
    return popup;
  }

  update(view) {
    this.view = view;
    const inTable = isInTable(view.state);
    const editable = view.editable;
    // The bar is shown when the toggle of the toolbar is on, and while the
    // cursor is in a table.
    this.bar.style.display = editable && (KEY.getState(view.state)?.pinned || inTable) ? '' : 'none';
    for (const { element, command, pressed, needsTable } of this.buttons) {
      let enabled = editable && (!needsTable || inTable);
      if (enabled && command) {
        try {
          enabled = command(view.state);
        } catch (error) {
          enabled = false;
        }
      }
      element.disabled = !enabled;
      if (pressed) element.setAttribute('aria-pressed', String(inTable && pressed(view.state)));
    }
    if (!inTable && this.popup?.dataset.for === 'fill') this.closePopup();
  }

  destroy() {
    document.removeEventListener('mousedown', this.onOutside, true);
    this.bar.remove();
  }
}

export const tableBar = $prose(() =>
  new Plugin({
    key: KEY,
    state: {
      init: () => ({ pinned: false }),
      apply: (tr, value) => tr.getMeta(KEY) ?? value,
    },
    view: (view) => new TableBar(view),
  })
);

// The button of the toolbar (Crepe top bar) that shows or hides the table bar.
export function buildTableToggle(builder) {
  builder.addGroup('sdoc-table', 'Table').addItem('sdoc-table-bar', {
    icon: icon('table').replace('<svg ', '<svg class="sdoc-table-icon" '),
    active: (ctx) => KEY.getState(ctx.get(editorViewCtx).state)?.pinned ?? false,
    onRun: (ctx) => {
      const view = ctx.get(editorViewCtx);
      const pinned = !KEY.getState(view.state)?.pinned;
      // The transaction also makes the toolbar draw the button again.
      view.dispatch(view.state.tr.setMeta(KEY, { pinned }));
    },
  });
}
