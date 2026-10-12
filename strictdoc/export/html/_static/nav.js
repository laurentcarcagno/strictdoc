// The sidebar (_shared/nav.jinja.html) collapses to its icons. The choice is
// kept in the browser; it is applied before the page is painted because this
// script runs where the sidebar is parsed.
(() => {
  const KEY = 'sdoc-nav-collapsed';
  const root = document.documentElement;
  const toggle = document.getElementById('nav-toggle');
  // The texts follow the language of the page (features/i18n).
  const sdocT = window.sdocT || ((text) => text);

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
      toggle.title = collapsed
        ? sdocT('Expand the sidebar')
        : sdocT('Collapse the sidebar');
    }
  }

  apply(read());

  if (toggle) {
    toggle.addEventListener('click', () => {
      const collapsed = root.dataset.nav !== 'collapsed';
      apply(collapsed);
      write(collapsed);
    });
  }

  // The project picker of a server with several projects: the projects of
  // the user, the current one selected; choosing one opens it.
  const picker = document.querySelector('[data-project-picker]');
  if (picker) {
    fetch(picker.dataset.src, { credentials: 'same-origin' })
      .then((response) => (response.ok ? response.json() : []))
      .then((projects) => {
        if (projects.length === 0) return;
        if (!projects.some((project) => project.current)) {
          const choose = document.createElement('option');
          choose.textContent = sdocT('Choose a project');
          choose.value = '';
          choose.selected = true;
          choose.disabled = true;
          picker.append(choose);
        }
        projects.forEach((project) => {
          const option = document.createElement('option');
          option.value = project.url;
          option.textContent = project.title;
          option.selected = project.current;
          picker.append(option);
        });
        picker.addEventListener('change', () => {
          if (picker.value) window.location.assign(picker.value);
        });
        picker.closest('[data-project-picker-box]').hidden = false;
      })
      .catch(() => {
        // No list: the picker stays hidden, the Projects page still works.
      });
  }
})();
