/**
 * Посилання всередині макета ведуть рамку на сирий файл `/it-assets/<it>/<id>/index.html`
 * без коментатора. Тут — чиста відповідь, якій сторінці дерева такий шлях відповідає
 * (id сторінки = назва теки), щоб оболонка відкрила її як клік по рядку панелі.
 */
import { flatten } from "./tree-model.js";

/** id сторінки (`'main'` для кореня ітерації) або `null`, коли шлях — не сторінка цієї ітерації. */
export function assetsPageOf(pathname, it, pages) {
  if (typeof pathname !== "string" || !it) return null;
  let segs;
  try { segs = pathname.split("/").map(decodeURIComponent); } catch { return null; }
  // ["", "it-assets", it, ...rest]
  if (segs[0] !== "" || segs[1] !== "it-assets" || segs[2] !== it) return null;
  let rest = segs.slice(3);
  if (rest.length && rest[rest.length - 1] === "index.html") rest = rest.slice(0, -1);
  else if (rest.length && rest[rest.length - 1] === "") rest = rest.slice(0, -1);
  else if (rest.length) return null;            // файл, не index.html
  if (rest.length > 1) return null;
  const id = rest.length ? rest[0] : "main";
  if (!id) return null;
  const f = flatten(pages).find((x) => x.page.id === id);
  return f && f.kind === "page" ? id : null;
}

/** Запобіжник від циклу редиректів: не більше `max` переходів за `windowMs`. Чиста — час і мітки приходять ззовні. */
export function followDecision(stamps, now, max = 3, windowMs = 3000) {
  const live = (stamps || []).filter((t) => now - t < windowMs);
  if (live.length >= max) return { follow: false, stamps: live };
  return { follow: true, stamps: [...live, now] };
}

/** Хвіст `#…` із посилання — лише для тієї самої ітерації й сторінки, що чекають у `pending`; інакше порожньо. */
export function hashFor(pending, it, page) {
  return pending && pending.it === it && pending.page === page ? (pending.hash || "") : "";
}
