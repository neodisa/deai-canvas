/**
 * Помічник макета (М2) наскрізно, на прикладі `docs/modules/examples/contrast/` («Контраст»): той самий приклад, що його копіюють
 * люди, у тимчасовому просторі (`DEAI_HOME` теж тимчасовий). Довіра — шов `DEAI_TRUST_CONFIRM`, увімкнення — `/api/module-enable`.
 *
 * Макет: на першій сторінці кнопка `#cta` (білий текст на `#9fd3b8` — контраст), поле без підпису, картинка без `alt` (далеко
 * внизу, за екраном) і лічильник кліків `window.__clicks`; друга сторінка без проблем. Сценарії йдуть одним станом, по черзі.
 *
 * Знімки для людини — лише коли задано `DEAI_SHOTS` (або `DEAI_SHOTS_DIR`).
 */
import assert from "node:assert/strict";
import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, stop, waitBarReady } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";
import { TONE_COLORS } from "../../app/page-rules.js";

/* Своя смуга (`tests/live-ports.test.mjs` стереже, що бази не збігаються). */
const PORT_BASE = 48000;
const EXAMPLE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/modules/examples/contrast");
const SHOTS = process.env.DEAI_SHOTS || process.env.DEAI_SHOTS_DIR || "";
const IMG = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

const MOCKUP = (id) => (id === "holovna"
  ? `<!doctype html><html><head><meta charset="utf-8"><title>Макет ${id}</title></head><body style="margin:0;font-family:sans-serif">`
    + `<button id="cta" style="color:#fff;background:#9fd3b8;border:0;padding:8px 16px;font-size:16px">Почати</button>`
    + `<p><input id="q" type="text" style="width:200px"></p>`
    + `<div style="height:1800px"></div><img id="pic" src="${IMG}" width="40" height="40">`
    + `<script>window.__clicks=0;document.getElementById("cta").addEventListener("click",function(){window.__clicks++});</script>`
    + `</body></html>`
  : `<!doctype html><html><head><meta charset="utf-8"><title>Макет ${id}</title></head>`
    + `<body style="margin:0;font-family:sans-serif"><h1 id="t" style="color:#111">Макет ${id}</h1><p style="color:#222">текст</p></body></html>`);

const BTN = '#isl-tools [data-act="modtool"]';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const waitToast = (page, re) => page.waitForFunction((src) => new RegExp(src).test(document.getElementById("cv-toast")?.textContent ?? ""), re.source, { timeout: 15000 });

let browser, server, context, page, errors;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await context?.close(); if (server) await stop(server.child); await browser?.close(); });

/** Довіра (як сторінка канваса: `Origin` + `Sec-Fetch-Site: same-origin`; системне вікно — шов) і увімкнення. */
async function trustAndEnable(url, id) {
  const st = await (await fetch(`${url}/api/module-trust?space=studio&id=${id}`)).json();
  assert.ok(st.trust?.hash, `стан довіри: ${JSON.stringify(st)}`);
  const tr = await fetch(`${url}/api/module-trust`, { method: "POST",
    headers: { "Content-Type": "application/json", Origin: url, "Sec-Fetch-Site": "same-origin" },
    body: JSON.stringify({ space: "studio", id, hash: st.trust.hash }) });
  assert.equal(tr.status, 200, `довіра: ${await tr.text()}`);
  const en = await (await fetch(`${url}/api/module-enable`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ space: "studio", id, settings: {} }) })).json();
  assert.equal(en.ok, true, `module-enable: ${JSON.stringify(en)}`);
}

const panel = () => page.frameLocator("#mod-panel iframe");
const panelOpen = () => page.waitForFunction(() => !document.getElementById("mod-panel").hidden, null, { timeout: 15000 });
const panelClosed = () => page.waitForFunction(() => document.getElementById("mod-panel").hidden, null, { timeout: 15000 });
const rows = () => panel().locator("#list .dk-row");
/** Виконати `fn(arg)` у документі макета (однієї походження з оболонкою). */
const inFrame = (fn, arg) => page.evaluate(([src, a]) => {
  const w = document.getElementById("frame").contentWindow;
  return w.eval(`(${src})`)(a);
}, [fn.toString(), arg]);
const marks = () => inFrame(() => {
  const h = document.querySelector("[data-deai-marks]");
  if (!h) return null;
  return [...h.shadowRoot.querySelectorAll(".mk")].map((b) => b.style.getPropertyValue("--t").trim().toUpperCase());
});
/** Тон мітки, що накриває елемент `sel` (порядок коробок у корені — порядок створення, а не розкладки). */
const toneAt = (sel) => inFrame((q) => {
  const h = document.querySelector("[data-deai-marks]");
  const e = document.querySelector(q).getBoundingClientRect();
  const cx = e.left + e.width / 2, cy = e.top + e.height / 2;
  const hit = h && [...h.shadowRoot.querySelectorAll(".mk")].find((b) => { const r = b.getBoundingClientRect(); return !b.hidden && r.left <= cx && cx <= r.right && r.top <= cy && cy <= r.bottom; });
  return hit ? hit.style.getPropertyValue("--t").trim().toUpperCase() : null;
}, sel);
const clicks = () => inFrame(() => window.__clicks);
const cssOf = (sel) => inFrame((s) => getComputedStyle(document.querySelector(s)).color, sel);
const waitFrame = (fn, arg, timeout = 15000) => page.waitForFunction(([src, a]) => {
  const w = document.getElementById("frame").contentWindow;
  try { return w.eval(`(${src})`)(a); } catch (e) { return false; }
}, [fn.toString(), arg], { timeout });
/** Екранні координати центру елемента макета (рамка може бути масштабована). */
const centre = (sel) => page.evaluate((s) => {
  const f = document.getElementById("frame");
  const r = f.getBoundingClientRect(), el = f.contentDocument.querySelector(s).getBoundingClientRect();
  const k = r.width / f.contentWindow.innerWidth;
  return { x: r.left + (el.left + el.width / 2) * k, y: r.top + (el.top + el.height / 2) * k };
}, sel);
const clickAt = async (sel) => { const c = await centre(sel); await page.mouse.click(c.x, c.y); };
const shot = async (name) => {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, `module-page-${name}.png`) });
};
const pickBtn = () => panel().locator("#pick");
const waitPicking = (on) => waitFrame((v) => !!document.querySelector("[data-deai-marks]")?.shadowRoot.querySelector(".cv") === v, on);
const openByKey = async (k) => { await page.click(`${BTN}[title$="(${k})"]`); await panelOpen(); };
/** Опитування умови (панель — ізольована рамка без `contentDocument`, її читаємо лише локаторами). */
async function until(fn, what, timeout = 15000) {
  const end = Date.now() + timeout;
  for (;;) {
    let v; try { v = await fn(); } catch (e) { v = false; }
    if (v) return v;
    if (Date.now() > end) throw new Error(`не дочекались: ${what}`);
    await sleep(100);
  }
}
const waitRows = (n) => until(async () => (await rows().count()) === n, `${n} рядків у панелі`);
const pressed = async () => (await pickBtn().getAttribute("aria-pressed")) === "true";
const waitUnpressed = () => until(async () => (await pickBtn().getAttribute("aria-pressed")) === "false", "кнопка вибору віджата");
const hotIndex = () => rows().evaluateAll((els) => els.findIndex((e) => e.classList.contains("hot")));

test("налаштування: простір, два модулі, довіра", async () => {
  const X = taskFixture({ html: MOCKUP });
  server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_TRUST_CONFIRM: "yes" },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }] });
  const mods = path.join(server.spaces[0].path, "modules");
  cpSync(EXAMPLE, path.join(mods, "contrast"), { recursive: true });
  /* Варіант без `change`: та сама панель, інші id/назва/клавіша й дозволи `read`+`mark`. */
  const ro = path.join(mods, "contrast-ro");
  cpSync(EXAMPLE, ro, { recursive: true });
  const mf = JSON.parse(readFileSync(path.join(ro, "module.json"), "utf8"));
  mf.id = "contrast-ro"; mf.name = "Контраст RO";
  mf.tools[0].id = "contrast-ro"; mf.tools[0].label = "Контраст RO"; mf.tools[0].key = "R"; mf.tools[0].page = ["read", "mark"];
  writeFileSync(path.join(ro, "module.json"), JSON.stringify(mf, null, 2));
  await trustAndEnable(server.url, "contrast");
  await trustAndEnable(server.url, "contrast-ro");
  context = await browser.newContext({ viewport: VIEW });
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  page = await context.newPage();
  errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("frame").contentDocument?.querySelector("[data-comment-layer]"), null, { timeout: 15000 });
  await page.waitForSelector(`${BTN}[title$="(K)"]`, { timeout: 15000 });
  await page.waitForSelector(`${BTN}[title$="(R)"]`, { timeout: 15000 });
  await waitFrame(() => window.__clicks === 0);
});

test("1. K відкриває «Контраст»: три мітки (error/warn/info) і три рядки", async () => {
  await page.keyboard.press("k");
  await panelOpen();
  await waitRows(3);
  assert.equal(await rows().count(), 3);
  await waitFrame(() => document.querySelector("[data-deai-marks]")?.shadowRoot.querySelectorAll(".mk").length === 3);
  assert.deepEqual(await marks(), [TONE_COLORS.error, TONE_COLORS.warn, TONE_COLORS.info].map((c) => c.toUpperCase()));
  const cls = await rows().evaluateAll((els) => els.map((e) => e.className));
  assert.match(cls[0], /tone-error/); assert.match(cls[1], /tone-warn/); assert.match(cls[2], /tone-info/);
  await shot("1-marks");
});

test("2. «Показати» на останньому рядку: картинка в видимій частині рамки", async () => {
  const inView = () => inFrame(() => { const r = document.getElementById("pic").getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
  assert.equal(await inView(), false, "картинка від початку в кадрі — фікстура не перевіряє прокрутку");
  await rows().last().locator("button", { hasText: "Показати" }).click();
  await waitFrame(() => { const r = document.getElementById("pic").getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
  await shot("2-reveal");
});

test("3. «Спробувати виправлення» → колір змінено, мітка ok; закриття панелі відкочує все", async () => {
  await inFrame(() => window.scrollTo(0, 0));
  const before = await cssOf("#cta");
  assert.equal(before, "rgb(255, 255, 255)");
  await rows().first().locator("button", { hasText: "Спробувати виправлення" }).click();
  await waitFrame(() => getComputedStyle(document.getElementById("cta")).color !== "rgb(255, 255, 255)");
  assert.notEqual(await cssOf("#cta"), before);
  await until(async () => (await toneAt("#cta")) === TONE_COLORS.ok.toUpperCase(), "мітка #cta стала ok");
  assert.equal((await marks()).length, 3, "після виправлення міток не три");
  await shot("3-fixed");
  await page.click('#mod-panel [data-act="modclose"]');
  await panelClosed();
  await waitFrame(() => getComputedStyle(document.getElementById("cta")).color === "rgb(255, 255, 255)");
  assert.equal(await inFrame(() => document.getElementById("cta").hasAttribute("style")), true,
    "у `#cta` власний `style` макета (колір, фон) — він лишається");
  assert.equal(await inFrame(() => document.getElementById("cta").getAttribute("style")),
    "color:#fff;background:#9fd3b8;border:0;padding:8px 16px;font-size:16px", "інлайн-стиль макета відкочено не дослівно");
  assert.equal(await marks(), null, "хост міток лишився після закриття панелі");
  await shot("3-after-close");
});

test("4. друга сторінка без проблем: подія `page` дійшла, міток нема", async () => {
  await openByKey("K");
  await waitRows(3);
  await page.click('.row[data-page="poshuk"]');
  await panel().locator("#list .dk-empty", { hasText: "Проблем не знайдено" }).waitFor({ timeout: 15000 });
  assert.equal(await rows().count(), 0);
  assert.equal(await marks(), null);
  await shot("4-clean-page");
});

test("5. «Вибрати елемент» → клік по #cta не доходить до сторінки, рядок підсвічено", async () => {
  await page.click('.row[data-page="holovna"]');
  await waitRows(3);
  await waitFrame(() => document.querySelector("[data-deai-marks]")?.shadowRoot.querySelectorAll(".mk").length === 3);
  const base = await clicks();
  assert.equal(base, 0);
  await pickBtn().click();
  assert.equal(await pickBtn().getAttribute("aria-pressed"), "true");
  await waitPicking(true);
  await shot("5-picking");
  await clickAt("#cta");
  await until(async () => (await hotIndex()) === 0, "підсвічено рядок #cta");
  assert.equal(await clicks(), base, "клік вибору дійшов до сторінки");
  await waitUnpressed();
  await waitPicking(false);
});

test("6. Esc у макеті й у панелі завершує вибір", async () => {
  // (а) фокус віддано макету → Esc у макеті
  await pickBtn().click();
  await waitPicking(true);
  await page.waitForFunction(() => document.activeElement?.id === "frame", null, { timeout: 15000 });
  await page.keyboard.press("Escape");
  await waitUnpressed();
  await waitPicking(false);
  const base = await clicks();
  await clickAt("#cta");
  await waitFrame((n) => window.__clicks === n + 1, base);
  // (б) фокус у панелі → Esc у панелі шле `cancelPick`
  await pickBtn().click();
  await waitPicking(true);
  await panel().locator(".sum").click({ position: { x: 3, y: 3 } });
  await page.waitForFunction(() => document.activeElement?.closest?.("#mod-panel") != null, null, { timeout: 15000 });
  // Повідомлення панелі під час вибору (не `page.pick`) не повертає фокус макету: «Показати» → мітка блимнула → фокус досі в панелі.
  await rows().first().locator("button", { hasText: "Показати" }).click();
  await waitFrame(() => !!document.querySelector("[data-deai-marks]")?.shadowRoot.querySelector(".mk.fl"));
  // Негативна перевірка: фокус перехоплюється вже ПІСЛЯ обробки повідомлення, тож стежимо за ним відрізок часу, а не один раз.
  for (let i = 0; i < 16; i++) {
    assert.equal(await page.evaluate(() => document.activeElement?.closest?.("#mod-panel") != null), true,
      "повідомлення панелі забрало фокус у неї на користь макета");
    await sleep(50);
  }
  await page.keyboard.press("Escape");
  await waitUnpressed();
  await waitPicking(false);
});

test("7. `listen`: справжній клік мишею по #cta доходить до сторінки й підсвічує рядок", async () => {
  const base = await clicks();
  await clickAt("#q");                                   // спершу інший елемент: підсвічується рядок поля
  await until(async () => (await hotIndex()) === 1, "підсвічено рядок поля");
  await clickAt("#cta");
  await until(async () => (await hotIndex()) === 0, "підсвічено рядок #cta");
  assert.equal(await clicks(), base + 1, "клік не дійшов до сторінки");
});

test("8. без дозволу `change`: «Спробувати виправлення» → тост not-allowed, колір не змінено", async () => {
  await page.click('#mod-panel [data-act="modclose"]');
  await panelClosed();
  await openByKey("R");
  await waitRows(3);
  await waitFrame(() => document.querySelector("[data-deai-marks]")?.shadowRoot.querySelectorAll(".mk").length === 3);
  const before = await cssOf("#cta");
  await rows().first().locator("button", { hasText: "Спробувати виправлення" }).click();
  await waitToast(page, /not-allowed/);
  await sleep(300);
  assert.equal(await cssOf("#cta"), before);
  assert.deepEqual(await marks(), [TONE_COLORS.error, TONE_COLORS.warn, TONE_COLORS.info].map((c) => c.toUpperCase()), "мітки змінились попри відмову");
});

test("без помилок сторінки й справжній ~/.deai не чіпано", async () => {
  assert.deepEqual(errors, []);
});
guardRealDeai();
