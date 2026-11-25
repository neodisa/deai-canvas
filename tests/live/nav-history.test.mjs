/**
 * Місце в адресі й власний стек Назад/Вперед (0.40). T4: адреса відображає місце (лише replaceState — pushState не викликається
 * жодного разу), перезавантаження лишає на місці (задача, ітерація, сторінка, режим, вид «Огляду» вкл. `v=flow`), невідоме або
 * видалене — тихий запасний варіант (і ітерація з адреси іншої задачі НЕ застосовується), задача з іншого простору, `/app/#…`
 * віддається у СВІЖІЙ сторінці. T5 (нижче): стек, кнопки, ⌘[ ⌘], ⌘R і Назад, `hashchange`, відмова охоронця.
 */
import assert from "node:assert/strict";
import { cpSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { stop, waitBarReady, goTasks } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 52000;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CONN_MODULES = path.join(ROOT, "tests", "fixtures", "modules-conn");
const MOCKUP = (page) => `<!doctype html><html><body><h1>${page}</h1></body></html>`;
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
  /* Друга половина: `hashchange` на задачу з ІНШОГО простору — `goTo` її перемикає (явна навігація, не старт). */
  await page.evaluate(() => { location.hash = "#sp=alpha&t=ta&it=it1&p=poshuk"; });
  /* Хеш уже наш (ми його вписали) — чекаємо ДІЮ: сервер перемкнено на задачу іншого простору, а оболонка живе в ній (смуга: «Задача A»). */
  await page.waitForFunction(async () => (await (await fetch("/api/tasks")).json()).current === "ta", null, { timeout: 20000 });
  await page.waitForFunction(() => /Задача A/.test(document.getElementById("bar")?.textContent || ""), null, { timeout: 20000 });
  await frameReady(page, /it=it1.*page=poshuk/);
  assert.match(await hash(page), /t=ta/);
  assert.match(await hash(page), /sp=alpha/);
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

  /* Свідок, що спостерігач ЧУЄ присвоєння `src` (інакше «нема it2» пусте): та сама адреса без `m=o` — «Макет» вантажить it1. */
  const p2 = await browser.newPage({ viewport: VIEW });
  t.after(() => p2.close());
  await p2.addInitScript(() => {
    window.__srcs = [];
    new MutationObserver((ms) => {
      for (const m of ms) {
        const f = document.getElementById("frame");
        if (f && (m.target === f || [...(m.addedNodes || [])].includes(f))) window.__srcs.push(f.getAttribute("src") || "");
      }
    }).observe(document, { subtree: true, attributes: true, attributeFilter: ["src"], childList: true });
  });
  await p2.goto(`${url}/app/#t=${t0}&it=it1&p=holovna`);
  await frameReady(p2, /it=it1.*page=holovna/);
  const srcs2 = await p2.evaluate(() => window.__srcs);
  assert.ok(srcs2.some((s) => /it=it1/.test(s)), `спостерігач не бачить присвоєнь src: ${JSON.stringify(srcs2)}`);
  assert.ok(!srcs2.some((s) => /it=it2/.test(s)), `у «Макеті» перший рендер теж уже з it1: ${JSON.stringify(srcs2)}`);
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

test("T4-10: перемикання задачі ззовні переживає перезавантаження: reload іде за сервером, task-switch сторінкою не шлеться", async (t) => {
  const A = twoIterations();
  const B = taskFixture({ html: PAGE });
  const { child, url } = await startServer(null, { portBase: PORT_BASE + 900, spaces: [
    { name: "Alpha", id: "alpha", color: "space-1", tasks: { ta: { dir: A, title: "Задача A" }, tb: { dir: B.dir, title: "Задача B" } } },
  ] });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${url}/app/#sp=alpha&t=ta&it=it1&p=poshuk`);
  await page.waitForFunction(() => /t=ta/.test(location.hash) && /it=it1/.test(location.hash));
  await frameReady(page, /it=it1.*page=poshuk/);
  const sw = await page.request.post(`${url}/api/task-switch`, { data: { id: "tb" } });
  assert.equal(sw.status(), 200);
  const switches = [];
  page.on("request", (r) => { if (new URL(r.url()).pathname === "/api/task-switch") switches.push(r.method()); });
  await page.reload();
  await page.waitForFunction(() => /t=tb/.test(location.hash), null, { timeout: 20000 });
  assert.doesNotMatch(await hash(page), /it=it1&p=poshuk/, "ітерація/сторінка задачі A не перенесені в B");
  assert.equal((await (await page.request.get(`${url}/api/tasks`)).json()).current, "tb");
  assert.deepEqual(switches, []);
});

const NB = '[data-act="navback"]';
const NF = '[data-act="navfwd"]';
const waitHash = (page, re) => page.waitForFunction((s) => new RegExp(s).test(location.hash), re.source);

test("T5-1: три переходи (сторінка, ітерація, режим) — три записи; ← → і ⌘[ ⌘] проходять їх; кнопки вимикаються на краях; pushState нуль", async (t) => {
  const { page } = await boot(t, 1300);
  await waitHash(page, /p=holovna/);
  assert.equal(await page.isDisabled(NB), true, "на першому записі ← вимкнена");
  assert.equal(await page.isDisabled(NF), true);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await waitHash(page, /p=poshuk/);
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="iter"][data-val="it1"]');
  await waitHash(page, /it=it1/);
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await waitHash(page, /m=o/);
  assert.equal(await page.isDisabled(NB), false);

  await page.click(NB);                                        // з «Огляду» — у «Макет» it1/holovna (вибір ітерації скинув сторінку на першу)
  await page.waitForFunction(() => !/m=o/.test(location.hash) && /it=it1/.test(location.hash));
  await page.waitForSelector("#stage:not([hidden])");
  await page.keyboard.press("Meta+BracketLeft");               // → it2/poshuk (стан до вибору it1)
  await waitHash(page, /it=it2.*p=poshuk/);
  await frameReady(page, /it=it2.*page=poshuk/);
  await page.keyboard.press("Control+BracketLeft");            // → it2/holovna
  await waitHash(page, /it=it2.*p=holovna/);
  await frameReady(page, /it=it2.*page=holovna/);
  assert.equal(await page.isDisabled(NB), true);
  await page.click(NF);
  await waitHash(page, /p=poshuk/);
  assert.equal(await page.isDisabled(NF), false);
  assert.equal(await pushes(page), 0, "pushState не викликано жодного разу");
});

test("T5-2: ⌘[ працює й з фокусом у макеті (окремий захоплювач у рамці); рамка не йде по власній історії", async (t) => {
  const { page } = await boot(t, 1400);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await waitHash(page, /p=poshuk/);
  await frameReady(page, /page=poshuk/);
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("h1");
  await f.click("h1");
  await page.keyboard.press("Meta+BracketLeft");
  await waitHash(page, /p=holovna/);
  await frameReady(page, /page=holovna/);
});

test("T5-3: перехід за посиланням у макеті — запис стека; Назад — рівно одне завантаження рамки", async (t) => {
  const dir = twoIterations();
  writeFileSync(path.join(dir, "iterations", "it2", "holovna", "index.html"),
    `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><a id="go" href="../poshuk/index.html">go</a></body></html>`);
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 1500 });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  let loads = 0;
  page.on("request", (r) => { if (/\/commented\?/.test(r.url())) loads += 1; });
  await page.goto(`${url}/app/`);
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("#go", { timeout: 20000 });
  await f.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  await f.click("#go");
  await waitHash(page, /p=poshuk/);
  await frameReady(page, /page=poshuk/);
  assert.equal(await page.isDisabled(NB), false, "перехід за посиланням — запис стека");
  const before = loads;
  await page.click(NB);
  await frameReady(page, /page=holovna/);
  await new Promise((r) => setTimeout(r, 1500));
  assert.equal(loads - before, 1, "Назад — рівно одне завантаження рамки");
});

test("T5-4: «Оновити» — у «Макеті» перезавантажує лише макет (адреса й стек ті самі)", async (t) => {
  const { page } = await boot(t, 1600);
  await frameReady(page, /page=holovna/);
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("h1");
  await f.evaluate(() => { window.__marker = 1; });
  const h0 = await hash(page);
  await page.click('[data-act="navreload"]');
  await page.waitForFunction(async () => {
    const w = document.getElementById("frame").contentWindow;
    return w.__marker === undefined && !!w.document.querySelector("h1");
  }, null, { timeout: 10000 });
  assert.equal(await hash(page), h0);
  assert.equal(await page.isDisabled(NB), true, "перезавантаження — не перехід");
});

test("T5-6: ⌘R, потім Назад — стек пережив перезавантаження (sessionStorage)", async (t) => {
  const { page } = await boot(t, 1700);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await waitHash(page, /p=poshuk/);
  await page.reload();
  await frameReady(page, /page=poshuk/);
  await page.waitForSelector(`${NB}:not([disabled])`);
  await page.click(NB);
  await waitHash(page, /p=holovna/);
  await frameReady(page, /page=holovna/);
  await page.waitForSelector(`${NF}:not([disabled])`);
});

test("T5-7: hashchange (адресу вписали руками) веде в місце й записується; Назад вертає", async (t) => {
  const { page } = await boot(t, 1800);
  await waitHash(page, /p=holovna/);
  const t0 = await page.evaluate(() => /(?:^#|&)t=([^&]+)/.exec(location.hash)[1]);
  await page.evaluate((id) => { location.hash = `#t=${id}&it=it1&p=poshuk`; }, t0);
  await frameReady(page, /it=it1.*page=poshuk/);
  await page.waitForFunction(() => /it=it1/.test(location.hash));
  await page.click(NB);
  await frameReady(page, /it=it2.*page=holovna/);
});

test("T5-8: запис стека вказує на видалену ітерацію — Назад тихо веде на запасну (остання ітерація, перша сторінка), без тосту", async (t) => {
  const { page } = await boot(t, 1900);
  await waitHash(page, /it=it2.*p=holovna/);                    // запис 1: it2/holovna
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="iter"][data-val="it1"]');
  await waitHash(page, /it=it1.*p=holovna/);                    // запис 2: it1/holovna
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="iter"][data-val="it2"]');
  await waitHash(page, /it=it2/);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await waitHash(page, /it=it2.*p=poshuk/);                     // записи 3 (it2/holovna) і 4 (it2/poshuk)
  await page.evaluate(async () => { await fetch("/api/iteration-delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: "it1" }) }); });
  await page.click(NB);                                         // → запис 3: it2/holovna
  await waitHash(page, /it=it2.*p=holovna/);
  await page.click(NB);                                         // → запис 2: it1 (видалена) — падаємо на it2/holovna
  await page.waitForFunction(() => /it=it2/.test(location.hash) && /p=holovna/.test(location.hash) && !/it=it1/.test(location.hash));
  await frameReady(page, /it=it2.*page=holovna/);
  assert.equal(await page.evaluate(() => document.getElementById("cv-toast")?.classList.contains("show") ?? false), false, "тосту нема");
  assert.equal(await page.evaluate(() => document.querySelector("#pages-panel .pp-err") === null), true, "панель без помилки сторінок");
});

/* ── T5-5: майстер незбережених налаштувань не пускає Назад (прилади — з `wizard.test.mjs`) ── */

let modulesDir;
function wizardModules() {
  if (modulesDir) return modulesDir;
  modulesDir = mkdtempSync(path.join(tmpdir(), "dc-nav-mods-"));
  cpSync(CONN_MODULES, modulesDir, { recursive: true });
  const dir = path.join(modulesDir, "memo-note");
  mkdirSync(dir);
  writeFileSync(path.join(dir, "module.json"), JSON.stringify({
    api: 1, id: "memo-note", name: "Memo note (test)", version: "1.0.0", roles: ["notify"],
    settings: [{ key: "label", type: "text", label: "Label (test)", default: "dflt-label" }],
  }));
  writeFileSync(path.join(dir, "server.py"),
    "def check(ctx):\n    return {'ok': True, 'detail': 'note ok'}\n"
    + "def mute_state(ctx):\n    return []\n"
    + "def mute_set(ctx, channel, muted, by):\n    return bool(muted)\n");
  return modulesDir;
}
const studio = () => [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: taskFixture({ html: MOCKUP }).dir, title: "Задача" } } }];
const step = (page, n) => page.waitForSelector(`#tasks-home .wz[data-step="${n}"]`, { timeout: 15000 });
const next = (page) => page.click('#tasks-home .wz [data-a="ok"]');
const card = (id) => `#tasks-home .wz-card[data-id="${id}"]`;
const pick = (id) => `#tasks-home input[data-wz-pick][value="${id}"]`;
const field = (id, key) => `${card(id)} [data-cn-field="${key}"]`;
async function openFromMenu(page, rows = 1) {
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction((n) => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === n, rows);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await step(page, 1);
}
async function pickAndNext(page, ids) {
  for (const id of ids) await page.locator(pick(id)).check();
  await next(page);
  await step(page, 3);
  for (const id of ids) await page.waitForSelector(card(id));
}
async function bootWizard(t, off) {
  const server = await startServer(null, { portBase: PORT_BASE + off, env: { DEAI_EXTRA_MODULES: wizardModules() }, spaces: studio() });
  t.after(() => stop(server.child));
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page);
  return page;
}

test("T5-5: майстер із незбереженим на кроці 3 відмовляє — ⌘[ не змінює ні адреси, ні стека; «Відкинути» — веде далі", async (t) => {
  const page = await bootWizard(t, 1200);
  await waitHash(page, /t=t1/);
  await page.click('#tabs [data-act="home"]');                       // запис 2: «Задачі»
  await waitHash(page, /h=tasks/);
  await openFromMenu(page);                                           // «Новий простір…» — майстер
  await page.fill("#sp-name", "Client");
  await next(page); await step(page, 2);
  await pickAndNext(page, ["memo-publish"]);                          // крок 3
  await page.fill(field("memo-publish", "note"), "draft");
  const before = await hash(page);
  await page.keyboard.press("Meta+BracketLeft");                      // ← у наш стек: goTo → wiz.requestExit → питання
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  await page.waitForFunction(() => document.querySelector('#tasks-home .wz[data-step="3"]'));
  assert.equal(await hash(page), before, "адреса не змінилась");
  assert.equal(await page.inputValue(field("memo-publish", "note")), "draft", "набране на місці");
  await page.keyboard.press("Meta+BracketLeft");
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="ok"]');             // «Відкинути»
  await page.waitForSelector('[data-act="page"][data-val="holovna"]', { timeout: 15000 });
  assert.doesNotMatch(await hash(page), /h=tasks/);
});

test("T5-9: вихід із «Задач» — адреса не тримає h=tasks, поки render() ще дочитується (⌘R у цьому вікні не відкриє «Задачі»)", async (t) => {
  const { page } = await boot(t, 2000);
  await waitHash(page, /p=holovna/);
  await page.click('#tabs [data-act="home"]');
  await waitHash(page, /h=tasks/);
  /* Повільні сторінки ітерації розтягують `render()` — вікно, у якому оверлей уже схований, а адреса ще не переписана. */
  await page.route("**/api/iteration-pages*", async (route) => { await new Promise((r) => setTimeout(r, 2500)); await route.continue(); });
  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"));
  assert.doesNotMatch(await hash(page), /h=tasks/, "оверлей схований — адреса вже без h=tasks");
  await page.unroute("**/api/iteration-pages*");
  await frameReady(page, /page=holovna/);
  assert.doesNotMatch(await hash(page), /h=tasks/);
  await page.click(NB);                                          // запис «Задачі» лишився одним записом: Назад веде до нього
  await waitHash(page, /h=tasks/);
});
