// The page view of the document screen: "Normal" (a wide column), "1 page"
// and "2 pages" (A4 sheets, one or two side by side).
//
// The elements stay where they are in the page. Each one is moved on its sheet
// with a transform, so that editing, the menus and the streams of the
// server work as in the normal view. The flow is cut like the lines of a
// document: a node that does not fit in what is left of a sheet is cut into its
// parts (the title, the label of a field, the paragraphs, the rows of a table),
// and only a part that does not fit starts the next sheet. A paragraph is cut
// between two lines (the rest of it is a copy that is only drawn, clipped, on
// the next sheet; two lines at least stay on each sheet). A title or a label
// is not left alone at the bottom of a sheet, and a part taller than a sheet
// makes its sheet taller. The sheets are drawn behind the elements, and the
// whole is scaled down when it does not fit the window.
(() => {
  const KEY = 'sdoc-page-view';
  const MODES = ['normal', 'one', 'two'];
  const SHEET = { width: 210, height: 297, margin: 15, gap: 8 }; // mm
  const root = document.documentElement;

  let mode = 'normal';
  try {
    const saved = localStorage.getItem(KEY);
    if (MODES.includes(saved)) mode = saved;
  } catch (error) {
    // No storage: the normal view.
  }

  let scheduled = false;
  let resizeObserver = null;
  const sizes = new WeakMap();

  function pixelsPerMm() {
    const probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;visibility:hidden;width:0;height:100mm';
    document.body.append(probe);
    const pixels = probe.getBoundingClientRect().height / 100;
    probe.remove();
    return pixels;
  }

  function contentOf() {
    return document.querySelector('[data-viewtype="document"] .main .content');
  }

  const KEEP_WITH_NEXT = 'h1,h2,h3,h4,h5,h6,sdoc-node-title,sdoc-node-field-label';
  const MAX_DEPTH = 14;

  // The children of an element that can go on different sheets: they are
  // blocks, stacked one under the other. Anything else (text with inline
  // elements, fields side by side) is one part.
  function partsOf(element, style) {
    if (['svg', 'img', 'pre', 'textarea', 'sdoc-markdown-editor'].includes(element.localName)) return null;
    if (style.display.startsWith('inline') && style.display !== 'inline-flex') return null;
    for (const node of element.childNodes) {
      if (node.nodeType === Node.TEXT_NODE && node.textContent.trim() !== '') return null;
    }
    const parts = [];
    let end = -Infinity;
    for (const child of element.children) {
      const childStyle = getComputedStyle(child);
      if (childStyle.position === 'absolute' || childStyle.position === 'fixed') continue;
      if (childStyle.display === 'none' || child.localName === 'sdoc-field-service') continue;
      if (childStyle.display === 'contents') {
        // A frame: its children are parts of the parent.
        const inner = partsOf(child, childStyle);
        if (!inner) return null;
        for (const part of inner) {
          const rect = part.getBoundingClientRect();
          if (rect.top < end - 1) return null;
          end = Math.max(end, rect.bottom);
          parts.push(part);
        }
        continue;
      }
      if (childStyle.display.startsWith('inline') && childStyle.display !== 'inline-flex') return null;
      const rect = child.getBoundingClientRect();
      if (rect.height === 0) continue;
      if (rect.top < end - 1) return null;
      end = Math.max(end, rect.bottom);
      parts.push(child);
    }
    return parts.length > 0 ? parts : null;
  }

  function clearMoves(content) {
    content.querySelectorAll('.sdoc-page-clone').forEach((clone) => clone.remove());
    content.querySelectorAll('[data-page-moved]').forEach((block) => {
      block.style.transform = '';
      block.style.clipPath = '';
      block.removeAttribute('data-page-moved');
    });
  }

  // Paragraph-like: inline content only, lines of one height, no frame of its own.
  const NOT_TEXT = 'img,svg,pre,table,textarea,input,iframe,video,canvas,sdoc-markdown-editor';
  function linesOf(element, style, height) {
    const lineHeight = parseFloat(style.lineHeight);
    if (!(lineHeight > 0) || style.display !== 'block') return 0;
    const frame = ['paddingTop', 'paddingBottom', 'borderTopWidth', 'borderBottomWidth'];
    if (frame.some((side) => parseFloat(style[side]) !== 0)) return 0;
    if (element.querySelector(NOT_TEXT)) return 0;
    const count = Math.round(height / lineHeight);
    return Math.abs(count * lineHeight - height) <= 2 ? count : 0;
  }

  // A copy of a paragraph, to draw its last lines on another sheet.
  function copyOf(element) {
    const clone = element.cloneNode(true);
    clone.removeAttribute('id');
    clone.querySelectorAll('[id]').forEach((inner) => inner.removeAttribute('id'));
    clone.classList.add('sdoc-page-clone');
    clone.setAttribute('aria-hidden', 'true');
    clone.style.cssText += ';position:absolute;pointer-events:none;width:' + element.getBoundingClientRect().width + 'px';
    element.after(clone);
    return clone;
  }

  function reset(content) {
    content.querySelectorAll('.sdoc-page-sheets').forEach((sheets) => sheets.remove());
    clearMoves(content);
    content.style.cssText = '';
    resizeObserver?.disconnect();
  }

  function layout() {
    scheduled = false;
    const content = contentOf();
    if (!content) return;
    if (mode === 'normal') {
      root.classList.remove('sdoc-page-view');
      reset(content);
      return;
    }
    root.classList.add('sdoc-page-view');
    content.querySelectorAll('.sdoc-page-sheets').forEach((old) => old.remove());

    const mm = pixelsPerMm();
    const width = SHEET.width * mm;
    const height = SHEET.height * mm;
    const margin = SHEET.margin * mm;
    const gap = SHEET.gap * mm;
    const columns = mode === 'two' ? 2 : 1;
    const usable = height - 2 * margin;

    // The flow is one column of the width of the text of a sheet.
    clearMoves(content);
    content.style.cssText = '';
    content.style.width = `${width}px`;
    content.style.paddingInline = `${margin}px`;
    content.style.boxSizing = 'border-box';
    content.style.transform = 'none';

    const origin = content.getBoundingClientRect().top;
    const pages = [];
    const moved = [];
    let page = null;

    const startPage = (start) => {
      page = { start, bottom: start, units: [], index: pages.length };
      pages.push(page);
    };
    const add = (unit) => {
      if (unit.natural === undefined) unit.natural = unit.top;
      unit.page = page;
      page.units.push(unit);
      page.bottom = Math.max(page.bottom, unit.bottom);
      for (let up = unit.parent; up && !up.first; up = up.parent) up.first = unit;
    };
    // A new sheet; a title or a label at the bottom of the old one comes along.
    const breakPage = (start) => {
      const carried = [];
      while (page.units.length > 1 && page.units[page.units.length - 1].element.matches(KEEP_WITH_NEXT)) {
        carried.unshift(page.units.pop());
      }
      page.bottom = Math.max(page.start, ...page.units.map((unit) => unit.bottom));
      startPage(carried.length > 0 ? carried[0].top : start);
      carried.forEach(add);
    };

    const place = (element, parent, depth) => {
      const style = getComputedStyle(element);
      if (style.display === 'none') return;
      if (style.position === 'absolute' || style.position === 'fixed') return;
      if (style.display === 'contents') {
        for (const child of [...element.children]) place(child, parent, depth);
        return;
      }
      if (element.classList.contains('sdoc-page-sheets')) return;
      const rect = element.getBoundingClientRect();
      if (rect.height === 0) return;
      const top = rect.top - origin;
      const bottom = rect.bottom - origin;
      if (!page) startPage(top);
      if (bottom - page.start <= usable) {
        add({ element, top, bottom, parent });
        return;
      }
      const parts = depth < MAX_DEPTH ? partsOf(element, style) : null;
      if (parts) {
        const unit = { element, top, bottom, parent, first: null };
        moved.push(unit);
        parts.forEach((part) => place(part, unit, depth + 1));
        return;
      }
      const count = linesOf(element, style, bottom - top);
      if (count >= 4 && lines(element, style, top, count, parent)) return;
      if (page.units.length > 0) breakPage(top);
      add({ element, top, bottom, parent });
    };

    // A paragraph of `count` lines over as many sheets as it takes.
    const lines = (element, style, top, count, parent) => {
      const lineHeight = parseFloat(style.lineHeight);
      let from = 0;
      while (from < count) {
        const start = top + from * lineHeight;
        const room = Math.floor((usable - (start - page.start)) / lineHeight);
        const rest = count - from;
        let to;
        if (rest <= room) to = count;
        else if (room >= 2 && rest - room >= 2) to = from + room;
        else if (room >= 3) to = from + room - 1;
        else if (page.units.length === 0) to = from + Math.max(1, Math.min(room, rest));
        else {
          breakPage(start);
          continue;
        }
        const piece = from === 0 ? element : copyOf(element);
        const natural = piece.getBoundingClientRect().top - origin + from * lineHeight;
        const unit = { element: piece, top: start, bottom: top + to * lineHeight, natural, parent };
        unit.clip = [from * lineHeight, (count - to) * lineHeight];
        add(unit);
        from = to;
        if (from < count) breakPage(top + from * lineHeight);
      }
      return true;
    };
    for (const child of [...content.children]) place(child, null, 0);
    if (pages.length === 0) startPage(0);
    pages.forEach((each) => {
      moved.push(...each.units);
    });
    const blocks = moved.map((unit) => unit.element);

    // A sheet is at least A4, and taller for a node that does not fit.
    for (const each of pages) {
      each.height = Math.max(height, each.bottom - each.start + 2 * margin);
    }
    const rows = Math.ceil(pages.length / columns);
    const rowTops = [];
    let y = 0;
    for (let row = 0; row < rows; row += 1) {
      rowTops.push(y);
      let rowHeight = 0;
      for (let column = 0; column < columns; column += 1) {
        const each = pages[row * columns + column];
        if (each) rowHeight = Math.max(rowHeight, each.height);
      }
      y += rowHeight + gap;
    }
    const totalHeight = y - gap;
    const totalWidth = columns * width + (columns - 1) * gap;

    const sheets = document.createElement('div');
    sheets.className = 'sdoc-page-sheets';
    pages.forEach((each, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      const left = column * (width + gap);
      const sheet = document.createElement('div');
      sheet.className = 'sdoc-page-sheet';
      sheet.dataset.testid = 'page-sheet';
      sheet.style.cssText =
        `left:${left}px;top:${rowTops[row]}px;width:${width}px;height:${each.height}px`;
      const number = document.createElement('div');
      number.className = 'sdoc-page-sheet__number';
      number.textContent = `${index + 1} / ${pages.length}`;
      sheet.append(number);
      sheets.append(sheet);
    });
    // A part goes where its first leaf goes; what is inside it moves with it.
    const where = (unit) => {
      const leaf = unit.first || unit;
      const column = leaf.page.index % columns;
      const row = Math.floor(leaf.page.index / columns);
      return {
        dx: column * (width + gap),
        dy: rowTops[row] + margin + (leaf.top - leaf.page.start) - leaf.natural,
      };
    };
    for (const unit of moved) {
      if (unit.first === null) continue;
      const own = where(unit);
      const base = unit.parent ? where(unit.parent) : { dx: 0, dy: 0 };
      unit.element.style.transform = `translate(${own.dx - base.dx}px, ${own.dy - base.dy}px)`;
      unit.element.dataset.pageMoved = '';
      if (unit.clip) unit.element.style.clipPath = `inset(${unit.clip[0]}px 0 ${unit.clip[1]}px 0)`;
    }
    content.prepend(sheets);
    content.style.height = `${totalHeight}px`;

    // The window may be narrower than the sheets: scale the whole down.
    const main = content.closest('.main');
    const style = getComputedStyle(main);
    const available = main.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    const scale = Math.min(1, available / totalWidth);
    const offset = Math.max(0, (available - totalWidth * scale) / 2);
    content.style.transform = `scale(${scale})`;
    content.style.marginLeft = `${offset}px`;
    content.style.marginBottom = `${-(totalHeight * (1 - scale))}px`;

    resizeObserver?.disconnect();
    // Only a change of size, not the first notification of each element.
    resizeObserver = new ResizeObserver((entries) => {
      const changed = entries.some((entry) => {
        const size = `${entry.contentRect.width}x${entry.contentRect.height}`;
        const known = sizes.get(entry.target);
        sizes.set(entry.target, size);
        return known !== undefined && known !== size;
      });
      if (changed) schedule();
    });
    blocks.forEach((block) => resizeObserver.observe(block));
    resizeObserver.observe(main);
  }

  function schedule() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(layout);
  }

  function setMode(next) {
    mode = next;
    try {
      localStorage.setItem(KEY, mode);
    } catch (error) {
      // Not remembered.
    }
    showMode();
    schedule();
  }

  function showMode() {
    document.querySelectorAll('[data-page-view]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.pageView === mode));
    });
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-page-view]');
    if (button) setMode(button.dataset.pageView);
  });

  function start() {
    showMode();
    const main = document.querySelector('[data-viewtype="document"] .main');
    if (!main) return;
    // Nodes arrive, change or go (edits, lazy chunks): lay out again.
    new MutationObserver((mutations) => {
      const outside = mutations.some((mutation) =>
        [...mutation.addedNodes, ...mutation.removedNodes].some(
          (node) => !(node.classList && (node.classList.contains('sdoc-page-sheets') || node.classList.contains('sdoc-page-clone'))),
        ),
      );
      if (outside) schedule();
    }).observe(main, { childList: true, subtree: true });
    window.addEventListener('resize', schedule);
    window.addEventListener('load', schedule);
    schedule();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
