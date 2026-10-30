/**
 * «В Figma» (T-41): живий макет із рамки → буфер обміну → вставка у Figma.
 *
 * Працює НЕ наш конвертер, а офіційний `capture.js` Figma (html-to-design) —
 * той самий, що вантажить букмарклет власника. Букмарклет ставить сторінці
 * `#figmacapture&figmadelay=1000`, і скрипт на старті кличе рівно
 * `window.figma.captureForDesign` (гілка `startClipboardFlow`). Ми кличемо ту
 * саму функцію напряму, бо лише так дістаємо ВІДПОВІДЬ: при невдачі вона
 * повертає `{success:false, error}`, а hash-тригер цю відповідь викидає. Тост
 * скрипта про помилку живе всередині рамки й на вузькій ширині обрізаний —
 * виміряно на пілоті, покладатися на нього не можна.
 *
 * Факти, на яких модуль стоїть (усі виміряні пілотом 28.09.2026 у справжньому
 * Google Chrome, канвас `fop-check`):
 *
 * 1. ⛔ ФОКУС. Скрипт перед записом у буфер чекає фокуса СВОГО документа, а
 *    клік у смузі лишає фокус у батьківському. Без `win.focus()` захоплення
 *    висить на «Захоплення сторінки…» вічно — без помилки, без таймауту.
 * 2. ⛔ АКТИВАЦІЯ ЖИВЕ ~5 с. Клік у смузі активує і same-origin рамку (це
 *    спрацювало, побоювання з нотатки не підтвердилось), але запис у буфер
 *    мусить встигнути: затримка 1000 мс проходить, 6000 мс — «Write permission
 *    denied». Тому скрипт підвантажується заздалегідь (`loadCapture` на
 *    наведенні), а затримка не більша за букмарклетну.
 * 3. ⛔ `data-h2d-ignore` ДІЄ ЛИШЕ ЗІ ЗНАЧЕННЯМ "true" (у скрипті —
 *    `getAttribute(...) === "true"`). Порожнє значення ігнорується мовчки, і
 *    вкладка «Comment» разом із панеллю коментатора їдуть у Figma з реальними
 *    координатами. Без помітки витік — ЗА ЗАМОВЧУВАННЯМ: скрипт розгортає
 *    Shadow DOM наших хостів у звичайні вузли.
 * 4. У вбудованому браузері Claude буфер заборонений самим браузером
 *    (`clipboard-write: denied` навіть для `writeText` верхнього документа) —
 *    там кнопка чесно каже про відмову, працює вона в Chrome.
 *
 * Модуль не знає ні смуги, ні словника: повертає КЛЮЧ причини, текст складає
 * `app.js`. DOM — лише той, що переданий аргументом (вікно рамки), тому все
 * тут перевіряється юнітами на підробках (`tests/figma-capture.test.mjs`).
 */

export const CAPTURE_SRC = 'https://mcp.figma.com/mcp/html-to-design/capture.js';

/** Як у букмарклеті власника (`figmadelay=1000`): час reveal-анімаціям
 *  добігти. Більше не можна — див. факт 2 у шапці. */
export const CAPTURE_DELAY_MS = 1000;

/** Стеля чекання на сам скрипт. Мовчазний CDN не сміє тримати кнопку в
 *  «Копіюю…» вічно. */
export const LOAD_TIMEOUT_MS = 8000;

/**
 * Усе, що канвас сам кладе в документ макета і що НЕ є макетом. Перелік
 * стереже парний тест: хост, який зʼявився в джерелі, але не тут, — червоне.
 *   - `[data-canvas-inspector]` — хост оверлея інспектора (`vendor/inspector.js`);
 *   - `[data-comment-layer]` — хост коментатора (бандл comment-layer; сам бандл
 *     ми не правимо — окремий проєкт, тому помітка ставиться тут, ззовні);
 *   - `#cl-down` — банер «коментарі недоступні» (`_COMMENT_DOWN_BANNER`, `serve.py`);
 *   - `#__figma_capture_toolbar_host__` — тулбар самого скрипта: після першого
 *     захоплення він лишається в документі й на другому потрапив би в payload
 *     порожнім кадром.
 */
export const OVERLAY_SELECTORS = [
  '[data-canvas-inspector]',
  '[data-comment-layer]',
  '#cl-down',
  '#__figma_capture_toolbar_host__',
];

/** Помітити наші оверлеї, щоб скрипт їх пропустив. Повертає кількість. */
export function markOverlays(doc) {
  let n = 0;
  for (const el of doc.querySelectorAll(OVERLAY_SELECTORS.join(','))) {
    el.setAttribute('data-h2d-ignore', 'true');   // саме "true" — факт 3
    n += 1;
  }
  return n;
}

/** Ключ причини невдачі. Відмову буфера виділено окремо, бо в неї є що
 *  порадити (Chrome замість вбудованого браузера, другий клік швидший). */
export function captureErrorKey(error) {
  return /permission|notallowed|not focused|denied/i.test(String(error ?? ''))
    ? 'figmaErrClipboard'
    : 'figmaErrFailed';
}

const ready = (win) => typeof win.figma?.captureForDesign === 'function';

/**
 * Підвантажити `capture.js` у документ рамки. Без hash `#figmacapture` скрипт
 * лише реєструє `window.figma` і нічого не захоплює — тому викликати це можна
 * заздалегідь. Тег один на документ: друге звернення чекає на той самий.
 * Невдала спроба прибирає свій тег, щоб наступна вставила свіжий, а не чекала
 * на мертвий.
 */
export function loadCapture(win, { src = CAPTURE_SRC, timeoutMs = LOAD_TIMEOUT_MS } = {}) {
  if (ready(win)) return Promise.resolve(win.figma);
  const doc = win.document;
  let s = doc.querySelector('script[data-dc-figma]');
  if (!s) {
    s = doc.createElement('script');
    s.src = src;
    s.dataset.dcFigma = '';
    (doc.head || doc.documentElement).appendChild(s);
  }
  const tag = s;
  return new Promise((resolve, reject) => {
    let done = false;
    const fail = (why) => {
      if (done) return;
      done = true; clearTimeout(timer); tag.remove(); reject(new Error(why));
    };
    const timer = setTimeout(() => fail('timeout'), timeoutMs);
    tag.addEventListener('load', () => {
      if (!ready(win)) { fail('no-api'); return; }
      if (done) return;
      done = true; clearTimeout(timer); resolve(win.figma);
    }, { once: true });
    tag.addEventListener('error', () => fail('load'), { once: true });
  });
}

/**
 * Захопити документ рамки в буфер. Повертає `{ok:true}` або
 * `{ok:false, key, detail}`.
 *
 * ⛔ Кличеться СИНХРОННО з обробника кліку: `win.focus()` — перший рядок, до
 * будь-якого `await`, інакше факти 1–2 з шапки.
 *
 * Успіх `captureForDesign` скрипт підтверджує ВЛАСНИМ тостом, а його проміс
 * при успіху розвʼязується лише тоді, коли людина закриє тулбар скрипта.
 * Тому викликач не чекає на цей результат, щоб зняти «Копіюю…»: він ловить
 * невдачу, коли б вона не прийшла.
 */
export async function captureToFigma(win, opts = {}) {
  /* ⛔ Ця обгортка НІКОЛИ не відхиляється (ревʼю T-41). Вікно рамки взяте в мить
     кліку й може «протухнути» за час захоплення — перемкнули сторінку, у рамці
     новий документ. Необроблене відхилення тут означало б, що `tell()` не
     спрацює: тиха невдача, рівно те, проти чого кнопка й проєктувалась.
     Виклик `attempt` СИНХРОННИЙ до його першого `await`, тож `win.focus()`
     лишається в жесті кліку. */
  try {
    return await attempt(win, opts);
  } catch (e) {
    return { ok: false, key: 'figmaErrFailed', detail: String(e?.message ?? e) };
  }
}

async function attempt(win, { delayMs = CAPTURE_DELAY_MS, load = loadCapture } = {}) {
  win.focus();
  markOverlays(win.document);
  let api;
  try {
    api = await load(win);
  } catch (e) {
    return { ok: false, key: 'figmaErrLoad', detail: String(e?.message ?? e) };
  }
  // Тулбар скрипта зʼявляється разом зі скриптом — помічаємо вдруге.
  markOverlays(win.document);
  let res;
  try {
    res = await api.captureForDesign({ selector: 'body', delayMs });
  } catch (e) {
    const detail = String(e?.message ?? e);
    return { ok: false, key: captureErrorKey(detail), detail };
  }
  if (res && res.success === false) {
    const detail = String(res.error ?? '');
    return { ok: false, key: captureErrorKey(detail), detail };
  }
  return { ok: true };
}
