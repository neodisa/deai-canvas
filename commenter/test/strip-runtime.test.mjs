/**
 * `stripRuntime(c)` (0.34): прибирає `_el`/`_pending` коментаря і `_pending` кожної відповіді, `replies` копіює
 * (вхід не мутує), решту полів (зокрема `agent`) лишає. Функцію витягуємо з джерела, як `pageOf`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");
const fn = src.match(/ {2}function stripRuntime\([\s\S]*?\n {2}\}/);
assert.ok(fn, "у comment-layer.js немає stripRuntime");
// eslint-disable-next-line no-new-func
const stripRuntime = new Function(`${fn[0]}\nreturn stripRuntime;`)();

test("stripRuntime: _el/_pending коментаря і вкладені _pending відповідей зникають, agent лишається", () => {
  const el = { tag: "x" };
  const c = { id: "a", text: "t", _el: el, _pending: true,
    replies: [{ id: "r1", text: "x", _pending: true }, { id: "r2", text: "y", agent: true }] };
  const before = JSON.parse(JSON.stringify({ ...c, _el: undefined }));
  const out = stripRuntime(c);
  assert.deepEqual(out, { id: "a", text: "t", replies: [{ id: "r1", text: "x" }, { id: "r2", text: "y", agent: true }] });
  assert.ok(!("_el" in out) && !("_pending" in out));
  assert.ok(!out.replies.some((r) => "_pending" in r));
  // вхід не змінено
  assert.equal(c._pending, true);
  assert.equal(c._el, el);
  assert.deepEqual(JSON.parse(JSON.stringify({ ...c, _el: undefined })), before);
  assert.equal(c.replies[0]._pending, true);
  assert.notEqual(out.replies, c.replies);
});

test("stripRuntime: без replies поля не зʼявляється", () => {
  assert.ok(!("replies" in stripRuntime({ id: "a", _pending: false })));
});
