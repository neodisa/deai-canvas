/**
 * ⌘F по макету (0.40): плашка, лічильник, Enter/⇧Enter/⌘G, Esc, підсвітка через CSS.highlights у вікні рамки БЕЗ жодної
 * мутації DOM макета (MutationObserver у рамці мовчить), новий пошук після зміни сторінки (і ОДИН захоплювач клавіш у рамці
 * після перезавантаження), «Огляд» → фільтр панелі, «Задачі» → пошук задач, ⌘G «згрупувати» не зламано (плашка закрита) і не
 * чіпається, коли плашка відкрита; модифікатор платформний (на Mac Ctrl+F — «курсор уперед», його не перехоплюємо).
 * `ControlOrMeta` — псевдонім Playwright: на Mac ⌘, інакше Ctrl (збігається з `isMacPlatform()` оболонки).
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 53000;
const VIEW = { width: 1440, height: 900 };
const MOD = "ControlOrMeta";
const html = (id) => id === "holovna"
  ? `<!DOCTYPE html><html><head><meta charset="utf-8"><style>.hid{display:none}</style></head><body style="margin:40px">
<h1>Головна сторінка</h1><p>Слово слово СЛОВО</p><p class="hid">слово приховане</p><script>var слово = 1</script>
<div style="height:1600px"></div><p id="far">слово внизу</p></body></html>`
  : `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>Пошук</h1><p>інше слово тут</p><img src="/slow.png" alt=""></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(t, off, build = () => taskFixture({ html })) {
  const { dir } = build();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  await page.waitForSelector('[data-act="page"][data-val="holovna"]', { timeout: 20000 });
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("#far", { timeout: 20000 });
  return { page, f };
}
const counter = (page) => page.$eval("#find-n", (e) => e.textContent);
const waitCount = (page, text, timeout = 10000) => page.waitForFunction((x) => document.getElementById("find-n").textContent === x, text, { timeout });
const hits = (f) => f.evaluate(() => [...CSS.highlights.get("deai-find")].map((r) => r.toString()));
const curHit = (f) => f.evaluate(() => [...CSS.highlights.get("deai-find-cur")].map((r) => r.toString()));
const findHidden = (page) => page.evaluate(() => document.getElementById("find").hidden);

test("1: ⌘F з фокусом в оболонці: плашка, лічильник, Enter/⇧Enter/⌘G, Esc знімає підсвітку", async (t) => {
  const { page, f } = await boot(t, 0);
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.waitForSelector("#find:not([hidden])");
  assert.equal(await page.evaluate(() => document.activeElement.id), "find-q");
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  assert.deepEqual((await hits(f)).map((s) => s.toLowerCase()), ["слово", "слово", "слово", "слово"], "4 видимі збіги: без display:none і без <script>");
  await page.keyboard.press("Enter");
  assert.equal(await counter(page), "2 / 4");
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.press("Shift+Enter");
  assert.equal(await counter(page), "4 / 4", "⇧Enter ходить по колу назад");
  assert.equal((await curHit(f)).length, 1);
  await f.waitForFunction(() => { const r = document.getElementById("far").getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
  await page.keyboard.press(`${MOD}+KeyG`);
  assert.equal(await counter(page), "1 / 4");
  await page.keyboard.press(`${MOD}+Shift+KeyG`);
  assert.equal(await counter(page), "4 / 4");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#find", { state: "hidden" });
  assert.equal(await f.evaluate(() => CSS.highlights.has("deai-find")), false, "підсвітку знято");
  assert.equal(await f.evaluate(() => document.adoptedStyleSheets.length), 0, "правило ::highlight знято з документа");
});

test("2: ⌘F з фокусом У МАКЕТІ відкриває плашку; повторний ⌘F виділяє текст у полі; ⌘G з рамки — один крок", async (t) => {
  const { page, f } = await boot(t, 100);
  await f.click("h1");
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.waitForSelector("#find:not([hidden])");
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await page.keyboard.press(`${MOD}+KeyF`);
  assert.equal(await page.evaluate(() => { const i = document.getElementById("find-q"); return i.selectionStart === 0 && i.selectionEnd === i.value.length; }), true);
  await f.click("h1");
  await page.keyboard.press(`${MOD}+KeyG`);
  assert.equal(await counter(page), "2 / 4", "⌘G з фокусом у макеті — рівно один крок");
});

test("3: пошук нічого не міняє в DOM макета (MutationObserver у рамці мовчить), нема збігів — «0 / 0»", async (t) => {
  const { page, f } = await boot(t, 200);
  await f.evaluate(() => {
    window.__muts = 0;
    new MutationObserver((r) => { window.__muts += r.length; }).observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
  });
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.keyboard.type("ЯЯЯ");
  await waitCount(page, "0 / 0");
  await page.keyboard.press("Escape");
  assert.equal(await f.evaluate(() => window.__muts), 0, "жодної мутації DOM макета від пошуку");
});

test("4: зміна сторінки при відкритій плашці — запит шукається заново; після перезавантаження рамки один захоплювач клавіш", async (t) => {
  const { page, f } = await boot(t, 300);
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await page.click('[data-act="page"][data-val="poshuk"]');
  await waitCount(page, "1 / 1", 15000);
  await page.click('[data-act="page"][data-val="holovna"]');
  await waitCount(page, "1 / 4", 15000);
  const f2 = await (await page.$("#frame")).contentFrame();
  await f2.waitForSelector("#far");
  await f2.click("h1");
  await page.keyboard.press(`${MOD}+KeyG`);
  assert.equal(await counter(page), "2 / 4", "після двох перезавантажень рамки ⌘G з неї — один крок (не два захоплювачі)");
  void f;
});

test("5: «Огляд» — ⌘F ставить фокус у фільтр сторінок, плашки нема; плашку, відкриту в «Макеті», «Огляд» закриває", async (t) => {
  const { page } = await boot(t, 400);
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.waitForSelector("#find:not([hidden])");
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  assert.equal(await findHidden(page), true, "плашка пішла разом із «Макетом»");
  await page.keyboard.press(`${MOD}+KeyF`);
  assert.equal(await page.evaluate(() => document.activeElement.id), "pp-filter");
  assert.equal(await findHidden(page), true);
});

test("5b: «Огляд» зі згорнутою панеллю — ⌘F розгортає її й фокусує фільтр", async (t) => {
  const { page } = await boot(t, 450);
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  await page.click('.panel [data-act="panel"]');
  await page.waitForFunction(() => document.body.classList.contains("panel-collapsed"));
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.waitForFunction(() => document.activeElement?.id === "pp-filter");
  assert.equal(await page.evaluate(() => document.body.classList.contains("panel-collapsed")), false);
});

test("6: «Задачі» — ⌘F ставить фокус у пошук задач, плашки нема", async (t) => {
  const { page } = await boot(t, 500);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#th-q");
  await page.keyboard.press(`${MOD}+KeyF`);
  assert.equal(await page.evaluate(() => document.activeElement.id), "th-q");
  assert.equal(await findHidden(page), true);
});

test("7: ⌘G «згрупувати» не зламано: плашка закрита — групує; плашка відкрита — ⌘G її крок, групування нема", async (t) => {
  const nested = () => {
    const nodes = [{ id: "holovna", name: "Головна", kind: "page", children: [
      { id: "s-err", name: "Помилка", kind: "state" }, { id: "s-empty", name: "Порожньо", kind: "state" }] },
    { id: "poshuk", name: "Пошук", kind: "page" }];
    const fx = taskFixture({ html, pages: ["holovna", "poshuk", "s-err", "s-empty"] });
    writeFileSync(path.join(fx.it1, "pages.json"), JSON.stringify({ pages: nodes }));
    return fx;
  };
  const { page, f } = await boot(t, 600, nested);
  void f;
  await page.waitForSelector('.panel [data-page="s-err"], .panel [data-page="holovna"] [data-act="toggle"]');
  if (!(await page.locator('.panel [data-page="s-err"]').count())) await page.click('.panel [data-page="holovna"] [data-act="toggle"]');
  await page.locator('.panel [data-page="s-err"] .row-name').click({ modifiers: [MOD] });
  await page.locator('.panel [data-page="s-empty"] .row-name').click({ modifiers: [MOD] });
  /* Плашка відкрита: ⌘G — «наступний збіг», а не «згрупувати». */
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await page.keyboard.press(`${MOD}+KeyG`);
  assert.equal(await counter(page), "2 / 4");
  assert.equal(await page.locator(".cv-ask").count(), 0, "⌘G при відкритій плашці не питає про теку");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#find", { state: "hidden" });
  /* Плашка закрита: ⌘G, як і раніше, «згрупувати». Фокус — не в полі вводу. */
  await page.locator('.panel [data-page="s-err"] .row-name').click({ modifiers: [MOD] });
  await page.locator('.panel [data-page="s-empty"] .row-name').click({ modifiers: [MOD] });
  await page.keyboard.press(`${MOD}+KeyG`);
  await page.waitForSelector(".cv-ask input", { timeout: 10000 });
  await page.keyboard.press("Enter");
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  await page.waitForSelector(".panel .row[data-kind=folder]", { timeout: 15000 });
});

test("8: платформний модифікатор: чужий (Ctrl на Mac, ⌘ деінде) пошук не відкриває й подію не гасить", async (t) => {
  const { page, f } = await boot(t, 700);
  const mac = await page.evaluate(() => /Mac/.test(navigator.platform));
  const wrong = mac ? "Control" : "Meta";
  await page.evaluate(() => {
    window.__prevented = [];
    window.addEventListener("keydown", (e) => { if (e.code === "KeyF") window.__prevented.push(e.defaultPrevented); });
  });
  await page.keyboard.press(`${wrong}+KeyF`);
  assert.equal(await findHidden(page), true, "чужий модифікатор не відкриває плашку");
  assert.deepEqual(await page.evaluate(() => window.__prevented), [false], "і не робить preventDefault (Ctrl+F на Mac — «курсор уперед»)");
  await f.click("h1");
  await page.keyboard.press(`${wrong}+KeyF`);
  assert.equal(await findHidden(page), true, "те саме з фокусом у макеті");
});

test("9: під модальним (палітра ⌘K) ⌘F плашку не відкриває", async (t) => {
  const { page } = await boot(t, 800);
  await page.keyboard.press(`${MOD}+KeyK`);
  await page.waitForSelector(".pal-it", { timeout: 5000 });
  await page.keyboard.press(`${MOD}+KeyF`);
  assert.equal(await findHidden(page), true);
});

test("10: повторний ⌘F лише фокусує й виділяє поле — збіг не скидається на перший", async (t) => {
  const { page, f } = await boot(t, 900);
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  assert.equal(await counter(page), "3 / 4");
  await page.keyboard.press(`${MOD}+KeyF`);
  assert.equal(await counter(page), "3 / 4", "повторний ⌘F не перезапускає пошук");
  assert.equal(await page.evaluate(() => { const i = document.getElementById("find-q"); return i.selectionStart === 0 && i.selectionEnd === i.value.length; }), true);
  await f.click("h1");
  await page.keyboard.press(`${MOD}+KeyF`);
  assert.equal(await counter(page), "3 / 4", "те саме з фокусом у макеті");
  /* Закрита й відкрита знову плашка шукає заново — з першого збігу. */
  await page.keyboard.press("Escape");
  await page.waitForSelector("#find", { state: "hidden" });
  await page.keyboard.press(`${MOD}+KeyF`);
  await waitCount(page, "1 / 4");
});

test("11: Esc: із фокусом у макеті закриває плашку; без плашки Esc до макета доходить; фокус вертається туди, звідки прийшов ⌘F", async (t) => {
  const { page, f } = await boot(t, 1000);
  await f.evaluate(() => { window.__esc = 0; document.addEventListener("keydown", (e) => { if (e.key === "Escape") window.__esc += 1; }); });
  await f.click("h1");
  await page.keyboard.press("Escape");
  assert.equal(await f.evaluate(() => window.__esc), 1, "плашки нема — Esc не гасимо (коментатор/інспектор ним користуються)");
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.waitForSelector("#find:not([hidden])");
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await f.click("h1");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#find", { state: "hidden" });
  assert.equal(await f.evaluate(() => window.__esc), 1, "Esc, що закрив плашку, до макета не дійшов");
  assert.equal(await f.evaluate(() => CSS.highlights.has("deai-find")), false);
  /* ⌘F із макета → Esc у полі: фокус у вікні рамки, не на body. */
  await f.click("h1");
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.waitForSelector("#find:not([hidden])");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#find", { state: "hidden" });
  assert.equal(await page.evaluate(() => document.activeElement.id), "frame", "фокус повернувся у рамку");
  /* ⌘F з елемента оболонки → ✕: фокус на тому ж елементі. */
  await page.focus("#bar button");
  const was = await page.evaluate(() => document.activeElement.outerHTML);
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.waitForSelector("#find:not([hidden])");
  await page.click('#find [data-find="close"]');
  await page.waitForSelector("#find", { state: "hidden" });
  assert.equal(await page.evaluate(() => document.activeElement.outerHTML), was, "фокус повернувся на елемент оболонки");
});

test("12: рамка пішла на чужий документ при відкритій плашці — лічильник скидається, а не лишає старе «N / M»", async (t) => {
  const other = createServer((q, r) => { r.setHeader("content-type", "text/html; charset=utf-8"); r.end("<!DOCTYPE html><title>x</title><p>слово</p>"); });
  await new Promise((ok) => other.listen(0, "127.0.0.1", ok));
  t.after(() => other.close());
  const { page, f } = await boot(t, 1100);
  void f;
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await page.evaluate((u) => { document.getElementById("frame").src = u; }, `http://127.0.0.1:${other.address().port}/`);
  await waitCount(page, "0 / 0", 15000);
});

test("13: між початком переходу рамки й її load ⌘G не фарбує нічого в новому документі зі старими збігами", async (t) => {
  const { page, f } = await boot(t, 1200);
  void f;
  let release = () => {};
  const held = new Promise((ok) => { release = ok; });
  await page.route("**/slow.png", async (route) => { await held; await route.fulfill({ status: 404, body: "" }); });
  await page.keyboard.press(`${MOD}+KeyF`);
  await page.keyboard.type("слово");
  await waitCount(page, "1 / 4");
  await page.click('[data-act="page"][data-val="poshuk"]');
  await page.waitForFunction(() => {
    const d = document.getElementById("frame").contentDocument;
    return d && d.readyState !== "complete" && !!d.body?.querySelector("img");
  }, null, { timeout: 15000 });
  await page.keyboard.press(`${MOD}+KeyG`);
  const st = await page.evaluate(() => {
    const d = document.getElementById("frame").contentDocument;
    return { sheets: d.adoptedStyleSheets.length, hl: d.defaultView.CSS.highlights.has("deai-find") || d.defaultView.CSS.highlights.has("deai-find-cur") };
  });
  assert.deepEqual(st, { sheets: 0, hl: false }, "у новому документі нічого зі старими збігами");
  release();
  await waitCount(page, "1 / 1", 15000);
});
