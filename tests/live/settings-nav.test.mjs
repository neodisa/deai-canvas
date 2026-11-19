/**
 * «Налаштування», каркас (етап Е, 0.31.0, Task 1) — живе проведення: справжній сервер в ізольованій «машині», справжній Chromium.
 * Юніти (`tests/settings-model.test.mjs`, `tests/connections-view.test.mjs`) доводять розмітку й модель; тут — те, що живе лише в
 * браузері: шестерня веде в останній розділ, а ⌘K — завжди в «Модулі»; вибір переживає вихід і перезавантаження; вузьке вікно
 * перекладає навігацію в рядок.
 *
 * Мапа «сценарій → запобіжник» (мутаційно):
 *   1 (шестерня → mods)        — `readSec`/типове `mods` у `connSec`.
 *   2 (клік по розділу)        — `case 'csec'` у `wireHome` (`app.js`): без нього клік нічого не робить.
 *   3 (вихід і назад)          — `setConnSec` пише в localStorage; шестерня НЕ скидає в `mods` (лише `conn`).
 *   4 (перезавантаження)       — читання `localStorage[SEC_KEY]` на старті (`connSec`).
 *   5 (⌘K → mods)              — `setConnSec('mods')` у `BAR_ACTIONS.conn`.
 *   6 (вузько → рядок)         — медіазапит `max-width:759px` у `styles.css`.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, stop, waitBarReady, goTasks } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 28600;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(t) {
  const X = taskFixture({ html: MOCKUP });
  const spaces = [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }];
  const server = await startServer(null, { portBase: PORT_BASE, spaces });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  return { ...server, page, errors };
}

const gear = async (page) => {
  await page.click('[data-act="settings"]');
  await page.waitForSelector(".set-nav", { timeout: 15000 });
};
const cur = (page) => page.locator('.set-nav .nav-i[aria-current="page"]').evaluateAll((n) => n.map((x) => x.dataset.v));
const h1 = (page) => page.locator("#cn-title").textContent();
const leave = async (page) => {
  await page.click('#tabs [data-act="home"]');
  await page.waitForFunction(() => !document.querySelector(".set-nav"), null, { timeout: 15000 });
};

test("1–6: шестерня → «Модулі»; клік по розділу; памʼять між виходами й перезавантаженням; ⌘K → «Модулі»; вузько — рядок", async (t) => {
  const { page, errors } = await boot(t);
  await gear(page);
  assert.deepEqual(await cur(page), ["mods"], "типово — «Модулі»");
  assert.equal(await h1(page), "Модулі");
  assert.match(await page.locator(".set-nav h6").first().textContent(), /Простір · Studio/);
  assert.equal(await page.locator(".set-nav .nav-i").count(), 6);

  await page.click('.set-nav [data-v="keys"]');
  await page.waitForFunction(() => document.querySelector('.set-nav .nav-i[aria-current="page"]')?.dataset.v === "keys");
  assert.deepEqual(await cur(page), ["keys"], "aria-current перейшов");
  assert.equal(await h1(page), "Гарячі клавіші");

  await leave(page);
  await gear(page);
  assert.deepEqual(await cur(page), ["keys"], "шестерня веде в останній розділ");

  await page.reload();
  await waitBarReady(page, 15000);
  await gear(page);
  assert.deepEqual(await cur(page), ["keys"], "після перезавантаження — той самий");

  await leave(page);
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "Налаштування простору");
  await page.waitForFunction(() => document.querySelectorAll(".pal-it").length >= 1, null, { timeout: 5000 });
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector('.set-nav .nav-i[aria-current="page"]')?.dataset.v === "mods", null, { timeout: 15000 });
  assert.equal(await h1(page), "Модулі", "⌘K веде в «Модулі»");

  await page.waitForSelector(".mc", { timeout: 15000 });   // перемальовка після списку модулів відбулась
  assert.equal(await page.locator(".set-nav").evaluate((n) => getComputedStyle(n).flexDirection), "column", "широко — колонка");
  await page.setViewportSize({ width: 700, height: 900 });
  assert.equal(await page.locator(".set-nav").evaluate((n) => getComputedStyle(n).flexDirection), "row", "вузько — рядок");
  assert.equal(await page.locator(".set-nav h6").first().evaluate((n) => getComputedStyle(n).display), "none", "вузько — без заголовків груп");
  assert.deepEqual(errors, []);
});

test("7: перемикач простору в фішці «Налаштування…» веде в «Модулі», навіть коли останнім був інший розділ", async (t) => {
  const { page, errors } = await boot(t);
  await gear(page);
  await page.click('.set-nav [data-v="upd"]');
  await page.waitForFunction(() => document.querySelector('.set-nav .nav-i[aria-current="page"]')?.dataset.v === "upd");
  await leave(page);
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForSelector('.dd--spaces [data-act="conn"]', { timeout: 15000 });
  await page.click('.dd--spaces [data-act="conn"]');
  await page.waitForSelector(".set-nav", { timeout: 15000 });
  assert.deepEqual(await cur(page), ["mods"]);
  assert.deepEqual(errors, []);
});

guardRealDeai();
