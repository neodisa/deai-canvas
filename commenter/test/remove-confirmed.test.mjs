/**
 * Етап В (0.28.0): оболонка Deai питає про видалення сама, у картці своєї панелі, і передає `{ confirmed: true }` —
 * коментатор тоді не кличе браузерний `confirm()` (його вбудований браузер Claude мовчки скасовує, Chrome вміє вимкнути
 * зовсім). Без прапорця — як було: власна панель коментатора (сторінка без host, превʼю) питає через `confirm()`.
 * Метод беремо з джерела й прогоняємо на підробному `this`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");

const m = src.match(/ {4}removeComment\(id, opts\) \{[\s\S]*?\n {4}\},/);
assert.ok(m, "у comment-layer.js немає removeComment(id, opts)");
// eslint-disable-next-line no-new-func
const make = (confirmFn) => new Function("confirm", `return { ${m[0].replace(/,\s*$/, "")} };`)(confirmFn).removeComment;

function world(confirmFn) {
  const removed = [];
  const self = {
    comments: [{ id: "a" }, { id: "b" }],
    store: { remove: (ids) => removed.push(...ids) },
    _persist() {}, _render() {}, _placePins() {},
  };
  self.removeComment = make(confirmFn);
  return { self, removed };
}

{
  let asked = 0;
  const { self, removed } = world(() => { asked += 1; return false; });
  self.removeComment("a", { confirmed: true });
  assert.equal(asked, 0, "з confirmed: true нативне вікно не показується");
  assert.deepEqual(removed, ["a"]);
  assert.deepEqual(self.comments.map((c) => c.id), ["b"]);
}
{
  let asked = 0;
  const { self, removed } = world(() => { asked += 1; return false; });
  self.removeComment("a");
  assert.equal(asked, 1, "без прапорця — як було, з confirm()");
  assert.deepEqual(removed, [], "відмова в confirm() нічого не видаляє");
  assert.equal(self.comments.length, 2);
}
{
  const { self, removed } = world(() => true);
  self.removeComment("a");
  assert.deepEqual(removed, ["a"], "згода в confirm() видаляє");
}
{
  // лише строго `true`: «щось правдиве» чи рядок — не підтвердження
  let asked = 0;
  const { self, removed } = world(() => { asked += 1; return false; });
  self.removeComment("a", { confirmed: "yes" });
  self.removeComment("a", { confirmed: 1 });
  assert.equal(asked, 2);
  assert.deepEqual(removed, []);
}
// власна панель коментатора лишає виклик без прапорця
assert.match(src, /else if \(act === 'delete'\) this\.removeComment\(id\);/, "власна панель коментатора питає через confirm()");
console.log("remove-confirmed: ok");
