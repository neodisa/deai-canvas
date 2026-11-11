/**
 * Кільце помилок клієнта (0.23.0, `app/err-ring.js`): ліміти, нормалізація без повних адрес і query-рядків, два слухачі,
 * `app.js` підключає модуль ПЕРШИМ імпортом.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { MSG_MAX, RING_MAX, fileOf, initErrRing, list, normalize, push, reset } from "../app/err-ring.js";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");

test.beforeEach(() => reset());

test("error → {msg, file, line}; file — від /app/ включно, решта адреси порожня", () => {
  assert.deepEqual(normalize({ type: "error", message: "boom", filename: "http://localhost:8765/app/app.js", lineno: 42 }),
    { msg: "boom", file: "app/app.js", line: 42 });
  assert.deepEqual(normalize({ type: "error", message: "x", filename: "https://cdn.example.com/lib/x.js", lineno: 1 }),
    { msg: "x", file: "", line: 1 });
});

test("query й фрагмент адреси не лишаються ні у file, ні в повідомленні", () => {
  assert.equal(fileOf("http://localhost:8765/app/app.js?v=123&token=SECRET#frag"), "app/app.js");
  assert.equal(normalize({ type: "error", message: "m", filename: "http://h/app/x.js?session=SECRET", lineno: 3 }).file, "app/x.js");
  const n = normalize({ type: "error", message: "Failed to fetch http://localhost:8765/api/x?token=SECRET&a=1 now", filename: "", lineno: 0 });
  assert.ok(!n.msg.includes("SECRET"), n.msg);
  assert.ok(n.msg.includes("http://localhost:8765/api/x"), n.msg);
});

test("unhandledrejection: msg з reason.message або з рядка; сміття → null", () => {
  assert.equal(normalize({ type: "unhandledrejection", reason: new Error("nope") }).msg, "nope");
  assert.equal(normalize({ type: "unhandledrejection", reason: "plain" }).msg, "plain");
  for (const bad of [null, undefined, 5, "x", { type: "unhandledrejection", reason: 7 }, { type: "error" }]) assert.equal(normalize(bad), null);
});

test("кільце тримає не більше RING_MAX найновіших; msg ≤ MSG_MAX", () => {
  assert.equal(RING_MAX, 20);
  for (let i = 0; i < 30; i += 1) push({ type: "error", message: `e${i}`, filename: "", lineno: i });
  const l = list();
  assert.equal(l.length, RING_MAX);
  assert.equal(l[0].msg, "e10");
  assert.equal(l[RING_MAX - 1].msg, "e29");
  reset();
  push({ type: "error", message: "я".repeat(MSG_MAX + 50), filename: "", lineno: 0 });
  assert.equal(Array.from(list()[0].msg).length, MSG_MAX);
});

test("push не кидає на сміття, list() віддає копію", () => {
  for (const bad of [null, undefined, 0, "s", [], { type: 5, message: {} }, { get message() { throw new Error("x"); } }]) push(bad);
  push({ type: "error", message: "ok", filename: "", lineno: 0 });
  const l = list();
  l[0].msg = "змінено";
  l.pop();
  assert.equal(list()[0].msg, "ok");
});

test("initErrRing ставить рівно два слухачі й не дублює; повертає list", () => {
  const seen = [];
  const win = { addEventListener: (type, fn) => seen.push([type, fn]) };
  const l1 = initErrRing(win);
  const l2 = initErrRing(win);
  assert.deepEqual(seen.map((x) => x[0]), ["error", "unhandledrejection"]);
  assert.equal(l1, list);
  assert.equal(l2, list);
  seen[0][1]({ type: "error", message: "via listener", filename: "", lineno: 0 });
  assert.equal(list()[0].msg, "via listener");
});

test("app.js підключає err-ring.js ПЕРШИМ імпортом", () => {
  const first = readFileSync(path.join(APP, "app.js"), "utf8").split("\n").find((l) => /^import\s/.test(l));
  assert.match(first, /from '\.\/err-ring\.js'/);
});
