# Етап 4d-3a «Міграція ЛІГИ: механізм, напрямки, tracker/dashboard/notify» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** простір ЛІГА на першому старті 0.17 сам (з датованим бекапом, ідемпотентно, «все або нічого») дістає явні `tracks`
і явні модулі `jira-tracker`, `supabase-dashboard`, `supabase-teams` у `space.json` + секрети в `secrets.json`; поведінка для
людини — та сама. Модулі Supabase читають налаштування `compat` замість `ctx['legacy']`; мігровані записи з `shared_state`
підлягають закону ізоляції. Реліз 0.17.0.

**Architecture:** новий `app/liga_migrate.py` (чистий розрахунок `plan()` + `run()` із бекапом/записом/позначкою +
`restore()`), CLI `bin/liga_migrate.py` (`status|dry-run|run|restore`), виклик на старті `serve.py main` до відкриття порту.
Модулі `supabase-dashboard`/`supabase-teams`: налаштування `compat`. Ядро ролей `dashboard`/`tracker`/`notify`: запис модуля з
`shared_state: true` іде через `implicit.route()`.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-05-liga-migration-a-design.md`. Читати перед кожною задачею.

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
- ⛔ Міграцію НІКОЛИ не запускати проти справжнього `~/.deai` / справжнього `tasks.json` власника — лише тимчасовий `DEAI_HOME`
  і тимчасові файли; живий канвас (PID 1063) не перезапускати.
- Знеособлено: лише вигадані значення (`https://sb.example.com`, `https://jira.example.com`, Alpha / `alpha@example.com`).
  Жодних справжніх хостів, ключів, імен; імʼя користувача машини — лише з оточення, ніколи літералом.

**Конвенції коду**

- Коментарі українською, у стилі навколишнього коду; ⛔-уроки прибраного коду переносяться в нове місце, не губляться.
- Python 3.9: без `match`, без `X | Y` в анотаціях.

**Еталони й мутації**

- `tests/legacy-golden.test.mjs`, `GoldenPinTest`, знімки `before-4c1`, `before-4c3`, `before-4d1`, `before-4d2` — зелені БЕЗ `UPDATE_*`.
- Кожна нова перевірка доводиться мутацією (один рядок → потрібний тест червоніє → файл відновлено побайтно, sha256).
  Мутації Python — лише `python3 -B`, з охоронцем, по одній.

**Набори тестів:** юніти — `npm test`; живі — лише послідовно `node --test --test-concurrency=1 tests/live/<файл>`.
Номери рядків — орієнтир («≈»). Кожна зміна наявного тесту — у звіті одним рядком із причиною.

---


---

## Структура файлів

| Файл | Що змінюється |
|---|---|
| `tests/make_before_4d3a.py`, `tests/fixtures/liga-migration/before-4d3a.json` (нові) | знімок 0.16.0 (Task 1) |
| `app/modules/supabase-dashboard/{module.json,server.py}`, `app/modules/supabase-teams/{module.json,server.py}`, `app/dashboard.py`, `app/notify.py` | `compat` (Task 2) |
| `app/serve.py`, `app/deai_modules.py` | `shared_state` → `implicit.route()` для `dashboard`/`tracker`/`notify` і синку (Task 3); старт міграції (Task 5) |
| `app/liga_migrate.py` (новий) | `plan()`, `run()`, `restore()`, `status()` (Task 4–5) |
| `bin/liga_migrate.py` (новий) | CLI (Task 5) |
| `app/connections-model.js` | лише якщо знімок Task 1/6 покаже дубль картки (Task 6) |
| `tests/test_liga_migrate.py` (новий), `tests/live/liga-migrate.test.mjs` (новий) | тести |
| `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `docs/modules/authoring.md`, `package.json` | Task 7 |

---

### Task 1: знімок 0.16.0 (до змін коду)

**Files:** Create `tests/make_before_4d3a.py` (зразок — `tests/make_before_4d2.py`: охорона fail-closed проти `bf9bb5b` для
`app/`/`bin/`, рецепт замороженої копії, розтяжка сокетів, детермінізм), `tests/fixtures/liga-migration/before-4d3a.json`,
`tests/test_liga_migrate.py` (клас `Before4d3aShape`).

- [ ] **Step 1:** простір ЛІГА в тимчасовому `DEAI_HOME` (реєстр із `legacy: true`, `integrations: true`, тека простору —
  тимчасова), старий `tasks.json` з вигаданим конфігом: `supabase_url`/`supabase_key`, `jira_base`, `design_work_root`,
  `design_work_roots` (united + один нестандартний ключ), `profile_repos` (united + seo); облікові Jira — з вигаданого оточення
  (поза ізоляцією) і окремо — з файлів `pipeline-feedback` у тимчасовому HOME. Секції:
  - `caps`: `deai_modules.capabilities(<ЛІГА>)`;
  - `tracks`: `serve.space_tracks(<ЛІГА>)` (id, label, root відносно HOME, repo, ds), `default_track`, `track_root` для кожного
    id і для невідомого рядка;
  - `ctx`: для `dashboard`, `tracker`, `notify` — ctx, який отримав би модуль (підміна `deai_modules.call`, що записує
    `(module.id, fn, ctx)`; секрети — замінити на `"<secret:len>"`) поза ізоляцією;
  - `check`: вердикти `check` трьох модулів на цих ctx (мережа — локальний фейк-сервер на loopback, як у тестах модулів, або
    підміна `_request` модуля; без справжньої мережі);
  - `api`: справжній сервер у процесі: `GET /api/spaces` (ЛІГА: `capabilities`, ключі), `GET /api/task` для задачі ЛІГИ
    (`track`, мітки, `space`);
  - `connections`: `app/connections-model.js` на `/api/spaces` ЛІГИ (через `node -e`, як у JS-тестах моделі) — які картки ролей
    отримує екран «Підключення».
- [ ] **Step 2:** двічі байт-у-байт, коміт (JSON + генератор + `Before4d3aShape`). Жодних змін у `app/`/`bin/`.

---

### Поправки контролера після Task 1 (06.11.2026) — мають перевагу над текстом Task 2–7 і спеки

- **Невідомі значення напрямку.** Адаптер ЛІГИ веде БУДЬ-ЯКИЙ рядок/`None`/число, що не є id із власним коренем, у
  СПІЛЬНИЙ корінь (`design_work_root`); явні `tracks` ведуть невідоме значення в корінь ДЕФОЛТНОГО напрямку (`united` — свій
  корінь). Для перелічених id паритет повний, для невідомих — ні. Тому в Task 4 (`plan()`): напрямки НЕ мігрують
  (`tracks: false`, причина `tracks-unknown-values`, ролі мігрують далі), якщо (а) у старому `tasks.json` є задача, чий
  `track`/`profile` не є рядком із переліку мігрованих id (включно з `None`, `''`, іншим регістром), АБО (б) корінь дефолтного
  `united` після міграції ≠ спільному кореню адаптера (`legacy_root(cfg, None)`) — бо тоді нова задача з невідомим значенням
  лягла б в інше місце. Інакше — мігрують. Тест на кожну з умов + мутація.
- **Джерела облікових Jira** беруться НЕЗАЛЕЖНО (email і token кожен: оточення → файл `pipeline-feedback`), пара Supabase — ЦІЛОЮ
  з одного джерела (корінь → оточення). `plan()` бере їх через ті самі функції `install_config` поза ізоляцією (спільний
  помічник), а не копією логіки.
- **`check` ЛІГИ на «Підключеннях» сьогодні** відповідає `bad-settings` для всіх трьох модулів (знімок `check.core_check`): після
  міграції це стає справжньою перевіркою — задокументувати в CHANGELOG як покращення.
- **Дубля картки нема** (знімок `connections.hypothetical_explicit`): `connections-model.js` не правимо, якщо Task 6 не покаже
  інакше.

---

### Task 2: налаштування `compat` у `supabase-dashboard` і `supabase-teams`

**Files:** Modify `app/modules/supabase-dashboard/module.json`, `.../server.py`, `app/modules/supabase-teams/module.json`,
`.../server.py`, `app/dashboard.py` (`legacy_ctx`), `app/notify.py` (`legacy_ctx`); Test `tests/test_liga_migrate.py`
(`CompatSetting`), наявні тести модулів.

- [ ] **Step 1 (тести, червоні):** для обох модулів — `compat: "comment-layer"` у `settings` дозволяє публікабельний ключ у
  `check` (і для `supabase-teams` пропускає `teams_notify_health`, бере ту саму `_problem`-гілку, що була для `legacy`);
  `compat: ""`/нема + `ctx['legacy'] = True` — поведінка як у звичайного простору (публікабельний ключ → `public-key`);
  невідоме значення `compat` — `bad-settings` (валідація `select` наявним механізмом); `legacy_ctx` обох кладе
  `settings.compat == "comment-layer"`; вердикти `check` на ctx неявного шляху — побайтно ті самі, що секція `check` знімка.
- [ ] **Step 2:** `module.json`: поле `{"key": "compat", "type": "select", "options": ["", "comment-layer"], "required": false,
  "label": …}` (формат `select` — як у наявних модулях, звірити з `deai_modules` валідацією); `server.py` обох — читати
  `settings.compat == "comment-layer"` замість `ctx.get('legacy')` (усі місця, `grep legacy`); докстрінги — ⛔ причина.
  `legacy_ctx` кладе `compat`; прапорець `legacy` у ctx лишається (вбудовані його не читають — тест-охоронець: у
  `app/modules/*/server.py` нема `ctx.get('legacy')`/`ctx['legacy']`).
- [ ] **Step 3:** мутації (повернути читання `ctx['legacy']` в одному місці → охоронець червоний; прибрати `compat` у
  `legacy_ctx` → тест знімка `check` червоний); тести, `npm test`, коміт.

---

### Task 3: `shared_state` — закон ізоляції для явних записів

**Files:** Modify `app/deai_modules.py` (доступ до прапорця запису), `app/serve.py` (`_team_fetch`, `_tracker_fetch`,
`notify_call`, `_overview_sync`); Test `tests/test_liga_migrate.py` (`SharedStateIsolation`).

- [ ] **Step 1 (тести, червоні):** простір із `integrations: true` і явним записом ролі (`dashboard`/`tracker`/`notify`) з
  `shared_state: true`: під `DC_TEAM_FAKE`/`DC_TRACKER_FAKE`/`DC_TEAMS_FAKE` — результат шва (як для `Implicit`); під
  `DC_TASKS_FILE`/`DC_NO_OVERVIEW` без шва — ТА САМА відповідь ізоляції, що для `Implicit` (`[], TEAM_ISOLATED` / `None` /
  `OSError`), модуль не кличеться; поза ізоляцією — модуль із `module_ctx`; той самий запис БЕЗ `shared_state` — як сьогодні
  (жодного шва, модуль кличеться навіть під ізоляцією); `_overview_sync` для `shared_state` під `DC_TASKS_FILE` не запускає
  дитину. `shared_state` не-`bool` → ігнорується (як `False`), не виняток.
- [ ] **Step 2:** `deai_modules.shared_state(space, module_id) -> bool` (читає нормалізований запис `space_modules`; збій →
  `False`); у трьох ролях і синку: `isinstance(prov, Implicit) or (isinstance(prov, Module) and deai_modules.shared_state(space,
  prov.id))` → гілка `implicit.route(implicit.for_role(role))`; для `'live'` — модуль `prov` з `module_ctx` (НЕ легасі-збирач).
  ⛔ Порядок `tracker` (`if not keys` після шва/ізоляції) — так само.
- [ ] **Step 3:** мутації (прибрати `shared_state`-умову в одній ролі → тест червоний); тести, `npm test`, живі `dashboard-role`,
  `tracker-role`, `notify-role` по одному; коміт.

---

### Task 4: `app/liga_migrate.py` — розрахунок і перевірки (без запису)

**Files:** Create `app/liga_migrate.py`; Test `tests/test_liga_migrate.py` (`PlanTest`).

- [ ] **Step 1 (тести, червоні):** `plan(home=None)` → `{"status": "ready"|"skip-*"|"abort-*", "roles": {...}, "tracks": ...,
  "space_id", "space_json": <новий вміст>, "secrets": {module: {key: "<secret>"}}}` (у звіті для людини — без значень секретів:
  окрема `report(plan)`). Сценарії: шар вимкнено → `skip-layer-off`; нема запису ЛІГИ → `skip-no-liga`; позначка є →
  `skip-done`; `held` → `skip-held`; тека не існує → `skip-no-path`; тека в робочому дереві git (`.git` у ній чи в предку) →
  `skip-path-in-git`; `space.json` нечитабельний → `skip-space-json-unreadable`; повний конфіг → три ролі + напрямки за
  спекою §3; нема пари Supabase → лише `tracker`; нема облікових Jira → без `tracker`; модуль уже є в `space.json` → роль не
  мігрує; непорожні `tracks` уже є → `tracks: false`; паритет напрямків (порівняння з адаптером для кожного id, включно з
  нестандартним ключем `design_work_roots`) — підмінений корінь, який `normalize` відкидає (тека всередині `Library`) →
  `abort-tracks-parity`; `_provider_for` на розрахованому `space.json` для кожної мігрованої ролі дає саме цей модуль
  (інакше `abort-provider`). Джерела облікових Jira — у тому самому порядку, що `install_config.jira_config()` поза ізоляцією
  (рефакторинг: спільний помічник, а не копія коду).
- [ ] **Step 2:** реалізація без запису на диск; модуль не імпортує `serve` (лише `spaces`, `deai_modules`, `tracks`,
  `install_config`, `implicit`). Тексти причин — коди + українські пояснення без значень.
- [ ] **Step 3:** мутації (вимкнути перевірку git → тест `skip-path-in-git` червоний; вимкнути паритет напрямків → тест
  `abort-tracks-parity` червоний); тести, коміт.

---

### Task 5: запис, бекап, позначка, відкат, CLI, старт сервера

**Files:** Modify `app/liga_migrate.py`, `app/serve.py` (`main`); Create `bin/liga_migrate.py`; Test `tests/test_liga_migrate.py`
(`RunTest`, `RestoreTest`, `StartupTest`).

- [ ] **Step 1 (тести, червоні):** `run()` у тимчасовому `DEAI_HOME`: бекап `<home>/backups/<stamp>-liga-4d3a/` (0700) з
  копіями старого `tasks.json`, `space.json` (якщо був), `secrets.json` (0600), `spaces.json` і `manifest.json` (джерела, sha256);
  потім `secrets.json` (через `deai_modules.write_secrets`), потім ОДИН атомарний запис `space.json` (злиття: `name`, `color`,
  чужі ключі — як були) з `modules`, `tracks`/`default_track`, `migrations.liga-4d3a {at, roles, tracks, backup}`; `last.json` у
  `<home>/migrations/`. Другий `run()` — `skip-done`, нічого не пише. Збій бекапу (тека не пишеться) → `abort-backup`, нічого
  не записано. Збій після секретів до `space.json` (підміна запису) → наступний `run()` доводить до кінця. `restore(stamp)`
  повертає `space.json`/`secrets.json` побайтно (sha256 з маніфесту); `restore(stamp, hold=True)` додає `held`. Жодного
  значення секрету в `last.json`, stderr, звіті CLI (перевірка: шукати вигадані значення в усіх виходах). Старт сервера:
  `serve.main` кличе `liga_migrate.startup()` до `make_server`; у ізольованому прогоні — ні, крім `DC_MIGRATE_LIGA=1` з
  тимчасовим `DEAI_HOME` (справжній `~/.deai` — відмова навіть зі швом); будь-який виняток міграції не валить старт (лише
  stderr і `last.json`).
- [ ] **Step 2:** реалізація; CLI `bin/liga_migrate.py status|dry-run|run|restore <stamp> [--hold]` (exit 0 / 1, людський
  текст українською, без значень секретів). Порядок замків: жодних `load_registry`/`catalog`/`provider` під `WRITE_LOCK`.
- [ ] **Step 3:** мутації (поміняти місцями секрети й `space.json` у `run()` → тест «збій посередині» червоний або
  позначка/ідемпотентність червоні; прибрати перевірку «справжній ~/.deai» у шві → тест червоний); тести, `npm test`, коміт.

---

### Task 6: паритет після міграції, «Підключення», живий тест

**Files:** Test `tests/test_liga_migrate.py` (`AfterMigrationParity`); Create `tests/live/liga-migrate.test.mjs`; Modify
`app/connections-model.js` (лише якщо потрібно).

- [ ] **Step 1:** сценарії знімка Task 1 на МІГРОВАНОМУ просторі: `tracks` і `track_root` — ті самі; `ctx` трьох ролей — ті
  самі значення налаштувань і секретів (форма — з `module_ctx`; різниця лише в задокументованому: `compat` замість `legacy`,
  `space.path`/`space.id` простору); `check` — ті самі вердикти; `caps` — id модулів для трьох ролей, `'legacy'` для
  `publish`/`comments`/`vcs`; `connections` — для кожної ролі ОДНА картка (явний модуль не дублюється «вбудованою»). Якщо
  дубль є — правка `connections-model.js` (≈317: «вбудована» лише для ролі, яку не веде явний модуль) + JS-тест.
- [ ] **Step 2:** живий тест (PORT_BASE 23100, тимчасовий `DEAI_HOME`, `DC_MIGRATE_LIGA=1`, фейк-сервер Supabase/Jira на
  loopback): старт → бекап і позначка є → «Підключення» ЛІГИ показують три модулі увімкненими → «Задачі» показують статуси
  Jira й вкладку «Команда» → другий старт нічого не пише (mtime `space.json` не змінився).
- [ ] **Step 3:** повні прогони, живі по одному (`liga-migrate`, `tasks-home`, `dashboard-role`, `tracker-role`,
  `notify-role`, `connections`, `tracks`); коміт.

---

### Task 7: документи й версія 0.17.0

- [ ] CHANGELOG `[0.17.0] — unreleased` (міграція, `compat`, `shared_state`, CLI; «Deliberate differences» і «Known limits» —
  зі спеки); README (дорожня карта 4d-3a/b/c → 4d-4 = 0.20, «Known limits»); `docs/design/spaces-and-modules.md` «Stage 4d-3a»;
  `docs/modules/authoring.md` (`compat`, `shared_state`, що вбудовані модулі не читають `ctx['legacy']`); `package.json`
  0.17.0; спека — «Implementation notes». Коміт.

---

## Після всіх задач (контролер)

Фінальне ревʼю (Sonnet) → виправлення → повторне ревʼю → прогони на знімку → дата → тег `v0.17.0` → push → памʼять.
