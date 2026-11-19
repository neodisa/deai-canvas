/**
 * Розділ «Простір» у «Налаштуваннях» (етап Е, 0.31.0): назва, колір, тека. Чисті рядки розмітки — ні DOM, ні мережі.
 * Кнопки — `data-th="spc"` (колір, `data-v` = токен `space-N`) і `data-th="spcopy"`; поле назви — `#set-sp-name`.
 * Поводження (запис `space-update`, стрілки радіогрупи) — в `app.js`. Неявний простір (без теки) — лише для читання.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { SPACE_COLORS, spaceColorToken } from "./spaces-model.js";

/** Простір без теки (неявний) нічого не зберігає: його назву й колір міняти нема де. */
export const spaceReadOnly = (sp) => !sp?.path;

export function spaceBodyHTML(sp) {
  const ro = spaceReadOnly(sp);
  const cur = spaceColorToken(sp.color);
  const dis = ro ? " disabled" : "";
  const items = SPACE_COLORS.map((c, i) => {
    const on = c === cur;
    return `<button type="button" class="sw" role="radio" aria-checked="${on}" tabindex="${on ? 0 : -1}"${dis}`
      + ` data-th="spc" data-v="${c}" data-val="${c}">`
      + `<span class="sw-pv" aria-hidden="true"><span class="sw-bar"></span><span class="sw-body"></span></span>`
      + `<span class="sw-n">${esc(t("spaceColorName", i + 1))}${on ? ico("check", 14) : ""}</span></button>`;
  }).join("");
  const path = ro ? "" : `<div class="sp-fld"><span class="sp-lbl">${esc(t("spFolder"))}</span>`
    + `<div class="sp-path"><span>${esc(sp.path)}</span>`
    + `<button type="button" class="icob" data-th="spcopy" data-v="path" aria-label="${esc(t("spCopyPath"))}" title="${esc(t("spCopyPath"))}">${ico("copy", 15)}</button></div></div>`;
  return `<div class="sp-fld"><label class="sp-lbl" for="set-sp-name">${esc(t("spName"))}</label>`
    + `<input class="cn-inp" id="set-sp-name" type="text" value="${esc(sp.name)}" maxlength="60" autocomplete="off" spellcheck="false"${dis}></div>`
    + `<div><h2 class="sub" id="sp-color-h">${esc(t("spColorH"))}</h2>`
    + `<div class="sw-grid" role="radiogroup" aria-labelledby="sp-color-h">${items}</div></div>`
    + path;
}
