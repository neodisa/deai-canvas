/**
 * Розмітка екрана «Задачі» (вхід — логотип у смузі). Чисті будівельники рядків:
 * ні DOM, ні fetch, ні `localStorage` — як `shell-bar.js` і `shell-panel.js`.
 * Усе, що торкається сторінки (фокус, клавіші, мережа, перемикання задачі),
 * живе в `app.js`; тут лише «стан → HTML», тож екран тестується в node без
 * браузера, а живий тест перевіряє вже проводку.
 *
 * Дві точки входу, бо екран перемальовується двома різними способами:
 *   · `homeHTML(ui, data)` — усе: заголовок, вкладки, пошук, сортування, чіпи,
 *     сітка. Для відкриття екрана й перемикання вкладки (там міняються і
 *     плейсхолдер пошуку, і список сортувань);
 *   · `homeGridHTML(ui, data)` — лише НИЖНЯ частина (чіпи з лічильниками,
 *     банер, сітка). Для набору в полі пошуку: перемалюй ми поле разом із
 *     сіткою, кожен символ губив би фокус, каретку й IME-композицію (той самий
 *     клас пастки, що `repaintTaskList` у дропдауні задач).
 *
 * Вхідні форми:
 *   ui   = { tab: 'mine'|'team', q, sort, status: 'active'|'done'|'all',
 *            tags: Set (ключі міток, `tagKey`), designers: Set, now?: мс }
 *          (`cursorId` екрана тут НЕ читається: фокус повертає `app.js`.)
 *   data = відповідь `/api/tasks-overview` (`{current, mine, team:{rows, error,
 *          fetchedAt, rowsAt}|null, space:{name, integrations}|null}`), АБО
 *          `null`/`{loading:true[, space]}` до відповіді, АБО `{failed: "причина"}`,
 *          коли запит не вдався.
 *
 * Простори (Deai 1.0, етап 1): `data.space` дає заголовок «Задачі · <простір>».
 * Простір без інтеграцій (`integrations === false`) не має дашборда команди —
 * `team: null`: вкладки «Команда» нема, а збережена в UI вкладка `team`
 * читається як `mine` (`effectiveTab`; без цього екран малював би порожній
 * список під вкладкою, якої нема), і в голові зʼявляється «Нова задача» — єдиний
 * спосіб завести задачу не з реєстру Jira. Порожній такий простір показує не
 * «Нічого не знайдено» (фільтрувати нема що), а підказку з тією ж кнопкою й
 * порадою попросити агента.
 *
 * ⛔ Усе, що приходить із даних (назва, ключ, дизайнер, статус Jira, причина
 * помилки), іде в розмітку ЛИШЕ через `esc()`/`mark()`: рядки команди пише
 * хто завгодно з дашборда, і `<b>` у назві не має ставати розміткою.
 * ⛔ `href` — лише http(s) (`safeUrl`): `javascript:` з того ж дашборда
 * виконався б по кліку на «Превʼю».
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { getLang, t } from "./i18n.js";
import { mark } from "./shell-bar.js";
import {
  SORTS, cleanTitle, filterTasks, relTime, sortTasks, statusCounts, tagKey, taskKey,
} from "./tasks-model.js";

/** Сортування вкладок: «Мої» мають `recent` (час відкриття), команда — ні. */
export const sortsFor = (tab) => SORTS.filter((k) => !(tab === "team" && k === "recent"));

/** Типове сортування вкладки. */
export const defaultSort = (tab) => (tab === "team" ? "changed" : "recent");

/** Сортування, яке справді діє: збережене `recent` на вкладці команди (де його
 *  нема) читається як типове, а не як «невідомий ключ». */
export const effectiveSort = (ui) => (sortsFor(ui.tab).includes(ui.sort) ? ui.sort : defaultSort(ui.tab));

/** `href` лише з http(s); решта (`javascript:`, `data:`, порожнє) → `null`. */
export function safeUrl(u) {
  return typeof u === "string" && /^https?:\/\//i.test(u.trim()) ? u.trim() : null;
}

/** Кадр картки: лише власний `/api/task-thumb?…` або http(s). Дашборд командний,
 *  `thumb_url` пише хто завгодно, і `//evil`, `data:`, `javascript:` чи довільний
 *  відносний шлях у `<img src>` — це запит на чужий хост або трекер. `null` —
 *  картка малює «немає кадру». */
export function safeThumb(u) {
  if (typeof u !== "string") return null;
  if (u.startsWith("/api/task-thumb?")) return u;
  return /^https?:\/\//i.test(u) ? u : null;
}

/** Прибрати з фільтрів значення, яких у даних більше нема (звільнений дизайнер,
 *  прибрана з усіх задач мітка): інакше фільтр лишається в `localStorage`, чіпа для нього
 *  нема, а список мовчки порожній. Не чіпає дизайнерів, коли команда недоступна
 *  без рядків, і мітки, коли «моїх» нема, — «не знаю» не те саме, що «нема».
 *  Віддає `true`, якщо щось змінила (тоді викликач зберігає). */
export function pruneFilters(ui, data) {
  if (!ready(data)) return false;
  let changed = false;
  const keep = (set, known) => {
    for (const v of [...set]) if (!known.has(v)) { set.delete(v); changed = true; }
  };
  if (data.mine.length) keep(ui.tags, new Set(data.mine.flatMap((x) => (x.tags || []).map(tagKey)).filter(Boolean)));
  const rows = data.team?.rows || [];
  if (rows.length) keep(ui.designers, new Set(rows.map((x) => x.designer).filter(Boolean)));
  return changed;
}

/** Заглушка кадру, що не завантажився: на неї `app.js` міняє зламаний `<img>`. */
export function thumbBrokenHTML() {
  return `<div class="th-none">${esc(t("thShotBroken"))}</div>`;
}

const ready = (data) => !!(data && Array.isArray(data.mine));

/** Простір без інтеграцій: рівно `integrations === false` (див. `bar-model.js`, «Вимикач»). */
const noIntegrations = (data) => data?.space?.integrations === false;

/** Чи є в екрана вкладка «Команда». Є дані — рішає `team` (`null` або ключа нема =
 *  дашборда нема; обʼєкт, навіть із помилкою, = є). Даних ще нема — вкладка
 *  стоїть, як і раніше «поки вантажиться», АЛЕ відомий простір без інтеграцій
 *  ховає її вже зараз, щоб вона не мигала на мить завантаження. */
const hasTeam = (data) => (ready(data) ? data.team != null : !noIntegrations(data));

/** Вкладка, яка справді малюється: збережена `team` без вкладки «Команда» — `mine`.
 *  Експортована: `app.js` вибирає за нею ще й пошук/сортування/повторний запит. */
export const effectiveTab = (ui, data) => (ui.tab === "team" && !hasTeam(data) ? "mine" : ui.tab);

/** `ui` із вже виправленою вкладкою (копія, лише коли довелось виправити). */
const withTab = (ui, data) => {
  const tab = effectiveTab(ui, data);
  return tab === ui.tab ? ui : { ...ui, tab };
};

/** «Нова задача»: кнопка в голові екрана й у порожньому стані (`data-th="newtask"`). */
const newTaskBtn = () => `<button class="ctl ctl--pri" data-th="newtask">${ico("plus")}${esc(t("newTask"))}</button>`;

/** «Підключення» (етап 3a): у голові простору без інтеграцій, поряд із «Нова задача» (`data-th="conn"`). */
const connBtn = () => `<button class="ctl ctl--out" data-th="conn">${ico("sliders")}${esc(t("cnTitle"))}</button>`;

/** Рядки вкладки: «мої» або рядки дашборда команди. */
function source(ui, data) {
  if (!ready(data)) return [];
  return ui.tab === "team" ? (data.team?.rows || []) : data.mine;
}

/** Час `rowsAt` (секунди) як «ГГ:ХХ» у мові інтерфейсу; нечисло → `null`. */
function clock(sec) {
  if (typeof sec !== "number" || !Number.isFinite(sec)) return null;
  return new Date(sec * 1000).toLocaleTimeString(getLang() === "en" ? "en-GB" : "uk-UA",
    { hour: "2-digit", minute: "2-digit" });
}

/** Відносний час ключем словника: «мої» — `changed` у секундах, команда —
 *  `updated` у ISO. Немає даних → порожньо (а не «—» у кожній картці). */
function relText(x, tab, now) {
  const ms = tab === "team" ? Date.parse(x.updated) : (typeof x.changed === "number" ? x.changed * 1000 : NaN);
  if (!Number.isFinite(ms)) return "";
  const r = relTime(ms, now);
  return t(r.key, r.n);
}

const CAT = { done: "done", indeterminate: "ind" };

/** Дія в кінці рядка бейджів: «мої» — «Мітки» (правка міток задачі) і посилання на опубліковане превʼю; команда —
 *  «Відкрити в канвасі» для своїх, інакше превʼю. ⛔ «Мітки» — кнопка ВСЕРЕДИНІ картки `data-th="open"`: клік по ній не мусить
 *  відкривати задачу, і це тримає лише порядок обробника (`app.js wireHome`: `closest('[data-th]')` бере найближчий — кнопку). */
function actionHTML(x, team) {
  const link = (href, title) => {
    const u = safeUrl(href);
    return u ? `<a class="th-lnk" href="${esc(u)}" target="_blank" rel="noopener"`
      + `${title ? ` title="${esc(title)}"` : ""}>${ico("ext")}${esc(t("thPreview"))}</a>` : "";
  };
  if (!team) {
    const aria = esc(t("thTagsEditAria", taskKey(x)));
    return `<button class="th-lnk" data-th="tags" data-id="${esc(x.id)}" title="${aria}" aria-label="${aria}">`
      + `${ico("pencil")}${esc(t("thTagsEdit"))}</button>${link(x.published, t("thPreviewTitle"))}`;
  }
  if (x.mine) {
    return `<button class="th-lnk" data-th="open" data-id="${esc(x.id)}">`
      + `${ico("task")}${esc(t("thOpenCanvas"))}</button>`;
  }
  return link(x.preview, t("thPreviewTitle"));
}

/** Одна картка. `cur` — id поточної задачі (лише на «Моїх»). */
export function cardHTML(x, ui, cur) {
  const team = ui.tab === "team";
  const q = ui.q || "";
  const isCur = !team && x.id === cur;
  const missing = !team && !!x.missing;
  const src = safeThumb(x.thumb);
  const thumb = src
    ? `<img class="th-img" src="${esc(src)}" alt="" loading="lazy" draggable="false">`
    : `<div class="th-none">${ico("camera")}${esc(t("thNoShot"))}</div>`;
  const parts = team
    ? [x.designer ? mark(x.designer, q) : "",
      x.iterations ? esc(t("thIter", x.iterations)) : "",
      x.pages ? esc(t("thPages", x.pages)) : "",
      esc(relText(x, "team", ui.now))]
    : [esc((x.tags || []).join(", ")),
      x.iterations ? esc(t("thIter", x.iterations)) : esc(t("thNoIter")),
      x.pages ? esc(t("thPages", x.pages)) : "",
      esc(relText(x, "mine", ui.now))];
  /* Статус Jira: порожній (`null`) — «невідомо», бейджа нема взагалі, а не «—». */
  const status = x.jiraStatus
    ? `<span class="th-bdg th-bdg--${CAT[x.jiraCat] || "new"}">${mark(x.jiraStatus, q)}</span>` : "";
  const comments = x.comments > 0
    ? `<span class="th-bdg th-bdg--com" title="${esc(t("thComments", x.comments))}"`
      + ` aria-label="${esc(t("thComments", x.comments))}">${ico("comment")}${esc(x.comments)}</span>` : "";
  const gone = missing
    ? `<span class="th-bdg th-bdg--warn">${ico("warn")}${esc(t("folderMissing"))}</span>` : "";
  /* Дієва картка (відкривається) — `button`; чужа картка команди без своєї теки
     не відкривається нічим, тож і ролі кнопки не має (але лишається у фокусі —
     стрілки ходять по всіх). `aria-disabled` на відсутній теці — НЕ `disabled`:
     клік мусить дійти до обробника й сказати причину тостом. */
  const actionable = !team || !!x.mine;
  const cls = `th-card${isCur ? " th-card--cur" : ""}${missing ? " th-card--miss" : ""}`;
  return `<div class="${cls}" tabindex="0" role="${actionable ? "button" : "group"}"`
    + `${actionable ? ` data-th="open"` : ""} data-id="${esc(x.id)}"${missing ? ' aria-disabled="true"' : ""}>
    <div class="th-thumb">${thumb}</div>
    <div class="th-cbody">
      <div class="th-krow"><span class="th-key">${mark(taskKey(x), q)}</span>${isCur
    ? `<span class="th-curb">· ${esc(t("thCurrent"))}</span>` : ""}</div>
      <div class="th-ttl">${mark(cleanTitle(x), q)}</div>
      <div class="th-meta">${parts.filter(Boolean).join(" · ")}</div>
      <div class="th-badges">${status}${comments}${gone}${actionHTML(x, team)}</div>
    </div></div>`;
}

/** Банер збою: причина + «Спробувати ще»; для застарілих рядків — і «дані на …». */
function bannerHTML(text, note) {
  return `<div class="th-banner" role="status">${ico("warn")}<span class="th-bmsg">${esc(text)}`
    + `${note ? ` <span class="th-stale">${esc(note)}</span>` : ""}</span>`
    + `<button class="th-lnk" data-th="retry">${ico("refresh")}${esc(t("retry"))}</button></div>`;
}

/** Банер «Трекер недоступний» (4c-2): лише на «Моїх» — статуси трекера живуть у картках «Моїх» (рядки «Команди» їх не
 *  отримують). `data.tracker` = `null` (трекера нема) чи `{error, okAt}`; `okAt` — епоха останнього успіху (`null` — його не
 *  було): статуси в картках тоді лишаються з останнього відомого й підписані часом. Текст помилки — чужий ввід, іде лише через
 *  `bannerHTML` (esc). */
function trackerBanner(team, data) {
  const tr = data.tracker;
  if (team || !tr || !tr.error) return "";
  const at = clock(tr.okAt);
  return bannerHTML(t("thTrackerErr", tr.error), at ? t("thStale", at) : "");
}

/** Чіпи: статус (з лічильниками після запиту), потім мітки чи дизайнери. */
function chipsHTML(ui, data, src, shown) {
  const c = statusCounts(src, ui.q);
  const st = (k, label) => `<button class="th-chip${ui.status === k ? " th-chip--on" : ""}"`
    + ` data-th="status" data-v="${k}" aria-pressed="${ui.status === k}">${esc(label)}</button>`;
  const team = ui.tab === "team";
  let extra;
  if (team) {
    const names = [...new Set(src.map((x) => x.designer).filter(Boolean))].sort((a, b) => a.localeCompare(b, "uk"));
    extra = names.map((d) => `<button class="th-chip${ui.designers.has(d) ? " th-chip--on" : ""}"`
      + ` data-th="designer" data-v="${esc(d)}" aria-pressed="${ui.designers.has(d)}">${esc(d)}</button>`).join("");
  } else {
    /* Ключ чипа — `tagKey` (без регістру), підпис — ПЕРШИЙ побачений запис; лічильник — задач, а не записів: мітка двічі в одній
       задачі (`x`, `X`) рахується раз. Порядок: більше задач — раніше, далі абетка. */
    const seen = new Map();                 // ключ → {label, n}
    for (const x of src) {
      const own = new Set();
      for (const tag of x.tags || []) {
        const k = tagKey(tag);
        if (!k) continue;
        const e = seen.get(k);
        if (!e) seen.set(k, { label: String(tag), n: 1 });
        else if (!own.has(k)) e.n += 1;
        own.add(k);
      }
    }
    extra = [...seen].sort((a, b) => b[1].n - a[1].n || a[1].label.localeCompare(b[1].label, "uk"))
      .map(([k, e]) => `<button class="th-chip${ui.tags.has(k) ? " th-chip--on" : ""}"`
        + ` data-th="tag" data-v="${esc(k)}" aria-pressed="${ui.tags.has(k)}">${esc(e.label)}</button>`).join("");
  }
  return `<div class="th-chips" role="group" aria-label="${esc(t("thFiltersLabel"))}">`
    + st("active", t("thStActive", c.active)) + st("done", t("thStDone", c.done)) + st("all", t("thStAll", c.all))
    + (extra ? `<span class="th-gap"></span>${extra}` : "")
    + `<span class="th-count">${esc(t("thShown", shown, src.length))}</span></div>`;
}

/** Нижня частина екрана: чіпи, банер, сітка (або стани «вантажу»/«збій»). */
export function homeGridHTML(ui, data) {
  ui = withTab(ui, data);
  if (!ready(data)) {
    return data && data.failed
      ? bannerHTML(t("thLoadErr", data.failed))
      : `<div class="th-note" role="status">${esc(t("thLoading"))}</div>`;
  }
  const team = ui.tab === "team";
  const src = source(ui, data);
  const sort = effectiveSort(ui);
  const list = sortTasks(filterTasks(src, {
    q: ui.q, status: ui.status,
    tags: team ? null : ui.tags, designers: team ? ui.designers : null,
  }), sort);
  const err = team ? data.team?.error : null;
  /* Помилка + рядки = ЗАСТАРІЛІ рядки (сервер не стирає останні відомі): їх
     показуємо під банером із часом останнього успіху. Помилка без рядків —
     лише банер: сітки, яка вдає «команда порожня», нема чого малювати. */
  const stale = err && src.length ? clock(data.team?.rowsAt) : null;
  /* `loadError` — повторний запит не вдався, а попередні дані ЦІЛІ: показуємо їх
     і банер, а не стираємо екран заради «не вдалося». */
  const banner = (data.loadError ? bannerHTML(t("thLoadErr", data.loadError)) : "")
    + (err ? bannerHTML(t("thTeamErr", err), stale ? t("thStale", stale) : "") : "")
    + trackerBanner(team, data);
  /* Порожній простір без інтеграцій — не «порожня видача»: скидати нічого, і кнопка
     «Скинути фільтри» вела б у нікуди. Замість неї — шлях до першої задачі. */
  const empty = noIntegrations(data) && !src.length
    ? `<div class="th-empty th-empty--space"><b>${esc(t("spaceEmpty"))}</b>`
      + `${esc(t("spaceEmptyAgent", data.space.name))}`
      + `<div class="th-empty-act">${newTaskBtn()}</div></div>`
    : `<div class="th-empty"><b>${esc(t("thEmpty"))}</b>${esc(t("thEmptyHint"))} `
      + `<button class="th-lnk" data-th="reset">${esc(t("thReset"))}</button></div>`;
  const grid = err && !src.length ? ""
    : `<div class="th-grid" id="th-grid" role="group" aria-label="${esc(t("thGridLabel"))}">`
      + `${list.map((x) => cardHTML(x, ui, data.current)).join("") || empty}</div>`;
  return chipsHTML(ui, data, src, err && !src.length ? 0 : list.length) + banner + grid;
}

/** Повний екран. Вкладки й поле пошуку є завжди — навіть поки дані вантажаться:
 *  фокус на пошук ставиться одразу при відкритті, а не після відповіді. */
export function homeHTML(ui, data) {
  ui = withTab(ui, data);
  const team = ui.tab === "team";
  const isReady = ready(data);
  const nMine = isReady ? data.mine.length : "—";
  const rows = isReady ? (data.team?.rows || []) : [];
  const nTeam = !isReady || (data.team?.error && !rows.length) ? "—" : rows.length;
  const tab = (k, label) => `<button class="th-tab${(ui.tab === k) ? " th-tab--on" : ""}" role="tab"`
    + ` aria-selected="${ui.tab === k}" data-th="tab" data-v="${k}">${esc(label)}</button>`;
  const sort = effectiveSort(ui);
  const opts = sortsFor(ui.tab).map((k) =>
    `<option value="${k}"${sort === k ? " selected" : ""}>${esc(t(`sort_${k}`))}</option>`).join("");
  /* Кнопки «Підключення» й «Нова задача» живуть у голові лише коли вони є (простір без інтеграцій), обидві в
     обгортці `.th-head-acts`: без них розмітка голови — як була (один `<h1>`), і екран простору з інтеграціями
     (ЛІГА) не змінюється ні байтом. */
  const h1 = `<h1 class="th-h">${esc(data?.space ? t("tasksIn", data.space.name) : t("tasks"))}</h1>`;
  const head = noIntegrations(data)
    ? `<div class="th-head">${h1}<div class="th-head-acts">${connBtn()}${newTaskBtn()}</div></div>` : h1;
  const tabs = tab("mine", t("thTabMine", nMine)) + (hasTeam(data) ? tab("team", t("thTabTeam", nTeam)) : "");
  return `<div class="th-in">
    ${head}
    <div class="th-tabs" role="tablist" aria-label="${esc(t("thTabsLabel"))}">${tabs}</div>
    <div class="th-tools">
      <label class="th-search">${ico("search")}<input id="th-q" type="text" autocomplete="off" spellcheck="false"
        aria-label="${esc(t("thSearchLabel"))}" placeholder="${esc(t(team ? "thSearchTeam" : "thSearchMine"))}"
        value="${esc(ui.q || "")}"><span class="th-slash" aria-hidden="true">/</span></label>
      <select class="th-sel" id="th-sort" aria-label="${esc(t("thSortLabel"))}">${opts}</select>
    </div>
    <div id="th-lower">${homeGridHTML(ui, data)}</div>
  </div>`;
}
