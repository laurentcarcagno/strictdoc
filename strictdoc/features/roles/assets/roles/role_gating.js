// Sets data-role on <html> from /whoami, so that role_gating.css can hide what
// the role cannot do, and shows the user in the footer of the sidebar.
// The server enforces the roles; this only avoids showing dead buttons.
(() => {
  const KEY = 'sdoc-whoami';
  const root = document.documentElement;
  let observing = false;

  // A reader that a document names as a reviewer may comment on it: the
  // Comment buttons of that document say who its reviewers are.
  function markCommenters() {
    const user = (root.dataset.user || '').toLowerCase();
    document.querySelectorAll('[data-reviewers]').forEach((button) => {
      const names = button.dataset.reviewers.split(',');
      if (user && names.includes(user)) button.dataset.canComment = '1';
    });
  }

  // @relation(SDOC-SRS-212, scope=range_start)
  // The actions that the role cannot do stay on the page, disabled, and say
  // which role they need (role_gating.css dims them). A click on them does
  // nothing. The server refuses them whatever the page shows.
  const sdocT = window.sdocT || ((text) => text);
  const RANK = { reader: 0, reviewer: 1, author: 2, administrator: 3 };
  const REASONS = {
    reviewer: sdocT('Needs the reviewer role'),
    author: sdocT('Needs the author role'),
    administrator: sdocT('Needs the administrator role'),
  };
  const GATED = [
    [
      'author',
      [
        '[data-testid^="node-edit-action"]',
        '[data-testid^="node-delete-action"]',
        '[data-testid^="node-move-action"]',
        '[data-testid^="node-clone-action"]',
        '[data-testid^="node-add-"]',
        '[data-testid="tree-add-document-action"]',
        '[data-testid="tree-add-folder-action"]',
        '[data-testid="tree-import-docx-action"]',
        '[data-testid="table-toolbar-edit-btn"]',
        '.content-view__add_new_row-TR',
      ].join(', '),
    ],
    [
      'administrator',
      [
        '[data-testid^="document-edit-config-action"]',
        '[data-testid="document-edit-grammar-action"]',
        '[data-testid="document-delete-action"]',
        '[data-testid="project-edit-title-action"]',
        '[data-testid="tree-import-reqif-action"]',
      ].join(', '),
    ],
  ];

  function disable(element, reason, required) {
    if (element.dataset.roleDisabled === required) return;
    if (element.dataset.roleDisabled === undefined) {
      element.dataset.roleTitle = element.getAttribute('title') || '';
    }
    element.dataset.roleDisabled = required;
    element.setAttribute('aria-disabled', 'true');
    element.setAttribute('title', reason);
  }

  function enable(element) {
    const title = element.dataset.roleTitle;
    if (title) {
      element.setAttribute('title', title);
    } else {
      element.removeAttribute('title');
    }
    element.removeAttribute('aria-disabled');
    delete element.dataset.roleDisabled;
    delete element.dataset.roleTitle;
  }

  function markDisabled() {
    const rank = RANK[root.dataset.role];
    if (rank === undefined) return;
    const wanted = new Map();
    GATED.forEach(([required, selector]) => {
      if (rank >= RANK[required]) return;
      document.querySelectorAll(selector).forEach((element) => {
        wanted.set(element, [REASONS[required], required]);
      });
    });
    document.querySelectorAll('[data-requires-role]').forEach((element) => {
      const required = element.dataset.requiresRole;
      if (RANK[required] !== undefined && rank < RANK[required]) {
        wanted.set(element, [REASONS[required], required]);
      }
    });
    // A reader comments only on the documents that name them as reviewer.
    if (root.dataset.role === 'reader') {
      document
        .querySelectorAll('[data-testid="node-comment-action"]:not([data-can-comment])')
        .forEach((element) => {
          wanted.set(element, [
            sdocT('Only the reviewers of this document can comment'),
            'reviewer',
          ]);
        });
    }
    document.querySelectorAll('[data-role-disabled]').forEach((element) => {
      if (!wanted.has(element)) enable(element);
    });
    wanted.forEach(([reason, required], element) => {
      disable(element, reason, required);
    });
  }

  document.addEventListener(
    'click',
    (event) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target && target.closest('[data-role-disabled]')) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true,
  );
  // @relation(SDOC-SRS-212, scope=range_end)

  function apply(who) {
    root.dataset.role = who.role || 'none';
    root.dataset.user = who.user || '';
    markCommenters();
    markDisabled();
    if (!observing) {
      observing = true;
      let pending = false;
      new MutationObserver(() => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => {
          pending = false;
          markCommenters();
          markDisabled();
        });
      }).observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  // The user footer of the sidebar (_shared/nav.jinja.html): initials, name,
  // role. The logout is an item of the sidebar.
  function showUser(who) {
    // The texts follow the language of the page (features/i18n).
    const sdocT = window.sdocT || ((text) => text);
    const ROLES = {
      reader: sdocT('reader'),
      reviewer: sdocT('reviewer'),
      author: sdocT('author'),
      administrator: sdocT('administrator'),
    };
    const roleName = ROLES[who.role] || sdocT('no role');
    const footer = document.getElementById('nav-user');
    if (!footer || footer.dataset.filled) return;
    footer.dataset.filled = '1';

    const name = who.user || '';
    const initials = name
      .split(/[\s._-]+/)
      .filter(Boolean)
      .map((part) => part[0])
      .join('')
      .slice(0, 2) || '?';

    const avatar = document.createElement('span');
    avatar.className = 'nav__avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = initials;

    const identity = document.createElement('span');
    identity.className = 'nav__identity';
    identity.dataset.testid = 'user-badge';
    const userName = document.createElement('span');
    userName.className = 'nav__user_name';
    userName.textContent = name;
    const userRole = document.createElement('span');
    userRole.className = 'nav__user_role';
    userRole.textContent = roleName;
    identity.append(userName, userRole);

    footer.title = `${name} (${roleName})`;
    footer.append(avatar, identity);
    footer.hidden = false;
  }

  try {
    const cached = sessionStorage.getItem(KEY);
    if (cached) apply(JSON.parse(cached));
  } catch (error) {
    // No storage: the answer of /whoami is used.
  }

  fetch('/whoami', { credentials: 'same-origin' })
    .then((response) => (response.ok ? response.json() : null))
    .then((who) => {
      if (!who) return;
      try {
        sessionStorage.setItem(KEY, JSON.stringify(who));
      } catch (error) {
        // Ignored.
      }
      apply(who);
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => showUser(who));
      } else {
        showUser(who);
      }
    });
})();
