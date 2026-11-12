/**
 * Розмітка оновлення інструмента (0.23.0): пігулка в смузі й діалог «Оновлення» для `askForm` (`app/ask.js`). Чиста розмітка, як
 * `trust-view.js`: ні DOM, ні fetch. Проводку (опит, `POST /api/update-apply`, перезавантаження) дає `openUpdateDialog` в `app.js`.
 *
 * Контракт `askForm`: один `<form role="dialog" aria-modal="true" aria-labelledby="up-h">`; «Оновити» — `button[type=submit][data-a=ok]`
 * (`disabled` з видимою причиною `.up-why`, коли `blocked`/`restartFailed`/`applying`); «Скасувати» — `data-a=cancel` з `data-autofocus`
 * (Enter, натиснутий не дивлячись, оновлення не запускає); слот помилки `[data-form-error]`; рядок стану `[data-up-status]`; блок опису
 * `[data-up-notes]` перемальовується по відповіді `GET /api/update-notes` тією ж `updateNotesHTML`.
 *
 * ⛔ Усе, що прийшло з сервера (версії, дата, ТІЛО CHANGELOG — звичайний текст із можливими `<`/`>`, код причини, адреса команди) —
 * лише через `esc()`. Розмітка з даних тут не збирається ніде, крім як із вже екранованих рядків.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { blockedHelp, notesReasonClass, notesToBlocks } from "./update-model.js";

/** Пігулка в смузі. `m` — контрол `update` з `bar-model.js`: `{version, restart}`. */
export function updatePillHTML(m) {
  if (!m) return "";
  const label = m.restart ? t("upPillRestart") : t("upPill", m.version);
  const title = m.restart ? t("upPillRestartTitle") : t("upPillTitle", m.version);
  return `<button class="ctl ctl--out upd-pill" data-act="update" title="${esc(title)}" aria-label="${esc(title)}">`
    + `${ico(m.restart ? "warn" : "down")}<span class="lbl-upd">${esc(label)}</span></button>`;
}

/* Мінімальне форматування рядка: ПЕРШЕ екранування (esc), потім на вже безпечному тексті — `код` і **жирне** (одним проходом зліва
   направо: код не розбирається всередині, жирне може містити код). Маркер без пари лишається буквальним; пара не перетинає рядок
   (`[^…\n]`), а порожні пари (`****`, ``` `` ```) форматуванням не вважаються. Нових тегів, окрім <strong>/<code>, не зʼявляється:
   після esc у тексті немає `<`, а самі маркери `*`/`` ` `` esc не чіпає. */
function inlineHTML(text) {
  const safe = esc(text);
  return safe.replace(/`([^`\n]+)`|\*\*([^*\n]+?)\*\*/g, (_m, code, bold) => (code !== undefined
    ? `<code>${code}</code>`
    : `<strong>${bold.replace(/`([^`\n]+)`/g, "<code>$1</code>")}</strong>`));
}

/* Блоки одного розділу: підряд ідучі пункти — один `<ul>`. Текст — лише `esc`. */
function blocksHTML(blocks) {
  let out = "";
  let list = "";
  const flush = () => { if (list) { out += `<ul class="up-list">${list}</ul>`; list = ""; } };
  for (const b of blocks) {
    if (b.kind === "li") { list += `<li>${inlineHTML(b.text)}</li>`; continue; }
    flush();
    out += b.kind === "h" ? `<p class="up-h3">${esc(b.text)}</p>` : `<p class="up-p">${inlineHTML(b.text)}</p>`;
  }
  flush();
  return out;
}

/**
 * Вміст блоку «Що нового». `sections === null` — відповідь ще летить; `reason` — причина, з якої опису нема (`updater.notes`):
 * коротка фраза «Опис змін зараз недоступний» + клас причини, а «Оновити» лишається доступним (опис — не умова оновлення).
 */
export function updateNotesHTML({ sections = null, reason = null } = {}) {
  if (sections === null && !reason) return `<p class="up-note" role="status">${esc(t("upNotesLoading"))}</p>`;
  if (reason) return `<p class="up-note">${esc(t("upNotesUnavail", notesReasonClass(reason)))}</p>`;
  const list = notesToBlocks(sections);
  if (!list.length) return `<p class="up-note">${esc(t("upNotesNone"))}</p>`;
  return list.map((s) => `<section class="up-sec"><h3 class="up-sec-h">${esc(`${s.version} · ${s.date}`)}</h3>`
    + `${blocksHTML(s.blocks)}</section>`).join("");
}

const STATE_KEYS = { offline: "upSt_offline", error: "upSt_error", disabled: "upSt_disabled", "no-git": "upSt_no_git" };

/**
 * Діалог оновлення. `d = {current, latest, blocked, state, reason, sections, notesReason, applying, error, restartFailed}` — `blocked`
 * з `GET /api/update` (код або `null`), `state`/`reason` — остання перевірка (`null` — ще не було), `restartFailed` — після `202` сервер не
 * зміг перезапуститись сам.
 */
export function updateDialogHTML(d) {
  const x = d || {};
  const help = x.blocked ? blockedHelp(x.blocked, x.latest) : null;
  const restart = x.restartFailed === true;
  const stateKey = STATE_KEYS[x.state];
  const cmd = help && help.command
    ? `<div class="up-cmd"><code>${esc(help.command)}</code>`
      + `<button type="button" data-copy="${esc(help.command)}">${esc(t("upCopyCmd"))}</button></div>`
    : "";
  const why = restart
    ? `<p class="up-why up-restart" id="up-why" role="alert">${ico("warn", 13)}<span>${esc(t("upRestartManual"))}</span></p>`
    : help
      ? `<p class="up-why" id="up-why" role="status">${ico("warn", 13)}<span>${esc(t(help.key, help.code))}</span></p>${cmd}`
      : "";
  const off = !!(help || restart || x.applying);
  return `<form class="cv-form up" novalidate role="dialog" aria-modal="true" aria-labelledby="up-h"${x.applying ? ' aria-busy="true"' : ""}>
    <h2 class="cv-form-h" id="up-h">${esc(t("upTitle"))}</h2>
    <p class="up-ver">${esc(t("upFromTo", x.current ?? "?", x.latest ?? "?"))}</p>
    ${why}
    ${stateKey ? `<p class="up-note">${esc(t(stateKey))}</p>` : ""}
    <p class="up-h3">${esc(t("upWhatsNew"))}</p>
    <div class="up-notes" data-up-notes role="region" tabindex="0" aria-label="${esc(t("upWhatsNew"))}">${updateNotesHTML({ sections: x.sections ?? null, reason: x.notesReason ?? null })}</div>
    <p class="up-st" data-up-status role="status"${x.applying ? "" : " hidden"}>${x.applying ? esc(t("upApplying")) : ""}</p>
    <p class="cv-form-err" id="cv-form-err" role="alert" data-form-error${x.error ? "" : " hidden"}>${esc(x.error || "")}</p>
    <div class="cv-ask-row">
      <button type="button" data-a="cancel" data-autofocus>${esc(t(restart ? "askClose" : "askCancel"))}</button>
      <button type="submit" data-a="ok"${off ? " disabled" : ""}${restart ? " hidden" : ""}${off && !x.applying ? ' aria-describedby="up-why"' : ""}>${esc(t(x.applying ? "upApplying" : "upApply"))}</button>
    </div>
  </form>`;
}
