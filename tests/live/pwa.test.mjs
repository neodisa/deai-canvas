/**
 * Канвас як застосунок (PWA «Deai Canvas», P1) — живі перевірки в справжньому
 * Chromium. Юніти (`tests/pwa.test.mjs`) тримають маніфест, значки й логіку
 * worker у заглушеному середовищі; тут — те, що доводить лише браузер:
 *
 *   A Chrome вважає сторінку встановлюваною: CDP `Page.getInstallabilityErrors`
 *     порожній, а розібраний маніфест не має помилок. Це ТА САМА перевірка, яку
 *     Chrome робить перед меню «Встановити» і `beforeinstallprompt`.
 *   B Service worker зареєстровано зі scope `/app/` і він керує сторінкою.
 *   C Сервер недосяжний (офлайн) → сторінка «Канвас не запущено» ОБОМА мовами
 *     за мовою застосунку; повернулась мережа → «Спробувати ще» веде в канвас.
 *   D Мережа лише: правка файла на сервері видна після перезавантаження, а
 *     CacheStorage порожній. Правимо КОПІЮ дерева (`root`), не чекаут.
 *   E ⌘K-дія встановлення: є лише після `beforeinstallprompt`, викликає
 *     `prompt()` рівно раз і зникає; у встановленому вікні її нема; `appinstalled`
 *     → тост.
 *
 * ⚠️ Що тут НЕ доводиться: чи справді Chrome ПОКАЖЕ банер. У безголовому режимі
 * немає UI встановлення, а евристика залученості (клік + 30 с) — на розсуд
 * браузера. Тому A міряє критерії, а не показ; подію E підставляємо самі.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { cpSync, mkdtempSync, readFileSync, utimesSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { DICT } from "../../app/i18n.js";
import { startServer, taskFixture } from "./fixture.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TOOL = path.resolve(HERE, "..", "..");
const PORT_BASE = 17000;
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

/** Копія дерева інструмента, яке тест вільний міняти. Без `node_modules`
 *  (симлінк на залежності чекаута: серверу вони не потрібні) і кешів Python. */
function copyOfTool() {
  const root = mkdtempSync(path.join(tmpdir(), "dc-pwa-root-"));
  const filter = (src) => !/[\\/](node_modules|__pycache__|\.git)([\\/]|$)/.test(src);
  for (const dir of ["app", "bin"]) cpSync(path.join(TOOL, dir), path.join(root, dir), { recursive: true, filter });
  return root;
}

async function boot(t, off, { root } = {}) {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off, ...(root ? { root } : {}) });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  return { page, context, url };
}

/** Завантажити канвас і дочекатись, поки worker візьме сторінку під контроль. */
async function openControlled(page, url) {
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  /* Одне очікування з ТАЙМАУТОМ, а не `await navigator.serviceWorker.ready`: без
     реєстрації той проміс не вирішується ніколи, і тест висів би, а не падав
     (виміряно мутацією «worker не реєструється»). `clients.claim()` бере
     відкриту сторінку під контроль, але момент ловимо опитуванням — без ставки
     на порядок подій. */
  await page.waitForFunction(async () => {
    const reg = await navigator.serviceWorker.getRegistration();
    return !!reg?.active && !!navigator.serviceWorker.controller;
  }, null, { timeout: 10000 });
}

/* ── A ───────────────────────────────────────────────────────────────────── */

test("A: Chrome вважає канвас встановлюваним — інсталяційних помилок немає, маніфест розібрано без помилок", async (t) => {
  const { page, url } = await boot(t, 0);
  await openControlled(page, url);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Page.enable");

  const { installabilityErrors } = await cdp.send("Page.getInstallabilityErrors");
  assert.deepEqual(installabilityErrors, [],
    `Chrome називає причини, чому встановити не можна: ${JSON.stringify(installabilityErrors)}`);

  const man = await cdp.send("Page.getAppManifest");
  assert.ok(man.url.endsWith("/app/manifest.webmanifest"), `маніфест лежить не там: ${man.url}`);
  assert.deepEqual(man.errors, [], `Chrome розібрав маніфест із зауваженнями: ${JSON.stringify(man.errors)}`);
  const parsed = JSON.parse(man.data);
  assert.equal(parsed.name, "Deai Canvas");
  assert.equal(parsed.launch_handler?.client_mode, "focus-existing");
  assert.equal(parsed.display, "standalone");
});

/* ── B ───────────────────────────────────────────────────────────────────── */

test("B: worker зареєстровано зі scope /app/ і він контролює сторінку", async (t) => {
  const { page, url } = await boot(t, 100);
  await openControlled(page, url);
  const info = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.getRegistration();
    return {
      scope: reg.scope, active: !!reg.active, script: reg.active?.scriptURL,
      controller: navigator.serviceWorker.controller?.scriptURL,
    };
  });
  assert.ok(info.scope.endsWith("/app/"), `scope: ${info.scope}`);
  assert.ok(info.active);
  assert.ok(info.script.endsWith("/app/sw.js"), info.script);
  assert.ok(info.controller.endsWith("/app/sw.js"), `сторінку не контролює worker: ${info.controller}`);

  // Після перезавантаження сторінка ВЖЕ відкривається під контролем (не лише
  // після claim): саме так її відкриє значок застосунку.
  await page.reload();
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  assert.ok(await page.evaluate(() => !!navigator.serviceWorker.controller));
});

/* ── C ───────────────────────────────────────────────────────────────────── */

/* Сторінка несе обидві мови, одна з них `hidden`: беремо лише видимий заголовок. */
const offlineTitle = (page) => page.locator("h1:visible").innerText();

test("C: сервер недосяжний → «Канвас не запущено» (мовою застосунку); мережа повернулась → «Спробувати ще» веде в канвас", async (t) => {
  const { page, context, url } = await boot(t, 200);
  await openControlled(page, url);

  await context.setOffline(true);
  await page.reload();
  assert.equal(await offlineTitle(page), DICT.uk.pwaOffTitle, "українською за замовчуванням");
  // Видно лише мову застосунку, не обидві одразу.
  assert.equal(await page.locator("section:visible").count(), 1);
  const text = await page.locator("main").innerText();
  assert.match(text, /start\.command/);
  assert.match(text, /python app\/serve\.py/);
  assert.equal(await page.locator("button:visible").innerText(), DICT.uk.pwaOffRetry);
  assert.equal(await page.evaluate(() => document.documentElement.lang), "uk");

  // Мережа повернулась, але сторінку не перезавантажували: кнопка сама веде далі.
  await context.setOffline(false);
  await page.locator("button:visible").click();
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  assert.equal(await page.locator("h1:has-text('Канвас не запущено')").count(), 0);
});

test("C2: офлайн-сторінка слухає мову застосунку з localStorage (English)", async (t) => {
  const { page, context, url } = await boot(t, 300);
  await openControlled(page, url);
  await page.evaluate(() => localStorage.setItem("dc-lang", "en"));

  await context.setOffline(true);
  await page.reload();
  assert.equal(await offlineTitle(page), DICT.en.pwaOffTitle);
  assert.equal(await page.locator("button:visible").innerText(), DICT.en.pwaOffRetry);
  assert.equal(await page.evaluate(() => document.documentElement.lang), "en");
  assert.equal(await page.title(), DICT.en.pwaOffTitle);
});

/* ── D ───────────────────────────────────────────────────────────────────── */

test("D: worker лише мережа — правка index.html на сервері видна після reload, CacheStorage порожній", async (t) => {
  const root = copyOfTool();
  /* Маркер — у `index.html`: це ЄДИНИЙ ресурс, якого worker справді торкається
     (його навігаційний шлях). Кеш-перший за навігацією — саме та поломка, що
     показала б стару оболонку після `git pull`. Другий маркер у `app.js` —
     страховка від протилежної: worker, що полізе в підресурси (у справжньому
     дизайні він їх не перехоплює взагалі). */
  const indexHtml = path.join(root, "app", "index.html");
  const appJs = path.join(root, "app", "app.js");
  const baseHtml = readFileSync(indexHtml, "utf8");
  const baseJs = readFileSync(appJs, "utf8");
  /* ⚠️ mtime зсуваємо вперед НАВМИСНО. Статику віддає `SimpleHTTPRequestHandler`:
     перезвірка йде за `If-Modified-Since` з СЕКУНДНОЮ точністю, тож правка в тій
     самій секунді, що й попереднє завантаження, читалась би як «не мінялось» і
     повертала стару версію — без жодного worker (виміряно: 4 падіння з 12 при
     тесті без зсуву). Це властивість статичного сервера, не worker; тест має
     перевіряти worker, а не секундну гру годинника. */
  let bump = 0;
  const mark = (v) => {
    writeFileSync(indexHtml, baseHtml.replace("</head>", `<meta name="sw-probe" content="${v}"></head>`));
    writeFileSync(appJs, `${baseJs}\nwindow.__swProbe = ${JSON.stringify(v)};\n`);
    bump += 10;
    const at = Date.now() / 1000 + bump;
    utimesSync(indexHtml, at, at);
    utimesSync(appJs, at, at);
  };
  const probes = (page) => page.evaluate(() => ({
    html: document.querySelector('meta[name="sw-probe"]')?.content ?? null,
    js: window.__swProbe ?? null,
  }));

  mark("v1");
  const { page, url } = await boot(t, 400, { root });
  await openControlled(page, url);
  assert.deepEqual(await probes(page), { html: "v1", js: "v1" });
  // Перезавантаження ПІД контролем worker — на ньому й видно кеш-перший.
  await page.reload();
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  assert.ok(await page.evaluate(() => !!navigator.serviceWorker.controller), "reload не під worker — перевірка порожня");
  assert.deepEqual(await probes(page), { html: "v1", js: "v1" });

  mark("v2");
  await page.reload();
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  assert.deepEqual(await probes(page), { html: "v2", js: "v2" },
    "після правки на сервері прийшла СТАРА версія — worker щось кешує");

  assert.deepEqual(await page.evaluate(() => caches.keys()), [], "worker завів кеш — він мусить бути лише мережею");
});

/* ── E ───────────────────────────────────────────────────────────────────── */

/** Підставна подія встановлення: що б Chrome не вирішив у безголовому режимі,
 *  наш бік (захоплення, пункт ⌘K, `prompt()`) перевіряється детерміновано. */
const fireInstallPrompt = (page) => page.evaluate(() => {
  const ev = new Event("beforeinstallprompt", { cancelable: true });
  ev.prompt = async () => { window.__prompted = (window.__prompted || 0) + 1; };
  ev.userChoice = Promise.resolve({ outcome: "accepted" });
  window.dispatchEvent(ev);
  return ev.defaultPrevented;
});

async function paletteItems(page, query) {
  await page.keyboard.press("Control+K");
  await page.waitForSelector("#palq");
  await page.fill("#palq", query);
  const labels = await page.locator(".pal-it").allInnerTexts();
  await page.keyboard.press("Escape");
  await page.waitForSelector("#palq", { state: "detached" });
  return labels;
}

test("E: пункт ⌘K «Встановити Deai Canvas» — лише після beforeinstallprompt, prompt() рівно раз, потім зникає", async (t) => {
  const { page, url } = await boot(t, 500);
  await openControlled(page, url);

  assert.deepEqual(await paletteItems(page, "Deai"), [], "пункт є ще до події встановлення");

  assert.equal(await fireInstallPrompt(page), true, "міні-банер Chrome не приглушено");
  const found = await paletteItems(page, "Deai");
  assert.equal(found.length, 1, `пунктів встановлення: ${found.length}`);
  assert.match(found[0], new RegExp(DICT.uk.pwaInstall.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

  await page.keyboard.press("Control+K");
  await page.fill("#palq", "Deai");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => window.__prompted === 1, null, { timeout: 3000 });
  assert.deepEqual(await paletteItems(page, "Deai"), [], "після використання подія мертва — пункт мав зникнути");
  assert.equal(await page.evaluate(() => window.__prompted), 1, "prompt() викликано не рівно раз");
});

test("E2: у встановленому вікні (display-mode: standalone) пункту нема, навіть із подією", async (t) => {
  const { page, url } = await boot(t, 600);
  /* Справжній standalone безголовий Chromium не дає (його має лише встановлений
     застосунок), а CDP-емуляція `display-mode` у Chromium не підтримується. Тому
     підміняємо `matchMedia` на самому запиті — це перевіряє рівно те, що важить:
     пункт читає саме `(display-mode: standalone)`. */
  await page.addInitScript(() => {
    const real = window.matchMedia.bind(window);
    window.matchMedia = (q) => (q === "(display-mode: standalone)"
      ? { matches: true, media: q, addEventListener() {}, removeEventListener() {} }
      : real(q));
  });
  await openControlled(page, url);
  assert.equal(await page.evaluate(() => matchMedia("(display-mode: standalone)").matches), true,
    "підміна standalone не спрацювала — перевірка порожня");

  await fireInstallPrompt(page);
  assert.deepEqual(await paletteItems(page, "Deai"), []);
});

test("E3: appinstalled → тост, пункт зникає", async (t) => {
  const { page, url } = await boot(t, 700);
  await openControlled(page, url);
  await fireInstallPrompt(page);
  assert.equal((await paletteItems(page, "Deai")).length, 1);

  await page.evaluate(() => window.dispatchEvent(new Event("appinstalled")));
  await page.waitForFunction((txt) => document.getElementById("cv-toast")?.textContent === txt
    && document.getElementById("cv-toast").classList.contains("show"), DICT.uk.pwaInstalled, { timeout: 3000 });
  assert.deepEqual(await paletteItems(page, "Deai"), []);
});
