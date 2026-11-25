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

  // Animations, observers and timers live as long as the page.
  let running = [];
  let cycle = 0; // timers from a cancelled cycle check it and do nothing
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

  function stop() {
    cycle += 1;
    waiting = null;
    running.forEach((a) => a.cancel());
    running = [];
  }

  function play() {
    stop();
    const id = cycle;
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

    // Easing goes on each keyframe (it shapes the segment after it); the effect itself runs linearly.
    const anim = (el, frames, delay, duration) => {
      const a = el.animate(frames.map((f) => ({ easing: EASE, ...f })), { delay, duration, fill: "both" });
      running.push(a);
      return a;
    };
    const t0 = 1100;
    // 1. "sign with " and "." fade out right to left; each gap closes only once its letter is gone.
    cut.slice().reverse().forEach((el, i) => {
      const w = `${cutW[cut.length - 1 - i]}px`;
      anim(el, [
        { width: w, opacity: 1, transform: "translateY(0)" },
        { width: w, opacity: 0, transform: "translateY(.1em)", offset: .42 },
        { width: "0px", opacity: 0, transform: "translateY(.1em)" },
      ], t0 + i * 34, 540);
    });
    // 2. "AI" lands next to "De" and turns into "ai".
    const t1 = t0 + 560;
    anim(ai, [{ width: `${upW}px` }, { width: `${lowW}px` }], t1, 420);
    anim(up, [{ opacity: 1, transform: "translateY(0)" }, { opacity: 0, transform: "translateY(-.12em)" }], t1, 260);
    anim(low, [{ opacity: 0, transform: "translateY(.12em)" }, { opacity: 1, transform: "translateY(0)" }], t1 + 140, 300);
    // 3. " Canvas" takes its room letter by letter, then each letter fades in.
    const t2 = t1 + 380;
    let last;
    add.forEach((el, i) => {
      const w = `${addW[i]}px`;
      last = anim(el, [
        { width: "0px", opacity: 0, transform: "translateY(.1em)" },
        { width: w, opacity: 0, transform: "translateY(.1em)", offset: .5 },
        { width: w, opacity: 1, transform: "translateY(0)" },
      ], t2 + i * 38, 480);
    });

    // `finished` rejects when a cycle is cancelled (resize, replay): the empty catches are intentional.
    last.finished.then(() => setTimeout(() => gate(() => {
      if (id !== cycle) return;
      running.forEach((a) => a.reverse());
      Promise.all(running.map((a) => a.finished))
        .then(() => setTimeout(() => gate(() => { if (id === cycle) play(); }), PAUSE))
        .catch(() => {});
    }), HOLD)).catch(() => {});
  }

  // The font size follows the viewport (clamp), so measured widths go stale on resize: drop the cycle
  // at once (plain text, no overflow) and start a fresh one when the resizing settles.
  let width = innerWidth;
  let resizeTimer;
  addEventListener("resize", () => {
    if (innerWidth === width) return;
    width = innerWidth;
    stop();
    line.classList.remove("is-ready");
    line.textContent = "Design with AI.";
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => gate(play), 400);
  });

  (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => gate(play));
})();

// Shimmer bands run only while their text is on screen and the tab is visible.
(() => {
  const items = [...document.querySelectorAll(".shimmer")];
  if (!items.length) return;
  const onScreen = new Set();
  const sync = () => items.forEach((el) => el.classList.toggle("is-paused", document.hidden || !onScreen.has(el)));
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) onScreen.add(entry.target);
      else onScreen.delete(entry.target);
    }
    sync();
  });
  items.forEach((el) => observer.observe(el));
  document.addEventListener("visibilitychange", sync);
})();

// Hero scene: a comment is pinned to the date field, the agent answers, the fixed screen fades in, loop.
(() => {
  const link = document.querySelector(".hero-screenshot");
  if (!link) return;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ASK = "Make the date field wider";
  const LOOP = 10000;

  const scene = document.createElement("div");
  scene.className = "scene";
  scene.setAttribute("aria-hidden", "true");
  scene.innerHTML = `
    <img class="sc-after" src="assets/northline-scene-after.webp" width="2880" height="1720" alt="" decoding="async">
    <svg class="sc-cursor" viewBox="0 0 20 22" fill="none"><path d="M2 1.5v16l4.2-4 3 6.6 3-1.4-3-6.4 5.8-.2L2 1.5z" fill="#182820" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></svg>
    <span class="sc-ripple"></span>
    <span class="sc-pin"><span class="sc-num">1</span><span class="sc-check">✓</span></span>
    <div class="sc-card">
      <div class="sc-head"><span>You</span><span class="sc-status"></span></div>
      <p class="sc-ask"></p>
      <p class="sc-answer">Widened the field so the full date fits on one line.</p>
    </div>
    <div class="sc-island"><span class="sc-dot"></span><span class="sc-label shimmer">AI is working</span></div>`;
  link.insertBefore(scene, link.querySelector(".expand-mark"));

  const ask = scene.querySelector(".sc-ask");
  const status = scene.querySelector(".sc-status");
  const label = scene.querySelector(".sc-label");

  const setState = (...classes) => classes.forEach((c) => scene.classList.add(c));

  function resetScene() {
    scene.classList.add("is-instant");
    scene.classList.remove("has-cursor", "cursor-out", "has-pin", "has-card", "has-island", "is-done", "is-fading");
    ask.textContent = "";
    status.textContent = "";
    label.textContent = "AI is working";
    scene.getBoundingClientRect(); // flush so the jump back is not animated
    scene.classList.remove("is-instant");
  }
  function showFinal() {
    setState("has-pin", "has-card", "has-island", "is-done");
    ask.textContent = ASK;
    status.textContent = "Done · It.3";
    label.textContent = "AI: done";
  }

  let typer;
  function typeAsk() {
    let i = 0;
    typer = setInterval(() => {
      ask.textContent = ASK.slice(0, ++i);
      if (i >= ASK.length) clearInterval(typer);
    }, 35);
  }

  // One loop, described once: [time in ms, what happens].
  const timeline = [
    [500, () => setState("has-cursor")],
    [1800, () => setState("has-pin")],
    [2100, () => { setState("has-card"); typeAsk(); }],
    [3600, () => { status.textContent = "Sent to AI"; setState("cursor-out"); }],
    [4000, () => setState("has-island")],
    [6200, () => { setState("is-done"); status.textContent = "Done · It.3"; label.textContent = "AI: done"; }],
    [9200, () => setState("is-fading")],
  ];

  let timers = [];
  function start() {
    stop();
    resetScene();
    timers = timeline.map(([at, fn]) => setTimeout(fn, at));
    timers.push(setTimeout(start, LOOP));
  }
  function stop() {
    timers.forEach(clearTimeout);
    clearInterval(typer);
    timers = [];
  }

  if (reduced) { showFinal(); return; }

  let inView = false;
  let running = false;
  function sync() {
    const shouldRun = inView && !document.hidden;
    scene.querySelectorAll(".shimmer").forEach((el) => el.classList.toggle("is-paused", !shouldRun));
    if (shouldRun === running) return;
    running = shouldRun;
    if (running) start();
    else stop(); // frozen where it is; the next run starts from the top of the loop
  }
  new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; sync(); }).observe(link);
  document.addEventListener("visibilitychange", sync);
})();
