// The view of the conflicts: one choice per conflict (the server, the local
// project, both, or a text typed by hand), then the document is written.
// Keys: n and p go to the next and the previous conflict, Escape closes the
// editor of the conflict that is open.
(() => {
  const dataElement = document.getElementById('gs-data');
  if (!dataElement) return;
  const texts = JSON.parse(dataElement.textContent || '{}');
  const file = document.body.dataset.file;
  const rows = [...document.querySelectorAll('.gs-row--conflict')];
  const finish = document.getElementById('gs-finish');
  const counter = document.getElementById('gs-resolved');
  const errorBox = document.getElementById('gs-error');
  const sdocT = window.sdocT || ((text) => text);
  const chosen = {}; // region -> {choice, text}
  let current = -1;

  const label = {
    server: 'the server',
    local: 'the local project',
    both: 'both',
    edit: 'edited by hand',
  };

  function refresh() {
    const solved = rows.filter((row) => chosen[row.dataset.region]).length;
    counter.textContent = String(solved);
    finish.disabled = solved !== rows.length;
  }

  function show(row) {
    const region = row.dataset.region;
    const state = row.querySelector('[data-state]');
    const answer = chosen[region];
    row.classList.toggle('is-solved', Boolean(answer));
    row.querySelectorAll('[data-choice]').forEach((button) => {
      button.setAttribute('aria-pressed', String(Boolean(answer) && button.dataset.choice === answer.choice));
    });
    state.textContent = answer ? `- ${sdocT('kept')}: ${sdocT(label[answer.choice])}` : '';
  }

  function choose(row, choice) {
    const region = row.dataset.region;
    const area = row.querySelector('textarea');
    const editor = row.querySelector('.gs-edit');
    if (choice === 'edit') {
      editor.hidden = false;
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

  function goTo(index, scroll = true) {
    if (!rows.length) return;
    current = (index + rows.length) % rows.length;
    rows.forEach((row, at) => row.classList.toggle('is-current', at === current));
    if (scroll) rows[current].scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  document.getElementById('gs-next').addEventListener('click', () => goTo(current + 1));
  document.getElementById('gs-prev').addEventListener('click', () => goTo(current - 1));
  document.addEventListener('keydown', (event) => {
    if (event.target.closest('textarea, select, input')) {
      if (event.key === 'Escape') event.target.closest('.gs-row').querySelector('.gs-edit').hidden = true;
      return;
    }
    if (event.key === 'n') goTo(current + 1);
    if (event.key === 'p') goTo(current - 1);
  });

  const select = document.getElementById('gs-file');
  if (select) {
    select.addEventListener('change', () => {
      window.location.href = `/git/sync/conflicts?file=${encodeURIComponent(select.value)}`;
    });
  }

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
        errorBox.textContent = answer.error || `${response.status}`;
        errorBox.hidden = false;
        finish.disabled = false;
        return;
      }
      window.location.href = answer.next || '/git/sync';
    } catch (error) {
      errorBox.textContent = sdocT('The server does not answer.');
      errorBox.hidden = false;
      finish.disabled = false;
    }
  });

  rows.forEach(show);
  refresh();
  goTo(0, false);
})();
