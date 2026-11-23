/**
 * Панель коментарів ЗОВНІШНЬОГО превʼю (0.32.0, Task 3): ті самі `commentsPanelHTML`/`cardHTML`, але з правами:
 * «Показати» всім; «Редагувати»/«Видалити» лише своїм (`isOwn`); закриті — без жодних дій; нема закрити/відкрити/доручити.
 * Типову розмітку Deai (без опцій) стереже `comments-view-default.test.mjs`.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { commentsPanelHTML } from "../app/comments-view.js";
import { setLang } from "../app/i18n.js";

setLang("uk");
const C = (o) => ({ id: o.id, n: o.n, text: o.text || "т", author: o.author || "Автор А", ts: "13.11.2026 10:00",
  status: o.status || "open", scope: o.scope || "current", where: "here", iter: "3",
  resolvedV: o.resolvedV ?? null, resolveReason: o.resolveReason ?? null, meta: o.meta || {}, _aud: o._aud });
const ACTIONS = { any: ["cmtshow"], own: ["cmtedit", "cmtdel"], closed: [] };
const base = (comments, over = {}) => ({ snapshot: { iteration: "3", comments }, query: "", selectedId: null, editingId: null,
  delAsk: null, expanded: { earlier: true, closed: true }, filter: "all", dual: false, teamDown: null, fresh: null, down: null,
  isOwn: (c) => c.id === "mine", actions: ACTIONS, ...over });
const card = (html, id) => new RegExp(`<article class="cmt-card[^"]*" data-cid="${id}">[\\s\\S]*?</article>`).exec(html)?.[0] ?? "";
const acts = (html) => [...html.matchAll(/data-act="(cmt[a-z]+)"/g)].map((m) => m[1]);

test("своя відкрита картка: Показати + Редагувати + Видалити, без Закрити", () => {
  const html = commentsPanelHTML(base([C({ id: "mine", n: 2 })]));
  assert.deepEqual(acts(card(html, "mine")), ["cmtshow", "cmtedit", "cmtdel"]);
  assert.equal(html.includes('data-act="cmtres"'), false);
});

test("чужа відкрита картка: лише Показати", () => {
  const html = commentsPanelHTML(base([C({ id: "other", n: 1 })]));
  assert.deepEqual(acts(card(html, "other")), ["cmtshow"]);
});

test("закрита картка: «Зроблено · Іт.N» і причина, жодних дій і порожнього рядка дій — навіть своя", () => {
  const html = commentsPanelHTML(base([C({ id: "mine", n: 3, status: "resolved", resolvedV: 2, resolveReason: "Кнопку збільшено" })]));
  const c = card(html, "mine");
  assert.match(c, /Зроблено · Іт\.2/);
  assert.match(c, /Кнопку збільшено/);
  assert.deepEqual(acts(c), []);
  assert.equal(c.includes("cmt-acts"), false, "порожній рядок дій лишився в закритій картці");
  for (const bad of ["cmtreopen", "cmtres", "cmtdel", "cmtedit"]) assert.equal(html.includes(`data-act="${bad}"`), false, bad);
});

test("попередня ітерація: чужа без дій, своя лише з Видалити; «Перенести» нема ніколи", () => {
  const html = commentsPanelHTML(base([C({ id: "mine", n: 2, scope: "earlier" }), C({ id: "other", n: 1, scope: "earlier" })]));
  assert.deepEqual(acts(card(html, "mine")), ["cmtdel"]);
  assert.deepEqual(acts(card(html, "other")), []);
  assert.equal(html.includes("cmtcarry"), false);
});

test("dual:false — ні чипів адресата, ні «Доручити AI», ні значка", () => {
  const html = commentsPanelHTML(base([C({ id: "mine", n: 1, _aud: "project", meta: { assignee: "claude" } })]));
  for (const bad of ["cmtassign", "cmtunassign", "cmt-aud", "cmt-badge", "cmt-filter", "cmtfilter"]) {
    assert.equal(html.includes(bad), false, bad);
  }
});

test("питання «Видалити» на своїй картці лишається; редагування своєї — textarea", () => {
  const ask = commentsPanelHTML(base([C({ id: "mine", n: 1 })], { delAsk: "mine" }));
  assert.match(ask, /data-act="cmtdelyes" data-val="mine"/);
  const edit = commentsPanelHTML(base([C({ id: "mine", n: 1, text: "було" })], { editingId: "mine" }));
  assert.match(edit, /<textarea class="cmt-edit"[^>]*>було<\/textarea>/);
});

test("кнопка «Додати коментар» у шапці: є лише з `adding`, натиснута, коли режим увімкнено", () => {
  const off = commentsPanelHTML(base([], { adding: false }));
  assert.match(off, /data-act="cmtadd"[^>]*aria-pressed="false"/);
  const on = commentsPanelHTML(base([], { adding: true }));
  assert.match(on, /data-act="cmtadd"[^>]*aria-pressed="true"/);
  assert.equal(commentsPanelHTML(base([], { adding: undefined })).includes("cmtadd"), false, "без опції кнопки нема");
});

test("без `isOwn` усі картки чужі (нічого не вгадуємо)", () => {
  const html = commentsPanelHTML(base([C({ id: "mine", n: 1 })], { isOwn: undefined }));
  assert.deepEqual(acts(card(html, "mine")), ["cmtshow"]);
});

test("відповіді: `repliesNote: false` ховає примітку «Відповіді недоступні» (превʼю — тихо); без прапора примітка лишається", () => {
  const withReplies = (o) => base([C({ id: "mine", n: 1 })], { threads: new Set(["mine"]), repliesOff: () => "off", ...o });
  assert.match(commentsPanelHTML(withReplies({})), /class="cmt-rnote"/, "Deai: примітка лишилась без прапора");
  const quiet = commentsPanelHTML(withReplies({ repliesNote: false }));
  assert.equal(quiet.includes("cmt-rnote"), false, "прапор не прибрав примітку");
  for (const bad of ["cmt-rta", 'data-act="cmtreply"']) assert.equal(quiet.includes(bad), false, bad);
  // прапор не вимикає поле, коли відповіді ввімкнені
  const on = commentsPanelHTML(base([C({ id: "mine", n: 1 })], { threads: new Set(["mine"]), repliesOff: () => null, repliesNote: false }));
  assert.match(on, /data-act="cmtreply" data-val="mine"/);
});
