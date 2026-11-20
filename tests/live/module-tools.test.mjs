/**
 * Інструменти модулів в оболонці (api 2, M1 Task 5): кнопка в острівці, панель-пісочниця, міст, клавіші, ⌘K.
 * Свій модуль-фікстура в тимчасовому просторі (`DEAI_HOME` — теж тимчасовий), довіра — через шов `DEAI_TRUST_CONFIRM`
 * (POST із «позначками браузера», як це робить сторінка канваса), увімкнення — звичайним `/api/module-enable`.
 *
 *   A острівець: кнопка лише в «Макеті»; без модуля розмітка та сама, що з модулем мінус його кнопка;
 *   B клік → панель із назвою, `sandbox` без `allow-same-origin`; `init` довіз контекст (назва сторінки);
 *      у панелі `localStorage` кидає, `fetch` відхилено, `deai.call` повертає значення; зміна сторінки → подія `context`;
 *   C права панель одна: коментарі закривають інструмент, `J` перемикає (і з рамки), ⌘K показує пункт, інспектор закриває.
 * Знімки для людини — у `SHOTS` (`DEAI_SHOTS`), якщо задано.
 */
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { VIEW, stop, waitBarReady } from "./_spaces-kit.mjs";
import { startServer, taskFixture } from "./fixture.mjs";

/* Своя смуга (`tests/live-ports.test.mjs` стереже, що бази не збігаються). */
const PORT_BASE = 33000;
const SHOTS = process.env.DEAI_SHOTS || "";
const MOCKUP = (id) => `<!doctype html><html><head><meta charset="utf-8"><title>Макет ${id}</title></head>`
  + `<body style="margin:0;font-family:sans-serif"><h1 id="t">Макет ${id}</h1><p>текст</p></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

const SERVER_PY = `def check(ctx):
    return {"ok": True, "detail": "probe"}


def tool_echo(ctx, args):
    return args
`;
const PANEL = `<!doctype html><html><head><meta charset="utf-8"><title>Probe panel</title></head><body class="dk-panel">
<h2 id="title">…</h2><div id="ls">…</div><div id="fetch">…</div><div id="echo">…</div><div id="ctx">…</div><div id="ev">…</div><button id="nav" type="button">nav</button>
<script>
const $ = (id) => document.getElementById(id);
$("nav").onclick = () => { location.href = "/api/module-ui/studio/probe-mod/panel/index.html?x=1"; };
deai.on("context", (c) => { $("ev").textContent = "context:" + (c.page ? c.page.title : "none"); });
(async () => {
  const init = await deai.ready;
  $("title").textContent = init.context.page ? init.context.page.title : "no-page";
  $("ctx").textContent = "ctx:" + init.context.space.id + ":" + init.theme + ":" + typeof init.vars["--s1"];
  try { localStorage.getItem("x"); $("ls").textContent = "ls:ok"; } catch (e) { $("ls").textContent = "ls:threw"; }
  try { await fetch("/api/tasks"); $("fetch").textContent = "fetch:ok"; } catch (e) { $("fetch").textContent = "fetch:rejected"; }
  const r = await deai.call("tool_echo", { x: 1 });
  $("echo").textContent = "echo:" + JSON.stringify(r);
})();
</script></body></html>`;

function writeProbe(spacePath) {
  const d = path.join(spacePath, "modules", "probe-mod");
  mkdirSync(path.join(d, "panel"), { recursive: true });
  writeFileSync(path.join(d, "module.json"), JSON.stringify({ api: 2, id: "probe-mod", name: "Probe module (test)", version: "1.0.0", roles: [],
    tools: [{ id: "probe", label: "Probe", icon: "task", panel: "panel/index.html", key: "J" }] }));
  writeFileSync(path.join(d, "server.py"), SERVER_PY);
  writeFileSync(path.join(d, "panel", "index.html"), PANEL);
}

/** Довіра (як сторінка канваса: `Origin` + `Sec-Fetch-Site: same-origin`; системне вікно — шов `yes`) і увімкнення. */
async function trustAndEnable(url) {
  const st = await (await fetch(`${url}/api/module-trust?space=studio&id=probe-mod`)).json();
  assert.ok(st.trust?.hash, `стан довіри: ${JSON.stringify(st)}`);
  const tr = await fetch(`${url}/api/module-trust`, { method: "POST",
    headers: { "Content-Type": "application/json", Origin: url, "Sec-Fetch-Site": "same-origin" },
    body: JSON.stringify({ space: "studio", id: "probe-mod", hash: st.trust.hash }) });
  assert.equal(tr.status, 200, `довіра: ${await tr.text()}`);
  const en = await (await fetch(`${url}/api/module-enable`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ space: "studio", id: "probe-mod", settings: {} }) })).json();
  assert.equal(en.ok, true, `module-enable: ${JSON.stringify(en)}`);
}

async function boot(t, { enable = true } = {}) {
  const X = taskFixture({ html: MOCKUP });
  const server = await startServer(null, { portBase: PORT_BASE, env: { DEAI_TRUST_CONFIRM: "yes" },
    spaces: [{ name: "Studio", id: "studio", color: "space-2", tasks: { t1: { dir: X.dir, title: "Задача" } } }] });
  t.after(() => stop(server.child));
  writeProbe(server.spaces[0].path);
  if (enable) await trustAndEnable(server.url);
  const context = await browser.newContext({ viewport: VIEW });
  t.after(() => context.close());
  const host = new URL(server.url).host;
  await context.route((u) => u.host !== host && !["data:", "blob:", "about:"].includes(u.protocol), (r) => r.abort("blockedbyclient"));
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message ?? e)));
  await page.goto(`${server.url}/app/`);
  await waitBarReady(page, 15000);
  await page.waitForSelector(".panel [data-page]", { timeout: 15000 });
  await page.waitForFunction(() => document.getElementById("frame").contentDocument?.querySelector("[data-comment-layer]"), null, { timeout: 15000 });
  return { ...server, page, errors };
}

const islandHtml = (page) => page.evaluate(() => document.getElementById("isl-tools").innerHTML);
const modVisible = (page) => page.evaluate(() => {
  const e = document.getElementById("mod-panel");
  return !!e && !e.hidden && getComputedStyle(e).display !== "none" && e.getClientRects().length > 0;
});
const BTN = '#isl-tools [data-act="modtool"]';
const stripMod = (h) => h.replace(/<button[^>]*data-act="modtool"[\s\S]*?<\/button>/g, "");

test("A: кнопка модуля — лише в «Макеті»; без модуля розмітка острівця та сама, що з модулем мінус його кнопка", async (t) => {
  const s = await boot(t, { enable: false });
  const { page } = s;
  const baseline = await islandHtml(page);
  assert.equal(baseline.includes("modtool"), false);
  await trustAndEnable(s.url);
  await page.reload();
  await waitBarReady(page, 15000);
  await page.waitForSelector(BTN, { timeout: 15000 });
  const withMod = await islandHtml(page);
  assert.equal(stripMod(withMod), baseline, "острівець без кнопки модуля відрізняється від базової розмітки");
  assert.match(withMod, /data-val="probe-mod\/probe"[^>]*aria-pressed="false"[^>]*aria-label="Probe" title="Probe \(J\)"/);
  assert.ok(withMod.indexOf('data-act="inspector"') < withMod.indexOf('data-act="modtool"'));
  await page.keyboard.press("Alt+M");                       // «Огляд»
  await page.waitForFunction(() => !document.getElementById("canvas").hidden, null, { timeout: 15000 });
  assert.equal(await page.locator(BTN).count(), 0, "в «Огляді» кнопка модуля є");
  await page.keyboard.press("Alt+M");
  await page.waitForSelector(BTN, { timeout: 15000 });
  assert.deepEqual(s.errors, []);
});

test("B+C: панель-пісочниця, міст, права панель одна, клавіші, ⌘K, інспектор", async (t) => {
  const s = await boot(t);
  const { page } = s;
  await page.waitForSelector(BTN, { timeout: 15000 });
  const panel = () => page.frameLocator("#mod-panel iframe");
  const frameWin = page.frameLocator("#frame");

  // B: відкриття
  await page.click(BTN);
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);
  assert.equal(await modVisible(page), true);
  assert.equal(await page.evaluate(() => document.body.classList.contains("with-mod")), true);
  assert.match(await page.locator("#mod-panel .panel-title").textContent(), /^Probe$/);
  assert.equal(await page.locator(BTN).getAttribute("aria-pressed"), "true");
  const sb = await page.locator("#mod-panel iframe").getAttribute("sandbox");
  assert.equal(sb, "allow-scripts allow-forms");
  assert.equal(sb.includes("allow-same-origin"), false);
  assert.equal(await page.locator("#mod-panel iframe").getAttribute("referrerpolicy"), "no-referrer");
  assert.equal(await page.locator("#mod-panel [data-act='modclose']").getAttribute("aria-label"), "Закрити");

  await panel().locator("#echo").filter({ hasText: "echo:" }).waitFor({ timeout: 15000 });
  assert.equal(await panel().locator("#title").textContent(), "Головна", "init не довіз назву сторінки з context");
  assert.equal(await panel().locator("#ls").textContent(), "ls:threw", "localStorage у пісочниці не кинув");
  assert.equal(await panel().locator("#fetch").textContent(), "fetch:rejected", "fetch з пісочниці не відхилено");
  assert.equal(await panel().locator("#echo").textContent(), 'echo:{"x":1}');
  assert.match(await panel().locator("#ctx").textContent(), /^ctx:studio:dark:string$/);

  // повідомлення НЕ від вікна рамки панелі (тут — від самої оболонки) міст ігнорує: `close` не закриває панель
  await page.evaluate(() => new Promise((done) => {
    window.postMessage({ deai: 1, id: 98, method: "close", args: [] }, "*");
    setTimeout(done, 400);
  }));
  assert.equal(await modVisible(page), true, "міст послухав повідомлення не від рамки панелі");

  // зміна сторінки в тому ж просторі: панель лишається й отримує `context`
  await page.locator('[data-page="poshuk"]').click();
  await panel().locator("#ev").filter({ hasText: "context:Пошук" }).waitFor({ timeout: 15000 });
  assert.equal(await modVisible(page), true, "зміна сторінки закрила панель");

  // знімки для людини
  if (SHOTS) {
    mkdirSync(SHOTS, { recursive: true });
    await page.screenshot({ path: path.join(SHOTS, "mod-panel-open.png") });
    const box = await page.locator("#hud .island").boundingBox();
    await page.screenshot({ path: path.join(SHOTS, "mod-island.png"),
      clip: { x: Math.max(0, box.x - 20), y: Math.max(0, box.y - 20), width: box.width + 40, height: box.height + 40 } });
  }

  // C: коментарі витісняють інструмент, `J` повертає його, а коментарі закриває
  await page.keyboard.press("c");
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden);
  assert.equal(await page.locator("#cmt-panel").isVisible(), true);
  assert.equal(await page.locator("#mod-panel iframe").count(), 0, "рамку закритої панелі не знято з розмітки");
  await page.keyboard.press("j");
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);
  assert.equal(await page.locator("#cmt-panel").isVisible(), false, "коментарі лишились разом з інструментом");
  await page.keyboard.press("j");
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden);
  assert.equal(await page.evaluate(() => document.body.classList.contains("with-mod")), false);
  assert.equal(await page.locator(BTN).getAttribute("aria-pressed"), "false");

  // `J` з фокусом у рамці макета
  await frameWin.locator("#t").click();
  await page.keyboard.press("j");
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);

  // інспектор: клавіша `I` у рамці закриває інструмент
  await frameWin.locator("#t").click();
  await page.keyboard.press("i");
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden, null, { timeout: 5000 });
  assert.equal(await page.locator("#insp-panel").isVisible(), true, "інспектор не ввімкнувся");
  // інструмент відкриває → інспектор вимикається
  await page.click(BTN);
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);
  assert.equal(await page.locator("#insp-panel").isVisible(), false, "інспектор лишився разом з інструментом");
  // кнопка інспектора закриває інструмент
  await page.click('#isl-tools [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden);

  // ⌘K: пункт «Probe» у групі «Модулі» з підказкою `J`; Enter відкриває
  await page.keyboard.press("ControlOrMeta+k");
  await page.waitForSelector(".pal");
  await page.fill("#palq", "Probe");
  const item = page.locator('.pal-it', { hasText: "Probe" });
  assert.equal(await item.count(), 1);
  assert.match(await page.locator(".pal-grp").first().textContent(), /Модулі/);
  assert.equal((await item.locator(".sp").textContent()).trim(), "J");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);

  // хрестик
  await page.click("#mod-panel [data-act='modclose']");
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden);

  assert.equal(await page.evaluate(() => document.activeElement?.dataset?.act), "modtool", "після × фокус не на кнопці інструмента");

  // скрипт панелі перейшов на іншу адресу — інструмент закривається (міст не слухає чужу сторінку)
  await page.click(BTN);
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);
  await panel().locator("#echo").filter({ hasText: "echo:" }).waitFor({ timeout: 15000 });
  await panel().locator("#nav").click();
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden, null, { timeout: 10000 });

  // чистий перегляд: літера модуля не відкриває панель
  await page.keyboard.press("ControlOrMeta+Shift+Backslash");
  await page.waitForSelector("#cv-unclean");
  await page.evaluate(() => { window.__dp = null; window.addEventListener("keydown", (e) => { window.__dp = e.defaultPrevented; }); });
  await page.keyboard.press("j");
  await page.waitForTimeout(300);
  assert.equal(await modVisible(page), false, "літера модуля відкрила панель у чистому перегляді");
  assert.equal(await page.evaluate(() => window.__dp), false, "літера в чистому перегляді проковтнута (preventDefault)");
  await page.keyboard.press("ControlOrMeta+Shift+Backslash");
  await page.waitForSelector("#bar .bar");

  // «Огляд» і «Задачі» закривають
  await page.click(BTN);
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);
  await page.keyboard.press("Alt+M");
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden);
  await page.keyboard.press("Alt+M");
  await page.waitForSelector(BTN);
  await page.click(BTN);
  await page.waitForFunction(() => !document.getElementById("mod-panel").hidden);
  await page.click('#tabs [data-act="home"]');
  await page.waitForFunction(() => document.getElementById("mod-panel").hidden);
  assert.deepEqual(s.errors, []);
});
