/**
 * Живий охоронець проводки панелі шарів: КОЖЕН видимий контрол `[data-act]`
 * усередині `#pages-panel` мусить РОБИТИ ХОЧ ЩОСЬ на клік — той самий
 * інваріант, що вже стереже `tests/live/shell-bar.test.mjs` для смуги, і та
 * сама причина: `tests/shell-panel.test.mjs` перевіряє лише, що РОЗМІТКА
 * несе правильний `data-act`/`data-val` — не що на нього щось РЕАГУЄ.
 * Делегація (`PANEL_ACTIONS[act]?.(...)`, `app.js`) ковтає забутий рядок
 * мовчки: кнопка просто перестає щось робити, і жоден юніт цього не бачить.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо запобіжник прибрати»:
 *
 *   panel (згорнути/розгорнути) — рядок `panel:` у `PANEL_ACTIONS`. Прибери
 *                                 його — клік не додасть `panel--rail` і не
 *                                 прибере: падає на «panel».
 *   newpage («+» дерева)        — рядок `newpage:` у `PANEL_ACTIONS`. Клік
 *                                 мусить підняти оверлей `ask()`
 *                                 (`.cv-ask-scrim` у DOM) — падає на
 *                                 «newpage».
 *   pagemenu («⋯» рядка)        — рядок `pagemenu:` у `PANEL_ACTIONS`. Клік
 *                                 мусить підняти `.cv-ctx` — падає на
 *                                 «pagemenu».
 *   page (клік по рядку)        — рядок `page:` у `PANEL_ACTIONS`. Клік по
 *                                 сторінці, що НЕ обрана, мусить перемалювати
 *                                 панель (клас `.row--sel` переїжджає) —
 *                                 падає на «page[poshuk]» (друга сторінка
 *                                 фікстури — перша вже обрана типово, і клік
 *                                 по вже обраній не змінив би підсвітку).
 *
 * ⛔ Свідомо НЕ в загальному прогоні (і чому — мовчазний пропуск гірший за
 * пояснений):
 *   shoot (кнопка «Кадри»)  — не «небезпечна», а ДОРОГА: справжній клік
 *     запускає headless Chromium (`bin/shoot.mjs`) через `serve.py`. Тому не
 *     пропущена мовчки, а перевірена ОКРЕМИМ тестом нижче («кнопка «Кадри»
 *     реагує на клік і її можна зупинити»), який одразу ж і зупиняє прогін —
 *     проводку доведено, а ціна лишається мінімальною.
 *   toggle (каретка стану)  — фікстура (`tests/live/fixture.mjs`) дає ДВІ
 *     сторінки БЕЗ дітей: каретки в дереві просто немає — не «схована», а
 *     відсутня в розмітці зовсім (`row-caret--none`, без `data-act`). Немає
 *     видимого контролу — нема що тиснути; юніт (`tests/shell-panel.test.mjs`)
 *     уже стереже саму каретку на чистій моделі з дітьми.
 *
 * Порядок циклу НАВМИСНО НЕ збігається з порядком DOM: `panel` — останнім.
 * Згортання в рейку прибирає з DOM дерево й «⋯» (рейка лишає лише три
 * контроли — `panel`/`newpage`/`shoot`, окрема перевірка нижче), тобто клік
 * по «panel» РАНІШЕ за решту прибрав би їх із розмітки ще до того, як цикл
 * до них дійде — не бага, а порядок, у якому такий цикл сам собі підставляє
 * ногу.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 9490;
const VIEW = { width: 1400, height: 900 };
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body><h1>${id}</h1></body></html>`;

test("кожен видимий контрол панелі щось робить на клік", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator("#pages-panel .row").first().waitFor();

  const controls = await page.$$eval("#pages-panel [data-act]", (els) =>
    els.filter((e) => e.offsetParent !== null).map((e) => ({
      act: e.dataset.act, val: e.dataset.val || null, tag: e.tagName,
    })));
  assert.ok(controls.length >= 4,
    `у панелі лише ${controls.length} контролів — розмітка не та`);
  assert.ok(controls.some((c) => c.act === "page"), "немає рядків дерева");
  /* «＋ стор.» прибрано (рішення власника 30.09.2026: сторінки створює Claude);
     єдине «＋» у шапці дерева створює ТЕКУ (`newfolder`) — його й вимагаємо. */
  assert.ok(controls.some((c) => c.act === "newfolder"), 'немає «＋ тека» у шапці дерева');
  assert.ok(!controls.some((c) => c.act === "newpage"), "«＋ сторінку» повернулась у панель");
  assert.ok(controls.some((c) => c.act === "pagemenu"), 'немає «⋯» рядка');

  const DANGEROUS_OR_EXPENSIVE = new Set(["shoot"]);
  // `panel` — останнім (порядок циклу), з причини в шапці файлу.
  const ordered = [
    ...controls.filter((c) => c.act !== "panel"),
    ...controls.filter((c) => c.act === "panel"),
  ];

  for (const c of ordered) {
    if (DANGEROUS_OR_EXPENSIVE.has(c.act)) continue;
    const name = c.val ? `${c.act}[${c.val}]` : c.act;
    /* Тег у селекторі — з Плану A, Task 3: дію `panel` тепер несуть ДВА
       елементи (кнопка-стрілка в шапці й `div.panel-fill` — порожнє місце під
       деревом). `page.click()` НЕ строгий (на відміну від `locator().click()`)
       і мовчки клікав би перший збіг двічі, тобто заповнювач лишився б
       неперевіреним, а цикл — вакуумно зеленим на другому колі. */
    const tag = c.tag.toLowerCase();
    const sel = c.val
      ? `#pages-panel ${tag}[data-act="${c.act}"][data-val="${c.val}"]`
      : `#pages-panel ${tag}[data-act="${c.act}"]`;

    /* «Уже обрана» сторінка — свідомий ноп у `PANEL_ACTIONS.page`
       (`pickedPage` не змінюється, перемальовки немає): типово обрана
       ОСТАННЯ сторінка фікстури (`render()` нормалізує `pickedPage` на
       перший «відкриваний» запис — перший у списку, `holovna`). Клікати
       чекаючи зміни тут означало б чекати того, чого код сам обіцяє не
       робити. */
    if (c.act === "page" && c.val === "holovna") continue;

    const before = await page.$eval("#pages-panel", (e) => e.innerHTML);
    await page.click(sel);
    /* Чекаємо НАСЛІДКУ, а не фіксований час: `newfolder` робить POST →
       `loadPages()` → `render()` і лише тоді показує поле назви, а під
       повним `test:live` (чотири Chromium паралельно) 150 мс не вистачало —
       флак 02.10.2026, «контрол «newfolder» не зробив нічого». Контрол, що не
       робить нічого, однаково червоніє — за 3 с. */
    const acted = await page.waitForFunction((was) =>
      document.getElementById("pages-panel").innerHTML !== was
        || document.querySelectorAll(".cv-ctx, .cv-ask-scrim").length > 0,
    before, { timeout: 3000 }).then(() => true, () => false);
    assert.ok(acted, `контрол «${name}» не зробив нічого`);

    // Прибираємо за собою: оверлей/меню не сміє лишитись і зіпсувати
    // наступний крок циклу (наприклад, `.cv-ask-scrim` ловить усі кліки).
    await page.keyboard.press("Escape");
    await page.waitForTimeout(50);
  }
});

/* Дорога дія — окремим тестом, а не мовчазним пропуском (шапка файлу). Клік
   мусить перевести секцію «Кадри» у стан «знімаю», і той самий контрол мусить
   уміти зупинити прогін — доводимо ОБИДВА без очікування повного прогону. */
test("кнопка «Кадри» реагує на клік і її можна зупинити", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 10 });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  const shoot = page.locator('#pages-panel [data-act="shoot"]');
  await shoot.waitFor();
  assert.match(await shoot.innerText(), /Зняти кадри/);

  await shoot.click();
  await page.waitForFunction(() => {
    const b = document.querySelector('#pages-panel [data-act="shoot"]');
    return !!b && /Стоп|Знімаю/.test(b.innerText);
  }, null, { timeout: 5000 });

  // Той самий контрол зупиняє прогін — інакше «Стоп» був би написом, а не дією.
  await page.locator('#pages-panel [data-act="shoot"]').click();
  await page.waitForFunction(() => {
    const b = document.querySelector('#pages-panel [data-act="shoot"]');
    return !!b && !/Стоп/.test(b.innerText);
  }, null, { timeout: 10000 });
});

/* Спека Task 4, п.1: «⋯» у рядку відкриває меню, і воно не зрізане ані
   `.panel-body{overflow:auto}` (звідки й прийшла вимога `position:fixed`,
   див. коментар над `positionCtxMenu` в app.js), ані краєм вікна — «обидва
   боки». Правий бік перевіряємо на вузькому вікні (менше за суму зсуву панелі
   й ширини меню — інакше клемпінг нічого не робить, і мутація «прибери
   клемпінг» лишила б перевірку зеленою); лівий — правим кліком біля самого
   лівого краю рядка (панель стоїть впритул до x=0, тож природний клік там
   і є найкоротший шлях до `x < 8`, без штучних координат). */
test('«⋯» відкриває меню, і воно ЦІЛКОМ у межах вікна (обидва боки)', async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 20 });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());

  // Правий край: вузьке вікно, у якому 246px панелі + ширина меню
  // (`.cv-ctx{min-width:190px}`) точно не влазять поруч.
  {
    const page = await browser.newPage({ viewport: { width: 320, height: 700 } });
    await page.goto(`${url}/app/`);
    await page.locator('#pages-panel [data-act="pagemenu"]').first().click();
    const box = await page.locator("#cv-ctx").boundingBox();
    assert.ok(box, "меню не зʼявилось");
    assert.ok(box.x + box.width <= 320,
      `меню вилазить за правий край: right=${box.x + box.width}, вікно=320`);
    assert.ok(box.x >= 0, `меню вилазить за лівий край: x=${box.x}`);
    await page.close();
  }

  /* Лівий край: правий клік ПРАВО НА МЕЖІ рядка (панель — `left:0`, тож у
     самого рядка `x ≈ 6px` — відступ `.panel-body{padding:6px}`, менший за
     поле клемпінгу 8px). `+1` — щоб не влучити повз рядок субпіксельним
     округленням, не щоб уникнути клемпінгу: сирий якір лишається 7px, менший
     за поле, — клемпінг мусить підняти його до 8. Без `Math.max(8, …)` тут
     стояло б ~7, а не ~8: різниця мала, але точна й перевірна, а не «десь
     не негативне». */
  {
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${url}/app/`);
    const row = page.locator('[data-page="holovna"]');
    await row.waitFor();
    const rb = await row.boundingBox();
    await page.mouse.click(rb.x + 1, rb.y + rb.height / 2, { button: "right" });
    const box = await page.locator("#cv-ctx").boundingBox();
    assert.ok(box, "меню не зʼявилось на правий клік");
    assert.ok(box.x >= 7.5 && box.x <= 9,
      `клемпінг лівого краю не спрацював як очікувалось: x=${box.x} (мало бути ≈8, поле — 8)`);
    await page.close();
  }
});

/* Escape закриває меню (спека Task 4, п.3) — ані `pillMenu`, ані старий
   `pageMenu` цього не вміли взагалі: рятував лише клік повз. */
test("Escape закриває меню сторінки", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 30 });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator('#pages-panel [data-act="pagemenu"]').first().click();
  await page.locator("#cv-ctx").waitFor();
  /* `pageMenu()` вішає слухачів через `setTimeout(…, 0)` — щоб клік, який
     ВІДКРИВ меню, сам його не закрив (той самий приймай, що в `pillMenu`).
     `waitFor()` вище резолвиться на мутації DOM і випереджає цей таймер:
     без паузи Escape долітає РАНІШЕ, ніж `document.addEventListener` устиг
     спрацювати, і тест ловив би гонку тесту, а не бага меню. */
  await page.waitForTimeout(50);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#cv-ctx").count(), 0, "Escape не закрив меню");
});

/* Згортання в рейку й назад не втрачає жодної дії (спека Task 4, п.2):
   три контроли лишаються в рейці, і всі три — ті самі елементи, що керують
   нею у відкритому стані. З Плану A, Task 3 у рейці є ще й обгортка
   `div.panel-rail` із тією ж дією `panel` («одна велика кнопка») — вона
   контрол не заміняє, тому перевірки нижче питають ВИДИМІСТЬ кожного з
   трьох, а не кількість елементів із дією. */
test("рейка не втрачає вхід назад і зʼємку; «＋ тека» живе лише в шапці дерева", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 40 });
  t.after(() => child.kill());

  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.locator("#pages-panel .row").first().waitFor();

  /* `button[data-act="panel"]` — САМА стрілка, а не «будь-що з дією панелі»:
     після Плану A, Task 3 дію несуть іще два елементи (`div.panel-fill` у
     відкритій панелі, `div.panel-rail` у рейці), і строгий `locator()` на
     голому `[data-act="panel"]` падає з «resolved to 2 elements». Тут
     перевіряється СКЛАД рейки, тож клікати треба тим самим контролом, що й
     раніше; порожнє місце й рейку як одну велику кнопку стереже окремий
     `tests/live/panel-click.test.mjs`. */
  await page.locator('#pages-panel button[data-act="panel"]').click();
  await page.waitForFunction(() => document.body.classList.contains("panel-collapsed"));

  const vis = (sel) => page.$$eval(sel, (els) => els.filter((e) => e.offsetParent !== null).length);
  assert.ok(await vis('#pages-panel [data-act="panel"]') > 0, "рейка загубила вхід назад");
  /* У рейці рівно два контроли (`shell-panel.js`): вхід назад і зʼємка. З дерева
     там нічого — ні «＋ теки», ні колишнього «＋ сторінки». */
  assert.equal(await vis('#pages-panel [data-act="newfolder"], #pages-panel [data-act="newpage"]'), 0,
    "у рейці зʼявилось додавання — рейка має лише вхід назад і зʼємку");
  assert.ok(await vis('#pages-panel [data-act="shoot"]') > 0, "рейка загубила зʼємку");
  // Дерево в рейці не малюється взагалі — не «сховане», а відсутнє.
  assert.equal(await vis("#pages-panel .row"), 0, "рейка чомусь показує дерево");

  // Назад — і дерево та ⋯ повертаються.
  await page.locator('#pages-panel button[data-act="panel"]').click();
  await page.waitForFunction(() => !document.body.classList.contains("panel-collapsed"));
  assert.ok(await vis("#pages-panel .row") > 0, "розгортання не повернуло дерево");
  assert.ok(await vis('#pages-panel [data-act="pagemenu"]') > 0, 'розгортання не повернуло «⋯»');
});
