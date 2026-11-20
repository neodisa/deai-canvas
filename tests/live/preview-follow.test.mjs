/**
 * Дерево превʼю йде за посиланнями в макеті + режим додавання коментарів перезаряджається на новій сторінці
 * (0.32.0, етап Ж, Task 5) — живе проведення на ЗІБРАНОМУ `publish/` (як `preview-comments`: статика, memo, без мережі).
 * У збірці до сторінки «Головна» дописано посилання (лише в збірці фікстури, не в коді продукту).
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо його прибрати»:
 *   1 дерево, хеш, «Скопіювати посилання» ідуть за рамкою, без другої навігації — `followFrame()` у слухачі `load` оболонки
 *      (без нього вибір у дереві лишається на старій сторінці); `expectedId` — щоб `apply()` не зациклився.
 *   2 посилання поза збіркою (404) — нічого не міняє — `followPageOf` повертає `null`.
 *   3 імʼя відоме, панель відкрита, додавання ввімкнене — нова сторінка теж на додаванні — гілка `ready` у `ext-comments.js`.
 *   4 «+» вимкнув додавання — нова сторінка лишається вимкненою — `st.userOff`.
 */
import "./_env.mjs";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { userInfo } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { startMemo } from "./_memo.mjs";
import { ANCHOR, t45Task } from "./_t45-fixture.mjs";
import { VIEW, guardRealDeai, postJson, sleep, stop } from "./_spaces-kit.mjs";
import { startServer } from "./fixture.mjs";

const PORT_BASE = 45000;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MODULES_DIR = path.join(ROOT, "tests", "fixtures", "modules");
const MODULE = "memo-comments";
const SPACE = "mod";
const TASK = "fixture";
const CHANNEL = `deai/${SPACE}/${TASK}`;
const TOKEN = "TOKEN-PRIVATE-do-not-leak";
const PUBKEY = "PUBKEY-public-ok";
const PW = "1100";
const OWN_KEY = `dc-own:${CHANNEL}`;
const USER_KEY = "comment-layer:user";
const PAGE_HASH = `#p=${encodeURIComponent("it1/holovna")}`;

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

let browser;
const shots = process.env.ZH_SHOTS_DIR;
test.before(async () => {
  browser = await chromium.launch();
  if (shots) mkdirSync(shots, { recursive: true });
});
test.after(async () => { await browser?.close(); });
const OUTSIDE = [];
const STUBBED = [];
const CDN = "cdn.jsdelivr.net";

/** Сервер + memo + збірка превʼю (`enable` — чи є в просторі модуль коментарів) + статика над `publish/`. */
async function boot(t, { enable = true, port = 0 } = {}) {
  const memo = await startMemo();
  t.after(() => memo.close());
  const task = t45Task();
  const server = await startServer(null, {
    portBase: PORT_BASE + port, spaces: [{ name: "Mod", id: SPACE, color: "space-3", tasks: { [TASK]: { dir: task.dir, title: "Задача" } } }],
    env: { DEAI_EXTRA_MODULES: MODULES_DIR, PLAYWRIGHT_BROWSERS_PATH: browsersPath() },
  });
  t.after(() => stop(server.child));
  if (enable) {
    const en = await (await postJson(server.url, "/api/module-enable", {
      space: SPACE, id: MODULE, settings: { endpoint: memo.url }, secrets: { token: TOKEN, pubkey: PUBKEY },
    })).json();
    assert.equal(en.ok, true, `module-enable: ${JSON.stringify(en)}`);
  }
  const res = await postJson(server.url, "/api/publish", {});
  const body = await res.json();
  assert.equal(res.status, 200, `POST /api/publish: ${JSON.stringify(body)}`);
  const out = path.join(server.home, "deai-published", SPACE, TASK);
  /* Посилання між сторінками — лише в ЗБІРЦІ фікстури (у продукті їх додає макет): головна веде на «Пошук» і на сторінку, якої
     в збірці нема (404); «Пошук» веде назад. */
  const link = (file, html) => {
    const f = path.join(out, "it1", file, "index.html");
    const src = readFileSync(f, "utf8");
    assert.ok(src.includes("Кабінет</nav>"), `у ${file} нема місця для посилань`);
    writeFileSync(f, src.replace("Кабінет</nav>", `Кабінет ${html}</nav>`));
  };
  link("holovna", '<a id="to-poshuk" style="color:#fff" href="../poshuk/index.html">до пошуку</a> '
    + '<a id="to-missing" style="color:#fff" href="../missing/index.html">до нікуди</a>');
  link("poshuk", '<a id="to-holovna" style="color:#fff" href="../holovna/index.html">назад</a>');
  const stat = await staticServer(out, PORT_BASE + port + 200);
  t.after(() => stat.child.kill());
  return { ...server, memo, out, base: stat.base, task };
}

/** Вхід у превʼю: збірка модуля публікації — без воріт (`gate_pw=None`), збірка ЛІГИ — з паролем; пускаємо за тим, що є. */
async function enter(page, env) {
  await page.goto(`${env.base}/${PAGE_HASH}`);
  await page.locator("#agpass, #bar .bar").first().waitFor({ state: "attached" });
  if (await page.locator("#agpass").count()) {
    await page.fill("#agpass", PW);
    await page.click("#authform button");
  }
  await page.locator("#bar .bar").waitFor();
}

/** Новий контекст браузера: нічого, крім локального, не пускає; CDN `html2canvas` — порожній скрипт; `prompt` — кидає й рахує. */
async function openPreview(env, t, { promptStub = true, init = null, initArg = null, early = false } = {}) {
  const ctx = await browser.newContext({ viewport: VIEW, permissions: ["clipboard-read", "clipboard-write"] });
  t.after(() => ctx.close());
  const outside = [];
  /* `html2canvas` шару коментатора — єдине, що просять поза машиною; його ПІДМІНЕНО порожнім скриптом (на мережу не виходить). */
  ctx.on("request", (r) => {
    if (isLocal(r.url())) return;
    if (new URL(r.url()).hostname === CDN) { STUBBED.push(r.url()); return; }
    outside.push(r.url()); OUTSIDE.push(r.url());
  });
  await ctx.route((u) => !isLocal(u.href), (route) => (new URL(route.request().url()).hostname === CDN
    ? route.fulfill({ status: 200, contentType: "application/javascript", body: "" }) : route.abort("blockedbyclient")));
  if (promptStub) {
    /* У КОЖНОМУ вікні й КОЖНІЙ рамці: виклик записується й кидає, тож «prompt() не кликали» — це й факт, і відсутність падіння. */
    await ctx.addInitScript(() => {
      window.__prompts = [];
      window.prompt = (...a) => { window.__prompts.push(a); throw new Error("prompt() is not supported"); };
    });
  }
  if (init) await ctx.addInitScript(init, initArg);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await enter(page, env);
  if (early) return { ctx, page, outside, errors };
  const frame = await until(() => page.frames().find((f) => /\/it1\/holovna\/index\.html$/.test(f.url())) ?? null, "рамка макета");
  await frame.waitForLoadState("load");
  await until(() => frame.evaluate(() => !!(window.CommentLayer && window.CommentLayer._inited)).catch(() => false), "коментатор у рамці");
  return { ctx, page, frame, outside, errors };
}

const panelOpen = (page) => page.evaluate(() => { const p = document.getElementById("cmt-panel"); return !!p && !p.hidden; });
const preName = ([k, v]) => { try { localStorage.setItem(k, v); } catch { /* пісочниця */ } };
const mode = (frame) => frame.evaluate(() => !!window.CommentLayer.commentMode);

const frameOf = (page, re) => until(() => page.frames().find((f) => re.test(f.url())) ?? null, `рамка ${re}`);
const readyFrame = async (page, re) => {
  const f = await frameOf(page, re);
  await f.waitForLoadState("load");
  await until(() => f.evaluate(() => !!(window.CommentLayer && window.CommentLayer._inited)).catch(() => false), "коментатор у рамці");
  return f;
};
const selectedRow = (page) => page.evaluate(() => document.querySelector("#pages-panel .row--sel")?.getAttribute("data-page") ?? null);
const hash = (page) => page.evaluate(() => location.hash);
const frameSrcAttr = (page) => page.evaluate(() => document.getElementById("frame").getAttribute("src"));
const clipboard = (page) => page.evaluate(() => navigator.clipboard.readText());

test("1: посилання в макеті на сторінку цієї ітерації — дерево, #p= і «Скопіювати посилання» йдуть за рамкою; без перезавантаження й без другого frame.src", async (t) => {
  const env = await boot(t, { port: 0 });
  const o = await openPreview(env, t);
  const { page, frame } = o;
  const navs = [];
  page.on("framenavigated", (f) => { if (f.parentFrame()) navs.push(f.url()); });
  assert.equal(await selectedRow(page), "it1/holovna");
  const srcBefore = await frameSrcAttr(page);

  await frame.locator("#to-poshuk").click();
  await until(async () => (await hash(page)) === `#p=${encodeURIComponent("it1/poshuk")}`, "хеш пішов за рамкою");
  assert.equal(await selectedRow(page), "it1/poshuk", "вибір у дереві не пішов за рамкою");
  await page.locator('#bar [data-act="copylink"]').first().click();
  await until(async () => (await clipboard(page)).includes(`p=${encodeURIComponent("it1/poshuk")}`), "скопійоване посилання веде на нову сторінку");

  await page.waitForTimeout(1200);          // другий `frame.src` (apply) дав би ще одну навігацію
  assert.equal(navs.filter((u) => /\/it1\/poshuk\/index\.html$/.test(u)).length, 1, `зайва навігація: ${JSON.stringify(navs)}`);
  assert.equal(await frameSrcAttr(page), srcBefore, "оболонка перепризначила frame.src");

  // і назад тим самим шляхом
  const f2 = await readyFrame(page, /\/it1\/poshuk\/index\.html$/);
  await f2.locator("#to-holovna").click();
  await until(async () => (await hash(page)) === `#p=${encodeURIComponent("it1/holovna")}`, "хеш повернувся");
  assert.equal(await selectedRow(page), "it1/holovna");
  assert.deepEqual(o.errors, []);
});

test("2: посилання на сторінку поза збіркою (404) нічого не міняє: вибір, хеш, посилання", async (t) => {
  const env = await boot(t, { port: 1000 });
  const o = await openPreview(env, t);
  const { page, frame } = o;
  const h0 = await hash(page);
  await frame.locator("#to-missing").click();
  await frameOf(page, /\/it1\/missing\/index\.html$/);
  await page.waitForTimeout(800);
  assert.equal(await hash(page), h0);
  assert.equal(await selectedRow(page), "it1/holovna");
  await page.locator('#bar [data-act="copylink"]').first().click();
  await until(async () => (await clipboard(page)).includes(`p=${encodeURIComponent("it1/holovna")}`), "посилання лишилось на попередній сторінці");
  assert.deepEqual(o.errors, []);
});

test("3: імʼя відоме, панель відкрита, додавання ввімкнене — після переходу за посиланням нова сторінка теж на додаванні (клік = пін без діалогу)", async (t) => {
  const env = await boot(t, { port: 2000 });
  const o = await openPreview(env, t, { init: preName, initArg: [USER_KEY, "Сам Собі"] });
  const { page, frame } = o;
  await page.keyboard.press("c");
  await until(() => mode(frame), "додавання на першій сторінці");
  /* У режимі додавання клік по посиланню коментатор перехоплює (це й є «додати коментар до посилання»), тож перехід макета
     робимо його ж скриптом — як зробив би роутер чи редирект. */
  await frame.evaluate(() => { location.href = document.getElementById("to-poshuk").href; });
  const f2 = await readyFrame(page, /\/it1\/poshuk\/index\.html$/);
  await until(() => mode(f2), "нова сторінка не на додаванні");
  assert.equal(await page.locator('#cmt-panel [data-act="cmtadd"]').getAttribute("aria-pressed"), "true");
  await f2.locator("ol li:nth-child(2)").click();
  const ta = f2.locator("[data-comment-layer] .compose textarea");
  await ta.waitFor();
  await ta.fill("Після переходу");
  await f2.locator("[data-comment-layer] .compose .save").click();
  const row = await until(() => (env.memo.store.get(CHANNEL) ?? []).find((c) => c.text === "Після переходу") ?? null, "коментар у сервісі");
  assert.equal(row.author, "Сам Собі");
  assert.equal(await page.locator(".cv-ask--form").count(), 0, "імʼя спитали");

  // те саме після переходу ПО ДЕРЕВУ: рядок «Головна»
  await until(async () => !(await mode(f2)) || (await page.locator('#cmt-panel [data-act="cmtadd"]').getAttribute("aria-pressed")) === "true", "стан після створення");
  await page.locator('#pages-panel .row', { hasText: "Головна" }).first().click();
  const f3 = await readyFrame(page, /\/it1\/holovna\/index\.html$/);
  await until(() => mode(f3), "перехід по дереву не перезарядив додавання");
  assert.deepEqual(o.errors, []);
});

test("4: «+» вимкнув додавання — після переходу за посиланням і по дереву нова сторінка лишається вимкненою; закриття панелі скидає це", async (t) => {
  const env = await boot(t, { port: 3000 });
  const o = await openPreview(env, t, { init: preName, initArg: [USER_KEY, "Сам Собі"] });
  const { page, frame } = o;
  await page.keyboard.press("c");
  await until(() => mode(frame), "додавання на першій сторінці");
  const add = page.locator('#cmt-panel [data-act="cmtadd"]');
  await add.click();
  await until(async () => !(await mode(frame)) && (await add.getAttribute("aria-pressed")) === "false", "«+» вимкнув додавання");
  await frame.locator("#to-poshuk").click();
  const f2 = await readyFrame(page, /\/it1\/poshuk\/index\.html$/);
  await page.waitForTimeout(800);
  assert.equal(await mode(f2), false, "нова сторінка ввімкнула додавання попри «+»");
  assert.equal(await add.getAttribute("aria-pressed"), "false");
  await page.locator('#pages-panel .row', { hasText: "Головна" }).first().click();
  const f3 = await readyFrame(page, /\/it1\/holovna\/index\.html$/);
  await page.waitForTimeout(800);
  assert.equal(await mode(f3), false, "перехід по дереву ввімкнув додавання попри «+»");

  // закрили панель й відкрили знову — це нова «сесія»: додавання знову вмикається на переході
  await page.keyboard.press("c");
  await page.keyboard.press("c");
  await until(() => mode(f3), "після повторного відкриття додавання не ввімкнулось");
  await f3.evaluate(() => { location.href = document.getElementById("to-poshuk").href; });   // у режимі додавання клік перехоплює коментатор
  const f4 = await readyFrame(page, /\/it1\/poshuk\/index\.html$/);
  await until(() => mode(f4), "нова сесія панелі: сторінка не на додаванні");
  assert.deepEqual(o.errors, []);
});

test("5: імені нема — перехід за посиланням додавання не вмикає і імені не питає", async (t) => {
  const env = await boot(t, { port: 4000 });
  const o = await openPreview(env, t);
  const { page, frame } = o;
  await page.keyboard.press("c");
  await frame.locator("#to-poshuk").click();
  const f2 = await readyFrame(page, /\/it1\/poshuk\/index\.html$/);
  await page.waitForTimeout(800);
  assert.equal(await mode(f2), false);
  assert.equal(await page.locator(".cv-ask--form").count(), 0);
  assert.deepEqual(o.errors, []);
});

test("6: інспектор увімкнено, рамка йде на іншу сторінку (посилання в макеті, дерево) — панель закривається ОДРАЗУ і не показує старий звіт; на новій сторінці він вимкнений (як у Deai)", async (t) => {
  const env = await boot(t, { port: 5000 });
  const o = await openPreview(env, t);
  const { page, frame } = o;
  const panel = () => page.evaluate(() => { const p = document.getElementById("insp-panel"); return !!p && !p.hidden && p.innerHTML.trim() !== ""; });
  const overlayOn = (f) => f.evaluate(() => !!(window.CanvasInspector && window.CanvasInspector.on)).catch(() => null);
  await until(() => frame.evaluate(() => !!window.CanvasInspector).catch(() => false), "оверлей на першій сторінці");
  await page.evaluate(() => { document.activeElement?.blur(); window.focus(); });
  await page.keyboard.press("i");
  await until(() => panel(), "панель інспектора відкрита");

  /* (а) перехід за посиланням У макеті: оболонка навігації не бачить. Тримаємо оверлей нового документа (`inspector.js`), тож
     документ уже ЗАМІНЕНО, а `load` ще нема — рівно те вікно, де лишався б старий звіт. */
  let release;
  const gate = new Promise((done) => { release = done; });
  await o.ctx.route(/\/(vendor\/inspector|comment-layer\/.*)\.js/, async (route) => { await gate; await route.continue(); });
  /* Увімкнений інспектор перехоплює клік (це пін), тож перехід робимо скриптом макета — як роутер чи редирект. */
  await frame.evaluate(() => { location.href = document.getElementById("to-poshuk").href; });
  await until(() => page.frames().some((f) => /\/it1\/poshuk\/index\.html$/.test(f.url())), "документ нової сторінки");
  await until(async () => !(await panel()), "панель досі показує звіт старої сторінки");
  release();
  const f2 = await readyFrame(page, /\/it1\/poshuk\/index\.html$/);
  await until(() => f2.evaluate(() => !!window.CanvasInspector).catch(() => false), "оверлей нової сторінки");
  assert.equal(await overlayOn(f2), false, "інспектор переїхав увімкненим (у Deai він вимикається)");
  assert.equal(await panel(), false);
  assert.equal(await page.locator('.island [data-act="inspector"]').getAttribute("aria-pressed"), "false");
  await o.ctx.unroute(/\/(vendor\/inspector|comment-layer\/.*)\.js/);

  /* (б) перехід по дереву: `apply()` — документ ще старий, але панель закрита вже на старті навігації. */
  await page.evaluate(() => { document.activeElement?.blur(); window.focus(); });
  await page.keyboard.press("i");
  await until(() => panel(), "панель відкрита на другій сторінці");
  let release2;
  const gate2 = new Promise((done) => { release2 = done; });
  await o.ctx.route(/\/it1\/holovna\/index\.html$/, async (route) => { await gate2; await route.continue(); });
  await page.locator('#pages-panel .row', { hasText: "Головна" }).first().click();
  await until(async () => !(await panel()), "панель лишилась відкритою на старті переходу по дереву");
  release2();
  const f3 = await readyFrame(page, /\/it1\/holovna\/index\.html$/);
  await until(() => f3.evaluate(() => !!window.CanvasInspector).catch(() => false), "оверлей на третій сторінці");
  assert.equal(await overlayOn(f3), false);
  assert.equal(await panel(), false);
  assert.deepEqual(o.errors, []);
});

test("99: ізоляція — жодного запиту за межі машини, справжній ~/.deai не зачеплено", () => {
  assert.deepEqual(OUTSIDE, [], `запити за межі машини:\n${OUTSIDE.join("\n")}`);
  guardRealDeai();
});
