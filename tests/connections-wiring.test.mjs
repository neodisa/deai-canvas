import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const src = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

/** Тіло функції `name` (від `{` після сигнатури до парної `}`). */
function fn(name) {
  const m = new RegExp(`(?:async )?function ${name}\\(`).exec(src);
  assert.ok(m, `функції ${name} нема`);
  const open = src.indexOf("{", src.indexOf(")", m.index));
  let depth = 0;
  for (let i = open; i < src.length; i += 1) {
    if (src[i] === "{") depth += 1;
    else if (src[i] === "}") { depth -= 1; if (depth === 0) return src.slice(open, i + 1); }
  }
  throw new Error(`немає закриття для ${name}`);
}

test("дії смуги: conn веде на сторінку, логотип — завжди на «Задачі»", () => {
  assert.match(src, /\n  conn: \(\) => enterConnections\(\),/);
  assert.match(src, /\n  home: \(\) => enterHome\(\{ page: 'tasks' \}\),/);
  assert.match(fn("wireHome"), /case 'conn': enterConnections\(\); break;/);
});

test("enterHome тримає відкриту сторінку (перемикання простору й запис модулів лишають «Підключення»)", () => {
  const b = fn("enterHome");
  assert.match(b, /page \?\? \(was \? homePage : 'tasks'\)/);
  assert.match(b, /if \(homePage === 'conn'\)[\s\S]*?loadConn\(\{ spaces \}\)/);
  assert.match(b, /if \(next !== 'conn'\) closeCnDrawer\(\{ focus: false \}\)/);
});

test("barState і paletteState несуть homePage", () => {
  assert.match(src, /homePage: homeOpen \? homePage : null,/);
  assert.match(src, /homePage: st\.homePage,/);
});

test("клавіші сторінки «Задачі» на «Підключенні» не діють", () => {
  assert.match(src, /if \(!homeOpen \|\| ev\.isComposing \|\| paletteOverlay \|\| document\.querySelector\('\.cv-ask-scrim'\)\) return;\n  if \(homePage === 'conn'\) return;/);
});

test("перечитування при поверненні у вікно: на «Підключенні» — loadConn", () => {
  assert.match(fn("refreshHomeOnReturn"), /homePage === 'conn' \? loadConn\(\) : loadHome\(\)/);
});

test("запити сторінки несуть явний space (агент міг перемкнути активний простір)", () => {
  assert.match(fn("loadConn"), /api\(`\/api\/modules\?space=\$\{encodeURIComponent\(sp\.id\)\}`\)/);
  assert.match(fn("connCheck"), /postForm\('\/api\/module-check', \{ space: connState\.spaceId, id: e\.id \}\)/);
  assert.match(fn("connDisable"), /postForm\('\/api\/module-disable', \{ space: connState\.spaceId, id: e\.id \}\)/);
});

test("після вимкнення — afterModulesChange (= afterSpaceChange: смуга, рамка, інспектор)", () => {
  assert.match(fn("connDisable"), /await afterModulesChange\(\);/);
  assert.match(fn("afterModulesChange"), /await afterSpaceChange\(\);/);
});

test("фокус після перемальовки повертається і на кнопки карток (data-cn + data-id)", () => {
  /* Не голий підрядок `a.dataset.cn` (його задовольнило б і `a.dataset.cnX`): умова, дія в селекторі й `data-id`. */
  assert.match(fn("focusKey"), /if \(a\.dataset\.cn\) \{\s*return `\[data-cn="\$\{a\.dataset\.cn\}"\]\$\{a\.dataset\.id != null \? `\[data-id="\$\{CSS\.escape\(a\.dataset\.id\)\}"\]` : ''\}`;/);
});
