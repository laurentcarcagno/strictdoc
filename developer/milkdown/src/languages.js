// The code block languages of the editor. Replaces '@codemirror/language-data',
// which bundles over 100 grammars (about 1 MB). Add a language here to get
// syntax colouring for it.
import {
  LanguageDescription,
  LanguageSupport,
  StreamLanguage,
} from '@codemirror/language';
import { cpp } from '@codemirror/lang-cpp';
import { html } from '@codemirror/lang-html';
import { javascript } from '@codemirror/lang-javascript';
import { json } from '@codemirror/lang-json';
import { python } from '@codemirror/lang-python';
import { sql } from '@codemirror/lang-sql';
import { shell } from '@codemirror/legacy-modes/mode/shell';
import { yaml } from '@codemirror/legacy-modes/mode/yaml';

const ready = (support) => () => Promise.resolve(support);

export const languages = [
  LanguageDescription.of({ name: 'C', alias: ['h'], extensions: ['c', 'h'], load: ready(cpp()) }),
  LanguageDescription.of({ name: 'C++', alias: ['cpp', 'cc', 'hpp'], extensions: ['cpp', 'cc', 'hpp'], load: ready(cpp()) }),
  LanguageDescription.of({ name: 'HTML', alias: ['xml'], extensions: ['html', 'xml'], load: ready(html()) }),
  LanguageDescription.of({ name: 'JavaScript', alias: ['js', 'ts', 'typescript'], extensions: ['js', 'ts'], load: ready(javascript({ typescript: true })) }),
  LanguageDescription.of({ name: 'JSON', extensions: ['json'], load: ready(json()) }),
  LanguageDescription.of({ name: 'Python', alias: ['py'], extensions: ['py'], load: ready(python()) }),
  LanguageDescription.of({ name: 'SQL', extensions: ['sql'], load: ready(sql()) }),
  LanguageDescription.of({ name: 'Shell', alias: ['bash', 'sh'], extensions: ['sh'], load: ready(new LanguageSupport(StreamLanguage.define(shell))) }),
  LanguageDescription.of({ name: 'YAML', alias: ['yml'], extensions: ['yaml', 'yml'], load: ready(new LanguageSupport(StreamLanguage.define(yaml))) }),
];
