/**
 * Сітка модулів «Налаштувань» (етап Е, 0.31.0; спека `docs/superpowers/specs/2026-11-19-settings-e-design.md`, §2). Чисті
 * функції — ні DOM, ні `t()`: лише ІМЕНА ключів словника. Джерело правди про дозволені дії — `cardView` моделі
 * «Підключень»; тут із них обирається ОДНА дія на картці, решта йде в меню «⋯».
 */
import { ROLE_ORDER, cardView, isOwn, ownRuns, roleError, roleIcon, roleKeys } from "./connections-model.js";

/** Бейдж картки → суфікс класу `.bdg--*` (`error` → `err`, `untrusted` → `trust`; решта — як є). */
export const BADGE_CLASS = { ok: "ok", error: "err", unchecked: "unchecked", off: "off", missing: "missing", untrusted: "trust" };

/** Чи є в модуля що налаштовувати: порожній `settings[]` — нема; невідомо (нема поля) — вважаємо, що є. */
const hasSettings = (e) => !(Array.isArray(e?.settings) && e.settings.length === 0);

/**
 * Рядок словника, що був хвостом фрази, — реченням: перша літера велика, у кінці крапка (якщо там уже нема `.`, `!`, `?`, `…`).
 * Наслідки ролей (`cnNone*`) писались продовженням «Зараз: нікого — …», тож частина починається з малої й без крапки.
 */
export function sentence(text) {
  const s = String(text ?? "").trim();
  if (!s) return "";
  const first = Array.from(s)[0];
  const up = first.toLocaleUpperCase() + s.slice(first.length);
  return /[.!?…]$/.test(up) ? up : `${up}.`;
}

/**
 * Стан картки → `{badge, action, click, menu}`:
 *   action — рівно одна дія на картці (`enable|configure|check|trust|trustinfo`) або `null`;
 *   click  — що робить клік по картці: увімкнений з робочим кодом → `configure` (шухляда); інакше — дія картки (`trust` для
 *            недовіреного, `enable`, `trustinfo`) чи `null`;
 *   menu   — пункти «⋯»: `{act, key, danger?}` і `"sep"`: Налаштувати (є налаштування) · Перевірити (увімкнений) ·
 *            Код (свій) · Забрати довіру (свій довірений) · Чому не можна (свій, нова версія не годиться) · — · Вимкнути.
 */
/* `roleFailed` — модуль ТРИМАЄ роль, чий збій записано в `capabilities.errors[роль]` (`failedRole`): картка тоді «Помилка» з дією
   «Налаштувати», навіть якщо сам запис ще «Підключено»/«Не перевірено». */
export function cardModel(e, roleFailed = false) {
  const v = cardView(e);
  const failed = roleFailed === true && e?.enabled === true && e?.status !== "missing" && (v.badge === "ok" || v.badge === "unchecked");
  if (failed) v.badge = "error";
  const own = isOwn(e);
  let action = null;
  if (e?.status === "missing") action = null;
  else if (v.badge === "untrusted" || (own && e.trust === "changed")) action = "trust";
  else if (own && !ownRuns(e) && e.trust === "refused") action = "trustinfo";
  else if (v.badge === "off") action = "enable";
  else if (v.badge === "error") action = "configure";
  else if (v.badge === "unchecked") action = "check";

  const working = e?.status !== "missing" && e?.enabled === true && !(own && !ownRuns(e));
  let click = null;
  if (e?.status === "missing") click = null;
  else if (working) click = "configure";
  else click = action;

  const head = [];
  if (v.actions.includes("configure") && hasSettings(e) && action !== "configure") head.push({ act: "configure", key: "cnConfigure" });
  if (v.actions.includes("check") && action !== "check") head.push({ act: "check", key: "cnCheck" });
  if (own) head.push({ act: "trust", key: "mcCode" });
  if (own && e.record === true) head.push({ act: "untrust", key: "cnUntrust" });
  if (v.actions.includes("trustinfo") && action !== "trustinfo") head.push({ act: "trustinfo", key: "cnTrustInfo" });
  const tail = v.actions.includes("disable") ? [{ act: "disable", key: "cnDisable", danger: true }] : [];
  const menu = head.length && tail.length ? [...head, "sep", ...tail] : [...head, ...tail];
  return { badge: v.badge, action, click, menu };
}

/** Роль, чий збій записано в `capabilities` і яку ТРИМАЄ цей модуль (увімкнений, не `missing`): код збою або `""`. */
export function failedRole(e, caps) {
  if (!e || e.enabled !== true || e.status === "missing") return "";
  for (const r of Array.isArray(e.roles) ? e.roles : []) if (roleError(caps, r)) return r;
  return "";
}

const valid = (e) => e && typeof e === "object" && typeof e.id === "string";
const firstRole = (e) => (Array.isArray(e.roles) && typeof e.roles[0] === "string" ? e.roles[0] : "");

/** Що в сітці: увімкнені, УСІ свої (навіть вимкнені), «Не встановлено». Вимкнені вбудовані — лише в каталозі. */
export function gridEntries(list) {
  const items = (Array.isArray(list) ? list : []).filter(valid)
    .filter((e) => e.status === "missing" || isOwn(e) || e.enabled === true);
  const named = [...new Set(items.map(firstRole))].filter((r) => r && !ROLE_ORDER.includes(r)).sort();
  const order = [...ROLE_ORDER, ...named, ""];
  const rank = (e) => order.indexOf(firstRole(e));
  return items.map((e, i) => ({ e, i })).sort((a, b) => rank(a.e) - rank(b.e) || a.i - b.i).map((x) => x.e);
}

/** Ролі зі списку ROLE_ORDER, яких не покриває жоден модуль із сітки («Інше» ніколи): `[{role, icon, titleKey, noneKey, error}]`
 *  (`error` — код збою ролі з `capabilities.errors`, коли відомий, інакше `""`: пунктирна картка тоді каже про збій). */
export function emptyRoles(list, caps) {
  const covered = new Set(gridEntries(list).flatMap((e) => (Array.isArray(e.roles) ? e.roles : [])));
  return ROLE_ORDER.filter((r) => !covered.has(r))
    .map((role) => ({ role, icon: roleIcon(role), titleKey: roleKeys(role).title, noneKey: roleKeys(role).none, error: roleError(caps, role) }));
}
