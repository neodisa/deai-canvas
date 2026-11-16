/**
 * Етап Г (0.29.0): панель властивостей і оверлей у бою. Мапа «перевірка → запобіжник → що буде без нього» — у кінці
 * файла (розділ «Мутації»), знята мутаційно.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 27200;
const VIEW = { width: 1400, height: 900 };

const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;font:16px/24px sans-serif;background:#fff}
#wrap{display:flex;flex-direction:column;gap:8px;padding:16px}
#card{display:flex;gap:12px;padding:10px 14px;border:1px solid #dde3ee;border-radius:7px;background:#f6f8fc}
#a{padding:6px 10px;background:#1f4fe0;color:#fff}
#b{padding:6px 10px;background:#e0e0e0}
</style></head><body><div id="wrap"><div id="card"><a id="a">One</a><a id="b">Two</a></div><p id="para">Hello</p></div></body></html>`;

async function openInspector(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame").contentWindow.CanvasInspector.on === true,
    null, { timeout: 3000 });
  return page;
}

/** Клік у центр елемента макета; чекаємо, поки оверлей його запінить. */
async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction((id) => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!(api.pinned && api.pinned.id === id);
  }, sel.slice(1), { timeout: 3000 });
}

const pinnedId = (page) => page.evaluate(() => {
  const p = document.getElementById("frame").contentWindow.CanvasInspector.pinned;
  return p ? p.id || p.localName : null;
});

/** Пакет тюнера на диску, або null. */
function pkg(dir) {
  const f = path.join(dir, ".dc-tuner.json");
  if (!existsSync(f)) return null;
  try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; }
}
async function waitPkg(page, dir, pred, what) {
  for (let i = 0; i < 80; i += 1) {
    const p = pkg(dir);
    if (p && pred(p)) return p;
    await page.waitForTimeout(50);
  }
  assert.fail(`пакет так і не дочекався: ${what}: ${JSON.stringify(pkg(dir))}`);
}
const editOf = (p, prop) => (p.elements || []).flatMap((e) => e.edits).find((e) => e.prop === prop);

async function boot(t) {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  return { dir, page: await openInspector(browser, url), url };
}

test("T2-proof. клік → панель властивостей із назвою й розділами; поле gap пише макет і пакет", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  assert.equal(await page.locator("#insp-panel .insp-name").textContent(), "div");
  for (const s of ["size", "edges", "layout", "spacing", "fill", "stroke"]) {
    assert.equal(await page.locator(`#insp-panel [data-sec="${s}"]`).count(), 1, `немає розділу ${s}`);
  }
  const gap = '#insp-panel .insp-f[data-prop="gap"] .insp-fi';
  await page.focus(gap);
  await page.keyboard.press("ArrowUp");
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi')?.value === "13");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((el) => getComputedStyle(el).gap), "13px");
  const p = await waitPkg(page, dir, (x) => editOf(x, "gap"), "правка gap");
  assert.equal(editOf(p, "gap").to, "13px");
});
