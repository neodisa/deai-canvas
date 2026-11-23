/**
 * Меню картки задачі (етап Д, 0.30.0): «⋯» на кадрі, правий клік, Shift+F10. Чиста розмітка; відкриття, позиція
 * (`positionCtxMenu`), клавіші й дії — `app.js`. Пункти — `[data-th][data-id]`: клік ловить той самий обробник екрана
 * (`wireHome`), що й решту `data-th`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { taskKey } from "./tasks-model.js";
import { safeUrl } from "./tasks-home.js";

/** Пункти меню: обʼєкти `{th, icon, key, kbd?, danger?, href?}` і `"sep"` (роздільник). */
export function taskMenuItems(x, { trash = false, actions = [] } = {}) {
  if (trash) {
    return [{ th: "restore", icon: "refresh", key: "taskRestore" }, "sep",
      { th: "purge", icon: "trash", key: "taskPurge", danger: true }];
  }
  const out = [{ th: "rename", icon: "pencil", key: "taskRename", kbd: "F2" },
    { th: "tags", icon: "sliders", key: "taskTagsMenu" }];
  const u = safeUrl(x.published);
  if (u) out.push({ th: "preview", icon: "ext", key: "taskPreviewOpen", href: u });
  /* Дії модулів: окрема група перед «Видалити»; `label` сирий (екранує розмітка), значення — ключ «модуль/дія». */
  if (actions.length) out.push("sep", ...actions.map((a) => ({ th: "modact", icon: "puzzle", label: a.label, v: a.key })));
  out.push("sep", { th: "delete", icon: "trash", key: "taskDelete", kbd: "⌫", danger: true });
  return out;
}

export function taskMenuHTML(x, opts = {}) {
  const id = esc(x.id);
  const items = taskMenuItems(x, opts).map((i) => {
    if (i === "sep") return '<hr role="separator">';
    const kbd = i.kbd ? `<kbd>${esc(i.kbd)}</kbd>` : "";
    const cls = i.danger ? ' class="danger"' : "";
    const body = `${ico(i.icon, 15)}<span>${esc(i.label ?? t(i.key))}</span>${kbd}`;
    const val = i.v != null ? ` data-v="${esc(i.v)}"` : "";
    return i.href
      ? `<a role="menuitem" tabindex="-1"${cls} data-th="${i.th}" data-id="${id}" href="${esc(i.href)}" target="_blank" rel="noopener">${body}</a>`
      : `<button type="button" role="menuitem" tabindex="-1"${cls} data-th="${i.th}" data-id="${id}"${val}>${body}</button>`;
  }).join("");
  return `<div id="th-menu" class="cv-ctx th-menu" role="menu" aria-label="${esc(t("thMenuAria", opts.trash ? x.id : taskKey(x)))}">${items}</div>`;
}
