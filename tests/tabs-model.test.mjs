import assert from "node:assert/strict";
import test from "node:test";
import {
  TABS_MAX, readTabs, writeTabs, upsertTab, closeTab, pruneTabs, tabsModel,
} from "../app/tabs-model.js";

const T = (id, extra = {}) => ({ id, title: `T ${id}`, space: "sp", color: "space-2", jira: null, ...extra });

test("readTabs: сміття, чужий формат, битий JSON — порожньо, без винятку", () => {
  for (const raw of [null, "", "{", "[]", '{"v":2,"tabs":[]}', '{"v":1}', '{"v":1,"tabs":{}}']) {
    assert.deepEqual(readTabs(raw), []);
  }
});

test("readTabs: відкидає записи без id, з неіснуючим кольором, дублі; обрізає довгі рядки", () => {
  const raw = JSON.stringify({ v: 1, tabs: [
    T("A"), { id: "" }, { title: "x" }, T("A"), T("B", { color: "red;position:fixed" }), T("C", { title: "x".repeat(500) }),
  ] });
  const out = readTabs(raw);
  assert.deepEqual(out.map((x) => x.id), ["A", "B", "C"]);
  assert.equal(out[1].color, null, "невідомий колір — null, а не рядок у style");
  assert.equal(out[2].title.length, 200);
});

test("writeTabs → readTabs — те саме", () => {
  const tabs = [T("A"), T("B", { space: null, color: null, jira: "LIGA-1" })];
  assert.deepEqual(readTabs(writeTabs(tabs)), tabs);
});

test("upsertTab: нова — в кінець; наявна — оновлюється на місці", () => {
  let tabs = upsertTab([], T("A"));
  tabs = upsertTab(tabs, T("B"));
  tabs = upsertTab(tabs, T("A", { title: "Нова назва" }));
  assert.deepEqual(tabs.map((x) => x.id), ["A", "B"]);
  assert.equal(tabs[0].title, "Нова назва");
});

test("upsertTab: понад TABS_MAX випадає найстаріша, але не та, що відкривається", () => {
  let tabs = [];
  for (let i = 0; i < TABS_MAX; i += 1) tabs = upsertTab(tabs, T(`T${i}`));
  tabs = upsertTab(tabs, T("NEW"));
  assert.equal(tabs.length, TABS_MAX);
  assert.equal(tabs[0].id, "T1");
  assert.equal(tabs.at(-1).id, "NEW");
});

test("closeTab: неактивна — next null; активна — правий сусід, інакше лівий, інакше home", () => {
  const tabs = [T("A"), T("B"), T("C")];
  assert.deepEqual(closeTab(tabs, "A", "C"), { tabs: [T("B"), T("C")], next: null });
  assert.equal(closeTab(tabs, "B", "B").next, "C");
  assert.equal(closeTab(tabs, "C", "C").next, "B");
  assert.equal(closeTab([T("A")], "A", "A").next, "home");
  assert.deepEqual(closeTab(tabs, "Z", "A"), { tabs, next: null }, "невідома — без змін");
});

test("pruneTabs: прибирає лише вкладки поточного простору, яких нема в списку", () => {
  const tabs = [T("A"), T("B"), T("X", { space: "other" })];
  assert.deepEqual(pruneTabs(tabs, "sp", ["A"]).map((x) => x.id), ["A", "X"]);
  assert.deepEqual(pruneTabs([T("A", { space: null })], null, []).map((x) => x.id), []);
});

test("tabsModel: активна лише поза оверлеєм; логотип/шестерня — за сторінкою; стан Claude за id або jira", () => {
  const tabs = [T("A"), T("B", { jira: "LIGA-9" })];
  const claude = { A: { state: "working" }, "LIGA-9": { state: "waiting" } };
  const m = tabsModel({ tabs, activeId: "A", homeOpen: false, homePage: "tasks", claude });
  assert.deepEqual(m.items.map((x) => [x.id, x.active, x.claude]), [["A", true, "working"], ["B", false, "waiting"]]);
  assert.equal(m.logoOn, false); assert.equal(m.gearOn, false);
  const h = tabsModel({ tabs, activeId: "A", homeOpen: true, homePage: "tasks", claude: null });
  assert.equal(h.items[0].active, false, "на «Задачах» жодна вкладка не активна");
  assert.equal(h.logoOn, true);
  assert.equal(tabsModel({ tabs, activeId: "A", homeOpen: true, homePage: "conn" }).gearOn, true);
  assert.equal(tabsModel({ tabs, activeId: "A", homeOpen: true, homePage: "wiz" }).logoOn, false);
});

test("tabsModel: невідомий стан Claude — без крапки, а не вигадана", () => {
  const m = tabsModel({ tabs: [T("A")], activeId: "A", claude: { A: { state: "weird" } } });
  assert.equal(m.items[0].claude, null);
});
