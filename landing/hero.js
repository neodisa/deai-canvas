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
