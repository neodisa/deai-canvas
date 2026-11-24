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
import { TONE_COLORS } from "../../app/page-rules.js";

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

/* ---------- Task 4: мітки, reveal, pick ---------- */
/** Стан міток зсередини тіньового кореня хоста (прямий нащадок documentElement; у фікстурі є ще «двійник» у body). */
const MARKS = (d) => {
  const hosts = [...d.documentElement.children].filter((e) => e.hasAttribute("data-deai-marks"));
  const root = hosts[0]?.shadowRoot;
  const wrap = root?.querySelector(".w");
  return { hosts: hosts.length, hostIgnore: hosts[0]?.getAttribute("data-h2d-ignore"), open: !!root,
    wrapShown: !!wrap && d.defaultView.getComputedStyle(wrap).display !== "none",
    marks: root ? [...root.querySelectorAll(".mk")].map((m) => {
      const r = m.getBoundingClientRect(), l = m.querySelector(".l");
      return { hidden: m.hidden, t: d.defaultView.getComputedStyle(m).getPropertyValue("--t").trim(), label: l.textContent,
        hasB: !!l.querySelector("b"), cls: m.className, dn: l.classList.contains("dn"),
        pe: d.defaultView.getComputedStyle(m).pointerEvents, r: { x: r.left, y: r.top, w: r.width, h: r.height } };
    }) : [],
    cover: !!root?.querySelector(".cv"), pickBox: !!root?.querySelector(".pk:not([hidden])") };
};
const BTN = (d) => { const r = d.getElementById("cta").getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; };
/** Рамка = елемент ±3 px з кожного боку: краї в межах tol, розміри — у межах 2·tol. */
const near = (a, b, tol, msg) => { for (const k of ["x", "y", "w", "h"]) assert.ok(Math.abs(a[k] - b[k]) <= (k === "w" || k === "h" ? 2 * tol : tol), `${msg}: ${k} ${a[k]} vs ${b[k]}`); };
const refOf = async (page, sel) => (await call(page, "query", [sel])).v[0].ref;
const frameRaf = (page) => inFrame(page, (d) => new Promise((ok) => d.defaultView.requestAnimationFrame(() => d.defaultView.requestAnimationFrame(ok))));

test("mark: хост, тіньовий корінь, колір тону, ярлик лише текстом, охоплення кнопки", async () => {
  const page = await open();
  try {
    const ref = await refOf(page, "#cta");
    const id = (await call(page, "mark", [ref, { tone: "error", label: "Контраст <b>1.9</b>:1" }])).v;
    assert.equal(id, "m1");
    const s = await inFrame(page, MARKS);
    assert.equal(s.hosts, 1);
    assert.equal(s.hostIgnore, "true");
    assert.equal(s.open, true);
    assert.equal(s.marks.length, 1);
    assert.equal(s.marks[0].t.toLowerCase(), TONE_COLORS.error.toLowerCase());
    assert.equal(s.marks[0].label, "Контраст <b>1.9</b>:1");
    assert.equal(s.marks[0].hasB, false);
    assert.equal(s.marks[0].pe, "none");
    near(s.marks[0].r, await inFrame(page, BTN), 4, "рамка охоплює кнопку");
    // без opts: тон info
    const id2 = (await call(page, "mark", [ref])).v;
    assert.equal(id2, "m2");
    assert.equal((await inFrame(page, MARKS)).marks[1].t.toLowerCase(), TONE_COLORS.info.toLowerCase());
  } finally { await page.close(); }
});

test("mark: хост не видно читальним методам", async () => {
  const page = await open();
  try {
    const before = (await call(page, "snapshot", [])).v.nodes.length;
    await call(page, "mark", [await refOf(page, "#cta"), { label: "x" }]);
    assert.deepEqual((await call(page, "query", ["[data-deai-marks]"])).v, []);
    assert.equal((await call(page, "snapshot", [])).v.nodes.length, before);
    assert.ok(!(await call(page, "query", ["*", { limit: 500 }])).v.some((n) => n.tag === "div" && n.id === "" && n.cls === "" && n.rect.w === 0 && n.rect.h === 0));
  } finally { await page.close(); }
});

test("mark: прокрутка — мітка їде з кнопкою, кліки її не бачать", async () => {
  const page = await open();
  try {
    await call(page, "mark", [await refOf(page, "#cta"), { tone: "ok" }]);
    await inFrame(page, (d) => d.defaultView.scrollTo(0, 300));
    await page.waitForFunction(() => {
      const d = document.getElementById("f").contentDocument;
      const m = [...d.documentElement.children].find((e) => e.hasAttribute("data-deai-marks")).shadowRoot.querySelector(".mk");
      return Math.abs(m.getBoundingClientRect().top + 3 - d.getElementById("cta").getBoundingClientRect().top) < 1;
    });
    await inFrame(page, (d) => d.defaultView.scrollTo(0, 0));
    await frameRaf(page);
    assert.equal(await inFrame(page, (d) => { const r = d.getElementById("cta").getBoundingClientRect(); return d.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2).id; }), "cta");
  } finally { await page.close(); }
});

test("mark: кнопку прибрали — мітка прихована; unmark, clearMarks, ліміт, bad-args", async () => {
  const page = await open();
  try {
    const ref = await refOf(page, "#cta");
    const id = (await call(page, "mark", [ref])).v;
    await inFrame(page, (d) => d.getElementById("cta").remove());
    await frameRaf(page);
    assert.equal((await inFrame(page, MARKS)).marks[0].hidden, true);
    assert.equal((await call(page, "unmark", [id])).v ?? null, null);
    assert.equal((await inFrame(page, MARKS)).marks.length, 0);
    assert.equal((await call(page, "unmark", ["m999"])).code, undefined, "невідомий id — тихо");
    const ref2 = await refOf(page, "#p");
    await call(page, "mark", [ref2]); await call(page, "mark", [ref2]);
    await call(page, "clearMarks");
    assert.equal((await inFrame(page, MARKS)).marks.length, 0);
    assert.equal((await call(page, "mark", [ref2, { tone: "red" }])).code, "bad-args");
    assert.equal((await call(page, "mark", ["r-nope"])).code, "stale-ref");
    const codes = await page.evaluate(async (r) => {
      const out = [];
      for (let i = 0; i < 301; i++) { try { window.A.mark(r); out.push("ok"); } catch (e) { out.push(e.code); } }
      return [out.filter((c) => c === "ok").length, out[300]];
    }, ref2);
    assert.deepEqual(codes, [300, "too-many"]);
  } finally { await page.close(); }
});

test("mark: довгий ярлик обрізається; слухачі знімаються разом з останньою міткою", async () => {
  const page = await open();
  try {
    const ref = await refOf(page, "#cta");
    const id = (await call(page, "mark", [ref, { label: "ж".repeat(100) }])).v;
    const lab = (await inFrame(page, MARKS)).marks[0].label;
    assert.equal(Array.from(lab).length, 60);
    assert.ok(lab.endsWith("…"));
    await inFrame(page, (d) => { const w = d.defaultView, o = w.requestAnimationFrame.bind(w); w.RAFN = 0; w.requestAnimationFrame = (f) => { w.RAFN++; return o(f); }; });
    await call(page, "unmark", [id]);
    await inFrame(page, (d) => { d.defaultView.RAFN = 0; d.body.appendChild(d.createElement("i")); d.defaultView.scrollTo(0, 50); d.defaultView.dispatchEvent(new d.defaultView.Event("resize")); });
    await frameRaf(page); await new Promise((r) => setTimeout(r, 100));
    // два наші власні rAF у frameRaf не рахуються: лічильник стоїть на оригіналі, що обгорнутий — frameRaf їх викликає, тож віднімаємо 2
    assert.equal(await inFrame(page, (d) => d.defaultView.RAFN), 2, "після останньої мітки помічник кадрів не просить");
  } finally { await page.close(); }
});

test("reveal: елемент у видимій області; без мітки — тимчасова рамка на ~1,2 с; з міткою — клас fl", async () => {
  const page = await open();
  try {
    const far = await refOf(page, "#far");
    assert.equal((await call(page, "reveal", [far])).v ?? null, null);
    assert.equal((await inFrame(page, MARKS)).marks.length, 1, "тимчасова мітка");
    assert.equal((await inFrame(page, MARKS)).marks[0].label, "");
    await page.waitForFunction(() => { const d = document.getElementById("f").contentDocument; const r = d.getElementById("far").getBoundingClientRect(); return r.top >= 0 && r.bottom <= 600; });
    await page.waitForFunction(() => { const d = document.getElementById("f").contentDocument; const h = [...d.documentElement.children].find((e) => e.hasAttribute("data-deai-marks")); return h.shadowRoot.querySelectorAll(".mk").length === 0; }, null, { timeout: 4000 });
    // з міткою
    const cta = await refOf(page, "#cta");
    await call(page, "mark", [cta, { tone: "warn" }]);
    await call(page, "reveal", [cta]);
    const s = await inFrame(page, MARKS);
    assert.equal(s.marks.length, 1, "нової тимчасової нема");
    assert.ok(s.marks[0].cls.split(/\s+/).includes("fl"));
    await new Promise((r) => setTimeout(r, 1500));
    assert.ok(!(await inFrame(page, MARKS)).marks[0].cls.split(/\s+/).includes("fl"));
    assert.equal((await call(page, "reveal", ["r-nope"])).code, "stale-ref");
  } finally { await page.close(); }
});

test("mark: біля верху ярлик перевертається (dn)", async () => {
  const page = await open();
  try {
    await call(page, "mark", [await refOf(page, "#h"), { label: "x" }]);
    await frameRaf(page);
    assert.equal((await inFrame(page, MARKS)).marks[0].dn, true, "заголовок біля верху");
    await call(page, "mark", [await refOf(page, "#far"), { label: "y" }]);
    await inFrame(page, (d) => d.defaultView.scrollTo(0, 2000)); await frameRaf(page);
    const m = (await inFrame(page, MARKS)).marks;
    assert.equal(m[1].dn, false);
  } finally { await page.close(); }
});

/** Запустити pick() і не чекати: результат у `window.PKV`. */
const startPick = (page) => page.evaluate(() => { window.PKV = undefined; window.PK = window.A.pick(); window.PK.then((v) => { window.PKV = { v }; }); return true; });
const pickResult = async (page) => { await page.waitForFunction(() => window.PKV !== undefined, null, { timeout: 3000 }); return page.evaluate(() => window.PKV.v); };
const centerOf = async (page, sel) => {
  const fr = await page.evaluate(() => { const r = document.getElementById("f").getBoundingClientRect(); return { x: r.left, y: r.top }; });
  const r = await inFrame(page, (d, s) => { const b = d.querySelector(s).getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; }, sel);
  return { x: fr.x + r.x, y: fr.y + r.y };
};

test("pick: клік по #cta повертає вузол, сторінка кліка не бачить, мітки ховаються й повертаються", async () => {
  const page = await open();
  try {
    await call(page, "mark", [await refOf(page, "#p"), { label: "p" }]);
    await startPick(page);
    await page.waitForFunction(() => { const d = document.getElementById("f").contentDocument; return [...d.documentElement.children].some((e) => e.shadowRoot?.querySelector(".cv")); });
    const during = await inFrame(page, MARKS);
    assert.equal(during.wrapShown, false, "мітки сховані");
    assert.equal(during.cover, true);
    const c = await centerOf(page, "#cta");
    await page.mouse.move(c.x - 5, c.y); await page.mouse.move(c.x, c.y);
    await page.waitForFunction(() => { const d = document.getElementById("f").contentDocument; return !!d.documentElement.querySelector("[data-deai-marks]") && [...d.documentElement.children].find((e) => e.hasAttribute("data-deai-marks")).shadowRoot.querySelector(".pk span")?.textContent.startsWith("button.lo "); });
    const label = await inFrame(page, (d) => [...d.documentElement.children].find((e) => e.hasAttribute("data-deai-marks")).shadowRoot.querySelector(".pk span").textContent);
    assert.match(label, /^button\.lo \d+×\d+$/);
    await page.mouse.click(c.x, c.y);
    const n = await pickResult(page);
    assert.equal(n.id, "cta");
    assert.equal(await inFrame(page, (d) => d.defaultView.PAGE_CLICKS), 0);
    const after = await inFrame(page, MARKS);
    assert.equal(after.wrapShown, true);
    assert.equal(after.cover, false);
    assert.equal(await page.evaluate(() => window.A.picking), false);
  } finally { await page.close(); }
});

test("pick: Esc → null; другий pick() → перший null; destroy() → null і хоста нема", async () => {
  const page = await open();
  try {
    await startPick(page);
    await page.waitForFunction(() => window.A.picking === true);
    const prevented = await inFrame(page, (d) => { const e = new d.defaultView.KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }); d.dispatchEvent(e); return e.defaultPrevented; });
    assert.equal(prevented, true);
    assert.equal(await pickResult(page), null);
    assert.equal(await page.evaluate(() => window.A.picking), false);
    // Esc без вибору сторінку не чіпає
    assert.equal(await inFrame(page, (d) => { const e = new d.defaultView.KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true }); d.dispatchEvent(e); return e.defaultPrevented; }), false);
    // другий pick
    const r = await page.evaluate(async () => { const a = window.A.pick(); const b = window.A.pick(); const first = await a; window.A.cancelPick(); return [first, await b]; });
    assert.deepEqual(r, [null, null]);
    // destroy під час pick
    await startPick(page);
    await page.waitForFunction(() => window.A.picking === true);
    await page.evaluate(() => window.A.destroy());
    assert.equal(await pickResult(page), null);
    assert.equal((await inFrame(page, MARKS)).hosts, 0);
  } finally { await page.close(); }
});

// ---------- Task 5: зміни вигляду з журналом і слухання ----------
const sty = (page, sel, prop) => inFrame(page, (d, a) => d.querySelector(a[0]).style.getPropertyValue(a[1]), [sel, prop]);
const comp = (page, sel, prop) => inFrame(page, (d, a) => d.defaultView.getComputedStyle(d.querySelector(a[0])).getPropertyValue(a[1]), [sel, prop]);
const clsOf = async (page) => (await attrIn(page, "#cta", "class")).split(" ").sort().join(" ");
const attrIn = (page, sel, name) => inFrame(page, (d, a) => d.querySelector(a[0]).getAttribute(a[1]), [sel, name]);

test("setStyle: застосоване/відхилене, колір чорний, відкат без атрибута style", async () => {
  const page = await open();
  try {
    const cta = await refOf(page, "#cta");
    const r = await call(page, "setStyle", [cta, { color: "rgb(0, 0, 0)", background: "url(x)", width: "nope" }]);
    assert.deepEqual(r.v.applied, ["color"]);
    assert.deepEqual([...r.v.rejected].sort(), ["background", "width"]);
    assert.equal(await comp(page, "#cta", "color"), "rgb(0, 0, 0)");
    assert.equal(await sty(page, "#cta", "color-priority"), "");
    assert.deepEqual((await call(page, "revert", [r.v.id])).v, { reverted: 1, skipped: 0 });
    assert.equal(await inFrame(page, (d) => d.getElementById("cta").hasAttribute("style")), false);
    assert.ok(!/style=/.test(await inFrame(page, (d) => d.getElementById("cta").outerHTML)));
  } finally { await page.close(); }
});

test("setStyle: усе відхилено → id null і нічого в журналі; не-рядок → bad-args", async () => {
  const page = await open();
  try {
    const p = await refOf(page, "#p");
    const r = await call(page, "setStyle", [p, { width: "nope", background: "url(x)" }]);
    assert.deepEqual({ ...r.v, rejected: [...r.v.rejected].sort() }, { id: null, applied: [], rejected: ["background", "width"] });
    assert.deepEqual((await call(page, "revertAll")).v, { reverted: 0, skipped: 0 });
    assert.equal((await call(page, "setStyle", [p, { color: 5 }])).code, "bad-args");
  } finally { await page.close(); }
});

test("setStyle: був style — відкат повертає green і атрибут на місці; null знімає властивість", async () => {
  const page = await open();
  try {
    const p = await refOf(page, "#p");
    await call(page, "setStyle", [p, { color: "red" }]);
    assert.equal(await comp(page, "#p", "color"), "rgb(255, 0, 0)");
    assert.deepEqual((await call(page, "revertAll")).v, { reverted: 1, skipped: 0 });
    assert.equal(await sty(page, "#p", "color"), "green");
    assert.ok(await attrIn(page, "#p", "style"));
    const r = await call(page, "setStyle", [p, { color: null }]);
    assert.deepEqual(r.v.applied, ["color"]);
    assert.equal(await sty(page, "#p", "color"), "");
    await call(page, "revert", [r.v.id]);
    assert.equal(await sty(page, "#p", "color"), "green");
  } finally { await page.close(); }
});

test("setStyle: сторінка сама змінила колір → відкат skipped, колір лишився; змінила лише пріоритет → теж skipped", async () => {
  const page = await open();
  try {
    const p = await refOf(page, "#p");
    const a = await call(page, "setStyle", [p, { color: "red" }]);
    await inFrame(page, (d) => d.getElementById("p").style.color = "blue");
    assert.deepEqual((await call(page, "revert", [a.v.id])).v, { reverted: 0, skipped: 1 });
    assert.equal(await sty(page, "#p", "color"), "blue");
    const b = await call(page, "setStyle", [p, { color: "red" }]);
    await inFrame(page, (d) => d.getElementById("p").style.setProperty("color", "red", ""));   // те саме значення, інший пріоритет
    assert.deepEqual((await call(page, "revert", [b.v.id])).v, { reverted: 0, skipped: 1 });
    assert.equal(await sty(page, "#p", "color"), "red");
  } finally { await page.close(); }
});

test("setStyle: LIFO — два записи на одну властивість відкочуються до початкового", async () => {
  const page = await open();
  try {
    const p = await refOf(page, "#p");
    await call(page, "setStyle", [p, { color: "red" }]);
    await call(page, "setStyle", [p, { color: "black" }]);
    assert.deepEqual((await call(page, "revertAll")).v, { reverted: 2, skipped: 0 });
    assert.equal(await sty(page, "#p", "color"), "green");
  } finally { await page.close(); }
});

test("setClass: add/remove, відкат; клас, що вже був, у журнал не йде; нема змін → id null", async () => {
  const page = await open();
  try {
    const cta = await refOf(page, "#cta");
    const r = await call(page, "setClass", [cta, { add: ["x"], remove: ["lo"] }]);
    assert.ok(r.v.id);
    assert.equal(await clsOf(page), "cta x");
    assert.deepEqual((await call(page, "revert", [r.v.id])).v, { reverted: 2, skipped: 0 });   // по класу
    assert.equal(await clsOf(page), "cta lo");
    const n = await call(page, "setClass", [cta, { add: ["cta"], remove: ["nope"] }]);
    assert.deepEqual(n.v, { id: null });
    assert.deepEqual((await call(page, "revertAll")).v, { reverted: 0, skipped: 0 });
    assert.equal(await clsOf(page), "cta lo");
    // додали «cta», якого вже не було б, якби прибрали раніше: відкат не прибирає наявний
    const m = await call(page, "setClass", [cta, { add: ["cta", "y"] }]);
    await call(page, "revert", [m.v.id]);
    assert.equal(await clsOf(page), "cta lo");
    assert.equal((await call(page, "setClass", [cta, { add: ["bad name"] }])).code, "bad-args");
    assert.equal((await call(page, "setClass", [cta, { add: "x" }])).code, "bad-args");
  } finally { await page.close(); }
});

test("setClass: відкат не чіпає клас, який сторінка вже прибрала/додала сама", async () => {
  const page = await open();
  try {
    const cta = await refOf(page, "#cta");
    const r = await call(page, "setClass", [cta, { add: ["x"], remove: ["lo"] }]);
    await inFrame(page, (d) => d.getElementById("cta").classList.remove("x"));
    await inFrame(page, (d) => d.getElementById("cta").classList.add("lo"));
    await call(page, "revert", [r.v.id]);
    assert.equal(await clsOf(page), "cta lo");
  } finally { await page.close(); }
});

test("setAttr: зміна/зняття, відкат; заборонені імена; значення завелике", async () => {
  const page = await open();
  try {
    const cta = await refOf(page, "#cta");
    const a = await call(page, "setAttr", [cta, "aria-label", "Інше"]);
    assert.equal(await attrIn(page, "#cta", "aria-label"), "Інше");
    await call(page, "revert", [a.v.id]);
    assert.equal(await attrIn(page, "#cta", "aria-label"), "Почати");
    const b = await call(page, "setAttr", [cta, "aria-label", null]);
    assert.equal(await attrIn(page, "#cta", "aria-label"), null);
    await call(page, "revert", [b.v.id]);
    assert.equal(await attrIn(page, "#cta", "aria-label"), "Почати");
    for (const n of ["href", "onclick", "style", "class", "data-deai-x"]) assert.equal((await call(page, "setAttr", [cta, n, "x"])).code, "not-allowed", n);
    assert.equal((await call(page, "setAttr", [cta, "title", "я".repeat(301)])).code, "bad-args");
    assert.equal((await call(page, "setAttr", [cta, "title", 5])).code, "bad-args");
    const c = await call(page, "setAttr", [cta, "data-new", "1"]);
    await inFrame(page, (d) => d.getElementById("cta").setAttribute("data-new", "page"));
    assert.deepEqual((await call(page, "revert", [c.v.id])).v, { reverted: 0, skipped: 1 });
    assert.equal(await attrIn(page, "#cta", "data-new"), "page");
  } finally { await page.close(); }
});

test("setText: not-leaf для елемента з дітьми; розмітка лишається текстом; відкат; чужа зміна → skipped", async () => {
  const page = await open();
  try {
    assert.equal((await call(page, "setText", [await refOf(page, "#h"), "x"])).code, "not-leaf");
    const cta = await refOf(page, "#cta");
    const r = await call(page, "setText", [cta, "<b>x</b>"]);
    assert.equal(await inFrame(page, (d) => d.getElementById("cta").textContent), "<b>x</b>");
    assert.equal(await inFrame(page, (d) => d.getElementById("cta").querySelectorAll("b").length), 0);
    await call(page, "revert", [r.v.id]);
    assert.equal(await inFrame(page, (d) => d.getElementById("cta").textContent), "Почати");
    assert.equal((await call(page, "setText", [cta, "я".repeat(2001)])).code, "bad-args");
    const s = await call(page, "setText", [cta, "один"]);
    await inFrame(page, (d) => { d.getElementById("cta").textContent = "сторінка"; });
    assert.deepEqual((await call(page, "revert", [s.v.id])).v, { reverted: 0, skipped: 1 });
    assert.equal(await inFrame(page, (d) => d.getElementById("cta").textContent), "сторінка");
  } finally { await page.close(); }
});

test("журнал: 501-ша зміна → too-many і документ НЕ змінено; зниклий елемент при відкаті → skipped; невідомий id", async () => {
  const page = await open();
  try {
    const p = await refOf(page, "#p");
    for (let i = 0; i < 500; i++) assert.ok((await call(page, "setAttr", [p, "data-n", String(i)])).v.id, String(i));
    const over = await call(page, "setAttr", [p, "data-n", "лишнє"]);
    assert.equal(over.code, "too-many");
    assert.equal(await attrIn(page, "#p", "data-n"), "499", "після відмови документ не змінено");
    assert.equal((await call(page, "setStyle", [p, { color: "red" }])).code, "too-many");
    assert.equal(await sty(page, "#p", "color"), "green");
    assert.equal((await call(page, "setClass", [p, { add: ["z"] }])).code, "too-many");
    assert.equal((await call(page, "setText", [p, "t"])).code, "too-many");
    assert.equal(await inFrame(page, (d) => d.getElementById("p").textContent), "Абзац");
    assert.deepEqual((await call(page, "revertAll")).v, { reverted: 500, skipped: 0 });
    assert.equal(await attrIn(page, "#p", "data-n"), null);
    // зниклий елемент
    const lt = await refOf(page, "#lt");
    await call(page, "setAttr", [lt, "title", "t"]);
    const st = await call(page, "setStyle", [lt, { color: "red", margin: "1px" }]);
    await inFrame(page, (d) => d.getElementById("lt").remove());
    assert.deepEqual((await call(page, "revertAll")).v, { reverted: 0, skipped: 3 });
    assert.deepEqual((await call(page, "revert", ["c999"])).v, { reverted: 0, skipped: 0 });
    assert.deepEqual((await call(page, "revert", [st.v.id])).v, { reverted: 0, skipped: 0 }, "вже забрано");
  } finally { await page.close(); }
});

test("revertAll: збій в одному записі не губить решту", async () => {
  const page = await open();
  try {
    const p = await refOf(page, "#p"), cta = await refOf(page, "#cta");
    await call(page, "setAttr", [p, "title", "a"]);
    await call(page, "setAttr", [cta, "title", "b"]);
    await call(page, "setAttr", [p, "data-q", "c"]);
    // перший за порядком відкату (newest) — на елементі, у якого removeAttribute кидає
    await inFrame(page, (d) => { d.getElementById("p").removeAttribute = () => { throw new Error("boom"); }; });
    const r = await call(page, "revertAll");
    assert.equal(r.v.reverted + r.v.skipped, 3);
    assert.ok(r.v.skipped >= 1);
    assert.equal(await attrIn(page, "#cta", "title"), null, "елемент cta відкочено попри збій на p");
  } finally { await page.close(); }
});

// слухання
const evCount = (page, n) => page.evaluate((x) => window.EV.filter((e) => e[0] === x).length, n);
test("listen click: подія page-click, клік доходить до сторінки; false → тиша; bad-args", async () => {
  const page = await open();
  try {
    assert.equal((await call(page, "listen", [{ click: "yes" }])).code, "bad-args");
    assert.equal((await call(page, "listen", [{ hover: 1 }])).code, "bad-args");
    await call(page, "listen", [{ click: true }]);
    const c = await centerOf(page, "#cta");
    await page.keyboard.down("Shift"); await page.mouse.click(c.x, c.y); await page.keyboard.up("Shift");
    const ev = await page.evaluate(() => window.EV.filter((e) => e[0] === "page-click"));
    assert.equal(ev.length, 1);
    assert.equal(ev[0][1].node.id, "cta");
    assert.equal(ev[0][1].shift, true);
    assert.equal(ev[0][1].button, 0);
    assert.equal(typeof ev[0][1].x, "number");
    assert.equal(await inFrame(page, (d) => d.defaultView.PAGE_CLICKS), 1);
    await call(page, "listen", [{ click: false }]);
    await page.mouse.click(c.x, c.y);
    assert.equal(await evCount(page, "page-click"), 1);
    assert.equal(await inFrame(page, (d) => d.defaultView.PAGE_CLICKS), 2);
  } finally { await page.close(); }
});

test("listen click: під час pick подій нема; клік по нашому оверлею — теж", async () => {
  const page = await open();
  try {
    await call(page, "listen", [{ click: true }]);
    await startPick(page);
    await page.waitForFunction(() => window.A.picking === true);
    const c = await centerOf(page, "#cta");
    await page.mouse.click(c.x, c.y);
    await pickResult(page);
    assert.equal(await evCount(page, "page-click"), 0);
    await inFrame(page, (d) => d.getElementById("ours4").dispatchEvent(new d.defaultView.MouseEvent("click", { bubbles: true })));
    assert.equal(await evCount(page, "page-click"), 0);
  } finally { await page.close(); }
});

test("listen hover: page-hover лише при зміні елемента, не частіше 10/с, остання подія не губиться", async () => {
  const page = await open();
  try {
    await call(page, "listen", [{ hover: true }]);
    const n = await inFrame(page, (d) => {
      const fire = (id) => d.getElementById(id).dispatchEvent(new d.defaultView.MouseEvent("mouseover", { bubbles: true }));
      const ids = ["p", "cta", "lt", "p", "cta", "lt", "p", "cta", "lt", "p", "cta", "lt", "p", "cta", "lt", "p", "cta", "lt", "p", "cta"];
      for (const id of ids) fire(id);
      return ids.length;
    });
    assert.equal(n, 20);
    const t0 = await evCount(page, "page-hover");
    assert.ok(t0 <= 2, `за 20 рухів одразу ≤ 2 події, є ${t0}`);
    await page.waitForTimeout(300);
    const evs = await page.evaluate(() => window.EV.filter((e) => e[0] === "page-hover").map((e) => e[1].node.id));
    assert.ok(evs.length <= 3, String(evs.length));
    assert.equal(evs[evs.length - 1], "cta", "відкладена остання");
    // той самий елемент — без події
    const before = await evCount(page, "page-hover");
    await inFrame(page, (d) => d.getElementById("cta").dispatchEvent(new d.defaultView.MouseEvent("mouseover", { bubbles: true })));
    await page.waitForTimeout(250);
    assert.equal(await evCount(page, "page-hover"), before);
    await call(page, "listen", [{ hover: false }]);
    await inFrame(page, (d) => d.getElementById("lt").dispatchEvent(new d.defaultView.MouseEvent("mouseover", { bubbles: true })));
    await page.waitForTimeout(250);
    assert.equal(await evCount(page, "page-hover"), before);
  } finally { await page.close(); }
});

test("destroy(): відкочує зміни, знімає слухачів, клік після destroy подій не дає", async () => {
  const page = await open();
  try {
    const p = await refOf(page, "#p");
    await call(page, "setStyle", [p, { color: "red" }]);
    await call(page, "setAttr", [p, "title", "t"]);
    await call(page, "listen", [{ click: true, hover: true }]);
    await page.evaluate(() => window.A.destroy());
    assert.equal(await sty(page, "#p", "color"), "green");
    assert.equal(await attrIn(page, "#p", "title"), null);
    const c = await centerOf(page, "#cta");
    await page.mouse.click(c.x, c.y);
    await inFrame(page, (d) => d.getElementById("cta").dispatchEvent(new d.defaultView.MouseEvent("mouseover", { bubbles: true })));
    await page.waitForTimeout(250);
    assert.equal(await evCount(page, "page-click"), 0);
    assert.equal(await evCount(page, "page-hover"), 0);
  } finally { await page.close(); }
});
