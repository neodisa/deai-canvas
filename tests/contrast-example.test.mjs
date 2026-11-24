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

const near = (c, r, g, b) => assert.ok(Math.abs(c.r - r) < 1e-6 && Math.abs(c.g - g) < 1e-6 && Math.abs(c.b - b) < 1e-6 && c.a === 1, JSON.stringify(c));
const snapOf = (...nodes) => ({ nodes });
const body = (bg = "rgb(255, 255, 255)") => node("body", "body", { styles: S("rgb(0, 0, 0)", bg) });
const find = (nodes) => Object.fromEntries(C.findings(snapOf(...nodes)).map((x) => [x.ref, x]));

test("bgOf: semi-transparent layers composited up to the first opaque ancestor, else white", () => {
  const b = node("b", "body", { styles: S("rgb(0, 0, 0)", "rgb(10, 20, 30)") });
  const wrap = node("w", "div", { parent: "b", styles: S("rgb(0, 0, 0)") });
  const leaf = node("l", "p", { parent: "w", styles: S("rgb(0, 0, 0)", "rgba(5, 5, 5, 0.4)") });
  const byRef = { b, w: wrap, l: leaf };
  near(C.bgOf(leaf, byRef), 8, 14, 20);                    // 0.4 * 5 + 0.6 * (10, 20, 30)
  near(C.bgOf(wrap, byRef), 10, 20, 30);
  near(C.bgOf(node("x", "p", { styles: S("rgb(0, 0, 0)") }), {}), 255, 255, 255);
  // two semi-transparent layers over the implicit white top
  const a = node("a", "div", { styles: S("rgb(0, 0, 0)", "rgba(0, 0, 0, 0.5)") });
  const c = node("c", "p", { parent: "a", styles: S("rgb(0, 0, 0)", "rgba(0, 0, 0, 0.5)") });
  near(C.bgOf(c, { a, c }), 63.75, 63.75, 63.75);
});

test("bgOf: a truncated parent chain ends the walk with white; an unknown colour space gives null", () => {
  const leaf = node("l", "p", { parent: "gone", styles: S("rgb(0, 0, 0)", "rgba(0, 0, 0, 0.5)") });
  near(C.bgOf(leaf, { l: leaf }), 127.5, 127.5, 127.5);
  const ok = node("o", "p", { styles: S("rgb(0, 0, 0)", "oklch(0.5 0.1 200)") });
  assert.equal(C.bgOf(ok, { o: ok }), null);
});

test("parseColor: rgb, rgba, slash alpha, color(srgb), transparent; other spaces are null", () => {
  assert.deepEqual({ ...C.parseColor("rgb(1 2 3 / 50%)") }, { r: 1, g: 2, b: 3, a: 0.5 });
  assert.deepEqual({ ...C.parseColor("color(srgb 1 0 0.5 / 0.25)") }, { r: 255, g: 0, b: 127.5, a: 0.25 });
  assert.deepEqual({ ...C.parseColor("color(srgb 0 0 0)") }, { r: 0, g: 0, b: 0, a: 1 });
  assert.equal(C.parseColor("transparent").a, 0);
  for (const v of ["oklch(0.5 0.1 200)", "lab(50 10 10)", "color(display-p3 1 0 0)", "", undefined]) assert.equal(C.parseColor(v), null, String(v));
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

test("text alpha is mixed with the background: grey 50% black on white fails, solid black passes", () => {
  const f = find([body(), node("t", "p", { parent: "body", text: "Hi", styles: S("rgba(0, 0, 0, 0.4)") }),
    node("u", "p", { parent: "body", text: "Ok", styles: S("rgba(0, 0, 0, 0.9)") })]);
  assert.deepEqual(Object.keys(f), ["t"]);                  // 0.4 black on white is about 2.9:1 mixed, 0.9 is far above 4.5
  assert.equal(f.t.tone, "error");
  assert.equal(f.t.fix.color, "rgb(0, 0, 0)");
});

test("a semi-transparent background is composited, not skipped to the ancestor", () => {
  const nodes = [body("rgb(0, 0, 0)"),
    node("t", "p", { parent: "body", text: "Hi", styles: S("rgb(255, 255, 255)", "rgba(255, 255, 255, 0.9)") })];
  const f = find(nodes);                                    // white on (almost white) over black: fails; skipping to black would pass
  assert.deepEqual(Object.keys(f), ["t"]);
  assert.equal(f.t.fix.color, "rgb(0, 0, 0)");
});

test("color(srgb …) text and background are understood; oklch is skipped, not guessed", () => {
  const f = find([body(), node("t", "p", { parent: "body", text: "A", styles: S("color(srgb 0.9 0.9 0.9)") }),
    node("k", "p", { parent: "body", text: "B", styles: S("oklch(0.9 0 0)") }),
    node("m", "p", { parent: "body", text: "C", styles: S("rgb(250, 250, 250)", "oklch(0.9 0 0)") })]);
  assert.deepEqual(Object.keys(f), ["t"]);
});

test("a dark background gets a white fix", () => {
  const f = find([body("rgb(20, 20, 20)"), node("t", "p", { parent: "body", text: "Dim", styles: S("rgb(40, 40, 40)") })]);
  assert.equal(f.t.fix.color, "rgb(255, 255, 255)");
});

test("the shown ratio is floored to one decimal", () => {
  // grey 120 on white is about 4.48:1: it fails, and rounding would read «4.5:1»
  const f = find([body(), node("t", "p", { parent: "body", text: "G", styles: S("rgb(120, 120, 120)") })]);
  const r = C.ratio(C.parseColor("rgb(120, 120, 120)"), C.parseColor("rgb(255, 255, 255)"));
  assert.ok(r < 4.5 && r > 4.4, String(r));
  assert.equal(f.t.label, "Контраст 4.4:1");
});

test("an input inside a label is labelled (walks the parent chain); a cut chain is not an error", () => {
  const f = find([body(), node("lb", "label", { parent: "body", text: "" }), node("w", "span", { parent: "lb" }),
    node("in", "input", { parent: "w" }), node("lone", "input", { parent: "missing" })]);
  assert.deepEqual(Object.keys(f), ["lone"]);
});

test("blank aria-label is not a name; role=img with aria-labelledby is named", () => {
  const f = find([body(),
    node("a", "input", { parent: "body", attrs: { "aria-label": "  " } }),
    node("b", "input", { parent: "body", attrs: { "aria-label": "" } }),
    node("c", "input", { parent: "body", attrs: { "aria-labelledby": "x" } }),
    node("d", "div", { parent: "body", attrs: { role: "img", "aria-label": "" } }),
    node("e", "div", { parent: "body", attrs: { role: "img", "aria-labelledby": "x" } })]);
  assert.deepEqual(Object.keys(f).sort(), ["a", "b", "d"]);
});

test("English strings and plain language switch", () => {
  try {
    C.setLang("en");
    assert.equal(C.getLang(), "en");
    const f = find([body(), node("t", "p", { parent: "body", text: "G", styles: S("rgb(120, 120, 120)") }),
      node("i", "input", { parent: "body" }), node("m", "img", { parent: "body" })]);
    assert.equal(f.t.label, "Contrast 4.4:1");
    assert.equal(f.i.label, "Field has no label");
    assert.equal(f.m.label, "Image has no description");
    C.setLang("de");
    assert.equal(C.getLang(), "uk");
  } finally { C.setLang("uk"); }
});
