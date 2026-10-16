/**
 * Розмітка смуги — модель на вході, рядок HTML на виході, і нічого крім
 * цього: жодного слухача, жодного звернення до DOM, жоден дропдаун сам себе
 * не відкриває. Причина, чому це важливо саме такою чистою функцією: смугу
 * можна прогнати юніт-тестом за мілісекунди на кожному з 27 імен ключів, які
 * називає `bar-model.js`, і на кожній пастці, яка вже раз спрацювала в
 * прототипі (обрубана кнопка публікації, недосяжне керування виглядом на
 * 1024px) — не запускаючи браузер і не чекаючи кадру рендера.
 *
 * Слухачів немає НАВІТЬ для відкриття дропдаунів: який саме дропдаун
 * відкритий — це `state.openDd`, другий аргумент, — бо це стан UI, а не
 * склад смуги, і `bar-model.js` про нього свідомо нічого не знає (див. його
 * шапку). Прив'язати клік до `data-act`/`data-dd` — робота Task 3
 * (`app.js`), одним делегованим обробником на всю смугу. Тому кожен клас
 * `data-act="…"`/`data-dd="…"` тут — КОНТРАКТ, а не косметика: рядок у ньому
 * мусить дослівно збігатися з `id`, який дав контролу `barModel()`. Розійдись
 * вони бодай на одну літеру — Task 3 не знайде контрол своїм
 * `closest('[data-act]')`, і кнопка не робитиме нічого, а жоден юніт-тест
 * такого розходження не побачить (обидва рядки — просто текст для JS).
 *
 * Ярус, на якому щось ховається (підпис чи цілий контрол), теж НЕ рахує ця
 * функція: ховає контейнерний запит у `styles.css` (`@container
 * (max-width:…)`), а не JS-порівняння з `window.innerWidth`. Роль цього
 * модуля — пришити ПРАВИЛЬНИЙ клас (`lbl-mode`/`lbl-gl`/`view-extra`) до
 * правильного контролу, звіряючись із порогом `TIERS`, який називає модель, —
 * а яку саме ширину вважати вузькою, вирішує CSS. Тому далі немає жодного
 * порівняння з реальним px: немає його й у аргументах цієї функції.
 */

import { TIERS } from "./bar-model.js";
import { LOGO_SVG } from "./logo.js";
import { t } from "./i18n.js";
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { cleanTitle, matches, taskKey } from "./tasks-model.js";
import { spaceColorToken, spaceRows } from "./spaces-model.js";

/** Клас, яким контейнерний запит ховає лише ПІДПИС контролу (іконка лишається).
 *  Значення `labelTier` у моделі — це саме пороги `TIERS.mode`/`TIERS.gl`, а
 *  не довільне число, тому зіставлення тут вичерпне, а не евристичне. */
const lblCls = (labelTier) => {
  if (labelTier === TIERS.gl) return "lbl-gl";
  if (labelTier === TIERS.mode) return "lbl-mode";
  return "";
};

/* ── дропдаун-пункт: та сама розмітка для GitLab і публікації ───────────── */
/* `title`/`sub`/`why`/`val` — ДАНІ: йдуть крізь `esc`. `marks` і `lead` — СИРА
   довірена розмітка, без `esc`: лише те, що збирає цей файл (крапка простору
   `spaceDot`, галочка, крапка стану), — дані користувача сюди не передавати.
   `current` — `aria-current="true"` на «де я зараз» (поточний простір): колір
   `dd-item--on` стан не оголошує, а читач мусить його почути. Без `current`
   розмітка пункту побайтно та сама, що була. */
const ddItem = ({ act, val = "", icon = "", lead = "", title, sub = "", why = "",
  on = false, danger = false, marks = "", cls: extra = "", current = false } = {}) => {
  const cls = `dd-item${on ? " dd-item--on" : ""}${danger ? " dd-item--danger" : ""}`
    + `${extra ? ` ${extra}` : ""}`;
  return `<button class="${cls}" data-act="${esc(act)}" data-val="${esc(val)}"${current ? ' aria-current="true"' : ""}${why ? " disabled" : ""}>
    ${lead || (icon ? ico(icon) : '<span class="ico" style="width:16px"></span>')}
    <span class="dd-body"><span class="dd-t">${esc(title)}</span>
    ${why ? `<span class="dd-why">${esc(why)}</span>` : ""}
    ${sub && !why ? `<span class="dd-sub">${esc(sub)}</span>` : ""}</span>
    ${marks}</button>`;
};

/* ── зона 1: простір, крошки задачі й ітерації ───────────────────────────── */
/* Кольорова крапка простору. Токен проходить `spaceColorToken`: реєстр правлять
   руками, а значення іде в `style` — `esc` не рятує від ін'єкції CSS (лапки
   цілі, а `;position:fixed` — ні). */
const spaceDot = (color) =>
  `<span class="space-dot" style="background:var(--${spaceColorToken(color)})"></span>`;

/**
 * Дропдаун просторів. Перелік — `state.spaces` (масив з `/api/spaces`), поточний —
 * `state.space.id`: ТЕ, чого модель смуги свідомо не несе (як `taskList` для
 * задач) — вона описує склад смуги, а не перелічує сутності. Недоступний простір
 * (`muted`) приглушений, але НЕ вимкнений: перейти в нього й побачити причину
 * (`tasksErrSpaceUnavailable`) — єдиний спосіб її дізнатись, а вимкнений пункт
 * мовчав би. Підпис такого рядка — причина, а не «0 задач»: «0 задач» про
 * простір, якого ми не змогли прочитати, — брехня.
 */
function ddSpaces(state) {
  const rows = spaceRows({ current: state?.space?.id, spaces: state?.spaces });
  const list = rows.map((r) => ddItem({
    act: "space", val: r.id, lead: spaceDot(r.color), title: r.name,
    sub: r.muted ? t("spaceUnavailable") : t("spaceTasks", r.sub.n, r.sub.path),
    on: r.on, current: r.on, cls: r.muted ? "dd-item--muted" : "",
    marks: r.on ? `<span class="dd-marks">${ico("check", 14)}</span>` : "",
  })).join("");
  return `<div class="dd dd--spaces"><div class="dd-head">${esc(t("spaces"))}</div>
    ${list}${list ? '<div class="dd-sep"></div>' : ""}
    ${ddItem({ act: "spacenew", icon: "plus", title: t("spaceNew") })}
    ${ddItem({ act: "spaceedit", icon: "pencil", title: t("spaceEdit") })}</div>`;
}

/* Фішка простору: `data-dd="space"` — делегація смуги відкриває дропдауни за
   `data-dd`, а не за `data-act` (клік тут розкриває перелік, не виконує дію).
   Стоїть ПОЗА `.crumbs`, як палітра: крошки стискаються на вузькому вікні, а
   фішка — «де я» найвищого рівня — не мусить пропадати разом із ними. `title` — повна назва:
   довга обрізається трикрапкою (`.space-name`), а інакше її ніде прочитати. */
function spaceChip(model, state, openDd) {
  const c = model.zone1.find((x) => x.id === "space");
  if (!c) return "";
  const open = openDd === "space";
  return `<div class="ddhost space-h">
    <button class="ctl ctl--out space-chip" data-dd="space" title="${esc(c.label)}"
      aria-expanded="${open}" aria-haspopup="true">
      ${spaceDot(c.color)}<span class="txt space-name">${esc(c.label)}</span>
      ${ico("chevdown", 14, "ico caret")}</button>
    ${open ? ddSpaces(state) : ""}
  </div>`;
}

/**
 * Список задач у дропдауні крошки — одне з речей, що беруться зі `state` в обхід
 * моделі (усі названо в шапці `barHTML` нижче): `state.taskList` і
 * `state.curTaskId`. `bar-model.js` свідомо не знає списку задач — це той
 * самий контракт, що й для `iterLabel`: модель описує СКЛАД смуги, а не
 * перелічує сутності, яких не бачить (список задач приходить з `/api/tasks`,
 * окремого від `/api/task` запиту). Без цього перемикання між задачами
 * лишилось би без жодного контролу в новій смузі — старий `#task-sel`
 * зникав би без заміни (функціональний регрес: 01.09.2026 задач заведено 16).
 */
function crumbTask(model, state, openDd) {
  const task = model.zone1.find((x) => x.id === "task");
  const open = openDd === "task";
  /* Дропдаун = три шари: поле пошуку, СПИСОК (єдине, що прокручується) і
     футер. Прокрутка саме списку, а не всього `.dd`, бо пошук і «Усі задачі»
     мусять лишатися видимими при 30+ задачах — інакше поле, в яке щойно
     набирали, виїхало б нагору разом із прокруткою. */
  const dd = `<div class="dd dd--tasks">
    <label class="dd-search">${ico("search", 14)}
      <input id="task-q" type="text" autocomplete="off" spellcheck="false"
        placeholder="${esc(t("taskSearchPh"))}" value="${esc(state?.taskQuery ?? "")}"
        aria-label="${esc(t("taskSearchPh"))}" role="combobox" aria-autocomplete="list"
        aria-expanded="true" aria-controls="task-list"${activeAttr(state)}></label>
    <div class="dd-list" id="task-list" role="listbox">${taskListHTML(state)}</div>
    <div class="dd-foot">${taskFootHTML(state)}</div>
  </div>`;
  return `<div class="ddhost crumb-h crumb--task">
    <button class="ctl crumb crumb--task" data-dd="task"
      aria-expanded="${open}" aria-haspopup="true">
      ${ico("task")}<span class="txt txt--fix">${esc(task.label)}</span>
      ${ico("chevdown", 14, "ico caret")}</button>
    ${open ? dd : ""}
  </div>`;
}

/**
 * Задачі, що проходять запит: ЄДИНЕ місце, де перелік фільтрується. Модуль
 * пошуку — `matches` з `tasks-model.js` (той самий, що на екрані «Задачі»):
 * друга копія правила «усі слова, без регістру» розійшлась би з першою
 * першого ж разу, коли хтось додасть ще одне шукане поле.
 */
export function visibleTasks(state) {
  return (state?.taskList ?? []).filter((x) => matches(x, state?.taskQuery ?? ""));
}

/**
 * Активний пункт: індекс у ряду «задачі…, футер». Футер — ОСТАННІЙ досяжний
 * (його індекс = кількість задач), тож стрілки доходять до нього, а Enter на
 * ньому відкриває екран «Задачі». Затиск тут, а не в `app.js`: нова видача
 * може бути коротшою за стару, і курсор, що лишився за її межею, не показав
 * би жодного активного пункту — а Enter тоді мовчав би.
 */
export function taskCursorIndex(state) {
  const n = visibleTasks(state).length;
  const c = Number.isFinite(state?.taskCursor) ? state.taskCursor : 0;
  /* Порожня видача: активного пункту НЕМА (-1), доки людина не зайде на футер
     стрілкою. Інакше єдиний пункт — футер — ставав би активним сам, і Enter на
     «Нічого не знайдено» мовчки кидав би її на екран «Задачі». */
  if (n === 0) return c < 0 ? -1 : 0;
  return Math.min(Math.max(c, 0), n);
}

/** `id` пункту за індексом ряду «задачі…, футер» (для `aria-activedescendant`). */
const optId = (i, n) => (i === n ? "task-opt-foot" : `task-opt-${i}`);

/** Атрибут активного пункту для поля пошуку (порожньо, коли активного нема). */
function activeAttr(state) {
  const i = taskCursorIndex(state);
  return i < 0 ? "" : ` aria-activedescendant="${optId(i, visibleTasks(state).length)}"`;
}

/**
 * Підсвітка збігів. ⛔ Порядок: спершу `esc` КОЖНОГО шматка, потім `<mark>`.
 * Навпаки (вставити тег у сирий текст і екранувати все) зробило б теги
 * видимим текстом, а екранувати вже після `innerHTML` неможливо — назва
 * задачі приходить із реєстру, і `<b>` у ній не має стати розміткою.
 * Збіги шукаємо регекспом з прапорцем `i` по ОРИГІНАЛУ, а не по
 * `toLowerCase()` копії: той міг би мати іншу довжину (`İ`) і зсунути зрізи.
 *
 * Експортована, бо ту саму підсвітку потрібно екрану «Задачі»
 * (`tasks-home.js`): друга копія екранування розійшлась би з першою мовчки.
 */
export function mark(text, q) {
  const words = [...new Set(String(q || "").split(/\s+/).filter(Boolean))]
    .sort((a, b) => b.length - a.length)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const src = String(text ?? "");
  if (!words.length) return esc(src);
  const re = new RegExp(words.join("|"), "gi");
  let out = "";
  let at = 0;
  for (const m of src.matchAll(re)) {
    if (!m[0]) continue;
    out += `${esc(src.slice(at, m.index))}<mark>${esc(m[0])}</mark>`;
    at = m.index + m[0].length;
  }
  return out + esc(src.slice(at));
}

/** Список дропдауна задач: заголовок (лише без запиту), пункти або «нічого». */
export function taskListHTML(state) {
  const q = state?.taskQuery ?? "";
  const list = visibleTasks(state);
  const cur = taskCursorIndex(state);
  if (!list.length) {
    return `<div class="dd-note dd-empty">${esc(t("noTasksFound", q))}</div>`;
  }
  const head = q.trim() ? "" : `<div class="dd-head">${esc(t("recentTasks"))}</div>`;
  const items = list.map((x, i) => {
    const on = x.id === state?.curTaskId;
    const key = x.missing
      ? `${mark(taskKey(x), q)} · ${esc(t("folderMissing"))}`
      : mark(taskKey(x), q);
    /* `missing` — НЕ `disabled`: вимкнену кнопку не можна ні клікнути, ні
       вибрати стрілками, і причина «чому не відкривається» лишилась би
       підказкою, яку ніхто не побачить. Пункт живий і каже причину сам. */
    const cls = `dd-item dd-item--task${x.missing ? " dd-item--missing" : ""}`
      + `${i === cur ? " dd-item--cur" : ""}${on ? " dd-item--on" : ""}`;
    /* `aria-current`, а не `aria-selected`: у списку з `aria-activedescendant`
       «вибраний» читач розуміє як «той, на якому стоїть курсор», а поточна
       задача — це «де я зараз», тобто саме `current`. */
    return `<button class="${cls}" data-act="task" data-val="${esc(x.id)}"
      id="${optId(i, list.length)}" role="option"${on ? ' aria-current="true"' : ""}${x.missing ? ' aria-disabled="true"' : ""}>
      ${ico("task")}
      <span class="dd-body"><span class="dd-k">${key}</span>
      <span class="dd-t">${mark(cleanTitle(x), q)}</span></span>
      ${on ? `<span class="dd-marks">${ico("check", 14)}</span>` : ""}</button>`;
  }).join("");
  return head + items;
}

/** Футер: «Усі задачі» (досяжний стрілками — останній) і підказка клавіш. */
export function taskFootHTML(state) {
  const n = visibleTasks(state).length;
  const on = taskCursorIndex(state) === n;
  return `<button class="dd-item dd-item--foot${on ? " dd-item--cur" : ""}" id="task-opt-foot" data-act="home" data-val="">
    ${ico("grid")}<span class="dd-body"><span class="dd-t">${esc(t("allTasks"))}</span></span></button>
    <span class="dd-hint">${esc(t("ddKeysHint"))}</span>`;
}

/* ⛔ Перемикача аудиторії коментарів у цьому дропдауні БІЛЬШЕ НЕМА, і це не
   забуте прибирання — це принцип 6 PRODUCT.md: коментатор окремий продукт,
   оболонка не ставить його контролів у свою смугу. Записано тут, бо саме тут
   його шукатимуть: уся дотеперішня історія цього контролу — це історія
   переїздів ПО СМУЗІ (сегмент → меню «⋯» → дропдаун крошки ітерації), і
   четвертий переїзд усередині смуги був би повторенням тієї самої помилки.

   Куди він пішов: вкладки «Клод»/«Команда» в панелі САМОГО коментатора
   (`audiences` в `CommentLayer.init`, `AUDIENCES_TMPL` у `app/serve.py`).
   Плюс аварійний вихід у ⌘K (`gSet` у `shell-palette.js`) — на випадок, коли
   коментатор не піднявся й вкладок немає разом із ним.

   Чому не «просто прибрали» раніше: він жене `&ch=` в URL рамки, тобто
   зникнення без нового дому = функціональний регрес. Рівно на зворотному
   порядку в Плані B зник вибір ітерації — контрол прибрали, заміна не
   зʼявилась, і менеджер ітерацій втратив основну функцію.

   Два колишні доми смуги, для повноти (обидва провалились ВИМІРОМ, не
   смаком): сегмент у смузі коштував ~180px там, де на 1440 бракує одного
   пікселя; меню «⋯» робило контрол недосяжним на будь-якій ширині понад
   1060px, бо CSS ховає «⋯» — знайдено живим тестом, не оком. */
function crumbIter(model, openDd) {
  const it = model.zone1.find((x) => x.id === "iter");
  if (!it) return "";
  const open = openDd === "iter";
  const marks = `<span class="crumb-marks">
    ${it.pub ? `<span class="dot dot--ok" title="${esc(t("markPreview"))}"></span>` : ""}
    ${it.onGl ? ico("cloud", 13, "ico") : ""}</span>`;
  /* Перелік ітерацій — ПЕРШИМ, перед діями: дропдаун крошки відповідає на
     питання «де я», і перемикання між версіями тут головне, а створення й
     видалення — рідше. Позначки ті самі, що на самій крошці: крапка «у
     превью», хмара «збігається з GitLab» — інакше довелось би відкривати
     кожну, щоб дізнатись, яку бачить колега. */
  const list = (it.items || []).map((x) => ddItem({
    act: "iter", val: x.id, icon: "iter", on: !!x.on,
    title: x.note ? `${x.label} · ${x.note}` : x.label,
    /* Автор — у ПІДПИСІ пункту, а походження («у неї це Іт.3») у `sub`: воно
       відповідає на питання «а це та версія, яку вона показувала?», яке й
       зникало разом із чужим номером. */
    sub: x.author ? (x.origin
      ? t("iterOriginTitle", x.author, String(x.origin.it || "").replace(/^it/, ""))
      : t("iterBy", x.author)) : "",
    /* Тільки `dd-item--foreign`: `crumb--foreign` малює пунктирну рамку,
       спроєктовану для ПІЛЮЛІ крошки, і в рядку переліку вона зайва. */
    cls: x.mine ? "" : "dd-item--foreign",
    marks: `${x.pub ? `<span class="dot dot--ok" title="${esc(t("markPreview"))}"></span>` : ""}`
      + `${x.onGl ? ico("cloud", 13, "ico") : ""}`,
  })).join("");
  const dd = `<div class="dd">
    ${list}${list ? '<div class="dd-sep"></div>' : ""}
    ${ddItem({ act: "newit", icon: "plus", title: t("newIteration"), sub: t("newIterationSub") })}
    ${ddItem({ act: "renit", icon: "pencil", title: t("renameIteration") })}
    ${ddItem({ act: "dupit", icon: "copy", title: t("dupIteration") })}
    <div class="dd-sep"></div>
    ${ddItem({ act: "delit", icon: "trash", title: t("delIteration"), danger: true })}</div>`;
  /* Підпис автора — ще один `txt--soft`, тобто тиснеться разом із приміткою і
     НЕ тисне тег `Іт.N` (межу стереже живий тест «довга примітка тисне на
     примітку, а не на тег ітерації»). Чужа ітерація має видимий клас, а не
     лише `title`: про межу треба дізнатись ДО того, як почав у ній працювати. */
  const who = it.author
    ? `<span class="txt txt--soft">${esc(t("iterBy", it.author))}</span>` : "";
  const foreign = it.mine ? "" : " crumb--foreign";
  /* Пояснення («працювати у своїй») у title ЗАВЖДИ, а походження — додатком.
     Раніше `origin` витісняв пояснення, а він є майже в кожній реальній чужій
     ітерації: пунктирна рамка лишалась без жодного пояснення саме в типовому
     випадку. */
  const foreignTitle = it.mine ? "" : ` title="${esc([
    it.origin ? t("iterOriginTitle", it.author || "",
      String(it.origin.it || "").replace(/^it/, "")) : "",
    t("iterForeign"),
  ].filter(Boolean).join(" — "))}"`;
  return `${ico("chevright", 14, "ico crumb-sep")}
  <div class="ddhost crumb-h crumb--iter">
    <button class="ctl crumb crumb--iter${foreign}" data-dd="iter"${foreignTitle}
      aria-expanded="${open}" aria-haspopup="true">
      ${ico("iter")}<span class="txt txt--fix">${esc(it.label)}</span>
      <span class="txt txt--soft">· ${esc(it.note)}</span>${who}${marks}
      ${ico("chevdown", 14, "ico caret")}</button>
    ${open ? dd : ""}
  </div>`;
}

/* ── зона 2: сегменти «як дивлюсь» ────────────────────────────────────────
   Один вигляд кнопки на всі сегменти (`mode`, `view`): іконка, підпис під
   `lblCls`, і — коли пункт вимкнений — причина ВИДИМА (`.dd-why`), а не лише
   в title. Причина видима навіть тут, усередині сегмента, а не тільки в
   дропдаунах: спека вимагає видиму причину скрізь, де контрол вимкнений, а
   не там, де це зручніше розмітити. */
function seg(model, id, extraCls = "") {
  const c = model.zone2.find((x) => x.id === id);
  if (!c) return "";
  const buttons = c.items.map((sub) => {
    const why = sub.disabled ? t(sub.whyKey) : "";
    return `<button data-act="${id}" data-val="${sub.id}"
      aria-pressed="${sub.id === c.value}"${sub.disabled ? " disabled" : ""}
      title="${esc(t(sub.labelKey))}">${ico(sub.id)}
      <span class="${lblCls(c.labelTier)}">${esc(t(sub.labelKey))}</span>
      ${why ? `<span class="dd-why">${esc(why)}</span>` : ""}</button>`;
  }).join("");
  return `<div class="seg${extraCls}" role="group" data-seg="${id}">${buttons}</div>`;
}

function vpSeg(model) {
  const c = model.zone2.find((x) => x.id === "vp");
  if (!c) return "";
  const buttons = c.items.map((sub) => `<button data-act="vp" data-val="${sub.id}"
    aria-pressed="${sub.id === c.value}"
    title="${esc(t(sub.labelKey))}" aria-label="${esc(t(sub.labelKey))}">${ico(sub.id)}</button>`).join("");
  const custom = c.showCustom ? `<span class="seg-div"></span>
    <input class="vpw" type="number" min="240" max="3840" value="${esc(c.vpw)}"
      placeholder="${esc(t("vpAuto"))}" data-act="vpw"
      aria-label="${esc(t("vpCustom"))}" title="${esc(t("vpCustom"))}">` : "";
  return `<div class="seg seg--icons view-extra" role="group" data-seg="vp">${buttons}${custom}</div>`;
}

function inspectorBtn(model) {
  const c = model.zone2.find((x) => x.id === "inspector");
  if (!c) return "";
  return `<button class="ctl ${c.active ? "ctl--on" : "ctl--out"} view-extra"
    data-act="inspector" aria-pressed="${c.active}" title="${esc(t(c.labelKey))}">
    ${ico("inspect")}<span class="${lblCls(c.labelTier)}">${esc(t(c.labelKey))}</span></button>`;
}

/* «⋯ Вигляд» — не окремий набір контролів, а ті самі, що зникли з бару:
   рівно `vp` та `inspector`, тобто контроли з `tier === TIERS.view`. Порахувати
   це з моделі, а не продублювати список руками, — щоб дропдаун не розійшовся
   зі складом бару, якщо колись зʼявиться третій контрол цього ярусу. */
function ddMore(model, state) {
  const overflow = model.zone2.filter((x) => x.tier === TIERS.view);
  const parts = overflow.map((c) => {
    if (c.items) {
      return c.items.map((sub) => ddItem({
        act: c.id, val: sub.id, icon: sub.id,
        title: t(sub.labelKey), on: sub.id === c.value,
      })).join("");
    }
    return ddItem({ act: c.id, icon: "inspect", title: t(c.labelKey), on: !!c.active });
  }).join("");
  return `<div class="dd dd--right"><div class="dd-head">${esc(t("view"))}</div>${parts}</div>`;
}

function zone2HTML(model, state, openDd) {
  const more = `<div class="ddhost view-more">
    <button class="ctl ctl--icon" data-dd="more" aria-expanded="${openDd === "more"}"
      title="${esc(t("view"))}">${ico("dots")}</button>
    ${openDd === "more" ? ddMore(model, state) : ""}
  </div>`;
  return `${seg(model, "mode")}${seg(model, "view")}${vpSeg(model)}${inspectorBtn(model)}${more}`;
}

/* ── зона 3: GitLab і публікація ──────────────────────────────────────────── */
const GL_DOT = { sync: "ok", ahead: "warn", behind: "bad", off: "off" };

function ddGitlab(model, iterLabel) {
  const c = model.zone3.find((x) => x.id === "gl");
  const parts = c.items.map((sub) => {
    if (sub.id === "glsetup") return ddItem({ act: sub.id, icon: "cloud", title: t(sub.labelKey) });
    if (sub.id === "glhistory") return ddItem({ act: sub.id, icon: "ext", title: t(sub.labelKey) });
    const icon = sub.id === "glpull" ? "down" : "up";
    const why = sub.disabled ? t(sub.whyKey) : "";
    return ddItem({
      act: sub.id, icon, title: t(sub.labelKey, iterLabel),
      sub: sub.subKey ? t(sub.subKey) : "", why,
    });
  }).join("");
  return `<div class="dd dd--right">${parts}</div>`;
}

function zoneGl(model, state, openDd) {
  const c = model.zone3.find((x) => x.id === "gl");
  /* Простір без інтеграцій: модель не віддає GitLab (`bar-model.js`, «Вимикач»).
     Без цієї охорони `c.labelTier` на `undefined` кидав би на першому ж рендері
     такого простору — і вся смуга лишалась би порожньою. */
  if (!c) return "";
  const open = openDd === "gl";
  return `<div class="ddhost">
    <button class="ctl ctl--out" data-dd="gl" aria-expanded="${open}">
      ${ico("cloud")}<span class="${lblCls(c.labelTier)}">${esc(t(c.labelKey))}</span>
      <span class="dot dot--${GL_DOT[c.status] || "off"}"></span>${ico("chevdown", 14, "ico caret")}
    </button>
    ${open ? ddGitlab(model, state.iterLabel) : ""}
  </div>`;
}

/* «В Figma» (T-41) — звичайна кнопка, не дропдаун: дія одна. Вимкнена несе
   причину в `title` (рядка `.dd-why` у кнопки немає) і атрибут `disabled` —
   делегація в `app.js` пропускає рівно `el.disabled`. `aria-busy` на час
   захоплення: і екранному читачу, і живому тесту видно, що клік подіяв. */
function figmaBtn(model) {
  const c = model.zone3.find((x) => x.id === "figma");
  if (!c) return "";
  const title = c.disabled ? t(c.whyKey) : t("toFigmaTitle");
  const label = esc(t(c.labelKey));
  /* Без підпису (`iconOnly`) імʼя кнопки несе `aria-label`: `title` — це
     причина вимкнення, а не назва дії. */
  return `<button class="ctl ctl--out" data-act="figma" title="${esc(title)}"`
    + `${c.iconOnly ? ` aria-label="${label}"` : ""}`
    + `${c.busy ? ' aria-busy="true"' : ""}${c.disabled ? " disabled" : ""}>`
    + `${ico("figma")}${c.iconOnly ? "" : `<span class="${lblCls(c.labelTier)}">${label}</span>`}</button>`;
}

function ddPublish(c) {
  const parts = c.items.map((sub) => {
    if (sub.id === "togglepub") {
      return ddItem({
        act: sub.id, title: t(sub.labelKey),
        marks: `<span class="chk ${sub.on ? "chk--on" : ""}">${ico("check", 12)}</span>`,
      });
    }
    if (sub.id === "teamsnotify") {
      return ddItem({
        act: sub.id, icon: "comment", title: t(sub.labelKey),
        why: sub.disabled ? t(sub.whyKey) : "",
        sub: sub.subKey ? t(sub.subKey, ...(sub.subArgs || [])) : "",
        marks: `<span class="chk ${sub.on ? "chk--on" : ""}">${ico("check", 12)}</span>`,
      });
    }
    if (sub.id === "pubpw") {
      return ddItem({
        act: sub.id, icon: "lock", title: t(sub.labelKey, sub.pw),
        sub: sub.warnKey ? t(sub.warnKey, ...(sub.warnArgs || [])) : t(sub.subKey),
        cls: sub.warnKey ? "dd-item--warn" : "",
      });
    }
    const icon = sub.id === "openpreview" ? "ext" : "link";
    const why = sub.disabled ? t(sub.whyKey) : "";
    /* Підпис «локально» (публікація модулем, `bar-model.js`): ключ і аргументи з моделі, а не склеєний
       там рядок — мову вибирає глядач. Час — уже текст (`app.js`, відносний: «5 хв тому»), не сирий ISO. */
    const subText = sub.subKey ? t(sub.subKey, ...(sub.subArgs || [])) : "";
    return ddItem({ act: sub.id, icon, title: t(sub.labelKey), why, sub: subText });
  }).join("");
  /* Застереження про гейт — БЕЗ `esc`, і це свідомо: рядок наш, зі словника, і
     несе один `<b>`. Той самий виняток, що вже діє для підписів із розміткою;
     дані користувача сюди не потрапляють узагалі. Лише для ЛІГА: воно про ЗОВНІШНЄ посилання, яке
     роздають менеджеру, а локальну публікацію модуля віддає цей самий канвас, і «посилання фактично
     публічне» там було б чужою тривогою. */
  /* Застереження модуля «за адресою» (Vercel; `notes` з `bar-model.js`) — того самого `.dd-note`, але з модифікатором за
     `id` (`public`/`stale`): `class="dd-note"` дослівно лишається лише ЛІГА-шному. Текст зі словника — з `esc` усе одно. У ЛІГА
     й у модуля «у теку» `notes` порожній — розмітка тоді та сама, що була, байт у байт. */
  const notes = (c.notes || []).map((n) => `<div class="dd-note dd-note--${n.id}">${esc(t(n.key))}</div>`).join("");
  return `<div class="dd dd--right">${parts}`
    + `${c.legacy ? `<div class="dd-note">${t("pubGateTruth")}</div>` : ""}${notes}</div>`;
}

function zonePublish(c, openDd) {
  if (!c) return ""; // простір без інтеграцій: публікації в моделі нема (див. `zoneGl`)
  const open = openDd === "pub";
  return `<div class="ddhost">
    <div class="split ${c.published ? "" : "split--ghost"}">
      <button class="split-main" data-act="publish" title="${esc(t(c.labelKey))}">
        ${ico(c.icon)}<span class="lbl-pub">${esc(t(c.labelKey))}</span>
      </button>
      <button class="split-more" data-dd="pub" aria-expanded="${open}"
        aria-label="${esc(t("publishing"))}">${ico("chevdown", 14)}</button>
    </div>
    ${open ? ddPublish(c) : ""}
  </div>`;
}

/**
 * Розмітка всієї смуги. `model` — вихід `barModel()` (склад і причини),
 * `state` — вихідний стан екрана: із нього беруться речі, яких модель свідомо
 * не несе — `state.openDd` (який дропдаун розкритий), `state.iterLabel`
 * (підпис поточної ітерації для «Надіслати Іт.3 на GitLab» — текст, що
 * складає вже DOM-шар, не модель, за її ж контрактом `t()`-виклику лише тут),
 * `state.taskList`/`state.curTaskId` (перелік задач для дропдауна крошки —
 * модель бачить лише ПОТОЧНУ задачу, список приходить окремим запитом),
 * `state.space`/`state.spaces` (ПОТОЧНИЙ простір і перелік для дропдауна
 * фішки: `space` — обʼєкт `{id, name, color, integrations}` з `/api/task`,
 * `spaces` — масив `/api/spaces`; без `space` фішки нема зовсім).
 *
 * ⛔ `state.commentMode` тут БІЛЬШЕ НЕ читається: смуга нічого не знає про
 * аудиторію коментарів (принцип 6 PRODUCT.md, коментар над `crumbIter`).
 * `barState()` його все ще віддає — але для ⌘K (`paletteState()` в
 * `app.js`), не для смуги.
 */
/* Двері в палітру ⌘K. Іконка лишається на будь-якій ширині, підпис-акорд
   зникає разом із рештою підписів на 1180 (`labelTier` у моделі): без
   підпису кнопка ще працює, без іконки її не було б видно взагалі.

   `aria-keyshortcuts` — не косметика: підпис «⌘K» бачить око, а екранний
   читач мусить дізнатись про акорд окремо, бо для нього це просто два
   символи в тексті кнопки. */
function paletteBtn(model) {
  const c = model.zone1.find((x) => x.id === "palette");
  if (!c) return "";
  return `<div class="pal-open"><button class="ctl ctl--icon" data-act="palette"
    title="${esc(t("paletteOpenTitle"))}" aria-keyshortcuts="Meta+K Control+K"
    >${ico("search")}<span class="lbl-pal">${esc(t("paletteOpen"))}</span></button></div>`;
}

/* Логотип — вхід на екран «Задачі». Імʼя несе `aria-label`: усередині лише
   декоративний SVG. `ctl--on` — «ми зараз там»; `aria-current="page"` дублює
   це для читача, бо колір сам по собі стану не оголошує. НЕ `aria-pressed`:
   повторний клік не вимикає екран, тож це не перемикач. */
function homeBtn(model) {
  const c = model.zone1.find((x) => x.id === "home");
  if (!c) return "";
  const name = esc(t("allTasks"));
  return `<button class="ctl ctl--icon logo-btn${c.on ? " ctl--on" : ""}" data-act="home"
    aria-label="${name}" title="${name}"${c.on ? ' aria-current="page"' : ""}>${LOGO_SVG}</button>`;
}

/* Голова зони 1 екрана «Задачі»: плоска крошка «Задачі» (нерухома — це «де я»,
   не перемикач) і шлях назад до задачі, з якої прийшли. Склад вирішила модель
   (`homeOpen`), тут лише малюнок. */
function homeCrumbs(model) {
  const back = model.zone1.find((x) => x.id === "back");
  const crumb = `<span class="crumb crumb--flat">${ico("grid")}`
    + `<span class="txt">${esc(t("tasks"))}</span></span>`;
  if (!back) return `<div class="crumbs">${crumb}</div>`;
  const why = esc(t("backToTask", back.label));
  return `<div class="crumbs">${crumb}</div>
    <button class="ctl ctl--out" data-act="back" title="${why}" aria-label="${why}">`
    + `${ico("chevleft")}<span class="txt txt--fix">${esc(back.label)}</span></button>`;
}

export function barHTML(model, state) {
  const openDd = state?.openDd ?? null;
  const home = model.zone1.some((x) => x.id === "crumb-tasks");
  const zone1 = home
    ? `${homeBtn(model)}${paletteBtn(model)}${spaceChip(model, state, openDd)}${homeCrumbs(model)}`
    : `${homeBtn(model)}${paletteBtn(model)}${spaceChip(model, state, openDd)}<div class="crumbs">`
      + `${crumbTask(model, state, openDd)}${crumbIter(model, openDd)}</div>`;
  /* Зони 2 і 3 екрана «Задачі» порожні в МОДЕЛІ — не малюємо їхніх контролів,
     але самі вузли лишаються (грид смуги на них тримається). */
  const zone2 = home ? "" : zone2HTML(model, state, openDd);
  const publish = model.zone3.find((x) => x.id === "publish");
  const zone3 = home ? ""
    : `${figmaBtn(model)}${zoneGl(model, state ?? {}, openDd)}${zonePublish(publish, openDd)}`;

  const errbar = model.error
    ? `<div class="errbar">${ico("warn")}<span>${esc(t(model.error.whyKey))}</span>
      <button class="ctl ctl--out" data-act="retry">${ico("refresh")}${esc(t("retry"))}</button></div>`
    : "";

  return `<div class="bar">
    <div class="zone zone-1">${zone1}</div>
    <div class="zone zone-2">${zone2}</div>
    <div class="zone zone-3">${zone3}</div>
  </div>
  ${errbar}`;
}
