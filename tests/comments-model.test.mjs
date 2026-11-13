import assert from "node:assert/strict";
import test from "node:test";

import { commentSections, matchQuery, openCount, shotSrc } from "../app/comments-model.js";

const C = (o) => ({ id: o.id, n: o.n, text: o.text || "", author: o.author || "Автор А", ts: o.ts || "",
  status: o.status || "open", scope: o.scope || "current", where: "here", meta: o.meta || {} });
const SNAP = { version: "3", iteration: "3", comments: [
  C({ id: "a", n: 1, text: "Кнопка ширша" }),
  C({ id: "b", n: 3, text: "Відступ зверху", author: "Автор Б" }),
  C({ id: "c", n: 2, text: "Старе", scope: "earlier" }),
  C({ id: "d", n: 4, text: "Готово раніше", status: "resolved", meta: { resolvedAt: 100 } }),
  C({ id: "e", n: 5, text: "Готово пізніше", status: "resolved", meta: { resolvedAt: 200 } }),
  C({ id: "f", n: 6, text: "Чужа ітерація закрита", status: "resolved", scope: "earlier" }),
  C({ id: "g", n: 7, text: "Інше", scope: "other" }),
] };

test("розділи: відкриті й попередні — новіші вгорі, закриті — за часом закриття", () => {
  const s = commentSections(SNAP);
  assert.deepEqual(s.open.map((c) => c.id), ["b", "a"]);
  assert.deepEqual(s.earlier.map((c) => c.id), ["c"]);
  assert.deepEqual(s.closed.map((c) => c.id), ["e", "d"]);
});

test("пошук: #N — точний номер, інакше підрядок без регістру по номеру, тексту, автору, часу, цитаті", () => {
  assert.deepEqual(commentSections(SNAP, { query: "#3" }).open.map((c) => c.id), ["b"]);
  assert.deepEqual(commentSections(SNAP, { query: "#30" }).open, []);
  assert.deepEqual(commentSections(SNAP, { query: "автор б" }).open.map((c) => c.id), ["b"]);
  assert.equal(matchQuery(C({ n: 9, meta: { sel: "Купити зараз" } }), "купити"), true);
  assert.equal(matchQuery(C({ n: 9 }), "   "), true);
});

test("лічильник — відкриті поточні, без пошуку; порожній знімок — нуль", () => {
  assert.equal(openCount(SNAP), 2);
  assert.equal(openCount(null), 0);
  assert.equal(openCount({ comments: "зламано" }), 0);
});

test("мініатюра — лише data:image і http(s)", () => {
  assert.equal(shotSrc({ meta: { shot: "data:image/png;base64,AAA" } }), "data:image/png;base64,AAA");
  assert.equal(shotSrc({ meta: { shotUrl: "https://x.example/s.png" } }), "https://x.example/s.png");
  assert.equal(shotSrc({ meta: { shot: "javascript:alert(1)" } }), null);
  assert.equal(shotSrc({ meta: { shot: "data:text/html;base64,AAA" } }), null);
  assert.equal(shotSrc({}), null);
});

test("#1 не збігається з #12", () => {
  assert.equal(matchQuery(C({ n: 12 }), "#1"), false);
  assert.equal(matchQuery(C({ n: 1 }), "#1"), true);
});

test("закриті без resolvedAt — за номером спаданням", () => {
  const snap = { comments: [C({ id: "p", n: 1, status: "resolved" }), C({ id: "q", n: 5, status: "resolved" }),
    C({ id: "r", n: 3, status: "resolved", meta: { resolvedAt: 50 } })] };
  assert.deepEqual(commentSections(snap).closed.map((c) => c.id), ["r", "q", "p"]);
});

test("мініатюра: shotUrl без shot; svg, //host і javascript: відхиляються", () => {
  assert.equal(shotSrc({ meta: { shotUrl: "http://x.example/a.png" } }), "http://x.example/a.png");
  assert.equal(shotSrc({ meta: { shot: "data:image/svg+xml;base64,AAA" } }), null);
  assert.equal(shotSrc({ meta: { shotUrl: "//host/x" } }), null);
  assert.equal(shotSrc({ meta: { shotUrl: "javascript:alert(1)" } }), null);
});
