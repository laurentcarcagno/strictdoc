// Commands of the table bar. Each one is a ProseMirror command: (state,
// dispatch) => boolean, and returns true without dispatching when called
// without dispatch (the bar uses that to enable or disable its buttons).
//
// A table is `table_header_row* table_row+`: the header rows are the first
// rows, and one row of the body at least stays. What prosemirror-tables does
// not know about that (the type of a new row, the last row of the body) is done
// here; the rest (columns, merge, split, colours) is prosemirror-tables.
import { Selection, TextSelection } from '@milkdown/kit/prose/state';
import {
  CellSelection,
  addColumnAfter,
  addColumnBefore,
  cellAround,
  deleteColumn,
  deleteRow,
  deleteTable,
  isInTable,
  mergeCells,
  selectedRect,
  setCellAttr,
  splitCell,
} from '@milkdown/kit/prose/tables';

export { isInTable, mergeCells, splitCell, addColumnBefore, addColumnAfter, deleteColumn, deleteTable };

const HEADER_ROW = 'table_header_row';

function headerCount(table) {
  let count = 0;
  table.forEach((row) => {
    if (row.type.name === HEADER_ROW) count += 1;
  });
  return count;
}

function emptyRow(schema, template, header) {
  const cellType = schema.nodes[header ? 'table_header' : 'table_cell'];
  const cells = [];
  template.forEach((cell) => {
    cells.push(cellType.createAndFill({ alignment: cell.attrs.alignment, colspan: 1, rowspan: 1 }));
  });
  return schema.nodes[header ? HEADER_ROW : 'table_row'].create(null, cells);
}

// The row of a new row: the row it is next to, except under the last header row.
function addRow(after) {
  return (state, dispatch) => {
    if (!isInTable(state)) return false;
    if (dispatch) {
      const { map, table, tableStart, top, bottom } = selectedRect(state);
      const reference = after ? bottom - 1 : top;
      const at = after ? bottom : top;
      const headers = headerCount(table);
      const header = reference < headers && !(after && reference === headers - 1);
      const tr = state.tr;
      const cells = [];
      for (let column = 0; column < map.width; column += 1) {
        const index = at * map.width + column;
        if (at > 0 && at < map.height && map.map[index] === map.map[index - map.width]) {
          // A cell that goes through the new row gets taller.
          const pos = map.map[index];
          const cell = table.nodeAt(pos);
          tr.setNodeMarkup(tr.mapping.map(tableStart + pos), null, { ...cell.attrs, rowspan: cell.attrs.rowspan + 1 });
          column += cell.attrs.colspan - 1;
        } else {
          const source = table.nodeAt(map.map[reference * map.width + column]);
          const type = state.schema.nodes[header ? 'table_header' : 'table_cell'];
          cells.push(type.createAndFill({ alignment: source.attrs.alignment, colspan: 1, rowspan: 1 }));
        }
      }
      let rowPos = tableStart;
      for (let i = 0; i < at; i += 1) rowPos += table.child(i).nodeSize;
      tr.insert(rowPos, state.schema.nodes[header ? HEADER_ROW : 'table_row'].create(null, cells));
      dispatch(tr.scrollIntoView());
    }
    return true;
  };
}

export const addRowBefore = addRow(false);
export const addRowAfter = addRow(true);

// The rows of the selection can go when a row of the body stays.
export function removeRows(state, dispatch) {
  if (!isInTable(state)) return false;
  const { table, top, bottom } = selectedRect(state);
  const headers = headerCount(table);
  const bodyLeft = table.childCount - headers - (bottom - Math.max(top, headers));
  if (bodyLeft < 1) return false;
  return deleteRow(state, dispatch);
}

// Whether a cell goes through the line between the rows `at - 1` and `at`.
function crossesRows(map, at) {
  if (at <= 0 || at >= map.height) return false;
  for (let column = 0; column < map.width; column += 1) {
    if (map.map[at * map.width + column] === map.map[(at - 1) * map.width + column]) return true;
  }
  return false;
}

// The row of the selection and the rows above it are header rows, or, when it
// is one already, it and the rows under it go back to the body.
export function toggleHeaderRows(state, dispatch) {
  if (!isInTable(state)) return false;
  const rect = selectedRect(state);
  const { map, table, tableStart } = rect;
  const headers = headerCount(table);
  const makeHeader = rect.top >= headers;
  const wanted = makeHeader ? rect.bottom : rect.top;
  if (crossesRows(map, wanted)) return false;
  if (!dispatch) return true;

  const schema = state.schema;
  const rows = [];
  table.forEach((row) => rows.push(row));
  const needsBody = wanted >= rows.length;
  const converted = rows.map((row, index) => {
    const header = index < wanted;
    if (header === (row.type.name === HEADER_ROW)) return row;
    const cellType = schema.nodes[header ? 'table_header' : 'table_cell'];
    const cells = [];
    row.forEach((cell) => cells.push(cellType.create(cell.attrs, cell.content, cell.marks)));
    return schema.nodes[header ? HEADER_ROW : 'table_row'].create(null, cells);
  });
  if (needsBody) converted.push(emptyRow(schema, rows[rows.length - 1], false));

  const start = tableStart - 1;
  const tr = state.tr.replaceWith(start, start + table.nodeSize, table.type.create(table.attrs, converted));
  // The cells keep their positions, only the new row is added at the end.
  const { selection } = state;
  if (selection instanceof CellSelection) {
    tr.setSelection(new CellSelection(tr.doc.resolve(selection.$anchorCell.pos), tr.doc.resolve(selection.$headCell.pos)));
  } else {
    tr.setSelection(TextSelection.create(tr.doc, selection.anchor, selection.head));
  }
  dispatch(tr);
  return true;
}

export function headerState(state) {
  if (!isInTable(state)) return false;
  const { table, top } = selectedRect(state);
  return top < headerCount(table);
}

// ---- Selecting ------------------------------------------------------------

function select(from, to) {
  return (state, dispatch) => {
    if (!isInTable(state)) return false;
    if (dispatch) {
      const rect = selectedRect(state);
      const { map, table, tableStart } = rect;
      const [row1, column1, row2, column2] = from(rect, map);
      const first = tableStart + map.positionAt(row1, column1, table);
      const last = tableStart + map.positionAt(row2, column2, table);
      dispatch(state.tr.setSelection(new CellSelection(state.doc.resolve(first), state.doc.resolve(last))));
    }
    return true;
  };
}

export const selectCell = (state, dispatch) => {
  if (!isInTable(state)) return false;
  const $cell = cellAround(state.selection.$head);
  if (!$cell) return false;
  if (dispatch) dispatch(state.tr.setSelection(new CellSelection($cell)));
  return true;
};
export const selectRow = select((rect, map) => [rect.top, 0, rect.bottom - 1, map.width - 1]);
export const selectColumn = select((rect, map) => [0, rect.left, map.height - 1, rect.right - 1]);
export const selectTable = select((rect, map) => [0, 0, map.height - 1, map.width - 1]);

// ---- Inserting ------------------------------------------------------------

// A table of `rows` rows (the first one is the header row) and `columns` columns.
export function insertTable(rows, columns) {
  return (state, dispatch) => {
    const { schema } = state;
    const make = (header) => {
      const type = schema.nodes[header ? 'table_header' : 'table_cell'];
      const cells = Array.from({ length: columns }, () => type.createAndFill({ alignment: null }));
      return schema.nodes[header ? HEADER_ROW : 'table_row'].create(null, cells);
    };
    const table = schema.nodes.table.create(null, [make(true), ...Array.from({ length: Math.max(1, rows - 1) }, () => make(false))]);
    if (dispatch) {
      // A table is not put into a cell: it goes after the table of the cursor.
      let tr = state.tr;
      if (isInTable(state)) {
        const { table: current, tableStart } = selectedRect(state);
        const after = tableStart - 1 + current.nodeSize;
        tr.insert(after, table);
        tr.setSelection(Selection.near(tr.doc.resolve(after + 1), 1));
        dispatch(tr.scrollIntoView());
        return true;
      }
      tr = tr.replaceSelectionWith(table);
      // The cursor goes into the first cell.
      const start = tr.mapping.map(state.selection.from, -1);
      tr.setSelection(Selection.findFrom(tr.doc.resolve(Math.max(0, start - 1)), 1, true) ?? tr.selection);
      dispatch(tr.scrollIntoView());
    }
    return true;
  };
}

// ---- Colours and alignment ------------------------------------------------

export const fillCells = (color) => setCellAttr('background', color);
export const alignCells = (side) => setCellAttr('alignment', side);

export function cellFill(state) {
  if (!isInTable(state)) return null;
  const $cell = state.selection instanceof CellSelection ? state.selection.$anchorCell : cellAround(state.selection.$head);
  return $cell?.nodeAfter?.attrs.background ?? null;
}
