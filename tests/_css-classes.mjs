/** Спільне для охоронців «кожен клас розмітки має стиль»: панель коментарів (0.27.1) і діалоги (етап В, 0.28.0). */
import { readFileSync } from "node:fs";

// Коментарі CSS не рахуються: `.cmt-x` у тексті коментаря — не правило (ревʼю 0.27.1).
export const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
export const hasRule = (cls) => new RegExp(`\\.${cls.replace(/[-]/g, "\\-")}(?![\\w-])`).test(css);

const NAME = /^[a-z][\w-]*[a-z0-9]$/;

/**
 * Класи з розмітки файлу:
 * - `class="…"` у шаблонах — літеральні шматки; `префікс${…}` — хвости з `dynamic` (префікса там нема — виняток, щоб
 *   новий динамічний клас не проходив повз охоронця);
 * - `quoted` — джерело RegExp-альтернатив: назви в лапках поза атрибутом (гілки тернарних виразів);
 * - `dom: true` — ще й DOM-код: `className = '…'`, `classList.add/toggle('…')`, `setAttribute('class', '…')`.
 */
export function classesIn(src, { dynamic = new Map(), quoted = "", dom = false } = {}) {
  const out = new Set();
  for (const m of src.matchAll(/class="([^"]*)"/g)) {
    // `${…}`-вставки всередині атрибута: беремо лише літеральні шматки, а гілки тернарних виразів — з лапок нижче
    const literal = m[1].replace(/\$\{[^}]*\}/g, " ");
    for (const c of literal.split(/\s+/)) if (NAME.test(c)) out.add(c);
    for (const d of m[1].matchAll(/([a-z][\w-]*-)\$\{/g)) {
      const tails = dynamic.get(d[1]);
      if (!tails) throw new Error(`динамічний клас «${d[1]}\${…}» без переліку хвостів у DYNAMIC`);
      for (const tail of tails) out.add(d[1] + tail);
    }
  }
  // `id="cmt-q"` — це id, а не клас: пропускаємо
  // `const INPUT_ID = 'cv-ask-input'` — це id (константи `*_ID`), а не клас
  const noIds = src.replace(/\b\w+_ID\s*=\s*(['"`])[^'"`]*\1/g, "");
  if (quoted) for (const m of noIds.matchAll(new RegExp(`(?<!\\bid=)["'\` ](${quoted})["'\`]`, "g"))) out.add(m[1]);
  if (dom) {
    const re = /(?:className\s*=\s*|classList\.(?:add|toggle)\(\s*|setAttribute\(\s*'class',\s*)(['"`])([^'"`]*)\1/g;
    for (const m of src.matchAll(re)) for (const c of m[2].split(/\s+/)) if (NAME.test(c)) out.add(c);
  }
  return out;
}
