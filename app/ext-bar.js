/**
 * Смуга ЗОВНІШНЬОЇ оболонки — опублікованого превʼю. Стан на вході, рядок
 * HTML на виході, і нічого крім цього: та сама ідіома, що в `shell-bar.js` і
 * `shell-panel.js` — ні слухачів, ні звернень до DOM. Проводку (`data-act` →
 * дія) робить `ext-shell.js` однією делегацією.
 *
 * ⛔ ЧОМУ ОКРЕМА ЗБІРКА, а не `barModel()` з прапорцем «зовнішній». У цій
 * смузі немає ні GitLab, ні публікації, ні інспектора, ні дій над ітерацією —
 * тобто немає зони 3 і половини зони 2. Провести це через модель означало б
 * додати гілки «зовнішній/внутрішній» у модуль, від якого залежить
 * ІНСТРУМЕНТ: кожна майбутня правка смуги мусила б думати про обидва світи, і
 * помилка в тій думці ламала б робоче місце дизайнера — не превʼю. Ціна
 * визнається прямо: два місця, де малюється смуга, і вони можуть розійтись.
 *
 * Що робить розходження дешевим і видимим — ТРИ речі спільні дослівно:
 *   · імена класів CSS (`.bar`, `.zone`, `.ctl`, `.seg`, `.crumb`, `.dd`) —
 *     `styles.css` їде в `publish/shell/` БЕЗ правок, тож перейменований клас
 *     тут означає смугу без стилів у чужому браузері;
 *   · іконки (`icons.js`) — `ico()` кидає на невідоме імʼя, тобто одрук видно
 *     на першому рендері, а не порожнім квадратом у темній смузі;
 *   · словник (`i18n.js`) — жодного напису в цьому файлі, усе через `t()`
 *     (охоронець `tests/i18n-literals.test.mjs` сканує й цей модуль).
 * Плюс пресети ширин беруться з `viewport.js`, а не переписуються масивом:
 * четвертий пристрій, доданий колись у ньому, приїде в обидві смуги сам.
 *
 * Ярус, на якому ховається підпис, як і в інструменті, рахує НЕ цей файл, а
 * контейнерний запит у `styles.css` (`.lbl-mode` на 1180px). Але класу
 * `.view-extra` тут немає СВІДОМО: у цій смузі немає меню «⋯», у яке контрол
 * міг би переїхати, тож `view-extra` означав би «перемикач ширин зникає
 * ЗОВСІМ на вузькому екрані» — рівно те, як 01.09.2026 усередині інструмента
 * пропало керування виглядом.
 */

import { t } from "./i18n.js";
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { PRESETS } from "./viewport.js";

/* Пункт дропдауна — та сама розмітка, що `ddItem` у `shell-bar.js`, але без
   полів, яким тут нема застосування (`sub`, `why`, `danger`, `marks`):
   у зовнішньому дропдауні лежить ЛИШЕ перелік ітерацій. */
const ddItem = ({ act, val, icon, title, on }) => `<button class="dd-item${
  on ? " dd-item--on" : ""}" data-act="${esc(act)}" data-val="${esc(val)}">
    ${ico(icon)}<span class="dd-body"><span class="dd-t">${esc(title)}</span></span></button>`;

/**
 * Зона 1: назва задачі й крошка ітерації.
 *
 * Назва задачі — ТЕКСТ, а не дропдаун: у превʼю задача одна, і кнопка
 * «перемкнути задачу» вела б нікуди. Це не економія — це те саме правило, що
 * вимикає «Огляд» без кадрів: контрол, за яким нічого немає, гірший за його
 * відсутність, бо на нього тиснуть.
 *
 * Крошка ітерації стає дропдауном лише коли ітерацій БІЛЬШЕ ОДНОЇ. Сама
 * крошка лишається завжди: вона відповідає на питання «де я», і без неї
 * глядач не знає, яку версію бачить.
 */
function zone1(st) {
  const many = (st.iters || []).length > 1;
  const open = st.openDd === "iter";
  const list = (st.iters || []).map((x) => ddItem({
    /* У ПЕРЕЛІКУ тег і примітка склеєні в один рядок — так само, як у
       `shell-bar.js`: пункт дропдауна обрізає браузер, і два вузли там нічого
       не дають. Розділювач малюється лише коли є що розділяти: «Іт.1 ·» без
       примітки читається як обрізаний текст. */
    act: "iter", val: x.id, icon: "iter", on: !!x.on,
    title: x.note ? `${x.label} · ${x.note}` : x.label,
  })).join("");
  const dd = `<div class="dd"><div class="dd-head">${esc(t("iterations"))}</div>${list}</div>`;
  /* `<span>`, а не `.ctl`: `.ctl` несе `cursor:pointer` і підсвітку на
     наведення, тобто виглядав би клікабельним. Але БОКС потрібен той самий —
     звідси `.crumb--flat` (`styles.css`): без нього це голий рядок, іконка
     впритул до тексту й висота 19px замість 32. */
  const task = `<span class="crumb crumb--flat crumb--task" title="${esc(st.task)}"
    >${ico("task")}<span class="txt txt--fix">${esc(st.task)}</span></span>`;
  /* Тег і примітка — ДВА вузли, як у крошці інструмента (`shell-bar.js`), і це
     несуче: `.txt--fix` не обрізається НІКОЛИ, `.txt--soft` обрізається завжди
     (`styles.css`, у крошки ітерації ще й `max-width:112px`). Саме на цьому
     розділенні тримається інваріант «крошку не стиснуло браком місця»: одним
     вузлом примітка зʼїдала тег, тобто зникало рівно те, що крошка й мусить
     сказати — яку версію глядач бачить.
     Порожню примітку не малюємо взагалі: вузол із самим «·» читається як
     обрізаний текст, тобто як зламана крошка. */
  const note = st.iterNote
    ? `<span class="txt txt--soft">· ${esc(st.iterNote)}</span>`
    : "";
  // `title` несе ПОВНИЙ підпис: примітку обрізає CSS, і без нього довгу
  // примітку не прочитати ніяк.
  const full = st.iterNote ? `${st.iterLabel} · ${st.iterNote}` : st.iterLabel;
  const crumb = many
    ? `<div class="ddhost crumb-h crumb--iter">
      <button class="ctl crumb crumb--iter" data-dd="iter" title="${esc(full)}"
        aria-expanded="${open}" aria-haspopup="true">
        ${ico("iter")}<span class="txt txt--fix">${esc(st.iterLabel)}</span>
        ${note}${ico("chevdown", 14, "ico caret")}</button>
      ${open ? dd : ""}
    </div>`
    : `<span class="crumb crumb--flat crumb--iter" title="${esc(full)}"
      >${ico("iter")}<span class="txt txt--fix">${esc(st.iterLabel)}</span>${note}</span>`;
  return `<div class="crumbs">${task}
    ${ico("chevright", 14, "ico crumb-sep")}${crumb}</div>`;
}

/**
 * Зона 2: «Макет / Огляд» і перемикач ширин — «як дивлюсь», оптично
 * посередині (грид `.bar`).
 *
 * Причина, чому «Огляд» вимкнений, малюється ВИДИМИМ рядком (`.dd-why`), а не
 * лише в `title`: те саме правило, що в смузі інструмента — вимкнений
 * контрол, який не каже чому, читається як зламаний, а глядач превʼю не має
 * ні зʼємки, ні способу дізнатись, що кадрів просто не знімали.
 */
function zone2(st) {
  const why = st.overviewWhyKey ? t(st.overviewWhyKey) : "";
  const mode = [
    { id: "layout", key: "modeLayout", why: "" },
    { id: "overview", key: "modeOverview", why },
  ].map((m) => `<button data-act="mode" data-val="${m.id}"
      aria-pressed="${st.mode === m.id}"${m.why ? " disabled" : ""}
      title="${esc(m.why || t(m.key))}">${ico(m.id)}
      <span class="lbl-mode">${esc(t(m.key))}</span>
      ${m.why ? `<span class="dd-why">${esc(m.why)}</span>` : ""}</button>`).join("");
  const vp = PRESETS.map((p) => `<button data-act="vp" data-val="${p.id}"
      aria-pressed="${st.vp === p.id}"
      title="${esc(p.label)}" aria-label="${esc(p.label)}">${ico(p.id)}</button>`).join("");
  return `<div class="seg" role="group" data-seg="mode">${mode}</div>
    <div class="seg seg--icons" role="group" data-seg="vp">${vp}</div>`;
}

/**
 * Зона 3: «Копіювати посилання».
 *
 * Підпис після кліку міняється на «Посилання скопійовано» — інакше клік по
 * кнопці, яка нічого видимо не робить, читається як промах. Тостів у
 * зовнішній оболонці немає (для одного повідомлення це був би цілий шар), тож
 * підтвердження живе в самій кнопці — так це й робила стара обгортка.
 */
function zone3(st) {
  const done = !!st.copied;
  return `<button class="ctl ctl--out" data-act="copylink"
    title="${esc(t("copyLink"))}">${ico(done ? "check" : "link")}
    <span>${esc(done ? t("toastCopied") : t("copyLink"))}</span></button>`;
}

/**
 * `extBarHTML(state)`. `state`:
 *   task: string — назва задачі (з маніфеста, тому екранується)
 *   iterLabel: string — ТЕГ поточної ітерації («Іт.3»/«It.3»), уже зі
 *     словника: маніфест везе `num`, тег ліпить `extBarState` (`ext-shell.js`)
 *   iterNote: string — примітка поточної ітерації ('' — немає). ОКРЕМИМ
 *     полем, бо розмітка поводиться з ними по-різному: тег не обрізається
 *     ніколи, примітка обрізається завжди
 *   iters: [{ id, label, note, on }] — перелік для дропдауна крошки
 *   openDd: 'iter' | null — який дропдаун розкритий (стан UI, не складу смуги)
 *   mode: 'layout' | 'overview'
 *   overviewWhyKey: string — імʼя ключа причини, чому «Огляд» вимкнений
 *     ('' — увімкнений)
 *   vp: id пресета з `viewport.js`
 *   copied: boolean — щойно скопійоване посилання
 *   error: string — ГОТОВИЙ рядок помилки для смуги під баром ('' — немає)
 *
 * `error` приходить уже перекладеним, як `pagesError` у панелі: цей модуль
 * лише малює, а причину («маніфест не читається» + текст збою) складає
 * проводка — вона одна знає, що саме зламалось.
 */
export function extBarHTML(st) {
  const errbar = st.error
    ? `<div class="errbar">${ico("warn")}<span>${esc(st.error)}</span>
      <button class="ctl ctl--out" data-act="retry">${ico("refresh")}${esc(t("retry"))}</button></div>`
    : "";
  return `<div class="bar">
    <div class="zone zone-1">${zone1(st)}</div>
    <div class="zone zone-2">${zone2(st)}</div>
    <div class="zone zone-3">${zone3(st)}</div>
  </div>
  ${errbar}`;
}
