import assert from "node:assert/strict";
import test from "node:test";
import {
  WZ_STEPS, allOk, errOffRows, holdersByRole, initialPick, offRows, pickModule, pickNone, pickedFor, pickedInOrder, prevStep,
  prunePick, staleRoles, titleFromFolder, wizardSections, writePlan,
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

test("вибрані — у порядку секцій; модуль кількох ролей — один раз, на першій", () => {
  const list = [...LIST, M("multi", ["tokens", "publish"])];
  const p = new Set(["multi", "supabase-comments"]);
  assert.deepEqual(pickedInOrder(list, p).map((e) => e.id), ["multi", "supabase-comments"],
    "multi стоїть і в publish, і в tokens — але в результаті раз, на першій секції");
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

test("план: enable зі stale НЕ звільняє ролі — disable тримача кількох ролей лишається в плані (застарілий за ролями тримача)", () => {
  const list = [M("multi", ["publish", "comments"], { enabled: true }), M("memo", ["publish"])];
  /* на кроці 2 публікацію не тримав ніхто (atPick), тепер тримає multi → enable memo застарілий; comments без змін */
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: new Map([["comments", ["multi"]]]) });
  assert.deepEqual(ops.map((o) => [o.op, o.id, o.roles, o.stale]),
    [["enable", "memo", ["publish"], ["publish"]], ["disable", "multi", ["comments"], ["publish"]]],
    "disable лишається в плані (стоїть на ролі comments), але застарілий за publish — контролер його не шле");
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

/* ── рецензія ca594d5: gone без disable, порядок операцій, повні операції, errored-тримач, назва з теки ───────── */

test("gone: вибраний замінник зник — тримач його ролі НЕ вимикається (disable лише для ролей поза gone)", () => {
  const h = M("h", ["publish"], { enabled: true });
  const prevList = [h, M("g", ["publish"])];
  const fresh = [h];
  const ops = writePlan({ list: fresh, pick: new Set(["g"]), forms: new Map(), atPick: holdersByRole(prevList), prevList });
  assert.deepEqual(ops, [{ op: "gone", id: "g", roles: ["publish"], stale: [] }]);
});

test("gone: тримач кількох ролей, одну з яких накрив gone, не вимикається; інша роль без gone — вимикається", () => {
  const mh = M("mh", ["publish", "comments"], { enabled: true });
  const g = M("g", ["publish"]);
  const prevList = [mh, g];
  const atPick = holdersByRole(prevList);
  assert.deepEqual(writePlan({ list: [mh], pick: new Set(["g"]), forms: new Map(), atPick, prevList }),
    [{ op: "gone", id: "g", roles: ["publish"], stale: [] }], "mh тримає і publish: вимкнути його = лишити publish без нікого");
  const c = M("c", ["comments"], { enabled: true });
  const h = M("h", ["publish"], { enabled: true });
  const prev2 = [h, c, g];
  const ops = writePlan({ list: [h, c], pick: new Set(["g"]), forms: new Map(), atPick: holdersByRole(prev2), prevList: prev2 });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["gone", "g"], ["disable", "c"]], "comments gone не накрив — «Без модуля» лишається");
});

test("gone з невідомими ролями (нема в prevList чи prevList нема) — жодного disable взагалі; enable лишаються", () => {
  const h = M("h", ["publish"], { enabled: true });
  const c = M("c", ["comments"], { enabled: true });
  const t = M("t", ["tokens"]);
  const list = [h, c, t];
  for (const prevList of [undefined, [], [h, c, t]]) {
    const ops = writePlan({ list, pick: new Set(["ghost", "t"]), forms: new Map(), atPick: holdersByRole(list), prevList });
    assert.deepEqual(ops, [
      { op: "gone", id: "ghost", roles: [], stale: [] },
      { op: "enable", id: "t", roles: ["tokens"], stale: [] },
    ], String(prevList && prevList.length));
  }
});

test("порядок: gone першими, далі enable/settings у порядку секцій (не «усі enable, потім settings»), disable останніми", () => {
  const list = [
    M("static-publish", ["publish"], { enabled: true, implicit: true, status: "ok" }),
    M("supabase-comments", ["comments"]),
    M("tok", ["tokens"], { enabled: true }),
  ];
  const forms = new Map([["static-publish", form(F, { folder: "a" }, { folder: "b" })]]);
  const pick = new Set(["static-publish", "supabase-comments", "tok", "ghost"]);
  const prevList = [...list, M("ghost", ["tokens"])];
  const ops = writePlan({ list, pick, forms, atPick: holdersByRole(list), prevList });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["gone", "ghost"], ["settings", "static-publish"], ["enable", "supabase-comments"]],
    "settings секції publish раніше за enable секції comments");
  const off = writePlan({ list: [...list, M("old", ["x"], { enabled: true })], pick, forms, atPick: new Map([["x", ["old"]]]), prevList });
  assert.deepEqual(off.map((o) => o.op), ["gone", "settings", "enable", "disable"], "disable — після enable/settings");
});

test("повні операції: op, id, roles, stale — для gone, settings, enable і disable", () => {
  /* на кроці 2 публікацію тримав хтось інший (atPick), токени не тримав ніхто; тепер publish тримає static-publish, а tokens — old */
  const atPick = new Map([["publish", ["other"]], ["comments", []]]);
  const list = [
    M("static-publish", ["publish"], { enabled: true, status: "ok" }),
    M("sb", ["comments"]),
    M("old", ["tokens"], { enabled: true }),
  ];
  const prevList = [...list, M("ghost", ["publish", "comments"])];
  const forms = new Map([["static-publish", form(F, { folder: "a" }, { folder: "b" })]]);
  const ops = writePlan({ list, pick: new Set(["static-publish", "sb", "ghost"]), forms, atPick, prevList });
  assert.deepEqual(ops, [
    { op: "gone", id: "ghost", roles: ["publish", "comments"], stale: [] },
    /* settings: тримачі publish змінились після кроку 2, але роль у settings не міняється — stale завжди [] */
    { op: "settings", id: "static-publish", roles: ["publish"], stale: [] },
    { op: "enable", id: "sb", roles: ["comments"], stale: [] },
    { op: "disable", id: "old", roles: ["tokens"], stale: ["tokens"], after: [] },
  ]);
});

test("errored-тримач звільненої ролі: replace його не вимикає (сервер: _holders лише status ok) — explicit disable, раз на тримача", () => {
  const h = M("h", ["publish"], { enabled: true, status: "error" });
  const memo = M("memo", ["publish"]);
  const list = [h, memo];
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(list) });
  assert.deepEqual(ops, [
    { op: "enable", id: "memo", roles: ["publish"], stale: [] },
    { op: "disable", id: "h", roles: ["publish"], stale: [], after: ["memo"] },
  ]);
  /* два errored-тримачі — обидва, по одному разу */
  const h2 = M("h2", ["publish"], { enabled: true, status: "error" });
  const two = [h, h2, memo];
  assert.deepEqual(writePlan({ list: two, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(two) }).map((o) => [o.op, o.id]),
    [["enable", "memo"], ["disable", "h"], ["disable", "h2"]]);
});

test("тримач зі status ok/unchecked звільненої ролі: replace вимкне сам — окремого disable нема", () => {
  for (const status of ["ok", "unchecked"]) {
    const list = [M("h", ["publish"], { enabled: true, status }), M("memo", ["publish"])];
    const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(list) });
    assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "memo"]], status);
  }
});

test("errored-тримач кількох ролей: звільнена одна, у другій «Без модуля» — один disable, не два", () => {
  const mh = M("mh", ["publish", "comments"], { enabled: true, status: "error" });
  const list = [mh, M("memo", ["publish"])];
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(list) });
  assert.deepEqual(ops.map((o) => [o.op, o.id, o.roles]), [["enable", "memo", ["publish"]], ["disable", "mh", ["comments"]]]);
  assert.deepEqual(ops[1].after, ["memo"], "гілка errored у «Без модуля»: його роль publish звільняє memo — disable чекає на нього");
});

test("errored-тримач: застарілий enable роль не звільняє — окремого disable нема (контролер enable не шле); вибраний не вимикається", () => {
  const h = M("h", ["publish"], { enabled: true, status: "error" });
  const list = [h, M("memo", ["publish"])];
  const stale = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: new Map() });
  assert.deepEqual(stale.map((o) => [o.op, o.id, o.stale]), [["enable", "memo", ["publish"]]]);
  /* людина вибрала САМЕ його (разом із замінником іншої його ролі) — явно вибране не вимикаємо */
  const both = [M("e", ["publish", "tokens"], { enabled: true, status: "error" }), M("memo", ["publish"])];
  const ops = writePlan({ list: both, pick: new Set(["memo", "e"]), forms: new Map(), atPick: holdersByRole(both) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "memo"]]);
});

test("errored-тримач: вимкнений не чіпаємо; а той, що ділить роль зі зниклим, — теж (gone його роль не чіпає)", () => {
  const off = M("off", ["publish"], { enabled: false, status: "error" });
  const memo = M("memo", ["publish"]);
  const list = [off, memo];
  assert.deepEqual(writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(list) }).map((o) => [o.op, o.id]),
    [["enable", "memo"]], "вимкнений errored — не тримач");
  /* memo замінює publish, g (comments) зник; h тримає і publish, і comments, errored — gone накрив його роль comments */
  const h = M("h", ["publish", "comments"], { enabled: true, status: "error" });
  const prevList = [h, memo, M("g", ["comments"])];
  const ops = writePlan({ list: [h, memo], pick: new Set(["memo", "g"]), forms: new Map(), atPick: holdersByRole(prevList), prevList });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["gone", "g"], ["enable", "memo"]]);
});

test("назва з теки: обрізає базу, «.» і «..» — порожньо, хвіст із пробілом і слешем", () => {
  assert.equal(titleFromFolder("/a/b /"), "b");
  assert.equal(titleFromFolder("/a/b / /"), "b");
  assert.equal(titleFromFolder("/a/ b"), "b");
  assert.equal(titleFromFolder("."), "");
  assert.equal(titleFromFolder(".."), "");
  assert.equal(titleFromFolder("~/proj/.."), "");
  assert.equal(titleFromFolder("~/proj/."), "");
  assert.equal(titleFromFolder("./site"), "site");
  assert.equal(titleFromFolder("..hidden"), "..hidden", "лише «.» і «..» цілком — не їхні префікси");
});

/* ── рядки «буде вимкнено» для errored-тримачів звільненої ролі (errOffRows) ──────────────────────────────── */

const rows = (r) => r.map((x) => [x.role, x.holder.id]);
const disableIds = (ops) => ops.filter((o) => o.op === "disable").map((o) => o.id).sort();

test("errOffRows: errored-тримач ролі, яку замінить ще не ввімкнений вибраний модуль", () => {
  const h = M("h", ["publish"], { enabled: true, status: "error" });
  const memo = M("memo", ["publish"]);
  const list = [h, memo];
  assert.deepEqual(rows(errOffRows(list, new Set(["memo"]))), [["publish", "h"]]);
  assert.equal(errOffRows(list, new Set(["memo"]))[0].holder, h, "holder — сам запис списку (для вʼю)");
  assert.deepEqual(errOffRows(list, new Set()), [], "заміни нема — і звільнених ролей нема (це справа offRows)");
});

test("errOffRows: не тримач, не errored, вибраний або вже в offRows — рядка нема", () => {
  const memo = M("memo", ["publish"]);
  const none = (h) => errOffRows([h, memo], new Set(["memo"]));
  assert.deepEqual(none(M("h", ["publish"], { enabled: false, status: "error" })), [], "вимкнений — не тримач");
  assert.deepEqual(none(M("h", ["publish"], { enabled: true, status: "ok" })), [], "replace вимкне сам");
  assert.deepEqual(none(M("h", ["publish"], { enabled: true, status: "unchecked" })), [], "replace вимкне сам");
  assert.deepEqual(none(M("h", ["publish"], { enabled: true, status: "missing" })), [], "missing — не тримач");
  const picked = M("e", ["publish", "tokens"], { enabled: true, status: "error" });
  assert.deepEqual(errOffRows([picked, memo], new Set(["memo", "e"])), [], "явно вибраного не вимикаємо");
  /* уже має рядок «Без модуля» (comments без вибраного) — другого рядка не треба */
  const mh = M("mh", ["publish", "comments"], { enabled: true, status: "error" });
  assert.deepEqual(offRows([mh, memo], new Set(["memo"])).map((o) => o.holder.id), ["mh"]);
  assert.deepEqual(errOffRows([mh, memo], new Set(["memo"])), []);
});

test("errOffRows: звільняють лише ще не ввімкнені вибрані; ввімкнений вибраний нічого не замінює", () => {
  const x = M("x", ["tokens"], { enabled: true, status: "ok" });
  const h = M("h", ["tokens"], { enabled: true, status: "error" });
  assert.deepEqual(errOffRows([x, h], new Set(["x"])), []);
  const y = M("y", ["tokens"]);
  assert.deepEqual(rows(errOffRows([x, h, y], new Set(["y"]))), [["tokens", "h"]]);
});

test("errOffRows: порядок секцій, раз на тримача (на першій звільненій ролі), без сміття на вході", () => {
  const e1 = M("e1", ["comments"], { enabled: true, status: "error" });
  const e2 = M("e2", ["publish"], { enabled: true, status: "error" });
  const both = M("both", ["tokens", "comments", "publish"], { enabled: true, status: "error" });
  const list = [e1, e2, both, M("memo", ["publish"]), M("sb", ["comments"]), M("css", ["tokens"])];
  assert.deepEqual(rows(errOffRows(list, new Set(["memo", "sb", "css"]))), [["publish", "e2"], ["publish", "both"], ["comments", "e1"]],
    "publish раніше за comments; both — один раз, на publish");
  assert.deepEqual(errOffRows(undefined, new Set(["a"])), []);
  assert.deepEqual(errOffRows([null, { id: 3 }], new Set(["a"])), []);
});

test("узгодженість: disable-операції writePlan (без stale й gone) = offRows ∪ errOffRows — вʼю не бреше про те, що вимкнеться", () => {
  const E = (id, roles, status = "error") => M(id, roles, { enabled: true, status });
  const cases = [
    [[E("h", ["publish"]), M("memo", ["publish"])], ["memo"]],
    [[E("mh", ["publish", "comments"]), M("memo", ["publish"])], ["memo"]],
    [[E("h1", ["publish"]), E("h2", ["publish"]), M("memo", ["publish"])], ["memo"]],
    [[E("old", ["tokens"], "ok"), M("memo", ["publish"])], []],
    [[E("e1", ["publish"]), E("c", ["comments"], "ok"), M("sb", ["x"]), M("memo", ["publish"]), M("cm", ["comments"], { enabled: false })], ["memo"]],
    [[E("h", ["publish"]), E("t", ["tokens"], "ok"), M("memo", ["publish"])], ["memo"]],
    [[E("x", ["tokens"], "ok"), E("h", ["tokens"])], ["x"]],
    [[E("s", ["publish"], "ok"), E("v", ["publish"])], ["v"]],
    [[E("s", ["publish"], "ok"), E("v", ["publish"]), M("cm", ["comments"])], ["s", "cm"]],
    [[E("mh", ["publish", "comments"]), E("p", ["publish"], "ok"), M("cm", ["comments"])], ["p", "cm"]],
  ];
  for (const [list, picked] of cases) {
    const pick = new Set(picked);
    const ops = writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list });
    const shown = [...offRows(list, pick), ...errOffRows(list, pick)].map((o) => o.holder.id).sort();
    assert.deepEqual(disableIds(ops), shown, JSON.stringify(list.map((e) => e.id)));
  }
});

test("узгодженість: тримач, якого вимкне сама заміна (ok), має рядок, але окремого disable нема — disable ⊆ рядків", () => {
  const mh = M("mh", ["publish", "comments"], { enabled: true, status: "ok" });
  const list = [mh, M("memo", ["publish"])];
  const pick = new Set(["memo"]);
  const ops = writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list });
  assert.deepEqual(disableIds(ops), []);
  assert.deepEqual(offRows(list, pick).map((o) => o.holder.id), ["mh"], "а рядок «буде вимкнено» є — його вимкне replace");
});

test("errored-тримач: gone накрив ту саму роль, що й вибраний замінник (суперечливий вибір) — disable не шлемо", () => {
  /* типово gone і замінник тієї ж ролі разом не трапляються (pickModule скидає зниклого), але writePlan не мусить на це розраховувати */
  const h = M("h", ["publish"], { enabled: true, status: "error" });
  const memo = M("memo", ["publish"]);
  const prevList = [h, memo, M("g", ["publish"])];
  const ops = writePlan({ list: [h, memo], pick: new Set(["g", "memo"]), forms: new Map(), atPick: holdersByRole(prevList), prevList });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["gone", "g"], ["enable", "memo"]]);
});

/* ── after: disable залежить від enable, що звільняє його роль; Minor 1: два увімкнені тримачі, вибраний уже ввімкнений ── */

const afterOf = (ops) => Object.fromEntries(ops.filter((o) => o.op === "disable").map((o) => [o.id, o.after]));
const E = (id, roles, status = "ok") => M(id, roles, { enabled: true, status });

test("after: звичайний «Без модуля» — []; не чіпає чужі enable; errored-тримач звільненої ролі — id замінника", () => {
  const list = [E("h", ["publish"]), M("cm", ["comments"])];
  const ops = writePlan({ list, pick: new Set(["cm"]), forms: new Map(), atPick: holdersByRole(list) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "cm"], ["disable", "h"]]);
  assert.deepEqual(afterOf(ops), { h: [] }, "enable cm — не про роль h: чекати нема на що");
  const err = [E("e", ["publish"], "error"), M("memo", ["publish"]), M("cm", ["comments"])];
  assert.deepEqual(afterOf(writePlan({ list: err, pick: new Set(["memo", "cm"]), forms: new Map(), atPick: holdersByRole(err) })),
    { e: ["memo"] }, "лише enable з перетином ролей, не всі");
});

test("after: тримач кількох ролей, звільнених двома enable, — обидва id, у порядку секцій", () => {
  const mh = E("mh", ["comments", "publish"], "error");
  const list = [mh, M("zz-pub", ["publish"]), M("aa-com", ["comments"])];
  const ops = writePlan({ list, pick: new Set(["aa-com", "zz-pub"]), forms: new Map(), atPick: holdersByRole(list) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["enable", "zz-pub"], ["enable", "aa-com"], ["disable", "mh"]]);
  assert.deepEqual(afterOf(ops), { mh: ["zz-pub", "aa-com"] }, "publish раніше за comments — не абетка й не порядок вибору");
});

test("after: застарілий enable в after не потрапляє (його контролер не шле)", () => {
  const mh = E("mh", ["publish", "comments"], "error");
  const list = [mh, M("memo", ["publish"])];
  const atPick = new Map([["publish", []], ["comments", ["mh"]]]);
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick });
  assert.deepEqual(ops.map((o) => [o.op, o.id, o.stale, o.after]),
    [["enable", "memo", ["publish"], undefined], ["disable", "mh", ["publish"], []]],
    "after без застарілого enable; а stale disable — за publish (роль тримача, що застаріла): не шлемо");
});

test("after: у Без-модуля-гілці з ok-тримачем звільненої ролі disable нема (replace сам) — отже after не потрібен", () => {
  const list = [E("mh", ["publish", "comments"]), M("memo", ["publish"])];
  assert.deepEqual(writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick: holdersByRole(list) }).map((o) => o.op), ["enable"]);
});

test("offRows: вибраний уже ввімкнений — решта тримачів ролі (не вибрані) теж у рядках", () => {
  const s = E("s", ["publish"], "ok");
  const v = E("v", ["publish"], "error");
  const memo = M("memo", ["publish"]);
  assert.deepEqual(offRows([s, v], new Set(["v"])).map((o) => [o.role, o.holder.id]), [["publish", "s"]]);
  assert.deepEqual(offRows([s, v], new Set(["s"])).map((o) => [o.role, o.holder.id]), [["publish", "v"]]);
  assert.deepEqual(offRows([s, v], new Set(["s", "v"])), [], "обидва вибрані (початковий стан) — нікого вимикати");
  assert.deepEqual(offRows([s, v, memo], new Set(["memo"])).map((o) => o.holder.id), [],
    "вибраний ще не ввімкнений — його replace вимкне тримачів сам (errored — errOffRows)");
  assert.deepEqual(rows(errOffRows([s, v, memo], new Set(["memo"]))), [["publish", "v"]]);
});

test("два увімкнені тримачі однієї ролі: людина вибирає одного — другий вимикається (plain, раз, не вибраний)", () => {
  const s = E("s", ["publish"], "ok");
  const v = E("v", ["publish"], "error");
  const list = [s, v];
  assert.equal(writePlan({ list, pick: initialPick(list), forms: new Map(), atPick: holdersByRole(list) }).length, 0, "початковий вибір — без змін");
  const p = pickModule(initialPick(list), list, "v");
  assert.deepEqual(ids(p), ["v"]);
  assert.deepEqual(writePlan({ list, pick: p, forms: new Map(), atPick: holdersByRole(list) }),
    [{ op: "disable", id: "s", roles: ["publish"], stale: [], after: [] }]);
  assert.deepEqual(writePlan({ list, pick: pickModule(p, list, "s"), forms: new Map(), atPick: holdersByRole(list) }),
    [{ op: "disable", id: "v", roles: ["publish"], stale: [], after: [] }]);
  /* два лишніх тримачі однієї ролі — по одному disable; тримач кількох ролей, лишній у двох, — один */
  const three = [E("a", ["publish"]), E("b", ["publish", "comments"], "error"), E("c", ["publish"])];
  const ops = writePlan({ list: three, pick: new Set(["c"]), forms: new Map(), atPick: holdersByRole(three) });
  assert.deepEqual(ops.map((o) => [o.op, o.id]), [["disable", "a"], ["disable", "b"]]);
});

/* Інваріант: після повністю успішного проходу ввімкнені тримачі ролей = вибір. Сервер у симуляції — найгірший: replace
   вимикає лише тримачів, що точно завантажились (status != error), решту вимикає явний disable з плану. */
function simulate(list, ops) {
  const on = new Map(list.map((e) => [e.id, e.enabled === true]));
  const by = new Map(list.map((e) => [e.id, e]));
  for (const op of ops) {
    if (op.op === "enable") {
      for (const o of list) {
        if (o.id !== op.id && on.get(o.id) && o.status !== "error" && o.roles.some((r) => by.get(op.id).roles.includes(r))) on.set(o.id, false);
      }
      on.set(op.id, true);
    } else if (op.op === "disable") on.set(op.id, false);
  }
  return list.filter((e) => on.get(e.id) && e.roles.length).map((e) => e.id).sort();
}

test("інваріант: після успішного проходу ввімкнені тримачі ролей = вибір (різні списки й вибори)", () => {
  const cases = [
    [[E("s", ["publish"]), E("v", ["publish"], "error"), M("cm", ["comments"]), M("t", ["tokens"])], ["v", "cm"]],
    [[E("s", ["publish"]), E("v", ["publish"], "error"), M("cm", ["comments"])], ["s"]],
    [[E("s", ["publish"]), E("v", ["publish"], "error")], []],
    [[E("mh", ["publish", "comments"], "error"), M("memo", ["publish"]), M("cm", ["comments"])], ["memo", "cm"]],
    [[E("mh", ["publish", "comments"], "error"), M("memo", ["publish"])], ["memo"]],
    [[E("mh", ["publish", "comments"], "ok"), M("memo", ["publish"])], ["memo"]],
    [[E("mh", ["publish", "comments"], "ok"), E("p", ["publish"], "ok")], ["p"]],
    [[E("mh", ["publish", "comments"], "error"), E("p", ["publish"], "ok"), M("cm", ["comments"])], ["p", "cm"]],
    [[E("a", ["publish"], "error"), E("b", ["publish"], "error"), M("memo", ["publish"])], ["memo"]],
    [[E("old", ["tokens"], "unchecked"), M("memo", ["publish"])], ["memo"]],
    [[E("x", ["tokens", "publish"], "error"), E("y", ["comments"], "error"), M("z", ["tokens"]), M("w", ["comments"])], ["z"]],
  ];
  for (const [list, picked] of cases) {
    const pick = new Set(picked);
    const ops = writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list });
    assert.deepEqual(simulate(list, ops), [...pick].sort(), JSON.stringify(list.map((e) => e.id)) + " → " + JSON.stringify(picked));
  }
});

test("інваріант: початковий вибір (усі тримачі) — план порожній, рядків нема", () => {
  for (const list of [[E("s", ["publish"]), E("v", ["publish"], "error")], [E("mh", ["publish", "comments"], "error"), E("t", ["tokens"])], []]) {
    const pick = initialPick(list);
    assert.deepEqual(writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list }), []);
    assert.deepEqual([offRows(list, pick), errOffRows(list, pick)], [[], []]);
  }
});

test("інваріант, вичерпно: усі списки з ≤3 модулів × усі узгоджені вибори — ввімкнені тримачі = вибір, after = enable з перетином ролей", () => {
  const roleSets = [["publish"], ["comments"], ["publish", "comments"], ["tokens"], []];
  const statuses = ["ok", "error", "unchecked"];
  const kinds = roleSets.flatMap((roles) => [false, true].flatMap((enabled) => statuses.map((status) => ({ roles, enabled, status }))));
  const lists = [];
  const build = (acc, n) => {
    if (acc.length === n) { lists.push(acc.map((k, i) => M(`m${i}`, k.roles, { enabled: k.enabled, status: k.status }))); return; }
    for (const k of kinds) build([...acc, k], n);
  };
  for (const n of [1, 2, 3]) build([], n);
  let checked = 0;
  for (const list of lists) {
    for (let mask = 0; mask < (1 << list.length); mask++) {
      const picked = list.filter((_, i) => mask & (1 << i));
      const clash = picked.some((a, i) => !a.roles.length || picked.slice(i + 1).some((b) => a.roles.some((r) => b.roles.includes(r))));
      if (clash) continue;
      const pick = new Set(picked.map((e) => e.id));
      const ops = writePlan({ list, pick, forms: new Map(), atPick: holdersByRole(list), prevList: list });
      const label = `${JSON.stringify(list)} / ${[...pick]}`;
      assert.deepEqual(simulate(list, ops), [...pick].sort(), label);
      for (const o of ops.filter((x) => x.op === "disable")) {
        const mine = list.find((e) => e.id === o.id).roles;
        const want = ops.filter((x) => x.op === "enable" && x.roles.some((r) => mine.includes(r))).map((x) => x.id);
        assert.deepEqual(o.after, want, `after: ${label}`);
      }
      checked += 1;
    }
  }
  assert.ok(checked > 10000, `перебір не порожній (${checked})`);
});

/* ── stale у disable — за ВСІМА ролями тримача (не лише за роллю рядка) ───────────────────────────────────── */

test("stale disable: тримач кількох ролей, застаріла ВЛАСНЕ інша роль — disable застарілий (контролер не шле)", () => {
  /* errored mh тримає publish і comments; на publish вибрано memo (enable застарілий), у comments «Без модуля» */
  const mh = E("mh", ["publish", "comments"], "error");
  const list = [mh, M("memo", ["publish"])];
  const atPick = new Map([["publish", []], ["comments", ["mh"]]]);
  const ops = writePlan({ list, pick: new Set(["memo"]), forms: new Map(), atPick });
  assert.deepEqual(ops, [
    { op: "enable", id: "memo", roles: ["publish"], stale: ["publish"] },
    { op: "disable", id: "mh", roles: ["comments"], stale: ["publish"], after: [] },
  ]);
});

test("stale disable: рядок на одній ролі, змінилась друга роль того ж тримача — stale містить саме її", () => {
  const h = E("h", ["publish", "comments"], "ok");
  const list = [h];
  const atPick = new Map([["publish", ["h"]], ["comments", []]]);
  const ops = writePlan({ list, pick: new Set(), forms: new Map(), atPick });
  assert.deepEqual(ops, [{ op: "disable", id: "h", roles: ["publish"], stale: ["comments"], after: [] }],
    "рядок — publish (перша роль), а застаріла comments");
});

test("stale disable: «вибраний уже ввімкнений» (Minor 1) — теж за всіма ролями тримача", () => {
  const p = E("p", ["publish"], "ok");
  const h = E("h", ["publish", "comments"], "ok");
  const list = [p, h];
  const atPick = new Map([["publish", ["h", "p"]], ["comments", []]]);
  const ops = writePlan({ list, pick: new Set(["p"]), forms: new Map(), atPick });
  assert.deepEqual(ops, [{ op: "disable", id: "h", roles: ["publish"], stale: ["comments"], after: [] }]);
});

test("stale disable: errored-тримач звільненої ролі (pass 2) — теж за всіма ролями; незастарілий enable лишається в after", () => {
  const mh = E("mh", ["publish", "comments"], "error");
  const list = [mh, M("memo", ["publish"]), M("cm", ["comments"])];
  const atPick = new Map([["publish", ["mh"]], ["comments", []]]);
  const ops = writePlan({ list, pick: new Set(["memo", "cm"]), forms: new Map(), atPick });
  assert.deepEqual(ops, [
    { op: "enable", id: "memo", roles: ["publish"], stale: [] },
    { op: "enable", id: "cm", roles: ["comments"], stale: ["comments"] },
    { op: "disable", id: "mh", roles: ["publish"], stale: ["comments"], after: ["memo"] },
  ]);
});

/* ── prunePick: вибір без id, яких модель вважає відсутніми ───────────────────────────────────────────────── */

test("prunePick: лишає присутні, скидає відсутні, missing і сміття; порядок вставки; новий Set, вхід не змінюється", () => {
  const list = [...LIST, M("gone", ["publish"], { status: "missing", enabled: true }), null, { id: 5 }, { id: "" }];
  const pick = new Set(["vercel-publish", "ghost", "gone", "static-publish", 5, "", null, undefined, "css-tokens"]);
  const before = [...pick];
  const out = prunePick(pick, list);
  assert.deepEqual([...out], ["vercel-publish", "static-publish", "css-tokens"], "порядок вставки збережено");
  assert.notEqual(out, pick, "новий Set");
  assert.deepEqual([...pick], before, "вхід не змінено");
  out.add("x");
  assert.equal(pick.has("x"), false, "результат не повʼязаний із входом");
  const all = new Set(["css-tokens", "supabase-comments"]);
  assert.notEqual(prunePick(all, LIST), all, "новий Set і тоді, коли нічого не скинуто");
  assert.deepEqual([...prunePick(all, LIST)], ["css-tokens", "supabase-comments"]);
});

test("prunePick: порожній, null і не-колекція — порожній Set; список-сміття — теж", () => {
  for (const bad of [new Set(), null, undefined, 42, "abc"]) {
    const out = prunePick(bad, LIST);
    assert.ok(out instanceof Set, String(bad));
    assert.equal(out.size, 0, String(bad));
  }
  assert.equal(prunePick(new Set(["css-tokens"]), undefined).size, 0);
  assert.equal(prunePick(new Set(["css-tokens"]), null).size, 0);
  assert.equal(prunePick(new Set(["css-tokens"]), "junk").size, 0);
});

test("prunePick: масив теж приймається (ітерабельне)", () => {
  assert.deepEqual([...prunePick(["css-tokens", "ghost"], LIST)], ["css-tokens"]);
});
