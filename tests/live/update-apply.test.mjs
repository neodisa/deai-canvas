/**
 * «Оновити й перезапустити» — єдиний живий тест, що справді застосовує оновлення (0.23.0, R-F).
 *
 * ⛔ ЖОДНОГО дотику до справжнього чекаута. Справжнє дерево — лише ДЖЕРЕЛО клону (`git clone` читає його); усе, що пише `git`
 * (`remote set-url`, `push`, `tag`, `commit`, `reset --hard`), іде з `cwd` у викидній теці. Сервер крутиться з викидного клону з тестовим
 * швом `DEAI_UPDATE_TEST_APPLY=1` (без нього ізольований прогін від `apply` і `execv` відмовляє), remote — bare-репо на диску поруч
 * (шлях файлової системи: мережі нема), `DEAI_NO_UPDATE_CHECK=1`. Хост, порт 8765 і живий канвас не задіяні; процес зупиняється за PID.
 *
 * Сценарій: remote має тег `v99.0.0` на коміті, що змінює `package.json` і додає розділ у `CHANGELOG.md`; клон повернуто на коміт
 * назад. `POST /api/update-check` бачить оновлення → пігулка → діалог із «Що нового» → «Оновити» → «Оновлюю…» → сторінка САМА
 * перезавантажилась → `GET /api/update` каже `current: 99.0.0`, `boot` новий, а PID сервера той самий (`execv` заміщує процес).
 */
import "./_env.mjs";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";
import { waitBarReady } from "./_spaces-kit.mjs";

const PORT_BASE = 24100;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const LOCAL = new Set(["127.0.0.1", "localhost"]);
const TARGET = "99.0.0";
const NOTE = "Тестова нотатка оновлення";

/** Git лише з явним `cwd` (викидна тека) і без глобального/системного конфігу: ні справжнього `~/.gitconfig`, ні чужої ідентичності. */
const GIT_ENV = { ...process.env, GIT_CONFIG_GLOBAL: "/dev/null", GIT_CONFIG_NOSYSTEM: "1", GIT_TERMINAL_PROMPT: "0" };
const git = (cwd, ...args) => execFileSync("git", ["-c", "user.name=t", "-c", "user.email=t@example.com", ...args],
  { cwd, env: GIT_ENV, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
/** Лише читання справжнього дерева (`-C`, без запису). */
const readRoot = (...args) => execFileSync("git", ["-C", ROOT, ...args], { env: GIT_ENV, encoding: "utf8" }).trim();

const alive = (pid) => { try { process.kill(pid, 0); return true; } catch { return false; } };

test("apply → рестарт → перезавантаження у викидному клоні", async (t) => {
  const headBefore = readRoot("rev-parse", "HEAD");
  const statusBefore = readRoot("status", "--porcelain", "--untracked-files=no");
  const tmp = realpathSync(mkdtempSync(path.join(tmpdir(), "dc-live-apply-")));
  const work = path.join(tmp, "work");
  const remote = path.join(tmp, "remote.git");
  let child = null;
  let browser = null;
  try {
    // 1. викидні репо: remote (bare) і клон; нова версія лишається ЛИШЕ в remote
    git(tmp, "init", "--bare", "-q", remote);
    git(tmp, "clone", "-q", "--no-hardlinks", ROOT, work);
    /* Джерело може стояти на відʼєднаному HEAD (релізний прогін іде з detached-дерева) — тоді й клон відʼєднаний, і апдейтер чесно
       відмовляє `detached`. Апдейт перевіряємо на гілці, як у людини. */
    git(work, "checkout", "-q", "-B", "main");
    git(work, "remote", "set-url", "origin", remote);
    const current = JSON.parse(readFileSync(path.join(work, "package.json"), "utf8")).version;
    assert.notEqual(current, TARGET, "перевірка недійсна: поточна версія вже цільова");
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main");
    if (!git(work, "tag", "-l", `v${current}`)) git(work, "tag", `v${current}`);
    git(work, "push", "-q", "origin", `v${current}`);

    const pkgPath = path.join(work, "package.json");
    writeFileSync(pkgPath, readFileSync(pkgPath, "utf8").replace(/"version":\s*"[^"]+"/, `"version": "${TARGET}"`));
    const clPath = path.join(work, "CHANGELOG.md");
    const cl = readFileSync(clPath, "utf8");
    const at = cl.indexOf("\n## [");
    assert.ok(at > 0, "перевірка недійсна: у CHANGELOG.md нема жодного розділу");
    writeFileSync(clPath, `${cl.slice(0, at + 1)}\n## [${TARGET}] — 11.11.2026\n\n### Added\n\n- ${NOTE}.\n${cl.slice(at)}`);
    git(work, "commit", "-q", "-m", `release ${TARGET}`, "--", "package.json", "CHANGELOG.md");
    git(work, "tag", `v${TARGET}`);
    git(work, "push", "-q", "origin", "HEAD:refs/heads/main", `v${TARGET}`);
    git(work, "reset", "-q", "--hard", "HEAD~1");                       // викидний клон: тег лишився лише в remote
    assert.equal(JSON.parse(readFileSync(pkgPath, "utf8")).version, current, "перевірка недійсна: клон не відкотився");

    // 2. сервер із коду клону
    const { dir } = taskFixture({ html: () => "<!doctype html><h1>Фікстура</h1>" });
    const server = await startServer(dir, {
      portBase: PORT_BASE, root: work,
      env: { DEAI_UPDATE_REMOTE: remote, DEAI_UPDATE_TEST_APPLY: "1", DEAI_NO_UPDATE_CHECK: "1" },
      spaces: [{ name: "Alpha", id: "alpha", color: "space-2", tasks: { fixture: { dir, title: "Фікстура" } } }],
    });
    child = server.child;
    const pid = child.pid;
    const { url } = server;

    // 3. перевірка бачить оновлення
    const checked = await (await fetch(`${url}/api/update-check`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
    })).json();
    assert.equal(checked.ok, true);
    assert.equal(checked.state, "ok", `перевірка не вдалась: ${JSON.stringify(checked)}`);
    assert.equal(checked.available, true);
    assert.equal(checked.latest, TARGET);
    assert.equal(checked.current, current);
    assert.equal(checked.blocked, null, `оновлення заблоковане: ${checked.blocked}`);
    const bootBefore = checked.boot;

    browser = await chromium.launch();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const hosts = new Set();
    context.on("request", (r) => {
      const u = new URL(r.url());
      if (/^(https?|wss?):$/.test(u.protocol)) hosts.add(u.hostname);
    });
    await context.route((u) => !LOCAL.has(u.hostname) && /^https?:$/.test(u.protocol), (route) => route.abort("blockedbyclient"));
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
    await page.goto(`${url}/app/`);
    await page.waitForSelector("#tabs .upd-pill", { timeout: 20000 });
    assert.match(await page.textContent("#tabs .upd-pill"), new RegExp(`Оновлення ${TARGET.replace(/\./g, "\\.")}`));

    // 4. діалог: версії й «Що нового» з CHANGELOG ВІДДАЛЕНОГО тега
    await page.click("#tabs .upd-pill");
    const form = page.locator(".cv-ask-pop form.up");
    await form.waitFor({ timeout: 15000 });
    assert.match(await form.locator(".up-ver").textContent(), new RegExp(`${current.replace(/\./g, "\\.")}.*${TARGET.replace(/\./g, "\\.")}`));
    await page.waitForFunction((note) => (document.querySelector("[data-up-notes]")?.textContent ?? "").includes(note), NOTE, { timeout: 30000 });
    assert.match(await form.locator("[data-up-notes] .up-sec-h").first().textContent(), new RegExp(`${TARGET.replace(/\./g, "\\.")} · 11\\.11\\.2026`));
    const ok = form.locator('button[data-a="ok"]');
    assert.equal(await ok.isDisabled(), false, "«Оновити» вимкнена, хоча оновлення дозволене");

    // 5. «Оновити й перезапустити» → «Оновлюю…» → сторінка перезавантажилась сама
    await page.evaluate(() => { window.__beforeReload = true; });
    await ok.click();
    await page.waitForFunction(() => /Оновлюю/.test(document.querySelector("[data-up-status]")?.textContent ?? "")
      || !window.__beforeReload, null, { timeout: 30000 });
    await page.waitForFunction(() => !window.__beforeReload, null, { timeout: 90000 });
    await waitBarReady(page, 30000);

    // 6. новий процес із новою версією, той самий PID
    const after = await (await fetch(`${url}/api/update`)).json();
    assert.equal(after.current, TARGET, "сервер не на новій версії");
    assert.notEqual(after.boot, bootBefore, "boot не змінився: це той самий процес Python");
    assert.equal(after.available, false);
    assert.equal(after.restart_failed, false);
    assert.equal(child.exitCode, null, "дочірній процес завершився");
    assert.ok(alive(pid), "PID сервера зник: execv мусить заміщувати процес, а не породжувати новий");
    assert.equal(await page.locator("#tabs .upd-pill").count(), 0, "пігулка лишилась після оновлення");
    assert.equal(JSON.parse(readFileSync(pkgPath, "utf8")).version, TARGET, "робоче дерево клону не оновилось");

    // 7. другий apply — нічого оновлювати
    const again = await fetch(`${url}/api/update-apply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    assert.equal(again.status, 409);
    assert.equal((await again.json()).code, "nothing-to-update");

    assert.deepEqual(errors, [], "помилки сторінки");
    assert.deepEqual([...hosts].filter((h) => !LOCAL.has(h)), [], "сторінка ходила не лише на 127.0.0.1");
  } finally {
    if (browser) await browser.close().catch(() => {});
    if (child && child.pid) { try { process.kill(child.pid, "SIGTERM"); } catch { /* уже зупинено */ } }
    rmSync(tmp, { recursive: true, force: true });
    // справжнє дерево не змінилось
    assert.equal(readRoot("rev-parse", "HEAD"), headBefore, "HEAD справжнього чекаута змінився");
    assert.equal(readRoot("status", "--porcelain", "--untracked-files=no"), statusBefore, "статус справжнього чекаута змінився");
  }
});
