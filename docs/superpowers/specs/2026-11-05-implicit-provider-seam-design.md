# Етап 4d-2: неявний постачальник замість літерала `'legacy'`, шов «шар вимкнено», ізоляція спільного стану (0.16.0)

Дата: 05.11.2026. Попередній етап — 4d-1 (0.15.0, напрямки простору). Дорожня карта — `docs/design/spaces-and-modules.md`.

## Рішення власника

- **26.10.2026 (етап 4):** чисте ядро + паритет; усе, що робить простір ЛІГА, стає загальним механізмом або модулем.
- **04.11.2026:** етап 4d — чотири підрелізи: 4d-1 напрямки (0.15.0, випущено 05.11) → **4d-2 шов «шар вимкнено» й ізоляція
  спільного стану без літерала `'legacy'` (ця спека, 0.16.0)** → 4d-3 явні модулі ЛІГИ з автоматичною міграцією конфігу з
  бекапом (0.17.0) → 4d-4 прапорець `integrations` і старі псевдоніми геть (0.18.0).

## Проблема

Шість ролей (`publish`, `comments`, `vcs`, `dashboard`, `tracker`, `notify`) у просторі ЛІГА вже виконують ВБУДОВАНІ модулі
(`vercel-publish`, `supabase-comments`, `git-sync`, `supabase-dashboard`, `jira-tracker`, `supabase-teams`). Але ядро
досі дізнається про це з рядка: `deai_modules.provider()` повертає `'legacy'`, і кожна роль у `app/serve.py` має свою
гілку `if prov == 'legacy':`, яка сама:

1. знаходить вбудований модуль (`catalog().get(...)`, `*.legacy_module()`);
2. збирає `ctx` з конфігу установки (`_comments_legacy_ctx`, `_vcs_legacy_ctx`, `dashboard/notify/tracker.legacy_ctx`);
3. вирішує ізоляцію тестів: шов-фейк (`DC_TEAM_FAKE`, `DC_TRACKER_FAKE`, `DC_TEAMS_FAKE`), відмова при `DC_TASKS_FILE` /
   `DC_NO_OVERVIEW`, — щоразу трохи інакше.

Розвідка 05.11 нарахувала ≈40 виконуваних місць з літералом (≈20 гілок `== 'legacy'` у `serve.py`, `bin/overview_push.py`,
`bin/state.py`, константи `LEGACY_*` у `deai_modules.py`) і ≈450 згадок у тестах. Окремо від літерала:

- **Шар вимкнено** визначає `spaces.layer_on()` («`DC_TASKS_FILE` без `DEAI_HOME`»), але перевірка розсипана: `provider()`
  коротко замикає `not layer_on() or request_space_id() is None` → `'legacy'`, а `serve.py` повторює ту саму умову руками
  (`task_publish_meta`, `task_preview_gate`, `tasks_path`, `_liga_like`), `deai_modules` ще й у ключі кешу. Єдиного «простору
  запиту» для цього випадку нема: хтось бере `IMPLICIT`, хтось `None`.
- **Ізоляція спільного стану** записана лише для гілок `'legacy'` і різниться між ролями: `dashboard`, `tracker`, `notify`
  мають шов-фейк і відмову; `_overview_sync` дивиться на `DC_TASKS_FILE` лише для `'legacy'`, а `DC_NO_OVERVIEW` — для всіх;
  `comments`, `publish`, `vcs` ізоляції в коді не мають — тести тримаються на підмінах (`sbconf.py`, `fake_npx.py`,
  `DC_MIRRORS_DIR`). При цьому `supabase_config()` і `jira_config()` у будь-якому прогоні читають СПРАВЖНІ змінні
  оточення (`SUPABASE_URL`/`SUPABASE_KEY`, `JIRA_EMAIL`/`JIRA_TOKEN`) і файли `~/.claude/pipeline-feedback/jira-*`: тест, що
  забув підміну, дістає облікові машини.

## Мета

1. **Один обʼєкт замість рядка.** `provider()` повертає `Module`, **`Implicit`** (неявний постачальник: роль, вбудований
   модуль, `ctx` з конфігу установки) або `None`. Жодна гілка ядра не порівнює постачальника з `'legacy'`.
2. **Одна таблиця неявних постачальників** — роль → (вбудований модуль, збирач `ctx`, шов-фейк, чи це спільний стан).
3. **Один шов «шар вимкнено»** — `spaces.request_space()`: запис простору запиту, а коли шар вимкнено чи простір запиту не
   зафіксовано — копія `IMPLICIT`. Перевірки `layer_on()` поза `spaces.py` і реєстровими інструментами зникають.
4. **Один закон ізоляції** — функція `isolated()` і маршрут `implicit.route(prov)` з однаковим порядком для всіх ролей
   (шов-фейк → відмова в ізольованому прогоні → справжній виклик).
5. **Ізольований прогін не бачить облікових машини**: `supabase_config()` / `jira_config()` в ізольованому прогоні читають
   лише корінь `DC_TASKS_FILE`, без змінних оточення й без `~/.claude/pipeline-feedback/`.
6. **Публічний контракт не змінюється**: `capabilities.<role>` у `/api/spaces`, `/api/space`, `/api/task` лишається
   `'legacy'`; `manifest.json` збірки — `"build": "legacy"|"module"`; JS не змінюється. Рядок `'legacy'` у ядрі живе лише у
   ОДНІЙ точці відображення назовні (`api_value`) і в іменах, що йдуть у 4d-3/4d-4 (див. «Не мета»).

## Не мета

- Явні модулі ЛІГИ в `space.json` і міграція конфігу — 4d-3 (тоді `capabilities` ЛІГИ стануть ідентифікаторами модулів, і
  `'legacy'` зникне з API природно; міняти контракт двічі не будемо).
- Прапорець `integrations`, псевдоніми `gitlab_*`, `profile` як синонім, `_liga_flow` — 4d-4.
- Ідентифікатор неявного простору `IMPLICIT['id'] == 'legacy'`, поле реєстру `legacy`, прапорець CLI `--legacy`,
  `BUILD_KINDS` / `"build": "legacy"` у маніфесті (контракт на диску для `ops/reseal_gate.py`), адаптер `tracks.legacy_tracks`
  — лишаються як є.
- Ізоляція модулів звичайного простору (див. §4: їхній конфіг — власний конфіг простору, а не спільний стан).

## Дизайн

### 1. `Implicit` — неявний постачальник

Новий модуль `app/implicit.py`:

```python
class Implicit:
    """Неявний постачальник ролі в просторі з інтеграціями без явного модуля (ЛІГА) чи при вимкненому шарі."""
    role: str           # одна з IMPLICIT_ROLES
    module_id: str      # вбудований модуль ролі
    shared: bool        # True — ctx несе спільний стан ЛІГИ (Supabase команди, Jira, Teams, віддалений хост)
    fake_env: str|None  # шов-фейк ролі (змінна оточення) або None
    def module(self) -> Module          # вбудований модуль з каталогу БЕЗ простору; нема/не ok → ModuleError('module-error')
    def ctx(self) -> dict               # збирач ctx ролі з конфігу установки; нема конфігу → ModuleError('<role>-unconfigured')
```

`IMPLICIT_ROLES` (заміна `LEGACY_ROLES`; той самий склад і порядок) і таблиця:

| роль | модуль | `ctx` (наявний збирач переїжджає сюди без змін логіки) | шов-фейк | `shared` |
|---|---|---|---|---|
| `publish` | `vercel-publish` (режим `cli`) | наявний з `_publish_legacy_call` | — (тести: `fake_npx`) | так |
| `comments` | `supabase-comments` | `_comments_legacy_ctx` | — (тести: підміна `supabase_config`) | так |
| `vcs` | `git-sync` | `_vcs_legacy_ctx` | — (тести: `DC_MIRRORS_DIR`) | так |
| `dashboard` | `supabase-dashboard` | `dashboard.legacy_ctx(*supabase_config())` | `DC_TEAM_FAKE` | так |
| `tracker` | `jira-tracker` | `tracker.legacy_ctx(*jira_config())` | `DC_TRACKER_FAKE` | так |
| `notify` | `supabase-teams` | `notify.legacy_ctx(*supabase_config())` | `DC_TEAMS_FAKE` | так |

Константи `LEGACY_ON_ERROR_ROLES` і `STRICT_LEGACY_ROLES` перейменовуються на `IMPLICIT_ON_ERROR_ROLES` і
`STRICT_IMPLICIT_ROLES` з тим самим складом і тією самою семантикою (`_provider_for`, `capabilities`). Екземпляри `Implicit`
— незмінні синглтони за роллю (`implicit.for_role(role)`); порівнюються `isinstance(p, Implicit)`.

**Межа відображення.** `deai_modules.api_value(p)`: `Module` → `p.id`, `Implicit` → `'legacy'`, `None` → `None`. Цим і лише
цим користуються `capabilities()`, `/api/spaces`, `/api/space`, `/api/task` та будь-яке інше місце, що віддає постачальника
назовні. `capabilities()` лишається ТОТАЛЬНОЮ й повертає ті самі значення, що 0.15.0.

### 2. Шов «шар вимкнено» — `spaces.request_space()`

```python
def request_space():
    """Запис простору запиту. Шар вимкнено чи простір запиту не зафіксовано → dict(IMPLICIT), БЕЗ читання реєстру.
    Інакше — active_space() (може кинути SpacesError; None — простору нема)."""
```

- `deai_modules.provider(role, space=None)`: `space = spaces.request_space()` замість короткого замикання; `IMPLICIT` іде тим
  самим `_provider_for`, і той для простору з інтеграціями без явних модулів повертає `implicit.for_role(role)` ДО каталогу —
  як сьогодні, без читання `space.json`, реєстру й каталогу. ⛔ `IMPLICIT` має `path: ''`: `_provider_for` для нього
  (`spaces._is_implicit`) НЕ кличе `space_modules` узагалі — інакше відносний `space.json` читався б з поточної теки процесу;
  закріплюється тестом із `space.json` у поточній теці.
- `serve.py`: `task_publish_meta` і `task_preview_gate` замість `space and layer_on() and request_space_id() is not None`
  питають `isinstance(<постачальник publish>, Module)`; `_liga_like(sp)` = `spaces.integrations_for(sp)` (для `IMPLICIT` —
  `True`); ключ кешу `deai_modules` (:1258) бере ідентифікатор `request_space()`.
- `layer_on()` лишається в `spaces.py` (сам шар: реєстр, `space.json`, `spaces-off`), у `tasks_path()` і в `bin/roots.py`,
  `bin/registry.py` (інструменти реєстру). Більше ніде.

### 3. Ролі в ядрі — один шлях

Кожна роль у `serve.py` (і `bin/overview_push.py`, `bin/state.py`) веде так:

```python
prov = deai_modules.provider(role)            # Module | Implicit | None
if prov is None: ...                          # як сьогодні
if isinstance(prov, Implicit):
    kind, fake = implicit.route(prov)         # §4: 'fake' / 'isolated' / 'live' — відповідь кожного випадку дає роль
    module, ctx = prov.module(), prov.ctx()   # лише для 'live'
else:
    module, ctx = prov, deai_modules.module_ctx(space, prov)
res = deai_modules.call(module, fn, ctx, ...)
```

Особливості ролей, які лишаються (вони не про літерал): канал коментарів ЛІГИ (`comment_channel`) проти `channel_for`;
дзеркала 0.7.0 і `mirror_flat` у `vcs`; `_publish_legacy_call` лишається ЄДИНОЮ точкою публікації ЛІГИ (тести її
підміняють) — лише всередині бере `Implicit`; кеш-власник `who` (`serve.py` :1985, :2107) бере `api_value(prov)`.

### 4. Закон ізоляції

`implicit.isolated()` — ОДНА функція: `bool(os.environ.get('DC_TASKS_FILE') or os.environ.get('DC_NO_OVERVIEW'))`.

`implicit.route(prov)` → `('fake', шлях)` | `('isolated', None)` | `('live', None)` — однаковий порядок для всіх ролей;
форму відповіді кожного випадку лишає роль (у 0.15.0 вони різні: `[]`+текст, `None`, `OSError`):

1. **шов-фейк** (`prov.fake_env` задано й змінна непорожня) — локальний обробник ролі (наявний код фейків `dashboard`,
   `tracker`, `notify` переїжджає в таблицю без змін поведінки й формату файлів); пише лише у свій файл;
2. **ізольований прогін** (`isolated()` і `prov.shared`) для ролей, що МАЮТЬ відмову сьогодні (`dashboard`, `tracker`,
   `notify`, синк дашборда), — та сама відмова й той самий текст, що 0.15.0 (`TEAM_ISOLATED`, `OSError('ізольований
   конфіг…')`…). Ролі `publish`, `comments`, `vcs` відмови не дістають (їхні живі тести ходять у локальні фейки через підміни,
   а не через шов) — їх захищає п. 5 нижче;
3. інакше — `(prov.module(), prov.ctx())`.

**Конфіг установки в ізольованому прогоні** (`app/install_config.py`): коли `isolated()`, `supabase_config()` бере пару
ЛИШЕ з кореня файла `DC_TASKS_FILE` (без `SUPABASE_URL`/`SUPABASE_KEY` з оточення); `jira_config()` бере `jira_base` з того
самого файла, а облікові — ЛИШЕ з його кореня (`jira_email`/`jira_token`, нові необовʼязкові ключі для тестових фікстур), ні з
оточення, ні з `~/.claude/pipeline-feedback/`. Підміни `serve.supabase_config` / `serve.jira_config` у тестах працюють як
раніше (вони стоять вище). Тести, що сьогодні покладаються на змінні оточення під `DC_TASKS_FILE`, план знаходить у Task 1
(знімок) і переводить на ключі кореня фікстури.

**Модулі звичайного простору** закону не підлягають: їхній `ctx` — `space.json` і `secrets.json` САМОГО простору (у тестах —
тимчасовий `DEAI_HOME`), а не спільний стан ЛІГИ. Це фіксується в документації як закон, а не прогалина.

`_overview_sync` (синк дашборда): ворота ті самі — для `Implicit` відмова при `isolated()`; для модуля — як сьогодні
(`DC_NO_OVERVIEW` до вирішення постачальника лишається).

## Паритет і перевірки

- **Знімок 0.15.0 до змін коду** — `tests/fixtures/implicit/before-4d2.json` генератором `tests/make_before_4d2.py`
  (охоронець fail-closed проти 6e68250, як `make_before_4d1.py`): `capabilities` для просторів ЛІГА / звичайний / шар вимкнено
  / нечитабельний `space.json` у ЛІГИ й у звичайного / свій модуль «на папері» / збій відбитків; тіла `/api/spaces`,
  `/api/space`, `/api/task` (ключі постачальників, `publish_gate`, `preview_gate`); для кожної ролі з фейком — результат
  через шов; для кожної ролі з відмовою — код/текст відмови в ізольованому прогоні; `manifest.json` збірки ЛІГИ
  (`build`); ключі кешу `who`. Після змін — той самий знімок без UPDATE-прапорців.
- **Метрика літерала:** тест-охоронець — у `app/**/*.py` і `bin/**/*.py` нема порівнянь постачальника з `'legacy'`
  (`== 'legacy'`, `!= 'legacy'`, `in (... 'legacy' ...)` щодо постачальника); дозволені входження перелічені явно
  (`api_value`, `IMPLICIT['id']`, `BUILD_KINDS`, `--legacy`, поле реєстру `legacy`, `legacy_tracks`) — тест читає
  джерела, а не рахує число. Доказ мутацією: повернутий `== 'legacy'` червонить тест.
- **Шов шару:** `provider()` при вимкненому шарі й при незафіксованому просторі запиту не читає реєстр, `space.json` і
  каталог (підрахунок викликів, як у 4d-1); `request_space()` повертає копію (зміна результату не чіпає `IMPLICIT`).
- **Ізоляція:** для кожної ролі таблиці — фейк має перевагу над відмовою; відмова не кличе модуль і не відкриває мережу
  (сокет-трипвайр); `supabase_config()` / `jira_config()` в ізольованому прогоні з виставленими справжніми змінними оточення
  й файлами `pipeline-feedback` у тимчасовому HOME — `(None, …)`, коли корінь `DC_TASKS_FILE` їх не має.
- Кожен новий охоронець доводиться мутацією (`python3 -B`).
- Повні прогони: `npm test`, обидва Python (3.x і `/usr/bin/python3` 3.9), живі тести по одному на знімку.

## Свідомі відмінності від 0.15.0

- В ізольованому прогоні `supabase_config()` / `jira_config()` не бачать змінних оточення й `~/.claude/pipeline-feedback/`
  (раніше бачили). Поза ізоляцією — як було.
- Внутрішній API: `deai_modules.provider()` / `comments_provider()` / `team_resolve()` тощо повертають `Implicit`, а не рядок
  `'legacy'`; `LEGACY_*`-константи перейменовано на `IMPLICIT_*` без псевдонімів (`ctx` модулів констант не несе; тести
  оновлюються в тому самому коміті).

## Відомі обмеження

- `'legacy'` лишається в публічному API (`capabilities`), у маніфесті збірки, в ідентифікаторі неявного простору й у полі
  реєстру — до 4d-3/4d-4.
- `bin/overview_push.py`, запущений руками поза ядром, і `ops/` не знають про `isolated()` (не тестовий шлях).
- `bin/registry.py` обчислює `TASKS_PATH` під час імпорту — не змінюється.

## Документи

CHANGELOG `[0.16.0]`, README (дорожня карта, «Known limits»), `docs/design/spaces-and-modules.md` «Stage 4d-2»,
`docs/modules/authoring.md` (абзац «неявний постачальник» замість `'legacy'`, якщо він там є).

## Чекліст релізу

Спека погоджена → план → реалізація задачами (виконавець і ревʼюер — Sonnet) → фінальне ревʼю → прогони на знімку → дата в
CHANGELOG → тег `v0.16.0` → push → памʼять.
