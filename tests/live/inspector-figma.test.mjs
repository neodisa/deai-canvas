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
#sc{box-sizing:content-box;width:200px;height:30px;padding:10px;transform:scale(.5);transform-origin:0 0}
#nb{border:0 none #f00;padding:4px;color:#222}
#fr{width:99.6px;height:20px;background:#ccc}
</style></head><body><div id="wrap"><div id="card"><a id="a">One</a><a id="b">Two</a></div><p id="para">Hello</p><div id="cb">Box</div><div id="sc">Sc</div><div id="fr">Fr</div><span id="nb">Nb</span><input id="inp"></div></body></html>`;

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

/** Лінії відстаней в оверлеї: усередині shadow-кореня рамки. */
const fieldValue = (page, prop) => page.locator(`#insp-panel .insp-f[data-prop="${prop}"] .insp-fi`).inputValue();
const altLines = (page) => page.evaluate(() => {
  const doc = document.getElementById("frame").contentDocument;
  const sh = doc.querySelector("[data-canvas-inspector]").shadowRoot;
  return sh.querySelectorAll(".rul:not(.hidden) .rg:not(.hidden)").length;
});

/** Видимість шару оверлея (`hl` — коробка margin, `hl-pad` — padding) у shadow-корені рамки. */
const layerShown = (page, cls) => page.evaluate((c) => {
  const doc = document.getElementById("frame").contentDocument;
  const n = doc.querySelector("[data-canvas-inspector]").shadowRoot.querySelector(`.${c}`);
  return !!n && !n.classList.contains("hidden");
}, cls);

test("T3b. коробка margin/padding: наведення без Alt — видима, під Alt — схована", async (t) => {
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

const POSTS = (page) => {
  const log = [];
  page.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/api/tuner")) log.push(r.url()); });
  return log;
};

test("1. клік → панель із назвою й розділами; Esc → батько; Enter → дочірній; ← → — сусіди", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  assert.equal(await page.locator("#insp-panel .insp-name").textContent(), "a");
  for (const s of ["size", "edges", "spacing", "fill", "stroke", "text"]) {
    assert.equal(await page.locator(`#insp-panel [data-sec="${s}"]`).count(), 1, `немає розділу ${s}`);
  }
  assert.equal(await page.locator('#insp-panel [data-sec="layout"]').count(), 0,
    "#a не flex-контейнер (він flex-елемент): авто-лейауту немає");
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), "card", "Esc вибирає батька");
  await page.keyboard.press("Enter");
  assert.equal(await pinnedId(page), "a", "Enter вибирає першого дочірнього");
  await page.keyboard.press("ArrowRight");
  assert.equal(await pinnedId(page), "b");
  await page.keyboard.press("ArrowLeft");
  assert.equal(await pinnedId(page), "a");
  // Esc до кореня: card → wrap → body → зняти вибір → вимкнути
  for (const want of ["card", "wrap", "body"]) {
    await page.keyboard.press("Escape");
    assert.equal(await pinnedId(page), want);
  }
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), null, "на корені Esc знімає вибір");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector.on), false);
});

test("1b. ті самі клавіші працюють із фокусом в ОБОЛОНЦІ (пересилання)", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.locator("#insp-panel .insp-top").click();            // фокус ушов із рамки в оболонку
  assert.equal(await page.evaluate(() => document.activeElement === document.body), true);
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), "card");
  await page.keyboard.press("Enter");
  assert.equal(await pinnedId(page), "a");
  await page.keyboard.press("ArrowRight");
  assert.equal(await pinnedId(page), "b");
});

test("1c. Esc поступається відкритому питанню оболонки", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.evaluate(() => {                                      // імітація відкритого питання: його тримає askUp()
    const d = document.createElement("div"); d.className = "cv-ask-scrim"; document.body.appendChild(d);
  });
  await page.evaluate(() => document.getElementById("frame").contentWindow.focus());
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), "a", "поки є питання, Esc не піднімає вибір");
});

test("2. Alt → лінії відстаней; відпущений Alt → ліній нема; Alt+→ — сусід; blur знімає лінії", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.keyboard.down("Alt");
  assert.ok(await altLines(page) > 0);
  await page.keyboard.up("Alt");
  assert.equal(await altLines(page), 0);
  await page.keyboard.down("Alt");
  await page.keyboard.press("ArrowRight");
  const onB = await page.evaluate(() => {
    const f = document.getElementById("frame");
    const sh = f.contentDocument.querySelector("[data-canvas-inspector]").shadowRoot;
    const g = sh.querySelector(".o-tgt").getBoundingClientRect();
    const b = f.contentDocument.getElementById("b").getBoundingClientRect();
    return Math.abs(g.left - b.left) < 1;
  });
  assert.equal(onB, true, "Alt+→: ціль — сусід #b");
  await page.evaluate(() => document.getElementById("frame").contentWindow.dispatchEvent(new Event("blur")));
  assert.equal(await altLines(page), 0, "втрата фокуса вікна прибирає лінії, навіть без keyup");
  await page.keyboard.up("Alt");
});

test("3. ↑ у полі gap: +1 на макеті й у пакеті; Shift+↑ — +10", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  const gap = '#insp-panel .insp-f[data-prop="gap"] .insp-fi';
  assert.equal(await fieldValue(page, "gap"), "12");
  await page.focus(gap);
  await page.keyboard.press("ArrowUp");
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi').value === "13");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((e) => getComputedStyle(e).gap), "13px");
  await waitPkg(page, dir, (p) => editOf(p, "gap")?.to === "13px", "gap 13px");
  await page.keyboard.press("Shift+ArrowUp");
  await waitPkg(page, dir, (p) => editOf(p, "gap")?.to === "23px", "gap 23px");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((e) => getComputedStyle(e).gap), "23px");
});

test("3b. пара ↔ пише ДВІ властивості; «Різні», коли сторони не рівні", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");                                        // padding: 10px 14px
  assert.equal(await fieldValue(page, "padding-left"), "14");
  const f = '#insp-panel .insp-f[data-prop="padding-left"] .insp-fi';
  await page.fill(f, "20");
  await page.press(f, "Enter");
  const p = await waitPkg(page, dir, (x) => editOf(x, "padding-left") && editOf(x, "padding-right"), "обидві сторони");
  assert.equal(editOf(p, "padding-left").to, "20px");
  assert.equal(editOf(p, "padding-right").to, "20px");
  // зробимо сторони різними через консоль макета й перечитаємо панель
  await page.frameLocator("#frame").locator("#card").evaluate((e) => { e.style.setProperty("padding-left", "3px", "important"); });
  await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector._tuned());
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="padding-top"]'));
  assert.equal(await page.locator('#insp-panel [data-act="inspsides"]').isDisabled(), true,
    "сторони різні — «окремо» розкрито само й не вимикається");
});

test("4. скраб підпису: значення міняється живцем, панель не перемальовується, пакет пишеться ОДИН раз", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  const label = page.locator('#insp-panel .insp-f[data-prop="gap"] .insp-fl');
  const box = await label.boundingBox();
  await page.evaluate(() => { document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi').dataset.keep = "1"; });
  const posts = POSTS(page);
  const cx = box.x + box.width / 2; const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 30, cy, { steps: 10 });                // 30 px = +10
  assert.equal(await page.evaluate(() => document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi')?.dataset.keep),
    "1", "під час жесту панель не перемальовується цілком");
  assert.equal(posts.length, 0, "під час жесту пакет не пишеться");
  await page.mouse.up();
  const p = await waitPkg(page, dir, (x) => editOf(x, "gap")?.to === "22px", "gap 22px");
  assert.equal(editOf(p, "gap").to, "22px");
  await page.waitForTimeout(300);
  assert.equal(posts.length, 1, `пакет мусить писатись ОДИН раз за жест, а писався ${posts.length}`);
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((e) => getComputedStyle(e).gap), "22px");
});

test("7. «Надіслати Клоду» → status: ready на диску і «Готово» в панелі", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  await page.focus('#insp-panel .insp-f[data-prop="gap"] .insp-fi');
  await page.keyboard.press("ArrowUp");
  await waitPkg(page, dir, (p) => p.status === "draft" && editOf(p, "gap"), "чернетка з правкою");
  await page.click("#insp-panel .insp-send");
  await waitPkg(page, dir, (p) => p.status === "ready", "status ready");
  assert.equal(await page.locator("#insp-panel .insp-ready").count(), 1);
});

test("8. клавіша M нічого не робить: ні режиму, ні лінійки; панель незмінна", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#card");
  const before = await page.locator("#insp-panel").innerHTML();
  await page.keyboard.press("m");
  const st = await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    const sh = api._host.shadowRoot;
    return { mode: api.mode, setMode: typeof api.setMode, ruler: sh.querySelectorAll(".rul:not(.hidden)").length };
  });
  assert.deepEqual(st, { mode: undefined, setMode: "undefined", ruler: 0 });
  assert.equal(await page.locator("#insp-panel").innerHTML(), before);
  assert.equal(await page.locator('#insp-panel [data-act="insptab"]').count(), 0);
});


const frameApi = (page) => page.evaluateHandle(() => document.getElementById("frame").contentWindow.CanvasInspector);

test("R1. скраб, що не дочекався pointerup (Esc, інше вікно), не заморожує панель", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#card");
  const box = await page.locator('#insp-panel .insp-f[data-prop="gap"] .insp-fl').boundingBox();
  const cx = box.x + box.width / 2; const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 9, cy, { steps: 3 });
  // pointerup не прийде: Esc вимикає інспектор, потім він вмикається знову й пінується інший елемент без жодного миші
  await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    api.set(false); api.set(true);
    api._setPin(document.getElementById("frame").contentDocument.getElementById("para"), true);
  });
  await page.waitForFunction(() => document.querySelector("#insp-panel .insp-name")?.textContent === "p",
    null, { timeout: 3000 }).catch(() => {});
  assert.equal(await page.locator("#insp-panel .insp-name").textContent(), "p", "панель показує новий елемент");
  await page.mouse.up();
});

test("R1b. lostpointercapture завершує скраб одним записом", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  const box = await page.locator('#insp-panel .insp-f[data-prop="gap"] .insp-fl').boundingBox();
  const cx = box.x + box.width / 2; const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 30, cy, { steps: 10 });
  await page.evaluate(() => {
    const lab = document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fl');
    lab.dispatchEvent(new Event("lostpointercapture", { bubbles: true }));
  });
  await waitPkg(page, dir, (p) => editOf(p, "gap")?.to === "22px", "запис на lostpointercapture");
  await page.mouse.up();
});

test("R2. W/H — розмір РОЗКЛАДКИ: дробова ширина без хибної delta, transform не псує число", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#fr");
  const w = '#insp-panel .insp-f[data-prop="width"] .insp-fi';
  assert.equal(await page.locator(w).getAttribute("data-delta"), null, "99.6 без відступів — delta немає");
  await page.fill(w, "101");
  await page.press(w, "Enter");
  await waitPkg(page, dir, (p) => editOf(p, "width"), "правка width");
  assert.equal(editOf(pkg(dir), "width").to, "101px", "пишеться введене, а не 100.6px");
  await pin(page, "#sc");
  assert.equal(await fieldValue(page, "width"), "220", "W = розмір розкладки (200 + 2×10), не масштабований rect");
  const label = await page.evaluate(() => document.getElementById("frame").contentDocument
    .querySelector("[data-canvas-inspector]").shadowRoot.querySelector(".o-size").textContent);
  assert.equal(label.split("×")[0].trim(), "220", "ярлик оверлея показує те саме число");
  await page.fill(w, "240");
  await page.press(w, "Enter");
  await waitPkg(page, dir, (p) => editOf(p, "width")?.to === "220px", "240 − 20 = 220px");
});

test("R3. менше за відступи: ширина клампиться ПІСЛЯ віднімання delta (0px, не -40px)", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#cb");
  const w = '#insp-panel .insp-f[data-prop="width"] .insp-fi';
  await page.fill(w, "10");
  await page.press(w, "Enter");
  await waitPkg(page, dir, (p) => editOf(p, "width"), "правка width");
  assert.equal(editOf(pkg(dir), "width").to, "0px");
});

test("R4. багатовластивісний запис атомарний: збій третьої властивості відкочує перші дві", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#nb");
  await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    const orig = api.applyTune.bind(api);
    api.applyTune = (p, v) => (p === "border-color" ? false : orig(p, v));
  });
  await page.click('#insp-panel [data-act="inspadd"][data-val="stroke"]');
  await page.waitForTimeout(400);
  const left = await page.frameLocator("#frame").locator("#nb").evaluate((e) => e.getAttribute("style"));
  assert.ok(!/border/.test(left || ""), `на макеті лишився інлайн: ${left}`);
  const p = pkg(dir);
  const props = p ? (p.elements || []).flatMap((e) => e.edits).map((e) => e.prop) : [];
  assert.deepEqual(props.filter((x) => x.startsWith("border")), [], "у пакеті нічого від дії не лишилось");
});

test("R5. Alt у полі вводу всередині макета не вмикає лінії", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.frameLocator("#frame").locator("#inp").focus();
  await page.keyboard.down("Alt");
  const alt = await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector.alt);
  await page.keyboard.up("Alt");
  assert.equal(alt, false);
});

test("R6. Shift+← → не навігують (ні в рамці, ні з фокусом в оболонці)", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.keyboard.press("Shift+ArrowRight");
  assert.equal(await pinnedId(page), "a", "рамка: Shift+→ — не сусід");
  await page.locator("#insp-panel .insp-top").click();
  await page.keyboard.press("Shift+ArrowRight");
  assert.equal(await pinnedId(page), "a", "оболонка: Shift+→ — не сусід");
  await page.keyboard.press("ArrowRight");
  assert.equal(await pinnedId(page), "b", "без Shift — сусід");
});

test("G1. «+» біля обведення без border → три довгі властивості в пакеті й рамка 1px solid", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#nb");
  await page.click('#insp-panel [data-act="inspadd"][data-val="stroke"]');
  const p = await waitPkg(page, dir, (x) => editOf(x, "border-style") && editOf(x, "border-width") && editOf(x, "border-color"), "три правки");
  assert.equal(editOf(p, "border-style").to, "solid");
  assert.equal(editOf(p, "border-width").to, "1px");
  assert.match(editOf(p, "border-color").to, /^#[0-9a-f]{6}$/i);
  const cs = await page.frameLocator("#frame").locator("#nb").evaluate((e) => { const c = getComputedStyle(e); return [c.borderTopWidth, c.borderTopStyle]; });
  assert.deepEqual(cs, ["1px", "solid"]);
});

test("G2. матриця вирівнювання пише justify-content/align-items; напрям column перемапує матрицю", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  await page.click('#insp-panel [data-act="inspalign"][data-val="2,1"]');
  let p = await waitPkg(page, dir, (x) => editOf(x, "justify-content") && editOf(x, "align-items"), "дві правки");
  assert.equal(editOf(p, "justify-content").to, "flex-end");
  assert.equal(editOf(p, "align-items").to, "center");
  await page.click('#insp-panel [data-act="inspdir"][data-val="column"]');
  p = await waitPkg(page, dir, (x) => editOf(x, "flex-direction")?.to === "column", "flex-direction");
  assert.equal(await page.locator('#insp-panel [data-act="inspalign"][data-val="1,2"]').getAttribute("aria-pressed"), "true",
    "у column головна вісь — вертикаль: вибір (2,1) перейшов у (1,2)");
  await page.click('#insp-panel [data-act="inspalign"][data-val="2,0"]');
  p = await waitPkg(page, dir, (x) => editOf(x, "justify-content")?.to === "flex-start", "column: justify = верх");
  assert.equal(editOf(p, "align-items").to, "flex-end", "column: align = право");
});

test("G3. колір у «Заливка»: hex + Enter пише background-color", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  const f = '#insp-panel .insp-f[data-prop="background-color"] .insp-fi';
  await page.fill(f, "#112233");
  await page.press(f, "Enter");
  const p = await waitPkg(page, dir, (x) => editOf(x, "background-color"), "background-color");
  assert.equal(editOf(p, "background-color").to.toLowerCase(), "#112233");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((e) => getComputedStyle(e).backgroundColor), "rgb(17, 34, 51)");
});

/* ── Мутації (кожна знята: прибери запобіжник — перевірка червоніє) ─────────────────────────────────────────────────
 *  1   handleKey Esc → `nextPin`/`_setPin` в `inspector.js`; прибери `_setPin(step.pin, true)` — Esc нічого не піднімає.
 *  1b  `inspShellKey` в `app.js`; прибери `document.addEventListener('keydown', inspShellKey)` — фокус в оболонці глухий.
 *  1c  `api.yieldEsc` у `load`-обробнику `app.js`; прибери рядок — Esc піднімає вибір попри питання.
 *  2   `setAlt`/`_draw` + `keyup`/`blur` у `init()`; прибери `window.addEventListener('blur', …)` — лінії лишаються.
 *  3   `inspStep` + `tuneWrite`; Shift-множник `(ev.shiftKey ? 10 : 1)` у keydown-слухачі панелі.
 *  3b  `tuneWrite(props.map(…))` в `inspCommit`; лиши лише `props[0]` — `padding-right` не пишеться.
 *  4   `inspScrubApply` з `{ save: false }` і `if (s.applied !== undefined) saveTune()` у `inspScrubEnd`; прибери
 *      `{ save: false }` — POST на кожен кадр, `posts.length` > 1; прибери `if (inspScrub) return;` у `paintInsp` —
 *      зникає `data-keep` (панель перемалювалась під час жесту).
 *  7   `tuneReady` → `markReady`; лишається з T-39.
 *  8   прибери `_onKey`-видалення M: поверни `toggleMode` — `api.mode` перестає бути `undefined`.
 */
