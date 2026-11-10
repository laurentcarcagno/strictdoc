// On a narrow screen the page shows the content or the menu, and the button
// of the menu (#layout-menu-toggle) switches between them (responsive.css).
// The sidebar is always expanded on a narrow screen; the choice to collapse it
// (nav.js) comes back above the breakpoint.
(() => {
  const NAV_KEY = 'sdoc-nav-collapsed';
  const layout = document.getElementById('layout');
  const button = document.getElementById('layout-menu-toggle');
  if (layout === null || button === null) {
    return;
  }
  const query = window.matchMedia('(max-width: 768px)');
  const root = document.documentElement;
  // The sdocT function follows the language of the page (features/i18n).
  const sdocT = window.sdocT || ((text) => text);
  // A page without a sidebar has no menu to open.
  const hasMenu = layout.querySelector('.layout_nav > *') !== null;

  function setOpen(open) {
    if (open) {
      layout.dataset.menu = 'open';
    } else {
      delete layout.dataset.menu;
    }
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
    button.title = open ? sdocT('Close the menu') : sdocT('Open the menu');
  }

  function storedCollapsed() {
    try {
      return localStorage.getItem(NAV_KEY) === '1';
    } catch (error) {
      return false;
    }
  }

  function apply() {
    if (query.matches) {
      delete root.dataset.nav;
      button.hidden = !hasMenu;
      setOpen(false);
      return;
    }
    if (storedCollapsed()) {
      root.dataset.nav = 'collapsed';
    }
    button.hidden = true;
    setOpen(false);
  }

  button.addEventListener('click', () => {
    setOpen(layout.dataset.menu !== 'open');
  });
  query.addEventListener('change', apply);
  apply();
})();
