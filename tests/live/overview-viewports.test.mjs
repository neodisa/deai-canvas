/**
 * Живі перевірки вьюпортів у «Огляді»: справжній сервер, справжній Chromium,
 * справжня зʼємка. Юніти перевіряють ключі й фільтри; тут — те, чого чистий
 * модуль не бачить: що ширина справді доїжджає до браузера, що автозʼємка
 * підхоплює нову ширину сама, і що прогін однієї ширини не зʼїдає чужі кадри.
 *
 * Мапа «перевірка → запобіжник», знята мутаційно (прибери охорону — подивись,
 * чи червоніє). Без неї «зелено» не означає нічого:
 *
 *   A (мобайл дає кадри 375) — прокид `--vp` у `_shoot` (`app/serve.py`). Мутація
 *                              «не додавати --vp в argv» червонить A, D і E.
 *                              ⚠️ Симптом ВИМІРЯНИЙ, і він не той, що
 *                              напрошується: не «кадр 1280 під іменем @375», а
 *                              «кадр @375 не зʼявляється взагалі» — дитина без
 *                              прапорця рахує свіжість типової ширини, там усе
 *                              свіже, і знімати їй нічого. Тобто фіча стає
 *                              інертною, а не бреше про ширину.
 *   B (автозʼємка сама)      — `maybeAutoShoot()` у `setCanvasViewport`. Мутація
 *                              «прибрати виклик» червонить A, D і E: перемкнув —
 *                              і сидиш із порожнім полотном, поки не натиснеш
 *                              кнопку руками. Виміряно.
 *   C (десктоп не перезнімає) — ⚠️ ПЕРЕВІРКА ПОВЕДІНКИ, НЕ ОХОРОНЕЦЬ, і сказано
 *                              це тут, щоб наступний читач не подумав інакше.
 *                              Спершу вона підписувалась як охоронець `frameKey`
 *                              («не додає суфікса типовій ширині»), але під
 *                              власною мутацією (суфікс завжди) лишилась ЗЕЛЕНОЮ:
 *                              у межах одного прогону засів і читання йдуть через
 *                              ту саму функцію, тобто стан самоузгоджений і
 *                              підміна імен непомітна. Обіцянку «без міграції»
 *                              стереже юніт «манифест СТАРОГО формату (без
 *                              суфікса) не вважається застарілим» у
 *                              `tests/shoot-check.test.mjs`: там манифест пишеться
 *                              РУКАМИ, тож мутація не може переписати й засів.
 *                              Тут лишається чесне: повернення на вже зняту
 *                              ширину не замовляє нового прогону.
 *   D (чужі ширини цілі)     — ⛔ ЦЕНТРАЛЬНИЙ ІНВАРІАНТ. `stampsFor` віддає
 *                              ключі ВСІХ ширин, бо `markStale` видаляє з
 *                              манифеста кожен запис, чийого id немає в
 *                              `stamps`. Мутація «віддавати лише поточну
 *                              ширину» — найприродніша реалізація вьюпортів —
 *                              червонить A, D і E (виміряно).
 *                              ⚠️ Симптом ЖИВОЇ перевірки не той, що напрошується:
 *                              не «десктопні записи стерто», а «мобільні кадри
 *                              не зʼявляються взагалі» — бо `stale` фільтрується
 *                              по тих самих `stamps`, і знімати стає нічого.
 *                              Саме СТИРАННЯ ловить юніт у `shoot-check.test.mjs`
 *                              («зʼємка мобайла лишає десктопні записи
 *                              недоторканими»): він червоніє з `actual: undefined`
 *                              на десктопному записі. Два боки одного інваріанта,
 *                              і жоден не зайвий: юніт бачить втрату даних, живий —
 *                              що фіча стає інертною.
 *   E (флоу на мобайлі)      — `cardW()` у виклику `flowLayout`. Мутація
 *                              «повернути сталу 1280» червонить ТІЛЬКИ E (A, C, D
 *                              лишаються зеленими) — єдиний ексклюзивний охоронець
 *                              у цьому файлі. Виміряно; діагностика на живому
 *                              графі дала колонки 200 і 790 при картках 375,
 *                              тобто зазор рівно GAP, а зі сталою 1280 друга
 *                              колонка стояла б на 1680.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { readManifest } from "../../bin/shots-manifest.mjs";
import { CANVAS_W } from "../../app/viewport.js";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 9290;
const VIEW = { width: 1400, height: 900 };

/* Градієнт, а не порожня сторінка: порожня стискається у WebP нижче
   `BYTES_FLOOR`, і кожен кадр діставав би `problem` «порожня сторінка» — тоді
   «свіжої ширини» не існувало б і перевірка C не мала б про що говорити.
   Ширина навмисно НЕ фіксована: сторінка мусить виглядати по-різному в 1280 і
   375, інакше байти збіглися б і `sha` не розрізняв би ширини. */
const PAGE = (title) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="margin:0;height:1200px;background:repeating-linear-gradient(37deg,`
  + `#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)">`
  + `<h1 style="margin:0;font:700 40px system-ui">${title}</h1></body></html>`;

const isShootPost = (req) => req.method() === "POST"
  && new URL(req.url()).pathname === "/api/shoot"
  && !/"check"\s*:\s*true/.test(req.postData() || "");

/** Тіла всіх СПРАВЖНІХ зʼємок, які замовила ця вкладка. */
function shootOrders(page) {
  const posts = [];
  page.on("request", (req) => { if (isShootPost(req)) posts.push(req.postData()); });
  return posts;
}

// Панель шарів (Task 4 Плану B): `#pp-shoot` більше не існує — кнопка
// зʼємки тепер `[data-act="shoot"]` усередині `#pages-panel`.
const SHOOT_BTN = '#pages-panel [data-act="shoot"]';

const running = (page, timeout = 30000) => page.waitForFunction(
  () => /^Стоп/.test(document.querySelector('#pages-panel [data-act="shoot"]')?.textContent || ""),
  null, { timeout });

const runEnded = (page, timeout = 180000) => page.waitForFunction(
  (sel) => !/^Стоп/.test(document.querySelector(sel)?.textContent || ""),
  SHOOT_BTN, { timeout });

/* Смуга (Task 3): перемикач «як дивлюсь» — сегмент із двох окремих кнопок
   (`[data-act="mode"]`), не перемикач `#view-toggle`; пресети ширини — не
   `[data-vp="…"]`, а `[data-act="vp"][data-val="…"]`. */
const toOverview = (page) => page.locator('[data-act="mode"][data-val="overview"]');

async function openApp(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await toOverview(page).waitFor();
  return page;
}

/** Зайти в «Огляд» і дочекатись, поки автозʼємка (якщо є) добіжить. */
async function overview(page) {
  await toOverview(page).click();
  await page.waitForFunction(() => !document.getElementById("canvas").hidden,
                             null, { timeout: 15000 });
  await runEnded(page);
}

/**
 * Перемкнути ширину полотна сегментом і дочекатись кінця прогону.
 *
 * `expectRun` не для краси: `runEnded` — це «кнопка НЕ каже Стоп», тобто одразу
 * після кліку воно істинне, поки прогін ще не встиг початись. Без очікування
 * старту перевірка проскакувала повз усю зʼємку за 300мс і потім дивувалась,
 * що кадрів немає. Там, де прогону не має бути (повернення на вже зняту
 * ширину), чекати старту не можна — його не буде за визначенням.
 */
async function switchTo(page, preset, { expectRun = false } = {}) {
  await page.locator(`[data-act="vp"][data-val="${preset}"]`).click();
  if (expectRun) await running(page, 20000);
  await runEnded(page);
}

/**
 * Дочекатись, поки кадр зʼявиться в манифесті НА ДИСКУ.
 *
 * Чому не через кнопку: підтести цього файлу ділять одну теку задачі, тож кадр
 * потрібної ширини міг зняти попередній підтест — і тоді прогону не буде
 * взагалі, а очікування «кнопка сказала Стоп» висітиме до таймауту. Стан на
 * диску — єдине, що однаково правдиве і після зʼємки, і без неї.
 */
async function waitForShot(it1, key, timeout = 120000) {
  const deadline = Date.now() + timeout;
  for (;;) {
    if (readManifest(it1).shots?.[key]) return true;
    if (Date.now() > deadline) throw new Error(`кадр ${key} так і не зʼявився в манифесті`);
    await new Promise((done) => setTimeout(done, 300));
  }
}

/** Дочекатись, поки картки ФАКТИЧНО стануть заданої ширини. */
const cardsAt = (page, w) => page.waitForFunction((want) => {
  const cards = [...document.querySelectorAll("#world .cv-card")];
  return cards.length > 0 && cards.every((c) => Math.round(parseFloat(c.style.width)) === want);
}, w, { timeout: 30000 });

/** Ширина карток у СВІТОВИХ координатах (до масштабу камери). */
const cardWidths = (page) => page.evaluate(() =>
  [...document.querySelectorAll("#world .cv-card")]
    .map((c) => Math.round(parseFloat(c.style.width))));

test("вьюпорти в «Огляді»", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());

  await t.test("A+B. мобайл дає кадри 375, і автозʼємка бере їх сама", async () => {
    const page = await openApp(browser, url);
    const orders = shootOrders(page);
    await overview(page);                       // десктопні кадри знялись автостартом
    const afterDesktop = orders.length;

    /* Перемикання — і жодного натискання кнопки зʼємки. Прогін мусить піти сам:
       кадрів цієї ширини немає, отже вони застарілі за побудовою.

       Чекаємо КАДР У МАНИФЕСТІ (`waitForShot`), а не кнопку `running()`: обидва
       docs те саме доводять (мутація «прибрати maybeAutoShoot()» червонить
       ОБИДВА способи однаково — ані запису в манифесті, ані «Стоп» на кнопці),
       але текст кнопки — стан ПЕРЕХІДНИЙ і короткий (дві крихітні сторінки
       знімаються за секунди), а `waitForFunction` по DOM тексту, що
       перезаписується цілком щотакту прогресу (`renderPanel()`, Task 4 Плану
       B), у цьому файлі виявився ненадійним живцем — той самий стан,
       підтверджений прямим `page.evaluate()` за секунду до перевірки, встигав
       зникнути до того, як `waitForFunction` встигав його побачити. Файл на
       диску такої гонки не має: він або є, або ні. */
    await page.locator('[data-act="vp"][data-val="mobile"]').click();
    await waitForShot(it1, "holovna@375");
    await runEnded(page);

    assert.ok(orders.length > afterDesktop, "перемикання ширини мусить замовити зʼємку саме");
    assert.deepEqual(await cardWidths(page), [375, 375], "картки стають завширшки 375");

    const shots = readManifest(it1).shots;
    assert.ok(shots["holovna@375"], "у манифесті мусить зʼявитись ключ із шириною");
    assert.equal(shots["holovna@375"].w, 375,
      "і кадр мусить бути СПРАВДІ 375 — інакше це десктоп під мобільним іменем");
    await page.close();
  });

  await t.test("C. повернення на «Десктоп» не запускає зайвого прогону", async () => {
    const page = await openApp(browser, url);
    const orders = shootOrders(page);
    await overview(page);                       // ми на мобайлі — вибір персистить
    const before = orders.length;

    await switchTo(page, "desktop");
    assert.deepEqual(await cardWidths(page), [CANVAS_W, CANVAS_W], "картки знову типової ширини");
    /* Кадри 1280 уже лежать під ключами БЕЗ суфікса — саме тому повернення на
       десктоп нічого не знімає. Якби типова ширина теж діставала суфікс, ці
       кадри стали б недосяжними й прогін пішов би заново. */
    assert.equal(orders.length, before, "наявні кадри типової ширини знаходяться як є");
    await page.close();
  });

  await t.test("D. ⛔ зʼємка мобайла не зʼїдає десктопні записи", async () => {
    const page = await openApp(browser, url);
    await overview(page);
    await switchTo(page, "desktop");
    await waitForShot(it1, "holovna");
    const desktopBefore = Object.fromEntries(
      Object.entries(readManifest(it1).shots).filter(([id]) => !id.includes("@")));
    assert.ok(Object.keys(desktopBefore).length >= 2, "десктопні кадри мусять бути на місці");

    /* Чекаємо КАДРИ, а не кнопку: підтести ділять теку, тож мобільні могли вже
       зняти вище — прогону тоді не буде, і очікування «Стоп» висіло б дарма. */
    await page.locator('[data-act="vp"][data-val="mobile"]').click();
    await waitForShot(it1, "holovna@375");
    await runEnded(page);
    await page.locator('[data-act="vp"][data-val="tablet"]').click();
    await waitForShot(it1, "holovna@768");
    await runEnded(page);

    const after = readManifest(it1).shots;
    for (const [id, rec] of Object.entries(desktopBefore)) {
      assert.ok(after[id], `запис ${id} ЗНИК із манифеста після зʼємки інших ширин`);
      assert.equal(after[id].sha, rec.sha, `кадр ${id} підмінено чужою шириною`);
      assert.equal(after[id].w, CANVAS_W, `ширина запису ${id} змінилась`);
    }
    assert.ok(after["holovna@375"] && after["holovna@768"],
      "а кадри обох нових ширин мусять зʼявитись поруч, а не замість");
    await page.close();
  });

  await t.test("E. флоу на мобільній ширині: колонки стоять по ширині кадру", async () => {
    /* Граф пишемо ДО того, як відкриємо застосунок для перевірки: `readFlow`
       читається на завантаженні, і збереження вже відкритій сторінці довелось би
       доганяти перезавантаженням просто під рукою рендера. */
    const setup = await openApp(browser, url);
    await setup.evaluate(async () => {
      await fetch("/api/flow-save", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ it: "it1", flow: { flows: [{ name: "Основний", nodes: [
          { id: "a", page: "holovna" }, { id: "b", page: "poshuk" },
        ], edges: [{ from: "a", to: "b" }] }] } }),
      });
    });
    await setup.close();

    const page = await openApp(browser, url);
    await overview(page);
    await page.locator('[data-act="vp"][data-val="mobile"]').click();
    await waitForShot(it1, "holovna@375");
    await runEnded(page);
    /* ⚠️ Чекаємо, поки ширина СПРАВДІ лягла на картки, а не просто поки минув
       клік. Перша редакція йшла далі одразу — `waitForShot` спрацьовував миттєво
       (кадри 375 зняв підтест вище), `runEnded` теж, і «Флоу» натискалось до
       того, як застосувався мобайл. Перевірка червоніла на −1280 і виглядала як
       баг продукту, хоч продукт був правий: діагностика показала колонки 200 і
       790 при картках 375, тобто рівно GAP. */
    await cardsAt(page, 375);

    /* Кнопка «Флоу» disabled, поки `flow.json` не довантажився, а клік по
       disabled нічого не робить МОВЧКИ — перевірка тоді міряла сітку й називала
       це розсипаним графом. Чекаємо готовності, і окремо — що вид СПРАВДІ
       перемкнувся. Смуга (Task 3): «Флоу»/«Сітка» — не один перемикач, що
       міняє підпис, а сегмент із ДВОХ кнопок; перемкнутий стан читається
       атрибутом `aria-pressed`, а не текстом кнопки (він завжди «Флоу»). */
    const flowBtn = '[data-act="view"][data-val="flow"]';
    await page.locator(`${flowBtn}:not([disabled])`).waitFor({ timeout: 15000 });
    await page.locator(flowBtn).click();
    await page.waitForFunction(
      (sel) => document.querySelector(sel)?.getAttribute("aria-pressed") === "true",
      flowBtn, { timeout: 15000 });
    await cardsAt(page, 375);

    /* Колонка друга стоїть на `cardW + GAP` від першої. Стала CARD_W замість
       `cardW()` розсунула б їх на 1280 при картках 375 — між кадром і стрілкою
       зяяв би розрив у ~890px, і граф читався б як розсипаний. */
    const gap = await page.evaluate(() => {
      const cards = [...document.querySelectorAll("#world .cv-card")]
        .sort((a, b) => parseFloat(a.style.left) - parseFloat(b.style.left));
      if (cards.length < 2) return null;
      const first = parseFloat(cards[0].style.left) + parseFloat(cards[0].style.width);
      return Math.round(parseFloat(cards[1].style.left) - first);
    });
    assert.ok(gap !== null, "у флоу-виді мусить бути принаймні дві картки");
    assert.ok(gap > 0 && gap < 400,
      `зазор між колонками мусить бути порядку GAP, а не ширини кадру: ${gap}`);
    await page.close();
  });
});
