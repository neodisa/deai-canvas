/**
 * Підказки на обрізаних назвах (0.40): довга назва в панелі — підказка з повним текстом через ~0,5 с; коротка — нічого;
 * `title` на рядках немає (дві підказки одночасно); pointerdown і з клавіатури теж.
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 50000;
const VIEW = { width: 1440, height: 900 };
const LONG = "Дуже довга назва сторінки, яка точно не влізе в панель шириною двісті сорок шість пікселів";
const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

export function longNames(dir) {
  writeFileSync(path.join(dir, "iterations", "it1", "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: LONG, published: true }, { id: "poshuk", name: "Пошук", published: true }],
  }));
}

async function boot(t, off) {
  const { dir } = taskFixture({ html });
  longNames(dir);
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  await page.waitForSelector('[data-page="holovna"] .row-name');
  return page;
}
const tipOn = (page) => page.evaluate(() => document.getElementById("dc-tip")?.classList.contains("on") ?? false);
const tipTxt = (page) => page.evaluate(() => document.getElementById("dc-tip")?.textContent ?? "");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("довга назва: підказка через затримку з повним текстом; коротка — без підказки; title на рядку нема", async (t) => {
  const page = await boot(t, 0);
  assert.equal(await page.getAttribute('[data-page="holovna"]', "title"), null, "на рядку нема title");
  await page.hover('[data-page="holovna"] .row-name');
  await sleep(200);
  assert.equal(await tipOn(page), false, "раніше за 500 мс підказки нема");
  await page.waitForFunction(() => document.getElementById("dc-tip")?.classList.contains("on"), null, { timeout: 3000 });
  assert.equal(await tipTxt(page), LONG);
  await page.hover('[data-page="poshuk"] .row-name');
  await sleep(900);
  assert.equal(await tipOn(page), false, "коротка назва не обрізана — підказки нема");
});

test("pointerdown ховає підказку; з клавіатури (focus-visible) вона теж зʼявляється", async (t) => {
  const page = await boot(t, 100);
  await page.hover('[data-page="holovna"] .row-name');
  await page.waitForFunction(() => document.getElementById("dc-tip")?.classList.contains("on"), null, { timeout: 3000 });
  await page.mouse.down();
  assert.equal(await tipOn(page), false, "pointerdown ховає");
  await page.mouse.up();
  await page.mouse.move(700, 600);
  await page.keyboard.press("Shift");   // остання взаємодія — клавіатура: focus() дає :focus-visible
  await page.evaluate(() => document.activeElement?.blur());   // mouse.down уже сфокусував рядок — без blur focus() не дасть focusin
  await page.locator('[data-page="holovna"]').focus();
  await page.waitForFunction(() => document.getElementById("dc-tip")?.classList.contains("on"), null, { timeout: 3000 });
  assert.equal(await tipTxt(page), LONG);
});
