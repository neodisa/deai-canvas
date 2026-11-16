# Shell dialogs (stage В, 0.28.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every dialog of the canvas looks like the dark shell; delete confirmations happen in place (page menu, iteration dropdown, comment card); «Баг / ідея» and the update dialog open as popovers at their buttons.

**Architecture:** `app/ask.js` keeps its single-overlay contract and gains two pure helpers (`splitTitle`, `popPlace`), a title/body markup, `tellError`, and an anchored (non-modal) mode for `askForm`. A new pure module `app/inline-confirm.js` renders the in-place confirmation used by three hosts. CSS moves the existing `.cv-ask*`/form classes onto shell tokens. The commenter gets one opt-in flag (`removeComment(id, { confirmed: true })`).

**Tech Stack:** vanilla ES modules, `node --test`, Python `unittest`, Playwright live tests (Chromium), esbuild for `commenter/`.

**Spec:** `docs/superpowers/specs/2026-11-16-shell-dialogs-design.md` — read it fully first; it is owner-approved (prototype + text). Do not add UI the spec does not describe.

**Rigor tier:** medium (one implementer, one final reviewer) — but the live tests for the three delete paths are mandatory and every «nothing was deleted» check is proven by mutation.

---

## Ground rules (binding)

- Repo: this repository's root, branch `feat/shell-dialogs` (created by the controller from `main` after 0.27.1).
- Commit ONLY with explicit paths: `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<msg>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <paths>` (new files: `git add -- <path>` first). Never `git add -A`, `--amend`, `stash`, `reset`, never checkout another branch. Never stage `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` or `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`.
- Tests never touch ports 8765/4317, the owner's live install, real `~/.deai`, `~/deai-published`, `~/deai-work`, `~/.gitconfig`, Teams, any real Supabase or Jira. Never set `DEAI_HOME`/`DC_TASKS_FILE`. Python via `python3 -B`. No network installs (`commenter/node_modules` already exists — only `npm run build`).
- Never `pkill`/`killall` by pattern, never `while pgrep -f …`; kill by PID only.
- Unit: `node --test tests/*.test.mjs` (NOT `node --test tests/`), `node --test commenter/test/*.test.mjs`, `python3 -B -m unittest discover -s tests -q`.
- Live: ONE file at a time, always with a temporary HOME and the env preload:
  `HOME=$(mktemp -d) node --test --import ./tests/live/_env.mjs tests/live/<file>.test.mjs`
  (without the temp HOME the server under test loses its git identity and an unrelated test fails).
- Every new guard is proven by mutation: copy → break → red → `cp` back → `cmp` identical → green. Report each.
- Public repo: no real names, internal hosts, IPs, keys, usernames, tmp/scratchpad paths.
- Code comments, i18n, docs, commit messages in Ukrainian (like the repo); report to the controller in English.
- `app/ask.js` is also shipped to the public preview shell and must keep importing ONLY `./i18n.js` (see the comment near `fallback` in `app/ext-shell.js`). Do not import `icons.js` or anything else into it.

## File map

| File | Change |
|---|---|
| `app/ask.js` | `splitTitle`, `popPlace` (exported, pure); title/body markup; `tellError`; `askForm(…, { anchor, place })` popover mode |
| `app/inline-confirm.js` | NEW pure `confirmHTML()` |
| `app/styles.css` | dialogs on shell tokens; popover; `.cfm*`; `.cv-ctx--confirm`, `.dd--confirm`, `.cmt-acts--cfm` |
| `app/i18n.js` | split question/explanation keys; `delUnwrap`; 13 error titles; `cfm*` keys (uk+en) |
| `app/app.js` | 13 `tellError` calls; page menu confirm; `deleteNodes(ids, {confirmed})`; iteration confirm dispatch; comment confirm; feedback/update anchors + feedback draft |
| `app/shell-bar.js` | iteration dropdown: `delitask` item, confirm render |
| `app/comments-view.js` | confirm row in a card |
| `commenter/src/comment-layer.js` (+ `app/vendor/comment-layer.min.js`, `commenter/build-stamp.json` by build) | `removeComment(id, opts)` |
| `tests/_css-classes.mjs` | NEW shared extractor (moved from `tests/comments-view-css.test.mjs`) |
| `tests/dialogs-css.test.mjs` | NEW guard for dialog markup files |
| `tests/ask-dialogs.test.mjs` | NEW unit tests for `splitTitle`, `popPlace`, source patterns |
| `tests/inline-confirm.test.mjs` | NEW |
| `tests/shell-bar.test.mjs` | iteration dropdown confirm markup |
| live: `tests/live/panel-tree.test.mjs` (page menu), `tests/live/shell-bar.test.mjs` (iteration dropdown — no live file deletes iterations today), `tests/live/comments-panel.test.mjs`, `tests/live/feedback.test.mjs`, `tests/live/update.test.mjs` | new scenarios + selector updates |
| `CHANGELOG.md`, `package.json`, `README.md` | 0.28.0 |

---

### Task 1: Pure helpers in `ask.js` — `splitTitle` and `popPlace`

**Files:** Modify `app/ask.js` (after `focusBackTarget`, before `const INPUT_ID`). Create `tests/ask-dialogs.test.mjs`.

- [ ] **Step 1: Failing tests** — create `tests/ask-dialogs.test.mjs`:

```js
/**
 * Етап В (0.28.0): чисті шматки діалогів — заголовок/пояснення і місце поповера. Поведінку оболонки в браузері
 * покривають живі тести (`tests/live/feedback.test.mjs`, `update.test.mjs`, видалення — у файлах дерева й панелі).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { popPlace, splitTitle } from "../app/ask.js";

const src = readFileSync(new URL("../app/ask.js", import.meta.url), "utf8");

test("splitTitle: перший рядок — заголовок, решта — пояснення; краї обрізано, двокрапку в кінці заголовка прибрано", () => {
  assert.deepEqual(splitTitle("Видалити сторінку?\nТека зникне."), { title: "Видалити сторінку?", body: "Тека зникне." });
  assert.deepEqual(splitTitle("Вимкнути?\n\nТиша для всіх.\nДругий рядок.\n"), { title: "Вимкнути?", body: "Тиша для всіх.\nДругий рядок." });
  assert.deepEqual(splitTitle("Нова назва сторінки:"), { title: "Нова назва сторінки", body: "" });
  assert.deepEqual(splitTitle(""), { title: "", body: "" });
  assert.deepEqual(splitTitle(null), { title: "", body: "" });
});

test("popPlace: по центру якоря, не ближче 8 px до країв; хвостик — на центр якоря", () => {
  const a = { left: 600, top: 700, width: 36, height: 36, bottom: 736 };
  assert.deepEqual(popPlace(a, 360, 400, 1200, 800, "above"), { left: 438, top: 290, tip: 180, place: "above" });
  const edge = { left: 1180, top: 40, width: 30, height: 24, bottom: 64 };
  assert.deepEqual(popPlace(edge, 340, 300, 1200, 800, "below"), { left: 852, top: 74, tip: 328, place: "below" });
});

test("popPlace: не влазить згори — перевертається вниз, і навпаки; коли ніде — притискається до краю", () => {
  const top = { left: 100, top: 30, width: 36, height: 36, bottom: 66 };
  assert.equal(popPlace(top, 300, 200, 1200, 800, "above").place, "below");
  const bottom = { left: 100, top: 760, width: 36, height: 30, bottom: 790 };
  assert.equal(popPlace(bottom, 300, 200, 1200, 800, "below").place, "above");
  const tiny = popPlace(top, 300, 900, 1200, 800, "above");
  assert.equal(tiny.top, 8);
});

test("ask.js тягне лише i18n.js (його везе й публічне превʼю)", () => {
  const imports = [...src.matchAll(/^import .* from ["']([^"']+)["'];?$/gm)].map((m) => m[1]);
  assert.deepEqual(imports, ["./i18n.js"]);
});
```

(Check the numbers: anchor centre x = 618; left = 618 − 180 = 438; above = 700 − 10 − 400 = 290; tip = 618 − 438 = 180. Edge: centre 1195; left = min(1200 − 340 − 8, 1195 − 170) = 852; below = 64 + 10 = 74; tip = min(328, 1195 − 852 = 343) = 328.)

- [ ] **Step 2: Run, expect FAIL** — `node --test tests/ask-dialogs.test.mjs` (exports missing).

- [ ] **Step 3: Implement** in `app/ask.js`:

```js
/**
 * Текст питання → `{title, body}` (етап В): перший рядок — заголовок картки, решта — пояснення під ним.
 * Двокрапка в кінці заголовка — спадок підписів поля (`'Нова назва сторінки:'`), у заголовку вона зайва.
 */
export function splitTitle(text) {
  const s = String(text ?? '');
  const i = s.indexOf('\n');
  const title = (i < 0 ? s : s.slice(0, i)).trim().replace(/:\s*$/, '');
  return { title, body: i < 0 ? '' : s.slice(i + 1).trim() };
}

const POP_GAP = 10;   // від якоря до картки
const POP_EDGE = 8;   // від картки до краю вікна

/**
 * Де стати поповеру (етап В). `a` — прямокутник якоря (`getBoundingClientRect()`), `w`×`h` — розмір картки,
 * `vw`×`vh` — вікно, `place` — бажане `'above'|'below'`. По горизонталі — центр над якорем, але не ближче
 * `POP_EDGE` до країв; не влазить із бажаного боку, а з другого влазить — перевертається; ніде — притискається.
 * `tip` — x хвостика відносно картки (на центр якоря), у межах картки з запасом 12 px.
 */
export function popPlace(a, w, h, vw, vh, place = 'below') {
  const cx = a.left + a.width / 2;
  const left = Math.max(POP_EDGE, Math.min(vw - w - POP_EDGE, cx - w / 2));
  const above = a.top - POP_GAP - h;
  const below = a.bottom + POP_GAP;
  let p = place === 'above' ? 'above' : 'below';
  if (p === 'above' && above < POP_EDGE && below + h <= vh - POP_EDGE) p = 'below';
  else if (p === 'below' && below + h > vh - POP_EDGE && above >= POP_EDGE) p = 'above';
  const top = p === 'above' ? Math.max(POP_EDGE, above) : Math.max(POP_EDGE, Math.min(vh - h - POP_EDGE, below));
  const tip = Math.max(12, Math.min(w - 12, cx - left));
  return { left: Math.round(left), top: Math.round(top), tip: Math.round(tip), place: p };
}
```

- [ ] **Step 4: Run, expect PASS** — `node --test tests/ask-dialogs.test.mjs tests/ask-form.test.mjs tests/browser-dialogs.test.mjs`.
- [ ] **Step 5: Commit** `app/ask.js tests/ask-dialogs.test.mjs` — «feat(0.28.0): заголовок/пояснення й місце поповера — чисті шматки діалогів».

---

### Task 2: `ask.js` overlay — title markup, `tellError`, anchored `askForm`

**Files:** Modify `app/ask.js` (`overlay()`, exports). Test: `tests/ask-dialogs.test.mjs`.

- [ ] **Step 1: Failing source-pattern tests** — append to `tests/ask-dialogs.test.mjs` (this file style matches `tests/ask-form.test.mjs`: behaviour that needs a DOM is pinned by source; the live tests in Task 9 prove it in a browser):

```js
import { tellError } from "../app/ask.js";

test("заголовок — h2.cv-ask-title з id, пояснення — p.cv-ask-text; поле підписане заголовком", () => {
  assert.match(src, /createElement\('h2'\)/);
  assert.match(src, /className = 'cv-ask-title'/);
  assert.match(src, /className = 'cv-ask-text'/);
  assert.match(src, /setAttribute\('aria-labelledby', TITLE_ID\)/);
  assert.equal(/htmlFor = INPUT_ID/.test(src), false, "підпис поля тепер — заголовок, не <label>");
});

test("tellError — повідомлення з класом помилки й іконкою зі спрайта, без імпорту icons.js", () => {
  assert.equal(typeof tellError, "function");
  assert.match(src, /export const tellError = \(title, reason\) =>/);
  assert.match(src, /cv-ask--error/);
  assert.match(src, /'#i-warn'/);
});

test("поповер: без підкладки, клас cv-ask-pop, закриття повз/якорем — але не під час busy", () => {
  assert.match(src, /'cv-ask-pop'/);
  assert.match(src, /popPlace\(/);
  assert.match(src, /if \(busy \|\| formEl\?\.getAttribute\('aria-busy'\) === 'true'\) return;/);
  assert.match(src, /addEventListener\('pointerdown', onOutside, true\)/);
  assert.match(src, /removeEventListener\('pointerdown', onOutside, true\)/);
  assert.match(src, /removeEventListener\('blur', onBlur\)/);
  assert.match(src, /removeEventListener\('resize', place\)/);
});
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement in `overlay()`** (keep every existing comment and behaviour that is not named here):

1. Destructure two more options: `error = false` in the `overlay(text, kind, { … })` signature.
2. Replace the `head` block (the `<label>`/`<p>` creation) with:

```js
    /* Заголовок і пояснення (етап В): перший рядок тексту — `<h2>`, решта — абзац під ним (`splitTitle`).
       У формі заголовок — у розмітці викликача (`form.build`), тож тут нічого. */
    const TITLE_ID = 'cv-ask-title';
    let head = null;
    if (!isForm) {
      const { title, body } = splitTitle(text);
      head = document.createElement('h2');
      head.className = 'cv-ask-title';
      head.id = TITLE_ID;
      if (error) {
        /* Іконка — `<use>` на спрайт оболонки, а не імпорт `icons.js`: `ask.js` їде в публічне превʼю й мусить
           тягнути лише `i18n.js`. Помилки (`tellError`) показує лише оболонка, де спрайт є. */
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('class', 'ico'); svg.setAttribute('width', '16'); svg.setAttribute('height', '16');
        svg.setAttribute('aria-hidden', 'true');
        const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
        use.setAttribute('href', '#i-warn');
        svg.appendChild(use);
        head.appendChild(svg);
      }
      head.appendChild(document.createTextNode(title));
      boxEl.appendChild(head);
      if (body) {
        const p = document.createElement('p');
        p.className = 'cv-ask-text';
        p.textContent = body;
        boxEl.appendChild(p);
      }
      boxEl.setAttribute('role', kind === 'tell' ? 'alertdialog' : 'dialog');
      boxEl.setAttribute('aria-modal', 'true');
      boxEl.setAttribute('aria-labelledby', TITLE_ID);
      if (error) boxEl.classList.add('cv-ask--error');
    }
```

   Move `const TITLE_ID` to module scope next to `INPUT_ID` if your linter/tests prefer (the test only checks `setAttribute('aria-labelledby', TITLE_ID)`).
3. In the `kind === 'ask'` block remove `head.htmlFor = INPUT_ID;` and add `input.setAttribute('aria-labelledby', TITLE_ID);`.
4. **Popover mode** (only for `kind === 'form'` with `form.anchor`):

```js
    /* Поповер (етап В): форма біля кнопки, якою її відкрили, без підкладки — макет під нею живий. Якоря нема,
       він схований чи відʼєднаний — звичайна модальна картка. */
    const anchorEl = isForm && form.anchor && form.anchor.isConnected && form.anchor.getClientRects().length
      ? form.anchor : null;
```
   - Container: `scrim.className = anchorEl ? 'cv-ask-pop' : 'cv-ask-scrim';` and `boxEl.className = isForm ? (anchorEl ? 'cv-ask cv-ask--form cv-ask--pop' : 'cv-ask cv-ask--form') : 'cv-ask';` (the `error` class is added in step 2).
   - Declare `let place = null; let onOutside = null;` next to `let formEl = null; let busy = false;` (they must exist before `done` can run — `const done` reads them).
   - After `document.body.appendChild(scrim)` and the form build, when `anchorEl`:

```js
    if (anchorEl) {
      /* Форма відгуку сама каже `aria-modal="true"`; поповер не модальний — макет під ним живий. */
      formEl?.removeAttribute('aria-modal');
      const tip = document.createElement('span');
      tip.className = 'cv-ask-tip';
      boxEl.appendChild(tip);
      place = () => {
        const r = popPlace(anchorEl.getBoundingClientRect(), boxEl.offsetWidth, boxEl.offsetHeight, innerWidth, innerHeight, form.place);
        boxEl.style.left = `${r.left}px`;
        boxEl.style.top = `${r.top}px`;
        boxEl.dataset.place = r.place;
        tip.style.left = `${r.tip}px`;
      };
      place();
      addEventListener('resize', place);
      /* Клік повз картку — відповідь «скасовано», як Esc. Клік по самому якорю теж закриває, і той самий клік
         НЕ мусить відкрити форму знову: гасимо його одноразовим слухачем у capture на якорі (знімаємо за 600 мс,
         якщо pointerdown так і не став кліком — перетягування). Під час відправки (`busy` / `aria-busy`) — нічого. */
      onOutside = (e) => {
        if (boxEl.contains(e.target)) return;
        if (busy || formEl?.getAttribute('aria-busy') === 'true') return;
        if (anchorEl.contains(e.target)) {
          const swallow = (ev) => { ev.stopImmediatePropagation(); ev.preventDefault(); };
          anchorEl.addEventListener('click', swallow, { capture: true, once: true });
          setTimeout(() => anchorEl.removeEventListener('click', swallow, { capture: true }), 600);
        }
        done(cancelled);
      };
      document.addEventListener('pointerdown', onOutside, true);
      /* Клік у макет — це клік в iframe: до `document` оболонки він не долітає, зате вікно оболонки втрачає фокус.
         Ловимо `blur` і перевіряємо, що фокус пішов саме в рамку (а не в інше вікно ОС). */
      onBlur = () => setTimeout(() => {
        if (document.activeElement?.tagName !== 'IFRAME') return;
        if (busy || formEl?.getAttribute('aria-busy') === 'true') return;
        done(cancelled);
      }, 0);
      addEventListener('blur', onBlur);
    }
```
   (declare `let onBlur = null;` together with `place`/`onOutside`.)
   - In `done()` add (next to the keydown removal):
```js
      if (onOutside) document.removeEventListener('pointerdown', onOutside, true);
      if (onBlur) removeEventListener('blur', onBlur);
      if (place) removeEventListener('resize', place);
```
   - Focus back: the existing `focusBackTarget(lost, [opener, form?.focusBack?.()])` already returns focus to the opener (the anchor) — keep it.
   - The built forms already carry `role="dialog"` and `aria-labelledby` (e.g. `form.fb` → `#fb-h`); the box adds nothing in popover mode.
   - `onKey` (Esc, Tab trap) stays as is in both modes. Button order stays: «Скасувати» left of the danger/ok button, focus on «Скасувати» for `danger`/`choice` (the existing line in `overlay()`).
5. Exports:

```js
/**
 * Помилка дії (етап В): заголовок «що не вдалося», під ним причина (рядок сервера), іконка `warn`.
 * Замість `tell(t('errFailed', e.message))` там, де відомо, ЩО саме не вдалося.
 */
export const tellError = (title, reason) => overlay(`${title}\n${reason ?? ''}`, 'tell', { error: true });
```
   and change `askForm` to pass the new options through:
```js
export const askForm = (build, { onMount, onSubmit, focusBack, anchor = null, place = 'below' } = {}) =>
  overlay('', 'form', { form: { build, onMount, onSubmit, focusBack, anchor, place } });
```
   Extend the `askForm` doc comment with `anchor` / `place` (one line each).

- [ ] **Step 4: Run** `node --test tests/ask-dialogs.test.mjs tests/ask-form.test.mjs tests/browser-dialogs.test.mjs` — PASS. If an existing source-pattern test in `ask-form.test.mjs`/`browser-dialogs.test.mjs` pinned the old `<label>`/`<p>` head, update it to the new markup and say so in the report; keep what it guarded (single overlay, Esc, focus on Cancel for `danger`/`choice`).
- [ ] **Step 5: Commit** `app/ask.js tests/ask-dialogs.test.mjs` (+ any updated test) — «feat(0.28.0): заголовок діалогу, tellError, поповер askForm біля якоря».

---

### Task 3: Dark dialogs in CSS + class guard for dialog markup

**Files:** Modify `app/styles.css`. Create `tests/_css-classes.mjs`, `tests/dialogs-css.test.mjs`. Modify `tests/comments-view-css.test.mjs` (use the shared module).

- [ ] **Step 1: Shared extractor.** Create `tests/_css-classes.mjs` (not a `*.test.mjs`, so `node --test tests/*.test.mjs` does not run it on its own). It is the 0.27.1 `classesInView` generalised: the quoted-branch prefixes become a parameter and DOM-code forms are added for `ask.js`.

```js
/** Спільне для охоронців «кожен клас розмітки має стиль»: панель коментарів (0.27.1) і діалоги (етап В, 0.28.0). */
import { readFileSync } from "node:fs";

// Коментарі CSS не рахуються: `.cmt-x` у тексті коментаря — не правило (ревʼю 0.27.1).
export const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
export const hasRule = (cls) => new RegExp(`\\.${cls.replace(/[-]/g, "\\-")}(?![\\w-])`).test(css);

const NAME = /^[a-z][\w-]*[a-z0-9]$/;

/**
 * Класи з розмітки файлу:
 * - `class="…"` у шаблонах — літеральні шматки; `префікс${…}` — хвости з `dynamic` (префікса там нема — виняток, щоб
 *   новий динамічний клас не проходив повз охоронця);
 * - `quoted` — джерело RegExp-альтернатив: назви в лапках поза атрибутом (гілки тернарних виразів);
 * - `dom: true` — ще й DOM-код: `className = '…'`, `classList.add/toggle('…')`, `setAttribute('class', '…')`.
 */
export function classesIn(src, { dynamic = new Map(), quoted = "", dom = false } = {}) {
  const out = new Set();
  for (const m of src.matchAll(/class="([^"]*)"/g)) {
    // `${…}`-вставки всередині атрибута: беремо лише літеральні шматки, а гілки тернарних виразів — з лапок нижче
    const literal = m[1].replace(/\$\{[^}]*\}/g, " ");
    for (const c of literal.split(/\s+/)) if (NAME.test(c)) out.add(c);
    for (const d of m[1].matchAll(/([a-z][\w-]*-)\$\{/g)) {
      const tails = dynamic.get(d[1]);
      if (!tails) throw new Error(`динамічний клас «${d[1]}\${…}» без переліку хвостів у DYNAMIC`);
      for (const tail of tails) out.add(d[1] + tail);
    }
  }
  // `id="cmt-q"` — це id, а не клас: пропускаємо
  if (quoted) for (const m of src.matchAll(new RegExp(`(?<!\\bid=)["'\` ](${quoted})["'\`]`, "g"))) out.add(m[1]);
  if (dom) {
    const re = /(?:className\s*=\s*|classList\.(?:add|toggle)\(\s*|setAttribute\(\s*'class',\s*)(['"`])([^'"`]*)\1/g;
    for (const m of src.matchAll(re)) for (const c of m[2].split(/\s+/)) if (NAME.test(c)) out.add(c);
  }
  return out;
}
```

  In `tests/comments-view-css.test.mjs` delete the local `css`/`classesInView`/`hasRule`, import `{ css, classesIn, hasRule }` and call `classesIn(view, { dynamic: DYNAMIC, quoted: "cmt-[\\w-]+|icob|insp-[\\w-]+|panel-title" })` in both places. `NO_STYLE`, `DYNAMIC` and the three tests stay as they are (the third reads `css` — now the imported one).
  Prove the move: `node --test tests/comments-view-css.test.mjs` green; then the 0.27.1 mutation (`icob` → `icon-btn` in `app/comments-view.js`) must still go red; restore + `cmp`.

- [ ] **Step 2: Failing guard** `tests/dialogs-css.test.mjs`:

```js
/**
 * Етап В: кожен клас розмітки діалогів має правило в `app/styles.css` — та сама вада, що білі кнопки 0.27.0, не
 * мусить повторитись у діалогах. Розмітка: `app/ask.js` (DOM-код), `feedback-view.js`, `update-view.js`,
 * `space-dialogs.js`, `trust-view.js`, `inline-confirm.js` (рядки).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { classesIn, hasRule } from "./_css-classes.mjs";

const FILES = ["ask.js", "feedback-view.js", "update-view.js", "space-dialogs.js", "trust-view.js", "inline-confirm.js"];
/** Маркери без власного стилю — лише з причиною (заповнити після першого прогону, перевіривши кожен grep-ом). */
const NO_STYLE = new Map([]);
const DYNAMIC = new Map([]);
/** Назви в лапках поза `class="…"` і DOM-код `ask.js`. Префікси — ті, що є в цих файлах; новий префікс — додати сюди. */
const OPTS = { dynamic: DYNAMIC, quoted: "cv-[\\w-]+|cfm[\\w-]*", dom: true };

test("кожен клас розмітки діалогів має правило в styles.css", () => {
  const missing = [];
  for (const f of FILES) {
    const src = readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8");
    for (const c of classesIn(src, OPTS)) if (!NO_STYLE.has(c) && !hasRule(c)) missing.push(`${f}: ${c}`);
  }
  assert.deepEqual(missing.sort(), []);
});

test("винятки не гниють", () => {
  const all = new Set(FILES.flatMap((f) => [...classesIn(readFileSync(new URL(`../app/${f}`, import.meta.url), "utf8"), OPTS)]));
  for (const [c, why] of NO_STYLE) {
    assert.ok(why.length > 10, c);
    assert.ok(all.has(c), `${c}: уже не вживається`);
    assert.equal(hasRule(c), false, `${c}: стиль уже є`);
  }
});
```

  `inline-confirm.js` does not exist until Task 5: leave it out of `FILES` here and add it in Task 5 Step 7 (that step's commit includes `tests/dialogs-css.test.mjs`).

- [ ] **Step 3: Run** — record every missing class. For each: a real visual element → add a rule in Step 4; a pure hook (only used by JS/tests — prove with grep) → `NO_STYLE` with a reason; a false positive of the extractor (e.g. a word in a string that is not a class) → tighten the extractor, not the list.

- [ ] **Step 4: Restyle** in `app/styles.css`. Find every rule: `grep -n "cv-ask\|cv-form\|cv-field\|cv-lbl\|cn-check\|cv-color\|\.tr\b\|\.tr-\|\.up\b\|\.up-\|\.fb\b\|\.fb-" app/styles.css`. Replace light-content values with shell tokens using this mapping (apply it to every rule of those blocks; keep sizes, gaps, max-heights, widths and anything a source-pattern test pins — only colours/borders/shadows change):

  | Light (now) | Dark (shell) |
  |---|---|
  | `var(--card)`, `#fff` backgrounds of the box | `var(--s2)` |
  | `var(--border)` / `var(--g200)` / `var(--g450)` borders | `var(--line2)` (lists/pre blocks: `var(--line)`) |
  | `var(--g900)` text | `var(--hi)` |
  | `var(--g700)` text | `var(--mid)` |
  | `var(--g600)` text | `var(--dim)` |
  | `var(--g50)` button/pre backgrounds | `var(--s3)` (buttons), `var(--s1)` (pre/list/inputs) |
  | `var(--accent)` primary button / focus | `var(--sel)` bg + `var(--on-sel)` text; focus outline `var(--sel)` |
  | field focus (input/textarea/select) | `border-color: var(--sel)` |
  | `var(--bad-ink)` danger | `var(--bad)` bg + `var(--on-sel)` text; error text `var(--bad)` |
  | `0 0 0 2px var(--card)` (colour-circle ring) | `0 0 0 2px var(--s2)` |
  | scrim `rgba(21,29,25,.34)` | `rgba(13,21,17,.55)` |

  Then merge these into the existing rules (one `.cv-ask{…}` rule, not two) and add the new ones next to `.cv-ask-row`. Leave `.cv-ask label,.cv-ask p{…pre-wrap…}` as it is — `.cv-ask-text` is a `<p>`, and `splitTitle` already trims the edges:

```css
.cv-ask{border-radius:var(--r-lg);box-shadow:0 18px 50px rgba(0,0,0,.45);color:var(--hi)}
.cv-ask-title{margin:0;display:flex;align-items:flex-start;gap:8px;font-size:14px;font-weight:650;line-height:1.35;color:var(--hi);text-wrap:balance}
.cv-ask-text{margin:0;font-size:13px;line-height:1.5;color:var(--mid)}
.cv-ask--error .cv-ask-title .ico{flex:none;margin-top:1px;color:var(--bad)}
.cv-ask button{height:var(--h-ctl);padding:0 14px}
.cv-ask button:hover{background:var(--s4)}
.cv-ask button[data-a="ok"]:hover{background:var(--sel-hover)}
.cv-ask-pop{position:fixed;inset:0;z-index:250;pointer-events:none}
.cv-ask--pop{position:absolute;pointer-events:auto;max-width:calc(100vw - 16px)}
.cv-ask--pop:has(form.fb){width:360px}
.cv-ask--pop:has(form.up){width:340px}
.cv-ask-tip{position:absolute;width:12px;height:12px;margin-left:-6px;background:var(--s2);border:1px solid var(--line2);transform:rotate(45deg)}
.cv-ask--pop[data-place="above"] .cv-ask-tip{bottom:-7px;border-top:0;border-left:0}
.cv-ask--pop[data-place="below"] .cv-ask-tip{top:-7px;border-bottom:0;border-right:0}
```
  Keep `.cv-ask-list{…max-height:160px…}`.
  If `.cv-ask--pop:has(form.fb)` conflicts with `.cv-ask--form:has(.fb){width:560px}`, order/specificity must make the popover width win (the popover rule is more specific with two classes + `:has`; verify with the live test in Task 9).

- [ ] **Step 5: Run** `node --test tests/*.test.mjs` — fix every CSS source-pattern test that pinned a light colour by updating the expected token (never drop a pinned size/limit). List each in the report.
- [ ] **Step 6: Mutations** for the new guard: rename `.cv-ask-title{` → `.cv-ask-titleX{` → red; rename `.cv-ask-tip{` → red. Restore + `cmp`.
- [ ] **Step 7: Commit** `app/styles.css tests/_css-classes.mjs tests/dialogs-css.test.mjs tests/comments-view-css.test.mjs` (+ updated tests) — «feat(0.28.0): темні діалоги на токенах оболонки, охоронець класів діалогів».

---

### Task 4: Texts — titles, explanations, error titles

**Files:** Modify `app/i18n.js`, `app/app.js` (13 call sites). Test: `tests/ask-dialogs.test.mjs` (+ `tests/i18n-keys.test.mjs` runs as is).

- [ ] **Step 1: Audit.** List every i18n key passed to `ask(`, `askYesNo(`, `tell(`, `askChoice(` in `app/*.js` (`grep -n "ask(t(\|askYesNo(t(\|tell(t(\|askChoice(t(" app/*.js`). For each, uk and en: the first line must be a short question or statement (≤ 80 characters, no trailing explanation); the explanation goes after `\n`. Known to change (uk / en the same way):
  - `menuDeletePageConfirm`: `'Видалити сторінку?\nТека буде видалена (git-історія збережеться).'`
  - `inspTunerResetAllAsk`: `(n) => \`Скинути всі накручені зміни на цій сторінці (${n})?\nЗаписка Клоду лишиться.\``
  - `delTreeTitle`: `(name, n) => \`Видалити «${name}»?\nРазом із цим шаром буде видалено вкладені (${n}):\``
  - `delManyTitle`: `(n, total) => \`Видалити вибране (${n})?\nРазом із вкладеними зникне ${total}:\``
  - `menuDuplicateIterationPrompt`: `(label) => \`Нова ітерація — копія ${label}\nПримітка (необовʼязково)\``
  - `askPreviewPw`: first line `'Пароль превʼю цієї задачі'`, the rest of the current text after `\n`.
  - `delUnwrap`: `'Прибрати лише теку'` / `'Remove the folder only'`.
  Report every other key you changed and why. A long single statement that is not a question may stay as one line if it reads well as a heading — your call, listed in the report.

- [ ] **Step 2: Failing test** — append to `tests/ask-dialogs.test.mjs`:

```js
import { setLang, t } from "../app/i18n.js";

const ERR_TITLES = ["errTDupIter", "errTOpenTask", "errTSpaceSwitch", "errTRenameIter", "errTDeleteIter", "errTVcsPush",
  "errTVcsPull", "errTPublish", "errTTeamsMute", "errTPreviewPw", "errTRenamePage", "errTMovePage", "errTPagePublish"];

test("заголовки помилок дій — є в обох мовах і починаються з «Не вдалося» / «Could not»", () => {
  for (const lang of ["uk", "en"]) {
    setLang(lang);
    for (const k of ERR_TITLES) assert.match(t(k), lang === "uk" ? /^Не вдалося / : /^Could not /, `${lang}:${k}`);
  }
  setLang("uk");
});

test("кожен живий tell(t('errFailed', …)) у app.js замінено на tellError, крім мертвого pillMenu", () => {
  const app = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");
  const start = app.indexOf("function pillMenu(");
  const end = app.indexOf("\n}\n", start);
  const live = app.slice(0, start) + app.slice(end);
  assert.equal((live.match(/tell\(t\('errFailed'/g) || []).length, 0);
  assert.equal((live.match(/tellError\(t\('errT/g) || []).length, 13);
});

test("заголовок питання — короткий перший рядок", () => {
  setLang("uk");
  for (const [k, args] of [["menuDeletePageConfirm", []], ["delTreeTitle", ["Картка", 3]], ["inspTunerResetAllAsk", [2]]]) {
    const first = t(k, ...args).split("\n")[0];
    assert.ok(first.length <= 80 && /\?$/.test(first), `${k}: «${first}»`);
  }
});
```

- [ ] **Step 3: Implement.** Add to `app/i18n.js` (uk / en):

  | key | uk | en |
  |---|---|---|
  | `errTDupIter` | Не вдалося дублювати ітерацію | Could not duplicate the iteration |
  | `errTOpenTask` | Не вдалося відкрити задачу | Could not open the task |
  | `errTSpaceSwitch` | Не вдалося перемкнути простір | Could not switch the space |
  | `errTRenameIter` | Не вдалося перейменувати ітерацію | Could not rename the iteration |
  | `errTDeleteIter` | Не вдалося видалити ітерацію | Could not delete the iteration |
  | `errTVcsPush` | Не вдалося надіслати зміни | Could not push the changes |
  | `errTVcsPull` | Не вдалося підтягнути зміни | Could not pull the changes |
  | `errTPublish` | Не вдалося змінити публікацію | Could not change publishing |
  | `errTTeamsMute` | Не вдалося змінити сповіщення Teams | Could not change Teams notifications |
  | `errTPreviewPw` | Не вдалося змінити пароль превʼю | Could not change the preview password |
  | `errTRenamePage` | Не вдалося перейменувати сторінку | Could not rename the page |
  | `errTMovePage` | Не вдалося перемістити сторінку | Could not move the page |
  | `errTPagePublish` | Не вдалося змінити публікацію сторінки | Could not change the page publishing |

  In `app/app.js` import `tellError` with the other `ask.js` names and replace each live `tell(t('errFailed', <reason>))` with `tellError(t('<key>'), <reason>)`, keeping the reason expression the call passes today (`e.message`, or `requestErrText(e)` in the two git-sync calls) — 16 calls today, 3 of them inside `pillMenu`, so 13 change — per the spec table (`dupIteration` → `errTDupIter`; task switch → `errTOpenTask`; `BAR_ACTIONS.space` → `errTSpaceSwitch`; `renit` → `errTRenameIter`; `delit` → `errTDeleteIter`; `/api/vcs-push` → `errTVcsPush`; `/api/vcs-pull` → `errTVcsPull`; `togglepub` → `errTPublish`; `teamsnotify` → `errTTeamsMute`; `pubpw` → `errTPreviewPw`; `renamePage` → `errTRenamePage`; `movePage` → `errTMovePage`; `togglePagePublish` → `errTPagePublish`). Leave the three calls inside `pillMenu` untouched.

- [ ] **Step 4: Run** `node --test tests/*.test.mjs` — PASS.
- [ ] **Step 5: Commit** `app/i18n.js app/app.js tests/ask-dialogs.test.mjs` — «feat(0.28.0): питання — заголовок і пояснення, помилки кажуть, що не вдалося».

---

### Task 5: In-place confirmation — module + page menu

**Files:** Create `app/inline-confirm.js`, `tests/inline-confirm.test.mjs`. Modify `app/app.js` (`pageMenu`, `deleteNodes`), `app/i18n.js`, `app/styles.css`.

- [ ] **Step 1: Failing tests** `tests/inline-confirm.test.mjs`:

```js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { confirmHTML } from "../app/inline-confirm.js";

const app = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

test("confirmHTML: лише питання, «Ні» перед «Видалити», атрибути викликача, тексти екрановано", () => {
  const html = confirmHTML({ title: "Видалити «<b>»?", yes: "Видалити", no: "Ні",
    yesAttrs: 'data-a="delyes"', noAttrs: 'data-a="delno"' });
  assert.match(html, /^<div class="cfm" role="group" aria-label="Видалити «&lt;b&gt;»\?">/);
  assert.match(html, /<p class="cfm-t">Видалити «&lt;b&gt;»\?<\/p><div class="cfm-row">/);
  assert.ok(html.indexOf('class="cfm-no"') < html.indexOf('class="cfm-yes"'));
  assert.match(html, /<button type="button" class="cfm-no" data-a="delno">Ні<\/button>/);
  assert.match(html, /<button type="button" class="cfm-yes" data-a="delyes">Видалити<\/button>/);
});

test("меню сторінки: «Видалити» для yesno питає в меню, «Так» кличе deleteNodes з confirmed; choice — як було", () => {
  const body = app.slice(app.indexOf("function pageMenu("), app.indexOf("// ===== Режим «Огляд»"));
  assert.match(body, /model\.kind !== 'yesno'\) \{ close\(\); deleteNodes\(ids\); return; \}/);
  assert.match(body, /deleteNodes\(ids, \{ confirmed: true \}\)/);
  assert.match(body, /\.cfm-no'\)\?\.focus\(\)/);
  assert.equal(/on\('delete'/.test(body), false);
});

test("deleteNodes: confirmed пропускає лише питання yesno", () => {
  const body = app.slice(app.indexOf("async function deleteNodes("), app.indexOf("const deletePage ="));
  assert.match(body, /async function deleteNodes\(ids, \{ confirmed = false \} = \{\}\)/);
  assert.match(body, /if \(!confirmed && !\(await askYesNo\(t\('menuDeletePageConfirm'\)/);
});
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Module** `app/inline-confirm.js`:

```js
/**
 * Вбудоване підтвердження (етап В, 0.28.0): питання на місці дії — у меню сторінки, у дропдауні ітерації, у картці
 * коментаря. Чиста розмітка. «Ні» стоїть першим і бере фокус (викликач кличе `.focus()` на `.cfm-no`): Enter чи пробіл,
 * натиснуті не дивлячись, нічого не видаляють. `yesAttrs`/`noAttrs` — готові атрибути кнопок; значення в них викликач
 * екранує сам (`esc`).
 */
import { esc } from "./esc.js";

export function confirmHTML({ title, yes, no, yesAttrs = "", noAttrs = "" }) {
  return `<div class="cfm" role="group" aria-label="${esc(title)}"><p class="cfm-t">${esc(title)}</p>`
    + `<div class="cfm-row"><button type="button" class="cfm-no" ${noAttrs}>${esc(no)}</button>`
    + `<button type="button" class="cfm-yes" ${yesAttrs}>${esc(yes)}</button></div></div>`;
}
```

- [ ] **Step 4: i18n** (uk / en): `cfmNo: 'Ні'`/`'No'`; `cfmDelPage: (n) => \`Видалити сторінку «${n}»?\``/`(n) => \`Delete page «${n}»?\``; `cfmDelState: (n) => \`Видалити стан «${n}»?\``/`Delete state «${n}»?`; `cfmDelFolder: (n) => \`Видалити теку «${n}»?\``/`Delete folder «${n}»?`;. Node kinds are `KINDS = ["folder", "page", "state"]` (`app/tree-model.js`; `pageMenu` already has `const kind = f?.kind ?? 'page'`): `'state'` → `cfmDelState`, `'folder'` → `cfmDelFolder` (an empty tree folder), `'page'` → `cfmDelPage`. No explanation line under the question in any of the three places (owner, 16.11.2026: captions nobody asked for clutter the UI).

- [ ] **Step 5: CSS** (comments block of dialogs, near `.cv-ctx`):

```css
.cfm{display:flex;flex-direction:column;gap:6px;padding:8px;border-radius:var(--r-sm);background:color-mix(in srgb,var(--bad) 10%,transparent)}
.cfm-t{margin:0;font-size:12px;font-weight:600;line-height:1.35;color:var(--hi)}
.cfm-row{display:flex;justify-content:flex-end;gap:6px}
.cfm-no,.cfm-yes{height:var(--h-sm);padding:0 10px;border-radius:var(--r-sm);font:inherit;font-size:12px;cursor:pointer}
.cfm-no{border:1px solid var(--line2);background:var(--s3);color:var(--hi)}
.cfm-no:hover{background:var(--s4)}
.cfm-yes{border:1px solid var(--bad);background:var(--bad);color:var(--on-sel);font-weight:600}
.cfm-no:focus-visible,.cfm-yes:focus-visible{outline:2px solid var(--sel);outline-offset:2px}
.cv-ctx--confirm{width:260px;padding:4px}
```
  (`.cv-ctx button{…}` gives every button in the context menu its own look — make sure `.cfm-no`/`.cfm-yes` win inside `.cv-ctx`; if not, scope as `.cv-ctx .cfm-no` etc. Verify visually in Task 9.)

- [ ] **Step 6: Wiring** in `app/app.js`:
  - `import { confirmHTML } from './inline-confirm.js';`
  - `deleteNodes(ids, { confirmed = false } = {})`; in the `yesno` branch: `if (!confirmed && !(await askYesNo(t('menuDeletePageConfirm'), { yes: t('menuDeleteYes'), danger: true }))) return;` — the `choice` branch is unchanged (always asks).
  - In `pageMenu`, delete the line `on('delete', …)` and add after the other `on(…)` lines:

```js
  /* «Видалити» (етап В): для одного вузла без дітей меню саме стає питанням — підтвердження там, де дія.
     Тека з вмістом чи кілька вузлів — темна картка з переліком (`askChoice`), як було: перелік у меню не вміщається. */
  const delBtn = m.querySelector('[data-a="delete"]');
  if (delBtn) delBtn.onclick = (ev) => {
    const ids = multi ? [...panelSel] : [pageId];
    const model = deleteDialogModel(panelPages, ids);
    if (!model || model.kind !== 'yesno') { close(); deleteNodes(ids); return; }
    ev.stopPropagation();
    const name = f?.page.name || '';
    const titleKey = kind === 'state' ? 'cfmDelState' : (kind === 'folder' ? 'cfmDelFolder' : 'cfmDelPage');
    m.classList.add('cv-ctx--confirm');
    m.innerHTML = confirmHTML({ title: t(titleKey, name), yes: t('menuDeleteYes'), no: t('cfmNo'),
      yesAttrs: 'data-a="delyes"', noAttrs: 'data-a="delno"' });
    /* Клік усередині питання — не «повз»: інакше документний слухач закрив би меню раніше за кнопку. */
    m.addEventListener('click', (e) => e.stopPropagation());
    m.querySelector('[data-a="delno"]').onclick = () => close();
    m.querySelector('[data-a="delyes"]').onclick = () => { close(); deleteNodes(ids, { confirmed: true }); };
    positionCtxMenu(m, anchor);
    m.querySelector('.cfm-no')?.focus();
  };
```
  Why `ev.stopPropagation()` on the «Видалити» click: `pageMenu` closes itself from a document `click` listener; without it the same click that turns the menu into a question would close it.

- [ ] **Step 7:** add `"inline-confirm.js"` to `FILES` in `tests/dialogs-css.test.mjs` (Task 3). **Run** `node --test tests/*.test.mjs` — PASS. **Commit** `app/inline-confirm.js app/app.js app/i18n.js app/styles.css tests/inline-confirm.test.mjs tests/dialogs-css.test.mjs` — «feat(0.28.0): підтвердження видалення сторінки прямо в меню».

---

### Task 6: In-place confirmation — iteration dropdown

**Files:** Modify `app/shell-bar.js` (`crumbIter`, `barHTML`), `app/app.js` (bar click delegation ~line 2935, `paintBar` state, `BAR_ACTIONS.delit` ~line 2373), `app/i18n.js`, `app/styles.css`. Tests: `tests/shell-bar.test.mjs`, `tests/inline-confirm.test.mjs`.

**Note on the spec's wording.** The spec writes `BAR_ACTIONS.delit({ confirmed: true })`. Bar actions are called by the delegation as `BAR_ACTIONS[act](el.dataset.val, el, ev)` — the first argument is a `data-val` string. The flag therefore travels as `data-val="confirmed"` → `delit('confirmed')`. Same meaning, no new calling convention.

- [ ] **Step 1: Failing tests.**
  - In `tests/shell-bar.test.mjs` (reuse its model fixture with an `iter` crumb): `barHTML(model, { openDd: "iter" })` → the dropdown has `data-act="delitask"` and no `data-act="delit"`; `barHTML(model, { openDd: "iter", iterDelAsk: true })` → contains `class="dd dd--confirm"`, `class="cfm"`, `class="cfm-yes" data-act="delit" data-val="confirmed"`, `class="cfm-no" data-act="delitno"`, the title `Видалити ${it.label}?` (the crumb's own label — `crumbIter` renders `it.label`), and NO `data-act="iter"` list items; `barHTML(model, { openDd: null, iterDelAsk: true })` → no `cfm` at all.
  - In `tests/inline-confirm.test.mjs` (source patterns on `app/app.js`):

```js
test("дропдаун ітерації: delitask питає на місці, delit(val) пропускає питання лише з 'confirmed'", () => {
  assert.match(app, /if \(act === 'delitask'\) \{ iterDelAsk = true; paintBar\(\);/);
  assert.match(app, /val === 'confirmed' \|\| await askYesNo\(t\('menuDeleteIterationConfirm'/);
  assert.match(app, /if \(openDd !== 'iter'\) iterDelAsk = false;/);
});
```

- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - i18n: `cfmDelIter: (l) => \`Видалити ${l}?\``/`Delete ${l}?`.
  - `shell-bar.js`: import `confirmHTML`; change the signature to `crumbIter(model, openDd, iterDelAsk = false)` and the caller in `barHTML` to `crumbIter(model, openDd, !!state?.iterDelAsk)`; the delete item becomes `ddItem({ act: "delitask", icon: "trash", title: t("delIteration"), danger: true })`; when `iterDelAsk` is true, `dd` is ONLY:
    ```js
    `<div class="dd dd--confirm">${confirmHTML({ title: t("cfmDelIter", it.label),
      yes: t("menuDeleteYes"), no: t("cfmNo"), yesAttrs: 'data-act="delit" data-val="confirmed"', noAttrs: 'data-act="delitno"' })}</div>`
    ```
    Keep everything else in `crumbIter` unchanged (`${open ? dd : ""}` already hides it when the dropdown is closed).
  - CSS: `.dd--confirm{width:260px;padding:4px}`.
  - `app/app.js`:
    - `let iterDelAsk = false;` next to `let openDd = null;`; add `iterDelAsk` to the state object passed to `barHTML` (around the `openDd,` property, ~line 1012).
    - At the top of `paintBar()`: `if (openDd !== 'iter') iterDelAsk = false;`
    - In the bar click delegation (`bar.addEventListener('click', …)`), right after `const act = el.dataset.act;` and BEFORE `openDd = null;`:
      ```js
      /* «Видалити ітерацію» в дропдауні (етап В): дропдаун лишається відкритим і стає питанням. */
      if (act === 'delitask') { iterDelAsk = true; paintBar(); bar.querySelector('.dd--confirm .cfm-no')?.focus(); return; }
      ```
    - `BAR_ACTIONS.delitno = () => {};` (the delegation already closes the dropdown before dispatch).
    - `BAR_ACTIONS.delit = async (val) => { … const go = val === 'confirmed' || await askYesNo(t('menuDeleteIterationConfirm', label), { yes: t('menuDeleteYes'), danger: true }); … }` — the palette (`shell-palette.js`, `act: "delit"`) calls it with no value → the dark card, as before.
    - Esc while the dropdown is open must close it (existing behaviour) — it resets `iterDelAsk` through `paintBar`.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs` — PASS. **Commit** `app/shell-bar.js app/app.js app/i18n.js app/styles.css` + tests — «feat(0.28.0): підтвердження видалення ітерації в дропдауні».

---

### Task 7: In-place confirmation — comment card + commenter flag

**Files:** Modify `app/comments-view.js`, `app/app.js` (`cmtdel`, new `cmtdelyes`/`cmtdelno`, panel state, Esc), `app/i18n.js`, `commenter/src/comment-layer.js`; rebuild `app/vendor/comment-layer.min.js` + `commenter/build-stamp.json`. Tests: `tests/comments-view.test.mjs`, `tests/comments-wiring.test.mjs`, `commenter/test/*.test.mjs`.

- [ ] **Step 1: Failing tests.**
  - `tests/comments-view.test.mjs`:
    ```js
    test("кошик у картці: delAsk — рядок дій стає питанням, «Скасувати» перед «Видалити»", () => {
      const html = commentsPanelHTML(base({ delAsk: "a", snapshot: { iteration: "3", comments: [C({ id: "a", n: 1 })] } }));
      assert.match(html, /<div class="cmt-acts cmt-acts--cfm"><div class="cfm"/);
      assert.match(html, /class="cfm-no" data-act="cmtdelno">Скасувати</);
      assert.match(html, /class="cfm-yes" data-act="cmtdelyes" data-val="a">Видалити</);
      assert.equal(html.includes('data-act="cmtdel"'), false);
    });
    ```
  - `tests/comments-wiring.test.mjs` (source patterns, same extraction style as the file uses for actions): `cmtdel` sets `cmtDelAsk = id` and paints (no `removeComment`); `cmtdelyes` requires `cmtDelAsk === id` and calls `removeComment(id, { confirmed: true })`; `cmtdelno` clears.
  - `commenter/test/` (follow that folder's style): `removeComment(id, { confirmed: true })` does not call `confirm`; `removeComment(id)` still calls it and returns early when it answers false.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - i18n: `cfmDelCmt: 'Видалити назавжди?'`/`'Delete for good?'`.
  - `comments-view.js`: import `confirmHTML`; in `cardHTML`, before building `acts`, if `c.id === st.delAsk` →
    ```js
    acts = `<div class="cmt-acts cmt-acts--cfm">${confirmHTML({ title: t("cfmDelCmt"), yes: t("cmtDelete"), no: t("cmtCancel"),
      yesAttrs: `data-act="cmtdelyes" data-val="${esc(c.id)}"`, noAttrs: 'data-act="cmtdelno"' })}</div>`;
    ```
    (and skip the normal action buttons for that card). Add `delAsk` to the `st` doc comment.
  - CSS: `.cmt-acts--cfm{display:block}` and `.cmt-acts--cfm .cfm{margin-top:2px}`.
  - `app/app.js`: `let cmtDelAsk = null;`; pass `delAsk: cmtDelAsk` in the panel state (where `filter: cmtFilter` is passed, ~line 1753);
    ```js
      cmtdel: (id) => { cmtDelAsk = id; paintComments(); cmtEl.querySelector('.cmt-acts--cfm .cfm-no')?.focus(); },
      cmtdelyes: (id) => { if (cmtDelAsk !== id) return; cmtDelAsk = null; cmtLayer()?.removeComment(id, { confirmed: true }); paintComments(); },
      cmtdelno: () => { cmtDelAsk = null; paintComments(); },
    ```
    - Esc: the panel closes on `if (cmtFree && cmtOpen && ev.key === 'Escape') { setCommentsOpen(false); return; }` (keydown handler, ~line 8015). Directly above it add:
      ```js
      /* Esc при питанні «Видалити назавжди?» (етап В) знімає лише питання — панель лишається. */
      if (cmtFree && cmtOpen && cmtDelAsk && ev.key === 'Escape') { cmtDelAsk = null; paintComments(); return; }
      ```
    - Click outside the question (spec: «Esc або клік повз — закрити, нічого не видаливши»):
      ```js
      /* Клік повз питання в картці — «ні». Capture і pointerdown: спрацює раніше за будь-який клік, що перемалює панель.
         Клік у макеті (iframe) сюди не долітає — питання лишається, нічого не видаляючи. */
      document.addEventListener('pointerdown', (ev) => {
        if (cmtDelAsk && !ev.target.closest?.('.cmt-acts--cfm')) { cmtDelAsk = null; paintComments(); }
      }, true);
      ```
    - Reset `cmtDelAsk = null` everywhere `cmtSel = null; cmtEditing = null;` is reset today (`grep -n "cmtSel = null" app/app.js` — 4 places: panel close, task switch, snapshot reset, mode off).
  - `commenter/src/comment-layer.js` `removeComment`:
    ```js
    removeComment(id, opts) {
      const c = this.comments.find((x) => x.id === id); if (!c) return;
      // Оболонка Deai (етап В) питає сама — у картці своєї панелі — і передає `{ confirmed: true }`.
      // Власна панель коментатора (сторінка без host, превʼю) — як було, з confirm().
      if (!(opts && opts.confirmed === true) && typeof confirm === 'function' && !confirm('Delete this comment permanently?')) return;
    ```
    The delegated `act === 'delete'` call in the commenter's own panel stays `this.removeComment(id)`.
  - Build: `cd commenter && npm run build` (no `npm ci` — offline). Commit the source, `app/vendor/comment-layer.min.js` and `commenter/build-stamp.json` together; the stamp test (`grep -ln "build-stamp" tests/*.test.mjs`) must stay green.
- [ ] **Step 4: Run** `node --test tests/*.test.mjs` and `node --test commenter/test/*.test.mjs` — PASS. **Mutation:** drop `opts.confirmed === true` check (always skip confirm) → the commenter test red; restore + `cmp`.
- [ ] **Step 5: Commit** — «feat(0.28.0): видалення коментаря питає в картці панелі, коментатор приймає confirmed».

---

### Task 8: Popovers — «Баг / ідея» with a draft, update

**Files:** Modify `app/app.js` (`BAR_ACTIONS.feedback`, `BAR_ACTIONS.update`, `openFeedback`, `openUpdateDialog`). Test: `tests/inline-confirm.test.mjs` or a new `tests/popovers-wiring.test.mjs` (source patterns).

- [ ] **Step 1: Failing tests** (source patterns on `app/app.js`):
  - `feedback: (val, el) => openFeedback(el?.closest?.('#hud') ? el : null)`;
  - `openFeedback(anchor = null)` passes `anchor, place: 'above'` to `askForm`;
  - a module-level `fbDraft` is passed into `feedbackDialogHTML({ ...(fbDraft || {}), … })`, updated on `input`/`change` in `onMount`, and set to `null` after a successful send (the `return undefined;` success path);
  - `update: (val, el) => openUpdateDialog(el?.classList?.contains('upd-pill') ? el : null)` and `openUpdateDialog(anchor = null)` passes `anchor, place: 'below'`;
  - `updatenotes` keeps calling `openUpdateDialog()` with no anchor.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.**
  - Draft helper (in `app/app.js`, next to `openFeedback`):
    ```js
    /* Чернетка відгуку (етап В): живе в памʼяті вкладки до успішної відправки — поповер закривається кліком повз,
       і набране не мусить пропадати. */
    let fbDraft = null;
    const fbDraftOf = (form) => {
      const v = formValues(form.elements);
      return { kind: v.kind, text: v.text, contact: v.contact, includeDiag: v.diag, includeShot: v.shot };
    };
    ```
    (`formValues` is exported by `ask.js` — import it.) Check `feedbackDialogHTML` reads exactly these names (`x.kind`, `x.text`, `x.contact`, `x.includeDiag`, `x.includeShot`); if a name differs, adapt and say so.
  - In `openFeedback(anchor = null)`: `feedbackDialogHTML({ ...(fbDraft || {}), shot: …, shotUrl: …, previewFailed: …, previewText: … })`; in `onMount(form)` add `const keep = () => { fbDraft = fbDraftOf(form); }; form.addEventListener('input', keep); form.addEventListener('change', keep);`; on the success path before `return undefined;` set `fbDraft = null;`; pass `anchor, place: 'above'` to `askForm`. `focusBack` stays.
    If the preview failed (`previewFailed`), the diag checkbox must stay off even if the draft had it on — keep the existing rule that the markup enforces.
  - `openUpdateDialog(anchor = null)` → `askForm(…, { …, anchor, place: 'below' })`. Applying the update already runs inside `onSubmit`, so ask.js `busy` is set for its whole duration — the popover's outside-click and anchor-click checks (Task 2) cover it with no extra code.
  - BAR_ACTIONS as in Step 1.
- [ ] **Step 4: Run** unit suite — PASS. **Commit** `app/app.js` + test — «feat(0.28.0): «Баг / ідея» і оновлення — поповери біля своїх кнопок, чернетка відгуку живе до відправки».

---

### Task 9: Live tests

Run each touched live file alone with the temp-HOME command from the ground rules.

- [ ] **Step 1: Existing files.** Run every live file that touches dialogs — the list is `grep -lE "cv-ask|cv-form|askYesNo|data-form=" tests/live/*.test.mjs` plus `panel-tree`, `shell-bar`, `comments-panel`, `feedback`, `update`, `update-apply` — one at a time. Fix only what the new markup changed: `.cv-ask p`/`label` reads → `.cv-ask-title` / `.cv-ask-text`; feedback/update opened via island/pill now live in `.cv-ask-pop` (not `.cv-ask-scrim`); page/iteration delete now asks in place. Never delete or loosen an assertion's intent; list every change.
- [ ] **Step 2: New scenarios (mandatory).** In the file with the closest fixture for each:
  1. **Page menu** (`panel-tree.test.mjs`): right-click/«⋯» on a page without children → «Видалити» → `.cv-ctx .cfm` visible, focus on `.cfm-no`; (a) Esc → menu gone, the page folder still exists on disk and in `pages.json`; (b) reopen → «Видалити» → click outside → still exists; (c) reopen → «Видалити» → «Ні» → still exists; (d) reopen → «Видалити» → «Видалити» → gone on disk and from the tree. A folder WITH children → «Видалити» → the dark modal `.cv-ask-scrim .cv-ask-list` with the children listed (no inline confirm).
  2. **Iteration dropdown** (`shell-bar.test.mjs`; the fixture needs at least two iterations — create one through the UI «Нова ітерація» if the fixture has one): open the iteration crumb dropdown → «Видалити ітерацію» → `.dd--confirm .cfm` with focus on `.cfm-no`; (a) Esc, (b) click outside the bar, (c) «Ні» → each time the iteration folder still exists on disk; (d) «Видалити» → gone. From the palette (⌘K → delete iteration) → the dark modal `.cv-ask-scrim` asks.
  3. **Comment card** (`comments-panel.test.mjs`): trash → `.cmt-acts--cfm` with focus on «Скасувати»; (a) Esc → the comment is still in the local store (the file/endpoint the fixture already reads) and the panel is still open; (b) click elsewhere in the panel → still there; (c) «Скасувати» → still there; (d) «Видалити» → gone from the store. No native dialog was raised in the whole scenario (`page.on('dialog')` counter stays 0).
  4. **Feedback** (`feedback.test.mjs`): click the island «Баг / ідея» → `.cv-ask-pop .cv-ask--pop form[data-form=feedback]` above the button (box bottom < button top), no `.cv-ask-scrim`, focus in `#fb-text`; type text → click on the canvas → popover gone; reopen → the text is still there; click the island button again while open → closed, not reopened; send (the fixture's fake endpoint) → reopen → empty. From ⌘K → the modal (`.cv-ask-scrim`).
  5. **Update** (`update.test.mjs`, its local test manifest, no network): click the version pill → `.cv-ask-pop form.up` below the pill (box top > pill bottom); Esc closes; focus returns to the pill.
  6. **Looks**: in one dialog of each kind (yes/no, choice, form, popover) the computed `background-color` of `.cv-ask` is not white (`rgb(255, 255, 255)`), and a `.cfm-yes` is not the browser default.
- [ ] **Step 3: Mutations** (each red, then restore + `cmp`):
  - `deleteNodes(ids, { confirmed: true })` → `deleteNodes(ids)` in the page-menu «Так» path → scenario 1(d) red (a second dialog appears / nothing deleted);
  - remove `e.stopPropagation()` from the page-menu confirm click guard → scenario 1 red;
  - `val === 'confirmed' ||` → `true ||` in `delit` → the palette scenario red (deletes without asking);
  - comment card «Видалити» calling `removeComment(id)` without the flag → scenario 3 red (native dialog fired / not deleted);
  - `cmtdel` calling `removeComment(id, { confirmed: true })` straight away (no question) → scenario 3(a) red;
  - drop the `delitask` early `return` in the bar delegation → scenario 2 red;
  - drop `fbDraft = null` on success → scenario 4 red.
- [ ] **Step 4: Commit** the live files — «test(0.28.0): живі — три вбудовані підтвердження, поповери, темні діалоги».

---

### Task 10: Docs and version

- [ ] `CHANGELOG.md`: `## [0.28.0] — <date>` above `[0.27.1]`, format like `[0.27.0]`: «Змінено» — dark dialogs with title/explanation; errors name the action; delete asks in place (page menu, iteration dropdown, comment card); feedback and update are popovers; feedback draft. «Не змінено» — Esc closes, focus on «Скасувати» for dangerous actions, folder-with-contents and palette deletes still ask in a centred card; the commenter's own panel outside the shell still uses the browser dialog.
- [ ] `package.json` → `"version": "0.28.0"`.
- [ ] `README.md`: if it describes dialogs, deleting pages/iterations or feedback — update; otherwise nothing.
- [ ] Full suites: `node --test tests/*.test.mjs`, `node --test commenter/test/*.test.mjs`, `node tests/inspector-core.test.mjs`, `HOME=$(mktemp -d) python3 -B -m unittest discover -s tests -q`, same for `-s bin -p 'test_*.py'` and `-s app -p 'test_*.py'`. All green.
- [ ] Commit `CHANGELOG.md package.json` (+ README) — «docs(0.28.0): CHANGELOG, версія».

---

### Controller-only (not for the implementer)

- Final review (one Sonnet reviewer) against the spec.
- Release run: full unit + Python + live (sequential, temp HOME), build determinism of `commenter/` (copy, `npm run build`, byte compare), forbidden-list guard (`DEAI_FORBIDDEN_LIST=… DEAI_REQUIRE_FORBIDDEN_LIST=1 python3 -B -m unittest tests.test_no_internal_addresses`).
- Visual check on the live canvas next to the prototype; the three deletes only on a scratch page/iteration/comment in a non-LIGA test task.
- Merge, tag `v0.28.0`; push only with the owner's OK.
