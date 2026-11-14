import assert from "node:assert/strict";
import test from "node:test";
import { SEEN_MAX, arrived, baseline, isNew, markSeen, newsByPage, readSeen, seenKey, teamOf, writeSeen } from "../app/comment-news.js";

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
