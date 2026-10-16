/**
 * Юніти ЧИСТОЇ моделі тюнера (`app/tuner-model.js`).
 *
 * Модель не торкається ні DOM, ні мережі, тож усе нижче — звичайні виклики з
 * підробленими `ident`/`decl`. Живу частину (звідки ці два об'єкти беруться —
 * `CanvasInspector.identity()` і `describe()`) стереже
 * `tests/live/tuner-identity.test.mjs`: підробити CSSOM у node означало б
 * перевіряти НАШІ уявлення про браузер.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»
 * (знята мутаційно, не написана з голови):
 *
 *   B («було» первинне) — гілка `was ? was.from : …` у `setEdit`. МУТАЦІЯ:
 *                         писати `from` щоразу заново (`from: str(decl.computed)`).
 *                         Після трьох поворотів ручки «було» дорівнює «стало»,
 *                         пакет каже «зміни 18px на 18px» — тобто ціле поле
 *                         перестає щось означати, а тести решти лишаються
 *                         зеленими: форма пакета не міняється. ПЕРЕВІРЕНО:
 *                         червоніє.
 *   H (рівень підказки) — явне перенесення `tier` у `hintOf` і в `packageJSON`.
 *                         МУТАЦІЯ: у `packageJSON` віддавати `{ name: h.name }`.
 *                         Тоді здогад («токен оголошений, але ніде не вжитий, і
 *                         збігається лише ФОРМА значення») стає в пакеті
 *                         неотличним від доведеного вжитком — і дефект, який
 *                         щойно полагодили (токен z-index, порекомендований для
 *                         font-weight), вертається не по одному рядку, а
 *                         гуртом. ПЕРЕВІРЕНО: червоніє.
 *   C (повернення)      — звірка через `normalizeValue`. Прибери її зовсім —
 *                         у пакеті лишиться правка-пустушка; звіряй рядки
 *                         навпростець — `#FFF` проти `#ffffff` дасть ту саму
 *                         пустушку, лише рідше.
 *   G (групування)      — ключ елемента береться з ЛАНЦЮЖКА, а не з `rule`
 *                         правки. Візьми `ident.selector` — і один блок, у
 *                         якому накрутили дві ручки з різних правил CSS,
 *                         розсиплеться в пакеті на два «елементи».
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  PKG_KIND, PKG_VERSION, clearEdit, editCount, elementKey, emptyTune,
  fromPackage, markReady, packageJSON, setDs, setEdit, setNote,
} from "../app/tuner-model.js";

/* Ознаки елемента — рівно те, що віддає `CanvasInspector.identity(prop)`.
   `selector` тут — селектор ПРАВИЛА, що виграло каскад для властивості (у
   різних властивостей він різний), а ключем елемента служить `trail`. */
const IDENT = {
  trail: ["body", "div.wrap", "p.card"],
  label: "p.card",
  selector: ".card",
  text: "Картка компанії",
};

/* Сусідній елемент: той самий підпис, ІНШИЙ ланцюжок. Саме так у макетах і
   буває (десять карток поспіль), і саме тому ключ — ланцюжок, а не підпис. */
const OTHER = { ...IDENT, trail: ["body", "div.side", "p.card"] };

/** Рядок звіту `describe()` — значення з токена. */
const TOKEN_DECL = {
  prop: "padding-top",
  computed: "16px",
  raw: "var(--sp-4)",
  token: "--sp-4",
  tokenValue: "16px",
  verdict: "token",
  hint: [],
};

/** Рядок звіту — хардкод із двома підказками РІЗНОГО рівня впевненості. */
const HARD_DECL = {
  prop: "font-weight",
  computed: "700",
  raw: "700",
  token: null,
  tokenValue: null,
  verdict: "hardcode",
  hint: [{ name: "--fw-bold", tier: "used" }, { name: "--fw-strong", tier: "shape" }],
};

/** Єдина правка пакета — щоб кожна перевірка не розкопувала вкладеність. */
function onlyEdit(pkg) {
  assert.equal(pkg.elements.length, 1, "мусить бути рівно один елемент");
  assert.equal(pkg.elements[0].edits.length, 1, "мусить бути рівно одна правка");
  return pkg.elements[0].edits[0];
}

test("A. правка несе було/стало І ПОХОДЖЕННЯ значення — інакше Клоду нема де правити", () => {
  const st = setEdit(emptyTune(), "holovna", IDENT, TOKEN_DECL, "24px");
  const pkg = packageJSON(st);
  const e = onlyEdit(pkg);

  assert.equal(e.prop, "padding-top");
  assert.equal(e.from, "16px", "«було» — те, що показував браузер до кручення");
  assert.equal(e.to, "24px");
  // Без `raw` і переможця каскаду пакет каже ЩО змінити, але не ДЕ.
  assert.equal(e.raw, "var(--sp-4)");
  assert.equal(e.rule, ".card", "селектор правила, що виграло каскад ДЛЯ ЦІЄЇ властивості");
  assert.equal(e.token, "--sp-4");
  assert.equal(e.tokenValue, "16px");
  // Без вироку Клод вигадає «найближчий токен» замість сказати, що його немає.
  assert.equal(e.verdict, "token");
  assert.deepEqual(e.hint, []);

  // Елемент несе ВСІ ознаки, а не лише шлях: пакет читатимуть уже після того,
  // як сторінку перепишуть, і `div > div:nth-child(3)` на той час не вказує
  // нікуди.
  const el = pkg.elements[0];
  assert.deepEqual(el.trail, ["body", "div.wrap", "p.card"]);
  assert.equal(el.label, "p.card");
  assert.equal(el.text, "Картка компанії");
  assert.equal(el.selector, "body > div.wrap > p.card");
  assert.equal(el.page, "holovna");
});

test("B. повторний поворот ручки рухає «стало»; «було» лишається ПЕРВИННИМ", () => {
  /* ⚠️ Кожен наступний поворот приходить із СВІЖИМ рядком звіту, і саме в
     цьому вся перевірка. Ручка тюнера жива: значення вже видно на макеті, тож
     наступний `describe()` бачить у `computed` те, що накрутили минулого разу.
     Перша версія цієї перевірки тричі підсовувала ОДИН І ТОЙ САМИЙ `decl` з
     `computed: '16px'` — і мутація «писати `from` щоразу заново» її пережила,
     бо `str(decl.computed)` тоді щоразу давав ту саму шістнадцятку. Тобто
     охоронець був фікцією рівно доти, доки тест не почав відтворювати
     справжню послідовність. */
  const live = (computed) => ({ ...TOKEN_DECL, computed });
  let st = setEdit(emptyTune(), "holovna", IDENT, live("16px"), "24px");
  st = setEdit(st, "holovna", IDENT, live("24px"), "32px");
  st = setEdit(st, "holovna", IDENT, live("32px"), "40px");

  assert.equal(editCount(st), 1, "три повороти однієї ручки — це одна правка");
  const e = onlyEdit(packageJSON(st));
  assert.equal(e.from, "16px",
    "після трьох поворотів «було» дорівнювало б «стало» — і пакет нічого не означав би");
  assert.equal(e.to, "40px");

  /* І походження теж знімається з ПЕРШОГО повороту: `raw`/`token` описують
     те, що написано в CSS, а не те, що дизайнер накрутив поверх. */
  assert.equal(e.raw, "var(--sp-4)");
  assert.equal(e.verdict, "token");
});

test("C. повернення значення до первинного ПРИБИРАЄ правку, а не пише пустушку", () => {
  /* Звіт знову СВІЖИЙ на кожному повороті (див. застереження у перевірці B):
     повертаючи ручку назад, дизайнер робить це з уже накрученого стану. */
  let st = setEdit(emptyTune(), "holovna", IDENT, TOKEN_DECL, "24px");
  assert.equal(editCount(st), 1, "свідок: правка спершу мусить зʼявитись");
  st = setEdit(st, "holovna", IDENT, { ...TOKEN_DECL, computed: "24px" }, "16px");
  assert.equal(editCount(st), 0);
  assert.deepEqual(packageJSON(st).elements, [], "порожній елемент у пакеті — теж брехня");

  /* Звірка — тим самим міряльним інструментом, що й решта інспектора: інакше
     «повернув як було» руками (`#FFF` замість `#ffffff`, `0` замість `0px`)
     лишало б у пакеті привида. */
  const colorDecl = { ...TOKEN_DECL, prop: "color", computed: "#ffffff", raw: "#ffffff" };
  let c = setEdit(emptyTune(), "holovna", IDENT, colorDecl, "#123456");
  c = setEdit(c, "holovna", IDENT, { ...colorDecl, computed: "#123456" }, "#FFF");
  assert.equal(editCount(c), 0, "#FFF і #ffffff — те саме значення, отже правки немає");
});

test("D. правки скоупляться по сторінці — сусідня не бачить чужих", () => {
  let st = setEdit(emptyTune(), "holovna", IDENT, TOKEN_DECL, "24px");
  st = setEdit(st, "poshuk", IDENT, HARD_DECL, "600");

  assert.equal(editCount(st), 2);
  assert.equal(packageJSON(st, "holovna").editCount, 1);
  assert.deepEqual(packageJSON(st, "holovna").elements.map((e) => e.page), ["holovna"]);
  assert.equal(packageJSON(st, "poshuk").elements[0].edits[0].prop, "font-weight");
  assert.equal(packageJSON(st, "poshuk").page, "poshuk", "пакет мусить казати, чим його відфільтрували");

  // Без фільтра — усі, і кожен елемент сам каже, з якої він сторінки.
  const all = packageJSON(st);
  assert.equal(all.page, null);
  assert.deepEqual(all.elements.map((e) => e.page).sort(), ["holovna", "poshuk"]);
});

test("E. записка Клоду їде в пакет ОКРЕМИМ полем", () => {
  let st = setEdit(emptyTune(), "holovna", IDENT, TOKEN_DECL, "24px");
  st = setNote(st, "Зроби картку щільнішою, але відступ зверху лиши як є");
  const pkg = packageJSON(st);
  assert.equal(pkg.note, "Зроби картку щільнішою, але відступ зверху лиши як є");
  assert.equal(onlyEdit(pkg).to, "24px", "записка не сміє підмінити собою правки");
  assert.equal(packageJSON(emptyTune()).note, "", "без записки — порожній рядок, не undefined");
});

test("F. clearEdit прибирає ОДНУ правку, а не весь елемент", () => {
  let st = setEdit(emptyTune(), "holovna", IDENT, TOKEN_DECL, "24px");
  st = setEdit(st, "holovna", IDENT, HARD_DECL, "600");
  assert.equal(editCount(st), 2);

  const key = elementKey(IDENT);
  st = clearEdit(st, "holovna", key, "padding-top");
  assert.equal(editCount(st), 1);
  const pkg = packageJSON(st);
  assert.equal(pkg.elements.length, 1, "елемент мусить лишитись — у ньому ще є правка");
  assert.deepEqual(pkg.elements[0].edits.map((e) => e.prop), ["font-weight"]);

  // Остання правка забирає з собою і елемент, і сторінку: порожній елемент
  // у пакеті читався б як «тут щось крутили».
  st = clearEdit(st, "holovna", key, "font-weight");
  assert.equal(editCount(st), 0);
  assert.deepEqual(packageJSON(st).elements, []);

  // Сміттєві адреси — тихо нічого: панель могла спитати про правку, якої вже
  // немає, і падати на цьому модель не має права.
  const one = setEdit(emptyTune(), "holovna", IDENT, TOKEN_DECL, "24px");
  assert.equal(editCount(clearEdit(one, "holovna", key, "margin-top")), 1);
  assert.equal(editCount(clearEdit(one, "poshuk", key, "padding-top")), 1);
  assert.equal(editCount(clearEdit(one, "holovna", "body > div", "padding-top")), 1);
  // Успадковане з прототипу не є правкою.
  assert.equal(editCount(clearEdit(one, "holovna", key, "constructor")), 1);
});

test("G. пакет групує ПО ЕЛЕМЕНТУ — навіть коли правила каскаду в правок різні", () => {
  /* Дві ручки в одному блоці, але виграли їх РІЗНІ правила CSS (`.card` для
     відступу, `#target` для ваги). Якби ключем елемента був селектор правила,
     блок розсипався б на два. */
  let st = setEdit(emptyTune(), "holovna", IDENT, TOKEN_DECL, "24px");
  st = setEdit(st, "holovna", { ...IDENT, selector: "#target" }, HARD_DECL, "600");
  st = setEdit(st, "holovna", OTHER, TOKEN_DECL, "8px");

  const pkg = packageJSON(st);
  assert.equal(pkg.elements.length, 2, "два ланцюжки — два елементи, три правки");
  assert.equal(pkg.editCount, 3);

  const card = pkg.elements.find((e) => e.selector === "body > div.wrap > p.card");
  assert.deepEqual(card.edits.map((e) => e.prop), ["padding-top", "font-weight"]);
  assert.deepEqual(card.edits.map((e) => e.rule), [".card", "#target"],
    "правило каскаду — у кожної правки СВОЄ, і воно мусить доїхати");

  const side = pkg.elements.find((e) => e.selector === "body > div.side > p.card");
  assert.equal(side.edits.length, 1, "однаковий підпис не сміє схлопнути два різні блоки");
});

test("H. рівень підказки доїжджає в пакет, і пакет каже, що здогад ЗАСТОСОВУВАТИ НЕ МОЖНА", () => {
  const st = setEdit(emptyTune(), "holovna", IDENT, HARD_DECL, "600");
  const pkg = packageJSON(st);
  const e = onlyEdit(pkg);

  // Свідок: без цього `deepEqual` на порожньому масиві був би зелений завжди.
  assert.equal(e.hint.length, 2, "обидві підказки мусять доїхати");
  assert.deepEqual(e.hint, [
    { name: "--fw-bold", tier: "used", ds: false },
    { name: "--fw-strong", tier: "shape", ds: false },
  ], "`tier` — єдине, що відрізняє доведений вжитком токен від ЗДОГАДУ за формою; "
    + "`ds` (T-40) — чи кандидат узагалі з дизайн-системи, і типове значення "
    + "тут ХИБНЕ: невідоме не сміє видавати себе за системне");

  /* Сам рівень у даних нічого не варт, поки читач не знає, що з ним робити:
     пакет читають у ІНШІЙ сесії, без цього контексту. Тому інструкція про
     здогад мусить лежати В ПАКЕТІ. */
  const shapeRule = pkg.instructions.filter((s) => /\bshape\b/.test(s));
  assert.equal(shapeRule.length, 1, "рівно один рядок інструкції мусить пояснювати здогад");
  assert.match(shapeRule[0], /confirm/i, "інструкція мусить вимагати підтвердження");
  assert.match(shapeRule[0], /do NOT apply|never apply/i,
    "і прямо забороняти застосовувати здогад мовчки");
  assert.match(pkg.instructions.join("\n"), /\bused\b/, "рівень «доведено вжитком» теж мусить бути описаний");

  // Підказка без рівня — це ЗДОГАД, а не факт: назвати її 'used' означало б
  // відмити здогад у доведення.
  const bare = setEdit(emptyTune(), "holovna", IDENT,
    { ...HARD_DECL, hint: [{ name: "--x" }] }, "600");
  assert.deepEqual(onlyEdit(packageJSON(bare)).hint,
    [{ name: "--x", tier: "shape", ds: false }]);
});

test("I. пакет самоописовий, серіалізовний і НЕ ділить посилань зі станом", () => {
  const st = setEdit(emptyTune(), "holovna", IDENT, HARD_DECL, "600");
  const pkg = packageJSON(st);

  assert.equal(pkg.kind, PKG_KIND, "читач приходить без контексту — пакет мусить назвати себе");
  assert.equal(pkg.version, PKG_VERSION);
  assert.equal(pkg.editCount, 1);
  assert.ok(pkg.instructions.length >= 5, "інструкція мусить бути, а не поле-заглушка");
  assert.equal(JSON.stringify(JSON.parse(JSON.stringify(pkg))), JSON.stringify(pkg),
    "пакет мусить переживати JSON без втрат");

  /* Той, кому пакет віддали, має право його мʼяти — модель від цього не сміє
     поїхати. */
  pkg.elements[0].edits[0].hint[0].tier = "used";
  pkg.elements[0].trail.push("zzz");
  pkg.instructions.length = 0;
  const again = packageJSON(st);
  assert.equal(again.elements[0].edits[0].hint[0].tier, "used");
  assert.deepEqual(again.elements[0].trail, ["body", "div.wrap", "p.card"]);
  assert.ok(again.instructions.length >= 5);
});

test("J. модель чиста: setEdit і clearEdit не чіпають вхідний стан", () => {
  const base = emptyTune();
  const one = setEdit(base, "holovna", IDENT, TOKEN_DECL, "24px");
  assert.equal(editCount(base), 0, "вхідний стан мусить лишитись порожнім");
  assert.notEqual(one, base);

  const two = setEdit(one, "holovna", IDENT, HARD_DECL, "600");
  assert.equal(editCount(one), 1, "попередній стан не сміє дізнатись про нову правку");
  assert.equal(editCount(two), 2);

  const less = clearEdit(two, "holovna", elementKey(IDENT), "font-weight");
  assert.equal(editCount(two), 2);
  assert.equal(editCount(less), 1);
});

test("K. правка, яку нікуди прикласти, не створюється — і не валить модель", () => {
  const base = emptyTune();
  assert.equal(editCount(setEdit(base, "", IDENT, TOKEN_DECL, "24px")), 0, "без сторінки");
  assert.equal(editCount(setEdit(base, "holovna", null, TOKEN_DECL, "24px")), 0, "без ознак елемента");
  assert.equal(editCount(setEdit(base, "holovna", { trail: [] }, TOKEN_DECL, "24px")), 0,
    "порожній ланцюжок і без підпису — адреси немає");
  assert.equal(editCount(setEdit(base, "holovna", IDENT, {}, "24px")), 0, "без властивості");
  assert.equal(editCount(setEdit(base, "holovna", IDENT, null, "24px")), 0, "без рядка звіту");

  // Ланцюжка немає, але підпис є — адреса гірша, проте є.
  const byLabel = setEdit(base, "holovna", { label: "p.card" }, TOKEN_DECL, "24px");
  assert.equal(editCount(byLabel), 1);
  assert.equal(packageJSON(byLabel).elements[0].selector, "p.card");

  // Сміття замість стану не сміє валити панель.
  assert.equal(editCount(null), 0);
  assert.equal(packageJSON(undefined).elements.length, 0);
  assert.equal(editCount(setEdit(null, "holovna", IDENT, TOKEN_DECL, "24px")), 1);
});

/* ── пакет із диска назад у стан (Task 16) ────────────────────────────────
   Канал на диск пише ПОВНИЙ пакет на кожну правку, тож без читання назад
   перший поворот ручки після перезавантаження канваса лягав би на файл
   пакетом з однієї правки — тобто мовчки зносив би роботу, яку дизайнер
   уважав збереженою. Дзеркальність двох функцій і є тим, що це тримає.

   Мутації, якими знята кожна перевірка нижче:
     · `fromPackage` повертає `emptyTune()` завжди → перша перевірка червоніє
       (round-trip дає порожній пакет), інші лишаються зеленими — тому
       перша й порівнює пакет ЦІЛКОМ, а не по полях;
     · прибрати `if (!prop) continue` → побита правка їде в стан із
       `prop: undefined` і вилазить у пакеті, третя перевірка червоніє;
     · замінити злиття `{ ...was.edits, ...edits }` на просте присвоєння →
       червоніє пʼята. Її вхід ЗУМИСНЕ не з `packageJSON`: наш писар одного
       ключа двічі на одну сторінку не кладе, тож перевірка на власному
       виході мутацію ПЕРЕЖИЛА (виміряно). А вхід тут — ФАЙЛ: його правлять
       руками, зливають із гілки й пише його інша версія інструмента. Гілка,
       яку неможливо довести, — гірша за відсутню, тому перевірка годує
       розбір саме тим, чого наш писар не пише. */

test("packageJSON → fromPackage → packageJSON: пакет повертається той самий", () => {
  let st = setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px");
  st = setEdit(st, "it1/holovna", IDENT, HARD_DECL, "900");
  st = setEdit(st, "it1/poshuk", OTHER, TOKEN_DECL, "32px");
  st = setNote(st, "картка затісна");
  const pkg = packageJSON(st);
  assert.deepEqual(packageJSON(fromPackage(pkg)), pkg,
    "прогін через диск щось загубив — саме цим і затирається робота");
  assert.equal(editCount(fromPackage(pkg)), 3);
});

test("відновлений стан ЖИВИЙ: його можна крутити далі й скидати", () => {
  const pkg = packageJSON(setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"));
  let st = fromPackage(pkg);
  /* Друга правка на ТОМУ САМОМУ елементі мусить лягти поруч, а не завести
     другий елемент: ключ рахується так само, як рахував до запису на диск. */
  st = setEdit(st, "it1/holovna", IDENT, HARD_DECL, "900");
  assert.equal(packageJSON(st).elements.length, 1);
  assert.equal(editCount(st), 2);
  st = clearEdit(st, "it1/holovna", "body > div.wrap > p.card", "padding-top");
  assert.equal(editCount(st), 1, "правку з диска неможливо скинути — ключ розійшовся");
});

test("побитий файл не валить розбір: непридатне пропускається, решта живе", () => {
  const good = packageJSON(setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"));
  const dirty = { ...good, elements: [
    null, "рядок замість елемента",
    { page: "it1/holovna", selector: "", edits: [] },        // нікуди прикласти
    { selector: "body > h1", edits: [{ prop: "gap", to: "4px" }] },  // без сторінки
    { page: "it1/holovna", selector: "body > h1", edits: [{ to: "4px" }, null] },
    ...good.elements,
  ] };
  const st = fromPackage(dirty);
  assert.equal(editCount(st), 1, "уціліла не рівно одна придатна правка");
  assert.equal(packageJSON(st).elements[0].selector, "body > div.wrap > p.card");
  // Сміття замість пакета теж не валить нічого.
  assert.equal(editCount(fromPackage(null)), 0);
  assert.equal(editCount(fromPackage("пакет")), 0);
  assert.equal(fromPackage(undefined).note, "");
});

test("здубльований елемент у ФАЙЛІ зливає правки, а не затирає їх", () => {
  /* Пакет, зібраний не нами: той самий елемент тієї самої сторінки записаний
     двома шматками. Так виглядає файл після ручної правки або злиття гілок —
     і саме тут просте присвоєння тихо з'їло б першу правку. */
  const dup = {
    kind: PKG_KIND, version: PKG_VERSION, page: null, note: "", editCount: 2,
    instructions: [], elements: [
      { page: "it1/holovna", selector: "body > h1", label: "h1", trail: ["body", "h1"],
        text: "Заголовок",
        edits: [{ prop: "font-size", from: "30px", to: "64px", hint: [] }] },
      { page: "it1/holovna", selector: "body > h1", label: "h1", trail: ["body", "h1"],
        text: "Заголовок",
        edits: [{ prop: "color", from: "#000", to: "#333", hint: [] }] },
    ],
  };
  const st = fromPackage(dup);
  assert.equal(editCount(st), 2, "другий запис затер перший — правка зникла з файла");
  assert.equal(packageJSON(st).elements.length, 1,
    "один елемент мусить лишитись одним, скільки б шматків не було у файлі");
  assert.deepEqual(packageJSON(st).elements[0].edits.map((e) => e.prop).sort(),
    ["color", "font-size"]);
});

test("однаковий селектор на двох сторінках лишається двома записами", () => {
  let st = setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px");
  st = setEdit(st, "it1/poshuk", IDENT, HARD_DECL, "900");
  const back = fromPackage(packageJSON(st));
  assert.equal(editCount(back), 2,
    "правки з двох сторінок схлопнулись в одну — сторінка перестала бути межею");
  assert.equal(packageJSON(back, "it1/holovna").editCount, 1);
  assert.equal(packageJSON(back, "it1/poshuk").editCount, 1);
});

/* ── `status`: чернетка чи готове (T-39) ──────────────────────────────────
   ⛔ Навіщо поле взагалі. Пакет зберігається АВТОМАТИЧНО, на кожен поворот
   ручки (`saveTune`, `app/app.js`), і саме так і мусить: нічого не губиться.
   Але читач від цього не міг відрізнити «дизайнер щойно крутнув і крутить
   далі» від «дизайнер закінчив» — на диску обидва стани однакові. Кнопка
   «Надіслати Клоду» нічого не надсилає (канал і так пише щоразу), вона
   ставить саме це поле.

   Мутації, якими знята кожна перевірка нижче:
     · прибрати `status` із `packageJSON` → перша червоніє;
     · лишити `drafted` лише в `setEdit`, не чіпаючи `clearEdit`/`setNote` →
       червоніє друга на тій гілці, яку пропустили;
     · читати `status` у `fromPackage` як `pkg.status` без звірки з 'ready' →
       червоніє четверта (побите значення стає «готовим»).
*/

test("пакет несе status, і типовий — чернетка", () => {
  const pkg = packageJSON(setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"));
  assert.equal(pkg.status, "draft");
  assert.equal(packageJSON(emptyTune()).status, "draft",
    "порожній пакет теж мусить називати свій стан, а не мовчати");
  assert.ok(pkg.instructions.some((i) => i.includes("status")),
    "читач приходить в ІНШІЙ сесії: поле, яке нічим не пояснене, — просто "
    + "слово в JSON");
});

test("«надіслати» ставить ready, а БУДЬ-ЯКА наступна зміна вертає draft", () => {
  const base = setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px");
  const ready = markReady(base);
  assert.equal(packageJSON(ready).status, "ready");

  /* Три двері, якими пакет міняється після «готово», — і кожні мусять вести
     назад у чернетку. Пакет, що каже «готово», поки дизайнер далі крутить, —
     рівно та брехня, проти якої поле й заведене. */
  assert.equal(packageJSON(setEdit(ready, "it1/holovna", IDENT, HARD_DECL, "900")).status,
    "draft", "нова правка");
  assert.equal(
    packageJSON(clearEdit(ready, "it1/holovna", "body > div.wrap > p.card", "padding-top")).status,
    "draft", "скинута правка");
  assert.equal(packageJSON(setNote(ready, "ще й ось це")).status, "draft", "нова записка");
});

test("те саме значення записки — НЕ зміна, і «готово» від неї не падає", () => {
  /* Панель шле в `setNote` значення поля, а поле віддає його й тоді, коли
     дизайнер нічого не набрав. Знімати «готово» подією, якої не було, —
     та сама неправда, лише в інший бік. */
  const ready = markReady(setNote(
    setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"), "тісно"));
  assert.equal(packageJSON(setNote(ready, "тісно")).status, "ready");
  assert.equal(setNote(ready, "тісно"), ready, "стан мусить лишитись тим самим обʼєктом");
});

test("status переживає диск — і побите значення читається як чернетка", () => {
  const ready = markReady(setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"));
  const pkg = packageJSON(ready);
  assert.deepEqual(packageJSON(fromPackage(pkg)), pkg,
    "прогін через диск загубив стан — і Клод прочитав би готове як чернетку");

  for (const bad of ["READY", "готово", 1, null, undefined, {}]) {
    assert.equal(packageJSON(fromPackage({ ...pkg, status: bad })).status, "draft",
      `${JSON.stringify(bad)} — усе, що не дослівне «ready», є чернеткою`);
  }
  /* Пакет із версії ДО T-39 поля не має зовсім — і це теж чернетка: назвати
     його готовим означало б підтвердити завершення, якого ніхто не оголошував. */
  const old = { ...pkg };
  delete old.status;
  assert.equal(packageJSON(fromPackage(old)).status, "draft");
});

test("markReady чистий: вхідний стан не чіпається", () => {
  const base = setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px");
  const ready = markReady(base);
  assert.notEqual(ready, base);
  assert.equal(packageJSON(base).status, "draft", "вхідний стан поїхав разом із виходом");
  assert.equal(markReady(ready), ready, "повторне «готово» не робить нового стану");
  assert.equal(editCount(ready), 1, "позначка готовності не сміє чіпати правок");
});

/* ── Походження ДС у пакеті (етап 2а, Task 7) ──────────────────────────────
   `ds` пакета називає, з чим звірялись вироки. Для статичного напрямку цього
   досить (`united`), а для ДС ПРОСТОРУ — ні: `space:<id>` не каже, з ЯКОГО
   файла токени, а Клод у наступній сесії читає пакет без канваса. Тому в
   пакет їде й `ds.source` — рівно для профілю простору; статична форма
   `{profile, known}` не міняється ні на байт. */

const SPACE_INFO = { profile: "space:s1", known: true, source: "tokens.css" };
const STATIC_INFO = { profile: "united", known: true, commit: "5f7050d77ab5", figma: "UI" };

test("setDs: профіль простору несе `source`, статичний напрямок — ні", () => {
  assert.deepEqual(setDs(emptyTune(), SPACE_INFO).ds,
    { profile: "space:s1", known: true, source: "tokens.css" });
  assert.deepEqual(setDs(emptyTune(), STATIC_INFO).ds, { profile: "united", known: true },
    "статична форма — рівно {profile, known}: commit/figma у пакет не їдуть");
  assert.deepEqual(setDs(emptyTune(), { profile: "seo", known: false }).ds,
    { profile: "seo", known: false });
  // `source` на статичному профілі — чужа рука: не переноситься
  assert.deepEqual(setDs(emptyTune(), { ...STATIC_INFO, source: "x.css" }).ds,
    { profile: "united", known: true });
});

test("setDs: непридатний `source` простору — порожній рядок, а не undefined і не число", () => {
  for (const source of [undefined, null, 5, {}, []]) {
    assert.deepEqual(setDs(emptyTune(), { ...SPACE_INFO, source }).ds,
      { profile: "space:s1", known: true, source: "" }, String(source));
  }
});

test("setDs: той самий об'єкт, коли нічого не змінилось; новий — коли змінився `source`", () => {
  const a = setDs(emptyTune(), SPACE_INFO);
  assert.equal(setDs(a, SPACE_INFO), a, "перезапис на кожну перемальовку панелі");
  const b = setDs(a, { ...SPACE_INFO, source: "other.css" });
  assert.notEqual(b, a, "файл токенів змінився — у пакеті мусить бути новий");
  assert.equal(b.ds.source, "other.css");
  // перехід простір → напрямок: `source` зникає
  const c = setDs(b, STATIC_INFO);
  assert.deepEqual(c.ds, { profile: "united", known: true });
  assert.equal(setDs(c, STATIC_INFO), c);
});

test("setDs не скидає готовність: ДС — факт про задачу, не правка", () => {
  const ready = markReady(setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"));
  assert.equal(packageJSON(setDs(ready, SPACE_INFO)).status, "ready");
});

test("пакет із ДС простору: packageJSON → fromPackage → packageJSON — `source` переживає диск", () => {
  const st = setDs(setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"), SPACE_INFO);
  const pkg = packageJSON(st);
  assert.deepEqual(pkg.ds, { profile: "space:s1", known: true, source: "tokens.css" });
  assert.deepEqual(packageJSON(fromPackage(pkg)), pkg,
    "прогін через диск загубив `source` — наступна сесія не знала б, з якого файла ДС");
  assert.equal(fromPackage(pkg).ds.source, "tokens.css");
});

test("пакет зі статичною ДС: форма `ds` не змінилась, і `source` із чужого пакета не підхоплюється", () => {
  const st = setDs(setEdit(emptyTune(), "it1/holovna", IDENT, TOKEN_DECL, "24px"), STATIC_INFO);
  const pkg = packageJSON(st);
  assert.deepEqual(pkg.ds, { profile: "united", known: true });
  assert.deepEqual(packageJSON(fromPackage(pkg)), pkg);
  const foreign = { ...pkg, ds: { profile: "united", known: true, source: "x.css" } };
  assert.deepEqual(fromPackage(foreign).ds, { profile: "united", known: true });
  // і порожній стан, і пакет без ДС (стара версія) — як були
  assert.deepEqual(packageJSON(emptyTune()).ds, { profile: null, known: false });
  assert.deepEqual(fromPackage({ ...pkg, ds: undefined }).ds, { profile: null, known: false });
});

test("fromPackage: профіль простору без `source` (чужа рука) — порожній рядок", () => {
  const pkg = packageJSON(setDs(emptyTune(), SPACE_INFO));
  for (const bad of [undefined, null, 7, {}]) {
    const st = fromPackage({ ...pkg, ds: { profile: "space:s1", known: true, source: bad } });
    assert.deepEqual(st.ds, { profile: "space:s1", known: true, source: "" });
  }
});

test("інструкція пакета пояснює `space:<id>` і `ds.source`", () => {
  const text = packageJSON(emptyTune()).instructions.join("\n");
  assert.match(text, /space:<id>/);
  assert.match(text, /ds\.source/);
  assert.match(text, /token file/i);
});
