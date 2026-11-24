# М2: помічник ядра для модулів — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** інструмент модуля з дозволами `page` дивиться, помічає, тимчасово змінює й слухає сторінку макета через
помічника ядра; код модуля в документ макета не потрапляє.

**Architecture:** чисті правила (`app/page-rules.js`) + DOM-помічник у вікні канваса над документом рамки
(`app/page-agent.js`) + методи `page.*` у наявному мості М1 (`app/module-host.js` ↔ `app/module-kit/bridge.js`) +
проводка в `app/app.js`. Маніфест і довіра — `app/deai_modules.py`, `app/trust-view.js`.

**Tech Stack:** vanilla JS ES modules, Python stdlib, `node --test`, Playwright (живі тести).

**Спека:** `docs/superpowers/specs/2026-11-24-modules-m2-page-helper-design.md` (погоджено 24.11.2026). Реліз — 0.39.0 (0.38.0 зайняв реліз хука Stop).

**Рівень строгості:** повний для T2–T7 (межа модуль ↔ макет), середній для T8–T9. Один виконавець за раз, ревʼю після
кожної задачі.

**Спільні правила для кожної задачі:** `python3 -B`; коміти лише
`git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…" -m "Co-Authored-By: …" -- <шляхи>`;
живі тести — по одному файлу під замком `/private/tmp/deai-live.lock` із тимчасовим `HOME`; без абсолютних локальних
шляхів, справжніх імен і внутрішніх хостів у коді, тестах, документах.

---

## Карта файлів

| Файл | Задача | Відповідальність |
|---|---|---|
| `app/deai_modules.py` | T1 | `page` у маніфесті інструмента, у `/api/module-ext` і в зведенні довіри |
| `app/page-rules.js` (нове) | T2 | чисті правила: дозволи методів, ліміти, атрибути, класи, стилі, журнал змін |
| `app/page-agent.js` (нове) | T3–T5 | DOM-помічник над переданим документом |
| `tests/live/page-agent.test.mjs` (нове) | T3–T5 | помічник у справжньому Chromium: батьківська сторінка + рамка, без сервера канваса |
| `app/module-host.js`, `app/module-kit/bridge.js` | T6 | методи `page.*` з перевіркою дозволів; `deai.page` у панелі |
| `app/app.js`, `app/figma-capture.js` | T7 | життєвий цикл помічника, події, Esc, оверлей для «В Figma» |
| `app/trust-view.js`, `app/i18n.js` | T8 | блок «Робота з макетом» |
| `docs/modules/examples/contrast/` (нове), `docs/modules/authoring.md` | T9 | приклад-модуль і документація |
| `tests/live/module-page.test.mjs` (нове) | T10 | наскрізний живий тест на прикладі «Контраст» |
| `CHANGELOG.md`, `package.json` | T11 | реліз (контролер) |

---

### Task 1: `page` у маніфесті, `/api/module-ext` і довірі

**Files:** Modify `app/deai_modules.py` (`_check_tools` ~540, `extensions` ~1286, зведення довіри ~2694); Test
`tests/test_modules.py` (клас `ManifestApi2`, ~637: хелпери `api2`, `bad`, `tool`, константа `TOOL`).

- [ ] **Step 1: Падаючі тести** (у `ManifestApi2`):

```python
    def test_tool_page_valid(self):
        for i, page in enumerate((['read'], ['read', 'mark'], ['read', 'mark', 'change', 'listen'], ['listen', 'read'])):
            mid = f'pg-ok{i}'
            self.api2(mid, tools=[self.tool(page=page)])
            m = dm.catalog()[mid]
            self.assertEqual(m.status, 'ok', m.error)
            self.assertEqual(m.tools[0]['page'], tuple(sorted(page, key=dm.PAGE_PERMS.index)))

    def test_tool_page_refusals(self):
        for i, (page, frag) in enumerate(((   [], 'must be a non-empty list'), ('read', 'must be a non-empty list'),
                                          (['read', 'read'], 'duplicate'), (['read', 'write'], "unknown permission 'write'"),
                                          (['read', 5], 'unknown permission'), (['mark'], '"mark" requires "read"'),
                                          (['change'], '"change" requires "read"'), (['listen'], '"listen" requires "read"'))):
            mid = f'pg-bad{i}'
            self.api2(mid, tools=[self.tool(page=page)])
            m = self.bad(mid, 'tools[0].page')
            self.assertIn(frag, m.error)

    def test_tool_without_page_has_empty_tuple(self):
        self.api2(tools=[TOOL])
        self.assertEqual(dm.catalog()['tl'].tools[0]['page'], ())
```

  `test_tool_unknown_key_and_frame`: очікування для `frame` → `'tools[0].frame: not supported — use "page"'`.
  Наявні порівняння словника інструмента цілком (`test_valid_api2_with_tool_and_action`, ~667, і подібні — шукати
  `'panel': 'panel/index.html', 'key'`) отримують `'page': ()`. Плюс: `extensions(space)` несе `'page': [...]` (список)
  у кожному інструменті, зведення довіри — `{'label', 'icon', 'page': [...]}`; тести цих функцій (шукати
  `extensions(` і `'tools': [{'label'` у `tests/`) доповнити полем.

- [ ] **Step 2: FAIL.** **Step 3: реалізація.**

```python
#: Дозволи інструмента на роботу з макетом (М2), у канонічному порядку. Решта вимагає `read`: без нього нема посилань.
PAGE_PERMS = ('read', 'mark', 'change', 'listen')
```

  У `_check_tools`: `frame` → `f'{at}.frame: not supported — use "page"'`; ключ `page` додати до дозволених; перевірка
  (непорожній `list` рядків → дублі → невідомі → вимога `read`) з повідомленнями як у тестах; у вихідний словник
  `'page': tuple(sorted(page, key=PAGE_PERMS.index))` (або `()`). `extensions`: `'page': list(t['page'])`. Зведення
  довіри: `{'label', 'icon', 'page': list(t['page'])}`.

- [ ] **Step 4: PASS** (`python3 -B -m unittest tests.test_modules tests.test_modules_own tests.test_modules_api
  tests.test_modules_trust_api tests.test_module_example`). **Step 5: мутації:** прибрати вимогу `read`; прибрати перевірку дублів. **Step 6: коміт**
  `feat(modules): дозволи інструмента page у маніфесті`.

### Task 2: `app/page-rules.js` — чисті правила

**Files:** Create `app/page-rules.js`; Test `tests/page-rules.test.mjs`.

- [ ] **Step 1: Падаючі тести** (`tests/page-rules.test.mjs`):

```js
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { LIMITS, METHOD_PERM, PAGE_PERMS, PageError, TONES, TONE_COLORS, allowed, attrAllowed, checkClassList,
  checkLabel, checkStyleMap, checkStyleNames, checkText, checkTone, createJournal, stillOurs } from "../app/page-rules.js";

test("кожен метод має дозвіл; allowed() дивиться лише на нього", () => {
  for (const [m, p] of Object.entries(METHOD_PERM)) {
    assert.ok(m.startsWith("page.") && PAGE_PERMS.includes(p), m);
    assert.equal(allowed(m, [p]), true);
    assert.equal(allowed(m, PAGE_PERMS.filter((x) => x !== p)), false, m);
  }
  assert.equal(allowed("page.nope", PAGE_PERMS), false);
  assert.equal(allowed("page.info", null), false);
});

test("атрибути: список дозволених, зарезервовані data-*, решта — ні", () => {
  for (const n of ["role", "hidden", "title", "alt", "lang", "dir", "tabindex", "disabled", "placeholder", "open",
    "aria-label", "aria-describedby", "data-x", "data-test-id", "ARIA-LABEL"]) assert.equal(attrAllowed(n), true, n);
  for (const n of ["onclick", "src", "href", "srcdoc", "style", "class", "action", "formaction", "xlink:href",
    "data-deai-x", "data-canvas-inspector", "data-comment-layer", "data-h2d-ignore", "aria-", "data-", "id", ""])
    assert.equal(attrAllowed(n), false, n);
});

test("класи: імена, ліміт, тип", () => {
  assert.deepEqual(checkClassList(["a", "b-c", "_d"]), ["a", "b-c", "_d"]);
  for (const bad of [["1a"], ["a b"], ["a:b"], [""], "a", [1], Array(LIMITS.classes + 1).fill("a")])
    assert.throws(() => checkClassList(bad), (e) => e instanceof PageError && e.code === "bad-args");
});

test("стилі: назви й значення; url( і екранування — rejected, null — зняти", () => {
  assert.deepEqual(checkStyleNames(["color", "background-color", "--x"]), ["color", "background-color", "--x"]);
  assert.throws(() => checkStyleNames(Array(LIMITS.styles + 1).fill("color")), /bad-args|styles/);
  assert.throws(() => checkStyleNames(["col or"]), (e) => e.code === "bad-args");
  const r = checkStyleMap({ color: "red", "--k": "1px", margin: null, background: "url(x.png)",
    "background-image": "IMAGE-SET(a 1x)", width: "u\\72l(x)" });
  assert.deepEqual(r.ok, [["color", "red"], ["--k", "1px"], ["margin", null]]);
  assert.deepEqual(r.rejected.sort(), ["background", "background-image", "width"]);
  assert.throws(() => checkStyleMap({}), (e) => e.code === "bad-args");
  assert.throws(() => checkStyleMap({ color: 5 }), (e) => e.code === "bad-args");
});

test("текст, ярлик, тон", () => {
  assert.equal(checkText("abc"), "abc");
  assert.throws(() => checkText("x".repeat(LIMITS.text + 1)), (e) => e.code === "bad-args");
  assert.equal(checkLabel(undefined), "");
  assert.equal(checkLabel("a".repeat(100)).length, LIMITS.label);
  assert.equal(checkTone(undefined), "info");
  for (const tn of TONES) assert.equal(checkTone(tn), tn);
  assert.throws(() => checkTone("red"), (e) => e.code === "bad-args");
});

test("кольори тонів збігаються з токенами ядра в styles.css", () => {
  const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
  const tok = (n) => css.match(new RegExp(`--${n}:(#[0-9A-Fa-f]{6})`))[1].toLowerCase();
  assert.deepEqual(Object.fromEntries(Object.entries(TONE_COLORS).map(([k, v]) => [k, v.toLowerCase()])),
    { error: tok("bad"), warn: tok("open"), ok: tok("ok"), info: tok("pick") });
});

test("журнал: id, ліміт, take, takeAll — новіші першими", () => {
  const j = createJournal(3);
  const a = j.add({ n: 1 }), b = j.add({ n: 2 }), c = j.add({ n: 3 });
  assert.deepEqual([a, b, c], ["c1", "c2", "c3"]);
  assert.throws(() => j.add({ n: 4 }), (e) => e.code === "too-many");
  assert.deepEqual(j.take("c2"), { id: "c2", n: 2 });
  assert.equal(j.take("c2"), null);
  assert.deepEqual(j.takeAll().map((x) => x.id), ["c3", "c1"]);
  assert.equal(j.size, 0);
});

test("stillOurs: відкат лише коли поточне досі «стало»", () => {
  assert.equal(stillOurs("red", "red"), true);
  assert.equal(stillOurs("blue", "red"), false);
  assert.equal(stillOurs(null, null), true);
});
```

- [ ] **Step 2: FAIL.** **Step 3: реалізація** `app/page-rules.js`:

```js
/**
 * Помічник ядра для модулів (М2): ЧИСТІ правила без DOM — які методи моста вимагають якого дозволу, ліміти, що можна
 * міняти в документі макета. DOM-частина — `page-agent.js`, міст — `module-host.js`. Спека:
 * `docs/superpowers/specs/2026-11-24-modules-m2-page-helper-design.md`.
 */

export const PAGE_PERMS = ["read", "mark", "change", "listen"];

export const METHOD_PERM = {
  "page.info": "read", "page.query": "read", "page.get": "read", "page.snapshot": "read", "page.pick": "read",
  "page.reveal": "read",
  "page.mark": "mark", "page.unmark": "mark", "page.clearMarks": "mark",
  "page.setStyle": "change", "page.setClass": "change", "page.setAttr": "change", "page.setText": "change",
  "page.revert": "change", "page.revertAll": "change",
  "page.listen": "listen",
};

export const LIMITS = {
  queryDefault: 100, queryMax: 500, styles: 24, attrs: 30, attrVal: 300, nodeText: 300, cls: 200,
  snapshotDefault: 2000, snapshotMax: 4000, snapshotBytes: 2 * 1024 * 1024,
  marks: 300, label: 60, changes: 500, styleProps: 40, styleVal: 500, classes: 20, text: 2000,
};

export const TONES = ["error", "warn", "ok", "info"];
/** Кольори тонів — ті самі значення, що `--bad`, `--open`, `--ok`, `--pick` у `styles.css` (стереже тест): у документі
 *  макета токенів оболонки нема, тож літерали. */
export const TONE_COLORS = { error: "#F37373", warn: "#FBBC55", ok: "#6AD09D", info: "#3D8BFF" };

export class PageError extends Error {
  constructor(code, message) { super(message || code); this.code = code; }
}
const bad = (why) => new PageError("bad-args", why);

export const allowed = (method, perms) =>
  Object.hasOwn(METHOD_PERM, method) && Array.isArray(perms) && perms.includes(METHOD_PERM[method]);

const ATTR_PLAIN = new Set(["role", "hidden", "title", "alt", "lang", "dir", "tabindex", "disabled", "placeholder", "open"]);
const DATA_RESERVED = ["data-deai-", "data-canvas-", "data-comment-", "data-h2d-"];
/** Атрибут, який модуль може поставити чи зняти: лише безпечні для виконання й завантаження (без `on*`, `src`, `href`…). */
export function attrAllowed(name) {
  if (typeof name !== "string") return false;
  const n = name.toLowerCase();
  if (ATTR_PLAIN.has(n)) return true;
  if (/^aria-[a-z]+(-[a-z]+)*$/.test(n)) return true;
  return /^data-[a-z0-9]+(-[a-z0-9]+)*$/.test(n) && !DATA_RESERVED.some((p) => n.startsWith(p));
}

const CLASS_RE = /^[A-Za-z_-][\w-]{0,99}$/;
export function checkClassList(list) {
  if (!Array.isArray(list) || list.length > LIMITS.classes) throw bad(`classes: a list of at most ${LIMITS.classes} names`);
  for (const c of list) if (typeof c !== "string" || !CLASS_RE.test(c)) throw bad(`bad class name ${String(c).slice(0, 40)}`);
  return list.slice();
}

const PROP_RE = /^(--[A-Za-z0-9_-]{1,60}|-?[a-z][a-z-]{0,59})$/;
export function checkStyleNames(list) {
  if (list == null) return [];
  if (!Array.isArray(list) || list.length > LIMITS.styles) throw bad(`styles: a list of at most ${LIMITS.styles} names`);
  for (const p of list) if (typeof p !== "string" || !PROP_RE.test(p)) throw bad(`bad style name ${String(p).slice(0, 40)}`);
  return list.slice();
}

/** Значення, що змусило б сторінку щось вантажити, або з CSS-екрануванням (обхід перевірки) — у `rejected`. */
const LOADS_RE = /(^|[^\w-])(url|image-set|-webkit-image-set|image|cross-fade|element|src)\s*\(/i;
export function checkStyleMap(map) {
  if (!map || typeof map !== "object" || Array.isArray(map)) throw bad("styles: an object {prop: value|null}");
  const keys = Object.keys(map);
  if (!keys.length || keys.length > LIMITS.styleProps) throw bad(`styles: 1 to ${LIMITS.styleProps} properties`);
  const ok = [], rejected = [];
  for (const p of keys) {
    if (!PROP_RE.test(p)) throw bad(`bad style name ${p.slice(0, 40)}`);
    const v = map[p];
    if (v === null) { ok.push([p, null]); continue; }
    if (typeof v !== "string" || v.length > LIMITS.styleVal) throw bad(`style ${p}: a string of at most ${LIMITS.styleVal} characters or null`);
    if (v.includes("\\") || LOADS_RE.test(v)) { rejected.push(p); continue; }
    ok.push([p, v]);
  }
  return { ok, rejected };
}

export function checkText(text) {
  if (typeof text !== "string" || text.length > LIMITS.text) throw bad(`text: a string of at most ${LIMITS.text} characters`);
  return text;
}
export const checkLabel = (label) => (typeof label === "string" ? label.slice(0, LIMITS.label) : "");
export function checkTone(tone) {
  if (tone === undefined || tone === null) return "info";
  if (!TONES.includes(tone)) throw bad(`tone: one of ${TONES.join(", ")}`);
  return tone;
}

/** Відкат повертає «було» лише коли зараз досі «стало»: змінене після модуля (скрипт сторінки, тюнер) не чіпаємо. */
export const stillOurs = (current, after) => current === after;

/** Журнал змін: `add` → id (`c1`…), `take(id)` → запис чи null, `takeAll()` → новіші першими (порядок відкату). */
export function createJournal(max = LIMITS.changes) {
  const items = new Map();
  let seq = 0;
  return {
    get size() { return items.size; },
    add(entry) {
      if (items.size >= max) throw new PageError("too-many", `at most ${max} active changes`);
      const id = `c${++seq}`;
      items.set(id, { id, ...entry });
      return id;
    },
    take(id) { const x = items.get(id) ?? null; if (x) items.delete(id); return x; },
    takeAll() { const all = [...items.values()].reverse(); items.clear(); return all; },
  };
}
```

- [ ] **Step 4: PASS** (`node --test tests/page-rules.test.mjs`). **Step 5: мутації:** дозволити `href` в
  `attrAllowed`; прибрати перевірку `\\`; `takeAll` без `reverse()` — кожна червона. **Step 6: коміт**
  `feat(page): чисті правила помічника модулів`.

### Task 3: `app/page-agent.js` — посилання, опис вузлів, запити, знімок

**Files:** Create `app/page-agent.js`; Create `tests/live/page-agent.test.mjs`.

**Стенд живого тесту (на всі T3–T5).** Без сервера канваса: Playwright `page.route("http://agent.test/**")` віддає
`app/*` з диска і дві сторінки з памʼяті. `host.html` імпортує помічника й працює над `iframe.contentDocument` — так
само, як у канвасі (інше вікно, те саме походження: ловить помилки на кшталт `instanceof` між вікнами).

```js
const HOST = `<!doctype html><meta charset="utf-8"><iframe id="f" src="/fixture.html" style="width:900px;height:600px;border:0"></iframe>
<script type="module">
  import { createPageAgent } from "/app/page-agent.js";
  window.EV = [];
  window.mk = () => { window.A?.destroy(); window.A = createPageAgent({ doc: document.getElementById("f").contentDocument,
    pageInfo: () => ({ id: "p1", title: "Сторінка" }), onEvent: (n, d) => window.EV.push([n, d]) }); return true; };
  document.getElementById("f").addEventListener("load", () => { window.READY = true; });
</script>`;
const FIXTURE = `<!doctype html><html><head><meta charset="utf-8"><title>F</title><style>.lo{color:#fff;background:#9fd3b8}</style></head>
<body style="margin:0;font-family:sans-serif">
  <h1 id="h">Заголовок <span>в</span> тексті</h1>
  <button id="cta" class="lo cta" aria-label="Почати">Почати</button>
  <p id="p" style="color: green">Абзац</p>
  <div id="tall" style="height:2000px">довгий</div>
  <a id="far" href="#x">далеко</a>
  <script>window.PAGE_CLICKS = 0; document.addEventListener("click", () => window.PAGE_CLICKS++);</script>
  <template><b>t</b></template>
  <div data-canvas-inspector><i id="ours">наше</i></div>
</body></html>`;
```

  Кожен тест: `page.goto("http://agent.test/host.html")`, `waitForFunction(() => window.READY)`, `evaluate(() => mk())`.
  Виклики — `page.evaluate((a) => window.A.query(...a), args)`; помилки ловити в `evaluate` і повертати `e.code`.

- [ ] **Step 1: Падаючі тести T3:**
  - `query("button")` → один вузол: `tag: "button"`, `id: "cta"`, `cls: "lo cta"`, `text: "Почати"`, `visible: true`,
    `rect` у координатах документа (прокрутити рамку на 500 px — `rect.y` не змінюється);
  - `query("i")` не повертає `#ours` (наш оверлей); `query("script, template, b")` — порожньо;
  - `query("[")` → `bad-selector`; `limit` понад 500 → обрізається до 500, `limit: 0`/від'ємний → `bad-args`;
  - той самий елемент — той самий `ref` у двох запитах; `get(ref, {styles: ["color"], attrs: true})` → `styles.color`
    обчислений (`rgb(255, 255, 255)`), `attrs["aria-label"] === "Почати"`;
  - `text` — лише власний текст (`h1` → `"Заголовок тексті"` без тексту `span`, пробіли згорнуті), обрізка 300;
  - `snapshot({styles: ["color"]})` → `nodes[0].tag === "body"`, `parent === null`; у кожного наступного `parent` — ref,
    що вже траплявся раніше в списку; без `script`/`template`/наших оверлеїв; `maxNodes: 3` → `truncated: true`, 3 вузли;
  - `info()` → `{page: {id: "p1", title: "Сторінка"}, viewport: {w: 900, h: 600}, scroll, size}`;
  - після `iframe.src = "/fixture.html?2"` і нового `mk()` старий `ref` → `stale-ref`; виклик на знищеному помічнику →
    `no-page`.

- [ ] **Step 2: FAIL. Step 3: реалізація (каркас файла; T4–T5 дописують методи):**

```js
/**
 * Помічник ядра для модулів (М2): працює над документом рамки макета ЗІ СВОГО вікна (те саме походження) — як
 * інспектор і тюнер. Код модуля сюди не потрапляє: модуль лише просить через міст (`module-host.js`).
 * ⛔ Жоден рядок від модуля не йде в `innerHTML`/`insertAdjacentHTML`/`eval` чи атрибут поза `attrAllowed` —
 * лише `textContent`, `style.setProperty`, `classList`. Стереже статичний тест у `tests/page-rules.test.mjs`.
 * ⛔ Вузли — з ІНШОГО вікна: жодного `instanceof`, лише `nodeType`/`localName`.
 */
import { LIMITS, PageError, checkStyleNames } from "./page-rules.js";

const OURS = "[data-canvas-inspector],[data-comment-layer],#cl-down,[data-deai-marks]";
const SKIP = new Set(["script", "style", "template", "noscript"]);
const clip = (s, n) => (s.length > n ? s.slice(0, n) : s);
const round = (x) => Math.round(x * 10) / 10;

export function createPageAgent({ doc, onEvent = () => {}, pageInfo = () => null }) {
  const win = doc.defaultView;
  let alive = true;
  let seq = 0;
  const byEl = new WeakMap();
  const byRef = new Map();

  const live = () => { if (!alive || !doc.defaultView) throw new PageError("no-page", "no live mockup page"); };
  const isOurs = (el) => !!el.closest(OURS);
  const inBody = (el) => !!doc.body && doc.body.contains(el) && !el.closest("script,style,template,noscript");
  function refOf(el) {
    let r = byEl.get(el);
    if (!r) { r = `r${++seq}`; byEl.set(el, r); byRef.set(r, new WeakRef(el)); }
    return r;
  }
  function elOf(ref) {
    live();
    const el = typeof ref === "string" ? byRef.get(ref)?.deref() : null;
    if (!el || !el.isConnected || el.ownerDocument !== doc) throw new PageError("stale-ref", "the element is gone or the page reloaded");
    return el;
  }
  function ownText(el) {
    let s = "";
    for (const n of el.childNodes) if (n.nodeType === 3) s += n.nodeValue;
    return clip(s.replace(/\s+/g, " ").trim(), LIMITS.nodeText);
  }
  function attrsOf(el) {
    const out = {};
    for (const a of [...el.attributes].slice(0, LIMITS.attrs)) out[a.name] = clip(a.value, LIMITS.attrVal);
    return out;
  }
  function describe(el, o = {}) {
    const r = el.getBoundingClientRect();
    const cs = win.getComputedStyle(el);
    const cls = el.getAttribute("class") || "";
    const n = { ref: refOf(el), tag: el.localName, id: el.id || "", cls: clip(cls, LIMITS.cls), text: ownText(el),
      rect: { x: round(r.left + win.scrollX), y: round(r.top + win.scrollY), w: round(r.width), h: round(r.height) },
      visible: r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none" };
    if (o.attrs === true) n.attrs = attrsOf(el);
    if (o.styles && o.styles.length) { n.styles = {}; for (const p of o.styles) n.styles[p] = cs.getPropertyValue(p); }
    return n;
  }
  const opts = (o) => ({ styles: checkStyleNames(o?.styles), attrs: o?.attrs === true });
  function intIn(v, dflt, max, name) {
    if (v === undefined) return dflt;
    if (!Number.isInteger(v) || v < 1) throw new PageError("bad-args", `${name}: a positive integer`);
    return Math.min(v, max);
  }

  const api = {
    get alive() { return alive; },
    info() {
      live();
      const de = doc.documentElement;
      return { page: pageInfo(), viewport: { w: win.innerWidth, h: win.innerHeight },
        scroll: { x: round(win.scrollX), y: round(win.scrollY) }, size: { w: de.scrollWidth, h: de.scrollHeight } };
    },
    query(selector, o = {}) {
      live();
      if (typeof selector !== "string" || !selector || selector.length > 1000) throw new PageError("bad-args", "selector: a non-empty string");
      const limit = intIn(o?.limit, LIMITS.queryDefault, LIMITS.queryMax, "limit");
      const so = opts(o);
      let found;
      try { found = doc.querySelectorAll(selector); } catch (e) { throw new PageError("bad-selector", String(e?.message || e).slice(0, 200)); }
      const out = [];
      for (const el of found) {
        if (out.length >= limit) break;
        if (inBody(el) && !isOurs(el)) out.push(describe(el, so));
      }
      return out;
    },
    get(ref, o = {}) { return describe(elOf(ref), opts(o)); },
    snapshot(o = {}) {
      live();
      const max = intIn(o?.maxNodes, LIMITS.snapshotDefault, LIMITS.snapshotMax, "maxNodes");
      const so = opts(o);
      const nodes = [];
      let bytes = 0, truncated = false;
      if (doc.body) {
        const walker = doc.createTreeWalker(doc.body, 1, { acceptNode: (n) => (SKIP.has(n.localName) || n.matches(OURS) ? 2 : 1) });
        for (let el = walker.currentNode; el; el = walker.nextNode()) {
          const n = describe(el, so);
          n.parent = el === doc.body ? null : refOf(el.parentElement);
          bytes += JSON.stringify(n).length;
          if (nodes.length >= max || bytes > LIMITS.snapshotBytes) { truncated = true; break; }
          nodes.push(n);
        }
      }
      return { info: api.info(), truncated, nodes };
    },
    destroy() {
      if (!alive) return;
      alive = false;
      byRef.clear();
    },
  };
  return api;
}
```

  (`acceptNode` повертає `2` = `FILTER_REJECT` — пропускає піддерево; константи з іншого вікна не беремо.)

- [ ] **Step 4: PASS** (`until mkdir /private/tmp/deai-live.lock 2>/dev/null; do sleep 10; done; H=$(mktemp -d); HOME="$H" node --test --import ./tests/live/_env.mjs tests/live/page-agent.test.mjs; rmdir /private/tmp/deai-live.lock`).
  **Step 5: мутації:** прибрати `isOurs` з `query`; `acceptNode` без `SKIP`. **Step 6: коміт**
  `feat(page): помічник — посилання, запити, знімок`.

### Task 4: мітки, `reveal`, `pick`

**Files:** Modify `app/page-agent.js`; Test `tests/live/page-agent.test.mjs`.

- [ ] **Step 1: Падаючі тести:**
  - `mark(ref, {tone: "error", label: "Контраст 1.9:1"})` → `m1`; у документі рамки один `[data-deai-marks]` з
    `data-h2d-ignore="true"`, у його тіньовому корені — `.mk` з `--t: #F37373` і ярликом із тим текстом (`textContent`,
    `label` з `<b>` лишається текстом); `getBoundingClientRect` мітки охоплює кнопку (±4 px);
  - прокрутка рамки на 300 px → після кадру мітка переїхала разом із кнопкою; `elementFromPoint` у центрі кнопки — кнопка
    (мітка кліки не забирає);
  - кнопку прибрали з DOM → мітка прихована; `unmark("m1")` → нема; `clearMarks()` → жодної; 301-ша мітка → `too-many`;
    `tone: "red"` → `bad-args`;
  - `reveal(refOf(#far))` → `#far` у видимій області рамки; `reveal` без мітки малює тимчасову рамку й прибирає її
    за ~1,2 с;
  - `pick()` → кліком по центру `#cta` (координати рамки + зсув iframe) повертає вузол `cta`, `PAGE_CLICKS` у рамці
    лишився 0; під час вибору мітки сховані, після — знову видно; `pick()` + Esc у рамці → `null`; `pick()` + другий
    `pick()` → перший дав `null`; `destroy()` під час `pick` → `null`, хоста нема.
- [ ] **Step 2: FAIL. Step 3: реалізація** у `createPageAgent` (до `const api`):

```js
  const STYLE = `:host{all:initial}
.w[hidden]{display:none}
.mk{position:fixed;box-sizing:border-box;border:2px solid var(--t);background:color-mix(in srgb,var(--t) 9%,transparent);border-radius:4px;pointer-events:none}
.mk[hidden]{display:none}
.mk.fl{animation:fl .6s 2}
@keyframes fl{50%{box-shadow:0 0 0 7px color-mix(in srgb,var(--t) 45%,transparent)}}
@media (prefers-reduced-motion:reduce){.mk.fl{animation:none;box-shadow:0 0 0 4px color-mix(in srgb,var(--t) 45%,transparent)}}
.l{position:absolute;left:-2px;bottom:100%;margin-bottom:3px;max-width:240px;padding:2px 6px;border-radius:4px;background:var(--t);color:#151d19;font:600 11px/16px system-ui,-apple-system,"Segoe UI",sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.l.dn{bottom:auto;top:100%;margin:3px 0 0}
.l:empty{display:none}
.cv{position:fixed;inset:0;cursor:crosshair;pointer-events:auto;background:transparent}
.pk{position:fixed;box-sizing:border-box;border:2px solid #3D8BFF;background:rgba(61,139,255,.1);border-radius:3px;pointer-events:none}
.pk[hidden]{display:none}
.pk span{position:absolute;left:-2px;top:100%;margin-top:3px;padding:2px 6px;border-radius:4px;background:#3D8BFF;color:#fff;font:600 11px/16px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap}`;
  let host = null, root = null, wrap = null;
  function ensureHost() {
    if (host && host.isConnected) return;
    host = doc.createElement("div");
    host.setAttribute("data-deai-marks", "");
    host.setAttribute("data-h2d-ignore", "true");         // «В Figma» пропускає лише зі значенням "true"
    host.style.setProperty("all", "initial", "important");
    for (const [k, v] of [["position", "fixed"], ["top", "0"], ["left", "0"], ["width", "0"], ["height", "0"],
      ["z-index", "2147482999"], ["pointer-events", "none"]]) host.style.setProperty(k, v, "important");
    doc.documentElement.appendChild(host);                  // не в body: не стаємо учасником розкладки сторінки
    root = host.attachShadow({ mode: "closed" });
    const st = doc.createElement("style"); st.textContent = STYLE; root.appendChild(st);
    wrap = doc.createElement("div"); wrap.className = "w"; root.appendChild(wrap);
  }
```

  Далі — `marks: Map<id, {el: WeakRef, box, lab}>`, `markSeq`; `place()` для всіх міток (у `requestAnimationFrame`
  рамки, злиття викликів в один кадр): елемента нема/не підключений → `box.hidden = true`; інакше
  `left/top/width/height` з `getBoundingClientRect()` ± 3 px, `lab.classList.toggle("dn", r.top < 22)`. Слухачі, лише
  поки є хоч одна мітка: `scroll` (документ, capture, passive), `resize` (вікно рамки), `MutationObserver` на
  `documentElement` (`subtree`, `childList`, `attributes`, `characterData`). `mark(ref, o)`: `elOf`, `checkTone`,
  `checkLabel`, ліміт `LIMITS.marks` → `too-many`, `box.style.setProperty("--t", TONE_COLORS[tone])`,
  `lab.textContent = label`. `unmark(id)` (невідомий — тихо), `clearMarks()`.

  `reveal(ref)`: `reduced = win.matchMedia("(prefers-reduced-motion: reduce)").matches`;
  `el.scrollIntoView({ block: "center", inline: "nearest", behavior: reduced ? "auto" : "smooth" })`; мітка цього
  елемента є — клас `fl` на 1200 мс (зняти/reflow/поставити); нема — тимчасова мітка `info` без ярлика, прибрати через
  1200 мс.

  `pick()`: попередній вибір → `null`; `ensureHost()`; `wrap.hidden = true` (мітки сховані); покрив `.cv` і рамка `.pk`
  у корені; `mousemove` на покриві → `topAt(x, y)` = перший з `doc.elementsFromPoint(x, y)`, що не `host`, не
  `isOurs`, і `inBody` → рамка й підпис `${tag}${cls ? "." + перший клас : ""} ${w}×${h}`; `click` (кнопка 0) на покриві
  → `finish(el ? describe(el) : null)`; `keydown` на документі (capture): Esc → `preventDefault`,
  `stopPropagation`, `finish(null)`. `finish` прибирає покрив/рамку/слухачі, `wrap.hidden = false`, резолвить проміс.
  `cancelPick()` = `finish(null)`; гетер `picking`. `destroy()`: `cancelPick()`, `clearMarks()`, зняти слухачі,
  `host?.remove()`.

- [ ] **Step 4: PASS. Step 5: мутації:** прибрати `data-h2d-ignore`; `pointer-events:auto` на `.mk`; покрив без
  перехоплення (клік доходить до сторінки) — кожна червона. **Step 6: коміт** `feat(page): мітки, показ і вибір елемента`.

### Task 5: зміни вигляду з журналом і слухання

**Files:** Modify `app/page-agent.js`; Test `tests/live/page-agent.test.mjs`, `tests/page-rules.test.mjs`.

- [ ] **Step 1: Падаючі тести:**
  - `setStyle(cta, {color: "rgb(0, 0, 0)", background: "url(x)", width: "nope"})` → `applied: ["color"]`,
    `rejected: ["background", "width"]`; обчислений колір — чорний; `revert(id)` → `reverted: 1`, атрибута `style` у
    кнопки нема (його й не було);
  - `#p` мав `style="color: green"`: `setStyle(p, {color: "red"})` → `revertAll()` → знову `green`, атрибут `style` на місці;
  - «досі наше»: `setStyle(p, {color: "red"})`, потім сторінка сама ставить `p.style.color = "blue"` → `revert(id)` →
    `skipped: 1`, колір лишився `blue`;
  - LIFO: `setStyle(p, {color: "red"})`, `setStyle(p, {color: "black"})`, `revertAll()` → `green`;
  - `setClass(cta, {add: ["x"], remove: ["lo"]})` → відкат: `class="lo cta"`; клас, що вже був, `add` не записує в журнал
    (відкат його не прибирає);
  - `setAttr(cta, "aria-label", "Інше")` / `null` → відкат повертає `"Почати"`; `setAttr(cta, "href", "x")` і
    `setAttr(cta, "onclick", "x")` → `not-allowed`;
  - `setText(h1)` → `not-leaf` (є `span`); `setText(cta, "<b>x</b>")` → текст буквально `<b>x</b>`, елемента `b` нема;
    відкат повертає `Почати`;
  - 501-ша зміна → `too-many`; зміна на елементі, якого вже нема, при відкаті → `skipped`;
  - `listen({click: true})` → клік у рамці по `#cta` → подія `page-click` з `node.id === "cta"` і `PAGE_CLICKS === 1`
    (клік дійшов до сторінки); `listen({click: false})` → подій нема; `listen({hover: true})` → наведення на `#p` →
    `page-hover` з `node.id === "p"`, не частіше 10/с (20 рухів за 100 мс → ≤ 2 події); під час `pick` `page-click` нема;
  - `destroy()` відкочує все й знімає слухачів (клік після `destroy` подій не дає).
  - **Статичний охоронець** (у `tests/page-rules.test.mjs`): у тексті `app/page-agent.js` нема `innerHTML`,
    `outerHTML`, `insertAdjacentHTML`, `eval(`, `new Function`, `document.write`, а кожен `setAttribute(` має першим
    аргументом рядковий літерал зі списку (`"data-deai-marks"`, `"data-h2d-ignore"`) або змінну, перевірену
    `attrAllowed` у тому самому методі (перевірка регекспом на конкретні рядки файла).
- [ ] **Step 2: FAIL. Step 3: реалізація.**
  - `journal = createJournal()`.
  - `setStyle(ref, map)`: `el = elOf(ref)`; `{ok, rejected} = checkStyleMap(map)`; для кожного `[p, v]`:
    `before = {v: el.style.getPropertyValue(p), pr: el.style.getPropertyPriority(p)}`; `v === null` →
    `removeProperty(p)`; інакше `removeProperty(p)` і `setProperty(p, v, "important")`; браузер не прийняв (порожнє
    значення після запису, коли `v` не `null`) → повернути `before`, `p` у `rejected`; інакше
    `items.push({p, before, after: {v: getPropertyValue(p), pr: getPropertyPriority(p)}})`, `p` у `applied`.
    Нема `items` → `{id: null, applied: [], rejected}`, у журнал нічого. Інакше
    `id = journal.add({kind: "style", el: new WeakRef(el), items})`.
  - `setClass`: `add`/`remove` через `checkClassList`; записуються лише справжні зміни (`added` — не було,
    `removed` — був).
  - `setAttr(ref, name, value)`: `attrAllowed(name)` інакше `not-allowed`; `value` — рядок ≤ `LIMITS.attrVal` чи `null`
    (`bad-args`); `before = el.getAttribute(name)`; поставити/зняти; `after = el.getAttribute(name)`.
  - `setText(ref, text)`: `el.children.length` → `not-leaf`; `checkText`; `before = el.textContent`;
    `el.textContent = text`; `after = el.textContent`.
  - `revertEntry(e)` → `{reverted, skipped}`: `el = e.el.deref()`; нема/не підключений → усі пункти `skipped`.
    `style`: для кожного пункту в зворотному порядку `stillOurs(cur, after)` за `v` і `pr` → повернути `before`
    (`before.v === ""` → `removeProperty`); після — `el.style.length === 0` → `removeAttribute("style")`.
    `class`: `added` → прибрати, якщо є; `removed` → додати, якщо нема. `attr`/`text` — `stillOurs` поточного з `after`.
  - `revert(id)`: `journal.take(id)` (нема → `{reverted: 0, skipped: 0}`); `revertAll()`: `journal.takeAll()`
    (новіші першими) і сума.
  - `listen({click, hover})`: булеві прапорці (інше → `bad-args`). `click` — `doc.addEventListener("click", h, {capture: true, passive: true})`;
    подія не перехоплюється; ціль — `ev.target`, текстовий вузол → його `parentElement`; `isOurs` чи не `inBody` → нічого;
    під час `pick` → нічого. `hover` — `mouseover` (capture, passive), той самий фільтр, лише коли елемент змінився,
    тротлінг 100 мс із відкладеною останньою подією.
  - `destroy()` додатково: `revertAll()`, зняти слухачі.
- [ ] **Step 4: PASS** (живий файл і `node --test tests/page-rules.test.mjs`). **Step 5: мутації:** відкат без
  `stillOurs`; `takeAll` у прямому порядку; `setText` через `innerHTML` (охоронець червоніє). **Step 6: коміт**
  `feat(page): тимчасові зміни з журналом і слухання дій`.

### Task 6: міст — `page.*` у хості, `deai.page` у панелі

**Files:** Modify `app/module-host.js`, `app/module-kit/bridge.js`; Test `tests/module-host.test.mjs`,
`tests/module-bridge.test.mjs`.

- [ ] **Step 1: Падаючі тести** (`tests/module-host.test.mjs`):

```js
const pageStub = () => {
  const calls = [];
  const p = new Proxy({}, { get: (_, k) => (...a) => { calls.push([k, a]); if (k === "pick") return Promise.resolve({ ref: "r1" });
    if (k === "query" && a[0] === "[") { const e = new Error("bad"); e.code = "bad-selector"; throw e; } return { k, a }; } });
  return { p, calls };
};
const mkHost = (perms, page) => createBridgeHost({ getContext: () => ({}), getSelection: () => null, getVars: () => ({}),
  getTheme: () => "dark", callTool: async () => null, toast() {}, close() {}, perms, getPage: () => page });

test("page.*: дозвіл, відсутній помічник, проксі аргументів, коди помилок", async () => {
  const { p, calls } = pageStub();
  const h = mkHost(["read", "mark"], p);
  assert.deepEqual(await h.handle({ deai: 1, id: 1, method: "page.query", args: ["a", { limit: 3 }] }),
    { deai: 1, re: 1, ok: true, value: { k: "query", a: ["a", { limit: 3 }] } });
  assert.equal((await h.handle({ deai: 1, id: 2, method: "page.setStyle", args: ["r1", {}] })).error, "not-allowed");
  assert.equal((await h.handle({ deai: 1, id: 3, method: "page.query", args: ["["] })).error, "bad-selector");
  assert.equal((await mkHost(["read"], null).handle({ deai: 1, id: 4, method: "page.info", args: [] })).error, "no-page");
  assert.equal((await mkHost([], p).handle({ deai: 1, id: 5, method: "page.info", args: [] })).error, "not-allowed");
  assert.deepEqual((await h.handle({ deai: 1, id: 6, method: "page.pick", args: [] })).value, { ref: "r1" });
  assert.ok(calls.every(([k]) => k !== "setStyle"));
});

test("М1-хост без perms/getPage — page.* → not-allowed, решта як була", async () => {
  const h = createBridgeHost({ getContext: () => ({ a: 1 }), getSelection: () => null, getVars: () => ({}), getTheme: () => "dark",
    callTool: async () => null, toast() {}, close() {} });
  assert.equal((await h.handle({ deai: 1, id: 1, method: "page.info", args: [] })).error, "not-allowed");
  assert.deepEqual((await h.handle({ deai: 1, id: 2, method: "context", args: [] })).value, { a: 1 });
});
```

  У `tests/module-bridge.test.mjs` (за наявним зразком підробленого `window.parent`): `deai.page.query("a", {limit: 2})`
  шле `{method: "page.query", args: ["a", {limit: 2}]}`; кожен метод `deai.page.*` шле свою назву з `METHOD_PERM`
  (повний перелік — один тест по ключах); `deai.page.pick()` не має таймауту (підроблений `setTimeout` фіксує, що
  таймер для нього не ставиться), решта — 60 с, як `call`.
- [ ] **Step 2: FAIL. Step 3: реалізація.**
  - `module-host.js`: `import { METHOD_PERM, allowed } from "./page-rules.js"`; `createBridgeHost({…, perms = [], getPage = () => null})`;
    `check()` пускає `METHODS` і ключі `METHOD_PERM`; у `handle` перед `switch`:

```js
    if (Object.hasOwn(METHOD_PERM, msg.method)) {
      if (!allowed(msg.method, perms)) return fail(id, "not-allowed", `${msg.method} needs the "${METHOD_PERM[msg.method]}" permission`);
      const page = getPage();
      if (!page || !page.alive) return fail(id, "no-page", "no live mockup page");
      try {
        const name = msg.method.slice(5);
        return ok(id, await page[name](...args));
      } catch (e) {
        return fail(id, (e && e.code) || "error", e && e.message);
      }
    }
```

  - `bridge.js`: `request(method, args, ms = PENDING_MS)` (`ms === 0` — без таймера); простір імен:

```js
    page: {
      info: function () { return request("page.info", []); },
      query: function (selector, opts) { return request("page.query", [selector, opts]); },
      get: function (ref, opts) { return request("page.get", [ref, opts]); },
      snapshot: function (opts) { return request("page.snapshot", [opts]); },
      pick: function () { return request("page.pick", [], 0); },
      reveal: function (ref) { return request("page.reveal", [ref]); },
      mark: function (ref, opts) { return request("page.mark", [ref, opts]); },
      unmark: function (id) { return request("page.unmark", [id]); },
      clearMarks: function () { return request("page.clearMarks", []); },
      setStyle: function (ref, map) { return request("page.setStyle", [ref, map]); },
      setClass: function (ref, ch) { return request("page.setClass", [ref, ch]); },
      setAttr: function (ref, name, value) { return request("page.setAttr", [ref, name, value]); },
      setText: function (ref, text) { return request("page.setText", [ref, text]); },
      revert: function (id) { return request("page.revert", [id]); },
      revertAll: function () { return request("page.revertAll", []); },
      listen: function (opts) { return request("page.listen", [opts]); }
    },
```

    `pick` без таймауту лишається в `pending` (ліміт 64 його рахує); шелл резолвить його `null` при закритті панелі.
- [ ] **Step 4: PASS** (`node --test tests/module-host.test.mjs tests/module-bridge.test.mjs`). **Step 5: мутації:**
  прибрати `allowed` у `handle`; `page.alive` не перевіряти. **Step 6: коміт** `feat(modules): методи page.* у мості`.

### Task 7: проводка в оболонці

**Files:** Modify `app/app.js`, `app/figma-capture.js`; Test `tests/figma-capture.test.mjs`, наявні живі
`tests/live/module-tools.test.mjs` (регресія).

- [ ] **Step 1: Падаючий тест** `figma-capture`: `OVERLAY_SELECTORS` містить `[data-deai-marks]`, `markOverlays` ставить
  йому `data-h2d-ignore="true"` (наявний зразок тесту на підробці документа).
- [ ] **Step 2: Реалізація.**
  - `figma-capture.js`: `'[data-deai-marks]'` в `OVERLAY_SELECTORS`.
  - `app.js`: `import { createPageAgent } from './page-agent.js';` `let pageAgent = null;`
  - `openModTool`: `bound.page = Array.isArray(x.page) ? x.page.filter((p) => typeof p === 'string') : [];`
    `bound.host = modHostFor(bound)`; `modHostFor` передає `perms: bound.page, getPage: () => (modOpen === bound ? pageAgent : null)`.
  - Нові функції біля `closeModTool`:

```js
/** Помічник макета (М2) — лише для відкритого інструмента з дозволами `page` і лише над живою сторінкою макета
 *  того ж походження. Старий завжди знищуємо: його документ або пішов, або інструмент закрито. */
function pageDetach() {
  if (!pageAgent) return;
  try { pageAgent.destroy(); } catch (e) { /* документ рамки вже вивантажено */ }
  pageAgent = null;
}
function pageAttach() {
  pageDetach();
  const bound = modOpen;
  if (!bound || !bound.page.length || mode === 'canvas' || cleanView) return;
  let doc = null;
  try { doc = frame.contentDocument; } catch (e) { doc = null; }
  if (!doc || !doc.body || doc.readyState === 'loading') return;
  pageAgent = createPageAgent({ doc, pageInfo: () => modContext().page,
    onEvent: (name, data) => { if (modOpen === bound) modPost(bound.host.event(name, data)); } });
  if (bound.inited) modPost(bound.host.event('page', { page: modContext().page }));
}
```

  - `closeModTool`: `pageDetach()` ПЕРШИМ рядком після `if (!modOpen) return;` (відкат змін на ще живому документі до
    події `close`).
  - Обробник `message`: після відправки `init` — `bound.inited = true; pageAttach();`.
  - `frame.addEventListener('load', …)` — новий окремий обробник: `if (modOpen) pageAttach(); else pageDetach();`.
  - Перед початком навантаження нової сторінки (місця, де ставиться `frame.src`, і посилання з рамки) нічого не треба:
    старий документ іде разом зі змінами, `load` перестворить помічника.
  - Esc в оболонці: на початку головного обробника `keydown` вікна —
    `if (ev.key === 'Escape' && pageAgent?.picking) { ev.preventDefault(); pageAgent.cancelPick(); return; }`.
  - Клавіші рамки (`frameCmtKey`) під час `pick` не діють: `if (pageAgent?.picking) return;` першим рядком.
- [ ] **Step 3: Перевірка.** `node --test tests/*.test.mjs` (усі юніти); живі `module-tools`, `module-example`,
  `canvas` по одному під замком — без регресій. **Step 4: коміт** `feat(page): помічник у життєвому циклі панелі інструмента`.

### Task 8: довіра — блок «Робота з макетом»

**Files:** Modify `app/trust-view.js`, `app/i18n.js`; Test `tests/trust-view.test.mjs`.

- [ ] **Step 1: Падаючі тести:** інструменти без `page` → розмітка діалогу без змін (порівняння з наявним
  еталоном тесту); інструменти з `["read","change"]` і `["read","listen"]` → один блок із заголовком `trustPage` і
  рядками `trustPageRead`, `trustPageChange`, `trustPageListen` у порядку `PAGE_PERMS`, без дублів; невідомий дозвіл
  ігнорується; текст екранується.
- [ ] **Step 2: Реалізація.** `i18n.js` (uk/en):
  `trustPage: 'Робота з макетом, поки панель інструмента відкрита'` / `'Working with the mockup while the tool panel is open'`;
  `trustPageRead: 'Читає вміст сторінок макета'` / `'Reads the content of mockup pages'`;
  `trustPageMark: 'Помічає елементи на сторінці'` / `'Marks elements on the page'`;
  `trustPageChange: 'Тимчасово змінює вигляд — до перезавантаження сторінки'` / `'Temporarily changes the look — until the page reloads'`;
  `trustPageListen: 'Стежить за кліками й наведенням'` / `'Watches clicks and hovering'`.
  `trust-view.js`: `pageHTML(tools)` → `<div class="tr-ext"><span class="tr-h3">…</span><ul class="tr-page">…</ul></div>`
  одразу після `extHTML(d.tools, "trustTools")`; стиль `.tr-page` — у `styles.css` поруч із `.tr-ext` (маркери списку як у
  наявних списках діалогу).
- [ ] **Step 3: PASS. Step 4: коміт** `feat(trust): блок «Робота з макетом» у діалозі довіри`.

### Task 9: приклад «Контраст» і документація

**Files:** Create `docs/modules/examples/contrast/{module.json,server.py,panel/index.html,panel/contrast.js,panel/contrast.css}`;
Modify `docs/modules/authoring.md`; Test `tests/test_module_example.py` (новий клас).

- [ ] **Step 1: Падаючий тест** (за зразком наявного для `page-notes`): маніфест `contrast` проходить `_check_tools`
  з `page == ("read", "mark", "change", "listen")`; `server.py` завантажується; файлів у теці лише перелічені.
- [ ] **Step 2: Приклад.**
  - `module.json`: `{"api": 2, "id": "contrast", "name": "Контраст", "version": "1.0.0", "roles": [], "tools": [{"id": "contrast", "label": "Контраст", "icon": "eye", "panel": "panel/index.html", "key": "K", "page": ["read", "mark", "change", "listen"]}]}`
    (іконку `eye` звірити з `app/icons.js`; нема — взяти наявну найближчу й поміняти в спеці).
  - `server.py`: докстрінг-коментар «функцій інструмента нема: уся логіка — у панелі» і порожнє тіло.
  - `panel/contrast.js` (класичний скрипт, як у `page-notes`): чисті функції `parseRgb`, `luminance`, `ratio`,
    `isLarge(fontSizePx, weight)` (≥ 24 px або ≥ 18,66 px і вага ≥ 700), `bgOf(node, byRef)` — найближчий предок
    (зі знімка) з непрозорим `background-color`, інакше білий; `findings(snapshot)`:
    - текст (`text` не порожній, `visible`) з контрастом < 4,5 (великий < 3) → `error` (< 3) чи `warn`, ярлик
      `Контраст N.N:1`, виправлення — чорний або білий колір тексту, що дає кращий контраст;
    - `input`/`select`/`textarea` без `aria-label`, `aria-labelledby`, `title` і без `label[for=id]` → `warn`
      «Немає підпису поля»;
    - `img` без `alt` і `[role=img]` без `aria-label` → `info` «Немає опису зображення».
  - Потік панелі: `deai.ready` → `deai.on("page", run)`; `run` = `deai.page.clearMarks()`, `snapshot({styles: […], attrs: true})`,
    `findings`, `mark` кожну, список (`.dk-list`): текст, ярлик, «Показати» (`reveal`), «Спробувати виправлення»
    (`setStyle` кольору; рядок стає «тимчасово виправлено», мітка — `ok`); унизу — «Тимчасових змін: N» і «Скасувати»
    (`revertAll` + `run`); «Вибрати елемент» (`pick` → перевірка одного вузла, підсвітка рядка). Тексти панелі —
    мовою з `deai.context().lang` (uk/en). Порожньо — `.dk-empty` «Проблем не знайдено».
    Помилка будь-якого виклику `deai.page.*` → `deai.toast("<дія>: " + e.code)` (живий тест чекає `not-allowed` у тості).
- [ ] **Step 3: Документація `authoring.md`.**
  - §7, таблиця ключів інструмента: рядок `page` (дозволи, вимога `read`, мінімальна версія Deai 0.39 — старіші
    відмовляють маніфесту як `unknown key`); `frame` — «not supported — use `page`».
  - Новий підрозділ §7 «Working with the mockup (`deai.page`)»: дозволи, таблиці методів, `Node`, події `page`,
    `page-click`, `page-hover`, коди помилок, ліміти, що тимчасове й коли відкочується, «досі наше», що не можна
    (атрибути, `url(`, розмітка), приклад «Контраст».
  - §8: абзац «A script inside the mockup — not yet» замінити на «Code inside the mockup — no; the core helper instead»
    (чому: походження канваса; що дає помічник).
  - Абзац «Коротко (uk)» на початку — одне речення про `page`.
- [ ] **Step 4: PASS** (`python3 -B -m unittest tests.test_module_example`), охоронець публічного репо.
  **Step 5: коміт** `docs(modules): помічник макета й приклад «Контраст»`.

### Task 10: наскрізний живий тест

**Files:** Create `tests/live/module-page.test.mjs` (`PORT_BASE = 48000`; додати в перелік, який стереже
`tests/live-ports.test.mjs`, якщо він ведеться списком).

- [ ] **Step 1: Тест** (зразок — `tests/live/module-example.test.mjs`: тимчасовий простір, копія
  `docs/modules/examples/contrast/`, довіра через шов `DEAI_TRUST_CONFIRM`, `/api/module-enable`):
  - макет-фікстура: кнопка `#cta` білим по `#9fd3b8`, `input` без підпису, `img` без `alt`, друга сторінка без проблем;
  - клавіша K → панель «Контраст» → у рамці макета `[data-deai-marks]` із трьома мітками (тони `error`/`warn`/`info`
    за `--t`), у панелі три рядки;
  - «Показати» на останньому рядку → елемент у видимій області рамки;
  - «Спробувати виправлення» на `#cta` → обчислений колір кнопки змінився, мітка `ok`; закрити панель хрестиком →
    колір повернувся, атрибута `style` у кнопки нема, `[data-deai-marks]` нема;
  - відкрити знову → перейти на другу сторінку (ліва панель) → панель отримала `page`, міток нема, «Проблем не знайдено»;
  - «Вибрати елемент» → клік по `#cta` → сторінка кліку не отримала (лічильник у фікстурі), панель показала вузол;
  - модуль-фікстура без `change` (окрема тека з тим самим кодом панелі й `page: ["read","mark"]`) — «Спробувати
    виправлення» дає тост помилки `not-allowed`, вигляд не змінився;
  - знімки для людини в `DEAI_SHOTS` (мітки, вибір, після закриття).
- [ ] **Step 2: PASS** (під замком, тимчасовий `HOME`). **Step 3: коміт** `test(live): помічник макета на прикладі «Контраст»`.

### Task 11 (контролер): реліз 0.39.0

- Фінальне ревʼю всієї гілки (Sonnet, свіжий погляд: ізоляція модуля від документа, відкат, події після закриття).
- `CHANGELOG.md` `[0.39.0]`: «Додано» (дозволи `page`, `deai.page`, блок довіри, приклад «Контраст»), «Відомі обмеження»
  (модуль не запускає свої бібліотеки в сторінці; помічник лише в «Макеті»; мітки й зміни не переживають
  перезавантаження). `package.json` → `0.39.0`.
- Охоронець публічного репо; релізний прогін: усі юніти + живі `page-agent`, `module-page`, `module-tools`,
  `module-example`, `canvas`, `ext-shell` по одному під замком.
- Злиття ff у живий `main`, анотований тег, перезапуск канваса з чистим env; push — лише за «да» власника.
