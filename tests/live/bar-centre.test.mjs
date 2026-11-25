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
    console.log(JSON.stringify({ width, layout, overview }));   // вимір для звіту виконавця
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
