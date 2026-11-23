/**
 * Панель «Історія змін» ітерації (фаза И, Р7). Чиста розмітка з відповіді `GET /api/iteration-history`; проводка — `app.js`.
 * Записи від новіших, групи днів «Сьогодні» / «Вчора» / ДД.ММ.РРРР. Тексти — за `kind` (i18n), `text` — запасний для `other`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";
import { initials } from "./shell-bar.js";

const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

/** Підпис дня запису відносно `now` (локальний час машини). */
export function dayKey(at, now = new Date()) {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "";
  if (ymd(d) === ymd(now)) return t("today");
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (ymd(d) === ymd(y)) return t("yesterday");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

const hhmm = (at) => { const d = new Date(at); return Number.isNaN(d.getTime()) ? "" : `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const itTag = (id) => t("iterTag", String(id || "").replace(/^it/, ""));

function what(e) {
  const a = e.args || {};
  switch (e.kind) {
    case "create": return a.note ? `${t("histCreate")} · ${a.note}` : t("histCreate");
    case "copy": return t("histCopy", itTag(a.from), a.note || "");
    case "merge": return t("histMerge", (a.from || []).map(itTag).join(", "));
    case "rename": return t("histRename", a.name || "");
    case "restore": return t("histRestore");
    case "delete": return t("histDelete");
    case "page-new": return t("histPageNew", a.name || a.page || "");
    case "page-rename": return t("histPageRename", a.name || a.page || "");
    case "page-move": return t("histPageMove", a.name || a.page || "");
    case "tree": return t("histTree");
    case "publish": return t("histPublish");
    case "ai": return a.synced ? `${t("histAi")} · ${t("histSynced")}` : t("histAi");
    case "sync": return t("histSync");
    default: return e.text || "";
  }
}

const filesLine = (files, more) => {
  const list = [...(files || []), ...(more > 0 ? [t("histMore", more)] : [])];
  return list.length ? `<div class="hist-files">${esc(list.join(" · "))}</div>` : "";
};

function entryHTML(e) {
  const ai = e.actor?.kind === "ai";
  const name = ai ? "" : (e.actor?.name || "");   // аватар «AI» уже каже, хто це — другий рядок «AI» зайвий
  return `<div class="hist-e"><span class="hist-av${ai ? " hist-av--ai" : ""}">${esc(ai ? "AI" : initials(e.actor?.name || ""))}</span>`
    + `<div class="hist-b"><div class="hist-t">${esc(what(e))}</div>${name ? `<div class="hist-m">${esc(name)}</div>` : ""}`
    + `${filesLine(e.files, e.more)}</div><span class="hist-time">${esc(hhmm(e.at))}</span></div>`;
}

export function histHTML({ label, entries = [], pending = null, degraded = false }, { now = new Date() } = {}) {
  const groups = [];
  for (const e of entries) {
    const k = dayKey(e.at, now);
    const g = groups[groups.length - 1];
    if (g && g.k === k) g.items.push(e); else groups.push({ k, items: [e] });
  }
  const pend = pending ? `<div class="hist-e hist-e--pending"><span class="hist-av">•</span>`
    + `<div class="hist-b"><div class="hist-t">${esc(t("histPending"))}</div>${filesLine(pending.files, pending.more)}</div>`
    + `<span class="hist-time">${esc(hhmm(pending.at))}</span></div>` : "";
  return `<div class="insp-top cmt-top">${ico("refresh", 16)}<span class="panel-title">${esc(t("histTitle", label))}</span>`
    + `<button type="button" class="icob" data-act="histclose" aria-label="${esc(t("histClose"))}" title="${esc(t("histClose"))}">${ico("x")}</button></div>`
    + `<div class="insp-body hist-body">${degraded ? `<p class="hist-deg">${esc(t("histDegraded"))}</p>` : ""}${pend}`
    + groups.map((g) => `<div class="hist-day">${esc(g.k)}</div>${g.items.map(entryHTML).join("")}`).join("")
    + `</div>`;
}
