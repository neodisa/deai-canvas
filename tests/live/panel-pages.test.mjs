/**
 * Живий тест дій над сторінками в панелі: перейменування й порядок.
 *
 * Звідки:
 *   · fb-22092026-31674a — поле перейменування СТОРІНКИ відкривалось порожнім:
 *     не видно, що правиш, і будь-яке «Гаразд» затирало назву;
 *   · fb-09092026-d4c51b / 24e49a — порядок сторінок був хронологією роботи, і
 *     поміняти його інструментом було неможливо (ні функції, ні маршруту, ні
 *     кнопки) — переставляли руками в `pages.json`.
 *
 * Мапа «перевірка → запобіжник → мутація»:
 *   A (поле з назвою)   — другий аргумент `ask(…, cur)` у `renamePage`.
 *                         МУТАЦІЯ: прибрати `cur` — поле знову порожнє.
 *   B (Підняти)         — пункт `up` у `pageMenu` + `POST /api/page-move {delta}`.
 *                         МУТАЦІЯ: `movePage` без запиту — порядок на диску
 *                         не змінюється.
 *   C (межа меню)       — `canMove`: у першої сторінки «Підняти» немає.
 *                         МУТАЦІЯ: завжди малювати обидва пункти.
 *   D (перетягування)   — `wirePageDrag` + `planMove`. МУТАЦІЇ: у `drop` не
 *                         кликати `movePage` — порядок на диску старий; зняти
 *                         поправку зсуву в `planMove` (`index` після виймання) — сторінка стає на одну
 *                         нижче, ніж кидали.
 *
 * Чому живий: обидві вади — у проводці «клік/перетягування → меню/діалог →
 * запит → перемальовка», якої юніт не бачить. Арифметику позиції стереже юніт
 * `tests/page-order.test.mjs`, тут — лише що вона доїжджає до диска.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 11590;
const VIEW = { width: 1400, height: 900 };

const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{margin:0;height:900px;font:14px/1.4 sans-serif;
  background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)}
</style></head><body><h1>${id}</h1></body></html>`;

async function open(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForSelector('.panel [data-page="holovna"]', { timeout: 15000 });
  return page;
}

const diskOrder = (it1) => JSON.parse(readFileSync(path.join(it1, "pages.json"), "utf8"))
  .pages.map((p) => p.id);
const panelOrder = (page) => page.evaluate(() =>
  [...document.querySelectorAll(".panel [data-page]")].map((r) => r.dataset.page));

async function until(fn, want, ms = 4000) {
  const end = Date.now() + ms;
  let got;
  while (Date.now() < end) {
    got = await fn();
    if (JSON.stringify(got) === JSON.stringify(want)) return got;
    await new Promise((r) => setTimeout(r, 50));
  }
  return got;
}

test("A: перейменування сторінки відкриває поле з ЧИННОЮ назвою, виділеною", async (t) => {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await open(browser, url);

  await page.locator('.panel [data-page="poshuk"]').click({ button: "right" });
  await page.click('#cv-ctx [data-a="rename"]');
  await page.waitForSelector(".cv-ask input");
  const f = await page.evaluate(() => {
    const i = document.querySelector(".cv-ask input");
    return { value: i.value, start: i.selectionStart, end: i.selectionEnd };
  });
  assert.equal(f.value, "Пошук", "поле порожнє — не видно, що правиш, «Гаразд» затре назву");
  assert.deepEqual([f.start, f.end], [0, "Пошук".length],
    "назва не виділена — набір поверх допише, а не замінить");
});

test("B+C: «Підняти» є там, де є куди, і міняє порядок на диску", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk", "vybir"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 30 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await open(browser, url);

  const items = async (id) => {
    await page.locator(`.panel [data-page="${id}"]`).click({ button: "right" });
    const got = await page.evaluate(() =>
      [...document.querySelectorAll("#cv-ctx [data-a]")].map((b) => b.dataset.a));
    return got;
  };
  const first = await items("holovna");
  assert.ok(!first.includes("up") && first.includes("down"),
    `у першої сторінки меню обіцяє рух за край: ${first}`);
  /* Пауза — та сама гонка тесту, що описана в `shell-panel.test.mjs` («Escape
     закриває меню»): слухачі меню вішаються через `setTimeout(…, 0)`. */
  await page.waitForTimeout(50);
  await page.keyboard.press("Escape");

  const last = await items("vybir");
  assert.ok(last.includes("up") && !last.includes("down"),
    `у останньої сторінки меню не те: ${last}`);
  await page.click('#cv-ctx [data-a="up"]');
  assert.deepEqual(await until(() => diskOrder(it1), ["holovna", "vybir", "poshuk"]),
    ["holovna", "vybir", "poshuk"], "«Підняти» не дійшло до pages.json");
  assert.deepEqual(await until(() => panelOrder(page), ["holovna", "vybir", "poshuk"]),
    ["holovna", "vybir", "poshuk"], "на диску переставлено, а панель показує старий порядок");
});

test("D: сторінку перетягують мишкою — і порядок зберігається", async (t) => {
  const { dir, it1 } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk", "vybir"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 60 });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await open(browser, url);

  /* «Головну» кидаємо у ВЕРХНЮ половину останнього рядка — тобто «перед
     "vybir"». Саме тут пастка зсуву видна наживо: без поправки сторінка,
     витягнута зверху, ставала б на одну нижче — ПІСЛЯ "vybir". Кидок «після
     останнього» її б не показав: там зайвий індекс мовчки обрізає сервер
     (`move_page`), і мутація поправки лишала тест зеленим (перевірено). */
  const target = page.locator('.panel [data-page="vybir"]');
  const box = await target.boundingBox();
  await page.locator('.panel [data-page="holovna"]').dragTo(target, {
    targetPosition: { x: box.width / 2, y: 3 },
  });
  assert.deepEqual(await until(() => diskOrder(it1), ["poshuk", "holovna", "vybir"]),
    ["poshuk", "holovna", "vybir"], "перетягування поставило сторінку не туди, куди кидали");
  assert.equal(await page.evaluate(() =>
    document.querySelectorAll(".row--drop-before,.row--drop-after").length), 0,
  "після кидка лишилась лінія-підказка");
});
