import assert from "node:assert/strict";
import test from "node:test";
import { BADGE_CLASS, TOOL_IDS, cardModel, emptyRoles, failedRole, gridEntries, sentence, toolCardModel, toolCards } from "../app/modules-grid.js";

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
  assert.deepEqual(r[0], { role: "publish", icon: "up", titleKey: "cnRolePublish", noneKey: "cnNonePublish", error: "" });
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

test("emptyRoles: збій ролі з capabilities.errors — у `error` (код); без збою й без capabilities — порожньо", () => {
  const r = emptyRoles([], { errors: { vcs: "module-error" } });
  assert.equal(r.find((x) => x.role === "vcs").error, "module-error");
  assert.equal(r.find((x) => x.role === "publish").error, "");
  assert.ok(emptyRoles([], null).every((x) => x.error === ""));
});

test("failedRole: роль, яку ТРИМАЄ увімкнений модуль і чий збій записано; вимкнений, missing, чужа роль — порожньо", () => {
  const caps = { errors: { publish: "module-error" } };
  assert.equal(failedRole(bi(), caps), "publish");
  assert.equal(failedRole(bi({ enabled: false }), caps), "");
  assert.equal(failedRole(bi({ status: "missing" }), caps), "");
  assert.equal(failedRole(bi({ roles: ["vcs"] }), caps), "");
  assert.equal(failedRole(bi(), { errors: {} }), "");
  assert.equal(failedRole(bi(), undefined), "");
  assert.equal(failedRole(null, caps), "");
});

test("cardModel: збій ролі (roleFailed) — «Помилка» з дією «Налаштувати» замість ok/unchecked; на вимкнений і зламаний не діє", () => {
  const m = cardModel(bi({ status: "unchecked" }), true);
  assert.deepEqual([m.badge, m.action, m.click], ["error", "configure", "configure"]);
  assert.ok(!acts(m).includes("configure"), "дія вже на картці — у «⋯» її нема");
  assert.ok(acts(m).includes("check") && acts(m).includes("disable"), "решта — у «⋯»");
  assert.equal(cardModel(bi({ enabled: false, status: "unchecked" }), true).badge, "off");
  assert.equal(cardModel(bi(), false).badge, "ok", "без прапорця — як було");
  assert.equal(cardModel(bi({ status: "missing" }), true).badge, "missing");
});

test("sentence: перша літера велика, у кінці крапка; готове речення не чіпає; порожнє — порожньо", () => {
  assert.equal(sentence("коментарі лише локальні — для вас і агента"), "Коментарі лише локальні — для вас і агента.");
  assert.equal(sentence("comments are local only — for you and the agent"), "Comments are local only — for you and the agent.");
  assert.equal(sentence("Без трекера — статусів задач нема."), "Без трекера — статусів задач нема.");
  assert.equal(sentence("інспектор звіряє без токенів простору"), "Інспектор звіряє без токенів простору.");
  assert.equal(sentence("без дашборда — вкладки «Команда» нема"), "Без дашборда — вкладки «Команда» нема.");
  assert.equal(sentence("ready!"), "Ready!");
  assert.equal(sentence("  "), "");
  assert.equal(sentence(undefined), "");
  assert.equal(sentence("їжак"), "Їжак.", "кирилична «ї» — з великої, не розбита на сурогати");
});

/* ── Інструменти простору («В Figma», етап Е): вимикачі в `space.json`, а не модулі ── */
test("toolCards: один інструмент — «В Figma» під ролею «Інструменти»; ключа нема = увімкнено, лише `false` вимикає", () => {
  const on = toolCards({ figma: true })[0];
  assert.deepEqual([on.id, on.tool, on.icon, on.nameKey, on.roleKey, on.on], ["tool:figma", "figma", "figma", "toFigma", "roleTools", true]);
  assert.equal(toolCards(undefined)[0].on, true, "старий сервер без `tools`");
  assert.equal(toolCards({})[0].on, true, "відсутній ключ");
  assert.equal(toolCards(null)[0].on, true);
  assert.equal(toolCards({ figma: false })[0].on, false);
  assert.equal(toolCards({ figma: "false" })[0].on, true, "не-булеве не вимикає");
  assert.deepEqual(TOOL_IDS, ["figma"]);
});

test("toolCardModel: увімкнено — «Увімкнено», без дії, «⋯ → Вимкнути»; вимкнено — «Вимкнено» й кнопка «Увімкнути», меню порожнє", () => {
  const on = toolCardModel(toolCards({})[0]);
  assert.deepEqual([on.badge, on.badgeKey, on.action], ["ok", "toolOn", null]);
  assert.deepEqual(on.menu, [{ act: "toolask", key: "cnDisable", danger: true }]);
  assert.equal(on.askKey, "toolFigmaNone");
  const off = toolCardModel(toolCards({ figma: false })[0]);
  assert.deepEqual([off.badge, off.badgeKey, off.action, off.menu], ["off", "toolOff", { act: "toolon", key: "toolEnable" }, []]);
});
