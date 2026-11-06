/**
 * Міграція ЛІГИ на старті сервера (Deai 0.17.0, етап 4d-3a, Task 6) — живе проведення: справжній `serve.py` на вільному порту з
 * тимчасовими `HOME`/`DEAI_HOME`, справжній Chromium. Простір ЛІГА — старий `tasks.json` з вигаданим конфігом (Supabase + Jira)
 * і `DC_MIGRATE_LIGA=1` (шов старту: ізольований прогін мігрує лише з ним і лише в тимчасовому домі).
 *
 * Юніти (`tests/test_liga_migrate.py`: `PlanTest`, `RunTest`, `RestoreTest`, `StartupTest`, `AfterMigrationParity`) доводять кожну
 * ланку; тут те, що бачить людина: перший старт лишає датований бекап і позначку, екран «Підключення» ЛІГИ показує ТРИ модулі
 * ввімкненими (по одній картці на роль), екран «Задачі» — статуси Jira й вкладку «Команда», а другий старт того самого дому НЕ
 * пише нічого (mtime і sha256 `space.json`/`secrets.json`/`last.json` ті самі, нового бекапу нема).
 *
 * ⚠️ Мережі нема, і не лише з принципу: вбудовані модулі Supabase/Jira приймають ЛИШЕ `https://<DNS-імʼя>` (не IP, не localhost),
 * тож loopback-сервер їм недосяжний. Дані для екранів дають шви-файли ізоляції (`DC_TRACKER_FAKE`, `DC_TEAM_FAKE`): для мігрованого
 * запису з `shared_state: true` саме вони (а не модуль) відповідають у ізольованому прогоні — закон ізоляції 4d-3a. Усе поза
 * машиною в браузері — `abort` і запис у `outside` (тест стверджує, що там порожньо).
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (прибери охорону — подивись, чи червоніє):
 *   1 (бекап і позначка)          — `liga_migrate.startup` у `serve.main` (без виклику міграції — немає бекапу й позначки) і шов
 *        `DC_MIGRATE_LIGA` (`startup`); бекап — `_backup`, позначка — `_commit_space`.
 *   2 («Підключення»: три модулі)  — `plan()` (ролі `tracker`/`dashboard`/`notify` мігрують) і `connections-model.js` (одна картка ролі).
 *   3 («Задачі»: статуси й «Команда») — `shared_state` → `implicit.route()` для мігрованих записів (без нього модуль пішов би в
 *        мережу замість шва).
 *   4 (другий старт нічого не пише) — позначка `skip-done` у `plan()` + «`plan()` поза замком» у `_run` (без нього зʼявляються
 *        лише `.lock`/`migrations/`, але вже створені тут; тож ключове — незмінність `space.json`, `secrets.json`, `last.json`).
 *
 * Етап 4d-3b (0.18.0, другий крок `liga-4d3b`: `comments` і `vcs` ЛІГИ — явні модулі `supabase-comments`/`git-sync`):
 *   1b (два бекапи на старті)      — `liga_migrate.run_all`/`startup` ітерують `STEPS` (без цього — один бекап або жодного для b); суфікс
 *        і маніфест кроку — `Step.stamp_re`/`_backup`; бекап b знімає space.json ПІСЛЯ запису a (план b рахується після a);
 *        ключ коментарів лише в `secrets.json` (`_commit_space` b) і `last.json.steps` (`_write_last` зберігає мапу кроків).
 *   2b («Підключення»: п'ять карток)  — `plan(step b)` записує обидва модулі; capabilities: `comments`/`vcs` — id, `publish` лишається
 *        `legacy` (крок публікацію не мігрує). Одна картка на роль (`connections-model.js`).
 *   3b (форма «Нова задача» без «Репозиторій») — `compat: design-canvas` запису `git-sync` → `serve.vcs_legacy_texts` → ключ `compat` у
 *        `/api/spaces` → `isLegacyVcs` у `spaces-model.js` (без `compat` поле зʼявилось би: поведінка людини змінилась би).
 *   3c (мігрований git-sync бере старе дзеркало) — накладка `_flat_mirror_overlay` (`cache_dir = _mirrors_base()`, `mirror_flat`) у `serve.py`:
 *        без неї push створив би дзеркало модуля під `<DEAI_HOME>/cache/liga/git-sync/mirrors` замість передствореного плоского
 *        `<DC_MIRRORS_DIR>/<slug>` (HEAD того не зрушив би, у базі дзеркал зʼявилась би зайва тека). ⚠️ У ізольованому прогоні запис
 *        `shared_state` йде шляхом `_vcs_legacy_ctx()` (закон ізоляції), тож накладку тут стереже саме він; гілку `if legacy:` у
 *        `vcs_provider` (звичайний прогін) стережуть юніти `VcsCompat`.
 *   4b (другий старт, дзеркала)    — `skip-done` ОБОХ кроків у `plan()`; старт нічого не пише в дзеркала (HEAD і перелік після 3c ті самі),
 *        `<DEAI_HOME>/cache/liga/git-sync/mirrors` нема.
 *   Паритет усього, що бачить людина (канали, тексти, дзеркала), — юніти `AfterMigrationParity4d3b` (`tests/test_liga_migrate_b.py`).
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { guardRealDeai, sleep, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs`): тести ЦЬОГО файла йдуть послідовно, тож одна база на всі. */
const PORT_BASE = 23100;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

/* Вигадані значення (репо приватне й знеособлене). */
const JIRA_BASE = "https://jira.example.com";
const JIRA_EMAIL = "alpha@example.com";
const JIRA_TOKEN = "jira_live_token_alpha";
const SB_KEY = "sb_publishable_test"; // `LIGA_SUPABASE.supabase_key` фікстури
const MODULES = { tracker: "jira-tracker", dashboard: "supabase-dashboard", notify: "supabase-teams" };
const ALL_MODULES = { ...MODULES, comments: "supabase-comments", vcs: "git-sync" }; // + роли другого кроку (4d-3b)

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => {
  await browser?.close();
  if (S.running) await stop(S.running);
  /* Свою git-теку прибираємо за ТОЧНИМ шляхом (лише `dc-live-ligamig-*` прямо в tmpdir), не за шаблоном. */
  if (S.gitDir && path.dirname(S.gitDir) === realpathSync(tmpdir()) && path.basename(S.gitDir).startsWith("dc-live-ligamig-")) rmSync(S.gitDir, { recursive: true, force: true });
});

/* ── git: лише локально (як `git-sync.test.mjs`): оточення без глобального конфігу людини, без підказок і без мережі ── */
const gitEnv = (home) => ({
  ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith("GIT_"))),
  HOME: home, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1", GIT_TERMINAL_PROMPT: "0", GIT_SSH_COMMAND: "false", LC_ALL: "C",
});
const git = (home, cwd, ...args) => execFileSync("git", args, { cwd, env: gitEnv(home), encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
/** Імʼя плоского дзеркала 0.7.0 (`_mirror` у `git-sync/server.py`, `mirror_flat`): slug останнього відрізка після `:` адреси. */
const flatSlug = (repo) => repo.split(":").pop().replace(/[^\w.-]+/g, "-").replace(/^-+|-+$/g, "");

/** Теки дзеркал у базі (без `<slug>@lock` — замок `git-sync` лишається поруч після кожного синку, і в 0.17 теж). */
const mirrorDirs = () => readdirSync(S.mirrorsDir).filter((n) => !n.endsWith("@lock")).sort();

const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");
const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));

/** Спільний стан файла: перший старт, його машина (для другого), тека з швами. */
const S = {};

async function newPage(t, url) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  t.after(() => context.close());
  const outside = [];
  await context.route((u) => !["127.0.0.1", "localhost"].includes(new URL(u.href).hostname) && !/^(data|blob|about):/.test(u.protocol), (route) => {
    outside.push(route.request().url());
    return route.abort("blockedbyclient");
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  page.on("dialog", async (d) => { errors.push(`нативний діалог: ${d.message()}`); await d.dismiss(); });
  page.errors = errors;
  page.outside = outside;
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-act="home"]', { timeout: 15000 });
  return page;
}

test("1: перший старт мігрує ЛІГУ: датований бекап, позначка, секрети тільки в secrets.json", async (t) => {
  const A = taskFixture({ html: MOCKUP });
  const seams = mkdtempSync(path.join(tmpdir(), "dc-liga-mig-"));
  const tracker = path.join(seams, "tracker.json");
  const team = path.join(seams, "team.json");
  writeFileSync(tracker, JSON.stringify({ "DEMO-1": { name: "Фейк у роботі", cat: "indeterminate" } }));
  writeFileSync(team, JSON.stringify([
    { id: "mine1", name: "Моя задача", designer: "Alpha", code_url: "https://example.com/p/mine1" },
    { id: "colleague", name: "Задача колеги", designer: "Beta", code_url: "https://example.com/p/colleague" }]));
  /* Локальний bare-origin і плоске дзеркало 0.7.0, створене ДО першого старту рівно там, де його лишила б версія 0.17: у `DC_MIRRORS_DIR`
     (тимчасова тека, не `.mirrors` репо) під імʼям `flatSlug(origin)`; справжній клон origin, як це робить сам `git-sync`. Без нього
     «дзеркал не зʼявилось» трималось би й коли накладка `cache_dir`/`mirror_flat` зламана: у тесті нічого не синкається. */
  S.gitDir = realpathSync(mkdtempSync(path.join(tmpdir(), "dc-live-ligamig-")));
  S.origin = path.join(S.gitDir, "origin.git");
  S.mirrorsDir = path.join(S.gitDir, "mirrors");
  S.slug = flatSlug(S.origin);
  git(S.gitDir, S.gitDir, "init", "--bare", "--quiet", "--initial-branch=main", S.origin);
  const seed = path.join(S.gitDir, "seed");
  git(S.gitDir, S.gitDir, "clone", "--quiet", S.origin, seed);
  git(S.gitDir, seed, "symbolic-ref", "HEAD", "refs/heads/main");
  writeFileSync(path.join(seed, "README.md"), "seed\n");
  git(S.gitDir, seed, "add", "-A");
  git(S.gitDir, seed, "-c", "user.name=Seed", "-c", "user.email=seed@example.invalid", "commit", "--quiet", "-m", "seed");
  git(S.gitDir, seed, "push", "--quiet", "origin", "main");
  git(S.gitDir, S.gitDir, "clone", "--quiet", "--branch", "main", S.origin, path.join(S.mirrorsDir, S.slug));
  S.mirror = path.join(S.mirrorsDir, S.slug);
  S.mirrorHeadBefore = git(S.gitDir, S.mirror, "rev-parse", "HEAD");
  S.mirrorsListBefore = readdirSync(S.mirrorsDir).sort();
  assert.deepEqual(S.mirrorsListBefore, [S.slug]);
  S.env = { DC_MIGRATE_LIGA: "1", DC_TRACKER_FAKE: tracker, DC_TEAM_FAKE: team, DC_TEAMS_FAKE: "", DC_MIRRORS_DIR: S.mirrorsDir,
    GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1", DC_IDENTITY_NAME: "Дизайнерка Тест", DC_IDENTITY_EMAIL: "me@example.invalid" };
  S.first = await startServer(null, {
    portBase: PORT_BASE, env: S.env, supabase: true, deaiDir: "state-deai",
    legacyExtra: { jira_base: JIRA_BASE, jira_email: JIRA_EMAIL, jira_token: JIRA_TOKEN },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A.dir, title: "Моя задача", jira: "DEMO-1" } } }],
  });
  S.running = S.first.child;
  const { deaiHome } = S.first;
  /* Міграція йде ДО відкриття порту (`serve.main`): коли сервер відповів, усе вже на диску. */
  const all = readdirSync(path.join(deaiHome, "backups")).sort();
  const backups = all.filter((n) => /-liga-4d3a$/.test(n));
  assert.equal(backups.length, 1, `рівно один бекап кроку 4d-3a: ${JSON.stringify(backups)}`);
  /* 4d-3b: два незалежні кроки на одному старті — два датовані бекапи з суфіксом СВОГО кроку (раніше був один). */
  const backupsB = all.filter((n) => /-liga-4d3b$/.test(n));
  assert.equal(backupsB.length, 1, `рівно один бекап кроку 4d-3b: ${JSON.stringify(backupsB)}`);
  assert.equal(all.length, 2, `рівно два бекапи на старті: ${JSON.stringify(all)}`);
  const manifest = readJson(path.join(deaiHome, "backups", backups[0], "manifest.json"));
  assert.ok(manifest.files["tasks.json"] && manifest.files["spaces.json"], `маніфест: ${JSON.stringify(Object.keys(manifest.files))}`);
  assert.equal(statSync(path.join(deaiHome, "backups", backups[0])).mode & 0o777, 0o700);
  const spacePath = path.join(S.first.spaces[0].path, "space.json");
  const sj = readJson(spacePath);
  const mark = sj.migrations?.["liga-4d3a"];
  assert.ok(mark, `позначки нема в space.json: ${JSON.stringify(sj)}`);
  assert.equal(mark.backup, backups[0]);
  assert.deepEqual(mark.roles, ["tracker", "dashboard", "notify"]);
  /* Другий крок (4d-3b): свій бекап, своя позначка, ролі `comments` і `vcs`; бекап b знімає вже мігрований кроком a space.json. */
  const markB = sj.migrations?.["liga-4d3b"];
  assert.ok(markB, `позначки 4d-3b нема: ${JSON.stringify(sj.migrations)}`);
  assert.equal(markB.backup, backupsB[0]);
  assert.deepEqual(markB.roles, ["comments", "vcs"]);
  assert.ok(readJson(path.join(deaiHome, "backups", backupsB[0], "space.json")).migrations["liga-4d3a"], "бекап b бачить запис a");
  assert.equal(readJson(path.join(deaiHome, "backups", backupsB[0], "manifest.json")).migration, "liga-4d3b");
  assert.equal(readJson(path.join(deaiHome, "backups", backups[0], "manifest.json")).migration, "liga-4d3a");
  assert.equal(statSync(path.join(deaiHome, "backups", backupsB[0])).mode & 0o777, 0o700);
  assert.deepEqual(Object.keys(sj.modules).sort(), ["git-sync", "jira-tracker", "supabase-comments", "supabase-dashboard", "supabase-teams"]);
  assert.equal(sj.name, "Liga", "чужі ключі space.json (імʼя, колір) збережено");
  assert.equal(sj.color, "space-2");
  /* ⛔ Значення секретів — лише в `secrets.json` (0600): ні в `space.json`, ні в `last.json`, ні в маніфесті. */
  const secretsPath = path.join(deaiHome, "secrets.json");
  assert.equal(statSync(secretsPath).mode & 0o777, 0o600);
  const sec = readJson(secretsPath);
  assert.equal(sec.liga["jira-tracker"].token, JIRA_TOKEN);
  assert.equal(sec.liga["supabase-dashboard"].key, SB_KEY);
  assert.equal(sec.liga["supabase-comments"].key, SB_KEY, "ключ Supabase для коментарів — теж лише в secrets.json");
  const last = readJson(path.join(deaiHome, "migrations", "last.json"));
  assert.equal(last.status, "done");
  assert.deepEqual(Object.keys(last.steps).sort(), ["liga-4d3a", "liga-4d3b"], "last.json тримає звіт кожного кроку");
  for (const f of [spacePath, path.join(deaiHome, "migrations", "last.json"), path.join(deaiHome, "backups", backups[0], "manifest.json"),
    path.join(deaiHome, "backups", backupsB[0], "manifest.json")]) {
    const body = readFileSync(f, "utf8");
    assert.ok(!body.includes(JIRA_TOKEN) && !body.includes(SB_KEY), `секрет у ${path.basename(f)}`);
  }
  S.spacePath = spacePath;
  S.backups = backups;
  S.backupsB = backupsB;
  /* Дзеркала ЛІГИ — плоска тека 0.7.0; міграція її не чіпає (сам синк — тест 3c), а дзеркал модуля під `<DEAI_HOME>/cache` не буває. */
  assert.deepEqual(mirrorDirs(), S.mirrorsListBefore, "міграція не додала дзеркал");
  assert.equal(git(S.gitDir, S.mirror, "rev-parse", "HEAD"), S.mirrorHeadBefore, "міграція не чіпала дзеркала");
  assert.equal(existsSync(path.join(deaiHome, "cache", "liga", "git-sync", "mirrors")), false);
});

test("2: «Підключення» ЛІГИ — п'ять модулів ввімкнені (три кроку a + comments і vcs кроку b), по одній картці на роль; публікація — вбудована", async (t) => {
  const { url } = S.first;
  const spaces = (await (await fetch(`${url}/api/spaces`)).json()).spaces;
  const caps = spaces.find((s) => s.id === "liga").capabilities;
  assert.deepEqual({ tracker: caps.tracker, dashboard: caps.dashboard, notify: caps.notify }, MODULES);
  /* 4d-3b: `comments` і `vcs` — явні модулі; публікація й далі вбудована (`publish` не мігрує). */
  assert.deepEqual({ publish: caps.publish, comments: caps.comments, vcs: caps.vcs }, { publish: "legacy", comments: "supabase-comments", vcs: "git-sync" });
  const mods = (await (await fetch(`${url}/api/modules?space=liga`)).json()).modules;
  for (const id of Object.values(ALL_MODULES)) {
    const m = mods.find((x) => x.id === id);
    assert.ok(m && m.enabled === true && m.implicit !== true, `${id} мусить бути явно ввімкнений: ${JSON.stringify(m)}`);
  }
  const page = await newPage(t, url);
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="static-publish"]', { timeout: 15000 });
  for (const id of Object.values(ALL_MODULES)) {
    assert.equal(await page.locator(`.cn-card[data-id="${id}"]`).count(), 1, `${id}: рівно одна картка (без дубля «вбудованої»)`);
    const cls = await page.locator(`.cn-card[data-id="${id}"] .cn-badge`).getAttribute("class");
    assert.ok(!/cn-badge--off\b/.test(cls), `${id}: картка мусить бути ввімкненою, а клас бейджа ${cls}`);
  }
  assert.deepEqual(page.errors, []);
  assert.deepEqual(page.outside, [], "запити назовні");
});

test("3: «Задачі» ЛІГИ — статус Jira на картці й вкладка «Команда»", async (t) => {
  const { url } = S.first;
  const page = await newPage(t, url);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
  const bdg = await page.$$eval("#tasks-home .th-card", (els) => Object.fromEntries(els
    .map((e) => [e.dataset.id, e.querySelector(".th-bdg[class*='th-bdg--']:not(.th-bdg--com)")?.textContent?.trim() ?? null])
    .filter(([, v]) => v)));
  assert.deepEqual(bdg, { mine1: "Фейк у роботі" }, "статус із трекера (шов `DC_TRACKER_FAKE` для мігрованого запису)");
  const tab = page.locator('#tasks-home [data-th="tab"][data-v="team"]');
  assert.match(await tab.textContent(), /Команда · 2/);
  await tab.click();
  await page.click('#tasks-home [data-th="status"][data-v="all"]');
  await page.waitForFunction(() => document.querySelectorAll("#tasks-home .th-card").length === 2, null, { timeout: 15000 });
  const ids = (await page.$$eval("#tasks-home .th-card", (els) => els.map((e) => e.dataset.id))).sort();
  assert.deepEqual(ids, ["colleague", "mine1"]);
  assert.equal(await page.locator("#tasks-home .th-banner").count(), 0, "банера помилки нема");
  assert.deepEqual(page.errors, []);
  assert.deepEqual(page.outside, [], "запити назовні");
});

test("3b: форма «Нова задача» мігрованої ЛІГИ — без поля «Репозиторій» (ціль синку живе в tasks.json, як до міграції)", async (t) => {
  const { url } = S.first;
  const page = await newPage(t, url);
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card", { timeout: 15000 });
  /* ⚠️ У ЛІГА (інтеграції ввімкнені) голова екрана без кнопки «Нова задача» (`noIntegrations` у `tasks-home.js`), тож форму відкриваємо тим
     самим делегованим обробником, що й кнопка: вузол `data-th="newtask"` доданий у `#tasks-home` і натиснутий — `newTaskDialog()` справжній. */
  await page.evaluate(() => {
    const b = document.createElement("button");
    b.dataset.th = "newtask";
    b.id = "t-newtask";
    document.getElementById("tasks-home").append(b);
  });
  await page.click("#t-newtask");
  await page.waitForSelector('form[data-form="task"]', { timeout: 15000 });
  assert.equal(await page.locator("#tf-title").count(), 1, "форма відкрилась");
  const model = await page.evaluate(async () => {
    const m = await import("/app/spaces-model.js");
    const row = (await (await fetch("/api/spaces")).json()).spaces.find((s) => s.id === "liga");
    return { hasVcs: m.hasVcs(row), isLegacyVcs: m.isLegacyVcs(row), compat: row.compat };
  });
  assert.deepEqual(model, { hasVcs: true, isLegacyVcs: true, compat: { comments: "comment-layer", vcs: "design-canvas" } },
    "рішення форми: роль vcs є, але це зашитий git-sync → поле не показуємо");
  assert.equal(await page.locator("#tf-repo").count(), 0, "поля «Репозиторій» нема: git-sync у ЛІГА — зашитий (compat design-canvas)");
  assert.equal(await page.locator('form[data-form="task"]').getByText("Репозиторій", { exact: false }).count(), 0, "жодного підпису «Репозиторій» у формі");
  assert.deepEqual(page.errors, []);
  assert.deepEqual(page.outside, [], "запити назовні");
});

test("3c: мігрований git-sync справді бере СТАРЕ плоске дзеркало: push через локальний origin лягає в нього, нових дзеркал нема", async () => {
  const { url, legacyFile, deaiHome } = S.first;
  /* Ціль синку — зашитий у `tasks.json` формат 0.17 (`gitlab{repo, path}`); сервер читає файл на кожен запит. */
  const cfg = readJson(legacyFile);
  cfg.tasks.mine1.gitlab = { repo: S.origin, path: "mockup/mine1", branch: "main" };
  writeFileSync(legacyFile, JSON.stringify(cfg));
  const st = await (await fetch(`${url}/api/vcs-status?it=it1`, { headers: { "X-Canvas-Task": "mine1" } })).json();
  assert.equal(st.configured, true, `ціль мусить бути видна: ${JSON.stringify(st)}`);
  const res = await fetch(`${url}/api/vcs-push`, {
    method: "POST", headers: { "Content-Type": "application/json", "X-Canvas-Task": "mine1" }, body: JSON.stringify({ it: "it1" }),
  });
  const body = await res.json();
  assert.equal(body.ok === false ? body.error : null, null, `push відмовлено: ${JSON.stringify(body)}`);
  assert.equal(body.synced, true, `push не дійшов до origin: ${JSON.stringify(body)}`);
  /* Дійшло до origin (локальний bare-репо) із зашитим текстом «design-canvas: sync». */
  assert.match(git(S.gitDir, S.origin, "log", "-1", "--format=%s", "main"), /^design-canvas: sync mockup\/mine1/);
  const tree = git(S.gitDir, S.origin, "ls-tree", "-r", "--name-only", "main").split("\n");
  assert.ok(tree.includes("mockup/mine1/pages.json") && tree.includes("mockup/mine1/holovna/index.html"), `дерево origin: ${JSON.stringify(tree)}`);
  /* Це зробило САМЕ передстворене плоске дзеркало: його HEAD зрушив і збігся з origin; нових тек у базі дзеркал нема. */
  const originHead = git(S.gitDir, S.origin, "rev-parse", "main");
  const mirrorHead = git(S.gitDir, S.mirror, "rev-parse", "HEAD");
  assert.notEqual(mirrorHead, S.mirrorHeadBefore, "HEAD старого дзеркала не змінився: push пішов не через нього");
  assert.equal(mirrorHead, originHead);
  assert.deepEqual(mirrorDirs(), S.mirrorsListBefore, "у базі дзеркал зʼявилась нова тека");
  assert.equal(existsSync(path.join(deaiHome, "cache", "liga", "git-sync", "mirrors")), false, "дзеркал модуля під <DEAI_HOME>/cache нема");
  assert.equal(existsSync(path.join(deaiHome, "cache", "liga")), false, "ЛІГА не заводить кеш модуля");
  S.mirrorHeadAfter = mirrorHead;
});

test("4: другий старт того самого дому нічого не пише (mtime і sha256 незмінні, нового бекапу нема)", async (t) => {
  const { deaiHome } = S.first;
  const files = [S.spacePath, path.join(deaiHome, "secrets.json"), path.join(deaiHome, "migrations", "last.json"), path.join(deaiHome, "spaces.json")];
  const before = files.map((f) => ({ f, mtime: statSync(f).mtimeMs, sha: sha(f) }));
  const backupsBefore = readdirSync(path.join(deaiHome, "backups")).sort();
  await stop(S.running);                                        // за PID (дитина `spawn`), не за шаблоном
  assert.ok(S.running.exitCode !== null || S.running.signalCode, "перший сервер мусить зупинитись");
  await sleep(1100);                                            // файлова система з секундною гранулярністю mtime теж побачила б запис
  S.second = await startServer(null, { portBase: PORT_BASE, env: S.env, machine: S.first });
  S.running = S.second.child;
  assert.equal((await fetch(`${S.second.url}/api/spaces`)).ok, true);
  await sleep(500);
  for (const b of before) {
    assert.equal(statSync(b.f).mtimeMs, b.mtime, `mtime змінився: ${path.basename(b.f)}`);
    assert.equal(sha(b.f), b.sha, `вміст змінився: ${path.basename(b.f)}`);
  }
  assert.deepEqual(readdirSync(path.join(deaiHome, "backups")).sort(), backupsBefore, "зʼявився новий бекап");
  assert.equal(backupsBefore.length, 2, "лишились рівно два бекапи (a і b), третього нема");
  assert.deepEqual(backupsBefore.map((n) => n.replace(/^.*-liga-/, "liga-")).sort(), ["liga-4d3a", "liga-4d3b"]);
  assert.deepEqual([S.backups[0], S.backupsB[0]].sort(), backupsBefore);
  const sj = readJson(S.spacePath);
  assert.ok(sj.migrations["liga-4d3a"], "позначка лишилась");
  assert.ok(sj.migrations["liga-4d3b"], "позначка 4d-3b лишилась");
  /* Дзеркала: старт нічого в них не пише (HEAD і перелік після push 3c ті самі), дзеркал модуля під `<DEAI_HOME>/cache` нема. */
  assert.deepEqual(mirrorDirs(), S.mirrorsListBefore, "другий старт змінив базу дзеркал");
  assert.equal(git(S.gitDir, S.mirror, "rev-parse", "HEAD"), S.mirrorHeadAfter, "другий старт зрушив дзеркало");
  assert.equal(existsSync(path.join(deaiHome, "cache", "liga", "git-sync", "mirrors")), false, "дзеркал git-sync у <DEAI_HOME>/cache нема");
  assert.equal(existsSync(path.join(deaiHome, "migrations", ".lock")), true);
  const caps = (await (await fetch(`${S.second.url}/api/spaces`)).json()).spaces.find((s) => s.id === "liga").capabilities;
  assert.equal(caps.tracker, "jira-tracker", "після рестарту ролі лишились явними");
  assert.deepEqual({ comments: caps.comments, vcs: caps.vcs, publish: caps.publish },
    { comments: "supabase-comments", vcs: "git-sync", publish: "legacy" }, "ролі кроку b теж лишились явними, публікація — вбудована");
});

guardRealDeai("5: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
