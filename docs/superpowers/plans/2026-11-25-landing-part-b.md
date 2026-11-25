# Landing part B — live landing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Deai Canvas landing alive and complete: heading morph, shimmer, a live first-screen scene of the comment loop,
an interactive dot grid, a "comments" section that shows what the agent did and did not do, and a scroll-driven tour of every
part of the interface. Addresses the owner's pins L#1, L#2, L#5, L#6, L#8–L#12 (spec: `docs/superpowers/specs/2026-11-25-landing-releases-design.md`, part B).

**Architecture:** Static page in `landing/` (HTML, one CSS file, vanilla JS, no build step, no dependencies). Behaviour is split
into focused deferred scripts: `site.js` (existing: tabs, lightbox, copy, share, menu), `hero.js` (heading morph + live scene),
`magnet.js` (dot grid), `tour.js` (scroll-driven tour). Screenshots come from the existing capture script
`ops/landing-shots.mjs`, which runs a throwaway Deai server on fictional demo data (Northline rail booking, Forma checkout).

**Tech Stack:** HTML/CSS/vanilla JS (ES2020, no modules needed), Web Animations API, `<canvas>` 2D, IntersectionObserver,
Node + Playwright (already in `node_modules`) for captures and checks, `cwebp`.

---

## Rules for every task

- Work in the worktree root. Never touch `app/`, `CHANGELOG.md`, `package.json` version, ports 8765/4317, `~/.deai`,
  `~/deai-work`, `~/deai-published`. Never `pkill`/`killall` by pattern, never `rm -rf`. Python: `python3 -B`.
- Commit with: `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<msg>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <paths>`.
  New files: `git add -- <path>` first. Never `git add -A`, never amend/rebase/reset, never bare `git stash`.
- Public repo: no real names (fictional "Maya Chen" is fine), no internal hosts, no absolute local paths in committed files.
- Motion rules (apply to all animation): `prefers-reduced-motion: reduce` → static final state, nothing moves; animations pause
  when off-screen (IntersectionObserver) and when `document.hidden`; no hover-only effects on touch (`(hover: none)`); every
  decorative layer is `aria-hidden="true"` and `pointer-events: none`; no layout shift (overlays are absolutely positioned).
- Copy: English, sentence case, the product is always "Deai Canvas". UI names must match the app's English strings
  (`app/i18n.js`, English block): "AI is working", "AI is waiting for your reply", "AI: done", "Done · It.N", "Resolved",
  "Assign to AI", "Show in preview", "Open comments: N", "Mine / Team".
- Local preview: `python3 -B -m http.server 8092 --bind 127.0.0.1 --directory landing` may already be running; if port 8092
  is busy, use another free port (8093+). Checks use Playwright from `node_modules` (see each task).
- Page check that every task must pass before commit (write it to the scratch folder, not the repo):
  375×812 and 1440×900, no horizontal scroll (`document.documentElement.scrollWidth <= innerWidth`), no console errors,
  same with `reducedMotion: "reduce"`.

## File map

- Modify `landing/index.html` — markup for all sections.
- Modify `landing/styles.css` — styles (keep one file; group new rules under comments `/* Hero scene */`, `/* Magnet */`,
  `/* Comments */`, `/* Tour */`).
- Create `landing/hero.js` — heading morph (B1) + live scene (B3).
- Create `landing/magnet.js` — dot grid (B4).
- Create `landing/tour.js` — scroll-driven tour (B5).
- Modify `landing/site.js` — only if tabs code must expose a hook for the tour.
- Modify `ops/landing-shots.mjs`, `ops/landing-shots/demos.mjs` — new captures.
- New assets in `landing/assets/`: `studio-tasks.webp`, `northline-iterations.webp`, `northline-comments.webp`,
  `northline-scene-before.webp`, `northline-scene-after.webp`. Remove `northline-review.webp` when nothing references it.

---

### Task 1: Remove "Connect your agent", heading morph, shimmer

Pins: L#10 (remove "Connect your agent" from the landing), L#1/L#12 (heading morph), L#6 (shimmer).

**Files:** `landing/index.html`, `landing/styles.css`, create `landing/hero.js`.

- [ ] **Step 1: Remove "Connect your agent" from the landing only.** In `landing/index.html` delete `<h3 class="connect-title">`
  and the whole `<ol class="connect-steps">…</ol>` from `.setup-copy`. Delete their CSS rules (`.connect-title`, `.connect-steps`
  and descendants, including media-query variants). README.md is NOT touched.

- [ ] **Step 2: Heading markup.** Replace the h1 with:

```html
<h1 id="hero-title" data-morph><span class="morph-line">Design with AI.</span><br> Keep control.</h1>
```

- [ ] **Step 3: Morph CSS** (append to `styles.css` under `/* Hero heading morph */`):

```css
.morph-line { display: inline-block; white-space: pre; }
.morph-line.is-ready > span {
  display: inline-block;
  overflow: hidden;
  vertical-align: bottom;
  padding-block: .06em .2em;   /* room for descenders while width is clipped */
  margin-block: -.06em -.2em;
}
.morph-line.is-ready > .m-ai { display: inline-grid; justify-items: start; }
.morph-line .m-ai > span { grid-area: 1 / 1; }
.morph-line .m-low { opacity: 0; }
.morph-line .m-add { width: 0; opacity: 0; }
```

- [ ] **Step 4: `landing/hero.js`** — port of the approved prototype, plus pause rules. Load it in `<head>` after site.js:
  `<script src="hero.js" defer></script>`.

```js
// Hero heading: "Design with AI." folds into "Deai Canvas" and back, on a loop.
// "De" stays, "sign with " and "." squeeze out right to left, "AI" becomes "ai", " Canvas" grows in.
(() => {
  const h1 = document.querySelector("[data-morph]");
  const line = h1 && h1.querySelector(".morph-line");
  if (!line || matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const EASE = "cubic-bezier(.7, 0, .25, 1)";
  const HOLD = 2600;
  const PAUSE = 900;
  const parts = [["m-keep", "De"]];
  for (const ch of "sign with ") parts.push(["m-cut", ch]);
  parts.push(["m-ai", null], ["m-cut m-dot", "."]);
  for (const ch of " Canvas") parts.push(["m-add", ch]);

  h1.setAttribute("aria-label", "Design with AI. Keep control.");
  line.setAttribute("aria-hidden", "true");

  let running = [];
  let visible = true;
  let waiting = null; // a cycle step deferred until the heading is visible again

  const gate = (fn) => {
    if (visible && !document.hidden) fn();
    else waiting = fn;
  };
  const resume = () => {
    if (waiting && visible && !document.hidden) { const fn = waiting; waiting = null; fn(); }
  };
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; resume(); }).observe(h1);
  document.addEventListener("visibilitychange", resume);

  function build() {
    line.textContent = "";
    for (const [cls, text] of parts) {
      const span = document.createElement("span");
      span.className = cls;
      if (cls === "m-ai") span.innerHTML = '<span class="m-up">AI</span><span class="m-low">ai</span>';
      else span.textContent = text;
      line.append(span);
    }
    line.classList.add("is-ready");
  }

  function measure(el) {
    const prev = el.style.width;
    el.style.width = "auto";
    const w = el.getBoundingClientRect().width;
    el.style.width = prev;
    return w;
  }

  function play() {
    running.forEach((a) => a.cancel());
    running = [];
    build();
    const cut = [...line.querySelectorAll(".m-cut")];
    const add = [...line.querySelectorAll(".m-add")];
    const ai = line.querySelector(".m-ai");
    const up = ai.querySelector(".m-up");
    const low = ai.querySelector(".m-low");
    const cutW = cut.map(measure);
    const addW = add.map(measure);
    const upW = up.getBoundingClientRect().width;
    const lowW = low.getBoundingClientRect().width;
    ai.style.width = `${upW}px`;

    const anim = (el, frames, delay, duration) => {
      const a = el.animate(frames, { delay, duration, easing: EASE, fill: "both" });
      running.push(a);
      return a;
    };
    const t0 = 1100;
    cut.slice().reverse().forEach((el, i) => {
      const w = cutW[cut.length - 1 - i];
      anim(el, [
        { width: `${w}px`, opacity: 1, transform: "translateY(0)" },
        { width: "0px", opacity: 0, transform: "translateY(.12em)" },
      ], t0 + i * 34, 460);
    });
    const t1 = t0 + 470;
    anim(ai, [{ width: `${upW}px` }, { width: `${lowW}px` }], t1, 420);
    anim(up, [{ opacity: 1, transform: "translateY(0)" }, { opacity: 0, transform: "translateY(-.35em)" }], t1, 320);
    anim(low, [{ opacity: 0, transform: "translateY(.35em)" }, { opacity: 1, transform: "translateY(0)" }], t1 + 80, 340);
    const t2 = t1 + 420;
    let last;
    add.forEach((el, i) => {
      last = anim(el, [
        { width: "0px", opacity: 0, transform: "translateY(.25em)" },
        { width: `${addW[i]}px`, opacity: 1, transform: "translateY(0)" },
      ], t2 + i * 38, 420);
    });

    last.finished.then(() => setTimeout(() => gate(() => {
      running.forEach((a) => a.reverse());
      Promise.all(running.map((a) => a.finished))
        .then(() => setTimeout(() => gate(play), PAUSE))
        .catch(() => {});
    }), HOLD)).catch(() => {});
  }

  // Window resize changes the font size (clamp), so measured widths go stale: rebuild on the next cycle.
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => gate(play));
})();
```

  Note: the line keeps "Design with AI." as plain text until fonts are ready and without JS, so no-JS and reduced-motion users
  see the static heading.

- [ ] **Step 5: Shimmer on the product label.** Markup: `<p class="product-label"><span aria-hidden="true"></span> <span class="shimmer">AI-first design workspace</span></p>`.
  CSS (own implementation, `background-clip: text`), a reusable `.shimmer` class that Task 3 also uses on "AI is working":

```css
/* Shimmer: a light band sweeps across the text. */
.shimmer {
  --shimmer-base: var(--muted);
  --shimmer-light: #9fbf8f;
  background: linear-gradient(100deg, var(--shimmer-base) 0 40%, var(--shimmer-light) 50%, var(--shimmer-base) 60% 100%) 100% 0 / 250% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  animation: shimmer 2.6s linear infinite;
}
@keyframes shimmer { to { background-position: -150% 0; } }
@media (prefers-reduced-motion: reduce) {
  .shimmer { animation: none; background: none; color: var(--shimmer-base); }
}
```

  Pick `--shimmer-light` so the band is clearly visible on `--paper` but the text stays readable (contrast of base ≥ 4.5:1;
  the band is decorative). Check it visually in a screenshot.

- [ ] **Step 6: Verify.** Playwright script in the scratch folder: load the page at 1440×900; after 4 s the h1 visible text
  (`line.innerText` ignoring zero-width spans is hard — instead assert `getComputedStyle(.m-add).width !== "0px"` for the last
  `.m-add`) shows "Canvas" grown in; `h1.getAttribute("aria-label") === "Design with AI. Keep control."`; with
  `reducedMotion: "reduce"` the h1 text is exactly "Design with AI. Keep control." and has no `.is-ready`. Take two screenshots
  (t≈0.5 s and t≈4 s) and look at them. Run the page check from the rules.

- [ ] **Step 7: Commit** `landing/index.html landing/styles.css landing/hero.js` — "feat(landing): heading folds into Deai Canvas, shimmer label, no Connect your agent block".

---

### Task 2: New captures

Pins: L#6 (scene frames), L#8 (spaces, tasks, iterations), L#9/L#11 (comments with agent replies).

**Files:** `ops/landing-shots.mjs`, `ops/landing-shots/demos.mjs`, new webp files in `landing/assets/`.

Context: `node ops/landing-shots.mjs` creates a temp HOME with a fictional "Studio" space (tasks `northline`, `forma`), starts the
real Deai server (`app/serve.py`) on a free port ≥ 31100 with `HOME`/`DEAI_HOME` pointing at the temp dir, seeds pins through
`POST /api/local-comments`, drives the app with Playwright at 1440×860 @2x and writes WebP files straight into `landing/assets/`.
Read `seedPins`, `studioShots`, `capture` first. Local comments support `replies: [{id, author, text, ts}]` — check
`app/comments-model.js` (`repliesOf`) and `app/comments-view.js` for the exact reply fields the panel renders and how a reply
from the agent is labelled.

- [ ] **Step 1: Richer demo data.**
  - Add two or three more small fictional tasks to the Studio space so the task list is not sparse (e.g. "Northline · Mobile
    tickets", "Forma · Product page", "Atlas · Onboarding"); each needs at least one iteration with one simple page (reuse the
    existing page generators or a tiny HTML page in the same visual language). Give tasks tags (`tags` in tasks.json), e.g.
    `booking`, `mobile`, `checkout`, `onboarding`. Fictional names only.
  - Northline pins (`northlinePins` in demos.mjs): keep the three, and give pin 2 ("Keep Find trains visible…") a reply from the
    agent that shows it is NOT done yet and needs a decision, e.g. author "AI", text "Sticky bar at the bottom or a button under
    the form? I can do either — which one?". Use whatever author marker the app uses for agent replies (check the view code;
    if the app has none, use author "Claude"). Pin 3 stays resolved with its note (shows "Done · It.2").
  - Make sure the change does not break the existing captures (`northline-inspector`, `studio-modules`, `northline-preview`,
    `forma-overview`, `forma-flow`): they must still be produced and look the same.

- [ ] **Step 2: New shots.** Add to the script (same `capture()` helper, 1440×860 @2x unless noted):
  1. `studio-tasks.webp` — the tasks home of the Studio space ("Mine" tab, all tasks visible with iteration, pages, open
     comments count and tags). Find how the app opens it (`tasks-home.js`, bar/space chip).
  2. `northline-iterations.webp` — Northline in Layout mode with the iterations list/menu open, showing It.1 and It.2 with their
     notes and the green "Show in preview" dot on the published one.
  3. `northline-comments.webp` — Layout mode on the search page with the comments panel open: the open pins (one with the agent
     reply visible — expand the thread if needed) and the Resolved group expanded showing "Done · It.2" with the note.
  4. `northline-scene-before.webp` and `northline-scene-after.webp` — the SAME framing: Layout mode, search page, no side panels
     open, comments pins hidden if possible, mouse parked at (5,5). "after" differs only in the departure date field: it shows the
     full date (e.g. "Friday, 18 September 2026") and is wider. Produce "after" by editing the field inside the frame before the
     capture (`frame.locator("#date-field")` → change text/width via evaluate), or via a real third iteration if that is simple —
     but do not change the iteration count shown in the other shots.
     Log the centre of `#date-field` in each scene image as percentages of the image width/height
     (`(rect.x + rect.width/2) / 1440 * 100`, using the frame's offset in the page) and print it, e.g.
     `scene pin: 41.2% 38.7%`; Task 3 positions the overlay with it. Put the numbers in the commit message too.
- [ ] **Step 3: Run** `node ops/landing-shots.mjs` (it prints each written file). Look at every new image. Each webp should be
  ≤ 350 KB; if larger, lower cwebp quality for that shot only (`-q 82`).
- [ ] **Step 4: Guard test:** `DEAI_FORBIDDEN_LIST="$HOME/Liga Tools/design-office-transition/scripts/deai-forbidden.txt" DEAI_REQUIRE_FORBIDDEN_LIST=1 python3 -B -m unittest tests.test_no_internal_addresses` → OK.
- [ ] **Step 5: Commit** the script, demos and all changed/new webp files — "feat(landing-shots): tasks, iterations, comment replies and scene frames".

---

### Task 3: Live hero scene + magnet dot grid

Pins: L#6 (live scene), L#5 (magnet texture), L#12 (animations must be visible).

**Files:** `landing/index.html`, `landing/styles.css`, `landing/hero.js` (append), create `landing/magnet.js`.

**Scene (B3).** The hero figure shows `northline-scene-before.webp` (keep the lightbox link; alt: "Northline rail booking in
Deai Canvas: a comment pinned to the departure date field and the agent's fix in the next iteration."). `hero.js` builds an
overlay inside `.hero-screenshot` (absolutely positioned over the image, `aria-hidden`, `pointer-events: none`), positioned in
percentages using the numbers from Task 2 (`--pin-x`, `--pin-y` custom properties on the overlay). Elements:
`after` image (same size, opacity 0), cursor (inline SVG arrow, 18–22 px), pin (numbered circle "1", 22–26 px, ink background,
lime ring), comment card (white, radius 10, shadow, 220–260 px wide, author line "You" + text), status island (pill at the
bottom centre of the screenshot like the app's island: dot + label), all scaled with the screenshot (use `clamp()`/container
units so they stay legible from 375 px to 1440 px; on < 560 px hide the card text body and keep pin + island).

Timeline, one loop ≈ 10 s (Web Animations or CSS classes driven by timers; must be pausable):
1. 0.0 s — before image, no overlay.
2. 0.5 s — cursor enters from the lower right and glides to the pin point (1.2 s, ease-out).
3. 1.8 s — click: small ripple, pin pops in (scale .6 → 1, 180 ms).
4. 2.1 s — comment card opens next to the pin; text "Make the date field wider" types in (~35 ms/char).
5. 3.6 s — card shows "Sent to AI"; cursor fades out.
6. 4.0 s — island appears: dot + "AI is working" with the `.shimmer` class from Task 1 (lighter colours to fit the dark pill).
7. 6.2 s — after image crossfades in (700 ms); pin turns resolved (lime fill + check); card becomes:
   status line "Done · It.3" and the agent note "Widened the field so the full date fits on one line."; island → "AI: done".
8. 9.2 s — overlay fades out, after image fades out (back to before), loop.

Pause rules: run only while the figure is in view and the tab is visible; when it leaves view, finish nothing — just freeze and
resume from the start of the loop when visible again. Reduced motion: no timeline; show the final state statically (after image
visible, resolved pin, "Done · It.3" card, island "AI: done"). No JS: just the before image.

**Magnet (B4).** `landing/magnet.js` draws an interactive dot grid on a `<canvas class="magnet" aria-hidden="true">` inserted as the
first child of `.canvas-stage` (hero) and `.setup-board` (setup), absolutely filling the element behind its content (content gets
`position: relative; z-index: 1`). Replace the static CSS dot background of `.canvas-stage` (keep the gradient) — the canvas
draws the dots. Own implementation (do not copy code from textures.dev):
- grid step 16 px (CSS px), dot radius 0.9 px, colour `#547b4d` at ~0.35 alpha; DPR-aware (`canvas.width = w * dpr`).
- pointer within radius R = 150 px pulls each dot towards it: offset = (pointer − dot) × k × (1 − d/R)², k ≈ 0.28; dots near
  the pointer grow to ~1.6 px and darken (alpha → 0.7). Each frame the drawn offset eases toward the target (lerp 0.18) so dots
  "stick" and spring back when the pointer leaves.
- draw loop runs only while the pointer is inside or dots are still settling; otherwise idle (no rAF).
- `ResizeObserver` re-sizes; IntersectionObserver stops drawing off-screen.
- `(hover: none)` or reduced motion: draw the static grid once (no interaction).
- Load: `<script src="magnet.js" defer></script>`.

- [ ] **Step 1:** Markup + CSS for the scene and magnet.
- [ ] **Step 2:** Scene code appended to `hero.js` (separate IIFE).
- [ ] **Step 3:** `magnet.js`.
- [ ] **Step 4: Verify** with Playwright (scratch script): at 1440×900 take screenshots at t = 1.0, 2.6, 4.6, 7.5 s and LOOK at
  them (cursor travelling, pin + card typing, "AI is working" island, after state with "Done · It.3"). Move the mouse over the
  hero stage padding and screenshot — dots visibly pulled. Same at 375×812. With reduced motion: one screenshot shows the final
  static state. Page check from the rules. Report the overlay alignment: the pin must sit on the date field in both widths.
- [ ] **Step 5: Commit** — "feat(landing): live comment scene on the first screen and a magnet dot grid".

---

### Task 4: Comments section + scroll-driven tour of every view

Pins: L#9/L#11 (comments with AI and team — you see at once what is done and what is not), L#2 (scroll between views),
L#8 (all features incl. spaces, tasks, iterations).

**Files:** `landing/index.html`, `landing/styles.css`, create `landing/tour.js`, maybe `landing/site.js`.

**4a. New section "Comments"** placed right after the story section (`#story`), id `comments`, light background like the story.
Add "Comments" to the header nav and footer nav (between Workflow and Modules).

Copy (use exactly, fix only typos):
- h2: "Every comment<br> gets an answer."
- lead: "Pin feedback to any element on any screen. You see at once what your agent fixed, what it is still working on, and where it needs your call."
- Status list (an HTML mock of the comments panel — real text, styled like small cards; each row: status chip, the pin text, the
  answer). Rows:
  1. chip "Done · It.3" (lime) — pin: "Show the full departure date." — answer (AI): "Widened the field so the full date fits on one line."
  2. chip "AI is waiting for your reply" (amber-ish, muted) — pin: "Keep Find trains visible on mobile." — answer (AI): "Sticky bar at the bottom or a button under the form? I can do either."
  3. chip "AI is working" (with `.shimmer`) — pin: "Use the route as the heading."
  4. chip "Team · Assigned to AI" — pin: "Can we show the price per person?" — from "Maya Chen · in the preview".
- Two short columns under the list:
  - "With your agent" — "Pins go to a local inbox your agent reads. It replies in the thread when it needs you and closes each pin with a note in the iteration that fixed it."
  - "With your team" — "Colleagues comment right in the published preview. New comments show up in Deai Canvas with a badge — reply in the thread or assign one to AI."
- The screenshot `northline-comments.webp` next to the list on desktop (below on mobile), with the lightbox link
  (`data-screenshot="Northline · Comments"`), alt describing open pins with an agent reply and the resolved group.

**4b. Tour (replaces the gallery in `#workflow`).** Keep the section id `workflow`, the dark band and the intro, change the h2 to
"Every part of the workspace." and the lead to "Scroll through the views you use every day — from the task list to the preview your team opens."
Seven tabs/panels in this order (tab label → panel h3 → panel text → image):
1. "Spaces & tasks" → "Keep every project in its place." → "Group tasks into spaces — one per client, product or team. The task list shows each task’s latest iteration, its pages, open comments and tags." → `studio-tasks.webp`
2. "Iterations" → "Every agent pass is an iteration." → "Each pass lands as a new iteration with a note about what changed. Earlier iterations stay editable, and a green dot marks the ones shown in the team preview." → `northline-iterations.webp`
3. "Overview" → "See every screen." → existing text → `forma-overview.webp`
4. "Flow" → "Follow the path." → existing text → `forma-flow.webp`
5. "Inspector" → "Inspect live elements." → "Click any element to see its spacing, layout and colors, checked against your space’s tokens. Tweak a value live, add a note and send the change to your agent." → `northline-inspector.webp`
6. "Comments" → "Pin feedback to the element." → "Comments stick to the element, not to screen coordinates, and carry over between iterations. Resolved pins keep the agent’s note and the iteration that fixed them." → `northline-comments.webp`
7. "Team preview" → "Share the version you want reviewed." → "Publish selected iterations as a clickable preview, with an optional password. Teammates try the real flow and comment right there." → `northline-preview.webp`
Keep the existing project labels ("Forma / Checkout", "Northline / Rail booking", "Studio / Tasks"). Tab icons: reuse the
existing icon classes where they fit; for the new tabs use simple CSS glyphs in the same style (no icon fonts, no emoji).

**Scroll behaviour (`tour.js`).** Only when `(min-width: 1024px) and (min-height: 640px)` and motion is allowed:
- the `.gallery` becomes a scroll track: height = 7 × 70vh + the sticky frame height; an inner wrapper is
  `position: sticky; top: <header height + 24px>` and holds the tabs (left) and the panels (right) exactly like today.
- on scroll (passive listener, rAF-throttled) the active index = floor(progress × 7) clamped; switching sets
  `aria-selected`/`tabindex`/`hidden` the same way as `initTabs` in `site.js` (reuse it: expose `initTabs` return value
  `{ show }` or dispatch a custom event — keep one source of truth). Panels crossfade (opacity 220 ms).
- a thin vertical progress line beside the tabs fills with scroll progress.
- clicking a tab (or arrow keys) scrolls the window to the start of that step (`behavior: "smooth"`), so scroll and tabs never
  disagree.
- when the media query stops matching (resize) the track collapses back to normal tabs.
Everywhere else (phones, reduced motion, short windows): the existing plain tabs, unchanged. No JS: panels stacked as today.

- [ ] **Step 1:** Comments section markup + CSS.
- [ ] **Step 2:** Tour markup (7 tabs/panels) + CSS.
- [ ] **Step 3:** `tour.js` + any minimal change in `site.js`.
- [ ] **Step 4: Verify** with Playwright: at 1440×900 scroll through `#workflow` in 7 steps, screenshot each, assert the selected
  tab index follows scroll; click tab 6 → page scrolls and tab 6 is selected; keyboard ArrowDown moves selection. At 375×812
  plain tabs work (click + arrows). With reduced motion: plain tabs. Page check from the rules. Look at all screenshots.
- [ ] **Step 5: Commit** — "feat(landing): comments section and a scroll-driven tour of every view".

---

### Task 5 (controller): canvas iteration, pins, push

- [ ] Copy `landing/` (index.html, styles.css, *.js, assets/) into a new iteration it3 of the canvas task `deai-landing`
  (`POST /api/iteration {from: "it2", note}` with header `X-Canvas-Task: deai-landing`, copy files, `POST /api/autosync`).
- [ ] Open it3 in the canvas and check the animations are visible in the frame (heading, scene, magnet, tour).
- [ ] Resolve pins L#1, L#2, L#5, L#6, L#8, L#9, L#10, L#11, L#12 with `bin/inbox.py --task deai-landing resolve <id> --it 3 --reason "…"`.
- [ ] Do NOT push yet: once GitHub Pages is on, a push of `landing/` to `main` publishes the site. Ask the owner to review it3
  in the canvas; push to `main` (fast-forward, origin checked) only after the owner's explicit «да».
