/**
 * Модель екрана «Задачі»: пошук, фільтри, сортування, відносний час. Чиста
 * логіка — ні DOM, ні fetch, ні `t()` (як `app/bar-model.js` і
 * `app/rows-model.js`): тестується в node, а DOM-шар лише збирає розмітку з
 * того, що тут повернулось.
 *
 * Модель приймає ДВІ форми рядка з `/api/tasks-overview` і не вимагає
 * однакової: «мої» (`mine[i]`) мають `tags`/`opened`/`changed` (секунди),
 * командні (`team.rows[i]`) — `designer`/`updated` (ISO). Тому кожна функція
 * дивиться лише на поля, які вона справді використовує, а відсутнє поле — це
 * «нема даних», а не помилка: фільтр за дизайнером не чіпає рядки без
 * `designer`, сортування «змінено» вміє обидва формати часу.
 *
 * Жодна функція не мутує вхід. Сортування й фільтри віддають НОВИЙ масив:
 * екран тримає початкове сховище й перебудовує вид із нього при кожній зміні
 * запиту, і вхід, переставлений «по дорозі», розійшовся б із тим, що показано.
 */

/** Ключі сортувань; підпис у UI — `sort_${k}` (словник наповнює DOM-шар). */
export const SORTS = ["recent", "changed", "jira", "title", "status"];

/* Роздільник між ключем і назвою в живих даних — п'ять варіантів (` · `,
   `: `, ` — `, ` – `, ` - `), тож ріжемо будь-який із них разом із пробілами
   навколо. */
const SEP = "[·:—–-]";

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * Назва для показу. Справжні назви часто починаються з ключа Jira
 * (`LIGA-7019 · Очікування…`), а ключ екран уже показує окремим значком —
 * дубль у назві з'їдає ширину рядка й нічого не додає. Різати можна тільки
 * коли ключ відомий: `LIGA-5 · …` у задачі без `jira` — це її справжня назва.
 * Якщо після зрізу не лишилось тексту (назва = один ключ), віддаємо назву як
 * є: порожній рядок у списку гірший за повтор ключа.
 */
export function cleanTitle(t) {
  const base = t.title || t.id;
  if (!t.jira || !t.title) return base;
  /* Роздільник обовʼязковий: без нього `LIGA-11` зʼїв би початок `LIGA-115`. */
  const re = new RegExp(`^\\s*${escapeRe(t.jira)}\\s*${SEP}\\s*`, "i");
  const stripped = base.replace(re, "");
  return stripped.trim() ? stripped : base;
}

/** Стійкий ключ задачі: Jira, а де її нема — id (`boss-interface`). */
export function taskKey(t) {
  return t.jira || t.id;
}

/**
 * Пошук: КОЖНЕ слово запиту (через пробіл, без регістру) мусить зустрітись
 * десь у ключі/id/назві/статусі Jira/дизайнері/мітках. Слова, а не фраза цілком:
 * «санк біз» знаходить «Санкції Бізнес-груп», і писати назву підряд не треба.
 * Назву беремо СИРУ (з ключем), щоб `7019` і `LIGA-7019` шукались однаково.
 */
export function matches(t, q) {
  const words = String(q || "").toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return true;
  const hay = [t.jira, t.id, t.title, t.jiraStatus, t.designer, ...(t.tags || [])]
    .filter(Boolean).join(" ").toLowerCase();
  return words.every((w) => hay.includes(w));
}

/** Статуси-фільтри екрана «Задачі». Один перелік: `app.js` перевіряє ним
 *  збережене значення, а `filterTasks` розуміє ті самі три. */
export const HOME_STATUSES = ["active", "done", "all"];

/** Виконана = категорія Jira `done`; задача без статусу — активна, не виконана. */
export function isDone(t) {
  return t.jiraCat === "done";
}

/**
 * Лічильники для вкладок «Активні / Виконані / Усі». Рахуються ПІСЛЯ запиту:
 * цифра на вкладці має казати, скільки там знайдеться, а не скільки задач
 * узагалі, інакше пошук лишає на вкладках числа, яких натиснувши не побачиш.
 */
export function statusCounts(list, q) {
  const out = { active: 0, done: 0, all: 0 };
  for (const t of list) {
    if (!matches(t, q)) continue;
    out.all += 1;
    out[isDone(t) ? "done" : "active"] += 1;
  }
  return out;
}

/**
 * Ключ мітки для чипів і фільтра: без регістру й крайніх пробілів (`United` і `united` — одна мітка). Не рядок і порожнє
 * дають порожній ключ — викликач такі мітки пропускає.
 */
export const tagKey = (s) => String(s ?? "").trim().toLowerCase();

/**
 * Фільтр екрана. Порожній `Set` = «не фільтрувати за цим». Дизайнера перевіряємо лише в рядків, які це поле мають:
 * «мої» не мають `designer`, і фільтр за ним не повинен мовчки ховати все з іншого джерела. Мітки — навпаки: вибрана
 * мітка ховає задачу БЕЗ міток (профільний фільтр 0.10.0 такі пропускав; свідома відмінність 4b-3). АБО між вибраними —
 * задача з будь-якою з них. Командні рядки міток не мають: екран віддає `tags: null` на «Команді».
 */
export function filterTasks(list, f) {
  const { q = "", status = "all", tags, designers } = f || {};
  return list.filter((t) => {
    if (!matches(t, q)) return false;
    if (status === "active" && isDone(t)) return false;
    if (status === "done" && !isDone(t)) return false;
    if (tags && tags.size && !(t.tags || []).some((x) => tags.has(tagKey(x)))) return false;
    if (designers && designers.size && t.designer && !designers.has(t.designer)) return false;
    return true;
  });
}

/**
 * Розбір збереженого стану екрана (`localStorage["dc-tasks-ui"]`, уже розібраний із JSON) у початковий `homeUi`. Чиста
 * функція, щоб міграцію старого ключа можна було перевірити без браузера. Мітки — з `raw.tags`; коли його нема (стан 0.10.0
 * писав `profiles`), — з `raw.profiles`: профіль `united` збігається з ключем похідної мітки «United», тож вибраний чип
 * лишається вибраним. Обидва — через `tagKey`. Сміття (не обʼєкт, не масив, не рядки) — порожньо й типове, без винятку.
 * `q` не зберігається: людина, що повернулась на екран, чекає побачити всі задачі.
 */
export function readHomeUi(raw) {
  const ui = { tab: "mine", q: "", sort: "recent", status: "active", tags: new Set(), designers: new Set() };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return ui;
  if (raw.tab === "team") ui.tab = "team";
  if (typeof raw.sort === "string" && SORTS.includes(raw.sort)) ui.sort = raw.sort;
  if (HOME_STATUSES.includes(raw.status)) ui.status = raw.status;
  const keys = Array.isArray(raw.tags) ? raw.tags : raw.profiles;
  if (Array.isArray(keys)) for (const v of keys) if (typeof v === "string" && tagKey(v)) ui.tags.add(tagKey(v));
  if (Array.isArray(raw.designers)) for (const v of raw.designers) if (typeof v === "string") ui.designers.add(v);
  return ui;
}

/* Усі порівняльники — «менше = раніше». «Нема даних» (null) завжди в кінці,
   незалежно від напрямку: задача без дати не має виринати нагору лише тому,
   що сортування спадне. Рівні ключі дають 0 — стабільність сортування
   (`Array.prototype.sort` стабільний з ES2019) лишає їх у вхідному порядку. */
/* `opened` — ISO-рядок, але зсуви можуть різнитись (`+05:00` проти `Z`), і
   лексикографічне порівняння тоді бреше про порядок у часі. Тож порівнюємо
   розібраний час; нерозбірливе (null, сміття) = «нема даних» → в кінець. */
const openedMs = (t) => {
  const p = t.opened ? Date.parse(t.opened) : NaN;
  return Number.isNaN(p) ? null : p;
};

const byDesc = (a, b) => (a == null && b == null ? 0 : a == null ? 1 : b == null ? -1 : a < b ? 1 : a > b ? -1 : 0);

const STATUS_RANK = { new: 0, indeterminate: 1, done: 2 };

/* Час зміни в мс. «Мої» дають секунди (`changed`), командні — ISO (`updated`). */
function changedMs(t) {
  if (typeof t.changed === "number" && Number.isFinite(t.changed)) return t.changed * 1000;
  const p = t.updated ? Date.parse(t.updated) : NaN;
  return Number.isNaN(p) ? null : p;
}

/* Номер із ключа: LIGA-7019 → 7019. Свіжіші задачі мають більший номер, тож
   «за Jira» спадно = «найновіші нагорі». */
function jiraNum(t) {
  const m = /(\d+)(?!.*\d)/.exec(t.jira || "");
  return m ? Number(m[1]) : null;
}

const CMP = {
  recent: (a, b) => byDesc(openedMs(a), openedMs(b)),
  changed: (a, b) => byDesc(changedMs(a), changedMs(b)),
  jira: (a, b) => byDesc(jiraNum(a), jiraNum(b)),
  title: (a, b) => cleanTitle(a).localeCompare(cleanTitle(b), "uk"),
  status: (a, b) => (STATUS_RANK[a.jiraCat] ?? 3) - (STATUS_RANK[b.jiraCat] ?? 3),
};

/** Нова відсортована копія; невідомий ключ → `recent`. */
export function sortTasks(list, key) {
  return [...list].sort(CMP[key] || CMP.recent);
}

const MIN = 60_000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;

/**
 * Відносний час як ІМʼЯ ключа словника + число (`{key, n}`): текст збирає
 * DOM-шар через `t(key, n)` — модуль мови не знає (патерн `bar-model.js`).
 * Приймає МІЛІСЕКУНДИ; секунди з `changed` перераховує викликач; нескінченний
 * `nowMs` замінюється на `Date.now()`. Час із
 * майбутнього (розбіжність годинників сервера й браузера) читається як
 * «щойно», а не як мінус-хвилини. Від 35 діб віддаємо сам момент (`n` =
 * epochMs) — формат дати належить словнику.
 */
export function relTime(epochMs, nowMs) {
  /* Викликач міг не передати `nowMs` (або передати NaN): тоді `d` стає NaN, усі
     порівняння хибні, і щойнашній час мовчки падає в `relDate`. */
  if (!Number.isFinite(nowMs)) nowMs = Date.now();
  if (typeof epochMs !== "number" || !Number.isFinite(epochMs)) return { key: "relUnknown", n: 0 };
  const d = nowMs - epochMs;
  if (d < 2 * MIN) return { key: "relJustNow", n: 0 };
  if (d < HOUR) return { key: "relMin", n: Math.floor(d / MIN) };
  if (d < DAY) return { key: "relHour", n: Math.floor(d / HOUR) };
  if (d < 2 * DAY) return { key: "relYesterday", n: 0 };
  if (d < 7 * DAY) return { key: "relDays", n: Math.floor(d / DAY) };
  if (d < 35 * DAY) return { key: "relWeeks", n: Math.floor(d / (7 * DAY)) };
  return { key: "relDate", n: epochMs };
}
