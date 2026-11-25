/**
 * Розміри знімка коментатора (0.35.1, баг 1): рендер min(DPR, 2) у межах стелі пікселів; мініатюра ≤ 720 (inline, `meta.shot`),
 * повний ≤ 2400 (JPEG, у `uploadShot` → `meta.shotUrl`); відповідь сховища `{ skipped: true }`; лайтбокс бере `shotUrl`.
 * `html2canvas` підмінено шпигуном, що віддає полотно `round(w·scale) × round(h·scale)` — мережа не потрібна.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const PAGE = `<!doctype html><html><head><meta charset="utf-8"><title>t</title></head><body style="margin:0">
<div id="small" style="width:300px;height:100px;background:#eef"></div>
<div id="mid" style="width:1000px;height:800px;background:#efe"></div>
<div id="huge" style="width:3000px;height:3000px;background:#fee"></div>
<p id="lone" style="margin:0;padding:10px">Абзац</p></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** upload: код `uploadShot` (рядок) або null; dpr: deviceScaleFactor. Спадок: кожне завантаження пише в `window.__uploads`. */
async function boot({ dpr = 1, upload = null, withHost = false, version = "1", seed = null } = {}) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 }, deviceScaleFactor: dpr });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(({ upload, withHost, version, seed }) => {
    window.__calls = []; window.__uploads = [];
    window.__rel = []; window.__holdN = 0; window.__saves = [];
    window.html2canvas = (el, opts) => {
      const r = el.getBoundingClientRect(); window.__calls.push({ w: r.width, h: r.height, scale: opts.scale });
      if (window.__holdN > 0) { window.__holdN -= 1; return new Promise((res) => window.__rel.push(() => res(mk(r, opts)))); }
      return Promise.resolve(mk(r, opts));
    };
    const mk = (r, opts) => {
      const c = document.createElement("canvas");
      c.width = Math.round(r.width * opts.scale); c.height = Math.round(r.height * opts.scale);
      const g = c.getContext("2d"); g.fillStyle = "#357"; g.fillRect(0, 0, c.width, c.height); g.fillStyle = "#fa0"; g.fillRect(0, 0, c.width / 2, c.height / 2);
      return Promise.resolve(c);
    };
    const mem = seed ? JSON.parse(seed) : []; window.__mem = mem;
    const store = { load: () => mem.slice(), save: (l) => { window.__saves.push(JSON.parse(JSON.stringify(l))); mem.length = 0; mem.push(...l); } };
    if (upload) store.uploadShot = (0, eval)(`(${upload})`);
    window.CommentLayer.init({ projectId: "t", storage: store, version, user: { name: "Тест" },
      host: withHost ? { onReady() {}, onChange() {}, onSelect() {}, onMode() {} } : undefined });
    window.CommentLayer.setCommentMode(true);
  }, { upload, withHost, version, seed: seed && JSON.stringify(seed) });
  return page;
}
const SHADOW = "document.querySelector('[data-comment-layer]').shadowRoot";
async function addComment(page, sel, text) {
  await page.click(sel, { position: { x: 3, y: 3 } });
  await page.waitForFunction(`!!${SHADOW}.querySelector('.compose textarea')`);
  await page.evaluate((t) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await page.evaluate(`${SHADOW}.querySelector('.compose .save').click()`);
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text, { timeout: 15000 });
  return page.evaluate((t) => window.__mem.find((c) => c.text === t), text);
}
const dims = (page, url) => page.evaluate(async (u) => {
  const img = new Image(); img.src = u; await img.decode(); return [img.naturalWidth, img.naturalHeight];
}, url);
const UPLOAD_OK = `(id, shot) => { window.__uploads.push({ id, shot }); return Promise.resolve("https://example.test/s/" + id + ".jpg"); }`;

test("DPR 2, звичайна ціль: рендер у масштабі 2", async () => {
  const page = await boot({ dpr: 2, upload: UPLOAD_OK });
  await addComment(page, "#small", "а");
  assert.deepEqual(await page.evaluate(() => window.__calls.map((c) => c.scale)), [2]);
  await page.close();
});

test("DPR 1: рендер у масштабі 1", async () => {
  const page = await boot({ dpr: 1, upload: UPLOAD_OK });
  await addComment(page, "#small", "б");
  assert.deepEqual(await page.evaluate(() => window.__calls.map((c) => c.scale)), [1]);
  await page.close();
});

test("DPR 2, 1000×800 (4 Мп у ×2) — ще ×2", async () => {
  const page = await boot({ dpr: 2, upload: UPLOAD_OK });
  await addComment(page, "#mid", "в");
  assert.deepEqual(await page.evaluate(() => window.__calls.map((c) => c.scale)), [2]);
  await page.close();
});

test("DPR 2, ціль 3000×3000: масштаб знижено під стелю 6 Мп (≈ 0.8165), а не 2", async () => {
  const page = await boot({ dpr: 2, upload: UPLOAD_OK });
  await addComment(page, "#huge", "г");
  const [c] = await page.evaluate(() => window.__calls);
  assert.equal(c.w, 3000); assert.equal(c.h, 3000);
  assert.ok(c.scale * c.scale * c.w * c.h <= 6000000, `площа ${c.scale * c.scale * c.w * c.h} понад 6 Мп`);
  assert.equal(c.scale.toFixed(3), "0.816");   // sqrt(6e6 / 9e6): сама стеля — 6 Мп
  await page.close();
});

test("мініатюра в межах 720×720 і JPEG; повний у uploadShot — JPEG ≤ 2400 і більший за мініатюру", async () => {
  const page = await boot({ dpr: 2, upload: UPLOAD_OK });
  const c = await addComment(page, "#mid", "д");
  assert.equal(c.meta.shotMiss, undefined);
  assert.ok(c.meta.shot.startsWith("data:image/jpeg"));
  const [tw, th] = await dims(page, c.meta.shot);
  assert.ok(tw <= 720 && th <= 720 && Math.max(tw, th) === 720, `мініатюра ${tw}×${th}`);
  const ups = await page.evaluate(() => window.__uploads);
  assert.equal(ups.length, 1);
  assert.ok(ups[0].shot.startsWith("data:image/jpeg"));
  const [fw, fh] = await dims(page, ups[0].shot);
  assert.deepEqual([fw, fh], [2000, 1600]);   // 1000×800 у ×2
  assert.ok(ups[0].shot.length > c.meta.shot.length, "повний має бути більшим за мініатюру");
  assert.equal(c.meta.shotUrl, "https://example.test/s/" + c.id + ".jpg");
  await page.close();
});

test("велика ціль: повний вписано в 2400×2400, мініатюра — в 720×720", async () => {
  const page = await boot({ dpr: 2, upload: UPLOAD_OK });
  const c = await addComment(page, "#huge", "е");
  const [fw, fh] = await dims(page, (await page.evaluate(() => window.__uploads))[0].shot);
  assert.deepEqual([fw, fh], [2400, 2400]);
  assert.deepEqual(await dims(page, c.meta.shot), [720, 720]);
  await page.close();
});

test("мала ціль: без збільшення (300×100 у ×2 = 600×200 — і повний, і мініатюра такі самі)", async () => {
  const page = await boot({ dpr: 2, upload: UPLOAD_OK });
  const c = await addComment(page, "#small", "є");
  assert.deepEqual(await dims(page, c.meta.shot), [600, 200]);
  assert.deepEqual(await dims(page, (await page.evaluate(() => window.__uploads))[0].shot), [600, 200]);
  await page.close();
});

test("сховище відповіло { skipped: true } — без повтору, без shotMiss, без shotUrl", async () => {
  const page = await boot({ upload: `(id, shot) => { window.__uploads.push({ id }); return Promise.resolve({ skipped: true }); }` });
  const t0 = Date.now();
  const c = await addComment(page, "#small", "ж");
  assert.ok(Date.now() - t0 < 450, "повтору через 500 мс бути не має");
  assert.equal(c.meta.shotMiss, undefined);
  assert.equal(c.meta.shotUrl, undefined);
  assert.ok(c.meta.shot.startsWith("data:image/jpeg"));
  assert.equal(await page.evaluate(() => window.__uploads.length), 1);
  await page.close();
});

test("сховище дало null — одна повторна спроба й shotMiss: upload, мініатюра лишається", async () => {
  const page = await boot({ upload: `(id, shot) => { window.__uploads.push({ id }); return Promise.resolve(null); }` });
  const c = await addComment(page, "#small", "з");
  assert.equal(c.meta.shotMiss, "upload");
  assert.equal(await page.evaluate(() => window.__uploads.length), 2);
  assert.ok(c.meta.shot.startsWith("data:image/jpeg"));
  await page.close();
});

const SHOT_THUMB = "data:image/png;base64,iVBORw0KGgo=";
const SHOT_FULL = "https://example.test/s/full.jpg";
const seed = (extra) => [{ id: "p1", author: "А", text: "пін", status: "open", ts: "13.11.2026 10:00",
  meta: { seq: 1, iteration: "1", version: "1/inshe", shot: SHOT_THUMB, ...extra } }];
const lbSrc = (page) => page.evaluate(`(() => { const i = ${SHADOW}.querySelector('.cllb img'); return i && i.getAttribute('src'); })()`);

test("лайтбокс: клік по img.shot картки відкриває meta.shotUrl; без нього — meta.shot", async () => {
  for (const [extra, want] of [[{ shotUrl: SHOT_FULL }, SHOT_FULL], [{}, SHOT_THUMB]]) {
    const page = await boot({ seed: seed(extra) });
    await page.evaluate(`${SHADOW}.querySelector('#cp1 img.shot').click()`);
    assert.equal(await lbSrc(page), want);
    await page.close();
  }
});

/* 0.39.1: `focus()` піна іншої сторінки в режимі хоста сам нічого не показує й вертає false — показ вирішує хост:
   оболонка Deai веде на сторінку коментаря, превʼю відкриває знімок через `openShot` (живий тест 15б у
   preview-comments). */
test("лайтбокс: openShot відкриває meta.shotUrl, інакше meta.shot; focus «іншої сторінки» (host) — false без лайтбокса", async () => {
  for (const [extra, want] of [[{ shotUrl: SHOT_FULL }, SHOT_FULL], [{}, SHOT_THUMB]]) {
    const page = await boot({ withHost: true, version: "1/holovna", seed: seed(extra) });
    await page.evaluate(() => window.CommentLayer.openShot("p1"));
    assert.equal(await lbSrc(page), want);
    await page.evaluate(`${SHADOW}.querySelector('.cllb').click()`);
    assert.equal(await lbSrc(page), null);
    assert.equal(await page.evaluate(() => window.CommentLayer.focus("p1")), false, "інша сторінка (host): focus вертає false");
    assert.equal(await lbSrc(page), null, "інша сторінка (host): focus сам лайтбокс не відкриває");
    await page.close();
  }
});

const fillAndSave = async (page, sel, text) => {
  await page.click(sel, { position: { x: 3, y: 3 } });
  await page.waitForFunction(`!!${SHADOW}.querySelector('.compose textarea')`);
  await page.evaluate((t) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await page.evaluate(`${SHADOW}.querySelector('.compose .save').click()`);
};

test("DPR 0.67 (зум браузера < 100 %): масштаб не нижче 1", async () => {
  const page = await boot({ dpr: 0.67, upload: UPLOAD_OK });
  await addComment(page, "#small", "м1");
  assert.deepEqual(await page.evaluate(() => window.__calls.map((c) => c.scale)), [1]);
  await page.close();
});

test("toBlob не відповідає: після 4 с — запасний toDataURL, пін зберігається з повним знімком", async () => {
  const page = await boot({ upload: UPLOAD_OK });
  await page.evaluate(() => { HTMLCanvasElement.prototype.toBlob = function () { /* ніколи не кличе колбек */ }; });
  const t0 = Date.now();
  const c = await addComment(page, "#small", "м2");
  const dt = Date.now() - t0;
  assert.ok(dt >= 3500 && dt < 9000, `очікували ≈ 4 с, а було ${dt} мс`);
  assert.equal(c.meta.shotMiss, undefined);
  const ups = await page.evaluate(() => window.__uploads);
  assert.equal(ups.length, 1);
  assert.ok(ups[0].shot.startsWith("data:image/jpeg"));
  assert.equal(c.meta.shotUrl, "https://example.test/s/" + c.id + ".jpg");
  await page.close();
});

test("пін, що ще знімається, не потрапляє в чужий save: перша поява в сховищі — одразу з meta.shot і shotUrl", async () => {
  const page = await boot({ upload: UPLOAD_OK, withHost: true });
  await page.evaluate(() => { window.__holdN = 1; });   // знімок першого піна (A) висить
  await fillAndSave(page, "#small", "A");
  await page.waitForFunction(() => window.__rel.length === 1);
  await fillAndSave(page, "#mid", "B");
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), "B", { timeout: 15000 });
  const withA = await page.evaluate(() => window.__saves.filter((l) => l.some((c) => c.text === "A")).length);
  assert.equal(withA, 0, "A (знімок ще триває) потрапив у чужий save без shotUrl");
  assert.deepEqual(await page.evaluate(() => window.__saves.at(-1).map((c) => c.text)), ["B"]);
  assert.equal(await page.evaluate(() => JSON.stringify(window.__saves).includes("_awaitShot")), false, "службова позначка протекла в сховище");
  // пін A при цьому видно в знімку для хоста
  assert.ok(await page.evaluate(() => window.CommentLayer.snapshot().comments.some((c) => c.text === "A" && !("_awaitShot" in c))));
  await page.evaluate(() => window.__rel.forEach((f) => f()));
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), "A", { timeout: 15000 });
  const first = await page.evaluate(() => window.__saves.find((l) => l.some((c) => c.text === "A")).find((c) => c.text === "A"));
  assert.ok(first.meta.shot.startsWith("data:image/jpeg"));
  assert.equal(first.meta.shotUrl, "https://example.test/s/" + first.id + ".jpg");
  await page.close();
});

test("лайтбокс: shotUrl не відкрився (404) — одноразово переходить на meta.shot", async () => {
  const page = await boot({ seed: seed({ shotUrl: SHOT_FULL }) });
  await page.route(SHOT_FULL, (r) => r.fulfill({ status: 404, body: "no" }));
  await page.evaluate(`${SHADOW}.querySelector('#cp1 img.shot').click()`);
  await page.waitForFunction(`${SHADOW}.querySelector('.cllb img').getAttribute('src') === ${JSON.stringify(SHOT_THUMB)}`);
  await page.close();
  const p2 = await boot({ withHost: true, version: "1/holovna", seed: seed({ shotUrl: SHOT_FULL }) });
  await p2.route(SHOT_FULL, (r) => r.fulfill({ status: 404, body: "no" }));
  await p2.evaluate(() => window.CommentLayer.openShot("p1"));
  await p2.waitForFunction(`${SHADOW}.querySelector('.cllb img').getAttribute('src') === ${JSON.stringify(SHOT_THUMB)}`);
  await p2.close();
});
