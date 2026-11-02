# Етап 4c-1 «Командний дашборд як роль» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** роль `dashboard` у ядрі й вбудований модуль `supabase-dashboard`; простір ЛІГА веде вкладку «Команда» й синк
карток через цей модуль як неявний постачальник; збирання карток — у `app/dashboard.py`. Реліз 0.12.0.

**Architecture:** ядро (`app/dashboard.py`) збирає картки й веде синк, модуль лише читає рядки (`rows`) і пише картки
(`push`). Постачальник ролі — `deai_modules.provider('dashboard')`: модуль простору або `'legacy'` (ЛІГА), для якого `ctx`
будує ядро з конфігу установки (`install_config.supabase_config()`), таблиця `overview_projects`. Кроки ЛІГИ, що ще не
стали ролями (реєстр GitLab, статуси Jira), передаються в синк колбеками адаптера.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-02-dashboard-role-design.md`. Читати перед кожною задачею.

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
  дизайнера, `~/.claude/pipeline-feedback/` (лог синку в тестах — у тимчасовій теці через шов). Процеси — лише за PID.
- **Жодної мережі в тестах.** Supabase, Jira, GitLab — лише заглушки (`mock.patch` `urlopen`/`Popen`, `DC_TEAM_FAKE`).
  Ізоляцію `DC_TASKS_FILE`/`DC_NO_OVERVIEW` не послаблювати — лише переносити разом із кодом.
- Знеособлено: лише вигадані значення (`https://demo.supabase.example`, ключі `sk-test-…`/`pk-test-…`, дизайнер `Alpha`,
  пошта `alpha@example.com`).

**Конвенції коду**

- Коментарі українською, у стилі навколишнього коду; ⛔-уроки переносяться разом із кодом, не губляться.
- Тексти інтерфейсу лише через `t()` з UK і EN (`app/i18n.js`); дані в розмітку — лише через `esc()`.
- Python 3.9: без `match`, без `X | Y` в анотаціях.

**Еталони й мутації**

- `tests/legacy-golden.test.mjs` і `GoldenPinTest` — зелені БЕЗ `UPDATE_*`.
- Кожна нова перевірка доводиться мутацією (один рядок → потрібний тест червоніє → файл відновлено побайтно, sha256).
  Мутації Python — лише `python3 -B`, з охоронцем, по одній.

**Набори тестів:** юніти — `npm test`; живі — лише послідовно `node --test --test-concurrency=1 tests/live/<файл>`.
Номери рядків — орієнтир («≈»).

---

## Структура файлів

| Файл | Що змінюється |
|---|---|
| `tests/fixtures/dashboard/before-4c1.json` (новий) | знімок 0.11.0: відповіді `/api/tasks-overview`, тіла upsert синку, гейти `_overview_sync` (Task 1) |
| `app/install_config.py` (новий) | `legacy_tasks_path`, `load_legacy_tasks`, `supabase_config` — переїзд із `serve.py` (без імпорту `serve`) |
| `app/dashboard.py` (новий) | збирання карток (з `bin/overview_push.py`), `legacy_ctx`, `normalize_rows`, `sync`, `rows` |
| `app/deai_modules.py` | роль `dashboard`: `ROLES_CALLED`, `ROLE_FUNCTIONS`, `ROLE_OPTIONAL_FUNCTIONS`, `LEGACY_ROLES`, `STATUS`, `KNOWN_OTHER_MODULES` |
| `app/modules/supabase-dashboard/` (нова) | `module.json`, `server.py`, `schema.sql`, `README.md` |
| `app/serve.py` | реекспорт `install_config`; `team_snapshot` через постачальника й кеш на простір; `/api/tasks-overview`; `_overview_sync` (гейт ролі, один на простір) |
| `bin/overview_push.py` | тонкий CLI над `app/dashboard.py` (`sync [--space ID]`, `discover`); Jira й реєстр — колбеки ЛІГИ |
| `app/connections-model.js`, `app/i18n.js` | роль `dashboard` на «Підключенні» й у майстрі; модуль `supabase-dashboard` у `BUILTIN_TEXT` |
| `tests/test_dashboard.py` (новий), `tests/test_dashboard_module.py` (новий) | ядро й модуль |
| `tests/live/tasks-home.test.mjs`, `tests/live/connections*.test.mjs` | живі |
| `docs/modules/authoring.md`, `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json` | Task 9 |

---

### Task 1: знімок 0.11.0 (до змін коду)

**Files:** Create `tests/fixtures/dashboard/before-4c1.json`, `tests/make_before_4c1.py` (генератор; лишається в репо, як
`before-4b2`), тест-читач у `tests/test_dashboard.py` (клас `Before4c1Shape` — лише перевіряє, що файл є й має ключі).

- [ ] **Step 1:** генератор на HEAD без змін коду, усе на заглушках:
  - `team_read`: (1) `DC_TEAM_FAKE` з трьома рядками (свій `t1` з `jira_status: "In Review"`, `jira_status_cat: "indeterminate"`,
    `open_comments: 2`; чужий `x9`; рядок без `id`) → тіло `/api/tasks-overview` (без часових полів: `fetchedAt`, `rowsAt`,
    `changed` — вирізати); (2) без шва, `supabase_config` → `('https://demo.supabase.example', 'pk-test-1')`, `urlopen`
    підмінено: записати `url`, заголовки (значення ключа замінити на `<key>`), тайм-аут; (3) `integrations: false` →
    `team: null` і жодного виклику `urlopen`.
  - `sync_push`: `bin/overview_push.py cmd_sync()` на фікстурі `tasks.json` (дві задачі з теками в tmp, одна без теки, одна
    фікстура-тимчасова), реєстр (`discover_projects`) — заглушка з одним записом, `open_comment_counts` → `{"dc/t1": 1}`,
    `jira_statuses` → `{"LIGA-1": {"name": "Done", "cat": "done"}}`, `upsert_project` підмінено записом `(row, ignore)`.
    Зберегти список `(row без synced_at/updated_at/jira_synced_at, ignore)` у порядку викликів; `_identity` → `("Alpha",
    "alpha@example.com")`.
  - `sync_gate`: для `_overview_sync` записати, чи стартував `Popen` (і з якими `argv` без абсолютних шляхів), у випадках:
    integrations on + конфіг є; `integrations: false`; `DC_NO_OVERVIEW=1`; конфігу нема.
- [ ] **Step 2:** запустити генератор, закомітити JSON + генератор + `Before4c1Shape`. Жодних змін у `app/` чи `bin/`.

---

### Task 2: `install_config.py` і `dashboard.py` — переїзд без зміни поведінки

**Files:** Create `app/install_config.py`, `app/dashboard.py`; Modify `app/serve.py` (≈130–160, ≈420–432), `bin/overview_push.py`;
Test `tests/test_dashboard.py` (`CardsParity`), `bin/test_overview_push.py` (без змін — мусить лишитись зеленим через реекспорт).

- [ ] **Step 1: Падаючі тести** (`tests/test_dashboard.py`):
  - `import install_config, dashboard` (шлях `app/`), `install_config.supabase_config` поводиться як `serve.supabase_config`
    (файл раніше за оточення, пара цілою, заготовки відкидаються) — перенести наявні кейси `SupabaseConfigTest` параметризовано
    на обидва імені;
  - `dashboard` НЕ імпортує `serve` (`'serve' not in sys.modules` після свіжого `importlib.import_module('dashboard')` у
    підпроцесі `python3 -c`);
  - **паритет карток:** на тих самих даних, що `sync_push` Task 1, `dashboard.build_card`/`discover_card`/`card_has_pii`/
    `map_status` дають ті самі рядки, що `before-4c1.json` (порівняння без часових полів).
- [ ] **Step 2: Реалізація:**
  - `app/install_config.py`: перенести `_SUPABASE_URL_RE`, `_SUPABASE_KEY_RE`, `legacy_tasks_path`, `load_legacy_tasks`,
    `supabase_config` з `serve.py` дослівно (докстрінги теж; імпорт `spaces`). У `serve.py`:
    ```python
    from install_config import legacy_tasks_path, load_legacy_tasks  # noqa: F401 — конфіг установки (4c-1: спільний із CLI)
    import install_config
    def supabase_config():
        """Тонка обгортка (`install_config.supabase_config`): ім'я в `serve` лишається точкою підміни для тестів."""
        return install_config.supabase_config()
    ```
    (`profile_repos` лишається в `serve`, кличе `load_legacy_tasks` як і раніше.)
  - `app/dashboard.py`: перенести з `bin/overview_push.py` дослівно `_PII`, `_GL_SSH`, `_GL_BRANCH`, `gitlab_web`, `to_iso`,
    `map_status`, `preview_source`, `build_row`→`build_card`, `row_has_pii`→`card_has_pii`, `discover_row`→`discover_card`,
    `_humanize`, `comment_project_key`, `_identity`, `_fixture_reason`/`_drop_fixtures` (вони кличуть `registry` — імпорт
    `bin/registry.py` лишається ледачим, як у `_registry()`). У `overview_push.py` — реекспорт старих імен:
    ```python
    from dashboard import (gitlab_web, to_iso, map_status, preview_source, comment_project_key, _identity,  # noqa: F401
                           _humanize, _fixture_reason, _drop_fixtures)
    from dashboard import build_card as build_row, card_has_pii as row_has_pii, discover_card as discover_row  # noqa: F401
    ```
- [ ] **Step 3:** `npm test` зелений (зокрема `bin/test_overview_push.py`, `tests/test_legacy_comments.py`). Мутація:
  `install_config.supabase_config` бере оточення раніше за файл → червоніє перенесений кейс. Коміт.

---

### Task 3: роль `dashboard` у каркасі модулів

**Files:** Modify `app/deai_modules.py` (≈102–160, ≈1696), `docs/modules/authoring.md` (розділ «Role `dashboard`»);
Test `tests/test_modules.py` (≈331, ≈455), новий клас `DashboardRole` у `tests/test_dashboard.py`.

- [ ] **Step 1: Падаючі тести:**
  - `dm.ROLES_CALLED == ('publish', 'tokens', 'comments', 'vcs', 'dashboard')`, `dm.ROLES_RESERVED == ('tracker', 'notify')`
    (оновити два наявні рядки в `test_modules.py` — причина: роль стала викликаною);
  - маніфест з `roles: ["dashboard"]` без `rows`/`push` → `bad-manifest`; з ними — `ok`; `open_comments` необовʼязковий;
  - простір з `integrations: true` без явних модулів → `provider('dashboard', space) == 'legacy'`; без інтеграцій і без
    модуля → `None`; `capabilities(space)['dashboard']` — те саме; при `ModuleError` у просторі з інтеграціями →
    `None` (НЕ `'legacy'`), `error` виставлено;
  - `'dashboard-unconfigured'` → 409, `'dashboard-error'` → 502 у `STATUS`;
  - `'supabase-dashboard' in dm.KNOWN_OTHER_MODULES` (інваріант `tests/test_comments_role.py` лишається зеленим).
- [ ] **Step 2: Реалізація:**
  ```python
  ROLES_CALLED = ('publish', 'tokens', 'comments', 'vcs', 'dashboard')
  ROLES_RESERVED = ('tracker', 'notify')
  ROLE_FUNCTIONS = {..., 'dashboard': ('rows', 'push')}
  ROLE_OPTIONAL_FUNCTIONS = {'vcs': ('validate', 'mirror_dir'), 'dashboard': ('open_comments',)}
  LEGACY_ROLES = ('publish', 'comments', 'vcs', 'dashboard')
  # LEGACY_ON_ERROR_ROLES НЕ змінюється: зашитий шлях дашборда — спільний Supabase ЛІГИ (як comments)
  STATUS[...]: 'dashboard-unconfigured': 409, 'dashboard-error': 502
  KNOWN_OTHER_MODULES = frozenset({'css-tokens', 'git-sync', 'static-publish', 'vercel-publish', 'supabase-dashboard'})
  ```
  Оновити докстрінги `provider`/`capabilities`/`LEGACY_ROLES` (перелік ролей). `docs/modules/authoring.md`: контракт `rows`,
  `push(ctx, cards, mode)` (`merge`|`insert`, повертає `{'ok': n, 'failed': {id: text}}`), `open_comments`, ключі `TEAM_KEYS`,
  коди помилок; рядок «reserved names» — лише `tracker`, `notify`.
- [ ] **Step 3:** мутації: `'dashboard'` додано в `LEGACY_ON_ERROR_ROLES` → червоніє тест помилки; `ROLE_FUNCTIONS` без
  `push` → червоніє тест маніфесту. `npm test`. Коміт.

---

### Task 4: модуль `supabase-dashboard`

**Files:** Create `app/modules/supabase-dashboard/{module.json, server.py, schema.sql, README.md}`;
Test `tests/test_dashboard_module.py`.

- [ ] **Step 1: Падаючі тести** (модуль вантажиться через `deai_modules.catalog()`; мережа — `mock.patch` `urlopen` модуля):
  - `module.json`: `id: supabase-dashboard`, `roles: ["dashboard"]`, налаштування `url` (text, required), `key` (secret,
    required, **без** `public`), `table` (text, не required);
  - `check`: погана адреса → `module-error` з текстом правил адреси (ті самі правила, що `supabase-comments`); ключ
    `sb_publishable_…` чи JWT із `"role":"anon"` у payload → відмова «потрібен непублічний ключ»; таблиця не за
    `[a-z_][a-z0-9_]{0,62}` → відмова; таблиці нема (відповідь `42P01`/`PGRST205`) → текст «запустіть schema.sql»; ок → `True`;
  - `rows`: GET `…/rest/v1/<table>?select=id,name,jira,jira_status,jira_status_cat,open_comments,thumb_url,code_url,updated_at,designer,iterations,pages&limit=500`,
    заголовки `apikey`/`Authorization: Bearer`, тайм-аут ≤4 с; не-масив → `module-error`;
  - `push(ctx, cards, 'merge'|'insert')`: POST `…/<table>?on_conflict=id`, `Prefer: resolution=merge-duplicates|ignore-duplicates,return=minimal`,
    пакети по 50 (120 карток → 3 запити), збій пакета → усі його id у `failed`, решта `ok`; поганий `mode` → `module-error`;
    картка зі значенням `None` → ключ не шлеться (захист і в модулі, не лише в ядрі);
  - `open_comments`: GET `…/rest/v1/comments?status=eq.open&select=project_id` → лічильники; `42P01` → `{}`;
  - жоден текст помилки не містить значення ключа (`ctx['secrets']['key']`), тіла запиту чи відповіді понад 200 знаків.
- [ ] **Step 2: Реалізація** — за зразком `app/modules/supabase-comments/server.py` (`_tls` з certifi, `_open`, `_error`,
  `_host_ok`, `_base`, `_clean`; скопіювати, НЕ імпортувати чужий модуль). Ключові константи:
  ```python
  TEAM_KEYS = ('id', 'name', 'jira', 'jira_status', 'jira_status_cat', 'open_comments', 'thumb_url', 'code_url',
               'updated_at', 'designer', 'iterations', 'pages')
  READ_TIMEOUT_S = 4
  PUSH_TIMEOUT_S = 15          # на пакет
  BATCH = 50
  MAX_ROWS = 500
  DEFAULT_TABLE = 'deai_dashboard'
  _TABLE_RE = re.compile(r'[a-z_][a-z0-9_]{0,62}', re.ASCII)
  ```
  Публічність ключа: `key.startswith('sb_publishable_')` або JWT (`a.b.c`), чий payload (base64url) має `"role": "anon"`.
  `schema.sql`: `create table if not exists public.deai_dashboard (id text primary key, name text, status text, jira text,
  jira_status text, jira_status_cat text, jira_synced_at timestamptz, open_comments int, figma_url text, code_url text,
  thumb_url text, thumb_source text, iterations int, pages int, gitlab_url text, gitlab_repo text, gitlab_path text,
  comment_project text, backup_at timestamptz, source text, designer text, designer_key text, updated_at timestamptz,
  synced_at timestamptz)`; `enable row level security`; **жодної** політики для `anon`; шапка-попередження як у
  `supabase-comments/schema.sql` («окремий проєкт», «не адоптуй чужу таблицю») + «ключ модуля — непублічний». `README.md`:
  що робить, налаштування, як запустити схему, чому ключ непублічний.
- [ ] **Step 3:** мутації: перевірку anon-ключа прибрано → червоніє; `BATCH` ігнорується (усі в один запит) → червоніє;
  фільтр `None` прибрано → червоніє. `npm test`. Коміт.

---

### Task 5: читання — вкладка «Команда» через постачальника

**Files:** Modify `app/dashboard.py` (`legacy_ctx`, `normalize_rows`, `route`), `app/serve.py` (`_team_fetch` ≈1753,
`team_snapshot` ≈1802, `/api/tasks-overview` ≈5507); Test `tests/test_dashboard.py` (`ReadPath`), `tests/test_tasks_overview.py`,
`tests/test_integrations_off.py` (лише якщо гейт змінив назву — кожна зміна з причиною).

- [ ] **Step 1: Падаючі тести:**
  - **Диференційний:** три сценарії `team_read` з Task 1 дають те саме тіло (без часових полів), той самий URL/заголовки
    (через модуль `supabase-dashboard` у шляху ЛІГИ — `urlopen` модуля підмінено), той самий `team: null` без мережі;
  - звичайний простір з фейковим модулем дашборда (тека в `DEAI_EXTRA_MODULES`, `rows` віддає 2 рядки + один без `id` +
    зайвий ключ `secret_col`) → `team.rows` має 2 рядки й лише `TEAM_KEYS`; без модуля → `team: null`;
  - кеш на простір: збій простору A не стає рядками простору B; `refresh=1` оминає кеш лише свого простору;
  - ⛔ ізоляція: `DC_TASKS_FILE` чи `DC_NO_OVERVIEW` без `DC_TEAM_FAKE` → у ЛІГИ жодного виклику модуля, пояснення як у
    0.11.0; `DC_TEAM_FAKE` → рядки з файла (шов лише для `'legacy'`);
  - ЛІГА без конфігу → `team.error` = «Supabase не налаштовано» (як у знімку), мережі нема;
  - модуль кидає `ModuleError`/`check-timeout` → `team.error` з текстом (≤200), рядки — останні вдалі.
- [ ] **Step 2: Реалізація** (`app/dashboard.py`):
  ```python
  TEAM_KEYS = (...)                 # той самий кортеж, що в модулі
  MAX_ROWS = 500
  READ_TIMEOUT = 4
  LEGACY_TABLE = 'overview_projects'
  LEGACY_MODULE = 'supabase-dashboard'

  def legacy_ctx(url, key, space_id=''):
      """`ctx` неявного постачальника ЛІГИ. ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`
      (урок `_vcs_legacy_ctx`). `url`/`key` — з `supabase_config()` викликача; нема → `dashboard-unconfigured`."""
      if url is None:
          raise deai_modules.ModuleError('dashboard-unconfigured', message='Supabase не налаштовано')
      return {'space': {'id': space_id, 'path': ''}, 'settings': {'url': url, 'table': LEGACY_TABLE},
              'secrets': {'key': key}, 'ModuleError': deai_modules.ModuleError, 'legacy': True}

  def normalize_rows(data):
      if not isinstance(data, list):
          raise ValueError('rows: очікувався масив')
      out = []
      for r in data[:MAX_ROWS]:
          if isinstance(r, dict) and isinstance(r.get('id'), str):
              out.append({k: r.get(k) for k in TEAM_KEYS})
      return out
  ```
  `ctx['legacy']` — модуль у ЛІГИ не відмовляє публічному ключу (спека §3; `check` ЛІГИ — лише з «Підключення»).
  `serve._team_fetch(space, prov)` — порядок: `'legacy'` + `DC_TEAM_FAKE` → файл; `'legacy'` + ізоляція → пояснення;
  `'legacy'` → `dashboard.legacy_ctx(*supabase_config(), …)` + вбудований модуль із `deai_modules.catalog()`; модуль →
  `deai_modules.module_ctx(space, prov)`; виклик — `deai_modules.call(m, 'rows', ctx, timeout=dashboard.READ_TIMEOUT)` →
  `normalize_rows`. «Ніколи не кидає» лишається. `_TEAM_CACHE` → словник `{space_id: {...}}` під тим самим `_TEAM_LOCK`.
  `/api/tasks-overview`: `prov = provider('dashboard')` (помилка → `team.error`, вкладка є лише коли prov не `None`);
  `None` → `team: null` як зараз. `space_view` не змінюється (`capabilities` уже несе `dashboard` після Task 3).
- [ ] **Step 3:** мутації: ключ кешу без простору; ізоляція `DC_NO_OVERVIEW` прибрана для `'legacy'`; `normalize_rows` без
  відбору ключів. `npm test`. Коміт.

---

### Task 6: запис — синк через постачальника, CLI, один синк на простір

**Files:** Modify `app/dashboard.py` (`sync`), `bin/overview_push.py` (CLI), `app/serve.py` (`_overview_sync` ≈7068 і 4 виклики
≈7006, ≈7051, ≈7617, ≈7667); Test `tests/test_dashboard.py` (`SyncParity`, `SyncRunner`), `tests/test_serve.py`
(`OverviewSyncGuard`, `OverviewSyncLog` — кожна зміна з причиною), `bin/test_overview_push.py` (лише точки підміни, якщо
переїхали — з причиною).

- [ ] **Step 1: Падаючі тести:**
  - **Диференційний `sync_push`:** `dashboard.sync(...)` для ЛІГИ з тими самими заглушками (реєстр, коментарі, Jira — колбеки)
    і фейковим модулем, що записує `push(cards, mode)`, дає ту саму **множину** карток і ті самі `mode` (`insert` для реєстру,
    `merge` для задач), що `before-4c1.json`; лог містить ті самі підсумкові рядки;
  - звичайний простір: ні реєстру, ні Jira не кличеться; `open_comments` модуля (є/нема) → статус `review`;
  - `push` повертає `failed` → назви задач у лозі вголос;
  - CLI: `overview_push.py sync` без `--space` → простір ЛІГА; `--space p` → простір `p`; невідомий простір → код 2 і текст;
    `from serve` у файлі нема (`grep`-тест);
  - **Диференційний `sync_gate`:** ті самі рішення «стартувати/ні», що в знімку; а також: простір з модулем дашборда без
    `integrations` → старт; без постачальника → ні; `DC_NO_OVERVIEW` → ні для будь-якого постачальника;
  - один на простір: другий тригер, поки перша дитина жива (`poll() is None`), `Popen` не кличе, ставить позначку; після
    завершення (`wait` у фоновому потоці) — рівно один повтор; тригер іншого простору стартує паралельно;
  - лог: ЛІГА — шлях із шва `serve.OVERVIEW_LOG` (типово `~/.claude/pipeline-feedback/overview-sync.log`), інші — `<DEAI_HOME>/logs/dashboard-sync.log`, тека 0o700.
- [ ] **Step 2: Реалізація:**
  ```python
  def sync(cfg, module, ctx, *, discover=None, statuses=None, identity=None, log=print, call=None):
      """Один прохід синку карток простору (спека §4). `call` — `deai_modules.call` (шов для тестів).
      `discover()` → {id: запис} (лише ЛІГА: реєстр GitLab); `statuses(keys)` → {jira: {name, cat}} (лише ЛІГА до 4c-2)."""
  ```
  Тіло — кроки 0–5 з `cmd_sync` дослівно за змістом (⛔-коментарі переносяться), лише `upsert_project(row, ignore)` →
  збирання списків і `call(module, 'push', ctx, cards, mode, timeout=PUSH_TIMEOUT)`; `open_comment_counts()` →
  `call(module, 'open_comments', ctx, timeout=…)` якщо функція є, інакше `{}`.
  `bin/overview_push.py`: `argparse` — `sync [--space ID]`, `discover`; резолв простору через `spaces` (без `--space` —
  `spaces.legacy` запис, як кличе зовнішній планувальник); постачальник — `deai_modules.provider('dashboard', space)`;
  `'legacy'` → `dashboard.legacy_ctx(*install_config.supabase_config())`, колбеки `discover_projects`/`jira_statuses`
  (Jira-код лишається в `overview_push.py` до 4c-2). `_supabase()`/`upsert_project`/`open_comment_counts` прибрати разом із
  тестами, що їх приколювали (`TestSupabaseGetter`, `TestUpsertProject` → переписати на модуль у Task 4/тут; кожну заміну
  назвати в звіті). `SUPABASE_SERVICE_KEY` (спека §5: лишається запасним ключем ЛІГИ): `install_config.supabase_config()`
  НЕ розширювати (його бачать коментарі — сервісний ключ туди не мусить потрапити); лише CLI ЛІГИ, коли
  `supabase_config()` дав `(None, None)`, бере пару `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` з оточення (та сама перевірка
  форми, що в `install_config`). Тест: файл є → файл; файла нема, `SUPABASE_URL`+`SUPABASE_SERVICE_KEY` → вони.
  `serve._overview_sync(self)`: гейт — `prov = provider('dashboard')` не `None` (помилка → тиша), `DC_NO_OVERVIEW` → тиша,
  `'legacy'` + `DC_TASKS_FILE` → тиша; конфіг ЛІГИ більше не передається через оточення (дитина читає `install_config`);
  argv — `[sys.executable, bin/overview_push.py, 'sync', '--space', <id простору запиту>]`; `_SYNC_RUNS = {sid: (popen,
  pending)}` під локом, потік-спостерігач `wait()` → повтор, якщо `pending`.
- [ ] **Step 3:** мутації: прибрати `DC_NO_OVERVIEW` у `_overview_sync`; прибрати позначку повтору; `insert` замість `merge`
  для задач. `npm test`. Коміт.

---

### Task 7: «Підключення» й майстер — роль `dashboard`

**Files:** Modify `app/connections-model.js` (≈20–45, ≈295), `app/i18n.js`; Test `tests/connections-model.test.mjs`,
`tests/connections-view.test.mjs`, тест майстра (`grep -ln ROLE_ORDER tests`).

- [ ] **Step 1: Падаючі тести:** `ROLE_ORDER` = `["publish", "comments", "vcs", "dashboard", "tokens"]`; `roleKeys("dashboard")`
  → `{title: "cnRoleDashboard", lead: "cnRoleDashboardLead", none: "cnNoneDashboard"}`; `roleIcon("dashboard")` — іконка з
  наявного набору `icons.js` (взяти `grid` чи найближчу наявну; нову не малювати); `roleKeys("tracker") === null` лишається;
  `BUILTIN_TEXT["supabase-dashboard"]` з полями `url`/`key`/`table`; `disableConsequences` — для ЛІГИ роль `dashboard` →
  `kind: 'legacy'`; i18n UK/EN мають усі нові ключі (`tests/i18n-keys.test.mjs`).
- [ ] **Step 2: Реалізація** — ключі UK/EN: `cnRoleDashboard` («Командний дашборд» / "Team dashboard"), `cnRoleDashboardLead`
  («Спільний огляд задач команди: вкладка «Команда» на екрані «Задачі».» / "A shared overview of the team's tasks: the
  «Team» tab of the Tasks screen."), `cnNoneDashboard` («Без дашборда — вкладки «Команда» нема.» / "No dashboard — no Team
  tab."), `cnModSbDashName` («Supabase — дашборд» / "Supabase dashboard"), `cnModSbDashDesc`, `cnFieldSbDashUrl`,
  `cnFieldSbDashKey` («Непублічний ключ (service_role)» / "Non-public key (service_role)"), `cnFieldSbDashTable`, і текст
  наслідку вимкнення в ЛІГИ.
- [ ] **Step 3:** `npm test`; мутація: `dashboard` геть з `disableConsequences`-переліку ЛІГИ → червоніє. Коміт.

---

### Task 8: живі тести

**Files:** `tests/live/tasks-home.test.mjs`, `tests/live/connections*.test.mjs` (+ `tests/live/fixture.mjs`, якщо треба
`DEAI_EXTRA_MODULES` з фейковим модулем дашборда; фейк — у `tests/fixtures/dashboard/fake-dashboard/` з `module.json` +
`server.py`, що віддає рядки з JSON-файла поруч і пише `push` у файл).

- [ ] Спершу прогнати наявні `tasks-home`, `connections*`, `spaces-flows` як є — список падінь.
- [ ] Сценарії: (1) звичайний простір без модуля дашборда — вкладки «Команда» нема; (2) той самий простір з увімкненим фейковим
  модулем — вкладка є, рядки з файла, чужий рядок без кнопки «відкрити»; (3) модуль кидає помилку — плашка з текстом, «Мої»
  живі; (4) «Підключення» — картка ролі «Командний дашборд», модуль у ній; (5) ЛІГА (`DC_TEAM_FAKE`) — як у 0.11.0.
- [ ] Кожен змінений живий файл — по одному; потім `npm test`. Коміт.

---

### Task 9: документи й версія 0.12.0

- [ ] `CHANGELOG.md` — `## [0.12.0] — невипущено` у стилі `[0.11.0]`: Added (роль `dashboard`, модуль `supabase-dashboard`
  + схема, вкладка «Команда» в будь-якому просторі з дашбордом, картка на «Підключенні»), Changed (ЛІГА — через модуль;
  синк один на простір; пакети по 50; кеш на простір; `overview_push.py` — CLI з `--space`, конфіг із `tasks.json` раніше
  за оточення; тайм-аут читання 4 с), Removed (`_supabase`, `upsert_project`, `open_comment_counts` з `overview_push.py`,
  `from serve` у CLI), «Як оновитись» (ЛІГА: нічого; звичайний простір: схема + непублічний ключ; планувальник ЛІГИ з
  `SUPABASE_URL`/`SUPABASE_KEY` в оточенні тепер пише туди, куди вказує `tasks.json`, якщо там є конфіг), «Відомі обмеження»
  (зі спеки + будь-яке відхилення, знайдене в реалізації).
- [ ] `README.md` — командний дашборд; модуль і його схема. `docs/design/spaces-and-modules.md` — «Stage 4c-1», шапка, таблиця
  ролей (`dashboard` — Supabase). `app/modules/supabase-dashboard/README.md` уже є (Task 4) — звірити.
- [ ] `package.json` 0.12.0; `npm test`; коміт.

---

## Після всіх задач (контролер)

1. Фінальне ревʼю всієї гілки від коміту спеки (`f498242`).
2. Повні прогони на знімку: `npm test`; `/usr/bin/python3` 3.9.6; живі — по одному (`inspector-ds` 2/4 — стара червона).
3. Дата в CHANGELOG → тег `v0.12.0` (анотований, neodisa) → `git push origin <sha>:refs/heads/main` і тег → звірити віддалений sha.
4. Памʼять, статус пайплайна, звіт власнику.
