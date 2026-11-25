/**
 * Центр сегмента «Макет / Огляд» (0.40): однаковий в обох режимах і не залежить від кнопок ← → ⟳ зліва й від набору контролів
 * справа. Вимір, а не здогад: тест написано ДО правки й упав на ній (дельта = половина різниці ширин решти зони 2).
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 54000;
const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

const metrics = (page) => page.evaluate(() => {
  const r = (s) => document.querySelector(s)?.getBoundingClientRect();
  const bar = r("#bar .bar"), seg = r('#bar [data-seg="mode"]'), z2 = r("#bar .zone-2");
  const kids = [...document.querySelectorAll("#bar .zone-2 > *")].map((e) => Math.round(e.getBoundingClientRect().width));
  return {
    cx: seg.left + seg.width / 2, barCx: bar.left + bar.width / 2,
    z2w: Math.round(z2.width), kids,
    overflow: document.querySelector("#bar .bar").scrollWidth - document.querySelector("#bar .bar").clientWidth,
  };
});

for (const width of [1440, 1280]) {
  test(`центр сегмента «Макет/Огляд» однаковий в обох режимах і збігається з центром смуги (${width})`, async (t) => {
    const { dir } = taskFixture({ html });
    const { child, url } = await startServer(dir, { portBase: PORT_BASE + (width === 1440 ? 0 : 100) });
    t.after(() => child.kill());
    const page = await browser.newPage({ viewport: { width, height: 800 } });
    t.after(() => page.close());
    await page.goto(`${url}/app/`);
    await page.waitForSelector('#bar [data-seg="mode"]');
    const layout = await metrics(page);
    await page.click('#bar [data-act="mode"][data-val="overview"]');
    await page.waitForSelector('#bar [data-seg="view"]');
    const overview = await metrics(page);
    assert.ok(Math.abs(layout.cx - overview.cx) < 1, `сегмент зсунувся на ${Math.abs(layout.cx - overview.cx).toFixed(1)}px між режимами`);
    assert.ok(Math.abs(layout.cx - layout.barCx) < 1.5, `не в центрі смуги: ${layout.cx} проти ${layout.barCx}`);
    assert.ok(layout.overflow <= 0 && overview.overflow <= 0, "смуга не переповнюється");
  });
}
/* Два стани «Огляду»: із графом (`flow.json`) і без нього — там «Флоу» вимкнений і несе ВИДИМУ причину (`.dd-why`), тож сегмент ширший. */
for (const [withFlow, width] of [true, false].flatMap((f) => [1024, 1280, 1440].map((w) => [f, w]))) {
  test(`решта контролів зони 2 не налазить на зону 3 (${width}, ${withFlow ? "є flow.json" : "без flow.json"})`, async (t) => {
    const { dir } = taskFixture({ html });
    if (withFlow) {
      writeFileSync(path.join(dir, "iterations", "it1", "flow.json"), JSON.stringify({ flows: [{ id: "f", title: "P", nodes: [{ id: "n1", page: "holovna" }], edges: [] }] }));
    }
    const { child, url } = await startServer(dir, { portBase: PORT_BASE + 200 + (width % 100) * 3 + (withFlow ? 0 : 1) });
    t.after(() => child.kill());
    const page = await browser.newPage({ viewport: { width, height: 800 } });
    t.after(() => page.close());
    await page.goto(`${url}/app/`);
    await page.waitForSelector('#bar [data-seg="mode"]');
    for (const mode of ["layout", "overview"]) {
      await page.click(`#bar [data-act="mode"][data-val="${mode}"]`);
      await page.waitForFunction((m) => document.querySelector(`#bar [data-act="mode"][data-val="${m}"]`)?.getAttribute("aria-pressed") === "true", mode);
      const g = await page.evaluate(() => {
        const x = document.querySelector("#bar .zone-2x")?.getBoundingClientRect();
        const z3 = [...document.querySelectorAll("#bar .zone-3 > *")].map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0);
        return { right: x ? x.right : 0, z3left: z3.length ? Math.min(...z3.map((r) => r.left)) : 1e9,
          bar: document.querySelector("#bar .bar").getBoundingClientRect().right };
      });
      assert.ok(g.right <= g.z3left + 0.5, `${mode}@${width}: зона 2x (${g.right}) налазить на зону 3 (${g.z3left})`);
      assert.ok(g.right <= g.bar, `${mode}@${width}: зона 2x вилізла за смугу`);
    }
  });
}

/* Найширші стани зони 3 (смуга в «Макеті» й «Огляді» перемальовується моделлю в живій оболонці — як це робить `app.js`): «не опубліковано»
   (найдовший підпис), опубліковано зі застарілою публікацією, GitLab відстає/попереду/вимкнений, нетипові репозиторії (`GitHub`/`Git`), обидві
   мови, з графом і без. Пігулка оновлення живе у смузі вкладок (`#tabs`), не в зоні 3. */
test("решта контролів зони 2 не налазить на зону 3 у найширших станах смуги (1024…1440, обидві мови, обидва режими)", async (t) => {
  const { dir } = taskFixture({ html });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 400 });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: { width: 1440, height: 800 } });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  await page.waitForSelector('#bar [data-seg="mode"]');
  const bad = [];
  let checked = 0;
  for (const width of [1024, 1100, 1180, 1240, 1280, 1301, 1360, 1440, 1441, 1500, 1560, 1600, 1601, 1700, 1800, 1801, 1920]) {
    await page.setViewportSize({ width, height: 800 });
    const rows = await page.evaluate(async () => {
      const { barModel } = await import("/app/bar-model.js");
      const { barHTML } = await import("/app/shell-bar.js");
      const { setLang } = await import("/app/i18n.js");
      const LIGA = { id: "liga", name: "ЛІГА", color: "space-1", capabilities: { publish: "vercel-publish", tokens: null }, compat: { publish: "design-canvas" } };
      const base = { mode: "layout", view: "grid", vp: "desktop", vpw: "", taskId: "LIGA-7003", iterLabel: "Іт.3", iterNote: "Правки",
        hasIteration: true, iterPub: true, iterOnGl: false, flowRaw: true, pagesError: "", flowError: "", gl: "sync", published: true,
        pubStale: false, pagePub: true, right: null, tasksErr: false, space: LIGA };
      const states = {
        fresh: { published: false, iterPub: false }, published: {}, stale: { pubStale: true }, behind: { gl: "behind", iterOnGl: true },
        ahead: { gl: "ahead" }, off: { gl: "off" }, "behind+stale": { gl: "behind", pubStale: true },
        github: { glLabel: "GitHub", published: false, iterPub: false }, git: { glLabel: "Git", published: false, iterPub: false },
      };
      const bar = document.getElementById("bar");
      const out = [];
      for (const lang of ["uk", "en"]) {
        setLang(lang);
        for (const [name, o] of Object.entries(states)) for (const mode of ["layout", "overview"]) for (const flow of [true, false]) {
          const st = { ...base, ...o, mode, flowRaw: flow ? true : null };
          bar.innerHTML = barHTML(barModel(st), st);
          const x = document.querySelector("#bar .zone-2x").getBoundingClientRect();
          const z3 = [...document.querySelectorAll("#bar .zone-3 > *")].map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0);
          out.push({ lang, name, mode, flow, right: x.right, z3left: Math.min(...z3.map((r) => r.left)), bar: document.querySelector("#bar .bar").getBoundingClientRect().right });
        }
      }
      setLang("uk");
      return out;
    });
    for (const r of rows) {
      checked += 1;
      if (r.right > r.z3left + 0.5 || r.right > r.bar) bad.push(`${width} ${r.lang}/${r.name}/${r.mode}/flow=${r.flow}: ${r.right.toFixed(1)} проти ${r.z3left.toFixed(1)}`);
    }
  }
  assert.ok(checked >= 17 * 2 * 9 * 2 * 2, `перевірено лише ${checked} комбінацій`);
  assert.deepEqual(bad, [], "зона 2x налазить на зону 3");
});
