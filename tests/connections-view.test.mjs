import assert from "node:assert/strict";
import test from "node:test";

import { DICT, setLang } from "../app/i18n.js";
import { cardHTML, connPageHTML, drawerHTML, modName, nowHTML, roleTitle } from "../app/connections-view.js";
import {
  builtinText, formFields, initialForm, refusalView, roleKeys, verdictText,
} from "../app/connections-model.js";

const SP = { id: "studio", name: "Studio", path: "/u/work/studio", integrations: false,
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

test("сторінка: legacy, missing-секція, завантаження, помилка списку й нечитабельний space.json", () => {
  const liga = { ...SP, integrations: true, capabilities: { publish: "legacy", comments: "legacy", tokens: null } };
  const missing = { id: "gone", name: "gone", roles: [], enabled: true, status: "missing", settings: [] };
  const h = connPageHTML(view({ space: liga, list: [...LIST, missing] }));
  assert.match(h, /вбудована інтеграція ЛІГА/);
  assert.match(h, /Не встановлені на цьому компʼютері/);
  assert.match(h, /data-cn="disable" data-id="gone"/);
  assert.match(connPageHTML(view({ list: null })), /Вантажу модулі…/);
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

test("рядок «Зараз»: модуль, модуль без запису, legacy, нікого, space.json не читається, невідома роль", () => {
  const v = (caps) => ({ space: { ...SP, capabilities: caps }, list: LIST });
  assert.match(nowHTML("publish", v({ publish: "static-publish" })), /Зараз: Публікація в теку/);
  assert.match(nowHTML("publish", v({ publish: "ghost-id" })), /Зараз: ghost-id/, "нема в списку — показуємо id, а не падаємо");
  assert.match(nowHTML("publish", v({ publish: "legacy" })), /вбудована інтеграція ЛІГА/);
  assert.match(nowHTML("comments", v({ comments: null })), /Зараз: нікого — коментарі лише локальні/);
  assert.match(nowHTML("vcs", v({ vcs: null })), /Зараз: нікого$|Зараз: нікого</, "роль без власного тексту — просто «нікого»");
  assert.match(nowHTML("publish", v({ error: "space-json-unreadable" })), /Зараз: невідомо — space\.json не читається/);
  assert.equal(nowHTML("vcs", v({ publish: "static-publish" })), "", "роль, якої capabilities не знає, — без рядка");
  setLang("en");
  assert.match(nowHTML("publish", v({ error: "x" })), /Now: unknown — space\.json cannot be read/);
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
  assert.equal(roleTitle("vcs"), "vcs");
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
  /* Без позначки: кнопка «Стерти», підказка про стирання схована. */
  assert.match(typed, /data-cn-dr="erase" data-key="pw" aria-pressed="false"[^>]*>Стерти</);
  assert.match(typed, /data-cn-erase-note="pw" hidden/);
  /* З позначкою: «Не стирати», підказка видима. */
  const marked = drawerHTML({ ...base, form: { values: {}, secrets: {}, erase: ["pw"] } });
  assert.match(marked, /data-cn-dr="erase" data-key="pw" aria-pressed="true"[^>]*>Не стирати</);
  assert.match(marked, /data-cn-erase-note="pw">буде стерто при збереженні</);
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
  const busy = drawerHTML({ ...base, busy: true });
  assert.match(busy, /Зберігаю й перевіряю…/);
  assert.match(busy, /data-cn-field="file"[^>]*disabled/);
  assert.match(busy, /data-cn-dr="submit" disabled/);
  const evil = drawerHTML({ ...base, entry: { ...e, name: "<b>", id: "<i>" }, spaceName: "<s>" });
  assert.doesNotMatch(evil, /<b>|<i>|<s>/);
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
  for (const role of ["publish", "comments", "tokens"]) for (const k of Object.values(roleKeys(role))) keys.add(k);
  for (const id of ["static-publish", "vercel-publish", "supabase-comments", "css-tokens"]) {
    const b = builtinText(id);
    keys.add(b.name); keys.add(b.desc);
    for (const k of Object.values(b.fields)) keys.add(k);
  }
  for (const code of ["bad-settings", "module-error", "check-timeout", "secrets-unreadable", "bad-manifest", "bad-folder",
    "no-folder", "not-writable", "no-token", "vercel-auth", "vercel-error", "vercel-busy", "bad-key", "no-schema",
    "supabase-error", "network", "totally-unknown"]) keys.add(verdictText({ ok: false, error: code }).key);
  keys.add(verdictText({ ok: true }).key);
  for (const code of ["role-taken", "bad-settings", "unknown-module", "unknown-space", "space-json-unreadable", "spaces-off",
    "unwritable", "timeout", "totally-unknown"]) keys.add(refusalView({ code }).key);
  assert.ok(keys.size > 40, `зібрано лише ${keys.size} ключів — обхід зламаний`);
  for (const k of keys) for (const lang of ["uk", "en"]) assert.ok(DICT[lang][k] !== undefined, `${lang}: немає ключа «${k}»`);
});
