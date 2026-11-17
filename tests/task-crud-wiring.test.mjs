/**
 * Проводка видалення/перейменування задач у `app/app.js` (етап Д, Task 9, борги ревʼю Task 8): виконуються самі тіла функцій
 * із заглушками (`app.js` у Node не імпортується — DOM на верхньому рівні, див. `tests/task-tags-wiring.test.mjs`).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

function balanced(open) {
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error("немає закриття дужки");
}
function declSource(name) {
  const m = new RegExp(`\\n((?:async )?function ${name}\\()`).exec(src);
  assert.ok(m, `у app.js нема функції ${name}`);
  const start = m.index + 1;
  const open = src.indexOf("{", src.indexOf(")", start));
  return src.slice(start, open) + balanced(open);
}
function load(env, funcs) {
  const decls = funcs.map(declSource).join("\n");
  // eslint-disable-next-line no-new-func
  return new Function("env", `with (env) { ${decls}\nreturn { ${funcs.map((f) => `${f}: ${f}`).join(", ")} }; }`)(env);
}

function titleEnv(over = {}) {
  const log = { bar: 0, tabs: 0 };
  return {
    log, markHomeMutated: () => {}, homeReady: () => false, homeData: null, tabs: [], saveTabs: () => {},
    paintTabs: () => { log.tabs += 1; }, paintBar: () => { log.bar += 1; },
    renamedAt: new Map(), pruneRenamed: () => {}, performance: { now: () => 1000 },
    curTask: null, currentTaskId: null, ...over,
  };
}

test("applyTaskTitle: після видалення поточної `curTask` ще про видалену задачу — нова назва нового поточного її не псує", () => {
  const stale = { id: "deleted", title: "Стара" };
  const env = titleEnv({ curTask: stale, currentTaskId: "next" });
  load(env, ["applyTaskTitle"]).applyTaskTitle("next", "Нова");
  assert.equal(env.curTask, stale, "обʼєкт чужої задачі замінено");
  assert.equal(env.curTask.title, "Стара");
  assert.equal(env.log.bar, 0, "смугу перемальовано з чужою задачею");
});

test("applyTaskTitle: `curTask` саме про цю задачу — назва нова, смуга перемальована", () => {
  const env = titleEnv({ curTask: { id: "x", title: "X" }, currentTaskId: "x" });
  load(env, ["applyTaskTitle"]).applyTaskTitle("x", "Ікс");
  assert.equal(env.curTask.title, "Ікс");
  assert.equal(env.log.bar, 1);
  assert.deepEqual(env.renamedAt.get("x"), { title: "Ікс", at: 1000 }, "перейменування не записано для render()");
});

test("toast: вузол для читачів екрана — role=status, aria-live=polite", () => {
  const made = [];
  const mk = () => {
    const n = { id: "", className: "", attrs: {}, classList: { add() {}, remove() {} }, setAttribute(k, v) { n.attrs[k] = v; },
      replaceChildren() {}, appendChild() {}, addEventListener() {}, dataset: {} };
    made.push(n); return n;
  };
  const document = { getElementById: () => made[0] ?? null, createElement: mk, body: { appendChild() {} } };
  const env = { document, clearTimeout: () => {}, setTimeout: () => 0 };
  load(env, ["toast"]).toast("текст");
  assert.equal(made[0].attrs.role, "status");
  assert.equal(made[0].attrs["aria-live"], "polite");
});

test("focusKey: картка «+» (th-card без data-id) ключується за data-th, а не за `data-id=undefined`", () => {
  const el = (cls, dataset, id = "") => ({ id, classList: { contains: (c) => cls.includes(c) }, dataset });
  const env = { document: { body: {} }, CSS: { escape: (x) => String(x) } };
  const { focusKey } = load(env, ["focusKey"]);
  assert.equal(focusKey(el(["th-card"], { th: "newtask" })), '[data-th="newtask"]');
  assert.equal(focusKey(el(["th-card"], { th: "open", id: "x" })), '.th-card[data-id="x"]');
});
