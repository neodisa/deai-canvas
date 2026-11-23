/**
 * «Нові командні коментарі» (Deai 0.27.0, Б2.4). Чиста: ні DOM, ні мережі, ні localStorage — сховище дає `app.js`.
 * Новий = командний (`_aud === 'project'` у знімку; у відповіді `/api/comment-news` — усі), відкритий, не мій, id не бачили.
 * ⛔ Маркер «бачив» — НАБІР id, а не `ts` (поправка 2 плану Б2): `ts` коментатора — локальний час автора з точністю до
 *   хвилини, а команда в різних поясах; маркер за часом губив би нові або плутав коментарі однієї хвилини.
 */
import { pinTarget } from "./overview-pins.js";

export const SEEN_MAX = 1000;
/** Ключ маркера в localStorage: простір (або `-`) і задача — id задач у різних просторах можуть збігатися. */
export const seenKey = (spaceId, taskId) => `dc-seen:${spaceId || "-"}:${taskId}`;
/** Ключ маркера «бачив» для ВІДПОВІДЕЙ (окремий від `seenKey`: старий клієнт пише лише головний): `dc-seen-r:<простір>:<задача>`. */
export const replySeenKey = (spaceId, taskId) => `dc-seen-r:${spaceId || "-"}:${taskId}`;
/** Рядок зі сховища → `Set` id; маркера нема або він битий — `null` (перший погляд, див. `baseline`). */
export function readSeen(raw) {
  if (typeof raw !== "string" || !raw) return null;
  try {
    const v = JSON.parse(raw);
    return v && v.v === 1 && Array.isArray(v.ids) ? new Set(v.ids.filter((x) => typeof x === "string")) : null;
  } catch { return null; }
}
/** `Set` → рядок для сховища: лише останні `SEEN_MAX` (порядок — додавання). Обрізка йде за порядком вставки: на першому
 *  погляді `baseline` вставляє id у порядку списку, тож відпадають перші зі списку, а не «найстарші» за часом. */
export const writeSeen = (set) => JSON.stringify({ v: 1, ids: [...(set || [])].slice(-SEEN_MAX) });
/** Перший погляд на задачу: усе, що вже є, — бачене (накопичене не вивалюється «новим»). */
export const baseline = (items) => new Set((items || []).map((c) => c && c.id).filter((x) => typeof x === "string"));
/** Додати id у маркер (переставляючи в кінець — `writeSeen` тримає найсвіжіші). */
export function markSeen(seen, ids) {
  const s = new Set(seen || []);
  for (const id of ids || []) if (typeof id === "string") { s.delete(id); s.add(id); }
  return s;
}
/** Командні коментарі знімка коментатора. */
export const teamOf = (comments) => (Array.isArray(comments) ? comments.filter((c) => c && c._aud === "project") : []);
/** Що рахується новиною (0.35): командні коментарі (як `teamOf`; відкритість перевіряє `isNew`) ПЛЮС відповіді на коментарі
 *  будь-якого каналу — відповідь агента на локальний пін теж новина. Відповідь — елемент тієї ж форми, що й коментар
 *  (`id`, `ts`, `author`, `status`, `version`), тож `isNew`/`baseline`/`arrived`/`countNew` працюють без змін; `parent` — id коментаря.
 *  Відповіді ЗАКРИТИХ коментарів теж у списку, зі статусом батька: `isNew`/`countNew` рахують лише відкриті (новиною вони не стають),
 *  зате `baseline` їх покриває — і коли закритий коментар відкриють знову, його давні відповіді не зʼявляться «новими».
 *  Відповідь без рядкового `id` пропускається (нема що запамʼятати в маркері «бачив»). */
export function newsItems(comments) {
  const all = Array.isArray(comments) ? comments : [];
  const replies = [];
  for (const c of all) {
    if (!c || !Array.isArray(c.replies)) continue;
    for (const r of c.replies) {
      if (!r || typeof r.id !== "string") continue;
      replies.push({ id: r.id, ts: r.ts, author: r.author, status: c.status, version: c.meta && c.meta.version, parent: c.id });
    }
  }
  return teamOf(all).concat(replies);
}
/** Чи «новий»: відкритий, не мій (`me` — імʼя автора цього вікна; порожнє — «мого» нема), id не бачили. */
export const isNew = (c, seen, me) => !!c && typeof c.id === "string" && c.status === "open"
  && !(me && c.author === me) && !!seen && !seen.has(c.id);
/** Що зʼявилось відносно попереднього знімка (`prevIds` — `Set` або `null` для першого: тоді нічого). */
export function arrived(prevIds, comments) {
  if (!prevIds) return [];
  return (comments || []).filter((c) => c && typeof c.id === "string" && !prevIds.has(c.id));
}
/** Нові за сторінками дерева: `{pageId: n}`. Виклик передає ЛИШЕ вже відібраний список «нових» (`isNew`), не усі коментарі; сторінку дає тег версії піна, як на «Огляді» (`pinTarget`). */
export function newsByPage(comments) {
  const out = {};
  for (const c of comments || []) {
    const t = pinTarget(c);
    if (t && t.page) out[t.page] = (out[t.page] || 0) + 1;
  }
  return out;
}
/** Скільки «нових» у відповіді `/api/comment-news` для задачі (число на вкладці). */
export const countNew = (items, seen, me) => (Array.isArray(items) ? items.filter((c) => isNew(c, seen, me)).length : 0);
