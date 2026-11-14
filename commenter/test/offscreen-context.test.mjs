/**
 * Пін, чийого елемента зараз немає на екрані, каже ДЕ його шукати (fb-06102026-c38f46).
 *
 * У SPA (boss-interface, вітання кроками через @switch) піни стояли на кроках
 * «Ваш партнер» і «Додаткові компанії», сторінка відкривалась на кроці 1 — і
 * клік по картці мовчки нічого не робив. Підпис збирається з `meta.ctx`, який
 * пишеться при створенні піна (`captureContext`). DOM-половину стереже живий тест
 * design-canvas/tests/live/offscreen-pin.test.mjs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");
const m = src.match(/ {2}function ctxLine\([\s\S]*?\n {2}\}/);
assert.ok(m, "у comment-layer.js немає ctxLine — контекст піна нема кому підписати");
const ctxLine = new Function(`${m[0]}; return ctxLine;`)();

assert.equal(ctxLine({ heading: "Ваш партнер", active: ["Крок 2"] }), "«Крок 2» · розділ «Ваш партнер»");
assert.equal(ctxLine({ heading: "Ваш партнер", active: [] }), "розділ «Ваш партнер»");
assert.equal(ctxLine({ heading: "", active: ["Вкладка A", "Крок 3"] }), "«Вкладка A» · «Крок 3»");
assert.equal(ctxLine(null), "", "старий пін без контексту — без підпису, а не «undefined»");
assert.equal(ctxLine("сміття"), "");
assert.equal(ctxLine({ heading: "Х", active: "не масив" }), "розділ «Х»");
console.log("offscreen-context: ok");

/* TD-36: проєктний пін (не `appLocal`) не пише заголовок у контекст — він їде в
   Supabase, а ПІБ у заголовку не розпізнати. Проводку стережемо текстом. */
assert.match(src, /captureContext\(el, this\.target, \{ heading: this\.appLocal \|\| \(aud === 'local' && this\._formAuds\(\)\.length > 0\) \}\)/,
  "створення піна мусить передавати { heading: this.appLocal || (aud === 'local' && …) } — командний пін без заголовка");
assert.doesNotMatch(src, /heading: this\.appLocal \|\| this\._formAuds/,
  "командний пін (aud !== 'local') не пише заголовок: він їде в спільне сховище (TD-36)");
console.log("offscreen-context: проводка заголовка ok");
