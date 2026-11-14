/**
 * Розмітка рядка вкладок (етап А, 0.25.0). Чиста: модель — `tabsModel` (`tabs-model.js`), проводка — `app.js`.
 * Не `role="tablist"`: вкладка тут веде на іншу задачу (навігація), а не перемикає панель на сторінці, тож активна
 * несе `aria-current="page"`, як логотип на «Задачах».
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { LOGO_SVG } from "./logo.js";
import { spaceColorToken } from "./spaces-model.js";
import { updatePillHTML } from "./update-view.js";

const cur = (on) => (on ? ' aria-current="page"' : "");

function tabHTML(x) {
  const dot = x.color
    ? `<span class="tab-dot" style="background:var(--${spaceColorToken(x.color)})"></span>`
    : '<span class="tab-dot"></span>';
  const claude = x.claude
    ? `<span class="tab-claude tab-claude--${x.claude}" role="img" aria-label="${esc(t(`claudeTab_${x.claude}`))}"></span>`
    : "";
  const news = x.news
    ? `<span class="tab-news" role="img" aria-label="${esc(t("tabNews", x.news))}">${x.news > 99 ? "99+" : x.news}</span>` : "";
  const tip = esc(t("tabTitle", x.id, x.title));
  return `<div class="tab${x.active ? " tab--on" : ""}">`
    + `<button class="tab-main" data-act="tab" data-val="${esc(x.id)}" title="${tip}"${cur(x.active)}>`
    + `${dot}<span class="tab-id">${esc(x.id)}</span>${claude}${news}</button>`
    + `<button class="tab-x" data-act="tabclose" data-val="${esc(x.id)}" aria-label="${esc(t("tabClose", x.id))}">`
    + `${ico("x", 12)}</button></div>`;
}

export function tabsHTML(m) {
  const logo = esc(t("logoTitle"));
  const open = esc(t("tabOpen"));
  const gear = esc(t("settings"));
  return `<button class="ctl ctl--icon logo-btn${m.logoOn ? " ctl--on" : ""}" data-act="home" aria-label="${esc(t("allTasks"))}" title="${logo}" aria-keyshortcuts="Meta+K Control+K"${cur(m.logoOn)}>${LOGO_SVG}</button>`
    + `<div class="tabs-list">${m.items.map(tabHTML).join("")}</div>`
    + `<button class="ctl ctl--icon tabs-new" data-act="tabnew" aria-label="${open}" title="${open}">${ico("plus")}</button>`
    + `<span class="tabs-sp"></span>`
    + updatePillHTML(m.update)
    + `<button class="ctl ctl--icon${m.gearOn ? " ctl--on" : ""}" data-act="settings" aria-label="${gear}" title="${gear}"${cur(m.gearOn)}>${ico("gear")}</button>`;
}
