/**
 * Модель панелі властивостей (етап Г, 0.29.0): payload `CanvasInspector.report()` + правки тюнера → модель для
 * `insp-panel.js`. ЧИСТИЙ модуль: ні DOM, ні мережі. Усе, чого бракує звіту (розмір, батько, власний текст,
 * `border-style`, кольори ДС), оверлей кладе в `report().facts` — тут його лише читають.
 *
 * Правила, які легко зіпсувати:
 *  · пара полів (↔, ↕) — ДВІ властивості: `props` несе обидві, а запис у пакет іде по одній (`tuneWrite`, `app.js`);
 *  · сторони різні → поле порожнє й `mixed`; сторони розкриваються самі (`forced`);
 *  · вирок пари — найтяжчий; чип токена лише для token/off-ds/overridden і лише коли токен один;
 *  · `snap` пари — лише коли обидві сторони мають ОДНАКОВИЙ snap і поле не «Різні»;
 *  · лічильник «поза ДС» рахує ПОКАЗАНІ поля (розкриті сторони — це вісім полів, а не чотири).
 */
import { normalizeValue } from "./vendor/inspector-core.js";
import { t } from "./i18n.js";

const HEX6 = /^#[0-9a-f]{6}$/;
const OFF = new Set(["hardcode", "off-ds", "overridden"]);
const CHIP = new Set(["token", "off-ds", "overridden"]);
const RANK = { overridden: 5, "off-ds": 4, hardcode: 3, token: 2, unknown: 1, unlinked: 0 };
const POS = ["flex-start", "center", "flex-end"];
const WEIGHTS = [400, 500, 600, 700];

const round2 = (n) => Math.round(n * 100) / 100;
const fmt = (n) => String(round2(n));
const numOf = (s) => { const n = parseFloat(String(s)); return Number.isFinite(n) ? n : null; };
const tokName = (n) => String(n || "").replace(/^--/, "");
const uniq = (xs) => [...new Set(xs)];

/** Колір `computed` → `#rrggbb` (нижній регістр), або null (прозорий, альфа, кілька різних, не колір). */
function colorOf(computed) {
  const found = String(computed || "").match(/rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}/g);
  const set = new Set((found || [computed]).map(normalizeValue));
  if (set.size !== 1) return null;
  const v = [...set][0];
  return HEX6.test(v) ? v : null;
}

function posOf(v, axis) {
  if (v === "flex-start" || v === "start" || v === "left") return 0;
  if (v === "center") return 1;
  if (v === "flex-end" || v === "end" || v === "right") return 2;
  if (v === "normal" && axis === "justify") return 0;   // `justify-content: normal` у flex = flex-start
  return -1;                                           // normal/stretch у align-items, space-* — не вічко матриці
}

/** Що писати, коли натиснули вічко (c — колонка, r — рядок). У рядку x = justify-content, у стовпчику — навпаки. */
export function alignWrites(dir, c, r) {
  const x = POS[c]; const y = POS[r];
  if (!x || !y) return [];
  return dir === "column" ? [["justify-content", y], ["align-items", x]] : [["justify-content", x], ["align-items", y]];
}

function verdictLine(d) {
  if (d.verdict === "off-ds") return t("inspOffDs", d.token || "");
  if (d.verdict === "overridden") {
    return t("inspOverridden", d.token || "", Array.isArray(d.ds) ? d.ds.filter(Boolean).join(", ") : "");
  }
  if (d.verdict === "hardcode") return t("inspHardcode");
  return "";
}

export function buildModel(rep, opts = {}) {
  if (!rep || !rep.groups) return null;
  const edits = opts.edits || {};
  const facts = rep.facts || {};
  const rows = {};
  for (const items of Object.values(rep.groups)) for (const d of items) rows[d.prop] = d;
  for (const d of facts.extra || []) rows[d.prop] = d;
  const shown = [];

  /** Поле з однієї чи кількох властивостей. `o`: kind, name, lab, split, zero, step, min, unit, base. */
  const mk = (id, props, o = {}) => {
    const ds = props.map((p) => rows[p]);
    if (ds.some((d) => !d)) return null;
    let kind = o.kind || "num";
    let value = ""; let mixed = false; let swatch = "";
    if (kind === "color") {
      const hex = colorOf(ds[0].computed);
      if (hex) { value = hex.slice(1).toUpperCase(); swatch = hex; } else { kind = "ro"; value = String(ds[0].computed); }
    } else if (kind === "num") {
      const parts = o.split ? String(ds[0].computed).trim().split(/\s+/) : ds.map((d) => String(d.computed).trim());
      const nums = parts.map((p) => (p === o.zero ? 0 : numOf(p)));
      if (nums.every((n) => n !== null)) {
        mixed = nums.some((n) => n !== nums[0]);
        value = mixed ? "" : fmt(nums[0]);
      } else value = parts[0];
    } else value = String(ds[0].computed);
    const verdict = [...ds].map((d) => d.verdict).sort((a, b) => (RANK[b] || 0) - (RANK[a] || 0))[0];
    const toks = uniq(ds.map((d) => d.token || ""));
    const token = CHIP.has(verdict) && toks.length === 1 ? tokName(toks[0]) : "";
    const s0 = ds[0].snap;
    const snap = !mixed && s0 && s0.token && ds.every((d) => d.snap && d.snap.token === s0.token && d.snap.value === s0.value)
      ? { token: s0.token, value: String(s0.value) } : null;
    const field = {
      id, kind, props, name: o.name || "", lab: o.lab || null, value, mixed, swatch, verdict, token,
      off: OFF.has(verdict), snap,
      changed: props.some((p) => edits[p]), miss: props.some((p) => edits[p] && edits[p].missing),
      title: [props.join(", "),
        ...uniq(ds.map((d) => (d.raw && /var\(/.test(d.raw) ? String(d.raw) : "")).filter(Boolean)),
        ...uniq(ds.map(verdictLine).filter(Boolean))].join(" · "),
      step: o.step || 1, min: o.min === undefined ? 0 : o.min, unit: o.unit === undefined ? "px" : o.unit,
      base: o.base == null ? null : o.base,
    };
    if (kind === "color" || kind === "ro") { field.unit = ""; field.min = null; }
    shown.push(field);
    return field;
  };

  /** Ширина/висота: число зі звіту, а на `auto` — з геометрії рамки. */
  const mkSize = (id, prop, fallback, lab, name) => {
    const f = mk(id, [prop], { lab: { t: lab }, name });
    if (!f) return null;
    const n = numOf(rows[prop].computed);
    /* У Figma W/H — РЕНДЕРЕНИЙ розмір (той самий, що в ярлику оверлея). CSS-значення (`content-box` + padding + рамка)
       від нього відрізняється на `delta`; поле його нюхає при записі й віднімає. */
    const rendered = Number.isFinite(fallback) ? fallback : null;
    if (rendered === null) { f.value = String(Math.round(n === null ? 0 : n)); return f; }
    f.value = String(Math.round(rendered));
    if (n !== null) {
      const d = Math.round((rendered - n) * 10) / 10;
      if (d !== 0) f.delta = d;
    }
    return f;
  };

  const crumbs = rep.crumbs || [];
  const anc = crumbs.slice(0, -1);
  const first = Math.max(0, anc.length - 3);
  const path = { more: first > 0, items: anc.slice(first).map((name, i) => ({ name, idx: first + i })) };

  const size = { w: mkSize("w", "width", facts.w, "W", t("inspLblWidth")), h: mkSize("h", "height", facts.h, "H", t("inspLblHeight")) };

  const edges = facts.parent
    ? { parent: facts.parent.name, top: facts.parent.top, right: facts.parent.right, bottom: facts.parent.bottom, left: facts.parent.left }
    : null;

  const disp = rows.display ? String(rows.display.computed) : "";
  const isFlex = /^(inline-)?flex$/.test(disp);
  const isGrid = /^(inline-)?grid$/.test(disp);
  let layout = null;
  if (isFlex || isGrid) {
    const dir = rows["flex-direction"] && String(rows["flex-direction"].computed).startsWith("column") ? "column" : "row";
    const jc = rows["justify-content"] ? String(rows["justify-content"].computed) : "";
    const ai = rows["align-items"] ? String(rows["align-items"].computed) : "";
    const px = posOf(jc, "justify"); const py = posOf(ai, "align");
    layout = {
      kind: isFlex ? "flex" : "grid", dir,
      ax: dir === "row" ? px : py, ay: dir === "row" ? py : px,
      gap: mk("gap", ["gap"], { split: true, lab: { t: isFlex && dir === "column" ? "↕" : "↔" }, name: t("inspFGap") }),
    };
    if (isGrid) { layout.ax = -1; layout.ay = -1; }
  }

  const P = (id, props, lab, name, min) => mk(id, props, { lab: { i: lab }, name, min });
  let spacing = {
    padX: P("padX", ["padding-left", "padding-right"], "padX", t("inspFPadX"), 0),
    padY: P("padY", ["padding-top", "padding-bottom"], "padY", t("inspFPadY"), 0),
    marX: P("marX", ["margin-left", "margin-right"], "marX", t("inspFMarX"), null),
    marY: P("marY", ["margin-top", "margin-bottom"], "marY", t("inspFMarY"), null),
  };
  const mixedPair = [spacing.padX, spacing.padY, spacing.marX, spacing.marY].some((f) => f && f.mixed);
  const forced = mixedPair;
  const sides = !!opts.sides || forced;
  if (sides) {
    // сторони замінюють пари: пари з `shown` прибираємо, щоб лічильник не рахував їх двічі
    for (const f of [spacing.padX, spacing.padY, spacing.marX, spacing.marY]) {
      const i = shown.indexOf(f); if (i >= 0) shown.splice(i, 1);
    }
    const side = (kind, key, prop, min) => {
      const word = t({ top: "inspDirTop", right: "inspDirRight", bottom: "inspDirBottom", left: "inspDirLeft" }[key]);
      const lab = { t: { top: "↑", right: "→", bottom: "↓", left: "←" }[key] };
      return mk(`${kind}${key}`, [prop], { lab, min, name: t(kind === "pad" ? "inspFPadSide" : "inspFMarSide", word) });
    };
    const four = (kind, pre, min) => ({
      top: side(kind, "top", `${pre}-top`, min), right: side(kind, "right", `${pre}-right`, min),
      bottom: side(kind, "bottom", `${pre}-bottom`, min), left: side(kind, "left", `${pre}-left`, min) });
    spacing = { ...spacing, pad: four("pad", "padding", 0), mar: four("mar", "margin", null) };
  }
  spacing = { sides, forced, pad: null, mar: null, ...spacing };

  const bg = rows["background-color"];
  const bgNorm = bg ? normalizeValue(bg.computed) : "";
  const fill = bg && bgNorm !== "rgba(0, 0, 0, 0)"
    ? mk("fill", ["background-color"], { kind: "color", name: t("inspFFill") }) : null;
  const dsc = facts.dsColors || {};
  const add = (pick, fallback) => (pick && pick.value
    ? { value: String(pick.value).toUpperCase(), token: pick.token || "" } : { value: fallback, token: "" });
  const fillAdd = add(dsc.fill, "#FFFFFF");
  const ink = rows.color ? colorOf(rows.color.computed) : null;
  const strokeAdd = add(dsc.line, ink ? ink.toUpperCase() : "#000000");

  const bw = rows["border-width"];
  const widths = bw ? String(bw.computed).trim().split(/\s+/).map(numOf) : [];
  const stroke = widths.some((n) => n !== null && n > 0)
    ? { color: mk("strokeColor", ["border-color"], { kind: "color", name: t("inspFStrokeC") }),
      width: mk("strokeW", ["border-width"], { split: true, lab: { i: "strokeW" }, name: t("inspFStrokeW") }) }
    : null;
  const radius = mk("radius", ["border-radius"], { split: true, lab: { i: "radius" }, name: t("inspLblRadius") });

  let text = null;
  if (facts.ownText && rows["font-size"]) {
    const fs = numOf(rows["font-size"].computed) || 16;
    const fam = rows["font-family"] ? String(rows["font-family"].computed).split(",")[0].replace(/["']/g, "").trim() : "";
    const wf = mk("weight", ["font-weight"], { kind: "weight", name: t("inspLblWeight"), unit: "" });
    if (wf) {
      const cur = numOf(wf.value);
      const list = uniq([...WEIGHTS, ...(cur === null ? [] : [cur])]).sort((a, b) => a - b);
      wf.options = list.map((w) => ({ value: String(w), label: t("inspWeightName", w) }));
    }
    text = {
      family: fam, weight: wf,
      size: mk("size", ["font-size"], { lab: { t: "Aa" }, name: t("inspLblSize") }),
      lh: mk("lh", ["line-height"], { lab: { i: "lh" }, name: t("inspLblLeading"), base: Math.round(fs * 1.2) }),
      ls: mk("ls", ["letter-spacing"], { lab: { i: "ls" }, name: t("inspLblTracking"), step: 0.1, min: null, zero: "normal" }),
      color: mk("textColor", ["color"], { kind: "color", name: t("inspFTextC") }),
    };
  }

  return {
    name: crumbs[crumbs.length - 1] || "", path, offDs: shown.filter((f) => f.off).length,
    size, edges, layout, spacing, fill, fillAdd, stroke, strokeAdd, radius, text,
  };
}
