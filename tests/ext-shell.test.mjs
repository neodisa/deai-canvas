/**
 * Адаптер зовнішньої оболонки: `manifest.json` → стан для двох малювальників
 * (`extBarHTML` і спільний `panelHTML` з `readonly: true`).
 *
 * Чому це окремий юніт, а не «перевіримо живим тестом». Живий тест ходить по
 * ЗІБРАНОМУ `publish/`, тобто бачить лише один маніфест — той, який зібралась
 * фікстура. Кути, від яких зовнішня оболонка справді ламається, у фікстурі не
 * трапляються: маніфест, який не прочитався; ітерація без жодного кадру;
 * сторінка на глибині 1, чий батько-тека до маніфеста не поїхав; глибоке
 * посилання на сторінку, якої в маніфесті немає. Кожен із них у чужому
 * браузері виглядає як «оболонка не піднялась», і ціну платить людина, якій
 * ми дали посилання.
 *
 * ⚠️ `ext-shell.js` везе І чистий адаптер, І проводку DOM (так його називає
 * план: «адаптер стану плюс тонка проводка»). Тому підняття оболонки в ньому
 * стоїть за перевіркою наявності `document` — інакше цей файл не можна було б
 * імпортувати в node, і адаптер перевірявся б лише крізь браузер.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { CARD_W, GAP, HEAD, ROW_TITLE_TOP } from "../app/canvas-geom.js";
import {
  copyUrl, effMode, extBarState, extPanelState, extRows, extTree, frameCardH, hashPage, overviewCardW,
  overviewRows, overviewWhyKey, overviewWorld, rowAction, startPage, vpWidth,
} from "../app/ext-shell.js";
import { DICT, setLang } from "../app/i18n.js";
import { rowsLayout, worldBox } from "../app/layout.js";
import { panelHTML } from "../app/shell-panel.js";

/** Маніфест, який пише `publish_manifest()` (див. `tests/test_serve.py`). */
const MAN = {
  task: "Віджет «Суди»",
  /* `num` і `note` ОКРЕМО — так їх кладе `publish_manifest`: номер це
     ідентифікатор, примітка це дані, а префікс «Іт.N» складає словник
     мовою глядача (див. тест англійської нижче). */
  iters: [{ id: "it1", num: "1", note: "старт" },
    { id: "it3", num: "3", note: "Правки" }],
  pages: [
    { id: "it1", it: "it1", key: "main", name: "Головна", depth: 0,
      path: "it1/index.html" },
    { id: "it1/empty", it: "it1", key: "empty", name: "Стан: порожньо", depth: 1,
      path: "it1/empty/index.html" },
    { id: "it1/poshuk", it: "it1", key: "poshuk", name: "Пошук", depth: 0,
      path: "it1/poshuk/index.html" },
    { id: "it3/nova", it: "it3", key: "nova", name: "Нова", depth: 0,
      path: "it3/nova/index.html" },
  ],
  frames: { it1: { main: "it1/_frames/main.webp" }, it3: {} },
  widths: [1280],
};

const UI = (o = {}) => ({
  it: "it1", page: "it1", mode: "layout", vp: "desktop", openDd: null,
  expanded: new Set(), collapsed: false, copied: false, error: "", ...o,
});

const rows = (man, ui) => extPanelState(man, UI(ui)).rows;

/* ── панель ─────────────────────────────────────────────────────────────── */

test("панель приходить у режимі лише-читання й без блоку кадрів", () => {
  const st = extPanelState(MAN, UI());
  assert.equal(st.readonly, true, "без прапорця панель показала б «⋯», «+» і зʼємку");
  assert.equal(st.shots, null, "зʼємки в статиці не існує — рахувати кадри нема для чого");
  const h = panelHTML(st);
  for (const act of ['data-act="pagemenu"', 'data-act="newpage"', 'data-act="shoot"',
    'data-act="shotsopen"']) {
    assert.ok(!h.includes(act), `${act} у статичному превʼю нікуди не веде`);
  }
  // Дерево при цьому ціле — інакше прапорець прибрав би зайве.
  assert.ok(h.includes('data-act="page" data-val="it1"'), "рядка сторінки немає");
  assert.ok(h.includes('data-act="panel"'), "згортання панелі — не дія над даними, лишається");
});

test("рядки — лише поточної ітерації", () => {
  assert.deepEqual(rows(MAN, {}).map((r) => r.id), ["it1", "it1/poshuk"]);
  assert.deepEqual(rows(MAN, { it: "it3", page: "it3/nova" }).map((r) => r.id),
    ["it3/nova"]);
});

/* Типово згорнуто: підсторінки й стани не мозолять очі, поки їх не попросили.
   Те саме правило, що в старій обгортці (`EXP` тримав саме РОЗГОРНУТІ). */
test("діти згорнуті типово й розгортаються карткою батька", () => {
  const closed = rows(MAN, { page: "it1/poshuk" });
  assert.deepEqual(closed.map((r) => r.id), ["it1", "it1/poshuk"]);
  const open = rows(MAN, { page: "it1/poshuk", expanded: new Set(["it1"]) });
  assert.deepEqual(open.map((r) => r.id), ["it1", "it1/empty", "it1/poshuk"]);
});

/* Вибрана сторінка МУСИТЬ бути видима: інакше глибоке посилання на стан
   відкриває макет, а в дереві підсвічено нічого. */
test("гілка вибраної сторінки розгортається, а сам набір не мутується", () => {
  const expanded = new Set();
  const r = rows(MAN, { page: "it1/empty", expanded });
  assert.deepEqual(r.map((r2) => r2.id), ["it1", "it1/empty", "it1/poshuk"]);
  assert.ok(r.find((x) => x.id === "it1/empty").selected, "вибір не позначений");
  assert.equal(expanded.size, 0,
    "адаптер чистий: розгортання вибраної гілки не сміє правити стан викликача");
});

test("каретка є лише в того, у кого справді є діти", () => {
  const r = rows(MAN, { expanded: new Set(["it1"]) });
  assert.equal(r.find((x) => x.id === "it1").hasKids, true);
  assert.equal(r.find((x) => x.id === "it1/empty").hasKids, false);
  assert.equal(r.find((x) => x.id === "it1/poshuk").hasKids, false);
  assert.equal(r.find((x) => x.id === "it1").expanded, true);
});

/* ⛔ Крапки «у превью» тут немає, і це рішення, а не пропуск: у маніфест їдуть
   ЛИШЕ опубліковані сторінки (`published_pages`), тобто крапка стояла б на
   кожному рядку без винятку й не відрізняла б нічого. Позначку, що є в
   кожного, читають як декор — і наступного разу, коли вона щось означатиме,
   їй уже не повірять. */
test("позначки «у превью» немає — у маніфесті інших сторінок не буває", () => {
  assert.deepEqual([...new Set(rows(MAN, { expanded: new Set(["it1"]) })
    .map((r) => r.mark))], [false]);
  assert.ok(!panelHTML(extPanelState(MAN, UI())).includes("row-mark"));
});

/* Тека в маніфест не їде (`published_pages` викидає `isGroup`), а її ДІТИ
   їдуть — із глибиною 1 і без батьківського рядка. Такий рядок мусить лишитись
   видимим: сховати його «до розгортання батька» означало б прибрати з превʼю
   опубліковану сторінку, і ніде жодного слова про причину. */
test("сторінка з теки видима, хоч батьківського рядка в маніфесті немає", () => {
  const man = { ...MAN, pages: [
    { id: "it1/grupa/a", it: "it1", key: "a", name: "А", depth: 1,
      path: "it1/grupa/a/index.html" },
    { id: "it1/grupa/b", it: "it1", key: "b", name: "Б", depth: 1,
      path: "it1/grupa/b/index.html" },
  ] };
  const r = rows(man, { page: "it1/grupa/a" });
  assert.deepEqual(r.map((x) => x.id), ["it1/grupa/a", "it1/grupa/b"]);
  // Іконка «стану» тут була б брехнею: це самостійні екрани, а не варіанти.
  assert.deepEqual([...new Set(r.map((x) => x.isState))], [false]);
});

test("маніфест, який не прочитався, доходить до панелі словами", () => {
  const st = extPanelState(null, UI({ error: "манифест не читається" }));
  assert.equal(st.hasIteration, false);
  assert.equal(st.pagesError, "манифест не читається");
  assert.ok(panelHTML(st).includes("манифест не читається"),
    "панель мовчить про причину — глядач бачить порожнє дерево");
});

test("рейка згорнутої панелі — з того самого прапорця", () => {
  assert.equal(extPanelState(MAN, UI({ collapsed: true })).panel, "rail");
  assert.equal(extPanelState(MAN, UI()).panel, "open");
});

/* ── смуга ──────────────────────────────────────────────────────────────── */

test("смуга складає тег ітерації сама, а примітку везе окремим полем", () => {
  const st = extBarState(MAN, UI({ it: "it3" }));
  assert.equal(st.task, "Віджет «Суди»");
  assert.equal(st.iterLabel, "Іт.3", "тег мусить приходити зі словника, не з маніфеста");
  assert.equal(st.iterNote, "Правки", "примітка — окреме поле, її обрізає розмітка");
  assert.deepEqual(st.iters, [
    { id: "it1", label: "Іт.1", note: "старт", on: false },
    { id: "it3", label: "Іт.3", note: "Правки", on: true },
  ]);
  assert.equal(st.mode, "layout");
  assert.equal(st.vp, "desktop");
});

/* ⛔ ЦЕНТРАЛЬНА перевірка цієї правки. Заміряно в браузері 03.09.2026 на
   зібраному превʼю: при `dc-lang=en` смуга йшла англійською («Layout /
   Overview / Copy link»), панель теж («Layers / Pages»), а крошка ітерації
   показувала «Іт.1 · фікстура» — бо `publish_manifest` клав у маніфест
   ГОТОВИЙ підпис, спечений `iteration_label()` у Python.

   Примітка при цьому лишається кирилицею СВІДОМО: її написав дизайнер, це
   дані, а не інтерфейс. Тому мішень перевірки — саме тег. */
test("англійська мова міняє ТЕГ ітерації, а примітку лишає як дані", () => {
  setLang("en");
  try {
    const st = extBarState(MAN, UI({ it: "it3" }));
    assert.equal(st.iterLabel, "It.3");
    assert.equal(st.iterNote, "Правки", "примітку не перекладаємо — це дані");
    assert.deepEqual(st.iters.map((x) => x.label), ["It.1", "It.3"]);
  } finally {
    setLang("uk");
  }
});

/**
 * Охоронець на дорогу, якою тут більше НЕ ходять.
 *
 * Інструмент зрізає префікс «Іт.N» із серверного `label_text` регекспом і
 * мусить тримати той регексп кирилицею — це записано і в `app/app.js`, і
 * винятком `new RegExp(` у `tests/i18n-literals.test.mjs`. Зовнішня оболонка
 * від цієї дороги відмовилась зовсім: сервер більше не пече підпис, тег
 * складає словник, примітка приїжджає окремим полем.
 *
 * Чому це варте охоронця, а не коментаря: регексп, скопійований сюди з
 * інструмента, ПРАЦЮВАВ би на око — і мовчки повернув би кирилицю в
 * English-режим, бо шукав би «Іт.3» у рядку, де стоїть «It.3», не знаходив і
 * лишав префікс усередині примітки. Тобто вада виглядала б рівно як та, яку
 * ця правка щойно прибрала.
 *
 * ⚠️ Чому НЕ покладаємось на `tests/i18n-literals.test.mjs`, який теж шукає
 * кирилицю: він сканує строкові й шаблонні літерали, а РЕГЕКСПНІ пропускає
 * свідомо (`REGEX_AFTER` там саме для того, щоб лапка всередині регекспа не
 * зсувала парування). Тобто `/^Іт\./` у цих файлах не побачив би НІХТО —
 * рівно та форма, якою вада й приїхала б.
 *
 * ⛔ Межа: скануємо КОД, не коментарі. Коментарі в цьому репозиторії —
 * головна документація, і «Іт.3» у них стоїть як приклад (цей абзац теж). Без
 * забілювання охоронець валив би саме опис того, що він стереже: перевірено,
 * рівно так він і впав на першому прогоні. Регексп забілювання — той самий,
 * що в `i18n-literals` (`(?<!:)` тримає `https://` коментарем не ставши).
 */
test("оболонка не розбирає підпис ітерації регекспом — його розділяє сервер", () => {
  for (const f of ["ext-shell.js", "ext-bar.js"]) {
    const raw = readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
    const code = raw.replace(/\/\*[\s\S]*?\*\/|(?<!:)\/\/[^\n]*/g, "");
    /* Свідки проти вакууму: файл прочитаний, і забілювання не зʼїло код
       цілком. Без другого зламане забілювання дало б порожній рядок — і
       охоронець зеленів би назавжди, бо шукати вже нічого. */
    assert.ok(raw.length > 5000, `${f}: прочитано ${raw.length} байт — не той файл`);
    assert.ok(code.length > raw.length / 3,
      `${f}: після забілювання лишилось ${code.length} із ${raw.length} байт `
      + "— зламаний регексп коментарів, а не «код чистий»");
    assert.ok(!code.includes("RegExp"),
      `${f}: зовнішній оболонці нема чого розбирати — сервер везе num і note окремо`);
    assert.ok(!code.includes("Іт."),
      `${f}: тег «Іт.» у коді означає кирилицю в English-режимі — він у словнику`);
  }
});

test("смуга малюється навіть без маніфеста — і тоді несе причину", () => {
  const st = extBarState(null, UI({ error: "манифест не читається" }));
  assert.deepEqual(st.iters, []);
  assert.equal(st.error, "манифест не читається");
  assert.equal(st.task, "");
});

/* ⛔ «Огляд» без кадрів — вимкнений із ПРИЧИНОЮ. Мовчазна кнопка, що відкриває
   порожнє полотно, читається як зламаний інструмент: у глядача немає ні
   зʼємки, ні способу дізнатись, що кадрів просто не знімали. */
test("ітерація без кадрів вимикає «Огляд» причиною зі словника", () => {
  assert.equal(overviewWhyKey(MAN, "it1"), "");
  assert.equal(overviewWhyKey(MAN, "it3"), "shotsNone");
  assert.equal(overviewWhyKey(null, "it1"), "shotsNone");
  assert.equal(extBarState(MAN, UI({ it: "it3" })).overviewWhyKey, "shotsNone");
  assert.equal(extBarState(MAN, UI()).overviewWhyKey, "");
});

/* ── глибоке посилання й «Копіювати посилання» ──────────────────────────── */

test("глибоке посилання читається з hash поруч із токеном гейта", () => {
  assert.equal(hashPage("#p=it1/poshuk"), "it1/poshuk");
  assert.equal(hashPage("#k=1100&p=it1/poshuk"), "it1/poshuk");
  assert.equal(hashPage("#p=it1%2Fposhuk"), "it1/poshuk");
  assert.equal(hashPage("#k=1100"), null);
  assert.equal(hashPage(""), null);
});

test("стартова сторінка — з посилання, інакше перша в ОСТАННІЙ ітерації", () => {
  assert.equal(startPage(MAN, "#p=it1/poshuk"), "it1/poshuk");
  // Сторінку могли зняти з превʼю після того, як посилання розійшлось.
  assert.equal(startPage(MAN, "#p=it9/nemaje"), "it3/nova");
  /* ⛔ Не `pages[0]`: перша сторінка маніфесту лежить у ПЕРШІЙ ітерації, тобто
     глядач відкривав превʼю на найстарішому макеті й мусив сам здогадатись
     перемкнути крошку. Інструмент так не робить давно (`render()` в app.js
     бере `iterations[length-1]`), і превʼю мусить відкриватись так само. */
  assert.equal(startPage(MAN, ""), "it3/nova");
  // Ітерація без сторінок пропускається: показувати нема чого, і порожній
  // екран замість макета був би гіршим за «відкрий попередню».
  assert.equal(startPage({ ...MAN, iters: [...MAN.iters, { id: "it4", num: "4" }] }, ""),
    "it3/nova");
  // Маніфест без `iters` (чужий або урізаний) — перша сторінка, як раніше.
  assert.equal(startPage({ ...MAN, iters: [] }, ""), "it1");
  assert.equal(startPage({ ...MAN, pages: [] }, ""), null);
  assert.equal(startPage(null, "#p=it1"), null);
});

/* Посилання з `#k=` — безшовний вхід без пароля: та сама модель, що в
   дашборді, і саме вона робить кнопку осмисленою (інакше менеджер шле колезі
   URL, який просить пароль, якого в колеги немає). */
test("«Копіювати посилання» дає безшовний вхід на потрібну сторінку", () => {
  const u = copyUrl({ origin: "https://x.vercel.app", pathname: "/", search: "" },
    "1100", "it1/poshuk");
  assert.equal(u, "https://x.vercel.app/#k=1100&p=it1%2Fposhuk");
});

test("пароль і сторінка в посиланні кодуються", () => {
  const u = copyUrl({ origin: "https://x.vercel.app", pathname: "/", search: "" },
    "a&b=c", "it1/по шук");
  assert.ok(u.includes("#k=a%26b%3Dc"), `пароль не закодований: ${u}`);
  assert.ok(!u.includes(" "), "пробіл у hash лишився сирим");
});

/* ── ширина рамки ───────────────────────────────────────────────────────── */

test("ширина рамки береться з пресетів viewport.js", async () => {
  const { PRESETS } = await import("../app/viewport.js");
  for (const p of PRESETS) assert.equal(vpWidth(p.id), p.w, `пресет ${p.id}`);
  assert.equal(vpWidth("desktop"), null, "десктоп — вільна ширина вікна");
  assert.equal(vpWidth("nema"), null, "невідомий пресет не сміє дати NaN у CSS");
});

/* ── «Огляд»: полотно з кадрів ───────────────────────────────────────────── */

/**
 * Маніфест із кадрами ДВОХ ширин і однією дірою.
 *
 * Діра навмисна й точкова: `empty@768` немає, хоч сусідні кадри 768 є. Це
 * найдорожчий кут усієї фічі — «кадри для цієї ширини знято, але не для всіх
 * сторінок», — і в живому тесті його не буває, бо зʼємка знімає все або нічого.
 */
const OMAN = {
  task: "Огляд",
  iters: [{ id: "it1", num: "1", note: "" }],
  pages: [
    { id: "it1", it: "it1", key: "main", name: "Головна", depth: 0,
      path: "it1/index.html" },
    { id: "it1/empty", it: "it1", key: "empty", name: "Стан: порожньо", depth: 1,
      path: "it1/empty/index.html" },
    { id: "it1/poshuk", it: "it1", key: "poshuk", name: "Пошук", depth: 0,
      path: "it1/poshuk/index.html" },
  ],
  frames: {
    it1: {
      main: "it1/_frames/main.webp",
      empty: "it1/_frames/empty.webp",
      poshuk: "it1/_frames/poshuk.webp",
      "main@768": "it1/_frames/main@768.webp",
      "poshuk@768": "it1/_frames/poshuk@768.webp",
    },
  },
  widths: [768, 1280],
};

/** Той самий маніфест у формі, яку пише `publish_frames` із 03.09.2026:
 *  кадр — це `{path, w, h}`, де `w`/`h` заміряла зʼємка. `poshuk` знято з
 *  подвоєною щільністю (2560 на вьюпорті 1280) — саме те, через що пропорцію
 *  доводиться рахувати, а не брати `h` як висоту картки. */
const OSIZED = { ...OMAN, frames: { it1: {
  main: { path: "it1/_frames/main.webp", w: 1280, h: 6879 },
  empty: { path: "it1/_frames/empty.webp", w: 1280, h: 3529 },
  poshuk: { path: "it1/_frames/poshuk.webp", w: 2560, h: 4000 },
} } };

const cardsOf = (man, ui) => overviewRows(man, UI(ui)).flatMap((r) => r.cards);

/* ⛔ ЦЕНТРАЛЬНА перевірка задачі: розкладку рахує СПІЛЬНА геометрія, а не
   власні числа зовнішньої оболонки. Очікуване тут збирається з тих самих
   `rowsLayout`/`worldBox`/констант `canvas-geom.js`, тобто будь-яке число,
   зашите в `ext-shell.js` руками, розводить дві сторони рівності.
   Мутація, якою це доведено: `gap: GAP` → `gap: 96` (той самий зазор, що
   стояв до 31.08.2026) — тест червоніє на `placed`. */
test("розкладка «Огляду» — спільною геометрією, не власними числами", () => {
  const rows = overviewRows(OMAN, UI());
  const H = { main: 2000, empty: 3000, poshuk: 1200 };
  const heightOf = (c) => H[c.key];
  const got = overviewWorld(rows, CARD_W, heightOf);

  const want = rowsLayout(
    rows.map((r) => r.cards.map((c) => ({ id: c.fkey, h: heightOf(c) }))),
    { cardW: CARD_W, gap: GAP, head: HEAD },
  ).map((p) => ({ ...p, y: p.y + ROW_TITLE_TOP }));
  assert.deepEqual(got.placed, want, "координати карток розійшлись із layout.js");
  assert.deepEqual(got.box, worldBox(want, CARD_W), "габарит світу — не з worldBox");

  /* Незалежні свідки: без них рівність вище була б зеленою і на порожньому
     світі (обидві сторони — нуль), і на розкладці в один стовпчик. */
  assert.equal(got.box.w, CARD_W + GAP + CARD_W, "другої колонки в ряду немає");
  assert.equal(got.placed[0].y, ROW_TITLE_TOP,
    "перший ряд не зсунутий під підпис — підпис поїхав вище нуля, куди камера не дивиться");
  assert.equal(got.placed[0].h, HEAD + H.main, "висота картки без голови");
  assert.ok(got.box.h > HEAD + H.empty, `габарит ${got.box.h} не вміщує найвищий ряд`);
});

/* ⛔ Кадр береться ключем ІЗ ШИРИНОЮ (`frameKey`), а не масштабуванням того
   самого знімка: інакше «Планшет» показував би десктопний кадр, стиснутий
   утроє, і глядач вирішив би, що макет на планшеті саме такий.
   Мутація, якою доведено: `frameKey(c.key, w)` → `c.key`. */
test("кадр береться за ключем із шириною — інша ширина, інші кадри", () => {
  const desk = cardsOf(OMAN, {});
  assert.deepEqual(desk.map((c) => c.fkey), ["main", "empty", "poshuk"],
    "типова ширина суфікса не додає (див. CANVAS_W у viewport.js)");
  assert.deepEqual(desk.map((c) => c.src), [
    "it1/_frames/main.webp", "it1/_frames/empty.webp", "it1/_frames/poshuk.webp"]);

  const tab = cardsOf(OMAN, { vp: "tablet" });
  assert.deepEqual(tab.map((c) => c.fkey), ["main@768", "empty@768", "poshuk@768"]);
  assert.deepEqual(tab.map((c) => c.src), [
    "it1/_frames/main@768.webp", null, "it1/_frames/poshuk@768.webp"]);

  assert.equal(overviewCardW("desktop"), CARD_W,
    "ширина картки полотна мусить дорівнювати ширині, якою знято типовий кадр");
  assert.equal(overviewCardW("tablet"), 768);
  assert.equal(overviewCardW("nema"), CARD_W, "невідомий пресет не сміє дати NaN у CSS");
});

/* ⛔ Порожній прямокутник читається як зламане полотно — те саме правило, що
   вимикає «Огляд» без кадрів із видимою причиною. Причин ДВІ, бо глядачеві
   треба різне: «не ту ширину дивиш» рятує клік по сегменту, «сторінку не
   знімали» — не рятує нічим, і казати одне замість другого означає відправити
   людину тиснути кнопки без наслідку. */
test("сторінка без кадру потрібної ширини — заглушка з причиною", () => {
  const gap = cardsOf(OMAN, { vp: "tablet" }).find((c) => c.key === "empty");
  assert.equal(gap.src, null);
  assert.equal(gap.whyKey, "extNoFramePage");

  const mob = cardsOf(OMAN, { vp: "mobile" });
  assert.deepEqual([...new Set(mob.map((c) => c.src))], [null], "кадрів 375 у маніфесті немає");
  assert.deepEqual([...new Set(mob.map((c) => c.whyKey))], ["extNoFrameWidth"]);

  assert.deepEqual([...new Set(cardsOf(OMAN, {}).map((c) => c.whyKey))], [""],
    "картка з кадром не сміє нести причину — заглушки в неї немає");
});

/* Причина мусить бути СЛОВОМ, а не іменем ключа на екрані. `t()` кидає на
   невідомому ключі, але кидає в рантаймі глядача — тут перевіряємо статично й
   в обох мовах: зовнішнє превʼю відкривають і англійською. */
test("обидві причини заглушки лежать у словнику двома мовами", () => {
  for (const key of ["extNoFramePage", "extNoFrameWidth"]) {
    for (const lang of ["uk", "en"]) {
      const v = DICT[lang][key];
      assert.notEqual(v, undefined, `${key} немає в ${lang}`);
      const text = typeof v === "function" ? v(390) : v;
      assert.ok(String(text).trim().length > 0, `${key}/${lang} — порожній рядок`);
      assert.ok(!String(text).includes(key), `${key}/${lang} показує імʼя ключа`);
    }
  }
});

test("картка на сторінку, ряд на верхню сторінку — склад дає rows-model", () => {
  const rows = overviewRows(OMAN, UI());
  assert.deepEqual(rows.map((r) => r.title), ["Головна", "Пошук"],
    "підпис ряду — імʼя верхньої сторінки");
  assert.deepEqual(rows.map((r) => r.cards.map((c) => c.label)),
    [["Головна", "Стан: порожньо"], ["Пошук"]]);
  const cards = rows.flatMap((r) => r.cards);
  assert.equal(cards.length, OMAN.pages.filter((p) => p.it === "it1").length,
    "карток мусить бути стільки, скільки сторінок: полотно нічого не ховає");
  /* Клік по картці мусить знати, ЩО відкривати: `id` сторінки (шлях у publish),
     а не ключ кадру. У неявної «Головної» вони розходяться назовсім. */
  assert.deepEqual(cards.map((c) => c.pageId), ["it1", "it1/empty", "it1/poshuk"]);
  assert.deepEqual(cards.map((c) => c.path),
    ["it1/index.html", "it1/empty/index.html", "it1/poshuk/index.html"]);
  // Інша ітерація — інші картки, і ні одної чужої.
  assert.deepEqual(overviewRows(MAN, UI({ it: "it3", page: "it3/nova" }))
    .flatMap((r) => r.cards).map((c) => c.pageId), ["it3/nova"]);
});

/* Сторінка з ТЕКИ приходить із `depth: 1` і без батьківського рядка (тека в
   маніфест не їде). У панелі це вже покрито; тут — щоб вона не стала карткою
   всередині чужого ряду. */
test("сторінки з теки дають свої ряди, а не приліплюються до чужого", () => {
  const man = { ...OMAN, pages: [
    { id: "it1/grupa/a", it: "it1", key: "a", name: "А", depth: 1,
      path: "it1/grupa/a/index.html" },
    { id: "it1/grupa/b", it: "it1", key: "b", name: "Б", depth: 1,
      path: "it1/grupa/b/index.html" },
  ], frames: { it1: { a: "it1/_frames/a.webp", b: "it1/_frames/b.webp" } } };
  const rows = overviewRows(man, UI({ page: "it1/grupa/a" }));
  assert.deepEqual(rows.map((r) => r.cards.map((c) => c.label)), [["А"], ["Б"]]);
  assert.deepEqual(rows.map((r) => r.title), ["А", "Б"]);
});

/* ⛔ Режим, у якому нема чого показати, не сміє бути «включеним»: сегмент
   стояв би натиснутим над макетом і брехав про те, де глядач. Досяжно це не
   теоретично, а найзвичайнішим шляхом: перемкнув ітерацію, будучи в «Огляді»,
   — а її ніхто не знімав. */
test("ітерація без кадрів не пускає в «Огляд» навіть із наставленим режимом", () => {
  assert.equal(effMode(OMAN, UI({ mode: "overview" })), "overview");
  const bare = { ...OMAN, frames: { it1: {} } };
  assert.equal(effMode(bare, UI({ mode: "overview" })), "layout");
  assert.equal(effMode(null, UI({ mode: "overview" })), "layout");
  assert.equal(effMode(OMAN, UI()), "layout");
  assert.equal(extBarState(bare, UI({ mode: "overview" })).mode, "layout",
    "смуга мусить показувати РЕАЛЬНИЙ режим, а не той, який просили");
});

/* ⛔ ЦЕНТРАЛЬНА перевірка правки 03.09.2026. Висота картки відома ЩЕ ДО того,
   як кадр приїхав: `publish_frames` тепер везе `w`/`h` заміряні зʼємкою.
   До цього пропорцію повідомляв лише сам знімок після завантаження, і на
   повільній мережі глядач бачив геометрію, яка брехала про розміри — розкид
   справжніх висот заміряний, 900…8000px.
   Мутація, якою доведено: `card.natW && card.natH ? … : FRAME_H_FALLBACK`
   → просто `FRAME_H_FALLBACK` — падає перший же `assert.equal` нижче. */
test("розмір із маніфеста дає висоту картки до приїзду кадру", () => {
  const cards = cardsOf(OSIZED, {});
  assert.deepEqual(cards.map((c) => [c.natW, c.natH]),
    [[1280, 6879], [1280, 3529], [2560, 4000]]);

  /* Ділимо на `natW`, а не беремо `natH` як є — рівно з тієї причини, з якої це
     робить `onFrameLoad`: кадр `poshuk` знято з подвоєною щільністю (2560 на
     ширині вьюпорта 1280), і голе `natH` дало б картку удвічі вищу за пропорцію. */
  assert.equal(frameCardH(cards[0], 1280), 6879);
  assert.equal(frameCardH(cards[1], 640), 1765, "пропорція під іншу ширину картки");
  assert.equal(frameCardH(cards[2], 1280), 2000, "щільність кадру не врахована");
});

/* ⛔ Друга дорога лишається робочою, а не аварійною: розмір, який не пройшов
   валідацію на python-боці, у маніфест не їде взагалі (`publish_frames`), і
   тоді пропорцію питає сам знімок. Вигаданого числа тут бути не сміє — світ
   мусить визнати, що не знає, і дочекатись кадру.
   Мутація: прибрати перевірку в `num()` (`typeof v === "number" && …` → `v`)
   — падає `natW`/`natH` нижче, бо `"1280"` і `0` пролізли б у пропорцію. */
test("кадр без придатного розміру чекає пропорції від самого знімка", () => {
  const man = { ...OSIZED, frames: { it1: {
    main: { path: "it1/_frames/main.webp" },
    empty: { path: "it1/_frames/empty.webp", w: "1280", h: 3529 },
    poshuk: { path: "it1/_frames/poshuk.webp", w: 1280, h: 0 },
  } } };
  const cards = cardsOf(man, {});
  assert.deepEqual(cards.map((c) => c.src), [
    "it1/_frames/main.webp", "it1/_frames/empty.webp", "it1/_frames/poshuk.webp"],
    "кадр із битим розміром мусить лишитись видимим — бракує лише пропорції");
  assert.deepEqual(cards.map((c) => [c.natW, c.natH]), [[0, 0], [0, 0], [0, 0]]);
  for (const c of cards) {
    assert.equal(frameCardH(c, 1280), 900,
      "без розміру картка мусить стати ЗАГЛУШКОВОЇ висоти, а не NaN/Infinity");
  }
  // Запис без `path` — не кадр: інакше `img.src` дістав би `undefined`.
  assert.equal(cardsOf({ ...OSIZED, frames: { it1: { main: { w: 1280, h: 10 } } } },
    {})[0].src, null);
});

/* ⛔ Зворотна сумісність, і причина в неї ВУЗЬКА, названа вголос. Превʼю,
   зібране між `0f62ddd` і цією правкою, несе `frames[fid]` РЯДКОМ. Живого
   такого немає (маніфест узагалі існує лише на цій невлитій гілці), але
   `ops/reseal_gate.py` перепечатує ЛИШЕ обгортку й свідомо лишає маніфест від
   старої публікації — тобто зібрана раніше тека може поїхати в деплой як є.
   Ціна прийняти обидві форми — один `typeof`; ціна не прийняти — `img.src`
   отримує `[object Object]`, тобто битий кадр БЕЗ імені причини.
   Мутація: прибрати гілку рядка — падає `src` нижче. */
test("превʼю зі старою формою кадру лишається читабельним", () => {
  const cards = cardsOf(OMAN, {});   // фікстура OMAN — саме стара форма
  assert.deepEqual(cards.map((c) => c.src), [
    "it1/_frames/main.webp", "it1/_frames/empty.webp", "it1/_frames/poshuk.webp"]);
  assert.deepEqual(cards.map((c) => [c.natW, c.natH]), [[0, 0], [0, 0], [0, 0]],
    "стара форма розмірів не несе — пропорцію дасть знімок");
  assert.equal(frameCardH(cards[0], 1280), 900);
});

test("маніфест без кадрів не валить розкладку — світ просто нульовий", () => {
  const rows = overviewRows(null, UI());
  assert.deepEqual(rows, []);
  assert.deepEqual(overviewWorld(rows, CARD_W, () => 900), { placed: [], box: { w: 0, h: 0 } });
});

const MAN_OUTLINE = {
  pages: [
    { id: "it1/p", it: "it1", key: "p", name: "Картка", depth: 0, path: "it1/p/index.html" },
    { id: "it1/s", it: "it1", key: "s", name: "Помилка", depth: 2, path: "it1/s/index.html" }],
  outline: [
    { id: "it1/p", it: "it1", key: "p", name: "Картка", kind: "page", depth: 0, path: "it1/p/index.html" },
    { id: "it1/w", it: "it1", key: "w", name: "Віджет", kind: "folder", depth: 1 },
    { id: "it1/s", it: "it1", key: "s", name: "Помилка", kind: "state", depth: 2, path: "it1/s/index.html" }],
};

test("панель превʼю будується з outline: тека видна, тип — з kind", () => {
  const r = extRows(MAN_OUTLINE, { it: "it1", page: "it1/s", expanded: new Set() });
  assert.deepEqual(r.map((x) => [x.id, x.isGroup, x.isState, x.depth]),
    [["it1/p", false, false, 0], ["it1/w", true, false, 1], ["it1/s", false, true, 2]]);
});

test("без outline (старе превʼю) — як раніше, з pages", () => {
  const { outline, ...old } = MAN_OUTLINE;
  const r = extRows(old, { it: "it1", page: "it1/p", expanded: new Set(["it1/p"]) });
  assert.deepEqual(r.map((x) => x.id), ["it1/p", "it1/s"]);
});

test("extTree з outline несе теки — сітка спускається в них", () => {
  const roots = extTree(MAN_OUTLINE, "it1");
  assert.equal(roots[0].id, "p");
  assert.equal(roots[0].children[0].kind, "folder");
  assert.equal(roots[0].children[0].children[0].id, "s");
});

const mk = (key, name, kind, depth, hasPath = kind !== "folder") => ({
  id: `it1/${key}`, it: "it1", key, name, kind, depth,
  ...(hasPath ? { path: `it1/${key}/index.html` } : {}) });
const DEEP_OUT = [
  mk("p1", "П1", "page", 0), mk("w", "В", "folder", 1), mk("s1", "С1", "state", 2),
  mk("p2", "П2", "page", 1), mk("f2", "Ф2", "folder", 2), mk("s3", "С3", "state", 3),
  mk("F", "Корінь", "folder", 0), mk("q", "Q", "page", 1), mk("sq", "SQ", "state", 2),
];
const MAN_DEEP = { ...MAN, pages: DEEP_OUT.filter((r) => r.kind !== "folder"), outline: DEEP_OUT };

test("панель і сітка «Огляду» узгоджені: ті самі id, той самий ряд кожного стану", () => {
  const ui = UI({ page: "it1/p1", expanded: new Set(DEEP_OUT.map((r) => r.id)) });
  const panel = extRows(MAN_DEEP, ui);
  assert.deepEqual(panel.map((r) => r.id), DEEP_OUT.map((r) => r.id));
  const grid = overviewRows(MAN_DEEP, ui);
  assert.deepEqual(grid.map((r) => r.title), ["П1", "П1 › П2", "Q"]);
  // ряд кожної картки = найближча сторінка-предок у панелі
  const headOf = new Map();
  grid.forEach((r) => r.cards.forEach((c) => headOf.set(c.pageId, r.cards[0].pageId)));
  assert.deepEqual([...headOf.keys()].sort(),
    DEEP_OUT.filter((r) => r.kind !== "folder").map((r) => r.id).sort());
  const stack = [];
  for (const r of DEEP_OUT) {
    while (stack.length && stack[stack.length - 1].depth >= r.depth) stack.pop();
    if (r.kind !== "folder") {
      const head = r.kind === "state" ? [...stack].reverse().find((a) => a.kind === "page") : r;
      assert.equal(headOf.get(r.id), head.id, r.id);
    }
    stack.push(r);
  }
  assert.deepEqual(panel.map((r) => r.isState), DEEP_OUT.map((r) => r.kind === "state"));
});

test("старе превʼю (без kind), три рівні: панель і сітка згодні, хто стан", () => {
  const old = [
    { id: "it1/a", it: "it1", key: "a", name: "A", depth: 0, path: "a" },
    { id: "it1/b", it: "it1", key: "b", name: "B", depth: 1, path: "b" },
    { id: "it1/c", it: "it1", key: "c", name: "C", depth: 2, path: "c" }];
  const man = { ...MAN, pages: old };
  const panel = extRows(man, UI({ page: "it1/c", expanded: new Set() }));
  const grid = overviewRows(man, UI());
  // у ряду разом із сторінкою лише ті, хто в панелі стан
  const inRow = grid.map((r) => r.cards.map((c) => c.pageId));
  const states = panel.filter((r) => r.isState).map((r) => r.id);
  assert.deepEqual(inRow.flat().filter((id) => states.includes(id)).sort(), states.sort());
  assert.deepEqual(panel.map((r) => r.isState), [false, true, false]);
  /* Онук-стан — дерево, яке `validate` відхиляє (стан без дітей): `buildRows`
     такого вузла не малює. Тут важливо лише, що панель не називає його станом. */
  assert.deepEqual(inRow, [["it1/a", "it1/b"]]);
});

test("клік по теці в превʼю — розгортання, а не перехід на неіснуючу сторінку", () => {
  assert.equal(rowAction(MAN_OUTLINE, "it1/w"), "toggle");
  assert.equal(rowAction(MAN_OUTLINE, "it1/p"), "goto");
  assert.equal(rowAction(MAN_OUTLINE, "it1/s"), "goto");
  // старе превʼю без outline та невідомий id — звичайний перехід
  assert.equal(rowAction({ pages: MAN_OUTLINE.pages }, "it1/w"), "goto");
  assert.equal(rowAction(null, "it1/w"), "goto");
});

test("«Огляд» у превʼю не дає картки для теки (картці потрібен кадр)", () => {
  const cards = overviewRows(MAN_DEEP, UI({ expanded: new Set(DEEP_OUT.map((r) => r.id)) }))
    .flatMap((r) => r.cards);
  const folders = new Set(DEEP_OUT.filter((r) => r.kind === "folder").map((r) => r.id));
  assert.ok(cards.length > 0);
  assert.deepEqual(cards.filter((c) => folders.has(c.pageId) || c.pageId === null), []);
});
