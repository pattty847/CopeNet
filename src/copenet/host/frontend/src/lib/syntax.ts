// Lightweight, dependency-free single-line syntax tokenizer for the diff +
// file-preview renderers. Not a full parser — it highlights the high-signal
// tokens (comments, strings, numbers, keywords) well enough to make code read
// like an editor, across the common languages a coding agent touches. It runs
// per-line (diffs are line-oriented) so multi-line block comments are only
// handled within a single line.

export type SyntaxClass = 'comment' | 'string' | 'number' | 'keyword' | 'plain';

export interface SyntaxToken {
  text: string;
  cls: SyntaxClass;
}

// Union keyword set across JS/TS, Python, Go, Rust, Java, C-family. False
// positives (a variable literally named "type") are acceptable for a
// lightweight highlighter.
const KEYWORDS = new Set([
  'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'do',
  'switch', 'case', 'break', 'continue', 'class', 'extends', 'implements', 'interface',
  'type', 'enum', 'import', 'export', 'from', 'default', 'new', 'this', 'super',
  'async', 'await', 'yield', 'try', 'catch', 'finally', 'throw', 'typeof', 'instanceof',
  'in', 'of', 'void', 'null', 'undefined', 'true', 'false', 'delete',
  'def', 'lambda', 'pass', 'None', 'True', 'False', 'elif', 'with', 'as', 'raise',
  'except', 'global', 'nonlocal', 'and', 'or', 'not', 'is', 'assert', 'del',
  'fn', 'mut', 'pub', 'struct', 'impl', 'trait', 'match', 'use', 'mod', 'crate',
  'func', 'package', 'go', 'defer', 'chan', 'map', 'range', 'select', 'self',
  'public', 'private', 'protected', 'static', 'final', 'abstract', 'override',
  'int', 'string', 'bool', 'float', 'double', 'char', 'long', 'short', 'unsigned',
]);

// Line-comment markers by file extension; falls back to // and #.
const LINE_COMMENTS: Record<string, string[]> = {
  py: ['#'], rb: ['#'], sh: ['#'], bash: ['#'], yaml: ['#'], yml: ['#'], toml: ['#'], ini: ['#'], r: ['#'],
  sql: ['--'], lua: ['--'],
  js: ['//'], jsx: ['//'], ts: ['//'], tsx: ['//'], go: ['//'], rs: ['//'],
  c: ['//'], h: ['//'], cpp: ['//'], hpp: ['//'], cc: ['//'], java: ['//'], kt: ['//'],
  cs: ['//'], swift: ['//'], php: ['//'], scala: ['//'], dart: ['//'],
};

export function langFromPath(path: string): string {
  const name = path.split('/').pop() || path;
  const ext = name.includes('.') ? name.split('.').pop()! : name;
  return ext.toLowerCase();
}

export function tokenizeLine(line: string, lang = ''): SyntaxToken[] {
  const tokens: SyntaxToken[] = [];
  const comments = LINE_COMMENTS[lang] || ['//', '#'];
  const n = line.length;
  let i = 0;
  let buf = '';
  const flush = () => {
    if (buf) {
      tokens.push({ text: buf, cls: 'plain' });
      buf = '';
    }
  };

  while (i < n) {
    const ch = line[i];
    const rest = line.slice(i);

    // Line comment → rest of line.
    if (comments.some((marker) => rest.startsWith(marker))) {
      flush();
      tokens.push({ text: rest, cls: 'comment' });
      break;
    }

    // Block comment (single-line slice, or to end of line).
    if (rest.startsWith('/*')) {
      flush();
      const end = rest.indexOf('*/');
      if (end >= 0) {
        tokens.push({ text: rest.slice(0, end + 2), cls: 'comment' });
        i += end + 2;
        continue;
      }
      tokens.push({ text: rest, cls: 'comment' });
      break;
    }

    // String literal (', ", `) with basic escape handling.
    if (ch === '"' || ch === "'" || ch === '`') {
      flush();
      let j = i + 1;
      let str = ch;
      while (j < n) {
        const cj = line[j];
        if (cj === '\\' && j + 1 < n) {
          str += cj + line[j + 1];
          j += 2;
          continue;
        }
        str += cj;
        j += 1;
        if (cj === ch) break;
      }
      tokens.push({ text: str, cls: 'string' });
      i = j;
      continue;
    }

    // Number (not when glued to an identifier char).
    const prev = i > 0 ? line[i - 1] : '';
    if (ch >= '0' && ch <= '9' && !/[A-Za-z_$]/.test(prev)) {
      flush();
      let j = i;
      let num = '';
      while (j < n && /[0-9._xXa-fA-F]/.test(line[j])) {
        num += line[j];
        j += 1;
      }
      tokens.push({ text: num, cls: 'number' });
      i = j;
      continue;
    }

    // Identifier / keyword.
    if (/[A-Za-z_$]/.test(ch)) {
      let j = i;
      let word = '';
      while (j < n && /[A-Za-z0-9_$]/.test(line[j])) {
        word += line[j];
        j += 1;
      }
      if (KEYWORDS.has(word)) {
        flush();
        tokens.push({ text: word, cls: 'keyword' });
      } else {
        buf += word;
      }
      i = j;
      continue;
    }

    buf += ch;
    i += 1;
  }

  flush();
  return tokens;
}

// Tailwind text classes per token kind. Hues chosen to read on the subtle
// green/red diff backgrounds without competing with them (the row background +
// gutter marker carry the add/remove signal; the text carries syntax).
export const SYNTAX_CLASS: Record<SyntaxClass, string> = {
  comment: 'text-operator-muted/55 italic',
  string: 'text-amber-300/90',
  number: 'text-sky-300/90',
  keyword: 'text-violet-300',
  plain: '',
};
