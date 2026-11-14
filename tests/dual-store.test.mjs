import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

/* Файл — класичний скрипт (`window.DeaiDualStore`), як `local-adapter.js`: вантажимо у пісочницю з `window`. */
function load() {
  const win = {};
  vm.runInNewContext(readFileSync(new URL("../app/vendor/dual-store.js", import.meta.url), "utf8"), { window: win });
  return win.DeaiDualStore;
}
/* Обʼєкти з `vm`-контексту мають СВІЙ прототип: `deepStrictEqual` їх не зрівняє зі звичайними — порівнюємо копії. */
const plain = (x) => JSON.parse(JSON.stringify(x));
/** Фейкове під-сховище: тримає `cache`, пише журнал; `notifyOnSave` — як локальний адаптер (синхронно в `save`). */
function fake(rows = [], { notifyOnSave = false, shots = false } = {}) {
  const s = { cache: rows.map((r) => ({ ...r })), subs: [], log: [] };
  s.store = {
    ready: Promise.resolve(),
    load: () => s.cache,
    save: (list) => { s.log.push(["save", list.map((c) => ({ ...c }))]); s.cache = list.map((c) => ({ ...c })); if (notifyOnSave) s.subs.forEach((f) => f(s.cache)); return Promise.resolve(); },
    remove: (ids) => { s.log.push(["remove", ids]); s.cache = s.cache.filter((c) => !ids.includes(c.id)); return Promise.resolve(); },
    subscribe: (f) => s.subs.push(f),
    refresh: () => { s.log.push(["refresh"]); return Promise.resolve(); },
    close: () => s.log.push(["close"]),
  };
  if (shots) s.store.uploadShot = (id, d) => { s.log.push(["shot", id]); return Promise.resolve("https://x/" + id); };
  return s;
}
const P = (id, extra = {}) => ({ id, author: "a", text: "t", status: "open", fp: null, htmlSnapshot: null, meta: { seq: 1 }, bornV: 1, resolvedV: null, resolveReason: null, ts: "14.11.2026 10:00", ...extra });

test("load — обʼєднання з _aud на копіях; під-сховища свого _aud не бачать", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  assert.deepEqual(plain(d.load().map((c) => [c.id, c._aud])), [["l1", "local"], ["t1", "project"]]);
  assert.equal("_aud" in L.cache[0], false);
  assert.equal(d.teamDown, null);
});

test("save ділить за _aud, знімає _aud, без _aud — локальне; незмінна частина не пишеться", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  const list = d.load().map((c) => ({ ...c }));
  list.push({ ...P("n1"), _aud: "project" }, P("n2"));         // n2 без _aud → локальне
  await d.save(list);
  assert.deepEqual(plain(L.log.at(-1)[1].map((c) => c.id)), ["l1", "n2"]);
  assert.deepEqual(plain(T.log.at(-1)[1].map((c) => c.id)), ["t1", "n1"]);
  assert.equal(T.log.at(-1)[1].some((c) => "_aud" in c), false);
  const before = [L.log.length, T.log.length];
  await d.save(d.load().map((c) => ({ ...c })));               // нічого не змінилось
  assert.deepEqual(plain([L.log.length, T.log.length]), before);
});

test("тінь командної частини: синхронне сповіщення локального не відкочує щойно змінений командний пін", async () => {
  const L = fake([P("l1")], { notifyOnSave: true }), T = fake([P("t1")]);   // командне після save НЕ сповіщає
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  let seen = null;
  d.subscribe((u) => { seen = u; });
  const list = d.load().map((c) => ({ ...c }));
  list[0] = { ...list[0], text: "змінено локально" };
  list[1] = { ...list[1], meta: { seq: 1, assignee: "claude" } };
  await d.save(list);
  assert.equal(seen.find((c) => c.id === "t1").meta.assignee, "claude");
});

test("remove — туди, де пін живе; невідомий id — в обидва", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  await d.remove(["t1"]);
  assert.deepEqual(plain(T.log.at(-1)), ["remove", ["t1"]]);
  assert.equal(L.log.some((e) => e[0] === "remove"), false);
  await d.remove(["x9"]);
  assert.deepEqual(plain([L.log.at(-1), T.log.at(-1)]), [["remove", ["x9"]], ["remove", ["x9"]]]);
});

test("скріншот у командне сховище — лише для командного піна (поправка 5)", async () => {
  const L = fake(), T = fake([], { shots: true });
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  assert.equal(await d.uploadShot("a", "data:image/jpeg;base64,AA", { _aud: "local" }), null);
  assert.equal(await d.uploadShot("a", "data:image/jpeg;base64,AA"), null);
  assert.equal(await d.uploadShot("b", "data:image/jpeg;base64,AA", { _aud: "project" }), "https://x/b");
  assert.deepEqual(plain(T.log.filter((e) => e[0] === "shot")), [["shot", "b"]]);
});

test("командного нема: локальне працює, teamDown — причина, командний запис відмовляє", async () => {
  const L = fake([P("l1")]);
  const d = load()({ local: L.store, team: null, teamDown: "адаптер не завантажився" });
  await d.ready;
  assert.equal(d.teamDown, "адаптер не завантажився");
  assert.deepEqual(plain(d.load().map((c) => c.id)), ["l1"]);
  const list = d.load().map((c) => ({ ...c, text: "змінено" }));
  list.push({ ...P("n1"), _aud: "project" });
  await assert.rejects(d.save(list));
  assert.deepEqual(plain(L.log.at(-1)[1].map((c) => [c.id, c.text])), [["l1", "змінено"]]);   // локальна частина записана попри відмову
});

test("команда впала на ready — teamDown, під-сховище закрите, далі лише локальне", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  T.store.ready = Promise.reject(new Error("сервіс не відповів"));
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  assert.equal(d.teamDown, "сервіс не відповів");
  assert.deepEqual(plain(d.load().map((c) => c.id)), ["l1"]);
  assert.ok(T.log.some((e) => e[0] === "close"));
});

test("сповіщення будь-якого під-сховища — свіже обʼєднання; refresh і close — обом", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  let got = null;
  d.subscribe((u) => { got = u.map((c) => c.id + ":" + c._aud); });
  T.cache = [P("t1"), P("t2")]; T.subs.forEach((f) => f(T.cache));
  assert.deepEqual(plain(got), ["l1:local", "t1:project", "t2:project"]);
  await d.refresh();
  await d.refreshLocal();                                     // лише локальне: командне — це трафік
  d.close();
  assert.deepEqual(plain([L.log.filter((e) => e[0] !== "save").map((e) => e[0]), T.log.map((e) => e[0])]),
    [["refresh", "refresh", "close"], ["refresh", "close"]]);
});
