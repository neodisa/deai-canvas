/**
 * Куди веде коментар (0.39.1): ітерація й сторінка, де він живе, — для «Показати» в панелі, коли пін не в цьому документі.
 * Чисте: без DOM і оболонки. Тег версії пише `page_version_tag` (`pages_model.py`): `"<n>"` — неявна сторінка `main`,
 * `"<n>/<сторінка>"` — явна. Пін без тегу (legacy) несе маршрут вигляду `/it27/<сторінка>/index.html`.
 * Нерозбірливе (`/commented`, порожнє) — `null`: оболонка тоді каже про це тостом, а не мовчить.
 */
export const MAIN_PAGE = "main";

const fromVersion = (v) => {
  const m = /^(?:it)?(\d+)(?:\/(.+))?$/.exec(String(v).trim());
  return m ? { it: `it${m[1]}`, page: m[2] || MAIN_PAGE } : null;
};

const fromRoute = (r) => {
  const path = String(r).split(/[?#]/)[0];
  const m = /^\/it(\d+)\/(?:(.+)\/)?index\.html$/.exec(path);
  return m ? { it: `it${m[1]}`, page: m[2] || MAIN_PAGE } : null;
};

/** `{ it, page }` або `null`. */
export function commentTarget(c) {
  const meta = c && typeof c === "object" && c.meta && typeof c.meta === "object" ? c.meta : null;
  if (!meta) return null;
  if (meta.version != null && meta.version !== "") {
    const t = fromVersion(meta.version);
    if (t) return t;
  }
  return typeof meta.route === "string" && meta.route ? fromRoute(meta.route) : null;
}
