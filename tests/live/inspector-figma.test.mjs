/**
 * Етап Г (0.29.0): панель властивостей і оверлей у бою. Мапа «перевірка → запобіжник → що буде без нього» — у кінці
 * файла (розділ «Мутації»), знята мутаційно.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 27200;
const VIEW = { width: 1400, height: 900 };

const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;font:16px/24px sans-serif;background:#fff}
#wrap{display:flex;flex-direction:column;gap:8px;padding:16px}
#card{display:flex;gap:12px;padding:10px 14px;border:1px solid #dde3ee;border-radius:7px;background:#f6f8fc}
#a{padding:6px 10px;background:#1f4fe0;color:#fff}
#b{padding:6px 10px;background:#e0e0e0}
#cb{box-sizing:content-box;width:300px;height:40px;padding:10px 24px;border:1px solid #888}
</style></head><body><div id="wrap"><div id="card"><a id="a">One</a><a id="b">Two</a></div><p id="para">Hello</p><div id="cb">Box</div></div></body></html>`;

async function openInspector(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame").contentWindow.CanvasInspector.on === true,
    null, { timeout: 3000 });
  return page;
}

/** Клік у центр елемента макета; чекаємо, поки оверлей його запінить. */
async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction((id) => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!(api.pinned && api.pinned.id === id);
  }, sel.slice(1), { timeout: 3000 });
}

const pinnedId = (page) => page.evaluate(() => {
  const p = document.getElementById("frame").contentWindow.CanvasInspector.pinned;
  return p ? p.id || p.localName : null;
});

/** Пакет тюнера на диску, або null. */
function pkg(dir) {
  const f = path.join(dir, ".dc-tuner.json");
  if (!existsSync(f)) return null;
  try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; }
}
async function waitPkg(page, dir, pred, what) {
  for (let i = 0; i < 80; i += 1) {
    const p = pkg(dir);
    if (p && pred(p)) return p;
    await page.waitForTimeout(50);
  }
  assert.fail(`пакет так і не дочекався: ${what}: ${JSON.stringify(pkg(dir))}`);
}
const editOf = (p, prop) => (p.elements || []).flatMap((e) => e.edits).find((e) => e.prop === prop);

async function boot(t) {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  return { dir, page: await openInspector(browser, url), url };
}

test("0. W/H панелі = РЕНДЕРЕНИЙ розмір (як ярлик оверлея); запис віднімає delta", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#cb");
  const label = await page.evaluate(() => {
    const sh = document.getElementById("frame").contentDocument.querySelector("[data-canvas-inspector]").shadowRoot;
    return sh.querySelector(".o-size").textContent;
  });
  const [lw, lh] = label.split("×").map((x) => parseInt(x, 10));
  const rendered = () => page.frameLocator("#frame").locator("#cb").evaluate((e) => [e.getBoundingClientRect().width, e.getBoundingClientRect().height]);
  assert.deepEqual(await rendered(), [lw, lh], "ярлик показує рендерений розмір");
  assert.equal(lw, 350, "300 + 2×24 + 2×1");
  assert.equal(await fieldValue(page, "width"), String(lw), "W панелі = ширина з ярлика, а не CSS width");
  assert.equal(await fieldValue(page, "height"), String(lh));
  const w = '#insp-panel .insp-f[data-prop="width"] .insp-fi';
  assert.equal(await page.locator(w).getAttribute("data-delta"), "50");
  await page.fill(w, String(lw + 34));
  await page.press(w, "Enter");
  await waitPkg(page, dir, (p) => editOf(p, "width"), "правка width");
  assert.equal((await rendered())[0], lw + 34, "відрендерена ширина виросла рівно на 34");
  assert.equal(editOf(pkg(dir), "width").to, "334px", "у CSS лягло введене − delta");
  assert.equal(await page.locator(w).getAttribute("data-delta"), "50", "delta стабільна й після перемальовки");
  await page.focus(w);
  await page.keyboard.press("ArrowUp");
  await waitPkg(page, dir, (p) => editOf(p, "width")?.to === "335px", "↑ у відображених одиницях");
  assert.equal((await rendered())[0], lw + 35);
});

test("0b. скраб підпису W теж віднімає delta: відрендерена ширина росте на показане значення", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#cb");
  const box = await page.locator('#insp-panel .insp-f[data-prop="width"] .insp-fl').boundingBox();
  const cx = box.x + box.width / 2; const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 30, cy, { steps: 10 });                // +10 у відображених одиницях
  await page.mouse.up();
  await waitPkg(page, dir, (p) => editOf(p, "width"), "правка width");
  assert.equal(editOf(pkg(dir), "width").to, "310px", "350+10 показано → 310 у CSS");
  assert.equal(await page.frameLocator("#frame").locator("#cb").evaluate((e) => e.getBoundingClientRect().width), 360);
});

test("T2-proof. клік → панель властивостей із назвою й розділами; поле gap пише макет і пакет", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  assert.equal(await page.locator("#insp-panel .insp-name").textContent(), "div");
  for (const s of ["size", "edges", "layout", "spacing", "fill", "stroke"]) {
    assert.equal(await page.locator(`#insp-panel [data-sec="${s}"]`).count(), 1, `немає розділу ${s}`);
  }
  const gap = '#insp-panel .insp-f[data-prop="gap"] .insp-fi';
  await page.focus(gap);
  await page.keyboard.press("ArrowUp");
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi')?.value === "13");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((el) => getComputedStyle(el).gap), "13px");
  const p = await waitPkg(page, dir, (x) => editOf(x, "gap"), "правка gap");
  assert.equal(editOf(p, "gap").to, "13px");
});
/** Лінії відстаней в оверлеї: усередині shadow-кореня рамки. */
const fieldValue = (page, prop) => page.locator(`#insp-panel .insp-f[data-prop="${prop}"] .insp-fi`).inputValue();
const altLines = (page) => page.evaluate(() => {
  const doc = document.getElementById("frame").contentDocument;
  const sh = doc.querySelector("[data-canvas-inspector]").shadowRoot;
  return sh.querySelectorAll(".rul:not(.hidden) .rg:not(.hidden)").length;
});

test("T3-proof. Alt показує відстані, відпущений Alt — ні; Alt+→ переводить ціль на сусіда", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  assert.equal(await altLines(page), 0, "без Alt ліній немає");
  await page.keyboard.down("Alt");
  assert.ok(await altLines(page) > 0, "з Alt є лінії до батька");
  await page.keyboard.up("Alt");
  assert.equal(await altLines(page), 0, "відпущений Alt прибирає лінії");

  await page.keyboard.down("Alt");
  await page.keyboard.press("ArrowRight");
  const ok = await page.evaluate(() => {
    const f = document.getElementById("frame");
    const sh = f.contentDocument.querySelector("[data-canvas-inspector]").shadowRoot;
    const tgt = sh.querySelector(".o-tgt").getBoundingClientRect();
    const b = f.contentDocument.getElementById("b").getBoundingClientRect();
    return Math.abs(tgt.left - b.left) < 1 && Math.abs(tgt.width - b.width) < 1;
  });
  await page.keyboard.up("Alt");
  assert.equal(ok, true, "ціль Alt — сусід #b");
});

/** Видимість шару оверлея (`hl` — коробка margin, `hl-pad` — padding) у shadow-корені рамки. */
const layerShown = (page, cls) => page.evaluate((c) => {
  const doc = document.getElementById("frame").contentDocument;
  const n = doc.querySelector("[data-canvas-inspector]").shadowRoot.querySelector(`.${c}`);
  return !!n && !n.classList.contains("hidden");
}, cls);

test("T3-proof. коробка margin/padding: наведення без Alt — видима, під Alt — схована", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  // Вибраний елемент коробки не має: заливка margin/padding лягала на нього й спотворювала кольори, які дизайнер
  // саме крутить у панелі (знайдено на знімку 16.11.2026). Курсор лежить на вибраному — ховера іншого елемента нема.
  await page.waitForFunction(() => !!document.getElementById("frame").contentWindow.CanvasInspector.pinned,
    null, { timeout: 3000 });
  assert.deepEqual([await layerShown(page, "hl"), await layerShown(page, "hl-pad")], [false, false],
    "на вибраному без наведення шари margin/padding сховані");
  const b = await page.frameLocator("#frame").locator("#b").boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2);
  await page.waitForFunction(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!(api.hover && api.hover.id === "b");
  }, null, { timeout: 3000 });
  assert.equal(await layerShown(page, "hl"), true, "без Alt шар margin видимий");
  assert.equal(await layerShown(page, "hl-pad"), true, "без Alt шар padding видимий");
  await page.keyboard.down("Alt");
  const hidden = [await layerShown(page, "hl"), await layerShown(page, "hl-pad")];
  await page.keyboard.up("Alt");
  assert.deepEqual(hidden, [false, false], "під Alt шари margin/padding сховані");
});

test("T3-proof. драбина: Enter — дитина, ← → — сусід, Esc — батько, далі зняти вибір, далі вимкнути", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#card");
  await page.keyboard.press("Enter");
  assert.equal(await pinnedId(page), "a", "Enter → перший дочірній");
  await page.keyboard.press("ArrowRight");
  assert.equal(await pinnedId(page), "b", "→ → сусід");
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), "card", "Esc → батько");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), null, "на корені вибір знято");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector.on), false,
    "без вибору Esc вимикає інспектор");
});

test("T3-proof. фокус в оболонці: ← → і Alt ідуть тим самим handleKey", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.evaluate(() => { document.getElementById("frame").blur(); document.body.focus(); });
  assert.equal(await page.evaluate(() => document.activeElement === document.body), true, "фокус у тілі оболонки");
  await page.keyboard.press("ArrowRight");
  assert.equal(await pinnedId(page), "b", "→ з оболонки веде до сусіда");
  await page.keyboard.down("Alt");
  const lines = await altLines(page);
  await page.keyboard.up("Alt");
  assert.ok(lines > 0, "Alt з оболонки малює відстані");
});
