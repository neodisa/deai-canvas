import assert from "node:assert/strict";
import test from "node:test";
import {
  WZ_STEPS, allOk, holdersByRole, initialPick, offRows, pickModule, pickNone, pickedFor, pickedInOrder, prevStep,
  staleRoles, titleFromFolder, wizardSections, writePlan,
} from "../app/wizard-model.js";

const M = (id, roles, extra = {}) => ({ id, name: id, roles, enabled: false, status: "unchecked", settings: [], ...extra });
const LIST = [
  M("css-tokens", ["tokens"]),
  M("static-publish", ["publish"], { enabled: true, implicit: true, status: "ok" }),
  M("supabase-comments", ["comments"]),
  M("vercel-publish", ["publish"]),
];
const ids = (s) => [...s].sort();

test("кроки: чотири, у порядку спеки", () => {
  assert.deepEqual(WZ_STEPS, ["space", "modules", "settings", "task"]);
});

test("секції: ROLE_ORDER, далі інші за абеткою; модуль кількох ролей — у кожній; missing і биті записи — ні", () => {
  const list = [...LIST, M("multi", ["zeta", "publish"]), M("gone", ["publish"], { status: "missing" }),
    null, { id: 5 }, M("alpha", ["alpha"])];
  const s = wizardSections(list);
  assert.deepEqual(s.map((x) => x.role), ["publish", "comments", "tokens", "alpha", "zeta"]);
  assert.deepEqual(s[0].modules.map((e) => e.id), ["static-publish", "vercel-publish", "multi"]);
  assert.deepEqual(s.find((x) => x.role === "zeta").modules.map((e) => e.id), ["multi"]);
  assert.ok(!s.flatMap((x) => x.modules).some((e) => e.id === "gone"));
});

test("роль __proto__ — звичайна роль (Map), не прототип", () => {
  const s = wizardSections([M("x", ["__proto__"])]);
  assert.deepEqual(s.map((x) => x.role), ["__proto__"]);
  assert.deepEqual(holdersByRole([M("x", ["__proto__"], { enabled: true })]).get("__proto__"), ["x"]);
});

test("початковий вибір — поточні тримачі (зокрема неявний static-publish), не missing і не вимкнені", () => {
  assert.deepEqual(ids(initialPick(LIST)), ["static-publish"]);
  const list = [...LIST, M("gone", ["comments"], { enabled: true, status: "missing" })];
  assert.deepEqual(ids(initialPick(list)), ["static-publish"]);
});

test("тримачі за ролями: відсортовані id увімкнених", () => {
  const list = [...LIST, M("alt", ["publish"], { enabled: true })];
  assert.deepEqual(holdersByRole(list).get("publish"), ["alt", "static-publish"]);
  assert.equal(holdersByRole(list).get("tokens"), undefined);
});

test("вибрати модуль прибирає інших тримачів його ролей; невідомий id — без змін", () => {
  const p = pickModule(new Set(["static-publish"]), LIST, "vercel-publish");
  assert.deepEqual(ids(p), ["vercel-publish"]);
  assert.deepEqual(ids(pickModule(p, LIST, "css-tokens")), ["css-tokens", "vercel-publish"]);
  assert.deepEqual(ids(pickModule(p, LIST, "nope")), ["vercel-publish"]);
});

test("модуль кількох ролей: вибір прибирає тримачів УСІХ його ролей; «Без модуля» в одній ролі прибирає його цілком", () => {
  const list = [...LIST, M("multi", ["publish", "comments"])];
  let p = pickModule(new Set(["static-publish", "supabase-comments", "css-tokens"]), list, "multi");
  assert.deepEqual(ids(p), ["css-tokens", "multi"]);
  assert.equal(pickedFor(p, list, "comments"), "multi");
  p = pickNone(p, list, "comments");
  assert.deepEqual(ids(p), ["css-tokens"]);
  assert.equal(pickedFor(p, list, "publish"), null);
});

test("вибрані в порядку секцій, кожен раз", () => {
  const list = [...LIST, M("multi", ["tokens", "publish"])];
  const p = new Set(["css-tokens", "multi", "supabase-comments"].filter((x) => x !== "css-tokens"));
  assert.deepEqual(pickedInOrder(list, p).map((e) => e.id), ["multi", "supabase-comments"]);
});

test("рядки «Без модуля»: роль без вибраного, яку хтось тримає", () => {
  assert.deepEqual(offRows(LIST, new Set()).map((o) => [o.role, o.holder.id]), [["publish", "static-publish"]]);
  assert.deepEqual(offRows(LIST, new Set(["vercel-publish"])), []);
});

const form = (fields, init, cur) => ({ fields, init: { values: init, secrets: {}, erase: [] }, cur: { values: cur, secrets: {}, erase: [] } });
const F = [{ key: "folder", type: "path", required: false, value: "a" }];

test("план: enable з невключеного, settings лише змінений, disable тримача «Без модуля»", () => {
  const atPick = holdersByRole(LIST);
  const pick = new Set(["vercel-publish", "css-tokens"]);
  const forms = new Map([["css-tokens", form(F, { folder: "a" }, { folder: "a" })]]);
  const ops = writePlan({ list: LIST, pick, forms, atPick });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "vercel-publish"], ["enable", "css-tokens"]],
    "static-publish вимкне заміна (replace), окремого disable нема");
  assert.ok(ops.every((o) => o.stale.length === 0));
});

test("план: увімкнений без змін — нічого; змінений — settings", () => {
  const atPick = holdersByRole(LIST);
  const pick = new Set(["static-publish"]);
  assert.deepEqual(writePlan({ list: LIST, pick, forms: new Map([["static-publish", form(F, { folder: "a" }, { folder: " a " })]]), atPick }), []);
  const ops = writePlan({ list: LIST, pick, forms: new Map([["static-publish", form(F, { folder: "a" }, { folder: "b" })]]), atPick });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["settings", "static-publish"]]);
});

test("план: «Без модуля» для публікації — disable static-publish", () => {
  const ops = writePlan({ list: LIST, pick: new Set(), forms: new Map(), atPick: holdersByRole(LIST) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["disable", "static-publish"]]);
});

test("план: тримач кількох ролей іде з заміною в ІНШІЙ ролі — окремого disable нема", () => {
  const list = [M("multi", ["publish", "comments"], { enabled: true }), M("memo", ["publish"]), M("c2", ["comments"])];
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(list) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "memo"]]);
});

test("план: вибраний, якого нема у свіжому списку, — gone", () => {
  const ops = writePlan({ list: LIST, pick: new Set(["static-publish", "ghost"]), forms: new Map(), atPick: holdersByRole(LIST) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["gone", "ghost"]]);
});

test("свіжість: тримачі ролі змінились після кроку 2 — stale у enable і в disable", () => {
  const atPick = holdersByRole(LIST);
  const now = LIST.map((e) => (e.id === "static-publish" ? { ...e, enabled: false } : e)).concat(M("agent", ["publish"], { enabled: true }));
  const ops = writePlan({ list: now, pick: new Set(["vercel-publish"]), forms: new Map(), atPick });
  assert.deepEqual(ops.map((o) => [o.op, o.id, o.stale]), [["enable", "vercel-publish", ["publish"]]]);
  const off = writePlan({ list: now, pick: new Set(), forms: new Map(), atPick });
  assert.deepEqual(off.map((o) => [o.op, o.id, o.stale]), [["disable", "agent", ["publish"]]]);
  assert.deepEqual(staleRoles(["publish", "tokens"], atPick, holdersByRole(now)), ["publish"]);
});

test("результати: усе ok — далі; будь-що інше — ні; порожньо — так", () => {
  assert.equal(allOk([{ kind: "ok" }, { kind: "ok" }]), true);
  assert.equal(allOk([{ kind: "ok" }, { kind: "failed" }]), false);
  assert.equal(allOk([]), true);
});

test("назад: 2→1, 3→2, 4→3, 4→2 коли крок 3 пропущено, 1→1", () => {
  assert.deepEqual([prevStep(2), prevStep(3), prevStep(4), prevStep(4, true), prevStep(1)], [1, 2, 3, 2, 1]);
});

test("назва з теки: останній сегмент без хвостового слеша; «~» і порожнє — ''", () => {
  assert.equal(titleFromFolder("~/work/landing/"), "landing");
  assert.equal(titleFromFolder("/a/b\\c"), "c");
  assert.equal(titleFromFolder("~"), "");
  assert.equal(titleFromFolder("  "), "");
  assert.equal(titleFromFolder(null), "");
});

/* ── охоронці, яких план не покривав (знайдено мутаційним самоаналізом) ───────────────────────────────────── */

test("биті записи не потрапляють нікуди: id не рядок чи порожній, enabled не строго true, ролі-сміття", () => {
  const junk = [M("", ["publish"], { enabled: true }), { id: 5, roles: ["publish"], enabled: true, status: "ok" },
    M("yes", ["publish"], { enabled: "yes" }), M("one", ["publish"], { enabled: 1 }), M("ok", ["publish"], { enabled: true })];
  assert.deepEqual(wizardSections(junk).flatMap((s) => s.modules.map((e) => e.id)).filter((x) => x === "" || x === 5), []);
  assert.deepEqual(holdersByRole(junk).get("publish"), ["ok"], "тримач — лише строго enabled === true і з рядковим id");
  assert.deepEqual(ids(initialPick(junk)), ["ok"]);
  const roles = wizardSections([M("r", [5, "", null, "publish", "publish"])]);
  assert.deepEqual(roles.map((s) => s.role), ["publish"], "не рядкові й порожні ролі відсіюються");
  assert.deepEqual(roles[0].modules.map((e) => e.id), ["r"], "повтор ролі не дублює модуль у секції");
  assert.deepEqual(holdersByRole([M("r", ["publish", "publish"], { enabled: true })]).get("publish"), ["r"]);
});

test("секції: лише ролі, що мають модулі, — не всі з ROLE_ORDER", () => {
  assert.deepEqual(wizardSections([M("p", ["publish"])]).map((s) => s.role), ["publish"]);
  assert.deepEqual(wizardSections([]), []);
  assert.deepEqual(wizardSections(undefined), []);
});

test("початковий вибір: увімкнений модуль без ролей у вибір не йде", () => {
  assert.deepEqual(ids(initialPick([M("bare", [], { enabled: true }), M("noroles", undefined, { enabled: true })])), []);
});

test("вибір і «Без модуля» скидають id, яких уже нема у списку; pickedFor ігнорує missing", () => {
  const gone = M("gone", ["publish"], { status: "missing", enabled: true });
  const list = [...LIST, gone];
  assert.deepEqual(ids(pickModule(new Set(["ghost", "static-publish"]), list, "css-tokens")), ["css-tokens", "static-publish"]);
  assert.deepEqual(ids(pickNone(new Set(["ghost", "css-tokens"]), list, "publish")), ["css-tokens"]);
  assert.equal(pickedFor(new Set(["gone"]), list, "publish"), null, "missing не є постачальником");
  assert.equal(pickedFor(new Set(["ghost"]), list, "publish"), null, "чужого id нема у списку — нема постачальника");
  assert.deepEqual(ids(pickModule(new Set(["static-publish"]), list, "gone")), ["static-publish"], "missing вибрати не можна");
});

test("свіжість: роль, що набула чи втратила тримача, — stale; порожнє з порожнім — ні", () => {
  const none = new Map();
  assert.deepEqual(staleRoles(["publish"], none, new Map([["publish", ["x"]]])), ["publish"], "був нікого — зʼявився хтось");
  assert.deepEqual(staleRoles(["publish"], new Map([["publish", ["x"]]]), none), ["publish"], "був хтось — нікого");
  assert.deepEqual(staleRoles(["publish"], new Map([["publish", ["x", "y"]]]), new Map([["publish", ["x"]]])), ["publish"]);
  assert.deepEqual(staleRoles(["publish"], none, none), []);
  assert.deepEqual(staleRoles(["publish"], undefined, undefined), []);
});

test("план: enable зі stale НЕ звільняє ролі — disable тримача кількох ролей лишається", () => {
  const list = [M("multi", ["publish", "comments"], { enabled: true }), M("memo", ["publish"])];
  /* на кроці 2 публікацію не тримав ніхто (atPick порожній), тепер тримає multi → enable memo застарілий */
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: new Map() });
  assert.deepEqual(ops.map((o) => [o.op, o.id, o.stale]),
    [["enable", "memo", ["publish"]], ["disable", "multi", ["comments"]]]);
});

test("план: вибраний увімкнений без форми — нічого й без винятку", () => {
  const list = [M("on", ["publish"], { enabled: true })];
  assert.deepEqual(writePlan({ list, pick: new Set(["on"]), forms: new Map(), atPick: holdersByRole(list) }), []);
  assert.deepEqual(writePlan({ list, pick: new Set(["on"]), forms: undefined, atPick: holdersByRole(list) }), []);
});

test("план: змінена форма ще не ввімкненого модуля — лише enable (налаштування їдуть разом із ним)", () => {
  const forms = new Map([["css-tokens", form(F, { folder: "a" }, { folder: "b" })]]);
  const ops = writePlan({ list: LIST, pick: new Set(["css-tokens", "static-publish"]), forms, atPick: holdersByRole(LIST) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "css-tokens"]]);
});

test("план: тримач кількох ролей без вибору в жодній — один disable (на першій ролі секцій), не два", () => {
  const list = [M("multi", ["comments", "publish"], { enabled: true })];
  const ops = writePlan({ list, pick: new Set(), forms: new Map(), atPick: holdersByRole(list) });
  assert.deepEqual(ops.map((o) => [o.op, o.id, o.roles]), [["disable", "multi", ["publish"]]]);
});

test("назад: пропущений крок 3 важить лише на кроці 4", () => {
  assert.deepEqual([prevStep(1, true), prevStep(2, true), prevStep(3, true), prevStep(4, true)], [1, 1, 2, 2]);
});

test("назва з теки: слеші-хвости, пробіли, «~/», «/», нерядкове", () => {
  assert.equal(titleFromFolder("  ~/work/x//  "), "x");
  assert.equal(titleFromFolder("~/"), "");
  assert.equal(titleFromFolder("/"), "");
  assert.equal(titleFromFolder(undefined), "");
  assert.equal(titleFromFolder(42), "42");
});
