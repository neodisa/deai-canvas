# Етап 4c-3 «Сповіщення Teams як роль» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** роль `notify` у ядрі й вбудований модуль `supabase-teams` (схема: картка Teams на новий пін, тиша на канал,
журнал доставок, здоровʼя); перемикач тиші в канвасі й маршрут `/api/teams-mute` — за постачальником ролі; ЛІГА — через той
самий модуль як неявний постачальник. Реліз 0.14.0.

**Architecture:** нове ядро `app/notify.py` (без імпорту `serve`) нормалізує стан тиші, рахує вигляд каналу (`mute_view`) і
будує `ctx` ЛІГИ; модуль кличе RPC `teams_mute_state`/`teams_mute_set` (і `teams_notify_health` у `check`). `serve.py`:
`notify_resolve()` + `notify_call(fn, *args)` замість `teams_rpc` — шов `DC_TEAMS_FAKE` і закон ізоляції для `'legacy'`
переносяться. Клієнт гейтить пункт «Сповіщати Teams» і опит за `capabilities.notify`.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium
(живі), SQL (PostgreSQL/Supabase — лише статичні перевірки, Postgres у тестах нема).

**Спека:** `docs/superpowers/specs/2026-11-03-notify-role-design.md`. Читати перед кожною задачею.

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
  дизайнера, `~/.claude/pipeline-feedback/`. Процеси — лише за PID. Фонові прогони — дочекатися й зупинити до звіту.
- **Жодної мережі в тестах.** Supabase — лише заглушки (шов `_open` модуля, `DC_TEAMS_FAKE`). Ізоляцію
  `DC_TASKS_FILE`/`DC_NO_OVERVIEW` не послаблювати. ⛔ Живий канал Teams команди не чіпати НІ В ЯКОМУ РАЗІ.
- Знеособлено: лише вигадані значення (`https://demo.supabase.example`, ключі `sk-test-…`/`pk-test-…`, канали `dc/t1`,
  `dc/t1/internal`, підпис `k:0123456789ab`).

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
| `tests/make_before_4c3.py`, `tests/fixtures/notify/before-4c3.json` (нові) | знімок 0.13.0 (Task 1) |
| `app/deai_modules.py` | роль `notify`: `ROLES_CALLED`, `ROLES_RESERVED = ()`, `ROLE_FUNCTIONS`, `LEGACY_ROLES`, `STRICT_LEGACY_ROLES`, `STATUS`, `KNOWN_OTHER_MODULES`, докстрінги |
| `app/notify.py` (новий) | `normalize_mutes`, `mute_view`, `check_set_args`, `legacy_ctx`, `legacy_module`, константи |
| `app/modules/supabase-teams/` (нова) | `module.json`, `server.py`, `schema.sql`, `README.md` |
| `app/serve.py` | `teams_rpc` → `notify_resolve` + `notify_call`; `teams_mute_view` → `notify.mute_view`; гейт `/api/teams-mute` (GET/POST) |
| `app/spaces-model.js`, `app/bar-model.js`, `app/app.js` | `hasNotify`; пункт меню й опит за роллю |
| `app/connections-model.js`, `app/i18n.js` | роль `notify` на «Підключенні» й у майстрі; `BUILTIN_TEXT["supabase-teams"]`; `CHECK_KEYS` |
| `tests/test_notify.py`, `tests/test_notify_module.py`, `tests/test_notify_schema.py` (нові) | ядро, модуль, статика схеми |
| `tests/fixtures/notify/fake-notify/`, `tests/live/notify-role.test.mjs` (нові) | живі |
| `docs/modules/authoring.md`, `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json` | Task 7 |

---

### Task 1: знімок 0.13.0 (до змін коду)

**Files:** Create `tests/make_before_4c3.py` (зразок — `tests/make_before_4c2.py`: рецепт замороженої копії `git archive
0267024 | tar -x -C <тека>` у докстрінгу, відмова писати типовий шлях, коли `app/`/`bin/` відрізняються від `0267024`),
`tests/fixtures/notify/before-4c3.json`; тест-читач `tests/test_notify.py` (клас `Before4c3Shape`).

- [ ] **Step 1:** генератор на HEAD без змін коду, усе на заглушках:
  - `rpc_requests`: `serve.teams_rpc('teams_mute_state', {})` і `serve.teams_rpc('teams_mute_set', {'p_project': 'dc/t1',
    'p_muted': True, 'p_by': 'k:0123456789ab'})` з підміненим `serve.supabase_config` → `('https://demo.supabase.example',
    'pk-test-1')` і `urllib.request.urlopen` (запис: метод, шлях, тіло JSON, заголовки — `apikey`/`Authorization` →
    `"<key>"`, тайм-аут, чи є TLS-контекст) + розбір відповіді-заглушки; ізоляція (`DC_TASKS_FILE`) → текст `OSError` і нуль
    викликів `urlopen`; простір без інтеграцій → тип винятку.
  - `route`: справжній сервер у процесі (ефемерний порт, як `tasks_overview` у `make_before_4c2.py`), ЛІГА з `DC_TEAMS_FAKE`
    (тимчасовий JSON): GET `/api/teams-mute` для задачі з каналом `dc/t1` — (1) не замовчано, (2) замовчано мною (підпис
    машини — підмінити `serve.mute_signature` на `'k:0123456789ab'`), (3) замовчано колегою, (4) замовчано батьківський канал
    при каналі `dc/t1/internal` (якщо задача фікстури дає такий канал — інакше лише `mute_view` напряму); POST
    `{muted: true}` / `{muted: false}` (з дозволеним Origin) і POST з чужим Origin (403), з `muted: "yes"` (400); GET і POST у
    просторі без інтеграцій (статус + тіло). Тіла — без часових полів (`muted_at` → тип).
  - `menu`: `bar-model` пункти дропдауна публікації через `node -e` (імпорт `app/bar-model.js`) для стану з інтеграціями й без
    (`space.integrations` true/false, `teams` = `{channel, muted:false}`) — список `id` пунктів.
- [ ] **Step 2:** запустити двічі (байт-у-байт), закомітити JSON + генератор + `Before4c3Shape`. Жодних змін у `app/`/`bin/`.

---

### Task 2: роль `notify` у каркасі модулів і ядро `app/notify.py`

**Files:** Modify `app/deai_modules.py`; Create `app/notify.py`; Test `tests/test_notify.py` (`NotifyRole`, `NotifyCore`),
`tests/test_modules.py` (рядки про `ROLES_RESERVED`, маніфест «reserved»), усі піни `capabilities()` (додати `notify`).

- [ ] **Step 1: Падаючі тести:**
  - `dm.ROLES_CALLED[-1] == 'notify'`, `dm.ROLES_RESERVED == ()`; маніфест з `roles: ["notify"]` без `mute_state`/`mute_set`
    → `bad-manifest`; з ними — `ok`; тест «reserved roles need no function» переписати: зарезервованих нема — маніфест із
    невідомою роллю (`"alpha"`) поводиться, як і раніше (перевірити, як каркас трактує невідому роль, і зберегти це);
  - простір з інтеграціями без модуля → `provider('notify') == 'legacy'`; без → `None`; `ModuleError` → `None`; зламаний
    `space.json` → `space-json-unreadable` (`STRICT_LEGACY_ROLES`); `capabilities` має ключ `notify`;
  - `STATUS['notify-unconfigured'] == 409`, `STATUS['notify-error'] == 502`; `'supabase-teams' in KNOWN_OTHER_MODULES`
    (тимчасове послаблення точної перевірки в `tests/test_comments_role.py` — як у 4c-2, з коментарем, прибирається в Task 3);
  - `notify.normalize_mutes`: лише словники з рядковим `project_id` 1..200; `muted_by` не рядок/> 200 → `''`; `muted_at` не
    рядок/> 40 → `None`; > 1000 рядків → обрізано; не список → `ValueError`;
  - `notify.mute_view(channel, rows, me)`: збіг каналу; підканал `dc/t1/internal` під замовчаним `dc/t1` (з `via`); `dc/t10`
    НЕ під `dc/t1`; `mine` лише при непорожньому збігу підпису; паритет із `serve.teams_mute_view` на кейсах знімка;
  - `notify.check_set_args(channel, muted, by)`: порожній/не рядок/> 200 канал, не-`bool` `muted`, `by` > 200 → `ValueError`.
- [ ] **Step 2: Реалізація:**
  ```python
  # app/deai_modules.py
  ROLES_CALLED = ('publish', 'tokens', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')
  ROLES_RESERVED = ()
  ROLE_FUNCTIONS = {..., 'notify': ('mute_state', 'mute_set')}
  LEGACY_ROLES = (..., 'tracker', 'notify')
  STRICT_LEGACY_ROLES = ('comments', 'dashboard', 'tracker', 'notify')   # LEGACY_ON_ERROR_ROLES — без змін
  STATUS[...]: 'notify-unconfigured': 409, 'notify-error': 502
  KNOWN_OTHER_MODULES = frozenset({..., 'jira-tracker', 'supabase-teams'})
  ```
  `ROLES_CALLED + ROLES_RESERVED` використовується в перевірці маніфесту (≈496) — порожній кортеж мусить працювати.
  ```python
  # app/notify.py — ядро ролі `notify` (етап 4c-3); БЕЗ імпорту `serve`
  NOTIFY_TIMEOUT = 10          # ядро чекає на виклик; сокет модуля — 8 с
  MAX_MUTES = 1000
  CHANNEL_MAX = BY_MAX = 200
  LEGACY_MODULE = 'supabase-teams'
  UNCONFIGURED = 'Supabase не налаштовано'
  def normalize_mutes(data): ...
  def mute_view(channel, rows, me): ...      # тіло — `serve.teams_mute_view` дослівно за змістом, `me` замість mute_signature()
  def check_set_args(channel, muted, by): ...
  ```
  `docs/modules/authoring.md`: розділ «The `notify` role» (функції, форма `mute_state`, аргументи `mute_set`, коди помилок і
  вердикти `check`, `NOTIFY_TIMEOUT`); «reserved names» — нема.
- [ ] **Step 3:** мутації: `'notify'` у `LEGACY_ON_ERROR_ROLES`; підканал без `'/'` у `mute_view` (`startswith(pid)`);
  `check_set_args` без перевірки `bool`. `npm test`. Коміт.

---

### Task 3: модуль `supabase-teams` (сервер, схема) і адаптер ЛІГИ

**Files:** Create `app/modules/supabase-teams/{module.json, server.py, schema.sql, README.md}`; Modify `app/notify.py`
(`legacy_ctx`, `legacy_module`), `tests/test_comments_role.py` (прибрати послаблення Task 2; `BUILTIN_IDS`),
`tests/test_modules_api.py` (`BUILTIN_IDS`); Test `tests/test_notify_module.py`, `tests/test_notify_schema.py`,
`tests/test_notify.py` (`LegacyAdapter`).

- [ ] **Step 1: Падаючі тести** (мережа — лише шов `_open` модуля):
  - `module.json`: `id: supabase-teams`, `roles: ["notify"]`, `url` (text, required), `key` (secret, required, без `public`);
  - **паритет зі знімком:** `mute_state`/`mute_set` модуля шлють рівно те, що `rpc_requests` у `before-4c3.json` (метод,
    шлях, тіло, набір заголовків, тайм-аут 8); розбір відповіді той самий;
  - `check`: погана адреса → текст правил; публічний ключ (`sb_publishable_…`, JWT `"role":"anon"`) → вердикт «потрібен
    непублічний ключ» (але з `ctx['legacy']` — без цієї перевірки); `teams_mute_state` 404 / код `PGRST202` → «запустіть
    schema.sql»; `teams_notify_health` → `webhook_set: false` → вердикт `notify-no-webhook`; інакше ok з деталлю «доставок за
    6 год: N, невдалих: M»; з `ctx['legacy']` — `teams_notify_health` НЕ кличеться (у базі ЛІГИ її нема);
  - тексти помилок без ключа, тіл, ≤ 200; редирект 302 не виконується; відповідь > ліміту → помилка «відповідь завелика»;
  - `notify.legacy_ctx(None, None)` → `ModuleError('notify-unconfigured')`; з парою → `settings.url`, `secrets.key`,
    `legacy: True`; `legacy_module()` → вбудований `supabase-teams` зі статусом `ok`;
  - **статика схеми** (`tests/test_notify_schema.py`, розбір тексту `schema.sql` регулярками — без БД): кожен
    `security definer` має `set search_path`; `cl_notify_teams` — `security invoker` і перевіряє `row_security_active`;
    `cl_send_teams` і `cl_notify_teams` мають `exception when others`; `teams_mute_set`, `teams_mute_state`,
    `teams_notify_health` — `grant execute … to service_role` і НЕ `to anon`/`authenticated`, є `revoke … from public`;
    `cl_send_teams` — `grant … to anon, authenticated`; обидві таблиці — `enable row level security` і `revoke all … from anon,
    authenticated`; `comment_teams_card` не містить `||` над полями коментаря поза дозволеним обрізанням тексту (перевірка:
    кожен `||` у тілі функції стоїть у рядку з `jsonb_build_array`/`jsonb_build_object` або в рядку обрізання `left(`);
    ідемпотентність (`create table if not exists`, `create or replace function`, `drop trigger if exists` перед `create
    trigger`); `cl_send_teams` перевіряє свіжість (`interval '2 minutes'`) і тишу з підканалами (`|| '/'`); секрет —
    `vault.decrypted_secrets` з імʼям `teams_webhook_url`; картинка й кнопка — лише за `https://`.
- [ ] **Step 2: Реалізація** — `server.py` за зразком `app/modules/supabase-dashboard/server.py` (копія `_tls`, `_opener`,
  `_NoRedirect`, `_open`, `_error`, `_host_ok`, `_clean`, перевірка публічного ключа). Константи:
  ```python
  TIMEOUT_S = 8
  HEALTH_HOURS = 6
  MAX_BODY = 1 << 20
  MSG_MAX = 200
  NO_FUNCTION_CODES = ('PGRST202', '42883')
  ```
  `schema.sql` — за спекою §2 (і зразком схеми ЛІГИ, описаною в спеці; назва проєкту = `c.project_id`, без
  `overview_projects`; підписи картки в одному `declare`-блоці). `README.md`: що робить; порядок (спершу схема
  `supabase-comments`, потім ця); Vault: `select vault.create_secret('<адреса вебхука>', 'teams_webhook_url');` — без
  вигаданих адрес; приймач (Power Automate «When a Teams webhook request is received» → «Post card in a chat or channel» — назви
  кроків лише загально, без URL); чому ключ непублічний; ЛІГА — не запускати.
- [ ] **Step 3:** мутації: перевірку публічного ключа прибрано; `teams_notify_health` для `legacy`; у схемі `grant … to anon`
  для `teams_mute_set` (статичний тест червоніє); `security invoker` → `definer` у тригері; прибрано `exception when others` у
  `cl_send_teams`. `npm test`. Коміт.

---

### Task 4: сервер — `notify_call` замість `teams_rpc`, маршрут за роллю

**Files:** Modify `app/serve.py` (`teams_rpc` ≈2393, `teams_mute_view` ≈2445, `/api/teams-mute` GET ≈5726, `_teams_mute`
≈6901); Test `tests/test_notify.py` (`ServerPath`), `tests/test_serve.py`, `tests/test_integrations_off.py`,
`tests/test_legacy_comments.py` (кожна зміна з причиною).

- [ ] **Step 1: Падаючі тести:**
  - **диференційний `route`:** усі сценарії `before-4c3.json` для ЛІГИ (шов `DC_TEAMS_FAKE`) дають ті самі статуси й тіла;
    простір без інтеграцій і без модуля → 409 з `code: 'notify-off'` (свідома відмінність — коду), тіло інше лише кодом;
  - **диференційний `rpc_requests`:** шлях ЛІГИ без шва (підмінені `supabase_config` і шов `_open` модуля) шле те саме, що
    знімок; ізоляція (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) → без мережі, GET → `{channel, error}`, POST → 502;
  - звичайний простір без інтеграцій із фейковим модулем `notify` (вбудовані через тестове `Env`, `self.mk`) → GET/POST
    працюють через модуль; збій модуля → GET `{channel, error}`, POST 502; поганий `muted` → 400 ДО виклику модуля; чужий
    Origin → 403 ДО всього;
  - `DC_TEAMS_FAKE` діє лише для `'legacy'` (у простору з модулем — ігнорується);
  - `teams_rpc` і `teams_mute_view` у `serve` більше нема (`hasattr`), `serve.mute_signature` лишився.
- [ ] **Step 2: Реалізація:**
  ```python
  def notify_resolve(): ...                     # `(space, prov)` ролі `notify` простору запиту, як `team_resolve`
  def notify_call(fn, *args, resolved=None): ...
  ```
  `notify_call`: `'legacy'` → шов `DC_TEAMS_FAKE` (код шва з `teams_rpc` дослівно за змістом, відповідь — у формі модуля:
  `mute_state` → список, `mute_set` → bool) → ізоляція (`OSError` з тим самим текстом) → `notify.legacy_ctx(*supabase_config(),
  …)` + `notify.legacy_module()`; модуль → `module_ctx`; виклик — `deai_modules.call(m, fn, ctx, *args,
  timeout=notify.NOTIFY_TIMEOUT)`; `mute_state` → `notify.normalize_mutes`. ⛔-уроки `teams_rpc` (заборона чіпати спільний
  стан з ізольованого конфігу; шов пише лише у свій файл) — переносяться в докстрінг. Маршрути: гейт — `prov is None` → 409
  `{ok: False, code: 'notify-off', error: 'сповіщень Teams у просторі нема'}`; `ModuleError`/`OSError`/`ValueError` → як
  зараз (GET `{channel, error}`, POST 502); `muted` перевіряється `notify.check_set_args` → 400.
- [ ] **Step 3:** мутації: прибрати ізоляцію для `'legacy'`; гейт за `integrations_on()` замість ролі; шов `DC_TEAMS_FAKE`
  для будь-якого постачальника; перевірка `muted` після виклику. `npm test`. Коміт.

---

### Task 5: клієнт — пункт меню за роллю, «Підключення» й майстер

**Files:** Modify `app/spaces-model.js` (`hasNotify` поруч із `hasVcs`), `app/bar-model.js` (≈317–354: `noInteg` →
`!hasNotify(space)` для пункту Teams), `app/app.js` (`loadTeamsMute` ≈2231: `noOutward()` → відсутність ролі),
`app/connections-model.js`, `app/i18n.js`; Test `tests/bar-model.test.mjs`, `tests/spaces-wiring.test.mjs`,
`tests/connections-model.test.mjs`, `tests/connections-view.test.mjs`, тест майстра, `tests/_legacy-golden-kit.mjs` (лише якщо
змінився сигнал — з причиною; `tests/legacy-golden.test.mjs` мусить лишитись зеленим БЕЗ `UPDATE_GOLDEN`).

- [ ] **Step 1: Падаючі тести:**
  - `hasNotify(space)` → `true` за `capabilities.notify` (модуль чи `'legacy'`); без ключа `capabilities` — за
    `integrations` (як `hasVcs`); `null` (шар вимкнено) — `true`, як `hasVcs(null)`;
  - **диференційний `menu`:** пункти дропдауна для ЛІГИ з інтеграціями й без — як у знімку; простір без інтеграцій, але з
    `capabilities.notify = 'fake-notify'` → пункт `teamsnotify` Є; з `notify: null` → нема;
  - «Підключення»: `ROLE_ORDER` = `[…, "dashboard", "tracker", "notify", "tokens"]`; `roleKeys("notify")`; `roleIcon("notify")` —
    наявна іконка (назвати у звіті); `LEGACY_ROLES` має `notify`; наслідок вимкнення поза ЛІГОЮ — свій ключ (механізм
    `consKey` з 4c-2); `BUILTIN_TEXT["supabase-teams"]` з `url`/`key`; `CHECK_KEYS["notify-no-webhook"]`; i18n UK/EN.
    Наявні тести, що брали `notify` як «зарезервовану роль без текстів», — на роль-вигадку (`"alpha"`, як у `groupModules`),
    з причиною.
- [ ] **Step 2: Реалізація** — ключі UK/EN: `cnRoleNotify` («Сповіщення Teams» / "Teams notifications"), `cnRoleNotifyLead`
  («Картка в канал Teams на кожен новий коментар; тиша — на канал задачі.» / "A card in a Teams channel for every new comment;
  silence per task channel."), `cnNoneNotify` («Без сповіщень — Teams мовчить.» / "No notifications — Teams stays silent."),
  `cnDisableNotify` («нові коментарі перестануть надходити карткою в Teams, а перемикач тиші зникне» / "new comments stop
  arriving as Teams cards, and the silence switch disappears"), `cnModSbTeamsName` («Supabase — Teams» / "Supabase Teams"),
  `cnModSbTeamsDesc`, `cnFieldSbTeamsUrl`, `cnFieldSbTeamsKey` («Непублічний ключ (service_role)» / "Non-public key
  (service_role)"), `cnErrNotifyNoWebhook` («У Vault нема секрету teams_webhook_url» / "No teams_webhook_url secret in Vault").
- [ ] **Step 3:** мутації: пункт Teams знову за `noInteg`; `notify` геть з `LEGACY_ROLES` клієнта. `npm test`, живий
  `tests/live/teams-mute.test.mjs` (по одному) — зелений. Коміт.

---

### Task 6: живі тести

**Files:** Create `tests/fixtures/notify/fake-notify/{module.json, server.py}` (стан тиші — у JSON-файлі з налаштування;
режим «збій» — коли у файлі `{"error": "…"}`), `tests/live/notify-role.test.mjs` (`PORT_BASE` — вільний: перевірити
`tests/live-ports.test.mjs`; теки `.live-ntf-*` + `.gitignore` + прибирання), зразок — `tests/live/tracker-role.test.mjs`.

- [ ] Спершу прогнати наявні `teams-mute`, `connections`, `tracker-role` як є — список падінь.
- [ ] Сценарії: (1) звичайний простір без інтеграцій і без модуля — пункту «Сповіщати Teams» у дропдауні публікації нема,
  модуль у каталозі, але не ввімкнений (`/api/modules`); (2) той самий простір з фейковим модулем — пункт є, «увімкнено»;
  вимкнення через діалог підтвердження → стан у файлі модуля й пункт «тиша (ви)»; (3) модуль у режимі «збій» → пункт вимкнений
  з причиною «невідомо», не «увімкнено»; (4) «Підключення» — секція «Сповіщення Teams», модуль у ній, діалог вимкнення з
  текстом `cnDisableNotify` (скасувати; нативних діалогів нема); (5) ЛІГА з `DC_TEAMS_FAKE` — як у 0.13.0.
- [ ] Кожен змінений живий файл — по одному; потім `npm test`. Коміт.

---

### Task 7: документи й версія 0.14.0

- [ ] `CHANGELOG.md` — `## [0.14.0] — unreleased` у стилі `[0.13.0]`: Added / Changed / Removed / Upgrading (ЛІГА: нічого;
  звичайний простір: схема `supabase-comments`, потім `supabase-teams`, секрет у Vault, непублічний ключ, приймач у Teams) /
  Deliberate differences / Known limits (зі спеки + відхилення реалізації з нотаток контролера).
- [ ] `README.md` — сповіщення в звичайному просторі. `docs/modules/authoring.md` — звірити з Task 2–3 (вердикти `check`,
  зарезервованих ролей нема). `app/modules/supabase-teams/README.md` — звірити. `docs/design/spaces-and-modules.md` —
  «Stage 4c-3», шапка («Next: 4d»), таблиця ролей, «What stays for later» (зарезервованих ролей нема), рядки «Left for 4c-3».
- [ ] Спека — «Implementation notes» (відхилення, прийняті на ревʼю). `package.json` 0.14.0; `npm test`; коміт.

---

## Після всіх задач (контролер)

1. Фінальне ревʼю всієї гілки від коміту спеки (`4987848`).
2. Повні прогони на знімку: `npm test`; `/usr/bin/python3` 3.9.6; живі — по одному (`inspector-ds` 2/4 — стара червона;
   `dashboard-role` тест 6 — артефакт знімка в `/tmp`, перевіряти в робочій теці).
3. Дата в CHANGELOG → тег `v0.14.0` (анотований, neodisa) → `git push origin <sha>:refs/heads/main` і тег → звірити віддалений sha.
4. Памʼять, статус пайплайна, звіт власнику (з кроком «запустити схему на справжньому Supabase — вручну»).
