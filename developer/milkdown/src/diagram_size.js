// The display size of a diagram is the width and height of its <svg> element.
// The viewBox stays: a size that differs from the viewBox scales the drawing,
// and preserveAspectRatio="none" lets the two axes scale on their own. Every
// renderer of the SVG (editor, document view, PDF, Word) then shows the size.

const SVG_NS = 'http://www.w3.org/2000/svg';

function parse(svgText) {
  const document_ = new DOMParser().parseFromString(svgText, 'image/svg+xml');
  if (document_.querySelector('parsererror') !== null) return null;
  const root = document_.documentElement;
  return root.namespaceURI === SVG_NS && root.localName === 'svg' ? root : null;
}

// {width, height, viewBoxWidth, viewBoxHeight}, or null.
export function readSize(svgText) {
  const root = parse(svgText);
  if (root === null) return null;
  const width = Number.parseFloat(root.getAttribute('width'));
  const height = Number.parseFloat(root.getAttribute('height'));
  const viewBox = (root.getAttribute('viewBox') ?? '').split(/[\s,]+/).map(Number);
  const [, , viewBoxWidth, viewBoxHeight] = viewBox;
  const valid = [width, height, viewBoxWidth, viewBoxHeight].every((value_) => value_ > 0);
  return valid && viewBox.length === 4 ? { width, height, viewBoxWidth, viewBoxHeight } : null;
}

// The SVG text with another display size.
export function writeSize(svgText, width, height) {
  const root = parse(svgText);
  const size = readSize(svgText);
  if (root === null || size === null) return svgText;
  root.setAttribute('width', String(Math.round(width)));
  root.setAttribute('height', String(Math.round(height)));
  const uniform =
    Math.abs(width / size.viewBoxWidth - height / size.viewBoxHeight) < 0.005;
  if (uniform) root.removeAttribute('preserveAspectRatio');
  else root.setAttribute('preserveAspectRatio', 'none');
  return new XMLSerializer().serializeToString(root);
}

// A diagram that was drawn again keeps the scale the user gave to the
// previous drawing.
export function keepScale(newSvg, previousSvg) {
  const previous = readSize(previousSvg);
  const fresh = readSize(newSvg);
  if (previous === null || fresh === null) return newSvg;
  const scaleX = previous.width / previous.viewBoxWidth;
  const scaleY = previous.height / previous.viewBoxHeight;
  if (Math.abs(scaleX - 1) < 0.001 && Math.abs(scaleY - 1) < 0.001) return newSvg;
  return writeSize(newSvg, fresh.viewBoxWidth * scaleX, fresh.viewBoxHeight * scaleY);
}
