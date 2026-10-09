/**
 * Service worker застосунку «Deai Canvas» (scope `/app/`).
 *
 * ⛔ ЛИШЕ МЕРЕЖА. Нічого не кешує, не прекешує й не віддає з кешу — ні код, ні
 * значки, ні офлайн-сторінку. Канвас — живий інструмент: оновлення це `git pull` +
 * перезапуск, і будь-який кеш коду показував би застарілу оболонку рівно там, де
 * дизайнер чекає свіжу. Юніт (`tests/pwa.test.mjs`) підставляє `caches`, що кидає
 * на будь-якому зверненні, а живий (`tests/live/pwa.test.mjs`) правит файл на
 * сервері й дивиться, чи дійшла нова версія.
 *
 * Робить рівно одне: навігація, що НЕ ДІЙШЛА до сервера (`fetch` відхилився —
 * сервер не запущено, мережі нема), → сторінка «Канвас не запущено» з поясненням,
 * як його підняти (`pwa-offline.js`). Відповідь сервера, ЯКА Б ВОНА НЕ БУЛА (навіть
 * 500), іде як є: офлайн-сторінка — про недосяжний сервер, не про помилку в ньому.
 *
 * Усе інше (скрипти, стилі, `/api/*`) worker не чіпає: без `respondWith` запит
 * іде браузеру нативно, як і без worker. Так він не стає посередником для
 * потоків і запитів, до яких йому нема діла.
 *
 * ЧОМУ ВЗАГАЛІ Є ОБРОБНИК `fetch`. Chrome показує пропозицію встановлення
 * (`beforeinstallprompt`) лише сторінці з worker, чий `fetch`-обробник справжній;
 * порожній він ігнорує. Меню «Встановити» працює й без нього (Chrome 112+), але
 * наш пункт ⌘K живе саме на `beforeinstallprompt`.
 *
 * `skipWaiting` + `clients.claim`: нова версія worker стає чинною одразу й бере
 * під контроль уже відкриті вікна — інакше перший запуск після встановлення
 * лишався б без worker до наступного відкриття.
 *
 * Модульний worker (`register(…, {type: "module"})`): так він статично імпортує
 * `pwa-offline.js` і словник замість копії тексту. Браузер перевіряє імпортовані
 * модулі при оновленні worker, тож правка словника доїжджає сама.
 */
import { offlineHTML } from "./pwa-offline.js";

const offlinePage = () => new Response(offlineHTML(), {
  status: 200,
  headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
});

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.mode !== "navigate" || req.method !== "GET") return;
  event.respondWith(fetch(req).catch(offlinePage));
});
