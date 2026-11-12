// npm run check:money — падает, если в исходниках или собранном web/ в видимых строках
// встречаются валютные знаки и коды. Деньги в интерфейсе запрещены ТЗ.
//  * frontend/src: ищем во всех строковых литералах и JSX-тексте (весь файл, кроме комментариев).
//  * web/: в своих чанках — всё; в минифицированных вендорных чанках знак доллара неизбежен
//    (`$$typeof`, шаблонные строки), поэтому там ищем только буквенные коды и знак рубля.
import { readdir, readFile, stat } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const SRC = join(root, 'src');
const WEB = join(root, '..', 'web');

const WORDS = /₽|\bруб(\.|\b|л)|\bBYN\b|\bRUB\b|\bUSD\b|\bEUR\b/;
const DOLLAR_IN_TEXT = /\$/;
const TEXT_EXT = new Set(['.ts', '.tsx', '.css', '.html', '.json', '.js', '.svg']);

async function* walk(dir) {
  let entries;
  try {
    entries = await readdir(dir);
  } catch {
    return;
  }
  for (const name of entries) {
    const p = join(dir, name);
    const s = await stat(p);
    if (s.isDirectory()) yield* walk(p);
    else if (TEXT_EXT.has(extname(name))) yield p;
  }
}

function stripComments(code) {
  return code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`])\/\/.*$/gm, '$1');
}

/** Видимые строки исходника: литералы в кавычках и текст между JSX-тегами. */
function visibleStrings(code) {
  const out = [];
  const re = /(['"`])((?:\\.|(?!\1)[^\\])*)\1|>([^<>{}]+)</g;
  let m;
  while ((m = re.exec(code))) out.push(m[2] ?? m[3] ?? '');
  return out;
}

const problems = [];
let files = 0;

for await (const file of walk(SRC)) {
  if (file.endsWith('schema.d.ts')) continue; // сгенерированные типы бэкенда: описания полей, не UI
  files++;
  const text = stripComments(await readFile(file, 'utf8'));
  const strings = extname(file) === '.json' ? [text] : visibleStrings(text);
  for (const s of strings) {
    if (WORDS.test(s)) problems.push(`${file}: «${s.match(WORDS)[0]}» в «${s.slice(0, 60)}»`);
    // В TS-строках $ встречается только как ${…} шаблона — его убираем перед проверкой.
    else if (DOLLAR_IN_TEXT.test(s.replace(/\$\{/g, ''))) problems.push(`${file}: «$» в «${s.slice(0, 60)}»`);
  }
}

for await (const file of walk(WEB)) {
  files++;
  const text = await readFile(file, 'utf8');
  const m = text.match(WORDS);
  if (m) problems.push(`${file}: «${m[0]}» рядом с «${text.slice(Math.max(0, m.index - 30), m.index + 30)}»`);
  if (extname(file) === '.html' && DOLLAR_IN_TEXT.test(text)) problems.push(`${file}: «$» в HTML`);
}

if (problems.length) {
  console.error(`check:money — найдено ${problems.length}:`);
  for (const p of problems) console.error('  ' + p);
  process.exit(1);
}
console.log(`check:money — денег нет (${files} файлов)`);
