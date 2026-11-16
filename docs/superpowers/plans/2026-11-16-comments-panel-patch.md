# Comments panel patch 0.27.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the comments panel shipped in 0.27.0 so it matches the prototype the owner approved on 16.11.2026: styled header buttons, the filter as its own row with counts, «Для Claude» = what Claude actually takes, and a note under both addressee chips.

**Architecture:** Pure model (`app/comments-model.js`) gains the new filter order, the «for Claude» rule and per-tab counts. The pure view (`app/comments-view.js`) renders the header, filter row, hint and card tweaks; CSS lives in `app/styles.css`. Wiring (`app/app.js`) changes only the default filter and the overview audiences; the workplace audiences live in `app/serve.py` (`DUAL_AUDIENCES_JS`) and must stay identical to `app/i18n.js`. A new structural test makes «class without a style» impossible to ship again.

**Tech Stack:** vanilla ES modules, `node --test`, Python `unittest`, Playwright live tests (Chromium).

**Spec:** `docs/superpowers/specs/2026-11-16-comments-panel-patch-design.md` (read it first — every decision there is the owner's).

**Rigor tier:** medium — one implementer for all tasks, one reviewer at the end, then the controller does the release run and the live/visual check.

---

## Ground rules (read before any step)

- Repo `~/Liga Tools/deai-canvas-dev`, branch `fix/comments-panel-0.27.1` (already created from `main` d8e1b1c; the spec commit is on it).
- Commit ONLY like this, with explicit paths (never `git add -A`, never `--amend`, `stash`, `reset`, never checkout other branches):
  `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<msg>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <paths>`
  (new files: `git add -- <path>` first).
- Never stage `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` or `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`.
- Tests never touch ports 8765/4317, `~/Liga Tools/deai-canvas`, real `~/.deai`, `~/deai-published`, `~/deai-work`, `~/.gitconfig`, Teams, any real Supabase or Jira. Never set `DEAI_HOME`/`DC_TASKS_FILE`. Python via `python3 -B`.
- Processes: never `pkill`/`killall` by pattern, never `while pgrep -f …`; kill only by PID.
- Live tests: ONE file at a time: `node --test tests/live/<file>.test.mjs`.
- Every new guard is proven by mutation: break the code → the test goes red → restore byte-exact (`cmp` against a copy) → green. Report each mutation.
- Unit commands: `node --test tests/` (JS), `python3 -B -m unittest discover -s tests -p 'test_*.py'` (Python; long — run the touched files during work, the full suite once at the end).
- Repo is PUBLIC: no real names, internal hosts, IPs, keys, usernames or tmp/scratchpad paths in code, tests, docs or commit messages.
- Language: code comments, i18n, docs and commit messages in Ukrainian like the rest of the repo; your report to the controller in English.

## File map

| File | Change |
|---|---|
| `app/comments-model.js` | `FILTERS` order, `forClaude`, `passFilter`, new `filterCounts` |
| `app/comments-view.js` | header (`icob`, icon, total only without filter), filter row + counts + `+N` + hint, card number colour, icon actions class, badge |
| `app/styles.css` | `--local-pin` token; `.cmt-filter*`, `.cmt-fn`, `.cmt-fnew`, `.cmt-fhint`, `.cmt-ib`, `.cmt-n--local`, header icon colour, card head wrap; drop dead `.cmt-ch*` |
| `app/i18n.js` | new keys `audChipLocalNote`, `cmtFHintLocal`, `cmtFHintTeam`, `cmtFHintAll`; new texts for `audChipTeamNote`, `cmtAssignedBadge` (uk + en) |
| `app/app.js` | default filter `'local'`; overview local audience gets `note` |
| `app/serve.py` | `DUAL_AUDIENCES_JS` gets `localNote` and the new team note |
| `tests/comments-model.test.mjs`, `tests/comments-view.test.mjs`, `tests/comments-wiring.test.mjs`, `tests/test_comments_role.py` | updated/new assertions |
| `tests/comments-view-css.test.mjs` | NEW structural guard |
| `tests/live/comments-team.test.mjs` (+ others only if they fail) | default tab; new scenario |
| `CHANGELOG.md`, `package.json`, `README.md` | 0.27.1 |

---

### Task 1: Model — filter order, «for Claude» rule, tab counts

**Files:**
- Modify: `app/comments-model.js` (the `FILTERS` / `passFilter` block, ~lines 22–29; add `filterCounts` after `openCount`)
- Test: `tests/comments-model.test.mjs`

- [ ] **Step 1: Update/add failing tests** in `tests/comments-model.test.mjs`.

Change the import line to also import `filterCounts` and `forClaude`:

```js
import { FILTERS, assignedToClaude, audOf, commentSections, filterCounts, forClaude, matchQuery, openCount, shotSrc } from "../app/comments-model.js";
```

In the test «audOf: без _aud — локальний; …» replace the last assertion with:

```js
  assert.deepEqual(FILTERS, ["local", "project", "all"], "порядок вкладок — рішення власника 16.11.2026");
```

Replace the test «commentSections: фільтр адресата local / project / all» with:

```js
const ASG = { comments: [...MIX.comments, A("p3", 5, "project", { meta: { assignee: "claude" } })] };

test("commentSections: «Для Claude» = локальні + доручені командні; «Команда» — усі командні", () => {
  const ids = (f) => { const s = commentSections(ASG, { filter: f }); return [...s.open, ...s.closed].map((c) => c.id).sort(); };
  assert.deepEqual(ids("all"), ["l1", "l2", "p1", "p2", "p3"]);
  assert.deepEqual(ids("local"), ["l1", "l2", "p3"]);
  assert.deepEqual(ids("project"), ["p1", "p2", "p3"]);
  assert.equal(forClaude(A("x", 9, "project", { meta: { assignee: "claude" } })), true);
  assert.equal(forClaude(A("x", 9, "project")), false);
  assert.equal(forClaude(A("x", 9)), true);
});

test("filterCounts: відкриті поточні за правилом вкладки; fresh — відкриті нові командні; пошук не враховано", () => {
  const snap = { comments: [...ASG.comments, A("e1", 6, "project", { scope: "earlier" }), A("q", 7, "project")] };
  assert.deepEqual(filterCounts(snap, new Set(["q", "p2", "l1"])), { local: 3, project: 3, all: 5, fresh: 1 });
  assert.deepEqual(filterCounts(snap), { local: 3, project: 3, all: 5, fresh: 0 });
  assert.deepEqual(filterCounts(null), { local: 0, project: 0, all: 0, fresh: 0 });
});
```

(Check against `MIX`: l1, l2 local open; p1 project open; p2 project resolved; p3 project open assigned; `snap` adds e1 earlier-scope and q open project. Open current: l1, l2, p1, p3, q → all 5; local rule: l1, l2, p3 → 3; project: p1, p3, q → 3; fresh: q only, because p2 is resolved and l1 is local.)

The test «commentSections: фільтр діє й на «нові»; openCount — усі адресати» must stay green unchanged (fresh p1 unassigned → not in «Для Claude»).

- [ ] **Step 2: Run, expect FAIL**

Run: `node --test tests/comments-model.test.mjs`
Expected: FAIL — `filterCounts`/`forClaude` are not exported, `FILTERS` order differs.

- [ ] **Step 3: Implement** in `app/comments-model.js`. Replace the `FILTERS` comment, constant and `passFilter` with:

```js
/** Вкладки фільтра панелі — у ЦЬОМУ порядку (рішення власника 16.11.2026: основна робота — з Claude, «Усі» — третя). */
export const FILTERS = ["local", "project", "all"];
/** «Для Claude» — те, що Claude бере в роботу: локальні + доручені йому командні. Те саме правило, що `for_agent`
 *  у `app/serve.py` і `bin/inbox.py` за замовчуванням; інакше вкладка обіцяла б більше або менше, ніж бачить агент. */
export const forClaude = (c) => audOf(c) === "local" || assignedToClaude(c);
const passFilter = (c, f) => (f === "local" ? forClaude(c) : f === "project" ? audOf(c) === "project" : true);
```

After `openCount` add:

```js
/** Числа на вкладках фільтра: відкриті поточні за правилом кожної вкладки (пошук НЕ враховано — числа про сторінку,
 *  а не про запит) і `fresh` — відкриті нові командні (той самий відбір, що розділ «Нові від команди»). */
export function filterCounts(snapshot, fresh = null) {
  const all = list(snapshot);
  const cur = all.filter((c) => c.status === "open" && c.scope === "current");
  return {
    local: cur.filter(forClaude).length,
    project: cur.filter((c) => audOf(c) === "project").length,
    all: cur.length,
    fresh: all.filter((c) => c.status === "open" && audOf(c) === "project" && !!(fresh && fresh.has(c.id))).length,
  };
}
```

- [ ] **Step 4: Run, expect PASS** — `node --test tests/comments-model.test.mjs`.
- [ ] **Step 5: Commit** `app/comments-model.js tests/comments-model.test.mjs` — «feat(0.27.1): «Для Claude» = локальні + доручені, порядок вкладок, числа вкладок».

---

### Task 2: View, CSS and texts — header, filter row, hint, card

**Files:**
- Modify: `app/comments-view.js` (whole `commentsPanelHTML`, `btn`, `cardHTML` head)
- Modify: `app/styles.css` (`:root`; the «Панель «Коментарі» (0.26.0)» block near the end, ~lines 1850–1888)
- Modify: `app/i18n.js` (uk block ~lines 682–684 and ~1260–1300; en block ~1797–1799 and ~2370–2400)
- Test: `tests/comments-view.test.mjs`

- [ ] **Step 1: Failing tests.** In `tests/comments-view.test.mjs`:

Change `base()` default `filter: "all"` → `filter: "local"`.

Replace the test «фільтр адресата — лише коли є командний постачальник (dual); активний — aria-pressed» with:

```js
test("фільтр — окремим рядком під пошуком, порядок Для Claude · Команда · Усі, з числами; без dual — нема", () => {
  assert.equal(commentsPanelHTML(base()).includes('data-act="cmtfilter"'), false);
  assert.equal(commentsPanelHTML(base()).includes('class="cmt-filter"'), false);
  const comments = [
    { ...C({ id: "l", n: 1 }), _aud: "local" },
    { ...C({ id: "p", n: 2 }), _aud: "project" },
    { ...C({ id: "a", n: 3, meta: { assignee: "claude" } }), _aud: "project" },
  ];
  const html = commentsPanelHTML(base({ dual: true, filter: "project", fresh: new Set(["p"]), snapshot: { iteration: "3", comments } }));
  const order = [...html.matchAll(/data-act="cmtfilter" data-val="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(order, ["local", "project", "all"]);
  assert.match(html, /data-val="local" aria-pressed="false"><span>Для Claude<\/span><span class="cmt-fn">2<\/span><\/button>/);
  assert.match(html, /data-val="project" aria-pressed="true"><span>Команда<\/span><span class="cmt-fn">2<\/span><span class="cmt-fnew"[^>]*>\+1<\/span><\/button>/);
  assert.match(html, /data-val="all" aria-pressed="false"><span>Усі<\/span><span class="cmt-fn">3<\/span><\/button>/);
  assert.ok(html.indexOf('id="cmt-q"') < html.indexOf('class="cmt-filter"'), "фільтр — під пошуком, не в шапці");
  assert.match(html, /<p class="cmt-fhint">Спільні коментарі\. Їх бачать колеги в превʼю\. Claude бере лише доручені\.<\/p>/);
  assert.match(html, /aria-label="Кому"/);
  assert.equal(html.includes("cmt-total"), false, "з фільтром числа у вкладках, не в шапці");
  assert.equal(commentsPanelHTML(base({ dual: true, filter: "local" })).includes("cmt-fnew"), false, "без нових мітки нема");
});

test("невідоме значення фільтра — вкладка «Для Claude»", () => {
  const html = commentsPanelHTML(base({ dual: true, filter: "сміття" }));
  assert.match(html, /data-val="local" aria-pressed="true"/);
  assert.match(html, /<p class="cmt-fhint">Те, що Claude візьме в роботу/);
});

test("шапка: іконка, назва, кнопки icob; icon-btn більше нема; без dual — число в шапці", () => {
  const html = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [C({ id: "a", n: 1 })] } }));
  assert.equal(html.includes("icon-btn"), false);
  assert.match(html, /<button type="button" class="icob" data-act="cmtpins"/);
  assert.match(html, /<button type="button" class="icob" data-act="comments"/);
  assert.match(html, /<div class="insp-top cmt-top"><svg[^>]*>.*?<\/svg><span class="panel-title">Коментарі<\/span><span class="cmt-total">1<\/span>/s);
});

test("картка: номер локального — фіолетовий лише з dual; бейдж «Доручено Claude»; іконкові дії — cmt-ib", () => {
  const comments = [{ ...C({ id: "l", n: 1 }), _aud: "local" }, { ...C({ id: "a", n: 2, meta: { assignee: "claude" } }), _aud: "project" }];
  const dual = commentsPanelHTML(base({ dual: true, filter: "all", snapshot: { iteration: "3", comments } }));
  assert.match(dual, /<span class="cmt-n cmt-n--local">1<\/span>/);
  assert.match(dual, /<span class="cmt-n">2<\/span>/);
  assert.match(dual, /<span class="cmt-badge">Доручено Claude<\/span>/);
  assert.match(dual, /class="cmt-act" data-act="cmtshow"/);
  for (const act of ["cmtedit", "cmtres", "cmtdel"]) assert.match(dual, new RegExp(`class="cmt-ib" data-act="${act}"`));
  const single = commentsPanelHTML(base({ snapshot: { iteration: "3", comments: [C({ id: "l", n: 1 })] } }));
  assert.match(single, /<span class="cmt-n">1<\/span>/, "без командного каналу піни не фіолетові — і номер теж");
});
```

If an existing test asserts `<span class="cmt-n">2</span>` for a card without `dual`, it stays valid. If any other existing test in this file fails ONLY because of the new default filter or markup order, fix the test's input/expectation minimally and say so in your report; never delete an assertion's intent.

- [ ] **Step 2: Run, expect FAIL** — `node --test tests/comments-view.test.mjs`.

- [ ] **Step 3: i18n.** In `app/i18n.js`, uk block: change `cmtAssignedBadge` to `'Доручено Claude'`, `audChipTeamNote` to `'Видно колегам у превʼю. Claude не візьме, поки не доручите.'`, and add next to them:

```js
  audChipLocalNote: 'Бачите лише ви і Claude. Claude візьме в роботу.',
```
```js
  cmtFHintLocal: 'Те, що Claude візьме в роботу: ваші коментарі для Claude і доручені йому командні.',
  cmtFHintTeam: 'Спільні коментарі. Їх бачать колеги в превʼю. Claude бере лише доручені.',
  cmtFHintAll: 'Усе на цій сторінці: ваші коментарі для Claude і коментарі команди.',
```

en block (same positions): `cmtAssignedBadge: 'Assigned to Claude'`, `audChipTeamNote: 'Colleagues see this in the preview. Claude will not pick it up until you assign it.'`, plus:

```js
  audChipLocalNote: 'Only you and Claude see this. Claude will pick it up.',
```
```js
  cmtFHintLocal: 'What Claude will pick up: your comments for Claude and team comments assigned to it.',
  cmtFHintTeam: 'Shared comments. Colleagues see them in the preview. Claude takes only the assigned ones.',
  cmtFHintAll: 'Everything on this page: your comments for Claude and comments from the team.',
```

⚠ `audChip*` values MUST be single-quoted and contain no ASCII apostrophe — `tests/test_comments_role.py` reads them with `'([^']*)'` and `app/serve.py` embeds them in single-quoted JS. (The uk `ʼ` is U+02BC, not an apostrophe — fine.)

- [ ] **Step 4: View.** In `app/comments-view.js`:

Import line → add `filterCounts`:
```js
import { FILTERS, assignedToClaude, audOf, commentSections, filterCounts, openCount, shotSrc } from "./comments-model.js";
```

Replace `btn` with (text buttons keep `cmt-act`; icon buttons are borderless `cmt-ib`):
```js
const btn = (act, val, label, icon) => `<button type="button" class="${icon ? "cmt-ib" : "cmt-act"}" data-act="${act}" data-val="${esc(val)}"`
  + ` aria-label="${esc(label)}" title="${esc(label)}">${icon ? ico(icon) : esc(label)}</button>`;
```

In `cardHTML`, the number span:
```js
  const num = `<span class="cmt-n${st.dual && audOf(c) === "local" ? " cmt-n--local" : ""}">${esc(c.n)}</span>`;
  const head = `<header class="cmt-head">${num}<span class="cmt-who">${esc(c.author || "")}</span>`
    + `${aud}${badge}${modeTag(m)}<span class="cmt-when">${esc(c.ts || t("cmtNoTime"))}</span></header>`;
```

Replace the start of `commentsPanelHTML` up to and including `const down = …` and the final `return` so that:
```js
const FILTER_KEY = { local: "cmtFLocal", project: "cmtFTeam", all: "cmtFAll" };
const HINT_KEY = { local: "cmtFHintLocal", project: "cmtFHintTeam", all: "cmtFHintAll" };

/** st: {snapshot, query, selectedId, editingId, expanded:{earlier,closed}, filter:'local'|'project'|'all', dual, teamDown, fresh:Set|null, down} */
export function commentsPanelHTML(st) {
  const filter = FILTERS.includes(st.filter) ? st.filter : "local";
  const hidden = !!(st.snapshot && st.snapshot.pinsHidden);
  const pins = `<button type="button" class="icob" data-act="cmtpins" aria-pressed="${hidden}"`
    + ` aria-label="${esc(t("cmtPins"))}" title="${esc(t("cmtPins"))}">${ico("eye")}</button>`;
  const close = `<button type="button" class="icob" data-act="comments" aria-label="${esc(t("cmtClose"))}" title="${esc(t("cmtClose"))}">${ico("x")}</button>`;
  // Без командного каналу фільтра нема — тоді число відкритих лишається в шапці.
  const total = st.dual ? "" : `<span class="cmt-total">${openCount(st.snapshot)}</span>`;
  const top = `<div class="insp-top cmt-top">${ico("comment")}<span class="panel-title">${esc(t("cmtTitle"))}</span>${total}${pins}${close}</div>`;
  const search = `<div class="cmt-search"><input type="search" id="cmt-q" value="${esc(st.query || "")}"`
    + ` placeholder="${esc(t("cmtSearch"))}" aria-label="${esc(t("cmtSearch"))}"></div>`;
  let seg = "";
  if (st.dual) {
    const n = filterCounts(st.snapshot, st.fresh);
    seg = `<div class="cmt-filter" role="group" aria-label="${esc(t("cmtFilter"))}">`
      + FILTERS.map((f) => `<button type="button" data-act="cmtfilter" data-val="${f}" aria-pressed="${filter === f}">`
        + `<span>${esc(t(FILTER_KEY[f]))}</span><span class="cmt-fn">${n[f]}</span>`
        + (f === "project" && n.fresh ? `<span class="cmt-fnew" title="${esc(t("cmtNewTitle"))}">+${n.fresh}</span>` : "")
        + "</button>").join("") + "</div>"
      + `<p class="cmt-fhint">${esc(t(HINT_KEY[filter]))}</p>`;
  }
  const down = st.teamDown ? `<p class="cmt-teamdown" role="alert">${esc(t("cmtTeamDown", st.teamDown))}</p>` : "";
```
…keep the existing `body` computation, but pass `filter: st.dual ? filter : "all"` to `commentSections`, and return:
```js
  return `${top}${search}${seg}${down}<div class="insp-body cmt-body">${body}</div>`;
}
```
Remove the old in-function `FILTER_KEY`, `seg`, `pins`, `top`, `total` definitions so nothing is duplicated. Check `cmtFilter` (the group label key) exists in i18n; if not, keep whatever key the old segment used for `aria-label` (it was `t("cmtFilter")`).

- [ ] **Step 5: CSS.** In `app/styles.css`:

In `:root`, right after `--bad-ink:#c2362e;`:
```css
  /* Колір піна «для Claude» (`LOCAL_PIN_COLOR` у `app.js`, `DUAL_AUDIENCES_JS` у `serve.py`): номер картки в панелі
     фарбується тим самим, щоб пін і картка читались як одне. Звіряє `tests/comments-view-css.test.mjs`. */
  --local-pin:#7C6CF0;
```

In the comments block, DELETE the three `.cmt-ch…` rules and ADD:
```css
.cmt-top>.ico{color:var(--dim)}
.cmt-filter{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;margin:8px 10px 0;border:1px solid var(--line);border-radius:var(--r-sm);overflow:hidden}
.cmt-filter button{display:flex;align-items:center;justify-content:center;gap:5px;min-width:0;height:var(--h-sm);padding:0 6px;border:0;border-left:1px solid var(--line);background:none;color:var(--dim);font:inherit;font-size:12px;cursor:pointer;white-space:nowrap}
.cmt-filter button:first-child{border-left:0}
.cmt-filter button:hover{color:var(--hi)}
.cmt-filter button[aria-pressed="true"]{background:var(--sel-tint-2);color:var(--hi)}
.cmt-filter button:focus-visible{outline:2px solid var(--sel);outline-offset:-2px}
.cmt-fn{font-size:11px;font-variant-numeric:tabular-nums}
.cmt-fnew{min-width:15px;padding:0 4px;border-radius:999px;background:var(--open);color:var(--on-sel);font-size:10px;font-weight:600;line-height:15px;text-align:center;box-sizing:border-box}
.cmt-fhint{margin:6px 12px 0;font-size:11px;line-height:1.4;color:var(--dim)}
.cmt-n--local{background:var(--local-pin);color:#fff}
.cmt-ib{display:inline-grid;place-items:center;width:var(--h-xs);height:var(--h-xs);flex:none;border:0;border-radius:var(--r-sm);background:none;color:var(--mid);cursor:pointer}
.cmt-ib:hover{background:var(--s4);color:var(--hi)}
.cmt-ib:focus-visible{outline:2px solid var(--sel);outline-offset:1px}
.cmt-acts>.cmt-ib:first-child,.cmt-acts>.cmt-act+.cmt-ib{margin-left:auto}
```
Change `.cmt-head{display:flex;align-items:center;gap:6px;margin-bottom:5px}` to:
```css
.cmt-head{display:flex;align-items:center;flex-wrap:wrap;gap:4px 6px;margin-bottom:5px}
.cmt-who,.cmt-aud,.cmt-badge,.cmt-when{white-space:nowrap}
```
Keep `.cmt-top .cmt-total{…}` (still used without a filter). Run `node --test tests/css-guards.test.mjs` — it forbids heights outside the token grid; the rules above use only tokens.

- [ ] **Step 6: Run, expect PASS** — `node --test tests/comments-view.test.mjs tests/css-guards.test.mjs tests/i18n-keys.test.mjs` (and any `tests/i18n*.test.mjs` that exists).
- [ ] **Step 7: Commit** `app/comments-view.js app/styles.css app/i18n.js tests/comments-view.test.mjs` — «fix(0.27.1): шапка панелі без білих кнопок, фільтр рядком з числами, картка в один рядок дій».

---

### Task 3: Guard — every class in the panel markup has a style

**Files:**
- Create: `tests/comments-view-css.test.mjs`

- [ ] **Step 1: Write the test**

```js
/**
 * Охоронець латки 0.27.1. У 0.27.0 кнопки шапки панелі мали клас `icon-btn`, якого не було в `app/styles.css`, — браузер
 * намалював свої світлі кнопки на темній панелі. Ні ревʼю, ні живі тести цього не бачили: вони перевіряють поведінку.
 * Тут — статично: кожен клас із розмітки `app/comments-view.js` має селектор у `app/styles.css`.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const view = readFileSync(new URL("../app/comments-view.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../app/styles.css", import.meta.url), "utf8");
const app = readFileSync(new URL("../app/app.js", import.meta.url), "utf8");

/** Класи-маркери без власного стилю — лише з причиною. */
const NO_STYLE = new Map([
  // приклад формату: ["cmt-sec--fold", "лише маркер для тестів, вигляд дає .cmt-sec"],
]);

function classesInView(src) {
  const out = new Set();
  for (const m of src.matchAll(/class="([^"]*)"/g)) {
    // `${…}`-вставки всередині атрибута: беремо лише літеральні шматки, а гілки тернарних виразів — з лапок нижче
    const literal = m[1].replace(/\$\{[^}]*\}/g, " ");
    // хвіст на «-»/«--» — префікс динамічного класу (`cmt-aud--${…}`): повне імʼя відоме лише під час виконання
    for (const c of literal.split(/\s+/)) if (/^[a-z][\w-]*[a-z0-9]$/.test(c)) out.add(c);
  }
  // класи з тернарних гілок: " cmt-card--sel", "cmt-ib" : "cmt-act" тощо
  for (const m of src.matchAll(/["'` ](cmt-[\w-]+|icob|insp-[\w-]+|panel-title)["'`]/g)) out.add(m[1]);
  return out;
}

const hasRule = (cls) => new RegExp(`\\.${cls.replace(/[-]/g, "\\-")}(?![\\w-])`).test(css);

test("кожен клас розмітки панелі коментарів має правило в styles.css", () => {
  const missing = [...classesInView(view)].filter((c) => !NO_STYLE.has(c) && !hasRule(c)).sort();
  assert.deepEqual(missing, [], `класи без стилю: ${missing.join(", ")}`);
});

test("перелік винятків не гниє: кожен виняток справді вживається і справді без стилю", () => {
  const used = classesInView(view);
  for (const [c, why] of NO_STYLE) {
    assert.ok(why && why.length > 10, `${c}: причина обовʼязкова`);
    assert.ok(used.has(c), `${c}: у розмітці вже нема — приберіть виняток`);
    assert.equal(hasRule(c), false, `${c}: стиль уже є — приберіть виняток`);
  }
});

test("колір номера локальної картки = колір піна для Claude", () => {
  const tok = /--local-pin:\s*(#[0-9A-Fa-f]{6})/.exec(css);
  const pin = /const LOCAL_PIN_COLOR = '(#[0-9A-Fa-f]{6})'/.exec(app);
  assert.ok(tok && pin, "токен або константа зникли");
  assert.equal(tok[1].toLowerCase(), pin[1].toLowerCase());
});
```

- [ ] **Step 2: Run** `node --test tests/comments-view-css.test.mjs`. If it reports real unstyled classes that existed before this patch (e.g. pure markers like `cmt-sec--fold`), do NOT style them blindly: add each to `NO_STYLE` with a true reason after checking it is only a hook (grep `app/app.js`/tests). If a class is genuinely meant to look like something, add the missing rule instead. Report every entry.

- [ ] **Step 3: Prove by mutation (each: copy file → mutate → run → red → restore with `cp` → `cmp` → green):**
  1. In `app/comments-view.js` change the eye button class `icob` → `icon-btn` → test 1 red.
  2. In `app/styles.css` rename `.cmt-fnew{` → `.cmt-fnewX{` → test 1 red.
  3. In `app/styles.css` change `--local-pin:#7C6CF0` → `--local-pin:#7C6CF1` → test 3 red.

- [ ] **Step 4: Commit** `tests/comments-view-css.test.mjs` (git add first) — «test(0.27.1): охоронець — кожен клас панелі коментарів має стиль».

---

### Task 4: Wiring — default tab and chip notes in both places

**Files:**
- Modify: `app/app.js:128` (default filter) and `app/app.js` ~5311–5314 (overview `audiences`)
- Modify: `app/serve.py` ~3070–3077 (`DUAL_AUDIENCES_JS`)
- Test: `tests/comments-wiring.test.mjs:36`, `tests/test_comments_role.py` (`test_dual_audience_labels_match_dictionary`)

- [ ] **Step 1: Failing tests.**

`tests/comments-wiring.test.mjs`, in the test «cmtfilter: лише значення з FILTERS, вибір памʼятається в dc-cmt-filter», change the regex on line 36 to:
```js
  assert.match(src, /localStorage\.getItem\('dc-cmt-filter'\); return FILTERS\.includes\(v\) \? v : 'local'/, "немає чи сміття — вкладка «Для Claude» (рішення власника 16.11.2026)");
```
(keep the rest of that test). Add:
```js
test("«Огляд»: аудиторія «Claude» має підказку під чипом, як і «Команді»", () => {
  assert.match(src, /\{ id: 'local', label: t\('audChipLocal'\), icon: 'bot', color: LOCAL_PIN_COLOR, private: true, note: t\('audChipLocalNote'\) \}/);
  assert.match(src, /\{ id: 'project', label: t\('audChipTeam'\), icon: 'team', note: t\('audChipTeamNote'\) \}/);
});
```
(`src` is the app.js source variable already used in that file — check its name and reuse it.)

`tests/test_comments_role.py`, in `test_dual_audience_labels_match_dictionary`:
```python
        keys = ('audChipLocal', 'audChipTeam', 'audChipLocalNote', 'audChipTeamNote')
        ...
            line = re.search(rf"var {lang} = \{{ local: '([^']*)', team: '([^']*)', localNote: '([^']*)', note: '([^']*)' \}};", serve.DUAL_AUDIENCES_JS)
```
and add after the loop:
```python
        self.assertIn("private: true, note: L.localNote }", serve.DUAL_AUDIENCES_JS)
```

- [ ] **Step 2: Run, expect FAIL** — `node --test tests/comments-wiring.test.mjs` and `python3 -B -m unittest tests.test_comments_role -k dual_audience` (run from the repo root; if `-k` is unsupported in this layout, run the whole `tests/test_comments_role.py` module).

- [ ] **Step 3: Implement.**

`app/app.js:128`:
```js
let cmtFilter = (() => { try { const v = localStorage.getItem('dc-cmt-filter'); return FILTERS.includes(v) ? v : 'local'; } catch (e) { return 'local'; } })();
```
Overview audiences:
```js
    { id: 'local', label: t('audChipLocal'), icon: 'bot', color: LOCAL_PIN_COLOR, private: true, note: t('audChipLocalNote') },
    { id: 'project', label: t('audChipTeam'), icon: 'team', note: t('audChipTeamNote') },
```
`app/serve.py` `DUAL_AUDIENCES_JS`:
```js
        var uk = { local: 'Claude', team: 'Команді', localNote: 'Бачите лише ви і Claude. Claude візьме в роботу.', note: 'Видно колегам у превʼю. Claude не візьме, поки не доручите.' };
        var en = { local: 'Claude', team: 'Team', localNote: 'Only you and Claude see this. Claude will pick it up.', note: 'Colleagues see this in the preview. Claude will not pick it up until you assign it.' };
        ...
        return [{ id: 'local', label: L.local, icon: 'bot', color: '#7C6CF0', private: true, note: L.localNote },
                { id: 'project', label: L.team, icon: 'team', note: L.note }];
```
Grep for any other test or golden fixture containing the OLD note text (`Командні коментарі видно колегам`, `Team comments are visible`) and update it; if a golden file is hash-pinned (`GoldenPinTest`), STOP and report instead of re-pinning.

- [ ] **Step 4: Run, expect PASS** — the two files above + `node --test tests/` (whole JS suite).
- [ ] **Step 5: Commit** `app/app.js app/serve.py tests/comments-wiring.test.mjs tests/test_comments_role.py` — «feat(0.27.1): типова вкладка «Для Claude», підказка під обома чипами адресата».

---

### Task 5: Live tests

**Files:**
- Modify: `tests/live/comments-team.test.mjs` (+ `tests/live/comments.test.mjs`, `tests/live/overview-comments.test.mjs` only if they fail)

- [ ] **Step 1: Run each comments live file separately** and record results:
  `node --test tests/live/comments-team.test.mjs`, then `tests/live/comments.test.mjs`, then `tests/live/overview-comments.test.mjs`, then `tests/live/tasks-home.test.mjs`.
  Expected failures come only from the new default tab: scenarios that look for an unassigned TEAM card in the panel without choosing a tab. Fix each by pressing the tab the scenario is about (`#cmt-panel [data-act="cmtfilter"][data-val="project"]` or `"all"`) before looking — never by deleting or loosening an assertion. If a failure is not explained by the default tab or the new markup, STOP and report it.

- [ ] **Step 2: Add a scenario to `tests/live/comments-team.test.mjs`** (reuse that file's helpers for server/page/space setup; follow the style of scenario 3 «фільтр»):
  - fresh browser context (no `dc-cmt-filter` in localStorage) → open the panel → `#cmt-panel [data-act="cmtfilter"][data-val="local"]` has `aria-pressed="true"`;
  - the filter row is below `#cmt-q` (compare `getBoundingClientRect().top`) and the header `.panel-title` text is not truncated (`scrollWidth <= clientWidth`);
  - the eye and close buttons' computed `background-color` is transparent (`rgba(0, 0, 0, 0)`) — the exact bug the owner saw;
  - a team comment is NOT in «Для Claude»; press «Доручити Claude» on it (from the «Команда» tab) → switch to «Для Claude» → the card is there and the `local` tab count went up by one;
  - reload → the last chosen tab is restored.
  Prove the scenario with two mutations (restore byte-exact each time): default `'local'` → `'all'` in `app/app.js:128` → red; `forClaude` without `|| assignedToClaude(c)` → red.

- [ ] **Step 3: Commit** the touched live files — «test(0.27.1): живі — типова вкладка, доручений у «Для Claude», шапка без білих кнопок».

---

### Task 6: Docs and version

**Files:**
- Modify: `CHANGELOG.md` (new section above `[0.27.0]`), `package.json` (`"version": "0.27.1"`), `README.md:332–333`

- [ ] **Step 1:** `CHANGELOG.md` — follow the format of the `[0.27.0]` entry (headings, language, bullet style):

```markdown
## [0.27.1] — 16.11.2026

### Виправлено
- Панель коментарів: око й хрестик у шапці були світлими браузерними кнопками — їхнього класу не було в стилях. Тепер це
  звичайні кнопки оболонки. Новий тест не пускає в розмітку панелі клас без стилю.
- Заголовок «Коментарі» більше не обрізається: фільтр переїхав із шапки окремим рядком під пошук.
- Дії картки вміщаються в один рядок: текстові кнопки ліворуч, іконки праворуч.

### Змінено
- Вкладки фільтра: «Для Claude · Команда · Усі», у кожній — число відкритих, на «Команді» — «+N» нових. Відкривається
  остання вибрана вкладка, уперше — «Для Claude». Під фільтром — рядок, що в ньому.
- «Для Claude» показує те, що Claude бере в роботу: ваші коментарі для Claude і доручені йому командні (раніше — лише
  локальні).
- Під обома чипами адресата в формі піна — хто це побачить. Бейдж дорученого — «Доручено Claude».
```

- [ ] **Step 2:** `package.json` version → `0.27.1`. `README.md` line 333: the filter sentence → `The panel filter is «For Claude / Team / All»; «For Claude» is what Claude picks up — your comments for Claude plus team comments assigned to it.` (keep the surrounding paragraph intact).
- [ ] **Step 3:** grep `docs/` and `app/modules/supabase-comments/README.md` for «Усі / Для Claude / Команда» or «All / For Claude / Team» and update the order and the «for Claude» rule wherever stated.
- [ ] **Step 4:** Run `node --test tests/` and the full Python suite `python3 -B -m unittest discover -s tests -p 'test_*.py'` (long; ~20 min) plus `python3 -B -m unittest discover -s bin -p 'test_*.py'` and `-s app -p 'test_*.py'` if those suites exist (see how `CHANGELOG`/previous release notes ran them). All green.
- [ ] **Step 5: Commit** `CHANGELOG.md package.json README.md` (+ any docs touched) — «docs(0.27.1): CHANGELOG, версія, опис фільтра».

---

### Controller-only (not for the implementer)

- Final review (one Sonnet reviewer) of `d8e1b1c..HEAD` against the spec.
- Release run: full JS/Python suites, live files one by one, build determinism, forbidden-list guard.
- Visual check on the live canvas: screenshot of the panel on a LIGA task next to the approved prototype; read-only for the team channel.
- Merge to `main`, tag `v0.27.1`; push only with the owner's explicit OK.
