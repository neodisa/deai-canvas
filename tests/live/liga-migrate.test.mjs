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
 *
 * Етап 4d-3c (0.19.0, третій крок `liga-4d3c`: `publish` ЛІГИ — явний `vercel-publish` із `compat: design-canvas`):
 *   1c (три бекапи на старті)      — `ALL_STEPS = (A, B, C)` + `STEP_C` (без них — два бекапи, без позначки c); бекап c знімає space.json ПІСЛЯ b.
 *   2c («Підключення»: шість карток) — `plan(step c)` пише запис без секретів (`shared_state`, `compat`); `capabilities.publish` — id модуля;
 *        роль `publish` має рівно одного ввімкненого виконавця (без дубля «вбудованої»).
 *   5 («Опублікувати» як до міграції) — `compat` запису → `deai_modules.publish_legacy_path` → `publish_module` дає `None` → `Handler._publish` йде
 *        гілкою ЛІГИ: ТІ САМІ `link`/`deploy` argv і ТОЙ САМИЙ текст помилки, що на НЕмігрованій лізі (другий сервер у цьому ж тесті, не
 *        лише текст із коду). Без `compat` (мутація: прибрати з `STEP_C` чи змусити `isLegacyPublish` його ігнорувати) шлях модуля мінтив би інші
 *        проєкти й не дав би рядка `pubpw` у смузі: червоніє саме порівняння й `pubpw`.
 *   6 («Перевірити» на картці)     — закон ізоляції: запис із `shared_state` → вердикт `isolated`, `npx` не викликано (`module_check_verdict`).
 *   ⚠️ ЗБЕРЕЖЕННЯ URL (той самий `pv-…`, ті самі адреса й скоуп, `publish_remote` відсутній) тут довести неможливо: мережі нема, а модуль перевіряє
 *        сторінку лише ПІСЛЯ знайденої адреси (сценарій «deploy без адреси» її свідомо не дає). Це доводить НЕізольований юніт
 *        `RealPublishNonIsolated` (`tests/test_liga_migrate_c.py`), а паритет усього, що бачить людина, — `AfterMigrationParity4d3c`.
 *        Так само перенесення скоупу (`vercel_scope`) між публікаціями доведене лише тим юнітом, а не живим прогоном.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, realpathSync, rmSync, statSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { guardRealDeai, sleep, stop } from "./_spaces-kit.mjs";
import { LIGA_SUPABASE_ORIGINALS, startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs`): тести ЦЬОГО файла йдуть послідовно, тож одна база на всі. */
const PORT_BASE = 23100;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

/* Вигадані значення (репо приватне й знеособлене). */
const JIRA_BASE = "https://jira.example.com";
const JIRA_EMAIL = "alpha@example.com";
const JIRA_TOKEN = "jira_live_token_alpha";
const SB_KEY = LIGA_SUPABASE_ORIGINALS.supabase_key; // оригінал кореня для кроків A–Е
/* 4d-4b: ще три оригінали кореня, які копіює й видаляє крок Е (`liga-4d4b`). */
const PW_ROOT = "pw-live-root";
const SSH_ROOT = "~/.ssh/id_live_root";
const HOST_ROOT = "203.0.113.7";
const MODULES = { tracker: "jira-tracker", dashboard: "supabase-dashboard", notify: "supabase-teams" };
const ALL_MODULES = { ...MODULES, comments: "supabase-comments", vcs: "git-sync", publish: "vercel-publish" }; // + роли 4d-3b і 4d-3c

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => {
  await browser?.close();
  if (S.running) await stop(S.running);
  /* Фальшивий `npx` тестів 5–6: точний шлях `dc-live-npx-*` прямо в tmpdir. */
  if (S.fakeAfter && realpathSync(path.dirname(S.fakeAfter)) === realpathSync(tmpdir()) && path.basename(S.fakeAfter).startsWith("dc-live-npx-")) rmSync(S.fakeAfter, { recursive: true, force: true });
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
  S.taskDir = A.dir;
  S.first = await startServer(null, {
    portBase: PORT_BASE, env: S.env, deaiDir: "state-deai",
    /* 4d-4b: оригінали Supabase/Jira/git/пароля лежать у КОРЕНІ старого файла (немігрована ЛІГА) — їх мігрують кроки A–Е; фікстура сама записів не пише.
       4d-4a: старий запис лише з `profile` (без `track`) — крок D дописує йому `track`; відносний корінь `liga360` адаптер у явні напрямки не бере. */
    legacyExtra: { ...LIGA_SUPABASE_ORIGINALS, jira_base: JIRA_BASE, jira_email: JIRA_EMAIL, jira_token: JIRA_TOKEN,
      gitlab_ssh_key: SSH_ROOT, gitlab_host_ip: HOST_ROOT, preview_password: PW_ROOT, design_work_roots: { liga360: "rel/l360" },
      tasks: { mine1: { dir: A.dir, title: "Моя задача", jira: "DEMO-1", profile: "united" } } },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A.dir, title: "Моя задача", jira: "DEMO-1" } } }],
  });
  S.running = S.first.child;
  const { deaiHome } = S.first;
  /* Міграція йде після відкриття порту, але до обслуговування запитів (`serve.serve_main`): коли сервер відповів, усе вже на диску. */
  const all = readdirSync(path.join(deaiHome, "backups")).sort();
  const backups = all.filter((n) => /-liga-4d3a$/.test(n));
  assert.equal(backups.length, 1, `рівно один бекап кроку 4d-3a: ${JSON.stringify(backups)}`);
  /* 4d-3b: два незалежні кроки на одному старті — два датовані бекапи з суфіксом СВОГО кроку (раніше був один). */
  const backupsB = all.filter((n) => /-liga-4d3b$/.test(n));
  assert.equal(backupsB.length, 1, `рівно один бекап кроку 4d-3b: ${JSON.stringify(backupsB)}`);
  /* 4d-3c: третій незалежний крок — свій датований бекап із суфіксом `-liga-4d3c`. */
  const backupsC = all.filter((n) => /-liga-4d3c$/.test(n));
  assert.equal(backupsC.length, 1, `рівно один бекап кроку 4d-3c: ${JSON.stringify(backupsC)}`);
  /* 4d-4a: четвертий незалежний крок — свій датований бекап із суфіксом `-liga-4d4a`. */
  const backupsD = all.filter((n) => /-liga-4d4a$/.test(n));
  assert.equal(backupsD.length, 1, `рівно один бекап кроку 4d-4a: ${JSON.stringify(backupsD)}`);
  /* 4d-4b: п'ятий незалежний крок — свій датований бекап із суфіксом `-liga-4d4b`. */
  const backupsE = all.filter((n) => /-liga-4d4b$/.test(n));
  assert.equal(backupsE.length, 1, `рівно один бекап кроку 4d-4b: ${JSON.stringify(backupsE)}`);
  assert.equal(all.length, 5, `рівно п'ять бекапів на старті: ${JSON.stringify(all)}`);
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
  /* Третій крок (4d-3c): `publish` → `vercel-publish`; бекап c знімає space.json ПІСЛЯ записів a і b (позначки обох уже в ньому). */
  const markC = sj.migrations?.["liga-4d3c"];
  assert.ok(markC, `позначки 4d-3c нема: ${JSON.stringify(sj.migrations)}`);
  assert.equal(markC.backup, backupsC[0]);
  assert.deepEqual(markC.roles, ["publish"]);
  const spaceInC = readJson(path.join(deaiHome, "backups", backupsC[0], "space.json"));
  assert.ok(spaceInC.migrations["liga-4d3a"] && spaceInC.migrations["liga-4d3b"], "бекап c бачить позначки a і b");
  assert.equal(spaceInC.migrations["liga-4d3c"], undefined, "бекап c знятий ДО запису власної позначки");
  assert.equal(readJson(path.join(deaiHome, "backups", backupsC[0], "manifest.json")).migration, "liga-4d3c");
  assert.equal(statSync(path.join(deaiHome, "backups", backupsC[0])).mode & 0o777, 0o700);
  /* Четвертий крок (4d-4a): без ролей; напрямки вже явні (крок a), тож пише лише `track = profile` у записи; бекап d знімає space.json ПІСЛЯ c і
     лічить у собі `tasks.json` ДО запису (`tasks.json.bak` лежить поруч із файлом задач). */
  const markD = sj.migrations?.["liga-4d4a"];
  assert.ok(markD, `позначки 4d-4a нема: ${JSON.stringify(sj.migrations)}`);
  assert.equal(markD.backup, backupsD[0]);
  assert.deepEqual([markD.roles, markD.tracks, markD.records, markD.notes], [[], true, 1, ["root-rebased:liga360"]],
    "напрямки адаптера записано явними (їх пише саме цей крок), `track = profile` у записі, відносний корінь `liga360` — нотатка без шляху");
  assert.equal(readJson(path.join(deaiHome, "backups", backupsD[0], "manifest.json")).migration, "liga-4d4a");
  assert.equal(statSync(path.join(deaiHome, "backups", backupsD[0])).mode & 0o777, 0o700);
  assert.ok(readJson(path.join(deaiHome, "backups", backupsD[0], "space.json")).migrations["liga-4d3c"], "бекап d бачить позначку c");
  assert.equal(readJson(path.join(deaiHome, "backups", backupsD[0], "tasks.json")).tasks.mine1.track, undefined, "бекап d — tasks.json ДО запису");
  const migrated = readJson(S.first.legacyFile).tasks.mine1;
  assert.deepEqual([migrated.track, migrated.profile], ["united", "united"], "запис дістав `track` (= `profile`), `profile` лишився");
  /* П'ятий крок (4d-4b): копії в записи, видалення з кореня, `tasks.json.bak` — байти ДО видалення (тут уже після кроку D: `track` є, оригінали ще є). */
  const markE = sj.migrations?.["liga-4d4b"];
  assert.ok(markE, `позначки 4d-4b нема: ${JSON.stringify(sj.migrations)}`);
  assert.equal(markE.backup, backupsE[0]);
  assert.deepEqual(markE.roles, []);
  for (const k of ["gitlab_ssh_key", "gitlab_host_ip", "preview_password"]) assert.ok(markE.copied.includes(k), `крок Е не скопіював ${k}: ${JSON.stringify(markE)}`);
  assert.equal(readJson(path.join(deaiHome, "backups", backupsE[0], "manifest.json")).migration, "liga-4d4b");
  assert.equal(statSync(path.join(deaiHome, "backups", backupsE[0])).mode & 0o777, 0o700);
  assert.ok(readJson(path.join(deaiHome, "backups", backupsE[0], "space.json")).migrations["liga-4d4a"], "бекап e бачить позначку d");
  assert.equal(readJson(path.join(deaiHome, "backups", backupsE[0], "tasks.json")).preview_password, PW_ROOT, "бекап e — tasks.json ДО видалення");
  const rootNow = readJson(S.first.legacyFile);
  for (const k of ["supabase_url", "supabase_key", "jira_base", "jira_email", "jira_token", "preview_password"]) assert.equal(k in rootNow, false, `корінь ще несе ${k}`);
  assert.equal(rootNow.tasks.mine1.title, "Моя задача", "записи задач крок Е не чіпав");
  assert.deepEqual(markE.removed.slice().sort(), Object.keys(readJson(path.join(deaiHome, "backups", backupsE[0], "tasks.json")))
    .filter((k) => !(k in rootNow)).sort(), "`removed` позначки = ключі, яких у корені справді нема");
  const gitSettings = sj.modules["git-sync"].settings;
  assert.deepEqual([gitSettings.ssh_key, gitSettings.host_ip, gitSettings.compat], [SSH_ROOT, HOST_ROOT, "design-canvas"], "ключ і IP скопійовано в запис git-sync");
  assert.equal(readJson(`${S.first.legacyFile}.bak`).preview_password, PW_ROOT, "`tasks.json.bak` — корінь ДО видалення");
  assert.deepEqual(sj.tracks.map((x) => x.id), ["united", "liga360", "seo"], "явні напрямки ЛІГИ (крок a)");
  /* Запис без секретів і з `compat`: саме він утримує шлях ЛІГИ (`publish_legacy_path`). */
  assert.deepEqual(sj.modules["vercel-publish"], { enabled: true, shared_state: true, settings: { auth: "cli", team: "", compat: "design-canvas" } });
  assert.deepEqual(Object.keys(sj.modules).sort(), ["git-sync", "jira-tracker", "supabase-comments", "supabase-dashboard", "supabase-teams", "vercel-publish"]);
  assert.equal(sj.name, "Liga", "чужі ключі space.json (імʼя, колір) збережено");
  assert.equal(sj.color, "space-2");
  /* ⛔ Значення секретів — лише в `secrets.json` (0600): ні в `space.json`, ні в `last.json`, ні в маніфесті. */
  const secretsPath = path.join(deaiHome, "secrets.json");
  assert.equal(statSync(secretsPath).mode & 0o777, 0o600);
  const sec = readJson(secretsPath);
  assert.equal(sec.liga["jira-tracker"].token, JIRA_TOKEN);
  assert.equal(sec.liga["supabase-dashboard"].key, SB_KEY);
  assert.equal(sec.liga["supabase-comments"].key, SB_KEY, "ключ Supabase для коментарів — теж лише в secrets.json");
  assert.equal(sec.liga["vercel-publish"].password, PW_ROOT, "пароль превʼю з кореня — секрет `password` запису vercel-publish (крок Е)");
  const last = readJson(path.join(deaiHome, "migrations", "last.json"));
  assert.equal(last.status, "done");
  assert.deepEqual(Object.keys(last.steps).sort(), ["liga-4d3a", "liga-4d3b", "liga-4d3c", "liga-4d4a", "liga-4d4b"], "last.json тримає звіт кожного кроку");
  for (const f of [spacePath, path.join(deaiHome, "migrations", "last.json"), path.join(deaiHome, "backups", backups[0], "manifest.json"),
    path.join(deaiHome, "backups", backupsB[0], "manifest.json"), path.join(deaiHome, "backups", backupsC[0], "manifest.json"),
    path.join(deaiHome, "backups", backupsD[0], "manifest.json"), path.join(deaiHome, "backups", backupsE[0], "manifest.json")]) {
    const body = readFileSync(f, "utf8");
    assert.ok(!body.includes(JIRA_TOKEN) && !body.includes(SB_KEY) && !body.includes(PW_ROOT), `секрет у ${path.basename(f)}`);
  }
  S.spacePath = spacePath;
  S.backups = backups;
  S.backupsB = backupsB;
  S.backupsC = backupsC;
  S.backupsD = backupsD;
  S.backupsE = backupsE;
  S.seams = { DC_TRACKER_FAKE: tracker, DC_TEAM_FAKE: team };
  /* Дзеркала ЛІГИ — плоска тека 0.7.0; міграція її не чіпає (сам синк — тест 3c), а дзеркал модуля під `<DEAI_HOME>/cache` не буває. */
  assert.deepEqual(mirrorDirs(), S.mirrorsListBefore, "міграція не додала дзеркал");
  assert.equal(git(S.gitDir, S.mirror, "rev-parse", "HEAD"), S.mirrorHeadBefore, "міграція не чіпала дзеркала");
  assert.equal(existsSync(path.join(deaiHome, "cache", "liga", "git-sync", "mirrors")), false);
});

test("2: «Підключення» ЛІГИ — шість модулів ввімкнені (три кроку a, comments і vcs кроку b, publish кроку c), по одній картці на роль", async (t) => {
  const { url } = S.first;
  const spaces = (await (await fetch(`${url}/api/spaces`)).json()).spaces;
  const caps = spaces.find((s) => s.id === "liga").capabilities;
  assert.deepEqual({ tracker: caps.tracker, dashboard: caps.dashboard, notify: caps.notify }, MODULES);
  /* 4d-3b: `comments` і `vcs` — явні модулі; 4d-3c: `publish` теж (id модуля, а не `legacy`; шлях ЛІГИ тримає `compat`, див. тест 5). */
  assert.deepEqual({ publish: caps.publish, comments: caps.comments, vcs: caps.vcs }, { publish: "vercel-publish", comments: "supabase-comments", vcs: "git-sync" });
  const mods = (await (await fetch(`${url}/api/modules?space=liga`)).json()).modules;
  for (const id of Object.values(ALL_MODULES)) {
    const m = mods.find((x) => x.id === id);
    assert.ok(m && m.enabled === true && m.implicit !== true, `${id} мусить бути явно ввімкнений: ${JSON.stringify(m)}`);
  }
  /* Роль `publish` має рівно одного ввімкненого виконавця — без дубля «вбудованої» публікації поряд із `vercel-publish`. */
  assert.deepEqual(mods.filter((m) => m.enabled && (m.roles ?? []).includes("publish")).map((m) => m.id), ["vercel-publish"],
    `роль publish: ${JSON.stringify(mods.filter((m) => (m.roles ?? []).includes("publish")).map((m) => [m.id, m.enabled, m.implicit]))}`);
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
  assert.deepEqual(model, { hasVcs: true, isLegacyVcs: true, compat: { comments: "comment-layer", vcs: "design-canvas", publish: "design-canvas" } },
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
  S.sealed = before;                                            // до тестів 5–6: нічого з цього не мусить змінитись і після публікації
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
  assert.equal(backupsBefore.length, 5, "лишились рівно п'ять бекапів (a, b, c, d і e), нового нема");
  assert.deepEqual(backupsBefore.map((n) => n.replace(/^.*-liga-/, "liga-")).sort(), ["liga-4d3a", "liga-4d3b", "liga-4d3c", "liga-4d4a", "liga-4d4b"]);
  assert.deepEqual([S.backups[0], S.backupsB[0], S.backupsC[0], S.backupsD[0], S.backupsE[0]].sort(), backupsBefore);
  const sj = readJson(S.spacePath);
  assert.ok(sj.migrations["liga-4d3a"], "позначка лишилась");
  assert.ok(sj.migrations["liga-4d3b"], "позначка 4d-3b лишилась");
  assert.ok(sj.migrations["liga-4d3c"], "позначка 4d-3c лишилась");
  assert.ok(sj.migrations["liga-4d4a"], "позначка 4d-4a лишилась");
  assert.ok(sj.migrations["liga-4d4b"], "позначка 4d-4b лишилась");
  /* Дзеркала: старт нічого в них не пише (HEAD і перелік після push 3c ті самі), дзеркал модуля під `<DEAI_HOME>/cache` нема. */
  assert.deepEqual(mirrorDirs(), S.mirrorsListBefore, "другий старт змінив базу дзеркал");
  assert.equal(git(S.gitDir, S.mirror, "rev-parse", "HEAD"), S.mirrorHeadAfter, "другий старт зрушив дзеркало");
  assert.equal(existsSync(path.join(deaiHome, "cache", "liga", "git-sync", "mirrors")), false, "дзеркал git-sync у <DEAI_HOME>/cache нема");
  assert.equal(existsSync(path.join(deaiHome, "migrations", ".lock")), true);
  const caps = (await (await fetch(`${S.second.url}/api/spaces`)).json()).spaces.find((s) => s.id === "liga").capabilities;
  assert.equal(caps.tracker, "jira-tracker", "після рестарту ролі лишились явними");
  assert.deepEqual({ comments: caps.comments, vcs: caps.vcs, publish: caps.publish },
    { comments: "supabase-comments", vcs: "git-sync", publish: "vercel-publish" }, "ролі кроків b і c теж лишились явними");
});

/* ── 4d-3c: публікація мігрованої ЛІГИ — як до міграції (стиль `legacy-publish-cli.test.mjs`: фальшивий `npx` першим у PATH) ── */
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const TESTS = path.join(ROOT, "tests");

/** Текст ЛІГИ для `vercel-no-url` — зі справжнього `app/serve.py` (`_LEGACY_NO_URL`), а не з памʼяті. */
function legacyNoUrl() {
  const m = readFileSync(path.join(ROOT, "app", "serve.py"), "utf8").match(/_LEGACY_NO_URL = \(\s*'([^']*)'\s*'([^']*)'\s*\)/);
  assert.ok(m, "не знайшов _LEGACY_NO_URL у app/serve.py — змінився формат константи");
  return m[1] + m[2];
}

/** Фальшивий `npx`: `deploy` із кодом 0 БЕЗ адреси (єдиний «успішний» деплой, що не йде в мережу), `link` — успішний. */
function makeFakeNpx() {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-live-npx-"));
  const made = spawnSync("python3", ["-B", "-c",
    "import sys; sys.path.insert(0, sys.argv[1]); import fake_npx; "
    + "fake_npx.make(sys.argv[2], {'deploy': {'code': 0, 'stdout': 'Done, no address here'}, 'link': {'code': 0}})",
    TESTS, dir], { encoding: "utf8" });
  assert.equal(made.status, 0, made.stderr);
  return dir;
}

/** Журнал фальшивого `npx`: `[{argv, cwd}]` — через сам `tests/fake_npx.py` (один формат на Python і Node). */
function npxCalls(dir) {
  const r = spawnSync("python3", ["-B", "-c",
    "import sys, json; sys.path.insert(0, sys.argv[1]); import fake_npx; print(json.dumps(fake_npx.calls(sys.argv[2])))",
    TESTS, dir], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}

/** Порівнянний вигляд журналу: номер проєкту `pv-<8 цифр>` мінтиться випадково, `cwd` — відносно теки задачі. */
const normCalls = (calls, taskDir) => calls.map((c) => ({
  argv: c.argv.map((a) => a.replace(/pv-\d{8}/g, "pv-<id>")),
  cwd: path.relative(realpathSync(taskDir), realpathSync(c.cwd)),
}));

/** Одна «людська» публікація: рядок `pubpw` у смузі → клік «Опублікувати» → відповідь сервера й текст у вікні → argv і привʼязка проєкту. */
async function publishAsPerson(t, server, fakeDir, taskDir) {
  const page = await newPage(t, server.url);
  await page.waitForSelector('#bar [data-act="publish"]', { timeout: 15000 });
  await page.click('#bar [data-dd="pub"]');
  const pw = page.locator('#bar [data-act="pubpw"]');
  await pw.waitFor({ timeout: 15000 });
  const pubpw = await pw.innerText();
  await page.keyboard.press("Escape");
  const respP = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/publish" && r.request().method() === "POST");
  await page.click('#bar [data-act="publish"]');
  const answer = await (await respP).json();
  const box = page.locator(".cv-ask");
  await box.waitFor({ timeout: 30000 });
  const shown = await box.textContent();
  const cfg = readJson(server.legacyFile);
  assert.deepEqual(page.errors, []);
  assert.deepEqual(page.outside, [], "запити назовні");
  /* Тека задачі в тексті вікна різна на двох машинах — порівнюємо з маркером (текст помилки ЛІГИ лишається побайтно). */
  const noDir = (s) => s.split(realpathSync(taskDir)).join("<task>").split(taskDir).join("<task>");
  return { pubpw, answer: { ...answer, deploy_error: noDir(String(answer.deploy_error ?? "")) }, shown: noDir(shown), calls: normCalls(npxCalls(fakeDir), taskDir), project: cfg.tasks.mine1.vercel_project,
    caps: (await (await fetch(`${server.url}/api/spaces`)).json()).spaces.find((s) => s.id === "liga").capabilities.publish };
}

test("5: «Опублікувати» мігрованої ЛІГИ — link/deploy argv і текст помилки ЛІГИ, рядок «Пароль превʼю» з секрету; немігрована ЛІГА не публікує зовсім", async (t) => {
  const want = legacyNoUrl();
  /* ── ДО міграції: окремий сервер на власній машині (без `DC_MIGRATE_LIGA` ізольований прогін не мігрує). 4d-4b: немігрована ЛІГА має ВСІ шість
     ролей вимкнених, тож публікації нема зовсім (до 0.21 її вів `Implicit`): ні кнопки, ні `POST /api/publish`. ── */
  const A2 = taskFixture({ html: MOCKUP });
  t.after(() => rmSync(A2.dir, { recursive: true, force: true }));
  const unmigrated = await startServer(null, {
    portBase: PORT_BASE, deaiDir: "state-deai", legacyExtra: { ...LIGA_SUPABASE_ORIGINALS, jira_base: JIRA_BASE, jira_email: JIRA_EMAIL, jira_token: JIRA_TOKEN },
    env: { ...S.seams, DC_TEAMS_FAKE: "", GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1" },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A2.dir, title: "Моя задача", jira: "DEMO-1" } } }],
  });
  try {
    const caps = (await (await fetch(`${unmigrated.url}/api/spaces`)).json()).spaces.find((s) => s.id === "liga").capabilities;
    assert.equal(caps.publish, null, "еталон: немігрована ЛІГА без ролі publish");
    const res = await fetch(`${unmigrated.url}/api/publish`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ build_only: true }) });
    assert.equal(res.status, 409);
    assert.equal((await res.json()).code, "no-publish-module");
  } finally {
    await stop(unmigrated.child);
    rmSync(unmigrated.home, { recursive: true, force: true });
    /* Тека конфігу `dc-live-cfg-*` (старий `tasks.json` цього сервера) — за ТОЧНИМ шляхом: прямо в tmpdir і з цим префіксом. */
    const cfgDir = path.dirname(unmigrated.tasksFile);
    if (path.dirname(realpathSync(cfgDir)) === realpathSync(tmpdir()) && path.basename(cfgDir).startsWith("dc-live-cfg-")) rmSync(cfgDir, { recursive: true, force: true });
  }

  /* ── ПІСЛЯ міграції: той самий диск, що й тести 1–4 (машина S.first), сервер перезапущено з фальшивим npx. ── */
  await stop(S.running);
  const fakeAfter = makeFakeNpx();                              // живе до кінця файла (тест 6 читає його журнал); прибирає `test.after`
  S.fakeAfter = fakeAfter;                                      // одразу: падіння нижче не лишає теку `dc-live-npx-*` (прибирає `test.after`)
  S.third = await startServer(null, { portBase: PORT_BASE, env: { ...S.env, PATH: `${fakeAfter}:${process.env.PATH}` }, machine: S.first });
  S.running = S.third.child;
  const after = await publishAsPerson(t, S.third, fakeAfter, S.taskDir);
  assert.equal(after.caps, "vercel-publish", "після міграції публікацію веде явний модуль (але шлях — ЛІГИ)");

  /* Те саме, що бачила людина до міграції. Мутація «без compat»: шлях модуля — інші argv (мінтить проєкт інакше), інший текст і
     немає рядка `pubpw` (`isLegacyPublish` хибне → `pwView` без пароля) — червоніє тут. Пароль — з СЕКРЕТУ (крок Е скопіював його з кореня). */
  assert.match(after.pubpw, new RegExp(PW_ROOT), `рядок «Пароль превʼю» мусить показувати пароль із секрету: ${after.pubpw}`);
  assert.equal(after.answer.deploy_error, want, "текст помилки не той, що в ЛІГИ");
  assert.ok(after.shown.includes(want), `у вікні нема тексту ЛІГИ: ${after.shown}`);
  assert.equal(after.answer.url, undefined, "адреси нема — і в відповіді її бути не може");
  const sub = (c) => c.argv[2];
  const link = after.calls.find((c) => sub(c) === "link");
  const deploy = after.calls.find((c) => sub(c) === "deploy");
  assert.ok(link && deploy, `нема link/deploy: ${JSON.stringify(after.calls)}`);
  assert.deepEqual(link.argv.slice(0, 2), ["--yes", "vercel"]);
  assert.equal(link.argv[link.argv.indexOf("--project") + 1], "pv-<id>", `link без --project pv-<8 цифр>: ${link.argv.join(" ")}`);
  for (const flag of ["--prod", "--yes"]) assert.ok(deploy.argv.includes(flag), `deploy без ${flag}: ${deploy.argv.join(" ")}`);
  assert.equal(link.cwd, "publish");
  assert.equal(deploy.cwd, "publish");
  assert.deepEqual(after.calls.filter((c) => ["list", "remove", "rm"].includes(sub(c))), [], "адреси нема → чистки старих деплоїв бути не повинно");
  assert.match(after.project ?? "", /^pv-\d{8}$/, "vercel_project не змінтився в tasks.json");
});

test("6: «Перевірити» на картці vercel-publish — вердикт isolated, npx не викликано; після публікації нічого з печаті міграції не змінилось", async (t) => {
  const callsBefore = npxCalls(S.fakeAfter).length;
  assert.ok(callsBefore >= 2, `свідок: тест 5 мусив лишити виклики link/deploy (${callsBefore})`);
  const page = await newPage(t, S.third.url);
  await page.click('#bar [data-dd="space"]');                   // «Підключення» живуть у випадайці простору (як у тесті 2)
  await page.waitForSelector('.dd--spaces .dd-item[data-act="space"]', { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="vercel-publish"]', { timeout: 15000 });
  const respP = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/module-check" && r.request().method() === "POST");
  await page.click('.cn-card[data-id="vercel-publish"] [data-cn="check"]');
  const answer = await (await respP).json();
  assert.equal(answer.check?.ok, false, JSON.stringify(answer));
  assert.equal(answer.check?.error, "isolated", `вердикт мусить бути isolated: ${JSON.stringify(answer.check)}`);
  assert.equal(npxCalls(S.fakeAfter).length, callsBefore, "«Перевірити» викликало npx (мережа з процесу сервера)");
  assert.deepEqual(page.errors, []);
  assert.deepEqual(page.outside, [], "запити назовні");
  /* Старт і публікація на третьому сервері нічого не дописали в печать міграції (space.json, secrets.json, last.json, spaces.json) і не додали бекапів. */
  for (const b of S.sealed) {
    assert.equal(statSync(b.f).mtimeMs, b.mtime, `mtime змінився: ${path.basename(b.f)}`);
    assert.equal(sha(b.f), b.sha, `вміст змінився: ${path.basename(b.f)}`);
  }
  assert.equal(readdirSync(path.join(S.first.deaiHome, "backups")).length, 5, "зʼявився новий бекап (їх рівно п'ять: a, b, c, d, e)");
});

test("6b: немігрована ЛІГА — `status` називає всі шість вимкнених ролей і команду виправлення; `unhold` знімає утримання кроку", async (t) => {
  /* Окрема машина без `DC_MIGRATE_LIGA`: старт нічого не мігрує, ролі вимкнені. CLI читає ТОЙ САМИЙ тимчасовий дім (`DEAI_HOME`), справжній `~/.deai` — ні. */
  const A3 = taskFixture({ html: MOCKUP });
  t.after(() => rmSync(A3.dir, { recursive: true, force: true }));
  const server = await startServer(null, {
    portBase: PORT_BASE, deaiDir: "state-deai", legacyExtra: { ...LIGA_SUPABASE_ORIGINALS, jira_base: JIRA_BASE, jira_email: JIRA_EMAIL, jira_token: JIRA_TOKEN },
    env: { GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1" },
    spaces: [{ name: "Liga", id: "liga", color: "space-2", legacy: true, tasks: { mine1: { dir: A3.dir, title: "Моя задача" } } }],
  });
  t.after(() => rmSync(server.home, { recursive: true, force: true }));
  t.after(() => rmSync(path.dirname(server.tasksFile), { recursive: true, force: true }));
  await stop(server.child);
  const cli = (...args) => spawnSync("python3", ["-B", path.join(ROOT, "bin", "migrate_liga.py"), ...args], {
    encoding: "utf8", cwd: ROOT,
    env: { ...process.env, HOME: server.home, DEAI_HOME: server.deaiHome, DC_TASKS_FILE: server.legacyFile },
  });
  const status = cli("status");
  assert.equal(status.status, 0, status.stderr);
  assert.match(status.stdout, /Ролі ЛІГИ/);
  for (const role of ["publish", "comments", "vcs", "dashboard", "tracker", "notify"]) assert.match(status.stdout, new RegExp(`${role} \\(`), `status не називає роль ${role}`);
  assert.doesNotMatch(status.stdout, new RegExp(`${SB_KEY}|${JIRA_TOKEN}`), "значення секретів у виводі");
  /* `unhold` — лише для утриманого кроку: на неутриманому — відмова з поясненням, нічого не пишеться. */
  const refused = cli("unhold", "liga-4d4b");
  assert.equal(refused.status, 1);
  assert.match(refused.stdout, /refuse-not-held|не утримано|refuse-/);
  assert.equal(existsSync(path.join(server.spaces[0].path, "space.json")), true);
  assert.equal(readJson(path.join(server.spaces[0].path, "space.json")).migrations, undefined, "відмова unhold нічого не записала");
});

guardRealDeai("7: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
