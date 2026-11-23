/**
 * Золотий еталон тіньового DOM коментатора БЕЗ нових опцій (0.35): без `host` розмітка й `STYLE` лишаються байт-у-байт.
 * Стани: (1) після init; (2) власна панель зі списком; (3) режим елемента — відкрита форма; (4) multi з двома елементами.
 * `DC_GOLDEN_WRITE=1` — записати еталони (робити лише з навмисно зміненим виглядом); без нього — лише порівняння.
 * Сервер не потрібен: бандл `app/vendor/comment-layer.min.js`, сторінка віддається через `page.route`.
 */
import assert from "node:assert/strict";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const FIX = path.join(ROOT, "tests", "fixtures", "commenter-golden");
const WRITE = process.env.DC_GOLDEN_WRITE === "1";
const PAGE = '<!doctype html><html><head><meta charset="utf-8"><title>t</title></head><body style="margin:40px"><main>'
  + '<h1 id="t">Заголовок</h1><p id="p">Абзац для коментаря</p><p id="q">Другий абзац</p></main></body></html>';
const SEED = [
  { id: "g-open", author: "Анна", text: "Відкритий коментар", status: "open", ts: "13.11.2026 10:00",
    meta: { seq: 1, iteration: "1", version: "1", route: "/app", url: "http://dc.test/app" } },
  { id: "g-done", author: "Борис", text: "Закритий коментар", status: "resolved", ts: "13.11.2026 11:00",
    meta: { seq: 2, iteration: "1", version: "1", route: "/app", url: "http://dc.test/app" } },
  { id: "g-else", author: "Анна", text: "Коментар з іншої сторінки", status: "open", ts: "13.11.2026 12:00",
    meta: { seq: 3, iteration: "1", version: "1", route: "/other", url: "http://dc.test/other" } },
];

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot() {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.route("http://dc.test/**", (r) => r.fulfill({ contentType: "text/html", body: PAGE }));
  await page.goto("http://dc.test/app");
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate((seed) => {
    window.html2canvas = () => { const c = document.createElement("canvas"); c.width = 20; c.height = 10; return Promise.resolve(c); };
    const mem = seed.map((x) => JSON.parse(JSON.stringify(x)));
    window.__mem = mem;
    const store = { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } };
    window.CommentLayer.init({ projectId: "t", storage: store, version: "1", user: { name: "Тест" } });
  }, SEED);
  return page;
}
const shadow = (page) => page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.innerHTML
  .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g, "ID"));
async function check(page, state) {
  const got = await shadow(page);
  const file = path.join(FIX, `${state}.html`);
  if (WRITE) { mkdirSync(FIX, { recursive: true }); writeFileSync(file, got); return; }
  assert.ok(existsSync(file), `немає еталона ${state}.html (DC_GOLDEN_WRITE=1)`);
  assert.equal(got, readFileSync(file, "utf8"), `тіньовий DOM «${state}» змінився`);
}

test("золотий еталон: після init", async () => {
  const page = await boot();
  await check(page, "1-init");
  await page.close();
});

test("золотий еталон: власна панель зі списком", async () => {
  const page = await boot();
  await page.evaluate(() => window.CommentLayer._openPanel());
  await check(page, "2-panel");
  await page.close();
});

test("золотий еталон: режим елемента — форма відкрита", async () => {
  const page = await boot();
  await page.evaluate(() => window.CommentLayer.setCommentMode(true));
  await page.click("#p");
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await check(page, "3-element-compose");
  await page.close();
});

test("золотий еталон: multi з двома елементами", async () => {
  const page = await boot();
  await page.evaluate(() => window.CommentLayer.setMode("multi"));
  await page.click("#p");
  await page.click("#q");
  assert.equal(await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".mccount").textContent), "2");
  await check(page, "4-multi");
  await page.close();
});
