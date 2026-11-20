/**
 * Б2 «Claude і команда разом» (Deai 0.27.0, Task 12) — живі сценарії робочого місця: адресат, колір піна, фільтр, доручення,
 * «нові від команди», число на вкладці, падіння командного, сторінка без `host`.
 *
 * Оточення — як у `comments.test.mjs`: простір `mod` із модулем `memo-comments` (сервіс `memo`, `_memo.mjs`), задача з двома
 * сторінками (`t45Task`), справжній сервер у ізольованій «машині», справжній Chromium; усе поза 127.0.0.1 — `abort`.
 * Рамка робочого місця несе `host=1` і КОМБІНОВАНЕ сховище (локальний файл задачі + `memo`); панель і острівець — оболонка.
 *
 * Мапа «сценарій → запобіжник» (мутації — у звіті T12):
 *   1 адресат і памʼять вибору — чипи коментатора, `host.defaultAudience/onAudiencePick` (`serve.py`/`app.js`), `_aud` не на диску;
 *   2 колір — `audiences[i].color` (`DUAL_AUDIENCES_JS`) → `_audColor`/`data-aud` у коментаторі;
 *   3 фільтр — `commentSections({filter})` + `cmtfilter` (`app.js`), підлога 28px сегмента;
 *   4 доручення — `cmtassign` → `setMeta(assignee)`, маршрут `/comments` (`for_agent`, `hidden`, `?all=1`);
 *   5 нові від команди — маркер `dc-seen:*` (набір id), `cmtNewsUpdate`, острівець/тост/дерево, `setCommentsOpen` посуває маркер;
 *   6 свій пін не «новий»;
 *   7 число на вкладці — `pollTabNews` (поріг 30 с, примусовий опит при зміні складу вкладок);
 *   8 падіння командного — `teamDown` комбінованого сховища; банера `__clDown` нема, локальне працює;
 *   9 без `host` — сторінка каналу як у 0.26.0, без комбінованого сховища.
 *
 * ⛔ Лише Playwright Chromium (панель Browser застосунку Claude блокує частину скриптів пісочниці).
 */
// 4d-4b: кеш браузерів Playwright читається при ІМПОРТІ playwright — `_env.mjs` мусить бути раніше за нього
import "./_env.mjs";
import assert from "node:assert/strict";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { userInfo } from "node:os";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { startServer } from "./fixture.mjs";
import { startMemo } from "./_memo.mjs";
import { ANCHOR, t45Task } from "./_t45-fixture.mjs";
import { VIEW, postJson, sleep, stop, guardRealDeai } from "./_spaces-kit.mjs";

const PORT_BASE = 27000;
const MODULE = "memo-comments";
const SPACE = "mod";
const CDN = "cdn.jsdelivr.net";
const LOCAL_RGB = "rgb(124, 108, 240)";
const channelOf = (task) => `deai/${SPACE}/${task}`;

const isLocal = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

function browsersPath() {
  if (process.env.PLAYWRIGHT_BROWSERS_PATH) return process.env.PLAYWRIGHT_BROWSERS_PATH;
  const home = userInfo().homedir;
  if (process.platform === "darwin") return path.join(home, "Library", "Caches", "ms-playwright");
  if (process.platform === "win32") return path.join(process.env.LOCALAPPDATA || path.join(home, "AppData", "Local"), "ms-playwright");
  return path.join(process.env.XDG_CACHE_HOME || path.join(home, ".cache"), "ms-playwright");
}

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

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

/** Сервер + `memo` + контекст + сторінка оболонки (ще не відкрита). `tasks` — id задач простору (перша — поточна). */
async function boot(t, { tasks = ["fixture"], enable = true } = {}) {
  const memo = await startMemo();
  t.after(() => memo.close());
  const dirs = {};
  for (const id of tasks) dirs[id] = t45Task().dir;
  const server = await startServer(null, {
    portBase: PORT_BASE,
    spaces: [{ name: "Mod", id: SPACE, color: "space-3", tasks: Object.fromEntries(tasks.map((id) => [id, { dir: dirs[id], title: `Задача ${id}` }])) }],
    env: { DEAI_EXTRA_MODULES: path.resolve("tests/fixtures/modules"), PLAYWRIGHT_BROWSERS_PATH: browsersPath() },
  });
  t.after(() => stop(server.child));
  if (enable) {
    const en = await (await postJson(server.url, "/api/module-enable", {
      space: SPACE, id: MODULE, settings: { endpoint: memo.url }, secrets: { token: "TOKEN-PRIVATE", pubkey: "PUBKEY" },
    })).json();
    assert.equal(en.ok, true, `module-enable: ${JSON.stringify(en)}`);
  }
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const outside = [];
  context.on("request", (r) => { if (!isLocal(r.url()) && new URL(r.url()).hostname !== CDN) outside.push(r.url()); });
  await context.route((u) => !isLocal(u.href), (route) => (new URL(route.request().url()).hostname === CDN
    ? route.fulfill({ status: 200, contentType: "application/javascript", body: "" }) : route.abort("blockedbyclient")));
  const errors = [];
  context.on("page", (p) => p.on("pageerror", (e) => errors.push(String(e.message ?? e))));
  const page = await context.newPage();
  /* Спільний детектор для КОЖНОГО сценарію: витік за межі машини й помилки сторінки не мусять з'являтись нізвідки. */
  t.after(() => {
    assert.deepEqual(outside, [], "запити поза машиною");
    assert.deepEqual(errors, [], errors.join("\n"));
  });
  return { ...server, memo, context, page, dirs, outside, errors };
}

const frameOf = async (page) => (await (await page.$("#frame")).contentFrame());
const SHADOW = "document.querySelector('[data-comment-layer]').shadowRoot";

/** Оболонку відкрито, рамка підняла шар коментатора (і він готовий до режиму хоста). */
async function openShell(env) {
  await env.page.goto(`${env.url}/app/`);
  await env.page.waitForSelector('#hud [data-act="comments"]');
  const frame = await frameOf(env.page);
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  return frame;
}
const openPanel = async (page) => {
  await page.click('#hud [data-act="comments"]');
  await page.waitForSelector("#cmt-panel:not([hidden]) .cmt-card, #cmt-panel:not([hidden]) .insp-hint, #cmt-panel:not([hidden]) .cmt-sec");
  await until(() => page.evaluate(() => !!document.getElementById("frame").contentWindow.CommentLayer?.tool?.()?.armed), "коментування ввімкнено");
};
const cardIds = (page) => page.$$eval("#cmt-panel .cmt-card", (els) => els.map((e) => e.dataset.cid));
const lsGet = (page, k) => page.evaluate((key) => localStorage.getItem(key), k);
const lsKeys = (page) => page.evaluate(() => Object.keys(localStorage));

/** Відбиток цілі: справжній `CommentLayerAnchor.fingerprint` у bare-сторінці (як `seedPin` у `comments.test.mjs`). */
async function fpOf(env, pageId, sel) {
  const bare = await env.context.newPage();
  await bare.goto(`${env.url}/commented?it=it1&page=${pageId}&bare=1`);
  await bare.addScriptTag({ content: ANCHOR });
  const fp = await bare.evaluate((s) => window.CommentLayerAnchor.fingerprint(document.querySelector(s), document.body), sel);
  await bare.close();
  return fp;
}
const pinRow = (env, { id, author, text, pageId = "holovna", seq = 1, fp, replies }) => ({
  id, author, text, status: "open", fp, htmlSnapshot: null, bornV: 1, ts: "14.11.2026 12:00", ...(replies ? { replies } : {}),
  meta: { url: `${env.url}/commented?it=it1&page=${pageId}`, route: "/commented", version: `1/${pageId}`, iteration: "1",
    viewport: { w: 1280, h: 900 }, seq },
});
/** Командний пін прямо в `memo` (канал задачі). */
async function seedTeam(env, spec, task = "fixture") {
  const fp = spec.fp ?? await fpOf(env, spec.pageId ?? "holovna", spec.sel ?? "[data-testid=subscribe]");
  const row = pinRow(env, { ...spec, fp });
  env.memo.store.set(channelOf(task), [...(env.memo.store.get(channelOf(task)) ?? []), row]);
  return row;
}
/** Локальний пін через справжній ендпоінт (як `seedPins`): файл задачі. */
async function seedLocal(env, spec) {
  const fp = await fpOf(env, spec.pageId ?? "holovna", spec.sel ?? "h1");
  const row = pinRow(env, { ...spec, fp });
  const r = await fetch(`${env.url}/api/local-comments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comments: [row] }) });
  assert.ok(r.ok, `посів локального піна: ${r.status}`);
  return row;
}
const localFile = (env, task = "fixture") => path.join(env.dirs[task], ".dc-local-comments.json");
const localList = (env, task = "fixture") => (existsSync(localFile(env, task)) ? JSON.parse(readFileSync(localFile(env, task), "utf8")) : []);

/** Створити пін живою формою коментатора у рамці. `pick` — id чипа адресата (або `null` — як є). */
async function addPin(frame, sel, text, pick = null) {
  await frame.click(sel);
  await frame.waitForFunction(`!!${SHADOW}.querySelector('.compose textarea')`);
  if (pick) await frame.evaluate((p) => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(`.compose .caud-b[data-pick="${p}"]`).click(), pick);
  await frame.evaluate((tx) => {
    const r = document.querySelector("[data-comment-layer]").shadowRoot;
    const ta = r.querySelector(".compose textarea");
    ta.value = tx; ta.dispatchEvent(new Event("input", { bubbles: true }));
    r.querySelector(".compose .save").click();
  }, text);
}
const chips = (frame) => frame.evaluate(() => [...document.querySelector("[data-comment-layer]").shadowRoot.querySelectorAll(".compose .caud-b")]
  .map((b) => [b.dataset.pick, b.getAttribute("aria-pressed")]));

/* ── 1: адресат і памʼять вибору ──────────────────────────────────────────────────────────────────── */

test("1: форма має два чипи (Claude типово), «Команді» шле пін у memo без _aud і не на диск, вибір запамʼятовано", async (t) => {
  const env = await boot(t);
  const { page, memo } = env;
  const frame = await openShell(env);
  await openPanel(page);

  await frame.click("h1");
  await frame.waitForFunction(`!!${SHADOW}.querySelector('.compose textarea')`);
  assert.deepEqual(await chips(frame), [["local", "true"], ["project", "false"]], "типово — Claude, чипів рівно два");
  // Під «AI» підпису нема: власник 16.11.2026 — підписи, про які не просили, загромождають форму.
  assert.equal(await frame.evaluate(`${SHADOW}.querySelector('.compose .caud-note')?.textContent ?? ""`), "", "під «AI» зʼявився підпис");
  await frame.evaluate(`${SHADOW}.querySelector('.compose .caud-b[data-pick="project"]').click()`);
  assert.deepEqual(await chips(frame), [["local", "false"], ["project", "true"]]);
  assert.ok((await frame.evaluate(`${SHADOW}.querySelector('.compose .caud-note').textContent`)).length > 0, "нема рядка-примітки «команда бачить це в превʼю»");
  await frame.evaluate(() => {
    const r = document.querySelector("[data-comment-layer]").shadowRoot;
    const ta = r.querySelector(".compose textarea");
    ta.value = "Для команди"; ta.dispatchEvent(new Event("input", { bubbles: true }));
    r.querySelector(".compose .save").click();
  });

  const row = await until(() => (memo.store.get(channelOf("fixture")) ?? []).find((c) => c.text === "Для команди") ?? null, "пін у memo");
  assert.equal("_aud" in row, false, "службове поле _aud потрапило в командне сховище");
  await sleep(600);
  assert.deepEqual(localList(env).map((c) => c.text), [], "командний пін потрапив у файл задачі");
  assert.equal(await lsGet(page, "dc-cmt-aud"), "project", "вибір адресата не запамʼятовано");

  /* друга форма — вже «Команді» */
  await frame.waitForFunction(`!${SHADOW}.querySelector('.compose textarea')`);
  await frame.click(".card:nth-child(2) h2");
  await frame.waitForFunction(`!!${SHADOW}.querySelector('.compose textarea')`);
  assert.deepEqual(await chips(frame), [["local", "false"], ["project", "true"]], "друга форма не памʼятає вибір");
  assert.deepEqual(env.outside, []);
  assert.deepEqual(env.errors, [], env.errors.join("\n"));
});

/* ── 2: колір ─────────────────────────────────────────────────────────────────────────────────────── */

test("2: локальний пін фіолетовий з data-aud=local, командний — іншого кольору", async (t) => {
  const env = await boot(t);
  const local = await seedLocal(env, { id: "loc-1", author: "Фікстура", text: "Локальний" });
  const team = await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний", sel: "[data-testid=subscribe]", seq: 2 });
  const frame = await openShell(env);
  const pins = await until(async () => {
    const r = await frame.evaluate(() => [...document.querySelector("[data-comment-layer]").shadowRoot.querySelectorAll(".pin")]
      .map((p) => ({ aud: p.dataset.aud ?? null, bg: getComputedStyle(p).backgroundColor, text: p.textContent.trim() })));
    return r.length >= 2 ? r : null;
  }, "два піни в рамці");
  const byAud = Object.fromEntries(pins.map((p) => [p.aud, p]));
  assert.equal(byAud.local?.bg, LOCAL_RGB, `локальний пін: ${JSON.stringify(pins)}`);
  assert.ok(byAud.project, `командний пін без data-aud=project: ${JSON.stringify(pins)}`);
  assert.notEqual(byAud.project.bg, LOCAL_RGB, "командний пін теж фіолетовий");
  assert.ok(local.id && team.id);
});

/* ── 3: фільтр ────────────────────────────────────────────────────────────────────────────────────── */

test("3: фільтр «Усі / Claude / Команда» — картки, висота ≥ 28px, вибір переживає перезавантаження", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await seedLocal(env, { id: "loc-1", author: "Фікстура", text: "Локальний" });
  await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний", seq: 2 });
  await openShell(env);
  await openPanel(page);
  const press = async (val) => { await page.click(`#cmt-panel [data-act="cmtfilter"][data-val="${val}"]`); };
  /* 0.27.1: типова вкладка — «Для AI» (недоручений командний там не видно), тож «обидві» — на вкладці «Усі». */
  await press("all");
  await until(async () => (await cardIds(page)).length === 2, "обидві картки");

  await press("local");
  await until(async () => JSON.stringify(await cardIds(page)) === '["loc-1"]', "лише локальна картка");
  await press("project");
  await until(async () => JSON.stringify(await cardIds(page)) === '["team-1"]', "лише командна картка");
  await press("all");
  await until(async () => (await cardIds(page)).length === 2, "обидві картки знову");
  const heights = await page.$$eval('#cmt-panel [data-act="cmtfilter"]', (els) => els.map((e) => e.getBoundingClientRect().height));
  assert.equal(heights.length, 3);
  for (const h of heights) assert.ok(h >= 28, `кнопка сегмента ${h}px < 28px`);

  await press("project");
  await until(async () => JSON.stringify(await cardIds(page)) === '["team-1"]', "фільтр застосовано");
  await page.reload();
  await page.waitForSelector('#hud [data-act="comments"]');
  await openPanel(page);
  assert.equal(await page.getAttribute('#cmt-panel [data-act="cmtfilter"][data-val="project"]', "aria-pressed"), "true", "фільтр не пережив перезавантаження");
  await until(async () => JSON.stringify(await cardIds(page)) === '["team-1"]', "після перезавантаження — лише командна");
});

/* ── 4: доручення ─────────────────────────────────────────────────────────────────────────────────── */

test("4: «Доручити AI» → meta.assignee у memo, бейдж, /comments бачить пін; «Забрати» — ні (hidden:1), ?all=1 — є", async (t) => {
  const env = await boot(t);
  const { page, memo, url } = env;
  const pin = await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний" });
  await openShell(env);
  await openPanel(page);
  /* 0.27.1: недоручений командний пін не в типовій вкладці «Для AI» — дивимось на вкладці «Команда». */
  await page.click('#cmt-panel [data-act="cmtfilter"][data-val="project"]');
  const card = `#cmt-panel .cmt-card[data-cid="${pin.id}"]`;
  await page.waitForSelector(card);
  assert.equal(await page.locator(`${card} .cmt-badge`).count(), 0);

  /* Маршрут ДО доручення: пін схований від агента. */
  const before = await (await fetch(`${url}/comments?it=it1&channel=project`)).json();
  assert.deepEqual(before.comments, [], "недоручений командний пін видно агентові");
  assert.equal(before.hidden, 1);

  await page.click(`${card} [data-act="cmtassign"]`);
  await until(() => (memo.store.get(channelOf("fixture")) ?? [])[0]?.meta?.assignee === "claude", "meta.assignee у memo");
  await page.waitForSelector(`${card} .cmt-badge`);
  await page.waitForSelector(`${card} [data-act="cmtunassign"]`);
  const on = await (await fetch(`${url}/comments?it=it1&channel=project`)).json();
  assert.deepEqual(on.comments.map((c) => c.id), [pin.id], `маршрут /comments не віддав доручений пін: ${JSON.stringify(on)}`);
  assert.equal(on.hidden, 0);

  await page.click(`${card} [data-act="cmtunassign"]`);
  await until(() => !(memo.store.get(channelOf("fixture")) ?? [])[0]?.meta?.assignee, "meta.assignee знято");
  await page.waitForSelector(`${card} [data-act="cmtassign"]`);
  assert.equal(await page.locator(`${card} .cmt-badge`).count(), 0, "бейдж лишився після «Забрати»");
  const off = await (await fetch(`${url}/comments?it=it1&channel=project`)).json();
  assert.deepEqual(off.comments, []);
  assert.equal(off.hidden, 1);
  const all = await (await fetch(`${url}/comments?it=it1&channel=project&all=1`)).json();
  assert.deepEqual(all.comments.map((c) => c.id), [pin.id], "?all=1 не віддає командний пін");
  /* `bin/inbox.py` тут не запускаємо: він читає реєстр і секрети з `DEAI_HOME` сервера, а ми не виставляємо `DEAI_HOME`
     із тесту (справжній дім не чіпаємо); правило «доручений» спільне з маршрутом (`for_agent`), його стережуть юніти inbox. */
});

/* ── 5, 6: «нові від команди» ────────────────────────────────────────────────────────────────────── */

const newCount = (page) => page.evaluate(() => document.querySelector('#hud [data-act="comments"] .isl-count--new')?.textContent ?? null);
const totalCount = (page) => page.evaluate(() => document.querySelector('#hud [data-act="comments"] .isl-count')?.className ?? null);
const seenKey = (task = "fixture") => `dc-seen:${SPACE}:${task}`;

test("5: пін колеги → «нових» на острівці, плашка, число в дереві; «Показати» → розділ; маркер переживає перезавантаження", async (t) => {
  const env = await boot(t);
  const { page, memo } = env;
  await openShell(env);
  /* База маркера — перший знімок, де відповіла команда. */
  await until(async () => (await lsGet(page, seenKey())) !== null, "маркер-база dc-seen");
  assert.equal(await newCount(page), null);

  const fp = await fpOf(env, "poshuk", "#q");
  memo.store.set(channelOf("fixture"), [pinRow(env, { id: "team-new", author: "Колега", text: "Нове від колеги", pageId: "poshuk", seq: 1, fp })]);

  await until(async () => (await newCount(page)) === "1", "число «нових» на острівці (≤ кілька секунд, memo опитується раз на секунду)", 8000);
  const notice = await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 5000 });
  assert.match(await notice.textContent(), /Новий коментар від Колега/);
  const row = await page.waitForSelector(".row-news", { timeout: 5000 });
  assert.equal((await row.textContent()).trim(), "1");
  assert.match(await row.evaluate((el) => el.closest("[data-val], li, .row")?.textContent ?? ""), /Пошук/, "число в дереві не на сторінці піна");

  await page.click('.cv-notice[data-notice="cmt-news"] [data-act="cmtshownew"]');
  /* 0.27.1: «Показати» з вкладки «Для AI» сам веде на «Команду» — картку видно без ручного перемикання. */
  await page.waitForSelector("#cmt-panel:not([hidden]) .cmt-sec--new .cmt-card");
  assert.equal(await page.getAttribute('#cmt-panel [data-act="cmtfilter"][data-val="project"]', "aria-pressed"), "true", "«Показати» не перемкнув на «Команду»");
  assert.equal(await page.locator("#cmt-panel .cmt-sec--new .cmt-card").count(), 1);
  assert.equal(await newCount(page), null, "бейдж острівця лишився «новим» при відкритій панелі");
  assert.equal(await page.locator('.cv-notice[data-notice="cmt-news"]').count(), 0, "плашка лишилась");
  assert.equal(await page.locator(".row-news").count(), 0, "число в дереві лишилось");

  /* Маркер збережено: після перезавантаження пін — уже не новий. */
  await page.reload();
  await page.waitForSelector('#hud [data-act="comments"]');
  await until(async () => (await totalCount(page)) !== null, "число відкритих на острівці після перезавантаження");
  assert.equal(await totalCount(page), "isl-count", `після перезавантаження пін знову «новий»: ${await totalCount(page)}`);
  await sleep(1500);
  assert.equal(await newCount(page), null);
  assert.equal(await page.locator('.cv-notice[data-notice="cmt-news"]').count(), 0, "плашка зʼявилась на першому знімку після завантаження");
});

test("5б: пін колеги, що прийшов при ВІДКРИТІЙ панелі, одразу «побачений» — після перезавантаження ні бейджа, ні плашки, ні числа в дереві", async (t) => {
  const env = await boot(t);
  const { page, memo } = env;
  await openShell(env);
  await openPanel(page);
  await page.click('#cmt-panel [data-act="cmtfilter"][data-val="project"]');   // 0.27.1: командні — на вкладці «Команда»
  await until(async () => (await lsGet(page, seenKey())) !== null, "маркер-база dc-seen");

  const fp = await fpOf(env, "poshuk", "#q");
  memo.store.set(channelOf("fixture"), [pinRow(env, { id: "team-open", author: "Колега", text: "Прийшов при відкритій панелі", pageId: "poshuk", seq: 1, fp })]);
  await page.waitForSelector("#cmt-panel:not([hidden]) .cmt-sec--new .cmt-card", { timeout: 8000 });

  /* Гілка відкритої панелі мусить сама зберегти маркер (`saveSeen`): інакше після перезавантаження пін знову «новий». */
  await page.reload();
  await page.waitForSelector('#hud [data-act="comments"]');
  await until(async () => (await totalCount(page)) !== null, "число відкритих на острівці після перезавантаження");
  await sleep(1500);
  assert.equal(await newCount(page), null, "бейдж «нових» зʼявився після перезавантаження");
  assert.equal(await page.locator('.cv-notice[data-notice="cmt-news"]').count(), 0, "плашка зʼявилась після перезавантаження");
  assert.equal(await page.locator(".row-news").count(), 0, "число в дереві зʼявилось після перезавантаження");
});

test("6: власний командний пін не «новий» — ні бейджа, ні плашки після закриття панелі", async (t) => {
  const env = await boot(t);
  const { page, memo } = env;
  const frame = await openShell(env);
  await openPanel(page);
  await addPin(frame, "h1", "Мій для команди", "project");
  await until(() => (memo.store.get(channelOf("fixture")) ?? []).some((c) => c.text === "Мій для команди"), "пін у memo");
  await page.click('#hud [data-act="comments"]');             // закрити панель
  await page.waitForSelector("#cmt-panel", { state: "hidden" });
  await until(async () => (await totalCount(page)) === "isl-count", "число відкритих на острівці");
  await sleep(2500);                                          // два періоди опитування memo
  assert.equal(await newCount(page), null, "власний пін став «новим»");
  assert.equal(await page.locator('.cv-notice[data-notice="cmt-news"]').count(), 0, "плашка про власний пін");
  assert.equal(await page.locator(".row-news").count(), 0);
});

/* ── 7: число на вкладці ──────────────────────────────────────────────────────────────────────────── */

test("7: пін колеги в іншій задачі → число на її вкладці (примусовий опит при зміні складу вкладок); перехід гасить", async (t) => {
  const env = await boot(t, { tasks: ["fixture", "second", "third"] });
  const { page, memo } = env;
  await openShell(env);
  const openFromHome = async (id) => {
    await page.click('#tabs [data-act="home"]');
    await page.waitForSelector(`#tasks-home .th-card[data-id="${id}"]`);
    await page.click(`#tasks-home .th-card[data-id="${id}"]`);
    await page.waitForFunction((want) => !!document.querySelector(`#tabs [data-act="tab"][data-val="${want}"][aria-current="page"]`), id);
  };
  await openFromHome("second");                                         // склад вкладок змінився → опит (база для «fixture»)
  /* Примусові опити зливаються хвостовим debounce (~1,5 с): чекаємо САМ раунд опиту «second», а не лише маркер
     (його міг уже записати острівець, коли «second» була активною) — інакше пін додасться до того, як опит візьме основу. */
  const baseRound = page.waitForResponse((r) => r.url().includes("/api/comment-news?task=second"), { timeout: 8000 });
  await page.click('#tabs [data-act="tab"][data-val="fixture"]');       // активна змінилась → опит (база для «second»)
  await baseRound;
  await until(async () => (await lsGet(page, seenKey("second"))) !== null, "маркер-база вкладки second");

  const fp = await fpOf(env, "holovna", "h1");
  memo.store.set(channelOf("second"), [pinRow(env, { id: "team-2", author: "Колега", text: "Для другої", fp })]);

  /* Поріг 30 с: `focus` одразу після бази НЕ опитує. Годинник Playwright тут не береться: він заморозив би й опитування
     адаптера `memo` та інші таймери оболонки — тож проби на «поріг» і «примус» робимо без фальшивого часу. */
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await sleep(1200);
  assert.equal(await page.locator('#tabs [data-act="tab"][data-val="second"] .tab-news').count(), 0, "focus опитав раніше порога в 30 с");

  await openFromHome("third");                                          // склад змінився → примусовий опит
  const badge = '#tabs [data-act="tab"][data-val="second"] .tab-news';
  await page.waitForSelector(badge, { timeout: 8000 });
  assert.equal((await page.textContent(badge)).trim(), "1");

  await page.click('#tabs [data-act="tab"][data-val="second"]');
  await page.waitForFunction((b) => !document.querySelector(b), badge);
});

/* Охоронець поведінки (а не регексу в `comments-wiring`): `render()` без зміни задачі/простору/складу вкладок опиту новин не дає. */
test("7b: кілька render() поспіль без зміни задачі/простору/вкладок — жодного запиту /api/comment-news", async (t) => {
  const env = await boot(t, { tasks: ["fixture", "second"] });
  const { page } = env;
  await openShell(env);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector('#tasks-home .th-card[data-id="second"]');
  const baseRound = page.waitForResponse((r) => r.url().includes("/api/comment-news?task="), { timeout: 8000 });
  await page.click('#tasks-home .th-card[data-id="second"]');
  await page.waitForFunction(() => !!document.querySelector('#tabs [data-act="tab"][data-val="second"][aria-current="page"]'));
  await page.click('#tabs [data-act="tab"][data-val="fixture"]');
  await baseRound;                                                      // базовий опит стався
  await sleep(2200);                                                    // вікно debounce минуло, хвіст теж
  const news = [];
  page.on("request", (r) => { if (r.url().includes("/api/comment-news")) news.push(r.url()); });
  for (let i = 0; i < 5; i++) {
    await page.evaluate(() => {                                         // `retry` → `render()` (див. `forceRender` у canvas.test)
      const b = document.createElement("button");
      b.dataset.act = "retry";
      document.getElementById("bar").appendChild(b);
      b.click();
      b.remove();
    });
    await sleep(100);
  }
  await sleep(2500);
  assert.deepEqual(news, [], "render() без зміни контексту не мусить опитувати новини");
});

/* ── 8: падіння командного ────────────────────────────────────────────────────────────────────────── */

test("8: адаптер модуля не вантажиться → у рамці нема банера, у панелі смуга, чипів нема, локальний пін пишеться у файл", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await page.route(`**/api/module-client/${MODULE}/adapter.js`, (r) => r.abort("failed"));
  const frame = await openShell(env);
  await openPanel(page);
  assert.equal(await frame.evaluate(() => !!document.getElementById("cl-down")), false, "банер __clDown у робочому місці при падінні командного");
  await page.waitForSelector("#cmt-panel .cmt-teamdown", { timeout: 8000 });
  assert.ok((await page.textContent("#cmt-panel .cmt-teamdown")).length > 20);

  await frame.click(".card:nth-child(5) p");                            // під заголовком «Матеріал 5»: є що писати в «де: розділ»
  await frame.waitForFunction(`!!${SHADOW}.querySelector('.compose textarea')`);
  assert.deepEqual(await chips(frame), [], "у формі лишились чипи адресата при падінні командного");
  await frame.evaluate(() => {
    const r = document.querySelector("[data-comment-layer]").shadowRoot;
    const ta = r.querySelector(".compose textarea");
    ta.value = "Локальний при падінні"; ta.dispatchEvent(new Event("input", { bubbles: true }));
    r.querySelector(".compose .save").click();
  });
  await until(() => localList(env).some((c) => c.text === "Локальний при падінні"), "локальний пін у файлі задачі");
  assert.equal(localList(env).some((c) => "_aud" in c), false);
  /* Єдина аудиторія — приватна локальна (`private: true`), чипів нема: заголовок розділу все одно пишемо (підказка «де: розділ» для Claude). */
  const mine = localList(env).find((c) => c.text === "Локальний при падінні");
  assert.ok(mine.meta?.ctx?.heading, "локальний пін при падінні командного втратив заголовок розділу");
});

/* ── 9: без host — як у 0.26.0 ───────────────────────────────────────────────────────────────────── */

test("9: /commented?ch=project напряму (без host) — ручка коментатора видна, комбінованого сховища нема", async (t) => {
  const env = await boot(t);
  const { page, url } = env;
  await page.goto(`${url}/commented?it=it1&page=holovna&ch=project`);
  await page.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  const st = await page.evaluate(() => {
    const host = document.querySelector("[data-comment-layer]");
    const h = host.shadowRoot.querySelector(".handle");
    const s = window.CommentLayer.store || {};
    return { handle: getComputedStyle(h).display, dual: typeof window.DeaiDualStore, teamDown: "teamDown" in s, refreshLocal: typeof s.refreshLocal,
      banner: !!document.getElementById("cl-down") };
  });
  assert.notEqual(st.handle, "none", "ручка коментатора схована без host");
  assert.equal(st.dual, "undefined", "сторінка без host завантажила DeaiDualStore");
  assert.equal(st.teamDown, false);
  assert.equal(st.refreshLocal, "undefined");
  assert.equal(st.banner, false);
});

/* ── 10: латка 0.27.1 — типова вкладка, шапка, доручений командний у «Для AI» ──────────────────── */

test("10: типово «Для AI»; фільтр під пошуком, заголовок не обрізано, кнопки шапки без білої плашки; доручений командний переходить у «Для AI»; вкладка памʼятається", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await seedLocal(env, { id: "loc-1", author: "Фікстура", text: "Локальний" });
  await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний", seq: 2 });
  await openShell(env);
  assert.equal(await lsGet(page, "dc-cmt-filter"), null, "свіжий контекст: вкладка ще не вибрана");
  await openPanel(page);
  const tab = (val) => `#cmt-panel [data-act="cmtfilter"][data-val="${val}"]`;
  const fn = (val) => page.locator(`${tab(val)} .cmt-fn`).textContent();

  assert.equal(await page.getAttribute(tab("local"), "aria-pressed"), "true", "типова вкладка — «Для AI»");
  await until(async () => JSON.stringify(await cardIds(page)) === '["loc-1"]', "у «Для AI» — лише локальна, недоручений командний не видно");
  assert.equal(await fn("local"), "1");
  assert.equal(await fn("project"), "1");
  assert.equal(await fn("all"), "2");

  const geo = await page.evaluate(() => {
    const q = document.querySelector("#cmt-q").getBoundingClientRect();
    const f = document.querySelector("#cmt-panel .cmt-filter").getBoundingClientRect();
    const title = document.querySelector("#cmt-panel .panel-title");
    const bg = (sel) => getComputedStyle(document.querySelector(sel)).backgroundColor;
    return { qTop: q.top, fTop: f.top, fBottom: q.bottom, truncated: title.scrollWidth > title.clientWidth,
      eye: bg('#cmt-panel [data-act="cmtpins"]'), close: bg('#cmt-panel [data-act="comments"]') };
  });
  assert.ok(geo.fTop >= geo.fBottom, "фільтр має стояти під полем пошуку");
  assert.equal(geo.truncated, false, "заголовок панелі обрізано");
  assert.equal(geo.eye, "rgba(0, 0, 0, 0)", "око в шапці має браузерну плашку");
  assert.equal(geo.close, "rgba(0, 0, 0, 0)", "хрестик у шапці має браузерну плашку");

  await page.click(tab("project"));
  const card = '#cmt-panel .cmt-card[data-cid="team-1"]';
  await page.waitForSelector(card);
  await page.click(`${card} [data-act="cmtassign"]`);
  await page.waitForSelector(`${card} [data-act="cmtunassign"]`);
  await until(async () => (await fn("local")) === "2", "число «Для AI» зросло");
  assert.equal(await fn("project"), "1", "доручений лишається й у «Команді»");
  await page.click(tab("local"));
  await until(async () => JSON.stringify((await cardIds(page)).sort()) === '["loc-1","team-1"]', "доручений командний — у «Для AI»");

  await page.click(tab("all"));
  await page.reload();
  await page.waitForSelector('#hud [data-act="comments"]');
  await openPanel(page);
  assert.equal(await page.getAttribute(tab("all"), "aria-pressed"), "true", "остання вибрана вкладка не відновилась");
});

/* ── 11–14: відповіді (0.34) ─────────────────────────────────────────────────────────────────────── */

const memoRow = (env, id, task = "fixture") => (env.memo.store.get(channelOf(task)) ?? []).find((c) => c.id === id);
const REPLY_TS = "20.11.2026 12:00";
/** Дочекатись бази маркера «бачив» (перший знімок) — далі все нове справді нове. */
const baseReady = (page) => until(async () => (await lsGet(page, seenKey())) !== null, "маркер-база dc-seen");
/** Адаптер модуля без підтримки відповідей: той самий файл, але `supportsReplies: false`. */
async function noRepliesAdapter(page) {
  await page.route(`**/api/module-client/${MODULE}/adapter.js`, async (route) => {
    const res = await route.fetch();
    const orig = await res.text();
    const body = orig.replace("supportsReplies: true", "supportsReplies: false");
    if (body === orig) throw new Error("фікстура memo-comments більше не містить `supportsReplies: true` — оновіть noRepliesAdapter");
    await route.fulfill({ response: res, body });
  });
}

test("11: відповідь на командний пін — запис у memo (replies), без смуги «недоступні»", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний" });
  await openShell(env);
  await openPanel(page);
  await page.click('#cmt-panel [data-act="cmtfilter"][data-val="project"]');
  const card = '#cmt-panel .cmt-card[data-cid="team-1"]';
  await page.waitForSelector(`${card} [data-act="cmtreply"]`);
  assert.equal(await page.locator("#cmt-panel .cmt-teamdown").count(), 0, "смуга при живих відповідях");
  await page.click(`${card} [data-act="cmtreply"]`);
  await page.fill(`${card} textarea.cmt-rta`, "Відповідь команді");
  await page.click(`${card} [data-act="cmtreplysend"]`);
  const row = await until(() => { const r = memoRow(env, "team-1"); return r && (r.replies ?? []).some((x) => x.text === "Відповідь команді") ? r : null; }, "відповідь у memo");
  assert.equal(row.replies.length, 1);
  assert.equal("_pending" in row.replies[0], false, "службове _pending потрапило в командне сховище");
  assert.match(await page.textContent(`${card} .cmt-rsum`), /1 відповідь/);
});

test("12: чужа відповідь у memo → «Нове», бейдж острівця, тост «Нова відповідь від …», «+1» на фільтрі; права; «бачив» переживає перезавантаження", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await page.addInitScript(() => { try { localStorage.setItem("comment-layer:user", "Я Тест"); } catch (e) { /* ні */ } });   // «своя» людина відома: чужу відповідь редагувати не можна
  await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний" });
  await openShell(env);
  await baseReady(page);
  assert.equal(await newCount(page), null);

  memoRow(env, "team-1").replies = [{ id: "rep-x", author: "Колега Два", text: "Чужа відповідь", ts: REPLY_TS }];
  await until(async () => (await newCount(page)) === "1", "бейдж «нових» від відповіді", 8000);
  const notice = await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 5000 });
  assert.match(await notice.textContent(), /Нова відповідь від Колега Два · #\d+/);

  await page.click('.cv-notice[data-notice="cmt-news"] [data-act="cmtshownew"]');
  await page.waitForSelector("#cmt-panel:not([hidden]) .cmt-sec--new .cmt-card");
  assert.equal(await page.getAttribute('#cmt-panel [data-act="cmtfilter"][data-val="project"]', "aria-pressed"), "true", "«Показати» не перемкнув на «Команду»");
  assert.equal(await page.textContent('#cmt-panel [data-act="cmtfilter"][data-val="project"] .cmt-fnew'), "+1", "нема «+1» на фільтрі");
  const card = '#cmt-panel .cmt-sec--new .cmt-card[data-cid="team-1"]';
  await page.waitForSelector(`${card} .cmt-reply--new`);
  /* права: чужу відповідь можна видалити, але не змінити */
  assert.equal(await page.locator(`${card} .cmt-reply [data-act="cmtrdel"]`).count(), 1);
  assert.equal(await page.locator(`${card} .cmt-reply [data-act="cmtredit"]`).count(), 0, "чужу відповідь можна редагувати");
  assert.equal(await newCount(page), null, "бейдж лишився при відкритій панелі");

  await page.reload();
  await page.waitForSelector('#hud [data-act="comments"]');
  await until(async () => (await totalCount(page)) !== null, "число відкритих після перезавантаження");
  /* Знімок уже оброблено (число відкритих є): стара відповідь не нова. Друга відповідь (інша id) доводить, що опитування живе, і що «нова» лише вона. */
  assert.equal(await newCount(page), null, "відповідь знову «нова» після перезавантаження");
  assert.equal(await page.locator('.cv-notice[data-notice="cmt-news"]').count(), 0, "плашка про вже бачену відповідь");
  memoRow(env, "team-1").replies.push({ id: "rep-y", author: "Колега Три", text: "Друга чужа", ts: REPLY_TS });
  await until(async () => (await newCount(page)) === "1", "бейдж лише від другої відповіді", 8000);
  assert.match(await (await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 5000 })).textContent(), /Нова відповідь від Колега Три/);
});

test("12б: та сама відповідь у наступному знімку (змінився лише текст) не «зʼявляється» вдруге — другого тосту нема", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний" });
  const frame = await openShell(env);
  await baseReady(page);
  memoRow(env, "team-1").replies = [{ id: "rep-x", author: "Колега Два", text: "Чужа відповідь", ts: REPLY_TS }];
  await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 8000 });
  await page.evaluate(() => document.querySelector('.cv-notice[data-notice="cmt-news"]').remove());
  memoRow(env, "team-1").replies[0].text = "Чужа відповідь, виправлена";
  /* Змінений знімок дійшов до шару й оболонки — тоді «нема тосту» чесна, а не «ще не встигло». */
  await until(() => frame.evaluate(() => window.CommentLayer.snapshot().comments.some((c) => (c.replies || []).some((r) => r.text === "Чужа відповідь, виправлена"))), "змінений знімок у шарі");
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  assert.equal(await page.locator('.cv-notice[data-notice="cmt-news"]').count(), 0, "стара відповідь знову дала тост");
  memoRow(env, "team-1").replies.push({ id: "rep-y", author: "Колега Три", text: "Друга чужа", ts: REPLY_TS });
  assert.match(await (await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 8000 })).textContent(), /Нова відповідь від Колега Три/);
  assert.equal(await newCount(page), "2", "бейдж: дві непрочитані відповіді (rep-x і rep-y), не більше");
});

test("13: відповідь агента (agent:true) у файлі задачі → те саме після focus вікна; «Для AI» показує «+1»", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await seedLocal(env, { id: "loc-1", author: "Фікстура", text: "Локальний" });
  await openShell(env);
  await baseReady(page);
  assert.equal(await newCount(page), null);

  const rows = localList(env);
  rows.find((c) => c.id === "loc-1").replies = [{ id: "rep-agent", author: "Claude", agent: true, text: "Готово, виправив", ts: REPLY_TS }];
  writeFileSync(localFile(env), JSON.stringify(rows, null, 1));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));

  await until(async () => (await newCount(page)) === "1", "бейдж від відповіді агента", 8000);
  const notice = await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 5000 });
  assert.match(await notice.textContent(), /Нова відповідь від Claude · #\d+/);
  await page.click('.cv-notice[data-notice="cmt-news"] [data-act="cmtshownew"]');
  await page.waitForSelector("#cmt-panel:not([hidden]) .cmt-sec--new .cmt-card");
  assert.equal(await page.getAttribute('#cmt-panel [data-act="cmtfilter"][data-val="local"]', "aria-pressed"), "true");
  assert.equal(await page.textContent('#cmt-panel [data-act="cmtfilter"][data-val="local"] .cmt-fnew'), "+1");
  const reply = '#cmt-panel .cmt-sec--new .cmt-reply--new';
  await page.waitForSelector(reply);
  assert.equal(await page.locator(`${reply} .cmt-ragent`).count(), 1, "відповідь агента без позначки агента");
  assert.equal(await page.locator(`${reply} [data-act="cmtredit"]`).count(), 0, "відповідь агента можна редагувати");

  /* Імʼя вікна збігається з автором відповіді агента: редагування закрито саме прапорцем `agent`, а не відмінністю імен. */
  await page.evaluate(() => localStorage.setItem("comment-layer:user", "Claude"));
  await page.reload();
  await page.waitForSelector('#hud [data-act="comments"]');
  await openPanel(page);
  await page.click('#cmt-panel .cmt-card[data-cid="loc-1"] [data-act="cmtthread"]');
  await page.waitForSelector("#cmt-panel .cmt-reply .cmt-ragent");
  assert.equal(await page.locator("#cmt-panel .cmt-reply [data-act=\"cmtrdel\"]").count(), 1, "видалити відповідь агента можна");
  assert.equal(await page.locator("#cmt-panel .cmt-reply [data-act=\"cmtredit\"]").count(), 0, "відповідь агента з тим самим імʼям редагується");
});

test("14: модуль без підтримки відповідей → смуга й нотатка, у командній картці нема поля, кнопок над відповідями нема; локальна відповідає", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await noRepliesAdapter(page);
  await seedLocal(env, { id: "loc-1", author: "Фікстура", text: "Локальний" });
  await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний", seq: 2 });
  memoRow(env, "team-1").replies = [{ id: "rep-old", author: "Колега", text: "Стара відповідь", ts: REPLY_TS }];
  await openShell(env);
  await openPanel(page);
  await page.waitForSelector("#cmt-panel .cmt-teamdown", { timeout: 8000 });
  assert.match(await page.textContent("#cmt-panel .cmt-teamdown"), /Відповіді команди недоступні: модуль коментарів не підтримує відповідей/);

  await page.click('#cmt-panel [data-act="cmtfilter"][data-val="project"]');
  const team = '#cmt-panel .cmt-card[data-cid="team-1"]';
  await page.waitForSelector(`${team} .cmt-rsum`);
  await page.click(`${team} .cmt-rsum`);   // розгорнути (є стара відповідь)
  await page.waitForSelector(`${team} .cmt-reply`);
  assert.match(await page.textContent(`${team} .cmt-rnote`), /Відповіді команди недоступні/);
  for (const sel of ["textarea.cmt-rta", '[data-act="cmtreply"]', '[data-act="cmtredit"]', '[data-act="cmtrdel"]']) {
    assert.equal(await page.locator(`${team} ${sel}`).count(), 0, `у командній картці без відповідей є ${sel}`);
  }

  await page.click('#cmt-panel [data-act="cmtfilter"][data-val="local"]');
  const loc = '#cmt-panel .cmt-card[data-cid="loc-1"]';
  await page.waitForSelector(`${loc} [data-act="cmtreply"]`);
  assert.equal(await page.locator(`${loc} .cmt-rnote`).count(), 0, "нотатка під локальним");
  await page.click(`${loc} [data-act="cmtreply"]`);
  await page.fill(`${loc} textarea.cmt-rta`, "Локальна відповідь");
  await page.click(`${loc} [data-act="cmtreplysend"]`);
  await until(() => localList(env).some((c) => (c.replies ?? []).some((r) => r.text === "Локальна відповідь")), "відповідь у файлі задачі");
});

/* ── 15–17: відповіді без команди; перехідний стан ─────────────────────────────────────────────────── */

const keysOf = async (page, prefix) => (await lsKeys(page)).filter((k) => k.startsWith(prefix));

test("15: БЕЗ команди (модуль не заведений) відповідь агента на локальний пін — новина: бейдж, тост, «Нове»; головний маркер не пишеться; після перезавантаження тосту нема", async (t) => {
  const env = await boot(t, { enable: false });
  const { page } = env;
  await seedLocal(env, { id: "loc-1", author: "Фікстура", text: "Локальний" });
  await openShell(env);
  await until(async () => (await keysOf(page, "dc-seen-r:")).length === 1, "база маркера відповідей");
  assert.deepEqual(await keysOf(page, "dc-seen:"), [], "головний маркер записано без команди (залив би «Нове» колегами, що зʼявляться пізніше)");
  assert.equal(await newCount(page), null);

  const rows = localList(env);
  rows.find((c) => c.id === "loc-1").replies = [{ id: "rep-a", author: "Claude", agent: true, text: "Готово", ts: REPLY_TS }];
  writeFileSync(localFile(env), JSON.stringify(rows, null, 1));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await until(async () => (await newCount(page)) === "1", "бейдж від відповіді агента без команди", 8000);
  assert.match(await (await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 5000 })).textContent(), /Нова відповідь від Claude · #\d+/);
  await page.click('.cv-notice[data-notice="cmt-news"] [data-act="cmtshownew"]');
  await page.waitForSelector("#cmt-panel:not([hidden]) .cmt-sec--new .cmt-card .cmt-reply--new");
  assert.deepEqual(await keysOf(page, "dc-seen:"), [], "відкриття панелі створило головний маркер без команди");

  await page.reload();
  await page.waitForSelector('#hud [data-act="comments"]');
  await until(async () => (await totalCount(page)) !== null, "число відкритих після перезавантаження");
  assert.equal(await newCount(page), null, "відповідь знову «нова» після перезавантаження");
  assert.equal(await page.locator('.cv-notice[data-notice="cmt-news"]').count(), 0, "тост про вже бачену відповідь");
  const again = localList(env);
  again.find((c) => c.id === "loc-1").replies.push({ id: "rep-b", author: "Claude Другий", agent: true, text: "Ще", ts: REPLY_TS });
  writeFileSync(localFile(env), JSON.stringify(again, null, 1));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await until(async () => (await newCount(page)) === "1", "бейдж лише від другої відповіді", 8000);
  assert.match(await (await page.waitForSelector('.cv-notice[data-notice="cmt-news"]', { timeout: 5000 })).textContent(), /Нова відповідь від Claude Другий/);
});

test("16: БЕЗ команди перше відкриття панелі зі старою відповіддю агента — вона не «Нове» і без позначки «нова»", async (t) => {
  const env = await boot(t, { enable: false });
  const { page } = env;
  await seedLocal(env, { id: "loc-1", author: "Фікстура", text: "Локальний",
    replies: [{ id: "rep-old", author: "Claude", agent: true, text: "Давня", ts: "19.11.2026 10:00" }] });
  await openShell(env);
  assert.equal(await newCount(page), null);
  await openPanel(page);
  await page.waitForSelector("#cmt-panel .cmt-card");
  assert.equal(await page.locator("#cmt-panel .cmt-sec--new").count(), 0, "стара відповідь у «Нове»");
  assert.equal(await page.locator("#cmt-panel .cmt-rnew").count(), 0, "стара відповідь із позначкою «нова»");
});

test("17: повільний командний канал — поки він не прочитався, смуги «модуль не підтримує відповідей» не блимає", async (t) => {
  const env = await boot(t);
  const { page } = env;
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      window.__bannerSeen = false;
      new MutationObserver(() => { if (document.querySelector("#cmt-panel .cmt-teamdown")) window.__bannerSeen = true; })
        .observe(document.body, { childList: true, subtree: true });
    });
  });
  let first = true;
  await page.route(`${env.memo.url}/c/**`, async (route) => {
    if (first && route.request().method() === "GET") { first = false; await sleep(2500); }
    await route.continue();
  });
  await seedTeam(env, { id: "team-1", author: "Колега", text: "Командний" });
  await openShell(env);
  await openPanel(page);
  await page.click('#cmt-panel [data-act="cmtfilter"][data-val="project"]');
  await page.waitForSelector('#cmt-panel .cmt-card[data-cid="team-1"] [data-act="cmtreply"]');
  assert.equal(await page.evaluate(() => window.__bannerSeen), false, "смуга «відповіді недоступні» блимнула, поки канал читався");
});

guardRealDeai("g: справжній ~/.deai не зʼявився і не змінився (ізоляція живих тестів)");
