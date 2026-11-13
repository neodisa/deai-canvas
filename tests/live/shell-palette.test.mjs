/**
 * Живі перевірки ⌘K палітри команд (Task 6 Плану B). Юніт
 * (`tests/shell-palette.test.mjs`) перевіряє лише РОЗМІТКУ чистих функцій
 * реєстру (`paletteActions`/`paletteHTML`/`paletteListHTML`/`keysHTML`) — не
 * те, що на клавіші й кліки в бою щось РЕАГУЄ, і не те, що виконання йде
 * через СПРАВЖНІ `BAR_ACTIONS`/`PANEL_ACTIONS`, а не мовчки нічого не робить.
 * Саме це — і рівно це — перевіряють живі тести нижче.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»:
 *
 *   A (відкриття й фільтр)  — `Control+K` мусить відкрити палітру ОДРАЗУ
 *                             (фокус у полі пошуку без жодного `waitFor`
 *                             понад мінімальний), а набір тексту в полі —
 *                             звузити список. Запобіжник: обробник `keydown`
 *                             біля кінця `app.js` (`meta && key==='k'`) і
 *                             слухач `input` в `ensureOverlayEl()`. Прибери
 *                             перший — `Control+K` не робить нічого; прибери
 *                             другий — поле приймає символи, а список не
 *                             звужується (візуально «зламаний пошук»).
 *   B (Enter ВИКОНУЄ дію)   — найважливіша перевірка задачі: Enter на пункті
 *                             «Планшет» мусить не лише ЗАКРИТИ палітру, а й
 *                             реально перемкнути `vp` на `tablet`
 *                             (`aria-pressed` сегмента смуги). Запобіжник:
 *                             рядок `(BAR_ACTIONS[a.act] ||
 *                             PANEL_ACTIONS[a.act])?.(a.val)` у
 *                             `execPaletteAction`. Мутація «лиши тільки
 *                             `closeOverlay()`, прибери виклик дії» ловиться
 *                             РІВНО тут: палітра так само закриється (перша
 *                             половина твердження пройде), а `aria-pressed`
 *                             лишиться на `desktop` — друга половина впаде.
 *                             Перевірка БЕЗ `waitFor`/таймауту: увесь шлях
 *                             `execPaletteAction → BAR_ACTIONS.vp →
 *                             setViewport → syncViewportBar` синхронний,
 *                             тож стан мусить бути готовий одразу, як
 *                             `keyboard.press` повертає керування (той самий
 *                             прийом, що вже стереже A/C у
 *                             `tests/live/shell-inspect.test.mjs`, — з
 *                             таймаутом мутація лишалась би непоміченою,
 *                             якби десь у ланцюжку зʼявився `setTimeout`).
 *   C (Esc — драбинка)      — Esc закриває ЛИШЕ палітру, не чіпаючи іншого
 *                             стану екрана (тут — режим «Огляд», в який
 *                             навмисно перемкнулись ПЕРЕД відкриттям палітри,
 *                             щоб «нічого не змінилось» не збіглося з
 *                             випадковим типовим станом). Запобіжник —
 *                             capture-слухач `Escape` наприкінці `app.js`
 *                             (докстрінг секції «Драбинка Escape»).
 *   D (мова)                — вибір «English» зі списку мусить перемалювати
 *                             ОБИДВІ поверхні відразу: заголовок панелі
 *                             шарів (`Шари`→`Layers`) і підпис кнопки
 *                             публікації в смузі (`Опублікувати`→`Publish`).
 *                             Запобіжник: `switchLang` кличе `paintBar()` і
 *                             `renderPanel()` ОБИДВА, синхронно. Мутація
 *                             «забути один із двох викликів» ловиться тим,
 *                             що перевірка дивиться в ОБИДВІ поверхні, а не
 *                             в одну.
 *   E (`?` — довідка клавіш)— відкриває `.keysheet` із рядком `⌘K`; Esc
 *                             закриває так само, як і саму палітру (той
 *                             самий `paletteOverlay`/capture-слухач).
 *   F (⌥M — режим)          — акорд, який довідка обіцяла пів релізу, а
 *                             обробника не мав НІ ДЕ (передрелізний аудит
 *                             02.09.2026). Юніт
 *                             `tests/shell-palette.test.mjs` стереже ПАРУ
 *                             «підказка ↔ прив'язка» статично; тут —
 *                             єдина перевірка, що клавіша справді МІНЯЄ
 *                             екран. Запобіжник: гілка `ev.altKey && !meta`
 *                             у слухачі `keydown` наприкінці `app.js`.
 *   G (⌘\ — панель шарів)   — те саме для другого загубленого акорда, і
 *                             навмисно в ДВА боки (згорнути й розгорнути):
 *                             односторонній тумблер лишав би дизайнера в
 *                             рейці без дороги назад із клавіатури.
 *                             Запобіжник: гілка `meta && !ev.altKey` там же
 *                             + `PANEL_ACTIONS.panel`.
 *
 * ⛔ Свідомо НЕ дублюємо тут: перевірку «сама дія працює» для КОЖНОГО
 * `BAR_ACTIONS`/`PANEL_ACTIONS` (це вже стереже `tests/live/shell-bar.test.mjs`
 * і `tests/live/shell-panel.test.mjs`) — палітра лише ДРУГИЙ ШЛЯХ до тих самих
 * дій, і перевіряти тут заново кожну з них означало б повторювати чужий набір.
 * Один `vp` (перевірка B) досить, щоб довести: шлях виконання СПРАВЖНІЙ.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* Свій `portBase`: сусідні живі набори — shell-bar=9390, shell-panel=9490,
   shell-inspect=9590, viewport=9090, overview-viewports=9290. */
const PORT_BASE = 9690;
const VIEW = { width: 1400, height: 900 };

const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:900px"><h1>${id}</h1></body></html>`;

/** Макет, готовий до роботи, смуга вже намальована. */
async function openCanvas(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator('#bar [data-act="mode"]').first().waitFor();
  return page;
}

test("A. Control+K відкриває палітру з фокусом у полі; набір тексту фільтрує", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  assert.equal(await page.locator(".pal").count(), 0, "палітра не мусить бути видима заздалегідь");
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible", timeout: 2000 });
  assert.ok(
    await page.locator("#palq").evaluate((el) => el === document.activeElement),
    "поле пошуку мусить отримати фокус одразу після відкриття",
  );

  const before = await page.locator(".pal-it").count();
  assert.ok(before > 10, `у реєстрі лише ${before} пунктів — це не повний список дій`);

  await page.fill("#palq", "мова");
  await page.waitForFunction(
    () => document.querySelectorAll(".pal-it").length === 2,
    null, { timeout: 2000 },
  );
  const texts = await page.$$eval(".pal-it", (els) => els.map((e) => e.textContent));
  assert.ok(texts.some((s) => s.includes("українська")), "серед відфільтрованого немає пункту «українська»");
  assert.ok(texts.some((s) => s.includes("English")), "серед відфільтрованого немає пункту «English»");
});

test("A2. кнопки палітри в смузі більше нема (0.25.0) — єдиний вхід акорд, і мова в палітрі є", async (t) => {
  /* Із 0.25.0 смуга задачі схудла: кнопку палітри прибрано, ⌘K/Ctrl+K лишився.
     Тест A вище доводить акорд; тут — що двері справді прибрані (не загубились
     у DOM прихованими) і що акорд знаходить мову інтерфейсу. */
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 50 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  assert.equal(await page.locator('#bar [data-act="palette"]').count(), 0, "кнопка палітри лишилась у смузі");
  assert.equal(await page.locator(".pal").count(), 0, "палітра не мусить бути видима заздалегідь");
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible", timeout: 10000 });
  assert.ok(
    await page.locator("#palq").evaluate((el) => el === document.activeElement),
    "акорд мусить дати фокус у полі",
  );

  await page.fill("#palq", "мова");
  await page.waitForFunction(
    () => document.querySelectorAll(".pal-it").length === 2,
    null, { timeout: 2000 },
  );
  const texts = await page.$$eval(".pal-it", (els) => els.map((e) => e.textContent));
  assert.ok(texts.some((x) => x.includes("українська")) && texts.some((x) => x.includes("English")),
    "у палітрі, відкритій акордом, немає мови інтерфейсу — саме того, що шукали");
});

test("B. Enter виконує САМУ дію (перемикає вьюпорт на планшет), а не лише закриває палітру", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 10 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  assert.equal(
    await page.locator('#bar [data-act="vp"][data-val="tablet"]').getAttribute("aria-pressed"),
    "false", "перевірка недійсна: планшет уже активний до будь-якої дії",
  );

  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "планшет");
  await page.waitForFunction(
    () => document.querySelectorAll(".pal-it").length === 1,
    null, { timeout: 2000 },
  );
  await page.keyboard.press("Enter");

  /* БЕЗ waitFor/таймауту: `execPaletteAction → BAR_ACTIONS.vp → setViewport
     → syncViewportBar` — увесь ланцюжок синхронний (жодного `await` на
     цьому шляху), тож до моменту, коли `keyboard.press` повертає керування,
     обидва наслідки мусять уже статись. Мутація «лиши тільки закриття
     оверлея» проходить першу перевірку (палітра й справді зникає) і падає
     на другій. */
  assert.equal(await page.locator(".pal").count(), 0, "Enter мусив закрити палітру одразу");
  assert.equal(
    await page.locator('#bar [data-act="vp"][data-val="tablet"]').getAttribute("aria-pressed"),
    "true", "Enter мусив виконати САМУ дію (vp→tablet) — палітра лише закрилась, дію не виконано",
  );
});

test("C. Esc закриває палітру драбинкою, не чіпаючи іншого стану екрана", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 20 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  // Свідомо НЕ типовий стан — щоб «нічого не змінилось» не збіглось випадково
  // зі стартовим станом смуги.
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.locator('#bar [data-act="mode"][data-val="overview"][aria-pressed="true"]').waitFor();

  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.keyboard.press("Escape");

  assert.equal(await page.locator(".pal").count(), 0, "Esc мусив закрити палітру одразу");
  assert.equal(
    await page.locator('#bar [data-act="mode"][data-val="overview"]').getAttribute("aria-pressed"),
    "true", "Esc не мав чіпати режим — це драбинка, а не вимикач усього",
  );
});

test("D. перемикання мови зі списку міняє підписи ОБОХ поверхонь — смуги й панелі — одразу", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 30 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  // `.panel-title` малює `text-transform:uppercase` (styles.css) — рендер
  // мовою UA/EN, а не сирий DOM-текст: порівнюємо в нижньому регістрі, щоб
  // перевірка стежила за МОВОЮ, а не випадково за регістром CSS.
  await page.locator("#pages-panel .panel-title").waitFor();
  assert.equal((await page.locator("#pages-panel .panel-title").innerText()).trim().toLowerCase(), "шари");
  assert.equal((await page.locator('#bar [data-act="publish"] .lbl-pub').innerText()).trim(), "Опублікувати");

  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "english");
  await page.waitForFunction(
    () => document.querySelectorAll(".pal-it").length === 1,
    null, { timeout: 2000 },
  );
  await page.keyboard.press("Enter");

  // switchLang кличе paintBar()/renderPanel() синхронно — без waitFor.
  assert.equal((await page.locator("#pages-panel .panel-title").innerText()).trim().toLowerCase(), "layers",
    "заголовок панелі не перемалювався новою мовою одразу");
  assert.equal((await page.locator('#bar [data-act="publish"] .lbl-pub').innerText()).trim(), "Publish",
    "підпис смуги не перемалювався новою мовою одразу");
});

test("E. ? відкриває довідку клавіш; Esc закриває її так само, як палітру", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  // Свіжий рендер: `document.activeElement` — `body` (не INPUT/SELECT), тож
  // клацати нема чого й нема куди — клік по `#stage` натомість влучає в
  // iframe макета (`#frame` покриває всю сцену) і переносить фокус ТУДИ, де
  // `?` уже не долетить до слухача батьківського документа взагалі (те саме
  // структурне обмеження, що не дає клавішам інспектора вирватись з iframe
  // назовні, — докстрінг секції «Драбинка Escape» вище в `app.js`).
  await page.keyboard.press("?");
  await page.locator(".keysheet").waitFor({ state: "visible", timeout: 2000 });
  assert.match(await page.locator(".keysheet").innerText(), /⌘K/);

  await page.keyboard.press("Escape");
  assert.equal(await page.locator(".keysheet").count(), 0, "Esc мусив закрити довідку клавіш");
});

test("F. ⌥M перемикає режим — акорд, який довідка обіцяла без обробника", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 60 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);

  /* Перевірка мусить бути дійсною: «Огляд» не сміє бути активним ДО акорда,
     інакше зелений колір нічого не значив би (той самий прийом, що в B). */
  assert.equal(
    await page.locator('#bar [data-act="mode"][data-val="overview"]').getAttribute("aria-pressed"),
    "false", "перевірка недійсна: «Огляд» уже активний до будь-якої дії",
  );

  /* Жодного кліку перед натиском: клік по сцені переносить фокус у рамку
     макета, і клавіша до слухача батьківського документа не долітає взагалі
     (те саме структурне обмеження, що описане у перевірці E). */
  await page.keyboard.press("Alt+m");

  /* ТУТ waitFor доречний, на відміну від B: `BAR_ACTIONS.mode` асинхронна —
     вхід у «Огляд» чекає на `freshen()` (мережа), тобто стан не може бути
     готовий у момент повернення `keyboard.press`. Мутація «прибрати гілку
     ⌥M» усе одно червоніє: акорд не робить нічого, і чекати нема на що. */
  await page.locator('#bar [data-act="mode"][data-val="overview"][aria-pressed="true"]')
    .waitFor({ timeout: 10000 });

  // І назад тим самим акордом — тумблер, а не одностороння дорога.
  await page.keyboard.press("Alt+m");
  await page.locator('#bar [data-act="mode"][data-val="layout"][aria-pressed="true"]')
    .waitFor({ timeout: 10000 });
});

test("G. ⌘\\ згортає й розгортає панель шарів", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 70 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await openCanvas(browser, url);
  await page.locator("#pages-panel .row").first().waitFor();

  /* `body.panel-collapsed` — той самий маркер, яким живий тест рейки
     (`tests/live/shell-panel.test.mjs`) перевіряє клік по стрілці: акорд
     мусить приводити екран у ТОЙ САМИЙ стан, а не у свій власний. */
  assert.ok(
    !await page.evaluate(() => document.body.classList.contains("panel-collapsed")),
    "перевірка недійсна: панель уже згорнута до будь-якої дії",
  );

  await page.keyboard.press("Control+\\");
  await page.waitForFunction(() => document.body.classList.contains("panel-collapsed"),
    null, { timeout: 10000 });
  // Дерево в рейці не малюється взагалі — той самий інваріант, що в `shell-panel`.
  assert.equal(await page.locator("#pages-panel .row").count(), 0,
    "рейка чомусь показує дерево — акорд згорнув панель не тим шляхом, що стрілка");

  await page.keyboard.press("Control+\\");
  await page.waitForFunction(() => !document.body.classList.contains("panel-collapsed"),
    null, { timeout: 10000 });
  assert.ok(await page.locator("#pages-panel .row").count() > 0,
    "розгортання акордом не повернуло дерево");
});
