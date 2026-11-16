/**
 * Вбудоване підтвердження (етап В, 0.28.0): питання на місці дії — у меню сторінки, у дропдауні ітерації, у картці
 * коментаря. Чиста розмітка. «Ні» стоїть першим і бере фокус (викликач кличе `.focus()` на `.cfm-no`): Enter чи пробіл,
 * натиснуті не дивлячись, нічого не видаляють. `yesAttrs`/`noAttrs` — готові атрибути кнопок; значення в них викликач
 * екранує сам (`esc`).
 */
import { esc } from "./esc.js";

export function confirmHTML({ title, yes, no, yesAttrs = "", noAttrs = "" }) {
  return `<div class="cfm" role="group" aria-label="${esc(title)}"><p class="cfm-t">${esc(title)}</p>`
    + `<div class="cfm-row"><button type="button" class="cfm-no" ${noAttrs}>${esc(no)}</button>`
    + `<button type="button" class="cfm-yes" ${yesAttrs}>${esc(yes)}</button></div></div>`;
}
