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
  const all = [target, ...target.getElementsByTagName('*')];
  for (const el of all) {
    if (blankDesc.has(el)) continue;   // посилання з відсічених вузлів нікому не потрібні
    for (const id of refIds(el)) {
      const ref = doc.getElementById(id);
      if (ref && !seen.has(ref)) {
        seen.add(ref); anchors.push(ref);
        if (blankDesc.size && blankDesc.has(ref)) {   // але на вузол усередині порожнього кореня вказує живий — лишаємо його, нащадків і предків до кореня
          blankDesc.delete(ref);
          for (const d of ref.getElementsByTagName('*')) blankDesc.delete(d);
          for (let p = ref.parentElement; p && blankDesc.has(p); p = p.parentElement) blankDesc.delete(p);
        }
      }
    }
  }
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
