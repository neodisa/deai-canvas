# Інспектор як у Figma (етап Г, 0.29.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Права панель інспектора стає однією панеллю властивостей у стилі Figma (розмір, відступи, заливка, текст…), а оверлей у рамці отримує ярлик, розмір, відстані за Alt і клавіатурну драбину Esc / Enter / ← →; «Лінійка» зникає.

**Architecture:** Дані й пакет тюнера не змінюються (`report()` → `tuneSet` → `applyTune` → `saveTune`). Нова чиста пара модулів: `app/insp-model.js` (payload оверлея + правки → модель панелі) і `app/insp-panel.js` (модель → HTML). `paintInsp` в `app.js` збирає модель і малює її; поля пишуть через наявний `tuneSet`, скраб — через `requestAnimationFrame` з одним записом пакета на відпусканні. Оверлей (`vendor/inspector.js`) втрачає режим лінійки й `_tip`, натомість малює ярлик, розмір і Alt-відстані (наявний `between`), та віддає оболонці `handleKey`/`setAlt` для клавіш із фокусом в оболонці.

**Tech Stack:** vanilla ES modules, `node --test`, Python `unittest`, Playwright live tests (Chromium).

**Spec:** `docs/superpowers/specs/2026-11-16-inspector-figma-design.md` — затверджена власником (прототип + текст). Не додавати UI, якого спека не описує.

**Rigor tier:** середній (один виконавець, один ревʼюер у кінці) — але живі тести на клавіші, Alt і тюнер обовʼязкові, і кожна нова перевірка доведена мутацією.

---

## Ground rules (binding)

- Repo: `deai-canvas-dev`, гілка `feat/inspector-figma` (worktree). Версія в `package.json` зараз `0.28.2`.
- Commit ONLY via `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <paths>` (new files: `git add -- <path>` first). Never `git add -A`, `--amend`, `stash`, `reset`, never checkout other branches. Never stage `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` or `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`.
- Tests never touch ports 8765/4317, `~/Liga Tools/deai-canvas`, the real `~/.deai`, `~/deai-published`, `~/deai-work`, `~/.gitconfig`, real `tasks.json`. Never set `DEAI_HOME`/`DC_TASKS_FILE`. Temp HOME and `python3 -B`. No network installs.
- Unit: `node --test tests/*.test.mjs` (NOT `node --test tests/`), `python3 -B -m unittest discover -s tests -q`.
- Live: ONE file at a time: `HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/<file>.test.mjs`.
- Never `pkill`/`killall` by pattern; kill by PID only. No `rm -rf` (use `mktemp -d` for fresh dirs).
- UI gets no explanatory caption/hint lines (owner rule). Назви клавіш — лише в `title` кнопки на острівці та в довідці `?`.
- Public repo: no real names, internal hosts, IPs, keys, tmp/scratchpad paths in files.
- Коментарі в коді, i18n, документи, повідомлення комітів — українською (як у репо). Звіт контролеру — англійською.
- Кожна нова перевірка доводиться мутацією: копія → зламати → червоне → `cp` назад → `cmp` ідентично → зелене. У звіті — кожна мутація одним рядком.
- Імена класів у розмітці — ПОВНІ літерали в кожній гілці (охоронець `tests/css-guards.test.mjs` читає `class="…"` регекспом по сирцю; інтерполяція в атрибуті class заборонена). Стан — атрибутами (`data-*`).

## Відхилення від спеки (знайдено читанням коду; пояснення в кінці, розділ «Self-review»)

1. Збирач моделі — окремий чистий модуль `app/insp-model.js`, а не функція в `app.js`: його можна тестувати в node, а `app.js` уже 8 тис. рядків. У `app.js` лишається лише проводка.
2. `report()` не віддає розмір, геометрію батька, прапорець власного тексту, `border-style` і кольори ДС для «+» — додається поле `facts` у payload (T2). Без нього ні «До країв батька», ні розділ «Текст», ні «+» не збудувати.
3. Спека каже, що `.insp-spec` зникає з `STYLE` оверлея. Не зникає: `reportHTML` (його і далі малює власна панель оверлея) малює `<section class="insp-spec">`. Зникають лише `.insp-spec dl/dt/dd` і `.insp-kind*` (вони були під `measureHTML`). Охоронець-свідок `.insp-spec` лишається чинним.
4. «+» біля обведення пише три довгі властивості (`border-style`, `border-width`, `border-color`), а не шорткат `border` — рядка `border` у звіті немає, і `tuneSet` без нього нікуди прикласти правку.
5. «Селектор» у `title` поля недоступний з payload (його дає лише `identity(prop)`, по одній властивості). У `title` ідуть властивості, `raw` (`var(--…)`), імʼя токена й вирок/приписане ДС.
6. Кнопка «до ДС» малюється лише там, де є `d.snap` (токен САМОЇ ДС із відомим значенням). Підказка з токена макета (`hint` без `ds`) кнопки не дає: вона веде не в ДС і не має значення для `snap`.
7. «Перший колір ДС поверхні» і «колір лінії ДС»: в індексі ДС немає семантичних категорій, лише `імʼя → значення`. Вибір — за іменем (`/surface|background|bg|canvas/` і `/border|line|stroke|divider|outline/`), чиста `pickDsColors` у `inspector-core.js`. Запасні значення: заливка `#FFFFFF` (як у спеці), обведення — власний колір тексту елемента (спека запасного не називає).
8. Порожній стан (нічого не вибрано): спека текстового підпису не залишає (`inspCascadeHint` прибирається). Панель показує лише шапку й порожнє тіло; назви клавіш — у `title` кнопки острівця.
9. Поправка контролера: підсвітка margin/padding в оверлеї (`_hl`/`_pad`, DevTools-оверлей v1.19) ЛИШАЄТЬСЯ — лише для наведеного (вибраний чистий: заливка коробки спотворювала його кольори, знайдено на знімку після T3); під Alt ховається. Див. Task 3, Step 4 (l).

## File map

| File | Change |
|---|---|
| `app/insp-panel.js` | NEW pure `panelHTML(model)` |
| `app/insp-model.js` | NEW pure `buildModel(report, {edits, sides})`, `alignWrites(dir, c, r)` |
| `app/shell-inspect.js` | `inspectHTML` = шапка + `panelHTML` + підвал; без вкладок, підказок, рядка клавіш, `measure` |
| `app/app.js` | імпорт моделі; `BAR_ACTIONS` (прибрати `insptab`; нові `inspnextoff`/`inspalign`/`inspdir`/`inspadd`/`inspsides`; змінити `insptune`/`insptunecolor`/`inspsnap`); `tuneSet` з `save:false`, `tuneWrite`; `paintInsp`; слухачі панелі (Enter/Esc/↑↓, `change`, скраб); пересилання клавіш `inspShellKey`; `api.yieldEsc` |
| `app/styles.css` | нова панель властивостей; прибрати правила звіту, лінійки, вкладок, `.insp-keys`; `--pick`, `--mono` |
| `app/i18n.js` | нові ключі `inspP*`, `inspF*`, `inspAl*`, … (uk+en); прибрати ключі лінійки/вкладок/клавіш; `inspectorKey`, `inspKeyAlt`, `inspKeyChild` |
| `app/shell-palette.js` | довідка `?`: рядок «M» → рядки «Alt» і «↵» |
| `app/vendor/inspector-core.js` | `pickDsColors` |
| `app/vendor/inspector.js` | `report().facts`; прибрати режим лінійки, `_tip`, `measure()`; ярлик, розмір, Alt, `handleKey`, `setAlt`, `yieldEsc`; новий `STYLE` |
| `app/vendor/insp-report.js` | прибрати `measureHTML`, `kindBadge`, `ROW_KEY`, `KIND_KEY` |
| `tests/_insp-fixtures.mjs` | NEW спільні фікстури моделі й payload |
| `tests/insp-panel.test.mjs`, `tests/insp-model.test.mjs` | NEW |
| `tests/shell-inspect.test.mjs`, `tests/css-guards.test.mjs`, `tests/insp-report.test.mjs`, `tests/island.test.mjs`, `tests/shell-palette.test.mjs`, `tests/inspector-core.test.mjs` | переписати/доповнити |
| live: `inspector-figma` (NEW), `inspector`, `inspector-panel`, `inspector-ds`, `shell-inspect`, `tuner`, `tuner-tasks`, `tuner-claude-clear`, `tuner-identity` | сценарії 1–8, виправлені селектори |
| `CHANGELOG.md`, `package.json` | 0.29.0 (T5, лише контролер) |

## Контракти між завданнями (щоб типи не розійшлись)

**Поле моделі `F`** (один контрол панелі):

```
{ id, kind: "num"|"color"|"weight"|"ro", props: ["padding-left","padding-right"], name,
  lab: {t: "W"} | {i: "padX"} | null, value: "12", mixed: false, swatch: "#1F4FE0" (лише color),
  options: [{value:"400", label:"Звичайна"}] (лише weight),
  verdict: "token"|"hardcode"|"off-ds"|"overridden"|"unlinked"|"unknown",
  token: "sp-3" (імʼя без "--", лише для token/off-ds/overridden), off: bool (hardcode|off-ds|overridden),
  snap: {token, value}|null, changed: bool, miss: bool, title: "…",
  step: 1, min: 0|null, unit: "px"|"", base: number|null }
```

**Модель панелі `M`** (`buildModel` → `panelHTML`):

```
{ name, path: {more: bool, items: [{name, idx}]}, offDs: n,
  size: {w: F, h: F},
  edges: null | {parent, top, right, bottom, left},
  layout: null | {kind: "flex"|"grid", dir: "row"|"column", ax: -1|0|1|2, ay: -1|0|1|2, gap: F|null},
  spacing: {sides: bool, forced: bool, padX, padY, marX, marY: F|null, pad: null|{top,right,bottom,left}, mar: null|{…}},
  fill: F|null, fillAdd: {value: "#FFFFFF", token: ""},
  stroke: null | {color: F, width: F}, strokeAdd: {value, token},
  radius: F|null,
  text: null | {family: string, weight: F|null, size, lh, ls, color: F|null} }
```

**Дії панелі** (`data-act` → `BAR_ACTIONS`): `inspector`, `inspcrumb` (`data-val` = індекс у `crumbs`), `insptune` / `insptunecolor` (поле; `data-prop` = перша властивість, `data-props` = усі через пробіл), `inspsnap` (`data-prop(s)`, `data-token`, `data-val`), `inspnextoff`, `inspalign` (`data-val` = `"c,r"`, `data-dir`), `inspdir` (`data-val` = `row|column`), `inspadd` (`data-val` = `fill|stroke`, `data-color`, `data-token`), `inspsides`, плюс наявні `insptunedrop`, `insptuneall`, `insptunenote`, `insptuneready`.

**API оверлея** (`window.CanvasInspector`): наявні `on`, `set`, `toggle`, `pinned`, `report()`, `identity(prop)`, `pinAt(i)`, `applyTune`, `clearTune`, `applyBySelector`, `clearBySelector`, `setChrome`, `setLabels`, `onChange`; нові `alt` (поле), `setAlt(on)`, `handleKey(key, {alt}) → boolean`, `yieldEsc` (колбек, ставить оболонка). Прибрані: `mode`, `setMode`, `toggleMode`, `measure()`.

---

### Task 1: чистий `insp-panel.js`, CSS, i18n, юніт-тести, css-guards

**Files:**
- Create: `app/insp-panel.js`, `tests/_insp-fixtures.mjs`, `tests/insp-panel.test.mjs`
- Modify: `app/styles.css` (додати блок після `.insp-hint`), `app/i18n.js` (додати ключі, uk і en), `tests/css-guards.test.mjs`, `tests/shell-inspect.test.mjs` (лише `PANEL_SOURCES`)

На цьому кроці стара розмітка звіту ще живе (її прибирає T2): новий CSS додається поруч, а охоронець навчається бачити нову розмітку.

- [ ] **Step 1: Базовий прогін** — переконатися, що старт зелений.

Run: `node --test tests/*.test.mjs 2>&1 | tail -8`
Expected: `# fail 0`. Записати число `# pass` у звіт.

- [ ] **Step 2: Фікстури** — створити `tests/_insp-fixtures.mjs`:

```js
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
```

- [ ] **Step 3: Failing-тести панелі** — створити `tests/insp-panel.test.mjs`:

```js
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
```

- [ ] **Step 4: Failing-доповнення css-guards** — у `tests/css-guards.test.mjs`:

  (a) імпорти: додати `import { panelHTML } from "../app/insp-panel.js";` і `import { FULL_MODEL, MIN_MODEL } from "./_insp-fixtures.mjs";` поруч із наявним `import { measureHTML, reportHTML } …`.

  (b) У розділі E перед `const DOCUMENTS = [` додати:

```js
/** Класи, які малює нова панель властивостей: усі гілки моделі (повна, найменша, grid, розкриті сторони). */
function panelClasses() {
  const out = new Set();
  const full = FULL_MODEL();
  const grid = FULL_MODEL();
  grid.layout = { kind: "grid", dir: "row", ax: -1, ay: -1, gap: full.layout.gap };
  const sides = FULL_MODEL();
  const side = (p) => ({ ...full.size.w, props: [p], id: p });
  sides.spacing = { ...sides.spacing, sides: true, forced: true,
    pad: { top: side("padding-top"), right: side("padding-right"), bottom: side("padding-bottom"), left: side("padding-left") },
    mar: { top: side("margin-top"), right: side("margin-right"), bottom: side("margin-bottom"), left: side("margin-left") } };
  for (const m of [full, MIN_MODEL(), grid, sides]) {
    for (const c of classesInMarkup(panelHTML(m))) out.add(c);
  }
  return out;
}
```

  (c) У `DOCUMENTS` для «права панель оболонки» додати поле `panel: true`; у `drawnClasses(doc)` перед `return drawn;` додати `if (doc.panel) for (const c of panelClasses()) drawn.add(c);`.

  (d) Наприкінці розділу E додати свідка вокабуляра (сирець ↔ рендер) — клас, дописаний у гілку, якої фікстури не проходять, не лишиться непоміченим:

```js
test("жоден клас insp-panel.js не лишився поза фікстурами — вокабуляр сирця = вокабуляр рендеру", () => {
  const source = classesInMarkup(readFileSync(path.join(APP, "insp-panel.js"), "utf8"));
  assert.ok(source.size > 10, "екстрактор не знайшов класів у insp-panel.js");
  const unrendered = [...source].filter((c) => !panelClasses().has(c)).sort();
  assert.deepEqual(unrendered, [],
    `у insp-panel.js є класи, яких не малює жодна фікстура: ${unrendered.join(", ")} — допиши фікстуру в tests/_insp-fixtures.mjs`);
});
```

  (e) У `tests/shell-inspect.test.mjs` додати до `PANEL_SOURCES` два рядки й змінити літерал:

```js
  { file: "app/insp-panel.js", marker: /export function panelHTML\s*\(/ },
```
  і `assert.equal(seen, 2, …)` → `assert.equal(seen, 3, …)` (текст повідомлення: `а не 3`). Файл `insp-model.js` додається в T2.

- [ ] **Step 5: Run — має бути червоно**

Run: `node --test tests/insp-panel.test.mjs tests/css-guards.test.mjs tests/shell-inspect.test.mjs 2>&1 | tail -15`
Expected: FAIL — `Cannot find module '../app/insp-panel.js'`.

- [ ] **Step 6: i18n-ключі** — у `app/i18n.js` у блок `uk` (після `inspSnapKnob`) і в блок `en` (після `inspSnapKnob`) додати. Українські:

```js
  // Етап Г (0.29.0): панель властивостей (`app/insp-panel.js`, `app/insp-model.js`).
  inspPSize: 'Розмір',
  inspPEdges: 'До країв батька',
  inspPAuto: 'Авто-лейаут',
  inspPSpacing: 'Відступи',
  inspPFill: 'Заливка',
  inspPStroke: 'Обведення й радіус',
  inspPText: 'Текст',
  inspMixed: 'Різні',
  inspOffCount: (n) => `${n} поза ДС`,
  inspAddFill: 'Додати заливку',
  inspAddStroke: 'Додати обведення',
  inspSides: 'Сторони окремо',
  inspDirRow: 'У рядок',
  inspDirCol: 'У стовпчик',
  inspAlLeft: 'ліворуч',
  inspAlCenter: 'по центру',
  inspAlRight: 'праворуч',
  inspAlTop: 'згори',
  inspAlMiddle: 'посередині',
  inspAlBottom: 'знизу',
  inspAlignCell: (h, v) => `${h}, ${v}`,
  inspFPadX: 'Внутрішній відступ ↔',
  inspFPadY: 'Внутрішній відступ ↕',
  inspFMarX: 'Зовнішній відступ ↔',
  inspFMarY: 'Зовнішній відступ ↕',
  inspFPadSide: (side) => `Внутрішній відступ — ${side}`,
  inspFMarSide: (side) => `Зовнішній відступ — ${side}`,
  inspFGap: 'Проміжок',
  inspFFill: 'Колір заливки',
  inspFStrokeW: 'Товщина обведення',
  inspFStrokeC: 'Колір обведення',
  inspFTextC: 'Колір тексту',
  inspWeightName: (w) => ({ 400: 'Звичайна', 500: 'Середня', 600: 'Напівжирна', 700: 'Жирна' })[w] || String(w),
```
  Англійські (ті самі ключі, той самий порядок):

```js
  inspPSize: 'Size',
  inspPEdges: 'To parent edges',
  inspPAuto: 'Auto layout',
  inspPSpacing: 'Spacing',
  inspPFill: 'Fill',
  inspPStroke: 'Stroke and radius',
  inspPText: 'Text',
  inspMixed: 'Mixed',
  inspOffCount: (n) => `${n} off DS`,
  inspAddFill: 'Add fill',
  inspAddStroke: 'Add stroke',
  inspSides: 'Sides separately',
  inspDirRow: 'Row',
  inspDirCol: 'Column',
  inspAlLeft: 'left',
  inspAlCenter: 'center',
  inspAlRight: 'right',
  inspAlTop: 'top',
  inspAlMiddle: 'middle',
  inspAlBottom: 'bottom',
  inspAlignCell: (h, v) => `${h}, ${v}`,
  inspFPadX: 'Padding ↔',
  inspFPadY: 'Padding ↕',
  inspFMarX: 'Margin ↔',
  inspFMarY: 'Margin ↕',
  inspFPadSide: (side) => `Padding — ${side}`,
  inspFMarSide: (side) => `Margin — ${side}`,
  inspFGap: 'Gap',
  inspFFill: 'Fill colour',
  inspFStrokeW: 'Stroke width',
  inspFStrokeC: 'Stroke colour',
  inspFTextC: 'Text colour',
  inspWeightName: (w) => ({ 400: 'Regular', 500: 'Medium', 600: 'Semibold', 700: 'Bold' })[w] || String(w),
```
  `inspDirTop/Right/Bottom/Left` лишаються: на них посилаються підписи сторін у `insp-model.js` (T2) — тому «прибрати `inspDir*`» зі спеки виконується частково (див. T3, grep).

- [ ] **Step 7: `app/insp-panel.js`** — створити:

```js
/**
 * Панель властивостей інспектора (етап Г, 0.29.0): модель на вході, рядок HTML на виході. ЧИСТИЙ модуль — ні DOM,
 * ні слухачів, ні звернення до макета (охоронець `tests/shell-inspect.test.mjs`, `PANEL_SOURCES`). Модель збирає
 * `app/insp-model.js`; проводку (`data-act` → дія) робить `app.js` тією ж делегацією на `#insp-panel`, що й раніше.
 *
 * ⛔ Жодних підписів-пояснень (правило власника, спека Р3): ні рядка клавіш, ні підказок під полями, ні речень про
 * вирок. Походження значення — у `title` ПОЛЯ (один титул на поле, не на внутрішній `input`: титул на вкладеному
 * контролі накрив би титул поля рівно там, де водять мишею).
 *
 * ⚠️ Класи — ПОВНІ літерали в кожній гілці, стан — `data-*`: охоронець css-guards читає `class="…"` регекспом.
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
```

  Перевірити: у `row(...(m.stroke ? [m.stroke.width] : []), m.radius)` `radius` може бути `null` — `fieldHTML(null)` віддає `""` ✓.

- [ ] **Step 8: CSS** — у `app/styles.css` у `:root` поруч із `--bad:#F37373;` додати токени:

```css
  /* Синій «змінено / вибрано» панелі властивостей і оверлея; моно-шрифт імен елементів. */
  --pick:#3D8BFF;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
```
  Одразу після правила `.insp-hint{…}` (перед коментарем `/* ── Звіт інспектора (T-39)`) вставити блок:

```css
/* ── Панель властивостей (0.29.0, етап Г) ─────────────────────────────────
   Вигляд — затверджений прототип. ⛔ Висота поля СТАЛА (`--h-sm`): нічого не переноситься, довге усікається — те саме
   правило, яке T-39 вивів для звіту. Стан — атрибутами `data-*` на `.insp-f`. */
.insp-props{padding:0}
.insp-path{display:flex;flex-wrap:wrap;align-items:center;gap:2px;padding:8px 10px 0;
  font:11.5px/1.3 var(--mono);color:var(--lo)}
.insp-pb{border:0;background:none;padding:2px 3px;border-radius:4px;color:var(--dim);cursor:pointer;font:inherit}
.insp-pb:hover{background:var(--s3);color:var(--hi)}
.insp-el{display:flex;align-items:center;gap:8px;padding:6px 10px 10px;border-bottom:1px solid var(--line)}
.insp-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font:600 13px/1.3 var(--mono);color:var(--hi)}
.insp-off{flex:none;margin-left:auto;padding:1px 7px;border-radius:999px;background:none;cursor:pointer;
  border:1px solid color-mix(in srgb,var(--open) 45%,transparent);color:var(--open);font:inherit;font-size:11px}
.insp-off:hover{background:color-mix(in srgb,var(--open) 14%,transparent)}
.insp-sec{display:grid;gap:6px;padding:10px 10px 12px;border-bottom:1px solid var(--line)}
.insp-sh{display:flex;align-items:center;min-height:var(--h-xs);font-size:11.5px;font-weight:600;color:var(--hi)}
.insp-ib{display:inline-grid;place-items:center;flex:none;width:var(--h-xs);height:var(--h-xs);margin-left:auto;
  border:0;border-radius:var(--r-sm);background:none;color:var(--dim);cursor:pointer}
.insp-ib:hover{background:var(--s4);color:var(--hi)}
.insp-ib[aria-pressed="true"]{background:var(--s4);color:var(--hi)}
.insp-ib:disabled{cursor:default}
.insp-row{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.insp-row--1{grid-template-columns:1fr}
.insp-f{position:relative;display:flex;align-items:center;height:var(--h-sm);min-width:0;
  border:1px solid transparent;border-radius:var(--r-sm);background:var(--s0)}
.insp-f:hover{border-color:var(--line2)}
.insp-f:focus-within{border-color:var(--sel)}
.insp-f[data-tuned]::before{content:"";position:absolute;left:-6px;top:50%;width:4px;height:4px;margin-top:-2px;
  border-radius:50%;background:var(--pick)}
.insp-f[data-miss]{border-style:dashed;border-color:var(--open)}
.insp-fl{flex:none;display:inline-grid;place-items:center;min-width:24px;height:100%;padding:0 4px;
  color:var(--lo);font-size:11px;cursor:ew-resize;user-select:none;touch-action:none}
.insp-fl .ico{color:var(--lo)}
.insp-fi{flex:1;min-width:0;height:100%;border:0;background:none;padding:0 2px;outline:none;
  font:inherit;font-size:12px;font-variant-numeric:tabular-nums;color:var(--hi)}
select.insp-fi{padding:0 6px}
select.insp-fi option{background:var(--s1)}
.insp-f[data-off] .insp-fi{color:var(--open)}
.insp-tok{flex:none;max-width:56%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 7px 0 2px;
  font:10.5px/1 var(--mono);color:var(--lo)}
.insp-tok[data-off]{color:var(--open)}
.insp-snap{flex:none;height:20px;margin-right:4px;padding:0 6px;border-radius:4px;background:none;cursor:pointer;
  border:1px solid color-mix(in srgb,var(--open) 50%,transparent);color:var(--open);
  font:10.5px/1 var(--mono);white-space:nowrap;max-width:46%;overflow:hidden;text-overflow:ellipsis}
.insp-snap:hover{background:color-mix(in srgb,var(--open) 14%,transparent)}
.insp-sw{flex:none;width:14px;height:14px;margin:0 4px 0 7px;border-radius:3px;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.18)}
.insp-ro{flex:1;min-width:0;padding:0 7px;font-size:12px;color:var(--mid);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.insp-edges{display:grid;grid-template-columns:44px 1fr 44px;grid-template-rows:22px 30px 22px;align-items:center;
  justify-items:center;padding:4px;border-radius:var(--r-sm);background:var(--s0);
  font:11px/1 var(--mono);color:var(--mid);font-variant-numeric:tabular-nums}
.insp-e-box{grid-column:2;grid-row:2;width:100%;height:100%;display:grid;place-items:center;overflow:hidden;
  white-space:nowrap;border:1px solid var(--line2);border-radius:3px;color:var(--lo);font-size:10.5px}
.insp-e-t{grid-column:2;grid-row:1}
.insp-e-b{grid-column:2;grid-row:3}
.insp-e-l{grid-column:1;grid-row:2}
.insp-e-r{grid-column:3;grid-row:2}
.insp-al{display:grid;grid-template-columns:auto 1fr;gap:6px;align-items:start}
.insp-al-side{display:grid;gap:6px}
.insp-dirs{display:flex;gap:2px;padding:2px;height:var(--h-sm);border-radius:var(--r-sm);background:var(--s0)}
.insp-dir{display:inline-grid;place-items:center;width:28px;border:0;border-radius:4px;background:none;
  color:var(--dim);cursor:pointer}
.insp-dir[aria-pressed="true"]{background:var(--s3);color:var(--hi)}
.insp-align{display:grid;grid-template-columns:repeat(3,1fr);width:62px;height:62px;padding:4px;
  border-radius:var(--r-sm);background:var(--s0)}
.insp-cell{display:grid;place-items:center;border:0;background:none;cursor:pointer;padding:0}
.insp-cell::after{content:"";width:3px;height:3px;border-radius:50%;background:var(--lo)}
.insp-cell:hover::after{background:var(--mid)}
.insp-cell[aria-pressed="true"]::after{width:12px;height:4px;border-radius:2px;background:var(--pick)}
.insp-pb:focus-visible,.insp-ps{color:var(--lo);padding:0 1px}
.insp-ib:focus-visible,.insp-cell:focus-visible,.insp-dir:focus-visible,
.insp-snap:focus-visible,.insp-off:focus-visible{outline:2px solid var(--sel);outline-offset:1px}
```
  ⚠️ Останній селектор `.insp-path button:focus-visible` містить тег — прибрати перший елемент переліку (охоронець «dead rules» читає `.insp-path`, це не проблема, але щоб не дублювати) і написати `.insp-pb:focus-visible,.insp-ib:focus-visible,…`.

- [ ] **Step 9: Run — має бути зелено**

Run: `node --test tests/insp-panel.test.mjs tests/css-guards.test.mjs tests/shell-inspect.test.mjs tests/i18n.test.mjs tests/i18n-keys.test.mjs tests/i18n-literals.test.mjs tests/icons.test.mjs 2>&1 | tail -15`
Expected: `# fail 0`. Якщо `css-guards` скаржиться на клас без правила — додати правило; якщо на мертве правило — це старий `insp-pb`/`insp-ps` без розмітки: `.insp-ps` має мати правило (додати `.insp-ps{color:var(--lo);padding:0 1px}`).

- [ ] **Step 10: Мутації** (звіт: по рядку на кожну)
  1. `insp-panel.js`: змінити `data-off` у гілці off-ds на `data-offx` → тест «вирок off-ds» червоний.
  2. Прибрати з `fieldHTML` гілку `HEX6.test` (завжди писати `style`) → тест «сміття в зразок не потрапляє» червоний.
  3. У `styles.css` перейменувати `.insp-cell` → `.insp-cellx` → css-guards червоний («клас без правила»).
  4. У `panelHTML` дописати `<p class="insp-hint">x</p>` → тест Р3 червоний.

  Кожну: `cp` файл у `$(mktemp -d)`, зламати, прогнати, `cp` назад, `cmp`.

- [ ] **Step 11: Commit**

```bash
git add -- app/insp-panel.js tests/_insp-fixtures.mjs tests/insp-panel.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.29.0): панель властивостей інспектора — чиста розмітка, стилі, ключі" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/insp-panel.js tests/_insp-fixtures.mjs tests/insp-panel.test.mjs app/styles.css app/i18n.js tests/css-guards.test.mjs tests/shell-inspect.test.mjs
```

**Live proof T1:** розмітка ще ніде не змонтована; доказ — юніти + охоронці (кроки 9–10). Живий доказ — наприкінці T2.

---

### Task 2: модель, дані оверлея, проводка в `app.js`, нова `inspectHTML`

**Files:**
- Create: `app/insp-model.js`, `tests/insp-model.test.mjs`
- Modify: `app/vendor/inspector-core.js` (+`pickDsColors`), `tests/inspector-core.test.mjs`, `app/vendor/inspector.js` (`report().facts`), `app/shell-inspect.js`, `app/app.js`, `app/styles.css` (прибрати старе), `tests/shell-inspect.test.mjs`, `tests/css-guards.test.mjs`, `tests/_insp-fixtures.mjs` (payload)

- [ ] **Step 1: Failing-тест `pickDsColors`** — у `tests/inspector-core.test.mjs`: додати `pickDsColors` до імпорту з `../app/vendor/inspector-core.js` і дописати наприкінці файла:

```js
// кольори ДС для «+» біля заливки й обведення (етап Г): за імʼям токена, лише непрозорі #rrggbb
{
  const toks = new Map([
    ['--color-text-100', ['#111111']],
    ['--color-surface-1', ['#F6F8FC']],
    ['--color-surface-alpha', ['#FBFBFF1A']],
    ['--color-border-subtle', ['#DDE3EE']],
  ]);
  assert.deepStrictEqual(pickDsColors(toks), {
    fill: { token: '--color-surface-1', value: '#f6f8fc' },
    line: { token: '--color-border-subtle', value: '#dde3ee' },
  });
  assert.deepStrictEqual(pickDsColors(new Map([['--a', ['#123456']]])), { fill: null, line: null });
  assert.deepStrictEqual(pickDsColors(null), { fill: null, line: null });
}
```
  Run: `node tests/inspector-core.test.mjs` → FAIL (`pickDsColors is not a function` / not exported).

- [ ] **Step 2: Реалізація** — у `app/vendor/inspector-core.js` після `dsIndex`:

```js
/**
 * Кольори ДС для кнопок «+» біля заливки й обведення (етап Г). В індексі ДС немає семантичних категорій, лише
 * `імʼя → значення`, тому вибір — за імʼям: «поверхня» (surface|background|bg|canvas) і «лінія»
 * (border|line|stroke|divider|outline). Береться ПЕРШИЙ токен з непрозорим значенням (`#rrggbb` після нормалізації);
 * альфа-кольори пропускаються. Нема збігу — `null`, і викликач підставляє запасне значення.
 */
export function pickDsColors(tokens) {
  const out = { fill: null, line: null };
  if (!tokens || typeof tokens.entries !== 'function') return out;
  const FILL = /(surface|background|bg|canvas)/i;
  const LINE = /(border|line|stroke|divider|outline)/i;
  for (const [name, values] of tokens.entries()) {
    const hex = (Array.isArray(values) ? values : [values]).map(normalizeValue)
      .find((v) => /^#[0-9a-f]{6}$/.test(v));
    if (!hex) continue;
    if (!out.fill && FILL.test(name)) out.fill = { token: name, value: hex };
    if (!out.line && LINE.test(name)) out.line = { token: name, value: hex };
    if (out.fill && out.line) break;
  }
  return out;
}
```
  Run: `node tests/inspector-core.test.mjs` → ok.

- [ ] **Step 3: Фікстура payload** — дописати в `tests/_insp-fixtures.mjs`:

```js
/** Рядок звіту `describe()`. */
export const D = (prop, computed, o = {}) => ({ prop, computed, raw: computed, token: null, tokenValue: null,
  verdict: "unlinked", hint: [], ds: null, snap: null, ...o });

/** Payload `report()` картки: flex-рядок, заливка, обведення, власний текст. `facts` — як віддасть оверлей. */
export const REPORT = (o = {}) => ({
  crumbs: ["body", "section.hero", "div.cta", "a.btn--primary"],
  groups: {
    box: [D("margin-top", "0px"), D("margin-right", "0px"), D("margin-bottom", "0px"), D("margin-left", "0px"),
      D("padding-top", "12px", { verdict: "hardcode" }), D("padding-right", "20px", { verdict: "hardcode" }),
      D("padding-bottom", "12px", { verdict: "hardcode" }), D("padding-left", "20px", { verdict: "hardcode" })],
    layout: [D("display", "flex"), D("width", "120px"), D("height", "44px")],
    flex: [D("flex-direction", "row"), D("align-items", "center"), D("justify-content", "flex-start"),
      D("flex-wrap", "nowrap"), D("gap", "8px", { verdict: "token", token: "--sp-2", raw: "var(--sp-2)" })],
    type: [D("font-family", '"Inter", sans-serif'), D("font-size", "14px", { verdict: "hardcode" }),
      D("font-weight", "600"), D("line-height", "20px"), D("letter-spacing", "normal")],
    color: [D("color", "rgb(255, 255, 255)", { verdict: "hardcode" }),
      D("background-color", "rgb(31, 79, 224)", { verdict: "hardcode" }),
      D("border-color", "rgb(31, 79, 224)"), D("border-width", "1px"), D("border-radius", "8px")],
  },
  blocked: false, partial: false, dsInfo: { profile: "united", known: true, commit: "abc", figma: "x" },
  facts: { w: 120, h: 44, ownText: true,
    parent: { name: "div.cta", top: 0, right: 8, bottom: 0, left: 0 },
    extra: [D("border-style", "solid")], dsColors: { fill: null, line: null } },
  ...o,
});
```

- [ ] **Step 4: Failing-тести моделі** — створити `tests/insp-model.test.mjs`:

```js
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
```
  Перевірити арифметику лічильника: у `REPORT()` hardcode-поля: padding-top/right/bottom/left (4), font-size, color, background-color. У зведеному вигляді показані: padX, padY (2) + font-size + color + fill (3) = 5 ✓. З розкритими сторонами: 4 padding + 3 = 7. **Замінити** безглуздий вираз у тесті на `7`:

```js
  assert.equal(buildModel(REPORT(), { sides: true }).offDs, 7, "чотири padding + font-size + color + fill");
```

  Run: `node --test tests/insp-model.test.mjs` → FAIL (`Cannot find module '../app/insp-model.js'`).

- [ ] **Step 5: `app/insp-model.js`**:

```js
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
    f.value = String(Math.round(n === null ? (fallback || 0) : n));
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
```
  Перевірити за тестами: (а) `weight` без `facts.ownText` не будується — `text` null ✓; (б) `strokeAdd` у тесті «нема обведення» очікує `#FFFFFF` — `color: rgb(255,255,255)` → `colorOf` → `#ffffff` → `.toUpperCase()` ✓; (в) `spacing = { sides, forced, pad: null, mar: null, ...spacing }` — розсип ПІСЛЯ перезаписує `pad/mar` лише якщо вони є в `spacing` (є у гілці sides) ✓; (г) лічильник у режимі sides: пари видалені з `shown`, додані 8 сторін (`mk` пушить) — hardcode padding ×4 ✓ (=7 разом із font-size, color, fill).

- [ ] **Step 6: Run — моделі зелені**

Run: `node --test tests/insp-model.test.mjs tests/insp-panel.test.mjs 2>&1 | tail -15`
Expected: `# fail 0`. Падіння на `offDs`-тесті звіряти з арифметикою вище, а не «підганяти» очікування.

- [ ] **Step 7: Дані оверлея — `report().facts`.** У `app/vendor/inspector.js`: у список імпортів з `./inspector-dom.js` додати `describe, ds`; з `./inspector-core.js` — новий імпорт `import { pickDsColors } from './inspector-core.js';` (поруч з іншими імпортами). Над `const Inspector = {` додати:

```js
/**
 * Те, чого немає в `describeAll`, але потрібно панелі властивостей (етап Г): розмір рамки, геометрія до батька,
 * чи є власний текст, `border-style` (для «+» біля обведення) і кольори ДС (для «+» біля заливки й обведення).
 * Усе — примітиви й плоскі обʼєкти: жодного вузла DOM (та сама межа, що в `report()`).
 */
function panelFacts(el) {
  const r = el.getBoundingClientRect();
  const doc = el.ownerDocument;
  const par = el !== doc.body && el.parentElement && el.parentElement !== doc.documentElement ? el.parentElement : null;
  let parent = null;
  if (par) {
    const p = par.getBoundingClientRect();
    parent = { name: label(par), top: Math.round(r.top - p.top), right: Math.round(p.right - r.right),
      bottom: Math.round(p.bottom - r.bottom), left: Math.round(r.left - p.left) };
  }
  let own = false;
  for (const n of Array.from(el.childNodes || [])) {
    if (n.nodeType === 3 && n.nodeValue.trim()) { own = true; break; }
  }
  return { w: Math.round(r.width), h: Math.round(r.height), parent, ownText: own,
    extra: [describe(el, 'border-style')], dsColors: pickDsColors(ds().tokens) };
}
```
  У `report()` у повернутий обʼєкт (після `dsInfo: rep.dsInfo,`) додати `facts: panelFacts(el),` з коментарем «поіменно, як і решта».

- [ ] **Step 8: `shell-inspect.js`** — замінити весь файл після шапки-докстрінгу. Оновити докстрінг (прибрати абзаци про вкладки/режими/лінійку, лишити про підвал і чистоту), імпорти — `import { panelHTML } from "./insp-panel.js";` замість `measureHTML, reportHTML`; **видалити** функції `tabsHTML` і `keysHTML`; лишити `tuneRow`, `tuneElement`, `tuneFootHTML` без змін; `inspectHTML` замінити на:

```js
export function inspectHTML(state) {
  if (state.shellMode !== "layout" || !state.on) return "";
  /* Одна панель, без вкладок: «Лінійки» немає (відстані — Alt у рамці), «Тюнер» давно переїхав у підвал. `model` —
     готова модель (`buildModel`, `insp-model.js`); панель її лише малює. Порожній стан (нічого не вибрано) — лише
     шапка й порожнє тіло: підписів-пояснень немає (правило власника), клавіші названо в `title` кнопки острівця. */
  const foot = tuneFootHTML(state.tune, Number(state.tuneOther) || 0,
    Array.isArray(state.tuneMissing) ? state.tuneMissing : []);
  return `<div class="insp-top">${ico("inspect", 16)}
      <span class="panel-title">${esc(t("inspector"))}</span>
      <button class="icob" data-act="inspector" title="${esc(t("kEsc"))}">${ico("x")}</button></div>
    <div class="insp-body insp-props">${panelHTML(state.model)}</div>${foot ? `<div class="insp-foot">${foot}</div>` : ""}`;
}
```
  Поля стану в докстрінгу `inspectHTML`: `shellMode`, `on`, `model`, `tune`, `tuneOther`, `tuneMissing` (прибрати `mode`, `report`, `measure`).

- [ ] **Step 9: Переписати `tests/shell-inspect.test.mjs`** (юніт). Видалити тести, що перевіряли вкладки (`insptab`, aria-pressed режиму, підпис клавіш, підказки, лінійка, «звіт малюється В ПАНЕЛІ», «без payload… вкладки», «панель не рахує…», «крихти звіту…»). Лишити без змін: «у «Огляді» панелі немає», «коли інспектор вимкнений», «кнопка закриття», «заголовок панелі», усі тести підвалу (`PKG`, `EMPTY`, …) — вони викликають `inspectHTML(S({ tune: … }))`. Замінити допоміжні `S`/`REP`/`MEAS` і дописати:

```js
import { FULL_MODEL, MIN_MODEL } from "./_insp-fixtures.mjs";

const S = (o = {}) => ({ shellMode: "layout", on: true, model: null, tune: null, tuneOther: 0, tuneMissing: [], ...o });

test("панель із моделлю малює панель властивостей, без моделі — лише шапку", () => {
  const withModel = inspectHTML(S({ model: FULL_MODEL() }));
  assert.match(withModel, /class="insp-name"/);
  assert.match(withModel, /data-sec="size"/);
  const bare = inspectHTML(S());
  assert.match(bare, /class="insp-top"/);
  assert.doesNotMatch(bare, /insp-sec/);
});

test("вкладок, підказок і рядка клавіш немає ніде", () => {
  for (const model of [null, FULL_MODEL(), MIN_MODEL()]) {
    const h = inspectHTML(S({ model, tune: PKG() }));
    assert.doesNotMatch(h, /insptab|insp-tabs|insp-keys|<kbd|insp-hint/);
  }
});

test("підвал зʼявляється лише коли є що показати — порожній блок із лінією не малюється", () => {
  assert.doesNotMatch(inspectHTML(S({ model: MIN_MODEL() })), /class="insp-foot"/);
  assert.match(inspectHTML(S({ model: MIN_MODEL(), tune: PKG() })), /class="insp-foot"/);
});
```
  Лише ПІСЛЯ цього перевірити, що `PKG`/`EMPTY` оголошені в файлі ДО тестів, які їх уживають (вони оголошені як `const` у середині файла — тести підвалу нижче; нові тести з `PKG()` ставити ПІСЛЯ їх оголошення).
  У `PANEL_SOURCES` додати `{ file: "app/insp-model.js", marker: /export function buildModel\s*\(/ }`; `assert.equal(seen, 3,…)` → `4` (`а не 4`). **Видалити** `{ file: "app/vendor/insp-report.js", … }` із переліку (shell більше його не імпортує) і лишити `seen === 3`: `shell-inspect.js`, `insp-panel.js`, `insp-model.js`. Фінальне число — `3`; виправити те, що написано в Step 4(e) T1 (там було «3» для `shell-inspect + insp-report + insp-panel»; ця перестановка зберігає число 3, але склад інший).

- [ ] **Step 10: `app.js` — проводка.** Усі правки — за іменами функцій (номери рядків орієнтовні).

  (a) Імпорт біля `import { inspectHTML } from './shell-inspect.js';`:

```js
import { alignWrites, buildModel } from './insp-model.js';
```

  (b) `BAR_ACTIONS`: **видалити** блок `insptab: (val) => {…},` разом із коментарем над ним. Замінити `insptune`/`insptunecolor`/`inspsnap` і дописати нові дії (після `inspcrumb`):

```js
  /* Поле панелі властивостей. Застосування — на Enter і на `change` (див. слухачі панелі нижче), не на кожну
     літеру: «Enter застосовує, Esc скасовує» (спека, розділ «Поле»). */
  insptune: (val, el) => inspCommit(el),
  insptunecolor: (val, el) => inspCommit(el),
  /* Кнопка «до ДС»: пише правку зі `snap` у КОЖНУ властивість поля (пара — дві). */
  inspsnap: (val, el) => tuneWrite(String(el.dataset.props || el.dataset.prop).split(' ')
    .map((p) => [p, el.dataset.val, { token: el.dataset.token, value: el.dataset.val }])),
  /* «N поза ДС»: фокус на наступне бурштинове поле по колу. Курсор — модульна змінна, а не `activeElement`: клік по
     самій кнопці забирає фокус, і «наступне від активного» щоразу давало б перше. */
  inspnextoff: () => {
    const list = [...inspEl.querySelectorAll('.insp-f[data-off]')];
    if (!list.length) return;
    inspOffAt = (inspOffAt + 1) % list.length;
    const f = list[inspOffAt].querySelector('.insp-fi');
    f?.focus();
    f?.scrollIntoView?.({ block: 'nearest' });
  },
  inspalign: (val, el) => {
    const [c, r] = String(val).split(',').map(Number);
    tuneWrite(alignWrites(el.dataset.dir, c, r));
  },
  inspdir: (val) => tuneWrite([['flex-direction', val === 'column' ? 'column' : 'row']]),
  /* «+»: заливка пише `background-color`; обведення — три довгі властивості (рядка `border` у звіті немає). Токен, якщо
     колір узято з ДС, їде як `snap` (читач пакета бачить, що вибрано ТОКЕН). */
  inspadd: (val, el) => {
    const color = el.dataset.color || '';
    if (!/^#[0-9a-fA-F]{6}$/.test(color)) return;
    const snap = el.dataset.token ? { token: el.dataset.token, value: color } : null;
    if (val === 'fill') tuneWrite([['background-color', color, snap]]);
    else if (val === 'stroke') tuneWrite([['border-style', 'solid'], ['border-width', '1px'], ['border-color', color, snap]]);
  },
  inspsides: () => { inspSides = !inspSides; paintInsp(); },
```

  (c) Модульні змінні — поруч із `let inspDecls = new Map();`:

```js
/* Стан панелі властивостей. `inspSides` — дизайнер розкрив сторони відступів («окремо»); `inspOffAt` — курсор кола
   «N поза ДС» (скидається, коли вибрано інший елемент: `inspPinKey`); `inspScrub` — активне тягнення підпису. */
let inspSides = false;
let inspOffAt = -1;
let inspPinKey = '';
let inspScrub = null;
```

  (d) `tuneSet` — додати четвертий параметр і умовний запис. Сигнатура `function tuneSet(prop, value, snap = null, opts = {})`; в кінці замінити `saveTune();` на:

```js
  if (opts.save !== false) saveTune();
  return true;
```
  а на відкоті (`return;` після `tuneState = was; …`) — `return false;`; на ранніх `return;` — `return false;`.
  Одразу після `tuneSet` додати:

```js
/**
 * Записати кілька властивостей одним жестом: `[[prop, value, snap?], …]`. Пара полів (↔) — дві правки, матриця — дві,
 * «+» обведення — три. Запис пакета — ОДИН у кінці (`saveTune` зливає й так, але зайвий POST на кожну властивість
 * жодного сенсу не має). `save:false` — для скрабу: пакет пишеться лише на відпусканні.
 */
function tuneWrite(list, opts = {}) {
  let any = false;
  for (const [prop, value, snap] of list) {
    if (tuneSet(prop, value, snap || null, { save: false })) any = true;
  }
  if (any && opts.save !== false) saveTune();
  return any;
}
```

  (e) Замінити `function tuneField(el, delta = 0) {…}` на:

```js
/** Застосувати поле панелі (Enter / change). Порожнє, недобране й незмінене — не значення; «Різні» порожнім не перетираємо. */
function inspCommit(el) {
  const props = String(el.dataset.props || el.dataset.prop || '').split(' ').filter(Boolean);
  if (!props.length) return;
  if (el.dataset.act === 'insptunecolor') {
    let h = el.value.trim().replace(/^#/, '');
    if (/^[0-9a-f]{3}$/i.test(h)) h = h.replace(/./g, '$&$&');
    if (!/^[0-9a-f]{6}$/i.test(h) || h.toUpperCase() === el.defaultValue.toUpperCase()) return;
    tuneWrite(props.map((p) => [p, `#${h.toUpperCase()}`]));
    return;
  }
  if (el.tagName === 'SELECT') { tuneWrite(props.map((p) => [p, el.value])); return; }
  const raw = el.value.trim().replace(',', '.');
  const n = Number(raw);
  if (raw === '' || !Number.isFinite(n) || raw === el.defaultValue.trim()) return;
  const min = el.dataset.min === undefined ? null : Number(el.dataset.min);
  const v = min === null ? n : Math.max(min, n);
  tuneWrite(props.map((p) => [p, tuneRound(v) + (el.dataset.unit || '')]));
}

/** ↑/↓ у полі: крок поля (`data-step`) × множник (Shift = ×10). Порожнє поле (`normal`, «Різні») крокує від `data-base` або 0. */
function inspStep(el, mult) {
  const step = Number(el.dataset.step) || 1;
  const cur = parseFloat(String(el.value).replace(',', '.'));
  const base = Number.isFinite(cur) ? cur : (Number(el.dataset.base) || 0);
  const min = el.dataset.min === undefined ? null : Number(el.dataset.min);
  let v = Math.round((base + mult * step) * 100) / 100;
  if (min !== null) v = Math.max(min, v);
  el.value = String(v);
  inspCommit(el);
}
```
  Рядок `const tuneRound = …` (вище за `tuneField`) лишається.

  (f) `paintInsp` — змінити так (старе → нове):
  - Перший рядок тіла: `if (inspScrub) return;` (під час скрабу панель не перемальовується — оновлює лише поле, див. слухачі).
  - Видалити `overlayMode`, `tab` і всі посилання на них. Звіт: `const rep = api && api.on ? api.report() : null;`.
  - Після побудови `inspDecls` (цикл по `rep.groups`) додати рядок для `facts.extra`:

```js
    for (const d of (rep.facts && rep.facts.extra) || []) inspDecls.set(d.prop, d);
```
  - Ключ піна й скидання кола:

```js
  const pinKey = rep ? rep.crumbs.join('>') : '';
  if (pinKey !== inspPinKey) { inspPinKey = pinKey; inspOffAt = -1; }
```
  - Обʼєкт `st`: прибрати `mode`, `measure` і `report`; додати
    `model: rep ? buildModel(rep, { edits: tuneEdits(), sides: inspSides }) : null,`.
  - Відновлення фокуса: у виразі `keep` додати гілку каретки для текстових полів: замінити
    `(mine && act.dataset.act && act.dataset.prop ? { act: act.dataset.act, prop: act.dataset.prop, sel: null } : null)` на

```js
      (mine && act.dataset.act && act.dataset.prop
        ? { act: act.dataset.act, prop: act.dataset.prop,
          sel: act.tagName === 'INPUT' ? [act.selectionStart, act.selectionEnd] : null } : null)
```
  (поля тепер текстові, `selectionStart` не кидає — стара примітка «каретку не відновлюємо» застаріла; оновити коментар).

  (g) Слухачі панелі: замінити блоки `inspEl.addEventListener('input' …)`, `…('change' …)`, `…('keydown' …)` (три «крутилка/пікер/грубий крок») на:

```js
/* Записка Клоду — на КОЖНУ літеру (власник просив «записується одразу»). Поля властивостей на `input` НЕ пишуть:
   значення застосовує Enter або вихід із поля (`change`). */
inspEl.addEventListener('input', (ev) => {
  const note = ev.target.closest?.('[data-act="insptunenote"]');
  if (note) BAR_ACTIONS.insptunenote(note.value, note, ev);
});
inspEl.addEventListener('change', (ev) => {
  const el = ev.target.closest?.('[data-act="insptune"],[data-act="insptunecolor"]');
  if (el) inspCommit(el);
});
/* Enter застосовує, Esc скасовує введене й знімає фокус, ↑/↓ — ±1, Shift — ±10 (крок поля — `data-step`). */
inspEl.addEventListener('keydown', (ev) => {
  const el = ev.target.closest?.('[data-act="insptune"],[data-act="insptunecolor"]');
  if (!el || el.tagName !== 'INPUT') return;
  if (ev.key === 'Enter') { ev.preventDefault(); inspCommit(el); return; }
  if (ev.key === 'Escape') { ev.preventDefault(); ev.stopPropagation(); el.value = el.defaultValue; el.blur(); return; }
  if (el.dataset.act !== 'insptune') return;
  const dir = ev.key === 'ArrowUp' ? 1 : (ev.key === 'ArrowDown' ? -1 : 0);
  if (!dir) return;
  ev.preventDefault();
  inspStep(el, dir * (ev.shiftKey ? 10 : 1));
});

/* Скраб: тягнути підпис поля вліво-вправо. 3 px руху — один крок, Shift — десять. Правка застосовується не частіше
   разу на кадр (rAF), а пакет пишеться ОДИН раз — на відпусканні. Поки йде жест, панель не перемальовується
   (`paintInsp` виходить рано): оновлюється лише значення в самому полі. */
function inspScrubApply(s) {
  if (s.next === null || s.applied === s.next) return;
  s.applied = s.next;
  tuneWrite(s.props.map((p) => [p, tuneRound(s.next) + s.unit]), { save: false });
}
inspEl.addEventListener('pointerdown', (ev) => {
  const lab = ev.target.closest?.('[data-scrub]');
  const inp = lab && lab.parentElement.querySelector('input[data-act="insptune"]');
  if (!inp || ev.button !== 0) return;
  ev.preventDefault();
  lab.setPointerCapture(ev.pointerId);
  const cur = parseFloat(String(inp.value).replace(',', '.'));
  inspScrub = { inp, props: String(inp.dataset.props || inp.dataset.prop).split(' '), x0: ev.clientX,
    v0: Number.isFinite(cur) ? cur : (Number(inp.dataset.base) || 0), step: Number(inp.dataset.step) || 1,
    min: inp.dataset.min === undefined ? null : Number(inp.dataset.min), unit: inp.dataset.unit || '',
    next: null, applied: undefined, raf: 0 };
});
inspEl.addEventListener('pointermove', (ev) => {
  const s = inspScrub;
  if (!s) return;
  let v = Math.round((s.v0 + Math.round((ev.clientX - s.x0) / 3) * s.step * (ev.shiftKey ? 10 : 1)) * 100) / 100;
  if (s.min !== null) v = Math.max(s.min, v);
  s.inp.value = String(v);
  s.next = v;
  if (!s.raf) s.raf = requestAnimationFrame(() => { s.raf = 0; inspScrubApply(s); });
});
const inspScrubEnd = () => {
  const s = inspScrub;
  if (!s) return;
  if (s.raf) { cancelAnimationFrame(s.raf); s.raf = 0; }
  inspScrubApply(s);                       // останній кадр жесту
  inspScrub = null;
  if (s.applied !== undefined) saveTune(); // ОДИН запис пакета на весь жест; нічого не крутили — нічого й не пишемо
  paintInsp();
};
inspEl.addEventListener('pointerup', inspScrubEnd);
inspEl.addEventListener('pointercancel', inspScrubEnd);
```
  У делегації `click` (`inspEl.addEventListener('click' …)`) умова `if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return;` лишається; додати `|| el.tagName === 'SELECT'`.

- [ ] **Step 11: Прибрати старе** (кожне — окремою перевіркою `grep` перед видаленням):
  - `app/styles.css`: видалити суцільний блок від коментаря `/* ── Звіт інспектора (T-39) ──` до кінця правила `.insp-kind--bad{…}` (він іде між `.insp-hint` і `/* ── Підвал панелі (T-39`); видалити правило `.insp-tabs{…}`; видалити блок `.insp-keys…` (три правила й коментар над ними, між `.insp-cancel:hover` і `/* Запит дерева в дорозі`). Лишити `.insp`, `.insp[hidden]`, `.insp-top`, `.insp-body`, `.insp-hint` (його використовує панель «Коментарі»), `.insp-foot` і все підвальне.
  - `tests/css-guards.test.mjs`: у `DOCUMENTS` для «права панель оболонки» замінити `render: { tunable: true, measure: true }` на `render: null`, `extra` на `[path.join(APP, "shell-inspect.js"), path.join(APP, "insp-panel.js"), path.join(APP, "comments-view.js")]` (`comments-view.js` малює `.insp-top/.insp-hint/.insp-body` панелі «Коментарі», яка ділить CSS з інспектором); `panel: true` лишається. У `drawnClasses` обгорнути `renderedClasses(doc.render)` умовою `doc.render ? … : new Set()`. Тест «ручки тюнера існують РІВНО в тому документі…» (`KNOBS`/`panel`/`overlay`) переписати: ручок `insptune`/`insptunecolor` у `reportHTML` немає в жодному документі (`panel` більше не малюється reportHTML) — тому перевіряти `overlay` як і раніше, а для оболонки — `panelHTML(FULL_MODEL())` містить обидві дії:

```js
  const KNOBS = ["insptune", "insptunecolor"];
  const panel = panelHTML(FULL_MODEL());
  const overlay = REPORT_CASES.map((p) => reportHTML(p, { tunable: false })).join("");
```
  - Свідок вокабуляра «жоден клас звіту не лишився поза рендером» (`source`/`rendered` по `insp-report.js`) — `rendered` тепер збирається лише з `{ tunable: false, measure: false }`; прибрати перший доданок із `tunable: true`.

- [ ] **Step 12: Run — усі юніти**

Run: `node --test tests/*.test.mjs 2>&1 | tail -12`
Expected: `# fail 0`. Типові червоні: `shell-inspect` (старі тести не прибрані), `css-guards` (мертве правило `.insp-sw` у `STYLE` оверлея чи в `styles.css`), `i18n-keys`.

- [ ] **Step 13: Мутації** (по рядку в звіті): (1) у `insp-model.js` прибрати `forced` (завжди `false`) → тест «різні сторони… розкриті самі» червоний; (2) у `mk` замінити `.sort(…)[0]` на `ds[0].verdict` → тест «вирок пари — найтяжчий» червоний; (3) у `pickDsColors` прибрати `find(/^#…/)` → тест з альфа-токеном червоний; (4) у `inspectHTML` повернути `insp-keys` → тест «вкладок, підказок… немає ніде» червоний.

- [ ] **Step 14: Живий доказ T2** — зібрати мінімальний живий сценарій. Створити `tests/live/inspector-figma.test.mjs` із першим тестом (повний набір — T4; тут доказ, що панель змонтована й поле пише):

```js
/**
 * Етап Г (0.29.0): панель властивостей і оверлей у бою. Мапа «перевірка → запобіжник → що буде без нього» — у кінці
 * файла (розділ «Мутації»), знята мутаційно.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 11590;
const VIEW = { width: 1400, height: 900 };

const PAGE = () => `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}
body{margin:0;font:16px/24px sans-serif;background:#fff}
#wrap{display:flex;flex-direction:column;gap:8px;padding:16px}
#card{display:flex;gap:12px;padding:10px 14px;border:1px solid #dde3ee;border-radius:7px;background:#f6f8fc}
#a{padding:6px 10px;background:#1f4fe0;color:#fff}
#b{padding:6px 10px;background:#e0e0e0}
</style></head><body><div id="wrap"><div id="card"><a id="a">One</a><a id="b">Two</a></div><p id="para">Hello</p></div></body></html>`;

async function openInspector(browser, url) {
  const page = await browser.newPage({ viewport: VIEW });
  await page.goto(`${url}/app/`);
  await page.waitForFunction(() => {
    const f = document.getElementById("frame");
    return !!(f && f.contentWindow && f.contentWindow.CanvasInspector);
  }, null, { timeout: 15000 });
  await page.click('#hud [data-act="inspector"]');
  await page.waitForFunction(() => document.getElementById("frame").contentWindow.CanvasInspector.on === true,
    null, { timeout: 3000 });
  return page;
}

/** Клік у центр елемента макета; чекаємо, поки оверлей його запінить. */
async function pin(page, sel) {
  const box = await page.frameLocator("#frame").locator(sel).boundingBox();
  assert.ok(box, `не знайшов ${sel} у макеті`);
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await page.waitForFunction((id) => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    return !!(api.pinned && api.pinned.id === id);
  }, sel.slice(1), { timeout: 3000 });
}

const pinnedId = (page) => page.evaluate(() => {
  const p = document.getElementById("frame").contentWindow.CanvasInspector.pinned;
  return p ? p.id || p.localName : null;
});

/** Пакет тюнера на диску, або null. */
function pkg(dir) {
  const f = path.join(dir, ".dc-tuner.json");
  if (!existsSync(f)) return null;
  try { return JSON.parse(readFileSync(f, "utf8")); } catch { return null; }
}
async function waitPkg(page, dir, pred, what) {
  for (let i = 0; i < 80; i += 1) {
    const p = pkg(dir);
    if (p && pred(p)) return p;
    await page.waitForTimeout(50);
  }
  assert.fail(`пакет так і не дочекався: ${what}: ${JSON.stringify(pkg(dir))}`);
}
const editOf = (p, prop) => (p.elements || []).flatMap((e) => e.edits).find((e) => e.prop === prop);

async function boot(t) {
  const { dir } = taskFixture({ html: PAGE });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE });
  t.after(() => child.kill());
  const browser = await chromium.launch();
  t.after(() => browser.close());
  return { dir, page: await openInspector(browser, url), url };
}

test("T2-proof. клік → панель властивостей із назвою й розділами; поле gap пише макет і пакет", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  assert.equal(await page.locator("#insp-panel .insp-name").textContent(), "div");
  for (const s of ["size", "edges", "layout", "spacing", "fill", "stroke"]) {
    assert.equal(await page.locator(`#insp-panel [data-sec="${s}"]`).count(), 1, `немає розділу ${s}`);
  }
  const gap = '#insp-panel .insp-f[data-prop="gap"] .insp-fi';
  await page.focus(gap);
  await page.keyboard.press("ArrowUp");
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi')?.value === "13");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((el) => getComputedStyle(el).gap), "13px");
  const p = await waitPkg(page, dir, (x) => editOf(x, "gap"), "правка gap");
  assert.equal(editOf(p, "gap").to, "13px");
});
```
  Run: `HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/inspector-figma.test.mjs 2>&1 | tail -15` → Expected: 1 pass. Мутація доказу: у `inspCommit` прибрати виклик `tuneWrite` → перевірка `gap === "13px"` червона.

- [ ] **Step 15: Commit**

```bash
git add -- app/insp-model.js tests/insp-model.test.mjs tests/live/inspector-figma.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.29.0): панель властивостей замість звіту — модель, поля, скраб, проводка" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/insp-model.js tests/insp-model.test.mjs tests/live/inspector-figma.test.mjs app/vendor/inspector-core.js tests/inspector-core.test.mjs app/vendor/inspector.js app/shell-inspect.js app/app.js app/styles.css tests/shell-inspect.test.mjs tests/css-guards.test.mjs tests/_insp-fixtures.mjs
```

> На цьому кроці живі файли `inspector-panel`, `shell-inspect`, `tuner*`, `inspector-ds` ще червоні (старі селектори, вкладки, M) — їх виправляє T4. Це очікувано; контролер не запускає повний live до T4.

---

### Task 3: оверлей — ярлик, розмір, Alt, клавіші, без лінійки

**Files:**
- Modify: `app/vendor/inspector.js`, `app/vendor/insp-report.js`, `app/app.js` (пересилання клавіш, `yieldEsc`), `app/shell-palette.js`, `app/i18n.js`, `app/styles.css` (лише коментарі, якщо згадують лінійку), `tests/insp-report.test.mjs`, `tests/css-guards.test.mjs`, `tests/island.test.mjs`, `tests/shell-palette.test.mjs`
- Test: `tests/inspector-nav.test.mjs` (NEW, юніт драбини й вибору цілі)

Оверлей в node не піднімається (чіпає `document` на імпорті), тому чисту частину — драбину пінів і вибір цілі Alt — виносимо в маленький чистий модуль, який можна тестувати.

- [ ] **Step 1: Failing-юніт драбини** — створити `tests/inspector-nav.test.mjs`:

```js
/**
 * Етап Г (0.29.0): чиста логіка клавіатурної драбини оверлея — що вибрати після Esc / Enter / ← → і яка ціль в Alt.
 * Дерево — прості вузли `{ parent, children }`: модуль про DOM не знає, `inspector.js` дає йому ці чотири функції.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { altTarget, nextPin } from "../app/vendor/inspector-nav.js";

const tree = () => {
  const mk = (name, parent = null) => ({ name, parent, children: [] });
  const body = mk("body");
  const wrap = mk("wrap", body); body.children.push(wrap);
  const a = mk("a", wrap); const b = mk("b", wrap); const c = mk("c", wrap); wrap.children.push(a, b, c);
  const kid = mk("kid", a); a.children.push(kid);
  return { body, wrap, a, b, c, kid };
};
const api = { parentOf: (n) => n.parent, childrenOf: (n) => n.children };

test("Esc: батько; на корені — зняти вибір; без вибору — вимкнути інспектор", () => {
  const { a, body, wrap } = tree();
  assert.deepEqual(nextPin("Escape", a, api), { pin: wrap });
  assert.deepEqual(nextPin("Escape", body, api), { pin: null });
  assert.deepEqual(nextPin("Escape", null, api), { off: true });
});

test("Enter: перший дочірній; без дітей — нічого не споживаємо", () => {
  const { a, wrap, b } = tree();
  assert.deepEqual(nextPin("Enter", wrap, api), { pin: a });
  assert.equal(nextPin("Enter", b, api), null);
  assert.equal(nextPin("Enter", null, api), null);
});

test("← / →: сусід; на краю лишаємось на місці, але ключ споживаємо (сторінка не гортається)", () => {
  const { a, b, c } = tree();
  assert.deepEqual(nextPin("ArrowRight", a, api), { pin: b });
  assert.deepEqual(nextPin("ArrowLeft", c, api), { pin: b });
  assert.deepEqual(nextPin("ArrowLeft", a, api), { pin: a });
  assert.deepEqual(nextPin("ArrowRight", c, api), { pin: c });
  assert.equal(nextPin("ArrowRight", null, api), null, "без вибору ← → не наші");
});

test("інші клавіші драбина не чіпає", () => {
  const { a } = tree();
  assert.equal(nextPin("x", a, api), null);
  assert.equal(nextPin("ArrowUp", a, api), null);
});

test("Alt-ціль: ← → ідуть сусідами від поточної цілі, ↑ — знову батько, без цілі — батько", () => {
  const { a, b, c, wrap } = tree();
  assert.equal(altTarget("ArrowRight", a, null, api), b);
  assert.equal(altTarget("ArrowRight", a, b, api), c, "друге натискання — далі по сусідах");
  assert.equal(altTarget("ArrowLeft", a, b, api), a, "назад до вибраного");
  assert.equal(altTarget("ArrowUp", a, c, api), wrap);
  assert.equal(altTarget("ArrowRight", c, null, api), null, "за краєм сусіда немає");
});
```
  Run: `node --test tests/inspector-nav.test.mjs` → FAIL (`Cannot find module`).

- [ ] **Step 2: `app/vendor/inspector-nav.js`** (чистий; лежить у `vendor/`, бо його імпортує оверлей):

```js
/* Клавіатурна драбина оверлея — чиста логіка без DOM (етап Г). Вузол — будь-що, що вміє `parentOf`/`childrenOf`;
   `inspector.js` дає ці дві функції поверх справжнього DOM (з відсівом власних хостів оверлея й `<html>`). */

const siblingsOf = (n, api) => {
  const p = api.parentOf(n);
  return p ? api.childrenOf(p) : [n];
};

/**
 * Що робить клавіша з вибором. `null` — клавіша не наша (не споживаємо); `{ pin }` — новий вибір (null — зняти);
 * `{ off: true }` — вимкнути інспектор.
 *  · Esc: батько → на корені зняти вибір → без вибору вимкнути;
 *  · Enter: перший дочірній (немає дітей — не наша);
 *  · ← / →: сусід; на краю лишаємось на місці, але клавішу споживаємо — щоб сторінка не гортала вбік під рукою
 *    дизайнера, який рухається по дереву.
 */
export function nextPin(key, pinned, api) {
  if (key === 'Escape') {
    if (!pinned) return { off: true };
    const up = api.parentOf(pinned);
    return { pin: up || null };
  }
  if (!pinned) return null;
  if (key === 'Enter') {
    const kids = api.childrenOf(pinned);
    return kids.length ? { pin: kids[0] } : null;
  }
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const sibs = siblingsOf(pinned, api);
    const next = sibs[sibs.indexOf(pinned) + (key === 'ArrowRight' ? 1 : -1)];
    return { pin: next || pinned };
  }
  return null;
}

/**
 * Ціль відстаней Alt з клавіатури. `current` — вже вибрана ціль (або null). Alt+→/← крокують сусідами ВІД ПОТОЧНОЇ
 * цілі (першого разу — від вибраного елемента), Alt+↑ повертає батька. За краєм сусіда немає — `null`.
 */
export function altTarget(key, pinned, current, api) {
  if (!pinned) return null;
  if (key === 'ArrowUp') return api.parentOf(pinned);
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const base = current || pinned;
    const sibs = siblingsOf(base, api);
    return sibs[sibs.indexOf(base) + (key === 'ArrowRight' ? 1 : -1)] || null;
  }
  return null;
}
```
  Run: `node --test tests/inspector-nav.test.mjs` → pass (5).

- [ ] **Step 3: Failing-юніт структури оверлея** — дописати в `tests/inspector-space-ds.test.mjs` НІЧОГО; натомість у новий `tests/inspector-nav.test.mjs` додати статичні охоронці сирця (оверлей читається текстом, не виконується):

```js
import { readFileSync } from "node:fs";
const overlay = readFileSync(new URL("../app/vendor/inspector.js", import.meta.url), "utf8");
const code = overlay.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

test("режиму лінійки й підказки-тултипа в оверлеї більше немає", () => {
  for (const gone of ["setMode", "toggleMode", "_ruler", "_candidates", "_containerBox", "_setMeas", "measure()", "_tip", "'ruler'"]) {
    assert.ok(!code.includes(gone), `в inspector.js лишився слід лінійки: ${gone}`);
  }
});

test("клавіші: оверлей ловить Alt, Esc, Enter, ← → і віддає оболонці handleKey / setAlt / yieldEsc", () => {
  for (const needle of ["e.key === 'Alt'", "e.key === 'Escape'", "e.key === 'Enter'", "e.key === 'ArrowLeft'",
    "handleKey(", "setAlt(", "yieldEsc"]) {
    assert.ok(code.includes(needle), `в inspector.js немає ${needle}`);
  }
});

test("STYLE оверлея: синій вибору й червоний відстаней; .insp-spec лишається (його малює reportHTML)", () => {
  const style = overlay.match(/const STYLE = `([\s\S]*?)`;/)[1];
  assert.match(style, /#3D8BFF/i); assert.match(style, /#F2554B/i);
  assert.ok(style.includes(".insp-spec"));
  assert.ok(!style.includes(".tip{") && !style.includes(".anch{"));
  // Підсвітка margin/padding (DevTools-оверлей, v1.19) лишається — поправка контролера.
  assert.ok(style.includes(".hl{") && style.includes(".hl-pad{"));
});
```
  Run → FAIL (слід лінійки є).

- [ ] **Step 4: Оверлей — реалізація.** У `app/vendor/inspector.js`:

  (a) Імпорти: прибрати `measure` (`import { between, measure } …` → `import { between } …`); додати `import { altTarget, nextPin } from './inspector-nav.js';`. Імпорт `pickDsColors`, `describe`, `ds` — з T2.

  (b) `STYLE`: видалити правила `.tip`, `.tip b`, `.tip .dim`, `.anch`, `.rg.box.v/.h`, `.rlab.box`, `.rg.v`/`.rg.h` (старі синьо-пунктирні) і коментарі над ними про лінійку; лишити `.btn`, `.btn:hover`, `.btn.on`, `.panel`, увесь блок `.insp-*` (`.insp-spec`, `.insp-f`, `.insp-dot*` …), `.hidden`. Додати (БЕЗ зворотних апострофів і `${` у коментарях — це шаблонний літерал):

```css
  /* Етап Г. Кольори оверлея — константи: документ макета токенів оболонки не бачить. Синій — вибір і наведення
     (так само, як у прототипі), червоний — відстані Alt. */
  .o-hov,.o-sel,.o-tgt{position:fixed;pointer-events:none;box-sizing:border-box;z-index:2147483000}
  .o-hov{outline:1px solid #3D8BFF}
  .o-sel{outline:2px solid #3D8BFF}
  .o-tgt{outline:1px dashed #F2554B}
  .o-tag,.o-size{position:fixed;pointer-events:none;z-index:2147483002;padding:1px 6px;background:#3D8BFF;
    color:#fff;white-space:nowrap;font:600 10.5px/16px ui-monospace,SFMono-Regular,Menlo,monospace}
  .o-tag{transform:translateY(-100%);border-radius:3px 3px 0 0}
  .o-tag.below{transform:none;border-radius:0 0 3px 3px}
  .o-size{transform:translateX(-50%);margin-top:6px;border-radius:4px}
  /* Лінії й числа відстаней. pointer-events:none не косметика: число лежить рівно в зазорі під курсором, і якби
     воно ловило події, ховер зіскакував би на нього. */
  .rul,.rg,.rlab{pointer-events:none}
  .rg{position:fixed;z-index:2147483001;box-sizing:border-box}
  .rg.v{border-left:1px solid #F2554B}
  .rg.h{border-top:1px solid #F2554B}
  .rg.lap.v{border-left-style:dotted}
  .rg.lap.h{border-top-style:dotted}
  .rlab{position:fixed;z-index:2147483002;padding:1px 5px;border-radius:4px;transform:translate(-50%,-50%);
    white-space:nowrap;background:#F2554B;color:#fff;font:600 10.5px/16px ui-monospace,SFMono-Regular,Menlo,monospace}
  .rlab.lap{outline:1px dotted #fff}
```

  (c) Розмітка в `init()`: замінити блок `box.innerHTML = …` на:

```js
    box.innerHTML = `
      <div class="o-hov hidden"></div>
      <div class="o-tag hidden"></div>
      <div class="o-sel hidden"></div>
      <div class="o-size hidden"></div>
      <div class="o-tgt hidden"></div>
      <div class="rul hidden">${DIRS.map((d) =>
        `<div class="rg hidden" data-ruler-line="${d}"></div>`
        + `<div class="rlab hidden" data-ruler-label="${d}"></div>`).join('')}</div>
      <button class="btn"><span aria-hidden="true">◎</span> <span data-lbl="inspector"></span></button>
      <div class="panel hidden"></div>`;
```
  Вузли `<div class="hl hidden">` і `<div class="hl-pad hidden">` у розмітці тіні ЛИШАЮТЬСЯ (поправка контролера — див. (l)),
  разом із `this._hl = sh.querySelector('.hl'); this._pad = sh.querySelector('.hl-pad');`.
  Посилання: замість `_anch/_tip` —

```js
    this._hov = sh.querySelector('.o-hov');
    this._tag = sh.querySelector('.o-tag');
    this._selb = sh.querySelector('.o-sel');
    this._size = sh.querySelector('.o-size');
    this._tgt = sh.querySelector('.o-tgt');
```
  Додати слухачі після `keydown`: 

```js
    window.addEventListener('keyup', (e) => { if (e.key === 'Alt') this.setAlt(false); }, true);
    window.addEventListener('blur', () => this.setAlt(false));
```

  (d) Стан: видалити `mode: 'cascade'`, `_meas`, `_measSig`; додати

```js
  /* Alt утримується: показуємо відстані від вибраного до цілі. `_altEl` — ціль, вибрана клавішами (Alt+← → ↑),
     перебиває ховер, поки курсор не зрушить на інший елемент. `yieldEsc` — колбек оболонки: поки відкрите питання,
     поповер чи форма, Esc належить їм, а не драбині. */
  alt: false,
  _altEl: null,
  _panelSeq: -1,
  yieldEsc: null,
```

  (e) Видалити методи `setMode`, `toggleMode`, `measure`, `_setMeas`, `_ruler`, `_candidates`, `_containerBox`, `_place`; змінити:

```js
  _navParent(el) {
    const p = el && el.parentElement;
    return p && p !== document.documentElement ? p : null;
  },
  /** Діти/сусіди без власних хостів оверлея й коментатора. */
  _kids(el) {
    return Array.from((el && el.children) || []).filter((n) => !n.matches(OVERLAY_HOSTS));
  },
  _api() {
    return { parentOf: (n) => this._navParent(n), childrenOf: (n) => this._kids(n) };
  },
  /** Єдина точка зміни вибору (клік, Esc/Enter/← →, крихта). `reveal` — докрутити до елемента (клавіші, не клік). */
  _setPin(el, reveal = false) {
    this.pinned = el || null;
    this._altEl = null;
    this._pinLeftFor = null;
    if (reveal && el && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    this._paint(this.pinned || this.hover);
  },
  /** Утримання Alt. Не міняє стану панелі оболонки — лише малює, тож `_emit` не кличемо. */
  setAlt(on) {
    const next = !!on && this.on;
    if (next === this.alt) return this;
    this.alt = next;
    if (!next) this._altEl = null;
    this._draw();
    return this;
  },
  /**
   * Клавіша для драбини. Кличе і власний `_onKey` (фокус у рамці), і оболонка (`inspShellKey`, фокус в оболонці) —
   * одна логіка на обидва шляхи. Повертає true, якщо клавішу споживано. Esc поступається, коли `yieldEsc()` каже,
   * що є відкрите питання/форма.
   */
  handleKey(key, mods = {}) {
    if (!this.on) return false;
    if (mods.alt) {
      if (!this.pinned) return false;
      const tgt = altTarget(key, this.pinned, this._altEl, this._api());
      if (key === 'ArrowUp' || key === 'ArrowLeft' || key === 'ArrowRight') {
        if (tgt) this._altEl = tgt;
        this._draw();
        return true;
      }
      return false;
    }
    if (key === 'Escape' && typeof this.yieldEsc === 'function' && this.yieldEsc()) return false;
    const step = nextPin(key, this.pinned, this._api());
    if (!step) return false;
    if (step.off) { this.set(false); return true; }
    this._setPin(step.pin, true);
    return true;
  },
```
  Зверни увагу: `altTarget` для ← → робить крок від поточної цілі; коли поточна ціль `null`, `altTarget` дає сусіда від вибраного.

  (f) `pinAt(i)`: `this._setPin(el)` замість двох рядків. `set(on)`: у гілці `!this.on` додати `this.alt = false; this._altEl = null;`.

  (g) `_emit`: `const sig = \`${this.on}|${this._pinSeq}\`;` і поправити докстрінг (прибрати «mode», «підпис лінійки»).

  (h) `_onMove` — замінити на:

```js
  _onMove(e) {
    if (!this.on) return;
    const el = this._pageEl(e);
    if (!el) return;                       // над чужим оверлеєм — не втручаємось
    e.stopPropagation();
    if (el !== this.hover) { this.hover = el; this._altEl = null; this._paint(this.pinned || el); }
    if (!this.pinned) return;
    /* Коли курсор нарешті зійшов із запіненого елемента, його :hover згас, і звіт треба перечитати
       (`_repaintPinned`). Рівно ОДИН перемальунок на вихід. */
    if (el === this.pinned || this.pinned.contains(el)) this._pinLeftFor = null;
    else if (this._pinLeftFor !== this.pinned) { this._pinLeftFor = this.pinned; this._repaintPinned(); }
  },
```
  `_repaintPinned`: прибрати рядок `if (this.mode === 'ruler') return;`; після `this._pinSeq += 1;` у `finally` додати `this._panelSeq = this._pinSeq;` (воно саме малює плаваюче вікно).

  (i) `_onDown`: `this.pinned = this.pinned === el ? null : el; this._paint(this.pinned || el);` → `this._setPin(this.pinned === el ? null : el);`.

  (j) `_onKey` — замінити цілком:

```js
  _onKey(e) {
    if (e.key === 'Alt') {
      if (this.on) { this.setAlt(true); e.preventDefault(); }
      return;
    }
    if (e.metaKey || e.ctrlKey) return;
    // Набір тексту (у т.ч. в полі comment-layer усередині його shadow DOM) не має ні вмикати інспектор, ні ловитись.
    if (isEditable(deepTarget(e)) || isEditable(activeDeep())) return;
    // Регексп, а не чотири порівняння: кирилична розкладка мусить працювати, а кирилиця в СТРОКОВОМУ літералі —
    // майбутнє спрацювання охоронця i18n (він не заглядає в регекспи).
    if (!e.altKey && /^[iIшШ]$/.test(e.key)) {
      this.toggle(); e.stopPropagation(); e.preventDefault(); return;
    }
    if (!this.on) return;
    const nav = e.key === 'Escape' || e.key === 'Enter' || e.key === 'ArrowLeft'
      || e.key === 'ArrowRight' || e.key === 'ArrowUp';
    if (!nav) return;
    if (this.handleKey(e.key, { alt: e.altKey })) { e.stopPropagation(); e.preventDefault(); }
  },
```

  (k) `_schedule`/`_reflow`:

```js
  _reflow() {
    if (!this.on) return;
    try { this._draw(); } finally { this._emit(); }
  },
```

  (l) `_hide`, `_frame`, `_paint`, `_draw`, `_pair` — замінити:

```js
  _hide() {
    [this._hov, this._tag, this._selb, this._size, this._tgt, this._rul, this._panel]
      .forEach((n) => n && n.classList.add('hidden'));
  },

  /** Коробка-рамка за прямокутником. */
  _place(box, r) {
    Object.assign(box.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px` });
    box.classList.remove('hidden');
  },

  _paint(el) {
    if (this.pinned !== this._pinWas) { this._pinWas = this.pinned; this._pinSeq += 1; }
    /* `finally`: якщо малювання впало на чужому макеті (воно ходить по живому DOM), батько все одно мусить
       дізнатись про стан. */
    try {
      this._draw();
      /* Плаваюче вікно звіту (сторінка без канваса) — лише коли змінився ЗВІТ (`_pinSeq`), а не на кожен рух
         курсора: `report()` коштує ~6 мс, а ховер при піні тепер теж малює. */
      if (this._panelSeq !== this._pinSeq) {
        this._panelSeq = this._pinSeq;
        if (this.pinned && this.pinned.isConnected) this._renderPanel();
        else this._panel.classList.add('hidden');
      }
    } finally { this._emit(); }
  },

  /**
   * Малювання за станом: наведення (рамка + ярлик), вибір (рамка 2 px + «W × H»), а з Alt — відстані від вибраного до
   * цілі (ховер, а немає — клавішна ціль чи батько) через `between`. Лише геометрія: сигнал назовні — у `_paint`.
   */
  _draw() {
    const pin = this.pinned && this.pinned.isConnected ? this.pinned : null;
    const hov = this.hover && this.hover.isConnected && this.hover !== pin ? this.hover : null;
    if (!pin && !hov) { this._hide(); return; }
    const alt = this.alt && !!pin;
    const hide = (...ns) => ns.forEach((n) => n.classList.add('hidden'));
    const px = (v) => `${v}px`;
    const hr = hov && !alt ? hov.getBoundingClientRect() : null;
    if (hr && finiteRect(hr)) {
      this._place(this._hov, hr);
      this._tag.textContent = label(hov);
      const below = hr.top < 18;
      Object.assign(this._tag.style, { left: px(hr.left), top: px(below ? hr.bottom : hr.top) });
      this._tag.classList.toggle('below', below);
      this._tag.classList.remove('hidden');
    } else hide(this._hov, this._tag);
    const pr = pin ? pin.getBoundingClientRect() : null;
    if (pr && finiteRect(pr)) {
      this._place(this._selb, pr);
      if (alt) hide(this._size);
      else {
        this._size.textContent = `${Math.round(pr.width)} × ${Math.round(pr.height)}`;
        Object.assign(this._size.style, { left: px(pr.left + pr.width / 2), top: px(pr.bottom) });
        this._size.classList.remove('hidden');
      }
    } else hide(this._selb, this._size);
    if (!alt) { hide(this._tgt, this._rul); return; }
    const tgt = (this._altEl && this._altEl.isConnected ? this._altEl : null) || hov || this._navParent(pin);
    const tr = tgt ? tgt.getBoundingClientRect() : null;
    if (!tr || !finiteRect(tr) || !pr || !finiteRect(pr)) { hide(this._tgt, this._rul); return; }
    this._place(this._tgt, tr);
    this._pair(pin, tgt);
  },
```
  Увага: `hov` при Alt береться з `this.hover` лише якщо `alt` — у гілці вище `hov && !alt`; для цілі Alt використовуємо `hov` (змінну, не `hr`) ✓.

  **Поправка контролера (16.11.2026): підсвітка margin/padding ЛИШАЄТЬСЯ.** Наявні шари `this._hl` (margin) і `this._pad`
  (padding) — DevTools-оверлей, який власник замовляв окремо (v1.19); спека їх не прибирає. Наявний `_frame(el)`
  перейменувати на `_box(el)`: тіло те саме (два `Object.assign` + `classList.remove('hidden')`), без `this._rect`/`this._cs`
  і без `return`. У `_draw` одразу після `const px = …` додати:

```js
    /* Коробка margin/padding (DevTools-оверлей, v1.19) — для наведеного, а немає — для вибраного; під Alt ховається,
       щоб не плутати з лініями відстаней. */
    const boxEl = alt ? null : (hov || pin);
    if (boxEl) this._box(boxEl); else hide(this._hl, this._pad);
```

  У `_hide` до переліку додати `this._hl, this._pad`. Класи `_hl`/`_pad` і їхні правила в `STYLE` не чіпати. У Step 10 (живий
  доказ T3) — ще одна перевірка: наведення без Alt → шар margin видимий; з Alt → схований. Мутація: прибрати рядок
  `if (boxEl) …` → перевірка червона.

  `_pair(anchor, target)`: прибрати рядки з `_setMeas`, весь блок `Object.assign(this._anch.style…)`/`this._anch.classList.remove('hidden')`; лишити `this._rul.classList.remove('hidden')`; у разі нескінченних прямокутників — `this._rul.classList.add('hidden'); return;` (без `_setMeas`). Класи ліній і плашок спростити: `line.className = \`rg ${vert ? 'v' : 'h'}${res.kind === 'overlap' ? ' lap' : ''}\`;` і `lab.className = \`rlab${res.kind === 'overlap' ? ' lap' : ''}\`;`.

  (m) `_renderPanel` лишається (читає `report()`); `_dsArrived`, `_tuned` без змін. Прибрати з докстрінгів згадки режиму/лінійки там, де вони тепер брешуть (`setLabels`: ключі `inspCascade`, `inspRuler` → лише `inspector`).

- [ ] **Step 5: `insp-report.js` — прибрати лінійку.** Видалити `ROW_KEY`, `KIND_KEY`, `kindBadge` і `measureHTML` разом із блоком-коментарем «Лінійка: числа в панель» (від `/* ── Лінійка: числа в панель` до кінця файла). У `tests/insp-report.test.mjs`: прибрати `measureHTML` з імпорту й видалити блок від `/* ── measureHTML: числа лінійки` до `/* ── Рядок про ДС: токени ПРОСТОРУ`. У `tests/css-guards.test.mjs`: прибрати `measureHTML` з імпорту, `MEASURE_CASES`, гілку `measure` у `renderedClasses`/`DOCUMENTS` (`measure: …`), перелік `render: { tunable: false, measure: false }` → `render: { tunable: false }`; шапку-коментар розділу E актуалізувати (рядки про `measureHTML` і `.insp-kind`).

- [ ] **Step 6: Оболонка — пересилання клавіш і Esc.** У `app/app.js` у `frame.addEventListener('load', …)` (там, де `api.setChrome(false)`) додати:

```js
    /* Esc поступається відкритому питанню/поповеру/формі оболонки (`askUp()`, палітра, модальні): драбина інспектора
       — найнижча сходинка Esc. */
    api.yieldEsc = () => shellModalOpen();
```
  Поруч із блоком слухачів панелі (після `inspScrubEnd`-слухачів, ДО великого `document.addEventListener('keydown', …)` палітри) додати:

```js
/* Клавіші інспектора, коли фокус в ОБОЛОНЦІ, а не в рамці: Alt, Esc, Enter, ← →, Alt+←/→/↑. Рамка слухає їх сама
   (`_onKey` оверлея); тут — той самий `handleKey`, одна логіка на обидва шляхи. Стрілки й Enter віддаємо лише коли
   нічого не сфокусовано (`target === body`): на кнопці чи в дереві шарів вони належать їм. Поле вводу, питання, палітра
   й дропдаун — теж не наші. */
function inspShellKey(ev) {
  const api = inspectorApi();
  if (!api || !api.on || mode === 'canvas' || homeOpen) return;
  if (ev.isComposing || ev.defaultPrevented || ev.metaKey || ev.ctrlKey) return;
  if (shellModalOpen() || openDd || cnDrawer || typingIn(ev, document)) return;
  if (ev.key === 'Alt') { api.setAlt(true); return; }
  if (ev.target !== document.body) return;
  if (api.handleKey(ev.key, { alt: ev.altKey })) ev.preventDefault();
}
document.addEventListener('keydown', inspShellKey);
document.addEventListener('keyup', (ev) => { if (ev.key === 'Alt') inspectorApi()?.setAlt(false); });
window.addEventListener('blur', () => inspectorApi()?.setAlt(false));
```
  (`openDd`, `cnDrawer`, `homeOpen`, `mode`, `typingIn`, `shellModalOpen` — наявні модульні імена `app.js`.)

- [ ] **Step 7: Довідка, палітра, ключі.**
  - `app/shell-palette.js` `keysHTML()`: у колонці «Макет» замінити `${row(`${t("inspCascade")} / ${t("inspRuler")}`, "M")}` на `${row(t("inspKeyAlt"), "Alt")}${row(t("inspKeyChild"), "↵")}`. Оновити докстрінг над `keysHTML` (рядок про `I` і `M`: тепер `I`, `Alt`, `↵` — `vendor/inspector.js`). `tests/shell-palette.test.mjs`: тест `keysHTML` назву «I/M/Esc/⌘K» → «I/Alt/Esc/⌘K» і додати `assert.match(html, /<kbd>Alt<\/kbd>/);`; у коментарі над «кожна kbd-підказка» виправити «`M` (каскад/лінійка)» на «`Alt`, `Enter`».
  - `app/i18n.js` (uk+en): додати `inspKeyAlt: 'Відстані до сусіда'` / `'Distances to a neighbour'`, `inspKeyChild: 'Дочірній елемент'` / `'Child element'`; змінити `inspectorKey`: uk `'Інспектор · I · Alt — відстані · Esc / ↵ — батько / дочірній · ← → — сусід'`, en `'Inspector · I · Alt — distances · Esc / ↵ — parent / child · ← → — neighbour'`.
  - `tests/island.test.mjs` рядок 26: `title="Інспектор · I"` → новий рядок uk.
  - **Прибрати ключі** (кожен — `grep -rn "<key>" app tests` ПЕРЕД видаленням; видаляти лише якщо споживачів, крім самого `i18n.js`, нема): `inspCascade`, `inspRuler`, `inspCascadeHint`, `inspRulerHint`, `inspKeysIntro`, `inspKeyToggle`, `inspKeyMode`, `inspKeyExit`, `inspMeasNear`, `inspMeasPair`, `inspKindElement`, `inspKindContainer`, `inspKindInside`, `inspKindDiagonal`, `inspKindGap`, `inspKindOverlap`, `inspAxisX`, `inspAxisY` — і в uk, і в en. **`inspDirTop/Right/Bottom/Left` ЛИШАЮТЬСЯ** (їх читає `insp-model.js` для підписів сторін). Якщо `grep` покаже, що ключ ще вживає `app/vendor/inspector.js` (`setLabels({ inspector, inspCascade, inspRuler })`) — спершу виправити споживача.

- [ ] **Step 8: Run — усі юніти**

Run: `node --test tests/*.test.mjs 2>&1 | tail -12`
Expected: `# fail 0`.

- [ ] **Step 9: Мутації** — (1) у `nextPin` для Esc повернути `{ pin: null }` на кореневому → тест «Esc: батько; на корені…» червоний… (насправді змінити `up || null` на `up`); (2) у `altTarget` прибрати гілку `ArrowUp` → тест «↑ — знову батько» червоний; (3) повернути `_tip` у `inspector.js` текстом → статичний тест «режиму лінійки… немає» червоний; (4) у `STYLE` замінити `#F2554B` на `#025cff` → тест «синій… червоний» червоний.

- [ ] **Step 10: Живий доказ T3** — дописати в `tests/live/inspector-figma.test.mjs` (імпорти й хелпери вже є з T2):

```js
/** Лінії відстаней в оверлеї: усередині shadow-кореня рамки. */
const altLines = (page) => page.evaluate(() => {
  const doc = document.getElementById("frame").contentDocument;
  const sh = doc.querySelector("[data-canvas-inspector]").shadowRoot;
  return sh.querySelectorAll(".rul:not(.hidden) .rg:not(.hidden)").length;
});

test("T3-proof. Alt показує відстані, відпущений Alt — ні; Alt+→ переводить ціль на сусіда", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  assert.equal(await altLines(page), 0, "без Alt ліній немає");
  await page.keyboard.down("Alt");
  assert.ok(await altLines(page) > 0, "з Alt є лінії до батька");
  await page.keyboard.up("Alt");
  assert.equal(await altLines(page), 0, "відпущений Alt прибирає лінії");

  await page.keyboard.down("Alt");
  await page.keyboard.press("ArrowRight");
  const ok = await page.evaluate(() => {
    const f = document.getElementById("frame");
    const sh = f.contentDocument.querySelector("[data-canvas-inspector]").shadowRoot;
    const tgt = sh.querySelector(".o-tgt").getBoundingClientRect();
    const b = f.contentDocument.getElementById("b").getBoundingClientRect();
    return Math.abs(tgt.left - b.left) < 1 && Math.abs(tgt.width - b.width) < 1;
  });
  await page.keyboard.up("Alt");
  assert.equal(ok, true, "ціль Alt — сусід #b");
});
```
  Run: `HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/inspector-figma.test.mjs 2>&1 | tail -15` → 2 pass. Мутація доказу: у `setAlt` прибрати `this._draw()` → перші `altLines > 0` червоніє.

- [ ] **Step 11: Commit**

```bash
git add -- app/vendor/inspector-nav.js tests/inspector-nav.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.29.0): оверлей — ярлик, розмір, відстані за Alt, клавіатурна драбина; лінійку прибрано" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/vendor/inspector-nav.js tests/inspector-nav.test.mjs app/vendor/inspector.js app/vendor/insp-report.js app/app.js app/shell-palette.js app/i18n.js tests/insp-report.test.mjs tests/css-guards.test.mjs tests/island.test.mjs tests/shell-palette.test.mjs tests/live/inspector-figma.test.mjs
```

---

### Task 4: живі тести — переписати зачеплені, дописати сценарії 1–8

**Files:**
- Modify: `tests/live/inspector-figma.test.mjs` (повний набір), `tests/live/shell-inspect.test.mjs`, `tests/live/inspector.test.mjs`, `tests/live/inspector-panel.test.mjs`, `tests/live/inspector-ds.test.mjs`, `tests/live/tuner.test.mjs`, `tests/live/tuner-tasks.test.mjs`, `tests/live/tuner-claude-clear.test.mjs`, `tests/live/tuner-identity.test.mjs`, `tests/live/tabs.test.mjs` (лише якщо падає)

Правило цього завдання: червоний файл спершу ДІАГНОСТУЄТЬСЯ (чи це застарілий селектор, чи справжня вада коду), і лише потім правиться. Тест не послаблюється заради зеленого; якщо перевірка втратила предмет (вкладка, M, лінійка), вона видаляється з поясненням у коментарі, а не залишається порожньою.

- [ ] **Step 1: Повний набір сценаріїв у `inspector-figma.test.mjs`.** Видалити тести `T2-proof` і `T3-proof` (їх поглинають сценарії) і додати нижче `boot`/`pin`/`pinnedId`/`waitPkg`/`altLines`:

```js
const POSTS = (page) => {
  const log = [];
  page.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/api/tuner")) log.push(r.url()); });
  return log;
};
const fieldValue = (page, prop) => page.locator(`#insp-panel .insp-f[data-prop="${prop}"] .insp-fi`).inputValue();

test("1. клік → панель із назвою й розділами; Esc → батько; Enter → дочірній; ← → — сусіди", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  assert.equal(await page.locator("#insp-panel .insp-name").textContent(), "a");
  for (const s of ["size", "edges", "spacing", "fill", "stroke", "text"]) {
    assert.equal(await page.locator(`#insp-panel [data-sec="${s}"]`).count(), 1, `немає розділу ${s}`);
  }
  assert.equal(await page.locator('#insp-panel [data-sec="layout"]').count(), 0,
    "#a не flex-контейнер (він flex-елемент): авто-лейауту немає");
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), "card", "Esc вибирає батька");
  await page.keyboard.press("Enter");
  assert.equal(await pinnedId(page), "a", "Enter вибирає першого дочірнього");
  await page.keyboard.press("ArrowRight");
  assert.equal(await pinnedId(page), "b");
  await page.keyboard.press("ArrowLeft");
  assert.equal(await pinnedId(page), "a");
  // Esc до кореня: card → wrap → body → зняти вибір → вимкнути
  for (const want of ["card", "wrap", "body"]) {
    await page.keyboard.press("Escape");
    assert.equal(await pinnedId(page), want);
  }
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), null, "на корені Esc знімає вибір");
  await page.keyboard.press("Escape");
  assert.equal(await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector.on), false);
});

test("1b. ті самі клавіші працюють із фокусом в ОБОЛОНЦІ (пересилання)", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.locator("#insp-panel .insp-top").click();            // фокус ушов із рамки в оболонку
  assert.equal(await page.evaluate(() => document.activeElement === document.body), true);
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), "card");
  await page.keyboard.press("Enter");
  assert.equal(await pinnedId(page), "a");
  await page.keyboard.press("ArrowRight");
  assert.equal(await pinnedId(page), "b");
});

test("1c. Esc поступається відкритому питанню оболонки", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.evaluate(() => {                                      // імітація відкритого питання: його тримає askUp()
    const d = document.createElement("div"); d.className = "cv-ask-scrim"; document.body.appendChild(d);
  });
  await page.evaluate(() => document.getElementById("frame").contentWindow.focus());
  await page.keyboard.press("Escape");
  assert.equal(await pinnedId(page), "a", "поки є питання, Esc не піднімає вибір");
});

test("2. Alt → лінії відстаней; відпущений Alt → ліній нема; Alt+→ — сусід; blur знімає лінії", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#a");
  await page.keyboard.down("Alt");
  assert.ok(await altLines(page) > 0);
  await page.keyboard.up("Alt");
  assert.equal(await altLines(page), 0);
  await page.keyboard.down("Alt");
  await page.keyboard.press("ArrowRight");
  const onB = await page.evaluate(() => {
    const f = document.getElementById("frame");
    const sh = f.contentDocument.querySelector("[data-canvas-inspector]").shadowRoot;
    const g = sh.querySelector(".o-tgt").getBoundingClientRect();
    const b = f.contentDocument.getElementById("b").getBoundingClientRect();
    return Math.abs(g.left - b.left) < 1;
  });
  assert.equal(onB, true, "Alt+→: ціль — сусід #b");
  await page.evaluate(() => document.getElementById("frame").contentWindow.dispatchEvent(new Event("blur")));
  assert.equal(await altLines(page), 0, "втрата фокуса вікна прибирає лінії, навіть без keyup");
  await page.keyboard.up("Alt");
});

test("3. ↑ у полі gap: +1 на макеті й у пакеті; Shift+↑ — +10", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  const gap = '#insp-panel .insp-f[data-prop="gap"] .insp-fi';
  assert.equal(await fieldValue(page, "gap"), "12");
  await page.focus(gap);
  await page.keyboard.press("ArrowUp");
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi').value === "13");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((e) => getComputedStyle(e).gap), "13px");
  await waitPkg(page, dir, (p) => editOf(p, "gap")?.to === "13px", "gap 13px");
  await page.keyboard.press("Shift+ArrowUp");
  await waitPkg(page, dir, (p) => editOf(p, "gap")?.to === "23px", "gap 23px");
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((e) => getComputedStyle(e).gap), "23px");
});

test("3b. пара ↔ пише ДВІ властивості; «Різні», коли сторони не рівні", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");                                        // padding: 10px 14px
  assert.equal(await fieldValue(page, "padding-left"), "14");
  const f = '#insp-panel .insp-f[data-prop="padding-left"] .insp-fi';
  await page.fill(f, "20");
  await page.press(f, "Enter");
  const p = await waitPkg(page, dir, (x) => editOf(x, "padding-left") && editOf(x, "padding-right"), "обидві сторони");
  assert.equal(editOf(p, "padding-left").to, "20px");
  assert.equal(editOf(p, "padding-right").to, "20px");
  // зробимо сторони різними через консоль макета й перечитаємо панель
  await page.frameLocator("#frame").locator("#card").evaluate((e) => { e.style.setProperty("padding-left", "3px", "important"); });
  await page.evaluate(() => document.getElementById("frame").contentWindow.CanvasInspector._tuned());
  await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="padding-top"]'));
  assert.equal(await page.locator('#insp-panel [data-act="inspsides"]').isDisabled(), true,
    "сторони різні — «окремо» розкрито само й не вимикається");
});

test("4. скраб підпису: значення міняється живцем, панель не перемальовується, пакет пишеться ОДИН раз", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  const label = page.locator('#insp-panel .insp-f[data-prop="gap"] .insp-fl');
  const box = await label.boundingBox();
  await page.evaluate(() => { document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi').dataset.keep = "1"; });
  const posts = POSTS(page);
  const cx = box.x + box.width / 2; const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx + 30, cy, { steps: 10 });                // 30 px = +10
  assert.equal(await page.evaluate(() => document.querySelector('#insp-panel .insp-f[data-prop="gap"] .insp-fi')?.dataset.keep),
    "1", "під час жесту панель не перемальовується цілком");
  assert.equal(posts.length, 0, "під час жесту пакет не пишеться");
  await page.mouse.up();
  const p = await waitPkg(page, dir, (x) => editOf(x, "gap")?.to === "22px", "gap 22px");
  assert.equal(editOf(p, "gap").to, "22px");
  await page.waitForTimeout(300);
  assert.equal(posts.length, 1, `пакет мусить писатись ОДИН раз за жест, а писався ${posts.length}`);
  assert.equal(await page.frameLocator("#frame").locator("#card").evaluate((e) => getComputedStyle(e).gap), "22px");
});

test("7. «Надіслати Клоду» → status: ready на диску і «Готово» в панелі", async (t) => {
  const { dir, page } = await boot(t);
  await pin(page, "#card");
  await page.focus('#insp-panel .insp-f[data-prop="gap"] .insp-fi');
  await page.keyboard.press("ArrowUp");
  await waitPkg(page, dir, (p) => p.status === "draft" && editOf(p, "gap"), "чернетка з правкою");
  await page.click("#insp-panel .insp-send");
  await waitPkg(page, dir, (p) => p.status === "ready", "status ready");
  assert.equal(await page.locator("#insp-panel .insp-ready").count(), 1);
});

test("8. клавіша M нічого не робить: ні режиму, ні лінійки; панель незмінна", async (t) => {
  const { page } = await boot(t);
  await pin(page, "#card");
  const before = await page.locator("#insp-panel").innerHTML();
  await page.keyboard.press("m");
  const st = await page.evaluate(() => {
    const api = document.getElementById("frame").contentWindow.CanvasInspector;
    const sh = api._host.shadowRoot;
    return { mode: api.mode, setMode: typeof api.setMode, ruler: sh.querySelectorAll(".rul:not(.hidden)").length };
  });
  assert.deepEqual(st, { mode: undefined, setMode: "undefined", ruler: 0 });
  assert.equal(await page.locator("#insp-panel").innerHTML(), before);
  assert.equal(await page.locator('#insp-panel [data-act="insptab"]').count(), 0);
});

/* ── Мутації (кожна знята: прибери запобіжник — перевірка червоніє) ─────────────────────────────────────────────────
 *  1   handleKey Esc → `nextPin`/`_setPin` в `inspector.js`; прибери `_setPin(step.pin, true)` — Esc нічого не піднімає.
 *  1b  `inspShellKey` в `app.js`; прибери `document.addEventListener('keydown', inspShellKey)` — фокус в оболонці глухий.
 *  1c  `api.yieldEsc` у `load`-обробнику `app.js`; прибери рядок — Esc піднімає вибір попри питання.
 *  2   `setAlt`/`_draw` + `keyup`/`blur` у `init()`; прибери `window.addEventListener('blur', …)` — лінії лишаються.
 *  3   `inspStep` + `tuneWrite`; Shift-множник `(ev.shiftKey ? 10 : 1)` у keydown-слухачі панелі.
 *  3b  `tuneWrite(props.map(…))` в `inspCommit`; лиши лише `props[0]` — `padding-right` не пишеться.
 *  4   `inspScrubApply` з `{ save: false }` і `if (s.applied !== undefined) saveTune()` у `inspScrubEnd`; прибери
 *      `{ save: false }` — POST на кожен кадр, `posts.length` > 1; прибери `if (inspScrub) return;` у `paintInsp` —
 *      зникає `data-keep` (панель перемалювалась під час жесту).
 *  7   `tuneReady` → `markReady`; лишається з T-39.
 *  8   прибери `_onKey`-видалення M: поверни `toggleMode` — `api.mode` перестає бути `undefined`.
 */
```
  Run: `HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/inspector-figma.test.mjs 2>&1 | tail -25`
  Expected: усі pass. Тест `3b` залежить від того, що `CanvasInspector._tuned()` — наявний метод (перемальовує пін і сигналить); якщо червоний на `inspsides disabled` — діагностувати: чи `forced` виставляється моделлю (юніт `insp-model` це покриває) чи панель не перечитала звіт.

- [ ] **Step 2: Мутації для кожного тесту вище** (по рядку у звіті): виконати 8 мутацій зі списку в коментарі файла; кожну — копія в `mktemp -d`, правка, прогін ТІЛЬКИ цього файла з `--test-name-pattern` на відповідний тест, `cp` назад, `cmp`.

- [ ] **Step 3: Сценарії 5 і 6 — у `inspector-ds.test.mjs`** (там уже є `withSpaceCanvas`, `pin`, `tokensArrived`). Замінити допоміжні `dotOf`/`titleOf`:

```js
/** Вирок поля — атрибут обгортки (`data-verdict`): колір поля й чип — похідні від нього. */
const verdictOf = (page, prop) => page.evaluate((p) => {
  const f = document.querySelector(`#insp-panel .insp-f[data-prop="${p}"]`);
  return f ? f.getAttribute("data-verdict") : null;
}, prop);
```
  Усі `assert.match(await dotOf(…), /insp-dot--tok\b/…)` → `assert.equal(await verdictOf(…), "token", …)`; `--hard` → `"hardcode"`; `--offds` → `"off-ds"`; `--over` → `"overridden"`. Селектор `.insp-note` (рядок про ДС) прибрано з панелі властивостей разом із поясненнями — тест E («напрямок без ДС») читав `.insp-note`: **видалити** його перевірку тексту й залишити лише твердження, що у напрямку без ДС жоден токен не «повз ДС» (`verdictOf(page, "color")` не `off-ds`/`overridden`); у коментарі пояснити, що рядок-пояснення прибрано правилом Р3, а рядок `dsInfo` лишається в пакеті тюнера (`pkg.ds`). Тест F («крапка веде назад у ДС») лишається: `.insp-snap` — та сама кнопка, `data-token`/`data-val` ті самі; `[data-tuned]` на `.insp-f` ті самі.

  Дописати два тести (сценарії 5, 6) у кінець файла:

```js
test("5. «до ДС» на бурштиновому полі: чип токена зʼявляється, правка зі snap лягає в пакет", async () => {
  await withSpaceCanvas(async (page, url) => {
    await tokensArrived(page);
    await pin(page, "#hard");
    assert.equal(await verdictOf(page, "color"), "hardcode");
    assert.equal(await page.locator('#insp-panel .insp-f[data-prop="color"] .insp-tok').count(), 0, "хардкод чипа не має");
    await page.click('#insp-panel .insp-f[data-prop="color"] .insp-snap');
    await page.waitForFunction(() => document.querySelector('#insp-panel .insp-f[data-prop="color"][data-tuned]'),
      null, { timeout: 3000 });
    const body = await (await fetch(`${url}/api/tuner`)).json();
    const edit = ((body.package || body).elements || []).flatMap((e) => e.edits).find((e) => e.prop === "color");
    assert.deepEqual(edit.snap, { token: "--color-primary-400", value: edit.snap.value });
  });
});

test("6. «N поза ДС» веде фокус на бурштинові поля по колу", async () => {
  await withSpaceCanvas(async (page) => {
    await tokensArrived(page);
    await pin(page, "#hard");
    const total = await page.locator("#insp-panel .insp-f[data-off]").count();
    assert.ok(total >= 2, `на хардкодній картці має бути щонайменше два бурштинові поля, а є ${total}`);
    const btn = page.locator('#insp-panel [data-act="inspnextoff"]');
    assert.match(await btn.textContent(), new RegExp(`^\\s*${total}\\b`), "лічильник = кількість бурштинових полів");
    const focusedProp = () => page.evaluate(() => document.activeElement?.closest(".insp-f")?.dataset.prop ?? null);
    const first = await page.evaluate(() => document.querySelector("#insp-panel .insp-f[data-off]").dataset.prop);
    await btn.click();
    assert.equal(await focusedProp(), first, "перший клік — перше бурштинове поле");
    await btn.click();
    const second = await page.evaluate(() => document.querySelectorAll("#insp-panel .insp-f[data-off]")[1].dataset.prop);
    assert.equal(await focusedProp(), second, "другий клік — наступне");
  });
});
```
  Мутації: (5) у `inspsnap` не передавати третій елемент `{token,value}` → `edit.snap` стає `null` → червоне; (6) у `inspnextoff` прибрати `inspOffAt = (inspOffAt + 1) % list.length` (завжди 0) → другий клік не рухається → червоне.

- [ ] **Step 4: Виправити решту зачеплених файлів — по одному.** Для кожного: запустити, діагностувати, виправити.

  | Файл | Що змінилось | Дія |
  |---|---|---|
  | `shell-inspect.test.mjs` (live) | немає `insptab`, режимів, M, підказок | тест **A**: перевірку `insptab >= 2` замінити на `assert.equal(await page.locator('#insp-panel [data-act="insptab"]').count(), 0)`; тест **B** («перемикач режиму міняє режим оверлея») **видалити** (предмет зник); тест **E** («клавіша M доходить до панелі») **видалити** — його покриває сценарій 8; тест **C**, **D** лишити: `Escape` у чистому стані вимикає інспектор (драбина дійшла до `set(false)`); «Огляд» ховає панель |
  | `inspector.test.mjs` | весь блок «режим лінійки» (A–S) стосується прибраного | видалити блок `test("інспектор: режим лінійки" …)`; збережені твердження про ГЕОМЕТРІЮ (`between`: вкладення, діагональ, перекриття — Q/R/S) переписати на Alt: пін A, `keyboard.down('Alt')`, ховер B, читати `.rg`/`.rlab` із shadow-кореня; решта (J, K, L, M, N, N2, O, P — про лінійку сусідів і плашки) втрачає предмет разом із `measure()` — видалити з коментарем-згадкою в шапці файла |
  | `inspector-panel.test.mjs` | `report()` має нове поле `facts`; панель без вкладок | тест A: перелік ключів `report()` доповнити `facts` і додати `structuredClone(facts)`; тести G (крихта) — шукати кнопки `[data-act="inspcrumb"]` у `.insp-path` (імена ті самі, індекс `data-val` — у `crumbs`); тест H («клавіша M оновлює панель») — **видалити**; 23 звернення до `.insp-*` → привести до нової розмітки: `.insp-f[data-prop]`, `.insp-fi`, `data-tuned` лишаються |
  | `tuner.test.mjs` | `rowValue`/`rowStepper`/`rowTuned` читають `.insp-f[data-prop]` — вони збережені; пари: `padding-bottom`/`padding-right` окремого поля не мають | у тестах, що адресують ДРУГУ властивість пари, спершу розкрити сторони: `await page.click('#insp-panel [data-act="inspsides"]')`; `Shift+ArrowUp` крутить ±10 і далі; тест «рядок не росте» міряє висоту `.insp-f` (стала `--h-sm` = 28) |
  | `tuner-tasks.test.mjs`, `tuner-claude-clear.test.mjs` | `bump()` = `focus` + `Shift+ArrowUp` | лишається чинним (`[data-act="insptune"][data-prop=…]` є); перевірити запуском |
  | `tuner-identity.test.mjs` | `identity(prop)` без змін | перевірити запуском |

  Кожен файл: `HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/<file>.test.mjs 2>&1 | tail -20`, ОДИН за раз. Якщо тест червоний не через селектор, а через поведінку (наприклад пакет не пишеться) — це вада T2/T3: зупинитись, виправити код, а не тест.

- [ ] **Step 5: Python-перевірка сценарію 8 (превʼю)** — наявні `tests/test_serve.py:192` (голий макет без інспектора) і `tests/test_spaces_serve.py:516` (превʼю без `inspector.js`) уже стережуть «в превʼю інспектора нема». Прогнати: `python3 -B -m unittest tests.test_serve tests.test_spaces_serve -q 2>&1 | tail -5` → OK. Нових перевірок не додавати.

- [ ] **Step 6: Повний юніт-прогін і окремі live-файли за переліком** — `node --test tests/*.test.mjs` і `python3 -B -m unittest discover -s tests -q`; живі — по одному: `inspector-figma`, `inspector`, `inspector-panel`, `inspector-ds`, `inspector-hint`, `inspector-project`, `shell-inspect`, `tuner`, `tuner-claude-clear`, `tuner-identity`, `tuner-tasks`, `tabs` (острівець: `["comments","inspector","feedback"]` не мусить змінитись), `shell-palette`, `shell-bar`. Записати pass/fail кожного у звіт.

- [ ] **Step 7: Commit**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(0.29.0): живі тести панелі властивостей і оверлея — сценарії 1–8, переписані зачеплені файли" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/live/inspector-figma.test.mjs tests/live/shell-inspect.test.mjs tests/live/inspector.test.mjs tests/live/inspector-panel.test.mjs tests/live/inspector-ds.test.mjs tests/live/tuner.test.mjs tests/live/tuner-tasks.test.mjs tests/live/tuner-claude-clear.test.mjs tests/live/tuner-identity.test.mjs
```

---

### Task 5: реліз (лише контролер)

**Files:** `CHANGELOG.md`, `package.json`.

- [ ] **Step 1: CHANGELOG** — над `## [0.28.2]` додати запис українською (стиль наявних):

```markdown
## [0.29.0] — 16.11.2026

Shell redesign, stage Г: inspector like Figma. The right panel of the inspector is now a property panel instead of a CSS report; the ruler is gone, distances are shown while Alt is held.

### Змінено
- Права панель інспектора — одна панель властивостей замість звіту й вкладок: шлях до предків, назва елемента, розділи «Розмір», «До країв батька», «Авто-лейаут», «Відступи», «Заливка», «Обведення й радіус», «Текст». Розділ зʼявляється лише коли стосується елемента.
- Поля крутяться як у Figma: Enter застосовує, Esc скасовує, ↑/↓ — ±1, Shift — ±10, підпис поля можна тягнути вліво-вправо. Пари (↔, ↕) пишуть обидві сторони; коли сторони різні, поле показує «Різні».
- Токени: чип з імʼям, бурштинове поле для значень повз дизайн-систему, кнопка «до ДС», кнопка «N поза ДС» веде по таких полях по колу.
- В оверлеї: ярлик з назвою на наведеному елементі, «W × H» під вибраним, відстані за утримуваним Alt (до наведеного, до батька або до сусіда за Alt+←/→/↑).
- Клавіші інспектора: Esc — батько (на корені зняти вибір, без вибору вимкнути), Enter — дочірній, ← → — сусід. Працюють і з фокусом в оболонці.

### Видалено
- «Лінійка» (вкладка, клавіша M, режим оверлея). Відстані — Alt.
- Рядок-підказка з клавішами в панелі інспектора: клавіші названо в підказці кнопки інспектора й у довідці «?».
```

- [ ] **Step 2: `package.json`** → `"version": "0.29.0"`. Перевірити, чи тест версії/`skill-version` не потребує інших файлів: `node --test tests/*.test.mjs 2>&1 | tail -5` і `python3 -B -m unittest discover -s tests -q 2>&1 | tail -5` (python-тести, що читають `package.json`/CHANGELOG, мусять лишитись зеленими).

- [ ] **Step 3: Повний релізний прогін** — юніти, python, потім кожен live-файл ПО ОДНОМУ (перелік з T4 Step 6 + решта `tests/live/*.test.mjs`); порівняти число `# pass` юнітів із Step 1 T1 (мусить вирости на нові тести, жоден старий не зникнути без пояснення).

- [ ] **Step 4: Перевірка проти живого канвасу** (контролер; порт 8765 — НЕ вбивати процеси за шаблоном; рестарт — `start.command`). Відкрити живий канвас, увімкнути інспектор на справжній задачі й пройти руками: клік → панель; ↑ у полі; скраб; Alt; Esc/Enter/← →; «до ДС»; «N поза ДС»; «Надіслати Клоду». Окремо: `report()` на важкій сторінці ≲ 10 мс (скраб і утримання ↑ не смикають панель), клавіатурний шлях Alt+←/→ у Windows-браузері (Alt+← = «назад» — `preventDefault` має спрацювати), PWA-вікно.

- [ ] **Step 5: Commit**

```bash
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "release: 0.29.0 — інспектор як у Figma" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- CHANGELOG.md package.json
```

---

## Self-review (спека ↔ план)

**Покриття спеки.**
- Р1 (одна панель, без вкладок): T1 `panelHTML`, T2 `inspectHTML`, прибрано `insptab`.
- Р2 (дані й пакет не змінюються): `tuneSet` лише розширено параметром `save`; формат пакета не чіпали.
- Р3 (без підписів): тест Р3 в T1, `inspectHTML` T2; `inspCascadeHint` та ін. прибрано T3.
- Р4 (лише «Макет»): не змінювалось (`shellMode`); власна панель оверлея лишається на `reportHTML` (T3 лише прибирає `measureHTML`).
- Панель: шлях, елемент, лічильник, розділи, підвал — T1+T2. «Різні», чип за вироком, змінене поле — T1/T2. Правки (пари, матриця, напрям, «+», скраб, rAF) — T2.
- Оверлей: ярлик, розмір, Alt, відстані через `between`, blur — T3. Кольори `STYLE` — T3.
- Клавіші (I, Esc, Enter, ← →, Alt, Alt+←/→/↑), пересилання з оболонки, виняток `askUp()` — T3; виняток ⌥M зберігається (`e.key === 'Alt'` не споживає наступні клавіші; `e.altKey && !I`).
- Прибирається з коду: вкладки/підказки/клавіші `shell-inspect.js`, `measureHTML`, M/режим/`_tip`, ключі i18n, застарілі коментарі — T2/T3 (коментарі про вкладку «Тюнер» у `css-guards`/CSS: прибрати під час редагування тих самих блоків; перелічено в T2 Step 11 і T3 Step 5).
- Перевірка: юніт `insp-panel` — T1; юніт оверлея (`nextPin`, `altTarget`, структурні охоронці) — T3; сценарії 1–8 — T4; мутації — у кожному завданні.

**Місця, де код суперечить спеці** — розділ «Відхилення» вгорі (8 пунктів). Вимагають уваги ревʼюера: пункти 3 (`.insp-spec` лишається в `STYLE`), 4 (три довгі властивості замість `border`), 5 (немає селектора в `title`), 7 (кольори ДС за імʼям).

**Не покрито задачею (свідомо).** Видалення мертвого `tunable: true` у `reportHTML`/`NUMERIC` (його тепер не викликає жоден документ) і файла `inspector-measure.js` (`measure()` без споживача; `between` живе) — окремий чистий-вгору крок після релізу, щоб не змішувати з функцією. Реєстр палітри ⌘K не отримав окремого рядка клавіш: підказка названа в довідці `?` і в `title` кнопки острівця.

**Типи й імена.** `buildModel` (T2) повертає рівно ті поля, які читає `panelHTML` (T1) — контракт у розділі «Контракти». `tuneWrite(list, opts)`, `tuneSet(prop, value, snap, opts)`, `inspCommit`, `inspStep`, `inspScrubApply` — визначені в T2 і не змінюють імен у T3/T4. Оверлей: `handleKey`, `setAlt`, `yieldEsc`, `_setPin`, `_draw`, `_pair` — визначені в T3 і вживаються в `app.js` (T3) лише під цими іменами.
