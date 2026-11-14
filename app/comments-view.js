/**
 * Розмітка правої панелі «Коментарі» (Deai 0.26.0, етап Б1). Чиста: рядок HTML зі стану; дії — `data-act` для
 * `BAR_ACTIONS` (делегація з `#cmt-panel` в `app.js`). Класи — лише `cmt-*`: `pin`/`cp`/`cbadge` належать коментатору
 * (`tests/principle6.test.mjs`). Тексти людей — лише через `esc()`; мініатюра — лише з `shotSrc`.
 */
import { commentSections, openCount, shotSrc } from "./comments-model.js";
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

// Службове значення, яким коментатор закриває вручну (`commenter/src/comment-layer.js`, `resolveComment`): не текст людини.
const MANUAL_REASON = "resolved manually";

const btn = (act, val, label, icon) => `<button type="button" class="cmt-act" data-act="${act}" data-val="${esc(val)}"`
  + ` aria-label="${esc(label)}" title="${esc(label)}">${icon ? ico(icon) : esc(label)}</button>`;

/** Де був елемент (`meta.ctx` коментатора: `{ active: [кроки/вкладки], heading }`) — для піна, якого зараз нема на екрані;
 *  той самий рядок, що й у картці коментатора (`ctxLine` у `commenter/src/comment-layer.js`). */
function ctxLine(ctx) {
  if (!ctx || typeof ctx !== "object") return "";
  const parts = (Array.isArray(ctx.active) ? ctx.active : []).map((a) => t("cmtCtxStep", String(a)));
  if (ctx.heading) parts.push(t("cmtCtxSection", String(ctx.heading)));
  return parts.join(" · ");
}

function modeTag(m) {
  if (!m || !m.mode || m.mode === "element") return "";
  const txt = m.mode === "multi" ? (m.count > 0 ? t("cmtModeMulti", m.count) : t("cmtModeMultiBare")) : m.mode === "area" ? t("cmtModeArea") : t("cmtModeText");
  return `<span class="cmt-tag">${esc(txt)}</span>`;
}

function cardHTML(c, st, kind) {
  const m = c.meta || {};
  const sel = c.id === st.selectedId ? " cmt-card--sel" : "";
  const closed = c.status === "resolved" ? " cmt-card--closed" : "";
  const head = `<header class="cmt-head"><span class="cmt-n">${esc(c.n)}</span><span class="cmt-who">${esc(c.author || "")}</span>`
    + `${modeTag(m)}<span class="cmt-when">${esc(c.ts || t("cmtNoTime"))}</span></header>`;
  const body = c.id === st.editingId
    ? `<textarea class="cmt-edit" data-val="${esc(c.id)}" aria-label="${esc(t("cmtEdit"))}">${esc(c.text || "")}</textarea>`
      + `<div class="cmt-acts">${btn("cmteditsave", c.id, t("cmtSave"))}${btn("cmteditcancel", c.id, t("cmtCancel"))}</div>`
    : `<p class="cmt-text">${esc(c.text || "")}</p>`;
  const quote = m.sel ? `<p class="cmt-sel">“${esc(String(m.sel).slice(0, 120))}”</p>` : "";
  const vp = m.viewport && m.viewport.w ? `<p class="cmt-vp">${esc(`${m.viewport.w}×${m.viewport.h || "?"}`)}</p>` : "";
  const ctx = ctxLine(m.ctx);
  const where = c.where === "elsewhere" ? `<p class="cmt-note">${esc(t("cmtElsewhere"))}</p>`
    : c.where === "offscreen" ? `<p class="cmt-note">${esc(t("cmtOffscreen"))}</p>`
      + (ctx ? `<p class="cmt-note cmt-ctx">${esc(ctx)}</p>` : "") : "";
  const src = shotSrc(c);
  const shot = src ? `<button type="button" class="cmt-shot" data-act="cmtshot" data-val="${esc(c.id)}" aria-label="${esc(t("cmtShot"))}">`
    + `<img src="${esc(src)}" alt="${esc(t("cmtShot"))}"></button>` : "";
  const done = c.status === "resolved"
    ? `<p class="cmt-done">${esc(c.resolvedV != null ? t("cmtDone", c.resolvedV) : t("cmtClosedPlain"))}</p>`
      + (c.resolveReason && c.resolveReason !== MANUAL_REASON ? `<p class="cmt-reason">${esc(c.resolveReason)}</p>` : "")
    : "";
  const iter = kind === "earlier" && c.iter != null ? `<p class="cmt-iter">${esc(t("cmtIter", c.iter))}</p>` : "";
  let acts = "";
  if (c.id !== st.editingId) {
    if (kind === "open") acts = btn("cmtshow", c.id, t("cmtShow")) + btn("cmtedit", c.id, t("cmtEdit"), "pencil")
      + btn("cmtres", c.id, t("cmtResolve"), "check") + btn("cmtdel", c.id, t("cmtDelete"), "trash");
    else if (kind === "earlier") acts = btn("cmtcarry", c.id, t("cmtCarry", st.snapshot.iteration))
      + btn("cmtdel", c.id, t("cmtDelete"), "trash");
    else acts = btn("cmtreopen", c.id, t("cmtReopen"), "refresh") + btn("cmtdel", c.id, t("cmtDelete"), "trash");
    acts = `<div class="cmt-acts">${acts}</div>`;
  }
  return `<article class="cmt-card${sel}${closed}" data-cid="${esc(c.id)}">${head}${iter}${body}${quote}${vp}${where}${shot}${done}${acts}</article>`;
}

function foldHTML(key, title, items, st, kind) {
  if (!items.length) return "";
  const open = !!(st.expanded && st.expanded[key]);
  return `<section class="cmt-sec cmt-sec--fold"><button type="button" class="cmt-fold" data-act="cmtsec" data-val="${key}"`
    + ` aria-expanded="${open}">${ico(open ? "chevdown" : "chevright")}${esc(`${title} (${items.length})`)}</button>`
    + (open ? items.map((c) => cardHTML(c, st, kind)).join("") : "") + "</section>";
}

/** st: {snapshot, query, selectedId, editingId, expanded:{earlier,closed}, channel:'local'|'project', team, down} */
export function commentsPanelHTML(st) {
  const total = openCount(st.snapshot);
  const seg = st.team
    ? `<div class="cmt-ch" role="group" aria-label="${esc(t("cmtChannel"))}">`
      + ["local", "project"].map((ch) => `<button type="button" data-act="cmtch" data-val="${ch}" aria-pressed="${st.channel === ch}">`
        + `${esc(t(ch === "local" ? "cmtChLocal" : "cmtChTeam"))}</button>`).join("") + "</div>"
    : "";
  const hidden = !!(st.snapshot && st.snapshot.pinsHidden);
  const pins = `<button type="button" class="icon-btn" data-act="cmtpins" aria-pressed="${hidden}"`
    + ` aria-label="${esc(t("cmtPins"))}" title="${esc(t("cmtPins"))}">${ico("eye")}</button>`;
  const top = `<div class="insp-top cmt-top"><span class="panel-title">${esc(t("cmtTitle"))}</span>`
    + `<span class="cmt-total">${total}</span>${seg}${pins}`
    + `<button type="button" class="icon-btn" data-act="comments" aria-label="${esc(t("cmtClose"))}" title="${esc(t("cmtClose"))}">${ico("x")}</button></div>`;
  const search = `<div class="cmt-search"><input type="search" id="cmt-q" value="${esc(st.query || "")}"`
    + ` placeholder="${esc(t("cmtSearch"))}" aria-label="${esc(t("cmtSearch"))}"></div>`;
  let body;
  if (!st.snapshot) {
    body = st.down ? `<p class="cmt-down" role="alert">${esc(t("cmtDown", st.down))}</p>` : `<p class="insp-hint">${esc(t("cmtLoading"))}</p>`;
  } else {
    const s = commentSections(st.snapshot, { query: st.query });
    const none = !s.open.length && !s.earlier.length && !s.closed.length;
    const empty = none ? `<p class="insp-hint">${esc(t(st.query ? "cmtNoMatch" : "cmtEmpty"))}</p>` : "";
    const open = `<section class="cmt-sec" aria-label="${esc(t("cmtOpen"))}"><h3 class="cmt-h">${esc(t("cmtOpen"))}`
      + ` <span>${s.open.length}</span></h3>${s.open.map((c) => cardHTML(c, st, "open")).join("")}</section>`;
    body = empty + open + foldHTML("earlier", t("cmtEarlier"), s.earlier, st, "earlier")
      + foldHTML("closed", t("cmtClosed"), s.closed, st, "closed");
  }
  return `${top}${search}<div class="insp-body cmt-body">${body}</div>`;
}
