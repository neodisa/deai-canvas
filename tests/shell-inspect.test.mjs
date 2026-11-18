import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { inspectHTML } from "../app/shell-inspect.js";
import { stripComments } from "./_sources.mjs";
import { FULL_MODEL, MIN_MODEL } from "./_insp-fixtures.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const S = (o = {}) => ({ shellMode: "layout", on: true, model: null, tune: null, tuneOther: 0, tuneMissing: [], ...o });

/* ── коли панелі не місце ────────────────────────────────────────────────
   Той самий принцип, за яким зі смуги зникає кнопка інспектора в «Огляді»
   (`shell-bar.js`, `TIERS.view`): кадри полотна там — знімки (`<img>`), а не
   живий DOM, і оверлею нема на чому малювати рамки. */

test('у «Огляді» (shellMode: overview) панелі немає — навіть коли інспектор увімкнений', () => {
  assert.equal(inspectHTML(S({ shellMode: "overview", on: true })), "");
});

test("коли інспектор вимкнений (on: false) — панелі немає, і в «Макеті» теж", () => {
  assert.equal(inspectHTML(S({ shellMode: "layout", on: false })), "");
  assert.equal(inspectHTML(S({ shellMode: "overview", on: false })), "");
});

test("«Макет» + інспектор увімкнений — панель малюється", () => {
  const h = inspectHTML(S({ shellMode: "layout", on: true }));
  assert.notEqual(h, "");
});

/* ── кнопка закриття ─────────────────────────────────────────────────────
   `data-act="inspector"` — ТА САМА дія, що кнопка смуги (не друга реалізація
   «увімкнено/вимкнено» поряд із першою, див. докстрінг модуля). */

test('кнопка закриття несе "[data-act=\\"inspector\\"]" — ту саму дію, що кнопка смуги', () => {
  const h = inspectHTML(S());
  assert.match(h, /<button class="icob" data-act="inspector"/);
});

/* ── заголовок панелі ────────────────────────────────────────────────── */

test("заголовок панелі несе назву інспектора", () => {
  const h = inspectHTML(S());
  assert.match(h, /class="panel-title"/);
});

/* ── шлях до стану макета рівно один (Task 9) ─────────────────────────────
   Правило, заради якого звіт узагалі переїхав у праву панель: каскад і
   геометрію рахує РІВНО ОДИН код — `describeAll()` / `measure()` усередині
   iframe макета, єдиний, хто бачить живий DOM, — а панель лише малює готовий
   серіалізовний payload. Досі правило трималось на самій домовленості (див.
   докстрінг `shell-inspect.js`): ніщо не заважало панелі «швиденько»
   дочитати потрібне з макета самій і завести ДРУГИЙ шлях до тих самих чисел,
   який рано чи пізно розійдеться з першим.

   Сканер статичний — по сирцю, а не по поведінці: звернення до DOM у рідкісній
   гілці чи у відкладеному таймері тест поведінки пропустить, бо воно просто
   не виконається, а ґрепу однаково, як часто код працює. */

/* ⚠️ Перелік НЕ сканується деревом, і це не забутість. Тут названі рівно два
   файли — панель і її рендерер, — бо заборона нижче стосується саме їх:
   `document.` в `app/app.js` чи в оверлеї цілком законний. Рекурсивний обхід
   (`tests/_sources.mjs`) зробив би цей охоронець нездійсненним, тому спільним
   з ним лишається тільки забілювання коментарів. Ціна ручного переліку —
   третій рендерер панелі, який забудуть сюди дописати; проти неї стоїть
   `seen === 3` і маркер на кожен файл. */
const PANEL_SOURCES = [
  /* Маркер на кожен файл — те, що в ньому ТОЧНО є, і в коді, а не в коментарі.
     Без нього охоронець тихо зеленіє, щойно файл перейменують, спорожнять або
     вирізання коментарів забілить увесь сирець: сканувати стане нічого, а
     «нічого не знайдено» читається як «порушень немає». Той самий свідок, що
     `examined` у `tests/i18n-literals.test.mjs`. */
  { file: "app/shell-inspect.js", marker: /export function inspectHTML\s*\(/ },
  { file: "app/insp-panel.js", marker: /export function panelHTML\s*\(/ },
  { file: "app/insp-model.js", marker: /export function buildModel\s*\(/ },
];

/* `document.` — саме з крапкою: звернення до макета завжди йде через ЧЛЕНА
   (`document.body`, `document.querySelector`), а слово `document` без крапки
   трапляється в іменах і в прозі. `ownerDocument` і `contentWindow` — два
   обхідні шляхи до того самого документа: перший через будь-який вузол,
   другий через сам iframe. */
const BANNED = /getComputedStyle|ownerDocument|querySelector|contentWindow|document\./;

test("ні панель, ні її рендерер не торкаються DOM макета — шлях підрахунку один", () => {
  let seen = 0;
  for (const { file, marker } of PANEL_SOURCES) {
    /* Коментарі вирізаються ПЕРЕД скануванням. Сьогодні жодне із заборонених
       імен у них не стоїть — перевірено ґрепом, — але коментарі тут головна
       документація, і пояснення «чому `getComputedStyle` кличе тільки
       `inspector-dom.js`» напрошується саме в цих двох докстрінгах. Охоронець,
       який валиться на власному поясненні, змушує пояснення не писати. Ціна
       вирізання — ризик зрізати зайве (рядок із `/*`, регекспний літерал), і
       рівно проти неї стоять обидва свідки нижче. */
    const src = stripComments(readFileSync(path.join(ROOT, file), "utf8"));

    assert.match(src, marker,
      `${file} не прочитаний, перейменований або вирізання коментарів зʼїло код `
      + `— заборона нижче перевіряла б порожнечу`);
    assert.ok(src.length > 900,
      `після вирізання коментарів від ${file} лишилось ${src.length} байтів `
      + `— забілено забагато, сканувати майже нічого`);
    seen += 1;

    assert.doesNotMatch(src, BANNED,
      `${file} звертається до DOM — це другий шлях до стану макета поряд із describeAll()`);
  }

  /* Підлога — ЛІТЕРАЛ, а не `PANEL_SOURCES.length`: інакше порожній список сам
     себе й підтвердив би, і охоронець лишився б зеленим, не глянувши в жоден
     файл. */
  assert.equal(seen, 3,
    `просканованих сирців ${seen}, а не 3 — список порожній або обірваний`);
});

/* ── ПІДВАЛ панелі (Task 15, перебудований у T-39) ─────────────────────────
   Список НАКРУЧЕНОГО, записка Клоду й дві дії — унизу тієї самої вкладки, де
   крутять. Окремої вкладки «Тюнер» немає: крутити в одному місці, а надсилати
   в іншому було зайвим переходом усередині однієї роботи.

   Пакет приходить готовим (`packageJSON`, `app/tuner-model.js`) — панель його
   не рахує й не доповнює, рівно як не рахує звіт і лінійку.

   ⛔ Записку перевіряємо саме як ПОЛЕ ТЮНЕРА: `comment-layer` — окремий
   продукт, і зливати їх не можна. Тому нижче стоїть перевірка, що в розмітці
   панелі немає нічого від коментатора. */

const PKG = (o = {}) => ({
  kind: "design-canvas.tuner.recommendations", version: 1, status: "draft",
  page: "it1/holovna", note: "", editCount: 1, instructions: [],
  elements: [{ page: "it1/holovna", selector: "body > div.wrap > p.card",
    label: "p.card", trail: ["body", "div.wrap", "p.card"], text: "Картка",
    edits: [{ prop: "gap", from: "8px", to: "12px", rule: ".card", raw: "var(--sp-2)",
      token: "--sp-2", tokenValue: "8px", verdict: "token", hint: [] }] }],
  ...o,
});

const EMPTY = (o = {}) => PKG({ elements: [], editCount: 0, ...o });

test("підвал показує накопичені зміни, згруповані по елементах", () => {
  const h = inspectHTML(S({ tune: PKG() }));
  assert.match(h, /p\.card/, "немає підпису елемента");
  assert.match(h, /8px/, "немає значення ДО");
  assert.match(h, /12px/, "немає значення ПІСЛЯ");
  assert.match(h, /gap/, "немає імені властивості");
});

test("кожна зміна має свій хрестик, адресований парою елемент+властивість", () => {
  const h = inspectHTML(S({ tune: PKG() }));
  assert.match(h, /data-act="insptunedrop"[^>]*data-prop="gap"/);
  assert.match(h, /data-sel="body &gt; div\.wrap &gt; p\.card"/,
    "ключ елемента мусить доїхати в розмітку екранованим — інакше скидати нічим");
});

/* ⛔ Це ЄДИНЕ місце, де лишилось скидання однієї правки: з рядка звіту пішло
   й перекреслене «було», і кнопка `insptuneoff`, якою те «було» й було
   (T-39). Якщо хрестик зникне звідси, скидати одну правку стане нічим. */
test("скидання ОДНІЄЇ правки живе саме тут — іншого входу в нього немає", () => {
  const h = inspectHTML(S({ tune: PKG() }));
  assert.match(h, /data-act="insptunedrop"/);
  assert.doesNotMatch(h, /insptuneoff/);
});

test("«Скинути все» зʼявляється лише коли є що скидати", () => {
  assert.match(inspectHTML(S({ tune: PKG() })), /data-act="insptuneall"/);
  assert.doesNotMatch(inspectHTML(S({ tune: EMPTY() })), /data-act="insptuneall"/,
    "кнопка скидання всього на порожньому списку обіцяє дію, якої немає");
});

test("лічильник несе ОБИДВА числа — елементів і змін", () => {
  const two = PKG({ elements: [...PKG().elements, {
    page: "it1/holovna", selector: "body > h1", label: "h1", trail: ["body", "h1"],
    text: "Заголовок", edits: [
      { prop: "font-size", from: "30px", to: "64px", rule: "h1", raw: "30px",
        token: null, tokenValue: null, verdict: "hardcode", hint: [] },
      { prop: "color", from: "#000", to: "#333", rule: "h1", raw: "#000",
        token: null, tokenValue: null, verdict: "hardcode", hint: [] }],
  }], editCount: 3 });
  const h = inspectHTML(S({ tune: two }));
  const sum = h.match(/<p class="insp-tune-sum">([\s\S]*?)<\/p>/)[1];
  assert.match(sum, /2/, "немає числа елементів");
  assert.match(sum, /3/, "немає числа змін");
});

test("записка для Клода — поле ТЮНЕРА, і вона показує вже записане", () => {
  const h = inspectHTML(S({ tune: PKG({ note: "картка затісна" }) }));
  assert.match(h, /data-act="insptunenote"/);
  assert.match(h, /картка затісна/);
});

/* ⛔ Несуче обмеження, а не косметика: `comment-layer` — окремий продукт зі
   своїм каналом і своєю панеллю. Якби записка виявилась його полем, «скинути
   накручене» почало б чіпати чужі дані, а коментар колеги поїхав би Клоду як
   інструкція до коду. Перевіряємо саме РОЗМІТКУ панелі: жодного сліду
   коментатора в ній бути не мусить. */
test("записка НЕ з коментатора: жодного сліду comment-layer у розмітці панелі", () => {
  const h = inspectHTML(S({ tune: PKG({ note: "текст" }) }));
  assert.doesNotMatch(h, /comment|cl-|CommentLayer/i,
    "у панелі тюнера зʼявився слід коментатора — це окремий продукт");
});

/* Порожній підвал — це три обіцянки дії, якої немає: «0 змін», порожній
   список і кнопка «Надіслати», яка нічого не позначить. Порожній стан такий
   самий, як був до тюнера взагалі: без підвалу й без підписів-пояснень. */
test("порожній пакет НЕ малює підвалу — ні лічильника, ні записки, ні дій", () => {
  const h = inspectHTML(S({ tune: EMPTY() }));
  assert.doesNotMatch(h, /insp-tune-sum/);
  assert.doesNotMatch(h, /insptunenote/);
  assert.doesNotMatch(h, /insptuneready/);
  assert.doesNotMatch(h, /class="insp-foot"/, "порожнього підвалу немає зовсім");
});

test("записка, написана без жодної правки, підвал ТРИМАЄ", () => {
  /* Інакше текст, який дизайнер уже набрав, зник би з екрана від скидання
     останньої правки — а він про задачу цілком, а не про ту правку. */
  const h = inspectHTML(S({ tune: EMPTY({ note: "тут усе тісно" }) }));
  assert.match(h, /data-act="insptunenote"/);
  assert.match(h, /тут усе тісно/);
});

/* ── правка, якої на макеті немає, МУСИТЬ ПРО ЦЕ СКАЗАТИ ──────────────────
   ⛔ Це та сама брехня, проти якої заведена вся фіча, лише з найтихішого
   боку. Знайдено живцем 18.09.2026 на справжньому макеті (`bf360`, it6/main):
   пакет піднявся з диска, ключ елемента ніс клас, який дописує ВЛАСНИЙ скрипт
   макета, і в мить `load` селектор не збігся ні з чим. Правка лишилась у
   списку й у пакеті — а на екрані її не було.

   Правку з пакета НЕ ПРИБИРАЄМО: вона описує те, що дизайнер справді зробив,
   і мусить доїхати Клоду. Змінюється не склад списку, а те, ЩО він про неї
   стверджує.

   МУТАЦІЯ: прибрати `data-miss`/`insp-miss` у `tuneRow` — обидві перевірки
   червоніють, бо не лягла правка стає невідрізненною від накладеної. */

test("правку, яка не лягла на цей документ, рядок позначає і пояснює", () => {
  const missing = [{ selector: "body > div.wrap > p.card", prop: "gap" }];
  const h = inspectHTML(S({ tune: PKG(), tuneMissing: missing }));
  assert.match(h, /<p class="insp-chg-row" data-miss=""/,
    "рядок мусить нести стан — інакше він показує правку як живу");
  assert.match(h, /class="insp-miss"[^>]*title="[^"]*(Не лягло|Not applied)/,
    "позначка без пояснення читається як «правку загублено»");
  /* ⛔ І правка лишається в списку цілком: значення, стрілка, хрестик. */
  assert.match(h, /data-act="insptunedrop"[^>]*data-prop="gap"/);
  assert.match(h, /12px/, "правку викинули зі списку — вона мусить доїхати Клоду");
});

test("позначка «не лягло» стоїть РІВНО на тій правці, якої немає", () => {
  /* Інакше вона не означає нічого: позначене все — позначене ніщо. */
  const clean = inspectHTML(S({ tune: PKG(), tuneMissing: [] }));
  assert.doesNotMatch(clean, /data-miss/, "порожній список — позначати нічого");
  assert.doesNotMatch(clean, /insp-miss/);
  /* Чужий селектор із тією самою властивістю на цей рядок не поширюється:
     адреса правки — ПАРА (елемент + властивість), як і в хрестика скидання. */
  const other = inspectHTML(S({ tune: PKG(),
    tuneMissing: [{ selector: "body > h1", prop: "gap" }] }));
  assert.doesNotMatch(other, /data-miss/,
    "позначка поїхала на правку іншого елемента — адресується не парою");
  /* І навпаки: той самий елемент, інша властивість. */
  const prop = inspectHTML(S({ tune: PKG(),
    tuneMissing: [{ selector: "body > div.wrap > p.card", prop: "color" }] }));
  assert.doesNotMatch(prop, /data-miss/);
});

test("без поля tuneMissing підвал малюється як і раніше", () => {
  /* Поле зʼявилось пізніше за саму панель, і його відсутність — не привід
     упасти: `paintInsp` міг би не долити його з тисячі причин, а підвал у
     цьому стані мусить просто нічого не стверджувати про накладання. */
  const h = inspectHTML(S({ tune: PKG() }));
  assert.doesNotMatch(h, /data-miss/);
  assert.match(h, /data-act="insptunedrop"/);
});

/* Сторінка — МЕЖА ВИДИМОСТІ правок (`tunePage`, `app.js`), тож решта пакета
   мусить бути видимою числом. Без цього рядка дизайнер, який крутив на двох
   екранах, вирішив би, що Клоду поїде лише половина. */
test("правки з інших сторінок згадуються числом, а не зникають мовчки", () => {
  const h = inspectHTML(S({ tune: PKG(), tuneOther: 4 }));
  assert.match(h, /insp-tune-other/);
  assert.match(h, /4/);
  assert.doesNotMatch(inspectHTML(S({ tune: PKG(), tuneOther: 0 })),
    /insp-tune-other/, "нуля чужих правок згадувати нема чого");
  /* І сама згадка тримає підвал на екрані навіть тоді, коли на ЦІЙ сторінці
     не накручено нічого: інакше «ще 4 на інших сторінках» не було б де
     сказати. */
  assert.match(inspectHTML(S({ tune: EMPTY(), tuneOther: 4 })), /insp-tune-other/);
});

/* ── «Надіслати AI» = status (T-39) ────────────────────────────────────
   ⛔ Кнопка НІЧОГО НЕ НАДСИЛАЄ й нічого не зберігає: пакет лягає на диск на
   кожну правку і без неї. Вона відповідає на єдине питання, на яке читач
   пакета досі не мав відповіді: «дизайнер іще крутить чи вже закінчив». Тому
   й позначка поруч каже «чекає», а не «надіслано». */

test("дії підвалу — надіслати й скасувати, і скасувати = скинути все", () => {
  const h = inspectHTML(S({ tune: PKG() }));
  assert.match(h, /class="insp-send" data-act="insptuneready"/);
  assert.match(h, /class="insp-cancel" data-act="insptuneall"/,
    "«Скасувати» — це та сама дія, що «Скинути все»: надсилання не є подією, "
    + "а збереження не є вибором, тож скасувати тут можна лише накручене");
});

test("позначку «готово» видно РІВНО тоді, коли пакет справді ready", () => {
  const draft = inspectHTML(S({ tune: PKG() }));
  const ready = inspectHTML(S({ tune: PKG({ status: "ready" }) }));
  assert.doesNotMatch(draft, /insp-ready/,
    "чернетка, позначена готовою, — це рівно та брехня, проти якої status і завели");
  assert.match(ready, /class="insp-ready"/);
});

test("панель НЕ вирішує сама, що пакет готовий — вона лише показує поле", () => {
  /* Найдешевший спосіб зламати `status` — порахувати його в панелі
     («є правки, отже готово»). Тоді сигнал перестав би означати намір
     дизайнера, а саме наміром він і є. */
  for (const status of ["draft", undefined, "щось третє"]) {
    assert.doesNotMatch(inspectHTML(S({ tune: PKG({ status }) })), /insp-ready/,
      String(status));
  }
});

test("панель із моделлю малює панель властивостей, без моделі — лише шапку", () => {
  const withModel = inspectHTML(S({ model: FULL_MODEL() }));
  assert.match(withModel, /class="insp-name"/);
  assert.match(withModel, /data-sec="size"/);
  const bare = inspectHTML(S());
  assert.match(bare, /class="insp-top"/);
  assert.doesNotMatch(bare, /insp-sec/);
});

test("вкладок, підказок і рядка клавіш немає ніде", () => {
  for (const model of [null, FULL_MODEL(), MIN_MODEL()]) {
    const h = inspectHTML(S({ model, tune: PKG() }));
    assert.doesNotMatch(h, /insptab|insp-tabs|insp-keys|<kbd|insp-hint/);
  }
});

test("підвал зʼявляється лише коли є що показати — порожній блок із лінією не малюється", () => {
  assert.doesNotMatch(inspectHTML(S({ model: MIN_MODEL() })), /class="insp-foot"/);
  assert.match(inspectHTML(S({ model: MIN_MODEL(), tune: PKG() })), /class="insp-foot"/);
});
