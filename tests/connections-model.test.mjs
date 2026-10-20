import assert from "node:assert/strict";
import test from "node:test";

import {
  ROLE_ORDER, builtinText, canErase, cardView, disableConsequences, formFields, formPatch, groupModules, initialForm,
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
  assert.equal(providerLine("error", { error: "" }, list), null, "роль «error» — не постачальник; непорожній capabilities.error — окремий стан нижче");
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

test("відмова HTTP: код → ключ, timeout → cnTimeout (не «простір чи задача»), невідома — загальна з текстом", () => {
  assert.deepEqual(refusalView({ code: "role-taken", message: "publish is already provided by x" }),
    { key: "cnRefRoleTaken", detail: "publish is already provided by x" });
  assert.deepEqual(refusalView({ code: "timeout", message: "timeout" }), { key: "cnTimeout", detail: "" });
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

/* ── Фікси після ревʼю задачі 2: списки без значення, capabilities.error, точний патч, коди ─────────────────────── */

const OPTS = [{ value: "a", label: "A" }, { value: "b", label: "B" }];
const SEL = (o) => formFields({ settings: [{ key: "s", type: "select", label: "S", options: OPTS, ...o }] });
const CUR = (init, values = init.values) => ({ values: { ...values }, secrets: {}, erase: [] });

test("списки: форма стартує з того, що людина БАЧИТЬ — порожній вибір не стає тихим записом першого варіанта", () => {
  /* Обовʼязковий без значення: порожньо, «не заповнено», пише лише свідомий вибір. */
  let f = SEL({ required: true });
  assert.equal(f[0].blank, true, "обовʼязковий без значення: вʼю малює порожній варіант");
  let init = initialForm(f);
  assert.equal(init.values.s, "");
  assert.deepEqual(missingRequired(f, CUR(init)), ["s"]);
  assert.deepEqual({ ...formPatch(f, init, CUR(init, { s: "a" })).settings }, { s: "a" });
  assert.deepEqual(missingRequired(f, CUR(init, { s: "a" })), []);

  /* Обовʼязковий із значенням, якого вже нема серед варіантів: так само порожньо й «не заповнено». */
  f = SEL({ required: true, value: "gone" });
  assert.equal(f[0].blank, true);
  assert.equal(initialForm(f).values.s, "");
  assert.deepEqual(missingRequired(f, CUR(initialForm(f))), ["s"]);

  /* Необовʼязковий із застарілим значенням: початково "", тож без дотику — НІЧОГО не пишемо (раніше стирали null).
     ⚠️ cur імітує те, що віддає DOM: вʼю обирає порожній варіант, значення елемента — "". Якби `initialForm` віддав
     "gone", патч вийшов би `{s: null}` — стирання, якого людина не просила. */
  f = SEL({ required: false, value: "gone" });
  init = initialForm(f);
  assert.equal(f[0].blank, true);
  assert.equal(init.values.s, "");
  const untouched = formPatch(f, init, CUR(init, { s: "" }));
  assert.deepEqual({ ...untouched.settings }, {});
  assert.equal(isDirty(untouched), false);

  /* Із дійсним значенням: обовʼязковому порожній варіант не потрібен, необовʼязковому — потрібен (очистити). */
  f = SEL({ required: true, value: "b" });
  assert.equal(f[0].blank, false);
  assert.equal(initialForm(f).values.s, "b");
  f = SEL({ required: false, value: "b" });
  assert.equal(f[0].blank, true);
  init = initialForm(f);
  assert.equal(init.values.s, "b");
  assert.deepEqual({ ...formPatch(f, init, CUR(init, { s: "" })).settings }, { s: null }, "свідоме очищення необовʼязкового");

  /* Значення-число зіставляється з варіантом за рядком; список без варіантів — порожній. */
  assert.equal(initialForm(SEL({ value: 5, options: [{ value: "5" }] })).values.s, "5");
  assert.equal(SEL({ required: true, value: "a", options: [] })[0].blank, true);
  assert.equal(initialForm(SEL({ value: "a", options: [] })).values.s, "");
});

test("рядок «Зараз»: непорожній capabilities.error — окремий стан, раніше за читання ролі", () => {
  const list = [M("vercel-publish")];
  assert.deepEqual(providerLine("publish", { error: "space-json-unreadable" }, list), { kind: "error" });
  assert.deepEqual(providerLine("vcs", { error: "x" }, list), { kind: "error" }, "навіть для ролі, якої caps не знає");
  assert.deepEqual(providerLine("error", { error: "x" }, list), { kind: "error" });
  assert.deepEqual(providerLine("publish", { publish: "vercel-publish", error: "x" }, list), { kind: "error" },
    "помилка перемагає застарілого постачальника");
  assert.equal(providerLine("publish", { publish: "vercel-publish", error: "" }, list).kind, "module");
  assert.equal(providerLine("publish", { publish: "vercel-publish", error: null }, list).kind, "module");
  assert.equal(providerLine("publish", null, list), null, "без capabilities — як було");
});

test("патч: ключ, якого нема в cur.values, не пишеться — undefined не стає null чи false", () => {
  const f = formFields({ settings: [
    { key: "t", type: "text", label: "T", value: "x" },
    { key: "b", type: "bool", label: "B", value: true },
    { key: "s", type: "select", label: "S", value: "a", options: OPTS },
  ] });
  const init = initialForm(f);
  for (const cur of [{ values: {}, secrets: {}, erase: [] }, { secrets: {}, erase: [] }, null, undefined]) {
    const p = formPatch(f, init, cur);
    assert.deepEqual({ ...p.settings }, {}, JSON.stringify(cur));
    assert.deepEqual({ ...p.secrets }, {});
  }
});

test("патч: пробіли по краях — лише для тексту, шляху й секретів; select порівнюється й іде ТОЧНО", () => {
  const f = formFields({ settings: [
    { key: "t", type: "text", label: "T", value: "  x " },
    { key: "p", type: "path", label: "P", value: "\t/a/b\n" },
    { key: "s", type: "select", label: "S", value: " a ", options: [{ value: "a" }, { value: " a " }] },
  ] });
  const init = initialForm(f);
  assert.deepEqual({ ...init.values }, { t: "  x ", p: "\t/a/b\n", s: " a " }, "форма несе збережене як є");
  /* ⚠️ Збережене значення з пробілами без правки — НЕ зміна. Раніше це перевіряла лише одна сторона порівняння
     (обрізалось cur, а init ні), і мутація «прибрати обрізання init» виживала: ніхто не передавав початкове з
     пробілами. */
  assert.deepEqual({ ...formPatch(f, init, CUR(init)).settings }, {});
  assert.deepEqual({ ...formPatch(f, init, CUR(init, { ...init.values, t: "x" })).settings }, {},
    "зняті пробіли в тексті — та сама зміна, що й нуль");
  /* select: " a " → "a" — це ІНШИЙ варіант, і він іде як є. */
  assert.deepEqual({ ...formPatch(f, init, CUR(init, { ...init.values, s: "a" })).settings }, { s: "a" });
  const g = formFields({ settings: [{ key: "s", type: "select", label: "S", value: "a", options: [{ value: "a" }, { value: " a " }] }] });
  const ginit = initialForm(g);
  assert.deepEqual({ ...formPatch(g, ginit, CUR(ginit, { s: " a " })).settings }, { s: " a " }, "пробіл у варіанті не обрізається");
  /* Секрети обрізаються свідомо: токен вставляють з буфера разом із переносом рядка. */
  const sec = formFields({ settings: [{ key: "k", type: "secret", label: "K", required: false, set: false }] });
  assert.deepEqual({ ...formPatch(sec, initialForm(sec), { values: {}, secrets: { k: "\n tk \n" }, erase: [] }).secrets }, { k: "tk" });
});

test("коди: vercel-busy і no-folder; відмова secrets-unreadable бере текст коду перевірки, власні ключі відмов — вище", () => {
  assert.deepEqual(verdictText({ ok: false, error: "vercel-busy", detail: "retry" }), { key: "cnErrVercelBusy", detail: "retry" });
  assert.deepEqual(verdictText({ ok: false, error: "no-folder" }), { key: "cnErrBadFolder", detail: "" });
  assert.deepEqual(refusalView({ code: "secrets-unreadable", message: "keychain locked" }),
    { key: "cnErrSecretsUnreadable", detail: "keychain locked" });
  assert.equal(refusalView({ code: "vercel-busy" }).key, "cnErrVercelBusy");
  assert.equal(refusalView({ code: "no-folder" }).key, "cnErrBadFolder");
  assert.equal(refusalView({ code: "bad-settings" }).key, "cnRefBadSettings", "власний ключ відмови раніше за ключ перевірки");
  assert.equal(refusalView({ code: "role-taken" }).key, "cnRefRoleTaken");
  assert.equal(refusalView({ code: "no-such-code", message: "m" }).key, "cnRefGeneric");
  assert.equal(refusalView({ code: "timeout" }).key, "cnTimeout");
});

test("причина: перевірка без коду → сервер пише error 'check failed', і деталь ТАКОЇ перевірки видно", () => {
  assert.deepEqual(whyOf(M("a", { status: "error", error: "check failed", last_check: { ok: false, detail: "boom" } })),
    { key: "cnErrGeneric", detail: "check failed — boom" });
  assert.deepEqual(whyOf(M("a", { status: "error", error: "bad-key", last_check: { ok: false, detail: "boom" } })),
    { key: "cnErrBadKey", detail: "" }, "перевірка без коду не дає деталь іншій причині");
});

test("canErase: лише заданий необовʼязковий секрет (спільне для патча й вʼю)", () => {
  assert.equal(canErase({ type: "secret", set: true, required: false }), true);
  assert.equal(canErase({ type: "secret", set: true, required: true }), false);
  assert.equal(canErase({ type: "secret", set: false, required: false }), false);
  assert.equal(canErase({ type: "secret", set: null, required: false }), false);
  assert.equal(canErase({ type: "text", set: true, required: false }), false);
  assert.equal(canErase(null), false);
  const [a, b, c] = formFields({ settings: [
    { key: "a", type: "secret", label: "A", set: true }, { key: "b", type: "secret", label: "B", required: true, set: true },
    { key: "c", type: "secret", label: "C" },
  ] });
  assert.deepEqual([canErase(a), canErase(b), canErase(c)], [true, false, false]);
});

test("ключі constructor, toString та інші члени прототипа — звичайні власні поля в полях, формі й патчі", () => {
  const f = formFields({ settings: [
    { key: "constructor", type: "text", label: "c", value: "a" },
    { key: "toString", type: "text", label: "t" },
    { key: "valueOf", type: "bool", label: "v", value: true },
    { key: "hasOwnProperty", type: "select", label: "h", value: "x", options: [{ value: "x" }, { value: "y" }] },
    { key: "isPrototypeOf", type: "secret", label: "s", required: false, set: true },
  ] });
  assert.deepEqual(f.map((x) => x.key), ["constructor", "toString", "valueOf", "hasOwnProperty", "isPrototypeOf"]);
  const init = initialForm(f);
  assert.equal(Object.getPrototypeOf(init.values), Object.prototype);
  assert.deepEqual(Object.keys(init.values), ["constructor", "toString", "valueOf", "hasOwnProperty"]);
  assert.equal(init.values.constructor, "a");
  assert.equal(init.values.toString, "");
  assert.equal(init.values.valueOf, true);
  assert.equal(init.values.hasOwnProperty, "x");
  assert.deepEqual({ ...formPatch(f, init, CUR(init)).settings }, {});

  const p = formPatch(f, init, {
    values: Object.fromEntries([["constructor", "b"], ["toString", "z"], ["valueOf", false], ["hasOwnProperty", "y"]]),
    secrets: Object.fromEntries([["isPrototypeOf", "tok"]]), erase: [],
  });
  assert.equal(Object.getPrototypeOf(p.settings), Object.prototype);
  assert.deepEqual(Object.keys(p.settings).sort(), ["constructor", "hasOwnProperty", "toString", "valueOf"]);
  assert.equal(p.settings.constructor, "b");
  assert.equal(p.settings.valueOf, false);
  assert.deepEqual(Object.keys(p.secrets), ["isPrototypeOf"]);
  assert.equal(p.secrets.isPrototypeOf, "tok");
  const erased = formPatch(f, init, { ...CUR(init), erase: ["isPrototypeOf"] });
  assert.equal(erased.secrets.isPrototypeOf, null, "стерти заданий необовʼязковий секрет з таким ключем");

  /* Застарілий init без ключів (у живому коді такого нема, але читання не мусить знаходити члени прототипа):
     порожнє — це порожнє, а не `String(Object)`, тож і запису нема. */
  const bare = formPatch(f, { values: {}, secrets: {}, erase: [] },
    CUR(init, Object.fromEntries([["constructor", ""], ["toString", ""], ["valueOf", false], ["hasOwnProperty", ""]])));
  assert.deepEqual({ ...bare.settings }, {}, "чужий init без ключів: рядки не вигадуються з прототипа");
  assert.deepEqual(missingRequired(formFields({ settings: [{ key: "constructor", type: "text", label: "c", required: true }] }),
    { values: {}, secrets: {}, erase: [] }), ["constructor"]);
});
