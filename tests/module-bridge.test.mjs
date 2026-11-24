/* Міст панелі модуля (app/module-kit/bridge.js): класичний скрипт у фальшивому вікні (node:vm). */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";
import { METHOD_PERM } from "../app/page-rules.js";

const SRC = readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "module-kit", "bridge.js"), "utf8");

/* Об'єкти з vm-контексту мають інші прототипи: порівнюємо їх як дані. */
const plain = (x) => JSON.parse(JSON.stringify(x));

function load() {
  const sent = [];
  const listeners = [];
  const keydowns = [];
  const parent = { postMessage: (msg, target) => sent.push({ msg, target }) };
  const style = { props: {}, setProperty(k, v) { this.props[k] = v; } };
  const documentElement = { dataset: {}, style };
  const timers = [];
  const win = {
    parent,
    setTimeout: (fn, ms) => { timers.push({ fn, ms, cleared: false }); return timers.length - 1; },
    clearTimeout: (h) => { if (timers[h]) timers[h].cleared = true; },
    document: { documentElement },
    addEventListener: (type, fn) => { if (type === "message") listeners.push(fn); else if (type === "keydown") keydowns.push(fn); },
  };
  win.window = win;
  vm.runInNewContext(SRC, win);
  const dispatch = (data, source = parent) => listeners.forEach((fn) => fn({ data, source }));
  return { win, sent, dispatch, parent, documentElement, style, timers, keydowns };
}

test("hello is sent on load", () => {
  const { sent } = load();
  assert.equal(sent.length, 1);
  assert.deepEqual(plain(sent[0].msg), { deai: 1, id: 1, method: "hello", args: [] });
  assert.equal(sent[0].target, "*");
});

test("requests are correlated by id", async () => {
  const { win, sent, dispatch } = load();
  const a = win.deai.context();
  const b = win.deai.call("fn", { x: 1 });
  const [ma, mb] = [sent[1].msg, sent[2].msg];
  assert.deepEqual([ma.method, mb.method], ["context", "call"]);
  assert.deepEqual(plain(mb.args), ["fn", { x: 1 }]);
  assert.notEqual(ma.id, mb.id);
  dispatch({ deai: 1, re: mb.id, ok: true, value: "B" });
  dispatch({ deai: 1, re: ma.id, ok: true, value: "A" });
  assert.equal(await a, "A");
  assert.equal(await b, "B");
});

test("selection is a promise, toast and close are fire-and-forget", () => {
  const { win, sent } = load();
  assert.equal(typeof win.deai.selection().then, "function");
  assert.equal(win.deai.toast("hi"), undefined);
  assert.equal(win.deai.close(), undefined);
  const last = sent.slice(-2).map((s) => s.msg);
  assert.deepEqual(plain([last[0].method, last[0].args, last[1].method]), ["toast", ["hi"], "close"]);
  assert.equal(new Set(sent.map((s) => s.msg.id)).size, sent.length);
});

test("an error reply rejects with code and detail", async () => {
  const { win, sent, dispatch } = load();
  const p = win.deai.call("f", []);
  dispatch({ deai: 1, re: sent[1].msg.id, ok: false, error: "bad-input", detail: "no good" });
  await assert.rejects(p, (e) => e.name === "Error" && e.message === "no good" && e.code === "bad-input");
  const q = win.deai.call("f", []);
  dispatch({ deai: 1, re: sent[2].msg.id, ok: false, error: "boom" });
  await assert.rejects(q, (e) => e.message === "boom" && e.code === "boom");
});

test("a reply is consumed once", async () => {
  const { win, sent, dispatch } = load();
  const p = win.deai.context();
  const id = sent[1].msg.id;
  dispatch({ deai: 1, re: id, ok: true, value: 1 });
  dispatch({ deai: 1, re: id, ok: true, value: 2 });
  assert.equal(await p, 1);
});

test("events: subscribe, unsubscribe, a throwing subscriber does not block others", () => {
  const { win, dispatch } = load();
  const got = [];
  const off1 = win.deai.on("tick", () => { throw new Error("x"); });
  const off2 = win.deai.on("tick", (d) => got.push(d));
  dispatch({ deai: 1, event: "tick", data: 1 });
  assert.deepEqual(plain(got), [1]);
  off2();
  dispatch({ deai: 1, event: "tick", data: 2 });
  assert.deepEqual(got, [1]);
  off1();
  assert.equal(typeof off1, "function");
});

test("init and theme apply a validated theme and vars", () => {
  const { dispatch, documentElement, style } = load();
  dispatch({
    deai: 1, event: "init",
    data: {
      theme: "dark-x", vars: {
        "--s1": "#123", "--ok-name-2": "red", "bad": "x", "--Upper": "x", "--a b": "x",
        "--long": "y".repeat(201), "--num": 5, "--max": "z".repeat(200), ["--" + "a".repeat(61)]: "x",
      },
    },
  });
  assert.equal(documentElement.dataset.theme, "dark-x");
  assert.deepEqual(plain(style.props), { "--s1": "#123", "--ok-name-2": "red", "--max": "z".repeat(200) });
  dispatch({ deai: 1, event: "theme", data: { theme: "light", vars: { "--s1": "#fff" } } });
  assert.equal(documentElement.dataset.theme, "light");
  assert.equal(style.props["--s1"], "#fff");
});

test("a bad theme is ignored", () => {
  const { dispatch, documentElement } = load();
  for (const t of ["Dark", "a".repeat(21), "x y", 5, "", "d4rk", null]) {
    dispatch({ deai: 1, event: "theme", data: { theme: t } });
  }
  assert.equal(documentElement.dataset.theme, undefined);
});

test("messages from other sources or without deai:1 are ignored", async () => {
  const { win, sent, dispatch } = load();
  const p = win.deai.context();
  const seen = [];
  win.deai.on("e", (d) => seen.push(d));
  const id = sent[1].msg.id;
  dispatch({ deai: 1, re: id, ok: true, value: "evil" }, {});
  dispatch({ deai: 1, event: "e", data: "evil" }, null);
  dispatch({ deai: 1, event: "theme", data: { theme: "evil" } }, {});
  dispatch({ deai: 2, re: id, ok: true, value: "evil" });
  dispatch({ re: id, ok: true, value: "evil" });
  dispatch(null);
  dispatch("deai");
  assert.deepEqual(seen, []);
  dispatch({ deai: 1, re: id, ok: true, value: "good" });
  assert.equal(await p, "good");
});

test("ready resolves on init with its data", async () => {
  const { win, dispatch } = load();
  let done = false;
  win.deai.ready.then(() => { done = true; });
  dispatch({ deai: 1, event: "theme", data: {} });
  await Promise.resolve();
  assert.equal(done, false);
  dispatch({ deai: 1, event: "init", data: { theme: "dark", vars: {}, context: { task: "t1" } } });
  assert.deepEqual(plain(await win.deai.ready), { theme: "dark", vars: {}, context: { task: "t1" } });
});

test("no module syntax: a classic script", () => {
  assert.doesNotMatch(SRC, /^\s*(import|export)\s/m);
  assert.match(SRC, /"use strict"/);
});

test("імена-пастки (__proto__, constructor…) не чіпають прототип: ні в re, ні в подіях", () => {
  const { win, dispatch } = load();
  const got = [];
  win.deai.on("__proto__", (d) => got.push(["proto", d]));
  win.deai.on("constructor", (d) => got.push(["ctor", d]));
  for (const re of ["__proto__", "constructor", "hasOwnProperty", "toString"]) {
    dispatch({ deai: 1, re, ok: true, value: 1 });
  }
  for (const event of ["push", "length", "hasOwnProperty", "toString", "valueOf"]) {
    dispatch({ deai: 1, event, data: 1 });
  }
  dispatch({ deai: 1, event: "__proto__", data: "p" });
  dispatch({ deai: 1, event: "constructor", data: "c" });
  assert.deepEqual(plain(got), [["proto", "p"], ["ctor", "c"]]);
  assert.equal(Object.getPrototypeOf({}), Object.prototype);
});

test("понад 64 запитів у польоті — миттєва відмова busy, без відправки", async () => {
  const { win, sent } = load();
  const open = [];
  for (let i = 0; i < 64; i++) open.push(win.deai.context());
  const before = sent.length;
  await assert.rejects(win.deai.context(), (e) => e.code === "busy");
  assert.equal(sent.length, before);
  open.forEach((p) => p.catch(() => {}));
});

test("запит без відповіді спливає за 60 с (timeout), відповідь знімає таймер й звільняє місце", async () => {
  const { win, sent, dispatch, timers } = load();
  const a = win.deai.context();
  const b = win.deai.context();
  assert.equal(timers[1].ms, 60000);   // [0] — таймер hello
  dispatch({ deai: 1, re: sent[1].msg.id, ok: true, value: 1 });
  assert.equal(await a, 1);
  assert.equal(timers[1].cleared, true);
  timers[2].fn();
  await assert.rejects(b, (e) => e.code === "timeout");
  dispatch({ deai: 1, re: sent[2].msg.id, ok: true, value: 2 });   // пізня відповідь — тиша
  for (let i = 0; i < 64; i++) win.deai.context().catch(() => {});
  await assert.rejects(win.deai.context(), (e) => e.code === "busy");
});

test("deai.page.query шле page.query з аргументами", () => {
  const { win, sent } = load();
  win.deai.page.query("a", { limit: 2 }).catch(() => {});
  assert.deepEqual(plain([sent[1].msg.method, sent[1].msg.args]), ["page.query", ["a", { limit: 2 }]]);
});

test("deai.page має рівно 17 методів METHOD_PERM, кожен шле своє імʼя", () => {
  const { win, sent } = load();
  const names = Object.keys(METHOD_PERM).map((m) => m.slice(5));
  assert.equal(names.length, 17);
  assert.deepEqual(Object.keys(win.deai.page).sort(), [...names].sort());
  for (const n of names) {
    const before = sent.length;
    win.deai.page[n]().catch(() => {});
    assert.equal(sent[before].msg.method, `page.${n}`);
  }
});

test("page.pick без таймера; інші page.* — 60 с; pick-у польоті рахується в ліміт 64", async () => {
  const { win, timers } = load();
  const base = timers.length;
  win.deai.page.pick().catch(() => {});
  assert.equal(timers.length, base);
  win.deai.page.info().catch(() => {});
  assert.equal(timers.at(-1).ms, 60000);
  const { win: w2 } = load();
  const open = [w2.deai.page.pick()];
  for (let i = 0; i < 63; i++) open.push(w2.deai.context());
  await assert.rejects(w2.deai.page.info(), (e) => e.code === "busy");
  open.forEach((p) => p.catch(() => {}));
});

test("Esc у панелі під час page.pick шле page.cancelPick один раз; без вибору — тиша; інші клавіші ігноруються", () => {
  const { win, sent, dispatch, keydowns } = load();
  assert.equal(keydowns.length, 1);
  const key = (k) => keydowns.forEach((fn) => fn({ key: k }));
  key("Escape");
  assert.equal(sent.length, 1);                                   // лише hello
  win.deai.page.pick().catch(() => {});
  const pickId = sent.at(-1).msg.id;
  key("Enter");
  assert.equal(sent.length, 2);
  key("Escape");
  assert.equal(sent.length, 3);
  assert.deepEqual(plain([sent[2].msg.method, sent[2].msg.args]), ["page.cancelPick", []]);
  key("Escape");
  assert.equal(sent.length, 3);                                   // вдруге для того ж вибору — ні
  dispatch({ deai: 1, re: pickId, ok: true, value: null });
  key("Escape");
  assert.equal(sent.length, 3);                                   // вибору вже нема
  win.deai.page.pick().catch(() => {});
  key("Escape");
  assert.equal(sent.at(-1).msg.method, "page.cancelPick");        // новий вибір — знову можна
});

const flush = () => new Promise((r) => setTimeout(r, 0));

test("page: подія до підписки → підписник отримує останню асинхронно й рівно раз", async () => {
  const { win, dispatch } = load();
  dispatch({ deai: 1, event: "page", data: { page: { id: "p1" } } });
  const got = [];
  win.deai.on("page", (d) => got.push(plain(d)));
  assert.equal(got.length, 0, "не синхронно");
  await flush();
  assert.deepEqual(got, [{ page: { id: "p1" } }]);
  await flush();
  assert.equal(got.length, 1);
});

test("page: підписка до події → один виклик, без повтору", async () => {
  const { win, dispatch } = load();
  const got = [];
  win.deai.on("page", (d) => got.push(plain(d)));
  dispatch({ deai: 1, event: "page", data: { n: 1 } });
  await flush();
  assert.deepEqual(got, [{ n: 1 }]);
});

test("page: нова подія замінює запамʼятану; решта подій не відтворюються", async () => {
  const { win, dispatch } = load();
  dispatch({ deai: 1, event: "page", data: { n: 1 } });
  dispatch({ deai: 1, event: "page", data: { n: 2 } });
  dispatch({ deai: 1, event: "context", data: { c: 1 } });
  const page = [], ctx = [];
  win.deai.on("page", (d) => page.push(plain(d)));
  win.deai.on("context", (d) => ctx.push(plain(d)));
  await flush();
  assert.deepEqual(page, [{ n: 2 }]);
  assert.deepEqual(ctx, []);
});

test("page: подія між підпискою і відтворенням не дублюється; відписаний підписник не чує відтворення", async () => {
  const { win, dispatch } = load();
  dispatch({ deai: 1, event: "page", data: { n: 1 } });
  const got = [], off = [];
  win.deai.on("page", (d) => got.push(plain(d)));
  dispatch({ deai: 1, event: "page", data: { n: 2 } });
  win.deai.on("page", (d) => off.push(plain(d)))();
  await flush();
  assert.deepEqual(got, [{ n: 2 }]);
  assert.deepEqual(off, []);
});

test("page: підписник, що кидає при відтворенні, не ламає інших", async () => {
  const { win, dispatch } = load();
  dispatch({ deai: 1, event: "page", data: { n: 1 } });
  const got = [];
  win.deai.on("page", () => { throw new Error("boom"); });
  win.deai.on("page", (d) => got.push(plain(d)));
  await flush();
  assert.deepEqual(got, [{ n: 1 }]);
});
