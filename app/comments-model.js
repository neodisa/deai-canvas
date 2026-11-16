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
/** Вкладки фільтра панелі — у ЦЬОМУ порядку (рішення власника 16.11.2026: основна робота — з Claude, «Усі» — третя). */
export const FILTERS = ["local", "project", "all"];
/** «Для Claude» — те, що Claude бере в роботу: локальні + доручені йому командні. Те саме правило, що `for_agent`
 *  у `app/serve.py` і `bin/inbox.py` за замовчуванням; інакше вкладка обіцяла б більше або менше, ніж бачить агент. */
export const forClaude = (c) => audOf(c) === "local" || assignedToClaude(c);
const passFilter = (c, f) => (f === "local" ? forClaude(c) : f === "project" ? audOf(c) === "project" : true);

/** `{fresh, open, earlier, closed}`: «нові від команди» (набір `fresh`, лише відкриті), відкриті поточні (без нових),
 *  відкриті попередніх ітерацій, закриті поточні. */
export function commentSections(snapshot, { query = "", filter = "all", fresh = null } = {}) {
  const hit = (c) => matchQuery(c, query) && passFilter(c, filter);
  // «Нові від команди» — лише командні (захист: локальний id у `fresh` сюди не потрапляє).
  const isFresh = (c) => !!(fresh && fresh.has(c.id)) && c.status === "open" && audOf(c) === "project";
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

/** Числа на вкладках фільтра: відкриті поточні за правилом кожної вкладки (пошук НЕ враховано — числа про сторінку,
 *  а не про запит) і `fresh` — відкриті нові командні (той самий відбір, що розділ «Нові від команди»). */
export function filterCounts(snapshot, fresh = null) {
  const all = list(snapshot);
  const cur = all.filter((c) => c.status === "open" && c.scope === "current");
  return {
    local: cur.filter(forClaude).length,
    project: cur.filter((c) => audOf(c) === "project").length,
    all: cur.length,
    fresh: all.filter((c) => c.status === "open" && audOf(c) === "project" && !!(fresh && fresh.has(c.id))).length,
  };
}

/** `src` мініатюри або `null`: лише растрові `data:image/…;base64,` і `http(s)://` (не `javascript:`, не `data:text/html`). */
export function shotSrc(c) {
  const s = c && c.meta && (c.meta.shot || c.meta.shotUrl);
  return typeof s === "string" && SHOT_RE.test(s) ? s : null;
}
