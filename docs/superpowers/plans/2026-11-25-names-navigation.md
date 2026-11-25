# 0.40 «Імена й навігація»: план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** повні назви сторінок у лівій панелі (ширина, що тягнеться, і підказка), місце в адресі з Назад / Вперед / Оновити, пошук ⌘F по макету й перемикач «Макет / Огляд», що не стрибає.

**Architecture:** чисті моделі (`app/location-model.js`, `app/find-model.js`, `app/panel-width.js`) + два невеликі DOM-модулі без стану застосунку (`app/tooltip.js`, `app/nav.js` з інʼєкцією `window`) + плашка пошуку (`app/find-bar.js`) + проводка в `app/app.js`, `app/shell-bar.js`, `app/bar-model.js`, `app/styles.css`. Адреса пишеться з одного місця (`nav.sync()` наприкінці `render()` / `enterHome`), а всі переходи «веде в місце» проходять через одну `goTo(loc)`, що ставить стан і робить РІВНО ОДИН `render()`.

**Tech Stack:** vanilla JS ES modules, `node --test`, Playwright (живі тести), CSS Custom Highlight API, History API.

**Спека:** `docs/superpowers/specs/2026-11-25-names-navigation-design.md` (погоджено 25.11.2026). Прототипи (ігноруються git, лежать у `.superpowers/proto/` основного worktree `deai-canvas`): `full-names.html` (лише варіант А) і `nav-find.html`. База: main 14b77d0 (v0.39.1), worktree `deai-canvas-040`, гілка `feat/names-nav`. Реліз — 0.40.0.

**Рівень строгості:** середній — один ревʼюер на задачу, фінальний ревʼю контролера. **Ризикованіші:** T4 і T5 (історія, `popstate`, відновлення на старті, гонки `render()`), T8 (немає доведеної причини — спершу вимір), T7 (клавіші в двох документах). Один виконавець за раз; живі тести — послідовно (спільний замок).

**Спільні правила для кожної задачі:**
- `python3 -B` для Python; жодного `git add -A`; коміти лише так (нові файли спершу `git add -- <шлях>`):
  `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>`
- Не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`. Нічого не пушити.
- Жива перевірка — по одному файлу, під спільним замком (кожна команда в один рядок):
  `until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME="$(mktemp -d)" node --test --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo "rc=$rc"`
- Ніколи не чіпати порти 8765 і 4317, справжній `~/.deai`, `~/Liga`, `~/deai-work`, `~/.gitconfig`. Живі тести стартують свій сервер на власному порту.
- Публічний репозиторій: у коді, тестах і документах — жодних справжніх імен, внутрішніх хостів, ключів, абсолютних локальних шляхів (писати «worktree deai-canvas-040»).
- Нових підписів у інтерфейсі, про які не просили, не додавати. Усі видимі й `aria-` рядки — через `app/i18n.js` в обох мовах (`UK` і `EN`; `tests/i18n.test.mjs`, `i18n-keys`, `i18n-literals` стережуть). Кирилиця в `app/**/*.js` поза `i18n.js` заборонена.
- Кольори в `styles.css` лише токенами (`tests/css-guards.test.mjs`); висоти — з сітки (`--h-sm` = 28px).
- Номери рядків `app/app.js` нижче — орієнтири з v0.39.1; шукати за ЯКОРЕМ (текстом), а не за числом.

---

## Карта файлів

| Файл | Задача | Відповідальність |
|---|---|---|
| `app/tooltip.js` (нове) | T1 | спільна підказка: плашка в `body`, затримка, «чи обрізано», позиція |
| `app/panel-width.js` (нове) | T2 | чисті межі ширини панелі, «потрібна ширина», розбір збереженого |
| `app/panel-resize.js` (нове) | T2 | ручка на краї панелі: вказівник, клавіатура, збереження |
| `app/location-model.js` (нове) | T3 | `parseLocation` / `formatLocation` / `sameLocation` / `hasPlace` |
| `app/nav.js` (нове) | T4–T5 | запис адреси в історію, індекс запису, `popstate`, відмова охоронця |
| `app/find-model.js` (нове) | T6 | чисті збіги тексту без урахування регістру, ліміт |
| `app/find-bar.js` (нове) | T7 | плашка пошуку, підсвітка у вікні рамки |
| `app/bar-model.js`, `app/shell-bar.js` | T5, T8 | елемент `nav` у зоні 1; обгортка зони 2 (T8) |
| `app/app.js` | T1, T2, T4, T5, T7 | монтування, `curLoc`, `goTo`, старт, ключі, проводка |
| `app/styles.css` | T1, T2, T5, T7, T8 | підказка, ручка, кнопки навігації, плашка пошуку, центр |
| `app/i18n.js` | T2, T5, T7 | рядки (uk + en) |
| `docs/agents/links.md` (нове) | T9 | тема довідки агента про формат адреси |
| `tests/*.test.mjs`, `tests/live/*.test.mjs`, `tests/test_agent_links_topic.py` | усі | див. задачі |
| `CHANGELOG.md`, `package.json` | T10 | реліз (контролер) |

Нові живі файли й бази портів (кожна база володіє смугою у 100 портів; `tests/live-ports.test.mjs` стереже, що бази не збігаються; вільне вище за 49000): `names-tooltip` 50000, `panel-resize` 51000, `nav-history` 52000, `find` 53000, `bar-centre` 54000.

---

### Task 1: `app/tooltip.js` і підказки на обрізаних назвах

**Files:**
- Create: `app/tooltip.js`, `tests/tooltip.test.mjs`, `tests/live/names-tooltip.test.mjs`
- Modify: `app/styles.css` (кінець розділу «панель»; після правила `.row-name`), `app/app.js` (монтування, біля `applyViewport();` перед `loadTune()` наприкінці файла)

Підказка — одна плашка `#dc-tip` у `body`. Цілі: будь-який елемент із `data-tip` (текст завжди) і `.row-name` (текст лише коли обрізано). Через 500 мс; ховається на `pointerout`, прокрутці, клавіші, `pointerdown`, `dragstart`, колесі, події `dc-tip-hide` (її шле ручка панелі в T2). `title` на рядки НЕ додаємо.

- [ ] **Step 1: Падаючий юніт-тест** — `tests/tooltip.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { isTruncated, placeTip, tipText } from "../app/tooltip.js";

const el = (o = {}) => ({
  scrollWidth: 0, clientWidth: 0, textContent: "", attrs: {}, classes: [],
  getAttribute(k) { return this.attrs[k] ?? null; },
  matches(sel) { return sel === ".row-name" && this.classes.includes("row-name"); },
  ...o,
});

test("isTruncated: лише коли вміст ширший за видиму частину", () => {
  assert.equal(isTruncated(el({ scrollWidth: 300, clientWidth: 200 })), true);
  assert.equal(isTruncated(el({ scrollWidth: 200, clientWidth: 200 })), false);
  assert.equal(isTruncated(null), false);
});

test("tipText: data-tip — завжди; .row-name — лише обрізана; решта — порожньо", () => {
  assert.equal(tipText(el({ attrs: { "data-tip": "Назад ⌘[" } })), "Назад ⌘[");
  const row = el({ classes: ["row-name"], textContent: "  Довга назва  ", scrollWidth: 300, clientWidth: 100 });
  assert.equal(tipText(row), "Довга назва");
  assert.equal(tipText(el({ classes: ["row-name"], textContent: "Коротка", scrollWidth: 50, clientWidth: 100 })), "");
  assert.equal(tipText(el({ textContent: "x", scrollWidth: 500, clientWidth: 10 })), "", "чужий елемент без data-tip");
  assert.equal(tipText(null), "");
});

test("placeTip: під елементом; притиснута до меж; біля низу — над елементом", () => {
  const base = { w: 200, h: 30, vw: 1000, vh: 800 };
  assert.deepEqual(placeTip({ ...base, rect: { left: 10, top: 20, bottom: 40 } }), { left: 10, top: 46 });
  assert.equal(placeTip({ ...base, rect: { left: 950, top: 20, bottom: 40 } }).left, 792, "правий край: vw - w - 8");
  assert.equal(placeTip({ ...base, rect: { left: -50, top: 20, bottom: 40 } }).left, 8, "лівий край: відступ 8");
  assert.equal(placeTip({ ...base, rect: { left: 10, top: 770, bottom: 790 } }).top, 734, "над елементом: top - 6 - h");
});
```

- [ ] **Step 2: Побачити падіння**

Run: `node --test tests/tooltip.test.mjs`
Expected: FAIL, `Cannot find module '../app/tooltip.js'`.

- [ ] **Step 3: `app/tooltip.js`**

```js
/**
 * Спільна підказка Deai (0.40): одна плашка в `body`, показ через 500 мс над елементом із `data-tip` або над `.row-name`,
 * причому назву рядка — ЛИШЕ коли її обрізано трикрапкою. Чисті функції (`isTruncated`, `tipText`, `placeTip`) окремо від
 * DOM-монтування, щоб юніт-тест не потребував браузера.
 * ⛔ Жодного `title` на тих самих елементах: дві підказки одночасно.
 */
export const TIP_DELAY = 500;
export const TIP_SELECTOR = "[data-tip],.row-name";

/** Вміст ширший за видиму частину (`text-overflow: ellipsis` спрацював). */
export function isTruncated(el) {
  return !!el && el.scrollWidth > el.clientWidth;
}

/** Текст підказки для елемента або `""`, коли показувати нічого. */
export function tipText(el) {
  if (!el) return "";
  const v = el.getAttribute("data-tip");
  if (v) return v;
  return el.matches(".row-name") && isTruncated(el) ? (el.textContent || "").trim() : "";
}

/** Позиція плашки: під елементом, притиснута до меж вікна; біля низу — над елементом. */
export function placeTip({ rect, w, h, vw, vh, gap = 6, pad = 8 }) {
  const left = Math.max(pad, Math.min(rect.left, vw - w - pad));
  let top = rect.bottom + gap;
  if (top + h > vh - pad) top = Math.max(pad, rect.top - gap - h);
  return { left, top };
}

/** Змонтувати плашку й слухачі на документі. Повертає `{ hide, el }`. */
export function mountTooltip(doc = document, { delay = TIP_DELAY } = {}) {
  const win = doc.defaultView;
  const tip = doc.createElement("div");
  tip.id = "dc-tip";
  tip.setAttribute("role", "tooltip");
  doc.body.appendChild(tip);
  let cur = null, timer = 0, watch = 0;
  const hide = () => { clearTimeout(timer); clearInterval(watch); cur = null; tip.classList.remove("on"); };
  const show = (el) => {
    const text = tipText(el);
    if (!text || !el.isConnected) return;
    tip.textContent = text;
    tip.classList.add("on");   // спершу робимо видимою — щоб виміряти, потім ставимо
    const { left, top } = placeTip({
      rect: el.getBoundingClientRect(), w: tip.offsetWidth, h: tip.offsetHeight, vw: win.innerWidth, vh: win.innerHeight,
    });
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    /* Фонова перемальовка (опит, подія агента) могла прибрати вузол під плашкою — вона б висіла до першого руху вказівника. */
    watch = setInterval(() => { if (!cur || !cur.isConnected) hide(); }, 400);
  };
  const arm = (el) => { hide(); cur = el; timer = setTimeout(() => show(el), delay); };
  doc.addEventListener("pointerover", (ev) => {
    const el = ev.target.closest?.(TIP_SELECTOR);
    if (!el) { if (cur) hide(); return; }
    if (el !== cur) arm(el);
  }, true);
  doc.addEventListener("pointerout", (ev) => { if (cur && !cur.contains(ev.relatedTarget)) hide(); }, true);
  /* З клавіатури: рядок дерева у фокусі (лише `:focus-visible`) показує повну назву так само. */
  doc.addEventListener("focusin", (ev) => {
    const name = ev.target.closest?.(".row")?.querySelector(".row-name");
    if (name && ev.target.matches?.(":focus-visible")) arm(name);
  }, true);
  for (const type of ["pointerdown", "keydown", "dragstart", "wheel", "scroll"]) doc.addEventListener(type, hide, true);
  win.addEventListener("dc-tip-hide", hide);
  win.addEventListener("blur", hide);
  return { hide, el: tip };
}
```

- [ ] **Step 4: Юніт зелений**

Run: `node --test tests/tooltip.test.mjs`
Expected: PASS (3 tests).

- [ ] **Step 5: CSS** — у `app/styles.css` одразу після правила `.row-name{…}` додати:

```css
/* Підказка (0.40, `app/tooltip.js`): темна плашка, лише `opacity` — без руху. Не ловить вказівник. */
#dc-tip{position:fixed;top:0;left:0;z-index:var(--z-toast);max-width:420px;padding:5px 8px;
  background:var(--s0);color:var(--hi);border:1px solid var(--s4);border-radius:var(--r-sm);
  font-size:12px;line-height:1.35;box-shadow:0 6px 20px rgba(0,0,0,.35);
  opacity:0;pointer-events:none;transition:opacity 120ms var(--ease);overflow-wrap:anywhere}
#dc-tip.on{opacity:1}
```

(Тінь — у тій самій формі `rgba(0,0,0,.35)`, що вже стоїть у файлі біля тостів і меню.)

- [ ] **Step 6: Монтування** — у `app/app.js` додати імпорт поруч з іншими (після `import { readFlow, … } from './flow-model.js';`):

```js
import { mountTooltip } from './tooltip.js';
```

і безпосередньо перед рядком `applyViewport();` (наприкінці файла, коментар «Ширина зі сховища мусить лягти у стиль ДО першого рендера») додати:

```js
/* Підказки (0.40): одна плашка на весь застосунок; ховається, коли ручка панелі починає перетягування (подія `dc-tip-hide`). */
mountTooltip(document);
```

- [ ] **Step 7: Падаючий живий тест** — `tests/live/names-tooltip.test.mjs`:

```js
/**
 * Підказки на обрізаних назвах (0.40): довга назва в панелі — підказка з повним текстом через ~0,5 с; коротка — нічого;
 * `title` на рядках немає (дві підказки одночасно); pointerdown і з клавіатури теж.
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 50000;
const VIEW = { width: 1440, height: 900 };
const LONG = "Дуже довга назва сторінки, яка точно не влізе в панель шириною двісті сорок шість пікселів";
const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

export function longNames(dir) {
  writeFileSync(path.join(dir, "iterations", "it1", "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: LONG, published: true }, { id: "poshuk", name: "Пошук", published: true }],
  }));
}

async function boot(t, off) {
  const { dir } = taskFixture({ html });
  longNames(dir);
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  await page.waitForSelector('[data-page="holovna"] .row-name');
  return page;
}
const tipOn = (page) => page.evaluate(() => document.getElementById("dc-tip")?.classList.contains("on") ?? false);
const tipTxt = (page) => page.evaluate(() => document.getElementById("dc-tip")?.textContent ?? "");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("довга назва: підказка через затримку з повним текстом; коротка — без підказки; title на рядку нема", async (t) => {
  const page = await boot(t, 0);
  assert.equal(await page.getAttribute('[data-page="holovna"]', "title"), null, "на рядку нема title");
  await page.hover('[data-page="holovna"] .row-name');
  await sleep(200);
  assert.equal(await tipOn(page), false, "раніше за 500 мс підказки нема");
  await page.waitForFunction(() => document.getElementById("dc-tip")?.classList.contains("on"), null, { timeout: 3000 });
  assert.equal(await tipTxt(page), LONG);
  await page.hover('[data-page="poshuk"] .row-name');
  await sleep(900);
  assert.equal(await tipOn(page), false, "коротка назва не обрізана — підказки нема");
});

test("pointerdown ховає підказку; з клавіатури (focus-visible) вона теж зʼявляється", async (t) => {
  const page = await boot(t, 100);
  await page.hover('[data-page="holovna"] .row-name');
  await page.waitForFunction(() => document.getElementById("dc-tip")?.classList.contains("on"), null, { timeout: 3000 });
  await page.mouse.down();
  assert.equal(await tipOn(page), false, "pointerdown ховає");
  await page.mouse.up();
  await page.mouse.move(700, 600);
  await page.keyboard.press("Shift");   // остання взаємодія — клавіатура: focus() дає :focus-visible
  await page.locator('[data-page="holovna"]').focus();
  await page.waitForFunction(() => document.getElementById("dc-tip")?.classList.contains("on"), null, { timeout: 3000 });
  assert.equal(await tipTxt(page), LONG);
});
```

(Якщо рядок дерева не фокусований напряму — подивитись `tabindex` у `rowHTML` (`app/shell-panel.js`) і сфокусувати елемент, що його несе; перевірку лишити.)

- [ ] **Step 8: Живий тест зелений**

Run: `until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME="$(mktemp -d)" node --test --import ./tests/live/_env.mjs tests/live/names-tooltip.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo "rc=$rc"`
Expected: `rc=0`.

- [ ] **Step 9: Звіряння охоронців**

Run: `node --test tests/i18n-literals.test.mjs tests/css-guards.test.mjs tests/js-parses.test.mjs tests/live-ports.test.mjs`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add -- app/tooltip.js tests/tooltip.test.mjs tests/live/names-tooltip.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.40): спільна підказка app/tooltip.js, повна назва на обрізаних рядках дерева" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/tooltip.js app/styles.css app/app.js tests/tooltip.test.mjs tests/live/names-tooltip.test.mjs
```

---

### Task 2: ручка ширини лівої панелі

**Files:**
- Create: `app/panel-width.js`, `app/panel-resize.js`, `tests/panel-width.test.mjs`, `tests/names-css.test.mjs`, `tests/live/panel-resize.test.mjs`
- Modify: `app/styles.css` (після `.panel-rail{…}`), `app/app.js` (імпорт і монтування), `app/i18n.js` (ключ `panelResize`, uk + en)

Ручка — ОКРЕМИЙ вузол `#panel-resize` у `body` (не всередині `.panel`: `renderPanel()` переписує `innerHTML` панелі, і перетягування з захопленим вказівником обірвалось би). Спека: смуга 8 px, `col-resize`, лінія `--sel` на ховері й під час перетягування; мінімум 200, максимум `min(520, ширина вікна − відкрита права панель − 420)`; подвійний клік / Enter — під найдовшу назву й назад до 246; ← / → крок 16; `localStorage` `dc-panel-w`; без `transition` на час перетягування; після зміни в «Огляді» — `fitAll()` якщо `!userMoved`. Типової ширини НЕ записуємо в `--panel-w` (поки людина нічого не тягла, CSS-типове 246 і поведінка вузьких вікон — як є).

- [ ] **Step 1: Падаючий юніт** — `tests/panel-width.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { KEY_STEP, PANEL_W_DEFAULT, PANEL_W_MAX, PANEL_W_MIN, clampPanelW, fitPanelW, panelWBounds, parseStoredW } from "../app/panel-width.js";

test("межі: 200..520 на широкому вікні; сцена ≥ 420 з правою панеллю", () => {
  assert.deepEqual(panelWBounds({ vw: 1600, rightW: 0 }), { min: 200, max: 520 });
  assert.deepEqual(panelWBounds({ vw: 1024, rightW: 308 }), { min: 200, max: 296 }, "1024 − 308 − 420");
  assert.deepEqual(panelWBounds({ vw: 1024, rightW: 0 }), { min: 200, max: 520 }, "1024 − 420 = 604 > 520");
});

test("вузьке вікно: максимум не опускається нижче мінімуму (панель лишається придатною)", () => {
  assert.deepEqual(panelWBounds({ vw: 320, rightW: 0 }), { min: 200, max: 200 });
  assert.equal(clampPanelW(500, { vw: 320, rightW: 0 }), 200);
});

test("clampPanelW: притискає й округлює", () => {
  assert.equal(clampPanelW(100, { vw: 1600, rightW: 0 }), PANEL_W_MIN);
  assert.equal(clampPanelW(9999, { vw: 1600, rightW: 0 }), PANEL_W_MAX);
  assert.equal(clampPanelW(300.4, { vw: 1600, rightW: 0 }), 300);
});

test("fitPanelW: якщо є обрізані назви — ширина росте на найбільше переповнення; інакше повертається до 246", () => {
  const b = { min: 200, max: 520 };
  assert.equal(fitPanelW({ cur: 246, overflows: [0, 90, 40], bounds: b }), 246 + 90 + 2);
  assert.equal(fitPanelW({ cur: 334, overflows: [0, 0], bounds: b }), PANEL_W_DEFAULT, "усе влізло — назад до типової");
  assert.equal(fitPanelW({ cur: 246, overflows: [], bounds: b }), PANEL_W_DEFAULT);
});

test("fitPanelW: упертись у максимум — наступний виклик теж повертає типову (не застрягає)", () => {
  const b = { min: 200, max: 300 };
  assert.equal(fitPanelW({ cur: 246, overflows: [400], bounds: b }), 300);
  assert.equal(fitPanelW({ cur: 300, overflows: [400], bounds: b }), PANEL_W_DEFAULT);
});

test("fitPanelW: типова 246 сама притискається до вузьких меж", () => {
  assert.equal(fitPanelW({ cur: 300, overflows: [0], bounds: { min: 200, max: 220 } }), 220);
});

test("parseStoredW: лише ціле в межах 200..520", () => {
  assert.equal(parseStoredW("320"), 320);
  for (const bad of [null, "", "abc", "199", "521", "300.5", "NaN"]) assert.equal(parseStoredW(bad), null, String(bad));
});

test("крок клавіші — 16", () => { assert.equal(KEY_STEP, 16); });
```

- [ ] **Step 2: Побачити падіння** — `node --test tests/panel-width.test.mjs` → FAIL (нема модуля).

- [ ] **Step 3: `app/panel-width.js`**

```js
/**
 * Ширина лівої панелі (0.40): чисті межі й вибір «під найдовшу назву». Без DOM — `panel-resize.js` читає й пише
 * сторінку, тут лише арифметика.
 */
export const PANEL_W_DEFAULT = 246;
export const PANEL_W_MIN = 200;
export const PANEL_W_MAX = 520;
/** Інваріант оболонки (коментар біля `body.with-insp` у `styles.css`): сцена не вужча за 420 px. */
export const STAGE_MIN = 420;
export const KEY_STEP = 16;

/** `{min, max}` для вікна завширшки `vw` і відкритої правої панелі завширшки `rightW` (0, коли її нема). */
export function panelWBounds({ vw, rightW = 0 }) {
  const max = Math.max(PANEL_W_MIN, Math.min(PANEL_W_MAX, vw - rightW - STAGE_MIN));
  return { min: PANEL_W_MIN, max };
}

export function clampPanelW(want, ctx) {
  const { min, max } = panelWBounds(ctx);
  return Math.round(Math.min(max, Math.max(min, want)));
}

/**
 * Куди ставити ширину подвійним кліком: `overflows` — по кожній назві `scrollWidth − clientWidth` (0, коли влізла).
 * Є що показувати — додаємо найбільше переповнення (+2 px на округлення); вже впираємось у межу чи нічого не обрізано —
 * повертаємо типову (притиснуту до меж).
 */
export function fitPanelW({ cur, overflows, bounds }) {
  const extra = Math.max(0, ...overflows);
  const pin = (w) => Math.round(Math.min(bounds.max, Math.max(bounds.min, w)));
  if (extra > 0) {
    const target = pin(cur + extra + 2);
    if (target > cur) return target;
  }
  return pin(PANEL_W_DEFAULT);
}

/** Збережене значення → ціле в межах, інакше `null`. */
export function parseStoredW(raw) {
  if (typeof raw !== "string" || !/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return n >= PANEL_W_MIN && n <= PANEL_W_MAX ? n : null;
}
```

- [ ] **Step 4: Юніт зелений** — `node --test tests/panel-width.test.mjs` → PASS (8 tests).

- [ ] **Step 5: i18n** — у `app/i18n.js` додати в кінець `UK` (перед закривальним `};` блока `const UK`) і в кінець `EN` (перед `};` блока `const EN`):

```js
  /* 0.40 «Імена й навігація»: ручка ширини панелі (лише `aria-label`, видимого підпису нема). */
  panelResize: 'Ширина панелі',
```
```js
  /* 0.40: panel width handle (`aria-label` only). */
  panelResize: 'Panel width',
```

- [ ] **Step 6: `app/panel-resize.js`**

```js
/**
 * Ручка ширини лівої панелі (0.40). Окремий вузол `#panel-resize` у `body`, а не дитина `.panel`: `renderPanel()` переписує
 * `innerHTML` панелі, і перетягування із захопленим вказівником обірвалось би на першій же перемальовці.
 * Значення: `--panel-w` на `<html>` (лише в оболонці застосунку; превʼю цього модуля не вантажить), збереження — `dc-panel-w`.
 * Поки людина нічого не обрала, змінну НЕ пишемо — діє типова 246 із `:root` і всі нинішні поведінки вузьких вікон.
 */
import { t } from "./i18n.js";
import { KEY_STEP, PANEL_W_DEFAULT, clampPanelW, fitPanelW, panelWBounds, parseStoredW } from "./panel-width.js";

const KEY = "dc-panel-w";

/**
 * @param {object} o
 * @param {() => number} o.rightW   ширина відкритої правої панелі (0, коли нема)
 * @param {() => number[]} o.overflows   по кожній видимій назві `scrollWidth − clientWidth`
 * @param {() => void} o.onResize   після завершеної зміни (у «Огляді» — `fitAll()`, якщо камеру не рухали)
 */
export function mountPanelResize({ doc = document, rightW = () => 0, overflows = () => [], onResize = () => {} }) {
  const win = doc.defaultView;
  const root = doc.documentElement;
  const read = () => { try { return parseStoredW(win.localStorage.getItem(KEY)); } catch (e) { return null; } };
  const write = (w) => { try { win.localStorage.setItem(KEY, String(w)); } catch (e) { /* без сховища ширина живе до перезавантаження */ } };
  let pref = read();   // що людина обрала; на екрані — притиснуте до меж, які залежать від вікна
  const ctx = () => ({ vw: win.innerWidth, rightW: rightW() });
  const base = () => clampPanelW(pref ?? PANEL_W_DEFAULT, ctx());

  const handle = doc.createElement("div");
  handle.id = "panel-resize";
  handle.setAttribute("role", "separator");
  handle.setAttribute("aria-orientation", "vertical");
  handle.setAttribute("aria-label", t("panelResize"));
  handle.tabIndex = 0;
  doc.body.appendChild(handle);

  function paint() {
    const b = panelWBounds(ctx());
    if (pref == null) root.style.removeProperty("--panel-w");
    else root.style.setProperty("--panel-w", `${clampPanelW(pref, ctx())}px`);
    handle.setAttribute("aria-valuemin", String(b.min));
    handle.setAttribute("aria-valuemax", String(b.max));
    handle.setAttribute("aria-valuenow", String(base()));
  }
  function set(w, { save = true } = {}) {
    pref = clampPanelW(w, ctx());
    if (save) write(pref);
    paint();
  }
  function fit() {
    set(fitPanelW({ cur: base(), overflows: overflows(), bounds: panelWBounds(ctx()) }));
    onResize();
  }

  let drag = null;
  handle.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    handle.setPointerCapture(ev.pointerId);
    drag = { x: ev.clientX, w: base() };
    doc.body.classList.add("panel-dragging");
    win.dispatchEvent(new Event("dc-tip-hide"));
  });
  handle.addEventListener("pointermove", (ev) => { if (drag) set(drag.w + ev.clientX - drag.x, { save: false }); });
  const end = () => {
    if (!drag) return;
    drag = null;
    doc.body.classList.remove("panel-dragging");
    if (pref != null) write(pref);
    onResize();
  };
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", end);
  handle.addEventListener("dblclick", fit);
  handle.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      ev.preventDefault();
      set(base() + (ev.key === "ArrowRight" ? KEY_STEP : -KEY_STEP));
      onResize();
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      fit();
    }
  });

  /* Вікно стало вужчим чи відкрилась права панель — межі змінились: притискаємо вибір (сам вибір лишається в сховищі). */
  win.addEventListener("resize", paint);
  new win.MutationObserver(paint).observe(doc.body, { attributes: true, attributeFilter: ["class"] });
  paint();
  return { handle, set, fit };
}
```

- [ ] **Step 7: CSS** — у `app/styles.css` одразу після правила `.panel-rail{…}` додати:

```css
/* Ручка ширини панелі (0.40, `app/panel-resize.js`): над `.panel-fill`/`.panel-rail` (ті лишаються сигналами згортання). */
#panel-resize{position:fixed;top:var(--h-top);bottom:0;left:calc(var(--panel-w) - 4px);width:8px;
  cursor:col-resize;z-index:calc(var(--z-panel) + 1);touch-action:none}
#panel-resize::after{content:"";position:absolute;top:0;bottom:0;left:3px;width:2px;background:transparent;
  transition:background var(--dur) var(--ease)}
#panel-resize:hover::after,#panel-resize:focus-visible::after,body.panel-dragging #panel-resize::after{background:var(--sel)}
#panel-resize:focus-visible{outline:none}
body.panel-dragging{user-select:none}
body.panel-dragging .panel{transition:none}
body:not(.with-panel) #panel-resize,body.panel-collapsed #panel-resize,body.home-open #panel-resize,
html.cv-clean #panel-resize{display:none}
```

- [ ] **Step 8: Падаючі CSS-охоронці** — `tests/names-css.test.mjs`:

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");

test("0.40: .row-name лишається з трикрапкою (довга назва обрізається, повна — у підказці)", () => {
  assert.match(css, /\.row-name\{[^}]*overflow:hidden[^}]*text-overflow:ellipsis/);
});
test("0.40: ручка панелі — col-resize, над .panel", () => {
  assert.match(css, /#panel-resize\{[^}]*cursor:col-resize/);
  assert.match(css, /#panel-resize\{[^}]*z-index:calc\(var\(--z-panel\) \+ 1\)/);
});
test("0.40: під час перетягування панель без transition", () => {
  assert.match(css, /body\.panel-dragging \.panel\{[^}]*transition:none/);
});
test("0.40: ручка ховається в рейці, на екрані «Задачі» і в чистому перегляді", () => {
  for (const sel of ["body:not(.with-panel) #panel-resize", "body.panel-collapsed #panel-resize", "body.home-open #panel-resize", "html.cv-clean #panel-resize"]) {
    assert.ok(css.includes(sel), sel);
  }
});
```

Run: `node --test tests/names-css.test.mjs` → PASS (CSS уже додано в Step 7; охоронці лишаються назавжди — мутація: прибрати `transition:none` → червоне).

- [ ] **Step 9: Проводка в `app/app.js`** — імпорт:

```js
import { mountPanelResize } from './panel-resize.js';
```

і одразу після `mountTooltip(document);` (з T1):

```js
/* Ручка ширини лівої панелі (0.40). `onResize`: подія `resize` вікна тут не приходить, тож «Огляд» вписуємо сам — якщо камеру не рухали. */
mountPanelResize({
  rightW: () => (['with-insp', 'with-cmt', 'with-mod', 'with-hist'].some((c) => document.body.classList.contains(c))
    ? parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--insp-w')) || 308 : 0),
  overflows: () => [...document.querySelectorAll('#pages-panel .row-name')].map((n) => n.scrollWidth - n.clientWidth),
  onResize: () => { if (mode === 'canvas' && !userMoved && !homeOpen) fitAll(); },
});
```

- [ ] **Step 10: Падаючий живий тест** — `tests/live/panel-resize.test.mjs`:

```js
/**
 * Ширина лівої панелі (0.40): перетягування краю, збереження після перезавантаження, подвійний клік під найдовшу назву й назад,
 * клавіші ← →, межа на вузькому вікні, «Огляд» перевписується. Підказки — `names-tooltip.test.mjs`.
 */
import assert from "node:assert/strict";
import { writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 51000;
const LONG = "Дуже довга назва сторінки, яка точно не влізе в панель шириною двісті сорок шість пікселів";
const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(t, off, viewport = { width: 1440, height: 900 }) {
  const { dir } = taskFixture({ html });
  writeFileSync(path.join(dir, "iterations", "it1", "pages.json"), JSON.stringify({
    pages: [{ id: "holovna", name: LONG, published: true }, { id: "poshuk", name: "Пошук", published: true }],
  }));
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  await page.waitForSelector("#panel-resize");
  await page.waitForSelector('[data-page="holovna"] .row-name');
  return page;
}
const panelW = (page) => page.evaluate(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width));
const stageLeft = (page) => page.evaluate(() => Math.round(document.getElementById("stage").getBoundingClientRect().left));
const drag = async (page, dx) => {
  const b = await (await page.$("#panel-resize")).boundingBox();
  const x = b.x + b.width / 2, y = b.y + 200;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y, { steps: 5 });
  await page.mouse.up();
};
const settled = (page) => page.waitForFunction(() => !document.body.classList.contains("panel-dragging"));

test("перетягування змінює ширину, сцена слідом; ширина переживає перезавантаження; під час жесту transition вимкнено", async (t) => {
  const page = await boot(t, 0);
  assert.equal(await panelW(page), 246);
  const b = await (await page.$("#panel-resize")).boundingBox();
  await page.mouse.move(b.x + 4, b.y + 200);
  await page.mouse.down();
  await page.mouse.move(b.x + 4 + 84, b.y + 200, { steps: 4 });
  assert.equal(await page.evaluate(() => getComputedStyle(document.getElementById("pages-panel")).transitionProperty), "none", "transition вимкнено під час перетягування");
  await page.mouse.up();
  await settled(page);
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) === 330);
  assert.equal(await stageLeft(page), 330, "сцена зсунулась разом із панеллю");
  assert.equal(await page.evaluate(() => localStorage.getItem("dc-panel-w")), "330");
  await page.reload();
  await page.waitForSelector("#panel-resize");
  assert.equal(await panelW(page), 330, "ширина пережила перезавантаження");
});

test("подвійний клік: під найдовшу назву (повна влізла) й назад до 246; Enter — те саме", async (t) => {
  const page = await boot(t, 100);
  const cut = () => page.$eval('[data-page="holovna"] .row-name', (n) => n.scrollWidth - n.clientWidth);
  assert.ok((await cut()) > 0, "на 246 назву обрізано");
  await page.dblclick("#panel-resize");
  await page.waitForFunction(() => { const n = document.querySelector('[data-page="holovna"] .row-name'); return n.scrollWidth <= n.clientWidth; });
  const w = await panelW(page);
  assert.ok(w > 246 && w <= 520, `ширина під назву: ${w}`);
  await page.dblclick("#panel-resize");
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) === 246);
  await page.focus("#panel-resize");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) > 246);
});

test("клавіші ← →: крок 16; aria-значення йдуть слідом", async (t) => {
  const page = await boot(t, 200);
  await page.focus("#panel-resize");
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.getElementById("panel-resize").getAttribute("aria-valuenow") === "262");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await page.waitForFunction(() => document.getElementById("panel-resize").getAttribute("aria-valuenow") === "230");
  assert.equal(await page.getAttribute("#panel-resize", "role"), "separator");
});

test("вузьке вікно: ширина не виходить за 800 − 420 = 380; мінімум 200", async (t) => {
  const page = await boot(t, 300, { width: 800, height: 700 });
  await drag(page, 600);
  await settled(page);
  await page.waitForFunction(() => document.getElementById("pages-panel").getBoundingClientRect().width <= 380.5);
  assert.equal(await panelW(page), 380);
  await drag(page, -900);
  await settled(page);
  await page.waitForFunction(() => Math.round(document.getElementById("pages-panel").getBoundingClientRect().width) === 200);
});

test("«Огляд»: після зміни ширини полотно вписується заново (камеру не рухали)", async (t) => {
  const page = await boot(t, 400);
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden]) #world");
  const tf = () => page.evaluate(() => document.getElementById("world").style.transform);
  await page.waitForFunction(() => document.getElementById("world").style.transform !== "");
  const before = await tf();
  await drag(page, 120);
  await settled(page);
  await page.waitForFunction((b) => document.getElementById("world").style.transform !== b, before, { timeout: 5000 });
});
```

Run (очікується червоне, доки Step 9 не зроблено — якщо вже зроблено, зелене): команда з «Спільних правил» для `panel-resize`.
Expected: `rc=0`.

- [ ] **Step 11: Сусідні живі тести, чутливі до ширини**

Run: `until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME="$(mktemp -d)" node --test --import ./tests/live/_env.mjs tests/live/shell-panel.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo "rc=$rc"`
Expected: `rc=0` (там ширина 320 і типові 246 — без збереженого значення нічого не змінилось). Те саме для `tests/live/panel-click.test.mjs` (клік по `.panel-fill` згортає — ручка стоїть над краєм, не над заповнювачем).

- [ ] **Step 12: Юніт-набір і охоронці**

Run: `node --test tests/panel-width.test.mjs tests/names-css.test.mjs tests/i18n.test.mjs tests/i18n-keys.test.mjs tests/i18n-literals.test.mjs tests/css-guards.test.mjs tests/live-ports.test.mjs`
Expected: PASS.

- [ ] **Step 13: Commit**

```bash
git add -- app/panel-width.js app/panel-resize.js tests/panel-width.test.mjs tests/names-css.test.mjs tests/live/panel-resize.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.40): ручка ширини лівої панелі (200–520, зберігається, под. клік під найдовшу назву)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/panel-width.js app/panel-resize.js app/styles.css app/app.js app/i18n.js tests/panel-width.test.mjs tests/names-css.test.mjs tests/live/panel-resize.test.mjs
```

---

### Task 3: `app/location-model.js`

**Files:** Create `app/location-model.js`, `tests/location-model.test.mjs`.

Формат: `#sp=<простір>&t=<задача>&it=<ітерація>&p=<сторінка>[&st=<стан>][&m=o[&v=flow]][&h=tasks|settings]`. Порядок ключів канонічний; значення `encodeURIComponent`; невідомі ключі й порожні значення ігноруються; `v=flow` має сенс лише з `m=o`; `st` лише з `p`; ключ `p=` сумісний із превʼю (`#p=` в `ext-shell.js`, там читається і як сусід `k=` гейта — розбір тут теж терпимий до чужих ключів).

- [ ] **Step 1: Падаючий тест** — `tests/location-model.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { EMPTY_LOC, formatLocation, hasPlace, parseLocation, sameLocation } from "../app/location-model.js";

const L = (o) => ({ ...EMPTY_LOC, ...o });

test("порожній hash → порожнє місце; hasPlace false", () => {
  for (const h of ["", "#", undefined, null]) {
    assert.deepEqual(parseLocation(h), EMPTY_LOC);
  }
  assert.equal(hasPlace(EMPTY_LOC), false);
  assert.equal(formatLocation(EMPTY_LOC), "");
});

test("туди й назад: усі ключі в канонічному порядку", () => {
  const loc = L({ sp: "studio", t: "fb-01102026-7f7b6d", it: "it2", p: "holovna", st: "open", m: "o", v: "flow", h: "settings" });
  const hash = formatLocation(loc);
  assert.equal(hash, "#sp=studio&t=fb-01102026-7f7b6d&it=it2&p=holovna&st=open&m=o&v=flow&h=settings");
  assert.deepEqual(parseLocation(hash), loc);
});

test("кодування: id з `--`, пробілами, кирилицею, `&`, `=`, `#`", () => {
  const loc = L({ t: "my--task one", p: "Головна & Пошук=1#x", it: "it1" });
  const hash = formatLocation(loc);
  assert.ok(!hash.slice(1).includes(" "), "пробіл закодовано");
  assert.equal(hash.split("&").length, 3, "`&` у значенні не створив зайвого ключа");
  assert.deepEqual(parseLocation(hash), loc);
});

test("невідомі ключі, порожні значення й сміття ігноруються; останній дубль перемагає", () => {
  const loc = parseLocation("#zzz=1&t=a&=b&it=&p=x&p=y&k=gate");
  assert.deepEqual(loc, L({ t: "a", p: "y" }));
});

test("зіпсований відсоток не кидає: значення лишається як є (як у ext-shell)", () => {
  assert.equal(parseLocation("#p=%E0%A4%A").p, "%E0%A4%A");
});

test("m і v: лише відомі значення; v=flow без m=o не пишеться; st без p не пишеться", () => {
  assert.equal(parseLocation("#m=x&v=y&h=z").m, null);
  assert.equal(parseLocation("#m=x&v=y&h=z").v, null);
  assert.equal(parseLocation("#m=x&v=y&h=z").h, null);
  assert.equal(formatLocation(L({ t: "a", v: "flow" })), "#t=a");
  assert.equal(formatLocation(L({ t: "a", st: "s1" })), "#t=a");
  assert.equal(formatLocation(L({ t: "a", m: "o" })), "#t=a&m=o");
});

test("sameLocation: порівнює канонічно, а не за порядком ключів у рядку", () => {
  assert.equal(sameLocation(parseLocation("#p=a&t=b"), parseLocation("#t=b&p=a")), true);
  assert.equal(sameLocation(L({ t: "a" }), L({ t: "b" })), false);
  assert.equal(sameLocation(L({ t: "a", v: "flow" }), L({ t: "a" })), true, "v без m=o не значущий");
});

test("`p=` сумісний із превʼю: той самий ключ і той самий регексп читають однаково", () => {
  const h = formatLocation(L({ t: "a", p: "holovna" }));
  assert.match(h, /(?:^#|&)p=holovna(?:&|$)/);
});
```

- [ ] **Step 2: Падіння** — `node --test tests/location-model.test.mjs` → FAIL (нема модуля).

- [ ] **Step 3: `app/location-model.js`**

```js
/**
 * Адреса оболонки (0.40): де людина в канвасі — hash `#sp=…&t=…&it=…&p=…` (+ `st`, `m=o`, `v=flow`, `h=tasks|settings`).
 * Чисті функції без DOM. Ключ `p=` має ту саму семантику, що в превʼю (`#p=` у `ext-shell.js`). Невідомі ключі ігноруються.
 */
export const EMPTY_LOC = Object.freeze({ sp: null, t: null, it: null, p: null, st: null, m: null, v: null, h: null });
/** Ключі-рядки в канонічному порядку; `app/agent_guide` і тема `docs/agents/links.md` звіряються з цим переліком парним тестом. */
export const LOC_KEYS = ["sp", "t", "it", "p", "st"];

const dec = (s) => { try { return decodeURIComponent(s); } catch (e) { return s; } };   // чиясь обрізана адреса не ламає старт

export function parseLocation(hash) {
  const loc = { ...EMPTY_LOC };
  const raw = String(hash || "").replace(/^#/, "");
  if (!raw) return loc;
  for (const part of raw.split("&")) {
    const i = part.indexOf("=");
    if (i <= 0) continue;
    const k = part.slice(0, i);
    const v = dec(part.slice(i + 1));
    if (!v) continue;
    if (LOC_KEYS.includes(k)) loc[k] = v;
    else if (k === "m") loc.m = v === "o" ? "o" : null;
    else if (k === "v") loc.v = v === "flow" ? "flow" : null;
    else if (k === "h") loc.h = v === "tasks" || v === "settings" ? v : null;
  }
  return loc;
}

export function formatLocation(loc) {
  const l = { ...EMPTY_LOC, ...loc };
  const out = [];
  for (const k of LOC_KEYS) {
    if (!l[k]) continue;
    if (k === "st" && !l.p) continue;
    out.push(`${k}=${encodeURIComponent(l[k])}`);
  }
  if (l.m === "o") {
    out.push("m=o");
    if (l.v === "flow") out.push("v=flow");
  }
  if (l.h) out.push(`h=${l.h}`);
  return out.length ? `#${out.join("&")}` : "";
}

export const sameLocation = (a, b) => formatLocation(a) === formatLocation(b);
export const hasPlace = (loc) => formatLocation(loc) !== "";
```

- [ ] **Step 4: Зелене** — `node --test tests/location-model.test.mjs` → PASS (8).

- [ ] **Step 5: Commit**

```bash
git add -- app/location-model.js tests/location-model.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.40): модель адреси оболонки location-model (parse/format/same)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/location-model.js tests/location-model.test.mjs
```

---

### Task 4: `app/nav.js` — запис адреси, і відновлення на старті (РИЗИК: старт, гонки `render()`)

**Files:**
- Create: `app/nav.js`, `tests/nav.test.mjs`, `tests/live/nav-history.test.mjs`
- Modify: `app/app.js` (імпорти, `curLoc`, `nav`, хвіст `render()`, `enterHome`, старт)

Тут з `nav.js` потрібні `sync` (запис) і `want` (намір «перехід зробила людина»). `popstate`, `back/forward`, відмова — у T5, але модуль пишемо цілим тепер (один файл, один тест) — у T4 живий тест перевіряє лише запис і відновлення.

Правила запису (спека §2): `sync()` порівнює поточний стан із hash; однаково — нічого; інакше `pushState`, якщо перед цим стояв `want()` (не старший за 5 с), інакше `replaceState`. Кожен запис несе `history.state = {dcn: <номер>}`; максимум номера тримаємо в `sessionStorage` (`dc-nav-max`), щоб після перезавантаження «→» знала, чи є що йти вперед.

- [ ] **Step 1: Падаючий юніт** — `tests/nav.test.mjs` (фальшиве вікно з історією):

```js
import assert from "node:assert/strict";
import test from "node:test";
import { createNav } from "../app/nav.js";
import { EMPTY_LOC } from "../app/location-model.js";

const L = (o) => ({ ...EMPTY_LOC, ...o });
const tick = () => new Promise((r) => setTimeout(r, 15));

/** Фальшиве вікно: записи історії, `go()` стріляє `popstate` асинхронно, як браузер. */
function fakeWin(hash = "") {
  const entries = [{ state: null, url: `/app/${hash}` }];
  let i = 0;
  const pops = [];
  const win = {
    location: {
      pathname: "/app/", search: "",
      get hash() { const u = entries[i].url; const k = u.indexOf("#"); return k < 0 ? "" : u.slice(k); },
    },
    history: {
      get state() { return entries[i].state; },
      pushState(s, _t, u) { entries.splice(i + 1); entries.push({ state: s, url: u }); i += 1; },
      replaceState(s, _t, u) { entries[i] = { state: s, url: u }; },
      go(n) { const j = i + n; if (j < 0 || j >= entries.length) return; i = j; setTimeout(() => pops.forEach((f) => f({ state: entries[i].state })), 0); },
      back() { this.go(-1); }, forward() { this.go(1); },
    },
    addEventListener(type, fn) { if (type === "popstate") pops.push(fn); },
  };
  return { win, entries, idx: () => i };
}

function setup({ hash = "", goTo, now } = {}) {
  const w = fakeWin(hash);
  const cur = { loc: L({ t: "a", it: "it1", p: "x" }) };
  const calls = [];
  let changed = 0;
  const nav = createNav({
    win: w.win, getLoc: () => cur.loc, onChange: () => { changed += 1; }, now,
    /* Справжній `goTo` ставить стан місця, куди повів, — інакше `sync()` після переходу переписав би запис «поточним» станом. */
    goTo: goTo ?? (async (loc) => { calls.push(loc); cur.loc = loc; return true; }),
  });
  return { ...w, nav, cur, calls, changed: () => changed };
}

test("старт без state: запис отримує номер 0; ← і → вимкнені", () => {
  const s = setup();
  assert.deepEqual(s.entries[0].state, { dcn: 0 });
  assert.equal(s.nav.canBack(), false);
  assert.equal(s.nav.canFwd(), false);
});

test("sync без наміру — replaceState (запис один), hash нормалізується", () => {
  const s = setup();
  s.nav.sync();
  assert.equal(s.entries.length, 1);
  assert.equal(s.entries[0].url, "/app/#t=a&it=it1&p=x");
});

test("sync з наміром — pushState, номер росте, ← доступна; повторний sync з тим самим станом нічого не пише", () => {
  const s = setup();
  s.nav.sync();
  s.nav.want();
  s.cur.loc = L({ t: "a", it: "it1", p: "y" });
  s.nav.sync();
  assert.equal(s.entries.length, 2);
  assert.deepEqual(s.entries[1].state, { dcn: 1 });
  assert.equal(s.nav.canBack(), true);
  assert.equal(s.nav.canFwd(), false);
  s.nav.want();
  s.nav.sync();
  assert.equal(s.entries.length, 2, "той самий стан — нового запису нема");
});

test("намір застарів (понад 5 с) — звичайний replace, а не push", () => {
  let t = 1000;
  const s = setup({ now: () => t });
  s.nav.sync();
  s.nav.want();
  t += 6000;
  s.cur.loc = L({ t: "a", p: "z" });
  s.nav.sync();
  assert.equal(s.entries.length, 1);
});

test("Назад → goTo з розібраним hash; прийнято — індекс ще 0, → доступна", async () => {
  const s = setup();
  s.nav.sync();
  s.nav.want();
  s.cur.loc = L({ t: "a", p: "y" });
  s.nav.sync();
  s.nav.back();
  await tick();
  assert.equal(s.calls.length, 1);
  assert.equal(s.calls[0].p, "x");
  assert.equal(s.idx(), 0);
  assert.equal(s.nav.canBack(), false);
  assert.equal(s.nav.canFwd(), true);
});

test("охоронець відмовив: вказівник історії вертається, goTo викликано один раз, адреса лишилась поточною", async () => {
  const s = setup({ goTo: async () => false });
  s.nav.sync();
  s.nav.want();
  s.cur.loc = L({ t: "a", p: "y" });
  s.nav.sync();
  const urlBefore = s.entries[1].url;
  s.nav.back();
  await tick(); await tick();
  assert.equal(s.idx(), 1, "повернулись на запис 1");
  assert.equal(s.entries[s.idx()].url, urlBefore);
  assert.equal(s.nav.canBack(), true);
});

test("новий перехід після ← відтинає «вперед»", async () => {
  const s = setup();
  s.nav.sync();
  for (const p of ["y", "z"]) { s.nav.want(); s.cur.loc = L({ t: "a", p }); s.nav.sync(); }
  s.nav.back(); await tick();
  assert.equal(s.nav.canFwd(), true);
  s.nav.want(); s.cur.loc = L({ t: "a", p: "n" }); s.nav.sync();
  assert.equal(s.nav.canFwd(), false);
});

test("hash змінено руками (state нема): goTo викликано; відмова переписує запис поточним місцем, без відкоту", async () => {
  const s = setup({ goTo: async () => false });
  s.nav.sync();
  s.win.history.pushState(null, "", "/app/#t=other");   // запис без нашого state — як ручна правка адреси
  s.win.history.go(0);                                   // браузер стріляє popstate зі state === null
  await tick(); await tick();
  assert.equal(s.win.location.hash, "#t=a&it=it1&p=x", "після відмови адреса — поточне місце");
  assert.equal(s.idx(), 1, "вказівник не рухався");
});

test("sessionStorage-подібний store: максимум переживає створення нового nav", () => {
  const mem = { n: 0 };
  const store = { get: () => mem.n, set: (n) => { mem.n = n; } };
  const w = fakeWin();
  const cur = { loc: L({ t: "a" }) };
  const a = createNav({ win: w.win, store, getLoc: () => cur.loc, goTo: async () => true });
  a.sync(); a.want(); cur.loc = L({ t: "b" }); a.sync();
  w.win.history.go(-1);   // як після ← і перезавантаження: запис 0, а максимум 1
  const b = createNav({ win: w.win, store, getLoc: () => cur.loc, goTo: async () => true });
  assert.equal(b.canFwd(), true);
});
```

(Тест «hash відредагований руками» перевіряє гілку `state === null`; якщо його складність дратує — спростити до виклику `pops` напряму, але гілку лишити покритою.)

- [ ] **Step 2: Падіння** — `node --test tests/nav.test.mjs` → FAIL (нема модуля).

- [ ] **Step 3: `app/nav.js`**

```js
/**
 * Історія переходів оболонки (0.40): запис адреси, індекс запису, Назад/Вперед. Залежності (вікно, хто знає поточне місце,
 * хто веде в місце) приходять ззовні — модуль не знає про `app.js` і тестується на фальшивому `window`.
 *
 * Правила:
 *  · `sync()` — ЄДИНЕ місце запису адреси. Однакове місце — нічого; різне — `pushState`, якщо перед цим `want()` (перехід
 *    зробила людина, намір живе ≤ 5 с), інакше `replaceState` (нормалізація, автоуточнення).
 *  · Кожен запис несе `history.state = {dcn: <номер>}`; максимум номера — у `store` (sessionStorage), щоб після
 *    перезавантаження «→» знала, чи є що йти вперед.
 *  · `popstate` → `goTo(loc)`. Відмова (`false`: майстер, незбережена панель, зайнятий перехід) — вертаємо вказівник історії
 *    `history.go(різниця)`; власний `popstate` від цього відкоту ковтаємо. Переходи по черзі (`chain`).
 */
import { formatLocation, parseLocation, sameLocation } from "./location-model.js";

export const INTENT_TTL = 5000;

export function createNav({ win, store = null, getLoc, goTo, onChange = () => {}, now = () => Date.now() }) {
  const hist = win.history;
  let idx = Number.isInteger(hist.state?.dcn) ? hist.state.dcn : 0;
  let max = Math.max(idx, Number(store?.get?.()) || 0);
  let intent = null, restoring = 0, chain = Promise.resolve();
  const urlOf = (hash) => `${win.location.pathname}${win.location.search}${hash}`;
  if (!Number.isInteger(hist.state?.dcn)) hist.replaceState({ dcn: idx }, "", urlOf(win.location.hash));

  const flags = () => `${idx > 0}|${idx < max}`;
  let shown = flags();
  const notify = () => { const f = flags(); if (f !== shown) { shown = f; onChange(); } };

  /** Наступний запис — перехід, який зробила людина. */
  function want() { intent = now(); }

  function sync() {
    const loc = getLoc();
    const push = intent !== null && now() - intent < INTENT_TTL;
    intent = null;
    if (sameLocation(parseLocation(win.location.hash), loc)) return;
    const url = urlOf(formatLocation(loc));
    if (push) {
      idx += 1;
      max = idx;
      hist.pushState({ dcn: idx }, "", url);
      store?.set?.(max);
    } else {
      hist.replaceState({ dcn: idx }, "", url);
    }
    notify();
  }

  win.addEventListener("popstate", (ev) => {
    if (restoring > 0) { restoring -= 1; return; }   // власний відкіт після відмови
    const to = Number.isInteger(ev.state?.dcn) ? ev.state.dcn : null;
    const from = idx;
    const loc = parseLocation(win.location.hash);
    chain = chain.then(async () => {
      let ok = false;
      try { ok = await goTo(loc); } catch (e) { ok = false; }
      if (ok) {
        if (to !== null) idx = to;
        if (idx > max) max = idx;
        sync();
        notify();
        return;
      }
      if (to !== null && to !== from) { restoring += 1; hist.go(from - to); }
      else hist.replaceState({ dcn: idx }, "", urlOf(formatLocation(getLoc())));
    });
  });

  return {
    want, sync,
    canBack: () => idx > 0,
    canFwd: () => idx < max,
    back() { if (idx > 0) hist.back(); },
    forward() { if (idx < max) hist.forward(); },
    index: () => idx,
  };
}
```

- [ ] **Step 4: Юніт зелений** — `node --test tests/nav.test.mjs` → PASS. Якщо тест `sessionStorage-подібний store` падає через порядок фальшивого `go` — виправити тест (поведінку `createNav` не зсувати).

- [ ] **Step 5: Проводка в `app/app.js` — місце зараз (`curLoc`) і `nav`.** Імпорти (поруч із попередніми):

```js
import { createNav } from './nav.js';
import { hasPlace, parseLocation } from './location-model.js';
```

Безпосередньо перед рядком `async function switchTask(val) {` (докстрінг «Переключення поточної задачі» над ним лишається над `switchTask`; вставити ПЕРЕД цим докстрінгом) додати:

```js
/* ── Місце в адресі (0.40) ────────────────────────────────────────────────────────────────────────────────────────────
   `curLoc()` — стан → місце (`location-model.js`); `nav` пише його в адресу з ОДНОГО місця (`nav.sync()` наприкінці
   `render()` та в `enterHome`) і веде Назад/Вперед. Намір «перехід зробила людина» (`nav.want()`) ставлять дії-переходи
   ПЕРЕД `render()`; без нього адреса лише нормалізується (`replaceState`). */
const curLoc = () => ({
  sp: spaceNow()?.id || null,
  t: currentTaskId || null,
  it: picked,
  p: pickedPage,
  st: pickedState,
  m: mode === 'canvas' ? 'o' : null,
  v: mode === 'canvas' && canvasView === 'flow' ? 'flow' : null,
  h: homeOpen ? (homePage === 'conn' ? 'settings' : 'tasks') : null,
});
const nav = createNav({
  win: window,
  store: {
    get: () => { try { return Number(sessionStorage.getItem('dc-nav-max')) || 0; } catch (e) { return 0; } },
    set: (n) => { try { sessionStorage.setItem('dc-nav-max', String(n)); } catch (e) { /* без сховища «→» лише в межах сеансу */ } },
  },
  getLoc: curLoc,
  goTo: (loc) => goTo(loc),   // `goTo` — T5; до нього `popstate` нічого не веде
  onChange: () => paintBar(),
});
```

І тимчасова заглушка (замінить T5) — одразу після блока:

```js
async function goTo() { return false; }
```

- [ ] **Step 6: Хвіст `render()`.** Замінити

```js
  await loadPages();
  paintBar();
  applyMode(task, { keepFrame });
  renderPanel();
```
на
```js
  await loadPages();
  paintBar();
  applyMode(task, { keepFrame });
  renderPanel();
  nav.sync();   // 0.40: адреса — з одного місця, після того як стан усталився
```

- [ ] **Step 7: `enterHome`.** Єдина вставка після `paintBar()` у синхронній частині: знайти фрагмент

```js
  const el = ensureHome();
  el.hidden = false;
  paintBar();
  if (homePage === 'wiz') {
```
і замінити на
```js
  const el = ensureHome();
  el.hidden = false;
  paintBar();
  nav.sync();   // 0.40: «Задачі» / «Налаштування» (h=…) — теж місце в адресі
  if (homePage === 'wiz') {
```
(Майстер дає `h=tasks`, як і «Задачі»: окремого запису для нього нема.)

- [ ] **Step 8: Старт.** Замінити останній рядок файла

```js
loadTune().then(render).then(async () => { await refreshGitlab(); paintBar(); });
```
на
```js
/* Старт із адреси (0.40). Сервер володіє поточними простором і задачею, тож задачу з адреси перемикаємо НА СЕРВЕРІ — до
   `loadTune()` (пакет тюнера береться для поточної задачі); решту (ітерація, сторінка, стан, режим, вид) ставимо змінними до
   першого `render()`. Невідоме чи видалене — тихо лишаємо звичне (остання ітерація, перша сторінка): `render()` нормалізує. */
async function bootPlace() {
  const loc = parseLocation(location.hash);
  if (!hasPlace(loc)) return null;
  try {
    if (loc.t) {
      const list = await api('/api/tasks');
      const x = (list.tasks || []).find((y) => y.id === loc.t);
      if (x && !x.missing && list.current !== loc.t) await post('/api/task-switch', { id: loc.t });
    }
  } catch (e) { /* сервер ще не відповів — звичайний старт */ }
  return loc;
}
function applyBootPlace(loc) {
  if (!loc) return;
  if (loc.it) picked = loc.it;
  if (loc.p) { pickedPage = loc.p; pickedState = loc.st || null; }
  if (loc.m === 'o') { mode = 'canvas'; canvasView = loc.v === 'flow' ? 'flow' : 'grid'; }
}
bootPlace()
  .then(async (loc) => { await loadTune(); applyBootPlace(loc); await render(); return loc; })
  .then(async (loc) => {
    if (loc?.m === 'o' && mode === 'canvas') { await freshen(); maybeAutoShoot(); await render(); }   // як вхід у «Огляд» кнопкою
    if (loc?.h === 'tasks') enterHome({ page: 'tasks' });
    else if (loc?.h === 'settings') await enterConnections();
    await refreshGitlab(); paintBar();
  });
```

(Нормалізація `picked`: `render()` скидає `picked` на останню, якщо id невідомий; `loadPages()` — `pickedPage` на першу відкривану. `pickedState` для чужої сторінки скидає той самий блок.)

- [ ] **Step 9: Живий тест — запис і відновлення.** `tests/live/nav-history.test.mjs` (T5 доповнить цей файл):

```js
/**
 * Місце в адресі й історія (0.40). T4: адреса відображає місце (replaceState без переходу), перезавантаження лишає на місці
 * (задача, ітерація, сторінка, режим, вид «Огляду»), невідоме/видалене — тихий запасний варіант, `/app/#…` віддається.
 * T5 (нижче в цьому файлі): записи історії, Назад/Вперед, кнопки, ⌘[ ⌘], відмова охоронця.
 */
import assert from "node:assert/strict";
import { cpSync, writeFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 52000;
const VIEW = { width: 1440, height: 900 };
const PAGE = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body style="margin:40px"><h1>${id}</h1><p>Абзац ${id}</p></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

/** Задача з двома ітераціями (it1, it2) і двома сторінками (holovna, poshuk). */
function twoIterations() {
  const { dir } = taskFixture({ html: PAGE });
  cpSync(path.join(dir, "iterations", "it1"), path.join(dir, "iterations", "it2"), { recursive: true });
  writeFileSync(path.join(dir, "iterations.json"), JSON.stringify({ iterations: [
    { id: "it1", date: "24.08.2026 12:00", note: "перша", published: true },
    { id: "it2", date: "25.08.2026 12:00", note: "друга", published: true }] }));
  return dir;
}
export async function boot(t, off, { hash = "", viewport = VIEW } = {}) {
  const dir = twoIterations();
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport });
  t.after(() => page.close());
  await page.goto(`${url}/app/${hash}`);
  await page.waitForSelector('[data-act="page"][data-val="holovna"]');
  return { page, url };
}
const src = (page) => page.getAttribute("#frame", "src");
const hash = (page) => page.evaluate(() => location.hash);
const idxOf = (page) => page.evaluate(() => history.state?.dcn);
const frameReady = (page, re) => page.waitForFunction((s) => new RegExp(s).test(document.getElementById("frame").getAttribute("src") || ""), re.source);

test("T4-1: адреса відображає місце; на старті запис один (replace), номер 0", async (t) => {
  const { page } = await boot(t, 0);
  await page.waitForFunction(() => /it=it2/.test(location.hash) && /p=holovna/.test(location.hash));
  assert.match(await hash(page), /^#(sp=[^&]*&)?t=[^&]+&it=it2&p=holovna$/);
  assert.equal(await idxOf(page), 0);
});

test("T4-2: перезавантаження лишає на місці — ітерація, сторінка, «Огляд» і вид", async (t) => {
  const { page } = await boot(t, 100);
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="iter"][data-val="it1"]');
  await page.click('[data-act="page"][data-val="poshuk"]');
  await frameReady(page, /it=it1.*page=poshuk/);
  await page.waitForFunction(() => /it=it1/.test(location.hash) && /p=poshuk/.test(location.hash));
  await page.reload();
  await frameReady(page, /it=it1.*page=poshuk/);
  assert.equal(await page.$eval('[data-act="page"][aria-selected="true"]', (e) => e.dataset.val), "poshuk");

  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForFunction(() => /m=o/.test(location.hash));
  await page.click('#bar [data-act="view"][data-val="flow"]', { timeout: 1500 }).catch(() => {});   // «Флоу» може бути вимкнено без flow.json — тоді лишаємось у сітці
  const h = await hash(page);
  await page.reload();
  await page.waitForSelector("#canvas:not([hidden])");
  assert.equal(await hash(page), h, "адреса після перезавантаження та сама");
  assert.equal(await page.evaluate(() => document.getElementById("stage").hidden), true, "відкрито «Огляд», а не «Макет»");
});

test("T4-3: видалена ітерація й невідома задача в адресі — тихо до запасних, адреса виправляється (replace)", async (t) => {
  const { page } = await boot(t, 200, { hash: "#t=no-such-task&it=it99&p=nope" });
  await page.waitForFunction(() => /it=it2/.test(location.hash));
  assert.match(await hash(page), /it=it2&p=holovna/);
  assert.equal(await idxOf(page), 0, "виправлення — replace, записів не додало");
  assert.equal(await page.evaluate(() => document.getElementById("pages-panel") !== null), true);
});

test("T4-4: `/app/#…` віддається (service worker не залежить від hash)", async (t) => {
  const { page, url } = await boot(t, 300);
  const r = await page.goto(`${url}/app/#t=x&it=it1`);
  assert.ok(r === null || r.ok(), "перехід на /app/ з hash не зламано");
  await page.waitForSelector('[data-act="page"][data-val="holovna"]');
});
```

(Селектор виду «Флоу» і ярлик `[data-act="view"][data-val="flow"]` — з `seg()` у `shell-bar.js`; без `flow.json` кнопка `disabled`, тест це переносить.)

Run: `until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; HOME="$(mktemp -d)" node --test --import ./tests/live/_env.mjs tests/live/nav-history.test.mjs; rc=$?; rmdir /private/tmp/deai-live.lock; echo "rc=$rc"`
Expected: `rc=0`. Якщо T4-2 показує ДВОЄ завантаження рамки при старті — це гонка (зайвий `render()`): перевірити, що `applyBootPlace` викликається лише ОДИН раз до першого `render()`, а другий `render()` — лише для «Огляду».

- [ ] **Step 10: Регресійний прохід близьких живих файлів** (по одному, команда з «Спільних правил»): `shell.test.mjs`, `frame-links.test.mjs`, `settings-nav.test.mjs`.
Expected: `rc=0` у кожного.

- [ ] **Step 11: Commit**

```bash
git add -- app/nav.js tests/nav.test.mjs tests/live/nav-history.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.40): адреса відображає місце (replaceState), відновлення на старті після перезавантаження" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/nav.js app/app.js tests/nav.test.mjs tests/live/nav-history.test.mjs
```

---

### Task 5: `goTo`, записи історії, Назад / Вперед / Оновити, ⌘[ ⌘] (РИЗИК: найбільший)

**Files:**
- Modify: `app/app.js`, `app/bar-model.js`, `app/shell-bar.js`, `app/styles.css`, `app/i18n.js`
- Create: `tests/bar-nav.test.mjs`
- Modify (тест): `tests/live/nav-history.test.mjs`

Принцип: `goTo(loc)` НЕ викликає `BAR_ACTIONS.*` підряд (кожна робить власний `render()`, а присвоєння `frame.src` і є перезавантаженням — два поспіль = подвійне завантаження рамки, див. коментар біля `leaveHome`). Вона повторює їхній СТАН (змінні) і робить один `render()`, але поважає ті самі охоронці й `switchTask`/`enterHome`/`leaveHome`/`enterConnections`.

- [ ] **Step 1: Падаючий юніт смуги** — `tests/bar-nav.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { barModel } from "../app/bar-model.js";
import { setLang } from "../app/i18n.js";
import { barHTML } from "../app/shell-bar.js";

setLang("uk");
const base = { mode: "layout", view: "grid", vp: "desktop", vpw: "", taskId: "t1", taskTitle: "Задача", hasIteration: true, iterLabel: "Іт.1", iterList: [{ id: "it1", label: "Іт.1" }], iterId: "it1" };

test("0.40: без стану `nav` смуга лишається такою, як була (золоті знімки ЛІГИ не зсуваються)", () => {
  const m = barModel(base);
  assert.ok(!m.zone1.some((x) => x.id === "nav"));
  assert.ok(!barHTML(m, base).includes('data-act="navback"'));
});

test("0.40: зі станом `nav` елемент стоїть ПЕРШИМ у зоні 1; ← → вимикаються за станом", () => {
  const s = { ...base, nav: { back: false, fwd: true } };
  const m = barModel(s);
  assert.equal(m.zone1[0].id, "nav");
  assert.equal(m.zone1[0].backOff, true);
  assert.equal(m.zone1[0].fwdOff, false);
  const h = barHTML(m, s);
  assert.match(h, /<button[^>]*data-act="navback"[^>]*disabled/);
  assert.doesNotMatch(h, /<button[^>]*data-act="navfwd"[^>]*disabled/);
  assert.ok(h.indexOf('data-act="navback"') < h.indexOf('class="crumbs"'), "кнопки перед крихтами");
  assert.match(h, /data-act="navreload"/);
});

test("0.40: на екрані «Задачі» (домівка) кнопок нема", () => {
  const s = { ...base, homeOpen: true, homePage: "tasks", nav: { back: true, fwd: true } };
  assert.ok(!barHTML(barModel(s), s).includes('data-act="navback"'));
});

test("0.40: id контролів унікальні й у присутності nav", () => {
  const m = barModel({ ...base, nav: { back: true, fwd: true } });
  const ids = [...m.zone1, ...m.zone2, ...m.zone3].map((x) => x.id);
  assert.equal(new Set(ids).size, ids.length);
});
```

(Поля `base` звірити з `base` у `tests/bar-model.test.mjs`, якщо `barModel` вимагатиме інших; тест міняти лише в `base`.)

- [ ] **Step 2: Падіння** — `node --test tests/bar-nav.test.mjs` → FAIL.

- [ ] **Step 3: i18n** — в кінець `UK` і `EN` (перед `};`):

```js
  /* 0.40: кнопки навігації смуги (підказки через `data-tip`). */
  navBack: 'Назад ⌘[',
  navFwd: 'Вперед ⌘]',
  navReload: 'Оновити макет',
```
```js
  /* 0.40: bar navigation buttons (tips via `data-tip`). */
  navBack: 'Back ⌘[',
  navFwd: 'Forward ⌘]',
  navReload: 'Reload mockup',
```

- [ ] **Step 4: Модель** — у `app/bar-model.js`, у `barModel`, одразу після блока `if (s.hasIteration) { … }` (що наповнює `zone1`), перед `const zone2 = [`:

```js
  /* Назад / Вперед / Оновити (0.40) — перші в зоні 1, лише коли оболонка дала стан історії: золоті знімки ЛІГИ й превʼю
     (`ext-bar.js`) стану `nav` не мають, тож їхня розмітка не змінюється. Екран «Задачі» повертається вище — без кнопок. */
  if (s.nav) zone1.unshift({ id: "nav", tier: 0, backOff: !s.nav.back, fwdOff: !s.nav.fwd });
```

- [ ] **Step 5: Розмітка** — у `app/shell-bar.js` перед `export function barHTML` додати:

```js
/* Назад / Вперед / Оновити (0.40): три кнопки-іконки на початку зони 1. Підказки — `data-tip` (`app/tooltip.js`), не `title`. */
function navHTML(model) {
  const c = model.zone1.find((x) => x.id === "nav");
  if (!c) return "";
  const b = (act, icon, key, off) => `<button class="ctl ctl--icon" data-act="${act}" data-tip="${esc(t(key))}"`
    + ` aria-label="${esc(t(key))}"${off ? " disabled" : ""}>${ico(icon, 16)}</button>`;
  return `<div class="nav" role="group">${b("navback", "chevleft", "navBack", c.backOff)}${b("navfwd", "chevright", "navFwd", c.fwdOff)}${b("navreload", "refresh", "navReload", false)}</div>`;
}
```

і в `barHTML` замінити

```js
    : `<div class="crumbs">${crumbTask(model, openDd, state)}${iter ? `<span class="crumb-sep" aria-hidden="true">/</span>${iter}` : ""}</div>`;
```
на
```js
    : `${navHTML(model)}<div class="crumbs">${crumbTask(model, openDd, state)}${iter ? `<span class="crumb-sep" aria-hidden="true">/</span>${iter}` : ""}</div>`;
```

- [ ] **Step 6: CSS** — після `.zone-3{justify-content:flex-end}` у `app/styles.css`:

```css
/* Назад / Вперед / Оновити (0.40): кнопки 28 px, роздільник праворуч. */
.nav{display:flex;align-items:center;gap:2px;flex:none;padding-right:6px;margin-right:4px;border-right:1px solid var(--line)}
.nav .ctl--icon{width:var(--h-sm);height:var(--h-sm)}
```

- [ ] **Step 7: Зелений юніт** — `node --test tests/bar-nav.test.mjs tests/bar-model.test.mjs tests/shell-bar.test.mjs tests/legacy-golden.test.mjs tests/ext-bar.test.mjs tests/i18n.test.mjs` → PASS (золоті знімки не змінились).

- [ ] **Step 8: `goTo`, спільна частина перемикача режиму й проводка в `app/app.js`.**

(a) Винести синхронну частину `BAR_ACTIONS.mode`. Замінити початок дії

```js
  mode: async (val) => {
    const wantCanvas = val === 'overview';
    if (wantCanvas === (mode === 'canvas')) return;
    mode = wantCanvas ? 'canvas' : 'single';
    if (wantCanvas) ensureSetup();
```
на
```js
  mode: async (val) => {
    const wantCanvas = val === 'overview';
    if (wantCanvas === (mode === 'canvas')) return;
    setModeState(wantCanvas);
```
Решту тіла (довгий коментар `Перемикач — НЕ побічна перебудова…`) лишити, але рядки, що вже у функції-винесенні, прибрати: `camWorld = null;` і `if (mode === 'canvas') closeModTool();`. Підсумкова дія:

```js
    /* …коментар про camWorld лишається тут… */
    if (mode === 'canvas') { await freshen(); maybeAutoShoot(); }
    nav.want();
    render();
  },
```
А окрему функцію додати прямо над `const BAR_ACTIONS = {`:

```js
/** Синхронна частина перемикача «Макет/Огляд» (0.40: спільна для кнопки смуги й `goTo`): стан без `render()`. Забути світ камери
 *  тут, а не в `applyMode` — причина в коментарі всередині `BAR_ACTIONS.mode`. */
function setModeState(wantCanvas) {
  mode = wantCanvas ? 'canvas' : 'single';
  if (wantCanvas) ensureSetup();
  camWorld = null;
  if (wantCanvas) closeModTool();   // «Огляд» — знімки, не живий макет: інструмент модуля там не живе
}
```

(b) Замінити заглушку `async function goTo() { return false; }` (з T4) на:

```js
let goGen = 0;
const taskKnown = (id) => !!(curTaskList?.tasks || []).find((x) => x.id === id && !x.missing);
/**
 * «Веди в місце» (0.40): Назад/Вперед, «Показати» коментар, у майбутньому — «агент відкриває сторінку». Одна функція, що
 * повторює СТАН дій-переходів і робить РІВНО ОДИН `render()` (кожна дія окремо робить свій — подвійне завантаження рамки).
 * Охоронці ті самі, що в кнопок: майстер (`wiz.requestExit`), незбережена панель «Підключень» (`dismissCnDrawer`), зайняті
 * переходи (`homeOpening`, `tabSwitch`, `creatingIt`). `false` — відмовили: `nav` вернув вказівник історії.
 * `stillWanted` — зовнішня умова «ще актуально» (перевіряється перед `render()`); новіша `goTo` перебиває старішу.
 */
async function goTo(loc, { stillWanted = () => true } = {}) {
  if (homeOpening || tabSwitch || creatingIt) return false;
  if (homeOpen && homePage === 'wiz') {
    await wiz.requestExit();
    if (homeOpen && homePage === 'wiz') return false;   // не вийшов — відмова
  }
  if (cnDrawer && !(await dismissCnDrawer())) return false;
  const gen = ++goGen;
  const live = () => gen === goGen && stillWanted();
  if (loc.h === 'tasks') { enterHome({ page: 'tasks' }); return true; }
  if (loc.h === 'settings') { await enterConnections(); return true; }
  /* Задача (а з нею й простір — `task-switch` перемикає й простір). Невідому чи видалену тихо ігноруємо: лишаємось у поточній. */
  if (loc.t && loc.t !== currentTaskId && taskKnown(loc.t)) {
    if (!(await switchTask(loc.t))) return false;
  } else if (!loc.t && loc.sp && loc.sp !== spaceNow()?.id) {
    try { await post('/api/space-switch', { id: loc.sp }); } catch (e) { return false; }
    await resetSpaceState();
  }
  if (!live()) return false;
  followStamps = []; followLatchKey = null;   // свідомий перехід скидає запобіжник від циклу редиректів
  const wantCanvas = loc.m === 'o';
  if (wantCanvas !== (mode === 'canvas')) setModeState(wantCanvas);
  if (wantCanvas) canvasView = loc.v === 'flow' ? 'flow' : 'grid';
  if (loc.it && loc.it !== picked) { picked = loc.it; pickedPage = null; pickedState = null; }
  if (loc.p) { pickedPage = loc.p; pickedState = loc.st || null; }
  openDd = null;
  if (!live()) return false;
  if (homeOpen) await leaveHome(); else await render();
  if (mode === 'canvas' && live()) { await freshen(); maybeAutoShoot(); await render(); }   // як вхід у «Огляд» кнопкою
  return true;
}
```

(c) Намір `nav.want()` у діях-переходах — кожна вставка ПЕРЕД відповідним `render()`/`leaveHome()`:
- `BAR_ACTIONS.home`: у кінці `enterHome({ page: 'tasks' });` → `nav.want(); enterHome({ page: 'tasks' });`
- `BAR_ACTIONS.settings` і `conn`: перед `enterConnections();` додати `nav.want();`
- `BAR_ACTIONS.tab`: `try { if (await switchTask(val)) render(); }` → `try { if (await switchTask(val)) { nav.want(); render(); } }`
- `homeOpenTask`: перед `await leaveHome();` додати `nav.want();`
- `BAR_ACTIONS.iter`: перед завершальним `render();` додати `nav.want();`
- `BAR_ACTIONS.view`: `canvasView = val;` → `canvasView = val; nav.want();`
- `PANEL_ACTIONS.page`: після рядка `pickedPage = val; pickedState = null; followStamps = []; followLatchKey = null; …` додати `nav.want(); nav.sync();` (у «Огляді» цей шлях НЕ робить `render()`, а камера й адреса мусять піти за вибором; у «Макеті» наступний `render()` бачить те саме місце — нічого не дописує)
- `openCard`: `pickedPage = c.page; pickedState = c.state || null; mode = 'single'; render();` → `…; mode = 'single'; nav.want(); render();`
- обробник `load` рамки, гілка «посилання всередині макета»: перед `render();` після `pickedPage = id; pickedState = null;` додати `nav.want();`

(d) Кнопки смуги — у `BAR_ACTIONS` (біля `home:`):

```js
  /* Назад / Вперед / Оновити (0.40). Назад і Вперед — справжня історія вікна (`nav`), тож `popstate` → `goTo`. «Оновити»:
     у «Макеті» лише макет (`reloadFrame`), в «Огляді» — перебудувати полотно (`render`). */
  navback: () => nav.back(),
  navfwd: () => nav.forward(),
  navreload: () => { if (homeOpen) return; if (mode === 'canvas') render(); else reloadFrame(); },
```

(e) Стан смуги: у `barState()` у поверненому об'єкті одразу після `mode: canvas ? 'overview' : 'layout',` додати

```js
    nav: { back: nav.canBack(), fwd: nav.canFwd() },
```

(f) `goToComment` (0.39.1) — навігація через `goTo`. Замінити в ній фрагмент від `cmtPendingDrop();` до кінця функції

```js
  cmtPendingDrop();
  cmtPending = { id, it: tg.it, page: tg.page, gen, armed: false, timer: null };
  openDd = null;
  picked = tg.it; pickedPage = tg.page; pickedState = null; followStamps = []; followLatchKey = null;
  await loadPages();
  if (gen !== taskSwitchGen || seq !== cmtGoSeq || picked !== tg.it || pickedPage !== tg.page) return;   // користувач пішов деінде
  await render();
}
```
на
```js
  cmtPendingDrop();
  cmtPending = { id, it: tg.it, page: tg.page, gen, armed: false, timer: null };
  nav.want();
  /* Той самий перехід, що й Назад/Вперед: `goTo` ставить ітерацію/сторінку й робить один `render()`; «ще актуально» — як було. */
  await goTo({ ...curLoc(), it: tg.it, p: tg.page, st: null, h: null, m: null, v: null },
    { stillWanted: () => gen === taskSwitchGen && seq === cmtGoSeq });
}
```
(Перевірка наявності ітерації й сторінки на початку функції лишається — вона дає тост `cmtGoGone`.)

(g) Клавіші ⌘[ / ⌘] — спільний розбір для оболонки й рамки. Додати біля `frameCmtKey` (перед `let frameHash = null;`):

```js
/** Клавіші навігації (0.40), спільні для оболонки й вікна рамки: ⌘[ / ⌘] (Ctrl на Windows) — Назад/Вперед. `true` — перехоплено.
 *  `code`, а не лише `key`: на українській розкладці `[` — це клавіша `х`. T7 додає сюди ⌘F і ⌘G. */
function navKeys(ev) {
  if (ev.isComposing || ev.altKey || ev.shiftKey || !(ev.metaKey || ev.ctrlKey)) return false;
  if (shellModalOpen()) return false;
  if (ev.code === 'BracketLeft' || ev.key === '[') { if (!ev.repeat) nav.back(); return true; }
  if (ev.code === 'BracketRight' || ev.key === ']') { if (!ev.repeat) nav.forward(); return true; }
  return false;
}
/** Те саме у вікні рамки: `frameCmtKey` виходить на будь-якому модифікаторі, тож окремий захоплювач. */
function frameNavKey(ev) { if (navKeys(ev)) { ev.preventDefault(); ev.stopPropagation(); } }
frame.addEventListener('load', () => {
  try { frame.contentWindow.addEventListener('keydown', frameNavKey, true); } catch (e) { /* чужий документ */ }
});
```
і в глобальному `document.addEventListener('keydown', …)` (той, що починається `const meta = ev.metaKey || ev.ctrlKey; if (meta && ev.key.toLowerCase() === 'k')`) — одразу після блока ⌘K додати:

```js
  if (navKeys(ev)) { ev.preventDefault(); return; }
```

- [ ] **Step 9: Живі тести** — доповнити `tests/live/nav-history.test.mjs`:

```js
const hist = (page) => page.evaluate(() => ({ idx: history.state?.dcn, hash: location.hash }));

test("T5-1: три переходи — три записи; ← → і ⌘[ ⌘] проходять їх; кнопки вимикаються на краях", async (t) => {
  const { page } = await boot(t, 400);
  await page.waitForFunction(() => /p=holovna/.test(location.hash));
  assert.equal(await page.isDisabled('[data-act="navback"]'), true, "на першому записі ← вимкнена");
  assert.equal(await page.isDisabled('[data-act="navfwd"]'), true);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await page.waitForFunction(() => history.state?.dcn === 1);
  await page.click('#bar [data-dd="iter"]');
  await page.click('#bar [data-act="iter"][data-val="it1"]');
  await page.waitForFunction(() => history.state?.dcn === 2 && /it=it1/.test(location.hash));
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForFunction(() => history.state?.dcn === 3 && /m=o/.test(location.hash));
  assert.equal(await page.isDisabled('[data-act="navback"]'), false);

  await page.click('[data-act="navback"]');
  await page.waitForFunction(() => history.state?.dcn === 2 && !/m=o/.test(location.hash));
  await page.waitForSelector("#stage:not([hidden])");
  await page.keyboard.press("Meta+BracketLeft");
  await page.waitForFunction(() => history.state?.dcn === 1 && /it=it2/.test(location.hash));
  await frameReady(page, /it=it2.*page=poshuk/);
  await page.keyboard.press("Control+BracketLeft");
  await page.waitForFunction(() => history.state?.dcn === 0);
  await frameReady(page, /it=it2.*page=holovna/);
  assert.equal(await page.isDisabled('[data-act="navback"]'), true);
  await page.click('[data-act="navfwd"]');
  await page.waitForFunction(() => history.state?.dcn === 1);
  assert.equal(await page.isDisabled('[data-act="navfwd"]'), false);
});

test("T5-2: ⌘[ працює й з фокусом у макеті (окремий захоплювач у рамці)", async (t) => {
  const { page } = await boot(t, 500);
  await page.click('[data-act="page"][data-val="poshuk"]');
  await page.waitForFunction(() => history.state?.dcn === 1);
  await frameReady(page, /page=poshuk/);
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("h1");
  await f.click("h1");
  await page.keyboard.press("Meta+BracketLeft");
  await page.waitForFunction(() => history.state?.dcn === 0);
});

test("T5-3: перехід за посиланням у макеті — запис історії; кожне завантаження рамки — одне (без подвійного reload при Назад)", async (t) => {
  const dir = twoIterations();
  writeFileSync(path.join(dir, "iterations", "it2", "holovna", "index.html"),
    `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><a id="go" href="../poshuk/index.html">go</a></body></html>`);
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + 600 });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  let loads = 0;
  page.on("request", (r) => { if (/\/commented\?/.test(r.url())) loads += 1; });
  await page.goto(`${url}/app/`);
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("#go", { timeout: 20000 });
  await f.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  await f.click("#go");
  await page.waitForFunction(() => history.state?.dcn === 1 && /p=poshuk/.test(location.hash), null, { timeout: 20000 });
  await frameReady(page, /page=poshuk/);
  const before = loads;
  await page.click('[data-act="navback"]');
  await frameReady(page, /page=holovna/);
  await new Promise((r) => setTimeout(r, 1500));
  assert.equal(loads - before, 1, "Назад — рівно одне завантаження рамки");
});

test("T5-4: «Оновити» — у «Макеті» перезавантажує лише макет (адреса й запис історії ті самі)", async (t) => {
  const { page } = await boot(t, 700);
  await frameReady(page, /page=holovna/);
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("h1");
  await f.evaluate(() => { window.__marker = 1; });
  const h0 = await hist(page);
  await page.click('[data-act="navreload"]');
  await f.waitForFunction(() => window.__marker === undefined, null, { timeout: 10000 }).catch(async () => {
    const f2 = await (await page.$("#frame")).contentFrame();
    await f2.waitForFunction(() => window.__marker === undefined);
  });
  assert.deepEqual(await hist(page), h0);
});
```

Додатково — відмова охоронця (проведення; логіку відкоту доводить юніт `tests/nav.test.mjs`). Скопіювати в початок `tests/live/nav-history.test.mjs` потрібні шматки з `tests/live/wizard.test.mjs` (імпорти `guardRealDeai, stop, waitBarReady, goTasks` з `./_spaces-kit.mjs`; функції `wizardModules` (~рядок 102), `boot` без `plant*` (~243), `openFromMenu` (~301), `firstSpace`/`pickAndNext` (~310–330), хелпери `step`, `next`, `pick`, `card`, `field`, константи `MOCKUP`, `SECRET`) і додати тест:

```js
test("T5-5: майстер відмовляє вийти — Назад не змінює ні адресу, ні сторінку майстра; «Відкинути» — виходить", async (t) => {
  /* Простір «Studio» з однією задачею (`studio()` із wizard.test.mjs). Шлях: вид задачі → «Задачі» (запис 1) → майстер на
     кроці 3 з набраним → «Назад». Охоронець питає «Відкинути незбережені налаштування?»; «Скасувати» лишає як було. */
  const m = await bootWizard(t, studio());           // = `boot(t, { spaces })` із wizard.test.mjs
  const { page } = m;
  await page.waitForFunction(() => history.state?.dcn >= 0);
  await page.click('#tabs [data-act="home"]');
  await page.waitForFunction(() => history.state?.dcn === 1 && /h=tasks/.test(location.hash));
  await openFromMenu(page);
  await step(page, 1); await next(page); await step(page, 2);
  await pickAndNext(page, ["memo-publish"]);
  await page.fill(field("memo-publish", "note"), "draft");
  const hashBefore = await page.evaluate(() => location.hash);
  await page.goBack();
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="cancel"]');
  await page.waitForSelector(".cv-ask-scrim", { state: "detached" });
  await page.waitForFunction(() => history.state?.dcn === 1);
  assert.equal(await page.evaluate(() => location.hash), hashBefore, "адреса лишилась поточною");
  assert.equal(await page.locator('#tasks-home .wz[data-step="3"]').count(), 1, "майстер на місці");
  assert.equal(await page.inputValue(field("memo-publish", "note")), "draft", "набране на місці");
  await page.goBack();
  await page.waitForSelector(".cv-ask-scrim");
  await page.click('.cv-ask-scrim button[data-a="discard"], .cv-ask-scrim button[data-a="ok"]');
  await page.waitForFunction(() => history.state?.dcn === 0, null, { timeout: 15000 });
});
```
(Імена кнопок діалогу — як у W5 `wizard.test.mjs` ~рядки 560–585; підставити точний `data-a` «Відкинути» звідти.)

Run (команда з «Спільних правил», `nav-history`): `rc=0`.

- [ ] **Step 10: Сусіди, що торкаються змінених шляхів** — по одному: `comment-goto.test.mjs` (route через `goTo`), `frame-links.test.mjs`, `shell.test.mjs`, `shell-bar.test.mjs`, `settings-nav.test.mjs`, `overview-viewports.test.mjs`. Expected: `rc=0`.

- [ ] **Step 11: Юніт-набір** — `node --test tests/*.test.mjs`. Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add -- tests/bar-nav.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.40): goTo, записи історії, Назад/Вперед/Оновити у смузі, ⌘[ ⌘]; «Показати» коментар через goTo" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/app.js app/bar-model.js app/shell-bar.js app/styles.css app/i18n.js tests/bar-nav.test.mjs tests/live/nav-history.test.mjs
```

---

### Task 6: `app/find-model.js`

**Files:** Create `app/find-model.js`, `tests/find-model.test.mjs`.

Чиста частина: масив текстів вузлів + запит → збіги `{i, start, end}` (індекс вузла, зсуви в оригінальному тексті). Без урахування регістру через `toLocaleLowerCase('uk')`; перерахунок зсувів (малі літери можуть змінити довжину, напр. `İ`); ліміт 1000; пропущені вузли (`null`/порожні) не ламають індекси.

- [ ] **Step 1: Падаючий тест** — `tests/find-model.test.mjs`:

```js
import assert from "node:assert/strict";
import test from "node:test";
import { FIND_LIMIT, SKIP_SELECTORS, SKIP_TAGS, findInTexts } from "../app/find-model.js";

test("порожній запит і порожній вхід — без збігів", () => {
  assert.deepEqual(findInTexts(["abc"], ""), { hits: [], total: 0, capped: false });
  assert.deepEqual(findInTexts([], "a"), { hits: [], total: 0, capped: false });
});

test("без урахування регістру, кирилиця", () => {
  const r = findInTexts(["Пошук по ПОШУКУ"], "пошук");
  assert.deepEqual(r.hits, [{ i: 0, start: 0, end: 5 }, { i: 0, start: 9, end: 14 }]);
});

test("кілька вузлів: збіги з індексом вузла, у порядку документа", () => {
  const r = findInTexts(["one two", "", "two three", "none"], "two");
  assert.deepEqual(r.hits, [{ i: 0, start: 4, end: 7 }, { i: 2, start: 0, end: 3 }]);
  assert.equal(r.total, 2);
});

test("збіги не перекриваються", () => {
  assert.deepEqual(findInTexts(["aaaa"], "aa").hits, [{ i: 0, start: 0, end: 2 }, { i: 0, start: 2, end: 4 }]);
});

test("зсуви лишаються в оригіналі, коли нижній регістр змінює довжину (İ → i̇)", () => {
  const text = "xİy";
  const r = findInTexts([text], "y");
  assert.equal(text.slice(r.hits[0].start, r.hits[0].end), "y");
  const r2 = findInTexts([text], "x");
  assert.equal(text.slice(r2.hits[0].start, r2.hits[0].end), "x");
});

test("ліміт 1000: повертаємо перші 1000, capped=true, total — 1000", () => {
  const r = findInTexts(["a ".repeat(1500)], "a");
  assert.equal(FIND_LIMIT, 1000);
  assert.equal(r.hits.length, 1000);
  assert.equal(r.capped, true);
  assert.equal(r.total, 1000);
});

test("пропущені (null) вузли не зсувають індекси", () => {
  const r = findInTexts([null, "abc", undefined, "abc"], "b");
  assert.deepEqual(r.hits.map((h) => h.i), [1, 3]);
});

test("що пропускаємо при обході: теги й оверлеї (той самий перелік, що в «В Figma»)", () => {
  for (const tag of ["script", "style", "noscript", "template"]) assert.ok(SKIP_TAGS.has(tag), tag);
  for (const sel of ["[data-comment-layer]", "[data-deai-marks]", "[data-canvas-inspector]"]) assert.ok(SKIP_SELECTORS.includes(sel), sel);
});
```

- [ ] **Step 2: Падіння** — `node --test tests/find-model.test.mjs` → FAIL.

- [ ] **Step 3: `app/find-model.js`**

```js
/**
 * Пошук по тексту макета (0.40): чиста частина. DOM (обхід вузлів, діапазони, підсвітка) — `find-bar.js`.
 * `findInTexts(texts, query)` → збіги в ОРИГІНАЛЬНОМУ тексті вузла, без урахування регістру (`toLocaleLowerCase('uk')`).
 * Нижній регістр може змінити довжину (`İ` → `i̇`), тож шукаємо в «згорнутому» рядку й вертаємо зсуви назад через карту.
 */
import { OVERLAY_SELECTORS } from "./figma-capture.js";

export const FIND_LIMIT = 1000;
/** Вузли всередині цих тегів тексту макета не належать. */
export const SKIP_TAGS = new Set(["script", "style", "noscript", "template"]);
/** Наші оверлеї в документі рамки (хост коментатора, позначки помічника, інспектор і тюнер, банер) — той самий перелік, що в «В Figma». */
export const SKIP_SELECTORS = [...OVERLAY_SELECTORS];

function fold(s) {
  let out = "";
  const start = [];   // для кожного коду UTF-16 згорнутого рядка — початок кодової точки в оригіналі
  const end = [];     // …і її кінець
  for (let o = 0; o < s.length;) {
    const ch = String.fromCodePoint(s.codePointAt(o));
    const f = ch.toLocaleLowerCase("uk");
    for (let k = 0; k < f.length; k += 1) { start.push(o); end.push(o + ch.length); }
    out += f;
    o += ch.length;
  }
  return { out, start, end };
}

export function findInTexts(texts, query, limit = FIND_LIMIT) {
  const q = fold(String(query ?? "")).out;
  const hits = [];
  if (!q) return { hits, total: 0, capped: false };
  for (let i = 0; i < texts.length && hits.length < limit; i += 1) {
    const text = texts[i];
    if (!text) continue;
    const f = fold(text);
    for (let at = f.out.indexOf(q); at !== -1 && hits.length < limit; at = f.out.indexOf(q, at + q.length)) {
      hits.push({ i, start: f.start[at], end: f.end[at + q.length - 1] });
    }
  }
  return { hits, total: hits.length, capped: hits.length >= limit };
}
```

- [ ] **Step 4: Зелене** — `node --test tests/find-model.test.mjs` → PASS (8).

- [ ] **Step 5: Commit**

```bash
git add -- app/find-model.js tests/find-model.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.40): find-model — збіги без урахування регістру, зсуви, ліміт 1000" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/find-model.js tests/find-model.test.mjs
```

---

### Task 7: ⌘F — плашка пошуку й підсвітка (РИЗИК: клавіші в двох документах, документ макета не можна міняти)

**Files:**
- Create: `app/find-bar.js`, `tests/live/find.test.mjs`
- Modify: `app/app.js`, `app/styles.css`, `app/i18n.js`

Підсвітка — CSS Custom Highlight API у ВІКНІ РАМКИ (`w.CSS.highlights`, `new w.Highlight`, діапазони з `doc.createRange()` рамки); правила `::highlight()` — через `doc.adoptedStyleSheets` (`new w.CSSStyleSheet()`), тож DOM макета НЕ змінюється. Плашка живе в оболонці. Спека: ⌘F у «Макеті» — плашка справа вгорі, поле, лічильник «i / n» («1000+» при ліміті), ↑ ↓, ✕; Enter / ⇧Enter, Esc; повторний ⌘F — фокус і виділення; ⌘G / ⇧⌘G — коли відкрита (інакше ⌘G лишається «згрупувати»); «Огляд» — фокус у `#pp-filter` (розгорнувши панель); «Задачі» — `#th-q`; в інших місцях не перехоплюємо.

- [ ] **Step 1: i18n** — в кінець `UK` / `EN`:

```js
  /* 0.40: пошук у макеті (⌘F). */
  findPlaceholder: 'Знайти в макеті',
  findPrev: 'Попередній збіг',
  findNext: 'Наступний збіг',
  findClose: 'Закрити пошук',
```
```js
  /* 0.40: find in mockup (⌘F). */
  findPlaceholder: 'Find in mockup',
  findPrev: 'Previous match',
  findNext: 'Next match',
  findClose: 'Close find',
```

- [ ] **Step 2: `app/find-bar.js`**

```js
/**
 * Плашка пошуку по макету (0.40). Живе в оболонці; підсвітка — у вікні рамки через CSS Custom Highlight API:
 * `CSS.highlights` вікна рамки + правила `::highlight()` у `adoptedStyleSheets` ЇЇ документа. ⛔ DOM макета не міняємо
 * (коментатор, інспектор, «В Figma» нічого не бачать): жодних `<mark>`, класів, атрибутів, стилів на вузлах.
 * ⛔ Вузли й конструктори — з ІНШОГО вікна: лише `w.Highlight`/`w.CSSStyleSheet`, жодного `instanceof`.
 */
import { FIND_LIMIT, SKIP_SELECTORS, SKIP_TAGS, findInTexts } from "./find-model.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

const SHEET = "::highlight(deai-find){background-color:#ffe28a;color:#1d2433}::highlight(deai-find-cur){background-color:#ff9f43;color:#1d2433}";
const SKIP_SEL = SKIP_SELECTORS.join(",");

/** Видимі текстові вузли документа рамки: без скриптів/стилів/шаблонів, наших оверлеїв і прихованих елементів. */
function textNodes(doc) {
  const w = doc.defaultView;
  if (!doc.body || !w) return [];
  const walker = doc.createTreeWalker(doc.body, w.NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      const p = n.parentElement;
      if (!p || SKIP_TAGS.has(p.localName) || p.closest(SKIP_SEL)) return w.NodeFilter.FILTER_REJECT;
      if (!n.data.trim() || p.getClientRects().length === 0) return w.NodeFilter.FILTER_REJECT;
      return w.NodeFilter.FILTER_ACCEPT;
    },
  });
  const out = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) out.push(n);
  return out;
}

export function createFindBar({ getFrame, onClose = () => {}, delay = 120 }) {
  const el = document.createElement("div");
  el.id = "find";
  el.setAttribute("role", "search");
  el.hidden = true;
  el.innerHTML = `<input id="find-q" type="text" spellcheck="false" autocomplete="off" aria-label="${t("findPlaceholder")}" placeholder="${t("findPlaceholder")}">`
    + `<span id="find-n" class="find-n" aria-live="polite"></span>`
    + `<button class="ctl ctl--icon find-prev" data-find="prev" aria-label="${t("findPrev")}">${ico("chevdown", 16)}</button>`
    + `<button class="ctl ctl--icon" data-find="next" aria-label="${t("findNext")}">${ico("chevdown", 16)}</button>`
    + `<button class="ctl ctl--icon" data-find="close" aria-label="${t("findClose")}">${ico("x", 16)}</button>`;
  document.body.appendChild(el);
  const input = el.querySelector("#find-q");
  const count = el.querySelector("#find-n");
  let nodes = [], ranges = [], cur = -1, capped = false, timer = 0, sheet = null, sheetDoc = null;

  const frameDoc = () => { try { return getFrame()?.contentDocument || null; } catch (e) { return null; } };
  const frameWin = () => frameDoc()?.defaultView || null;

  function clearHighlight() {
    try {
      const w = sheetDoc?.defaultView;
      w?.CSS?.highlights?.delete("deai-find");
      w?.CSS?.highlights?.delete("deai-find-cur");
      if (sheet && sheetDoc) sheetDoc.adoptedStyleSheets = sheetDoc.adoptedStyleSheets.filter((s) => s !== sheet);
    } catch (e) { /* документ уже мертвий */ }
    sheet = null; sheetDoc = null;
  }
  function paint(doc) {
    const w = doc.defaultView;
    if (!w?.CSS?.highlights || !w.Highlight || !w.CSSStyleSheet) return;
    if (sheetDoc !== doc) {
      clearHighlight();
      sheet = new w.CSSStyleSheet();
      sheet.replaceSync(SHEET);
      doc.adoptedStyleSheets = [...doc.adoptedStyleSheets, sheet];
      sheetDoc = doc;
    }
    w.CSS.highlights.set("deai-find", new w.Highlight(...ranges));
    w.CSS.highlights.set("deai-find-cur", new w.Highlight(...(cur >= 0 ? [ranges[cur]] : [])));
  }
  function label() {
    const q = input.value;
    count.classList.toggle("none", !!q && ranges.length === 0);
    count.textContent = !q ? "" : ranges.length ? `${cur + 1} / ${capped ? `${FIND_LIMIT}+` : ranges.length}` : "0 / 0";
  }
  function show() {
    const doc = frameDoc();
    if (doc && ranges.length) {
      paint(doc);
      try { ranges[cur].startContainer.parentElement?.scrollIntoView({ block: "center" }); } catch (e) { /* вузол зник */ }
    }
    label();
  }
  function run() {
    clearTimeout(timer);
    timer = 0;   // відкладений пошук виконано: наступний Enter — це «наступний збіг», а не повторний пошук
    const doc = frameDoc();
    nodes = []; ranges = []; cur = -1; capped = false;
    if (!doc || !input.value) { clearHighlight(); label(); return; }
    nodes = textNodes(doc);
    const r = findInTexts(nodes.map((n) => n.data), input.value);
    capped = r.capped;
    ranges = r.hits.map((h) => { const x = doc.createRange(); x.setStart(nodes[h.i], h.start); x.setEnd(nodes[h.i], h.end); return x; });
    cur = ranges.length ? 0 : -1;
    if (!ranges.length) clearHighlight();
    show();
  }
  function step(d) {
    if (!ranges.length) return;
    cur = (cur + d + ranges.length) % ranges.length;
    show();
  }
  function close() {
    clearTimeout(timer);
    clearHighlight();
    nodes = []; ranges = []; cur = -1;
    if (el.hidden) return;
    el.hidden = true;
    onClose();
  }
  function open() {
    el.hidden = false;
    input.focus();
    input.select();
    if (input.value) run();
  }

  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, delay); });
  input.addEventListener("keydown", (ev) => {
    if (ev.isComposing) return;
    if (ev.key === "Enter") { ev.preventDefault(); if (timer) run(); else step(ev.shiftKey ? -1 : 1); }
    else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); close(); }
  });
  el.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-find]");
    if (!b) return;
    if (b.dataset.find === "prev") step(-1);
    else if (b.dataset.find === "next") step(1);
    else close();
  });

  return { open, close, next: () => step(1), prev: () => step(-1), rerun: () => { if (!el.hidden) run(); }, isOpen: () => !el.hidden, el };
}
```

(`Enter` одразу виконує відкладений пошук, якщо він ще чекає (`timer`), інакше переходить до наступного збігу.)

- [ ] **Step 3: CSS** — у `app/styles.css` після блока `#panel-resize` (T2):

```css
/* Плашка пошуку в макеті (0.40, `app/find-bar.js`): справа вгорі над сценою; зсувається лівіше правих панелей. */
#find{position:fixed;top:calc(var(--h-top) + 8px);right:12px;z-index:var(--z-widget);display:flex;align-items:center;gap:2px;
  padding:4px 4px 4px 10px;background:var(--s2);border:1px solid var(--line2);border-radius:var(--r-lg);
  box-shadow:0 8px 24px rgba(0,0,0,.35)}
#find[hidden]{display:none}
body.with-insp #find,body.with-cmt #find,body.with-mod #find,body.with-hist #find{right:calc(var(--insp-w) + 12px)}
#find input{width:220px;height:var(--h-sm);background:none;border:0;outline:0;color:var(--hi);font:inherit}
#find input::placeholder{color:var(--dim)}
.find-n{min-width:46px;padding-right:4px;text-align:right;color:var(--dim);font-size:12px;font-variant-numeric:tabular-nums}
.find-n.none{color:var(--bad-ink)}
#find .ctl--icon{width:var(--h-sm);height:var(--h-sm)}
.find-prev .ico{transform:rotate(180deg)}
```
(Якщо `--bad-ink` недоречний на тлі `--s2` для контрасту — взяти токен, який `css-guards` приймає для тексту помилки на `--s2` (`grep -n "bad" tests/css-guards.test.mjs`).)

- [ ] **Step 4: Проводка в `app/app.js`.** Імпорти:

```js
import { createFindBar } from './find-bar.js';
```

Створення й розбір клавіш — розширити `navKeys` (T5) і додати `find`. Біля `frameCmtKey` (там, де `navKeys`) **замінити** функцію `navKeys` на:

```js
const find = createFindBar({ getFrame: () => frame });
/** ⌘F: де саме шукати. «Макет» — плашка; «Огляд» — фільтр сторінок (розгорнувши панель); «Задачі» — пошук задач; інакше не наше. */
function findHere() {
  if (homeOpen) {
    if (homePage !== 'tasks') return false;
    const q = document.getElementById('th-q');
    if (!q) return false;
    q.focus(); q.select();
    return true;
  }
  if (mode === 'canvas') {
    if (panelCollapsed) setPanelCollapsed(false);
    const f = document.getElementById('pp-filter');
    if (!f) return false;
    f.focus(); f.select();
    return true;
  }
  if (!curTask) return false;
  find.open();
  return true;
}
/** Закрити плашку, коли «Макет» пішов (Огляд, «Задачі»): її документа вже нема. Кличе `render()` і `enterHome`. */
function findGuard() { if (find.isOpen() && (mode === 'canvas' || homeOpen)) find.close(); }
/** Клавіші навігації й пошуку (0.40), спільні для оболонки й вікна рамки. `true` — перехоплено. `code`, а не лише `key`: на
 *  українській розкладці `[` — клавіша `х`, `F` — `а`, `G` — `п`. ⌘G працює лише коли плашка відкрита — інакше лишається
 *  «згрупувати» в дереві (обробник нижче в глобальному keydown). */
function navKeys(ev) {
  if (ev.isComposing || ev.altKey || !(ev.metaKey || ev.ctrlKey)) return false;
  if (shellModalOpen()) return false;
  const k = (ev.key || '').toLowerCase();
  if (!ev.shiftKey && (ev.code === 'BracketLeft' || ev.key === '[')) { if (!ev.repeat) nav.back(); return true; }
  if (!ev.shiftKey && (ev.code === 'BracketRight' || ev.key === ']')) { if (!ev.repeat) nav.forward(); return true; }
  if (!ev.shiftKey && (ev.code === 'KeyF' || k === 'f')) return findHere();
  if ((ev.code === 'KeyG' || k === 'g') && find.isOpen()) { if (!ev.repeat) (ev.shiftKey ? find.prev() : find.next()); return true; }
  return false;
}
```
Хуки: у `render()` одразу після `nav.sync();` додати `findGuard();`; в `enterHome` після `nav.sync();` теж `findGuard();`. А в обробнику `load` рамки (окремий слухач з T5 `frame.addEventListener('load', …frameNavKey…)`) доповнити:

```js
frame.addEventListener('load', () => {
  try { frame.contentWindow.addEventListener('keydown', frameNavKey, true); } catch (e) { return; }   // чужий документ
  if (find.isOpen()) find.rerun();   // зміна сторінки чи перезавантаження макета — шукаємо той самий запит заново
});
```
(це заміна слухача з T5 `navKeys`-кроку, а не другий.) Порядок у глобальному keydown: `if (navKeys(ev)) { ev.preventDefault(); return; }` стоїть ДО гілки ⌘G «згрупувати» (T5 вставила його одразу після ⌘K) — гілка «згрупувати» не чіпається: при закритій плашці `navKeys` для ⌘G повертає `false` і подія доходить до неї як і раніше.

- [ ] **Step 5: Падаючий живий тест** — `tests/live/find.test.mjs`:

```js
/**
 * ⌘F по макету (0.40): плашка, лічильник, Enter/⇧Enter/⌘G, Esc, підсвітка через CSS.highlights у вікні рамки БЕЗ жодної
 * мутації DOM макета (MutationObserver у рамці мовчить), новий пошук після зміни сторінки, «Огляд» → фільтр панелі,
 * ⌘G «згрупувати» не зламано (плашка закрита).
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 53000;
const VIEW = { width: 1440, height: 900 };
const html = (id) => id === "holovna"
  ? `<!DOCTYPE html><html><head><meta charset="utf-8"><style>.hid{display:none}</style></head><body style="margin:40px">
<h1>Головна сторінка</h1><p>Слово слово СЛОВО</p><p class="hid">слово приховане</p><script>var слово = 1</script>
<div style="height:1600px"></div><p id="far">слово внизу</p></body></html>`
  : `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>Пошук</h1><p>інше слово тут</p></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

async function boot(t, off) {
  const { dir } = taskFixture({ html });
  const { child, url } = await startServer(dir, { portBase: PORT_BASE + off });
  t.after(() => child.kill());
  const page = await browser.newPage({ viewport: VIEW });
  t.after(() => page.close());
  await page.goto(`${url}/app/`);
  const f = await (await page.$("#frame")).contentFrame();
  await f.waitForSelector("#far", { timeout: 20000 });
  await f.waitForFunction(() => window.CommentLayer && window.CommentLayer._inited, null, { timeout: 20000 });
  return { page, f };
}
const counter = (page) => page.$eval("#find-n", (e) => e.textContent);
const hits = (f) => f.evaluate(() => [...CSS.highlights.get("deai-find")].map((r) => r.toString()));
const curHit = (f) => f.evaluate(() => [...CSS.highlights.get("deai-find-cur")].map((r) => r.toString()));

test("1: ⌘F з фокусом в оболонці: плашка, лічильник, Enter/⇧Enter/⌘G, Esc знімає підсвітку", async (t) => {
  const { page, f } = await boot(t, 0);
  await page.keyboard.press("Control+KeyF");
  await page.waitForSelector("#find:not([hidden])");
  assert.equal(await page.evaluate(() => document.activeElement.id), "find-q");
  await page.keyboard.type("слово");
  await page.waitForFunction(() => document.getElementById("find-n").textContent === "1 / 4");
  assert.deepEqual((await hits(f)).map((s) => s.toLowerCase()), ["слово", "слово", "слово", "слово"], "4 видимі збіги: без display:none і без <script>");
  await page.keyboard.press("Enter");
  assert.equal(await counter(page), "2 / 4");
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.press("Shift+Enter");
  assert.equal(await counter(page), "4 / 4", "⇧Enter ходить по колу назад");
  assert.equal((await curHit(f)).length, 1);
  await f.waitForFunction(() => { const r = document.getElementById("far").getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
  await page.keyboard.press("Control+KeyG");
  assert.equal(await counter(page), "1 / 4");
  await page.keyboard.press("Control+Shift+KeyG");
  assert.equal(await counter(page), "4 / 4");
  await page.keyboard.press("Escape");
  await page.waitForSelector("#find", { state: "hidden" });
  assert.equal(await f.evaluate(() => CSS.highlights.has("deai-find")), false, "підсвітку знято");
});

test("2: ⌘F з фокусом У МАКЕТІ відкриває плашку; повторний ⌘F виділяє текст у полі", async (t) => {
  const { page, f } = await boot(t, 100);
  await f.click("h1");
  await page.keyboard.press("Control+KeyF");
  await page.waitForSelector("#find:not([hidden])");
  await page.keyboard.type("сторінка");
  await page.waitForFunction(() => document.getElementById("find-n").textContent === "1 / 1");
  await page.keyboard.press("Control+KeyF");
  assert.equal(await page.evaluate(() => { const i = document.getElementById("find-q"); return i.selectionStart === 0 && i.selectionEnd === i.value.length; }), true);
});

test("3: пошук нічого не міняє в DOM макета (MutationObserver у рамці мовчить), нема збігів — «0 / 0»", async (t) => {
  const { page, f } = await boot(t, 200);
  await f.evaluate(() => {
    window.__muts = 0;
    new MutationObserver((r) => { window.__muts += r.length; }).observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
  });
  await page.keyboard.press("Control+KeyF");
  await page.keyboard.type("слово");
  await page.waitForFunction(() => document.getElementById("find-n").textContent === "1 / 4");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Control+KeyF");
  await page.keyboard.type("ЯЯЯ");
  await page.waitForFunction(() => document.getElementById("find-n").textContent === "0 / 0");
  await page.keyboard.press("Escape");
  assert.equal(await f.evaluate(() => window.__muts), 0, "жодної мутації DOM макета від пошуку");
});

test("4: зміна сторінки при відкритій плашці — той самий запит шукається заново", async (t) => {
  const { page } = await boot(t, 300);
  await page.keyboard.press("Control+KeyF");
  await page.keyboard.type("слово");
  await page.waitForFunction(() => document.getElementById("find-n").textContent === "1 / 4");
  await page.click('[data-act="page"][data-val="poshuk"]');
  await page.waitForFunction(() => document.getElementById("find-n").textContent === "1 / 1", null, { timeout: 15000 });
});

test("5: «Огляд» — ⌘F ставить фокус у фільтр сторінок, плашки нема; ⌘G групує як і раніше, коли плашка закрита", async (t) => {
  const { page } = await boot(t, 400);
  await page.click('#bar [data-act="mode"][data-val="overview"]');
  await page.waitForSelector("#canvas:not([hidden])");
  await page.keyboard.press("Control+KeyF");
  assert.equal(await page.evaluate(() => document.activeElement.id), "pp-filter");
  assert.equal(await page.evaluate(() => document.getElementById("find").hidden), true);
  await page.click('#bar [data-act="mode"][data-val="layout"]');
  await page.waitForSelector("#stage:not([hidden])");
  await page.click('[data-act="page"][data-val="holovna"]');
  await page.keyboard.press("Control+KeyG");   // плашка закрита: ⌘G — «згрупувати» (нема вибраних — подія не перехоплена, помилок нема)
  assert.equal(await page.evaluate(() => document.getElementById("find").hidden), true);
});

test("6: «Задачі» — ⌘F ставить фокус у пошук задач", async (t) => {
  const { page } = await boot(t, 500);
  await page.click('#tabs [data-act="home"]');
  await page.waitForSelector("#th-q");
  await page.keyboard.press("Control+KeyF");
  assert.equal(await page.evaluate(() => document.activeElement.id), "th-q");
});
```

Run (команда з «Спільних правил», `find`): `rc=0`. Якщо тест 3 бачить мутації — шукати їх у `find-bar.js` (єдине, що торкається рамки: `adoptedStyleSheets`, `CSS.highlights`, `createRange`; жодне не повинно ловитись `MutationObserver`).

- [ ] **Step 6: Регресія навколо клавіш** — по одному: `shell-typing.test.mjs`, `shell-palette.test.mjs`, `panel-tree.test.mjs` (⌘G «згрупувати»), `comments-panel.test.mjs`, `inspector.test.mjs`. Expected: `rc=0`.

- [ ] **Step 7: Юніт-набір** — `node --test tests/*.test.mjs` → PASS.

- [ ] **Step 8: Commit**

```bash
git add -- app/find-bar.js tests/live/find.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(0.40): ⌘F — пошук по макету (плашка, CSS Custom Highlight у вікні рамки, ⌘G), «Огляд» і «Задачі»" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/find-bar.js app/app.js app/styles.css app/i18n.js tests/live/find.test.mjs
```

---

### Task 8: перемикач «Макет / Огляд» не стрибає (РИЗИК: причина не доведена — спершу вимір)

**Files:** Create `tests/live/bar-centre.test.mjs`; Modify (після виміру) `app/shell-bar.js`, `app/styles.css`, золоті знімки `tests/fixtures/legacy-golden/bar-*.html`.

Гіпотеза (з коду): смуга вже `grid 1fr auto 1fr`, тож бічні зони центр не зсувають; центральна зона (`.zone-2`) = `[Макет|Огляд][Сітка|Флоу — лише «Огляд»][ширини; поле довільної ширини — лише «Макет»][⋯]`, тобто ЇЇ ширина різна в двох режимах, а `justify-content:center` ставить сегмент режиму не в центр, а на (центр − ширина решти / 2). Це і є «стрибок». Гіпотезу доводимо вимірюванням ДО правки.

- [ ] **Step 1: Вимір (тест, що фіксує симптом)** — `tests/live/bar-centre.test.mjs`:

```js
/**
 * Центр сегмента «Макет / Огляд» (0.40): однаковий в обох режимах і не залежить від кнопок ← → ⟳ зліва й від набору контролів
 * справа. Вимір, а не здогад: тест написано ДО правки й упав на ній (дельта = половина різниці ширин решти зони 2).
 */
import assert from "node:assert/strict";
import test from "node:test";
import { chromium } from "playwright";
import { startServer, taskFixture } from "./fixture.mjs";

const PORT_BASE = 54000;
const html = (id) => `<!DOCTYPE html><html><head><meta charset="utf-8"></head><body><h1>${id}</h1></body></html>`;

let browser;
test.before(async () => { browser = await chromium.launch(); });
test.after(async () => { await browser?.close(); });

const metrics = (page) => page.evaluate(() => {
  const r = (s) => document.querySelector(s)?.getBoundingClientRect();
  const bar = r("#bar .bar"), seg = r('#bar [data-seg="mode"]'), z2 = r("#bar .zone-2");
  const kids = [...document.querySelectorAll("#bar .zone-2 > *")].map((e) => Math.round(e.getBoundingClientRect().width));
  return {
    cx: seg.left + seg.width / 2, barCx: bar.left + bar.width / 2,
    z2w: Math.round(z2.width), kids,
    overflow: document.querySelector("#bar .bar").scrollWidth - document.querySelector("#bar .bar").clientWidth,
  };
});

for (const width of [1440, 1280]) {
  test(`центр сегмента «Макет/Огляд» однаковий в обох режимах і збігається з центром смуги (${width})`, async (t) => {
    const { dir } = taskFixture({ html });
    const { child, url } = await startServer(dir, { portBase: PORT_BASE + (width === 1440 ? 0 : 100) });
    t.after(() => child.kill());
    const page = await browser.newPage({ viewport: { width, height: 800 } });
    t.after(() => page.close());
    await page.goto(`${url}/app/`);
    await page.waitForSelector('#bar [data-seg="mode"]');
    const layout = await metrics(page);
    await page.click('#bar [data-act="mode"][data-val="overview"]');
    await page.waitForSelector('#bar [data-seg="view"]');
    const overview = await metrics(page);
    console.log(JSON.stringify({ width, layout, overview }));   // вимір для звіту виконавця
    assert.ok(Math.abs(layout.cx - overview.cx) < 1, `сегмент зсунувся на ${Math.abs(layout.cx - overview.cx).toFixed(1)}px між режимами`);
    assert.ok(Math.abs(layout.cx - layout.barCx) < 1.5, `не в центрі смуги: ${layout.cx} проти ${layout.barCx}`);
    assert.ok(layout.overflow <= 0 && overview.overflow <= 0, "смуга не переповнюється");
  });
}
```

Run (команда з «Спільних правил», `bar-centre`) ДО будь-якої правки CSS/розмітки.
Expected: **FAIL** з різницею, ≈ половині різниці `z2w` між режимами (рядок `console.log` покаже `z2w` і ширини дітей). Записати числа в повідомлення коміту. Якщо різниці НЕМАЄ (тест зелений) — гіпотеза хибна: не правити розкладку, а виміряти ще раз з нав. кнопками (T5 уже в гілці) і шукати інший чинник (`getComputedStyle(.bar).gridTemplateColumns`, фактичні ширини колонок); результат записати у звіт і зупинитись для рішення контролера.

- [ ] **Step 2: Виправлення (якщо гіпотеза підтверджена).** Ціль: сегмент режиму НЕ рухається від решти зони 2. Підхід — решта контролів (`view`, `vp`, `⋯`) виходить із потоку центру: сегмент режиму — єдина «автоширинна» центральна колонка, а решта стоїть поруч із нею в тій самій 1fr-колонці справа.

`app/shell-bar.js`, `zone2HTML`: замінити

```js
  return `${seg(model, "mode")}${seg(model, "view")}${vpSeg(model)}${more}`;
```
на
```js
  /* 0.40: сегмент режиму — єдиний у центрі смуги (ширина решти зони різна в «Макеті» й «Огляді» — через неї він «стрибав»);
     решта контролів — поруч у лівому краї правої колонки (`.zone-2x`). */
  return `${seg(model, "mode")}<div class="zone-2x">${seg(model, "view")}${vpSeg(model)}${more}</div>`;
```

`app/styles.css`, після `.zone-3{justify-content:flex-end}`:

```css
/* 0.40: центр смуги — лише сегмент режиму (`.zone-2` у центральній колонці `auto` несе тільки його). `.zone-2x` (Сітка/Флоу,
   ширини, «⋯») виходить із потоку й стоїть упритул праворуч від сегмента, у просторі правої колонки, — тому різна ширина решти
   в «Макеті» й «Огляді» сегмент не зсуває. */
.zone-2{position:relative}
.zone-2x{position:absolute;left:calc(100% + 10px);top:0;bottom:0;display:flex;align-items:center;gap:6px;white-space:nowrap}
```

Перевірити геометрію: `.zone-2x` НЕ перекриває зону 3 на 1024 / 1280 / 1440 (див. Step 3). Контейнерні запити (`TIERS`) уже ховають підписи й переносять ширини в «⋯» на вузьких смугах — якщо на якійсь ширині перекриття лишається, підняти відповідний поріг у `TIERS` (`app/bar-model.js`) на виміряну величину й оновити `tests/bar-model.test.mjs`; вибір записати в CHANGELOG (T10).

- [ ] **Step 3: Геометрія без перекриття** — додати в `tests/live/bar-centre.test.mjs` тест:

```js
for (const width of [1024, 1280, 1440]) {
  test(`решта контролів зони 2 не налазить на зону 3 (${width})`, async (t) => {
    const { dir } = taskFixture({ html });
    const { child, url } = await startServer(dir, { portBase: PORT_BASE + 200 + (width % 100) * 3 });
    t.after(() => child.kill());
    const page = await browser.newPage({ viewport: { width, height: 800 } });
    t.after(() => page.close());
    await page.goto(`${url}/app/`);
    await page.waitForSelector('#bar [data-seg="mode"]');
    for (const mode of ["layout", "overview"]) {
      await page.click(`#bar [data-act="mode"][data-val="${mode}"]`);
      await page.waitForFunction((m) => document.querySelector(`#bar [data-act="mode"][data-val="${m}"]`)?.getAttribute("aria-pressed") === "true", mode);
      const g = await page.evaluate(() => {
        const x = document.querySelector("#bar .zone-2x")?.getBoundingClientRect();
        const z3 = [...document.querySelectorAll("#bar .zone-3 > *")].map((e) => e.getBoundingClientRect()).filter((r) => r.width > 0);
        return { right: x ? x.right : 0, z3left: z3.length ? Math.min(...z3.map((r) => r.left)) : 1e9,
          bar: document.querySelector("#bar .bar").getBoundingClientRect().right };
      });
      assert.ok(g.right <= g.z3left + 0.5, `${mode}@${width}: зона 2x (${g.right}) налазить на зону 3 (${g.z3left})`);
      assert.ok(g.right <= g.bar, `${mode}@${width}: зона 2x вилізла за смугу`);
    }
  });
}
```

Run (`bar-centre`): `rc=0`.

- [ ] **Step 4: Знімки й сусіди.** Розмітка смуги змінилась свідомо (обгортка `.zone-2x`), отже золоті знімки ЛІГИ треба перезняти ЯВНО й переглянути diff очима (це санкціонований шлях з `tests/legacy-golden.test.mjs`: «ЛІГА змінилась свідомо → перезняти»):

Run: `UPDATE_GOLDEN=1 node --test tests/legacy-golden.test.mjs && git diff --stat tests/fixtures/legacy-golden && git diff tests/fixtures/legacy-golden | head -60`
Expected: у diff — ЛИШЕ обгортка `<div class="zone-2x">…</div>` навколо `view`/`vp`/`⋯`, жодних інших змін. Потім: `node --test tests/legacy-golden.test.mjs tests/shell-bar.test.mjs tests/bar-model.test.mjs tests/bar-nav.test.mjs tests/ext-bar.test.mjs tests/css-guards.test.mjs` → PASS.

Живі, чутливі до смуги, по одному: `bar-narrow.test.mjs`, `shell.test.mjs`, `shell-bar.test.mjs`, `tabs.test.mjs`, `overview-viewports.test.mjs`. Expected: `rc=0`.

- [ ] **Step 5: Commit**

```bash
git add -- tests/live/bar-centre.test.mjs
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "fix(0.40): сегмент «Макет/Огляд» не стрибає — решта контролів зони 2 винесена з центру (вимір у тесті)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- app/shell-bar.js app/styles.css tests/live/bar-centre.test.mjs tests/fixtures/legacy-golden
```

---

### Task 9: тема довідки агента про формат адреси

**Files:** Create `docs/agents/links.md`, `tests/test_agent_links_topic.py`.

Теми довідки — `docs/agents/<тема>.md`, авто-виявляються (`app/agents_md.py`, `topics()`), індекс у блоці `AGENTS.md` оновлюється тим самим механізмом (хеш змісту, 0.37.0). Файл тем — англійською; перший рядок `# …`, другий (≤120 символів) — рядок індексу. Роутів нових нема (охоронець покриття `tests/test_agent_guide_coverage.py` не зачеплено).

- [ ] **Step 1: Падаючий тест** — `tests/test_agent_links_topic.py` (парний інваріант: ключі в темі = ключі моделі адреси):

```python
"""Тема `links` довідки агента описує формат адреси `/app/#…` і не розходиться з `app/location-model.js`."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


class LinksTopic(unittest.TestCase):
    def test_topic_exists_with_index_line(self):
        lines = read('docs', 'agents', 'links.md').split('\n')
        self.assertTrue(lines[0].startswith('# '))
        self.assertTrue(0 < len(lines[1].strip()) <= 120, 'line 2 is the index line, up to 120 chars')

    def test_documents_every_key_of_the_location_model(self):
        model = read('app', 'location-model.js')
        keys = re.search(r'LOC_KEYS\s*=\s*\[([^\]]*)\]', model).group(1)
        names = re.findall(r'"([a-z]+)"', keys) + ['m', 'v', 'h']
        text = read('docs', 'agents', 'links.md')
        for k in names:
            self.assertRegex(text, r'`%s=' % re.escape(k), f'key {k}= not documented in links.md')

    def test_shows_the_address_shape(self):
        text = read('docs', 'agents', 'links.md')
        self.assertIn('/app/#', text)
        self.assertIn('encodeURIComponent', text)


if __name__ == '__main__':
    unittest.main()
```

Run: `python3 -B -m unittest tests.test_agent_links_topic` → FAIL (нема файла).

- [ ] **Step 2: `docs/agents/links.md`**

```markdown
# Links
Give the owner a link to a place in the canvas: space, task, iteration, page, mode — «here is where I worked».

The canvas window keeps its current place in the address, so a place can be shared as a link and the canvas opens right
there (also after a reload). The address is `/app/` of the running Deai plus a hash:

    http://127.0.0.1:8765/app/#sp=<space-id>&t=<task-id>&it=<iteration-id>&p=<page-id>

Keys (all optional; unknown keys are ignored; every value goes through `encodeURIComponent`):

- `sp=` the space id (`GET /api/spaces`); `t=` the task id (`GET /api/tasks`); `it=` the iteration id, e.g. `it2`;
- `p=` the page id from the iteration's `pages.json` (the same key as in a published preview link `#p=<page-id>`);
- `st=` a state of the page, only together with `p=`;
- `m=o` — «Огляд» (the overview canvas); without `m` it is «Макет». `v=flow` — the flow view of the overview, only with `m=o`;
- `h=tasks` or `h=settings` — the «Задачі» screen or the settings over the task.

An id that no longer exists is not an error: the canvas silently opens the nearest place (the last iteration, the first page).
Compose the link from ids you read through the API, never from names; the port is the one Deai runs on (default 8765).
```

- [ ] **Step 3: Зелене** — `python3 -B -m unittest tests.test_agent_links_topic tests.test_agent_guide tests.test_agent_guide_coverage tests.test_agents_md` → OK. Якщо `test_agent_guide` скаржиться, що блок > 6 KB — скоротити рядок 2 теми, не міняючи формату.

- [ ] **Step 4: Живий `agents-md`** (довідка оновлюється тим самим механізмом): `tests/live/agents-md.test.mjs` → `rc=0`.

- [ ] **Step 5: Commit**

```bash
git add -- docs/agents/links.md tests/test_agent_links_topic.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "docs(0.40): тема довідки агента «links» — формат адреси /app/#… (парний тест із location-model)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/agents/links.md tests/test_agent_links_topic.py
```

---

### Task 10: реліз 0.40.0 (контролер)

**Files:** `CHANGELOG.md`, `package.json` (версія), `VERSION`-файли за звичайним релізним проходом.

Не виконується виконавцем. Контролер: фінальний ревʼю всієї гілки (особливо T4–T5: гонки `render()`, подвійне завантаження рамки, відмова охоронця); повний `npm test` і живий прогін послідовно (`test:live`, по одному файлу під замком — паралельні сусіди дають фальшиві падіння); перевірка «проти живого» на релізі (запуск канваса з чистим env, відкриття `/app/#…`, ⌘[ ⌘] ⌘F, перетягування краю панелі); запис у CHANGELOG (повні назви й ширина, місце в адресі, Назад/Вперед/Оновити, ⌘F, центр перемикача — з виміряною причиною зі T8; тема `links` для агента); підняття версії; тег. Перепублікація превʼю не потрібна (оболонка превʼю не змінювалась).

---

## Самоперевірка плану

**Покриття спеки (розділ → задача):**
- §1 ручка, межі, подвійний клік, клавіатура, збереження, без transition, `fitAll`, підказка (`data-tip`/`.row-name`, 500 мс, умови приховування, без `title`) → T1, T2.
- §2 адреса й модель (`parse/format/same`, кодування, невідомі ключі) → T3; одне місце запису, `pushState`/`replaceState` за наміром, список переходів і не-переходів → T4 (`sync`/`want`) і T5 (проводка намірів); старт і ⌘R → T4 (`bootPlace`, `applyBootPlace`); `popstate` → `goTo`, `history.state`, відмова охоронця і відкіт → T4 (`nav.js`) + T5 (`goTo`); кнопки ← → ⟳ → T5; ⌘[ ⌘] у оболонці й у рамці → T5; `goToComment` через `goTo` → T5; `sw.js` + hash → T4 (T4-4).
- §3 ⌘F: плашка, лічильник, ліміт «1000+», підсвітка без зміни DOM, пропуски вузлів, ⌘G, «Огляд», «Задачі», повторний пошук після зміни сторінки → T6, T7.
- §4 центр перемикача (спершу вимір) → T8.
- §5 гайд агента → T9. Тести спеки: юніти (T1–T3, T6), живі 1–4 (T1/T2, T4/T5, T7, T8), охоронці CSS (T2).

**Ризики, яких спека не передбачила (знайдені в коді):**
1. `render()` присвоює `frame.src` щоразу — тому `goTo` не може викликати `BAR_ACTIONS.*` підряд (подвійне завантаження); він повторює стан і робить один `render()` (T5), а `BAR_ACTIONS.mode` розщеплено на `setModeState`.
2. `bootPlace` мусить перемкнути задачу на сервері ДО `loadTune()`, інакше пакет тюнера береться від чужої задачі.
3. У «Огляді» `PANEL_ACTIONS.page` не робить `render()` — адреса без явного `nav.sync()` не пішла б за вибором сторінки (T5 це робить).
4. Золоті знімки ЛІГИ (`tests/legacy-golden`) побайтно порівнюють розмітку смуги: кнопки навігації додаються лише за наявності `state.nav` (знімки не зсуваються); обгортка `.zone-2x` у T8 вимагає свідомого `UPDATE_GOLDEN=1` з переглядом diff.
5. Смуга вже `1fr auto 1fr`; ймовірна причина стрибка — різна ширина решти центральної зони (поле довільної ширини лише в «Макеті», «Сітка/Флоу» лише в «Огляді»), а не бічні зони; а винесення решти з центру забирає місце в правій колонці — тому перевірка перекриття на 1024/1280/1440.
6. Кнопки ← → ⟳ за спекою — лише на смузі задачі; на екрані «Задачі» їх нема (через `bar-narrow` на 320–375), але ⌘[ ⌘] працюють скрізь — тож повернутись із «Задач» можна клавішею.
7. Майстер не має «відмовили/дозволили» в результаті `requestExit()` — відмову `goTo` визначає за тим, що майстер лишився відкритим.
8. Відновлення в «Огляд» робить другий `render()` після `freshen()` (як вхід кнопкою) — лише для `m=o`.

**Пункти спеки без окремої задачі:** жодного. Перепублікацію превʼю й перелік клавіш у довідці-оверлеї (`openKeys`) спека не просить — не робимо.
