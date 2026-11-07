/**
 * Напрямки простору (Deai 0.15.0, етап 4d-1, Task 6) — живе проведення: справжній `serve.py` на вільному порту з тимчасовою
 * `DEAI_HOME`, справжній Chromium. Мережі нема: репо напрямків — вигадані адреси, до яких ніхто не ходить (простір без
 * постачальника `vcs` їх мовчки не застосовує), ЛІГА — без Supabase.
 *
 * Юніти (`tests/test_tracks.py`, `tests/test_serve_tracks.py`…) доводять кожну ланку окремо; тут те, чого вони не бачать:
 * що задача, створена через `POST /api/task-new`, справді лягає в теку напрямку на диску, що на екрані «Задачі» її картка
 * несе мітку напрямку (і чіп фільтра теж), що відмова `unknown-track` не лишає ні теки, ні задачі, і що відповідь
 * `GET /api/spaces` не віддає браузеру ні шляхів, ні адрес репо.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (`track: 'web'` → тека під `root` напрямку, мітка `Web` у картці й чіпі) — `track_root` + `tracks.label_tag` (`label`
 *     напрямку, а не сирий id; мутація «мітка = id» червонить саме цей сценарій).
 *   2 (`profile: 'mobile'` — синонім → мітка `Mobile`, тека — шлях простору) — розбір `profile` у маршруті `task-new`
 *     (`known` напрямок) + `track_root` (`root` нема → шлях простору).
 *   3 (`track: 'nope'` → 400 `unknown-track`, теки й задачі нема) — перевірка напрямку в маршруті ДО `task_new`
 *     (мутація «після запису» червонить саме цей сценарій).
 *   4 (ЛІГА без поля → `united`; запис має і `track`, і `profile`; мітка `United`) — `task_new(legacy=True)` пише обидва
 *     ключі (колеги на 0.14.0 читають `profile` зі спільного реєстру) + ЯВНІ напрямки `space.json` (4b; після 4d-4a адаптера
 *     `legacy_tracks` нема, їх пише крок міграції). 4a — шар вимкнено: напрямків нема, `track` → `unknown-track` (ізольований режим).
 *   5 (`/api/spaces`: `tracks` без `root`/`repo`) — проєкція в `_space_view`.
 *   6 (`profile: 'united'` у звичайному просторі → 200, напрямок за замовчуванням, без помилки) — спека §6.7: застарілий
 *     ключ, що не є напрямком простору, ігнорується, як у 0.14.0 (скіл пайплайну шле його всім).
 */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
// 4d-4b: кеш браузерів Playwright читається при ІМПОРТІ playwright — `_env.mjs` мусить бути раніше за нього
import "./_env.mjs";
import { chromium } from "playwright";
import { guardRealDeai, postJson, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs`): тести ЦЬОГО файла йдуть послідовно, тож одна база на всі. */
const PORT_BASE = 23000;
const ROOT = realpathSync(path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", ".."));
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";
/* Вигадана адреса репо напрямку `web`: у відповідь `/api/spaces` вона потрапити не мусить (сценарій 5). */
const WEB_REPO = "ssh://git@example.com/o/r.git";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── прилади ───────────────────────────────────────────────────────────────────────────────────────── */

/** Зупинити сервер, потім прибрати тимчасову домівку й теку конфіга: у ЦЬОМУ порядку й однією дією (порядок кількох `t.after` не
 *  гарантуємо), і при падінні теж. `home` є лише в режимі просторів; теки задач лежать усередині цих двох. */
function shutdown(t, server) {
  t.after(async () => {
    await stop(server.child);
    if (server.home) rmSync(server.home, { recursive: true, force: true });
    rmSync(path.dirname(server.tasksFile), { recursive: true, force: true });
  });
}

/**
 * Сервер звичайного простору «Alpha» (id `alpha`) з двома напрямками: `web` (з власним `root` і вигаданим репо) і `mobile`
 * (без `root` — тека задачі лягає в шлях простору). Фікстура пише `space.json` без `tracks`, тож дописуємо його одразу після
 * старту (сервер читає `space.json` на кожен запит, кешу нема). Повертає ще `webRoot` і `spPath`.
 */
async function bootPlain(t, portOffset) {
  const A = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE + portOffset,
    spaces: [{ name: "Alpha", id: "alpha", color: "space-2", tasks: { t1: { dir: A.dir, title: "Задача один" } } }],
  });
  shutdown(t, server);
  /* ⛔ Корінь напрямку НЕ в чекауті: `spaces.check_new_path` відкидає шлях усередині теки інструмента (`path-tool`), і `root`
     мовчки стає шляхом простору. Тимчасова домівка тесту (`HOME` сервера) — дозволена; `shutdown` її прибирає. */
  const webRoot = path.join(server.home, "web-root");
  mkdirSync(webRoot);
  const spPath = server.spaces[0].path;
  writeFileSync(path.join(spPath, "space.json"), JSON.stringify({
    name: "Alpha", color: "space-2", default_track: "web",
    tracks: [
      { id: "web", label: "Web", root: webRoot, repo: WEB_REPO },
      { id: "mobile", label: "Mobile" },
    ],
  }));
  return { ...server, webRoot, spPath };
}

const newTask = (url, body) => postJson(url, "/api/task-new", { space: "alpha", ...body });

/** Задача за id з `/api/tasks` (простір запиту — поточний; `task-new` робить простір задачі поточним). */
async function taskRow(url, id) {
  const data = await (await fetch(`${url}/api/tasks`)).json();
  return (data.tasks || []).find((x) => x.id === id) ?? null;
}

/** Екран «Задачі» очима дизайнера: текст рядка метаданих картки `id` (`null` — картки нема) і підписи чіпів-міток. */
async function homeView(t, url, id) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-act="home"]', { timeout: 15000 });
  await page.click('#bar [data-act="home"]');
  /* Картка поточної задачі (`t1` чи щойно створена) вже є на екрані, коли він наповнений: чекаємо хоч одну. */
  await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
  const card = page.locator(`#tasks-home .th-card[data-id="${id}"]`);
  const meta = (await card.count()) ? await card.locator(".th-meta").innerText() : null;
  const chips = await page.$$eval('#tasks-home [data-th="tag"]', (els) => els.map((e) => e.textContent.trim()));
  assert.deepEqual(errors, []);
  return { meta, chips };
}

/** Вміст теки (імена) або `[]`, коли її нема. */
const ls = (dir) => (existsSync(dir) ? readdirSync(dir).sort() : []);

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("1: `track: 'web'` → тека задачі під `root` напрямку; на «Задачах» у картки мітка `Web` (і чіп фільтра)", async (t) => {
  const { url, webRoot } = await bootPlain(t, 0);
  const res = await newTask(url, { id: "w1", title: "Веб-задача", track: "web" });
  const body = await res.json();
  assert.equal(res.status, 200, JSON.stringify(body));
  assert.equal(path.dirname(realpathSync(body.dir)), webRoot, "тека задачі мусить лягти під `root` напрямку");
  assert.ok(existsSync(path.join(body.dir, "index.html")) || readdirSync(body.dir).length > 0, "тека задачі порожня");

  const row = await taskRow(url, "w1");
  assert.equal(row?.track, "web");
  assert.deepEqual(row?.tags, ["Web"], "мітка — `label` напрямку");

  const { meta, chips } = await homeView(t, url, "w1");
  assert.ok(meta !== null, "картки нової задачі нема на екрані «Задачі»");
  assert.match(meta, /(^| · )Web( · |$)/, `у картці нема мітки «Web»: ${meta}`);
  assert.ok(chips.includes("Web"), `чіпа «Web» нема серед ${JSON.stringify(chips)}`);
});

test("2: `profile: 'mobile'` (синонім; mobile — відомий напрямок) → мітка `Mobile`, тека — шлях простору", async (t) => {
  const { url, spPath } = await bootPlain(t, 100);
  const res = await newTask(url, { id: "m1", title: "Мобільна задача", profile: "mobile" });
  const body = await res.json();
  assert.equal(res.status, 200, JSON.stringify(body));
  assert.equal(path.dirname(realpathSync(body.dir)), realpathSync(spPath), "`mobile` без `root` — тека лягає в шлях простору");

  const row = await taskRow(url, "m1");
  assert.equal(row?.track, "mobile", "синонім `profile` мусить стати напрямком");
  assert.deepEqual(row?.tags, ["Mobile"]);

  const { meta, chips } = await homeView(t, url, "m1");
  assert.ok(meta !== null, "картки нової задачі нема на екрані «Задачі»");
  assert.match(meta, /(^| · )Mobile( · |$)/, `у картці нема мітки «Mobile»: ${meta}`);
  assert.ok(chips.includes("Mobile"), `чіпа «Mobile» нема серед ${JSON.stringify(chips)}`);
});

test("3: `track: 'nope'` → 400 `unknown-track`; теки нема, задачі нема ні в API, ні на «Задачах»", async (t) => {
  const { url, webRoot, spPath } = await bootPlain(t, 200);
  const before = { web: ls(webRoot), space: ls(spPath), tasks: JSON.stringify((await (await fetch(`${url}/api/tasks`)).json()).tasks) };

  const res = await newTask(url, { id: "ghost1", title: "Привид", track: "nope" });
  assert.equal(res.status, 400);
  const body = await res.json();
  assert.equal(body.ok, false);
  assert.equal(body.code, "unknown-track", JSON.stringify(body));

  /* Інший вигляд відмови — не за шаблоном id (`Nope`) — той самий порядок: відмова до будь-якого запису. */
  const bad = await newTask(url, { id: "ghost2", title: "Привид два", track: "Nope" });
  assert.equal(bad.status, 400);
  assert.equal((await bad.json()).code, "bad-track");

  assert.deepEqual(ls(webRoot), before.web, "після відмови зʼявилась тека під `root` напрямку");
  assert.deepEqual(ls(spPath), before.space, "після відмови зʼявилась тека в шляху простору");
  assert.ok(!existsSync(path.join(webRoot, "ghost1")) && !existsSync(path.join(spPath, "ghost1")), "тека відмовленої задачі існує");
  assert.equal(JSON.stringify((await (await fetch(`${url}/api/tasks`)).json()).tasks), before.tasks, "список задач змінився");
  assert.equal(await taskRow(url, "ghost1"), null);
  assert.equal(await taskRow(url, "ghost2"), null);

  const { meta } = await homeView(t, url, "ghost1");
  assert.equal(meta, null, "відмовлена задача зʼявилась на екрані «Задачі»");
});

/** Спільна частина сценарію 4: нова задача ЛІГИ без поля напрямку. `readRecord` дає запис із файла задач ЛІГИ. */
async function ligaCase(t, server) {
  const res = await postJson(server.url, "/api/task-new", { id: "l1", title: "Задача ліги" });
  const body = await res.json();
  assert.equal(res.status, 200, JSON.stringify(body));

  const rec = JSON.parse(readFileSync(server.tasksFile, "utf8")).tasks.l1;
  assert.equal(rec?.track, "united", "без поля напрямок — `united`");
  assert.equal(rec?.profile, "united", "запис ЛІГИ мусить нести й `profile` (колеги на 0.14.0 читають його зі спільного реєстру)");

  const row = await taskRow(server.url, "l1");
  assert.equal(row?.track, "united");
  assert.deepEqual(row?.tags, ["United"]);

  const { meta, chips } = await homeView(t, server.url, "l1");
  assert.ok(meta !== null, "картки нової задачі нема на екрані «Задачі»");
  assert.match(meta, /(^| · )United( · |$)/, `у картці нема мітки «United»: ${meta}`);
  assert.ok(chips.includes("United"), `чіпа «United» нема серед ${JSON.stringify(chips)}`);
}

test("4a: шар просторів вимкнено (`DC_TASKS_FILE`) — напрямків нема (4d-4a: адаптера ЛІГИ більше нема): нова задача без поля — без `track` і без мітки, `track` → 400 `unknown-track`", async (t) => {
  const A = taskFixture({ html: MOCKUP });
  const server = await startServer(A.dir, { portBase: PORT_BASE + 300 });
  shutdown(t, server);
  const res = await postJson(server.url, "/api/task-new", { id: "l1", title: "Задача ліги" });
  const body = await res.json();
  assert.equal(res.status, 200, JSON.stringify(body));
  const rec = JSON.parse(readFileSync(server.tasksFile, "utf8")).tasks.l1;
  assert.equal(rec?.track, undefined, "без напрямків `track` не пишеться (раніше адаптер ставив `united`)");
  assert.ok(!rec?.profile, "`profile` лишається порожнім: нема напрямку, який дзеркалити");
  const row = await taskRow(server.url, "l1");
  assert.equal(row?.track ?? null, null);
  assert.deepEqual(row?.tags, [], "мітки нема: адаптерної `United` більше нема");
  const bad = await postJson(server.url, "/api/task-new", { id: "l2", title: "Привид", track: "united" });
  assert.equal(bad.status, 400);
  assert.equal((await bad.json()).code, "unknown-track", "напрямків нема — будь-який `track` невідомий (ізольований режим)");
  assert.ok(!(JSON.parse(readFileSync(server.tasksFile, "utf8")).tasks.l2), "відмова не лишила запису");
});

test("4b: ЛІГА як простір з інтеграціями й ЯВНИМИ напрямками (те, що пише крок `liga-4d4a`) — нова задача без поля → `track` і `profile` = `united`, мітка `United`", async (t) => {
  const A = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE + 400,
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { t1: { dir: A.dir, title: "Задача один" } } }],
  });
  shutdown(t, server);
  /* Напрямки ЛІГИ — явні в `space.json`, як після кроку міграції (сервер читає файл на кожен запит). Корінь `liga360` нема — тека простору. */
  writeFileSync(path.join(server.spaces[0].path, "space.json"), JSON.stringify({
    name: "Liga", color: "space-2", default_track: "united",
    tracks: [{ id: "united", label: "United", ds: "united" }, { id: "liga360", label: "LIGA360", ds: "liga360" }, { id: "seo", label: "SEO", ds: "seo" }],
  }));
  await ligaCase(t, server);
});

test("5: `GET /api/spaces` — `tracks: [{id, label}]` і `default_track` без `root`/`repo`; шляхи й адреси не їдуть у браузер", async (t) => {
  const { url, webRoot } = await bootPlain(t, 500);
  const raw = await (await fetch(`${url}/api/spaces`)).text();
  const alpha = JSON.parse(raw).spaces.find((s) => s.id === "alpha");
  assert.deepEqual(alpha.tracks, [{ id: "web", label: "Web" }, { id: "mobile", label: "Mobile" }]);
  assert.equal(alpha.default_track, "web");
  for (const track of alpha.tracks) assert.deepEqual(Object.keys(track).sort(), ["id", "label"]);
  /* Свідок: відповідь не містить ні кореня напрямку, ні адреси репо де завгодно (не лише в `tracks`). */
  assert.ok(!raw.includes(webRoot), "корінь напрямку потрапив у `/api/spaces`");
  assert.ok(!raw.includes("example.com") && !raw.includes(WEB_REPO), "адреса репо напрямку потрапила в `/api/spaces`");
});

test("6: `profile: 'united'` у звичайному просторі (не напрямок простору) → 200, задача йде в напрямок за замовчуванням, без помилки (спека §6.7)", async (t) => {
  const { url, webRoot } = await bootPlain(t, 600);
  const res = await newTask(url, { id: "p1", title: "Задача від скіла пайплайну", profile: "united" });
  const body = await res.json();
  assert.equal(res.status, 200, `старий ключ \`profile\` мусить проходити, як у 0.14.0: ${JSON.stringify(body)}`);
  assert.equal(body.ok, true);
  assert.equal(path.dirname(realpathSync(body.dir)), webRoot, "задача мусить піти в напрямок за замовчуванням (`web`)");

  const row = await taskRow(url, "p1");
  assert.equal(row?.track, "web", "ігнорований `profile` не мусить стати напрямком");
  assert.deepEqual(row?.tags, ["Web"]);

  const { meta } = await homeView(t, url, "p1");
  assert.ok(meta !== null, "картки нової задачі нема на екрані «Задачі»");
  assert.match(meta, /(^| · )Web( · |$)/, `у картці нема мітки «Web»: ${meta}`);
  assert.doesNotMatch(meta, /united/i, "значення ігнорованого `profile` просочилось у мітку");
});

guardRealDeai("7: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
