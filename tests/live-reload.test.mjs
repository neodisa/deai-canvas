/**
 * Автооновлення рамки (fb-01102026-309e3b): коли перезавантажувати макет, бо
 * його файли змінились на диску. Чиста функція кроку опитування.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { QUIET_MS, reloadStep } from "../app/live-reload.js";

const at = (state, stamp, now, held = false, it = "it1", page = "p") =>
  reloadStep(state, { it, page, stamp, now, held });

test("перше читання — лише запамʼятати, не перезавантажувати", () => {
  const r = at(null, 100, 0);
  assert.equal(r.action, "none");
  assert.equal(r.state.seen, 100);
});

test("зміна чекає тиші QUIET_MS, потім reload", () => {
  let s = at(null, 100, 0).state;
  let r = at(s, 200, 1000);            s = r.state; assert.equal(r.action, "none");
  r = at(s, 200, 1000 + QUIET_MS - 1); s = r.state; assert.equal(r.action, "none");
  r = at(s, 200, 1000 + QUIET_MS);     s = r.state; assert.equal(r.action, "reload");
  r = at(s, 200, 9999);                              assert.equal(r.action, "none", "один reload на зміну");
});

test("нова зміна під час очікування перезапускає тишу (Клод пише кількома записами)", () => {
  let s = at(null, 100, 0).state;
  s = at(s, 200, 1000).state;
  s = at(s, 300, 1000 + QUIET_MS - 10).state;
  assert.equal(at(s, 300, 1000 + QUIET_MS + 10).action, "none");
  assert.equal(at(s, 300, 1000 + QUIET_MS - 10 + QUIET_MS).action, "reload");
});

test("щось у руках (інспектор / коментар) → notice, а не reload", () => {
  let s = at(null, 100, 0).state;
  s = at(s, 200, 1000, true).state;
  assert.equal(at(s, 200, 1000 + QUIET_MS, true).action, "notice");
});

test("інша сторінка чи ітерація — нова база без дії", () => {
  let s = at(null, 100, 0).state;
  s = at(s, 200, 1000).state;
  const r = at(s, 200, 1000 + QUIET_MS, false, "it1", "q");
  assert.equal(r.action, "none");
  assert.equal(r.state.seen, 200);
});

test("відповідь без числа (сервер ліг) — нічого не міняє", () => {
  const s = at(null, 100, 0).state;
  const r = at(s, undefined, 5000);
  assert.equal(r.action, "none");
  assert.deepEqual(r.state, s);
});

test("shouldPollStamp: лише робочий вид, обрана ітерація, видима вкладка (ревʼю 1.47, W2–W3)", async () => {
  const { shouldPollStamp } = await import("../app/live-reload.js");
  assert.equal(shouldPollStamp({ mode: "work", picked: "it1", visible: true }), true);
  assert.equal(shouldPollStamp({ mode: "canvas", picked: "it1", visible: true }), false, "опитування в «Огляді»");
  assert.equal(shouldPollStamp({ mode: "work", picked: null, visible: true }), false);
  assert.equal(shouldPollStamp({ mode: "work", picked: "it1", visible: false }), false, "опитування схованої вкладки");
});

test("shouldPollStamp: під екраном «Задачі» рамка схована — не опитуємо (інакше плашка «макет змінився» пливе над екраном)", async () => {
  const { shouldPollStamp } = await import("../app/live-reload.js");
  assert.equal(shouldPollStamp({ mode: "work", picked: "it1", visible: true, home: true }), false);
  assert.equal(shouldPollStamp({ mode: "work", picked: "it1", visible: true, home: false }), true);
});
