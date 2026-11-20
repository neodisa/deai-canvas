/**
 * Імʼя автора в режимі хоста (0.32.0): `host.userName()` — опційний гачок, яким оболонка (публічне превʼю) сама дає імʼя, і тоді
 * `prompt()` не викликається НІКОЛИ. Плюс `host.onAdd(id)` — хост дізнається id щойно створеного коментаря.
 * Зворотна сумісність: без гачка `getUser` поводиться як було (запис у localStorage, `prompt()` останнім, «Anonymous»).
 * Як і сусідні тести, витягуємо чисту функцію з джерела й годуємо підробленими `localStorage`/`prompt`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "comment-layer.js");
const src = readFileSync(SRC, "utf8");
const fn = src.match(/ {2}function getUser\([\s\S]*?\n {2}\}/);
assert.ok(fn, "у comment-layer.js немає getUser");

/** Нове оточення на кожен тест: `store` — localStorage (Map), `prompts` — виклики prompt(). */
function env({ stored = null, promptValue = "З діалогу", storageThrows = false, promptThrows = false } = {}) {
  const store = new Map(stored == null ? [] : [["comment-layer:user", stored]]);
  const prompts = [];
  const localStorage = {
    getItem: (k) => { if (storageThrows) throw new Error("sandbox"); return store.has(k) ? store.get(k) : null; },
    setItem: (k, v) => { if (storageThrows) throw new Error("sandbox"); store.set(k, v); },
  };
  const prompt = (...a) => { prompts.push(a); if (promptThrows) throw new Error("prompt() is not supported"); return promptValue; };
  // eslint-disable-next-line no-new-func
  const getUser = new Function("localStorage", "prompt", `${fn[0]}\nreturn getUser;`)(localStorage, prompt);
  return { getUser, store, prompts };
}

test("зворотна сумісність: без хоста prompt() питає останнім і імʼя пишеться в localStorage", () => {
  const e = env();
  assert.deepEqual(e.getUser(null, null), { name: "З діалогу" });
  assert.equal(e.prompts.length, 1);
  assert.equal(e.store.get("comment-layer:user"), "З діалогу");
  const f = env({ promptValue: "" });
  assert.deepEqual(f.getUser(null, null), { name: "Anonymous" });
  assert.equal(f.store.get("comment-layer:user"), "Anonymous", "старе: «Anonymous» запам'ятовується (поведінку не міняємо)");
});

test("зворотна сумісність: хост без `userName` (Deai) — як було, prompt() лишається запасним", () => {
  const e = env();
  assert.deepEqual(e.getUser(null, null, { onReady() {} }), { name: "З діалогу" });
  assert.equal(e.prompts.length, 1);
});

test("збережене імʼя з localStorage має пріоритет над усім і prompt() не кличеться", () => {
  const e = env({ stored: "Олена" });
  assert.deepEqual(e.getUser(null, null, { userName: () => "Інше" }), { name: "Олена" });
  assert.equal(e.prompts.length, 0);
});

test("хост із `userName`: імʼя від хоста, prompt() не кличеться, імʼя запамʼятовується", () => {
  const e = env();
  assert.deepEqual(e.getUser(null, null, { userName: () => "  Марко  " }), { name: "Марко" });
  assert.equal(e.prompts.length, 0);
  assert.equal(e.store.get("comment-layer:user"), "Марко");
});

test("хост із `userName`, імені нема: «Anonymous», prompt() НЕ кличеться і «Anonymous» не запамʼятовується", () => {
  for (const userName of [() => "", () => null, () => { throw new Error("boom"); }]) {
    const e = env();
    assert.deepEqual(e.getUser(null, null, { userName }), { name: "Anonymous" });
    assert.equal(e.prompts.length, 0, "prompt() у режимі хоста з гачком");
    assert.equal(e.store.has("comment-layer:user"), false, "«Anonymous» записано — оболонка вже не спитає імені");
  }
});

test("хост із `userName`, імені нема, є запасне `defaultUser`: береться воно, без prompt()", () => {
  const e = env();
  assert.deepEqual(e.getUser(null, { name: "Машина" }, { userName: () => "" }), { name: "Машина" });
  assert.equal(e.prompts.length, 0);
});

test("localStorage недоступний (пісочниця): хост із гачком усе одно дає імʼя й не кличе prompt()", () => {
  const e = env({ storageThrows: true });
  assert.deepEqual(e.getUser(null, null, { userName: () => "Гість" }), { name: "Гість" });
  assert.equal(e.prompts.length, 0);
});

test("джерело: onAdd лунає в усіх трьох місцях створення коментаря, до першого onChange", () => {
  const emits = [...src.matchAll(/_emit\('onAdd', (\w+(?:\.\w+)?)\)/g)].map((m) => m[1]);
  assert.deepEqual(emits.sort(), ["copy.id", "id", "newId"], "onAdd має лунати з _addComment, _addCanvasComment і _carryToCurrent");
  const add = src.slice(src.indexOf("    _addComment(el, text"), src.indexOf("    async _finishComment"));
  assert.ok(add.indexOf("_emit('onAdd'") < add.indexOf("this._render()"), "onAdd має бути раніше за перший _render (onChange)");
});
