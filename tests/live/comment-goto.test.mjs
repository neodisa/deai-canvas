/**
 * «Показати» в панелі «Коментарі» веде до коментаря, де б він не жив (0.39.1) — живе проведення.
 *
 * Раніше `focus(id)` коментатора скролив лише до елемента В ЦЬОМУ документі: картка з іншої сторінки чи ітерації мала «Показати»,
 * але клік нічого не робив. Тепер `focus` повертає `false`, а оболонка веде на ітерацію й сторінку з тегу версії піна тими ж
 * кроками, що й клік користувача, і доводить показ, коли новий коментатор шле `ready`.
 *
 * Фікстура: дві ітерації (it1, it2), дві сторінки (holovna, poshuk), піни засіяні файлом задачі у тій формі, яку пише коментатор.
 * Картка «з попередніх ітерацій» «Показати» не має (лише «Перенести»), тож міжітераційний перехід перевіряємо з карткою, яку
 * оболонці повертає змінений знімок: у ньому скоуп піна it1 підроблено на `current` (так він виглядає в «Нове»).
 */
import assert from "node:assert/strict";
import { cpSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 49000;
const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px">
<main><h1 id="t">Заголовок</h1><div style="height:2400px"></div><p id="p">Абзац для коментаря</p></main></body></html>`;

const until = async (fn, ms = 15000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await fn()) return; await new Promise((r) => setTimeout(r, 100)); }
  throw new Error(`умова не виконалась за ${ms} мс`);
};
const pinFp = { tag: "p", stableId: null, text: "Абзац для коментаря", textHash: "x", structHash: "x", styleHash: "x", path: ["p[0]"] };
const seedPin = (extra) => ({ author: "Клод", status: "open", fp: pinFp, htmlSnapshot: null, bornV: 1, ts: "13.11.2026 10:00", ...extra });

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Сервер з it1+it2; відкрита it2. `pins` — піни, що лягають у файл задачі до старту. Чекає `ready` коментатора рамки. */
async function boot(t, portOff, pins, { openPanel = true, filter = null } = {}) {
  const { dir } = taskFixture({ html: PAGE });
  cpSync(path.join(dir, "iterations", "it1"), path.join(dir, "iterations", "it2"), { recursive: true });
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({ iterations: [
    { id: "it1", date: "24.08.2026 12:00", note: "перша", published: true },
    { id: "it2", date: "25.08.2026 12:00", note: "друга", published: true }] }));
  writeFileSync(path.join(dir, ".dc-local-comments.json"), JSON.stringify(pins));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + portOff });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  t.after(() => page.close());
  if (filter) await page.addInitScript((f) => { try { localStorage.setItem("dc-cmt-filter", f); } catch (e) {} }, filter);
  await page.addInitScript(() => {
    window.__cmtMsgs = [];
    window.addEventListener("message", (e) => { if (e.data && e.data.type === "dc-comments") window.__cmtMsgs.push(e.data.ev); });
  });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#hud [data-act="comments"]');
  await until(() => page.evaluate(() => window.__cmtMsgs.includes("ready")));
  if (openPanel) {
    await page.click('#hud [data-act="comments"]');
    await page.waitForSelector("#cmt-panel .cmt-sec");
  }
  return { page };
}

const fr = (page) => page.evaluate(() => document.getElementById("frame").contentWindow);
const frameOf = async (page) => (await (await page.$("#frame")).contentFrame());
const src = (page) => page.getAttribute("#frame", "src");
const selTexts = (page) => page.$$eval("#cmt-panel .cmt-card--sel .cmt-text", (e) => e.map((x) => x.textContent));
const showBtn = (page, text) => page.locator(`#cmt-panel .cmt-card:has-text("${text}") [data-act="cmtshow"]`);
const toastText = (page) => page.evaluate(() => { const el = document.getElementById("cv-toast"); return el && el.classList.contains("show") ? el.textContent : null; });
/** Елемент `#p` у вікні рамки (після плавного скролу). */
const pInView = async (page) => {
  const f = await frameOf(page);
  return f.evaluate(() => { const r = document.getElementById("p").getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
};
/** Знімок коментатора рамки, у якому скоуп піна `id` підроблено на `current` (так він виглядає у «Нове» з кнопкою «Показати»). */
async function fakeCurrent(page, id, patch = {}) {
  const f = await frameOf(page);
  const snap = await f.evaluate(() => window.CommentLayer.snapshot());
  snap.comments = snap.comments.map((c) => (c.id === id ? { ...c, scope: "current", where: "elsewhere", ...patch } : c));
  await f.evaluate((sn) => parent.postMessage({ type: "dc-comments", ev: "change", snapshot: sn }, location.origin), snap);
  await page.waitForSelector(`#cmt-panel .cmt-card[data-cid="${id}"] [data-act="cmtshow"]`);
}

test("1: «Показати» на картці іншої сторінки тієї ж ітерації веде на цю сторінку; картка вибрана, елемент у кадрі", async (t) => {
  const { page } = await boot(t, 0, [seedPin({ id: "p1", text: "На пошуку", meta: { iteration: "2", version: "2/poshuk", seq: 1, viewport: { w: 1440, h: 900 } } })]);
  assert.match(await src(page), /it=it2/);
  assert.doesNotMatch(await src(page), /page=poshuk/);
  await showBtn(page, "На пошуку").click();
  await until(async () => /page=poshuk/.test(await src(page)));
  assert.match(await src(page), /it=it2/);
  await until(async () => (await selTexts(page)).includes("На пошуку"));
  await until(() => pInView(page));
  assert.equal(await page.evaluate(() => !document.getElementById("cmt-panel").hidden), true, "панель коментарів лишилась відкритою");
});

test("2: «Показати» на картці іншої ітерації веде на її ітерацію й сторінку, зберігаючи ширину мобайла", async (t) => {
  const { page } = await boot(t, 100, [seedPin({ id: "p2", text: "З першої ітерації", meta: { iteration: "1", version: "1/poshuk", seq: 1, viewport: { w: 1440, h: 900 } } })]);
  await page.click('#bar [data-act="vp"][data-val="mobile"]');
  await until(async () => (await page.evaluate(() => document.getElementById("frame").getBoundingClientRect().width)) < 500);
  const w0 = await page.evaluate(() => document.getElementById("frame").getBoundingClientRect().width);
  await fakeCurrent(page, "p2");
  await showBtn(page, "З першої ітерації").click();
  await until(async () => /it=it1/.test(await src(page)) && /page=poshuk/.test(await src(page)));
  await until(async () => (await selTexts(page)).includes("З першої ітерації"));
  await until(() => pInView(page));
  assert.equal(await page.evaluate(() => document.getElementById("frame").getBoundingClientRect().width), w0, "ширина вьюпорта збережена");
  assert.equal(await page.evaluate(() => !document.getElementById("cmt-panel").hidden), true);
});

test("3: ціль без розбору — мовчки; ітерації чи сторінки в цілі нема — тост; рамка не рухається ні в одному випадку", async (t) => {
  const { page } = await boot(t, 200, [
    seedPin({ id: "g1", text: "Зниклий", meta: { iteration: "99", version: "99/zzz", seq: 1, viewport: { w: 1440, h: 900 } } }),
    seedPin({ id: "g2", text: "Без тегу", meta: { route: "/commented", seq: 2, viewport: { w: 1440, h: 900 } } }),
    seedPin({ id: "g3", text: "Нема сторінки", meta: { iteration: "2", version: "2/zzz", seq: 3, viewport: { w: 1440, h: 900 } } }),
  ]);
  const before = await src(page);
  const hide = () => page.evaluate(() => document.getElementById("cv-toast")?.classList.remove("show"));
  for (const [id, text] of [["g1", "Зниклий"], ["g3", "Нема сторінки"]]) {
    await fakeCurrent(page, id);
    await showBtn(page, text).click();
    await until(async () => /Не вдалося знайти/.test((await toastText(page)) || ""));
    assert.equal(await src(page), before, `${id}: рамка не мусить рухатись`);
    await hide();
  }
  await fakeCurrent(page, "g2");
  await showBtn(page, "Без тегу").click();
  await new Promise((r) => setTimeout(r, 1200));
  assert.equal(await toastText(page), null, "нерозбірлива ціль — без нового повідомлення");
  assert.equal(await src(page), before);
});

test("4: «Показати» на тій самій сторінці скролить до елемента без переходу", async (t) => {
  const { page } = await boot(t, 300, [seedPin({ id: "s1", text: "Тут же", meta: { iteration: "2", version: "2/holovna", seq: 1, viewport: { w: 1440, h: 900 } } })]);
  const before = await src(page);
  await showBtn(page, "Тут же").click();
  await until(() => pInView(page));
  await until(async () => (await selTexts(page)).includes("Тут же"));
  assert.equal(await src(page), before);
});

test("5: тост «нового коментаря» на іншій сторінці: «Показати» веде туди й вибирає картку", async (t) => {
  const { page } = await boot(t, 400, [seedPin({ id: "nw", text: "Нове від Олени", author: "Олена", meta: { iteration: "2", version: "2/poshuk", seq: 1, viewport: { w: 1440, h: 900 } } })], { openPanel: false, filter: "all" });
  const f = await frameOf(page);
  const snap = await f.evaluate(() => window.CommentLayer.snapshot());
  const post = (comments) => f.evaluate((sn) => parent.postMessage({ type: "dc-comments", ev: "change", snapshot: sn }, location.origin), { ...snap, comments });
  /* Спершу знімок без нього (маркер «бачив» уже є), потім із ним як командним: так він «надходить». */
  await post(snap.comments.filter((c) => c.id !== "nw"));
  await post(snap.comments.map((c) => (c.id === "nw" ? { ...c, _aud: "project", where: "elsewhere" } : c)));
  const btn = page.locator('.cv-notice [data-act="cmtshownew"]');
  await btn.waitFor();
  await btn.click();
  await until(async () => /page=poshuk/.test(await src(page)));
  await until(async () => (await selTexts(page)).includes("Нове від Олени"));
  await until(() => pInView(page));
});
