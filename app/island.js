/**
 * Інструменти острівця внизу робочої зони (0.25.0 / 0.26.0): коментарі (обидва види) | інспектор (лише «Макет» —
 * він працює по живому DOM, у «Огляді» кадри — знімки) | баг/ідея останнім. Сегмент стану Claude — окремий вузол `#claude-hud` (`role="status"`,
 * його веде `paintClaude` в `app.js`), бо жива область не сміє містити кнопок.
 * Дії — ті самі `BAR_ACTIONS` (`comments`, `inspector`, `feedback`): делегація з `#hud` в `app.js`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

/** Режим коментатора → іконка (форми ті самі, що в його власній смужці). Невідомий режим кнопки не отримує. */
const MODE_ICON = { element: "element", text: "text", multi: "layers", area: "area" };

/** Кнопка «Коментарі»: нові від команди (амбер, `isl-count--new`) важливіші за «відкритих усього» — число одне, не два. */
function commentsBtn({ commentsOn, commentsCount, commentsNew }) {
  const n = commentsNew > 0
    ? `<span class="isl-count isl-count--new" aria-hidden="true">${commentsNew > 99 ? "99+" : commentsNew}</span>`
    : commentsCount > 0
      ? `<span class="isl-count" aria-hidden="true">${commentsCount > 99 ? "99+" : commentsCount}</span>` : "";
  const label = commentsNew > 0 ? t("cmtIslandNew", commentsNew) : t("cmtIsland", commentsCount);
  return `<button class="isl-btn${commentsOn ? " isl-btn--on" : ""}" data-act="comments" aria-pressed="${commentsOn}"`
    + ` aria-label="${esc(label)}" title="${esc(t("cmtKey"))}">${ico("comment")}${n}</button>`;
}

function inspectorBtn(inspectorOn) {
  return `<button class="isl-btn${inspectorOn ? " isl-btn--on" : ""}" data-act="inspector" aria-pressed="${inspectorOn}"`
    + ` aria-label="${esc(t("inspector"))}" title="${esc(t("inspectorKey"))}">${ico("inspect")}</button>`;
}

/** «Сховати інтерфейс» — лише в превʼю (0.32.0): чистий перегляд макета, підказка з акордом. */
function cleanBtn() {
  const tip = esc(t("islandCleanKey"));
  return `<button class="isl-btn" data-act="clean" aria-label="${esc(t("islandClean"))}" title="${tip}">${ico("clean")}</button>`;
}

/** Набори кнопок превʼю — у порядку й під ключами, відомими лише сюди (`bug`/AI у превʼю нема за визначенням). */
const PREVIEW_TOOLS = ["cmt", "insp", "clean"];

/**
 * `tools` (0.32.0): явний набір для ЗОВНІШНЬОГО превʼю — `['cmt', 'insp', 'clean']` (невідоме ігнорується). Без нього — набір
 * Deai, як і було (коментарі | інспектор | баг), байт у байт. Роздільник — лише між «коментарі+інспектор» і «сховати».
 */
export function islandToolsHTML({ screen = "task", mode = "layout", inspectorOn = false, commentsOn = false, commentsCount = 0, commentsNew = 0, commentTool = null, tools = null } = {}) {
  if (Array.isArray(tools)) {
    const want = PREVIEW_TOOLS.filter((k) => tools.includes(k));
    const head = want.filter((k) => k !== "clean").map((k) => (k === "cmt"
      ? commentsBtn({ commentsOn, commentsCount, commentsNew }) : inspectorBtn(inspectorOn)));
    const tail = want.includes("clean") ? [cleanBtn()] : [];
    return head.join("") + (head.length && tail.length ? '<span class="isl-sep" aria-hidden="true"></span>' : "") + tail.join("");
  }
  const parts = [];
  if (screen === "task") {
    parts.push(commentsBtn({ commentsOn, commentsCount, commentsNew }));
    /* Фільтр ПЕРШИМ (лише власні ключі MODE_ICON — не `constructor`/`__proto__`), потім потрібно > 1 відомого режиму.
       На «Огляді» режим один — кнопок режимів нема за будь-яких даних інструмента. */
    const known = commentsOn && mode !== "overview" && commentTool && Array.isArray(commentTool.modes)
      ? commentTool.modes.filter((m) => typeof m === "string" && Object.hasOwn(MODE_ICON, m)) : [];
    if (known.length > 1) {
      const modes = known;
      parts.push('<span class="isl-sep" aria-hidden="true"></span>');
      parts.push(`<div class="isl-modes" role="group" aria-label="${esc(t("islModes"))}">`
        + modes.map((m) => {
          const on = commentTool.mode === m;
          const tip = esc(t(`islMode_${m}`));
          return `<button class="isl-btn${on ? " isl-btn--on" : ""}" data-act="cmtmode" data-val="${esc(m)}" aria-pressed="${on}"`
            + ` aria-label="${tip}" title="${tip}">${ico(MODE_ICON[m])}</button>`;
        }).join("") + "</div>");
      if (commentTool.canFreeze) {
        const tip = esc(t("islFreeze"));
        parts.push(`<button class="isl-btn isl-freeze${commentTool.freeze ? " isl-freeze--on" : ""}" data-act="cmtfreeze"`
          + ` aria-pressed="${!!commentTool.freeze}" aria-label="${tip}" title="${tip}">${ico("freeze")}</button>`);
      }
      parts.push('<span class="isl-sep" aria-hidden="true"></span>');
    }
    if (mode === "layout") {
      parts.push(inspectorBtn(inspectorOn));
    }
    parts.push('<span class="isl-sep" aria-hidden="true"></span>');
  }
  const fb = esc(t("fbIsland"));
  parts.push(`<button class="isl-btn" data-act="feedback" aria-label="${fb}" title="${fb}">${ico("bug")}</button>`);
  return parts.join("");
}
