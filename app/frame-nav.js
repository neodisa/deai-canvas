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
