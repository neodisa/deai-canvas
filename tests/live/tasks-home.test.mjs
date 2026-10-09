/**
 * Екран «Задачі» (батч 1.52, Task 6) — живе проведення.
 *
 * Розмітку стережуть юніти (`tests/tasks-home.test.mjs`); тут те, чого вони
 * не бачать: що логотип справді відкриває екран, що сцена під ним схована
 * (а не лише перекрита), що Enter переключає задачу й повертає макет, що задача
 * без теки НЕ переключається, що ⌘K веде туди ж, що «Команда» читає живу
 * відповідь, а на 1024 смуга не вилазить за вікно.
 */
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя база: `node --test` крутить файли паралельно (`tests/live-ports.test.mjs`
   стереже, що жодна база не збігається з чужою). */
const PORT_BASE = 18000;

const HTML = () => "<!doctype html><h1>Фікстура</h1>";

/** Сервер: 10 задач «Задача N», одна без теки («Привид»), fixture — поточна.
 *  `team` — рядки дашборда (масив) або рядок-шлях до неіснуючого файла (збій). */
async function boot(t, portBase, { team } = {}) {
  const { dir } = taskFixture({ html: HTML });
  const extraTasks = {};
  for (let i = 0; i < 10; i += 1) {
    extraTasks[`t${i}`] = { dir, jira: `LIGA-${10000 + i}`, title: `LIGA-${10000 + i} · Задача ${i} для пошуку`,
      profile: i % 2 ? "united" : "liga360" };
  }
  extraTasks.ghost = { dir: `${dir}-нема-на-цій-машині`, jira: "LIGA-7021", title: "Привид без теки" };
  const env = {};
  if (typeof team === "string") env.DC_TEAM_FAKE = team;
  else if (team) {
    const f = path.join(mkdtempSync(path.join(tmpdir(), "dc-team-")), "team.json");
    writeFileSync(f, JSON.stringify(team));
    env.DC_TEAM_FAKE = f;
  }
  const { child, url } = await startServer(dir, { portBase, extraTasks, env });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-act="home"]');
  return { page, url, dir };
}

const TEAM = [
  { id: "t7", name: "Задача 7 для пошуку", jira: "LIGA-7022", designer: "Ольга",
    jira_status: "В роботі", jira_status_cat: "indeterminate", updated_at: new Date(Date.now() - 3600e3).toISOString(),
    iterations: 2, pages: 3, open_comments: 1, code_url: "https://example.com/p/t7" },
  { id: "colleague", name: "Задача колеги", jira: "LIGA-7023", designer: "Олег",
    jira_status: "Готово", jira_status_cat: "done", updated_at: new Date(Date.now() - 2 * 86400e3).toISOString(),
    iterations: 1, pages: 1, open_comments: 0, code_url: "https://example.com/p/colleague",
    thumb_url: "http://127.0.0.1:9/nope.png" },
];

const cur = async (url) => (await (await fetch(`${url}/api/tasks`)).json()).current;
const homeShown = (page) => page.evaluate(() => {
  const h = document.getElementById("tasks-home");
  return !!h && !h.hidden && getComputedStyle(h).display !== "none";
});
const stageShown = (page) => page.evaluate(() => getComputedStyle(document.getElementById("stage")).display !== "none");
const cardIds = (page) => page.$$eval("#tasks-home .th-card", (els) => els.map((e) => e.dataset.id));

test("логотип відкриває екран, сцена схована; пошук «Задача 7» → 1 картка; Enter відкриває t7 і повертає макет", async (t) => {
  const { page, url } = await boot(t, PORT_BASE);
  assert.equal(await homeShown(page), false, "перевірка недійсна: екран відкритий до кліку");
  assert.equal(await stageShown(page), true);

  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await homeShown(page), true, "екран «Задачі» не зʼявився");
  assert.equal(await stageShown(page), false, "сцена лишилась видимою під екраном");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "th-q", "фокус одразу в пошуку");
  assert.match(await page.textContent("#tasks-home .th-tab--on"), /Мої · 12/);
  assert.ok((await cardIds(page)).includes("fixture"));
  assert.equal(await page.locator("#tasks-home .th-card--cur").getAttribute("data-id"), "fixture", "поточна задача позначена");

  await page.keyboard.type("Задача 7");
  await page.waitForFunction(() => document.querySelectorAll("#tasks-home .th-card").length === 1);
  assert.deepEqual(await cardIds(page), ["t7"]);
  assert.equal(await page.evaluate(() => document.activeElement?.id), "th-q", "набір не губить фокус");
  assert.ok(await page.locator("#tasks-home mark").count() > 0, "збіги підсвічені");
  assert.match(await page.textContent("#tasks-home .th-chip--on"), /Активні · 1/);

  await page.keyboard.press("Enter");
  await page.waitForFunction(async () => (await (await fetch("/api/tasks")).json()).current === "t7");
  assert.equal(await cur(url), "t7");
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.equal(await homeShown(page), false);
  assert.equal(await stageShown(page), true, "макет не повернувся після вибору задачі");
  assert.ok(await page.waitForSelector('#bar [data-act="mode"]', { timeout: 3000 }), "смуга не повернула контролів задачі");
});

test("клавіатура: / фокусує пошук, Esc чистить і знімає фокус, ↓ веде до карток, стрілки ходять, Enter відкриває", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 100);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press("/");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "th-q", "/ не вів у пошук");
  assert.equal(await page.inputValue("#th-q"), "", "«/» не мусить потрапляти в поле");

  await page.keyboard.type("Задача");
  await page.keyboard.press("Escape");
  assert.equal(await page.inputValue("#th-q"), "", "перший Esc чистить запит");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "th-q", "перший Esc не знімає фокус");
  await page.keyboard.press("Escape");
  assert.notEqual(await page.evaluate(() => document.activeElement?.id), "th-q", "другий Esc знімає фокус");

  await page.keyboard.press("/");
  await page.keyboard.press("ArrowDown");
  const first = await page.evaluate(() => document.activeElement?.dataset?.id);
  assert.equal(first, (await cardIds(page))[0], "↓ із пошуку веде на першу картку");
  await page.keyboard.press("ArrowRight");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.id), (await cardIds(page))[1]);
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowUp");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "th-q", "↑ з першого ряду вертає в пошук");

  // Enter на картці: відкрити ЦЮ задачу
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowRight");
  const second = await page.evaluate(() => document.activeElement?.dataset?.id);
  await page.keyboard.press("Enter");
  await page.waitForFunction((id) => fetch("/api/tasks").then((r) => r.json()).then((d) => d.current === id), second);
  assert.equal(await cur(url), second);
});

test("задача без теки: причина і мітка на картці, клік не переключає й не виходить з екрана", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 200);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.keyboard.type("Привид");
  await page.waitForFunction(() => document.querySelectorAll("#tasks-home .th-card").length === 1);
  const card = page.locator("#tasks-home .th-card");
  assert.equal(await card.getAttribute("aria-disabled"), "true");
  assert.match(await card.textContent(), /теки немає на цій машині/);

  /* `force`: Playwright читає `aria-disabled` як «не активний» і відмовляється
     клікати, а справжня мишка по такій картці клікає — і відповідь має бути
     причиною, а не мовчанням. */
  await card.click({ force: true });
  await page.waitForSelector("#cv-toast.show");
  assert.match(await page.textContent("#cv-toast"), /LIGA-7021.*теки немає на цій машині/);
  assert.equal(await cur(url), "fixture", "задача без теки стала поточною");
  assert.equal(await homeShown(page), true, "екран закрився після відмови");

  // Enter у пошуку веде тим самим шляхом
  await page.focus("#th-q");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(300);
  assert.equal(await cur(url), "fixture", "Enter у пошуку переключив задачу без теки");
  assert.equal(await homeShown(page), true);
});

test("⌘K → «Задачі» відкриває екран; логотип ще раз і «Назад» вертають до задачі", async (t) => {
  const { page } = await boot(t, PORT_BASE + 300);
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "Задачі");
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length >= 1);
  assert.match(await page.locator(".pal-it").first().textContent(), /Задачі/);
  await page.keyboard.press("Enter");
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await homeShown(page), true, "⌘K «Задачі» не відкрив екран");
  assert.equal(await page.locator(".pal").count(), 0, "палітра лишилась поверх екрана");
  assert.equal(await page.locator('#bar [data-dd="task"]').count(), 0, "відкрився дропдаун крихти, а не екран");

  await page.click('#bar [data-act="back"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.equal(await stageShown(page), true);
});

test("«Команда»: рядки живої відповіді, «Відкрити в канвасі» лише для своїх, превʼю — посиланням, зламаний кадр → заглушка", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 400, { team: TEAM });
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.match(await page.textContent('#tasks-home [data-v="team"]'), /Команда · 2/);

  await page.click('#tasks-home [data-th="tab"][data-v="team"]');
  await page.waitForFunction(() => document.querySelector("#tasks-home .th-tab--on")?.dataset.v === "team");
  await page.click('#tasks-home [data-th="status"][data-v="all"]');
  await page.waitForFunction(() => document.querySelectorAll("#tasks-home .th-card").length === 2);
  assert.deepEqual((await cardIds(page)).sort(), ["colleague", "t7"]);
  assert.equal(await page.locator('#tasks-home .th-sel option[value="recent"]').count(), 0, "у «Команді» нема сортування за відкриттям");

  const mine = page.locator('#tasks-home .th-card[data-id="t7"]');
  assert.match(await mine.textContent(), /Ольга/);
  assert.match(await mine.locator("button.th-lnk").textContent(), /Відкрити в канвасі/);
  const other = page.locator('#tasks-home .th-card[data-id="colleague"]');
  assert.equal(await other.locator("button.th-lnk").count(), 0, "чужа задача отримала «Відкрити в канвасі»");
  const a = other.locator("a.th-lnk");
  assert.equal(await a.getAttribute("href"), "https://example.com/p/colleague");
  assert.equal(await a.getAttribute("target"), "_blank");
  assert.match(await a.getAttribute("rel"), /noopener/);
  await page.waitForFunction(() => document.querySelector('.th-card[data-id="colleague"] .th-none'), null, { timeout: 5000 });
  assert.match(await other.locator(".th-none").textContent(), /кадр недоступний/);

  // клік по посиланню не відкриває задачу (і не вилітає з екрана)
  assert.equal(await cur(url), "fixture");

  await mine.locator("button.th-lnk").click();
  await page.waitForFunction(() => fetch("/api/tasks").then((r) => r.json()).then((d) => d.current === "t7"));
  assert.equal(await cur(url), "t7");
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
});

test("збій команди: банер із причиною, «Спробувати ще» перепитує з refresh=1; «Мої» живі", async (t) => {
  const { page } = await boot(t, PORT_BASE + 500, { team: "/нема/такого/team.json" });
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.click('#tasks-home [data-th="tab"][data-v="team"]');
  await page.waitForSelector("#tasks-home .th-banner");
  assert.match(await page.textContent("#tasks-home .th-banner"), /Дашборд команди недоступний/);
  assert.match(await page.textContent('#tasks-home [data-v="team"]'), /Команда · —/);
  assert.equal(await page.locator("#tasks-home .th-card").count(), 0);

  const req = page.waitForRequest((r) => r.url().includes("/api/tasks-overview?refresh=1"));
  await page.click('#tasks-home [data-th="retry"]');
  await req;

  await page.click('#tasks-home [data-th="tab"][data-v="mine"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator("#tasks-home .th-banner").count(), 0, "банер збою команди на «Моїх»");
});

test("вкладка й фільтри переживають закриття екрана, запит — ні; «Скинути фільтри» на порожній видачі", async (t) => {
  const { page } = await boot(t, PORT_BASE + 600, { team: TEAM });
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.click('#tasks-home [data-th="profile"][data-v="united"]');
  await page.keyboard.press("/");
  await page.keyboard.type("Задача");
  await page.click('#bar [data-act="back"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.inputValue("#th-q"), "", "запит пережив закриття");
  assert.equal(await page.locator('#tasks-home [data-v="united"]').getAttribute("aria-pressed"), "true", "чіп напрямку забутий");

  await page.keyboard.type("zzzнемає");
  await page.waitForSelector("#tasks-home .th-empty");
  assert.match(await page.textContent("#tasks-home .th-empty"), /Нічого не знайдено/);
  await page.click('#tasks-home [data-th="reset"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.inputValue("#th-q"), "");
  assert.equal(await page.locator('#tasks-home [data-v="united"]').getAttribute("aria-pressed"), "false");
});

test("геометрія на 1024: смуга не ширша за вікно, сторінка без горизонтальної прокрутки, у «Командi» теж", async (t) => {
  const { page } = await boot(t, PORT_BASE + 700, { team: TEAM });
  await page.setViewportSize({ width: 1024, height: 800 });
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  const measure = () => page.evaluate(() => {
    const bar = document.querySelector("#bar .bar");
    const home = document.getElementById("tasks-home");
    return {
      bar: bar.scrollWidth, barBox: bar.getBoundingClientRect().width,
      doc: document.documentElement.scrollWidth, home: home.scrollWidth, homeClient: home.clientWidth,
      win: window.innerWidth,
    };
  });
  for (const tab of ["mine", "team"]) {
    await page.click(`#tasks-home [data-th="tab"][data-v="${tab}"]`);
    await page.waitForFunction((v) => document.querySelector("#tasks-home .th-tab--on")?.dataset.v === v, tab);
    const m = await measure();
    assert.ok(m.bar <= m.win && m.barBox <= m.win, `[${tab}] смуга ${m.bar}px ширша за вікно ${m.win}px`);
    assert.ok(m.doc <= m.win, `[${tab}] сторінка з горизонтальною прокруткою: ${m.doc} > ${m.win}`);
    assert.ok(m.home <= m.homeClient, `[${tab}] екран прокручується вбік: ${m.home} > ${m.homeClient}`);
  }
});

test("логотип і ⌘K читаються окремо: між ними відступ і риска-роздільник", async (t) => {
  const { page } = await boot(t, PORT_BASE + 800);
  const g = await page.evaluate(() => {
    const logo = document.querySelector("#bar .logo-btn").getBoundingClientRect();
    const pal = document.querySelector("#bar .pal-open");
    const pr = pal.getBoundingClientRect();
    return { gap: pr.left - logo.right, line: getComputedStyle(pal).borderLeftWidth };
  });
  assert.ok(g.gap >= 8, `логотип упритул до палітри: ${g.gap}px`);
  assert.equal(g.line, "1px", "роздільника між логотипом і палітрою нема");
});

/** Усі `/api/*` запити сторінки з моменту виклику (крім дозволених «фонових»). */
function watchApi(page) {
  const seen = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api/")) seen.push(`${r.method()} ${u.pathname}`);
  });
  return seen;
}
const QUIET_OK = /\/api\/(claude-status|tasks-overview|task-thumb|tuner|shoot-progress)$/;

test("під екраном «Задачі» канвас спить: фокус вікна й опитування відбитка не б'ють у схований макет", async (t) => {
  const { page } = await boot(t, PORT_BASE + 900);
  await page.waitForSelector("#frame");
  await page.waitForTimeout(800);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.waitForTimeout(300);
  const seen = watchApi(page);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  // опитування відбитка — раз на 2 с: 2.6 с покривають щонайменше один тік
  await page.waitForTimeout(2600);
  const bad = seen.filter((x) => !QUIET_OK.test(x.split(" ")[1]));
  assert.deepEqual(bad, [], `схований макет отримав запити під екраном: ${bad.join(", ")}`);
  assert.equal(await page.locator('.cv-notice[data-notice="frame-changed"]').count(), 0);
});

test("те саме в «Огляді»: фокус вікна не перебудовує полотно й не запускає зйомку під екраном", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1000);
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  await page.waitForTimeout(1500);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.waitForTimeout(300);
  const seen = watchApi(page);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForTimeout(800);
  const bad = seen.filter((x) => !QUIET_OK.test(x.split(" ")[1]));
  assert.deepEqual(bad, [], `полотно під екраном ворушилось: ${bad.join(", ")}`);
});

test("клавіші задачі під екраном «Задачі» німі: ⌘G не групує, ⌥M не міняє режим", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1100);
  await page.waitForSelector(".panel [data-page]");
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.evaluate(() => document.activeElement.blur());
  const seen = watchApi(page);
  await page.keyboard.press("Control+g");
  await page.keyboard.press("Alt+m");
  await page.keyboard.press("Control+Shift+\\");
  await page.waitForTimeout(700);
  assert.deepEqual(seen.filter((x) => /page-group|task\b|shoot/.test(x)), [], "клавіша діє на схований макет");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "⌘G відкрив діалог над екраном");
  assert.equal(await page.evaluate(() => document.documentElement.classList.contains("cv-clean")), false, "чистий перегляд увімкнувся під екраном");
  assert.equal(await page.locator("#canvas").evaluate((e) => e.hidden), true, "⌥M перемкнув на «Огляд»");
});

test("задача, переключена поза вкладкою: екран порівнює зі свіжою поточною, а не з застарілим списком", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 1200);
  await page.waitForSelector('#bar [data-dd="task"]');
  // сервер міняє поточну задачу «за спиною» вкладки (task-new, друге вікно)
  await page.evaluate(() => fetch("/api/task-switch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: "t3" }) }));
  assert.equal(await cur(url), "t3");
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="fixture"]');
  // вкладка досі вважає поточною `fixture` — клік по ній мусить ПЕРЕКЛЮЧИТИ, а не «вийти»
  await page.click('#tasks-home .th-card[data-id="fixture"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.equal(await cur(url), "fixture", "вихід без переключення: на екрані лишилась чужа задача");
});

test("вихід з екрана вертає фокус на логотип", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1300);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.click('#bar [data-act="back"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.waitForFunction(() => document.activeElement?.dataset?.act === "home");
});

test("повторний запит не вдався, дані вже є: «Мої» лишаються, зверху банер", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1400, { team: "/нема/такого/team.json" });
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.route("**/api/tasks-overview*", (r) => r.abort());
  await page.click('#tasks-home [data-th="tab"][data-v="team"]');
  await page.click('#tasks-home [data-th="retry"]');
  await page.waitForFunction(() => /Не вдалося завантажити/.test(document.getElementById("tasks-home").textContent));
  await page.click('#tasks-home [data-th="tab"][data-v="mine"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.match(await page.textContent("#tasks-home .th-banner"), /Не вдалося завантажити/);
  assert.match(await page.textContent('#tasks-home [data-v="mine"]'), /Мої · 12/, "добрі дані стерто збоєм повтору");
});

test("збережений фільтр, якого вже нема в даних, не лишається невидимим", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1500);
  await page.evaluate(() => localStorage.setItem("dc-tasks-ui", JSON.stringify({ tab: "mine", status: "all", sort: "recent", profiles: ["gone"], designers: [] })));
  await page.reload();
  await page.waitForSelector('#bar [data-act="home"]');
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator('#tasks-home [data-th="profile"][aria-pressed="true"]').count(), 0);
  assert.ok((await cardIds(page)).length > 1, "невидимий фільтр сховав усі картки");
  assert.deepEqual(JSON.parse(await page.evaluate(() => localStorage.getItem("dc-tasks-ui"))).profiles, [], "зниклий фільтр лишився в сховищі");
});

test("мова: перемикання з ⌘K на екрані «Задачі» перемальовує сам екран", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1600);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.match(await page.textContent("#tasks-home .th-tab--on"), /Мої/);
  await page.evaluate(() => document.activeElement.blur());
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "english");
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length >= 1);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /Mine/.test(document.querySelector("#tasks-home .th-tab--on")?.textContent || ""));
  assert.match(await page.textContent("#tasks-home h1"), /Tasks/);
  assert.match(await page.getAttribute("#th-q", "placeholder"), /Key, title/);
});

test("гонка: поточну переключили дропдауном, екран ще вантажиться — клік по картці старої задачі ПЕРЕКЛЮЧАЄ", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 1700);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="fixture"]');   // homeData.current = fixture
  await page.click('#bar [data-act="back"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.click('#bar [data-dd="task"]');
  await page.click('#bar [data-act="task"][data-val="t3"]');
  await page.waitForFunction(() => fetch("/api/tasks").then((r) => r.json()).then((d) => d.current === "t3"));
  // відповідь екрана затримана: до її приходу він показує СТАРІ дані (current = fixture)
  await page.route("**/api/tasks-overview*", async (r) => { await new Promise((d) => setTimeout(d, 1500)); await r.continue(); });
  await page.click('#bar [data-act="home"]');
  await page.click('#tasks-home .th-card[data-id="fixture"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.equal(await cur(url), "fixture", "клік по старій поточній пропустив переключення: лишилась t3");
});

test("вхід з чистого перегляду: екран зʼявляється зі смугою, режим чистого перегляду знято", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1800);
  await page.keyboard.press("Control+Shift+Backslash");
  await page.waitForFunction(() => document.documentElement.classList.contains("cv-clean"));
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "Задачі");
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length >= 1);
  await page.keyboard.press("Enter");
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.evaluate(() => document.documentElement.classList.contains("cv-clean")), false, "чистий перегляд лишився");
  assert.equal(await homeShown(page), true, "екран порожній/схований");
  assert.ok(await page.locator("#bar .bar").isVisible(), "смуги нема");
});

