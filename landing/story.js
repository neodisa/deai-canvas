// Story vignettes: each one plays its short entrance once, when its step first scrolls into view.
// Without JS (or without IntersectionObserver) the CSS shows the final state; the hidden start
// state only exists under `.js` and only when motion is allowed.
(() => {
  const steps = document.querySelectorAll(".story-steps > li");
  if (!steps.length) return;
  if (!("IntersectionObserver" in window)) {
    for (const step of steps) step.classList.add("is-in");
    return;
  }
  const seen = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add("is-in");
      seen.unobserve(entry.target);
    }
  }, { threshold: 0.35 });
  for (const step of steps) seen.observe(step);
})();
