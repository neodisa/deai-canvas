/**
 * Пошук по тексту макета (0.40): чиста частина. DOM (обхід вузлів, діапазони, підсвітка) — `find-bar.js`.
 * `findInTexts(texts, query)` → збіги в ОРИГІНАЛЬНОМУ тексті вузла, без урахування регістру (`toLocaleLowerCase('uk')`).
 * Нижній регістр може змінити довжину (`İ` → `i̇`), тож шукаємо в «згорнутому» рядку й вертаємо зсуви назад через карту.
 */
import { OVERLAY_SELECTORS } from "./figma-capture.js";

export const FIND_LIMIT = 1000;
/** Вузли всередині цих тегів тексту макета не належать. */
export const SKIP_TAGS = new Set(["script", "style", "noscript", "template"]);
/** Наші оверлеї в документі рамки (хост коментатора, позначки помічника, інспектор і тюнер, банер) — той самий перелік, що в «В Figma». */
export const SKIP_SELECTORS = [...OVERLAY_SELECTORS];

function fold(s) {
  let out = "";
  const start = [];   // для кожного коду UTF-16 згорнутого рядка — початок кодової точки в оригіналі
  const end = [];     // …і її кінець
  for (let o = 0; o < s.length;) {
    const ch = String.fromCodePoint(s.codePointAt(o));
    const f = ch.toLocaleLowerCase("uk");
    for (let k = 0; k < f.length; k += 1) { start.push(o); end.push(o + ch.length); }
    out += f;
    o += ch.length;
  }
  return { out, start, end };
}

export function findInTexts(texts, query, limit = FIND_LIMIT) {
  const q = fold(String(query ?? "")).out;
  const hits = [];
  if (!q) return { hits, total: 0, capped: false };
  for (let i = 0; i < texts.length && hits.length < limit; i += 1) {
    const text = texts[i];
    if (!text) continue;
    const f = fold(text);
    for (let at = f.out.indexOf(q); at !== -1 && hits.length < limit; at = f.out.indexOf(q, at + q.length)) {
      hits.push({ i, start: f.start[at], end: f.end[at + q.length - 1] });
    }
  }
  return { hits, total: hits.length, capped: hits.length >= limit };
}
