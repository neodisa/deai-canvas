# План: знімки пінів — якість і пропуски (0.35.1)

Спека: `docs/superpowers/specs/2026-11-23-commenter-shots-design.md`. Рівень «середній»: план без таблиць мутацій, одне
ревʼю в кінці, повний релізний прогін. Гілка `fix/commenter-shots` від гілки «Відповідей» (0.35.0); перед релізом — злиття
`main` (не rebase).

## Спільні правила

- Робоча тека — worktree цієї гілки. Живий канвас, його checkout і чужі worktree не чіпати.
- Тести: `node --test tests/*.test.mjs`, `node --test commenter/test/*.test.mjs`, `python3 -B -m unittest`; живі — по
  одному файлу під спільним локом `/private/tmp/deai-live.lock`, з тимчасовим `HOME`.
- Після правки `commenter/src` — `cd commenter && npm run build`, потім `tests/commenter-stamp.test.mjs`.
- Без нових опцій хоста тіньовий DOM коментатора побайтно той самий (`tests/live/commenter-golden.test.mjs`).
- Коди `meta.shotMiss` — контракт (`app/comments-view.js`, `bin/inbox.py`, `app/serve.py`, `cmtShotMiss_*` в i18n): нових
  кодів цей план не додає.
- Коміти — від імені `neodisa`, лише перелічені шляхи.

## Task 1 — баг 2: знімок на будь-якій сторінці

Файли: `commenter/src/shot-colors.js` (новий), `commenter/src/shot-scope.js`, `commenter/src/comment-layer.js`,
`commenter/test/shot-colors.test.mjs` (новий), `tests/live/commenter-shot-real.test.mjs` (новий),
`tests/fixtures/vendor/html2canvas-1.4.1.min.js` (копія бібліотеки для тестів, MIT, із заголовком ліцензії), бандл і штамп.

1. Червоний живий тест на справжньому `html2canvas`: сторінка з `color-mix(in srgb|oklab, …)`/`oklch()` у фоні `body`,
   тіні, градієнті й рамці; SVG-іконка в кнопці; кнопка з `transition` і стилем, що приходить зовнішньою таблицею. На
   поточному коді — `shotMiss: render`.
2. Чисті функції (юніт): переписування колірних функцій у рядку значення (кілька кольорів, вкладений `color-mix`, `lab(` не
   плутати з `oklab(`); вибір HTML-цілі для SVG.
3. `onclone`: вимкнути переходи в клоні, потім нормалізувати кольори (усі читання → усі записи). SVG-ціль → HTML-предок до
   перевірок ліміту й `shotScope`.
4. Збірка, штамп, юніти коментатора, живі `commenter-shot`, `commenter-heavy`, `commenter-golden`, новий файл.

## Task 2 — баг 1: два розміри знімка

Файли: `commenter/src/comment-layer.js`, `app/vendor/local-adapter.js`, `app/vendor/dual-store.js`, `app/serve.py`
(`/api/local-shots`, `TASK_IGNORE`), тести (юніт, Python, живі).

1. Рендер `min(devicePixelRatio, 2)` у межах `SHOT_MAX_PX` (6 Мп).
2. Мініатюра 720×720 JPEG 0.7 → `meta.shot`; повний 2400×2400 JPEG 0.85 (`toBlob`) → `uploadShot` → `meta.shotUrl`.
3. Лайтбокс і `openShot` — спершу `meta.shotUrl`.
4. Локальні: `POST/GET /api/local-shots`, файл `.dc-local-shots/<id>.jpg`, правило `.dc-local-shots/` у `TASK_IGNORE`;
   `local-adapter.uploadShot`; `dual-store` — локальні піни в локальне сховище.
5. Тести: розміри мініатюри й повного (DPR 2 і 1, стеля пікселів), лайтбокс бере `shotUrl`, сервер (валідація id і
   `data:image/jpeg`, межа розміру, шлях лише в теці задачі, правило ignore), адаптери, живий Deai: пін → файл і `shotUrl`.

## Task 3 — реліз 0.35.1

Злиття `main` (після 0.35.0), `package.json` + CHANGELOG, повний прогін (node, Python, усі живі по одному під локом),
охоронець забороненого списку, перевірка на стенді (частка знімків, розміри, найдовша задача після «Надіслати»), ff у живий
checkout, тег, перезапуск канваса, `/api/update`. Push — лише за «да» власника.
