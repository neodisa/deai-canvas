/**
 * Живий сторож: шорткати коментатора (C/P/H) не їдять набір у полях ОБОЛОНКИ.
 *
 * ЩО ЛАМАЛОСЬ. comment-layer вішає keydown на вікно рамки І на кожен same-origin
 * предок — отже й на вікно оболонки. А «друкуємо?» він питав лише в
 * `document.activeElement` ДОКУМЕНТА РАМКИ. Коли фокус у `#palq` (⌘K), activeElement рамки — `body`:
 * c/p/h з'їдались і вмикали режим коментування. «chip» у палітрі лишало «i».
 * (Поле `#task-q` перемикача задач прибрано в 0.25.0 — його перевірка видалена.)
 *
 * Мапа «перевірка → запобіжник» (мутація: прибрати — перевірка червоніє):
 *   A (набір у `#palq`) — елемент-походження події в `_isTyping(e)`
 *        (`keyOrigin`/`typingIn` у comment-layer). Мутація «typingIn дивиться лише
 *        на active» червонить A.
 *   B (контроль) — клік у тіло рамки й `c` ВМИКАЄ режим: виправлення не вбило
 *        шорткат. Без B «нічого не вмикається» зеленіло б і на `return` у
 *        першому рядку обробника.
 *
 * ⛔ Supabase ЛІГИ — вигаданий хост із `tasks.json` фікстури (`supabase: true`), перехоплений у браузері (`hermeticLiga`, як у
 * `comment-audience.test.mjs`): шар мусить піднятись у рамці без мережі.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { hermeticLiga } from "./_liga-supabase.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя база порту: `node --test` крутить файли ПАРАЛЕЛЬНО. */
const PORT_BASE = 12500;
const VIEW = { width: 1400, height: 900 };

const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:900px;background:repeating-linear-gradient(37deg,#e11 0 10px,`
  + `#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)">`
  + `<h1 style="margin:40px">${id}</h1></body></html>`;

async function hermetic(page, t) {
  const seen = await hermeticLiga(page);
  t.after(() => assert.deepEqual(seen.outside, [], `запити за межі машини:\n${seen.outside.join("\n")}`));
}

function waitLayer(page) {
  return page.waitForFunction(() => {
    const w = (document.getElementById("frame") || {}).contentWindow;
    const host = w && w.document.querySelector("[data-comment-layer]");
    return !!(w && w.document.readyState === "complete" && host
      && host.shadowRoot && host.shadowRoot.querySelector(".panel"));
  }, null, { timeout: 20000 });
}

/** Режим коментування: `.arming` у тіньовому корені АБО `cl-freeze` на html рамки. */
function armed(page) {
  return page.evaluate(() => {
    const w = document.getElementById("frame").contentWindow;
    const host = w.document.querySelector("[data-comment-layer]");
    return {
      arming: !!host.shadowRoot.querySelector(".arming"),
      freeze: w.document.documentElement.classList.contains("cl-freeze"),
    };
  });
}

const panelOpen = (page) => page.evaluate(() => { const p = document.getElementById("cmt-panel"); return !!p && !p.hidden; });

async function boot(t) {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await hermetic(page, t);
  await page.goto(`${url}/app/`);
  await waitLayer(page);
  return page;
}

test("A. набір «chip» у палітрі ⌘K не вмикає коментування й не губить літери", async (t) => {
  const page = await boot(t);
  await page.keyboard.press("Control+k");
  await page.locator("#palq").waitFor({ state: "visible", timeout: 5000 });
  await page.keyboard.type("chip");
  assert.equal(await page.inputValue("#palq"), "chip",
    "літери c/p/h з'їдені шорткатом коментатора");
  assert.deepEqual(await armed(page), { arming: false, freeze: false },
    "набір у палітрі увімкнув режим коментування");
  /* C тепер клавіша ОБОЛОНКИ (вмикає панель коментарів), тож охороняємо і її: панель лишилась закритою. */
  assert.equal(await panelOpen(page), false, "набір у палітрі відкрив панель коментарів оболонки");
});

test("A2. набір «chip» у полі самого макета не вмикає коментування й не відкриває панель оболонки", async (t) => {
  const page = await boot(t);
  await page.frameLocator("#frame").locator("body").evaluate((b) => {
    const ta = b.ownerDocument.createElement("textarea"); ta.id = "mockfield"; ta.style.cssText = "position:fixed;left:200px;top:200px;width:200px";
    b.appendChild(ta);
  });
  await page.frameLocator("#frame").locator("#mockfield").click();
  await page.keyboard.type("chip");
  assert.equal(await page.frameLocator("#frame").locator("#mockfield").inputValue(), "chip",
    "літери c/p/h з'їдені шорткатом (поле макета)");
  assert.deepEqual(await armed(page), { arming: false, freeze: false }, "набір у полі макета увімкнув режим коментування");
  assert.equal(await panelOpen(page), false, "набір у полі макета відкрив панель коментарів оболонки");
});

test("B. контроль: фокус у тілі рамки — `c` вмикає коментування", async (t) => {
  const page = await boot(t);
  /* Клік у тіло рамки: activeElement рамки — body, подія — з рамки. */
  await page.frameLocator("#frame").locator("h1").click();
  await page.keyboard.press("c");
  await page.waitForFunction(() => {
    const w = document.getElementById("frame").contentWindow;
    return !!w.document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".arming");
  }, null, { timeout: 3000 });
  assert.equal((await armed(page)).arming, true, "шорткат `c` мусить вмикати режим");
  assert.equal(await panelOpen(page), true, "шорткат `c` мусить відкривати панель коментарів оболонки");
});
