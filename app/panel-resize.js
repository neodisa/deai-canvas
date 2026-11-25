/**
 * Ручка ширини лівої панелі (0.40). Окремий вузол `#panel-resize` у `body`, а не дитина `.panel`: `renderPanel()` переписує
 * `innerHTML` панелі, і перетягування із захопленим вказівником обірвалось би на першій же перемальовці.
 * Значення: `--panel-w` на `<html>` (лише в оболонці застосунку; превʼю цього модуля не вантажить), збереження — `dc-panel-w`.
 * Поки людина нічого не обрала, змінну НЕ пишемо — діє типова 246 із `:root` і всі нинішні поведінки вузьких вікон.
 */
import { t } from "./i18n.js";
import { KEY_STEP, PANEL_W_DEFAULT, clampPanelW, fitPanelW, panelWBounds, parseStoredW } from "./panel-width.js";

const KEY = "dc-panel-w";

/**
 * @param {object} o
 * @param {() => number} o.rightW   ширина відкритої правої панелі (0, коли нема)
 * @param {() => number[]} o.overflows   по кожній видимій назві `scrollWidth − clientWidth`
 * @param {() => void} o.onResize   після завершеної зміни (у «Огляді» — `fitAll()`, якщо камеру не рухали)
 */
export function mountPanelResize({ doc = document, rightW = () => 0, overflows = () => [], onResize = () => {} }) {
  const win = doc.defaultView;
  const root = doc.documentElement;
  const read = () => { try { return parseStoredW(win.localStorage.getItem(KEY)); } catch (e) { return null; } };
  const write = (w) => { try { win.localStorage.setItem(KEY, String(w)); } catch (e) { /* без сховища ширина живе до перезавантаження */ } };
  let pref = read();   // що людина обрала; на екрані — притиснуте до меж, які залежать від вікна
  const ctx = () => ({ vw: win.innerWidth, rightW: rightW() });
  const base = () => clampPanelW(pref ?? PANEL_W_DEFAULT, ctx());

  const handle = doc.createElement("div");
  handle.id = "panel-resize";
  handle.setAttribute("role", "separator");
  handle.setAttribute("aria-orientation", "vertical");
  handle.setAttribute("aria-label", t("panelResize"));
  handle.tabIndex = 0;
  doc.body.appendChild(handle);

  function paint() {
    const b = panelWBounds(ctx());
    if (pref == null) root.style.removeProperty("--panel-w");
    else root.style.setProperty("--panel-w", `${clampPanelW(pref, ctx())}px`);
    handle.setAttribute("aria-valuemin", String(b.min));
    handle.setAttribute("aria-valuemax", String(b.max));
    handle.setAttribute("aria-valuenow", String(base()));
  }
  function set(w, { save = true } = {}) {
    pref = clampPanelW(w, ctx());
    if (save) write(pref);
    paint();
  }
  function fit() {
    set(fitPanelW({ cur: base(), overflows: overflows(), bounds: panelWBounds(ctx()) }));
    onResize();
  }

  let drag = null;
  handle.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    handle.setPointerCapture(ev.pointerId);
    drag = { x: ev.clientX, w: base() };
    doc.body.classList.add("panel-dragging");
    win.dispatchEvent(new Event("dc-tip-hide"));
  });
  handle.addEventListener("pointermove", (ev) => { if (drag) set(drag.w + ev.clientX - drag.x, { save: false }); });
  const end = () => {
    if (!drag) return;
    drag = null;
    doc.body.classList.remove("panel-dragging");
    if (pref != null) write(pref);
    onResize();
  };
  handle.addEventListener("pointerup", end);
  handle.addEventListener("pointercancel", end);
  handle.addEventListener("dblclick", fit);
  handle.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      ev.preventDefault();
      set(base() + (ev.key === "ArrowRight" ? KEY_STEP : -KEY_STEP));
      onResize();
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      fit();
    }
  });

  /* Вікно стало вужчим чи відкрилась права панель — межі змінились: притискаємо вибір (сам вибір лишається в сховищі). */
  win.addEventListener("resize", paint);
  new win.MutationObserver(paint).observe(doc.body, { attributes: true, attributeFilter: ["class"] });
  paint();
  return { handle, set, fit };
}
