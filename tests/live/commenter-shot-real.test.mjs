/**
 * Знімок на СПРАВЖНЬОМУ html2canvas 1.4.1 (0.35.1): бібліотека розбирає лише rgb/hsl, тож сучасні кольори
 * (`color-mix`, `oklch`, `oklab`), ціль-SVG і CSS-переходи в клоні давали `shotMiss: render`. Бібліотека — копія
 * у tests/fixtures/vendor (CDN у headless недосяжний); у решті живих тестів html2canvas — шпигун.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const H2C = readFileSync(path.join(ROOT, "tests", "fixtures", "vendor", "html2canvas-1.4.1.min.js"), "utf8");

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(html, { route } = {}) {
  const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
  if (route) await route(page);
  await page.setContent(html, { waitUntil: "load" });
  await page.addScriptTag({ content: H2C });
  await page.evaluate(() => {   // обгортка лише запам'ятовує, який елемент отримала бібліотека, і викликає справжню
    const real = window.html2canvas;
    window.__targets = [];
    window.html2canvas = (el, opts) => { window.__targets.push(el.tagName.toLowerCase()); return (window.__wrap || real)(el, opts, real); };
  });
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(() => {
    const mem = [];
    window.__mem = mem;
    const store = { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } };
    window.CommentLayer.init({ projectId: "t", storage: store, version: "1", user: { name: "Тест" },
      host: { onReady() {}, onChange() {}, onSelect() {}, onMode() {} } });
    window.CommentLayer.setCommentMode(true);
  });
  return page;
}
async function addComment(page, sel, text) {
  await page.click(sel);
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await page.evaluate((t) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").click());
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text, { timeout: 20000 });
  return page.evaluate((t) => window.__mem.find((c) => c.text === t).meta || {}, text);
}
function assertShot(meta) {
  assert.equal(meta.shotMiss, undefined, `shotMiss: ${meta.shotMiss}`);
  assert.ok(typeof meta.shot === "string" && meta.shot.startsWith("data:image/jpeg"), "meta.shot має бути JPEG");
}
/** Піксель знімка в частках ширини/висоти. */
function pixelAt(page, dataUrl, fx, fy) {
  return page.evaluate(async ([u, x, y]) => {
    const img = new Image(); img.src = u; await img.decode();
    const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
    const g = c.getContext("2d"); g.drawImage(img, 0, 0);
    return Array.from(g.getImageData(Math.floor(img.width * x), Math.floor(img.height * y), 1, 1).data);
  }, [dataUrl, fx, fy]);
}

test("(a) тінь в oklch() і градієнт із color-mix(in oklab) у цілі — знімок є, колір не втрачено", async () => {
  const page = await boot(`<!doctype html><html><body style="margin:40px;background:#fff">
<div id="card" style="width:300px;height:120px;box-shadow:0 4px 12px oklch(0.6 0.2 30 / 0.5);
 background:linear-gradient(90deg, color-mix(in oklab, #00a000 100%, #00a000), color-mix(in oklab, #00a000 100%, #00a000));
 border:2px solid color-mix(in srgb, #123 50%, #fff)"><p id="t">Картка</p></div></body></html>`);
  const meta = await addComment(page, "#card", "а");
  assertShot(meta);
  const [r, g, b] = await pixelAt(page, meta.shot, 0.5, 0.5);
  assert.ok(g > 120 && r < 80 && b < 80, `градієнт мав лишитись зеленим, а піксель rgb(${r}, ${g}, ${b})`);
  await page.close();
});

test("(b) фон body у color-mix(in srgb) і звичайний <p> у цілі — знімок є", async () => {
  const page = await boot(`<!doctype html><html><body style="margin:40px;background:color-mix(in srgb, #fff 80%, #ccc)">
<p id="p" style="color:color-mix(in srgb, #000 70%, #00f)">Простий абзац</p></body></html>`);
  assertShot(await addComment(page, "#p", "б"));
  await page.close();
});

test("(c) клік по <svg> в кнопці — html2canvas отримує кнопку, знімок є", async () => {
  const page = await boot(`<!doctype html><html><body style="margin:40px">
<button id="b" style="padding:10px;background:#eee"><svg id="ic" width="24" height="24" viewBox="0 0 24 24"><path id="pa" d="M2 2h20v20H2z" fill="#c00"/></svg> Додати</button></body></html>`);
  const meta = await addComment(page, "#ic", "в");
  assertShot(meta);
  assert.deepEqual(await page.evaluate(() => window.__targets), ["button"]);
  await page.close();
});

const BTN_PAGE = `<!doctype html><html><head><link rel="stylesheet" href="https://example.test/t.css"></head>
<body style="margin:40px"><button id="b">Кнопка</button></body></html>`;
const BTN_CSS = "#b{padding:12px 20px;border:0;color:#fff;background-color:color-mix(in srgb, #3366cc 90%, #ffffff);transition:background-color 3s linear}";
const routeCss = (delay) => async (page) => {
  await page.route("https://example.test/t.css", async (route) => {
    if (delay) await new Promise((r) => setTimeout(r, delay));
    await route.fulfill({ status: 200, contentType: "text/css", body: BTN_CSS });
  });
};

test("(d) перехід із зовнішньої таблиці в клоні: кольори нормалізовані, переходи вимкнені — знімок є", async () => {
  const page = await boot(BTN_PAGE, { route: routeCss(150) });
  assertShot(await addComment(page, "#b", "г"));
  await page.close();
});

test("(d') контроль: кольори нормалізовані, але стиль «transition:none» вирізано — знімок НЕ виходить", async () => {
  const page = await boot(BTN_PAGE, { route: routeCss(150) });
  await page.evaluate(() => {
    window.__wrap = (el, opts, real) => {
      const oc = opts.onclone;
      return real(el, { ...opts, onclone: (doc, e) => {
        const W = doc.defaultView, orig = W.Node.prototype.appendChild;
        W.Node.prototype.appendChild = function (n) { return n.tagName === "STYLE" && /transition:\s*none/.test(n.textContent) ? n : orig.call(this, n); };
        try { oc(doc, e); } finally { W.Node.prototype.appendChild = orig; }
      } });
    };
  });
  const meta = await addComment(page, "#b", "г2");
  assert.equal(meta.shot, undefined, "без вимкнення переходів знімок мав зірватись (інакше тест не доводить нічого)");
  assert.equal(meta.shotMiss, "render");
  await page.close();
});
