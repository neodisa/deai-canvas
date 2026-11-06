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
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync, mkdtempSync } from "node:fs";
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

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); if (S.running) await stop(S.running); });

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
  S.env = { DC_MIGRATE_LIGA: "1", DC_TRACKER_FAKE: tracker, DC_TEAM_FAKE: team, DC_TEAMS_FAKE: "" };
  S.first = await startServer(null, {
    portBase: PORT_BASE, env: S.env, supabase: true, deaiDir: "state-deai",
    legacyExtra: { jira_base: JIRA_BASE, jira_email: JIRA_EMAIL, jira_token: JIRA_TOKEN },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A.dir, title: "Моя задача", jira: "DEMO-1" } } }],
  });
  S.running = S.first.child;
  const { deaiHome } = S.first;
  /* Міграція йде ДО відкриття порту (`serve.main`): коли сервер відповів, усе вже на диску. */
  const backups = readdirSync(path.join(deaiHome, "backups")).filter((n) => /-liga-4d3a$/.test(n));
  assert.equal(backups.length, 1, `рівно один бекап міграції: ${JSON.stringify(backups)}`);
  const manifest = readJson(path.join(deaiHome, "backups", backups[0], "manifest.json"));
  assert.ok(manifest.files["tasks.json"] && manifest.files["spaces.json"], `маніфест: ${JSON.stringify(Object.keys(manifest.files))}`);
  assert.equal(statSync(path.join(deaiHome, "backups", backups[0])).mode & 0o777, 0o700);
  const spacePath = path.join(S.first.spaces[0].path, "space.json");
  const sj = readJson(spacePath);
  const mark = sj.migrations?.["liga-4d3a"];
  assert.ok(mark, `позначки нема в space.json: ${JSON.stringify(sj)}`);
  assert.equal(mark.backup, backups[0]);
  assert.deepEqual(mark.roles, ["tracker", "dashboard", "notify"]);
  assert.deepEqual(Object.keys(sj.modules).sort(), ["jira-tracker", "supabase-dashboard", "supabase-teams"]);
  assert.equal(sj.name, "Liga", "чужі ключі space.json (імʼя, колір) збережено");
  assert.equal(sj.color, "space-2");
  /* ⛔ Значення секретів — лише в `secrets.json` (0600): ні в `space.json`, ні в `last.json`, ні в маніфесті. */
  const secretsPath = path.join(deaiHome, "secrets.json");
  assert.equal(statSync(secretsPath).mode & 0o777, 0o600);
  const sec = readJson(secretsPath);
  assert.equal(sec.liga["jira-tracker"].token, JIRA_TOKEN);
  assert.equal(sec.liga["supabase-dashboard"].key, SB_KEY);
  const last = readJson(path.join(deaiHome, "migrations", "last.json"));
  assert.equal(last.status, "done");
  for (const f of [spacePath, path.join(deaiHome, "migrations", "last.json"), path.join(deaiHome, "backups", backups[0], "manifest.json")]) {
    const body = readFileSync(f, "utf8");
    assert.ok(!body.includes(JIRA_TOKEN) && !body.includes(SB_KEY), `секрет у ${path.basename(f)}`);
  }
  S.spacePath = spacePath;
  S.backups = backups;
});

test("2: «Підключення» ЛІГИ — три модулі ввімкнені, по одній картці на роль; решта ролей — вбудовані", async (t) => {
  const { url } = S.first;
  const spaces = (await (await fetch(`${url}/api/spaces`)).json()).spaces;
  const caps = spaces.find((s) => s.id === "liga").capabilities;
  assert.deepEqual({ tracker: caps.tracker, dashboard: caps.dashboard, notify: caps.notify }, MODULES);
  assert.deepEqual({ publish: caps.publish, comments: caps.comments, vcs: caps.vcs }, { publish: "legacy", comments: "legacy", vcs: "legacy" });
  const mods = (await (await fetch(`${url}/api/modules?space=liga`)).json()).modules;
  for (const id of Object.values(MODULES)) {
    const m = mods.find((x) => x.id === id);
    assert.ok(m && m.enabled === true && m.implicit !== true, `${id} мусить бути явно ввімкнений: ${JSON.stringify(m)}`);
  }
  const page = await newPage(t, url);
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="static-publish"]', { timeout: 15000 });
  for (const id of Object.values(MODULES)) {
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
  const sj = readJson(S.spacePath);
  assert.ok(sj.migrations["liga-4d3a"], "позначка лишилась");
  assert.equal(existsSync(path.join(deaiHome, "migrations", ".lock")), true);
  const caps = (await (await fetch(`${S.second.url}/api/spaces`)).json()).spaces.find((s) => s.id === "liga").capabilities;
  assert.equal(caps.tracker, "jira-tracker", "після рестарту ролі лишились явними");
});

guardRealDeai("5: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
