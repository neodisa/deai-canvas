/**
 * Живі перевірки «канвас помічає зміну ззовні» (батч 1.47):
 *   A чужий перезапис pages.json без тек → плашка з назвою теки; «Відновити» → тека на диску
 *   B файл сторінки змінився, нічого не в руках → рамка оновилась сама, прокрутка лишилась
 *   C те саме з відкритим інспектором → плашка, рамка НЕ перезавантажена; «Оновити» → оновлено
 */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, utimesSync, writeFileSync } from "node:fs";
import path from "node:path";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 15000;
const VIEW = { width: 1400, height: 900 };
const TALL = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="margin:0"><h1 id="t">${id}</h1><div style="height:3000px"></div></body></html>`;
const disk = (it1) => JSON.parse(readFileSync(path.join(it1, "pages.json"), "utf8")).pages;

async function until(fn, ok, ms = 10000) {
  const end = Date.now() + ms;
  let v;
  while (Date.now() < end) {
    v = await fn();
    if (ok(v)) return v;
    await new Promise((r) => setTimeout(r, 150));
  }
  return v;
}

async function boot(t, nodes, off) {
  const ids = (ns) => ns.flatMap((n) => [n.id, ...ids(n.children ?? [])]);
  const folders = new Set(nodes.flatMap(function walk(n) {
    return [...(n.kind === "folder" ? [n.id] : []), ...(n.children ?? []).flatMap(walk)];
  }));
  const { dir, it1 } = taskFixture({ html: TALL, pages: ids(nodes).filter((i) => !folders.has(i)) });
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({ pages: nodes }));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  return { page, it1 };
}

const frameText = (page) => page.evaluate(() =>
  document.getElementById("frame").contentDocument?.getElementById("t")?.textContent ?? null);

/** Переписати сторінку й гарантовано зсунути mtime (ФС може мати грубу роздільність). */
function rewrite(it1, id, text) {
  const f = path.join(it1, id, "index.html");
  writeFileSync(f, TALL(text));
  const s = Date.now() / 1000 + 5;
  utimesSync(f, s, s);
}

test("A: чужий перезапис дерева без тек → плашка й «Відновити» повертає теку на диск", async (t) => {
  const { page, it1 } = await boot(t, [
    { id: "w", name: "Віджет", kind: "folder", children: [{ id: "kartka", name: "Картка", kind: "page" }] },
    { id: "osoba", name: "Особа", kind: "page" }], 0);
  writeFileSync(path.join(it1, "pages.json"), JSON.stringify({ pages: [
    { id: "kartka", name: "kartka" }, { id: "osoba", name: "osoba" }] }));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const note = page.locator('.cv-notice[data-notice="tree-lost"]');
  await note.waitFor({ timeout: 8000 });
  assert.match(await note.textContent(), /Віджет/);
  await note.locator('button[data-act="restore"]').click();
  const pages = await until(() => disk(it1), (p) => p[0]?.id === "w");
  assert.equal(pages[0].id, "w", `тека не повернулась: ${JSON.stringify(pages)}`);
  await page.locator('.cv-notice[data-notice="tree-lost"]').waitFor({ state: "detached", timeout: 5000 });
});

test("B: файл сторінки змінився, нічого не в руках → рамка оновилась сама, прокрутка ціла", async (t) => {
  const { page, it1 } = await boot(t, [{ id: "kartka", name: "Картка", kind: "page" }], 100);
  await until(() => frameText(page), (v) => v === "kartka");
  await page.evaluate(() => document.getElementById("frame").contentWindow.scrollTo(0, 600));
  await new Promise((r) => setTimeout(r, 2500));          // база опитування встигла стати
  rewrite(it1, "kartka", "НОВЕ");
  assert.equal(await until(() => frameText(page), (v) => v === "НОВЕ", 12000), "НОВЕ");
  const y = await page.evaluate(() => document.getElementById("frame").contentWindow.scrollY);
  assert.ok(Math.abs(y - 600) < 2, `прокрутку скинуто: ${y}`);
});

test("C: відкритий інспектор → плашка замість перезавантаження; «Оновити» — оновлює", async (t) => {
  const { page, it1 } = await boot(t, [{ id: "kartka", name: "Картка", kind: "page" }], 200);
  await until(() => frameText(page), (v) => v === "kartka");
  // Інспектор вантажиться ПІСЛЯ сторінки — без чекання під навантаженням його ще немає.
  await page.waitForFunction(() => document.getElementById("frame").contentWindow.CanvasInspector, null, { timeout: 15000 });
  await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector.set(true));
  await new Promise((r) => setTimeout(r, 2500));
  rewrite(it1, "kartka", "НОВЕ");
  const note = page.locator('.cv-notice[data-notice="frame-changed"]');
  await note.waitFor({ timeout: 12000 });
  assert.equal(await frameText(page), "kartka", "рамку перезавантажено попри відкритий інспектор");
  await note.locator('button[data-act="reload"]').click();
  assert.equal(await until(() => frameText(page), (v) => v === "НОВЕ"), "НОВЕ");
});

test("E: власні дії над деревом не перезавантажують рамку (ревʼю 1.47, D1)", async (t) => {
  /* `write_pages` знімає `pages.json.bak` через `copy2` з mtime ПОПЕРЕДНЬОЇ
     версії: друга дія поспіль зсувала відбиток вмісту, і рамка мигала
     перезавантаженням (або вискакувала хибна плашка) без жодної зміни макета. */
  const { page } = await boot(t, [
    { id: "kartka", name: "Картка", kind: "page" }, { id: "osoba", name: "Особа", kind: "page" }], 300);
  await until(() => frameText(page), (v) => v === "kartka");
  await new Promise((r) => setTimeout(r, 2500));
  await page.evaluate(() => {
    window.__loads = 0;
    document.getElementById("frame").addEventListener("load", () => { window.__loads += 1; });
  });
  for (const name of ["Особа 2", "Особа 3"]) {
    const st = await page.evaluate(async (n) => (await fetch("/api/page-rename", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ it: "it1", page: "osoba", name: n }) })).status, name);
    assert.equal(st, 200);
    await new Promise((r) => setTimeout(r, 1200));
  }
  await new Promise((r) => setTimeout(r, 4500));        // > QUIET_MS + два такти опитування
  assert.equal(await page.evaluate(() => window.__loads), 0, "рамку перезавантажено без зміни макета");
  assert.equal(await page.locator(".cv-notice").count(), 0, "хибна плашка");
});
