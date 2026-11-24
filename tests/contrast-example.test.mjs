import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// The panel script is a classic script: load it in a context with no `deai`, so only the pure logic is defined.
const src = readFileSync(new URL("../docs/modules/examples/contrast/panel/contrast.js", import.meta.url), "utf8");
const ctx = vm.createContext({ window: {} });
vm.runInContext(src, ctx);
const C = vm.runInContext("Contrast", ctx);

const node = (ref, tag, o = {}) => ({ ref, tag, id: "", cls: "", text: "", visible: true, parent: null, attrs: {}, styles: {}, ...o });
const S = (color, bg = "rgba(0, 0, 0, 0)", size = "16px", weight = "400") =>
  ({ color, "background-color": bg, "font-size": size, "font-weight": weight });

test("ratio: white on light green fails badly, black on white is 21", () => {
  const white = C.parseRgb("rgb(255, 255, 255)"), green = C.parseRgb("rgb(159, 211, 184)");
  assert.ok(C.ratio(white, green) < 3);
  assert.equal(Math.round(C.ratio(C.parseRgb("rgb(0, 0, 0)"), white)), 21);
  assert.equal(C.parseRgb("rgba(1, 2, 3, 0.5)").a, 0.5);
  assert.equal(C.parseRgb("nonsense"), null);
});

test("isLarge: 24px, or 18.66px and bold", () => {
  assert.equal(C.isLarge("24px", "400"), true);
  assert.equal(C.isLarge("23.9px", "400"), false);
  assert.equal(C.isLarge("18.66px", "700"), true);
  assert.equal(C.isLarge("18.6px", "700"), false);
  assert.equal(C.isLarge("18.66px", "600"), false);
});

test("bgOf: nearest opaque ancestor through two levels, else white", () => {
  const body = node("b", "body", { styles: S("rgb(0, 0, 0)", "rgb(10, 20, 30)") });
  const wrap = node("w", "div", { parent: "b", styles: S("rgb(0, 0, 0)") });
  const leaf = node("l", "p", { parent: "w", styles: S("rgb(0, 0, 0)", "rgba(5, 5, 5, 0.4)") });
  const byRef = { b: body, w: wrap, l: leaf };
  assert.deepEqual({ ...C.bgOf(leaf, byRef) }, { r: 10, g: 20, b: 30, a: 1 });
  assert.deepEqual({ ...C.bgOf(node("x", "p", { styles: S("rgb(0, 0, 0)") }), {}) }, { r: 255, g: 255, b: 255, a: 1 });
});

test("findings: text contrast, unlabeled fields, images without alt", () => {
  const nodes = [
    node("body", "body", { styles: S("rgb(0, 0, 0)", "rgb(255, 255, 255)") }),
    node("t1", "button", { parent: "body", text: "Go", styles: S("rgb(255, 255, 255)", "rgb(159, 211, 184)", "14px", "600") }),
    node("t2", "p", { parent: "body", text: "Fine", styles: S("rgb(0, 0, 0)") }),
    node("t3", "p", { parent: "body", text: "Grey", styles: S("rgb(130, 130, 130)") }),
    node("t4", "p", { parent: "body", text: "Hidden", visible: false, styles: S("rgb(250, 250, 250)") }),
    node("f1", "input", { parent: "body", id: "a" }),
    node("f2", "input", { parent: "body", id: "b" }),
    node("f3", "input", { parent: "body", id: "c", attrs: { "aria-label": "Name" } }),
    node("f4", "input", { parent: "body", attrs: { type: "hidden" } }),
    node("lb", "label", { parent: "body", attrs: { for: "b" }, text: "Email" }),
    node("i1", "img", { parent: "body" }),
    node("i2", "img", { parent: "body", attrs: { alt: "" } }),
    node("i3", "div", { parent: "body", attrs: { role: "img" } }),
    node("i4", "div", { parent: "body", attrs: { role: "img", "aria-label": "Logo" } }),
  ];
  const f = C.findings({ nodes });
  const by = Object.fromEntries(f.map((x) => [x.ref, x]));
  assert.deepEqual(Object.keys(by).sort(), ["f1", "i1", "i3", "t1", "t3"]);
  assert.equal(by.t1.tone, "error");
  assert.match(by.t1.label, /^Контраст \d\.\d:1$/);
  assert.equal(by.t1.fix.color, "rgb(0, 0, 0)");
  assert.equal(by.t3.tone, "warn");                       // grey on white is about 3.5:1: between 3 and 4.5
  assert.equal(by.f1.tone, "warn");
  assert.equal(by.i1.tone, "info");
});
