/**
 * Розмітка правої панелі «Коментарі» (Deai 0.26.0, етап Б1). Чиста: рядок HTML зі стану; дії — `data-act` для
 * `BAR_ACTIONS` (делегація з `#cmt-panel` в `app.js`). Класи — лише `cmt-*`: `pin`/`cp`/`cbadge` належать коментатору
 * (`tests/principle6.test.mjs`). Тексти людей — лише через `esc()`; мініатюра — лише з `shotSrc`.
 */
import { FILTERS, assignedToClaude, audOf, commentSections, filterCounts, openCount, repliesOf, shotSrc } from "./comments-model.js";
import { esc } from "./esc.js";
import { confirmHTML } from "./inline-confirm.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

// Службове значення, яким коментатор закриває вручну (`commenter/src/comment-layer.js`, `resolveComment`): не текст людини.
const MANUAL_REASON = "resolved manually";

const btn = (act, val, label, icon, extra = "") => `<button type="button" class="${icon ? "cmt-ib" : "cmt-act"}${extra}" data-act="${act}" data-val="${esc(val)}"`
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

/** Коди, якими коментатор позначає відсутній знімок (`meta.shotMiss`, рядок; `commenter/src/comment-layer.js`). Невідомий код — мовчимо. */
const SHOT_MISS = ["too-big", "no-lib", "timeout", "render", "detached", "upload"];

/** Хто автор відповіді: агент (`agent === true`) — «AI», решта — імʼя з відповіді. */
const replyWho = (r) => (r.agent === true ? t("cmtAudLocal") : String(r.author || ""));
/** `ДД.ММ.РРРР ГГ:ХХ` → `ДД.ММ ГГ:ХХ` для згорнутого рядка; інший формат лишається як є. */
const shortWhen = (ts) => {
  const m = /^(\d{2}\.\d{2})\.\d{4} (\d{2}:\d{2})$/.exec(String(ts || ""));
  return m ? `${m[1]} ${m[2]}` : String(ts || "");
};

/** Одна відповідь у гілці. `own`/`del` — права на дії (лише відкритий коментар); `key` — `cid|rid`. */
function replyHTML(c, r, st, open) {
  const key = `${c.id}|${r.id}`;
  const isFresh = !!(st.fresh && st.fresh.has(r.id));
  const editing = open && st.replyEdit === key;
  const agent = r.agent === true;
  const who = `<span class="cmt-rwho${agent ? " cmt-ragent" : ""}">${esc(replyWho(r))}</span>`;
  let acts = "";
  if (open && !editing) {
    if (typeof st.isOwnReply === "function" && st.isOwnReply(r)) acts += btn("cmtredit", key, t("cmtReplyEdit"), "pencil");
    if (typeof st.canDeleteReply === "function" && st.canDeleteReply(r)) acts += btn("cmtrdel", key, t("cmtReplyDelete"), "trash");
  }
  const head = `<div class="cmt-rhead">${who}${isFresh ? `<span class="cmt-rnew">${esc(t("cmtReplyNewChip"))}</span>` : ""}`
    + `${r.editedTs ? `<span class="cmt-redited">${esc(t("cmtReplyEdited"))}</span>` : ""}`
    + `<span class="cmt-when">${esc(r.ts || t("cmtNoTime"))}</span>${acts}</div>`;
  const body = editing
    ? `<textarea class="cmt-redit" data-val="${esc(key)}" aria-label="${esc(t("cmtReplyEdit"))}">${esc(r.text || "")}</textarea>`
      + `<div class="cmt-acts">${btn("cmtreditsave", key, t("cmtSave"))}${btn("cmtreditcancel", key, t("cmtCancel"))}</div>`
    : `<p class="cmt-rtext">${esc(r.text || "")}</p>`;
  const cfm = open && st.replyDelAsk === key ? confirmHTML({ title: t("cfmDelReply"), yes: t("cmtDelete"), no: t("cmtCancel"),
    yesAttrs: `data-act="cmtrdelyes" data-val="${esc(key)}"`, noAttrs: 'data-act="cmtrdelno"' }) : "";
  return `<li class="cmt-reply${isFresh ? " cmt-reply--new" : ""}">${head}${body}${cfm}</li>`;
}

/** Гілка відповідей під текстом картки (0.34). Лише коли виклик передав `st.threads` (Set розгорнутих id) — без нього картка
 *  така, як була, хоч би й мала `replies`. Закритий коментар: згорнутий/розгорнутий список без поля й без дій. */
function threadHTML(c, st) {
  if (!(st.threads instanceof Set)) return "";
  const open = c.status === "open";
  const list = repliesOf(c);
  const n = list.length;
  const expanded = st.threads.has(c.id);
  const off = open && typeof st.repliesOff === "function" ? st.repliesOff(c) : null;
  const canReply = open && typeof st.repliesOff === "function" && off == null;
  const replying = canReply && st.replying === c.id;
  let sum = "";
  if (n) {
    const k = list.filter((r) => st.fresh && st.fresh.has(r.id)).length;
    const last = list[n - 1];
    const lastWhen = shortWhen(last.ts);
    sum = `<button type="button" class="cmt-rsum" data-act="cmtthread" data-val="${esc(c.id)}" aria-expanded="${expanded}">`
      + `${ico(expanded ? "chevdown" : "chevright")}<span>${esc(t("cmtReplies", n))}</span>`
      + (k ? `<span class="cmt-rnew">${esc(t("cmtReplyNew", k))}</span>` : "")
      + (expanded ? "" : `<span class="cmt-rlast">${esc(`· ${replyWho(last)}${lastWhen ? `, ${lastWhen}` : ""}`)}</span>`) + "</button>";
  } else if (canReply && !replying) {
    sum = `<button type="button" class="cmt-rsum" data-act="cmtreply" data-val="${esc(c.id)}">${ico("comment")}<span>${esc(t("cmtReply"))}</span></button>`;
  }
  const items = n && expanded ? `<ol class="cmt-replies">${list.map((r) => replyHTML(c, r, st, open)).join("")}</ol>` : "";
  const box = canReply && (replying || (n && expanded))
    ? `<div class="cmt-rbox${replying ? " cmt-rbox--on" : ""}"><textarea class="cmt-rta" data-val="${esc(c.id)}"`
      + ` placeholder="${esc(t("cmtReplyPh"))}" aria-label="${esc(t("cmtReply"))}"></textarea>`
      + `<div class="cmt-rrow"><span class="cmt-rhint">${esc(t("cmtReplyHint"))}</span>${btn("cmtreplycancel", c.id, t("cmtCancel"))}`
      + `${btn("cmtreplysend", c.id, t("cmtReplySend"), null, " cmt-act--pri")}</div></div>` : "";
  const note = open && typeof off === "string" && off && (expanded || !n) ? `<p class="cmt-rnote">${esc(t("cmtRepliesOff"))}</p>` : "";
  return sum || items || box || note ? `<div class="cmt-thread">${sum}${items}${box}${note}</div>` : "";
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
    const nRep = st.threads instanceof Set ? repliesOf(c).length : 0;   // питання про відповіді — лише з гілкою (без неї картка як була)
    acts = `<div class="cmt-acts cmt-acts--cfm">${confirmHTML({ title: nRep ? t("cfmDelCmtReplies", nRep) : t("cfmDelCmt"), yes: t("cmtDelete"), no: t("cmtCancel"),
      yesAttrs: `data-act="cmtdelyes" data-val="${esc(c.id)}"`, noAttrs: 'data-act="cmtdelno"' })}</div>`;
  } else if (c.id !== st.editingId) {
    /* Типовий набір дій за видом картки — порядок і розмітка Deai. */
    let list;
    if (kind === "open") list = [["cmtshow", btn("cmtshow", c.id, t("cmtShow"))]]
      .concat(st.dual && audOf(c) === "project"
        ? [[assignedToClaude(c) ? "cmtunassign" : "cmtassign", btn(assignedToClaude(c) ? "cmtunassign" : "cmtassign", c.id, t(assignedToClaude(c) ? "cmtUnassign" : "cmtAssign"))]] : [])
      .concat([["cmtedit", btn("cmtedit", c.id, t("cmtEdit"), "pencil")], ["cmtres", btn("cmtres", c.id, t("cmtResolve"), "check")],
        ["cmtdel", btn("cmtdel", c.id, t("cmtDelete"), "trash")]]);
    else if (kind === "earlier") list = [["cmtcarry", btn("cmtcarry", c.id, t("cmtCarry", st.snapshot.iteration))],
      ["cmtdel", btn("cmtdel", c.id, t("cmtDelete"), "trash")]];
    else list = [["cmtreopen", btn("cmtreopen", c.id, t("cmtReopen"), "refresh")], ["cmtdel", btn("cmtdel", c.id, t("cmtDelete"), "trash")]];
    /* Права (зовнішнє превʼю, 0.32.0): `st.actions` — `{any, own, closed}` — дозволені дії; решта з типового набору відпадає.
       Закриті — лише `closed` (у превʼю порожньо: закривати й відкривати знову — тільки в Deai). Без `st.actions` — усе як було. */
    if (st.actions) {
      const own = typeof st.isOwn === "function" && !!st.isOwn(c);
      const ok = kind === "closed" ? st.actions.closed || [] : [...(st.actions.any || []), ...(own ? st.actions.own || [] : [])];
      list = list.filter(([act]) => ok.includes(act));
    }
    acts = list.map(([, markup]) => markup).join("");
    if (acts) acts = `<div class="cmt-acts">${acts}</div>`;
  }
  /* «Без знімка: причина» — замість мовчання, коли коментатор не зміг зняти знімок (`meta.shotMiss`) і зображення нема. */
  const miss = typeof m.shotMiss === "string" && SHOT_MISS.includes(m.shotMiss) && !m.shot && !m.shotUrl
    ? `<p class="cmt-shotmiss">${ico("camera")}<span>${esc(t(`cmtShotMiss_${m.shotMiss}`))}</span></p>` : "";
  return `<article class="cmt-card${sel}${closed}" data-cid="${esc(c.id)}">${head}${iter}${body}${quote}${vp}${where}${shot}${done}${miss}${threadHTML(c, st)}${acts}</article>`;
}

function foldHTML(key, title, items, st, kind) {
  if (!items.length) return "";
  const open = !!(st.expanded && st.expanded[key]);
  return `<section class="cmt-sec cmt-sec--fold"><button type="button" class="cmt-fold" data-act="cmtsec" data-val="${key}"`
    + ` aria-expanded="${open}">${ico(open ? "chevdown" : "chevright")}${esc(`${title} (${items.length})`)}</button>`
    + (open ? items.map((c) => cardHTML(c, st, kind)).join("") : "") + "</section>";
}

const FILTER_KEY = { local: "cmtFLocal", project: "cmtFTeam", all: "cmtFAll" };

/** st: {snapshot, query, selectedId, editingId, delAsk (id картки з питанням «Видалити назавжди?»), expanded:{earlier,closed}, filter:'local'|'project'|'all', dual, teamDown, fresh:Set|null, down}
 *  Гілка відповідей (0.34; без `threads` картка як була): `threads: Set` (розгорнуті id коментарів), `replying: id`, `replyEdit: "cid|rid"`,
 *  `replyDelAsk: "cid|rid"`, `isOwnReply(r)`, `canDeleteReply(r)`, `repliesOff(c) → рядок причини|null`; `fresh` — id коментарів І відповідей.
 *  Необовʼязково (превʼю, 0.32.0; без них — Deai як було): `isOwn(c)`, `actions: {any, own, closed}` (дозволені `data-act`), `adding: boolean` (кнопка «Додати коментар»), `emptyKey` (ключ i18n порожнього списку; за замовчуванням `cmtEmpty`). */
export function commentsPanelHTML(st) {
  const filter = FILTERS.includes(st.filter) ? st.filter : "local";
  const hidden = !!(st.snapshot && st.snapshot.pinsHidden);
  const pins = `<button type="button" class="icob" data-act="cmtpins" aria-pressed="${hidden}"`
    + ` aria-label="${esc(t("cmtPins"))}" title="${esc(t("cmtPins"))}">${ico("eye")}</button>`;
  const close = `<button type="button" class="icob" data-act="comments" aria-label="${esc(t("cmtClose"))}" title="${esc(t("cmtClose"))}">${ico("x")}</button>`;
  // Без командного каналу фільтра нема — тоді число відкритих лишається в шапці.
  const total = st.dual ? "" : `<span class="cmt-total">${openCount(st.snapshot)}</span>`;
  /* «Додати коментар» (зовнішнє превʼю, 0.32.0): там панель відкривається для читання, а режим додавання вмикає ця кнопка. */
  const add = typeof st.adding === "boolean"
    ? `<button type="button" class="icob" data-act="cmtadd" aria-pressed="${st.adding}" aria-label="${esc(t("prevAddCmt"))}"`
      + ` title="${esc(t("prevAddCmt"))}">${ico("plus")}</button>` : "";
  const top = `<div class="insp-top cmt-top">${ico("comment")}<span class="panel-title">${esc(t("cmtTitle"))}</span>${total}${add}${pins}${close}</div>`;
  const search = `<div class="cmt-search"><input type="search" id="cmt-q" value="${esc(st.query || "")}"`
    + ` placeholder="${esc(t("cmtSearch"))}" aria-label="${esc(t("cmtSearch"))}"></div>`;
  let seg = "";
  if (st.dual) {
    const n = filterCounts(st.snapshot, st.fresh);
    seg = `<div class="cmt-filter" role="group" aria-label="${esc(t("cmtFilter"))}">`
      + FILTERS.map((f) => `<button type="button" data-act="cmtfilter" data-val="${f}" aria-pressed="${filter === f}">`
        + `<span>${esc(t(FILTER_KEY[f]))}</span><span class="cmt-fn">${n[f]}</span>`
        + (n.fresh[f] ? `<span class="cmt-fnew" title="${esc(t("cmtNewTitle"))}">+${n.fresh[f]}</span>` : "")
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
    const empty = none ? `<p class="insp-hint">${esc(t(st.query || hasAny ? "cmtNoMatch" : st.emptyKey || "cmtEmpty"))}</p>` : "";
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
