import assert from "node:assert/strict";
import test from "node:test";

import { DICT, setLang } from "../app/i18n.js";
import { cardHTML, connPageHTML, drawerHTML, fieldHTML, modName, nowHTML, roleTitle } from "../app/connections-view.js";
import {
  builtinText, formFields, initialForm, refusalView, roleKeys, verdictText,
} from "../app/connections-model.js";

const SP = { id: "studio", name: "Studio", path: "/u/work/studio",
  capabilities: { publish: "static-publish", comments: null, tokens: null } };
const LIST = [
  { id: "css-tokens", name: "Токени з CSS", roles: ["tokens"], enabled: false, implicit: false, status: "unchecked",
    settings: [{ key: "file", type: "path", label: "CSS-файл із токенами дизайн-системи", required: true }] },
  { id: "static-publish", name: "Публікація в теку", roles: ["publish"], enabled: true, implicit: true, status: "unchecked",
    settings: [{ key: "folder", type: "path", label: "Тека", required: true, value: "{home}/deai-published/{space_id}" },
      { key: "password", type: "secret", label: "Пароль", required: false, set: true }] },
  { id: "supabase-comments", name: "Supabase", roles: ["comments"], enabled: false, implicit: false, status: "unchecked", settings: [] },
  { id: "vercel-publish", name: "Vercel", roles: ["publish"], enabled: false, implicit: false, status: "unchecked", settings: [] },
];
const view = (o = {}) => ({ space: SP, list: LIST, failed: null, busy: new Map(), ...o });

test.beforeEach(() => setLang("uk"));

/* Помічники розбору розмітки: усе — регекспом по рядку, без DOM (node). Тег — від `<` до першого `>`: дані в розмітці
   екрановані, тож зайвого `>` усередині атрибута бути не може (а якби був — це і є вада, яку ловлять тести). */
const ent = (settings, o = {}) => ({ id: "m", name: "M", roles: ["publish"], enabled: true, status: "ok", settings, ...o });
const drawer = (e, over = {}) => {
  const fields = formFields(e);
  return drawerHTML({ entry: e, mode: "edit", fields, form: initialForm(fields), busy: false, result: null, errors: {},
    spaceName: "S", ...over });
};
const escRe = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
/** Тег поля (`input|select`) за його `data-cn-field` (значення — уже в екранованому вигляді). */
const fieldTag = (h, key) => new RegExp(`<(?:input|select)\\b[^>]*data-cn-field="${escRe(key)}"[^>]*>`).exec(h)?.[0] ?? null;
const attr = (tag, name) => new RegExp(`\\s${name}="([^"]*)"`).exec(tag ?? "")?.[1] ?? null;
const tokens = (tag, name) => (attr(tag, name) ?? "").split(" ").filter(Boolean);
/** Текст кнопки з даною дією `data-cn="…"` без розмітки всередині (іконка — це `<svg>`). */
const btnText = (h, act) => {
  const m = new RegExp(`<button[^>]*data-cn="${act}"[^>]*>([\\s\\S]*?)</button>`).exec(h);
  return m ? m[1].replace(/<[^>]*>/g, "").trim() : null;
};

test("сторінка: заголовок, тека, секції в порядку ролей, рядок «Зараз», агент з id простору", () => {
  const h = connPageHTML(view());
  assert.match(h, /Підключення · Studio/);
  assert.match(h, /\/u\/work\/studio\/space\.json/);
  const order = ["Публікація", "Командні коментарі", "Токени дизайн-системи"].map((s) => h.indexOf(`>${s}<`));
  assert.ok(order.every((i) => i > 0) && order[0] < order[1] && order[1] < order[2], String(order));
  assert.match(h, /Зараз: Публікація в теку/);
  assert.match(h, /Зараз: нікого — коментарі лише локальні/);
  assert.match(h, /\/api\/modules\?space=studio/);
  assert.doesNotMatch(h, /Не встановлені/, "секції missing нема, коли таких модулів нема");
});

test("сторінка: ЛІГА-модулі, missing-секція, завантаження, помилка списку й нечитабельний space.json", () => {
  const liga = { ...SP, capabilities: { publish: "vercel-publish", comments: "supabase-comments", tokens: null }, compat: { publish: "design-canvas" } };
  const missing = { id: "gone", name: "gone", roles: [], enabled: true, status: "missing", settings: [] };
  const h = connPageHTML(view({ space: liga, list: [...LIST, missing] }));
  assert.doesNotMatch(h, /вбудована інтеграція ЛІГА/, "4d-4c: вбудованої інтеграції нема — рядок «Зараз» показує модуль");
  assert.match(h, /Не встановлені на цьому компʼютері/);
  assert.match(h, /data-cn="disable" data-id="gone"/);
  assert.match(connPageHTML(view({ list: null })), /class="cn-loading" role="status">Завантажую модулі…</,
    "завантаження оголошується читачу екрана (role=status)");
  const failed = connPageHTML(view({ list: null, failed: { code: null, message: "<b>boom</b>" } }));
  assert.match(failed, /Не вдалося прочитати модулі простору/);
  assert.match(failed, /data-cn="retry"/);
  assert.doesNotMatch(failed, /<b>boom/);
  const sj = connPageHTML(view({ list: null, failed: { code: "space-json-unreadable", message: "x" } }));
  assert.match(sj, /space\.json цього простору не читається/);
  assert.doesNotMatch(connPageHTML(view({ space: { ...SP, capabilities: { error: "space-json-unreadable" } } })), /cn-card/,
    "capabilities.error — картки не малюються");
});

test("сторінка: простору нема — порожньо; неоцінений space.json не малює рядків «Зараз»", () => {
  assert.equal(connPageHTML(view({ space: null })), "");
  assert.equal(connPageHTML(null), "");
  const bad = connPageHTML(view({ space: { ...SP, capabilities: { error: "space-json-unreadable" } } }));
  assert.match(bad, /role="alert"/);
  assert.match(bad, /data-cn="retry"/);
  assert.doesNotMatch(bad, /cn-now|Зараз:/, "стара capabilities нічого не варта — «Зараз» не показуємо");
});

test("тексти ролі tracker (4c-2): усі ключі є в UK і EN, а підписи полів Jira — з BUILTIN_TEXT", () => {
  const keys = ["cnRoleTracker", "cnRoleTrackerLead", "cnNoneTracker", "cnModJiraName", "cnModJiraDesc", "cnFieldJiraBase",
    "cnFieldJiraEmail", "cnFieldJiraToken", "cnDisableTracker", "cnErrTrackerAuth"];
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(typeof DICT[lang][k] === "string" && DICT[lang][k], `${lang}: немає ключа «${k}»`);
  assert.equal(DICT.en.cnRoleTracker, "Issue tracker");
  assert.equal(DICT.en.cnErrTrackerAuth, "Jira rejected the email or token.");
  assert.equal(DICT.uk.cnErrTrackerAuth, "Jira не прийняла email чи токен.");
  const b = builtinText("jira-tracker");
  for (const k of [b.name, b.desc, ...Object.values(b.fields)]) assert.ok(DICT.uk[k] && DICT.en[k], k);
});

test("тексти ролі notify (4c-3): усі ключі є в UK і EN, а підписи полів supabase-teams — з BUILTIN_TEXT", () => {
  const keys = ["cnRoleNotify", "cnRoleNotifyLead", "cnNoneNotify", "cnModSbTeamsName", "cnModSbTeamsDesc", "cnFieldSbTeamsUrl",
    "cnFieldSbTeamsKey", "cnDisableNotify", "cnErrNotifyNoWebhook", "cnErrNotifyNoSchema", "cnErrPublicKey"];
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(typeof DICT[lang][k] === "string" && DICT[lang][k], `${lang}: немає ключа «${k}»`);
  assert.equal(DICT.en.cnRoleNotify, "Teams notifications");
  assert.equal(DICT.uk.cnRoleNotify, "Сповіщення Teams");
  assert.equal(DICT.uk.cnErrNotifyNoSchema, "У базі нема функцій сповіщень — виконайте schema.sql модуля.");
  assert.equal(DICT.en.cnErrNotifyNoSchema, "The database has no notification functions — run the module's schema.sql.");
  assert.equal(DICT.uk.cnErrPublicKey, "Потрібен непублічний ключ (service_role), а вказано публічний.");
  assert.equal(DICT.en.cnErrPublicKey, "This needs the non-public (service_role) key, not the public one.");
  const b = builtinText("supabase-teams");
  for (const k of [b.name, b.desc, ...Object.values(b.fields)]) assert.ok(DICT.uk[k] && DICT.en[k], k);
});

test("рядок «Зараз»: модуль, модуль без запису, нікого, space.json не читається, невідома роль", () => {
  const v = (caps) => ({ space: { ...SP, capabilities: caps }, list: LIST });
  assert.match(nowHTML("publish", v({ publish: "static-publish" })), /Зараз: Публікація в теку/);
  assert.doesNotMatch(nowHTML("publish", v({ publish: "legacy" })), /вбудована інтеграція ЛІГА/, "4d-4c: «legacy» — звичайний id, не особливий рядок");
  assert.match(nowHTML("publish", v({ publish: "ghost-id" })), /Зараз: ghost-id/, "нема в списку — показуємо id, а не падаємо");
  assert.match(nowHTML("comments", v({ comments: null })), /Зараз: нікого — коментарі лише локальні/);
  assert.match(nowHTML("alpha", v({ alpha: null })), /Зараз: нікого$|Зараз: нікого</, "роль без власного тексту — просто «нікого» (4c-3: приклад alpha — tracker і notify мають тексти)");
  assert.match(nowHTML("notify", v({ notify: null })), /Зараз: нікого — Без сповіщень — Teams мовчить\./, "4c-3: роль notify має власний текст «нікого»");
  assert.match(nowHTML("tracker", v({ tracker: null })), /Зараз: нікого — Без трекера — статусів задач нема\./, "4c-2: роль tracker має власний текст «нікого»");
  assert.match(nowHTML("vcs", v({ vcs: null })), /Зараз: нікого — макети лише на цьому компʼютері/, "роль vcs має власний текст «нікого»");
  assert.match(nowHTML("dashboard", v({ dashboard: null })), /Зараз: нікого — без дашборда — вкладки «Команда» нема/, "4c-1: роль dashboard має власний текст «нікого»");
  assert.match(nowHTML("vcs", { space: { ...SP, capabilities: { vcs: "git-sync" } }, list: [{ id: "git-sync", name: "Синхронізація з git", roles: ["vcs"] }] }),
    /Зараз: Git</, "постачальник — назва вбудованого модуля зі словника, а не сирий id чи назва з маніфесту");
  assert.match(nowHTML("publish", v({ error: "space-json-unreadable" })), /Зараз: невідомо — space\.json не читається/);
  assert.equal(nowHTML("alpha", v({ publish: "static-publish" })), "", "роль, якої capabilities не знає, — без рядка (4c-3: приклад alpha)");
  setLang("en");
  assert.match(nowHTML("publish", v({ error: "space-json-unreadable" })), /Now: unknown — space\.json cannot be read/);
});

test("картка: бейдж, «типово», дії з data-cn і data-id, опис вбудованого, причина помилки", () => {
  const sp = cardHTML(LIST[1], new Map());
  assert.match(sp, /Публікація в теку/);
  assert.match(sp, /cn-badge--unchecked/);
  assert.match(sp, />типово</);
  for (const a of ["configure", "check", "disable"]) assert.match(sp, new RegExp(`data-cn="${a}" data-id="static-publish"`));
  assert.match(sp, /Збирає превʼю в теку/);
  const err = cardHTML({ ...LIST[3], enabled: true, status: "error", error: "no-token",
    last_check: { ok: false, error: "no-token", detail: "Токен Vercel не задано" } }, new Map());
  assert.match(err, /cn-badge--error/);
  assert.match(err, /Токен Vercel не задано\./);
  const busy = cardHTML({ ...LIST[1] }, new Map([["static-publish", "check"]]));
  assert.match(busy, /Перевіряю…/);
  assert.match(busy, /disabled/);
});

test("картка: вимкнений — лише «Підключити» без причини; код vercel-busy має свій текст", () => {
  const off = cardHTML(LIST[3], new Map());
  assert.match(off, /cn-badge--off/);
  assert.match(off, /data-cn="enable" data-id="vercel-publish"/);
  assert.doesNotMatch(off, /data-cn="(configure|check|disable)"|cn-why/);
  assert.doesNotMatch(off, />типово</);
  const busy = cardHTML({ ...LIST[3], enabled: true, status: "error", error: "vercel-busy",
    last_check: { ok: false, error: "vercel-busy" } }, new Map());
  assert.match(busy, /Vercel тимчасово відмовляє \(ліміт запитів\)/);
});

test("картка: ворожі назва, id і деталь — лише текстом", () => {
  const evil = { id: 'x"><img src=x onerror=1>', name: "<b>n</b>", roles: ["<script>"], enabled: true, status: "error",
    error: "<i>e</i>", last_check: { ok: false, error: "<i>e</i>", detail: "<svg onload=1>" }, settings: [] };
  const h = cardHTML(evil, new Map());
  /* `<svg` без продовження не годиться: це початок розмітки справжньої `ico()` (`<svg class="ico" …>`). */
  assert.doesNotMatch(h, /<img|<b>n|<script>|<i>e|<svg onload/);
  assert.match(h, /&lt;b&gt;n&lt;\/b&gt;/);
  assert.match(h, /data-id="x&quot;&gt;&lt;img src=x onerror=1&gt;"/);
});

test("назви й підписи вбудованих — мовою інтерфейсу; чужі — з маніфесту", () => {
  setLang("en");
  assert.equal(modName(LIST[1]), "Publish to a folder");
  assert.equal(roleTitle("publish"), "Publishing");
  assert.equal(roleTitle("vcs"), "Git sync");
  assert.equal(roleTitle("dashboard"), "Team dashboard", "4c-1: а не сире слово «dashboard»");
  assert.equal(roleTitle("tracker"), "Issue tracker", "4c-2: а не сире слово «tracker»");
  assert.equal(roleTitle("notify"), "Teams notifications", "4c-3: а не сире слово «notify»");
  assert.equal(roleTitle("alpha"), "alpha", "роль без тексту — просто імʼя (4c-3: приклад alpha замість notify)");
  assert.equal(roleTitle(""), "Other");
  assert.equal(modName({ id: "memo-publish", name: "Memo (тест)" }), "Memo (тест)");
  assert.equal(modName({ id: "bare" }), "bare", "без назви — id");
  assert.equal(roleTitle("__proto__"), "__proto__", "роль з прототипу — просто імʼя");
});

test("панель: поля за типами, секрет без значення, стерти лише заданий необовʼязковий, підказка шляху", () => {
  const e = { id: "vault", name: "Vault", roles: ["publish"], enabled: true, status: "ok", settings: [
    { key: "folder", type: "path", label: "Тека", required: true, value: '{home}/"x"' },
    { key: "on", type: "bool", label: "Прапор", required: false, value: true },
    { key: "mode", type: "select", label: "Режим", required: false, value: "b", options: [{ value: "a", label: "A" }, { value: "b", label: "<B>" }] },
    { key: "token", type: "secret", label: "Токен", required: true, set: true },
    { key: "pw", type: "secret", label: "Пароль", required: false, set: true },
    { key: "nope", type: "secret", label: "Ні", required: false, set: null },
  ] };
  const fields = formFields(e);
  const h = drawerHTML({ entry: e, mode: "edit", fields, form: initialForm(fields), busy: false, result: null, errors: {}, spaceName: "Studio" });
  assert.match(h, /value="\{home\}\/&quot;x&quot;"/);
  assert.match(h, /type="checkbox"[^>]*checked/);
  assert.match(h, /<option value="b" selected>&lt;B&gt;<\/option>/);
  const pw = [...h.matchAll(/<input[^>]*type="password"[^>]*>/g)].map((m) => m[0]);
  assert.equal(pw.length, 3);
  for (const i of pw) {
    assert.doesNotMatch(i, /\svalue=/, "секрет ніколи не потрапляє в розмітку");
    assert.match(i, /autocomplete="new-password"/);
  }
  assert.equal((h.match(/data-cn-dr="erase"/g) || []).length, 1, "стерти — лише заданий необовʼязковий (pw)");
  assert.match(h, /data-cn-dr="erase" data-key="pw"/);
  assert.match(h, /невідомо — сховище секретів не читається/);
  assert.match(h, /\{home\} — домашня тека/);
  assert.match(h, /data-cn-dr="check"/, "у режимі правки є «Перевірити»");
  assert.match(h, /data-cn-dr="submit"[^>]*>Зберегти</);
});

test("панель: введений секрет і позначка «стерти» — значення в розмітку не потрапляє, стан кнопки видно", () => {
  const e = { id: "vault", name: "Vault", roles: ["publish"], enabled: true, status: "ok", settings: [
    { key: "token", type: "secret", label: "Токен", required: true, set: false },
    { key: "pw", type: "secret", label: "Пароль", required: false, set: true },
  ] };
  const fields = formFields(e);
  const base = { entry: e, mode: "edit", fields, busy: false, result: null, errors: {}, spaceName: "Studio" };
  const typed = drawerHTML({ ...base, form: { values: {}, secrets: { token: "S3CR3T-<x>", pw: "ANOTHER" }, erase: [] } });
  assert.doesNotMatch(typed, /S3CR3T|ANOTHER/, "введений секрет не повертається в розмітку");
  /* Без позначки: підпис кнопки СТАЛИЙ («Стерти»), стан — лише `aria-pressed`; примітка про стирання схована. */
  assert.match(typed, /data-cn-dr="erase" data-key="pw" aria-pressed="false" aria-label="Стерти: Пароль"[^>]*>Стерти</);
  assert.match(typed, /data-cn-erase-note="pw" hidden/);
  /* З позначкою: той самий підпис, `aria-pressed="true"`, примітка видима. */
  const marked = drawerHTML({ ...base, form: { values: {}, secrets: {}, erase: ["pw"] } });
  assert.match(marked, /data-cn-dr="erase" data-key="pw" aria-pressed="true" aria-label="Стерти: Пароль"[^>]*>Стерти</);
  assert.match(marked, /data-cn-erase-note="pw">буде стерто після збереження</);
  assert.doesNotMatch(marked, /Не стирати/, "підпис кнопки не міняється від стану");
  /* Стан секрету: «не задано» для токена, «задано» для пароля; плейсхолдери різні. */
  assert.match(typed, /не задано · Зберігається поза текою простору/);
  assert.match(typed, /задано · Зберігається/);
  assert.match(typed, /placeholder="Введіть значення"/);
  assert.match(typed, /placeholder="Нове значення \(порожньо — не міняти\)"/);
});

test("панель: список — порожня опція лише коли `blank`; вибрана, коли значення форми порожнє", () => {
  const opts = [{ value: "a", label: "A" }, { value: "b", label: "B" }];
  const sel = (o) => ({ key: "mode", type: "select", label: "Режим", options: opts, ...o });
  const html = (settings) => {
    const e = { id: "m", name: "M", roles: ["publish"], enabled: true, status: "ok", settings };
    const fields = formFields(e);
    return drawerHTML({ entry: e, mode: "edit", fields, form: initialForm(fields), busy: false, result: null, errors: {}, spaceName: "S" });
  };
  const blank = (h) => (h.match(/<option value=""/g) || []).length;

  /* Обовʼязковий зі значенням із варіантів — без порожньої опції (інакше «—» дозволив би очистити обовʼязкове). */
  const reqOk = html([sel({ required: true, value: "b" })]);
  assert.equal(blank(reqOk), 0);
  assert.match(reqOk, /<option value="b" selected>B<\/option>/);
  assert.doesNotMatch(reqOk, /<option value="a" selected>/);

  /* Обовʼязковий без значення — з порожньою, і саме вона вибрана (браузер не підсуне «A» мовчки). */
  const reqNone = html([sel({ required: true })]);
  assert.equal(blank(reqNone), 1);
  assert.match(reqNone, /<option value="" selected>—<\/option>/);
  assert.doesNotMatch(reqNone, /<option value="[ab]" selected>/);

  /* Обовʼязковий зі значенням, якого вже нема серед варіантів, — те саме. */
  const reqStale = html([sel({ required: true, value: "gone" })]);
  assert.match(reqStale, /<option value="" selected>—<\/option>/);
  assert.doesNotMatch(reqStale, /<option value="[ab]" selected>/);

  /* Необовʼязковий — порожня опція завжди: вибрана без значення, невибрана зі значенням. */
  const optNone = html([sel({ required: false })]);
  assert.match(optNone, /<option value="" selected>—<\/option>/);
  const optVal = html([sel({ required: false, value: "a" })]);
  assert.equal(blank(optVal), 1);
  assert.match(optVal, /<option value="">—<\/option>/);
  assert.match(optVal, /<option value="a" selected>A<\/option>/);
});

test("панель: режим підключення, помилки полів, результат і зайнятість", () => {
  const e = LIST[0];
  const fields = formFields(e);
  const base = { entry: e, mode: "enable", fields, form: initialForm(fields), busy: false, result: null, errors: {}, spaceName: "Studio" };
  const h = drawerHTML(base);
  assert.doesNotMatch(h, /data-cn-dr="check"/);
  assert.match(h, /data-cn-dr="submit"[^>]*>Підключити</);
  assert.match(drawerHTML({ ...base, errors: { file: "cnFieldRequired" } }), /aria-invalid="true"[\s\S]*Обовʼязкове поле\./);
  assert.match(drawerHTML({ ...base, result: { kind: "failed", key: "cnErrBadSettings", detail: "file: required" } }),
    /Збережено, але перевірка не пройшла\.[\s\S]*Налаштування неповні[\s\S]*file: required/);
  assert.match(drawerHTML({ ...base, result: { kind: "ok", key: "cnCheckOk", detail: "2 tokens" } }), /cn-res--ok[\s\S]*Працює\./);
  /* «refused» — HTTP-відмова: без «Збережено, але…», бо нічого не збережено. */
  const refused = drawerHTML({ ...base, result: { kind: "refused", key: "cnRefRoleTaken", detail: "" } });
  assert.match(refused, /cn-res--err[\s\S]*Роль уже зайнята/);
  assert.doesNotMatch(refused, /Збережено, але/);
  const busy = drawerHTML({ ...base, busy: "save" });
  assert.match(busy, /Зберігаю й перевіряю…/);
  assert.match(busy, /data-cn-field="file"[^>]*disabled/);
  assert.match(busy, /data-cn-dr="submit" disabled/);
  /* Ворожі назва, роль і імʼя простору — текстом, і САМЕ в тих місцях, де вони виводяться (а не лише «нема сирого»). */
  const evil = drawerHTML({ ...base, entry: { ...e, id: "evil-mod", name: "<q>n", roles: ["<q>r"] }, spaceName: "<q>s" });
  assert.doesNotMatch(evil, /<q>/);
  assert.match(evil, /<b id="cn-dr-title">&lt;q&gt;n<\/b>/);
  assert.match(evil, /&lt;q&gt;r · &lt;q&gt;s</);
});

test("панель: без налаштувань — «Налаштувань немає», у панелі є хрестик із підписом", () => {
  const e = LIST[2];
  const h = drawerHTML({ entry: e, mode: "enable", fields: [], form: initialForm([]), busy: false, result: null, errors: {}, spaceName: "S" });
  assert.match(h, /Налаштувань немає\./);
  assert.match(h, /data-cn-dr="close" aria-label="Закрити"/);
  assert.match(h, /id="cn-dr-title"/);
  assert.match(h, /Коментарі команди у вашому проєкті Supabase/, "опис вбудованого в панелі");
});

test("словник: кожен ключ, який віддає модель, є в обох мовах (модель ключів сама не кличе t())", () => {
  const keys = new Set();
  for (const role of ["publish", "comments", "vcs", "dashboard", "tokens"]) for (const k of Object.values(roleKeys(role))) keys.add(k);
  for (const id of ["static-publish", "vercel-publish", "supabase-comments", "css-tokens", "git-sync", "supabase-dashboard"]) {
    const b = builtinText(id);
    keys.add(b.name); keys.add(b.desc);
    for (const k of Object.values(b.fields)) keys.add(k);
  }
  for (const code of ["bad-settings", "module-error", "check-timeout", "secrets-unreadable", "bad-manifest", "bad-folder",
    "no-folder", "not-writable", "no-token", "vercel-auth", "vercel-error", "vercel-busy", "bad-key", "no-schema",
    "supabase-error", "network", "vcs-offline", "vcs-auth", "vcs-bad-target", "vcs-busy", "vcs-error",
    "totally-unknown"]) keys.add(verdictText({ ok: false, error: code }).key);
  keys.add(verdictText({ ok: true }).key);
  for (const code of ["role-taken", "bad-settings", "unknown-module", "unknown-space", "space-json-unreadable", "spaces-off",
    "unwritable", "timeout", "totally-unknown"]) keys.add(refusalView({ code }).key);
  assert.ok(keys.size > 40, `зібрано лише ${keys.size} ключів — обхід зламаний`);
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає ключа «${k}»`);
});

/* ───────── Правки після ревʼю Task 3 ───────── */

test("панель: ключі constructor / toString / __proto__ не ламають розмітку (помилки й підписи — лише власні)", () => {
  /* `d.errors` — звичайний обʼєкт; `errors["constructor"]` без перевірки власності віддав би `Object` (truthy), і `t(err)`
     кинув би на першому ж рендері. Те саме з підписом вбудованого модуля (`fields[f.key]`). */
  const keys = ["constructor", "toString", "__proto__", "hasOwnProperty", "valueOf"];
  const types = ["path", "bool", "select", "secret", "text"];
  const settings = keys.map((key, i) => ({ key, type: types[i], label: `L-${i}`, required: i % 2 === 0,
    ...(types[i] === "select" ? { value: "a", options: [{ value: "a", label: "A" }] } : {}),
    ...(types[i] === "secret" ? { set: true } : {}) }));
  for (const base of [ent(settings), ent(settings, { id: "css-tokens" })]) {
    const clean = drawer(base);
    assert.equal((clean.match(/data-cn-field=/g) || []).length, 5);
    assert.doesNotMatch(clean, /aria-invalid|cn-field-err|function|\[object/, "помилок нема — і «помилки» з прототипа теж");
    for (let i = 0; i < 5; i += 1) assert.match(clean, new RegExp(`L-${i}`), "підпис — з маніфесту, не з прототипа");
    /* Власна властивість — навіть `__proto__` (так її створює `Object.fromEntries` у контролері) — позначає саме своє поле. */
    const own = drawer(base, { errors: JSON.parse('{"__proto__":"cnFieldRequired","constructor":"cnFieldRequired"}') });
    assert.equal((own.match(/aria-invalid="true"/g) || []).length, 2);
    assert.match(fieldTag(own, "__proto__"), /aria-invalid="true"/);
    assert.match(fieldTag(own, "constructor"), /aria-invalid="true"/);
    assert.doesNotMatch(fieldTag(own, "toString"), /aria-invalid/);
  }
  /* Форма без значень цих ключів не падає й дає ПОРОЖНЄ, а не текст функції з прототипа (`value="function Object() …"`). */
  const fields = formFields(ent(settings));
  const empty = drawerHTML({ entry: ent(settings), mode: "enable", fields, form: { values: {}, secrets: {}, erase: [] },
    busy: false, result: null, errors: {}, spaceName: "S" });
  assert.doesNotMatch(empty, /native code|function|\[object/);
  assert.match(fieldTag(empty, "constructor"), /value=""/);
  assert.doesNotMatch(fieldTag(empty, "valueOf"), /value="[^"]/);
});

test("сторінка: ворожі назва, тека й id простору — лише текстом, у заголовку, помилці й блоці агента", () => {
  const sp = { id: '<q>"I', name: '<q>"N', path: '<q>"P', capabilities: { publish: null, comments: null, tokens: null } };
  const pages = [
    connPageHTML(view({ space: sp })),
    connPageHTML(view({ space: sp, list: null })),
    connPageHTML(view({ space: sp, list: null, failed: { code: "space-json-unreadable", message: "x" } })),
    connPageHTML(view({ space: { ...sp, capabilities: { error: "space-json-unreadable" } } })),
  ];
  for (const h of pages) {
    assert.doesNotMatch(h, /<q>/);
    assert.ok(!h.includes('"N') && !h.includes('"P'), "лапка з даних не виходить з атрибута чи тексту");
    assert.match(h, /&lt;q&gt;&quot;N/, "назва простору в заголовку");
    assert.match(h, /&lt;q&gt;&quot;P/, "тека в тексті");
  }
  const page = pages[0];
  /* Блок агента: у запиті — `encodeURIComponent` (він і є екрануванням), у прикладі тіла — `esc`. */
  assert.match(page, /GET \/api\/modules\?space=%3Cq%3E%22I</);
  assert.match(page, /\{space: "&lt;q&gt;&quot;I", id, settings, secrets, replace\}/);
  assert.match(pages[2], /&lt;q&gt;&quot;P[^<]*space\.json/, "у помилці space.json теж");
});

test("панель: ворожі ключ, підпис, значення варіанта й тип — лише текстом, у всіх місцях виводу", () => {
  const e = ent([
    { key: 'k"><q>', type: "path", label: "L<q>", required: false, value: "v" },
    { key: 's"><q>', type: "select", label: "S", required: false, value: 'o"><q>', options: [{ value: 'o"><q>', label: "O<q>" }] },
    { key: 'p"><q>', type: "secret", label: "P<q>", required: false, set: true },
  ]);
  const h = drawer(e);
  assert.doesNotMatch(h, /<q>/);
  assert.match(h, /data-cn-field="k&quot;&gt;&lt;q&gt;"/);
  assert.match(h, /data-cn-field="s&quot;&gt;&lt;q&gt;"/);
  assert.match(h, /<option value="o&quot;&gt;&lt;q&gt;" selected>O&lt;q&gt;<\/option>/);
  assert.match(h, /data-cn-dr="erase" data-key="p&quot;&gt;&lt;q&gt;"/);
  assert.match(h, /data-cn-erase-note="p&quot;&gt;&lt;q&gt;"/);
  assert.match(h, /aria-label="Стерти: P&lt;q&gt;"/);
  assert.match(h, />L&lt;q&gt;</);
  /* Тип у `data-type` — з моделі білий список, але `drawerHTML` приймає й готові поля: екрануємо й його. */
  const raw = drawerHTML({ entry: e, mode: "edit", fields: [{ key: "t", type: 'x"><q>', label: "L", required: false }],
    form: { values: { t: "v" }, secrets: {}, erase: [] }, busy: false, result: null, errors: {}, spaceName: "S" });
  assert.doesNotMatch(raw, /<q>/);
  assert.match(raw, /data-type="x&quot;&gt;&lt;q&gt;"/);
});

test("панель: кожна <label for> має елемент із таким id, id унікальні", () => {
  const e = ent([
    { key: "a", type: "text", label: "A", required: true },
    { key: "b", type: "path", label: "B", required: false },
    { key: "c", type: "select", label: "C", required: false, options: [{ value: "1", label: "1" }] },
    { key: "d", type: "secret", label: "D", required: false, set: true },
    { key: "e", type: "bool", label: "E", required: false, value: false },
  ]);
  const h = drawer(e, { errors: { a: "cnFieldRequired" } });
  const fors = [...h.matchAll(/<label[^>]*\sfor="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(fors.length, 4, "bool огортається в label без for — решта має for");
  for (const x of fors) assert.ok(h.includes(` id="${x}"`), `label for="${x}" без елемента`);
  const ids = [...h.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(new Set(ids).size, ids.length, `дублі id: ${ids}`);
});

test("панель: повідомлення про помилку поля привʼязане до поля — aria-invalid і aria-describedby на кожному типі", () => {
  const e = ent([
    { key: "t", type: "text", label: "T", required: true },
    { key: "s", type: "select", label: "S", required: true, options: [{ value: "1", label: "1" }] },
    { key: "x", type: "secret", label: "X", required: true, set: false },
    { key: "b", type: "bool", label: "B", required: false, value: false },
  ]);
  const errors = { t: "cnFieldRequired", s: "cnFieldRequired", x: "cnFieldRequired", b: "cnFieldRequired" };
  const h = drawer(e, { errors });
  const pIds = [...h.matchAll(/<p class="cn-field-err" id="([^"]+)">Обовʼязкове поле\.<\/p>/g)].map((m) => m[1]);
  assert.equal(pIds.length, 4);
  const used = [];
  for (const key of Object.keys(errors)) {
    const tag = fieldTag(h, key);
    assert.match(tag, /aria-invalid="true"/, key);
    const mine = tokens(tag, "aria-describedby").filter((id) => pIds.includes(id));
    assert.equal(mine.length, 1, `поле «${key}» не посилається на своє повідомлення: ${tag}`);
    used.push(...mine);
  }
  assert.equal(new Set(used).size, 4, "кожне повідомлення — рівно одне поле");
  /* Без помилки — ні aria-invalid, ні посилання на неіснуюче повідомлення. */
  const ok = drawer(e);
  assert.doesNotMatch(ok, /aria-invalid|cn-field-err/);
  assert.doesNotMatch(fieldTag(ok, "t"), /aria-describedby/);
});

test("панель: aria-required на обовʼязкових полях, текстових, списках і секретах — і лише на них", () => {
  const e = ent([
    { key: "t", type: "text", label: "T", required: true },
    { key: "p", type: "path", label: "P", required: true },
    { key: "s", type: "select", label: "S", required: true, value: "1", options: [{ value: "1", label: "1" }] },
    { key: "x", type: "secret", label: "X", required: true, set: false },
    { key: "b", type: "bool", label: "B", required: true, value: false },
    { key: "t2", type: "text", label: "T2", required: false },
    { key: "s2", type: "select", label: "S2", required: false, options: [{ value: "1", label: "1" }] },
    { key: "x2", type: "secret", label: "X2", required: false, set: false },
  ]);
  const h = drawer(e);
  for (const k of ["t", "p", "s", "x"]) assert.match(fieldTag(h, k), /aria-required="true"/, `обовʼязкове «${k}»`);
  for (const k of ["b", "t2", "s2", "x2"]) assert.doesNotMatch(fieldTag(h, k), /aria-required/, `необовʼязкове «${k}»`);
});

test("панель: підказка шляху, стан секрету й примітка стирання привʼязані до поля через aria-describedby", () => {
  const e = ent([
    { key: "folder", type: "path", label: "F", required: true, value: "x" },
    { key: "pw", type: "secret", label: "P", required: false, set: true },
    { key: "plain", type: "text", label: "Q", required: false, value: "" },
  ]);
  const idOf = (h, re) => re.exec(h)?.[1];
  for (const erase of [[], ["pw"]]) {
    const h = drawer(e, { form: { ...initialForm(formFields(e)), erase }, errors: { folder: "cnFieldRequired", pw: "cnFieldRequired" } });
    const hint = idOf(h, /<p class="cn-hint" id="([^"]+)">\{home\}/);
    const state = idOf(h, /<p class="cn-secret" id="([^"]+)">/);
    const note = idOf(h, /<p class="cn-hint" id="([^"]+)" data-cn-erase-note="pw"/);
    const errF = idOf(h, /<p class="cn-field-err" id="([^"]+)"/);
    assert.ok(hint && state && note && errF, "усі четверо мають id");
    assert.equal(new Set([hint, state, note, errF]).size, 4);
    const f = tokens(fieldTag(h, "folder"), "aria-describedby");
    assert.deepEqual(f.filter((x) => x === hint || x === errF), [hint, errF], "підказка шляху, далі помилка");
    assert.match(attr(fieldTag(h, "folder"), "aria-describedby"), /^\S+ \S+$/, "кілька id — через пробіл");
    const s = tokens(fieldTag(h, "pw"), "aria-describedby");
    assert.ok(s.includes(state), "стан секрету описує поле");
    assert.equal(s.includes(note), erase.length > 0,
      "примітку про стирання посилання охоплює лише коли вона видима: `hidden`-елемент, на який вказує describedby, усе одно озвучується");
    assert.equal(s.length, erase.length ? 3 : 2);
    assert.equal(tokens(fieldTag(h, "plain"), "aria-describedby").length, 0, "звичайне поле — без описів");
  }
});

test("панель: «Збережено, але…» із загальним кодом не повторює «Перевірка не пройшла» — голова й деталь; інші види лишають текст ключа", () => {
  const e = ent([]);
  const res = (r) => drawer(e, { result: r });
  const failed = res({ kind: "failed", key: "cnErrGeneric", detail: "memo-says-no — note is fail" });
  assert.match(failed, /<b>Збережено, але перевірка не пройшла\.<\/b>[\s\S]*memo-says-no — note is fail/);
  assert.doesNotMatch(failed, /Перевірка не пройшла\./, "ключ cnErrGeneric тут — повтор голови");
  /* Без деталі лишається одна голова. */
  assert.doesNotMatch(res({ kind: "failed", key: "cnErrGeneric", detail: "" }), /Перевірка не пройшла\./);
  /* Конкретний код — свій текст (він не повтор). */
  assert.match(res({ kind: "failed", key: "cnErrBadSettings", detail: "" }), /Налаштування неповні/);
  /* Інші види: кнопка «Перевірити» в панелі й HTTP-відмова — без голови, тож текст ключа потрібен. */
  assert.match(res({ kind: "check-failed", key: "cnErrGeneric", detail: "x" }), /Перевірка не пройшла\./);
  assert.match(res({ kind: "refused", key: "cnErrGeneric", detail: "x" }), /Перевірка не пройшла\./);
  /* Англійською так само. */
  setLang("en");
  const en = res({ kind: "failed", key: "cnErrGeneric", detail: "d" });
  assert.doesNotMatch(en, new RegExp(DICT.en.cnErrGeneric.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  assert.match(en, /<b>Saved, but the check failed\.<\/b>/);
});

test("панель: результат — role=status для успіху і role=alert для кожної відмови", () => {
  const e = ent([]);
  const res = (r) => drawer(e, { result: r });
  assert.match(res({ kind: "ok", key: "cnCheckOk", detail: "" }), /<div class="cn-res cn-res--ok" role="status">/);
  for (const kind of ["failed", "check-failed", "refused"]) {
    const h = res({ kind, key: "cnErrGeneric", detail: "" });
    assert.match(h, /<div class="cn-res cn-res--err" role="alert">/, kind);
    assert.doesNotMatch(h, /role="status"/, kind);
  }
  assert.doesNotMatch(res(null), /cn-res/);
});

test("картка: у спокої «Перевірити» без блокування, в польоті — «Перевіряю…», інша дія підпису не міняє", () => {
  const idle = cardHTML(LIST[1], new Map());
  assert.equal(btnText(idle, "check"), "Перевірити");
  assert.equal(btnText(idle, "configure"), "Налаштувати");
  assert.equal(btnText(idle, "disable"), "Вимкнути");
  assert.doesNotMatch(idle, /disabled/);
  const checking = cardHTML(LIST[1], new Map([["static-publish", "check"]]));
  assert.equal(btnText(checking, "check"), "Перевіряю…");
  assert.equal((checking.match(/<button[^>]*disabled/g) || []).length, 3, "усі три кнопки вимкнені");
  const disabling = cardHTML(LIST[1], new Map([["static-publish", "disable"]]));
  assert.equal(btnText(disabling, "check"), "Перевірити", "підпис «Перевіряю…» — лише для перевірки");
  assert.equal((disabling.match(/<button[^>]*disabled/g) || []).length, 3);
  /* Дія в польоті в ІНШОЇ картки цю не чіпає. */
  assert.doesNotMatch(cardHTML(LIST[1], new Map([["vercel-publish", "check"]])), /disabled/);
});

test("панель: busy — 'save' чи 'check': усе вимкнено; «Зберігаю й перевіряю…» лише для 'save', «Перевіряю…» лише для 'check'", () => {
  const e = ent([
    { key: "a", type: "text", label: "A", required: false },
    { key: "s", type: "select", label: "S", required: false, options: [{ value: "1", label: "1" }] },
    { key: "p", type: "secret", label: "P", required: false, set: true },
    { key: "b", type: "bool", label: "B", required: false, value: false },
  ]);
  const controls = (h) => [...h.matchAll(/<(?:input|select|button)\b[^>]*\bdata-cn-(?:field|dr="(?:erase|check|submit)")[^>]*>/g)].map((m) => m[0]);
  const idle = drawer(e);
  assert.ok(controls(idle).length >= 7, "поля, «Стерти», «Перевірити», головна");
  for (const c of controls(idle)) assert.doesNotMatch(c, /disabled/, c);
  assert.equal(btnText(idle.replace(/data-cn-dr=/g, "data-cn="), "submit"), "Зберегти");
  const txt = (h, act) => btnText(h.replace(/data-cn-dr=/g, "data-cn="), act);

  const save = drawer(e, { busy: "save" });
  for (const c of controls(save)) assert.match(c, /disabled/, c);
  assert.equal(txt(save, "submit"), "Зберігаю й перевіряю…");
  assert.equal(txt(save, "check"), "Перевірити", "на «Перевірити» під час запису — звичайний підпис");

  const check = drawer(e, { busy: "check" });
  for (const c of controls(check)) assert.match(c, /disabled/, c);
  assert.equal(txt(check, "check"), "Перевіряю…");
  assert.equal(txt(check, "submit"), "Зберегти", "головна під час перевірки не каже «Зберігаю»");
  assert.doesNotMatch(check, /Зберігаю й перевіряю/);
  const enable = drawer(e, { busy: "check", mode: "enable" });
  assert.equal(txt(enable, "submit"), "Підключити");
  /* EN — ті самі стани. */
  setLang("en");
  assert.equal(txt(drawer(e, { busy: "save" }), "submit"), "Saving and checking…");
  assert.equal(txt(drawer(e, { busy: "check" }), "check"), "Checking…");
});

test("картка: вимкнений модуль зі status: error причини не показує", () => {
  const h = cardHTML({ ...LIST[3], enabled: false, status: "error", error: "no-token",
    last_check: { ok: false, error: "no-token", detail: "Токен Vercel не задано" } }, new Map());
  assert.doesNotMatch(h, /cn-why|Токен Vercel не задано/);
  assert.match(h, /cn-badge--off/);
  assert.match(h, /data-cn="enable"/);
});

test("сторінка: текст помилки списку обрізається до 300 символів ДО екранування", () => {
  const detail = (message) => /<span class="cn-why-detail">([^<]*)<\/span>/.exec(
    connPageHTML(view({ list: null, failed: { code: null, message } })))?.[1];
  assert.equal(detail("x".repeat(500)).length, 300);
  assert.equal(detail("y".repeat(300)).length, 300, "рівно 300 — без обрізання");
  assert.equal(detail("z".repeat(40)), "z".repeat(40));
  /* Обрізається сирий текст, а не вже екранований: 300 символів `&` → 300 × `&amp;`, а не 60. */
  assert.equal(detail("&".repeat(500)), "&amp;".repeat(300));
});

test("англійською: вбудованої інтеграції ЛІГА в рядку «Зараз» нема (4d-4c)", () => {
  setLang("en");
  const liga = { ...SP, capabilities: { publish: "static-publish", comments: "supabase-comments", tokens: null }, compat: { publish: "design-canvas" } };
  const h = connPageHTML(view({ space: liga }));
  assert.doesNotMatch(h, /built-in LIGA integration/);
  assert.doesNotMatch(h, /ЛІГА/);
});

test("слова: ключі стирання й нові підписи — в обох мовах, застарілий «Не стирати» прибрано", () => {
  assert.equal(DICT.uk.cnEraseFor("Пароль"), "Стерти: Пароль");
  assert.equal(DICT.en.cnEraseFor("Password"), "Erase: Password");
  assert.equal(DICT.uk.cnEraseUndo, undefined);
  assert.equal(DICT.en.cnEraseUndo, undefined);
  assert.equal(DICT.uk.cnNowNobody, "Зараз: нікого", "живий тест спирається на цей рядок");
  assert.equal(DICT.uk.cnNonePublish, "кнопки публікації в смузі нема", "і на цей");
  assert.equal(DICT.en.cnNowNobody, "Now: none");
  assert.equal(DICT.en.cnNowNone("x"), "Now: none — x");
  assert.equal(DICT.en.cnDisableNone("publish", "x"), "After this, the “publish” role has no module: x.");
  assert.equal(DICT.uk.cnDisableLegacy, undefined);
  assert.equal(DICT.en.cnNowLegacy, undefined);
  assert.equal(DICT.en.cnReplaceAsk("R", "H", "N"),
    "R is currently handled by “H”. Connect “N” instead? “H” will be turned off; its settings stay.");
  assert.equal(DICT.uk.cnLoading, "Завантажую модулі…");
  assert.equal(DICT.uk.cnEraseMarked, "буде стерто після збереження");
  assert.equal(DICT.uk.cnCheckSavedFirst, "Спершу збережіть зміни — перевіряється збережене.");
  assert.equal(DICT.uk.cnRefRoleTaken, "Роль уже зайнята іншим модулем — оновіть сторінку й спробуйте ще раз.");
  assert.equal(DICT.uk.cnErrBadKey, "Ключ Supabase не підходить або не заданий.");
  assert.equal(DICT.uk.cnLead,
    "Модулі цього простору: куди публікувати превʼю, де зберігати коментарі команди, звідки брати токени. Без жодного модуля канвас працює.");
});

test("поле з префіксом майстра: id і похідні id (-state, -err) з префіксом; типово — cn-f", () => {
  const e = { id: "memo", settings: [] };
  const f = { key: "token", type: "secret", label: "Token", required: false, set: true };
  const h = fieldHTML(e, f, 2, { errors: { token: "cnFieldRequired" }, form: { values: {}, erase: [] }, busy: false }, "wz-f-1");
  assert.match(h, /id="wz-f-1-2"/);
  assert.match(h, /id="wz-f-1-2-state"/);
  assert.match(h, /id="wz-f-1-2-err"/);
  assert.doesNotMatch(h, /cn-f-/);
  assert.match(fieldHTML(e, f, 0, { errors: {}, form: { values: {}, erase: [] }, busy: false }), /id="cn-f-0"/);
});

/* ── картка git-sync (етап 4a, Task 7) ───────────────────────────────────────────────────────────── */

const GIT = { id: "git-sync", name: "Синхронізація з git", roles: ["vcs"], enabled: true, implicit: false, status: "unchecked",
  settings: [
    { key: "repo", type: "text", label: "Репозиторій (типовий для задач простору)", required: false, value: "git@github.com:o/r.git" },
    { key: "branch", type: "text", label: "Гілка", required: false, value: "main" },
    { key: "path", type: "text", label: "Тека в репозиторії", required: false, value: "mockup/{task}" },
    { key: "ssh_key", type: "text", label: "SSH-ключ (необовʼязково)", required: false },
    { key: "host_ip", type: "text", label: "IP сервера (необовʼязково)", required: false },
    { key: "autosync", type: "bool", label: "Відправляти після кожної відповіді агента", required: false, value: false },
  ] };

test("сторінка: секція «Синхронізація з git» стоїть після коментарів, з карткою git-sync і рядком «Зараз»", () => {
  const sp = { ...SP, capabilities: { publish: "static-publish", comments: null, vcs: "git-sync", tokens: null } };
  const h = connPageHTML(view({ space: sp, list: [...LIST, GIT] }));
  assert.match(h, /<h2 class="cn-sec-h"[^>]*>Синхронізація з git<\/h2>/);
  assert.match(h, /Відправляти ітерації в git-репозиторій і отримувати правки колег\./);
  assert.ok(h.indexOf("Командні коментарі") < h.indexOf("Синхронізація з git") && h.indexOf("Синхронізація з git") < h.indexOf("Токени дизайн-системи"),
    "порядок секцій: публікація, коментарі, git, токени");
  assert.match(h, /<div class="cn-card" data-id="git-sync">/);
  assert.match(h, /Будь-який git-репозиторій — GitHub, GitLab чи свій сервер\./);
  assert.match(h, /Зараз: Git/);
});

test("панель git-sync: підписи шести полів — зі словника (обома мовами), а не сирий label маніфесту", () => {
  const h = drawer(GIT);
  for (const k of ["repo", "branch", "path", "ssh_key", "host_ip", "autosync"]) assert.ok(fieldTag(h, k), `поле ${k}`);
  assert.match(h, /Репозиторій \(типовий для задач\)/);
  assert.match(h, /Тека в репозиторії \(\{task\} — id задачі\)/);
  assert.match(h, /IP сервера, коли DNS у VPN не відповідає \(необовʼязково\)/);
  setLang("en");
  const en = drawer(GIT);
  assert.match(en, /Repository \(default for tasks\)/);
  assert.match(en, /Send after every agent reply/);
  assert.doesNotMatch(en, /[а-яіїєґ]/i, "англійська панель git-sync без кирилиці (мова автора модуля сюди не просочується)");
});

test("вердикт «isolated» (4d-3b): перевірку спільного стану в ізольованому прогоні не виконано — свій текст UK/EN, не «Модуль упав»", () => {
  assert.deepEqual(verdictText({ ok: false, error: "isolated", detail: "x" }), { key: "cnErrIsolated", detail: "x" });
  assert.equal(refusalView({ code: "isolated" }).key, "cnErrIsolated");
  for (const lang of ["uk", "en"]) assert.ok(typeof DICT[lang].cnErrIsolated === "string" && DICT[lang].cnErrIsolated, lang);
});
