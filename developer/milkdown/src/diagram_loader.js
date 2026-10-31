// Loads the diagram editor bundle (diagram.js and diagram.css, next to
// milkdown.js) the first time it is needed. The bundle sets window.sdocDiagram.

// A classic script knows its own address only while it is evaluated.
const BUNDLE_URL = document.currentScript?.src ?? null;

let loading = null;

export function loadDiagramEditor() {
  if (window.sdocDiagram !== undefined) return Promise.resolve(window.sdocDiagram);
  if (loading === null) {
    loading = new Promise((resolve, reject) => {
      const base = baseUrl();
      if (base === null) {
        loading = null;
        reject(new Error('The address of the diagram editor is unknown.'));
        return;
      }
      const style = document.createElement('link');
      style.rel = 'stylesheet';
      style.href = `${base}diagram.css`;
      document.head.append(style);

      const script = document.createElement('script');
      script.src = `${base}diagram.js`;
      script.onload = () => {
        if (window.sdocDiagram === undefined) {
          loading = null;
          reject(new Error('The diagram editor did not start.'));
          return;
        }
        resolve(window.sdocDiagram);
      };
      script.onerror = () => {
        loading = null;
        script.remove();
        style.remove();
        reject(new Error('The diagram editor could not be loaded.'));
      };
      document.head.append(script);
    });
  }
  return loading;
}

function baseUrl() {
  const url =
    BUNDLE_URL ??
    document.querySelector('script[src*="milkdown/milkdown.js"]')?.src ??
    null;
  return url === null ? null : url.slice(0, url.lastIndexOf('/') + 1);
}
