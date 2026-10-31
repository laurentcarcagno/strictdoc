// Crepe's image block reads the title of a Markdown image as its caption and
// refuses null. A Markdown image without a title (![1.00](./pic.png), what the
// editor writes) has a null title: the image was dropped from the editor when
// the field was opened again. The title becomes an empty string, whether this
// runs before or after the plugin that makes image blocks.
import { $remark } from '@milkdown/kit/utils';

function giveTitles(node) {
  const isImage = node.type === 'image' || node.type === 'image-block';
  if (isImage && (node.title === null || node.title === undefined)) {
    node.title = '';
  }
  if (Array.isArray(node.children)) node.children.forEach(giveTitles);
}

export const sdocImageCaption = $remark(
  'sdocImageCaption',
  () => () => (tree) => giveTitles(tree)
);
