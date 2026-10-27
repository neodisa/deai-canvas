/**
 * Синхронізація з git: вбудований модуль `git-sync` (Deai 0.8.0, етап 4a) — живе проведення: справжній сервер в ізольованій
 * «машині» (тимчасові `HOME`/`DEAI_HOME`), справжній Chromium, справжній git на ЛОКАЛЬНОМУ bare-репо (`file://` у тимчасовій теці).
 * Мережі нема: сервер має `GIT_SSH_COMMAND=false`, браузер не пускає нічого за межі машини (`route` → `abort`, а спроба лишає запис
 * у `outside`), а глобальний git-конфіг людини не читається ні тестом, ні сервером (`GIT_CONFIG_GLOBAL=/dev/null`, `HOME` —
 * тимчасовий). «Колега» — окремий клон із власною особою (`user.name=Колега`), що пушить у той самий origin ПОЗА канвасом.
 *
 * Юніти (`tests/test_git_sync_module.py`, `tests/test_vcs_core.py`, `tests/vcs-client.test.mjs`) доводять кожну ланку окремо; тут —
 * те, що живе тільки в зв'язку: чи смуга справді зникає без ролі, чи «Підключення» вмикає модуль і зона зʼявляється з підписом,
 * чи клік по «Надіслати» кладе коміт у origin, чи «Підтягнути» заводить ітерацію колеги й форк, чи автосинк слухає налаштування,
 * чи форма нової задачі тягне макет колеги, чи ЛІГА лишилась такою, як була.
 *
 * Сценарії: 1 — без модуля (зони нема, статус не питається); 2 — «Підключення»: секція, вмикання, «Працює.» без англійської деталі,
 * зона з підписом «Git»; 3 — перший push (тост, коміт у origin, «Історії» нема для `file://`); 4 — pull після правки колеги
 * (крапка «відстає», «Підтягнути…», ітерація й форк); 5 — автосинк (`autosync-off`, увімкнення на «Підключенні», `changed`);
 * 6 — нова задача з полем «Репозиторій» (рядок про клон, макет колеги в Іт.1, форк) і без нього (звичайний запит); 6b — підказка
 * поля з типового `repo` модуля; 6c — без ролі поля нема; 7 — ЛІГА без змін (підпис «GitLab», `design-canvas: sync …`,
 * «Налаштувати…» → повідомлення про `tasks.json`); 8 — «Налаштувати…» поза ЛІГОЮ веде на «Підключення» з фокусом на картці
 * `git-sync` (перелік просторів уже завантажено); 8b — те саме на свіжозавантаженій сторінці, коли `/api/spaces` ще не питали (вхід сам
 * читає перелік); 9 — майстер: секція
 * «Синхронізація з git» на кроці 2, модуль не вибраний типово, вибраний — запис у `space.json` і зона в новому просторі; 10 — `vcs-busy`:
 * лок дзеркала тримає чужа операція → стан «зайнято», дія каже причину, відкладений повтор знімає стан.
 *
 * Мапа «сценарій → запобіжник», знята мутаційно (одна мутація — один рядок застосунку, файл відновлено побайтно: sha256 до й після
 * збігаються; Python-мутації — з `PYTHONDONTWRITEBYTECODE=1`):
 *   1   — `if (noVcs()) { … return; }` на початку `refreshGitlab` (`app.js`): без нього простір без ролі питає статус (запит у журналі).
 *   1–4, 7, 10 — адреса `/api/vcs-status` у `refreshGitlab` разом з `/api/gitlab-status` у диспетчері сервера (`serve.py`) — вимога плану:
 *        статус не доходить, зона не оживає (1 ще й каже, що псевдонім для Stop-хука мертвий).
 *   2   — гілка `git-sync` у `verdictText` (`connections-model.js`): без неї «Працює.» несе сирий англійський detail модуля.
 *   2, 3, 6, 8 — `labelKey: brand ? … : "gitlab"` у `bar-model.js`: підпис зони завжди «GitLab».
 *   3   — `glNoWeb` у `bar-model.js` («Історія» для `file://`); тема коміту `deai: sync` (`serve.py`); `brandArg` у `ddGitlab` (`shell-bar.js`).
 *   4   — `iteration_is_mine` у `_pull_into_task` (форк чужої ітерації); `src_name` (текст даних «з репозиторію»); `brandArg`.
 *   5   — `autosync` у `_autosync` (`serve.py`): без нього вимкнений автосинк усе одно відправляє.
 *   6   — `taskCreateClones` (`app.js`): `false` — нема рядка про клон, `true` — рядок і для порожнього поля; `entry['vcs'] = vcs` у `_task_new_write`.
 *   6b  — `setAttribute('placeholder', hint)` у `newTaskDialog`.
 *   6c  — `withRepo = hasVcs && !isLegacyVcs` (поле без ролі).
 *   7   — `'GitLab'` для ЛІГИ у `gitlab_status` (`serve.py`); гілка `isLegacyVcs` у `BAR_ACTIONS.glsetup`.
 *   8   — аргумент ролі в `enterConnections('vcs')` (фокус на картці git-sync, а не на першій).
 *   8b  — читання переліку в `enterConnections` (`if (cold) await loadSpaces()`): без нього перший клік на свіжій сторінці мертвий.
 *   9   — `holds(e)` в `initialPick` (`wizard-model.js`): без нього git-sync вибраний типово.
 *   10  — `scheduleGlRetry(key)` у гілці `vcs-busy` (`refreshGitlab`): без нього «зайнято» не знімається.
 *   Не доведено мутацією: рядки секції «Синхронізація з git» на кроці 2 майстра (лише текст заголовка), запис `space.json` майстром, сама
 *   фраза про зайнятість у діалозі сценарію 10 (її дає і гілка `glCache.busy`, і код `vcs-busy` у відповіді дії).
 */
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, postJson, sleep, stop } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга. ⚠️ Не 13600: ту займає `own-modules.test.mjs`, а `tests/live-ports.test.mjs` забороняє дві бази на одну смугу
   й смуги ближчі за 100 портів (`node --test` крутить файли паралельно — збіг дав би випадкове «сервер не піднявся»). */
const PORT_BASE = 13700;
const MOCKUP = (page) => `<!doctype html><html><head><meta charset="utf-8"></head><body><h1>Макет ${page}</h1></body></html>`;
/** Особа ЦІЄЇ машини (`DC_IDENTITY_*`: git-конфіг людини сервер не читає) і особа колеги — різні ключі, тож чуже справді чуже. */
const ME = { name: "Дизайнерка Тест", email: "me@example.invalid" };
const PEER = { name: "Колега", email: "kolega@example.invalid" };
const GL = '#bar [data-dd="gl"]';

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/* ── git: лише локально ────────────────────────────────────────────────────────────────────────────── */

/** Тимчасова тека, яку створив ЦЕЙ файл: прибираємо за ТОЧНИМ шляхом, а не за шаблоном. Видаляємо лише теку, що лежить прямо в
 *  `tmpdir()` і має префікс `dc-live-` (інакше мовчки пропускаємо: помилка в шляху не має знести чужого). Без цього кожен прогін
 *  лишав би на диску по теці на кожну з `git`-домівок, `tasks.json`-теку й фікстуру задачі (≈13 тестів × 4). */
const TMP_ROOT = realpathSync(tmpdir());
function rmOwn(dir) {
  if (!dir) return;
  let real;
  try { real = realpathSync(dir); } catch { return; }                              // вже нема — нічого прибирати
  if (path.dirname(real) !== TMP_ROOT || !path.basename(real).startsWith("dc-live-")) return;
  rmSync(real, { recursive: true, force: true });
}

/** Оточення git тесту: жодного `GIT_*` від батька, без глобального конфігу людини, без підказок і без мережі. */
const gitEnv = (home) => ({
  ...Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith("GIT_"))),
  HOME: home, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1", GIT_TERMINAL_PROMPT: "0", GIT_SSH_COMMAND: "false", LC_ALL: "C",
});
const git = (home, cwd, ...args) => execFileSync("git", args, { cwd, env: gitEnv(home), encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

/** `.canvas-state.json` колеги: заява про авторство (її читає «Підтягнути», а не `git log`). */
const peerState = (task) => JSON.stringify({
  task, source_it: "it1", author: PEER.name, author_key: PEER.email, published: false, publish_url: null, published_at: null,
}, null, 2);

const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
const iterationsOf = (taskDir) => readJson(path.join(taskDir, "iterations.json")).iterations;

/** Дочекатись, поки `fn()` дасть істину (синхронна умова на диску чи в API), або впасти з поясненням. */
async function until(what, fn, ms = 15000) {
  const end = Date.now() + ms;
  for (;;) {
    const v = await fn();
    if (v) return v;
    if (Date.now() > end) throw new Error(`не дочекались: ${what}`);
    await sleep(100);
  }
}

/* ── машина ────────────────────────────────────────────────────────────────────────────────────────── */

/**
 * Сервер + сторінка + bare-origin + колега. `enable`: `"repo"` — `git-sync` ввімкнено через API (як це робить екран «Підключення»)
 * з типовим `repo` = origin; `"norepo"` — ввімкнено без типового репозиторію; `null` — модуль не вмикається. `legacy` — простір ЛІГА
 * (старий `tasks.json`) із двома задачами: `plain` (без `gitlab`) і `mapped` (`gitlab{repo: origin, path}`).
 */
async function boot(t, { enable = "repo", legacy = false, open = true } = {}) {
  const tmp = realpathSync(mkdtempSync(path.join(tmpdir(), "dc-live-git-")));
  const origin = path.join(tmp, "origin.git");
  git(tmp, tmp, "init", "--bare", "--quiet", "--initial-branch=main", origin);
  const originUrl = `file://${origin}`;
  const A = taskFixture({ html: MOCKUP });
  const B = legacy ? taskFixture({ html: MOCKUP }) : null;
  /* Прибирання СВОЇХ тек: теки тесту, фікстури задач і (коли сервер піднявся) домівка й тека `tasks.json` сервера — їх дає
     `startServer` (`home`, `dirname(legacyFile)`), `fixture.mjs` лишається як є. Спершу зупиняємо сервер (зупинка ідемпотентна): під
     ним тека не зникає. Один хук, зареєстрований ДО підняття сервера, щоб і збій `startServer` не лишив теки. */
  let server = null;
  t.after(async () => {
    if (server) await stop(server.child);
    for (const dir of [tmp, A.dir, B?.dir, server?.home, server?.legacyFile && path.dirname(server.legacyFile)]) rmOwn(dir);
  });
  const spaces = legacy
    ? [{ name: "Liga", id: "liga", color: "space-2", legacy: true,
      tasks: { plain: { dir: A.dir, title: "Без маппінгу" }, mapped: { dir: B.dir, title: "З маппінгом" } } }]
    : [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: A.dir, title: "Задача" } } }];
  server = await startServer(null, {
    portBase: PORT_BASE, spaces,
    env: { GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1", GIT_SSH_COMMAND: "false",
      DC_IDENTITY_NAME: ME.name, DC_IDENTITY_EMAIL: ME.email },
  });
  const sp = server.spaces[0];
  if (legacy) {
    const cfg = readJson(server.legacyFile);
    cfg.tasks.mapped.gitlab = { repo: origin, path: "mockup/mapped", branch: "main" };
    writeFileSync(server.legacyFile, JSON.stringify(cfg));
  }
  if (enable) {
    const res = await postJson(server.url, "/api/module-enable", {
      space: sp.id, id: "git-sync", ...(enable === "repo" ? { settings: { repo: originUrl } } : {}),
    });
    assert.equal(res.status, 200, `git-sync не ввімкнувся: ${await res.text()}`);
  }
  const host = new URL(server.url).host;
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const outside = [];
  const requests = [];
  context.on("request", (r) => {
    requests.push(r.url());
    const u = new URL(r.url());
    if (u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol)) outside.push(r.url());
  });
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  if (open) {
    await page.goto(`${server.url}/app/`);
    await page.waitForSelector("#bar .space-chip", { timeout: 15000 });
  }
  const originRefs = () => git(tmp, origin, "for-each-ref", "--format=%(refname)");
  let peers = 0;
  /** Колега пушить у origin ПОЗА канвасом: свіжий клон → файли → коміт від його імені → push. Повертає повний sha. */
  const peerPush = (files, message = "Колега: правка") => {
    const dir = path.join(tmp, `peer-${peers += 1}`);
    if (originRefs()) git(tmp, tmp, "clone", "--quiet", "--branch", "main", originUrl, dir);
    else {                                                   // порожній origin: клон без гілки, перший коміт створить `main`
      git(tmp, tmp, "clone", "--quiet", originUrl, dir);
      git(tmp, dir, "symbolic-ref", "HEAD", "refs/heads/main");
    }
    for (const [rel, text] of Object.entries(files)) {
      mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
      writeFileSync(path.join(dir, rel), text);
    }
    git(tmp, dir, "add", "-A");
    git(tmp, dir, "-c", `user.name=${PEER.name}`, "-c", `user.email=${PEER.email}`, "commit", "--quiet", "-m", message);
    git(tmp, dir, "push", "--quiet", "origin", "main");
    return git(tmp, dir, "rev-parse", "HEAD");
  };
  const originLog = (fmt) => git(tmp, origin, "log", "-1", `--format=${fmt}`, "main");
  const originFile = (rel) => git(tmp, origin, "show", `main:${rel}`);
  const originTree = () => git(tmp, origin, "ls-tree", "-r", "--name-only", "main").split("\n");
  return { ...server, tmp, origin, originUrl, A, B, page, context, outside, requests, errors, spaceId: sp.id, spacePath: sp.path,
    peerPush, originLog, originRefs, originFile, originTree };
}

/** Вхід на «Підключення»: дропдаун простору → «Підключення…» → сторінка з картками. */
async function openConnections(page) {
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length >= 1, null, { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector('.cn-card[data-id="git-sync"]', { timeout: 15000 });
}

/** Дропдаун простору відкрито й закрито: список просторів (`spacesResp`) завантажено — на старті сторінка його не питає. */
async function warmSpaces(page) {
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length >= 1, null, { timeout: 15000 });
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => !document.querySelector(".dd--spaces"), null, { timeout: 15000 });
}

/** Тост ПОКАЗАНО (`.show`) і говорить те саме: застарілий текст схованого тоста не рахується. */
const waitToast = (page, re) => page.waitForFunction((src) => {
  const el = document.getElementById("cv-toast");
  return Boolean(el) && el.classList.contains("show") && new RegExp(src).test(el.textContent ?? "");
}, re.source, { timeout: 15000 });

/** Пункти меню зони синку: `[{act, text, disabled}]` (меню відкривається кліком по кнопці зони). */
async function glMenu(page) {
  await page.click(GL);
  await page.waitForSelector(`${GL} ~ .dd .dd-item`, { timeout: 15000 });
  return page.evaluate(() => [...document.querySelectorAll('#bar [data-dd="gl"] ~ .dd .dd-item')].map((b) => ({
    act: b.dataset.act, text: b.querySelector(".dd-t")?.textContent.trim() ?? "", why: b.querySelector(".dd-why")?.textContent.trim() ?? "",
    disabled: b.disabled,
  })));
}
const glLabel = (page) => page.locator(`${GL} span[class*="lbl"]`).first().textContent();
const glDot = async (page) => (await page.locator(`${GL} .dot`).getAttribute("class")).match(/dot--(\w+)/)[1];

/* ── сценарії ──────────────────────────────────────────────────────────────────────────────────────── */

test("1: без модуля — зони синку в смузі нема, статус не питається, API чесно каже «не налаштовано», автосинк — no-gitlab", async (t) => {
  const s = await boot(t, { enable: null });
  const { page } = s;
  /* Свідок живої смуги: поруч із зоною синку стоїть зона публікації (неявна «Публікація в теку» простору). Без нього «зони нема»
     зеленіло б і на порожній, ще не намальованій смузі. */
  await page.waitForSelector('#bar [data-dd="pub"]', { timeout: 15000 });
  await page.waitForSelector('#bar [data-dd="iter"]', { timeout: 15000 });
  await sleep(800);                                          // перший опит статусу (`refreshGitlab`) відбувся б саме тут
  assert.equal(await page.locator(GL).count(), 0, "зона синку без ролі `vcs`");
  assert.deepEqual(s.requests.filter((u) => /\/api\/(vcs|gitlab)-status/.test(u)), [], "простір без ролі статус синку НЕ питає");
  const sp = (await (await fetch(`${s.url}/api/spaces`)).json()).spaces.find((x) => x.id === "studio");
  assert.equal(sp.capabilities.vcs, null, "capabilities.vcs — ролі нема");

  /* Ті самі адреси, що викликає Stop-хук dev-pipeline: «нема синку» — штатний стан, а не 409/500. */
  assert.deepEqual(await (await fetch(`${s.url}/api/vcs-status`)).json(), { configured: false });
  assert.deepEqual(await (await fetch(`${s.url}/api/gitlab-status`)).json(), { configured: false });
  const auto = await (await postJson(s.url, "/api/autosync", {})).json();
  assert.deepEqual(auto, { ok: true, changed: false, reason: "no-gitlab" });
  assert.equal((await postJson(s.url, "/api/vcs-push", { it: "it1" })).status, 400, "push без ролі — 400");
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("2: «Підключення» — секція «Синхронізація з git», вмикання з repo, «Перевірити» → «Працює.» (без англійської деталі), зона зʼявляється з підписом «Git»", async (t) => {
  const s = await boot(t, { enable: null });
  const { page } = s;
  await openConnections(page);
  const sec = page.locator(".cn-sec", { has: page.locator('.cn-card[data-id="git-sync"]') });
  assert.equal((await sec.locator(".cn-sec-h").textContent()).trim(), "Синхронізація з git");
  assert.match(await sec.locator(".cn-now").textContent(), /Зараз: нікого — макети лише на цьому компʼютері/);
  assert.match(await page.locator('.cn-card[data-id="git-sync"] .cn-badge').getAttribute("class"), /cn-badge--off/);

  await page.click('[data-cn="enable"][data-id="git-sync"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="repo"]');
  for (const key of ["branch", "path", "ssh_key", "host_ip", "autosync"]) {
    assert.equal(await page.locator(`#cn-drawer [data-cn-field="${key}"]`).count(), 1, `поле «${key}» у панелі`);
  }
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="branch"]'), "main");
  assert.equal(await page.inputValue('#cn-drawer [data-cn-field="path"]'), "mockup/{task}");
  await page.fill('#cn-drawer [data-cn-field="repo"]', s.originUrl);
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector('.cn-card[data-id="git-sync"] .cn-badge--ok', { timeout: 15000 });
  assert.equal(await page.locator("#cn-drawer").isHidden(), true, "перевірка гаразд — панель закрилась");
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "роль vcs вільна — питання «Замінити?» не було");
  const mod = readJson(path.join(s.spacePath, "space.json")).modules["git-sync"];
  assert.equal(mod.enabled, true);
  assert.equal(mod.settings.repo, s.originUrl);

  /* Вердикт у панелі: «Працює.» і БІЛЬШЕ нічого (сирий англійський `detail` модуля — «branch main is not on the remote yet…» —
     в зелений рядок не потрапляє). */
  await page.click('[data-cn="configure"][data-id="git-sync"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-dr="check"]');
  await page.click('#cn-drawer [data-cn-dr="check"]');
  await page.waitForSelector("#cn-drawer .cn-res--ok", { timeout: 15000 });
  assert.equal((await page.locator("#cn-drawer .cn-res--ok").textContent()).trim(), "Працює.");
  assert.match(await sec.locator(".cn-now").textContent(), /Зараз: Git/);
  await page.keyboard.press("Escape");
  await page.waitForSelector("#cn-drawer", { state: "hidden" });

  /* Назад до задачі: зона синку з підписом «Git» (не «GitLab»), незапушений макет — крапка «попереду». */
  await page.click('#bar [data-act="back"]');
  await page.waitForSelector(GL, { timeout: 15000 });
  assert.equal((await glLabel(page)).trim(), "Git");
  await page.waitForSelector(`${GL} .dot--warn`, { timeout: 15000 });
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("3: перший push — меню без «Історії» (file://), тост «Надіслано на Git · комміт …», коміт у origin від особи машини, крапка «збігається»", async (t) => {
  const s = await boot(t);
  const { page } = s;
  await page.waitForSelector(`${GL} .dot--warn`, { timeout: 15000 });
  assert.equal((await glLabel(page)).trim(), "Git");
  const menu = await glMenu(page);
  assert.deepEqual(menu.map((m) => m.act), ["glpush"], "відстає — нема, історії для file:// нема (`web: null`), лише «Надіслати»");
  assert.equal(menu[0].text, "Надіслати Іт.1 на Git");
  assert.equal(menu[0].disabled, false);
  assert.equal(s.originRefs(), "", "до кліку origin порожній");

  await page.click('#bar [data-act="glpush"]');
  await waitToast(page, /^Надіслано на Git · комміт [0-9a-f]{4,}$/);
  const sha = (await page.locator("#cv-toast").textContent()).match(/комміт ([0-9a-f]+)/)[1];
  assert.ok(s.originLog("%H").startsWith(sha), "sha з тоста — це комміт origin");
  assert.match(s.originLog("%s"), /^deai: sync mockup\/t1 \(Задача\) · it1$/);
  assert.equal(s.originLog("%an <%ae>"), `${ME.name} <${ME.email}>`, "коміт підписано особою машини");
  const tree = s.originTree();
  for (const f of ["mockup/t1/holovna/index.html", "mockup/t1/poshuk/index.html", "mockup/t1/pages.json", "mockup/t1/.canvas-state.json", "mockup/t1/README.md"]) {
    assert.ok(tree.includes(f), `у репо є ${f}`);
  }
  assert.equal(readJson(path.join(s.A.dir, "iterations.json")).iterations.length, 1, "локально нових ітерацій нема");
  assert.equal(JSON.parse(s.originFile("mockup/t1/.canvas-state.json")).author_key, ME.email, "заява автора в репо — моя");

  /* Після відправки статус перечитано: збігається — зелена крапка, «Надіслати» вимкнене з причиною «Збігається з репозиторієм». */
  await page.waitForSelector(`${GL} .dot--ok`, { timeout: 15000 });
  const after = await glMenu(page);
  assert.equal(after[0].disabled, true);
  assert.equal(after[0].why, "Збігається з репозиторієм");
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("4: pull після правки колеги — крапка «відстає», «Підтягнути…», нова ітерація колеги + форк, макет приїхав", async (t) => {
  const s = await boot(t);
  const { page } = s;
  assert.equal((await (await postJson(s.url, "/api/vcs-push", { it: "it1" })).json()).synced, true, "перший push (як це робить Stop-хук)");
  await page.reload();
  await page.waitForSelector(`${GL} .dot--ok`, { timeout: 15000 });

  s.peerPush({ "mockup/t1/holovna/index.html": MOCKUP("holovna колега"), "mockup/t1/.canvas-state.json": peerState("t1") });
  await page.reload();
  await page.waitForSelector(`${GL} .dot--bad`, { timeout: 15000 });
  const menu = await glMenu(page);
  assert.deepEqual(menu.map((m) => m.act), ["glpull", "glpush"]);
  assert.equal(menu[0].text, "Підтягнути Іт.1 з Git");
  assert.equal(menu[1].disabled, false, "відправка не вимкнена — її гальмує guard сервера, а не смуга");

  await page.click('#bar [data-act="glpull"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /Підтягнути зміни з Git як нову ітерацію\?/);
  await page.click('.cv-ask [data-a="ok"]');
  const its = await until("ітерації після «Підтягнути»", () => { const x = iterationsOf(s.A.dir); return x.length === 3 ? x : null; });
  const [, got, fork] = its;
  assert.equal(got.id, "it2");
  assert.equal(got.from_gitlab, true);
  assert.equal(got.author, PEER.name, "автор — із заяви колеги, а не з git log");
  assert.equal(got.note, "оновлення з репозиторію", "текст даних звичайного простору (поправка 12)");
  assert.equal(fork.id, "it3", "чужу ітерацію одразу форкають");
  assert.equal(fork.from, "it2");
  assert.equal(fork.note, "продовження після оновлення з репозиторію");
  assert.match(readFileSync(path.join(s.A.dir, "iterations", "it2", "holovna", "index.html"), "utf8"), /holovna колега/);
  assert.match(readFileSync(path.join(s.A.dir, "iterations", "it1", "holovna", "index.html"), "utf8"), /Макет holovna<\/h1>/, "моя it1 не змінена");
  /* Смуга відобразила нову ітерацію (перемальовка після «Підтягнути») і більше не «відстає». */
  await page.click('#bar [data-dd="iter"]');
  await page.waitForFunction(() => document.querySelectorAll('#bar .dd-item[data-act="iter"]').length === 3, null, { timeout: 15000 });
  const rows = await page.locator('#bar .dd-item[data-act="iter"] .dd-t').allTextContents();
  assert.deepEqual(rows.map((x) => x.trim().split(" ")[0]).sort(), ["Іт.1", "Іт.2", "Іт.3"], `ітерації в дропдауні: ${rows}`);
  await page.waitForFunction(() => !document.querySelector('#bar [data-dd="gl"] .dot--bad'), null, { timeout: 15000 });
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("5: автосинк — autosync-off за замовчуванням (origin порожній), вмикається на «Підключенні», далі changed:true, повтор — clean", async (t) => {
  const s = await boot(t);
  const { page } = s;
  const off = await (await postJson(s.url, "/api/autosync", {})).json();
  assert.deepEqual(off, { ok: true, changed: false, reason: "autosync-off" });
  assert.equal(s.originRefs(), "", "вимкнений автосинк нічого не відправив");

  await openConnections(page);
  await page.click('[data-cn="configure"][data-id="git-sync"]');
  await page.waitForSelector('#cn-drawer:not([hidden]) [data-cn-field="autosync"]');
  assert.equal(await page.locator('#cn-drawer [data-cn-field="autosync"]').isChecked(), false);
  await page.locator('#cn-drawer [data-cn-field="autosync"]').check();
  await page.click('#cn-drawer [data-cn-dr="submit"]');
  await page.waitForSelector("#cn-drawer", { state: "hidden", timeout: 15000 });
  assert.equal(readJson(path.join(s.spacePath, "space.json")).modules["git-sync"].settings.autosync, true);

  writeFileSync(path.join(s.A.it1, "holovna", "index.html"), MOCKUP("holovna автосинк"));
  const on = await (await postJson(s.url, "/api/autosync", {})).json();
  assert.equal(on.ok, true);
  assert.equal(on.changed, true, `автосинк мусив відправити: ${JSON.stringify(on)}`);
  assert.equal(on.synced, true);
  assert.equal(on.it, "it1");
  assert.match(s.originLog("%s"), /^deai: sync mockup\/t1 \(Задача\) · it1$/);
  assert.match(s.originFile("mockup/t1/holovna/index.html"), /holovna автосинк/);
  const again = await (await postJson(s.url, "/api/autosync", {})).json();
  assert.deepEqual({ changed: again.changed, reason: again.reason }, { changed: false, reason: "clean" });
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

/** «Нова задача» на екрані «Задачі»: форма з полем «Репозиторій». */
async function openTaskForm(page) {
  await page.click('#bar [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  await page.click('#tasks-home .th-head [data-th="newtask"]');
  await page.waitForSelector('form[data-form="task"]');
}

test("6: нова задача — з «Репозиторієм»: рядок «Перший клон…», макет колеги в Іт.1 + форк; з порожнім полем — звичайний запит без ознак клону", async (t) => {
  const s = await boot(t, { enable: "norepo" });
  const { page } = s;
  s.peerPush({ "mockup/t2/index.html": MOCKUP("t2 колега"), "mockup/t2/.canvas-state.json": peerState("t2") });
  /* Запит затримано (справжній сервер відповість після паузи): інакше локальний клон скінчився б швидше за 150 мс, після яких зʼявляється
     рядок-статус, і його було б нічим побачити. Затримка — лише часу, відповідь справжня. */
  await page.route("**/api/task-new", async (route) => { await sleep(1500); await route.continue(); });

  await openTaskForm(page);
  assert.equal(await page.locator("#tf-repo").count(), 1, "поле «Репозиторій» у звичайному просторі з роллю vcs");
  await page.fill("#tf-title", "Від колеги");
  await page.fill("#tf-id", "t2");
  await page.fill("#tf-repo", s.originUrl);
  await page.click('form[data-form="task"] [data-a="ok"]');
  await page.waitForSelector('form[data-form="task"] p.cv-form-note[role="status"]', { timeout: 5000 });
  await page.waitForFunction(() => /Перший клон репозиторію/.test(document.querySelector("p.cv-form-note")?.textContent ?? ""), null, { timeout: 5000 });
  assert.equal((await page.locator('form[data-form="task"] [data-a="ok"]').textContent()).trim(), "Створюю…");
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector("#bar .crumb--task .txt")?.textContent.trim() === "t2", null, { timeout: 15000 });

  const tasks = readJson(path.join(s.spacePath, "tasks.json")).tasks;
  assert.deepEqual(tasks.t2.vcs, { repo: s.originUrl }, "ціль задачі — у tasks.json");
  const its = iterationsOf(tasks.t2.dir);
  assert.deepEqual(its.map((i) => i.id), ["it1", "it2"]);
  assert.equal(its[0].author, PEER.name, "Іт.1 — чужа (заява колеги)");
  assert.equal(its[1].from, "it1");
  assert.equal(its[1].note, "продовження макета з репозиторію", "текст даних звичайного простору (поправка 12)");
  assert.match(readFileSync(path.join(tasks.t2.dir, "iterations", "it1", "index.html"), "utf8"), /t2 колега/, "макет колеги в Іт.1");
  await page.waitForSelector(GL, { timeout: 15000 });
  assert.equal((await glLabel(page)).trim(), "Git");

  /* Порожнє поле: той самий запит, але без `vcs` — звичайний `postForm`, жодного рядка про клон і підпису «Створюю…». */
  await openTaskForm(page);
  await page.fill("#tf-title", "Порожнє поле");
  await page.fill("#tf-id", "t3");
  await page.click('form[data-form="task"] [data-a="ok"]');
  await sleep(600);                                          // понад 150 мс: рядок зʼявився б, якби запит вважався клоном
  assert.equal(await page.locator("p.cv-form-note").count(), 0, "рядка про клон нема");
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 20000 });
  const t3 = readJson(path.join(s.spacePath, "tasks.json")).tasks.t3;
  assert.equal("vcs" in t3, false, "порожнє поле ключа vcs у задачі не лишає");
  assert.deepEqual(iterationsOf(t3.dir).map((i) => i.id), ["it1"]);
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("6b: поле «Репозиторій» — підказка з типового repo модуля", async (t) => {
  const s = await boot(t);
  await openTaskForm(s.page);
  await s.page.waitForFunction((u) => document.querySelector("#tf-repo")?.placeholder === u, s.originUrl, { timeout: 15000 });
  await s.page.click('form[data-form="task"] [data-a="cancel"]');
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

/* Окремий тест, а не другий `boot` у 6b: два сервери разом ризикують сісти на один порт (`startServer` бере `база + hrtime % 100`) —
   тоді дочірній не біндиться, а готовність підтверджує ПЕРШИЙ (де поле є) і `count === 0` червоніє хибно. */
test("6c: без ролі vcs поля «Репозиторій» у формі нової задачі нема", async (t) => {
  const s = await boot(t, { enable: null });
  await openTaskForm(s.page);
  assert.equal(await s.page.locator("#tf-repo").count(), 0, "без ролі vcs форма — як до 4a");
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("7: ЛІГА без змін — підпис «GitLab», «Налаштувати…» для задачі без маппінгу каже про tasks.json (не «Підключення»), push іде зашитим шляхом і дає design-canvas: sync", async (t) => {
  const s = await boot(t, { enable: null, legacy: true });
  const { page } = s;
  assert.equal((await (await fetch(`${s.url}/api/spaces`)).json()).spaces[0].capabilities.vcs, "legacy");
  /* Поточна задача — без `gitlab`: зона є, але репозиторій не налаштований → єдиний пункт «Налаштувати…». */
  await page.waitForSelector(GL, { timeout: 15000 });
  assert.equal((await glLabel(page)).trim(), "GitLab", "у ЛІГА підпис — «GitLab»");
  const off = await glMenu(page);
  assert.deepEqual(off.map((m) => m.act), ["glsetup"]);
  assert.equal(off[0].text, "Налаштувати репозиторій…");
  await page.click('#bar [data-act="glsetup"]');
  await page.waitForSelector(".cv-ask-scrim");
  const msg = await page.locator(".cv-ask-scrim").textContent();
  assert.match(msg, /GitLab налаштовується в tasks\.json/);
  assert.match(msg, /gitlab\.repo/);
  assert.equal(await page.locator(".cn-card").count(), 0, "сторінка «Підключення» не відкрилась");
  assert.equal(await page.locator("#bar .crumb--flat").count(), 0, "крихти «Підключення» нема");
  await page.click('.cv-ask [data-a="ok"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });

  /* Задача з маппінгом: той самий зашитий шлях 0.7.0 (дзеркало — плоска тека `.mirrors`, не `<DEAI_HOME>/cache`). */
  assert.equal((await postJson(s.url, "/api/task-switch", { id: "mapped" })).status, 200);
  await page.reload();
  await page.waitForSelector(`${GL} .dot--warn`, { timeout: 15000 });
  assert.equal((await glLabel(page)).trim(), "GitLab");
  const menu = await glMenu(page);
  assert.equal(menu.find((m) => m.act === "glpush").text, "Надіслати Іт.1 на GitLab");
  await page.click('#bar [data-act="glpush"]');
  await waitToast(page, /^Надіслано на GitLab · комміт [0-9a-f]{4,}$/);
  assert.match(s.originLog("%s"), /^design-canvas: sync mockup\/mapped \(З маппінгом\) · it1$/, "текст даних ЛІГИ лишився «design-canvas»");
  assert.ok(existsSync(path.join(s.home, ".mirrors")) && readdirSync(path.join(s.home, ".mirrors")).length > 0, "дзеркало ЛІГИ — у плоскій теці 0.7.0");
  assert.equal(existsSync(path.join(s.deaiHome, "cache", "liga", "git-sync", "mirrors")), false, "дзеркал модуля в ЛІГА нема");
  await page.waitForSelector(`${GL} .dot--ok`, { timeout: 15000 });
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("8: «Налаштувати…» поза ЛІГОЮ (модуль без repo) веде на «Підключення» з фокусом на картці git-sync, а не на повідомлення про tasks.json", async (t) => {
  const s = await boot(t, { enable: "norepo" });
  const { page } = s;
  await page.waitForSelector(GL, { timeout: 15000 });
  assert.equal((await glLabel(page)).trim(), "Git", "підпис без відомого `label` у звичайному просторі — «Git»");
  assert.equal(await glDot(page), "off");
  /* Теплий шлях: список просторів уже завантажено (дропдаун простору відкрито й закрито) — `enterConnections` бере простір зі
     `spacesResp` без власного читання. Холодний шлях (сторінка списку ще не питала) — 8b. */
  await warmSpaces(page);
  const menu = await glMenu(page);
  assert.deepEqual(menu.map((m) => m.act), ["glsetup"]);
  await page.click('#bar [data-act="glsetup"]');
  await page.waitForSelector('.cn-card[data-id="git-sync"]', { timeout: 15000 });
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "повідомлення про tasks.json не показано");
  await page.waitForFunction(() => document.activeElement?.closest?.(".cn-card")?.dataset?.id === "git-sync", null, { timeout: 15000 });
  assert.match(await page.locator("#bar .crumb--flat").textContent(), /Підключення/);
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

/* Холодний шлях: на старті сторінка `/api/spaces` НЕ питає (його вантажать дропдаун простору, палітра, вхід у «Підключення»), а зона
   синку вже є — простір смуга знає з задачі. Колись `enterConnections` брав простір зі `spacesResp` і мовчки виходив, тож перший клік
   по «Налаштувати…» на свіжозавантаженій сторінці був мертвий (знайдено цим файлом, Task 8; виправлено окремим комітом). Тепер вхід
   сам читає перелік, коли його ще нема. */
test("8b: «Налаштувати…» на свіжозавантаженій сторінці (список просторів ще не питали) веде на «Підключення» з фокусом на картці git-sync", async (t) => {
  const s = await boot(t, { enable: "norepo" });
  const { page } = s;
  await page.waitForSelector(GL, { timeout: 15000 });
  assert.equal(s.requests.filter((u) => new URL(u).pathname === "/api/spaces").length, 0, "свідок: сторінка списку просторів ще не питала");
  const menu = await glMenu(page);
  assert.deepEqual(menu.map((m) => m.act), ["glsetup"]);
  await page.click('#bar [data-act="glsetup"]');
  await page.waitForSelector('.cn-card[data-id="git-sync"]', { timeout: 15000 });
  assert.equal(await page.locator(".cv-ask-scrim").count(), 0, "повідомлення про tasks.json не показано");
  await page.waitForFunction(() => document.activeElement?.closest?.(".cn-card")?.dataset?.id === "git-sync", null, { timeout: 15000 });
  assert.match(await page.locator("#bar .crumb--flat").textContent(), /Підключення/);
  assert.ok(s.requests.some((u) => new URL(u).pathname === "/api/spaces"), "вхід сам прочитав перелік просторів");
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

test("9: майстер нового простору — на кроці 2 секція «Синхронізація з git», модуль типово не вибраний; вибраний — картка з repo, запис у space.json, зона в новому просторі", async (t) => {
  const s = await boot(t, { enable: null });
  const { page } = s;
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1);
  await page.click('.dd--spaces [data-act="spacenew"]');
  await page.waitForSelector('#tasks-home .wz[data-step="1"]');
  await page.fill("#sp-name", "Fresh");
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="2"] input[data-wz-pick][value="git-sync"]', { timeout: 15000 });
  const legends = await page.locator("#tasks-home .wz-sec legend").allTextContents();
  assert.ok(legends.map((x) => x.trim()).includes("Синхронізація з git"), `секції кроку 2: ${legends}`);
  assert.equal(await page.locator('#tasks-home input[data-wz-pick][data-role="vcs"][value="git-sync"]').isChecked(), false, "git-sync типово не вибраний");
  assert.equal(await page.locator('#tasks-home input[data-wz-pick][data-role="vcs"][value=""]').isChecked(), true, "типово — «Без модуля»");

  await page.locator('#tasks-home input[data-wz-pick][value="git-sync"]').check();
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="3"] .wz-card[data-id="git-sync"]', { timeout: 15000 });
  await page.fill('#tasks-home .wz-card[data-id="git-sync"] [data-cn-field="repo"]', s.originUrl);
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForSelector('#tasks-home .wz[data-step="4"]', { timeout: 15000 });
  const created = (await (await fetch(`${s.url}/api/spaces`)).json()).spaces.find((x) => x.id !== "studio");
  const mod = readJson(path.join(created.path, "space.json")).modules["git-sync"];
  assert.equal(mod.enabled, true);
  assert.equal(mod.settings.repo, s.originUrl);
  await page.fill("#tf-title", "Перша");
  await page.click('#tasks-home .wz [data-a="ok"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 20000 });
  await page.waitForSelector(GL, { timeout: 15000 });
  assert.equal((await glLabel(page)).trim(), "Git");
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

/** Тримає `flock` на файлі, поки жива дитина (її вбиваємо ЗА PID); повертається, коли лок узято. */
async function holdLock(lockPath) {
  const child = spawn("python3", ["-c", [
    "import fcntl, sys",
    "fh = open(sys.argv[1], 'a+')",
    "fcntl.flock(fh.fileno(), fcntl.LOCK_EX)",
    "print('locked', flush=True)",
    "sys.stdin.read()",
  ].join("\n"), lockPath], { stdio: ["pipe", "pipe", "inherit"] });
  await new Promise((done, fail) => {
    child.stdout.once("data", done);
    child.once("exit", () => fail(new Error("тримач локу вийшов до того, як узяв лок")));
  });
  return { release: () => child.stdin.end(), pid: child.pid, child };
}

test("10: vcs-busy — лок дзеркала тримає чужа операція: стан «зайнято» (сіра крапка), дія каже про зайнятість, відкладений повтор знімає стан", async (t) => {
  const s = await boot(t);
  const { page } = s;
  assert.equal((await (await postJson(s.url, "/api/vcs-push", { it: "it1" })).json()).synced, true, "перший push створив дзеркало");
  const mirrors = path.join(s.deaiHome, "cache", "studio", "git-sync", "mirrors", "local");
  const lockFile = readdirSync(mirrors).find((n) => n.endsWith("@lock"));
  assert.ok(lockFile, `лок-файл дзеркала є: ${readdirSync(mirrors)}`);
  const lock = await holdLock(path.join(mirrors, lockFile));
  t.after(() => { try { lock.child.kill(); } catch { /* вже вийшов */ } });
  assert.equal((await (await fetch(`${s.url}/api/vcs-status`)).json()).code, "vcs-busy", "свідок: сервер каже vcs-busy, поки лок тримають");

  await page.reload();
  await page.waitForSelector(GL, { timeout: 15000 });
  assert.equal(await glDot(page), "off", "«зайнято» — не помилка й не «збігається»: сіра крапка");
  await glMenu(page);
  await page.click('#bar [data-act="glpush"]');
  await page.waitForSelector(".cv-ask-scrim");
  assert.match(await page.locator(".cv-ask-scrim").textContent(), /Синхронізація вже йде — спробуй за хвилину\./);
  await page.click('.cv-ask [data-a="ok"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });

  /* Лок знято → відкладений повтор (≈5 с) перепитує статус САМ: стан «зайнято» не лишається назавжди. */
  lock.release();
  await page.waitForFunction(() => !document.querySelector('#bar [data-dd="gl"] .dot--off'), null, { timeout: 15000 });
  assert.equal(await glDot(page), "ok", "після повтору — справжній стан: макет збігається");
  assert.deepEqual(s.outside, []);
  assert.deepEqual(s.errors, []);
});

guardRealDeai();
