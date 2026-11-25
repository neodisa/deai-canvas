/**
 * Плашка пошуку по макету (0.40). Живе в оболонці; підсвітка — у вікні рамки через CSS Custom Highlight API:
 * `CSS.highlights` вікна рамки + правила `::highlight()` у `adoptedStyleSheets` ЇЇ документа. ⛔ DOM макета не міняємо
 * (коментатор, інспектор, «В Figma» нічого не бачать): жодних `<mark>`, класів, атрибутів, стилів на вузлах.
 * ⛔ Вузли й конструктори — з ІНШОГО вікна: лише `w.Highlight`/`w.CSSStyleSheet`, жодного `instanceof`.
 */
import { FIND_LIMIT, SKIP_SELECTORS, SKIP_TAGS, findInTexts } from "./find-model.js";
import { ico } from "./icons.js";
import { t } from "./i18n.js";

const SHEET = "::highlight(deai-find){background-color:#ffe28a;color:#1d2433}::highlight(deai-find-cur){background-color:#ff9f43;color:#1d2433}";
const SKIP_SEL = SKIP_SELECTORS.join(",");

/** Видимі текстові вузли документа рамки: без скриптів/стилів/шаблонів, наших оверлеїв і прихованих елементів. */
function textNodes(doc) {
  const w = doc.defaultView;
  if (!doc.body || !w) return [];
  const walker = doc.createTreeWalker(doc.body, w.NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      const p = n.parentElement;
      if (!p || SKIP_TAGS.has(p.localName) || p.closest(SKIP_SEL)) return w.NodeFilter.FILTER_REJECT;
      if (!n.data.trim() || p.getClientRects().length === 0) return w.NodeFilter.FILTER_REJECT;
      return w.NodeFilter.FILTER_ACCEPT;
    },
  });
  const out = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) out.push(n);
  return out;
}

export function createFindBar({ getFrame, onClose = () => {}, delay = 120 }) {
  const el = document.createElement("div");
  el.id = "find";
  el.setAttribute("role", "search");
  el.hidden = true;
  el.innerHTML = `<input id="find-q" type="text" spellcheck="false" autocomplete="off" aria-label="${t("findPlaceholder")}" placeholder="${t("findPlaceholder")}">`
    + `<span id="find-n" class="find-n" aria-live="polite"></span>`
    + `<button class="ctl ctl--icon find-prev" data-find="prev" aria-label="${t("findPrev")}" data-tip="${t("findPrev")}">${ico("chevdown", 16)}</button>`
    + `<button class="ctl ctl--icon" data-find="next" aria-label="${t("findNext")}" data-tip="${t("findNext")}">${ico("chevdown", 16)}</button>`
    + `<button class="ctl ctl--icon" data-find="close" aria-label="${t("findClose")}" data-tip="${t("findClose")}">${ico("x", 16)}</button>`;
  document.body.appendChild(el);
  const input = el.querySelector("#find-q");
  const count = el.querySelector("#find-n");
  let nodes = [], ranges = [], cur = -1, capped = false, timer = 0, sheet = null, sheetDoc = null;

  const frameDoc = () => { try { return getFrame()?.contentDocument || null; } catch (e) { return null; } };
  const frameWin = () => frameDoc()?.defaultView || null;

  function clearHighlight() {
    try {
      const w = sheetDoc?.defaultView;
      w?.CSS?.highlights?.delete("deai-find");
      w?.CSS?.highlights?.delete("deai-find-cur");
      if (sheet && sheetDoc) sheetDoc.adoptedStyleSheets = sheetDoc.adoptedStyleSheets.filter((s) => s !== sheet);
    } catch (e) { /* документ уже мертвий */ }
    sheet = null; sheetDoc = null;
  }
  function paint(doc) {
    const w = doc.defaultView;
    if (!w?.CSS?.highlights || !w.Highlight || !w.CSSStyleSheet) return;
    if (sheetDoc !== doc) {
      clearHighlight();
      sheet = new w.CSSStyleSheet();
      sheet.replaceSync(SHEET);
      doc.adoptedStyleSheets = [...doc.adoptedStyleSheets, sheet];
      sheetDoc = doc;
    }
    w.CSS.highlights.set("deai-find", new w.Highlight(...ranges));
    w.CSS.highlights.set("deai-find-cur", new w.Highlight(...(cur >= 0 ? [ranges[cur]] : [])));
  }
  function label() {
    const q = input.value;
    count.classList.toggle("none", !!q && ranges.length === 0);
    count.textContent = !q ? "" : ranges.length ? `${cur + 1} / ${capped ? `${FIND_LIMIT}+` : ranges.length}` : "0 / 0";
  }
  function show() {
    const doc = frameDoc();
    if (doc && ranges.length) {
      paint(doc);
      try { ranges[cur].startContainer.parentElement?.scrollIntoView({ block: "center" }); } catch (e) { /* вузол зник */ }
    }
    label();
  }
  function run() {
    clearTimeout(timer);
    timer = 0;   // відкладений пошук виконано: наступний Enter — це «наступний збіг», а не повторний пошук
    const doc = frameDoc();
    nodes = []; ranges = []; cur = -1; capped = false;
    if (!doc || !input.value) { clearHighlight(); label(); return; }
    nodes = textNodes(doc);
    const r = findInTexts(nodes.map((n) => n.data), input.value);
    capped = r.capped;
    ranges = r.hits.map((h) => { const x = doc.createRange(); x.setStart(nodes[h.i], h.start); x.setEnd(nodes[h.i], h.end); return x; });
    cur = ranges.length ? 0 : -1;
    if (!ranges.length) clearHighlight();
    show();
  }
  function step(d) {
    if (!ranges.length) return;
    cur = (cur + d + ranges.length) % ranges.length;
    show();
  }
  function close() {
    clearTimeout(timer);
    clearHighlight();
    nodes = []; ranges = []; cur = -1;
    if (el.hidden) return;
    el.hidden = true;
    onClose();
  }
  function open() {
    el.hidden = false;
    input.focus();
    input.select();
    if (input.value) run();
  }

  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, delay); });
  input.addEventListener("keydown", (ev) => {
    if (ev.isComposing) return;
    if (ev.key === "Enter") { ev.preventDefault(); if (timer) run(); else step(ev.shiftKey ? -1 : 1); }
    else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); close(); }
  });
  el.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-find]");
    if (!b) return;
    if (b.dataset.find === "prev") step(-1);
    else if (b.dataset.find === "next") step(1);
    else close();
  });

  return { open, close, next: () => step(1), prev: () => step(-1), rerun: () => { if (!el.hidden) run(); }, isOpen: () => !el.hidden, el };
}
