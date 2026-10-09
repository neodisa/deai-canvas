import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { DICT } from "../app/i18n.js";
import { ERR_KEY, errKey, kindOf, flatten, findNode, pathOf, validate, applyMove, planMove, topIds, statsOf, visibleIds, visibleRows, stepRow, firstChildRow, rowRange }
  from "../app/tree-model.js";

const RULES = JSON.parse(readFileSync(new URL("./fixtures/tree-rules.json", import.meta.url), "utf8"));
const clone = (v) => JSON.parse(JSON.stringify(v));
function tree(spec) {
  if (Array.isArray(spec)) return clone(spec);
  if (spec.startsWith("DEEP:")) {
    const n = Number(spec.split(":")[1]);
    const root = { id: "f1", name: "F1", kind: "folder" };
    let cur = root;
    for (let i = 2; i <= n; i += 1) { const nx = { id: `f${i}`, name: `F${i}`, kind: "folder" }; cur.children = [nx]; cur = nx; }
    return [root];
  }
  return clone(RULES.trees[spec]);
}

test("спільні кейси validate — те саме, що в Python", () => {
  for (const c of RULES.validate) {
    assert.equal(validate(tree(c.tree))?.code ?? null, c.err, c.name);
  }
});

test("спільні кейси visible — visibleIds = правило превʼю, як у Python", () => {
  for (const c of RULES.visible) {
    assert.deepEqual([...visibleIds(tree(c.tree))], c.visible, c.name);
    const t = tree(c.tree);
    const open = flatten(t).filter((f) => f.kind !== "folder" && visibleIds(t).has(f.page.id)).map((f) => f.page.id);
    assert.deepEqual(open, c.open, `${c.name}: відкривані`);
  }
});

test("applyMove на дереві з не-списковим children — corrupt, а не збій", () => {
  for (const bad of [{ id: "x" }, "abc", 7]) {
    const r = applyMove([{ id: "p", name: "P", kind: "page", children: bad }], ["p"], null, 0);
    assert.equal(r.err, "corrupt", JSON.stringify(bad));
  }
});

test("спільні кейси applyMove — те саме, що op_move у Python", () => {
  for (const c of RULES.move) {
    const t = tree(c.tree);
    const before = JSON.stringify(t);
    const r = applyMove(t, c.ids, c.parent, c.index);
    assert.equal(JSON.stringify(t), before, `${c.name}: вхід зачеплено`);
    assert.equal(r.err ?? null, c.err, c.name);
    if (c.err) continue;
    if (c.noop) {
      assert.equal(r.noop, true, c.name);
      assert.equal(JSON.stringify(r.tree), before, c.name);
    } else {
      assert.notEqual(r.noop, true, c.name);
    }
    for (const [id, kids] of Object.entries(c.order ?? {})) {
      assert.deepEqual((findNode(r.tree, id).node.children ?? []).map((x) => x.id), kids, c.name);
    }
    for (const [id, k] of Object.entries(c.kinds ?? {})) {
      assert.equal(flatten(r.tree).find((f) => f.page.id === id).kind, k, c.name);
    }
  }
});

test("kindOf — вивід для легасі", () => {
  assert.equal(kindOf({}, "page"), "state");
  assert.equal(kindOf({ isGroup: true }, "page"), "folder");
  assert.equal(kindOf({}, "folder"), "page");
  assert.equal(kindOf({ kind: "page" }, "page"), "page");
});

test("flatten — усі рівні з parent/depth/kind", () => {
  const t = tree("BASE");
  assert.deepEqual(flatten(t).map((f) => [f.page.id, f.parent, f.depth, f.kind]), [
    ["p", null, 0, "page"], ["w", "p", 1, "folder"], ["s1", "w", 2, "state"],
    ["s2", "w", 2, "state"], ["q", null, 0, "page"], ["t1", "q", 1, "state"]]);
  assert.deepEqual(pathOf(t, "s2").map((n) => n.id), ["p", "w", "s2"]);
});

test("planMove — три зони перетворюються на (parent, index) без пастки зсуву", () => {
  const t = tree("BASE");
  // s1 кинуто ПІСЛЯ s2 — у тому ж батьку, після виймання s1 індекс s2 = 0 → 1
  const a = planMove(t, ["s1"], "s2", "after");
  assert.deepEqual([a.parent, a.index], ["w", 1]);
  assert.deepEqual(findNode(a.tree, "w").node.children.map((x) => x.id), ["s2", "s1"]);
  const b = planMove(t, ["t1"], "w", "inside");
  assert.deepEqual(findNode(b.tree, "w").node.children.map((x) => x.id), ["s1", "s2", "t1"]);
  assert.equal(b.index, 2, "у запит іде фактична позиція, не MAX_SAFE_INTEGER");
  const c = planMove(t, ["t1"], "w", "first");
  assert.deepEqual(findNode(c.tree, "w").node.children.map((x) => x.id), ["t1", "s1", "s2"]);
  assert.equal(planMove(t, ["w"], null, "end").err, "state-outside-page");
  assert.equal(planMove(t, ["p"], "s1", "before").err, "cycle");
  assert.equal(planMove(t, ["q"], "q", "inside").err, "self");
  assert.equal(planMove(t, ["q"], "p", "after").noop, true);
  // тягнуть s1 «перед» s2 — вона вже там: без виймання з rest індекс збивався б
  assert.equal(planMove(t, ["s1"], "s2", "before").noop, true);
});

test("applyMove чіпає лише вузли, яких торкнулась дія", () => {
  const t = [
    { id: "r", name: "R", kind: "page", children: [] },
    { id: "a", name: "A", kind: "page" },
    { id: "b", name: "B", kind: "page", children: [{ id: "x", name: "X", kind: "state" }] },
  ];
  const r = applyMove(t, ["x"], "a", 0);
  assert.deepEqual(r.tree.find((n) => n.id === "r").children, [], "сторонній children: [] лишився");
  assert.equal("children" in r.tree.find((n) => n.id === "b"), false, "старий батько прибрано");
});

test("applyMove не падає на сміттєвому вході — відмовляє кодом", () => {
  assert.equal(applyMove([null], ["p"], null, 0).err, "bad-id");
  assert.equal(applyMove([{ id: 5, name: "P" }], ["p"], null, 0).err, "bad-id");
  assert.equal(applyMove([{ id: "p", name: "P", kind: "zzz" }], ["p"], null, 0).err, "bad-kind");
  assert.equal(applyMove([{ id: "p", name: "P" }], ["p"], null, 1.5).err, "bad-index");
});

test("topIds і statsOf", () => {
  const t = tree("BASE");
  assert.deepEqual(topIds(t, ["s1", "w", "q"]), ["w", "q"]);
  assert.deepEqual(statsOf(findNode(t, "p").node, null), { pages: 0, states: 2, folders: 1 });
});

const ids = (r, id) => findNode(r.tree, id).node.children.map((x) => x.id);

test("planMove: кілька id — у порядку дерева, index = позиція першого", () => {
  const t = tree("BASE");
  const b = planMove(t, ["s2", "s1"], "t1", "before");
  assert.deepEqual([b.parent, b.index, b.ids], ["q", 0, ["s1", "s2"]]);
  assert.deepEqual(ids(b, "q"), ["s1", "s2", "t1"]);
  const a = planMove(t, ["s2", "s1"], "t1", "after");
  assert.deepEqual([a.parent, a.index, a.ids], ["q", 1, ["s1", "s2"]]);
  assert.deepEqual(ids(a, "q"), ["t1", "s1", "s2"]);
});

test("planMove: після останнього, перед першим, зі зміною батька", () => {
  const t = tree("BASE");
  const last = planMove(t, ["s1"], "t1", "after");
  assert.deepEqual([last.parent, last.index], ["q", 1]);
  assert.deepEqual(ids(last, "q"), ["t1", "s1"]);
  const first = planMove(t, ["t1"], "s1", "before");
  assert.deepEqual([first.parent, first.index], ["w", 0]);
  assert.deepEqual(ids(first, "w"), ["t1", "s1", "s2"]);
});

test("planMove: inside батька, якому вузол уже належить, — у кінець", () => {
  const t = tree("BASE");
  const r = planMove(t, ["s1"], "w", "inside");
  assert.equal(r.noop ?? false, false);
  assert.deepEqual(ids(r, "w"), ["s2", "s1"]);
  assert.equal(r.index, 1);
  const last = planMove(t, ["s2"], "w", "inside");
  assert.equal(last.noop, true);
});

test("planMove: end — явна гілка, bad-where — відмова, а не тихий корінь", () => {
  const t = tree("BASE");
  const e = planMove(t, ["p"], null, "end");
  assert.deepEqual([e.parent, e.index], [null, 1]);
  assert.deepEqual(e.tree.map((x) => x.id), ["q", "p"]);
  const w = planMove(t, ["s1"], "s2", "sideways");
  assert.deepEqual([w.err, w.parent, w.index, w.ids], ["bad-where", null, null, ["s1"]]);
  assert.equal(w.tree, undefined);
});

test("planMove: форма відповіді однакова, на відмові parent/index = null", () => {
  const t = tree("BASE");
  for (const [args, code] of [
    [[["w"], null, "end"], "state-outside-page"],
    [[["p"], "s1", "before"], "cycle"],
    [[["q"], "q", "inside"], "self"],
    [[["q"], "zzz", "before"], "not-found"],
    [[["zzz"], null, "end"], "not-found"],
    [[["q"], null, "nope"], "bad-where"],
    [["q", null, "end"], "bad-ids"],
  ]) {
    const r = planMove(t, ...args);
    assert.equal(r.err, code, code);
    assert.equal(r.parent, null, code);
    assert.equal(r.index, null, code);
    assert.ok(Array.isArray(r.ids), code);
  }
  const ok = planMove(t, ["s1"], "s2", "after");
  assert.ok(Number.isInteger(ok.index) && "parent" in ok && Array.isArray(ok.ids));
});

test("applyMove: ids не масив — bad-ids", () => {
  assert.equal(applyMove(tree("BASE"), "q", null, 0).err, "bad-ids");
  assert.equal(applyMove(tree("BASE"), undefined, null, 0).err, "bad-ids");
});

test("кожен код відмови має ключ словника; errKey невідомого — null", () => {
  const codes = new Set(["state-outside-page", "state-has-children", "cycle", "self", "not-siblings",
    "too-deep", "bad-kind", "not-found", "stale", "bad-id", "bad-index", "dup-id", "empty-name",
    "bad-where", "bad-ids"]);
  for (const c of [...RULES.validate, ...RULES.move]) if (c.err) codes.add(c.err);
  for (const c of codes) {
    assert.match(errKey(c) ?? "", /^tree[A-Z]/, c);
    assert.equal(errKey(c), ERR_KEY[c], c);
  }
  assert.equal(errKey("no-such-code"), null);
  assert.equal(errKey("toString"), null, "прототип не вважається кодом");
  assert.equal(errKey(undefined), null);
});

test("visibleIds: прихована тека ховає сторінки під собою, теки самі — у наборі, коли видимі", () => {
  const pages = [
    { id: "f", name: "F", kind: "folder", published: false, children: [
      { id: "p", name: "P", kind: "page" }] },
    { id: "g", name: "G", kind: "folder", children: [{ id: "q", name: "Q", kind: "page" }] }];
  assert.deepEqual([...visibleIds(pages)].sort(), ["g", "q"]);
});

test("visibleIds: явне published:true під схованим предком лишається схованим", () => {
  const pages = [{ id: "p", name: "P", kind: "page", published: false, children: [
    { id: "s", name: "S", kind: "state", published: true }] }];
  assert.equal(visibleIds(pages).size, 0);
});

test("visibleIds: ховає лише буквальне false", () => {
  const pages = [{ id: "a", name: "A", published: 0 }, { id: "b", name: "B", published: null },
    { id: "c", name: "C", published: "false" }, { id: "d", name: "D", published: false }];
  assert.deepEqual([...visibleIds(pages)], ["a", "b", "c"]);
});

test("кожен код відмови має переклад в обох мовах", () => {
  for (const [code, key] of Object.entries(ERR_KEY)) {
    assert.ok(key in DICT.uk && key in DICT.en, `${code} → ${key} без перекладу`);
  }
});

test("busy (503) має свій ключ — «зайнято» не плутається з «змінилось»", () => {
  assert.equal(errKey("busy"), "treeBusy");
});

test("visibleRows: згорнутий предок ховає всю гілку; фокус робить вузол коренем; фільтр розкриває шлях", () => {
  const t = tree("BASE");
  const ids = (o) => visibleRows(t, o).map((r) => [r.page.id, r.depth]);
  assert.deepEqual(ids({ expanded: new Set(["p"]) }), [["p", 0], ["w", 1], ["q", 0]]);
  assert.deepEqual(ids({ expanded: new Set(["w"]) }), [["p", 0], ["q", 0]], "онук при згорнутому дідові");
  assert.deepEqual(ids({ expanded: new Set(), focus: "w" }), [["s1", 0], ["s2", 0]]);
  assert.deepEqual(ids({ expanded: new Set(), filter: "помил" }), [["p", 0], ["w", 1], ["s2", 2]]);
});

test("visibleRows: фокус на згорнутій гілці лишає її вміст видимим; невідомий фокус = без фокуса", () => {
  const t = tree("BASE");
  const ids = (o) => visibleRows(t, o).map((r) => [r.page.id, r.depth]);
  // предки САМОГО фокусу (p) не мусять бути розгорнуті — вузол і так корінь показу
  assert.deepEqual(ids({ expanded: new Set(["w"]), focus: "w" }), [["s1", 0], ["s2", 0]]);
  assert.deepEqual(ids({ expanded: new Set(), focus: "zzz" }), [["p", 0], ["q", 0]]);
});

test("visibleRows: фільтр без регістру, пробіли по краях, порожній збіг; у фокусі шукає лише всередині", () => {
  const t = tree("BASE");
  const ids = (o) => visibleRows(t, o).map((r) => r.page.id);
  assert.deepEqual(ids({ expanded: new Set(), filter: "  ОСОБА " }), ["q"]);
  assert.deepEqual(ids({ expanded: new Set(), filter: "нема такого" }), []);
  // «Порожньо» є і під w (s1), і під q (t1): у фокусі на w — лише s1
  assert.deepEqual(ids({ expanded: new Set(), filter: "порожньо", focus: "w" }), ["s1"]);
  assert.deepEqual(ids({ expanded: new Set(), filter: "порожньо" }), ["p", "w", "s1", "q", "t1"]);
});

test("visibleRows: kind і parent переходять із flatten; вхід не мутується", () => {
  const t = tree("BASE");
  const before = JSON.stringify(t);
  const r = visibleRows(t, { expanded: new Set(["p"]) });
  assert.deepEqual(r.map((x) => [x.page.id, x.parent, x.kind]), [["p", null, "page"], ["w", "p", "folder"], ["q", null, "page"]]);
  assert.equal(JSON.stringify(t), before);
});

test("stepRow: сусід за напрямком; на краях — null; невідомий поточний — перший/останній", () => {
  const rows = visibleRows(tree("BASE"), { expanded: new Set(["p", "w"]) }); // p w s1 s2 q
  assert.equal(stepRow(rows, "p", 1), "w");
  assert.equal(stepRow(rows, "w", -1), "p");
  assert.equal(stepRow(rows, "p", -1), null);
  assert.equal(stepRow(rows, "q", 1), null);
  assert.equal(stepRow(rows, "zzz", 1), "p");
  assert.equal(stepRow(rows, "zzz", -1), "q");
  assert.equal(stepRow([], "p", 1), null);
});

test("firstChildRow: перша дитина лише коли вона ВИДИМА одразу після вузла", () => {
  const open = visibleRows(tree("BASE"), { expanded: new Set(["p", "w"]) });
  assert.equal(firstChildRow(open, "p"), "w");
  assert.equal(firstChildRow(open, "w"), "s1");
  const shut = visibleRows(tree("BASE"), { expanded: new Set() });
  assert.equal(firstChildRow(shut, "p"), null, "згорнутий — дитини в списку нема");
  assert.equal(firstChildRow(open, "s1"), null, "листок");
});

test("rowRange: діапазон між опорою й кінцем у видимому порядку, в обидва боки; невідомий кінець — null", () => {
  const rows = visibleRows(tree("BASE"), { expanded: new Set(["p", "w"]) }); // p w s1 s2 q
  assert.deepEqual(rowRange(rows, "w", "s2"), ["w", "s1", "s2"]);
  assert.deepEqual(rowRange(rows, "s2", "w"), ["w", "s1", "s2"]);
  assert.deepEqual(rowRange(rows, "q", "q"), ["q"]);
  assert.equal(rowRange(rows, "zzz", "q"), null);
});
