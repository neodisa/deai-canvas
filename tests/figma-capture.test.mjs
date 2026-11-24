/**
 * Кнопка «В Figma» (T-41): чиста частина — що помічаємо, в якому порядку
 * діємо на рамку і як читаємо відповідь `capture.js`.
 *
 * Кожна перевірка тут стереже факт, виміряний ЖИВЦЕМ на пілоті 28.09.2026
 * (канвас `fop-check`, справжній Google Chrome), а не здогадку:
 *   - `data-h2d-ignore` діє ЛИШЕ зі значенням `"true"` — порожнє значення
 *     скрипт мовчки ігнорує, і панель коментатора їде у Figma;
 *   - без фокуса на документі макета скрипт висить на «Захоплення…» вічно;
 *   - хости наших оверлеїв у payload стають безіменними DIV — атрибути скрипт
 *     викидає, тож ловити витік треба тут, у переліку, а в живому тесті — за
 *     ТЕКСТОМ оверлеїв.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  CAPTURE_DELAY_MS, CAPTURE_SRC, OVERLAY_SELECTORS, captureErrorKey, captureToFigma,
  loadCapture, markOverlays,
} from "../app/figma-capture.js";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");

/** Документ-підробка: рівно ті методи, які кличе модуль. */
function fakeDoc(hosts = []) {
  const els = hosts.map((sel) => ({ sel, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } }));
  const appended = [];
  const doc = {
    els, appended,
    querySelectorAll: (sel) => els.filter((e) => sel.split(",").includes(e.sel)),
    querySelector: (sel) => appended.find((s) => sel === "script[data-dc-figma]" && s.dataset.dcFigma === "") || null,
    createElement: () => {
      const s = new EventTarget();
      s.dataset = {};
      s.remove = () => { appended.splice(appended.indexOf(s), 1); };
      return s;
    },
    head: { appendChild: (s) => { appended.push(s); } },
  };
  return doc;
}

test("markOverlays ставить data-h2d-ignore=\"true\" — не порожнє значення", () => {
  const doc = fakeDoc(["[data-canvas-inspector]", "[data-comment-layer]", "#cl-down"]);
  assert.equal(markOverlays(doc), 3);
  for (const e of doc.els) assert.equal(e.attrs["data-h2d-ignore"], "true", e.sel);
});

test("мітки помічника макета (data-deai-marks) помічаються як оверлей", () => {
  assert.ok(OVERLAY_SELECTORS.includes("[data-deai-marks]"));
  const doc = fakeDoc(["[data-deai-marks]"]);
  assert.equal(markOverlays(doc), 1);
  assert.equal(doc.els[0].attrs["data-h2d-ignore"], "true");
});

/* Парний інваріант: хост, який канвас кладе в макет, мусить бути в переліку.
   Перейменуй атрибут хоста інспектора чи id банера — і оверлей поїде у Figma
   без жодної помилки; тут це червоне. */
test("кожен хост, який канвас кладе в макет, є в OVERLAY_SELECTORS", () => {
  const src = (f) => readFileSync(path.join(APP, f), "utf8");
  const pairs = [
    ["[data-canvas-inspector]", src("vendor/inspector.js").includes("data-canvas-inspector")],
    ["[data-comment-layer]", src("vendor/comment-layer.min.js").includes("data-comment-layer")],
    ["#cl-down", src("serve.py").includes("d.id = 'cl-down'")],
    ["[data-deai-marks]", src("page-agent.js").includes("data-deai-marks")],
  ];
  for (const [sel, present] of pairs) {
    assert.ok(present, `джерело хоста ${sel} більше його не створює — перевір, як він тепер зветься`);
    assert.ok(OVERLAY_SELECTORS.includes(sel), `${sel} не помічається перед захопленням`);
  }
});

test("captureErrorKey відрізняє відмову буфера від решти", () => {
  assert.equal(captureErrorKey("Clipboard error: Failed to execute 'write' on 'Clipboard': Write permission denied."),
    "figmaErrClipboard");
  assert.equal(captureErrorKey("NotAllowedError: Document is not focused."), "figmaErrClipboard");
  assert.equal(captureErrorKey("Element not found: body"), "figmaErrFailed");
  assert.equal(captureErrorKey(undefined), "figmaErrFailed");
});

/** Вікно-підробка: пише журнал викликів, щоб перевірити ПОРЯДОК. */
function fakeWin(result, { loadFails = false } = {}) {
  const log = [];
  const doc = fakeDoc(["[data-comment-layer]"]);
  const win = {
    document: doc,
    focus: () => log.push("focus"),
    figma: undefined,
  };
  const load = async (w) => {
    log.push("load");
    if (loadFails) throw new Error("load");
    w.figma = { captureForDesign: async (opts) => { log.push(["capture", opts]); return result; } };
    return w.figma;
  };
  return { win, log, load, doc };
}

test("captureToFigma: фокус ДО завантаження, помітка оверлеїв, захоплення body", async () => {
  const { win, log, load, doc } = fakeWin(undefined);
  const res = await captureToFigma(win, { load, delayMs: 7 });
  assert.equal(log[0], "focus", "фокус мусить бути першим — інакше скрипт висить вічно");
  assert.equal(log[1], "load");
  assert.deepEqual(log[2], ["capture", { selector: "body", delayMs: 7 }]);
  assert.equal(doc.els[0].attrs["data-h2d-ignore"], "true");
  assert.deepEqual(res, { ok: true });
});

test("captureToFigma: {success:false} скрипта — це невдача, а не успіх", async () => {
  const { win, load } = fakeWin({ success: false, error: "Clipboard error: Write permission denied." });
  const res = await captureToFigma(win, { load });
  assert.equal(res.ok, false);
  assert.equal(res.key, "figmaErrClipboard");
  assert.match(res.detail, /permission denied/);
});

test("captureToFigma: скрипт не завантажився — окрема причина", async () => {
  const { win, load } = fakeWin(undefined, { loadFails: true });
  const res = await captureToFigma(win, { load });
  assert.equal(res.ok, false);
  assert.equal(res.key, "figmaErrLoad");
});

test("затримка за замовчуванням — як у букмарклеті, і в межах вікна активації", () => {
  assert.equal(CAPTURE_DELAY_MS, 1000);
  assert.equal(CAPTURE_SRC, "https://mcp.figma.com/mcp/html-to-design/capture.js");
});

test("loadCapture: API вже є — нового скрипта не вставляє", async () => {
  const doc = fakeDoc();
  const win = { document: doc, figma: { captureForDesign() {} } };
  await loadCapture(win);
  assert.equal(doc.appended.length, 0);
});

test("loadCapture: вставляє скрипт один раз і чекає на API", async () => {
  const doc = fakeDoc();
  const win = { document: doc };
  const p1 = loadCapture(win, { timeoutMs: 1000 });
  const p2 = loadCapture(win, { timeoutMs: 1000 });
  assert.equal(doc.appended.length, 1, "друге звернення не сміє вставити другий скрипт");
  assert.equal(doc.appended[0].src, CAPTURE_SRC);
  win.figma = { captureForDesign() {} };
  doc.appended[0].dispatchEvent(new Event("load"));
  assert.equal(await p1, win.figma);
  assert.equal(await p2, win.figma);
});

test("loadCapture: помилка мережі — відмова і прибраний тег (наступна спроба вставить новий)", async () => {
  const doc = fakeDoc();
  const win = { document: doc };
  const p = loadCapture(win, { timeoutMs: 1000 });
  doc.appended[0].dispatchEvent(new Event("error"));
  await assert.rejects(p, /load/);
  assert.equal(doc.appended.length, 0);
});

test("loadCapture: скрипт мовчить — відмова за таймаутом, а не вічне чекання", async () => {
  const doc = fakeDoc();
  const win = { document: doc };
  await assert.rejects(loadCapture(win, { timeoutMs: 20 }), /timeout/);
  assert.equal(doc.appended.length, 0);
});

/* Ревʼю T-41: вікно рамки, взяте в мить кліку, може «протухнути» за час
   захоплення (перемкнули сторінку — у рамці новий документ). Будь-який збій
   мусить повернутись `{ok:false}` і дійти до `tell()`, а не стати
   необробленим відхиленням — тобто тихою невдачею. */
test("captureToFigma ніколи не відхиляється: збій на протухлому вікні — {ok:false}", async () => {
  const win = {
    focus() {},
    get document() { throw new Error("документ рамки зник"); },
  };
  const res = await captureToFigma(win, { load: async () => ({ captureForDesign: async () => ({}) }) });
  assert.equal(res.ok, false);
  assert.equal(res.key, "figmaErrFailed");
  assert.match(res.detail, /зник/);
});
