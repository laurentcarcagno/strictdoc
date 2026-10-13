// <sdoc-ai-bar>: the command bar of the assistant, above every Markdown editor
// of a form (features/llm/assist/). Type "/" for the commands, "@" to mention a
// requirement, a document or the selection. The server answers typed
// operations; they are shown as proposals and only a click applies them.
//
// The bar talks to the editor (<sdoc-markdown-editor>, see
// developer/milkdown/src/entry.js) through getMarkdown(), getSelection() and
// replaceRange(). Texts of the server are shown with textContent, never as HTML.
(() => {
  const URLS = {
    commands: '/llm/assist/commands',
    mentions: '/llm/assist/mentions',
    assist: '/actions/llm/assist',
    apply: '/actions/llm/apply',
  };
  const HISTORY_KEY = 'sdoc-ai-history';
  const MAX_DIFF_WORDS = 600;

  let catalogue = null;
  async function loadCatalogue() {
    if (!catalogue) {
      catalogue = fetch(`${URLS.commands}?scope=field`, {
        credentials: 'same-origin',
      })
        .then((response) => (response.ok ? response.json() : null))
        .catch(() => null);
    }
    return catalogue;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // **bold** and `code` in a line, as DOM nodes.
  function inline(parent, text) {
    for (const part of text.split(/(`[^`]+`|\*\*[^*]+\*\*)/)) {
      if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
        parent.append(element('code', '', part.slice(1, -1)));
      } else if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        parent.append(element('strong', '', part.slice(2, -2)));
      } else if (part) {
        parent.append(document.createTextNode(part));
      }
    }
  }

  // A small Markdown: paragraphs and "- " lists.
  function markdownLite(text) {
    const box = element('div', 'ai-bar__text');
    let list = null;
    for (const line of text.split('\n')) {
      if (line.startsWith('- ')) {
        if (!list) {
          list = element('ul');
          box.append(list);
        }
        const item = element('li');
        inline(item, line.slice(2));
        list.append(item);
      } else {
        list = null;
        if (line.trim()) {
          const paragraph = element('p');
          inline(paragraph, line);
          box.append(paragraph);
        }
      }
    }
    return box;
  }

  // Word level difference of two texts: [[kind, text], ...], kind in = + -.
  function diffWords(before, after) {
    const a = before.split(/(\s+)/).filter((part) => part !== '');
    const b = after.split(/(\s+)/).filter((part) => part !== '');
    if (a.length > MAX_DIFF_WORDS || b.length > MAX_DIFF_WORDS) {
      return [['-', before], ['+', after]];
    }
    const table = Array.from({ length: a.length + 1 }, () =>
      new Array(b.length + 1).fill(0)
    );
    for (let i = a.length - 1; i >= 0; i -= 1) {
      for (let j = b.length - 1; j >= 0; j -= 1) {
        table[i][j] =
          a[i] === b[j]
            ? table[i + 1][j + 1] + 1
            : Math.max(table[i + 1][j], table[i][j + 1]);
      }
    }
    const out = [];
    let i = 0;
    let j = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) {
        out.push(['=', a[i]]);
        i += 1;
        j += 1;
      } else if (table[i + 1][j] >= table[i][j + 1]) {
        out.push(['-', a[i]]);
        i += 1;
      } else {
        out.push(['+', b[j]]);
        j += 1;
      }
    }
    while (i < a.length) out.push(['-', a[i++]]);
    while (j < b.length) out.push(['+', b[j++]]);
    return out;
  }

  function diffView(before, after) {
    const box = element('div', 'ai-bar__diff');
    for (const [kind, text] of diffWords(before, after)) {
      if (kind === '=') box.append(document.createTextNode(text));
      else box.append(element(kind === '-' ? 'del' : 'ins', '', text));
    }
    return box;
  }

  class SdocAiBar extends HTMLElement {
    connectedCallback() {
      if (this._built) return;
      this._built = true;
      this._result = null;
      this._busy = false;
      this._menuItems = [];
      this._menuIndex = -1;
      this._history = this._loadHistory();
      this._historyAt = -1;
      this.dataset.testid = 'ai-bar';

      const row = element('div', 'ai-bar__row');
      const icon = element('span', 'ai-bar__icon', '✦');
      icon.setAttribute('aria-hidden', 'true');
      this._input = element('input', 'ai-bar__input');
      this._input.type = 'text';
      this._input.autocomplete = 'off';
      this._input.spellcheck = false;
      this._input.placeholder =
        'Ask the assistant…  / for commands, @ to mention';
      this._input.setAttribute('aria-label', 'Assistant command');
      this._input.dataset.testid = 'ai-bar-input';
      this._provider = element('select', 'ai-bar__provider');
      this._provider.hidden = true;
      this._provider.setAttribute('aria-label', 'Provider');
      this._send = element('button', 'ai-bar__send', 'Run');
      this._send.type = 'button';
      this._send.dataset.testid = 'ai-bar-run';
      row.append(icon, this._input, this._provider, this._send);

      this._menu = element('div', 'ai-bar__menu');
      this._menu.hidden = true;
      this._menu.setAttribute('role', 'listbox');
      this._menu.dataset.testid = 'ai-bar-menu';
      this._panel = element('div', 'ai-bar__panel');
      this._panel.hidden = true;
      this._panel.dataset.testid = 'ai-bar-panel';
      this.append(row, this._menu, this._panel);

      this._input.addEventListener('input', () => this._onInput());
      this._input.addEventListener('keydown', (event) => this._onKey(event));
      this._input.addEventListener('blur', () =>
        setTimeout(() => this._closeMenu(), 150)
      );
      this._send.addEventListener('click', () => this._run());
      loadCatalogue().then((data) => this._setCatalogue(data));
    }

    // ---- the editor and the form ----

    get _editor() {
      return this.parentElement?.querySelector('sdoc-markdown-editor') ?? null;
    }

    _context() {
      const form = this.closest('form');
      const value = (name) =>
        form?.querySelector(`input[name="${name}"]`)?.value ?? '';
      let fieldName = '';
      for (let node = this; node && node !== form; node = node.parentElement) {
        const named = node.querySelector?.(
          'input[type="hidden"][name$="[name]"]'
        );
        if (named) {
          fieldName = named.value;
          break;
        }
      }
      const isNew = Boolean(form?.querySelector('input[name="reference_mid"]'));
      return {
        document_mid: value('context_document_mid') || value('document_mid'),
        node_mid: isNew ? '' : value('requirement_mid') || value('section_mid'),
        reference_mid: isNew ? value('reference_mid') : '',
        field: fieldName,
      };
    }

    _target() {
      const editor = this._editor;
      const text = editor ? editor.getMarkdown() : '';
      const selection = editor ? editor.getSelection() : null;
      return {
        ...this._context(),
        text,
        selection: selection
          ? { text: selection.text, from: selection.from, to: selection.to }
          : null,
      };
    }

    // ---- catalogue, providers ----

    _setCatalogue(data) {
      this._catalogue = data;
      if (!data) return;
      const names = Object.keys(data.providers ?? {});
      if (names.length > 1) {
        for (const name of names) {
          const option = element('option', '', name);
          option.value = name;
          option.title = data.providers[name];
          this._provider.append(option);
        }
        this._provider.value = data.default_provider;
        this._provider.hidden = false;
      }
    }

    _providerName() {
      return this._provider.hidden ? '' : this._provider.value;
    }

    _isCloud(name) {
      const locals = this._catalogue?.local ?? [];
      const chosen = name || this._catalogue?.default_provider;
      return Boolean(chosen) && !locals.includes(chosen);
    }

    // ---- the lists ----

    _onInput() {
      const text = this._input.value;
      const caret = this._input.selectionStart ?? text.length;
      const slash = /^\/(\w*)$/.exec(text.slice(0, caret));
      if (slash && !text.slice(caret).trim().startsWith(' ')) {
        this._showCommands(slash[1]);
        return;
      }
      const at = /(^|\s)@([\w.:§-]*)$/.exec(text.slice(0, caret));
      if (at) {
        this._showMentions(at[2]);
        return;
      }
      this._closeMenu();
    }

    _showCommands(prefix) {
      const commands = this._catalogue?.commands ?? [];
      const items = commands
        .filter((command) => command.name.startsWith(prefix.toLowerCase()))
        .map((command) => ({
          label: command.usage,
          detail: command.summary,
          insert: `/${command.name} `,
          replace: /^\/\w*/,
        }));
      this._openMenu(items);
    }

    async _showMentions(query) {
      // Answers can come back in another order than the keys were typed.
      this._mentionSeq = (this._mentionSeq ?? 0) + 1;
      const sequence = this._mentionSeq;
      const context = this._context();
      const selected = Boolean(this._editor?.getSelection());
      const url =
        `${URLS.mentions}?q=${encodeURIComponent(query)}` +
        `&node_mid=${encodeURIComponent(context.node_mid)}` +
        `&selection=${selected}`;
      let data = null;
      try {
        const response = await fetch(url, { credentials: 'same-origin' });
        if (response.ok) data = await response.json();
      } catch (error) {
        // No list: the user can still type the mention.
      }
      if (sequence !== this._mentionSeq || this._input.value === '' || !data) {
        return;
      }
      const items = data.mentions.map((mention) => ({
        label: `@${mention.token}`,
        detail: [mention.label, mention.detail].filter(Boolean).join(' — '),
        insert: `@${mention.token} `,
        replace: /@[\w.:§-]*$/,
      }));
      this._openMenu(items, true);
    }

    _openMenu(items) {
      this._menuItems = items;
      this._menuIndex = items.length ? 0 : -1;
      this._menu.replaceChildren();
      items.forEach((item, index) => {
        const entry = element('div', 'ai-bar__menu-item');
        entry.setAttribute('role', 'option');
        entry.append(
          element('span', 'ai-bar__menu-label', item.label),
          element('span', 'ai-bar__menu-detail', item.detail)
        );
        entry.addEventListener('mousedown', (event) => {
          event.preventDefault();
          this._choose(index);
        });
        this._menu.append(entry);
      });
      this._menu.hidden = items.length === 0;
      this._markMenu();
    }

    _markMenu() {
      [...this._menu.children].forEach((child, index) =>
        child.classList.toggle('is-active', index === this._menuIndex)
      );
    }

    _closeMenu() {
      this._mentionSeq = (this._mentionSeq ?? 0) + 1;
      this._menu.hidden = true;
      this._menuItems = [];
      this._menuIndex = -1;
    }

    _choose(index) {
      const item = this._menuItems[index];
      if (!item) return;
      const caret = this._input.selectionStart ?? this._input.value.length;
      const head = this._input.value.slice(0, caret).replace(item.replace, '');
      const tail = this._input.value.slice(caret);
      this._input.value = head + item.insert + tail;
      const position = (head + item.insert).length;
      this._input.setSelectionRange(position, position);
      this._closeMenu();
      this._input.focus();
    }

    // ---- keys ----

    _onKey(event) {
      const open = !this._menu.hidden && this._menuItems.length > 0;
      if (event.key === 'ArrowDown' && open) {
        event.preventDefault();
        this._menuIndex = (this._menuIndex + 1) % this._menuItems.length;
        this._markMenu();
      } else if (event.key === 'ArrowUp' && open) {
        event.preventDefault();
        this._menuIndex =
          (this._menuIndex - 1 + this._menuItems.length) %
          this._menuItems.length;
        this._markMenu();
      } else if ((event.key === 'Enter' || event.key === 'Tab') && open) {
        event.preventDefault();
        this._choose(this._menuIndex);
      } else if (event.key === 'Enter') {
        // A form: Enter must not save it.
        event.preventDefault();
        this._run();
      } else if (event.key === 'Escape') {
        if (open) this._closeMenu();
        else this._panel.hidden = true;
      } else if (event.key === 'ArrowUp' && this._input.value === '') {
        this._recall(-1);
      } else if (event.key === 'ArrowDown' && this._historyAt >= 0) {
        this._recall(1);
      }
    }

    _loadHistory() {
      try {
        return JSON.parse(sessionStorage.getItem(HISTORY_KEY) ?? '[]');
      } catch (error) {
        return [];
      }
    }

    _remember(text) {
      this._history = [text, ...this._history.filter((t) => t !== text)].slice(
        0,
        20
      );
      this._historyAt = -1;
      try {
        sessionStorage.setItem(HISTORY_KEY, JSON.stringify(this._history));
      } catch (error) {
        // No storage: the history lasts as long as the page.
      }
    }

    _recall(step) {
      const next = this._historyAt + (step < 0 ? 1 : -1);
      if (next < -1 || next >= this._history.length) return;
      this._historyAt = next;
      this._input.value = next === -1 ? '' : this._history[next];
    }

    focusInput() {
      this._input.focus();
    }

    // ---- running a command ----

    async _run(confirmed = false) {
      const input = this._input.value.trim();
      if (!input || this._busy) return;
      this._closeMenu();
      this._remember(input);
      this._busy = true;
      this._send.disabled = true;
      this._showStatus('Working…');
      const payload = {
        v: 1,
        scope: 'field',
        input,
        target: this._target(),
        provider: this._providerName(),
        cloud_confirmed: confirmed,
      };
      try {
        const response = await fetch(URLS.assist, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) {
          this._showError(body.detail ?? `Error ${response.status}.`);
        } else if (body.status === 'needs_confirmation') {
          this._showConfirmation(body);
        } else {
          this._showResult(body);
        }
      } catch (error) {
        this._showError(`The assistant cannot be reached: ${error.message}`);
      } finally {
        this._busy = false;
        this._send.disabled = false;
      }
    }

    // ---- showing ----

    _show(...nodes) {
      this._panel.replaceChildren(...nodes);
      this._panel.hidden = false;
    }

    _showStatus(text) {
      const status = element('div', 'ai-bar__status', text);
      status.setAttribute('role', 'status');
      this._show(status);
    }

    _showError(text) {
      const box = element('div', 'ai-bar__error', text);
      box.setAttribute('role', 'alert');
      box.dataset.testid = 'ai-bar-error';
      this._show(box, this._closeButton());
    }

    _closeButton() {
      const bar = element('div', 'ai-bar__buttons');
      const close = element('button', 'ai-bar__button', 'Close');
      close.type = 'button';
      close.addEventListener('click', () => {
        this._panel.hidden = true;
      });
      bar.append(close);
      return bar;
    }

    _showConfirmation(body) {
      const confirmation = body.confirmation;
      const box = element('div', 'ai-bar__confirm');
      box.dataset.testid = 'ai-bar-confirm';
      box.append(
        element(
          'p',
          'ai-bar__warning',
          `This sends ${confirmation.chars} characters to the provider ` +
            `${confirmation.provider} (${confirmation.model}), outside the network.`
        )
      );
      const details = element('details');
      details.append(
        element('summary', '', 'What is sent'),
        element('pre', 'ai-bar__prompt', confirmation.prompt)
      );
      box.append(details);
      const buttons = element('div', 'ai-bar__buttons');
      const yes = element('button', 'ai-bar__button ai-bar__button--primary', 'Send');
      yes.type = 'button';
      yes.dataset.testid = 'ai-bar-confirm-send';
      yes.addEventListener('click', () => this._run(true));
      const no = element('button', 'ai-bar__button', 'Cancel');
      no.type = 'button';
      no.addEventListener('click', () => {
        this._panel.hidden = true;
      });
      buttons.append(yes, no);
      this._show(box, buttons);
    }

    _showResult(result) {
      this._result = result;
      const nodes = [];
      if (result.message) {
        const message = markdownLite(result.message);
        message.dataset.testid = 'ai-bar-message';
        nodes.push(message);
      }
      for (const warning of result.warnings ?? []) {
        nodes.push(element('p', 'ai-bar__warning', warning));
      }
      for (const finding of result.findings ?? []) {
        nodes.push(this._findingCard(finding));
      }
      const hasActions = (result.actions ?? []).length > 0;
      for (const action of result.actions ?? []) {
        nodes.push(this._actionCard(action));
      }
      const buttons = element('div', 'ai-bar__buttons');
      if (hasActions) {
        const apply = element(
          'button',
          'ai-bar__button ai-bar__button--primary',
          'Apply selected'
        );
        apply.type = 'button';
        apply.dataset.testid = 'ai-bar-apply';
        apply.addEventListener('click', () => this._apply());
        buttons.append(apply);
      }
      const again = element('button', 'ai-bar__button', 'Try again');
      again.type = 'button';
      again.addEventListener('click', () => this._run());
      const close = element('button', 'ai-bar__button', hasActions ? 'Discard' : 'Close');
      close.type = 'button';
      close.dataset.testid = 'ai-bar-discard';
      close.addEventListener('click', () => {
        this._panel.hidden = true;
      });
      buttons.append(again, close);
      const meta = result.meta ?? {};
      if (meta.model) {
        buttons.append(
          element(
            'span',
            'ai-bar__meta',
            `${meta.is_local ? 'local' : 'cloud'} · ${meta.model} · ${meta.prompt ?? ''}`
          )
        );
      }
      nodes.push(buttons);
      this._show(...nodes);
    }

    _findingCard(finding) {
      const card = element('div', `ai-bar__card ai-bar__card--${finding.severity}`);
      card.dataset.testid = 'ai-bar-finding';
      const head = element('div', 'ai-bar__card-head');
      head.append(
        element('span', 'ai-bar__badge', finding.severity),
        element('span', 'ai-bar__rule', finding.rule)
      );
      card.append(head);
      if (finding.quote) card.append(element('blockquote', '', finding.quote));
      card.append(element('p', '', finding.message));
      if (finding.suggestion) {
        card.append(element('p', 'ai-bar__suggestion', finding.suggestion));
      }
      return card;
    }

    _actionCard(action) {
      // A div, not a label: the label style of the forms would apply.
      const card = element('div', 'ai-bar__card ai-bar__action');
      card.dataset.testid = 'ai-bar-action';
      const box = document.createElement('input');
      box.type = 'checkbox';
      card.addEventListener('click', (event) => {
        if (event.target !== box) box.checked = !box.checked;
      });
      box.checked = Boolean(action.default);
      box.dataset.actionId = action.id;
      const body = element('div', 'ai-bar__action-body');
      body.append(element('div', 'ai-bar__card-title', action.label));
      if (action.op === 'replace_text') {
        body.append(diffView(action.old, action.new));
      } else if (action.op === 'add_comment') {
        if (action.anchor) {
          body.append(element('blockquote', '', action.anchor.text));
        }
        body.append(element('p', '', action.body));
      } else if (action.op === 'insert_node') {
        const fields = action.node.fields;
        body.append(element('p', 'ai-bar__card-title', fields.TITLE));
        body.append(element('p', '', fields.STATEMENT));
        if (fields.RATIONALE) {
          body.append(element('p', 'ai-bar__suggestion', fields.RATIONALE));
        }
      }
      card.append(box, body);
      return card;
    }

    // ---- applying ----

    async _apply() {
      const result = this._result;
      if (!result) return;
      const chosen = new Set(
        [...this._panel.querySelectorAll('input[data-action-id]')]
          .filter((box) => box.checked)
          .map((box) => box.dataset.actionId)
      );
      const actions = result.actions.filter((action) => chosen.has(action.id));
      if (actions.length === 0) {
        this._showError('Tick at least one proposal.');
        return;
      }
      const edits = actions.filter((action) => action.op === 'replace_text');
      const remote = actions.filter((action) => action.op !== 'replace_text');
      const editor = this._editor;
      const notes = [];
      if (remote.length > 0 && editor) {
        // The form that is open would send the old comments and the old
        // revision: changes that need the server wait for a saved form.
        if (editor.getMarkdown() !== (this._cleanMarkdown ?? editor.getMarkdown())) {
          this._showError(
            'Save or discard your changes first, then add the comments or the requirements.'
          );
          return;
        }
      }
      for (const edit of edits.sort(
        (a, b) => (b.range?.from ?? 0) - (a.range?.from ?? 0)
      )) {
        const current = editor ? editor.getMarkdown() : '';
        const slice = edit.range
          ? current.slice(edit.range.from, edit.range.to)
          : current;
        if (!editor || slice !== edit.old) {
          this._showError(
            'The text changed since the answer: run the command again.'
          );
          return;
        }
        editor.replaceRange(edit.range ? edit.range.from : null, edit.range?.to ?? null, edit.new);
        notes.push('Text replaced. Ctrl+Z undoes it; nothing is saved until you save the form.');
      }
      if (remote.length > 0) {
        const response = await fetch(URLS.apply, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            call_id: result.meta.call_id,
            action_ids: remote.map((action) => action.id),
          }),
        }).catch(() => null);
        const body = response ? await response.json().catch(() => ({})) : {};
        if (!response || !response.ok) {
          this._showError(body.detail ?? 'The server refused.');
          return;
        }
        for (const error of body.errors ?? []) {
          notes.push(`Not applied: ${error.message}`);
        }
        if ((body.applied ?? []).length > 0) {
          notes.push(`${body.applied.length} change(s) saved. The page reloads.`);
          setTimeout(() => window.Turbo?.visit(window.location.href, { action: 'replace' }), 1200);
        }
      }
      const done = element('div', 'ai-bar__status', notes.join(' '));
      done.dataset.testid = 'ai-bar-done';
      this._show(done, this._closeButton());
    }

    // The editor as it was when the bar first looked at it (not edited yet).
    markClean() {
      this._cleanMarkdown = this._editor?.getMarkdown();
    }
  }

  if (!customElements.get('sdoc-ai-bar')) {
    customElements.define('sdoc-ai-bar', SdocAiBar);
  }

  // A bar above every Markdown editor, including the ones that Turbo adds.
  function attach() {
    document.querySelectorAll('sdoc-markdown-editor').forEach((editor) => {
      const previous = editor.previousElementSibling;
      if (previous && previous.tagName === 'SDOC-AI-BAR') return;
      const bar = document.createElement('sdoc-ai-bar');
      editor.before(bar);
      // The editor writes its first Markdown when it is ready.
      const mark = () => bar.markClean();
      if (editor.dataset.ready === 'true') mark();
      else new MutationObserver((_, observer) => {
        if (editor.dataset.ready === 'true') {
          observer.disconnect();
          mark();
        }
      }).observe(editor, { attributes: true, attributeFilter: ['data-ready'] });
    });
  }

  let scheduled = false;
  new MutationObserver(() => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      attach();
    });
  }).observe(document.documentElement, { childList: true, subtree: true });
  attach();

  // Turbo keeps a snapshot of the page: the bars are rebuilt, not cached.
  document.addEventListener('turbo:before-cache', () => {
    document.querySelectorAll('sdoc-ai-bar').forEach((bar) => bar.remove());
  });

  // Ctrl+/ puts the cursor in the bar of the editor that has the focus, or the
  // first one.
  document.addEventListener('keydown', (event) => {
    if (event.key !== '/' || !(event.ctrlKey || event.metaKey)) return;
    const bars = [...document.querySelectorAll('sdoc-ai-bar')];
    if (bars.length === 0) return;
    const active = bars.find((bar) => bar.parentElement?.contains(document.activeElement));
    event.preventDefault();
    (active ?? bars[0]).focusInput();
  });
})();
