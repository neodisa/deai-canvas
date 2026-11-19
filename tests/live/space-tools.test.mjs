/**
 * «В Figma» як інструмент простору (етап Е, 0.31.0, Task 4) — живе проведення: справжній сервер в ізольованій «машині»
 * (тимчасові `HOME`/`DEAI_HOME`), справжній Chromium. Юніти доводять модель, розмітку й проводку; тут те, що живе лише в браузері:
 * картка «В Figma» у «Налаштування → Модулі» вимикає кнопку в смузі задачі й пункт ⌘K (без перезавантаження сторінки) і вмикає їх
 * назад; запис лишається в `space.json` простору, а питання «Вимкнути?» — у картці, з наслідком і без запиту до «Так».
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, askNo, askYes, goTasks, stop, waitBarReady } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 28900;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(t) {
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, {
    portBase: PORT_BASE,
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }],
  });
  t.after(() => stop(server.child));
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  const posts = [];
  context.on("request", (r) => { if (r.method() === "POST") posts.push(new URL(r.url()).pathname); });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  return { ...server, page, errors, posts };
}

const CARD = '.mc[data-id="tool:figma"]';
async function openModules(page) {
  await goTasks(page);
  await page.click('#bar [data-dd="space"]');
  await page.waitForFunction(() => document.querySelectorAll('.dd--spaces .dd-item[data-act="space"]').length === 1, null, { timeout: 15000 });
  await page.click('#bar [data-act="conn"]');
  await page.waitForSelector(CARD, { timeout: 15000 });
}
async function openTask(page) {
  await page.click('#tabs [data-act="home"]');
  await page.click('#tasks-home .th-card[data-id="t1"]');
  await page.waitForFunction(() => !document.body.classList.contains("home-open"), null, { timeout: 15000 });
  await page.waitForSelector("#bar .crumb--title", { timeout: 15000 });
}
async function paletteHasFigma(page) {
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible" });
  await page.fill("#palq", "Figma");
  await page.waitForTimeout(150);
  const n = await page.locator(".pal-it").filter({ hasText: "В Figma" }).count();
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".pal"), null, { timeout: 5000 });
  return n > 0;
}
const spaceJson = (server) => JSON.parse(readFileSync(path.join(server.spaces[0].path, "space.json"), "utf8"));

test("вимкнути на картці → у задачі нема кнопки «В Figma» й пункту ⌘K; увімкнути → є знову; сторінка не перезавантажується", async (t) => {
  const server = await boot(t);
  const { page, errors, posts } = server;
  await page.evaluate(() => { window.__noReload = true; });
  await openModules(page);

  const card = page.locator(CARD);
  assert.equal((await card.locator(".mc-name b").textContent()).trim(), "В Figma");
  assert.equal((await card.locator(".mc-name span").textContent()).trim(), "Інструменти");
  assert.equal((await card.locator(".bdg").textContent()).trim(), "Увімкнено");
  assert.equal(await card.locator(".mc-open").count(), 0, "шухляди нема: назва — звичайний текст");
  assert.equal(await card.locator(".mc-foot button").count(), 0, "увімкнений: дії на картці нема, вимкнути — у «⋯»");

  /* контроль: поки увімкнено, кнопка й пункт ⌘K є */
  await openTask(page);
  assert.equal(await page.locator('#bar [data-act="figma"]').count(), 1, "контроль: кнопка «В Figma» в смузі є");
  assert.equal(await paletteHasFigma(page), true, "контроль: пункт ⌘K є");

  /* «⋯ → Вимкнути» → питання в картці з наслідком; «Скасувати» нічого не пише */
  await openModules(page);
  await page.click(`${CARD} .mc-more`);
  await page.waitForSelector("#th-menu");
  await page.click('#th-menu [data-cn="toolask"]');
  await page.waitForSelector(`.mc--ask[data-id="tool:figma"]`);
  assert.match(await page.locator('.mc--ask[data-id="tool:figma"]').textContent(), /Кнопки «В Figma» в смузі нема\./);
  assert.equal(await page.evaluate(() => document.activeElement?.className.includes("cfm-no")), true, "фокус — на «Скасувати»");
  await askNo(page, "tool:figma");
  await page.waitForSelector(CARD);
  assert.equal(posts.includes("/api/space-tool"), false, "«Скасувати» запиту не шле");
  assert.equal(spaceJson(server).tools, undefined);

  await page.click(`${CARD} .mc-more`);
  await page.click('#th-menu [data-cn="toolask"]');
  await askYes(page, "tool:figma");
  await page.waitForFunction(() => document.querySelector('.mc[data-id="tool:figma"] .bdg')?.textContent.trim() === "Вимкнено", null, { timeout: 15000 });
  assert.deepEqual(spaceJson(server).tools, { figma: false }, "стан у space.json простору");
  assert.equal((await card.locator(".mc-foot button").textContent()).trim(), "Увімкнути");
  assert.equal(await card.locator(".mc-more").count(), 0, "вимкнений: меню «⋯» порожнє");

  await openTask(page);
  assert.equal(await page.locator('#bar [data-act="figma"]').count(), 0, "кнопки «В Figma» у смузі нема");
  assert.equal(await paletteHasFigma(page), false, "пункту ⌘K нема");

  /* вмикаємо назад */
  await openModules(page);
  await page.click(`${CARD} [data-cn="toolon"]`);
  await page.waitForFunction(() => document.querySelector('.mc[data-id="tool:figma"] .bdg')?.textContent.trim() === "Увімкнено", null, { timeout: 15000 });
  assert.equal(spaceJson(server).tools, undefined, "увімкнено = ключа нема, файл мінімальний");
  await openTask(page);
  assert.equal(await page.locator('#bar [data-act="figma"]').count(), 1, "кнопка повернулась");
  assert.equal(await paletteHasFigma(page), true, "пункт ⌘K повернувся");

  assert.equal(await page.evaluate(() => window.__noReload === true), true, "сторінка не перезавантажувалась");
  assert.deepEqual(errors, []);
});
