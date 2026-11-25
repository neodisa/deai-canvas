/** Пороги `TIERS` парні з контейнерними запитами `styles.css`: ярус у моделі й правило в CSS не розходяться (мутація: змінити число в одному з двох). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { TIERS } from "../app/bar-model.js";

const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
/** Ширина `@container (max-width:Npx)`, у блоці якого є `sel`. */
const widthOf = (sel) => {
  const re = /@container \(max-width:(\d+)px\)\s*\{([^}]*(?:\}[^}]*?)?)\}/g;
  const found = [];
  for (const m of css.matchAll(re)) if (m[2].includes(sel)) found.push(Number(m[1]));
  return found;
};

for (const [tier, sel] of [["gl", ".lbl-gl{"], ["mode", ".lbl-mode,"], ["viewLabel", ".lbl-view{"], ["viewWhy", ".zone-2x .seg .dd-why{display:none}"], ["view", ".view-extra{"]]) {
  test(`TIERS.${tier} = ${TIERS[tier]} збігається з контейнерним запитом для «${sel}»`, () => {
    assert.deepEqual(widthOf(sel), [TIERS[tier]]);
  });
}
