/**
 * Герметичність живих тестів простору ЛІГА після 4b-2: командні коментарі ЛІГИ йдуть через вбудований модуль
 * `supabase-comments` (його `supabase.min.js` і `adapter.js` сторінка бере з `/api/module-client/…`, без CDN), а адреса й
 * ключ Supabase — з конфігу установки (`startServer(…, { supabase: true })` пише їх у корінь `tasks.json`).
 *
 * Файл НЕ `*.test.mjs` навмисно (див. `fixture.mjs`): `npm run test:live` бере лише `*.test.mjs`.
 *
 * Що робить `hermeticLiga(page|context)`:
 *   · усе поза машиною — `abort` і запис у `outside` (тест стверджує, що там порожньо: справжня мережа недопустима);
 *   · `abcdefghijkl.supabase.co`: REST/Storage — порожня відповідь з CORS (запити з `http://127.0.0.1` — крос-доменні, тож
 *     без `Access-Control-Allow-*` браузер відкинув би відповідь ще до адаптера), realtime-websocket — закритий одразу
 *     (адаптер лише перепідключається, а `load()` іде REST-ом); кожен запит у `supabase`/`sockets`;
 *   · `cdn.jsdelivr.net` (html2canvas шару коментатора) — порожній 200, а не `abort`: збій CDN — це банер, а тут банер лише
 *     заважав би. Лишилось у `cdn` — тест бачить, що саме підмінено.
 */
export const LIGA_SB_HOST = "abcdefghijkl.supabase.co";
export const CDN_HOST = "cdn.jsdelivr.net";
/** Адреса файла модуля, який несе фабрику `window.DeaiComments` (блокування = «адаптер не завантажився»). */
export const MODULE_ADAPTER_GLOB = "**/api/module-client/supabase-comments/adapter.js";

const CORS = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "*",
  "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
};

export const isLocalUrl = (u) => {
  const x = new URL(u);
  if (["data:", "blob:", "about:"].includes(x.protocol)) return true;
  return ["http:", "https:", "ws:", "wss:"].includes(x.protocol) && ["127.0.0.1", "localhost"].includes(x.hostname);
};

/**
 * @param {import("playwright").Page|import("playwright").BrowserContext} target
 * @param {{rows?: object[], seen?: object}} [opts] `rows` — що віддає `GET /rest/v1/…` (типово порожньо); `seen` — спільний
 *   збирач (його ж повертаємо), щоб кілька сторінок одного тесту складали запити в одне місце
 * @returns {Promise<{outside: string[], supabase: string[], sockets: string[], cdn: string[]}>}
 */
export async function hermeticLiga(target, { rows = [], seen = { outside: [], supabase: [], sockets: [], cdn: [] } } = {}) {
  /* Порядок значущий: пізніша маршрутизація має пріоритет, тож загальний `abort` ставимо ПЕРШИМ. */
  await target.route((u) => !isLocalUrl(u.href), (route) => {
    seen.outside.push(route.request().url());
    return route.abort("blockedbyclient");
  });
  await target.route(`**/${CDN_HOST}/**`, (route) => {
    seen.cdn.push(route.request().url());
    return route.fulfill({ status: 200, contentType: "application/javascript", body: "" });
  });
  await target.route(`**/${LIGA_SB_HOST}/**`, (route) => {
    const req = route.request();
    seen.supabase.push(`${req.method()} ${new URL(req.url()).pathname}`);
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: CORS });
    const isGet = req.method() === "GET";
    return route.fulfill({
      status: isGet ? 200 : 201, headers: CORS, contentType: "application/json",
      body: JSON.stringify(isGet ? rows : []),
    });
  });
  await target.routeWebSocket((u) => u.hostname === LIGA_SB_HOST, (ws) => {
    seen.sockets.push(ws.url());
    return ws.close();
  });
  return seen;
}
