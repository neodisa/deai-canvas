/*!
 * anchor — алгоритм якоря comment-layer: відбиток елемента і пошук його знову.
 * Окремим модулем з T-45: той самий алгоритм потрібен трьом місцям — віджету в
 * сторінці, затвору канваса (геометрія кадру) і оболонці «Огляду». Друга копія
 * розійшлась би з першою саме там, де цього не видно: пін на «Огляді» стояв би
 * не на тому елементі, що в живому виді.
 */
/* ===========================================================================
 * 1. Anchor algorithm  (validated in the spike — Node + real browser DOM)
 *    fingerprint(el) captured at comment time; classify(fp) decides after a
 *    regeneration whether the region was rewritten (RESOLVE) or is unchanged.
 *    Bias: only resolve when confident it changed (a false resolve silently
 *    drops live feedback — the costly error).
 * ========================================================================= */
export function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0).toString(36);
}
export function isHashy(t) {
  if (/^(css-|sc-|jsx-|emotion-|_)/i.test(t)) return true;
  if (/^[a-z]{1,3}[0-9a-f]{5,}$/i.test(t)) return true;
  if (/^[0-9a-f]{6,}$/i.test(t)) return true;
  if (t.length >= 6 && !/[aeiou]/i.test(t)) return true;
  // mixed-case with no '-' => CSS-in-JS generated class (styled-components,
  // emotion). Utility/BEM classes are lower-case-with-dashes, so unaffected.
  if (/[a-z]/.test(t) && /[A-Z]/.test(t) && !t.includes('-') && t.length <= 12) return true;
  return false;
}
export const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
export const stableClasses = (el) => [...el.classList].filter((t) => !isHashy(t)).sort();

export function structSig(el) {
  let s = '';
  (function walk(x, d) { for (const c of x.children) { s += c.tagName.toLowerCase() + '(' + d + ')'; walk(c, d + 1); } })(el, 1);
  return hash(s);
}
export function styleSig(el) {
  let s = stableClasses(el).join('.');
  (function walk(x) { for (const c of x.children) { s += '|' + stableClasses(c).join('.'); walk(c); } })(el);
  return hash(s);
}
export function stableId(el) {
  if (el.getAttribute('data-comment-id')) return 'cid:' + el.getAttribute('data-comment-id');
  if (el.getAttribute('data-testid')) return 'testid:' + el.getAttribute('data-testid');
  if (el.id && !isHashy(el.id)) return 'id:' + el.id;
  if (el.getAttribute('aria-label')) return 'aria:' + norm(el.getAttribute('aria-label'));
  return null;
}
export function tagPath(el, root) {
  const path = []; let n = el;
  while (n && n !== root && n.parentElement) {
    const sibs = [...n.parentElement.children].filter((c) => c.tagName === n.tagName);
    path.unshift(n.tagName.toLowerCase() + '[' + sibs.indexOf(n) + ']');
    n = n.parentElement;
  }
  return path;
}
export function fingerprint(el, root) {
  const text = norm(el.textContent);
  return {
    tag: el.tagName.toLowerCase(), stableId: stableId(el), text, textHash: hash(text),
    structHash: structSig(el), styleHash: styleSig(el), path: tagPath(el, root),
  };
}
export function pathSim(a, b) {
  const ra = [...a].reverse(), rb = [...b].reverse(); let m = 0;
  for (let i = 0; i < Math.min(ra.length, rb.length); i++) { if (ra[i] === rb[i]) m++; else break; }
  return m / Math.max(ra.length, rb.length, 1);
}
export function textSim(a, b) {
  const wa = new Set(a.split(' ').filter(Boolean)), wb = new Set(b.split(' ').filter(Boolean));
  if (!wa.size && !wb.size) return 1;
  let i = 0; for (const w of wa) if (wb.has(w)) i++;
  return i / (wa.size + wb.size - i || 1);
}
export const MATCH_THRESHOLD = 0.35;
export function findMatch(fp, root) {
  fp = fp || {};
  const fpText = fp.text || '', fpPath = fp.path || []; // tolerate partial/foreign fingerprints
  const cs = [...root.querySelectorAll('*')];
  if (fp.stableId) {
    const byId = cs.filter((c) => stableId(c) === fp.stableId);
    if (byId.length === 1) return { el: byId[0], score: 1 };
    if (byId.length > 1) {
      let b = null, bs = -1;
      for (const c of byId) { const s = textSim(fpText, norm(c.textContent)); if (s > bs) { bs = s; b = c; } }
      return { el: b, score: 0.9 };
    }
  }
  let best = null, bestScore = -1;
  for (const c of cs) {
    if (c.tagName.toLowerCase() !== fp.tag) continue;
    const score = 0.25 * pathSim(fpPath, tagPath(c, root)) + 0.75 * textSim(fpText, norm(c.textContent));
    if (score > bestScore) { bestScore = score; best = c; }
  }
  return { el: best, score: bestScore };
}
export function classify(fp, root) {
  const m = findMatch(fp, root);
  if (!m.el || m.score < MATCH_THRESHOLD) return { decision: 'RESOLVE', reason: 'region removed / replaced', el: null };
  const nx = fingerprint(m.el, root);
  const tch = nx.textHash !== fp.textHash, sch = nx.structHash !== fp.structHash, ych = nx.styleHash !== fp.styleHash;
  if (tch || sch || ych) {
    const r = []; if (tch) r.push('text'); if (sch) r.push('structure'); if (ych) r.push('style');
    return { decision: 'RESOLVE', reason: 'regenerated (' + r.join('+') + ')', el: m.el };
  }
  return { decision: 'CARRY_FORWARD', reason: 'unchanged region', el: m.el };
}

/* ===========================================================================
 * 1b. Геометрія кадру (T-45: піни на «Огляді» канваса).
 *     Той самий відбиток, що в піна, плюс прямокутник у координатах ДОКУМЕНТА.
 *     Знімає затвор канваса — у тій розкладці, що дала пікселі кадру.
 * ========================================================================= */

/* Текст ріжемо: контейнер несе текст УСІХ нащадків, і без стелі файл геометрії
   ріс би як «текст сторінки × глибина». Стеля одна на обидва боки порівняння —
   див. `findMatchIn`. */
export const GEO_TEXT_CAP = 2000;
const capText = (s) => (s || '').slice(0, GEO_TEXT_CAP);

export function geometry(root, { cap = 8000 } = {}) {
  const sx = window.scrollX, sy = window.scrollY;
  const els = [];
  let truncated = false;
  for (const el of root.querySelectorAll('*')) {
    if (els.length >= cap) { truncated = true; break; }
    const r = el.getBoundingClientRect();
    const text = norm(el.textContent);
    /* Нульові НЕ викидаємо: `findMatch` бачить і невидимі елементи, і коли
       найкращий збіг піна невидимий, живий вид пін НЕ ставить (`_placePins`
       пропускає 0×0). Викинь їх тут — `findMatchIn` узяв би наступного, і пін
       на «Огляді» став би там, де в живому виді його немає. */
    const e = {
      tag: el.tagName.toLowerCase(), stableId: stableId(el), path: tagPath(el, root),
      text: capText(text), textHash: hash(text), structHash: structSig(el), styleHash: styleSig(el),
      x: Math.round(r.left + sx), y: Math.round(r.top + sy),
      w: Math.round(r.width), h: Math.round(r.height),
    };
    /* Для НАВЕДЕННЯ на «Огляді» (етап 2 T-45): у живому виді ціль кліку дає
       браузер (`elementFromPoint`), а він не бере невидимих і прозорих для миші
       елементів. Ставимо прапорці лише коли вони є — файл не росте на кожному. */
    if (r.width > 0 || r.height > 0) {
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden') e.hid = 1;
      if (cs.pointerEvents === 'none') e.pe = 0;
    }
    els.push(e);
  }
  return { els, truncated };
}

/* `findMatch`, але по записах геометрії, а не по DOM. Логіка МУСИТЬ лишатись
   тією самою рядок у рядок — розійдуться, і пін на «Огляді» стоятиме не там, де
   в живому виді. Одна чесна відмінність: `findMatch` порівнює ПОВНИЙ текст, тут
   — зрізаний до `GEO_TEXT_CAP` з обох боків. Для коротших елементів результат
   той самий; чи змінює це вибір на довших, міряє живий паритетний тест канваса. */
export function findMatchIn(fp, entries) {
  fp = fp || {};
  const fpText = capText(fp.text), fpPath = fp.path || [];
  const es = entries || [];
  if (fp.stableId) {
    const byId = [];
    for (let i = 0; i < es.length; i++) if (es[i].stableId === fp.stableId) byId.push(i);
    if (byId.length === 1) return { i: byId[0], score: 1 };
    if (byId.length > 1) {
      let b = -1, bs = -1;
      for (const i of byId) { const s = textSim(fpText, es[i].text || ''); if (s > bs) { bs = s; b = i; } }
      return { i: b, score: 0.9 };
    }
  }
  let best = -1, bestScore = -1;
  for (let i = 0; i < es.length; i++) {
    const e = es[i];
    if (e.tag !== fp.tag) continue;
    const score = 0.25 * pathSim(fpPath, e.path || []) + 0.75 * textSim(fpText, e.text || '');
    if (score > bestScore) { bestScore = score; best = i; }
  }
  return { i: best, score: bestScore };
}
