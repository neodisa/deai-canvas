/**
 * Дерево превʼю йде за посиланнями всередині макета (0.32.0, етап Ж, Task 5).
 *
 * Чиста відповідь на одне питання: якій сторінці ПОТОЧНОЇ ітерації відповідає адреса, на яку щойно пішла рамка. Адреси
 * сторінок у маніфесті — відносні до обгортки (`<it>/<сторінка>/index.html`), тож база — тека, де лежить сама обгортка
 * (`location.pathname` без останнього сегмента): превʼю може стояти в корені хоста чи під префіксом.
 * Інша ітерація, невідомий шлях, не `index.html`, кривий `%`-запис — `null`: оболонка не міняє нічого.
 */

/** id сторінки (`pages[i].id`) або `null`. `framePath` — `pathname` документа рамки, `wrapperPath` — `pathname` обгортки. */
export function followPageOf(framePath, wrapperPath, pages, it) {
  if (typeof framePath !== "string" || typeof wrapperPath !== "string" || !it || !Array.isArray(pages)) return null;
  let frame;
  let base;
  try {
    frame = decodeURIComponent(framePath.split(/[?#]/)[0]);
    base = decodeURIComponent(wrapperPath.split(/[?#]/)[0]);
  } catch { return null; }
  base = base.slice(0, base.lastIndexOf("/") + 1);
  if (!frame.startsWith(base)) return null;
  let rel = frame.slice(base.length);
  if (rel === "" || rel.endsWith("/")) rel += "index.html";
  for (const p of pages) {
    if (p && p.it === it && typeof p.path === "string" && p.path === rel) return p.id;
  }
  return null;
}
