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
 *          `ui.edit` (етап Д, 0.30.0) — тимчасовий стан екрана з `app.js`:
 *          `{ newForm: bool, ren: id|null, ask: {id, kind: 'del'|'purge', claude: bool}|null, trash: bool }`.
 *          Відсутній `ui.edit` = усе вимкнено (розмітка як без етапу Д, плюс картка «+» і «⋯»).
 *   data = відповідь `/api/tasks-overview` (`{current, mine, team:{rows, error,
 *          fetchedAt, rowsAt}|null, space:{name, capabilities}|null}`), АБО
 *          `null`/`{loading:true[, space]}` до відповіді, АБО `{failed: "причина"}`,
 *          коли запит не вдався. `data.trash` (етап Д) — рядки кошика `{id, title, jira, tags, at, thumb}`; нема → `[]`.
 *
 * Простори (Deai 1.0, етап 1): `data.space` дає заголовок «Задачі · <простір>».
 * Простір без дашборда команди (`capabilities.dashboard == null`) не має команди —
 * `team: null`: вкладки «Команда» нема, а збережена в UI вкладка `team`
 * читається як `mine` (`effectiveTab`; без цього екран малював би порожній
 * список під вкладкою, якої нема), а першою клітинкою сітки стає картка «+» («Нова задача», етап Д) — єдиний
 * спосіб завести задачу не з реєстру Jira. Порожній такий простір показує не
 * «Нічого не знайдено» (фільтрувати нема що), а під сіткою — пораду попросити агента.
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
import { confirmHTML } from "./inline-confirm.js";
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

/** Простір без дашборда команди: відповідь знає `capabilities` і роль `dashboard` у ній порожня (4d-4c; було `integrations === false`). */
const noDashboard = (data) => {
  const caps = data?.space?.capabilities;
  return !!(caps && typeof caps === "object" && "dashboard" in caps && caps.dashboard == null);
};

/** Чи є в екрана вкладка «Команда». Є дані — рішає `team` (`null` або ключа нема =
 *  дашборда нема; обʼєкт, навіть із помилкою, = є). Даних ще нема — вкладка
 *  стоїть, як і раніше «поки вантажиться», АЛЕ відомий простір без дашборда
 *  ховає її вже зараз, щоб вона не мигала на мить завантаження. */
const hasTeam = (data) => (ready(data) ? data.team != null : !noDashboard(data));

/** Вкладка, яка справді малюється: збережена `team` без вкладки «Команда» — `mine`.
 *  Експортована: `app.js` вибирає за нею ще й пошук/сортування/повторний запит. */
export const effectiveTab = (ui, data) => (ui.tab === "team" && !hasTeam(data) ? "mine" : ui.tab);

/** `ui` із вже виправленою вкладкою (копія, лише коли довелось виправити). */
const withTab = (ui, data) => {
  const tab = effectiveTab(ui, data);
  return tab === ui.tab ? ui : { ...ui, tab };
};

/** Етап Д: «Нова задача» — перша клітинка сітки (`data-th="newtask"`). Форма відкрита — порожній слот: живу `<form>` у нього
 *  вставляє `app.js` (поля переживають перемальовку сітки — набраного не губимо). */
export function newTaskCardHTML(ui) {
  return ui.edit?.newForm
    ? '<div class="th-card th-card--form" id="th-new-slot"></div>'
    : `<button class="th-card th-card--new" data-th="newtask" aria-label="${esc(t("newTask"))}">`
      + `<span class="th-new-ic">${ico("plus", 20)}</span><span>${esc(t("newTask"))}</span></button>`;
}

/** «Підключення» (етап 3a): у голові простору без інтеграцій (`data-th="conn"`). */
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

/** Дія в кінці рядка бейджів: «мої» — лише посилання на опубліковане превʼю (мітки, перейменування й видалення — в меню «⋯»);
 *  команда — «Відкрити в канвасі» для своїх, інакше превʼю. */
function actionHTML(x, team) {
  const link = (href, title) => {
    const u = safeUrl(href);
    return u ? `<a class="th-lnk" href="${esc(u)}" target="_blank" rel="noopener"`
      + `${title ? ` title="${esc(title)}"` : ""}>${ico("ext")}${esc(t("thPreview"))}</a>` : "";
  };
  if (!team) return link(x.published, t("thPreviewTitle"));
  if (x.mine) {
    return `<button class="th-lnk" data-th="open" data-id="${esc(x.id)}">`
      + `${ico("task")}${esc(t("thOpenCanvas"))}</button>`;
  }
  return link(x.preview, t("thPreviewTitle"));
}

/** Етап Д: картка задачі з кошика. Кадр знебарвлений (CSS), «видалено <коли>», «Повернути», «⋯» → меню кошика. */
export function trashCardHTML(x, ui) {
  const edit = ui.edit || {};
  const asking = !!(edit.ask && edit.ask.id === x.id && edit.ask.kind === "purge");
  const src = safeThumb(x.thumb);
  const thumb = src ? `<img class="th-img" src="${esc(src)}" alt="" loading="lazy" draggable="false">`
    : `<div class="th-none">${ico("camera")}${esc(t("thNoShot"))}</div>`;
  const ms = Date.parse(x.at);
  const when = Number.isFinite(ms) ? (() => { const r = relTime(ms, ui.now); return t(r.key, r.n); })() : "";
  const meta = [esc((x.tags || []).join(", ")), when ? esc(t("thDeleted", when)) : ""].filter(Boolean).join(" · ");
  const more = asking ? "" : `<button class="th-more" data-th="menu" data-id="${esc(x.id)}" data-trash="1" aria-haspopup="menu"`
    + ` aria-expanded="false" aria-label="${esc(t("thMenuAria", x.title || x.id))}" title="${esc(t("thMenuTitle"))}">${ico("dots")}</button>`;
  const tail = asking
    ? confirmHTML({ title: t("taskPurgeAsk", x.title || x.id), no: t("askCancel"), yes: t("taskPurge"),
      noAttrs: `data-th="askno" data-id="${esc(x.id)}"`, yesAttrs: `data-th="askyes" data-id="${esc(x.id)}"` })
    : `<div class="th-badges"><button class="th-lnk" data-th="restore" data-id="${esc(x.id)}">${ico("refresh")}${esc(t("taskRestore"))}</button></div>`;
  return `<div class="th-card th-card--trash${asking ? " th-card--ask" : ""}" tabindex="0" role="group" aria-label="${esc(x.id)} — ${esc(x.title || x.id)}" data-id="${esc(x.id)}" data-trash="1">`
    + `<div class="th-thumb">${thumb}${more}</div><div class="th-cbody">`
    + `<div class="th-krow"><span class="th-key">${esc(x.id)}</span></div>`
    + `<div class="th-ttl">${esc(x.title || x.id)}</div><div class="th-meta">${meta}</div>${tail}</div></div>`;
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
  /* Етап Д: питання «Видалити?» стоїть на місці бейджів, картка тоді не відкривається і без «⋯»; поле назви — замість `.th-ttl`. */
  const edit = ui.edit || {};
  const asking = !team && edit.ask && edit.ask.id === x.id ? edit.ask : null;
  const more = team || asking ? ""
    : `<button class="th-more" data-th="menu" data-id="${esc(x.id)}" aria-haspopup="menu" aria-expanded="false"`
      + ` aria-label="${esc(t("thMenuAria", cleanTitle(x)))}" title="${esc(t("thMenuTitle"))}">${ico("dots")}</button>`;
  const ttl = !team && edit.ren === x.id
    ? `<input id="th-ren" class="th-ren" type="text" value="${esc(cleanTitle(x))}" aria-label="${esc(t("newTaskTitle"))}"`
      + ` autocomplete="off" spellcheck="false">`
    : `<div class="th-ttl">${mark(cleanTitle(x), q)}</div>`;
  const tail = asking
    ? confirmHTML({
      title: asking.claude ? t("taskDelAskClaude", cleanTitle(x)) : t("taskDelAsk", cleanTitle(x)),
      no: t("askCancel"), yes: t("taskDelete"),
      noAttrs: `data-th="askno" data-id="${esc(x.id)}"`, yesAttrs: `data-th="askyes" data-id="${esc(x.id)}"`,
    })
    : `<div class="th-badges">${status}${comments}${gone}${actionHTML(x, team)}</div>`;
  /* Фаза И (Р1): ідентифікатора на картці немає. Ключ видно лише коли пошук збігся з ним, а не з назвою. Рядок стоїть
     завжди (мін. висота в CSS): назви карток на одній лінії. */
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const titleL = cleanTitle(x).toLowerCase();
  const keyL = taskKey(x).toLowerCase();
  const keyHit = words.some((w) => keyL.includes(w) && !titleL.includes(w));
  const krow = (keyHit ? `<span class="th-key">${mark(taskKey(x), q)}</span>` : "")
    + (isCur ? `<span class="th-curb">${keyHit ? "· " : ""}${esc(t("thCurrent"))}</span>` : "");
  const cls = `th-card${isCur ? " th-card--cur" : ""}${missing ? " th-card--miss" : ""}${asking ? " th-card--ask" : ""}`;
  const renaming = !team && edit.ren === x.id;
  const open = actionable && !asking && !renaming;
  /* Група без імені в фокусі нічого не каже скрінрідеру: питання й перейменування називаємо «ключ — назва». */
  const name = !open && !team ? ` aria-label="${esc(cleanTitle(x))}"` : "";
  return `<div class="${cls}" tabindex="0" role="${open ? "button" : "group"}"${name}`
    + `${open ? ` data-th="open"` : ""} data-id="${esc(x.id)}"${missing ? ' aria-disabled="true"' : ""}>
    <div class="th-thumb">${thumb}${more}</div>
    <div class="th-cbody">
      <div class="th-krow">${krow}</div>
      ${ttl}
      <div class="th-meta">${parts.filter(Boolean).join(" · ")}</div>
      ${tail}
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
function chipsHTML(ui, data, src, shown, inTrash = false) {
  const c = statusCounts(src, ui.q);
  const st = (k, label) => `<button class="th-chip${!inTrash && ui.status === k ? " th-chip--on" : ""}"`
    + ` data-th="status" data-v="${k}" aria-pressed="${!inTrash && ui.status === k}">${esc(label)}</button>`;
  const team = ui.tab === "team";
  let extra;
  if (inTrash) {
    extra = "";                             // у вигляді кошика мітки й дизайнери не фільтрують
  } else if (team) {
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
  /* Етап Д: чип «Кошик · N» — лише з непорожнім кошиком і не на «Команді». */
  const trashN = team ? 0 : (data.trash || []).length;
  const trashChip = trashN ? `${extra ? "" : '<span class="th-gap"></span>'}<button class="th-chip${inTrash ? " th-chip--on" : ""}" data-th="trash"`
    + ` aria-pressed="${inTrash}">${ico("trash")}${esc(t("thTrash", trashN))}</button>` : "";
  return `<div class="th-chips" role="group" aria-label="${esc(t("thFiltersLabel"))}">`
    + st("active", t("thStActive", c.active)) + st("done", t("thStDone", c.done)) + st("all", t("thStAll", c.all))
    + (extra ? `<span class="th-gap"></span>${extra}` : "") + trashChip
    + `<span class="th-count">${esc(t("thShown", shown, inTrash ? shown : src.length))}</span></div>`;
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
  /* Етап Д: вигляд кошика — лише на «Моїх» і лише з непорожнім кошиком (порожній кошик вигляду не має). */
  const trash = data.trash || [];
  const inTrash = !team && !!ui.edit?.trash && trash.length > 0;
  const list = inTrash ? trash : sortTasks(filterTasks(src, {
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
  /* Порожній простір без дашборда — не «порожня видача»: скидати нічого, і кнопка «Скинути фільтри» вела б у нікуди.
     Шлях до першої задачі — картка «+» першою клітинкою сітки; під сіткою лише порада попросити агента. */
  const spaceEmpty = noDashboard(data) && !src.length && !inTrash;
  const empty = spaceEmpty ? ""
    : `<div class="th-empty"><b>${esc(t("thEmpty"))}</b>${esc(t("thEmptyHint"))} `
      + `<button class="th-lnk" data-th="reset">${esc(t("thReset"))}</button></div>`;
  const plus = !team && noDashboard(data) && !inTrash ? newTaskCardHTML(ui) : "";
  const cardsHtml = inTrash ? list.map((x) => trashCardHTML(x, ui)).join("")
    : list.map((x) => cardHTML(x, ui, data.current)).join("");
  const below = spaceEmpty
    ? `<div class="th-empty th-empty--space"><b>${esc(t("spaceEmpty"))}</b>${esc(t("spaceEmptyAgent", data.space.name))}</div>` : "";
  const grid = err && !src.length ? ""
    : `<div class="th-grid" id="th-grid" role="group" aria-label="${esc(t("thGridLabel"))}">`
      + `${plus}${cardsHtml || empty}</div>${below}`;
  return chipsHTML(ui, data, src, err && !src.length ? 0 : list.length, inTrash) + banner + grid;
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
  /* Кнопка «Підключення» живе в голові лише коли простір без дашборда, в обгортці `.th-head-acts`: без неї розмітка
     голови — як була (один `<h1>`), і екран простору з дашбордом (ЛІГА) не змінюється ні байтом. «Нова задача» — картка
     «+» у сітці (етап Д), не кнопка голови. */
  const h1 = `<h1 class="th-h">${esc(data?.space ? t("tasksIn", data.space.name) : t("tasks"))}</h1>`;
  const head = noDashboard(data)
    ? `<div class="th-head">${h1}<div class="th-head-acts">${connBtn()}</div></div>` : h1;
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
