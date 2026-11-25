// Scroll-driven tour: on large screens the gallery pins while the page scrolls and each scroll step selects the next
// view. Selection itself belongs to initTabs in site.js; this file only turns scroll position into a "tabs:show" event
// and turns tab choices ("tabs:select") into a scroll, so scroll and tabs never disagree.
(() => {
  const gallery = document.querySelector("[data-tour]");
  if (!gallery) return;
  const tabList = gallery.querySelector("[data-gallery-tabs]");
  const frame = gallery.querySelector(".gallery-frame");
  const progress = gallery.querySelector(".tour-progress");
  const tabs = [...tabList.querySelectorAll('[role="tab"]')];
  const count = tabs.length;
  const STEP = 0.7; // viewport heights of scrolling per view
  const PIN_GAP = 24; // space between the top of the window (or a sticky header) and the pinned frame
  const ARRIVE_PX = 2; // a smooth scroll we started counts as arrived within this distance
  const LOCK_MS = 1500; // fallback: stop waiting for that scroll to arrive
  const query = matchMedia("(min-width: 1024px) and (min-height: 640px) and (prefers-reduced-motion: no-preference)");

  let active = false;
  let ticking = false;
  let lockTarget = null; // scroll position of a smooth scroll we started ourselves
  let lockTimer;
  let observer;
  let top = PIN_GAP; // pinned frame offset, re-measured on resize only

  // The pinned frame has to start below a sticky or fixed header, if there is one.
  function pinTop() {
    const header = document.querySelector(".site-header");
    const position = header ? getComputedStyle(header).position : "static";
    return (position === "sticky" || position === "fixed" ? header.getBoundingClientRect().height : 0) + PIN_GAP;
  }
  const stepPx = () => innerHeight * STEP;
  const selected = () => tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");

  function measure() {
    top = pinTop();
    gallery.style.setProperty("--tour-top", `${top}px`);
    gallery.style.height = `${frame.offsetHeight + count * stepPx()}px`;
  }

  function update() {
    ticking = false;
    if (!active) return;
    const scrolled = top - gallery.getBoundingClientRect().top;
    const range = count * stepPx();
    const p = Math.min(1, Math.max(0, scrolled / range));
    progress.style.setProperty("--p", p.toFixed(4));
    if (lockTarget !== null) {
      if (Math.abs(scrollY - lockTarget) > ARRIVE_PX) return;
      lockTarget = null;
      clearTimeout(lockTimer);
    }
    const index = Math.min(count - 1, Math.floor(p * count));
    if (index !== selected()) tabList.dispatchEvent(new CustomEvent("tabs:show", { detail: { index } }));
  }

  function request() {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  }

  // +1 px lands just inside the step, not on the previous step's boundary.
  function goTo(index) {
    const target = scrollY + gallery.getBoundingClientRect().top - top + index * stepPx() + 1;
    lockTarget = Math.max(0, Math.round(Math.min(target, document.documentElement.scrollHeight - innerHeight)));
    clearTimeout(lockTimer);
    lockTimer = setTimeout(unlock, LOCK_MS);
    scrollTo({ top: target, behavior: "smooth" });
  }

  // The user took over the scroll (wheel, touch, keys other than the tab arrows): follow them at once.
  function unlock() {
    if (lockTarget === null) return;
    lockTarget = null;
    clearTimeout(lockTimer);
    request();
  }
  const onKey = (event) => { if (!tabList.contains(event.target)) unlock(); };

  const onSelect = (event) => { if (active) goTo(event.detail.index); };
  const onResize = () => { measure(); request(); };

  function enable() {
    active = true;
    gallery.classList.add("is-tour");
    measure();
    // Keep the user's own choice unless the page is already scrolled into the tour.
    const scrolled = top - gallery.getBoundingClientRect().top;
    if (scrolled > 0 && scrolled < count * stepPx()) request();
    addEventListener("scroll", request, { passive: true });
    addEventListener("wheel", unlock, { passive: true });
    addEventListener("touchstart", unlock, { passive: true });
    addEventListener("keydown", onKey);
    addEventListener("resize", onResize); // window height changes the step size even when the frame keeps its size
    observer = new ResizeObserver(onResize);
    observer.observe(frame);
  }

  function disable() {
    // Scrolled inside the tall track? Keep the gallery in view once the track collapses.
    const box = gallery.getBoundingClientRect();
    const inside = box.top < 0 && box.bottom > innerHeight;
    active = false;
    lockTarget = null;
    clearTimeout(lockTimer);
    gallery.classList.remove("is-tour");
    gallery.style.removeProperty("height");
    gallery.style.removeProperty("--tour-top");
    progress.style.removeProperty("--p");
    removeEventListener("scroll", request);
    removeEventListener("wheel", unlock);
    removeEventListener("touchstart", unlock);
    removeEventListener("keydown", onKey);
    removeEventListener("resize", onResize);
    observer?.disconnect();
    if (inside) scrollTo(0, scrollY + gallery.getBoundingClientRect().top - PIN_GAP);
  }

  tabList.addEventListener("tabs:select", onSelect);
  const sync = () => { if (query.matches && !active) enable(); else if (!query.matches && active) disable(); };
  query.addEventListener("change", sync);
  sync();
})();
