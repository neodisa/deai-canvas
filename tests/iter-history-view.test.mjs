import assert from "node:assert/strict";
import test from "node:test";
import { histHTML, dayKey } from "../app/iter-history-view.js";
import { setLang } from "../app/i18n.js";

const NOW = new Date("2026-11-23T15:00:00");
const E = (o) => ({ sha: "a", at: "2026-11-23T14:32:00", actor: { kind: "person", name: "Олена Д." }, kind: "other",
  args: {}, text: "", files: [], more: 0, ...o });

test("групи днів: Сьогодні, Вчора, ДД.ММ.РРРР", () => {
  setLang("uk");
  assert.equal(dayKey("2026-11-23T09:00:00", NOW), "Сьогодні");
  assert.equal(dayKey("2026-11-22T23:59:00", NOW), "Вчора");
  assert.equal(dayKey("2026-11-20T10:00:00", NOW), "20.11.2026");
});

test("шапка, записи, AI фіолетовий, файли з «ще N», час ГГ:ХХ", () => {
  setLang("uk");
  const h = histHTML({ label: "Іт.5", entries: [
    E({ kind: "ai", actor: { kind: "ai", name: "AI" }, args: { synced: false }, files: ["a.html", "b.css"], more: 2 }),
    E({ at: "2026-11-21T18:40:00", kind: "copy", args: { from: "it4", note: "Мобільна" } }),
  ], pending: null }, { now: NOW });
  assert.match(h, /<span class="panel-title">Історія · Іт\.5<\/span>/);
  assert.match(h, /data-act="histclose"/);
  assert.match(h, /<span class="hist-av hist-av--ai">AI<\/span>/);
  assert.match(h, /Макет змінено/);
  assert.match(h, /a\.html · b\.css · ще 2/);
  assert.match(h, /<span class="hist-time">14:32<\/span>/);
  assert.match(h, /Створено як копію Іт\.4 · Мобільна/);
  assert.match(h, /<span class="hist-av">ОД<\/span>/);
  assert.ok(h.indexOf("Сьогодні") < h.indexOf("21.11.2026"));
});

test("незаписані зміни — першими, без автора", () => {
  setLang("uk");
  const h = histHTML({ label: "Іт.5", entries: [E({ kind: "publish" })], pending: { files: ["x.html"], more: 0, at: "2026-11-23T14:50:00" } }, { now: NOW });
  assert.ok(h.indexOf("Незаписані зміни") < h.indexOf("Опубліковано"));
  assert.match(h, /hist-e--pending/);
});

test("невідома тема — як є; недоступна історія — один рядок; текст екранується", () => {
  setLang("uk");
  const h = histHTML({ label: "Іт.1", entries: [E({ kind: "other", text: "<b>x</b>" })], pending: null, degraded: true }, { now: NOW });
  assert.match(h, /&lt;b&gt;x&lt;\/b&gt;/);
  assert.match(h, /Історія недоступна/);
});

test("усі види записів мають текст; en і uk; порожня назва = «Назву прибрано»", () => {
  setLang("uk");
  const kinds = [
    ["merge", { from: ["it2", "it3"] }, /Іт\.2, Іт\.3/], ["rename", { name: "" }, /Назву прибрано/],
    ["rename", { name: "Категорія" }, /«Категорія»/], ["delete", {}, /Переміщено в кошик/],
    ["restore", {}, /Повернуто з кошика/], ["page-new", { name: "Каталог" }, /Додано сторінку «Каталог»/],
    ["page-rename", { name: "X" }, /перейменовано/], ["page-move", { name: "X" }, /переміщено/],
    ["tree", {}, /дерево сторінок/], ["sync", {}, /Синхронізовано з GitLab/],
    ["ai", { synced: true }, /Макет змінено · у GitLab/], ["create", { note: "н" }, /Створено · н/],
  ];
  for (const [kind, args, re] of kinds) assert.match(histHTML({ label: "Іт.5", entries: [E({ kind, args })] }, { now: NOW }), re, kind);
  setLang("en");
  const h = histHTML({ label: "It.5", entries: [E({ kind: "publish" }), E({ kind: "copy", args: { from: "it4", note: "" } })] }, { now: NOW });
  assert.match(h, /History · It\.5/);
  assert.match(h, /Published to preview/);
  assert.match(h, /Created as a copy of It\.4</);
  assert.match(h, /Today/);
  setLang("uk");
});
