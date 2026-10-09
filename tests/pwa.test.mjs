/**
 * Канвас як застосунок (PWA «Deai Canvas», задача P1, спека
 * `docs/superpowers/specs/2026-10-09-canvas-pwa-design.md`).
 *
 * Тут — усе, що перевіряється БЕЗ браузера: маніфест, значки, проводка, межа
 * «лише локальний інструмент», поведінка service worker у заглушеному
 * середовищі та модель сторінкового боку (`app/pwa.js`). Що Chrome справді
 * вважає це встановлюваним застосунком, доводить `tests/live/pwa.test.mjs`
 * (CDP `Page.getInstallabilityErrors`), а маршрути й MIME — `tests/test_pwa.py`.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inflateSync } from "node:zlib";

import { esc } from "../app/esc.js";
import { DICT, LANG_KEY } from "../app/i18n.js";
import { ICON_FILES, layoutOf, PALETTE } from "../app/pwa/icon-spec.mjs";
import { offlineHTML } from "../app/pwa-offline.js";
import { initPwa } from "../app/pwa.js";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");
const read = (rel) => readFileSync(path.join(APP, rel), "utf8");

/* ── маніфест ────────────────────────────────────────────────────────────── */

test("маніфест: поля рівно за спекою (id/start_url/scope, standalone, focus-existing, кольори, три значки)", () => {
  const m = JSON.parse(read("manifest.webmanifest"));
  /* `deepEqual` по ВСЬОМУ обʼєкту, а не по виборці полів: зайве поле — теж
     рішення (`display_override`, `orientation`), і воно має бути свідомим, а
     не тим, що приїхало «заодно». */
  assert.deepEqual(m, {
    id: "/app/",
    name: "Deai Canvas",
    short_name: "Deai Canvas",
    start_url: "/app/",
    scope: "/app/",
    display: "standalone",
    /* Без цього на десктопі `auto` = нове вікно на кожен запуск; повторний
       клік по значку мусить виводити наперед вже відкрите. */
    launch_handler: { client_mode: "focus-existing" },
    theme_color: PALETTE.bg,
    background_color: PALETTE.bg,
    icons: [
      { src: "pwa/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "pwa/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "pwa/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  });
});

test("маніфест: колір теми — токен --s1 оболонки, а не вигаданий літерал", () => {
  const css = read("styles.css");
  const s1 = css.match(/--s1:\s*(#[0-9A-Fa-f]{6})/);
  assert.ok(s1, "у styles.css не знайдено --s1");
  assert.equal(PALETTE.bg.toUpperCase(), s1[1].toUpperCase());
});

/* ── значки ──────────────────────────────────────────────────────────────── */

/** Мінімальний декодер PNG 8-біт (RGB або RGBA) без черезрядковості — рівно те,
 *  що віддає скриншот Chromium: суцільне зображення (maskable) він пише БЕЗ
 *  альфа-каналу, зображення з прозорими кутами (any) — з ним. Власний, бо читати
 *  треба ПІКСЕЛІ (що maskable справді на всю площу, а `any` має прозорі кути), а
 *  залежності для цього тягнути не варто. */
function decodePng(buf) {
  assert.equal(buf.subarray(0, 8).toString("hex"), "89504e470d0a1a0a", "не PNG");
  let w = 0; let h = 0; let ct = -1; let bd = 0; let il = 0;
  const idat = [];
  for (let p = 8; p < buf.length;) {
    const len = buf.readUInt32BE(p);
    const type = buf.toString("ascii", p + 4, p + 8);
    const body = buf.subarray(p + 8, p + 8 + len);
    if (type === "IHDR") {
      w = body.readUInt32BE(0); h = body.readUInt32BE(4);
      bd = body[8]; ct = body[9]; il = body[12];
    } else if (type === "IDAT") idat.push(body);
    p += 12 + len;
  }
  assert.equal(bd, 8, "очікується 8 біт на канал");
  assert.ok(ct === 6 || ct === 2, `очікується RGB/RGBA (color type 2/6), а тут ${ct}`);
  assert.equal(il, 0, "черезрядковий PNG не підтримується");
  const raw = inflateSync(Buffer.concat(idat));
  const bpp = ct === 6 ? 4 : 3; const stride = w * bpp;
  const px = Buffer.alloc(h * stride);
  for (let y = 0; y < h; y += 1) {
    const f = raw[y * (stride + 1)];
    const line = raw.subarray(y * (stride + 1) + 1, (y + 1) * (stride + 1));
    for (let x = 0; x < stride; x += 1) {
      const a = x >= bpp ? px[y * stride + x - bpp] : 0;
      const b = y > 0 ? px[(y - 1) * stride + x] : 0;
      const c = x >= bpp && y > 0 ? px[(y - 1) * stride + x - bpp] : 0;
      let v = line[x];
      if (f === 1) v += a;
      else if (f === 2) v += b;
      else if (f === 3) v += (a + b) >> 1;
      else if (f === 4) {
        const pp = a + b - c;
        const pa = Math.abs(pp - a); const pb = Math.abs(pp - b); const pc = Math.abs(pp - c);
        v += pa <= pb && pa <= pc ? a : (pb <= pc ? b : c);
      }
      px[y * stride + x] = v & 255;
    }
  }
  const pixel = (x, y) => {
    const o = y * stride + x * bpp;
    return { r: px[o], g: px[o + 1], b: px[o + 2], a: bpp === 4 ? px[o + 3] : 255 };
  };
  return { w, h, pixel };
}

const hex = ({ r, g, b }) => `#${[r, g, b].map((n) => n.toString(16).padStart(2, "0")).join("")}`.toUpperCase();

test("значки: кожен файл з маніфесту існує, має заявлений розмір і розмір у IHDR", () => {
  const m = JSON.parse(read("manifest.webmanifest"));
  assert.equal(m.icons.length, ICON_FILES.length, "маніфест і специфікація значків розійшлись");
  for (const icon of m.icons) {
    const buf = readFileSync(path.join(APP, icon.src));
    const { w, h } = decodePng(buf);
    const [dw, dh] = icon.sizes.split("x").map(Number);
    assert.deepEqual([w, h], [dw, dh], `${icon.src}: у файлі ${w}x${h}, заявлено ${icon.sizes}`);
  }
});

test("значки: специфікація і маніфест описують ті самі файли", () => {
  const m = JSON.parse(read("manifest.webmanifest"));
  assert.deepEqual(
    m.icons.map((i) => [i.src, i.purpose, i.sizes]),
    ICON_FILES.map((f) => [`pwa/${f.file}`, f.purpose, `${f.size}x${f.size}`]),
  );
});

test("значки: фон — темно-шавлієвий, логотип по центру, кольори рамки й прямокутника — ті, що в смузі", () => {
  for (const f of ICON_FILES) {
    const png = decodePng(readFileSync(path.join(APP, "pwa", f.file)));
    const L = layoutOf(f.size, f.purpose);
    // Точка в координатах логотипа (viewBox 283) → піксель значка.
    const at = (lx, ly) => png.pixel(
      Math.round(L.offset + (lx / 283) * L.logo), Math.round(L.offset + (ly / 283) * L.logo));
    assert.equal(hex(png.pixel(Math.round(f.size / 2), Math.round(L.offset / 2))), PALETTE.bg.toUpperCase(),
      `${f.file}: над логотипом не фон`);
    assert.equal(hex(at(141, 30)), PALETTE.frame.toUpperCase(), `${f.file}: верх рамки не ${PALETTE.frame}`);
    assert.equal(hex(at(141, 128)), PALETTE.inner.toUpperCase(), `${f.file}: внутрішній прямокутник не білий`);
  }
});

test("значки: any — скруглений квадрат із прозорими кутами, maskable — на всю площу без прозорості", () => {
  for (const f of ICON_FILES) {
    const png = decodePng(readFileSync(path.join(APP, "pwa", f.file)));
    const corners = [[0, 0], [f.size - 1, 0], [0, f.size - 1], [f.size - 1, f.size - 1]]
      .map(([x, y]) => png.pixel(x, y));
    if (f.purpose === "any") {
      for (const c of corners) assert.equal(c.a, 0, `${f.file}: кут має бути прозорим`);
      // Середина сторони — вже всередині квадрата, суцільний фон.
      const mid = png.pixel(Math.round(f.size / 2), 2);
      assert.equal(mid.a, 255, `${f.file}: край квадрата прозорий`);
    } else {
      /* ⛔ Прозорий кут у maskable — це брак, а не стиль: ОС підкладає під нього
         власний колір (білий чи чорний), і значок виглядає з «рамкою». */
      for (const c of corners) {
        assert.equal(c.a, 255, `${f.file}: кут maskable прозорий`);
        assert.equal(hex(c), PALETTE.bg.toUpperCase());
      }
    }
  }
});

test("значки: логотип maskable лежить усередині безпечної зони (коло 80% від сторони)", () => {
  const f = ICON_FILES.find((x) => x.purpose === "maskable");
  const L = layoutOf(f.size, "maskable");
  // Квадрат логотипа цілком у колі радіуса 0.4·size: його кут — найдальша точка.
  const halfDiag = (L.logo / 2) * Math.SQRT2;
  assert.ok(halfDiag <= 0.4 * f.size, `логотип виходить із безпечної зони: ${halfDiag.toFixed(1)} > ${0.4 * f.size}`);
  assert.ok(L.logo >= 0.45 * f.size, "логотип зник: менше за 45% сторони");
});

test("генератор значків парситься (перший порожній запуск без Playwright не потрібен)", () => {
  const r = spawnSync(process.execPath, ["--check", path.join(APP, "pwa", "make-icons.mjs")], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
});

/* ── проводка в застосунок ───────────────────────────────────────────────── */

test("index.html локального інструмента посилається на маніфест і колір теми", () => {
  const html = read("index.html");
  assert.match(html, /<link rel="manifest" href="manifest\.webmanifest">/);
  assert.match(html, new RegExp(`<meta name="theme-color" content="${PALETTE.bg}">`, "i"));
});

test("заголовок вікна встановленого застосунку збігається з його імʼям (title = name з маніфесту)", () => {
  /* Встановлене вікно Chrome показує `<title>` сторінки, а не імʼя з маніфесту:
     із «Design Canvas» у заголовку воно підписувалось би не так, як лежить у
     Dock і ⌘Tab («Deai Canvas»). */
  const m = JSON.parse(read("manifest.webmanifest"));
  assert.match(read("index.html"), new RegExp(`<title>${m.name}</title>`));
});

test("app.js підключає pwa.js і віддає палітрі стан встановлення", () => {
  const src = read("app.js");
  assert.match(src, /from '\.\/pwa\.js'/);
  assert.match(src, /canInstall:\s*pwa\.canInstall\(\)/);
  assert.match(src, /standalone:\s*pwa\.isStandalone\(\)/);
  /* Дія палітри виконується тут напряму — як `lang`, не через BAR_ACTIONS/
     PANEL_ACTIONS: це дія самого застосунку, не смуги й не панелі. */
  assert.match(src, /a\.act === 'pwainstall'/);
});

/* ── межа: ЛИШЕ локальний інструмент ─────────────────────────────────────── */

/* Оболонка опублікованих превʼю — інший продукт, для рецензентів: ні маніфесту,
   ні service worker. Перевіряємо ТЕКСТ усіх модулів, які публікація везе в
   `shell/`, а не лише два файли з іменами: той самий клас, що вже гнав
   охоронців i18n («перелік іменами забудуть доповнити»). Сам перелік —
   `SHELL_MODULES` у serve.py. */
function shellModules() {
  const src = readFileSync(path.join(APP, "serve.py"), "utf8");
  const m = src.match(/SHELL_MODULES\s*=\s*\(([\s\S]*?)\)/);
  assert.ok(m, "у serve.py не знайдено SHELL_MODULES");
  const names = [...m[1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
  assert.ok(names.length >= 10, `розібрано лише ${names.length} модулів — розбір зламаний`);
  return names;
}

test("оболонка превʼю не знає про маніфест, service worker і встановлення", () => {
  const forbidden = /manifest\.webmanifest|rel=["']manifest["']|serviceWorker|sw\.js|beforeinstallprompt|appinstalled/;
  for (const name of shellModules()) {
    assert.doesNotMatch(read(name), forbidden, `${name} їде в превʼю, а згадує PWA`);
  }
  assert.ok(shellModules().includes("ext-shell.js"), "свідок: ext-shell.js має бути в переліку");
});

test("pwa.js, pwa-offline.js і sw.js не їдуть у publish/shell/", () => {
  const list = shellModules();
  for (const own of ["pwa.js", "pwa-offline.js", "sw.js", "manifest.webmanifest"]) {
    assert.ok(!list.includes(own), `${own} у SHELL_MODULES — превʼю отримало б PWA`);
  }
});

/* ── service worker у заглушеному середовищі ─────────────────────────────── */

/* Реальний `sw.js` виконується в Node з підставним `self`. Так перевіряється
   ПОВЕДІНКА (не лише текст), а головне — «нічого не кешує»: `caches` тут
   кидає на будь-якому зверненні, тож SW, який полізе в CacheStorage, падає. */
const handlers = {};
const spies = { skipWaiting: 0, claim: 0 };
globalThis.self = {
  addEventListener: (type, fn) => { handlers[type] = fn; },
  skipWaiting: () => { spies.skipWaiting += 1; return Promise.resolve(); },
  clients: { claim: () => { spies.claim += 1; return Promise.resolve(); } },
};
globalThis.caches = new Proxy({}, {
  get() { throw new Error("service worker торкнувся CacheStorage — він мусить бути лише мережею"); },
});
await import("../app/sw.js");

/** Подія `fetch` із заглушкою: збирає, що саме віддали в `respondWith`. */
function fetchEvent(request) {
  const ev = { request, responded: null, respondWith(p) { ev.responded = Promise.resolve(p); } };
  return ev;
}
const navRequest = (over = {}) => ({ mode: "navigate", method: "GET", url: "http://127.0.0.1:8765/app/", ...over });

test("sw: install кличе skipWaiting, activate — clients.claim (і чекає на нього)", async () => {
  assert.equal(typeof handlers.install, "function");
  assert.equal(typeof handlers.activate, "function");
  let waited = null;
  handlers.install({ waitUntil: (p) => { waited = p; } });
  await waited;
  assert.equal(spies.skipWaiting, 1, "install не кликав skipWaiting");
  waited = null;
  handlers.activate({ waitUntil: (p) => { waited = p; } });
  assert.ok(waited, "activate не передав claim у waitUntil");
  await waited;
  assert.equal(spies.claim, 1, "activate не кликав clients.claim");
});

test("sw: навігація, що дійшла до сервера, віддається як є (той самий Response, без копій)", async () => {
  const live = new Response("<html>canvas</html>", { status: 200 });
  const was = globalThis.fetch;
  globalThis.fetch = async () => live;
  try {
    const ev = fetchEvent(navRequest());
    handlers.fetch(ev);
    assert.ok(ev.responded, "навігацію не перехоплено — Chrome не вважатиме обробник справжнім");
    assert.equal(await ev.responded, live);
  } finally { globalThis.fetch = was; }
});

test("sw: відповідь сервера 500 теж іде як є — офлайн-сторінка лише для НЕдосяжного сервера", async () => {
  const boom = new Response("помилка сервера", { status: 500 });
  const was = globalThis.fetch;
  globalThis.fetch = async () => boom;
  try {
    const ev = fetchEvent(navRequest());
    handlers.fetch(ev);
    const res = await ev.responded;
    assert.equal(res.status, 500);
    assert.equal(await res.text(), "помилка сервера");
  } finally { globalThis.fetch = was; }
});

test("sw: сервер недосяжний → сторінка «Канвас не запущено» обома мовами, 200, HTML", async () => {
  const was = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError("Failed to fetch"); };
  try {
    const ev = fetchEvent(navRequest());
    handlers.fetch(ev);
    const res = await ev.responded;
    assert.equal(res.status, 200);
    assert.match(res.headers.get("content-type"), /^text\/html/);
    const body = await res.text();
    assert.ok(body.includes(DICT.uk.pwaOffTitle), "нема українського заголовка");
    assert.ok(body.includes(DICT.en.pwaOffTitle), "нема англійського заголовка");
  } finally { globalThis.fetch = was; }
});

test("sw: не-навігаційні запити і не-GET лишаються браузеру (respondWith не кличеться)", () => {
  for (const req of [
    { mode: "cors", method: "GET", url: "http://127.0.0.1:8765/app/app.js" },
    { mode: "same-origin", method: "GET", url: "http://127.0.0.1:8765/api/task" },
    { mode: "navigate", method: "POST", url: "http://127.0.0.1:8765/app/" },
  ]) {
    const ev = fetchEvent(req);
    handlers.fetch(ev);
    assert.equal(ev.responded, null, `${req.method} ${req.mode} ${req.url} перехоплено`);
  }
});

test("sw: файл парситься як модуль і не містить Cache API", () => {
  const src = read("sw.js");
  /* Коментарі в цьому репозиторії — головна документація, і слово «caches» у
     поясненні законне; дивимось у код. */
  const code = src.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1 ");
  assert.doesNotMatch(code, /\bcaches\b|\bCacheStorage\b|\.put\(|\.addAll\(/, "SW обіцяв кешувати нічого");
  const r = spawnSync(process.execPath, ["--check", path.join(APP, "sw.js")], { encoding: "utf8" });
  assert.equal(r.status, 0, r.stderr);
});

/* ── офлайн-сторінка ─────────────────────────────────────────────────────── */

test("офлайн-сторінка: текст бере зі словника обох мов, без «undefined» і зайвої розмітки з даних", () => {
  const html = offlineHTML();
  for (const lang of ["uk", "en"]) {
    for (const key of ["pwaOffTitle", "pwaOffLead", "pwaOffMac", "pwaOffWin", "pwaOffRetry"]) {
      assert.ok(DICT[lang][key], `у словнику ${lang} нема ${key}`);
      // Словник кладеться в розмітку екранованим — тим самим `esc()`, що й скрізь.
      assert.ok(html.includes(esc(DICT[lang][key])), `${lang}.${key} не потрапив на сторінку`);
    }
  }
  assert.doesNotMatch(html, /undefined|\[object /);
});

test("офлайн-сторінка: називає обидва способи запуску й має кнопку «Спробувати ще»", () => {
  const html = offlineHTML();
  assert.ok(html.includes("start.command"), "нема способу для Mac");
  assert.ok(html.includes("python app/serve.py"), "нема способу для Windows");
  assert.match(html, /<button[^>]*>/);
});

test("офлайн-сторінка самодостатня: жодного зовнішнього ресурсу (сервера, який міг би віддати, нема)", () => {
  const html = offlineHTML();
  /* `http://www.w3.org/2000/svg` — простір імен SVG у `xmlns` логотипа, не адреса,
     яку хтось завантажує, тож його виключено, а решта адрес — ні. */
  assert.doesNotMatch(html, /<link\b|<img\b|<script[^>]*\bsrc=|@import|url\(|https?:\/\/(?!www\.w3\.org\/2000\/svg)/,
    "сторінка тягне ресурс — офлайн він не завантажиться");
  // Логотип — інлайн-SVG з того самого `logo.js`, що й смуга.
  assert.match(html, /<svg class="logo"/);
});

test("офлайн-сторінка: мова береться з того самого ключа localStorage, що й застосунок", () => {
  assert.ok(offlineHTML().includes(JSON.stringify(LANG_KEY)), "сторінка не знає ключа мови");
});

/* ── сторінковий бік: реєстрація і подія встановлення ────────────────────── */

/** Підставне вікно: події + matchMedia + serviceWorker. */
function fakeWin({ standalone = false, sw = true, registerRejects = false, ready = "complete" } = {}) {
  const win = new EventTarget();
  win.registered = [];
  win.document = { readyState: ready };
  win.matchMedia = (q) => ({ matches: standalone && q === "(display-mode: standalone)" });
  win.navigator = sw ? {
    serviceWorker: {
      register: (url, opts) => {
        win.registered.push([url, opts]);
        return registerRejects ? Promise.reject(new Error("відхилено")) : Promise.resolve({});
      },
    },
  } : {};
  return win;
}
function installEvent() {
  const ev = new Event("beforeinstallprompt", { cancelable: true });
  ev.prompts = 0;
  ev.prompt = async () => { ev.prompts += 1; };
  ev.userChoice = Promise.resolve({ outcome: "accepted" });
  return ev;
}

test("pwa: реєструє sw.js модулем зі scope './' (тобто /app/)", () => {
  const win = fakeWin();
  initPwa({ win });
  assert.deepEqual(win.registered, [["sw.js", { scope: "./", type: "module" }]]);
});

test("pwa: поки сторінка вантажиться, реєстрація чекає на load", () => {
  const win = fakeWin({ ready: "loading" });
  initPwa({ win });
  assert.equal(win.registered.length, 0, "зареєстровано до load");
  win.dispatchEvent(new Event("load"));
  assert.equal(win.registered.length, 1);
});

test("pwa: без підтримки service worker і з відхиленою реєстрацією — мовчки, без винятків", async () => {
  assert.doesNotThrow(() => initPwa({ win: fakeWin({ sw: false }) }));
  const win = fakeWin({ registerRejects: true });
  const pwa = initPwa({ win });
  await new Promise((r) => setTimeout(r, 0)); // відхилення не повинно стати unhandled rejection
  assert.equal(pwa.canInstall(), false);
});

test("pwa: реєстрація, що кидає СИНХРОННО (sandbox, заборонений доступ до serviceWorker), не валить застосунок", () => {
  const throwing = fakeWin();
  throwing.navigator = { get serviceWorker() { throw new DOMException("sandbox", "SecurityError"); } };
  assert.doesNotThrow(() => initPwa({ win: throwing }));

  const syncReject = fakeWin();
  syncReject.navigator.serviceWorker.register = () => { throw new TypeError("sync"); };
  const pwa = initPwa({ win: syncReject });
  // Решта працює: подія встановлення береться й без worker.
  syncReject.dispatchEvent(installEvent());
  assert.equal(pwa.canInstall(), true);
});

test("pwa: beforeinstallprompt глушить міні-банер Chrome й вмикає canInstall", () => {
  const win = fakeWin();
  const pwa = initPwa({ win });
  assert.equal(pwa.canInstall(), false, "до події встановити не можна");
  const ev = installEvent();
  win.dispatchEvent(ev);
  assert.equal(ev.defaultPrevented, true, "банер Chrome не приглушено — наш пункт ⌘K був би другим шляхом");
  assert.equal(pwa.canInstall(), true);
});

test("pwa: install() викликає prompt РІВНО раз і скидає подію (повторно її використати не можна)", async () => {
  const win = fakeWin();
  const pwa = initPwa({ win });
  const ev = installEvent();
  win.dispatchEvent(ev);
  assert.equal(await pwa.install(), "accepted");
  assert.equal(ev.prompts, 1);
  assert.equal(pwa.canInstall(), false, "після використання подія мертва — пункт мусить зникнути");
  assert.equal(await pwa.install(), "unavailable", "повторний виклик без нової події — нічого не робить");
  assert.equal(ev.prompts, 1);
});

test("pwa: prompt() без жесту (NotAllowedError) лишає подію придатною — наступний клік спрацює", async () => {
  const win = fakeWin();
  const pwa = initPwa({ win });
  const ev = installEvent();
  let calls = 0;
  ev.prompt = async () => {
    calls += 1;
    if (calls === 1) throw new DOMException("потрібен жест користувача", "NotAllowedError");
    ev.prompts += 1;
  };
  win.dispatchEvent(ev);
  assert.equal(await pwa.install(), "blocked", "відмова через жест — окремий результат, не «помилка»");
  assert.equal(pwa.canInstall(), true,
    "подію не спалено: вона ще не показувала діалог, наступний жест має шанс");
  assert.equal(await pwa.install(), "accepted");
  assert.equal(ev.prompts, 1);
  assert.equal(pwa.canInstall(), false);
});

test("pwa: інша відмова prompt() (напр. InvalidStateError — вже показували) спалює подію й не кидає", async () => {
  const win = fakeWin();
  const pwa = initPwa({ win });
  const ev = installEvent();
  ev.prompt = async () => { throw new DOMException("вже показано", "InvalidStateError"); };
  win.dispatchEvent(ev);
  assert.equal(await pwa.install(), "error");
  assert.equal(pwa.canInstall(), false, "мертва подія не повинна лишатись «придатною»");
  assert.equal(await pwa.install(), "unavailable");
});

test("pwa: dismissed — повертається як є, без винятку, подію витрачено", async () => {
  const win = fakeWin();
  const pwa = initPwa({ win });
  const ev = installEvent();
  ev.userChoice = Promise.resolve({ outcome: "dismissed" });
  win.dispatchEvent(ev);
  assert.equal(await pwa.install(), "dismissed");
  assert.equal(pwa.canInstall(), false, "після діалогу подія мертва, поки Chrome не пришле нову");
  assert.equal(ev.prompts, 1);
});

test("pwa: подвійний клік, поки діалог відкритий, не викликає prompt() удруге", async () => {
  const win = fakeWin();
  const pwa = initPwa({ win });
  const ev = installEvent();
  let finish;
  ev.userChoice = new Promise((r) => { finish = r; });
  win.dispatchEvent(ev);
  const first = pwa.install();
  assert.equal(await pwa.install(), "busy");
  assert.equal(ev.prompts, 1, "другий prompt() кинув би InvalidStateError і спалив подію");
  finish({ outcome: "accepted" });
  assert.equal(await first, "accepted");
});

test("pwa: appinstalled скидає canInstall і кличе onInstalled", () => {
  const win = fakeWin();
  let told = 0;
  const pwa = initPwa({ win, onInstalled: () => { told += 1; } });
  win.dispatchEvent(installEvent());
  assert.equal(pwa.canInstall(), true);
  win.dispatchEvent(new Event("appinstalled"));
  assert.equal(pwa.canInstall(), false);
  assert.equal(told, 1);
});

test("pwa: isStandalone читає display-mode: standalone", () => {
  assert.equal(initPwa({ win: fakeWin({ standalone: true }) }).isStandalone(), true);
  assert.equal(initPwa({ win: fakeWin({ standalone: false }) }).isStandalone(), false);
});
