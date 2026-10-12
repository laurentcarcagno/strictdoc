// Delegated listeners cover every modal - nothing is registered or needs
// cleanup per modal instance:
// - the cancel buttons (footer and the X of the header) and a click on the
//   backdrop close the modal; so does Escape;
// - a template-based static modal opens from its trigger;
// - an open modal keeps the focus: it moves to its first field or button,
//   Tab stays inside, and the focus goes back to the trigger on close.

(() => {

  const SEL_MODAL = '[data-js-modal]';
  const SEL_CANCEL = '[data-js-modal-cancel-button]';
  const SEL_TRIGGER = '[data-js-modal-template-trigger]';
  const SEL_FOCUSABLE = [
    'a[href]', 'button:not([disabled])', 'input:not([disabled])',
    'select:not([disabled])', 'textarea:not([disabled])',
    '[contenteditable="true"]', '[tabindex]:not([tabindex="-1"])',
  ].join(',');

  // The element that had the focus when a modal opened.
  let opener = null;

  function close(modal) {
    modal.remove();
    if (opener && document.contains(opener)) {
      opener.focus();
    }
    opener = null;
  }

  function focusables(modal) {
    return Array.from(modal.querySelectorAll(SEL_FOCUSABLE)).filter(
      (element) => element.offsetParent !== null,
    );
  }

  // The first interactive element is the X of the header: focusing it does
  // not open the suggestions of an autocompletable field.
  function focusFirst(modal) {
    if (modal.contains(document.activeElement)) return;
    const first = focusables(modal)[0];
    if (first) first.focus({ preventScroll: true });
  }

  document.addEventListener('click', (event) => {
    const btn = event.target.closest?.(SEL_CANCEL);
    if (!btn) return;
    const modal = btn.closest(SEL_MODAL);
    if (!modal) return;
    event.preventDefault();
    close(modal);
  });

  // A click on the backdrop itself, not on the dialog.
  document.addEventListener('click', (event) => {
    if (event.target?.tagName !== 'SDOC-BACKDROP') return;
    const modal = event.target.closest(SEL_MODAL);
    if (modal) close(modal);
  });

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest?.(SEL_TRIGGER);
    if (!trigger) return;
    const template = document.getElementById(
      trigger.dataset.jsModalTemplateTrigger,
    );
    if (!(template instanceof HTMLTemplateElement)) return;
    document.getElementById('modal').innerHTML = template.innerHTML;
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      document.querySelectorAll(SEL_MODAL).forEach((modal) => close(modal));
      return;
    }
    if (event.key !== 'Tab') return;
    const modal = document.querySelector(SEL_MODAL);
    if (!modal) return;
    const items = focusables(modal);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (!modal.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  // A modal arrives in the page (Turbo stream or template): take the focus.
  new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (!(node instanceof Element)) continue;
        const modal = node.matches(SEL_MODAL) ? node : node.querySelector?.(SEL_MODAL);
        if (!modal) continue;
        if (!opener) opener = document.activeElement;
        requestAnimationFrame(() => focusFirst(modal));
        return;
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });

})();
