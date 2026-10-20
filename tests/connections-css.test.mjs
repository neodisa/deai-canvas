import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
const css = read("styles.css").replace(/\/\*[\s\S]*?\*\//g, "");
const rule = (selector) => {
  const e = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = new RegExp(`(?:^|[}\\s])${e}\\s*\\{([^{}]*)\\}`).exec(css);
  return m ? m[1] : null;
};

test("кожен клас розмітки «Підключення» має правило в styles.css", () => {
  const src = read("connections-view.js").replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/[^\n]*/g, "");
  const classes = new Set();
  for (const m of src.matchAll(/class="([^"]+)"/g)) {
    for (const c of m[1].replace(/\$\{[^}]*\}/g, " ").split(/\s+/)) {
      /* Фрагмент, що закінчується на «-», — статична голова класу з інтерполяцією (`cn-badge--${kind}`): сам по
         собі він не клас. Варіанти, яким потрібне правило, названо поіменно нижче. */
      if (/^cn-/.test(c) && !c.endsWith("-")) classes.add(c);
    }
  }
  /* Модифікатори значка: ці три мають власний колір. `unchecked` і `off` — лише базовий `.cn-badge` (нейтральний). */
  for (const k of ["ok", "error", "missing"]) classes.add(`cn-badge--${k}`);
  assert.ok(classes.size >= 25, `знайдено лише ${classes.size} класів — регексп зламано: ${[...classes]}`);
  const missing = [...classes].filter((c) => !new RegExp(`\\.${c}(?![\\w-])`).test(css));
  assert.deepEqual(missing, [], `класи без правила: ${missing.join(", ")}`);
});

test("кнопка «Підключення» в голові «Задач»: ряд дій має правило", () => {
  assert.match(rule(".th-head-acts") ?? "", /display:flex/);
});

test("бічна панель: 420px, над оверлеєм і під смугою, схована атрибутом і поза оверлеєм", () => {
  const d = rule(".cn-drawer");
  assert.ok(d, "правила .cn-drawer немає");
  assert.match(d, /position:fixed/);
  assert.match(d, /width:420px/);
  assert.match(d, /z-index:var\(--z-widget\)/);
  assert.match(rule(".cn-drawer[hidden]") ?? "", /display:none/);
  assert.match(rule("body:not(.home-open) .cn-drawer") ?? "", /display:none/);
  assert.match(css, /@media\s*\(max-width:\s*720px\)\s*\{[^{}]*\.cn-drawer\s*\{[^{}]*width:100%/);
});

test("кольори правил .cn-* — лише токени (тінь може мати rgba)", () => {
  const bad = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!/\.cn-/.test(m[1])) continue;
    const body = m[2].replace(/box-shadow:[^;]*;?/g, "");
    if (/#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i.test(body)) bad.push(m[1].trim());
  }
  assert.deepEqual(bad, [], `літерали кольорів у: ${bad.join(", ")}`);
});
