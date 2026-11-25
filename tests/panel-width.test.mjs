import assert from "node:assert/strict";
import test from "node:test";
import { KEY_STEP, PANEL_W_DEFAULT, PANEL_W_MAX, PANEL_W_MIN, clampPanelW, fitPanelW, panelWBounds, parseStoredW } from "../app/panel-width.js";

test("межі: 200..520 на широкому вікні; сцена ≥ 420 з правою панеллю", () => {
  assert.deepEqual(panelWBounds({ vw: 1600, rightW: 0 }), { min: 200, max: 520 });
  assert.deepEqual(panelWBounds({ vw: 1024, rightW: 308 }), { min: 200, max: 296 }, "1024 − 308 − 420");
  assert.deepEqual(panelWBounds({ vw: 1024, rightW: 0 }), { min: 200, max: 520 }, "1024 − 420 = 604 > 520");
});

test("вузьке вікно: максимум не опускається нижче мінімуму (панель лишається придатною)", () => {
  assert.deepEqual(panelWBounds({ vw: 320, rightW: 0 }), { min: 200, max: 200 });
  assert.equal(clampPanelW(500, { vw: 320, rightW: 0 }), 200);
});

test("clampPanelW: притискає й округлює", () => {
  assert.equal(clampPanelW(100, { vw: 1600, rightW: 0 }), PANEL_W_MIN);
  assert.equal(clampPanelW(9999, { vw: 1600, rightW: 0 }), PANEL_W_MAX);
  assert.equal(clampPanelW(300.4, { vw: 1600, rightW: 0 }), 300);
});

test("fitPanelW: якщо є обрізані назви — ширина росте на найбільше переповнення; інакше повертається до 246", () => {
  const b = { min: 200, max: 520 };
  assert.equal(fitPanelW({ cur: 246, overflows: [0, 90, 40], bounds: b }), 246 + 90 + 2);
  assert.equal(fitPanelW({ cur: 334, overflows: [0, 0], bounds: b }), PANEL_W_DEFAULT, "усе влізло — назад до типової");
  assert.equal(fitPanelW({ cur: 246, overflows: [], bounds: b }), PANEL_W_DEFAULT);
});

test("fitPanelW: упертись у максимум — наступний виклик теж повертає типову (не застрягає)", () => {
  const b = { min: 200, max: 300 };
  assert.equal(fitPanelW({ cur: 246, overflows: [400], bounds: b }), 300);
  assert.equal(fitPanelW({ cur: 300, overflows: [400], bounds: b }), PANEL_W_DEFAULT);
});

test("fitPanelW: типова 246 сама притискається до вузьких меж", () => {
  assert.equal(fitPanelW({ cur: 300, overflows: [0], bounds: { min: 200, max: 220 } }), 220);
});

test("parseStoredW: лише ціле в межах 200..520", () => {
  assert.equal(parseStoredW("320"), 320);
  for (const bad of [null, "", "abc", "199", "521", "300.5", "NaN"]) assert.equal(parseStoredW(bad), null, String(bad));
});

test("крок клавіші — 16", () => { assert.equal(KEY_STEP, 16); });
