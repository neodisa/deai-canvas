/**
 * Область знімка для html2canvas. Бібліотека клонує ВЕСЬ документ незалежно від цілі
 * і синхронно копіює стилі кожного SVG-вузла та псевдоелемента — на важких сторінках
 * це секунди заморозки. `ignoreElements` лишає лише ланцюжок предків цілі, її
 * піддерево, <head>/стилі та елементи поза ціллю, на які посилається піддерево.
 *
 * Відомe прийняте обмеження: селектори, що залежать від сусідів (`:nth-child`, `+`, `~`), можуть
 * стилізувати ціль у мініатюрі інакше, ніж у живому макеті.
 */
const SVG_NS = 'http://www.w3.org/2000/svg';
const URL_ATTRS = ['fill', 'stroke', 'mask', 'clip-path', 'filter', 'marker-start', 'marker-mid', 'marker-end'];
const URL_RE = /url\(\s*['"]?#([^'")\s]+)['"]?\s*\)/g;

function refIds(el) {
  const ids = [];
  // `href="#…"` — посилання лише в SVG (use/image/textPath); звичайне <a href="#main"> якорем не є.
  for (const name of el.namespaceURI === SVG_NS ? ['href', 'xlink:href'] : []) {
    const v = el.getAttribute && el.getAttribute(name);
    if (v && v.charAt(0) === '#' && v.length > 1) ids.push(v.slice(1));
  }
  for (const name of URL_ATTRS) {
    const v = el.getAttribute && el.getAttribute(name);
    if (!v) continue;
    URL_RE.lastIndex = 0;
    let m;
    while ((m = URL_RE.exec(v))) ids.push(m[1]);
  }
  return ids;
}

export function shotScope(target, blankRoots) {
  const doc = target.ownerDocument;
  // «Порожні» корені SVG (обрізка понад бюджет): їхні нащадки в знімок не йдуть, сам корінь клонується й тримає бокс.
  const blankDesc = new Set();
  if (blankRoots) for (const b of blankRoots) for (const d of b.getElementsByTagName('*')) blankDesc.add(d);
  const anchors = [target];
  const seen = new Set([target]);
  const queue = [];
  const scan = (el) => {
    for (const id of refIds(el)) {
      const ref = doc.getElementById(id);
      if (!ref || seen.has(ref)) continue;
      seen.add(ref); anchors.push(ref);
      if (blankDesc.has(ref)) {   // на вузол усередині порожнього кореня вказує живий — лишаємо його, нащадків і предків до кореня
        const keep = [ref, ...ref.getElementsByTagName('*')];
        for (let p = ref.parentElement; p && blankDesc.has(p); p = p.parentElement) keep.push(p);
        for (const k of keep) { blankDesc.delete(k); queue.push(k); }   // їхні власні посилання теж треба зібрати (транзитивно)
      }
    }
  };
  for (const el of [target, ...target.getElementsByTagName('*')]) if (!blankDesc.has(el)) scan(el);   // посилання з відсічених вузлів нікому не потрібні
  while (queue.length) scan(queue.pop());
  return function ignoreElements(node) {
    if (blankDesc.size && blankDesc.has(node)) return true;
    if (node.closest && node.closest('head')) return false;
    const tag = node.tagName;
    if (tag === 'STYLE' || tag === 'LINK') return false;
    for (const a of anchors) {
      if (node === a || node.contains(a) || a.contains(node)) return false;
    }
    return true;
  };
}
