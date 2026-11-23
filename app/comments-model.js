/**
 * Модель панелі коментарів оболонки (Deai 0.26.0, етап Б1). Чиста: ні DOM, ні мережі. Вхід — знімок коментатора
 * (`CommentLayer.snapshot()`: копії коментарів із `n`, `scope`, `where`, `iter`). Що «поточне», вирішує КОМЕНТАТОР
 * (`scope`), а не ця модель — друга реалізація того самого знання розійшлась би мовчки (принцип 6 `PRODUCT.md`).
 */
const SHOT_RE = /^(data:image\/(png|jpe?g|webp|gif);base64,|https?:\/\/)/i;

const list = (snapshot) => (snapshot && Array.isArray(snapshot.comments) ? snapshot.comments : []);
const byNewest = (a, b) => (Number(b.n) || 0) - (Number(a.n) || 0);
const closedAt = (c) => Number((c.meta && c.meta.resolvedAt) || c.resolvedAt || 0) || 0;

/** `ДД.ММ.РРРР ГГ:ХХ` → `РРРРММДДГГХХ` (те саме правило, що `tsKey` локального адаптера і `stampKey` коментатора); не за форматом — порожньо. */
const stampKey = (ts) => {
  const m = /^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2})$/.exec(String(ts || ""));
  return m ? m[3] + m[2] + m[1] + m[4] + m[5] : "";
};

/** Відповіді коментаря за `ts` (0.35). Стабільно: рівні хвилини лишають порядок сховища; хоч один `ts` не розібрався — порядок
 *  сховища (як `mergeReplies` у коментаторі). Не обʼєкти відкидаються. */
export function repliesOf(c) {
  const rs = c && Array.isArray(c.replies) ? c.replies.filter((r) => r && typeof r === "object") : [];
  if (!rs.every((r) => stampKey(r.ts))) return rs;
  return rs.map((r, i) => [r, i]).sort((a, b) => stampKey(a[0].ts).localeCompare(stampKey(b[0].ts)) || a[1] - b[1]).map((x) => x[0]);
}

/** Пошук як у панелі коментатора: `#N` — точний номер; інакше підрядок без регістру в «#n текст автор час цитата» і в тексті й авторах відповідей. */
export function matchQuery(c, query) {
  const q = String(query || "").trim().toLowerCase();
  if (!q) return true;
  const num = /^#(\d+)$/.exec(q);
  if (num) return Number(c.n) === Number(num[1]);
  const sel = (c.meta && c.meta.sel) || "";
  const rep = repliesOf(c).map((r) => `${r.text || ""} ${r.author || ""}`).join(" ");
  return `#${c.n} ${c.text || ""} ${c.author || ""} ${c.ts || ""} ${sel} ${rep}`.toLowerCase().includes(q);
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

/** «Свіжий» (Нове): відкритий І (командний з id у `fresh` АБО з відповіддю в `fresh` — будь-якого адресата: локальний коментар
 *  з новою відповіддю AI теж нове). */
const isFreshIn = (fresh, c) => !!fresh && c.status === "open"
  && ((fresh.has(c.id) && audOf(c) === "project") || repliesOf(c).some((r) => fresh.has(r.id)));

/** `{fresh, open, earlier, closed}`: «Нове» (набір `fresh`, лише відкриті), відкриті поточні (без нових),
 *  відкриті попередніх ітерацій, закриті поточні. */
export function commentSections(snapshot, { query = "", filter = "all", fresh = null } = {}) {
  const hit = (c) => matchQuery(c, query) && passFilter(c, filter);
  // Сам коментар свіжий лише командний (захист: локальний id у `fresh` сюди не потрапляє); нова відповідь — будь-якого адресата.
  const isFresh = (c) => isFreshIn(fresh, c);
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
 *  а не про запит) і `fresh: {local, project}` — свіжі відкриті (той самий відбір, що розділ «Нове») за фільтром кожної вкладки. */
export function filterCounts(snapshot, fresh = null) {
  const all = list(snapshot);
  const cur = all.filter((c) => c.status === "open" && c.scope === "current");
  return {
    local: cur.filter(forClaude).length,
    project: cur.filter((c) => audOf(c) === "project").length,
    all: cur.length,
    fresh: {
      local: all.filter((c) => isFreshIn(fresh, c) && passFilter(c, "local")).length,
      project: all.filter((c) => isFreshIn(fresh, c) && passFilter(c, "project")).length,
    },
  };
}

/** `src` мініатюри або `null`: лише растрові `data:image/…;base64,` і `http(s)://` (не `javascript:`, не `data:text/html`). */
export function shotSrc(c) {
  const s = c && c.meta && (c.meta.shot || c.meta.shotUrl);
  return typeof s === "string" && SHOT_RE.test(s) ? s : null;
}
