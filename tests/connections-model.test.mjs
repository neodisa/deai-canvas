import assert from "node:assert/strict";
import test from "node:test";

import {
  ROLE_ORDER, builtinText, cardView, disableConsequences, formFields, formPatch, groupModules, initialForm,
  isDirty, missingRequired, providerLine, refusalView, roleHolders, roleIcon, roleKeys, verdictText, whyOf,
  writePayload,
} from "../app/connections-model.js";

const M = (id, o = {}) => ({ id, name: id, roles: ["publish"], enabled: false, implicit: false, status: "unchecked",
  settings: [], ...o });

test("ролі: порядок секцій, ключі й іконки; чужа роль і __proto__ не мають ключів", () => {
  assert.deepEqual(ROLE_ORDER, ["publish", "comments", "tokens"]);
  assert.equal(roleKeys("publish").title, "cnRolePublish");
  assert.equal(roleKeys("comments").none, "cnNoneComments");
  assert.equal(roleKeys("vcs"), null);
  assert.equal(roleKeys("__proto__"), null);
  assert.equal(roleKeys("toString"), null);
  assert.equal(roleIcon("publish"), "up");
  assert.equal(roleIcon("comments"), "comment");
  assert.equal(roleIcon("tokens"), "sliders");
  assert.equal(roleIcon("vcs"), "dots");
  assert.equal(roleIcon(undefined), "dots");
  assert.equal(roleIcon("constructor"), "dots");
});

test("вбудовані тексти: чотири модулі, решта — null", () => {
  for (const id of ["static-publish", "vercel-publish", "supabase-comments", "css-tokens"]) {
    const b = builtinText(id);
    assert.ok(b && b.name && b.desc && b.fields, id);
  }
  assert.equal(builtinText("static-publish").fields.folder, "cnFieldStaticFolder");
  assert.equal(builtinText("memo-publish"), null);
  assert.equal(builtinText("__proto__"), null);
});

test("групування: відомі ролі за порядком, далі інші за абеткою, без ролі — останні; missing окремо", () => {
  const list = [
    M("t", { roles: ["tokens"] }), M("z", { roles: ["vcs"] }), M("a", { roles: ["alpha"] }),
    M("p2"), M("p1"), M("n", { roles: [] }), M("c", { roles: ["comments", "publish"] }),
    { id: "gone", name: "gone", roles: [], enabled: true, status: "missing", settings: [] },
    null, { name: "без id" },
  ];
  const { sections, missing } = groupModules(list);
  assert.deepEqual(sections.map((s) => s.role), ["publish", "comments", "tokens", "alpha", "vcs", ""]);
  assert.deepEqual(sections[0].modules.map((e) => e.id), ["p2", "p1"], "порядок усередині — як у списку сервера");
  assert.deepEqual(sections[1].modules.map((e) => e.id), ["c"], "кілька ролей — у секції першої");
  assert.deepEqual(missing.map((e) => e.id), ["gone"]);
  assert.deepEqual(groupModules(null), { sections: [], missing: [] });
});

test("рядок «Зараз»: модуль, legacy, нікого з наслідком, невідома роль, нема capabilities", () => {
  const list = [M("vercel-publish", { name: "Vercel" })];
  assert.deepEqual(providerLine("publish", { publish: "vercel-publish" }, list),
    { kind: "module", id: "vercel-publish", entry: list[0] });
  assert.deepEqual(providerLine("publish", { publish: "ghost" }, list), { kind: "module", id: "ghost", entry: null });
  assert.deepEqual(providerLine("comments", { comments: "legacy" }, list), { kind: "legacy" });
  assert.deepEqual(providerLine("tokens", { tokens: null }, list), { kind: "none", noneKey: "cnNoneTokens" });
  assert.equal(providerLine("vcs", { publish: null }, list), null, "роль, якої capabilities не знає");
  assert.equal(providerLine("error", { error: "x" }, list), null);
  assert.equal(providerLine("publish", null, list), null);
  assert.equal(providerLine("__proto__", {}, list), null);
});

test("картка: бейдж і дії для кожного стану", () => {
  assert.deepEqual(cardView(M("a", { status: "missing", enabled: true })),
    { badge: "missing", actions: ["disable"], why: true, implicit: false });
  assert.deepEqual(cardView(M("a", { enabled: false, status: "error" })),
    { badge: "off", actions: ["enable"], why: false, implicit: false });
  assert.deepEqual(cardView(M("a", { enabled: true, status: "ok" })),
    { badge: "ok", actions: ["configure", "check", "disable"], why: false, implicit: false });
  assert.deepEqual(cardView(M("a", { enabled: true, status: "unchecked", implicit: true })),
    { badge: "unchecked", actions: ["configure", "check", "disable"], why: false, implicit: true });
  assert.deepEqual(cardView(M("a", { enabled: true, status: "error" })),
    { badge: "error", actions: ["configure", "check", "disable"], why: true, implicit: false });
});

test("вердикт: відомий код, невідомий код, вільний текст, ok, обрізання до 300", () => {
  assert.deepEqual(verdictText({ ok: true, detail: "2 tokens" }), { key: "cnCheckOk", detail: "2 tokens" });
  assert.deepEqual(verdictText({ ok: false, error: "no-token", detail: "Токен не задано" }),
    { key: "cnErrNoToken", detail: "Токен не задано" });
  assert.deepEqual(verdictText({ ok: false, error: "file: not found" }), { key: "cnErrGeneric", detail: "file: not found" });
  assert.deepEqual(verdictText({ ok: false, error: "weird", detail: "why" }), { key: "cnErrGeneric", detail: "weird — why" });
  assert.deepEqual(verdictText(null), { key: "cnErrGeneric", detail: "" });
  const long = verdictText({ ok: false, error: "network", detail: "x".repeat(500) });
  assert.equal(long.key, "cnErrNetwork");
  assert.equal(long.detail.length, 300);
  assert.ok(long.detail.endsWith("…"));
  for (const code of ["bad-settings", "module-error", "check-timeout", "secrets-unreadable", "bad-manifest",
    "bad-folder", "not-writable", "no-token", "vercel-auth", "vercel-error", "bad-key", "no-schema",
    "supabase-error", "network"]) {
    assert.notEqual(verdictText({ ok: false, error: code }).key, "cnErrGeneric", code);
  }
});

test("причина: missing; error з деталлю лише свого last_check; не-error — null", () => {
  assert.deepEqual(whyOf(M("a", { status: "missing" })), { key: "cnWhyMissing", detail: "" });
  assert.deepEqual(whyOf(M("a", { status: "error", error: "bad-key", last_check: { ok: false, error: "bad-key", detail: "401" } })),
    { key: "cnErrBadKey", detail: "401" });
  assert.deepEqual(whyOf(M("a", { status: "error", error: "secrets-unreadable", last_check: { ok: true, detail: "2 tokens" } })),
    { key: "cnErrSecretsUnreadable", detail: "" }, "стара успішна перевірка не дає деталь чужій причині");
  /* ⚠️ Окремий випадок, якого немає в першому: стара НЕУСПІШНА перевірка з ІНШИМ кодом. Без нього умова
     `lc.error === e.error` лишалась недоведеною — `lc.ok === false` сама відсікала успішний вердикт, і
     мутація «прибрати порівняння кодів» виживала. */
  assert.deepEqual(whyOf(M("a", { status: "error", error: "secrets-unreadable", last_check: { ok: false, error: "bad-key", detail: "401" } })),
    { key: "cnErrSecretsUnreadable", detail: "" }, "деталь чужого вердикту не прилипає до іншої причини");
  assert.equal(whyOf(M("a", { status: "ok" })), null);
  assert.equal(whyOf(null), null);
});

test("відмова HTTP: код → ключ, timeout → formTimeout, невідома — загальна з текстом", () => {
  assert.deepEqual(refusalView({ code: "role-taken", message: "publish is already provided by x" }),
    { key: "cnRefRoleTaken", detail: "publish is already provided by x" });
  assert.deepEqual(refusalView({ code: "timeout", message: "timeout" }), { key: "formTimeout", detail: "" });
  assert.deepEqual(refusalView({ message: "boom" }), { key: "cnRefGeneric", detail: "boom" });
  for (const code of ["bad-settings", "unknown-module", "unknown-space", "space-json-unreadable", "spaces-off", "unwritable"]) {
    assert.notEqual(refusalView({ code }).key, "cnRefGeneric", code);
  }
});

test("хто тримає ролі: увімкнені (і неявний) з перетином ролей, крім самого себе й missing", () => {
  const me = M("vercel-publish");
  const list = [me, M("static-publish", { enabled: true, implicit: true }), M("off-pub", { enabled: false }),
    M("cm", { roles: ["comments"], enabled: true }), { id: "gone", roles: ["publish"], enabled: true, status: "missing" }];
  assert.deepEqual(roleHolders(me, list).map((e) => e.id), ["static-publish"]);
  assert.deepEqual(roleHolders(M("x", { roles: [] }), list), []);
  assert.deepEqual(roleHolders(me, null), []);
});

test("наслідки вимкнення: legacy для ЛІГА publish/comments, «нікого» інакше, лише для ролей, які він тримає", () => {
  const e = M("vercel-publish");
  assert.deepEqual(disableConsequences(e, { integrations: false, capabilities: { publish: "vercel-publish" } }),
    [{ role: "publish", kind: "none", noneKey: "cnNonePublish" }]);
  assert.deepEqual(disableConsequences(e, { integrations: true, capabilities: { publish: "vercel-publish" } }),
    [{ role: "publish", kind: "legacy" }]);
  assert.deepEqual(disableConsequences(e, { integrations: false, capabilities: { publish: "static-publish" } }), []);
  const tok = M("css-tokens", { roles: ["tokens"] });
  assert.deepEqual(disableConsequences(tok, { integrations: true, capabilities: { tokens: "css-tokens" } }),
    [{ role: "tokens", kind: "none", noneKey: "cnNoneTokens" }], "токенів ЛІГА не має — legacy тут нема");
  assert.deepEqual(disableConsequences(e, null), []);
});

const SETTINGS = [
  { key: "folder", type: "path", label: "Тека", required: true, value: "{home}/deai-published/{space_id}" },
  { key: "team", type: "text", label: "Команда", required: false },
  { key: "on", type: "bool", label: "Прапорець", required: false, value: true },
  { key: "mode", type: "select", label: "Режим", required: false, value: "a",
    options: [{ value: "a", label: "A" }, { value: "b" }, { label: "без значення" }] },
  { key: "token", type: "secret", label: "Токен", required: true, set: false },
  { key: "password", type: "secret", label: "Пароль", required: false, set: true },
  { key: "odd", type: "weird", label: "", required: false, value: 5 },
];

test("поля форми з settings[]", () => {
  const f = formFields({ settings: [...SETTINGS, null, { type: "text" }] });
  assert.deepEqual(f.map((x) => [x.key, x.type]), [["folder", "path"], ["team", "text"], ["on", "bool"],
    ["mode", "select"], ["token", "secret"], ["password", "secret"], ["odd", "text"]]);
  assert.equal(f[4].set, false);
  assert.equal(f[5].set, true);
  assert.equal(f[4].value, undefined, "секрет не несе значення");
  assert.deepEqual(f[3].options, [{ value: "a", label: "A" }, { value: "b", label: "b" }]);
  assert.equal(f[6].label, "odd", "порожній підпис — ключ");
  assert.equal(formFields({ settings: [{ key: "k", type: "secret", label: "K", set: null }] })[0].set, null);
});

test("початкова форма й патч: лише змінене, обрізання пробілів, очищене необовʼязкове — null", () => {
  const f = formFields({ settings: SETTINGS });
  const init = initialForm(f);
  assert.deepEqual({ ...init.values }, { folder: "{home}/deai-published/{space_id}", team: "", on: true, mode: "a", odd: "5" });
  assert.deepEqual(init.erase, []);
  const same = formPatch(f, init, { values: { ...init.values }, secrets: { token: "", password: "  " }, erase: [] });
  assert.deepEqual({ ...same.settings }, {});
  assert.deepEqual({ ...same.secrets }, {});
  assert.equal(isDirty(same), false);
  const p = formPatch(f, init, {
    values: { ...init.values, team: "  acme ", on: false, mode: "b", odd: "" },
    secrets: { token: " tk-1 \n", password: "" }, erase: ["password"],
  });
  assert.deepEqual({ ...p.settings }, { team: "acme", on: false, mode: "b", odd: null });
  assert.deepEqual({ ...p.secrets }, { token: "tk-1", password: null });
  assert.equal(isDirty(p), true);
});

test("патч: стерти можна лише заданий необовʼязковий; введене перемагає стирання", () => {
  const f = formFields({ settings: SETTINGS });
  const init = initialForm(f);
  const p = formPatch(f, init, { values: { ...init.values }, secrets: { password: "new" }, erase: ["password", "token"] });
  assert.deepEqual({ ...p.secrets }, { password: "new" });
});

test("патч: ключ __proto__ — звичайне власне поле, не прототип", () => {
  const f = formFields({ settings: [{ key: "__proto__", type: "text", label: "x", value: "a" }] });
  const init = initialForm(f);
  const p = formPatch(f, init, { values: Object.fromEntries([["__proto__", "b"]]), secrets: {}, erase: [] });
  assert.equal(Object.getPrototypeOf(p.settings), Object.prototype);
  assert.deepEqual(Object.keys(p.settings), ["__proto__"]);
  assert.equal(JSON.parse(JSON.stringify(p.settings)).__proto__, "b");
});

test("обовʼязкові: порожній шлях, незаданий і невведений секрет; заданий секрет і прапорець — ні", () => {
  const f = formFields({ settings: SETTINGS });
  const init = initialForm(f);
  assert.deepEqual(missingRequired(f, { values: { ...init.values, folder: "  " }, secrets: {}, erase: [] }), ["folder", "token"]);
  assert.deepEqual(missingRequired(f, { values: { ...init.values }, secrets: { token: "x" }, erase: [] }), []);
  const unknown = formFields({ settings: [{ key: "k", type: "secret", label: "K", required: true, set: null }] });
  assert.deepEqual(missingRequired(unknown, { values: {}, secrets: {}, erase: [] }), ["k"], "невідомо — теж треба ввести");
});

test("тіло запиту: space і id завжди, порожні патчі не йдуть, replace лише true", () => {
  assert.deepEqual(writePayload("s", "m", { settings: {}, secrets: {} }), { space: "s", id: "m" });
  assert.deepEqual(writePayload("s", "m", { settings: { a: 1 }, secrets: { b: null } }, true),
    { space: "s", id: "m", settings: { a: 1 }, secrets: { b: null }, replace: true });
  assert.deepEqual(writePayload("s", "m", null, "yes"), { space: "s", id: "m" });
});

/* ⚠️ Прогалини першої редакції цього файла: мутації, що ВИЖИВАЛИ проти тестів вище (знайдено перед комітом). Кожен
   рядок нижче вбиває рівно одну з них. Без цього охоронці спеки «стерти можна лише заданий необовʼязковий»,
   «крім самого себе» й «нічого не змінено — кнопка вимкнена» червоніти не вміли б: на даних плану вони були
   недосяжні (самого себе там вимкнено, а секрети — або обовʼязкові, або вже задані й необовʼязкові лише в одній парі). */
test("прогалини: стирання секрету, власник ролі — не сам модуль, брудний патч з однієї половини, обовʼязковий прапорець", () => {
  const f = formFields({ settings: [
    { key: "opt-unset", type: "secret", label: "A", required: false, set: false },
    { key: "req-set", type: "secret", label: "B", required: true, set: true },
    { key: "flag", type: "bool", label: "C", required: true, value: false },
  ] });
  const init = initialForm(f);
  const p = formPatch(f, init, { values: { ...init.values }, secrets: {}, erase: ["opt-unset", "req-set"] });
  assert.deepEqual({ ...p.secrets }, {}, "незаданий необовʼязковий і обовʼязковий заданий — стирати нічого/не можна");
  assert.deepEqual(missingRequired(f, { values: {}, secrets: {}, erase: [] }), [], "обовʼязковий прапорець не буває «порожнім»");

  const self = M("vercel-publish", { enabled: true });
  assert.deepEqual(roleHolders(self, [self]).map((e) => e.id), [], "увімкнений модуль не тримає роль «замість себе»");

  assert.equal(isDirty({ settings: { a: 1 }, secrets: {} }), true, "лише налаштування");
  assert.equal(isDirty({ settings: {}, secrets: { b: "x" } }), true, "лише секрети");
  assert.equal(isDirty(null), false);
});
