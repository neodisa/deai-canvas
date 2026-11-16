/**
 * Етап В: кожен клас розмітки діалогів має правило в `app/styles.css` — та сама вада, що білі кнопки 0.27.0, не
 * мусить повторитись у діалогах. Розмітка: `app/ask.js` (DOM-код), `feedback-view.js`, `update-view.js`,
 * `space-dialogs.js`, `trust-view.js`, `inline-confirm.js` (рядки).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { classesIn, hasRule } from "./_css-classes.mjs";

const FILES = ["ask.js", "feedback-view.js", "update-view.js", "space-dialogs.js", "trust-view.js"];
/** Маркери без власного стилю — лише з причиною (заповнити після першого прогону, перевіривши кожен grep-ом). */
const NO_STYLE = new Map([
  ["up-p", "абзац опису змін; вигляд дає тегове правило `.up .up-notes p`"],
  ["up-sec", "обгортка версії в описі змін; вигляд дають `.up-sec-h` і `.up .up-notes p`"],
  ["up-restart", "модифікатор `.up-why` (текст про ручний перезапуск); вигляд дає `.up .up-why`"],
]);
const DYNAMIC = new Map([]);
/** Назви в лапках поза `class="…"` і DOM-код `ask.js`. Префікси — ті, що є в цих файлах; новий префікс — додати сюди. */
const OPTS = { dynamic: DYNAMIC, quoted: "cv-[\\w-]+|cfm[\\w-]*", dom: true };

test("кожен клас розмітки діалогів має правило в styles.css", () => {
  const missing = [];
  for (const f of FILES) {
    const src = readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
    for (const c of classesIn(src, OPTS)) if (!NO_STYLE.has(c) && !hasRule(c)) missing.push(`${f}: ${c}`);
  }
  assert.deepEqual(missing.sort(), []);
});

test("винятки не гниють", () => {
  const all = new Set(FILES.flatMap((f) => [...classesIn(readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8"), OPTS)]));
  for (const [c, why] of NO_STYLE) {
    assert.ok(why.length > 10, c);
    assert.ok(all.has(c), `${c}: уже не вживається`);
    assert.equal(hasRule(c), false, `${c}: стиль уже є`);
  }
});
