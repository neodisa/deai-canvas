import assert from "node:assert/strict";
import test from "node:test";
import { applyRecentTitles, pruneRenamed } from "../app/recent-titles.js";

const task = { id: "a", title: "Стара" };
const list = { current: "a", tasks: [{ id: "a", title: "Стара" }, { id: "b", title: "B" }] };

test("перейменування ПІСЛЯ початку запитів перекриває стару відповідь — і в задачі, і в списку", () => {
  const m = new Map([["a", { title: "Нова", at: 200 }]]);
  const r = applyRecentTitles(task, list, m, 100);
  assert.equal(r.task.title, "Нова");
  assert.equal(r.list.tasks[0].title, "Нова");
  assert.equal(r.list.tasks[1].title, "B", "чужу задачу чіпати не можна");
  assert.equal(task.title, "Стара", "вхід мутовано");
});

test("перейменування ДО початку запитів ігнорується: сервер його вже знає, тінь не постійна", () => {
  const m = new Map([["a", { title: "Нова", at: 50 }]]);
  const r = applyRecentTitles(task, list, m, 100);
  assert.equal(r.task.title, "Стара");
  assert.equal(r.list.tasks[0].title, "Стара");
});

test("порожня назва в мапі не губиться, а нема запису — без змін; null/без tasks не падає", () => {
  assert.equal(applyRecentTitles(task, list, new Map(), 0).task, task);
  assert.equal(applyRecentTitles(null, null, new Map([["a", { title: "x", at: 9 }]]), 0).task, null);
  assert.deepEqual(applyRecentTitles(task, {}, new Map(), 0).list, {});
});

test("pruneRenamed прибирає записи старші за хвилину", () => {
  const m = new Map([["a", { title: "x", at: 0 }], ["b", { title: "y", at: 100000 }]]);
  pruneRenamed(m, 100500);
  assert.deepEqual([...m.keys()], ["b"]);
});
