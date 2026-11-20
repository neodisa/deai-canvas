/**
 * Інспектор лише для перегляду в ОПУБЛІКОВАНОМУ превʼю (0.32.0, етап Ж, Task 4) — живе проведення на ЗІБРАНОМУ `publish/`, який
 * лежить під статичним сервером (так він лежить у Vercel: один origin, без сервера інструмента).
 *
 * Збірка — справжня: сервер у тимчасовій «машині», простір з модулем `css-tokens` (справжній, на CSS у тимчасовій теці) і,
 * для перевірки взаємовиключності, з `memo-comments` (фікстура `tests/fixtures/modules/memo-comments/`, сервіс `memo` лише на
 * 127.0.0.1); `POST /api/publish`. Мережі нема: `context.route` рве все, що не локальне. Жоден запит не сміє піти на `/api/…`.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо його прибрати»:
 *   1 кнопка смуги і I           — `live && insp?.has()` у `islandTools()` + `shellKey` (`ext-inspect.js`). Прибери — кнопки нема, I мовчить.
 *   2 значення й токен зі знімка — `tok=…` у тезі (`preview_inspector_tag`) і його читання в `inspector.js`; `ds-snapshot.json` у збірці.
 *                              Прибери будь-що — чип зникає, а вирок `token` стає `unknown`; `--bf-ink` не стає `off-ds`.
 *   3 панель лише для перегляду — `readonly: true` у `paint()` (`ext-inspect.js`) → `panelHTML(…, { readonly })`. Прибери — поля вводу, підвал тюнера.
 *   4 Alt, Esc, ← →            — слухачі оверлея в рамці й `shellKey` в оболонці; `setAlt`/`yieldEsc`/`onChange` проводяться на кожен `load` рамки.
 *   5 взаємовиключність        — `onOn` (інспектор → `cmt.setOpen(false)`) і `onOpen` (коментарі → `insp.setOn(false)`) у `ext-shell.js`.
 *   6 чистий перегляд          — `closeSidePanels()` у `toggleClean` і `canUse: () => !clean`.
 *   7 жодного /api/            — тег без `sp` без `tok`; знімок — файл збірки; оверлей не питає сервер.
 *   8 без знімка — без вироків — `preview_tokens_snapshot` → `None`: файла нема, тег без `sp`/`tok`; оверлей показує значення й імена `var()`
 *                              зі сторінки (як Deai без ДС), але нічого не називає «повз ДС» — звіряти нема з чим.
 *   9 prompt ніколи            — як у коментарів: пастка `window.prompt` у кожному вікні й кожній рамці.
 */
import "./_env.mjs";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir, userInfo } from "node:os";
import path from "node:path";
import test, { after, before, describe } from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { startMemo } from "./_memo.mjs";
import { VIEW, postJson, sleep, stop } from "./_spaces-kit.mjs";
import { startServer } from "./fixture.mjs";

const PORT_BASE = 32000;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules");
const SPACE = "mod";
const TASK = "fixture";
const PW = "1100";
const PAGE_HASH = `#p=${encodeURIComponent("it1/holovna")}`;
const TOKENS_CSS = ":root{\n  --color-primary-400: #025CFF;\n  --sp-4: 16px;\n}\n";

/** Сторінка під три вироки: токен зі знімка (`#ok`), вигадане імʼя (`#off`), flex-обгортка для розкладки (`#wrap`). */
const PAGE = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Головна</title><style>
*{box-sizing:border-box}
:root{--color-primary-400:#025CFF;--sp-4:16px;--bf-ink:#123456}
body{margin:0;height:900px;font:14px/1.4 sans-serif;background:#fff}
#wrap{margin:30px;padding:var(--sp-4);display:flex;gap:24px;justify-content:flex-start;align-items:flex-start;background:#eef}
.card{margin:0;padding:var(--sp-4);width:220px;height:120px;background:#fff}
#ok{color:var(--color-primary-400)}
#off{color:var(--bf-ink)}
</style></head><body>
<div id="wrap"><p id="ok" class="card">Токен</p><p id="off" class="card">Повз ДС</p></div>
</body></html>`;

function browsersPath() {
  if (process.env.PLAYWRIGHT_BROWSERS_PATH) return process.env.PLAYWRIGHT_BROWSERS_PATH;
  const home = userInfo().homedir;
  if (process.platform === "darwin") return path.join(home, "Library", "Caches", "ms-playwright");
  return path.join(process.env.XDG_CACHE_HOME || path.join(home, ".cache"), "ms-playwright");
}

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

async function until(fn, what, ms = 15000) {
  const end = Date.now() + ms;
  let last;
  while (Date.now() < end) {
    last = await fn();
    if (last) return last;
    await sleep(100);
  }
  return assert.fail(`не дочекались: ${what} (останнє значення: ${JSON.stringify(last)})`);
}

/** Статика на вільному порту — так само, як `publish/` лежить у Vercel. */
async function staticServer(root, port) {
  const child = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "-d", root], { stdio: "ignore" });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    try { if ((await fetch(`${base}/manifest.json`)).ok) return { child, base }; } catch { /* ще не піднявся */ }
    await sleep(250);
  }
  child.kill();
  throw new Error("статичний сервер превʼю не піднявся");
}

/** Тека задачі з однією сторінкою `holovna` під вироки. */
function task() {
  const dir = mkdtempSync(path.join(tmpdir(), "dc-pinsp-"));
  const it1 = path.join(dir, "iterations", "it1");
  mkdirSync(path.join(it1, "holovna"), { recursive: true });
  writeFileSync(path.join(it1, "holovna", "index.html"), PAGE);
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({ pages: [{ id: "holovna", name: "Головна", published: true }] }));
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({
    iterations: [{ id: "it1", date: "20.11.2026 12:00", note: "фікстура", published: true }],
  }));
  return dir;
}

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Сервер + збірка превʼю + статика. `tokens` — чи є в просторі `css-tokens`; `comments` — чи є командні коментарі (memo). */
async function boot(cleanups, { tokens, comments, port }) {
  const dir = task();
  const server = await startServer(null, {
    portBase: PORT_BASE + port, spaces: [{ name: "Mod", id: SPACE, color: "space-3", tasks: { [TASK]: { dir, title: "Задача" } } }],
    env: { DEAI_EXTRA_MODULES: MODULES_DIR, PLAYWRIGHT_BROWSERS_PATH: browsersPath() },
  });
  cleanups.push(() => stop(server.child));
  let memo = null;
  if (comments) {
    memo = await startMemo();
    cleanups.push(() => memo.close());
    const en = await (await postJson(server.url, "/api/module-enable", {
      space: SPACE, id: "memo-comments", settings: { endpoint: memo.url }, secrets: { token: "TOKEN-PRIVATE", pubkey: "PUBKEY-public" },
    })).json();
    assert.equal(en.ok, true, `module-enable memo: ${JSON.stringify(en)}`);
  }
  if (tokens) {
    const cssDir = mkdtempSync(path.join(tmpdir(), "dc-pinsp-css-"));
    const cssFile = path.join(cssDir, "tokens.css");
    writeFileSync(cssFile, TOKENS_CSS);
    const en = await (await postJson(server.url, "/api/module-enable", {
      space: SPACE, id: "css-tokens", settings: { file: cssFile },
    })).json();
    assert.equal(en.ok, true, `module-enable css-tokens: ${JSON.stringify(en)}`);
  }
  const res = await postJson(server.url, "/api/publish", {});
  const body = await res.json();
  assert.equal(res.status, 200, `POST /api/publish: ${JSON.stringify(body)}`);
  const out = path.join(server.home, "deai-published", SPACE, TASK);
  const stat = await staticServer(out, PORT_BASE + port + 200);
  cleanups.push(() => stat.child.kill());
  return { ...server, memo, out, base: stat.base };
}

/** Вхід у превʼю: збірка модуля — без воріт, збірка ЛІГИ — з паролем; пускаємо за тим, що є. */
async function enter(page, env) {
  await page.goto(`${env.base}/${PAGE_HASH}`);
  await page.locator("#agpass, #bar .bar").first().waitFor({ state: "attached" });
  if (await page.locator("#agpass").count()) {
    await page.fill("#agpass", PW);
    await page.click("#authform button");
  }
  await page.locator("#bar .bar").waitFor();
}

/** Новий контекст: нічого, крім локального, не пускає; кожен запит записується; `prompt` — кидає й рахує. */
async function openPreview(env, { init = null } = {}) {
  const ctx = await browser.newContext({ viewport: VIEW });
  const requests = [];
  const outside = [];
  ctx.on("request", (r) => { requests.push(r.url()); if (!isLocal(r.url())) outside.push(r.url()); });
  await ctx.route((u) => !isLocal(u.href), (route) => {
    // CDN `html2canvas` шару коментатора — порожній скрипт; усе інше поза машиною — відмова (і в `outside`)
    return new URL(route.request().url()).hostname === "cdn.jsdelivr.net"
      ? route.fulfill({ status: 200, contentType: "application/javascript", body: "" }) : route.abort("blockedbyclient");
  });
  await ctx.addInitScript(() => {
    window.__prompts = [];
    window.prompt = (...a) => { window.__prompts.push(a); throw new Error("prompt() is not supported"); };
  });
  if (init) await ctx.addInitScript(init);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await enter(page, env);
  const frame = await until(() => page.frames().find((f) => /\/it1\/holovna\/index\.html$/.test(f.url())) ?? null, "рамка макета");
  await frame.waitForLoadState("load");
  await until(() => frame.evaluate(() => !!window.CanvasInspector).catch(() => false), "оверлей інспектора в рамці");
  return { ctx, page, frame, requests, outside, errors };
}

const on = (frame) => frame.evaluate(() => !!window.CanvasInspector.on);
const panelShown = (page) => page.evaluate(() => { const p = document.getElementById("insp-panel"); return !!p && !p.hidden; });
const cmtShown = (page) => page.evaluate(() => { const p = document.getElementById("cmt-panel"); return !!p && !p.hidden; });
const addMode = (frame) => frame.evaluate(() => !!window.CommentLayer?.commentMode);
const shownBox = (page, sel) => page.evaluate((s) => {
  const e = document.querySelector(s);
  return !!e && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
}, sel);

/** Запінити елемент макета кліком. Інспектор мусить бути ввімкнений. */
async function pin(o, sel, edge = false) {
  const box = await o.frame.locator(sel).boundingBox();
  assert.ok(box, `нема ${sel} у макеті`);
  // `edge` — по полю самого елемента (його відступу), а не по центру, де лежить дитина
  await o.page.mouse.click(edge ? box.x + 4 : box.x + box.width / 2, edge ? box.y + 4 : box.y + box.height / 2);
  await until(() => o.frame.evaluate((s) => !!(window.CanvasInspector.pinned && window.CanvasInspector.pinned.matches(s)), sel), `пін ${sel}`);
}

/** Віддати фокус ОБОЛОНЦІ (після кліку в рамку він у ній): наступні клавіші летять у `document.body` обгортки. */
const focusShell = (page) => page.evaluate(() => { document.activeElement?.blur(); window.focus(); });

describe("інспектор у превʼю: збірка із знімком токенів і командними коментарями", () => {
  const cleanups = [];
  let env;
  const seen = { requests: [], outside: [], prompts: 0 };
  before(async () => { env = await boot(cleanups, { tokens: true, comments: true, port: 0 }); });
  after(async () => { for (const c of cleanups.reverse()) await c(); });

  const open = async (t, opts) => {
    const o = await openPreview(env, opts);
    t.after(async () => {
      seen.requests.push(...o.requests);
      seen.outside.push(...o.outside);
      for (const f of [o.page, o.frame]) seen.prompts += (await f.evaluate(() => window.__prompts.length).catch(() => 0));
      await o.ctx.close();
    });
    return o;
  };

  test("1: у смузі «Інспектор»; I на оболонці й I з фокусом у рамці вмикають і вимикають його", async (t) => {
    const o = await open(t);
    const { page, frame } = o;
    const btn = page.locator('#bar [data-act="inspector"]');
    await btn.waitFor();
    assert.equal(await btn.getAttribute("aria-label"), "Інспектор");
    assert.match(await btn.getAttribute("title"), /I · Alt/);
    assert.equal(await btn.getAttribute("aria-pressed"), "false");
    assert.deepEqual(await page.evaluate(() => [...document.querySelectorAll("#bar .ext-tools [data-act]")].map((b) => b.dataset.act)),
      ["comments", "inspector", "clean"], "порядок кнопок інструментів у смузі");
    assert.equal(await panelShown(page), false, "панель відкрита до натискання");

    await focusShell(page);
    await page.keyboard.press("i");
    await until(() => on(frame), "I на оболонці ввімкнула оверлей");
    assert.equal(await panelShown(page), true, "панель не зʼявилась");
    assert.equal(await btn.getAttribute("aria-pressed"), "true");
    await page.keyboard.press("i");
    await until(async () => !(await on(frame)), "друга I вимкнула");
    assert.equal(await panelShown(page), false);

    // фокус у рамці: I ловить сам оверлей, а оболонка дізнається з `onChange`
    await frame.locator("#wrap").click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("i");
    await until(() => on(frame), "I з рамки ввімкнула оверлей");
    await until(() => panelShown(page), "панель після I з рамки");
    assert.equal(await btn.getAttribute("aria-pressed"), "true");
    await page.keyboard.press("i");
    await until(async () => !(await on(frame)), "I з рамки вимкнула");
    assert.equal(await panelShown(page), false);

    // кнопка смуги — той самий перемикач; закриття в шапці панелі теж
    await btn.click();
    await until(() => on(frame), "кнопка смуги");
    await page.locator('#insp-panel [data-act="inspector"]').click();
    await until(async () => !(await on(frame)), "кнопка закриття в шапці панелі");
    assert.equal(await panelShown(page), false);
    assert.deepEqual(o.errors, []);
  });

  test("2: клік по елементу показує значення й токен зі знімка; вигаданий токен — «повз ДС»", async (t) => {
    const o = await open(t);
    const { page } = o;
    await page.keyboard.press("i");
    await until(() => on(o.frame), "оверлей");
    await pin(o, "#ok");
    const color = page.locator('#insp-panel .insp-f[data-prop="color"]');
    await color.waitFor();
    assert.equal(await color.getAttribute("data-verdict"), "token",
      "вирок не `token`: знімок не доїхав (інакше імʼя --color-primary-400 нікому не відоме)");
    assert.equal((await color.locator(".insp-tok").textContent()).trim(), "color-primary-400");
    assert.equal((await color.locator(".insp-ro").textContent()).trim(), "025CFF", "значення — текстом");
    const pad = page.locator('#insp-panel .insp-f[data-props="padding-left padding-right"]');
    assert.equal((await pad.locator(".insp-ro").textContent()).trim(), "16");
    assert.match(await page.locator("#insp-panel .insp-name").textContent(), /^p\.card$/);

    await pin(o, "#off");
    const off = page.locator('#insp-panel .insp-f[data-prop="color"]');
    await until(async () => (await off.getAttribute("data-verdict")) === "off-ds", "вирок off-ds для --bf-ink");
    assert.equal(await off.locator(".insp-tok[data-off]").count(), 1, "чип «повз ДС»");
    assert.deepEqual(o.errors, []);
  });

  test("3: панель лише для перегляду: ні input, ні textarea, ні select, ні contenteditable, ні тюнера", async (t) => {
    const o = await open(t);
    const { page } = o;
    await page.keyboard.press("i");
    await until(() => on(o.frame), "оверлей");
    // порожній стан (нічого не вибрано): лише шапка
    assert.equal(await page.locator("#insp-panel .insp-body").count(), 1);
    await pin(o, "#wrap", true);                                 // flex-обгортка: є й матриця вирівнювання
    await page.locator("#insp-panel .insp-sec").first().waitFor();
    assert.equal(await page.locator("#insp-panel input, #insp-panel textarea, #insp-panel select, #insp-panel [contenteditable]").count(), 0,
      "у режимі перегляду зʼявилось поле вводу");
    for (const sel of ['[data-act="insptune"]', '[data-act="insptunecolor"]', '[data-act="inspsnap"]', '[data-act="inspadd"]',
      '[data-act="inspsides"]', '[data-act="inspalign"]', '[data-act="inspdir"]', "[data-scrub]", ".insp-foot", ".insp-snap"]) {
      assert.equal(await page.locator(`#insp-panel ${sel}`).count(), 0, `у режимі перегляду є ${sel}`);
    }
    // розкладка видна — вимкненими кнопками, натиснуте вічко одне
    assert.equal(await page.locator("#insp-panel .insp-cell[disabled]").count(), 9);
    assert.equal(await page.locator('#insp-panel .insp-dir[disabled]').count(), 2);
    assert.equal(await page.locator('#insp-panel .insp-cell[aria-pressed="true"]').count(), 1);
    // жодного дотику до макета: значення не змінились (клік по вимкненому вічку нічого не пише)
    const before = await o.frame.evaluate(() => getComputedStyle(document.getElementById("wrap")).justifyContent);
    await page.locator("#insp-panel .insp-cell").nth(8).click({ force: true });
    assert.equal(await o.frame.evaluate(() => getComputedStyle(document.getElementById("wrap")).justifyContent), before);
    assert.equal(await o.frame.evaluate(() => document.getElementById("wrap").hasAttribute("style")), false, "макет отримав інлайн-стиль");
    assert.deepEqual(o.errors, []);
  });

  test("4: Alt — відстані, Esc/↵ — батько/дочірній, ← → — сусід: з рамки й з оболонки", async (t) => {
    const o = await open(t);
    const { page, frame } = o;
    await page.keyboard.press("i");
    await until(() => on(frame), "оверлей");
    await pin(o, "#ok");                                           // клік віддав фокус рамці
    const pinnedId = () => frame.evaluate(() => { const p = window.CanvasInspector.pinned; return p ? (p.id || p.tagName.toLowerCase()) : null; });
    await page.keyboard.down("Alt");
    await until(() => frame.evaluate(() => window.CanvasInspector.alt === true), "Alt з рамки показав відстані");
    await page.keyboard.up("Alt");
    await until(() => frame.evaluate(() => window.CanvasInspector.alt === false), "Alt відпущено");
    await page.keyboard.press("ArrowRight");
    await until(async () => (await pinnedId()) === "off", "→ у рамці — сусід");
    await page.keyboard.press("ArrowLeft");
    await until(async () => (await pinnedId()) === "ok", "← у рамці — назад");
    await page.keyboard.press("Escape");
    await until(async () => (await pinnedId()) === "wrap", "Esc у рамці — батько");
    await page.keyboard.press("Enter");
    await until(async () => (await pinnedId()) === "ok", "↵ у рамці — дочірній");

    // фокус в оболонці: ті самі клавіші, той самий оверлей
    await focusShell(page);
    await page.keyboard.press("Escape");
    await until(async () => (await pinnedId()) === "wrap", "Esc на оболонці — батько");
    await page.keyboard.press("Enter");
    await until(async () => (await pinnedId()) === "ok", "↵ на оболонці — дочірній");
    await page.keyboard.press("ArrowRight");
    await until(async () => (await pinnedId()) === "off", "→ на оболонці — сусід");
    await page.keyboard.down("Alt");
    await until(() => frame.evaluate(() => window.CanvasInspector.alt === true), "Alt з оболонки показав відстані");
    await page.keyboard.up("Alt");
    await until(() => frame.evaluate(() => window.CanvasInspector.alt === false), "Alt з оболонки відпущено");
    assert.deepEqual(o.errors, []);
  });

  test("5: інспектор і коментарі взаємовиключні: відкриття одного закриває інше, зокрема режим додавання", async (t) => {
    const o = await open(t, { init: () => { try { localStorage.setItem("comment-layer:user", "Тест"); } catch (e) { /* ні */ } } });
    const { page, frame } = o;
    await until(() => frame.evaluate(() => !!(window.CommentLayer && window.CommentLayer._inited)).catch(() => false), "коментатор у рамці");
    const cbtn = page.locator('#bar [data-act="comments"]');
    const ibtn = page.locator('#bar [data-act="inspector"]');
    await cbtn.waitFor();

    await page.keyboard.press("c");
    await until(() => cmtShown(page), "коментарі відкрито");
    await until(() => addMode(frame), "імʼя відоме — режим додавання ввімкнувся разом із панеллю");
    await ibtn.click();
    await until(() => on(frame), "інспектор ввімкнувся");
    assert.equal(await cmtShown(page), false, "панель коментарів лишилась відкритою");
    assert.equal(await addMode(frame), false, "режим додавання лишився ввімкненим");
    assert.equal(await panelShown(page), true);
    assert.equal(await cbtn.getAttribute("aria-pressed"), "false");

    await cbtn.click();
    await until(() => cmtShown(page), "коментарі відкрилися");
    assert.equal(await on(frame), false, "інспектор лишився ввімкненим");
    assert.equal(await panelShown(page), false, "панель інспектора лишилась відкритою");
    assert.equal(await ibtn.getAttribute("aria-pressed"), "false");

    // клавіші: C ↔ I з обох боків
    await focusShell(page);
    await page.keyboard.press("i");
    await until(() => on(frame), "I");
    assert.equal(await cmtShown(page), false);
    await page.keyboard.press("c");
    await until(() => cmtShown(page), "C");
    assert.equal(await on(frame), false);
    // I з рамки при відкритих коментарях
    await frame.locator("#wrap").click({ position: { x: 4, y: 4 } });
    await until(async () => !(await addMode(frame)) || true, "—");
    if (await addMode(frame)) await page.locator('#cmt-panel [data-act="cmtadd"]').click();
    await frame.locator("body").press("i");
    await until(() => on(frame), "I з рамки");
    assert.equal(await cmtShown(page), false, "I з рамки не закрила коментарі");
    assert.deepEqual(o.errors, []);
  });

  test("6: «Сховати інтерфейс» і ⇧⌘\\ закривають обидві панелі; у чистому вигляді I не вмикає інспектор", async (t) => {
    const o = await open(t);
    const { page, frame } = o;
    const clean = () => page.evaluate(() => document.documentElement.classList.contains("cv-clean"));
    await page.keyboard.press("i");
    await until(() => on(frame), "інспектор");
    await pin(o, "#ok");
    await page.click('#bar [data-act="clean"]');
    await until(clean, "чистий перегляд");
    assert.equal(await on(frame), false, "оверлей лишився ввімкненим у чистому вигляді");
    assert.equal(await panelShown(page), false);
    assert.equal(await shownBox(page, "#insp-panel"), false);
    assert.equal(await shownBox(page, "#cmt-panel"), false);

    // I у чистому вигляді (фокус у рамці й на оболонці) інспектор не вмикає
    await frame.locator("#wrap").click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("i");
    await sleep(300);
    assert.equal(await on(frame), false, "I з рамки ввімкнула інспектор у чистому вигляді");
    await focusShell(page);
    await page.keyboard.press("i");
    await sleep(200);
    assert.equal(await on(frame), false, "I на оболонці ввімкнула інспектор у чистому вигляді");

    await page.keyboard.press("ControlOrMeta+Shift+Backslash");
    await until(async () => !(await clean()), "акорд повернув інтерфейс");
    assert.equal(await shownBox(page, "#bar .ext-tools"), true);
    assert.equal(await on(frame), false, "повернення не вмикає інспектор саме");

    // акорд з відкритим інспектором — з рамки
    await page.keyboard.press("i");
    await until(() => on(frame), "інспектор знову");
    await frame.locator("#wrap").click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("ControlOrMeta+Shift+Backslash");
    await until(clean, "акорд з рамки");
    assert.equal(await on(frame), false);
    assert.equal(await panelShown(page), false);
    await page.click("#cv-unclean");
    await until(async () => !(await clean()), "кнопка повернення");

    // і коментарі: відкриті + акорд → закриті
    await focusShell(page);
    await page.keyboard.press("c");
    await until(() => cmtShown(page), "коментарі");
    await page.keyboard.press("ControlOrMeta+Shift+Backslash");
    await until(clean, "акорд при коментарях");
    assert.equal(await cmtShown(page), false);
    assert.equal(await on(frame), false);
    assert.deepEqual(o.errors, []);
  });

  test("7: жодного запиту до /api/… і за межі машини; знімок токенів — єдиний запит оверлея; prompt() не кликали", async (t) => {
    const o = await open(t);
    const { page, frame } = o;
    await page.keyboard.press("i");
    await until(() => on(frame), "оверлей");
    await pin(o, "#ok");
    await page.locator('#insp-panel .insp-f[data-prop="color"] .insp-tok').waitFor();
    assert.ok(o.requests.some((u) => /\/shell\/ds-snapshot\.json$/.test(new URL(u).pathname)), "знімок токенів не запитували");
    assert.deepEqual(o.requests.filter((u) => new URL(u).pathname.startsWith("/api/")), [], "превʼю запитало /api/…");
    assert.deepEqual(o.outside, [], "запити за межі машини");
    assert.deepEqual(await page.evaluate(() => window.__prompts), [], "prompt() у вікні");
    assert.deepEqual(await frame.evaluate(() => window.__prompts), [], "prompt() у рамці");
    assert.deepEqual(o.errors, []);
  });

  test("8: наприкінці — нічого не просили в /api/ і prompt не кликали за весь прогін", async () => {
    assert.ok(seen.requests.length > 20, `свідок порожній: ${seen.requests.length} запитів`);
    assert.deepEqual(seen.requests.filter((u) => new URL(u).pathname.startsWith("/api/")), []);
    assert.deepEqual(seen.outside, []);
    assert.equal(seen.prompts, 0);
  });
});

describe("інспектор у превʼю: простір без модуля токенів — значення без звірки з ДС", () => {
  const cleanups = [];
  let env;
  before(async () => { env = await boot(cleanups, { tokens: false, comments: false, port: 1000 }); });
  after(async () => { for (const c of cleanups.reverse()) await c(); });

  test("9: файла знімка нема, оверлей працює, вироків про ДС нема, /api/ не просили", async (t) => {
    const o = await openPreview(env);
    t.after(() => o.ctx.close());
    const res = await fetch(`${env.base}/shell/ds-snapshot.json`);
    assert.equal(res.status, 404, "знімок є в збірці без модуля токенів");
    const tag = await o.frame.evaluate(() => [...document.scripts].map((s) => s.src).find((s) => s.includes("inspector.js")));
    assert.ok(tag && !/[?&](sp|tok)=/.test(tag), `тег несе sp/tok без знімка: ${tag}`);
    await o.page.keyboard.press("i");
    await until(() => on(o.frame), "оверлей");
    await pin(o, "#ok");
    const color = o.page.locator('#insp-panel .insp-f[data-prop="color"]');
    await color.waitFor();
    assert.equal((await color.locator(".insp-ro").textContent()).trim(), "025CFF", "значення видно");
    // без ДС звіряти нема з чим: `var()` лишається `var()`, але ніщо не називається «повз ДС» чи «перевизначено»
    await pin(o, "#off");
    await until(async () => (await o.page.locator("#insp-panel .insp-name").textContent()).includes("card"), "інший елемент");
    const verdict = await o.page.locator('#insp-panel .insp-f[data-prop="color"]').getAttribute("data-verdict");
    assert.ok(verdict !== "off-ds" && verdict !== "overridden", `без знімка вирок про ДС: ${verdict}`);
    assert.equal(await o.page.locator("#insp-panel .insp-tok[data-off]").count(), 0, "«повз ДС» без знімка");
    assert.deepEqual(o.requests.filter((u) => new URL(u).pathname.startsWith("/api/")), []);
    assert.deepEqual(o.requests.filter((u) => /ds-snapshot/.test(u)), [], "оверлей питає знімок, якого нема");
    assert.deepEqual(o.outside, []);
    assert.deepEqual(o.errors, []);
  });
});
