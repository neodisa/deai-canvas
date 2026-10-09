/**
 * ДЕ стоїть пін і скільки таких самих елементів (fb-30092026-e53eaa, п.1–2).
 *
 * Скріншот піна — вирізка самого елемента (111×32): коли той самий компонент
 * повторюється, не видно, в якому він віджеті, і дизайнер з Claude говорили про
 * різні піни. `bin/pin-where.mjs` відкриває сторінку піна в браузері (статичний
 * HTML не годиться: у SPA DOM малює JS), знаходить елемент тим самим `findMatch`,
 * що й коментатор, і каже: віджет + інші екземпляри.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { chromium } from "playwright";

import { pinWhere } from "../../bin/pin-where.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 15600;
const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<section><h3>Ризики компанії</h3><button class="madd">Додати умову</button></section>
<section><h3>Санкції</h3><button class="madd">Додати умову</button></section>
<compliance-court-widget><div><span id="solo">Судові справи</span></div></compliance-court-widget>
</body></html>`;

async function fp(url, sel) {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(`${url}/commented?it=it1&page=kartka&bare=1`);
    const { ANCHOR } = await import("../../bin/pin-where.mjs");
    await page.addScriptTag({ content: ANCHOR });
    return await page.evaluate((s) => window.CommentLayerAnchor.fingerprint(
      document.querySelector(s), document.body), sel);
  } finally { await browser.close(); }
}

test("віджет піна й інші екземпляри того самого елемента", async (t) => {
  const { dir } = taskFixture({ html: PAGE, pages: ["kartka"] });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());

  const first = await fp(url, "section:first-of-type button");
  const solo = await fp(url, "#solo");
  const pins = [
    { id: "p-first", fp: first, it: "it1", page: "kartka" },
    { id: "p-solo", fp: solo, it: "it1", page: "kartka" },
    { id: "p-gone", fp: { tag: "marquee", text: "зник", textHash: "x", structHash: "x", path: ["marquee[0]"] },
      it: "it1", page: "kartka" },
    /* Тег є на сторінці, а все інше чуже: `findMatch` дасть кандидата з низьким
       балом — без порогу збігу його б назвали «знайденим» і вигадали віджет. */
    { id: "p-weak", fp: { tag: "button", text: "зовсім інша кнопка оплати", textHash: "x", structHash: "y",
      styleHash: "z", path: ["div[7]", "nav[2]", "button[5]"] }, it: "it1", page: "kartka" },
  ];
  const got = await pinWhere({ url, pins, launch: () => chromium.launch() });

  assert.equal(got["p-first"].found, true);
  assert.equal(got["p-first"].widget, "Ризики компанії");
  assert.deepEqual(got["p-first"].twins, ["Санкції"], "другий такий самий елемент не знайдено");
  assert.equal(got["p-solo"].widget, "compliance-court-widget");
  assert.deepEqual(got["p-solo"].twins, []);
  assert.equal(got["p-gone"].found, false);
  assert.equal(got["p-weak"].found, false, "слабкий збіг названо знайденим");
});
