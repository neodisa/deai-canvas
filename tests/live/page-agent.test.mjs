/**
 * Помічник ядра для модулів (М2, Task 3): посилання, опис вузлів, запити, знімок.
 * Без сервера канваса: Playwright `page.route("http://agent.test/**")` віддає `app/*` з диска й дві сторінки з памʼяті.
 * `host.html` імпортує помічника й працює над `iframe.contentDocument` — як у канвасі (інше вікно, те саме походження).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const HOST = `<!doctype html><meta charset="utf-8"><iframe id="f" src="/fixture.html" style="width:900px;height:600px;border:0"></iframe>
<script>document.getElementById("f").addEventListener("load", () => { window.READY = true; });</script>
<script type="module">
  import { createPageAgent } from "/app/page-agent.js";
  window.EV = [];
  window.mk = () => { window.A?.destroy(); window.A = createPageAgent({ doc: document.getElementById("f").contentDocument,
    pageInfo: () => ({ id: "p1", title: "Сторінка" }), onEvent: (n, d) => window.EV.push([n, d]) }); return true; };
</script>`;
const FIXTURE = `<!doctype html><html><head><meta charset="utf-8"><title>F</title><style>.lo{color:#fff;background:#9fd3b8}</style></head>
<body style="margin:0;font-family:sans-serif">
  <h1 id="h">Заголовок <span>в</span> тексті</h1>
  <button id="cta" class="lo cta" aria-label="Почати">Почати</button>
  <p id="p" style="color: green">Абзац</p>
  <div id="tall" style="height:2000px">довгий</div>
  <a id="far" href="#x">далеко</a>
  <script>window.PAGE_CLICKS = 0; document.addEventListener("click", () => window.PAGE_CLICKS++);</script>
  <template><b>t</b></template>
  <div data-canvas-inspector><i id="ours">наше</i></div>
</body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function open() {
  const page = await browser.newPage();
  await page.route("http://agent.test/**", async (route) => {
    const u = new URL(route.request().url());
    if (u.pathname.startsWith("/app/") && u.pathname.endsWith(".js") && !u.pathname.includes("..")) {
      return route.fulfill({ status: 200, contentType: "text/javascript", body: readFileSync(path.join(ROOT, u.pathname)) });
    }
    if (u.pathname === "/host.html") return route.fulfill({ status: 200, contentType: "text/html", body: HOST });
    if (u.pathname === "/fixture.html") return route.fulfill({ status: 200, contentType: "text/html", body: FIXTURE });
    return route.fulfill({ status: 404, body: "" });
  });
  await page.goto("http://agent.test/host.html");
  await page.waitForFunction(() => window.READY);
  await page.evaluate(() => window.mk());
  return page;
}
/** Виклик методу помічника; помилка → її `code`. */
const call = (page, method, args = []) => page.evaluate(async ([m, a]) => {
  try { return { v: await window.A[m](...a) }; } catch (e) { return { code: e.code, msg: String(e.message) }; }
}, [method, args]);

test("query: опис вузла, стабільний ref, координати документа", async () => {
  const page = await open();
  try {
    const r = await call(page, "query", ["button"]);
    assert.equal(r.v.length, 1);
    const n = r.v[0];
    assert.equal(n.tag, "button");
    assert.equal(n.id, "cta");
    assert.equal(n.cls, "lo cta");
    assert.equal(n.text, "Почати");
    assert.equal(n.visible, true);
    await page.evaluate(() => document.getElementById("f").contentWindow.scrollTo(0, 500));
    const r2 = await call(page, "query", ["button"]);
    assert.equal(r2.v[0].rect.y, n.rect.y, "rect у координатах документа, а не вікна");
    assert.equal(r2.v[0].ref, n.ref, "той самий елемент — той самий ref");
  } finally { await page.close(); }
});

test("query: наші оверлеї та script/template не потрапляють у результат", async () => {
  const page = await open();
  try {
    assert.deepEqual((await call(page, "query", ["i"])).v, []);
    assert.deepEqual((await call(page, "query", ["script, template, b"])).v, []);
  } finally { await page.close(); }
});

test("query: помилки вхідних даних і ліміт", async () => {
  const page = await open();
  try {
    assert.equal((await call(page, "query", ["["])).code, "bad-selector");
    assert.equal((await call(page, "query", ["div", { limit: 0 }])).code, "bad-args");
    assert.equal((await call(page, "query", ["div", { limit: -3 }])).code, "bad-args");
    const big = await call(page, "query", ["*", { limit: 100000 }]);
    assert.ok(Array.isArray(big.v) && big.v.length <= 500);
  } finally { await page.close(); }
});

test("get: обчислені стилі й атрибути; text — лише власний", async () => {
  const page = await open();
  try {
    const ref = (await call(page, "query", ["#cta"])).v[0].ref;
    const g = await call(page, "get", [ref, { styles: ["color"], attrs: true }]);
    assert.equal(g.v.styles.color, "rgb(255, 255, 255)");
    assert.equal(g.v.attrs["aria-label"], "Почати");
    const h = (await call(page, "query", ["h1"])).v[0];
    assert.equal(h.text, "Заголовок тексті");
    assert.equal((await call(page, "query", ["h1", { styles: ["color; x"] }])).code, "bad-args");
  } finally { await page.close(); }
});

test("snapshot: порядок документа, parent, фільтри, maxNodes", async () => {
  const page = await open();
  try {
    const s = (await call(page, "snapshot", [{ styles: ["color"] }])).v;
    assert.equal(s.nodes[0].tag, "body");
    assert.equal(s.nodes[0].parent, null);
    assert.equal(s.truncated, false);
    const seen = new Set([s.nodes[0].ref]);
    for (const n of s.nodes.slice(1)) {
      assert.ok(seen.has(n.parent), `parent ${n.parent} раніше в списку`);
      seen.add(n.ref);
    }
    for (const n of s.nodes) assert.ok(!["script", "style", "template", "noscript", "i"].includes(n.tag), n.tag);
    assert.ok(s.nodes.every((n) => n.styles && "color" in n.styles));
    const t = (await call(page, "snapshot", [{ maxNodes: 3 }])).v;
    assert.equal(t.truncated, true);
    assert.equal(t.nodes.length, 3);
  } finally { await page.close(); }
});

test("info: сторінка, вʼюпорт, прокрутка, розмір", async () => {
  const page = await open();
  try {
    const i = (await call(page, "info")).v;
    assert.deepEqual(i.page, { id: "p1", title: "Сторінка" });
    assert.deepEqual(i.viewport, { w: 900, h: 600 });
    assert.deepEqual(i.scroll, { x: 0, y: 0 });
    assert.ok(i.size.h > 2000 && i.size.w >= 900);
  } finally { await page.close(); }
});

test("stale-ref після перезавантаження рамки; no-page після destroy", async () => {
  const page = await open();
  try {
    const ref = (await call(page, "query", ["#cta"])).v[0].ref;
    await page.evaluate(() => { window.READY = false; document.getElementById("f").src = "/fixture.html?2"; });
    await page.waitForFunction(() => window.READY);
    await page.evaluate(() => window.mk());
    assert.equal((await call(page, "get", [ref])).code, "stale-ref");
    await page.evaluate(() => window.A.destroy());
    assert.equal((await call(page, "info")).code, "no-page");
    assert.equal((await call(page, "query", ["div"])).code, "no-page");
  } finally { await page.close(); }
});
