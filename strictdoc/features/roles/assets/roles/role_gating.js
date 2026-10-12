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

  function apply(who) {
    root.dataset.role = who.role || 'none';
    root.dataset.user = who.user || '';
    markCommenters();
    if (!observing) {
      observing = true;
      let pending = false;
      new MutationObserver(() => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => {
          pending = false;
          markCommenters();
        });
      }).observe(document.documentElement, { childList: true, subtree: true });
    }
  }

  // The user footer of the sidebar (_shared/nav.jinja.html): initials, name,
  // role. The logout is an item of the sidebar.
  function showUser(who) {
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
    userRole.textContent = who.role || 'no role';
    identity.append(userName, userRole);

    footer.title = `${name} (${who.role || 'no role'})`;
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
