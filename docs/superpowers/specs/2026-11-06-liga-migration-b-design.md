# Етап 4d-3b: міграція простору ЛІГА, другий крок — `comments` і `vcs` (0.18.0)

Дата: 06.11.2026. Попередній етап — 4d-3a (0.17.0, випущено 06.11.2026; спека `2026-11-05-liga-migration-a-design.md`). Дорожня
карта — `docs/design/spaces-and-modules.md`. Номери рядків нижче — за кодом на `v0.17.0` (HEAD `6906621`); код — правда, спека — намір.

## Рішення власника

- **26.10.2026 (етап 4):** чисте ядро + паритет; усе, що робить простір ЛІГА, стає загальним механізмом або модулем.
- **04.11.2026:** 4d-3 — явні модулі ЛІГИ з **автоматичною міграцією конфігу з бекапом**.
- **05.11.2026:** 4d-3 ділиться на 4d-3a (0.17.0, випущено), **4d-3b (0.18.0, ця спека)** — `comments` (схема каналів) і `vcs`
  (плоскі дзеркала git-синку), 4d-3c (0.19.0) — `publish`; 4d-4 стає 0.20.0. Секрети **копіюються**, оригінали лишаються
  (корінь старого `tasks.json`, оточення, `pipeline-feedback`) аж до 4d-4.
- **06.11.2026:** власник доручив іти далі автономно; відкриті питання закрито рекомендованими значеннями (розділ нижче).
- **06.11.2026:** спеку **погоджено** власником («Продолжаем»), включно з відомим обмеженням про відкат 0.18 → 0.17 лише через `restore`.

## Проблема

Після 0.17.0 ЛІГА має явними `tracker`, `dashboard`, `notify` і напрямки (де вони збіглися з адаптером). `comments` і `vcs` досі —
неявний постачальник (`Implicit`; `capabilities` каже `'legacy'`), бо явний запис модуля через `space.json` двох речей виразити
не міг:

1. **Канал коментарів.** Неявний шлях веде командні коментарі каналом `comment_project` задачі або `dc/<задача>` (+ `/internal`)
   (`serve.comment_channel`, `app/serve.py:2765`); явний модуль — `deai/<простір>/<задача>` (`deai_modules.channel_for`,
   `app/deai_modules.py:2080`). Історія пінів, тиша Teams і лічильники дашборда прив'язані до `comments.project_id`, тобто до
   каналу: змінити схему — «втратити» історію.
2. **Дзеркала git-синку.** Неявний шлях кладе плоскі теки `<.mirrors>/<slug репо>` (`mirror_flat`, `cache_dir = _mirrors_base()`,
   `app/serve.py:594–611`); явний модуль — `<DEAI_HOME>/cache/<простір>/git-sync/mirrors/<хост>/<slug>-<hash8>`
   (`deai_modules._cache_dir`, `:1628`; `app/modules/git-sync/server.py:251–271`). Інший шлях = повторний клон великих репо й
   осиротілі незапушені коміти старих дзеркал.

Крім того, шість місць ядра сприймають «неявний постачальник» як «це ЛІГА» (тексти даних, мітка «GitLab», канал). Урок фінального
ревʼю 4d-3a: **ЛІГА — запис реєстру (`legacy: true`), а не тип постачальника**; після міграції постачальник стає `Module`, а
поведінка ЛІГИ мусить лишитись (див. §3 і §6).

## Мета

1. **Паритет для людини:** ті самі канали, та сама історія пінів, ті самі тиші/лічильники Teams, ті самі теки дзеркал (без
   повторного клону, без осиротілих комітів), ті самі теми комітів і підписи «GitLab», та сама форма «Нова задача» (без поля
   «Репозиторій» у ЛІГИ).
2. **`comments` і `vcs` ЛІГИ — явні вбудовані модулі** (`supabase-comments`, `git-sync`) у `space.json`, секрет коментарів — у
   `secrets.json`; налаштування `compat` (§1, §2) виражають те, що раніше було зашито.
3. **Міграція — другий незалежний крок `liga-4d3b`** у тому самому `app/liga_migrate.py` (§4): свій бекап, позначка, відкат.
4. **Закон ізоляції** охоплює мігровані записи `comments` і `vcs` (§5).
5. **Неявний шлях лишається запасним** до 4d-4 (вимкнув явний запис — повернувся вбудований режим).

## Не мета

- `publish` — 4d-3c (`capabilities.publish` лишається `'legacy'`; збірка превʼю модулем коментарі ЛІГИ не несе, §5). Див. спеку 4d-3c
  (`2026-11-06-liga-migration-c-design.md`): відмова `publish_comments` для `shared_state` там НЕ знімається.
- Прибирання оригіналів, `gitlab_*`, `integrations`, `profile` — 4d-4.
- Запуск `schema.sql` на Supabase ЛІГИ; перейменування чи перенесення наявних дзеркал; `SUPABASE_SERVICE_KEY`.
- Міграція напрямків (зроблена в 4d-3a) і ролей `tracker`/`dashboard`/`notify`.

## Дизайн

### 1. `comments`: налаштування `compat` і ОДНА функція каналу

Модуль `supabase-comments` (`app/modules/supabase-comments/module.json`, зараз `url`, `key` (секрет, `public`), `shots_bucket`; версія
1.1.0) дістає необовʼязкове `compat` (`select`, формат `options` як у 4d-3a: `[{"value": …, "label": …}]`): `""` — «Deai:
`deai/<простір>/<задача>`», `"comment-layer"` — «comment-layer: `comment_project` або `dc/<задача>`»; типово `""`; версія → 1.2.0. Підпис
налаштування застерігає: зміна значення на живому просторі «відриває» наявну історію пінів (канал інший).

**Одна функція** `deai_modules.comment_channel_of(space, prov, task, tid, internal=False)` вирішує канал:

- `prov` — `Implicit` **або** вбудований (`origin == 'builtin'`, як у `ProjectComments.takes_iteration`, `serve.py:3413`)
  `Module` із розв'язаним `settings.compat == "comment-layer"` → схема comment-layer (`task.comment_project or f"dc/{tid}"` +
  `/internal`);
- інакше → `channel_for(space, tid, internal)`.

Чому лише вбудований: свій модуль простору міг би оголосити власне налаштування `compat` з іншим змістом. Допоміжна
`deai_modules.compat_of(space, module_id)` — ТОТАЛЬНА (`""` при будь-якому збої), читає розв'язані налаштування запису
(`resolve_settings`, `:1003`). Саму схему («`comment_project` або `dc/<id>`») переносимо як `deai_modules.legacy_comment_channel(task,
tid, internal)`; `serve.comment_channel` (`:2765`) і `dashboard.comment_project_key` (`app/dashboard.py:145`) стають тонкими обгортками
(жодної другої копії формули).

**Усі місця каналу ходять через цю функцію** (сьогодні їх два сорти):

| Місце | Сьогодні | Після |
|---|---|---|
| `comments_route` (`serve.py:3098`) → `/commented` (`:6209`), `/api/comment-config` (`:6372`), `publish_comments` (`:4284`), `ProjectComments._module` (`:3431`) | `Implicit` → `comment_channel`; модуль → `channel_for` | функція |
| `ProjectComments.channel` (`:3400`; читає `bin/inbox.py:654` і `bin/state.py`) | `kind == 'module'` → `channel_for`, інакше `comment_channel` | функція |
| `GET /api/task` → `comment_channel` (`:5938`), `GET`/`POST /api/teams-mute` (`:5979`, `:7168`) | **завжди** `comment_channel` (при інтеграціях), хоч би хто вів коментарі | функція з постачальником `comments` простору запиту |
| лічильники дашборда `dashboard.sync` (`app/dashboard.py:383`) | `comment_project_key` | необовʼязковий колбек `channel_of(task, tid)` (як `statuses`/`discover`); його будує `bin/overview_push.cmd_sync` із функції й постачальника простору `sp` |

Збій рішення про постачальника (`ModuleError`) у трьох «завжди»-місцях — не 5xx і не `None`: канал рахується за схемою comment-layer, як
і в 0.17.0 (рядок лишається там, де він був). Постачальника для них беремо з кешу `_capabilities_full(space)[1]` (як `publish_module`,
`:1985`), а не з нового проходу каталогом на кожен запит.

**Свідома відмінність (виправлення старої розбіжності):** у НЕ-ЛІГА просторі з інтеграціями й явним модулем коментарів без `compat`
`api/task`, тиша й лічильники тепер бачать справжній канал `deai/<простір>/<задача>` (раніше — `dc/<задача>`, тож тиша й лічильники
дивились повз піни).

**Паритет `ProjectComments` для агента.** `kind` лишається `'module'` для мігрованої ЛІГИ, тож усе, що розрізняє «ЛІГА» за
`kind`, мусить читати предикат «схема comment-layer» (та сама умова, що в функції каналу), а не `kind`:
- `ProjectComments.label` → «Supabase» (а не «модуль supabase-comments»), коли предикат істинний — заголовок `inbox` не змінюється;
- `bin/inbox.py:565` (`module_space = kind == 'module'`, що знімає обмеження `MIN_PREFIX` і дозволяє не знати номер ітерації) →
  `kind == 'module' and not <схема comment-layer>`: інакше у мігрованій ЛІГІ мовчки зʼявилось би «префікс коротший за 6 символів —
  можна»;
- `takes_iteration` вже істинний для вбудованого `supabase-comments` — без змін.

Відхилені альтернативи: (а) міграція пише `compat: ""` і переносить історію пінів у нові канали — потребує запису в спільну базу
ЛІГИ (схема, Teams-тригер і мʼют-рядки прив'язані до `project_id`); (б) окреме налаштування «канал-шаблон» — загальніше, ніж треба:
вирішує одне історичне виключення; два значення `select` — той самий розмір, що в 4d-3a.

### 2. `vcs`: налаштування `compat` і один предикат «легасі-тексти»

`git-sync` (`app/modules/git-sync/module.json`, версія 1.0.0 → 1.1.0) дістає `compat` (`select`: `""` — «Немає», `"design-canvas"` —
«design-canvas (ЛІГА): плоскі дзеркала, тексти й підпис 0.7.0»). `compat == "design-canvas"` означає РІВНО поведінку `Implicit`:

- `mirror_flat: True` і `cache_dir = serve._mirrors_base()` (`DC_MIRRORS_DIR` або `<ROOT>/.mirrors`, `:594`) — накладає **ядро** у
  `vcs_provider` поверх `module_ctx` (модуль не знає ні `ROOT`, ні `DC_MIRRORS_DIR`; друга копія логіки в модулі розсинхронізувалась би);
- тексти даних і підписи — «легасі» (див. нижче); `settings.autosync` читається з запису як є (міграція кладе `true`, як зашито в
  `_vcs_legacy_ctx`, `:607`).

Відхилена альтернатива: модуль сам читає `compat` для `mirror_flat`, а ядро лише підставляє `cache_dir` — логіка в двох місцях.

**Один предикат** `serve.vcs_legacy_texts(prov, space)` = `isinstance(prov, Implicit)` **або** (вбудований `Module` з
`compat_of(space, prov.id) == "design-canvas"`). `vcs_provider` (`serve.py:621`) обчислює його ОДИН раз і кладе третім елементом
кортежу `(module, ctx, legacy)`; усі споживачі (`:967`/`:992`/`:1016` README і тема коміту «design-canvas: sync» проти «deai: sync»;
`:1071` підпис і `web`; `:1298` автокоміт; `:1365` «GitLab»/«репозиторію»; `:2479`/`:2544` примітка форку; `bin/state.py:419`) лишаються
читати `v[2]`, але тепер це значення предиката, а не «чи неявний». Охоронець (AST) гарантує, що `isinstance(…, Implicit)` у
ядрі для рішень про тексти/канал живе лише в цих двох предикатах (урок 4d-3a: не прирівнювати «ЛІГА» до «неявного постачальника»).

`_vcs_ssh` (`:648`) і так бере `gitlab_ssh_key`/`gitlab_host_ip` із кореня при інтеграціях для БУДЬ-ЯКОГО постачальника — для паритету
копіювання не потрібне; міграція `ssh_key`/`host_ip` у налаштування — разом із прибиранням `gitlab_*` у 4d-4 (рішення контролера 06.11).

**UI.** `app/spaces-model.js:292` `isLegacyVcs` = `capabilities.vcs === 'legacy'`; після міграції там id модуля, тож форма «Нова
задача» (`app/app.js:1537`, `withRepo = hasVcs && !isLegacyVcs`) показала б поле «Репозиторій», а підписи (`vcsLabel`, `vcsFailKey`,
`:322`/`:352`) стали б «Git». Мінімальна форма: **сусідній ключ `compat` обʼєкта простору** (поряд із `capabilities`) — `{role: значення}`
лише для ролей, де явний вбудований модуль має непорожнє `compat`; віддають `serve.space_view` (`:5184`) і `spaces_listing` (`:5194`). `isLegacyVcs`:
`caps.vcs === 'legacy' || space.compat?.vcs === 'design-canvas'`. Не в `capabilities`: його значення — рядки-id, а `error` уже виняток
(ламає перебір за `ROLES_CALLED`); сусідній ключ не зачіпає наявні точні тести на `capabilities`.

### 3. `shared_state` і мігровані записи — позначка, предикат, канал

Обидва нові записи міграції мають `shared_state: true` (як у 4d-3a). Допоки неявний шлях — запасний (§6), вирішальне — що **«ЛІГА» у
ядрі = `Implicit` або запис із `compat`/`shared_state`**, і це читається лише з двох предикатів §1 і §2.

### 4. Міграція: упорядкований список кроків

`liga_migrate.py` зашитий на один крок: `MARK = 'liga-4d3a'` (`:45`), `ROLE_MODULES` (`:47`), `_plan` (`:198`, пропуски за `mig.get(MARK)`),
`BACKUP_SUFFIX`/`STAMP_RE` (`:295`–`:297`), `_backup` (маніфест `migration: MARK`, `:491`), `_commit_space` (`:503`), `_load_manifest`
(`migration != MARK`, `:630`), `_restore_locked` (`--hold`, `:769`), `status`/`status_text`, `BENIGN` у `bin/migrate_liga.py`.

**Узагальнення:** `STEPS = (Step('liga-4d3a', …), Step('liga-4d3b', …))`; крок має: імʼя-позначку, склад ролей (`ROLE_MODULES`), чи
мігрує напрямки (лише 4d-3a), суфікс бекапу, `STAMP_RE` (`[0-9]{8}-[0-9]{6}-<mark>(?:-[0-9]{1,3})?`, імʼя бекапу однозначно визначає
крок), значення `migration` у маніфесті. `plan(home, step)`, `run`, `restore`, `status` — на кожен крок; поведінка 4d-3a не змінюється
(тести 4d-3a лишаються зеленими без правок).

**Порядок і незалежність.** На одному старті `startup()` проходить кроки по порядку: `liga-4d3a`, потім `liga-4d3b`. Кожен —
повний цикл (план → бекап → секрети → один запис `space.json` → `last.json`), під тим самим замком `migrations/.lock`. `abort-*` одного
кроку зупиняє наступні **на цьому старті** (стан сумнівний); `skip-*` (зокрема `skip-nothing`, `skip-done`) наступний крок
не блокують. ВИНЯТКИ: `held` (`{held: true}`) раннього кроку тримає ВСІ наступні (правило розрахунку `plan`: інакше після `restore <b>` і
`restore <a> --hold` крок b ожив би на наступному старті) і `skip-busy` кроку зупиняє наступні на цьому старті (інший процес може бути посеред кроку). Користувач, що стрибнув з 0.16 на 0.18, отримує обидва кроки за один старт і **два** бекапи. План другого кроку
рахується вже ПІСЛЯ запису першого (читає актуальний `space.json`).

**Що записує `liga-4d3b`** (`space.json` — злиття, чужі ключі/модулі не чіпаємо; наявний модуль ролі → `module-present`):

- `comments` → `supabase-comments`: `{enabled: true, shared_state: true, settings: {url, shots_bucket: "overview-thumbs", compat:
  "comment-layer"}}` + `secrets {key}`; адреса й ключ — з `install_config.supabase_from(cfg)` (ті самі джерела й порядок, що
  `_comments_legacy_ctx`, `serve.py:3084`). Коди пропуску: `no-supabase`, `bad-url` (`user:pass@` в адресі), `module-present`.
  `shots_bucket` = `serve.LEGACY_SHOTS_BUCKET` (`serve.py:3080`): картка Teams бере `meta.shotUrl` звідти.
- `vcs` → `git-sync`: `{enabled: true, shared_state: true, settings: {branch: "main", path: "mockup/{task}", autosync: true, compat:
  "design-canvas"}}`; `ssh_key`/`host_ip` НЕ копіюємо (їх і далі дає корінь через `_vcs_ssh`; переносить 4d-4); секретів нема. Код
  пропуску лише `module-present`. Налаштування `repo` НЕ пишемо: репо задає ціль задачі (`vcs_target`, `serve.py:666`).
- Позначка `migrations["liga-4d3b"]` = `{at, roles, backup}` (без `tracks`).
- Перевірка `abort-provider`: на розрахованому в памʼяті `space.json` ядро (`_provider_for(..., explicit_override=…)`) мусить
  вирішити кожну мігровану роль саме цим модулем (`Module`), інакше крок нічого не пише.

Частковість остаточна, як у 4d-3a: якщо Supabase-конфігу нема, `vcs` мігрує, позначка пишеться, `comments` лишається неявним (код у
`last.json`/рядку старту; картка `supabase-comments` на «Підключеннях»).

**Відкат — LIFO.** Імʼя бекапу каже, чий це крок. `restore <stamp-b>` повертає `space.json` і ліговий шматок секретів зі стану після
4d-3a — 4d-3a лишається застосованим. `restore <stamp-a>` при застосованому (позначка без `held`) 4d-3b — **відмова** `refuse-later-applied`,
текст називає бекап, який відкочувати першим: інакше повернення `space.json` «до 4d-3a» мовчки затерло б модулі, позначку й секрет
4d-3b, лишивши осиротілий бекап. `--hold` кроку пише `{held: true}` лише його позначку. `last.json` лишає верхній рівень як у 4d-3a
(звіт останньої дії, тепер ще й `step`) і додає `steps: {позначка: звіт}`. CLI: `status`/`dry-run`/`run` показують усі кроки; `restore <stamp>`
визначає крок за імʼям. `BENIGN` у `bin/migrate_liga.py` НЕ розширюється (поправка плану 7): `restore` повертає 0 лише для `restored`, тож
`refuse-later-applied` дає код 1.

### 5. Закон ізоляції для `comments` і `vcs`

Сьогодні `Implicit` для цих двох ролей не має ні шва-фейка (`fake_env = None`, `app/implicit.py:23`/`:24`), ні відмови: в
ізольованому прогоні (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) він просто бере конфіг із **кореня файла задач** — `supabase_config()` не читає
оточення (`install_config.py:31`–`:75`), `_vcs_legacy_ctx` — сталі + `_vcs_ssh` з `load_tasks()`. Закон для мігрованих записів:

- у ізольованому прогоні (`implicit.isolated()`) запис із `shared_state: true` для `comments`/`vcs` будує `ctx` **так, як неявний шлях**
  (`_comments_legacy_ctx()` / `_vcs_legacy_ctx()`) — власні налаштування й секрети запису не читаються; канал і предикат — ті ж (за
  `compat`). Тобто демо/тест під `DC_TASKS_FILE` над справжнім `DEAI_HOME` не дістане ні справжній ключ Supabase з `secrets.json`;
- поза ізоляцією — `module_ctx` запису (+ накладка `cache_dir`/`mirror_flat` для `compat == "design-canvas"`, §2);
- місце одне: `comments_route` (`serve.py:3098`) і `vcs_provider` (`:621`), через `_shared_module(space, prov)` (`:1952`).

**Збірка превʼю модулем:** `publish_comments(module_publish=True)` (`serve.py:4252`) повертає `False` для `Implicit` («Supabase ЛІГА не
їде в превʼю, зібране модулем», `:4264`–`:4281`); та сама відмова — для `Module` коментарів із `shared_state` (інакше мігрована ЛІГА
з увімкненим модулем публікації почала б нести ключ у превʼю). Знімається в 4d-3c. ⚠️ Уточнення: НЕ знімається — див. спеку 4d-3c
(`2026-11-06-liga-migration-c-design.md`, «Свідомі відмінності»).

`ProjectComments._module` (`serve.py:3421`) гейтить викликом `spaces.require_integrations()` лише `Implicit` (`:3390`); мігрований запис
не гейтимо (явний модуль завжди працював без прапорця `integrations` — незмінне правило модулів).

### 6. Неявний шлях — запасний

`Implicit` для `comments` і `vcs` лишається в `IMPLICIT_ROLES`/`STRICT_IMPLICIT_ROLES`/`IMPLICIT_ON_ERROR_ROLES`
(`deai_modules.py:126`/`:131`). Вимкнув явний запис — повернувся вбудований режим (текст `LEGACY_ROLES` у `connections-model.js` лишається
правдивим); `capabilities.comments`/`vcs` мігрованої ЛІГИ — id модулів, `publish` — `'legacy'`. Зламаний (не завантажений) явний
`supabase-comments` лишає `module-error`, не повертає в Supabase ЛІГИ (існуюче правило `_provider_for`).

## Паритет і перевірки

- **Знімок 0.17.0 ДО змін коду** — `tests/make_before_4d3b.py` + `tests/fixtures/liga-migration/before-4d3b.json`; генератор
  запускається проти `git archive v0.17.0` (рецепт як у `make_before_4d3a.py`; відмова на робочій теці, що відрізняється від тегу),
  без мережі, у тимчасових `HOME`/`DEAI_HOME`, ЛІГА = запис реєстру `legacy: true`, `integrations: true`, вигадані значення.
  На відміну від 4d-3a (там `vcs_provider → None`) — `vcs` НЕ підміняється: знімається справжній `vcs_provider()`. Знімається:
  - **comments:** канали для задач із `comment_project` і без, плюс `/internal`; `ctx` (санітизований: налаштування, довжини секретів);
    `GET /api/comment-config?ch=project` (канал, `client`, конфіг); `GET /api/task` → `comment_channel`; канал, який бачить
    `GET /api/teams-mute` (шов `DC_TEAMS_FAKE`); ключ лічильника дашборда (`dashboard.sync` із фейковим модулем: який рядок
    `open_comments` лягає в картку); заголовок/`label` і поведінка `inbox` щодо короткого префікса;
  - **vcs:** `ctx` (налаштування, `mirror_flat`, `cache_dir` відносно `DC_MIRRORS_DIR`); `vcs_mirror_dir` для зразкових репо
    (SSH-, https-, з вкладеним шляхом); тексти: тема коміту, README, `gitlab_status` (`web`/`label`), «GitLab»/«репозиторію»,
    примітка форку, `label` у `bin/state.py` — через підміну `deai_modules.call` (git не запускається); прапорець форми «Нова
    задача» (`hasVcs`/`isLegacyVcs` через `node` на записі `/api/spaces`), `capabilities`.
- **`Before4d3bShape`** — структурні перевірки самого знімка (наявність і повнота секцій), як `Before4d3aShape`.
- **`AfterMigrationParity4d3b`** — ті самі сценарії на мігрованій ЛІГІ (`run()` у тимчасовому домі, дві конфігурації стенду, як у 4d-3a)
  дають те саме, крім явного списку **`EXPECT_DIFF`** (`capabilities.comments`/`vcs` — id модулів; `/api/spaces` має `compat`; `ctx`
  будує `module_ctx`: ті ж значення + `compat`, є `space.path`; нічого більше — тест падає на кожній зайвій різниці).
- **Кроки міграції:** по тесту на кожен код пропуску/відмови кроку 4d-3b; ідемпотентність; бекап повний (права 0700/0600, sha256);
  `restore` побайтно; **LIFO** (`restore <stamp-a>` при застосованому 4d-3b — `refuse-later-applied`, нічого не записано); два кроки на одному
  старті (два бекапи, порядок, `abort` першого не пускає другий, `skip-nothing` першого не блокує другий); збій між секретами й
  `space.json`; жодного значення секрету в звітах/stderr/`last.json`; невідомі ключі `space.json` збережено.
- **Ізоляція:** запис `comments`/`vcs` із `shared_state` в ізольованому прогоні будує `ctx` неявного шляху (ключ із кореня файла, не із
  `secrets.json`); без `shared_state` — звичайний модуль; відмова `publish_comments(module_publish=True)` для запису.
- **Живий тест** (розширення `tests/live/liga-migrate.test.mjs`, тимчасовий `DEAI_HOME`): картки `supabase-comments` і `git-sync` увімкнені;
  публікація й далі вбудована (`capabilities.publish == 'legacy'`); форма «Нова задача» без поля «Репозиторій»; другий старт нічого не
  пише; тека `.mirrors` не змінилась і дзеркал під `<DEAI_HOME>/cache` не зʼявилось (аналог `tests/live/git-sync.test.mjs:495–505`).
- **Мутаційні докази** (кожна нова перевірка «падає, коли зламати»; `python3 -B`): функція каналу (прибрати гілку `compat`, прибрати гілку
  `Implicit`, перейти на `channel_for` в одному з шести місць); предикат «легасі-тексти» (повернути `isinstance(prov, Implicit)`);
  накладка `cache_dir`/`mirror_flat`; гілка ізоляції; відмова LIFO; порядок кроків. Додатково AST-охоронець: жодного прямого
  `comment_channel(`/`comment_project_key(` поза функцією і її обгортками.
- Повні прогони (`npm test`, обидва Python, живі по одному — без паралельних сусідів), голдени без перезйомки.

## Свідомі відмінності від 0.17.0

- ЛІГА з конфігом після першого старту 0.18 — `comments` і `vcs` явні (id в `capabilities`, картки на «Підключеннях»).
- **У НЕ-ЛІГА просторі з інтеграціями й явним модулем коментарів без `compat`** `api/task`, тиша Teams і лічильники дашборда тепер на справжньому
  каналі `deai/<простір>/<задача>` (виправлення старої розбіжності).
- Копія: ключ Supabase для коментарів — у `secrets.json`; зміна оригіналу (корінь `tasks.json`, оточення) на коментарі ЛІГИ більше не
  діє — міняти на «Підключеннях». `gitlab_ssh_key`/`gitlab_host_ip` у корені й далі діють (переносить 4d-4).
- Теки дзеркал і тексти не змінюються (це й є мета); `compat` — налаштування, його можна змінити на екрані, і тоді канал/тека поміняються:
  підпис у картці каже, що це «відриває» наявну історію/дзеркала.

## Відомі обмеження

- **Відкат на 0.17 після міграції 4d-3b НЕБЕЗПЕЧНИЙ без `restore`:** 0.17 не знає `compat` (невідоме налаштування просто ігнорується в
  `resolve_settings`), тож канал коментарів стане `deai/…` (історія й тиша «зникнуть»), а дзеркала — під `<DEAI_HOME>/cache` (повторний
  клон, осиротілі коміти). Перед відкатом — `bin/migrate_liga.py restore <stamp-b> --hold`.
- Часткова міграція остаточна (як у 4d-3a): без Supabase-конфігу на першому старті `comments` лишається неявним.
- `skip-path-in-git`/`skip-no-path`, відсутність `flock` на Windows, гонка `run` із CLI проти правок з екрана — як у 4d-3a.
- Поле «Репозиторій» у «Нова задача» лишається прихованим для ЛІГИ, навіть якщо людина задасть `repo` у картці `git-sync`
  (налаштування `repo` діє на задачі без цілі — `vcs_target` — але форма за паритетом його не пропонує).
- `publish_comments` відмовляє (`False`) і для СВОГО (`origin == 'space'`) модуля коментарів із вручну виставленим `shared_state`
  (предикат `_shared_module` без походження; умова «вбудований» — лише в гілках ізоляції `comments_route`/`vcs_provider`): безпечний бік.
- Публікація (`publish`) ще неявна: превʼю, зібране модулем публікації, коментарів ЛІГИ не несе (лишається; див. спеку 4d-3c `2026-11-06-liga-migration-c-design.md`).

## Рішення за відкритими питаннями (контролер, 06.11.2026)

1. **`ssh_key`/`host_ip` не копіюємо** в 4d-3b: `_vcs_ssh` (`serve.py:648`) і так бере корінь при інтеграціях для будь-якого
   постачальника, а копія — знімок, що застаріє при ротації, і зміна місця вибору ключа (`_pick`, `git-sync/server.py:218`). Переносимо
   разом із прибиранням `gitlab_*` у 4d-4.
2. **`/api/task`, тиша й лічильники при збої постачальника коментарів** — схема comment-layer, як у 0.17.0 (паритет; помилку бачить
   сама роль коментарів).
3. **`last.json`** — сумісна форма: верхній рівень = остання дія (+ `step`) і мапа `steps`; читачі 4d-3a не ламаються.
4. **`compat` лишається редагованим** на картці, з попередженням у підписі, що зміна «відриває» наявну історію/дзеркала.
5. **`bin/state.py` і `bin/inbox.py` під явним модулем без сервера** — розбір за кодом (простір фіксує `task_anywhere`); підтвердити
   живим прогоном у Task 2 плану.

## Документи

CHANGELOG `[0.18.0]` (Upgrading, Deliberate differences, Known limits), README (розділ «LIGA migration» — два кроки, відкат LIFO,
`last.json`), `docs/design/spaces-and-modules.md` «Stage 4d-3b» + оновлений рядок дорожньої карти, `docs/modules/authoring.md`
(`compat` двох модулів), `module.json` двох модулів.

## Чекліст релізу

Спека погоджена → план → реалізація задачами (виконавець і ревʼюер — Sonnet, послідовно: живі тести) → фінальне ревʼю → прогони на
знімку → дата в CHANGELOG → тег `v0.18.0` → push → памʼять. ⛔ Міграцію на справжньому `~/.deai` власника не запускаємо ні в тестах,
ні вручну: вона станеться сама при першому старті канваса 0.18.

## План (контур задач)

1. **Знімок 0.17.0** — `make_before_4d3b.py` + фікстура + `Before4d3bShape` (до будь-якої правки коду).
2. **Канал** — `comment_channel_of`/`compat_of`, налаштування `compat` у `supabase-comments`, усі шість місць, колбек лічильників,
   предикат для `inbox`/`label`, AST-охоронець, мутації.
3. **`vcs`** — `compat` у `git-sync`, `vcs_legacy_texts`, накладка `cache_dir`/`mirror_flat`, ключ `compat` простору в API й
   `isLegacyVcs`, мутації.
4. **Ізоляція** — гілка `shared_state` у `comments_route`/`vcs_provider`, відмова `publish_comments`, тести.
5. **Узагальнення міграції** — `STEPS`, `STAMP_RE` на крок, маніфест, LIFO, `last.json`, CLI; тести 4d-3a зелені без правок.
6. **Крок `liga-4d3b`** — розрахунок, запис, коди пропуску, `abort-provider`; тести плану/запуску/відкату, два кроки на старті.
7. **Паритет і живий тест** — `AfterMigrationParity4d3b` з `EXPECT_DIFF`, розширення `liga-migrate.test.mjs`.
8. **Документи, мутаційні докази, фінальне ревʼю, реліз.**

## Implementation notes (відхилення, прийняті під час реалізації й ревʼю)

Де код відрізняється від тексту вище — правда за кодом. Поправки контролера 1–11 до плану (`docs/superpowers/plans/2026-11-06-liga-migration-b.md`)
мають перевагу над текстом спеки; тут їх зведення і рішення, що зʼявились на ревʼю.

**Поправки до плану (1–11).**

1. **«Тести 4d-3a зелені без правок» не буквальне.** `plan/run/_run/restore/_restore/status` БЕЗ `step` лишаються кроком 4d-3a;
   `run_all()`, `startup()` і CLI ітерують `STEPS`. Єдина правка тесту 4d-3a — один рядок у `_Stand.setUp`
   (`mock.patch.object(liga_migrate, 'STEPS', liga_migrate.ALL_STEPS[:1])`); нові тести — у `tests/test_liga_migrate_b.py`.
2. **`compat_of`** читає сирий запис `space_modules(space)[id]['settings']['compat']` (лише `str`, інакше `""`), а не `resolve_settings`:
   функція тотальна без обходу каталогу, результат ідентичний.
3. **Захист за id:** предикати кажуть «вбудований І `id == 'supabase-comments'`» (канал) та «вбудований І `id == 'git-sync'`» (тексти),
   бо `supabase-dashboard`/`supabase-teams` мають СВОЄ `compat`.
4. **Ключ `compat` обʼєкта простору** — лише коли непорожній (інакше відсутній).
5. **Свідома відмінність ширша:** `/api/teams-mute` і лічильники дашборда не мають гейта `integrations`, тож справжній канал
   `deai/<простір>/<задача>` при явному модулі коментарів без `compat` бачать і простори без інтеграцій.
6. **`LEGACY_SHOTS_BUCKET`** перенесено в `install_config.py` (міграція не імпортує `serve`), `serve` лишає аліас; тест зіставляє
   значення; запис міграції для `vcs` звіряється з `serve._vcs_legacy_ctx()['settings']`.
7. **`BENIGN` не розширюється:** `restore` повертає 0 лише для `restored`, тож `refuse-later-applied` дає код 1 (доводить тест).
8. **`last.json`:** `_write_last` зливає мапу `steps` (читає `_read_last()` під замком), інакше звіт 3b стер би звіт 3a.
9. **Номери рядків спеки** звірено з кодом (збігаються); шість місць каналу = `comments_route`, `ProjectComments.channel`, `api/task`,
   `teams-mute` GET, `teams-mute` POST, лічильники дашборда.
11. **Порядок старту (фінальне ревʼю):** `serve_main(port)` спершу займає порт (`make_server`), потім `liga_migrate.startup()`, потім
    `serve_forever()`: міграція — після відкриття порту, до обслуговування запитів (зʼєднання чекають у черзі). Зайнятий порт
    (`OSError`) зупиняє процес ДО міграції; інакше старіший сервер, що тримає порт, обслуговував би перепис, якого не розуміє.
    Рядок старту при `done` називає імʼя бекапу й підказку відкату (`restore <stamp> --hold`).
10. **Порядок появи `STEP_B`:** у Task 5 `ALL_STEPS = (STEP_A,)`, тести механізму — на синтетичному другому кроці; реальний `STEP_B` — Task 6.
11. **Живий `liga-migrate` між Task 6 і Task 7 очікувано червоний** (старт пише два бекапи); його розширила Task 7.

**Рішення з ревʼю (понад поправки).**

- **«Перевірка» модуля й закон ізоляції — для ВСІХ п'яти ролей.** `module_check_verdict`: запис із `shared_state` в ізольованому
  прогоні не перевіряється (вердикт `isolated`; ні `secrets.json`, ні мережі; `last_check` не перезаписується). Це закрило прогалину
  0.17 (там так само читався справжній `secrets.json` через «Перевірку» `dashboard`/`tracker`/`notify`). Умова — без походження:
  відмова безпечна для будь-якого модуля. Новий код `isolated` у `connections-model.js` (`cnErrIsolated`, uk/en).
- **`_builtin_shared` лише в гілках `comments_route`/`vcs_provider`.** Перша спроба обмежити «лише вбудовані» в самому
  `_shared_module` ламала закон 4d-3a для власних модулів (`implicit.route`); предикат `_shared_module` лишився без походження,
  а підстановка ключа кореня задач (`_comments_legacy_ctx`/`_vcs_legacy_ctx`) — тільки для вбудованих (`_builtin_shared`).
  `publish_comments` відмовляє за `_shared_module` (безпечний бік — і для свого модуля з вручну виставленим прапорцем).
- **Утримання раннього кроку тримає наступні** (`skip-held` із власним текстом причини «утримано разом із …»): інакше після
  `restore <b>` і `restore <a> --hold` крок b ожив би на наступному старті. Лише `held`; `done`/`skip-nothing` не блокують.
- **`skip-busy` зупиняє наступні кроки на старті** (як `abort-*`), `abort` не маскується пізнішим успіхом у підсумку `startup()`.
- **`skip-integrations-off`** (ЛІГА з вимкненими інтеграціями не мігрує): у 0.17 її ролі вимкнені (неявного постачальника нема),
  явні записи їх увімкнули б. Перевіряється у `_plan` КОЖНОГО кроку, отже діє й на 4d-3a; доброякісний код (`BENIGN`), старт мовчить.
- **Рядок «напрямки»** виводиться лише для кроку з напрямками — і в рядку старту/`status_text`, і в CLI `run` (виправлено в Task 8;
  вивід одного кроку 4d-3a побайтно як у 0.17, пінить `CliStepsTest`).
- **Живі прогони `liga-migrate` ізольовані** (`DC_TASKS_FILE` + шов `DC_MIGRATE_LIGA=1`, тимчасовий `DEAI_HOME`): закон ізоляції
  віддає гілку неявного `ctx`, тому шлях власника (НЕізольований: мігрований `git-sync` бере старе плоске дзеркало) покритий
  юніт-тестом `RealPushNonIsolated` (справжній `git push` у локальний `origin`), а живий тест перевіряє лише відсутність нових тек.
- **Змінені наявні тести** (по рядку): `tests/test_liga_migrate.py` — `_Stand.setUp` бачить один крок (Поправка 1);
  `tests/test_supabase_comments.py` і `tests/test_git_sync_module.py` — нові версії модулів (1.2.0, 1.1.0) і налаштування `compat`;
  `tests/connections-model.test.mjs`, `tests/connections-view.test.mjs`, `tests/vcs-client.test.mjs` — підписи `compat`/код `isolated`/
  `isLegacyVcs` через ключ `compat`.

**Мутаційні докази.** Кожна мутація — один рядок, `python3 -B`, файл відновлено, `sha256` збігся. Усі рядки нижче повторно прогнано
виконавцем Task 8 (06.11.2026) проти `tests/test_liga_migrate_b.py` (157 тестів) — у ревʼю/коммітах окремих звітів із мутаціями
нема, тож цифри цієї таблиці — з повторного прогону. Списки тестів не вичерпні (показано перші червоні; числа в дужках — оцінка).

| Блок | Мутація | Червоніє |
|---|---|---|
| Функція каналу, гілка `compat` | у `comment_scheme_legacy` умова `compat_of(…) == COMPAT_COMMENT_LAYER` → `False` | `CommentChannel.test_builtin_with_compat_uses_the_legacy_scheme` |
| Функція каналу, гілка `Implicit` | `comment_scheme_legacy` для `Implicit` повертає `False` | `CommentChannel.test_implicit_uses_the_legacy_scheme`, `ChannelCallSites.test_http_implicit_space_keeps_the_legacy_scheme`, `ProjectCommentsParity.test_label_and_legacy_scheme` |
| Шість місць: `comments_route` | замість `comment_channel_of` — `channel_for` | `AfterMigrationParity4d3b` (3), `ChannelCallSites` (2), `ChannelGuard`, `SharedStateIsolationB` (кілька) |
| Шість місць: `ProjectComments.channel` | замість функції — `channel_for` | `AfterMigrationParity4d3b` (3), `ChannelCallSites.test_in_process_sites_follow_compat`, `ProjectCommentsParity.test_inbox_matches_the_0_17_snapshot_on_a_migrated_view`, `ChannelGuard` |
| Шість місць: `api/task`/`teams-mute` (спільний помічник) | замість функції — `channel_for` | `AfterMigrationParity4d3b` (3), `ChannelCallSites` (3), `ChannelGuard` |
| Предикат текстів | `vcs_legacy_texts` лише `isinstance(prov, Implicit)` (решта → `False`) | `VcsLegacyTexts.test_matrix`, `…test_consumers_read_the_third_element_not_the_provider_type`, `VcsCompat` (4), `RealPushNonIsolated`, `SharedStateIsolationB.test_vcs_outside_isolation_takes_the_record` |
| Накладка дзеркал | у `vcs_provider` прибрано `{**ctx, **_flat_mirror_overlay()}` | `VcsCompat.test_compat_overlays_flat_mirrors_on_the_module_ctx`, `…test_both_paths_take_the_overlay_from_one_helper`, `RealPushNonIsolated`, `AfterMigrationParity4d3b` (3) |
| Гілка ізоляції `comments_route` | `and implicit.isolated()` → `and False` | `SharedStateIsolationB` (5: ctx, канал, без конфігу, HTTP-конфіг, публікація) |
| Гілка ізоляції `vcs_provider` | те саме | `SharedStateIsolationB.test_vcs_isolated_takes_the_legacy_ctx` |
| Відмова публікації | `publish_comments`: умова без `_shared_module` | `SharedStateIsolationB.test_publish_comments_refuses_shared_state_module_in_module_publish` |
| Страж «Перевірки» модуля | `module_check_verdict`: `implicit.isolated()` → `False` | `SharedStateIsolationB.test_check_verdict_isolated_shared_record_touches_nothing` |
| LIFO | прибрано перевірку `later is not None` у `_restore_locked` | `LifoRestoreTest.test_restore_a_refused_while_b_applied_and_writes_nothing`, `CliStepsTest.test_restore_finds_the_step_by_stamp_and_lifo_refusal_exits_1`, `StepBStartupTest.test_lifo_over_the_real_steps` |
| Порядок кроків | `ALL_STEPS = (STEP_B, STEP_A)` | `StepBConstants`, `StepsDefaults` (2), `StepBStartupTest` (6), `AfterMigrationParity4d3b`, `IntegrationsOffTest`, `RealPushNonIsolated` |
| Утримання раннього кроку | цикл `earlier` у `_plan` вимкнено | `LifoRestoreTest` (2), `StepBPlanTest.test_skip_held_by_an_earlier_step_has_its_own_reason`, `StepsTest.test_marks_are_independent`, `TwoStepsStartupTest.test_held_first_step_holds_the_second` |
| `skip-integrations-off` | перевірку `integrations` вимкнено | `IntegrationsOffTest` (4) |
| Запис кроку b | `shared_state` → `False` у записі `git-sync` | `StepBPlanTest.test_ready_comments_and_vcs_entries` |
| Запис кроку b | з `git-sync` прибрано `compat` | `AfterMigrationParity4d3b` (3), `RealPushNonIsolated`, `StepBPlanTest` (2) |
| Запис кроку b | з `supabase-comments` прибрано `compat` | `AfterMigrationParity4d3b` (3), `StepBPlanTest.test_ready_comments_and_vcs_entries` |
| Охоронець `ChannelGuard` | прямий виклик `comment_channel(` у `ProjectComments.channel` | `ChannelGuard.test_no_direct_calls_outside_the_wrappers` |
| Охоронець `TextPredicateGuard` | `isinstance(v[0], implicit.Implicit)` у споживачі тексту | `TextPredicateGuard.test_consumers_do_not_test_the_provider_type` |
| Рядок «напрямки» в CLI | умова `step.tracks` → `True` | `StepBRunTest.test_no_secret_value_anywhere` |

Не повторювались (мутації Task 5/6 із плану: `abort-*` не зупиняє наступні, спільний `STAMP_RE`, `_write_last` без злиття `steps`,
`_load_manifest` ігнорує крок, `hold` усіх кроків, `status()` без `steps`, копіювання `ssh_key`/`host_ip`, `abort-provider`, порядок
секрети/`space.json`, `tracks` у позначці b, `skip-nothing` блокує): таблиця їх не стверджує.
