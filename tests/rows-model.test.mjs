import assert from "node:assert/strict";
import test from "node:test";

import { buildRows } from "../app/rows-model.js";
import { visibleIds } from "../app/tree-model.js";
import { readFileSync } from "node:fs";

/**
 * Дерево сторінок у формі, яку віддає `/api/iteration-pages`
 * (див. заголовок `app/pages_model.py`: два рівні, `isGroup` буває на обох).
 */
const PAGES = [
  { id: "holovna", name: "Головна" },
  { id: "poshuk", name: "Пошук", children: [
    /* Дитина знята з превʼю ОКРЕМО від батька: без цього «крапка успадковується
       від своєї сторінки» не відрізнити від «крапка одна на весь ряд», і
       підміна `page` на верхню сторінку ряду лишилась би зеленою. */
    { id: "poshuk-porozhno", name: "Стан: порожньо", published: false },
    /* Тека ВСЕРЕДИНІ сторінки: охорона по `isGroup` у дітях — окремий рядок від
       охорони на верхньому рівні, і на дереві без вкладеної теки половина
       охорони знімалась би непоміченою. */
    { id: "poshuk-stare", name: "Старе", isGroup: true },
  ] },
  { id: "arhiv", name: "Архів", isGroup: true },
];

/** Вузли графа у формі, яку віддає `readFlow(...).flows[*].nodes`. */
const NODES = [
  { page: "holovna", state: null, key: "holovna", label: "Головна" },
  { page: "holovna", state: "?s=empty", key: "holovna~a1b2c3d4", label: "Головна · порожньо" },
  /* ДРУГИЙ стан тієї самої сторінки: на одному стані порядок станів у ряду не
     закріплений нічим, і `push` → `unshift` лишався б зеленим. */
  { page: "holovna", state: "?s=loading", key: "holovna~99887766", label: "Головна · завантаження" },
  { page: "poshuk-porozhno", state: "?s=slow", key: "poshuk-porozhno~ffffffff", label: "Порожньо · повільно" },
];

/**
 * Тека з дитиною — фікстур `tests/shoot-check.test.mjs` дослівно: саме на
 * такому дереві `nodeList` кладе на диск кадр для «Пошук».
 */
const GROUPED = [
  { id: "holovna", name: "Головна" },
  { id: "grupa", name: "Розділ", isGroup: true,
    children: [{ id: "poshuk", name: "Пошук" }] },
];

test("ряд = сторінка, її стани, її діти і стани дітей — саме в такому порядку", () => {
  const rows = buildRows(PAGES, NODES);
  assert.deepEqual(rows.map((r) => r.map((c) => c.key)), [
    ["holovna", "holovna~a1b2c3d4", "holovna~99887766"],
    ["poshuk", "poshuk-porozhno", "poshuk-porozhno~ffffffff"],
  ]);
});

test("групи не показуються — ні рядом, ні карткою", () => {
  const rows = buildRows(PAGES, NODES);
  assert.ok(!rows.flat().some((c) => c.key === "arhiv"), "група потрапила на полотно");
  assert.ok(!rows.flat().some((c) => c.key === "poshuk-stare"), "вкладена тека потрапила на полотно");
});

test("немає графа — ряд схлопується до сторінки з дітьми, а не зникає", () => {
  const rows = buildRows(PAGES, []);
  assert.deepEqual(rows.map((r) => r.map((c) => c.key)), [
    ["holovna"],
    ["poshuk", "poshuk-porozhno"],
  ]);
});

test("вузол на неіснуючу сторінку не створює ряду-привида", () => {
  const rows = buildRows(PAGES, [
    { page: "nemaje", state: "?s=x", key: "nemaje~00000000", label: "Привид" },
  ]);
  assert.ok(!rows.flat().some((c) => c.key.startsWith("nemaje")), "привид на полотні");
});

test("той самий стан у двох смугах — один кадр, перше входження", () => {
  const twice = [...NODES, { page: "holovna", state: "?s=empty",
                             key: "holovna~a1b2c3d4", label: "Друга смуга" }];
  const rows = buildRows(PAGES, twice);
  assert.equal(rows[0].filter((c) => c.key === "holovna~a1b2c3d4").length, 1);
});

test("картка СТОРІНКИ несе page, state і published — «Відкрити» читає саме page", () => {
  const [page] = buildRows(PAGES, NODES)[0];
  assert.equal(page.key, "holovna");
  /* `page` несучий, хоч у сітці й дорівнює `id`: `openCard` (`app/app.js`) кладе
     в `pickedPage` саме його, і без нього «Відкрити» відкриває першу-ліпшу
     сторінку замість тієї, по якій клікнули. */
  assert.equal(page.page, "holovna");
  assert.equal(page.state, null);
  assert.equal(page.label, "Головна");
  assert.equal(page.published, true);
});

test("картка СТАНУ несе page, state і published — це все, що треба для малювання", () => {
  const state = buildRows(PAGES, NODES)[0][1];
  assert.equal(state.page, "holovna");
  assert.equal(state.state, "?s=empty");
  assert.equal(state.label, "Головна · порожньо");
  assert.equal(state.published, true);
});

test("зняту з превʼю сторінку успадковують і її стани — крапка одна на екран", () => {
  const off = [{ id: "holovna", name: "Головна", published: false }];
  const rows = buildRows(off, NODES);
  assert.deepEqual(rows[0].map((c) => c.published), [false, false, false]);
});

test("крапку дитина має СВОЮ, а не батькову — і стан дитини бере дитинину", () => {
  const [, poshuk] = buildRows(PAGES, NODES);
  // «Пошук» у превʼю, «Стан: порожньо» знято — і його стан із флоу теж знято.
  assert.deepEqual(poshuk.map((c) => c.published), [true, false, false]);
});

test("легасі-дитина сторінки — стан, підписаний без ↳", () => {
  const [, poshuk] = buildRows(PAGES, NODES);
  assert.deepEqual(poshuk.map((c) => c.label),
    ["Пошук", "Стан: порожньо", "Порожньо · повільно"]);
});

test("сторінка ВСЕРЕДИНІ теки не зникає — тека не ряд, а її дитина ряд сама", () => {
  /* Кадр цієї сторінки вже на диску (`bin/shoot.mjs` ходить у дітей теки повз
     охорону по `isGroup`), і сітка до правки її малювала. `continue` на теці
     разом із дітьми прибрав би її з полотна мовчки. */
  const rows = buildRows(GROUPED, [
    { page: "poshuk", state: "?s=empty", key: "poshuk~11112222", label: "Пошук · порожньо" },
  ]);
  assert.deepEqual(rows.map((r) => r.title), ["Головна", "Пошук"]);
  assert.deepEqual(rows.map((r) => r.map((c) => c.key)),
    [["holovna"], ["poshuk", "poshuk~11112222"]]);
  // У власному ряду дитина теки — верхня сторінка, тому без `↳`.
  assert.deepEqual(rows[1].map((c) => c.label), ["Пошук", "Пошук · порожньо"]);
  // Сама тека рядом не стає: злиття різних екранів в один ряд — та сама
  // безсенсовність, проти якої вся правка.
  assert.ok(!rows.flat().some((c) => c.key === "grupa"), "тека потрапила на полотно");
});

test("вузол із порожнім станом — це сама сторінка, а не другий такий самий кадр", () => {
  /* `"state": {}` і `{"q": ""}` `checkState` пропускає, а `shotKey` віддає для
     них голий id сторінки — ключ той самий, що в картки з дерева. `seen` тут не
     допомагає: він дедуплікує вузли між собою, а не вузол проти дерева. */
  const rows = buildRows(PAGES, [
    { page: "poshuk", state: {}, key: "poshuk", label: "Пошук" },
    { page: "poshuk-porozhno", state: { q: "" }, key: "poshuk-porozhno", label: "Порожньо" },
  ]);
  assert.deepEqual(rows[1].map((c) => c.key), ["poshuk", "poshuk-porozhno"]);
});

test("порядок станів у ряду — порядок вузлів у flow.json, і це навмисно", () => {
  /* Послідовність станів у файлі — авторська розповідь («порожньо →
     завантаження»), і сортувати її за ключем чи підписом не можна. */
  const rows = buildRows(PAGES, NODES);
  assert.deepEqual(rows[0].map((c) => c.label),
    ["Головна", "Головна · порожньо", "Головна · завантаження"]);
});

test("підпис ряду — імʼя верхньорівневої сторінки", () => {
  assert.deepEqual(buildRows(PAGES, NODES).map((r) => r.title), ["Головна", "Пошук"]);
});

const DEEP = [
  { id: "kartka", name: "Картка компанії", kind: "page", children: [
    { id: "w", name: "Віджет «Санкції»", kind: "folder", children: [
      { id: "s-err", name: "Помилка", kind: "state" },
      { id: "g", name: "Графік", kind: "folder", children: [
        { id: "s-hover", name: "Наведення", kind: "state" }] }] },
    { id: "s-none", name: "Компанію не знайдено", kind: "state" },
    { id: "ist", name: "Історія змін", kind: "page", children: [
      { id: "ist-empty", name: "Порожньо", kind: "state" }] }] },
  { id: "mob", name: "Мобайл", kind: "folder", children: [
    { id: "k375", name: "Картка · 375", kind: "page" }] },
];

test("стани збираються крізь теки віджетів і підписані шляхом від сторінки", () => {
  const rows = buildRows(DEEP, []);
  assert.deepEqual(rows[0].map((c) => c.label),
    ["Картка компанії", "Віджет «Санкції» · Помилка", "Віджет «Санкції» · Графік · Наведення",
     "Компанію не знайдено"]);
});

test("підсторінка — ОКРЕМИЙ ряд із заголовком-шляхом (рішення власника 30.09.2026)", () => {
  const rows = buildRows(DEEP, []);
  assert.deepEqual(rows.map((r) => r.title),
    ["Картка компанії", "Картка компанії › Історія змін", "Картка · 375"]);
  assert.deepEqual(rows[1].map((c) => c.key), ["ist", "ist-empty"]);
});

test("схована сторінка ховає й свої стани в сітці", () => {
  const t = JSON.parse(JSON.stringify(DEEP));
  t[0].published = false;
  const rows = buildRows(t, []);
  assert.ok(rows[0].every((c) => c.published === false));
  assert.ok(rows[1].every((c) => c.published === false), "підсторінка схованої — теж схована");
});

const C = (rows) => rows.map((r) => r.map((c) => [c.key, c.published]));

test("тека, схована всередині сторінки, ховає свої стани, а сусідні лишає", () => {
  const t = [{ id: "p", name: "P", kind: "page", children: [
    { id: "w", name: "W", kind: "folder", published: false, children: [
      { id: "s1", name: "S1", kind: "state" }] },
    { id: "s2", name: "S2", kind: "state" }] }];
  assert.deepEqual(C(buildRows(t, [])), [[["p", true], ["s1", false], ["s2", true]]]);
});

test("схована коренева тека ховає ряди своїх сторінок", () => {
  const t = [{ id: "f", name: "F", kind: "folder", published: false, children: [
    { id: "p", name: "P", kind: "page", children: [{ id: "s", name: "S", kind: "state" }] }] }];
  assert.deepEqual(C(buildRows(t, [])), [[["p", false], ["s", false]]]);
});

test("підсторінка всередині схованої теки — схована", () => {
  const t = [{ id: "p", name: "P", kind: "page", children: [
    { id: "w", name: "W", kind: "folder", published: false, children: [
      { id: "sub", name: "Sub", kind: "page" }] }] }];
  assert.deepEqual(C(buildRows(t, [])), [[["p", true]], [["sub", false]]]);
});

test("стан схований сам, батько видимий", () => {
  const t = [{ id: "p", name: "P", kind: "page", children: [
    { id: "s", name: "S", kind: "state", published: false }] }];
  assert.deepEqual(C(buildRows(t, [])), [[["p", true], ["s", false]]]);
});

test("flow-вузол на стан і на підсторінку — у ряді своєї сторінки з її видимістю", () => {
  const t = [{ id: "p", name: "P", kind: "page", children: [
    { id: "s", name: "S", kind: "state", published: false },
    { id: "sub", name: "Sub", kind: "page" }] }];
  const nodes = [
    { page: "s", state: "?a=1", key: "s~aaaaaaaa", label: "S · a" },
    { page: "sub", state: "?b=1", key: "sub~bbbbbbbb", label: "Sub · b" }];
  assert.deepEqual(C(buildRows(t, nodes)),
    [[["p", true], ["s", false], ["s~aaaaaaaa", false]],
     [["sub", true], ["sub~bbbbbbbb", true]]]);
});

test("published кожної картки збігається з visibleIds на глибокій фікстурі", () => {
  const t = JSON.parse(JSON.stringify(DEEP));
  t[0].children[0].children[1].children[0].published = false; // стан у вкладеній теці
  t[0].children[2].published = false;                         // підсторінка
  t[1].children[0].published = true;                          // явне true під теками
  const vis = visibleIds(t);
  const cards = buildRows(t, []).flat();
  assert.ok(cards.length > 5);
  for (const c of cards) assert.equal(c.published, vis.has(c.page), c.key);
  t[1].published = false;
  const vis2 = visibleIds(t);
  for (const c of buildRows(t, []).flat()) assert.equal(c.published, vis2.has(c.page), c.key);
});

test("дитина легасі-теки (isGroup) всередині сторінки — підсторінка зі своїм рядом", () => {
  const t = [{ id: "p", name: "P", children: [
    { id: "g", name: "G", isGroup: true, children: [{ id: "k", name: "K" }] }] }];
  assert.deepEqual(buildRows(t, []).map((r) => r.title), ["P", "P › K"]);
});

test("паритет видимості: published кожної картки buildRows = visibleIds, на всіх кейсах фікстури", () => {
  const RULES = JSON.parse(readFileSync(new URL("./fixtures/tree-rules.json", import.meta.url), "utf8"));
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const trees = [
    ...RULES.visible.map((c) => [c.name, typeof c.tree === "string" ? RULES.trees[c.tree] : c.tree]),
    ...Object.entries(RULES.trees).filter(([k]) => k !== "NOID"),
  ];
  let cards = 0;
  for (const [name, spec] of trees) {
    const t = clone(spec);
    const vis = visibleIds(t);
    for (const row of buildRows(t, [])) {
      for (const card of row) {
        cards += 1;
        assert.equal(card.published, vis.has(card.page), `${name}: ${card.page}`);
      }
    }
  }
  assert.ok(cards > 10, "кейси справді дали картки");
});
