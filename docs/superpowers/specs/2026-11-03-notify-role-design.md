# Етап 4c-3: сповіщення Teams як роль `notify` і модуль `supabase-teams` (0.14.0)

Дата: 03.11.2026. Попередній етап — 4c-2 (0.13.0, статуси трекера). Дорожня карта — `docs/design/spaces-and-modules.md`.

## Рішення власника

- **26.10.2026 (етап 4):** чисте ядро + паритет; усе, що робить простір ЛІГА, стає модулем.
- **02.11.2026:** модулі 4c — вбудовані й загальні, специфіка ЛІГИ — у конфігу й адаптері ядра. 4c-1 дашборд (0.12.0) →
  4c-2 трекер (0.13.0) → **4c-3 тиша Teams через роль `notify` (ця спека, 0.14.0)** → 4d.
- **03.11.2026:** вбудований модуль дає **повні сповіщення + тишу**: свій `schema.sql` (новий пін → картка в Teams через
  вебхук із Vault, журнал доставок, тиша на канал) у тому ж Supabase, що й коментарі; будь-який простір із коментарями в
  Supabase отримує картки й перемикач. ЛІГА — через той самий модуль, її база не змінюється.

## Проблема

- Сповіщення Teams існують лише в ЛІГИ, і живуть у **базі** (схема comment-layer ЛІГИ, поза цим репо): INVOKER-тригер
  `cl_notify_teams` на INSERT у `comments` → DEFINER `cl_send_teams(id)` (свіжість 2 хв, тиша, вебхук із Vault
  `teams_webhook_url`, `net.http_post`, журнал `teams_delivery_log`) → Power Automate → канал Teams.
- Канвас лише читає й перемикає тишу: `teams_rpc` (`app/serve.py`) кличе RPC `teams_mute_state`/`teams_mute_set` Supabase
  ЛІГИ (`supabase_config()`, тайм-аут 8 с), маршрут `/api/teams-mute` (GET стан, POST перемикання), пункт «Сповіщати
  Teams» у дропдауні публікації (`bar-model.js` `teamsItem`, `app.js` `teamsnotify`). Гейт усього — прапорець
  `integrations` (`spaces.integrations_on()`, у клієнті `noOutward`/`noInteg`).
- Звичайний простір сповіщень не має взагалі; роль `notify` — остання зарезервована (`ROLES_RESERVED`).

## Мета

1. Роль `notify` у ядрі: ядро кличе модуль, щоб прочитати й перемкнути тишу каналу.
2. Вбудований модуль **`supabase-teams`** зі своєю схемою: картка Teams на кожен новий пін, тиша на канал, журнал доставок,
   чесний `check`.
3. ЛІГА — неявний постачальник через той самий модуль (`ctx` з конфігу установки, ті самі RPC ЛІГИ).
4. Перемикач у канвасі й маршрут залежать від постачальника ролі, а не від `integrations`.
5. Паритет ЛІГИ: ті самі запити тиші, ті самі відповіді маршруту, той самий пункт меню.

## Не мета

- Зміни бази ЛІГИ (її тригери, картка з назвою проєкту з `overview_projects`, публічний ключ для RPC тиші).
- Інші месенджери (Slack тощо), особиста тиша (на людину), дайджести, ручна кнопка «надіслати».
- Прапорець `integrations`, літерал `'legacy'`, ключ `profile` — 4d. Перейменування маршруту `/api/teams-mute` — 4d (API).
- Доктор інсталяції ЛІГИ (`teams-muted`, `teams_delivery_health`) — живе в design-office, не тут.

## Дизайн

### 1. Роль `notify`

- `ROLES_CALLED` += `'notify'`; `ROLES_RESERVED = ()` (порожньо — усі ролі дорожньої карти викликані).
- Обовʼязкові функції `server.py`: `check(ctx)`, `mute_state(ctx)`, `mute_set(ctx, channel, muted, by)`.
  - `mute_state(ctx)` → список `{'project_id': str, 'muted_at': str|None, 'muted_by': str}` (замовчані канали). Ядро
    нормалізує (`notify.normalize_mutes`): лише словники з непорожнім рядковим `project_id` ≤ 200 знаків; `muted_by` —
    рядок ≤ 200 (інше → `''`); `muted_at` — рядок ≤ 40 чи `None`; не більше `MAX_MUTES = 1000`; не список → `ValueError`.
  - `mute_set(ctx, channel, muted, by)` → `bool` (новий стан); `channel` — непорожній рядок ≤ 200, `muted` — `bool`,
    `by` — підпис ≤ 200. Ядро перевіряє аргументи ДО виклику.
- `LEGACY_ROLES` += `'notify'`; `STRICT_LEGACY_ROLES` += `'notify'` (зашитий шлях — спільний Supabase ЛІГИ); у
  `LEGACY_ON_ERROR_ROLES` — НІ.
- `capabilities.notify` — id модуля / `'legacy'` / `null`.
- Коди в `STATUS`: `notify-unconfigured` 409 (ЛІГА без конфігу Supabase), `notify-error` 502.
- Тайм-аут: ядро чекає `NOTIFY_TIMEOUT = 10` с на виклик; власний тайм-аут сокета модуля — 8 с (як у `teams_rpc`).
- Нове ядро `app/notify.py` (БЕЗ імпорту `serve`): `normalize_mutes`, `mute_view(channel, rows, me)` (переїзд
  `teams_mute_view`: тиша каналу покриває підканали `<канал>/…`; `mine` — за підписом), `legacy_ctx(url, key, space_id)`,
  `legacy_module()`, константи. `mute_signature()` лишається в `serve` (особа машини), передається як `me`.

### 2. Модуль `supabase-teams` (вбудований, 1.0.0)

- Налаштування: `url` (text, обовʼязкове — правила адреси `supabase-comments`), `key` (secret, **НЕ** `public`,
  обовʼязкове: непублічний ключ — `service_role` чи ключ окремої ролі).
- `schema.sql` (людина запускає один раз у SQL-редакторі проєкту, ПІСЛЯ схеми `supabase-comments`; ідемпотентна;
  шапка-попередження «окремий проєкт / не адоптуй чужу таблицю», як у `supabase-comments`, + «ЛІГА: не запускати — у вашій
  базі це вже є»):
  - `create extension if not exists pg_net;`
  - `teams_delivery_log(request_id bigint pk, comment_id text, created_at)` — RLS, `revoke all` від `anon`/`authenticated`;
  - `teams_project_mute(project_id text pk 1..200, muted_at, muted_by text ≤200)` — RLS, `revoke all` від `anon`/`authenticated`;
  - `comment_teams_card(c comments) → jsonb` — Adaptive Card 1.4 у конверті `{type: message, attachments: [...]}` лише через
    `jsonb_build_object` (без рядкової конкатенації): «Новий коментар», факти (Проєкт = `project_id`, Ітерація/Сторінка з
    `meta.version`/`meta.route`, Автор, Статус), текст ≤ 500 знаків, картинка за `meta.shotUrl` (https), кнопка за
    `meta.url` (https). Підписи — українською, зібрані в один `declare`-блок на початку функції (легко змінити);
  - `cl_send_teams(p_comment_id text)` — `security definer`, `set search_path = pg_catalog, public, vault, net`: свіжість
    2 хв; тиша (канал і підканали); вебхук `vault.decrypted_secrets` `teams_webhook_url` (нема → `raise warning`, вихід);
    `net.http_post`; запис у журнал; `exception when others` → `raise warning` (не абортить). `revoke all from public`,
    `grant execute to anon, authenticated` (кличе INVOKER-тригер від імені автора піна);
  - `cl_notify_teams()` — `security invoker` тригер `after insert on comments`: лише коли `row_security_active('public.comments')`
    (адмінські вставки — мимо), виклик у `begin … exception when others then null; end`;
  - `teams_mute_set(p_project, p_muted, p_by)`, `teams_mute_state()` — DEFINER; ⛔ на відміну від ЛІГИ — `grant execute`
    лише `service_role` (`revoke … from public, anon, authenticated`): перемикач кличе канвас непублічним ключем, сторінка —
    ніколи;
  - `teams_notify_health(window_hours int default 6) → (webhook_set bool, sent, responded, failed, last_failed_at,
    last_sent_at)` — DEFINER, лише `service_role`; лише агрегати й факт наявності секрету, без значення.
- `server.py` (лише stdlib; хелпери адреси/TLS/`_open`/`_NoRedirect`/`_clean` — копія з `supabase-dashboard`, не імпорт):
  - `mute_state` → `POST <url>/rest/v1/rpc/teams_mute_state` `{}`; `mute_set` → `POST …/rpc/teams_mute_set`
    `{"p_project", "p_muted", "p_by"}` — тіла й заголовки (`apikey`, `Authorization: Bearer`, `Content-Type`) рівно як у
    `teams_rpc` 0.13.0; тайм-аут сокета 8 с; без редиректів;
  - `check`: адреса за правилами; публічний ключ (`sb_publishable_…`, JWT `role: anon`) → вердикт «потрібен непублічний ключ»
    (не для `ctx['legacy']`); `teams_mute_state` 404/`PGRST202` → «запустіть schema.sql»; далі `teams_notify_health(6)`:
    `webhook_set = false` → вердикт `notify-no-webhook` «у Vault нема секрету teams_webhook_url»; інакше ok з деталлю
    «доставок за 6 год: N, невдалих: M». Для `ctx['legacy']` (ЛІГА) — лише `teams_mute_state` (у базі ЛІГИ
    `teams_notify_health` нема);
  - тексти помилок: фіксовані слова + HTTP-статус + код PostgREST, ≤ 200; ключа й тіл — ніколи.

### 3. Адаптер ЛІГИ (неявний постачальник)

- `notify.legacy_ctx(url, key, space_id='')` — `url`/`key` з `supabase_config()` (той самий, що в коментарів і дашборда);
  нема → `ModuleError('notify-unconfigured', message='Supabase не налаштовано')`; `legacy: True`. ⛔ НЕ `module_ctx()`.
- ⛔ Ізоляція (закон 03.08.2026, переноситься з `teams_rpc`): шлях ЛІГИ — спершу шов `DC_TEAMS_FAKE` (локальний JSON, як
  зараз, лише для `'legacy'`), далі `DC_TASKS_FILE`/`DC_NO_OVERVIEW` → `OSError('ізольований конфіг: спільний стан Teams не
  чіпаємо')` без мережі, далі модуль.
- `teams_rpc` зникає; його місце — `notify_call(fn, *args)` у `serve.py` (резолв постачальника, шов, ізоляція, виклик через
  `deai_modules.call(…, timeout=NOTIFY_TIMEOUT)`).

### 4. Маршрут і клієнт

- `/api/teams-mute` GET/POST: гейт — постачальник ролі `notify` простору запиту (`notify_resolve()`); нема → 409
  `{code: 'notify-off', error: 'сповіщень Teams у просторі нема'}` (для ЛІГИ й простору без інтеграцій — та сама поведінка,
  що зараз: у простору без інтеграцій і без модуля постачальника нема). Збій модуля в GET → `{channel, error}` («не знаю» ≠
  «увімкнено»); у POST → 502 `{ok: false, channel, error}`. Origin-перевірка POST — без змін, першою.
- Клієнт: Teams-пункт меню й опит `/api/teams-mute` — за `capabilities.notify` (новий `hasNotify(space)` у
  `spaces-model.js`, як `hasVcs`/`hasTeamComments`), а не за `integrations`. Тексти пункту — без змін.
- «Підключення» й майстер: роль `notify` у `ROLE_ORDER` (після `tracker`, перед `tokens`), іконка з наявного набору,
  `LEGACY_ROLES` клієнта; `BUILTIN_TEXT["supabase-teams"]` (`url`, `key`); i18n UK/EN «Сповіщення Teams» / "Teams
  notifications", опис, «Зараз: …», наслідок вимкнення («нові коментарі перестануть надходити карткою в Teams; перемикач
  тиші зникне»); `CHECK_KEYS` для `notify-no-webhook`.

## Паритет і перевірки

- **Знімок 0.13.0 ДО змін** (`tests/fixtures/notify/before-4c3.json`): (а) запити `teams_rpc` ЛІГИ на заглушці мережі (метод,
  шлях, тіло, заголовки без значення ключа, тайм-аут) для стану й перемикання; (б) відповіді GET/POST `/api/teams-mute` ЛІГИ
  на шві `DC_TEAMS_FAKE` (замовчано мною / колегою / підканал / не замовчано) і в ізоляції; (в) статуси маршруту в просторі без
  інтеграцій; (г) пункти меню (`bar-model`) з інтеграціями й без.
- Диференційні після змін: те саме для ЛІГИ; модуль шле ті самі запити, що `teams_rpc`.
- Модуль: правила адреси; публічний ключ; `check` (нема схеми, нема вебхука, здоровʼя); тексти без ключа; без редиректів.
- Схема — **статично** (Postgres на машині нема): кожна функція `security definer` має `set search_path`; `cl_notify_teams` —
  `security invoker` з `row_security_active`; обидві відправки ковтають помилки; `teams_mute_*` і `teams_notify_health` —
  `grant` лише `service_role`, `revoke` від `anon`/`authenticated`/`public`; таблиці з RLS і `revoke all`; картка без `||`
  над даними коментаря (лише `jsonb_build_*`, обрізання тексту — дозволений виняток); ідемпотентність (`if not exists`,
  `create or replace`, `drop trigger if exists`).
- Ядро: `normalize_mutes`; `mute_view` (підканали, `mine`); перевірка аргументів `mute_set`; ізоляція ЛІГИ.
- Мутації: ізоляція `DC_TASKS_FILE`/`DC_NO_OVERVIEW`; `'notify'` у `LEGACY_ON_ERROR_ROLES`; підканали в `mute_view`; гейт
  маршруту за роллю; перевірка публічного ключа; кожна статична перевірка схеми.
- Живі: звичайний простір із фейковим модулем `notify` без інтеграцій — пункт «Сповіщати Teams» є, перемикання працює, збій
  → пункт вимкнений з причиною; без модуля — пункту нема; «Підключення» — картка ролі; ЛІГА (`DC_TEAMS_FAKE`) — як у 0.13.0.

## Свідомі відмінності від 0.13.0

- Пункт «Сповіщати Teams» і маршрут — за роллю `notify`, а не за `integrations` (для ЛІГИ — те саме).
- Код відмови маршруту без постачальника — `notify-off` (було `integrations-off`), текст той самий за змістом.
- У схемі модуля RPC тиші — лише для непублічного ключа (у ЛІГИ — для ключа сторінки, її база не змінюється).

## Відомі обмеження

- SQL схеми не виконується в тестах (нема Postgres) — лише статичні перевірки; перший запуск на справжньому Supabase —
  ручний крок власника.
- Картка без назви проєкту (лише id каналу) і українською; Power Automate (чи інший приймач) — налаштовує людина.
- Доставка «вистрілив і забув» (без повторів), як у ЛІГИ; здоровʼя видно лише в `check` на «Підключенні».
- `pg_net`/Vault мусять бути доступні в проєкті Supabase.

## Документи

`CHANGELOG.md [0.14.0]`, `README.md` (сповіщення в звичайному просторі), `docs/modules/authoring.md` (контракт ролі
`notify`; «reserved» — порожньо), `app/modules/supabase-teams/README.md` (схема, Vault, Power Automate — без вигаданих
URL), `docs/design/spaces-and-modules.md` (Stage 4c-3), `package.json` 0.14.0.

## Чекліст релізу

Фінальне ревʼю → повні прогони (npm test; Python 3.9.6; живі по одному) → дата в CHANGELOG → тег `v0.14.0` (анотований, від
neodisa) → явний push sha і тегу → памʼять.
