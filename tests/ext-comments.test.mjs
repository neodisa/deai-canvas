/**
 * Чисті шматки панелі коментарів превʼю (`app/ext-comments.js`): імʼя автора й «чи можна чіпати». DOM-проводку
 * (відкриття панелі, додавання, `cmtshot`) стереже `tests/live/preview-comments.test.mjs`.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { CMT_ACTS, PREVIEW_ACTIONS, USER_KEY, canTouch, cleanName, ownStore, readNameFrom } from "../app/ext-comments.js";
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
