/**
 * «Важка SPA» (0.35, баг 1): знімок піна не зникає мовчки. Сторінка генерується тут: 40 карток × 10 інлайн-SVG-іконок по 4 SVG-елементи
 * + таблиця 30×8. `html2canvas` підмінено шпигуном (справжнього офлайн нема), CDN перехоплюється `page.route` — тож стенд міряє, ЯКА гілка
 * гасить знімок і який код (`meta.shotMiss`) лишається в піні, а не час рендеру.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const CDN = "https://cdn.jsdelivr.net/**";
const CDN_URL = "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js";
const CDN_SEL = `head script[src="${CDN_URL}"]`;

const icon = (n) => `<svg class="ic" width="12" height="12"><g><path d="M0 0h${n}v4z"/><circle r="1"/></g></svg>`;
const card = (i, icons = 10) => `<div class="card" id="card${i}" style="padding:10px"><h3>Картка ${i}</h3>${Array.from({ length: icons }, (_, k) => icon(k + 1)).join("")}</div>`;
const table = () => `<table id="tbl"><tbody>${Array.from({ length: 30 }, (_, r) => `<tr>${Array.from({ length: 8 }, (_, c) => `<td>${r}.${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
const PAGE = `<!doctype html><html><head><meta charset="utf-8"><title>t</title></head><body style="margin:40px">
<main id="m"><section id="cards" style="padding:10px">${Array.from({ length: 40 }, (_, i) => card(i)).join("")}</section>
<div id="bigcard" style="padding:10px"><h3>Велика</h3>${Array.from({ length: 100 }, (_, k) => icon(k + 1)).join("")}</div>
${table()}
<div id="huge" style="padding:10px">${"<i>x</i>".repeat(1600)}</div>
<p id="lone" style="padding:10px">Єдиний абзац без двійника</p></main></body></html>`;

// тіло скрипта-шпигуна `html2canvas` (для CDN/`shotLib` через route)
const SPY_SRC = `window.__calls = window.__calls || [];
window.html2canvas = (el, opts) => { window.__calls.push({ el, opts }); const c = document.createElement("canvas"); c.width = 20; c.height = 10; return Promise.resolve(c); };`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/**
 * h2c: "spy" | "none" | "throw" | "hang"; upload: функція uploadShot (рядок коду) чи null; initExtra: додаткові опції init;
 * anchors: код провайдера полотна.
 */
async function boot({ h2c = "spy", upload = null, initExtra = "{}", anchors = null, clock = false, url = null } = {}) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  if (clock) await page.clock.install();
  if (url) await page.goto(url); else await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(`(() => {
    window.__calls = []; window.__uploads = []; window.__saves = [];
    const mode = ${JSON.stringify(h2c)};
    if (mode === "spy") window.html2canvas = (el, opts) => { window.__calls.push({ el, opts }); const c = document.createElement("canvas"); c.width = 20; c.height = 10; return Promise.resolve(c); };
    if (mode === "throw") window.html2canvas = (el, opts) => { window.__calls.push({ el, opts }); throw new Error("boom"); };
    if (mode === "hang") window.html2canvas = (el, opts) => { window.__calls.push({ el, opts }); return new Promise(() => {}); };
    const mem = []; window.__mem = mem;
    const store = { load: () => mem.slice(), save: (l) => { window.__saves.push(JSON.parse(JSON.stringify(l))); mem.length = 0; mem.push(...l); } };
    ${upload ? `store.uploadShot = ${upload};` : ""}
    const base = { projectId: "t", storage: store, version: "1", user: { name: "Тест" } };
    ${anchors ? `base.anchors = ${anchors};` : `base.host = { onReady() {}, onChange() {}, onSelect() {}, onMode() {} };`}
    window.CommentLayer.init(Object.assign(base, ${initExtra}));
    ${anchors ? "" : "window.CommentLayer.setCommentMode(true);"}
  })()`);
  return page;
}
const SHADOW = `document.querySelector("[data-comment-layer]").shadowRoot`;
async function typeAndSave(page, text) {
  await page.waitForFunction(`!!${SHADOW}.querySelector(".compose textarea")`);
  await page.evaluate((t) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await page.evaluate(`${SHADOW}.querySelector(".compose .save").click()`);
}
async function addComment(page, sel, text, position) {
  await page.click(sel, position ? { position } : undefined);
  await typeAndSave(page, text);
  await waitSaved(page, text);
}
const waitSaved = (page, text) => page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text);
const cm = (page, text) => page.evaluate((t) => window.__mem.find((c) => c.text === t), text);
const corner = { x: 3, y: 3 };

test("1. картка з іконками понад бюджет SVG: знімок зроблено, понад-бюджетні іконки порожні, shotMiss нема; секція (>1500 елементів до обрізки) теж", async () => {
  const page = await boot();
  await addComment(page, "#bigcard", "велика картка", corner);
  assert.equal(await page.evaluate(() => window.__calls.length), 1, "html2canvas мав викликатись");
  const r = await page.evaluate(() => {
    const ig = window.__calls[0].opts.ignoreElements;
    const svgs = [...document.querySelectorAll("#bigcard svg")];
    const first = svgs[0], last = svgs[svgs.length - 1];
    return { firstPath: ig(first.querySelector("path")), firstSvg: ig(first), lastSvg: ig(last), lastPath: ig(last.querySelector("path")),
      lastCircle: ig(last.querySelector("circle")), card: ig(document.querySelector("#bigcard")) };
  });
  assert.deepEqual(r, { firstPath: false, firstSvg: false, lastSvg: false, lastPath: true, lastCircle: true, card: false });
  const c = await cm(page, "велика картка");
  assert.ok(c.meta.shot && c.meta.shot.startsWith("data:image/jpeg"));
  assert.equal(c.meta.shotMiss, undefined);
  // секція: 1680+ елементів до обрізки, лише ~700 після — ліміт вузлів рахується ПІСЛЯ обрізки
  const raw = await page.evaluate(() => document.querySelector("#cards").getElementsByTagName("*").length);
  assert.ok(raw > 1500, `секція має бути понад ліміт до обрізки, є ${raw}`);
  await addComment(page, "#cards", "уся секція", corner);
  assert.equal(await page.evaluate(() => window.__calls.length), 2);
  const s = await cm(page, "уся секція");
  assert.ok(s.meta.shot);
  assert.equal(s.meta.shotMiss, undefined);
  await page.close();
});

test("2. ціль понад 1500 елементів і після обрізки: shotMiss too-big, html2canvas не викликано", async () => {
  const page = await boot();
  await addComment(page, "#huge", "завелика", corner);
  assert.equal(await page.evaluate(() => window.__calls.length), 0);
  const c = await cm(page, "завелика");
  assert.equal(c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, "too-big");
  await page.close();
});

test("3. CDN недоступний: shotMiss no-lib; потім бібліотека з'являється — наступний пін знову йде на CDN (2 запити) і має знімок", async () => {
  const page = await boot({ h2c: "none" });
  let reqs = 0, ok = false;
  await page.route(CDN, (r) => { reqs++; return ok ? r.fulfill({ contentType: "application/javascript", body: SPY_SRC }) : r.abort(); });
  await addComment(page, "#lone", "без бібліотеки", corner);
  assert.equal((await cm(page, "без бібліотеки")).meta.shotMiss, "no-lib");
  assert.equal(reqs, 1);
  assert.equal(await page.evaluate((q) => document.querySelectorAll(q).length, CDN_SEL), 0, "невдалий <script> прибрано");
  ok = true;
  await addComment(page, "#lone", "бібліотека є", corner);
  assert.equal(reqs, 2, "кеш відхиленого проміса мав скинутись — CDN запитано знову");
  const c = await cm(page, "бібліотека є");
  assert.ok(c.meta.shot);
  assert.equal(c.meta.shotMiss, undefined);
  await page.close();
});

test("3б. CDN мовчить: після 8 с завантаження (page.clock) shotMiss no-lib, <script> прибрано", async () => {
  const page = await boot({ h2c: "none", clock: true });
  await page.route(CDN, () => {});   // запит висить
  await page.click("#lone", { position: corner });
  await typeAndSave(page, "CDN мовчить");
  await page.waitForFunction((q) => document.querySelector(q), CDN_SEL);
  await page.clock.fastForward(8500);
  await waitSaved(page, "CDN мовчить");
  assert.equal((await cm(page, "CDN мовчить")).meta.shotMiss, "no-lib");
  assert.equal(await page.evaluate((q) => document.querySelectorAll(q).length, CDN_SEL), 0);
  await page.close();
});

test("3в. гонка скидання: запізнілий очікувач не знищує чужий, новіший запит бібліотеки", async () => {
  const page = await boot({ h2c: "none", clock: true });
  const held = [];
  await page.route(CDN, (r) => { held.push(r); });
  const pin = async (text) => { await page.click("#lone", { position: corner }); await typeAndSave(page, text); };
  const nScripts = () => page.evaluate((q) => document.querySelectorAll(q).length, CDN_SEL);
  await pin("A");
  await page.waitForFunction((q) => document.querySelector(q), CDN_SEL);
  await page.clock.fastForward(2000);
  await pin("C");                       // чекає на той самий запит E1
  await page.clock.fastForward(6500);   // t=8.5: A вичерпав 8 с і скинув E1
  await waitSaved(page, "A");
  assert.equal((await cm(page, "A")).meta.shotMiss, "no-lib");
  await pin("B");                     // новий запит E2
  await page.waitForFunction((q) => document.querySelector(q), CDN_SEL);   // скрипт E2 уже в <head>
  await page.clock.fastForward(2000);   // t=10.5: C вичерпав свої 8 с
  await waitSaved(page, "C");
  assert.equal((await cm(page, "C")).meta.shotMiss, "no-lib");
  assert.equal(await nScripts(), 1, "<script> запиту B прибрано чужим очікувачем");
  // Chrome зливає другий запит тієї ж адреси з першим, що висить, — тож віддаємо єдиний утриманий: його чекають і E2
  await held[0].fulfill({ contentType: "application/javascript", body: SPY_SRC });
  await waitSaved(page, "B");
  const b = await cm(page, "B");
  assert.ok(b.meta.shot, "B мав отримати знімок");
  assert.equal(b.meta.shotMiss, undefined);
  await page.close();
});

test("4. html2canvas кидає: shotMiss render", async () => {
  const page = await boot({ h2c: "throw" });
  await addComment(page, "#lone", "кидає", corner);
  assert.equal(await page.evaluate(() => window.__calls.length), 1);
  const c = await cm(page, "кидає");
  assert.equal(c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, "render");
  await page.close();
});

test("5. html2canvas висить: після 8 с (page.clock) shotMiss timeout", async () => {
  const page = await boot({ h2c: "hang", clock: true });
  await page.click("#lone", { position: corner });
  await typeAndSave(page, "висить");
  await page.waitForFunction(() => window.__calls.length === 1);
  assert.equal(await page.evaluate(() => window.__mem.some((c) => c.text === "висить")), false, "до 8 с запису нема");
  await page.clock.fastForward(8500);
  await waitSaved(page, "висить");
  const c = await cm(page, "висить");
  assert.equal(c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, "timeout");
  await page.close();
});

test("5б. окремі бюджети: бібліотека вантажиться 5 с, рендер ще 5 с — разом понад 8 с, а знімок є", async () => {
  const page = await boot({ h2c: "none", clock: true });
  let held = null;
  await page.route(CDN, (r) => { held = r; });
  const SLOW = `window.__calls = window.__calls || [];
    window.html2canvas = (el, opts) => { window.__calls.push({ el, opts }); return new Promise((res) => setTimeout(() => { const c = document.createElement("canvas"); c.width = 20; c.height = 10; res(c); }, 5000)); };`;
  await page.click("#lone", { position: corner });
  await typeAndSave(page, "два бюджети");
  await page.waitForFunction((q) => document.querySelector(q), CDN_SEL);
  while (!held) await new Promise((r) => setTimeout(r, 20));
  await page.clock.fastForward(5000);
  await held.fulfill({ contentType: "application/javascript", body: SLOW });
  await page.waitForFunction(() => window.__calls.length === 1);
  await page.clock.fastForward(5500);
  await waitSaved(page, "два бюджети");
  const c = await cm(page, "два бюджети");
  assert.ok(c.meta.shot, "знімок мав бути: бюджет рендеру не їсть завантаження бібліотеки");
  assert.equal(c.meta.shotMiss, undefined);
  await page.close();
});

test("6. uploadShot: null двічі → upload і рівно 2 виклики; перший null, другий URL → shotUrl без shotMiss; виняток двічі → upload", async () => {
  let page = await boot({ upload: "(id, shot) => { window.__uploads.push(id); return Promise.resolve(null); }" });
  await addComment(page, "#lone", "нуль двічі", corner);
  assert.equal(await page.evaluate(() => window.__uploads.length), 2);
  let c = await cm(page, "нуль двічі");
  assert.ok(c.meta.shot, "інлайн-знімок лишається");
  assert.equal(c.meta.shotUrl, undefined);
  assert.equal(c.meta.shotMiss, "upload");
  await page.close();

  page = await boot({ upload: "(id, shot) => { window.__uploads.push(id); return Promise.resolve(window.__uploads.length === 1 ? null : 'https://x.test/s.jpg'); }" });
  await addComment(page, "#lone", "повтор вдався", corner);
  assert.equal(await page.evaluate(() => window.__uploads.length), 2);
  c = await cm(page, "повтор вдався");
  assert.equal(c.meta.shotUrl, "https://x.test/s.jpg");
  assert.equal(c.meta.shotMiss, undefined);
  await page.close();

  page = await boot({ upload: "(id) => { window.__uploads.push(id); throw new Error('net'); }" });
  await addComment(page, "#lone", "виняток", corner);
  assert.equal(await page.evaluate(() => window.__uploads.length), 2);
  assert.equal((await cm(page, "виняток")).meta.shotMiss, "upload");
  await page.close();
});

test("6б. uploadShot висить: після 8 с — upload одразу, рівно 1 виклик (без повтору після таймауту)", async () => {
  const page = await boot({ clock: true, upload: "(id) => { window.__uploads.push(id); return new Promise(() => {}); }" });
  await page.click("#lone", { position: corner });
  await typeAndSave(page, "заливка висить");
  await page.waitForFunction(() => window.__uploads.length === 1);
  await page.clock.fastForward(8500);
  await page.clock.fastForward(1000);   // повтор (якби був) стартував би через 500 мс після таймауту
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), "заливка висить", { timeout: 3000 });
  assert.equal(await page.evaluate(() => window.__uploads.length), 1);
  const c = await cm(page, "заливка висить");
  assert.ok(c.meta.shot);
  assert.equal(c.meta.shotMiss, "upload");
  await page.close();
});

test("7. ціль зникла і двійника нема: shotMiss detached", async () => {
  const page = await boot();
  await page.click("#lone", { position: corner });
  await page.evaluate(() => document.querySelector("#lone").remove());
  await typeAndSave(page, "зникла");
  await waitSaved(page, "зникла");
  assert.equal(await page.evaluate(() => window.__calls.length), 0);
  const c = await cm(page, "зникла");
  assert.equal(c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, "detached");
  await page.close();
});

test("8. полотно: anchors.shot → null → render; кидає → render; не функція → без знімка й без коду; заливка не вдалась → upload", async () => {
  const T = `{ fp: { tag: "div", text: "x" }, rect: { left: 100, top: 100, width: 50, height: 50 }, meta: { url: "u", route: "/", version: "1" } }`;
  const canvasPin = async (page, text) => {
    await page.evaluate(`window.CommentLayer._openCanvasCompose(${T})`);
    await typeAndSave(page, text);
    await waitSaved(page, text);
    return cm(page, text);
  };
  const A = (shot) => `{ place: () => [], subscribe() {}, active: () => true, armed() {}, ${shot} }`;
  let page = await boot({ anchors: A("shot: () => null") });
  let c = await canvasPin(page, "null");
  assert.equal(c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, "render");
  await page.close();

  page = await boot({ anchors: A("shot: () => { throw new Error('x'); }") });
  c = await canvasPin(page, "кидає");
  assert.equal(c.meta.shotMiss, "render");
  await page.close();

  page = await boot({ anchors: A("") });
  c = await canvasPin(page, "без shot");
  assert.equal(c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, undefined);
  await page.close();

  page = await boot({ anchors: A("shot: () => 'data:image/jpeg;base64,AA=='"), upload: "(id) => { window.__uploads.push(id); return null; }" });
  c = await canvasPin(page, "заливка");
  assert.equal(c.meta.shot, "data:image/jpeg;base64,AA==");
  assert.equal(c.meta.shotMiss, "upload");
  assert.equal(await page.evaluate(() => window.__uploads.length), 2);
  await page.close();
});

test("8б. полотно: anchors.shot висить — після 8 с (page.clock) shotMiss timeout", async () => {
  const page = await boot({ clock: true, anchors: `{ place: () => [], subscribe() {}, active: () => true, armed() {}, shot: () => new Promise(() => {}) }` });
  await page.evaluate(`window.CommentLayer._openCanvasCompose({ fp: { tag: "div", text: "x" }, rect: { left: 100, top: 100, width: 50, height: 50 }, meta: { url: "u", route: "/", version: "1" } })`);
  await typeAndSave(page, "полотно висить");
  // збагачення (`_enrich`) відсутнє, тож таймер знімка вже стоїть; зсуваємо годинник повз 8 с
  await page.clock.fastForward(8500);
  await waitSaved(page, "полотно висить");
  const c = await cm(page, "полотно висить");
  assert.equal(c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, "timeout");
  await page.close();
});

test("9. shotLib: запитано саме цю адресу, CDN — ні; javascript:/data: ігноруються → CDN", async () => {
  // відносна адреса потребує справжньої бази — сторінка віддається з route на .test-хості
  const run = async (shotLib, withLocal) => {
    const p = await browser.newPage({ viewport: { width: 1200, height: 800 } });
    const seen = []; let cdnHits = 0;
    if (withLocal) {
      await p.route("http://heavy.test/**", (r) => {
        const u = new URL(r.request().url());
        seen.push(u.pathname);
        if (u.pathname === "/lib/h2c.js") return r.fulfill({ contentType: "application/javascript", body: SPY_SRC });
        if (u.pathname === "/") return r.fulfill({ contentType: "text/html", body: PAGE });
        return r.abort();
      });
    }
    await p.route(CDN, (r) => { cdnHits++; return r.fulfill({ contentType: "application/javascript", body: SPY_SRC }); });
    if (withLocal) await p.goto("http://heavy.test/"); else await p.setContent(PAGE);
    await p.addScriptTag({ content: BUNDLE });
    await p.evaluate(`(() => { const mem = []; window.__mem = mem;
      window.CommentLayer.init({ projectId: "t", storage: { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } }, version: "1", user: { name: "Т" },
        shotLib: ${JSON.stringify(shotLib)}, host: { onReady() {}, onChange() {}, onSelect() {}, onMode() {} } });
      window.CommentLayer.setCommentMode(true); })()`);
    await addComment(p, "#lone", "lib", corner);
    const c = await cm(p, "lib");
    await p.close();
    return { seen, cdnHits, shot: !!c.meta.shot, miss: c.meta.shotMiss };
  };
  const own = await run("/lib/h2c.js", true);
  assert.deepEqual(own.seen.filter((x) => x.startsWith("/lib")), ["/lib/h2c.js"]);
  assert.equal(own.cdnHits, 0, "CDN не мав запитуватись");
  assert.equal(own.shot, true);
  assert.equal(own.miss, undefined);
  for (const bad of ["javascript:alert(1)", "data:text/javascript,window.html2canvas=1"]) {
    const r = await run(bad, false);
    assert.equal(r.cdnHits, 1, `${bad} мав бути проігнорований — запит на CDN`);
    assert.equal(r.shot, true);
  }
});

test("10. shotMiss уже в ПЕРШОМУ save (до першого persist)", async () => {
  const page = await boot();
  await addComment(page, "#huge", "перший запис", corner);
  const first = await page.evaluate(() => {
    const s = window.__saves.find((l) => l.some((c) => c.text === "перший запис"));
    return s.find((c) => c.text === "перший запис").meta.shotMiss;
  });
  assert.equal(first, "too-big");
  await page.close();
});
