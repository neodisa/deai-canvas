# Етап 4b-2: коментарі простору ЛІГА через модуль `supabase-comments` (0.10.0)

Дата: 30.10.2026. Попередній етап — 4b-1 (0.9.0, публікація ЛІГИ через `vercel-publish`). Дорожня карта — `docs/design/spaces-and-modules.md`.

## Рішення власника

- **26.10.2026 (етап 4):** чисте ядро + паритет; у 4b стара публікація й коментарі ЛІГИ переїжджають на наявні модулі, зашиті
  константи Supabase і профілі йдуть з ядра.
- **30.10.2026:** 4b = 4b-1 публікація (0.9.0) → **4b-2 коментарі й константи Supabase (ця спека, 0.10.0)** → 4b-3 профілі (0.11.0).

## Проблема

Командні коментарі ЛІГИ — окремий шлях у ядрі, паралельний ролі `comments`:

- `COMMENT_SNIPPET` (≈65 рядків) з `supabase-js@2` з jsdelivr, вендорним `supabase-adapter.min.js` (3 КБ, джерела в
  репозиторії нема) і `CommentLayerSupabase({url, anonKey, projectId})`, з адресою й ключем, вшитими зі `SUPABASE_URL` /
  `SUPABASE_KEY` (`app/serve.py` ≈128);
- гілки `'legacy'` у `/commented`, `/api/comment-config` (`{sbUrl, sbKey, project}`), `publish_comments`/`build_preview`
  (копія `BUNDLES`), `ProjectComments` (вид `legacy`), `supabase_pins` (REST напряму), `bin/inbox.py patch_project_pin`,
  `bin/state.py _open_pins`, `app/overview-comments.js` (гілка `SB_JS` + `CommentLayerSupabase`), статичне
  підключення старого адаптера в `app/index.html`;
- константи Supabase в коді читають і компанійні частини 4c: командний дашборд (`_team_fetch`, `_overview_sync` →
  `bin/overview_push.py`) і тиша в Teams (`teams_rpc`).

Модуль `supabase-comments` (роль `comments`, 2b-2) уже вміє те саме для звичайних просторів — окрім кількох речей, які в
ЛІГИ є: власний канал (`dc/<задача>` / `comment_project`), завантаження скріншота піна в Storage (`meta.shotUrl` —
його бере картка Teams), номер ітерації при розвʼязанні (`resolved_v`), TLS із certifi.

## Мета

1. ЛІГА веде коментарі через модуль `supabase-comments` як **неявний постачальник** (зразок 4a/4b-1: `ctx` будує ядро,
   модуль береться з каталогу вбудованих). Скрізь, де ядро зараз розгалужується на `'legacy'`, — один шлях модуля.
2. Модуль отримує те, чого бракує для паритету (загальне, корисне будь-якому простору): необовʼязкове завантаження
   скріншотів піна, необовʼязковий номер ітерації в `resolve`, certifi.
3. `SUPABASE_URL`/`SUPABASE_KEY` зникають із коду. Адреса й публічний ключ проєкту Supabase ЛІГИ — у конфігу установки;
   одна функція ядра (`supabase_config()`) віддає їх і коментарям ЛІГИ, і частинам 4c.
4. Функціональний паритет ЛІГИ: ті самі канали, історія, тиша Teams, лічильники дашборда, скріншоти в картках Teams,
   аудиторії, внутрішній канал, розвʼязання з номером ітерації. Свідомі відмінності — перелічені нижче.

## Не мета

- Командний дашборд, статуси трекера, тиша Teams як ролі (`dashboard`/`tracker`/`notify`) — 4c; тут вони лише беруть
  адресу й ключ із конфігу замість констант.
- Профілі — 4b-3. Прапорець `integrations` і літерал `'legacy'` у `capabilities` — 4d.
- Опубліковані раніше превʼю ЛІГИ — не чіпаються (кожне несе свою копію шару, адаптера й ключа).
- `schema.sql` модуля на спільному проєкті ЛІГИ НЕ запускається (переписує політики); таблиця ЛІГИ вже має ту саму форму.

## Дизайн

### 1. Конфіг установки: адреса й ключ Supabase ЛІГИ

- Корінь `tasks.json` простору ЛІГА (`spaces.legacy_tasks_file()` — той самий файл, що несе `gitlab_ssh_key`):
  `supabase_url` (https, хост — DNS-імʼя) і `supabase_key` (публічний ключ: `sb_publishable_…` чи anon JWT; секретний
  ключ — відмова тими ж правилами, що в модулі).
- Запасний шлях — змінні оточення `SUPABASE_URL` / `SUPABASE_KEY` (їх уже вміє `bin/overview_push.py`; `_overview_sync`
  передає їх дитині).
- `supabase_config()` → `(url, key)` або `(None, None)`; кешу нема (файл маленький, читається на запит). Нема
  конфігу → коментарі ЛІГИ «недоступні» (як модуль, що не пройшов перевірку: сторінка з локальними пінами й плашкою,
  публікація без командних коментарів + `comments_unavailable`), дашборд і тиша Teams — тихо вимкнені (як зараз при
  `DC_NO_OVERVIEW`).
- `tasks.example.json` і README (розділ простору ЛІГА) — як заповнити. Тексти помилок без значень ключа.

### 2. Модуль `supabase-comments` 1.1.0

- **Скріншоти.** Нове необовʼязкове налаштування `shots_bucket` (текст; порожньо — вимкнено, як зараз). Коли задано,
  адаптер віддає шару `uploadShot(id, dataUrl)` — поведінка старого адаптера ЛІГИ: лише `data:image/…`, `POST
  {url}/storage/v1/object/<bucket>/comment-shots/<id>.jpg` з публічним ключем, `x-upsert: true`, `Cache-Control: 3600`,
  результат — публічна адреса `…/object/public/<bucket>/comment-shots/<id>.jpg` або `null`. Імʼя кошика — лише
  `[a-z0-9][a-z0-9_-]{0,62}`; `id` піна — лише безпечні символи (інакше `null`).
- **Ітерація при розвʼязанні.** `resolve(ctx, channel, id, status, reason, iteration=None)`: ціле `iteration` ≥ 1 →
  ще й `resolved_v`. Без нього — як зараз. Ядро передає номер, коли він є.
- **TLS.** HTTP-клієнт модуля — з контекстом certifi, коли пакет є (як `_ssl_context` ядра); інакше типовий.
- Решта модуля — без змін (канал, `list`, `check`, вимога публічного ключа).

### 3. Ядро: неявний постачальник коментарів ЛІГИ

- `_comments_legacy_ctx()` — `settings = {url, shots_bucket: 'overview-thumbs'}`, `secrets = {key}` з конфігу §1,
  `ModuleError`; без `module_ctx()` (не чіпати `~/.deai`). Нема конфігу → `ModuleError('comments-unconfigured')`
  (новий код у `STATUS`, 409) — ним живляться «недоступні».
- `comments_provider(space)` для `'legacy'` повертає `(модуль, legacy ctx, legacy=True)` (за зразком `vcs_provider`);
  `comments_client`, `ProjectComments`, `publish_comments`, `/commented`, `/api/comment-config` беруть клієнтський
  конфіг модуля через цей `ctx`.
- **Канал ЛІГИ не змінюється:** `comment_channel(task, tid)` (`comment_project` чи `dc/<tid>`, `+/internal`) замість
  `channel_for` скрізь, де постачальник — ЛІГА. `publish_comments` отримує `task`.
- `/api/comment-config` для ЛІГИ — форма модуля (`{ch, module, client[], config, channel, version, user}`), канал — §3.
  Гілка `sbUrl/sbKey` зникає. `app/overview-comments.js` — лише шлях модуля (гілка `SB_JS`/`CommentLayerSupabase`
  зникає); `app/index.html` більше не вантажить старий адаптер.
- Сторінка `/commented` і опубліковане превʼю ЛІГИ — `MODULE_COMMENT_SNIPPET` з каналом ЛІГИ, аудиторіями й
  внутрішнім каналом, як зараз у ЛІГИ (аудиторії/інспектор — ті самі прапорці, що в гілці ЛІГИ сьогодні).
  Збірка ЛІГИ копіює файли модуля (`supabase.min.js`, `adapter.js`) замість `BUNDLES`; мітка збірки лишається
  `legacy` (`reseal_gate` працює за міткою).
- Піни для агента й розвʼязання: `ProjectComments` вид `legacy` зникає — модуль із каналом ЛІГИ; `supabase_pins`,
  `bin/inbox.py patch_project_pin`, `bin/state.py _open_pins` → через `ProjectComments`/модуль; `inbox resolve` передає
  номер ітерації (`resolved_v` пишеться, як було).
- Гейт `spaces.require_integrations()` на шляху ЛІГИ лишається.
- **Видаляються:** `COMMENT_SNIPPET`, `inject_comment_layer`, `INTERNAL_TINT` (мертвий: жоден виклик не передає `internal=True`), `supabase_pins`,
  `patch_project_pin`, гілки `'legacy'` коментарів, `SUPABASE_URL`/`SUPABASE_KEY`, `app/vendor/supabase-adapter.min.js`.
  `BUNDLES`/`BUILD_KINDS` лишаються (їх читає `reseal_gate` для старих збірок без мітки).
- `bin/import_preview.py`: маркери старого сніпета (`_SNIPPET_HEAD`/`_SNIPPET_START`) — заморожені літерали (як
  `_OLD_SNIPPET_START`), бо `COMMENT_SNIPPET` зникає, а старі превʼю в обігу треба й далі впізнавати.

### 4. Частини 4c

`_team_fetch`, `teams_rpc`, `_overview_sync` (і `bin/overview_push.py` без оточення) беруть `supabase_config()` замість
констант; нема конфігу → тихо нічого (як `DC_NO_OVERVIEW`). Решта 4c — без змін.

## Паритет — як доводимо

- Новий диференційний знімок ДО змін (як `before-4b1.json`): для ЛІГИ — канал і `projectId` у сторінці `/commented` і в
  опублікованому превʼю, рядки `list` → піни агента, тіло PATCH розвʼязання (`status`, `resolved_v`, `resolve_reason`),
  `/api/comment-config` (канал/версія/користувач), Teams-тиша (`teams_rpc` аргументи), дашборд (`overview_push` env).
  Після змін — ті самі значення з нового шляху; відмінності — лише перелічені нижче.
- Золоті знімки `tests/fixtures/comments-role/page-legacy-project.html` і `config-legacy-project.json` міняються СВІДОМО
  (структура сторінки модуля); решта чотирьох — без змін; `legacy-golden` смуги/палітри — без `UPDATE_GOLDEN`.
- Мутації: канал ЛІГИ → `channel_for`; без `shots_bucket` у `ctx` ЛІГИ; без `iteration` у розвʼязанні; конфіг із
  секретним ключем; `require_integrations` прибрано.
- Живі: `tests/live/comments.test.mjs` (сторінка ЛІГИ — тепер модуль), «Огляд» з пінами ЛІГИ, без мережі (заглушки
  клієнта модуля, як у живих тестах звичайних просторів).

## Свідомі відмінності від 0.9.0 (для ЛІГИ)

- Опубліковане превʼю й сторінка `/commented` — розмітка модуля, supabase-js з власної копії (без jsdelivr і плаваючої
  версії `@2`); вхід адаптера без збереження сесії (сесій у ЛІГИ й так не було).
- Розвʼязання фільтрує ще й за каналом і повідомляє, коли пін не знайдено (раніше — тихо нуль рядків).
- `list` — з порядком за `id` і стелею 5000 (як у будь-якому просторі); рядки проходять санітарну обробку пінів агента.
- Повтор realtime-оновлення — з дебаунсом 120 мс; `close()` закриває сокет.
- Без конфігу установки коментарі ЛІГИ недоступні (раніше працювали з константами коду).
- `inbox resolve --dry-run` друкує `[dry-run] Supabase: resolve <канал> <id> Іт.N «причина»` замість сирого PATCH.
- `state`: Supabase ЛІГИ не відповів → «проєктні: не дістати (<код>)» замість тихого `0`.

## Відомі обмеження

- PostgREST `max-rows` (типово 1000) усе ще може тихо обрізати `list` (як раніше).
- Вже опубліковані превʼю ЛІГИ несуть старий ключ усередині: змінити ключ у конфігу їх не оновить.
- `html2canvas` шар і далі довантажує з jsdelivr (поза цим етапом).
- Ключ — у `tasks.json` відкритим текстом (публічний ключ, як і раніше був у коді).

## Документи

`CHANGELOG.md [0.10.0]`, `README.md` (конфіг Supabase ЛІГИ; модуль коментарів — скріншоти), `docs/design/spaces-and-modules.md`
(Stage 4b-2), `docs/modules/comments.md` (`shots_bucket`, `iteration`), `tasks.example.json`, `package.json` 0.10.0.

## Чекліст релізу

Фінальне ревʼю гілки → повні прогони (npm test; Python 3.13 і 3.9.6; живі по одному) → дата в CHANGELOG → тег `v0.10.0`
(анотований, від neodisa) → явний push sha і тегу → памʼять.

## Поправки (план, 30.10.2026)

Уточнення реалізації — у розділі «Поправки до спеки» плану `docs/superpowers/plans/2026-10-30-legacy-comments-module.md`:
`comments_provider` не змінює форми (нова `comments_route`), `comments_client(…, ctx=None)`, номер ітерації — лише
вбудованому модулю, `build_preview(comments=True)` зникає, старий адаптер переїжджає в тестові фікстури.
