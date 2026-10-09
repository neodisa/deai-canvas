/**
 * Статус Клода на канвасі (ідея 02.09.2026, fb-01102026-309e3b п.3).
 *
 *   A справжній удар (POST /api/claude-status) поточної задачі → у зоні 1 фішка
 *     «Claude працює», без перезавантаження сторінки;
 *   B сервер сказав «згасло» (state: null) → фішка ЗНИКАЄ, а не висить старою —
 *     несуча вимога власника: не брехати «працює», коли нічого не відбувається;
 *   C файли сторінки змінились щойно → у рядку панелі точка «Змінено щойно».
 */
import assert from "node:assert/strict";
import test from "node:test";
import { utimesSync, writeFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 15800;
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

async function boot(t, off) {
  const { dir, it1 } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  return { page, url, it1 };
}

const chip = (page) => page.evaluate(() => document.querySelector(".claude-chip")?.textContent.trim() ?? null);

test("A+B: удар → фішка «Claude працює»; сервер сказав «згасло» → фішки немає", async (t) => {
  const { page, url } = await boot(t, 0);
  let stub = null;
  await page.route("**/api/claude-status", (route) => (stub
    ? route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(stub) })
    : route.continue()));
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  assert.equal(await chip(page), null, "фішка до першого удару");

  const r = await fetch(`${url}/api/claude-status`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: "fixture", phase: "design", status: "in_progress", note: "Іт.1", session: "live" }) });
  assert.ok(r.ok);
  await page.waitForFunction(() => /Claude працює/.test(document.querySelector(".claude-chip")?.textContent || ""),
    null, { timeout: 12000 });

  stub = { state: null };
  await page.waitForFunction(() => !document.querySelector(".claude-chip"), null, { timeout: 12000 });
});

test("C: сторінка, змінена щойно, має точку в панелі", async (t) => {
  const { page, url, it1 } = await boot(t, 100);
  for (const id of ["holovna", "poshuk"]) {
    const f = path.join(it1, id, "index.html");
    const old = Date.now() / 1000 - 3600;
    utimesSync(f, old, old);
  }
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  /* Той самий DOM-вузол рядка до і після точки: точка ставиться НА МІСЦІ. Повна
     перемальовка панелі на кожну зміну рвала жести (panel-click під навантаженням). */
  await page.evaluate(() => { window.__row = document.querySelector('.panel [data-page="poshuk"]'); });
  writeFileSync(path.join(it1, "poshuk", "index.html"), PAGE("poshuk змінено"));
  await page.waitForFunction(() => document.querySelector('.panel [data-page="poshuk"] .row-recent-dot'),
    null, { timeout: 12000 });
  assert.equal(await page.evaluate(() => window.__row.isConnected), true, "панель перемальовано цілком");
  assert.equal(await page.locator('.panel [data-page="holovna"] .row-recent-dot').count(), 0,
    "точка на сторінці, яку не міняли");
});
