// Sets data-role on <html> from /whoami, so that role_gating.css can hide what
// the role cannot do, and shows the user name and role in the header.
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

  function showBadge(who) {
    if (document.querySelector('[data-testid="user-badge"]')) return;
    const handler = document.getElementById('header-actions');
    if (!handler || !handler.parentElement) return;
    const badge = document.createElement('span');
    badge.className = 'sdoc-user-badge';
    badge.dataset.testid = 'user-badge';
    badge.textContent = `${who.user} (${who.role || 'no role'})`;
    handler.parentElement.insertBefore(badge, handler);
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
        document.addEventListener('DOMContentLoaded', () => showBadge(who));
      } else {
        showBadge(who);
      }
    });
})();
