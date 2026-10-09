/**
 * «В Figma» (T-41) живцем: справжній Chromium, справжній `capture.js` Figma,
 * справжній буфер обміну.
 *
 * Мапа «перевірка → запобіжник → що буде без запобіжника»:
 *
 *   оверлеї не їдуть у Figma — `markOverlays` у `captureToFigma`
 *     (`app/figma-capture.js`). Без нього вкладка й панель коментатора
 *     потрапляють у payload з реальними координатами (виміряно пілотом
 *     28.09.2026). ⛔ Перевірка — за ТЕКСТОМ оверлеїв, а не за атрибутами:
 *     скрипт викидає атрибути, хост стає безіменним DIV, і пошук
 *     `data-comment-layer` у payload зелений навіть при повному витоку (саме
 *     так збрехав перший замір пілота). Свідок: текст оверлеїв ДО захоплення
 *     непорожній — інакше перевірка стерегла б порожнечу.
 *   ширина — рамка з пресетом «мобайл» дає `viewportRect.width === 375`.
 *   «Огляд» — кнопка `disabled` з причиною в title (`figmaWhyKey`).
 *   невдача гучна — скрипт не завантажився / буфер заборонений → оверлей
 *     `tell()` з причиною, а не тиша. Буфер забороняє сам headless-Chromium
 *     без виданого дозволу — рівно так, як вбудований браузер Claude.
 *
 * `capture.js` тягнемо з mcp.figma.com ОДИН раз і віддаємо браузеру через
 * `page.route`: прогін не залежить від мережі на кожному кліку. Немає мережі —
 * тест ПРОПУСКАЄТЬСЯ з причиною (фіча без мережі не працює за побудовою,
 * `technical_debt.md`), а не зеленіє.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { CAPTURE_SRC } from "../../app/figma-capture.js";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 11490;
const VIEW = { width: 1400, height: 900 };
const MARK = "figma-fixture-marker-7c1";

const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="margin:0;font:16px sans-serif"><main style="padding:24px">`
  + `<h1>${id}</h1><p>${MARK}</p></main></body></html>`;

let SCRIPT = null;
let WHY_SKIP = "";
try {
  const res = await fetch(CAPTURE_SRC);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  SCRIPT = await res.text();
} catch (e) {
  WHY_SKIP = `capture.js недоступний (${e.message}) — без мережі фіча не працює`;
}

async function open(t, { grant = true, route = "script", port = PORT_BASE } = {}) {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: port });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const ctx = await browser.newContext({ viewport: VIEW });
  if (grant) await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: url });
  await ctx.route(CAPTURE_SRC, (r) => (route === "abort"
    ? r.abort()
    : r.fulfill({ status: 200, contentType: "text/javascript", body: SCRIPT })));
  const page = await ctx.newPage();
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const d = document.getElementById("frame")?.contentDocument;
    return !!(d && d.defaultView.CanvasInspector && d.querySelector("[data-comment-layer]")?.shadowRoot);
  }, null, { timeout: 15000 });
  return page;
}

/** Тексти всередині Shadow DOM наших оверлеїв — те, що НЕ сміє доїхати у Figma. */
const overlayTexts = (page) => page.evaluate(() => {
  const d = document.getElementById("frame").contentDocument;
  const out = new Set();
  for (const h of d.querySelectorAll("[data-comment-layer],[data-canvas-inspector]")) {
    const walk = (n) => {
      if (n.nodeType === 3 && n.textContent.trim().length > 2) out.add(n.textContent.trim());
      for (const c of n.childNodes) walk(c);
      if (n.shadowRoot) walk(n.shadowRoot);
    };
    walk(h);
  }
  return [...out];
});

/** Дочекатись payload Figma в буфері й розібрати дерево. */
async function readPayload(page) {
  /* Цикл у Node, а не `waitForFunction`: async-предикат там повертає проміс,
     а проміс — truthy, тож очікування «збувалось» миттєво з порожнім значенням. */
  let html = "";
  for (let i = 0; i < 100 && !html; i += 1) {
    html = await page.evaluate(async () => {
      try {
        for (const it of await navigator.clipboard.read()) {
          if (!it.types.includes("text/html")) continue;
          const v = await (await it.getType("text/html")).text();
          if (v.includes("(figh2d)")) return v;
        }
      } catch (e) { /* буфер ще порожній */ }
      return "";
    });
    if (!html) await page.waitForTimeout(200);
  }
  assert.ok(html, "за 20 с у буфері так і не зʼявився payload Figma");
  const b64 = html.match(/\(figh2d\)(.*?)\(\/figh2d\)/)[1];
  return JSON.parse(Buffer.from(b64, "base64").toString("utf8"));
}

const textNodes = (doc) => {
  const out = [];
  const walk = (n) => {
    if (n.nodeType === 3 && n.text) out.push(n.text.trim());
    for (const c of n.childNodes || []) walk(c);
  };
  walk(doc.root);
  return out;
};

test("клік «В Figma» кладе в буфер макет — і жодного нашого оверлея", { skip: WHY_SKIP || false }, async (t) => {
  const page = await open(t);
  const leakable = await overlayTexts(page);
  assert.ok(leakable.length >= 2,
    `свідок: в оверлеях знайшлось лише ${leakable.length} текстів — перевірка стерегла б порожнечу`);

  await page.click('#bar [data-act="figma"]');
  const doc = await readPayload(page);
  const texts = textNodes(doc);
  assert.ok(texts.includes(MARK), "у payload немає самого макета");
  const leaked = leakable.filter((x) => texts.includes(x));
  assert.deepEqual(leaked, [], "тексти наших оверлеїв доїхали у Figma");
});

test("мобайл копіюється в мобільній ширині", { skip: WHY_SKIP || false }, async (t) => {
  const page = await open(t, { port: PORT_BASE + 10 });
  await page.click('#bar [data-act="vp"][data-val="mobile"]');
  await page.waitForFunction(() => document.getElementById("frame").clientWidth === 375);
  await page.click('#bar [data-act="figma"]');
  const doc = await readPayload(page);
  assert.equal(doc.viewportRect.width, 375);
});

test("в «Огляді» кнопка вимкнена з причиною", { skip: WHY_SKIP || false }, async (t) => {
  const page = await open(t, { port: PORT_BASE + 20 });
  const btn = '#bar [data-act="figma"]';
  assert.equal(await page.$eval(btn, (b) => b.disabled), false);
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForFunction((sel) => document.querySelector(sel)?.disabled === true, btn);
  assert.match(await page.$eval(btn, (b) => b.title), /Огляд/);
});

test("скрипт не завантажився — гучна причина, а не тиша", { skip: WHY_SKIP || false }, async (t) => {
  const page = await open(t, { route: "abort", port: PORT_BASE + 30 });
  await page.click('#bar [data-act="figma"]');
  const box = page.locator(".cv-ask");
  await box.waitFor({ timeout: 15000 });
  assert.match(await box.innerText(), /mcp\.figma\.com/);
  // «Копіюю…» знято: кнопка знову жива.
  await page.waitForFunction(() => !document.querySelector('#bar [data-act="figma"]').disabled);
});

test("буфер заборонений — гучна причина з порадою", { skip: WHY_SKIP || false }, async (t) => {
  const page = await open(t, { grant: false, port: PORT_BASE + 40 });
  await page.click('#bar [data-act="figma"]');
  const box = page.locator(".cv-ask");
  await box.waitFor({ timeout: 15000 });
  assert.match(await box.innerText(), /Chrome/);
});
