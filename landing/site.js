const tabList = document.querySelector("[data-gallery-tabs]");
const tabs = [...tabList.querySelectorAll('[role="tab"]')];
const panels = tabs.map((tab) => document.getElementById(tab.getAttribute("aria-controls")));
const horizontalTabs = matchMedia("(max-width: 760px)");

function showPanel(index) {
  tabs.forEach((tab, i) => {
    const selected = i === index;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    panels[i].hidden = !selected;
  });
}

function setTabOrientation() {
  tabList.setAttribute("aria-orientation", horizontalTabs.matches ? "horizontal" : "vertical");
}

tabs.forEach((tab, i) => {
  panels[i].setAttribute("role", "tabpanel");
  panels[i].setAttribute("aria-labelledby", tab.id);
  tab.addEventListener("click", () => showPanel(i));
});
setTabOrientation();
horizontalTabs.addEventListener("change", setTabOrientation);
showPanel(0);
tabList.hidden = false;

tabList.addEventListener("keydown", (event) => {
  const current = tabs.indexOf(event.target);
  if (current < 0 || event.altKey || event.ctrlKey || event.metaKey) return;

  const previous = horizontalTabs.matches ? "ArrowLeft" : "ArrowUp";
  const next = horizontalTabs.matches ? "ArrowRight" : "ArrowDown";
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
  showPanel(index);
  tabs[index].focus();
});

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

const copyButton = document.querySelector("[data-copy]");
const copyStatus = document.querySelector("[data-copy-status]");
const prompt = document.getElementById("setup-prompt");
let copyTimer;

async function copyPrompt() {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(prompt.textContent.trim());
      return true;
    } catch {
      // Fall through to the select-and-copy path when the browser denies clipboard access.
    }
  }

  const selection = getSelection();
  const range = document.createRange();
  range.selectNodeContents(prompt);
  selection.removeAllRanges();
  selection.addRange(range);
  const copied = document.execCommand("copy");
  if (copied) selection.removeAllRanges();
  return copied;
}

copyButton.hidden = false;
copyButton.addEventListener("click", async () => {
  clearTimeout(copyTimer);
  if (await copyPrompt()) {
    copyButton.textContent = "Copied";
    copyStatus.classList.add("visually-hidden");
    copyStatus.textContent = "Setup prompt copied to clipboard.";
    copyTimer = setTimeout(() => { copyButton.textContent = "Copy prompt"; }, 2400);
  } else {
    copyButton.textContent = "Copy prompt";
    copyStatus.classList.remove("visually-hidden");
    copyStatus.textContent = "Prompt selected. Press Ctrl+C or ⌘C to copy.";
  }
});
