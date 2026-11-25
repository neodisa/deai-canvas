/**
 * Місце в адресі й власний стек Назад/Вперед (0.40). T4: адреса відображає місце (лише replaceState — pushState не викликається
 * жодного разу), перезавантаження лишає на місці (задача, ітерація, сторінка, режим, вид «Огляду» вкл. `v=flow`), невідоме або
 * видалене — тихий запасний варіант (і ітерація з адреси іншої задачі НЕ застосовується), задача з іншого простору, `/app/#…`
 * віддається у СВІЖІЙ сторінці. T5 (нижче): стек, кнопки, ⌘[ ⌘], ⌘R і Назад, `hashchange`, відмова охоронця.
 */
import assert from "node:assert/strict";
import { cpSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 52000;
const VIEW = { width: 1440, height: 900 };
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px"><h1>${id}</h1><p>Абзац ${id}</p></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Задача з двома ітераціями (it1, it2), двома сторінками (holovna, poshuk) і графом у it1 (щоб «Флоу» був доступний). */
function twoIterations() {
  const { dir } = taskFixture({ html: PAGE });
  cpSync(path.join(dir, "iterations", "it1"), path.join(dir, "iterations", "it2"), { recursive: true });
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({ iterations: [
    { id: "it1", date: "24.08.2026 12:00", note: "перша", published: true },
    { id: "it2", date: "25.08.2026 12:00", note: "друга", published: true }] }));
  writeFileSync(path.join(dir, "iterations", "it1", "flow.json"), JSON.stringify({ flows: [
    { id: "f", title: "Потік", nodes: [{ id: "n1", page: "holovna" }, { id: "n2", page: "poshuk" }], edges: [{ from: "n1", to: "n2" }] }] }));
  return dir;
}
/** Новий сервер + СВІЖА сторінка (нова вкладка: `goto` у ній справді вантажить документ, а не лише міняє hash). */
export async function boot(t, off, { hash = "", viewport = VIEW } = {}) {
  const dir = twoIterations();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport });
  t.after(() => page.close());
  /* Лічильник `pushState`: адреса пишеться ЛИШЕ replaceState (історію браузера заповнює рамка — на неї Назад не будуємо). */
  await page.addInitScript(() => {
    window.__push = 0;
    const p = history.pushState.bind(history);
    history.pushState = (...a) => { window.__push += 1; return p(...a); };
  });
  await page.goto(`${url}/app/${hash}`);
  await page.waitForSelector('[data-act="page"][data-val="holovna"]');
  return { page, url };
}
const src = (page) => page.getAttribute("#frame", "src");
const hash = (page) => page.evaluate(() => location.hash);
const frameReady = (page, re) => page.waitForFunction((s) => new RegExp(s).test(document.getElementById("frame").getAttribute("src") || ""), re.source);
const pushes = (page) => page.evaluate(() => window.__push);

test("T4-1: адреса відображає місце; pushState не викликано", async (t) => {
  const { page } = await boot(t, 0);
  await page.waitForFunction(() => /it=it2/.test(location.hash) && /p=holovna/.test(location.hash));
  assert.match(await hash(page), /^#(sp=[^&]*&)?t=[^&]+&it=it2&p=holovna$/);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await page.waitForFunction(() => /p=poshuk/.test(location.hash));
  assert.equal(await pushes(page), 0);
});

test("T4-2: перезавантаження лишає на місці — ітерація, сторінка, «Огляд» і вид «Флоу»", async (t) => {
  const { page } = await boot(t, 100);
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="iter"][data-val="it1"]');
  await page.click('[data-act="page"][data-val="poshuk"]');
  await frameReady(page, /it=it1.*page=poshuk/);
  await page.waitForFunction(() => /it=it1/.test(location.hash) && /p=poshuk/.test(location.hash));
  await page.reload();
  await frameReady(page, /it=it1.*page=poshuk/);
  assert.equal(await page.$eval('[data-act="page"][aria-selected="true"]', (e) => e.dataset.val), "poshuk");

  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForFunction(() => /m=o/.test(location.hash));
  /* «Флоу» мусить бути доступний (граф є в it1): провалена кнопка — провалений тест, а не мовчазний пропуск. */
  await page.click('#bar [data-act="view"][data-val="flow"]');
  await page.waitForFunction(() => /v=flow/.test(location.hash));
  const h = await hash(page);
  await page.reload();
  await page.waitForSelector("#canvas:not([hidden])");
  await page.waitForFunction((x) => location.hash === x, h);
  assert.equal(await page.evaluate(() => document.getElementById("stage").hidden), true, "відкрито «Огляд», а не «Макет»");
  assert.equal(await page.$eval('#bar [data-act="view"][data-val="flow"]', (e) => e.getAttribute("aria-pressed")), "true", "вид «Флоу» відновлено");
});

test("T4-3: невідома задача: ітерація й сторінка з адреси ІНШОЇ задачі не застосовуються — звичне місце поточної; адреса виправлена", async (t) => {
  const { page } = await boot(t, 200, { hash: "#t=no-such-task&it=it1&p=poshuk" });
  await page.waitForFunction(() => /it=it2/.test(location.hash));
  assert.match(await hash(page), /it=it2&p=holovna/, "остання ітерація й перша сторінка поточної задачі, а не it1/poshuk з адреси");
  assert.equal(await pushes(page), 0);
});

test("T4-3b: видалена ітерація в адресі (задача відома) — тихо остання; сторінка — перша", async (t) => {
  const { page } = await boot(t, 250);
  const t0 = await page.evaluate(() => /(?:^#|&)t=([^&]+)/.exec(location.hash)[1]);
  const p2 = await browser.newPage({ viewport: VIEW });
  t.after(() => p2.close());
  await p2.goto(`${page.url().split("/app/")[0]}/app/#t=${t0}&it=it99&p=nope`);
  await p2.waitForSelector('[data-act="page"][data-val="holovna"]');
  await p2.waitForFunction(() => /it=it2&p=holovna/.test(location.hash));
});

test("T4-4: `/app/#…` віддається у СВІЖІЙ сторінці (service worker не залежить від hash)", async (t) => {
  const { url } = await boot(t, 300);
  const fresh = await browser.newPage({ viewport: VIEW });
  t.after(() => fresh.close());
  const r = await fresh.goto(`${url}/app/#t=x&it=it1`);
  assert.ok(r !== null && r.ok(), "справжній документ, а не зміна hash у вже відкритій сторінці");
  await fresh.waitForSelector('[data-act="page"][data-val="holovna"]');
});

test("T4-5: задача з ІНШОГО простору в адресі: старт веде в неї (task-switch перемикає простір)", async (t) => {
  const A = taskFixture({ html: PAGE });
  const B = taskFixture({ html: PAGE });
  const server = await startServer(null, { portBase: PORT_BASE + 400, spaces: [
    { name: "Alpha", id: "alpha", color: "space-1", tasks: { ta: { dir: A.dir, title: "Задача A" } } },
    { name: "Beta", id: "beta", color: "space-2", tasks: { tb: { dir: B.dir, title: "Задача B" } } },
  ] });
  t.after(() => server.child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${server.url}/app/#sp=beta&t=tb&it=it1&p=poshuk`);
  await page.waitForFunction(() => /t=tb/.test(location.hash) && /sp=beta/.test(location.hash), null, { timeout: 20000 });
  await frameReady(page, /it=it1.*page=poshuk/);
  /* Друга половина (hashchange → інший простір) чекає на справжній `goTo` із T5: у T4 він заглушка. */
});

/** id поточної задачі сервера (для адрес-посилань у нових вкладках). */
const currentTask = async (page, url) => (await (await page.request.get(`${url}/api/tasks`)).json()).current;

test("T4-6: порядок старту — task-switch на сервері ПЕРЕД першим читанням тюнера (пакет тюнера береться для задачі з адреси)", async (t) => {
  const A = taskFixture({ html: PAGE });
  const B = taskFixture({ html: PAGE });
  const server = await startServer(null, { portBase: PORT_BASE + 500, spaces: [
    { name: "Alpha", id: "alpha", color: "space-1", tasks: { ta: { dir: A.dir, title: "Задача A" } } },
    { name: "Beta", id: "beta", color: "space-2", tasks: { tb: { dir: B.dir, title: "Задача B" } } },
  ] });
  t.after(() => server.child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  const seen = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.pathname === "/api/task-switch" || u.pathname === "/api/tuner") seen.push(`${r.method()} ${u.pathname}`);
  });
  await page.goto(`${server.url}/app/#sp=beta&t=tb&it=it1&p=poshuk`);
  await page.waitForFunction(() => /t=tb/.test(location.hash), null, { timeout: 20000 });
  await page.waitForTimeout(800);
  const sw = seen.indexOf("POST /api/task-switch");
  const tune = seen.indexOf("GET /api/tuner");
  assert.ok(sw >= 0, `task-switch не було: ${seen}`);
  assert.ok(tune >= 0, `тюнер не читався: ${seen}`);
  assert.ok(sw < tune, `тюнер прочитано ДО перемикання задачі: ${seen}`);
});

test("T4-7: старт із #…&it=…&m=o — ПЕРШИЙ рендер уже з ітерацією й режимом з адреси (рамка не вантажить останню ітерацію)", async (t) => {
  const dir = twoIterations();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 600 });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.addInitScript(() => {
    window.__srcs = [];
    new MutationObserver((ms) => {
      for (const m of ms) {
        const f = document.getElementById("frame");
        if (f && (m.target === f || [...(m.addedNodes || [])].includes(f))) window.__srcs.push(f.getAttribute("src") || "");
      }
    }).observe(document, { subtree: true, attributes: true, attributeFilter: ["src"], childList: true });
  });
  const t0 = await currentTask(page, url);
  await page.goto(`${url}/app/#t=${t0}&it=it1&m=o`);
  await page.waitForSelector("#canvas:not([hidden])");
  await page.waitForSelector(".cv-card");
  await page.waitForTimeout(800);
  const srcs = await page.evaluate(() => window.__srcs);
  assert.ok(!srcs.some((s) => /it=it2/.test(s)), `рамка вантажила останню ітерацію до адресної: ${JSON.stringify(srcs)}`);
  assert.match(await hash(page), /it=it1/);
  assert.match(await hash(page), /m=o/);
});

test("T4-8: старт із h=tasks відкриває «Задачі» й адреса зберігає h= після render", async (t) => {
  const dir = twoIterations();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 700 });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  const t0 = await currentTask(page, url);
  await page.goto(`${url}/app/#t=${t0}&it=it1&p=holovna&h=tasks`);
  await page.waitForFunction(() => document.body.classList.contains("home-open"), null, { timeout: 20000 });
  await page.waitForTimeout(800);
  assert.equal(await page.evaluate(() => document.body.classList.contains("home-open")), true);
  assert.match(await hash(page), /h=tasks/);
});

test("T4-9: старт із h=settings відкриває «Налаштування» й адреса зберігає h=settings", async (t) => {
  const A = taskFixture({ html: PAGE });
  const server = await startServer(null, { portBase: PORT_BASE + 800, spaces: [
    { name: "Alpha", id: "alpha", color: "space-1", tasks: { ta: { dir: A.dir, title: "Задача A" } } },
  ] });
  t.after(() => server.child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${server.url}/app/#sp=alpha&t=ta&it=it1&p=holovna&h=settings`);
  await page.waitForSelector(".set-nav", { timeout: 20000 });
  await page.waitForTimeout(800);
  assert.equal(await page.evaluate(() => document.body.classList.contains("home-open")), true);
  assert.match(await hash(page), /h=settings/);
});
