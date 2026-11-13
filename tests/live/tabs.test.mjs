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

/** Опитує умову з боку node (Playwright не чекає проміс у waitForFunction). */
async function until(fn, ms = 15000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await fn()) return; await new Promise((r) => setTimeout(r, 100)); }
  throw new Error("умова не виконалась за " + ms + " мс");
}

/** Логотип → «Задачі» → картка → чекаємо, що сервер і екран перейшли на `id`. */
async function openFromHome(page, url, id) {
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector(`#tasks-home .th-card[data-id="${id}"]`);
  await page.click(`#tasks-home .th-card[data-id="${id}"]`);
  await until(async () => (await (await fetch(`${url}/api/tasks`)).json()).current === id);
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
  await until(async () => (await cur(url)) === "fixture");
  await page.waitForFunction(() => !!document.querySelector('#tabs [data-act="tab"][data-val="fixture"][aria-current="page"]'));
  assert.equal(await cur(url), "fixture");
  await page.waitForFunction(() => /Фікстура/.test(document.querySelector("#bar .crumb--title")?.textContent || ""));
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

const focusedAct = (page) => page.evaluate(() => {
  const a = document.activeElement;
  return a && a.dataset ? `${a.dataset.act || ""}|${a.dataset.val || ""}` : "";
});

test("8: фокус на вкладці переживає перемальовку рядка (зміна стану Claude)", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 800);
  await openFromHome(page, url, "t0");
  let stub = null;
  await page.route("**/api/claude-statuses", (route) => (stub
    ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(stub) })
    : route.continue()));
  await page.focus('#tabs [data-act="tab"][data-val="t0"]');
  assert.equal(await focusedAct(page), "tab|t0");
  stub = { tasks: { t0: { state: "working", age_s: 1 } } };
  await page.waitForSelector("#tabs .tab-claude", { timeout: 12000 });
  assert.equal(await focusedAct(page), "tab|t0", "фокус втрачено після перемальовки вкладок");
});

test("9: Enter на кнопці інспектора в острівці лишає фокус на ній і перемикає aria-pressed", async (t) => {
  const { page } = await boot(t, PORT_BASE + 900);
  await frameReady(page);
  const sel = '#hud [data-act="inspector"]';
  const before = await page.getAttribute(sel, "aria-pressed");
  await page.focus(sel);
  await page.keyboard.press("Enter");
  await page.waitForFunction(([s, b]) => document.querySelector(s)?.getAttribute("aria-pressed") !== b, [sel, before]);
  assert.equal(await focusedAct(page), "inspector|", "фокус зник з кнопки інспектора");
  assert.notEqual(await page.getAttribute(sel, "aria-pressed"), before);
});

test("10: закриття вкладки з клавіатури лишає фокус на вкладці чи логотипі, не на body", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 1000);
  await openFromHome(page, url, "t0");
  await page.focus('#tabs [data-act="tabclose"][data-val="t0"]');
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.querySelector('#tabs [data-act="tab"][data-val="t0"]'));
  await until(async () => (await focusedAct(page)) !== "|").catch(() => {});
  const f = await focusedAct(page);
  assert.ok(f.startsWith("tab|") || f === "home|", `фокус на «${f}», а не на вкладці/логотипі`);
  await page.focus('#tabs [data-act="tabclose"]');
  await page.keyboard.press("Enter");
  await until(async () => (await focusedAct(page)) !== "|").catch(() => {});
  const g = await focusedAct(page);
  assert.ok(g.startsWith("tab|") || g === "home|", `після закриття останньої фокус на «${g}»`);
});

test("11: швидкі кліки по двох вкладках — одна зміна задачі за раз, виграє остання", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 1100);
  for (const id of ["t0", "t1", "t2"]) await openFromHome(page, url, id);
  await page.click('#tabs [data-act="tab"][data-val="fixture"]');
  await until(async () => (await cur(url)) === "fixture" && (await page.evaluate(() => document.querySelector('#tabs [aria-current="page"]')?.dataset.val)) === "fixture");
  await page.waitForTimeout(500);
  let inflight = 0; let maxInflight = 0; let posts = 0;
  await page.route("**/api/task-switch", async (route) => {
    inflight += 1; posts += 1; maxInflight = Math.max(maxInflight, inflight);
    await new Promise((r) => setTimeout(r, 400));
    await route.continue();
    inflight -= 1;
  });
  await page.evaluate(() => {
    document.querySelector('#tabs [data-act="tab"][data-val="t0"]').click();
    document.querySelector('#tabs [data-act="tab"][data-val="t1"]').click();
    document.querySelector('#tabs [data-act="tab"][data-val="t2"]').click();
  });
  await until(async () => (await cur(url)) === "t2" && (await page.evaluate(() => document.querySelector('#tabs [aria-current="page"]')?.dataset.val)) === "t2");
  await page.waitForTimeout(800);
  assert.equal(await cur(url), "t2", "виграла не остання вкладка");
  assert.equal(maxInflight, 1, `одночасних task-switch: ${maxInflight}`);
  assert.equal(posts, 2, `зайвих task-switch: ${posts} (мало бути перший і останній)`);
});
