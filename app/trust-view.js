/**
 * Діалог довіри своєму модулю простору (Deai 0.7.0, етап 3c; спека
 * `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`, «Діалог довіри»). Чиста розмітка для `askForm`
 * (`app/ask.js`), як `space-dialogs.js`: ні DOM, ні fetch. Проводку (запит довіри, повторне відкриття, «Забрати
 * довіру») дає `openTrust` в `app.js`.
 *
 *   trustDialogHTML(d)  d — `trust` з `GET /api/module-trust` ({id, name, version, roles, settings, path, state, record,
 *                       refused?, hash?, files?, removed?, total?}) + `reopened` (тека змінилась, поки діалог був відкритий).
 *
 * Контракт `askForm`: один `<form role="dialog" aria-modal="true" aria-labelledby="tr-h">`; «Довіряю» —
 * `button[type=submit][data-a=ok]`; «Скасувати»/«Закрити» — `data-a=cancel` з `data-autofocus` (інакше фокус ліг би на
 * першу кнопку, і Enter, натиснутий не дивлячись, довіряв би); слот помилки `[data-form-error]`; рядок очікування
 * системного вікна `[data-tr-wait]`; «Забрати довіру» — `data-tr="untrust"`.
 *
 * ⛔ Усе з диска (назва, версія, шлях, імена файлів, мітки налаштувань, деталь відмови) — лише через `esc()` і обрізане
 * до `TR_MAX`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { trustWhyKey } from "./connections-model.js";
import { roleTitle } from "./connections-view.js";
import { PAGE_PERMS } from "./page-rules.js";

/** Найдовший рядок із диска в діалозі. */
export const TR_MAX = 80;
/** Скільки імен прибраних файлів перелічує рядок «Прибрано»; решта — «і ще N» (їх може бути до 200). */
export const TR_REMOVED_MAX = 10;
/** Стеля запиту довіри: сервер чекає людину в системному вікні до 120 с (`module_trust.CONFIRM_TIMEOUT`). */
export const TRUST_POST_TIMEOUT_MS = 150000;

/* Як `module_trust._clean`: СПЕРШУ прибрати `Cc`/`Cf`/`Cs`/`Zl`/`Zp` (керування, bidi-перевизначення, самотні сурогати),
   далі міряти й різати в code points, а не в одиницях UTF-16 — тоді назва й шлях у діалозі збігаються із системним вікном і
   для не-BMP (емодзі), а зріз не лишає самотнього сурогата. */
const clean = (s) => String(s ?? "").replace(/[\p{Cc}\p{Cf}\p{Cs}\p{Zl}\p{Zp}]/gu, "");
const cut = (s) => {
  const v = Array.from(clean(s));
  return v.length > TR_MAX ? `${v.slice(0, TR_MAX - 1).join("")}…` : v.join("");
};
/** Шлях — із СЕРЕДИНИ (голова, «…», хвіст): у шляху важливий кінець, тека модуля. Та сама формула, що в системного вікна
 *  (`module_trust._clean(s, n=80, middle=True)`: `head = (n-1)//3`) — діалог і вікно мають показувати однаковий шлях. */
export const cutMid = (s) => {
  const v = Array.from(clean(s));
  if (v.length <= TR_MAX) return v.join("");
  const head = Math.floor((TR_MAX - 1) / 3);
  return `${v.slice(0, head).join("")}…${v.slice(v.length - (TR_MAX - 1 - head)).join("")}`;
};
const list0 = (x) => (Array.isArray(x) ? x : []);

/** Розмір людині: до 1 КБ — байти, далі КБ чи МБ з однією цифрою після коми (роздільник — у словнику). */
export function sizeText(n) {
  const b = Math.max(0, Math.floor(Number(n) || 0));
  if (b < 1024) return t("trSizeB", String(b));
  if (b < 1024 * 1024) return t("trSizeKb", (b / 1024).toFixed(1));
  return t("trSizeMb", (b / (1024 * 1024)).toFixed(1));
}

function asksHTML(settings) {
  const items = list0(settings).filter((s) => s && typeof s.key === "string");
  if (!items.length) return `<p class="tr-none">${esc(t("trAsksNone"))}</p>`;
  return `<p class="tr-h3">${esc(t("trAsks"))}</p><ul class="tr-asks">${items.map((s) => {
    const mark = s.type === "secret"
      ? ` <span class="tr-mark">${esc(t(s.public === true ? "trSecretPublic" : "trSecret"))}</span>` : "";
    return `<li>${esc(cut(s.label || s.key))}${mark}</li>`;
  }).join("")}</ul>`;
}

/* Інструменти острівця й дії модуля (api 2): по рядку, лише коли є що показати. Мітки — з маніфесту теки (з диска): `cut` + `esc`. */
function extHTML(items, key) {
  const names = list0(items).filter((x) => x && typeof x.label === "string").map((x) => cut(x.label));
  return names.length ? `<p class="tr-ext"><span class="tr-h3">${esc(t(key))}</span> ${esc(names.join(", "))}</p>` : "";
}

/* Права на сторінки макета, які заявили інструменти (`page`): об'єднання за всіма інструментами, порядок PAGE_PERMS, без дублів. */
function pageHTML(tools) {
  const used = new Set();
  for (const x of list0(tools)) if (x && Array.isArray(x.page)) for (const p of x.page) used.add(p);
  const perms = PAGE_PERMS.filter((p) => used.has(p));
  return perms.length
    ? `<p class="tr-h3">${esc(t("trustPage"))}</p><ul class="tr-page">${perms.map((p) => `<li>${esc(t("trustPage" + p[0].toUpperCase() + p.slice(1)))}</li>`).join("")}</ul>` : "";
}

/* Позначки «новий»/«змінено» — лише коли є запис довіри: без нього кожен файл «новий», і позначка нічого не каже. */
function filesHTML(d) {
  const files = list0(d.files).filter((f) => f && typeof f.path === "string");
  const removed = list0(d.removed).filter((f) => f && typeof f.path === "string");
  const marks = d.record === true;
  const changed = files.filter((f) => f.change === "new" || f.change === "changed").length + removed.length;
  const head = t("trFiles", Number(d.total?.files ?? files.length), sizeText(d.total?.bytes ?? 0))
    + (d.state === "changed" ? ` · ${t("trChangedCount", changed)}` : "");
  const rows = files.map((f) => {
    const m = marks && (f.change === "new" || f.change === "changed")
      ? `<span class="tr-mark">${esc(t(f.change === "new" ? "trNew" : "trChanged"))}</span>` : "";
    return `<li><code>${esc(cut(f.path))}</code><span class="tr-size">${esc(sizeText(f.size))}</span>${m}</li>`;
  }).join("");
  /* Імен — не більше TR_REMOVED_MAX: сервер віддає до 200 прибраних, а кожне до TR_MAX знаків. Повний лічильник — у шапці. */
  const goneNames = removed.slice(0, TR_REMOVED_MAX).map((f) => cut(f.path));
  if (removed.length > TR_REMOVED_MAX) goneNames.push(t("trRemovedMore", removed.length - TR_REMOVED_MAX));
  const gone = removed.length
    ? `<p class="tr-removed">${esc(t("trRemoved", goneNames.join(", ")))}</p>` : "";
  return `<p class="tr-h3">${esc(head)}</p>`
    + `<ul class="tr-files" tabindex="0" aria-label="${esc(t("trFilesList"))}">${rows}</ul>${gone}`;
}

/** Діалог довіри. `state: refused` — без «Довіряю» й попередження: лише причина і «Закрити». */
export function trustDialogHTML(d) {
  const name = cut(d?.name || d?.id || "");
  const refused = d?.state === "refused";
  const title = refused ? t("trTitleRefused", name) : (d?.state === "changed" ? t("trTitleNew", name) : t("trTitle", name));
  const roles = list0(d?.roles).map((r) => cut(roleTitle(r))).join(" · ");
  const meta = [d?.version ? `v${cut(d.version)}` : "", roles].filter(Boolean).join(" · ");
  const print = !refused && d?.hash ? ` · ${esc(t("trFingerprint", String(d.hash).slice(0, 12)))}` : "";
  const body = refused
    ? `<p class="tr-refused" role="alert">${ico("warn", 13)}<span>${esc(t("trRefused", t(trustWhyKey(d.refused?.code))))}`
      + `${d.refused?.detail ? `<span class="cn-why-detail">${esc(cut(d.refused.detail))}</span>` : ""}</span></p>`
    : `<div class="tr-warn">${ico("warn")}<div><p>${esc(t("trWarn"))}</p>`
      + `${list0(d?.roles).includes("comments") ? `<p>${esc(t("trWarnComments"))}</p>` : ""}`
      + `<p>${esc(t("trWarnSystem"))}</p></div></div>${asksHTML(d.settings)}${extHTML(d.tools, "trustTools")}${pageHTML(d.tools)}${extHTML(d.actions, "trustActions")}${filesHTML(d)}`;
  const untrust = d?.record === true
    ? `<button type="button" class="tr-untrust" data-tr="untrust">${esc(t("cnUntrust"))}</button>` : "";
  return `<form class="cv-form tr" novalidate role="dialog" aria-modal="true" aria-labelledby="tr-h">
    ${d?.reopened ? `<p class="tr-reopened" role="status">${esc(t("trReopened"))}</p>` : ""}
    <h2 class="cv-form-h" id="tr-h">${esc(title)}</h2>
    <p class="tr-meta">${esc(meta)}</p>
    <p class="tr-path"><code>${esc(cutMid(d?.path))}</code>${print}</p>
    ${body}
    <p class="tr-wait" data-tr-wait role="status" hidden>${esc(t("trWaiting"))}</p>
    <p class="cv-form-err" id="cv-form-err" role="alert" data-form-error hidden></p>
    <div class="cv-ask-row">${untrust}
      <button type="button" data-a="cancel" data-autofocus>${esc(t(refused ? "trClose" : "askCancel"))}</button>
      ${refused ? "" : `<button type="submit" data-a="ok">${esc(t("trTrust"))}</button>`}</div>
  </form>`;
}
