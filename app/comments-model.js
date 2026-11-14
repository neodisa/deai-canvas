/**
 * Модель панелі коментарів оболонки (Deai 0.26.0, етап Б1). Чиста: ні DOM, ні мережі. Вхід — знімок коментатора
 * (`CommentLayer.snapshot()`: копії коментарів із `n`, `scope`, `where`, `iter`). Що «поточне», вирішує КОМЕНТАТОР
 * (`scope`), а не ця модель — друга реалізація того самого знання розійшлась би мовчки (принцип 6 `PRODUCT.md`).
 */
const SHOT_RE = /^(data:image\/(png|jpe?g|webp|gif);base64,|https?:\/\/)/i;

const list = (snapshot) => (snapshot && Array.isArray(snapshot.comments) ? snapshot.comments : []);
const byNewest = (a, b) => (Number(b.n) || 0) - (Number(a.n) || 0);
const closedAt = (c) => Number((c.meta && c.meta.resolvedAt) || c.resolvedAt || 0) || 0;

/** Пошук як у панелі коментатора: `#N` — точний номер; інакше підрядок без регістру в «#n текст автор час цитата». */
export function matchQuery(c, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return true;
  const num = /^#(\d+)$/.exec(q);
  if (num) return Number(c.n) === Number(num[1]);
  const sel = (c.meta && c.meta.sel) || "";
  return `#${c.n} ${c.text || ""} ${c.author || ""} ${c.ts || ""} ${sel}`.toLowerCase().includes(q);
}

/** Адресат картки: `_aud` комбінованого сховища; без нього (лише локальний канал) — 'local'. */
export const audOf = (c) => (c && c._aud === "project" ? "project" : "local");
/** Доручено Claude (`meta.assignee`, спека Б-Р6) — те саме правило, що `for_agent` у `serve.py`. */
export const assignedToClaude = (c) => !!(c && c.meta && c.meta.assignee === "claude");
/** Фільтр панелі «Усі / Для Claude / Команда». */
export const FILTERS = ["all", "local", "project"];
const passFilter = (c, f) => (f === "local" || f === "project" ? audOf(c) === f : true);

/** `{fresh, open, earlier, closed}`: «нові від команди» (набір `fresh`, лише відкриті), відкриті поточні (без нових),
 *  відкриті попередніх ітерацій, закриті поточні. */
export function commentSections(snapshot, { query = "", filter = "all", fresh = null } = {}) {
  const hit = (c) => matchQuery(c, query) && passFilter(c, filter);
  const isFresh = (c) => !!(fresh && fresh.has(c.id)) && c.status === "open";
  const all = list(snapshot);
  return {
    fresh: all.filter((c) => isFresh(c) && hit(c)).sort(byNewest),
    open: all.filter((c) => c.status === "open" && c.scope === "current" && !isFresh(c) && hit(c)).sort(byNewest),
    earlier: all.filter((c) => c.status === "open" && c.scope === "earlier" && !isFresh(c) && hit(c)).sort(byNewest),
    closed: all.filter((c) => c.status === "resolved" && c.scope === "current" && hit(c))
      .sort((a, b) => (closedAt(b) - closedAt(a)) || byNewest(a, b)),
  };
}

/** Відкриті поточні — число на кнопці острівця. */
export function openCount(snapshot) {
  return list(snapshot).filter((c) => c.status === "open" && c.scope === "current").length;
}

/** `src` мініатюри або `null`: лише растрові `data:image/…;base64,` і `http(s)://` (не `javascript:`, не `data:text/html`). */
export function shotSrc(c) {
  const s = c && c.meta && (c.meta.shot || c.meta.shotUrl);
  return typeof s === "string" && SHOT_RE.test(s) ? s : null;
}
