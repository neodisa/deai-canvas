/**
 * Роль `dashboard` (Deai 0.12.0, етап 4c-1, Task 8) — живе проведення: справжній `serve.py` на вільному порту з тимчасовою
 * `DEAI_HOME` у дитячому оточенні, справжній Chromium, ФЕЙКОВІ модулі (`tests/fixtures/dashboard/fake-dashboard`, `fake-vcs`,
 * через тестовий шов `DEAI_EXTRA_MODULES`). Мережі нема: Supabase, GitLab, Jira — ніде; ЛІГА має лише вигаданий конфіг.
 *
 * Юніти (`tests/test_dashboard*.py`, `tests/test_serve_*`) доводять кожну ланку окремо; тут те, чого вони не бачать:
 * що вкладка «Команда» у звичайному просторі справді йде від ПОСТАЧАЛЬНИКА ролі (модуль простору), що синк карток іде тим
 * самим модулем (серверний тригер → дитина `bin/overview_push.py sync --space` → `push`), що ЛІГА лишається `'legacy'` і мовчить
 * в ізольованому прогоні, і що екран «Підключення» показує секцію «Командний дашборд».
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (нема модуля → нема вкладки; модуль увімкнено → вкладка, рядки з файла, чужий рядок без «Відкрити в канвасі») —
 *     `team_snapshot`/`team_resolve` у `serve.py`; «серверу все одно, хто постачальник» (рядки ігнорують модуль) червонить 1 і 2.
 *     Відбір рядків із `id` рядком — `dashboard.normalize_rows` (мутація «без перевірки id» червонить 1). Зайва колонка
 *     чужої таблиці: КЛЮЧІ рядка відбирають двічі — `normalize_rows` і проєкція `tasks_overview` (`team_out`), тож кожен шар окремо
 *     живим тестом не відокремити (їх доводять юніти); тут лише наскрізне «колонка не доходить до відповіді й розмітки» — воно
 *     червоніє, коли зламано ОБИДВА шари разом (глибока оборона, а не доказ одного).
 *   2 (модуль відмовив) — `except ModuleError` у `_team_fetch`: текст модуля у банері, «Мої» живі.
 *   3 («Підключення») — `ROLE_ORDER`/`ROLE_KEYS` у `connections-model.js`: секція «Командний дашборд» і картки.
 *   4 (ЛІГА: `DC_TEAM_FAKE`) і 5 (ЛІГА без шва — ізольований прогін) — гілка `'legacy'` у `_team_fetch`.
 *   6 (синк звичайного простору) — `_overview_sync` (постачальник, а не `integrations`) + `dashboard.sync` (`merge`, без
 *     `insert`: реєстр — крок ЛІГИ); 7 — бар'єр фікстур `_drop_fixtures`; 8 — гейт `DC_NO_OVERVIEW` для будь-якого постачальника;
 *     9 — ЛІГА під `DC_TASKS_FILE` мовчить.
 */
import assert from "node:assert/strict";
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir, userInfo } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { guardRealDeai, postJson, sleep, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs`): тести ЦЬОГО файла йдуть послідовно, тож одна база на всі. */
const PORT_BASE = 14000;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "dashboard");
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => {
  /* Залишки попередніх прогонів, убитих охоронцем (124/125): `t.after` тоді не спрацював, а тека лежить у корені чекаута. */
  for (const n of readdirSync(ROOT)) if (n.startsWith(".live-dash-")) rmSync(path.join(ROOT, n), { recursive: true, force: true });
  browser = await chromium.launch();
});
test.after(async () => { await browser?.close(); });

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

/** Рядки «дашборда»: свій (`mine1` — задача цього простору), чужий (`colleague`), з зайвою колонкою таблиці й сміття без `id`. */
const ROWS = [
  { id: "mine1", name: "Моя задача", designer: "Alpha", iterations: 2, pages: 3, open_comments: 1, code_url: "https://example.com/p/mine1",
    updated_at: new Date(Date.now() - 3600e3).toISOString(), secret_col: "SECRET-COLUMN" },
  { id: "colleague", name: "Задача колеги", designer: "Beta", iterations: 1, pages: 1, open_comments: 0,
    code_url: "https://example.com/p/colleague", updated_at: new Date(Date.now() - 2 * 86400e3).toISOString(), secret_col: "SECRET-COLUMN" },
  { id: 5, name: "Не рядок: id не рядок" },
];

/** Тимчасова тека з файлом рядків і порожнім журналом викликів фейкового модуля. */
function workDir() {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-dash-"));
  const rowsFile = path.join(dir, "rows.json");
  writeFileSync(rowsFile, JSON.stringify(ROWS));
  return { dir, rowsFile, logFile: path.join(dir, "calls.jsonl") };
}

/** Виклики фейкового модуля з журналу (`[{fn, mode?, ids?}]`); файла ще нема — порожньо. */
const calls = (logFile) => (existsSync(logFile)
  ? readFileSync(logFile, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []);

/**
 * Конфіг Supabase ЛІГИ з хостом `.example` — він не резолвиться ніколи (RFC 2606), тож гейт ізоляції можна прибрати мутацією,
 * не боячись справжньої мережі. Конфіг установки читається на кожен виклик (кешу нема), тож пишемо ПІСЛЯ старту сервера.
 * Спільний хост `abcdefghijkl.supabase.co` із `fixture.mjs` не чіпаємо: інші тести спираються на нього.
 */
function useExampleSupabase(legacyFile) {
  const cfg = JSON.parse(readFileSync(legacyFile, "utf8"));
  writeFileSync(legacyFile, JSON.stringify({ ...cfg, supabase_url: "https://demo.supabase.example", supabase_key: "sb_publishable_test" }));
}

/** Дочекатись умови (опитування, а не фіксована пауза); `null` — не дочекались. */
async function until(fn, ms = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const v = await fn();
    if (v) return v;
    await sleep(150);
  }
  return null;
}

/**
 * Копія теки задачі ПОЗА тимчасовими коренями машини. ⛔ Це не примха: синк дашборда відкидає вголос будь-яку задачу з `dir` у
 * `/tmp`/`/var/folders` (`registry.fixture_path_reason`, інцидент 15.09.2026 — фікстура `nova` на командному дашборді), тож
 * задача зі звичайної `taskFixture` ніколи не дійшла б до `push`. Тека лежить у корені чекаута (прихована, `.live-dash-*`) і
 * прибирається разом із тестом.
 */
function outsideTemp(t, from) {
  const dir = mkdtempSync(path.join(ROOT, ".live-dash-"));
  cpSync(from, dir, { recursive: true });
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return dir;
}

/**
 * Сервер звичайного простору «Alpha» (id `alpha`) із задачею `mine1` + браузерна сторінка.
 * `env` — додаткове оточення сервера (`DC_NO_OVERVIEW: ""` вмикає синк); `DEAI_EXTRA_MODULES` — фейкові модулі.
 */
async function bootPlain(t, { env = {}, portOffset = 0, inRepo = false } = {}) {
  const A = taskFixture({ html: MOCKUP });
  if (inRepo) A.dir = outsideTemp(t, A.dir);
  const server = await startServer(null, {
    portBase: PORT_BASE + portOffset, env: { DEAI_EXTRA_MODULES: MODULES_DIR, ...env },
    spaces: [{ name: "Alpha", id: "alpha", color: "space-2", tasks: { mine1: { dir: A.dir, title: "Моя задача" } } }],
  });
  t.after(() => stop(server.child));
  const page = await newPage(t, server.url);
  return { ...server, page, taskDir: A.dir };
}

async function newPage(t, url) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  page.errors = errors;
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-act="home"]', { timeout: 15000 });
  return page;
}

/** Увімкнути фейковий модуль у просторі `alpha` прямим записом (як екран «Підключення»): `{ok, check}`. */
async function enable(url, id, settings) {
  const res = await postJson(url, "/api/module-enable", { space: "alpha", id, settings });
  const body = await res.json();
  assert.equal(body.ok, true, `module-enable ${id}: ${JSON.stringify(body)}`);
  return body;
}

const overview = async (url, qs = "") => (await fetch(`${url}/api/tasks-overview${qs}`)).json();

/** `POST /api/vcs-push` (єдиний серверний тригер синку звичайного простору); відповідь — обʼєкт чи `{status, body}` для не-JSON. */
async function vcsPush(url) {
  const r = await postJson(url, "/api/vcs-push", { it: "it1" });
  const body = await r.text();
  try { return JSON.parse(body); } catch { return { status: r.status, body: body.slice(0, 300) }; }
}

/** Відкрити екран «Задачі» (логотип) і дочекатись карток «Моїх». */
async function openHome(page) {
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
}

const tabTeam = (page) => page.locator('#tasks-home [data-th="tab"][data-v="team"]');
const cardIds = (page) => page.$$eval("#tasks-home .th-card", (els) => els.map((e) => e.dataset.id));

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("1: звичайний простір — без модуля вкладки «Команда» нема; з увімкненим фейковим модулем рядки йдуть з його файла", async (t) => {
  const w = workDir();
  const { page, url } = await bootPlain(t);

  /* Модуль у каталозі є (`DEAI_EXTRA_MODULES`), але в просторі не ввімкнений: постачальника нема → `team: null`. */
  assert.equal((await overview(url)).team, null, "без постачальника ролі відповідь мусить мати `team: null`");
  await openHome(page);
  assert.equal(await tabTeam(page).count(), 0, "без постачальника ролі вкладка «Команда» мусить бути прихована");
  assert.deepEqual(calls(w.logFile), [], "модуль, який не ввімкнено, не кликали");

  const en = await enable(url, "fake-dashboard", { rows_file: w.rowsFile, log_file: w.logFile });
  assert.equal(en.check.ok, true, `check фейкового модуля: ${JSON.stringify(en.check)}`);
  const caps = (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((s) => s.id === "alpha").capabilities;
  assert.equal(caps.dashboard, "fake-dashboard", `capabilities.dashboard: ${JSON.stringify(caps)}`);

  /* Серверна відповідь: лише рядки з рядковим `id` (`normalize_rows`) і наскрізно — зайва колонка таблиці не їде нікуди
     (відбір ключів роблять `normalize_rows` і проєкція `tasks_overview` разом; кожну окремо доводять юніти). */
  const ov = await overview(url, "?refresh=1");
  assert.deepEqual(ov.team.rows.map((r) => r.id).sort(), ["colleague", "mine1"], JSON.stringify(ov.team));
  assert.ok(!JSON.stringify(ov).includes("SECRET-COLUMN"), "зайва колонка чужої таблиці дійшла до відповіді");
  assert.ok(calls(w.logFile).some((c) => c.fn === "rows"), "рядки команди не пройшли через модуль простору");

  await page.reload();
  await page.waitForSelector('#bar [data-act="home"]', { timeout: 15000 });
  await openHome(page);
  assert.match(await tabTeam(page).textContent(), /Команда · 2/);
  await tabTeam(page).click();
  await page.waitForFunction(() => document.querySelector("#tasks-home .th-tab--on")?.dataset.v === "team");
  await page.click('#tasks-home [data-th="status"][data-v="all"]');
  await page.waitForFunction(() => document.querySelectorAll("#tasks-home .th-card").length === 2);
  assert.deepEqual((await cardIds(page)).sort(), ["colleague", "mine1"]);
  const mine = page.locator('#tasks-home .th-card[data-id="mine1"]');
  assert.match(await mine.textContent(), /Alpha/);
  assert.match(await mine.locator("button.th-lnk").textContent(), /Відкрити в канвасі/);
  const other = page.locator('#tasks-home .th-card[data-id="colleague"]');
  assert.equal(await other.locator("button.th-lnk").count(), 0, "чужий рядок отримав «Відкрити в канвасі»");
  assert.equal(await other.locator("a.th-lnk").getAttribute("href"), "https://example.com/p/colleague");
  assert.ok(!(await page.content()).includes("SECRET-COLUMN"), "зайва колонка потрапила в розмітку");
  assert.deepEqual(page.errors, []);
});

test("2: модуль відмовив — банер із ЙОГО текстом, «Спробувати ще» перепитує з refresh=1, «Мої» живі", async (t) => {
  const w = workDir();
  const { page, url } = await bootPlain(t, { portOffset: 100 });
  await enable(url, "fake-dashboard", { rows_file: w.rowsFile, log_file: w.logFile, fail: "fake-down-777" });
  await openHome(page);
  await tabTeam(page).click();
  await page.waitForSelector("#tasks-home .th-banner", { timeout: 15000 });
  assert.match(await page.textContent("#tasks-home .th-banner"), /fake-down-777/, "текст відмови модуля мусить дійти до банера");
  assert.match(await page.textContent("#tasks-home .th-banner"), /Дашборд команди недоступний/);
  assert.equal(await page.locator("#tasks-home .th-card").count(), 0);
  const req = page.waitForRequest((r) => r.url().includes("/api/tasks-overview?refresh=1"));
  await page.click('#tasks-home [data-th="retry"]');
  await req;
  await page.click('#tasks-home [data-th="tab"][data-v="mine"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.deepEqual(await cardIds(page), ["mine1"], "«Мої» мусять жити, коли команда недоступна");
  assert.equal(await page.locator("#tasks-home .th-banner").count(), 0, "банер збою команди на «Моїх»");
});

test("3: «Підключення» — секція «Командний дашборд» з картками supabase-dashboard і фейкового модуля; підключення з екрана дає роль", async (t) => {
  const w = workDir();
  const { page, url } = await bootPlain(t, { portOffset: 200 });
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="static-publish"]', { timeout: 15000 });

  const titles = await page.locator(".cn-sec-h").allTextContents();
  assert.ok(titles.includes("Командний дашборд"), `секції: ${JSON.stringify(titles)}`);
  /* Порядок ролей (`ROLE_ORDER`): дашборд між синхронізацією з git і трекером (4c-2: «Трекер задач» стоїть перед токенами). */
  assert.deepEqual(titles.slice(titles.indexOf("Командний дашборд") - 1, titles.indexOf("Командний дашборд") + 2),
    ["Синхронізація з git", "Командний дашборд", "Трекер задач"]);
  const sec = page.locator(".cn-sec", { has: page.locator(".cn-sec-h", { hasText: "Командний дашборд" }) });
  assert.deepEqual((await sec.locator(".cn-card").evaluateAll((els) => els.map((e) => e.dataset.id))).sort(),
    ["fake-dashboard", "supabase-dashboard"], "у секції мусять стояти обидва модулі ролі");
  for (const id of ["fake-dashboard", "supabase-dashboard"]) {
    assert.match(await sec.locator(`.cn-card[data-id="${id}"] .cn-badge`).getAttribute("class"), /cn-badge--off/, `${id}: не підключений`);
  }
  /* Вбудований модуль має свої тексти з словника: назва — не сирий id. */
  assert.match(await sec.locator('.cn-card[data-id="supabase-dashboard"]').textContent(), /Supabase/);

  await page.click('[data-cn="enable"][data-id="fake-dashboard"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="rows_file"]');
  await page.fill('#cn-drawer [data-cn-field="rows_file"]', w.rowsFile);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector('.cn-card[data-id="fake-dashboard"] .cn-badge--ok', { timeout: 15000 });
  const caps = (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((s) => s.id === "alpha").capabilities;
  assert.equal(caps.dashboard, "fake-dashboard", "після підключення з екрана роль мусить мати власника");
  assert.deepEqual(page.errors, []);
});

test("4: ЛІГА з DC_TEAM_FAKE — вкладка «Команда» як у 0.11.0: рядки зі шва, постачальник 'legacy', фейковий модуль не кликано", async (t) => {
  const w = workDir();
  const A = taskFixture({ html: MOCKUP });
  const seam = path.join(w.dir, "team.json");
  writeFileSync(seam, JSON.stringify([
    { id: "mine1", name: "Моя задача", designer: "Alpha", code_url: "https://example.com/p/mine1" },
    { id: "colleague", name: "Задача колеги", designer: "Beta", code_url: "https://example.com/p/colleague" }]));
  const server = await startServer(null, {
    portBase: PORT_BASE + 300, env: { DEAI_EXTRA_MODULES: MODULES_DIR, DC_TEAM_FAKE: seam },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A.dir, title: "Моя задача" } } }],
    supabase: true,
  });
  t.after(() => stop(server.child));
  const caps = (await (await fetch(`${server.url}/api/spaces`)).json()).spaces.find((s) => s.id === "liga").capabilities;
  assert.equal(caps.dashboard, "legacy", `ЛІГА мусить лишатись неявним постачальником: ${JSON.stringify(caps)}`);
  const page = await newPage(t, server.url);
  await openHome(page);
  assert.match(await tabTeam(page).textContent(), /Команда · 2/);
  await tabTeam(page).click();
  await page.click('#tasks-home [data-th="status"][data-v="all"]');
  await page.waitForFunction(() => document.querySelectorAll("#tasks-home .th-card").length === 2);
  assert.deepEqual((await cardIds(page)).sort(), ["colleague", "mine1"]);
  assert.equal(await page.locator('#tasks-home .th-card[data-id="colleague"] button.th-lnk').count(), 0);
  assert.deepEqual(page.errors, []);
});

test("5: ЛІГА без шва — ізольований прогін: вкладка є, рядків нема, пояснення замість мережі (модуль не кликано)", async (t) => {
  const A = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE + 400, env: { DEAI_EXTRA_MODULES: MODULES_DIR },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A.dir, title: "Моя задача" } } }],
  });
  t.after(() => stop(server.child));
  /* Конфіг із хостом `.example`: без гейта ізоляції модуль пішов би до нього й відповів би «Supabase недоступний» замість
     пояснення — тест червоніє, а справжньої мережі нема (`.example` не резолвиться). */
  useExampleSupabase(server.legacyFile);
  const ov = await overview(server.url, "?refresh=1");
  assert.ok(ov.team, "ЛІГА мусить мати вкладку «Команда» (постачальник 'legacy')");
  assert.deepEqual(ov.team.rows, []);
  assert.match(ov.team.error, /ізольованому прогоні/, `пояснення ізоляції: ${JSON.stringify(ov.team)}`);
  const page = await newPage(t, server.url);
  await openHome(page);
  await tabTeam(page).click();
  await page.waitForSelector("#tasks-home .th-banner", { timeout: 15000 });
  assert.match(await page.textContent("#tasks-home .th-banner"), /ізольованому прогоні/);
});

test("6: синк звичайного простору йде через модуль: vcs-push → дитина overview_push.py sync --space → open_comments, push merge (без insert)", async (t) => {
  const w = workDir();
  const { url, deaiHome } = await bootPlain(t, { portOffset: 500, env: { DC_NO_OVERVIEW: "" }, inRepo: true });
  await enable(url, "fake-dashboard", { rows_file: w.rowsFile, log_file: w.logFile });
  await enable(url, "fake-vcs", { repo: "git@git.example:org/demo-design.git" });
  const res = await vcsPush(url);
  assert.equal(res.synced, true, `vcs-push: ${JSON.stringify(res)}`);

  const pushed = await until(() => calls(w.logFile).some((c) => c.fn === "push"));
  assert.ok(pushed, `синк не дійшов до модуля; журнал: ${JSON.stringify(calls(w.logFile))}`);
  const log = calls(w.logFile).filter((c) => c.fn !== "rows");
  assert.deepEqual(log, [{ fn: "open_comments" }, { fn: "push", mode: "merge", ids: ["mine1"] }],
    "звичайний простір: лічильники коментарів, далі лише `merge` карток задач (реєстр GitLab — крок ЛІГИ)");
  const syncLog = path.join(deaiHome, "logs", "dashboard-sync.log");
  assert.ok(await until(() => existsSync(syncLog) && /синхронізовано 1 проєктів/.test(readFileSync(syncLog, "utf8"))),
    `лог дитини синку: ${existsSync(syncLog) ? readFileSync(syncLog, "utf8") : "нема"}`);
});

test("7: задача з тимчасової теки (фікстура) НЕ їде на дашборд: синк відкидає її вголос, `push` без карток не кличеться", async (t) => {
  const w = workDir();
  const { url, deaiHome } = await bootPlain(t, { portOffset: 800, env: { DC_NO_OVERVIEW: "" } });
  await enable(url, "fake-dashboard", { rows_file: w.rowsFile, log_file: w.logFile });
  await enable(url, "fake-vcs", { repo: "git@git.example:org/demo-design.git" });
  const res = await vcsPush(url);
  assert.equal(res.synced, true, `vcs-push: ${JSON.stringify(res)}`);
  const syncLog = path.join(deaiHome, "logs", "dashboard-sync.log");
  assert.ok(await until(() => existsSync(syncLog) && /не віддаю на дашборд «mine1»/.test(readFileSync(syncLog, "utf8"))),
    `лог дитини синку: ${existsSync(syncLog) ? readFileSync(syncLog, "utf8") : "нема"}`);
  assert.ok(!calls(w.logFile).some((c) => c.fn === "push"), `фікстура дійшла до модуля: ${JSON.stringify(calls(w.logFile))}`);
});

test("8: DC_NO_OVERVIEW (типове оточення живих тестів) глушить синк і для звичайного простору з модулем дашборда", async (t) => {
  const w = workDir();
  const { url, deaiHome } = await bootPlain(t, { portOffset: 600, inRepo: true });
  await enable(url, "fake-dashboard", { rows_file: w.rowsFile, log_file: w.logFile });
  await enable(url, "fake-vcs", { repo: "git@git.example:org/demo-design.git" });
  const res = await vcsPush(url);
  assert.equal(res.synced, true, `vcs-push: ${JSON.stringify(res)}`);
  await sleep(2500);                              // запас на дитину, яка НЕ мусить стартувати
  assert.deepEqual(calls(w.logFile), [], "синк стартував попри DC_NO_OVERVIEW");
  assert.equal(existsSync(path.join(deaiHome, "logs", "dashboard-sync.log")), false, "дитина синку відкрила лог попри DC_NO_OVERVIEW");
});

test("9: ЛІГА під DC_TASKS_FILE мовчить: збірка превʼю (build_only) не стартує синк, лога нема ні в ЛІГИ, ні в домівці простору", async (t) => {
  const A = taskFixture({ html: MOCKUP });
  /* `DC_NO_OVERVIEW: ""` вимикає ЛИШЕ загальний гейт: тримати має гейт `DC_TASKS_FILE` саме для постачальника 'legacy'. Конфіг
     установки є (хост `.example`), тож «нема куди пушити» мовчання не пояснює (інакше тест зеленів би й без гейта), а мутація
     «прибери гейт» безпечна: дитина синку дійшла б лише до хоста, що не резолвиться, і лишила б лог — на ньому тест і червоніє. */
  const server = await startServer(null, {
    portBase: PORT_BASE + 700, env: { DEAI_EXTRA_MODULES: MODULES_DIR, DC_NO_OVERVIEW: "" },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A.dir, title: "Моя задача" } } }],
  });
  t.after(() => stop(server.child));
  useExampleSupabase(server.legacyFile);
  /* ⛔ Теки лога ЛІГИ в тимчасовій домівці нема, а `_overview_spawn` її не створює: без неї `open(лог)` падав би мовчки, дитина не
     стартувала б ЗА БУДЬ-ЯКОГО гейта, і тест зеленів би й без нього (мутація «прибери гейт» це виявила). */
  mkdirSync(path.join(server.home, ".claude", "pipeline-feedback"), { recursive: true });
  const built = await (await postJson(server.url, "/api/publish", { build_only: true })).json();
  assert.equal(built.ok, true, JSON.stringify(built));
  await sleep(2500);
  assert.equal(existsSync(path.join(server.home, ".claude", "pipeline-feedback", "overview-sync.log")), false,
    "ЛІГА під DC_TASKS_FILE відкрила лог синку: дитина стартувала б у спільний Supabase");
  assert.equal(existsSync(path.join(server.deaiHome, "logs")), false, "синк ЛІГИ пішов лозі звичайного простору");
});

/* Справжній лог синку ЛІГИ (`~/.claude/pipeline-feedback/overview-sync.log`): лише `stat` (нічого не пишемо). Свій, а не в спільному
   `_spaces-kit.mjs`: його читають усі файли просторів, а справжній канвас на машині міг би дописати в лог сам по собі. */
const REAL_SYNC_LOG = path.join(userInfo().homedir, ".claude", "pipeline-feedback", "overview-sync.log");
const syncLogStat = () => { try { const s = statSync(REAL_SYNC_LOG); return `${s.mtimeMs}:${s.size}`; } catch { return null; } };
const SYNC_LOG_BEFORE = syncLogStat();
test("10: справжній лог синку ЛІГИ не зʼявився і не змінився", () => {
  assert.equal(syncLogStat(), SYNC_LOG_BEFORE, `живий тест торкнувся справжнього ${REAL_SYNC_LOG}`);
});

guardRealDeai("11: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
