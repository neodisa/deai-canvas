# Універсальна роль `comments` (2b-2) — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** командні коментарі як роль модуля з універсальним контрактом (браузерний адаптер сховища CommentLayer + серверні `client_config`/`list`/`resolve`), перший модуль — `supabase-comments`, доказ універсальності — тестовий `memo-comments`.

**Architecture:** ядро вчиться ролі `comments`: маніфест `client` (файли адаптера) і прапорець `public` у секретах; роздача файлів адаптера; сніпет у сторінках канваса, на «Огляді» й у збірках превʼю; агент читає/закриває через модуль. Шлях ЛІГА (`'legacy'`) побайтно той самий.

**Tech Stack:** Python 3 stdlib, unittest, ES-модулі без збирача, `node:test`, Playwright; supabase-js 2.110.0 (MIT, вендорено).

Спека: `docs/superpowers/specs/2026-10-19-comments-role-design.md`. Зразки планів: `2026-10-14-modules-2a.md`, `2026-10-16-vercel-publish.md`.

## Правила репо, яких мусить триматись кожна задача

- Репо `neodisa/deai-canvas` (корінь репо), гілка `main`. Автор: `git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit …`; повідомлення українською + `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Лише свої файли. НЕ пушити.
- ⛔ Порти 8765/4317 — живі сервери власника; свої — випадкові, зупиняти за PID; жодного `pkill`/`killall`. Справжні `~/.deai`, `~/deai-published`, `tasks.json` не чіпати. `DEAI_HOME` у оболонці НЕ виставляти.
- ⛔ ЖОДНОГО реального мережевого запиту в тестах (розтяжки; підставні сервери на `127.0.0.1`).
- Усі прогони — через сторож `python3 "$G" <с> <МБ> <команда>`, послідовно; мутації — `python3 -B`, відновлення байт-у-байт.
- Рядки UI — `t('key')` в обох словниках; `esc`/`textContent`; кольори — токени. Золотий знімок ЛІГА (`tests/legacy-golden.test.mjs`) — без змін.
- База 0.3.0: node 1258 + inspector-core; py tests/ 1938 skip 1; bin 156; app 170; живі vercel+modules+spaces 20/20.

## Файли

| Файл | Відповідальність |
|---|---|
| `app/deai_modules.py` | `client` у маніфесті, `public` у налаштуваннях, роль `comments`, `provider/capabilities` |
| `app/serve.py` | `/api/module-client/…`; сніпет `/commented`, `/api/comment-config`; `build_preview` з коментарями модуля; читання пінів для агента |
| `app/overview-comments.js`, `app/app.js`, `app/spaces-model.js`, `app/bar-model.js`, `app/shell-palette.js` | «Огляд» через адаптер модуля; вкладка «Команда» за `capabilities.comments` |
| `bin/inbox.py` | `list`/`resolve` через модуль |
| `app/modules/supabase-comments/*` (нові) | модуль Supabase |
| `tests/fixtures/modules/memo-comments/*` (нові) | тестовий модуль-доказ |
| `docs/modules/comments.md` (новий) | як написати модуль коментарів |

---

### Task 1: ядро — роль `comments`, маніфест `client`, прапорець `public`, роздача адаптера

**Files:** `app/deai_modules.py`, `app/serve.py`; `tests/test_modules.py`, новий `tests/test_comments_role.py`; фікстура `tests/fixtures/modules/memo-comments/{module.json,server.py,adapter.js}`.

- Маніфест: `client` — список 1–8 імен (`^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.js$`), кожен — звичайний файл у теці модуля ≤ 512 КБ, без симлінків; обовʼязковий для ролі `comments`, заборонений без неї (`bad-manifest`). `Module.client` (tuple). Налаштування `secret` може мати `"public": true` (bool); на інших типах — `bad-manifest`.
- `ROLES_CALLED += ('comments',)`; модуль із роллю `comments` мусить мати `client_config`, `list`, `resolve`, `check`.
- `provider('comments', space)`: явно ввімкнений модуль → він; простір з `integrations` → `'legacy'`; інакше `None`. `capabilities` → `{'publish', 'tokens', 'comments'}` (тотальна).
- `comments_client(space, prov) -> dict` (у `deai_modules`): `call(prov,'client_config',ctx, timeout=CHECK_TIMEOUT)`; перевірка: `dict`, ≤ 4096 байт JSON, значення str/int/float/bool/None, жодне значення секрету з `public` ≠ true (≥ 1 символу — тут важливі навіть короткі) не міститься в жодному значенні → інакше `ModuleError('module-error')`.
- `channel_for(space, tid, internal=False)` → `deai/<space-id>/<tid>` (`/internal`).
- `GET /api/module-client/<module-id>/<file>`: модуль із `catalog()`, `status=='ok'`, роль `comments`, `file ∈ module.client`; відкриття з тим самим захистом, що `open_published_file` (без симлінків, `O_NOFOLLOW`, `S_ISREG`); `text/javascript; charset=utf-8`, `X-Content-Type-Options: nosniff`, ETag/304; усе інше → 404 зі сталим тілом. Маршрут — у `HANDLED_PREFIXES`.
- `DEAI_EXTRA_MODULES` (оточення): додаткова тека вбудованих модулів (для тестів); `catalog()` обʼєднує (`id`-конфлікт → модуль з `app/modules` виграє, інший — `status:'error'` з причиною). Задокументувати в docstring як тестовий шов.
- Фікстура `memo-comments`: `module.json` (`roles: ["comments"]`, `client: ["adapter.js"]`, налаштування `endpoint` text — адреса тестового сервера `http://127.0.0.1:<порт>`), `server.py` (`client_config` → `{endpoint}`; `list`/`resolve` — HTTP до `endpoint`; `check` → ok), `adapter.js` (`DeaiComments.create(cfg)` — `load/save/remove/subscribe` через `fetch(cfg.endpoint + '/c/' + encodeURIComponent(cfg.channel))`, опитування раз на 1 с для `subscribe`).
- [ ] Тести: маніфест (`client` правила, `public`), постачальник/`capabilities.comments` для всіх форм простору, `comments_client` (форма, межа, непублічний секрет → відмова, публічний — дозволено), `channel_for`, маршрут адаптера (200 + заголовки, 304, неоголошений файл / dotfile / `..` / симлінк / модуль без ролі / неіснуючий → 404), `DEAI_EXTRA_MODULES` (фікстура вантажиться, конфлікт id). Мутації: прибрати перевірку непублічних секретів; роздавати неоголошений файл; `public` на не-секреті приймається.
- [ ] Коміт `feat(modules): роль comments — маніфест client, публічні секрети, роздача адаптера`.

### Task 2: сторінки канваса й «Огляд» через модуль; вкладка «Команда»

**Files:** `app/serve.py` (`_commented` ~:4377, `COMMENT_SNIPPET` ~:2125, `_comment_config` ~:4565), `app/overview-comments.js`, `app/app.js`, `app/spaces-model.js` (`effectiveCommentMode`), `app/bar-model.js`/`app/shell-palette.js` (аудиторія `project`), `app/i18n.js`; тести `tests/test_comments_role.py`, node-тести, `tests/spaces-wiring.test.mjs`.

- `/commented?ch=project`, постачальник-модуль: новий `MODULE_COMMENT_SNIPPET` — `comment-layer.min.js` (з `/app/vendor/`), файли адаптера (`/api/module-client/<id>/<file>`), `window.__deaiCommentsCfg = <json: {...client_config, channel}>` (екранування для `<script>` як у наявних сніпетах), завантажувач CommentLayer зі `storage: DeaiComments.create({...cfg, onChange})`; `'legacy'` — як сьогодні; `None` — пониження до `local`, як сьогодні.
- `/api/comment-config?ch=project`: модуль → `{ch:'project', module, client:[адреси], config, channel, version, user}`; `'legacy'` — як було; `None` → 409 як було.
- `overview-comments.js`: для відповіді з `module` — вантажить файли `client` по порядку і бере `DeaiComments.create`; гілка ЛІГА (CDN supabase) — без змін.
- UI: `hasTeamComments(space) = capabilities ? capabilities.comments != null : integrations !== false`; аудиторія `project`, вкладка «Команда», `effectiveCommentMode` — на ньому; `noOutward` не чіпати.
- [ ] Тести: сніпет для модуля (порядок скриптів, конфіг без непублічних секретів, канал), ЛІГА побайтно та сама, `None` → local; `comment-config` для трьох випадків; node: `hasTeamComments`, режим, палітра/смуга; i18n. Мутації: сніпет модуля в ЛІГА-просторі; `hasTeamComments` за `integrations`.
- [ ] Коміт `feat(comments): коментарі модуля в сторінках канваса й на «Огляді»; вкладка «Команда» за capabilities`.

### Task 3: опубліковані превʼю з коментарями модуля

**Files:** `app/serve.py` (`build_preview`, `publish_with_module`, `_publish_by_url`); тести `tests/test_publish_module.py`, `tests/test_comments_role.py`.

- `build_preview(task, tid, its, *, comments, gate_pw)`: `comments` приймає `True` (ЛІГА, як було), `False`, або `{'module': id, 'files': [...], 'config': {...}}`; для модуля — копіює `comment-layer.min.js` і файли адаптера в `publish/comment-layer/`, у сторінки — той самий модульний сніпет з відносними шляхами (`depth_up`), каналом задачі й `client_config`.
- `publish_with_module` (обидві гілки): якщо в просторі постачальник `comments` — модуль, збирає з його коментарями; інакше `comments=False` як було.
- [ ] Тести: збірка з модулем (файли є, сніпет з відносними шляхами, без непублічних секретів, канал), ЛІГА-збірка побайтно та сама, без модуля — як 0.3.0; `/published/…` роздає файли адаптера (CSP/ACAO як було). Мутації: секрет у збірці; ЛІГА отримує модульний сніпет.
- [ ] Коміт `feat(publish): превʼю з коментарями модуля comments`.

### Task 4: агент читає й закриває коментарі через модуль

**Files:** `bin/inbox.py` (`supabase_pins`/`patch_project_pin`), `app/serve.py` (`supabase_pins` ~:1976, маршрут `/comments` ~:4943); тести `bin/test_inbox*.py`/`tests/test_inbox.py`.

- Для простору з модулем: `list(ctx, channel)` замість REST до зашитого Supabase; `resolve(ctx, channel, id, reason)` замість `PATCH`; канал — `channel_for`. `'legacy'` — як було (побайтно). `None` — лише локальні, як було.
- Форма елемента, яку чекає `inbox`, — та сама, що з REST (перетворення з форми CommentLayer у місці виклику).
- [ ] Тести на фікстурі `memo-comments` (її сервер у процесі): `inbox` бачить і закриває проєктні коментарі; ЛІГА-шлях без змін (наявні тести зелені без правок); мережа — лише `127.0.0.1`. Мутації: `inbox` іде в зашитий REST для модульного простору.
- [ ] Коміт `feat(comments): агент читає й закриває коментарі через модуль`.

### Task 5: модуль `supabase-comments`

**Files:** `app/modules/supabase-comments/{module.json,server.py,adapter.js,supabase.min.js,schema.sql,LICENSE-supabase-js}` (нові); `tests/test_supabase_comments.py`, `tests/supabase-adapter-module.test.mjs` (нові).

- `supabase.min.js` — копія `comment-layer/node_modules/@supabase/supabase-js/dist/umd/supabase.js` (2.110.0) без змін + `LICENSE-supabase-js` (MIT, текст з пакета); у тесті — SHA-256 файла приколоти.
- `schema.sql` — з `comment-layer/supabase/schema.sql` (перевірити, що без імен/хостів).
- `adapter.js` — `DeaiComments.create(cfg)`: `supabase.createClient(cfg.url, cfg.key)`, логіка `CommentLayerSupabase` (форма рядків, повтори `upsert`, видалення з фільтром каналу, realtime → перечитування).
- `server.py` — як у спеці (REST, `check` з кодами `bad-key`/`no-schema`/`network`, ключ лише в заголовках до `url`, `https`-only, без переходів за редиректами).
- [ ] Тести: підставний REST Supabase в процесі (`list`, `resolve`, `check` усі гілки, ключ лише в заголовках, редирект не слідується, `http://` → відмова); node: адаптер проти підставного `supabase` (форма рядків, повтори, фільтр каналу при видаленні, `subscribe`). Мутації: ключ у тексті помилки; видалення без фільтра каналу; редирект слідується.
- [ ] Коміт `feat(modules): supabase-comments — свої коментарі на Supabase`.

### Task 6: документ для авторів модулів, живий тест, 0.4.0

**Files:** `docs/modules/comments.md` (новий), `tests/live/comments.test.mjs` (новий, `PORT_BASE` — вільна смуга), `CHANGELOG.md`, `README.md`, `package.json` (`0.4.0`), `docs/design/spaces-and-modules.md`, спека (відхилення).

- `docs/modules/comments.md`: контракт обох половин, форма коментаря, канал, `public`, мінімальний приклад (на основі `memo-comments`), як перевірити.
- Живий тест (сервер із `DEAI_EXTRA_MODULES=tests/fixtures/modules`, сервер `memo` на `127.0.0.1`): увімкнути `memo-comments` через API → пін у канвасі (вкладка «Команда») → його видно на «Огляді» → публікація `static-publish` → пін видно в `/published/…`; простір ЛІГА — без змін; жодного запиту за межі localhost.
- README: розділ «Comments» (роль, Supabase: схема, ключ, увімкнення через API; свій модуль — посилання на документ), CHANGELOG 0.4.0 з точними числами.
- [ ] `node --test --test-concurrency=1 tests/live/comments.test.mjs tests/live/vercel.test.mjs tests/live/modules.test.mjs tests/live/spaces.test.mjs` → PASS; `npm test` зелений; коміти `test(comments): …`, `docs: 0.4.0 — універсальні коментарі (2b-2)`.

---

## Після плану

- Ревʼю кожної задачі (одне коло), фінальне ревʼю `v0.3.0..HEAD`, тег `v0.4.0`, пуш `main` і тегу.
