function initTabs(tabList, horizontalQuery) {
  const tabs = [...tabList.querySelectorAll('[role="tab"]')];
  const panels = tabs.map((tab) => document.getElementById(tab.getAttribute("aria-controls")));
  const horizontal = () => !horizontalQuery || horizontalQuery.matches;

  function show(index) {
    tabs.forEach((tab, i) => {
      const selected = i === index;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panels[i].hidden = !selected;
    });
  }

  // Other scripts (the scroll tour) can follow user choices and drive the selection through events,
  // so this function stays the single place that knows how a tab is selected.
  function announce(index) {
    tabList.dispatchEvent(new CustomEvent("tabs:select", { detail: { index } }));
  }
  tabList.addEventListener("tabs:show", (event) => show(event.detail.index));

  function setOrientation() {
    tabList.setAttribute("aria-orientation", horizontal() ? "horizontal" : "vertical");
  }

  tabs.forEach((tab, i) => {
    panels[i].setAttribute("role", "tabpanel");
    panels[i].setAttribute("aria-labelledby", tab.id);
    tab.addEventListener("click", () => { show(i); announce(i); });
  });
  setOrientation();
  horizontalQuery?.addEventListener("change", setOrientation);
  show(0);
  tabList.hidden = false;

  tabList.addEventListener("keydown", (event) => {
    const current = tabs.indexOf(event.target);
    if (current < 0 || event.altKey || event.ctrlKey || event.metaKey) return;
    const previous = horizontal() ? "ArrowLeft" : "ArrowUp";
    const next = horizontal() ? "ArrowRight" : "ArrowDown";
    const last = tabs.length - 1;
    let index;
    switch (event.key) {
      case previous: index = current === 0 ? last : current - 1; break;
      case next: index = current === last ? 0 : current + 1; break;
      case "Home": index = 0; break;
      case "End": index = last; break;
      default: return;
    }
    event.preventDefault();
    show(index);
    tabs[index].focus();
    announce(index);
  });
}

initTabs(document.querySelector("[data-gallery-tabs]"), matchMedia("(max-width: 760px)"));
initTabs(document.querySelector("[data-setup-tabs]"), null);

const dialog = document.querySelector("[data-screenshot-dialog]");
const enlarged = dialog.querySelector("[data-enlarged-image]");
let screenshotTrigger;

if (typeof dialog.showModal === "function") {
  for (const link of document.querySelectorAll("[data-screenshot]")) {
    link.addEventListener("click", (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      screenshotTrigger = link;
      const thumbnail = link.querySelector("img");
      const image = document.createElement("img");
      image.src = thumbnail.currentSrc || thumbnail.src;
      image.alt = thumbnail.alt;
      image.width = Number(thumbnail.getAttribute("width"));
      image.height = Number(thumbnail.getAttribute("height"));
      enlarged.replaceChildren(image);
      dialog.querySelector("h2").textContent = link.dataset.screenshot;
      dialog.querySelector("[data-full-size]").href = link.href;
      dialog.showModal();
    });
  }
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    screenshotTrigger?.focus({ preventScroll: true });
    enlarged.replaceChildren();
  });
}

const setupStatus = document.querySelector(".setup-action [data-copy-status]");

for (const button of document.querySelectorAll("[data-copy]")) {
  const source = document.getElementById(button.dataset.copy);
  const label = button.textContent;
  // Each copy button reports into the live region of its own [data-copy-scope] block (the setup board).
  const copyStatus = button.closest("[data-copy-scope]").querySelector("[data-copy-status]");
  let timer;
  button.hidden = false;
  button.addEventListener("click", async () => {
    clearTimeout(timer);
    if (await copyText(source.textContent.trim())) {
      button.textContent = "Copied";
      copyStatus.classList.add("visually-hidden");
      copyStatus.textContent = "";
      requestAnimationFrame(() => { copyStatus.textContent = "Copied to clipboard."; });
      timer = setTimeout(() => { button.textContent = label; copyStatus.textContent = ""; }, 2400);
    } else {
      const selection = getSelection();
      const range = document.createRange();
      range.selectNodeContents(source);
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = label;
      copyStatus.classList.remove("visually-hidden");
      copyStatus.textContent = "Text selected. Press Ctrl+C or ⌘C to copy.";
    }
  });
}

// Switching install tabs drops a stale copy message. Arrow keys move focus; Safari does not focus a clicked button.
function clearCopyStatus() {
  setupStatus.textContent = "";
  setupStatus.classList.add("visually-hidden");
}
const setupTabs = document.querySelector("[data-setup-tabs]");
setupTabs.addEventListener("click", clearCopyStatus);
setupTabs.addEventListener("focusin", clearCopyStatus);

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fall back to a hidden textarea when the browser denies clipboard access.
    }
  }
  const previous = document.activeElement;
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.append(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  previous?.focus({ preventScroll: true });
  return copied;
}

const SHARE = {
  title: "Deai Canvas",
  text: "Deai Canvas — a local workspace for reviewing what your AI agent designs. Check it out:",
  url: "https://deai-canvas.vercel.app/",
};
const shareButton = document.querySelector("[data-share]");
const shareStatus = document.querySelector("[data-share-status]");
let shareTimer;

shareButton.hidden = false;
shareButton.addEventListener("click", async () => {
  if (navigator.share && matchMedia("(pointer: coarse)").matches) {
    try {
      await navigator.share(SHARE);
    } catch {
      // The share sheet was closed.
    }
    return;
  }
  clearTimeout(shareTimer);
  shareStatus.textContent = "";
  const copied = await copyText(`${SHARE.text} ${SHARE.url}`);
  shareButton.textContent = copied ? "Link copied" : "Copy failed";
  shareStatus.textContent = copied ? "A link to Deai Canvas was copied to the clipboard." : "The link could not be copied.";
  shareTimer = setTimeout(() => { shareButton.textContent = "Share"; shareStatus.textContent = ""; }, 2400);
});

const menuButton = document.querySelector("[data-menu]");
const siteNav = document.getElementById("site-nav");
const compactHeader = matchMedia("(max-width: 760px)");

function setMenu(open, focusButton = false) {
  menuButton.setAttribute("aria-expanded", String(open));
  siteNav.classList.toggle("is-open", open);
  if (!open && focusButton) menuButton.focus();
}

menuButton.hidden = false;
menuButton.addEventListener("click", () => setMenu(menuButton.getAttribute("aria-expanded") !== "true"));
siteNav.addEventListener("click", (event) => {
  if (event.target.closest("a")) setMenu(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && siteNav.classList.contains("is-open")) setMenu(false, true);
});
document.addEventListener("click", (event) => {
  if (siteNav.classList.contains("is-open") && !siteNav.contains(event.target) && !menuButton.contains(event.target)) setMenu(false);
});
compactHeader.addEventListener("change", () => setMenu(false));
