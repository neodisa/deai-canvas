/**
 * Панель властивостей інспектора (етап Г, 0.29.0): модель на вході, рядок HTML на виході. ЧИСТИЙ модуль — ні DOM,
 * ні слухачів, ні звернення до макета (охоронець `tests/shell-inspect.test.mjs`, `PANEL_SOURCES`). Модель збирає
 * `app/insp-model.js`; проводку (`data-act` → дія) робить `app.js` тією ж делегацією на `#insp-panel`, що й раніше.
 *
 * ⛔ Жодних підписів-пояснень (правило власника, спека Р3): ні рядка клавіш, ні підказок під полями, ні речень про
 * вирок. Походження значення — у `title` ПОЛЯ (один титул на поле, не на внутрішній `input`: титул на вкладеному
 * контролі накрив би титул поля рівно там, де водять мишею).
 *
 * ⚠️ Класи — ПОВНІ літерали в кожній гілці, стан — `data-*`: охоронець css-guards читає атрибут class регекспом по сирцю.
 *
 * Адреса поля для всіх, хто дивиться ззовні: `data-prop` (ПЕРША властивість) і `data-props` (усі, через пробіл) —
 * і на обгортці `.insp-f`, і на `input`. Ключ відновлення фокуса в `paintInsp` — пара `data-act` + `data-prop`.
 */
import { esc } from "./esc.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

const HEX6 = /^#[0-9a-fA-F]{6}$/;
const SVG = (d) => `<svg class="ico" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"`
  + ` stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
/* Підписи полів-іконок (з затвердженого прототипу). */
const GLYPH = {
  padX: SVG('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7.5 8.5v7M16.5 8.5v7"/>'),
  padY: SVG('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M8.5 8h7M8.5 16h7"/>'),
  marX: SVG('<rect x="7.5" y="6" width="9" height="12" rx="1.5"/><path d="M3 4v16M21 4v16"/>'),
  marY: SVG('<rect x="6" y="7.5" width="12" height="9" rx="1.5"/><path d="M4 3h16M4 21h16"/>'),
  radius: SVG('<path d="M5 20V11a6 6 0 0 1 6-6h8"/>'),
  strokeW: SVG('<path d="M4 7h16"/><path d="M4 15h16" stroke-width="3.5"/>'),
  lh: SVG('<path d="M4 4h16M4 20h16M12 8v8M9.5 10.5 12 8l2.5 2.5M9.5 13.5 12 16l2.5-2.5"/>'),
  ls: SVG('<path d="M5 5v14M19 5v14M8 12h8M10.5 9.5 8 12l2.5 2.5M13.5 9.5 16 12l-2.5 2.5"/>'),
  sides: SVG('<rect x="4" y="4" width="16" height="16" rx="2" stroke-dasharray="3 3"/>'),
};
const ARROW = {
  row: SVG('<path d="M4 12h15M13 6l6 6-6 6"/>'),
  column: SVG('<path d="M12 4v15M6 13l6 6 6-6"/>'),
};

/** Підпис поля: іконка або літера. Тягнеться вліво-вправо («скраб») — `data-scrub` = властивості. */
function labelHTML(f) {
  const inner = f.lab && f.lab.i && GLYPH[f.lab.i] ? GLYPH[f.lab.i] : esc((f.lab && f.lab.t) || "");
  return `<span class="insp-fl" data-scrub="${esc(f.props.join(" "))}" title="${esc(f.name)}">${inner}</span>`;
}

/** Імʼя токена без `--` (чип і кнопка читаються коротко; повне — в `data-token`/`title`). */
const short = (name) => String(name || "").replace(/^--/, "");

/** Хвіст поля: чип токена (за вироком) і кнопка «до ДС». Таблиця — у спеці, розділ «Поле». */
function tailHTML(f) {
  let chip = "";
  if (f.token && (f.verdict === "off-ds" || f.verdict === "overridden")) {
    chip = `<span class="insp-tok" data-off title="${esc(f.token)}">${esc(f.token)}</span>`;
  } else if (f.token && f.verdict === "token") {
    chip = `<span class="insp-tok" title="${esc(f.token)}">${esc(f.token)}</span>`;
  }
  const snap = f.snap && f.snap.token && f.snap.value != null
    ? `<button type="button" class="insp-snap" data-act="inspsnap" data-prop="${esc(f.props[0])}"`
      + ` data-props="${esc(f.props.join(" "))}" data-token="${esc(f.snap.token)}" data-val="${esc(f.snap.value)}"`
      + ` title="${esc(t("inspSnapTo", f.snap.token))}" aria-label="${esc(t("inspSnapTo", f.snap.token))}"`
      + `>${esc(short(f.snap.token))}</button>`
    : "";
  return chip + snap;
}

/** Одне поле. Стан — атрибутами обгортки (`data-off`, `data-tuned`, `data-miss`, `data-mixed`, `data-verdict`). */
function fieldHTML(f) {
  if (!f) return "";
  const first = esc(f.props[0]);
  const all = esc(f.props.join(" "));
  let wrap = `data-prop="${first}" data-props="${all}" data-verdict="${esc(f.verdict)}"`;
  if (f.off) wrap += " data-off";
  if (f.changed) wrap += " data-tuned";
  if (f.miss) wrap += " data-miss";
  if (f.mixed) wrap += " data-mixed";
  const title = f.title ? ` title="${esc(f.title)}"` : "";
  if (f.kind === "ro") {
    return `<div class="insp-f" ${wrap} data-ro${title}><span class="insp-ro">${esc(f.value)}</span></div>`;
  }
  if (f.kind === "weight") {
    const opts = (f.options || []).map((o) => `<option value="${esc(o.value)}"`
      + `${String(o.value) === String(f.value) ? " selected" : ""}>${esc(o.label)}</option>`).join("");
    return `<div class="insp-f" ${wrap}${title}><select class="insp-fi" data-act="insptune" data-prop="${first}"`
      + ` data-props="${all}" data-unit="" aria-label="${esc(f.name)}">${opts}</select>${tailHTML(f)}</div>`;
  }
  if (f.kind === "color") {
    const sw = HEX6.test(f.swatch || "") ? ` style="background:${f.swatch}"` : "";
    return `<div class="insp-f" ${wrap}${title}><span class="insp-sw"${sw}></span>`
      + `<input class="insp-fi" data-act="insptunecolor" data-prop="${first}" data-props="${all}"`
      + ` value="${esc(f.value)}" aria-label="${esc(f.name)}" autocomplete="off" spellcheck="false">${tailHTML(f)}</div>`;
  }
  const min = f.min == null ? "" : ` data-min="${esc(f.min)}"`;
  const base = f.base == null ? "" : ` data-base="${esc(f.base)}"`;
  const ph = f.mixed ? ` placeholder="${esc(t("inspMixed"))}"` : "";
  return `<div class="insp-f" ${wrap}${title}>${labelHTML(f)}`
    + `<input class="insp-fi" data-act="insptune" data-prop="${first}" data-props="${all}"`
    + ` data-step="${esc(Number(f.step) || 1)}" data-unit="${esc(f.unit || "")}"${min}${base}`
    + ` value="${esc(f.value)}"${ph} aria-label="${esc(f.name)}" inputmode="decimal" autocomplete="off" spellcheck="false">`
    + `${tailHTML(f)}</div>`;
}

const row = (...fields) => `<div class="insp-row">${fields.map(fieldHTML).join("")}</div>`;
const row1 = (field) => `<div class="insp-row insp-row--1">${fieldHTML(field)}</div>`;

/** Розділ. `extra` — кнопка в шапці (`+`, перемикач сторін). Порожнє тіло — розділ лише з шапкою (заливка без поля). */
function sec(key, head, body, extra = "") {
  return `<section class="insp-sec" data-sec="${key}"><div class="insp-sh">${esc(head)}${extra}</div>${body}</section>`;
}

function pathHTML(m) {
  const items = (m.path && m.path.items) || [];
  const more = m.path && m.path.more ? `<span class="insp-ps">…</span>` : "";
  const btns = items.map((p) => `<button type="button" class="insp-pb" data-act="inspcrumb" data-val="${esc(p.idx)}">`
    + `${esc(p.name)}</button><span class="insp-ps">›</span>`).join("");
  return `<div class="insp-path">${more}${btns}</div>`;
}

function elHTML(m) {
  const off = m.offDs > 0
    ? `<button type="button" class="insp-off" data-act="inspnextoff">${esc(t("inspOffCount", m.offDs))}</button>` : "";
  return `<div class="insp-el"><span class="insp-name" title="${esc(m.name)}">${esc(m.name)}</span>${off}</div>`;
}

function edgesSec(m) {
  const e = m.edges;
  if (!e) return "";
  return sec("edges", t("inspPEdges"), `<div class="insp-edges"><span class="insp-e-t">${esc(e.top)}</span>`
    + `<span class="insp-e-l">${esc(e.left)}</span><span class="insp-e-box">${esc(e.parent)}</span>`
    + `<span class="insp-e-r">${esc(e.right)}</span><span class="insp-e-b">${esc(e.bottom)}</span></div>`);
}

function layoutSec(m) {
  const l = m.layout;
  if (!l) return "";
  if (l.kind === "grid") return sec("layout", t("inspPAuto"), row1(l.gap));
  const names = [[t("inspAlLeft"), t("inspAlCenter"), t("inspAlRight")], [t("inspAlTop"), t("inspAlMiddle"), t("inspAlBottom")]];
  let cells = "";
  for (let r = 0; r < 3; r += 1) {
    for (let c = 0; c < 3; c += 1) {
      cells += `<button type="button" class="insp-cell" data-act="inspalign" data-val="${c},${r}"`
        + ` data-dir="${esc(l.dir)}" aria-pressed="${c === l.ax && r === l.ay}"`
        + ` aria-label="${esc(t("inspAlignCell", names[0][c], names[1][r]))}"></button>`;
    }
  }
  const dir = (id, label) => `<button type="button" class="insp-dir" data-act="inspdir" data-val="${id}"`
    + ` aria-pressed="${l.dir === id}" aria-label="${esc(label)}">${ARROW[id]}</button>`;
  return sec("layout", t("inspPAuto"), `<div class="insp-al"><div class="insp-align">${cells}</div>`
    + `<div class="insp-al-side"><div class="insp-dirs">${dir("row", t("inspDirRow"))}${dir("column", t("inspDirCol"))}</div>`
    + `${fieldHTML(l.gap)}</div></div>`);
}

function spacingSec(m) {
  const s = m.spacing;
  const toggle = `<button type="button" class="insp-ib" data-act="inspsides" aria-pressed="${!!s.sides}"`
    + `${s.forced ? " disabled" : ""} aria-label="${esc(t("inspSides"))}" title="${esc(t("inspSides"))}">${GLYPH.sides}</button>`;
  const body = s.sides && s.pad && s.mar
    ? row(s.pad.top, s.pad.right) + row(s.pad.bottom, s.pad.left) + row(s.mar.top, s.mar.right) + row(s.mar.bottom, s.mar.left)
    : row(s.padX, s.padY) + row(s.marX, s.marY);
  return sec("spacing", t("inspPSpacing"), body, toggle);
}

const addBtn = (kind, add, label) => `<button type="button" class="insp-ib" data-act="inspadd" data-val="${kind}"`
  + ` data-color="${esc(add.value)}" data-token="${esc(add.token)}" aria-label="${esc(label)}" title="${esc(label)}">`
  + `${ico("plus", 14)}</button>`;

function fillSec(m) {
  return m.fill
    ? sec("fill", t("inspPFill"), row1(m.fill))
    : sec("fill", t("inspPFill"), "", addBtn("fill", m.fillAdd, t("inspAddFill")));
}

function strokeSec(m) {
  const add = m.stroke ? "" : addBtn("stroke", m.strokeAdd, t("inspAddStroke"));
  const body = (m.stroke ? row1(m.stroke.color) : "")
    + row(...(m.stroke ? [m.stroke.width] : []), m.radius);
  return sec("stroke", t("inspPStroke"), body, add);
}

function textSec(m) {
  const x = m.text;
  if (!x) return "";
  const family = `<div class="insp-row insp-row--1"><div class="insp-f" data-prop="font-family" data-props="font-family"`
    + ` data-ro title="${esc(x.family)}"><span class="insp-ro">${esc(x.family)}</span></div></div>`;
  return sec("text", t("inspPText"), family + row(x.weight, x.size) + row(x.lh, x.ls) + (x.color ? row1(x.color) : ""));
}

/** Модель → HTML тіла панелі (шлях, елемент, розділи). Немає моделі — `''`: шапку й підвал додає `inspectHTML`. */
export function panelHTML(m) {
  if (!m) return "";
  return pathHTML(m) + elHTML(m)
    + sec("size", t("inspPSize"), row(m.size.w, m.size.h))
    + edgesSec(m) + layoutSec(m) + spacingSec(m) + fillSec(m) + strokeSec(m) + textSec(m);
}
