/**
 * Роль `tracker` (Deai 0.13.0, етап 4c-2, Task 7) — живе проведення: справжній `serve.py` на вільному порту з тимчасовою
 * `DEAI_HOME` у дитячому оточенні, справжній Chromium, ФЕЙКОВИЙ модуль (`tests/fixtures/tracker/fake-tracker`, через тестовий
 * шов `DEAI_EXTRA_MODULES`). Мережі нема: Jira, Supabase, GitLab — ніде; статуси йдуть із JSON-файла, шлях до якого — налаштування
 * модуля.
 *
 * Юніти (`tests/test_tracker*.py`, `tests/test_tasks_overview.py`, `tests/tasks-home.test.mjs`) доводять кожну ланку окремо; тут
 * те, чого вони не бачать: що бейджі статусу на картках «Моїх» справді приходять від ПОСТАЧАЛЬНИКА ролі (модуль простору) без
 * дашборда, що збій модуля після успіху дає банер, а бейджі лишаються, що екран «Підключення» показує секцію «Трекер задач» і
 * чесно називає наслідок вимкнення, і що ЛІГА в ізольованому прогоні мовчить, як у 0.12.0.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (нема модуля → `tracker: null`, бейджів і банера нема, модуль не кликано) — `tracker_snapshot` (`prov is None` → `None`).
 *   2 (модуль ввімкнено → бейджі з його файла; у модуль іде лише валідний ключ) — `_tracker_fetch` + `tracker.keys_of`/`KEY_RE`;
 *     пріоритет «статус трекера над рядком дашборда» — `tasks_overview` (`trk`).
 *   3 (збій після успіху: банер із текстом модуля й часом, бейджі лишились; «Спробувати ще» перепитує з `refresh=1`) — `refresh` у
 *     `tracker_snapshot` + гілка `error` кешу, що НЕ стирає останні статуси; клієнтський `trackerBanner`.
 *   4 («Підключення») — `ROLE_ORDER`/`ROLE_KEYS` у `connections-model.js`; текст наслідку вимкнення — `consKey` (`cnDisableTracker`)
 *     у `disableConsequences` і його проводка в `connDisable` (`app.js`).
 *   5 (ЛІГА з `DC_TASKS_FILE` + `DC_TEAM_FAKE`) — гілка `'legacy'` у `_tracker_fetch`: ізоляція → `None`, банера нема.
 */
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { guardRealDeai, postJson, stop, goTasks } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";
import { hermeticLiga } from "./_liga-supabase.mjs";

/* Своя смуга (`tests/live-ports.test.mjs`): тести ЦЬОГО файла йдуть послідовно, тож одна база на всі. */
const PORT_BASE = 21000;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "tracker");
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

/* Спільний збирач запитів усіх сторінок файла: ЛІГА під `supabase: true` читає командне сховище, тож без `hermeticLiga` сторінка йшла б
   на справжній `*.supabase.co`. `outside` мусить лишитись порожнім (перевіряє `test.after`). */
const SEEN = { outside: [], supabase: [], sockets: [], cdn: [] };
let browser;
test.before(async () => {
  /* Залишки попередніх прогонів, убитих охоронцем (124/125): `t.after` тоді не спрацював, а тека лежить у корені чекаута. */
  for (const n of readdirSync(ROOT)) if (n.startsWith(".live-trk-")) rmSync(path.join(ROOT, n), { recursive: true, force: true });
  browser = await chromium.launch();
});
test.after(async () => {
  await browser?.close();
  assert.deepEqual(SEEN.outside, [], "запити поза машиною: герметичність ЛІГИ порушена");
});

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

/** Статуси «трекера»: `DEMO-1` і `DEMO-2` — є, `DEMO-3` — задача є, а статусу в трекері нема (бейджа не буде). */
const STATUSES = {
  "DEMO-1": { name: "Фейк у роботі", cat: "indeterminate" },
  "DEMO-2": { name: "Фейк готово", cat: "done" },
};

/** Тека з файлом статусів і порожнім журналом викликів фейкового модуля; прибирається разом із тестом. */
function workDir(t) {
  const dir = mkdtempSync(path.join(ROOT, ".live-trk-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const statusesFile = path.join(dir, "statuses.json");
  writeFileSync(statusesFile, JSON.stringify(STATUSES));
  return { dir, statusesFile, logFile: path.join(dir, "calls.jsonl") };
}

/** Виклики фейкового модуля з журналу (`[{fn, keys}]`); файла ще нема — порожньо. */
const calls = (logFile) => (existsSync(logFile)
  ? readFileSync(logFile, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)) : []);

/**
 * Сервер звичайного простору «Alpha» (id `alpha`): чотири задачі — три з ключами (`DEMO-1`, `DEMO-2`, `DEMO-3`) і одна з
 * НЕвалідним (`not-a-key`: ручна правка `tasks.json`, до модуля потрапити не мусить) + браузерна сторінка.
 */
async function bootPlain(t, { portOffset = 0 } = {}) {
  const A = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE + portOffset, env: { DEAI_EXTRA_MODULES: MODULES_DIR },
    spaces: [{ name: "Alpha", id: "alpha", color: "space-2", tasks: {
      d1: { dir: A.dir, title: "Задача один", jira: "DEMO-1" },
      d2: { dir: A.dir, title: "Задача два", jira: "DEMO-2" },
      d3: { dir: A.dir, title: "Задача три", jira: "DEMO-3" },
      bad: { dir: A.dir, title: "Задача з сміттям", jira: "not-a-key" },
    } }],
  });
  t.after(() => stop(server.child));
  const page = await newPage(t, server.url);
  return { ...server, page };
}

async function newPage(t, url) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await hermeticLiga(context, { seen: SEEN });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  /* Нативний діалог ОС у живому тесті — завжди провал: жодна дія цього файла не мусить його викликати. */
  page.on("dialog", async (d) => { errors.push(`нативний діалог: ${d.message()}`); await d.dismiss(); });
  page.errors = errors;
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#tabs [data-act="home"]', { timeout: 15000 });
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

/**
 * Відкрити екран «Задачі» (логотип) і дочекатись карток «Моїх». `all` — ще й чіп «Усі»: типовий фільтр «Активні» ховає задачі зі
 * статусом категорії `done`, а нам треба бачити й їхні бейджі.
 */
async function openHome(page, { all = false } = {}) {
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
  if (!all) return;
  await page.click('#tasks-home [data-th="status"][data-v="all"]');
  await page.waitForFunction(() => document.querySelectorAll("#tasks-home .th-card").length === 4, null, { timeout: 15000 });
}

/** Бейджі статусу на картках «Моїх»: `{id задачі: текст}`; картки без бейджа в мапу не потрапляють. */
const badges = (page) => page.$$eval("#tasks-home .th-card", (els) => Object.fromEntries(els
  .map((e) => [e.dataset.id, e.querySelector(".th-bdg[class*='th-bdg--']:not(.th-bdg--com)")?.textContent?.trim() ?? null])
  .filter(([, v]) => v)));
const trackerBanner = (page) => page.locator("#tasks-home .th-banner", { hasText: "Трекер недоступний" });

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("1: звичайний простір без трекера — `tracker: null`, бейджів статусу й банера нема; модуль є в каталозі, але не ввімкнений", async (t) => {
  const { page, url } = await bootPlain(t);
  const caps = (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((s) => s.id === "alpha").capabilities;
  assert.equal(caps.tracker ?? null, null, `постачальника ролі нема, а capabilities.tracker = ${JSON.stringify(caps.tracker)}`);
  /* Свідок «модуль є, але не ввімкнений» (без нього «модуль не кликали» вдавало б перевірку на порожній журналі: `log_file` задає
     лише ввімкнення). Каталог (`DEAI_EXTRA_MODULES`) показує фейковий модуль, а простір його не вмикав. */
  const mods = (await (await fetch(`${url}/api/modules?space=alpha`)).json()).modules;
  const fake = mods.find((m) => m.id === "fake-tracker");
  assert.ok(fake, `фейковий модуль мусить бути в каталозі: ${JSON.stringify(mods.map((m) => m.id))}`);
  assert.notEqual(fake.enabled, true, "фейковий трекер уже ввімкнено — сценарій без трекера недійсний");
  const ov = await overview(url, "?refresh=1");
  assert.equal(ov.tracker, null, "без постачальника ролі відповідь мусить мати `tracker: null`");
  assert.ok(ov.mine.every((x) => x.jiraStatus == null), `статус зʼявився без трекера: ${JSON.stringify(ov.mine)}`);
  await openHome(page);
  assert.equal(await page.locator("#tasks-home .th-card").count(), 4);
  assert.deepEqual(await badges(page), {}, "бейджі статусу без трекера");
  assert.equal(await page.locator("#tasks-home .th-banner").count(), 0, "банер без трекера");
  assert.deepEqual(page.errors, []);
});

test("2: той самий простір з увімкненим фейковим трекером, без дашборда — бейджі на картках «Моїх»; у модуль іде лише валідний ключ", async (t) => {
  const w = workDir(t);
  const { page, url } = await bootPlain(t, { portOffset: 100 });
  const en = await enable(url, "fake-tracker", { statuses_file: w.statusesFile, log_file: w.logFile });
  assert.equal(en.check.ok, true, `check фейкового модуля: ${JSON.stringify(en.check)}`);
  const sp = (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((s) => s.id === "alpha");
  assert.equal(sp.capabilities.tracker, "fake-tracker", `capabilities.tracker: ${JSON.stringify(sp.capabilities)}`);
  assert.ok(!sp.capabilities.dashboard, `свідок «без дашборда»: ${JSON.stringify(sp.capabilities)}`);

  await openHome(page, { all: true });
  assert.deepEqual(await badges(page), { d1: "Фейк у роботі", d2: "Фейк готово" },
    "бейджі: лише там, де трекер знає ключ (`DEMO-3` без статусу, `not-a-key` — сміття)");
  assert.match(await page.locator('#tasks-home .th-card[data-id="d1"] .th-bdg--ind').textContent(), /Фейк у роботі/);
  assert.match(await page.locator('#tasks-home .th-card[data-id="d2"] .th-bdg--done').textContent(), /Фейк готово/);
  assert.equal(await page.locator("#tasks-home .th-banner").count(), 0, "банер при успіху");
  const got = calls(w.logFile).filter((c) => c.fn === "statuses");
  assert.ok(got.length >= 1, "свідок: статуси мусили піти через модуль простору");
  assert.deepEqual(got[0].keys, ["DEMO-1", "DEMO-2", "DEMO-3"], `у модуль потрапили не ті ключі: ${JSON.stringify(got)}`);
  const ov = await overview(url);
  assert.equal(ov.tracker.error, null);
  assert.equal(typeof ov.tracker.okAt, "number", "є час останнього успіху");
  assert.deepEqual(page.errors, []);
});

test("3: трекер у режимі «збій» після успіху — банер «Трекер недоступний…» з текстом модуля й часом, бейджі лишились; «Спробувати ще» лікує", async (t) => {
  const w = workDir(t);
  const { page, url } = await bootPlain(t, { portOffset: 200 });
  await enable(url, "fake-tracker", { statuses_file: w.statusesFile, log_file: w.logFile });
  await openHome(page, { all: true });
  assert.deepEqual(await badges(page), { d1: "Фейк у роботі", d2: "Фейк готово" }, "свідок: до збою бейджі є");
  const okAt = (await overview(url)).tracker.okAt;

  /* Збій: файл тепер каже «помилка». Кеш (5 хв) без `refresh=1` його б не побачив — тест не залежить від годинника. */
  writeFileSync(w.statusesFile, JSON.stringify({ error: "fake-tracker-down-777" }));
  const failed = await overview(url, "?refresh=1");
  assert.equal(failed.tracker.error, "fake-tracker-down-777");
  assert.equal(failed.tracker.okAt, okAt, "збій не стирає час останнього успіху");
  assert.deepEqual(failed.mine.filter((x) => x.jiraStatus).map((x) => x.id).sort(), ["d1", "d2"],
    "збій НЕ стирає останні відомі статуси");

  await page.reload();
  await page.waitForSelector('#tabs [data-act="home"]', { timeout: 15000 });
  await openHome(page, { all: true });
  const banner = trackerBanner(page);
  await banner.waitFor({ timeout: 15000 });
  const text = await banner.textContent();
  assert.match(text, /fake-tracker-down-777/, "текст відмови модуля мусить дійти до банера");
  /* Очікуваний час — з `okAt` і форматером САМОЇ сторінки (мова, пояс, формат — Chromium цього прогону), а не лише «щось схоже на час». */
  const want = await page.evaluate((sec) => new Date(sec * 1000).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" }), okAt);
  assert.ok(text.includes(`дані на ${want}`), `банер мусить казати «дані на ${want}» (час останнього успіху): ${text}`);
  assert.deepEqual(await badges(page), { d1: "Фейк у роботі", d2: "Фейк готово" }, "бейджі лишились із останнього успіху");

  /* «Спробувати ще»: перепитує з `refresh=1`; трекер уже здоровий → банер зникає, статуси оновились. */
  writeFileSync(w.statusesFile, JSON.stringify({ ...STATUSES, "DEMO-1": { name: "Фейк оновлено", cat: "done" } }));
  const req = page.waitForRequest((r) => r.url().includes("/api/tasks-overview?refresh=1"));
  await banner.locator('[data-th="retry"]').click();
  await req;
  await page.waitForFunction(() => !document.querySelector("#tasks-home .th-banner"), null, { timeout: 15000 });
  assert.deepEqual(await badges(page), { d1: "Фейк оновлено", d2: "Фейк готово" });
  assert.deepEqual(page.errors, []);
});

test("4: «Підключення» — секція «Трекер задач» з jira-tracker і фейковим модулем; вимкнення називає наслідок (діалог, не нативний), «Скасувати» нічого не міняє", async (t) => {
  const w = workDir(t);
  const { page, url } = await bootPlain(t, { portOffset: 300 });
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="static-publish"]', { timeout: 15000 });

  const titles = await page.locator(".cn-sec-h").allTextContents();
  const at = titles.indexOf("Трекер задач");
  assert.ok(at >= 0, `секції: ${JSON.stringify(titles)}`);
  assert.deepEqual(titles.slice(at - 1, at + 2), ["Командний дашборд", "Трекер задач", "Сповіщення Teams"], "4c-3: після трекера — «Сповіщення Teams», токени далі");
  const sec = page.locator(".cn-sec", { has: page.locator(".cn-sec-h", { hasText: "Трекер задач" }) });
  assert.deepEqual((await sec.locator(".cn-card").evaluateAll((els) => els.map((e) => e.dataset.id))).sort(),
    ["fake-tracker", "jira-tracker"], "у секції мусять стояти обидва модулі ролі");
  for (const id of ["fake-tracker", "jira-tracker"]) {
    assert.match(await sec.locator(`.cn-card[data-id="${id}"] .cn-badge`).getAttribute("class"), /cn-badge--off/, `${id}: не підключений`);
  }
  /* Вбудований модуль має свої тексти зі словника: назва — не сирий id. */
  assert.match(await sec.locator('.cn-card[data-id="jira-tracker"]').textContent(), /Jira/);

  await page.click('[data-cn="enable"][data-id="fake-tracker"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="statuses_file"]');
  await page.fill('#cn-drawer [data-cn-field="statuses_file"]', w.statusesFile);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector('.cn-card[data-id="fake-tracker"] .cn-badge--ok', { timeout: 15000 });
  const capsOf = async () => (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((s) => s.id === "alpha").capabilities;
  assert.equal((await capsOf()).tracker, "fake-tracker", "після підключення з екрана роль мусить мати власника");

  /* Вимкнення: діалог (внутрішній `.cv-ask-scrim`) каже, що зникнуть статуси; «Скасувати» лишає все як було. */
  await page.click('[data-cn="disable"][data-id="fake-tracker"]');
  await page.waitForSelector(".cv-ask-scrim", { timeout: 15000 });
  const ask = await page.locator(".cv-ask-scrim").textContent();
  assert.match(ask, /Статуси задач зникнуть з екрана «Задачі» й перестануть оновлюватись у дашборді/,
    `діалог вимкнення мусить назвати наслідок для трекера: ${ask}`);
  assert.doesNotMatch(ask, /лишиться без модуля/, "загальний текст «без модуля» не мусить підміняти текст трекера");
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.match(await page.locator('.cn-card[data-id="fake-tracker"] .cn-badge').getAttribute("class"), /cn-badge--ok/, "скасування не вимикає");
  assert.equal((await capsOf()).tracker, "fake-tracker", "скасування не міняє постачальника");
  assert.deepEqual(page.errors, []);
});

test("5: ЛІГА з DC_TASKS_FILE + DC_TEAM_FAKE — як у 0.12.0: `tracker: null`, банера нема, статус на картці — з рядка дашборда", async (t) => {
  const w = workDir(t);
  const A = taskFixture({ html: MOCKUP });
  const seam = path.join(w.dir, "team.json");
  writeFileSync(seam, JSON.stringify([
    { id: "d1", name: "Задача один", designer: "Alpha", jira: "DEMO-1", jira_status: "Дашборд-статус", jira_status_cat: "indeterminate",
      code_url: "https://example.com/p/d1" },
    { id: "colleague", name: "Задача колеги", designer: "Beta", code_url: "https://example.com/p/colleague" }]));
  const server = await startServer(null, {
    portBase: PORT_BASE + 400,
    /* Явно гасимо шви трекера й сповіщень, що могли б протекти з оболонки розробника (сервер успадковує `process.env`). */
    env: { DEAI_EXTRA_MODULES: MODULES_DIR, DC_TEAM_FAKE: seam, DC_TRACKER_FAKE: "", DC_TEAMS_FAKE: "" },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, roles: ["comments", "dashboard", "notify", "vcs", "publish", "tracker"],
      tasks: { d1: { dir: A.dir, title: "Задача один", jira: "DEMO-1" } } }],
    supabase: true,
  });
  t.after(() => stop(server.child));
  const caps = (await (await fetch(`${server.url}/api/spaces`)).json()).spaces.find((s) => s.id === "liga").capabilities;
  assert.equal(caps.tracker, "jira-tracker", `ЛІГА веде трекер явним записом (4d-4b): ${JSON.stringify(caps)}`);
  const ov = await overview(server.url, "?refresh=1");
  assert.equal(ov.tracker, null, "ізольований прогін ЛІГИ: трекера для екрана нема (мережі нема, пояснювати нічого)");
  const page = await newPage(t, server.url);
  await openHome(page);
  assert.equal(await trackerBanner(page).count(), 0, "банер трекера в ізольованій ЛІГІ");
  assert.equal(await page.locator("#tasks-home .th-banner").count(), 0, "жодного банера на «Моїх»");
  assert.deepEqual(await badges(page), { d1: "Дашборд-статус" }, "статус із рядка дашборда (шов `DC_TEAM_FAKE`), як у знімку 0.12.0");
  /* Лог синку ЛІГИ лежить у `<HOME>/.claude/pipeline-feedback`: теки нема, бо ніхто (ні синк, ні трекер) туди не писав. */
  assert.equal(existsSync(path.join(server.home, ".claude", "pipeline-feedback")), false, "ЛІГА в ізоляції створила теку pipeline-feedback");
  assert.deepEqual(page.errors, []);
});

guardRealDeai("6: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
