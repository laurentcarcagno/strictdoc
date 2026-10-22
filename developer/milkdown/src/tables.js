// Tables of the editor: what Word users expect (header rows, merged cells,
// coloured cells) written in a Markdown field.
//
// A simple table (one header row, no merged cell, no colour) is a pipe table,
// as before. Any other table is an HTML <table>: Markdown has no way to write
// a merged cell or a colour, and StrictDoc renders the HTML of a Markdown field
// as it is. The HTML is written without a blank line (a blank line ends an HTML
// block) and read back only when every tag and attribute of it is known, so
// that a table written by hand with other attributes stays as it is.
import { $node, $remark } from '@milkdown/kit/utils';
import { tableNodes } from '@milkdown/kit/prose/tables';

const CELL_COLOR = /^#[0-9a-fA-F]{3,8}$/;

// ---- Schema ----------------------------------------------------------------

const alignment = {
  default: 'left',
  getFromDOM: (dom) => dom.style.textAlign || dom.getAttribute('align') || 'left',
  setDOMAttr: (value, attrs) => {
    attrs.style = `text-align: ${value || 'left'}`;
  },
};

const background = {
  default: null,
  getFromDOM: (dom) => dom.style.backgroundColor || null,
  setDOMAttr: (value, attrs) => {
    if (value) attrs.style = `${attrs.style ?? ''};background-color: ${value}`;
  },
};

// A cell holds paragraphs (several after two cells are merged); they are
// written as lines of one cell.
const original = tableNodes({
  tableGroup: 'block',
  cellContent: 'paragraph+',
  cellAttributes: { alignment, background },
});

function cellAttrs(node) {
  return {
    alignment: node.align ?? null,
    colspan: node.colspan ?? 1,
    rowspan: node.rowspan ?? 1,
    background: node.background ?? null,
    colwidth: null,
  };
}

function parseCell(header) {
  return {
    match: (node) => node.type === 'sdocTableCell' && Boolean(node.header) === header,
    runner: (state, node, type) => {
      state
        .openNode(type, cellAttrs(node))
        .openNode(state.schema.nodes.paragraph)
        .next(node.children)
        .closeNode()
        .closeNode();
    },
  };
}

// The rows and the cells are written by the table.
const writtenByTable = { match: () => false, runner: () => {} };

const tableNode = $node('table', () => ({
  ...original.table,
  content: 'table_header_row* table_row+',
  disableDropCursor: true,
  parseMarkdown: {
    match: (node) => node.type === 'sdocTable',
    runner: (state, node, type) => {
      state.openNode(type);
      state.next(node.children);
      state.closeNode();
    },
  },
  toMarkdown: {
    match: (node) => node.type.name === 'table',
    runner: (state, node) => writeTable(state, node),
  },
}));

const headerRowNode = $node('table_header_row', () => ({
  ...original.table_row,
  disableDropCursor: true,
  content: 'table_header*',
  parseDOM: [
    { tag: 'tr[data-is-header]' },
    {
      tag: 'tr',
      getAttrs: (dom) => (dom instanceof HTMLElement && dom.querySelector('th') ? {} : false),
    },
  ],
  toDOM: () => ['tr', { 'data-is-header': true }, 0],
  parseMarkdown: {
    match: (node) => node.type === 'sdocTableRow' && node.header,
    runner: (state, node, type) => {
      state.openNode(type);
      state.next(node.children);
      state.closeNode();
    },
  },
  toMarkdown: writtenByTable,
}));

const rowNode = $node('table_row', () => ({
  ...original.table_row,
  disableDropCursor: true,
  content: 'table_cell*',
  parseMarkdown: {
    match: (node) => node.type === 'sdocTableRow' && !node.header,
    runner: (state, node, type) => {
      state.openNode(type);
      state.next(node.children);
      state.closeNode();
    },
  },
  toMarkdown: writtenByTable,
}));

const cellNode = $node('table_cell', () => ({
  ...original.table_cell,
  disableDropCursor: true,
  parseMarkdown: parseCell(false),
  toMarkdown: writtenByTable,
}));

const headerNode = $node('table_header', () => ({
  ...original.table_header,
  disableDropCursor: true,
  parseMarkdown: parseCell(true),
  toMarkdown: writtenByTable,
}));

// ---- Reading: the tables of the Markdown -----------------------------------

class NotATable extends Error {}

function fromPipeTable(node) {
  const align = node.align ?? [];
  return {
    type: 'sdocTable',
    children: node.children.map((row, r) => ({
      type: 'sdocTableRow',
      header: r === 0,
      children: row.children.map((cell, c) => ({
        type: 'sdocTableCell',
        header: r === 0,
        align: align[c] ?? null,
        children: cell.children,
      })),
    })),
  };
}

const CELL_ATTRIBUTES = ['colspan', 'rowspan', 'style', 'align', 'bgcolor'];

function cssColor(value) {
  const color = value.trim();
  if (CELL_COLOR.test(color)) return color.toLowerCase();
  const rgb = color.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/);
  if (rgb) {
    return `#${[1, 2, 3].map((i) => Number(rgb[i]).toString(16).padStart(2, '0')).join('')}`;
  }
  throw new NotATable('colour');
}

function span(cell, name) {
  const raw = cell.getAttribute(name);
  if (raw === null) return 1;
  if (!/^[1-9]\d{0,2}$/.test(raw)) throw new NotATable(name);
  return Number(raw);
}

// The inline content of a cell as mdast; anything unknown refuses the table.
function phrasing(parent) {
  const out = [];
  for (const child of parent.childNodes) {
    if (child.nodeType === Node.TEXT_NODE) {
      const value = child.textContent.replace(/\s+/g, ' ');
      if (value !== '') out.push({ type: 'text', value });
      continue;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) continue;
    const name = child.localName;
    const attributes = [...child.attributes].map((a) => a.name);
    const only = (...allowed) => {
      if (attributes.some((a) => !allowed.includes(a))) throw new NotATable(name);
    };
    if (name === 'strong' || name === 'b') {
      only();
      out.push({ type: 'strong', children: phrasing(child) });
    } else if (name === 'em' || name === 'i') {
      only();
      out.push({ type: 'emphasis', children: phrasing(child) });
    } else if (name === 'del' || name === 's') {
      only();
      out.push({ type: 'delete', children: phrasing(child) });
    } else if (name === 'code') {
      only();
      if (child.children.length > 0) throw new NotATable(name);
      out.push({ type: 'inlineCode', value: child.textContent });
    } else if (name === 'br') {
      only();
      out.push({ type: 'break' });
    } else if (name === 'a') {
      only('href', 'title');
      const url = child.getAttribute('href');
      if (url === null) throw new NotATable(name);
      out.push({ type: 'link', url, title: child.getAttribute('title'), children: phrasing(child) });
    } else if (name === 'img') {
      only('src', 'alt', 'title');
      const url = child.getAttribute('src');
      if (url === null) throw new NotATable(name);
      out.push({ type: 'image', url, alt: child.getAttribute('alt') ?? '', title: child.getAttribute('title') });
    } else {
      throw new NotATable(name);
    }
  }
  return out;
}

function trimEdges(children) {
  const first = children[0];
  if (first?.type === 'text') first.value = first.value.replace(/^ /, '');
  const last = children[children.length - 1];
  if (last?.type === 'text') last.value = last.value.replace(/ $/, '');
  return children.filter((child) => child.type !== 'text' || child.value !== '');
}

function readCell(cell, header) {
  const attributes = [...cell.attributes].map((a) => a.name);
  if (attributes.some((a) => !CELL_ATTRIBUTES.includes(a))) throw new NotATable('attribute');
  const out = {
    type: 'sdocTableCell',
    header,
    colspan: span(cell, 'colspan'),
    rowspan: span(cell, 'rowspan'),
    align: null,
    background: null,
    children: trimEdges(phrasing(cell)),
  };
  const align = cell.getAttribute('align');
  if (align !== null) {
    if (!['left', 'center', 'right'].includes(align)) throw new NotATable('align');
    out.align = align;
  }
  const bgcolor = cell.getAttribute('bgcolor');
  if (bgcolor !== null) out.background = cssColor(bgcolor);
  for (const declaration of (cell.getAttribute('style') ?? '').split(';')) {
    if (declaration.trim() === '') continue;
    const at = declaration.indexOf(':');
    const property = declaration.slice(0, at).trim().toLowerCase();
    const value = declaration.slice(at + 1).trim().toLowerCase();
    if (at < 0) throw new NotATable('style');
    if (property === 'background-color' || property === 'background') {
      out.background = cssColor(value);
    } else if (property === 'text-align' && ['left', 'center', 'right'].includes(value)) {
      out.align = value;
    } else {
      throw new NotATable('style');
    }
  }
  return out;
}

// Header rows are the first rows, and every row has the same width.
function fromHtmlTable(html) {
  const body = new DOMParser().parseFromString(html, 'text/html').body;
  const tables = [...body.children];
  if (tables.length !== 1 || tables[0].localName !== 'table' || tables[0].attributes.length > 0) {
    throw new NotATable('table');
  }
  if (body.textContent.replace(/\s+/g, '') !== tables[0].textContent.replace(/\s+/g, '')) {
    throw new NotATable('text around');
  }
  const rows = [];
  let headers = 0;
  for (const part of tables[0].children) {
    if (!['thead', 'tbody'].includes(part.localName) || part.attributes.length > 0) {
      throw new NotATable(part.localName);
    }
    for (const row of part.children) {
      if (row.localName !== 'tr' || row.attributes.length > 0) throw new NotATable('row');
      const cells = [...row.children];
      if (cells.some((cell) => !['td', 'th'].includes(cell.localName))) throw new NotATable('cell');
      const allHeader = cells.length > 0 && cells.every((cell) => cell.localName === 'th');
      const noHeader = cells.every((cell) => cell.localName === 'td');
      const isHeader = part.localName === 'thead' || (allHeader && rows.length === headers);
      if (!allHeader && !noHeader && !(part.localName === 'thead')) throw new NotATable('th in a row');
      if (isHeader && rows.length === headers) headers += 1;
      else if (part.localName === 'thead') throw new NotATable('thead after rows');
      rows.push({ header: isHeader && rows.length < headers, cells });
    }
  }
  if (rows.length === 0) throw new NotATable('empty');
  // A table of headers only keeps its last row as a row of the body.
  if (headers === rows.length) headers -= 1;
  const model = rows.map((row, r) => ({
    type: 'sdocTableRow',
    header: r < headers,
    children: row.cells.map((cell) => readCell(cell, r < headers)),
  }));
  return { type: 'sdocTable', children: padRows(model) };
}

// Every row as wide as the table, counting the cells that come from the rows above.
function padRows(rows) {
  const taken = [];
  let width = 0;
  rows.forEach((row, r) => {
    taken[r] ??= [];
    let column = 0;
    for (const cell of row.children) {
      while (taken[r][column]) column += 1;
      for (let down = 0; down < cell.rowspan; down += 1) {
        taken[r + down] ??= [];
        for (let across = 0; across < cell.colspan; across += 1) taken[r + down][column + across] = true;
      }
      column += cell.colspan;
    }
    width = Math.max(width, taken[r].length, column);
  });
  rows.forEach((row, r) => {
    for (let column = 0; column < width; column += 1) {
      if (taken[r][column]) continue;
      row.children.push({
        type: 'sdocTableCell', header: row.header, colspan: 1, rowspan: 1, align: null, background: null, children: [],
      });
      taken[r][column] = true;
    }
  });
  // A cell that goes below the table is cut.
  rows.forEach((row, r) => {
    for (const cell of row.children) cell.rowspan = Math.min(cell.rowspan, rows.length - r);
  });
  return rows;
}

// The block HTML of the Markdown, which the commonmark preset may wrap in a paragraph.
function htmlOf(node) {
  const html = node.type === 'paragraph' && node.children.length === 1 ? node.children[0] : node;
  return html.type === 'html' && /^\s*<table[\s>]/i.test(html.value) ? html : null;
}

function transformTables(parent) {
  if (!Array.isArray(parent.children)) return;
  parent.children = parent.children.map((child) => {
    if (child.type === 'table') return fromPipeTable(child);
    const html = htmlOf(child);
    if (html) {
      try {
        return fromHtmlTable(html.value);
      } catch (error) {
        if (!(error instanceof NotATable)) throw error;
        return child;
      }
    }
    transformTables(child);
    return child;
  });
}

const tablesRemark = $remark('sdocTablesRemark', () =>
  function sdocTablesPlugin() {
    return (tree) => transformTables(tree);
  }
);

// ---- Writing ---------------------------------------------------------------

function cellParagraphs(cell) {
  const out = [];
  cell.forEach((paragraph) => out.push(paragraph));
  return out;
}

const side = (value) => value || 'left';

// A table is a pipe table when nothing of it needs HTML.
function isPipeTable(table) {
  let headers = 0;
  table.forEach((row) => {
    if (row.type.name === 'table_header_row') headers += 1;
  });
  if (headers !== 1) return false;
  const head = table.firstChild;
  let simple = true;
  table.forEach((row) => {
    if (row.childCount !== head.childCount) simple = false;
    row.forEach((cell, _offset, column) => {
      const { colspan, rowspan } = cell.attrs;
      const paragraphs = cellParagraphs(cell);
      const breaks = paragraphs[0]?.content.content.some(
        (node, at, all) => node.type.name === 'hardbreak' && at < all.length - 1
      );
      if (colspan !== 1 || rowspan !== 1 || cell.attrs.background) simple = false;
      if (paragraphs.length !== 1 || breaks) simple = false;
      if (side(cell.attrs.alignment) !== side(head.maybeChild(column)?.attrs.alignment)) simple = false;
    });
  });
  return simple;
}

// The inline content of a cell without its trailing hard break, which the next
// read would drop (a table cell cannot end with one).
function cellContent(cell) {
  const paragraph = cell.content.firstChild;
  const last = paragraph.lastChild;
  return last?.type.name === 'hardbreak'
    ? paragraph.content.cut(0, paragraph.content.size - last.nodeSize)
    : paragraph.content;
}

function writePipeTable(state, table) {
  const align = [];
  table.firstChild.forEach((cell) => align.push(cell.attrs.alignment));
  state.openNode('table', undefined, { align });
  table.forEach((row, _offset, index) => {
    state.openNode('tableRow', undefined, index === 0 ? { isHeader: true } : undefined);
    row.forEach((cell) => {
      state.openNode('tableCell');
      state.next(cellContent(cell));
      state.closeNode();
    });
    state.closeNode();
  });
  state.closeNode();
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function escapeAttribute(text) {
  return escapeHtml(text).replace(/"/g, '&quot;');
}

const MARK_TAGS = {
  strong: ['<strong>', '</strong>'],
  emphasis: ['<em>', '</em>'],
  strike_through: ['<del>', '</del>'],
  inlineCode: ['<code>', '</code>'],
};

function markTag(mark) {
  if (mark.type.name === 'link') {
    const title = mark.attrs.title ? ` title="${escapeAttribute(mark.attrs.title)}"` : '';
    return [`<a href="${escapeAttribute(mark.attrs.href)}"${title}>`, '</a>'];
  }
  return MARK_TAGS[mark.type.name] ?? ['', ''];
}

function inlineHtml(paragraph) {
  let out = '';
  let open = [];
  paragraph.forEach((node) => {
    const marks = node.marks;
    let keep = 0;
    while (keep < open.length && keep < marks.length && open[keep].eq(marks[keep])) keep += 1;
    for (let i = open.length - 1; i >= keep; i -= 1) out += markTag(open[i])[1];
    for (let i = keep; i < marks.length; i += 1) out += markTag(marks[i])[0];
    open = [...marks];
    switch (node.type.name) {
      case 'hardbreak':
        out += '<br />';
        break;
      case 'image': {
        const title = node.attrs.title ? ` title="${escapeAttribute(node.attrs.title)}"` : '';
        out += `<img src="${escapeAttribute(node.attrs.src)}" alt="${escapeAttribute(node.attrs.alt ?? '')}"${title} />`;
        break;
      }
      case 'sdocLink':
        out += `[LINK: ${escapeHtml(node.attrs.value)}]`;
        break;
      case 'sdocAnchor':
        out += `[ANCHOR: ${escapeHtml(node.attrs.value)}]`;
        break;
      default:
        out += escapeHtml(node.textContent);
    }
  });
  for (let i = open.length - 1; i >= 0; i -= 1) out += markTag(open[i])[1];
  return out;
}

function cellHtml(cell, tag) {
  const { colspan, rowspan, alignment: align, background: fill } = cell.attrs;
  let attributes = '';
  if (colspan > 1) attributes += ` colspan="${colspan}"`;
  if (rowspan > 1) attributes += ` rowspan="${rowspan}"`;
  const style = [];
  if (fill && CELL_COLOR.test(fill)) style.push(`background-color:${fill}`);
  if (align && align !== 'left') style.push(`text-align:${align}`);
  if (style.length > 0) attributes += ` style="${style.join(';')}"`;
  const lines = cellParagraphs(cell).map(inlineHtml).filter((line, i, all) => line !== '' || all.length === 1);
  return `<${tag}${attributes}>${lines.join('<br />')}</${tag}>`;
}

function writeHtmlTable(state, table) {
  const lines = ['<table>'];
  let section = '';
  const enter = (name) => {
    if (section === name) return;
    if (section) lines.push(`</${section}>`);
    lines.push(`<${name}>`);
    section = name;
  };
  table.forEach((row) => {
    const header = row.type.name === 'table_header_row';
    enter(header ? 'thead' : 'tbody');
    const cells = [];
    row.forEach((cell) => cells.push(cellHtml(cell, header ? 'th' : 'td')));
    lines.push(`<tr>${cells.join('')}</tr>`);
  });
  if (section) lines.push(`</${section}>`);
  lines.push('</table>');
  state.addNode('html', undefined, lines.join('\n'));
}

function writeTable(state, table) {
  if (isPipeTable(table)) writePipeTable(state, table);
  else writeHtmlTable(state, table);
}

export const sdocTables = [tablesRemark, tableNode, headerRowNode, rowNode, cellNode, headerNode].flat();
