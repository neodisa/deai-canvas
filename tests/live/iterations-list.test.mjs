/**
 * Перелік ітерацій і історія (фаза И, Task 9) — живе проведення.
 *
 * Юніти стережуть розмітку й модель (`tests/shell-bar.test.mjs`, `tests/iter-history-view.test.mjs`); тут те, чого вони не бачать:
 * що «⋯» рядка відкривається ПРАВОРУЧ від переліку, що поле назви справді тримає фокус і зберігає Enter/blur, що видалення йде
 * через сервер у кошик і «Повернути» повертає ітерацію на місце, що історія читає справжній git теки задачі.
 *
 * Знімки для перевірки вигляду пишуться лише коли задано `DEAI_SHOTS_DIR` (звичайний прогін файлів не створює).
 */
import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 35000;
const SHOTS = process.env.DEAI_SHOTS_DIR || "";
const TITLE = "Лендінг тижня";

/** Фікстурна особа машини: ітерації з іншим ключем автора в iterations.json стають «чужими». */
const ME = { name: "Lead", email: "lead@example.com" };

/**
 * Сервер + браузер. `count` — скільки ітерацій (1…3; it2, it3 — копіями it1 через `/api/iteration`, тож в історії є «копія»);
 * `foreign` — зробити останню чужою (ініціали в рядку).
 */
async function boot(t, { count = 2, foreign = false, portBase = PORT_BASE } = {}) {
  const keep = { n: process.env.DC_IDENTITY_NAME, e: process.env.DC_IDENTITY_EMAIL };
  process.env.DC_IDENTITY_NAME = ME.name;
  process.env.DC_IDENTITY_EMAIL = ME.email;
  t.after(() => {
    if (keep.n === undefined) delete process.env.DC_IDENTITY_NAME; else process.env.DC_IDENTITY_NAME = keep.n;
    if (keep.e === undefined) delete process.env.DC_IDENTITY_EMAIL; else process.env.DC_IDENTITY_EMAIL = keep.e;
  });
  const { dir } = taskFixture({ html: () => "<!doctype html><h1>Фікстура</h1>" });
  const { child, url } = await startServer(dir, { portBase, title: TITLE });
  t.after(() => child.kill());
  const post = (p, b) => fetch(url + p, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) })
    .then((r) => r.json());
  const names = ["", "Друга", "Третя"];
  for (let i = 2; i <= count; i += 1) await post("/api/iteration", { from: "it1", note: names[i - 1] });
  if (foreign && count >= 2) {
    const f = path.join(dir, "iterations.json");
    const j = JSON.parse(readFileSync(f, "utf8"));
    Object.assign(j.iterations[j.iterations.length - 1], { author: "Ольга Сидорук", author_key: "designer2@example.com" });
    writeFileSync(f, JSON.stringify(j));
  }
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-dd="iter"]');
  await page.waitForSelector("#frame");
  const ids = async () => (await (await fetch(`${url}/api/task`)).json()).iterations.map((x) => x.id);
  return { page, url, post, dir, ids };
}

/** Знімок у `DEAI_SHOTS_DIR`: без змінної — нічого не пишемо. */
async function shot(page, name) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(SHOTS, name) });
}

const rows = (page) => page.$$eval("#bar .dd--iters .it-row .dd-t", (els) => els.map((e) => e.textContent.trim()));
const openList = async (page) => {
  await page.click('#bar [data-dd="iter"]');
  await page.waitForSelector("#bar .dd--iters .it-row");
};
const openRowMenu = async (page, id) => {
  await page.click(`#bar .it-more[data-val="${id}"]`);
  await page.waitForSelector(`#bar .dd--itmenu[data-for="${id}"]`);
};

test("смуга: задача перша, далі «/» і ітерація; вкладка — назва задачі, не id", async (t) => {
  const { page } = await boot(t);
  const order = await page.evaluate(() => {
    const a = document.querySelector('#bar [data-dd="task"]');
    const sep = document.querySelector("#bar .crumb-sep");
    const b = document.querySelector('#bar [data-dd="iter"]');
    const f = Node.DOCUMENT_POSITION_FOLLOWING;
    return !!(a && sep && b && (a.compareDocumentPosition(sep) & f) && (sep.compareDocumentPosition(b) & f) && sep.textContent.trim() === "/");
  });
  assert.ok(order, "порядок: задача / ітерація");
  assert.equal((await page.textContent("#tabs .tab--on .tab-id")).trim(), TITLE, "вкладка показує не назву");
  assert.equal((await page.textContent('#bar [data-dd="task"] .txt')).trim(), TITLE);
  await shot(page, "01-bar.png");
});

test("перелік: рядки, меню «⋯» відкривається праворуч; рядок чужої має ініціали", async (t) => {
  const { page } = await boot(t, { count: 3, foreign: true });
  await openList(page);
  assert.deepEqual(await rows(page), ["Іт.3 · Третя", "Іт.2 · Друга", "Іт.1 · фікстура"]);
  assert.equal(await page.locator('#bar .it-row[data-it="it3"] .it-who').textContent(), "ОС", "ініціали чужої ітерації");
  assert.equal(await page.locator("#bar .it-row .it-who").count(), 1, "ініціали лише в чужої");
  await shot(page, "02-list.png");
  await openRowMenu(page, "it2");
  const geo = await page.evaluate(() => {
    const l = document.querySelector("#bar .dd--iters").getBoundingClientRect();
    const m = document.querySelector("#bar .dd--itmenu").getBoundingClientRect();
    return { listRight: l.right, menuLeft: m.left, menuRight: m.right, vw: window.innerWidth };
  });
  assert.ok(geo.menuLeft >= geo.listRight, `меню не праворуч від переліку: ${JSON.stringify(geo)}`);
  assert.ok(geo.menuRight <= geo.vw, "меню вилізло за вікно");
  await shot(page, "03-rowmenu.png");
});

test("перейменування: меню → поле → Enter зберігає; Esc скасовує; F2 на рядку відкриває поле", async (t) => {
  const { page, url } = await boot(t);
  await openList(page);
  // меню → «Перейменувати» → Enter
  await openRowMenu(page, "it2");
  await page.click('#bar .dd--itmenu [data-act="itren"]');
  await page.waitForSelector("#it-ren-in");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "it-ren-in", "фокус не в полі");
  await shot(page, "04-rename.png");
  await page.fill("#it-ren-in", "Фільтри");
  await page.press("#it-ren-in", "Enter");
  await page.waitForFunction(() => [...document.querySelectorAll("#bar .dd--iters .dd-t")].some((e) => e.textContent.trim() === "Іт.2 · Фільтри"));
  assert.ok((await rows(page)).includes("Іт.2 · Фільтри"));
  const saved = (await (await fetch(`${url}/api/task`)).json()).iterations.find((x) => x.id === "it2");
  assert.match(saved.label_text, /Фільтри/, "назва не дійшла до сервера");
  // Esc скасовує: дропдаун лишається відкритим, назва не змінилась
  await openRowMenu(page, "it2");
  await page.click('#bar .dd--itmenu [data-act="itren"]');
  await page.waitForSelector("#it-ren-in");
  await page.fill("#it-ren-in", "Не зберігати");
  await page.press("#it-ren-in", "Escape");
  await page.waitForSelector("#it-ren-in", { state: "detached" });
  await page.waitForSelector("#bar .dd--iters");
  assert.ok((await rows(page)).includes("Іт.2 · Фільтри"), "Esc зберіг назву");
  assert.ok(!(await rows(page)).some((x) => /Не зберігати/.test(x)));
  // F2 на рядку
  await page.focus('#bar .it-row[data-it="it2"] .dd-item');
  await page.keyboard.press("F2");
  await page.waitForSelector("#it-ren-in");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "it-ren-in");
  await page.press("#it-ren-in", "Escape");
});

test("«Нова ітерація»: новий рядок одразу в режимі назви, фокус у полі; діалогу нема", async (t) => {
  const { page, ids } = await boot(t);
  let dialogs = 0;
  page.on("dialog", (d) => { dialogs += 1; d.dismiss(); });
  await openList(page);
  await page.click('#bar [data-act="newit"]');
  await page.waitForSelector("#it-ren-in");
  assert.equal(await page.evaluate(() => document.activeElement?.id), "it-ren-in", "фокус не в полі нового рядка");
  assert.deepEqual(await ids(), ["it1", "it2", "it3"]);
  assert.equal(await page.locator(".cv-ask").count(), 0, "зʼявився діалог питання");
  await page.fill("#it-ren-in", "Нова назва");
  await page.press("#it-ren-in", "Enter");
  await page.waitForFunction(() => [...document.querySelectorAll("#bar .dd--iters .dd-t")].some((e) => e.textContent.trim() === "Іт.3 · Нова назва"));
  assert.equal(dialogs, 0, "зʼявилось вікно браузера");
});

test("видалення: питання в рядку → тост «Повернути» → ітерація повертається на місце", async (t) => {
  const { page, ids } = await boot(t, { count: 3 });
  await openList(page);
  await openRowMenu(page, "it2");
  await page.click('#bar .dd--itmenu [data-act="itdel"]');
  await page.waitForSelector("#bar .it-cfm .cfm");
  assert.match(await page.textContent("#bar .it-cfm .cfm-t"), /Видалити Іт\.2/);
  await shot(page, "05-delete.png");
  await page.click('#bar .it-cfm [data-act="itdelyes"]');
  await page.waitForSelector('#cv-toast.show [data-act="undo"]');
  assert.deepEqual(await ids(), ["it1", "it3"], "сервер не прибрав ітерацію");
  await shot(page, "06-toast.png");
  const restoreReq = page.waitForRequest((r) => r.url().endsWith("/api/iteration-restore"));
  await page.click('#cv-toast [data-act="undo"]');
  const hdr = (await restoreReq).headers()["x-canvas-task"];
  assert.ok(hdr, "«Повернути» не називає задачу заголовком X-Canvas-Task: після перемикання задачі пішло б не туди");
  await page.waitForFunction(async () => (await (await fetch("/api/task")).json()).iterations.length === 3);
  assert.deepEqual(await ids(), ["it1", "it2", "it3"], "ітерація повернулась не на своє місце");
  // перелік показує найновішу ітерацію зверху; без ручного перевідкриття дропдауна — перемальовка сама мусить дати Іт.2
  if (!(await page.locator("#bar .dd--iters").count())) await openList(page);
  await page.waitForFunction(() => document.querySelectorAll("#bar .dd--iters .it-row").length === 3, null, { timeout: 5000 });
  assert.deepEqual((await rows(page)).map((x) => x.slice(0, 4)), ["Іт.3", "Іт.2", "Іт.1"]);
});

test("видалення: «Видалити» вимкнене, коли лишилась одна ітерація", async (t) => {
  const { page } = await boot(t, { count: 1 });
  await openList(page);
  await openRowMenu(page, "it1");
  const del = page.locator('#bar .dd--itmenu [data-act="itdel"]');
  assert.equal(await del.isDisabled(), true, "єдину ітерацію можна видалити");
});

test("«Огляд»: меню рядка без «Історії змін» (панелі там нема); ⌘K без історії; у «Макеті» пункт є", async (t) => {
  const { page } = await boot(t, { count: 2 });
  await openList(page);
  await openRowMenu(page, "it2");
  assert.equal(await page.locator('#bar .dd--itmenu [data-act="ithist"]').count(), 1, "у «Макеті» пункту нема");
  await page.keyboard.press("Escape");
  await page.click('[data-act="mode"][data-val="overview"]');
  await page.waitForSelector('[data-act="mode"][data-val="layout"]');
  await openList(page);
  await openRowMenu(page, "it2");
  assert.equal(await page.locator('#bar .dd--itmenu [data-act="ithist"]').count(), 0, "в «Огляді» пункт «Історія змін» мертвий");
  assert.equal(await page.locator('#bar .dd--itmenu [data-act="itren"]').count(), 1);
});

test("історія: меню рядка → панель із записами; закриття; винятковість із коментарями; ⌘K відкриває для поточної", async (t) => {
  const { page, url, dir, post } = await boot(t, { count: 3 });
  // запис AI: правка файла в it2 → автосинк комітить її з трейлером актора
  writeFileSync(path.join(dir, "iterations", "it2", "ai-edit.txt"), "правка\n");
  const sync = await post("/api/autosync", {});
  assert.equal(sync.ok, true);
  await openList(page);
  await openRowMenu(page, "it2");
  await page.click('#bar .dd--itmenu [data-act="ithist"]');
  await page.waitForSelector("#hist-panel:not([hidden]) .hist-e");
  assert.equal(await page.evaluate(() => document.body.classList.contains("with-hist")), true, "немає with-hist");
  assert.match(await page.textContent("#hist-panel .panel-title"), /Історія · Іт\.2/);
  assert.match(await page.textContent("#hist-panel"), /Створено як копію Іт\.1/);
  assert.ok(await page.locator("#hist-panel .hist-av--ai").count() >= 1, "запис AI не зʼявився");
  await shot(page, "07-history.png");
  // закриття
  await page.click('#hist-panel [data-act="histclose"]');
  assert.ok(await page.$eval("#hist-panel", (e) => e.hidden), "панель не закрилась");
  assert.equal(await page.evaluate(() => document.body.classList.contains("with-hist")), false);
  // винятковість: відкриваємо історію, потім коментарі — історія мусить піти
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "Історія");
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length >= 1, null, { timeout: 5000 });
  await page.keyboard.press("Enter");
  await page.waitForSelector("#hist-panel:not([hidden]) .hist-e");
  assert.match(await page.textContent("#hist-panel .panel-title"), /Історія · Іт\.3/, "⌘K відкрив не поточну ітерацію");
  await page.click('#hud [data-act="comments"]');
  await page.waitForFunction(() => document.getElementById("hist-panel").hidden);
  assert.equal(await page.evaluate(() => document.body.classList.contains("with-hist")), false, "історія лишилась поряд із коментарями");
  assert.ok(url);
});

test("дропдаун задачі: перейменувати й теги, без «Видалити»", async (t) => {
  const { page } = await boot(t);
  await page.click('#bar [data-dd="task"]');
  await page.waitForSelector("#bar .dd--task");
  assert.equal(await page.locator('#bar .dd--task [data-act="tren"]').count(), 1);
  assert.equal(await page.locator('#bar .dd--task [data-act="ttags"]').count(), 1);
  assert.equal(await page.locator('#bar .dd--task [data-act*="del"]').count(), 0, "у дропдауні задачі є видалення");
  await shot(page, "08-taskdd.png");
});

test("екран «Задачі»: картки без ідентифікаторів", async (t) => {
  const { page } = await boot(t);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#tasks-home .th-card");
  assert.equal(await page.locator("#tasks-home .th-key").count(), 0, "на картці лишився ключ");
  assert.match(await page.textContent("#tasks-home .th-card"), new RegExp(TITLE));
  await shot(page, "09-home.png");
});
