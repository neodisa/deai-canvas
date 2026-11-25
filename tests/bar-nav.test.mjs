import assert from "node:assert/strict";
import test from "node:test";
import { barModel } from "../app/bar-model.js";
import { setLang } from "../app/i18n.js";
import { barHTML } from "../app/shell-bar.js";

setLang("uk");
const base = { mode: "layout", view: "grid", vp: "desktop", vpw: "", taskId: "t1", taskTitle: "Задача", hasIteration: true, iterLabel: "Іт.1", iterList: [{ id: "it1", label: "Іт.1" }], iterId: "it1" };

test("0.40: без стану `nav` смуга лишається такою, як була (золоті знімки ЛІГИ не зсуваються)", () => {
  const m = barModel(base);
  assert.ok(!m.zone1.some((x) => x.id === "nav"));
  assert.ok(!barHTML(m, base).includes('data-act="navback"'));
});

test("0.40: зі станом `nav` елемент стоїть ПЕРШИМ у зоні 1; ← → вимикаються за станом", () => {
  const s = { ...base, nav: { back: false, fwd: true } };
  const m = barModel(s);
  assert.equal(m.zone1[0].id, "nav");
  assert.equal(m.zone1[0].backOff, true);
  assert.equal(m.zone1[0].fwdOff, false);
  const h = barHTML(m, s);
  assert.match(h, /<button[^>]*data-act="navback"[^>]*disabled/);
  assert.doesNotMatch(h, /<button[^>]*data-act="navfwd"[^>]*disabled/);
  assert.ok(h.indexOf('data-act="navback"') < h.indexOf('class="crumbs"'), "кнопки перед крихтами");
  assert.match(h, /data-act="navreload"/);
});

test("0.40: на екрані «Задачі» (домівка) кнопок нема", () => {
  const s = { ...base, homeOpen: true, homePage: "tasks", nav: { back: true, fwd: true } };
  assert.ok(!barHTML(barModel(s), s).includes('data-act="navback"'));
});

test("0.40: id контролів унікальні й у присутності nav", () => {
  const m = barModel({ ...base, nav: { back: true, fwd: true } });
  const ids = [...m.zone1, ...m.zone2, ...m.zone3].map((x) => x.id);
  assert.equal(new Set(ids).size, ids.length);
});
