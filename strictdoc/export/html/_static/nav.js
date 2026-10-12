// The sidebar (_shared/nav.jinja.html) collapses to its icons. The choice is
// kept in the browser; it is applied before the page is painted because this
// script runs where the sidebar is parsed.
(() => {
  const KEY = 'sdoc-nav-collapsed';
  const root = document.documentElement;
  const toggle = document.getElementById('nav-toggle');

  function read() {
    try {
      return localStorage.getItem(KEY) === '1';
    } catch (error) {
      return false;
    }
  }

  function write(collapsed) {
    try {
      localStorage.setItem(KEY, collapsed ? '1' : '0');
    } catch (error) {
      // No storage: the choice lasts until the next page.
    }
  }

  function apply(collapsed) {
    if (collapsed) {
      root.dataset.nav = 'collapsed';
    } else {
      delete root.dataset.nav;
    }
    if (toggle) {
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      toggle.title = collapsed ? 'Expand the sidebar' : 'Collapse the sidebar';
    }
  }

  apply(read());

  // In a project of a registry, the portal is the parent host:
  // <slug>.<root> gives <root>.
  document.querySelectorAll('[data-portal-link]').forEach((link) => {
    const parts = window.location.hostname.split('.');
    if (parts.length < 2) return;
    const port = window.location.port ? `:${window.location.port}` : '';
    link.href = `${window.location.protocol}//${parts.slice(1).join('.')}${port}/`;
  });

  if (toggle) {
    toggle.addEventListener('click', () => {
      const collapsed = root.dataset.nav !== 'collapsed';
      apply(collapsed);
      write(collapsed);
    });
  }
})();
