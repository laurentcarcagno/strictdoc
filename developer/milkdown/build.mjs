// Builds the editor bundle into strictdoc/features/milkdown/assets/milkdown/.
// Run with: npm ci && npm run build   (in developer/milkdown)
import { build } from 'esbuild';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const outdir = path.resolve(
  here, '..', '..', 'strictdoc', 'features', 'milkdown', 'assets', 'milkdown'
);

await build({
  entryPoints: {
    milkdown: path.join(here, 'src', 'entry.js'),
    // The diagram editor (maxGraph), loaded on the first click on its button.
    diagram: path.join(here, 'src', 'diagram_entry.js'),
  },
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

// maxGraph is Apache-2.0: the bundle ships with its license text.
const maxGraphDir = path.join(here, 'node_modules', '@maxgraph', 'core');
const maxGraph = JSON.parse(readFileSync(path.join(maxGraphDir, 'package.json'), 'utf8'));
writeFileSync(
  path.join(outdir, 'diagram.js.LEGAL.txt'),
  `Bundled license information:

${maxGraph.name} ${maxGraph.version}

` +
    readFileSync(path.join(maxGraphDir, 'LICENSE'), 'utf8')
);
