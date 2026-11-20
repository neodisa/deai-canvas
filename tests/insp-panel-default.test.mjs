/**
 * Охоронець «Deai без змін» (0.32.0, Task 4): `panelHTML` і `inspectHTML` отримали опцію `readonly` для превʼю, і без неї їхній
 * вихід мусить лишитись БАЙТ У БАЙТ таким, яким був до неї. Знято ДО правки (коміт e6631a8): sha256 повного рядка розмітки на
 * дев'яти сценаріях. Змінилась розмітка свідомо — перезніми хеші разом із причиною в коміті; змінилась мовчки — тест червоний.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { setLang } from "../app/i18n.js";
import { panelHTML } from "../app/insp-panel.js";
import { inspectHTML } from "../app/shell-inspect.js";
import { F, FULL_MODEL, MIN_MODEL } from "./_insp-fixtures.mjs";

setLang("uk");
const sha = (s) => createHash("sha256").update(s).digest("hex");

const grid = () => { const m = FULL_MODEL(); m.layout = { kind: "grid", dir: "row", ax: -1, ay: -1, gap: F() }; return m; };
const sides = () => {
  const m = FULL_MODEL();
  const P = (id, prop) => F({ id, props: [prop] });
  m.spacing = { ...m.spacing, sides: true,
    pad: { top: P("pt", "padding-top"), right: P("pr", "padding-right"), bottom: P("pb", "padding-bottom"), left: P("pl", "padding-left") },
    mar: { top: P("mt", "margin-top"), right: P("mr", "margin-right"), bottom: P("mb", "margin-bottom"), left: P("ml", "margin-left") } };
  return m;
};
const noFill = () => { const m = FULL_MODEL(); m.stroke = null; m.fill = null; m.fillAdd = { value: "#FFFFFF", token: "" }; return m; };
const mixed = () => {
  const m = MIN_MODEL();
  m.size = { w: F({ id: "w", props: ["width"], mixed: true, value: "", verdict: "unlinked", token: "" }),
    h: F({ id: "h", props: ["height"], kind: "ro", value: "auto", verdict: "token", token: "sp-1" }) };
  return m;
};

const PANEL = { full: FULL_MODEL(), min: MIN_MODEL(), grid: grid(), sides: sides(), nofill: noFill(), mixed: mixed() };
const S = (o = {}) => ({ shellMode: "layout", on: true, model: FULL_MODEL(), tune: null, tuneOther: 0, tuneMissing: [], ...o });

const GOLDEN = {
  "panel:full": "5adabbea13470ea2c9dfe966bfcee9cc401db0899395353a9b97b0ba2dfd22eb",
  "panel:min": "8bfffd587b6e93482d319651138b76699610486807e6e27d1fcbae2d550d8a8b",
  "panel:grid": "9549821faa560af7bcdde31fbb94b180fab79a0a38bca6e5f1a8b1eddf3336cb",
  "panel:sides": "f55871367eed1289b123a6ddfde5564ad55e0d534d12cb9c96d52b2b8d3c2f4f",
  "panel:nofill": "77ab0e3ebc654b13e199e374305249ef594bdcb15dd99dfa997f44c570e4f8e5",
  "panel:mixed": "4cebb1ba4b84e3308a153bb7f0b37a3a6da21ad6935e8a9e04903e4693e56375",
  "panel:null": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "inspect:full": "f2e99419709205bb93e2133154d7b3dae2f6ba9fe6fb8f977958711c4bb88590",
  "inspect:nomodel": "66410e0a0640e42f48b58df6dfaf58552273c8a51d80d727c30e65dd324f7281",
};

for (const [name, m] of Object.entries(PANEL)) {
  test(`типова панель не змінилась: ${name}`, () => assert.equal(sha(panelHTML(m)), GOLDEN[`panel:${name}`]));
}
test("типова панель не змінилась: без моделі", () => assert.equal(sha(panelHTML(null)), GOLDEN["panel:null"]));
test("типова панель не змінилась: порожній обʼєкт опцій теж типовий", () => {
  assert.equal(sha(panelHTML(FULL_MODEL(), {})), GOLDEN["panel:full"]);
  assert.equal(sha(panelHTML(FULL_MODEL(), { readonly: false })), GOLDEN["panel:full"]);
});
test("типова оболонка панелі не змінилась: з моделлю", () => assert.equal(sha(inspectHTML(S())), GOLDEN["inspect:full"]));
test("типова оболонка панелі не змінилась: без моделі", () => assert.equal(sha(inspectHTML(S({ model: null }))), GOLDEN["inspect:nomodel"]));
