/**
 * Охоронець «Deai без змін» (0.32.0, Task 3): `commentsPanelHTML` отримав опції для превʼю (`isOwn`, `actions`), і без них
 * його вихід мусить лишитись БАЙТ У БАЙТ таким, яким був до них. Знято ДО правки: хеші sha256 повного рядка розмітки для
 * шести сценаріїв (відкриті/попередні/закриті × dual × питання «Видалити» × редагування). Змінилась розмітка свідомо —
 * перезніми хеші разом із причиною в коміті; змінилась мовчки — тест червоний.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { commentsPanelHTML } from "../app/comments-view.js";
import { setLang } from "../app/i18n.js";

setLang("uk");
const C = (o) => ({ id: o.id, n: o.n, text: o.text || "т", author: o.author || "Автор А", ts: "13.11.2026 10:00",
  status: o.status || "open", scope: o.scope || "current", where: o.where || "here", iter: o.iter || "3",
  resolvedV: o.resolvedV ?? null, resolveReason: o.resolveReason ?? null, meta: o.meta || {}, _aud: o._aud });
const COMMENTS = [
  C({ id: "a", n: 5, text: "відкритий" }),
  C({ id: "b", n: 4, _aud: "project", meta: { assignee: "claude", sel: "цитата" } }),
  C({ id: "c", n: 3, scope: "earlier", iter: "2" }),
  C({ id: "d", n: 2, status: "resolved", resolvedV: 2, resolveReason: "Зробив" }),
  C({ id: "e", n: 1, status: "resolved", resolveReason: "resolved manually" }),
];
const base = (over = {}) => ({ snapshot: { version: "3", iteration: "3", comments: COMMENTS }, query: "", selectedId: null,
  editingId: null, delAsk: null, expanded: { earlier: true, closed: true }, filter: "all", dual: false, teamDown: null, fresh: null, down: null, ...over });
const sha = (s) => createHash("sha256").update(s).digest("hex");

const CASES = {
  "dual:false, усе розгорнуто": base(),
  "dual:true, усе розгорнуто": base({ dual: true }),
  "dual:true, фільтр project": base({ dual: true, filter: "project" }),
  "питання «Видалити» на відкритому": base({ delAsk: "a" }),
  "редагування відкритого": base({ editingId: "a" }),
  "згорнуті розділи": base({ expanded: { earlier: false, closed: false } }),
};

const GOLDEN = {
  "dual:false, усе розгорнуто": "1d1a6f7eb1386d7c2cc40cae575359ec29a1ac281fafddc7e04f1aebc47d131a",
  "dual:true, усе розгорнуто": "54f871f257b7db2922511431121f5002d8c81630f722f4c7de57f2ddd8b44232",
  "dual:true, фільтр project": "14188b21ecd5a9c50c952f42d90d03d2e109f4db2281825c2387295c4f4f7487",
  "питання «Видалити» на відкритому": "87a72f7a77df8056e54759626b37f2a42ddce0fe5e3fb02f45428b41418eed36",
  "редагування відкритого": "8c31efedac5f2b5027d9424300a381ae73583e0caa1754257f0e26f3ab4701b8",
  "згорнуті розділи": "d53d7bf1f0953f5c0b8ede34fcadabe1f9173ef24f6cc6be8ab7eba5e260e4a6",
};

for (const [name, st] of Object.entries(CASES)) {
  test(`типова розмітка не змінилась: ${name}`, () => {
    assert.equal(sha(commentsPanelHTML(st)), GOLDEN[name]);
  });
}
