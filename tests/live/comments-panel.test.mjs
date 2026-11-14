/**
 * Панель «Коментарі» в оболонці, вид «Макет» (Deai 0.26.0, етап Б1, Task 7) — живе проведення.
 *
 * Юніти стережуть чисту модель і розмітку (`comments-model`, `comments-view`, `island`); режим хоста коментатора —
 * `commenter-host.test.mjs`. Тут те, чого вони не бачать: що оболонка додає `host=1` до адреси рамки, що відкрита
 * панель вмикає режим коментування, що картки ведуть живий коментатор (створити, закрити, повернути, редагувати,
 * перенести), що C/H ловляться і з фокусом в оболонці, і з фокусом у макеті, що інспектор і коментарі взаємно
 * виключні, що чужа посилка панелі не вірить, і що рамка, яка перейшла на адресу без `host=1`, повертається в режим хоста.
 *
 * Три сервери: A — звичайний (сценарії 1–9, 12, 13; піни створюються живою формою), B — із засіяним закритим піном
 * (10), C — з двома ітераціями й відкритим піном першої (11). Сервер D (Task 8, «Огляд») — фікстура T-45 із кадрами й
 * 9 посіяними пінами (сценарії 15–19): коментатор «Огляду» живе у вікні оболонки, а панель — та сама.
 */
import assert from "node:assert/strict";
import { cpSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";
import { seedPins, shootAll, t45Task } from "./_t45-fixture.mjs";

const PORT_BASE = 26100;
const SEEDED_PORT_BASE = 26200;
const TWO_IT_PORT_BASE = 26300;
const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px">
<main><h1 id="t">Заголовок</h1><p id="p">Абзац для коментаря</p></main></body></html>`;

const until = async (fn, ms = 15000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await fn()) return; await new Promise((r) => setTimeout(r, 100)); }
  throw new Error(`умова не виконалась за ${ms} мс`);
};
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const pinFp = { tag: "p", stableId: null, text: "Абзац для коментаря", textHash: "x", structHash: "x", styleHash: "x", path: ["p[0]"] };
const seedPin = (extra) => ({ author: "Клод", status: "open", fp: pinFp, htmlSnapshot: null, bornV: 1, ts: "13.11.2026 10:00", ...extra });

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Сервер + сторінка оболонки; `prepare(dir)` — засів файлів задачі до старту. Чекає, поки коментатор у рамці піднявся. */
async function boot(t, portBase, prepare) {
  /* `t.after` для сценаріїв, що мають власний сервер; для A (спільного) — `aCleanup`. */
  const after = t ? (f) => t.after(f) : (f) => aCleanup.push(f);
  const { dir } = taskFixture({ html: PAGE, pages: ["kartka"] });
  if (prepare) prepare(dir);
  const { child, url } = await startServer(dir, { portBase });
  after(() => child.kill());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  after(() => page.close());
  /* Усі посилки коментатора — у лічильник сторінки оболонки (сценарій 13: `ready` після повернення в режим хоста). */
  await page.addInitScript(() => {
    window.__cmtMsgs = [];
    window.addEventListener("message", (e) => { if (e.data && e.data.type === "dc-comments") window.__cmtMsgs.push(e.data.ev); });
  });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#hud [data-act="comments"]');
  const frame = await (await page.$("#frame")).contentFrame();
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  await until(() => page.evaluate(() => window.__cmtMsgs.includes("ready")));
  return { page, frame, url, dir };
}

const shadowShown = (frame, sel) => frame.evaluate((s) => {
  const el = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(s);
  return el ? getComputedStyle(el).display : null;
}, sel);
/* «Коментування ввімкнено» — через `tool().armed`: з host смужка `.modes` коментатора схована навмисно (режими — в острівці,
   0.27.0), тож `.modes.show` більше не ознака режиму. Імʼя лишене: його вживають 8 сценаріїв. */
const modesShown = (frame) => frame.evaluate(() => !!window.CommentLayer.tool().armed);
const panelOpen = (page) => page.evaluate(() => !document.getElementById("cmt-panel").hidden);
const cardTexts = (page) => page.$$eval("#cmt-panel .cmt-card .cmt-text", (els) => els.map((e) => e.textContent));
const panelText = (page) => page.textContent("#cmt-panel");
const islCount = (page) => page.evaluate(() => document.querySelector('#hud [data-act="comments"] .isl-count')?.textContent ?? null);
const inspectorOn = (page) => page.evaluate(() => !!document.getElementById("frame").contentWindow.CanvasInspector?.on);
/** Усі посилки коментатора до сторінки оболонки зараховуються з `addInitScript`; чекаємо, поки їх стане більше. */
const msgCount = (page, ev) => page.evaluate((e) => window.__cmtMsgs.filter((x) => x === e).length, ev);
/** Повідомлення вже в лічильнику, але обробник оболонки міг ще не відпрацювати: віддаємо йому кадр. */
const settle = (page) => page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
const fromFrame = (frame, snap) => frame.evaluate((sn) => parent.postMessage({ type: "dc-comments", ev: "change", snapshot: sn }, location.origin), snap);
const FAKE = { iteration: "1", comments: [{ id: "f", n: 99, text: "фейк", status: "open", scope: "current" }] };
const waitSnap = (page) => page.waitForSelector("#cmt-panel .cmt-sec");

async function addComment(frame, text) {
  await frame.click("#p");
  await frame.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await frame.evaluate((tx) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = tx; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await frame.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").click());
}

/* ───────── Сервер A: живе між сценаріями 1–9, 12, 13 (кожен спирається на стан попереднього) ───────── */
const A = {};
const aCleanup = [];
test.after(async () => { for (const f of aCleanup.reverse()) { try { await f(); } catch (e) { /* вже закрито */ } } });

test("1: у острівці є кнопка «Коментарі»; рамка — з host=1; ручка коментатора схована", async () => {
  Object.assign(A, await boot(null, PORT_BASE));
  const { page, frame } = A;
  assert.equal(await page.getAttribute('#hud [data-act="comments"]', "aria-pressed"), "false");
  assert.match(await page.getAttribute("#frame", "src"), /host=1/);
  assert.equal(await shadowShown(frame, ".handle"), "none");
});

test("2: клік по кнопці — панель видима, aria-pressed=true, body.with-cmt, у рамці режим коментування", async () => {
  const { page, frame } = A;
  await page.click('#hud [data-act="comments"]');
  await waitSnap(page);
  assert.equal(await panelOpen(page), true);
  assert.equal(await page.getAttribute('#hud [data-act="comments"]', "aria-pressed"), "true");
  assert.equal(await page.evaluate(() => document.body.classList.contains("with-cmt")), true);
  await until(() => modesShown(frame));
});

test("2б: режими коментування — в острівці (4 кнопки + заморозка), смужки коментатора нема, острівець не піднімається", async () => {
  const { page, frame } = A;
  const isl = () => page.evaluate(() => document.querySelector("#hud .island").getBoundingClientRect().bottom);
  const modes = () => page.$$eval('#hud [data-act="cmtmode"]', (els) => els.map((e) => [e.dataset.val, e.getAttribute("aria-pressed")]));
  assert.deepEqual(await modes(), [["element", "true"], ["text", "false"], ["multi", "false"], ["area", "false"]]);
  assert.equal(await page.getAttribute('#hud [data-act="cmtfreeze"]', "aria-pressed"), "true", "заморозка типово ввімкнена");
  assert.equal(await shadowShown(frame, ".modes"), "none", "смужка режимів коментатора видима поряд з острівцем");
  const bottomOpen = await isl();
  await page.click('#hud [data-act="cmtmode"][data-val="text"]');
  assert.equal(await frame.evaluate(() => window.CommentLayer.tool().mode), "text");
  assert.equal(await page.getAttribute('#hud [data-act="cmtmode"][data-val="text"]', "aria-pressed"), "true");
  assert.equal(await page.getAttribute('#hud [data-act="cmtmode"][data-val="element"]', "aria-pressed"), "false");
  await page.click('#hud [data-act="cmtfreeze"]');
  assert.equal(await frame.evaluate(() => document.documentElement.classList.contains("cl-freeze")), false);
  assert.equal(await page.getAttribute('#hud [data-act="cmtfreeze"]', "aria-pressed"), "false");
  await page.click('#hud [data-act="cmtfreeze"]');
  assert.equal(await frame.evaluate(() => document.documentElement.classList.contains("cl-freeze")), true);
  await page.click('#hud [data-act="cmtmode"][data-val="element"]');
  assert.equal(await frame.evaluate(() => window.CommentLayer.tool().mode), "element");
  /* Острівець той самий, що при закритій панелі: підйому (колишній claude-lift) нема. */
  await page.click('#hud [data-act="comments"]');
  await until(async () => (await modes()).length === 0);
  assert.equal(await isl(), bottomOpen, "острівець зсунувся між відкритою й закритою панеллю");
  await page.click('#hud [data-act="comments"]');
  await until(() => modesShown(frame));
});

test("3: клік по елементу + «Comment» → картка №1 у панелі й число 1 на кнопці острівця", async () => {
  const { page, frame } = A;
  await addComment(frame, "Зробити ширшим");
  await page.waitForSelector("#cmt-panel .cmt-card");
  assert.equal(await page.textContent("#cmt-panel .cmt-card .cmt-n"), "1");
  assert.deepEqual(await cardTexts(page), ["Зробити ширшим"]);
  assert.equal(await islCount(page), "1");
});

test("4: «Закрити» → розділ «Закриті (1)», числа нема; розгорнути → «Повернути» → знову відкрита", async () => {
  const { page } = A;
  await page.click('#cmt-panel [data-act="cmtres"]');
  await page.waitForSelector('#cmt-panel .cmt-fold[data-val="closed"]');
  assert.match(await page.textContent('#cmt-panel .cmt-fold[data-val="closed"]'), /Закриті \(1\)/);
  assert.equal(await islCount(page), null);
  await page.click('#cmt-panel .cmt-fold[data-val="closed"]');
  await page.click('#cmt-panel [data-act="cmtreopen"]');
  await until(async () => (await islCount(page)) === "1");
  assert.equal(!!(await page.$('#cmt-panel .cmt-fold[data-val="closed"]')), false, "після «Повернути» закритих не лишилось");
});

test("5: «Редагувати» → textarea.cmt-edit → нова думка → «Зберегти» → картка й файл задачі з новим текстом", async () => {
  const { page, dir } = A;
  await page.click('#cmt-panel [data-act="cmtedit"]');
  await page.waitForSelector("#cmt-panel textarea.cmt-edit");
  await page.fill("#cmt-panel textarea.cmt-edit", "Зробити значно ширшим");
  // Знімок коментатора приходить і сам (тут — від перемикача пінів): перемальовка не смій з'їсти набране.
  const n0 = await msgCount(page, "change");
  await A.frame.evaluate(() => { window.CommentLayer.togglePins(); window.CommentLayer.togglePins(); });
  await until(async () => (await msgCount(page, "change")) >= n0 + 2);
  await settle(page);
  assert.equal(await page.inputValue("#cmt-panel textarea.cmt-edit"), "Зробити значно ширшим", "чернетка редагування загубилась на перемальовці");
  await page.click('#cmt-panel [data-act="cmteditsave"]');
  await until(async () => (await cardTexts(page)).join() === "Зробити значно ширшим");
  assert.equal(!!(await page.$("#cmt-panel textarea.cmt-edit")), false);
  const file = path.join(dir, ".dc-local-comments.json");
  await until(() => { try { return JSON.parse(readFileSync(file, "utf8")).some((c) => c.text === "Зробити значно ширшим"); } catch (e) { return false; } });
});

test("6: клік по піну в рамці → .cmt-card--sel на цій картці", async () => {
  const { page, frame } = A;
  assert.equal(!!(await page.$("#cmt-panel .cmt-card--sel")), false, "до кліку вибраної картки нема");
  await frame.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".pin").click());
  await page.waitForSelector("#cmt-panel .cmt-card--sel");
  assert.equal(await panelOpen(page), true);
});

test("7: пошук #1 → одна картка; «нема-такого» → «Нічого не знайдено.»", async () => {
  const { page } = A;
  await page.fill("#cmt-q", "#1");
  await until(async () => (await page.$$("#cmt-panel .cmt-card")).length === 1);
  await page.fill("#cmt-q", "нема-такого");
  await until(async () => (await panelText(page)).includes("Нічого не знайдено."));
  assert.equal((await page.$$("#cmt-panel .cmt-card")).length, 0);
  await page.fill("#cmt-q", "");
  await until(async () => (await page.$$("#cmt-panel .cmt-card")).length === 1);
});

test("8: C з фокусом в оболонці закриває панель й режим; C з фокусом у макеті відкриває (обробник на вікні рамки)", async () => {
  const { page, frame } = A;
  await page.click("#bar", { position: { x: 3, y: 3 } });
  await page.keyboard.press("c");
  await until(async () => !(await panelOpen(page)));
  await until(async () => !(await modesShown(frame)));
  // Режим вимкнено: клік по макету не створює форми, а лише ставить у нього фокус.
  await frame.click("#t");
  await page.keyboard.press("c");
  await until(() => panelOpen(page));
  await until(() => modesShown(frame));
});

test("9: кнопка інспектора закриває панель; C знову — вимикає інспектор і відкриває панель", async () => {
  const { page } = A;
  await page.click('#hud [data-act="inspector"]');
  await until(async () => !(await panelOpen(page)));
  assert.equal(await inspectorOn(page), true);
  await page.keyboard.press("c");
  await until(() => panelOpen(page));
  assert.equal(await inspectorOn(page), false, "інспектор лишився ввімкненим поруч із режимом коментування");
});

test("9б: набір у формі коментатора й у полі редагування (C/H/Esc-літери, кирилиця) не закриває панель і не губить текст", async () => {
  const { page, frame } = A;
  assert.equal(await panelOpen(page), true);
  await frame.click("#p");
  await frame.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await page.keyboard.type("cc hh");
  // Українська розкладка: `code` лишається KeyC/KeyH, а `key` — «с»/«р». Подія з shadow DOM, як від справжнього набору.
  await frame.evaluate(() => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    for (const [key, code] of [["с", "KeyC"], ["р", "KeyH"], ["с", "KeyC"]]) {
      ta.dispatchEvent(new KeyboardEvent("keydown", { key, code, bubbles: true, composed: true, cancelable: true }));
    }
  });
  assert.equal(await panelOpen(page), true, "набір у формі коментатора закрив панель");
  assert.equal(await modesShown(frame), true, "набір у формі вимкнув режим коментування");
  assert.equal(await frame.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea")?.value), "cc hh");
  await frame.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .cancel").click());
  // Поле редагування в панелі оболонки.
  await page.click('#cmt-panel [data-act="cmtedit"]');
  await page.waitForSelector("#cmt-panel textarea.cmt-edit");
  await page.fill("#cmt-panel textarea.cmt-edit", "");
  await page.keyboard.type("cc hh");
  assert.equal(await panelOpen(page), true);
  assert.equal(await page.inputValue("#cmt-panel textarea.cmt-edit"), "cc hh");
  await page.click('#cmt-panel [data-act="cmteditcancel"]');
});

test("9в: адреса рамки з host=0 повертається в режим хоста одним переходом, без петлі й без двох host", async () => {
  const { page, frame } = A;
  const base = (await page.getAttribute("#frame", "src")).replace(/&host=1/, "");
  let navs = 0;
  const onNav = (f) => { if (f === frame) navs += 1; };
  page.on("framenavigated", onNav);
  await page.evaluate(() => { window.__cmtMsgs.length = 0; });
  await frame.evaluate((u) => { location.href = u; }, `${base}&host=0`);
  await until(() => page.evaluate(() => window.__cmtMsgs.includes("ready")));
  await pause(1500); // петля дала б нові переходи
  page.off("framenavigated", onNav);
  assert.equal([...frame.url().matchAll(/host=/g)].length, 1, `кілька host у ${frame.url()}`);
  assert.match(frame.url(), /host=1/);
  assert.ok(navs <= 2, `рамка перезавантажується знову й знову: ${navs} переходів`);
});

test("12: підроблена посилка від самої оболонки (не від рамки) панель не змінює", async () => {
  const { page, frame } = A;
  // Контроль: ТА САМА посилка від рамки — доходить (інакше відсутність нижче нічого не доводила б).
  const n0 = await msgCount(page, "change");
  await fromFrame(frame, FAKE);
  await until(async () => (await msgCount(page, "change")) > n0);
  await until(async () => (await panelText(page)).includes("фейк"));
  // Справжній знімок від коментатора витісняє підробку.
  await frame.evaluate(() => { window.CommentLayer.togglePins(); window.CommentLayer.togglePins(); });
  await until(async () => !(await panelText(page)).includes("фейк"));
  // Від самої оболонки — ігнорується.
  const n1 = await msgCount(page, "change");
  await page.evaluate((sn) => window.postMessage({ type: "dc-comments", ev: "change", snapshot: sn }, "*"), FAKE);
  await until(async () => (await msgCount(page, "change")) > n1);
  await settle(page);
  assert.equal((await panelText(page)).includes("фейк"), false, "чужа посилка потрапила в панель");
});

test("13: рамка, що перейшла на адресу без host=1 (старий пін), повертається в режим хоста: ready, ручки нема", async () => {
  const { page, frame } = A;
  const bare = (await page.getAttribute("#frame", "src")).replace(/&host=1/, "");
  assert.equal(bare.includes("host=1"), false);
  await page.evaluate(() => { window.__cmtMsgs.length = 0; });
  await frame.evaluate((u) => { location.href = u; }, bare);
  await until(() => page.evaluate(() => window.__cmtMsgs.includes("ready")));
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited);
  assert.match(frame.url(), /host=1/);
  assert.equal(await shadowShown(frame, ".handle"), "none");
});

/* ───────── Сервер B: закритий пін із тим, що зробив Клод ───────── */
test("10: закритий пін показує «Зроблено · Іт.1» і причину від Клода", async (t) => {
  const { page } = await boot(t, SEEDED_PORT_BASE, (dir) => {
    writeFileSync(path.join(dir, ".dc-local-comments.json"), JSON.stringify([seedPin({
      id: "r1", text: "Кнопка вузька", status: "resolved", resolvedV: 1, resolveReason: "Зробив кнопку ширшою",
      meta: { iteration: "1", version: "1", seq: 7, viewport: { w: 1280, h: 900 } },
    })]));
  });
  await page.click('#hud [data-act="comments"]');
  await page.waitForSelector('#cmt-panel .cmt-fold[data-val="closed"]');
  await page.click('#cmt-panel .cmt-fold[data-val="closed"]');
  const txt = await panelText(page);
  assert.match(txt, /Зроблено · Іт\.1/);
  assert.match(txt, /Зробив кнопку ширшою/);
});

/* ───────── Сервер C: дві ітерації, відкритий пін першої ───────── */
test("11: відкритий пін ітерації 1 при відкритій ітерації 2 — «З попередніх ітерацій», перенос дає копію у відкритих", async (t) => {
  const { page } = await boot(t, TWO_IT_PORT_BASE, (dir) => {
    cpSync(path.join(dir, "iterations", "it1"), path.join(dir, "iterations", "it2"), { recursive: true });
    writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({ iterations: [
      { id: "it1", date: "24.08.2026 12:00", note: "перша", published: true },
      { id: "it2", date: "25.08.2026 12:00", note: "друга", published: true }] }));
    writeFileSync(path.join(dir, ".dc-local-comments.json"), JSON.stringify([seedPin({
      id: "o1", text: "Лишилось з першої", meta: { iteration: "1", version: "1", seq: 3, viewport: { w: 1280, h: 900 } },
    })]));
  });
  assert.match(await page.getAttribute("#frame", "src"), /it=it2/);
  await page.click('#hud [data-act="comments"]');
  await page.waitForSelector('#cmt-panel .cmt-fold[data-val="earlier"]');
  assert.match(await page.textContent('#cmt-panel .cmt-fold[data-val="earlier"]'), /З попередніх ітерацій \(1\)/);
  await page.click('#cmt-panel .cmt-fold[data-val="earlier"]');
  assert.match(await page.textContent('#cmt-panel [data-act="cmtcarry"]'), /Перенести в Іт\.2/);
  await page.click('#cmt-panel [data-act="cmtcarry"]');
  await until(async () => (await islCount(page)) === "1");
  const open = await page.$$eval('#cmt-panel .cmt-sec[aria-label="Відкриті"] .cmt-card .cmt-text', (els) => els.map((e) => e.textContent));
  assert.deepEqual(open, ["Лишилось з першої"]);
});

/* ───────── Сервер A, останній сценарій: запізніла посилка старого документа ───────── */
test("14: поки готовності нового документа нема, `change` із рамки не повертає старих карток", async () => {
  const { page, frame } = A;
  /* Детерміновано: скрипт коментатора не віддаємо → нова сторінка рамки (після повернення в host=1) НІКОЛИ не пошле
     `ready`, тобто `frameCmtReady` лишається false. Посилку «старого документа» шлемо з неї ж самої. */
  await page.route("**/comment-layer.min.js", (r) => r.abort());
  const base = (await page.getAttribute("#frame", "src")).replace(/&host=1/, "");
  await frame.evaluate((u) => { location.href = u; }, base);
  await until(() => frame.url().includes("host=1") && frame.evaluate(() => document.readyState === "complete").catch(() => false));
  await pause(500);
  const n0 = await msgCount(page, "change");
  await fromFrame(frame, { ...FAKE, comments: [{ ...FAKE.comments[0], text: "застарілий" }] });
  await until(async () => (await msgCount(page, "change")) > n0);
  await settle(page);
  assert.equal((await panelText(page)).includes("застарілий"), false, "запізніла посилка старого документа повернула картку");
  await page.unroute("**/comment-layer.min.js");
});

/* ───────── Сервер A, продовження: рамка без коментатора, чужий origin, C у чистому вигляді й під діалогом ───────── */
/** Рамка знову на коментованій сторінці в режимі хоста; чекає `ready` і картки. */
async function backToLayer() {
  const { page } = A;
  const base = (await page.getAttribute("#frame", "src")).replace(/&host=1/, "");
  await page.evaluate(() => { window.__cmtMsgs.length = 0; });
  // З боку оболонки, а не з документа рамки: із чужого origin навігація йшла б як міжсайтова й сервер її відхиляє.
  await page.evaluate((u) => { document.getElementById("frame").src = u; }, base);
  await until(() => page.evaluate(() => window.__cmtMsgs.includes("ready")));
  await until(async () => (await cardTexts(A.page)).length > 0);
}
const keyC = (frame) => frame.evaluate(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "c", code: "KeyC", bubbles: true, cancelable: true })));

test("21: M-2 — рамка перейшла на сторінку того ж походження без коментатора: старі картки зникають, не лишаються з мертвими діями", async () => {
  const { page, frame, url } = A;
  await backToLayer();
  assert.equal(await panelOpen(page), true);
  await frame.evaluate((u) => { location.href = u; }, `${url}/app/esc.js`);
  await until(async () => (await cardTexts(page)).length === 0);
  assert.equal((await page.$$("#cmt-panel .cmt-card")).length, 0, "картки без живого коментатора лишились");
  assert.match(await panelText(page), /Коментатор завантажується/);
  await backToLayer();
});

test("22: M-1 — рамка пішла на чужий origin: картки зникають, а посилка звідти (source збігається, origin ні) панель не змінює", async () => {
  const { page, frame } = A;
  await backToLayer();
  await page.route("http://other.test/**", (r) => r.fulfill({ status: 200, contentType: "text/html; charset=utf-8", body: `<!DOCTYPE html><title>x</title><script>
    window.addEventListener("message", (e) => {
      if (e.data !== "forge") return;
      parent.postMessage({ type: "dc-comments", ev: "ready" }, "*");
      parent.postMessage({ type: "dc-comments", ev: "change", snapshot: { iteration: "1", comments: [{ id: "f", n: 99, text: "foreign-origin", status: "open", scope: "current" }] } }, "*");
    });</script>` }));
  await frame.evaluate(() => { location.href = "http://other.test/x"; });
  await until(async () => (await cardTexts(page)).length === 0);
  const n0 = await msgCount(page, "change");
  await page.evaluate(() => document.getElementById("frame").contentWindow.postMessage("forge", "*"));
  await until(async () => (await msgCount(page, "change")) > n0);
  await settle(page);
  assert.equal((await panelText(page)).includes("foreign-origin"), false, "посилка з чужого origin потрапила в панель");
  await page.unroute("http://other.test/**");
  await backToLayer();
});

test("23: M-4 — у чистому вигляді C не вмикає коментування ні з оболонки, ні з макета", async () => {
  const { page, frame } = A;
  await backToLayer();
  await page.click("#bar", { position: { x: 3, y: 3 } });
  await page.keyboard.press("c");
  await until(async () => !(await panelOpen(page)));
  await page.keyboard.press("ControlOrMeta+Shift+Backslash");
  await until(() => page.evaluate(() => document.documentElement.classList.contains("cv-clean")));
  // Окремо: два перемикання поспіль гасили б одне одного, і зламана охорона лишилась би непоміченою.
  await page.keyboard.press("c");
  await pause(400);
  assert.equal(await panelOpen(page), false, "C з оболонки у чистому вигляді відкрила панель");
  assert.equal(await modesShown(frame), false, "C з оболонки у чистому вигляді запустила коментатора");
  await keyC(frame);
  await pause(400);
  assert.equal(await panelOpen(page), false, "C з макета у чистому вигляді відкрила панель");
  assert.equal(await modesShown(frame), false, "C з макета у чистому вигляді запустила коментатора");
  await page.keyboard.press("ControlOrMeta+Shift+Backslash");
  await until(() => page.evaluate(() => !document.documentElement.classList.contains("cv-clean")));
  await page.keyboard.press("c");
  await until(() => panelOpen(page)); // контроль: поза чистим виглядом та сама клавіша працює
});

test("24: M-5 — під відкритим діалогом оболонки (відгук) C не перемикає панель: ні з фокусом на кнопці діалогу, ні з макета", async () => {
  const { page, frame } = A;
  assert.equal(await panelOpen(page), true);
  await page.click('#hud [data-act="feedback"]');
  await page.waitForSelector(".cv-ask-scrim");
  await page.locator(".cv-ask-scrim button").first().focus();
  await page.keyboard.press("c");
  await keyC(frame);
  await pause(400);
  assert.equal(await panelOpen(page), true, "C під діалогом закрила панель");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  assert.equal(await panelOpen(page), true, "Esc діалогу закрив ще й панель");
});

test("25: M-3 — зміна ітерації скидає вибір і редагування: після `ready` нового документа їх нема (id належать старому)", async (t) => {
  const { page } = await boot(t, TWO_IT_PORT_BASE + 50, (dir) => {
    cpSync(path.join(dir, "iterations", "it1"), path.join(dir, "iterations", "it2"), { recursive: true });
    writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({ iterations: [
      { id: "it1", date: "24.08.2026 12:00", note: "перша", published: true },
      { id: "it2", date: "25.08.2026 12:00", note: "друга", published: true }] }));
    writeFileSync(path.join(dir, ".dc-local-comments.json"), JSON.stringify([seedPin({
      id: "o1", text: "Лишилось з першої", meta: { iteration: "1", version: "1", seq: 3, viewport: { w: 1280, h: 900 } },
    })]));
  });
  const pick = async (id) => {
    await page.evaluate(() => { window.__cmtMsgs.length = 0; });
    await page.locator('[data-dd="iter"]').click();
    await page.locator(`.dd [data-act="iter"][data-val="${id}"]`).click();
    await until(() => page.evaluate(() => window.__cmtMsgs.includes("ready")));
  };
  await pick("it1");
  await page.click('#hud [data-act="comments"]');
  await page.waitForSelector('#cmt-panel .cmt-card[data-cid="o1"]');
  await page.click('#cmt-panel [data-act="cmtshow"]');
  await page.click('#cmt-panel [data-act="cmtedit"]');
  await page.waitForSelector("#cmt-panel textarea.cmt-edit");
  assert.ok(await page.$("#cmt-panel .cmt-card--sel"));
  await pick("it2");
  await page.waitForSelector('#cmt-panel .cmt-fold[data-val="earlier"]');
  await page.click('#cmt-panel .cmt-fold[data-val="earlier"]');
  await page.waitForSelector('#cmt-panel .cmt-card[data-cid="o1"]');
  assert.equal(!!(await page.$("#cmt-panel textarea.cmt-edit")), false, "редагування старого документа пережило зміну ітерації");
  assert.equal(!!(await page.$("#cmt-panel .cmt-card--sel")), false, "вибір старого документа пережив зміну ітерації");
});

/* ───────── Сервер D: «Огляд» (Task 8). Коментатор полотна — у вікні оболонки; панель — та сама, що в «Макеті» ───────── */
const D = {};
const OVR_PORT_BASE = 26400;
const canvasHost = () => document.querySelector("#canvas [data-comment-layer]");
const camNow = (page) => page.evaluate(() => {
  const m = /translate\(([-\d.e]+)px,\s*([-\d.e]+)px\)\s*scale\(([-\d.e]+)\)/.exec(document.getElementById("world").style.transform);
  return { x: +m[1], y: +m[2], s: +m[3] };
});
const composeText = (page) => page.evaluate(() => document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(".compose textarea")?.value ?? null);
const cmtNotes = (page) => page.$$eval("#cmt-panel .cmt-note", (els) => els.length);
const pressAt = async (page, x, y) => { await page.mouse.move(x, y); await page.mouse.down(); await page.mouse.up(); };

test("15: «Огляд» — з відкритою панеллю ті самі картки, але полотна (без приміток «на іншій сторінці»); ручка коментатора полотна схована", async () => {
  const { dir } = t45Task();
  const server = await startServer(dir, { portBase: OVR_PORT_BASE, title: "Огляд" });
  aCleanup.push(() => server.child.kill());
  const comments = await seedPins(browser, server.url);
  const shot = await shootAll(server.url);
  assert.ok(shot.ok, `зʼємка: ${JSON.stringify(shot).slice(0, 300)}`);
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  aCleanup.push(() => page.close());
  await page.addInitScript(() => {
    window.__cmtMsgs = [];
    window.addEventListener("message", (e) => { if (e.data && e.data.type === "dc-comments") window.__cmtMsgs.push(e.data.ev); });
  });
  await page.goto(`${server.url}/app/`);
  const frame = await (await page.waitForSelector("#frame")).contentFrame();
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  await until(() => page.evaluate(() => window.__cmtMsgs.includes("ready")));
  Object.assign(D, { page, frame, server, comments });
  // Макет: панель відкрита, у рамці є примітки «на іншій сторінці» (піни «Пошуку» при відкритій «Головній»).
  await page.click('#hud [data-act="comments"]');
  await waitSnap(page);
  await until(async () => (await cmtNotes(page)) > 0);
  // Вибір і редагування в Макеті — не мусять переживати перемикання виду.
  await page.click('#cmt-panel [data-act="cmtedit"]');
  await page.waitForSelector("#cmt-panel textarea.cmt-edit");
  await page.fill("#cmt-panel textarea.cmt-edit", "чернетка з Макета");
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]")?.shadowRoot?.querySelectorAll(".cp").length);
  await until(async () => (await cmtNotes(page)) === 0);
  assert.equal(await panelOpen(page), true, "панель закрилась при вході в «Огляд»");
  assert.equal(!!(await page.$("#cmt-panel textarea.cmt-edit")), false, "редагування Макета пережило перемикання виду");
  assert.equal(!!(await page.$("#cmt-panel .cmt-card--sel")), false, "вибір Макета пережив перемикання виду");
  assert.equal((await page.$$("#cmt-panel .cmt-card")).length, comments.length, "картки — не ті, що в пінів полотна");
  assert.equal(await islCount(page), String(comments.length));
  // Режим коментування: у полотна ввімкнено, у рамки вимкнено; ручка й панель коментатора полотна схованi.
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), true);
  assert.equal(await frame.evaluate(() => !!window.CommentLayer.commentMode), false, "коментатор рамки лишився в режимі на «Огляді»");
  const hidden = await page.evaluate(() => {
    const r = document.querySelector("#canvas [data-comment-layer]").shadowRoot;
    return ["handle", "panel"].map((c) => getComputedStyle(r.querySelector("." + c)).display);
  });
  assert.deepEqual(hidden, ["none", "none"]);
});

test("16: «Огляд» — «Показати» рухає камеру; C закриває й знову відкриває панель; закрити/повернути ведуть коментатор полотна", async () => {
  const { page } = D;
  const target = "t45-poshuk-1";
  const cam0 = await camNow(page);
  await page.click(`#cmt-panel [data-cid="${target}"] [data-act="cmtshow"]`);
  await until(async () => { const c = await camNow(page); return Math.abs(c.x - cam0.x) > 20 || Math.abs(c.y - cam0.y) > 20 || Math.abs(c.s - cam0.s) > 0.01; });
  await page.waitForSelector(`#cmt-panel [data-cid="${target}"].cmt-card--sel`);
  // Закрити → картка в «Закриті»; повернути → знову відкрита (дії ідуть у шар полотна, а не в рамку).
  await page.click(`#cmt-panel [data-cid="${target}"] [data-act="cmtres"]`);
  await page.waitForSelector('#cmt-panel .cmt-fold[data-val="closed"]');
  assert.equal(await islCount(page), String(D.comments.length - 1));
  await page.click('#cmt-panel .cmt-fold[data-val="closed"]');
  await page.click(`#cmt-panel [data-cid="${target}"] [data-act="cmtreopen"]`);
  await until(async () => (await islCount(page)) === String(D.comments.length));
  // C із фокусом в оболонці.
  await page.click("#bar", { position: { x: 3, y: 3 } });
  await page.keyboard.press("c");
  await until(async () => !(await panelOpen(page)));
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), false, "C не вимкнув режим полотна");
  await page.keyboard.press("c");
  await until(() => panelOpen(page));
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), true);
});

test("17: «Огляд» — клік по кадру в режимі коментування → форма; набір «с/р/cc hh» у формі не перемикає панель і не губить текст (shadow DOM документа оболонки)", async () => {
  const { page } = D;
  await page.waitForTimeout(450);
  /* Після «Показати» камера стоїть на піні «Пошуку» — клікаємо в центр видимої частини його кадру. */
  const at = await page.evaluate(() => {
    const r = document.querySelector('.cv-card[data-key="poshuk"] .cv-card-body').getBoundingClientRect();
    const c = document.getElementById("canvas").getBoundingClientRect();
    const l = Math.max(r.left, c.left), rr = Math.min(r.right, c.right), tp = Math.max(r.top, c.top), bt = Math.min(r.bottom, c.bottom);
    return { x: (l + rr) / 2, y: (tp + bt) / 2 };
  });
  await page.mouse.move(at.x, at.y); await page.waitForTimeout(100);
  await pressAt(page, at.x, at.y);
  await until(async () => (await composeText(page)) !== null);
  await page.keyboard.type("cc hh");
  // Українська розкладка: `code` лишається KeyC/KeyH, а `key` — «с»/«р»; подія — з тіньового DOM, як від справжнього набору.
  await page.evaluate(() => {
    const ta = document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    for (const [key, code] of [["с", "KeyC"], ["р", "KeyH"], ["с", "KeyC"]]) {
      ta.dispatchEvent(new KeyboardEvent("keydown", { key, code, bubbles: true, composed: true, cancelable: true }));
    }
  });
  assert.equal(await panelOpen(page), true, "набір у формі коментатора полотна закрив панель");
  assert.equal(await composeText(page), "cc hh", "форма зникла або текст втрачено");
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), true, "режим вимкнено під час набору");
});

test("18: «Огляд» — Esc із формою закриває ЛИШЕ форму; наступний Esc виходить із режиму й закриває панель", async () => {
  const { page } = D;
  assert.notEqual(await composeText(page), null, "форма з попереднього сценарію зникла");
  await page.keyboard.press("Escape");
  await until(async () => (await composeText(page)) === null);
  assert.equal(await panelOpen(page), true, "перший Esc закрив усю панель разом із формою");
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), true, "перший Esc вимкнув режим");
  await page.keyboard.press("Escape");
  await until(async () => !(await panelOpen(page)));
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), false);
});

test("18б: «Огляд» — Esc у полі редагування картки скасовує редагування, а не виходить із режиму й не закриває панель", async () => {
  const { page } = D;
  await page.keyboard.press("c");
  await until(() => panelOpen(page));
  await page.click('#cmt-panel [data-act="cmtedit"]');
  await page.waitForSelector("#cmt-panel textarea.cmt-edit");
  await page.fill("#cmt-panel textarea.cmt-edit", "правка");
  await page.press("#cmt-panel textarea.cmt-edit", "Escape");
  await page.waitForFunction(() => !document.querySelector("#cmt-panel textarea.cmt-edit"));
  assert.equal(await panelOpen(page), true, "Esc у редагуванні закрив панель");
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), true, "Esc у редагуванні вимкнув режим");
});

test("19: назад у «Макет» — панель лишається відкритою, режим рамки знову увімкнено, картки — рамки; подія полотна в Макеті не діє", async () => {
  const { page, frame } = D;
  assert.equal(await panelOpen(page), true);
  await page.getByRole("button", { name: /Макет/ }).click();
  await page.waitForFunction(() => document.getElementById("canvas").hidden);
  await until(async () => (await cmtNotes(page)) > 0);
  assert.equal(await panelOpen(page), true, "панель закрилась при поверненні в «Макет»");
  await until(() => modesShown(frame));
  const own = await frame.evaluate(() => window.CommentLayer.snapshot().comments.map((c) => c.text).sort());
  const shown = (await cardTexts(page)).slice().sort();
  assert.deepEqual(shown, own, "картки Макета ≠ знімок коментатора рамки");
  // Запізніла подія коментатора полотна в Макеті ігнорується (поправка 11).
  await page.evaluate(() => window.postMessage({ type: "dc-comments", ev: "mode", on: false }, "*"));
  await settle(page);
  assert.equal(await panelOpen(page), true);
});

test("19б: «Огляд» — кнопок режимів нема (один режим), у «Макеті» вони повертаються, а з закритою панеллю зникають", async () => {
  const { page } = D;
  const n = () => page.$$eval('#hud [data-act="cmtmode"]', (els) => els.length);
  assert.equal(await n(), 4, "у «Макеті» з відкритою панеллю мало б бути 4 режими");
  await page.click('[data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  await until(async () => (await n()) === 0);
  assert.equal(await page.$$eval('#hud [data-act="cmtfreeze"]', (els) => els.length), 0, "на «Огляді» кнопка заморозки");
  await page.click('[data-act="mode"][data-val="layout"]');
  await until(async () => (await n()) === 4);
  await page.click('#hud [data-act="comments"]');
  await until(async () => (await n()) === 0);
});
