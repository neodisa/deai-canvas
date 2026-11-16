/**
 * Етап Г (0.29.0): чиста логіка клавіатурної драбини оверлея — що вибрати після Esc / Enter / ← → і яка ціль в Alt.
 * Дерево — прості вузли `{ parent, children }`: модуль про DOM не знає, `inspector.js` дає йому ці чотири функції.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { altTarget, nextPin } from "../app/vendor/inspector-nav.js";

const tree = () => {
  const mk = (name, parent = null) => ({ name, parent, children: [] });
  const body = mk("body");
  const wrap = mk("wrap", body); body.children.push(wrap);
  const a = mk("a", wrap); const b = mk("b", wrap); const c = mk("c", wrap); wrap.children.push(a, b, c);
  const kid = mk("kid", a); a.children.push(kid);
  return { body, wrap, a, b, c, kid };
};
const api = { parentOf: (n) => n.parent, childrenOf: (n) => n.children };

test("Esc: батько; на корені — зняти вибір; без вибору — вимкнути інспектор", () => {
  const { a, body, wrap } = tree();
  assert.deepEqual(nextPin("Escape", a, api), { pin: wrap });
  assert.deepEqual(nextPin("Escape", body, api), { pin: null });
  assert.deepEqual(nextPin("Escape", null, api), { off: true });
});

test("Enter: перший дочірній; без дітей — нічого не споживаємо", () => {
  const { a, wrap, b } = tree();
  assert.deepEqual(nextPin("Enter", wrap, api), { pin: a });
  assert.equal(nextPin("Enter", b, api), null);
  assert.equal(nextPin("Enter", null, api), null);
});

test("← / →: сусід; на краю лишаємось на місці, але ключ споживаємо (сторінка не гортається)", () => {
  const { a, b, c } = tree();
  assert.deepEqual(nextPin("ArrowRight", a, api), { pin: b });
  assert.deepEqual(nextPin("ArrowLeft", c, api), { pin: b });
  assert.deepEqual(nextPin("ArrowLeft", a, api), { pin: a });
  assert.deepEqual(nextPin("ArrowRight", c, api), { pin: c });
  assert.equal(nextPin("ArrowRight", null, api), null, "без вибору ← → не наші");
});

test("інші клавіші драбина не чіпає", () => {
  const { a } = tree();
  assert.equal(nextPin("x", a, api), null);
  assert.equal(nextPin("ArrowUp", a, api), null);
});

test("Alt-ціль: ← → ідуть сусідами від поточної цілі, ↑ — знову батько, без цілі — батько", () => {
  const { a, b, c, wrap } = tree();
  assert.equal(altTarget("ArrowRight", a, null, api), b);
  assert.equal(altTarget("ArrowRight", a, b, api), c, "друге натискання — далі по сусідах");
  assert.equal(altTarget("ArrowLeft", a, b, api), a, "назад до вибраного");
  assert.equal(altTarget("ArrowUp", a, c, api), wrap);
  assert.equal(altTarget("ArrowRight", c, null, api), null, "за краєм сусіда немає");
});

import { readFileSync } from "node:fs";
const overlay = readFileSync(new URL("../app/vendor/inspector.js", import.meta.url), "utf8");
const code = overlay.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

test("режиму лінійки й підказки-тултипа в оверлеї більше немає", () => {
  for (const gone of ["setMode", "toggleMode", "_ruler", "_candidates", "_containerBox", "_setMeas", "measure()", "_tip", "'ruler'"]) {
    assert.ok(!code.includes(gone), `в inspector.js лишився слід лінійки: ${gone}`);
  }
});

test("клавіші: оверлей ловить Alt, Esc, Enter, ← → і віддає оболонці handleKey / setAlt / yieldEsc", () => {
  for (const needle of ["e.key === 'Alt'", "e.key === 'Escape'", "e.key === 'Enter'", "e.key === 'ArrowLeft'",
    "handleKey(", "setAlt(", "yieldEsc"]) {
    assert.ok(code.includes(needle), `в inspector.js немає ${needle}`);
  }
});

test("STYLE оверлея: синій вибору й червоний відстаней; .insp-spec лишається (його малює reportHTML)", () => {
  const style = overlay.match(/const STYLE = `([\s\S]*?)`;/)[1];
  assert.match(style, /#3D8BFF/i); assert.match(style, /#F2554B/i);
  assert.ok(style.includes(".insp-spec"));
  assert.ok(!style.includes(".tip{") && !style.includes(".anch{"));
  // Підсвітка margin/padding (DevTools-оверлей, v1.19) лишається — поправка контролера.
  assert.ok(style.includes(".hl{") && style.includes(".hl-pad{"));
});
