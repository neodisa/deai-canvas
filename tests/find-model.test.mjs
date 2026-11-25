import assert from "node:assert/strict";
import test from "node:test";
import { FIND_LIMIT, SKIP_SELECTORS, SKIP_TAGS, findInTexts } from "../app/find-model.js";

test("порожній запит і порожній вхід — без збігів", () => {
  assert.deepEqual(findInTexts(["abc"], ""), { hits: [], total: 0, capped: false });
  assert.deepEqual(findInTexts([], "a"), { hits: [], total: 0, capped: false });
});

test("без урахування регістру, кирилиця", () => {
  const r = findInTexts(["Пошук по ПОШУКУ"], "пошук");
  assert.deepEqual(r.hits, [{ i: 0, start: 0, end: 5 }, { i: 0, start: 9, end: 14 }]);
});

test("кілька вузлів: збіги з індексом вузла, у порядку документа", () => {
  const r = findInTexts(["one two", "", "two three", "none"], "two");
  assert.deepEqual(r.hits, [{ i: 0, start: 4, end: 7 }, { i: 2, start: 0, end: 3 }]);
  assert.equal(r.total, 2);
});

test("збіги не перекриваються", () => {
  assert.deepEqual(findInTexts(["aaaa"], "aa").hits, [{ i: 0, start: 0, end: 2 }, { i: 0, start: 2, end: 4 }]);
});

test("зсуви лишаються в оригіналі, коли нижній регістр змінює довжину (İ → i̇)", () => {
  const text = "xİy";
  const r = findInTexts([text], "y");
  assert.equal(text.slice(r.hits[0].start, r.hits[0].end), "y");
  const r2 = findInTexts([text], "x");
  assert.equal(text.slice(r2.hits[0].start, r2.hits[0].end), "x");
});

test("ліміт 1000: повертаємо перші 1000, capped=true, total — 1000", () => {
  const r = findInTexts(["a ".repeat(1500)], "a");
  assert.equal(FIND_LIMIT, 1000);
  assert.equal(r.hits.length, 1000);
  assert.equal(r.capped, true);
  assert.equal(r.total, 1000);
});

test("пропущені (null) вузли не зсувають індекси", () => {
  const r = findInTexts([null, "abc", undefined, "abc"], "b");
  assert.deepEqual(r.hits.map((h) => h.i), [1, 3]);
});

test("що пропускаємо при обході: теги й оверлеї (той самий перелік, що в «В Figma»)", () => {
  for (const tag of ["script", "style", "noscript", "template"]) assert.ok(SKIP_TAGS.has(tag), tag);
  for (const sel of ["[data-comment-layer]", "[data-deai-marks]", "[data-canvas-inspector]"]) assert.ok(SKIP_SELECTORS.includes(sel), sel);
});

test("кінець збігу береться з карти кінців, а не з довжини запиту: після İ зсув згорнутого рядка ≠ оригіналу", () => {
  const text = "İİxİ";
  const r = findInTexts([text], "x");
  assert.equal(r.hits.length, 1);
  assert.equal(text.slice(r.hits[0].start, r.hits[0].end), "x");
});
