// The page view of the document screen: "Normal" (a wide column), "1 page"
// and "2 pages" (A4 sheets, one or two side by side).
//
// The nodes stay where they are in the page. Each one is moved on its sheet
// with a transform, so that editing, the menus and the streams of the
// server work as in the normal view. A node that would cross the bottom of a
// sheet starts the next one; a node taller than a sheet makes its sheet
// taller. The sheets are drawn behind the nodes, and the whole is scaled down
// when it does not fit the window.
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

  // The blocks to put on the sheets: what each node frame holds, in order.
  function blocksOf(content) {
    const blocks = [];
    const visit = (parent) => {
      for (const child of parent.children) {
        if (child.classList.contains('sdoc-page-sheets')) continue;
        const isFrame = child.localName === 'turbo-frame';
        if (isFrame && child.id.startsWith('article-')) {
          blocks.push(...child.children);
        } else if (isFrame && child.querySelector(':scope > turbo-frame')) {
          visit(child);
        } else {
          blocks.push(child);
        }
      }
    };
    visit(content);
    return blocks.filter((block) => block.offsetHeight > 0);
  }

  function isHeading(block) {
    return block.getAttribute('show-node-type-name') === 'SECTION' || block.getAttribute('node-role') === 'root';
  }

  function reset(content) {
    content.querySelectorAll('.sdoc-page-sheets').forEach((sheets) => sheets.remove());
    content.querySelectorAll('[data-page-moved]').forEach((block) => {
      block.style.transform = '';
      block.removeAttribute('data-page-moved');
    });
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
    content.style.width = `${width}px`;
    content.style.paddingInline = `${margin}px`;
    content.style.boxSizing = 'border-box';
    content.style.transform = 'none';

    const blocks = blocksOf(content);
    const pages = [];
    let page = null;
    for (const block of blocks) {
      const top = block.offsetTop;
      const bottom = top + block.offsetHeight;
      if (!page || (bottom - page.start > usable && page.blocks.length > 0)) {
        // A heading is not left alone at the bottom of a sheet.
        let carried = null;
        if (page && page.blocks.length > 1 && isHeading(page.blocks[page.blocks.length - 1].block)) {
          carried = page.blocks.pop();
          page.bottom = Math.max(...page.blocks.map((entry) => entry.bottom));
        }
        page = { start: carried ? carried.top : top, bottom, blocks: [] };
        pages.push(page);
        if (carried) page.blocks.push(carried);
      }
      page.blocks.push({ block, top, bottom });
      page.bottom = Math.max(page.bottom, bottom);
    }
    if (pages.length === 0) pages.push({ start: 0, bottom: 0, blocks: [] });

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
      for (const { block, top } of each.blocks) {
        const dx = left;
        const dy = rowTops[row] + margin + (top - each.start) - top;
        block.style.transform = `translate(${dx}px, ${dy}px)`;
        block.dataset.pageMoved = '';
      }
    });
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
    resizeObserver = new ResizeObserver(schedule);
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
          (node) => !(node.classList && node.classList.contains('sdoc-page-sheets')),
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
