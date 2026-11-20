/* Міст панелі модуля (app/module-kit/bridge.js): класичний скрипт у фальшивому вікні (node:vm). */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import vm from "node:vm";

const SRC = readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app", "module-kit", "bridge.js"), "utf8");

/* Об'єкти з vm-контексту мають інші прототипи: порівнюємо їх як дані. */
const plain = (x) => JSON.parse(JSON.stringify(x));

function load() {
  const sent = [];
  const listeners = [];
  const parent = { postMessage: (msg, target) => sent.push({ msg, target }) };
  const style = { props: {}, setProperty(k, v) { this.props[k] = v; } };
  const documentElement = { dataset: {}, style };
  const win = {
    parent,
    document: { documentElement },
    addEventListener: (type, fn) => { if (type === "message") listeners.push(fn); },
  };
  win.window = win;
  vm.runInNewContext(SRC, win);
  const dispatch = (data, source = parent) => listeners.forEach((fn) => fn({ data, source }));
  return { win, sent, dispatch, parent, documentElement, style };
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
