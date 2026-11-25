import assert from "node:assert/strict";
import test from "node:test";
import { isTruncated, placeTip, tipText } from "../app/tooltip.js";

const el = (o = {}) => ({
  scrollWidth: 0, clientWidth: 0, textContent: "", attrs: {}, classes: [],
  getAttribute(k) { return this.attrs[k] ?? null; },
  matches(sel) { return sel === ".row-name" && this.classes.includes("row-name"); },
  ...o,
});

test("isTruncated: лише коли вміст ширший за видиму частину", () => {
  assert.equal(isTruncated(el({ scrollWidth: 300, clientWidth: 200 })), true);
  assert.equal(isTruncated(el({ scrollWidth: 200, clientWidth: 200 })), false);
  assert.equal(isTruncated(null), false);
});

test("tipText: data-tip — завжди; .row-name — лише обрізана; решта — порожньо", () => {
  assert.equal(tipText(el({ attrs: { "data-tip": "Назад ⌘[" } })), "Назад ⌘[");
  const row = el({ classes: ["row-name"], textContent: "  Довга назва  ", scrollWidth: 300, clientWidth: 100 });
  assert.equal(tipText(row), "Довга назва");
  assert.equal(tipText(el({ classes: ["row-name"], textContent: "Коротка", scrollWidth: 50, clientWidth: 100 })), "");
  assert.equal(tipText(el({ textContent: "x", scrollWidth: 500, clientWidth: 10 })), "", "чужий елемент без data-tip");
  assert.equal(tipText(null), "");
});

test("placeTip: під елементом; притиснута до меж; біля низу — над елементом", () => {
  const base = { w: 200, h: 30, vw: 1000, vh: 800 };
  assert.deepEqual(placeTip({ ...base, rect: { left: 10, top: 20, bottom: 40 } }), { left: 10, top: 46 });
  assert.equal(placeTip({ ...base, rect: { left: 950, top: 20, bottom: 40 } }).left, 792, "правий край: vw - w - 8");
  assert.equal(placeTip({ ...base, rect: { left: -50, top: 20, bottom: 40 } }).left, 8, "лівий край: відступ 8");
  assert.equal(placeTip({ ...base, rect: { left: 10, top: 770, bottom: 790 } }).top, 734, "над елементом: top - 6 - h");
});
