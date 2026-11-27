// Story vignettes: each one plays its short entrance once, when its step first scrolls into view.
// The hidden start state is gated by `html.story-ready`, which this script sets only once it is running:
// without JS, with a failed script load, or without IntersectionObserver the CSS shows the final state.
// It also only applies when motion is allowed.
(() => {
  const steps = document.querySelectorAll(".story-steps > li");
  if (!steps.length) return;
  if (!("IntersectionObserver" in window)) {
    for (const step of steps) step.classList.add("is-in");
    return;
  }
  document.documentElement.classList.add("story-ready");
  const seen = new IntersectionObserver((entries) => {
    // Steps entering together are staggered by their index in this batch; a step entering alone has no delay.
    let n = 0;
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.style.setProperty("--d", n++);
      entry.target.classList.add("is-in");
      seen.unobserve(entry.target);
    }
  }, { threshold: 0.35 });
  for (const step of steps) seen.observe(step);
})();
