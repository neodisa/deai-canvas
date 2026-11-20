/* Набір панелі модуля: кожна змінна, яку читає kit.css, — у KIT_VARS, а кожна з KIT_VARS визначена в оболонці. */
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { KIT_VARS } from "../app/module-kit/kit-vars.js";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "app");
const read = (f) => readFileSync(path.join(APP, f), "utf8");
const strip = (css) => css.replace(/\/\*[\s\S]*?\*\//g, "");

test("every var(--x) used in kit.css is listed in KIT_VARS", () => {
  const used = new Set([...strip(read("module-kit/kit.css")).matchAll(/var\(\s*(--[a-z0-9-]+)/g)].map((m) => m[1]));
  assert.ok(used.size > 5, "kit.css reads shell tokens");
  const missing = [...used].filter((v) => !KIT_VARS.includes(v));
  assert.deepEqual(missing, []);
});

test("every KIT_VARS name is defined in app/styles.css", () => {
  const css = strip(read("styles.css"));
  const undefinedNames = KIT_VARS.filter((v) => !new RegExp("(^|[;{\\s])" + v + "\\s*:", "m").test(css));
  assert.deepEqual(undefinedNames, []);
});

test("KIT_VARS has valid unique names, all of them used by the kit", () => {
  assert.equal(new Set(KIT_VARS).size, KIT_VARS.length);
  const used = new Set([...read("module-kit/kit.css").matchAll(/var\(\s*(--[a-z0-9-]+)/g)].map((m) => m[1]));
  for (const v of KIT_VARS) {
    assert.match(v, /^--[a-z0-9-]{1,60}$/);
    assert.ok(used.has(v), `${v} is listed but kit.css does not read it`);
  }
});

test("kit.css has no color literal outside var() fallbacks", () => {
  const css = strip(read("module-kit/kit.css")).replace(/var\([^)]*\)/g, "var()");
  assert.doesNotMatch(css, /#[0-9a-fA-F]{3,8}\b|\b(rgb|rgba|hsl|oklch)\(/);
});
