/**
 * Свої модулі простору на екрані «Підключення» (Deai 0.7.0, етап 3c; спека
 * `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`, «Екран «Підключення»»): `cardView` для кожного стану
 * таблиці, причина, рядок довіри, примітки, нові відмови; розмітка — пігулка «свій», бейдж, дії, «Забрати довіру».
 * Вбудовані модулі — без змін (їх стережуть наявні `connections-model.test.mjs` і `connections-view.test.mjs`).
 */
import assert from "node:assert/strict";
import test from "node:test";
import { DICT } from "../app/i18n.js";
import {
  cardView, isOwn, noteView, ownRuns, providerLine, refusalView, roleHolders, trustLine, trustWhyKey, whyOf,
} from "../app/connections-model.js";
import { connMenuHTML, connPageHTML, drawerHTML, mcardHTML, ownTagHTML, trustLineHTML } from "../app/connections-view.js";
import { publishErr } from "../app/spaces-model.js";

const own = (over = {}) => ({
  id: "acme", name: "Acme", version: "1.0.0", api: 1, roles: ["publish"], builtin: false, custom: true,
  enabled: false, implicit: false, status: "untrusted", trust: "untrusted", record: false, runs: false,
  source: "~/work/alpha/modules/acme", error: "module is not trusted on this computer", settings: [], ...over,
});
const builtin = (over = {}) => ({
  id: "static-publish", name: "Static", version: "1", api: 1, roles: ["publish"], builtin: true,
  enabled: true, implicit: false, status: "ok", settings: [], ...over,
});
const pick = (v) => ({ badge: v.badge, actions: v.actions, why: v.why });

test("isOwn / ownRuns: лише `custom: true`; `runs` — лише у свого", () => {
  assert.equal(isOwn(own()), true);
  assert.equal(isOwn(builtin()), false);
  assert.equal(isOwn(builtin({ custom: "true" })), false, "лише справжнє true");
  assert.equal(ownRuns(own({ runs: true })), true);
  assert.equal(ownRuns(builtin({ runs: true })), false, "вбудований не «свій», навіть з полем runs");
  assert.equal(ownRuns(own({ runs: undefined })), false, "нема поля runs — код не виконується (безпечне типове)");
  assert.equal(ownRuns(own({ runs: "true" })), false, "лише справжнє true");
});

test("cardView: кожен стан таблиці спеки", () => {
  assert.deepEqual(pick(cardView(own())), { badge: "untrusted", actions: ["trust"], why: false });
  assert.deepEqual(pick(cardView(own({ enabled: true }))), { badge: "untrusted", actions: ["trust", "disable"], why: true });
  const refused = { trust: "refused", status: "error", trust_error: "symlink", error: "symlink: alias.py: symbolic link" };
  assert.deepEqual(pick(cardView(own(refused))), { badge: "error", actions: ["trustinfo"], why: true });
  assert.deepEqual(pick(cardView(own({ ...refused, enabled: true }))), { badge: "error", actions: ["trustinfo", "disable"], why: true });
  /* Знімок працює: як у вбудованого + дія довіри. */
  assert.deepEqual(pick(cardView(own({ trust: "refused", runs: true, status: "ok", enabled: true, trust_error: "too-big" }))),
    { badge: "ok", actions: ["configure", "check", "disable", "trustinfo"], why: false });
  assert.deepEqual(pick(cardView(own({ trust: "changed", runs: true, status: "unchecked" }))),
    { badge: "off", actions: ["enable", "trust"], why: false });
  assert.deepEqual(pick(cardView(own({ trust: "changed", runs: true, status: "error", enabled: true, error: "check failed" }))),
    { badge: "error", actions: ["configure", "check", "disable", "trust"], why: true });
  assert.deepEqual(pick(cardView(own({ trust: "trusted", runs: true, status: "ok", enabled: true }))),
    { badge: "ok", actions: ["configure", "check", "disable"], why: false });
});

test("cardView вбудованого — рівно як до 3c (жодних дій довіри)", () => {
  assert.deepEqual(pick(cardView(builtin())), { badge: "ok", actions: ["configure", "check", "disable"], why: false });
  assert.deepEqual(pick(cardView(builtin({ enabled: false }))), { badge: "off", actions: ["enable"], why: false });
  assert.deepEqual(pick(cardView(builtin({ trust: "changed" }))), { badge: "ok", actions: ["configure", "check", "disable"], why: false },
    "поле trust без custom — не свій модуль");
});

test("whyOf: недовірений увімкнений — потрібна довіра; недовірений вимкнений — нічого; refused без знімка — причина + деталь", () => {
  assert.deepEqual(whyOf(own({ enabled: true })), { key: "cnTrustNeededWhy", detail: "" });
  assert.equal(whyOf(own()), null);
  assert.deepEqual(whyOf(own({ trust: "refused", status: "error", trust_error: "hardlink", error: "hardlink: a.py" })),
    { key: "trWhyHardlink", detail: "hardlink: a.py" });
  assert.equal(whyOf(own({ trust: "refused", status: "error", error: "x".repeat(400) })).detail.length, 300, "деталь обрізано");
});

test("trustWhyKey: кожна причина спеки має свій ключ, невідома — trWhyOther", () => {
  const codes = ["symlink", "hardlink", "special-file", "too-many-files", "too-big", "too-deep", "bad-name", "unreadable",
    "unstable", "bad-manifest", "snapshot-damaged", "trust-unreadable"];
  const keys = codes.map(trustWhyKey);
  assert.equal(new Set(keys).size, codes.length, "ключі не повторюються");
  assert.ok(!keys.includes("trWhyOther"));
  assert.equal(trustWhyKey("nope"), "trWhyOther");
  assert.equal(trustWhyKey("__proto__"), "trWhyOther", "Map, а не обʼєкт");
});

test("trustLine: changed / refused зі знімком / пошкоджений знімок / нечитабельний файл довіри; інакше null", () => {
  assert.deepEqual(trustLine(own({ trust: "changed", runs: true })), { key: "cnTrustChanged", why: null });
  assert.deepEqual(trustLine(own({ trust: "refused", runs: true, trust_error: "too-deep" })), { key: "cnTrustRefusedNew", why: "trWhyTooDeep" });
  assert.equal(trustLine(own({ trust: "refused", runs: false, status: "error" })), null, "без знімка — причина в whyOf, не тут");
  assert.deepEqual(trustLine(own({ trust_error: "snapshot-damaged", record: true })), { key: "cnTrustDamaged", why: null });
  assert.deepEqual(trustLine(own({ trust_error: "trust-unreadable" })), { key: "cnRefTrustUnreadable", why: null });
  assert.equal(trustLine(own({ trust: "trusted", runs: true })), null);
  assert.equal(trustLine(own()), null);
  assert.equal(trustLine(builtin({ trust: "changed" })), null);
});

test("noteView: коди → ключі з текою; невідомий — cnNoteOther; сміття відкинуто", () => {
  assert.deepEqual(noteView([
    { folder: "modules/pub", code: "id-taken" }, { folder: "modules/m32", code: "too-many-modules" },
    { folder: "modules", code: "modules-link" }, { folder: "modules", code: "modules-unreadable" },
    { folder: "modules/x", code: "what" }, null, { code: "id-taken" }, { folder: 3, code: "id-taken" },
    { folder: "modules/y" }, { folder: "modules/z", code: 5 },
  ]), [
    { key: "cnNoteIdTaken", folder: "modules/pub" }, { key: "cnNoteTooMany", folder: "modules/m32" },
    { key: "cnNoteLink", folder: "modules" }, { key: "cnNoteUnreadable", folder: "modules" },
    { key: "cnNoteOther", folder: "modules/x" },
  ]);
  assert.deepEqual(noteView(undefined), []);
});

test("refusalView: нові коди довіри мають свої тексти", () => {
  const want = {
    "module-untrusted": "cnRefUntrusted", "module-changed": "cnRefChanged", "module-refused": "cnRefRefused",
    "trust-needs-ui": "cnRefNeedsUi", "trust-declined": "cnRefDeclined", "trust-no-confirm": "cnRefNoConfirm",
    "trust-busy": "cnRefBusy", "trust-unreadable": "cnRefTrustUnreadable",
  };
  for (const [code, key] of Object.entries(want)) assert.equal(refusalView({ code }).key, key, code);
});

test("providerLine: роль «на папері» за увімкненим недовіреним — «чекає довіри», а не «нікого»", () => {
  const caps = { publish: null, comments: null, tokens: null };
  const list = [own({ enabled: true })];
  assert.deepEqual(providerLine("publish", caps, list), { kind: "waiting", id: "acme", entry: list[0] });
  assert.equal(providerLine("publish", caps, [own()]).kind, "none", "невключений роль не тримає");
  assert.equal(providerLine("publish", caps, [own({ enabled: true, trust: "trusted", runs: true, status: "ok" })]).kind, "none");
  assert.equal(providerLine("comments", caps, list).kind, "none", "чужа роль");
  assert.equal(providerLine("publish", caps, [builtin({ enabled: true })]).kind, "none", "вбудований без `runs` — не «свій, що чекає довіри»");
  assert.equal(providerLine("publish", { ...caps, error: "space-json-unreadable" }, list).kind, "error", "стан простору — першим");
});

test("roleHolders: увімкнений недовірений свій модуль — власник ролі (сервер так само тримає роль «на папері»)", () => {
  const list = [own({ enabled: true }), builtin({ id: "vercel-publish", enabled: false })];
  assert.deepEqual(roleHolders(list[1], list).map((x) => x.id), ["acme"]);
});

test("mcardHTML: пігулка «свій» з текою в title, бейдж «Чекає довіри» з замком, кнопка «Довірити»", () => {
  const h = mcardHTML(own({ name: '<img src=x onerror="alert(1)">', source: '~/a"b<c' }), new Map());
  assert.match(h, /<span class="mc-tag" title="~\/a&quot;b&lt;c">свій<\/span>/);
  assert.match(h, /bdg bdg--trust"><svg[^>]*>.*?<\/svg>Чекає довіри/s);
  assert.match(h, /data-cn="trust" data-id="acme">/);
  assert.doesNotMatch(h, /<img/, "назва з маніфесту — текст");
  assert.doesNotMatch(mcardHTML(builtin(), new Map()), /mc-tag|data-cn="trust/);
});

test("mcardHTML: рядок довіри в картці; «Чому не можна…» для refused", () => {
  const h = mcardHTML(own({ trust: "changed", runs: true, status: "unchecked" }), new Map());
  assert.match(h, /<p class="mc-why">У теці є зміни/);
  const r = mcardHTML(own({ trust: "refused", status: "error", trust_error: "symlink", error: "symlink: a" }), new Map());
  assert.match(r, /data-cn="trustinfo"/);
  assert.match(r, /class="mc-why">У теці є символьне посилання/);
  /* refused ЗІ знімком: причина вставлена в речення (а не «undefined»), працює попередня; «Чому не можна…» — у меню «⋯». */
  const e = own({ trust: "refused", runs: true, status: "ok", enabled: true, trust_error: "too-big" });
  const k = mcardHTML(e, new Map());
  assert.match(k, /<p class="mc-why">Нову версію теки не можна довірити\. Тека завелика \(понад 5 МіБ\)\. Працює попередня\./);
  assert.doesNotMatch(k, /undefined/);
  assert.doesNotMatch(k, /data-cn="trustinfo"/, "на картці — не друга дія");
  assert.match(connMenuHTML(e), /data-cn="trustinfo" data-id="acme"/);
});

test("ownTagHTML і trustLineHTML екранують навіть текст словника (захист на глибину: текст у розмітку лише через esc)", () => {
  const saved = { custom: DICT.uk.cnCustom, changed: DICT.uk.cnTrustChanged };
  DICT.uk.cnCustom = "<u>свій</u>";
  DICT.uk.cnTrustChanged = "<i>зміни</i>";
  try {
    assert.match(ownTagHTML(own()), /&lt;u&gt;свій&lt;\/u&gt;/);
    assert.match(trustLineHTML(own({ trust: "changed", runs: true })), /&lt;i&gt;зміни&lt;\/i&gt;/);
    assert.doesNotMatch(trustLineHTML(own({ trust: "changed", runs: true })), /<i>/);
  } finally { DICT.uk.cnCustom = saved.custom; DICT.uk.cnTrustChanged = saved.changed; }
  assert.equal(ownTagHTML(builtin()), "");
  assert.equal(trustLineHTML(own()), "");
});

test("mcardHTML: «Довірити» несе замок, «Чому не можна…» — знак питання", () => {
  assert.match(mcardHTML(own(), new Map()), /data-cn="trust" data-id="acme"><svg[^>]*><use href="#i-lock"\/><\/svg>Довірити/);
  const r = mcardHTML(own({ trust: "refused", status: "error", trust_error: "symlink", error: "symlink: a" }), new Map());
  assert.match(r, /data-cn="trustinfo" data-id="acme"><svg[^>]*><use href="#i-help"\/><\/svg>Чому не можна…/);
  assert.match(mcardHTML(own(), new Map([["acme", "trust"]])), /data-cn="trust" data-id="acme" disabled>/, "дія в польоті — кнопка вимкнена");
});

test("connPageHTML: примітки під головою — лише коли є", () => {
  const sp = { id: "alpha", name: "Alpha", path: "~/work/alpha", capabilities: { publish: null, comments: null, tokens: null } };
  const base = { space: sp, list: [own()], failed: null, busy: new Map() };
  assert.doesNotMatch(connPageHTML({ ...base, notes: [] }), /cn-notes/);
  assert.doesNotMatch(connPageHTML(base), /cn-notes/, "без поля notes — як до 3c");
  const h = connPageHTML({ ...base, notes: [{ folder: "modules/<b>", code: "id-taken" }] });
  assert.match(h, /<ul class="cn-notes"><li class="cn-note">/);
  assert.match(h, /modules\/&lt;b&gt;/);
  assert.doesNotMatch(h, /cn-agent|Агент може написати свій модуль/, "блок «Через агента» переїхав в AGENTS.md (етап Е)");
  assert.ok(h.indexOf("cn-notes") < h.indexOf('class="mg"'), "примітки — над сіткою, а не під нею");
});

test("connPageHTML: роль «на папері» (capabilities.publish = null БЕЗ error) і ввімкнений недовірений свій модуль — картка з «Довірити», не помилка сторінки", () => {
  const sp = { id: "alpha", name: "Alpha", path: "~/work/alpha", capabilities: { publish: null } };
  const h = connPageHTML({ space: sp, list: [own({ enabled: true })], notes: [], failed: null, busy: new Map() });
  assert.match(h, /data-cn="trust" data-id="acme"/);
  assert.match(h, /Чекає довіри/);
  assert.doesNotMatch(h, /cn-err/, "поправка 11: без error сторінка не ховає картки");
});

test("drawerHTML: «Забрати довіру» лише у свого модуля з записом довіри", () => {
  const d = (entry) => drawerHTML({ entry, mode: "edit", fields: [], form: { values: {}, erase: [] }, busy: false,
    result: null, errors: {}, spaceName: "S" });
  const trusted = d(own({ record: true, runs: true, trust: "trusted", status: "ok", enabled: true }));
  assert.match(trusted, /data-cn-dr="untrust"/);
  assert.match(trusted, /<button type="button" class="ctl ctl--out cn-dr-untrust"/, "клас руйнівної кнопки — гачок її рамки в CSS");
  assert.ok(trusted.indexOf("cn-dr-untrust") < trusted.indexOf('data-cn-dr="check"'), "«Забрати довіру» — перша у футері");
  assert.doesNotMatch(d(own({ record: false })), /data-cn-dr="untrust"/);
  assert.doesNotMatch(d(builtin({ record: true })), /data-cn-dr="untrust"/);
  /* Запис у польоті — кнопка вимкнена, як і решта; лише хрестик живий. */
  const busy = drawerHTML({ entry: own({ record: true, runs: true, trust: "trusted", status: "ok", enabled: true }), mode: "edit",
    fields: [], form: { values: {}, erase: [] }, busy: "save", result: null, errors: {}, spaceName: "S" });
  assert.match(busy, /data-cn-dr="untrust" disabled>/);
});

test("publishErr: module-untrusted має людський текст без тексту сервера, ключ є в обох мовах", () => {
  assert.deepEqual(publishErr({ code: "module-untrusted", status: 409 }), { key: "publishErrUntrusted", args: [] });
  /* Текст сервера не просочується: відмову про довіру пояснює словник, а не відповідь. */
  assert.deepEqual(publishErr({ code: "module-untrusted", status: 409, message: "secret server text" }),
    { key: "publishErrUntrusted", args: [] });
  for (const lang of ["uk", "en"]) assert.ok(DICT[lang].publishErrUntrusted !== undefined, `${lang}: немає publishErrUntrusted`);
});

test("словник: кожен ключ, який віддає модель для своїх модулів, є в обох мовах", () => {
  const keys = new Set(["cnCustom", "cnBadgeUntrusted", "cnTrust", "cnTrustInfo", "cnUntrust", "cnUntrustAsk", "cnUntrustRole",
    "cnUntrustKeeps", "cnToastTrusted", "cnToastUntrusted", "trWhyOther"]);
  for (const c of ["symlink", "hardlink", "special-file", "too-many-files", "too-big", "too-deep", "bad-name", "unreadable",
    "unstable", "bad-manifest", "snapshot-damaged", "trust-unreadable"]) keys.add(trustWhyKey(c));
  for (const e of [own({ enabled: true }), own({ trust: "changed", runs: true }), own({ trust: "refused", runs: true, trust_error: "x" }),
    own({ trust_error: "snapshot-damaged" }), own({ trust_error: "trust-unreadable" })]) {
    const w = whyOf(e); if (w) keys.add(w.key);
    const l = trustLine(e); if (l) { keys.add(l.key); if (l.why) keys.add(l.why); }
  }
  for (const n of noteView(["id-taken", "too-many-modules", "modules-link", "modules-unreadable", "?"].map((code) => ({ folder: "f", code })))) keys.add(n.key);
  for (const code of ["module-untrusted", "module-changed", "module-refused", "trust-needs-ui", "trust-declined", "trust-no-confirm",
    "trust-busy", "trust-unreadable"]) keys.add(refusalView({ code }).key);
  assert.ok(keys.size >= 40, `зібрано лише ${keys.size}`);
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає ключа «${k}»`);
});
