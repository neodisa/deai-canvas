/* Клавіатурна драбина оверлея — чиста логіка без DOM (етап Г). Вузол — будь-що, що вміє `parentOf`/`childrenOf`;
   `inspector.js` дає ці дві функції поверх справжнього DOM (з відсівом власних хостів оверлея й `<html>`). */

const siblingsOf = (n, api) => {
  const p = api.parentOf(n);
  return p ? api.childrenOf(p) : [n];
};

/**
 * Що робить клавіша з вибором. `null` — клавіша не наша (не споживаємо); `{ pin }` — новий вибір (null — зняти);
 * `{ off: true }` — вимкнути інспектор.
 *  · Esc: батько → на корені зняти вибір → без вибору вимкнути;
 *  · Enter: перший дочірній (немає дітей — не наша);
 *  · ← / →: сусід; на краю лишаємось на місці, але клавішу споживаємо — щоб сторінка не гортала вбік під рукою
 *    дизайнера, який рухається по дереву.
 */
export function nextPin(key, pinned, api) {
  if (key === 'Escape') {
    if (!pinned) return { off: true };
    const up = api.parentOf(pinned);
    return { pin: up || null };
  }
  if (!pinned) return null;
  if (key === 'Enter') {
    const kids = api.childrenOf(pinned);
    return kids.length ? { pin: kids[0] } : null;
  }
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const sibs = siblingsOf(pinned, api);
    const next = sibs[sibs.indexOf(pinned) + (key === 'ArrowRight' ? 1 : -1)];
    return { pin: next || pinned };
  }
  return null;
}

/**
 * Ціль відстаней Alt з клавіатури. `current` — вже вибрана ціль (або null). Alt+→/← крокують сусідами ВІД ПОТОЧНОЇ
 * цілі (першого разу — від вибраного елемента), Alt+↑ повертає батька. За краєм сусіда немає — `null`.
 */
export function altTarget(key, pinned, current, api) {
  if (!pinned) return null;
  if (key === 'ArrowUp') return api.parentOf(pinned);
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const base = current || pinned;
    const sibs = siblingsOf(base, api);
    return sibs[sibs.indexOf(base) + (key === 'ArrowRight' ? 1 : -1)] || null;
  }
  return null;
}
