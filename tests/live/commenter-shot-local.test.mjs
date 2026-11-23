/**
 * Повний знімок ЛОКАЛЬНОГО піна в оболонці (0.35.1, баг 1, варіант B): пін, поставлений живою формою в рамці, лишає в задачі файл
 * `.dc-local-shots/<id>.jpg` (поза git макета), `meta.shotUrl` — абсолютна адреса `/api/local-shots/<id>.jpg`, `meta.shot` — мала
 * мініатюра inline, а `shotMiss` нема. html2canvas — справжній 1.4.1 із тестових фікстур, віддається через `page.route` замість CDN.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const H2C = readFileSync(path.join(ROOT, "tests", "fixtures", "vendor", "html2canvas-1.4.1.min.js"), "utf8");
const PORT_BASE = 47100;
const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px">
<main><h1 id="t">Заголовок</h1><p id="p" style="padding:20px;background:#dfe">Абзац для коментаря</p></main></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

test("локальний пін: файл знімка в теці задачі, shotUrl — абсолютна адреса, GET віддає JPEG, shotMiss нема", async (t) => {
  const { dir } = taskFixture({ html: PAGE, pages: ["kartka"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  t.after(() => ctx.close());
  const page = await ctx.newPage();
  await page.route("https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js", (r) => r.fulfill({ status: 200, contentType: "text/javascript", body: H2C }));
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#hud [data-act="comments"]');
  const frame = await (await page.$("#frame")).contentFrame();
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  await page.click('#hud [data-act="comments"]');
  await frame.waitForFunction(() => window.CommentLayer.tool && window.CommentLayer.tool().armed, null, { timeout: 15000 });

  await frame.click("#p");
  await frame.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await frame.evaluate(() => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = "знімок"; ta.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await frame.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").click());

  const file = path.join(dir, ".dc-local-comments.json");
  let pin = null;
  const end = Date.now() + 30000;
  while (Date.now() < end && !pin) {
    if (existsSync(file)) { try { pin = JSON.parse(readFileSync(file, "utf8")).find((c) => c.text === "знімок") || null; } catch { /* дописується */ } }
    if (!pin) await new Promise((r) => setTimeout(r, 200));
  }
  assert.ok(pin, "пін не записано");
  assert.equal(pin.meta.shotMiss, undefined, `shotMiss: ${pin.meta.shotMiss}`);
  assert.ok(pin.meta.shot.startsWith("data:image/jpeg"), "мініатюра inline");
  assert.equal(pin.meta.shotUrl, `${url}/api/local-shots/${pin.id}.jpg`);
  const onDisk = path.join(dir, ".dc-local-shots", `${pin.id}.jpg`);
  assert.ok(existsSync(onDisk), "файл повного знімка");
  const bytes = readFileSync(onDisk);
  assert.deepEqual([...bytes.subarray(0, 3)], [0xff, 0xd8, 0xff]);
  const r = await fetch(pin.meta.shotUrl);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("content-type"), "image/jpeg");
  assert.equal(Buffer.compare(Buffer.from(await r.arrayBuffer()), bytes), 0);
  // повний знімок більший за мініатюру (мініатюра ≤ 720 px, повний — у густині ×2)
  const dims = await page.evaluate(async ({ thumb, full }) => {
    const size = async (u) => { const i = new Image(); i.src = u; await i.decode(); return [i.naturalWidth, i.naturalHeight]; };
    return { thumb: await size(thumb), full: await size(full) };
  }, { thumb: pin.meta.shot, full: pin.meta.shotUrl });
  assert.ok(dims.thumb[0] <= 720 && dims.thumb[1] <= 720, `мініатюра ${dims.thumb}`);
  assert.ok(dims.full[0] > dims.thumb[0], `повний ${dims.full} не більший за мініатюру ${dims.thumb}`);
});
