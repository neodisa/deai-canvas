/**
 * Рядок вкладок і острівець (0.25.0, Task 9) — живе проведення.
 *
 * Юніти стережуть чисту модель і розмітку (`tests/tabs-model.test.mjs`, `tests/tabs-view.test.mjs`, `tests/island.test.mjs`);
 * тут те, чого вони не бачать: що вкладка зʼявляється від справжнього відкриття задачі, що клік і хрестик ведуть серверну
 * задачу й екран «Задачі», що вкладки переживають перезавантаження, що на 1024 нічого не вилазить за вікно і острівець не
 * налазить на панель інспектора, а склад кнопок острівця залежить від екрана.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 19000;
const HTML = () => "<!doctype html><h1>Фікстура</h1>";

/** Сервер із задачею `fixture` (поточна) і п'ятьма додатковими `t0…t4` (усі з текою). */
async function boot(t, portBase, { viewport = { width: 1440, height: 900 } } = {}) {
  const { dir } = taskFixture({ html: HTML });
  const extraTasks = {};
  for (let i = 0; i < 5; i += 1) {
    extraTasks[`t${i}`] = { dir, jira: `LIGA-${10000 + i}`, title: `LIGA-${10000 + i} · Задача ${i} для вкладок` };
  }
  const { child, url } = await startServer(dir, { portBase, extraTasks });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#tabs [data-act="tab"]');
  return { page, url };
}

const cur = async (url) => (await (await fetch(`${url}/api/tasks`)).json()).current;
const tabIds = (page) => page.$$eval('#tabs [data-act="tab"]', (els) => els.map((e) => e.dataset.val));
const activeTab = (page) => page.$$eval('#tabs [data-act="tab"][aria-current="page"]', (els) => els.map((e) => e.dataset.val));
const homeShown = (page) => page.evaluate(() => {
  const h = document.getElementById("tasks-home");
  return !!h && !h.hidden && getComputedStyle(h).display !== "none";
});
const barTitle = (page) => page.textContent("#bar .crumb--title");
const islandActs = (page) => page.$$eval("#hud .isl-btn", (els) => els.map((e) => e.dataset.act));

/** Логотип → «Задачі» → картка → чекаємо, що сервер і екран перейшли на `id`. */
async function openFromHome(page, url, id) {
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector(`#tasks-home .th-card[data-id="${id}"]`);
  await page.click(`#tasks-home .th-card[data-id="${id}"]`);
  await page.waitForFunction(async (want) => (await (await fetch("/api/tasks")).json()).current === want, id);
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.waitForFunction((want) => !!document.querySelector(`#tabs [data-act="tab"][data-val="${want}"][aria-current="page"]`), id);
}

const frameReady = (page) => page.waitForFunction(() => {
  const f = document.getElementById("frame");
  return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
}, null, { timeout: 15000 });

test("1: на старті у рядку одна вкладка поточної задачі, вона активна, логотип — ні", async (t) => {
  const { page } = await boot(t, PORT_BASE);
  assert.deepEqual(await tabIds(page), ["fixture"]);
  assert.deepEqual(await activeTab(page), ["fixture"]);
  assert.equal(await page.getAttribute('#tabs [data-act="home"]', "aria-current"), null, "логотип позначений поточним поза «Задачами»");
});

test("2: «Задачі» → друга задача карткою → дві вкладки, активна — друга", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 100);
  await openFromHome(page, url, "t0");
  assert.deepEqual(await tabIds(page), ["fixture", "t0"]);
  assert.deepEqual(await activeTab(page), ["t0"]);
});

test("3: клік по першій вкладці перемикає задачу — смуга й aria-current слідом", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 200);
  await openFromHome(page, url, "t0");
  assert.match(await barTitle(page), /Задача 0/);
  await page.click('#tabs [data-act="tab"][data-val="fixture"]');
  await page.waitForFunction(async () => (await (await fetch("/api/tasks")).json()).current === "fixture");
  await page.waitForFunction(() => !!document.querySelector('#tabs [data-act="tab"][data-val="fixture"][aria-current="page"]'));
  assert.equal(await cur(url), "fixture");
  assert.deepEqual(await activeTab(page), ["fixture"]);
  assert.match(await barTitle(page), /Фікстура/);
  assert.deepEqual(await tabIds(page), ["fixture", "t0"], "перемикання не губить вкладок");
});

test("4: хрестик активної віддає активність сусідці; хрестик останньої веде на «Задачі»", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 300);
  await openFromHome(page, url, "t0");
  await page.click('#tabs [data-act="tabclose"][data-val="t0"]');
  await page.waitForFunction(() => !document.querySelector('#tabs [data-act="tab"][data-val="t0"]'));
  assert.deepEqual(await tabIds(page), ["fixture"]);
  await page.waitForFunction(() => !!document.querySelector('#tabs [data-act="tab"][data-val="fixture"][aria-current="page"]'));
  assert.equal(await cur(url), "fixture", "сервер лишився на сусідній задачі");
  assert.equal(await homeShown(page), false, "поки є вкладка, «Задачі» не відкриваються");

  await page.click('#tabs [data-act="tabclose"][data-val="fixture"]');
  await page.waitForFunction(() => { const h = document.getElementById("tasks-home"); return !!h && !h.hidden; });
  assert.equal(await homeShown(page), true, "остання вкладка закрита — мав відкритись екран «Задачі»");
  assert.deepEqual(await tabIds(page), []);
  assert.equal(await page.getAttribute('#tabs [data-act="home"]', "aria-current"), "page");
});

test("5: вкладки переживають перезавантаження (той самий список і активна)", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 400);
  await openFromHome(page, url, "t0");
  await openFromHome(page, url, "t1");
  const before = await tabIds(page);
  assert.deepEqual(before, ["fixture", "t0", "t1"]);
  await page.reload();
  await page.waitForSelector('#tabs [data-act="tab"]');
  await page.waitForFunction(() => !!document.querySelector('#tabs [data-act="tab"][aria-current="page"]'));
  assert.deepEqual(await tabIds(page), before);
  assert.deepEqual(await activeTab(page), ["t1"]);
});

test("6: на 1024×700 нічого не вилазить за вікно; острівець лівіше панелі інспектора", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 500, { viewport: { width: 1024, height: 700 } });
  await openFromHome(page, url, "t0");
  await frameReady(page);
  const geo = () => page.evaluate(() => ({
    sw: document.documentElement.scrollWidth, iw: window.innerWidth,
    tabs: document.getElementById("tabs").getBoundingClientRect().width,
    bar: document.getElementById("bar").getBoundingClientRect().width,
  }));
  let g = await geo();
  assert.ok(g.sw <= g.iw, `горизонтальна прокрутка: ${g.sw} > ${g.iw}`);
  assert.ok(g.tabs <= g.iw, `#tabs ширший за вікно: ${g.tabs}`);
  assert.ok(g.bar <= g.iw, `#bar ширший за вікно: ${g.bar}`);

  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => { const p = document.getElementById("insp-panel"); return !!p && !p.hidden && p.getBoundingClientRect().width > 0; });
  const r = await page.evaluate(() => ({
    isl: document.querySelector("#hud .island").getBoundingClientRect().right,
    insp: document.getElementById("insp-panel").getBoundingClientRect().left,
  }));
  assert.ok(r.isl < r.insp, `острівець (правий край ${r.isl}) налазить на панель інспектора (лівий ${r.insp})`);
  g = await geo();
  assert.ok(g.sw <= g.iw, `з відкритим інспектором зʼявилась горизонтальна прокрутка: ${g.sw} > ${g.iw}`);
});

test("6б: шість вкладок у вікні 420px — рядок прокручується всередині, шестерня лишається у вікні", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 600, { viewport: { width: 420, height: 700 } });
  for (const id of ["t0", "t1", "t2", "t3", "t4"]) await openFromHome(page, url, id);
  assert.equal((await tabIds(page)).length, 6);
  const g = await page.evaluate(() => {
    const list = document.querySelector("#tabs .tabs-list");
    const gear = document.querySelector('#tabs [data-act="settings"]').getBoundingClientRect();
    return { sw: document.documentElement.scrollWidth, iw: window.innerWidth,
      tabs: document.getElementById("tabs").getBoundingClientRect().width,
      listScroll: list.scrollWidth, listClient: list.clientWidth, gearRight: gear.right, gearLeft: gear.left };
  });
  assert.ok(g.sw <= g.iw, `сторінка розпухла вбік: ${g.sw} > ${g.iw}`);
  assert.ok(g.tabs <= g.iw, `#tabs ширший за вікно: ${g.tabs}`);
  assert.ok(g.gearLeft >= 0 && g.gearRight <= g.iw, `шестерню виштовхало за вікно: ${g.gearLeft}…${g.gearRight}`);
  assert.ok(g.listClient > 0, "список вкладок схлопнувся в нуль");
  assert.ok(g.listScroll > g.listClient, `перевірка недійсна: вкладки вміщаються без прокрутки (${g.listScroll} ≤ ${g.listClient})`);
});

test("7: острівець за екранами — «Макет»: інспектор і баг; «Огляд» і «Задачі»: лише баг", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 700);
  await frameReady(page);
  assert.deepEqual(await islandActs(page), ["inspector", "feedback"], "«Макет»");

  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForFunction(() => document.querySelectorAll("#hud .isl-btn").length === 1);
  assert.deepEqual(await islandActs(page), ["feedback"], "«Огляд»");

  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.deepEqual(await islandActs(page), ["feedback"], "«Задачі»");
});
