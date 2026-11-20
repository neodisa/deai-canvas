import assert from "node:assert/strict";
import test from "node:test";
import { setLang } from "../app/i18n.js";
import { islandToolsHTML } from "../app/island.js";
import { ICONS } from "../app/icons.js";

setLang("uk");
const acts = (h) => [...h.matchAll(/data-act="([a-z]+)"/g)].map((m) => m[1]);

test("«Макет»: інспектор, роздільник, баг — баг останній", () => {
  const h = islandToolsHTML({ screen: "task", mode: "layout", inspectorOn: false });
  assert.deepEqual(acts(h), ["comments", "inspector", "feedback"]);
  assert.ok(h.indexOf("isl-sep") > h.indexOf('data-act="inspector"'));
});

test("«Огляд»: коментарі є, інспектора нема (знімки, не живий DOM)", () => {
  assert.deepEqual(acts(islandToolsHTML({ screen: "task", mode: "overview" })), ["comments", "feedback"]);
});

test("«Задачі» / «Налаштування»: лише баг", () => {
  assert.deepEqual(acts(islandToolsHTML({ screen: "home", mode: "layout" })), ["feedback"]);
});

test("інспектор — перемикач: aria-pressed за станом; імена й підказки з клавішею", () => {
  const on = islandToolsHTML({ screen: "task", mode: "layout", inspectorOn: true });
  assert.match(on, /data-act="inspector" aria-pressed="true" aria-label="Інспектор" title="Інспектор · I · Alt — відстані · Esc \/ ↵ — батько \/ дочірній · ← → — сусід"/);
  assert.match(on, /data-act="feedback" aria-label="Баг \/ ідея" title="Баг \/ ідея"/);
  assert.match(islandToolsHTML({ screen: "task", mode: "layout", inspectorOn: false }), /aria-pressed="false"/);
});

test("кнопка «Коментарі» — у задачі в обох видах, перед інспектором; число відкритих", () => {
  const lay = islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true, commentsCount: 3 });
  assert.match(lay, /data-act="comments" aria-pressed="true"/);
  assert.ok(lay.indexOf('data-act="comments"') < lay.indexOf('data-act="inspector"'));
  assert.match(lay, /<span class="isl-count" aria-hidden="true">3<\/span>/);
  const ov = islandToolsHTML({ screen: "task", mode: "overview", commentsCount: 0 });
  assert.match(ov, /data-act="comments" aria-pressed="false"/);
  assert.equal(ov.includes("isl-count"), false);
  assert.equal(ov.includes('data-act="inspector"'), false);
  assert.equal(islandToolsHTML({ screen: "home" }).includes('data-act="comments"'), false);
  assert.match(islandToolsHTML({ screen: "task", mode: "layout", commentsCount: 120 }), />99\+</);
});

test("нові від команди: isl-count--new із числом нових і своїм aria-label; без нових — як було", () => {
  const h = islandToolsHTML({ screen: "task", mode: "layout", commentsCount: 5, commentsNew: 2 });
  assert.match(h, /<span class="isl-count isl-count--new" aria-hidden="true">2<\/span>/);
  assert.match(h, /aria-label="Коментарі: нових від команди — 2"/);
  assert.equal(/class="isl-count"/.test(h), false);
  const none = islandToolsHTML({ screen: "task", mode: "layout", commentsCount: 5, commentsNew: 0 });
  assert.match(none, /<span class="isl-count" aria-hidden="true">5<\/span>/);
  assert.equal(none.includes("isl-count--new"), false);
  assert.match(islandToolsHTML({ screen: "task", mode: "layout", commentsNew: 150 }), /isl-count--new" aria-hidden="true">99\+</);
});

/* ---- T11: режими коментування в острівці ---- */
const TOOL = { mode: "element", freeze: true, modes: ["element", "text", "multi", "area"], canFreeze: true };
const modeActs = (h) => [...h.matchAll(/data-act="cmtmode" data-val="([a-z]+)"/g)].map((m) => m[1]);

test("режими: лише коли коментування ввімкнено, є інструмент і режимів > 1; на «Огляді», «Задачах», без інструмента — нема", () => {
  const base = { screen: "task", mode: "layout", commentsOn: true, commentTool: TOOL };
  assert.deepEqual(modeActs(islandToolsHTML(base)), ["element", "text", "multi", "area"]);
  assert.equal(islandToolsHTML({ ...base, commentsOn: false }).includes("cmtmode"), false);
  assert.equal(islandToolsHTML({ ...base, commentTool: null }).includes("cmtmode"), false);
  assert.equal(islandToolsHTML({ ...base }).includes("cmtmode"), true);
  const ov = islandToolsHTML({ ...base, mode: "overview", commentTool: { mode: "element", freeze: false, modes: ["element"], canFreeze: false } });
  assert.equal(ov.includes("cmtmode") || ov.includes("cmtfreeze"), false, "на «Огляді» режимів і заморозки нема");
  assert.equal(islandToolsHTML({ ...base, screen: "home" }).includes("cmtmode"), false);
});

test("режими: натиснутий — за mode; невідомий режим у modes відкидається; тільки відомі іконки", () => {
  const h = islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true,
    commentTool: { ...TOOL, mode: "multi", modes: ["element", "bogus", "multi"] } });
  assert.deepEqual(modeActs(h), ["element", "multi"]);
  assert.match(h, /data-act="cmtmode" data-val="multi" aria-pressed="true"/);
  assert.match(h, /isl-btn isl-btn--on" data-act="cmtmode" data-val="multi"/);
  assert.match(h, /data-act="cmtmode" data-val="element" aria-pressed="false"/);
  for (const id of [...h.matchAll(/#i-([a-z]+)/g)].map((m) => m[1])) assert.ok(ICONS[id], `іконки «${id}» нема у спрайті`);
});

test("режими: лише власні ключі MODE_ICON; фільтр перед порогом > 1; на «Огляді» без режимів", () => {
  const mk = (modes, over = {}) => islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true, commentTool: { ...TOOL, modes }, ...over });
  for (const bad of ["constructor", "__proto__", "toString", "hasOwnProperty"]) {
    assert.deepEqual(modeActs(mk(["element", bad, "text"])), ["element", "text"], bad);
  }
  /* один відомий + сміття: самотньої кнопки й зайвих роздільників нема */
  const lone = mk(["element", "bogus"]);
  assert.equal(lone.includes("cmtmode"), false);
  assert.equal(lone.includes("isl-modes"), false);
  assert.equal(mk(["constructor", "__proto__"]).includes("cmtmode"), false);
  assert.equal(mk(["element", 7, null, {}, "text"]).includes('data-val="7"'), false);
  /* явно «Огляд»: режими не малюються, навіть якщо інструмент каже 4 */
  assert.equal(mk(["element", "text", "multi", "area"], { mode: "overview" }).includes("cmtmode"), false);
  assert.equal(mk(["element", "text", "multi", "area"], { mode: "overview" }).includes("cmtfreeze"), false);
});

test("заморозка: aria-pressed і isl-freeze--on за freeze; canFreeze:false — кнопки нема", () => {
  const on = islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true, commentTool: TOOL });
  assert.match(on, /isl-freeze isl-freeze--on" data-act="cmtfreeze" aria-pressed="true"/);
  const off = islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true, commentTool: { ...TOOL, freeze: false } });
  assert.match(off, /data-act="cmtfreeze" aria-pressed="false"/);
  assert.equal(off.includes("isl-freeze--on"), false);
  const none = islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true, commentTool: { ...TOOL, canFreeze: false } });
  assert.equal(none.includes("cmtfreeze"), false);
  assert.ok(none.includes("cmtmode"));
});

test("порядок: коментарі, режими, заморозка, інспектор, баг; режими в групі з aria-label", () => {
  const h = islandToolsHTML({ screen: "task", mode: "layout", commentsOn: true, commentTool: TOOL });
  assert.deepEqual(acts(h), ["comments", "cmtmode", "cmtmode", "cmtmode", "cmtmode", "cmtfreeze", "inspector", "feedback"]);
  assert.match(h, /<div class="isl-modes" role="group" aria-label="Режим коментування">/);
});

/* ---- 0.32.0 Task 2: острівець превʼю (набір кнопок) ---- */
const SEP = '<span class="isl-sep" aria-hidden="true"></span>';
const CMT_BTN = (on, n) => `<button class="isl-btn${on ? " isl-btn--on" : ""}" data-act="comments" aria-pressed="${on}" aria-label="${n ? `Коментарі, відкритих: ${n}` : "Коментарі"}" title="Коментарі · C"><svg class="ico" width="16" height="16" aria-hidden="true"><use href="#i-comment"/></svg>${n ? `<span class="isl-count" aria-hidden="true">${n}</span>` : ""}</button>`;
const INSP_BTN = (on) => `<button class="isl-btn${on ? " isl-btn--on" : ""}" data-act="inspector" aria-pressed="${on}" aria-label="Інспектор" title="Інспектор · I · Alt — відстані · Esc / ↵ — батько / дочірній · ← → — сусід"><svg class="ico" width="16" height="16" aria-hidden="true"><use href="#i-inspect"/></svg></button>`;
const BUG_BTN = '<button class="isl-btn" data-act="feedback" aria-label="Баг / ідея" title="Баг / ідея"><svg class="ico" width="16" height="16" aria-hidden="true"><use href="#i-bug"/></svg></button>';
const CLEAN_BTN = '<button class="isl-btn" data-act="clean" aria-label="Сховати інтерфейс" title="Сховати інтерфейс (⇧⌘\\)"><svg class="ico" width="16" height="16" aria-hidden="true"><use href="#i-clean"/></svg></button>';

test("Deai без опції `tools` — розмітка байт у байт як до 0.32.0", () => {
  assert.equal(islandToolsHTML({ screen: "task", mode: "layout", inspectorOn: true, commentsOn: true, commentsCount: 3 }),
    CMT_BTN(true, 3) + INSP_BTN(true) + SEP + BUG_BTN);
  assert.equal(islandToolsHTML({ screen: "task", mode: "overview", commentsNew: 2 }),
    `<button class="isl-btn" data-act="comments" aria-pressed="false" aria-label="Коментарі: нових від команди — 2" title="Коментарі · C"><svg class="ico" width="16" height="16" aria-hidden="true"><use href="#i-comment"/></svg><span class="isl-count isl-count--new" aria-hidden="true">2</span></button>` + SEP + BUG_BTN);
  assert.equal(islandToolsHTML({ screen: "home" }), BUG_BTN);
});

test("превʼю: `tools: ['clean']` — одна кнопка, без «баг», без AI і без зайвих роздільників", () => {
  const h = islandToolsHTML({ tools: ["clean"] });
  assert.equal(h, CLEAN_BTN);
  assert.deepEqual(acts(h), ["clean"]);
  assert.equal(h.includes("isl-sep"), false);
});

test("превʼю: `tools: ['cmt','insp','clean']` — три кнопки по порядку, роздільник лише між групами", () => {
  const h = islandToolsHTML({ tools: ["cmt", "insp", "clean"], commentsCount: 2, inspectorOn: true });
  assert.deepEqual(acts(h), ["comments", "inspector", "clean"]);
  assert.equal(h, CMT_BTN(false, 2) + INSP_BTN(true) + SEP + CLEAN_BTN);
  assert.equal(h.includes('data-act="feedback"'), false);
  assert.equal(h.includes("claude"), false);
  assert.equal(h.endsWith(SEP), false);
  assert.deepEqual(acts(islandToolsHTML({ tools: ["insp", "clean"] })), ["inspector", "clean"]);
});

test("превʼю: невідомі імена в `tools` ігноруються; порожній набір — порожній рядок", () => {
  assert.deepEqual(acts(islandToolsHTML({ tools: ["clean", "bug", "zzz"] })), ["clean"]);
  assert.equal(islandToolsHTML({ tools: [] }), "");
});

test("превʼю: без `clean` роздільника нема (нічого після нього — хвостового роздільника не буває)", () => {
  assert.equal(islandToolsHTML({ tools: ["cmt", "insp"] }), CMT_BTN(false, 0) + INSP_BTN(false));
});
