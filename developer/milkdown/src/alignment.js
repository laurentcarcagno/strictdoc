// The alignment of paragraphs, images (and diagrams) and tables.
//
// Markdown has no alignment, and StrictDoc renders the HTML of a Markdown field
// as it is. What is not aligned to the left is written as HTML, and read back
// only when every tag and attribute of it is known:
//
//   a paragraph  <p style="text-align: center">Some <strong>text</strong>.</p>
//   an image     <p style="text-align: right"><img src="./pic.png" alt="1.00" /></p>
//   a table      <table style="width: fit-content; margin-left: auto; margin-right: auto">
//
// (the tables write their own HTML, see tables.js). A left paragraph and a left
// image stay Markdown. Other HTML stays as written.
//
// The four buttons of the toolbar work on what the cursor is in: a selected
// image, a table, or else the paragraphs of the selection. Justified is for
// paragraphs only. A table that is aligned takes the width of its content: a
// button that is already on puts the table back to the full width.
import { imageBlockSchema } from '@milkdown/kit/component/image-block';
import { editorViewCtx } from '@milkdown/kit/core';
import { paragraphSchema } from '@milkdown/kit/preset/commonmark';
import { NodeSelection, Plugin, PluginKey } from '@milkdown/kit/prose/state';
import { Decoration, DecorationSet } from '@milkdown/kit/prose/view';
import { $prose, $remark } from '@milkdown/kit/utils';
import { NotATable, escapeAttribute, inlineHtml, phrasing, trimEdges } from './tables.js';

const ALIGNED = 'sdocAlignedParagraph';
const ALIGNMENTS = ['left', 'center', 'right', 'justify'];
const BLOCK_ALIGNMENTS = ['left', 'center', 'right'];
const CELL_TYPES = ['table_cell', 'table_header'];
const IMAGE_BLOCK = 'image-block';

const ITEMS = [
  { name: 'left', label: 'Align left', icon: '<path d="M2 4h12M2 7h8M2 10h12M2 13h8"/>' },
  { name: 'center', label: 'Align centre', icon: '<path d="M2 4h12M4 7h8M2 10h12M4 13h8"/>' },
  { name: 'right', label: 'Align right', icon: '<path d="M2 4h12M6 7h8M2 10h12M6 13h8"/>' },
  { name: 'justify', label: 'Justify', icon: '<path d="M2 4h12M2 7h12M2 10h12M2 13h12"/>' },
];

// ---- Paragraph schema ------------------------------------------------------

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

// ---- Image block schema ----------------------------------------------------

const alignedImage = imageBlockSchema.extendSchema((previous) => (ctx) => {
  const base = previous(ctx);
  return {
    ...base,
    attrs: { ...base.attrs, align: { default: null } },
    parseMarkdown: {
      match: base.parseMarkdown.match,
      runner: (state, node, type) => {
        // A Markdown image has no title unless it was written with one.
        let ratio = Number(node.alt || 1);
        if (Number.isNaN(ratio) || ratio === 0) ratio = 1;
        state.addNode(type, {
          src: node.url,
          caption: node.title ?? '',
          ratio,
          align: node.align ?? null,
        });
      },
    },
    toMarkdown: {
      match: base.toMarkdown.match,
      runner: (state, node) => {
        const { src, caption, ratio, align } = node.attrs;
        if (!align) {
          base.toMarkdown.runner(state, node);
          return;
        }
        const alt = Number.parseFloat(ratio).toFixed(2);
        const title = caption ? ` title="${escapeAttribute(caption)}"` : '';
        state.addNode(
          'html',
          undefined,
          `<p style="text-align: ${align}"><img src="${escapeAttribute(src)}" alt="${alt}"${title} /></p>`
        );
      },
    },
  };
});

// ---- Reading ---------------------------------------------------------------

// The aligned paragraph or image of an HTML block, as mdast; anything unknown
// refuses it.
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
  const children = trimEdges(phrasing(paragraph));
  // A paragraph that holds one image is an image block.
  if (children.length === 1 && children[0].type === 'image') {
    const image = children[0];
    return {
      type: IMAGE_BLOCK,
      url: image.url,
      alt: image.alt,
      title: image.title ?? '',
      align: BLOCK_ALIGNMENTS.includes(align) && align !== 'left' ? align : null,
    };
  }
  return { type: ALIGNED, align: align === 'left' ? null : align, children };
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

// ---- Display of an aligned image -------------------------------------------

// The node view of an image block is Crepe's: the alignment reaches its CSS as
// an attribute of the block (sdoc_editor.css).
const alignedImageDisplay = $prose(() =>
  new Plugin({
    key: new PluginKey('SDOC_IMAGE_ALIGN'),
    props: {
      decorations: (state) => {
        const found = [];
        state.doc.descendants((node, position) => {
          if (node.type.name === IMAGE_BLOCK && node.attrs.align) {
            found.push(Decoration.node(position, position + node.nodeSize, { 'data-align': node.attrs.align }));
          }
          return node.type.name !== 'table';
        });
        return DecorationSet.create(state.doc, found);
      },
    },
  })
);

// ---- Command and buttons ---------------------------------------------------

// What the buttons act on: {kind: 'image' | 'table', position, node}, or
// {kind: 'paragraphs', paragraphs} (not those of a table cell, which has its
// own alignment in the table bar).
function target(state) {
  const { selection } = state;
  if (selection instanceof NodeSelection && selection.node.type.name === IMAGE_BLOCK) {
    return { kind: 'image', position: selection.from, node: selection.node };
  }
  const { $from } = selection;
  for (let depth = $from.depth; depth > 0; depth -= 1) {
    if ($from.node(depth).type.name === 'table') {
      return { kind: 'table', position: $from.before(depth), node: $from.node(depth) };
    }
  }
  const paragraphs = [];
  state.doc.nodesBetween(selection.from, selection.to, (node, position, parent) => {
    if (node.type.name === 'paragraph' && !CELL_TYPES.includes(parent?.type.name)) {
      paragraphs.push({ node, position });
    }
    return true;
  });
  return { kind: 'paragraphs', paragraphs };
}

// The alignment of what the cursor is in; null for a table at the full width.
export function currentAlign(state) {
  const found = target(state);
  if (found.kind === 'paragraphs') return found.paragraphs[0]?.node.attrs.align ?? 'left';
  if (found.kind === 'table') return found.node.attrs.align;
  return found.node.attrs.align ?? 'left';
}

export function setAlign(view, name) {
  const found = target(view.state);
  const transaction = view.state.tr;
  if (found.kind === 'paragraphs') {
    for (const { node, position } of found.paragraphs) {
      transaction.setNodeMarkup(position, undefined, { ...node.attrs, align: name === 'left' ? null : name });
    }
  } else {
    // Justified is for paragraphs only.
    if (!BLOCK_ALIGNMENTS.includes(name)) return;
    let value = name;
    if (found.kind === 'image') value = name === 'left' ? null : name;
    // The pressed button of a table goes back to the full width.
    else if (found.node.attrs.align === name) value = null;
    transaction.setNodeMarkup(found.position, undefined, { ...found.node.attrs, align: value });
  }
  if (!transaction.docChanged) return;
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
      active: (ctx) => currentAlign(ctx.get(editorViewCtx).state) === item.name,
      onRun: (ctx) => setAlign(ctx.get(editorViewCtx), item.name),
    });
  }
}

export const sdocAlignment = [alignedParagraphRemark, alignedParagraph, alignedImage, alignedImageDisplay].flat();
