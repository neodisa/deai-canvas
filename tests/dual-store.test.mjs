import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

/* Файл — класичний скрипт (`window.DeaiDualStore`), як `local-adapter.js`: вантажимо у пісочницю з `window`. */
function load(timers = { setTimeout, clearTimeout }) {
  const win = {};
  vm.runInNewContext(readFileSync(new URL("../app/vendor/dual-store.js", import.meta.url), "utf8"), { window: win, setTimeout: timers.setTimeout, clearTimeout: timers.clearTimeout });
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

test("команда здала ready, але з loadError (збій першого читання) — teamDown, команду закрито, локальні піни на місці", async () => {
  for (const timers of [undefined, { setTimeout: undefined, clearTimeout: undefined }]) {
    const L = fake([P("l1")]), T = fake([]);
    T.store.loadError = "402";
    const d = (timers ? load(timers) : load())({ local: L.store, team: T.store });
    await d.ready;
    assert.equal(d.teamDown, "402", timers ? "без таймерів" : "з таймером");
    assert.deepEqual(plain(d.load().map((c) => c.id)), ["l1"]);
    assert.ok(T.log.some((e) => e[0] === "close"));
  }
  const L = fake([P("l1")]), T = fake([P("t1")]);
  T.store.loadError = null;
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  assert.equal(d.teamDown, null, "здорова команда не відключається");
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

test("відхилений командний запис повторюється при наступному save, навіть без змін командної частини (teamDirty)", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  let fail = true;
  const orig = T.store.save;
  T.store.save = (list) => (fail ? (T.log.push(["save-fail"]), Promise.reject(new Error("мережа"))) : orig(list));
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  const list = d.load().map((c) => ({ ...c }));
  list.push({ ...P("n1"), _aud: "project" });
  await assert.rejects(d.save(list));
  fail = false;
  const next = d.load().map((c) => (c.id === "l1" ? { ...c, text: "інше" } : { ...c }));   // змінено лише локальне
  await d.save(next);
  assert.deepEqual(plain(T.log.at(-1)[1].map((c) => c.id)), ["t1", "n1"], "командний запис повторено");
  const n = T.log.length;
  await d.save(d.load().map((c) => ({ ...c })));
  assert.equal(T.log.length, n, "після успіху повторів нема");
});

test("синхронний кидок під-сховища стає відмовою; прапорець повтору лишається", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  let boom = true;
  const orig = T.store.save;
  T.store.save = (list) => { if (boom) throw new Error("синхронно"); return orig(list); };
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  const list = d.load().map((c) => ({ ...c }));
  list.push({ ...P("n1"), _aud: "project" });
  await assert.rejects(d.save(list), /синхронно/);
  boom = false;
  await d.save(d.load().map((c) => ({ ...c })));
  assert.deepEqual(plain(T.log.at(-1)[1].map((c) => c.id)), ["t1", "n1"]);
  const L2 = fake([P("l1")]);
  L2.store.save = () => { throw new Error("локальне впало"); };
  const d2 = load()({ local: L2.store, team: null, teamDown: "x" });
  await d2.ready;
  await assert.rejects(d2.save([{ ...P("l1"), text: "z" }]), /локальне впало/);
});

test("teamDirty: пізній успіх СТАРОГО командного запису не знімає відмову новішого (teamSeq)", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  const defers = [];
  const orig = T.store.save;
  T.store.save = (list) => { T.log.push(["save", list.map((c) => ({ ...c }))]); return new Promise((res, rej) => defers.push({ res, rej })); };
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  const base = d.load().map((c) => ({ ...c }));
  const a = d.save([...base, { ...P("n1"), _aud: "project" }]);                       // A у польоті
  const b = d.save([...base, { ...P("n1"), _aud: "project" }, { ...P("n2"), _aud: "project" }]);   // B у польоті
  defers[1].rej(new Error("мережа"));
  await assert.rejects(b);
  defers[0].res();
  await a;                                                                              // повільний A завершився успіхом
  const n = T.log.length;
  T.store.save = orig;
  const next = d.load().map((c) => ({ ...c }));                                         // командна частина — та сама
  await d.save(next);
  assert.equal(T.log.length, n + 1, "запис B повторено");
  assert.deepEqual(plain(T.log.at(-1)[1].map((c) => c.id)), ["t1", "n1", "n2"]);
});

const never = () => new Promise(() => {});
const closes = (T) => T.log.filter((e) => e[0] === "close").length;

test("завислий ready командного не ховає локальних: тайм-аут → teamDown, команду закрито раз, load — лише локальне", { timeout: 2000 }, async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  T.store.ready = never();
  const d = load()({ local: L.store, team: T.store, teamTimeoutMs: 20 });
  await d.ready;
  assert.match(d.teamDown, /did not answer/);
  assert.equal(closes(T), 1);
  assert.deepEqual(plain(d.load().map((c) => c.id)), ["l1"]);
});

test("команда відповіла ПІСЛЯ тайм-ауту: лишається вимкненою, close не вдруге, необроблених відмов нема", { timeout: 2000 }, async () => {
  const bad = [];
  const spy = (e) => bad.push(e);
  process.on("unhandledRejection", spy);
  try {
    for (const late of ["resolve", "reject"]) {
      const L = fake([P("l1")]), T = fake([P("t1")]);
      let fin; T.store.ready = new Promise((res, rej) => { fin = late === "resolve" ? res : () => rej(new Error("пізно")); });
      const d = load()({ local: L.store, team: T.store, teamTimeoutMs: 20 });
      await d.ready;
      fin();
      await new Promise((r) => setTimeout(r, 30));
      assert.match(d.teamDown, /did not answer/, late);
      assert.equal(closes(T), 1, late);
      assert.deepEqual(plain(d.load().map((c) => c.id)), ["l1"], late);
    }
    assert.deepEqual(bad, []);
  } finally { process.off("unhandledRejection", spy); }
});

test("команда готова до тайм-ауту: не вимкнена, таймер знято", { timeout: 2000 }, async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  const live = new Set();                                                       // таймери, що ще чекають
  const d = load({
    setTimeout: (f, ms) => { const h = setTimeout(f, ms); live.add(h); return h; },
    clearTimeout: (h) => { live.delete(h); clearTimeout(h); },
  })({ local: L.store, team: T.store, teamTimeoutMs: 60000 });
  await d.ready;
  assert.equal(live.size, 0, "таймер тайм-ауту знято, коли команда відповіла першою");
  assert.equal(d.teamDown, null);
  assert.equal(closes(T), 0);
  assert.deepEqual(plain(d.load().map((c) => c.id)), ["l1", "t1"]);
});

test("close(), потім пізня відмова готовності команди: team.close рівно раз", { timeout: 2000 }, async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  let rej; T.store.ready = new Promise((_, r) => { rej = r; });
  const d = load()({ local: L.store, team: T.store, teamTimeoutMs: 60000 });
  d.close();
  rej(new Error("пізно"));
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(closes(T), 1);
});

/* ---------- Відповіді (0.35) ---------- */
test("зміна лише replies пишеться в потрібне під-сховище за _aud, інше не чіпає", async () => {
  const L = fake([P("l1")]), T = fake([P("t1")]);
  const d = load()({ local: L.store, team: T.store });
  await d.ready;
  const r = { id: "r1", author: "a", text: "відп", ts: "20.11.2026 10:00" };
  let list = d.load().map((c) => (c.id === "t1" ? { ...c, replies: [r] } : { ...c }));
  await d.save(list);
  assert.equal(L.log.filter((e) => e[0] === "save").length, 0, "локальне не мало писатись");
  assert.deepEqual(plain(T.log.at(-1)[1][0].replies), [r]);
  list = d.load().map((c) => (c.id === "l1" ? { ...c, replies: [r] } : { ...c }));
  const tn = T.log.length;
  await d.save(list);
  assert.deepEqual(plain(L.log.at(-1)[1][0].replies), [r]);
  assert.equal(T.log.length, tn, "командне не мало писатись");
});

test("repliesDown: null без команди; null при teamDown; пропускає team.repliesDown", async () => {
  const L = fake();
  const none = load()({ local: L.store });
  assert.equal(none.repliesDown, null);
  const down = load()({ local: L.store, teamDown: "VPN" });
  assert.equal(down.teamDown, "VPN");
  assert.equal(down.repliesDown, null);
  const T = fake();
  T.store.repliesDown = "модуль без відповідей";
  const d = load()({ local: L.store, team: T.store });
  assert.equal(d.repliesDown, "модуль без відповідей");
  assert.equal(Object.keys(d).includes("repliesDown"), true, "enumerable");
  T.store.repliesDown = "";
  assert.equal(d.repliesDown, null);
  T.store.repliesDown = 5;
  assert.equal(d.repliesDown, null);
  T.store.repliesDown = "x";
  await d.ready;
  d.close();                                    // команда знята — причини нема
  assert.equal(d.repliesDown, null);
});

test("supportsReplies: local так; project лише з team.supportsReplies === true; інше — ні", async () => {
  const L = fake();
  const T = fake();
  const d = load()({ local: L.store, team: T.store });
  assert.equal(d.supportsReplies("local"), true);
  assert.equal(d.supportsReplies("project"), false, "прапора нема");
  T.store.supportsReplies = "yes";
  assert.equal(d.supportsReplies("project"), false, "не строго true");
  T.store.supportsReplies = true;
  assert.equal(d.supportsReplies("project"), true);
  assert.equal(d.supportsReplies("other"), false);
  assert.equal(d.supportsReplies(undefined), false);
  const noTeam = load()({ local: L.store });
  assert.equal(noTeam.supportsReplies("project"), false);
  assert.equal(noTeam.supportsReplies("local"), true);
});
