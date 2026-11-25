/**
 * Ширина лівої панелі (0.40): чисті межі й вибір «під найдовшу назву». Без DOM — `panel-resize.js` читає й пише
 * сторінку, тут лише арифметика.
 */
export const PANEL_W_DEFAULT = 246;
export const PANEL_W_MIN = 200;
export const PANEL_W_MAX = 520;
/** Інваріант оболонки (коментар біля `body.with-insp` у `styles.css`): сцена не вужча за 420 px. */
export const STAGE_MIN = 420;
export const KEY_STEP = 16;

/** `{min, max}` для вікна завширшки `vw` і відкритої правої панелі завширшки `rightW` (0, коли її нема). */
export function panelWBounds({ vw, rightW = 0 }) {
  const max = Math.max(PANEL_W_MIN, Math.min(PANEL_W_MAX, vw - rightW - STAGE_MIN));
  return { min: PANEL_W_MIN, max };
}

export function clampPanelW(want, ctx) {
  const { min, max } = panelWBounds(ctx);
  return Math.round(Math.min(max, Math.max(min, want)));
}

/**
 * Куди ставити ширину подвійним кліком: `overflows` — по кожній назві `scrollWidth − clientWidth` (0, коли влізла).
 * Є що показувати — додаємо найбільше переповнення (+2 px на округлення); вже впираємось у межу чи нічого не обрізано —
 * повертаємо типову (притиснуту до меж).
 */
export function fitPanelW({ cur, overflows, bounds }) {
  const extra = Math.max(0, ...overflows);
  const pin = (w) => Math.round(Math.min(bounds.max, Math.max(bounds.min, w)));
  if (extra > 0) {
    const target = pin(cur + extra + 2);
    if (target > cur) return target;
  }
  return pin(PANEL_W_DEFAULT);
}

/** Збережене значення → ціле в межах, інакше `null`. */
export function parseStoredW(raw) {
  if (typeof raw !== "string" || !/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return n >= PANEL_W_MIN && n <= PANEL_W_MAX ? n : null;
}
