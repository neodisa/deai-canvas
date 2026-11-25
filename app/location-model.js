/**
 * Адреса оболонки (0.40): де людина в канвасі — hash `#sp=…&t=…&it=…&p=…` (+ `st`, `m=o`, `v=flow`, `h=tasks|settings`).
 * Чисті функції без DOM. Ключ `p=` має ту саму семантику, що в превʼю (`#p=` у `ext-shell.js`). Невідомі ключі ігноруються.
 */
export const EMPTY_LOC = Object.freeze({ sp: null, t: null, it: null, p: null, st: null, m: null, v: null, h: null });
/** Ключі-рядки в канонічному порядку; розділ «Links» теми `docs/agents/tasks.md` звіряється з цим переліком парним тестом. */
export const LOC_KEYS = ["sp", "t", "it", "p", "st"];

const dec = (s) => { try { return decodeURIComponent(s); } catch (e) { return s; } };   // чиясь обрізана адреса не ламає старт

export function parseLocation(hash) {
  const loc = { ...EMPTY_LOC };
  const raw = String(hash || "").replace(/^#/, "");
  if (!raw) return loc;
  for (const part of raw.split("&")) {
    const i = part.indexOf("=");
    if (i <= 0) continue;
    const k = part.slice(0, i);
    const v = dec(part.slice(i + 1));
    if (!v) continue;
    if (LOC_KEYS.includes(k)) loc[k] = v;
    else if (k === "m") loc.m = v === "o" ? "o" : null;
    else if (k === "v") loc.v = v === "flow" ? "flow" : null;
    else if (k === "h") loc.h = v === "tasks" || v === "settings" ? v : null;
  }
  return loc;
}

export function formatLocation(loc) {
  const l = { ...EMPTY_LOC, ...loc };
  const out = [];
  for (const k of LOC_KEYS) {
    if (!l[k]) continue;
    if (k === "st" && !l.p) continue;
    out.push(`${k}=${encodeURIComponent(l[k])}`);
  }
  if (l.m === "o") {
    out.push("m=o");
    if (l.v === "flow") out.push("v=flow");
  }
  if (l.h) out.push(`h=${l.h}`);
  return out.length ? `#${out.join("&")}` : "";
}

export const sameLocation = (a, b) => formatLocation(a) === formatLocation(b);
export const hasPlace = (loc) => formatLocation(loc) !== "";

/**
 * Що робити із задачею з адреси (чиста частина `resolveTaskLoc` з `app.js`). `rows` — рядки `/api/tasks?all=1` або `null`, коли запит
 * НЕ вдався. `'current'` — діємо в поточній; `'switch'` — перемкнути; `'unknown'` — запит удався, а задачі нема, вона `missing` чи її
 * id двозначний (`/api/task-switch` приймає лише `id`, тож однаковий id у двох просторах він не розрізнить — 409; `sp` в адресі —
 * лише інформація, а не ключ вибору); `'error'` — запит не вдався або простір, де могла бути задача, не прочитано (`skipped`): НЕ «нема» (запис стека не можна викидати через збій).
 */
export function classifyTask(loc, current, rows, skipped = []) {
  if (!loc.t || loc.t === current) return "current";
  if (rows === null) return "error";
  const m = rows.filter((x) => x.id === loc.t);
  /* Простір, якого сервер не зміг прочитати (`skipped_spaces`), не доводить, що задачі там нема: адреса з таким `sp` — «невідомо»,
     а без `sp` «нема» дозволено лише коли ВСІ простори прочитано. Це `error` (запис стека лишається), а не `unknown`. */
  if (loc.sp && skipped.includes(loc.sp)) return "error";
  if (!loc.sp && m.length === 0 && skipped.length) return "error";
  if (m.length !== 1 || m[0].missing) return "unknown";
  return "switch";
}
