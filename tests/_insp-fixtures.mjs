/**
 * Спільні фікстури етапу Г: модель панелі (для `insp-panel`, `css-guards`) і payload `report()` (для `insp-model`).
 * Файл НЕ `*.test.mjs` навмисно — як `_css-classes.mjs`: `node --test tests/*.test.mjs` його не запускає.
 */

/** Поле моделі з типовими значеннями; `o` перекриває. */
export const F = (o = {}) => ({
  id: "gap", kind: "num", props: ["gap"], name: "Проміжок", lab: { t: "↔" }, value: "12", mixed: false,
  verdict: "token", token: "sp-3", off: false, snap: null, changed: false, miss: false,
  title: "gap · var(--sp-3)", step: 1, min: 0, unit: "px", base: null, ...o,
});

/** Колірне поле. */
export const COLOR = (o = {}) => F({
  id: "fill", kind: "color", props: ["background-color"], name: "Колір заливки", lab: null, value: "1F4FE0",
  swatch: "#1F4FE0", verdict: "hardcode", token: "", off: true, step: 1, min: null, unit: "", ...o,
});

const SIZE_W = () => F({ id: "w", props: ["width"], name: "Ширина", lab: { t: "W" }, value: "560",
  verdict: "unlinked", token: "", title: "width" });
const SIZE_H = () => F({ id: "h", props: ["height"], name: "Висота", lab: { t: "H" }, value: "320",
  verdict: "unlinked", token: "", title: "height" });
const PAIR = (id, props, lab, name) => F({ id, props, name, lab: { i: lab }, value: "16", min: id.startsWith("mar") ? null : 0,
  title: props.join(", ") });

/** Найменший можливий елемент: без батька, без розкладки, без заливки й обведення, без тексту. */
export const MIN_MODEL = () => ({
  name: "div#wrap", path: { more: false, items: [] }, offDs: 0,
  size: { w: SIZE_W(), h: SIZE_H() }, edges: null, layout: null,
  spacing: { sides: false, forced: false,
    padX: PAIR("padX", ["padding-left", "padding-right"], "padX", "Внутрішній відступ ↔"),
    padY: PAIR("padY", ["padding-top", "padding-bottom"], "padY", "Внутрішній відступ ↕"),
    marX: PAIR("marX", ["margin-left", "margin-right"], "marX", "Зовнішній відступ ↔"),
    marY: PAIR("marY", ["margin-top", "margin-bottom"], "marY", "Зовнішній відступ ↕"),
    pad: null, mar: null },
  fill: null, fillAdd: { value: "#FFFFFF", token: "" },
  stroke: null, strokeAdd: { value: "#000000", token: "" },
  radius: F({ id: "radius", props: ["border-radius"], name: "Радіус", lab: { i: "radius" }, value: "8" }),
  text: null,
});

/** Усе одразу: шлях зі скороченням, лічильник, батько, flex, заливка, обведення, текст. */
export const FULL_MODEL = () => ({
  ...MIN_MODEL(),
  name: "a.btn--primary",
  path: { more: true, items: [{ name: "section.hero", idx: 1 }, { name: "div.cta", idx: 2 }] },
  offDs: 3,
  edges: { parent: "div.cta", top: 12, right: 0, bottom: 12, left: 24 },
  layout: { kind: "flex", dir: "row", ax: 1, ay: 1, gap: F() },
  fill: COLOR({ verdict: "off-ds", token: "brand-x", snap: { token: "--brand-600", value: "#1F4FE0" } }),
  stroke: { color: COLOR({ id: "strokeColor", props: ["border-color"], name: "Колір обведення", value: "DDE3EE",
    swatch: "#DDE3EE" }), width: F({ id: "strokeW", props: ["border-width"], name: "Товщина обведення",
    lab: { i: "strokeW" }, value: "1" }) },
  text: { family: "Inter", weight: F({ id: "weight", kind: "weight", props: ["font-weight"], name: "Насиченість",
    lab: null, value: "600", unit: "", options: [{ value: "400", label: "Regular" }, { value: "600", label: "Semibold" }] }),
  size: F({ id: "size", props: ["font-size"], name: "Кегль", lab: { t: "Aa" }, value: "14" }),
  lh: F({ id: "lh", props: ["line-height"], name: "Інтерліньяж", lab: { i: "lh" }, value: "20" }),
  ls: F({ id: "ls", props: ["letter-spacing"], name: "Трекінг", lab: { i: "ls" }, value: "0", step: 0.1, min: null }),
  color: COLOR({ id: "textColor", props: ["color"], name: "Колір тексту", value: "FFFFFF", swatch: "#FFFFFF" }) },
});
