// The project tree of the sidebar (see sidebar.py and
// templates/features/project_index/sidebar_tree.jinja.html).
//
// - It asks the server for the tree and shows it under the project picker. The
//   actions that change the tree replace it in place (Turbo streams that target
//   #frame_project_tree), so everything here works on a tree that can be
//   replaced at any time.
// - The management of the tree is in the menu of a right click on a node (or
//   its "..." button): the menus are <template>s of the fragment, the script
//   shows one of them, with the path or the document of the node filled in.
//   The items are Turbo links like the ones of the former actions menu.
// - The current document is marked, the folders that were closed stay closed,
//   and the scroll position is kept from one page to the next.
(() => {
  const container = document.getElementById('frame_project_tree');
  if (!container) return;

  const FOLDERS_KEY = 'sdoc-tree-closed-folders';
  const SCROLL_KEY = 'sdoc-tree-scroll';
  const FRAGMENTS_KEY = 'projectTreeFragmentVisibility';
  const scripts = JSON.parse(container.dataset.scripts || '{}');

  // ---- what the forms of the menu need on every screen ----

  function loadScript(src) {
    return new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = src;
      script.onload = resolve;
      script.onerror = resolve;
      document.head.append(script);
    });
  }

  // The screens of the project load Turbo and the scripts of the forms (modal,
  // editable fields) themselves, most of them; the ones that do not get them
  // here.
  async function ensureScripts() {
    if (!window.Turbo && scripts.turbo && !document.querySelector('script[src*="turbo.min.js"]')) {
      try {
        await import(scripts.turbo);
      } catch (error) {
        // The menu then opens its pages as plain pages.
      }
    }
    for (const name of ['modal', 'editable', 'guard']) {
      const source = scripts[name];
      const file = source ? source.split('/').pop() : '';
      if (source && !document.querySelector(`script[src*="${file}"]`)) {
        await loadScript(source);
      }
    }
  }

  // ---- reading and keeping the state ----

  function readClosed() {
    try {
      return new Set(JSON.parse(localStorage.getItem(FOLDERS_KEY) || '[]'));
    } catch (error) {
      return new Set();
    }
  }

  function writeClosed(closed) {
    try {
      localStorage.setItem(FOLDERS_KEY, JSON.stringify([...closed]));
    } catch (error) {
      // No storage: the folders are open again on the next page.
    }
  }

  function fragmentsShown() {
    try {
      return sessionStorage.getItem(FRAGMENTS_KEY) === 'show';
    } catch (error) {
      return false;
    }
  }

  // The name of a document without the suffix of its view (-TABLE, -TRACE...).
  function baseName(pathname) {
    return decodeURIComponent(pathname)
      .replace(/\.html$/, '')
      .replace(/-(DEEP-TRACE|TRACE|TABLE|PDF)$/, '');
  }

  function afterRender() {
    container.querySelectorAll('summary[data-tree-node="folder"]').forEach((row) => row.setAttribute('draggable', 'true'));
    const closed = readClosed();
    container.querySelectorAll('.sdoc-tree__folder').forEach((folder) => {
      folder.open = !closed.has(folder.dataset.path);
    });
    // The included documents (fragments) are hidden unless the project page
    // switch shows them; project_tree.js keeps that switch.
    if (!fragmentsShown()) {
      container.querySelectorAll('[included-document]').forEach((row) => {
        row.style.display = 'none';
      });
    }
    const here = baseName(window.location.pathname);
    // The links keep the view on screen (table, traceability...).
    const view = window.location.pathname.match(
      /(-DEEP-TRACE|-TRACE|-TABLE|-PDF)\.html$/
    );
    if (view) {
      container.querySelectorAll('.sdoc-tree__file').forEach((file) => {
        const target = new URL(file.href, window.location.href);
        target.pathname = target.pathname.replace(
          /\.html$/,
          `${view[1]}.html`
        );
        file.setAttribute('href', target.pathname);
      });
    }
    container.querySelectorAll('.sdoc-tree__file').forEach((file) => {
      const mine = baseName(new URL(file.href, window.location.href).pathname);
      const current = mine === here;
      file.classList.toggle('is-current', current);
      if (current) {
        file.setAttribute('aria-current', 'page');
        let parent = file.parentElement;
        while (parent && parent !== container) {
          if (parent.tagName === 'DETAILS') parent.open = true;
          parent = parent.parentElement;
        }
      } else {
        file.removeAttribute('aria-current');
      }
    });
    try {
      const top = Number(sessionStorage.getItem(SCROLL_KEY) || 0);
      if (top) container.scrollTop = top;
    } catch (error) {
      // No storage.
    }
    // The document on screen has to be in view: if the remembered position
    // hides it (a link in the text led here), it goes to the middle.
    const current = container.querySelector('.sdoc-tree__file.is-current');
    if (current) {
      const box = container.getBoundingClientRect();
      const item = current.getBoundingClientRect();
      if (item.top < box.top || item.bottom > box.bottom) {
        const center = () => {
          const b = container.getBoundingClientRect();
          const i = current.getBoundingClientRect();
          container.scrollTop += i.top + i.height / 2 - (b.top + b.height / 2);
        };
        center();
        saveScroll();
        // Once the layout has settled.
        requestAnimationFrame(() => {
          center();
          saveScroll();
        });
      }
    }
  }

  // The position is kept when the user leaves by a link of the tree (and
  // when the document on screen is brought to the middle), not at every
  // scroll.
  function saveScroll() {
    try {
      sessionStorage.setItem(SCROLL_KEY, String(container.scrollTop));
    } catch (error) {
      // No storage.
    }
  }

  container.addEventListener('click', (event) => {
    if (event.target.closest('.sdoc-tree__file')) saveScroll();
  });

  // A folder that is closed or opened is remembered by its path.
  container.addEventListener(
    'toggle',
    (event) => {
      const folder = event.target;
      if (!folder.classList || !folder.classList.contains('sdoc-tree__folder')) return;
      const closed = readClosed();
      if (folder.open) closed.delete(folder.dataset.path);
      else closed.add(folder.dataset.path);
      writeClosed(closed);
    },
    true
  );

  // ---- loading and replacing the tree ----

  async function load() {
    try {
      const response = await fetch(container.dataset.src, { credentials: 'same-origin' });
      if (!response.ok) throw new Error(String(response.status));
      container.innerHTML = await response.text();
    } catch (error) {
      container.textContent = '';
    }
  }

  // The tree is replaced by Turbo streams (a document or a folder was created,
  // a file imported): mark it again each time.
  new MutationObserver(() => {
    if (container.querySelector('[data-tree-root]') && !container.dataset.rendered) {
      container.dataset.rendered = '1';
      afterRender();
    }
    if (!container.querySelector('[data-tree-root]')) {
      delete container.dataset.rendered;
    }
  }).observe(container, { childList: true });

  // A message under the project name (a move that was refused...).
  function showNotice(text) {
    container.parentElement.querySelectorAll('.sdoc-tree__notice').forEach((old) => old.remove());
    const notice = document.createElement('div');
    notice.className = 'sdoc-tree__notice';
    notice.setAttribute('role', 'alert');
    notice.dataset.testid = 'tree-notice';
    notice.textContent = text;
    notice.addEventListener('click', () => notice.remove());
    container.before(notice);
    setTimeout(() => notice.remove(), 10000);
  }

  // The tree again, after a change. When a path moved (from -> to) and the
  // page on screen is that document, or in that folder, the page follows it.
  async function reloadAfterMove(from, to) {
    const current = container.querySelector('.sdoc-tree__file.is-current');
    const here = current ? current.dataset.relPath : '';
    let next = '';
    if (from && to && here) {
      if (here === from) next = to;
      else if (here.startsWith(`${from}/`)) next = to + here.slice(from.length);
    }
    await load();
    if (next) {
      const moved = container.querySelector(`.sdoc-tree__file[data-rel-path="${CSS.escape(next)}"]`);
      if (moved) window.location.href = moved.getAttribute('href');
    }
  }

  // A change that the tree shows (the title of a document, a renamed folder)
  // asks for the tree again by adding a marker to #sdoc_tree_refresh.
  const refresh = document.getElementById('sdoc_tree_refresh');
  if (refresh) {
    new MutationObserver(() => {
      const marker = refresh.firstElementChild;
      if (!marker) return;
      const { from, to } = marker.dataset;
      refresh.replaceChildren();
      reloadAfterMove(from, to);
    }).observe(refresh, { childList: true });
  }

  // ---- drag and drop: a document or a folder to another folder ----

  const MOVE_URL = '/actions/project_index/move';
  let dragged = null;

  function mayMove() {
    const role = document.documentElement.dataset.role;
    return !role || role === 'author' || role === 'administrator';
  }

  function parentOf(path) {
    const at = path.lastIndexOf('/');
    return at < 0 ? '' : path.slice(0, at);
  }

  function dropTarget(event) {
    return event.target.closest('[data-tree-node="folder"], [data-tree-node="root"]');
  }

  function destinationOf(target) {
    return target.dataset.treeNode === 'root' ? '' : target.dataset.path;
  }

  function mayDrop(target) {
    if (!dragged || !target) return false;
    const destination = destinationOf(target);
    if (destination === parentOf(dragged.source)) return false;
    if (dragged.kind === 'folder') {
      if (destination === dragged.source || destination.startsWith(`${dragged.source}/`)) return false;
    }
    return true;
  }

  function clearDropTargets() {
    container.querySelectorAll('.is-drop-target').forEach((row) => row.classList.remove('is-drop-target'));
  }

  container.addEventListener('dragstart', (event) => {
    const node = event.target.closest('[data-tree-node="document"], [data-tree-node="folder"]');
    if (!node || !mayMove()) {
      event.preventDefault();
      return;
    }
    const kind = node.dataset.treeNode;
    dragged = { kind, source: kind === 'document' ? node.dataset.relPath : node.dataset.path };
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', dragged.source);
    closeMenu();
  });

  let openTimer = null;
  container.addEventListener('dragover', (event) => {
    const target = dropTarget(event);
    if (!mayDrop(target)) {
      clearDropTargets();
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    if (!target.classList.contains('is-drop-target')) {
      clearDropTargets();
      target.classList.add('is-drop-target');
      clearTimeout(openTimer);
      const folder = target.closest('details');
      if (folder && !folder.open) openTimer = setTimeout(() => { folder.open = true; }, 700);
    }
  });

  container.addEventListener('dragleave', (event) => {
    if (!container.contains(event.relatedTarget)) clearDropTargets();
  });

  container.addEventListener('drop', async (event) => {
    const target = dropTarget(event);
    const moving = dragged;
    clearDropTargets();
    clearTimeout(openTimer);
    if (!moving || !mayDrop(target)) return;
    event.preventDefault();
    try {
      const response = await fetch(MOVE_URL, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ source: moving.source, destination: destinationOf(target) }),
      });
      let answer = {};
      try {
        answer = await response.json();
      } catch (error) {
        // Not JSON: the message below tells the status.
      }
      if (!response.ok) {
        showNotice(answer.error || `The move was refused (${response.status}).`);
        return;
      }
      await reloadAfterMove(answer.from, answer.to);
    } catch (error) {
      showNotice('The move failed: the server does not answer.');
    }
  });

  container.addEventListener('dragend', () => {
    dragged = null;
    clearDropTargets();
    clearTimeout(openTimer);
  });

  // ---- the menu of the right click ----

  const menu = document.createElement('turbo-frame');
  menu.id = 'sdoc_tree_menu';
  menu.className = 'sdoc-tree-menu';
  menu.setAttribute('role', 'menu');
  menu.hidden = true;
  menu.dataset.testid = 'tree-context-menu';
  document.body.append(menu);

  function closeMenu() {
    menu.hidden = true;
    menu.replaceChildren();
  }

  function fill(item, node) {
    const template = item.dataset.href;
    if (!template) return;
    const link = node.querySelector('a[data-tree-node]') || node;
    item.setAttribute(
      'href',
      template
        .replace('{path}', encodeURIComponent(node.dataset.path || ''))
        .replace('{mid}', encodeURIComponent(node.dataset.documentMid || ''))
        .replace('{href}', link.getAttribute('href') || '#')
    );
  }

  function openMenu(node, x, y) {
    const type = node.dataset.treeNode;
    const template = container.querySelector(`template[data-tree-menu="${type}"]`);
    if (!template) return;
    menu.replaceChildren(template.content.cloneNode(true));
    const holder = node.closest('.sdoc-tree__row') || node;
    menu.querySelectorAll('[data-href]').forEach((item) => fill(item, holder.contains(node) ? node : holder));
    menu.hidden = false;
    // A role that may do nothing here (the CSS of the roles hides the items)
    // gets no empty box.
    const allowed = [...menu.querySelectorAll('.sdoc-tree-menu__item')].some(
      (item) => item.offsetParent !== null
    );
    if (!allowed) {
      closeMenu();
      return;
    }
    // Inside the window, whatever the place of the click.
    const box = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(4, Math.min(x, window.innerWidth - box.width - 4))}px`;
    menu.style.top = `${Math.max(4, Math.min(y, window.innerHeight - box.height - 4))}px`;
    const first = menu.querySelector('.sdoc-tree-menu__item');
    if (first) first.focus({ preventScroll: true });
  }

  container.addEventListener('contextmenu', (event) => {
    const node = event.target.closest('[data-tree-node]');
    if (!node) return;
    event.preventDefault();
    openMenu(node, event.clientX, event.clientY);
  });

  // The "..." button of a row opens the same menu (touch, or no right click).
  container.addEventListener('click', (event) => {
    const more = event.target.closest('.sdoc-tree__more');
    if (!more) return;
    event.preventDefault();
    event.stopPropagation();
    const row = more.closest('.sdoc-tree__row');
    const node = row.matches('[data-tree-node]') ? row : row.querySelector('[data-tree-node]');
    const box = more.getBoundingClientRect();
    openMenu(node, box.right, box.bottom);
  });

  document.addEventListener(
    'click',
    (event) => {
      if (menu.hidden || menu.contains(event.target)) return;
      closeMenu();
    },
    true
  );
  // A choice in the menu closes it once Turbo has taken the link.
  menu.addEventListener('click', (event) => {
    if (event.target.closest('.sdoc-tree-menu__item')) setTimeout(closeMenu, 0);
  });
  document.addEventListener('keydown', (event) => {
    if (menu.hidden) return;
    const items = [...menu.querySelectorAll('.sdoc-tree-menu__item')].filter(
      (item) => item.offsetParent !== null
    );
    const at = items.indexOf(document.activeElement);
    if (event.key === 'Escape') {
      closeMenu();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      items[(at + 1) % items.length]?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      items[(at - 1 + items.length) % items.length]?.focus();
    }
  });
  window.addEventListener('resize', closeMenu);
  window.addEventListener('blur', closeMenu);
  container.addEventListener('scroll', closeMenu);

  // ---- go ----

  ensureScripts().then(load);
})();
