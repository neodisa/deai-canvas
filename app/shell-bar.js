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
import { t } from "./i18n.js";
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { confirmHTML } from "./inline-confirm.js";
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
const ddItem = ({ act, val = "", icon = "", lead = "", title, sub = "", why = "", tip = "",
  on = false, danger = false, marks = "", cls: extra = "", current = false } = {}) => {
  const cls = `dd-item${on ? " dd-item--on" : ""}${danger ? " dd-item--danger" : ""}`
    + `${extra ? ` ${extra}` : ""}`;
  return `<button class="${cls}" data-act="${esc(act)}" data-val="${esc(val)}"${current ? ' aria-current="true"' : ""}${why || tip ? " disabled" : ""}${tip ? ` title="${esc(tip)}"` : ""}>
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
 *
 * «Підключення…» (етап 3a) — вхід на екран підключень поточного простору. На самій
 * сторінці `conn` (`state.homePage`) пункту нема: він нічого б не робив, а ⌘K на тій
 * сторінці свій `space-conn` теж ховає. Лише рівно `"conn"`: на «Задачах», у смузі
 * задачі й поза оверлеєм (`homePage` — `null`) пункт є.
 */
function ddSpaces(state) {
  const onConn = state?.homePage === "conn";
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
    ${ddItem({ act: "spaceedit", icon: "pencil", title: t("spaceEdit") })}
    ${onConn ? "" : ddItem({ act: "conn", icon: "sliders", title: t("cnOpen") })}</div>`;
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

/* ⛔ Перемикача аудиторії коментарів у цьому дропдауні БІЛЬШЕ НЕМА, і це не
   забуте прибирання — це принцип 6 PRODUCT.md: коментатор окремий продукт,
   оболонка не ставить його контролів у свою смугу. Записано тут, бо саме тут
   його шукатимуть: уся дотеперішня історія цього контролу — це історія
   переїздів ПО СМУЗІ (сегмент → меню «⋯» → дропдаун крошки ітерації), і
   четвертий переїзд усередині смуги був би повторенням тієї самої помилки.

   Куди він пішов: після 0.27.0 перемикача каналу нема взагалі. Рамка живе
   в комбінованому режимі (Claude + команда в одній панелі коментарів
   оболонки), адресата обирають у самому коментарі. Аварійного виходу в
   локальний канал у ⌘K теж більше нема. Історія контролу — історія переїздів
   ПО СМУЗІ, тож повертати його в смугу було б повторенням тієї самої помилки.

   Два колишні доми смуги, для повноти (обидва провалились ВИМІРОМ, не
   смаком): сегмент у смузі коштував ~180px там, де на 1440 бракує одного
   пікселя; меню «⋯» робило контрол недосяжним на будь-якій ширині понад
   1060px, бо CSS ховає «⋯» — знайдено живим тестом, не оком. */
/** Ініціали для кружка чужої ітерації: перші літери двох перших слів. */
export function initials(name) {
  const w = String(name || "").trim().split(/\s+/).filter(Boolean);
  return w.slice(0, 2).map((x) => [...x][0].toUpperCase()).join("") || "?";
}

/* Фаза И (Р3–Р6). `ui` — `{menu, ren, del}` (id ітерації або null) зі стану смуги; `null` — нічого не розкрито. Рядок — або
   звичайний (вибір + «⋯»), або поле назви, або питання про видалення: на місці рядка, не поверх. */
function iterRow(x, ui) {
  const title = x.note ? `${x.label} · ${x.note}` : x.label;
  if (ui?.ren === x.id) {
    return `<div class="it-ren">${ico("iter")}<b>${esc(x.label)} ·</b>`
      + `<input id="it-ren-in" class="it-ren-in" type="text" maxlength="40" value="${esc(x.note)}" data-val="${esc(x.id)}"`
      + ` aria-label="${esc(t("iterRenameAria", x.label))}" autocomplete="off" spellcheck="false"></div>`;
  }
  if (ui?.del === x.id) {
    return `<div class="it-cfm">${confirmHTML({ title: t("cfmDelIter", title), yes: t("menuDeleteYes"), no: t("cfmNo"),
      yesAttrs: `data-act="itdelyes" data-val="${esc(x.id)}"`, noAttrs: 'data-act="itdelno"' })}</div>`;
  }
  /* Автор — лише в підказці кружка (чужа ітерація): під рядком підпису нема; походження («в автора це Іт.3») відповідає на
     питання «чи це та версія, яку вона показувала?», пояснення «працювати у своїй» — про межу. */
  const tip = [x.origin ? t("iterOriginTitle", x.author || "", String(x.origin.it || "").replace(/^it/, "")) : x.author, t("iterForeign")]
    .filter(Boolean).join(" — ");
  const who = x.mine ? "" : `<span class="it-who" title="${esc(tip)}">${esc(initials(x.author))}</span>`;
  /* Позначки ті самі, що на крошці: крапка «у превʼю», хмара «збігається з GitLab». */
  const marks = `${x.pub ? `<span class="dot dot--ok" title="${esc(t("markPreview"))}"></span>` : ""}${x.onGl ? ico("cloud", 13, "ico") : ""}`;
  return `<div class="it-row" data-it="${esc(x.id)}">`
    + `<button class="dd-item${x.on ? " dd-item--on" : ""}${x.mine ? "" : " dd-item--foreign"}" data-act="iter" data-val="${esc(x.id)}">`
    + `${ico("iter")}<span class="dd-body"><span class="dd-t">${esc(title)}</span></span><span class="dd-marks">${marks}${who}</span></button>`
    + `<button class="it-more" data-act="itmenu" data-val="${esc(x.id)}" aria-haspopup="menu" aria-expanded="${ui?.menu === x.id}"`
    + ` aria-label="${esc(t("iterMenuAria", title))}" title="${esc(t("iterMenuTitle"))}">${ico("dots")}</button></div>`;
}

/* Меню «⋯» рядка: усе діє на ЦЮ ітерацію (не на поточну). Позицію (праворуч від переліку, на висоті рядка) ставить `paintBar`. */
function iterMenu(x, count, modActs, overview = false) {
  const id = esc(x.id);
  return `<div class="dd dd--itmenu" role="menu" data-for="${id}">
    ${ddItem({ act: "itren", val: x.id, icon: "pencil", title: t("iterRename"), marks: "<kbd>F2</kbd>" })}
    ${ddItem({ act: "itdup", val: x.id, icon: "copy", title: t("dupIteration") })}
    ${overview ? "" : ddItem({ act: "ithist", val: x.id, icon: "refresh", title: t("iterHistory") })}
    ${modActs.length ? `<div class="dd-sep"></div>${modActs.map((a) => ddItem({ act: "itmodact", val: `${x.id}::${a.key}`, icon: "puzzle", title: a.label })).join("")}` : ""}
    <div class="dd-sep"></div>
    ${ddItem({ act: "itdel", val: x.id, icon: "trash", title: t("iterDelete"), danger: true, tip: count <= 1 ? t("iterDelOnly") : "" })}
  </div>`;
}

/* «Видалені» (патч після 0.36.0): скільки лишилось до автоочищення кошика — від `expiresAt` до `nowMs`. Чиста (тести без DOM).
   ≥ доби — дні, округлені до найближчих (свіжовидалена — «ще 7 дн.»); < доби — години вниз; < години, минуле чи зіпсоване —
   «менше години». `soon` — колір попередження. */
export function trashLeft(expiresAt, nowMs = Date.now()) {
  const ms = Date.parse(expiresAt) - nowMs;
  const H = 3600e3;
  const D = 24 * H;
  if (!(ms >= H)) return { text: t("trashLeftUnderHour"), soon: true };
  if (ms < D) return { text: t("trashLeftHours", Math.floor(ms / H)), soon: true };
  return { text: t("trashLeftDays", Math.round(ms / D)), soon: false };
}

const pad2 = (n) => String(n).padStart(2, "0");
/** Локальні дата й час видалення для підказки рядка (`DD.MM.YYYY`, `HH:MM`); зіпсоване — `null`. */
function deletedWhen(at) {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return null;
  return [`${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`, `${pad2(d.getHours())}:${pad2(d.getMinutes())}`];
}

function goneRow(x, nowMs) {
  const title = x.note ? `${x.label} · ${x.note}` : x.label;
  const when = deletedWhen(x.deletedAt);
  const tip = when ? t("trashDeletedAt", title, when[0], when[1]) : title;
  const left = trashLeft(x.expiresAt, nowMs);
  return `<div class="it-gone" title="${esc(tip)}">${ico("iter")}`
    + `<span class="it-gone-b"><span class="it-gone-t">${esc(title)}</span>`
    + `<span class="it-gone-s${left.soon ? " it-gone-s--soon" : ""}">${esc(left.text)}</span></span>`
    + `<button type="button" class="it-back" data-act="itback" data-val="${esc(x.trash)}"`
    + ` aria-label="${esc(t("iterRestoreAria", title))}">${esc(t("iterRestore"))}</button></div>`;
}

/* Розділ стоїть найнижче (під «Новою ітерацією»): дія рідкісна. Порожній кошик — рядок порожній, щоб розмітка дропдауна без кошика
   лишилась байт-у-байт такою, як була. */
function goneSection(trash, gone, nowMs) {
  if (!trash.length) return "";
  return `<div class="dd-sep"></div>`
    + `<button class="dd-item it-gone-h" data-act="itgone" aria-expanded="${gone}">${ico("trash")}`
    + `<span class="dd-body"><span class="dd-t">${esc(t("iterTrash"))}</span></span>`
    + `<span class="dd-marks">${trash.length}${ico("chevright", 14, "ico caret")}</span></button>`
    + (gone ? `<div class="it-gone-list">${trash.map((x) => goneRow(x, nowMs)).join("")}</div>` : "");
}

function crumbIter(model, openDd, ui = null, modActs = [], overview = false, gone = false, nowMs = Date.now()) {
  const it = model.zone1.find((x) => x.id === "iter");
  if (!it) return "";
  const open = openDd === "iter";
  const items = it.items || [];
  const marks = `<span class="crumb-marks">
    ${it.pub ? `<span class="dot dot--ok" title="${esc(t("markPreview"))}"></span>` : ""}
    ${it.onGl ? ico("cloud", 13, "ico") : ""}</span>`;
  /* Перелік ітерацій — перше, що бачить людина в дропдауні: він відповідає на «де я», а створення — рідше («Нова ітерація»
     лише внизу). Дії над ітерацією — у меню рядка, а не тут. */
  const menuFor = ui?.menu ? items.find((x) => x.id === ui.menu) : null;
  const dd = open ? `<div class="dd dd--iters">
    ${items.map((x) => iterRow(x, ui)).join("")}${items.length ? '<div class="dd-sep"></div>' : ""}
    ${ddItem({ act: "newit", icon: "plus", title: t("newIteration") })}${goneSection(it.trash || [], gone, nowMs)}
  </div>${menuFor ? iterMenu(menuFor, items.length, modActs, overview) : ""}` : "";
  /* Імені автора в крошці нема (власник: лише ітерація та її назва); чужа ітерація — видимий клас `crumb--foreign`
     і title-підказка: про межу треба дізнатись ДО того, як почав у ній працювати. Автор — у підказці кружка чужого рядка переліку. */
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
  /* Роздільника перед крошкою нема: вона перша в зоні 1 (раніше його ставили після крошки задачі). */
  return `<div class="ddhost crumb-h crumb--iter">
    <button class="ctl crumb crumb--iter${foreign}" data-dd="iter"${foreignTitle}
      aria-expanded="${open}" aria-haspopup="true">
      ${ico("iter")}<span class="txt txt--fix">${esc(it.label)}</span>
      <span class="txt txt--soft">· ${esc(it.note)}</span>${marks}
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

/* «⋯ Вигляд» — не окремий набір контролів, а ті самі, що зникли з бару:
   лише `vp` (ширини), тобто контроли з `tier === TIERS.view`. Порахувати
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
    return "";
  }).join("");
  return `<div class="dd dd--right"><div class="dd-head">${esc(t("view"))}</div>${parts}</div>`;
}

function zone2HTML(model, state, openDd) {
  const more = `<div class="ddhost view-more">
    <button class="ctl ctl--icon" data-dd="more" aria-expanded="${openDd === "more"}"
      title="${esc(t("view"))}">${ico("dots")}</button>
    ${openDd === "more" ? ddMore(model, state) : ""}
  </div>`;
  return `${seg(model, "mode")}${seg(model, "view")}${vpSeg(model)}${more}`;
}

/* ── зона 3: GitLab і публікація ──────────────────────────────────────────── */
/* Стани без запису тут (`busy` — синк іде, а опит натрапив на лок дзеркала; `error`) малюються сірою крапкою через `|| "off"` у
   `zoneGl`: це не помилка (червоного нема) і не «збігається» (зеленого нема). */
const GL_DOT = { sync: "ok", ahead: "warn", behind: "bad", off: "off" };

function ddGitlab(model, iterLabel) {
  const c = model.zone3.find((x) => x.id === "gl");
  /* Підпис репозиторію (`c.brand`, лише `GitHub`/`Git`) — ОСТАННІМ аргументом текстів, що називають репозиторій: без нього
     (ЛІГА, «GitLab») аргумент не передається, а текст бере типове «GitLab» — розмітка ЛІГИ побайтно та сама. */
  const brandArg = c.brand ? [c.brand] : [];
  const parts = c.items.map((sub) => {
    if (sub.id === "glsetup") return ddItem({ act: sub.id, icon: "cloud", title: t(sub.labelKey) });
    if (sub.id === "glhistory") return ddItem({ act: sub.id, icon: "ext", title: t(sub.labelKey, ...brandArg) });
    const icon = sub.id === "glpull" ? "down" : "up";
    const why = sub.disabled ? t(sub.whyKey) : "";
    return ddItem({
      act: sub.id, icon, title: t(sub.labelKey, iterLabel, ...brandArg),
      sub: sub.subKey ? t(sub.subKey) : "", why,
    });
  }).join("");
  return `<div class="dd dd--right">${parts}</div>`;
}

function zoneGl(model, state, openDd) {
  const c = model.zone3.find((x) => x.id === "gl");
  /* Простір без ролі `vcs`: модель не віддає зону синку (`bar-model.js`, «Вимикач»).
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
    if (sub.id === "modpw") {
      return ddItem({ act: sub.id, icon: "lock", title: t(sub.labelKey), sub: t("frPwSub", t(sub.stateKey)) });
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

/* Голова зони 1 екрана «Задачі»: плоска крошка «Задачі» (нерухома — це «де я»,
   не перемикач). Склад вирішила модель (`homeOpen`), тут лише малюнок. На сторінці «Налаштування» (етап 3a) модель дає
   `crumb-conn` замість `crumb-tasks` — крошка та сама, але з іконкою `sliders`. Сторінка майстра нового простору
   (етап 3b) — `crumb-wiz`: іконка `plus`, «Новий простір»; фішки простору там модель не дає, тож розмітка її і не малює. */
function homeCrumbs(model) {
  const wiz = model.zone1.some((x) => x.id === "crumb-wiz");
  const conn = model.zone1.some((x) => x.id === "crumb-conn");
  const [icon, key] = wiz ? ["plus", "wzCrumb"] : conn ? ["sliders", "cnTitle"] : ["grid", "tasks"];
  /* `crumb--page` — крошка сторінки оверлею без ліміту ширини (див. `.crumb.crumb--page` у styles.css): інакше глобальний
     `.crumb{max-width:110px}` стискав іконку до 0px. */
  return `<div class="crumbs"><span class="crumb crumb--flat crumb--page">${ico(icon)}<span class="txt">${esc(t(key))}</span></span></div>`;
}

/* Фаза И (Р2): задача — ПЕРША крошка й кнопка. Дропдаун — ті самі пункти, що «⋯» картки, крім «Видалити» (видалення —
   лише з екрана «Задачі»). Клас `crumb--title` лишено: на ньому правило ширини `#bar .crumb.crumb--title`. */
function crumbTask(model, openDd, state) {
  const c = model.zone1.find((x) => x.id === "title");
  if (!c) return "";
  const open = openDd === "task";
  const acts = Array.isArray(state?.taskActs) ? state.taskActs : [];
  const prev = typeof state?.taskPreview === "string" && /^https?:\/\//i.test(state.taskPreview) ? state.taskPreview : "";
  const dd = open ? `<div class="dd dd--task">
    ${ddItem({ act: "tren", icon: "pencil", title: t("taskRename"), marks: "<kbd>F2</kbd>" })}
    ${ddItem({ act: "ttags", icon: "sliders", title: t("taskTagsMenu") })}
    ${prev ? ddItem({ act: "tprev", val: prev, icon: "ext", title: t("taskPreviewOpen") }) : ""}
    ${acts.length ? `<div class="dd-sep"></div>\n    ${acts.map((a) => ddItem({ act: "tmodact", val: a.key, icon: "puzzle", title: a.label })).join("")}` : ""}
  </div>` : "";
  return `<div class="ddhost crumb-h crumb--task">`
    + `<button class="ctl crumb crumb--title" data-dd="task" aria-haspopup="true" aria-expanded="${open}" title="${esc(c.label)}">`
    + `${ico("task")}<span class="txt">${esc(c.label)}</span>${ico("chevdown", 14, "ico caret")}</button>${dd}</div>`;
}

/**
 * Розмітка всієї смуги. `model` — вихід `barModel()` (склад і причини),
 * `state` — вихідний стан екрана: із нього беруться речі, яких модель свідомо
 * не несе — `state.openDd` (який дропдаун розкритий), `state.iterLabel`
 * (підпис поточної ітерації для «Надіслати Іт.3 на GitLab» — текст, що
 * складає вже DOM-шар, не модель, за її ж контрактом `t()`-виклику лише тут),
 * `state.space`/`state.spaces` (ПОТОЧНИЙ простір і перелік для дропдауна
 * фішки на екранах «Задачі»/«Налаштування»: `space` — обʼєкт
 * `{id, name, color, capabilities}` з `/api/task`, `spaces` — масив
 * `/api/spaces`; без `space` фішки нема зовсім).
 *
 * Смуга нічого не знає про аудиторію коментарів (принцип 6 PRODUCT.md): адресата
 * вибирають у формі коментатора, а `state.commentMode` у 0.27.0 прибрано зовсім.
 */
/* Назад / Вперед / Оновити (0.40): три кнопки-іконки на початку зони 1. Підказки — `data-tip` (`app/tooltip.js`), не `title`. */
function navHTML(model) {
  const c = model.zone1.find((x) => x.id === "nav");
  if (!c) return "";
  const b = (act, icon, key, off) => `<button class="ctl ctl--icon" data-act="${act}" data-tip="${esc(t(key))}"`
    + ` aria-label="${esc(t(key))}"${off ? " disabled" : ""}>${ico(icon, 16)}</button>`;
  return `<div class="nav" role="group">${b("navback", "chevleft", "navBack", c.backOff)}${b("navfwd", "chevright", "navFwd", c.fwdOff)}${b("navreload", "refresh", "navReload", false)}</div>`;
}

export function barHTML(model, state) {
  const openDd = state?.openDd ?? null;
  const home = model.zone1.some((x) => x.id === "crumb-tasks" || x.id === "crumb-conn" || x.id === "crumb-wiz");
  /* Третій аргумент `crumbIter` — `state.iterUi` `{menu, ren, del}`: меню рядка, поле назви, питання видалення (фаза И). */
  const iter = home ? "" : crumbIter(model, openDd, state?.iterUi ?? null, Array.isArray(state?.modActs) ? state.modActs : [],
    state?.mode === "overview", state?.iterGone === true, typeof state?.now === "number" ? state.now : Date.now());
  const zone1 = home
    ? `${spaceChip(model, state, openDd)}${homeCrumbs(model)}`
    : `${navHTML(model)}<div class="crumbs">${crumbTask(model, openDd, state)}${iter ? `<span class="crumb-sep" aria-hidden="true">/</span>${iter}` : ""}</div>`;
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

  return `<div class="bar${home ? " bar--home" : ""}">
    <div class="zone zone-1">${zone1}</div>
    <div class="zone zone-2">${zone2}</div>
    <div class="zone zone-3">${zone3}</div>
  </div>
  ${errbar}`;
}
