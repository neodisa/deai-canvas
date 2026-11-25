/**
 * Спільна підказка Deai (0.40): одна плашка в `body`, показ через 500 мс над елементом із `data-tip` або над `.row-name`,
 * причому назву рядка — ЛИШЕ коли її обрізано трикрапкою. Чисті функції (`isTruncated`, `tipText`, `placeTip`) окремо від
 * DOM-монтування, щоб юніт-тест не потребував браузера.
 * ⛔ Жодного `title` на тих самих елементах: дві підказки одночасно.
 */
export const TIP_DELAY = 500;
export const TIP_SELECTOR = "[data-tip],.row-name";

/** Вміст ширший за видиму частину (`text-overflow: ellipsis` спрацював). */
export function isTruncated(el) {
  return !!el && el.scrollWidth > el.clientWidth;
}

/** Текст підказки для елемента або `""`, коли показувати нічого. */
export function tipText(el) {
  if (!el) return "";
  const v = el.getAttribute("data-tip");
  if (v) return v;
  return el.matches(".row-name") && isTruncated(el) ? (el.textContent || "").trim() : "";
}

/** Позиція плашки: під елементом, притиснута до меж вікна; біля низу — над елементом. */
export function placeTip({ rect, w, h, vw, vh, gap = 6, pad = 8 }) {
  const left = Math.max(pad, Math.min(rect.left, vw - w - pad));
  let top = rect.bottom + gap;
  if (top + h > vh - pad) top = Math.max(pad, rect.top - gap - h);
  return { left, top };
}

/** Змонтувати плашку й слухачі на документі. Повертає `{ hide, el }`. */
export function mountTooltip(doc = document, { delay = TIP_DELAY } = {}) {
  const win = doc.defaultView;
  const tip = doc.createElement("div");
  tip.id = "dc-tip";
  tip.setAttribute("role", "tooltip");
  doc.body.appendChild(tip);
  let cur = null, timer = 0, watch = 0;
  const hide = () => { clearTimeout(timer); clearInterval(watch); cur = null; tip.classList.remove("on"); };
  const show = (el) => {
    const text = tipText(el);
    if (!text || !el.isConnected) return;
    tip.textContent = text;
    tip.classList.add("on");   // спершу робимо видимою — щоб виміряти, потім ставимо
    const { left, top } = placeTip({
      rect: el.getBoundingClientRect(), w: tip.offsetWidth, h: tip.offsetHeight, vw: win.innerWidth, vh: win.innerHeight,
    });
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
    /* Фонова перемальовка (опит, подія агента) могла прибрати вузол під плашкою — вона б висіла до першого руху вказівника. */
    watch = setInterval(() => { if (!cur || !cur.isConnected) hide(); }, 400);
  };
  const arm = (el) => { hide(); cur = el; timer = setTimeout(() => show(el), delay); };
  doc.addEventListener("pointerover", (ev) => {
    const el = ev.target.closest?.(TIP_SELECTOR);
    if (!el) { if (cur) hide(); return; }
    if (el !== cur) arm(el);
  }, true);
  doc.addEventListener("pointerout", (ev) => { if (cur && !cur.contains(ev.relatedTarget)) hide(); }, true);
  /* З клавіатури: рядок дерева у фокусі (лише `:focus-visible`) показує повну назву так само. */
  doc.addEventListener("focusin", (ev) => {
    const name = ev.target.closest?.(".row")?.querySelector(".row-name");
    if (name && ev.target.matches?.(":focus-visible")) arm(name);
  }, true);
  for (const type of ["pointerdown", "keydown", "dragstart", "wheel", "scroll"]) doc.addEventListener(type, hide, true);
  win.addEventListener("dc-tip-hide", hide);
  win.addEventListener("blur", hide);
  return { hide, el: tip };
}
