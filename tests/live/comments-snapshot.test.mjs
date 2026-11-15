/**
 * Живий тест знімка каналу команди (0.27.0, адаптер `supabase-comments`): перемикання сторінок робочого місця ЛІГИ
 * перезавантажує рамку, а кожне перезавантаження раніше робило повний `select *` каналу (до ~700 КБ). Тепер останнє вдале
 * читання лежить у `sessionStorage` вкладки на 2 хв, і решта перезавантажень його не повторює.
 *
 * Мапа «перевірка → запобіжник → мутація»:
 *   A (одне читання на ≥3 перезавантаження рамки) — засівання кешу знімком у `create()` адаптера.
 *                         МУТАЦІЯ: вимкнути засівання — GET по одному на кожне перезавантаження (≥3).
 *
 * ⛔ Supabase — вигаданий хост фікстури (`supabase: true`), перехоплений у браузері (`hermeticLiga`): жодної справжньої мережі.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { hermeticLiga } from "./_liga-supabase.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 27100;
const VIEW = { width: 1400, height: 900 };
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>`
  + `<body style="height:900px;background:repeating-linear-gradient(37deg,#e11 0 10px,#18a 10px 20px,#2c3 20px 30px,#fd0 30px 40px)">`
  + `<h1>${id}</h1></body></html>`;

test("A: перемикання між трьома сторінками ЛІГИ — РІВНО одне читання командного каналу (GET /rest/v1/comments)", async (t) => {
  const { dir } = taskFixture({ html: PAGE, pages: ["holovna", "poshuk", "vybir"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE, supabase: true });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  const net = await hermeticLiga(page);
  await page.goto(`${url}/app/`);
  await page.waitForSelector('.panel [data-page="holovna"]', { timeout: 15000 });

  /* Рамка, що ВЖЕ показує сторінку `id` з піднятим шаром коментарів (новий документ рамки, а не старий). */
  const ready = (id) => page.waitForFunction((want) => {
    const w = (document.getElementById("frame") || {}).contentWindow;
    return !!(w && w.document.readyState === "complete" && w.location.href.includes(want)
      && w.CommentLayer && w.CommentLayer._inited);
  }, id, { timeout: 15000 });
  const reads = () => net.supabase.filter((r) => r === "GET /rest/v1/comments").length;

  await ready("holovna");
  const frameDocs = new Set();
  for (const id of ["poshuk", "vybir", "holovna"]) {
    await page.locator(`.panel [data-page="${id}"]`).click();
    await ready(id);
    frameDocs.add(await page.evaluate(() => {
      const w = document.getElementById("frame").contentWindow;
      return (w.__docMark = w.__docMark || Math.random());
    }));
    await page.waitForTimeout(400);                  // GET (якби був) вилітає при create(); дати йому дійти до збирача
  }
  assert.equal(frameDocs.size, 3, "рамка справді перезавантажувалась на кожен клік (інакше перевірка порожня)");
  assert.equal(reads(), 1, `очікували ОДНЕ читання на 4 завантаження рамки, а було ${reads()}:\n${net.supabase.join("\n")}`);
  const snap = await page.evaluate(() => Object.keys(sessionStorage).filter((k) => k.startsWith("deai-comments:v1:")));
  assert.equal(snap.length, 1, "знімок каналу лежить у sessionStorage оболонки");
  assert.deepEqual(net.outside, [], `запити за межі машини:\n${net.outside.join("\n")}`);
});
