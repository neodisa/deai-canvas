/**
 * Кільце помилок клієнта (0.23.0): останні `error`/`unhandledrejection` сторінки для діагностики відгуку. Лише МІНІМУМ, потрібний, щоб
 * зрозуміти збій: повідомлення (обрізане), файл у вигляді `app/<імʼя>` і рядок. Ні стеків, ні повних адрес, ні query-рядків (у них
 * бувають токени/імена задач): `file` — частина від `/app/` включно, решта адреси → `''`.
 *
 * Модуль ЧИСТИЙ, окрім `initErrRing(win)`, що ставить рівно два слухачі. `app.js` підключає його ПЕРШИМ імпортом: тоді кільце ловить
 * і помилки завантаження наступних модулів. Кільце лежить у памʼяті сторінки; відгук бере з нього ОДИН знімок (`list()`).
 */

/** Скільки останніх помилок тримає кільце (сервер приймає не більше стільки ж: `feedback.CLIENT_ERRORS_MAX`). */
export const RING_MAX = 20;
/** Найдовше повідомлення, символів (сервер ріже так само: `feedback.CLIENT_MSG_MAX`). */
export const MSG_MAX = 200;

const ring = [];

/** Адреса → `app/<шлях>` або `''`. Query (`?…`) і фрагмент (`#…`) відрізаються ДО пошуку, щоб не лишитись у результаті. */
export function fileOf(url) {
  if (typeof url !== "string") return "";
  const bare = url.split("#")[0].split("?")[0];
  const i = bare.indexOf("/app/");
  return i < 0 ? "" : bare.slice(i + 1);
}

/** У повідомленні адреси теж можуть нести query (`fetch http://…/x?token=…`): лишаємо адресу без `?…`/`#…`. */
const URL_QUERY = /(https?:\/\/[^\s?#)'"]+)[?#][^\s)'"]*/g;

/** Подія `error`/`unhandledrejection` → `{msg, file, line}` або `null` (сміття). Нічого не кидає. */
export function normalize(ev) {
  if (!ev || typeof ev !== "object") return null;
  let raw;
  let file = "";
  let line = 0;
  if (ev.type === "unhandledrejection") {
    const r = ev.reason;
    raw = r && typeof r === "object" && typeof r.message === "string" ? r.message : (typeof r === "string" ? r : "");
  } else {
    raw = typeof ev.message === "string" ? ev.message : "";
    file = fileOf(ev.filename);
    line = Number.isInteger(ev.lineno) && ev.lineno >= 0 ? ev.lineno : 0;
  }
  const msg = Array.from(raw.replace(URL_QUERY, "$1")).slice(0, MSG_MAX).join("");
  if (!msg && !file) return null;
  return { msg, file, line };
}

/** Додати подію в кільце (найстаріші випадають). Не кидає на будь-який вхід. */
export function push(ev) {
  try {
    const e = normalize(ev);
    if (!e) return;
    ring.push(e);
    while (ring.length > RING_MAX) ring.shift();
  } catch (_) { /* кільце — допоміжне: воно саме не має ставати причиною помилки */ }
}

/** Копія кільця: що з нею зроблять, кільце не зачепить. */
export const list = () => ring.map((e) => ({ ...e }));

/** Шов тестів. */
export function reset() { ring.length = 0; }

const installed = new WeakSet();

/** Ставить рівно два слухачі на `win` (повторний виклик на тому ж вікні не дублює) і повертає `list`. */
export function initErrRing(win = typeof window === "undefined" ? null : window) {
  if (win && typeof win.addEventListener === "function" && !installed.has(win)) {
    installed.add(win);
    win.addEventListener("error", push);
    win.addEventListener("unhandledrejection", push);
  }
  return list;
}

initErrRing();
