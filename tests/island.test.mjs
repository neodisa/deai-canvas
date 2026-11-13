import assert from "node:assert/strict";
import test from "node:test";
import { setLang } from "../app/i18n.js";
import { islandToolsHTML } from "../app/island.js";

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
  assert.match(on, /data-act="inspector" aria-pressed="true" aria-label="Інспектор" title="Інспектор · I"/);
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
