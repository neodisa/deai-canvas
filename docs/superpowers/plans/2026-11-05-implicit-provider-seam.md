# Етап 4d-2 «Неявний постачальник, шов шару, закон ізоляції» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ядро перестає порівнювати постачальника ролі з рядком `'legacy'`: `provider()` повертає `Module | Implicit | None`,
шов «шар вимкнено» — одна функція `spaces.request_space()`, ізоляція спільного стану — один закон `implicit.isolated()` /
`implicit.route()`, а ізольований прогін не бачить облікових машини. Публічний контракт (`capabilities` = `'legacy'`,
`manifest.json` `build`) — без змін. Реліз 0.16.0.

**Architecture:** новий `app/implicit.py` (без імпорту `serve`, без мережі): клас `Implicit`, таблиця `IMPLICIT_ROLES`,
`for_role`, `isolated`, `route`. `deai_modules`: `_provider_for` повертає `Implicit`, `api_value()` — єдина точка відображення
назовні, `provider()` через `spaces.request_space()`. `serve.py` і `bin/` — гілки `isinstance(prov, Implicit)` замість
`== 'legacy'`. `install_config`: конфіг установки в ізольованому прогоні — лише корінь `DC_TASKS_FILE`.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-05-implicit-provider-seam-design.md`. Читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  Рядок `Co-Authored-By` — рівно такий. Коміт — лише з переліком шляхів; новий файл спершу `git add -- <шлях>`.
- **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md`.

**Прогони й середовище**

- Кожен прогін — через охоронця памʼяті `python3 "$G" <секунд> <МБ> <команда…>` (шлях `$G` дає контролер).
- Не виставляти `DEAI_HOME` у шелі; не чіпати порти 8765/4317, справжні `~/.deai`, `~/deai-published`, `~/.gitconfig`,
  `tasks.json` дизайнера, `~/.claude/pipeline-feedback/`. Процеси — лише за PID. Фонові прогони — дочекатися й зупинити до звіту.
- **Жодної мережі в тестах.** Ізоляцію `DC_TASKS_FILE`/`DC_NO_OVERVIEW` не послаблювати.
- Знеособлено: лише вигадані значення (`https://sb.example.com`, `https://jira.example.com`, Alpha / `alpha@example.com`).
  Жодних справжніх хостів, ключів, імен; імʼя користувача машини — лише з оточення, ніколи літералом.

**Конвенції коду**

- Коментарі українською, у стилі навколишнього коду; ⛔-уроки прибраного коду переносяться в нове місце, не губляться.
- Python 3.9: без `match`, без `X | Y` в анотаціях.

**Еталони й мутації**

- `tests/legacy-golden.test.mjs`, `GoldenPinTest`, знімки `before-4c1`, `before-4c3`, `before-4d1` — зелені БЕЗ `UPDATE_*`.
- Кожна нова перевірка доводиться мутацією (один рядок → потрібний тест червоніє → файл відновлено побайтно, sha256).
  Мутації Python — лише `python3 -B`, з охоронцем, по одній.

**Набори тестів:** юніти — `npm test`; живі — лише послідовно `node --test --test-concurrency=1 tests/live/<файл>`.
Номери рядків — орієнтир («≈»). Кожна зміна наявного тесту — у звіті одним рядком із причиною.

---

## Структура файлів

| Файл | Що змінюється |
|---|---|
| `tests/make_before_4d2.py`, `tests/fixtures/implicit/before-4d2.json` (нові) | знімок 0.15.0 (Task 1) |
| `app/implicit.py` (новий) | `Implicit`, `IMPLICIT_ROLES`, `for_role`, `isolated`, `route` |
| `app/spaces.py` | `request_space()` |
| `app/deai_modules.py` | `IMPLICIT_*` замість `LEGACY_*`; `_provider_for` → `Implicit`; `api_value`; `capabilities`; `provider` через `request_space`; ключ кешу (≈1258) |
| `app/serve.py` | гілки ролей (≈629, 1923, 1985, 2054, 2107, 2626, 3088, 3373–3411, 4261, 4872, 4907, 7118, 7609, 8131), `_liga_like`, `who` |
| `bin/overview_push.py`, `bin/state.py` | `isinstance(…, Implicit)` |
| `app/install_config.py` | ізольований конфіг (Task 5) |
| `tests/test_implicit.py` (новий) | знімок, ядро, шов шару, ізоляція, охоронець літерала |
| `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `docs/modules/authoring.md`, `package.json` | Task 7 |

---

### Task 1: знімок 0.15.0 (до змін коду) і перелік залежностей від оточення

**Files:** Create `tests/make_before_4d2.py` (зразок — `tests/make_before_4d1.py`: рецепт замороженої копії `git archive 6e68250 |
tar -x -C <тека>` у докстрінгу; охорона fail-closed проти `6e68250` для `app/`/`bin/`, включно з невідстежуваними файлами й
помилками git), `tests/fixtures/implicit/before-4d2.json`, `tests/test_implicit.py` (клас `Before4d2Shape`).

- [ ] **Step 1:** генератор на HEAD без змін коду, усе в тимчасових теках, `HOME` підмінено, без мережі:
  - `caps`: `deai_modules.capabilities(sp)` для {ЛІГА (`integrations: True`, без `space.json`); ЛІГА з нечитабельним
    `space.json`; звичайний без модулів; звичайний з `static-publish`; звичайний із нечитабельним `space.json`; звичайний зі своїм
    модулем «на папері» (недовірений); збій відбитків (підміна `_caps_key` → виняток)};
  - `provider`: `deai_modules.provider(role)` для кожної ролі при {шар вимкнено (`DC_TASKS_FILE` без `DEAI_HOME`); шар увімкнено,
    простір запиту не зафіксовано} — значення (`'legacy'`/`None`/id) і факт читання реєстру/`space.json`/каталогу (лічильники
    підмінених `spaces.load_registry`, `deai_modules.space_modules`, `deai_modules.catalog`);
  - `api`: справжній сервер у процесі на ефемерному порту (як `make_before_4d1.py`) — `GET /api/spaces` (ключ `capabilities`
    кожного простору), `GET /api/space`, `GET /api/task` (`X-Canvas-Task`): ключі постачальників, `publish_gate`, `preview_gate`;
    у двох режимах: ЛІГА в реєстрі тимчасового `DEAI_HOME` і шар вимкнено;
  - `isolation`: для `dashboard` (`serve.team_rows`/`_team_fetch`), `tracker` (функція статусів ≈2040), `notify`
    (`serve.notify_call` `mute_state` і `mute_set`) і синку дашборда (`_overview_sync` — чи запущено дитину; підмінити
    `_overview_launch`) з постачальником `'legacy'`: (а) з фейк-змінною — результат; (б) з `DC_TASKS_FILE` без фейку — результат /
    клас і текст винятку; (в) з `DC_NO_OVERVIEW` без `DC_TASKS_FILE` — те саме; модуль при (б)/(в) НЕ кличеться (підміна
    `deai_modules.call` рахує виклики);
  - `install`: `install_config.supabase_config()` і `jira_config()` під `DC_TASKS_FILE` (корінь фікстури з парою / без пари) ×
    {змінні оточення `SUPABASE_URL`/`SUPABASE_KEY`/`JIRA_EMAIL`/`JIRA_TOKEN` поставлені вигаданими значеннями / ні} × {файли
    `<HOME>/.claude/pipeline-feedback/jira-email|jira-token` у тимчасовому HOME є / нема} — значення (вигадані — можна писати);
  - `build`: `"build"` у `manifest.json` збірки ЛІГИ й модуля (як у `make_before_4c1.py`, якщо там є готовий рецепт; інакше —
    `serve.BUILD_KINDS` і функція, що пише маніфест, на тимчасовій теці).
- [ ] **Step 2:** запустити двічі (байт-у-байт), закомітити JSON + генератор + `Before4d2Shape`. Жодних змін у `app/`/`bin/`.
- [ ] **Step 3 (звіт, не код):** перелік тестів, що під `DC_TASKS_FILE` покладаються на `SUPABASE_*`/`JIRA_*` з оточення чи на
  файли `pipeline-feedback` (`grep` по `tests/` + `os.environ[...] =`/`mock.patch.dict(os.environ`), з file:line. Контролер
  вирішує по ньому Task 5.

---

### Task 2: ядро `app/implicit.py` і шов `spaces.request_space()`

**Files:** Create `app/implicit.py`; Modify `app/spaces.py`; Test `tests/test_implicit.py`.

- [ ] **Step 1: тести (червоні):** `ImplicitCore` — `for_role(r)` для кожної з 6 ролей повертає той самий обʼєкт (синглтон),
  незмінний (`setattr` → `AttributeError`); `module_id`/`fake_env`/`shared` за таблицею спеки §1; `for_role('tokens')` →
  `KeyError`; `isolated()` — таблиця істинності `DC_TASKS_FILE` × `DC_NO_OVERVIEW` (порожній рядок = нема); `route(p)` →
  `('fake', <шлях>)` коли `p.fake_env` задано й змінна непорожня (навіть під ізоляцією), `('isolated', None)` коли `isolated()`
  і `p.shared`, інакше `('live', None)`. `RequestSpace` — `spaces.request_space()` при вимкненому шарі й при незафіксованому
  просторі запиту повертає КОПІЮ `IMPLICIT` (зміна результату не чіпає `spaces.IMPLICIT`) і НЕ кличе `load_registry`
  (підміна з лічильником); при зафіксованому — те саме, що `active_space()`.
- [ ] **Step 2: реалізація:**
  ```python
  """Неявний постачальник ролі (4d-2): простір з інтеграціями без явного модуля (ЛІГА) чи вимкнений шар. Без мережі, без serve."""
  import os

  class Implicit:
      __slots__ = ('role', 'module_id', 'shared', 'fake_env')
      def __init__(self, role, module_id, shared, fake_env):
          for k, v in (('role', role), ('module_id', module_id), ('shared', shared), ('fake_env', fake_env)):
              object.__setattr__(self, k, v)
      def __setattr__(self, k, v):
          raise AttributeError('Implicit is immutable')
      def __repr__(self):
          return f'Implicit({self.role!r})'

  #: Ролі із зашитим шляхом ЛІГИ (колишні `LEGACY_ROLES`; склад і порядок ті самі).
  IMPLICIT_ROLES = ('publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')
  _TABLE = {
      'publish':   Implicit('publish',   'vercel-publish',     True, None),
      'comments':  Implicit('comments',  'supabase-comments',  True, None),
      'vcs':       Implicit('vcs',       'git-sync',           True, None),
      'dashboard': Implicit('dashboard', 'supabase-dashboard', True, 'DC_TEAM_FAKE'),
      'tracker':   Implicit('tracker',   'jira-tracker',       True, 'DC_TRACKER_FAKE'),
      'notify':    Implicit('notify',    'supabase-teams',     True, 'DC_TEAMS_FAKE'),
  }

  def for_role(role):
      return _TABLE[role]

  def isolated():
      """⛔ Закон ізоляції: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` — «стан не справжній цієї машини»; зі спільного стану ЛІГИ не ходимо."""
      return bool(os.environ.get('DC_TASKS_FILE') or os.environ.get('DC_NO_OVERVIEW'))

  def route(p):
      """Куди йти неявному постачальнику: `('fake', шлях)` → `('isolated', None)` → `('live', None)`. Порядок однаковий для всіх
      ролей; що повертати в кожному випадку, вирішує роль (форми відповідей 0.15.0 різні: див. знімок `isolation`)."""
      fake = os.environ.get(p.fake_env) if p.fake_env else None
      if fake:
          return 'fake', fake
      if p.shared and isolated():
          return 'isolated', None
      return 'live', None
  ```
  Перевірити звіркою з кодом, що ідентифікатори модулів збігаються з тим, що беруть гілки 0.15.0 (`PUBLISH_LEGACY_MODULE`,
  `COMMENTS_MODULE`, `VCS_MODULE`, `dashboard/tracker/notify.legacy_module()`); розбіжність — стоп і звіт контролеру.
  `spaces.request_space()`:
  ```python
  def request_space():
      """Простір запиту (4d-2, шов «шар вимкнено»): шар вимкнено чи простір запиту не зафіксовано → `dict(IMPLICIT)` БЕЗ читання
      реєстру; інакше `active_space()` (може кинути `SpacesError`; `None` — простору нема)."""
      if not layer_on() or request_space_id() is None:
          return dict(IMPLICIT)
      return active_space()
  ```
- [ ] **Step 3:** тести зелені (обидва Python), `npm test`; коміт.

---

### Task 3: `deai_modules` на `Implicit` (з тимчасовим мостом рівності)

**Files:** Modify `app/deai_modules.py`; Test `tests/test_implicit.py`, наявні тести модулів.

Щоб кожен коміт був зеленим, `serve.py` і `bin/` переходять у Task 4, а до того `Implicit` тимчасово дорівнює `'legacy'`:
у `Implicit` додати `__eq__` (`other == 'legacy'` або той самий обʼєкт) і `__hash__ = lambda self: hash('legacy')` з коментарем
`# ⛔ МІСТ 4d-2 Task 3→5: прибирається в Task 6 разом з охоронцем літерала`.

- [ ] **Step 1: тести (червоні):** `ProviderImplicit` — `provider(role)` для ЛІГИ, вимкненого шару й незафіксованого простору
  повертає `isinstance(…, Implicit)` для ролей `IMPLICIT_ROLES` і `None` для `tokens`; при вимкненому шарі / незафіксованому
  просторі не читає реєстр, `space.json` і каталог (лічильники); ⛔ `_provider_for(role, dict(spaces.IMPLICIT))` НЕ кличе
  `space_modules` (тест із `space.json`, що лежить у ПОТОЧНІЙ теці процесу — `os.chdir` у тимчасову теку з зіпсованим
  `space.json`: результат той самий, читань нема); `api_value(Module)` → id, `api_value(Implicit)` → `'legacy'`, `api_value(None)`
  → `None`, інше → `TypeError`; `capabilities()` — значення знімка `caps` без змін (порівняння з `before-4d2.json`).
- [ ] **Step 2: реалізація:**
  - `LEGACY_ROLES` → `IMPLICIT_ROLES = implicit.IMPLICIT_ROLES`; `LEGACY_ON_ERROR_ROLES` → `IMPLICIT_ON_ERROR_ROLES`;
    `STRICT_LEGACY_ROLES` → `STRICT_IMPLICIT_ROLES` (склад той самий; коментарі-уроки переносяться дослівно за змістом);
    всі використання в `app/`, `bin/`, `tests/` — на нові імена (без псевдонімів).
  - `_provider_for`: для `spaces._is_implicit(space)` — одразу `implicit.for_role(role) if role in IMPLICIT_ROLES else None`
    (без `space_modules`, без каталогу); решта повернень `'legacy'` → `implicit.for_role(role)`.
  - `provider(role, space=None)`: `space = spaces.request_space()` коли `None`; `None` → `None`; далі `_provider_for`.
    Докстрінг оновити (вимкнений шар і незафіксований простір — через шов, без читань).
  - `api_value(p)` — нова функція; `capabilities()` (≈1925, ≈1932, `except`-гілка) віддає значення лише через `api_value` /
    константу `API_IMPLICIT = 'legacy'` (одна на модуль, з коментарем «до 4d-3: публічний контракт»).
  - ключ кешу (≈1258): ідентифікатор з `spaces.request_space()` замість власної перевірки `layer_on()`.
- [ ] **Step 3:** усі тести зелені (обидва Python), `npm test`, знімки без UPDATE; мутації: (а) `_provider_for` для неявного
  простору кличе `space_modules` → тест із `chdir` червоний; (б) `api_value(Implicit)` → `'implicit'` → тест знімка `caps`
  червоний. Коміт.

---

### Task 4: `serve.py` і `bin/` — один шлях ролей

**Files:** Modify `app/serve.py`, `bin/overview_push.py`, `bin/state.py`; Test наявні тести ролей + `tests/test_implicit.py`.

- [ ] **Step 1:** кожну гілку `prov == 'legacy'` / `pub in (None, 'legacy')` / `kind == 'legacy'` переписати на
  `isinstance(prov, implicit.Implicit)` (у `bin/` — через `deai_modules`/`implicit`, як там імпортується ядро):
  - `dashboard` (`_team_fetch` ≈1923), `tracker` (≈2054), `notify` (`notify_call` ≈2626): тіло гілки —
    `kind, fake = implicit.route(prov)`; `'fake'` — наявний код фейку ролі БЕЗ змін формату; `'isolated'` — та сама відповідь,
    що 0.15.0 (`[], TEAM_ISOLATED` / `None` / `OSError('ізольований конфіг: …')` — тексти не міняти); `'live'` — наявний
    вбудований модуль і `legacy_ctx`. ⛔ Порядок `tracker` зберегти: `if not keys: return {}, None` — ПІСЛЯ фейку й ізоляції для
    неявного, як у 0.15.0.
  - синк дашборда (`_overview_sync` ≈7609): `legacy = isinstance(prov, Implicit)`; для неявного — `implicit.route(prov)[0] ==
    'isolated'` → `return` (раніше лише `DC_TASKS_FILE`; `DC_NO_OVERVIEW` уже відсікається вище для всіх — поведінка та сама,
    звірити знімком `isolation`).
  - `vcs` (≈629), `comments_route` (≈3088), `_CommentsProv.kind` (≈3373–3411; внутрішній рядок `kind` лишається, якщо його
    читає лише `bin/state.py` — тоді перейменувати на `'implicit'` в обох місцях; ключ підпису ≈3380 — без змін видимого тексту),
    збірка (≈4261/4263).
  - `task_publish_meta` (≈4872) і `task_preview_gate` (≈4907): потрібне одне — «публікує модуль». Новий тотальний помічник
    `deai_modules.publish_module(space)` → `Module` або `None` (ніколи не кидає; `Implicit`, `None`, `ModuleError`, збій — `None`;
    бере те саме рішення, що `capabilities(space)['publish']`, з тим самим кешем: `capabilities` зберігає поруч сирі
    постачальники, а назовні віддає `api_value`). Обидві функції: `mod = deai_modules.publish_module(space)` замість
    `space and layer_on() and request_space_id() is not None` + `pub in (None, 'legacy')`. Для вимкненого шару й незафіксованого
    простору `space` — `IMPLICIT` чи `None` → `None` (як у 0.15.0: «модулів нема»). ⛔ Звірити зі знімком `api` в обох режимах;
    розбіжність — стоп і звіт контролеру.
  - пароль превʼю (≈7118), ≈8131, `build='legacy'` (≈8152 — це `BUILD_KINDS`, контракт на диску: лишається, але вибір
    `'legacy'`/`'module'` — за `isinstance`), кеш-власник `who` (≈1985, ≈2107) — `deai_modules.api_value(prov)`.
  - `_liga_like(sp)` (≈1661): `spaces.integrations_for(sp)` (для `IMPLICIT` — `True`); `tasks_path()` (≈343) не чіпати.
  - `bin/overview_push.py` (≈118, ≈149), `bin/state.py` (≈301) — так само.
- [ ] **Step 2:** усі тести зелені БЕЗ змін очікувань ролей (обидва Python), `npm test`, знімки `before-4c1/4c3/4d1/4d2` без
  UPDATE; живі по одному: `comments`, `dashboard-role`, `tracker-role`, `notify-role`, `teams-mute`, `legacy-publish-cli`,
  `git-sync`, `tasks-home`, `tracks`. Коміт.

---

### Task 5: ізольований конфіг установки

**Files:** Modify `app/install_config.py`; Test `tests/test_implicit.py` (+ тести з переліку Task 1 Step 3, якщо контролер так
вирішив).

- [ ] **Step 1: тести (червоні):** у тимчасовому HOME з файлами `.claude/pipeline-feedback/jira-email|jira-token` і з
  виставленими вигаданими `SUPABASE_URL`/`SUPABASE_KEY`/`JIRA_EMAIL`/`JIRA_TOKEN`: під `DC_TASKS_FILE` (і окремо під
  `DC_NO_OVERVIEW`) `supabase_config()` → `(None, None)`, коли корінь фікстури пари не має, і пара з кореня, коли має;
  `jira_config()` → `(base, None, None)`/`(None, None, None)` без облікових у корені, і повна трійка з `jira_email`/`jira_token`
  кореня; поза ізоляцією — значення знімка `install` (оточення й файли працюють, як у 0.15.0).
- [ ] **Step 2: реалізація:** в `install_config` — `implicit.isolated()` (імпорт без циклу: `implicit` не імпортує нічого з
  ядра) відрізає джерела «оточення» і «`pipeline-feedback`»; корінь `DC_TASKS_FILE` — `jira_email`/`jira_token` (рядки,
  та сама перевірка форми, що в джерел оточення). Докстрінги обох функцій — новий порядок джерел і ⛔-причина.
- [ ] **Step 3:** тести з переліку Task 1 Step 3 перевести на ключі кореня фікстури (кожна зміна — рядок у звіті); мутація:
  прибрати перевірку `isolated()` → нові тести червоні. Усі тести зелені, `npm test`. Коміт.

---

### Task 6: прибрати міст і охоронець літерала

**Files:** Modify `app/implicit.py`; Test `tests/test_implicit.py` (клас `NoLegacyLiteral`).

- [ ] **Step 1: тест (червоний, поки міст є):** `NoLegacyLiteral` читає `app/*.py`, `bin/*.py` (через `ast`, а не regex):
  жодного порівняння (`Compare` з `Eq`/`NotEq`/`In`/`NotIn`), де одна зі сторін — рядок `'legacy'` (у т. ч. всередині
  кортежу/списку/множини). Дозволені місця — явний перелік `(файл, функція)` з причиною в коментарі тесту (очікувано:
  `spaces.py` — `IMPLICIT`/`_is_implicit`/поле `legacy`; `serve.py` — розбір `--legacy` і `BUILD_KINDS`; `tracks.py` — нічого).
  Окремо: `Implicit('x', …) == 'legacy'` → `False`.
- [ ] **Step 2:** прибрати `__eq__`/`__hash__` моста; будь-яке місце, що ще покладалося на рівність, — виправити (тести
  покажуть). Мутація: повернути одну гілку `prov == 'legacy'` у `serve.py` → `NoLegacyLiteral` червоний.
- [ ] **Step 3:** усі тести зелені (обидва Python), `npm test`, знімки без UPDATE. Коміт.

---

### Task 7: документи й версія 0.16.0

- [ ] `CHANGELOG.md` `[0.16.0] — unreleased`: що змінилось (неявний постачальник, шов, закон ізоляції, ізольований конфіг),
  «Deliberate differences» (ізольований конфіг; внутрішній API `provider()`; перейменовані константи), «Known limits» (спека).
- [ ] `README.md` — дорожня карта (4d-2 зроблено) і «Known limits»; `docs/design/spaces-and-modules.md` — «Stage 4d-2» і рядки
  15/117/515; `docs/modules/authoring.md` — абзац про `'legacy'`, якщо є (контракт модулів не змінюється); `package.json`
  0.16.0; спека — розділ «Implementation notes» з відхиленнями, прийнятими на ревʼю.
- [ ] Коміт.

---

## Після всіх задач (контролер)

Фінальне ревʼю всього етапу (Sonnet) → виправлення → повторне ревʼю → прогони на знімку (`npm test`, `/usr/bin/python3`, живі по
одному) → дата в CHANGELOG → тег `v0.16.0` → push (`"${SHA}:refs/heads/main"` + тег, `ls-remote`) → памʼять.
