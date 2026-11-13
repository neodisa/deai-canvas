import assert from "node:assert/strict";
import test from "node:test";

import { RESERVED_Q, shotKey, stateQuery, checkState, rankNodes, readFlow } from "../app/flow-model.js";
import { t } from "../app/i18n.js";

test("сторінка без стану ключується сама собою — кадри етапу 1 лишаються чинними", () => {
  assert.equal(shotKey("poshuk", null), "poshuk");
  assert.equal(shotKey("poshuk", {}), "poshuk");
});

test("стан дає окремий ключ, стабільний і безпечний для імені файла", () => {
  const k = shotKey("poshuk", { state: "empty" });
  assert.match(k, /^poshuk~[0-9a-f]{8}$/);
  assert.equal(k, shotKey("poshuk", { state: "empty" }), "ключ мусить бути стабільним");
});

test("порядок ключів у стані не міняє кадру: це той самий екран", () => {
  assert.equal(shotKey("p", { a: "1", b: "2" }), shotKey("p", { b: "2", a: "1" }));
});

test("різні стани — різні кадри", () => {
  assert.notEqual(shotKey("p", { state: "empty" }), shotKey("p", { state: "error" }));
});

test("стан не сміє захопити наші власні параметри", () => {
  for (const bad of ["it", "page", "bare", "ch", "v", "host"]) {
    assert.throws(() => checkState({ [bad]: "x" }), { message: t("flowStateReserved", bad) },
      `${bad} мусить бути відхилений`);
  }
  assert.ok(RESERVED_Q.has("page"));
  assert.ok(RESERVED_Q.has("host"), "host=1 — службовий параметр режиму хоста коментатора, не стан сторінки");
});

test("stateQuery дає кусок URL у стабільному порядку", () => {
  assert.equal(stateQuery({ b: "2", a: "1" }), "&a=1&b=2");
  assert.equal(stateQuery(null), "");
});

test("null і порожнє в стані — це ВІДСУТНІСТЬ стану, а не значення в URL", () => {
  // JSON цілком може принести `"state": null`. Без фільтра воно поїхало б у URL
  // рядком `&state=null` — макет отримав би стан, якого ніхто не оголошував.
  assert.equal(shotKey("p", { state: null }), "p");
  assert.equal(stateQuery({ state: null, other: undefined, blank: "" }), "");
});

test("ранг — найдовший шлях від входу, а не перший знайдений", () => {
  // a→b→c і a→c: c мусить стати в колонку 2, інакше стрілка a→c піде назад
  const ranks = rankNodes(
    [{ id: "a" }, { id: "b" }, { id: "c" }],
    [{ from: "a", to: "b" }, { from: "b", to: "c" }, { from: "a", to: "c" }],
  );
  assert.deepEqual([...ranks], [["a", 0], ["b", 1], ["c", 2]]);
});

test("ланцюг, описаний З КІНЦЯ, теж розкладається правильно", () => {
  // На цьому випадку падав перший варіант алгоритму: давав d=2 замість 3.
  const ranks = rankNodes(
    [{ id: "d" }, { id: "c" }, { id: "b" }, { id: "a" }],
    [{ from: "a", to: "b" }, { from: "b", to: "c" }, { from: "c", to: "d" }],
  );
  assert.equal(ranks.get("d"), 3);
});

test("коло з хвостом називає саме коло, а не хвіст", () => {
  assert.throws(
    () => rankNodes([{ id: "a" }, { id: "b" }, { id: "x" }],
                    [{ from: "a", to: "b" }, { from: "b", to: "a" }, { from: "b", to: "x" }]),
    { message: t("flowLoop", "a → b → a") },
  );
});

test("кілька входів — кожен у нульовій колонці", () => {
  const ranks = rankNodes([{ id: "a" }, { id: "b" }, { id: "c" }],
                          [{ from: "a", to: "c" }, { from: "b", to: "c" }]);
  assert.equal(ranks.get("a"), 0);
  assert.equal(ranks.get("b"), 0);
  assert.equal(ranks.get("c"), 1);
});

test("замкнене коло — помилка декларації, а не привід малювати як вийде", () => {
  assert.throws(
    () => rankNodes([{ id: "a" }, { id: "b" }],
                    [{ from: "a", to: "b" }, { from: "b", to: "a" }]),
    { message: t("flowLoop", "a → b → a") },
  );
});

test("вузол сам на себе — теж коло", () => {
  assert.throws(() => rankNodes([{ id: "a" }], [{ from: "a", to: "a" }]),
                { message: t("flowLoop", "a → a") });
});

const PAGES = ["holovna", "poshuk", "stattia"];

test("справний флоу читається, підпис береться з pages.json, коли свого немає", () => {
  const r = readFlow({ flows: [{ id: "f", title: "Пошук", nodes: [
    { id: "n1", page: "holovna" },
    { id: "n2", page: "poshuk", label: "Свій підпис" },
  ], edges: [{ from: "n1", to: "n2", label: "Вводить запит" }] }] },
    PAGES.map((id) => ({ id, name: id.toUpperCase() })));
  assert.deepEqual(r.problems, []);
  assert.equal(r.flows[0].nodes[0].label, "HOLOVNA");
  assert.equal(r.flows[0].nodes[1].label, "Свій підпис");
});

test("вузол на зниклу сторінку не малюється — і це ПОМІТНО, а не тихо", () => {
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "n1", page: "holovna" }, { id: "zomb", page: "znykla" },
  ], edges: [{ from: "n1", to: "zomb" }] }] }, PAGES.map((id) => ({ id, name: id })));
  assert.equal(r.flows[0].nodes.length, 1);
  assert.equal(r.flows[0].edges.length, 0, "ребро у викинутий вузол теж іде");
  assert.deepEqual(r.problems, [
    t("flowNoPage", t("flowNode", "zomb"), "znykla"),
    t("flowEdgeNoNode", "n1", "zomb"),
  ]);
});

test("два вузли на той самий екран — помилка: читач шукатиме різницю й не знайде", () => {
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "poshuk" }, { id: "b", page: "poshuk" },
  ], edges: [] }] }, PAGES.map((id) => ({ id, name: id })));
  assert.deepEqual(r.problems, [t("flowDupScreen", "a", "b", "poshuk")]);
});

test("той самий page з РІЗНИМ станом — два законні вузли", () => {
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "poshuk" },
    { id: "b", page: "poshuk", state: { state: "empty" } },
  ], edges: [] }] }, PAGES.map((id) => ({ id, name: id })));
  assert.deepEqual(r.problems, []);
});

test("замкнене коло не валить увесь файл — падає лише своя смуга", () => {
  const r = readFlow({ flows: [
    { id: "bad", nodes: [{ id: "a", page: "holovna" }, { id: "b", page: "poshuk" }],
      edges: [{ from: "a", to: "b" }, { from: "b", to: "a" }] },
    { id: "good", nodes: [{ id: "c", page: "stattia" }], edges: [] },
  ] }, PAGES.map((id) => ({ id, name: id })));
  assert.equal(r.flows.length, 1, "справна смуга мусить лишитись");
  assert.equal(r.flows[0].id, "good");
  assert.equal(r.problems[0], `${t("flowAt", "bad")}: ${t("flowLoop", "a → b → a")}`);
});

test("сторінки поза графом віддаються окремо — це група «не у флоу»", () => {
  const r = readFlow({ flows: [{ id: "f", nodes: [{ id: "a", page: "holovna" }], edges: [] }] },
                     PAGES.map((id) => ({ id, name: id })));
  assert.deepEqual(r.orphans.map((p) => p.id), ["poshuk", "stattia"]);
});

test("немає файла зовсім — не помилка: флоу ще не описували", () => {
  const r = readFlow(null, PAGES.map((id) => ({ id, name: id })));
  assert.deepEqual(r.flows, []);
  assert.deepEqual(r.problems, []);
  assert.equal(r.orphans.length, 3);
});

test("жодна сторінка не зникає: вона або у графі, або в «не у флоу»", () => {
  const pages = ["holovna", "poshuk", "stattia"].map((id) => ({ id, name: id }));
  const r = readFlow({ flows: [
    { id: "bad", nodes: [{ id: "a", page: "holovna" }, { id: "b", page: "poshuk" }],
      edges: [{ from: "a", to: "b" }, { from: "b", to: "a" }] },
  ] }, pages);
  const shown = new Set([...r.flows.flatMap((f) => f.nodes.map((n) => n.page)),
                         ...r.orphans.map((p) => p.id)]);
  assert.deepEqual([...shown].sort(), ["holovna", "poshuk", "stattia"]);
});

test("побитий формат — це problems, а не падіння всього читання", () => {
  const pages = ["holovna", "poshuk"].map((id) => ({ id, name: id }));

  const noFlows = readFlow({ flows: { id: "f" } }, pages);
  assert.notEqual(noFlows.problems.length, 0, "«flows» не список");
  assert.deepEqual(noFlows.flows, []);
  assert.deepEqual(noFlows.orphans.map((p) => p.id), ["holovna", "poshuk"]);

  const noNodes = readFlow({ flows: [{ id: "f", nodes: { id: "a" }, edges: [] }] }, pages);
  assert.notEqual(noNodes.problems.length, 0, "«nodes» не список");
  assert.deepEqual(noNodes.flows, []);

  const noEdges = readFlow(
    { flows: [{ id: "f", nodes: [{ id: "a", page: "holovna" }], edges: "нема" }] }, pages);
  assert.notEqual(noEdges.problems.length, 0, "«edges» не список");
  assert.deepEqual(noEdges.flows, []);
  assert.deepEqual(noEdges.orphans.map((p) => p.id), ["holovna", "poshuk"],
    "сторінки пропущеної смуги мусять знайтись у «не у флоу»");
});

test("другий вузол із тим самим id — викинуто: інакше ребра мовчки неоднозначні", () => {
  const pages = ["holovna", "poshuk"].map((id) => ({ id, name: id }));
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "holovna" }, { id: "a", page: "poshuk" },
  ], edges: [] }] }, pages);
  assert.equal(r.flows[0].nodes.length, 1);
  assert.equal(r.flows[0].nodes[0].page, "holovna", "лишається перший");
  assert.deepEqual(r.problems, [t("flowDupId", t("flowNode", "a"))]);
  assert.deepEqual(r.orphans.map((p) => p.id), ["poshuk"]);
});

test("стрілка сама в себе — викидаємо стрілку, а не всю смугу", () => {
  const pages = ["holovna", "poshuk"].map((id) => ({ id, name: id }));
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "holovna" }, { id: "b", page: "poshuk" },
  ], edges: [{ from: "a", to: "a" }, { from: "a", to: "b" }] }] }, pages);
  assert.equal(r.flows.length, 1, "смуга мусить лишитись");
  assert.equal(r.flows[0].edges.length, 1);
  assert.deepEqual(r.problems, [t("flowEdgeSelf", "a", "a")]);
  assert.equal(r.flows[0].ranks.get("b"), 1);
});

test("«&» чи «=» у значенні стану не схлопує два різні екрани", () => {
  // Було: shotKey хешував сирий `k=v`, а stateQuery для URL екранував — дві
  // функції одного файла розходились у тому, що вважають однаковим станом.
  // {a:1, b:2} і {a:"1&b=2"} давали ОДИН ключ, і readFlow звинувачував автора
  // в дублі, якого той не робив.
  assert.notEqual(shotKey("p", { a: "1", b: "2" }), shotKey("p", { a: "1&b=2" }));
  const pages = [{ id: "poshuk", name: "Пошук" }];
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "poshuk", state: { q: "закон", tab: "усі" } },
    { id: "b", page: "poshuk", state: { q: "закон&tab=усі" } },
  ], edges: [] }] }, pages);
  assert.deepEqual(r.problems, [], "це два різні екрани, автор нічого не дублював");
  assert.equal(r.flows[0].nodes.length, 2);
});

test("«state»: «empty» замість {state: «empty»} — описка, а не другий екран", () => {
  assert.throws(() => checkState("empty"), { message: t("flowStateNotObject", "string") });
  assert.throws(() => checkState(42), { message: t("flowStateNotObject", "number") });
  assert.throws(() => checkState(true), { message: t("flowStateNotObject", "boolean") });
  assert.throws(() => checkState(["empty"]), { message: t("flowStateNotObject", t("flowArray")) },
    "масив — теж не стан, і саме масивом (не «object») мусить бути названий");
  checkState(null);            // відсутність стану — це не описка
  checkState(undefined);
  const pages = [{ id: "poshuk", name: "Пошук" }];
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "poshuk" }, { id: "b", page: "poshuk", state: "empty" },
  ], edges: [] }] }, pages);
  assert.equal(r.flows[0].nodes.length, 1, "описка не сміє стати законним екраном");
  assert.equal(r.problems[0], `${t("flowNode", "b")}: ${t("flowStateNotObject", "string")}`);
});

test("null серед смуг, вузлів і ребер — це problems, а не TypeError", () => {
  const pages = ["holovna", "poshuk"].map((id) => ({ id, name: id }));
  const r = readFlow({ flows: [
    null,
    { id: "f", nodes: [{ id: "a", page: "holovna" }, null, "вузол"], edges: [null] },
  ] }, pages);
  assert.equal(r.flows.length, 1);
  assert.equal(r.flows[0].nodes.length, 1);
  assert.equal(r.problems.length, 4, r.problems.join(" | "));
  assert.equal(r.problems[0], t("flowNotObject", t("flowAtIndex", 1)));
});

test("описка в назві кореневого ключа не мовчить, як «файла немає»", () => {
  const pages = [{ id: "holovna", name: "Головна" }];
  assert.deepEqual(readFlow(null, pages).problems, [], "немає файла — не помилка");
  assert.deepEqual(readFlow(undefined, pages).problems, []);
  for (const bad of [{ flowz: [] }, "рядок", [{ id: "f" }], 42]) {
    const r = readFlow(bad, pages);
    assert.notEqual(r.problems.length, 0, `${JSON.stringify(bad)}: мусить сказати, що не так`);
    assert.deepEqual(r.flows, []);
    assert.deepEqual(r.orphans.map((p) => p.id), ["holovna"]);
  }
});

test("зарезервований ключ у стані вузла стає problems, а не тихо їде в URL", () => {
  const pages = [{ id: "poshuk", name: "Пошук" }];
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "poshuk", state: { page: "інша" } },
  ], edges: [] }] }, pages);
  assert.deepEqual(r.flows[0].nodes, []);
  assert.deepEqual(r.problems, [`${t("flowNode", "a")}: ${t("flowStateReserved", "page")}`]);
});

test("stateQuery екранує ключ і значення — інакше стан ламає власний URL", () => {
  assert.equal(stateQuery({ q: "a&b=c" }), "&q=a%26b%3Dc");
  assert.equal(stateQuery({ "a b": "1" }), "&a%20b=1");
});

test("orphans — завжди новий масив, а не той, що дав викликач", () => {
  const pages = [{ id: "holovna", name: "Головна" }];
  for (const raw of [null, { flowz: [] }, { flows: "не список" }, { flows: [] }]) {
    const r = readFlow(raw, pages);
    assert.notStrictEqual(r.orphans, pages, `${JSON.stringify(raw)}: віддано масив викликача`);
  }
  readFlow(null, pages).orphans.push({ id: "чуже" });
  assert.equal(pages.length, 1, "масив викликача мусить лишитись цілим");
});

test("вузол на теку (isGroup) — помилка: тека не відкривається як екран", () => {
  const pages = [{ id: "grupa", name: "Список", isGroup: true },
                 { id: "holovna", name: "Головна" }];
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "grupa" }, { id: "b", page: "holovna" },
  ], edges: [] }] }, pages);
  assert.equal(r.flows[0].nodes.length, 1);
  assert.equal(r.problems[0], t("flowIsGroup", t("flowNode", "a"), "grupa"));
});

test("вузол на теку за kind (без isGroup) — теж помилка", () => {
  const pages = [{ id: "grupa", name: "Список", kind: "folder" },
                 { id: "holovna", name: "Головна" }];
  const r = readFlow({ flows: [{ id: "f", nodes: [
    { id: "a", page: "grupa" }, { id: "b", page: "holovna" },
  ], edges: [] }] }, pages);
  assert.equal(r.flows[0].nodes.length, 1);
  assert.equal(r.problems[0], t("flowIsGroup", t("flowNode", "a"), "grupa"));
});

test("явний kind:page перемагає зайвий isGroup — це сторінка, як у pm.kind_of", () => {
  const pages = [{ id: "dvoyaka", name: "Двоїста", kind: "page", isGroup: true }];
  const r = readFlow({ flows: [{ id: "f", nodes: [{ id: "a", page: "dvoyaka" }], edges: [] }] }, pages);
  assert.deepEqual(r.problems, []);
  assert.equal(r.flows[0].nodes.length, 1);
});

test("вузол без id — скарга про ВІДСУТНІЙ id, а не про зайнятий", () => {
  /* Перша перевірка вузла була про дублі (`ids.has(node.id)`), а не про те, чи id
     взагалі є. Наслідок був подвійний, і обидві половини тихі:
       — ОДИН вузол без id проходив як законний екран з `id: undefined` і БЕЗ
         жодної скарги (перевірено: `problems` порожній);
       — ДРУГИЙ такий діставав «id вже зайнятий у цій смузі», тобто скаргу на
         поле, якого автор ніколи не писав.
     Найімовірніша описка автора тут — просто забути рядок `"id": …`, і саме її
     повідомлення мусить назвати. */
  const pages = [{ id: "holovna", name: "Головна" }, { id: "poshuk", name: "Пошук" }];
  const AT = t("flowAt", "f");    // усі смуги нижче — флоу з id "f"
  const one = readFlow({ flows: [{ id: "f", nodes: [
    { page: "holovna" }, { id: "b", page: "poshuk" },
  ], edges: [] }] }, pages);
  assert.equal(one.flows[0].nodes.length, 1, "вузол без id не сміє стати законним екраном");
  assert.equal(one.flows[0].nodes[0].id, "b");
  assert.equal(one.problems[0], t("flowNoId", t("flowNodeIndex", 1, AT)));
  assert.notEqual(one.problems[0], t("flowDupId", t("flowNodeIndex", 1, AT)),
    "скарга вказувала б у поле, якого автор ніколи не писав");
  assert.deepEqual(one.orphans.map((p) => p.id), ["holovna"],
    "сторінка викинутого вузла мусить знайтись у «не у флоу»");

  // Порожній рядок — те саме: id, за яким не можна ні знайти вузол, ні описати ребро.
  const blank = readFlow({ flows: [{ id: "f", nodes: [{ id: "", page: "holovna" }],
                                     edges: [] }] }, pages);
  assert.equal(blank.problems[0], t("flowNoId", t("flowNodeIndex", 1, AT)));
  assert.deepEqual(blank.flows[0].nodes, []);

  /* Не рядок — теж «немає id»: id їде в імена й ключі (у `app/app.js` він стає
     `\`${i}\\u0000${id}\``), а числовий чи логічний id зробив би вузол
     невимовним у ребрах і в скаргах — `«0»` там взагалі falsy. */
  const num = readFlow({ flows: [{ id: "f", nodes: [{ id: 3, page: "holovna" }],
                                   edges: [] }] }, pages);
  assert.equal(num.problems[0], t("flowNoId", t("flowNode", 3)));
  assert.deepEqual(num.flows[0].nodes, []);

  // І двоє без id дають ДВІ однакові скарги про відсутній id, а не одну про дубль.
  const two = readFlow({ flows: [{ id: "f", nodes: [
    { page: "holovna" }, { page: "poshuk" },
  ], edges: [] }] }, pages);
  assert.equal(two.problems.length, 2, two.problems.join(" | "));
  assert.deepEqual(two.problems, [
    t("flowNoId", t("flowNodeIndex", 1, AT)),
    t("flowNoId", t("flowNodeIndex", 2, AT)),
  ]);
});
