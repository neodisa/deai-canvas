/**
 * Живі перевірки пінів на «Огляді» (T-45): справжній сервер, справжній Chromium,
 * справжня зʼємка з геометрією, справжній comment-layer у режимі «полотно».
 *
 * Мапа «перевірка → запобіжник», знята мутаційно (прибери охорону — подивись,
 * чи червоніє). Без неї «зелено» не означає нічого:
 *
 *   A (паритет алгоритму) — `findMatchIn` у `comment-layer/src/anchor.js`.
 *        Мутація «вага шляху 0.25 → 0.3» червонить A.
 *   B (пін на елементі)   — `PIN_OFFSET` і формула екрана в `overview-pins.js`.
 *        Мутація «PIN_OFFSET → 0» червонить B.
 *   C (кластер)           — `clustered` у `layoutPins` (межа — юніт overview-pins D).
 *   D (пін → картка)      — ранній return на `[data-comment-layer]` у
 *        `pointerdown` (`app.js`). Мутація «прибрати» червонить D: пастка
 *        `setPointerCapture`, тому натискання — `mouse.down/up`, а НЕ
 *        `locator.click()`, який бреше.
 *   E (картка → переліт)  — `_focusElement` → `anchors.reveal` (comment-layer).
 *   F (колесо)            — фільтр `composedPath()[0].closest('.cp')` у `wheel`.
 *        Мутація «прибрати фільтр» червонить F (колесо над панеллю зумило б
 *        полотно); «ігнорувати весь шар» — теж F (пін крав би колесо).
 *        ⚠️ Перша редакція F зеленіла під мутацією: панель ще виїжджала, точка
 *        лягала за край вікна. Тепер крок доводить, що точка — НА панелі.
 *   G (прихований iframe мовчить) — `hiddenFrame()` у `_keyHandler`
 *        comment-layer. Мутація «прибрати» червонить G.
 *   H (живий вид без змін) — DOM-режим comment-layer.
 *   I (лічильник на ручці) — `this.anchors ? open.length` у `_render`.
 *   J (шапка панелі під смугою) — `--cl-top` від `anchors.top()`. Мутація
 *        «не писати змінну» червонить J.
 *   K (створення на «Огляді», етап 2) — `!commentArmed` у pointerup (інакше клік
 *        відкриває кадр), `enrich` (HTML), `cropShot` (скриншот), частка кліку
 *        `targetFor`, права межа композера. Кожна мутація червонить K.
 *   L (панорама в режимі коментування) — поріг руху в `_canvasClick`.
 *   M (поза кадром) — `null`-гілка `layoutPins` + `off` у comment-layer.
 *   N (D1) — спільний `inflight` в `ensure` (рахунок підйомів) + друга лінія
 *        `if (cl) destroy()` перед `init` (рахунок хостів). ⚠️ Перша редакція N
 *        зеленіла без `inflight`: друга лінія маскувала першу.
 *   O (D2) — `refresh` на `enter`. Мутація «без refresh» червонить O.
 *   P (D3) — `_armComment(false)` у `destroy`. Мутація червонить P.
 *   Q (D4) — `elementFromPoint(...)` у `hit`: смугу відсікає `canvasEl.contains`
 *        (Q), панель оболонки ВСЕРЕДИНІ полотна — `.closest('.cv-card-body')` (Q2).
 *        ⚠️ Перша редакція Q зеленіла: під кнопкою не було кадру; мутація «лише
 *        .closest» виживала, доки не зʼявився Q2 (повторне ревʼю).
 *   R (NEW-1) — `if (!shot) return undefined` у `geoOf`. Мутація «null» червонить R.
 *   S (NEW-3) — `retryAt` + таймер повтору. Обидві мутації червонять S.
 */
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import test from "node:test";

// 4d-4b: кеш браузерів Playwright читається при ІМПОРТІ playwright — `_env.mjs` мусить бути раніше за нього
import "./_env.mjs";
import { chromium } from "playwright";

import { CLUSTER_W } from "../../app/overview-pins.js";
import { MODULE_ADAPTER_GLOB, hermeticLiga } from "./_liga-supabase.mjs";
import { startServer } from "./fixture.mjs";
import { ANCHOR, TARGETS, seedPins, shootAll, t45Task } from "./_t45-fixture.mjs";

const PORT_BASE = 12090;
const VIEW = { width: 1440, height: 900 };
const SHOTS = process.env.T45_SHOTS || "";   // тека для скриншотів у звіт (необовʼязково)

let server, browser, comments;

test.before(async () => {
  const { dir } = t45Task();
  server = await startServer(dir, { portBase: PORT_BASE, title: "T-45", supabase: true });
  browser = await chromium.launch();
  comments = await seedPins(browser, server.url);
  const shot = await shootAll(server.url);
  assert.ok(shot.ok, `зʼємка: ${JSON.stringify(shot).slice(0, 400)}`);
});

test.after(async () => {
  await browser?.close();
  server?.child.kill();
});

/** Справжнє натискання: `mouse.down/up`, не `locator.click()` — див. шапку. */
async function pressAt(page, x, y) {
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.up();
}

async function overview() {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${server.url}/app/`);
  // рамка живого виду встигає підняти свій comment-layer — G перевіряє, що він мовчить
  await page.waitForFunction(() => {
    const w = document.getElementById("frame")?.contentWindow;
    return Boolean(w && w.CommentLayer && w.CommentLayer._inited);
  }, null, { timeout: 20000 });
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  await page.waitForFunction(() => {
    const h = document.querySelector("#canvas [data-comment-layer]");
    return Boolean(h && h.shadowRoot && h.shadowRoot.querySelectorAll(".cp").length);
  }, null, { timeout: 20000 });
  return page;
}

/** Піни полотна з shadow root: ключ, ідентифікатори, кластер, центр кружка. */
const pinsOf = (page) => page.evaluate(() => {
  const root = document.querySelector("#canvas [data-comment-layer]").shadowRoot;
  return [...root.querySelectorAll(".cp")].map((w) => {
    const r = w.firstChild.getBoundingClientRect();
    return { key: w._item.key, ids: w._item.ids, cluster: w._item.cluster, off: w._item.off, vis: w._item.vis,
             text: w.firstChild.textContent, cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
  });
});

/** Камера з трансформу світу — рівно те, що бачить людина. */
const camOf = (page) => page.evaluate(() => {
  const m = /translate\(([-\d.e]+)px,\s*([-\d.e]+)px\)\s*scale\(([-\d.e]+)\)/.exec(document.getElementById("world").style.transform);
  const c = document.getElementById("canvas").getBoundingClientRect();
  return { x: +m[1], y: +m[2], scale: +m[3], left: c.left, top: c.top, w: c.width, h: c.height };
});

async function settleCam(page) {
  /* Спершу пауза: переліт стартує з наступного кадру після кліку, і два перші
     замiри «до старту» однакові — без паузи функція рапортувала б «стала» ще до
     того, як камера рушила (так і впала перша редакція E). */
  await page.waitForTimeout(150);
  let prev = null;
  for (let i = 0; i < 40; i += 1) {
    const c = await camOf(page);
    if (prev && Math.abs(c.x - prev.x) < 0.5 && Math.abs(c.y - prev.y) < 0.5 && Math.abs(c.scale - prev.scale) < 1e-4) return c;
    prev = c;
    await page.waitForTimeout(60);
  }
  return prev;
}

test("A: findMatchIn по геометрії вибирає ТОЙ САМИЙ елемент, що findMatch по DOM — для кожного", async () => {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  for (const pid of Object.keys(TARGETS)) {
    await page.goto(`${server.url}/commented?it=it1&page=${pid}&bare=1`);
    await page.addScriptTag({ content: ANCHOR });
    const diff = await page.evaluate(() => {
      const A = window.CommentLayerAnchor, body = document.body;
      const geo = A.geometry(body).els;
      const bad = [];
      for (const el of body.querySelectorAll("*")) {
        const fp = A.fingerprint(el, body);
        const dom = A.findMatch(fp, body);
        const g = A.findMatchIn(fp, geo);
        const a = dom.el ? A.tagPath(dom.el, body).join(">") : null;
        const b = g.i >= 0 ? geo[g.i].path.join(">") : null;
        if (a !== b || Math.abs(dom.score - g.score) > 1e-9) bad.push({ a, b, sa: dom.score, sb: g.score });
      }
      return bad;
    });
    assert.deepEqual(diff, [], `${pid}: розбіжність DOM ↔ геометрія`);
  }
  await page.close();
});

/* Колесо в «Огляді» (0.25.0): просто колесо РУХАЄ полотно, а масштабує ⌘ + колесо (Ctrl — щипок — підсилюється ×6, тому ⌘). */
async function zoomWheel(page, dx, dy) {
  await page.keyboard.down("Meta");
  try { await page.mouse.wheel(dx, dy); } finally { await page.keyboard.up("Meta"); }
}

test("B: пін стоїть на своєму елементі — кут +10/+10 з геометрії кадру, за будь-якого зуму", async () => {
  const page = await overview();
  const cam = await settleCam(page);
  assert.ok(1280 * cam.scale >= CLUSTER_W, `фікстура мусить бути поза кластером (масштаб ${cam.scale})`);
  const pins = await pinsOf(page);
  const single = pins.filter((p) => !p.cluster && !p.off);
  // «привид» (елемента нема) на кадрі не стоїть — він у лічильнику «поза кадром» (M)
  assert.equal(single.length, comments.length - 1, "кожен посіяний пін має стояти на полотні");
  const expected = await page.evaluate(async (list) => {
    const A = window.CommentLayerAnchor;
    const out = {};
    for (const c of list) {
      if (c.id === "t45-ghost") continue;
      const pid = c.meta.version.split("/")[1];
      const g = await (await fetch(`/shot-geo?it=it1&node=${pid}`)).json();
      const e = g.els[A.findMatchIn(c.fp, g.els).i];
      const card = document.querySelector(`.cv-card[data-key="${pid}"]`);
      out[c.id] = { x: parseFloat(card.style.left) + e.x + 10, y: parseFloat(card.style.top) + 34 + e.y + 10 };
    }
    return out;
  }, comments);
  const check = (cm, list) => {
    for (const p of list) {
      const w = expected[p.ids[0]];
      const ex = cm.left + cm.x + w.x * cm.scale, ey = cm.top + cm.y + w.y * cm.scale;
      assert.ok(Math.abs(p.cx - ex) <= 2 && Math.abs(p.cy - ey) <= 2,
        `${p.ids[0]}: пін (${p.cx.toFixed(1)},${p.cy.toFixed(1)}) ≠ елемент (${ex.toFixed(1)},${ey.toFixed(1)})`);
    }
  };
  check(cam, single.filter((p) => p.vis));
  if (SHOTS) { mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: `${SHOTS}/overview-pins.png` }); }
  // Зум колесом — піни їдуть разом із кадрами, а не лишаються на старих місцях.
  await page.mouse.move(700, 400);
  for (let i = 0; i < 4; i += 1) await zoomWheel(page, 0, -120);
  const cam2 = await settleCam(page);
  assert.ok(cam2.scale > cam.scale * 1.3, "зум не відбувся");
  check(cam2, (await pinsOf(page)).filter((p) => !p.cluster && !p.off && p.vis));
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/overview-pins-zoom.png` });
  await page.close();
});

test("C: на дрібному зумі піни злипаються в лічильник на кадр; клік — переліт до кадру", async () => {
  const page = await overview();
  await page.mouse.move(700, 400);
  for (let i = 0; i < 30; i += 1) await zoomWheel(page, 0, 120);
  const cam = await settleCam(page);
  assert.ok(1280 * cam.scale < CLUSTER_W, `не віддалились (масштаб ${cam.scale})`);
  const pins = await pinsOf(page);
  const byPage = Object.fromEntries(pins.map((p) => [p.key, p]));
  assert.ok(pins.every((p) => p.cluster || p.off), "на дрібному зумі — лише лічильники");
  assert.equal(byPage["k:holovna"]?.text, String(TARGETS.holovna.length));
  assert.equal(byPage["k:poshuk"]?.text, String(TARGETS.poshuk.length));
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/overview-clusters.png` });
  const k = byPage["k:holovna"];
  await pressAt(page, k.cx, k.cy);
  const after = await settleCam(page);
  assert.ok(after.scale > cam.scale * 2, "клік по лічильнику не наблизив кадр");
  await page.close();
});

test("D+E: клік по піну відкриває картку; клік по картці — переліт камери до піна", async () => {
  const page = await overview();
  const pin = (await pinsOf(page)).find((p) => !p.cluster && p.vis && p.ids[0] === "t45-holovna-2");
  assert.ok(pin, "пін кнопки «Підписатися» не на екрані");
  await pressAt(page, pin.cx, pin.cy);
  const opened = await page.evaluate((id) => {
    const root = document.querySelector("#canvas [data-comment-layer]").shadowRoot;
    return { panel: root.querySelector(".panel").classList.contains("show"),
             flash: root.querySelector(`#c${id}`)?.classList.contains("flash") };
  }, pin.ids[0]);
  assert.deepEqual(opened, { panel: true, flash: true }, "клік по піну не дійшов до панелі");
  // Панель виїжджає переходом — міряти картку до кінця виїзду означає цілитись
  // у точку за правим краєм вікна (так і впала перша редакція цього кроку).
  await page.waitForTimeout(450);
  // Картка ІНШОГО піна (сторінка «Пошук») — переліт через пів полотна.
  const target = "t45-poshuk-1";
  const box = await page.evaluate((id) => {
    const el = document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(`#c${id} .who`);
    el.scrollIntoView({ block: "center" });   // картка могла бути за прокруткою списку
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }, target);
  await pressAt(page, box.x, box.y);
  const cam = await settleCam(page);
  assert.ok(cam.scale >= 0.5 - 1e-6, `переліт лишив дрібний масштаб ${cam.scale}`);
  const p = (await pinsOf(page)).find((x) => x.ids[0] === target && !x.cluster);
  const cx = cam.left + cam.w / 2, cy = cam.top + cam.h / 2;
  assert.ok(p && Math.abs(p.cx - cx) <= 40 && Math.abs(p.cy - cy) <= 40,
    `пін після перельоту не в центрі: ${p && `${p.cx.toFixed(0)},${p.cy.toFixed(0)}`} проти ${cx},${cy}`);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/overview-reveal.png` });
  await page.close();
});

test("F: колесо над піном зумить полотно; над списком панелі — ні", async () => {
  const page = await overview();
  const pin = (await pinsOf(page)).find((p) => !p.cluster && !p.off && p.vis);
  const before = (await settleCam(page)).scale;
  await page.mouse.move(pin.cx, pin.cy);
  await zoomWheel(page, 0, -120);
  const mid = (await settleCam(page)).scale;
  assert.ok(mid > before * 1.05, "колесо над піном не дійшло до полотна");
  await page.keyboard.press("p");   // панель коментатора полотна
  await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]")
    .shadowRoot.querySelector(".panel").classList.contains("show"));
  // Панель виїжджає переходом. Без паузи точка лягала за правий край вікна, колесо
  // крутилось у порожнечі, і перевірка зеленіла навіть без фільтра колеса — її
  // власна мутація це й показала. Тому ще й доводимо, що точка — НА панелі.
  await page.waitForTimeout(450);
  const list = await page.evaluate(() => {
    const host = document.querySelector("#canvas [data-comment-layer]");
    const r = host.shadowRoot.querySelector(".list").getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + 60;
    return { x, y, onPanel: document.elementFromPoint(x, y) === host && x < innerWidth };
  });
  assert.ok(list.onPanel, `точка колеса не на панелі: ${JSON.stringify(list)}`);
  await page.mouse.move(list.x, list.y);
  await zoomWheel(page, 0, 120);
  const after = (await settleCam(page)).scale;
  assert.equal(after, mid, "колесо над панеллю зумнуло полотно");
  await page.close();
});

test("G: на «Огляді» клавіші бере коментатор полотна, а прихований живий iframe мовчить", async () => {
  const page = await overview();
  await page.mouse.move(700, 450);
  await page.keyboard.press("p");
  const st = await page.evaluate(() => ({
    canvas: document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(".panel").classList.contains("show"),
    frame: document.getElementById("frame").contentWindow.CommentLayer._panel.classList.contains("show"),
  }));
  assert.deepEqual(st, { canvas: true, frame: false });
  await page.close();
});

test("I: лічильник на ручці коментатора — усі відкриті піни ітерації, а не «цього маршруту»", async () => {
  // Оболонка живе на `/app/`, піни народжені на `/commented`: рахунок по маршруту
  // давав 0 при восьми пінах на полотні (знайдено скриншотом першого прогону).
  const page = await overview();
  const n = await page.evaluate(() => document.querySelector("#canvas [data-comment-layer]")
    .shadowRoot.querySelector(".cbadge").textContent);
  assert.equal(n, String(comments.length));
  await page.close();
});

test("J: шапка панелі коментатора — під смугою оболонки, а не під нею сховано", async () => {
  // Панель прибита до верху вікна; в оболонці це верх СМУГИ. Знайдено живим
  // оглядом на boss-interface: вкладки «Клод/Команда» й ✕ були недосяжні.
  const page = await overview();
  await page.keyboard.press("p");
  await page.waitForTimeout(450);
  const r = await page.evaluate(() => {
    const head = document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(".panel .head");
    const h = head.getBoundingClientRect();
    return { head: h.top, canvas: document.getElementById("canvas").getBoundingClientRect().top,
             hit: document.elementFromPoint(h.left + 12, h.top + h.height / 2)?.hasAttribute?.("data-comment-layer") };
  });
  assert.ok(r.head >= r.canvas - 0.5, `шапка панелі вище полотна: ${JSON.stringify(r)}`);
  assert.equal(r.hit, true, "шапку панелі накриває смуга оболонки");
  await page.close();
});

test("H: живий вид сторінки — піни DOM-режиму на місці, як до T-45", async () => {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${server.url}/app/`);
  const n = await page.waitForFunction(() => {
    const w = document.getElementById("frame")?.contentWindow;
    const cl = w && w.CommentLayer;
    if (!cl || !cl._inited) return false;
    const pins = cl._pins.querySelectorAll(".pin").length;
    return pins || false;
  }, null, { timeout: 20000 });
  assert.equal(await n.jsonValue(), TARGETS.holovna.length);
  await page.close();
});

/* ── Етап 2: створення на «Огляді». ОСТАННІМИ у файлі: K додає пін у спільну
   фікстуру, а I/H вище рахують посіяні. ──────────────────────────────────── */

/** Екранна точка частки (fx,fy) елемента `sel` сторінки `pid` на полотні. */
async function pointOf(page, pid, sel, fx, fy) {
  // відбиток цілі — справжній, із bare-сторінки
  const bare = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await bare.goto(`${server.url}/commented?it=it1&page=${pid}&bare=1`);
  await bare.addScriptTag({ content: ANCHOR });
  const fp = await bare.evaluate((s) => window.CommentLayerAnchor.fingerprint(document.querySelector(s), document.body), sel);
  await bare.close();
  const at = await page.evaluate(async ({ pid, fp, fx, fy }) => {
    const A = window.CommentLayerAnchor;
    const g = await (await fetch(`/shot-geo?it=it1&node=${pid}`)).json();
    const e = g.els[A.findMatchIn(fp, g.els).i];
    const card = document.querySelector(`.cv-card[data-key="${pid}"]`);
    const m = /translate\(([-\d.e]+)px,\s*([-\d.e]+)px\)\s*scale\(([-\d.e]+)\)/.exec(document.getElementById("world").style.transform);
    const c = document.getElementById("canvas").getBoundingClientRect();
    const s = +m[3], ox = c.left + +m[1], oy = c.top + +m[2];
    const L = parseFloat(card.style.left), T = parseFloat(card.style.top) + 34;
    return { x: ox + (L + e.x + fx * e.w) * s, y: oy + (T + e.y + fy * e.h) * s,
             rect: { left: ox + (L + e.x) * s, top: oy + (T + e.y) * s, width: e.w * s, height: e.h * s } };
  }, { pid, fp, fx, fy });
  return { ...at, fp };
}

const shadow = (page, fn, arg) => page.evaluate(([src, a]) => {
  const root = document.querySelector("#canvas [data-comment-layer]").shadowRoot;
  return new Function("root", "a", src)(root, a);   // eslint-disable-line no-new-func
}, [fn, arg]);

test("K: коментар на «Огляді» — підсвітка, клік, композер, пін у точці кліку; у живому виді той самий", async () => {
  const page = await overview();
  await settleCam(page);
  await page.mouse.move(700, 450);
  await page.keyboard.press("c");
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), true,
    "режим коментування не ввімкнувся");
  await page.waitForTimeout(450);   // панель виїхала — не накриває кадр
  const tgt = await pointOf(page, "holovna", ".card:nth-child(3) h2", 0.3, 0.5);
  await page.mouse.move(tgt.x, tgt.y);
  await page.waitForTimeout(80);
  const hov = await shadow(page, "const b = root.querySelector('.clhov'); if (!b || b.style.display === 'none') return null; const r = b.getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height };");
  assert.ok(hov, "наведення не підсвітило елемент");
  for (const k of ["left", "top", "width", "height"]) {
    assert.ok(Math.abs(hov[k] - tgt.rect[k]) <= 2, `рамка наведення ${k}: ${hov[k].toFixed(1)} ≠ ${tgt.rect[k].toFixed(1)}`);
  }
  /* Події миші несуть ЦІЛІ екранні координати: клік у дробову точку Chrome округлює вниз, і на низькому елементі (тут ~9 екранних
     пікселів) частка кліку їде на ~0.1. Тож клікаємо в цілий піксель і чекаємо частку САМЕ цього пікселя (допуск 0.03 лишився). */
  const cx = Math.round(tgt.x), cy = Math.round(tgt.y);
  const want = { fx: (cx - tgt.rect.left) / tgt.rect.width, fy: (cy - tgt.rect.top) / tgt.rect.height };
  await pressAt(page, cx, cy);
  assert.equal(await page.evaluate(() => document.getElementById("canvas").hidden), false, "клік відкрив кадр замість коментаря");
  assert.ok(await shadow(page, "return !!root.querySelector('.compose textarea');"), "композер не відкрився");
  await page.keyboard.type("Правка з Огляду: заголовок третьої картки");
  const save = await shadow(page, "const r = root.querySelector('.compose .save').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 };");
  await pressAt(page, save.x, save.y);
  // Пін — у файлі каналу, після збагачення (HTML) і скриншота
  let mine = null;
  for (let i = 0; i < 60 && !(mine && mine.htmlSnapshot?.outerHTML); i += 1) {
    const list = (await (await fetch(`${server.url}/api/local-comments`)).json()).comments;
    mine = list.find((c) => c.text === "Правка з Огляду: заголовок третьої картки") || null;
    if (!(mine && mine.htmlSnapshot?.outerHTML)) await page.waitForTimeout(250);
  }
  assert.ok(mine, "коментар не доїхав до файлу каналу");
  assert.deepEqual(mine.fp, tgt.fp, "відбиток ≠ живому fingerprint того самого елемента");
  assert.equal(mine.meta.version, "1/holovna");
  assert.match(mine.meta.url, /\/commented\?it=it1&page=holovna&ch=local$/);
  assert.equal(mine.meta.via, "overview");
  assert.ok(Math.abs(mine.meta.anchor.fx - want.fx) < 0.03 && Math.abs(mine.meta.anchor.fy - want.fy) < 0.03,
    `частка кліку ${JSON.stringify(mine.meta.anchor)}`);
  assert.match(mine.htmlSnapshot.outerHTML, /^<h2[\s>]/, "HTML елемента не дописано");
  assert.match(mine.meta.shot || "", /^data:image\/jpeg/, "скриншот не вирізано з кадру");
  // Пін стоїть у точці кліку
  const pin = (await pinsOf(page)).find((p) => p.ids[0] === mine.id && !p.cluster);
  assert.ok(pin && Math.abs(pin.cx - cx) <= 2 && Math.abs(pin.cy - cy) <= 2,
    `пін не в точці кліку: ${pin && `${pin.cx.toFixed(1)},${pin.cy.toFixed(1)}`} проти ${tgt.x.toFixed(1)},${tgt.y.toFixed(1)}`);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/overview-create.png` });
  // Живий вид: той самий пін на тому самому елементі
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Макет/ }).click();
  const el = await page.waitForFunction((id) => {
    const w = document.getElementById("frame")?.contentWindow;
    const cl = w && w.CommentLayer;
    const c = cl && cl._inited && cl.comments.find((x) => x.id === id);
    return c && c._el ? c._el.textContent.trim() : false;
  }, mine.id, { timeout: 20000 });
  assert.equal(await el.jsonValue(), "Матеріал 3");
  await page.close();
});

test("L: у режимі коментування перетягування панорамує (без композера), Esc знімає режим", async () => {
  const page = await overview();
  const before = await settleCam(page);
  await page.mouse.move(700, 450);
  await page.keyboard.press("c");
  await page.waitForTimeout(450);
  const tgt = await pointOf(page, "poshuk", "ol li:nth-child(3)", 0.5, 0.5);
  await page.mouse.move(tgt.x, tgt.y);
  await page.mouse.down();
  for (let i = 1; i <= 12; i += 1) await page.mouse.move(tgt.x - i * 10, tgt.y - i * 6);
  await page.mouse.up();
  const after = await settleCam(page);
  assert.ok(Math.abs(after.x - before.x) > 50, "перетягування не зсунуло полотно");
  assert.equal(await shadow(page, "return !!root.querySelector('.compose');"), false, "після панорами відкрився композер");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), false,
    "Esc не зняв режим коментування");
  await page.close();
});

/* ── Ревʼю T-45: D1–D4 і D7. Після K/L — деякі пишуть у спільну фікстуру. ── */

/** Заглушка supabase-js ДО завантаження сторінки: канал «Команда» піднімається без мережі й без справжньої бази; записи
 *  збираються у `window.__sbWrites`. Від 4b-2 канал «Команда» ЛІГИ — це адаптер модуля `supabase-comments` (його
 *  `adapter.js` справжній, він кличе `window.supabase.createClient`), тож заглушка лишилась тією самою, а справжній
 *  `supabase.min.js` модуля підмінено порожнім файлом, щоб він її не затер. Конфіг Supabase ЛІГИ — у `tasks.json` фікстури
 *  (`supabase: true`); усе за межі машини `abort`-иться й складається в `.outside` (тест мусить лишити його порожнім). */
async function withSupabaseStub(page) {
  const seen = await hermeticLiga(page);
  await page.route(MODULE_ADAPTER_GLOB.replace("adapter.js", "supabase.min.js"), (route) => route.fulfill({
    status: 200, contentType: "application/javascript", body: "" }));
  await page.addInitScript(() => {
    window.__sbWrites = []; window.__sbClosed = 0;
    window.supabase = { createClient: () => {
      const q = { select() { return q; }, eq() { return q; }, in() { return q; }, delete() { return q; },
        order() { return Promise.resolve({ data: [], error: null }); },
        upsert: async (rows) => { window.__sbWrites.push(...rows); return { error: null }; } };
      return { from: () => q, channel: () => ({ on() { return this; }, subscribe() { return this; } }),
               removeChannel: () => { window.__sbClosed += 1; } };
    } };
  });
  return seen;
}
const hosts = (page) => page.evaluate(() => document.querySelectorAll("#canvas [data-comment-layer]").length);
async function switchAudience(page, id) {
  if (!(await shadow(page, "return root.querySelector('.panel').classList.contains('show');"))) {
    await page.mouse.move(700, 450); await page.keyboard.press("p"); await page.waitForTimeout(450);
  }
  const b = await shadow(page, `const r = root.querySelector('[data-aud="${id}"]').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 };`);
  await pressAt(page, b.x, b.y);
  await page.waitForFunction(() => {
    const hs = document.querySelectorAll("#canvas [data-comment-layer]");
    return hs.length === 1 && hs[0].shadowRoot.querySelector(".handle");
  }, null, { timeout: 20000 });
  await page.waitForTimeout(300);
}

test("M: пін без місця на кадрі — лічильник «поза кадром: 1» над кадром; клік — панель на ньому", async () => {
  const page = await overview();
  await settleCam(page);
  const off = (await pinsOf(page)).find((p) => p.off);
  assert.ok(off, "лічильника «поза кадром» немає");
  assert.equal(off.key, "o:holovna");
  assert.deepEqual(off.ids, ["t45-ghost"]);
  assert.equal(off.text, "поза кадром: 1");
  await pressAt(page, off.cx, off.cy);
  await page.waitForTimeout(100);
  const st = await shadow(page, "return { panel: root.querySelector('.panel').classList.contains('show'), flash: root.querySelector('#ct45-ghost')?.classList.contains('flash') };");
  assert.deepEqual(st, { panel: true, flash: true });
  await page.close();
});

test("N (D1): перемикання каналу на «Огляді» лишає ОДИН інстанс, і коментар «Клоду» йде у файл, а не в «Команду»", async () => {
  const page = await browser.newPage({ viewport: VIEW });
  const net = await withSupabaseStub(page);
  /* Скільки разів піднімали інстанс — по запитах конфігу каналу. Самого числа
     хостів мало: друга лінія (`if (cl) destroy()` перед `init`) прибирає дубль
     у кінці, і перевірка «один хост» зеленіла навіть без `inflight`. Лишні
     підйоми — це й є вада: подвійна мережа, два клієнти Supabase, вікно, коли
     інстансів два (мутаційно). */
  let configs = 0;
  page.on("request", (r) => { if (new URL(r.url()).pathname === "/api/comment-config") configs += 1; });
  await page.goto(`${server.url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]")?.shadowRoot?.querySelector(".handle"));
  assert.equal(configs, 1, `вхід у «Огляд» підняв інстанс ${configs} рази`);
  await switchAudience(page, "project");
  await switchAudience(page, "local");
  await switchAudience(page, "project");
  await switchAudience(page, "local");
  assert.equal(await hosts(page), 1, "після чотирьох перемикань — не один інстанс");
  assert.equal(configs, 5, `на 4 перемикання — ${configs - 1} підйомів інстансу замість 4`);
  assert.ok(await page.evaluate(() => window.__sbClosed) >= 2, "realtime-канал «Команди» не закрито при знищенні (TD-27)");
  const styles = await page.evaluate(() => [...document.head.querySelectorAll("style")].filter((x) => x.textContent.includes(".cl-hl")).length);
  assert.equal(styles, 1, `стилів коментатора в head: ${styles}`);
  // коментар у каналі «Клод»
  await page.keyboard.press("Escape");
  await page.mouse.move(700, 450);
  await page.keyboard.press("c");
  await page.waitForTimeout(450);
  const tgt = await pointOf(page, "poshuk", "ol li:nth-child(4)", 0.5, 0.5);
  await page.mouse.move(tgt.x, tgt.y); await page.waitForTimeout(60);
  await pressAt(page, tgt.x, tgt.y);
  await page.keyboard.type("D1: коментар Клоду");
  const save = await shadow(page, "const r = root.querySelector('.compose .save').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 };");
  await pressAt(page, save.x, save.y);
  let mine = null;
  for (let i = 0; i < 60 && !mine; i += 1) {
    mine = (await (await fetch(`${server.url}/api/local-comments`)).json()).comments.find((c) => c.text === "D1: коментар Клоду") || null;
    if (!mine) await page.waitForTimeout(250);
  }
  assert.ok(mine, "коментар «Клоду» не доїхав у локальний файл");
  assert.deepEqual(await page.evaluate(() => window.__sbWrites.map((r) => r.text)), [], "коментар «Клоду» поїхав у «Команду»");
  assert.deepEqual(net.outside, [], `запити за межі машини:\n${net.outside.join("\n")}`);
  await page.close();
});

test("O (D2): пін, лишений у живому виді, видно на «Огляді» після повернення — канал перечитується", async () => {
  const page = await overview();
  const before = await shadow(page, "return root.querySelector('.cbadge').textContent;");
  // запис живого виду — той самий ендпоінт, що бере local-adapter рамки
  const list = (await (await fetch(`${server.url}/api/local-comments`)).json()).comments;
  const src = list.find((c) => c.id === "t45-poshuk-0");
  await fetch(`${server.url}/api/local-comments`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comments: [...list, { ...src, id: "t45-live", text: "лишено в живому виді", meta: { ...src.meta, seq: 999 } }] }) });
  await page.getByRole("button", { name: /Макет/ }).click();
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.waitForFunction((b) => document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(".cbadge").textContent === String(Number(b) + 1), before, { timeout: 10000 });
  await page.close();
});

test("P (D3): перемикання каналу посеред режиму коментування не лишає його «залиплим»", async () => {
  const page = await browser.newPage({ viewport: VIEW });
  await withSupabaseStub(page);
  await page.goto(`${server.url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]")?.shadowRoot?.querySelector(".handle"));
  await page.mouse.move(700, 450);
  await page.keyboard.press("c");
  await page.waitForTimeout(450);
  await switchAudience(page, "project");
  assert.equal(await page.evaluate(() => document.getElementById("canvas").classList.contains("cv-commenting")), false,
    "режим коментування лишився після знищення інстансу");
  // клік по кадру знову відкриває кадр
  const card = await page.evaluate(() => { const r = document.querySelector('.cv-card[data-key="poshuk"] .cv-card-body').getBoundingClientRect(); return { x: r.left + 40, y: r.top + 40 }; });
  await pressAt(page, card.x, card.y);
  await page.waitForFunction(() => document.getElementById("canvas").hidden, null, { timeout: 5000 });
  await page.close();
});

test("Q (D4): у режимі коментування UI оболонки над кадром — не ціль: «Макет» працює, рамки нема", async () => {
  const page = await overview();
  await settleCam(page);
  /* Покласти ТІЛО кадру просто під кнопку «Макет» смуги. Перша редакція
     панорамила лише вгору — під кнопкою кадру не було зовсім, `hit` і без
     перевірки не знаходив цілі, і тест зеленів на мутації (так і знайдено). */
  const btn = await page.getByRole("button", { name: /Макет/ }).boundingBox();
  const bx = btn.x + btn.width / 2, by = btn.y + btn.height / 2;
  const body = await page.evaluate(() => { const r = document.querySelector('.cv-card[data-key="holovna"] .cv-card-body').getBoundingClientRect(); return { x: r.left + 120, y: r.top + 160 }; });
  await page.mouse.move(body.x, body.y); await page.mouse.down();
  for (let i = 1; i <= 12; i += 1) await page.mouse.move(body.x + (bx - body.x) * i / 12, body.y + (by - body.y) * i / 12);
  await page.mouse.up();
  await settleCam(page);
  // доказ, що під кнопкою справді лежить кадр (у світових координатах)
  const under = await page.evaluate(({ x, y }) => {
    const m = /translate\(([-\d.e]+)px,\s*([-\d.e]+)px\)\s*scale\(([-\d.e]+)\)/.exec(document.getElementById("world").style.transform);
    const c = document.getElementById("canvas").getBoundingClientRect();
    const wx = (x - c.left - +m[1]) / +m[3], wy = (y - c.top - +m[2]) / +m[3];
    const card = document.querySelector('.cv-card[data-key="holovna"]');
    const L = parseFloat(card.style.left), T = parseFloat(card.style.top) + 34;
    return wx > L && wx < L + 1280 && wy > T && wy < T + parseFloat(card.style.height);
  }, { x: bx, y: by });
  assert.ok(under, "під кнопкою «Макет» немає кадру — перевірка нічого б не довела");
  await page.keyboard.press("c");
  await page.waitForTimeout(450);
  await page.mouse.move(bx, by);
  await page.waitForTimeout(60);
  assert.equal(await shadow(page, "const b = root.querySelector('.clhov'); return !!b && b.style.display !== 'none';"), false,
    "рамка наведення намалювалась крізь смугу оболонки");
  await pressAt(page, bx, by);
  await page.waitForFunction(() => document.getElementById("canvas").hidden, null, { timeout: 5000 });
  assert.equal(await page.evaluate(() => !!document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelector(".compose")), false,
    "клік по «Макет» відкрив композер");
  await page.close();
});

test("Q2 (D4): панель оболонки ВСЕРЕДИНІ полотна поверх кадру — теж не ціль", async () => {
  /* Смугу вже відсікає `canvasEl.contains`; перевірку `.closest(".cv-card-body")`
     доводить лише те, що лежить у #canvas над кадром (як панель скарг флоу).
     Повторне ревʼю: без цього кроку мутація «лише .closest» виживала. */
  const page = await overview();
  await settleCam(page);
  const box = await page.evaluate(() => {
    const r = document.querySelector('.cv-card[data-key="holovna"] .cv-card-body').getBoundingClientRect();
    const d = document.createElement("div");
    d.id = "cv-flow-problems";
    d.textContent = "скарги флоу";
    d.style.cssText = `position:fixed;left:${r.left + 20}px;top:${r.top + 20}px;width:220px;height:120px;background:#fff;z-index:30`;
    document.getElementById("canvas").appendChild(d);
    return { x: r.left + 120, y: r.top + 80 };
  });
  await page.mouse.move(700, 450);
  await page.keyboard.press("c");
  await page.waitForTimeout(450);
  await page.mouse.move(box.x, box.y);
  await page.waitForTimeout(60);
  assert.equal(await shadow(page, "const b = root.querySelector('.clhov'); return !!b && b.style.display !== 'none';"), false,
    "рамка наведення крізь панель оболонки");
  await pressAt(page, box.x, box.y);
  assert.equal(await shadow(page, "return !!root.querySelector('.compose');"), false, "клік по панелі оболонки відкрив композер");
  await page.close();
});

test("R (NEW-1): поки кадри ще знімаються, «поза кадром» не блимає на заглушках", async () => {
  /* Свіжа задача БЕЗ кадрів: вхід в «Огляд» запускає автозйомку (T-34), і поки
     вона йде, кадру немає. Було: «нема кадру» = «відомо, що місця нема», і на
     заглушках до кінця прогону стояло «поза кадром: 7» (повторне ревʼю). */
  const { dir } = t45Task();
  const srv = await startServer(dir, { portBase: PORT_BASE, title: "T-45 R" });
  try {
    await seedPins(browser, srv.url);
    const page = await browser.newPage({ viewport: VIEW });
    await page.goto(`${srv.url}/app/`);
    await page.getByRole("button", { name: /Огляд/ }).click();
    await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]")?.shadowRoot?.querySelector(".handle"), null, { timeout: 20000 });
    const seen = new Set();
    for (let i = 0; i < 30; i += 1) {
      const texts = await page.evaluate(() => [...document.querySelector("#canvas [data-comment-layer]").shadowRoot
        .querySelectorAll(".pin.off")].map((p) => p.textContent));
      texts.forEach((x) => seen.add(x));
      await page.waitForTimeout(100);
    }
    assert.ok([...seen].every((x) => x === "поза кадром: 1"), `на заглушках блимало: ${[...seen].join(", ")}`);
    await page.close();
  } finally { srv.child.kill(); }
});

test("S (NEW-3): мережевий збій геометрії — не вирок «поза кадром»: повтор сам, піни стають на місце", async () => {
  const page = await browser.newPage({ viewport: VIEW });
  let aborted = 0;
  await page.route("**/shot-geo**", (route) => (aborted < 2 ? (aborted += 1, route.abort("failed")) : route.continue()));
  await page.goto(`${server.url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  const early = await page.evaluate(() => [...document.querySelector("#canvas [data-comment-layer]")?.shadowRoot?.querySelectorAll(".pin.off") || []].map((p) => p.textContent));
  assert.ok(early.every((x) => x === "поза кадром: 1"), `збій мережі дав «поза кадром»: ${early.join(", ")}`);
  await page.waitForFunction(() => [...document.querySelector("#canvas [data-comment-layer]").shadowRoot.querySelectorAll(".cp")]
    .filter((w) => !w._item.off && !w._item.cluster).length >= 8, null, { timeout: 15000 });
  assert.ok(aborted >= 1, "перехоплення не спрацювало — перевірка нічого не довела");
  await page.close();
});

test("T: браузер без prompt() (вбудована панель Electron) — коментар однаково зберігається, автор — особа машини", async () => {
  /* Живий огляд власника 29.09.2026: кнопка «Comment» не робила нічого —
     `getUser` кликав `prompt()`, а вбудований браузер його не підтримує
     (кидає «prompt() is not supported»). Playwright prompt мовчки закриває,
     тому решта тестів цього не бачила. Тут prompt КИДАЄ, як в Electron, і імені
     в localStorage нема — перший коментар на цій адресі. */
  const page = await browser.newPage({ viewport: VIEW });
  await page.addInitScript(() => {
    window.prompt = () => { throw new Error("prompt() is not supported."); };
    try { localStorage.removeItem("comment-layer:user"); } catch (e) { /* немає — і добре */ }
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${server.url}/app/`);
  await page.getByRole("button", { name: /Огляд/ }).click();
  await page.locator(".cv-card img").first().waitFor();
  await page.waitForFunction(() => document.querySelector("#canvas [data-comment-layer]")?.shadowRoot?.querySelector(".handle"));
  await settleCam(page);
  await page.mouse.move(700, 450);
  await page.keyboard.press("c");
  await page.waitForTimeout(450);
  const tgt = await pointOf(page, "holovna", ".card:nth-child(6) h2", 0.4, 0.5);
  await page.mouse.move(tgt.x, tgt.y); await page.waitForTimeout(60);
  await pressAt(page, tgt.x, tgt.y);
  await page.keyboard.type("T: без prompt");
  const save = await shadow(page, "const r = root.querySelector('.compose .save').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 };");
  await pressAt(page, save.x, save.y);
  let mine = null;
  for (let i = 0; i < 60 && !mine; i += 1) {
    mine = (await (await fetch(`${server.url}/api/local-comments`)).json()).comments.find((c) => c.text === "T: без prompt") || null;
    if (!mine) await page.waitForTimeout(250);
  }
  assert.ok(mine, `коментар не збережено; помилки сторінки: ${errors.join(" | ")}`);
  const cfg = await (await fetch(`${server.url}/api/comment-config?ch=local&it=it1`)).json();
  assert.ok(cfg.user && cfg.user.name, "сервер не віддав особу машини");
  assert.equal(mine.author, cfg.user.name, "автор — не особа машини");
  // і живий вид того самого походження бере те саме імʼя
  assert.equal(await page.evaluate(() => localStorage.getItem("comment-layer:user")), cfg.user.name);
  await page.close();
});

test("U: живий вид у браузері без prompt() і без імені — коментар зберігається (охорона prompt у getUser)", async () => {
  /* Рамка особи машини НЕ знає свідомо (сніпет їде в публікацію — ПІБ туди не
     можна), тож тут `getUser` доходить до `prompt()`. Без охорони виняток обривав
     `_addComment`, і коментар не зберігався — той самий симптом, що на «Огляді». */
  const page = await browser.newPage({ viewport: VIEW });
  await page.addInitScript(() => {
    window.prompt = () => { throw new Error("prompt() is not supported."); };
    try { localStorage.removeItem("comment-layer:user"); } catch (e) { /* нема — і добре */ }
  });
  await page.goto(`${server.url}/app/`);
  const frame = await (await page.waitForSelector("#frame")).contentFrame();
  await frame.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  await frame.evaluate(() => window.CommentLayer._addComment(document.querySelector("h1"), "U: DOM без prompt"));
  let mine = null;
  for (let i = 0; i < 60 && !mine; i += 1) {
    mine = (await (await fetch(`${server.url}/api/local-comments`)).json()).comments.find((c) => c.text === "U: DOM без prompt") || null;
    if (!mine) await page.waitForTimeout(250);
  }
  assert.ok(mine, "коментар живого виду не збережено");
  assert.equal(mine.author, "Anonymous");
  await page.close();
});
