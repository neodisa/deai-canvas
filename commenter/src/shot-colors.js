/**
 * Знімок і сучасні кольори (0.35.1). html2canvas 1.4.1 розбирає лише rgb/rgba/hsl/hsla, а браузер віддає обчислений
 * колір у тому просторі, у якому його задано (`color-mix(in srgb, …)` → `color(srgb …)`, `oklab(…)`, `oklch(…)`).
 * Один такий колір у цілі чи у фоні html/body — і рендер кидає. Тому в КЛОНІ (не на живій сторінці) такі значення
 * переписуються в `rgba()`, а CSS-переходи вимкнено: у клоні таблиці стилів довантажуються, `transition` стартує від
 * стилів за замовчуванням, колір посеред переходу знову `oklab(…)`, а перехід у каскаді сильніший за inline `!important`.
 * Сам запис переписаного кольору теж запускає перехід (колір той самий, а запис інший) — тож на кожен вузол із записом
 * іде ще й inline `transition-property: none !important` (правило зі стилю з `*` програє `#id`/`.class {…!important}`).
 * Також: ціль-SVG → найближчий HTML-предок (html2canvas запам'ятовує клон цілі лише для HTML-елементів).
 */
const SVG_NS = 'http://www.w3.org/2000/svg';

// Функція з одним рівнем вкладених дужок (color-mix усередині з color()); `\b` не дає `lab(` збігтись усередині `oklab(`.
const COLOR_FN = /\b(?:color-mix|color|oklab|oklch|lab|lch)\((?:[^()]|\([^()]*\))*\)/g;
const COLOR_FN_TEST = /\b(?:color-mix|color|oklab|oklch|lab|lch)\(/;

export const SHOT_COLOR_PROPS = ['color', 'background-color', 'background-image', 'border-top-color', 'border-right-color',
  'border-bottom-color', 'border-left-color', 'outline-color', 'text-decoration-color', 'box-shadow', 'text-shadow',
  '-webkit-text-stroke-color', '-webkit-text-fill-color', 'caret-color', 'column-rule-color'];

/** Кожну колірну функцію в значенні міняє на `toRgba(збіг)`; `null` від конвертера лишає цей збіг як є. */
export function rewriteColors(value, toRgba) {
  if (typeof value !== 'string' || !COLOR_FN_TEST.test(value)) return value;
  return value.replace(COLOR_FN, (m) => {
    const out = toRgba(m);
    return out == null ? m : out;
  });
}

/** Ціль-SVG (іконка, path) → найближчий предок не з SVG-простору імен; без такого лишається як є. */
export function liftSvgTarget(el) {
  let t = el;
  while (t && t.namespaceURI === SVG_NS && t.parentElement) t = t.parentElement;
  return t && t.namespaceURI === SVG_NS ? el : t;
}

/**
 * Конвертер «колір → rgba(r, g, b, a)» силами самого браузера: колір малюється в canvas 1×1 і читається піксель.
 * Непрочитний браузером колір (невідома функція) → `null`; результат кешується на значення.
 */
export function canvasColorConverter(doc) {
  let ctx = null;
  const cache = new Map();
  return function toRgba(value) {
    if (cache.has(value)) return cache.get(value);
    let out = null;
    try {
      if (!ctx) {
        const c = doc.createElement('canvas');
        c.width = c.height = 1;
        ctx = c.getContext('2d', { willReadFrequently: true });
      }
      const SENTINEL = '#010203';
      ctx.fillStyle = SENTINEL;
      ctx.fillStyle = value;
      if (ctx.fillStyle !== SENTINEL) {   // змінилось — значення розібрано
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillRect(0, 0, 1, 1);
        const d = ctx.getImageData(0, 0, 1, 1).data;
        out = `rgba(${d[0]}, ${d[1]}, ${d[2]}, ${+(d[3] / 255).toFixed(3)})`;
      }
    } catch (e) { out = null; }
    cache.set(value, out);
    return out;
  };
}

/**
 * Для `onclone` html2canvas. Спершу вимикає переходи в клоні (лише їх: `animation: none` сховав би елементи з
 * `fill-mode: forwards`), потім переписує колірні функції html, body, цілі й усіх її нащадків (вузли-замінники
 * псевдоелементів у клоні — звичайні елементи). Усі читання обчислених стилів — ДО будь-якого запису, щоб не
 * провокувати перерахунок стилів на кожен запис. Повертає кількість записів.
 */
export function normalizeClone(cloneDoc, cloneEl, toRgba) {
  const style = cloneDoc.createElement('style');
  style.textContent = '*,*::before,*::after{transition:none!important}';
  (cloneDoc.head || cloneDoc.documentElement).appendChild(style);
  const win = cloneDoc.defaultView;
  const nodes = [cloneDoc.documentElement, cloneDoc.body];
  if (cloneEl) { nodes.push(cloneEl); for (const d of cloneEl.getElementsByTagName('*')) nodes.push(d); }
  const writes = [];
  for (const n of nodes) {
    if (!n || !n.style) continue;
    const cs = win.getComputedStyle(n);
    for (const p of SHOT_COLOR_PROPS) {
      const v = cs.getPropertyValue(p);
      if (!v || !COLOR_FN_TEST.test(v)) continue;
      const nv = rewriteColors(v, toRgba);
      if (nv !== v) writes.push([n, p, nv]);
    }
  }
  const killed = new Set();
  for (const [n, p, v] of writes) {
    if (!killed.has(n)) { killed.add(n); n.style.setProperty('transition-property', 'none', 'important'); }
    n.style.setProperty(p, v, 'important');
  }
  return writes.length;
}
