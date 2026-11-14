import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import test from "node:test";

import { barModel } from "../app/bar-model.js";
import { setLang } from "../app/i18n.js";
import { paletteActions } from "../app/shell-palette.js";
import { barHTML } from "../app/shell-bar.js";
import { BAR_CASES, PALETTE_CASES, snapshot } from "./_legacy-golden-kit.mjs";

/* «Золотий знімок» простору ЛІГА: розмітка смуги й дії палітри мусять лишитись ТАКИМИ САМИМИ,
   якими були до модулів (Task 8, `capabilities.publish`). Еталони — літерали у
   `tests/fixtures/legacy-golden/`, зняті з коду перед Task 8 етапу 2а (стан після Task 7) і побайтно звірені з поточним
   (`tests/_legacy-golden-kit.mjs` — чому саме так, і як знімали).

   Падіння цього файла — не «оновіть еталон», а питання: ЛІГА змінилась свідомо? Якщо так — перезнімаємо:
   `UPDATE_GOLDEN=1 node --test tests/legacy-golden.test.mjs` і дивимось diff еталонів очима. */

const DIR = new URL("./fixtures/legacy-golden/", import.meta.url);
const UPDATE = process.env.UPDATE_GOLDEN === "1";

const snap = (() => { setLang("uk"); return snapshot({ barModel, barHTML, paletteActions }); })();

function golden(file, actual, parse = (s) => s) {
  if (UPDATE) { writeFileSync(new URL(file, DIR), typeof actual === "string" ? actual : `${JSON.stringify(actual, null, 2)}\n`); return; }
  return parse(readFileSync(new URL(file, DIR), "utf8"));
}

for (const name of Object.keys(BAR_CASES)) {
  test(`ЛІГА: розмітка смуги «${name}» — байт у байт як до модулів`, () => {
    const want = golden(`bar-${name}.html`, snap.bar[name]);
    if (!UPDATE) assert.equal(snap.bar[name], want);
  });
}

for (const name of Object.keys(PALETTE_CASES)) {
  test(`ЛІГА: дії палітри «${name}» — ті самі, в тому самому порядку, з тими самими полями`, () => {
    const want = golden(`palette-${name}.json`, snap.palette[name], JSON.parse);
    if (!UPDATE) assert.deepEqual(snap.palette[name], want);
  });
}

test("знімок справді знімає ЛІГА: у ньому GitLab, пароль, Teams і застереження про публічність", () => {
  const h = snap.bar["pub-published"];
  for (const s of ['data-dd="gl"', 'data-act="pubpw"', 'data-act="teamsnotify"', 'class="dd-note"', 'data-act="publish"']) {
    assert.ok(h.includes(s), `в еталоні ЛІГА нема ${s} — він знімав не те`);
  }
  const ids = snap.palette.behind.map((a) => a.id);
  for (const id of ["publish", "togglepub", "copylink", "openpreview", "glpull", "glpush"]) {
    assert.ok(ids.includes(id), `в палітрі еталона ЛІГА нема «${id}»`);
  }
});
