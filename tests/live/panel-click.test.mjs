/**
 * План A, Task 3: панель шарів згортається кліком по ПОРОЖНЬОМУ місцю й
 * розгортається кліком по будь-якому місцю рейки. Слова власника: «еще бы
 * хотелось бы, чтобы эта левая панель закрывалась по пустому месту. И
 * открывалась тоже на любое место нажав, чтобы удобнее было с ней работать».
 *
 * ЧОМУ це живий тест, а не юніт. Розмітку тримають юніти
 * (`tests/shell-panel.test.mjs`): заповнювач є, він порожній, стоїть після
 * рядків і перед блоком кадрів. Але вся фіча тримається на ОДНІЙ речі, якої
 * в рядку HTML не видно: `ev.target.closest('[data-act]')` у делегації
 * (`wirePanelEvents`, `app.js`) вертає НАЙБЛИЖЧИЙ предок із дією. Тому клік
 * по рядку, каретці, «⋯», «+», кнопці зʼємки чи тихому рядку кадрів
 * знаходить СВОЮ дію й до панелі не доходить — задарма, без жодної перевірки
 * «а чи не по кнопці я клікнув» і без списку винятків. Виміряти це можна
 * лише справжнім кліком у справжньому DOM.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»:
 *
 *   A. порожнє місце     — `.panel-fill[data-act="panel"]` усередині
 *      згортає                `.panel-body` (`shell-panel.js`) + `flex:1` на
 *                             ньому (`styles.css`). Прибери `data-act` —
 *                             клік нічого не знайде (тіло панелі дії не
 *                             несе) і панель не згорнеться. Прибери `flex:1`
 *                             — заповнювач стиснеться в 24px, і клік у
 *                             порожнє місце влучить у мертве тіло: тест
 *                             падає ще на перевірці самої точки, з іменем
 *                             елемента, у який влучив.
 *   B. будь-яке місце    — обгортка `.panel-rail[data-act="panel"]`. Прибери
 *      рейки розгортає        її — клікатиме лише сама стрілка.
 *   C. клік по рядку     — `data-act="page"` на рядку. Прибери — клік по
 *      вибирає сторінку       рядку піде вгору по дереву; сторінка не
 *                             виберeться (а панель однаково не згорнеться:
 *                             рядок лежить ПОЗА заповнювачем — саме тому тут
 *                             міряється ДІЯ, а не лише «не згорнулась»).
 *   D. клік по «⋯»       — `data-act="pagemenu"` на кнопці. Прибери —
 *      відкриває меню         найближчим предком із дією стає САМ РЯДОК
 *                             (`data-act="page"`), меню не відкриється, і
 *                             тест почервоніє. Це й є доказ, що тест стереже
 *                             МЕХАНІКУ (котра дія знайшлась), а не лише
 *                             «панель не згорнулась».
 *   E. клік по «+»       — `data-act="newpage"`. Прибери — замість запиту
 *      питає імʼя             імені клік знайде дію тіла панелі (немає) чи
 *                             заповнювача, залежно від того, куди його
 *                             перенесли.
 *   F. клік по тихому    — `data-act="shotsopen"` на рядку `.shots-quiet`
 *      рядку кадрів           (Task 2). Прибери — блок не розгорнеться.
 *      розгортає блок         Блок кадрів лежить ПОЗА заповнювачем, тож
 *                             панель і тут не згорнеться — і саме тому
 *                             міряється розгортання блоку.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { runShoot } from "../../bin/shoot.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 10090;
const VIEW = { width: 1400, height: 900 };
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body><h1>${id}</h1></body></html>`;

/* Сторінка для F — з градієнтом, і це не косметика: порожня сторінка
   стискається у WebP нижче `BYTES_FLOOR`, і КОЖЕН кадр дістає `problem`
   «порожня сторінка», тобто лишається застарілим за побудовою. Виміряно
   першим прогоном цього файлу: з простою `PAGE` вище тихий рядок не
   зʼявляється НІКОЛИ (`stale: true, problem: "знімок 3944 байт — це порожня
   сторінка"` у манифесті), і тест падав не на панелі, а на неможливості
   свіжої ітерації. Та сама причина й той самий градієнт, що в
   `tests/live/autoshoot.test.mjs` і `shell.test.mjs`. */
const HEAVY_PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:1200px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)"><h1>${id}</h1></body></html>`;

const collapsed = (page) => page.evaluate(() =>
  document.body.classList.contains("panel-collapsed"));

/** Свіжа вкладка з відкритою панеллю й намальованим деревом. `newPage()` дає
 *  СВІЙ контекст, тобто чистий `localStorage`: `dc-panel-collapsed`,
 *  записаний попереднім підтестом, не сміє вирішувати за наступний. */
async function openApp(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator("#pages-panel .row").first().waitFor();
  return page;
}

/**
 * Точка ПІД останнім рядком дерева — те саме «пустое место», про яке просив
 * власник, знайдене вимірюванням, а не селектором: `elementFromPoint` каже,
 * у що справді влучить мишка, і разом із `closest('[data-act]')` — яку дію
 * знайде делегація. Без цієї перевірки тест міг би зелено клікати по
 * елементу, якого користувач ніколи не бачить.
 */
const spotBelowTree = (page) => page.evaluate(() => {
  const rows = [...document.querySelectorAll("#pages-panel .row")];
  const last = rows[rows.length - 1].getBoundingClientRect();
  const panel = document.getElementById("pages-panel").getBoundingClientRect();
  const x = Math.round(panel.left + panel.width / 2);
  const y = Math.round(last.bottom + 30);
  const el = document.elementFromPoint(x, y);
  return {
    x, y,
    cls: el ? String(el.className) : null,
    tag: el ? el.tagName : null,
    act: el?.closest("[data-act]")?.dataset.act ?? null,
    inPanel: !!el?.closest("#pages-panel"),
  };
});

/** Те саме для середини рейки: рівно посередині її висоти, тобто далеко і від
 *  стрілки вгорі, і від значка зʼємки внизу. */
const spotMidRail = (page) => page.evaluate(() => {
  const p = document.getElementById("pages-panel").getBoundingClientRect();
  const x = Math.round(p.left + p.width / 2);
  const y = Math.round(p.top + p.height / 2);
  const el = document.elementFromPoint(x, y);
  return {
    x, y,
    cls: el ? String(el.className) : null,
    tag: el ? el.tagName : null,
    act: el?.closest("[data-act]")?.dataset.act ?? null,
    inPanel: !!el?.closest("#pages-panel"),
  };
});

test("панель згортається кліком по порожньому й розгортається кліком по рейці", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  await t.test("A/B. порожнє місце згортає, будь-яке місце рейки розгортає", async () => {
    const page = await openApp(browser, url);
    assert.equal(await collapsed(page), false, "панель почала життя згорнутою — перевірка недійсна");

    const spot = await spotBelowTree(page);
    assert.ok(spot.inPanel, `точка (${spot.x},${spot.y}) взагалі не в панелі: ${spot.tag}.${spot.cls}`);
    assert.equal(spot.act, "panel",
      `порожнє місце під деревом не веде до дії «панель»: влучили в ${spot.tag}.${spot.cls}, дія «${spot.act}»`);
    await page.mouse.click(spot.x, spot.y);
    await page.waitForFunction(() => document.body.classList.contains("panel-collapsed"),
      null, { timeout: 3000 });

    const rail = await spotMidRail(page);
    assert.notEqual(rail.tag, "BUTTON",
      "клікаємо в порожнє місце рейки, а не в кнопку — інакше перевірка про кнопку, а не про рейку");
    assert.equal(rail.act, "panel",
      `середина рейки не веде до дії «панель»: влучили в ${rail.tag}.${rail.cls}, дія «${rail.act}»`);
    await page.mouse.click(rail.x, rail.y);
    await page.waitForFunction(() => !document.body.classList.contains("panel-collapsed"),
      null, { timeout: 3000 });
    await page.close();
  });

  await t.test("C. клік по рядку сторінки вибирає її, а не згортає панель", async () => {
    const page = await openApp(browser, url);
    /* Друга сторінка фікстури: перша вже обрана типово, і клік по обраній —
       свідомий ноп (`PANEL_ACTIONS.page`), тобто перевірка ні про що. */
    await page.locator('[data-page="poshuk"]').click();
    await page.waitForFunction(() =>
      document.querySelector("#pages-panel .row--sel")?.dataset.page === "poshuk",
    null, { timeout: 3000 });
    assert.equal(await collapsed(page), false, "клік по рядку сторінки згорнув панель");
    await page.close();
  });

  await t.test("D. клік по «⋯» відкриває меню, а не згортає панель", async () => {
    const page = await openApp(browser, url);
    /* Цілимось у КЛАС (`.row-more`), а не в `[data-act="pagemenu"]`: інакше
       мутація «прибрати `data-act` із «⋯»» валила б тест на «локатор нічого
       не знайшов», тобто на власному селекторі, а не на механіці. За класом
       клік ВІДБУВАЄТЬСЯ, і `closest('[data-act]')` знаходить найближчого
       предка з дією — САМ РЯДОК (`data-act="page"`): меню не відкривається,
       і тест червоніє саме на цьому. Виміряно мутацією 02.09.2026. */
    await page.locator("#pages-panel .row-more").first().click();
    await page.locator("#cv-ctx").waitFor({ timeout: 3000 });
    assert.equal(await collapsed(page), false, "клік по «⋯» згорнув панель");
    await page.keyboard.press("Escape");
    await page.close();
  });

  await t.test("E. клік по «+» питає імʼя сторінки, а не згортає панель", async () => {
    const page = await openApp(browser, url);
    /* Та сама причина, що в D: цілимось у «+» так, як його бачить око
       (`.tree-head .icob`), а не за його ж дією. */
    await page.locator("#pages-panel .tree-head .icob").click();
    await page.locator(".cv-ask-scrim").waitFor({ timeout: 3000 });
    assert.equal(await collapsed(page), false, "клік по «+» згорнув панель");
    await page.keyboard.press("Escape");
    await page.close();
  });
});

/**
 * G. Ціна заповнювача: `.panel-body` стала flex-колонкою (у блоковому
 * контейнері дитина не може дорости до вільної висоти). У колонці рядки
 * дерева типово СТИСКАЮТЬСЯ замість того, щоб скролитись — `flex-shrink:1`, —
 * тож довге дерево втратило б скрол і показало б усі сторінки сплющеними.
 * Від цього стоїть `.panel-body > *{flex:none}`, і саме результат стереже цей
 * тест: 40 сторінок у вікні 900px гарантовано не влазять.
 *
 * Мутації, якими виміряно, що тест НЕ вакуумний (обидві — 02.09.2026):
 *   · прибрати `> *{flex:none}` — тест ЗЕЛЕНИЙ. Рядок тримає свої 28px
 *     власним вмістом: каретка й «⋯» самі по 28px, тобто min-content рядка й
 *     є 28. Записано тут навмисно: інакше наступний читач вирішив би, що
 *     охоронець стереже саме цей рядок CSS, і зняв би його «як зайвий».
 *   · прибрати `> *{flex:none}` І додати дітям `min-height:0` (звична в
 *     `styles.css` приправа до flex-колонок, тобто дуже ймовірний наступний
 *     крок) — рядок сплющується до 16.45px, тест ЧЕРВОНИЙ саме на цьому.
 */
test("G. довге дерево скролиться, а не сплющується — заповнювач не з'їв рядки", async (t) => {
  const pages = Array.from({ length: 40 }, (_, i) => `p${i + 1}`);
  const { dir } = taskFixture({ html: PAGE, pages });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 60 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator("#pages-panel .row").first().waitFor();

  const m = await page.evaluate(() => {
    const body = document.querySelector("#pages-panel .panel-body");
    const rows = [...document.querySelectorAll("#pages-panel .row")];
    return {
      rows: rows.length,
      minRow: Math.min(...rows.map((r) => r.getBoundingClientRect().height)),
      scrollH: body.scrollHeight, clientH: body.clientHeight,
    };
  });
  assert.equal(m.rows, 40, "перевірка недійсна — дерево не намалювало всі сторінки");
  assert.equal(m.minRow, 28, `рядок сплющився до ${m.minRow}px замість 28 — колонка стиснула дерево`);
  assert.ok(m.scrollH > m.clientH,
    `тіло панелі не скролиться (${m.scrollH} ≤ ${m.clientH}) — 40 рядків не влазять у 900px, отже їх стиснули`);
});

/**
 * F. Тихий блок кадрів (Task 2) — окремим тестом, бо він існує ЛИШЕ при
 * підтвердженій свіжості: кадри мусять справді лежати на диску, а «Огляд» —
 * порахувати їх свіжими. `runShoot` тут той самий прийом, що `preShoot` у
 * `tests/live/shell.test.mjs`: один справжній прогін замість автозʼємки на
 * кожному вході.
 *
 * Перевіряється саме ПАРА: клік по тихому рядку розгортає блок кадрів І не
 * згортає панель. Блок кадрів лежить поза заповнювачем, тож друга половина
 * зелена й сама по собі — тому першою половиною й тримається тест: без
 * власної дії рядок нічого б не розгорнув.
 */
test("F. клік по тихому рядку кадрів розгортає блок, а панель лишає відкритою", async (t) => {
  const { dir, it1 } = taskFixture({ html: HEAVY_PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  await runShoot({
    dir: it1, it: "it1", url, all: true, now: "24.08.2026 12:00",
    launch: () => chromium.launch(),
    onProgress: () => {},
  });

  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator('[data-act="mode"][data-val="overview"]').click();
  await page.locator(".shots-quiet").waitFor({ timeout: 30000 });

  await page.locator(".shots-quiet").click();
  await page.locator('#pages-panel [data-act="shoot"]').waitFor({ timeout: 5000 });
  assert.equal(await collapsed(page), false, "клік по тихому рядку кадрів згорнув панель");
});
