/**
 * Розмітка відгуку (0.23.0) для `askForm` (`app/ask.js`). Чиста розмітка: ні DOM, ні fetch. Проводку (запити, кільце помилок, тост)
 * дає `openFeedback` в `app.js`.
 *
 * Контракт `askForm`: один `<form data-form="feedback" role="dialog" aria-modal="true">`; відправка — `button[type=submit][data-a=ok]`;
 * `data-a=cancel`; слот помилки `[data-form-error]` (`#cv-form-err`, на нього вказує `aria-describedby` текстового поля).
 *
 * ⛔ Усе, що не з нашого словника (текст людини, JSON діагностики з повідомленнями помилок) — лише через `esc()`; JSON іде в `<pre>`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { TEXT_MAX } from "./feedback-model.js";

/** Вміст `<pre>` «Що буде надіслано»: JSON або фраза, що перегляд недоступний. */
export function previewPreHTML(text) {
  return esc(text || t("fbPreviewNone"));
}

/** `d = {kind, text, contact, includeDiag, includeShot, shot:{available, bytes, reasonKey}, shotUrl, previewText, previewFailed}`.
 *  `shotUrl` — локальна адреса знімка (мініатюра показується, коли знімок прикладено); `previewFailed` — перегляду нема: діагностика
 *  за замовчуванням ВИМКНЕНА (людина не бачила, що піде) і біля галочки стоїть примітка. */
export function feedbackDialogHTML(d) {
  const x = d || {};
  const shot = x.shot || { available: false, reasonKey: "fbShotNone" };
  const kind = x.kind === "idea" ? "idea" : "bug";
  const shotWhy = `<span class="fb-why" id="fb-shot-why" data-fb-shot-why${shot.available ? " hidden" : ""}>${esc(t(shot.reasonKey || "fbShotNone"))}</span>`;
  const thumb = x.shotUrl
    ? `<img class="fb-thumb" data-fb-thumb src="${esc(x.shotUrl)}" alt="${esc(t("fbShotAlt"))}" decoding="async" loading="lazy"${shot.available && x.includeShot ? "" : " hidden"}>`
    : "";
  const diagOn = x.previewFailed ? false : x.includeDiag !== false;
  const diagWhy = `<span class="fb-why" id="fb-diag-why" data-fb-diag-why${x.previewFailed ? "" : " hidden"}>${esc(t("fbDiagOff"))}</span>`;
  return `<form class="cv-form fb" data-form="feedback" novalidate role="dialog" aria-modal="true" aria-labelledby="fb-h">
    <h2 class="cv-form-h" id="fb-h">${esc(t("fbTitle"))}</h2>
    <div class="cv-field" role="radiogroup" aria-label="${esc(t("fbKind"))}">
      <div class="fb-kinds">
        <label class="cn-check"><input type="radio" name="kind" value="bug"${kind === "bug" ? " checked" : ""}>${esc(t("fbKindBug"))}</label>
        <label class="cn-check"><input type="radio" name="kind" value="idea"${kind === "idea" ? " checked" : ""}>${esc(t("fbKindIdea"))}</label>
      </div>
    </div>
    <div class="cv-field">
      <label for="fb-text">${esc(t("fbText"))}</label>
      <textarea id="fb-text" name="text" rows="5" required maxlength="${TEXT_MAX * 2}" data-autofocus aria-describedby="cv-form-err"
        placeholder="${esc(t("fbTextPh"))}">${esc(x.text || "")}</textarea>
    </div>
    <div class="cv-field">
      <label for="fb-contact">${esc(t("fbContact"))}</label>
      <input id="fb-contact" name="contact" type="text" autocomplete="off" value="${esc(x.contact || "")}" placeholder="${esc(t("fbContactPh"))}">
    </div>
    <div class="cv-field fb-opts">
      <label class="cn-check" for="fb-diag"><input type="checkbox" id="fb-diag" name="diag"${diagOn ? " checked" : ""}${x.previewFailed ? ' aria-describedby="fb-diag-why"' : ""}>${esc(t("fbDiag"))}</label>
      ${diagWhy}
      <label class="cn-check" for="fb-shot"><input type="checkbox" id="fb-shot" name="shot"${shot.available && x.includeShot ? " checked" : ""}${shot.available ? "" : " disabled"} aria-describedby="fb-shot-why">${esc(t("fbShot"))}</label>
      ${shotWhy}
      ${thumb}
    </div>
    <details class="fb-preview" data-fb-preview>
      <summary>${esc(t("fbWhat"))}</summary>
      <p class="fb-hint">${esc(t("fbWhatHint"))}</p>
      <pre class="fb-pre" data-fb-pre tabindex="0">${previewPreHTML(x.previewText)}</pre>
    </details>
    <p class="cv-form-err" id="cv-form-err" role="alert" data-form-error hidden></p>
    <div class="cv-ask-row">
      <button type="button" data-a="cancel">${esc(t("askCancel"))}</button>
      <button type="submit" data-a="ok">${esc(t("fbSend"))}</button>
    </div>
  </form>`;
}

/** Кнопка в смузі. `m` — контрол `feedback` з `bar-model.js`. Лише іконка: підпис несуть `title`/`aria-label`. */
export function feedbackBtnHTML(m) {
  if (!m) return "";
  const label = esc(t("fbOpen"));
  return `<button class="ctl ctl--icon fb-btn" data-act="feedback" title="${label}" aria-label="${label}">${ico("comment")}</button>`;
}
