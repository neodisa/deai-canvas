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
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
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
      /* 4d-4a: напрямок — лише `track` (адаптера, що виводив мітку з `profile`, нема): запис ЛІГИ несе обидва ключі, як після кроку
         `liga-4d4a`. Напрямків простору в ізольованому режимі нема → мітка — значення як є, нижнім регістром. */
      profile: i % 2 ? "united" : "liga360", track: i % 2 ? "united" : "liga360" };
  }
  extraTasks.ghost = { dir: `${dir}-нема-на-цій-машині`, jira: "LIGA-7021", title: "Привид без теки" };
  const env = {};
  if (typeof team === "string") env.DC_TEAM_FAKE = team;
  else if (team) {
    const f = path.join(mkdtempSync(path.join(tmpdir(), "dc-team-")), "team.json");
    writeFileSync(f, JSON.stringify(team));
    env.DC_TEAM_FAKE = f;
  }
  const { child, url, tasksFile } = await startServer(dir, { portBase, extraTasks, env, supabase: team !== undefined });   // 4d-4b: вкладку «Команда» веде явний запис дашборда мігрованої ЛІГИ
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#tabs [data-act="home"]');
  return { page, url, dir, tasksFile };
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

  await page.click('#tabs [data-act="home"]');
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
  await page.click('#tabs [data-act="home"]');
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
  await page.click('#tabs [data-act="home"]');
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

  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.equal(await stageShown(page), true);
});

test("«Команда»: рядки живої відповіді, «Відкрити в канвасі» лише для своїх, превʼю — посиланням, зламаний кадр → заглушка", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 400, { team: TEAM });
  await page.click('#tabs [data-act="home"]');
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
  await page.click('#tabs [data-act="home"]');
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

test("мітки ЛІГИ з профілю (без tags): чипи United/LIGA360, клік фільтрує, вибір переживає закриття екрана, перезавантаження сторінки; запит — ні; «Скинути фільтри» на порожній видачі", async (t) => {
  const { page } = await boot(t, PORT_BASE + 600, { team: TEAM });
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  const chips = await page.$$eval('#tasks-home [data-th="tag"]', (els) => els.map((e) => e.textContent.trim()));
  assert.equal(chips.length, 2, `чипи міток: ${JSON.stringify(chips)}`);
  assert.ok(chips.some((c) => c.startsWith("united")) && chips.some((c) => c.startsWith("liga360")), `чипи: ${JSON.stringify(chips)}`);
  await page.click('#tasks-home [data-th="tag"][data-v="united"]');
  const only = await cardIds(page);
  assert.deepEqual([...only].sort(), ["t1", "t3", "t5", "t7", "t9"], `фільтр United видав не рівно United-задачі: ${only}`);
  await page.keyboard.press("/");
  await page.keyboard.type("Задача");
  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.inputValue("#th-q"), "", "запит пережив закриття");
  assert.equal(await page.locator('#tasks-home [data-v="united"]').getAttribute("aria-pressed"), "true", "чіп мітки забутий");
  assert.deepEqual(JSON.parse(await page.evaluate(() => localStorage.getItem("dc-tasks-ui"))).tags, ["united"], "стан збережено не під ключем tags");

  await page.reload();
  await page.waitForSelector('#tabs [data-act="home"]');
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator('#tasks-home [data-v="united"]').getAttribute("aria-pressed"), "true", "чіп мітки не пережив перезавантаження");

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
  await page.click('#tabs [data-act="home"]');
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

/* Перевірка «логотип і ⌘K читаються окремо: відступ і риска» прибрана в 0.25.0: кнопки палітри в смузі більше нема,
   логотип живе в рядку вкладок `#tabs` (його геометрію стереже `bar-narrow.test.mjs` і `tabs.test.mjs`). */

/** Усі `/api/*` запити сторінки з моменту виклику (крім дозволених «фонових»). */
function watchApi(page) {
  const seen = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.pathname.startsWith("/api/")) seen.push(`${r.method()} ${u.pathname}`);
  });
  return seen;
}
/* `spaces`: повернення фокуса на відкритий екран «Задачі» перечитує його (`refreshHomeOnReturn` →
   `loadHome` → перелік просторів, потім огляд) — це «звичайне» перечитування самого екрана, а не
   запит до схованого макета. Жоден ІНШИЙ `space*` (`space-peek`, `space-new`…) у цей список не
   потрапляє: без діалогу вони під екраном мовчать (їх теж стереже перевірка нижче). */
const QUIET_OK = /\/api\/(claude-status|tasks-overview|task-thumb|tuner|shoot-progress|spaces)$/;
/* `local-comments` сюди НЕ входить (0.27.0, Б2.1): `focus` перечитує локальні піни (`cmtRefreshLocal`), але під екраном
   «Задачі» мовчить — макет схований, а вихід з екрана однаково перезавантажує рамку. */

test("під екраном «Задачі» канвас спить: фокус вікна й опитування відбитка не б'ють у схований макет", async (t) => {
  const { page } = await boot(t, PORT_BASE + 900);
  await page.waitForSelector("#frame");
  await page.waitForTimeout(800);
  await page.click('#tabs [data-act="home"]');
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

test("повернення до вікна під екраном «Задачі»: пара focus+visibilitychange — рівно одне перечитування екрана, жодного іншого `space*`", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1900);
  await page.waitForSelector("#frame");
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.waitForTimeout(1000);   // gap 800 мс від можливого попереднього оновлення
  const seen = watchApi(page);
  /* Одне повернення до вікна браузер сповіщає двома подіями. */
  await page.evaluate(() => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
  await page.waitForTimeout(1200);
  const n = (what) => seen.filter((x) => x === what).length;
  assert.equal(n("GET /api/spaces"), 1, `GET /api/spaces ×${n("GET /api/spaces")} на пару focus+visibilitychange (${seen.join(", ")})`);
  assert.equal(n("GET /api/tasks-overview"), 1, `GET /api/tasks-overview ×${n("GET /api/tasks-overview")} на пару focus+visibilitychange`);
  const other = seen.filter((x) => /\/api\/space[^s]|\/api\/space-/.test(x));
  assert.deepEqual(other, [], `екран питає ще й інше про простори: ${other.join(", ")}`);
});

test("те саме в «Огляді»: фокус вікна не перебудовує полотно й не запускає зйомку під екраном", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1000);
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  await page.waitForTimeout(1500);
  await page.click('#tabs [data-act="home"]');
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
  await page.click('#tabs [data-act="home"]');
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
  await page.waitForSelector('#bar .crumb--title');
  // сервер міняє поточну задачу «за спиною» вкладки (task-new, друге вікно)
  await page.evaluate(() => fetch("/api/task-switch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: "t3" }) }));
  assert.equal(await cur(url), "t3");
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="fixture"]');
  // вкладка досі вважає поточною `fixture` — клік по ній мусить ПЕРЕКЛЮЧИТИ, а не «вийти»
  await page.click('#tasks-home .th-card[data-id="fixture"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  assert.equal(await cur(url), "fixture", "вихід без переключення: на екрані лишилась чужа задача");
});

test("вихід з екрана вертає фокус на активну вкладку задачі", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1300);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.waitForFunction(() => document.activeElement?.dataset?.act === "tab" && document.activeElement.getAttribute("aria-current") === "page");
});

test("повторний запит не вдався, дані вже є: «Мої» лишаються, зверху банер", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1400, { team: "/нема/такого/team.json" });
  await page.click('#tabs [data-act="home"]');
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
  await page.evaluate(() => localStorage.setItem("dc-tasks-ui", JSON.stringify({ tab: "mine", status: "all", sort: "recent", tags: ["gone"], designers: [] })));
  await page.reload();
  await page.waitForSelector('#tabs [data-act="home"]');
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator('#tasks-home [data-th="tag"][aria-pressed="true"]').count(), 0);
  assert.ok((await cardIds(page)).length > 1, "невидимий фільтр сховав усі картки");
  assert.deepEqual(JSON.parse(await page.evaluate(() => localStorage.getItem("dc-tasks-ui"))).tags, [], "зниклий фільтр лишився в сховищі");
});

test("старий стан із зниклим `profiles: ['gone']`: мігрує, а потім чиститься — жодного чипа вибраного, у сховищі tags без «gone»", async (t) => {
  const { page } = await boot(t, PORT_BASE + 2300);
  await page.evaluate(() => localStorage.setItem("dc-tasks-ui", JSON.stringify({ tab: "mine", status: "all", sort: "recent", profiles: ["gone"], designers: [] })));
  await page.reload();
  await page.waitForSelector('#tabs [data-act="home"]');
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator('#tasks-home [data-th="tag"][aria-pressed="true"]').count(), 0, "мігрований зниклий фільтр лишився вибраним");
  assert.ok((await cardIds(page)).length > 1, "мігрований невидимий фільтр сховав картки");
  const saved = JSON.parse(await page.evaluate(() => localStorage.getItem("dc-tasks-ui")));
  assert.deepEqual(saved.tags, [], "у сховищі лишилась «gone» під tags");
  assert.equal("profiles" in saved, false, "старий ключ profiles пережив запис");
});

/* ═══════════════════════ мітки задач (4b-3, Task 5) ═══════════════════════ */

const readTasks = (file) => JSON.parse(readFileSync(file, "utf8")).tasks;

test("мітки 2: старий стан 0.10.0 (`profiles: ['united']`) мігрує — чип United уже вибраний, а новий запис іде під `tags`", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1900);
  await page.evaluate(() => localStorage.setItem("dc-tasks-ui", JSON.stringify({ tab: "mine", status: "all", sort: "recent", profiles: ["united"], designers: [] })));
  await page.reload();
  await page.waitForSelector('#tabs [data-act="home"]');
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator('#tasks-home [data-th="tag"][data-v="united"]').getAttribute("aria-pressed"), "true", "старий вибір не мігрував");
  assert.equal(await page.locator('#tasks-home [data-th="tag"][data-v="liga360"]').getAttribute("aria-pressed"), "false");
  assert.deepEqual([...(await cardIds(page))].sort(), ["t1", "t3", "t5", "t7", "t9"], "міграція не відфільтрувала картки до рівно United-задач");
  // будь-яка зміна стану пише вже новий ключ
  await page.click('#tasks-home [data-th="tag"][data-v="liga360"]');
  const saved = JSON.parse(await page.evaluate(() => localStorage.getItem("dc-tasks-ui")));
  assert.deepEqual([...saved.tags].sort(), ["liga360", "united"]);
});

test("мітки 3: «⋯» → «Мітки…» відкриває діалог (задача НЕ відкривається), збереження → картка й чипи, tasks.json; помилка — під полем, файл без змін", async (t) => {
  const { page, url, tasksFile } = await boot(t, PORT_BASE + 2000);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="t2"]');
  assert.equal(await cur(url), "fixture");

  await page.click('#tasks-home .th-more[data-id="t2"]');
  await page.click('#th-menu [data-th="tags"]');
  await page.waitForSelector('form[data-form="tags"]');
  assert.equal(await homeShown(page), true, "екран зник: «Мітки…» відкрили задачу");
  assert.equal(await cur(url), "fixture", "клік по «Мітки» переключив задачу");
  assert.equal(await page.inputValue("#tg-tags"), "liga360", "діалог не заповнений похідною міткою");

  // помилка: 33 знаки — текст під полем, діалог лишається, файл без змін
  const before = readFileSync(tasksFile, "utf8");
  await page.fill("#tg-tags", "x".repeat(33));
  await page.click('form[data-form="tags"] [data-a="ok"]');
  await page.waitForFunction(() => /до 32 знаків/.test(document.querySelector('form[data-form="tags"] [data-form-error]')?.textContent || ""));
  assert.equal(await page.locator('form[data-form="tags"]').count(), 1, "діалог закрився на помилці");
  assert.equal(readFileSync(tasksFile, "utf8"), before, "помилка змінила tasks.json");

  await page.fill("#tg-tags", "alpha, beta");
  await page.click('form[data-form="tags"] [data-a="ok"]');
  await page.waitForSelector('form[data-form="tags"]', { state: "detached" });
  assert.deepEqual(readTasks(tasksFile).t2.tags, ["alpha", "beta"], "tasks.json без міток");
  assert.equal(await cur(url), "fixture", "збереження міток переключило задачу");
  // збереження перемальовує картку (кнопка-відкривач зникає з DOM): фокус мусить дістатися нової кнопки тієї ж картки (`focusBack`)
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.id + "/" + document.activeElement?.className), "t2/th-more", "після збереження фокус загублено");
  const cardTags = await page.textContent('#tasks-home .th-card[data-id="t2"]');
  assert.match(cardTags, /alpha/, "картка не показує нову мітку");
  assert.match(cardTags, /beta/);
  assert.equal(await page.locator('#tasks-home [data-th="tag"][data-v="alpha"]').count(), 1, "чипа alpha нема");
  assert.equal(await page.locator('#tasks-home [data-th="tag"][data-v="beta"]').count(), 1, "чипа beta нема");
  // t2 втратила LIGA360, але її мають t0, t4…: чип лишається
  assert.equal(await page.locator('#tasks-home [data-th="tag"][data-v="liga360"]').count(), 1, "чип LIGA360 зник, хоч задачі t0/t4… його мають");
});

test("мітки 4: «Нова задача» з полем «Мітки» у звичайному просторі → задача має tags, чип зʼявляється на екрані", async (t) => {
  const server = await startServer(null, { portBase: PORT_BASE + 2100, spaces: [{ name: "P", id: "p", color: "space-3", tasks: {} }] });
  t.after(() => server.child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${server.url}/app/`);
  await page.waitForSelector("#tasks-home .th-empty--space");
  await page.click('#th-grid [data-th="newtask"]');
  await page.waitForSelector('#th-grid #th-new-slot form[data-form="task"]');
  assert.equal(await page.locator("#tf-tags").count(), 1, "поля «Мітки» нема у формі");
  await page.fill("#tf-title", "Задача з мітками");
  await page.fill("#tf-id", "tg1");
  await page.fill("#tf-tags", "alpha, beta");
  await page.click('form[data-form="task"] [data-a="ok"]');
  await page.waitForSelector('form[data-form="task"]', { state: "detached" });
  const file = path.join(server.spaces[0].path, "tasks.json");
  assert.deepEqual(readTasks(file).tg1.tags, ["alpha", "beta"], "задача створена без міток");
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="tg1"]');
  assert.equal(await page.locator('#tasks-home [data-th="tag"][data-v="alpha"]').count(), 1, "чипа alpha нема");
  assert.equal(await page.locator('#tasks-home [data-th="tag"][data-v="beta"]').count(), 1, "чипа beta нема");
});

test("мітки 5: клавіатура — Shift+F10 → ↓ → Enter на «Мітки…» відкриває діалог (задача НЕ відкривається), Esc закриває й вертає фокус на «⋯» картки", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 2200);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="t4"]');
  await page.focus('#tasks-home .th-card[data-id="t4"]');
  await page.keyboard.press("Shift+F10");
  await page.waitForSelector("#th-menu");
  await page.keyboard.press("ArrowDown");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.th), "tags", "↓ не стала на «Мітки…»");
  await page.keyboard.press("Enter");
  await page.waitForSelector('form[data-form="tags"]');
  assert.equal(await homeShown(page), true, "Enter на «Мітки…» відкрив задачу");
  assert.equal(await cur(url), "fixture", "Enter на «Мітки…» переключив задачу");
  await page.keyboard.press("Escape");
  await page.waitForSelector('form[data-form="tags"]', { state: "detached" });
  assert.equal(await homeShown(page), true, "Esc закрив ще й екран");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.id + "/" + document.activeElement?.className), "t4/th-more", "фокус не повернувся на «⋯» картки");
});

test("мова: перемикання з ⌘K на екрані «Задачі» перемальовує сам екран", async (t) => {
  const { page } = await boot(t, PORT_BASE + 1600);
  await page.click('#tabs [data-act="home"]');
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
  assert.match(await page.getAttribute("#th-q", "placeholder"), /Title, number, status/);
});

test("гонка: поточну переключили карткою «Задач», екран ще вантажиться — клік по картці старої задачі ПЕРЕКЛЮЧАЄ", async (t) => {
  const { page, url } = await boot(t, PORT_BASE + 1700);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="fixture"]');   // homeData.current = fixture
  await page.click('#tabs [data-act="tab"]');
  await page.waitForFunction(() => document.getElementById("tasks-home").hidden);
  /* Перемикача задач у смузі нема (0.25.0): «поточну переключили» — карткою «Задач» t3 (екран знову вантажиться). */
  await page.click('#tabs [data-act="home"]');
  await page.click('#tasks-home .th-card[data-id="t3"]');
  await page.waitForFunction(() => fetch("/api/tasks").then((r) => r.json()).then((d) => d.current === "t3"));
  // відповідь екрана затримана: до її приходу він показує СТАРІ дані (current = fixture)
  await page.route("**/api/tasks-overview*", async (r) => { await new Promise((d) => setTimeout(d, 1500)); await r.continue(); });
  await page.click('#tabs [data-act="home"]');
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

