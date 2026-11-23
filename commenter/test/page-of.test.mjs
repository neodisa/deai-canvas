/**
 * `pageOf(v)` (0.34): сторінка з тегу версії піна — усе після ПЕРШОГО `/`. У режимі хоста за нею, а не за маршрутом
 * (у превʼю це адреса Deai), вирішується, чи пін на цій сторінці. Функцію витягуємо з джерела, як `getUser` у host-user.test.mjs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");
const fn = src.match(/ {2}function pageOf\([\s\S]*?\n {2}\}/);
assert.ok(fn, "у comment-layer.js немає pageOf");
// eslint-disable-next-line no-new-func
const pageOf = new Function(`${fn[0]}\nreturn pageOf;`)();

test("pageOf: усе після першого «/»", () => {
  assert.equal(pageOf("1/holovna"), "holovna");
  assert.equal(pageOf("12/b/c"), "b/c");
  assert.equal(pageOf("3/"), "");
});

test("pageOf: без «/», не рядок — порожньо", () => {
  assert.equal(pageOf("3"), "");
  assert.equal(pageOf(""), "");
  assert.equal(pageOf(null), "");
  assert.equal(pageOf(undefined), "");
  assert.equal(pageOf(3), "");
});
