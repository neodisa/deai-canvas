/**
 * Група «Застосунок» у «Налаштуваннях» (етап Е, 0.31.0): «Загальне», «Оновлення», «Гарячі клавіші». Чисті рядки розмітки — ні DOM,
 * ні мережі. Кнопки: мова — `data-th="lang"` (`data-v` = `uk`/`en`, радіогрупа `.seg`), встановлення — `data-th="pwa"`,
 * оновлення — `data-th="up"` (`data-v` = `check` | `open`); поводження — в `app.js`.
 * Клавіші малюються з `KEYS` (`shell-palette.js`) — того самого масиву, що й аркуш `?`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { relTime } from "./tasks-model.js";
import { KEYS } from "./shell-palette.js";
import { STATE_KEYS } from "./update-view.js";

const row = (title, lead, ctl) => `<div class="set-row"><div class="set-row-l"><span class="set-row-t">${esc(title)}</span>`
  + `${lead ? `<span class="set-row-s">${esc(lead)}</span>` : ""}</div>${ctl}</div>`;

/** «Загальне». `v = {lang, canInstall, standalone}`; рядок «Окреме вікно» — лише коли можна встановити чи вже встановлено. */
export function generalBodyHTML(v) {
  const x = v || {};
  const opt = (id, key) => {
    const on = x.lang === id;
    return `<button type="button" role="radio" aria-checked="${on}" tabindex="${on ? 0 : -1}" data-th="lang" data-v="${id}">${esc(t(key))}</button>`;
  };
  const seg = `<div class="seg" role="radiogroup" aria-label="${esc(t("appLang"))}">${opt("uk", "appLangUk")}${opt("en", "appLangEn")}</div>`;
  let rows = row(t("appLang"), "", seg);
  if (x.standalone === true) {
    rows += row(t("appWindow"), t("appWindowLead"), `<span class="set-row-v">${esc(t("appInstalled"))}</span>`);
  } else if (x.canInstall === true) {
    rows += row(t("appWindow"), t("appWindowLead"),
      `<button type="button" class="ctl ctl--out" data-th="pwa" data-v="install">${ico("download")}${esc(t("appInstall"))}</button>`);
  }
  return `<div class="set-rows">${rows}</div>`;
}

/** Рядок стану: відома відмова перевірки → її текст; інакше «остання перевірка {коли}»; перевірок ще не було — нічого. */
function stateLine(u) {
  if (STATE_KEYS[u.state]) return t(STATE_KEYS[u.state]);
  if (typeof u.checked_at !== "number") return "";
  const r = relTime(u.checked_at * 1000, Date.now());
  return t("updLast", t(r.key, r.n));
}

/** «Оновлення». `u` — `GET /api/update` (чи `null`, поки не питали); `checking` — `POST /api/update-check` у польоті. */
export function updateBodyHTML(u, checking = false) {
  const x = u && typeof u === "object" ? u : {};
  const check = `<button type="button" class="ctl ctl--out" data-th="up" data-v="check"${checking ? " disabled" : ""}`
    + `${checking ? ' aria-busy="true"' : ""}>${ico("refresh")}${esc(t(checking ? "updChecking" : "updCheckNow"))}</button>`;
  const go = x.available === true && typeof x.latest === "string" && x.latest
    ? `<button type="button" class="ctl ctl--pri" data-th="up" data-v="open">${esc(t("updTo", x.latest))}</button>` : "";
  return `<div class="set-rows">${row(t("updName", typeof x.current === "string" ? x.current : ""), stateLine(x),
    `<div class="set-row-a">${check}${go}</div>`)}</div>`;
}

/** «Гарячі клавіші»: дві групи (як аркуш `?`), рядок = підпис + `kbd`. */
export function keysBodyHTML() {
  const group = (id, titleKey) => `<h2 class="sub">${esc(t(titleKey))}</h2><div class="set-rows">`
    + KEYS.filter((k) => k.group === id).map((k) => row(t(k.labelKey), "", `<kbd>${esc(k.kbd)}</kbd>`)).join("") + "</div>";
  return group("general", "keysGeneral") + group("layout", "keysLayout");
}
