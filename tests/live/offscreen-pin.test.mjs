/**
 * Пін на елементі, якого зараз немає на екрані (fb-06102026-c38f46).
 *
 * boss-interface, Іт.15: вітання гортається кроками через `@switch`, сторінка
 * відкривається на кроці 1, а піни стоять на кроках «Ваш партнер» і «Додаткові
 * компанії». Дизайнер клікав по картці — і нічого: `_focusElement` мовчки
 * виходив, коли елемента немає. Стан SPA ми повернути не можемо (він у
 * застосунку, не в URL), тому контракт такий (рішення власника 06.10.2026):
 *   A картка каже «Елемента зараз немає на екрані…» і ДЕ він був (`meta.ctx`);
 *   B клік по стрілці відкриває знімок елемента, а не мовчить;
 *   C новий пін при створенні записує контекст: заголовок над елементом і
 *     активний крок (`aria-current`/`aria-selected`).
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 15400;
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<nav><button aria-current="step">Крок 1</button><button>Крок 2</button></nav>
<h2>Вітаємо</h2>
<section><h3>Ваш партнер</h3><p id="target">Партнер ${id}: ТОВ «Приклад»</p></section>
<div hidden><h3>Схований заголовок</h3></div>
</body></html>`;
const SHOT = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='40' height='20'%3E%3Crect width='40' height='20' fill='%23c00'/%3E%3C/svg%3E";

function ghost(url, extra = {}) {
  return {
    id: "ghost-1", author: "Фікстура", text: "Правка до кроку 2", status: "open",
    fp: { tag: "button", stableId: null, text: "Додати компанію", textHash: "x", structHash: "x",
          styleHash: "x", path: ["button[9]"] },
    htmlSnapshot: null, bornV: 1, ts: "06.10.2026 12:00",
    meta: { url: `${url}/commented?it=it1&page=kartka&ch=local`, route: "/commented",
            version: "1/kartka", iteration: "1", viewport: { w: 1280, h: 900 }, seq: 1, shot: SHOT, ...extra },
  };
}

async function boot(t, off, comments) {
  const { dir } = taskFixture({ html: PAGE, pages: ["kartka"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  if (comments) {
    const r = await fetch(`${url}/api/local-comments`, { method: "POST",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comments: comments(url) }) });
    assert.ok(r.ok, `посів пінів: ${r.status}`);
  }
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`${url}/commented?it=it1&page=kartka&ch=local`);
  await page.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited);
  return { page, url };
}

const card = (page, sel) => page.evaluate((s) => {
  const host = document.querySelector("[data-comment-layer]");
  const el = host && host.shadowRoot.querySelector(`#cghost-1 ${s}`);
  return el ? el.textContent.replace(/\s+/g, " ").trim() : null;
}, sel);

test("A+B: картка каже «немає на екрані» з контекстом, стрілка відкриває знімок", async (t) => {
  const { page } = await boot(t, 0, (url) => [ghost(url, { ctx: { heading: "Додаткові компанії", active: ["Крок 2"] } })]);
  await page.evaluate(() => window.CommentLayer.open());
  const note = await card(page, ".offscreen");
  assert.ok(note, "у картці немає позначки «немає на екрані»");
  assert.match(note, /немає на екрані/);
  assert.match(note, /«Крок 2» · розділ «Додаткові компанії»/);
  await page.evaluate(() => document.querySelector("[data-comment-layer]").shadowRoot
    .querySelector("#cghost-1 .jump").click());
  const lightbox = await page.waitForFunction(() => {
    const lb = document.querySelector("[data-comment-layer]").shadowRoot.querySelector(".cllb img");
    return lb ? lb.getAttribute("src") : null;
  }, null, { timeout: 5000 }).then((h) => h.jsonValue(), () => null);
  assert.ok(lightbox && lightbox.startsWith("data:image/svg"), "клік по стрілці мовчить замість знімка");
});

test("A: пін, чий елемент є на екрані, позначки не має", async (t) => {
  const { page } = await boot(t, 100, null);
  const fp = await page.evaluate(() => window.CommentLayer._algo.fingerprint(
    document.getElementById("target"), document.body));
  await page.evaluate(async (f) => {
    const r = await fetch("/api/local-comments");
    const url = location.href;
    const pin = { id: "ghost-1", author: "Ф", text: "на місці", status: "open", fp: f, htmlSnapshot: null,
      bornV: 1, ts: "06.10.2026 12:00", meta: { url, route: "/commented", version: "1/kartka", iteration: "1", seq: 1 } };
    await fetch("/api/local-comments", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comments: [pin] }) });
    return r.ok;
  }, fp);
  await page.reload();
  await page.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited);
  await page.evaluate(() => window.CommentLayer.open());
  await page.waitForFunction(() => document.querySelector("[data-comment-layer]").shadowRoot.querySelector("#cghost-1"));
  assert.equal(await card(page, ".offscreen"), null, "позначка на піні, чий елемент видно");
});

test("C: контекст піна — найближчий видимий заголовок і активний крок", async (t) => {
  const { page } = await boot(t, 200, null);
  const ctx = await page.evaluate(() => window.CommentLayer._algo.captureContext(
    document.getElementById("target"), document.body));
  assert.deepEqual(ctx, { heading: "Ваш партнер", active: ["Крок 1"] });
});

test("C2: у контекст не потрапляють номери й вибрані рядки (PII, ревʼю 1.51)", async (t) => {
  /* `meta.ctx` проєктних пінів їде в Supabase. Довгі цифрові серії (ЄДРПОУ, ІПН,
     номери справ) і вибрані рядки таблиць/списків — чужі дані, не «де я». */
  const { page } = await boot(t, 300, null);
  const ctx = await page.evaluate(() => {
    document.body.insertAdjacentHTML("afterbegin",
      '<table><tr role="row" aria-selected="true"><td>Синтетичний Іван Петрович</td></tr></table>'
      + '<h2 id="pii">Компанія 41234567</h2><button aria-pressed="true">Дуже довга назва активної кнопки понад тридцять символів</button>');
    const target = document.getElementById("target");
    target.insertAdjacentHTML("beforebegin", "<h4>Справа № 9123456789</h4>");   // найближчий, але з номером
    return window.CommentLayer._algo.captureContext(target, document.body);
  });
  assert.deepEqual(ctx, { heading: "Ваш партнер", active: ["Крок 1"] });
});

test("C3: без заголовка, коли так сказано (проєктні піни, TD-36)", async (t) => {
  /* ПІБ у заголовку («Картка клієнта: …») надійно не розпізнати, а контекст
     проєктних пінів їде в Supabase — для них заголовок не пишемо зовсім. */
  const { page } = await boot(t, 400, null);
  const ctx = await page.evaluate(() => window.CommentLayer._algo.captureContext(
    document.getElementById("target"), document.body, { heading: false }));
  assert.deepEqual(ctx, { heading: "", active: ["Крок 1"] });
});
