/**
 * Гілка відповідей у картці панелі коментарів (0.35, Task 7a): розмітка, права, «Без знімка: …» і ЕТАЛОН сумісності.
 * Еталон (`_comments-view-golden.json`) знято з коду ДО змін: без нових полів `st` розмітка — байт у байт та сама, навіть
 * коли коментарі несуть `replies`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { commentsPanelHTML } from "../app/comments-view.js";
import { DICT, setLang, t } from "../app/i18n.js";

setLang("uk");
const GOLD = JSON.parse(readFileSync(new URL("./_comments-view-golden.json", import.meta.url), "utf8"));

const REPLIES = [
  { id: "r1", author: "Автор Б", text: "Так <b>one</b>", ts: "19.11.2026 12:05" },
  { id: "r2", author: "AI", agent: true, text: "Готово", ts: "19.11.2026 12:31", editedTs: "19.11.2026 12:40" },
];
const C = (o) => ({ id: o.id, n: o.n, text: o.text || "т", author: o.author || "Автор А", ts: "13.11.2026 10:00",
  status: o.status || "open", scope: o.scope || "current", where: o.where || "here", iter: o.iter || "3",
  resolvedV: o.resolvedV ?? null, resolveReason: o.resolveReason ?? null, meta: o.meta || {},
  ...(o.replies ? { replies: o.replies } : {}), ...(o._aud ? { _aud: o._aud } : {}) });
const base = (over = {}) => ({ snapshot: null, query: "", selectedId: null, editingId: null, expanded: { earlier: true, closed: true },
  filter: "all", dual: false, teamDown: null, fresh: null, down: null, ...over });
const snap = (...comments) => ({ version: "3", iteration: "3", comments });
const view = (comments, over = {}) => commentsPanelHTML(base({ snapshot: snap(...comments), ...over }));
/** Опт-ін гілки: `threads` — Set; права за замовчуванням — «моя» лише `r1`, видаляти можна будь-яку. */
const th = (ids = [], over = {}) => ({ threads: new Set(ids), repliesOff: () => null, isOwnReply: (r) => r.id === "r1", canDeleteReply: () => true, ...over });

/* ── Еталон ── */
const snapA = snap(C({ id: "a", n: 1 }), C({ id: "b", n: 2, meta: { sel: "x", shot: "data:image/png;base64,AAAA" } }));
const snapB = snap(C({ id: "a", n: 1, replies: REPLIES }),
  C({ id: "b", n: 2, replies: REPLIES, status: "resolved", resolvedV: 2, resolveReason: "ok", meta: { resolvedAt: 5 } }),
  C({ id: "c", n: 3, replies: REPLIES, scope: "earlier" }), C({ id: "d", n: 4, replies: [] }));
const snapC = snap(C({ id: "p", n: 1, _aud: "project", replies: REPLIES, meta: { assignee: "claude" } }), C({ id: "l", n: 2, replies: REPLIES }));

test("ЕТАЛОН: без нових полів st картка без відповідей і картки З відповідями — байт у байт як до 0.35", () => {
  assert.equal(commentsPanelHTML(base({ snapshot: snapA })), GOLD.noReplies);
  assert.equal(commentsPanelHTML(base({ snapshot: snapB })), GOLD.withReplies);
  assert.equal(commentsPanelHTML(base({ snapshot: snapB, delAsk: "a" })), GOLD.withRepliesDelAsk);
  assert.equal(commentsPanelHTML(base({ snapshot: snapB, editingId: "a", selectedId: "d" })), GOLD.withRepliesEditing);
  assert.equal(commentsPanelHTML(base({ snapshot: snapC, dual: true })), GOLD.dual);
  assert.equal(commentsPanelHTML(base({ snapshot: snapB, actions: { any: ["cmtshow"], own: ["cmtedit"], closed: [] }, isOwn: (c) => c.id === "a" })), GOLD.rights);
  for (const k of Object.keys(GOLD)) assert.equal(GOLD[k].includes("cmt-thread"), false, `${k}: в еталоні гілки нема`);
});

/* ── Множина ── */
test("cmtReplies: українська множина 1/2/5/11/21/22; англійська", () => {
  const uk = [1, 2, 5, 11, 21, 22].map((n) => t("cmtReplies", n));
  assert.deepEqual(uk, ["1 відповідь", "2 відповіді", "5 відповідей", "11 відповідей", "21 відповідь", "22 відповіді"]);
  assert.deepEqual([1, 2, 5, 11, 21, 22].map((n) => t("cfmDelCmtReplies", n).replace("Видалити назавжди разом із ", "")),
    ["1 відповіддю?", "2 відповідями?", "5 відповідями?", "11 відповідями?", "21 відповіддю?", "22 відповідями?"]);
  setLang("en");
  try { assert.deepEqual([1, 2].map((n) => t("cmtReplies", n)), ["1 reply", "2 replies"]); assert.equal(t("cfmDelCmtReplies", 1), "Delete permanently along with 1 reply?"); }
  finally { setLang("uk"); }
});

test("cmtReplyNew: «+N нова/нові/нових» за українською множиною 1/3/5/11/21; англійська «+N new»", () => {
  assert.deepEqual([1, 3, 5, 11, 21].map((n) => t("cmtReplyNew", n)), ["+1 нова", "+3 нові", "+5 нових", "+11 нових", "+21 нова"]);
  setLang("en");
  try { assert.deepEqual([1, 3].map((n) => t("cmtReplyNew", n)), ["+1 new", "+3 new"]); }
  finally { setLang("uk"); }
});

test("тексти 0.35: однакові ключі в uk і en", () => {
  for (const k of Object.keys(DICT.uk).filter((x) => /^(cmtRepl|cfmDelReply|cfmDelCmtReplies|cmtShotMiss_|cmtTeamRepliesDown)/.test(x))) assert.ok(k in DICT.en, k);
  assert.equal(t("cmtNewTitle"), "Нове");
});

/* ── Гілка ── */
test("згорнута гілка: «N відповідей» з aria-expanded=false і «· автор, ДД.ММ ГГ:ХХ» останньої; без списку й поля", () => {
  const html = view([C({ id: "a", n: 1, replies: REPLIES })], th());
  assert.match(html, /<button type="button" class="cmt-rsum" data-act="cmtthread" data-val="a" aria-expanded="false">/);
  assert.match(html, /<span>2 відповіді<\/span>/);
  assert.match(html, /<span class="cmt-rlast">· AI, 19\.11 12:31<\/span>/);
  assert.equal(html.includes("cmt-replies"), false);
  assert.equal(html.includes("cmt-rbox"), false);
});

test("розгорнута гілка: список за ts, автор агента — «AI» з cmt-ragent, «змінено», поле, дії над відповідями", () => {
  const html = view([C({ id: "a", n: 1, replies: [REPLIES[1], REPLIES[0]] })], th(["a"]));
  assert.match(html, /aria-expanded="true"/);
  assert.equal(html.includes("cmt-rlast"), false);
  assert.ok(html.indexOf("cmt-rwho\">Автор Б") < html.indexOf("cmt-rwho cmt-ragent\">AI"), "порядок за ts, не за сховищем");
  assert.match(html, /<span class="cmt-rwho cmt-ragent">AI<\/span>/);
  assert.match(html, /<span class="cmt-redited">змінено<\/span>/);
  assert.match(html, /<ol class="cmt-replies"><li class="cmt-reply">/);
  assert.match(html, /<textarea class="cmt-rta" data-val="a" placeholder="Відповісти…"/);
  assert.match(html, /data-act="cmtreplycancel" data-val="a"/);
  assert.match(html, /class="cmt-act cmt-act--pri" data-act="cmtreplysend" data-val="a"/);
  assert.match(html, /data-act="cmtredit" data-val="a\|r1"/);
  assert.equal(html.includes('data-act="cmtredit" data-val="a|r2"'), false, "змінити можна лише свою");
  assert.match(html, /data-act="cmtrdel" data-val="a\|r1"/);
  assert.match(html, /data-act="cmtrdel" data-val="a\|r2"/);
});

test("відповідь агента показує «AI», а не збережене імʼя; у згортці теж", () => {
  const rs = [{ id: "r1", author: "claude-bot", agent: true, text: "т", ts: "19.11.2026 12:05" }];
  const open = view([C({ id: "a", n: 1, replies: rs })], th(["a"]));
  assert.match(open, /<span class="cmt-rwho cmt-ragent">AI<\/span>/);
  assert.equal(open.includes("claude-bot"), false);
  assert.match(view([C({ id: "a", n: 1, replies: rs })], th()), /· AI, 19\.11 12:05/);
});

test("без відповідей: «Відповісти» (cmtreply); коли відповідаємо — лише поле з --on", () => {
  const c = C({ id: "a", n: 1 });
  assert.match(view([c], th()), /class="cmt-rsum" data-act="cmtreply" data-val="a"><svg[^>]*>.*<\/svg><span>Відповісти<\/span>/);
  const on = view([c], th([], { replying: "a" }));
  assert.equal(on.includes("cmt-rsum"), false);
  assert.match(on, /class="cmt-rbox cmt-rbox--on"/);
  assert.equal(view([c], { threads: new Set() }).includes("cmt-thread"), false, "без repliesOff кнопки нема");
});

test("поле й кнопка відповіді — лише на ВІДКРИТОМУ коментарі; закритий розгортається читанням", () => {
  const closed = C({ id: "z", n: 1, status: "resolved", replies: REPLIES, meta: { resolvedAt: 1 } });
  const html = view([closed], th(["z"], { replying: "z" }));
  assert.match(html, /<ol class="cmt-replies">/);
  for (const bad of ["cmt-rbox", "cmt-rta", "cmtreplysend", "cmtredit", "cmtrdel", "cmtreply\""]) assert.equal(html.includes(bad), false, bad);
  const none = view([C({ id: "y", n: 2, status: "resolved", meta: { resolvedAt: 1 } })], th(["y"], { replying: "y" }));
  assert.equal(none.includes("cmt-thread"), false, "закритий без відповідей — без гілки і без «Відповісти»");
  assert.match(view([closed], th()), /aria-expanded="false"/);
});

test("repliesOff: рядок причини → нотатка замість поля (коли розгорнуто або відповідей нема); null → поле", () => {
  const off = th([], { repliesOff: () => "why" });
  const a = view([C({ id: "a", n: 1 })], off);
  assert.match(a, /<p class="cmt-rnote">Відповіді команди недоступні — причина вгорі панелі\.<\/p>/);
  assert.equal(a.includes("cmtreply"), false);
  const b = view([C({ id: "b", n: 1, replies: REPLIES })], off);
  assert.equal(b.includes("cmt-rnote"), false, "згорнуто з відповідями — без нотатки");
  const c = view([C({ id: "b", n: 1, replies: REPLIES })], { ...off, threads: new Set(["b"]) });
  assert.match(c, /cmt-rnote/);
  assert.equal(c.includes("cmt-rbox"), false, "поля відповіді нема, поки відповіді недоступні");
});

test("свіжі відповіді: клас, чип «нова», «+K нова» у згортці", () => {
  const fresh = new Set(["r2"]);
  const folded = view([C({ id: "a", n: 1, replies: REPLIES })], th([], { fresh }));
  assert.match(folded, /<span class="cmt-rnew">\+1 нова<\/span>/);
  const open = view([C({ id: "a", n: 1, replies: REPLIES })], th(["a"], { fresh }));
  assert.match(open, /<li class="cmt-reply cmt-reply--new">.*?<span class="cmt-rnew">нова<\/span>/);
  assert.equal((open.match(/cmt-reply--new/g) || []).length, 1);
});

test("екранування тексту й автора відповіді, id у атрибутах", () => {
  const evil = [{ id: 'r"><i>', author: "<img src=x>", text: "<img src=x onerror=alert(1)>", ts: "<b>t</b>" }];
  const html = view([C({ id: 'a"><u>', n: 1, replies: evil })], th(['a"><u>'], { isOwnReply: () => true }));
  for (const bad of ["<img src=x", "<b>t</b>", "<i>", "<u>"]) assert.equal(html.includes(bad), false, bad);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  const ed = view([C({ id: "a", n: 1, replies: [{ id: "r", author: "x", text: "</textarea><b>", ts: "19.11.2026 12:05" }] })], th(["a"], { replyEdit: "a|r" }));
  assert.equal(ed.includes("</textarea><b>"), false);
});

test("правка відповіді: textarea.cmt-redit з текстом + Зберегти/Скасувати; без правки — нема", () => {
  const html = view([C({ id: "a", n: 1, replies: REPLIES })], th(["a"], { replyEdit: "a|r1" }));
  assert.match(html, /<textarea class="cmt-redit" data-val="a\|r1"[^>]*>Так &lt;b&gt;one&lt;\/b&gt;<\/textarea>/);
  assert.match(html, /data-act="cmtreditsave" data-val="a\|r1"/);
  assert.match(html, /data-act="cmtreditcancel" data-val="a\|r1"/);
  assert.equal(html.includes('data-act="cmtredit" data-val="a|r1"'), false, "під час правки кнопок дій немає");
  assert.equal(view([C({ id: "a", n: 1, replies: REPLIES })], th(["a"])).includes('class="cmt-redit"'), false);
});

test("видалення відповіді: підтвердження на місці з cmtrdelyes/cmtrdelno", () => {
  const html = view([C({ id: "a", n: 1, replies: REPLIES })], th(["a"], { replyDelAsk: "a|r2" }));
  assert.match(html, /Видалити відповідь\?/);
  assert.match(html, /data-act="cmtrdelyes" data-val="a\|r2"/);
  assert.match(html, /data-act="cmtrdelno"/);
  assert.equal((html.match(/cmtrdelyes/g) || []).length, 1);
});

test("видалення коментаря з відповідями питає про кількість; без відповідей і без гілки — як було", () => {
  const c = C({ id: "a", n: 1, replies: REPLIES });
  assert.match(view([c], th([], { delAsk: "a" })), /Видалити назавжди разом із 2 відповідями\?/);
  assert.match(view([C({ id: "a", n: 1 })], th([], { delAsk: "a" })), /Видалити назавжди\?/);
  assert.match(view([c], { delAsk: "a" }), /Видалити назавжди\?/);
});

test("фільтр «Для AI»/«Команда»: «+K» свіжих на обох вкладках; на «Усі» — ні", () => {
  const html = view([C({ id: "l", n: 1, replies: REPLIES }), C({ id: "p", n: 2, _aud: "project" })],
    { dual: true, fresh: new Set(["r2", "p"]) });
  assert.match(html, /data-val="local" aria-pressed="false"><span>Для AI<\/span><span class="cmt-fn">1<\/span><span class="cmt-fnew"[^>]*>\+1<\/span>/);
  assert.match(html, /data-val="project"[^>]*><span>Команда<\/span><span class="cmt-fn">1<\/span><span class="cmt-fnew"[^>]*>\+1<\/span>/);
  assert.doesNotMatch(html, /data-val="all"[^>]*>(?:(?!<\/button>).)*cmt-fnew/);
  assert.match(html, /<h3 class="cmt-h cmt-h--new">Нове <span>2<\/span>/);
});

/* ── «Без знімка» ── */
const CODES = ["too-big", "no-lib", "timeout", "render", "detached", "upload"];
test("shotMiss: усі 6 кодів → рядок із камерою і текстом коду; не залежить від threads", () => {
  for (const code of CODES) {
    for (const over of [{}, th()]) {
      const html = view([C({ id: "a", n: 1, meta: { shotMiss: code } })], over);
      assert.match(html, /<p class="cmt-shotmiss"><svg[^>]*><use href="#i-camera"/, code);
      assert.ok(html.includes(t(`cmtShotMiss_${code}`)), code);
      assert.match(t(`cmtShotMiss_${code}`), /^Без знімка: .+\.$/, code);
    }
  }
});

test("shotMiss: нема, коли є зображення (shot або shotUrl) чи код невідомий/не рядок; стоїть перед рядком дій", () => {
  for (const meta of [{ shotMiss: "timeout", shot: "data:image/png;base64,AAAA" }, { shotMiss: "timeout", shotUrl: "https://x.test/a.png" },
    { shotMiss: "zzz" }, { shotMiss: { code: "timeout" } }, { shotMiss: null }, {}])
    assert.equal(view([C({ id: "a", n: 1, meta })]).includes("cmt-shotmiss"), false, JSON.stringify(meta));
  const html = view([C({ id: "a", n: 1, meta: { shotMiss: "render" } })]);
  assert.ok(html.indexOf("cmt-shotmiss") < html.indexOf('class="cmt-acts"'));
});
