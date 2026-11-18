/**
 * Посилання всередині макета (0.30.1): клік по `<a href="../poshuk/index.html#sec">` веде рамку на сирий файл сторінки
 * без коментатора. Оболонка має провести це як клік по рядку панелі: `/commented?page=poshuk` із коментатором,
 * хвіст `#sec` збережено, рядок панелі — поточний.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 27500;
const HTML = (id) => id === "holovna"
  ? `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px"><main><h1>Головна</h1>
<a id="go" href="../poshuk/index.html#sec">go</a></main></body></html>`
  : `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px"><main><h1>Пошук</h1>
<div style="height:900px"></div><h2 id="sec">Секція</h2><p>текст</p></main></body></html>`;

test("посилання в макеті на іншу сторінку: коментатор лишається, рядок панелі й хеш слідом", async (t) => {
  const { dir } = taskFixture({ html: HTML });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${url}/app/`);
  await page.waitForSelector("#frame");
  const frameEl = await page.$("#frame");
  const frame = await frameEl.contentFrame();
  await frame.waitForSelector("#go", { timeout: 20000 });
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  assert.match(await frame.evaluate(() => location.search), /page=holovna/);

  await frame.click("#go");
  await page.waitForFunction(() => {
    const w = document.querySelector("#frame").contentWindow;
    try {
      return w.location.pathname === "/commented" && /page=poshuk/.test(w.location.search)
        && w.location.hash === "#sec" && !!w.CommentLayer && !!w.CommentLayer._inited;
    } catch { return false; }
  }, null, { timeout: 20000 });
  const sel = await page.$eval('#panel [data-act="page"][aria-selected="true"], [data-act="page"][aria-selected="true"]', (e) => e.dataset.val);
  assert.equal(sel, "poshuk", "поточний рядок панелі — сторінка, на яку повело посилання");
  const hash = await page.evaluate(() => document.querySelector("#frame").contentWindow.location.hash);
  assert.equal(hash, "#sec");
  // Хвіст одноразовий: наступний вибір сторінки в панелі йде без нього.
  await page.click('[data-act="page"][data-val="holovna"]');
  await page.waitForFunction(() => /page=holovna/.test(document.querySelector("#frame").contentWindow.location.search));
  assert.equal(await page.evaluate(() => document.querySelector("#frame").contentWindow.location.hash), "");
});

test("редирект-цикл сирих сторінок не крутить оболонку нескінченно", async (t) => {
  const { dir } = taskFixture({ html: (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<script>setTimeout(() => location.replace('../${id === "holovna" ? "poshuk" : "holovna"}/index.html'), 400)</script></body></html>` });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 50 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  let n = 0;
  page.on("request", (r) => { if (/\/commented\?/.test(r.url())) n++; });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('[data-act="page"][data-val="holovna"]');
  await new Promise((r) => setTimeout(r, 6000));
  const settled = n;
  assert.ok(settled <= 5, `запитів /commented: ${settled}`);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await page.waitForFunction(() => /page=poshuk/.test(document.querySelector("#frame").getAttribute("src") || ""));
  assert.deepEqual(errors, []);
});
