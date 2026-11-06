# Етап 4d-3c: міграція простору ЛІГА, третій крок — `publish` (0.19.0)

Дата: 06.11.2026. Попередній етап — 4d-3b (0.18.0, випущено 06.11.2026; спека `2026-11-06-liga-migration-b-design.md`). Дорожня
карта — `docs/design/spaces-and-modules.md`. Номери рядків нижче — за кодом на `v0.18.0` (HEAD `6ce8e61`); код — правда, спека — намір.

## Рішення власника

- **26.10.2026 (етап 4):** чисте ядро + паритет; усе, що робить простір ЛІГА, стає загальним механізмом або модулем; для людини
  нічого не змінюється.
- **04.11.2026:** 4d-3 — явні модулі ЛІГИ з **автоматичною міграцією конфігу з бекапом**.
- **05.11.2026:** 4d-3 ділиться на 4d-3a (0.17.0), 4d-3b (0.18.0) і **4d-3c (0.19.0, ця спека)** — `publish`; 4d-4 стає 0.20.0.
  Секрети **копіюються**, оригінали лишаються (корінь старого `tasks.json`, оточення, `pipeline-feedback`) аж до 4d-4.
- **06.11.2026:** 4d-3a (0.17.0) і 4d-3b (0.18.0) випущено.
- **06.11.2026:** власник доручив іти далі («Продолжаем следующий этап… Если нет продуктовых вопросов, работай автономно»).
  **Нових продуктових питань ця спека не породила**: кожна прогалина нижче вирішена за принципом паритету (26.10.2026) — це
  похідні рішення (розділ «Похідні рішення»), а не вибір власника.

## Проблема

Після 0.18.0 ЛІГА має явними `tracker`, `dashboard`, `notify`, `comments`, `vcs` і напрямки. Лишилась `publish`: її веде
неявний постачальник `Implicit('publish', 'vercel-publish', True, None)` (`app/implicit.py:22`), а `capabilities.publish` каже `'legacy'`.
Публікація ЛІГИ — не «просто модуль `vercel-publish`»: це окрема гілка `Handler._publish` (`app/serve.py:8244`–`8341`), що робить
п'ять речей, яких шлях модуля (`_publish_by_url`, `serve.py:4865`) не робить:

1. **Стан проєкту в `tasks.json`, а не в `iterations.json`.** Імʼя `pv-NNNNNNNN` мінтиться ОДИН раз на задачу в `tasks.json`
   (`_vercel_project`, `:4998`; відмовляє, якщо `publish_url` є, а `vercel_project` нема), скоуп — `vercel_scope`
   (`_remember_vercel_scope`, `:5036`), обидва їдуть у реєстр (`_registry_push`, `:8312`). Модуль-шлях бере `state` із
   `publish_remote` (`_stored_publish_state`, `:4855`) — ЛІГА його не пише ніколи (`publish_remote` лише в `:4923`), тож при
   модуль-шляху кожна опублікована задача отримала б **новий проєкт і новий URL** (старий URL уже в менеджера).
2. **`legacy_state: True`** (`_publish_legacy_call`, `:5103`): модуль приймає зі стану будь-яке безпечне імʼя (старі `dc-…`) і скоуп; у
   звичайному шляху стан недовірений (4b-1, «Поправки»).
3. **Пароль превʼю** — не секрет модуля `password` (порожній = без гейта), а `preview_password(cfg, task)` (`:4154`): пароль задачі →
   пароль кореня → типовий `1100` (`DEFAULT_PREVIEW_PW`, `:4151`); гейт у DOM, обовʼязковий, змінюється з екрана
   (`/api/preview-password`, `:7198`).
4. **Збірка з міткою `build: 'legacy'`** (`:8265`): лише такі збірки перепечатує `ops/reseal_gate.py` (мітку `module` пропускає).
5. **Побічні дії й ключі відповіді:** `git_autocommit` (`:8340`), `_registry_push` (`:8312`), `_overview_sync` (`:8341`), запис
   `publish_url`/`published_at`/`publish_verified`, ключі `deploy_url`/`domain_warning`/`not_task_link`/`verify_error`/`verify_hint`/
   `deploy_error`/`deploy_blocked`/`cleanup_warning` — і коментарі збірки з каналом ЛІГИ (`publish_comments(…)` з `module_publish=False`, `:8264`).

Модуль-шлях відрізняється й тим, що `publish_comments(module_publish=True)` ВІДМОВЛЯЄ для коментарів із `shared_state` (`:4354`): збірка
модуля не несе Supabase ЛІГИ.

Урок 4d-3a/4d-3b: **ЛІГА — не тип постачальника**. Після міграції `publish` ЛІГИ стане `Module`, а `Handler._publish`,
`/api/preview-password`, `task_preview_gate`, `task_publish_share` і JS кажуть «ЛІГА» там, де бачать `Implicit`/`'legacy'`.
Тому ключове рішення цього етапу — **один предикат «шлях публікації ЛІГИ»**, а не ще одна копія поведінки ЛІГИ в модулі.

## Мета

1. **Паритет для людини:** ті самі проєкти й URL (без нових), той самий скоуп, пароль `1100`/пароль задачі/пароль кореня, `#k=` у
   «Копіювати посилання», ті самі побічні дії, ключі відповіді й тексти.
2. **`publish` ЛІГИ — явний вбудований модуль** `vercel-publish` у `space.json` (картка на «Підключеннях»), без секретів.
3. **Міграція — третій незалежний крок `liga-4d3c`** у `app/liga_migrate.py`: свій бекап, позначка, відкат; відкат LIFO на три кроки.
4. **Після 0.19.0 мігрована ЛІГА віддає id модулів для всіх шести ролей**; `'legacy'` лишається лише для немігрованої/запасної
   (вимкнений явний запис) ЛІГИ до 4d-4.

## Не мета

- Перенесення пароля превʼю (`tasks.json`) і `vercel_project`/`vercel_scope` у `space.json`/реєстр модуля — 4d-4.
- Прибирання неявного шляху (`Implicit` лишається запасним до 4d-4), токен-вхід для ЛІГИ, зміна `static-publish`.
- Зняття відмови `publish_comments(module_publish=True)` для `shared_state` (див. «Поправка до 4d-3b» — вона лишається).
- `ssh_key`/`host_ip`/`gitlab_*`, `integrations`, `profile` — 4d-4.

## Дизайн

### 1. Налаштування `compat` модуля `vercel-publish` і ОДИН предикат

`app/modules/vercel-publish/module.json` (версія 1.1.0 → 1.2.0) дістає `compat` (`select`, формат `options` як у 4d-3a/4d-3b: `""` —
«Немає», `"design-canvas"` — «design-canvas (ЛІГА): проєкти й скоуп із tasks.json, пароль превʼю задачі/кореня/1100»), типово `""`,
`required: false`. Підпис попереджає: у режимі `design-canvas` `auth`, `team` і `password` запису **не читаються** (гілка ЛІГИ бере
`auth: cli`, `team: ''` зашито в `_publish_legacy_ctx`, `serve.py:5093`–`5100`, а пароль — з `tasks.json`), а зміна значення на
живому просторі перемикає публікацію на модуль-шлях (нові проєкти, інші URL).

**Один предикат** `deai_modules.publish_legacy_path(prov, space=None)` = `isinstance(prov, Implicit)` **або** (вбудований `Module`
(`origin == 'builtin'`), `id == 'vercel-publish'` і `compat_of(space, 'vercel-publish') == "design-canvas"`). Тотальний (збій → `False`),
`space=None` для `Module` → `spaces.active_space()`. Захист за `origin` і `id` — як у предикатах 4d-3b: свій модуль міг би оголосити власне
`compat`. Предикат живе в `deai_modules` (поруч із `compat_of`, `:2098`), а не в `serve`, бо його потребує `publish_module` (`:1982`), а
`serve` імпортує `deai_modules`, не навпаки.

### 2. Споживачі ядра: що перемикається на предикат

Повний перелік (скаут `isinstance(…, Implicit)` і `publish_module(` за `app/`, `bin/`, `ops/`; поза ними рішень про публікацію ЛІГИ нема):

| Місце | Сьогодні | Після |
|---|---|---|
| `Handler._publish` (`serve.py:8240`–`8246`): `prov is None` → 409; `not isinstance(prov, Implicit)` → `publish_with_module`; інакше гілка ЛІГИ | неявний → гілка ЛІГИ | `not publish_legacy_path(prov)` → `publish_with_module`; предикат істинний → гілка ЛІГИ **без змін** (проєкти/скоуп/`legacy_state`, гейт, `build='legacy'`, коментарі `module_publish=False`, усі побічні дії й ключі) |
| `Handler._preview_password` (`:7219`): `league = isinstance(provider('publish'), Implicit)`, інакше 409 | неявний | `publish_legacy_path(prov)` (`ModuleError` → не ЛІГА, як було) |
| `task_preview_gate` (`:4993`), `task_publish_share` (`:4962`) — обидва питають `deai_modules.publish_module(space)` | `Module` → стан `'module'` / поля `publish_*` | **`publish_module(space)` повертає `None`, коли предикат істинний** (його докстрінг уже каже «`Implicit` → `None`»); самі функції не міняються — одне місце замість двох |
| `publish_comments` (`:4354`) | відмова `module_publish and (Implicit або shared_state)` | без змін: шлях ЛІГИ викликає `module_publish=False`, а справжня збірка МОДУЛЯ й далі не несе Supabase ЛІГИ |
| `publish_with_module` (`:4612`), `_publish_by_url` (`:4865`) | модуль-шлях | без змін; ЛІГА сюди не потрапляє |
| `/published/…` (`:8719`) | лише `static-publish` | без змін |
| `_registry_push`, `_overview_sync` | рішення за роллю `dashboard`/ізоляцією | без змін |

Охоронець (AST, як `TextPredicateGuard` у `tests/test_liga_migrate_b.py:947`): у `serve.py` у функціях `_publish`, `_preview_password`,
`task_preview_gate`, `task_publish_share` жодного `isinstance(…, Implicit)` і жодного прямого `provider('publish')`-порівняння з типом;
`publish_module(` у `serve.py` лише в цих двох споживачах. `tests/test_implicit.py:650` `NoLegacyLiteral` лишається чинним.

### 3. UI: `compat.publish` і один предикат у моделі

`deai_modules.COMPAT_ROLES`/`COMPAT_ALLOWED` (`:2113`/`:2115`) додають `('publish', 'vercel-publish')` і `'publish': COMPAT_DESIGN_CANVAS`;
`compat_view` (`:2118`) віддає `{publish: 'design-canvas'}` лише для явного вбудованого модуля з непорожнім `compat` (ключ — поруч із
`capabilities`, як у 4d-3b; `serve.space_view`/`spaces_listing`, `:5266`/`:5287`, без змін).

JS: ЄДИНА правка рішення — `isLegacyPublish` (`app/spaces-model.js:572`):
`caps.publish === 'legacy' || space.compat?.publish === 'design-canvas'` (як `isLegacyVcs`, `:292`–`:297`). Усе інше читає її:
`isRemotePublish` (`:597`–`:599`), `previewTarget` (`:631`–`:639`), `publishReaction` (`:813`–`:816`), `pwView` (`:835`–`:836`),
`bar-model.js:332` (рядок `pubpw`, `:360`, і `notes`, `:372`), `app.js` (`:882`, `:997`, `:1954`–`:1958`, `:2149`, `:2180`–`:2207`).
Нового літералу порівняння в цих місцях не зʼявляється. `isVercelPublish` (`:799`) лишається: `publishReaction` перевіряє легасі ЩЕ ДО нього.

Екран «Підключення»: картка `vercel-publish` показує запис. `disableConsequences` (`connections-model.js:313`–`:319`) для ролі, яку
веде явний модуль у просторі з інтеграціями (`LEGACY_ROLES`, `:305`), віддає `kind: 'legacy'`; текст `cnDisableLegacy`
(«знову виконуватиме вбудована інтеграція ЛІГА») **лишається правдивим**: вимкнений запис → `_provider_for` повертає `Implicit` (для
`publish` у просторі з інтеграціями — `deai_modules.py:1849`) → та сама гілка ЛІГИ. Те саме, якщо вбудований модуль не завантажився
(`m.status != 'ok'` — не переможець).

### 4. Міграція: третій крок `liga-4d3c`

`app/liga_migrate.py`: `ROLE_MODULES_C = (('publish', 'vercel-publish'),)`, `_entries_c`, `STEP_C = Step('liga-4d3c', ROLE_MODULES_C, False,
'-liga-4d3c', <STAMP_RE c>, _entries_c)` за зразком `STEP_B` (`:195`–`:364`), `ALL_STEPS = (STEP_A, STEP_B, STEP_C)`. Механізм кроків
4d-3b (`held` раннього кроку тримає наступні, `abort-*` і `skip-busy` зупиняють наступні на старті, `skip-integrations-off`, LIFO,
`last.json` із `steps`) працює без змін — `_plan` ітерує `ALL_STEPS[:index]`.

**Що записує крок** (злиття; чужі ключі й модулі не чіпаємо):

- `publish` → `vercel-publish`: `{enabled: true, shared_state: true, settings: {auth: "cli", team: "", compat: "design-canvas"}}`,
  **секретів нема** (токена не існує: вхід — `vercel login` машини; пароль превʼю лишається в `tasks.json` — 4d-4). `auth: "cli"` — щоб
  «Перевірити» на картці (`vercel whoami`) було правдивим; сама гілка ЛІГИ значення не читає (§1).
- Коди пропуску ролі: `module-present` (`vercel-publish` уже є в `space.json`) і `publisher-present` — `_provider_for('publish', space,
  explicit_override=<поточні modules>)` уже вирішує `Module` (людина ввімкнула інший модуль публікації): крок його не перебиває, і не
  лишає вічного `abort-provider` на кожному старті. Без Supabase/адрес кодів нема: нічого копіювати.
- Позначка `migrations["liga-4d3c"]` = `{at, roles, backup}` (без `tracks`).
- Перевірка `abort-provider`: на розрахованому в памʼяті `space.json` `_provider_for('publish', …, explicit_override=…)` мусить вирішити
  саме `Module` `vercel-publish`, інакше крок нічого не пише.

**Відкат — LIFO на три кроки.** `restore <stamp-c>` повертає `space.json` і ліговий шматок секретів зі стану після 4d-3b. `restore
<stamp-a|b>` при застосованому пізнішому кроці — `refuse-later-applied`; `_applied_later` (`:835`) зараз називає ПЕРШИЙ застосований
пізніший крок — для трьох кроків називаємо **останній застосований** (його й треба відкочувати першим), щоб одна відмова вела прямо
до правильного бекапу. `--hold` пише `{held: true}` лише позначку цього кроку.

**Попередження про відкат (нове, і гостріше, ніж у 4d-3b):** 0.18 не знає `compat` у `vercel-publish` (невідоме налаштування
ігнорується), тож мігрований запис пішов би **модуль-шляхом: новий проєкт і новий URL для кожної опублікованої задачі, і без
гейта** (секрета `password` у записі нема). Перед відкатом на 0.18 — `bin/migrate_liga.py restore <stamp-c> --hold`; на 0.17 — c, потім b;
на 0.16 — c, b, a (кожен з `--hold`).

### 5. Закон ізоляції

У публікації ЛІГИ **нема шва й нема гілки ізоляції** (`implicit.for_role('publish')` не викликається в `serve.py`; `implicit.route`
— лише для `dashboard`/`tracker`/`notify`; `fake_env = None`, `implicit.py:22`): ізольований прогін (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) під
гілкою ЛІГИ викликає справжній `npx` за `_node_bin` (тести ставлять `tests/fake_npx.py` на `PATH` або підміняють `serve._node_bin`).
`_registry_push` (`:2603`: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` → `False`) і `_overview_sync` (`:7687`: гейти ролі `dashboard`) ізоляцію вже
мають, `git_autocommit` пушить лише за `_outbound_ok()`. Тому закон для мігрованого запису: **той самий, що для `Implicit`, бо запис іде
ТОЮ САМОЮ гілкою** (§2); нового коду ізоляції нема. «Перевірка» картки: `module_check_verdict` (`:5406`) уже віддає `isolated` для
будь-якого запису з `shared_state` — без `npx` і мережі. Охоплення доводить тест (§Паритет), а не припущення.

### 6. Значення API

`capabilities.publish` мігрованої ЛІГИ — `'vercel-publish'`; `'legacy'` лишається для немігрованої ЛІГИ, вимкненого запису, зламаного
вбудованого модуля й помилки рішення (`IMPLICIT_ON_ERROR_ROLES`, `deai_modules.py:126`). Дорожня карта й дизайн-документ казали «`'legacy'`
іде в 4d-3c» — це виправляється: він іде з 4d-4, разом з неявним постачальником.

## Паритет і перевірки

- **Знімок 0.18.0 ДО змін коду** — `tests/make_before_4d3c.py` + `tests/fixtures/liga-migration/before-4d3c.json`; генератор запускається
  проти `git archive v0.18.0` (рецепт і відмова на робочій теці — як `make_before_4d3b.py`; спільні помічники імпортуються з
  `make_before_4d3a.py`/`make_before_4d3b.py`), без мережі, у тимчасових `HOME`/`DEAI_HOME`, вигадані значення, фальшивий `npx` із
  `tests/fake_npx.py` і підмінений `_fetch_page` модуля. **Два стенди:** (1) ЛІГА, нічого не мігровано; (2) ЛІГА після 4d-3a+4d-3b
  (генератор запускає кроки A, B кодом 0.18). Знімається:
  - **`POST /api/publish`**: відповідь (порядок ключів), записи `tasks.json` (`vercel_project`, `vercel_scope`) і `iterations.json`
    (`publish_url`, `published_at`, `publish_verified`; `publish_remote` відсутній), журнал argv фальшивого `npx` (`link --project pv-…
    [--scope]`, `deploy --prod`, прибирання), мітка `build` у `manifest.json`, шиті сторінки (пароль `1100`/пароль задачі/пароль
    кореня; `authgate`), ін'єкція коментарів (канал, відсутність ключа Supabase в сторінках, де коментарі вимкнені), шпигуни побічних
    дій (`git_autocommit`, `_registry_push`, `_overview_sync` — порядок і аргументи), гілки: `build_only`, без Node (`deploy_blocked`),
    `ModuleError` (`vercel-login`/`vercel-scope`/без адреси), `verify_error: vercel_protection`, друга публікація (той самий проєкт і скоуп);
  - **`GET /api/task`**: `preview_password`, `preview_password_custom`, `preview_gate` (`state`), відсутність `publish_gate`/`publish_share_url`;
  - **`POST /api/preview-password`**: 200 (відповідь, запис у `tasks.json`) і 409 для простору без ЛІГИ;
  - **`GET /api/spaces`**: `capabilities`, `compat`; читання предикатів JS через `node` на записі: `isLegacyPublish`, `pwView`,
    `previewTarget`, `copyUrl` (`#k=<пароль>&p=<сторінка>`), `publishReaction`, `barState` (рядок `pubpw`, `legacy`); картки
    `GET /api/modules` для `vercel-publish`.
- **`Before4d3cShape`** — структурні перевірки самого знімка (наявність і повнота секцій), як `Before4d3bShape`.
- **`AfterMigrationParity4d3c`** — ті самі сценарії на ЛІГІ після кроку C (обидва стенди) дають те саме, крім явного **`EXPECT_DIFF`**:
  `capabilities.publish` = `'vercel-publish'`; `/api/spaces` має `compat.publish`; картка `vercel-publish` увімкнена, з налаштуваннями
  (секретів нема); нічого більше — тест падає на кожній зайвій різниці.
- **НЕізольований тест `RealPublishNonIsolated`:** мігрований запис, тимчасовий `HOME`, `tests/fake_npx.py` на `PATH`, `DC_TASKS_FILE`
  НЕ виставлено, шпигуни замість `_registry_push`/`_overview_sync`/пушу: перша публікація мінтить `pv-…` і пише скоуп; друга — **той самий
  проєкт, той самий URL, той самий скоуп**, `link --project` зі стану `tasks.json`, пароль `1100`; `publish_remote` у `iterations.json`
  НЕ зʼявляється; відмова модуль-шляху (`publish_comments(module_publish=True)` для коментарів `shared_state`) не змінилась.
- **Кроки міграції:** по тесту на кожен код пропуску/відмови (`module-present`, `publisher-present`, `skip-held` від a чи b,
  `skip-integrations-off`, `skip-nothing`, `abort-provider`); ідемпотентність; бекап повний (0700/0600, sha256); `restore` побайтно;
  **LIFO на три кроки** (`restore <a>`/`<b>` при застосованому c → `refuse-later-applied` з ім'ям c; після `restore <c>` — b, потім a);
  три кроки на одному старті (три бекапи, порядок; `abort` раннього не пускає наступні; `skip-nothing` не блокує); жодних значень
  секретів у звітах (секретів кроку нема — перевірка, що `secrets.json` не змінився); невідомі ключі `space.json` збережено.
- **Предикат і споживачі:** матриця `publish_legacy_path` (`Implicit`; вбудований + `compat`; вбудований без `compat`; свій модуль із
  тим самим id/`compat`; `static-publish`; `None`; зламаний `space.json`); `publish_module` повертає `None` для мігрованого запису й `Module`
  для звичайного `vercel-publish`; `/api/preview-password`, `task_preview_gate`, `task_publish_share` — по сценарію на кожен; AST-охоронець §2.
- **JS:** `tests/spaces-model.test.mjs`/`bar-model.test.mjs`/`connections-model.test.mjs` — `isLegacyPublish` із `compat.publish`;
  `legacy-golden` — без перезйомки.
- **Живий тест** (розширення `tests/live/liga-migrate.test.mjs`, тимчасовий `DEAI_HOME`, ізольований прогін із `DC_MIGRATE_LIGA=1`): третій
  бекап; картка `vercel-publish` увімкнена; `capabilities.publish == 'vercel-publish'`; клік «Опублікувати» з фальшивим `npx` на `PATH`
  (стиль `tests/live/legacy-publish-cli.test.mjs`) дає ті самі `link`/`deploy` argv і той самий текст помилки, що до міграції; смуга показує
  пароль превʼю (рядок `pubpw`); другий старт нічого не пише. ⚠️ Збереження самого URL у живому тесті неможливе без мережі (модуль
  перевіряє сторінку після знайденої адреси; `legacy-publish-cli` свідомо дає вивід БЕЗ адреси) — його доводить `RealPublishNonIsolated`.
- **Мутаційні докази** (кожна нова перевірка «падає, коли зламати»; `python3 -B`, один рядок, відновлення побайтно): предикат — гілка
  `Implicit` → `False`; гілка `compat` → `False`; прибрано захист `origin`/`id`; `publish_module` без фільтра предиката; `_publish` назад на
  `isinstance(prov, Implicit)`; `_preview_password` так само; `compat_view` без `publish`; JS `isLegacyPublish` без `compat`; `STEP_C` без
  `compat` у записі; `shared_state` → `False`; порядок `ALL_STEPS`; `_applied_later` повертає перший, а не останній; `publisher-present` вимкнено.
- Повні прогони (`npm test`, обидва Python, живі по одному — без паралельних сусідів), голдени без перезйомки.

## Свідомі відмінності від 0.18.0

- ЛІГА з конфігом після першого старту 0.19 — `publish` явний (`capabilities.publish == 'vercel-publish'`, картка на «Підключеннях»).
- Налаштування `auth`/`team`/`password` на картці `vercel-publish` у режимі `design-canvas` декоративні (гілка ЛІГИ їх не читає); підпис
  `compat` каже це вголос. Пароль превʼю міняється, як і раніше, зі смуги.
- `restore <a>` при застосованих b і c називає в відмові ОСТАННІЙ застосований крок (було: перший пізніший).
- **Виправлення нотатки 4d-3b:** відмова `publish_comments(module_publish=True)` для коментарів із `shared_state` **не знімається** (4d-3b
  спека, «Збірка превʼю модулем», рядки 192–194 і «Відомі обмеження», рядок 260, казали «знімається в 4d-3c»). Вона й далі потрібна:
  ЛІГА публікує гілкою ЛІГИ (`module_publish=False`, коментарі працюють), а відмова стереже справжні збірки МОДУЛЯ (інший модуль публікації,
  `vercel-publish` без `compat`) від виходу ключа Supabase ЛІГИ в превʼю. У спеку 4d-3b додається однорядковий вказівник на цю.

## Відомі обмеження

- **Відкат на 0.18 після кроку C НЕБЕЗПЕЧНИЙ без `restore <stamp-c> --hold`:** модуль-шлях, нові URL, превʼю без гейта (§4).
- Ручне вмикання `vercel-publish` у просторі ЛІГИ БЕЗ `compat` — свідома дія: модуль-шлях, нові проєкти й URL, пароль — секрет модуля.
  Картка про це не попереджає (`compat` — лише налаштування); попередження в підписі `compat`.
- Пароль превʼю, `vercel_project`, `vercel_scope` лишаються в `tasks.json` (4d-4); копій у `space.json` нема.
- Часткова міграція остаточна (як у 3a/3b); `skip-path-in-git`/`skip-no-path`, відсутність `flock` на Windows, гонка `run` із CLI проти правок
  з екрана — як раніше.
- Публікація в ізольованому прогоні — справжній `npx` (шва нема, і не було); ізоляцію дають лише підміни тестів (§5).

## Похідні рішення (за принципом паритету, не питання власнику)

1. **Не відтворюємо поведінку ЛІГИ в `publish_with_module`; гілку ЛІГИ зберігаємо й перемикаємо предикатом.** Одна гілка — одна поведінка,
   тести 4b-1 (`LegacyPublishViaModule`, `Dispatch`) лишаються зеленими.
2. **Предикат у `deai_modules` + `publish_module` його поважає** — урок 4d-3b: «ЛІГА» читається з одного місця.
3. **`shared_state: true` на записі `publish`** — для єдності з іншими ролями й вердикту `isolated` «Перевірки»; на маршрутизацію він не
   впливає (її вирішує `compat`).
4. **`publisher-present`** замість вічного `abort-provider`, коли людина вже ввімкнула інший модуль публікації.
5. **`_applied_later` називає останній застосований крок** — для трьох кроків.
6. **Живий тест не перевіряє URL** (немає мережі) — це `RealPublishNonIsolated`.

## Відхилені альтернативи

- **Відтворити поведінку ЛІГИ всередині `publish_with_module`/`_publish_by_url`** (читати `tasks.json`, `legacy_state`, пароль 1100, побічні
  дії): друга копія адаптера ЛІГИ в шляху модуля, що розійдеться з першою; змішує «звичайний простір» і «ЛІГА» в одній функції.
- **Засіяти `publish_remote` у `iterations.json` при міграції** (перенести проєкт/скоуп зі `tasks.json`): міграція не бачить усіх
  задач (`iterations.json` — по задачах у теках), стан і так недовірений у модуль-шляху (імена `dc-…` відхиляються), і пароль перестав би
  бути паролем ЛІГИ (`gate_pw` модуля = секрет `password`, порожній = без гейта) — змінюються URL чи пароль, тобто паритет втрачено.
- **Скасувати відмову `publish_comments` для `shared_state`:** не потрібно (гілка ЛІГИ не йде через `module_publish=True`) і відкрило б
  вихід ключа Supabase в збірку чужого модуля публікації.
- **Окремий ключ `legacy_path: true` у записі замість `compat`:** ще одне налаштування для того самого; `compat` уже узвичаєно (3a/3b).
- **Предикат лише в `serve.py`:** `publish_module` у `deai_modules` не міг би його викликати.

## Відкриті питання

Продуктових для власника — **нема** (усе виведено з паритету). Технічні, що закриваються в реалізації:

1. **`publisher-present` через `_provider_for` на поточному `space.json`** — перевірити в Task 5, що виклик не залежить від порядку
   завантаження каталогу й не кидає для зламаного свого модуля (`paper`); інакше — просто `abort-provider`.
2. **Чи ховати декоративні `auth`/`team`/`password` на картці в режимі `design-canvas`:** маніфест умовного показу не вміє; лишаємо
   підпис. Якщо це виявиться плутаним на живому прогоні — окрема дрібна задача (UX, не продукт).
3. **Холодний `check` (`npx vercel whoami`, `check_timeout_s: 130`) після міграції** — перший «Перевірити» на картці може бути довгим;
   перевірити живим прогоном із фальшивим `npx` (тайм-аут клієнта), текстів не змінюємо.

## Документи

CHANGELOG `[0.19.0]` (Upgrading — відкат c→b→a і застереження про відкат на 0.18; Deliberate differences; Known limits; виправлення
нотаток «знімається в 4d-3c» у `[0.18.0]`, рядки 87 і 171), README (розділ «LIGA migration» — три кроки), `docs/design/spaces-and-modules.md`
(«Stage 4d-3c», виправити рядок 17 і рядки 630–631 про `'legacy'`), `docs/modules/authoring.md` (`compat` у `vercel-publish`), `serve.py:4336`
(таблиця докстрінгу `publish_comments`), `module.json`, однорядковий вказівник у спеці 4d-3b, `package.json` 0.19.0.

## Чекліст релізу

Спека погоджена → план → реалізація задачами (виконавець і ревʼюер — Sonnet, послідовно: живі тести) → фінальне ревʼю → прогони на
знімку → дата в CHANGELOG → тег `v0.19.0` → push → памʼять. ⛔ Міграцію на справжньому `~/.deai` власника не запускаємо ні в тестах, ні
вручну: вона станеться сама при першому старті канваса 0.19.

## План (контур задач)

1. **Знімок 0.18.0** — `make_before_4d3c.py` + фікстура + `Before4d3cShape` (до будь-якої правки коду).
2. **Предикат і споживачі** — `publish_legacy_path`, `publish_module`, `_publish`, `_preview_password`, AST-охоронець, мутації.
3. **`compat` модуля і UI** — `module.json` 1.2.0, `COMPAT_ROLES`/`compat_view`, `isLegacyPublish`, JS-тести.
4. **Крок `liga-4d3c`** — `STEP_C`, `_entries_c`, коди пропуску, `abort-provider`, LIFO на три кроки (`_applied_later`), CLI/`status`.
5. **Паритет** — `AfterMigrationParity4d3c` із `EXPECT_DIFF`, `RealPublishNonIsolated`, три кроки на одному старті.
6. **Живий тест** — розширення `liga-migrate.test.mjs`.
7. **Документи, мутаційні докази.**
8. **Фінальне ревʼю, реліз** (CHANGELOG, тег, памʼять).
