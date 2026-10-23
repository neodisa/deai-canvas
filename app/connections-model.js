/**
 * Модель екрана «Підключення» (Deai 0.5.0, етап 3a; спека
 * `docs/superpowers/specs/2026-10-20-connections-screen-design.md`). Чисті функції: ні DOM, ні fetch, ні `t()` —
 * лише ІМЕНА ключів словника (як `bar-model.js`), тож модуль тестується в node без браузера й без мови.
 *
 * Вхід — записи `GET /api/modules` (`{id, name, roles, enabled, implicit, status, settings[], last_check?, error?}`)
 * і `capabilities` простору з `/api/spaces` (`{publish, comments, tokens[, error]}`).
 * Свої модулі простору (3c) мають у записі ще `custom: true`, `trust` (`untrusted|trusted|changed|refused`), `record`,
 * `runs` (чи виконується тут їхній код), `source`, `trust_error?`; `GET /api/modules` може нести `notes` (`[{folder, code}]`).
 *
 * ⛔ Ключі з даних (роль, id модуля, ключ налаштування) НІКОЛИ не індексують звичайний обʼєкт без перевірки власної
 * властивості: роль `__proto__` чи `constructor` інакше дістала б щось із прототипу. Тому `has()` скрізь, а мапи
 * значень будуються `Object.fromEntries` (власна властивість `__proto__` — просто поле, а не прототип).
 */

const has = (o, k) => o != null && typeof k === "string" && Object.prototype.hasOwnProperty.call(o, k);
const get = (o, k) => (has(o, k) ? o[k] : undefined);

/** Ролі зі своїми текстами — у порядку секцій. Інші ролі йдуть далі за абеткою, модулі без ролі — останніми. */
export const ROLE_ORDER = ["publish", "comments", "tokens"];

const ROLE_KEYS = {
  publish: { title: "cnRolePublish", lead: "cnRolePublishLead", none: "cnNonePublish" },
  comments: { title: "cnRoleComments", lead: "cnRoleCommentsLead", none: "cnNoneComments" },
  tokens: { title: "cnRoleTokens", lead: "cnRoleTokensLead", none: "cnNoneTokens" },
};
/** Ключі словника ролі (`title`, `lead`, `none`) або `null` для ролі без своїх текстів. */
export const roleKeys = (role) => get(ROLE_KEYS, role) ?? null;

const ROLE_ICONS = { publish: "up", comments: "comment", tokens: "sliders" };
/** Іконка ролі (імʼя з `icons.js`); невідома роль — `dots`. */
export const roleIcon = (role) => get(ROLE_ICONS, role) ?? "dots";

/* Вбудовані модулі: назва, опис і підписи полів — зі словника (обидві мови). Маніфести не змінюються: їхні `name` і
   `label` — мова автора модуля, і для модулів поза цією таблицею екран показує саме їх. */
const BUILTIN_TEXT = {
  "static-publish": { name: "cnModStaticName", desc: "cnModStaticDesc",
    fields: { folder: "cnFieldStaticFolder", password: "cnFieldPreviewPassword" } },
  "vercel-publish": { name: "cnModVercelName", desc: "cnModVercelDesc",
    fields: { token: "cnFieldVercelToken", team: "cnFieldVercelTeam", password: "cnFieldPreviewPassword" } },
  "supabase-comments": { name: "cnModSupabaseName", desc: "cnModSupabaseDesc",
    fields: { url: "cnFieldSupabaseUrl", key: "cnFieldSupabaseKey" } },
  "css-tokens": { name: "cnModCssName", desc: "cnModCssDesc", fields: { file: "cnFieldCssFile" } },
};
/** Ключі словника вбудованого модуля (`name`, `desc`, `fields{ключ: ключ словника}`) або `null`. */
export const builtinText = (id) => get(BUILTIN_TEXT, id) ?? null;

/* ── свої модулі простору (етап 3c) ───────────────────────────────────────────────────────────────── */

/** Свій модуль простору: запис `GET /api/modules` з `custom: true` (вбудовані цього поля не мають). */
export const isOwn = (e) => e?.custom === true;
/** Код свого модуля виконується тут (робочий довірений знімок): `runs: true`. Недовірений і `refused` без знімка — ні. */
export const ownRuns = (e) => isOwn(e) && e.runs === true;

const TRUST_WHY = new Map([
  ["symlink", "trWhySymlink"], ["hardlink", "trWhyHardlink"], ["special-file", "trWhySpecial"],
  ["too-many-files", "trWhyTooMany"], ["too-big", "trWhyTooBig"], ["too-deep", "trWhyTooDeep"],
  ["bad-name", "trWhyBadName"], ["unreadable", "trWhyUnreadable"], ["unstable", "trWhyUnstable"],
  ["bad-manifest", "trWhyBadManifest"], ["snapshot-damaged", "trWhyDamaged"], ["trust-unreadable", "trWhyTrustFile"],
]);
/** Ключ словника причини `refused`/`untrusted` (код сервера `trust_error`, `refused.code`); невідомий — `trWhyOther`. */
export const trustWhyKey = (code) => TRUST_WHY.get(code) ?? "trWhyOther";

/**
 * Рядок довіри під описом картки свого модуля: `{key, why}` (`why` — ключ причини для шаблону або `null`) чи `null`.
 * `changed` — у теці є нова версія; `refused` зі знімком — нова версія не годиться, працює попередня; недовірений з
 * пошкодженим знімком — довіритись знову; файл довіри не читається — сказати це. `refused` без знімка — не тут: його
 * причина — у `whyOf` (картка без робочого коду).
 */
export function trustLine(e) {
  if (!isOwn(e)) return null;
  if (e.trust === "changed") return { key: "cnTrustChanged", why: null };
  if (e.trust === "refused" && ownRuns(e)) return { key: "cnTrustRefusedNew", why: trustWhyKey(e.trust_error) };
  if (e.trust_error === "snapshot-damaged") return { key: "cnTrustDamaged", why: null };
  if (e.trust_error === "trust-unreadable") return { key: "cnRefTrustUnreadable", why: null };
  return null;
}

const NOTE_KEYS = new Map([
  ["id-taken", "cnNoteIdTaken"], ["too-many-modules", "cnNoteTooMany"], ["modules-link", "cnNoteLink"],
  ["modules-unreadable", "cnNoteUnreadable"],
]);
/** Примітки `GET /api/modules` (`[{folder, code}]`) → `[{key, folder}]`; невідомий код — `cnNoteOther`, сміття — геть. */
export function noteView(notes) {
  return (Array.isArray(notes) ? notes : [])
    .filter((n) => n && typeof n.folder === "string" && typeof n.code === "string")
    .map((n) => ({ key: NOTE_KEYS.get(n.code) ?? "cnNoteOther", folder: n.folder }));
}

/**
 * Секції сторінки: `{sections: [{role, modules}], missing}`. Модуль стоїть у секції ПЕРШОЇ ролі (кілька ролей
 * перелічує картка); `status: missing` — окремо. Порядок усередині секції — як у списку сервера (за абеткою id).
 */
export function groupModules(list) {
  const byRole = new Map();
  const missing = [];
  for (const e of Array.isArray(list) ? list : []) {
    if (!e || typeof e !== "object" || typeof e.id !== "string") continue;
    if (e.status === "missing") { missing.push(e); continue; }
    const first = Array.isArray(e.roles) && typeof e.roles[0] === "string" ? e.roles[0] : "";
    if (!byRole.has(first)) byRole.set(first, []);
    byRole.get(first).push(e);
  }
  const named = [...byRole.keys()].filter((r) => r && !ROLE_ORDER.includes(r)).sort();
  const order = [...ROLE_ORDER.filter((r) => byRole.has(r)), ...named, ...(byRole.has("") ? [""] : [])];
  return { sections: order.map((role) => ({ role, modules: byRole.get(role) })), missing };
}

/**
 * Рядок «Зараз» ролі з `capabilities` простору: `{kind: 'module', id, entry|null}`, `{kind: 'legacy'}`,
 * `{kind: 'waiting', id, entry}`, `{kind: 'none', noneKey}`, `{kind: 'error'}`; `null` — роль, якої `capabilities` не
 * знає (нема що казати).
 *
 * ⛔ `capabilities.error` (space.json не читається) — окремий стан і перевіряється РАНІШЕ за читання ролі: тоді решта
 * `capabilities` нічого не варта (стара чи порожня), і показувати з неї «Зараз працює …» було б неправдою.
 */
export function providerLine(role, caps, list) {
  if (!caps || typeof caps !== "object") return null;
  if (get(caps, "error")) return { kind: "error" };
  if (role === "error" || !has(caps, role)) return null;
  const v = caps[role];
  if (v === "legacy") return { kind: "legacy" };
  if (typeof v !== "string" || !v) {
    /* Роль «на папері» за увімкненим своїм модулем, що тут не працює (3c): сервер віддає `null` без `error`
       (поправка 11), але це не «нікого» — роль чекає довіри. */
    const waiting = (Array.isArray(list) ? list : []).find((x) => x && x.enabled === true && isOwn(x) && !ownRuns(x)
      && Array.isArray(x.roles) && x.roles.includes(role));
    if (waiting) return { kind: "waiting", id: waiting.id, entry: waiting };
    return { kind: "none", noneKey: roleKeys(role)?.none ?? null };
  }
  const entry = (Array.isArray(list) ? list : []).find((x) => x && x.id === v) ?? null;
  return { kind: "module", id: v, entry };
}

/**
 * Картка: бейдж (`missing|off|ok|unchecked|error|untrusted`), дії (`enable|configure|check|disable|trust|trustinfo`), чи
 * показувати причину. Вбудований — рівно як до 3c. Свій модуль без робочого коду: недовірений — «Потрібна довіра» і
 * «Довіритись…», `refused` без знімка — «Помилка» і «Чому не можна…» (+ «Вимкнути», коли ввімкнений). Свій зі знімком —
 * як вбудований, плюс «Довіритись…» для `changed` і «Чому не можна…» для `refused` (нова версія не годиться).
 */
export function cardView(e) {
  if (e?.status === "missing") return { badge: "missing", actions: ["disable"], why: true, implicit: false };
  if (isOwn(e) && !ownRuns(e)) {
    const off = e.enabled === true ? ["disable"] : [];
    if (e.trust === "refused") return { badge: "error", actions: ["trustinfo", ...off], why: true, implicit: false };
    return { badge: "untrusted", actions: ["trust", ...off], why: e.enabled === true, implicit: false };
  }
  let v;
  if (!e?.enabled) v = { badge: "off", actions: ["enable"], why: false, implicit: false };
  else {
    const badge = e.status === "ok" ? "ok" : e.status === "error" ? "error" : "unchecked";
    v = { badge, actions: ["configure", "check", "disable"], why: badge === "error", implicit: e.implicit === true };
  }
  if (isOwn(e) && e.trust === "changed") v.actions.push("trust");
  else if (isOwn(e) && e.trust === "refused") v.actions.push("trustinfo");
  return v;
}

/** Найдовша деталь у розмітці: текст модуля чи сервера може бути будь-якої довжини. */
export const DETAIL_MAX = 300;
const clip = (s) => (typeof s === "string" && s ? (s.length > DETAIL_MAX ? `${s.slice(0, DETAIL_MAX - 1)}…` : s) : "");

const CHECK_KEYS = new Map([
  ["bad-settings", "cnErrBadSettings"], ["module-error", "cnErrModuleError"], ["check-timeout", "cnErrTimeout"],
  ["secrets-unreadable", "cnErrSecretsUnreadable"], ["bad-manifest", "cnErrBadManifest"],
  ["bad-folder", "cnErrBadFolder"], ["no-folder", "cnErrBadFolder"], ["not-writable", "cnErrNotWritable"],
  ["no-token", "cnErrNoToken"], ["vercel-auth", "cnErrVercelAuth"], ["vercel-error", "cnErrVercelError"],
  ["vercel-busy", "cnErrVercelBusy"],
  ["bad-key", "cnErrBadKey"], ["no-schema", "cnErrNoSchema"], ["supabase-error", "cnErrSupabaseError"],
  ["network", "cnErrNetwork"],
]);

/**
 * Вердикт перевірки (`{ok, error?, detail?}`) → `{key, detail}`. Невідомий код і вільний текст модуля
 * (`css-tokens`: «file: not found») — загальний текст, а сам текст іде деталлю: інакше людина не дізналась би причини.
 */
export function verdictText(v) {
  if (!v || typeof v !== "object") return { key: "cnErrGeneric", detail: "" };
  if (v.ok === true) return { key: "cnCheckOk", detail: clip(v.detail) };
  const code = typeof v.error === "string" ? v.error : "";
  const key = CHECK_KEYS.get(code);
  if (key) return { key, detail: clip(v.detail) };
  const detail = [code, typeof v.detail === "string" ? v.detail : ""].filter(Boolean).join(" — ");
  return { key: "cnErrGeneric", detail: clip(detail) };
}

/**
 * Причина на картці: `missing` — свій текст; `error` — текст коду і деталь ЛИШЕ з того `last_check`, що й дав цю
 * помилку (стара успішна перевірка не пояснює `secrets-unreadable`); інакше `null`.
 */
export function whyOf(e) {
  if (!e) return null;
  if (e.status === "missing") return { key: "cnWhyMissing", detail: "" };
  if (isOwn(e) && !ownRuns(e)) {
    /* Свій без робочого коду: `refused` — причина й деталь сервера; недовірений — лише коли ввімкнений (роль не працює). */
    if (e.trust === "refused") return { key: trustWhyKey(e.trust_error), detail: clip(e.error) };
    return e.enabled === true ? { key: "cnTrustNeededWhy", detail: "" } : null;
  }
  if (e.status !== "error") return null;
  const lc = e.last_check;
  /* Перевірка, що повернула `ok:false` БЕЗ `error`, лишає на сервері `error: 'check failed'` — її деталь теж ТА САМА. */
  const detail = lc && lc.ok === false && (lc.error ?? "check failed") === e.error ? lc.detail : undefined;
  return verdictText({ ok: false, error: e.error, detail });
}

const REFUSAL_KEYS = new Map([
  ["role-taken", "cnRefRoleTaken"], ["bad-settings", "cnRefBadSettings"], ["unknown-module", "cnRefUnknownModule"],
  ["unknown-space", "cnRefUnknownSpace"], ["space-json-unreadable", "cnRefSpaceJson"], ["spaces-off", "cnRefSpacesOff"],
  ["unwritable", "cnRefUnwritable"],
  ["module-untrusted", "cnRefUntrusted"], ["module-changed", "cnRefChanged"], ["module-refused", "cnRefRefused"],
  ["trust-needs-ui", "cnRefNeedsUi"], ["trust-declined", "cnRefDeclined"], ["trust-no-confirm", "cnRefNoConfirm"],
  ["trust-busy", "cnRefBusy"], ["trust-unreadable", "cnRefTrustUnreadable"],
]);

/**
 * Відмова HTTP (`api()` кидає `Error` з `code`): `{key, detail}`; `timeout` (`formApi`) — свій `cnTimeout`
 * (не `formTimeout`: той каже «простір чи задача»).
 * Власний ключ відмови стоїть РАНІШЕ за ключ перевірки (`bad-settings` — і те, і те: у формі це «відмова», а не
 * «перевірка»); коди перевірки на запасі, бо сервер віддає їх і відмовою (409 `secrets-unreadable` від запису секретів).
 */
export function refusalView(err) {
  const code = typeof err?.code === "string" ? err.code : "";
  if (code === "timeout") return { key: "cnTimeout", detail: "" };
  return { key: REFUSAL_KEYS.get(code) ?? CHECK_KEYS.get(code) ?? "cnRefGeneric", detail: clip(typeof err?.message === "string" ? err.message : "") };
}

/**
 * Хто, КРІМ `e`, зараз тримає хоч одну з його ролей: увімкнені (зокрема неявно) і не `missing`.
 *
 * Модуль зі `status: error` теж рахується: він увімкнений і роль за ним — а чи працює він, не наше діло. Зайве
 * підтвердження «замінити?» для зламаного постачальника безпечне; приховати заміну було б гірше. НЕ звужувати.
 */
export function roleHolders(e, list) {
  const mine = new Set(Array.isArray(e?.roles) ? e.roles : []);
  if (!mine.size) return [];
  return (Array.isArray(list) ? list : []).filter((o) => o && o.id !== e.id && o.enabled === true
    && o.status !== "missing" && Array.isArray(o.roles) && o.roles.some((r) => mine.has(r)));
}

/**
 * Що станеться з ролями, які `e` зараз ВИКОНУЄ (`capabilities[role] === e.id`), якщо його вимкнути:
 * `[{role, kind: 'legacy'}]` — простір з інтеграціями (ЛІГА) повернеться до вбудованої публікації чи коментарів;
 * `[{role, kind: 'none', noneKey}]` — роль лишиться без модуля.
 */
export function disableConsequences(e, space) {
  const caps = space?.capabilities;
  if (!e || !caps || typeof caps !== "object") return [];
  const out = [];
  for (const role of Array.isArray(e.roles) ? e.roles : []) {
    if (role === "error" || !has(caps, role) || caps[role] !== e.id) continue;
    if (space.integrations === true && (role === "publish" || role === "comments")) out.push({ role, kind: "legacy" });
    else out.push({ role, kind: "none", noneKey: roleKeys(role)?.none ?? null });
  }
  return out;
}

const TYPES = new Set(["text", "path", "bool", "select", "secret"]);

/** Поля форми з `settings[]` запису. Невідомий тип — `text`; секрет несе лише `set` (`true|false|null`). */
export function formFields(e) {
  const out = [];
  for (const s of Array.isArray(e?.settings) ? e.settings : []) {
    if (!s || typeof s.key !== "string" || !s.key) continue;
    const type = TYPES.has(s.type) ? s.type : "text";
    const f = { key: s.key, type, label: typeof s.label === "string" && s.label ? s.label : s.key, required: s.required === true };
    if (type === "secret") f.set = s.set === true ? true : (s.set === false ? false : null);
    else f.value = s.value;
    if (type === "select") {
      f.options = (Array.isArray(s.options) ? s.options : []).filter((o) => o && typeof o.value === "string")
        .map((o) => ({ value: o.value, label: typeof o.label === "string" && o.label ? o.label : o.value }));
      /* `blank` — вʼю малює ПОРОЖНІЙ варіант (і обирає його, коли значення не серед варіантів). Необовʼязковому він
         потрібен завжди (очистити); обовʼязковому — лише коли дійсного значення нема. Без цього браузер мовчки
         показав би перший варіант, і форма записала б його, хоча людина нічого не обирала. */
      f.blank = !f.required || !f.options.some((o) => o.value === String(f.value ?? ""));
    }
    out.push(f);
  }
  return out;
}

/**
 * Початкові значення форми (секретів нема ніколи): `{values, secrets: {}, erase: []}`.
 * Форма стартує з того, що людина БАЧИТЬ: значення списку, якого вже нема серед варіантів, показується порожнім
 * варіантом, тож і початкове — `""`. Інакше недоторкана форма дала б запис `null` (стирання, якого ніхто не просив).
 */
export function initialForm(fields) {
  const values = [];
  for (const f of fields) {
    if (f.type === "secret") continue;
    if (f.type === "select") {
      const v = f.value == null ? "" : String(f.value);
      values.push([f.key, f.options.some((o) => o.value === v) ? v : ""]);
      continue;
    }
    values.push([f.key, f.type === "bool" ? f.value === true : (f.value == null ? "" : String(f.value))]);
  }
  return { values: Object.fromEntries(values), secrets: {}, erase: [] };
}

const trim = (v) => (typeof v === "string" ? v.trim() : v);
/** Нормалізація значення поля для ПОРІВНЯННЯ: текст і шлях — без країв; список — точно (варіант може бути з пробілом). */
const norm = (f, v) => (f.type === "select" ? String(v ?? "") : trim(String(v ?? "")));

/** Чи можна стерти секрет: лише заданий і необовʼязковий (спільне для патча й вʼю — кнопка «Стерти»). */
export const canErase = (f) => f?.type === "secret" && f.set === true && !f.required;

/**
 * Патч запиту: `{settings, secrets}` лише зі зміненого. Текст і шлях обрізаються з обох боків порівняння (вставка з
 * буфера несе пробіли й перенос рядка; збережене з пробілами без правки — не зміна); список порівнюється й іде
 * ТОЧНО. Очищене поле — `null` (ключ знімається, діє типове маніфесту). Секрет: введене — нове значення (обрізається
 * СВІДОМО: токен вставляють з переносом рядка); позначене до стирання — `null`, але лише `canErase`; введене
 * перемагає стирання. Поле, якого нема в `cur.values`, не пишеться: `undefined` не стає ні `null`, ні `false`.
 */
export function formPatch(fields, init, cur) {
  const settings = [];
  const secrets = [];
  const erase = new Set(Array.isArray(cur?.erase) ? cur.erase : []);
  for (const f of fields) {
    if (f.type === "secret") {
      const typed = trim(get(cur?.secrets, f.key));
      if (typeof typed === "string" && typed) secrets.push([f.key, typed]);
      else if (erase.has(f.key) && canErase(f)) secrets.push([f.key, null]);
      continue;
    }
    if (!has(cur?.values, f.key)) continue;
    if (f.type === "bool") {
      const a = get(init?.values, f.key) === true;
      const b = get(cur?.values, f.key) === true;
      if (a !== b) settings.push([f.key, b]);
      continue;
    }
    const a = norm(f, get(init?.values, f.key));
    const b = norm(f, get(cur?.values, f.key));
    if (a !== b) settings.push([f.key, b === "" ? null : b]);
  }
  return { settings: Object.fromEntries(settings), secrets: Object.fromEntries(secrets) };
}

export const isDirty = (p) => Object.keys(p?.settings ?? {}).length > 0 || Object.keys(p?.secrets ?? {}).length > 0;

/** Ключі обовʼязкових полів без значення: порожній текст/шлях/список; секрет не заданий (чи невідомо) і не введений. */
export function missingRequired(fields, cur) {
  return fields.filter((f) => {
    if (!f.required || f.type === "bool") return false;
    if (f.type === "secret") {
      const typed = trim(get(cur?.secrets, f.key));
      return f.set !== true && !(typeof typed === "string" && typed);
    }
    return norm(f, get(cur?.values, f.key)) === "";
  }).map((f) => f.key);
}

/** Тіло `module-enable|settings`: `space` і `id` завжди (запис іде туди, що людина бачить); порожні патчі не йдуть. */
export function writePayload(space, id, patch, replace = false) {
  const out = { space, id };
  if (Object.keys(patch?.settings ?? {}).length) out.settings = patch.settings;
  if (Object.keys(patch?.secrets ?? {}).length) out.secrets = patch.secrets;
  if (replace === true) out.replace = true;
  return out;
}
