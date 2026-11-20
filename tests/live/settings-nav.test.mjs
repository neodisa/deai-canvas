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
 *   8 (колір простору)         — `paintSpaceColor` (`data-space-color` на `<html>`) і правила `:root[data-space-color]`; запис — `spaceSave`;
 *                                 стрілки радіогрупи — `keydown` у `wireHome`; назва — Enter/`focusout` (`commitSpaceName`).
 *   9 (Загальне)               — `case 'lang'` + `switchLang` у `wireHome`; рядок «Окреме вікно» — `generalBodyHTML` за `pwa.canInstall()`;
 *                                 перемальовка на `beforeinstallprompt` — слухач біля `initPwa`.
 *  10 (Оновлення)              — `case 'up'`: «Перевірити зараз» → `checkUpdateNow` (`POST /api/update-check`, фокус назад), «Оновити до» →
 *                                 `openUpdateDialog`; `repaintSettingsSec('upd')` на зміну стану.
 *  11 (Гарячі клавіші)         — `keysBodyHTML` читає `KEYS`, як і `keysHTML()` (аркуш `?`).
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, guardRealDeai, stop, waitBarReady, goTasks } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 28600;
const MOCKUP = () => "<!doctype html><html><body><h1>Макет</h1></body></html>";

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(t, { color = "space-2" } = {}) {
  const X = taskFixture({ html: MOCKUP });
  const spaces = [{ name: "Studio", id: "studio", color, tasks: { t1: { dir: X.dir, title: "Задача" } } }];
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

/** Відтінок OKLCH з обчисленого кольору (`oklch(...)` чи `rgb(...)`): сторінка віддає те, що вважає потрібним. */
async function hueOf(page, selector) {
  const css = await page.locator(selector).first().evaluate((n) => getComputedStyle(n).backgroundColor);
  const ok = css.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
  if (ok) return Number(ok[3]);
  const [r, g, b] = css.match(/[\d.]+/g).slice(0, 3).map((v) => { const c = Number(v) / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
  return ((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360;
}
const sw = (page, name) => page.locator(".sw", { hasText: name });

test("8: колір простору — «Фіолетовий» фарбує вікно (hue ≈ 300), «Зелений» вертає початковий; стрілки, фішка, назва", async (t) => {
  const { page, errors } = await boot(t, { color: "space-1" });
  await gear(page);
  await page.click('.set-nav [data-v="space"]');
  await page.waitForSelector(".sw-grid", { timeout: 15000 });
  assert.equal(await h1(page), "Простір");
  assert.equal(await page.locator("#set-sp-name").inputValue(), "Studio");
  assert.equal(await page.locator(".sp-path span").count(), 1, "тека показана");
  const initialBg = await page.locator("#bar").evaluate((n) => getComputedStyle(n).backgroundColor);
  const initialMeta = await page.locator('meta[name="theme-color"]').getAttribute("content");
  assert.equal(await page.evaluate(() => document.documentElement.dataset.spaceColor), "space-1");
  assert.equal(await page.locator('.sw[aria-checked="true"]').count(), 1);
  assert.ok(Math.abs((await hueOf(page, "#bar")) - 162) < 6, "початково — зелений відтінок");

  await sw(page, "Фіолетовий").click();
  await page.waitForFunction(() => document.documentElement.dataset.spaceColor === "space-5", null, { timeout: 15000 });
  const hue = await hueOf(page, "#bar");
  assert.ok(Math.abs(hue - 300) < 8, `смуга фіолетова: hue ${hue}`);
  assert.notEqual(await page.locator("#bar").evaluate((n) => getComputedStyle(n).backgroundColor), initialBg);
  assert.notEqual(await page.locator('meta[name="theme-color"]').getAttribute("content"), initialMeta, "theme-color пішов за простором");
  assert.match(await page.locator(".space-chip .space-dot, .space-chip [style]").first().getAttribute("style"), /--space-5/, "фішка простору — фіолетова");
  assert.equal(await sw(page, "Фіолетовий").getAttribute("aria-checked"), "true");

  /* Перезавантаження: колір збережено в `space.json`, а не лише в пам'яті сторінки. */
  await page.reload();
  await waitBarReady(page, 15000);
  assert.equal(await page.evaluate(() => document.documentElement.dataset.spaceColor), "space-5", "колір пережив перезавантаження");

  /* Клавіатура: радіогрупа — стрілки ходять по колу й одразу вибирають; у Tab-порядку одна плитка. */
  await gear(page);
  await page.click('.set-nav [data-v="space"]');
  await page.waitForSelector(".sw-grid");
  assert.equal(await page.locator('.sw[tabindex="0"]').count(), 1);
  await sw(page, "Фіолетовий").focus();
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.documentElement.dataset.spaceColor === "space-6", null, { timeout: 15000 });
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.val), "space-6", "фокус пішов за вибором");
  assert.ok(Math.abs((await hueOf(page, "#bar")) - 200) < 8, "бірюзовий");

  /* Назва: Enter зберігає й дзеркалиться в навігації. */
  await page.fill("#set-sp-name", "Нова назва");
  await page.press("#set-sp-name", "Enter");
  await page.waitForFunction(() => /Простір · Нова назва/.test(document.querySelector(".set-nav h6")?.textContent ?? ""), null, { timeout: 15000 });

  await sw(page, "Зелений").click();
  await page.waitForFunction(() => document.documentElement.dataset.spaceColor === "space-1", null, { timeout: 15000 });
  assert.equal(await page.locator("#bar").evaluate((n) => getComputedStyle(n).backgroundColor), initialBg, "«Зелений» повернув початковий фон");
  assert.equal(await page.locator('meta[name="theme-color"]').getAttribute("content"), initialMeta);
  assert.deepEqual(errors, []);
});

const sec = async (page, id) => {
  await page.click(`.set-nav [data-v="${id}"]`);
  await page.waitForFunction((v) => document.querySelector('.set-nav .nav-i[aria-current="page"]')?.dataset.v === v, id, { timeout: 15000 });
};

test("9: «Загальне» — English перемикає інтерфейс і назад; «Окреме вікно» зʼявляється з подією встановлення", async (t) => {
  const { page, errors } = await boot(t);
  await gear(page);
  await sec(page, "app");
  assert.equal(await h1(page), "Загальне");
  assert.equal(await page.locator('.seg [aria-checked="true"]').textContent(), "Українська");
  assert.equal(await page.locator('.seg [role="radio"][tabindex="0"]').count(), 1);
  assert.equal(await page.locator(".set-row", { hasText: "Окреме вікно" }).count(), 0, "без можливості встановити рядка нема");

  await page.click('.seg [data-v="en"]');
  await page.waitForFunction(() => document.querySelector("#cn-title")?.textContent === "General", null, { timeout: 15000 });
  assert.equal(await page.locator('.set-nav .nav-i[data-v="keys"]').textContent(), "Keyboard shortcuts");
  assert.equal(await page.locator('.seg [aria-checked="true"]').textContent(), "English");
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.v), "en", "фокус лишився на вибраному");
  await page.keyboard.press("ArrowLeft");
  await page.waitForFunction(() => document.querySelector("#cn-title")?.textContent === "Загальне", null, { timeout: 15000 });
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.v), "uk", "стрілка вибирає й несе фокус");

  await page.evaluate(() => window.dispatchEvent(new Event("beforeinstallprompt")));
  await page.locator(".set-row", { hasText: "Окреме вікно" }).waitFor({ timeout: 5000 });
  assert.equal(await page.locator('[data-th="pwa"]').textContent(), "Встановити");
  await page.click('[data-th="pwa"]');          // `prompt()` на підробній події не існує → `error`, подію витрачено → рядок зникає
  await page.waitForFunction(() => !document.querySelector('[data-th="pwa"]'), null, { timeout: 5000 });
  assert.deepEqual(errors, []);
});

test("10: «Оновлення» — назва з версією, стан, «Перевірити зараз» шле POST, «Оновити до» відкриває діалог", async (t) => {
  const { page, errors, deaiHome, url } = await boot(t);
  writeFileSync(path.join(deaiHome, "update.json"), JSON.stringify({ checked_at: Math.floor(Date.now() / 1000) - 7200, latest: "99.0.0", state: "ok", reason: "" }));
  await page.reload();
  await waitBarReady(page, 15000);
  await gear(page);
  await sec(page, "upd");
  const cur = (await (await fetch(`${url}/api/update`)).json()).current;
  await page.locator(".set-row", { hasText: `Deai Canvas ${cur}` }).waitFor({ timeout: 10000 });
  assert.match(await page.locator(".set-row-s").textContent(), /остання перевірка 2 год тому/);

  await page.click('[data-th="up"][data-v="open"]');
  await page.locator(".cv-form.up").waitFor({ timeout: 10000 });
  assert.match(await page.locator(".up-ver").textContent(), /99\.0\.0/);
  await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector(".cv-form.up"), null, { timeout: 5000 });

  const req = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/api/update-check"), { timeout: 10000 });
  await page.click('[data-th="up"][data-v="check"]');
  await req;
  await page.waitForFunction(() => /вимкнено/.test(document.querySelector(".set-row-s")?.textContent ?? ""), null, { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector('[data-th="up"][data-v="check"]').disabled, null, { timeout: 5000 });
  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.v), "check", "фокус повернувся на кнопку");
  assert.equal(await page.locator('[data-th="up"][data-v="check"]').textContent(), "Перевірити зараз");
  assert.deepEqual(errors, []);
});

test("11: «Гарячі клавіші» — ті самі рядки, що аркуш «?»", async (t) => {
  const { page, errors } = await boot(t);
  await gear(page);
  await sec(page, "keys");
  const pairs = (rows) => rows.map((r) => r.replace(/\s+/g, " ").trim());
  const fromSection = await page.locator(".set-row").evaluateAll((n) => n.map((r) => `${r.querySelector(".set-row-t").textContent}|${r.querySelector("kbd").textContent}`));
  assert.ok(fromSection.some((x) => x.endsWith("|⌘K")), "⌘K є в розділі");
  await page.keyboard.press("?");
  await page.locator(".keysheet").waitFor({ timeout: 5000 });
  const fromSheet = await page.locator(".keysheet dt").evaluateAll((n) => n.map((d) => `${d.textContent}|${d.nextElementSibling.textContent}`));
  assert.deepEqual(pairs(fromSection), pairs(fromSheet));
  assert.deepEqual(errors, []);
});

guardRealDeai();
