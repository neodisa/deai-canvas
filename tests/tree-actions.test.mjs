import assert from "node:assert/strict";
import test from "node:test";
import {
  DELETE_LIST_CAP, deleteDialogModel, groupTargetIds, pageMenuItems, runSequential,
  shouldRefreshPanel, treeBusyGate, treeTarget,
} from "../app/tree-actions.js";

const P = (id, children, extra = {}) => ({ id, name: id.toUpperCase(), ...(children ? { children } : {}), ...extra });

test("pageMenuItems: матриця типів", () => {
  const m = (o) => pageMenuItems(o);
  assert.deepEqual(m({ kind: "state", hasParent: true }),
    ["rename", "group", "out", "kind", "pub", "delete"]);
  assert.deepEqual(m({ kind: "page" }), ["folder", "rename", "group", "kind", "pub", "delete"]);
  assert.deepEqual(m({ kind: "page", hasChildren: true, hasParent: true, canUp: true, canDown: true }),
    ["folder", "rename", "group", "up", "down", "out", "focus", "kind", "pub", "delete"]);
  assert.deepEqual(m({ kind: "folder", hasChildren: true }),
    ["folder", "rename", "group", "ungroup", "focus", "pub", "delete"]);
  assert.deepEqual(m({ kind: "folder", hasChildren: false }),
    ["folder", "rename", "group", "pub", "delete"]);
  assert.deepEqual(m({ kind: "page", multi: true, hasParent: true }), ["group", "delete"]);
});

test("treeTarget / groupTargetIds", () => {
  assert.equal(treeTarget(new Set(["a"]), "p"), "a");
  assert.equal(treeTarget(new Set(["a", "b"]), "p"), "p");
  assert.equal(treeTarget(new Set(), null), null);
  assert.deepEqual(groupTargetIds(new Set(["a", "b"]), "p"), ["a", "b"]);
  assert.deepEqual(groupTargetIds(new Set(), "p"), ["p"]);
  assert.deepEqual(groupTargetIds(new Set(), null), []);
});

test("deleteDialogModel: лист — yesno; тека з вмістом — choice з unwrap", () => {
  const tree = [P("a"), P("f", [P("x"), P("y", [P("z")])], { kind: "folder" })];
  assert.equal(deleteDialogModel(tree, ["a"]).kind, "yesno");
  const m = deleteDialogModel(tree, ["f"]);
  assert.equal(m.kind, "choice");
  assert.equal(m.unwrap, true);
  assert.deepEqual(m.names, ["X", "Y", "Z"]);
  assert.deepEqual(m.titleArgs, ["F", 3]);
  assert.equal(deleteDialogModel(tree, ["nope"]), null);
});

test("deleteDialogModel: unwrap лише коли підняття валідне (сторінка зі станами в корені — ні)", () => {
  const S = (id) => P(id, null, { kind: "state" });
  // кореневу сторінку зі станами прибрати «з підняттям» не можна: стани опинились би в корені
  const root = [P("p", [S("s1"), S("s2")], { kind: "page" })];
  const m = deleteDialogModel(root, ["p"]);
  assert.equal(m.kind, "choice");
  assert.equal(m.unwrap, false);
  // та сама сторінка всередині теки — стан теж лишається без сторінки
  const inFolder = [P("f", [P("p", [S("s1")], { kind: "page" })], { kind: "folder" })];
  assert.equal(deleteDialogModel(inFolder, ["p"]).unwrap, false);
  // а підсторінки сторінка піднімає спокійно
  const pages = [P("p", [P("c", null, { kind: "page" })], { kind: "page" })];
  assert.equal(deleteDialogModel(pages, ["p"]).unwrap, true);
  // легасі: дитина кореневої сторінки без kind — стан, піднімати нікуди
  assert.equal(deleteDialogModel([P("f", [P("x")])], ["f"]).unwrap, false);
  // теку зі станами всередині сторінки прибрати можна (стани лишаються в сторінці)
  const w = [P("p", [P("w", [S("s")], { kind: "folder" })], { kind: "page" })];
  assert.equal(deleteDialogModel(w, ["w"]).unwrap, true);
});

test("deleteDialogModel: множинний — список із нащадками, без unwrap, без дублів вкладених", () => {
  const tree = [P("a"), P("f", [P("x")]), P("b")];
  const m = deleteDialogModel(tree, ["a", "f", "x"]);
  assert.equal(m.kind, "choice");
  assert.equal(m.unwrap, false);
  assert.deepEqual(m.ids, ["a", "f"]);
  assert.deepEqual(m.names, ["A", "F", "X"]);
  assert.equal(m.titleKey, "delManyTitle");
  assert.deepEqual(m.titleArgs, [2, 3]);
});

test("deleteDialogModel: обрізання до 30 і «ще N»", () => {
  const kids = Array.from({ length: 35 }, (_, i) => P(`k${i}`));
  const m = deleteDialogModel([P("f", kids)], ["f"]);
  assert.equal(m.names.length, DELETE_LIST_CAP);
  assert.equal(m.more, 5);
  const exact = deleteDialogModel([P("f", kids.slice(0, 30))], ["f"]);
  assert.equal(exact.more, 0);
  const many = deleteDialogModel(kids, kids.map((k) => k.id));
  assert.equal(many.names.length, 30);
  assert.equal(many.more, 5);
});

test("runSequential: усе проходить", async () => {
  const seen = [];
  const r = await runSequential(["a", "b"], async (id) => { seen.push(id); return true; });
  assert.deepEqual(r, { done: ["a", "b"], failed: [], stopped: false });
  assert.deepEqual(seen, ["a", "b"]);
});

test("runSequential: stillValid=false після першого кроку — решта НЕ виконується", async () => {
  let it = "it1";
  const seen = [];
  const r = await runSequential(["a", "b", "c"], async (id) => { seen.push(id); it = "it2"; return true; },
    { stillValid: () => it === "it1" });
  assert.deepEqual(seen, ["a"]);
  assert.deepEqual(r, { done: ["a"], failed: [], stopped: true });
});

test("runSequential: часткова відмова зупиняє цикл і називає id", async () => {
  const seen = [];
  const r = await runSequential(["a", "b", "c"], async (id) => { seen.push(id); return id !== "b"; });
  assert.deepEqual(seen, ["a", "b"]);
  assert.deepEqual(r, { done: ["a"], failed: ["b"], stopped: false });
});

test("treeBusyGate: перекритий run → null без виклику; throw знімає замок", async () => {
  const flips = [];
  const g = treeBusyGate((b) => flips.push(b));
  let release;
  const first = g.run(() => new Promise((res) => { release = res; }));
  assert.equal(g.busy, true);
  let called = false;
  assert.equal(await g.run(async () => { called = true; return 1; }), null);
  assert.equal(called, false);
  release("ok");
  assert.equal(await first, "ok");
  assert.equal(g.busy, false);
  await assert.rejects(g.run(async () => { throw new Error("x"); }), /x/);
  assert.equal(g.busy, false, "виняток лишив замок");
  assert.equal(await g.run(async () => 7), 7);
  assert.deepEqual(flips, [true, false, true, false, true, false]);
});

import { composeDeleteNote } from "../app/tree-actions.js";
const fakeT = (k, ...a) => `${k}:${a.join("|")}`;
test("composeDeleteNote: причина не губиться, зупинка й успіх — тиша", () => {
  assert.equal(composeDeleteNote(fakeT, { done: 2, total: 2 }), null);
  assert.equal(composeDeleteNote(fakeT, { done: 1, total: 3, stopped: true, why: "x" }), null);
  assert.equal(composeDeleteNote(fakeT, { done: 1, total: 3, why: "boom" }), "delPartialWhy:1|3|boom");
  assert.equal(composeDeleteNote(fakeT, { done: 1, total: 3 }), "delPartial:1|3");
  assert.equal(composeDeleteNote(fakeT, { done: 0, total: 1, why: "boom" }), "boom");
  assert.equal(composeDeleteNote(fakeT, { done: 0, total: 1 }), null);
});

test("dropZone: контейнер ділиться на 25/50/25, стан — навпіл", async () => {
  const { dropZone } = await import("../app/tree-actions.js");
  const z = (y, o = {}) => dropZone({ y, top: 100, height: 40, kind: "folder", expanded: false, hasKids: false, filtering: false, ...o });
  assert.equal(z(103), "before");
  assert.equal(z(120), "inside");
  assert.equal(z(138), "after");
  // межі: рівно 25% і 75% — вже «всередину»
  assert.equal(z(110), "inside");
  assert.equal(z(130), "inside");
  // стан не вміщає: верхня половина — перед, нижня — після
  assert.equal(z(110, { kind: "state" }), "before");
  assert.equal(z(120, { kind: "state" }), "after");
  assert.equal(z(117, { kind: "state" }), "before");   // 42% — ще верхня половина
  // сторінка вміщає (стани всередині)
  assert.equal(z(120, { kind: "page" }), "inside");
});

test("dropZone: «після» розгорнутого контейнера з дітьми = перша дитина", async () => {
  const { dropZone } = await import("../app/tree-actions.js");
  const o = { top: 0, height: 40, kind: "folder", hasKids: true, expanded: true, filtering: false };
  assert.equal(dropZone({ y: 39, ...o }), "first");
  // згорнутий або порожній — звичайне «після»
  assert.equal(dropZone({ y: 39, ...o, expanded: false }), "after");
  assert.equal(dropZone({ y: 39, ...o, hasKids: false }), "after");
  // під фільтром гілки розкриті примусово, а перша дитина може бути відфільтрована
  assert.equal(dropZone({ y: 39, ...o, filtering: true }), "after");
  // стан із дітьми не «першує»: вміщати нікого
  assert.equal(dropZone({ y: 39, ...o, kind: "state" }), "after");
});

test("dropZone: нульова висота не дає NaN-зони", async () => {
  const { dropZone } = await import("../app/tree-actions.js");
  assert.equal(dropZone({ y: 5, top: 5, height: 0, kind: "page", expanded: false, hasKids: false, filtering: false }), "before");
});

test("shouldCommitDrop: ітерація змінилась / скасовано / err / noop — без запиту", async () => {
  const { shouldCommitDrop } = await import("../app/tree-actions.js");
  const ok = { commit: true, plan: { ids: ["a"], parent: null, index: 0 }, startIt: "i1", currentIt: "i1" };
  assert.equal(shouldCommitDrop(ok), true);
  assert.equal(shouldCommitDrop({ ...ok, currentIt: "i2" }), false);
  assert.equal(shouldCommitDrop({ ...ok, commit: false }), false);
  assert.equal(shouldCommitDrop({ ...ok, plan: null }), false);
  assert.equal(shouldCommitDrop({ ...ok, plan: { err: "cycle" } }), false);
  assert.equal(shouldCommitDrop({ ...ok, plan: { noop: true } }), false);
});

test("resolveDrop: кінець кореня, порожнеча у фокусі, перша дитина, self тихий", async () => {
  const { resolveDrop, zoneOfHit } = await import("../app/tree-actions.js");
  const pages = [P("a", [P("a1"), P("a2")], { kind: "folder" }), P("b"), P("c", [P("c1")])];
  const st = { expanded: new Set(["a"]), filtering: false, focus: null };
  const row = (id, y) => ({ kind: "row", id, y, top: 0, height: 40 });
  // порожнеча без фокуса — кінець кореня, підсвічується fill
  const e = resolveDrop(pages, ["b"], { kind: "fill" }, st);
  assert.equal(e.where, "end"); assert.equal(e.target, null); assert.equal(e.fill, true);
  assert.deepEqual(e.plan.parent, null);
  // порожнеча у фокусі — усередину фокусної гілки
  const f = resolveDrop(pages, ["b"], { kind: "fill" }, { ...st, focus: "c" });
  assert.equal(f.where, "inside"); assert.equal(f.target, "c"); assert.equal(f.plan.parent, "c"); assert.equal(f.fill, true);
  // «після» розгорнутої теки з дітьми — перша дитина, лінія над нею
  const first = resolveDrop(pages, ["b"], row("a", 39), st);
  assert.equal(first.where, "first"); assert.deepEqual(first.mark, { row: "a1", cls: "row--drop-before" });
  // середина — рамка на весь рядок
  assert.deepEqual(resolveDrop(pages, ["b"], row("c", 20), st).mark, { row: "c", cls: "row--in" });
  // self: тихо, без червоного
  const s = resolveDrop(pages, ["b"], row("b", 20), st);
  assert.equal(s.quiet, true); assert.equal(s.mark.cls, null);
  // цикл: червоний рядок і причина
  const cyc = resolveDrop(pages, ["a"], row("a1", 20), st);
  assert.equal(cyc.quiet, false); assert.equal(cyc.mark.cls, "row--nope"); assert.equal(cyc.plan.err, "cycle");
  // поза деревом — нічого
  assert.equal(resolveDrop(pages, ["b"], null, st).where, null);
  assert.equal(zoneOfHit(pages, row("c", 20), st).target, "c");
});

test("shouldRefreshPanel: до запиту — лише коли тихо й ітерація обрана", () => {
  const ok = { it: "it2", current: "it2" };
  assert.equal(shouldRefreshPanel(ok), true);
  assert.equal(shouldRefreshPanel({ ...ok, current: null, it: null }), false, "нема обраної ітерації");
  assert.equal(shouldRefreshPanel({ ...ok, busy: true }), false, "запит дерева в дорозі");
  assert.equal(shouldRefreshPanel({ ...ok, dragging: true }), false, "жест перетягування");
  assert.equal(shouldRefreshPanel({ ...ok, askOpen: true }), false, "відкритий діалог");
  assert.equal(shouldRefreshPanel({ ...ok, current: "it3" }), false, "ітерацію перемкнули");
});

test("shouldRefreshPanel: після запиту — лише коли rev змінився (і досі тихо, і та сама ітерація)", () => {
  const ok = { it: "it2", current: "it2", seenRev: "aaa" };
  assert.equal(shouldRefreshPanel({ ...ok, rev: "aaa" }), false, "той самий rev — нічого не міняємо");
  assert.equal(shouldRefreshPanel({ ...ok, rev: "bbb" }), true);
  assert.equal(shouldRefreshPanel({ ...ok, rev: "" }), true, "файл зник — це теж зміна");
  assert.equal(shouldRefreshPanel({ ...ok, rev: "bbb", busy: true }), false, "за час запиту почали писати");
  assert.equal(shouldRefreshPanel({ ...ok, rev: "bbb", dragging: true }), false);
  assert.equal(shouldRefreshPanel({ ...ok, rev: "bbb", askOpen: true }), false);
  assert.equal(shouldRefreshPanel({ ...ok, rev: "bbb", current: "it3" }), false, "відповідь про іншу ітерацію");
  assert.equal(shouldRefreshPanel({ ...ok, rev: undefined }), true, "без rev — це перевірка «до запиту»");
  assert.equal(shouldRefreshPanel({ ...ok, rev: null }), false, "не-рядок rev — відповідь зіпсована, не чіпаємо");
});

test("vanishedFolders: чужий перезапис без тек → назви зниклих (fb-01102026-71980b)", async () => {
  const { vanishedFolders } = await import("../app/tree-actions.js");
  const next = [{ id: "a", name: "a", kind: "page" }, { id: "c", name: "c", kind: "page" }];
  assert.deepEqual(vanishedFolders({ prev: VF_PREV, next, prevRev: "r1", nextRev: "r2" }),
    [{ id: "f", name: "Віджет" }, { id: "g", name: "Друга" }]);
});

test("vanishedFolders: власна дія (rev той самий, що дала наша відповідь) — мовчимо", async () => {
  const { vanishedFolders } = await import("../app/tree-actions.js");
  assert.deepEqual(vanishedFolders({ prev: VF_PREV, next: [], prevRev: "r2", nextRev: "r2" }), []);
});

test("vanishedFolders: перше читання (prevRev порожній) — мовчимо", async () => {
  const { vanishedFolders } = await import("../app/tree-actions.js");
  assert.deepEqual(vanishedFolders({ prev: [], next: [], prevRev: "", nextRev: "r1" }), []);
});

test("vanishedFolders: теки на місці, змінились лише сторінки — мовчимо", async () => {
  const { vanishedFolders } = await import("../app/tree-actions.js");
  const next = [...VF_PREV, { id: "d", name: "D", kind: "page" }];
  assert.deepEqual(vanishedFolders({ prev: VF_PREV, next, prevRev: "r1", nextRev: "r2" }), []);
});

/* Дерево панелі ДО чужого перезапису: дві теки й сторінка. */
const VF_PREV = [
  { id: "f", name: "Віджет", kind: "folder", children: [{ id: "a", name: "A", kind: "page" }] },
  { id: "g", name: "Друга", kind: "folder", children: [] },
  { id: "c", name: "C", kind: "page" },
];

test("vanishedFolders: дерево ІНШОЇ ітерації — не тривога (ревʼю 1.47, W1)", async () => {
  const { vanishedFolders } = await import("../app/tree-actions.js");
  assert.deepEqual(vanishedFolders({ prev: VF_PREV, next: [], prevRev: "r1", nextRev: "r2",
    prevIt: "it1", it: "it2" }), []);
  assert.equal(vanishedFolders({ prev: VF_PREV, next: [], prevRev: "r1", nextRev: "r2",
    prevIt: "it1", it: "it1" }).length, 2, "та сама ітерація мусить тривожитись");
});
