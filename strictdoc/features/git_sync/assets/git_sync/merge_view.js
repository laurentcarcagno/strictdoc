// The conflict view, in the modal: one choice per conflict (the server, the
// local project, both, or a text typed by hand), then the document is
// written. The modal arrives as a Turbo stream, so everything is delegated
// to the document, and a dialog is set up when it appears. Keys: n and p go
// to the next and the previous conflict, Escape closes the editor of the
// conflict that is open (the modal closes with the next Escape).
(() => {
  const sdocT = window.sdocT || ((text) => text);
  const label = {
    server: 'the server',
    local: 'the local project',
    both: 'both',
    edit: 'edited by hand',
  };

  function setup(dialog) {
    if (dialog.dataset.ready) return;
    dialog.dataset.ready = '1';
    const texts = JSON.parse(dialog.querySelector('#gs-data').textContent || '{}');
    const file = dialog.dataset.file;
    const rows = [...dialog.querySelectorAll('.gs-row--conflict')];
    const finish = document.getElementById('gs-finish');
    const counter = dialog.querySelector('#gs-resolved');
    const errorBox = dialog.querySelector('#gs-error');
    const chosen = {}; // region -> {choice, text}
    let current = -1;

    function refresh() {
      const solved = rows.filter((row) => chosen[row.dataset.region]).length;
      counter.textContent = String(solved);
      finish.disabled = solved !== rows.length;
    }

    function show(row) {
      const answer = chosen[row.dataset.region];
      row.classList.toggle('is-solved', Boolean(answer));
      row.querySelectorAll('[data-choice]').forEach((button) => {
        button.setAttribute(
          'aria-pressed',
          String(Boolean(answer) && button.dataset.choice === answer.choice),
        );
      });
      row.querySelector('[data-state]').textContent = answer
        ? `- ${sdocT('kept')}: ${sdocT(label[answer.choice])}`
        : '';
    }

    function choose(row, choice) {
      const region = row.dataset.region;
      const area = row.querySelector('textarea');
      if (choice === 'edit') {
        row.querySelector('.gs-edit').hidden = false;
        if (!area.value) area.value = (chosen[region] && chosen[region].text) || texts[region].local;
        area.focus();
        chosen[region] = { choice: 'edit', text: area.value };
      } else {
        chosen[region] = { choice, text: texts[region][choice] };
        area.value = texts[region][choice];
      }
      show(row);
      refresh();
    }

    function goTo(index, scroll = true) {
      if (!rows.length) return;
      current = (index + rows.length) % rows.length;
      rows.forEach((row, at) => row.classList.toggle('is-current', at === current));
      if (scroll) rows[current].scrollIntoView({ block: 'center', behavior: 'smooth' });
    }

    rows.forEach((row) => {
      row.querySelectorAll('[data-choice]').forEach((button) => {
        button.addEventListener('click', () => {
          goTo(rows.indexOf(row), false);
          choose(row, button.dataset.choice);
        });
      });
      row.querySelector('textarea').addEventListener('input', (event) => {
        chosen[row.dataset.region] = { choice: 'edit', text: event.target.value };
        show(row);
        refresh();
      });
    });

    dialog.querySelector('#gs-next').addEventListener('click', () => goTo(current + 1));
    dialog.querySelector('#gs-prev').addEventListener('click', () => goTo(current - 1));
    dialog.addEventListener('keydown', (event) => {
      if (event.target.closest('textarea, select, input')) {
        if (event.key === 'Escape') {
          event.stopPropagation();
          event.target.closest('.gs-row').querySelector('.gs-edit').hidden = true;
        }
        return;
      }
      if (event.key === 'n') goTo(current + 1);
      if (event.key === 'p') goTo(current - 1);
    });

    const select = dialog.querySelector('#gs-file');
    if (select) select.addEventListener('change', () => load(`/actions/git/sync_conflicts?file=${encodeURIComponent(select.value)}`));

    finish.addEventListener('click', async () => {
      errorBox.hidden = true;
      const payload = {};
      rows.forEach((row) => { payload[row.dataset.region] = chosen[row.dataset.region].text; });
      finish.disabled = true;
      try {
        const response = await fetch('/actions/git/sync/resolve', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({ file, texts: JSON.stringify(payload) }),
        });
        const answer = await response.json().catch(() => ({}));
        if (!response.ok) {
          errorBox.textContent = answer.error || String(response.status);
          errorBox.hidden = false;
          finish.disabled = false;
          return;
        }
        await load(answer.next);
      } catch (error) {
        errorBox.textContent = sdocT('The server does not answer.');
        errorBox.hidden = false;
        finish.disabled = false;
      }
    });

    rows.forEach(show);
    refresh();
    goTo(0, false);
  }

  // The next dialog: a stream that replaces the content of the modal.
  async function load(url) {
    const response = await fetch(url, {
      credentials: 'same-origin',
      headers: { Accept: 'text/vnd.turbo-stream.html' },
    });
    const text = await response.text();
    if (window.Turbo && window.Turbo.renderStreamMessage) window.Turbo.renderStreamMessage(text);
  }

  function scan() {
    document.querySelectorAll('.gs-dialog--merge').forEach(setup);
  }

  new MutationObserver(scan).observe(document.documentElement, { childList: true, subtree: true });
  scan();
})();
