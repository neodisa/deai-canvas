/**
 * Охоронець латки 0.27.1. У 0.27.0 кнопки шапки панелі мали клас `icon-btn`, якого не було в `app/styles.css`, — браузер
 * намалював свої світлі кнопки на темній панелі. Ні ревʼю, ні живі тести цього не бачили: вони перевіряють поведінку.
 * Тут — статично: кожен клас із розмітки `app/comments-view.js` має селектор у `app/styles.css`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { classesIn, css, hasRule } from "./_css-classes.mjs";

const view = readFileSync(new URL("../app/comments-view.js", import.meta.url), "utf8");
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

const OPTS = { dynamic: DYNAMIC, quoted: "cmt-[\\w-]+|icob|insp-[\\w-]+|panel-title" };

test("кожен клас розмітки панелі коментарів має правило в styles.css", () => {
  const missing = [...classesIn(view, OPTS)].filter((c) => !NO_STYLE.has(c) && !hasRule(c)).sort();
  assert.deepEqual(missing, [], `класи без стилю: ${missing.join(", ")}`);
});

test("перелік винятків не гниє: кожен виняток справді вживається і справді без стилю", () => {
  const used = classesIn(view, OPTS);
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
