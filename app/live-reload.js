/**
 * Автооновлення рамки, коли файли макета змінились на диску (fb-01102026-309e3b).
 *
 * Чиста функція кроку опитування `/api/it-stamp`: стан → (новий стан, дія).
 * Жодного DOM і fetch — проводка в `app.js`.
 *   state  — `{ it, page, seen, pending, since }` або null;
 *   stamp  — відбиток вмісту ітерації (число) з сервера;
 *   held   — у рамці щось «в руках» (інспектор, набір коментаря): тоді
 *            замість перезавантаження — плашка (рішення власника 02.10.2026).
 * Дія: 'none' | 'reload' | 'notice'.
 *
 * ⛔ Чекаємо ТИШІ `QUIET_MS`: Клод пише сторінку кількома записами, і рамка без
 * паузи смикалась би на напівзаписаному HTML. ⛔ Зміна файлу — доказ ЗМІНИ, а не
 * того, що Клод ще працює: статус «Клод працює» (окреме замовлення 02.09.2026)
 * з цього сигналу не виводимо.
 */
export const QUIET_MS = 1500;

/** Чи опитувати відбиток зараз: лише робочий вид (у «Огляді» рамки нема —
 *  застарілі кадри знімає автозʼємка T-34), обрана ітерація, видима вкладка
 *  (схована не бачить рамки, а запити йшли б даремно) і НЕ екран «Задачі»
 *  (`home`): сцена під ним схована, перезавантаження рамки там нікому не видно,
 *  а плашка «макет змінився» (z-index 310) попливла б над екраном. Повернення на
 *  задачу робить повний `render()`, тож пропущена зміна не губиться. */
export function shouldPollStamp({ mode, picked, visible, home = false }) {
  return mode !== "canvas" && !!picked && !!visible && !home;
}

export function reloadStep(state, { it, page, stamp, now, held }) {
  if (typeof stamp !== "number") return { state, action: "none" };
  if (!state || state.it !== it || state.page !== page) {
    return { state: { it, page, seen: stamp, pending: null, since: 0 }, action: "none" };
  }
  if (stamp === state.seen) return { state: { ...state, pending: null }, action: "none" };
  if (stamp !== state.pending) return { state: { ...state, pending: stamp, since: now }, action: "none" };
  if (now - state.since < QUIET_MS) return { state, action: "none" };
  return { state: { ...state, seen: stamp, pending: null }, action: held ? "notice" : "reload" };
}
