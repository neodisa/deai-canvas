import assert from "node:assert/strict";
import test from "node:test";
import { SEEN_MAX, arrived, baseline, isNew, markSeen, newsByPage, countNew, newsItems, readSeen, seenKey, teamOf, writeSeen } from "../app/comment-news.js";

test("seenKey: простір і задача; без простору — «-»", () => {
  assert.equal(seenKey("liga", "t1"), "dc-seen:liga:t1");
  assert.equal(seenKey(null, "t1"), "dc-seen:-:t1");
});

test("readSeen: сміття, чужа версія — null; не-рядки в ids відкидаються", () => {
  for (const raw of [null, "", "x{", '{"v":2,"ids":["a"]}', '{"v":1}', '{"v":1,"ids":"a"}']) assert.equal(readSeen(raw), null, String(raw));
  assert.deepEqual([...readSeen('{"v":1,"ids":["a",5,null,"b"]}')], ["a", "b"]);
});

test("writeSeen: лише останні SEEN_MAX; круговий обмін", () => {
  const ids = Array.from({ length: SEEN_MAX + 5 }, (_, i) => `i${i}`);
  const back = readSeen(writeSeen(new Set(ids)));
  assert.equal(back.size, SEEN_MAX);
  assert.equal(back.has("i0"), false);
  assert.equal(back.has("i4"), false);
  assert.equal(back.has("i5"), true);
  assert.equal(back.has(`i${SEEN_MAX + 4}`), true);
});

test("baseline: усі наявні id", () => {
  assert.deepEqual([...baseline([{ id: "a" }, { id: "b" }, null, { id: 3 }])], ["a", "b"]);
  assert.equal(baseline(null).size, 0);
});

test("markSeen: додає і переставляє наявний id в кінець; вхід не мутує", () => {
  const s0 = new Set(["a", "b"]);
  const s1 = markSeen(s0, ["a", "c", 7]);
  assert.deepEqual([...s1], ["b", "a", "c"]);
  assert.deepEqual([...s0], ["a", "b"]);
});

test("teamOf: лише _aud === project", () => {
  const l = [{ id: "a", _aud: "project" }, { id: "b", _aud: "local" }, { id: "c" }, null];
  assert.deepEqual(teamOf(l).map((c) => c.id), ["a"]);
  assert.deepEqual(teamOf(null), []);
});

test("isNew: відкритий, не мій, не бачений", () => {
  const seen = new Set(["old"]);
  const c = { id: "n", status: "open", author: "Автор А" };
  assert.equal(isNew(c, seen, "Автор Б"), true);
  assert.equal(isNew({ ...c, status: "resolved" }, seen, "Автор Б"), false, "закритий");
  assert.equal(isNew(c, seen, "Автор А"), false, "мій");
  assert.equal(isNew(c, seen, ""), true, "імені нема — «мого» нема");
  assert.equal(isNew({ ...c, id: "old" }, seen, "Автор Б"), false, "бачений");
  assert.equal(isNew(c, null, "Автор Б"), false, "маркера нема");
});

test("arrived: перший знімок — нічого; далі лише нові id", () => {
  assert.deepEqual(arrived(null, [{ id: "a" }]), []);
  assert.deepEqual(arrived(new Set(["a"]), [{ id: "a" }, { id: "b" }]).map((c) => c.id), ["b"]);
});

test("newsByPage: сторінка з тегу версії; «3» — main; без версії й url — пропуск", () => {
  const r = newsByPage([
    { meta: { version: "3/stattia" } }, { meta: { version: "3/stattia" } },
    { meta: { version: "3" } }, { meta: {} }, { meta: { version: "x" } },
  ]);
  assert.deepEqual(r, { stattia: 2, main: 1 });
});

test("Б2 ревʼю M3: newsByPage рахує все, що отримала — відбір «нових» робить виклик (isNew)", () => {
  const mixed = [
    { id: "n", status: "open", author: "А", meta: { version: "3/stattia" } },
    { id: "seen", status: "open", author: "А", meta: { version: "3/stattia" } },
    { id: "mine", status: "open", author: "Я", meta: { version: "3/stattia" } },
  ];
  const seen = new Set(["seen"]);
  assert.deepEqual(newsByPage(mixed), { stattia: 3 }, "без відбору — усі");
  assert.deepEqual(newsByPage(mixed.filter((c) => isNew(c, seen, "Я"))), { stattia: 1 });
});

test("countNew: рахує лише нові (відкриті, не мої, не бачені); не масив — 0", async () => {
  const { countNew } = await import("../app/comment-news.js");
  const items = [{ id: "a", status: "open", author: "x" }, { id: "b", status: "open", author: "me" },
    { id: "c", status: "resolved", author: "x" }, { id: "d", status: "open", author: "x" }];
  assert.equal(countNew(items, new Set(["d"]), "me"), 1);
  assert.equal(countNew(items, null, "me"), 0);
  assert.equal(countNew(null, new Set(), "me"), 0);
});

test("newsItems: командні коментарі + відповіді на ВІДКРИТІ коментарі будь-якого каналу", () => {
  const R = (id, o = {}) => ({ id, ts: "20.11.2026 10:00", author: "AI", text: "т", ...o });
  const all = [
    { id: "p1", _aud: "project", status: "open", author: "x", meta: { version: "3/a" }, replies: [R("rp")] },
    { id: "l1", status: "open", author: "Я", meta: { version: "3/b" }, replies: [R("rl", { author: "Я" }), { text: "без id" }, null] },
    { id: "l2", status: "resolved", author: "Я", replies: [R("rc")] },
    { id: "l3", status: "open", author: "Я" },
  ];
  const items = newsItems(all);
  assert.deepEqual(items.map((i) => i.id), ["p1", "rp", "rl", "rc"], "відповіді закритого — теж у списку (для бази «бачив»), без відповідей — нічого; без id пропущено");
  assert.equal(items.find((i) => i.id === "rc").status, "resolved", "відповідь закритого несе статус батька");
  assert.equal(isNew(items.find((i) => i.id === "rc"), new Set(), "Хтось"), false, "відповідь закритого не нова");
  assert.equal(countNew(items, new Set(), "Хтось"), 3, "закрита не рахується (p1, rp, rl)");
  assert.deepEqual(items.find((i) => i.id === "rl"), { id: "rl", ts: "20.11.2026 10:00", author: "Я", status: "open", version: "3/b", parent: "l1" });
  assert.equal(items.find((i) => i.id === "rp").parent, "p1");
  assert.equal(items.find((i) => i.id === "rp").version, "3/a");
  assert.equal(newsItems(null).length, 0);
  assert.equal(newsItems([{ id: "x", status: "open", replies: [R("y")] }])[0].version, undefined, "нема meta — version undefined, без падіння");
});

test("newsItems + isNew/countNew: власна відповідь не нова; чужа — нова, доки не бачена", () => {
  const all = [{ id: "l1", status: "open", author: "Я", replies: [
    { id: "mine", author: "Я", ts: "t" }, { id: "ai", author: "AI", ts: "t" }] }];
  const items = newsItems(all);
  assert.equal(isNew(items.find((i) => i.id === "mine"), new Set(), "Я"), false);
  assert.equal(isNew(items.find((i) => i.id === "ai"), new Set(), "Я"), true);
  assert.equal(countNew(items, new Set(), "Я"), 1);
  assert.equal(countNew(items, new Set(["ai"]), "Я"), 0);
  assert.deepEqual([...baseline(items)], ["mine", "ai"]);
  assert.deepEqual(arrived(new Set(["mine"]), items).map((i) => i.id), ["ai"]);
});

test("newsItems: закритий коментар відкрили знову — його давні відповіді не стають «новими» (їх покрила база «бачив»)", () => {
  const R = (id) => ({ id, ts: "t", author: "AI" });
  const closed = [{ id: "c1", status: "resolved", author: "Я", replies: [R("old1"), R("old2")] }];
  const seen = baseline(newsItems(closed));                      // перший знімок: коментар закритий
  assert.deepEqual([...seen].sort(), ["old1", "old2"]);
  const reopened = [{ id: "c1", status: "open", author: "Я", replies: [R("old1"), R("old2"), R("fresh")] }];
  const news = newsItems(reopened);
  assert.deepEqual(news.filter((c) => isNew(c, seen, "Я")).map((c) => c.id), ["fresh"], "давні відповіді стали новими після відкриття");
});
