/**
 * Статус Клода на канвасі (ідея 02.09.2026, fb-01102026-309e3b п.3; острівець і
 * бейдж — 12.10.2026).
 *
 *   A справжній удар (POST /api/claude-status) поточної задачі → унизу робочої
 *     області, по центру видимої частини, острівець «Claude працює»; у смузі — нічого;
 *   B сервер сказав «згасло» (state: null) → острівець ЗНИКАЄ, а не висить старим —
 *     несуча вимога власника: не брехати «працює», коли нічого не відбувається;
 *   C файли сторінки змінились щойно → у рядку панелі точка «Змінено щойно»;
 *   D бейдж на іконці застосунку: крапка — працює, «1» — чекає, знято — згасло й на pagehide;
 *   E приховане вікно (перекрите вікном Claude) далі оновлює бейдж;
 *   J на старті бейдж знімається (міг лишитись від упалого вікна), хай сервер і каже «нічого»;
 *   F острівець є в «Огляді» (підказка схована), немає на «Задачах» і в чистому перегляді;
 *     тост і плашка піднімаються над ним лише поки його видно;
 *   G смужка режимів коментатора відкрита → острівець над нею (у «Макеті» й в «Огляді»),
 *     закрита → знову внизу;
 *   H острівець по центру робочої області за згорнутої панелі й відкритого інспектора;
 *   I опит не пересотворює острівець: вузол і текст підпису ті самі, міняється лише вік;
 *   K два вікна канваса: одне закрили (`pagehide`) і зняло спільний бейдж — інше ставить його знову;
 *   L повернення до видимого вікна опитує одразу (годинник завмерлий: таймер опиту не спрацює сам);
 *   M сторінку повернули з bfcache — теж опит одразу, не лише повторне застосування бейджа.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, utimesSync, writeFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

/* База 20000: файл займає дванадцять смуг по 100 портів (зсуви 0…1100), а 15800…16599
   налазило на `clean-view` (16200), `preview-password` та інших. Вище за верхівку
   `tasks-home` (18000 + 1800) нічого немає. Зсуви 200 і 300 — під D/E (бейдж),
   800 — J, 900 — K, 1000 — L, 1100 — M. */
const PORT_BASE = 20000;
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

async function bootServer(t, off) {
  const { dir, it1 } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  return { browser, url, it1 };
}

async function boot(t, off) {
  const { browser, url, it1 } = await bootServer(t, off);
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  return { page, url, it1 };
}

const island = (page) => page.evaluate(() =>
  document.querySelector("#claude-hud .claude-island")?.textContent.trim() ?? null);

/* Бейдж у Dock: справжнього встановленого застосунку в headless немає, тож API
   підмінюємо ДО скриптів сторінки й записуємо виклики. Видимість теж підмінна —
   так емулюємо вікно канваса, перекрите вікном Claude. */
const STUB = () => {
  window.__badge = [];
  /* Спільний журнал на кілька вікон (тест K): `__badgeLog` з `context.exposeFunction`
     — лише там, де він є; у решти тестів виклику просто немає. */
  const log = (entry) => { window.__badge.push(entry); window.__badgeLog?.(window.__who ?? "?", entry); };
  Object.defineProperty(Navigator.prototype, "setAppBadge", { configurable: true,
    value(...a) { log(a.length ? ["set", a[0]] : ["set"]); return Promise.resolve(); } });
  Object.defineProperty(Navigator.prototype, "clearAppBadge", { configurable: true,
    value() { log(["clear"]); return Promise.resolve(); } });
  window.__vis = "visible";
  Object.defineProperty(Document.prototype, "visibilityState", { configurable: true, get() { return window.__vis; } });
  Object.defineProperty(Document.prototype, "hidden", { configurable: true, get() { return window.__vis !== "visible"; } });
};
const badgeIs = (page, want, timeout = 12000) => page.waitForFunction((w) =>
  JSON.stringify(window.__badge.at(-1) ?? null) === w, JSON.stringify(want), { timeout });

/** Сервер «каже», що Клод працює (без справжнього удару): однакова відповідь на кожен опит. */
const stubWorking = (page, extra = {}) => page.route("**/api/claude-status", (route) => route.fulfill({
  status: 200, contentType: "application/json",
  body: JSON.stringify({ state: "working", phase: "design", note: "", age_s: 4, ...extra }) }));

test("A+B: удар → острівець «Claude працює» внизу по центру; сервер сказав «згасло» → острівця немає", async (t) => {
  const { page, url } = await boot(t, 0);
  let stub = null;
  await page.route("**/api/claude-status", (route) => (stub
    ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(stub) })
    : route.continue()));
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  assert.equal(await island(page), null, "острівець до першого удару");

  const r = await fetch(`${url}/api/claude-status`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: "fixture", phase: "design", status: "in_progress", note: "Іт.1", session: "live" }) });
  assert.ok(r.ok);
  await page.waitForFunction(() =>
    /Claude працює/.test(document.querySelector("#claude-hud .claude-island")?.textContent || ""), null, { timeout: 12000 });
  assert.equal(await page.locator("#bar .claude-chip, #bar .claude-island").count(), 0, "статус лишився в смузі");
  assert.equal(await page.evaluate(() => document.body.classList.contains("claude-on")), true);
  /* Унизу й по центру ВИДИМОЇ робочої області: панель шарів відкрита, тож центр
     області зсунутий праворуч від центру вікна. */
  const geo = await page.evaluate(() => {
    const i = document.querySelector("#hud .island").getBoundingClientRect();
    const s = document.getElementById("stage").getBoundingClientRect();
    return { gap: innerHeight - i.bottom, delta: Math.abs((i.left + i.right) / 2 - (s.left + s.right) / 2) };
  });
  assert.ok(geo.gap >= 8 && geo.gap <= 24, `острівець не внизу: відступ ${geo.gap}px`);
  assert.ok(geo.delta <= 2, `острівець не по центру робочої області: зсув ${geo.delta}px`);

  stub = { state: null };
  await page.waitForFunction(() => !document.querySelector("#claude-hud .claude-island"), null, { timeout: 12000 });
  assert.equal(await page.evaluate(() => document.body.classList.contains("claude-on")), false,
    "claude-on пережив згаслий статус — тост і плашки висіли б задерті над порожнечею");
});

test("C: сторінка, змінена щойно, має точку в панелі", async (t) => {
  const { page, url, it1 } = await boot(t, 100);
  for (const id of ["holovna", "poshuk"]) {
    const f = path.join(it1, id, "index.html");
    const old = Date.now() / 1000 - 3600;
    utimesSync(f, old, old);
  }
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  /* Той самий DOM-вузол рядка до і після точки: точка ставиться НА МІСЦІ. Повна
     перемальовка панелі на кожну зміну рвала жести (panel-click під навантаженням). */
  await page.evaluate(() => { window.__row = document.querySelector('.panel [data-page="poshuk"]'); });
  writeFileSync(path.join(it1, "poshuk", "index.html"), PAGE("poshuk змінено"));
  await page.waitForFunction(() => document.querySelector('.panel [data-page="poshuk"] .row-recent-dot'),
    null, { timeout: 12000 });
  assert.equal(await page.evaluate(() => window.__row.isConnected), true, "панель перемальовано цілком");
  assert.equal(await page.locator('.panel [data-page="holovna"] .row-recent-dot').count(), 0,
    "точка на сторінці, яку не міняли");
});

test("D: бейдж — крапка, поки працює; «1», коли чекає; знято, коли згасло і коли вікно закрили", async (t) => {
  const { page, url } = await boot(t, 200);
  await page.addInitScript(STUB);
  let stub = { state: "working", phase: "design", note: "", age_s: 3 };
  await page.route("**/api/claude-status", (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify(stub) }));
  await page.goto(`${url}/app/`);
  /* Перший опит — одразу при завантаженні, не через 5 с: 3 с — менше за інтервал. */
  await badgeIs(page, ["set"], 3000);                 // крапка — БЕЗ аргументу (0 бейдж знімає)
  stub = { state: "waiting", phase: "design", note: "", age_s: 3 };
  await badgeIs(page, ["set", 1]);
  stub = { state: null };
  await badgeIs(page, ["clear"]);
  stub = { state: "working", phase: "design", note: "", age_s: 1 };
  await badgeIs(page, ["set"]);
  await page.evaluate(() => dispatchEvent(new PageTransitionEvent("pagehide", { persisted: false })));
  assert.deepEqual(await page.evaluate(() => window.__badge.at(-1)), ["clear"],
    "закрите вікно лишило бейдж — він висів би «працює», коли вже нікому опитувати");
  /* Сторінку повернули з bfcache: відповідь сервера та сама («працює»), тож опит бейдж
     сам не повернув би — його мусить повернути `pageshow`. Подія синхронна, чекати нічого. */
  await page.evaluate(() => dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true })));
  assert.deepEqual(await page.evaluate(() => window.__badge.at(-1)), ["set"],
    "повернена з bfcache сторінка лишилась без бейджа, хоча Клод працює");
});

test("E: приховане вікно (перекрите вікном Claude) далі оновлює бейдж", async (t) => {
  const { page, url } = await boot(t, 300);
  await page.addInitScript(STUB);
  let stub = { state: "working", phase: "design", note: "", age_s: 2 };
  await page.route("**/api/claude-status", (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify(stub) }));
  await page.goto(`${url}/app/`);
  await badgeIs(page, ["set"]);
  await page.evaluate(() => { window.__vis = "hidden"; document.dispatchEvent(new Event("visibilitychange")); });
  stub = { state: "waiting", phase: "design", note: "", age_s: 2 };
  await badgeIs(page, ["set", 1]);
  /* Повернулись до вікна: стан не змінився, тож опит бейдж не чіпає, а система могла
     його скинути, поки вікно було перекрите, — `visibilitychange` мусить застосувати
     бейдж ще раз. Міряємо кількість викликів, а не час: гонки з опитом немає. */
  const n = await page.evaluate(() => window.__badge.length);
  await page.evaluate(() => { window.__vis = "visible"; document.dispatchEvent(new Event("visibilitychange")); });
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => ({ len: window.__badge.length, last: window.__badge.at(-1) }));
  assert.ok(after.len > n, "повернення до видимого вікна не застосувало бейдж ще раз");
  assert.deepEqual(after.last, ["set", 1], "після повернення бейдж не той, що каже сервер");
});

test("J: на старті знімаємо бейдж, що міг лишитись від упалого вікна, коли сервер каже «нічого»", async (t) => {
  const { page, url } = await boot(t, 800);
  await page.addInitScript(STUB);
  let polls = 0;
  await page.route("**/api/claude-status", (route) => { polls += 1; return route.fulfill({ status: 200,
    contentType: "application/json", body: JSON.stringify({ state: null }) }); });
  await page.goto(`${url}/app/`);
  /* Перший опит дає «нічого» — це дорівнює початковому `null`, тож перемальовки не
     буде. Знімає бейдж лише явна перемальовка на старті, а не зміна статусу. */
  await badgeIs(page, ["clear"], 3000);
  for (let i = 0; i < 40 && polls < 1; i += 1) await page.waitForTimeout(50);
  assert.ok(polls >= 1, "перший опит не відбувся — тест порожній");
  await page.waitForTimeout(300);
  const log = await page.evaluate(() => window.__badge);
  assert.ok(!log.some((e) => e[0] === "set"), `сервер сказав «нічого», а бейдж виставлено: ${JSON.stringify(log)}`);
});

test("K: два вікна канваса — закрили одне, і воно зняло спільний бейдж; інше ставить його знову", async (t) => {
  const { browser, url } = await bootServer(t, 900);
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  t.after(() => context.close());
  /* Бейдж належить застосунку, а не вікну: журнал ОДИН на обидва вікна, інакше порядок
     викликів між вікнами не побачити. `who` ставить окремий init-скрипт кожної сторінки. */
  const log = [];
  await context.exposeFunction("__badgeLog", (who, entry) => { log.push([who, ...entry]); });
  await context.addInitScript(STUB);
  await context.route("**/api/claude-status", (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ state: "waiting", phase: "design", note: "", age_s: 3 }) }));
  const A = await context.newPage();
  await A.addInitScript(() => { window.__who = "A"; });
  const B = await context.newPage();
  await B.addInitScript(() => { window.__who = "B"; });
  await A.goto(`${url}/app/`);
  await B.goto(`${url}/app/`);
  await badgeIs(A, ["set", 1], 5000);
  await badgeIs(B, ["set", 1], 5000);

  /* Закрили B: `pagehide` знімає бейдж застосунку. Стан не змінився (все ще «чекає»), тож
     опит у A бейдж сам не поверне — його мусить повернути сповіщення від B. */
  const n = log.length;
  await B.evaluate(() => dispatchEvent(new PageTransitionEvent("pagehide", { persisted: false })));
  const tail = () => log.slice(n);
  for (let i = 0; i < 30 && !tail().some((e) => e[0] === "A"); i += 1) await new Promise((r) => setTimeout(r, 50));
  assert.deepEqual(tail()[0], ["B", "clear"], `закриття B не зняло бейдж: ${JSON.stringify(tail())}`);
  assert.deepEqual(log.at(-1), ["A", "set", 1],
    `A не поставило бейдж знову після закриття B — застосунок лишився б без бейджа: ${JSON.stringify(tail())}`);
});

/* Сторінка із завмерлим годинником: `setInterval` опиту (5 с) сам не спрацює, тож кожен
   опит у тесті — наслідок події, а не таймера. Інакше «опит одразу» не відрізнити від
   «опит за ≤5 с», і охоронець зеленів би при зламаному коді. `polls` рахує звернення. */
async function bootFrozen(t, off) {
  const { page, url } = await boot(t, off);
  await page.clock.install({ time: new Date("2026-10-12T10:00:00Z") });
  await page.clock.pauseAt(new Date("2026-10-12T10:00:01Z"));
  await page.addInitScript(STUB);
  const ctl = { polls: 0, stub: { state: "working", phase: "design", note: "", age_s: 3 } };
  await page.route("**/api/claude-status", (route) => { ctl.polls += 1; return route.fulfill({ status: 200,
    contentType: "application/json", body: JSON.stringify(ctl.stub) }); });
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  /* Перший опит — зі старту, без таймера. */
  assert.deepEqual(await lastBadge(page, ["set"], 5000), ["set"], "перший опит не відбувся — тест порожній");
  /* Свідок: годинник справді завмер (інакше «опит одразу» знову не відрізнити від таймера). */
  const t0 = await page.evaluate(() => Date.now());
  await new Promise((r) => setTimeout(r, 250));
  assert.equal(await page.evaluate(() => Date.now()), t0, "годинник сторінки не завмер — тест не міряє те, що має");
  return { page, ctl };
}
/** Без `waitForFunction`: його опитування — на `requestAnimationFrame` сторінки, а годинник завмерлий. */
async function lastBadge(page, want, ms = 2000) {
  const end = Date.now() + ms;
  let last;
  do {
    last = await page.evaluate(() => window.__badge.at(-1) ?? null);
    if (JSON.stringify(last) === JSON.stringify(want)) return last;
    await new Promise((r) => setTimeout(r, 50));
  } while (Date.now() < end);
  return last;
}

test("L: повернення до видимого вікна опитує одразу — не чекає таймера опиту", async (t) => {
  const { page, ctl } = await bootFrozen(t, 1000);
  const before = ctl.polls;
  await page.evaluate(() => { window.__vis = "hidden"; document.dispatchEvent(new Event("visibilitychange")); });
  ctl.stub = { state: "waiting", phase: "design", note: "", age_s: 3 };
  await page.evaluate(() => { window.__vis = "visible"; document.dispatchEvent(new Event("visibilitychange")); });
  assert.deepEqual(await lastBadge(page, ["set", 1]), ["set", 1],
    "повернулись до вікна, а правда (сервер каже «чекає») не прийшла — опит чекав би таймера до 5 с");
  assert.equal(ctl.polls, before + 1, "опитів не рівно один: годинник не завмер, тест не міряє те, що має");
});

test("M: сторінку повернули з bfcache — опит одразу, а не лише повторне застосування бейджа", async (t) => {
  const { page, ctl } = await bootFrozen(t, 1100);
  const before = ctl.polls;
  /* Відновлена сторінка тримає `claudeView` зі стану на момент заморожування. Поки вона
     лежала в bfcache, статус змінився («працює» → «чекає»), — відновлення мусить це дізнатись. */
  ctl.stub = { state: "waiting", phase: "design", note: "", age_s: 3 };
  await page.evaluate(() => dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true })));
  assert.deepEqual(await lastBadge(page, ["set", 1]), ["set", 1],
    "повернена з bfcache сторінка лишилась зі старим бейджем: статус за час сну змінився, а опиту не було");
  assert.equal(ctl.polls, before + 1, "опитів не рівно один: годинник не завмер, тест не міряє те, що має");
});

test("F: сегмент Claude є в «Огляді» (підказка видима), немає на «Задачах»; острівця немає в чистому перегляді", async (t) => {
  const { page, url } = await boot(t, 400);
  await stubWorking(page);
  await page.goto(`${url}/app/`);
  await page.waitForSelector("#claude-hud .claude-island", { timeout: 12000 });
  const shown = () => page.evaluate(() => {
    const el = document.querySelector("#claude-hud .claude-island");
    return !!el && el.getClientRects().length > 0;
  });
  /* Тост і плашка піднімаються над острівцем ЛИШЕ поки його видно. Вузли-зонди, а
     не справжній тост: той показується лише з дії й одразу гасне. Базові значення
     читаємо зі стилів, щоб тест не тримав другу копію чисел, що розійдеться. */
  const css = readFileSync(new URL("../../app/styles.css", import.meta.url), "utf8");
  const baseOf = (sel) => new RegExp(`^\\${sel}\\{[^}]*?bottom:(\\d+px)`, "m").exec(css)?.[1];
  const BASE = { toast: baseOf(".cv-toast"), notice: baseOf(".cv-notice") };
  assert.ok(BASE.toast && BASE.notice, `не знайшов базових відступів тосту/плашки у styles.css: ${JSON.stringify(BASE)}`);
  const lifts = () => page.evaluate(() => {
    const mk = (cls) => { const d = document.createElement("div"); d.className = cls; document.body.appendChild(d); return d; };
    const toast = mk("cv-toast show");
    const notice = mk("cv-notice");
    const out = { toast: getComputedStyle(toast).bottom, notice: getComputedStyle(notice).bottom };
    toast.remove();
    notice.remove();
    return out;
  });
  /* 0.25.0: острівець (інструменти) стоїть завжди, крім чистого перегляду, тож тост і плашка підняті над ним і без Claude. */
  assert.deepEqual(await lifts(), { toast: "64px", notice: "106px" }, "тост і плашка не піднялись над острівцем");

  await page.click('[data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  assert.equal(await shown(), true, "острівця немає в «Огляді»");
  assert.equal(await page.evaluate(() => getComputedStyle(document.getElementById("canvas-hint")).visibility),
    "visible", "підказка «Огляду» схована без причини: ховає її лише claude-lift (смужка режимів коментатора)");
  await page.click('[data-act="mode"][data-val="layout"]');
  await page.waitForSelector("#stage:not([hidden])");

  await page.keyboard.press("ControlOrMeta+Shift+Backslash");
  await page.waitForFunction(() => document.documentElement.classList.contains("cv-clean"), null, { timeout: 3000 });
  assert.equal(await shown(), false, "острівець у чистому перегляді");
  assert.deepEqual(await lifts(), BASE, "тост/плашка підняті над острівцем, якого в чистому перегляді немає");
  await page.keyboard.press("ControlOrMeta+Shift+Backslash");
  await page.waitForFunction(() => !document.documentElement.classList.contains("cv-clean"), null, { timeout: 3000 });
  assert.equal(await shown(), true, "острівець не повернувся після чистого перегляду");

  await page.click('#tabs [data-act="home"]');
  await page.waitForFunction(() => document.body.classList.contains("home-open"));
  assert.equal(await shown(), false, "сегмент Claude на екрані «Задачі» — статус про макет, якого тут немає");
  assert.equal(await page.locator("#hud .island").count(), 1, "острівець (інструменти) мав лишитись на «Задачах»");
  assert.deepEqual(await page.$$eval("#hud .isl-btn", (els) => els.map((e) => e.dataset.act)), ["feedback"]);
});

/* Геометрія смужки режимів коментатора й острівця в координатах вікна. Смужка живе в
   тіньовому корені коментатора ВСЕРЕДИНІ рамки: її координати — від рамки. */
const geometry = (page) => page.evaluate(() => {
  const f = document.getElementById("frame");
  const fr = f.getBoundingClientRect();
  const bar = f.contentDocument.querySelector("[data-comment-layer]").shadowRoot.querySelector(".modes").getBoundingClientRect();
  const i = document.querySelector("#hud .island").getBoundingClientRect();
  return { barTop: fr.top + bar.top, barBottom: fr.top + bar.bottom, barLeft: fr.left + bar.left, barRight: fr.left + bar.right,
    islTop: i.top, islBottom: i.bottom, islLeft: i.left, islRight: i.right, winH: innerHeight };
});

/** Міряє, доки `ok(g)` не справдиться (смужка й острівець їдуть .2 с, опит — до .5 с),
 *  і ще раз після паузи: перший збіг може випасти на середину руху. */
async function settled(page, ok, ms = 4000) {
  const end = Date.now() + ms;
  let g = await geometry(page);
  while (!ok(g) && Date.now() < end) {
    await page.waitForTimeout(150);
    g = await geometry(page);
  }
  if (!ok(g)) return g;
  await page.waitForTimeout(450);
  return geometry(page);
}

test("G: острівець над смужкою режимів коментатора, поки вона відкрита, і знову внизу, коли ні", async (t) => {
  const { page, url } = await boot(t, 500);
  await stubWorking(page);
  await page.goto(`${url}/app/`);
  await page.waitForSelector("#claude-hud .claude-island", { timeout: 12000 });
  /* Як дизайнер: клац по ручці «Comment» на правому краї рамки (тіньовий корінь коментатора). */
  await page.waitForFunction(() => document.getElementById("frame").contentDocument
    ?.querySelector("[data-comment-layer]")?.shadowRoot?.querySelector(".handle"), null, { timeout: 15000 });
  await page.frameLocator("#frame").locator(".handle").click();
  await page.waitForFunction(() => document.getElementById("frame").contentDocument
    .querySelector("[data-comment-layer]").shadowRoot.querySelector(".modes.show"), null, { timeout: 5000 });

  for (const width of [1440, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    const g = await settled(page, (m) => m.barTop - m.islBottom >= 6);
    /* Свідок: по горизонталі смужка й острівець перетинаються, тож перевірка по
       вертикалі справді щось міряє, а не зеленіє через те, що вони порознь. */
    assert.ok(g.barLeft < g.islRight && g.islLeft < g.barRight,
      `${width}: смужка й острівець не перетинаються по горизонталі — тест порожній: ${JSON.stringify(g)}`);
    assert.ok(g.barTop - g.islBottom >= 6,
      `${width}: острівець накриває смужку режимів коментатора (запас ${g.barTop - g.islBottom}px): ${JSON.stringify(g)}`);
  }

  /* Вийшли з коментування (та сама ручка, тепер «Stop») → смужка зникла → острівець опускається. */
  await page.frameLocator("#frame").locator(".handle").click();
  const g = await settled(page, (m) => m.winH - m.islBottom <= 24);
  assert.ok(g.winH - g.islBottom >= 8 && g.winH - g.islBottom <= 24,
    `острівець лишився піднятим після виходу з коментування: відступ ${g.winH - g.islBottom}px`);

  /* «Огляд»: коментатор полотна живе в документі оболонки, а не в рамці — той самий підйом. */
  await page.click('[data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]")?.shadowRoot?.querySelector(".handle"),
    null, { timeout: 15000 });
  await page.locator("#canvas [data-comment-layer] .handle").click();
  await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(".modes.show"),
    null, { timeout: 5000 });
  let gap = 0;
  for (let i = 0; i < 20 && gap < 70; i += 1) {
    await page.waitForTimeout(150);
    gap = await page.evaluate(() => innerHeight - document.querySelector("#hud .island").getBoundingClientRect().bottom);
  }
  assert.ok(gap >= 70, `в «Огляді» острівець не піднявся над смужкою режимів коментатора: відступ ${gap}px`);
});

test("H: острівець по центру робочої області за згорнутої панелі й відкритого інспектора", async (t) => {
  const { page, url } = await boot(t, 600);
  await stubWorking(page);
  await page.goto(`${url}/app/`);
  await page.waitForSelector("#claude-hud .claude-island", { timeout: 12000 });
  await page.waitForFunction(() => document.getElementById("frame").contentWindow?.CanvasInspector, null, { timeout: 15000 });
  const check = async (what) => {
    await page.waitForTimeout(300);
    const g = await page.evaluate(() => {
      const i = document.querySelector("#hud .island").getBoundingClientRect();
      const s = document.getElementById("stage").getBoundingClientRect();
      return { delta: Math.abs((i.left + i.right) / 2 - (s.left + s.right) / 2), stage: [s.left, s.right] };
    });
    assert.ok(g.delta <= 2, `${what}: острівець не по центру робочої області: зсув ${g.delta}px, сцена ${g.stage}`);
  };
  const collapse = () => page.click('#pages-panel button[data-act="panel"]');

  await check("панель відкрита");
  await collapse();
  await page.waitForFunction(() => document.body.classList.contains("panel-collapsed"), null, { timeout: 3000 });
  await check("панель згорнута");
  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => document.body.classList.contains("with-insp"), null, { timeout: 3000 });
  await check("панель згорнута, інспектор відкритий");
  await collapse();
  await page.waitForFunction(() => !document.body.classList.contains("panel-collapsed"), null, { timeout: 3000 });
  await check("панель відкрита, інспектор відкритий");
});

test("I: опит не пересотворює острівець — вузол і текст підпису ті самі, міняється лише вік", async (t) => {
  const { page, url } = await boot(t, 700);
  /* Вік росте на кожен опит: кожен опит міняє стан, тож перемальовка йде щоразу —
     саме той випадок, коли пересотворений вузол змусив би читач екрана читати знову. */
  let n = 1;
  await page.route("**/api/claude-status", (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ state: "working", phase: "design", note: "", age_s: n++ * 5 }) }));
  await page.goto(`${url}/app/`);
  await page.waitForSelector("#claude-hud .claude-island", { timeout: 12000 });
  await page.evaluate(() => {
    const hud = document.getElementById("claude-hud");
    window.__isl = hud.firstElementChild;
    window.__lblText = hud.querySelector(".lbl-claude").firstChild;
    window.__ages = new Set();
  });
  /* Вік мусить змінитись щонайменше двічі: три різні тексти (перший + дві зміни). */
  await page.waitForFunction(() => {
    window.__ages.add(document.querySelector("#claude-hud .claude-age")?.textContent);
    return window.__ages.size >= 3;
  }, null, { timeout: 25000, polling: 250 });
  const kept = await page.evaluate(() => {
    const hud = document.getElementById("claude-hud");
    return { island: hud.firstElementChild === window.__isl, label: hud.querySelector(".lbl-claude").firstChild === window.__lblText,
      hudKids: hud.children.length };
  });
  assert.equal(kept.island, true, "острівець пересотворено на місці — жива область оголошувала б його щоразу");
  assert.equal(kept.label, true, "підпис переписано без потреби — читач екрана читав би його щоразу");
  assert.equal(kept.hudKids, 1);
});
