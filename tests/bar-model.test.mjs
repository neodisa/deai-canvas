import assert from "node:assert/strict";
import test from "node:test";

import {
  TIERS, barModel, figmaWhyKey, flowWhyKey, labelVisibleAt, linkWhyKey, overflowAt, visibleAt,
} from "../app/bar-model.js";

const base = {
  mode: "layout", view: "grid", vp: "desktop", vpw: "",
  taskId: "LIGA-7003", iterLabel: "Іт.3", iterNote: "Правки",
  hasIteration: true, flowRaw: true, pagesError: "", flowError: "",
  gl: "sync", published: true, pubStale: false, iterPub: true, pagePub: true,
  iterOnGl: true, tasksErr: "", right: null,
};

/* Три зони — це не оформлення, а відповідь на три різні питання: де я / як
   дивлюсь / куди віддаю. Контрол, який не належить жодній, — привід
   переглянути контрол, а не додати четверту зону.

   Раніше тест звіряв `Object.keys(m)` рівно з `["zone1","zone2","zone3"]` —
   тобто стеріг ЧИСЛО ключів, а не задум. Коли модель отримала четверте поле
   `error` (стан «tasks.json не читається», Task 8 review, п.6), той тест впав
   би на речі, яка не має стосунку до зон: `error` — не зона, у ній немає
   контролів, і в перевірку унікальності id вона не входить. */
test("модель віддає три зони, і кожен контрол лежить рівно в одній", () => {
  const m = barModel(base);
  assert.ok(m.zone1 && m.zone2 && m.zone3, "усі три зони присутні");
  const ids = [...m.zone1, ...m.zone2, ...m.zone3].map((x) => x.id);
  assert.equal(new Set(ids).size, ids.length, "контрол трапляється двічі");
});

/* «Контрол не бреше про режим»: інспектор працює по живому DOM, якого в
   «Огляді» не існує — там кадри це знімки. Він мусить ЗНИКАТИ, а не стояти
   ввімкненим і нічого не робити. */
test("інспектора немає в «Огляді»", () => {
  assert.ok(barModel(base).zone2.some((x) => x.id === "inspector"));
  assert.ok(!barModel({ ...base, mode: "overview" }).zone2.some((x) => x.id === "inspector"));
});

test("перемикач «Сітка / Флоу» є лише в «Огляді»", () => {
  assert.ok(!barModel(base).zone2.some((x) => x.id === "view"));
  assert.ok(barModel({ ...base, mode: "overview" }).zone2.some((x) => x.id === "view"));
});

/* «Причина видима»: модель віддає КЛЮЧ словника, а не текст. Тоді тест не
   залежить від мови, а DOM-шар сам кличе t(). */
test("«Флоу» без flow.json вимкнений і несе ключ причини", () => {
  const m = barModel({ ...base, mode: "overview", flowRaw: null });
  const flow = m.zone2.find((x) => x.id === "view").items.find((x) => x.id === "flow");
  assert.equal(flow.disabled, true);
  assert.equal(flow.whyKey, "whyNoFlow");
});

test("перелік сторінок не завантажився — причина інша", () => {
  const m = barModel({ ...base, mode: "overview", pagesError: "500" });
  const flow = m.zone2.find((x) => x.id === "view").items.find((x) => x.id === "flow");
  assert.equal(flow.whyKey, "whyPagesError");
});

/* Ревʼю Task 8 (п.2): третій випадок «Флоу» — граф ПОБУДОВАНИЙ (`flowRaw`
   truthy), але в ньому лишились скарги парсингу (дублі id, повислі ребра —
   `flow-model.js`). Це НЕ «зламаний файл»: файл прочитався, граф є, скарги
   показуються на полотні. Контрол мусить лишатись живим — інакше єдиний спосіб
   побачити скарги (натиснути «Флоу») сам себе забороняє. */
test("«Флоу» з побудованим графом живий, навіть якщо лишились скарги парсингу", () => {
  const m = barModel({ ...base, mode: "overview", flowRaw: {}, flowError: "битий" });
  const flow = m.zone2.find((x) => x.id === "view").items.find((x) => x.id === "flow");
  assert.equal(flow.disabled, false);
  assert.equal(flow.whyKey, "");
});

test("посилання: три різні причини недоступності", () => {
  const link = (s) => barModel(s).zone3.find((x) => x.id === "publish")
    .items.find((x) => x.id === "copylink");
  assert.equal(link({ ...base, published: false }).whyKey, "whyNoPublish");
  assert.equal(link({ ...base, iterPub: false }).whyKey, "whyItOff");
  assert.equal(link({ ...base, pagePub: false }).whyKey, "whyPageOff");
  assert.equal(link(base).whyKey, "");
});

/* ЦЕ той самий баг, з якого почалась уся робота: на 1024 підписи ховались, а
   заміни не зʼявлялось — керування виглядом ставало недосяжним. Знайшли його
   ВИМІРОМ у браузері, бо модель жила в шаблонах. Тепер це юніт: або контрол
   видимий у смузі, або він у «⋯». Ніколи ні там ні там, і ніколи в обох. */
test("на кожному ярусі кожен контрол зони 2 або в смузі, або в «⋯»", () => {
  for (const mode of ["layout", "overview"]) {
    for (const w of [1024, 1120, 1280, 1440]) {
      const m = barModel({ ...base, mode });
      const vis = new Set(visibleAt(m.zone2, w).map((x) => x.id));
      const more = new Set(overflowAt(m.zone2, w).map((x) => x.id));
      for (const item of m.zone2) {
        const inBar = vis.has(item.id), inMore = more.has(item.id);
        assert.ok(inBar || inMore, `${w}/${mode}: «${item.id}» зник зовсім`);
        assert.ok(!(inBar && inMore), `${w}/${mode}: «${item.id}» продубльований`);
      }
    }
  }
});

/* Головна дія і перемикач режиму не їдуть у «⋯» на жодному ярусі: це і є
   обіцянка «головне не зникає», яку смуга 1462px не тримала. */
test("режим і публікація ніколи не в «⋯»", () => {
  for (const w of [1024, 1120, 1280, 1440]) {
    const m = barModel(base);
    assert.ok(visibleAt(m.zone2, w).some((x) => x.id === "mode"), `${w}: режим`);
    assert.ok(visibleAt(m.zone3, w).some((x) => x.id === "publish"), `${w}: публікація`);
    assert.equal(overflowAt(m.zone3, w).length, 0, `${w}: зона 3 нічого не ховає`);
  }
});

/* Обрубок: на 1024 підпис публікації ховався, а іконки в опублікованому стані
   не було — кнопка лишалась 20-піксельним нічим. Тому іконка є ЗАВЖДИ, у
   будь-якому стані. */
test("у публікації завжди є іконка, у кожному стані", () => {
  for (const s of [base, { ...base, published: false }, { ...base, pubStale: true }]) {
    const pub = barModel(s).zone3.find((x) => x.id === "publish");
    assert.ok(pub.icon, "публікація без іконки — це той самий обрубок");
  }
});

test("яруси — три, і саме ті, що в спеці", () => {
  assert.deepEqual(TIERS, { gl: 1300, mode: 1180, view: 1060 });
});

/* Чисті функції причин перевіряємо і напряму: DOM-шар кличе саме їх, і
   порядок пріоритету тут несучий — «немає публікації» важливіше за «ітерація
   не в превью», бо перше робить друге неважливим. */
test("порядок пріоритету причин посилання", () => {
  assert.equal(linkWhyKey({ published: false, iterPub: false, pagePub: false }), "whyNoPublish");
  assert.equal(linkWhyKey({ published: true, iterPub: false, pagePub: false }), "whyItOff");
  assert.equal(linkWhyKey({ published: true, iterPub: true, pagePub: false }), "whyPageOff");
  assert.equal(linkWhyKey({ published: true, iterPub: true, pagePub: true }), "");
});

test("причина «Флоу»: три ІЗ ЧОТИРЬОХ станів розрізнені явно (Task 8 review, п.2)", () => {
  // 1) перелік сторінок не прийшов — рано казати щось про flow.json узагалі.
  assert.equal(flowWhyKey({ pagesError: "500", flowRaw: null }), "whyPagesError");
  // 2) flow.json нема зовсім.
  assert.equal(flowWhyKey({ pagesError: "", flowRaw: null, flowError: "" }), "whyNoFlow");
  // 3) flow.json є, але не читається (побитий JSON) — з графа нічого будувати.
  assert.equal(flowWhyKey({ pagesError: "", flowRaw: null, flowError: "битий" }), "whyFlowBroken");
  // 4) flow.json прочитався, граф є — причини нема, навіть якщо в графі
  //    лишились скарги парсингу (`flowError` тут — залишок ПОПЕРЕДНЬОЇ спроби
  //    читання, не сигнал про поточний граф; правду каже лише `flowRaw`).
  assert.equal(flowWhyKey({ pagesError: "", flowRaw: {}, flowError: "битий" }), "");
  assert.equal(flowWhyKey({ pagesError: "", flowRaw: {} }), "");
});

/* ДІРА, знайдена мутацією на Task 8: набір ширин вище — [1024, 1120, 1280,
   1440] — обходить усі три пороги ярусів (1060 / 1180 / 1300), тому підміна
   `w <= item.tier` на `w < item.tier` лишала всі тести зеленими. А розбіжність
   саме на межі — найгірша: контейнерний запит `max-width:1060px` матчиться НА
   1060, і модель, яка на цій ширині вважає контрол видимим, дала б смугу, де
   вона й «⋯» розходяться на одному конкретному пікселі. Ловиться лише
   перевіркою РІВНО на порозі. */
test("рівно на порозі ярусу контрол уже в «⋯», а не ще в смузі", () => {
  for (const mode of ["layout", "overview"]) {
    const m = barModel({ ...base, mode });
    const atTier = TIERS.view;
    const vis = visibleAt(m.zone2, atTier).map((x) => x.id);
    const more = overflowAt(m.zone2, atTier).map((x) => x.id);
    assert.ok(more.includes("vp"),
      `${mode}: на ширині рівно ${atTier} «vp» мусить бути в «⋯», а він у смузі`);
    assert.ok(!vis.includes("vp"), `${mode}: «vp» і в смузі, і на порозі`);
    /* На піксель ШИРШЕ — уже в смузі: інакше перевірка була б зеленою і для
       моделі, що ховає контрол назавжди. */
    assert.ok(visibleAt(m.zone2, atTier + 1).map((x) => x.id).includes("vp"),
      `${mode}: на ${atTier + 1} «vp» мусить вернутись у смугу`);
  }
});

/* Те саме для підписів: `labelTier` живе за тим самим правилом, і зсув на
   піксель тут дав би смугу, де підпис зник, а місце під нього лишилось.

   Ревʼю Task 8 (п.1): у прототипі `.lbl-mode` вішається на ВСІ сегменти
   зони 2, включно з «Сітка/Флоу» (`viewSeg` у `docs/proto/shell.html`), і
   контейнерний запит `@container (max-width:1180px){.lbl-mode{display:none}}`
   ховає їх усі одним правилом. Модель, що памʼятала `labelTier` лише в
   `mode`, брехала б для «Сітка»/«Флоу»: сказала б «підпис видно» там, де CSS
   уже його сховав. Тому перевіряємо ОБИДВА контроли з `labelTier`, а не
   один — інакше наступний контрол із підписом повторить ту саму прогалину. */
test("рівно на порозі labelTier підпис уже схований — і в mode, і в view", () => {
  const m = barModel({ ...base, mode: "overview" });
  const mode = m.zone2.find((x) => x.id === "mode");
  const view = m.zone2.find((x) => x.id === "view");
  assert.equal(mode.labelTier, TIERS.mode, "mode: labelTier не той ярус");
  assert.equal(view.labelTier, TIERS.mode, "view: labelTier не той ярус");
  for (const item of [mode, view]) {
    assert.equal(labelVisibleAt(item, TIERS.mode), false,
      `${item.id}: на ширині рівно ${TIERS.mode} підпис мусить бути схований`);
    assert.equal(labelVisibleAt(item, TIERS.mode + 1), true,
      `${item.id}: на ${TIERS.mode + 1} підпис мусить вернутись`);
  }
});

/* Ревʼю Task 8 (п.4): `gl`, на відміну від `publish`, ніс лише `status` —
   DOM-шар мусив би сам додумувати, які пункти дропдауна показувати. Прототип
   (`ddGitlab`, `docs/proto/shell.html`) розгалужує це не навпіл, а на ЧОТИРИ
   випадки: «off» — нема з чим працювати, крім «Налаштувати» (ні «Надіслати»,
   ні історії — репозиторій не підключений); «behind» — додається
   «Підтягнути»; «ahead»/«sync» — лишається «Надіслати» (вимкнене й з
   причиною лише при «sync») та історія. */
test("меню GitLab: набір пунктів залежить від стану синхронізації", () => {
  const items = (gl) => barModel({ ...base, gl }).zone3.find((x) => x.id === "gl")
    .items.map((x) => x.id);
  assert.deepEqual(items("off"), ["glsetup"], "off: тільки «Налаштувати»");
  assert.deepEqual(items("behind"), ["glpull", "glpush", "glhistory"]);
  assert.deepEqual(items("ahead"), ["glpush", "glhistory"]);
  assert.deepEqual(items("sync"), ["glpush", "glhistory"]);
});

test("«Надіслати» вимкнений лише коли вже збігається, і несе причину", () => {
  const push = (gl) => barModel({ ...base, gl }).zone3.find((x) => x.id === "gl")
    .items.find((x) => x.id === "glpush");
  assert.equal(push("sync").disabled, true);
  assert.equal(push("sync").whyKey, "glSync");
  assert.equal(push("behind").disabled, false);
  assert.equal(push("ahead").disabled, false);
});

/* Ревʼю Task 8 (п.5): у прототипі поруч із підписом ітерації стоять дві мітки
   — зелена крапка («в превью», уже наш `iterPub`) і хмара («ця ітерація
   збігається з GitLab» — нове поле `iterOnGl`). Модель губила обидві. */
test("крошка ітерації несе мітки «в превью» і «збігається з GitLab»", () => {
  const iter = (s) => barModel(s).zone1.find((x) => x.id === "iter");
  assert.equal(iter(base).pub, true);
  assert.equal(iter(base).onGl, true);
  assert.equal(iter({ ...base, iterPub: false }).pub, false);
  assert.equal(iter({ ...base, iterOnGl: false }).onGl, false);
});

/* Ревʼю Task 8 (п.7): «задача без ітерацій» — реальний старт кожної нової
   задачі, і фікстура носила `hasIteration` без жодного assert. Крошки
   ітерації тоді немає ЗОВСІМ (не «є, але вимкнена») — так само, як
   інспектор чи «Флоу» зникають, а не показуються бляклими. */
test("задача без ітерацій: крошки ітерації нема, крошка задачі є", () => {
  const m = barModel({ ...base, hasIteration: false });
  assert.ok(m.zone1.some((x) => x.id === "task"), "крошка задачі мусить лишитись");
  assert.ok(!m.zone1.some((x) => x.id === "iter"), "крошки ітерації без ітерації бути не може");
});

/* Друге незахищене поле фікстури: довільна ширина полотна (`vpw`) — вона має
   сенс лише в «Макеті», в «Огляді» кадри вже зняті під фіксовані пресети. */
test("довільна ширина полотна доступна лише в «Макеті»", () => {
  const vp = (s) => barModel(s).zone2.find((x) => x.id === "vp");
  assert.equal(vp(base).showCustom, true);
  assert.equal(vp({ ...base, mode: "overview" }).showCustom, false);
});

/* Ревʼю Task 8 (п.6): стан «tasks.json не читається» був не описаний узагалі
   — у прототипі під трьома зонами зʼявляється смуга помилки з причиною й
   кнопкою «Спробувати ще» (`renderBar`, `c.tasksErr`). Модель віддає це
   четвертим полем, не змішуючи з зонами: помилка — не контрол смуги. */
test("«tasks.json не читається» — модель віддає error з причиною й кнопкою «ще раз»", () => {
  assert.equal(barModel(base).error, null, "у базовому стані помилки нема");
  assert.deepEqual(barModel({ ...base, tasksErr: "unexpected token" }).error,
    { whyKey: "tasksErr", retry: true });
});

/* Причина буває НЕ в наших файлах: коли на порту канваса відповідає сторонній
   процес, той самий збій розбору означає «це не наш сервер», а не «побився
   tasks.json». Ключ приходить окремим полем, а не замість `tasksErr`: сам
   прапорець «помилка є» і ПРИЧИНА — різні величини, і склеїти їх означало б
   зробити з тексту причини перемикач стану. */
test("причину смуги помилки можна назвати точніше за типову", () => {
  assert.deepEqual(
    barModel({ ...base, tasksErr: "unexpected token", tasksErrKey: "tasksErrPort" }).error,
    { whyKey: "tasksErrPort", retry: true });
  // Без ключа — типова причина, як і було.
  assert.equal(barModel({ ...base, tasksErr: "x" }).error.whyKey, "tasksErr");
  // Ключ без помилки смуги не малює: помилки ж немає.
  assert.equal(barModel({ ...base, tasksErrKey: "tasksErrPort" }).error, null);
});

/* РЕГРЕС, який уже стався: коли панельний `<select>` прибрали, разом із ним
   зник ЄДИНИЙ спосіб обрати не-останню ітерацію — у `app.js` `picked` інакше
   встановлюється лише на останню, на щойно створену, або скидається. Для
   менеджера ітерацій це втрата основної функції, і жоден тест її не тримав.
   Тепер тримає: крошка ітерації несе перелік, а не саму лише поточну. */
test("крошка ітерації несе перелік, а не лише поточну", () => {
  const st = {
    ...base,
    iterId: "it2",
    iterList: [
      { id: "it1", label: "Іт.1", note: "перша", pub: true, onGl: true },
      { id: "it2", label: "Іт.2", note: "друга", pub: false, onGl: false },
      { id: "it3", label: "Іт.3", note: "", pub: true, onGl: false },
    ],
  };
  const it = barModel(st).zone1.find((x) => x.id === "iter");
  assert.equal(it.items.length, 3, "переліку ітерацій немає — перемкнути нічим");
  assert.deepEqual(it.items.map((x) => x.id), ["it1", "it2", "it3"]);
  const cur = it.items.filter((x) => x.on);
  assert.deepEqual(cur.map((x) => x.id), ["it2"], "поточна позначена не одна");
  /* Позначки їдуть у перелік: інакше довелось би відкривати кожну ітерацію,
     щоб дізнатись, яка в превью і яку бачить колега на GitLab. */
  assert.equal(it.items[0].pub, true);
  assert.equal(it.items[0].onGl, true);
});

/* Підпис автора й ознака чужої ітерації — те, заради чого вся задача про
   передачу задачі між дизайнерами. Модель мусить нести їх ДАНИМИ: складати
   підпис («Іт.6 · Ольга») тут означало б робити це мовою збірки, а мову
   вибирає глядач — той самий розділ, що вже двічі лікували 02.09.2026. */
test("крошка ітерації несе автора, ознаку «своя/чужа» і походження", () => {
  const st = {
    ...base,
    iterId: "it6", iterAuthor: "Lead", iterMine: true,
    iterList: [
      { id: "it5", label: "Іт.5", note: "", author: "Ольга Сидорук",
        mine: false, origin: { it: "it3" } },
      { id: "it6", label: "Іт.6", note: "правки", author: "Lead", mine: true },
    ],
  };
  const it = barModel(st).zone1.find((x) => x.id === "iter");
  assert.equal(it.author, "Lead");
  assert.equal(it.mine, true);
  assert.deepEqual(it.items.map((x) => [x.author, x.mine]),
    [["Ольга Сидорук", false], ["Lead", true]]);
  assert.equal(it.items[0].origin.it, "it3", "номер ітерації в автора загубився");
});

/* Стара задача без підписів: «своя» за замовчуванням. Інакше вся наявна
   історія раптом стала б чужою — тобто непушабельною. */
test("ітерація без автора вважається своєю", () => {
  const it = barModel({
    ...base, iterList: [{ id: "it1", label: "Іт.1", note: "" }],
  }).zone1.find((x) => x.id === "iter");
  assert.equal(it.items[0].mine, true);
  assert.equal(it.items[0].author, "");
});

test("порожній перелік не ламає крошку", () => {
  const it = barModel({ ...base, iterList: [] }).zone1.find((x) => x.id === "iter");
  assert.deepEqual(it.items, []);
});

/* Логотип — перший контрол зони 1, ПЕРЕД палітрою (батч 1.52, екран «Задачі»).
   Порядок змінено свідомо: раніше палітра була головою зони 1, і тест це
   фіксував. Логотип відповідає на «де я / як вийти до всіх задач» — це старший
   рівень за палітру («що я можу»), тому він стоїть першим. Палітра далі
   несе ярус підпису; `tier: 0` бо саму кнопку ховати нікуди: у зоні 1 немає
   «⋯», і схована кнопка стала б знову зниклою дією — рівно тим, що ця кнопка
   й лікує. */
test("зона 1 починається з логотипа, далі палітра, і її підпис має ярус", () => {
  const m = barModel(base);
  assert.equal(m.zone1[0].id, "home", "логотип не перший в зоні 1");
  assert.equal(m.zone1[0].tier, 0, "логотип ховати нікуди");
  assert.equal(m.zone1[0].on, false, "без homeOpen логотип не активний");
  assert.equal(m.zone1[1].id, "palette", "палітра мусить лишитись другою");
  assert.equal(m.zone1[1].tier, 0, "саму кнопку палітри ховати нікуди");
  assert.equal(m.zone1[1].labelTier, TIERS.mode,
    "підпис палітри мусить зникати разом із рештою підписів");
  assert.equal(m.zone1[2].id, "task", "крошка задачі мусить лишитись третьою");
});

/* `on` — те, що фарбує логотип «ми на екрані Задачі». Якби модель його не
   несла, розмітка не мала б звідки взяти підсвітку. */
test("логотип активний рівно коли відкритий екран «Задачі»", () => {
  assert.equal(barModel({ ...base, homeOpen: true }).zone1[0].on, true);
  assert.equal(barModel({ ...base, homeOpen: false }).zone1[0].on, false);
});

/* Без ітерації зона 1 — це логотип + палітра + задача, і не більше: палітра не
   сміє зникнути разом із крошкою ітерації (вона до неї не має стосунку). */
test("палітра лишається, коли ітерації немає", () => {
  const m = barModel({ ...base, hasIteration: false });
  assert.equal(m.zone1[0].id, "home");
  assert.equal(m.zone1[1].id, "palette");
  assert.equal(m.zone1.length, 3, "очікував логотип + палітру + задачу");
});

/* Екран «Задачі»: склад смуги описує МОДЕЛЬ (принцип 5 PRODUCT.md — контрол,
   безглуздий у цьому режимі, прихований), розмітка лише малює. Без задачі
   (`taskId` порожній) «Назад» не має куди вести — його немає, а не мертвий. */
test("екран «Задачі»: логотип, палітра, крошка «Задачі», «Назад до …» — і нічого з макета", () => {
  const m = barModel({ ...base, homeOpen: true });
  assert.deepEqual(m.zone1.map((x) => x.id), ["home", "palette", "crumb-tasks", "back"]);
  assert.equal(m.zone1[0].on, true);
  assert.equal(m.zone1[2].labelKey, "tasks");
  assert.equal(m.zone1[3].label, base.taskId, "«Назад» мусить нести ключ поточної задачі");
  assert.deepEqual(m.zone2, [], "перемикач «Макет/Огляд» без задачі безглуздий");
  assert.deepEqual(m.zone3, [], "публікація/GitLab/Figma без вигляду задачі безглузді");
  assert.equal(barModel({ ...base, homeOpen: true, taskId: "" }).zone1
    .some((x) => x.id === "back"), false, "без задачі «Назад» вести нікуди");
});

/* «В Figma» (T-41) — зона 3 «куди віддаю», ПЕРЕД GitLab: головна кнопка
   публікації лишається крайньою справа. Рішення власника 28.09.2026. */
test("«В Figma» — перший контрол зони 3, підпис ховається разом із GitLab", () => {
  const m = barModel(base);
  assert.deepEqual(m.zone3.map((x) => x.id), ["figma", "gl", "publish"]);
  const f = m.zone3[0];
  assert.equal(f.tier, 0, "саму кнопку ховати нікуди: у зоні 3 немає «⋯»");
  assert.equal(f.labelTier, TIERS.gl);
  assert.equal(f.disabled, false);
});

/* Контрол не бреше про режим: в «Огляді» кадри — знімки, живого DOM немає, і
   захоплювати нічого. На відміну від інспектора кнопка НЕ зникає, а стоїть
   вимкненою з причиною: вона в зоні «куди віддаю», і її зникнення зсувало б
   GitLab і публікацію при кожному перемиканні режиму. */
test("«В Figma» вимкнена з причиною там, де макета немає", () => {
  const f = (o) => barModel({ ...base, ...o }).zone3.find((x) => x.id === "figma");
  assert.deepEqual([f({ mode: "overview" }).disabled, f({ mode: "overview" }).whyKey],
    [true, "whyFigmaOverview"]);
  assert.deepEqual([f({ hasIteration: false }).disabled, f({ hasIteration: false }).whyKey],
    [true, "whyFigmaNoMockup"]);
  assert.deepEqual([f({ figmaBusy: true }).disabled, f({ figmaBusy: true }).whyKey],
    [true, "whyFigmaBusy"]);
  assert.equal(f({ figmaBusy: true }).busy, true);
});

test("figmaWhyKey: «Огляд» важливіший за решту причин", () => {
  assert.equal(figmaWhyKey({ ...base, mode: "overview", hasIteration: false, figmaBusy: true }),
    "whyFigmaOverview");
  assert.equal(figmaWhyKey({ ...base, hasIteration: false, figmaBusy: true }), "whyFigmaNoMockup");
  assert.equal(figmaWhyKey(base), "");
});

/* Живий тест `shell.test.mjs` зловив: на 1360 в «Огляді» зона 3 не влазила на
   10px (зона 2 там ширша на «Сітка/Флоу»). Рішення власника 28.09.2026: у
   «Огляді», де кнопка однаково вимкнена, — лише іконка. */
test("«В Figma» в «Огляді» — лише іконка, у «Макеті» — з підписом", () => {
  const f = (o) => barModel({ ...base, ...o }).zone3.find((x) => x.id === "figma");
  assert.equal(f({ mode: "overview" }).iconOnly, true);
  assert.equal(f({}).iconOnly, false);
});

/* ── простори (Deai 1.0, етап 1) ──────────────────────────────────────────────
   Фішка простору — у зоні 1 («де я»), ПЕРЕД крошкою задачі: задача живе в
   просторі, тож шлях читається зліва направо. Без `space` (шар просторів
   вимкнено чи просторів ще нема) смуга така, як була, — жодного порожнього
   місця під фішку. `integrations === false` прибирає з зони 3 рівно те, що
   ходить назовні (GitLab і публікацію); «В Figma» лишається — вона працює по
   живому макету, а не по зовнішній службі. */
const SP = (o = {}) => ({ id: "p", name: "P", color: "space-2", integrations: false, ...o });

test("простір: фішка в зоні 1 між палітрою й задачею, з назвою і кольором", () => {
  const m = barModel({ ...base, space: SP() });
  assert.deepEqual(m.zone1.map((x) => x.id), ["home", "palette", "space", "task", "iter"]);
  const chip = m.zone1[2];
  assert.equal(chip.label, "P");
  assert.equal(chip.color, "space-2");
  assert.equal(chip.tier, 0, "фішку ховати нікуди: у зоні 1 немає «⋯»");
});

test("простір: без `space` — смуга як була, фішки нема (шар вимкнено / просторів нема)", () => {
  for (const space of [undefined, null]) {
    const m = barModel({ ...base, space });
    assert.deepEqual(m.zone1.map((x) => x.id), ["home", "palette", "task", "iter"]);
    assert.deepEqual(m.zone3.map((x) => x.id), ["figma", "gl", "publish"]);
  }
});

test("простір на екрані «Задачі»: фішка є, між палітрою й крошкою «Задачі»", () => {
  const m = barModel({ ...base, space: SP(), homeOpen: true });
  assert.deepEqual(m.zone1.map((x) => x.id), ["home", "palette", "space", "crumb-tasks", "back"]);
  assert.equal(m.zone1[2].label, "P");
});

test("простір без інтеграцій: у зоні 3 нема GitLab і публікації, «В Figma» лишається", () => {
  const m = barModel({ ...base, space: SP({ integrations: false }) });
  assert.deepEqual(m.zone3.map((x) => x.id), ["figma"]);
});

test("простір З інтеграціями: зона 3 — як була", () => {
  for (const integrations of [true, undefined]) {
    const m = barModel({ ...base, space: SP({ integrations }) });
    assert.deepEqual(m.zone3.map((x) => x.id), ["figma", "gl", "publish"], String(integrations));
  }
});

test("вимикач інтеграцій — рівно `integrations === false`, а не «нема значення»", () => {
  // `space` без поля `integrations` (відповідь старої форми) не має красти GitLab у людини.
  const m = barModel({ ...base, space: { id: "p", name: "P", color: "space-1" } });
  assert.deepEqual(m.zone3.map((x) => x.id), ["figma", "gl", "publish"]);
});

test("простір: id у всій смузі лишаються унікальними", () => {
  const m = barModel({ ...base, space: SP() });
  const ids = [...m.zone1, ...m.zone2, ...m.zone3].map((x) => x.id);
  assert.equal(new Set(ids).size, ids.length);
});

/* ── публікація за `capabilities.publish` (модулі 2а, Task 8) ─────────────────
   Зона 3 більше не питає «є інтеграції?» про ВСЕ назовні разом: GitLab і Teams
   лишились на `integrations`, а публікація пішла на `hasPublish`
   (`spaces-model.js`) — простір без інтеграцій публікує вбудованим модулем у
   теку. Пункти дропдауна фільтруються поштучно: пароль ЛІГА (`pubpw`) — лише
   коли публікує саме ЛІГА, Teams — лише з інтеграціями. */
const CAPS = (publish, o = {}) => ({
  id: "p", name: "P", color: "space-2", integrations: false, capabilities: { publish, tokens: null }, ...o,
});
const pubItems = (s) => barModel({ ...base, ...s }).zone3.find((x) => x.id === "publish")?.items.map((x) => x.id);

test("простір без інтеграцій з модулем публікації: публікація є, GitLab нема", () => {
  const m = barModel({ ...base, space: CAPS("static-publish") });
  assert.deepEqual(m.zone3.map((x) => x.id), ["figma", "publish"]);
});

test("публікація модулем: у дропдауні лише показ, відкриття й посилання — без пароля ЛІГА і без Teams", () => {
  assert.deepEqual(pubItems({ space: CAPS("static-publish"), teams: null }), ["togglepub", "openpreview", "copylink"]);
  assert.deepEqual(pubItems({ space: CAPS("static-publish"), teams: { channel: "dc/x", muted: false } }),
    ["togglepub", "openpreview", "copylink"], "інтеграцій нема — Teams нема, хоч би дані й були");
});

test("простір без постачальника публікації (`publish: null`): ні публікації, ні GitLab — лишається «В Figma»", () => {
  assert.deepEqual(barModel({ ...base, space: CAPS(null) }).zone3.map((x) => x.id), ["figma"]);
  assert.deepEqual(barModel({ ...base, space: CAPS(null, { integrations: true }) }).zone3.map((x) => x.id),
    ["figma", "gl"], "публікації нема (її вимкнено), GitLab лишився на інтеграціях");
});

test("простір ЛІГА (`publish: 'legacy'`): усе як було, пароль превʼю й Teams — на місці", () => {
  const sp = CAPS("legacy", { integrations: true });
  assert.deepEqual(barModel({ ...base, space: sp }).zone3.map((x) => x.id), ["figma", "gl", "publish"]);
  assert.deepEqual(pubItems({ space: sp, teams: { channel: "dc/x", muted: false } }),
    ["togglepub", "openpreview", "copylink", "teamsnotify", "pubpw"]);
});

test("`pubpw` — лише коли публікує ЛІГА: ні для модуля, ні там, де модуль підмінив ЛІГА при інтеграціях", () => {
  assert.ok(!pubItems({ space: CAPS("static-publish") }).includes("pubpw"));
  assert.ok(!pubItems({ space: CAPS("static-publish", { integrations: true }) }).includes("pubpw"));
  assert.ok(pubItems({ space: CAPS("legacy", { integrations: true }) }).includes("pubpw"));
  assert.ok(pubItems({ space: { id: "x", integrations: true } }).includes("pubpw"), "стара форма з інтеграціями");
  assert.ok(pubItems({}).includes("pubpw"), "без `space` — як було");
});

test("Teams у дропдауні — лише з інтеграціями; без них пункт не висить вічним «перевіряю…»", () => {
  // Без інтеграцій `app.js` тримає `teams: null` ВІЧНО (стану тиші там нема, `/api/teams-mute` → 409).
  assert.ok(!pubItems({ space: CAPS("static-publish"), teams: null }).includes("teamsnotify"));
  // З інтеграціями `null` — це коротка мить завантаження: пункт стоїть вимкненим з причиною.
  const it = barModel({ ...base, space: CAPS("legacy", { integrations: true }), teams: null }).zone3
    .find((x) => x.id === "publish").items.find((x) => x.id === "teamsnotify");
  assert.equal(it.disabled, true);
  assert.equal(it.whyKey, "whyTeamsLoading");
  // модуль при ввімкнених інтеграціях: Teams живий, пароля ЛІГА нема
  assert.ok(pubItems({ space: CAPS("static-publish", { integrations: true }), teams: { channel: "c", muted: false } })
    .includes("teamsnotify"));
});

test("стара форма відповіді (без `capabilities`) — рішення за `integrations`, як і було", () => {
  assert.deepEqual(barModel({ ...base, space: { id: "p", integrations: false } }).zone3.map((x) => x.id), ["figma"]);
  assert.deepEqual(barModel({ ...base, space: { id: "p", integrations: true } }).zone3.map((x) => x.id),
    ["figma", "gl", "publish"]);
  assert.deepEqual(barModel({ ...base, space: { id: "p" } }).zone3.map((x) => x.id), ["figma", "gl", "publish"]);
});

test("публікація: `legacy` на контролі каже, чий це постачальник (розмітка ховає застереження про ЛІГА-гейт)", () => {
  const ctl = (space) => barModel({ ...base, space }).zone3.find((x) => x.id === "publish");
  assert.equal(ctl(CAPS("legacy", { integrations: true })).legacy, true);
  assert.equal(ctl(CAPS("static-publish")).legacy, false);
  assert.equal(ctl(undefined).legacy, true);
});

test("локальна публікація: «Відкрити» і «Скопіювати» несуть підпис «локально» (з часом, коли він відомий)", () => {
  const items = (o) => Object.fromEntries(barModel({ ...base, space: CAPS("static-publish"), ...o }).zone3
    .find((x) => x.id === "publish").items.map((x) => [x.id, x]));
  const local = items({ pubLocal: true, pubWhen: "5 хв тому" });
  assert.equal(local.openpreview.subKey, "publishLocalSub");
  assert.deepEqual(local.openpreview.subArgs, ["5 хв тому"]);
  assert.equal(local.copylink.subKey, "publishLocalLinkSub");
  const noWhen = items({ pubLocal: true });
  assert.deepEqual(noWhen.openpreview.subArgs, [""]);
  const ext = items({});
  assert.equal(ext.openpreview.subKey, undefined, "не локальна — без підпису");
  assert.equal(ext.copylink.subKey, undefined);
});

test("публікація для `published`: непублікована — «Опублікувати» й вимкнені відкриття/посилання з причиною", () => {
  const m = barModel({ ...base, published: false, space: CAPS("static-publish") });
  const pub = m.zone3.find((x) => x.id === "publish");
  assert.equal(pub.labelKey, "publish");
  assert.equal(pub.items.find((x) => x.id === "openpreview").whyKey, "whyNoPublish");
  assert.equal(pub.items.find((x) => x.id === "copylink").whyKey, "whyNoPublish");
});
