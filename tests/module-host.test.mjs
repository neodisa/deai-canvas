/* Логіка оболонки для інструментів модулів (app/module-host.js): острівець, клавіші, міст-хост. */
import assert from "node:assert/strict";
import test from "node:test";
import { CORE_KEYS, MAX_ISLAND_TOOLS, actionItems, createBridgeHost, islandModTools, modKeyMap, modToolKey, paletteModTools } from "../app/module-host.js";
import { KEYS } from "../app/shell-palette.js";

const tool = (i, o = {}) => ({ module: "m1", module_name: "M1", id: `t${i}`, label: `Tool ${i}`, icon: "puzzle", key: null, panel: `/api/module-ui/s/m1/p${i}.html`, ...o });
const EXT = { tools: [tool(1, { key: "J" }), tool(2, { key: "C" }), tool(3), tool(4, { key: "K" }), tool(5)], actions: [] };

test("islandModTools: до 3 перших, лише «Макет» на екрані задачі", () => {
  assert.equal(MAX_ISLAND_TOOLS, 3);
  const r = islandModTools(EXT, { screen: "task", mode: "layout" });
  assert.deepEqual(r.map((x) => x.key), ["m1/t1", "m1/t2", "m1/t3"]);
  assert.deepEqual(islandModTools(EXT, { screen: "task", mode: "overview" }), []);
  assert.deepEqual(islandModTools(EXT, { screen: "home", mode: "layout" }), []);
  assert.deepEqual(islandModTools(null, { screen: "task", mode: "layout" }), []);
  assert.deepEqual(islandModTools({}, { screen: "task", mode: "layout" }), []);
});

test("islandModTools: літера — лише вільна від ядра (C зайнята → null)", () => {
  const r = islandModTools(EXT, { screen: "task", mode: "layout" });
  assert.deepEqual(r.map((x) => x.letter), ["J", null, null]);
  assert.deepEqual(r.map((x) => x.label), ["Tool 1", "Tool 2", "Tool 3"]);
});

test("іконка поза набором ядра → puzzle (і для острівця, і для ⌘K)", () => {
  const ext = { tools: [tool(1, { icon: "nope" }), tool(2, { icon: "constructor" }), tool(3, { icon: "inspect" })] };
  assert.deepEqual(islandModTools(ext, { screen: "task", mode: "layout" }).map((x) => x.icon), ["puzzle", "puzzle", "inspect"]);
  assert.deepEqual(paletteModTools(ext).map((x) => x.icon), ["puzzle", "puzzle", "inspect"]);
});

test("modKeyMap: літера → модуль/інструмент, без літер ядра, перший виграє", () => {
  assert.deepEqual(modKeyMap(EXT, CORE_KEYS), { J: "m1/t1", K: "m1/t4" });
  const dup = { tools: [tool(1, { key: "J" }), tool(2, { key: "J" })] };
  assert.deepEqual(modKeyMap(dup, CORE_KEYS), { J: "m1/t1" });
  assert.deepEqual(modKeyMap(null, CORE_KEYS), {});
  const m = modKeyMap({ tools: [tool(1, { key: "__proto__" }), tool(2, { key: "j" }), tool(3, { key: "JJ" })] }, []);
  assert.deepEqual(Object.keys(m), []);
  assert.equal(Object.hasOwn(modKeyMap(EXT, CORE_KEYS), "toString"), false);
});

test("CORE_KEYS закріплено проти KEYS: кожна одно-літерна клавіша ядра в списку", () => {
  assert.deepEqual([...CORE_KEYS].sort(), ["C", "H", "I", "M", "P"]);
  for (const k of KEYS) {
    if (/^[A-Z]$/.test(k.kbd)) assert.ok(CORE_KEYS.includes(k.kbd), `«${k.kbd}» у KEYS, але не в CORE_KEYS`);
  }
});

test("paletteModTools: усі інструменти, з літерою лише вільною", () => {
  const r = paletteModTools(EXT);
  assert.equal(r.length, 5);
  assert.deepEqual(r.map((x) => x.letter), ["J", null, null, "K", null]);
  assert.equal(modToolKey(EXT.tools[3]), "m1/t4");
});

function host(over = {}) {
  const calls = [];
  const h = createBridgeHost({
    getContext: () => ({ space: { id: "s", name: "S" }, task: { id: "t", name: "T" }, iteration: null, page: null, lang: "uk", theme: "dark" }),
    getSelection: () => null,
    getVars: () => ({ "--s1": "#111" }),
    getTheme: () => "dark",
    callTool: async (...a) => { calls.push(["call", ...a]); return { echo: a[1] }; },
    toast: (t) => calls.push(["toast", t]),
    close: () => calls.push(["close"]),
    ...over,
  });
  return { h, calls };
}
const M = (method, args, id = 1) => ({ deai: 1, id, method, ...(args === undefined ? {} : { args }) });

test("хост: context, selection, hello (без відповіді), невідомий метод", async () => {
  const { h } = host();
  const c = await h.handle(M("context", []));
  assert.equal(c.ok, true);
  assert.equal(c.re, 1);
  assert.equal(c.deai, 1);
  assert.equal(c.value.page, null);
  assert.deepEqual(await h.handle(M("selection", [], 2)), { deai: 1, re: 2, ok: true, value: null });
  assert.equal(await h.handle(M("hello", [], 3)), null);
  assert.equal(h.check(M("hello", [], 3)), null);
  assert.deepEqual(await h.handle(M("nope", [], 4)), { deai: 1, re: 4, ok: false, error: "unknown-method", detail: "nope" });
});

test("хост: форма повідомлення — чужі й криві ігноруються, з id — bad-message", async () => {
  const { h } = host();
  for (const m of [null, 5, "x", {}, { deai: 2, id: 1, method: "context" }, { deai: 1, id: -1, method: "context" },
    { deai: 1, id: 1.5, method: "context" }, { deai: 1, id: "1", method: "context" }]) {
    assert.equal(await h.handle(m), null, JSON.stringify(m));
  }
  const bad = await h.handle({ deai: 1, id: 7, method: "context", args: "no" });
  assert.equal(bad.ok, false);
  assert.equal(bad.error, "bad-message");
  assert.equal((await h.handle({ deai: 1, id: 8, method: 5 })).error, "bad-message");
});

test("хост: розмір понад 64 КіБ — too-big (і циклічний обʼєкт теж)", async () => {
  const { h, calls } = host();
  const big = await h.handle(M("call", ["tool_x", "x".repeat(70000)], 9));
  assert.deepEqual([big.ok, big.error, big.re], [false, "too-big", 9]);
  const cyc = { a: 1 }; cyc.self = cyc;
  assert.equal((await h.handle(M("call", ["tool_x", cyc], 10))).error, "too-big");
  assert.deepEqual(calls, []);
  const edge = await h.handle(M("call", ["tool_x", "y".repeat(65000)], 11));
  assert.equal(edge.ok, true);
});

test("хост: call іде у callTool(fn, args) — модуль панель не обирає", async () => {
  const { h, calls } = host();
  const r = await h.handle({ deai: 1, id: 1, method: "call", args: ["tool_echo", { x: 1 }], module: "evil", fnModule: "evil" });
  assert.deepEqual(r.value, { echo: { x: 1 } });
  assert.deepEqual(calls, [["call", "tool_echo", { x: 1 }]]);
  assert.equal((await h.handle(M("call", [5, {}], 2))).error, "bad-args");
  assert.equal((await h.handle(M("call", [], 3))).error, "bad-args");
  const three = await h.handle(M("call", ["tool_a", {}, "m2"], 4));
  assert.equal(three.ok, true);
  assert.deepEqual(calls.at(-1), ["call", "tool_a", {}]);   // callTool отримує лише (fn, args): третій аргумент панелі — не модуль
});

test("хост: не більше 4 одночасних call — п'ятий busy; після завершення місце звільняється", async () => {
  const gates = [];
  const { h } = host({ callTool: () => new Promise((res) => gates.push(res)) });
  const ps = [1, 2, 3, 4].map((i) => h.handle(M("call", ["tool_a", i], i)));
  const fifth = await h.handle(M("call", ["tool_a", 5], 5));
  assert.deepEqual([fifth.ok, fifth.error], [false, "busy"]);
  gates[0]("ok1");
  assert.equal((await ps[0]).value, "ok1");
  const again = h.handle(M("call", ["tool_a", 6], 6));
  gates[4]("ok6");
  assert.equal((await again).value, "ok6");
  gates.slice(1, 4).forEach((g) => g(null));
  await Promise.all(ps);
});

test("хост: помилка callTool → {error: code, detail ≤ 300}; без code — error", async () => {
  const { h } = host({ callTool: async () => { throw Object.assign(new Error("d".repeat(500)), { code: "module-busy" }); } });
  const r = await h.handle(M("call", ["tool_a", 1]));
  assert.equal(r.error, "module-busy");
  assert.equal(r.detail.length, 300);
  const { h: h2 } = host({ getContext: () => { throw new Error("boom"); } });
  const r2 = await h2.handle(M("context", []));
  assert.deepEqual([r2.ok, r2.error, r2.detail], [false, "error", "boom"]);
});

test("хост: toast — рядок ≤ 200, close — без відповіді; не рядок — bad-args", async () => {
  const { h, calls } = host();
  assert.equal(await h.handle(M("toast", ["t".repeat(300)])), null);
  assert.equal(calls[0][1].length, 200);
  assert.equal((await h.handle(M("toast", [5], 2))).error, "bad-args");
  assert.equal(await h.handle(M("close", [], 3)), null);
  assert.deepEqual(calls.at(-1), ["close"]);
});

test("хост: event — повідомлення для панелі", () => {
  const { h } = host();
  assert.deepEqual(h.event("theme", { a: 1 }), { deai: 1, event: "theme", data: { a: 1 } });
  const init = h.initData();
  assert.deepEqual(Object.keys(init).sort(), ["context", "theme", "vars"]);
  assert.equal(init.theme, "dark");
  assert.equal(init.vars["--s1"], "#111");
});

const act = (m, id, where, label = id) => ({ module: m, module_name: `${m} name`, id, label, where });
const AEXT = { tools: [], actions: [act("m1", "a", ["palette", "task"], "A <b>"), act("m2", "b", ["iteration"]), act("m1", "c", ["palette", "task", "iteration"], 'C "q"')] };

test("actionItems: фільтр за where, порядок ext, сирі підписи", () => {
  assert.deepEqual(actionItems(AEXT, "palette").map((x) => x.key), ["m1/a", "m1/c"]);
  assert.deepEqual(actionItems(AEXT, "task").map((x) => x.key), ["m1/a", "m1/c"]);
  assert.deepEqual(actionItems(AEXT, "iteration").map((x) => x.key), ["m2/b", "m1/c"]);
  assert.deepEqual(actionItems(AEXT, "palette")[0], { key: "m1/a", label: "A <b>", module: "m1", id: "a", moduleName: "m1 name" });
  assert.equal(actionItems(AEXT, "palette")[1].label, 'C "q"');
});

test("actionItems: порожнє й чуже", () => {
  assert.deepEqual(actionItems(AEXT, "nowhere"), []);
  assert.deepEqual(actionItems(null, "palette"), []);
  assert.deepEqual(actionItems({}, "palette"), []);
  assert.deepEqual(actionItems({ actions: "x" }, "palette"), []);
  assert.deepEqual(actionItems({ actions: [{ module: "m", id: "i", label: "L" }] }, "palette"), []);
});

/* Проводка в app.js (функції не виносяться з модуля оболонки — перевіряємо джерело). */
import { readFileSync } from "node:fs";
const APP = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");
const fnSrc = (name) => { const i = APP.indexOf(`function ${name}(`); assert.ok(i > 0, name); return APP.slice(i, APP.indexOf("\n}\n", i)); };

test("loadModExt: змінений список → paintBar (дропдаун ітерації); сам loadModExt не кличеться з paintBar/modSync/paintIsland", () => {
  assert.match(fnSrc("loadModExt").replace("async ", ""), /JSON\.stringify\(modExtNow\(\)\) !== prev\) paintBar\(\); else paintIsland\(\);/);
  for (const f of ["paintBar", "modSync", "paintIsland"]) assert.equal(/loadModExt\(/.test(fnSrc(f)), false, `${f} кличе loadModExt — цикл`);
});

test("runModuleAction: порожній текст помилки → «—», як у гілці збою", () => {
  assert.match(fnSrc("runModuleAction"), /catch \(e\) \{\s*toast\(t\('modActFail', label, e\?\.message \|\| String\(e\?\.code \?\? ''\) \|\| '—'\)\);/);
});
