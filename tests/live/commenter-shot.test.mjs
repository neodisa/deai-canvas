/**
 * Область знімка коментатора (0.30.1): html2canvas отримує `ignoreElements`, що лишає лише предків цілі,
 * її піддерево, <head>/стилі та елементи, на які посилається піддерево (<use>, url(#id)); завеликий
 * таргет знімка не отримує. html2canvas підмінено шпигуном — мережа не потрібна.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const BUNDLE = readFileSync(path.join(ROOT, "app", "vendor", "comment-layer.min.js"), "utf8");
const PAGE = `<!doctype html><html><head><meta charset="utf-8"><title>t</title><link rel="stylesheet" href="data:text/css,"></head>
<body style="margin:40px">
<svg id="sprite" width="0" height="0"><defs><linearGradient id="g"><stop offset="0" stop-color="#000"/></linearGradient></defs>
<symbol id="ic"><path d="M0 0h4v4z"/></symbol><symbol id="other"><path d="M0 0h2v2z"/></symbol></svg>
<style id="bodystyle">p{margin:0}</style>
<main id="m"><section id="s1"><div id="d1"><p id="p">Абзац для коментаря
<svg id="u" width="8" height="8"><use href="#ic"/></svg>
<a id="skip" href="#far">x</a><svg id="f" width="8" height="8"><rect id="r" width="8" height="8" fill="url(#g)"/></svg></p></div></section>
<section id="s2"><svg id="o" width="8" height="8"><circle r="3"/></svg><p id="q">Інша секція</p></section></main>
<section id="far"><div id="farin"><p>далеко</p></div></section><div id="big"></div></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot() {
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });
  await page.setContent(PAGE);
  await page.addScriptTag({ content: BUNDLE });
  await page.evaluate(() => {
    window.__calls = [];
    window.html2canvas = (el, opts) => {
      window.__calls.push({ el, opts });
      const c = document.createElement("canvas"); c.width = 20; c.height = 10; return Promise.resolve(c);
    };
    const mem = [];
    window.__mem = mem;
    const store = { load: () => mem.slice(), save: (l) => { mem.length = 0; mem.push(...l); } };
    window.CommentLayer.init({ projectId: "t", storage: store, version: "1", user: { name: "Тест" },
      host: { onReady() {}, onChange() {}, onSelect() {}, onMode() {} } });
    window.CommentLayer.setCommentMode(true);
  });
  return page;
}
async function addComment(page, sel, text, position) {
  await page.click(sel, position ? { position } : undefined);
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea"));
  await page.evaluate((t) => {
    const ta = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose textarea");
    ta.value = t; ta.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
  await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".compose .save").click());
  await page.waitForFunction((t) => window.__mem.some((c) => c.text === t), text);
}

test("ignoreElements лишає предків, піддерево, head/стилі та посилання з піддерева", async () => {
  const page = await boot();
  await addComment(page, "#p", "знімок");
  const r = await page.evaluate(() => {
    const call = window.__calls[0];
    if (!call) return null;
    const ig = call.opts.ignoreElements;
    const q = (s) => document.querySelector(s);
    const rect = call.el.getBoundingClientRect();
    const clone = document.createElement("p");
    call.opts.onclone(document, clone);
    const out = {
      rect: [rect.width, rect.height],
      pin: ["width", "height", "box-sizing", "flex", "max-width", "min-width", "max-height"].map((n) => [clone.style.getPropertyValue(n), clone.style.getPropertyPriority(n)]),
      hasFn: typeof ig === "function",
      target: call.el.id,
      outsideSection: ig(q("#s2")), outsideChild: ig(q("#q")), outsideSvg: ig(q("#o")), big: ig(q("#big")),
      anc: ["main", "#s1", "#d1", "body", "html"].map((s) => ig(q(s))),
      desc: ["#u", "#f", "#r", "#u use"].map((s) => ig(q(s))),
      bodyStyle: ig(q("#bodystyle")),
      head: [...document.head.children].map((n) => ig(n)),
      far: ig(q("#far")), farin: ig(q("#farin")),
      ic: ig(q("#ic")), sprite: ig(q("#sprite")), other: ig(q("#other")), g: ig(q("#g")),
    };
    return out;
  });
  assert.ok(r, "html2canvas має бути викликаний");
  assert.equal(r.hasFn, true);
  assert.equal(r.pin[0][0], `${r.rect[0]}px`);
  assert.equal(r.pin[1][0], `${r.rect[1]}px`);
  assert.deepEqual(r.pin.slice(2).map((x) => x[0]), ["border-box", "0 0 auto", "none", "0px", "none"]);
  assert.ok(r.pin.every((x) => x[1] === "important"));
  assert.equal(r.target, "p");
  assert.equal(r.outsideSection, true);
  assert.equal(r.outsideChild, true);
  assert.equal(r.outsideSvg, true);
  assert.equal(r.big, true);
  assert.deepEqual(r.anc, [false, false, false, false, false]);
  assert.deepEqual(r.desc, [false, false, false, false]);
  assert.equal(r.bodyStyle, false);
  assert.ok(r.head.length > 0 && r.head.every((v) => v === false));
  assert.equal(r.far, true, "<a href=#far> не робить секцію якорем");
  assert.equal(r.farin, true);
  assert.equal(r.ic, false);
  assert.equal(r.sprite, false);
  assert.equal(r.other, true, "непов'язаний symbol відсікається");
  assert.equal(r.g, false);
  await page.close();
});

test("ціль із понад 1500 нащадків: html2canvas не викликається, коментар без meta.shot, але з meta.shotMiss too-big", async () => {
  const page = await boot();
  await page.evaluate(() => {
    const big = document.querySelector("#big");
    big.style.padding = "30px";
    big.innerHTML = "<i>x</i>".repeat(1600);
  });
  await addComment(page, "#big", "без знімка", { x: 5, y: 5 });
  assert.equal(await page.evaluate(() => window.__calls.length), 0, "html2canvas не мав викликатись");
  const c = await page.evaluate(() => window.__mem.find((x) => x.text === "без знімка"));
  assert.equal(c.meta && c.meta.shot, undefined);
  assert.equal(c.meta.shotMiss, "too-big");
  await page.close();
});

test("ціль із понад 300 SVG-вузлами (але <1500 елементів): знімок є, нащадки порожнього svg відсікаються, сам svg лишається", async () => {
  const page = await boot();
  await page.evaluate(() => {
    const big = document.querySelector("#big");
    big.style.padding = "30px";
    big.innerHTML = '<svg id="bs" width="10" height="10">' + "<path d=\"M0 0h1v1z\"/>".repeat(400) + "</svg>";
  });
  await addComment(page, "#big", "svg-важкий", { x: 5, y: 5 });
  assert.equal(await page.evaluate(() => window.__calls.length), 1, "html2canvas мав викликатись (обрізка замість відмови)");
  const r = await page.evaluate(() => {
    const ig = window.__calls[0].opts.ignoreElements;
    return { svg: ig(document.querySelector("#bs")), path: ig(document.querySelector("#bs path")),
      wrap: ig(document.querySelector("#big")) };
  });
  assert.deepEqual(r, { svg: false, path: true, wrap: false });
  const c = await page.evaluate(() => window.__mem.find((x) => x.text === "svg-важкий"));
  assert.ok(c.meta.shot, "знімок мав бути");
  assert.equal(c.meta.shotMiss, undefined);
  await page.close();
});

test("посилання з живого вузла в порожній корінь рятує symbol, його path і градієнт, на який вказує path (транзитивно)", async () => {
  const page = await boot();
  await page.evaluate(() => {
    const big = document.querySelector("#big");
    big.style.padding = "30px";
    // b1 — перший, понад бюджет → порожній; symbol і path (fill=url(#gr2)) ідуть РАНІШЕ за градієнт; живий b2 посилається на symbol
    big.innerHTML = '<svg id="b1" width="10" height="10"><symbol id="sym2"><path id="sp2" d="M0 0h1v1z" fill="url(#gr2)"/></symbol>'
      + '<linearGradient id="gr2"><stop id="st2" offset="0"/></linearGradient><path id="junk" d="M0 0h1v1z"/>' + "<path d=\"M0 0h1v1z\"/>".repeat(400) + '</svg>'
      + '<svg id="b2" width="10" height="10" mask="url(#sym2)"><circle r="1"/></svg>';
  });
  await addComment(page, "#big", "транзитивно", { x: 5, y: 5 });
  assert.equal(await page.evaluate(() => window.__calls.length), 1);
  const r = await page.evaluate(() => {
    const ig = window.__calls[0].opts.ignoreElements, q = (s) => document.querySelector(s);
    return { sym: ig(q("#sym2")), path: ig(q("#sp2")), grad: ig(q("#gr2")), stop: ig(q("#st2")), junk: ig(q("#junk")), b1: ig(q("#b1")), b2: ig(q("#b2")), b2c: ig(q("#b2 circle")) };
  });
  assert.deepEqual(r, { sym: false, path: false, grad: false, stop: false, junk: true, b1: false, b2: false, b2c: true });
  await page.close();
});
