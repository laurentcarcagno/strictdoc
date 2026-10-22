// <sdoc-markdown-editor>: a Milkdown (Crepe) editor for one multiline field
// of a document whose MARKUP is Markdown.
//
// Markup, in the form (see components/form/field/markdown_editor/index.jinja):
//   <sdoc-form-field>
//     <sdoc-markdown-editor data-upload-url="..."></sdoc-markdown-editor>
//     <textarea hidden name="...">markdown</textarea>
//   </sdoc-form-field>
// The hidden textarea is what the form submits. It only changes when the user
// changes the text, so a field that was not edited is sent back as it was.
import { Crepe } from '@milkdown/crepe';
import { editorViewCtx, schemaCtx, serializerCtx } from '@milkdown/kit/core';
import { replaceAll } from '@milkdown/kit/utils';
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';
import { sdocMarkers } from './sdoc_markers.js';
import { sdocTables } from './tables.js';
import { tableBar } from './table_bar.js';
import './sdoc_editor.css';

const IMAGE_ERROR_CLASS = 'sdoc-markdown-editor__error';

class SdocMarkdownEditor extends HTMLElement {
  constructor() {
    super();
    // editable_field.js refuses every drop outside its own fields, at window
    // level. The editor handles dropped images itself, so the drag events
    // stop here (after the editor saw them) and never reach that guard.
    for (const type of ['dragenter', 'dragover', 'dragleave', 'drop']) {
      this.addEventListener(type, (event) => event.stopPropagation());
    }
  }

  connectedCallback() {
    // A generation counter makes a late create() of a removed element harmless.
    this._generation = (this._generation ?? 0) + 1;
    this._start(this._generation);
  }

  disconnectedCallback() {
    this._generation = (this._generation ?? 0) + 1;
    this._stop();
  }

  get _textarea() {
    return this.parentElement?.querySelector('textarea[hidden]') ?? null;
  }

  async _start(generation) {
    const textarea = this._textarea;
    if (textarea === null || this._crepe) return;

    const original = textarea.value;
    const host = document.createElement('div');
    host.className = 'sdoc-markdown-editor__host';
    this.replaceChildren(host);

    const crepe = new Crepe({
      root: host,
      defaultValue: original,
      features: {
        [Crepe.Feature.TopBar]: true,
        // Replaced by sdoc tables and the table bar (merged cells, header rows).
        [Crepe.Feature.Table]: false,
        [Crepe.Feature.Latex]: false,
        [Crepe.Feature.AI]: false,
      },
      featureConfigs: {
        [Crepe.Feature.ImageBlock]: {
          onUpload: (file) => this._upload(file),
          inlineOnUpload: (file) => this._upload(file),
          blockOnUpload: (file) => this._upload(file),
        },
        [Crepe.Feature.Placeholder]: { text: 'Write here...' },
      },
    });
    // The tables are read before the markers, which look into their cells.
    crepe.editor.use(sdocTables);
    crepe.editor.use(sdocMarkers);
    crepe.editor.use(tableBar);
    this._crepe = crepe;
    await crepe.create();
    if (generation !== this._generation) {
      this._stop();
      return;
    }

    // What the editor writes for the text as loaded. Only a difference from
    // it counts as an edit, so opening a field and saving it changes nothing.
    const baseline = crepe.getMarkdown();
    const sync = (markdown) => {
      textarea.value = markdown === baseline ? original : markdown;
    };
    crepe.on((listener) => {
      listener.markdownUpdated((_ctx, markdown) => sync(markdown));
    });
    // Milkdown reports a change about 200 ms after the last key. A click on
    // Save inside that delay would send the old text, so the form is also
    // synchronised when it is submitted (this listener runs before Turbo's).
    this._form = this.closest('form');
    this._onSubmit = () => sync(crepe.getMarkdown());
    this._form?.addEventListener('submit', this._onSubmit, true);
    this.dataset.ready = 'true';
  }

  _stop() {
    const crepe = this._crepe;
    this._crepe = null;
    delete this.dataset.ready;
    this._form?.removeEventListener('submit', this._onSubmit, true);
    this._form = null;
    if (crepe) {
      try {
        crepe.destroy();
      } catch (error) {
        console.error('sdoc-markdown-editor: destroy failed', error);
      }
    }
  }

  // ---- What the assistant bar (features/llm/assets/llm/ai_bar.js) uses ----

  // The Markdown of the field as the editor writes it now (the text that the
  // form would send), also before the editor is ready.
  getMarkdown() {
    return this._crepe
      ? this._crepe.getMarkdown()
      : (this._textarea?.value ?? '');
  }

  // The selection as {text, from, to}: text is the Markdown of the selected
  // words, from and to are offsets in getMarkdown(). null when nothing is
  // selected or the words cannot be found in the Markdown.
  getSelection() {
    const crepe = this._crepe;
    if (!crepe) return null;
    let result = null;
    crepe.editor.action((ctx) => {
      const { selection, doc } = ctx.get(editorViewCtx).state;
      if (selection.empty) return;
      const plain = doc.textBetween(selection.from, selection.to, '\n');
      let markdown = plain;
      try {
        const wrapper = ctx
          .get(schemaCtx)
          .topNodeType.createAndFill(null, selection.content().content);
        if (wrapper) markdown = ctx.get(serializerCtx)(wrapper).trim();
      } catch (error) {
        // The plain text is used when the selection cannot be serialised.
      }
      if (markdown.length === 0) return;
      // The same words may appear before: take the n-th occurrence, n being
      // how many times they appear before the selection.
      const before = doc.textBetween(0, selection.from, '\n');
      let skipped = 0;
      for (
        let at = before.indexOf(plain);
        plain && at >= 0;
        at = before.indexOf(plain, at + plain.length)
      ) {
        skipped += 1;
      }
      const full = crepe.getMarkdown();
      let found = -1;
      for (let n = 0, at = full.indexOf(markdown); at >= 0; n += 1) {
        found = at;
        if (n >= skipped) break;
        at = full.indexOf(markdown, at + markdown.length);
      }
      if (found >= 0) {
        result = { text: markdown, from: found, to: found + markdown.length };
      }
    });
    return result;
  }

  // Replaces the whole text (from === null) or the words between two offsets
  // of getMarkdown(), as one change that Ctrl+Z undoes.
  replaceRange(from, to, text) {
    const crepe = this._crepe;
    if (!crepe) return false;
    const current = crepe.getMarkdown();
    const next =
      from === null ? text : current.slice(0, from) + text + current.slice(to);
    crepe.editor.action(replaceAll(next));
    return true;
  }

  async _upload(file) {
    this._clearError();
    const uploadUrl = this.dataset.uploadUrl;
    try {
      if (!uploadUrl) throw new Error('Image upload is not available here.');
      const body = new FormData();
      body.append('uploaded_files', file);
      const response = await fetch(uploadUrl, { method: 'POST', body });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail ?? `Upload failed (${response.status}).`);
      }
      // The server replaces spaces in the file name and may answer with a
      // Sphinx wildcard ("name.*") that Markdown cannot resolve.
      const name = file.name.replace(/ /g, '_');
      let uri = payload.images?.[name];
      if (!uri) throw new Error('The server did not return the image path.');
      if (uri.endsWith('.*')) {
        uri = uri.slice(0, -1) + name.split('.').pop();
      }
      return uri;
    } catch (error) {
      this._showError(`Image upload failed: ${error.message}`);
      throw error;
    }
  }

  _showError(message) {
    const element = document.createElement('div');
    element.className = IMAGE_ERROR_CLASS;
    element.setAttribute('role', 'alert');
    element.dataset.testid = 'markdown-editor-error';
    element.textContent = message;
    this.prepend(element);
  }

  _clearError() {
    this.querySelector(`.${IMAGE_ERROR_CLASS}`)?.remove();
  }
}

if (!customElements.get('sdoc-markdown-editor')) {
  customElements.define('sdoc-markdown-editor', SdocMarkdownEditor);
}

// Turbo keeps a snapshot of the page for the back button. An editor in that
// snapshot would be a dead copy, so the editors are removed before it is taken.
document.addEventListener('turbo:before-cache', () => {
  document.querySelectorAll('sdoc-markdown-editor').forEach((element) => {
    element._stop();
    element.replaceChildren();
  });
});
