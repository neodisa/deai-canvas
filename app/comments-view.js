/**
 * Розмітка правої панелі «Коментарі» (Deai 0.26.0, етап Б1). Чиста: рядок HTML зі стану; дії — `data-act` для
 * `BAR_ACTIONS` (делегація з `#cmt-panel` в `app.js`). Класи — лише `cmt-*`: `pin`/`cp`/`cbadge` належать коментатору
 * (`tests/principle6.test.mjs`). Тексти людей — лише через `esc()`; мініатюра — лише з `shotSrc`.
 */
import { FILTERS, assignedToClaude, audOf, commentSections, filterCounts, openCount, shotSrc } from "./comments-model.js";
import { esc } from "./esc.js";
import { confirmHTML } from "./inline-confirm.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

// Службове значення, яким коментатор закриває вручну (`commenter/src/comment-layer.js`, `resolveComment`): не текст людини.
const MANUAL_REASON = "resolved manually";

const btn = (act, val, label, icon) => `<button type="button" class="${icon ? "cmt-ib" : "cmt-act"}" data-act="${act}" data-val="${esc(val)}"`
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
  const aud = st.dual
    ? `<span class="cmt-aud cmt-aud--${audOf(c)}">${esc(t(audOf(c) === "project" ? "cmtAudTeam" : "cmtAudLocal"))}</span>` : "";
  const badge = st.dual && assignedToClaude(c) ? `<span class="cmt-badge">${esc(t("cmtAssignedBadge"))}</span>` : "";
  const num = `<span class="cmt-n${st.dual && audOf(c) === "local" ? " cmt-n--local" : ""}">${esc(c.n)}</span>`;
  const head = `<header class="cmt-head">${num}<span class="cmt-who">${esc(c.author || "")}</span>`
    + `${aud}${badge}${modeTag(m)}<span class="cmt-when">${esc(c.ts || t("cmtNoTime"))}</span></header>`;
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
  /* «Зроблено · Іт.N» — лише коли пін закрив Claude (`bin/inbox.py resolve` пише в `resolvedV` номер робочої ітерації).
     Ручне закриття в коментаторі теж ставить `resolvedV`, але це його ВНУТРІШНІЙ лічильник версій, а не Іт.N
     (див. `bin/inbox.py`, гілка «уже закритий») — «Зроблено · Іт.1» про пін Іт.6 було б неправдою; знайдено перевіркою
     проти живого канвасу 0.26.0. */
  const byClaude = c.resolvedV != null && c.resolveReason !== MANUAL_REASON;
  const done = c.status === "resolved"
    ? `<p class="cmt-done">${esc(byClaude ? t("cmtDone", c.resolvedV) : t("cmtClosedPlain"))}</p>`
      + (c.resolveReason && c.resolveReason !== MANUAL_REASON ? `<p class="cmt-reason">${esc(c.resolveReason)}</p>` : "")
    : "";
  const iter = kind === "earlier" && c.iter != null ? `<p class="cmt-iter">${esc(t("cmtIter", c.iter))}</p>` : "";
  let acts = "";
  if (c.id === st.delAsk) {
    /* Кошик (етап В): рядок дій стає питанням «Видалити назавжди?» — підтвердження на місці, без нативного `confirm()`. */
    acts = `<div class="cmt-acts cmt-acts--cfm">${confirmHTML({ title: t("cfmDelCmt"), yes: t("cmtDelete"), no: t("cmtCancel"),
      yesAttrs: `data-act="cmtdelyes" data-val="${esc(c.id)}"`, noAttrs: 'data-act="cmtdelno"' })}</div>`;
  } else if (c.id !== st.editingId) {
    if (kind === "open") acts = btn("cmtshow", c.id, t("cmtShow"))
      + (st.dual && audOf(c) === "project"
        ? btn(assignedToClaude(c) ? "cmtunassign" : "cmtassign", c.id, t(assignedToClaude(c) ? "cmtUnassign" : "cmtAssign")) : "")
      + btn("cmtedit", c.id, t("cmtEdit"), "pencil")
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

const FILTER_KEY = { local: "cmtFLocal", project: "cmtFTeam", all: "cmtFAll" };

/** st: {snapshot, query, selectedId, editingId, delAsk (id картки з питанням «Видалити назавжди?»), expanded:{earlier,closed}, filter:'local'|'project'|'all', dual, teamDown, fresh:Set|null, down} */
export function commentsPanelHTML(st) {
  const filter = FILTERS.includes(st.filter) ? st.filter : "local";
  const hidden = !!(st.snapshot && st.snapshot.pinsHidden);
  const pins = `<button type="button" class="icob" data-act="cmtpins" aria-pressed="${hidden}"`
    + ` aria-label="${esc(t("cmtPins"))}" title="${esc(t("cmtPins"))}">${ico("eye")}</button>`;
  const close = `<button type="button" class="icob" data-act="comments" aria-label="${esc(t("cmtClose"))}" title="${esc(t("cmtClose"))}">${ico("x")}</button>`;
  // Без командного каналу фільтра нема — тоді число відкритих лишається в шапці.
  const total = st.dual ? "" : `<span class="cmt-total">${openCount(st.snapshot)}</span>`;
  const top = `<div class="insp-top cmt-top">${ico("comment")}<span class="panel-title">${esc(t("cmtTitle"))}</span>${total}${pins}${close}</div>`;
  const search = `<div class="cmt-search"><input type="search" id="cmt-q" value="${esc(st.query || "")}"`
    + ` placeholder="${esc(t("cmtSearch"))}" aria-label="${esc(t("cmtSearch"))}"></div>`;
  let seg = "";
  if (st.dual) {
    const n = filterCounts(st.snapshot, st.fresh);
    seg = `<div class="cmt-filter" role="group" aria-label="${esc(t("cmtFilter"))}">`
      + FILTERS.map((f) => `<button type="button" data-act="cmtfilter" data-val="${f}" aria-pressed="${filter === f}">`
        + `<span>${esc(t(FILTER_KEY[f]))}</span><span class="cmt-fn">${n[f]}</span>`
        + (f === "project" && n.fresh ? `<span class="cmt-fnew" title="${esc(t("cmtNewTitle"))}">+${n.fresh}</span>` : "")
        + "</button>").join("") + "</div>";
  }
  const down = st.teamDown ? `<p class="cmt-teamdown" role="alert">${esc(t("cmtTeamDown", st.teamDown))}</p>` : "";
  let body;
  if (!st.snapshot) {
    body = st.down ? `<p class="cmt-down" role="alert">${esc(t("cmtDown", st.down))}</p>` : `<p class="insp-hint">${esc(t("cmtLoading"))}</p>`;
  } else {
    const s = commentSections(st.snapshot, { query: st.query, filter: st.dual ? filter : "all", fresh: st.fresh });
    const none = !s.fresh.length && !s.open.length && !s.earlier.length && !s.closed.length;
    // Коментарі є, але запит чи активний фільтр адресата сховали всі — «нема збігів», а не «ще немає».
    const hasAny = Array.isArray(st.snapshot.comments) && st.snapshot.comments.length > 0;
    const empty = none ? `<p class="insp-hint">${esc(t(st.query || hasAny ? "cmtNoMatch" : "cmtEmpty"))}</p>` : "";
    const fresh = s.fresh.length
      ? `<section class="cmt-sec cmt-sec--new" aria-label="${esc(t("cmtNewTitle"))}"><h3 class="cmt-h cmt-h--new">${esc(t("cmtNewTitle"))}`
        + ` <span>${s.fresh.length}</span></h3>${s.fresh.map((c) => cardHTML(c, st, "open")).join("")}</section>` : "";
    const open = `<section class="cmt-sec" aria-label="${esc(t("cmtOpen"))}"><h3 class="cmt-h">${esc(t("cmtOpen"))}`
      + ` <span>${s.open.length}</span></h3>${s.open.map((c) => cardHTML(c, st, "open")).join("")}</section>`;
    body = empty + fresh + open + foldHTML("earlier", t("cmtEarlier"), s.earlier, st, "earlier")
      + foldHTML("closed", t("cmtClosed"), s.closed, st, "closed");
  }
  return `${top}${search}${seg}${down}<div class="insp-body cmt-body">${body}</div>`;
}
