/**
 * Інструменти острівця внизу робочої зони (етап А, 0.25.0): інспектор (лише «Макет» — він працює по живому DOM,
 * у «Огляді» кадри — знімки) | баг/ідея останнім. Сегмент стану Claude — окремий вузол `#claude-hud` (`role="status"`,
 * його веде `paintClaude` в `app.js`), бо жива область не сміє містити кнопок. Кнопка коментарів — етап Б.
 * Дії — ті самі `BAR_ACTIONS` (`inspector`, `feedback`): делегація з `#hud` в `app.js`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

export function islandToolsHTML({ screen = "task", mode = "layout", inspectorOn = false } = {}) {
  const parts = [];
  if (screen === "task" && mode === "layout") {
    parts.push(`<button class="isl-btn${inspectorOn ? " isl-btn--on" : ""}" data-act="inspector" aria-pressed="${inspectorOn}"`
      + ` aria-label="${esc(t("inspector"))}" title="${esc(t("inspectorKey"))}">${ico("inspect")}</button>`);
    parts.push('<span class="isl-sep" aria-hidden="true"></span>');
  }
  const fb = esc(t("fbIsland"));
  parts.push(`<button class="isl-btn" data-act="feedback" aria-label="${fb}" title="${fb}">${ico("bug")}</button>`);
  return parts.join("");
}
