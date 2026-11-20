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
const grab = (n) => src.match(new RegExp(` {2}function ${n}\\([\\s\\S]*?\\n {2}\\}`))[0];
const stripRuntime = new Function(`${fn[0]}\nreturn stripRuntime;`)();
// eslint-disable-next-line no-new-func
const mergeReplies = new Function(`${grab("stampKey")}\n${grab("mergeReplies")}\nreturn mergeReplies;`)();

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

test("stripRuntime: _goneReplies прибирається, биті записи replies відкидаються", () => {
  const out = stripRuntime({ id: "a", _goneReplies: ["r"], replies: [null, 7, "s", { id: "r1", _pending: true }] });
  assert.deepEqual(out, { id: "a", replies: [{ id: "r1" }] });
});

test("mergeReplies: усі ts читаються — за ts; є нечитний — порядок зовнішніх, нові в кінці", () => {
  const e = (id, ts) => ({ id, ts });
  assert.deepEqual(mergeReplies([e("a", "02.01.2026 10:00"), e("b", "01.01.2026 10:00")], [e("c", "01.01.2026 11:00")]).map((r) => r.id), ["b", "c", "a"]);
  assert.deepEqual(mergeReplies([e("a", "02.01.2026 10:00"), e("b", "")], [e("c", "01.01.2026 11:00"), e("d", "x")]).map((r) => r.id), ["a", "b", "c", "d"]);
  assert.deepEqual(mergeReplies([e("a", "1"), null, e("b", "2")], [null, { id: "a", ts: "9" }]).map((r) => [r.id, r.ts]), [["a", "9"], ["b", "2"]]);
  assert.deepEqual(mergeReplies(undefined, [e("c", "01.01.2026 11:00")]).map((r) => r.id), ["c"]);
});
