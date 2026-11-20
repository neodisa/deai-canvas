import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ICONS } from "../app/icons.js";

/*
 * The module manifest validator (app/deai_modules.py, core_icons) parses icon
 * names out of app/icons.js with a line regex. This test keeps that regex and
 * the real ICONS object in step: a new icon written in a shape the regex
 * misses would make every manifest that names it fail.
 */
const RE = /^ {2}([a-z][a-zA-Z0-9]*): `/gm;

test("icon names parsed by the manifest validator regex equal the ICONS keys", () => {
  const text = readFileSync(new URL("../app/icons.js", import.meta.url), "utf8");
  const names = [...text.matchAll(RE)].map((m) => m[1]);
  assert.ok(names.length > 10);
  assert.deepEqual(names, Object.keys(ICONS));
});
