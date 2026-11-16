/**
 * Етап Г (0.29.0): розмітка панелі властивостей. Чиста функція `panelHTML(model)` — модель на вході, рядок на виході.
 * Що кнопки й поля РЕАГУЮТЬ у бою, перевіряють живі тести (`tests/live/inspector-figma.test.mjs`).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { panelHTML } from "../app/insp-panel.js";
import { COLOR, F, FULL_MODEL, MIN_MODEL } from "./_insp-fixtures.mjs";

const secs = (h) => [...h.matchAll(/data-sec="([a-z]+)"/g)].map((m) => m[1]);

test("немає моделі — порожній рядок (панель без вибраного елемента показує лише шапку)", () => {
  assert.equal(panelHTML(null), "");
  assert.equal(panelHTML(undefined), "");
});

test("розділи залежать від елемента: найменший має розмір, відступи, заливку й обведення", () => {
  assert.deepEqual(secs(panelHTML(MIN_MODEL())), ["size", "spacing", "fill", "stroke"]);
});

test("батько зʼявляє розділ «До країв», flex — «Авто-лейаут», власний текст — «Текст»", () => {
  assert.deepEqual(secs(panelHTML(FULL_MODEL())),
    ["size", "edges", "layout", "spacing", "fill", "stroke", "text"]);
});

test("flex: матриця 3×3 з одним натиснутим вічком, два напрями, gap", () => {
  const h = panelHTML(FULL_MODEL());
  assert.equal((h.match(/data-act="inspalign"/g) || []).length, 9);
  assert.equal((h.match(/class="insp-cell"[^>]*aria-pressed="true"/g) || []).length, 1);
  assert.match(h, /data-act="inspdir" data-val="row"[^>]*aria-pressed="true"/);
  assert.match(h, /data-act="inspdir" data-val="column"[^>]*aria-pressed="false"/);
  assert.match(h, /data-prop="gap"/);
});

test("grid: лише gap — без матриці й без напряму", () => {
  const m = FULL_MODEL();
  m.layout = { kind: "grid", dir: "row", ax: -1, ay: -1, gap: F() };
  const h = panelHTML(m);
  assert.equal((h.match(/data-act="inspalign"/g) || []).length, 0);
  assert.doesNotMatch(h, /data-act="inspdir"/);
  assert.match(h, /data-prop="gap"/);
});

test("матриця без вирівнювання (ax/ay = -1) — жодне вічко не натиснуте", () => {
  const m = FULL_MODEL();
  m.layout = { ...m.layout, ax: -1, ay: -1 };
  assert.equal((panelHTML(m).match(/class="insp-cell"[^>]*aria-pressed="true"/g) || []).length, 0);
});

test("шлях: скорочення «…» на початку й кнопка-предок із індексом крихти", () => {
  const h = panelHTML(FULL_MODEL());
  assert.match(h, /class="insp-path"><span class="insp-ps">…<\/span>/);
  assert.match(h, /data-act="inspcrumb" data-val="1"[^>]*>section\.hero</);
  assert.match(h, /data-act="inspcrumb" data-val="2"[^>]*>div\.cta</);
  assert.doesNotMatch(panelHTML(MIN_MODEL()), /…/, "короткий шлях не скорочується");
});

test("назва елемента екранується", () => {
  const m = MIN_MODEL();
  m.name = '<img src=x onerror="1">';
  const h = panelHTML(m);
  assert.doesNotMatch(h, /<img src=x/);
  assert.match(h, /&lt;img src=x/);
});

/* ── чип токена за вироком (таблиця зі спеки) ───────────────────────── */
const fieldOf = (field) => {
  const m = MIN_MODEL();
  m.size = { w: field, h: F({ id: "h", props: ["height"] }) };
  const h = panelHTML(m);
  const i = h.indexOf(`data-prop="${field.props[0]}"`);
  return h.slice(h.lastIndexOf("<div", i), h.indexOf("</div>", i) + 6);
};
const W = (o) => F({ id: "w", props: ["width"], name: "Ширина", lab: { t: "W" }, ...o });

test("вирок token: чип з імʼям, поле звичайне, кнопки «до ДС» немає", () => {
  const f = fieldOf(W({ verdict: "token", token: "sp-3", off: false }));
  assert.match(f, /<span class="insp-tok" title="sp-3">sp-3<\/span>/);
  assert.doesNotMatch(f, /data-off|insp-snap/);
});

test("вирок hardcode: чипа немає, поле бурштинове, кнопка — токен-підказка", () => {
  const f = fieldOf(W({ verdict: "hardcode", token: "", off: true,
    snap: { token: "--sp-3", value: "12px" } }));
  assert.doesNotMatch(f, /insp-tok/);
  assert.match(f, /data-verdict="hardcode" data-off/);
  assert.match(f, /class="insp-snap" data-act="inspsnap" data-prop="width"[^>]*data-token="--sp-3" data-val="12px"[^>]*>sp-3</);
});

test("вирок off-ds: бурштиновий чип з імʼям І кнопка до ДС", () => {
  const f = fieldOf(W({ verdict: "off-ds", token: "bf-gap", off: true, snap: { token: "--sp-2", value: "8px" } }));
  assert.match(f, /<span class="insp-tok" data-off title="bf-gap">bf-gap<\/span>/);
  assert.match(f, /data-act="inspsnap"/);
});

test("вирок overridden: бурштиновий чип і кнопка зі значенням, яке приписує ДС", () => {
  const f = fieldOf(W({ verdict: "overridden", token: "alpha-100", off: true,
    snap: { token: "--alpha-100", value: "#FBFBFF1A" } }));
  assert.match(f, /insp-tok" data-off/);
  assert.match(f, /data-val="#FBFBFF1A"/);
});

test("вирок unlinked: ні чипа, ні кнопки, поле звичайне", () => {
  const f = fieldOf(W({ verdict: "unlinked", token: "", off: false }));
  assert.doesNotMatch(f, /insp-tok|insp-snap|data-off/);
});

test("пара сторін: кнопка «до ДС» адресує обидві властивості", () => {
  const m = MIN_MODEL();
  m.spacing.padX = F({ id: "padX", props: ["padding-left", "padding-right"], verdict: "hardcode", token: "",
    off: true, snap: { token: "--sp-3", value: "12px" } });
  assert.match(panelHTML(m), /data-act="inspsnap" data-prop="padding-left" data-props="padding-left padding-right"/);
});

/* ── «Різні», лічильник, зміни ──────────────────────────────────────── */
test("«Різні»: порожнє поле із заповнювачем і позначкою, число пишеться в обидві сторони", () => {
  const m = MIN_MODEL();
  m.spacing.padX = F({ id: "padX", props: ["padding-left", "padding-right"], value: "", mixed: true });
  const h = panelHTML(m);
  assert.match(h, /data-props="padding-left padding-right"[^>]*data-mixed/);
  assert.match(h, /value="" placeholder="Різні"/);
});

test("«N поза ДС»: кнопка є лише коли є такі поля", () => {
  const h = panelHTML(FULL_MODEL());
  assert.match(h, /<button type="button" class="insp-off" data-act="inspnextoff">3 поза ДС<\/button>/);
  assert.doesNotMatch(panelHTML(MIN_MODEL()), /inspnextoff/);
});

test("змінене поле й правка, що не лягла, мають свої позначки", () => {
  const m = MIN_MODEL();
  m.size = { w: F({ id: "w", props: ["width"], changed: true }), h: F({ id: "h", props: ["height"], miss: true }) };
  const h = panelHTML(m);
  assert.match(h, /data-prop="width"[^>]*data-tuned/);
  assert.match(h, /data-prop="height"[^>]*data-miss/);
});

/* ── колір, «+», сторони, текст ─────────────────────────────────────── */
test("колір: hex без «#», зразок зліва; сміття в зразок не потрапляє", () => {
  const h = panelHTML(FULL_MODEL());
  assert.match(h, /<span class="insp-sw" style="background:#1F4FE0"><\/span>/);
  assert.match(h, /data-act="insptunecolor" data-prop="background-color"[^>]*value="1F4FE0"/);
  const m = FULL_MODEL();
  m.fill = COLOR({ swatch: "red;background:url(//x/y)" });
  assert.doesNotMatch(panelHTML(m), /url\(|style="background:red/);
});

test("немає заливки/обведення — кнопки «+» несуть колір і токен для запису", () => {
  const m = MIN_MODEL();
  m.fillAdd = { value: "#E8EEFC", token: "--brand-50" };
  const h = panelHTML(m);
  assert.match(h, /data-act="inspadd" data-val="fill" data-color="#E8EEFC" data-token="--brand-50"/);
  assert.match(h, /data-act="inspadd" data-val="stroke" data-color="#000000" data-token=""/);
});

test("відступи: перемикач сторін; розкритий — вісім полів замість чотирьох", () => {
  const closed = panelHTML(MIN_MODEL());
  assert.match(closed, /data-act="inspsides"[^>]*aria-pressed="false"/);
  const m = MIN_MODEL();
  const side = (p) => F({ id: p, props: [p], name: p, lab: { t: "·" } });
  m.spacing = { ...m.spacing, sides: true,
    pad: { top: side("padding-top"), right: side("padding-right"), bottom: side("padding-bottom"), left: side("padding-left") },
    mar: { top: side("margin-top"), right: side("margin-right"), bottom: side("margin-bottom"), left: side("margin-left") } };
  const open = panelHTML(m);
  assert.match(open, /data-act="inspsides"[^>]*aria-pressed="true"/);
  for (const p of ["padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin-top", "margin-right", "margin-bottom", "margin-left"]) {
    assert.match(open, new RegExp(`data-prop="${p}"`));
  }
});

test("відступи: коли сторони різні, перемикач не вимикається", () => {
  const m = MIN_MODEL();
  m.spacing.sides = true; m.spacing.forced = true;
  m.spacing.pad = { top: F({ props: ["padding-top"] }), right: F({ props: ["padding-right"] }),
    bottom: F({ props: ["padding-bottom"] }), left: F({ props: ["padding-left"] }) };
  m.spacing.mar = { top: F({ props: ["margin-top"] }), right: F({ props: ["margin-right"] }),
    bottom: F({ props: ["margin-bottom"] }), left: F({ props: ["margin-left"] }) };
  assert.match(panelHTML(m), /data-act="inspsides"[^>]*disabled/);
});

test("текст: шрифт лише для читання, насиченість — вибір, решта — поля", () => {
  const h = panelHTML(FULL_MODEL());
  assert.match(h, /class="insp-ro">Inter</);
  assert.match(h, /<select class="insp-fi" data-act="insptune" data-prop="font-weight"/);
  assert.match(h, /<option value="600" selected>Semibold<\/option>/);
  for (const p of ["font-size", "line-height", "letter-spacing", "color"]) {
    assert.match(h, new RegExp(`data-prop="${p}"`));
  }
});

test("крок і межі несуть у data-атрибутах: трекінг 0.1 без нижньої межі, відступ ≥ 0", () => {
  const h = panelHTML(FULL_MODEL());
  assert.match(h, /data-prop="letter-spacing" data-props="letter-spacing" data-step="0.1" data-unit="px"/);
  assert.doesNotMatch(h.match(/<input[^>]*data-prop="letter-spacing"[^>]*>/)[0], /data-min/);
  assert.match(h.match(/<input[^>]*data-prop="padding-left"[^>]*>/)[0], /data-min="0"/);
});

/* ── Р3: жодних підписів-пояснень ───────────────────────────────────── */
test("у панелі немає рядка клавіш, <kbd>, підказок і речень-пояснень", () => {
  const h = panelHTML(FULL_MODEL());
  assert.doesNotMatch(h, /insp-keys|<kbd|insp-hint|insp-note|insp-warn/);
  assert.doesNotMatch(h, /<p[ >]/, "жодного абзацу-пояснення: лише шапки, поля й кнопки");
  const src = readFileSync(new URL("../app/insp-panel.js", import.meta.url), "utf8");
  assert.doesNotMatch(src.replace(/\/\*[\s\S]*?\*\//g, ""), /<kbd|<p /);
});

test("data-delta на полі розміру — лише коли delta не нуль (атрибут, не клас)", () => {
  assert.match(fieldOf(W({ delta: 50 })), /<input[^>]*data-delta="50"/);
  assert.doesNotMatch(fieldOf(W({})), /data-delta/);
  assert.doesNotMatch(fieldOf(W({ delta: 0 })), /data-delta/);
});
