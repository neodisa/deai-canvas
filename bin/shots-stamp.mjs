/**
 * Штамп теки — content-hash, за яким видно, чи відстав знімок від макета.
 *
 * Хеш вмісту, а НЕ mtime і не git: форматер міняє mtime (перезняли б те, що не
 * змінювалось), а git не бачить незакоміченої правки — а рев'ю-раунд живе саме в
 * такому стані, і знімок із брудного дерева, підписаний комітом, був би брехнею.
 */
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

/** Теки, які ніколи не входять у штамп: похідні артефакти й службове. */
export const SKIP_DIRS = new Set(["shots", "node_modules", ".git", "publish"]);

/**
 * Службові файли САМОГО інструмента, які лежать у корені ітерації поруч із
 * дизайном. Вони описують, ЯК показати сторінки (перелік, граф флоу), але на
 * те, як браузер намалює будь-яку з них, не впливають ніяк — макети статичні
 * і жодного з цих файлів не читають.
 *
 * ⛔ Навіщо їх виключати. Корінь ітерації входить у штамп КОЖНОЇ сторінки
 * (`stampsFor`, `bin/shoot.mjs`) — свідомо, бо там лежать спільні стилі. Тому
 * правка графа флоу чи перейменування сторінки робила застарілими ВСІ кадри
 * ітерації й замовляла повну пересʼємку, у якій жоден піксель не змінився б.
 * Це TD-9, і виміряний він був вужче, ніж є насправді: там сказано про неявну
 * `main`, а насправді зачіпало всі сторінки разом.
 *
 * Тримати список тут, а не в `shoot.mjs`: він про ПРИРОДУ файлів (не дизайн),
 * а не про те, хто саме рахує штамп.
 */
export const TOOL_META = new Set(["pages.json", "flow.json"]);

/**
 * `[[відносний шлях, sha256], …]` по теці. `recursive: false` — лише файли
 * верхнього рівня: так рахується неявна `main`, чия «тека сторінки» це корінь
 * ітерації, де лежать ще й теки інших сторінок.
 * Теки немає — внесок нульовий, це не помилка: сторінку могли ще не створити.
 * Файли, чиї імена починаються з точки (`.canvas-state.json`), пропускаються.
 */
export function fileEntries(dir, { recursive = true, base = dir, skipNames = null } = {}) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    // Теки немає — внесок нульовий, це не помилка: сторінку могли ще не створити.
    // Будь-яка ІНША помилка (тека виявилась файлом, немає прав) прокидається:
    // тихо віддати [] означало б, що штамп більше не бачить змін у цій сторінці,
    // а це рівно та брехня, проти якої цей модуль існує.
    if (err.code === "ENOENT") return [];
    throw err;
  }
  const out = [];
  for (const entry of entries) {
    if (entry.name.startsWith(".")) continue;
    // Недописаний tmp атомарних писарів (`pages.json.ab12cd.tmp`) — не частина
    // сторінки. Без цього рядка осиротілий файл у корені ітерації зсував штамп,
    // тобто конвеєр перезнімав сторінку, у якій нічого не змінилось. Теку
    // `shots/` рятував SKIP_DIRS, корінь ітерації — ніщо. Суфікс той самий, що
    // в `atomic_io.TMP_SUFFIX` на боці Python; звірку тримає окремий тест.
    if (entry.name.endsWith(".tmp")) continue;
    /* Службові файли інструмента — лише там, де про це ПОПРОСИВ той, хто
       рахує штамп. Межа тут не по глибині, а по частині: `skipNames` передає
       лише частина «корінь ітерації» (`stampsFor`, `bin/shoot.mjs`), і вона
       нерекурсивна. Частина «сторінка» його не передає взагалі, тож
       однойменний файл усередині сторінки лишається її вмістом. Спроба
       розрізняти глибиною (`dir === base`) якраз і протікала: верхній рівень
       теки СТОРІНКИ — теж `base`. */
    if (skipNames && skipNames.has(entry.name)) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!recursive || SKIP_DIRS.has(entry.name)) continue;
      out.push(...fileEntries(full, { recursive, base }));
      continue;
    }
    if (!entry.isFile()) continue;
    out.push([path.relative(base, full),
              createHash("sha256").update(readFileSync(full)).digest("hex")]);
  }
  return out;
}

/** Один штамп із записів. Сортуємо, бо порядок обходу теки не є частиною правди. */
export function stampFrom(entries) {
  const rows = entries.map(([rel, hash]) => `${rel}:${hash}`).sort();
  return createHash("sha256").update(rows.join("\n")).digest("hex").slice(0, 16);
}

/**
 * Штамп кількох тек разом: `[{ dir, label, recursive }]`. `label` попереду шляху,
 * щоб `index.html` сторінки й `index.html` у `shared/` не злилися в один запис.
 */
export function folderStamp(parts) {
  return stampFrom(parts.flatMap(({ dir, label, recursive = true, skipNames = null }) =>
    fileEntries(dir, { recursive, skipNames }).map(([rel, hash]) => [`${label}/${rel}`, hash])));
}
