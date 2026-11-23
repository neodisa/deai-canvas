/**
 * Нормалізація кольорів і SVG-ціль знімка (0.35.1). html2canvas 1.4.1 розбирає лише rgb/hsl, тож `color-mix()`,
 * `color()`, `oklab()`, `oklch()`, `lab()`, `lch()` у клоні переписуються в rgba(). Чисті функції — без DOM.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { rewriteColors, liftSvgTarget, SHOT_COLOR_PROPS } from "../src/shot-colors.js";

const tag = (m) => `<${m}>`;

test("rewriteColors: тінь із двома кольорами — переписано обидва, решта значення незмінна", () => {
  const v = "oklch(0.6 0.2 30 / 0.5) 0px 4px 12px 0px, color(srgb 1 0 0 / 0.3) 0px 1px 2px 0px";
  assert.equal(rewriteColors(v, tag), "<oklch(0.6 0.2 30 / 0.5)> 0px 4px 12px 0px, <color(srgb 1 0 0 / 0.3)> 0px 1px 2px 0px");
});

test("rewriteColors: градієнт — кольорові функції всередині linear-gradient(...)", () => {
  const v = "linear-gradient(90deg, oklab(0.5 0.1 0.1) 0%, rgb(0, 0, 0) 50%, oklab(0.9 0 0 / 0.2) 100%)";
  assert.equal(rewriteColors(v, tag), "linear-gradient(90deg, <oklab(0.5 0.1 0.1)> 0%, rgb(0, 0, 0) 50%, <oklab(0.9 0 0 / 0.2)> 100%)");
});

test("rewriteColors: вкладений color-mix із color() — один збіг на зовнішню функцію", () => {
  const v = "color-mix(in srgb, color(srgb 1 0 0) 40%, blue)";
  const seen = [];
  assert.equal(rewriteColors(v, (m) => { seen.push(m); return "X"; }), "X");
  assert.deepEqual(seen, [v]);
});

test("rewriteColors: lab( не збігається всередині oklab( і навпаки", () => {
  const seen = [];
  rewriteColors("oklab(1 0 0) lab(50 10 10) oklch(1 0 0) lch(50 10 10)", (m) => { seen.push(m); return "X"; });
  assert.deepEqual(seen, ["oklab(1 0 0)", "lab(50 10 10)", "oklch(1 0 0)", "lch(50 10 10)"]);
  assert.equal(rewriteColors("oklab(1 0 0)", tag), "<oklab(1 0 0)>");
});

test("rewriteColors: без колірних функцій — значення те саме (rgb, hsl, ключові слова, url)", () => {
  for (const v of ["rgb(1, 2, 3)", "rgba(0, 0, 0, 0.5) 0px 1px 2px", "hsl(10 20% 30%)", "none", "red", "url(\"a.png\")", ""]) {
    assert.equal(rewriteColors(v, () => { throw new Error("не мав викликатись"); }), v);
  }
});

test("rewriteColors: конвертер повернув null — цей збіг лишається як був", () => {
  const v = "oklab(1 0 0) 0 0 1px, lch(50 10 10) 0 0 2px";
  assert.equal(rewriteColors(v, (m) => (m.startsWith("lch") ? "rgba(1, 2, 3, 1)" : null)), "oklab(1 0 0) 0 0 1px, rgba(1, 2, 3, 1) 0 0 2px");
});

test("SHOT_COLOR_PROPS: усі колірні властивості з рішення", () => {
  for (const p of ["color", "background-color", "background-image", "border-top-color", "border-right-color", "border-bottom-color",
    "border-left-color", "outline-color", "text-decoration-color", "box-shadow", "text-shadow", "-webkit-text-stroke-color",
    "-webkit-text-fill-color", "caret-color", "column-rule-color"]) assert.ok(SHOT_COLOR_PROPS.includes(p), p);
});

const SVG = "http://www.w3.org/2000/svg";
const node = (ns, parentElement) => ({ namespaceURI: ns, parentElement });

test("liftSvgTarget: іконка в кнопці — ціль стає кнопкою (path → svg → button)", () => {
  const body = node("http://www.w3.org/1999/xhtml", null);
  const button = node("http://www.w3.org/1999/xhtml", body);
  const svg = node(SVG, button);
  const path = node(SVG, svg);
  assert.equal(liftSvgTarget(path), button);
  assert.equal(liftSvgTarget(svg), button);
});

test("liftSvgTarget: HTML-ціль не змінюється; кореневий svg без HTML-предка лишається собою", () => {
  const html = node("http://www.w3.org/1999/xhtml", null);
  assert.equal(liftSvgTarget(html), html);
  const lone = node(SVG, null);
  assert.equal(liftSvgTarget(lone), lone);
});
