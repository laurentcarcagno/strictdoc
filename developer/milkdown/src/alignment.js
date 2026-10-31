// The alignment of a paragraph: left, centre, right or justified.
//
// Markdown has no alignment, and StrictDoc renders the HTML of a Markdown field
// as it is. A paragraph that is not aligned to the left is written as an HTML
// paragraph, with its inline content as HTML (the way the tables write their
// cells), and read back only when every tag and attribute of it is known:
//
//   <p style="text-align: center">Some <strong>text</strong>.</p>
//
// A left paragraph stays a Markdown paragraph. Other HTML stays as written.
import { editorViewCtx } from '@milkdown/kit/core';
import { paragraphSchema } from '@milkdown/kit/preset/commonmark';
import { $remark } from '@milkdown/kit/utils';
import { NotATable, inlineHtml, phrasing, trimEdges } from './tables.js';

const ALIGNED = 'sdocAlignedParagraph';
const ALIGNMENTS = ['left', 'center', 'right', 'justify'];
const CELL_TYPES = ['table_cell', 'table_header'];

const ITEMS = [
  { name: 'left', label: 'Align left', icon: '<path d="M2 4h12M2 7h8M2 10h12M2 13h8"/>' },
  { name: 'center', label: 'Align centre', icon: '<path d="M2 4h12M4 7h8M2 10h12M4 13h8"/>' },
  { name: 'right', label: 'Align right', icon: '<path d="M2 4h12M6 7h8M2 10h12M6 13h8"/>' },
  { name: 'justify', label: 'Justify', icon: '<path d="M2 4h12M2 7h12M2 10h12M2 13h12"/>' },
];

// ---- Schema ----------------------------------------------------------------

function alignOf(dom) {
  const value = dom.style?.textAlign || dom.getAttribute?.('align');
  return ALIGNMENTS.includes(value) && value !== 'left' ? value : null;
}

const alignedParagraph = paragraphSchema.extendSchema((previous) => (ctx) => {
  const base = previous(ctx);
  return {
    ...base,
    attrs: { align: { default: null } },
    parseDOM: [{ tag: 'p', getAttrs: (dom) => ({ align: alignOf(dom) }) }],
    toDOM: (node) => {
      const [tag, attributes, hole] = base.toDOM(node);
      const align = node.attrs.align;
      return [tag, align ? { ...attributes, style: `text-align: ${align}` } : attributes, hole];
    },
    parseMarkdown: {
      match: (node) => node.type === 'paragraph' || node.type === ALIGNED,
      runner: (state, node, type) => {
        state.openNode(type, node.type === ALIGNED ? { align: node.align } : undefined);
        if (node.children) state.next(node.children);
        else state.addText(node.value || '');
        state.closeNode();
      },
    },
    toMarkdown: {
      match: base.toMarkdown.match,
      runner: (state, node) => {
        const align = node.attrs.align;
        if (align && node.content.size > 0) {
          state.addNode('html', undefined, `<p style="text-align: ${align}">${inlineHtml(node)}</p>`);
        } else {
          base.toMarkdown.runner(state, node);
        }
      },
    },
  };
});

// ---- Reading ---------------------------------------------------------------

// The aligned paragraph of an HTML block, as mdast; anything unknown refuses it.
function fromHtmlParagraph(html) {
  const body = new DOMParser().parseFromString(html, 'text/html').body;
  const [paragraph, ...others] = body.children;
  if (others.length > 0 || paragraph?.localName !== 'p') throw new NotATable('paragraph');
  if (body.textContent.replace(/\s+/g, '') !== paragraph.textContent.replace(/\s+/g, '')) {
    throw new NotATable('text around');
  }
  if ([...paragraph.attributes].some((attribute) => !['style', 'align'].includes(attribute.name))) {
    throw new NotATable('attribute');
  }
  let align = null;
  const attribute = paragraph.getAttribute('align');
  if (attribute !== null) {
    if (!ALIGNMENTS.includes(attribute)) throw new NotATable('align');
    align = attribute;
  }
  for (const declaration of (paragraph.getAttribute('style') ?? '').split(';')) {
    if (declaration.trim() === '') continue;
    const at = declaration.indexOf(':');
    const property = declaration.slice(0, at).trim().toLowerCase();
    const value = declaration.slice(at + 1).trim().toLowerCase();
    if (at < 0 || property !== 'text-align' || !ALIGNMENTS.includes(value)) throw new NotATable('style');
    align = value;
  }
  // A paragraph without alignment is plain HTML written by hand: it stays.
  if (align === null) throw new NotATable('no alignment');
  return {
    type: ALIGNED,
    align: align === 'left' ? null : align,
    children: trimEdges(phrasing(paragraph)),
  };
}

// The block HTML of the Markdown, which the commonmark preset may wrap in a paragraph.
function htmlParagraphOf(node) {
  const html = node.type === 'paragraph' && node.children?.length === 1 ? node.children[0] : node;
  return html.type === 'html' && /^\s*<p[\s>]/i.test(html.value) ? html : null;
}

function transformParagraphs(parent) {
  if (!Array.isArray(parent.children)) return;
  parent.children = parent.children.map((child) => {
    const html = htmlParagraphOf(child);
    if (html) {
      try {
        return fromHtmlParagraph(html.value);
      } catch (error) {
        if (!(error instanceof NotATable)) throw error;
        return child;
      }
    }
    transformParagraphs(child);
    return child;
  });
}

const alignedParagraphRemark = $remark('sdocAlignedParagraphRemark', () =>
  function sdocAlignedParagraphPlugin() {
    return (tree) => transformParagraphs(tree);
  }
);

// ---- Command and buttons ---------------------------------------------------

// The paragraphs of the selection that are not in a table cell (a cell has its
// own alignment, in the table bar).
function selectedParagraphs(state) {
  const found = [];
  const { from, to } = state.selection;
  state.doc.nodesBetween(from, to, (node, position, parent) => {
    if (node.type.name === 'paragraph' && !CELL_TYPES.includes(parent?.type.name)) {
      found.push({ node, position });
    }
    return true;
  });
  return found;
}

export function paragraphAlign(state) {
  return selectedParagraphs(state)[0]?.node.attrs.align ?? 'left';
}

export function setParagraphAlign(view, align) {
  const paragraphs = selectedParagraphs(view.state);
  if (paragraphs.length === 0) return;
  const value = align === 'left' ? null : align;
  const transaction = view.state.tr;
  for (const { node, position } of paragraphs) {
    transaction.setNodeMarkup(position, undefined, { ...node.attrs, align: value });
  }
  view.dispatch(transaction.scrollIntoView());
  view.focus();
}

function icon(paths) {
  return `<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true">${paths}</svg>`;
}

// The buttons of the toolbar (Crepe top bar).
export function buildAlignButtons(builder) {
  const group = builder.addGroup('sdoc-align', 'Alignment');
  for (const item of ITEMS) {
    group.addItem(`sdoc-align-${item.name}`, {
      icon: icon(item.icon),
      label: item.label,
      active: (ctx) => paragraphAlign(ctx.get(editorViewCtx).state) === item.name,
      onRun: (ctx) => setParagraphAlign(ctx.get(editorViewCtx), item.name),
    });
  }
}

export const sdocParagraphAlign = [alignedParagraphRemark, alignedParagraph].flat();
