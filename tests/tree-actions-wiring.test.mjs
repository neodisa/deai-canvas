/**
 * B4: проводка `app/app.js`, яку юніти `tree-actions.test.mjs` не бачать.
 * `app.js` не імпортується в Node (DOM на верхньому рівні), тож це мінімум
 * текстових перевірок — самі рішення живуть у `app/tree-actions.js` і
 * тестуються імпортом.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

test("кожна команда палітри дерева має обробник у PANEL_ACTIONS", () => {
  for (const act of ["groupsel", "ungroup", "outdent", "focusbranch", "togglekind"]) {
    assert.match(src, new RegExp(`\\n  ${act}: `), `PANEL_ACTIONS.${act} немає`);
  }
});

test("масове видалення питає stillValid перед кожним кроком і передає ітерацію в treePost", () => {
  assert.match(src, /runSequential\(model\.ids,[\s\S]*?\{ stillValid: \(\) => picked === it \}\)/);
  assert.match(src, /treePost\('\/api\/page-delete', \{ page: id, mode \}, \{ it, quiet: true \}\)/);
  assert.match(src, /if \(opts\.it !== undefined && picked !== opts\.it\) return null/);
});

test("treePost: таймаут 15 с через AbortController, замок — treeBusyGate", () => {
  assert.match(src, /TREE_TIMEOUT_MS = 15000/);
  assert.match(src, /signal: ctl\.signal/);
  assert.match(src, /treeGate\.run\(/);
});

test("занятість перевіряється ДО діалогу видалення", () => {
  const i = src.indexOf("async function deleteNodes(");
  const body = src.slice(i, src.indexOf("\n}\n", i));
  assert.ok(body.indexOf("treeGate.busy") > 0);
  assert.ok(body.indexOf("treeGate.busy") < body.indexOf("askChoice("));
  assert.ok(body.indexOf("treeGate.busy") < body.indexOf("askYesNo("));
});

test("⌘G: ціль рахується до preventDefault, автоповтор ігнорується", () => {
  const i = src.indexOf("=== 'g'");
  const ctx = src.slice(i, i + 900);
  assert.ok(ctx.indexOf("groupTargetIds(") < ctx.indexOf("preventDefault()"));
  assert.match(ctx, /ev\.repeat/);
  assert.match(ctx, /input,textarea,\[contenteditable\]/);
});

test("кидок: treePost несе ітерацію жесту, перемальовка лише в тій самій ітерації", () => {
  assert.match(src, /'\/api\/page-move'[^\n]*\{ it: cur\.it \}\)/);
  assert.match(src, /shouldCommitDrop\(\{ commit, plan, startIt: cur\.it, currentIt: picked \}\)/);
  assert.match(src, /if \(r && picked === cur\.it\) \{/);
  assert.match(src, /d\.openId === hit\.id && picked === d\.it/);
});

test("кидок: план з точки відпускання, відновлення після перемальовки, розкриття лише після успіху", () => {
  // план при відпусканні лічиться заново, а не береться з кешу руху
  assert.match(src, /resolveDrop\(panelPages, cur\.ids, hitAt\(ev\.clientX, ev\.clientY\)/);
  assert.match(src, /el\.addEventListener\('pointerup', \(ev\) => finish\(true, ev\)\)/);
  // renderPanel кличе хук жесту
  assert.match(src, /restoreRowFocus\(el\);\n  dragRepaint\?\.\(\);/);
  // розкриття — після `if (r && picked === cur.it)`, не до запиту
  assert.match(src, /if \(r && picked === cur\.it\) \{\n[^\n]*\n      if \(res\.where === 'inside'/);
  // скасування: втрата capture, blur, Esc із stopPropagation
  assert.match(src, /'lostpointercapture', \(\) => finish\(false\)/);
  assert.match(src, /window\.addEventListener\('blur', onBlur\)/);
  assert.match(src, /ev\.preventDefault\(\); ev\.stopPropagation\(\);\n    finish\(false\)/);
  // старт жесту: зайнято / модифікатори / другий вказівник
  assert.match(src, /if \(d\?\.on\) return;/);
  assert.match(src, /ev\.shiftKey \|\| ev\.metaKey \|\| ev\.ctrlKey \|\| ev\.altKey/);
  assert.match(src, /if \(treeGate\.busy\) return;  /);
});

test("палітра: pagePub — по ланцюжку видимості (visibleIds), а не по власному прапорцю", () => {
  assert.match(src, /pagePub: !pickedPg \|\| visibleIds\(panelPages\)\.has\(pickedPg\.id\)/);
  assert.doesNotMatch(src, /pagePub: [^\n]*published !== false/);
});

test("оновлення панелі з диска: focus і visibilitychange, рішення — shouldRefreshPanel ДО і ПІСЛЯ запиту", () => {
  const i = src.indexOf("async function refreshPanelFromDisk(");
  const body = src.slice(i, src.indexOf("\n}\n", i));
  assert.equal((body.match(/shouldRefreshPanel\(/g) || []).length, 2, "до й після await");
  assert.ok(body.indexOf("shouldRefreshPanel(") < body.indexOf("await api("));
  assert.match(body, /rev: r\?\.rev \?\? '', seenRev: panelRev/);
  assert.match(body, /busy: treeGate\.busy, dragging: dragActive\(\)/);
  assert.match(body, /\.cv-ask-scrim/);
  assert.match(body, /if \(mode === 'canvas' \|\| pickedPage !== before\) render\(\); else renderPanel\(\);/, "«Огляд» або зникла відкрита сторінка → повний render");
  assert.match(src, /addEventListener\('focus', \(\) => \{ syncTuneFromDisk\(\); refreshPanelFromDisk\(\); \}\)/);
  assert.match(src, /visibilityState === 'visible'\) \{ syncTuneFromDisk\(\); refreshPanelFromDisk\(\); \}/);
  assert.match(src, /dragActive = \(\) => d !== null;/, "жест повідомляє про себе");
});

test("loadPages звіряє теки лише в межах ТІЄЇ САМОЇ ітерації (ревʼю 1.47, W1)", () => {
  assert.match(src, /vanishedFolders\(\{ prev: panelPages, next: r\.pages \|\| \[\], prevRev: panelRev, nextRev: r\.rev \|\| '',\s*prevIt: panelPagesIt, it \}\)/);
  assert.match(src, /panelPagesIt = it;/);
});

test("опитування it-stamp питає shouldPollStamp з видимістю вкладки (ревʼю 1.47, W2–W3)", () => {
  assert.match(src, /if \(!shouldPollStamp\(\{ mode, picked, visible: document\.visibilityState === 'visible', home: homeOpen \}\)\) return;/);
});
