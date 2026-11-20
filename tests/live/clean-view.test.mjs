/**
 * Чистий перегляд макета (fb-01102026-7f7b6d) — в обох оболонках.
 *
 *   A канвас: ⇧⌘\ ховає смугу, панель і хост коментатора в рамці, сцена — на весь
 *     екран, зʼявляється кнопка «Показати інтерфейс»;
 *   B клік по макету (фокус у рамці) → ⇧⌘\ ВСЕРЕДИНІ рамки повертає оболонку —
 *     головна пастка записки: слухач батька цей акорд уже не бачить;
 *   C кнопка повернення працює; ⌘\ лишився панеллю шарів і чистий режим не вмикає;
 *   D зовнішнє превʼю (зібраний publish/ на статиці): той самий акорд і кнопка.
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 16200;
const VIEW = { width: 1400, height: 900 };
const CHORD = "ControlOrMeta+Shift+Backslash";
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Макет ${id}</title></head>`
  + `<body style="margin:0"><h1 id="t">${id}</h1><p>текст макета</p></body></html>`;

const shown = (page, sel) => page.evaluate((s) => {
  const e = document.querySelector(s);
  return !!e && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
}, sel);

async function canvas(t, off) {
  const { dir } = taskFixture({ html: PAGE, pages: ["holovna"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("frame").contentDocument
    ?.querySelector("[data-comment-layer]"), null, { timeout: 15000 });
  return page;
}

const framePinsHidden = (page) => page.evaluate(() => {
  const h = document.getElementById("frame").contentDocument.querySelector("[data-comment-layer]");
  return getComputedStyle(h).display === "none";
});

test("A+B: акорд ховає оболонку й піни; повернення акордом ізсередини рамки", async (t) => {
  const page = await canvas(t, 0);
  assert.equal(await shown(page, "#bar .bar"), true);
  await page.keyboard.press(CHORD);
  assert.equal(await shown(page, "#bar .bar"), false, "смуга лишилась");
  assert.equal(await shown(page, "#pages-panel"), false, "панель лишилась");
  assert.equal(await shown(page, "#cv-unclean"), true, "немає кнопки повернення");
  assert.equal(await framePinsHidden(page), true, "піни коментатора лишились");
  const box = await page.evaluate(() => document.getElementById("stage").getBoundingClientRect().toJSON());
  assert.deepEqual([box.top, box.left, box.width], [0, 0, 1400], "сцена не на весь екран");

  await page.frameLocator("#frame").locator("#t").click();
  await page.keyboard.press(CHORD);
  await page.waitForFunction(() => !document.documentElement.classList.contains("cv-clean"), null, { timeout: 3000 });
  assert.equal(await shown(page, "#bar .bar"), true, "акорд у рамці не повернув оболонку");
  assert.equal(await framePinsHidden(page), false, "піни не повернулись");
  assert.equal(await page.locator("#cv-unclean").count(), 0);
});

test("A2: перезавантаження рамки в чистому режимі не повертає піни (ревʼю 1.51)", async (t) => {
  /* Хост коментатора створюється ПІСЛЯ події load рамки, тож сховати його на load
     не можна — правило мусить діяти й на хост, що зʼявиться пізніше. */
  const page = await canvas(t, 300);
  await page.keyboard.press(CHORD);
  await page.evaluate(() => document.getElementById("frame").contentWindow.location.reload());
  await page.waitForFunction(() => document.getElementById("frame").contentDocument
    ?.querySelector("[data-comment-layer]"), null, { timeout: 15000 });
  await page.waitForTimeout(800);
  const vis = await page.evaluate(() => {
    const h = document.getElementById("frame").contentDocument.querySelector("[data-comment-layer]");
    return getComputedStyle(h).display;
  });
  assert.equal(vis, "none", "піни повернулись після перезавантаження рамки");
  await page.click("#cv-unclean");
  await page.waitForFunction(() => getComputedStyle(document.getElementById("frame").contentDocument
    .querySelector("[data-comment-layer]")).display !== "none", null, { timeout: 3000 });
});

test("C: кнопка повертає; ⌘\\ лишився панеллю шарів", async (t) => {
  const page = await canvas(t, 100);
  await page.keyboard.press(CHORD);
  await page.click("#cv-unclean");
  assert.equal(await shown(page, "#bar .bar"), true, "кнопка не повернула інтерфейс");

  const collapsed = () => page.evaluate(() => document.body.classList.contains("panel-collapsed"));
  const before = await collapsed();
  await page.keyboard.press("ControlOrMeta+Backslash");
  await page.waitForFunction((b) => document.body.classList.contains("panel-collapsed") !== b, before, { timeout: 3000 });
  assert.equal(await page.evaluate(() => document.documentElement.classList.contains("cv-clean")), false,
    "⌘\\ увімкнув чистий режим");
});

async function staticServer(root, port) {
  const child = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "-d", root],
    { stdio: "ignore" });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 60; i += 1) {
    try { if ((await fetch(`${base}/manifest.json`)).ok) return { child, base }; } catch {}
    await new Promise((r) => setTimeout(r, 250));
  }
  child.kill();
  throw new Error("статичний сервер превʼю не піднявся");
}

test("D: зовнішнє превʼю — акорд і кнопка", async (t) => {
  const { dir } = taskFixture({ html: PAGE, pages: ["holovna"] });
  const tool = await startServer(dir, { portBase: PORT_BASE + 200, liga: true });   // 4d-4b: збірка превʼю — через `vercel-publish` ЛІГИ
  t.after(() => tool.child.kill());
  const built = await (await fetch(`${tool.url}/api/publish`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ build_only: true }) })).json();
  assert.ok(built.ok, JSON.stringify(built));
  const statics = await staticServer(built.dir, PORT_BASE + 290);
  t.after(() => statics.child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(statics.base);
  await page.fill("#agpass", "1100");
  await page.click("#authform button");
  await page.locator("#bar .bar").waitFor();

  await page.keyboard.press(CHORD);
  assert.equal(await shown(page, "#bar .bar"), false, "смуга превʼю лишилась");
  assert.equal(await shown(page, "#pages-panel"), false, "панель превʼю лишилась");
  assert.equal(await shown(page, "#cv-unclean"), true);
  await page.click("#cv-unclean");
  assert.equal(await shown(page, "#bar .bar"), true, "кнопка не повернула оболонку превʼю");

  // 0.32.1: інструменти превʼю — у смузі згори; їхня кнопка ховає все (і саму смугу), акорд повертає.
  assert.equal(await shown(page, "#bar .ext-tools"), true, "інструментів превʼю нема");
  await page.click('#bar [data-act="clean"]');
  assert.equal(await shown(page, "#bar .ext-tools"), false, "інструменти лишились у чистому перегляді");
  assert.equal(await shown(page, "#bar .bar"), false);
  await page.keyboard.press(CHORD);
  assert.equal(await shown(page, "#bar .ext-tools"), true, "акорд не повернув інструменти");
});
