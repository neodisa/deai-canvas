import assert from "node:assert/strict";
import test from "node:test";

import { panelHTML, treeBodyHTML } from "../app/shell-panel.js";

const row = (o = {}) => ({
  id: "holovna", depth: 0, isGroup: false, isState: false, hasKids: false,
  expanded: false, selected: false, name: "Головна", mark: true, ...o,
});

const S = (o = {}) => ({
  panel: "open", hasIteration: true, pagesError: "",
  /* Типове значення тут — `false`, як і в бою (`app.js`, `dc-shots-open`):
     блок кадрів починає життя ЗГОРНУТИМ. Тому кожен тест дерева нижче
     заодно перевіряє, що згорнутий блок нічого в панелі не ламає. */
  shotsOpen: false,
  rows: [row()],
  shots: { bad: false, running: false, have: 3, done: 0, total: 3, stale: 0 },
  ...o,
});

/* Секція кадрів завжди остання в розмітці панелі — беремо її від першого
   `<div class="shots`. */
function shotsBlock(h) {
  const i = h.indexOf('<div class="shots');
  assert.ok(i >= 0, "секції кадрів у розмітці немає взагалі");
  return h.slice(i);
}

/* Те, що в секції кадрів ЧИТАЄ людина: теги знято, отже все, що сидить у
   `title`, сюди не потрапляє. Саме ця різниця й міряється нижче — «причина
   лишилась однією, у підказці кнопки, а не другим рядком під нею». */
const shotsText = (h) => shotsBlock(h)
  .replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();

/* ── дерево ──────────────────────────────────────────────────────────────── */

test("кожен рядок дерева несе data-page", () => {
  const h = panelHTML(S({
    rows: [row({ id: "a" }), row({ id: "b", depth: 1, isState: true })],
  }));
  assert.match(h, /data-page="a"/);
  assert.match(h, /data-page="b"/);
});

/* Каретка — лише там, де є діти: інакше назви стрибають на ширину каретки
   залежно від того, чи в сторінки є стани. */
test("каретка є лише в рядка з дітьми, і показує напрям стрілкою", () => {
  const withKids = panelHTML(S({ rows: [row({ id: "a", hasKids: true, expanded: false })] }));
  assert.match(withKids, /data-act="toggle" data-val="a"/);
  assert.match(withKids, /aria-expanded="false"/);

  const noKids = panelHTML(S({ rows: [row({ id: "a", hasKids: false })] }));
  assert.doesNotMatch(noKids, /data-act="toggle"/);
  assert.match(noKids, /row-caret--none/);

  const open = panelHTML(S({ rows: [row({ id: "a", hasKids: true, expanded: true })] }));
  assert.match(open, /aria-expanded="true"/);
});

/* Каретка згортає ПІДСТОРІНКИ, кнопка рейки — ПАНЕЛЬ. Доки каретка позичала
   `collapsePanel`/`expandPanel`, обидві мали дослівно однакову підказку
   («Згорнути панель»), і каретка нею брехала: панель вона не торкає. Знайдено
   живим прогоном — дерево доступності показало два різні контроли з тим самим
   імʼям. Тест тримає саму РІЗНИЦЮ, а не конкретні слова: підписи можна
   переписати, збігтися вони не мають права. */
test("підказка каретки не збігається з підказкою згортання панелі", () => {
  const title = (html) => {
    const m = /class="row-caret" data-act="toggle"[^>]*?title="([^"]*)"/s.exec(html);
    assert.ok(m, "каретка без title — підказки немає взагалі");
    return m[1];
  };
  const railTitle = (html) => {
    const m = /data-act="panel" title="([^"]*)"/.exec(html);
    assert.ok(m, "кнопка згортання панелі без title");
    return m[1];
  };

  const shut = panelHTML(S({ rows: [row({ id: "a", hasKids: true, expanded: false })] }));
  const open = panelHTML(S({ rows: [row({ id: "a", hasKids: true, expanded: true })] }));

  assert.notEqual(title(shut), railTitle(shut));
  assert.notEqual(title(open), railTitle(open));
  // І сама каретка мусить казати про підсторінки, а не про щось інше.
  assert.notEqual(title(shut), title(open), "розгорнута й згорнута каретка кажуть одне й те саме");
  for (const t of [title(shut), title(open)]) {
    assert.match(t, /підсторінк/i, `підказка каретки не про підсторінки: «${t}»`);
  }
});

/* Вкладеність — класом глибини (`.row--d1`) і змінною `--d` (відступ-padding
   у CSS; B2 прибрав `margin-left` класу), не власним відступом рядка:
   контейнерний запит/тема можуть його перевизначити, а число «депту» звідки
   рахувати клас — з `state.rows`, не з рекурсії всередині цього модуля
   (дерево лишається в app.js, див. шапку файла). */
test("вкладеність рядка — класом глибини", () => {
  const h = panelHTML(S({ rows: [row({ id: "a", depth: 0 }), row({ id: "b", depth: 1 })] }));
  assert.match(h, /class="row row--d0[^"]*" style="--d:0" data-page="a"/);
  assert.match(h, /class="row row--d1[^"]*" style="--d:1" data-page="b"/);
});

/* Іконка рядка: організатор → folder, дитина ЗВИЧАЙНОЇ сторінки (стан) →
   state, усе інше → page. `isState` рахує app.js (там і батько відомий). */
test("іконка рядка залежить від isGroup/isState", () => {
  const group = panelHTML(S({ rows: [row({ id: "g", isGroup: true })] }));
  assert.match(group, /#i-folder/);
  const state = panelHTML(S({ rows: [row({ id: "s", depth: 1, isState: true })] }));
  assert.match(state, /#i-state/);
  const plain = panelHTML(S({ rows: [row({ id: "p" })] }));
  assert.match(plain, /#i-page/);
});

/* «⋯» — дії над сторінкою живуть ПРИ сторінці, не лише в контекстному меню
   правим кліком (спека Task 4, п.1): дія, досяжна тільки правим кліком,
   недосяжна з клавіатури. */
test('кожен рядок несе «⋯» з data-act="pagemenu" і своїм data-val', () => {
  const h = panelHTML(S({ rows: [row({ id: "abc" })] }));
  assert.match(h, /data-act="pagemenu" data-val="abc"/);
});

/* Позначка «у превью» — лише коли мала бути (мітка з даних, не завжди). */
test("позначка «у превью» малюється лише коли mark:true", () => {
  const on = panelHTML(S({ rows: [row({ id: "a", mark: true })] }));
  assert.match(on, /dot dot--ok row-mark/);
  const off = panelHTML(S({ rows: [row({ id: "a", mark: false })] }));
  assert.doesNotMatch(off, /row-mark/);
});

/* Назви сторінок ідуть із pages.json, який правлять руками. */
test("назва сторінки екранується", () => {
  const h = panelHTML(S({ rows: [row({ id: "a", name: '<img src=x onerror="alert(1)">' })] }));
  assert.ok(!h.includes("<img src=x"), "розмітка з даних доїхала неекранованою");
  assert.match(h, /&lt;img/);
});

/* ── секція «Кадри» ──────────────────────────────────────────────────────── */

/* Чотири стани зі спеки Task 4 + два додаткові (усе свіже — і в прототипі
   демонстративне «shotsFresh»; свіжість НЕВІДОМА — якого прототип не знає,
   бо демо завжди має точні числа, а `checkOf()` у бою — ні: перший вхід у
   «Огляд» для цієї ітерації ще не бігав). Змішати «невідомо» з «усе свіже»
   означало б збрехати рівно там, де `freshen()` (app.js) явно рятує від
   цього кнопку «Перезняти». */
test("кадрів немає — стан і підпис кнопки", () => {
  const h = panelHTML(S({ shots: { bad: false, running: false, have: 0, done: 0, total: 5, stale: null } }));
  assert.match(h, /кадрів ще немає/);
  assert.match(h, /Зняти кадри \(5\)/);
});

test("N треба перезняти — стан і підпис кнопки несуть обидва числа", () => {
  const h = panelHTML(S({ shots: { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 } }));
  assert.match(h, /3 з 12 треба перезняти/);
  assert.match(h, /Оновити кадри \(3\)/);
});

test("знімаю N з M — стан під час прогону, з прогрес-баром", () => {
  const h = panelHTML(S({ shots: { bad: false, running: true, have: 8, done: 4, total: 12, stale: 3 } }));
  assert.match(h, /знімаю 4 з 12/);
  assert.match(h, /class="prog"/);
  assert.match(h, /width:33%/);
});

test("манифест не читається — стан гучний, а не мовчазний", () => {
  const h = panelHTML(S({ shots: { bad: true, running: false, have: 8, done: 0, total: null, stale: null } }));
  assert.match(h, /манифест кадрів не читається/);
  assert.match(h, /shots-s--bad/);
});

/* ── тихий стан: усе свіже ───────────────────────────────────────────────
   Виміряно 02.09.2026 у живому браузері: при повній свіжості блок казав одне
   й те саме ЧОТИРИ рази — заголовок «Кадри для огляду», рядок «22 кадрів,
   усі свіжі», ВИМКНЕНА кнопка «Оновити кадри (0)» і рядок «нічого не
   застаріло». Тест тримає не наявність класу, а саму КІЛЬКІСТЬ сказаного:
   `shotsText()` знімає теги, тож у ньому лишається рівно те, що читає
   людина. */
test("усе свіже й блок згорнутий — один тихий рядок, без кнопки й без «(0)»", () => {
  const h = panelHTML(S({
    shots: { bad: false, running: false, have: 22, done: 0, total: 22, stale: 0 },
  }));
  assert.equal(shotsText(h), "Кадри · 22 свіжі");
  assert.match(h, /data-act="shotsopen"/, "тихий рядок нічим не розгорнути");
  assert.doesNotMatch(shotsBlock(h), /data-act="shoot"/);
  assert.doesNotMatch(h, /disabled/);
  assert.doesNotMatch(h, /\(0\)/);
});

test("тихий рядок розгортається — керування зʼємкою вертається повністю", () => {
  const h = panelHTML(S({
    shotsOpen: true,
    shots: { bad: false, running: false, have: 12, done: 0, total: 12, stale: 0 },
  }));
  assert.match(h, /12 кадрів, усі свіжі/);
  assert.match(h, /data-act="shoot"/);
  assert.match(h, /disabled/, "застарілого нема — кнопці нема чого робити");
  assert.match(h, /Оновити кадри<\/span>/, "число «(0)» ні про що — підпис без нього");
  assert.doesNotMatch(h, /\(0\)/);
  /* Причина лишається ОДНІЄЮ: у підказці кнопки, не другим рядком під нею. */
  assert.doesNotMatch(shotsText(h), /нічого не застаріло/,
    "причина сказана двічі — рядком і підказкою");
  assert.match(h, /title="[^"]*нічого не застаріло/, "причина зникла зовсім");
});

/* Дорога назад. Тихий рядок відкриває блок — а закрити його мусить бути чим:
   інакше «опціонально» (слова власника) означало б «один раз і назавжди».
   Заголовок стає контролом РІВНО тоді, коли згортати дозволено; у гучних
   станах він лишається текстом, бо кнопка, яка на клік нічого не згорне,
   брехала б про свою дію. */
test("розгорнутий свіжий блок згортається назад — заголовок є контролом", () => {
  const h = panelHTML(S({
    shotsOpen: true,
    shots: { bad: false, running: false, have: 12, done: 0, total: 12, stale: 0 },
  }));
  assert.match(h, /<button class="shots-h shots-h--btn" data-act="shotsopen"/);
});

test("у гучних станах заголовок блоку НЕ контрол — згортати однаково не дадуть", () => {
  const loud = [
    { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 },
    { bad: false, running: true, have: 8, done: 4, total: 12, stale: null },
    { bad: true, running: false, have: 8, done: 0, total: null, stale: null },
    { bad: false, running: false, have: 0, done: 0, total: 5, stale: null },
    { bad: false, running: false, have: 5, done: 0, total: null, stale: null },
  ];
  for (const shots of loud) {
    for (const shotsOpen of [false, true]) {
      const h = panelHTML(S({ shotsOpen, shots }));
      assert.doesNotMatch(h, /data-act="shotsopen"/,
        `заголовок обіцяє згорнути те, що згортатись не має права: ${JSON.stringify(shots)}`);
    }
  }
});

/* ── несучий інваріант: згорнутий блок не ховає проблему ─────────────────
   Три перевірки нижче важливіші за саму фічу. Збережений вибір «згорнуто» не
   сміє перемогти застаріле, прогін зʼємки чи побитий манифест: інакше
   тихий блок ховає саме те, про що мусить кричати. Випадок `running` уже
   коштував нам «Стопа» один раз (План B, знайдено падінням живих A/B/E/F в
   `autoshoot.test.mjs`) — там кнопку прибирав збій переліку сторінок, тут її
   прибрав би збережений вибір. Той самий клас втрати, інша причина. */
test("застаріле розгортає блок навіть при shotsOpen:false", () => {
  const h = panelHTML(S({
    shots: { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 },
  }));
  assert.match(h, /data-act="shoot"/, "згорнутий блок сховав застарілі кадри");
  assert.match(h, /3 з 12 треба перезняти/);
});

test("прогін зʼємки розгортає блок навіть при shotsOpen:false — «Стоп» видимий", () => {
  const h = panelHTML(S({
    shots: { bad: false, running: true, have: 8, done: 4, total: 12, stale: null },
  }));
  assert.match(h, /data-act="shoot"/, "прогін нічим спинити — кнопку сховав тихий стан");
  assert.match(shotsText(h), /Стоп 4\/12/, "лічильник «Стоп N/M» зник разом із блоком");
});

test("збій манифеста розгортає блок навіть при shotsOpen:false", () => {
  const h = panelHTML(S({
    shots: { bad: true, running: false, have: 8, done: 0, total: null, stale: null },
  }));
  assert.match(h, /shots-s--bad/, "згорнутий блок сховав збій манифеста");
  assert.match(h, /data-act="shoot"/);
});

/* «(0)» — не стан, а артефакт підстановки нуля в шаблон із числом. Тест
   окремий і по ВСІХ станах ×  обох станах згорнутості: місце, де нуль знову
   доїде до підпису, наперед невідоме. */
test("«(0)» не малюється ні в одному стані", () => {
  const states = [
    { bad: false, running: false, have: 22, done: 0, total: 22, stale: 0 },
    { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 },
    { bad: false, running: false, have: 0, done: 0, total: 5, stale: null },
    { bad: false, running: false, have: 0, done: 0, total: 0, stale: null },
    { bad: false, running: false, have: 5, done: 0, total: null, stale: null },
    { bad: false, running: true, have: 0, done: 0, total: 12, stale: null },
    { bad: false, running: true, have: 8, done: 4, total: 12, stale: 3 },
    { bad: true, running: false, have: 8, done: 0, total: null, stale: null },
  ];
  for (const shots of states) {
    for (const shotsOpen of [false, true]) {
      const h = panelHTML(S({ shotsOpen, shots }));
      assert.doesNotMatch(h, /\(0\)/,
        `«(0)» доїхало до розмітки: ${JSON.stringify({ shotsOpen, shots })}`);
    }
  }
});

test("свіжість ще не перевірялась — не бреше «усе свіже», кнопка лишається живою", () => {
  const h = panelHTML(S({ shots: { bad: false, running: false, have: 5, done: 0, total: null, stale: null } }));
  assert.doesNotMatch(h, /усі свіжі/);
  assert.match(h, /свіжість ще не перевірялась/);
  assert.doesNotMatch(h, /disabled/, "невідома свіжість не сміє глушити кнопку — не підтверджено, що нічого робити не треба");
  assert.match(h, /Оновити кадри<\/span>/, "без числа — бо число невідоме, а не нуль");
});

/* ── порожнє місце панелі — теж контрол ──────────────────────────────────
   Слова власника: «еще бы хотелось бы, чтобы эта левая панель закрывалась по
   пустому месту. И открывалась тоже на любое место нажав, чтобы удобнее было
   с ней работать».

   Несуча ідея рішення — НЕ слухач на тлі панелі, а те, що делегація
   (`wirePanelEvents`, `app.js`) бере НАЙБЛИЖЧИЙ предок із дією:
   `ev.target.closest('[data-act]')`. Тому «порожнє місце» — це власний
   елемент із `data-act="panel"`, а кожен контрол над ним екранує себе САМ,
   своєю ж дією, задарма й без жодного переліку винятків.

   Що юніт тут МОЖЕ, а чого не може: рядок HTML не має `closest()`, тож
   механіку «клік по контролу не доходить до панелі» доводить живий тест
   (`tests/live/panel-click.test.mjs`) — і доводить її МУТАЦІЄЮ: прибери
   `data-act` із «⋯», і клік по ньому знайде вже не своє меню, а дію
   найближчого предка. Юніти нижче тримають те, що видно в рядку: САМ
   заповнювач, його місце в розмітці й те, що кожен контрол має власну дію. */

test("порожнє місце під деревом несе дію «панель» і стоїть ПІСЛЯ рядків", () => {
  const h = panelHTML(S({ rows: [row({ id: "a" }), row({ id: "b" })] }));
  assert.match(h, /<div class="panel-fill" data-act="panel"/,
    "порожнє місце панелі нічого не робить на клік");
  assert.ok(h.indexOf('data-page="b"') < h.indexOf('class="panel-fill"'),
    "заповнювач стоїть ПЕРЕД рядками — тоді він накриє дерево, а не порожнє місце");
});

/* Три речі однією перевіркою, бо всі три — про МІСЦЕ, і всі три ламаються
   разом:
   1. заповнювач — ОСТАННЯ дитина `.panel-body`, тобто того самого
      скрольованого блоку, у якому й лежить порожнє місце під деревом. Стій
      він СУСІДОМ до `.panel-body`, порожнє місце всередині тіла лишилось би
      мертвим (`.panel-body{flex:1}` забирає всю висоту), а клік по ньому —
      без дії;
   2. заповнювач ПОРОЖНІЙ — рядки дерева не сміють опинитись усередині нього:
      клік по рядку тоді знайшов би свою ж дію (`page`), але сам заповнювач
      перестав би бути «порожнім місцем» і згортав би панель із-під дерева;
   3. блок «Кадри» іде ПІСЛЯ заповнювача — інакше він поїде вгору й
      відліпиться від низу панелі, бо саме заповнювач тепер їсть вільну
      висоту. */
test("заповнювач — остання й порожня дитина тіла, блок кадрів іде ПІСЛЯ нього", () => {
  const h = panelHTML(S());
  assert.match(h, /<div class="panel-fill" data-act="panel"[^>]*><\/div>\s*<\/div>\s*<div class="shots/,
    "порядок «рядки → заповнювач → кінець тіла → кадри» зламано");
});

/* Рейка — одна велика кнопка (46px завширшки): у власника «открывалась тоже
   на любое место нажав». Корінь рейки, який малює цей модуль, — обгортка
   `.panel-rail`: справжній корінь панелі (`#pages-panel`) створює `app.js`, і
   вішати дію на нього означало б проводити ту саму фічу у двох файлах.
   Три контроли рейки лишаються при своїх діях (тест нижче) — обгортка їх не
   з'їдає рівно з тієї ж причини, що заповнювач не з'їдає дерево. */
test("рейка — одна велика кнопка: її корінь несе дію «панель»", () => {
  const h = panelHTML(S({ panel: "rail" }));
  assert.match(h, /^\s*<div class="panel-rail" data-act="panel"/,
    "у рейці клікає лише сама стрілка, а не будь-яке місце");
  // Обгортка мусить закритись, а не лишити рейку відкритим тегом.
  assert.match(h, /<\/div>\s*$/);
});

/* Перелік екранів. Кожен контрол панелі, який НЕ мусить згортати її, має
   ВЛАСНИЙ `data-act` — і саме тому `closest('[data-act]')` від нього
   зупиниться на ньому, не дійшовши ні до заповнювача, ні до кореня рейки.
   Тест тримає ПЕРЕЛІК іменами дій: новий контрол без своєї дії стане
   кнопкою, що згортає панель замість своєї роботи, і цей список — єдине
   місце, де це видно до живого прогону. */
test("кожен контрол панелі екранує себе власною дією", () => {
  const loud = panelHTML(S({
    rows: [row({ id: "a", hasKids: true, expanded: true }), row({ id: "b", depth: 1 })],
    shots: { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 },
  }));
  for (const act of ["page", "toggle", "pagemenu", "newfolder", "shoot"]) {
    assert.match(loud, new RegExp(`data-act="${act}"`),
      `контрол «${act}» лишився без власної дії — клік по ньому дійде до панелі`);
  }
  // Тихий рядок кадрів існує лише у своєму стані — тому окремим викликом.
  assert.match(panelHTML(S()), /data-act="shotsopen"/,
    "тихий рядок кадрів без власної дії згортав би панель замість блоку");
});

/* ── рейка ───────────────────────────────────────────────────────────────── */

/* panel==='rail' не сміє втратити жоден із трьох контролів: вхід назад,
   додавання сторінки, зʼємку. Тихий стан блоку кадрів рейки НЕ стосується —
   там і так один значок, ховати в ньому нічого; цей тест і є той охоронець:
   стан у ньому типовий (усе свіже, `shotsOpen:false`), тобто рівно той, у
   якому відкрита панель мовчить, а `data-act="shoot"` тут вимагається. */
test("рейка лишає вхід назад і зʼємку; «＋» на рейці немає (сторінки створює Claude)", () => {
  const h = panelHTML(S({ panel: "rail" }));
  assert.match(h, /data-act="panel"/, "нема входу назад");
  assert.doesNotMatch(h, /data-act="newpage"|data-act="newfolder"/, "на рейці лишився «＋»");
  assert.match(h, /data-act="shoot"/, "нема зʼємки");
});

test("рейка без ітерації не показує зʼємку — нічого не знімати", () => {
  const h = panelHTML(S({ panel: "rail", hasIteration: false, shots: null }));
  assert.match(h, /data-act="panel"/);
  assert.doesNotMatch(h, /data-act="shoot"/);
});

/* ── порожні стани: жоден не мовчить ────────────────────────────────────── */

test("немає ітерації — дерева немає, а панель каже, чого чекати", () => {
  const h = panelHTML(S({ hasIteration: false, rows: [], shots: null }));
  assert.doesNotMatch(h, /class="row /);
  assert.match(h, /Сторінки з.явля/);
});

test("дерево порожнє (є ітерація, сторінок 0) — теж не мовчить", () => {
  const h = panelHTML(S({ rows: [] }));
  assert.match(h, /дерево шарів порожнє/);
});

test("перелік сторінок не завантажився — помилка замість дерева й кадрів", () => {
  const h = panelHTML(S({ pagesError: "500" }));
  assert.match(h, /shots-s--bad/);
  assert.match(h, />500</);
  assert.doesNotMatch(h, /class="row /);
  assert.doesNotMatch(h, /class="shots"/, "кадри без валідного переліку сторінок — недостовірні, ховаємо разом з деревом");
});

/* Друга половина того самого правила, і вона з живого бага. Ховати лічильник
   на `pagesError` правильно — він рахується по сторінках. Але під час
   ПРОГОНУ кнопка каже «Стоп N/M» з прогресу зʼємки, а не з переліку, і
   ховати її означає лишити користувача з прогоном, який нічим спинити.
   Панель перемальовується щотакту (700мс), тож транзиєнтний збій переліку
   забирав «Стоп» посеред роботи — падіння живих A/B/E/F в `autoshoot`. */
test("під час зʼємки «Стоп» лишається навіть при збої переліку сторінок", () => {
  const h = panelHTML(S({
    pagesError: "сторінки не завантажились: Failed to fetch",
    shots: { running: true, done: 4, total: 12, have: 4, stale: 0 },
  }));
  assert.match(h, /data-act="shoot"/,
    "кнопку зʼємки прибрано посеред прогону — спинити його нічим");
});

/* ── readonly: та сама панель у статичному превʼю ────────────────────────
   Опубліковане превʼю (План B) — статика: ні сервера, ні зʼємки, ні
   перейменування. Панель там потрібна лише як НАВІГАЦІЯ по дереву сторінок,
   тому `state.readonly` прибирає рівно дії над даними й не торкає ні рядка
   розмітки дерева.

   Прапорець, а не другий модуль — і саме це тримають тести нижче ПАРАМИ
   («прибирає» / «лишає»). Розмітка рядків, каретки, глибина, іконки,
   позначка «у превью» й екранування назв — те саме в обох світах; другий
   модуль розійшовся б із першим на першій же правці дерева, і розходження
   було б видно не в тесті, а в чужому браузері за посиланням. */

test("readonly прибирає ВСІ дії над даними: «⋯», «+» і зʼємку", () => {
  const h = panelHTML(S({
    readonly: true,
    rows: [row({ id: "a", hasKids: true, expanded: true }), row({ id: "b", depth: 1 })],
  }));
  for (const act of ["pagemenu", "newfolder", "shoot", "shotsopen"]) {
    assert.doesNotMatch(h, new RegExp(`data-act="${act}"`),
      `у статичному превʼю дія «${act}» нікуди не веде, а кнопка є`);
  }
});

/* Не лише кнопка — ВЕСЬ блок. Заголовок «Кадри для огляду», рядок стану,
   прогрес і тихий рядок у статиці однаково брешуть: зʼємки там не існує, тож
   будь-який із цих станів розповідав би глядачеві про механізм, якого в його
   світі немає. Перевіряємо по всіх станах кадрів — місце, де блок знову
   протече в розмітку, наперед невідоме. */
test("readonly не малює блок кадрів ні в одному його стані", () => {
  const states = [
    { bad: false, running: false, have: 22, done: 0, total: 22, stale: 0 },
    { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 },
    { bad: false, running: false, have: 0, done: 0, total: 5, stale: null },
    { bad: false, running: false, have: 5, done: 0, total: null, stale: null },
    { bad: false, running: true, have: 8, done: 4, total: 12, stale: 3 },
    { bad: true, running: false, have: 8, done: 0, total: null, stale: null },
  ];
  for (const shots of states) {
    for (const shotsOpen of [false, true]) {
      for (const panel of ["open", "rail"]) {
        const h = panelHTML(S({ readonly: true, panel, shotsOpen, shots }));
        assert.doesNotMatch(h, /class="shots/,
          `блок кадрів доїхав у статику: ${JSON.stringify({ panel, shotsOpen, shots })}`);
        assert.ok(!h.includes("Кадри"),
          `текст блоку кадрів доїхав у статику: ${JSON.stringify({ panel, shotsOpen, shots })}`);
        assert.doesNotMatch(h, /class="prog"/,
          `прогрес зʼємки доїхав у статику: ${JSON.stringify({ panel, shotsOpen, shots })}`);
      }
    }
  }
});

/* Половина задачі — саме цей перелік. Він фіксує те, що НЕ сміє розійтись
   між інструментом і превʼю: дерево з глибиною, вибір рядка, каретка з
   `aria-expanded`, три іконки, позначка «у превью». Перелічено явно й
   поіменно, а не «дерево на місці»: розходження в одному класі глибини не
   впаде ніде, крім чужого браузера. */
test("readonly лишає дерево цілим: глибина, вибір, каретка, іконки, позначка", () => {
  const h = panelHTML(S({
    readonly: true,
    rows: [
      row({ id: "g", isGroup: true, hasKids: true, expanded: true, mark: false }),
      row({ id: "s", depth: 1, isState: true, selected: true }),
      row({ id: "p", depth: 2, hasKids: false }),
    ],
  }));
  // Ідентичність рядка й вибір сторінки — те, за що тримається навігація.
  assert.match(h, /class="row row--d0[^"]*" style="--d:0" data-page="g"/);
  assert.match(h, /class="row row--d1 row--sel" style="--d:1" data-page="s"/);
  assert.match(h, /class="row row--d2[^"]*" style="--d:2" data-page="p"/);
  assert.match(h, /data-act="page" data-val="g"/);
  assert.match(h, /data-act="page" data-val="s"/);
  assert.match(h, /data-act="page" data-val="p"/);
  // Каретка підсторінок — навігація, не дія над даними.
  assert.match(h, /data-act="toggle" data-val="g"/);
  // aria-expanded (як і решта дерева ARIA) у статиці прибрано свідомо — див. тест нижче
  assert.match(h, /row-caret--none/, "рядок без дітей втратив порожню каретку — назви поїдуть");
  // Три іконки: організатор, стан, звичайна сторінка.
  assert.match(h, /#i-folder/);
  assert.match(h, /#i-state/);
  assert.match(h, /#i-page/);
  // Позначка «у превью» — лише де мала бути, як і в інструменті.
  assert.match(h, /dot dot--ok row-mark/);
  assert.equal(h.match(/row-mark/g).length, 2, "позначка не там, де mark:true");
});

/* Назви сторінок пише дизайнер у `pages.json` — недовірені дані, і в статиці
   вони ще й їдуть на чужу машину за посиланням, де жодного нашого коду вже
   немає. Екранування — та сама функція для обох світів, і тест на неї
   дублюється свідомо: він мусить упасти в readonly, навіть якщо хтось
   «оптимізує» саме цю гілку. */
test("readonly екранує назви сторінок так само, як інструмент", () => {
  const bad = '<img src=x onerror="alert(1)">';
  const h = panelHTML(S({ readonly: true, rows: [row({ id: "a", name: bad })] }));
  assert.ok(!h.includes("<img src=x"), "розмітка з даних доїхала неекранованою");
  assert.match(h, /&lt;img/);
  // І дослівно те саме, що дає інструмент для тієї ж назви.
  const tool = panelHTML(S({ rows: [row({ id: "a", name: bad })] }));
  const nameOf = (s) => /<span class="row-name">([^<]*)<\/span>/.exec(s)[1];
  assert.equal(nameOf(h), nameOf(tool), "екранування розійшлось між двома світами");
});

/* Згортання панелі — не дія над даними, а робота з місцем на екрані: у
   превʼю рамка так само тісна, як в інструменті. Тому в readonly лишаються
   всі три входи — стрілка в шапці, порожнє місце під деревом і сама рейка. */
test("readonly лишає згортання панелі: стрілка, заповнювач і рейка", () => {
  const open = panelHTML(S({ readonly: true }));
  assert.match(open, /<button class="icob" data-act="panel"/, "нема стрілки згортання");
  assert.match(open, /<div class="panel-fill" data-act="panel"/, "нема заповнювача");

  const rail = panelHTML(S({ readonly: true, panel: "rail" }));
  assert.match(rail, /^\s*<div class="panel-rail" data-act="panel"/,
    "рейка перестала бути однією великою кнопкою");
  assert.match(rail, /<\/div>\s*$/, "рейка лишилась відкритим тегом");
});

/* Рейка в статиці — рівно ОДИН контрол. Тест парний до «рейка лишає вхід
   назад, додавання сторінки й зʼємку»: там три дії вимагаються, тут двох із
   них не сміє бути. */
test("readonly у рейці лишає лише вхід назад", () => {
  const h = panelHTML(S({ readonly: true, panel: "rail" }));
  assert.match(h, /data-act="panel"/);
  assert.doesNotMatch(h, /data-act="newpage"/);
  assert.doesNotMatch(h, /data-act="shoot"/);
});

/* Порожні стани в статиці однаково не мовчать: маніфест може приїхати з
   ітерацією без сторінок, і глядач мусить прочитати чому, а не дивитись у
   порожню панель. */
test("readonly з порожнім деревом не мовчить", () => {
  assert.match(panelHTML(S({ readonly: true, rows: [] })), /дерево шарів порожнє/);
  assert.match(panelHTML(S({ readonly: true, hasIteration: false, rows: [], shots: null })),
    /Сторінки з.явля/);
});

/* Несуче: панель у самому інструменті не сміє змінитись ні на байт. `false`
   і відсутній прапорець — дослівно те саме, що було до `readonly`; решту
   доводять 342 наявних юніти, які цей файл уже ганяє по кожному стану. */
test("readonly відсутній або false — панель дослівно та сама", () => {
  const cases = [
    {},
    { rows: [row({ id: "a", hasKids: true, expanded: true }), row({ id: "b", depth: 1 })] },
    { panel: "rail" },
    { shotsOpen: true },
    { shots: { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 } },
    { shots: { bad: false, running: true, have: 8, done: 4, total: 12, stale: null } },
    { shots: { bad: true, running: false, have: 8, done: 0, total: null, stale: null } },
    { pagesError: "500" },
    { hasIteration: false, rows: [], shots: null },
  ];
  for (const c of cases) {
    assert.equal(panelHTML(S({ ...c, readonly: false })), panelHTML(S(c)),
      `readonly:false змінив панель інструмента: ${JSON.stringify(c)}`);
    assert.equal(panelHTML(S({ ...c, readonly: undefined })), panelHTML(S(c)),
      `readonly:undefined змінив панель інструмента: ${JSON.stringify(c)}`);
  }
});

/* ── тривога кадрів лише там, де свіжість міряють (fb-22092026-c74093) ──────
   «Помаранчеве "Оновити кадри" висить постійно — показувати лише в "Огляді"».
   У «Макеті» `freshen()` не бігає, тож тривога там була про невиміряне.
   МУТАЦІЯ: `warn = !fresh` (без режиму) — червоніє перша перевірка;
   МУТАЦІЯ: прибрати `s.bad ||` — червоніє друга (збій мовчить у «Макеті»). */
test("у «Макеті» блок кадрів тихий: без помаранчевого, але вхід у зʼємку живий", () => {
  const cases = [
    { bad: false, running: false, have: 5, done: 0, total: null, stale: null },
    { bad: false, running: false, have: 8, done: 0, total: 12, stale: 3 },
    { bad: false, running: false, have: 0, done: 0, total: 5, stale: null },
  ];
  for (const shots of cases) {
    const h = panelHTML(S({ shots: { ...shots, overview: false } }));
    assert.doesNotMatch(h, /ctl--warn|shots-s--warn/,
      `у «Макеті» тривога про невиміряне: ${JSON.stringify(shots)}`);
    assert.match(h, /data-act="shoot"/, "з «Макета» зник вхід у зʼємку");
    // Свідок: у «Огляді» ТОЙ САМИЙ стан лишається гучним.
    assert.match(panelHTML(S({ shots: { ...shots, overview: true } })), /ctl--warn/,
      `у «Огляді» тривога зникла теж: ${JSON.stringify(shots)}`);
  }
});

test("побитий манифест кричить і в «Макеті» — це збій, а не свіжість", () => {
  const h = panelHTML(S({ shots: { bad: true, running: false, have: 8, done: 0,
    total: null, stale: null, overview: false } }));
  assert.match(h, /shots-s--bad/);
  assert.match(h, /ctl--warn/, "збій манифеста в «Макеті» перестав бути тривогою");
});

/* ── B2: будь-яка глибина, «＋ тека», крихти, фільтр ─────────────────────── */

const deepRow = (over = {}) => ({ id: "x", depth: 9, kind: "state", isGroup: false, isState: true,
  hasKids: false, expanded: false, selected: false, multi: false, name: "Стан на дні",
  mark: true, count: "", ...over });

test("глибокий рядок: відступ обмежений 7 рівнями, далі бейдж рівня", () => {
  const html = panelHTML(S({ rows: [deepRow()] }));
  assert.match(html, /style="--d:7"/);
  assert.match(html, /class="row-deep"[^>]*>10</);
});

/* Іконка шукається ВСЕРЕДИНІ розмітки рядка: шапка дерева теж має #i-folder
   («＋ тека»), тож пошук по всій панелі проходив би й без іконки в рядку. */
const rowMarkup = (html) => html.slice(html.indexOf('<div class="row '), html.indexOf('<span class="row-name">'));

test("іконку рядка дає kind; без kind — запасний вихід за прапорцями", () => {
  const icon = (o) => rowMarkup(panelHTML(S({ rows: [deepRow({ depth: 0, ...o })] })));
  assert.match(icon({ kind: "folder", isGroup: true, isState: false }), /data-kind="folder"[\s\S]*?#i-folder/);
  assert.match(icon({ kind: "state" }), /data-kind="state"[\s\S]*?#i-state/);
  assert.match(icon({ kind: "page", isState: false }), /data-kind="page"[\s\S]*?#i-page/);
  assert.match(icon({ kind: undefined, isGroup: true, isState: false }), /data-kind="folder"[\s\S]*?#i-folder/);
  assert.match(icon({ kind: undefined, isState: true }), /data-kind="state"[\s\S]*?#i-state/);
  assert.match(icon({ kind: undefined, isState: false }), /data-kind="page"[\s\S]*?#i-page/);
});

test("kind з чужого JSON не потрапляє в розмітку: білий список + екранування", () => {
  const h = panelHTML(S({ rows: [deepRow({ kind: '"><img onerror=1>' })] }));
  assert.doesNotMatch(h, /<img/);
  assert.match(h, /data-kind="page"/);
});

test("згорнутий контейнер показує лічильник, повний текст — у title", () => {
  const html = panelHTML(S({ rows: [deepRow({ depth: 0, kind: "page", hasKids: true,
    count: "3 стор · 12 ст", countTitle: "Сторінок: 3 & станів: 12" })] }));
  assert.match(html, /class="row-cnt" title="Сторінок: 3 &amp; станів: 12">3 стор · 12 ст</);
});

test("множинний вибір позначений класом, рядки більше НЕ draggable (свій pointer-драг)", () => {
  const html = panelHTML(S({ rows: [deepRow({ multi: true })] }));
  assert.match(html, /row--multi/);
  assert.doesNotMatch(html, /draggable=/);
});

test("у шапці дерева — «＋ тека», не «нова сторінка»; на рейці «＋» немає", () => {
  const open = panelHTML(S());
  assert.match(open, /data-act="newfolder"/);
  assert.doesNotMatch(open, /data-act="newpage"/);
  const rail = panelHTML(S({ panel: "rail" }));
  assert.doesNotMatch(rail, /data-act="newpage"|data-act="newfolder"/);
});

test("фільтр і крихти; у фокусі — вихід «Усі шари»", () => {
  const html = panelHTML(S({ filter: "сан", crumbs: [{ id: "p", name: "Картка" }, { id: "w", name: "Віджет" }],
    focus: { id: "w", name: "Віджет" } }));
  assert.match(html, /id="pp-filter"[^>]*value="сан"/);
  assert.match(html, /data-act="unfocus"/);
  assert.match(html, /Віджет/);
});

test("довгий шлях крихт стискається: перший › … › два останні", () => {
  const crumbs = ["A", "B", "C", "D", "E"].map((n) => ({ id: n, name: n }));
  const html = panelHTML(S({ crumbs }));
  assert.match(html, />A<[\s\S]*>…<[\s\S]*>D<[\s\S]*>E</);
  assert.doesNotMatch(html, />B</);
});

test("фільтр без збігів каже «нічого не знайдено», а не «порожнє дерево»", () => {
  const html = panelHTML(S({ filter: "zzz", rows: [] }));
  assert.match(html, /Нічого не знайдено/);
  assert.doesNotMatch(html, /data-act="unfocus"/);
});

test("readonly: ні «＋ тека», ні ⋯ — як і раніше", () => {
  const html = panelHTML(S({ readonly: true, rows: [deepRow()] }));
  assert.doesNotMatch(html, /data-act="newfolder"|data-act="pagemenu"/);
});

/* ── B2, ревʼю ───────────────────────────────────────────────────────────── */

test("межа бейджа: рівень 7 — без бейджа, рівень 8 — бейдж «9»", () => {
  const h7 = panelHTML(S({ rows: [deepRow({ depth: 7 })] }));
  assert.match(h7, /style="--d:7"/);
  assert.doesNotMatch(h7, /row-deep/);
  const h8 = panelHTML(S({ rows: [deepRow({ depth: 8 })] }));
  assert.match(h8, /style="--d:7"/);
  assert.match(h8, /class="row-deep"[^>]*>9</);
});

test("екранування: назва, крихта, countTitle, значення фільтра", () => {
  const evil = '"><b>x</b>';
  const h = panelHTML(S({
    filter: evil, crumbs: [{ id: "a", name: evil }, { id: "b", name: "ok" }],
    rows: [deepRow({ name: evil, count: "1", countTitle: evil })],
  }));
  assert.doesNotMatch(h, /<b>x<\/b>/);
  assert.match(h, /value="&quot;&gt;&lt;b&gt;x/);
});

test("readonly: фільтра немає (його нікому обробити)", () => {
  assert.doesNotMatch(panelHTML(S({ readonly: true })), /pp-filter/);
  assert.match(panelHTML(S()), /pp-filter/);
});

test("фільтр має доступне імʼя", () => {
  assert.match(panelHTML(S()), /id="pp-filter"[^>]*aria-label="Фільтр: назва…"/);
});

test("крихти: хвіст «…» і список у фокусі", () => {
  const crumbs = ["A", "B", "C", "D", "E"].map((n) => ({ id: n, name: n }));
  const h = panelHTML(S({ crumbs, focus: { id: "E", name: "E" } }));
  assert.match(h, /data-act="unfocus"[\s\S]*?>A<[\s\S]*?>…<[\s\S]*?>D<[\s\S]*?>E</);
  assert.doesNotMatch(h, />B<|>C</);
  // корінь без фокуса — крихти нічого не додають
  assert.doesNotMatch(panelHTML(S({ crumbs: [{ id: "A", name: "A" }] })), /tree-crumbs/);
});

test("row--multi разом із row--sel", () => {
  const h = panelHTML(S({ rows: [deepRow({ multi: true, selected: true })] }));
  assert.match(h, /class="row row--d9 row--sel row--multi"/);
});

test("нова тека має власну іконку folderplus", () => {
  assert.match(panelHTML(S()), /data-act="newfolder"[^>]*>[\s\S]*?#i-folderplus/);
});

test("доступність дерева: tree / treeitem, рівень, вибір, розгорнутість", () => {
  const h = panelHTML(S({ rows: [
    row({ id: "a", depth: 2, hasKids: true, expanded: true, selected: true }),
    row({ id: "b", depth: 0, multi: true }),
    row({ id: "c", depth: 0 }),
  ] }));
  assert.match(h, /role="tree"/);
  assert.match(h, /role="treeitem" aria-level="3" aria-selected="true" aria-expanded="true"[^>]*data-page="a"|data-page="a"[^>]*role="treeitem"/);
  const rowOf = (id) => new RegExp(`<div class="row [^>]*data-page="${id}"[^>]*>`).exec(h)[0];
  assert.match(rowOf("a"), /aria-level="3"/);
  assert.match(rowOf("a"), /aria-selected="true"/);
  assert.match(rowOf("a"), /aria-expanded="true"/);
  assert.match(rowOf("b"), /aria-selected="true"/);
  assert.match(rowOf("c"), /aria-selected="false"/);
  assert.doesNotMatch(rowOf("c"), /aria-expanded/);
});

/* ── B3: фільтр поза перемальовуваною частиною + клавіатура дерева ── */

test("treeBodyHTML: це рівно те, що лежить у .tree-body відкритої панелі, а фільтра в ньому нема", () => {
  const st = S({
    filter: "ос", focus: { id: "a", name: "A" }, crumbs: [{ id: "a", name: "A" }],
    rows: [row({ id: "a" }), row({ id: "b" })],
  });
  const inner = treeBodyHTML(st);
  assert.ok(panelHTML(st).includes(`<div class="tree-body">${inner}</div>`),
    "панель мусить збирати тіло дерева з того ж treeBodyHTML — інакше точкове оновлення розійдеться з повним");
  assert.doesNotMatch(inner, /pp-filter/);
  assert.match(inner, /data-act="unfocus"/, "крихти з виходом із фокуса — всередині тіла, яке перемальовується");
  assert.match(inner, /role="tree"/);
});

test("панель: порядок дітей .panel-body стабільний — tree-head, фільтр, tree-body, panel-fill", () => {
  const h = panelHTML(S());
  const order = ["tree-head", 'class="tree-filter"', 'class="tree-body"', "panel-fill"].map((k) => h.indexOf(k));
  assert.ok(order.every((i) => i >= 0), "чогось із чотирьох бракує");
  assert.deepEqual([...order].sort((a, b) => a - b), order, "порядок не той: точкове оновлення тримається на ньому");
  // крихти більше не сусід фільтра, а частина тіла дерева
  assert.ok(h.indexOf("tree-crumbs") === -1 || h.indexOf("tree-crumbs") > h.indexOf('class="tree-body"'));
});

test("порожній фільтр/помилка/нема ітерації теж живуть у .tree-body", () => {
  assert.match(treeBodyHTML(S({ rows: [], filter: "zzz" })), /filter|shots-s/);
  assert.match(panelHTML(S({ rows: [], filter: "zzz" })), /class="tree-body"><p/);
  assert.match(panelHTML(S({ pagesError: "500", rows: [] })), /class="tree-body"><p/);
});

test("клавіатура: roving tabindex за row.focus; без жодного focus перший рядок tabbable", () => {
  const h = panelHTML(S({ rows: [row({ id: "a" }), row({ id: "b", focus: true }), row({ id: "c" })] }));
  const ti = (id) => h.match(new RegExp(`<div class="row[^"]*"[^>]*data-page="${id}"[^>]*tabindex="(-?\\d)"`))?.[1];
  assert.equal(ti("a"), "-1");
  assert.equal(ti("b"), "0");
  assert.equal(ti("c"), "-1");
  const none = panelHTML(S({ rows: [row({ id: "a" }), row({ id: "b" })] }));
  assert.equal((none.match(/tabindex="0"/g) || []).length, 1, "рівно один tab-стоп на все дерево");
  assert.match(none, /data-page="a"[^>]*tabindex="0"/);
});

test("клавіатура: aria-expanded лише на рядку; каретка — tabindex=-1 і без aria-expanded", () => {
  const h = panelHTML(S({ rows: [row({ id: "a", hasKids: true, expanded: true })] }));
  const caret = h.match(/<button class="row-caret"[^>]*>/)[0];
  assert.match(caret, /tabindex="-1"/);
  assert.doesNotMatch(caret, /aria-expanded/);
  assert.match(h, /role="treeitem"[^>]*aria-expanded="true"/);
});

test("глибина з нечислового/відсутнього row.depth — 0, а не NaN у --d і aria-level", () => {
  const h = panelHTML(S({ rows: [row({ id: "a", depth: undefined }), row({ id: "b", depth: "2" })] }));
  assert.doesNotMatch(h, /NaN|undefined/);
  assert.match(h, /data-page="a"[^>]*aria-level="1"/);
  assert.match(h, /--d:2/);
});

/* ── B3 (ревʼю): превʼю без обіцянок, aria-selected, каретка під фільтром ── */

test("readonly: без tabindex, role=tree/treeitem, aria-* — розмітка не обіцяє клавіатури, якої там нема", () => {
  const h = panelHTML(S({ readonly: true, rows: [row({ id: "a", hasKids: true, expanded: true, selected: true }), row({ id: "b" })] }));
  assert.doesNotMatch(h, /tabindex|role="tree|role="treeitem|aria-expanded|aria-level|aria-selected/);
  assert.match(h, /data-page="a"/, "рядки й дії лишились");
  assert.match(panelHTML(S({ rows: [row({ id: "a" })] })), /role="tree"[\s\S]*role="treeitem"/, "в інструменті — лишилось");
});

test("aria-selected: ariaSelected з рядка має перевагу; без нього — selected/multi", () => {
  const sel = (o) => panelHTML(S({ rows: [row({ id: "a", ...o })] })).match(/data-page="a"[^>]*aria-selected="(\w+)"/)[1];
  assert.equal(sel({ selected: true }), "true");
  assert.equal(sel({ multi: true }), "true");
  assert.equal(sel({}), "false");
  assert.equal(sel({ selected: true, ariaSelected: false }), "false", "відкрита сторінка поза вибором — не selected для читача");
  assert.equal(sel({ ariaSelected: true }), "true");
});

test("під фільтром каретки нема: розкриття примусове, шеврон збрехав би", () => {
  const rows = [row({ id: "a", hasKids: true, expanded: true })];
  assert.match(panelHTML(S({ rows })), /class="row-caret"/);
  const f = panelHTML(S({ rows, filter: "аб" }));
  assert.doesNotMatch(f, /data-act="toggle"|class="row-caret"/);
  assert.match(f, /row-caret--none/, "місце під каретку лишилось — назви не стрибають");
});

test("readonly: каретка лишається звичайною кнопкою (у Tab-порядку), без tabindex=-1", () => {
  const h = panelHTML(S({ readonly: true, rows: [row({ id: "a", hasKids: true })] }));
  assert.match(h, /class="row-caret"[^>]*data-act="toggle"/);
  assert.doesNotMatch(h.match(/<button class="row-caret"[^>]*>/)[0], /tabindex/);
});

test("рядок сторінки, змінений щойно, має позначку «змінено щойно»", async () => {
  const { panelHTML } = await import("../app/shell-panel.js");
  const st = (recent) => S({ rows: [row({ id: "p", name: "Картка", recent })] });
  const hot = panelHTML(st(true));
  assert.match(hot, /class="row-recent-dot"/);
  assert.doesNotMatch(panelHTML(st(false)), /row-recent-dot/);
});

test("рядок із news: бурштиновий лічильник row-news з підписом; без news — нема", () => {
  const html = panelHTML(S({ rows: [deepRow({ news: 2 })] }));
  assert.match(html, /<span class="row-news" title="Нових коментарів від команди: 2">2<\/span>/);
  assert.equal(panelHTML(S({ rows: [deepRow({})] })).includes("row-news"), false);
  assert.match(panelHTML(S({ rows: [deepRow({ news: 250 })] })), />99\+<\/span>/);
});
