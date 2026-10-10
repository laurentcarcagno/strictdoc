// Builds the editor bundle into strictdoc/features/milkdown/assets/milkdown/.
// Run with: npm ci && npm run build   (in developer/milkdown)
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const outdir = path.resolve(
  here, '..', '..', 'strictdoc', 'features', 'milkdown', 'assets', 'milkdown'
);

await build({
  entryPoints: { milkdown: path.join(here, 'src', 'entry.js') },
  outdir,
  bundle: true,
  minify: true,
  format: 'iife',
  target: ['es2020'],
  legalComments: 'external',
  alias: {
    '@codemirror/language-data': path.join(here, 'src', 'languages.js'),
    'katex/dist/katex.min.css': path.join(here, 'src', 'empty.css'),
    katex: path.join(here, 'src', 'katex_stub.js'),
  },
  loader: {
    '.woff': 'dataurl', '.woff2': 'dataurl', '.ttf': 'dataurl',
    '.svg': 'dataurl', '.png': 'dataurl',
  },
  logLevel: 'info',
});
