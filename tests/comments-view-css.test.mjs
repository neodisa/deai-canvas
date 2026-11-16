/**
 * Охоронець латки 0.27.1. У 0.27.0 кнопки шапки панелі мали клас `icon-btn`, якого не було в `app/styles.css`, — браузер
 * намалював свої світлі кнопки на темній панелі. Ні ревʼю, ні живі тести цього не бачили: вони перевіряють поведінку.
 * Тут — статично: кожен клас із розмітки `app/comments-view.js` має селектор у `app/styles.css`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const view = readFileSync(new URL("../app/comments-view.js", import.meta.url), "utf8");
// Коментарі CSS не рахуються: `.cmt-x` у тексті коментаря — не правило (ревʼю 0.27.1).
const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const app = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

/** Класи-маркери без власного стилю — лише з причиною. */
const NO_STYLE = new Map([
  ["cmt-body", "гачок скролу в app.js (querySelector); вигляд дає .insp-body"],
  ["cmt-ctx", "маркер рядка «де був елемент»; вигляд дає .cmt-note поруч"],
  ["cmt-sec--fold", "маркер згорнутого розділу; вигляд дає .cmt-sec"],
  ["cmt-sec--new", "гачок живих тестів розділу «Нові від команди»; вигляд дає .cmt-sec і .cmt-h--new"],
  ["cmt-aud--local", "колір дає базовий .cmt-aud (--dim); окремо фарбується лише командний"],
]);

/** Динамічні класи `префікс${вираз}`: усі можливі хвости. Новий динамічний префікс без запису тут — червоне (ревʼю 0.27.1:
 *  без цього `cmt-aud--local` охоронець не бачив зовсім). */
const DYNAMIC = new Map([
  ["cmt-aud--", ["local", "project"]],
]);

function classesInView(src) {
  const out = new Set();
  for (const m of src.matchAll(/class="([^"]*)"/g)) {
    // `${…}`-вставки всередині атрибута: беремо лише літеральні шматки, а гілки тернарних виразів — з лапок нижче
    const literal = m[1].replace(/\$\{[^}]*\}/g, " ");
    // хвіст на «-»/«--» — префікс динамічного класу (`cmt-aud--${…}`): повне імʼя відоме лише під час виконання
    for (const c of literal.split(/\s+/)) if (/^[a-z][\w-]*[a-z0-9]$/.test(c)) out.add(c);
    for (const d of m[1].matchAll(/([a-z][\w-]*-)\$\{/g)) {
      const tails = DYNAMIC.get(d[1]);
      if (!tails) throw new Error(`динамічний клас «${d[1]}\${…}» без переліку хвостів у DYNAMIC`);
      for (const tail of tails) out.add(d[1] + tail);
    }
  }
  // класи з тернарних гілок: " cmt-card--sel", "cmt-ib" : "cmt-act" тощо
  // `id="cmt-q"` — це id, а не клас: пропускаємо
  for (const m of src.matchAll(/(?<!\bid=)["'` ](cmt-[\w-]+|icob|insp-[\w-]+|panel-title)["'`]/g)) out.add(m[1]);
  return out;
}

const hasRule = (cls) => new RegExp(`\\.${cls.replace(/[-]/g, "\\-")}(?![\\w-])`).test(css);

test("кожен клас розмітки панелі коментарів має правило в styles.css", () => {
  const missing = [...classesInView(view)].filter((c) => !NO_STYLE.has(c) && !hasRule(c)).sort();
  assert.deepEqual(missing, [], `класи без стилю: ${missing.join(", ")}`);
});

test("перелік винятків не гниє: кожен виняток справді вживається і справді без стилю", () => {
  const used = classesInView(view);
  for (const [c, why] of NO_STYLE) {
    assert.ok(why && why.length > 10, `${c}: причина обовʼязкова`);
    assert.ok(used.has(c), `${c}: у розмітці вже нема — приберіть виняток`);
    assert.equal(hasRule(c), false, `${c}: стиль уже є — приберіть виняток`);
  }
});

test("колір номера локальної картки = колір піна для Claude", () => {
  const tok = /--local-pin:\s*(#[0-9A-Fa-f]{6})/.exec(css);
  const pin = /const LOCAL_PIN_COLOR = '(#[0-9A-Fa-f]{6})'/.exec(app);
  assert.ok(tok && pin, "токен або константа зникли");
  assert.equal(tok[1].toLowerCase(), pin[1].toLowerCase());
});
