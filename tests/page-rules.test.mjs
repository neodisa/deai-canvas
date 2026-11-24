import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { LIMITS, METHOD_PERM, PAGE_PERMS, PageError, TONES, TONE_COLORS, allowed, attrAllowed, checkClassList,
  checkLabel, checkStyleMap, checkStyleNames, checkText, checkTone, createJournal, stillOurs } from "../app/page-rules.js";

test("кожен метод має дозвіл; allowed() дивиться лише на нього", () => {
  for (const [m, p] of Object.entries(METHOD_PERM)) {
    assert.ok(m.startsWith("page.") && PAGE_PERMS.includes(p), m);
    assert.equal(allowed(m, [p]), true);
    assert.equal(allowed(m, PAGE_PERMS.filter((x) => x !== p)), false, m);
  }
  assert.equal(allowed("page.nope", PAGE_PERMS), false);
  assert.equal(allowed("page.info", null), false);
});

test("атрибути: список дозволених, зарезервовані data-*, решта — ні", () => {
  for (const n of ["role", "hidden", "title", "alt", "lang", "dir", "tabindex", "disabled", "placeholder", "open",
    "aria-label", "aria-describedby", "data-x", "data-test-id", "ARIA-LABEL"]) assert.equal(attrAllowed(n), true, n);
  for (const n of ["onclick", "src", "href", "srcdoc", "style", "class", "action", "formaction", "xlink:href",
    "data-deai-x", "data-canvas-inspector", "data-comment-layer", "data-h2d-ignore", "aria-", "data-", "id", ""])
    assert.equal(attrAllowed(n), false, n);
});

test("класи: імена, ліміт, тип", () => {
  assert.deepEqual(checkClassList(["a", "b-c", "_d"]), ["a", "b-c", "_d"]);
  for (const bad of [["1a"], ["a b"], ["a:b"], [""], "a", [1], Array(LIMITS.classes + 1).fill("a")])
    assert.throws(() => checkClassList(bad), (e) => e instanceof PageError && e.code === "bad-args");
});

test("стилі: назви й значення; url( і екранування — rejected, null — зняти", () => {
  assert.deepEqual(checkStyleNames(["color", "background-color", "--x"]), ["color", "background-color", "--x"]);
  assert.throws(() => checkStyleNames(Array(LIMITS.styles + 1).fill("color")), /bad-args|styles/);
  assert.throws(() => checkStyleNames(["col or"]), (e) => e.code === "bad-args");
  const r = checkStyleMap({ color: "red", "--k": "1px", margin: null, background: "url(x.png)",
    "background-image": "IMAGE-SET(a 1x)", width: "u\\72l(x)" });
  assert.deepEqual(r.ok, [["color", "red"], ["--k", "1px"], ["margin", null]]);
  assert.deepEqual(r.rejected.sort(), ["background", "background-image", "width"]);
  assert.throws(() => checkStyleMap({}), (e) => e.code === "bad-args");
  assert.throws(() => checkStyleMap({ color: 5 }), (e) => e.code === "bad-args");
});

test("текст, ярлик, тон", () => {
  assert.equal(checkText("abc"), "abc");
  assert.throws(() => checkText("x".repeat(LIMITS.text + 1)), (e) => e.code === "bad-args");
  assert.equal(checkLabel(undefined), "");
  assert.equal(checkLabel("a".repeat(100)).length, LIMITS.label);
  assert.equal(checkTone(undefined), "info");
  for (const tn of TONES) assert.equal(checkTone(tn), tn);
  assert.throws(() => checkTone("red"), (e) => e.code === "bad-args");
});

test("кольори тонів збігаються з токенами ядра в styles.css", () => {
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  const tok = (n) => css.match(new RegExp(`--${n}:(#[0-9A-Fa-f]{6})`))[1].toLowerCase();
  assert.deepEqual(Object.fromEntries(Object.entries(TONE_COLORS).map(([k, v]) => [k, v.toLowerCase()])),
    { error: tok("bad"), warn: tok("open"), ok: tok("ok"), info: tok("pick") });
});

test("журнал: id, ліміт, take, takeAll — новіші першими", () => {
  const j = createJournal(3);
  const a = j.add({ n: 1 }), b = j.add({ n: 2 }), c = j.add({ n: 3 });
  assert.deepEqual([a, b, c], ["c1", "c2", "c3"]);
  assert.throws(() => j.add({ n: 4 }), (e) => e.code === "too-many");
  assert.deepEqual(j.take("c2"), { id: "c2", n: 2 });
  assert.equal(j.take("c2"), null);
  assert.deepEqual(j.takeAll().map((x) => x.id), ["c3", "c1"]);
  assert.equal(j.size, 0);
});

test("stillOurs: відкат лише коли поточне досі «стало»", () => {
  assert.equal(stillOurs("red", "red"), true);
  assert.equal(stillOurs("blue", "red"), false);
  assert.equal(stillOurs(null, null), true);
});
