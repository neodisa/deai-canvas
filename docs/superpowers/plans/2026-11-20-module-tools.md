# Модулі М1 — інструменти й дії — план

> **Для виконавців:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (контролер) / superpowers:test-driven-development
> (виконавець). Кроки з чекбоксами (`- [ ]`).

**Мета:** модуль простору (`api: 2`) додає свої **інструменти** (кнопка в острівці, панель-пісочниця праворуч, пункт ⌘K,
необовʼязкова клавіша) і **дії** (пункт ⌘K, «⋯» задачі, дропдаун ітерації → функція `server.py` → тост). Без модулів з
інструментами оболонка — байт у байт як була.

**Спека:** `docs/superpowers/specs/2026-11-20-modules-boundaries-design.md` (поправка 20.11: скрипт у макеті, М2 — відкладено;
у М1 `frame` у маніфесті — відмова).

**Архітектура.** Маніфест розширюється в `app/deai_modules.py` (`API_VERSIONS = (1, 2)`), `server.py` модуля дає функції
`tool_*` і `action_<id>`. Сервер: легкий `GET /api/module-ext` (що малювати), роздача файлів панелі
`GET /api/module-ui/<простір>/<модуль>/<шлях>` (пісочниця CSP, лише тека панелі), набір панелі
`GET /api/module-ui-kit/<файл>` (`kit.css`, `bridge.js`), `POST /api/module-tool` і `POST /api/module-action`. Оболонка: новий
модуль `app/module-host.js` (міст і стан панелі, чиста логіка під юніт-тести), права панель `#mod-panel`, кнопки острівця,
клавіші, ⌘K, меню. Межа безпеки — діалог довіри (код модуля після довіри виконується з правами людини); пісочниця панелі —
межа стабільності й явного API: панель не бачить канваса, його сховища й `/api/*`, лише міст.

**Стек:** vanilla JS (ES-модулі), Python 3 stdlib, `node --test`, `unittest`, Playwright (живі).

**Рівень строгості:** повний (виконання коду модуля, довіра, нова поверхня HTTP). Окреме ревʼю (спека → якість) після T1, T3,
T4, T5; T2, T6, T7 — одне спільне ревʼю; наприкінці — фінальне ревʼю всієї гілки.

---

## Спільні правила (для КОЖНОЇ задачі)

- Робоча тека: worktree `deai-canvas-dev`, гілка `feat/module-tools`. Інших гілок не чіпати.
- Коміт: `git add -- <нові файли>` і
  `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>`.
  Ніколи `git add -A`, `--amend`, `stash`, `reset`, `checkout` інших гілок, `rebase`. Ніколи не стейджити
  `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `…2026-11-09-agents-sdk-policy-addendum.md`.
- Паралельно в тому ж репо працюють сесії «Перший запуск» і «Відповіді в коментарях» (свої worktree). Живі тести —
  під замком: `mkdir /private/tmp/deai-live.lock` перед прогоном (не вдалось — чекати й повторити), `rmdir` після.
- Тести НЕ торкаються портів 8765/4317, живого дерева `~/Liga Tools/deai-canvas`, справжніх `~/.deai`, `~/deai-published`,
  `~/deai-work`, `~/.gitconfig`, `~/.claude/pipeline-feedback`, Teams, Supabase, Jira, Vercel. Python — `python3 -B`. Без
  встановлення пакетів із мережі. Свої модулі в тестах — `tests/test_modules_own.py` `OwnEnv` (тимчасовий `DEAI_HOME`,
  довіра через шов `DEAI_TRUST_CONFIRM` лише з нетиповим `DEAI_HOME`).
- Живі тести — ПО ОДНОМУ файлу: `node --test --import ./tests/live/_env.mjs tests/live/<f>.test.mjs`; ніколи паралельно з
  Python-набором; код не міняється під час прогону. Порти — смуги `tests/live/_port.mjs` (нова смуга для нового файла).
  Сервери зупиняти лише за PID; ніколи `pkill`/`killall`; без `rm -rf` (`mktemp -d`).
- Кожна НОВА перевірка доводиться мутацією (зламати → червоне → повернути → зелене; у звіт).
- Тексти ядра: обидві мови в `app/i18n.js` (uk + en). Без кирилиці поза `i18n.js` у JS (тест). Тексти модуля (назви
  інструментів і дій) — як є, через `esc`. Жодних підписів, яких нема в спеці.
- `tests/css-guards.test.mjs` — повні літерали класів; нові стилі — токени, без колірних літералів.
- Приклади адрес у тестах — вигадані (`example.com`, `10.20.30.40`); у публічному репо — жодних справжніх імен, хостів,
  ключів, tmp-шляхів.
- Наприкінці задачі: `node --test tests/*.test.mjs`, `python3 -B -m unittest tests.test_modules tests.test_modules_own
  tests.test_serve` (і інші набори, які задача зачепила), живі файли, які задача зачепила.

---

### Task 1: Маніфест `api: 2` — `tools` і `actions`

**Файли:** `app/deai_modules.py`, тести `tests/test_modules.py` (вбудовані через `DEAI_EXTRA_MODULES`) і
`tests/test_modules_own.py`, новий `tests/icons-parity.test.mjs`.

Контракт (джерело правди — цей розділ):

- `API_VERSIONS = (1, 2)`; `API_VERSION = 2` лишається іменем «найновіший». `api` маніфесту — ціле з `API_VERSIONS`, інакше
  `api: must be one of 1, 2` (старіший Deai на `api: 2` уже відмовляє — `api: must be 1`). `Module.api` — значення з маніфесту
  (зараз усюди підставляється `API_VERSION`: `_failed`, `_build`, `_meta_kw` → брати `meta['api']`).
- `tools` / `actions` при `api: 1` — `tools: requires api 2` / `actions: requires api 2`.
- `tools`: список 1..`MAX_TOOLS = 4` обʼєктів; ключі лише `id`, `label`, `icon`, `panel`, `key` (невідомий ключ —
  `tools[i]: unknown key 'x'`; `frame` — окремо `tools[i].frame: not supported yet`).
  - `id` — `ID_RE`, унікальний у модулі; `label` — непорожній рядок ≤ 40 знаків (після `strip`);
  - `icon` — імʼя з `core_icons()`; невідоме — `tools[i].icon: unknown icon 'x'`;
  - `panel` — відносний шлях `UI_PATH_RE` = 2..4 сегменти `[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}` через `/`, останній на `.html`
    (тобто панель завжди в підтеці, не в корені модуля поруч із `server.py`); файл існує в теці модуля, `lstat` — звичайний
    файл, `st_nlink == 1`, кожен сегмент-тека — не посилання, розмір ≤ `MAX_PANEL_BYTES = 256 * 1024`; імʼя — рівно як на
    диску (як `_check_client`: `os.listdir` кожного рівня);
  - `key` — необовʼязковий, рядок з однієї латинської літери; нормалізується до верхнього регістру; літера з
    `RESERVED_KEYS = frozenset('CIHMP')` — `tools[i].key: 'C' is reserved by Deai`; повтор у межах модуля — відмова.
- `actions`: список 1..`MAX_ACTIONS = 8` обʼєктів; ключі лише `id`, `label`, `where`, `timeout_s`.
  - `id` — `ID_RE`, унікальний; `label` — непорожній ≤ 60; `where` — непорожній список без повторів із
    `ACTION_WHERE = ('palette', 'task', 'iteration')`; `timeout_s` — ціле 1..`MAX_CHECK_TIMEOUT` (без нього —
    `ACTION_TIMEOUT = 15`).
- `_build`: для модуля з `actions` — обовʼязкова callable `action_<id з '-' → '_'>` (`server.py: no callable action_x()` —
  `bad-manifest`); для модуля з `tools` — у `fns` додаються ВСІ callable верхнього рівня, чиє імʼя відповідає
  `TOOL_FN_RE = re.compile(r'tool_[a-z0-9_]{1,40}')` (жодної обовʼязкової — панель може не кликати сервер).
- Нові слоти `Module`: `tools` (кортеж словників `{id, label, icon, panel, key}`, `key` — `None` чи літера), `actions`
  (кортеж `{id, label, where: tuple, timeout_s: int|None}`). Додати в `__slots__`, `__init__`, `_clone` (копії кортежів),
  `_meta_kw`, `_failed`.
- `core_icons()`: множина імен з `app/icons.js` за регулярним виразом `^  ([a-z][a-zA-Z0-9]*): \``, з кешем на процес. Порожня
  множина (файл не прочитався) — кожна іконка невідома (відмова, не мовчазний пропуск).
- Модуль без `tools`/`actions` (будь-який `api`) — жодних змін у поведінці й записах API.

- [ ] Тести (червоні спершу): валідний `api: 2` з інструментом і дією; `api: 3`; `tools` при `api: 1`; кожна відмова зі
  списку вище окремим тестом (невідомий ключ, `frame`, погані `id`/`label`/`icon`/`key`, зарезервована клавіша, дубль `id`,
  `panel` у корені, `../`, абсолютний, не `.html`, посилання (файл і тека), жорстке посилання, завеликий, регістр-двійник,
  відсутній файл; `where` порожній/невідомий/дубль; `timeout_s` 0/151/рядок; дія без `action_*`); `tool_*` потрапляють у
  `fn()`, `tool-bad` (дефіс) — ні; `_clone` не ділить кортежі; свій модуль (`OwnEnv`) з інструментом довіряється й
  завантажується зі знімка (тека `panel/` у знімку є).
- [ ] `tests/icons-parity.test.mjs`: той самий регулярний вираз, застосований до тексту `app/icons.js`, дає рівно
  `Object.keys(ICONS)` (захист від формату, на якому Python-розбір мовчки втратив би іконки).
- [ ] Реалізація; мутації: прибрати перевірку `nlink`, перевірку `RESERVED_KEYS`, нормалізацію регістру клавіші.
- [ ] Коміт: `feat(modules): маніфест api 2 — інструменти й дії модуля`.

### Task 2: Що малювати — `GET /api/module-ext` і діалог довіри

**Файли:** `app/serve.py`, `app/deai_modules.py` (`trust_view`, нова `extensions(space)`), `app/trust-view.js`,
`app/i18n.js`, тести `tests/test_serve.py`, `tests/test_modules_own.py`, `tests/trust-view.test.mjs` (наявний або новий).

- [ ] `deai_modules.extensions(space)` → `{'tools': [...], 'actions': [...]}` лише з модулів каталогу простору, що
  `status == 'ok'`, увімкнені явно (`space_modules`) і мають `api == 2`; порядок — порядок каталогу (за абеткою id),
  інструменти модуля — у порядку маніфесту. Запис інструмента:
  `{'module': mid, 'module_name': m.name, 'id', 'label', 'icon', 'key', 'panel': '/api/module-ui/<sid>/<mid>/<шлях, quote>'}`;
  дія: `{'module', 'module_name', 'id', 'label', 'where': [...]}`. Клавіша, яку оголосили ≥ 2 інструменти (будь-яких
  модулів), — `key: None` в усіх них.
- [ ] `GET /api/module-ext?space=<id>` → `extensions(space)` (той самий вибір простору, обробка `space-json-unreadable` і
  `spaces-off`, що в `GET /api/modules`; простір без шару просторів — `{'tools': [], 'actions': []}`). Додати маршрут у
  список GET-маршрутів API (~serve.py:6194) — ті самі перевірки походження, що в сусідів.
- [ ] `trust_view` (свій модуль): поле `tools` (`[{label, icon}]`) і `actions` (`[{label}]`) з маніфесту ТЕКИ (до довіри,
  як решта полів); `trust-view.js` `trustDialogHTML` — рядки «Інструменти в острівці: …» і «Дії: …» (лише коли є), назви
  через `esc`; i18n `trustTools`, `trustActions` (uk/en).
- [ ] Тести: вибір модулів (вимкнений, недовірений, `changed`, `api: 1`, помилковий — не потрапляють), порядок, конфлікт
  клавіш, `quote` шляху, простір без шару; діалог довіри з інструментами/діями й без них (золотий рядок без змін).
- [ ] Коміт: `feat(modules): /api/module-ext і інструменти з діями в діалозі довіри`.

### Task 3: Роздача панелі й набір панелі

**Файли:** `app/serve.py`, нові `app/module-kit/kit.css`, `app/module-kit/bridge.js`, тести `tests/test_serve.py`,
`tests/module-bridge.test.mjs` (новий, юніт моста панелі в `node:vm` з підробленим `parent`).

Роздача `GET /api/module-ui/<простір>/<модуль>/<шлях…>` — до `_take_task`, як `/api/module-client/`:

- [ ] `module_ui_target(path)` → `(Module, [сегменти шляху], kind)` або `None`, НЕ кидає. Складові розкодовані суворо
  (`unquote(errors='strict')`, як `module_client_target`; `%2f` усередині складової — відмова), простір — `SPACE_ID_RE` і є в
  реєстрі, модуль — `ID_RE`, з `catalog(sp)` під `request_space(sid)`, `status == 'ok'`, явно увімкнений у просторі,
  `api == 2`. Кожен сегмент шляху — `[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}`, 2..6 сегментів. Дозволено: файл усередині теки
  панелі якогось інструмента модуля (префікс сегментів = тека `panel`) з розширенням з
  `MODULE_UI_TYPES = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
  '.png': 'image/png', '.json': 'application/json', '.woff2': 'font/woff2'}` (`kind` — `html` для `.html`, інакше `asset`).
- [ ] Відкриття — обхід дескрипторами від `mod.dir` (свій модуль — тека знімка довіри): кожна тека `O_DIRECTORY|O_NOFOLLOW`,
  файл — тим самим захистом, що `_published_open_file` (звичайний, `nlink == 1`, `O_NOFOLLOW`); без `dir_fd` — запасний
  `open_published_file`. Будь-яка відмова — сталий 404 як `_send_module_client_404`.
- [ ] Заголовки КОЖНОЇ відповіді (і 304): `MODULE_UI_HEADERS` =
  `Content-Security-Policy: sandbox allow-scripts allow-forms; default-src 'self' 'unsafe-inline' data:; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'`,
  `X-Content-Type-Options: nosniff`, `Access-Control-Allow-Origin: *`, `Referrer-Policy: no-referrer`.
- [ ] `html`: тіло = файл (≤ 256 КіБ, читається з відкритого дескриптора) з уставкою
  `<link rel="stylesheet" href="/api/module-ui-kit/kit.css"><script src="/api/module-ui-kit/bridge.js"></script>`
  одразу після `<!doctype …>` (без урахування регістру, з пробілами перед ним), або на самому початку, якщо doctype нема.
  `Content-Type: text/html; charset=utf-8`, `Cache-Control: no-store` (панель має бачити перепубліковані байти знімка).
  `asset` — `_send_iter_file` з `extra_headers=MODULE_UI_HEADERS`.
- [ ] `GET /api/module-ui-kit/<файл>`: лише `MODULE_KIT_FILES = ('kit.css', 'bridge.js')` з `app/module-kit/`, ті самі
  `MODULE_UI_HEADERS`; решта — сталий 404.
- [ ] `bridge.js` (класичний скрипт, без імпортів, без кирилиці) — `window.deai`:
  - вихідне: `parent.postMessage({deai: 1, id, method, args}, '*')`; `id` — лічильник; методи `hello`, `context`,
    `selection`, `call(fn, args)`, `toast(text)`, `close()`; кожен (крім `toast`/`close`) повертає `Promise`;
  - вхідне (`message` лише від `parent`, `event.source === window.parent`): відповідь `{deai: 1, re, ok, value}` /
    `{deai: 1, re, ok: false, error, detail}` → resolve/reject (`Error` з `code = error`); подія
    `{deai: 1, event, data}` → підписники `deai.on(event, fn)` (повертає функцію відписки);
  - подія `init` / `theme` (`{theme, vars}`): ставить `document.documentElement.dataset.theme = theme` і кожну пару `vars`
    (лише ключі `--[a-z0-9-]+`, значення-рядки ≤ 200) через `style.setProperty`; `init` додатково резолвить `deai.ready`;
  - старт: одразу шле `hello`.
- [ ] `kit.css`: базове тло/текст/шрифт панелі й класи-контракт для авторів `dk-btn`, `dk-btn--primary`, `dk-field`
  (input/textarea/select), `dk-list`, `dk-row`, `dk-muted`, `dk-empty` — значення з відповідних правил `app/styles.css`,
  записані через `var(--…, запасне)`. Список змінних, які набір читає, — `KIT_VARS` у `app/module-kit/kit-vars.js`
  (експорт масиву; його ж візьме оболонка в T5). Тест: кожен `var(--x` у `kit.css` є в `KIT_VARS`, і кожна з `KIT_VARS`
  визначена в `app/styles.css`.
- [ ] Тести Python: позитив (html з уставкою, asset), CSP/ACAO/nosniff на 200 і 304, 404 на: `server.py`, `module.json`,
  файл поза текою панелі, тека-посилання, файл-посилання, жорстке посилання, недозволене розширення, `..`/`%2e%2e`/`%2f`,
  чужий простір, вимкнений/недовірений/`changed`/`api: 1` модуль, неіснуючий; правка теки після довіри не доходить
  (роздається знімок); kit — лише два файли. Юніт моста: запит/відповідь, reject з кодом, подія, `vars` з поганим ключем
  ігнорується, повідомлення не від `parent` ігнорується.
- [ ] Коміт: `feat(modules): роздача панелі інструмента в пісочниці й набір панелі`.

### Task 4: Виклики — `POST /api/module-tool` і `POST /api/module-action`

**Файли:** `app/serve.py`, `app/deai_modules.py` (`call_tool`, `run_action`), тести `tests/test_serve.py`,
`tests/test_modules_own.py`.

- [ ] Обидва маршрути — у списку POST-маршрутів API з тими самими перевірками походження/заголовків, що в
  `/api/module-check`; простір — як у `/api/module-check`. Тіло ≤ 64 КіБ, інакше 413 зі сталим кодом.
- [ ] `POST /api/module-tool` `{module, fn, args}`: модуль — з `extensions`-правилом (увімкнений, `ok`, `api: 2`, має
  `tools`); `fn` — `TOOL_FN_RE` і є в `fn()`; виклик `call(m, fn, module_ctx(space, m), args, timeout=TOOL_TIMEOUT)` з
  `TOOL_TIMEOUT = 15`. Результат — JSON-серіалізовний (`json.dumps(..., allow_nan=False)`) і ≤ 256 КіБ, інакше
  `module-error` «result is not JSON» / «result is too big». Відповідь `{'value': …}`; помилки — звичайним конвертом
  ядра (код, статус, `detail` — вже очищений `call()`).
- [ ] `POST /api/module-action` `{module, action, from, task, iteration}`: дія оголошена, `from ∈ action.where`; `task` — id
  наявної задачі поточного реєстру, що належить цьому простору (інакше 404 `unknown-task`); `iteration` — `None` чи id ітерації цієї задачі. Модулю
  передається `target = {'from', 'task': {'id', 'name', 'dir'}, 'iteration': {'id', 'name'} | None}` (`dir` — абсолютна тека
  задачі). Виклик `call(m, 'action_…', ctx, target, timeout=timeout_s or ACTION_TIMEOUT)`. Результат нормалізується:
  `ok` — `bool` (інакше `module-error`), `text` — рядок, обрізаний до 300, `url` — лише `http://`/`https://` ≤ 2048, інше
  відкидається мовчки. Відповідь `{'ok', 'text'?, 'url'?}`.
- [ ] Ізольований прогін (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) — як `module_check_verdict`: модулі з `shared_state` не кличуться.
- [ ] Тести: позитив обох; невідомий/вимкнений/недовірений/`api: 1` модуль; `fn` без префікса, `__init__`, `check`,
  `action_x` через `/api/module-tool`; дія з чужого `where`; невідома задача/ітерація; тайм-аут (`check-timeout`);
  виняток модуля з секретом у тексті (вирізано); не-JSON і завеликий результат; `url` `javascript:` відкинуто; тіло
  > 64 КіБ; запит без належного походження відхилено.
- [ ] Коміт: `feat(modules): виклики інструментів і дій модуля`.

### Task 5: Оболонка — острівець, панель-пісочниця, міст, клавіші, ⌘K

**Файли:** новий `app/module-host.js` (+ `tests/module-host.test.mjs`), `app/island.js`, `app/app.js`, `app/index.html`,
`app/styles.css`, `app/shell-palette.js`, `app/i18n.js`, `app/icons.js` (лише якщо треба `puzzle` чи інша), тести
`tests/island.test.mjs` (наявний), `tests/shell-palette.test.mjs`, новий живий `tests/live/module-tools.test.mjs`.

- [ ] `module-host.js` (без DOM-залежностей у логіці, юніт-тестований):
  - `islandModTools(ext, {mode, screen})` → до `MAX_ISLAND_TOOLS = 3` перших інструментів, лише `screen === 'task'` і
    `mode === 'layout'`;
  - `modKeyMap(ext, coreKeys)` → `{літера: ключ інструмента}` без літер ядра (`coreKeys` — з `KEYS` і обробників `app.js`);
  - `handleBridge(msg, ctx)` → `{reply?, effect?}`: перевіряє форму (`deai === 1`, ціле `id`, метод зі списку, `args` —
    масив), розмір (`JSON.stringify` ≤ 64 КіБ, інакше `too-big`), не більше 4 паралельних `call` (`busy`); методи:
    `hello` → подія `init` `{context, theme, vars}`; `context`; `selection`; `call(fn, args)` → `POST /api/module-tool` з
    модулем ПАНЕЛІ (панель модуль не обирає); `toast(text)` → текст ≤ 200, показ «<назва інструмента>: текст»;
    `close()`; невідомий — `unknown-method`;
  - `context` = `{space: {id, name}, task: {id, name}, iteration: {id, name} | null, page: {id, title} | null, lang, theme}`;
  - `selection` = останній вибір інспектора НА ПОТОЧНІЙ сторінці (`{selector, tag, styles}` із `report()` у `paintInsp`) або
    `null`; зміна сторінки скидає. Події `selection` нема: панель і інспектор взаємовиключні, тож поки панель відкрита,
    вибір не змінюється (спека «зміна вибору» — до М2/спільних панелей).
- [ ] Права панель: `<aside id="mod-panel" class="mod-panel" hidden>` у `index.html` поруч із `#insp-panel`/`#cmt-panel`:
  шапка (іконка, назва інструмента, кнопка «Закрити» `data-act="modclose"`) і
  `<iframe sandbox="allow-scripts allow-forms" referrerpolicy="no-referrer" title="…">`. Ширина й зсув робочої зони —
  як `body.with-insp` (`body.with-mod`), той самий `--insp-w`.
- [ ] Одна панель на раз: відкриття інструмента закриває коментарі й інспектор їхніми функціями; `setCommentsOpen(true)`,
  увімкнення інспектора, `toggleClean`, вихід з екрана задачі, режим «Огляд», зміна простору — закривають інструмент.
  Зміна задачі/ітерації/сторінки в тому ж просторі — панель лишається, отримує подію `context`. Закриття — спершу подія
  `close` у панель, потім зняття `src` (`about:blank`) і `hidden`.
- [ ] Міст: `window.addEventListener('message')` — лише `ev.source === modFrame.contentWindow`, відповіді —
  `modFrame.contentWindow.postMessage(…, '*')` (непрозоре походження). `vars` — значення `KIT_VARS` з
  `getComputedStyle(document.documentElement)`; зміна теми чи кольору простору — подія `theme`.
- [ ] Дані: `GET /api/module-ext` на вході в простір/задачу і після змін модулів (увімкнення, довіра, налаштування —
  ті самі місця, де зараз перечитується `/api/modules`); збій — інструментів нема, без помилки в смузі.
- [ ] `islandToolsHTML(…, modTools)`: кнопки після інспектора (`data-act="modtool" data-val="<модуль>/<інструмент>"`,
  `aria-pressed`, `aria-label`/`title` — назва, з літерою, якщо є); іконка, якої нема в `ICONS`, — `puzzle`. Без
  `modTools` — вивід байт у байт як був (наявні золоті тести не змінюються).
- [ ] Клавіші: літера з `modKeyMap` без модифікаторів, не в полі вводу, екран задачі, «Макет» → перемкнути інструмент.
- [ ] ⌘K: `paletteActions(state)` отримує `state.modTools`; пункти `{id: 'modtool:<ключ>', group: 'modules', label, icon,
  kbd, act: 'modtool', val}` — новий необовʼязковий `label` (сирий текст, через `esc`) поряд із `labelKey`; група
  «Модулі» (`palGroupModules`). Тест «кожна kbd-підказка має обробник» розширити: kbd модульних пунктів обслуговує
  `modKeyMap`.
- [ ] i18n: `modClose` «Закрити», `palGroupModules` «Модулі», `modToolKey` (підказка з літерою), uk + en.
- [ ] Живий `module-tools.test.mjs` (свій модуль-фікстура в тимчасовому просторі, довіра через шов, увімкнення через API):
  кнопка в острівці лише в «Макеті»; клік → панель з назвою, рамка `sandbox` без `allow-same-origin`; панель отримала
  `init` і показує назву сторінки з `context`; у панелі `localStorage` кидає, `fetch('/api/tasks')` відхилено (результат
  панель пише у свій DOM, тест читає `frame.locator`); `deai.call('tool_echo', …)` повертає значення; відкриття коментарів
  закриває панель; клавіша модуля перемикає; ⌘K показує пункт; без модулів — острівець як був (порівняння розмітки).
- [ ] Мутації: прибрати перевірку `ev.source`; дати панелі обирати модуль у `call`; прибрати закриття панелі в
  `setCommentsOpen`.
- [ ] Коміт: `feat(modules): інструменти модулів в острівці й панель-пісочниця з мостом`.

### Task 6: Дії модулів у ⌘K, «⋯» задачі й дропдауні ітерації

**Файли:** `app/module-host.js` (`actionItems(ext, where)`), `app/shell-palette.js`, `app/task-menu.js`, `app/shell-bar.js`
(`crumbIter`), `app/app.js` (`execPaletteAction`, `wireHome`, `BAR_ACTIONS`), `app/i18n.js`, тести
`tests/shell-palette.test.mjs`, `tests/task-menu.test.mjs` (наявний або новий), `tests/shell-bar.test.mjs`, живий
`module-tools.test.mjs` (доповнити).

- [ ] Пункти: ⌘K — дії з `palette` (ціль — поточна задача й ітерація; поза задачею пунктів нема), «⋯» картки задачі — з
  `task` (ціль — ця задача, ітерація `null`), дропдаун ітерації — з `iteration` (ціль — ця ітерація). Пункт — назва дії
  (сирий текст), іконка `puzzle`, `data-act="modact"`, значення `<модуль>/<дія>`. Без дій — меню байт у байт як були.
- [ ] Виконання: `POST /api/module-action`; поки йде — повторний запуск тієї ж дії ігнорується; відповідь `ok` → тост
  `text` або `modActDone` «Готово»; `url` → кнопка тосту `modActOpen` «Відкрити» (`window.open(url, '_blank', 'noopener')`);
  `ok: false` чи помилка → тост `modActFail` «<назва дії>: <текст>».
- [ ] i18n: `modActDone`, `modActOpen`, `modActFail` (uk + en).
- [ ] Тести: юніт (пункти за `where`, порядок, екранування назви), меню без дій — золоті; живий — дія з ⌘K і з «⋯» дає тост,
  `url` дає кнопку «Відкрити».
- [ ] Коміт: `feat(modules): дії модулів у ⌘K і меню задачі та ітерації`.

### Task 7: Приклад-модуль і документація

**Файли:** нові `docs/modules/examples/page-notes/{module.json,server.py,panel/index.html,panel/notes.js}`,
`docs/modules/authoring.md`, генератор `AGENTS.md` (де згадано модулі; знайти за `authoring`), `README.md` (розділ модулів),
живий `module-tools.test.mjs` (фікстура — копія прикладу).

- [ ] Приклад «Нотатки сторінок» (`api: 2`, без ролей): інструмент `notes` (`icon` з набору ядра, `panel/index.html`,
  клавіша `N`, якщо вільна) — нотатка до поточної сторінки: панель читає `deai.context()`, вантажить
  `deai.call('tool_load', {task, page})`, зберігає `deai.call('tool_save', {task, page, text})`, оновлюється на подію
  `context`; сервер пише JSON у `ctx['cache_dir']` (створює 0700). Дія `summary` (`where: ["palette", "task"]`) —
  `{ok: true, text: "Нотаток: N"}`. Стилі — класи `dk-*`.
- [ ] `authoring.md`: розділ «Інструменти й дії (api 2)» — маніфест (усі поля, ліміти, відмови), міст (`window.deai`, методи,
  події, коди помилок), класи `dk-*`, `tool_*`/`action_*` з сигнатурами й тайм-аутами, `target` дії; розділ «Межі» (каркас /
  точки розширення / «ні», зі спеки); скрипт у макеті — «поки ні» з причиною.
- [ ] Генератор `AGENTS.md` і README — коротко: модуль може додати інструмент і дію; деталі — `authoring.md`.
- [ ] Живий тест на прикладі: довіра → увімкнення → нотатка зберігається й переживає перезавантаження → дія показує
  кількість.
- [ ] Коміт: `docs(modules): приклад «Нотатки сторінок» і контракт інструментів у authoring.md`.

### Task 8 (контролер): реліз

- [ ] `git merge main` (не rebase) — підхопити релізи паралельних сесій; версія — наступна вільна мінорна на момент
  релізу; CHANGELOG (що дає модуль, межі, М2 відкладено), `package.json`.
- [ ] Повний прогін: `node --test tests/*.test.mjs`, усі Python-набори, живі файли по одному (мінімум
  `module-tools`, `own-modules`, `comments`, `clean-view`, `ext-shell`).
- [ ] Охоронець забороненого списку (`DEAI_REQUIRE_FORBIDDEN_LIST=1 … tests.test_no_internal_addresses`).
- [ ] Фінальне ревʼю всієї гілки (Sonnet, англійською), правки, релізний прогін за рецептом; push — лише з «да» власника.
