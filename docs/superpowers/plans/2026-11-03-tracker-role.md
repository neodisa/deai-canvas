# Етап 4c-2 «Статуси трекера як роль» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** роль `tracker` у ядрі й вбудований модуль `jira-tracker`; статуси задач — і в синку дашборда (будь-який простір із
трекером), і на екрані «Задачі» напряму; ЛІГА — через той самий модуль як неявний постачальник з адресою `jira_base` у
`tasks.json`. Реліз 0.13.0.

**Architecture:** нове ядро `app/tracker.py` (без імпорту `serve`) фільтрує ключі, ділить на пакети по 100, кличе
`statuses(ctx, keys)` модуля й нормалізує відповідь; модуль лише ходить у трекер. Постачальник —
`deai_modules.provider('tracker')`: модуль простору або `'legacy'` (ЛІГА), для якого `ctx` будує ядро з конфігу установки
(`install_config.jira_config()`). Синк дашборда отримує колбек `statuses` від CLI; екран «Задачі» — через кеш на простір
`tracker_snapshot` у `serve.py`.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-03-tracker-role-design.md`. Читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  Рядок `Co-Authored-By` — рівно такий (Opus 5.5). Коміт — лише з переліком шляхів; новий файл спершу `git add -- <шлях>`.
- **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md`.

**Прогони й середовище**

- Кожен прогін — через охоронця памʼяті `python3 "$G" <секунд> <МБ> <команда…>` (шлях `$G` дає контролер).
- Не виставляти `DEAI_HOME`; не чіпати порти 8765/4317, справжні `~/.deai`, `~/deai-published`, `~/.gitconfig`, `tasks.json`
  дизайнера, `~/.claude/pipeline-feedback/` (файли облікових Jira в тестах — у тимчасовому `HOME`). Процеси — лише за PID.
- **Жодної мережі в тестах.** Jira, Supabase, GitLab — лише заглушки (`mock.patch` шва `_open` модуля, `DC_TRACKER_FAKE`,
  `DC_TEAM_FAKE`). Ізоляцію `DC_TASKS_FILE`/`DC_NO_OVERVIEW` не послаблювати.
- Знеособлено: лише вигадані значення (`https://demo.atlassian.example`, `alpha@example.com`, токен `tok-test-1`, ключі
  `DEMO-1`, `DEMO-2`).

**Конвенції коду**

- Коментарі українською, у стилі навколишнього коду; ⛔-уроки переносяться разом із кодом, не губляться.
- Тексти інтерфейсу лише через `t()` з UK і EN (`app/i18n.js`); дані в розмітку — лише через `esc()`.
- Python 3.9: без `match`, без `X | Y` в анотаціях.

**Еталони й мутації**

- `tests/legacy-golden.test.mjs` і `GoldenPinTest` — зелені БЕЗ `UPDATE_*`.
- Кожна нова перевірка доводиться мутацією (один рядок → потрібний тест червоніє → файл відновлено побайтно, sha256).
  Мутації Python — лише `python3 -B`, з охоронцем, по одній.

**Набори тестів:** юніти — `npm test`; живі — лише послідовно `node --test --test-concurrency=1 tests/live/<файл>`.
Номери рядків — орієнтир («≈»). Кожна зміна наявного тесту — у звіті одним рядком із причиною.

---

## Структура файлів

| Файл | Що змінюється |
|---|---|
| `tests/fixtures/tracker/before-4c2.json` (новий), `tests/make_before_4c2.py` (новий) | знімок 0.12.0: запит `jira_statuses`, картки синку ЛІГИ, `/api/tasks-overview` ЛІГИ (Task 1) |
| `app/deai_modules.py` | роль `tracker`: `ROLES_CALLED`, `ROLES_RESERVED`, `ROLE_FUNCTIONS`, `LEGACY_ROLES`, `STRICT_LEGACY_ROLES`, `STATUS`, `KNOWN_OTHER_MODULES`, докстрінги |
| `app/tracker.py` (новий) | `KEY_RE`, `keys_of`, `normalize`, `statuses`, `legacy_ctx`, `legacy_module`, константи |
| `app/install_config.py` | `jira_config()` |
| `app/modules/jira-tracker/` (нова) | `module.json`, `server.py`, `README.md` |
| `bin/overview_push.py` | Jira-код геть; колбек `statuses` з постачальника `tracker` простору |
| `app/dashboard.py` | `sync`: збій `statuses` → рядок у лог |
| `app/serve.py` | `tracker_resolve`, `_tracker_fetch`, `tracker_snapshot`, `tasks_overview(…, tracker=…)`, `/api/tasks-overview` |
| `app/tasks-home.js`, `app/i18n.js` | банер «Трекер недоступний» над «Моїми» |
| `app/connections-model.js`, `app/i18n.js` | роль `tracker` на «Підключенні» й у майстрі; `BUILTIN_TEXT["jira-tracker"]` |
| `tests/test_tracker.py` (новий), `tests/test_tracker_module.py` (новий) | ядро й модуль |
| `tests/fixtures/tracker/fake-tracker/` (нова), `tests/live/tracker-role.test.mjs` (новий) | живі |
| `docs/modules/authoring.md`, `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json` | Task 8 |

---

### Task 1: знімок 0.12.0 (до змін коду)

**Files:** Create `tests/make_before_4c2.py` (генератор; лишається в репо, як `make_before_4c1.py`),
`tests/fixtures/tracker/before-4c2.json`; тест-читач `tests/test_tracker.py` (клас `Before4c2Shape` — файл є, має ключі
`jira_request`, `sync_cards`, `tasks_overview`).

- [ ] **Step 1:** генератор на HEAD без змін коду (зразок — `tests/make_before_4c1.py`), усе на заглушках:
  - `jira_request`: `overview_push.jira_statuses(["DEMO-1", "DEMO-2", "DEMO-1", "", None])` з `JIRA_EMAIL=alpha@example.com`,
    `JIRA_TOKEN=tok-test-1` в оточенні (тимчасовий `HOME`), `urllib.request.urlopen` підмінено: записати метод, шлях URL
    (без хоста — хост `_JIRA_BASE` у знімок не йде), тіло (JSON), заголовки (`Authorization` → `"<basic>"`, якщо є),
    тайм-аут; відповідь-заглушка `{"issues": [{"key": "DEMO-1", "fields": {"status": {"name": "In Review",
    "statusCategory": {"key": "indeterminate"}}}}, {"key": "DEMO-2", "fields": {"status": {"name": "Done",
    "statusCategory": {"key": "done"}}}}]}` → записати результат. Плюс: без облікових → `{}` і жодного `urlopen`;
    `urlopen` кидає `OSError` → `{}`.
  - `sync_cards`: `dashboard.sync(cfg, fake_module, ctx, statuses=<заглушка з результатом вище>, identity=("Alpha",
    "alpha@example.com"), log=<список>, call=<запис push>)` на фікстурі з двома задачами з теками в tmp (`jira: "DEMO-1"`,
    `jira: "DEMO-2"`) → список `(mode, картки без synced_at/updated_at/jira_synced_at)` і рядки логу.
  - `tasks_overview`: ЛІГА на `DC_TEAM_FAKE` (рядок `t1` з `jira_status: "In Review"`, `jira_status_cat: "indeterminate"`)
    і `DC_TASKS_FILE` → тіло `/api/tasks-overview` без часових полів (`fetchedAt`, `rowsAt`, `changed`) — зразок
    `team_read` у `make_before_4c1.py`.
- [ ] **Step 2:** запустити генератор, закомітити JSON + генератор + `Before4c2Shape`. Жодних змін в `app/` чи `bin/`.

---

### Task 2: роль `tracker` у каркасі модулів і ядро `app/tracker.py`

**Files:** Modify `app/deai_modules.py` (≈102–170, ≈1705, докстрінги `provider`/`capabilities`), `app/install_config.py`;
Create `app/tracker.py`; Test `tests/test_tracker.py` (`TrackerRole`, `TrackerCore`, `JiraConfig`), `tests/test_modules.py`
(≈334, ≈457–460).

- [ ] **Step 1: Падаючі тести:**
  - `dm.ROLES_CALLED == ('publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker')`, `dm.ROLES_RESERVED == ('notify',)`
    (оновити `test_modules.py:334`; `:457–460` — маніфест «reserved» тепер лише з `notify`, причина: `tracker` викликана);
  - маніфест з `roles: ["tracker"]` без `statuses` → `bad-manifest`; з нею — `ok`;
  - простір з `integrations: true` без модуля → `provider('tracker', space) == 'legacy'`; без інтеграцій і без модуля →
    `None`; `capabilities(space)['tracker']` — те саме; при `ModuleError` у просторі з інтеграціями → `None` (не `'legacy'`);
    зламаний `space.json` у просторі з інтеграціями → `space-json-unreadable`, не `'legacy'` (`STRICT_LEGACY_ROLES`);
  - `STATUS['tracker-unconfigured'] == 409`, `STATUS['tracker-error'] == 502`; `'jira-tracker' in dm.KNOWN_OTHER_MODULES`;
  - `tracker.KEY_RE`: так — `DEMO-1`, `AB_2-10`; ні — `demo-1`, `DEMO-0`, `DEMO-01`, `-1`, `DEMO 1`, `DEMO-1) OR (x`, ключ
    довший за 32 знаки до дефіса, не-рядок;
  - `tracker.keys_of({'a': {'jira': 'DEMO-2'}, 'b': {'jira': 'DEMO-1'}, 'c': {'jira': 'DEMO-2'}, 'd': {'jira': 'bad'},
    'e': {}, 'f': {'jira': ['DEMO-3']}})` → `['DEMO-2', 'DEMO-1']`;
  - `tracker.normalize(data, keys)`: лише запитані ключі; `name` обрізано до 80, керівні символи → запис відкинуто,
    порожній/не рядок → відкинуто; `cat` поза `('new', 'indeterminate', 'done')` → `None`; не словник → `ValueError`;
  - `tracker.statuses(module, ctx, keys, timeout=6, socket_s=4, call=fake)`: сміття відкинуто ДО виклику (fake не бачить
    `bad`); 250 ключів → 3 виклики по ≤100; `ctx` кожного виклику має `timeout_s == 4`, а вихідний `ctx` не змінено;
    `fake` кличеться як `call(module, 'statuses', ctx2, chunk, timeout=6)`; жодного валідного ключа → `{}` без виклику;
    збій пакета (`ModuleError`) → піднімається вгору;
  - `install_config.jira_config()`: `jira_base` у `tasks.json` + `JIRA_EMAIL`/`JIRA_TOKEN` в оточенні → трійка (база без
    `/` у кінці); облікові з файлів `<HOME>/.claude/pipeline-feedback/jira-email|jira-token`, коли оточення нема; оточення
    раніше за файли; нема `jira_base`, база не https / з шляхом / з `user@` / заготовка `https://<сайт>.atlassian.net` →
    `(None, None, None)`; токен із пробілом → `(None, None, None)`; `tasks.json` битий → `(None, None, None)` без винятку.
- [ ] **Step 2: Реалізація:**
  ```python
  # app/deai_modules.py
  ROLES_CALLED = ('publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker')
  ROLES_RESERVED = ('notify',)
  ROLE_FUNCTIONS = {..., 'tracker': ('statuses',)}
  LEGACY_ROLES = ('publish', 'comments', 'vcs', 'dashboard', 'tracker')
  # LEGACY_ON_ERROR_ROLES НЕ змінюється: зашитий шлях трекера — сайт Jira ЛІГИ, не локальний
  STRICT_LEGACY_ROLES = ('comments', 'dashboard', 'tracker')
  STATUS[...]: 'tracker-unconfigured': 409, 'tracker-error': 502
  KNOWN_OTHER_MODULES = frozenset({..., 'supabase-dashboard', 'jira-tracker'})
  ```
  Коментарі над `LEGACY_ON_ERROR_ROLES`/`STRICT_LEGACY_ROLES` доповнити причиною для `tracker`.
  ```python
  # app/tracker.py — ядро ролі `tracker` (етап 4c-2); БЕЗ імпорту `serve` (як `app/dashboard.py`)
  KEY_RE = re.compile(r'[A-Z][A-Z0-9_]{0,31}-[1-9][0-9]{0,9}', re.ASCII)   # fullmatch
  CATS = ('new', 'indeterminate', 'done')
  BATCH = 100
  NAME_MAX = 80
  READ_TIMEOUT, READ_SOCKET_S = 6, 4      # екран «Задачі»
  SYNC_TIMEOUT, SYNC_SOCKET_S = 30, 15    # синк дашборда
  LEGACY_MODULE = 'jira-tracker'
  UNCONFIGURED = 'Jira не налаштовано: додайте jira_base у tasks.json і облікові JIRA_EMAIL/JIRA_TOKEN'

  def keys_of(tasks): ...            # унікальні валідні `task['jira']` у порядку файла
  def normalize(data, keys): ...
  def statuses(module, ctx, keys, *, timeout, socket_s, call=None): ...
  ```
  `install_config.jira_config()` — у стилі `supabase_config()` (той самий файл через `load_legacy_tasks`, регекс адреси —
  `_SUPABASE_URL_RE`, перейменувати не треба; хост без `<`/`>` уже гарантує регекс); облікові — логіка `_jira_creds` з
  `bin/overview_push.py` (дослівно за змістом, `os.path.expanduser('~/.claude/pipeline-feedback/…')`), токен — за
  `_SUPABASE_KEY_RE`. `legacy_ctx`/`legacy_module` — у Task 3 (потрібен сам модуль).
  `docs/modules/authoring.md`: розділ «The `tracker` role» — `statuses(ctx, keys)`, `ctx['timeout_s']`, форма відповіді,
  `KEY_RE`, коди помилок; «reserved names» — лише `notify`.
- [ ] **Step 3:** мутації: `'tracker'` у `LEGACY_ON_ERROR_ROLES` → червоніє тест `ModuleError`; фільтр `KEY_RE` у
  `statuses` прибрано → червоніє «сміття до виклику»; `BATCH` ігнорується → червоніє «3 виклики». `npm test`. Коміт.

---

### Task 3: модуль `jira-tracker` і адаптер ЛІГИ

**Files:** Create `app/modules/jira-tracker/{module.json, server.py, README.md}`; Modify `app/tracker.py` (`legacy_ctx`,
`legacy_module`); Test `tests/test_tracker_module.py`, `tests/test_tracker.py` (`LegacyAdapter`).

- [ ] **Step 1: Падаючі тести** (модуль вантажиться через `deai_modules.catalog()`; мережа — `mock.patch` шва `_open` модуля):
  - `module.json`: `id: jira-tracker`, `roles: ["tracker"]`, налаштування `base` (text, required), `email` (text, required),
    `token` (secret, required, **без** `public`);
  - адреса: так — `https://demo.atlassian.example`, `https://demo.atlassian.example:8443/`; ні (→ `module-error` з текстом
    правил) — `http://…`, IP, `localhost`, одна мітка, з шляхом, з параметрами, з `user@`; email без `@` чи > 254 → відмова;
  - `check`: `GET <base>/rest/api/3/myself` з `Authorization: Basic base64(email:token)` → 200 → `True`; 401/403 → текст
    «невірний email чи токен»; 500 → текст зі статусом; мережа → текст «Jira недосяжна»;
  - `statuses(ctx, ['DEMO-1','DEMO-2'])`: `POST <base>/rest/api/3/search/jql`, тіло рівно `{"jql": "key in (DEMO-1,DEMO-2)",
    "fields": ["status"], "maxResults": 100}`, заголовки `Accept`/`Content-Type: application/json`, тайм-аут сокета =
    `ctx['timeout_s']` (не число / поза 1…30 → 4); відповідь зі знімка → `{'DEMO-1': {'name': 'In Review', 'cat':
    'indeterminate'}, 'DEMO-2': {...}}`; `issues` не масив / нема → `{}`; запис без `key`/`status` пропущено; 400 →
    `module-error` зі статусом;
  - **паритет зі знімком:** метод, шлях, тіло й набір заголовків запиту модуля = `jira_request` з `before-4c2.json`;
  - жоден текст помилки не містить токена, email, тіла запиту чи відповіді (тіло 400 з ключем `DEMO-1` → ключа в тексті
    нема); текст ≤ 200; редирект 302 не виконується (другого `_open` нема);
  - `tracker.legacy_ctx(None, None, None)` → `ModuleError('tracker-unconfigured')` з `UNCONFIGURED`;
    `legacy_ctx('https://demo.atlassian.example', 'alpha@example.com', 'tok-test-1', space_id='s')` → `settings` `{'base',
    'email'}`, `secrets` `{'token'}`, `legacy: True`; `legacy_module()` → вбудований `jira-tracker` зі статусом `ok`.
- [ ] **Step 2: Реалізація** — за зразком `app/modules/supabase-dashboard/server.py` (`_CodedError`, `_NetworkError`,
  `_NoRedirect`, `_tls` з certifi, `_opener`, `_open`, `_error`, `_host_ok`, `_clean`; скопіювати, НЕ імпортувати). Константи:
  ```python
  DEFAULT_TIMEOUT_S = 4
  MAX_TIMEOUT_S = 30
  MAX_RESULTS = 100
  MAX_BODY = 4 << 20
  MSG_MAX = 200
  ```
  Докстрінг модуля — як у `supabase-dashboard`: що робить, ключі `ctx`, шов мережі, форма запитів, ⛔ про тексти без
  токена/email/тіл. `README.md`: що робить, налаштування (як створити API-токен Atlassian — без вигаданих URL сторінок;
  «у налаштуваннях облікового запису Atlassian, розділ безпеки»), що лише Jira Cloud.
  `app/tracker.py`: `legacy_ctx(base, email, token, space_id='')` і `legacy_module()` — дзеркало `dashboard.legacy_ctx`/
  `legacy_module` (⛔ НЕ `module_ctx()` — урок 4c-1 переноситься коментарем).
- [ ] **Step 3:** мутації: `_NoRedirect` прибрано з `_opener` → червоніє тест редиректу; `_clean` не вичищає токен →
  червоніє тест текстів; `maxResults` 50 → червоніє паритет. `npm test`. Коміт.

---

### Task 4: синк дашборда через постачальника `tracker`

**Files:** Modify `bin/overview_push.py` (≈33–86, `cmd_sync` ≈180), `app/dashboard.py` (`sync` ≈355); Test
`tests/test_tracker.py` (`SyncStatuses`), `bin/test_overview_push.py` (тести `jira_statuses`/`_jira_creds`, якщо є, —
переписати на `tracker`/модуль або прибрати разом із кодом; кожну зміну — з причиною).

- [ ] **Step 1: Падаючі тести:**
  - **Диференційний `sync_cards`:** `cmd_sync` ЛІГИ (простір із `legacy`, `install_config.jira_config` →
    вигадана трійка, `_open` модуля `jira-tracker` → відповідь знімка, `dashboard`-модуль — фейк із записом `push`) дає ті
    самі картки й `mode`, що `before-4c2.json`;
  - звичайний простір з фейковим модулем трекера (тека в `DEAI_EXTRA_MODULES`) і фейковим дашбордом → `jira_status` на
    картках від трекера; без модуля трекера → `statuses=None`, жодного виклику;
  - ЛІГА без `jira_base` → `statuses=None` (мережі нема), синк іде далі;
  - трекер кидає `ModuleError` → картки без `jira_status` (не `None`!), у лозі рядок
    `⚠ overview: статуси трекера недоступні: <текст>`;
  - `grep`-тест: у `bin/overview_push.py` нема `_JIRA_BASE`, `jira_statuses`, `_jira_creds`, `urllib.request`.
- [ ] **Step 2: Реалізація:**
  - `bin/overview_push.py`: прибрати Jira-блок і `_ssl_context` (⛔-урок «токен ніколи не в git/коді/чаті — лише
    локальний файл chmod 600» перенести в докстрінг `install_config.jira_config`); новий хелпер:
    ```python
    def _statuses(sp, legacy):
        """Колбек статусів для `dashboard.sync` від постачальника ролі `tracker` простору `sp` або `None` (кроку нема)."""
    ```
    `'legacy'` → `tracker.legacy_module()` + `tracker.legacy_ctx(*install_config.jira_config(), space_id=sp['id'])`
    (`tracker-unconfigured` → `None` без мережі); модуль → `deai_modules.module_ctx(sp, prov)`; повертає
    `lambda keys: tracker.statuses(m, ctx, keys, timeout=tracker.SYNC_TIMEOUT, socket_s=tracker.SYNC_SOCKET_S)`;
    збій вирішення ролі → `None` і рядок у лог. `cmd_sync` передає `statuses=_statuses(sp, legacy)` для БУДЬ-ЯКОГО простору.
  - `app/dashboard.py`, крок 2 `sync`: `except Exception as e` → `jstatus = {}` і
    `log(f'⚠ overview: статуси трекера недоступні: {(getattr(e, "message", None) or str(e) or type(e).__name__)[:200]}')`;
    докстрінг — «статуси трекера (будь-який простір із роллю `tracker`)».
- [ ] **Step 3:** мутації: прибрати рядок у лог → червоніє; `statuses` лише для `legacy` → червоніє тест звичайного простору.
  `npm test`. Коміт.

---

### Task 5: екран «Задачі» — статуси від трекера

**Files:** Modify `app/serve.py` (біля `team_snapshot` ≈1711–1830, `tasks_overview` ≈1889, `/api/tasks-overview` ≈5631),
`app/tasks-home.js` (≈265–280), `app/i18n.js`; Test `tests/test_tasks_overview.py` (`TrackerOverview`),
`tests/tasks-home.test.mjs`.

- [ ] **Step 1: Падаючі тести:**
  - `tasks_overview(cfg, team, tracker=({'DEMO-1': {'name': 'Done', 'cat': 'done'}}, None, 100.0))`: свій `t1` з
    `jira: DEMO-1` і рядком дашборда `In Review` → `jiraStatus: 'Done'`, `jiraCat: 'done'`; задача без статусу трекера →
    з рядка дашборда; ні того, ні того → `None`; `out['tracker'] == {'error': None, 'okAt': 100.0}`; `tracker=None` →
    `out['tracker'] is None` і поведінка як у знімку; рядки «Команди» статусів трекера НЕ отримують;
  - **диференційний:** `tasks_overview` знімка (ЛІГА, `DC_TASKS_FILE`, `DC_TEAM_FAKE`) — те саме тіло + `tracker: null`
    (ізоляція: трекер ЛІГИ не кличеться, `_open` модуля не викликано);
  - `DC_TRACKER_FAKE` (JSON `{ключ: {name, cat}}`) для ЛІГИ → статуси з файла навіть в ізоляції (шов першим, як `DC_TEAM_FAKE`);
  - звичайний простір з фейковим модулем трекера, без дашборда → `team: null`, а `mine[].jiraStatus` від трекера;
  - кеш: другий запит у межах `TRACKER_TTL` модуль не кличе; новий ключ задачі, якого нема в кеші, → запит; `refresh=1` →
    запит; збій після успіху → статуси лишаються, `error` є, `okAt` — час успіху; помилка кешується `TRACKER_ERR_TTL`;
    інший постачальник (`who`) → чистий запис; кеш простору A не видно в просторі B; `_TRACKER_LOCK` — окремий від `_TEAM_LOCK`
    (`assertIsNot`);
  - ЛІГА без `jira_base` (не в ізоляції) → `tracker.error` = `UNCONFIGURED`, мережі нема; зламаний свій модуль «на папері»
    (`ModuleError` у `tracker_resolve`) → `tracker: {'error': текст, 'okAt': None}`;
  - JS (`tasks-home.test.mjs`): «Мої» з `tracker: {error: 'x', okAt: 1700000000}` → банер `thTrackerErr` + `thStale` з
    часом; `okAt: null` → банер без часу; `tracker: null` чи `error: null` → банера нема; на вкладці «Команда» банера
    трекера нема; текст помилки з `<b>` екрановано.
- [ ] **Step 2: Реалізація** (`app/serve.py`, поруч із `team_snapshot`, той самий стиль і ⛔-коментарі):
  ```python
  TRACKER_TTL = 300
  TRACKER_ERR_TTL = 30
  #: Кеш статусів трекера НА ПРОСТІР: `{id: {'at', 'statuses', 'error', 'okAt', 'who', 'keys'}}`.
  _TRACKER_CACHE = {}
  _TRACKER_LOCK = threading.Lock()     # ⛔ окремий від `_TEAM_LOCK`: мертвий Jira не тримає рядки команди

  def tracker_resolve(): ...            # `(space, prov)` ролі `tracker`, як `team_resolve`
  def _tracker_fetch(space, prov, keys): ...   # `(statuses, error)` або `None` (= трекера нема: ізоляція ЛІГИ); не кидає
  def tracker_snapshot(keys, now=None, refresh=False, resolved=None): ...   # `None` | `(statuses, error, ok_at)`
  ```
  `_tracker_fetch` для `'legacy'`: `DC_TRACKER_FAKE` → файл (`normalize` до `keys`); `DC_TASKS_FILE`/`DC_NO_OVERVIEW` →
  `None`; інакше `tracker.legacy_ctx(*install_config.jira_config(), space_id=…)` (через тонку обгортку `serve.jira_config`,
  як `supabase_config` — точка підміни для тестів); модуль → `module_ctx`. Виклик — `tracker.statuses(…,
  timeout=tracker.READ_TIMEOUT, socket_s=tracker.READ_SOCKET_S)` для перших 100 ключів. Помилки — як `_team_fetch`.
  `tasks_overview(cfg, team, now=None, rows_at=None, tracker=None)` — пріоритет трекер → рядок → `None`; поле `tracker`.
  `/api/tasks-overview`: `keys = tracker.keys_of(cfg['tasks'])`, `tracker_snapshot(keys, refresh=…)`; гілка `NoTask` →
  `'tracker': None`.
  `app/tasks-home.js`: на «Моїх» (`!team`) — `bannerHTML(t("thTrackerErr", err), okAt ? t("thStale", clock(okAt)) : "")`;
  i18n UK/EN `thTrackerErr`: «Трекер недоступний: {…}» / "Issue tracker unavailable: {…}" (плейсхолдер — як у `thTeamErr`).
- [ ] **Step 3:** мутації: прибрати ізоляцію для `'legacy'` → червоніє диференційний; кеш без ключа простору → червоніє;
  збій стирає статуси → червоніє; пріоритет дашборд → трекер → червоніє. `npm test`. Коміт.

---

### Task 6: «Підключення» й майстер — роль `tracker`

**Files:** Modify `app/connections-model.js` (≈20–55, ≈289), `app/i18n.js`; Test `tests/connections-model.test.mjs` (≈22,
≈30, ≈51–57, ≈71, ≈310), `tests/connections-view.test.mjs` (≈90, ≈98, ≈146), тест майстра (`grep -ln ROLE_ORDER tests`).

- [ ] **Step 1: Падаючі тести:** `ROLE_ORDER` = `["publish", "comments", "vcs", "dashboard", "tracker", "tokens"]`;
  `roleKeys("tracker")` → `{title: "cnRoleTracker", lead: "cnRoleTrackerLead", none: "cnNoneTracker"}`; `roleIcon("tracker")`
  — іконка з наявного набору `icons.js` (нову не малювати; назвати у звіті); `BUILTIN_TEXT["jira-tracker"]` з полями
  `base`/`email`/`token`; `LEGACY_ROLES` клієнта має `tracker` → у ЛІГИ `kind: 'legacy'` з наслідком вимкнення; i18n UK/EN
  мають усі нові ключі. Наявні тести, що брали `tracker` як «роль без текстів/невідому», переписати на `notify` (причина:
  `tracker` тепер викликана) — кожен рядок у звіті.
- [ ] **Step 2: Реалізація** — ключі UK/EN: `cnRoleTracker` («Трекер задач» / "Issue tracker"), `cnRoleTrackerLead`
  («Статуси задач із трекера — на екрані «Задачі» й у командному дашборді.» / "Task statuses from your issue tracker — on
  the Tasks screen and in the team dashboard."), `cnNoneTracker` («Без трекера — статусів задач нема.» / "No tracker — no
  task statuses."), `cnModJiraName` («Jira Cloud» / "Jira Cloud"), `cnModJiraDesc`, `cnFieldJiraBase` («Адреса сайту Jira
  (https://<сайт>.atlassian.net)» / "Jira site address (https://<site>.atlassian.net)"), `cnFieldJiraEmail`,
  `cnFieldJiraToken` («API-токен Atlassian» / "Atlassian API token"), і текст наслідку вимкнення («статуси задач зникнуть з
  екрана «Задачі» й перестануть оновлюватись у дашборді»).
- [ ] **Step 3:** `npm test`; мутація: `tracker` геть з `LEGACY_ROLES` клієнта → червоніє. Коміт.

---

### Task 7: живі тести

**Files:** Create `tests/fixtures/tracker/fake-tracker/{module.json, server.py}` (віддає статуси з JSON-файла поруч, шлях —
з налаштування; режим «збій» — коли у файлі `{"error": "…"}`), `tests/live/tracker-role.test.mjs` (`PORT_BASE` — вільний,
не 14000; зразок — `tests/live/dashboard-role.test.mjs`, зокрема прибирання тимчасових тек і `.gitignore`).

- [ ] Спершу прогнати наявні `tasks-home`, `connections`, `dashboard-role` як є — список падінь.
- [ ] Сценарії: (1) звичайний простір без трекера — бейджів статусу нема, банера нема; (2) той самий простір з увімкненим
  фейковим трекером, без дашборда — бейджі статусів на картках «Моїх»; (3) трекер у режимі «збій» після успіху →
  банер «Трекер недоступний…» з часом, бейджі лишились; (4) «Підключення» — картка ролі «Трекер задач», модуль у ній;
  (5) ЛІГА з `DC_TASKS_FILE` + `DC_TEAM_FAKE` — як у знімку, банера трекера нема.
- [ ] Кожен змінений живий файл — по одному; потім `npm test`. Коміт.

---

### Task 8: документи й версія 0.13.0

- [ ] `CHANGELOG.md` — `## [0.13.0] — невипущено` у стилі `[0.12.0]` (англійською): Added (роль `tracker`, модуль
  `jira-tracker`, статуси на екрані «Задачі» без дашборда, банер, картка на «Підключенні»), Changed (ЛІГА — через модуль,
  адреса з `jira_base`; синк бере статуси в будь-якого простору з трекером; збій трекера в лозі; ключі поза `KEY_RE` не
  йдуть у трекер), Removed (Jira-код з `overview_push.py`), «Upgrading» (ЛІГА: **додати `jira_base` у `tasks.json`**,
  облікові — як були), «Known limits» (зі спеки + відхилення реалізації).
- [ ] `README.md` — трекер у звичайному просторі. `docs/design/spaces-and-modules.md` — «Stage 4c-2», шапка, таблиця ролей,
  «What stays for later» (лишається `notify`). `docs/modules/authoring.md` — звірити з Task 2. `app/modules/jira-tracker/README.md` — звірити.
- [ ] `package.json` 0.13.0; `npm test`; коміт.

---

## Після всіх задач (контролер)

1. Фінальне ревʼю всієї гілки від коміту спеки (`9219dad`).
2. Повні прогони на знімку: `npm test`; `/usr/bin/python3` 3.9.6; живі — по одному (`inspector-ds` 2/4 — стара червона;
   `dashboard-role` тест 6 — артефакт знімка в `/tmp`, перевіряти в робочій теці).
3. Дата в CHANGELOG → тег `v0.13.0` (анотований, neodisa) → `git push origin <sha>:refs/heads/main` і тег → звірити віддалений sha.
4. Памʼять, статус пайплайна, звіт власнику.
