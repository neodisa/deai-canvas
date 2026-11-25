/**
 * Ширина лівої панелі (0.40): перетягування краю, збереження після перезавантаження, подвійний клік під найдовшу назву й назад,
 * клавіші ← →, межа на вузькому вікні, «Огляд» перевписується. Підказки — `names-tooltip.test.mjs`.
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 51000;
/* Назва мусить бути довшою за 246-пікселькову панель, але влізти в максимум 520: інакше «під найдовшу назву» недосяжне. */
const LONG = "Довга назва сторінки, що не влізе у типову панель";
const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(t, off, viewport = { width: 1440, height: 900 }) {
  const { dir } = taskFixture({ html });
  writeFileSync(path.join(dir, "iterations", "it1", "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: LONG, published: true }, { id: "poshuk", name: "Пошук", published: true }],
  }));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  await page.waitForSelector("#panel-resize");
  await page.waitForSelector('[data-page="holovna"] .row-name');
  return page;
}
const panelW = (page) => page.evaluate(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width));
const stageLeft = (page) => page.evaluate(() => Math.round(document.getElementById("stage").getBoundingClientRect().left));
const drag = async (page, dx) => {
  const b = await (await page.$("#panel-resize")).boundingBox();
  const x = b.x + b.width / 2, y = b.y + 200;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y, { steps: 5 });
  await page.mouse.up();
};
const settled = (page) => page.waitForFunction(() => !document.body.classList.contains("panel-dragging"));

test("перетягування змінює ширину, сцена слідом; ширина переживає перезавантаження; під час жесту transition вимкнено", async (t) => {
  const page = await boot(t, 0);
  assert.equal(await panelW(page), 246);
  const b = await (await page.$("#panel-resize")).boundingBox();
  await page.mouse.move(b.x + 4, b.y + 200);
  await page.mouse.down();
  await page.mouse.move(b.x + 4 + 84, b.y + 200, { steps: 4 });
  assert.equal(await page.evaluate(() => getComputedStyle(document.getElementById("pages-panel")).transitionProperty), "none", "transition вимкнено під час перетягування");
  await page.mouse.up();
  await settled(page);
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) === 330);
  assert.equal(await stageLeft(page), 330, "сцена зсунулась разом із панеллю");
  assert.equal(await page.evaluate(() => localStorage.getItem("dc-panel-w")), "330");
  await page.reload();
  await page.waitForSelector("#panel-resize");
  assert.equal(await panelW(page), 330, "ширина пережила перезавантаження");
});

test("подвійний клік: під найдовшу назву (повна влізла) й назад до 246; Enter — те саме", async (t) => {
  const page = await boot(t, 100);
  const cut = () => page.$eval('[data-page="holovna"] .row-name', (n) => n.scrollWidth - n.clientWidth);
  assert.ok((await cut()) > 0, "на 246 назву обрізано");
  await page.dblclick("#panel-resize");
  await page.waitForFunction(() => { const n = document.querySelector('[data-page="holovna"] .row-name'); return n.scrollWidth <= n.clientWidth; });
  const w = await panelW(page);
  assert.ok(w > 246 && w <= 520, `ширина під назву: ${w}`);
  await page.dblclick("#panel-resize");
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) === 246);
  await page.focus("#panel-resize");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) > 246);
});

test("клавіші ← →: крок 16; aria-значення йдуть слідом", async (t) => {
  const page = await boot(t, 200);
  await page.focus("#panel-resize");
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.getElementById("panel-resize").getAttribute("aria-valuenow") === "262");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await page.waitForFunction(() => document.getElementById("panel-resize").getAttribute("aria-valuenow") === "230");
  assert.equal(await page.getAttribute("#panel-resize", "role"), "separator");
});

test("вузьке вікно: ширина не виходить за 800 − 420 = 380; мінімум 200", async (t) => {
  const page = await boot(t, 300, { width: 800, height: 700 });
  await drag(page, 600);
  await settled(page);
  await page.waitForFunction(() => document.getElementById("pages-panel").getBoundingClientRect().width <= 380.5);
  assert.equal(await panelW(page), 380);
  await drag(page, -900);
  await settled(page);
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) === 200);
});

test("«Огляд»: після зміни ширини полотно вписується заново (камеру не рухали)", async (t) => {
  const page = await boot(t, 400);
  await page.locator('[data-act="mode"][data-val="overview"]').click();
  await page.locator(".cv-card img").first().waitFor();
  const tf = () => page.evaluate(() => document.getElementById("world").style.transform);
  await page.waitForFunction(() => document.getElementById("world").style.transform !== "");
  const before = await tf();
  await drag(page, 120);
  await settled(page);
  await page.waitForFunction((b) => document.getElementById("world").style.transform !== b, before, { timeout: 5000 });
});

test("збережена широка панель на вузькому вікні притискається до межі, а вибір у сховищі лишається", async (t) => {
  const page = await boot(t, 500, { width: 800, height: 700 });
  await page.evaluate(() => localStorage.setItem("dc-panel-w", "500"));
  await page.reload();
  await page.waitForSelector("#panel-resize");
  assert.equal(await panelW(page), 380, "800 − 420");
  assert.equal(await page.evaluate(() => localStorage.getItem("dc-panel-w")), "500", "вибір не перезаписано притисненим");
});
