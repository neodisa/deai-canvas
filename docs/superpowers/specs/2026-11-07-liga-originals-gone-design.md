# Етап 4d-4b: оригінали ЛІГИ — геть, запасний `Implicit` — геть (0.21.0)

Дата: 07.11.2026. Попередній етап — 4d-4a (0.20.0, `2026-11-07-liga-tracks-final-design.md`, HEAD `0d52a74`, тег `v0.20.0`). Дорожня
карта — `docs/design/spaces-and-modules.md`. Номери рядків нижче — за кодом на `v0.20.0` (шляхи — від кореня репо `<repo>`); код — правда,
спека — намір. Це чернетка для ревʼю контролера: нічого в коді не змінено.

## Рішення власника

- **26.10.2026 (етап 4):** чисте ядро + паритет; усе, що робить простір ЛІГА, стає загальним механізмом або модулем; для людини
  нічого не змінюється.
- **04.11.2026:** 4d-4 — прапорець `integrations` і старі псевдоніми геть.
- **06.11.2026:** секрети в 4d-3 **копіюються**, оригінали (корінь `tasks.json`, оточення, `~/.claude/pipeline-feedback/`) лишаються
  до 4d-4.
- **07.11.2026:** власник доручив наступні етапи автономно («работай автономно»); 4d-4 ділиться на 4d-4a (0.20.0, зроблено), **4d-4b
  (ця спека, 0.21.0)** і 4d-4c (0.22.0: `integrations`, `'legacy'` в API, запасні гілки JS, `_liga_flow`, `/api/gitlab-*`, `_liga_like`).
- **Видалення оригіналів поза `tasks.json`** (змінні оточення, файли `pipeline-feedback`) — не справа Deai: вони спільні з окремим
  інструментом ЛІГИ. Deai лише перестає їх читати.

## Рішення контролера для цього етапу (вхід спеки)

1. П'ятий крок міграції `liga-4d4b`: (а) копіює останні оригінали — `gitlab_ssh_key`/`gitlab_host_ip` кореня → налаштування
   `ssh_key`/`host_ip` запису `git-sync`; `preview_password` кореня → секрет `password` запису `vercel-publish`; (б) **видаляє з кореня
   `tasks.json` ЛІГИ** кожен оригінал, чиє значення доказово лежить у явних записах/секретах (рівність значень); решта лишається й
   потрапляє в нотатки. Бекап як в інших кроків; відкат **домерджує** видалені ключі в живий `tasks.json`, файл цілком не
   перезаписує. Змінні оточення й `pipeline-feedback` крок не чіпає.
2. Рантайм не читає оригіналів (`install_config.supabase_from/jira_from/service_key_config`, оточення, `pipeline-feedback`,
   `_vcs_ssh`/`gitlab_cfg`, `preview_password`, `bin/overview_push.py`).
3. `Implicit` — більше не постачальник: роль ЛІГИ без явного ввімкненого запису просто вимкнена.
4. Немігрована ЛІГА після 0.21: ролі вимкнені, старт і `status` називають кожну вимкнену роль, причину й команду виправлення.

## Похідні рішення цієї спеки (щоб ревʼю бачило, де я вибирав)

- **Д1. Крок Е — «ефективне значення збережено».** Рівність — між значенням, яке видалений читач реально віддав би (після його
  `strip`/`rstrip('/')`), і значенням у записі. Єдиний виняток з «лише порівнюємо» — пароль превʼю (див. §5, Д4).
- **Д2. Не видаляємо `design_work_root`, `design_work_roots`, `profile_repos`, `registry`, `current`, `tasks`.** `design_work_root` досі
  читає рантайм для КОЖНОГО простору (`app/serve.py:2386`–`2389`, `default_task_root`; `app/spaces.py:804` пише його в `tasks.json` кожного
  нового простору) — це конфіг самого файла, а не оригінал ЛІГИ. `design_work_roots`/`profile_repos` читає лише міграція (після 4d-4a),
  секретів у них нема, а рівність з явними `tracks` недоказова (`tracks.normalize` відкидає/переносить корені, ключі поза `ID_RE`, ліміт 20
  id — див. нотатки 4d-4a). Видалення цих двох ключів — окреме рішення, коли інструмент ЛІГИ піде (питання П2).
- **Д3. Шов, що лишається, — тільки для `shared_state`-записів.** `route`, фейкові шви `DC_TEAM_FAKE`/`DC_TRACKER_FAKE`/`DC_TEAMS_FAKE`, закон
  ізоляції переїжджають у новий чистий модуль `app/isolation.py` (§7); `app/implicit.py` видаляється.
- **Д4. Конфлікт пароля превʼю.** Якщо в записі `vercel-publish` уже є секрет `password`, відмінний від кореня (людина вписала його на екрані
  «Підключення», а режим `design-canvas` його **ігнорував**, див. `app/modules/vercel-publish/module.json`), крок перезаписує секрет значенням кореня:
  в дії було корінь, паритет — важливіший за інертне значення. Старий секрет лишається в бекапі кроку; нотатка `overwrote:password`.
  Для решти ключів, де запис УЖЕ був ефективним (`ssh_key`/`host_ip` у налаштуваннях перемагали корінь — `app/serve.py:683`–`686`; секрети
  дашборда/трекера/Teams/коментарів — завжди з запису), відмінне значення НЕ перезаписується: корінь лишається, нотатка `differs:<ключ>`.
- **Д5. Нова підкоманда `bin/migrate_liga.py unhold <позначка>`** (знімає лише `{held: true}` позначки): без неї «команда виправлення» для `skip-held`
  — ручна правка `space.json`.
- **Д6. Ізоляційний закон для коментарів/пароля превʼю — «справжній дім».** Ізольований прогін (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) читає облікові з
  `module_ctx` запису **лише коли `DEAI_HOME` — не справжній `~/.deai` машини** (за `pwd`, див. §7); у справжньому домі спільні ролі
  поводяться як ізольовані (відмова `comments-unconfigured`, пароль превʼю — `1100`).

## Проблема

Після 0.20.0 усі шість ролей і напрямки ЛІГИ — явні записи, але рантайм ще тягне **«оригінали»** і **запасного постачальника**:

**Читачі оригіналів у рантаймі (v0.20.0):**

| Де | Що читає |
|---|---|
| `app/install_config.py:35`–`56` `supabase_config`, `:58`–`74` `supabase_from` | корінь `supabase_url`/`supabase_key`, далі `SUPABASE_URL`/`SUPABASE_KEY` (поза ізоляцією) |
| `app/install_config.py:76`–`98` `service_key_config` | `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (лише `bin/overview_push.py`) |
| `app/install_config.py:100`–`125` `jira_config`, `:127`–`153` `jira_from` | корінь `jira_base` (+ `jira_email`/`jira_token` лише в ізоляції), `JIRA_EMAIL`/`JIRA_TOKEN`, файли `~/.claude/pipeline-feedback/jira-email|jira-token` |
| `app/serve.py:106`–`109`, `:2042`–`2045` | обгортки-«точки підміни» тестів над двома вище |
| `app/serve.py:539`–`551` `gitlab_cfg`; `:673`–`688` `_vcs_ssh` | корінь `gitlab_ssh_key`/`gitlab_host_ip` (третя ланка ланцюга «своє > налаштування модуля > корінь») |
| `app/serve.py:4131`–`4144` `preview_password(cfg, task)` | корінь `preview_password`; кличуть `:5995` (`/api/task`), `:7215` (`_preview_password`), `:8232` (`_publish`), `ops/reseal_gate.py:41`, `:118` |
| `bin/registry.py:261`–`263` `_ssh_key(cfg)` | корінь `gitlab_ssh_key` для git спільного реєстру (`design-office`) |
| `bin/overview_push.py:103`–`108` `_legacy_config`, `:154` | `supabase_config()` → `service_key_config()`; `jira_config()` |

Ці місця — та сама інформація, що вже скопійована в записи кроками 4d-3a/b/c (крім трьох значень нижче). Доки вони живі, запис і оригінал
можуть розійтись, а тест «рантайм не читає оригіналів» неможливий.

**Три значення, яких 4d-3 свідомо не копіював** (`app/liga_migrate.py:342`–`370` `_entries_b`: «`ssh_key`/`host_ip`/`repo` НЕ копіюємо»; `:373`–`381`
`_entries_c`: «секретів нема… пароль превʼю дає задача/корінь»): `gitlab_ssh_key`, `gitlab_host_ip`, `preview_password`. Їх копіює крок Е.

**Запасний постачальник `Implicit`** (`app/implicit.py`, 48 рядків) діє, коли ЛІГА без явного ввімкненого запису ролі:

- `app/deai_modules.py:1815`–`1818` (неявний простір: шар вимкнено/простір запиту не зафіксовано → `implicit.for_role`);
  `:1824`–`1832`, `:1849`–`1850` (простір з `integrations`: порожній/відсутній явний запис → `Implicit`);
  `:114`–`131` (`IMPLICIT_ROLES`, `IMPLICIT_ON_ERROR_ROLES`, `STRICT_IMPLICIT_ROLES`); `:1887`, `:2013`, `:2177` (`api_value`, `publish_legacy_path`, `comment_scheme_legacy`).
- Споживачі в `app/serve.py`: `:622`–`624`, `:645`–`652` (`vcs_provider`), `:1924`–`1940` (`_team_fetch`), `:2073`–`2086` (`_tracker_fetch`), `:2658`–`2681`
  (`notify_call`), `:2797`, `:3137`–`3147` (`comments_route`), `:3430`–`3477` (`ProjectComments.kind == 'implicit'`), `:4330`–`4333` (`publish_comments`),
  `:7688`–`7705` (`_overview_launch`); у `bin/overview_push.py:121`–`123`, `:153`–`154`.
- Легасі-збирачі `ctx` з оригіналів: `serve._comments_legacy_ctx` (`:3116`–`3126`), `serve._vcs_legacy_ctx` (`:592`–`603`), `dashboard.legacy_ctx/legacy_module`
  (`app/dashboard.py:229`–`244`), `tracker.legacy_ctx`, `notify.legacy_ctx/legacy_module` (`app/notify.py:77`–`93`).

**Але `implicit` — це не лише запасний шлях.** Те, що в ньому живе, використовують і мігровані `shared_state`-записи:

- `implicit.route(p)` (`app/implicit.py:42`–`48`): шов `DC_*_FAKE` → ізоляція → живий. Його кличуть `_team_fetch` (`serve.py:1926`), `_tracker_fetch` (`:2074`),
  `notify_call` (`:2659`) **і для `Module` із `shared_state`** (через `implicit.for_role(<роль>)`).
- `implicit.isolated()` (`:35`–`38`) — закон ізоляції: `serve.py:656`, `:3152`, `:5394`, `:7697`, `:7702`; `app/install_config.py:62`–`66`, `:85`, `:140`.
- Таблиця `_TABLE` (`app/implicit.py:22`–`29`) — єдине місце відповідності «роль → фейковий шов».

Тож «видалити `Implicit`» без перенесення цього зламає ізоляцію і живі тести ролей (§7).

**Закон ізоляції тримається на оригіналах.** Ізольований прогін читає облікові лише з кореня власного файла задач (`install_config.py:62`–`66`, `:140`–`145`):
ізоляція — це «стан не справжній цієї машини», і фікстура під `DC_TASKS_FILE` кладе туди вигадану пару. Тести (≈20 файлів, ≈180 рядків —
див. Додаток Б) і живі тести (`tests/live/fixture.mjs` `LIGA_SUPABASE`, `legacyExtra`) стоять на цьому. Без читання кореня ізольованому прогону
треба інше джерело (§7).

## Мета

1. Після 0.21 на машині, де ЛІГА мігрована, **нічого не залежить від оригіналів**: корінь `tasks.json` ЛІГИ не має облікових ключів, оточення
   й `pipeline-feedback` ніхто не читає.
2. Рантайм **не читає оригіналів** (AST-охоронець, §9); легасі-збирачі `ctx` і `Implicit` видалені.
3. Роль ЛІГИ без явного ввімкненого запису **вимкнена**, і людина про це знає з першого рядка старту.
4. Для людини з мігрованою ЛІГОЮ — ті самі відповіді, мітки, URL, паролі превʼю, канали, ключі (паритет, §9).
5. Відкат кожного кроку лишається повним (LIFO), крок Е відкочується без втрати живих правок `tasks.json`.

## Не мета

- `integrations` (вихідний гейт, `static-publish` за замовчуванням, `task-new`), значення API `'legacy'`, JS-запасні гілки, `_liga_flow`, `/api/gitlab-*`,
  `_liga_like` — 4d-4c. Нижче (§8) — що з цього стає **мертвим**, але лишається.
- Видалення змінних оточення й файлів `pipeline-feedback`.
- Видалення `design_work_root(s)`/`profile_repos`/`registry`/`current` з кореня (Д2).
- Новий інтерфейс «міграція» на екрані; нові ключі кореня.
- Правка `tests/fixtures/liga-migration/before-4d3*.json`/`before-4d4a.json` (зафіксовані знімки лишаються еталонами своїх етапів).

## Дизайн

### 1. П'ятий крок `liga-4d4b`

`STEP_E = Step('liga-4d4b', (), False, '-liga-4d4b', <stamp_re>, <entries>, originals=True)`; `ALL_STEPS = (A, B, C, D, E)` (`app/liga_migrate.py:553`–`563`).
Нове поле `Step.originals` (за замовчуванням `False`): гілка «записи/секрети/`tasks.json`» крок Е відрізняє від D (`ungated`, `:463`, `:466`, `:515`, `:533`,
`:823`–`827`, `:856`, `:922`, `:948`–`956`, `:1235`; `bin/migrate_liga.py:49`, `:55`). Ролей у позначці немає (`roles: []`), як у D, хоч крок і змінює
вже наявні записи `git-sync`/`vercel-publish` — у цьому його відмінність від кроків A–C, які лише **додають** записи (`_commit_space`: «модуль, що зʼявився
тим часом, не перезаписуємо», `:813`–`816`).

Ворота — ті самі, що в `_plan` (`:409`–`443`): шар, ЛІГА, `integrations`, тека, `space.json`, позначка/`held`, **`held` раннього кроку тримає Е**, git, файл задач.
Е не має сенсу без A–D: якщо `held`/`skip-*` раннього кроку, Е — `skip-held` (`reason`: «утримано разом із …»), і корінь не чіпається.

#### 1.1. Що крок рахує (чисто, у памʼяті)

`plan(step=E)` читає: корінь `tasks.json` (`install_config.load_legacy_tasks`, лишається — це файл, а не оригінал), `space.json` (`_load_space_json`),
секрети ЛІГИ (`deai_modules._load_secrets`, без локу). Для кожного ключа з `ORIGINAL_KEYS` будує запис `{key, effective, holder, status}`.

`ORIGINAL_KEYS` (рівно вісім ключів кореня):

| Ключ кореня | Ефективне значення (як рахував видалений читач) | Тримач у записі | Копіюємо? | Доказ рівності |
|---|---|---|---|---|
| `supabase_url` | `strip()`, `rstrip('/')`; форма `_SUPABASE_URL_RE` (`install_config.py:30`), без `userinfo` (`_has_userinfo`, `liga_migrate.py:303`) | `settings.url` записів `supabase-dashboard`, `supabase-teams`, `supabase-comments` | ні (A/B вже скопіювали) | усі три записи є, `enabled`, `shared_state`, і `settings.url` кожного = ефективне |
| `supabase_key` | `strip()`; друковний ASCII (`_SUPABASE_KEY_RE`) | секрет `key` тих самих трьох записів | ні | секрет `key` кожного = ефективне |
| `jira_base` | як `supabase_url` | `settings.base` запису `jira-tracker` | ні | запис є, `enabled`, `shared_state`, значення збігається |
| `jira_email` | `strip()`, друковний | `settings.email` `jira-tracker` | ні | збіг |
| `jira_token` | `strip()`, друковний ASCII | секрет `token` `jira-tracker` | ні | збіг |
| `gitlab_ssh_key` | значення як є (рядок, непорожній) | `settings.ssh_key` запису `git-sync` | **так** | після запису: збіг побайтно |
| `gitlab_host_ip` | як є | `settings.host_ip` `git-sync` | **так** | збіг побайтно |
| `preview_password` | як є: рядок; число (`int`/`float`) → `str(v)` (так читав `str((cfg or {}).get('preview_password') …)`, `serve.py:4143`–`4144`) | секрет `password` запису `vercel-publish` з `compat == "design-canvas"` | **так** (Д4) | секрет = `str(значення)` |

Правила рішення про ключ (порядок):

1. Нема в корені (або `None`) → пропускаємо мовчки (нічого видаляти й копіювати).
2. **Непридатне значення** — не рядок/число, порожнє після `strip`, не тієї форми, чи (`write_secrets`) не `str ≤ MAX_VALUE_LEN`/`_encodable` — нотатка `unfit:<ключ>`,
   ключ лишається. (Корінь `jira_email`/`jira_token` — другорядні: до 0.15 їх читала лише ізоляція, поза нею вони ніколи не були ефективними; ту саму логіку застосовано, але на
   реальній машині їх зазвичай нема.)
3. **Тримача нема** (запис відсутній / `enabled != True` / без `shared_state` / для `preview_password` — `compat != "design-canvas"`) → нотатка
   `no-record:<id модуля>`; ключ лишається. Для пари Supabase і трьох записів: якщо не всі три тримачі готові — **жоден** із двох ключів не видаляється,
   нотатка `partial:supabase` (+ `no-record:…`/`differs:…` для винуватців). Причина: корінь для відсутнього тримача — єдина копія, яку людина може
   повернути простою правкою.
4. **Тримач має інше значення** → `differs:<ключ>`, корінь лишається (Д4: для `preview_password` — перезапис, нотатка `overwrote:password`, `kept` без ключа).
5. **Тримач порожній, а ключ копіюємо** (`gitlab_*`, `preview_password`) → у **план копії** (settings-патч/секрет).
6. **Збіг** → ключ у список видалення.

Охоронець маркера: після видалення `spaces.has_markers(new_root)` (`app/spaces.py:281`–`285`; маркери `registry`, `gitlab_host_ip`, `gitlab_ssh_key`, задача з `gitlab`)
мусить лишитись істинним, якщо було істинним до: інакше реєстр, відновлений з нуля (`spaces.py:316`–`317`), створив би ЛІГУ з `integrations: false`.
Коли це не так, крок **не видаляє `gitlab_host_ip`** (нотатка `marker-kept:gitlab_host_ip`). На справжніх машинах ключ `registry` (його пише `bin/registry.py`) і задачі з
`gitlab` це майже завжди закривають; охоронець — страховка.

Копіюється **лише в існуючий** запис: Е ніколи не створює запис `git-sync`/`vercel-publish` (це справа A–C).

#### 1.2. Коди

- **Статуси:** `skip-nothing` (нема копій, видалень і нотаток — позначку не пишемо), `skip-held`, `skip-busy`, `skip-done`, `skip-integrations-off`,
  `skip-path-in-git`, `skip-no-path`, `skip-tasks-unreadable`, `skip-space-json-unreadable`, `skip-registry-unreadable`, `skip-layer-off`, `skip-no-liga` — як у 0.20.
- **Нові `abort-*`** (у `ABORT_CODES`, `:58`): `abort-originals` (`tasks.json` не записано: копії вже лежать, нічого не видалено — наступний старт повторить), `abort-verify`
  (після запису копій перечитане значення не збігається з планом: **нічого не видалено**). Обидва — з `last.json` і з рядком старту.
- `abort-provider` для Е не застосовується (ролей кроку нема): замість нього — перевірка в памʼяті, що розрахований `space.json` дає ті самі **вирішення ролей**, що й до кроку
  (`_provider_for` на `explicit_override`): запис `git-sync` з новими налаштуваннями лишається `Module`, `publish_legacy_path` лишається істинним. Інакше — `abort-provider`.
- **Нотатки позначки** (коди без шляхів і значень, id модулів/ключів — можна): `differs:<ключ>`, `no-record:<id>`, `partial:supabase`, `unfit:<ключ>`,
  `overwrote:password`, `marker-kept:gitlab_host_ip`.

#### 1.3. Форма позначки

`migrations["liga-4d4b"] = {at, roles: [], copied: [ключі], removed: [ключі], kept: [ключі], notes: [...], backup}`. Лише імена ключів, ніколи значення. `kept` —
оригінали, що лишились у корені (для людини: «що ще лежить»). `held: true` — як в інших кроків (`restore --hold`).

#### 1.4. Порядок запису й замки (перевикористання машинерії D)

Під міжпроцесним `flock` (`_exclusive`, `:713`–`733`) і внутрішнім `spaces.WRITE_LOCK` лише на окремий запис (`:906`–`969` — як у `_run_locked`):

1. **Перевірка до бекапу:** `_records_writable(tasks.json)` (`:844`–`848`; перейменувати на `_tasks_writable`) — тека, файл і наявний `tasks.json.bak` доступні для запису;
   інакше `abort-originals` БЕЗ бекапу (кожен старт інакше лишав би по теці бекапу). Те саме для `secrets.json` (доступність запису) — інакше `abort-secrets`.
2. **Бекап** кроку (`_backup`, `:766`–`801`: `tasks.json`, `space.json`, `secrets.json`, `spaces.json`, sha256 до/після, 0600/0700). Тут це особливо важливо: бекап `tasks.json`
   — єдина копія видалених ключів у файлі, окрім `tasks.json.bak`.
3. **Секрети:** `deai_modules.write_secrets(space_id, 'vercel-publish', {'password': …})` (оголошений секрет; `write_secrets` бере `WRITE_LOCK` сам — вкладених локів нема).
4. **`space.json`:** налаштування `ssh_key`/`host_ip` `git-sync` — злиттям у ПОТОЧНИЙ файл під локом (`_commit_space`-стиль: перечитати, злити лише відсутні/порожні ключі,
   чужі правки не губляться). Позначка **ще не пишеться**.
5. **Перевірка прочитанням:** `_load_secrets()` + `_load_space_json()` (без локу): кожне скопійоване значення — рівне плану. Не так — `abort-verify`, нічого не видалено.
6. **`tasks.json`:** під `WRITE_LOCK`: `before = _file_sig(path)` (mtime_ns, size) → `load_legacy_tasks()` → **ще раз** звірити рівність кожного ключа списку видалення з диском
   (щойно перечитаними записом і секретом: людина могла змінити налаштування між кроками 5 і 6) і лишити в списку лише ті, що збіглись → `shutil.copy2(path, path + '.bak')` →
   `_file_sig(path) == before` → `atomic_write_json(path, cfg)` без цих ключів. Ретраї `_RECORDS_ATTEMPTS = 3`; постійна гонка — `abort-originals` (`OSError('tasks file keeps changing')`).
   Записи задач (`cfg['tasks']`) і всі чужі ключі — як є: файл перечитується, ключі видаляються по одному, а не пишеться «знімок плану».
7. **Позначка:** `_commit_space` пише `migrations['liga-4d4b']` **останньою** — після видалення. Збій між 6 і 7 лишає ключі видаленими без позначки: наступний старт перераховує —
   копії вже збігаються, видаляти нічого — `skip-nothing`/«позначка з нотатками»; позначка дописується. Збій між 4 і 6 — копії є, ключі ще в корені, наступний старт доробить.

Ідемпотентність: повторний `plan(E)` після кроків 3–4 дає «копіювати нічого, видалити те саме».
Залишкове вікно TOCTOU між `_file_sig` і `atomic_write_json` — те саме, що в D (`CHANGELOG` 0.20, «Known limits»); `.bak` має байти до кроку.

`skip-nothing` **не** видається, коли є нотатки (`unfit`, `differs`, `no-record`, `partial`): тоді позначка пишеться з `removed: []`, щоб людина раз почула про залишки й `status`
їх показував. Повторна позначка не пишеться (`skip-done`).

#### 1.5. Відкат кроку Е

`restore <stamp-E> [--hold]` (`_restore_locked`, `:1114`–`1185`) повертає `space.json` і ліговий шматок секретів з бекапу (LIFO, `refuse-later-applied`, запобіжна копія `-pre-restore`) —
як і для інших кроків — **і додатково відновлює корінь**:

- Перелік — з позначки `removed` ПОТОЧНОГО `space.json`, прочитаної ДО його заміни (запасний шлях, коли позначка нечитана/без `removed`: ключі `ORIGINAL_KEYS`, що є в `tasks.json` з бекапу й
  відсутні в живому).
- Значення — з `tasks.json` **бекапу** (sha256 уже звірено `_load_manifest`, `:1005`–`1025`).
- Злиття: під `WRITE_LOCK`, ті самі перевірка запису до змін, `_file_sig`-ретраї, `.bak`, `atomic_write_json`. Додається **лише** ключ, якого в живому корені **нема**; якщо людина вже
  вписала там своє — лишається її (відмітка в звіті `restore`: `kept-live:<ключ>`). Записи задач/решта ключів не чіпаються.
- Порядок: **спершу корінь**, потім `space.json`/секрети. Збій між ними лишає простір мігрованим і з поверненими ключами (узгоджено); навпаки було б «немігровано без ключів».
- `--hold` пише `{held: true}` лише для Е. Звіт `restore` додає `root_restored: [ключі]`.

### 2. Рантайм не читає оригіналів

| Місце | Було | Стане |
|---|---|---|
| `app/install_config.py` | `supabase_config/from`, `service_key_config`, `jira_config/from` | **видалені** з модуля; лишаються `legacy_tasks_path`, `load_legacy_tasks`, `LEGACY_SHOTS_BUCKET`, регекспи форми (потрібні міграції). Їхня копія — приватні `_supabase_from`/`_jira_from` у `liga_migrate` (міграція ще читає оригінали на першому старті старої установки: кроки A–Е) |
| `serve.supabase_config/jira_config` (`:106`–`109`, `:2042`–`2045`) | обгортки | видалені разом із читачами |
| `serve.gitlab_cfg(cfg, task)` (`:539`–`551`) | `gl.ssh_key or cfg.gitlab_ssh_key` | `gitlab_cfg(task)`: лише `gl`; `cfg` геть |
| `serve._vcs_ssh(cfg, settings, *own)` (`:673`–`688`) | `own > settings > корінь` | `_vcs_ssh(settings, *own)`: `own > settings`; ціль не несе поля — модуль бере своє (`_pick`, `app/modules/git-sync/server.py`) |
| `serve.vcs_target(cfg, tid, task, settings)` (`:691`–`728`, `:2499`, `:7970`) | `cfg` для `gitlab_cfg`/`_vcs_ssh` | `vcs_target(tid, task, settings)` |
| `serve.preview_password(cfg, task)` (`:4131`–`4144`) | задача > корінь > `1100` | `preview_password(task, space)`: **задача > секрет `password` запису `vercel-publish` (`deai_modules.publish_password(space)`) > `1100`**. Рішення читати секрет — та сама умова `publish_legacy_path(prov, space)`, що вже веде гілку ЛІГИ (`deai_modules.py:2003`–`2020`). Кличуть: `/api/task` (`:5995`, `space` береться з `:5996` — переставити), `_preview_password` (`:7215`), `_publish` (`:8232`), `ops/reseal_gate.py` (`:41`, `:118`; простір ЛІГИ — з реєстру `legacy: true`) |
| `bin/registry._ssh_key(cfg)` (`:261`–`263`) | корінь `gitlab_ssh_key` або `~/.ssh/gitlab_ed25519` | `_ssh_key()`: налаштування `ssh_key` запису `git-sync` ЛІГИ (`deai_modules.space_modules`), інакше той самий дефолт. Ізольований/без шару прогін — дефолт |
| `bin/overview_push._legacy_config` (`:103`–`108`) і гілки `Implicit` (`:119`–`123`, `:153`–`154`) | конфіг установки + сервісний ключ з оточення | **видалені**: лишається `module_ctx(sp, prov)`; нема постачальника — «нема постачальника командного дашборда» (`cmd_sync`, `:197`–`199`) |
| `serve._comments_legacy_ctx` (`:3116`–`3126`) | `ctx` з конфігу установки | видалений; ізольована гілка `comments_route` — §7 |
| `dashboard.legacy_ctx/legacy_module`, `tracker.legacy_ctx/legacy_module`, `notify.legacy_ctx/legacy_module` | легасі-збирачі | видалені (мають кликачів лише з гілок `Implicit`) |
| Тексти `COMMENTS_UNCONFIGURED` (`serve.py:3113`), `tracker.UNCONFIGURED` (`app/tracker.py:26`), `deai_modules.py:176`, `:180` | «додайте … у tasks.json» | «додайте адресу й ключ на екрані «Підключення»» |

Що **лишається**: `serve._vcs_legacy_ctx` (`:592`–`603`) і `_flat_mirror_overlay` (`:606`–`613`) — це ізольований ctx `shared_state`-запису `git-sync` (плоскі дзеркала в `DC_MIRRORS_DIR`),
а не збирач з оригіналів; `_publish_legacy_ctx` (`serve.py:5072`) — ctx публікації ЛІГИ в режимі `cli`, його кличе гілка `compat`, а не `Implicit`.

### 3. Постачальник без `Implicit` (`app/deai_modules.py`)

`_provider_for(role, space, …)` (`:1792`–`1851`) спрощується:

- `spaces._is_implicit(space)` (неявний простір: шар вимкнено чи простір запиту не зафіксовано) → **`None`** для будь-якої ролі, БЕЗ читання реєстру/`space.json` (як і раніше «без читання»).
  Це свідома зміна: неявний простір — режим «стан не справжній» (тести, шар вимкнено); ролей у ньому нема.
- Решта: одна гілка для всіх просторів (ЛІГА теж): `explicit = space_modules(space)` (`ModuleError('space-json-unreadable')` — для КОЖНОЇ ролі, а не лише `STRICT_IMPLICIT_ROLES`:
  це поведінка, яку мала лише ЛІГА для чотирьох ролей, тепер вона загальна), `_paper_failure`, пошук переможця, `_enabled_module_is_lost` для `comments`.
- **Видаляється** `if role in IMPLICIT_ROLES and integrations: return implicit.for_role(role)` і гілка «порожньо явних → `Implicit`». ЛІГА без ввімкненого запису ролі → `None`.
- Неявний типовий модуль `static-publish` (`_implicit_on`, `:936`–`940`) лишається **як є** (лише простір без інтеграцій): ЛІГА його НЕ отримує — `integrations` до 4d-4c. Тож ЛІГА без `vercel-publish` не має
  публікації взагалі (409 `no-publish-module`, `serve.py:8215`–`8217`).
- Константи `IMPLICIT_ROLES`, `IMPLICIT_ON_ERROR_ROLES`, `STRICT_IMPLICIT_ROLES` (`:114`–`131`) видаляються (`capabilities`, `:1923`–`1970`: на `ModuleError` роль — `None`, а не `'legacy'`; без неї `API_IMPLICIT` більше
  ніколи не повертається ядром — див. §8). `provider()`/`api_value()`: `Implicit` більше не існує; `api_value(Module)→id`, `api_value(None)→None`, решта — `TypeError` як і було.
- `publish_legacy_path` (`:2003`–`2020`) і `comment_scheme_legacy` (`:2173`–`2180`): гілка `isinstance(prov, Implicit)` — геть; лишається умова «вбудований модуль із `compat`».
- `serve`: усі `isinstance(prov, implicit.Implicit)` видалені (`:622`, `:645`, `:1924`, `:2073`, `:2658`, `:2797`, `:3137`, `:3430`, `:4330`, `:7688`); `vcs_provider()` на `prov is None` повертає `None` (вже так, `:641`–`642`); `ProjectComments.kind` втрачає
  значення `'implicit'` (`:3398`–`3402`, `:3430`, `:3446`, `:3451`, `:3465`, `:3477`; читач — `bin/state.py:295`–`301`).

Наслідок для коду, що спирався на «неявний простір дає `Implicit`»: усі виклики `provider(role)` без зафіксованого простору запиту (`serve.py:640`, `:1971`, `:2052`, `:2631`, `:7197`, `:7683`, `:8215`) повертають `None`. Реальні шляхи
(маршрути, CLI) простір фіксують (`task_anywhere`, `set_request_space`, `bin/inbox.py:358`–`362`, `bin/state.py:293`–`298`); у плані — аудит кожного з викликів на «простір зафіксовано» (Task 6).

### 4. Немігрована ЛІГА

Кроки A–Е можуть не застосуватись: `skip-held` (людина зробила `restore --hold`), `skip-path-in-git` (тека простору в робочому дереві git — `space.json` не можна писати; **постійний** до перенесення теки),
`skip-tasks-unreadable`, `skip-space-json-unreadable`, `skip-registry-unreadable`, `skip-no-path`, `skip-busy` (минущий), `abort-*`. Після 0.21 у такій ЛІЗІ **усі шість ролей вимкнені** (до 0.21 їх вів `Implicit`):

| Роль → модуль | Що перестає працювати |
|---|---|
| `publish` → `vercel-publish` | «Опублікувати» (409 `no-publish-module`, `serve.py:8215`–`8217`) |
| `comments` → `supabase-comments` | командні коментарі (лише локальний шар); `inbox`/`state` для агента — «не підключено» |
| `vcs` → `git-sync` | синк із GitLab, автосинк, бутстрап задачі з репо |
| `dashboard` → `supabase-dashboard` | вкладка «Команда», `bin/overview_push.py`, синк рядків |
| `tracker` → `jira-tracker` | бейджі статусів Jira |
| `notify` → `supabase-teams` | тиша Teams (409 `notify-off`, `serve.py:2619`–`2623`) |

Виняток — `skip-integrations-off`: у такій ЛІЗІ ролей не було й у 0.20 (немає неявних постачальників без `integrations`); рядок «інтеграції вимкнено — так і було».

#### 4.1. Старт і `status` називають кожну вимкнену роль

Нова чиста функція `liga_migrate.roles_state(home=None)` → `[{role, module, on, reason, fix}]` для шести ролей. `on` — `provider(role, liga)` дає `Module` і `module_ctx(liga, prov)` будується (без мережі,
без коду модуля; `bad-settings`/`secrets-unreadable` → `reason`). Причина — перша застосовна:

1. запис є, `enabled: false` → `disabled`; fix: «увімкніть на екрані «Підключення»»;
2. запису нема й позначка кроку-власника ролі каже `skipped[role]` (`no-jira`, `no-supabase`, `bad-url`, `publisher-present`, `module-present`) → той код; fix: `no-jira`/`no-supabase`/`bad-url` → «додайте адресу/облікові на екрані «Підключення» (оточення й pipeline-feedback більше не читаються)»;
3. позначки кроку нема й останній звіт кроку (`last.json`) — `skip-held` → fix `python3 bin/migrate_liga.py unhold <позначка>` і `run`; `skip-path-in-git` → наявна підказка (перенести теку поза git) і `run`; `skip-tasks-unreadable` → «виправте tasks.json» і `run`; `skip-space-json-unreadable`
   → «виправте space.json» і `run`; `abort-*` → «`python3 bin/migrate_liga.py status`, усуньте причину, `run`»; `skip-busy` → «повторіть старт»;
4. запис є, модуль не завантажився/недовірений → `module-error`/`module-untrusted`; fix — екран «Підключення»;
5. інакше `no-record`; fix `python3 bin/migrate_liga.py run`.

Старт (`liga_migrate.startup`, `:1306`–`1363`) після `run_all` друкує блок (лише для не-ізольованого прогону з ЛІГОЮ): `ролі ЛІГИ вимкнено: <роль> (<модуль>) — <код>; виправити: <команда>` по рядку на роль; усі шість увімкнені — один рядок не друкується.
`status` / `bin/migrate_liga.py status` додає секцію «Ролі ЛІГИ» з усіма шістьма (`так`/`ні (<код>)`). Старий рядок `TRACKS_NOT_MIGRATED` (`:1259`) лишається.

### 5. Мапа ключів → тримачів (де людина шукає свої значення після 0.21)

Налаштування `git-sync` (`ssh_key`, `host_ip`) — прості поля на «Підключенні» (шлях і IP не секрет, `module.json` тип `text`); секрет `password` `vercel-publish` — поле «Пароль превʼю» (тип `secret`, на екрані — «задано»). Маніфест `vercel-publish`:
підпис `compat` («пароль превʼю … з tasks.json») оновлюється — «пароль превʼю: задачі, далі секрет модуля»; версія маніфесту 1.2.0 → 1.3.0.

### 6. Ризик «єдина копія»

Після кроку Е облікові значення лежать лише в `<DEAI_HOME>/secrets.json` і `<DEAI_HOME>/backups/…`, обидва — у домі Deai. Втрата дому (`~/.deai`) = втрата облікових. Старт після кроку друкує одним рядком: «оригінали видалено з tasks.json; єдина
копія — secrets.json і backups/ у домі Deai». (Змінні оточення й `pipeline-feedback` лишаються з боку інструмента ЛІГИ: для jira/supabase там може бути друга копія; Deai її не чіпає.)

### 7. Новий дім для `route`, фейкових швів і закону ізоляції: `app/isolation.py`

Чистий модуль (імпортує лише `os`; без `spaces`/`serve`, цикл неможливий — як `implicit.py` сьогодні).

```
isolated()                    # DC_TASKS_FILE або DC_NO_OVERVIEW — як app/implicit.py:35–38
FAKE_ENV = {'dashboard': 'DC_TEAM_FAKE', 'tracker': 'DC_TRACKER_FAKE', 'notify': 'DC_TEAMS_FAKE'}   # таблиця з implicit._TABLE
route(role)                   # ('fake', шлях) → ('isolated', None) → ('live', None); роль без шва — лише isolated/live
real_home(home)               # чи `home` — справжній ~/.deai машини за pwd (realpath); без urlparse/HOME
```

`route(role)` заміняє `implicit.route(prov)` у трьох викликачах (`serve.py:1926`, `:2074`, `:2659`), які тепер працюють лише з `Module` + `shared_state`: `_shared_module(space, prov)` (`:1951`–`1957`) лишається умовою входу. Параметр `shared` зникає (він завжди був
`True`). Правило ізоляції для `dashboard`/`tracker`/`notify` **не змінюється**: ізольований прогін НІКОЛИ не живий — шов або відмова (`TEAM_ISOLATED`, `None`, `OSError('ізольований конфіг…')`); паритет відповідей 0.15–0.20 той самий.

**Що ізольований прогін читає для облікових.** Корінь файла задач — більше ні. Залишаються (Д6):

- `dashboard`/`tracker`/`notify` — нічого (шов або відмова): їм облікові в ізоляції й не були потрібні.
- `comments` (`comments_route`, `serve.py:3152`–`3155`): `isolation.isolated()` + вбудований `shared_state`-запис → **якщо `DEAI_HOME` не справжній** (`isolation.real_home`): `module_ctx(space, prov)` — тобто налаштування й секрет `key` запису з тимчасового
  дому фікстури; **у справжньому домі**: `ModuleError('comments-unconfigured')` (як «конфігу нема» було). Жива мережа в тестах і далі відрізана підміною шва `_open` модуля (`tests/sbconf.py::patch_open`).
- `vcs` (`vcs_provider`, `:656`–`660`): без змін — `_vcs_legacy_ctx()` (фіксовані налаштування, плоскі дзеркала); `ssh_key`/`host_ip` в ізоляції не беруться ні з кореня, ні із запису (ціль їх не несе) — випадково потрапити на справжній ключ ізольований прогін не може.
- Пароль превʼю (`deai_modules.publish_password`): той самий ключ «справжній дім»: тимчасовий дім → секрет запису, справжній → `1100`.
- `module_check_verdict` (`serve.py:5394`) і `_overview_launch` (`:7697`) — без змін (відмова/тиша в ізоляції).

`real_home` — **суворіша за `liga_migrate._real_home`** (`:1294`–`1304`: той вважає `<HOME>/.deai` справжнім і за підміненим `HOME`): для закону ізоляції «справжній» — лише `pwd`-дім, бо інакше кожен живий тест з `DEAI_HOME=<HOME>/.deai` втратив би коментарі.
Шов міграції `DC_MIGRATE_LIGA=1` лишається на широкому правилі (рішення 4d-3).

Наслідок для шару вимкнено (`DC_TASKS_FILE` без `DEAI_HOME`; `spaces.layer_on()` хибне, `app/spaces.py:96`–`100`): неявний простір → **усі ролі `None`**, `read_secrets` → `{}` (`deai_modules.py:1426`–`1431`). Тести, що йшли шляхом ЛІГИ через неявний простір
(≈ уся `tests/test_implicit.py`, `test_legacy_comments.py`, частина `test_tasks_overview.py`/`test_dashboard.py`/`test_tracker.py`/`test_notify.py`…), мусять одержати **явну фікстуру** (тимчасовий `DEAI_HOME` + реєстр + `space.json` + `secrets.json`) — Додаток Б. Допоміжник
`tests/liga_fixture.py` будує її (а) безпосередньо записами й (б) запуском **справжньої** міграції `liga_migrate.run_all` на старому корені (вона читає оригінали — це дозволено в `liga_migrate`); другий спосіб дає паритетний знімок «як у людини».

### 8. Що стає мертвим після 0.21 і лишається до 4d-4c

| Що | Стан у 0.21 | Коли геть |
|---|---|---|
| значення API `'legacy'` / `deai_modules.API_IMPLICIT` (`:116`) | ядро його **більше не повертає** (`api_value` не має `Implicit`; `capabilities` на помилці дає `None`) | 4d-4c (разом із JS `connections-model.js`, `spaces-model.js`, `connections-view.js`, `NoLegacyLiteral`, `PublishJsGuard`) |
| JS-запасні гілки `'legacy'` | мертві (сервер не шле значення) | 4d-4c |
| `spaces.IMPLICIT` (`spaces.py:51`) і неявний простір | лишаються (режим «шар вимкнено»), **ролей у ньому нема** | 4d-4c (разом з `_liga_like`) |
| `serve._liga_like` (`:1692`–`1695`) | без кликачів (закріплено `LigaLikePin`) | 4d-4c |
| `serve._liga_flow`, 409 `no-integrations-space` (`:1563`) | живі (потік `task-new`) | 4d-4c |
| `integrations`-гейти (`integrations_on()`, `integrations_for`, `_implicit_on`, `require_integrations`, `ProjectComments._module`) | живі | 4d-4c |
| `/api/gitlab-*` аліаси | живі (ідуть у `vcs`) | 4d-4c |
| `deai_modules.shared_state()` і поле `shared_state` запису | живі: це тепер **єдина** ознака «спільного стану» для закону ізоляції | не видаляється |
| `ProjectComments.kind == 'implicit'`, `serve._overview_launch(legacy=…)` | значення/параметр завжди хибні — видалити з `Implicit` у 4d-4b, параметр `legacy` лишити (ЛІГА = `space.legacy is True`) | параметр — 4d-4c |
| `spaces.LEGACY_MARKERS` (`:44`) | живі (охоронець маркера, §1.1) | 4d-4c |

## Свідомі відмінності для людини

### Мігрована ЛІГА (звичайний випадок)

1. **Корінь `tasks.json` ЛІГИ втрачає** (за умови рівності) `supabase_url`, `supabase_key`, `jira_base`, `jira_email`, `jira_token`, `gitlab_ssh_key`, `gitlab_host_ip`, `preview_password`. Файл виглядає інакше; бекап кроку й `tasks.json.bak` (байти до кроку) — на місці. Старий Deai (≤0.20) чи
   будь-який зовнішній інструмент, що читав ці ключі з файла, їх не знайде, доки не зроблено `restore` кроку Е.
2. **`bin/registry.py` бере SSH-ключ із запису `git-sync`** (раніше — з кореня). Якщо в записі `ssh_key` порожній і корінь ключа не мав — той самий дефолт `~/.ssh/gitlab_ed25519`. Якщо в записі й корені були **різні** ключі, реєстр піде ключем запису (нотатка `differs:gitlab_ssh_key` попередить на старті кроку).
3. **На «Підключенні» зʼявляються** `ssh_key`/`host_ip` у `git-sync` (видимі значення — шлях і IP) і «Пароль превʼю: задано» у `vercel-publish`. Редагування пароля там **тепер діє** на превʼю ЛІГИ (раніше режим `design-canvas` його ігнорував). Порядок: пароль задачі > секрет запису > `1100`.
4. **Оточення й `pipeline-feedback` не читаються взагалі.** Роль, яку на момент міграції не було чим вмикнути (`no-jira`/`no-supabase`), раніше підхоплювала `Implicit`-ланка з оточення пізніше — тепер облікові треба внести на «Підключенні». `SUPABASE_SERVICE_KEY` для `bin/overview_push.py` — те саме: якщо
   дашборд-запису нема, синк каже «нема постачальника»; сервісний ключ вноситься як секрет `key` запису `supabase-dashboard`.
5. **Старт друкує вимкнені ролі** (по рядку на роль із причиною й командою) — на КОЖНОМУ старті, поки роль вимкнена. Якщо людина свідомо не користується роллю, рядок лишається (ввімкнути її на «Підключенні» — зникне).
6. **`capabilities` на помилці рішення (`space-json-unreadable` тощо) тепер `None` для всіх ролей**, а не `'legacy'` для `publish`/`vcs` (`deai_modules.py:1969`). Екран «Підключення» ховав це за `error`; зовнішній споживач, що читав `'legacy'` як «ввімкнено», бачитиме `None`.
7. **Тексти «не налаштовано»** (`comments-unconfigured`, `tracker-unconfigured`, `notify-unconfigured`, `dashboard-unconfigured`) називають екран «Підключення», а не `tasks.json`.
8. **Нечитабельний `space.json` у ЛІЗІ** тепер дає `space-json-unreadable` для КОЖНОЇ ролі (раніше — для чотирьох і лише в просторі з `integrations`; `publish`/`vcs` тихо йшли `Implicit`).
9. **Відкат** кроку Е повертає ключі в корінь (домерджем), але **не відновлює правок кореня, які людина зробила після кроку** — вони як були (`kept-live`).
10. **Пароль превʼю, відмінний від інертного секрета (Д4):** секрет перезаписано значенням кореня (старий — у бекапі).

### Немігрована ЛІГА (`skip-held`, `skip-path-in-git`, `skip-*`, `abort-*`)

11. **Усі шість ролей вимкнені** (таблиця §4): без публікації, командних коментарів, синку з GitLab, «Команди», статусів Jira й тиші Teams; `bin/overview_push.py` — «нема постачальника». Раніше — працювали через оточення/корінь. Найчутливіший випадок — `skip-path-in-git`
    (постійний): ролей не повернути, поки тека простору в робочому дереві git; підказка друкується на кожному старті.
12. Корінь `tasks.json` такої ЛІГИ **не чіпається** (Е пропущено): ключі лишаються, але їх ніхто не читає — «мертві дані», доки міграція не пройде.

### Розробнику/тестам

13. Ізольований прогін більше не бачить облікових у корені файла задач; живі й юніт-тести, що клали туди `supabase_*`/`jira_*`, переписуються (Додаток Б).
14. `serve.supabase_config`, `serve.jira_config`, `install_config.{supabase,jira,service_key}_*`, `vcs_target(cfg,…)`, `gitlab_cfg(cfg,…)`, `preview_password(cfg, task)` — змінені/видалені підписи.

## Відкат (0.21 → 0.20 → …)

- **0.21 → 0.20:** `python3 bin/migrate_liga.py restore <stamp-E> --hold` **обовʼязково**, інакше 0.20 живе без: `preview_password` (його compat-гілка читає лише корінь/задачу → пароль зсунеться на `1100`), `gitlab_ssh_key` для реєстру
  (`bin/registry.py` 0.20 читає корінь → дефолтний ключ), `supabase_*`/`jira_*` як запас для немігрованих ролей. `restore` Е повертає `space.json`, секрети й **домерджує ключі** в корінь. Далі за потреби — як у 0.20 (`d`, `c`, `b`, `a`, LIFO).
  0.20 про позначку `liga-4d4b` не знає (ігнорує невідомий ключ `migrations`), налаштування `ssh_key`/`host_ip` і секрет `password` у записах — валідні оголошені поля.
- **Без `restore`, але з поверненням ключа руками:** `tasks.json.bak` — байти ДО кроку (ручний відкат, як у D); перезаписує живий файл — задачі, створені після кроку, зникнуть. Тому `restore`, а не `.bak`.
- **0.21 → 0.20 на машині, де Е не виконувався** (немігрована ЛІГА): нічого відкочувати; 0.20 поверне `Implicit`.
- Нічого не видаляється назавжди: копії в бекапі кроку (`<DEAI_HOME>/backups/<stamp>-liga-4d4b`, 0600/0700), але див. «Ризики» про єдину копію.

## Тестування

**Знімок.** Генератор `tests/make_before_4d4b.py` → `tests/fixtures/liga-migration/before-4d4b.json`, знятий з **замороженої копії v0.20.0** (`git archive v0.20.0`, як `make_before_4d4a.py`), спільні помічники з `make_before_4d3a/3b/4d4a`. Стенди:
(1) мігрована ЛІГА з усіма записами й рівними оригіналами (звичайний шлях), (2) мігрована з **різними** значеннями (`differs:*`, конфлікт пароля), (3) мігрована частково (`no-record:*`, `partial:supabase`), (4) **немігрована** ЛІГА (`skip-held`) — знімок того, що 0.20
робила через `Implicit` (еталон для таблиці «стало вимкнено»), (5) звичайний простір. Секції: `capabilities`, `provider`, `api` (`/api/task` пароль/`preview_gate`, `/api/modules`, `/api/comment-config`), `isolation` (форми відповідей у ізоляції), `registry_ssh`, `vcs_target`, `startup_text`.
Знімки `before-4d2/4d3a/4d3b/4d3c/4d4a` лишаються й **продовжують проходити** там, де стенд — мігрована ЛІГА; місця, де стенд — неявна ЛІГА (4d2, 4d3a), переходять на явну фікстуру `liga_fixture` (їх зафіксовані значення — еталон, а не код).

**Паритет після міграції (`AfterMigrationParity4d4b`).** Для стендів 1–3 і 5 те саме, що в 0.20, **крім** `EXPECT_DIFF` — точного переліку (ключі, а не «приблизно»):
`api.task.preview_password` (стенд 2: секрет перезаписано кореневим — рівно значення кореня, отже БЕЗ відмінності; відмінності нема, ключ у таблиці, щоб тест це стверджував),
`root_keys` (корінь без восьми ключів; усе інше побайтно те саме), `modules.git-sync.settings` (+`ssh_key`,`host_ip`), `modules.vercel-publish.secrets` (+`password` як «задано»), `registry_ssh` (з запису), `capabilities.error_path` (`'legacy'` → `None`), тексти `*-unconfigured`, рядок старту «ролі ЛІГИ».
Стенд 4 (немігрована): таблиця «стало вимкнено» буквально, по шести ролях, відповідь API кожної (409 `no-publish-module`, `notify-off`, вкладка «Команда» відсутня, `vcs_provider()` → `None`, …).

**Модульні тести кроку Е** (`tests/test_liga_migrate_e.py`): ворота (`held` раннього кроку тримає Е); кожен рядок таблиці §1.1 і правило 1–6 (включно з `unfit`, `partial:supabase`, `differs`, `overwrote:password`, `compat != design-canvas`);
охоронець маркера; `abort-originals` (недоступний на запис файл, постійна гонка), `abort-verify` (підміна `_load_secrets` між 3 і 5); порядок запису (збій між 4/6, між 6/7 → повторний запуск доробляє, нічого не втрачено); бекап/`.bak`; **відкат**: домердж лише відсутніх ключів, `kept-live`, живі правки задач
не губляться, `--hold`, LIFO на п'ять кроків; `skip-nothing` (з нотатками — позначка); ідемпотентність; старт на п'ять кроків (один старт зі старої установки 0.16: п'ять бекапів); CLI `run`/`dry-run`/`status`/`unhold`; `roles_state` по кожному рядку §4.1.

**AST-охоронець `NoOriginalsRead`** (`tests/test_no_originals.py`, за зразком `NoTracksAdapter`, `tests/test_no_adapter.py`): `app/**/*.py` (крім `liga_migrate.py`), `bin/*.py`, `ops/*.py` не мають **рядкових констант** `supabase_url`, `supabase_key`, `jira_base`, `jira_email`, `jira_token`, `gitlab_ssh_key`, `gitlab_host_ip`, `SUPABASE_URL`,
`SUPABASE_KEY`, `SUPABASE_SERVICE_KEY`, `JIRA_EMAIL`, `JIRA_TOKEN`, `pipeline-feedback` (поза докстрінгами/коментарями), ні імен `supabase_from`, `jira_from`, `service_key_config`, `supabase_config`, `jira_config`, `legacy_ctx`, `legacy_module`; `preview_password` — дозволено лише як `.get`/підписка на імені задачі (`task`, `t`) та як імʼя функції.
Окремий охоронець `NoImplicit`: ніхто не імпортує `implicit`, імені `Implicit` нема (`app/implicit.py` видалений).
**Мутації** (кожна має червоніти; `python3 -B`, файл відновлюється, `sha256` до/після): повернути читання кореня в `preview_password`; прибрати рівність у правилі видалення (видаляти завжди); прибрати перевірку `abort-verify`; видаляти ДО копії; пропустити охоронець маркера; зробити `restore` перезаписом
файла замість домерджу; прибрати `real_home` із `comments_route`; повернути `Implicit` в `_provider_for`; прибрати `partial:supabase`.

**Тести, які це змушує змінити:** Додаток Б. **Живі тести:** `tests/live/fixture.mjs` (`startServer(…, { supabase: true })` більше не пише `LIGA_SUPABASE` у корінь, а будує мігровану ЛІГУ — або запускає справжню міграцію через `DC_MIGRATE_LIGA=1` і `deaiDir` ≠ `.deai`;
`legacyExtra` лишається ТІЛЬКИ для тестів міграції), `_liga-supabase.mjs`, `liga-migrate.test.mjs` (п'ятий крок, `unhold`, друк ролей), `comments.test.mjs`, `dashboard-role.test.mjs`, `tracker-role.test.mjs`, `notify-role.test.mjs`, `teams-mute.test.mjs`, `tasks-home.test.mjs`,
`preview-password.test.mjs` (секрет замість кореня), `git-sync.test.mjs`/`legacy-publish-cli.test.mjs` (`ssh_key` із запису). Перед фінальним ревʼю — повний `npm run test:live` послідовно (правило «задачі з test:live — послідовно»; git-ідентичність у тимчасовому `HOME`).

## Ризики

| № | Ризик | Пом'якшення |
|---|---|---|
| Р1 | **Єдина копія облікових** — `secrets.json` і `backups/` в одному домі (§6) | рядок після кроку; бекап 0600; документ; (питання П1 — чи тримати зовнішню копію) |
| Р2 | **Немігрована ЛІГА втрачає всі ролі**, зокрема постійно при `skip-path-in-git` | рядок-на-роль зі шляхом виправлення; `unhold`; підказка перенести теку; reality-check на машині власника ДО релізу (`bin/migrate_liga.py status` — чи всі кроки застосовані) |
| Р3 | **Зовнішній інструмент читає корінь** (`gitlab_ssh_key`/`preview_password`/`supabase_*`) — відомо лише власнику | `restore` Е; питання П1; не видаляємо оточення/`pipeline-feedback` |
| Р4 | Неявний простір без ролей: викликач, що «забув зафіксувати простір», мовчки втрачає роль | аудит усіх `provider(…)` без `space` (Task 6); тест «кожен реальний шлях фіксує простір» |
| Р5 | Видалення з `tasks.json` — єдиний крок, що ЗМЕНШУЄ дані; гонка з UI | порядок «копія → перевірка → видалення»; `_file_sig`-ретраї; `.bak`; повторне звіряння рівності всередині локу; бекап до запису |
| Р6 | Ізольований закон змінився (облікові з тимчасового дому) — міг би пропустити справжні | `real_home` за `pwd` + мутація; ізольовані `dashboard/tracker/notify` лишаються «ніколи живі» |
| Р7 | Мертва `has_markers`: стерті `gitlab_*` → реєстр відновлюється з `integrations:false` | охоронець маркера (`marker-kept`) |
| Р8 | Обсяг переписування тестів (≈50 файлів торкається джерел облікових/швів) | `tests/liga_fixture.py` + мутаційні охоронці; план ділить Додаток Б на 3 завдання |
| Р9 | `'legacy'` у `capabilities` зникає раніше, ніж JS-запасні гілки (4d-4c) | JS сприймає `None` як «нема» (перевірити `connections-model.js` у плані); у 4d-4c гілки видаляються |
| Р10 | Крок Е після D на старті зі старої установки (п'ять кроків, п'ять бекапів) — довгий старт | кроки швидкі (файли), порядок відомий; `status`/підказка відкату — одна, для найпізнішого |

## Рішення контролера щодо відкритих питань (07.11.2026)

Власник: «Делай следующий этап автономно, если нет вопросов». П1 і П2 мають безпечні дефолти з відкатом, тож питаннями до власника
не стають — приймаються рекомендації: **П1** — виконувати крок Е (файл задач ЛІГИ — власний файл Deai; спільні з інструментом ЛІГИ
оточення й `pipeline-feedback` не чіпаємо); **П2** — `design_work_roots`/`profile_repos` лишаються в корені до 4d-4c/1.0.

Факт для Р2/Р3 (перевірено 07.11.2026 без читання вмісту): у робочій установці Deai власника файла задач ЛІГИ (`<repo>/tasks.json`)
нема, а домашня тека Deai спільна з інструментом ЛІГИ (відома пастка спільного стану, рішення «розвести домашні теки» — до заміни
інструмента). Тобто на машині власника кроки A–Е реально спрацюють у день заміни інструмента ЛІГИ на Deai, а не на першому старті
0.21; перевірка `status` — частина того дня, а не цього релізу.

## Відкриті питання (лише рівня власника)

- **П1. Чи читає щось поза цим репо корінь `tasks.json` ЛІГИ** (`gitlab_ssh_key`, `preview_password`, `supabase_*`, `jira_*`) — зовнішній dev-pipeline, старий канвас, інструмент ЛІГИ? Тільки власник знає.
  **Рекомендація:** вважати, що ні (оточення й `pipeline-feedback` — спільні, і ми їх не чіпаємо; корінь — файл самого Deai), виконати Е, а розбіжність усунути `restore` кроку Е. Якщо відповідь «так» для конкретного ключа — додати його до виключень `ORIGINAL_KEYS`.
- **П2. `design_work_roots` і `profile_repos` у корені** — видаляти в 0.21 чи лишити? **Рекомендація:** лишити (Д2): секретів у них нема, рівність з `tracks` недоказова, видалення — в 4d-4c/1.0, коли інструмент ЛІГИ піде.

## Додаток А: що крок Е робить зі старих версій файла (коротко)

| Вхідний корінь | Результат |
|---|---|
| усі вісім ключів, записи A–C рівні | усі видалено; `copied: [gitlab_*, preview_password]`; нотаток нема |
| `supabase_*` є, запису `supabase-teams` нема | пара лишається; `partial:supabase`, `no-record:supabase-teams` |
| `jira_base` є, токен лише в оточенні | `jira_base` видалено (рівний `settings.base`); токена в корені нема — нічого |
| `preview_password`, `vercel-publish.compat = ''` | лишається; `no-record:vercel-publish` (режим модуля; інший зміст секрета) |
| `gitlab_ssh_key` = запис `ssh_key` | видалено без копії |
| `gitlab_ssh_key` ≠ запис `ssh_key` | лишається; `differs:gitlab_ssh_key` |
| останній маркер ЛІГИ | `gitlab_host_ip` лишається; `marker-kept:gitlab_host_ip` |

## Додаток Б: тести й живі тести, які змінює цей етап

Підрахунок — `grep` на `v0.20.0` (кількість рядків із джерелом облікових/швом/`Implicit`; не обсяг роботи):

- **Перехід на явну фікстуру ЛІГИ** (облікові з кореня/оточення → `tests/liga_fixture.py`): `tests/sbconf.py` (`write_root`/`drop_root`/`ENV` → фікстура запису), `test_legacy_comments.py` (44), `test_dashboard.py` (25+3), `test_tasks_overview.py` (14+2+20 швів), `bin/test_overview_push.py` (10; сервісний ключ — тест «більше не береться»),
  `test_inbox.py` (9), `test_comments_agent.py` (9), `test_comments_role.py` (8+13 `Implicit`), `test_integrations_off.py` (7), `test_spaces_serve.py` (6), `test_publish_module.py` (6+15 `preview_password`+12 `Implicit`), `test_liga_migrate.py` (5+17 jira), `test_liga_migrate_b.py`/`_c.py`/`_d.py` (`Implicit`/корінь),
  `test_serve.py` (3+14 `preview_password`), `test_modules.py` (3+25 `Implicit`), `test_tracker.py` (32 jira), `test_notify.py`, `test_state.py`, `test_supabase_comments.py`, `test_vcs_core.py` (11 `gitlab_ssh_key` → налаштування запису), `test_gitlab_sync.py`, `test_task_tags.py`, `test_tracks.py`.
- **Переписати/видалити:** `tests/test_implicit.py` (869 рядків, 57 згадок): `ImplicitCore` → `IsolationCore` (таблиця `FAKE_ENV`, `route`, `real_home`); `ProviderImplicit` → «неявний простір → `None`, ЛІГА без запису → `None`»; `IsolatedInstallConfig` (≈15 тестів) → «ізольований прогін не читає кореня; читає
  `module_ctx` лише в тимчасовому домі»; `Before4d2Shape`/`EffectiveSpace`/`LigaLikePin` лишаються; `RolesParity` — на явній фікстурі.
- **Знімки-генератори** `make_before_4c*`/`4d1`/`4d2`/`4d3a`/`4d3b`/`4d3c`/`4d4a`: НЕ переганяються (еталони), але їхні читачі в тестах — на явну фікстуру там, де знімок зроблено з неявної ЛІГИ.
- **Нові:** `tests/test_liga_migrate_e.py`, `tests/test_no_originals.py`, `tests/test_isolation.py`, `tests/liga_fixture.py`, `tests/make_before_4d4b.py` + `before-4d4b.json`.
- **Живі:** `tests/live/{fixture,_liga-supabase,liga-migrate,comments,dashboard-role,tracker-role,notify-role,teams-mute,tasks-home,preview-password,git-sync,legacy-publish-cli}.mjs`; перевірити `canvas`, `comment-audience`, `inspector-project`, `overview-comments`, `shell-typing` (по одній згадці).
- **Модулі/документи:** `app/modules/vercel-publish/module.json` (підпис `compat`, версія), `tasks.example.json`, `README.md`, `CHANGELOG.md`, `package.json` (0.21.0), `docs/design/spaces-and-modules.md`.

## Додаток В: оцінка обсягу

≈ **16 завдань плану** (код — 8: крок Е чистий розрахунок; запис Е + відкат Е; `roles_state`/старт/`status`/`unhold`; `app/isolation.py` + перенесення швів; провайдер без `Implicit` + споживачі; рантайм без оригіналів (`preview_password`, `_vcs_ssh`, `registry`, `overview_push`);
маніфест/тексти/документи; охоронці + мутації. Тести — 5: знімок `before-4d4b`; `liga_fixture` + перехід `test_implicit`/ядро; перехід 20 файлів двома хвилями; `AfterMigrationParity4d4b`; живі тести. Реліз — 3: повний прогін послідовно, наскрізний аудит (перед релізом — на машині власника
`status` п'яти кроків), версія/CHANGELOG/тег). Ризик найбільший у перемикачі провайдера (споживачі `Implicit` ≈ 20 місць) і в переписуванні тестів.
