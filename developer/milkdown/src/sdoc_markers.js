// Milkdown nodes that keep StrictDoc's "[LINK: UID]" and "[ANCHOR: id, "title"]"
// markers intact. Without them the Markdown serializer writes "\[LINK: UID\]",
// which the SDoc grammar no longer reads as a link.
import { $inputRule, $node, $remark } from '@milkdown/kit/utils';
import { InputRule } from '@milkdown/kit/prose/inputrules';

const MARKERS = [
  // The UID pattern is REGEX_UID of strictdoc/backend/sdoc/grammar/grammar.py.
  { name: 'sdocLink', label: 'LINK', pattern: '[\\w]+[\\w()\\-\\/.: ]*' },
  { name: 'sdocAnchor', label: 'ANCHOR', pattern: '[^\\]\\r\\n]+' },
];

function splitTextNode(node, marker) {
  const regex = new RegExp(`\\[${marker.label}: (${marker.pattern})\\]`, 'g');
  const parts = [];
  let last = 0;
  for (const match of node.value.matchAll(regex)) {
    if (match.index > last) {
      parts.push({ type: 'text', value: node.value.slice(last, match.index) });
    }
    parts.push({ type: marker.name, value: match[1] });
    last = match.index + match[0].length;
  }
  if (parts.length === 0) return null;
  if (last < node.value.length) {
    parts.push({ type: 'text', value: node.value.slice(last) });
  }
  return parts;
}

function transformChildren(parent, marker) {
  if (!Array.isArray(parent.children)) return;
  const children = [];
  for (const child of parent.children) {
    if (child.type === 'text') {
      children.push(...(splitTextNode(child, marker) ?? [child]));
    } else {
      transformChildren(child, marker);
      children.push(child);
    }
  }
  parent.children = children;
}

function createMarker(marker) {
  const remarkPlugin = $remark(`${marker.name}Remark`, () =>
    function sdocMarkerPlugin() {
      const data = this.data();
      (data.toMarkdownExtensions ??= []).push({
        handlers: {
          [marker.name]: (node) => `[${marker.label}: ${node.value}]`,
        },
      });
      return (tree) => transformChildren(tree, marker);
    }
  );

  const node = $node(marker.name, () => ({
    group: 'inline',
    inline: true,
    atom: true,
    selectable: true,
    attrs: { value: { default: '' } },
    parseDOM: [
      {
        tag: `span[data-sdoc-marker="${marker.name}"]`,
        getAttrs: (dom) => ({ value: dom.getAttribute('data-value') ?? '' }),
      },
    ],
    toDOM: (n) => [
      'span',
      {
        class: `sdoc-marker sdoc-marker-${marker.label.toLowerCase()}`,
        'data-sdoc-marker': marker.name,
        'data-value': n.attrs.value,
        title: `${marker.label}: ${n.attrs.value}`,
      },
      `${marker.label}: ${n.attrs.value}`,
    ],
    parseMarkdown: {
      match: (n) => n.type === marker.name,
      runner: (state, n, type) => {
        state.addNode(type, { value: n.value });
      },
    },
    toMarkdown: {
      match: (n) => n.type.name === marker.name,
      runner: (state, n) => {
        state.addNode(marker.name, undefined, n.attrs.value);
      },
    },
  }));

  // Typing "[LINK: R-1]" turns the text into the node as soon as "]" is typed.
  const inputRule = $inputRule((ctx) =>
    new InputRule(
      new RegExp(`\\[${marker.label}: (${marker.pattern})\\]$`),
      (state, match, start, end) =>
        state.tr.replaceWith(
          start,
          end,
          node.type(ctx).create({ value: match[1] })
        )
    )
  );

  return [remarkPlugin, node, inputRule].flat();
}

export const sdocMarkers = MARKERS.flatMap(createMarker);
