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
  <button id="cta" class="lo cta" aria-label="Почати" data-deai-x="1" data-keep="k">Почати</button>
  <p id="p" style="color: green; --big: ${"z".repeat(2000)}">Абзац</p>
  <p id="lt">${"я".repeat(400)}</p>
  <div id="hid" style="display:none">скрито</div>
  <div id="inv" style="visibility:hidden">невидиме</div>
  <div id="tall" style="height:2000px">довгий</div>
  <a id="far" href="#x">далеко</a>
  <script>window.PAGE_CLICKS = 0; document.addEventListener("click", () => window.PAGE_CLICKS++);</script>
  <template><b>t</b></template>
  <div data-canvas-inspector id="ov-insp"><i id="ours">наше</i></div>
  <div data-comment-layer id="ov-cl"><i id="ours2">наше</i></div>
  <div id="cl-down"><i id="ours3">наше</i></div>
  <div data-deai-marks id="ov-marks"><i id="ours4">наше</i></div>
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
  await ready(page);
  await page.evaluate(() => window.mk());
  return page;
}
/** Рамка завантажена І модуль уже визначив `window.mk` (класичний скрипт може спрацювати раніше за модульний). */
const ready = (page) => page.waitForFunction(() => window.READY && typeof window.mk === "function");
/** Виконати код у документі рамки (аргумент — один обʼєкт). */
const inFrame = (page, fn, arg) => page.evaluate(([src, a]) => {
  const d = document.getElementById("f").contentDocument;
  return new Function("d", "a", `return (${src})(d, a)`)(d, a);
}, [fn.toString(), arg]);
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
    const far = (await call(page, "query", ["#far"])).v[0];
    assert.ok(far.rect.y > 2000, "#far нижче першого екрана");
    await page.evaluate(() => document.getElementById("f").contentWindow.scrollTo(0, 500));
    const far2 = (await call(page, "query", ["#far"])).v[0];
    assert.equal(far2.rect.y, far.rect.y, "rect у координатах документа, а не вікна");
    assert.equal(far2.ref, far.ref, "той самий елемент — той самий ref");
    assert.match(n.ref, /^r[a-z0-9]+-\d+$/, "ref з епохою");
  } finally { await page.close(); }
});

test("query: наші оверлеї та script/template не потрапляють у результат", async () => {
  const page = await open();
  try {
    assert.deepEqual((await call(page, "query", ["i"])).v, []);
    assert.deepEqual((await call(page, "query", ["script, template, b"])).v, []);
    for (const sel of ["[data-canvas-inspector]", "[data-comment-layer]", "#cl-down", "[data-deai-marks]"])
      assert.deepEqual((await call(page, "query", [sel])).v, [], `${sel} — сам хост теж невидимий`);
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
    for (const n of s.nodes) assert.ok(!["script", "style", "template", "noscript"].includes(n.tag), n.tag);
    for (const n of s.nodes) assert.ok(!["ov-insp", "ov-cl", "cl-down", "ov-marks", "ours", "ours2", "ours3", "ours4"].includes(n.id), `оверлей ${n.id} у знімку`);
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
    await ready(page);
    await page.evaluate(() => window.mk());
    const fresh = (await call(page, "query", ["*"])).v;
    assert.ok(fresh.length > 5, "новий помічник виділив власні ref-и");
    assert.ok(!fresh.some((n) => n.ref === ref), "старе посилання не збігається з жодним новим");
    assert.equal((await call(page, "get", [ref])).code, "stale-ref");
    await page.evaluate(() => window.A.destroy());
    assert.equal((await call(page, "info")).code, "no-page");
    assert.equal((await call(page, "query", ["div"])).code, "no-page");
    assert.equal((await call(page, "get", [fresh[0].ref])).code, "no-page");
    assert.equal((await call(page, "snapshot")).code, "no-page");
  } finally { await page.close(); }
});

test("ref: різні помічники — різні епохи, навіть без перезавантаження", async () => {
  const page = await open();
  try {
    const a = (await call(page, "query", ["#cta"])).v[0].ref;
    await page.evaluate(() => window.mk());
    const b = (await call(page, "query", ["#cta"])).v[0].ref;
    assert.notEqual(a, b);
    assert.equal((await call(page, "get", [a])).code, "stale-ref");
  } finally { await page.close(); }
});

test("get: елемент, що став «нашим» чи опинився поза body, — stale-ref", async () => {
  const page = await open();
  try {
    const ref = async (sel) => (await call(page, "query", [sel])).v[0].ref;
    const p = await ref("#p"), h = await ref("#h"), cta = await ref("#cta"), lt = await ref("#lt");
    assert.equal((await call(page, "get", [p])).v.id, "p");
    await inFrame(page, (d) => d.getElementById("ov-insp").appendChild(d.getElementById("p")));
    assert.equal((await call(page, "get", [p])).code, "stale-ref", "переїхав у оверлей");
    await inFrame(page, (d) => d.getElementById("h").setAttribute("data-canvas-inspector", ""));
    assert.equal((await call(page, "get", [h])).code, "stale-ref", "сам став оверлеєм");
    await inFrame(page, (d) => d.head.appendChild(d.getElementById("cta")));
    assert.equal((await call(page, "get", [cta])).code, "stale-ref", "переїхав у head");
    await inFrame(page, (d) => d.getElementById("cl-down").appendChild(d.getElementById("lt")));
    assert.equal((await call(page, "get", [lt])).code, "stale-ref", "переїхав у #cl-down");
  } finally { await page.close(); }
});

test("query: ліміт 500 справді зрізає, limit 1 дає один", async () => {
  const page = await open();
  try {
    await inFrame(page, (d) => { for (let i = 0; i < 600; i++) { const e = d.createElement("i"); e.className = "many"; d.body.appendChild(e); } });
    assert.equal((await call(page, "query", [".many", { limit: 9999 }])).v.length, 500);
    assert.equal((await call(page, "query", [".many", { limit: 1 }])).v.length, 1);
    assert.equal((await call(page, "query", [".many"])).v.length, 100);
  } finally { await page.close(); }
});

test("query: межі селектора — довжина й кількість функціональних псевдокласів", async () => {
  const page = await open();
  try {
    assert.equal((await call(page, "query", ["a" + ",a".repeat(150)])).code, "bad-args", "301 символ");
    assert.equal((await call(page, "query", [":not(a):not(b):not(c):not(d):not(e)"])).code, "bad-args");
    assert.equal((await call(page, "query", [":NOT(a):Is(b):WHERE(c):Has(d):not(e)"])).code, "bad-args", "регістр не рятує");
    assert.equal((await call(page, "query", [":not(:is(a,b)) :where(c):has(d)"])).v.length, 0, "рівно 4 — ще можна");
    assert.ok((await call(page, "query", [":not(a):not(b):not(c):not(d)"])).v.length > 0);
  } finally { await page.close(); }
});

test("get: значення стилю обрізається до ліміту; attrs не показує службових і не бере прототип", async () => {
  const page = await open();
  try {
    const p = (await call(page, "query", ["#p"])).v[0].ref;
    const g = (await call(page, "get", [p, { styles: ["--big"] }])).v;
    assert.ok(g.styles["--big"].length <= 500 && g.styles["--big"].length > 0);
    const cta = (await call(page, "query", ["#cta", { attrs: true }])).v[0];
    assert.equal(cta.attrs["data-keep"], "k");
    assert.ok(!("data-deai-x" in cta.attrs), "службовий маркер не віддаємо");
    // Прототип видно лише в самій сторінці: через міст Playwright обʼєкт серіалізується заново.
    assert.equal(await page.evaluate(() => Object.getPrototypeOf(window.A.query("#cta", { attrs: true })[0].attrs)), null);
  } finally { await page.close(); }
});

test("text обрізається до 300 символів", async () => {
  const page = await open();
  try {
    assert.equal((await call(page, "query", ["#lt"])).v[0].text.length, 300);
  } finally { await page.close(); }
});

test("visible: display:none і visibility:hidden — false", async () => {
  const page = await open();
  try {
    assert.equal((await call(page, "query", ["#hid"])).v[0].visible, false);
    assert.equal((await call(page, "query", ["#inv"])).v[0].visible, false);
  } finally { await page.close(); }
});

test("bad-args: maxNodes 0/-1/\"5\", styles не масив", async () => {
  const page = await open();
  try {
    for (const m of [0, -1, "5", 1.5, null]) assert.equal((await call(page, "snapshot", [{ maxNodes: m }])).code, "bad-args", String(m));
    const ref = (await call(page, "query", ["#cta"])).v[0].ref;
    for (const st of ["color", { 0: "color" }, 5]) {
      assert.equal((await call(page, "snapshot", [{ styles: st }])).code, "bad-args");
      assert.equal((await call(page, "get", [ref, { styles: st }])).code, "bad-args");
      assert.equal((await call(page, "query", ["h1", { styles: st }])).code, "bad-args");
    }
  } finally { await page.close(); }
});

// 400 вузлів по 30 атрибутів по 300 кириличних символів (2 байти в UTF-8): понад 2 МБ байтів, але менше — «символів».
const FAT = (d) => {
  for (let i = 0; i < 400; i++) {
    const e = d.createElement("div"); e.className = "fat";
    for (let k = 0; k < 30; k++) e.setAttribute(`data-k${k}`, "я".repeat(300));
    d.body.appendChild(e);
  }
};

test("snapshot: обрізається за БАЙТАМИ UTF-8", async () => {
  const page = await open();
  try {
    await inFrame(page, FAT);
    const s = (await call(page, "snapshot", [{ attrs: true, maxNodes: 4000 }])).v;
    assert.equal(s.truncated, true);
    assert.ok(s.nodes.length < 400);
    const bytes = s.nodes.reduce((a, n) => a + new TextEncoder().encode(JSON.stringify(n)).length, 0);
    assert.ok(bytes <= 2 * 1024 * 1024, `байтів ${bytes}`);
    assert.ok(bytes > 1.5 * 1024 * 1024, "бюджет використано, а не недобрано");
  } finally { await page.close(); }
});

test("snapshot: maxNodes == число вузлів — не truncated; менше — truncated", async () => {
  const page = await open();
  try {
    const all = (await call(page, "snapshot", [])).v;
    const exact = (await call(page, "snapshot", [{ maxNodes: all.nodes.length }])).v;
    assert.equal(exact.truncated, false);
    assert.equal(exact.nodes.length, all.nodes.length);
    assert.equal((await call(page, "snapshot", [{ maxNodes: all.nodes.length - 1 }])).v.truncated, true);
  } finally { await page.close(); }
});

test("query: спільний бюджет байтів — вихід не більший за ліміт", async () => {
  const page = await open();
  try {
    await inFrame(page, FAT);
    const r = (await call(page, "query", [".fat", { limit: 500, attrs: true }])).v;
    assert.ok(r.length > 0 && r.length < 400, `вузлів ${r.length}`);
    const bytes = r.reduce((a, n) => a + new TextEncoder().encode(JSON.stringify(n)).length, 0);
    assert.ok(bytes <= 2 * 1024 * 1024, `байтів ${bytes}`);
  } finally { await page.close(); }
});
