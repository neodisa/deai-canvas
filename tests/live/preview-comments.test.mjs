/**
 * Командні коментарі в ОПУБЛІКОВАНОМУ превʼю (0.32.0, етап Ж, Task 3) — живе проведення на ЗІБРАНОМУ `publish/`, який лежить
 * під статичним сервером (так він лежить у Vercel: один origin, без сервера інструмента).
 *
 * Збірка — справжня: сервер у тимчасовій «машині», простір `mod` з модулем `memo-comments` (фікстура
 * `tests/fixtures/modules/memo-comments/`), `POST /api/publish`. Сервіс коментарів — найменший `memo` (`_memo.mjs`, лише
 * 127.0.0.1): ні справжнього Supabase, ні мережі (`context.route` рве все, що не локальне; CDN `html2canvas` підмінено порожнім
 * скриптом). Допоміжний `outside` мусить бути порожнім у кінці кожного тесту.
 *
 * Мапа «перевірка → запобіжник → що станеться, якщо його прибрати»:
 *   1 острівець і C        — `island.comments = true` в `open()` лише з `manifest.comments`; `EXT_ACTIONS.comments`; клавіша C у
 *                            `wire()`. Закриті — без дій: `PREVIEW_ACTIONS.closed = []` у `ext-comments.js`.
 *   2 імʼя перед першим    — `ensureName()` у `setAdding`: прибери виклик — коментатор сам спитає `prompt()` чи підпише «Anonymous».
 *   3 чужий коментар       — `st.isOwn`/`PREVIEW_ACTIONS.own` у `paint`: без них чужа картка отримала б «Редагувати/Видалити».
 *   4 змінити/видалити своє — `actions.cmtedit/cmtdelyes` + `ownGuard`; `host.onAdd` у коментаторі (без нього id нікуди не пишеться).
 *   5 prompt ніколи        — `host.userName` у `PREVIEW_HOST_ARG` + гілка `getUser` у коментаторі.
 *   6 перехід рамки        — `cmt.dropFrame()` в `apply()` і `cmt.onFrameLoad()` у слухачі `load`.
 *   7 без особи машини     — `PREVIEW_HOST_ARG` не має `defaultUser`.
 *   8 збірка без коментарів — `man.comments` у `open()`.
 */
import "./_env.mjs";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { userInfo } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { startMemo } from "./_memo.mjs";
import { ANCHOR, t45Task } from "./_t45-fixture.mjs";
import { VIEW, guardRealDeai, postJson, sleep, stop } from "./_spaces-kit.mjs";
import { startServer } from "./fixture.mjs";

const PORT_BASE = 30000;
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
  const stat = await staticServer(out, PORT_BASE + port + 200);
  t.after(() => stat.child.kill());
  return { ...server, memo, out, base: stat.base, task };
}

/** Посіяти коментарі в memo: відбиток кнопки рахує справжній `CommentLayerAnchor` у bare-сторінці. */
async function seed(env, rows) {
  const ctx = await browser.newContext({ viewport: VIEW });
  const bare = await ctx.newPage();
  await bare.goto(`${env.url}/commented?it=it1&page=holovna&bare=1`);
  await bare.addScriptTag({ content: ANCHOR });
  const fp = await bare.evaluate(() => window.CommentLayerAnchor.fingerprint(
    document.querySelector("[data-testid=subscribe]"), document.body));
  await ctx.close();
  const out = rows.map((r, i) => ({
    id: r.id, author: r.author, text: r.text, status: r.status || "open", fp, htmlSnapshot: null, bornV: 1,
    ts: "19.11.2026 12:00", ...(r.extra || {}),
    meta: { url: `${env.url}/commented?it=it1&page=holovna&ch=project`, route: "/commented", version: "1/holovna",
            iteration: "1", viewport: { w: 1280, h: 900 }, seq: i + 1 },
  }));
  env.memo.store.set(CHANNEL, out);
  return out;
}

const SEED = [
  { id: "seed-open", author: "Олена", text: "Кнопка зливається з фоном" },
  { id: "seed-open-2", author: "Марко", text: "Заголовок задовгий" },
  { id: "seed-closed", author: "Олена", text: "Вирівняйте відступи", status: "resolved", extra: { resolvedV: 2, resolveReason: "Кнопку збільшено" } },
];

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
  const ctx = await browser.newContext({ viewport: VIEW });
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
const cards = (page) => page.evaluate(() => [...document.querySelectorAll("#cmt-panel .cmt-card")].map((c) => ({
  id: c.dataset.cid, who: c.querySelector(".cmt-who")?.textContent, text: c.querySelector(".cmt-text")?.textContent,
  acts: [...c.querySelectorAll("[data-act]")].map((b) => b.dataset.act), done: c.querySelector(".cmt-done")?.textContent ?? null,
  reason: c.querySelector(".cmt-reason")?.textContent ?? null, closed: c.classList.contains("cmt-card--closed"),
})));
const ls = (page, k) => page.evaluate((key) => { try { return localStorage.getItem(key); } catch { return "THROWS"; } }, k);
const prompts = async (o) => ({ shell: await o.page.evaluate(() => window.__prompts), frame: await o.frame.evaluate(() => window.__prompts) });

/** Додати коментар: «+» → (ім'я) → клік по заголовку в рамці → текст → «Comment». Повертає рядок memo. */
async function addComment(o, env, text, { name = "Тест", expectDialog = true } = {}) {
  const { page, frame } = o;
  if (!(await panelOpen(page))) await page.keyboard.press("c");
  await page.locator('#cmt-panel [data-act="cmtadd"]').click();
  if (expectDialog) {
    await page.locator(".cv-ask--form").waitFor();
    await page.fill('.cv-ask--form input[name="name"]', name);
    await page.click('.cv-ask--form button[data-a="ok"]');
    await page.locator(".cv-ask--form").waitFor({ state: "detached" });
  }
  await until(() => frame.evaluate(() => !!window.CommentLayer.commentMode), "режим додавання в рамці");
  await frame.locator("h1").click();
  const ta = frame.locator("[data-comment-layer] .compose textarea");
  await ta.waitFor();
  await ta.fill(text);
  await frame.locator("[data-comment-layer] .compose .save").click();
  return until(() => (env.memo.store.get(CHANNEL) ?? []).find((c) => c.text === text) ?? null, `коментар «${text}» у сервісі`);
}

test("1: після входу в острівці «Коментарі» з числом відкритих; C відкриває панель; закриті — згорнуті, «Зроблено · Іт.N», без дій", async (t) => {
  const env = await boot(t, { port: 0 });
  await seed(env, SEED);
  const o = await openPreview(env, t);
  const { page } = o;

  const btn = page.locator('.island [data-act="comments"]');
  await btn.waitFor();
  assert.equal(await btn.locator(".isl-count").textContent(), "2", "число відкритих на кнопці");
  assert.equal(await panelOpen(page), false, "панель відкрита до натискання");
  await page.keyboard.press("c");
  assert.equal(await panelOpen(page), true, "C не відкрила панель");
  assert.equal(await btn.getAttribute("aria-pressed"), "true");
  const open = await until(async () => { const c = await cards(page); return c.length === 2 ? c : null; }, "дві відкриті картки");
  assert.deepEqual(open.map((c) => c.id).sort(), ["seed-open", "seed-open-2"]);

  // закриті — у згорнутому розділі «Закриті»
  const fold = page.locator('#cmt-panel [data-act="cmtsec"][data-val="closed"]');
  assert.match(await fold.textContent(), /Закриті \(1\)/);
  assert.equal(await fold.getAttribute("aria-expanded"), "false");
  assert.equal((await cards(page)).length, 2, "закриті видно до розгортання");
  await fold.click();
  const all = await cards(page);
  const closed = all.find((c) => c.id === "seed-closed");
  assert.ok(closed, "закрита картка не розгорнулась");
  assert.equal(closed.done, "Зроблено · Іт.2");
  assert.equal(closed.reason, "Кнопку збільшено");
  assert.deepEqual(closed.acts, [], "закрита картка має дії");
  assert.equal(await page.locator('#cmt-panel .cmt-card--closed .cmt-acts').count(), 0, "порожній рядок дій у закритій");
  if (shots) await page.screenshot({ path: path.join(shots, "cmt.png") });

  await page.keyboard.press("c");
  assert.equal(await panelOpen(page), false, "друга C не закрила панель");
  assert.deepEqual(o.errors, []);
  assert.deepEqual(o.outside, [], "запити за межі машини");
});

test("2: імʼя питаємо один раз — лише перед першим додаванням; «Скасувати» не вмикає додавання; потім свій коментар із «Змінити»/«Видалити»", async (t) => {
  const env = await boot(t, { port: 1000 });
  await seed(env, SEED);
  const o = await openPreview(env, t);
  const { page, frame } = o;

  await page.keyboard.press("c");
  // відкриття панелі імені НЕ питає
  assert.equal(await page.locator(".cv-ask--form").count(), 0, "імʼя питали на відкритті панелі");
  assert.equal(await ls(page, USER_KEY), null);

  // «Скасувати»: додавання не вмикається, імʼя не записано
  const add = page.locator('#cmt-panel [data-act="cmtadd"]');
  assert.equal(await add.getAttribute("aria-pressed"), "false");
  await add.click();
  const dlg = page.locator(".cv-ask--form");
  await dlg.waitFor();
  assert.match(await dlg.innerText(), /Як вас підписати в коментарях\?/);
  assert.equal(await dlg.locator("input").count(), 1, "у діалозі одне поле");
  assert.deepEqual(await dlg.locator("button").allTextContents(), ["Скасувати", "Зберегти"]);
  if (shots) await page.screenshot({ path: path.join(shots, "name.png") });
  await page.click('.cv-ask--form button[data-a="cancel"]');
  await dlg.waitFor({ state: "detached" });
  assert.equal(await frame.evaluate(() => !!window.CommentLayer.commentMode), false, "скасування увімкнуло додавання");
  assert.equal(await add.getAttribute("aria-pressed"), "false");
  assert.equal(await ls(page, USER_KEY), null, "скасування записало імʼя");

  // порожнє імʼя діалог не приймає
  await add.click();
  await dlg.waitFor();
  await page.click('.cv-ask--form button[data-a="ok"]');
  assert.equal(await dlg.count(), 1, "діалог закрився з порожнім імʼям");
  assert.equal(await frame.evaluate(() => !!window.CommentLayer.commentMode), false);
  await page.click('.cv-ask--form button[data-a="cancel"]');
  await dlg.waitFor({ state: "detached" });

  // «Зберегти»: імʼя записано, додавання ввімкнене, коментар збережено
  const row = await addComment(o, env, "Мій перший коментар", { name: "Тест Тестович" });
  assert.equal(row.author, "Тест Тестович");
  assert.equal(await ls(page, USER_KEY), "Тест Тестович");
  assert.ok(JSON.parse(await ls(page, OWN_KEY)).includes(row.id), "id створеного коментаря не записано як «мій»");
  const mine = await until(async () => (await cards(page)).find((c) => c.id === row.id) ?? null, "своя картка в панелі");
  assert.deepEqual(mine.acts, ["cmtshow", "cmtedit", "cmtdel"], "своя картка: Показати/Змінити/Видалити, без «Закрити»");

  // другий раз — без діалогу
  if (await add.getAttribute("aria-pressed") === "true") await add.click();
  await until(async () => (await add.getAttribute("aria-pressed")) === "false", "додавання вимкнено");
  await add.click();
  await sleep(500);
  assert.equal(await page.locator(".cv-ask--form").count(), 0, "імʼя спитали вдруге");
  await until(async () => (await add.getAttribute("aria-pressed")) === "true", "додавання знову ввімкнено без діалогу");
  assert.equal(await frame.evaluate(() => !!window.CommentLayer.commentMode), true);

  assert.deepEqual(await prompts(o), { shell: [], frame: [] }, "prompt() викликали");
  assert.deepEqual(o.errors, []);
  assert.deepEqual(o.outside, [], "запити за межі машини");
});

test("3: чужий коментар (посіяний, інший браузер) — лише «Показати»: ні змінити, ні видалити, ні закрити, ні повернути, ні доручити", async (t) => {
  const env = await boot(t, { port: 2000 });
  await seed(env, [...SEED, { id: "seed-same-name", author: "Тест", text: "Те саме імʼя, інший браузер" }]);
  const o = await openPreview(env, t);
  const { page } = o;
  await page.evaluate(([k, v]) => localStorage.setItem(k, v), [USER_KEY, "Тест"]);   // імʼя збігається з автором чужого — «свій» від імені не залежить
  await page.keyboard.press("c");
  await page.locator('#cmt-panel [data-act="cmtsec"][data-val="closed"]').click();
  const all = await until(async () => { const c = await cards(page); return c.length === 4 ? c : null; }, "усі картки (3 відкриті + 1 закрита)");
  for (const c of all) {
    const allowed = c.closed ? [] : ["cmtshow"];
    assert.deepEqual(c.acts, allowed, `картка ${c.id}: дозволено лише ${JSON.stringify(allowed)}`);
  }
  const forbidden = ["cmtedit", "cmtdel", "cmtres", "cmtreopen", "cmtassign", "cmtunassign", "cmtcarry", "cmtfilter"];
  for (const act of forbidden) assert.equal(await page.locator(`#cmt-panel [data-act="${act}"]`).count(), 0, `у панелі є «${act}»`);
  assert.equal(await page.locator("#cmt-panel .cmt-aud, #cmt-panel .cmt-filter").count(), 0, "чипи/фільтр адресатів у превʼю");

  // «Показати» працює
  await page.locator('#cmt-panel [data-act="cmtshow"][data-val="seed-open"]').click();
  assert.equal(await page.locator('#cmt-panel .cmt-card--sel').count(), 1);

  // навіть напряму: підроблена кнопка з дією ЧУЖОГО коментаря (закрити — дії нема в реєстрі; видалити/змінити — дія є, але чуже)
  const fake = (act, val) => page.evaluate(([a, v]) => {
    const b = document.createElement("button");
    b.dataset.act = a; b.dataset.val = v;
    document.body.appendChild(b);
    b.click();
    b.remove();
  }, [act, val]);
  await fake("cmtres", "seed-open");
  await fake("cmtdel", "seed-open");
  assert.equal(await page.locator("#cmt-panel .cfm").count(), 0, "для чужого коментаря показано питання «Видалити»");
  await fake("cmtdelyes", "seed-open");
  await fake("cmtedit", "seed-open");
  assert.equal(await page.locator("#cmt-panel textarea.cmt-edit").count(), 0, "чужий коментар перейшов у редагування");
  await fake("cmteditsave", "seed-open");
  await sleep(600);
  const stored = env.memo.store.get(CHANNEL);
  assert.equal(stored.find((c) => c.id === "seed-open").status, "open", "чужий коментар закрито підробленою дією");
  assert.equal(stored.length, 4, "чужий коментар видалено підробленою дією");
  assert.deepEqual(o.outside, []);
});

test("4: свій коментар змінюється й видаляється (інлайн-підтвердження); зміна й видалення доходять до сервісу", async (t) => {
  const env = await boot(t, { port: 3000 });
  await seed(env, SEED);
  const o = await openPreview(env, t);
  const { page } = o;
  const row = await addComment(o, env, "Спершу так", { name: "Автор" });
  const card = page.locator(`#cmt-panel .cmt-card[data-cid="${row.id}"]`);
  await card.waitFor();

  // зміна
  await card.locator('[data-act="cmtedit"]').click();
  const ta = card.locator("textarea.cmt-edit");
  await ta.fill("Потім інакше");
  await card.locator('[data-act="cmteditsave"]').click();
  await until(() => (env.memo.store.get(CHANNEL) ?? []).find((c) => c.id === row.id)?.text === "Потім інакше", "зміна в сервісі");
  assert.equal(await card.locator(".cmt-text").textContent(), "Потім інакше");

  // скасувати питання «Видалити» — нічого не видаляє
  await card.locator('[data-act="cmtdel"]').click();
  await card.locator(".cfm").waitFor();
  await card.locator('[data-act="cmtdelno"]').click();
  assert.equal(await card.locator(".cfm").count(), 0);
  assert.ok((env.memo.store.get(CHANNEL) ?? []).some((c) => c.id === row.id), "«Скасувати» видалило коментар");

  // видалення
  await card.locator('[data-act="cmtdel"]').click();
  await card.locator('[data-act="cmtdelyes"]').click();
  await until(() => !(env.memo.store.get(CHANNEL) ?? []).some((c) => c.id === row.id), "видалення в сервісі");
  await until(async () => (await page.locator(`#cmt-panel .cmt-card[data-cid="${row.id}"]`).count()) === 0, "картка зникла");
  assert.deepEqual(o.errors, []);
  assert.deepEqual(o.outside, []);
});

test("5: window.prompt підмінено кидком у ОБОХ вікнах — нікого не викликають, навіть коли коментатор у рамці сам лишився без імені", async (t) => {
  const env = await boot(t, { port: 4000 });
  await seed(env, SEED);
  const o = await openPreview(env, t);
  const { page, frame } = o;
  assert.equal(await page.evaluate(() => typeof window.__prompts), "object", "свідок: підміна є в обгортці");
  assert.equal(await frame.evaluate(() => typeof window.__prompts), "object", "свідок: підміна є в рамці");

  // повний шлях через оболонку
  await addComment(o, env, "Через діалог оболонки", { name: "Оболонка" });
  assert.deepEqual(await prompts(o), { shell: [], frame: [] });

  // коментатор у рамці в обхід оболонки й без імені (localStorage порожній, оболонка імені не дала): «Anonymous», prompt() — ні
  await page.evaluate((k) => { localStorage.removeItem(k); window.__dcPreviewUser = ""; }, USER_KEY);
  await frame.evaluate(() => { window.CommentLayer.setCommentMode(false); });
  await frame.evaluate(() => window.CommentLayer.setCommentMode(true));
  await frame.locator("h1").click();
  const ta = frame.locator("[data-comment-layer] .compose textarea");
  await ta.waitFor();
  await ta.fill("Без імені");
  await frame.locator("[data-comment-layer] .compose .save").click();
  const anon = await until(() => (env.memo.store.get(CHANNEL) ?? []).find((c) => c.text === "Без імені") ?? null, "коментар без імені");
  assert.equal(anon.author, "Anonymous");
  assert.equal(await ls(page, USER_KEY), null, "«Anonymous» запамʼятали — оболонка вже не спитає імені");
  assert.deepEqual(await prompts(o), { shell: [], frame: [] }, "prompt() викликали");
  assert.deepEqual(o.errors, []);
});

test("6: перехід рамки на іншу сторінку скидає старі картки, доки нова сторінка не надішле свій список", async (t) => {
  const env = await boot(t, { port: 5000 });
  await seed(env, SEED);
  const o = await openPreview(env, t);
  const { page } = o;
  await page.keyboard.press("c");
  await until(async () => (await cards(page)).length === 2, "картки першої сторінки");

  // нову сторінку тримаємо в дорозі — і дивимось, що панель не показує карток старої
  let release;
  const gate = new Promise((done) => { release = done; });
  await o.ctx.route(/\/it1\/poshuk\/index\.html$/, async (route) => { await gate; await route.continue(); });
  await page.locator('#pages-panel .row', { hasText: "Пошук" }).first().click();
  await until(async () => (await cards(page)).length === 0, "картки старої сторінки скинуто на початку переходу");
  assert.match(await page.locator("#cmt-panel .cmt-body").innerText(), /завантажується/);
  assert.equal(await page.locator('#cmt-panel [data-act="cmtdel"], #cmt-panel [data-act="cmtedit"]').count(), 0);
  release();
  await until(async () => (await cards(page)).length === 2, "картки нової сторінки після її ready");

  // перехід САМОЇ рамки на документ без коментатора (посилання всередині макета): картки знімаємо на `load`
  await o.ctx.unroute(/\/it1\/poshuk\/index\.html$/);
  await page.evaluate((u) => { document.getElementById("frame").contentWindow.location.assign(u); }, `${env.base}/manifest.json`);
  await until(async () => (await cards(page)).length === 0, "картки скинуто, коли рамка пішла на документ без коментатора");
  assert.deepEqual(o.outside, []);
});

test("7: особа машини дизайнера не їде в превʼю: у сторінках і в живому коментаторі нема defaultUser", async (t) => {
  const env = await boot(t, { port: 6000 });
  await seed(env, SEED);
  for (const p of ["it1/holovna/index.html", "it1/poshuk/index.html", "manifest.json", "index.html"]) {
    const txt = await (await fetch(`${env.base}/${p}`)).text();
    assert.equal(txt.includes("defaultUser"), false, `${p} несе defaultUser`);
  }
  const html = readFileSync(path.join(env.out, "it1", "holovna", "index.html"), "utf8");
  assert.ok(html.includes("userName: function") && html.includes("onAdd: function"), "свідок: сторінка в режимі хоста превʼю");
  const o = await openPreview(env, t);
  assert.equal(await o.frame.evaluate(() => window.CommentLayer.opts && window.CommentLayer.opts.defaultUser), undefined);
  assert.equal(await o.frame.evaluate(() => typeof (window.CommentLayer.opts.host || {}).userName), "function");
  assert.deepEqual(o.outside, []);
});

test("8: збірка без командних коментарів — ні кнопки «Коментарі», ні панелі, ні помилок", async (t) => {
  const env = await boot(t, { enable: false, port: 7000 });
  const man = await (await fetch(`${env.base}/manifest.json`)).json();
  assert.equal("comments" in man, false, "маніфест без коментарів несе ключ comments");
  const ctx = await browser.newContext({ viewport: VIEW });
  t.after(() => ctx.close());
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await enter(page, env);
  await page.locator(".island").waitFor();
  assert.equal(await page.locator('.island [data-act="comments"]').count(), 0, "кнопка «Коментарі» без коментарів у збірці");
  await page.keyboard.press("c");
  assert.equal(await panelOpen(page), false, "C відкрила панель без коментарів у збірці");
  assert.equal(await page.locator("#cmt-panel .cmt-card, #cmt-panel .cmt-top").count(), 0);
  assert.equal(await page.evaluate(() => document.body.classList.contains("with-cmt")), false);
  assert.deepEqual(errors, []);
});

const PIXEL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";
const preName = ([k, v]) => { try { localStorage.setItem(k, v); } catch { /* пісочниця */ } };
const mode = (frame) => frame.evaluate(() => !!window.CommentLayer.commentMode);

test("10: імʼя вже збережене — відкрита панель вмикає додавання, як у Deai: клік по макету створює пін без жодного діалогу", async (t) => {
  const env = await boot(t, { port: 8000 });
  await seed(env, SEED);
  const o = await openPreview(env, t, { init: preName, initArg: [USER_KEY, "Збережене Імʼя"] });
  const { page, frame } = o;
  assert.equal(await mode(frame), false, "додавання ввімкнене до відкриття панелі");
  await page.keyboard.press("c");
  await until(() => mode(frame), "відкрита панель з відомим імʼям не ввімкнула додавання");
  const add = page.locator('#cmt-panel [data-act="cmtadd"]');
  assert.equal(await add.getAttribute("aria-pressed"), "true");
  await frame.locator("h1").click();
  const ta = frame.locator("[data-comment-layer] .compose textarea");
  await ta.waitFor();
  await ta.fill("Без діалогу");
  await frame.locator("[data-comment-layer] .compose .save").click();
  const row = await until(() => (env.memo.store.get(CHANNEL) ?? []).find((c) => c.text === "Без діалогу") ?? null, "коментар у сервісі");
  assert.equal(row.author, "Збережене Імʼя");
  assert.equal(await page.locator(".cv-ask--form").count(), 0, "імʼя спитали, хоч воно збережене");
  // «+» — перемикач: вимикає додавання, щоб клацати макет
  await until(async () => (await add.getAttribute("aria-pressed")) === "true" || !(await mode(frame)), "стан після створення");
  if (await mode(frame)) { await add.click(); }
  await until(async () => !(await mode(frame)) && (await add.getAttribute("aria-pressed")) === "false", "«+» вимикає додавання");
  assert.deepEqual(await prompts(o), { shell: [], frame: [] });
  assert.deepEqual(o.errors, []);
});

test("11: імені нема — панель лише читає; «+» питає імʼя ОДИН раз; далі відкриття панелі вмикає додавання одразу", async (t) => {
  const env = await boot(t, { port: 9000 });
  await seed(env, []);
  const o = await openPreview(env, t);
  const { page, frame } = o;
  await page.keyboard.press("c");
  const add = page.locator('#cmt-panel [data-act="cmtadd"]');
  await add.waitFor();
  assert.equal(await mode(frame), false, "без імені панель увімкнула додавання");
  assert.equal(await add.getAttribute("aria-pressed"), "false");
  assert.match(await page.locator("#cmt-panel .cmt-body").innerText(), /Натисніть «\+», щоб залишити коментар\./);
  await add.click();
  await page.locator(".cv-ask--form").waitFor();
  await page.fill('.cv-ask--form input[name="name"]', "Нова Людина");
  await page.click('.cv-ask--form button[data-a="ok"]');
  await until(() => mode(frame), "після імені додавання не ввімкнулось");
  assert.match(await page.locator("#cmt-panel .cmt-body").innerText(), /Натисніть на макет, щоб залишити\./);
  // закрити й відкрити: імʼя є — арм одразу, діалогу нема
  await page.keyboard.press("c");
  await until(async () => !(await mode(frame)), "закриття панелі не вимкнуло додавання");
  await page.keyboard.press("c");
  await until(() => mode(frame), "повторне відкриття не ввімкнуло додавання");
  assert.equal(await page.locator(".cv-ask--form").count(), 0, "імʼя спитали вдруге");
  assert.deepEqual(await prompts(o), { shell: [], frame: [] });
  assert.deepEqual(o.errors, []);
});

test("12: localStorage недоступний у обох вікнах — коментар підписано введеним імʼям, не «Anonymous»; prompt не кличеться", async (t) => {
  const env = await boot(t, { port: 10000 });
  await seed(env, []);
  const o = await openPreview(env, t, { init: () => {
    Object.defineProperty(window, "localStorage", { configurable: true, get() { throw new DOMException("blocked", "SecurityError"); } });
  } });
  const row = await addComment(o, env, "З блокованим сховищем", { name: "Без Сховища" });
  assert.equal(row.author, "Без Сховища");
  assert.deepEqual(await prompts(o), { shell: [], frame: [] });
});

test("13: старе «Anonymous» у сховищі — не імʼя: панель не армиться, «+» питає, діалог без передзаповнення", async (t) => {
  const env = await boot(t, { port: 11000 });
  await seed(env, []);
  const o = await openPreview(env, t, { init: preName, initArg: [USER_KEY, "Anonymous"] });
  const { page, frame } = o;
  await page.keyboard.press("c");
  await sleep(500);
  assert.equal(await mode(frame), false, "«Anonymous» прийняли за імʼя");
  await page.locator('#cmt-panel [data-act="cmtadd"]').click();
  await page.locator(".cv-ask--form").waitFor();
  assert.equal(await page.inputValue('.cv-ask--form input[name="name"]'), "");
});

test("14: «C» у макеті в чистому вигляді не відкриває панель і не повертає інтерфейс", async (t) => {
  const env = await boot(t, { port: 12000 });
  await seed(env, SEED);
  const o = await openPreview(env, t);
  const { page, frame } = o;
  await page.keyboard.press("ControlOrMeta+Shift+Backslash");
  await until(() => page.evaluate(() => document.documentElement.classList.contains("cv-clean")), "чистий вигляд");
  await frame.locator("h1").click();
  await page.keyboard.press("c");
  await sleep(400);
  assert.equal(await panelOpen(page), false, "C у рамці відкрила панель у чистому вигляді");
  assert.equal(await page.evaluate(() => document.documentElement.classList.contains("cv-clean")), true, "чистий вигляд скасовано");
});

test("15: картка зі знімком — кнопка «cmtshot» відкриває знімок у коментаторі; зміна «свого» бере id зі стану, а не з кнопки", async (t) => {
  const env = await boot(t, { port: 13000 });
  const rows = await seed(env, SEED);
  rows[0].meta.shotUrl = PIXEL;
  env.memo.store.set(CHANNEL, rows);
  const o = await openPreview(env, t);
  const { page, frame } = o;
  await page.keyboard.press("c");
  const shot = page.locator('#cmt-panel [data-act="cmtshot"][data-val="seed-open"]');
  await shot.waitFor();
  await shot.click();
  await frame.locator("[data-comment-layer] .cllb").waitFor();
  await frame.locator("[data-comment-layer] .cllb").click();    // закрити знімок: він накриває макет
  await frame.locator("[data-comment-layer] .cllb").waitFor({ state: "detached" });

  const row = await addComment(o, env, "Свій для підробки", { name: "Автор" });
  const card = page.locator(`#cmt-panel .cmt-card[data-cid="${row.id}"]`);
  await card.waitFor();
  await card.locator('[data-act="cmtedit"]').click();
  await card.locator("textarea.cmt-edit").fill("Підроблене збереження");
  await page.evaluate(() => {
    const b = document.createElement("button");
    b.dataset.act = "cmteditsave"; b.dataset.val = "seed-open";
    document.body.appendChild(b); b.click(); b.remove();
  });
  await until(() => (env.memo.store.get(CHANNEL) ?? []).find((c) => c.id === row.id)?.text === "Підроблене збереження", "збережено id зі стану");
  assert.equal(env.memo.store.get(CHANNEL).find((c) => c.id === "seed-open").text, "Кнопка зливається з фоном", "чужий коментар змінено");
});

test("16: панель відкрито, коли рамка ще вантажиться, а імʼя відоме — додавання вмикається на `ready` рамки", async (t) => {
  const env = await boot(t, { port: 14000 });
  await seed(env, SEED);
  let release;
  const gate = new Promise((done) => { release = done; });
  const o = await openPreview(env, t, { init: preName, initArg: [USER_KEY, "Рано"], early: true });
  /* Рамка вже стартувала (оболонка її створює при вході); тримаємо лише ПЕРЕХІД на іншу сторінку — і відкриваємо панель
     посеред нього: коментатора в рамці ще нема. */
  const { page } = o;
  await o.ctx.route(/\/it1\/poshuk\/index\.html$/, async (route) => { await gate; await route.continue(); });
  await page.locator('#pages-panel .row', { hasText: "Пошук" }).first().click();
  await page.keyboard.press("c");
  assert.equal(await panelOpen(page), true);
  release();
  const frame = await until(() => page.frames().find((f) => /\/it1\/poshuk\/index\.html$/.test(f.url())) ?? null, "рамка нової сторінки");
  await until(() => frame.evaluate(() => !!(window.CommentLayer && window.CommentLayer._inited)).catch(() => false), "коментатор нової сторінки");
  await until(() => mode(frame), "відкладене додавання не ввімкнулось на ready");
  assert.equal(await page.locator('#cmt-panel [data-act="cmtadd"]').getAttribute("aria-pressed"), "true");
});

test("99: ізоляція — жодного запиту за межі машини, справжній ~/.deai не зачеплено", () => {
  assert.deepEqual(OUTSIDE, [], `запити за межі машини:\n${OUTSIDE.join("\n")}`);
  guardRealDeai();
});
