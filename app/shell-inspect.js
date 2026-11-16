/**
 * Розмітка правої панелі інспектора — стан на вході, рядок HTML на виході, і нічого крім цього: жодного слухача,
 * жодного звернення до DOM. Проводку (`data-act` → дія) робить `app.js` однією делегацією на контейнер
 * `#insp-panel` і кличе ТУ САМУ мапу дій, що й смуга (`BAR_ACTIONS`): `[data-act="inspector"]` тут (кнопка
 * закриття) і в смузі (кнопка відкриття) мусять лишатись одним рішенням «увімкнено/вимкнено».
 *
 * Етап Г (0.29.0): панель — одна, без вкладок. Тіло — панель властивостей у стилі Figma (`insp-panel.js`, модель —
 * `insp-model.js`), підвал — накручене, записка й дві дії (T-39). «Лінійки» немає: відстані — Alt у рамці макета.
 * Клавіші названо лише в `title` кнопки острівця та в довідці `?` — підписів-пояснень у панелі немає.
 *
 * `inspectHTML(state)`. `state`:
 *   shellMode: 'layout' | 'overview' — інспектор — оверлей у iframe МАКЕТА; у «Огляді» кадри — знімки, живого DOM
 *     там немає, тому панель існує ЛИШЕ в «Макеті» (як і кнопка в смузі, `shell-bar.js`, `TIERS.view`).
 *   on: boolean — `CanvasInspector.on`.
 *   model: модель панелі (`buildModel`, `insp-model.js`) або null — коли нічого не запінено. Панель її не рахує.
 *   tune: пакет `packageJSON(tuneState, page)` (`app/tuner-model.js`) або null — що накручено на ЦІЙ сторінці,
 *     записка Клоду і `status`. Панель його не рахує, лише малює.
 *   tuneOther: number — скільки правок лежить на ІНШИХ сторінках (сторінка — межа видимості правок, і мовчазне
 *     «їх немає» було б неправдою про пакет).
 *   tuneMissing: [{selector, prop}] — правки, які на ЦЬОМУ документі макета не лежать. Окремо від пакета: пакет —
 *     НАМІР дизайнера, «лягло чи ні» — факт про рамку, що на екрані, і в файл йому не можна.
 *
 * Повертає `''`, коли панелі не місце (не «Макет», або інспектор вимкнений): `app.js` (`paintInsp`) читає його ж,
 * щоб вирішити, чи прибирати контейнер із розкладки — одне рішення, а не два.
 */

import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { panelHTML } from "./insp-panel.js";

/* ── Підвал панелі (T-39) ───────────────────────────────────────────────────
   Усе НАКРУЧЕНЕ на цій сторінці, записка Клоду й дві дії — прибиті до низу
   тієї самої вкладки, де крутять. Пакет приходить готовим (`packageJSON`,
   `app/tuner-model.js`) — панель його не рахує й не доповнює, рівно як не
   рахує звіт і лінійку.

   ⛔ ЗАПИСКА — НЕ КОМЕНТАР. `comment-layer` — окремий продукт зі своїм
   каналом і своєю панеллю; ця записка живе в ПАКЕТІ тюнера і їде тому ж
   читачеві, що й правки. Зливати їх не можна: тоді «скинути накручене»
   означало б чіпати чужий продукт, а коментар колеги — їхати Клоду як
   інструкція до коду.

   Групування ПО ЕЛЕМЕНТУ — те саме рішення, що в `packageJSON` і з тієї ж
   причини: так це й читають («цей блок — ось ці правки»). Плоский список
   змусив би дизайнера збирати блок назад очима. */

/**
 * Один рядок списку змін: `властивість: було → стало` і хрестик скидання.
 *
 * ⛔ Це ЄДИНЕ місце, де видно «було», і єдина кнопка скидання однієї правки:
 * у самому рядку звіту не лишилось ні того, ні того (T-39). Рядок звіту
 * дублював «було» перекресленим текстом і платив за це 28px висоти на кожну
 * правку — саме через це панель і «скакала». Тут же воно стоїть один раз,
 * поруч зі стрілкою, у списку, який для цього й існує.
 *
 * Скидає рядок САМЕ ЦЮ правку, і адресує її ПАРОЮ (`data-sel` елемента +
 * `data-prop`): у списку елемент не запінений — дизайнер дивиться на перелік,
 * а не на макет, — тож звичайний шлях «правка запіненого» тут не працює.
 * `data-sel` — ключ ЕЛЕМЕНТА (поле `selector` пакета), не `rule` правки:
 * перше адресує блок, друге каже, де правити код (шапка `app/tuner-model.js`).
 */
function tuneRow(sel, e, miss) {
  /* ⛔ ПОЗНАЧКА «НЕ ЛЯГЛО» — те, заради чого цей рядок узагалі чесний. Правка
     лишається в пакеті (вона описує зроблене дизайнером), але малювати її
     так само, як ту, що стоїть на макеті, означає стверджувати зміну, якої на
     екрані немає. Стан — АТРИБУТОМ (`data-miss`), як `data-tuned` у полі
     звіту: охоронець css-guards витягує імена класів регекспом по САМОМУ
     сирцю, і клас, зібраний тернарником усередині атрибута class, лишив би
     йому шматок шаблону замість імені.
     Титул — на самій позначці: дизайнер наводиться саме на неї, коли питає
     «а чому воно бліде», і в титулі рядка (властивість, було→стало) цьому
     поясненню не місце. */
  const mark = miss
    ? `<span class="insp-miss" title="${esc(t("inspTunerNotApplied"))}"`
      + ` aria-label="${esc(t("inspTunerNotApplied"))}">${ico("warn", 12)}</span>` : "";
  return `<p class="insp-chg-row"${miss ? ` data-miss=""` : ""}`
    + ` title="${esc(e.prop)}: ${esc(e.from)} → ${esc(e.to)}">`
    + `<span class="insp-chg-prop">${esc(e.prop)}</span>`
    + `<span class="insp-tune-from">${esc(e.from)}</span>`
    + `<span class="insp-tune-arr">→</span>`
    + `<span class="insp-tune-to">${esc(e.to)}</span>`
    + mark
    + `<button class="insp-tune-x" data-act="insptunedrop" data-sel="${esc(sel)}"`
    + ` data-prop="${esc(e.prop)}" title="${esc(t("inspTunerDrop"))}">${ico("x", 12)}</button>`
    + `</p>`;
}

/**
 * Блок одного елемента у списку змін.
 *
 * У заголовку — короткий підпис елемента, у `title` — повний ключ
 * (ланцюжок предків). Ключ цілком у заголовок не поміститься (панель 308px),
 * а без нього дві однакові на вигляд картки не розрізнити.
 */
function tuneElement(el, missing) {
  const rows = (el.edits || []).map((e) => tuneRow(el.selector, e,
    missing.some((m) => m && m.selector === el.selector && m.prop === e.prop))).join("");
  const name = el.label || el.selector;
  return `<section class="insp-chg-el">`
    + `<h6 title="${esc(el.selector)}">${esc(name)}</h6>${rows}</section>`;
}

/**
 * Підвал: лічильник, список змін, згадка про інші сторінки, записка, дії.
 *
 * @param {?object} pkg     пакет ЦІЄЇ сторінки (`packageJSON(state, page)`)
 * @param {number}  other   скільки правок лежить на ІНШИХ сторінках
 * @param {Array}   missing пари `{selector, prop}`, які на цьому документі не
 *                          лежать — рядок про них КАЖЕ, а не мовчить
 *
 * `other` малюється навіть при порожній сторінці — і саме тому це окремий
 * рядок, а не частина лічильника: сторінка є межею видимості правок
 * (`tunePage`, `app/app.js`), і без цього числа дизайнер вирішив би, що Клоду
 * поїде лише те, що він бачить перед собою.
 *
 * ⛔ «Надіслати Клоду» НІЧОГО НЕ НАДСИЛАЄ і нічого не зберігає: збереження
 * автоматичне й лишається таким (`saveTune`, `app/app.js`) — пакет на диску
 * свіжий після кожного повороту ручки. Кнопка ставить `status: ready`, тобто
 * відповідає на єдине питання, на яке читач пакета досі не мав відповіді:
 * «дизайнер іще крутить чи вже закінчив». Тому й позначка поруч каже
 * «чекає на Клода», а не «надіслано»: події відправлення не існує.
 *
 * «Скасувати» — це та сама дія, що й «Скинути все» над запискою
 * (`insptuneall`), і ОДНА дія тут навмисно має два входи: у макеті власника
 * вони обидва намальовані. Скасувати в цьому підвалі більше нічого й не
 * можна — надсилання не є подією, а збереження не є вибором.
 */
function tuneFootHTML(pkg, other, missing) {
  const els = pkg && Array.isArray(pkg.elements) ? pkg.elements : [];
  const edits = els.reduce((n, el) => n + (el.edits || []).length, 0);
  const note = pkg && typeof pkg.note === "string" ? pkg.note : "";
  /* Порожньому підвалу тут не місце: лічильник «0 змін», мертва кнопка
     «Надіслати» й порожній список — це три обіцянки дії, якої немає. Тіло
     панелі в цьому стані порожнє — підписів-пояснень немає. */
  if (!edits && !other && !note) return "";
  const ready = pkg && pkg.status === "ready"
    ? `<span class="insp-ready">${esc(t("inspTunerReadyMark"))}</span>` : "";
  const sum = edits
    ? `<p class="insp-tune-sum"><span>${esc(t("inspTunerCount", els.length, edits))}</span>`
      + ready
      + `<button class="insp-tune-all" data-act="insptuneall"`
      + `>${esc(t("inspTunerResetAll"))}</button></p>`
    : "";
  const rest = other > 0
    ? `<p class="insp-tune-other">${esc(t("inspTunerOther", other))}</p>` : "";
  /* Список змін — В ОКРЕМІЙ, ОБМЕЖЕНІЙ ПО ВИСОТІ коробці, і це не косметика.
     Підвал прибитий до низу (`flex:none`), тобто кожен його зайвий піксель
     зʼїдається в тіла панелі: двадцять правок без цієї межі лишили б від
     звіту смужку, а від записки — нічого. Прокрутка тут чесніша за зростання:
     підвал мусить лишатись підвалом. */
  const list = els.length
    ? `<div class="insp-chg">${els.map((el) => tuneElement(el, missing)).join("")}</div>` : "";
  return sum + list + rest
    + `<textarea class="insp-note-ta" data-act="insptunenote" rows="2"`
    + ` aria-label="${esc(t("inspTunerNote"))}"`
    + ` placeholder="${esc(t("inspTunerNotePh"))}">${esc(note)}</textarea>`
    + `<div class="insp-acts">`
    + `<button class="insp-send" data-act="insptuneready"`
    + ` title="${esc(t("inspTunerSendHint"))}">${esc(t("inspTunerSend"))}</button>`
    + `<button class="insp-cancel" data-act="insptuneall">${esc(t("inspTunerCancel"))}</button>`
    + `</div>`;
}

export function inspectHTML(state) {
  if (state.shellMode !== "layout" || !state.on) return "";
  /* Одна панель, без вкладок: «Лінійки» немає (відстані — Alt у рамці), «Тюнер» давно переїхав у підвал. `model` —
     готова модель (`buildModel`, `insp-model.js`); панель її лише малює. Порожній стан (нічого не вибрано) — лише
     шапка й порожнє тіло: підписів-пояснень немає (правило власника), клавіші названо в `title` кнопки острівця. */
  const foot = tuneFootHTML(state.tune, Number(state.tuneOther) || 0,
    Array.isArray(state.tuneMissing) ? state.tuneMissing : []);
  return `<div class="insp-top">${ico("inspect", 16)}
      <span class="panel-title">${esc(t("inspector"))}</span>
      <button class="icob" data-act="inspector" title="${esc(t("kEsc"))}">${ico("x")}</button></div>
    <div class="insp-body">${panelHTML(state.model)}</div>${foot ? `<div class="insp-foot">${foot}</div>` : ""}`;
}
