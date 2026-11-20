/**
 * Розділ «AGENTS.md» у «Налаштуваннях» (етап Е, 0.31.0): чисті рядки розмітки для шести станів — ні DOM, ні мережі.
 * Стан `a` — відповідь `GET /api/agents-md` ({exists, hasBlock, outdated, newer, version, fileVersion, block, own, path}) або
 * `{loading: true}` / `{failed: {code}}`. Кнопки — `data-th="ag"` + `data-v` (`copy`, `copypath`, `update`, `create`, `retry`);
 * поводження — в `app.js`. Увесь вміст файла екранується.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

/** «Оновити з шаблону» активна лише коли шаблон новіший або файл є, а блока в ньому нема (і файл не з новішого Deai). */
export const canUpdate = (a) => !!a && !a.newer && (a.outdated === true || (a.exists === true && a.hasBlock === false));

/** Стан відповіді → один із: `loading | error | nofolder | nofile | file`. */
export function agentsKind(a) {
  if (!a || a.loading) return "loading";
  if (a.failed) return a.failed.code === "no-folder" ? "nofolder" : "error";
  return a.exists ? "file" : "nofile";
}

/** Кнопки голови (праворуч від `h1`): лише коли файл є. */
export function agentsActsHTML(a, busy = false) {
  if (agentsKind(a) !== "file") return "";
  const dis = busy || !canUpdate(a) ? " disabled" : "";
  return `<div class="ag-acts"><button type="button" class="ctl ctl--out" data-th="ag" data-v="copy">${ico("copy")}${esc(t("agCopy"))}</button>`
    + `<button type="button" class="ctl ctl--out" data-th="ag" data-v="update"${dis}>${ico("refresh")}${esc(t("agUpdate"))}</button></div>`;
}

const plate = (text, btn) => `<div class="note" role="status">${ico("warn", 16)}<p>${esc(text)}</p>${btn}</div>`;

function viewerHTML(a) {
  const own = typeof a.own === "string" ? a.own : "";
  const tpl = a.hasBlock
    ? `<div class="ag-part"><div class="ag-g">${esc(t("agPartTpl", a.fileVersion ?? a.version))}</div><pre role="region" tabindex="0" aria-label="${esc(t("agPartTpl", a.fileVersion ?? a.version))}">${esc(a.block ?? "")}</pre></div>` : "";
  const mine = own.trim() === ""
    ? "" : `<div class="ag-part ag-own"><div class="ag-g">${esc(t("agPartOwn"))}</div><pre role="region" tabindex="0" aria-label="${esc(t("agPartOwn"))}">${esc(own)}</pre></div>`;
  return `<div class="ag"><div class="ag-bar">${ico("doc", 14)}<span>${esc(a.path ?? "")}</span>`
    + `<button type="button" class="icob" data-th="ag" data-v="copypath" aria-label="${esc(t("agCopyPath"))}" title="${esc(t("agCopyPath"))}">${ico("copy", 15)}</button></div>`
    + `<div class="ag-body">${tpl}${mine}</div></div>`;
}

/** Тіло розділу (під `h1`). `busy` — запис у польоті: кнопки вимкнені. */
export function agentsBodyHTML(a, busy = false) {
  const k = agentsKind(a);
  if (k === "loading") return `<p class="cn-loading" role="status">${esc(t("agLoading"))}</p>`;
  if (k === "nofolder") return `<p class="ag-empty">${esc(t("agNoFolder"))}</p>`;
  if (k === "error") {
    return `<div class="cn-err" role="alert">${ico("warn")}<span>${esc(t("agErrLoad"))}</span>`
      + `<button type="button" class="ctl ctl--out" data-th="ag" data-v="retry">${ico("refresh")}${esc(t("retry"))}</button></div>`;
  }
  if (k === "nofile") {
    return `<div class="ag-empty"><p>${esc(t("agNoFile"))}</p>`
      + `<button type="button" class="ctl ctl--pri" data-th="ag" data-v="create"${busy ? " disabled" : ""}>${esc(t("agCreate"))}</button></div>`;
  }
  const dis = busy ? " disabled" : "";
  const upd = `<button type="button" class="ctl ctl--pri" data-th="ag" data-v="update"${dis}>${ico("refresh", 14)}${esc(t("agUpdate"))}</button>`;
  let note = "";
  if (a.newer) note = plate(t("agNewerNote", a.fileVersion), `<button type="button" class="ctl ctl--pri" data-th="ag" data-v="update" disabled>${ico("refresh", 14)}${esc(t("agUpdate"))}</button>`);
  else if (a.outdated) note = plate(t("agOutdatedNote", a.version, a.fileVersion), upd);
  return note + viewerHTML(a);
}
