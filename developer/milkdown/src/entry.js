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
import '@milkdown/crepe/theme/common/style.css';
import '@milkdown/crepe/theme/frame.css';
import { sdocMarkers } from './sdoc_markers.js';
import './sdoc_editor.css';

const IMAGE_ERROR_CLASS = 'sdoc-markdown-editor__error';

class SdocMarkdownEditor extends HTMLElement {
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
    crepe.editor.use(sdocMarkers);
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
