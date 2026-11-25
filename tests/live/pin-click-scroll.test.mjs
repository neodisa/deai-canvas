/**
 * Клік по піну не губиться, коли макет скролиться (0.39.1) — живе проведення.
 *
 * `_placePins` раніше на кожну подію scroll/resize робив `innerHTML = ''` і створював усі піни наново: перебудова між mousedown і
 * mouseup віддавала mouseup новому елементу, клік зникав. Макет із анімацією скролу (подія кожні ~30 мс) і клік зі швидкістю людини
 * відтворювали це стабільно. Тепер піни ключовані за id: елемент живий, змінюється лише позиція.
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px">
<main><h1 id="t">Заголовок</h1><p id="p">Абзац для коментаря</p></main></body></html>`;
const until = async (fn, ms = 15000) => {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await fn()) return; await new Promise((r) => setTimeout(r, 100)); }
  throw new Error(`умова не виконалась за ${ms} мс`);
};
const pause = (ms) => new Promise((r) => setTimeout(r, ms));
const fp = { tag: "p", stableId: null, text: "Абзац для коментаря", textHash: "x", structHash: "x", styleHash: "x", path: ["p[0]"] };

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

test("клік по піну влучає, хоча макет шле scroll кожні 30 мс; після кліку картка вибрана", async (t) => {
  const { dir } = taskFixture({ html: PAGE, pages: ["kartka"] });
  writeFileSync(path.join(dir, ".dc-local-comments.json"), JSON.stringify([
    { id: "k1", author: "Клод", status: "open", text: "Піну не можна губити клік", fp, htmlSnapshot: null, bornV: 1, ts: "13.11.2026 10:00",
      meta: { iteration: "1", version: "1/kartka", seq: 1, viewport: { w: 1440, h: 900 } } }]));
  const { child, url } = await startServer(dir, { portBase: 49500 });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#hud [data-act="comments"]');
  const frame = await (await page.$("#frame")).contentFrame();
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  await page.click('#hud [data-act="comments"]');
  await page.waitForSelector("#cmt-panel .cmt-card");
  await until(() => frame.evaluate(() => !!document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".pin")));
  /* Знімаємо вибір, щоб кліку було що змінювати: натискання на сам пін не виділяє картку, поки він не влучив. */
  await page.click('#cmt-panel .cmt-search, #cmt-panel input', { timeout: 1000 }).catch(() => {});
  await frame.evaluate(() => { setInterval(() => window.dispatchEvent(new Event("scroll")), 30); });
  const box = async () => frame.evaluate(() => {
    const p = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".pin"); const r = p.getBoundingClientRect();
    const f = parent.document.getElementById("frame").getBoundingClientRect();
    return { x: f.x + r.x + r.width / 2, y: f.y + r.y + r.height / 2 };
  });
  for (let i = 0; i < 5; i++) {
    await page.evaluate(() => { document.querySelectorAll("#cmt-panel .cmt-card--sel").forEach((e) => e.classList.remove("cmt-card--sel")); });
    const b = await box();
    await page.mouse.move(b.x, b.y, { steps: 4 });
    await pause(120);
    await page.mouse.down(); await pause(150); await page.mouse.up();
    await until(async () => (await page.$$("#cmt-panel .cmt-card--sel")).length > 0, 3000)
      .catch(() => assert.fail(`спроба ${i + 1}: клік по піну загубився під скролом`));
  }
});
