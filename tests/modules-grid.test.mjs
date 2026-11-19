import assert from "node:assert/strict";
import test from "node:test";
import { BADGE_CLASS, cardModel, emptyRoles, gridEntries } from "../app/modules-grid.js";

const bi = (over = {}) => ({ id: "static-publish", name: "Static", roles: ["publish"], builtin: true, enabled: true, implicit: false,
  status: "ok", settings: [{ key: "folder", type: "path" }], ...over });
const own = (over = {}) => ({ id: "acme", name: "Acme", roles: ["publish"], builtin: false, custom: true, enabled: false,
  implicit: false, status: "untrusted", trust: "untrusted", record: false, runs: false, settings: [], ...over });
const acts = (m) => m.menu.map((x) => (x === "sep" ? "-" : x.act));

test("cardModel: ok → без дії, клік — шухляда", () => {
  const m = cardModel(bi());
  assert.deepEqual([m.badge, m.action, m.click], ["ok", null, "configure"]);
  assert.deepEqual(acts(m), ["configure", "check", "-", "disable"]);
});
test("cardModel: unchecked → Перевірити (у меню вже нема дубля)", () => {
  const m = cardModel(bi({ status: "unchecked" }));
  assert.deepEqual([m.badge, m.action], ["unchecked", "check"]);
  assert.deepEqual(acts(m), ["configure", "-", "disable"]);
});
test("cardModel: error → Налаштувати", () => {
  const m = cardModel(bi({ status: "error", error: "no-token" }));
  assert.deepEqual([m.badge, m.action, m.click], ["error", "configure", "configure"]);
  assert.deepEqual(acts(m), ["check", "-", "disable"]);
});
test("cardModel: модуль без налаштувань — «Налаштувати» у меню нема", () => {
  assert.deepEqual(acts(cardModel(bi({ settings: [] }))), ["check", "-", "disable"]);
  assert.ok(acts(cardModel(bi({ settings: undefined }))).includes("configure"), "невідомо → є");
});
test("cardModel: свій недовірений → Довірити; клік — діалог довіри; меню: Код (+ Вимкнути, коли ввімкнений)", () => {
  const m = cardModel(own());
  assert.deepEqual([m.badge, m.action, m.click], ["untrusted", "trust", "trust"]);
  assert.deepEqual(acts(m), ["trust"]);
  assert.equal(m.menu[0].key, "mcCode");
  const on = cardModel(own({ enabled: true }));
  assert.deepEqual([on.action, on.click], ["trust", "trust"]);
  assert.deepEqual(acts(on), ["trust", "-", "disable"]);
});
test("cardModel: свій refused БЕЗ знімка → Чому? (trustinfo)", () => {
  const m = cardModel(own({ trust: "refused", trust_error: "symlink", error: "x" }));
  assert.deepEqual([m.badge, m.action, m.click], ["error", "trustinfo", "trustinfo"]);
  assert.deepEqual(acts(m), ["trust"], "Код лишається; trustinfo — уже дія картки");
});
test("cardModel: свій refused ЗІ знімком (працює попередня) → дія за станом, trustinfo — у меню", () => {
  const m = cardModel(own({ trust: "refused", runs: true, enabled: true, status: "ok", record: true, settings: [{ key: "k" }] }));
  assert.deepEqual([m.badge, m.action, m.click], ["ok", null, "configure"]);
  assert.deepEqual(acts(m), ["configure", "check", "trust", "untrust", "trustinfo", "-", "disable"]);
});
test("cardModel: свій changed (довірений, у теці зміни) → Довірити, клік — шухляда", () => {
  const m = cardModel(own({ trust: "changed", runs: true, enabled: true, status: "ok", record: true, settings: [{ key: "k" }] }));
  assert.deepEqual([m.badge, m.action, m.click], ["ok", "trust", "configure"]);
  assert.deepEqual(acts(m), ["configure", "check", "trust", "untrust", "-", "disable"]);
});
test("cardModel: свій довірений вимкнений → Підключити; меню без Вимкнути і без «-»", () => {
  const m = cardModel(own({ trust: "trusted", runs: true, status: "ok", record: true }));
  assert.deepEqual([m.badge, m.action, m.click], ["off", "enable", "enable"]);
  assert.deepEqual(acts(m), ["trust", "untrust"]);
  assert.equal(m.menu.find((x) => x.act === "untrust").key, "cnUntrust");
});
test("cardModel: свій довірений увімкнений: Забрати довіру в меню, Вимкнути червоним", () => {
  const m = cardModel(own({ trust: "trusted", runs: true, enabled: true, status: "ok", record: true }));
  assert.equal(m.menu.at(-1).danger, true);
  assert.ok(acts(m).includes("untrust"));
});
test("cardModel: Не встановлено → без дії й без кліку; у меню лише Вимкнути", () => {
  const m = cardModel(bi({ status: "missing", enabled: true }));
  assert.deepEqual([m.badge, m.action, m.click], ["missing", null, null]);
  assert.deepEqual(acts(m), ["disable"]);
});
test("cardModel: сміття не кидає", () => {
  assert.doesNotThrow(() => cardModel(null));
  assert.doesNotThrow(() => cardModel({}));
});
test("BADGE_CLASS: error → err, untrusted → trust", () => {
  assert.equal(BADGE_CLASS.error, "err");
  assert.equal(BADGE_CLASS.untrusted, "trust");
  assert.equal(BADGE_CLASS.ok, "ok");
});

test("gridEntries: увімкнені, УСІ свої, missing; вимкнений вбудований — ні", () => {
  const list = [
    bi({ id: "off-builtin", enabled: false, status: "ok" }),
    bi({ id: "on" }),
    own({ id: "own-off" }),
    bi({ id: "gone", status: "missing", enabled: true }),
  ];
  assert.deepEqual(gridEntries(list).map((e) => e.id), ["on", "own-off", "gone"]);
});
test("gridEntries: порядок ROLE_ORDER, далі чужі ролі за абеткою, далі без ролі; усередині — як у списку", () => {
  const e = (id, roles) => bi({ id, roles });
  const list = [e("z", ["zeta"]), e("n", []), e("t", ["tokens"]), e("p2", ["publish"]), e("a", ["alpha"]), e("c", ["comments"]), e("p1", ["publish"])];
  assert.deepEqual(gridEntries(list).map((x) => x.id), ["p2", "p1", "c", "t", "a", "z", "n"]);
});
test("gridEntries: не масив і сміття — порожньо", () => {
  assert.deepEqual(gridEntries(null), []);
  assert.deepEqual(gridEntries([null, 3, {}, { id: 5 }]), []);
});

test("emptyRoles: роль із вимкненим вбудованим — порожня; решта ролей — у порядку ROLE_ORDER", () => {
  const r = emptyRoles([bi({ enabled: false })]);
  assert.deepEqual(r.map((x) => x.role), ["publish", "comments", "vcs", "dashboard", "tracker", "notify", "tokens"]);
  assert.deepEqual(r[0], { role: "publish", icon: "up", titleKey: "cnRolePublish", noneKey: "cnNonePublish" });
});
test("emptyRoles: роль із модулем у сітці не порожня; свій вимкнений теж покриває", () => {
  const r = emptyRoles([bi(), own({ roles: ["vcs"] })]);
  assert.ok(!r.some((x) => x.role === "publish" || x.role === "vcs"));
  assert.equal(r.length, 5);
});
test("emptyRoles: «Інше» й чужі ролі ніколи", () => {
  const r = emptyRoles([bi({ roles: ["alpha"] }), bi({ id: "x", roles: [] })]);
  assert.ok(r.every((x) => ["publish", "comments", "vcs", "dashboard", "tracker", "notify", "tokens"].includes(x.role)));
  assert.equal(r.length, 7);
});
test("emptyRoles: порожній список — усі сім", () => {
  assert.equal(emptyRoles([]).length, 7);
  assert.equal(emptyRoles(undefined).length, 7);
});
