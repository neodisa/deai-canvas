import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { LIMITS, METHOD_PERM, PAGE_PERMS, PageError, TONES, TONE_COLORS, allowed, attrAllowed, isCoreAttr, checkClassList,
  checkAttrValue, checkLabel, checkStyleMap, checkStyleNames, checkText, checkTone, createJournal, stillOurs } from "../app/page-rules.js";

test("кожен метод має дозвіл; allowed() дивиться лише на нього", () => {
  for (const [m, p] of Object.entries(METHOD_PERM)) {
    assert.ok(m.startsWith("page.") && PAGE_PERMS.includes(p), m);
    assert.equal(allowed(m, [p]), true);
    assert.equal(allowed(m, PAGE_PERMS.filter((x) => x !== p)), false, m);
  }
  assert.equal(allowed("page.nope", PAGE_PERMS), false);
  assert.equal(allowed("page.info", null), false);
  assert.equal(allowed("page.info", "read"), false);
  for (const m of ["__proto__", "constructor", "toString", "hasOwnProperty"]) assert.equal(allowed(m, PAGE_PERMS), false, m);
});

test("таблиця METHOD_PERM точно збігається зі спекою (16 методів)", () => {
  assert.deepEqual(METHOD_PERM, {
    "page.info": "read", "page.query": "read", "page.get": "read", "page.snapshot": "read", "page.pick": "read",
    "page.reveal": "read",
    "page.mark": "mark", "page.unmark": "mark", "page.clearMarks": "mark",
    "page.setStyle": "change", "page.setClass": "change", "page.setAttr": "change", "page.setText": "change",
    "page.revert": "change", "page.revertAll": "change",
    "page.listen": "listen",
  });
});

test("атрибути: список дозволених, зарезервовані data-*, решта — ні", () => {
  for (const n of ["role", "hidden", "title", "alt", "lang", "dir", "tabindex", "disabled", "placeholder", "open",
    "aria-label", "aria-describedby", "data-x", "data-test-id"]) assert.equal(attrAllowed(n), true, n);
  for (const n of ["onclick", "src", "href", "srcdoc", "style", "class", "action", "formaction", "xlink:href",
    "data-deai-x", "data-canvas-inspector", "data-comment-layer", "data-h2d-ignore", "aria-", "data-", "id", "", null, 5, "hidden\n", "data-a--b", "DATA-DEAI-X", "data-a_b", "data-Key",
    "data-dc-x", "ARIA-LABEL", "Role", "data-\u212Aey"])
    assert.equal(attrAllowed(n), false, n);
});

test("isCoreAttr: службові маркери ядра", () => {
  for (const n of ["data-deai-x", "data-canvas-inspector", "data-comment-layer", "data-comment-id", "data-h2d-ignore", "data-dc-x", "DATA-DEAI-X"])
    assert.equal(isCoreAttr(n), true, n);
  for (const n of ["data-x", "data-test-id", "aria-label", "class", "", null, 5]) assert.equal(isCoreAttr(n), false, String(n));
});

test("класи: імена, ліміт, тип", () => {
  assert.deepEqual(checkClassList(["a", "b-c", "_d"]), ["a", "b-c", "_d"]);
  for (const bad of [["1a"], ["a b"], ["a:b"], [""], "a", [1], Array(LIMITS.classes + 1).fill("a")])
    assert.throws(() => checkClassList(bad), (e) => e instanceof PageError && e.code === "bad-args");
  assert.throws(() => checkClassList(["a\n"]), (e) => e.code === "bad-args");
  assert.deepEqual(checkClassList(["a".repeat(100)]), ["a".repeat(100)]);
  assert.throws(() => checkClassList(["a".repeat(101)]), (e) => e.code === "bad-args");
});

test("стилі: назви й значення; url( і екранування — rejected, null — зняти", () => {
  assert.deepEqual(checkStyleNames(["color", "background-color", "--x"]), ["color", "background-color", "--x"]);
  assert.throws(() => checkStyleNames(Array(LIMITS.styles + 1).fill("color")), (e) => e instanceof PageError && e.code === "bad-args");
  assert.throws(() => checkStyleNames(["col or"]), (e) => e.code === "bad-args");
  const r = checkStyleMap({ color: "red", "--k": "1px", margin: null, background: "url(x.png)",
    "background-image": "IMAGE-SET(a 1x)", width: "u\\72l(x)" });
  assert.deepEqual(r.ok, [["color", "red"], ["--k", "1px"], ["margin", null]]);
  assert.deepEqual(r.rejected.sort(), ["background", "background-image", "width"]);
  assert.throws(() => checkStyleMap({}), (e) => e.code === "bad-args");
  assert.throws(() => checkStyleMap({ color: 5 }), (e) => e.code === "bad-args");
  const badArgs = (m) => assert.throws(() => checkStyleMap(m), (e) => e instanceof PageError && e.code === "bad-args");
  const props41 = Object.fromEntries(Array.from({ length: 41 }, (_, i) => [`--p${i}`, "1"]));
  badArgs(props41);
  badArgs({ color: "x".repeat(501) });
  badArgs([["color", "red"]]);
  badArgs(JSON.parse('{"__proto__": "red"}'));
  badArgs({ Color: "red" });
  badArgs({ color: "" });
  const rej = (v) => assert.deepEqual(checkStyleMap({ "--x": v }), { ok: [], rejected: ["--x"] }, v);
  for (const v of ["URL(x)", '-webkit-image-set("a" 1x)', 'src("a")', "cross-fade(a,b)", 'image("a")', "a\nurl(x)",
    "url\n(x)", "/**/url(x)", "url(a)", "attr(data-x type(<url>))", "attr(data-x url)", "-webkit-cross-fade(a,b)",
    "-moz-element(#a)", "a\\b"]) rej(v);
  for (const v of ["u/**/rl(x)", "calc(1px + 2px)", "var(--x)"])
    assert.deepEqual(checkStyleMap({ "--x": v }), { ok: [["--x", v]], rejected: [] }, v);
});

test("значення атрибута: рядок до ліміту або null", () => {
  assert.equal(checkAttrValue("x"), "x");
  assert.equal(checkAttrValue(null), null);
  assert.equal(checkAttrValue("a".repeat(LIMITS.attrVal)), "a".repeat(LIMITS.attrVal));
  for (const v of ["a".repeat(LIMITS.attrVal + 1), 5, undefined, {}])
    assert.throws(() => checkAttrValue(v), (e) => e instanceof PageError && e.code === "bad-args");
});

test("текст, ярлик, тон", () => {
  assert.equal(checkText("abc"), "abc");
  assert.throws(() => checkText("x".repeat(LIMITS.text + 1)), (e) => e.code === "bad-args");
  assert.equal(checkLabel(undefined), "");
  assert.equal(checkLabel(null), "");
  assert.equal(checkLabel("abc"), "abc");
  assert.equal(checkLabel("a".repeat(LIMITS.label)), "a".repeat(LIMITS.label));
  const cut = checkLabel("a".repeat(100));
  assert.equal(Array.from(cut).length, LIMITS.label);
  assert.equal(cut, "a".repeat(LIMITS.label - 1) + "…");
  const emo = checkLabel("😀".repeat(100));
  assert.equal(emo, "😀".repeat(LIMITS.label - 1) + "…");
  assert.doesNotMatch(emo, /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/);
  for (const v of [5, {}, []]) assert.throws(() => checkLabel(v), (e) => e instanceof PageError && e.code === "bad-args");
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

test("журнал: full, монотонні id, повторне add після take, дефолт 500, id запису не перекривається", () => {
  const j = createJournal(2);
  assert.equal(j.full, false);
  j.add({}); j.add({});
  assert.equal(j.full, true);
  j.take("c1");
  assert.equal(j.full, false);
  assert.equal(j.add({}), "c3");
  assert.equal(j.full, true);
  j.takeAll();
  assert.equal(j.add({}), "c4");
  const d = createJournal();
  for (let i = 0; i < 500; i++) d.add({});
  assert.equal(d.full, true);
  assert.throws(() => d.add({}), (e) => e.code === "too-many");
  const k = createJournal(3);
  const id = k.add({ id: "evil", n: 1 });
  assert.deepEqual(k.take(id), { id: "c1", n: 1 });
});

test("журнал: newer(id) — живі записи після id, найстаріші першими; невідомий id і вже забраний → []", () => {
  const j = createJournal(5);
  const a = j.add({ n: 1 }), b = j.add({ n: 2 }), c = j.add({ n: 3 });
  assert.deepEqual(j.newer(a).map((x) => x.n), [2, 3]);
  assert.deepEqual(j.newer(b).map((x) => x.n), [3]);
  assert.deepEqual(j.newer(c), []);
  assert.deepEqual(j.newer("c99"), []);
  assert.deepEqual(j.newer(undefined), []);
  j.take(b);
  assert.deepEqual(j.newer(b), [], "після take — невідомий");
  assert.deepEqual(j.newer(a).map((x) => x.n), [3], "забраний запис більше не «новіший»");
  j.newer(a)[0].n = 30;                                   // живі обʼєкти: передача шару міняє їх
  assert.equal(j.take(c).n, 30);
});

test("stillOurs: відкат лише коли поточне досі «стало»", () => {
  assert.equal(stillOurs("red", "red"), true);
  assert.equal(stillOurs("blue", "red"), false);
  assert.equal(stillOurs(null, null), true);
});

// Статичний охоронець: помічник ніколи не пише розмітку чи код, а `setAttribute` — лише з відомими іменами.
const SAFE_ATTRS = new Set(["data-deai-marks", "data-h2d-ignore"]);
const NEW_FORBIDDEN = [/\bFunction\s*\(/, /setAttribute(NS|Node)\b/, /\.cssText\b/, /createContextualFragment|DOMParser|srcdoc/, /[\w$)\]]\[\s*["'`]/];
const FORBIDDEN = [/innerHTML/, /outerHTML/, /insertAdjacentHTML/, /\beval\(/, /new\s+Function/, /document\.write/, ...NEW_FORBIDDEN];
function guardViolations(raw) {
  const out = [];
  const src = raw.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'])\/\/.*$/gm, "$1");   // коментарі не рахуються
  for (const re of FORBIDDEN) if (re.test(src)) out.push(`forbidden: ${re}`);
  const lines = src.split("\n");
  lines.forEach((line, i) => {
    for (const m of line.matchAll(/setAttribute\(\s*([^,)]*)/g)) {
      const a = m[1].trim();
      const lit = /^"([^"]*)"$/.exec(a);
      if (lit ? SAFE_ATTRS.has(lit[1]) : a === "name") continue;
      out.push(`setAttribute first arg ${a} at line ${i + 1}`);
    }
  });
  // змінна `name` — лише там, де її щойно перевірив attrAllowed
  const named = [...src.matchAll(/setAttribute\(\s*name\b/g)].length;
  if (named && !/attrAllowed\(name\)/.test(src)) out.push("setAttribute(name) without attrAllowed(name)");
  return out;
}

test("охоронець page-agent.js: нема innerHTML/eval/…, setAttribute лише з відомими іменами", () => {
  const src = readFileSync(new URL("../app/page-agent.js", import.meta.url), "utf8");
  assert.deepEqual(guardViolations(src), []);
});

test("охоронець ловить порушення (мутації тексту)", () => {
  const src = readFileSync(new URL("../app/page-agent.js", import.meta.url), "utf8");
  for (const bad of ["el.innerHTML = x;", "el.outerHTML = x;", "el.insertAdjacentHTML('a', x);", "eval(x);", "new Function(x);", "document.write(x);",
    'el.setAttribute("onclick", x);', "el.setAttribute(k, v);", "el.setAttribute(attr, v);"]) {
    assert.ok(guardViolations(`${src}\n${bad}\n`).length > 0, bad);
  }
  assert.ok(/setAttribute\(\s*name/.test(src), "setAttr використовує name");
  assert.ok(guardViolations(src.replace(/attrAllowed\(name\)/g, "ok(name)")).length > 0);
});

test("охоронець: кожен новий шаблон спрацьовує на своїй мутації, а справжній код чистий", () => {
  const src = readFileSync(new URL("../app/page-agent.js", import.meta.url), "utf8");
  const cases = [["Function(x);", NEW_FORBIDDEN[0]], ["globalThis.Function(x);", NEW_FORBIDDEN[0]],
    ["el.setAttributeNS(a, b, c);", NEW_FORBIDDEN[1]], ["el.setAttributeNode(n);", NEW_FORBIDDEN[1]],
    ["el.style.cssText = x;", NEW_FORBIDDEN[2]],
    ["r.createContextualFragment(x);", NEW_FORBIDDEN[3]], ["new DOMParser();", NEW_FORBIDDEN[3]], ["f.srcdoc = x;", NEW_FORBIDDEN[3]],
    ['el["inner" + "HTML"] = x;', NEW_FORBIDDEN[4]], ["el['x'] = 1;", NEW_FORBIDDEN[4]], ["el[`x`] = 1;", NEW_FORBIDDEN[4]],
    ['f()["x"];', NEW_FORBIDDEN[4]], ['a[0]["x"];', NEW_FORBIDDEN[4]], ['a[ "x" ];', NEW_FORBIDDEN[4]]];
  for (const [bad, re] of cases) assert.ok(guardViolations(`${src}\n${bad}\n`).includes(`forbidden: ${re}`), bad);
  assert.equal(guardViolations(src).filter((v) => NEW_FORBIDDEN.some((re) => v === `forbidden: ${re}`)).length, 0);
  assert.deepEqual(guardViolations("for (const [k, v] of [[\"a\", 1], [\"b\", 2]]) {}\nconst m = [\"x\", \"y\"];\n"), [], "масиви-літерали не хибні спрацювання");
});
