// Admonitions (note, warning, ...) of a Markdown field.
//
// Markdown has no admonition, so a field writes one as HTML (see the user
// guide, "HTML elements in a Markdown field"):
//
//   <div class="sdoc-admonition sdoc-note" role="note">
//   <p class="sdoc-admonition-title">Note</p>
//
//   Text in **Markdown**.
//
//   </div>
//
// The editor reads this as three kinds of blocks: a paragraph that holds the
// opening HTML, the Markdown blocks, and a paragraph that holds </div>. The text
// of the field is not changed. This plugin only draws the blocks as a box
// (CSS classes on the three kinds of blocks, see sdoc_editor.css) and the slash
// menu inserts a new box, written as the same HTML.
import { commandsCtx } from '@milkdown/kit/core';
import { clearTextInCurrentBlockCommand } from '@milkdown/kit/preset/commonmark';
import { Plugin, PluginKey } from '@milkdown/kit/prose/state';
import { Decoration, DecorationSet } from '@milkdown/kit/prose/view';
import { $prose, insert } from '@milkdown/kit/utils';

export const ADMONITION_TYPES = [
  'note',
  'hint',
  'tip',
  'important',
  'attention',
  'caution',
  'danger',
  'error',
  'warning',
];

const OPENING = /^<div\s[^>]*class="([^"]*\bsdoc-admonition\b[^"]*)"[^>]*>/;
const TITLE = /<p\b[^>]*class="[^"]*\bsdoc-admonition-title\b[^"]*"[^>]*>([\s\S]*?)<\/p>/;
const CLOSING = /^<\/div>$/;

// The HTML of a paragraph that holds nothing but one HTML node, or null.
function htmlOnly(node) {
  if (node.type.name !== 'paragraph' || node.childCount !== 1) return null;
  const child = node.firstChild;
  return child.type.name === 'html' ? String(child.attrs.value).trim() : null;
}

function openingOf(html) {
  const match = OPENING.exec(html);
  if (match === null) return null;
  const classes = match[1].split(/\s+/);
  const type = ADMONITION_TYPES.find((name) => classes.includes(`sdoc-${name}`)) ?? 'plain';
  const title = TITLE.exec(html);
  return { type, title: title === null ? '' : title[1].replace(/<[^>]*>/g, '').trim() };
}

// The decorations of the boxes: an opening is drawn only when a closing follows.
export function admonitionDecorations(doc) {
  const decorations = [];
  let pending = null;
  doc.forEach((node, offset) => {
    const html = htmlOnly(node);
    if (pending === null) {
      const opening = html === null ? null : openingOf(html);
      if (opening !== null) pending = { ...opening, blocks: [{ node, offset, part: 'open' }] };
      return;
    }
    if (html !== null && CLOSING.test(html)) {
      pending.blocks.push({ node, offset, part: 'close' });
      for (const { node: block, offset: at, part } of pending.blocks) {
        const attributes = { class: `sdoc-adm sdoc-adm-${part} sdoc-adm-${pending.type}` };
        if (part === 'open') attributes['data-sdoc-title'] = pending.title;
        decorations.push(Decoration.node(at, at + block.nodeSize, attributes));
      }
      pending = null;
      return;
    }
    pending.blocks.push({ node, offset, part: 'body' });
  });
  return DecorationSet.create(doc, decorations);
}

const admonitionBoxes = $prose(
  () =>
    new Plugin({
      key: new PluginKey('SDOC_ADMONITION'),
      props: { decorations: (state) => admonitionDecorations(state.doc) },
    })
);

export function admonitionMarkdown(type) {
  const title = type.charAt(0).toUpperCase() + type.slice(1);
  return (
    `<div class="sdoc-admonition sdoc-${type}" role="note">\n` +
    `<p class="sdoc-admonition-title">${title}</p>\n\n` +
    'Text.\n\n</div>'
  );
}

const ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="1"/><path d="M3 9h18"/></svg>';

// The slash menu (Crepe BlockEdit buildMenu): one item per type.
export function buildAdmonitionMenu(builder) {
  const group = builder.addGroup('sdoc-admonitions', 'Admonition');
  for (const type of ADMONITION_TYPES) {
    group.addItem(`sdoc-admonition-${type}`, {
      label: `${type.charAt(0).toUpperCase()}${type.slice(1)} box`,
      icon: ICON,
      onRun: (ctx) => {
        ctx.get(commandsCtx).call(clearTextInCurrentBlockCommand.key);
        insert(admonitionMarkdown(type))(ctx);
      },
    });
  }
}

export const sdocAdmonition = [admonitionBoxes];
