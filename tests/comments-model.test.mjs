import assert from "node:assert/strict";
import test from "node:test";

import { FILTERS, assignedToClaude, audOf, commentSections, filterCounts, forClaude, matchQuery, openCount, repliesOf, shotSrc } from "../app/comments-model.js";

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

const A = (id, n, aud, o = {}) => ({ ...C({ id, n, ...o }), ...(aud ? { _aud: aud } : {}) });
const MIX = { comments: [A("l1", 1), A("l2", 2, "local"), A("p1", 3, "project"), A("p2", 4, "project", { status: "resolved" })] };

test("audOf: без _aud — локальний; assignedToClaude — лише meta.assignee === claude", () => {
  assert.equal(audOf({}), "local");
  assert.equal(audOf(null), "local");
  assert.equal(audOf({ _aud: "project" }), "project");
  assert.equal(audOf({ _aud: "чужий" }), "local");
  assert.equal(assignedToClaude({ meta: { assignee: "claude" } }), true);
  assert.equal(assignedToClaude({ meta: { assignee: "ann" } }), false);
  assert.equal(assignedToClaude({}), false);
  assert.deepEqual(FILTERS, ["local", "project", "all"], "порядок вкладок — рішення власника 16.11.2026");
});

const ASG = { comments: [...MIX.comments, A("p3", 5, "project", { meta: { assignee: "claude" } })] };

test("commentSections: «Для AI» = локальні + доручені командні; «Команда» — усі командні", () => {
  const ids = (f) => { const s = commentSections(ASG, { filter: f }); return [...s.open, ...s.closed].map((c) => c.id).sort(); };
  assert.deepEqual(ids("all"), ["l1", "l2", "p1", "p2", "p3"]);
  assert.deepEqual(ids("local"), ["l1", "l2", "p3"]);
  assert.deepEqual(ids("project"), ["p1", "p2", "p3"]);
  assert.equal(forClaude(A("x", 9, "project", { meta: { assignee: "claude" } })), true);
  assert.equal(forClaude(A("x", 9, "project")), false);
  assert.equal(forClaude(A("x", 9)), true);
});

test("filterCounts: відкриті поточні за правилом вкладки; fresh — відкриті нові командні; пошук не враховано", () => {
  const snap = { comments: [...ASG.comments, A("e1", 6, "project", { scope: "earlier" }), A("q", 7, "project")] };
  assert.deepEqual(filterCounts(snap, new Set(["q", "p2", "l1"])), { local: 3, project: 3, all: 5, fresh: { local: 0, project: 1 } });
  assert.deepEqual(filterCounts(snap), { local: 3, project: 3, all: 5, fresh: { local: 0, project: 0 } });
  assert.deepEqual(filterCounts(null), { local: 0, project: 0, all: 0, fresh: { local: 0, project: 0 } });
});

test("commentSections: «нові» не дублюються у «Відкритих»; закритий у fresh не потрапляє", () => {
  const s = commentSections(MIX, { fresh: new Set(["p1", "p2"]) });
  assert.deepEqual(s.fresh.map((c) => c.id), ["p1"]);
  assert.deepEqual(s.open.map((c) => c.id).sort(), ["l1", "l2"]);
  assert.deepEqual(s.closed.map((c) => c.id), ["p2"]);
  assert.deepEqual(commentSections(MIX).fresh, []);
});

test("commentSections: фільтр діє й на «нові»; openCount — усі адресати", () => {
  const s = commentSections(MIX, { fresh: new Set(["p1"]), filter: "local" });
  assert.deepEqual(s.fresh, []);
  assert.equal(openCount(MIX), 3);
});

test("Б2 ревʼю M5: локальний id у fresh не потрапляє в «Нові від команди»", () => {
  const s = commentSections(MIX, { fresh: new Set(["l1", "l2"]) });
  assert.deepEqual(s.fresh, []);
  assert.deepEqual(s.open.map((c) => c.id).sort(), ["l1", "l2", "p1"]);
});

/* ── Відповіді (0.34) ── */
const R = (id, ts, o = {}) => ({ id, author: "Автор Б", text: "відп", ts, ...o });
const withReplies = (id, n, aud, replies, o = {}) => ({ ...A(id, n, aud, o), replies });

test("matchQuery: знаходить коментар за текстом відповіді і за автором відповіді", () => {
  const c = withReplies("a", 1, undefined, [R("r1", "19.11.2026 12:05", { text: "Темніший синій", author: "Олена Т" })]);
  assert.equal(matchQuery(c, "темніший"), true);
  assert.equal(matchQuery(c, "олена"), true);
  assert.equal(matchQuery(c, "зеленіший"), false);
  assert.equal(matchQuery(A("b", 2), "темніший"), false);
});

test("repliesOf: за ts; стабільно для рівних хвилин; нерозібраний ts — порядок сховища; не обʼєкти відкидаються", () => {
  const c = { replies: [R("late", "20.11.2026 10:00"), R("e1", "19.11.2026 09:00"), R("e2", "19.11.2026 09:00"), null, "x"] };
  assert.deepEqual(repliesOf(c).map((r) => r.id), ["e1", "e2", "late"]);
  const bad = { replies: [R("b", "20.11.2026 10:00"), R("a", "сміття"), R("c", "19.11.2026 09:00")] };
  assert.deepEqual(repliesOf(bad).map((r) => r.id), ["b", "a", "c"]);
  assert.deepEqual(repliesOf({}), []);
  assert.deepEqual(repliesOf(null), []);
  assert.deepEqual(repliesOf({ replies: "x" }), []);
});

test("commentSections: нова відповідь робить коментар свіжим — і локальний теж (відповідь AI)", () => {
  const snap = { comments: [
    withReplies("l1", 1, undefined, [R("rn", "20.11.2026 10:00", { agent: true, author: "AI" })]),
    withReplies("p1", 2, "project", [R("rp", "20.11.2026 10:01")]),
    withReplies("l2", 3, undefined, [R("old", "20.11.2026 10:02")]),
    withReplies("l3", 4, undefined, [R("rn2", "20.11.2026 10:03")], { status: "resolved" }),
  ] };
  const s = commentSections(snap, { fresh: new Set(["rn", "rp", "rn2"]) });
  assert.deepEqual(s.fresh.map((c) => c.id).sort(), ["l1", "p1"], "закритий з новою відповіддю — не свіжий");
  assert.deepEqual(s.open.map((c) => c.id), ["l2"]);
  assert.deepEqual(commentSections(snap, { fresh: new Set(["rn"]), filter: "project" }).fresh, [], "фільтр діє й на свіжі");
  assert.deepEqual(commentSections(snap, { fresh: new Set(["l1"]) }).fresh, [], "id локального коментаря сам по собі не свіжить");
});

test("filterCounts.fresh: {local, project} — свіжі відкриті за фільтром кожної вкладки", () => {
  const snap = { comments: [
    withReplies("l1", 1, undefined, [R("rl", "20.11.2026 10:00")]),
    A("p1", 2, "project"),
    withReplies("p2", 3, "project", [R("rp", "20.11.2026 10:00")], { meta: { assignee: "claude" } }),
    withReplies("p3", 4, "project", [R("rq", "20.11.2026 10:00")]),
  ] };
  assert.deepEqual(filterCounts(snap, new Set(["rl", "p1", "rp", "rq"])).fresh, { local: 2, project: 3 });
  assert.deepEqual(filterCounts(snap, new Set(["rl"])).fresh, { local: 1, project: 0 });
});
