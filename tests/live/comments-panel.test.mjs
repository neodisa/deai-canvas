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
 * (10), C — з двома ітераціями й відкритим піном першої (11).
 */
import assert from "node:assert/strict";
import { cpSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

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
const modesShown = (frame) => frame.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".modes.show"));
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
  assert.equal(await page.$('#cmt-panel .cmt-fold[data-val="closed"]'), null, "після «Повернути» закритих не лишилось");
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
  assert.equal(await page.$("#cmt-panel textarea.cmt-edit"), null);
  const file = path.join(dir, ".dc-local-comments.json");
  await until(() => { try { return JSON.parse(readFileSync(file, "utf8")).some((c) => c.text === "Зробити значно ширшим"); } catch (e) { return false; } });
});

test("6: клік по піну в рамці → .cmt-card--sel на цій картці", async () => {
  const { page, frame } = A;
  assert.equal(await page.$("#cmt-panel .cmt-card--sel"), null, "до кліку вибраної картки нема");
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
