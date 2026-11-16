/**
 * Етап Г (0.29.0): збирач моделі панелі. Чиста функція: payload `report()` + правки → модель. Тут — що саме
 * потрапляє в панель і в якому вигляді; що поля реагують — перевіряють живі тести.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { alignWrites, buildModel } from "../app/insp-model.js";
import { D, REPORT } from "./_insp-fixtures.mjs";

const withProps = (rep, props) => {
  const next = structuredClone(rep);
  for (const items of Object.values(next.groups)) {
    for (const d of items) if (d.prop in props) Object.assign(d, props[d.prop]);
  }
  return next;
};

test("немає звіту — немає моделі", () => {
  assert.equal(buildModel(null), null);
  assert.equal(buildModel({}), null);
});

test("назва й шлях: до трьох предків, довший шлях скорочується на початку", () => {
  const m = buildModel(REPORT());
  assert.equal(m.name, "a.btn--primary");
  assert.deepEqual(m.path, { more: false, items: [{ name: "body", idx: 0 }, { name: "section.hero", idx: 1 }, { name: "div.cta", idx: 2 }] });
  const long = buildModel(REPORT({ crumbs: ["html", "body", "main", "section", "div", "span"] }));
  assert.equal(long.path.more, true);
  assert.deepEqual(long.path.items.map((p) => p.idx), [2, 3, 4]);
});

test("розмір береться зі звіту, а коли width: auto — з геометрії рамки", () => {
  const m = buildModel(REPORT());
  assert.equal(m.size.w.value, "120");
  assert.deepEqual(m.size.w.props, ["width"]);
  const auto = buildModel(withProps(REPORT(), { width: { computed: "auto" } }));
  assert.equal(auto.size.w.value, "120", "facts.w = 120");
});

test("W/H — РЕНДЕРЕНИЙ розмір (як ярлик оверлея); різниця з CSS-значенням — delta", () => {
  const rep = withProps(REPORT(), { width: { computed: "716px" }, height: { computed: "40px" } });
  rep.facts.w = 766; rep.facts.h = 82;
  const m = buildModel(rep);
  assert.equal(m.size.w.value, "766");
  assert.equal(m.size.w.delta, 50);
  assert.equal(m.size.h.value, "82");
  assert.equal(m.size.h.delta, 42);
  const eq = buildModel(REPORT());                                  // 120px / facts.w 120
  assert.equal("delta" in eq.size.w, false, "рівні — без delta");
  const frac = withProps(REPORT(), { width: { computed: "119.6px" } });
  assert.equal(buildModel(frac).size.w.delta, 0.4, "округлення до 0.1");
  const auto = buildModel(withProps(REPORT(), { width: { computed: "auto" } }));
  assert.equal("delta" in auto.size.w, false, "не число — без delta");
});

test("батько зʼявляється лише коли є в facts", () => {
  assert.deepEqual(buildModel(REPORT()).edges, { parent: "div.cta", top: 0, right: 8, bottom: 0, left: 0 });
  const rep = REPORT(); rep.facts.parent = null;
  assert.equal(buildModel(rep).edges, null);
});

test("flex: напрям і вічко матриці з justify-content / align-items", () => {
  const l = buildModel(REPORT()).layout;
  assert.equal(l.kind, "flex"); assert.equal(l.dir, "row");
  assert.equal(l.ax, 0, "justify-content: flex-start → ліва колонка");
  assert.equal(l.ay, 1, "align-items: center → середній рядок");
  assert.deepEqual(l.gap.props, ["gap"]);
  assert.equal(l.gap.token, "sp-2");
  const col = buildModel(withProps(REPORT(), { "flex-direction": { computed: "column" } })).layout;
  assert.equal(col.dir, "column");
  assert.equal(col.ax, 1, "у стовпчику вісь x — align-items");
  assert.equal(col.ay, 0, "а вісь y — justify-content");
});

test("align-items: normal/stretch та space-between не підсвічують жодного вічка", () => {
  const l = buildModel(withProps(REPORT(), { "align-items": { computed: "normal" }, "justify-content": { computed: "space-between" } })).layout;
  assert.equal(l.ax, -1); assert.equal(l.ay, -1);
});

test("grid: лише gap; не flex і не grid — розділу немає", () => {
  const g = buildModel(withProps(REPORT(), { display: { computed: "grid" } })).layout;
  assert.equal(g.kind, "grid");
  assert.equal(buildModel(withProps(REPORT(), { display: { computed: "block" } })).layout, null);
});

test("alignWrites: рядок — x у justify-content, стовпчик — навпаки", () => {
  assert.deepEqual(alignWrites("row", 2, 0), [["justify-content", "flex-end"], ["align-items", "flex-start"]]);
  assert.deepEqual(alignWrites("column", 2, 0), [["justify-content", "flex-start"], ["align-items", "flex-end"]]);
  assert.deepEqual(alignWrites("row", 3, 0), [], "поза матрицею — нічого");
});

test("відступи: пари → дві властивості; різні сторони → «Різні» і сторони розкриті самі", () => {
  const m = buildModel(REPORT());
  assert.deepEqual(m.spacing.padX.props, ["padding-left", "padding-right"]);
  assert.equal(m.spacing.padX.value, "20"); assert.equal(m.spacing.padX.mixed, false);
  assert.equal(m.spacing.sides, false);
  const mixed = buildModel(withProps(REPORT(), { "padding-left": { computed: "4px" } }));
  assert.equal(mixed.spacing.sides, true); assert.equal(mixed.spacing.forced, true);
  assert.equal(mixed.spacing.pad.left.value, "4");
  assert.equal(mixed.spacing.pad.right.value, "20");
});

test("перемикач «окремо» (opts.sides) розкриває сторони без різниці; margin може бути відʼємним", () => {
  const m = buildModel(REPORT(), { sides: true });
  assert.equal(m.spacing.sides, true); assert.equal(m.spacing.forced, false);
  assert.equal(m.spacing.mar.top.min, null, "margin без нижньої межі");
  assert.equal(m.spacing.pad.top.min, 0);
});

test("вирок пари — найтяжчий із двох; чип токена лише коли токен один і вирок про токен", () => {
  const m = buildModel(withProps(REPORT(), {
    "padding-left": { verdict: "token", token: "--sp-3" }, "padding-right": { verdict: "off-ds", token: "--sp-3" },
  }));
  assert.equal(m.spacing.padX.verdict, "off-ds");
  assert.equal(m.spacing.padX.token, "sp-3");
  assert.equal(m.spacing.padX.off, true);
  const hard = buildModel(REPORT()).spacing.padX;
  assert.equal(hard.token, "", "хардкод чипа не має");
});

test("snap пари — лише коли обидві сторони мають однаковий snap і не «Різні»", () => {
  const snap = { token: "--sp-5", value: "20px" };
  const same = buildModel(withProps(REPORT(), { "padding-left": { snap }, "padding-right": { snap } })).spacing.padX;
  assert.deepEqual(same.snap, snap);
  const one = buildModel(withProps(REPORT(), { "padding-left": { snap } })).spacing.padX;
  assert.equal(one.snap, null);
});

test("заливка: колір без «#» у верхньому регістрі; прозорий фон — заливки немає і є значення для «+»", () => {
  const m = buildModel(REPORT());
  assert.equal(m.fill.value, "1F4FE0"); assert.equal(m.fill.swatch, "#1f4fe0");
  const none = buildModel(withProps(REPORT(), { "background-color": { computed: "rgba(0, 0, 0, 0)" } }));
  assert.equal(none.fill, null);
  assert.deepEqual(none.fillAdd, { value: "#FFFFFF", token: "" });
  const rep = withProps(REPORT(), { "background-color": { computed: "rgba(0, 0, 0, 0)" } });
  rep.facts.dsColors = { fill: { token: "--surface-1", value: "#f6f8fc" }, line: { token: "--border-1", value: "#dde3ee" } };
  const ds = buildModel(rep);
  assert.deepEqual(ds.fillAdd, { value: "#F6F8FC", token: "--surface-1" });
});

test("напівпрозорий фон — поле лише для читання, а не хибний hex", () => {
  const m = buildModel(withProps(REPORT(), { "background-color": { computed: "rgba(0, 0, 0, 0.5)" } }));
  assert.equal(m.fill.kind, "ro");
});

test("обведення: є, коли товщина > 0; нема — значення для «+» із ДС, запасне — колір тексту елемента", () => {
  const m = buildModel(REPORT());
  assert.equal(m.stroke.width.value, "1"); assert.equal(m.stroke.color.value, "1F4FE0");
  const none = buildModel(withProps(REPORT(), { "border-width": { computed: "0px" } }));
  assert.equal(none.stroke, null);
  assert.deepEqual(none.strokeAdd, { value: "#FFFFFF", token: "" }, "color: rgb(255,255,255) — власний колір тексту");
});

test("радіус: різні кути → «Різні»", () => {
  assert.equal(buildModel(REPORT()).radius.value, "8");
  const mixed = buildModel(withProps(REPORT(), { "border-radius": { computed: "8px 4px 8px 4px" } })).radius;
  assert.equal(mixed.mixed, true); assert.equal(mixed.value, "");
});

test("текст: лише з власним текстом; трекінг normal → 0; line-height normal → base із кегля", () => {
  const m = buildModel(REPORT()).text;
  assert.equal(m.family, "Inter");
  assert.equal(m.weight.value, "600");
  assert.equal(m.ls.value, "0");
  const rep = REPORT(); rep.facts.ownText = false;
  assert.equal(buildModel(rep).text, null);
  const norm = buildModel(withProps(REPORT(), { "line-height": { computed: "normal" } })).text.lh;
  assert.equal(norm.value, "normal"); assert.equal(norm.base, 17, "14 × 1.2 = 16.8 → 17");
});

test("насиченість: варіанти 400–700 і поточне нестандартне значення", () => {
  const w = buildModel(withProps(REPORT(), { "font-weight": { computed: "300" } })).text.weight;
  assert.deepEqual(w.options.map((o) => o.value), ["300", "400", "500", "600", "700"]);
  assert.equal(w.value, "300");
});

test("лічильник «поза ДС»: hardcode + off-ds + overridden серед ПОКАЗАНИХ полів", () => {
  // padX, padY (hardcode) + color/fill/font-size (hardcode) = 5 у зведеному вигляді
  assert.equal(buildModel(REPORT()).offDs, 5);
  // розкриті сторони — показано вісім відступів, а не чотири
  assert.equal(buildModel(REPORT(), { sides: true }).offDs, 7, "чотири padding + font-size + color + fill");
});

test("правки з пакета: змінене поле й «не лягло» ", () => {
  const m = buildModel(REPORT(), { edits: { "padding-left": { from: "20px", to: "24px" }, "gap": { from: "8px", to: "9px", missing: true } } });
  assert.equal(m.spacing.padX.changed, true);
  assert.equal(m.layout.gap.changed, true); assert.equal(m.layout.gap.miss, true);
  assert.equal(m.spacing.padY.changed, false);
});

test("title поля: властивості, raw із var(), вирок — без вигаданого селектора", () => {
  const f = buildModel(REPORT()).layout.gap;
  assert.match(f.title, /gap/); assert.match(f.title, /var\(--sp-2\)/);
});

test("модель не лізе в DOM", () => {
  const src = readFileSync(new URL("../app/insp-model.js", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
  assert.doesNotMatch(src, /getComputedStyle|ownerDocument|querySelector|contentWindow|document\./);
});
