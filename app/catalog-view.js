/**
 * Діалог «Додати модуль» і його друга сторінка «Свій модуль» (етап Е, 0.31.0; спека
 * `docs/superpowers/specs/2026-11-19-settings-e-design.md`, §3). Чиста розмітка для `askForm` (`app/ask.js`), як
 * `trust-view.js`: ні DOM, ні fetch. Проводку (вибір, друга сторінка, копіювання запиту) дає `connCatalog` в `app.js`.
 *
 *   catFormHTML(inner, page)   `<form>` діалогу зі сталою шапкою; `page` — `list|own` (`data-page`); `inner` — вміст однієї зі сторінок (`.cat-pg`);
 *   catListHTML(groups, role)  сторінка 1: групи за ролями, рядки `.cat` (`[data-cat-pick=<id>]`), підсвічена група `role`
 *                              (`.cat--hl`, перша кнопка групи — `data-autofocus`), останній рядок — «Свій модуль» (`[data-cat-own]`);
 *   catOwnHTML(prompt, what)   сторінка 2 («‹» — `[data-cat-back]` у шапці): кроки `ol.steps`, поле `#own-what`, запит `pre.prompt`,
 *                              «Скопіювати запит» (`[data-cat-copy]`).
 *
 * Контракт `askForm`: заголовок `#cat-h` (назва діалогу для зчитувача), хрестик у шапці — перший `data-a="cancel"`; кнопки відправки
 * нема: вибір модуля закриває діалог програмно (`form.requestSubmit()`). ⛔ Усе з даних (назви, опис, запит) — лише через `esc()`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { builtinText, roleIcon } from "./connections-model.js";
import { modName, roleTitle } from "./connections-view.js";

/**
 * `<form>` діалогу. Шапка СТАЛА для обох сторінок (`[data-cat-back]`, `#cat-h`, хрестик): `askForm` чіпляє «Скасувати» до першого
 * `[data-a="cancel"]` ЛИШЕ при відкритті, тож хрестик не можна перемальовувати; сторінки міняють вміст `.cat-pg` і показують/ховають
 * «‹» та підпис шапки (`page` — `list|own`, `data-page`; підпис — `catTitle`/`catOwn`).
 */
export const catFormHTML = (inner, page = "list") => `<form class="cv-form cat-d" data-form="catalog" data-page="${esc(page)}" novalidate`
  + ` role="dialog" aria-modal="true" aria-labelledby="cat-h"><div class="cat-h">`
  + `<button type="button" class="icob" data-cat-back aria-label="${esc(t("catBack"))}" title="${esc(t("catBack"))}"${page === "own" ? "" : " hidden"}>${ico("chevleft", 16)}</button>`
  + `<h2 class="cv-form-h" id="cat-h">${esc(t(page === "own" ? "catOwn" : "catTitle"))}</h2>`
  + `<button type="button" class="icob" data-a="cancel" aria-label="${esc(t("askClose"))}" title="${esc(t("askClose"))}">${ico("x", 16)}</button></div>`
  + `<div class="cat-pg">${inner}</div></form>`;

/** Один рядок каталогу: іконка ролі, назва, опис і кнопка «Підключити» / «Замінити {поточний}». */
function rowHTML(r, role, hl, af) {
  const e = r.entry;
  const desc = builtinText(e.id)?.desc;
  const label = r.replaces ? t("catReplace", r.replaces) : t("catConnect");
  return `<div class="cat${hl ? " cat--hl" : ""}"><span class="mc-ic">${ico(roleIcon(role), 18)}</span>`
    + `<div class="mc-name"><b>${esc(modName(e))}</b>${desc ? `<span>${esc(t(desc))}</span>` : ""}</div>`
    + `<button type="button" class="ctl ctl--out" data-cat-pick="${esc(e.id)}"${af ? " data-autofocus" : ""}>${esc(label)}</button></div>`;
}

/** Сторінка 1. `groups` — `catalogGroups`; `role` — роль, з чиєї пунктирної картки відкрито («» — з голови сторінки). */
export function catListHTML(groups, role = "") {
  const list = Array.isArray(groups) ? groups : [];
  /* Фокус починається з першої кнопки підсвіченої групи, а без неї — з першого рядка (інакше `askForm` взяв би хрестик у шапці). */
  const focusRole = list.some((g) => g.role === role && role) ? role : list[0]?.role;
  const body = list.map((g) => `<h3 class="cat-g">${esc(roleTitle(g.role))}</h3>`
    + g.rows.map((r, i) => rowHTML(r, g.role, !!role && g.role === role, g.role === focusRole && i === 0)).join("")).join("");
  const own = `<div class="cat cat--own"><span class="mc-ic">${ico("puzzle", 18)}</span>`
    + `<div class="mc-name"><b>${esc(t("catOwn"))}</b><span>${esc(t("catOwnLead"))}</span></div>`
    + `<button type="button" class="ctl ctl--out" data-cat-own${list.length ? "" : " data-autofocus"}>${esc(t("catOwnHow"))}${ico("chevright", 14)}</button></div>`;
  return `<div class="cat-b">${body}${own}</div>`;
}

/** Сторінка 2. `prompt` — готовий запит (`ownPrompt`), `what` — що людина вже ввела в поле. */
export function catOwnHTML(prompt, what = "") {
  const step = (n) => `<li><b>${esc(t(`ownStep${n}`))}</b>${esc(t(`ownStep${n}Rest`))}</li>`;
  return `<div class="cat-b cat-b--pad"><ol class="steps">${step(1)}${step(2)}${step(3)}</ol>`
    + `<div class="cv-field"><label for="own-what">${esc(t("ownWhat"))}</label>`
    + `<textarea class="ta" id="own-what" name="what" rows="3" placeholder="${esc(t("ownWhatPh"))}" spellcheck="false">${esc(what)}</textarea></div>`
    + `<pre class="prompt" id="own-prompt">${esc(prompt)}</pre></div>`
    + `<div class="cat-f"><button type="button" class="ctl ctl--out" data-a="cancel">${esc(t("askClose"))}</button>`
    + `<button type="button" class="ctl ctl--pri" data-cat-copy>${ico("copy", 15)}${esc(t("ownCopy"))}</button></div>`;
}
