/**
 * Роль `notify` (Deai 0.14.0, етап 4c-3, Task 6) — живе проведення: справжній `serve.py` на вільному порту з тимчасовою
 * `DEAI_HOME` у дитячому оточенні, справжній Chromium, ФЕЙКОВИЙ модуль (`tests/fixtures/notify/fake-notify`, через тестовий
 * шов `DEAI_EXTRA_MODULES`). Мережі нема: Supabase і Teams — ніде; стан тиші лежить у JSON-файлі, шлях до якого — налаштування
 * модуля.
 *
 * Юніти (`tests/test_notify*.py`, `tests/*-model.test.mjs`) доводять кожну ланку окремо; тут те, чого вони не бачать: що пункт
 * «Сповіщати Teams» у дропдауні публікації стоїть на ПОСТАЧАЛЬНИКУ ролі (а не на «є інтеграції»), що вимкнення йде через
 * внутрішній діалог підтвердження й доходить до сховища модуля, що збій модуля дає «стан невідомий», а не «увімкнено», що екран
 * «Підключення» показує секцію «Сповіщення Teams» і чесно називає наслідок вимкнення, і що ЛІГА з `DC_TEAMS_FAKE` лишилась як у 0.13.0.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (нема модуля → пункта нема, модуль у каталозі, але не ввімкнений; `/api/teams-mute` → 409 `notify-off`) — `hasNotify`
 *     (`spaces-model.js`) у `bar-model.js` (`...(hasNotify(s.space) ? [teamsItem(…)] : [])`) і гейт `_notify_route_gate` у `serve.py`.
 *   2 (модуль ввімкнено → пункт є й «увімкнено»; вимкнення — діалог → стан у файлі модуля → «тиша (ви)»; назад — без питання) —
 *     `notify_call` (роль, а не `DC_TEAMS_FAKE`) + `teamsnotify` в `app.js` + `notify.mute_view` (`mine` за підписом машини).
 *   3 (збій модуля → пункт вимкнений із «стан невідомий», не «увімкнено») — `teamsItem` (`tm.error`) + гілка `ModuleError` у
 *     `do_GET /api/teams-mute` (`{channel, error}`), яку клієнт читає як «невідомо».
 *   4 («Підключення» — секція «Сповіщення Teams», діалог вимкнення з текстом `cnDisableNotify`) — `ROLE_ORDER`/`ROLE_KEYS` у
 *     `connections-model.js`; `consKey` у `disableConsequences` і його проводка в `connDisable` (`app.js`).
 *   5 (ЛІГА з `DC_TEAMS_FAKE` — як у 0.13.0) — гілка `'legacy'` у `notify_call` (шов лише для неї).
 */
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { askNo, pickFromCatalog, guardRealDeai, goTasks, menuDisable, postJson, stop, waitBadge } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";
import { hermeticLiga } from "./_liga-supabase.mjs";

/* Своя смуга (`tests/live-ports.test.mjs`): тести ЦЬОГО файла йдуть послідовно, тож одна база на всі. */
const PORT_BASE = 22000;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "notify");
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";
/* Особа машини для тесту: підпис тиші (`k:<хеш пошти>`) рахується з неї, тож «тиша (ви)» не залежить від git-конфіга розробника. */
const IDENTITY = { DC_IDENTITY_NAME: "Alpha", DC_IDENTITY_EMAIL: "alpha@example.com" };
/* Канал задачі `t1` без `comment_project` — `dc/<id>` (`comment_channel`). */
const CHANNEL = "dc/t1";

/* Спільний збирач запитів усіх сторінок файла: ЛІГА під `supabase: true` читає командне сховище, тож без `hermeticLiga` сторінка йшла б
   на справжній `*.supabase.co`. `outside` мусить лишитись порожнім (перевіряє `test.after`). */
const SEEN = { outside: [], supabase: [], sockets: [], cdn: [] };
let browser;
test.before(async () => {
  /* Залишки попередніх прогонів, убитих охоронцем (124/125): `t.after` тоді не спрацював, а тека лежить у корені чекаута. */
  for (const n of readdirSync(ROOT)) if (n.startsWith(".live-ntf-")) rmSync(path.join(ROOT, n), { recursive: true, force: true });
  browser = await chromium.launch();
});
test.after(async () => {
  await browser?.close();
  assert.deepEqual(SEEN.outside, [], "запити поза машиною: герметичність ЛІГИ порушена");
});

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

/** Тека зі станом тиші фейкового модуля; прибирається разом із тестом. */
function workDir(t) {
  const dir = mkdtempSync(path.join(ROOT, ".live-ntf-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return { dir, stateFile: path.join(dir, "mutes.json") };
}

/** Стан тиші з файла модуля (`{канал: {muted_at, muted_by}}`); файла ще нема — порожньо. */
const muteDb = (file) => (existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : {});

/** Дочекатися умови (запис у файл модуля іде після відповіді діалогу): опит кожні 100 мс до 15 с, без вічного очікування. */
async function until(cond) {
  const deadline = Date.now() + 15000;
  while (!cond() && Date.now() < deadline) await new Promise((r) => setTimeout(r, 100));
}

/** Сервер звичайного простору «Alpha» (id `alpha`) з однією задачею `t1` (канал `dc/t1`) + браузерна сторінка. */
async function bootPlain(t, { portOffset = 0 } = {}) {
  const A = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE + portOffset, env: { DEAI_EXTRA_MODULES: MODULES_DIR, ...IDENTITY },
    spaces: [{ name: "Alpha", id: "alpha", color: "space-2", tasks: { t1: { dir: A.dir, title: "Задача один" } } }],
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
  await page.waitForSelector("#bar [data-dd]", { timeout: 15000 });
  return page;
}

/** Увімкнути фейковий модуль у просторі `alpha` прямим записом (як екран «Підключення»): `{ok, check}`. */
async function enable(url, settings) {
  const res = await postJson(url, "/api/module-enable", { space: "alpha", id: "fake-notify", settings });
  const body = await res.json();
  assert.equal(body.ok, true, `module-enable fake-notify: ${JSON.stringify(body)}`);
  return body;
}

const capsOf = async (url, id = "alpha") => (await (await fetch(`${url}/api/spaces`)).json()).spaces.find((s) => s.id === id).capabilities;

/** Відкрити дропдаун публікації. Пункт «Сповіщати Teams» (є чи нема) шукається вже після того, як дропдаун справді відкрито. */
async function openPub(page) {
  await page.click('#bar [data-dd="pub"]');
  await page.waitForSelector("#bar .dd-item", { timeout: 15000 });
  return page.locator('#bar [data-act="teamsnotify"]');
}

/** Пункт Teams, що закінчив опит стану: уже не «перевіряю стан у базі…» (`disabled` лишається лише для «невідомо»). */
async function settledTeams(page, { expectDisabled = false } = {}) {
  const el = await openPub(page);
  await el.waitFor({ timeout: 15000 });
  await page.waitForFunction((dis) => {
    const b = document.querySelector('#bar [data-act="teamsnotify"]');
    return b && !/перевіряю/.test(b.innerText) && (dis || !b.disabled);
  }, expectDisabled, { timeout: 15000 });
  return el;
}

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("1: звичайний простір без модуля — пункта «Сповіщати Teams» нема, `/api/teams-mute` — 409; модуль є в каталозі, але не ввімкнений", async (t) => {
  const { page, url } = await bootPlain(t);
  assert.equal((await capsOf(url)).notify ?? null, null, "постачальника ролі нема, а capabilities.notify є");
  /* Свідок «модуль є, але не ввімкнений»: без нього «пункта нема» вдавало б перевірку на порожньому каталозі. */
  const mods = (await (await fetch(`${url}/api/modules?space=alpha`)).json()).modules;
  const fake = mods.find((m) => m.id === "fake-notify");
  assert.ok(fake, `фейковий модуль мусить бути в каталозі: ${JSON.stringify(mods.map((m) => m.id))}`);
  assert.notEqual(fake.enabled, true, "фейковий notify уже ввімкнено — сценарій без модуля недійсний");
  const res = await fetch(`${url}/api/teams-mute`);
  assert.equal(res.status, 409);
  assert.equal((await res.json()).code, "notify-off");

  const item = await openPub(page);
  assert.equal(await item.count(), 0, "пункт «Сповіщати Teams» без постачальника ролі");
  /* Дропдаун відкрито й наповнено (свідок: порожній дропдаун теж не мав би пункта). */
  assert.ok(await page.locator("#bar .dd-item").count() > 0);
  assert.deepEqual(page.errors, []);
});

test("2: той самий простір із фейковим notify — пункт є й «увімкнено»; вимкнення через діалог → стан у файлі модуля → «тиша (ви)»; увімкнення без питання", async (t) => {
  const w = workDir(t);
  const { page, url } = await bootPlain(t, { portOffset: 100 });
  const en = await enable(url, { state_file: w.stateFile });
  assert.equal(en.check.ok, true, `check фейкового модуля: ${JSON.stringify(en.check)}`);
  assert.equal((await capsOf(url)).notify, "fake-notify");
  await page.reload();
  await page.waitForSelector("#bar [data-dd]", { timeout: 15000 });

  let el = await settledTeams(page);
  assert.equal(await el.locator(".chk--on").count(), 1, "типово — шумимо");
  assert.match(await el.innerText(), /dc\/t1/);
  assert.deepEqual(muteDb(w.stateFile), {}, "свідок: у сховищі модуля тиші ще нема");

  /* Вимкнення: внутрішній діалог (`.cv-ask`) каже «ВСІХ»; «Так» пише в СХОВИЩЕ МОДУЛЯ, а не деінде. */
  await el.click();
  await page.waitForSelector(".cv-ask", { timeout: 15000 });
  assert.match(await page.locator(".cv-ask").innerText(), /ВСІХ/);
  await page.click('.cv-ask [data-a="ok"]');
  await page.waitForSelector(".cv-ask", { state: "detached" });
  await until(() => Object.keys(muteDb(w.stateFile)).length > 0);
  const stored = muteDb(w.stateFile);
  assert.deepEqual(Object.keys(stored), [CHANNEL], `тиша мусить лягти у файл модуля: ${JSON.stringify(stored)}`);
  assert.match(stored[CHANNEL].muted_by, /^k:[0-9a-f]{12}$/, "підпис — хеш пошти, без ПІБ");

  /* Після перезавантаження стан приходить із модуля, а підпис збігається з підписом машини: «тиша (ви)». */
  await page.reload();
  await page.waitForSelector("#bar [data-dd]", { timeout: 15000 });
  el = await settledTeams(page);
  assert.equal(await el.locator(".chk--on").count(), 0, "після перезавантаження — вимкнено");
  assert.match(await el.innerText(), /вимкнено для всіх \(тобою\)/);

  /* Увімкнути назад — без питання, і файл модуля порожнішає. */
  await el.click();
  await until(() => Object.keys(muteDb(w.stateFile)).length === 0);
  assert.equal(await page.locator(".cv-ask").count(), 0, "увімкнення не питає підтвердження");
  assert.deepEqual(muteDb(w.stateFile), {}, "увімкнення мусить прибрати тишу зі сховища модуля");
  assert.deepEqual(page.errors, []);
});

test("3: модуль у режимі «збій» — пункт вимкнений із причиною «стан невідомий», а не «увімкнено»", async (t) => {
  const w = workDir(t);
  const { page, url } = await bootPlain(t, { portOffset: 200 });
  await enable(url, { state_file: w.stateFile });
  /* Збій: файл тепер каже «помилка» — `check` при вмиканні вже пройшов, а `mute_state` відмовляє. */
  writeFileSync(w.stateFile, JSON.stringify({ error: "fake-notify-down-777" }));
  const get = await fetch(`${url}/api/teams-mute`);
  const body = await get.json();
  assert.equal(body.channel, CHANNEL);
  assert.match(String(body.error), /fake-notify-down-777/, `GET мусить віддати {channel, error}: ${JSON.stringify(body)}`);
  assert.notEqual(body.muted, false, "збій не мусить виглядати як «не замовчано»");

  await page.reload();
  await page.waitForSelector("#bar [data-dd]", { timeout: 15000 });
  const el = await settledTeams(page, { expectDisabled: true });
  await page.waitForFunction(() => /стан невідомий/.test(document.querySelector('#bar [data-act="teamsnotify"]')?.innerText || ""),
    null, { timeout: 15000 });
  assert.equal(await el.isDisabled(), true, "пункт при збої мусить бути вимкнений");
  assert.equal(await el.locator(".chk--on").count(), 0, "збій не мусить показувати «увімкнено»");
  assert.deepEqual(page.errors, []);
});

test("4: «Підключення» — роль «Сповіщення Teams» без модуля; вимкнення називає наслідок (питання в картці), «Скасувати» нічого не міняє", async (t) => {
  const w = workDir(t);
  const { page, url } = await bootPlain(t, { portOffset: 300 });
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.mc[data-id="static-publish"]', { timeout: 15000 });

  const roles = await page.locator(".mc--empty").evaluateAll((els) => els.map((e) => e.dataset.role));
  assert.ok(roles.includes("notify"), `порожні ролі: ${JSON.stringify(roles)}`);
  assert.match(await page.locator('.mc--empty[data-role="notify"]').textContent(), /Сповіщення Teams/);
  assert.equal(await page.locator('.mc[data-id="fake-notify"], .mc[data-id="supabase-teams"]').count(), 0, "вимкнені модулі ролі — не в сітці (лише в каталозі)");

  await pickFromCatalog(page, "fake-notify");
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="state_file"]');
  await page.fill('#cn-drawer [data-cn-field="state_file"]', w.stateFile);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await waitBadge(page, "fake-notify", "ok");
  assert.equal((await capsOf(url)).notify, "fake-notify", "після підключення з екрана роль мусить мати власника");

  /* Вимкнення: питання в картці каже, що картки зникнуть; «Скасувати» лишає все як було. */
  await menuDisable(page, "fake-notify");
  const ask = await page.locator(".mc--ask .cfm-t").textContent();
  assert.match(ask, /Нові коментарі перестануть надходити карткою в Teams, а перемикач тиші зникне/,
    `питання вимкнення мусить назвати наслідок для сповіщень: ${ask}`);
  assert.doesNotMatch(ask, /лишиться без модуля/, "загальний текст «без модуля» не мусить підміняти текст сповіщень");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "діалогу нема — питання в картці");
  await askNo(page, "fake-notify");
  await page.waitForSelector(".mc--ask", { state: "detached" });
  await waitBadge(page, "fake-notify", "ok");                // скасування не вимикає
  assert.equal((await capsOf(url)).notify, "fake-notify", "скасування не міняє постачальника");
  assert.deepEqual(page.errors, []);
});

test("5: ЛІГА з DC_TEAMS_FAKE — як у 0.13.0: пункт є, тиша через діалог лягає у файл шва, стан переживає перезавантаження", async (t) => {
  const w = workDir(t);
  const A = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE + 400,
    env: { DEAI_EXTRA_MODULES: MODULES_DIR, DC_TEAMS_FAKE: w.stateFile, ...IDENTITY },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { t1: { dir: A.dir, title: "Задача один" } } }],
    supabase: true,
  });
  t.after(() => stop(server.child));
  assert.equal((await capsOf(server.url, "liga")).notify, "supabase-teams", "ЛІГА веде сповіщення явним записом (4d-4b)");
  const page = await newPage(t, server.url);

  let el = await settledTeams(page);
  assert.equal(await el.locator(".chk--on").count(), 1, "типово — шумимо");
  assert.match(await el.innerText(), /dc\/t1/);
  await el.click();
  await page.waitForSelector(".cv-ask", { timeout: 15000 });
  await page.click('.cv-ask [data-a="ok"]');
  await page.waitForSelector(".cv-ask", { state: "detached" });
  await until(() => !!muteDb(w.stateFile)[CHANNEL]);
  assert.ok(muteDb(w.stateFile)[CHANNEL], "тиша ЛІГИ мусить лягти у файл шва `DC_TEAMS_FAKE`");

  await page.reload();
  await page.waitForSelector("#bar [data-dd]", { timeout: 15000 });
  el = await settledTeams(page);
  assert.equal(await el.locator(".chk--on").count(), 0, "після перезавантаження — вимкнено");
  assert.match(await el.innerText(), /вимкнено для всіх/);
  assert.deepEqual(page.errors, []);
});

guardRealDeai("6: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
