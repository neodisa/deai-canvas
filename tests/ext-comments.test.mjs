/**
 * Чисті шматки панелі коментарів превʼю (`app/ext-comments.js`): імʼя автора й «чи можна чіпати». DOM-проводку
 * (відкриття панелі, додавання, `cmtshot`) стереже `tests/live/preview-comments.test.mjs`.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { CMT_ACTS, CMT_EVENTS, PREVIEW_ACTIONS, REPLY_ACTS, USER_KEY, canTouch, canTouchReply, cleanName, createExtComments, ownStore, parentOfReply,
  readNameFrom, storeRepliesOn } from "../app/ext-comments.js";
import { commentsPanelHTML } from "../app/comments-view.js";
import { setLang, t } from "../app/i18n.js";

const mem = (obj) => () => ({ getItem: (k) => (k in obj ? obj[k] : null) });
const throwing = () => { throw new Error("blocked"); };

test("імʼя: «Anonymous» зі старої рамки — не імʼя; порожнє — теж; решта обрізається", () => {
  assert.equal(cleanName("Anonymous"), "");
  assert.equal(cleanName("  Anonymous "), "");
  assert.equal(cleanName(null), "");
  assert.equal(cleanName("  Олена "), "Олена");
  assert.equal(cleanName("Anonymous Smith"), "Anonymous Smith");
  assert.equal(readNameFrom(mem({ [USER_KEY]: "Anonymous" }), () => ""), "", "старе «Anonymous» прийняли за імʼя");
});

test("імʼя: сховище недоступне — імʼя з памʼяті оболонки; сховище має перевагу", () => {
  assert.equal(readNameFrom(throwing, () => "Марко"), "Марко");
  assert.equal(readNameFrom(mem({ [USER_KEY]: "Олена" }), () => "Марко"), "Олена");
  assert.equal(readNameFrom(mem({ [USER_KEY]: "Anonymous" }), () => "Марко"), "Марко");
  assert.equal(readNameFrom(throwing, () => undefined), "");
});

test("canTouch: лише СВІЙ і ВІДКРИТИЙ у знімку; закритий, чужий, відсутній — ні", () => {
  const store = (ids) => ({ has: (id) => ids.includes(id) });
  const snap = { comments: [{ id: "a", status: "open" }, { id: "b", status: "resolved" }, { id: "c", status: "open" }] };
  const own = store(["a", "b", "ghost"]);
  assert.equal(canTouch(own, snap, "a"), true);
  assert.equal(canTouch(own, snap, "b"), false, "закритий свій");
  assert.equal(canTouch(own, snap, "c"), false, "чужий");
  assert.equal(canTouch(own, snap, "ghost"), false, "свій, якого нема в знімку");
  assert.equal(canTouch(own, null, "a"), false);
});

test("cmtshot: дія в реєстрі оболонки й дозволена всім; картка зі знімком малює кнопку", () => {
  setLang("uk");
  assert.ok(CMT_ACTS.includes("cmtshot"));
  assert.ok(PREVIEW_ACTIONS.any.includes("cmtshot"));
  const c = { id: "x", n: 1, text: "т", author: "А", ts: "1", status: "open", scope: "current", where: "here", iter: "1",
    meta: { shotUrl: "https://example.test/s.png" } };
  const html = commentsPanelHTML({ snapshot: { iteration: "1", comments: [c] }, query: "", selectedId: null, editingId: null,
    delAsk: null, expanded: {}, filter: "all", dual: false, isOwn: () => false, actions: PREVIEW_ACTIONS, adding: false });
  assert.match(html, /data-act="cmtshot" data-val="x"/);
});

test("порожня панель превʼю: підказка за `emptyKey`; без нього — як у Deai", () => {
  setLang("uk");
  const base = { snapshot: { iteration: "1", comments: [] }, query: "", selectedId: null, editingId: null, delAsk: null,
    expanded: {}, filter: "all", dual: false };
  assert.match(commentsPanelHTML({ ...base, emptyKey: "cmtEmptyPlus" }), /Натисніть «\+», щоб залишити коментар\./);
  assert.match(commentsPanelHTML(base), /Натисніть на макет, щоб залишити\./);
  setLang("en");
  assert.equal(t("cmtEmptyPlus"), "Press “+” to leave a comment.");
  setLang("uk");
});

test("ownStore лишається працездатним без сховища", () => {
  const s = ownStore(throwing, "k");
  s.add("a");
  assert.equal(s.has("a"), true);
});

/* ── Відповіді (0.34): права в превʼю ─────────────────────────────────────────────────────────────────────────────────── */

test("CMT_EVENTS: `reply` — посилка рамки (`onReply`); усі 10 дій відповідей — у реєстрі й не серед «чужих» дій", () => {
  assert.ok(CMT_EVENTS.has("reply"));
  assert.ok(CMT_EVENTS.has("add"));
  assert.equal(REPLY_ACTS.length, 10);
  for (const a of REPLY_ACTS) assert.ok(CMT_ACTS.includes(a), a);
  for (const a of ["cmtres", "cmtreopen", "cmtassign", "cmtunassign", "cmtcarry"]) assert.equal(CMT_ACTS.includes(a), false, a);
});

test("storeRepliesOn: булеве сховище модуля, функція комбінованого, без геттерів — ні; `repliesDown` вимикає", () => {
  assert.equal(storeRepliesOn({ supportsReplies: true, repliesDown: null }), true, "булеве true");
  assert.equal(storeRepliesOn({ supportsReplies: false, repliesDown: "no-replies-schema" }), false, "булеве false");
  assert.equal(storeRepliesOn({ supportsReplies: true, repliesDown: "timeout" }), false, "збій");
  assert.equal(storeRepliesOn({ supportsReplies: (ch) => ch === "project" }), true, "функція");
  assert.equal(storeRepliesOn({ supportsReplies: () => false }), false);
  assert.equal(storeRepliesOn({}), false, "старий модуль без геттерів");
  assert.equal(storeRepliesOn({ supportsReplies: "yes" }), false, "не булеве й не функція");
  assert.equal(storeRepliesOn(null), false);
  assert.equal(storeRepliesOn({ get supportsReplies() { throw new Error("boom"); } }), false);
});

const snapR = () => ({ iteration: "1", comments: [
  { id: "o", status: "open", replies: [{ id: "r-mine" }, { id: "r-other" }] },
  { id: "x", status: "resolved", replies: [{ id: "r-closed" }] },
  { id: "e", status: "open" },
] });

test("canTouchReply: лише СВОЯ відповідь під ВІДКРИТИМ коментарем, що її містить, за ввімкнених відповідей", () => {
  const own = { has: (id) => ["r-mine", "r-closed", "ghost"].includes(id) };
  const s = snapR();
  assert.equal(canTouchReply(own, s, "o", "r-mine", true), true);
  assert.equal(canTouchReply(own, s, "o", "r-other", true), false, "чужа");
  assert.equal(canTouchReply(own, s, "x", "r-closed", true), false, "під закритим");
  assert.equal(canTouchReply(own, s, "o", "r-mine", false), false, "відповіді вимкнені");
  assert.equal(canTouchReply(own, s, "e", "r-mine", true), false, "не під своїм коментарем");
  assert.equal(canTouchReply(own, s, "o", "ghost", true), false, "свій id, якого нема");
  assert.equal(canTouchReply(own, null, "o", "r-mine", true), false);
  assert.equal(parentOfReply(s, "r-closed").id, "x");
  assert.equal(parentOfReply(s, "nope"), null);
});

/** Найменший «DOM» для `createExtComments`: лише те, до чого доходить `paint` і делегація; без браузера. */
function harness({ store, name = "Гість", snap, replies = true } = {}) {
  const handlers = {};
  const calls = { reply: [], editReply: [], removeReply: [] };
  const mount = { innerHTML: "", hidden: true, setAttribute() {}, contains: () => false, querySelector: () => null,
    querySelectorAll: (sel) => (sel === ".cmt-rta" ? mount.rtas : sel === ".cmt-rbox--on" ? mount.onBoxes : []), rtas: [], onBoxes: [],
    addEventListener: (k, f) => { handlers[k] = f; } };
  const g = globalThis;
  const saved = { document: g.document, window: g.window, location: g.location, CSS: g.CSS };
  g.document = { activeElement: null, body: { classList: { toggle() {} } }, addEventListener() {}, querySelector: () => null };
  g.window = { addEventListener() {}, __dcPreviewUser: "" };
  g.location = { origin: "http://x.test", pathname: "/p" };
  g.CSS = { escape: (v) => String(v) };
  const layer = {
    snapshot: () => snap, setCommentMode() {}, focus() {}, store: store ?? { supportsReplies: replies, repliesDown: null },
    reply: (id, text) => { calls.reply.push([id, text]); return "new-r"; },
    editReply: (...a) => { calls.editReply.push(a); return true; }, removeReply: (...a) => { calls.removeReply.push(a); return true; },
  };
  const frame = { contentWindow: { CommentLayer: layer, addEventListener() {} }, contentDocument: {} };
  const ctl = createExtComments({ frame, mount, channel: "c", storage: () => ({ getItem: (k) => (k === USER_KEY ? name : null), setItem() {} }) });
  const post = (m) => ctl.onMessage({ source: frame.contentWindow, origin: "http://x.test", data: { type: "dc-comments", ...m } });
  const done = () => Object.assign(g, saved);
  return { ctl, calls, mount, layer, post, done, handlers };
}
const rc = (id, status, replies, n = 1) => ({ id, n, text: "т", author: "А", ts: "20.11.2026 10:00", status, scope: "current", where: "here", iter: "1", meta: {}, replies });
const rp = (id, author = "Б") => ({ id, author, text: `текст ${id}`, ts: "20.11.2026 11:00" });
const actsIn = (html, id) => [...(new RegExp(`<li class="cmt-reply[^>]*>(?:(?!</li>)[\\s\\S])*?${id}[\\s\\S]*?</li>`).exec(html)?.[0] ?? "").matchAll(/data-act="(cmt[a-z]+)"/g)].map((m) => m[1]);

/** Панель відкрито, рамка «ready», відповіді розгорнуті — повертає `html` після перемальовування. */
function boot2(opts) {
  const h = harness(opts);
  h.post({ ev: "ready" });
  h.ctl.setOpen(true);
  h.ctl.actions.cmtthread("o");
  return h;
}

test("paint: права відповіді — своя (і лише своя) з «змінити»/«видалити», чужа лише читається; «reply» робить відповідь своєю ДО першого change", () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r-mine"), rp("r-other")])] };
  const h = boot2({ snap });
  try {
    assert.deepEqual(actsIn(h.mount.innerHTML, "r-mine"), [], "до події `reply` відповідь ще не своя");
    h.post({ ev: "reply", id: "r-mine" });
    assert.deepEqual(actsIn(h.mount.innerHTML, "r-mine"), ["cmtredit", "cmtrdel"]);
    assert.deepEqual(actsIn(h.mount.innerHTML, "r-other"), []);
    assert.match(h.mount.innerHTML, /data-act="cmtreply"|class="cmt-rbox/);       // поле відповіді є
  } finally { h.done(); }
});

test("охоронець своєї відповіді: чужу змінити/видалити напряму — ніщо; свою — так; під закритим — ні", () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r-mine"), rp("r-other")]), rc("x", "resolved", [rp("r-closed")], 2)] };
  const h = boot2({ snap });
  try {
    h.post({ ev: "reply", id: "r-mine" });
    h.post({ ev: "reply", id: "r-closed" });
    const a = h.ctl.actions;
    a.cmtredit("o|r-other"); a.cmtreditsave("o|r-other");
    a.cmtrdel("o|r-other"); a.cmtrdelyes("o|r-other");
    a.cmtredit("x|r-closed"); a.cmtrdel("x|r-closed"); a.cmtrdelyes("x|r-closed");
    a.cmtredit("o|r-mine-x"); a.cmtredit("x|r-mine");      // не та пара коментар|відповідь
    assert.deepEqual([h.calls.editReply, h.calls.removeReply], [[], []], "чужа/закрита/підроблена пара дійшла до коментатора");
    assert.equal(h.mount.innerHTML.includes("cmt-redit"), false, "чужа перейшла в редагування");
    assert.equal(h.mount.innerHTML.includes("cfm"), false, "для чужої показано питання «Видалити»");
    // своя
    a.cmtredit("o|r-mine");
    assert.match(h.mount.innerHTML, /<textarea class="cmt-redit"/);
    a.cmtreditsave();
    assert.equal(h.calls.editReply.length, 1);
    assert.deepEqual(h.calls.editReply[0].slice(0, 2), ["o", "r-mine"]);
    a.cmtrdelyes("o|r-mine");                               // без питання — нічого
    assert.equal(h.calls.removeReply.length, 0);
    a.cmtrdel("o|r-mine");
    a.cmtrdelyes("o|r-mine");
    assert.deepEqual(h.calls.removeReply, [["o", "r-mine"]]);
  } finally { h.done(); }
});

test("відповідь на ЗАКРИТИЙ коментар неможлива: ні поля, ні дії; на відкритий — так (імʼя відоме)", async () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", []), rc("x", "resolved", [rp("r-old")], 2)] };
  const h = harness({ snap });
  try {
    h.post({ ev: "ready" });
    h.ctl.setOpen(true);
    h.ctl.actions.cmtthread("x");
    h.ctl.actions.cmtreply("x");
    await h.ctl.actions.cmtreplysend("x");
    assert.deepEqual(h.calls.reply, [], "відповідь на закритий дійшла до коментатора");
    assert.equal(/data-act="cmtreply(send)?" data-val="x"/.test(h.mount.innerHTML), false);
    assert.equal(/<textarea class="cmt-rta" data-val="x"/.test(h.mount.innerHTML), false);
    // відкритий: поле з'являється, текст беремо з чернетки (поле в тестовому DOM не живе)
    h.ctl.actions.cmtreply("o");
    assert.match(h.mount.innerHTML, /<textarea class="cmt-rta" data-val="o"/);
    await h.ctl.actions.cmtreplysend("o");              // порожньо — нічого
    assert.deepEqual(h.calls.reply, []);
    h.handlers.input({ target: { classList: { contains: (k) => k === "cmt-rta" }, dataset: { val: "o" }, value: "  Привіт  " } });
    await h.ctl.actions.cmtreplysend("o");
    assert.deepEqual(h.calls.reply, [["o", "Привіт"]], "текст відповіді (з чернетки) не дійшов до коментатора");
  } finally { h.done(); }
});

test("відповіді вимкнені (булеве false, `repliesDown`, функція false, без геттерів): ні поля, ні примітки, ні кнопок змінити/видалити; наявні — читаються", () => {
  setLang("uk");
  const shapes = {
    "булеве": { supportsReplies: false, repliesDown: "no-replies-schema" },
    "збій": { supportsReplies: true, repliesDown: "boom" },
    "функція": { supportsReplies: () => false },
    "без геттерів": {},
  };
  for (const [name, store] of Object.entries(shapes)) {
    const snap = { iteration: "1", comments: [rc("o", "open", [rp("r-mine")]), rc("e", "open", [], 2)] };
    const h = boot2({ snap, store });
    try {
      h.post({ ev: "reply", id: "r-mine" });
      h.ctl.actions.cmtthread("e");
      const html = h.mount.innerHTML;
      assert.match(html, /текст r-mine/, `${name}: наявна відповідь має читатись`);
      for (const bad of ["cmt-rta", "cmt-rbox", 'data-act="cmtreply"', 'data-act="cmtreplysend"', 'data-act="cmtredit"', 'data-act="cmtrdel"',
        "cmt-rnote", "cmt-teamdown"]) assert.equal(html.includes(bad), false, `${name}: «${bad}» у превʼю без відповідей`);
      assert.equal(html.includes("Відповіді команди недоступні"), false, `${name}: примітка`);
      h.ctl.actions.cmtredit("o|r-mine"); h.ctl.actions.cmtrdel("o|r-mine"); h.ctl.actions.cmtreply("o");
      assert.equal(/cmt-redit|class="cfm|cmt-rta/.test(h.mount.innerHTML), false, `${name}: дії обійшли розмітку`);
    } finally { h.done(); }
  }
});

test("відповіді ввімкнені, але відповідей ще нема: кнопка «Відповісти» є (контроль до «вимкнено»)", () => {
  setLang("uk");
  const h = boot2({ snap: { iteration: "1", comments: [rc("e", "open", [], 1)] } });
  try { assert.match(h.mount.innerHTML, /data-act="cmtreply" data-val="e"/); } finally { h.done(); }
});

const fakeTa = (cid, box = { classList: { added: [], add(c) { this.added.push(c); } } }) =>
  ({ classList: { contains: (k) => k === "cmt-rta" }, dataset: { val: cid }, value: "", box, closest: (sel) => (sel === ".cmt-rbox" ? box : sel === ".cmt-rta" ? null : null) });
const focusTarget = (ta) => ({ target: { closest: (sel) => (sel === ".cmt-rta" ? ta : null) } });

test("focusin на полі відповіді: рядок «Надіслати» вмикається БЕЗ перемальовки (клас на боксі + `replying`); закритий коментар чи вимкнені відповіді — нічого", () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r1")]), rc("x", "resolved", [rp("r2")], 2)] };
  const h = boot2({ snap });
  try {
    const before = h.mount.innerHTML;
    const ta = fakeTa("o");
    h.handlers.focusin(focusTarget(ta));
    assert.deepEqual(ta.box.classList.added, ["cmt-rbox--on"], "клас не поставлено");
    assert.equal(h.mount.innerHTML, before, "focusin перемалював панель (згубить каретку)");
    h.handlers.focusin(focusTarget(ta));
    assert.equal(ta.box.classList.added.length, 1, "повторний фокус знову ставить клас");
    h.post({ ev: "change", snapshot: snap });                 // наступна звичайна перемальовка дає той самий стан із `replying`
    assert.match(h.mount.innerHTML, /cmt-rbox cmt-rbox--on/);
    const closed = fakeTa("x");
    h.handlers.focusin(focusTarget(closed));
    assert.deepEqual(closed.box.classList.added, [], "закритий коментар");
    h.handlers.focusin({ target: { closest: () => null } });   // не наше поле — тихо
  } finally { h.done(); }
  const off = boot2({ snap, store: {} });
  try {
    const ta = fakeTa("o");
    off.handlers.focusin(focusTarget(ta));
    assert.deepEqual(ta.box.classList.added, [], "вимкнені відповіді");
  } finally { off.done(); }
});

test("утримане ⌘↵ (`ev.repeat`) відповідь не шле; звичайне — шле один раз", async () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r1")])] };
  const h = boot2({ snap });
  try {
    h.handlers.input({ target: { classList: { contains: (k) => k === "cmt-rta" }, dataset: { val: "o" }, value: "Привіт" } });
    const key = (repeat) => h.handlers.keydown({ key: "Enter", ctrlKey: true, repeat, preventDefault() {}, stopPropagation() {},
      target: { closest: (sel) => (/cmt-rta/.test(sel) ? fakeTa("o") : null) } });
    key(true);
    await new Promise((r) => setTimeout(r, 20));
    assert.deepEqual(h.calls.reply, [], "повтор клавіші надіслав відповідь");
    key(false);
    await new Promise((r) => setTimeout(r, 20));
    assert.deepEqual(h.calls.reply, [["o", "Привіт"]]);
  } finally { h.done(); }
});

test("чернетка відповіді переживає перехід рамки (`dropFrame`) і повертається в поле після `ready`", () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r1")])] };
  const h = boot2({ snap });
  try {
    const ta = fakeTa("o");
    h.mount.rtas = [ta];
    h.handlers.input({ target: { classList: { contains: (k) => k === "cmt-rta" }, dataset: { val: "o" }, value: "Недописана" } });
    h.ctl.dropFrame();
    ta.value = "";
    h.post({ ev: "ready" });
    assert.equal(ta.value, "Недописана", "чернетку скинуто разом із рамкою");
  } finally { h.done(); }
});

test("focusin: другий бокс забирає рядок «Надіслати» в першого (розгорнутий лише один)", () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r1")]), rc("e", "open", [rp("r2")], 2)] };
  const h = boot2({ snap });
  try {
    const mk = () => ({ cls: new Set(), classList: null });
    const b1 = mk(), b2 = mk();
    for (const b of [b1, b2]) b.classList = { add: (c) => b.cls.add(c), remove: (c) => b.cls.delete(c) };
    h.mount.onBoxes = [b1, b2];
    h.handlers.focusin(focusTarget(fakeTa("o", b1)));
    h.handlers.focusin(focusTarget(fakeTa("e", b2)));
    assert.deepEqual([b1.cls.has("cmt-rbox--on"), b2.cls.has("cmt-rbox--on")], [false, true]);
  } finally { h.done(); }
});

test("Esc у полі відповіді згортає рядок і він лишається згорнутим: фокус, повернутий перемальовкою, `focusin` не вмикає знову", () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r1")])] };
  const h = boot2({ snap });
  try {
    const box = { classList: { added: [], add(c) { this.added.push(c); }, remove() {} } };
    const ta = fakeTa("o", box);
    // перемальовка повертає фокус: `focus()` синхронно кидає focusin (як у браузері) — поки `paint` відновлює фокус
    h.mount.querySelector = (sel) => (/cmt-rta\[/.test(sel) ? Object.assign(ta, { focus: () => h.handlers.focusin(focusTarget(ta)), setSelectionRange() {} }) : null);
    globalThis.document.activeElement = Object.assign(ta, { id: "", selectionStart: 0, selectionEnd: 0 });
    h.mount.contains = () => true;
    h.handlers.keydown({ key: "Escape", preventDefault() {}, stopPropagation() {}, target: { closest: (sel) => (/cmt-rta/.test(sel) ? ta : null) } });
    assert.deepEqual(box.classList.added, [], "Esc → перемальовка → повернутий фокус знову розгорнув поле");
    assert.doesNotMatch(h.mount.innerHTML, /cmt-rbox--on/);
  } finally { h.done(); }
});

test("набір у полі відповіді розгортає рядок, коли він згорнутий (після Esc фокус лишається, а `focusin` не повториться); закритий — ні", () => {
  setLang("uk");
  const snap = { iteration: "1", comments: [rc("o", "open", [rp("r1")]), rc("x", "resolved", [rp("r2")], 2)] };
  const h = boot2({ snap });
  try {
    const ta = fakeTa("o");
    h.handlers.input({ target: ta });
    assert.deepEqual(ta.box.classList.added, ["cmt-rbox--on"], "набір не розгорнув рядок");
    const closed = fakeTa("x");
    h.handlers.input({ target: closed });
    assert.deepEqual(closed.box.classList.added, []);
  } finally { h.done(); }
});
