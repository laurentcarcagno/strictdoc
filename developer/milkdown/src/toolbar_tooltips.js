// Tooltips for the buttons of the toolbars of the editor: the top bar of Crepe
// and the table bar.
//
// A button of the top bar has no label: Crepe draws an icon only. The labels
// come from the items that were registered (the order of the buttons in the
// page is the order of the items that have an action), so the Crepe items get
// a label from LABELS and the items of StrictDoc give their own `label`. A
// button with a `title` (the table bar) gives its title, and the browser tooltip
// is left out so that two bubbles never show.
const LABELS = {
  bold: 'Bold',
  italic: 'Italic',
  strikethrough: 'Strikethrough',
  code: 'Inline code',
  'bullet-list': 'Bulleted list',
  'ordered-list': 'Numbered list',
  'task-list': 'Task list',
  link: 'Link',
  image: 'Image',
  table: 'Table',
  'code-block': 'Code block',
  math: 'Formula',
  quote: 'Quote',
  hr: 'Horizontal rule',
};
const HEADING_LABEL = 'Text style';
const SHOW_DELAY_MS = 350;
const GAP = 6;
const TARGETS =
  '.top-bar-item, .top-bar-heading-button, .sdoc-table-bar [title], .sdoc-table-bar [data-tooltip]';

// builder: a function that gives the groups of the top bar (GroupBuilder.build).
export function installToolbarTooltips(host, builder) {
  const bubble = document.createElement('div');
  bubble.className = 'sdoc-tooltip';
  bubble.setAttribute('role', 'tooltip');
  bubble.id = `sdoc-tooltip-${Math.random().toString(36).slice(2)}`;
  bubble.hidden = true;
  document.body.append(bubble);

  let timer = 0;
  let current = null;

  // The text of a button, or null when it has none.
  function textOf(target) {
    if (target.dataset.tooltip) return target.dataset.tooltip;
    const title = target.getAttribute('title');
    if (title) {
      // The title moves to our own attribute: the browser would draw its own bubble.
      target.dataset.tooltip = title;
      if (!target.hasAttribute('aria-label')) target.setAttribute('aria-label', title);
      target.removeAttribute('title');
      return title;
    }
    if (target.classList.contains('top-bar-heading-button')) return HEADING_LABEL;
    if (target.classList.contains('top-bar-item')) return labelOfTopBarItem(target);
    return null;
  }

  function labelOfTopBarItem(target) {
    const buttons = [...host.querySelectorAll('.top-bar-item')];
    const items = builder()
      .flatMap((group) => group.items)
      .filter((item) => !item.selector && item.onRun);
    const item = items[buttons.indexOf(target)];
    if (item === undefined) return null;
    const label = item.label ?? LABELS[item.key] ?? null;
    if (label !== null && !target.hasAttribute('aria-label')) target.setAttribute('aria-label', label);
    return label;
  }

  function place(target) {
    const rect = target.getBoundingClientRect();
    bubble.hidden = false;
    const { width, height } = bubble.getBoundingClientRect();
    const left = Math.min(Math.max(rect.left + rect.width / 2 - width / 2, 4), window.innerWidth - width - 4);
    const below = rect.bottom + GAP + height <= window.innerHeight;
    bubble.style.left = `${left}px`;
    bubble.style.top = `${below ? rect.bottom + GAP : rect.top - GAP - height}px`;
  }

  function show(target) {
    const text = textOf(target);
    if (text === null) return;
    current = target;
    bubble.textContent = text;
    target.setAttribute('aria-describedby', bubble.id);
    place(target);
  }

  function hide() {
    window.clearTimeout(timer);
    timer = 0;
    bubble.hidden = true;
    current?.removeAttribute('aria-describedby');
    current = null;
  }

  function targetOf(event) {
    const target = event.target instanceof Element ? event.target.closest(TARGETS) : null;
    return target !== null && host.contains(target) ? target : null;
  }

  const onPointerOver = (event) => {
    const target = targetOf(event);
    if (target === null || target === current) return;
    hide();
    timer = window.setTimeout(() => show(target), SHOW_DELAY_MS);
  };
  const onPointerOut = (event) => {
    const target = targetOf(event);
    if (target !== null && !target.contains(event.relatedTarget)) hide();
  };
  const onFocusIn = (event) => {
    const target = targetOf(event);
    if (target !== null) {
      hide();
      show(target);
    }
  };

  // The accessible names do not wait for a hover: the buttons are named when
  // the bar is drawn, and again when it is drawn again.
  const nameButtons = () => {
    for (const button of host.querySelectorAll('.top-bar-item')) textOf(button);
  };
  const observer = new MutationObserver(nameButtons);
  observer.observe(host, { childList: true, subtree: true });
  nameButtons();

  host.addEventListener('pointerover', onPointerOver);
  host.addEventListener('pointerout', onPointerOut);
  host.addEventListener('pointerdown', hide, true);
  host.addEventListener('focusin', onFocusIn);
  host.addEventListener('focusout', hide);
  host.addEventListener('keydown', hide, true);
  window.addEventListener('scroll', hide, true);

  return () => {
    observer.disconnect();
    hide();
    host.removeEventListener('pointerover', onPointerOver);
    host.removeEventListener('pointerout', onPointerOut);
    host.removeEventListener('pointerdown', hide, true);
    host.removeEventListener('focusin', onFocusIn);
    host.removeEventListener('focusout', hide);
    host.removeEventListener('keydown', hide, true);
    window.removeEventListener('scroll', hide, true);
    bubble.remove();
  };
}
