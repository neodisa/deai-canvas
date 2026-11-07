# Етап 4d-4b «Оригіналів ЛІГИ нема, запасного постачальника нема» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** на першому старті 0.21 простір ЛІГА п'ятим незалежним кроком `liga-4d4b` (свій датований бекап, позначка, відкат; усе або нічого) копіює в явні записи останні три оригінали (`gitlab_ssh_key`/`gitlab_host_ip` → налаштування `ssh_key`/`host_ip` запису `git-sync`; `preview_password` → секрет `password` запису `vercel-publish`) і **видаляє з кореня `tasks.json` ЛІГИ** кожен із восьми оригіналів, чия рівність із записом доведена перечитаним диском. Після кроку рантайм **не читає оригіналів** (корінь, оточення, `~/.claude/pipeline-feedback/`), запасного постачальника `Implicit` **нема**: роль ЛІГИ без явного ввімкненого запису вимкнена, і старт та `status` називають кожну вимкнену роль, причину й команду виправлення.

**Architecture:** `Step.originals` (нове поле) відрізняє крок Е від D; чистий розрахунок `_decide_originals` (рівність → видалення, порожньо й копіюємо → копія, інакше нотатка) і запис «precheck → бекап → секрети → налаштування `space.json` → перевірка прочитанням → видалення з кореня із **свіжим повторним рішенням під локом** → позначка останньою». Відкат Е **домерджує** відсутні ключі в живий `tasks.json` (файл цілком не перезаписує). Закон ізоляції, фейкові шви й `route` переїжджають із `app/implicit.py` у чистий `app/isolation.py` (імпортує лише `os`/`pwd`); `app/implicit.py` видаляється. `_provider_for` — одна гілка для всіх просторів, неявний простір → `None`. Читачі оригіналів (`install_config`, `serve`, `bin/registry.py`, `bin/overview_push.py`, `ops/reseal_gate.py`) видалені; ключ git і пароль превʼю йдуть із записів (`deai_modules.publish_password`, налаштування `git-sync`). Охоронці `NoOriginalsRead`/`NoImplicit` (AST) не дають їм повернутися. Тести переходять на явну фікстуру `tests/liga_fixture.py` (прямі записи АБО справжня міграція зі старого кореня).

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-07-liga-originals-gone-design.md`. Читати перед кожною задачею; ПОПРАВКИ НИЖЧЕ мають перевагу над текстом спеки й задач. Попередній етап: `docs/superpowers/plans/2026-11-07-liga-tracks-final.md` (шаблон процесу: знімок → крок → LIFO → паритет → живі → документи).

**Про прототип.** Усі hunk-и й тести нижче — реальний результат прототипу, прогнаного поверх `git archive v0.20.0` (код = коміт `0d52a74`, поза репо; HEAD `869c552` відрізняється від тегу лише документами). Прототип: `tests/test_liga_migrate_e.py` — 58 тестів зелені; `test_isolation` 11, `test_liga_fixture` 3, `test_originals_gone` 29, `test_no_originals` 5, `test_before_4d4b` 7, `AfterMigrationParity4d4b` 14 — зелені; `app`-тести (170) зелені; JS `connections-model` 36 зелених. Виконавець застосовує hunk-и задача за задачею і доводить тестами, а не копіює наосліп: прототип НЕ довів повний набір до зеленого після видалення: з 4449 тестів базового прогону (зелений, `OK (skipped=2)`) запустилося 2109, у них 356 червоних (`failures=81, errors=275`), а ще 17 модулів не імпортуються (`import implicit`) — це Додаток З, його лікують Task 13–14.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  Коміт — лише з переліком шляхів; новий файл спершу `git add -- <шлях>`. **Ніколи** `git add -A` / `git add .`; не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md`; ніколи `--amend`.
- ⛔ Лише точкові правки наявних файлів інструментом `Edit`; жодних скриптів `sed`/Python-заміни, жодного переписування файла цілком (нові файли — `Write`). Унифіковані diff-и в Додатку Ж — ЕТАЛОН результату: застосовувати hunk за hunk через `Edit`, а не `patch`. Після КОЖНОЇ задачі: `git diff HEAD | grep '^-[^-]'` показує лише заплановані видалення.
- ⛔ У ЖОДЕН комітований файл (план, спека, докстрінги, тести, фікстури, CHANGELOG, памʼять) не пишемо ні шляху scratchpad, ні шляху охоронця `$G`, ні жодного шляху з імʼям користувача машини чи префіксом домашньої/тимчасової теки; імʼя користувача — лише з оточення (`os.path.expanduser('~')`). Перед кожним комітом: `git diff --cached | grep -nE "$(basename "$HOME")|<префікс домашніх тек macOS>|<префікс тимчасових тек macOS>"` → нуль (префікси — літерали, які виконавець складає сам; у файлах плану їх не друкуємо).

**Прогони й середовище**

- `G=<scratchpad>/bin/guard.py` — справжній шлях контролер дає в кожному брифі; кожна важка команда — `python3 "$G" <секунд> <МБ> <команда…>`. Живі тести — по одному файлу, ПОСЛІДОВНО: `node --test --test-concurrency=1 tests/live/<файл>.test.mjs` (правило «задачі з test:live — послідовно»: сусід, що править модуль під час прогону, дає до 8 фальшивих падінь).
- Python-тести — під `python3` і під `/usr/bin/python3` (3.9): без `match`, без `X | Y` в анотаціях.
- ⛔ **Кожен прогін Python-тестів — з тимчасовим `HOME`** (`HOME=$(mktemp -d) python3 -B -m unittest …`). Після Task 11 `registry._ssh_key()`/`reseal_gate` читають простір із реєстру, тож тест без підміни `HOME` торкнувся б справжнього `~/.deai`. Після кожного прогону: `ls ~/deai-work ~/.deai` не змінились. macOS не має `timeout` — довгі прогони лише через `$G`.
- ⛔ **Живі тести з тимчасовим `HOME`** (інцидент 4d-4a: два прогони впали не через код): Playwright шукає браузери в кеші справжнього дому (треба `PLAYWRIGHT_BROWSERS_PATH`), а `git commit` у фікстурах без `~/.gitconfig` падає «Please tell me who you are» (треба `GIT_CONFIG_GLOBAL`). Виправлено ОДИН РАЗ у Task 2 (`tests/live/_env.mjs`, імпорт у фікстурах); далі `HOME=$(mktemp -d) node --test …` працює без ручних змінних.
- ⛔ Міграцію НІКОЛИ не запускати проти справжнього `~/.deai`; `DC_MIGRATE_LIGA=1` — лише з тимчасовим `DEAI_HOME`, що не дорівнює `<HOME>/.deai`; не виставляти `DEAI_HOME` у шелі. Нових тестових стендів без `mock.patch.dict(os.environ, {'HOME': …, 'DEAI_HOME': …})` у `setUp` (або `LigaFixture(self).env()`) нема (`tests/test_serve.py::TestsCannotWriteLiveConfig` вимагає присвоєння `DEAI_HOME` у файлі, що пише простори, і `spaces_guard` у `setUpModule`/`tearDownModule`). Жодної мережі (`NoNet`/`SocketTripwire`), порти 8765/4317 не чіпати, процеси — лише за PID (ніяких `pkill`/`killall` за шаблоном). Не чіпати `~/deai-published`, справжній `tasks.json`, `~/.gitconfig`, `~/.claude/pipeline-feedback/`.
- Знеособлено: лише вигадані значення (`https://sb.example.com`, `pv-12345678`, `team_x`, `alpha@example.com`, `203.0.113.7`). ПІБ/ЄДРПОУ/ІПН/реквізити у фікстурах — нуль.
- ⛔ Живі тести ізольовані (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) → доводять ізольований шлях, а НЕ шлях власника; кожне твердження про шлях власника має НЕізольований юніт-тест із справжніми ефектами (стенд `AfterMigrationParity4d4b`, Task 15).

**Конвенції:** коментарі коду українською, ⛔-уроки переносяться в нове місце; TDD (тест червоний → код → зелений); кожна нова перевірка доводиться мутацією: один рядок → потрібний тест червоніє → файл відновлено, `sha256` до/після збігається; мутації — лише `python3 -B` (застарілий `.pyc` дає ложне «вижила»), по одній; **охоронець, який не може впасти, — фікція** (кожен охоронець має тест «зіпсований код червоніє»). Еталони (`tests/legacy-golden.test.mjs`, `GoldenPinTest`, знімки `before-4c1…4d4b`, `AfterMigrationParity`, `…4d3b`, `…4d3c`, `…4d4a`, `…4d4b`) — зелені БЕЗ `UPDATE_*`. Кожна зміна наявного тесту — у звіті одним рядком із причиною; НІЧОГО не видаляємо мовчки (таблиці відповідності — Додаток З). Номери рядків — за `v0.20.0`.

**Типові пастки цього етапу (⛔):** (1) **єдина копія облікових**: після кроку Е вони лише в `secrets.json` і `backups/` дому Deai — не чистити `backups/`; (2) `restore` Е НЕ перезаписує `tasks.json` цілком — лише домерджує відсутні ключі (людина могла додати задачі); (3) `ALL_STEPS` стає п'ятьма в Task 4, а `STEPS` (те, що біжить на старті) — лише в Task 7, коли вже є запис, відкат і вивід: два тести 4d-4a про «чотири кроки» змінюються в Task 4 і Task 7 (Поправка 6); (4) `provider(<роль>)` без простору мовчки дає `None` — аудит `ProviderCallersPinTheSpace` (Task 9); (5) оточення й `pipeline-feedback` крок НЕ чіпає — вони спільні з окремим інструментом ЛІГИ; (6) `design_work_root(s)`, `profile_repos`, `registry`, `current`, `tasks` у корені лишаються (Д2 спеки); (7) `real_home` для закону ізоляції — за `pwd`, а НЕ за `$HOME` (`liga_migrate._real_home` лишається ширшою — це інше правило); (8) мутації й охоронці не мають залишати `.pyc`: `python3 -B`.

---
## Поправки до спеки (виявлено при звірці з кодом; мають перевагу над текстом задач і спеки)

Звірено з `v0.20.0`. Кожна — з доказом `файл:рядок` і тим, що робити.

1. **`skipped` не лежить у позначці кроку.** Спека §4.1 п.2 каже «позначка кроку-власника каже `skipped[role]`». У коді позначку збирає `_commit_space` (`app/liga_migrate.py:826`: `dict(planned['migrations'][step.mark], at=…, backup=…)` — лише `roles`, `tracks`, `records`, `notes`), а `skipped` є лише у звіті кроку: `_info` (`:648`, `'skipped': {роль: причина}`) → `last.json` (`:1243`, `:1340`). Тому `roles_state` бере код `no-jira`/`no-supabase`/`bad-url`/`publisher-present`/`module-present` із `last.json → steps[<позначка власника>].skipped`; коли звіту нема (інший процес переписав `last.json`, ручне видалення) — код `not-migrated` («крок застосовано, а запису нема»). Нових полів у позначці не вводимо (це змінило б `restore`/LIFO-пін 4d-3).
2. **`held` раннього кроку тримає пізніші — спека це не враховує у `roles_state`.** `plan` кроку B/C/D/E при `held` кроку A дає `skip-held` (`app/liga_migrate.py`, ворота `_plan`), але власної позначки `held` у B/C нема. Наївне «позначка кроку-власника» дає для `publish`/`comments`/`vcs` код `no-record` і команду `run` — оманливу (`run` знову скаже `skip-held`). Прототип: `_held_mark(mig, owner)` шукає першу утриману позначку серед кроків до власника включно; команда — `unhold <ця позначка>` (тест `test_early_step_held_names_the_early_mark_for_later_owners`, параметр знімка `unmigrated.startup_text`).
3. **`disableConsequences` у JS бреше після 0.21 — спека (Р9) про це мовчить.** `app/connections-model.js:320`: `if (space.integrations === true && LEGACY_ROLES.has(role)) out.push({ role, kind: "legacy" })` — екран «Підключення» каже «після вимкнення роль повернеться до вбудованого шляху». Запасного шляху більше нема, тож текст був би неправдою. Правка 4d-4b (Task 11): гілку й `LEGACY_ROLES` видалити, ЛІГА йде тими ж `kind: "none"`, що й інші; чотири закріплені тести `tests/connections-model.test.mjs` з назвою «наслідки вимкнення …» (publish/dashboard/tracker; notify; git-sync; мігрований vercel-publish) оновлюються. Решту JS-запасних гілок (`providerLine` `'legacy'`, `isLegacyVcs`, `isLegacyPublish`, `app.js:2955`) лишаємо до 4d-4c: сервер значення вже не шле.
4. **`spaces.LEGACY_MARKERS` і `OVERVIEW_LOG` — два свідомі винятки охоронця.** Спека вимагає, щоб `app/**/*.py` не мали рядків `gitlab_host_ip`/`gitlab_ssh_key`/`pipeline-feedback`. Але `app/spaces.py:44` `LEGACY_MARKERS = ('registry', 'gitlab_host_ip', 'gitlab_ssh_key')` — ознака «файл ЛІГИ» для відновлення реєстру (спека сама вимагає охоронця маркера, §1.1), а `app/serve.py:5494` `OVERVIEW_LOG = '~/.claude/pipeline-feedback/overview-sync.log'` — шлях ЖУРНАЛУ синку, не облікових. Охоронець має точний `ALLOWED = {(файл, значення)}` (не «будь-що у файлі»); обидва — до 4d-4c.
5. **`serve.preview_password` читав корінь КОЖНОГО простору, не лише ЛІГИ.** `preview_password(cfg, task)` (`app/serve.py:4131`–`4144`) отримував `load_tasks()` (`:5995`, `:8232`, `ops/reseal_gate.py:41`) — це `tasks.json` АКТИВНОГО простору, а не «простору ЛІГА». Ключ кореня `preview_password` ніде не документований (`README.md`, `tasks.example.json` його не мають), але у звичайному просторі він діяв. Після 0.21 корінь не читається в жодному просторі: пароль — задача > секрет запису `vercel-publish` (лише ЛІГА з `compat == design-canvas`) > `1100`. У CHANGELOG — окремий рядок «Known limits» («ключ кореня `preview_password` у файлі задач ЗВИЧАЙНОГО простору більше не діє: пароль — поле задачі»).
6. **П'ятий крок і вивід «Ролі ЛІГИ» ламають дев'ять наявних тестів, яких нема в Додатку Б спеки** (виміряно: прототипний `liga_migrate.py` + база `v0.20.0`, шість тестів у стані «після Task 7» + три у стані «після Task 11»). *Task 4* (склад `ALL_STEPS`): `tests/test_liga_migrate_d.py:138` `StepDConstants.test_steps_list_and_shape`. *Task 7* (старт/`status` друкують вимкнені ролі, тож «тихі» тести перестають бути тихими): `test_liga_migrate_d.py:481` `FourStepsStartup.test_order_backups_and_one_restore_hint` (п'ять бекапів, ОДИН рядок відкату), `test_liga_migrate_b.py` `CliStepsTest.test_single_step_output_is_byte_identical_to_4d3a` (CLI `status` тепер додає секцію «Ролі ЛІГИ»), `StepBRunTest.test_second_start_is_skip_done_and_writes_nothing` і `TwoStepsStartupTest.test_second_start_is_silent_and_writes_nothing` (другий старт «мовчав»; тепер друкує РІВНО рядки вимкнених ролей і досі нічого не пише), `test_liga_migrate_c.py` `PublisherPresent.test_publisher_present_is_quiet_on_startup_but_visible_in_dry_run` (те саме). Рецепт для «тихих»: очікування — точний список рядків `ролі ЛІГИ вимкнено: …` (вони й є новою поведінкою за спекою §4.1), «нічого не пише» — перевіряється деревом файлів, а не порожнім stderr. *Task 11* (читачі оригіналів переїхали в `liga_migrate._supabase_from`/`_jira_from`; тести підміняли `install_config.supabase_from`): `test_liga_migrate_b.py` `StepBPlanTest.test_bad_url_userinfo_is_not_migrated`, `StepBPlanTest.test_url_and_key_come_from_supabase_from`, `test_liga_migrate.py` `RunTest.test_userinfo_urls_are_not_migrated` — ціль підміни стає `liga_migrate._supabase_from`. Стенди 4d-3/4d-4a, що мають піни `STEPS`/`ALL_STEPS[:n]`, лишаються зеленими.
7. **Маніфест `vercel-publish` 1.2.0 → 1.3.0 ламає закріплені тести** (спека називає лише «версія 1.2.0 → 1.3.0»): `tests/test_liga_migrate_c.py:643`–`654` (`PublishCompatSetting`, версія), `:1387`–`1401` (`_COMPAT_LABEL`, `_COMPAT_OPT`, `_expect_card`: `version` «1.1.0 → 1.3.0»), `tests/test_vercel_publish.py:551`. Підпис `compat` ЛІГИ з прототипу: «пароль превʼю — спершу пароль задачі, далі секрет цього модуля» (старий текст стверджував, що `password` у режимі ЛІГА не читається — після 0.21 це неправда).
8. **Тексти «не налаштовано» — не в `deai_modules.py:176/180`** (там лише коментарі до таблиці `STATUS`, рядки 161–168). Користувач бачить: `serve.COMMENTS_UNCONFIGURED` (`app/serve.py:3113`), `tracker.UNCONFIGURED` (`app/tracker.py:26`, нині «додайте jira_base у tasks.json і облікові JIRA_EMAIL/JIRA_TOKEN»), `dashboard.UNCONFIGURED` (`:226`) і `notify.UNCONFIGURED` (`:21`) — вони й міняються (на «…на екрані «Підключення»»); коментарі в `deai_modules.py` оновлюються для чесності. Закріплені тексти: `test_tracker.py`, `test_dashboard.py`, `test_notify.py`, `test_tasks_overview.py`, `test_inbox.py`, `test_legacy_comments.py`, `tests/tasks-home.test.mjs`, живий `comments.test.mjs`.
9. **`EXPECT_DIFF` паритету ширший за перелік спеки (§Тестування).** Замір на прототипі (Додаток Д): окрім `capabilities.error_path`, `registry_ssh`, `root_keys`, `modules.git-sync.settings` і `modules.vercel-publish.secrets`, змінюються (а) `provider.implicit_space.*` (`Implicit/legacy` → `NoneType/None` на ВСІХ п'яти стендах, включно з `plain`), (б) цілі `vcs_target`: ключ і IP **зникають із цілі** (модуль бере своє з налаштувань), а ефективні значення (`effective.*`) НЕ змінюються, (в) `api.modules.*` — три видимі поля (`host_ip`, `ssh_key`, «Пароль превʼю: задано»), (г) стенд `partial`: ролі без запису (`tracker`, `notify`) → `None`, `teams_mute` 200 → 409 `notify-off`, (д) `unmigrated`: усі шість ролей `None`, пароль превʼю `pw-alpha` → `1100`, `comment-config` 200 → 409 `integrations-off`, ізольовані `comments_ctx` — `ModuleError`/`module-error`. Стенд `differs`: пароль превʼю БЕЗ відмінності (секрет перезаписано кореневим, Д4), `registry_ssh` — `/other/key` (ключ запису). Таблиці — літерали Додатка Д.
10. **`differs`/`partial` у знімку готуються ПІСЛЯ міграції A–D, а крок Е вирішує саме ці розбіжності.** Генератор 0.20 міняє запис після `run_all`; для «після» колектор запускає кроки A–D, міняє запис, і лише тоді Е (інакше `differs:*`/`overwrote:password` ніколи б не спрацювали). Колектор — `tests/after_4d4b_collect.py` (diff до генератора — Додаток Д).
11. **Аудит `provider(<роль>)` без простору (Р4) виконано: сім викликів, усі в потоці запиту.** `team_resolve`, `tracker_resolve`, `notify_resolve`, `vcs_provider`, `_publish`, `_overview_sync`, `_preview_password` у `app/serve.py` (рядки 640, 1971, 2052, 2631, 7197, 7683, 8215 у v0.20.0) — усі в обробниках запиту (простір фіксує `task_anywhere`/`set_request_space`) або в потоках, обгорнутих `_in_space` (`app/serve.py:5159`; кожен `threading.Thread`/`Timer` у файлі, інваріант `tests/test_spaces_serve.py`). CLI (`bin/inbox.py:358`–`362`, `bin/state.py:293`–`298`, `bin/overview_push.py`) передає `space` явно. Власні потоки `deai_modules` (`:812`, `:1608`) викликів провайдера не мають. Тест `ProviderCallersPinTheSpace` (Додаток В) закріплює перелік.
12. **Закон ізоляції для коментарів у немігрованій ЛІЗІ дає `ModuleError('module-error')`, а не `comments-unconfigured`.** Спека (§7): «у справжньому домі — `comments-unconfigured`». Це так, коли запис `supabase-comments` ЄДИНИЙ і є (тест `test_real_home_is_refused`). Коли ж запису нема взагалі (немігрована ЛІГА), `comments_provider` дає `None`, а `comments_route` на `None` кидає `ModuleError('module-error', 'comments: no provider')` (перший рядок функції) — це бачить колектор знімка (`unmigrated.isolation.comments_ctx`: `raised: ModuleError`, `code: module-error`). Обидва коди — літерали паритету.
13. **`PROFILE_OK`/`NoTracksAdapter` лишаються як є**; `NoOriginalsRead` — новий окремий охоронець (не розширення), бо цілі різні (спека каже «за зразком» — так і зроблено). Прототип охоронця дозволяє `preview_password` лише як `.get`/`.pop`/`[…]` на змінній `task`/`t` (і `(task or {})`) і як ключ літерала-словника (форма ВІДПОВІДІ API: `app/serve.py:5950`, `:7148`).
14. **Крок Е без нічого й без нотаток — `skip-nothing`, але прототип показує ще один випадок:** на стенді `regular` після D крок `liga-4d4a` дає `skip-nothing` (у тестовому корені нема записів задач) — тож «п'ять кроків done» у `LigaFixture.migrate()` — це `['done', 'done', 'done', 'skip-nothing', 'done']`.
15. **Живі й юніт-тести з тимчасовим `HOME` падали не через код (урок 4d-4a), а через середовище** — окремий крок Task 2, а не «примітка до живих».

---

## Структура файлів

**Нові:** `app/isolation.py`; `tests/make_before_4d4b.py` + `tests/fixtures/liga-migration/before-4d4b.json` + `tests/test_before_4d4b.py`; `tests/test_liga_migrate_e.py`; `tests/test_isolation.py`; `tests/liga_fixture.py` + `tests/test_liga_fixture.py`; `tests/test_originals_gone.py`; `tests/test_no_originals.py`; `tests/test_liga_parity_4d4b.py` + `tests/after_4d4b_collect.py`; `tests/live/_env.mjs` + `tests/live-env.test.mjs`.
**Видаляються:** `app/implicit.py`; тести-мертвяки `tests/test_implicit.py` (переноситься, див. Додаток З).
**Змінюються (код):** `app/liga_migrate.py`, `app/deai_modules.py`, `app/serve.py`, `app/install_config.py`, `app/dashboard.py`, `app/notify.py`, `app/tracker.py`, `app/connections-model.js`, `app/modules/vercel-publish/module.json`, `bin/migrate_liga.py`, `bin/overview_push.py`, `bin/registry.py`, `bin/state.py`, `ops/reseal_gate.py`.
**Змінюються (тести):** Додаток З. **Документи:** `README.md`, `CHANGELOG.md`, `package.json`, `docs/design/spaces-and-modules.md`.

**Порядок і зелене дерево.** Task 1–8 — дерево зелене на кожному кроці (нова функціональність поруч зі старою; Task 8 переводить тести на явні записи, які на старому коді теж зелені: явний запис завжди виграє у `Implicit`). Task 9–11 — видалення: **відомо червоні** тести, що стверджують `Implicit`, видалені підписи й оригінали; їхній перелік за прототипом — Додаток З; лікують Task 13 (родина провайдера/serve/dashboard/tracker/notify/comments) і Task 14 (родина vcs/gitlab/inbox/state/bin/migrate-стенди). Task 12 (охоронці) і Task 15–16 — після зеленого Task 14.


---

### Task 1: знімок 0.20.0 (ДО будь-якої правки коду)

**Files:** Create `tests/make_before_4d4b.py` (Додаток Е), `tests/fixtures/liga-migration/before-4d4b.json` (генерується), `tests/test_before_4d4b.py` (Додаток Б).

Знімок фіксує те, що 0.20.0 робить через оригінали й `Implicit`: п'ять стендів (`regular` — мігрована A–D, усі вісім оригіналів у корені рівні записам; `differs` — записи після міграції відрізняються від кореня; `partial` — нема записів `supabase-teams`/`jira-tracker`; `unmigrated` — `held` на 4d-3a, ролі веде `Implicit`; `plain` — звичайний простір), секції `capabilities` (+ `error_path`), `provider` (у просторі й у неявному просторі запиту), `api` (`/api/task`, `/api/modules`, `/api/comment-config`, `/api/teams-mute`, `/api/tasks-overview`), `vcs_target`, `registry_ssh`, `startup_text`, `root_keys`, `isolation`. Генератор — з замороженої копії, детермінований, на зміненому `app/`/`bin`/`ops` відмовляється (код виходу 2).

- [ ] **Step 1: тест форми знімка (червоний).** Створи `tests/test_before_4d4b.py` (Додаток Б, клас `Before4d4bShape`: мета, п'ять стендів і їхні секції, `Implicit` у знімку, вісім оригіналів у корені, розмір, **машинонезалежність** — жодного шляху, імені користувача й часового штампа).
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_before_4d4b
  ```
  Очікувано: `FileNotFoundError: …before-4d4b.json` у `setUpClass` (файла знімка ще нема).
- [ ] **Step 2: генератор.** Створи `tests/make_before_4d4b.py` рівно за Додатком Е (спільні помічники `Rig`, `NoNet`, `SocketTripwire`, `Server`, `scrub`, `rel`, `CLEAN` імпортуються з `make_before_4d3a.py`/`make_before_4d3b.py` — другої копії нема). Зашитий коміт джерела — `0d52a74`.
- [ ] **Step 3: зняти знімок із ЗАМОРОЖЕНОЇ копії** (ніколи з робочої теки після правок):
  ```bash
  D=$(mktemp -d) && git archive v0.20.0 | tar -x -C "$D" && cp tests/make_before_4d4b.py "$D/tests/"
  HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4b.py" --out tests/fixtures/liga-migration/before-4d4b.json
  HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4b.py" --out "$D/second.json" && cmp tests/fixtures/liga-migration/before-4d4b.json "$D/second.json"
  ```
  Очікувано: файл ≈ 42 KB; `cmp` мовчить (детермінований: штампи бекапів → `<stamp>`); `non_loopback_attempts` = 10 (їх зупинила розтяжка, до мережі не дійшла жодна). Ключі стендів: `differs/partial` — `api capabilities isolation provider registry_ssh root_keys vcs_target`; `regular/unmigrated` — те саме + `startup_text`; `plain` — `api capabilities provider root_keys`.
- [ ] **Step 4:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_before_4d4b` → 7 тестів OK. `git diff --stat HEAD` — лише три нові файли; `git status --short | grep -v '^??'` порожньо.
- [ ] **Step 5: коміт.**
  ```bash
  git add -- tests/make_before_4d4b.py tests/test_before_4d4b.py tests/fixtures/liga-migration/before-4d4b.json
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(4d-4b): знімок поведінки 0.20.0 (оригінали, Implicit, закон ізоляції)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/make_before_4d4b.py tests/test_before_4d4b.py tests/fixtures/liga-migration/before-4d4b.json
  ```

---

### Task 2: живі тести відтворювані у тимчасовому `HOME`

**Files:** Create `tests/live/_env.mjs`, `tests/live-env.test.mjs`; Modify `tests/live/fixture.mjs`, `tests/live/_spaces-kit.mjs`, `tests/live/_t45-fixture.mjs` (по одному рядку-імпорту).

Урок 4d-4a: правило «кожен прогін із тимчасовим `HOME`» ламало живі тести двома місцями, не повʼязаними з кодом: кеш браузерів Playwright (у справжньому домі) і git-ідентичність у фікстурах. Виправляємо ОДИН раз, до всіх живих задач.

- [ ] **Step 1: тест (червоний).** `tests/live-env.test.mjs` (код нижче) — три тести: кеш беремо з дому ОС (`os.userInfo().homedir`, не `$HOME`); тимчасовий `HOME` без `.gitconfig` отримує вигадану ідентичність, а заданий `GIT_CONFIG_GLOBAL`/`PLAYWRIGHT_BROWSERS_PATH`/наявний `.gitconfig` не перекриваються; імпорт у дочірньому процесі з тимчасовим `HOME` виставляє змінну.
  ```js
  import test from "node:test";
  import assert from "node:assert/strict";
  import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
  import { tmpdir } from "node:os";
  import path from "node:path";
  import { spawnSync } from "node:child_process";
  import { applyLiveEnv, playwrightCache } from "./live/_env.mjs";

  test("кеш Playwright береться з дому ОС, а не з $HOME", () => {
    const osHome = mkdtempSync(path.join(tmpdir(), "osh-"));
    assert.equal(playwrightCache(osHome, "darwin"), null, "нема кешу — null");
    mkdirSync(path.join(osHome, "Library", "Caches", "ms-playwright"), { recursive: true });
    assert.equal(playwrightCache(osHome, "darwin"), path.join(osHome, "Library", "Caches", "ms-playwright"));
    mkdirSync(path.join(osHome, ".cache", "ms-playwright"), { recursive: true });
    assert.equal(playwrightCache(osHome, "linux"), path.join(osHome, ".cache", "ms-playwright"));
    assert.equal(playwrightCache(null), null);
  });

  test("тимчасовий HOME без .gitconfig отримує вигадану ідентичність і кеш; задане не перекривається", () => {
    const osHome = mkdtempSync(path.join(tmpdir(), "osh-"));
    for (const sub of [[".cache", "ms-playwright"], ["Library", "Caches", "ms-playwright"], ["AppData", "Local", "ms-playwright"]]) {
      mkdirSync(path.join(osHome, ...sub), { recursive: true });       // той, що відповідає платформі прогону, знайдеться
    }
    const env = { HOME: mkdtempSync(path.join(tmpdir(), "h-")) };
    applyLiveEnv(env, osHome);
    assert.equal(env.PLAYWRIGHT_BROWSERS_PATH, playwrightCache(osHome));
    assert.match(readFileSync(env.GIT_CONFIG_GLOBAL, "utf8"), /live@example\.invalid/);
    const mine = { HOME: env.HOME, PLAYWRIGHT_BROWSERS_PATH: "/x", GIT_CONFIG_GLOBAL: "/y" };
    applyLiveEnv(mine, osHome);
    assert.deepEqual([mine.PLAYWRIGHT_BROWSERS_PATH, mine.GIT_CONFIG_GLOBAL], ["/x", "/y"]);
    const withCfg = { HOME: mkdtempSync(path.join(tmpdir(), "h-")) };
    writeFileSync(path.join(withCfg.HOME, ".gitconfig"), "[user]\n\tname = A\n");
    applyLiveEnv(withCfg, null);
    assert.equal(withCfg.GIT_CONFIG_GLOBAL, undefined, "наявний .gitconfig у HOME не підміняємо");
  });

  test("імпорт у дочірньому процесі з тимчасовим HOME виставляє обидві змінні", () => {
    const home = mkdtempSync(path.join(tmpdir(), "h-"));
    const r = spawnSync(process.execPath, ["-e", `import("${path.resolve("tests/live/_env.mjs")}").then(()=>console.log(JSON.stringify({g:process.env.GIT_CONFIG_GLOBAL||null})))`],
      { env: { PATH: process.env.PATH, HOME: home }, encoding: "utf8" });
    assert.equal(r.status, 0, r.stderr);
    assert.match(JSON.parse(r.stdout).g, /gitconfig$/);
  });
  ```
  `node --test tests/live-env.test.mjs` → `ERR_MODULE_NOT_FOUND` (нема `tests/live/_env.mjs`).
- [ ] **Step 2: реалізація** — `tests/live/_env.mjs` (повний текст):
  ```js
  /**
   * Відтворюваність живих тестів у ТИМЧАСОВОМУ `HOME` (4d-4b): правило «кожен прогін — з тимчасовим HOME» ламало два місця, не пов'язані з кодом:
   *  · Playwright шукає браузери в кеші справжнього дому → без `PLAYWRIGHT_BROWSERS_PATH` запуск падає «Executable doesn't exist»;
   *  · `git commit` у фікстурах без ідентичності (нема `~/.gitconfig`) падає «Please tell me who you are».
   * Імпорт цього файла (першим рядком у `fixture.mjs`) виправляє обидва: кеш — за паролем ОС (`os.userInfo().homedir`, а НЕ `$HOME`),
   * ідентичність — окремий тимчасовий `.gitconfig` з вигаданим автором. Нічого, що вже задано, не перекриває; справжній `~/.gitconfig` не читає й не пише.
   */
  import { existsSync, mkdtempSync, writeFileSync } from "node:fs";
  import os from "node:os";
  import path from "node:path";

  export function playwrightCache(osHome, platform = process.platform) {
    if (!osHome) return null;
    const sub = platform === "darwin" ? ["Library", "Caches", "ms-playwright"]
      : platform === "win32" ? ["AppData", "Local", "ms-playwright"] : [".cache", "ms-playwright"];
    const p = path.join(osHome, ...sub);
    return existsSync(p) ? p : null;
  }

  export function applyLiveEnv(env = process.env, osHome = (() => { try { return os.userInfo().homedir; } catch { return null; } })()) {
    if (!env.PLAYWRIGHT_BROWSERS_PATH) {
      const cache = playwrightCache(osHome);
      if (cache) env.PLAYWRIGHT_BROWSERS_PATH = cache;
    }
    const hasGlobal = env.GIT_CONFIG_GLOBAL || (env.HOME && existsSync(path.join(env.HOME, ".gitconfig")));
    if (!hasGlobal) {
      const dir = mkdtempSync(path.join(os.tmpdir(), "live-gitcfg-"));
      const file = path.join(dir, "gitconfig");
      writeFileSync(file, "[user]\n\tname = Live\n\temail = live@example.invalid\n");
      env.GIT_CONFIG_GLOBAL = file;
    }
    return env;
  }

  applyLiveEnv();
  ```
  Імпорт `import "./_env.mjs";` (з коментарем «4d-4b: Playwright-кеш і git-ідентичність у тимчасовому HOME — ДО будь-якого запуску браузера/git») — ПЕРШИМ імпортом у `fixture.mjs`, `_spaces-kit.mjs`, `_t45-fixture.mjs` (кожен живий файл із `playwright` тягне один із трьох; перевірка: `for f in $(grep -l playwright tests/live/*.test.mjs); do grep -qE "fixture.mjs|_spaces-kit.mjs|_t45-fixture.mjs" $f || echo NOFIX $f; done` → порожньо).
- [ ] **Step 3:** `node --test tests/live-env.test.mjs` → 3 OK; `node --check` для трьох змінених файлів. Показова перевірка в тимчасовому домі: `HOME=$(mktemp -d) node --test --test-concurrency=1 tests/live/git-sync.test.mjs` (коміти фікстури) і `HOME=$(mktemp -d) node --test --test-concurrency=1 tests/live/canvas.test.mjs` (браузер) — зелені без ручних змінних. (У прототипі перевірено `live-env.test.mjs` і `node --check`; живі файли виконавець прогоняє тут уперше.)
- [ ] **Step 4: коміт** (`git add -- tests/live/_env.mjs tests/live-env.test.mjs`; шляхи: усі п'ять файлів).

---

### Task 3: `app/isolation.py` — новий дім закону ізоляції

**Files:** Create `app/isolation.py`, `tests/test_isolation.py` (Додаток Б).

Чистий модуль (імпортує лише `os` і `pwd`; без `spaces`/`serve`/`deai_modules`, цикл імпорту неможливий): `isolated()`, `FAKE_ENV`, `route(role)`, `real_home(home)`. `real_home` — за `pwd` (суворіша за `liga_migrate._real_home`, яка лишається ширшою — шов міграції `DC_MIGRATE_LIGA=1`).

- [ ] **Step 1: тести (червоні).** `tests/test_isolation.py` (Додаток Б, клас `IsolationCore`, 11 тестів): модуль імпортує лише `os`/`pwd`; таблиця `FAKE_ENV`; `isolated()` = `DC_TASKS_FILE`|`DC_NO_OVERVIEW`; порядок `route`: шов → ізольовано → живо; кожна роль має свій шов; ролі без шва (`comments`, `vcs`, `publish`, `tokens`) — лише `isolated`/`live`; `real_home` за паролем ОС, а не за підміненим `HOME`; слід за симлінком; невідомий дім ОС і сміття — «справжній» (безпечніший бік).
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_isolation
  ```
  Очікувано: `ModuleNotFoundError: No module named 'isolation'`.
- [ ] **Step 2: реалізація.** `app/isolation.py` — Додаток Ж, «Нові файли» (повний текст 47 рядків: `FAKE_ENV = {'dashboard': 'DC_TEAM_FAKE', 'tracker': 'DC_TRACKER_FAKE', 'notify': 'DC_TEAMS_FAKE'}`; `route(role)` — `('fake', шлях)` → `('isolated', None)` → `('live', None)`).
- [ ] **Step 3: `app/implicit.py` НЕ чіпаємо** (спроба зробити його тонким делегатом ламає два наявні тести: `ImplicitCore.test_route_not_shared_is_live_when_isolated` — `shared=False` — і `IsolatedInstallConfig.test_no_import_cycle` — модуль має імпортувати лише `os`; виміряно). Замість делегування — тест точної копії, що живе до Task 10 (код у `tests/test_isolation.py`, Додаток Б, «Клас Task 3»):
  ```python
class ParityWithImplicitUntilRemoval(unittest.TestCase):
    """До видалення `app/implicit.py` (4d-4b Task 10) його `isolated`/`route` — ОРИГІНАЛ, а `isolation` — точна копія: на всіх комбінаціях оточення відповіді рівні
    (`implicit.py` не чіпаємо: тести `ImplicitCore` стверджують його форму, зокрема `shared=False`). Клас видаляється разом із модулем."""

    COMBOS = ({}, {'DC_TASKS_FILE': '1'}, {'DC_NO_OVERVIEW': '1'}, {'DC_TEAM_FAKE': '/tmp/f.json'}, {'DC_TRACKER_FAKE': '/tmp/f.json', 'DC_NO_OVERVIEW': '1'},
              {'DC_TEAMS_FAKE': '/tmp/f.json', 'DC_TASKS_FILE': '1'}, {'DC_TEAM_FAKE': ''})

    def test_the_copy_equals_the_original(self):
        import implicit
        for env in self.COMBOS:
            with mock.patch.dict(os.environ, env):
                self.assertEqual(implicit.isolated(), isolation.isolated(), env)
                for role in implicit.IMPLICIT_ROLES:
                    self.assertEqual(implicit.route(implicit.for_role(role)), isolation.route(role), (env, role))
        self.assertEqual({r: implicit.for_role(r).fake_env for r in implicit.IMPLICIT_ROLES if implicit.for_role(r).fake_env},
                         isolation.FAKE_ENV)
  ```
- [ ] **Step 4:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_isolation tests.test_implicit` → 72 OK (виміряно); `git diff HEAD --stat` — лише нові файли.
- [ ] **Step 5: мутація.** У `isolation.route` помінявши порядок (`isolated()` раніше за шов) → `test_route_order_fake_then_isolated_then_live` червоніє; у `real_home` замінити `pwd` на `os.path.expanduser('~')` → `test_real_home_is_the_pwd_home_not_the_HOME_variable` червоніє.
- [ ] **Step 6: коміт** `app/isolation.py tests/test_isolation.py`.

---

### Task 4: крок `liga-4d4b` — чистий розрахунок (`plan`)

**Files:** Modify `app/liga_migrate.py`, `tests/test_liga_migrate_d.py` (один тест); Create `tests/test_liga_migrate_e.py` (Додаток А: класи `PlanE`, потім решта в Task 5–7).

Нічого не пишемо на диск: `plan(step=STEP_E)` читає корінь `tasks.json`, `space.json` ЛІГИ і `secrets.json`, для кожного з восьми `ORIGINAL_KEYS` вирішує: нема → мовчки; непридатне → `unfit:<ключ>`; тримача нема (запис відсутній / не `enabled` / без `shared_state` / для пароля `compat != design-canvas`) → `no-record:<модуль>`; значення відмінне → `differs:<ключ>` (для пароля — перезапис, Д4, `overwrote:password`); порожньо й копіюємо (`gitlab_*`, пароль) → у план копії; збіг → у список видалення. Пара Supabase — все або нічого (`partial:supabase`). Охоронець маркера (`marker-kept:gitlab_host_ip`).

- [ ] **Step 1: тести (червоні).** `tests/test_liga_migrate_e.py` — спільний стенд `_StandE` + клас `PlanE` (Додаток А, 18 тестів: звичайний шлях «вісім видалено, три скопійовано»; `plan` чистий (дерево не змінилось); `skip-nothing` і нотатки ≠ `skip-nothing`; `unfit`; відсутній/вимкнений/без-`shared_state` тримач; `partial:supabase`; `differs`; конфлікт пароля `overwrote:password`; `compat != design-canvas`; числовий пароль → рядок; нормалізація адреси; три тести охоронця маркера; ворота (`held` раннього кроку тримає Е); перевірка «запис лишається тим самим постачальником» → `abort-provider`).
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e.PlanE
  ```
  Очікувано (виміряно на v0.20.0): усі тести `ERROR: AttributeError: module 'liga_migrate' has no attribute 'STEP_E'. Did you mean: 'STEP_A'?`.
  Один наявний тест міняється під п'ять кроків `ALL_STEPS` — `tests/test_liga_migrate_d.py` `StepDConstants.test_steps_list_and_shape` (довжина 5, склад; `STEP_E.ungated is False`, `STEP_E.originals is True`, `roles == ()`; `STEPS` лишається чотирма до Task 7 — окремий assert).
- [ ] **Step 2: реалізація (hunk-и Додатка Ж, `app/liga_migrate.py`).** Застосуй через `Edit`: `ABORT_CODES` + `_REASONS` (`abort-originals`, `abort-verify`); `Step` + поле `originals` (`defaults=(None, False, False)`); блок `ORIGINALS`/`ORIGINAL_KEYS`/`_MARKER_KEYS`/`_fits`/`_effective`/`_holder_ready`/`_held`/`_decide_originals`/`_originals_state`/`_plan_originals` (hunk `+448,181`); гілка `if step.originals: return _plan_originals(…)` у `_plan` (hunk `+674,8`); імена ключів кореня в звіті `plan` (hunk `+764,10`); `STEP_E` і `ALL_STEPS = (A, B, C, D, E)` (hunk `+796,10`), **`STEPS = ALL_STEPS[:4]`** з коментарем «до Task 7 на старті біжать чотири кроки: запису Е ще нема». Ключове:
  ```python
  Step = namedtuple('Step', 'mark roles tracks suffix stamp_re entries ungated originals', defaults=(None, False, False))
  STEP_E = Step('liga-4d4b', (), False, '-liga-4d4b', re.compile(r'^[0-9]{8}-[0-9]{6}(-[0-9]{1,3})?-liga-4d4b$'),
                lambda cfg, present: {}, False, True)
  ```
  (точний `stamp_re` і `entries` — як у hunk `+796`; `entries` — порожня функція: ролей кроку Е нема.)
- [ ] **Step 3:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e.PlanE tests.test_liga_migrate_d tests.test_liga_migrate_c tests.test_liga_migrate_b tests.test_liga_migrate` → зелені (`STEPS` ще чотири, стенди 4d-3 не бачать Е).
- [ ] **Step 4: мутації** (по одній, `python3 -B`, `sha256` до/після): `if equal:` → `if True:` у `_decide_originals` (видаляти завжди) → червоніють `test_differs_keeps_root_and_does_not_overwrite`, `test_a_person_changed_a_setting_between_copy_and_delete_keeps_that_key` (останній — Task 5); `note('partial:supabase')` → `pass` і зняти `sb_blocked` → `test_supabase_pair_is_all_or_nothing`; `if had_markers:` → `if False:` → `test_marker_guard_keeps_one_marker_key`, `test_marker_guard_uses_ssh_key_when_it_is_the_only_marker`.
- [ ] **Step 5: коміт** `app/liga_migrate.py tests/test_liga_migrate_e.py tests/test_liga_migrate_d.py`.

---

### Task 5: крок Е — запис (precheck → бекап → секрети → налаштування → перевірка → видалення → позначка)

**Files:** Modify `app/liga_migrate.py`; тести — клас `RunE` у `tests/test_liga_migrate_e.py` (Додаток А).

Порядок і замки (спека §1.4): (1) **precheck до бекапу** — `_records_writable(tasks.json)` і `_secrets_writable()`: інакше `abort-originals`/`abort-secrets` БЕЗ бекапу (кожен старт інакше лишав би по теці бекапу); (2) бекап (`tasks.json`, `space.json`, `secrets.json`, `spaces.json`, sha256, 0600/0700); (3) `deai_modules.write_secrets` (бере `WRITE_LOCK` сам); (4) `_merge_settings` — злиття лише відсутніх/порожніх ключів у ПОТОЧНИЙ `space.json`; (5) `_verify_copies` — перечитане з диска (без локу) дорівнює плану, інакше `abort-verify` і **нічого не видалено**; (6) `_commit_originals` — під `WRITE_LOCK`: `_file_sig` → читання → **свіже повторне рішення** (`_decide_originals` на щойно прочитаних записі й секреті) → `.bak` → `_file_sig` → `atomic_write_json`; ключі видаляються по одному з щойно прочитаного файла; ретраї `_RECORDS_ATTEMPTS=3`; (7) позначка — `_commit_space(mark_patch=…)` **останньою**.

- [ ] **Step 1: тести (червоні).** `RunE` (Додаток А, 12 тестів): `test_run_copies_verifies_removes_then_marks`; `test_mark_is_written_last`; `test_backup_and_dot_bak_hold_the_bytes_before`; `test_abort_before_backup_when_tasks_unwritable` (нема теки бекапів); `test_abort_verify_when_the_copy_does_not_read_back`; `test_failure_before_the_root_leaves_copies_and_next_start_finishes`; `test_failure_between_root_and_mark_is_finished_by_next_start`; **`test_a_person_changed_a_setting_between_copy_and_delete_keeps_that_key`** (змінює `ssh_key` ПІСЛЯ перевірки копій і ДО запису кореня — доводить свіже рішення; на прототипі старіша версія цього тесту підміняла `_decide_originals` не в тому виклику і мутація «без свіжого рішення» ВИЖИВАЛА — переписано); `test_race_on_tasks_file_aborts`; `test_idempotent`; `test_notes_only_still_writes_mark`; `test_foreign_edits_to_space_json_survive`.
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e.RunE
  ```
  Очікувано: `AttributeError: module 'liga_migrate' has no attribute '_run_originals'` (або `abort-internal`-статус у `_run`).
- [ ] **Step 2: реалізація (hunk-и Додатка Ж).** `_commit_space(..., mark_patch=None)` (hunk `+1040,7`, `+1062,7`: ключі позначки Е — `copied/removed/kept/notes`; чужі ключі, що дописав власник між планом і записом, не перезаписуються); блок `_secrets_writable`/`_merge_settings`/`_verify_copies`/`_commit_originals`/`_run_originals` (hunk `+1109,137`); гілка `if step.originals: return _run_originals(home, step, p, space_path)` у `_run_locked` (hunk `+1289,8`). Код `_commit_originals` і `_run_originals` — Додаток Ж (≈90 рядків, повністю перевірено прототипом).
- [ ] **Step 3:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e` (Plan+Run) зелений; суміжні `tests.test_liga_migrate_d` зелений.
- [ ] **Step 4: мутації:** `if not ok:` → `if False:` (`abort-verify`) → `test_abort_verify_when_the_copy_does_not_read_back`; `todo = [k for k in planned_remove if k in fresh['remove'] and k in cfg]` → без `fresh['remove']` → `test_a_person_changed_a_setting_between_copy_and_delete_keeps_that_key` (виміряно: ЧЕРВОНІЄ лише після переписування тесту); прибрати `_file_sig`-звіряння перед `atomic_write_json` → `test_race_on_tasks_file_aborts`.
- [ ] **Step 5: коміт.**

---

### Task 6: крок Е — відкат (домердж), LIFO на п'ять кроків

**Files:** Modify `app/liga_migrate.py`; тести — клас `RestoreE` у `tests/test_liga_migrate_e.py`.

`restore <stamp-E> [--hold]` повертає `space.json` і ліговий шматок секретів з бекапу (LIFO, `refuse-later-applied`, запобіжна копія `-pre-restore` — як у інших кроків) **і додатково домерджує корінь**: перелік — з позначки `removed` ПОТОЧНОГО `space.json` (прочитаної ДО його заміни; запасний шлях, коли позначка нечитана чи без `removed`: ключі `ORIGINAL_KEYS` з `tasks.json` бекапу, відсутні в живому), значення — з `tasks.json` бекапу. Додається **лише ключ, якого в живому корені нема**; свій ключ людини лишається (`kept-live`). **Порядок: спершу корінь, потім `space.json`/секрети** — збій між ними лишає простір мігрованим І з поверненими ключами (узгоджено), а не «немігрованим без ключів».

- [ ] **Step 1: тести (червоні).** `RestoreE` (Додаток А, 7 тестів): `test_restore_merges_removed_keys_back_and_keeps_live_edits` (нова задача й свій `preview_password` у живому файлі переживають відкат; звіт `root_restored`, `kept_live`); `test_restore_never_rewrites_the_whole_file`; `test_restore_with_hold_marks_only_e`; `test_restore_fallback_when_mark_lacks_removed`; **`test_restore_aborts_when_the_live_file_keeps_changing`** (постійна гонка → `abort-restore`, `space.json` і корінь не чіпано; на прототипі мутація «без `_file_sig`-звіряння» спершу ВИЖИВАЛА — тест дописано); `test_restore_refuses_when_the_live_file_is_unreadable` (корінь першим: `space.json` не чіпано); `test_lifo_five_steps` (E, потім D, C, B, A; `refuse-later-applied` для будь-якого іншого порядку).
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e.RestoreE
  ```
  Очікувано: `restore` Е повертає `space.json`, але корінь НЕ повернуто → `AssertionError: 'jira_base' not found in …` у `test_restore_merges_…`.
- [ ] **Step 2: реалізація.** `_restore_root(sp, d, files)` (hunk `+1481,40`, ≈35 рядків, Додаток Ж) і виклик у `_restore_locked` ПЕРЕД записом `space.json` (hunk `+1548,12`); `root_restored`/`kept_live` у звіті (початок hunk `+1591`).
- [ ] **Step 3:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e tests.test_liga_migrate_d` зелені.
- [ ] **Step 4: мутації:** тіло домерджу → `cur = dict(old)` (перезапис цілого файла) → `test_restore_merges_…`, `test_restore_never_rewrites_the_whole_file` (виміряно); прибрати `_file_sig`-звіряння перед записом → `test_restore_aborts_when_the_live_file_keeps_changing` (виміряно).
- [ ] **Step 5: коміт.**

---

### Task 7: вивід Е, `status`, CLI `unhold`, `roles_state`, увімкнення п'ятого кроку на старті

**Files:** Modify `app/liga_migrate.py`, `bin/migrate_liga.py`, `tests/test_liga_migrate_d.py`, `tests/test_liga_migrate_b.py`, `tests/test_liga_migrate_c.py` (п'ять тестів, Поправка 6); тести — класи `RolesState`, `StartupE`, `StatusAndCli` у `tests/test_liga_migrate_e.py`.

`roles_state(home=None)` → `[{role, module, on, reason, fix}]` для шести ролей (порядок `LIGA_ROLES`): ЧИСТА (без мережі й без коду модуля), `on` — `_provider_for` дає ЯВНИЙ `Module` цієї ролі і `module_ctx` будується; причина — перша застосовна (`disabled` → код кроку з `last.json` (Поправка 1) → `skip-held` (Поправка 2) → останній звіт `skip-*`/`abort-*` → `module-error`/`module-untrusted`/`bad-settings` → `no-record`); `integrations` ЛІГИ вимкнено — `on: False, reason: 'integrations-off', fix: ''` і рядків старту нема («так було й у 0.20»). Команди виправлення без шляхів і значень. `unhold <позначка>` знімає лише `{held: true}`.

- [ ] **Step 1: тести (червоні).** `RolesState` (13), `StartupE` (3), `StatusAndCli` (5) у Додатку А: усі шість увімкнені → рядків нема; `disabled`; код зі звіту `last.json` + текст «оточення й pipeline-feedback більше не читаються»; `not-migrated`; `skip-held` з `unhold liga-4d3a`; **`held` раннього кроку для власників B/C** (Поправка 2); коди `skip-path-in-git`/`skip-tasks-unreadable`/`skip-space-json-unreadable`/`abort-write`/`skip-busy` мають свої підказки; `no-record` → `run`; несправний модуль; нечитабельний `space.json` — усі шість `space-json-unreadable`; `integrations-off` тихо; рядки без значень і шляхів. Старт: п'ять бекапів і ОДИН рядок відкату (для найпізнішого); рядок «оригінали видалено з tasks.json; єдина копія — secrets.json і backups/ у домі Deai» (`ORIGINALS_REMOVED_LINE`) і підсумок «скопійовано: …; видалено: …»; блок «ролі ЛІГИ вимкнено» друкується на КОЖНОМУ старті, поки роль вимкнена; ізольований прогін блок не друкує. CLI: `dry-run` називає ключі без значень; `unhold` (знімає лише `{held: true}`, чужі позначки лишаються, `refuse-not-held` для застосованого кроку, `refuse-mark` для невідомого, `refuse-no-liga`, `skip-layer-off`).
  Змінити наявне (Поправка 6): `tests/test_liga_migrate_d.py:481` `FourStepsStartup.test_order_backups_and_one_restore_hint` — п'ять кроків, п'ять бекапів, ОДИН рядок відкату, рядок підказки LIFO називає чотири попередні; `tests/test_liga_migrate_b.py` `CliStepsTest.test_single_step_output_is_byte_identical_to_4d3a` (+ секція «Ролі ЛІГИ» у `status`), `StepBRunTest.test_second_start_is_skip_done_and_writes_nothing`, `TwoStepsStartupTest.test_second_start_is_silent_and_writes_nothing`, `tests/test_liga_migrate_c.py` `PublisherPresent.test_publisher_present_is_quiet_on_startup_but_visible_in_dry_run` — очікування «тиші» стають точним списком рядків вимкнених ролей, «нічого не пише» — порівнянням дерева файлів.
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e.RolesState tests.test_liga_migrate_e.StartupE tests.test_liga_migrate_e.StatusAndCli
  ```
  Очікувано: `AttributeError: module 'liga_migrate' has no attribute 'roles_state'` (і `unhold`).
- [ ] **Step 2: реалізація (hunk-и Додатка Ж).** Великий hunk `+1591,186` (`LIGA_ROLES`, `_ROLE_FIX`, `_held_mark`, `_reason_from_reports`, `roles_state`, `roles_lines`, `ORIGINALS_REMOVED_LINE`, `originals_summary`, `unhold`), `status`/`status_text` (`+1784…+1836`), `startup` (`+1899`, `+1932`, `+1949`), `report()` — рядок Е; **перемикач `STEPS = ALL_STEPS`** (після нього на старті біжать п'ять кроків). `bin/migrate_liga.py` — підкоманда `unhold <позначка>`, вивід Е (50 рядків, Додаток Ж).
- [ ] **Step 3:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_e tests.test_liga_migrate_d tests.test_liga_migrate_c tests.test_liga_migrate_b tests.test_liga_migrate` — зелені після правки п'яти тестів (виміряно перед правкою: `test_liga_migrate_e` 58 OK, `test_liga_migrate` 132 OK, `…_d` 2 червоні, `…_c` 1, `…_b` 3).
- [ ] **Step 4: мутація:** `return 'skip-held'` у `_reason_from_reports` → `pass` → `RolesState.test_held_step_names_unhold`, `test_early_step_held_names_the_early_mark_for_later_owners` (виміряно).
- [ ] **Step 5: коміт** `app/liga_migrate.py bin/migrate_liga.py tests/test_liga_migrate_e.py tests/test_liga_migrate_d.py`.

---

### Task 8: `tests/liga_fixture.py` і хвиля 1 переходу тестів на явні записи

**Files:** Create `tests/liga_fixture.py`, `tests/test_liga_fixture.py` (Додаток Б); Modify тести хвилі 1 (Додаток З, таблиця «Хвиля 1»).

До видалення коду переводимо тести з «облікові в корені/оточенні» на явні записи: на СТАРОМУ коді вони зелені, бо явний запис завжди виграє у `Implicit` (запасний постачальник діє лише без явного ввімкненого запису). Це зменшує Task 13–14 до «лише те, що стверджує видалене».

`LigaFixture` (Додаток Б): `env()` — тимчасові `HOME`/`DEAI_HOME`, без жодних облікових оточення, `spaces.legacy_tasks_file` → тимчасовий файл; `build(roles, overrides, tasks, root_extra)` — прямі записи шести ролей рівно такої форми, яку пишуть кроки A–C, + `secrets.json` (0600) + корінь БЕЗ облікових; `legacy_root()` + `migrate()` — старий корінь із вісьмома оригіналами і **справжній** `liga_migrate.run_all` на п'яти кроках («як у людини»; у тестовому корені `liga-4d4a` дає `skip-nothing`).

- [ ] **Step 1: тести фікстури (червоні).** `tests/test_liga_fixture.py` (3): `build()` дає шість явних `Module`-постачальників і корінь `['registry', 'tasks']`; `migrate()` дає ті самі постачальники, чистий корінь і `publish_password == liga_fixture.PASSWORD`; `overrides={'tracker': {'enabled': False}}` вимикає лише трекер (`roles_state`: `disabled`).
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_fixture
  ```
  Очікувано (виміряно на v0.20.0, коли Task 4–7 ще не було): `AttributeError: … 'roles_state'` і `['done','done','done','skip-nothing'] != […'done']`; на дереві після Task 7 — `ModuleNotFoundError: liga_fixture`, поки не створено файл.
- [ ] **Step 2: реалізація:** `tests/liga_fixture.py` — Додаток Б (127 рядків). Усі значення вигадані (`https://sb.example.com`, `alpha@example.com`, `203.0.113.7`).
- [ ] **Step 3: хвиля 1** — за таблицею Додатка З (файл → що замінити → очікуваний результат): `tests/sbconf.py` (`write_root`/`drop_root`/`ENV` → побудова запису через `LigaFixture`), `test_legacy_comments.py`, `test_dashboard.py`, `test_tasks_overview.py`, `test_inbox.py`, `test_comments_agent.py`, `test_comments_role.py`, `test_integrations_off.py`, `test_spaces_serve.py`, `test_state.py`, `test_supabase_comments.py`, `test_tracker.py`, `test_notify.py` — **лише** там, де сценарій «облікові з кореня/оточення → роль працює» (не там, де тест стверджує саме `Implicit`/оригінали: ті лишаються до Task 13). Після кожного файла: `HOME=$(mktemp -d) python3 -B -m unittest tests.<файл>` зелений на СТАРОМУ коді. Ізольовані сценарії (`DC_TASKS_FILE`) для `comments` тут НЕ чіпаємо: їм потрібна зміна `comments_route` (Task 10).
  ⚠️ Прототип цю хвилю НЕ виконував (тести конвертувалися лише на вже зміненому коді). Припущення «на СТАРОМУ коді зелено» спирається на правило «явний запис виграє у `Implicit`»; якщо конкретний файл на старому коді червоніє — не силуй: залиш його до Task 13 і запиши причину в звіт.
- [ ] **Step 4:** повний Python-набір не червонішає: `python3 "$G" 2400 3072 python3 -B -m unittest discover -s tests` (під тимчасовим `HOME`) — порівняти кількість тестів і відсутність нових падінь з базою `Ran 4449 tests … OK (skipped=2)` плюс нові тести Task 1–7.
- [ ] **Step 5: коміт** кожного файла хвилі окремо чи групою за шляхами.


---

### Task 9: постачальник без `Implicit` + аудит викликів `provider()`

**Files:** Modify `app/deai_modules.py`; тести — `tests/test_originals_gone.py` (класи `ProviderWithoutImplicit`, `ProviderCallersPinTheSpace`, Додаток В).

`_provider_for(role, space, …)` — одна гілка для всіх просторів: неявний простір (`spaces._is_implicit(space)`: шар вимкнено чи простір запиту не зафіксовано) → `None` БЕЗ читання реєстру/`space.json`; решта — `explicit = space_modules(space)` (`ModuleError('space-json-unreadable')` для КОЖНОЇ ролі, а не лише для чотирьох), `_paper_failure`, переможець, `_enabled_module_is_lost` для `comments`. ЛІГА без ввімкненого запису ролі → `None`. Видаляються `IMPLICIT_ROLES`, `IMPLICIT_ON_ERROR_ROLES`, `STRICT_IMPLICIT_ROLES`; `capabilities` на `ModuleError`/збої — `None` (не `'legacy'`); `api_value(Module)→id`, `api_value(None)→None`, решта — `TypeError`; `publish_legacy_path` і `comment_scheme_legacy` — лише «вбудований модуль із `compat`». `API_IMPLICIT` лишається константою (до 4d-4c: її розбирають JS-охоронці), але ядро її більше не повертає. Додається `deai_modules.publish_password(space)` (Task 11 її споживає; тут — разом, бо це та сама умова `publish_legacy_path`).

- [ ] **Step 1: тести (червоні).** `ProviderWithoutImplicit` (9): у ядрі нема імен `Implicit`/`IMPLICIT_ROLES`/`IMPLICIT_ON_ERROR_ROLES`/`STRICT_IMPLICIT_ROLES`, `api_value('legacy')` — `TypeError`; шість явних записів дають шість `Module`; ЛІГА без записів — `None` для всіх шести; вимкнений запис — `None`; **незафіксований простір запиту — жодної ролі** (раніше `Implicit` для шести); шар вимкнено — ролей і секретів нема; нечитабельний `space.json` — `space-json-unreadable` для всіх шести; `capabilities` на помилці — `publish`/`vcs` = `None`, нічого зі значень `'legacy'`; `publish_legacy_path`/`comment_scheme_legacy` бачать лише модуль. `ProviderCallersPinTheSpace` (2): AST-перелік однопараметрових `provider('<роль>')` у `app`/`bin`/`ops` дорівнює точно семи аудитованим викликам (Поправка 11), і сам сканер «може впасти» (зіпсований код дає результат).
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_originals_gone.ProviderWithoutImplicit tests.test_originals_gone.ProviderCallersPinTheSpace
  ```
  Очікувано (виміряно на базі `v0.20.0` + `isolation.py` + `liga_fixture.py`): `ProviderWithoutImplicit` — 7 з 9 червоних: `test_the_core_has_no_fallback_names`, `test_a_liga_role_without_a_record_is_none`, `test_a_disabled_record_is_none`, `test_an_unpinned_request_space_has_no_roles`, `test_layer_off_has_no_roles`, `test_unreadable_space_json_is_an_error_for_every_role`, `test_capabilities_error_path_gives_none_not_legacy`; `ProviderCallersPinTheSpace` — зелений і ДО Task 9 (це аудит, а не вимога: він фіксує, що Task 9–11 не додають викликів без простору).
- [ ] **Step 2: реалізація (hunk-и `app/deai_modules.py`, Додаток Ж):** `import isolation` замість `import implicit`; видалення трьох констант; нова гілка `_provider_for`; `api_value`; `capabilities` (`caps[role] = None`, у `except` — `{role: None …}` + `error`); `publish_legacy_path`; `publish_password(space)` (умова: простір непорожній, не неявний, шар увімкнено; ізольований прогін у **справжньому домі** (`isolation.real_home`) — `None`; `publish_legacy_path(prov, space)`; секрет `password`; тотальна — не кидає); `comment_scheme_legacy(space, prov)`. Оновити докстрінги, що кажуть «`Implicit` АБО…» (прототип їх лишив застарілими — виконавець чистить).
- [ ] **Step 3: аудит (Р4) у звіті:** `grep -n "provider(" app/*.py bin/*.py ops/*.py | grep -v "def \|#"` — сім однопараметрових викликів (Поправка 11), кожен у потоці запиту чи `_in_space`; двопараметрові (`bin/overview_push.py:118/150/177`, `serve.comments_provider`, `:5463`, `:8694`) передають `space`.
- [ ] **Step 4: що червоніє (відомо, лікує Task 13):** тести, що стверджують `Implicit` у провайдері/`capabilities` (`test_implicit.py::ProviderImplicit/RolesParity/PublishModule`, `test_modules.py`, `test_comments_role.py`, `test_integrations_off.py`, `test_publish_module.py`) і всі, що імпортують `implicit` (Додаток З, колонка «причина»). Нові тести Task 9 зелені.
- [ ] **Step 5: мутації:** повернути в `_provider_for` гілку «порожньо явних → щось» → `test_a_liga_role_without_a_record_is_none`; у `publish_password` прибрати перевірку `real_home` → `test_isolated_run_in_the_real_home_never_reads_the_shared_secret` (Task 11).
- [ ] **Step 6: коміт** `app/deai_modules.py tests/test_originals_gone.py`.

---

### Task 10: споживачі `Implicit` у `serve`/`dashboard`/`tracker`/`notify`/`bin/*`, закон ізоляції, видалення `app/implicit.py`

**Files:** Modify `app/serve.py`, `app/dashboard.py`, `app/notify.py`, `app/tracker.py`, `app/install_config.py` (лише імпорт `isolation`), `app/liga_migrate.py` (імпорт `isolation`), `bin/overview_push.py`, `bin/state.py`; Delete `app/implicit.py`; тести — `tests/test_originals_gone.py` (`CommentsInIsolation`, `DashboardSyncWithoutLegacy`), `tests/test_isolation.py` (видалити `ParityWithImplicitUntilRemoval`).

Усі `isinstance(prov, implicit.Implicit)` у `serve` видалено (`vcs_provider`, `_team_fetch`, `_tracker_fetch`, `notify_call`, `comments_route`, `ProjectComments.kind == 'implicit'`, `publish_comments`, `_overview_launch`); `implicit.route(implicit.for_role(r))` → `isolation.route(r)` (три викликачі: `_team_fetch`, `_tracker_fetch`, `notify_call`; параметр `shared` зникає — він завжди був `True`); `implicit.isolated()` → `isolation.isolated()` (серве, `install_config`, `liga_migrate`). Видалено легасі-збирачі: `serve._comments_legacy_ctx`, `dashboard.legacy_ctx/legacy_module`, `tracker.legacy_ctx/legacy_module`, `notify.legacy_ctx/legacy_module`, `overview_push._legacy_config`. **Лишаються** `serve._vcs_legacy_ctx`/`_flat_mirror_overlay` (ізольований ctx `shared_state`-запису `git-sync`, не збирач з оригіналів) і `_publish_legacy_ctx` (ctx публікації ЛІГИ в режимі `cli`).

**Д6 — закон ізоляції для коментарів** (єдина змістовна зміна поведінки цього завдання): ізольований прогін (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) із вбудованим `shared_state`-записом `supabase-comments`: у ТИМЧАСОВОМУ домі (`isolation.real_home(spaces.home())` хибне) `module_ctx` бере налаштування й секрет фікстури; у СПРАВЖНЬОМУ домі — `ModuleError('comments-unconfigured', COMMENTS_UNCONFIGURED)`. Для `dashboard`/`tracker`/`notify` нічого не міняється (шов або відмова — ізольований прогін НІКОЛИ не живий).

- [ ] **Step 1: тести (червоні).** `CommentsInIsolation` (4): тимчасовий дім → контекст фікстури (`url`, `key`); справжній дім (підміна `isolation.real_home`) → `comments-unconfigured` з текстом «…на екрані «Підключення»»; НЕізольований прогін → запис у будь-якому домі; нема запису → `comments_provider` → `None`, корінь не читається. `DashboardSyncWithoutLegacy` (2): без запису `supabase-dashboard` `overview_push._target(sp) == (None, None, False)` навіть із `SUPABASE_URL`+`SUPABASE_SERVICE_KEY` в оточенні; `_legacy_config` нема; із записом — `module_ctx`.
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_originals_gone.CommentsInIsolation tests.test_originals_gone.DashboardSyncWithoutLegacy
  ```
  Очікувано до змін (виміряно на базі `v0.20.0`): `CommentsInIsolation` — 3 з 4 червоних (`test_temp_home_gives_the_fixture_context`, `test_real_home_is_refused`, `test_a_missing_record_is_unconfigured_not_the_root`); `DashboardSyncWithoutLegacy` — 1 з 2 (`test_no_dashboard_record_means_no_provider_even_with_the_service_key`).
- [ ] **Step 2: реалізація** — hunk-и `app/serve.py` (≈480 рядків diff: `comments_route` з `real_home`, `vcs_provider`, `_team_fetch`/`_tracker_fetch`/`notify_call` через `isolation.route`, `ProjectComments`, `_overview_launch`, `publish_comments`), `app/dashboard.py`, `app/notify.py`, `app/tracker.py`, `bin/overview_push.py`, `bin/state.py` (читач `kind`), Додаток Ж. Потім `git rm app/implicit.py` і прибрати `ParityWithImplicitUntilRemoval` з `tests/test_isolation.py` (рядок у таблиці відповідності: «копія доведена, оригінал видалено»). Тексти `COMMENTS_UNCONFIGURED`/`tracker.UNCONFIGURED`/`dashboard.UNCONFIGURED`/`notify.UNCONFIGURED` → «…додайте адресу й ключ (облікові) на екрані «Підключення»» (Поправка 8); `bin/overview_push.py`: нема постачальника дашборда → «нема постачальника командного дашборда» (`cmd_sync`).
- [ ] **Step 3:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_originals_gone tests.test_isolation tests.test_liga_migrate_e` зелені; `python3 -B -c "import sys; sys.path[:0]=['app','bin']; import serve, overview_push, dashboard, tracker, notify, liga_migrate, install_config"` — без помилок імпорту.
- [ ] **Step 4: мутація:** прибрати `real_home` з `comments_route` (`if False:`) → `CommentsInIsolation.test_real_home_is_refused` (виміряно).
- [ ] **Step 5: що червоніє (Додаток З):** усі модулі, що імпортували `implicit` чи легасі-збирачі; лікує Task 13.
- [ ] **Step 6: коміт** (шляхи — усі змінені файли коду + два тести; `git rm app/implicit.py` входить у pathspec).

---

### Task 11: читачі оригіналів видалено; пароль превʼю й ключ git — з записів; JS

**Files:** Modify `app/liga_migrate.py` (приватні копії читачів), `app/install_config.py`, `app/serve.py`, `bin/registry.py`, `ops/reseal_gate.py`, `app/modules/vercel-publish/module.json`, `app/connections-model.js`, `tests/connections-model.test.mjs`, `tests/test_liga_migrate_c.py` (підпис/версія), `tests/test_vercel_publish.py` (версія); тести — `tests/test_originals_gone.py` (`PreviewPasswordFromTheRecord`, `GitChainWithoutTheRoot`, `RegistrySshKey`, `TextsNameTheConnectionsScreen`).

Таблиця змін (спека §2): `install_config.supabase_config/supabase_from/service_key_config/jira_config/jira_from` — **видалено** (лишаються `legacy_tasks_path`, `load_legacy_tasks`, `LEGACY_SHOTS_BUCKET`, регекспи форми — їх потребує міграція); їхня копія — приватні `liga_migrate._supabase_from`/`_jira_from` (тіла байт у байт, ізоляція `isolation.isolated()`; кроки A–C ще читають оригінали на першому старті старої установки); `serve.supabase_config/jira_config` — видалено; `gitlab_cfg(task)` — лише поля задачі; `_vcs_ssh(*own)` — `own > налаштування модуля` (поле, якого нема в задачі, у ціль НЕ кладеться — модуль бере своє); `vcs_target(tid, task, settings)`, `vcs_task(tid, task)`; `preview_password(task, space)` — **задача > секрет `password` запису `vercel-publish` (`deai_modules.publish_password(space)`) > `1100`** (споживачі: `/api/task`, `_preview_password`, `_publish`, `ops/reseal_gate.py` — простір ЛІГИ з реєстру `legacy: true`, `liga_space()`); `registry._ssh_key()` — налаштування `ssh_key` запису `git-sync` ЛІГИ, інакше `~/.ssh/gitlab_ed25519` (реєстр/`space.json` нечитабельні чи шар вимкнено — типовий).

- [ ] **Step 1: тести (червоні).** `PreviewPasswordFromTheRecord` (6): задача → секрет → `1100`; **корінь ігнорується** (і з записом, і без нього — `1100`); режим модуля (`compat` порожній) цього секрета тут не читає; ізольований прогін у тимчасовому домі бере секрет фікстури; у справжньому домі — `1100` (Д6); старий трипараметровий підпис — `TypeError`. `GitChainWithoutTheRoot` (3): ціль не несе ключа/IP з кореня, лише поля задачі; `gitlab_cfg` без кореня й зі старим підписом — `TypeError`; ефективні `ssh_key`/`host_ip` (налаштування запису) = те, що давав корінь до міграції. `RegistrySshKey` (2): запис → типовий → ніколи корінь; нечитабельний реєстр/шар вимкнено → типовий. `TextsNameTheConnectionsScreen` (1): чотири тексти називають «Підключення» й не згадують `tasks.json`/`jira_base`/`JIRA_*`/`supabase_url`.
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_originals_gone.PreviewPasswordFromTheRecord tests.test_originals_gone.GitChainWithoutTheRoot tests.test_originals_gone.RegistrySshKey tests.test_originals_gone.TextsNameTheConnectionsScreen
  ```
  Очікувано (виміряно на базі `v0.20.0`): `PreviewPasswordFromTheRecord` — 4 з 6 червоних (`test_task_then_secret_then_default`, `test_the_root_password_is_ignored` — повертає `root-pw`, `test_isolated_run_in_a_temp_home_uses_the_fixture_secret`, `test_module_mode_does_not_use_the_legacy_secret_here` — `publish_password` ще нема); `GitChainWithoutTheRoot` — 2 з 3 (`TypeError` старих підписів `vcs_target`/`gitlab_cfg`); `RegistrySshKey` — 2 з 2 (`TypeError: _ssh_key() missing 1 required positional argument`); `TextsNameTheConnectionsScreen` — 1 з 1.
  JS: у `tests/connections-model.test.mjs` оновити чотири тести «наслідки вимкнення …»: ЛІГА (`integrations: true`) дає ті самі `kind: "none"`, що й інші (publish `cnNonePublish`; dashboard `cnNoneDashboard`; tracker `{noneKey: "cnNoneTracker", consKey: "cnDisableTracker"}`; notify `{noneKey: "cnNoneNotify", consKey: "cnDisableNotify"}`; vcs `cnNoneVcs`) — Поправка 3. `node --test tests/connections-model.test.mjs` → чотири червоні (виміряно: `pass 32 / fail 4` після правки коду).
- [ ] **Step 2: реалізація.** Hunk-и: `app/install_config.py` (−≈140 рядків читачів), `app/liga_migrate.py` (`+308,66` — копії `_supabase_from`/`_jira_from`; `+399,7` — три виклики), `app/serve.py` (`gitlab_cfg`, `_vcs_ssh`, `vcs_target`, `vcs_task`, `preview_password`, три місця виклику, видалення обгорток `supabase_config`/`jira_config`), `bin/registry.py` (`_ssh_key()`, виклик у `_git`), `ops/reseal_gate.py` (`liga_space()`), `app/connections-model.js` (прибрати `LEGACY_ROLES` і гілку `legacy` у `disableConsequences`, докстрінг), `app/modules/vercel-publish/module.json` (версія 1.3.0, підписи `compat`; діфф — Додаток Ж). Виправити закріплені: `test_liga_migrate_c.py:643`–`654`, `:1387`–`1401`, `test_vercel_publish.py:551`; ціль підміни `install_config.supabase_from` → `liga_migrate._supabase_from` у `test_liga_migrate_b.py` (`StepBPlanTest.test_bad_url_userinfo_is_not_migrated`, `…test_url_and_key_come_from_supabase_from`) і `test_liga_migrate.py` (`RunTest.test_userinfo_urls_are_not_migrated`) — Поправка 6. Оновити докстрінги `vcs_target`/`gitlab_cfg`/`preview_password`/`comment_scheme_legacy` (прототип лишив застарілі згадки кореня й `Implicit`).
- [ ] **Step 3:** нові тести Task 11 зелені; `node --test tests/connections-model.test.mjs` — 36 OK; `HOME=$(mktemp -d) python3 -B -m unittest tests.test_vercel_publish` — 186 OK (виміряно).
- [ ] **Step 4: мутації** (виміряно): `preview_password` дописати читання `load_legacy_tasks()['preview_password']` → `test_the_root_password_is_ignored` (+ `NoOriginalsRead`, Task 12); `_vcs_ssh` — запасний хід на корінь → `test_the_target_carries_only_the_tasks_own_fields`; `registry._ssh_key` — типовий ключ підмінити → `RegistrySshKey` (2 червоні); прибрати `real_home` з `publish_password` → `test_isolated_run_in_the_real_home_never_reads_the_shared_secret`.
- [ ] **Step 5: коміт.**

---

### Task 12: охоронці `NoOriginalsRead` і `NoImplicit`

**Files:** Create `tests/test_no_originals.py` (Додаток Г).

Після Task 4 (оригінали живуть лише в `liga_migrate`), Task 10 (`implicit` видалено) і Task 11 (читачі видалені). Охоронець — AST (за зразком `NoTracksAdapter`, `tests/test_no_adapter.py`): `NoOriginalsRead` — `app/**/*.py` (крім `liga_migrate.py`), `bin/*.py`, `ops/*.py` без `test_*` не мають рядкових констант `supabase_url`, `supabase_key`, `jira_base`, `jira_email`, `jira_token`, `gitlab_ssh_key`, `gitlab_host_ip`, `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_KEY`, `JIRA_EMAIL`, `JIRA_TOKEN`, підрядка `pipeline-feedback`, ані імен `supabase_from`, `jira_from`, `service_key_config`, `supabase_config`, `jira_config`, `legacy_ctx`, `legacy_module` (докстрінги не рахуються); `preview_password` — лише як `.get`/`.pop`/`[…]` на `task`/`t`/`(task or {})`, ключ літерала-словника (форма відповіді API) і імʼя функції; точний `ALLOWED = {(app/spaces.py, gitlab_host_ip), (app/spaces.py, gitlab_ssh_key), (app/serve.py, pipeline-feedback)}` (Поправка 4). `NoImplicit` — `app/implicit.py` нема, ніхто не імпортує `implicit`, імені `Implicit` нема (`implicit.<атрибут>` теж).

- [ ] **Step 1: тест (написаний уже в Додатку Г).** Запуск на дереві ПІСЛЯ Task 11:
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_no_originals
  ```
  Очікувано: 5 OK. **Доказ, що охоронець МОЖЕ впасти** (виміряно): на `v0.20.0` сканер знаходить порушення у 7 файлах (`app/dashboard.py`, `install_config.py`, `notify.py`, `serve.py`, `tracker.py`, `bin/overview_push.py`, `bin/registry.py`) для `NoOriginalsRead` і у 6 файлах (`deai_modules.py`, `implicit.py`, `install_config.py`, `liga_migrate.py`, `serve.py`, `bin/overview_push.py`) для `NoImplicit`; тести `test_the_guard_can_fail` перевіряють сім форм порушення (`cfg.get('supabase_url')`, `os.environ.get('JIRA_TOKEN')`, шлях `pipeline-feedback`, імпорт/виклик `supabase_from`, `def legacy_ctx`, `cfg.get('preview_password')`, `cfg['preview_password']`, `cfg.pop('preview_password')`) і чисті форми (`task.get(…)`, `t[…]`, `(task or {}).get(…)`, словник відповіді, докстрінг).
- [ ] **Step 2: мутації** (виміряно): додати `import implicit` у `app/serve.py` → `NoImplicit.test_no_implicit_provider`; додати читання `load_legacy_tasks()['preview_password']` → `test_the_runtime_does_not_read_originals`; додати `'supabase_url'` до `LEGACY_MARKERS` → `test_the_runtime_does_not_read_originals` (список винятків точний, а не «будь-що у файлі»).
- [ ] **Step 3: коміт** `tests/test_no_originals.py`.

---

### Task 13: хвиля 2 переписування тестів — провайдер, ролі, serve

**Files:** Modify/Retire тести за Додатком З, «Хвиля 2»; Modify `tests/test_implicit.py` (→ `IsolationCore` перенесено в Task 3; решта — за таблицею).

Мета: повернути до зеленого тести, червоні після Task 9–11 з причин «`Implicit` більше нема», «оригінали з кореня більше не діють», «видалені підписи/імена». Кожен клас — у таблиці відповідності Додатка З: що було → що тепер (новий тест, `ProviderWithoutImplicit…`, `IsolationCore`, фікстура) або «лишається без змін». **Нічого не видаляємо мовчки**: кожен ретайрений тест має рядок «замінено тестом X»; кожна зміна наявного тесту — одним рядком у звіті з причиною.

- [ ] **Step 1:** виміряти поточне червоне (по файлах, ізольовано): `for m in <список>; do HOME=$(mktemp -d) python3 -B -m unittest tests.$m 2>&1 | tail -3; done`. Перелік модулів і причина — Додаток З (за прототипом: 17 модулів не імпортуються через `import implicit`; в інших `TypeError: vcs_target() takes 3 positional arguments but 4 were given` тощо).
- [ ] **Step 2:** перекласти за рецептами Додатка З (R1–R6): `import implicit` → `import isolation`; твердження `Implicit` → `None`/«роль вимкнена»; облікові з кореня/оточення → `LigaFixture`; `preview_password(cfg, task)` → `(task, space)`; тексти. Особливі: `tests/test_implicit.py` — класи `Before4d2Shape`, `EffectiveSpace`, `LigaLikePin` лишаються (змінюється лише імпорт); `ImplicitCore` → `IsolationCore` (вже в `test_isolation.py`; клас видаляється з файла з рядком у таблиці); `ProviderImplicit` → «неявний простір → `None`, ЛІГА без запису → `None`» (дублюється `ProviderWithoutImplicit`; незаміщене переписується); `RolesParity` — на явній фікстурі; `PublishModule`, `NoLegacyLiteral` — підлаштувати; `IsolatedInstallConfig` (12) → «ізольований прогін не читає кореня; читає `module_ctx` лише в тимчасовому домі» (покрито `CommentsInIsolation`/`PreviewPasswordFromTheRecord`; решта 8 — за таблицею).
- [ ] **Step 3:** кожен переписаний файл ізольовано зелений; після всієї хвилі — `python3 "$G" 2400 3072 python3 -B -m unittest discover -s tests` (тимчасовий `HOME`): лишаються червоними лише модулі Task 14.
- [ ] **Step 4: коміт** по файлах/групах (pathspec), у звіті — таблиця відповідності.

---

### Task 14: хвиля 3 — vcs/gitlab, inbox/state, стенди міграції, `bin/*`

**Files:** Додаток З, «Хвиля 3»: `tests/test_vcs_core.py`, `tests/test_gitlab_sync.py`, `tests/test_inbox.py`, `tests/test_state.py`, `tests/test_liga_migrate.py`, `…_b.py`, `…_c.py`, `…_d.py`, `bin/test_overview_push.py`, `bin/test_registry.py`; живий/JS — за Task 16.

Виміряно на прототипі: `test_vcs_core` 232 червоних (77× `vcs_target() takes 3 positional arguments but 4 were given`, 35× `vcs_task() takes 2 positional arguments but 3 were given`, решта — наслідки у `setUp`), `test_gitlab_sync` 34, `test_state` 12, `test_inbox` 11, `test_liga_migrate` 9 (стенд `AfterMigrationParity` — `.adapter`/`implicit`), `test_liga_migrate_b` 3+9 `setUpClass`, `test_liga_migrate_d` 3 (піни п'яти кроків), `bin/test_overview_push.TestLegacyConfig` 6 (читач оригіналів — ретайрити: сервісний ключ з оточення більше не береться → «більше не береться» як новий тест).

- [ ] **Step 1:** `vcs_target(cfg, tid, task, settings)` → `vcs_target(tid, task, settings)`, `vcs_task(cfg, tid, task)` → `vcs_task(tid, task)`; тест «пріоритет ключа й IP — один для кожного шляху цілі» (`test_the_key_and_ip_priority_is_one_for_every_path_of_the_target`, 15) переписати: `own > налаштування модуля`; корінь — лише негативний assert. `test_the_gitlab_target_of_the_legacy_provider_is_the_070_result_byte_for_byte` (56) — еталон 0.7.0 тепер без ключа/IP кореня в цілі; значення беруться з налаштувань запису (фікстура): паритет ефективних значень.
- [ ] **Step 2:** стенди `test_liga_migrate*.py`: піни `STEPS` п'яти кроків; `AfterMigrationParity` (4d-3a), `…4d3b`, `…4d3c`, `…4d4a` — збір і очікування на явній фікстурі/мігрованій ЛІЗІ; їхні ЗНІМКИ (`before-4d3*.json`, `before-4d4a.json`) не чіпаємо. Якщо очікувана відмінність виникає з причини 4d-4b (напр. `provider.implicit_space`), вона НЕ додається у старі класи — вона належить `AfterMigrationParity4d4b`; старий клас тоді збирає розділ, не залежний від `Implicit`.
- [ ] **Step 3:** `bin/test_overview_push.py::TestLegacyConfig` (6) → ретайрити з рядками відповідності (усі шість стверджували читання оригіналів; замінює `DashboardSyncWithoutLegacy`); `bin/test_registry.py::TestTrack`/`TestFixturePathReason` — під тимчасовим `HOME`. ⚠️ `TestFixturePathReason.test_tmpdir_equal_to_home_does_not_poison_real_tasks` падає і на базі `v0.20.0` під тимчасовим `HOME` (виміряно на `p0` і `p1`) — не наслідок 4d-4b; у звіті окремо.
- [ ] **Step 4:** повний прогін Python: `python3 "$G" 2400 3072 python3 -B -m unittest discover -s tests` + `-s bin -p 'test_*.py'` + `-s app -p 'test_*.py'` (тимчасовий `HOME`) і під `/usr/bin/python3` (3.9). Очікувано: усе зелене, кількість тестів ≥ базової (4449) мінус ретайрені плюс нові (звіт: «було N, ретайрено M з таблицею, додано K»).
- [ ] **Step 5: коміт** по файлах/групах.

---

### Task 15: паритет після міграції `AfterMigrationParity4d4b`

**Files:** Create `tests/test_liga_parity_4d4b.py`, `tests/after_4d4b_collect.py` (Додаток Д).

Сценарії знімка `before-4d4b.json` на МІГРОВАНІЙ ЛІЗІ п'ятьма кроками, **НЕізольовано** (шлях власника: `DEAI_HOME` + реєстр, без `DC_TASKS_FILE`/`DC_NO_OVERVIEW`; живі тести ізольовані і цього не доводять). Колектор `after_4d4b_collect.py` — той самий код, що генератор знімка, з новими підписами (`vcs_target(tid, task, settings)`, `registry._ssh_key()`, `isolation.isolated()`) і порядком «A–D → підготовка `differs`/`partial` → Е» (Поправка 10). Очікуваний перелік відмінностей — **ТОЧНИЙ**: для кожного листка «було» береться зі знімка (`_expect`), «стало» — буквальне значення таблиці (Додаток Д: `EXPECT_REGULAR` 23 листки, `EXPECT_DIFFERS` 19, `EXPECT_PARTIAL` 40, `EXPECT_UNMIGRATED` 97, `EXPECT_PLAIN` 12; позиційні `root_keys` і `startup_text` — окремі буквальні списки).

- [ ] **Step 1: тест (червоний).** Створи `tests/test_liga_parity_4d4b.py` (14 тестів): мережі не було (`SocketTripwire`/`NoNet`, спроб не більше, ніж у знімку); п'ять стендів і розділи; точні відмінності на кожному стенді; `root_keys` буквально (після Е — `['current','design_work_root','design_work_roots','profile_repos','registry','tasks']` на `regular`; на `differs` лишаються `gitlab_ssh_key` і `jira_token`; на `partial` — `jira_*` і `supabase_*`; `unmigrated`/`plain` — без змін); рядки старту буквально (`regular`: п'ять кроків, «скопійовано…», «оригінали видалено…», один рядок відкату; `unmigrated`: п'ять `skip-held` і шість рядків «ролі ЛІГИ вимкнено …» із `unhold liga-4d3a`); **`test_expected_diff_is_exact_not_loose`** (зайвий листок і «очікувана зміна не сталась» червоніють на КОЖНОМУ стенді); що бачить людина на `regular` (лише три видимі поля `/api/modules`; `capabilities`, пароль превʼю, канал, ключ коментарів — рівно знімок); **Д4** (пароль `differs` — без відмінності: секрет перезаписано кореневим); ключ SSH `differs` — запис виграє, реєстр іде ним, корінь лишив `gitlab_ssh_key`; `unmigrated` — усі шість ролей `None`, пароль `1100`, `teams_mute` 409 `notify-off`, `comment_config` 409, `registry_ssh` — типовий.
  ```bash
  HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_parity_4d4b
  ```
  Очікувано до Task 4–11 (виміряно на v0.20.0): `AttributeError: module 'liga_migrate' has no attribute 'STEP_E'`; на повному дереві — 14 OK.
- [ ] **Step 2:** `tests/after_4d4b_collect.py` — Додаток Д (діф до генератора: `_stand` біжить `lm.run(step=s)` для `ALL_STEPS[:4]`, готує `differs`/`partial`, потім Е; `vcs_target('a-1', task, settings)`; `registry._ssh_key()`; `serve.isolation.isolated()`; `collect_all()` повертає `{стенд: розділи, '_wire': лічильник}`).
- [ ] **Step 3: мутації** (по одній): прибрати з Е видалення `jira_base` → `EXPECT_REGULAR`/`ROOT_AFTER` червоніють; у `preview_password` повернути корінь → `unmigrated.api.task.preview_password` (`1100` → `pw-alpha`) і `test_what_a_person_sees_regular`; повернути `Implicit` в `_provider_for` → `provider.implicit_space.*` у всіх п'яти таблицях.
- [ ] **Step 4: коміт** `tests/test_liga_parity_4d4b.py tests/after_4d4b_collect.py`.

---

### Task 16: живі тести, документи, версія 0.21.0

**Files:** Modify `tests/live/{fixture,_liga-supabase,liga-migrate,comments,dashboard-role,tracker-role,notify-role,teams-mute,tasks-home,preview-password,git-sync,legacy-publish-cli}.mjs` (+ перевірка `canvas`, `comment-audience`, `inspector-project`, `overview-comments`, `shell-typing` — по одній згадці), `tasks.example.json` (за потреби), `README.md`, `CHANGELOG.md`, `package.json`, `docs/design/spaces-and-modules.md`.

**Живі.** `tests/live/fixture.mjs`: `startServer(…, { supabase: true })` більше не пише `LIGA_SUPABASE` у корінь — будує **мігровану ЛІГУ**: явні записи через `isolatedMachine` (форма — та сама, що `LigaFixture.build()`: шість ролей у `space.json`, `secrets.json` 0600, корінь без облікових) АБО запускає справжню міграцію через `DC_MIGRATE_LIGA=1` з `deaiDir` ≠ `.deai` (`<HOME>/.deai` сервер вважає «справжнім» — відмова); `legacyExtra` лишається ТІЛЬКИ для тестів міграції. `_liga-supabase.mjs` — перехоплення без змін (мережі нема). `liga-migrate.test.mjs` — п'ятий крок, `unhold`, друк вимкнених ролей. `preview-password.test.mjs` — секрет замість кореня. `git-sync.test.mjs`/`legacy-publish-cli.test.mjs` — `ssh_key` із запису. Живі тести ізольовані → доводять ізольований шлях; шлях власника доводить `AfterMigrationParity4d4b` (Task 15).

- [ ] **Step 1:** по одному файлу, послідовно, під тимчасовим `HOME` (завдяки Task 2 без ручних змінних): `HOME=$(mktemp -d) node --test --test-concurrency=1 tests/live/<файл>.test.mjs`; кожен файл спершу ЧЕРВОНИЙ на новому коді (старі фікстури пишуть оригінали в корінь) → перевести → зелений. Перед фінальним ревʼю — повний `npm run test:live` ПОСЛІДОВНО (`--test-concurrency=1`, а не `4` із `package.json`).
- [ ] **Step 2: документи.** `package.json` `0.21.0`; `CHANGELOG.md` `## [0.21.0] — <дата випуску>` (англійською, як усі записи): п'ятий крок `liga-4d4b`; рантайм без оригіналів; `Implicit` видалено; немігрована ЛІГА — шість ролей вимкнені, старт і `status` їх називають; `unhold`; закон ізоляції в `app/isolation.py`; Д4 (перезапис інертного пароля); «Known limits»: єдина копія облікових у домі Deai (`secrets.json` + `backups/`), `tasks.json.bak` — ручний відкат, ключ кореня `preview_password` ЗВИЧАЙНОГО простору більше не діє (Поправка 5), `skip-path-in-git` — ролей не повернути, поки тека простору в робочому дереві git; відкат 0.21 → 0.20 — **обовʼязково** `restore <stamp-E> --hold`. `README.md` — рядки про `supabase_url`/`jira_base`/оточення/`pipeline-feedback` (приблизно 335–338, 472–474, 594–598, 628, 695–697): облікові вносяться на екрані «Підключення», старі джерела не читаються, мапа «ключ → тримач» (спека §5: налаштування `git-sync` `ssh_key`/`host_ip`, секрет `password` `vercel-publish`). `docs/design/spaces-and-modules.md` — 4d-4b зроблено, 4d-4c — далі. `tasks.example.json` — без змін (оригіналів там нема).
- [ ] **Step 3: перевірка відсутності витоків** у всіх комітованих файлах: `git diff --cached | grep -nE "$(basename "$HOME")|<префікс домашніх тек macOS>|<префікс тимчасових тек macOS>"` → нуль.
- [ ] **Step 4: коміти** по файлах/групах; пакетний коміт релізу (`package.json`, `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`) — останній.

---

## Таблиця мутацій (кожна має червоніти; `python3 -B`, файл відновлюється, `sha256` до/після збігається)

Виміряно на прототипі (`✓` — червоніє; рядок — які саме тести).

| № | Мутація (один рядок) | Файл | Червоніє (названий тест) | Задача |
|---|---|---|---|---|
| M1 | видаляти завжди (`if equal:` → `if True:`) | `liga_migrate._decide_originals` | `PlanE.test_differs_keeps_root_and_does_not_overwrite`, `RunE.test_a_person_changed_a_setting_between_copy_and_delete_keeps_that_key` ✓ | 4 |
| M2 | прибрати `abort-verify` (`if not ok:` → `if False:`) | `_run_originals` | `RunE.test_abort_verify_when_the_copy_does_not_read_back` ✓ | 5 |
| M3 | прибрати свіже рішення під локом (`and k in fresh['remove']`) | `_commit_originals` | `RunE.test_a_person_changed_a_setting_between_copy_and_delete_keeps_that_key` ✓ (після переписування тесту; старіша версія — вижила) | 5 |
| M4 | пропустити охоронець маркера (`if had_markers:` → `if False:`) | `_decide_originals` | `PlanE.test_marker_guard_keeps_one_marker_key`, `…uses_ssh_key_when_it_is_the_only_marker` ✓ | 4 |
| M5 | прибрати нотатку `partial:supabase` | `_decide_originals` | `PlanE.test_supabase_pair_is_all_or_nothing` ✓ | 4 |
| M6 | зняти «все або нічого» для пари Supabase (`if missing:` → `if False:`) | `_decide_originals` | `PlanE.test_supabase_pair_is_all_or_nothing` ✓ | 4 |
| M7 | `restore` перезаписує файл цілком (`cur = dict(old)`) | `_restore_root` | `RestoreE.test_restore_merges_removed_keys_back_and_keeps_live_edits`, `…never_rewrites_the_whole_file` ✓ | 6 |
| M8 | `restore` без звіряння `_file_sig` | `_restore_root` | `RestoreE.test_restore_aborts_when_the_live_file_keeps_changing` ✓ (після дописування тесту; раніше — вижила) | 6 |
| M9 | `roles_state`: `held` ігнорується | `_reason_from_reports` | `RolesState.test_held_step_names_unhold`, `…early_step_held_names_the_early_mark_for_later_owners` ✓ | 7 |
| M10 | `preview_password` знову читає корінь | `serve.preview_password` | `PreviewPasswordFromTheRecord.test_the_root_password_is_ignored`, `NoOriginalsRead.test_the_runtime_does_not_read_originals` ✓ | 11/12 |
| M11 | `import implicit` повернуто | `serve.py` | `NoImplicit.test_no_implicit_provider` ✓ (+ імпорт-помилка `test_originals_gone`) | 12 |
| M12 | `_vcs_ssh`: запасний хід на корінь | `serve._vcs_ssh` | `GitChainWithoutTheRoot.test_the_target_carries_only_the_tasks_own_fields` ✓ | 11 |
| M13 | новий літерал оригіналу (`'supabase_url'` у `LEGACY_MARKERS`) | `spaces.py` | `NoOriginalsRead.test_the_runtime_does_not_read_originals` ✓ (перелік винятків точний) | 12 |
| M14 | прибрати `real_home` з `comments_route` | `serve.comments_route` | `CommentsInIsolation.test_real_home_is_refused` ✓ | 10 |
| M15 | прибрати `real_home` з `publish_password` | `deai_modules.publish_password` | `PreviewPasswordFromTheRecord.test_isolated_run_in_the_real_home_never_reads_the_shared_secret` ✓ | 11 |
| M16 | `registry._ssh_key`: підмінити типовий ключ | `bin/registry.py` | `RegistrySshKey` (2 червоні) ✓ | 11 |
| M17 | `route`: порядок «ізоляція раніше за шов» | `isolation.route` | `IsolationCore.test_route_order_fake_then_isolated_then_live` | 3 |
| M18 | `real_home` за `$HOME` замість `pwd` | `isolation.real_home` | `IsolationCore.test_real_home_is_the_pwd_home_not_the_HOME_variable` | 3 |
| M19 | `_provider_for`: порожньо явних → повертає щось | `deai_modules` | `ProviderWithoutImplicit.test_a_liga_role_without_a_record_is_none` | 9 |
| M20 | колектор паритету: `EXPECT_*` без однієї відмінності | `test_liga_parity_4d4b` | `test_exact_differences_<стенд>` і `test_expected_diff_is_exact_not_loose` | 15 |

M17, M18, M19, M20 — з тестів, що в прототипі зелені; мутації для них доводить виконавець (у прототипі вимірювалися M1–M16).

## Після всіх задач (контролер)

1. Повний прогін у такому порядку, кожен з `$G` і тимчасовим `HOME`: Python `unittest discover -s tests`, `-s bin -p 'test_*.py'`, `-s app -p 'test_*.py'`; під `/usr/bin/python3` (3.9); `npm test`; `npm run test:live` ПОСЛІДОВНО (`--test-concurrency=1`). Усе зелене; еталони (`legacy-golden`, `GoldenPinTest`, знімки `before-*`) — без `UPDATE_*`; `ls ~/deai-work ~/.deai` не змінились.
2. **Наскрізний аудит** (окремий субагент, не виконавець): перелік змінних файлів ↔ Поправки; `git diff v0.20.0 -- app bin ops | grep -nE "supabase_url|supabase_key|jira_base|jira_email|jira_token|gitlab_ssh_key|gitlab_host_ip|SUPABASE_|JIRA_|pipeline-feedback|implicit"` — лише `liga_migrate.py`, `spaces.py` (`LEGACY_MARKERS`) і `serve.py` (`OVERVIEW_LOG`); перевірка «охоронці можуть впасти» (мутації M10–M13); аудит викликів `provider()` (Поправка 11).
3. **Reality-check перед релізом на машині власника:** `python3 bin/migrate_liga.py status` — чи всі п'ять кроків застосовані; за Р2 спеки (рішення контролера 07.11.2026) на машині власника файла задач ЛІГИ у робочій установці Deai нема, тож кроки A–Е реально спрацюють у день заміни інструмента ЛІГИ на Deai, а не на першому старті 0.21. Перевірка `status` — частина того дня, а не цього релізу. Відкат: `restore <stamp-E> --hold`, далі за потреби `d`, `c`, `b`, `a`.
4. Версія/CHANGELOG/тег `v0.21.0` — після зеленого фінального ревʼю; не пушити без дозволу контролера; перепублікація превʼю ЛІГИ — окремий follow-up (як у 0.17–0.20).
5. Памʼять проєкту (`project-deai-opensource`): додати «v0.21.0 4d-4b: …» (оригінали видалено, `Implicit` видалено, `isolation.py`, `unhold`, п'ять кроків; далі 4d-4c = 0.22.0).


---

## Додаток З: тести, які змінює цей етап (таблиці відповідності)

Джерело: прототип (повний прогін на `p1`: `Ran 2109 tests … failures=81, errors=275`, ще 17 модулів не імпортуються; база `v0.20.0`: `Ran 4449 tests … OK (skipped=2)`) + підрахунок спеки (Додаток Б спеки). Рецепти:

- **R1** — `import implicit` → `import isolation` (закон ізоляції, шви); імена `implicit.route(...)` → `isolation.route(<роль>)`.
- **R2** — твердження «роль веде `Implicit`/`'legacy'`» → «роль вимкнена: `None`» (або ЯВНИЙ запис через `LigaFixture`).
- **R3** — облікові з кореня/оточення (`supabase_*`, `jira_*`, `JIRA_*`) → `LigaFixture(self).env().build(...)` (прямі записи) чи `.migrate()` (справжня міграція).
- **R4** — `serve.vcs_target(cfg, …)`/`vcs_task(cfg, …)`/`gitlab_cfg(cfg, …)`/`preview_password(cfg, task)` → нові підписи без `cfg` (`preview_password(task, space)`).
- **R5** — тексти «не налаштовано» → нові (Поправка 8).
- **R6** — ретайр із рядком відповідності (що замінює).

### Хвиля 1 (Task 8, ДО видалення; на старому коді зелено, див. застереження в Task 8)

| Файл | Було (джерело облікових/шву) | Рецепт |
|---|---|---|
| `tests/sbconf.py` | `write_root`/`drop_root`/`ENV` | R3: фабрика запису через `LigaFixture`; старі імена лишаються тонкими обгортками до Task 13 |
| `tests/test_legacy_comments.py` (44) | корінь + `Implicit` | R3 |
| `tests/test_dashboard.py` (25+3) | корінь, `legacy_ctx` | R3 (виклики `legacy_ctx` — Task 13) |
| `tests/test_tasks_overview.py` (14+2+20 швів) | корінь, `DC_*_FAKE` | R3; шви лишаються (`isolation.route`) |
| `tests/test_inbox.py` (9), `tests/test_comments_agent.py` (9), `tests/test_comments_role.py` (8+13 `Implicit`), `tests/test_integrations_off.py` (7), `tests/test_spaces_serve.py` (6), `tests/test_publish_module.py` (6+15 `preview_password`+12 `Implicit`), `tests/test_modules.py` (3+25 `Implicit`), `tests/test_tracker.py` (32 jira), `tests/test_notify.py`, `tests/test_state.py`, `tests/test_supabase_comments.py`, `tests/test_task_tags.py`, `tests/test_tracks.py` | корінь/оточення/`Implicit` | R3 там, де сценарій «облікові → роль працює»; твердження про `Implicit` — до Task 13 |

### Хвиля 2 (Task 13): модулі, що не імпортуються після Task 9–11 (`ModuleNotFoundError: No module named 'implicit'`), і місцеві падіння

| Модуль тестів | Причина (виміряно) | Рецепт |
|---|---|---|
| `test_implicit` | `import implicit` | див. розбір нижче |
| `test_modules`, `test_modules_own`, `test_modules_trust_api`, `test_css_tokens`, `test_static_publish`, `test_vercel_integration`, `test_publish_module`, `test_supabase_comments` | `import implicit` / `Implicit` у `provider()` | R1+R2; `test_publish_module` ще R4 (`preview_password`) |
| `test_comments_role`, `test_comments_agent`, `test_legacy_comments` | `import implicit`, `legacy_ctx`, `ProjectComments.kind == 'implicit'` | R1+R2+R3; ізольовані сценарії → `CommentsInIsolation`-подібні (тимчасовий дім) |
| `test_dashboard`, `test_tracker`, `test_notify`, `test_tasks_overview` | `import implicit`, `legacy_ctx`/`legacy_module`, `supabase_config` | R1+R3+R5 |
| `test_integrations_off` (17) | `Implicit` для просторів з інтеграціями | R2 |
| `test_modules_api` (6) | `'legacy'` у `capabilities` | R2 (`None`), JS-ключі без змін |
| `test_spaces_serve`, `test_serve` | `setUpModule`: імпорт `implicit`/`supabase_config` | R1; `TestsCannotWriteLiveConfig` — без змін |
| `test_liga_migrate_c` | `import implicit`, версія/підпис `vercel-publish` | R1; Поправка 7 |

**Розбір `tests/test_implicit.py`** (клас → доля; нічого не губимо):

| Клас (тестів) | Доля |
|---|---|
| `Before4d2Shape` (9), `EffectiveSpace` (4), `LigaLikePin` (1) | лишаються (R1: імпорт); знімок `before-4d2.json` — еталон 0.15 |
| `ImplicitCore` (11) | `test_roles_order`, `test_singleton_and_immutable`, `test_table`, `test_module_ids_match_real_code`, `test_unknown_role` → R6 (`Implicit` видалено; таблиця шви — `IsolationCore.test_fake_env_table_is_the_old_one`, ролі — `liga_migrate.LIGA_ROLES`); `test_isolated_truth_table` → `IsolationCore.test_isolated_is_tasks_file_or_no_overview`; `test_route_fake_wins_even_isolated`, `test_route_isolated_and_live` → `IsolationCore.test_route_order_fake_then_isolated_then_live`; `test_route_empty_fake_is_absent` → `IsolationCore.test_an_empty_seam_is_absent`; `test_route_not_shared_is_live_when_isolated` → R6 (параметр `shared` завжди був `True`; ролі без шва — `IsolationCore.test_roles_without_a_seam_are_only_isolated_or_live`); `test_no_serve_import` → `IsolationCore.test_imports_nothing_but_os` |
| `ProviderImplicit` (11) | `test_layer_off_is_implicit_without_reads` → `ProviderWithoutImplicit.test_layer_off_has_no_roles` (інвертовано); `test_unfixed_request_space_is_implicit_without_reads` → `…test_an_unpinned_request_space_has_no_roles`; `test_provider_none_when_no_space`, `test_provider_uses_effective_space_seam`, `test_explicit_space_does_not_use_seam`, `test_provider_for_implicit_space_does_not_read_space_json_in_cwd`, `test_provider_for_plain_space_without_integrations_has_no_implicit` → лишаються (R2: `None`); `test_provider_for_integrations_space_returns_implicit` → `…test_a_liga_role_without_a_record_is_none` (інвертовано); `test_role_constants_renamed` → R6 (`test_the_core_has_no_fallback_names`); `test_api_value` → лишається без випадку `Implicit` + `TypeError` для `'legacy'`; `test_capabilities_match_before_4d2_snapshot` → переписати на `LigaFixture` (значення `'legacy'` у знімку 4d-2 — еталон 0.15, а не вимога) |
| `RolesParity` (5) | R3: явна фікстура; `route` через `isolation` |
| `PublishModule` (4) | `test_implicit_none_and_failures_are_none` → R2 (`None`); решта лишається |
| `NoLegacyLiteral` (3) | `test_implicit_is_not_the_public_string` → R6 (`Implicit` нема); решта — лишається (літерал `'legacy'` живе до 4d-4c) |
| `IsolatedInstallConfig` (12) | `…supabase_isolated_ignores_env_when_root_has_no_pair`, `…takes_the_root_pair_not_the_env`, `…jira_isolated_without_root_credentials…`, `…jira_isolated_takes_the_full_triple…`, `…service_key_isolated_is_none…`, `…service_key_outside_isolation_is_the_0_15_0_pair`, `…outside_isolation_matches_the_0_15_0_snapshot` → R6 (читачі видалені; їх замінюють `CommentsInIsolation`, `PreviewPasswordFromTheRecord`, `NoOriginalsRead`); `…supabase_root_pair_form_is_checked`, `…jira_root_credentials_need_both_and_the_same_form_as_env`, `…outside_isolation_the_root_credentials_are_ignored_and_env_and_files_work`, `…isolation_cuts_exactly_the_env_and_files_sources_of_the_snapshot` → переносяться до `tests/test_liga_migrate.py` як клас `OriginalsReadersCopy` проти `liga_migrate._supabase_from`/`_jira_from` (ті самі твердження; джерела — міграція ще читає оригінали); `…test_no_import_cycle` → `IsolationCore.test_imports_nothing_but_os` |

### Хвиля 3 (Task 14)

| Файл | Причина (виміряно) | Рецепт |
|---|---|---|
| `test_vcs_core` (232 червоних) | 77× `vcs_target() takes 3 positional arguments but 4 were given`, 35× `vcs_task() takes 2 positional arguments but 3 were given`, решта — каскад `setUp` | R4; ключі кореня (`gitlab_ssh_key` ×11) → налаштування запису `git-sync` через `LigaFixture(overrides={'vcs': {'settings': {...}}})` |
| `test_gitlab_sync` (34) | `vcs_target`/`gitlab_cfg` | R4 |
| `test_state` (12), `test_inbox` (11) | `ProjectComments.kind == 'implicit'`, `legacy_ctx`, оригінали | R1+R2+R3 |
| `test_liga_migrate` (9), `…_b` (3+9 `setUpClass`), `…_d` (3) | стенд `AfterMigrationParity` (`.adapter`, `implicit`), піни `STEPS` | R1; піни п'яти кроків; знімки 4d-3/4d-4a не чіпаємо |
| `bin/test_overview_push.py::TestLegacyConfig` (6) | `_legacy_config`/`service_key_config` видалено | R6: `…isolated_run_never_takes_the_service_key_from_the_environment`, `…neither_is_unconfigured_and_cli_names_it_without_values`, `…no_file_pair_the_service_key_pair_from_the_environment`, `…the_file_of_the_installation_wins`, `…the_service_key_never_reaches_supabase_config`, `…the_service_key_without_a_url_is_nothing` → усі шість замінює `DashboardSyncWithoutLegacy` (сервісний ключ з оточення більше не береться; без запису дашборда — «нема постачальника») |
| `bin/test_registry.py` | `_ssh_key(cfg)` | R4: `RegistrySshKey`; тимчасовий `HOME` |

### Не чіпаємо (еталони й заморожені знімки)

`tests/fixtures/liga-migration/before-4d3a/3b/3c/4d4a.json`, `tests/fixtures/implicit/before-4d2.json`, `tests/make_before_4c*/4d1/4d2/4d3a/4d3b/4d3c/4d4a.py` (генератори НЕ переганяються; їхні читачі в тестах — на явну фікстуру там, де знімок зроблено з неявної ЛІГИ). Нові: `before-4d4b.json` + `make_before_4d4b.py`.

### Живі й JS (Task 11, Task 16)

`tests/connections-model.test.mjs` — чотири «наслідки вимкнення …» (Task 11); `tests/live/*.mjs` — Task 16 (список там).

---

## Додаток Ж (вступ): прототипні hunk-и

Нижче — унифіковані diff-и «`v0.20.0` → прототип» кожного змінюваного файла коду (мітки `a/`, `b/` відносно кореня репо), у порядку задач: ядро кроку Е (`app/liga_migrate.py`, `bin/migrate_liga.py`), провайдер і ізоляція (`app/deai_modules.py`), споживачі (`app/serve.py`, `app/dashboard.py`, `app/notify.py`, `app/tracker.py`, `bin/overview_push.py`, `bin/state.py`), читачі оригіналів (`app/install_config.py`, `bin/registry.py`, `ops/reseal_gate.py`), маніфест і JS. Новий файл `app/isolation.py` — повним текстом. Застарілі докстрінги, які прототип лишив (`vcs_target`, `gitlab_cfg`, `preview_password`, `comment_scheme_legacy`), виконавець оновлює. Номери рядків у `@@` — за прототипом; застосовуй за вмістом.


---

# Додатки (повні тексти прототипу)

Кожен файл нижче — дослівний результат прототипу, прогнаного поверх `git archive v0.20.0` (поза репо, з тимчасовим `HOME`). Створюй файли рівно за цими текстами (`Write`), а hunk-и коду застосовуй через `Edit` за вмістом.


## Додаток А: `tests/test_liga_migrate_e.py` (58 тестів: `PlanE` 18, `RunE` 12, `RestoreE` 7, `RolesState` 13, `StartupE` 3, `StatusAndCli` 5; джерело для Task 4–7)

````python
"""Етап 4d-4b: п'ятий крок міграції ЛІГИ `liga-4d4b` — останні оригінали кореня `tasks.json` (копія в запис і видалення з кореня)."""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from test_liga_migrate import _WriteStand  # noqa: E402


class _StandE(_WriteStand):
    """Стенд кроку Е: простір ЛІГА з УЖЕ мігрованими A–C записами (рівні оригіналам) і коренем з усіма вісьмома ключами."""

    SSH, HOSTIP, PW = '~/.ssh/id_example', '203.0.113.7', 'pw-alpha'
    ALL = ('supabase_url', 'supabase_key', 'jira_base', 'jira_email', 'jira_token', 'gitlab_ssh_key', 'gitlab_host_ip', 'preview_password')

    def setUp(self):
        super().setUp()
        self.secret_values = (self.SB_KEY, self.JIRA_TOKEN, self.PW)
        self.lm_steps = self.mock.patch.object(self.lm, 'STEPS', self.lm.ALL_STEPS)
        self.lm_steps.start()
        self.addCleanup(self.lm_steps.stop)
        self.E = self.lm.STEP_E
        self.rec_all()

    # --- стенд
    def rec_all(self, **over):
        """Явні записи A–C (рівні кореню) + `secrets.json`; `over` — заміна окремих частин: `mods`, `secrets`."""
        mods = {
            'supabase-dashboard': {'enabled': True, 'shared_state': True, 'settings': {'url': self.SB_URL, 'table': 'overview_projects', 'compat': 'comment-layer'}},
            'supabase-teams': {'enabled': True, 'shared_state': True, 'settings': {'url': self.SB_URL, 'compat': 'comment-layer'}},
            'supabase-comments': {'enabled': True, 'shared_state': True, 'settings': {'url': self.SB_URL, 'shots_bucket': 'overview-thumbs', 'compat': 'comment-layer'}},
            'jira-tracker': {'enabled': True, 'shared_state': True, 'settings': {'base': self.JIRA_BASE, 'email': self.JIRA_EMAIL}},
            'git-sync': {'enabled': True, 'shared_state': True, 'settings': {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True, 'compat': 'design-canvas'}},
            'vercel-publish': {'enabled': True, 'shared_state': True, 'settings': {'auth': 'cli', 'team': '', 'compat': 'design-canvas'}},
        }
        mods.update(over.get('mods', {}))
        for k in over.get('drop', ()):
            mods.pop(k, None)
        self.space_json({'name': 'Liga', 'modules': mods, 'migrations': over.get('migrations', {})})
        sec = {'supabase-dashboard': {'key': self.SB_KEY}, 'supabase-teams': {'key': self.SB_KEY}, 'supabase-comments': {'key': self.SB_KEY},
               'jira-tracker': {'token': self.JIRA_TOKEN}}
        sec.update(over.get('secrets', {}))
        self._write(self.secrets_path(), {'legacy': sec})
        os.chmod(self.secrets_path(), 0o600)

    def root(self, **extra):
        """Корінь `tasks.json` ЛІГИ: усі вісім ключів (`extra` — заміна/додавання; `None` — прибрати ключ)."""
        cfg = self.config(supabase=False, jira=False)
        cfg.update(supabase_url=self.SB_URL, supabase_key=self.SB_KEY, jira_base=self.JIRA_BASE, jira_email=self.JIRA_EMAIL,
                   jira_token=self.JIRA_TOKEN, gitlab_ssh_key=self.SSH, gitlab_host_ip=self.HOSTIP, preview_password=self.PW,
                   registry={'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'})     # `registry` — маркер ЛІГИ, що лишається (як на справжніх машинах)
        for k, v in extra.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        self.cfg = cfg
        self._write(self.tasks_path, cfg)
        return cfg

    def run_e(self):
        return self.lm._run(None, self.E)

    def mark(self):
        return self.read_json(self.space_path())['migrations'][self.E.mark]

    def tasks(self):
        return self.read_json(self.tasks_path)


class PlanE(_StandE):
    def test_regular_all_eight_removed_two_copied(self):
        self.root()
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'ready')
        d = p['originals']
        self.assertEqual(sorted(d['remove']), sorted(self.ALL))
        self.assertEqual(sorted(d['copied']), ['gitlab_host_ip', 'gitlab_ssh_key', 'preview_password'])
        self.assertEqual(d['notes'], [])
        self.assertEqual(p['roles'], {})
        self.assertEqual(p['space_json']['migrations']['liga-4d4b']['roles'], [])

    def test_plan_is_pure(self):
        self.root()
        before = self.snapshot_tree()
        self.lm.plan(step=self.E)
        self.assertEqual(self.snapshot_tree(), before)

    def test_nothing_to_do_is_skip_nothing(self):
        self.root(**{k: None for k in self.ALL})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-nothing')

    def test_notes_alone_are_not_skip_nothing(self):
        self.root(**dict({k: None for k in self.ALL}, jira_base='https://example.com/x'))          # непридатна форма (шлях)
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'ready')
        self.assertEqual(p['notes'], ['unfit:jira_base'])

    def test_unfit_values_stay(self):
        self.root(supabase_key='has space', jira_email='  ', gitlab_host_ip=7, preview_password=True)
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['notes']), ['unfit:gitlab_host_ip', 'unfit:jira_email', 'unfit:preview_password', 'unfit:supabase_key'])
        for k in ('supabase_key', 'jira_email', 'gitlab_host_ip', 'preview_password'):
            self.assertIn(k, d['kept'])
            self.assertNotIn(k, d['remove'])

    def test_missing_holder_keeps_key(self):
        self.rec_all(drop=('jira-tracker',))
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['kept']), ['jira_base', 'jira_email', 'jira_token'])
        self.assertIn('no-record:jira-tracker', d['notes'])

    def test_disabled_or_not_shared_holder_is_not_a_holder(self):
        self.rec_all(mods={'git-sync': {'enabled': False, 'shared_state': True, 'settings': {}}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['kept']), ['gitlab_host_ip', 'gitlab_ssh_key'])
        self.rec_all(mods={'git-sync': {'enabled': True, 'settings': {}}})
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(sorted(d['kept']), ['gitlab_host_ip', 'gitlab_ssh_key'])

    def test_supabase_pair_is_all_or_nothing(self):
        self.rec_all(drop=('supabase-teams',))
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('partial:supabase', d['notes'])
        self.assertIn('no-record:supabase-teams', d['notes'])
        self.assertEqual(sorted(k for k in d['kept'] if k.startswith('supabase')), ['supabase_key', 'supabase_url'])
        self.assertIn('jira_base', d['remove'])                      # решта оригіналів — незалежно

    def test_differs_keeps_root_and_does_not_overwrite(self):
        self.rec_all(mods={'git-sync': {'enabled': True, 'shared_state': True, 'settings': {'ssh_key': '/other/key', 'compat': 'design-canvas'}}},
                     secrets={'jira-tracker': {'token': 'other-token'}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('differs:gitlab_ssh_key', d['notes'])
        self.assertIn('differs:jira_token', d['notes'])
        self.assertIn('gitlab_ssh_key', d['kept'])
        self.assertNotIn('git-sync', d['copy_settings'].get('git-sync', {}) and ['x'] or ['git-sync'])
        self.assertNotIn('ssh_key', d['copy_settings'].get('git-sync', {}))
        self.assertIn('host_ip', d['copy_settings']['git-sync'])       # порожнє поле копіюється й тоді, коли сусіднє відрізняється

    def test_password_conflict_is_overwritten_with_the_root(self):                    # Д4
        self.rec_all(secrets={'vercel-publish': {'password': 'inert-old'}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': self.PW}})
        self.assertIn('overwrote:password', d['notes'])
        self.assertIn('preview_password', d['remove'])

    def test_password_needs_design_canvas_compat(self):
        self.rec_all(mods={'vercel-publish': {'enabled': True, 'shared_state': True, 'settings': {'auth': 'cli', 'compat': ''}}})
        self.root()
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('preview_password', d['kept'])
        self.assertIn('no-record:vercel-publish', d['notes'])

    def test_numeric_password_is_stringified(self):
        self.root(preview_password=4321)
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['copy_secrets'], {'vercel-publish': {'password': '4321'}})

    def test_url_normalised_before_comparison(self):
        self.root(supabase_url=' %s/ ' % self.SB_URL, supabase_key=' %s ' % self.SB_KEY)
        self.assertIn('supabase_url', self.lm.plan(step=self.E)['originals']['remove'])
        self.assertIn('supabase_key', self.lm.plan(step=self.E)['originals']['remove'])

    def test_marker_guard_keeps_one_marker_key(self):
        self.root(registry=None)                                      # маркерів, окрім `gitlab_*`, у корені нема
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('marker-kept:gitlab_host_ip', d['notes'])
        self.assertIn('gitlab_host_ip', d['kept'])
        self.assertNotIn('gitlab_host_ip', d['remove'])

    def test_marker_guard_silent_when_registry_key_present(self):
        self.root(registry={'head': 'abc'})
        d = self.lm.plan(step=self.E)['originals']
        self.assertEqual(d['notes'], [])
        self.assertIn('gitlab_host_ip', d['remove'])

    def test_marker_guard_uses_ssh_key_when_it_is_the_only_marker(self):
        self.root(gitlab_host_ip=None, registry=None)
        d = self.lm.plan(step=self.E)['originals']
        self.assertIn('marker-kept:gitlab_ssh_key', d['notes'])

    def test_gates(self):
        self.root()
        self.space_json({'modules': {}, 'migrations': {'liga-4d4a': {'held': True}}})
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'skip-held')                   # held раннього кроку тримає Е
        self.space_json({'modules': {}, 'migrations': {'liga-4d4b': {'at': 'x'}}})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-done')
        self.space_json({'modules': {}, 'migrations': {'liga-4d4b': {'held': True}}})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-held')

    def test_provider_unchanged_check(self):
        self.root()
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'ready')                        # запис git-sync з новими налаштуваннями лишається тим самим постачальником


class RunE(_StandE):
    def test_run_copies_verifies_removes_then_marks(self):
        self.root()
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        t = self.tasks()
        for k in self.ALL:
            self.assertNotIn(k, t)
        self.assertEqual(sorted(t['tasks']), ['a-1', 'a-2'])          # решта файла — як була
        self.assertIn('design_work_root', t)
        sj = self.read_json(self.space_path())
        self.assertEqual(sj['modules']['git-sync']['settings']['ssh_key'], self.SSH)
        self.assertEqual(sj['modules']['git-sync']['settings']['host_ip'], self.HOSTIP)
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish'], {'password': self.PW})
        m = self.mark()
        self.assertEqual((m['roles'], m['copied'], m['kept'], m['notes']),
                         ([], ['gitlab_host_ip', 'gitlab_ssh_key', 'preview_password'], [], []))
        self.assertEqual(sorted(m['removed']), sorted(self.ALL))
        self.assertTrue(m['backup'].endswith('-liga-4d4b'))
        self.assert_no_secrets_in_logs()

    def test_mark_is_written_last(self):
        self.root()
        order = []
        real_commit, real_space = self.lm._commit_originals, self.lm._commit_space
        self.mock.patch.object(self.lm, '_commit_originals', lambda *a, **k: order.append('root') or real_commit(*a, **k)).start()
        self.mock.patch.object(self.lm, '_commit_space', lambda *a, **k: order.append('mark') or real_space(*a, **k)).start()
        self.addCleanup(self.mock.patch.stopall)
        self.run_e()
        self.assertEqual(order, ['root', 'mark'])

    def test_backup_and_dot_bak_hold_the_bytes_before(self):
        self.root()
        before = self.read(self.tasks_path)
        _st, info = self.run_e()
        self.assertEqual(self.read(self.deai, 'backups', info['backup'], 'tasks.json'), before)
        self.assertEqual(self.read(self.tasks_path + '.bak'), before)

    def test_abort_before_backup_when_tasks_unwritable(self):
        self.root()
        before = self.snapshot_tree()
        with self.mock.patch.object(self.lm, '_records_writable', lambda p: False):
            st, _info = self.run_e()
        self.assertEqual(st, 'abort-originals')
        self.assertEqual(self.tree_without_logs(), {k: v for k, v in before.items() if os.sep + 'migrations' + os.sep not in k})
        self.assertEqual(self.backups(), [])

    def test_abort_verify_when_the_copy_does_not_read_back(self):
        self.root()
        real = self.dm._load_secrets
        calls = {'n': 0}

        def lying():
            calls['n'] += 1
            out = real()
            if calls['n'] >= 3:                                     # перевірка прочитанням — після плану, бекапу й запису
                out = json.loads(json.dumps(out))
                out.get('legacy', {}).pop('vercel-publish', None)
            return out
        with self.mock.patch.object(self.dm, '_load_secrets', lying):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-verify')
        self.assertEqual(self.tasks()['preview_password'], self.PW)      # нічого не видалено
        self.assertNotIn('liga-4d4b', self.read_json(self.space_path()).get('migrations', {}))

    def test_failure_before_the_root_leaves_copies_and_next_start_finishes(self):
        self.root()
        with self.mock.patch.object(self.lm, '_commit_originals', side_effect=OSError('x')):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-originals')
        self.assertIn('preview_password', self.tasks())                  # корінь цілий
        self.assertEqual(self.read_json(self.secrets_path())['legacy']['vercel-publish'], {'password': self.PW})   # копії лежать
        self.assertNotIn('liga-4d4b', self.read_json(self.space_path()).get('migrations', {}))
        st, _i = self.run_e()                                          # повтор доробляє
        self.assertEqual(st, 'done')
        self.assertNotIn('preview_password', self.tasks())

    def test_failure_between_root_and_mark_is_finished_by_next_start(self):
        self.root()
        with self.mock.patch.object(self.lm, '_commit_space', side_effect=OSError('x')):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-write')
        for k in self.ALL:
            self.assertNotIn(k, self.tasks())                           # ключі вже видалені, позначки нема
        p = self.lm.plan(step=self.E)
        self.assertEqual(p['status'], 'skip-nothing')                    # нічого видаляти; позначка не пишеться (див. Поправку)

    def test_a_person_changed_a_setting_between_copy_and_delete_keeps_that_key(self):
        """Вікно між перевіркою копій і видаленням: людина міняє `ssh_key` на екрані «Підключення» ПІСЛЯ `abort-verify`-перевірки, але ДО запису кореня.
        Свіже рішення всередині `_commit_originals` бачить розбіжність і ключ лишає (інакше єдина копія була б значенням, якого людина вже не хоче)."""
        self.root()
        real = self.lm._verify_copies

        def verify_then_tamper(sid, space_path, d):
            ok = real(sid, space_path, d)
            data = self.read_json(self.space_path())
            data['modules']['git-sync']['settings']['ssh_key'] = '/changed/by/a/person'
            self._write(self.space_path(), data)
            return ok
        with self.mock.patch.object(self.lm, '_verify_copies', verify_then_tamper):
            st, info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertIn('gitlab_ssh_key', self.tasks())
        self.assertIn('gitlab_ssh_key', self.mark()['kept'])
        self.assertNotIn('gitlab_ssh_key', self.mark()['removed'])
        self.assertNotIn('gitlab_host_ip', self.tasks())             # решта ключів видалена, як планувалось
        self.assertEqual(self.read_json(self.space_path())['modules']['git-sync']['settings']['ssh_key'], '/changed/by/a/person')   # правку людини не перетерто

    def test_race_on_tasks_file_aborts(self):
        self.root()
        real = self.lm._file_sig
        n = {'i': 0}

        def moving(p):
            n['i'] += 1
            return (n['i'], 1)
        with self.mock.patch.object(self.lm, '_file_sig', moving):
            st, _i = self.run_e()
        self.assertEqual(st, 'abort-originals')

    def test_idempotent(self):
        self.root()
        self.assertEqual(self.run_e()[0], 'done')
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-done')

    def test_notes_only_still_writes_mark(self):
        self.root(**dict({k: None for k in self.ALL}, jira_base='https://example.com/x'))
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        self.assertEqual(self.mark()['notes'], ['unfit:jira_base'])
        self.assertEqual(self.mark()['removed'], [])
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-done')

    def test_foreign_edits_to_space_json_survive(self):
        self.root()
        real = self.lm._merge_settings

        def edit_then_merge(space_path, patches):
            sj = self.read_json(self.space_path())
            sj['name'] = 'Renamed by a person'
            self._write(self.space_path(), sj)
            return real(space_path, patches)
        with self.mock.patch.object(self.lm, '_merge_settings', edit_then_merge):
            self.run_e()
        self.assertEqual(self.read_json(self.space_path())['name'], 'Renamed by a person')


class RestoreE(_StandE):
    def _applied(self):
        self.root()
        st, info = self.run_e()
        self.assertEqual(st, 'done')
        return info['backup']

    def test_restore_merges_removed_keys_back_and_keeps_live_edits(self):
        stamp = self._applied()
        t = self.tasks()
        t['tasks']['a-3'] = {'dir': '/new', 'title': 'Created after the step'}
        t['gitlab_ssh_key'] = '/my/own/key'                              # людина вже вписала своє
        self._write(self.tasks_path, t)
        st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        now = self.tasks()
        self.assertIn('a-3', now['tasks'])                               # живі правки задач не губляться
        self.assertEqual(now['gitlab_ssh_key'], '/my/own/key')           # kept-live
        for k in self.ALL:
            if k != 'gitlab_ssh_key':
                self.assertIn(k, now)
        self.assertEqual(info['kept_live'], ['gitlab_ssh_key'])
        self.assertNotIn('gitlab_ssh_key', info['root_restored'])
        self.assertNotIn('liga-4d4b', self.read_json(self.space_path()).get('migrations', {}))
        self.assertTrue(os.path.exists(self.tasks_path + '.bak'))

    def test_restore_never_rewrites_the_whole_file(self):
        stamp = self._applied()
        t = self.tasks()
        t['tasks']['a-3'] = {'dir': '/new', 'title': 'Created after the step'}
        self._write(self.tasks_path, t)
        self.lm._restore(stamp)
        self.assertIn('a-3', self.tasks()['tasks'])

    def test_restore_with_hold_marks_only_e(self):
        stamp = self._applied()
        self.lm._restore(stamp, hold=True)
        mig = self.read_json(self.space_path())['migrations']
        self.assertEqual(mig['liga-4d4b'], {'held': True})

    def test_restore_fallback_when_mark_lacks_removed(self):
        stamp = self._applied()
        sj = self.read_json(self.space_path())
        sj['migrations']['liga-4d4b'].pop('removed')
        self._write(self.space_path(), sj)
        st, info = self.lm._restore(stamp)
        self.assertEqual(st, 'restored')
        for k in self.ALL:
            self.assertIn(k, self.tasks())

    def test_restore_aborts_when_the_live_file_keeps_changing(self):
        """Постійна гонка на живому `tasks.json` (людина/UI пише без перерви): відкат нічого не пише в корінь і не чіпає `space.json`."""
        stamp = self._applied()
        before_space, before_root = self.read(self.space_path()), self.read(self.tasks_path)
        n = {'i': 0}

        def moving(p):
            n['i'] += 1
            return (n['i'], 1)
        with self.mock.patch.object(self.lm, '_file_sig', moving):
            st, _i = self.lm._restore(stamp)
        self.assertEqual(st, 'abort-restore')
        self.assertEqual(self.read(self.space_path()), before_space)
        self.assertEqual(self.read(self.tasks_path), before_root)

    def test_restore_refuses_when_the_live_file_is_unreadable(self):
        stamp = self._applied()
        self._write(self.tasks_path, '{not json')
        before = self.read(self.space_path())
        st, _i = self.lm._restore(stamp)
        self.assertEqual(st, 'abort-restore')
        self.assertEqual(self.read(self.space_path()), before)          # space.json не чіпано: корінь першим

    def test_lifo_five_steps(self):
        stamp = self._applied()
        stamp_d = self.lm._backup(self.deai, 'legacy', self.space_dir, self.lm.STEP_D)      # справжній бекап кроку D (манифест, sha256)
        sj = self.read_json(self.space_path())
        sj['migrations']['liga-4d4a'] = {'at': 'x', 'backup': stamp_d}
        self._write(self.space_path(), sj)
        st, info = self.lm._restore(stamp_d)
        self.assertEqual(st, 'refuse-later-applied')
        self.assertEqual(info['rollback_first'], stamp)


class RolesState(_StandE):
    """`roles_state()` (§4.1): шість ролей, причина — перша застосовна, команда виправлення без шляхів і значень."""

    def by_role(self):
        return {r['role']: r for r in self.lm.roles_state()}

    def test_all_six_on_when_records_are_enabled(self):
        got = self.lm.roles_state()
        self.assertEqual([r['role'] for r in got], ['publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify'])
        self.assertTrue(all(r['on'] and r['reason'] is None and r['fix'] == '' for r in got))
        self.assertEqual(self.lm.roles_lines(got), [])

    def test_disabled_record(self):
        self.rec_all(mods={'jira-tracker': {'enabled': False, 'shared_state': True, 'settings': {'base': self.JIRA_BASE, 'email': self.JIRA_EMAIL}}})
        r = self.by_role()['tracker']
        self.assertEqual((r['on'], r['reason']), (False, 'disabled'))
        self.assertIn('«Підключення»', r['fix'])

    def test_no_record_with_skipped_code_from_the_last_report(self):
        self.rec_all(drop=('jira-tracker',), migrations={'liga-4d3a': {'at': 'x', 'roles': ['dashboard', 'notify'], 'tracks': False, 'backup': 'b'}})
        self._write(os.path.join(self.deai, 'migrations', 'last.json'),
                    {'steps': {'liga-4d3a': {'status': 'done', 'skipped': {'tracker': 'no-jira'}}}})
        r = self.by_role()['tracker']
        self.assertEqual(r['reason'], 'no-jira')
        self.assertIn('pipeline-feedback', r['fix'])                     # текст каже, що оточення й pipeline-feedback більше не читаються

    def test_applied_step_without_the_role_and_without_a_report_is_not_migrated(self):
        self.rec_all(drop=('jira-tracker',), migrations={'liga-4d3a': {'at': 'x', 'roles': ['dashboard', 'notify'], 'tracks': False, 'backup': 'b'}})
        self.assertEqual(self.by_role()['tracker']['reason'], 'not-migrated')

    def test_held_step_names_unhold(self):
        self.rec_all(drop=('jira-tracker', 'supabase-dashboard', 'supabase-teams'), migrations={'liga-4d3a': {'held': True}})
        r = self.by_role()['tracker']
        self.assertEqual(r['reason'], 'skip-held')
        self.assertIn('migrate_liga.py unhold liga-4d3a', r['fix'])

    def test_early_step_held_names_the_early_mark_for_later_owners(self):
        """`held` кроку A тримає B і C: роль `publish` (власник C) каже `skip-held` і `unhold liga-4d3a`, а не оманливе `no-record`/`run`."""
        self.rec_all(drop=('vercel-publish', 'git-sync', 'supabase-comments'), migrations={'liga-4d3a': {'held': True}})
        for role in ('publish', 'comments', 'vcs'):
            r = self.by_role()[role]
            self.assertEqual(r['reason'], 'skip-held', role)
            self.assertIn('migrate_liga.py unhold liga-4d3a', r['fix'], role)

    def test_last_report_skip_codes_have_their_own_fix(self):
        self.rec_all(drop=('vercel-publish',))
        for code, needle in (('skip-path-in-git', 'поза робоче дерево git'), ('skip-tasks-unreadable', 'tasks.json'),
                             ('skip-space-json-unreadable', 'space.json'), ('abort-write', 'status'), ('skip-busy', 'повторіть')):
            self._write(os.path.join(self.deai, 'migrations', 'last.json'), {'steps': {'liga-4d3c': {'status': code}}})
            r = self.by_role()['publish']
            self.assertEqual(r['reason'], code)
            self.assertIn(needle, r['fix'], code)

    def test_no_record_default_names_run(self):
        self.rec_all(drop=('supabase-comments',))
        r = self.by_role()['comments']
        self.assertEqual(r['reason'], 'no-record')
        self.assertIn('migrate_liga.py run', r['fix'])

    def test_broken_module_is_module_error(self):
        self.rec_all(mods={'git-sync': {'enabled': True, 'shared_state': True, 'settings': {'compat': 'bogus-value'}}})
        r = self.by_role()['vcs']
        self.assertFalse(r['on'])
        self.assertIn(r['reason'], ('bad-settings', 'module-error'))

    def test_unreadable_space_json_names_every_role(self):
        self._write(self.space_path(), '{not json')
        got = self.lm.roles_state()
        self.assertEqual({r['reason'] for r in got}, {'space-json-unreadable'})
        self.assertEqual(len(got), 6)

    def test_integrations_off_is_quiet(self):
        self.registry()
        reg = self.read_json(os.path.join(self.deai, 'spaces.json'))
        reg['spaces'][0]['integrations'] = False
        self._write(os.path.join(self.deai, 'spaces.json'), reg)
        got = self.lm.roles_state()
        self.assertEqual({r['reason'] for r in got}, {'integrations-off'})
        self.assertEqual(self.lm.roles_lines(got), [])

    def test_layer_off_and_no_liga_give_nothing(self):
        self.registry(entry=False)
        self.assertEqual(self.lm.roles_state(), [])

    def test_lines_carry_no_values_or_paths(self):
        self.rec_all(drop=('jira-tracker',))
        text = '\n'.join(self.lm.roles_lines(self.lm.roles_state()))
        self.assertIn('ролі ЛІГИ вимкнено: tracker (jira-tracker) — no-record; виправити:', text)
        for bad in (self.tmp, self.SB_KEY, self.JIRA_TOKEN):
            self.assertNotIn(bad, text)


class StartupE(_StandE):
    """Старт: п'ять кроків, рядки Е, рядок «єдина копія», блок вимкнених ролей; ізольований прогін блок не друкує."""

    def fresh_unmigrated_tree(self):
        """Стара установка 0.16: записів нема, корінь має оригінали; `JIRA_*` у оточенні (старт з терміналу)."""
        import shutil
        shutil.rmtree(self.space_dir)
        os.makedirs(self.space_dir)
        if os.path.exists(self.secrets_path()):
            os.remove(self.secrets_path())
        self.root()
        os.environ['JIRA_EMAIL'], os.environ['JIRA_TOKEN'] = self.JIRA_EMAIL, self.JIRA_TOKEN

    def test_five_steps_five_backups_one_restore_hint(self):
        self.fresh_unmigrated_tree()
        st, err = self.quiet(self.lm.startup)
        self.assertEqual(st, 'done')
        marks = ('liga-4d3a', 'liga-4d3b', 'liga-4d3c', 'liga-4d4a', 'liga-4d4b')
        for m in marks:
            self.assertIn('%s: done' % m, err)
        self.assertEqual(len(self.backups()), 5)
        self.assertEqual(err.count('відкат: bin/migrate_liga.py restore'), 1)
        self.assertIn('restore %s --hold' % self.backups()[-1].replace(self.backups()[-1], [b for b in self.backups() if b.endswith('-liga-4d4b')][0]), err)
        self.assertIn(self.lm.ORIGINALS_REMOVED_LINE, err)
        self.assertIn('скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password', err)
        self.assertNotIn('ролі ЛІГИ вимкнено', err)                       # усі шість ролей увімкнено
        for v in (self.SB_KEY, self.JIRA_TOKEN, self.PW, self.SSH, self.HOSTIP):
            self.assertNotIn(v, err)

    def test_off_roles_are_named_on_every_start_while_off(self):
        self.fresh_unmigrated_tree()
        os.environ.pop('JIRA_EMAIL')
        os.environ.pop('JIRA_TOKEN')                                      # трекер не мігрує: `no-jira`
        _st, err1 = self.quiet(self.lm.startup)
        self.assertIn('ролі ЛІГИ вимкнено: tracker (jira-tracker) — no-jira; виправити:', err1)
        _st, err2 = self.quiet(self.lm.startup)                           # другий старт: кроки skip-done, але рядок лишається
        self.assertIn('ролі ЛІГИ вимкнено: tracker (jira-tracker) — no-jira', err2)

    def test_isolated_run_prints_no_roles_block(self):
        self.fresh_unmigrated_tree()
        os.environ.pop('JIRA_EMAIL')
        os.environ.pop('JIRA_TOKEN')
        self.lm.startup()
        with self.mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path, 'DEAI_HOME': self.deai, 'DC_MIGRATE_LIGA': '1'}):
            _st, err = self.quiet(self.lm.startup)
        self.assertNotIn('ролі ЛІГИ вимкнено', err)


class StatusAndCli(_StandE):
    def test_status_text_has_originals_and_roles_sections(self):
        self.root()
        self.run_e()
        text = self.lm.status_text(self.lm.status())
        self.assertIn('Міграція ЛІГИ (liga-4d4b)', text)
        self.assertIn('скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password', text)
        self.assertIn('видалено:', text)
        self.assertIn('Ролі ЛІГИ', text)
        self.assertIn('publish (vercel-publish): так', text)
        for v in (self.SB_KEY, self.JIRA_TOKEN, self.PW, self.SSH, self.HOSTIP):
            self.assertNotIn(v, text)

    def test_cli_dry_run_names_keys_not_values(self):
        self.root()
        code, out, _err = self.cli('dry-run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4b: ready', out)
        self.assertIn('copy: gitlab_ssh_key, gitlab_host_ip, preview_password', out)
        self.assert_no_secrets(out)
        self.assertNotIn(self.SSH, out)

    def test_cli_unhold(self):
        self.space_json({'modules': {}, 'migrations': {'liga-4d4a': {'held': True}, 'liga-4d4b': {'at': 'x', 'backup': 'b'}}})
        code, out, _e = self.cli('unhold', 'liga-4d4a')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4a unhold: unheld', out)
        self.assertNotIn('liga-4d4a', self.read_json(self.space_path())['migrations'])
        self.assertIn('liga-4d4b', self.read_json(self.space_path())['migrations'])      # чужі позначки лишились
        code, out, _e = self.cli('unhold', 'liga-4d4b')                  # застосований крок — не `held`
        self.assertEqual(code, 1)
        self.assertIn('refuse-not-held', out)
        self.assertEqual(self.cli('unhold', 'liga-nope')[0], 1)

    def test_unhold_lets_the_step_run_again(self):
        self.root()
        self.space_json({'modules': {}, 'migrations': {'liga-4d4b': {'held': True}}})
        self.assertEqual(self.lm.plan(step=self.E)['status'], 'skip-held')
        self.assertEqual(self.lm.unhold('liga-4d4b'), 'unheld')
        self.assertNotEqual(self.lm.plan(step=self.E)['status'], 'skip-held')

    def test_unhold_refuses_without_liga_and_in_layer_off(self):
        self.registry(entry=False)
        self.assertEqual(self.lm.unhold('liga-4d4a'), 'refuse-no-liga')
        with self.mock.patch.dict(os.environ, {'DC_TASKS_FILE': self.tasks_path}):
            os.environ.pop('DEAI_HOME')
            self.assertEqual(self.lm.unhold('liga-4d4a'), 'skip-layer-off')


if __name__ == '__main__':
    unittest.main()
````


## Додаток Б: допоміжні тести й фікстура

### `tests/test_isolation.py` (Task 3, `IsolationCore`, 11 тестів)

````python
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import isolation  # noqa: E402

ENVS = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TRACKER_FAKE', 'DC_TEAMS_FAKE')


class IsolationCore(unittest.TestCase):
    """Закон ізоляції й шви тестів (раніше `ImplicitCore`): `isolated`, `route`, таблиця `FAKE_ENV`, `real_home`."""

    def setUp(self):
        e = mock.patch.dict(os.environ, {})
        e.start()
        self.addCleanup(e.stop)
        for k in ENVS:
            os.environ.pop(k, None)

    def test_imports_nothing_but_os(self):
        """Чистий модуль: цикл імпорту з `spaces`/`serve`/`deai_modules` неможливий."""
        import ast
        with open(isolation.__file__.replace('.pyc', '.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        mods = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertEqual(mods, {'os', 'pwd'})

    def test_fake_env_table_is_the_old_one(self):
        self.assertEqual(isolation.FAKE_ENV, {'dashboard': 'DC_TEAM_FAKE', 'tracker': 'DC_TRACKER_FAKE', 'notify': 'DC_TEAMS_FAKE'})

    def test_isolated_is_tasks_file_or_no_overview(self):
        self.assertFalse(isolation.isolated())
        for k in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW'):
            with mock.patch.dict(os.environ, {k: '1'}):
                self.assertTrue(isolation.isolated(), k)
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': 'x'}):
            self.assertFalse(isolation.isolated())                 # шов сам по собі не робить прогін ізольованим

    def test_route_order_fake_then_isolated_then_live(self):
        self.assertEqual(isolation.route('dashboard'), ('live', None))
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '1'}):
            self.assertEqual(isolation.route('dashboard'), ('isolated', None))
            with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': '/tmp/fake.json'}):
                self.assertEqual(isolation.route('dashboard'), ('fake', '/tmp/fake.json'))   # шов раніше за ізоляцію

    def test_an_empty_seam_is_absent(self):
        """Порожнє значення шва (`DC_TEAM_FAKE=`) — як відсутнє: ні шва, ні ізоляції не вмикає."""
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': ''}):
            self.assertEqual(isolation.route('dashboard'), ('live', None))
            with mock.patch.dict(os.environ, {'DC_TASKS_FILE': '1'}):
                self.assertEqual(isolation.route('dashboard'), ('isolated', None))

    def test_each_role_uses_its_own_seam(self):
        for role, env in isolation.FAKE_ENV.items():
            with mock.patch.dict(os.environ, {env: '/tmp/x.json'}):
                self.assertEqual(isolation.route(role), ('fake', '/tmp/x.json'), role)
                for other in set(isolation.FAKE_ENV) - {role}:
                    self.assertEqual(isolation.route(other), ('live', None), (role, other))

    def test_roles_without_a_seam_are_only_isolated_or_live(self):
        for role in ('comments', 'vcs', 'publish', 'tokens'):
            self.assertEqual(isolation.route(role), ('live', None))
            with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1', 'DC_TEAM_FAKE': '/tmp/x.json'}):
                self.assertEqual(isolation.route(role), ('isolated', None), role)

    def test_real_home_is_the_pwd_home_not_the_HOME_variable(self):
        import pwd
        real = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, '.deai')
        self.assertTrue(isolation.real_home(real))
        with tempfile.TemporaryDirectory() as t:
            with mock.patch.dict(os.environ, {'HOME': t}):          # тест підміняє HOME, але не пароль ОС
                self.assertFalse(isolation.real_home(os.path.join(t, '.deai')))
                self.assertFalse(isolation.real_home(t))
                self.assertTrue(isolation.real_home(real))

    def test_real_home_follows_symlinks(self):
        import pwd
        real = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, '.deai')
        with tempfile.TemporaryDirectory() as t:
            link = os.path.join(t, 'link')
            os.symlink(real, link)
            self.assertTrue(isolation.real_home(link))

    def test_real_home_unknown_os_home_is_real(self):
        """Безпечніший бік: не вдалось дізнатись дім ОС — вважаємо справжнім (облікових із цієї теки не беремо)."""
        with mock.patch('pwd.getpwuid', side_effect=KeyError('x')):
            self.assertTrue(isolation.real_home('/anything'))

    def test_real_home_garbage_is_real(self):
        self.assertTrue(isolation.real_home(None))


if __name__ == '__main__':
    unittest.main()
````

Клас Task 3 (дописується в той самий файл; видаляється в Task 10):

````python
class ParityWithImplicitUntilRemoval(unittest.TestCase):
    """До видалення `app/implicit.py` (4d-4b Task 10) його `isolated`/`route` — ОРИГІНАЛ, а `isolation` — точна копія: на всіх комбінаціях оточення відповіді рівні
    (`implicit.py` не чіпаємо: тести `ImplicitCore` стверджують його форму, зокрема `shared=False`). Клас видаляється разом із модулем."""

    COMBOS = ({}, {'DC_TASKS_FILE': '1'}, {'DC_NO_OVERVIEW': '1'}, {'DC_TEAM_FAKE': '/tmp/f.json'}, {'DC_TRACKER_FAKE': '/tmp/f.json', 'DC_NO_OVERVIEW': '1'},
              {'DC_TEAMS_FAKE': '/tmp/f.json', 'DC_TASKS_FILE': '1'}, {'DC_TEAM_FAKE': ''})

    def test_the_copy_equals_the_original(self):
        import implicit
        for env in self.COMBOS:
            with mock.patch.dict(os.environ, env):
                self.assertEqual(implicit.isolated(), isolation.isolated(), env)
                for role in implicit.IMPLICIT_ROLES:
                    self.assertEqual(implicit.route(implicit.for_role(role)), isolation.route(role), (env, role))
        self.assertEqual({r: implicit.for_role(r).fake_env for r in implicit.IMPLICIT_ROLES if implicit.for_role(r).fake_env},
                         isolation.FAKE_ENV)
````

### `tests/liga_fixture.py` (Task 8)

````python
"""Явна фікстура простору ЛІГА (4d-4b): ролі ЛІГИ — це ЯВНІ записи `space.json` + секрети в тимчасовому `DEAI_HOME`, а не облікові в корені
`tasks.json` чи в оточенні (рантайм їх більше не читає). Два способи, що дають однаковий результат:

* `LigaFixture.build()` — прямі записи (швидко, для тестів ролей); `LigaFixture.migrate()` — НАСПРАВДІ запускає `liga_migrate.run_all` на
  старому корені з вісьмома оригіналами («як у людини»): рантайм-тести, що мають перевіряти шлях міграції, беруть його.
* Лише ТИМЧАСОВІ теки: жодного шляху в справжній дім. Значення — вигадані (`https://sb.example.com`, `team_x`, `alpha@example.com`).

Використання: `fx = LigaFixture(self); fx.build(); …` — у `setUp` тесту, що вже підмінив `HOME`/`DEAI_HOME` (`fx.env()` робить це сам,
якщо тест цього не зробив).
"""
import json
import os
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))

SB_URL, SB_KEY = 'https://sb.example.com', 'sb_fixture_key_alpha'
JIRA_BASE, JIRA_EMAIL, JIRA_TOKEN = 'https://jira.example.com', 'alpha@example.com', 'jira_fixture_token_alpha'
SSH_KEY, HOST_IP, PASSWORD = '~/.ssh/id_example', '203.0.113.7', 'pw-fixture'
#: Шість ролей → (модуль, налаштування, секрети). Форма — та сама, що пишуть кроки A–C (`liga_migrate._entries_*`).
ROLE_RECORDS = {
    'dashboard': ('supabase-dashboard', {'url': SB_URL, 'table': 'overview_projects', 'compat': 'comment-layer'}, {'key': SB_KEY}),
    'notify': ('supabase-teams', {'url': SB_URL, 'compat': 'comment-layer'}, {'key': SB_KEY}),
    'comments': ('supabase-comments', {'url': SB_URL, 'shots_bucket': 'overview-thumbs', 'compat': 'comment-layer'}, {'key': SB_KEY}),
    'tracker': ('jira-tracker', {'base': JIRA_BASE, 'email': JIRA_EMAIL}, {'token': JIRA_TOKEN}),
    'vcs': ('git-sync', {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True, 'compat': 'design-canvas',
                         'ssh_key': SSH_KEY, 'host_ip': HOST_IP}, {}),
    'publish': ('vercel-publish', {'auth': 'cli', 'team': '', 'compat': 'design-canvas'}, {'password': PASSWORD}),
}
ALL_ROLES = tuple(ROLE_RECORDS)


class LigaFixture:
    """Тимчасовий `HOME`/`DEAI_HOME` + реєстр із простором ЛІГА (`legacy: true`, `integrations: true`) + `space.json` + `secrets.json`."""

    def __init__(self, test, tmp=None):
        self.test = test
        if tmp is None:
            d = tempfile.TemporaryDirectory(prefix='liga-fx-')
            test.addCleanup(d.cleanup)
            tmp = d.name
        self.tmp = os.path.realpath(tmp)
        self.home = os.path.join(self.tmp, 'home')
        self.deai = os.path.join(self.home, '.deai')
        self.space_dir = os.path.join(self.tmp, 'liga-space')
        self.tasks_path = os.path.join(self.tmp, 'legacy-tasks.json')
        for d in (self.home, self.deai, self.space_dir):
            os.makedirs(d, exist_ok=True)

    # --- оточення
    def env(self, **extra):
        """`HOME`/`DEAI_HOME` у тимчасовій теці, без жодних облікових оточення; `spaces.legacy_tasks_file` → `self.tasks_path`."""
        import deai_modules
        import spaces
        e = mock.patch.dict(os.environ, dict({'HOME': self.home, 'DEAI_HOME': self.deai}, **extra))
        e.start()
        self.test.addCleanup(e.stop)
        for name in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'DC_TRACKER_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
                     'SUPABASE_SERVICE_KEY', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DEAI_EXTRA_MODULES'):
            if name not in extra:
                os.environ.pop(name, None)
        lf = mock.patch.object(spaces, 'legacy_tasks_file', lambda: self.tasks_path)
        lf.start()
        self.test.addCleanup(lf.stop)
        deai_modules.reset_caches()
        self.test.addCleanup(deai_modules.reset_caches)
        return self

    def _write(self, path, obj):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(obj if isinstance(obj, str) else json.dumps(obj))

    def registry(self, integrations=True):
        self._write(os.path.join(self.deai, 'spaces.json'),
                    {'version': 1, 'current': 'legacy', 'spaces': [{'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': integrations}]})

    # --- спосіб (а): прямі записи
    def build(self, roles=ALL_ROLES, overrides=None, tasks=None, root_extra=None):
        """Явні записи `roles` (рівні тим, що пишуть кроки A–C) + `secrets.json`; корінь `tasks.json` БЕЗ облікових (лише `tasks`/маркер `registry`).
        `overrides[роль] = {'enabled': False, 'settings': {…}, 'secrets': {…}}` — заміна окремих частин запису."""
        self.registry()
        mods, sec = {}, {}
        for role in roles:
            mid, settings, secrets = ROLE_RECORDS[role]
            o = (overrides or {}).get(role, {})
            mods[mid] = {'enabled': o.get('enabled', True), 'shared_state': True, 'settings': dict(settings, **o.get('settings', {}))}
            s = dict(secrets, **o.get('secrets', {}))
            if s:
                sec[mid] = s
        self._write(os.path.join(self.space_dir, 'space.json'), {'name': 'Liga', 'modules': mods, 'migrations': {}})
        secrets_path = os.path.join(self.deai, 'secrets.json')
        self._write(secrets_path, {'legacy': sec})
        os.chmod(secrets_path, 0o600)
        root = dict({'registry': {'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'}, 'tasks': tasks or {}}, **(root_extra or {}))
        self._write(self.tasks_path, root)
        import deai_modules
        deai_modules.reset_caches()
        return self

    # --- спосіб (б): справжня міграція зі старого кореня
    def legacy_root(self, **over):
        """Старий корінь із вісьмома оригіналами (`over` — заміна/додавання; `None` — прибрати ключ) і `registry`-маркером."""
        cfg = {'supabase_url': SB_URL, 'supabase_key': SB_KEY, 'jira_base': JIRA_BASE, 'jira_email': JIRA_EMAIL, 'jira_token': JIRA_TOKEN,
               'gitlab_ssh_key': SSH_KEY, 'gitlab_host_ip': HOST_IP, 'preview_password': PASSWORD,
               'registry': {'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'}, 'tasks': {}}
        for k, v in over.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        self._write(self.tasks_path, cfg)
        return cfg

    def migrate(self, **over):
        """Старий корінь → `liga_migrate.run_all()` на всіх п'яти кроках. Повертає `[(позначка, статус, підсумок)]`. Потрібен `jira_email`/`jira_token`
        в ОТОЧЕННІ міграції (A читає їх із `JIRA_*`): виставляємо на час прогону й прибираємо."""
        import liga_migrate
        self.registry()
        self._write(os.path.join(self.space_dir, 'space.json'), {'name': 'Liga'})
        cfg = self.legacy_root(**over)
        env = {} if cfg.get('jira_email') is None else {'JIRA_EMAIL': cfg['jira_email'], 'JIRA_TOKEN': cfg.get('jira_token') or ''}
        with mock.patch.dict(os.environ, env), mock.patch.object(liga_migrate, 'STEPS', liga_migrate.ALL_STEPS):
            return liga_migrate.run_all()
````

### `tests/test_liga_fixture.py` (Task 8, 3 тести)

````python
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import liga_fixture  # noqa: E402
import deai_modules  # noqa: E402
import liga_migrate  # noqa: E402


def _roles(space):
    return {r: (lambda p: p.id if isinstance(p, deai_modules.Module) else p)(deai_modules._provider_for(r, space)) for r in liga_fixture.ALL_ROLES}


class LigaFixtureBothWays(unittest.TestCase):
    """Обидва способи фікстури дають ОДНАКОВИХ постачальників і однакові ефективні налаштування/секрети; корінь без облікових."""

    def space(self, fx):
        return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True, 'integrations': True}

    def test_build_makes_all_six_roles_explicit(self):
        fx = liga_fixture.LigaFixture(self).env().build()
        self.assertEqual(_roles(self.space(fx)), {r: liga_fixture.ROLE_RECORDS[r][0] for r in liga_fixture.ALL_ROLES})
        self.assertTrue(all(s['on'] for s in liga_migrate.roles_state()))
        with open(fx.tasks_path, encoding='utf-8') as f:
            root = json.load(f)
        self.assertEqual(sorted(root), ['registry', 'tasks'])

    def test_migrate_gives_the_same_roles_and_a_clean_root(self):
        fx = liga_fixture.LigaFixture(self).env()
        res = fx.migrate()
        self.assertEqual([r[1] for r in res], ['done', 'done', 'done', 'skip-nothing', 'done'], res)       # 4d-4a: у тестовому корені нема записів задач
        self.assertEqual(_roles(self.space(fx)), {r: liga_fixture.ROLE_RECORDS[r][0] for r in liga_fixture.ALL_ROLES})
        with open(fx.tasks_path, encoding='utf-8') as f:
            root = json.load(f)
        self.assertEqual(sorted(root), ['registry', 'tasks'])
        self.assertEqual(deai_modules.publish_password(self.space(fx)), liga_fixture.PASSWORD)
        self.assertTrue(all(s['on'] for s in liga_migrate.roles_state()))

    def test_overrides_disable_one_role(self):
        fx = liga_fixture.LigaFixture(self).env().build(overrides={'tracker': {'enabled': False}})
        st = {s['role']: s for s in liga_migrate.roles_state()}
        self.assertEqual((st['tracker']['on'], st['tracker']['reason']), (False, 'disabled'))
        self.assertTrue(st['notify']['on'])


if __name__ == '__main__':
    unittest.main()
````

### `tests/test_before_4d4b.py` (Task 1, 7 тестів)

````python
"""Знімок поведінки 0.20.0 (`fixtures/liga-migration/before-4d4b.json`, етап 4d-4b, Task 1): на місці, без шляхів машини, достатньо великий, форма — та, на яку
спираються тести паритету (`AfterMigrationParity4d4b`). Сам знімок не переганяємо: еталон «до»; генератор відмовляється працювати на зміненому `app/`/`bin/`."""
import json
import os
import re
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4b.json')
ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')


def _flat(o, p=''):
    if isinstance(o, dict):
        return {k2: v2 for k, v in o.items() for k2, v2 in _flat(v, '%s/%s' % (p, k)).items()}
    if isinstance(o, list):
        return {k2: v2 for i, v in enumerate(o) for k2, v2 in _flat(v, '%s[%d]' % (p, i)).items()}
    return {p: o}


class Before4d4bShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_meta(self):
        m = self.snap['meta']
        self.assertEqual((m['version'], m['source_commit'], m['generator']), ('0.20.0', '0d52a74', 'tests/make_before_4d4b.py'))
        self.assertEqual(self.snap['non_loopback_attempts'], 10)

    def test_five_stands_and_their_sections(self):
        st = self.snap['stands']
        self.assertEqual(sorted(st), ['differs', 'partial', 'plain', 'regular', 'unmigrated'])
        full = ['api', 'capabilities', 'isolation', 'provider', 'registry_ssh', 'root_keys', 'vcs_target']
        self.assertEqual(sorted(st['differs']), full)
        self.assertEqual(sorted(st['partial']), full)
        self.assertEqual(sorted(st['regular']), sorted(full + ['startup_text']))
        self.assertEqual(sorted(st['unmigrated']), sorted(full + ['startup_text']))
        self.assertEqual(sorted(st['plain']), ['api', 'capabilities', 'provider', 'root_keys'])

    def test_the_snapshot_records_the_implicit_provider_of_0_20(self):
        """Те, що після 0.21 ЗНИКАЄ: у неявному просторі й у немігрованій ЛІЗІ шість ролей — `Implicit`/`legacy`."""
        for name in ('regular', 'plain'):
            imp = self.snap['stands'][name]['provider']['implicit_space']
            self.assertEqual({r: imp[r]['api'] for r in ROLES if r != 'tokens'}, {r: 'legacy' for r in ROLES if r != 'tokens'}, name)
        un = self.snap['stands']['unmigrated']['provider']['in_space']
        self.assertEqual({r: un[r]['type'] for r in ROLES if r != 'tokens'}, {r: 'Implicit' for r in ROLES if r != 'tokens'})
        self.assertEqual(self.snap['stands']['regular']['provider']['in_space']['publish']['type'], 'Module')

    def test_the_originals_are_in_the_root_before_the_step(self):
        for name in ('regular', 'differs', 'partial', 'unmigrated'):
            keys = self.snap['stands'][name]['root_keys']
            for k in ('supabase_url', 'supabase_key', 'jira_base', 'jira_email', 'jira_token', 'gitlab_ssh_key', 'gitlab_host_ip', 'preview_password'):
                self.assertIn(k, keys, (name, k))

    def test_big_enough_to_mean_something(self):
        for name, st in self.snap['stands'].items():
            self.assertGreater(len(_flat(st)), 130 if name == 'plain' else 180, name)

    def test_machine_independent(self):
        """⛔ Ні справжніх шляхів, ні імен, ні тимчасових тек, ні часових штампів; значення — вигадані."""
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/Users/', '/home/', '/var/folders', '/private/', '/tmp/', 'before-4d4b-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))
        self.assertIsNone(re.search(r'\d{8}-\d{6}', self.raw))            # штампи бекапів → `<stamp>`

    def test_the_generator_refuses_to_overwrite_the_reference_on_changed_code(self):
        """Генератор у зміненому `app/` (тут — без `.git`-копії, тож перевіряємо лише, що він відмовляє за зашитим комітом у справжньому репо)."""
        src = os.path.join(_HERE, 'make_before_4d4b.py')
        with open(src, encoding='utf-8') as f:
            text = f.read()
        self.assertIn("return '0d52a74'", text)
        self.assertIn('sys.exit(2)', text)


if __name__ == '__main__':
    unittest.main()
````


## Додаток В: `tests/test_originals_gone.py` (Task 9–11; 29 тестів: `ProviderWithoutImplicit` 9, `ProviderCallersPinTheSpace` 2, `PreviewPasswordFromTheRecord` 6, `GitChainWithoutTheRoot` 3, `RegistrySshKey` 2, `CommentsInIsolation` 4, `DashboardSyncWithoutLegacy` 2, `TextsNameTheConnectionsScreen` 1)

````python
"""Рантайм без оригіналів і без запасного постачальника (етап 4d-4b): провайдер, пароль превʼю, ланцюг ключа git, ключ реєстру, коментарі в ізоляції,
синк дашборда. Усе на явній фікстурі ЛІГИ (`liga_fixture`): тимчасові `HOME`/`DEAI_HOME`, вигадані значення, мережі нема."""
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
for _p in (os.path.join(os.path.dirname(_HERE), 'app'), os.path.join(os.path.dirname(_HERE), 'bin')):
    sys.path.insert(0, _p)
import liga_fixture as lf  # noqa: E402
import deai_modules  # noqa: E402
import isolation  # noqa: E402
import spaces  # noqa: E402
import serve  # noqa: E402

ROLES = ('publish', 'comments', 'vcs', 'dashboard', 'tracker', 'notify')


def _liga(fx):
    return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True, 'integrations': True}


class ProviderWithoutImplicit(unittest.TestCase):
    """Роль ЛІГИ без явного ввімкненого запису — `None`; запасного постачальника нема."""

    def test_the_core_has_no_fallback_names(self):
        for name in ('Implicit', 'IMPLICIT_ROLES', 'IMPLICIT_ON_ERROR_ROLES', 'STRICT_IMPLICIT_ROLES'):
            self.assertFalse(hasattr(deai_modules, name), name)
        with self.assertRaises(TypeError):
            deai_modules.api_value('legacy')

    def test_all_six_explicit_records_are_modules(self):
        fx = lf.LigaFixture(self).env().build()
        got = {r: deai_modules.provider(r, _liga(fx)).id for r in ROLES}
        self.assertEqual(got, {r: lf.ROLE_RECORDS[r][0] for r in ROLES})

    def test_a_liga_role_without_a_record_is_none(self):
        fx = lf.LigaFixture(self).env().build(roles=())
        for r in ROLES:
            self.assertIsNone(deai_modules.provider(r, _liga(fx)), r)

    def test_a_disabled_record_is_none(self):
        fx = lf.LigaFixture(self).env().build(overrides={'tracker': {'enabled': False}})
        self.assertIsNone(deai_modules.provider('tracker', _liga(fx)))
        self.assertEqual(deai_modules.provider('notify', _liga(fx)).id, 'supabase-teams')

    def test_an_unpinned_request_space_has_no_roles(self):
        """Простір запиту не зафіксовано → неявний простір → жодної ролі (раніше `Implicit` для шести)."""
        lf.LigaFixture(self).env().build()
        with spaces.request_space(None):
            for r in ROLES + ('tokens',):
                self.assertIsNone(deai_modules.provider(r), r)

    def test_layer_off_has_no_roles(self):
        """Шар вимкнено (`DC_TASKS_FILE` без `DEAI_HOME`): неявний простір, ролей нема, секретів нема."""
        lf.LigaFixture(self).env()
        os.environ.pop('DEAI_HOME')
        os.environ['DC_TASKS_FILE'] = '/nonexistent/tasks.json'
        for r in ROLES:
            self.assertIsNone(deai_modules.provider(r), r)
        self.assertEqual(deai_modules.read_secrets('legacy', 'supabase-comments'), {})

    def test_unreadable_space_json_is_an_error_for_every_role(self):
        """Було лише для чотирьох ролей (`STRICT_IMPLICIT_ROLES`); тепер — для всіх шести, як у звичайних просторах."""
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.space_dir, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        for r in ROLES:
            with self.assertRaises(deai_modules.ModuleError, msg=r) as cm:
                deai_modules.provider(r, _liga(fx))
            self.assertEqual(cm.exception.code, 'space-json-unreadable', r)

    def test_capabilities_error_path_gives_none_not_legacy(self):
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.space_dir, 'space.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        deai_modules.reset_caches()
        caps = deai_modules.capabilities(_liga(fx))
        self.assertEqual((caps['publish'], caps['vcs'], caps['error']), (None, None, 'space-json-unreadable'))
        self.assertNotIn('legacy', caps.values())

    def test_publish_legacy_path_and_comment_scheme_read_only_the_module(self):
        fx = lf.LigaFixture(self).env().build()
        sp = _liga(fx)
        self.assertTrue(deai_modules.publish_legacy_path(deai_modules.provider('publish', sp), sp))
        self.assertTrue(deai_modules.comment_scheme_legacy(sp, deai_modules.provider('comments', sp)))
        self.assertFalse(deai_modules.publish_legacy_path(None, sp))
        self.assertFalse(deai_modules.comment_scheme_legacy(sp, None))


class PreviewPasswordFromTheRecord(unittest.TestCase):
    """Пароль превʼю: задача > секрет `password` запису `vercel-publish` (режим `design-canvas`) > `1100`. Корінь `tasks.json` не читається."""

    def test_task_then_secret_then_default(self):
        fx = lf.LigaFixture(self).env().build()
        sp = _liga(fx)
        self.assertEqual(serve.preview_password({'preview_password': 'task-pw'}, sp), 'task-pw')
        self.assertEqual(serve.preview_password({}, sp), lf.PASSWORD)
        fx.build(roles=tuple(r for r in lf.ALL_ROLES if r != 'publish'))
        self.assertEqual(serve.preview_password({}, sp), serve.DEFAULT_PREVIEW_PW)
        self.assertEqual(serve.preview_password(None, None), serve.DEFAULT_PREVIEW_PW)

    def test_the_root_password_is_ignored(self):
        fx = lf.LigaFixture(self).env().build(root_extra={'preview_password': 'root-pw'})
        self.assertEqual(serve.preview_password({}, _liga(fx)), lf.PASSWORD)
        fx.build(roles=(), root_extra={'preview_password': 'root-pw'})
        self.assertEqual(serve.preview_password({}, _liga(fx)), serve.DEFAULT_PREVIEW_PW)

    def test_module_mode_does_not_use_the_legacy_secret_here(self):
        """`compat` порожній: пароль у режимі модуля читає сам `publish_with_module`; `/api/task` дає типовий (так було й до 4d-4b для режиму модуля)."""
        fx = lf.LigaFixture(self).env().build(overrides={'publish': {'settings': {'compat': ''}}})
        self.assertIsNone(deai_modules.publish_password(_liga(fx)))

    def test_isolated_run_in_a_temp_home_uses_the_fixture_secret(self):
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        self.assertEqual(serve.preview_password({}, _liga(fx)), lf.PASSWORD)

    def test_isolated_run_in_the_real_home_never_reads_the_shared_secret(self):
        """Д6: ізольований прогін у СПРАВЖНЬОМУ домі — `1100`, секрет не береться (закон ізоляції)."""
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        with mock.patch.object(isolation, 'real_home', lambda home: True):
            self.assertEqual(serve.preview_password({}, _liga(fx)), serve.DEFAULT_PREVIEW_PW)

    def test_the_old_signature_is_gone(self):
        fx = lf.LigaFixture(self).env().build()
        with self.assertRaises(TypeError):
            serve.preview_password({'preview_password': 'x'}, {}, _liga(fx))


class GitChainWithoutTheRoot(unittest.TestCase):
    """Ключ і IP git: своє поле задачі > налаштування запису `git-sync`. Кореня `tasks.json` у ланцюгу нема."""

    def test_the_target_carries_only_the_tasks_own_fields(self):
        fx = lf.LigaFixture(self).env().build(root_extra={'gitlab_ssh_key': '/root/key', 'gitlab_host_ip': '198.51.100.1'})
        settings = {'branch': 'main', 'path': 'mockup/{task}'}
        with spaces.request_space('legacy'):
            t = serve.vcs_target('a-1', {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1'}}, settings)
            self.assertNotIn('ssh_key', t)
            self.assertNotIn('host_ip', t)
            own = serve.vcs_target('a-1', {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1', 'ssh_key': '/own/key',
                                                       'host_ip': '198.51.100.9'}}, settings)
            self.assertEqual((own['ssh_key'], own['host_ip']), ('/own/key', '198.51.100.9'))
            v = serve.vcs_target('a-1', {'vcs': {'repo': 'git@example.com:o/r.git'}}, settings)
            self.assertNotIn('ssh_key', v)

    def test_gitlab_cfg_has_no_root(self):
        lf.LigaFixture(self).env().build(root_extra={'gitlab_ssh_key': '/root/key'})
        got = serve.gitlab_cfg({'gitlab': {'repo': 'r', 'path': 'p'}})
        self.assertIsNone(got['ssh_key'])
        self.assertIsNone(got['host_ip'])
        self.assertEqual(serve.gitlab_cfg({'gitlab': {'repo': 'r', 'path': 'p', 'ssh_key': '~/k'}})['ssh_key'], os.path.expanduser('~/k'))
        with self.assertRaises(TypeError):
            serve.gitlab_cfg({}, {'gitlab': {}})                      # старий підпис `gitlab_cfg(cfg, task)`

    def test_the_effective_values_come_from_the_record(self):
        """Ефективні ключ і IP для git (ціль, інакше налаштування запису) — ті самі, що давав корінь до міграції (паритет)."""
        fx = lf.LigaFixture(self).env().build()
        with spaces.request_space('legacy'):
            _mod, ctx, _legacy = serve.vcs_provider()
        self.assertEqual((ctx['settings']['ssh_key'], ctx['settings']['host_ip']), (lf.SSH_KEY, lf.HOST_IP))


class RegistrySshKey(unittest.TestCase):
    def test_key_from_the_record_else_default_never_the_root(self):
        import registry
        fx = lf.LigaFixture(self).env().build(root_extra={'gitlab_ssh_key': '/root/key'})
        self.assertEqual(registry._ssh_key(), os.path.expanduser(lf.SSH_KEY))
        fx.build(overrides={'vcs': {'settings': {'ssh_key': '/other/key'}}})
        self.assertEqual(registry._ssh_key(), '/other/key')
        fx.build(overrides={'vcs': {'settings': {'ssh_key': ''}}}, root_extra={'gitlab_ssh_key': '/root/key'})
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))
        fx.build(roles=())
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))

    def test_layer_off_or_unreadable_registry_is_the_default(self):
        import registry
        fx = lf.LigaFixture(self).env().build()
        with open(os.path.join(fx.deai, 'spaces.json'), 'w', encoding='utf-8') as f:
            f.write('{not json')
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))
        os.environ.pop('DEAI_HOME')
        os.environ['DC_TASKS_FILE'] = '/nonexistent/tasks.json'
        self.assertEqual(registry._ssh_key(), os.path.expanduser('~/.ssh/gitlab_ed25519'))


class CommentsInIsolation(unittest.TestCase):
    """Д6: ізольований прогін читає облікові коментарів із запису лише в ТИМЧАСОВОМУ домі; у справжньому — `comments-unconfigured`."""

    def route(self, fx):
        sp = _liga(fx)
        with spaces.request_space('legacy'):
            prov, _err = serve.comments_provider(sp)
            return serve.comments_route(sp, prov)

    def test_temp_home_gives_the_fixture_context(self):
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        _mod, ctx, _ch = self.route(fx)
        self.assertEqual((ctx['settings']['url'], ctx['secrets']['key']), (lf.SB_URL, lf.SB_KEY))

    def test_real_home_is_refused(self):
        fx = lf.LigaFixture(self).env(DC_TASKS_FILE='/nonexistent/tasks.json').build()
        with mock.patch.object(isolation, 'real_home', lambda home: True):
            with self.assertRaises(deai_modules.ModuleError) as cm:
                self.route(fx)
        self.assertEqual(cm.exception.code, 'comments-unconfigured')
        self.assertIn('«Підключення»', cm.exception.message)

    def test_non_isolated_uses_the_record_in_any_home(self):
        fx = lf.LigaFixture(self).env().build()
        with mock.patch.object(isolation, 'real_home', lambda home: True):
            _mod, ctx, _ch = self.route(fx)
        self.assertEqual(ctx['settings']['url'], lf.SB_URL)

    def test_a_missing_record_is_unconfigured_not_the_root(self):
        fx = lf.LigaFixture(self).env().build(roles=(), root_extra={'supabase_url': lf.SB_URL, 'supabase_key': lf.SB_KEY})
        sp = _liga(fx)
        with spaces.request_space('legacy'):
            prov, _err = serve.comments_provider(sp)
        self.assertIsNone(prov)


class DashboardSyncWithoutLegacy(unittest.TestCase):
    def test_no_dashboard_record_means_no_provider_even_with_the_service_key(self):
        import overview_push
        fx = lf.LigaFixture(self).env(SUPABASE_URL=lf.SB_URL, SUPABASE_SERVICE_KEY='service-key-alpha').build(roles=())
        self.assertEqual(overview_push._target(_liga(fx)), (None, None, False))
        self.assertFalse(hasattr(overview_push, '_legacy_config'))

    def test_with_the_record_the_module_ctx_is_used(self):
        import overview_push
        fx = lf.LigaFixture(self).env().build()
        mod, ctx, legacy = overview_push._target(_liga(fx))
        self.assertEqual((mod.id, ctx['settings']['url'], legacy), ('supabase-dashboard', lf.SB_URL, True))


class TextsNameTheConnectionsScreen(unittest.TestCase):
    def test_no_text_sends_the_person_to_tasks_json(self):
        import dashboard
        import notify
        import tracker
        for text in (serve.COMMENTS_UNCONFIGURED, dashboard.UNCONFIGURED, notify.UNCONFIGURED, tracker.UNCONFIGURED):
            self.assertIn('«Підключення»', text)
            for bad in ('tasks.json', 'jira_base', 'JIRA_EMAIL', 'JIRA_TOKEN', 'supabase_url'):
                self.assertNotIn(bad, text)


class ProviderCallersPinTheSpace(unittest.TestCase):
    """Аудит (Р4): `provider(<роль>)` БЕЗ простору мовчки дає `None`, коли простір запиту не зафіксовано (раніше — `Implicit`). Дозволені лише ті
    виклики, що йдуть із потоку запиту (простір фіксує `task_anywhere`/`set_request_space`) чи обгорнутого `_in_space` фонового потоку; новий
    однопараметровий виклик — свідоме рішення з правкою цього списку. Решта викликів (`bin/*`, `serve.comments_provider`) передають `space` явно."""

    ALLOWED = {('app/serve.py', 'team_resolve'): 'dashboard', ('app/serve.py', 'tracker_resolve'): 'tracker',
               ('app/serve.py', 'notify_resolve'): 'notify', ('app/serve.py', 'vcs_provider'): 'vcs',
               ('app/serve.py', '_publish'): 'publish', ('app/serve.py', '_overview_sync'): 'dashboard',
               ('app/serve.py', '_preview_password'): 'publish'}

    @staticmethod
    def scan(tree):
        """`{імʼя функції: роль}` для викликів `<щось>.provider('<роль>')` з ОДНИМ позиційним аргументом (простір не передано)."""
        import ast
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        out = {}
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'provider' and len(n.args) == 1
                    and not n.keywords and isinstance(n.args[0], ast.Constant)):
                f = n
                while f in parents:
                    f = parents[f]
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        break
                out[getattr(f, 'name', '<module>')] = n.args[0].value
        return out

    @classmethod
    def found(cls):
        import ast
        import glob
        root = os.path.dirname(_HERE)
        out = {}
        for p in sorted(glob.glob(os.path.join(root, 'app', '*.py')) + glob.glob(os.path.join(root, 'bin', '*.py')) + glob.glob(os.path.join(root, 'ops', '*.py'))):
            if os.path.basename(p).startswith('test_'):
                continue
            with open(p, encoding='utf-8') as f:
                for fn, role in cls.scan(ast.parse(f.read())).items():
                    out[(os.path.relpath(p, root), fn)] = role
        return out

    def test_only_the_audited_callers_ask_without_a_space(self):
        self.assertEqual(self.found(), self.ALLOWED)

    def test_the_audit_can_fail(self):
        import ast
        self.assertEqual(self.scan(ast.parse("def f():\n    return deai_modules.provider('tracker')\n")), {'f': 'tracker'})
        self.assertEqual(self.scan(ast.parse("def f(sp):\n    return deai_modules.provider('tracker', sp)\n")), {})
        self.assertEqual(self.scan(ast.parse("x = m.provider('vcs')")), {'<module>': 'vcs'})


if __name__ == '__main__':
    unittest.main()
````


## Додаток Г: `tests/test_no_originals.py` (Task 12, 5 тестів)

````python
import ast
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _docstring_nodes(tree):
    """Вузли-літерали, що є докстрінгами модуля/класу/функції: пояснення про оригінали дозволені, код — ні."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = getattr(n, 'body', None)
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                out.add(b[0].value)
    return out


class NoOriginalsRead(unittest.TestCase):
    """⛔ Оригінали ЛІГИ (корінь `tasks.json`, оточення, `pipeline-feedback`) читає ЛИШЕ `app/liga_migrate.py` (4d-4b). Охоронець — AST:
    рядкові константи, імена, атрибути, визначення й імпорти. Сканує `app/**/*.py` (крім `liga_migrate.py`), `bin/*.py`, `ops/*.py`
    без `test_*`; докстрінги й коментарі не рахуються."""

    STRINGS = {'supabase_url', 'supabase_key', 'jira_base', 'jira_email', 'jira_token', 'gitlab_ssh_key', 'gitlab_host_ip',
               'SUPABASE_URL', 'SUPABASE_KEY', 'SUPABASE_SERVICE_KEY', 'JIRA_EMAIL', 'JIRA_TOKEN'}
    NAMES = {'supabase_from', 'jira_from', 'service_key_config', 'supabase_config', 'jira_config', 'legacy_ctx', 'legacy_module'}
    #: `preview_password` дозволено лише: імʼя функції; `.get`/`.pop('preview_password')`/`['preview_password']` на ЗАДАЧІ (`task`/`t`, також
    #: `(task or {})`); ключ літерала-словника (форма ВІДПОВІДІ API). Будь-що інше — читання кореня.
    TASK_VARS = {'task', 't'}
    #: Єдині свідомі винятки (файл, значення), кожен — з причиною: `LEGACY_MARKERS` (охоронець маркера, живий до 4d-4c) і журнал синку
    #: огляду `OVERVIEW_LOG` (шлях ЖУРНАЛУ, а не облікових).
    ALLOWED = {('app/spaces.py', 'str:gitlab_host_ip'), ('app/spaces.py', 'str:gitlab_ssh_key'), ('app/serve.py', 'str:pipeline-feedback')}

    @staticmethod
    def _files():
        out = []
        for base, _d, fs in os.walk(os.path.join(ROOT, 'app')):
            out += [os.path.join(base, f) for f in fs if f.endswith('.py') and not f.startswith('test_')]
        for sub in ('bin', 'ops'):
            out += [p for p in glob.glob(os.path.join(ROOT, sub, '*.py')) if not os.path.basename(p).startswith('test_')]
        return sorted(p for p in out if os.path.basename(p) != 'liga_migrate.py')

    @classmethod
    def scan(cls, tree):
        """Що в дереві порушує закон: `{'str:<значення>', 'name:<імʼя>', 'preview_password'}`."""
        doc = _docstring_nodes(tree)
        hits = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n not in doc:
                if n.value in cls.STRINGS:
                    hits.add('str:' + n.value)
                if 'pipeline-feedback' in n.value:
                    hits.add('str:pipeline-feedback')
            ident = None
            if isinstance(n, ast.Name):
                ident = n.id
            elif isinstance(n, ast.Attribute):
                ident = n.attr
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                ident = n.name
            elif isinstance(n, ast.alias):
                ident = n.name.split('.')[-1]
            elif isinstance(n, ast.arg):
                ident = n.arg
            if ident in cls.NAMES:
                hits.add('name:' + ident)
        hits |= cls._preview_password_misuse(tree, doc)
        return hits

    @classmethod
    def _is_task(cls, recv):
        if isinstance(recv, ast.BoolOp) and recv.values:
            recv = recv.values[0]
        return isinstance(recv, ast.Name) and recv.id in cls.TASK_VARS

    @classmethod
    def _preview_password_misuse(cls, tree, doc):
        """`'preview_password'` як рядок — лише `<task|t>.get('preview_password')` чи `<task|t>['preview_password']`."""
        allowed = set()
        for n in ast.walk(tree):
            recv = None
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('get', 'pop') and n.args
                    and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'preview_password'):
                recv, const = n.func.value, n.args[0]
            elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == 'preview_password':
                recv, const = n.value, n.slice
            if cls._is_task(recv):
                allowed.add(const)
            if isinstance(n, ast.Dict):
                allowed |= {k for k in n.keys if isinstance(k, ast.Constant) and k.value == 'preview_password'}
        bad = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == 'preview_password'
               and n not in doc and n not in allowed]
        return {'preview_password'} if bad else set()

    def test_the_runtime_does_not_read_originals(self):
        bad = {}
        for p in self._files():
            with open(p, encoding='utf-8') as f:
                hit = self.scan(ast.parse(f.read()))
            rel = os.path.relpath(p, ROOT)
            hit = {h for h in hit if (rel, h) not in self.ALLOWED}
            if hit:
                bad[rel] = sorted(hit)
        self.assertEqual(bad, {})

    def test_the_guard_can_fail(self):
        """Охоронець, який не може впасти, — фікція: кожна форма порушення дає червоне, чисте читання задачі — ні."""
        for src, want in (("cfg.get('supabase_url')", 'str:supabase_url'), ("os.environ.get('JIRA_TOKEN')", 'str:JIRA_TOKEN'),
                          ("os.path.join(h, '.claude', 'pipeline-feedback')", 'str:pipeline-feedback'),
                          ("import x\nx.supabase_from(cfg)", 'name:supabase_from'),
                          ("def legacy_ctx():\n    return 1", 'name:legacy_ctx'),
                          ("cfg.get('preview_password')", 'preview_password'), ("cfg['preview_password']", 'preview_password'),
                          ("cfg.pop('preview_password', None)", 'preview_password')):
            with self.subTest(src=src):
                self.assertIn(want, self.scan(ast.parse(src)))
        self.assertEqual(self.scan(ast.parse("task.get('preview_password')")), set())
        self.assertEqual(self.scan(ast.parse("t['preview_password']")), set())
        self.assertEqual(self.scan(ast.parse("(task or {}).get('preview_password')")), set())
        self.assertEqual(self.scan(ast.parse("r = {'preview_password': pw}")), set())
        self.assertEqual(self.scan(ast.parse('def f():\n    """supabase_url лишилась лише в докстрінгу"""\n    return 1')), set())

    def test_the_scan_sees_the_migration_module(self):
        """Охоронець не порожній: у `liga_migrate.py` (виключеному зі сканування) оригінали справді є."""
        with open(os.path.join(ROOT, 'app', 'liga_migrate.py'), encoding='utf-8') as f:
            self.assertIn('str:supabase_url', self.scan(ast.parse(f.read())))
        self.assertTrue(self._files())


class NoImplicit(unittest.TestCase):
    """⛔ Запасного постачальника `Implicit` нема (4d-4b): модуля `app/implicit.py` нема, ніхто його не імпортує, імені `Implicit` у коді нема."""

    @staticmethod
    def _files():
        out = []
        for base, _d, fs in os.walk(os.path.join(ROOT, 'app')):
            out += [os.path.join(base, f) for f in fs if f.endswith('.py')]
        for sub in ('bin', 'ops'):
            out += glob.glob(os.path.join(ROOT, sub, '*.py'))
        return sorted(p for p in out if not os.path.basename(p).startswith('test_'))

    @staticmethod
    def scan(tree):
        hits = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                hits |= {'import:' + a.name for a in n.names if a.name.split('.')[-1] == 'implicit'}
            elif isinstance(n, ast.ImportFrom):
                if (n.module or '').split('.')[-1] == 'implicit':
                    hits.add('from:implicit')
                hits |= {'import:' + a.name for a in n.names if a.name in ('implicit', 'Implicit')}
            elif isinstance(n, ast.Name) and n.id == 'Implicit':
                hits.add('name:Implicit')
            elif isinstance(n, ast.Attribute) and (n.attr == 'Implicit' or (isinstance(n.value, ast.Name) and n.value.id == 'implicit')):
                hits.add('attr:' + n.attr)
            elif isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == 'Implicit':
                hits.add('def:Implicit')
        return hits

    def test_no_implicit_provider(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'app', 'implicit.py')))
        bad = {}
        for p in self._files():
            with open(p, encoding='utf-8') as f:
                hit = self.scan(ast.parse(f.read()))
            if hit:
                bad[os.path.relpath(p, ROOT)] = sorted(hit)
        self.assertEqual(bad, {})

    def test_the_guard_can_fail(self):
        for src in ('import implicit', 'from app import implicit', 'from implicit import route', 'x = implicit.route(p)',
                    'isinstance(p, deai_modules.Implicit)', 'class Implicit:\n    pass'):
            with self.subTest(src=src):
                self.assertTrue(self.scan(ast.parse(src)), src)
        self.assertEqual(self.scan(ast.parse('import isolation\nisolation.route("x")')), set())


if __name__ == '__main__':
    unittest.main()
````


## Додаток Д: паритет після міграції (Task 15)

### `tests/test_liga_parity_4d4b.py` (14 тестів; таблиці `EXPECT_*` виміряні на прототипі: 23 / 19 / 40 / 97 / 12 листків)

````python
"""Паритет після міграції `AfterMigrationParity4d4b` (етап 4d-4b): ті самі сценарії, що знімок 0.20.0 (`fixtures/liga-migration/before-4d4b.json`), на
МІГРОВАНІЙ ЛІЗІ п'ятьма кроками, НЕізольовано (шлях власника: `DEAI_HOME` + реєстр, без `DC_TASKS_FILE`/`DC_NO_OVERVIEW`; живі тести ізольовані і
цього не доводять). Збір — `after_4d4b_collect.collect_all` (ті самі розділи, що в генераторі знімка, нові підписи функцій; на стендах `differs`/`partial` запис
міняється ПЕРЕД кроком Е, бо Е ці розбіжності й оцінює). Очікуваний перелік відмінностей — ТОЧНИЙ: кожен листок із «було» зі знімка і «стало» буквально.
Мережі нема (`SocketTripwire` + `NoNet`), справжній `~/.deai` стереже `spaces_guard`."""
import json
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'bin'))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4b.json')
STANDS = ('regular', 'differs', 'partial', 'unmigrated', 'plain')
ABSENT = '<absent>'
#: Розділи, що порівнюються окремо буквальними списками (позиційні), а не листками.
SEPARATE = ('/root_keys', '/startup_text')


def _flat(obj, path=''):
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flat(v, '%s/%s' % (path, k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flat(v, '%s[%d]' % (path, i)))
        out[path + '[]'] = len(obj)
    else:
        out[path] = obj
    return out


def _diff(before, after):
    """`{шлях: (було, стало)}` для листків, що відрізняються (відсутній — `ABSENT`), без `SEPARATE`."""
    fb, fa = _flat(before), _flat(after)
    return {k: (fb.get(k, ABSENT), fa.get(k, ABSENT)) for k in sorted(set(fb) | set(fa))
            if not k.startswith(SEPARATE) and fb.get(k, ABSENT) != fa.get(k, ABSENT)}


def _expect(before, after_literals):
    """Очікувана зміна: «було» береться зі ЗНІМКА, «стало» — буквальне значення з таблиці (не обчислене)."""
    fb = _flat(before)
    return {k: (fb.get(k, ABSENT), v) for k, v in after_literals.items()}


EXPECT_REGULAR = {
    '/api/modules/list/git-sync/fields/host_ip': '203.0.113.7',
    '/api/modules/list/git-sync/fields/ssh_key': '~/.ssh/example',
    '/api/modules/list/vercel-publish/fields/password': '<set>',
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/vcs_target/provider/settings/host_ip': '203.0.113.7',
    '/vcs_target/provider/settings/ssh_key': '~/.ssh/example',
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab/target/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/ssh_key': ABSENT,
}

EXPECT_DIFFERS = {
    '/api/modules/list/git-sync/fields/host_ip': '203.0.113.7',
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/registry_ssh': '/other/key',
    '/vcs_target/provider/settings/host_ip': '203.0.113.7',
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
}

EXPECT_PARTIAL = {
    '/api/modules/list/git-sync/fields/host_ip': '203.0.113.7',
    '/api/modules/list/git-sync/fields/ssh_key': '~/.ssh/example',
    '/api/modules/list/vercel-publish/fields/password': '<set>',
    '/api/task/capabilities/notify': None,
    '/api/task/capabilities/tracker': None,
    '/api/tasks_overview/tracker': None,
    '/api/tasks_overview/tracker/error': ABSENT,
    '/api/tasks_overview/tracker/okAt': ABSENT,
    '/api/teams_mute/body/channel': ABSENT,
    '/api/teams_mute/body/code': 'notify-off',
    '/api/teams_mute/body/error': 'сповіщень Teams у просторі нема',
    '/api/teams_mute/body/ok': False,
    '/api/teams_mute/status': 409,
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/capabilities/ok/notify': None,
    '/capabilities/ok/tracker': None,
    '/isolation/notify_state/message': 'сповіщень Teams у просторі нема',
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/provider/in_space/notify/api': None,
    '/provider/in_space/notify/type': 'NoneType',
    '/provider/in_space/tracker/api': None,
    '/provider/in_space/tracker/type': 'NoneType',
    '/vcs_target/provider/settings/host_ip': '203.0.113.7',
    '/vcs_target/provider/settings/ssh_key': '~/.ssh/example',
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab/target/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/ssh_key': ABSENT,
}

EXPECT_UNMIGRATED = {
    '/api/comment_config/channel': None,
    '/api/comment_config/code': 'integrations-off',
    '/api/comment_config/config': None,
    '/api/comment_config/config/key': ABSENT,
    '/api/comment_config/config/shotsBucket': ABSENT,
    '/api/comment_config/config/url': ABSENT,
    '/api/comment_config/module': None,
    '/api/comment_config/status': 409,
    '/api/task/capabilities/comments': None,
    '/api/task/capabilities/dashboard': None,
    '/api/task/capabilities/notify': None,
    '/api/task/capabilities/publish': None,
    '/api/task/capabilities/tracker': None,
    '/api/task/capabilities/vcs': None,
    '/api/task/preview_password': '1100',
    '/api/tasks_overview/team': None,
    '/api/tasks_overview/team/error': ABSENT,
    '/api/tasks_overview/team/tab': ABSENT,
    '/api/tasks_overview/tracker': None,
    '/api/tasks_overview/tracker/error': ABSENT,
    '/api/tasks_overview/tracker/okAt': ABSENT,
    '/api/teams_mute/body/channel': ABSENT,
    '/api/teams_mute/body/code': 'notify-off',
    '/api/teams_mute/body/error': 'сповіщень Teams у просторі нема',
    '/api/teams_mute/body/ok': False,
    '/api/teams_mute/status': 409,
    '/capabilities/error_path/publish': None,
    '/capabilities/error_path/vcs': None,
    '/capabilities/ok/comments': None,
    '/capabilities/ok/dashboard': None,
    '/capabilities/ok/notify': None,
    '/capabilities/ok/publish': None,
    '/capabilities/ok/tracker': None,
    '/capabilities/ok/vcs': None,
    '/isolation/comments_ctx/code': 'module-error',
    '/isolation/comments_ctx/key_set': ABSENT,
    '/isolation/comments_ctx/raised': 'ModuleError',
    '/isolation/comments_ctx/url': ABSENT,
    '/isolation/notify_state/message': 'сповіщень Teams у просторі нема',
    '/isolation/team_rows[1]': 'вимкнено: у просторі нема постачальника командного дашборда',
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
    '/provider/in_space/comments/api': None,
    '/provider/in_space/comments/type': 'NoneType',
    '/provider/in_space/dashboard/api': None,
    '/provider/in_space/dashboard/type': 'NoneType',
    '/provider/in_space/notify/api': None,
    '/provider/in_space/notify/type': 'NoneType',
    '/provider/in_space/publish/api': None,
    '/provider/in_space/publish/type': 'NoneType',
    '/provider/in_space/tracker/api': None,
    '/provider/in_space/tracker/type': 'NoneType',
    '/provider/in_space/vcs/api': None,
    '/provider/in_space/vcs/type': 'NoneType',
    '/registry_ssh': '~/.ssh/gitlab_ed25519',
    '/vcs_target/provider': None,
    '/vcs_target/provider/legacy_texts': ABSENT,
    '/vcs_target/provider/settings/autosync': ABSENT,
    '/vcs_target/provider/settings/branch': ABSENT,
    '/vcs_target/provider/settings/compat': ABSENT,
    '/vcs_target/provider/settings/host_ip': ABSENT,
    '/vcs_target/provider/settings/path': ABSENT,
    '/vcs_target/provider/settings/ssh_key': ABSENT,
    '/vcs_target/task_gitlab/effective/host_ip': ABSENT,
    '/vcs_target/task_gitlab/effective/ssh_key': ABSENT,
    '/vcs_target/task_gitlab/target/branch': ABSENT,
    '/vcs_target/task_gitlab/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab/target/path': ABSENT,
    '/vcs_target/task_gitlab/target/repo': ABSENT,
    '/vcs_target/task_gitlab/target/ssh_key': ABSENT,
    '/vcs_target/task_gitlab/target/task': ABSENT,
    '/vcs_target/task_gitlab_own_key/effective/host_ip': ABSENT,
    '/vcs_target/task_gitlab_own_key/effective/ssh_key': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/branch': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/host_ip': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/path': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/repo': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/ssh_key': ABSENT,
    '/vcs_target/task_gitlab_own_key/target/task': ABSENT,
    '/vcs_target/task_vcs/effective/host_ip': ABSENT,
    '/vcs_target/task_vcs/effective/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/branch': ABSENT,
    '/vcs_target/task_vcs/target/host_ip': ABSENT,
    '/vcs_target/task_vcs/target/path': ABSENT,
    '/vcs_target/task_vcs/target/repo': ABSENT,
    '/vcs_target/task_vcs/target/ssh_key': ABSENT,
    '/vcs_target/task_vcs/target/task': ABSENT,
}

EXPECT_PLAIN = {
    '/provider/implicit_space/comments/api': None,
    '/provider/implicit_space/comments/type': 'NoneType',
    '/provider/implicit_space/dashboard/api': None,
    '/provider/implicit_space/dashboard/type': 'NoneType',
    '/provider/implicit_space/notify/api': None,
    '/provider/implicit_space/notify/type': 'NoneType',
    '/provider/implicit_space/publish/api': None,
    '/provider/implicit_space/publish/type': 'NoneType',
    '/provider/implicit_space/tracker/api': None,
    '/provider/implicit_space/tracker/type': 'NoneType',
    '/provider/implicit_space/vcs/api': None,
    '/provider/implicit_space/vcs/type': 'NoneType',
}

ROOT_KEYS_AFTER_REGULAR = ['current', 'design_work_root', 'design_work_roots', 'profile_repos', 'registry', 'tasks']
ROOT_KEYS_AFTER_DIFFERS = ['current', 'design_work_root', 'design_work_roots', 'gitlab_ssh_key', 'jira_token', 'profile_repos', 'registry', 'tasks']
ROOT_KEYS_AFTER_PARTIAL = ['current', 'design_work_root', 'design_work_roots', 'jira_base', 'jira_email', 'jira_token', 'profile_repos', 'registry', 'supabase_key', 'supabase_url', 'tasks']
ROOT_KEYS_AFTER_UNMIGRATED = ['current', 'design_work_root', 'design_work_roots', 'gitlab_host_ip', 'gitlab_ssh_key', 'jira_base', 'jira_email', 'jira_token', 'preview_password', 'profile_repos', 'registry', 'supabase_key', 'supabase_url', 'tasks']
ROOT_KEYS_AFTER_PLAIN = ['current', 'design_work_root', 'design_work_roots', 'gitlab_host_ip', 'gitlab_ssh_key', 'jira_base', 'jira_email', 'jira_token', 'preview_password', 'profile_repos', 'registry', 'supabase_key', 'supabase_url', 'tasks']

STARTUP_REGULAR = [
    'liga-4d3a: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d3a',
    'liga-4d3b: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d3b',
    'liga-4d3c: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d3c',
    'liga-4d4a: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d4a',
    '  напрямки: записано; записи: 1; нотатки: default-root-differs',
    'liga-4d4b: done — міграцію виконано',
    '  бекап: <stamp>-liga-4d4b',
    '  скопійовано: gitlab_host_ip, gitlab_ssh_key, preview_password; видалено: gitlab_host_ip, gitlab_ssh_key, jira_base, jira_email, jira_token, preview_password, supabase_key, supabase_url',
    '  оригінали видалено з tasks.json; єдина копія — secrets.json і backups/ у домі Deai',
    '  відкат: bin/migrate_liga.py restore <stamp>-liga-4d4b --hold',
    '  раніші кроки (<stamp>-liga-4d3a, <stamp>-liga-4d3b, <stamp>-liga-4d3c, <stamp>-liga-4d4a) — лише після відкату пізніших, у зворотному порядку',
]

STARTUP_UNMIGRATED = [
    'liga-4d3a: skip-held — міграцію вимкнено вручну (held у space.json)',
    'liga-4d3b: skip-held — утримано разом із liga-4d3a (ранній крок вимкнено вручну: held у space.json)',
    'liga-4d3c: skip-held — утримано разом із liga-4d3a (ранній крок вимкнено вручну: held у space.json)',
    'liga-4d4a: skip-held — утримано разом із liga-4d3a (ранній крок вимкнено вручну: held у space.json)',
    'liga-4d4b: skip-held — утримано разом із liga-4d3a (ранній крок вимкнено вручну: held у space.json)',
    '  напрямки ЛІГИ не мігровані — нові задачі лягають у теку простору',
    'ролі ЛІГИ вимкнено: publish (vercel-publish) — skip-held; виправити: python3 bin/migrate_liga.py unhold liga-4d3a, далі: python3 bin/migrate_liga.py run',
    'ролі ЛІГИ вимкнено: comments (supabase-comments) — skip-held; виправити: python3 bin/migrate_liga.py unhold liga-4d3a, далі: python3 bin/migrate_liga.py run',
    'ролі ЛІГИ вимкнено: vcs (git-sync) — skip-held; виправити: python3 bin/migrate_liga.py unhold liga-4d3a, далі: python3 bin/migrate_liga.py run',
    'ролі ЛІГИ вимкнено: dashboard (supabase-dashboard) — skip-held; виправити: python3 bin/migrate_liga.py unhold liga-4d3a, далі: python3 bin/migrate_liga.py run',
    'ролі ЛІГИ вимкнено: tracker (jira-tracker) — skip-held; виправити: python3 bin/migrate_liga.py unhold liga-4d3a, далі: python3 bin/migrate_liga.py run',
    'ролі ЛІГИ вимкнено: notify (supabase-teams) — skip-held; виправити: python3 bin/migrate_liga.py unhold liga-4d3a, далі: python3 bin/migrate_liga.py run',
]


EXPECT = {'regular': EXPECT_REGULAR, 'differs': EXPECT_DIFFERS, 'partial': EXPECT_PARTIAL, 'unmigrated': EXPECT_UNMIGRATED, 'plain': EXPECT_PLAIN}
ROOT_AFTER = {'regular': ROOT_KEYS_AFTER_REGULAR, 'differs': ROOT_KEYS_AFTER_DIFFERS, 'partial': ROOT_KEYS_AFTER_PARTIAL,
              'unmigrated': ROOT_KEYS_AFTER_UNMIGRATED, 'plain': ROOT_KEYS_AFTER_PLAIN}


class AfterMigrationParity4d4b(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import deai_modules
        import after_4d4b_collect as col
        with open(BEFORE, encoding='utf-8') as f:
            cls.before = json.load(f)['stands']
        deai_modules.reset_caches()
        cls.after = col.collect_all()
        cls.wire = cls.after.pop('_wire')
        deai_modules.reset_caches()

    def _diff(self, name):
        return _diff(self.before[name], self.after[name])

    def test_no_network_and_all_stands_present(self):
        # `SocketTripwire` рахує спроби НЕ-loopback з'єднань, які `NoNet`/розтяжка зупинили (жодна не дійшла до мережі); у знімку їх 10 — без `Implicit`
        # і без читання оригіналів спроб не побільшало.
        with open(BEFORE, encoding='utf-8') as f:
            self.assertLessEqual(self.wire, json.load(f)['non_loopback_attempts'])
        self.assertEqual(sorted(self.after), sorted(STANDS))

    def test_snapshot_is_big_enough_to_mean_something(self):
        for name in STANDS:
            self.assertEqual(sorted(self.after[name]), sorted(self.before[name]), name)
            self.assertGreater(len(_flat(self.before[name])), 130 if name == 'plain' else 180, name)

    def test_exact_differences_regular(self):
        self.assertEqual(self._diff('regular'), _expect(self.before['regular'], EXPECT_REGULAR))

    def test_exact_differences_differs(self):
        self.assertEqual(self._diff('differs'), _expect(self.before['differs'], EXPECT_DIFFERS))

    def test_exact_differences_partial(self):
        self.assertEqual(self._diff('partial'), _expect(self.before['partial'], EXPECT_PARTIAL))

    def test_exact_differences_unmigrated(self):
        self.assertEqual(self._diff('unmigrated'), _expect(self.before['unmigrated'], EXPECT_UNMIGRATED))

    def test_exact_differences_plain(self):
        self.assertEqual(self._diff('plain'), _expect(self.before['plain'], EXPECT_PLAIN))

    def test_root_keys_are_literal(self):
        for name in STANDS:
            self.assertEqual(self.after[name]['root_keys'], ROOT_AFTER[name], name)

    def test_startup_lines_are_literal(self):
        self.assertEqual(self.after['regular']['startup_text'], STARTUP_REGULAR)
        self.assertEqual(self.after['unmigrated']['startup_text'], STARTUP_UNMIGRATED)

    def test_expected_diff_is_exact_not_loose(self):
        """Охоронець самого порівняння: зайвий листок і зниклий очікуваний — обидва червоніють на КОЖНОМУ стенді."""
        for name in STANDS:
            exp = _expect(self.before[name], EXPECT[name])
            extra = json.loads(json.dumps(self.after[name]))
            extra['api']['task']['preview_password'] = 'змінено'                         # зайвий листок
            d = _diff(self.before[name], extra)
            self.assertIn('/api/task/preview_password', d)
            self.assertNotEqual(d, exp, name)
            missing = json.loads(json.dumps(self.before[name]))                         # очікувана зміна «не сталась»
            self.assertNotEqual(_diff(self.before[name], missing), exp, name)

    def test_what_a_person_sees_regular(self):
        """Звичайна мігрована ЛІГА: у відповідях API нових відмінностей лише три видимі поля на «Підключенні» (ssh_key, host_ip, «Пароль превʼю: задано»);
        `capabilities`, пароль превʼю, канали й ключі коментарів — РІВНО знімок."""
        api = {k for k in self._diff('regular') if k.startswith('/api/')}
        self.assertEqual(api, {'/api/modules/list/git-sync/fields/host_ip', '/api/modules/list/git-sync/fields/ssh_key',
                               '/api/modules/list/vercel-publish/fields/password'})
        a = self.after['regular']['api']
        self.assertEqual(a['task']['preview_password'], 'pw-alpha')
        self.assertEqual(a['task']['capabilities'], self.before['regular']['api']['task']['capabilities'])
        self.assertEqual(a['comment_config']['config']['key'], 'sb_test_key_alpha')

    def test_conflicting_password_is_overwritten_by_the_root_value(self):
        """Д4: у `differs` секрет `password` був інертним `inert-old`, режим `design-canvas` брав корінь; тепер секрет = значення кореня, пароль превʼю не змінився."""
        self.assertEqual(self.before['differs']['api']['task']['preview_password'], 'pw-alpha')
        self.assertEqual(self.after['differs']['api']['task']['preview_password'], 'pw-alpha')
        self.assertNotIn('/api/task/preview_password', self._diff('differs'))

    def test_differing_ssh_key_stays_the_records_and_registry_follows_it(self):
        """`differs`: запис вигравав (`/other/key`), корінь лишився з нотаткою `differs:gitlab_ssh_key`; реєстр тепер іде ключем запису."""
        self.assertEqual(self.after['differs']['vcs_target']['task_gitlab']['effective']['ssh_key'], self.before['differs']['vcs_target']['task_gitlab']['effective']['ssh_key'])
        self.assertEqual(self.after['differs']['registry_ssh'], '/other/key')
        self.assertIn('gitlab_ssh_key', self.after['differs']['root_keys'])

    def test_unmigrated_loses_all_six_roles(self):
        """Таблиця «стало вимкнено» буквально: усі шість ролей — `None`, публікація/Teams/коментарі відмовляють, пароль превʼю — типовий 1100."""
        a = self.after['unmigrated']
        self.assertEqual({r: a['provider']['in_space'][r]['api'] for r in ('comments', 'dashboard', 'notify', 'publish', 'tracker', 'vcs')},
                         {r: None for r in ('comments', 'dashboard', 'notify', 'publish', 'tracker', 'vcs')})
        self.assertEqual(a['api']['task']['preview_password'], '1100')
        self.assertEqual(a['api']['teams_mute']['status'], 409)
        self.assertEqual(a['api']['teams_mute']['body']['code'], 'notify-off')
        self.assertEqual(a['api']['comment_config']['status'], 409)
        self.assertIsNone(a['vcs_target']['provider'])
        self.assertEqual(a['registry_ssh'], '~/.ssh/gitlab_ed25519')


if __name__ == '__main__':
    unittest.main()
````

### `tests/after_4d4b_collect.py` — діф до генератора знімка (`tests/make_before_4d4b.py`, Додаток Е)

````diff
--- a/tests/make_before_4d4b.py
+++ b/tests/after_4d4b_collect.py
@@ -86,8 +86,8 @@
         _write(os.path.join(rig.space_dir, 'space.json'), {'migrations': {'liga-4d3a': {'held': True}}})
         return rig, sp
     with rig.activate({'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN}), contextlib.redirect_stderr(io.StringIO()):
-        res = lm.run_all()
-    assert [r[1] for r in res] == ['done'] * len(lm.STEPS), res
+        res = [lm.run(step=s) for s in lm.ALL_STEPS[:4]]                       # A–D: як у знімку; Е — ПІСЛЯ підготовки стендів
+    assert res == ['done'] * 4, res
     spj = os.path.join(rig.space_dir, 'space.json')
     with open(spj, encoding='utf-8') as f:
         data = json.load(f)
@@ -104,6 +104,9 @@
         for mid in ('supabase-teams', 'jira-tracker'):
             data['modules'].pop(mid, None)
     _write(spj, data)
+    with rig.activate(), contextlib.redirect_stderr(io.StringIO()):
+        st = lm.run(step=lm.STEP_E)
+    assert st == 'done', st
     return rig, sp
 
 
@@ -193,9 +196,8 @@
         _mod, ctx, legacy = prov
         settings = ctx.get('settings') or {}
         out['provider'] = {'legacy_texts': legacy, 'settings': {k: settings.get(k) for k in ('ssh_key', 'host_ip', 'branch', 'path', 'autosync', 'compat')}}
-        cfg = rig.cfg
         for key, task in cases.items():
-            t = serve.vcs_target(cfg, 'a-1', task, settings)
+            t = serve.vcs_target('a-1', task, settings)
             out[key] = {'target': t, 'effective': {'ssh_key': (t or {}).get('ssh_key') or (os.path.expanduser(settings['ssh_key']) if settings.get('ssh_key') else None),
                                                    'host_ip': (t or {}).get('host_ip') or settings.get('host_ip')}}
     return scrub(out, rig.home)
@@ -203,7 +205,7 @@
 
 def _registry_ssh(rig):
     import registry
-    return rel(registry._ssh_key(rig.cfg), rig.home)
+    return rel(registry._ssh_key(), rig.home)
 
 
 def _startup_text(tmp, name):
@@ -237,7 +239,7 @@
             out['comments_ctx'] = {'url': ctx['settings'].get('url'), 'key_set': bool(ctx['secrets'].get('key'))}
         except Exception as e:  # noqa: BLE001
             out['comments_ctx'] = {'raised': type(e).__name__, 'code': getattr(e, 'code', None)}
-        out['overview_launch_gate'] = {'isolated': serve.implicit.isolated()}
+        out['overview_launch_gate'] = {'isolated': serve.isolation.isolated()}
         serve.deai_modules.reset_caches()
     return scrub(out, rig.home)
 
@@ -282,46 +284,23 @@
     return snap
 
 
-def _source_commit():
-    """Коміт коду, з якого знято знімок (код 0.20.0 = `0d52a74`; після нього лише docs 4d-4b). Зашито."""
-    return '0d52a74'
 
-
-def _code_differs_from_source():
-    """`True`, якщо `app/`/`bin/` відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — у `ROOT` нема `.git`
-    (заморожена копія з `git archive`: довіряємо рецепту). Закрито за замовчуванням усередині git-теки."""
-    if not os.path.lexists(os.path.join(ROOT, '.git')):
-        return None
-    try:
-        top = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=30)
-        if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
-            return True
-        src = _source_commit()
-        if subprocess.run(['git', '-C', ROOT, 'cat-file', '-e', src + '^{commit}'], capture_output=True, timeout=30).returncode != 0:
-            return True
-        diff = subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', src, '--', 'app', 'bin', 'ops'], capture_output=True, timeout=60)
-        untracked = subprocess.run(['git', '-C', ROOT, 'ls-files', '--others', '--exclude-standard', '--', 'app', 'bin', 'ops'],
-                                   capture_output=True, text=True, timeout=60)
-    except (OSError, subprocess.SubprocessError):
-        return True
-    return untracked.returncode != 0 or diff.returncode != 0 or bool(untracked.stdout.strip())
+def collect_all():
+    import spaces_guard
+    real = spaces_guard.snapshot()
+    out = {}
+    with tempfile.TemporaryDirectory(prefix='after-4d4b-') as tmp:
+        tmp = os.path.normpath(tmp)
+        home = os.path.join(tmp, 'home')
+        os.makedirs(home)
+        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire, mock.patch('urllib.request.urlopen', NoNet()):
+            for n in CLEAN:
+                os.environ.pop(n, None)
+            for name in STANDS:
+                out[name] = _scenarios(tmp, name)
+            out['_wire'] = wire.count
+    spaces_guard.assert_untouched(real)
+    return out
 
-
-def main(argv=None):
-    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
-    ap.add_argument('--out', default=OUT_DEFAULT)
-    args = ap.parse_args(argv)
-    if os.path.realpath(args.out) == os.path.realpath(OUT_DEFAULT) and _code_differs_from_source():
-        print('⛔ make_before_4d4b: app/, bin/ або ops/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
-              'Запускай із замороженої копії (git archive %s | tar -x -C <тека>), див. докстрінг.'
-              % (_source_commit(), _source_commit()), file=sys.stderr)
-        sys.exit(2)
-    snap = make()
-    os.makedirs(os.path.dirname(args.out), exist_ok=True)
-    with open(args.out, 'w', encoding='utf-8') as f:
-        f.write(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
-    print('знімок записано:', args.out)
-
-
 if __name__ == '__main__':
-    main()
+    json.dump(collect_all(), open(sys.argv[1], 'w'), ensure_ascii=False, indent=1, sort_keys=True)
````


## Додаток Е: `tests/make_before_4d4b.py` (Task 1; генератор знімка, запускається ЛИШЕ з замороженої копії `v0.20.0`)

````python
#!/usr/bin/env python3
"""Генератор знімка поведінки оригіналів і запасного постачальника ЛІГИ на 0.20.0: `tests/fixtures/liga-migration/before-4d4b.json` (етап 4d-4b, Task 1).

Знімок знято ДО змін коду (код = 0.20.0, коміт `0d52a74`, тег `v0.20.0`) і лишається в репо еталоном паритету п'ятого кроку міграції ЛІГИ
(`liga-4d4b`): після 0.21 людина з мігрованою ЛІГОЮ бачить ті самі `capabilities`, пароль превʼю, канали, ключі SSH, що й до кроку, хоч оригінали
кореня `tasks.json` видалено, запасного постачальника (`Implicit`) нема, а закон ізоляції не читає кореня. Тести (`tests/test_liga_migrate_e.py`,
клас `AfterMigrationParity4d4b`) читають JSON, а не переганяють генератор. Запуск на НОВОМУ коді дасть не «до», а «після»: еталон не перезаписувати.

Спільні помічники (`Rig`, `NoNet`, `SocketTripwire`, `Server`, `scrub`, `rel`, `CLEAN`, `_write`, вигадані константи, `_call`) ІМПОРТУЮТЬСЯ з
`make_before_4d3a.py`/`make_before_4d3b.py`: друга копія розійшлась би.

П'ять стендів (усі — НЕізольовані: без `DC_TASKS_FILE`/`DC_NO_OVERVIEW`, шлях власника; ізольований шлях — секція `isolation`):
  * `regular`    — ЛІГА мігрована кроками A–D, усі вісім оригіналів у корені РІВНІ записам;
  * `differs`    — те саме, але записи після міграції відрізняються від кореня (ssh_key, токен Jira, інертний пароль превʼю);
  * `partial`    — те саме, але записів `supabase-teams` і `jira-tracker` нема (часткова міграція);
  * `unmigrated` — ЛІГА з `held` на кроці 4d-3a: ролі веде `Implicit` (еталон таблиці «стало вимкнено»);
  * `plain`      — звичайний простір без інтеграцій.
Секції: `capabilities` (+ `error_path`: нечитабельний `space.json`), `provider` (для простору ЛІГА і для неявного простору запиту), `api`
(`/api/task`: пароль превʼю й гейт, канал; `/api/modules`; `/api/comment-config`; `/api/teams-mute`; `/api/tasks`), `vcs_target` (цілі й
ЕФЕКТИВНІ ключ і IP), `registry_ssh` (ключ git реєстру), `startup_text` (рядки старту), `root_keys` (ключі кореня `tasks.json`),
`isolation` (форми відповідей ізольованого прогону: рядки команди, статуси, мовчання Teams, `ctx` коментарів).

⚠️ ПІДПИСИ 0.20.0: `serve.vcs_target(cfg, tid, task, settings)`, `registry._ssh_key(cfg)`, `serve.preview_password(cfg, task)`; у новому коді —
`vcs_target(tid, task, settings)`, `_ssh_key()`, `preview_password(task, space)`. Тести «після» кличуть нову форму. Не міняти тут.

Запуск (з кореня репо): проти ЗАМОРОЖЕНОЇ копії старого коду:
    D=$(mktemp -d) && git archive v0.20.0 | tar -x -C "$D" && cp tests/make_before_4d4b.py "$D/tests/"
    HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4b.py" --out tests/fixtures/liga-migration/before-4d4b.json
Запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від `0d52a74`, генератор ВІДМОВЛЯЄ (код виходу 2).

⛔ Ізоляція: власні тимчасові `HOME` і `DEAI_HOME`, чисте оточення, жодної мережі (розтяжка сокетів + `urlopen`), шпигуни замість
`serve._registry_push`/`serve.git_autocommit`/`Handler._overview_sync`; справжній `~/.deai` стереже `spaces_guard`; порти 8765/4317 не
чіпаємо (ефемерний порт loopback). Детермінований: два прогони побайтово однакові (часові штампи бекапів замінено `<stamp>`).
"""
import argparse
import io
import json
import contextlib
import os
import re
import subprocess
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

from make_before_4d3a import (CLEAN, JIRA_BASE, JIRA_ENV_EMAIL, JIRA_ENV_TOKEN, SB_KEY, SB_URL, SPACE_ID, NoNet, Rig, Server,  # noqa: E402
                              SocketTripwire, _write, rel, scrub)
from make_before_4d3b import _call  # noqa: E402

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4b.json')
STANDS = ('regular', 'differs', 'partial', 'unmigrated', 'plain')
ROLES = ('comments', 'dashboard', 'notify', 'publish', 'tokens', 'tracker', 'vcs')
SSH, HOSTIP, PW = '~/.ssh/example', '203.0.113.7', 'pw-alpha'
STAMP = re.compile(r'[0-9]{8}-[0-9]{6}(-[0-9]{1,3})?')


def _stand(tmp, name, migrate=True):
    """`(rig, sp)`: ЛІГА чи звичайний простір (`plain`); ЛІГА мігрована справжнім `run_all()` (кроки A–D) — як у людини (`migrate=False` — перший старт, ще не мігровано)."""
    import liga_migrate as lm
    base = name.split('-')[0]                             # `<стенд>-startup` — окрема тека, той самий стенд
    rig = Rig(tmp, name)
    cfg = rig.config()
    cfg.update(jira_email=JIRA_ENV_EMAIL, jira_token=JIRA_ENV_TOKEN, gitlab_host_ip=HOSTIP, preview_password=PW,
               registry={'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'})
    _write(rig.tasks_path, cfg)
    liga = rig.registry()
    sp = liga
    if base == 'plain':
        plain_dir = os.path.join(rig.home, 'plain-space')
        _write(os.path.join(plain_dir, 'space.json'), {})
        pdir = os.path.join(plain_dir, 'p-1')
        _write(os.path.join(pdir, 'iterations.json'), {'iterations': [], 'publish_url': None})
        _write(os.path.join(plain_dir, 'tasks.json'), {'tasks': {'p-1': {'dir': pdir, 'title': 'Plain demo'}}, 'current': 'p-1'})
        sp = {'id': 'plain', 'path': plain_dir, 'legacy': False, 'integrations': False}
        _write(os.path.join(rig.deai, 'spaces.json'), {'version': 1, 'current': 'legacy', 'spaces': [liga, sp]})
        return rig, sp
    if not migrate and base != 'unmigrated':
        return rig, sp
    if base == 'unmigrated':
        _write(os.path.join(rig.space_dir, 'space.json'), {'migrations': {'liga-4d3a': {'held': True}}})
        return rig, sp
    with rig.activate({'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN}), contextlib.redirect_stderr(io.StringIO()):
        res = lm.run_all()
    assert [r[1] for r in res] == ['done'] * len(lm.STEPS), res
    spj = os.path.join(rig.space_dir, 'space.json')
    with open(spj, encoding='utf-8') as f:
        data = json.load(f)
    sec_path = os.path.join(rig.deai, 'secrets.json')
    if base == 'differs':
        data['modules']['git-sync']['settings']['ssh_key'] = '/other/key'
        with open(sec_path, encoding='utf-8') as f:
            sec = json.load(f)
        sec['legacy']['vercel-publish'] = {'password': 'inert-old'}
        sec['legacy']['jira-tracker'] = {'token': 'other-token'}
        _write(sec_path, sec)
        os.chmod(sec_path, 0o600)
    elif base == 'partial':
        for mid in ('supabase-teams', 'jira-tracker'):
            data['modules'].pop(mid, None)
    _write(spj, data)
    return rig, sp


def _capabilities(sp, rig):
    import deai_modules as dm
    out = {'ok': dm.capabilities(sp)}
    spj = os.path.join(sp['path'], 'space.json')
    keep = None
    if os.path.isfile(spj):
        with open(spj, 'rb') as f:
            keep = f.read()
    _write(spj, '{not json')                              # нечитабельний space.json: `error_path`
    dm.reset_caches()
    out['error_path'] = dm.capabilities(sp)
    if keep is not None:
        with open(spj, 'wb') as f:
            f.write(keep)
    else:
        os.remove(spj)
    dm.reset_caches()
    return out


def _provider(sp):
    import deai_modules as dm
    import spaces

    def one(role, space=None):
        try:
            p = dm.provider(role, space) if space is not None else dm.provider(role)
            return {'api': dm.api_value(p), 'type': type(p).__name__}
        except Exception as e:  # noqa: BLE001
            return {'raised': type(e).__name__, 'code': getattr(e, 'code', None)}
    out = {'in_space': {r: one(r, sp) for r in ROLES}}
    with spaces.request_space(None):                       # простір запиту НЕ зафіксовано: неявний простір (0.20.0 — `Implicit`)
        out['implicit_space'] = {r: one(r) for r in ROLES}
    return out


def _api(rig, sp):
    tid = 'p-1' if sp['id'] == 'plain' else 'a-1'
    import serve
    out = {}
    spy = mock.MagicMock(return_value=False)
    with mock.patch.object(serve, '_registry_push', spy), mock.patch.object(serve, 'git_autocommit', lambda *a, **k: None), \
            mock.patch.object(serve.Handler, '_overview_sync', lambda *a, **k: None), Server() as srv:
        st, body = srv.req('GET', '/api/task', task=tid)
        keys = ('preview_password', 'preview_password_custom', 'preview_gate', 'comment_channel')
        out['task'] = {'status': st, **{k: (body or {}).get(k, '<absent>') for k in keys},
                       'capabilities': ((body or {}).get('space') or {}).get('capabilities'),
                       'compat': ((body or {}).get('space') or {}).get('compat', '<absent>')}
        st, body = srv.req('GET', '/api/modules?space=' + sp['id'])
        mods = (body or {}).get('modules') or []
        def fields(m):          # значення простих полів і «задано» секретів; без підписів (`label`) — вони не про поведінку
            return {f['key']: ('<set>' if f.get('set') else f.get('value', '<unset>')) if f.get('type') == 'secret' else f.get('value', '<unset>')
                    for f in (m.get('settings') or []) if isinstance(f, dict) and f.get('key')}
        out['modules'] = {'status': st, 'list': {m['id']: {'enabled': m.get('enabled'), 'implicit': m.get('implicit'), 'status': m.get('status'),
                                                              'fields': fields(m)} for m in mods}}
        st, body = srv.req('GET', '/api/comment-config?ch=project&it=it1', task=tid)
        body = body if isinstance(body, dict) else {}
        out['comment_config'] = {'status': st, 'module': body.get('module'), 'channel': body.get('channel'), 'config': body.get('config'),
                                 'code': body.get('code')}
        st, body = srv.req('GET', '/api/teams-mute', task=tid)
        out['teams_mute'] = {'status': st, 'body': body if isinstance(body, dict) else None}
        st, body = srv.req('GET', '/api/tasks-overview?refresh=1', task=tid)
        body = body if isinstance(body, dict) else {}
        team = body.get('team')
        out['tasks_overview'] = {'status': st, 'team': (None if team is None else {k: team.get(k) for k in ('error', 'tab') if isinstance(team, dict)}),
                                 'tracker': body.get('tracker')}
    return scrub(out, rig.home)


def _vcs_target(rig, sp):
    """Цілі `vcs_target` і ЕФЕКТИВНІ ключ та IP (ціль, інакше налаштування запису): саме вони доходять до git."""
    import serve
    cases = {'task_gitlab': {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1'}},
             'task_gitlab_own_key': {'gitlab': {'repo': 'git@example.com:o/r.git', 'path': 'mockup/a-1', 'ssh_key': '/own/key', 'host_ip': '198.51.100.9'}},
             'task_vcs': {'vcs': {'repo': 'git@example.com:o/r.git'}}}
    out = {}
    with serve.spaces.request_space(sp['id']):
        try:
            prov = serve.vcs_provider()
        except Exception as e:  # noqa: BLE001
            return {'raised': type(e).__name__}
        if prov is None:
            return {'provider': None}
        _mod, ctx, legacy = prov
        settings = ctx.get('settings') or {}
        out['provider'] = {'legacy_texts': legacy, 'settings': {k: settings.get(k) for k in ('ssh_key', 'host_ip', 'branch', 'path', 'autosync', 'compat')}}
        cfg = rig.cfg
        for key, task in cases.items():
            t = serve.vcs_target(cfg, 'a-1', task, settings)
            out[key] = {'target': t, 'effective': {'ssh_key': (t or {}).get('ssh_key') or (os.path.expanduser(settings['ssh_key']) if settings.get('ssh_key') else None),
                                                   'host_ip': (t or {}).get('host_ip') or settings.get('host_ip')}}
    return scrub(out, rig.home)


def _registry_ssh(rig):
    import registry
    return rel(registry._ssh_key(rig.cfg), rig.home)


def _startup_text(tmp, name):
    """Рядки ПЕРШОГО старту (`liga_migrate.startup`) на стенді, що ще не мігрований (`regular`) чи утриманий (`unmigrated`)."""
    import liga_migrate as lm
    rig, sp = _stand(tmp, name + '-startup', migrate=False)
    buf = io.StringIO()
    with rig.activate({'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN}), contextlib.redirect_stderr(buf):
        lm.startup()
    return STAMP.sub('<stamp>', buf.getvalue()).splitlines()


def _isolation(rig, sp):
    """Форми відповідей ІЗОЛЬОВАНОГО прогону (`DC_TASKS_FILE`): рядки команди, статуси, мовчання Teams, `ctx` коментарів (де беруться облікові)."""
    import dashboard
    import serve
    out = {}
    env = {'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1'}
    with mock.patch.dict(os.environ, env), serve.spaces.request_space(sp['id']):
        serve.deai_modules.reset_caches()
        out['team_rows'] = list(serve.team_rows(refresh=True))
        out['tracker'] = serve.tracker_snapshot(['DEMO-1'], refresh=True)
        try:
            out['notify_state'] = serve.notify_call('mute_state')
        except Exception as e:  # noqa: BLE001
            out['notify_state'] = {'raised': type(e).__name__, 'message': str(e)[:120]}
        try:
            space = serve.spaces.active_space()
            prov, err = serve.comments_provider(space)
            mod, ctx, _ch = serve.comments_route(space, prov)
            out['comments_ctx'] = {'url': ctx['settings'].get('url'), 'key_set': bool(ctx['secrets'].get('key'))}
        except Exception as e:  # noqa: BLE001
            out['comments_ctx'] = {'raised': type(e).__name__, 'code': getattr(e, 'code', None)}
        out['overview_launch_gate'] = {'isolated': serve.implicit.isolated()}
        serve.deai_modules.reset_caches()
    return scrub(out, rig.home)


def _scenarios(tmp, name):
    rig, sp = _stand(tmp, name)
    out = {}
    with rig.activate():
        import deai_modules as dm
        dm.reset_caches()
        with open(rig.tasks_path, encoding='utf-8') as f:
            out['root_keys'] = sorted(json.load(f))
        out['capabilities'] = _capabilities(sp, rig)
        out['provider'] = _provider(sp)
        out['api'] = _api(rig, sp)
        if name != 'plain':
            out['vcs_target'] = _vcs_target(rig, sp)
            out['registry_ssh'] = _registry_ssh(rig)
            out['isolation'] = _isolation(rig, sp)
        dm.reset_caches()
    if name in ('regular', 'unmigrated'):
        out['startup_text'] = _startup_text(tmp, name)
    return scrub(out, rig.home)


def make():
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d4b-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire, mock.patch('urllib.request.urlopen', NoNet()):
            for n in CLEAN:
                os.environ.pop(n, None)
            snap = {'meta': {'version': '0.20.0', 'source_commit': _source_commit(), 'generator': 'tests/make_before_4d4b.py',
                             'volatile_stripped': ['backup stamps → <stamp>']}, 'stands': {}}
            for name in STANDS:
                snap['stands'][name] = _scenarios(tmp, name)
            snap['non_loopback_attempts'] = wire.count
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.20.0 = `0d52a74`; після нього лише docs 4d-4b). Зашито."""
    return '0d52a74'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — у `ROOT` нема `.git`
    (заморожена копія з `git archive`: довіряємо рецепту). Закрито за замовчуванням усередині git-теки."""
    if not os.path.lexists(os.path.join(ROOT, '.git')):
        return None
    try:
        top = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=30)
        if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
            return True
        src = _source_commit()
        if subprocess.run(['git', '-C', ROOT, 'cat-file', '-e', src + '^{commit}'], capture_output=True, timeout=30).returncode != 0:
            return True
        diff = subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', src, '--', 'app', 'bin', 'ops'], capture_output=True, timeout=60)
        untracked = subprocess.run(['git', '-C', ROOT, 'ls-files', '--others', '--exclude-standard', '--', 'app', 'bin', 'ops'],
                                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return True
    return untracked.returncode != 0 or diff.returncode != 0 or bool(untracked.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if os.path.realpath(args.out) == os.path.realpath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4d4b: app/, bin/ або ops/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
              'Запускай із замороженої копії (git archive %s | tar -x -C <тека>), див. докстрінг.'
              % (_source_commit(), _source_commit()), file=sys.stderr)
        sys.exit(2)
    snap = make()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print('знімок записано:', args.out)


if __name__ == '__main__':
    main()
````


## Додаток Ж: прототипні hunk-и коду

### Новий файл `app/isolation.py`

````python
"""Закон ізоляції й шви тестів (4d-4b; раніше жив у `app/implicit.py`, який зник разом із запасним постачальником).

Чистий модуль: імпортує лише `os` (і `pwd` у `real_home`) — без `spaces`/`serve`/`deai_modules`, тож цикл імпорту неможливий (як було в `implicit.py`).

* `isolated()` — «стан не справжній цієї машини»: `DC_TASKS_FILE` чи `DC_NO_OVERVIEW`. Зі спільного стану ЛІГИ (Supabase, Jira, Teams) ізольований
  прогін не ходить ніколи; чи є шов — вирішує `route()`.
* `route(role)` — куди йти запису `shared_state`: `('fake', шлях)` → `('isolated', None)` → `('live', None)`. Порядок однаковий для всіх ролей; що
  повертати в кожному випадку, вирішує роль (форми відповідей 0.15.0 різні).
* `real_home(home)` — чи `home` — справжній `~/.deai` машини (за `pwd`, а не за `$HOME`: тест підміняє `HOME`, але не підміняє пароль ОС).
  ⛔ Суворіша за `liga_migrate._real_home`: для закону ізоляції «справжній» — лише `pwd`-дім; `<HOME>/.deai` тесту — НЕ справжній.
"""
import os

#: Шви тестів: роль → змінна оточення з шляхом до локального JSON замість живої бази. Лише для ролей, що ходять у спільний стан.
FAKE_ENV = {'dashboard': 'DC_TEAM_FAKE', 'tracker': 'DC_TRACKER_FAKE', 'notify': 'DC_TEAMS_FAKE'}


def isolated():
    """⛔ Закон ізоляції: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` — «стан не справжній цієї машини»; зі спільного стану ЛІГИ не ходимо."""
    return bool(os.environ.get('DC_TASKS_FILE') or os.environ.get('DC_NO_OVERVIEW'))


def route(role):
    """`('fake', шлях)` → `('isolated', None)` → `('live', None)` для запису `shared_state` ролі `role`. Шов (`FAKE_ENV[role]`) раніше за
    ізоляцію; роль без шва (`comments`, `vcs`, `publish`) — лише ізольовано чи живо."""
    env = FAKE_ENV.get(role)
    fake = os.environ.get(env) if env else None
    if fake:
        return 'fake', fake
    if isolated():
        return 'isolated', None
    return 'live', None


def real_home(home):
    """Чи `home` (шлях до `DEAI_HOME`) — справжній `~/.deai` машини: `<дім з пароля ОС>/.deai`, порівняння за `realpath`. Не вдалось
    дізнатись дім ОС (`pwd` нема, `KeyError`) — вважаємо справжнім (безпечніший бік: облікових із цієї теки не беремо)."""
    try:
        import pwd
        real = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, '.deai')
    except (ImportError, KeyError, OSError):
        return True
    try:
        return os.path.realpath(os.path.expanduser(home)) == os.path.realpath(real)
    except (OSError, ValueError, TypeError):
        return True
````


### `app/liga_migrate.py`

````diff
--- a/app/liga_migrate.py
+++ b/app/liga_migrate.py
@@ -37,8 +37,8 @@
 from urllib.parse import urlsplit
 
 import deai_modules
-import implicit
 import install_config
+import isolation
 import spaces
 import tracks as tracks_core
 from atomic_io import TMP_SUFFIX, atomic_write_json
@@ -55,7 +55,7 @@
 COMPAT = 'comment-layer'
 SKIP_CODES = ('skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-held', 'skip-no-path', 'skip-path-in-git',
               'skip-space-json-unreadable', 'skip-registry-unreadable', 'skip-tasks-unreadable', 'skip-nothing', 'skip-busy', 'skip-integrations-off')
-ABORT_CODES = ('abort-provider', 'abort-internal', 'abort-lock', 'abort-tracks', 'abort-records')
+ABORT_CODES = ('abort-provider', 'abort-internal', 'abort-lock', 'abort-tracks', 'abort-records', 'abort-originals', 'abort-verify')
 _REASONS = {
     'skip-layer-off': 'шар просторів вимкнено: міграція не біжить',
     'skip-no-liga': 'у реєстрі нема простору ЛІГА',
@@ -74,6 +74,8 @@
     'abort-internal': 'непередбачена помилка розрахунку: міграція нічого не пише',
     'abort-tracks': 'розраховані напрямки не збігаються з адаптером за id чи дефолтом: міграція нічого не пише',
     'abort-records': 'tasks.json не записано: space.json не змінено, наступний запуск почне заново',
+    'abort-originals': 'tasks.json ЛІГИ не записано: копії вже лежать у записах, нічого не видалено — наступний запуск почне заново',
+    'abort-verify': 'скопійоване значення не збіглося з планом після запису: нічого не видалено з tasks.json',
     'abort-lock': 'міжпроцесний замок недоступний (flock не працює на цій файловій системі): міграція нічого не пише, щоб не йти без замка',
 }
 
@@ -306,13 +308,66 @@
         return '@' in urlsplit(url).netloc
     except ValueError:
         return True
+
+
+#: ⛔ Читачі ОРИГІНАЛІВ кореня `tasks.json`/оточення/`pipeline-feedback` — ЄДИНІ копії на весь код (4d-4b: з `install_config` вони видалені).
+#: Міграція ще читає оригінали на першому старті старої установки (кроки A–C), далі їх тримає лише вона. Тіла — байт у байт ті, що були
+#: в `install_config.supabase_from`/`jira_from`; ізоляція — `isolation.isolated()`.
+def _supabase_from(cfg):
+    """`(url, key)` за вже прочитаним коренем старого `tasks.json` (`cfg`; не словник — як порожній) — та сама логіка й ті самі
+    джерела, що в `supabase_config()` (його тіло, винесене сюди без змін, щоб міграція ЛІГИ `liga_migrate.plan` брала облікові
+    ТИМИ САМИМИ правилами, а не копією; ізоляція `isolation.isolated()` — як там)."""
+    cfg = cfg if isinstance(cfg, dict) else {}
+    sources = [(cfg.get('supabase_url'), cfg.get('supabase_key'))]
+    if not isolation.isolated():                        # ⛔ в ізольованому прогоні оточення не читаємо (див. докстрінг)
+        sources.append((os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY')))
+    for url, key in sources:
+        if not (isinstance(url, str) and isinstance(key, str)):
+            continue
+        url, key = url.strip(), key.strip()
+        # адреса — повністю `https://<хост>[:порт][/]`; ключ — друковний ASCII без пробілів (див. докстрінг)
+        if install_config._SUPABASE_URL_RE.fullmatch(url) and install_config._SUPABASE_KEY_RE.fullmatch(key):
+            return url.rstrip('/'), key
+    return None, None
+
+
+
+
+def _jira_from(cfg):
+    """`(base, email, token)` за вже прочитаним коренем старого `tasks.json` (`cfg`) — тіло `jira_config()`, винесене без змін
+    (див. його докстрінг: джерела, порядок, ізоляція). Спільний помічник для `liga_migrate.plan`: ті самі правила, не копія."""
+    base = cfg.get('jira_base') if isinstance(cfg, dict) else None
+    if not isinstance(base, str):
+        return None, None, None
+    base = base.strip()
+    if not install_config._SUPABASE_URL_RE.fullmatch(base):           # та сама форма адреси, що в `supabase_config`
+        return None, None, None
 
+    def from_file(name):
+        try:
+            with open(os.path.expanduser('~/.claude/pipeline-feedback/' + name), encoding='utf-8') as f:
+                return f.read()
+        except (OSError, ValueError):
+            return None
+    def pick(env, name, key, valid):
+        if isolation.isolated():                         # ⛔ лише корінь файла задач (ключ `jira_email`/`jira_token`)
+            raw = cfg.get(key)
+            return raw.strip() if isinstance(raw, str) and valid(raw.strip()) else None
+        for raw in (os.environ.get(env), from_file(name)):          # оточення раніше за файл; порожнє/негодне — далі
+            if isinstance(raw, str) and valid(raw.strip()):
+                return raw.strip()
+        return None
+    email = pick('JIRA_EMAIL', 'jira-email', 'jira_email', lambda v: bool(v) and v.isprintable())
+    token = pick('JIRA_TOKEN', 'jira-token', 'jira_token', lambda v: install_config._SUPABASE_KEY_RE.fullmatch(v) is not None)
+    return (base.rstrip('/'), email, token) if (email and token) else (None, None, None)
 
+
+
 def _role_entries(cfg, present):
     """`{role: (module, ознака_пропуску | None, запис space.json | None, секрети | None)}` за вже прочитаним `cfg`; облікові — ті
     самі функції `install_config`, що в сервері (`supabase_from`/`jira_from`): джерела й порядок не продубльовано."""
-    sb_url, sb_key = install_config.supabase_from(cfg)
-    base, email, token = install_config.jira_from(cfg)
+    sb_url, sb_key = _supabase_from(cfg)
+    base, email, token = _jira_from(cfg)
     spec = {
         'tracker': ((base and email and token), 'no-jira', {'base': base, 'email': email}, {'token': token}),
         'dashboard': ((sb_url and sb_key), 'no-supabase', {'url': sb_url, 'table': DASHBOARD_TABLE, 'compat': COMPAT}, {'key': sb_key}),
@@ -344,7 +399,7 @@
     `comments` → `supabase-comments`: адреса й ключ — `install_config.supabase_from` (ті самі джерела, що `serve._comments_legacy_ctx`);
     кошик — `install_config.LEGACY_SHOTS_BUCKET`. `vcs` → `git-sync`: налаштування ті самі, що в `serve._vcs_legacy_ctx` (тест зіставляє).
     ⛔ `ssh_key`/`host_ip`/`repo` НЕ копіюємо: ключ і IP дає корінь (`_vcs_ssh`), репо — ціль задачі; секретів у `git-sync` нема."""
-    sb_url, sb_key = install_config.supabase_from(cfg)
+    sb_url, sb_key = _supabase_from(cfg)
     out = {}
     for role, mid in ROLE_MODULES_B:
         if mid in present:
@@ -393,6 +448,181 @@
         return isinstance(prov, deai_modules.Module)
     except deai_modules.ModuleError:
         return False
+
+
+#: 4d-4b: вісім «оригіналів» кореня `tasks.json` ЛІГИ і де лежить їхня копія. `kind`: `s` — налаштування запису, `k` — секрет запису.
+#: `copy` — крок Е сам кладе значення в запис, коли там порожньо (4d-3 це свідомо не копіював). Рядки — ТІ САМІ, що були в читачів рантайму
+#: (вони видалені: `install_config.{supabase,jira}_*`, `serve.preview_password`, `_vcs_ssh`); міграція — єдине місце, що їх ще знає.
+SB_MODULES = ('supabase-dashboard', 'supabase-teams', 'supabase-comments')
+ORIGINALS = (
+    ('supabase_url', SB_MODULES, 's', 'url', False),
+    ('supabase_key', SB_MODULES, 'k', 'key', False),
+    ('jira_base', ('jira-tracker',), 's', 'base', False),
+    ('jira_email', ('jira-tracker',), 's', 'email', False),
+    ('jira_token', ('jira-tracker',), 'k', 'token', False),
+    ('gitlab_ssh_key', ('git-sync',), 's', 'ssh_key', True),
+    ('gitlab_host_ip', ('git-sync',), 's', 'host_ip', True),
+    ('preview_password', ('vercel-publish',), 'k', 'password', True),
+)
+ORIGINAL_KEYS = tuple(o[0] for o in ORIGINALS)
+#: Ключі, наявність яких у корені робить файл «файлом ЛІГИ» для `spaces.has_markers` (реєстр без запису ЛІГИ відновлюється з нуля).
+_MARKER_KEYS = ('gitlab_host_ip', 'gitlab_ssh_key')
+
+
+def _fits(v):
+    """Значення можна покласти в запис (`write_secrets`/налаштування `text`): рядок ≤ `MAX_VALUE_LEN`, кодується в UTF-8."""
+    return isinstance(v, str) and len(v) <= deai_modules.MAX_VALUE_LEN and deai_modules._encodable(v)
+
+
+def _effective(key, raw):
+    """Значення, яке віддав би ВИДАЛЕНИЙ читач (після його `strip`/`rstrip('/')`/форми), або `None` — «непридатне» (`unfit`)."""
+    if key in ('supabase_url', 'jira_base'):
+        s = raw.strip() if isinstance(raw, str) else ''
+        ok = install_config._SUPABASE_URL_RE.fullmatch(s) and not _has_userinfo(s)
+        return s.rstrip('/') if ok else None
+    if key in ('supabase_key', 'jira_token'):
+        s = raw.strip() if isinstance(raw, str) else ''
+        return s if install_config._SUPABASE_KEY_RE.fullmatch(s) else None
+    if key == 'jira_email':
+        s = raw.strip() if isinstance(raw, str) else ''
+        return s if s and s.isprintable() else None
+    if key == 'preview_password':
+        if isinstance(raw, bool):                            # `True` — не пароль (читач бачив би «True»): непридатне
+            return None
+        v = str(raw) if isinstance(raw, (int, float)) else raw
+        return v if isinstance(v, str) and v.strip() and _fits(v) else None
+    return raw if isinstance(raw, str) and raw.strip() and _fits(raw) else None        # gitlab_ssh_key / gitlab_host_ip: як є
+
+
+def _holder_ready(norm, mid, key):
+    """Запис `mid` готовий тримати оригінал: є, `enabled`, `shared_state`; для `preview_password` — ще й `compat == design-canvas`
+    (інакше секрет `password` має інший зміст: модуль-режим, а не пароль превʼю ЛІГИ)."""
+    e = norm.get(mid)
+    if not (isinstance(e, dict) and e.get('enabled') is True and e.get('shared_state') is True):
+        return None
+    if key == 'preview_password' and (e.get('settings') or {}).get('compat') != PUBLISH_COMPAT:
+        return None
+    return e
+
+
+def _held(norm, secrets, sid, mid, kind, field):
+    e = norm.get(mid) or {}
+    if kind == 'k':
+        return deai_modules._bucket(secrets, sid, mid).get(field)
+    v = (e.get('settings') or {}).get(field)
+    return v if isinstance(v, str) and v else None
+
+
+def _decide_originals(cfg, norm, secrets, sid, had_markers=None):
+    """ЧИСТИЙ розрахунок кроку Е (нічого не читає з диска): `{'copy_settings': {mid: {поле: значення}}, 'copy_secrets': {mid: {поле:
+    значення}}, 'remove': [ключі], 'kept': [ключі], 'notes': [коди]}`. Правила (спека §1.1): нема в корені — мовчки; непридатне —
+    `unfit:<ключ>`; тримача нема — `no-record:<модуль>`; значення відмінне — `differs:<ключ>` (для `preview_password` — перезапис, Д4,
+    `overwrote:password`); порожнє й копіюємо — у план копії; збіг — у список видалення. Пара Supabase — лише разом: не всі три
+    тримачі — `partial:supabase`, жоден із двох не видаляється. ⛔ Значень у виході НЕМАЄ нікуди, крім `copy_*` (їх пише запис)."""
+    out = {'copy_settings': {}, 'copy_secrets': {}, 'copied': [], 'remove': [], 'kept': [], 'notes': []}
+    notes = out['notes']
+
+    def note(code):
+        if code not in notes:
+            notes.append(code)
+
+    sb_blocked = False
+    present = [o for o in ORIGINALS if cfg.get(o[0]) is not None]
+    if any(o[0] in ('supabase_url', 'supabase_key') for o in present):
+        missing = [m for m in SB_MODULES if not _holder_ready(norm, m, 'supabase_url')]
+        if missing:
+            sb_blocked = True
+            note('partial:supabase')
+            for m in missing:
+                note('no-record:' + m)
+    for key, mods_, kind, field, copyable in present:
+        eff = _effective(key, cfg[key])
+        if eff is None:
+            note('unfit:' + key)
+            out['kept'].append(key)
+            continue
+        if key in ('supabase_url', 'supabase_key') and sb_blocked:
+            out['kept'].append(key)
+            continue
+        holders = [m for m in mods_ if _holder_ready(norm, m, key)]
+        if len(holders) != len(mods_):
+            for m in mods_:
+                if m not in holders:
+                    note('no-record:' + m)
+            out['kept'].append(key)
+            continue
+        equal = True
+        for m in mods_:
+            cur = _held(norm, secrets, sid, m, kind, field)
+            if cur == eff:
+                continue
+            if cur is None and copyable:                    # порожньо — копіюємо
+                out['copy_secrets' if kind == 'k' else 'copy_settings'].setdefault(m, {})[field] = eff
+                out['copied'].append(key)
+            elif key == 'preview_password':                 # Д4: корінь був ЕФЕКТИВНИМ, секрет — інертним: перезапис
+                out['copy_secrets'].setdefault(m, {})[field] = eff
+                out['copied'].append(key)
+                note('overwrote:password')
+            else:
+                note('differs:' + key)
+                equal = False
+        if equal:
+            out['remove'].append(key)
+        else:
+            out['kept'].append(key)
+    # Охоронець маркера: без `registry`/задач з `gitlab` реєстр, відновлений з нуля, створив би ЛІГУ з `integrations: false`.
+    if had_markers is None:
+        had_markers = spaces.has_markers(cfg)
+    if had_markers:
+        left = {k: v for k, v in cfg.items() if k not in out['remove']}
+        if not spaces.has_markers(left):
+            for k in _MARKER_KEYS:
+                if k in out['remove']:
+                    out['remove'].remove(k)
+                    out['kept'].append(k)
+                    note('marker-kept:' + k)
+                    break
+    return out
+
+
+def _originals_state(path, data, cfg):
+    """`(norm, secrets)` для `_decide_originals`: явні записи `space.json` ЛІГИ (`data`) і весь `secrets.json`."""
+    mods = deai_modules._raw_modules(data)
+    return deai_modules._normalize(mods), deai_modules._load_secrets()
+
+
+def _plan_originals(reg, liga, sid, path, data, mods, mig, cfg, step):
+    """`plan()` кроку Е (див. `_decide_originals`): ворота вже пройдено в `_plan`."""
+    norm, secrets = _originals_state(path, data, cfg)
+    d = _decide_originals(cfg, norm, secrets, sid)
+    if not (d['copy_settings'] or d['copy_secrets'] or d['remove'] or d['notes']):
+        raise _Stop('skip-nothing', space_id=sid)
+    new_mods = {k: (dict(v) if isinstance(v, dict) else v) for k, v in mods.items()}
+    for mid, patch in d['copy_settings'].items():
+        rec = dict(new_mods[mid])
+        st = dict(rec.get('settings') or {})
+        st.update(patch)
+        rec['settings'] = st
+        new_mods[mid] = rec
+    # Перевірка В ПАМʼЯТІ: запис із новими налаштуваннями лишається тим самим постачальником (ролі кроку Е нема — міняти нічого не вільно).
+    space = {'id': sid, 'path': path, 'legacy': True, 'integrations': liga.get('integrations') is True}
+    for role in deai_modules.ROLES_CALLED:
+        got = []
+        for m in (mods, new_mods):
+            try:
+                prov = deai_modules._provider_for(role, space, explicit_override=deai_modules._normalize(m))
+            except deai_modules.ModuleError:
+                prov = None
+            got.append((getattr(prov, 'id', None), isinstance(prov, deai_modules.Module)))
+        if got[0] != got[1]:
+            raise _Stop('abort-provider', space_id=sid)
+    space_json = dict(data)
+    space_json['modules'] = new_mods
+    marks = dict(mig) if isinstance(mig, dict) else {}
+    marks[step.mark] = {'roles': [], 'copied': sorted(d['copied']), 'removed': sorted(d['remove']), 'kept': sorted(d['kept']),
+                        'notes': list(d['notes'])}
+    space_json['migrations'] = marks
+    return _result('ready', space_id=sid, space_path=path, space_json=space_json, notes=list(d['notes']), originals=d)
 
 
 def plan(home=None, step=None):
@@ -444,6 +674,8 @@
         raise _Stop('skip-tasks-unreadable', space_id=sid) from None
     if not isinstance(cfg, dict):
         raise _Stop('skip-tasks-unreadable', space_id=sid)
+    if step.originals:                                       # 4d-4b: оригінали кореня (копія й видалення), ролей нема
+        return _plan_originals(reg, liga, sid, path, data, mods, mig, cfg, step)
 
     roles = (step.entries or _role_entries)(cfg, set(mods))      # ролі кроку (4d-3a — `_role_entries`; пошук за імʼям на виклик: точка підміни)
     # 4d-3c (Поправка 4 плану): `_entries_c` не знає простору, тож «публікацію вже веде інший модуль» проставляємо тут, одним блоком,
@@ -532,6 +764,10 @@
             lines.append('  tracks: ' + ('migrate' if p.get('tracks') else 'skip: ' + str(p.get('tracks_reason'))))
         if _step(step).ungated:
             lines.append('  records: %d; notes: %s' % (len(p.get('records') or []), ', '.join(p.get('notes') or []) or '-'))
+        if _step(step).originals:                            # 4d-4b: імена ключів кореня, без значень
+            o = p.get('originals') or {}
+            lines.append('  copy: %s; remove: %s; kept: %s; notes: %s' % tuple(
+                ', '.join(o.get(k) or []) or '-' for k in ('copied', 'remove', 'kept', 'notes')))
         for mid, sec in (p.get('secrets') or {}).items():
             lines.append('  secrets %s: %s' % (mid, ', '.join(sorted(sec)) or '-'))
     return '\n'.join(lines)
@@ -550,7 +786,7 @@
 #: `roles` — `((роль, модуль), …)` у порядку запису; `tracks` — чи мігрує напрямки (лише 4d-3a); `suffix` — хвіст імені бекапу;
 #: `stamp_re` — строге імʼя бекапу (імʼя однозначно каже, чий це крок); `entries(cfg, present)` — розрахунок ролей кроку
 #: (`None` = `_role_entries`, 4d-3a; `_entries_b` додає Task 6). `hold` кроку — це `{held: True}` у ЙОГО позначці.
-Step = namedtuple('Step', 'mark roles tracks suffix stamp_re entries ungated', defaults=(None, False))
+Step = namedtuple('Step', 'mark roles tracks suffix stamp_re entries ungated originals', defaults=(None, False, False))
 STEP_A = Step(MARK, ROLE_MODULES, True, BACKUP_SUFFIX, STAMP_RE)
 #: Другий крок (4d-3b, 0.18.0): `comments` і `vcs` ЛІГИ — явні модулі; без напрямків (`tracks=False`), свій бекап і позначка без `tracks`.
 STEP_B = Step('liga-4d3b', ROLE_MODULES_B, False, '-liga-4d3b', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3b(?:-[0-9]{1,3})?'), _entries_b)
@@ -560,7 +796,10 @@
 #: Четвертий крок (4d-4a, 0.20.0): напрямки ЛІГИ — остаточно явні (БЕЗ воріт паритету, розбіжності — нотатки позначки) і записи задач
 #: (`track = profile`). Ролей нема; `ungated=True` — крок без воріт паритету й з записом `tasks.json`.
 STEP_D = Step('liga-4d4a', (), True, '-liga-4d4a', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d4a(?:-[0-9]{1,3})?'), lambda cfg, present: {}, True)
-ALL_STEPS = (STEP_A, STEP_B, STEP_C, STEP_D)
+#: П'ятий крок (4d-4b, 0.21.0): останні оригінали кореня `tasks.json` ЛІГИ — копія в записи (`gitlab_*`, `preview_password`) і видалення
+#: з кореня за рівністю. Ролей нема; `originals=True` — гілка «оригінали» в `_plan`/`_run_locked`/`_restore_locked`.
+STEP_E = Step('liga-4d4b', (), False, '-liga-4d4b', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d4b(?:-[0-9]{1,3})?'), lambda cfg, present: {}, False, True)
+ALL_STEPS = (STEP_A, STEP_B, STEP_C, STEP_D, STEP_E)
 STEPS = ALL_STEPS
 
 
@@ -801,7 +1040,7 @@
     return name
 
 
-def _commit_space(space_path, p, stamp, step=None, records=None):
+def _commit_space(space_path, p, stamp, step=None, records=None, mark_patch=None):
     """ОДИН атомарний запис `space.json`: злиття з ПОТОЧНИМ вмістом диска (перечитуємо під замком, відразу перед записом): чужі
     ключі й правки, зроблені після `plan()`, не губляться. Модуль, що зʼявився тим часом, не перезаписуємо. Позначка вже є — `skip-done`."""
     step = _step(step)
@@ -823,7 +1062,7 @@
         if step.tracks and p['tracks'] and (tracks_core.adapter_applies(cur.get('tracks'), space_path) if step.ungated else cur.get('tracks') is None):
             new['tracks'], new['default_track'] = planned['tracks'], planned['default_track']
             wrote = True
-        marks[step.mark] = dict(planned['migrations'][step.mark], at=time.strftime('%Y-%m-%dT%H:%M:%S'), backup=stamp)
+        marks[step.mark] = dict(planned['migrations'][step.mark], at=time.strftime('%Y-%m-%dT%H:%M:%S'), backup=stamp, **(mark_patch or {}))
         if step.ungated:                                    # 4d-4a: позначка каже, що крок записав НАСПРАВДІ (власні напрямки, що зʼявились, не затираємо)
             marks[step.mark]['tracks'], marks[step.mark]['records'] = wrote, records
         new['migrations'] = marks
@@ -870,6 +1109,137 @@
                 atomic_write_json(path, cfg)
                 return len(todo)
         raise OSError('tasks file keeps changing')           # постійна гонка: не пишемо поверх чужого, наступний старт повторить
+
+
+def _secrets_writable():
+    """Чи можна писати `secrets.json` (тека дому — для тимчасового файла, сам файл — якщо є): перевірка ДО бекапу (як `_records_writable`)."""
+    p, home = deai_modules._secrets_path(), spaces.home()
+    return (not os.path.exists(home) or os.access(home, os.W_OK)) and (not os.path.exists(p) or os.access(p, os.W_OK))
+
+
+def _merge_settings(space_path, patches):
+    """Копії налаштувань у ПОТОЧНИЙ `space.json` під `WRITE_LOCK`: перечитуємо, кладемо лише відсутні/порожні ключі запису, що ще є; чужі
+    правки (і запис, що зник) не чіпаємо — розбіжність побачить перевірка `abort-verify`."""
+    if not patches:
+        return
+    sp = os.path.join(space_path, 'space.json')
+    with spaces.WRITE_LOCK:
+        cur = deai_modules._load_space_json(sp)
+        mods = dict(deai_modules._raw_modules(cur))
+        changed = False
+        for mid, patch in patches.items():
+            rec = mods.get(mid)
+            if not isinstance(rec, dict):
+                continue
+            st = rec.get('settings')
+            st = dict(st) if isinstance(st, dict) else {}
+            for k, v in patch.items():
+                if not (isinstance(st.get(k), str) and st[k]):
+                    st[k] = v
+                    changed = True
+            mods[mid] = dict(rec, settings=st)
+        if changed:
+            new = dict(cur)
+            new['modules'] = mods
+            _write_space(sp, new)
+
+
+def _verify_copies(sid, space_path, d):
+    """Після запису копій: перечитане з диска (без локу) дорівнює плану. Інакше `abort-verify` — нічого не видалено."""
+    secrets = deai_modules._load_secrets()
+    data = deai_modules._load_space_json(os.path.join(space_path, 'space.json'))
+    norm = deai_modules._normalize(deai_modules._raw_modules(data))
+    for mid, patch in d['copy_secrets'].items():
+        for k, v in patch.items():
+            if deai_modules._bucket(secrets, sid, mid).get(k) != v:
+                return False
+    for mid, patch in d['copy_settings'].items():
+        for k, v in patch.items():
+            if (norm.get(mid, {}).get('settings') or {}).get(k) != v:
+                return False
+    return True
+
+
+def _commit_originals(sid, space_path, planned_remove):
+    """Видаляє з кореня `tasks.json` ЛІГИ ключі зі списку, чия рівність з копією ПІДТВЕРДЖЕНА щойно перечитаним диском. Під `WRITE_LOCK`:
+    `_file_sig` → читання → повторне звіряння (людина могла змінити налаштування між копією й видаленням) → `.bak` → `_file_sig` →
+    `atomic_write_json`. Ключі видаляються ПО ОДНОМУ з щойно прочитаного файла: записи задач і чужі ключі — як є. Повертає
+    список видалених; постійна гонка — `OSError`."""
+    path = install_config.legacy_tasks_path()
+    sp = os.path.join(space_path, 'space.json')
+    with spaces.WRITE_LOCK:
+        for _attempt in range(_RECORDS_ATTEMPTS):
+            before = _file_sig(path)
+            cfg = install_config.load_legacy_tasks()
+            norm, secrets = _originals_state(space_path, deai_modules._load_space_json(sp), cfg)
+            fresh = _decide_originals(cfg, norm, secrets, sid)
+            todo = [k for k in planned_remove if k in fresh['remove'] and k in cfg]
+            if not todo:
+                return []
+            for k in todo:
+                del cfg[k]
+            shutil.copy2(path, path + '.bak')
+            if _file_sig(path) == before:
+                atomic_write_json(path, cfg)
+                return todo
+        raise OSError('tasks file keeps changing')
+
+
+def _run_originals(home, step, p, space_path):
+    """Запис кроку Е (спека §1.4): precheck → бекап → секрети → налаштування `space.json` → перевірка прочитанням → видалення з кореня →
+    позначка (остання). Повертає `(статус, підсумок)`; кожен збій — код, без значень."""
+    d = p['originals']
+    if (p['originals']['remove'] or d['copy_settings'] or d['copy_secrets']) and not _records_writable(install_config.legacy_tasks_path()):
+        info = _info(p, status='abort-originals', reason=_REASONS['abort-originals'])
+        _write_last(info, step)
+        return 'abort-originals', info
+    if d['copy_secrets'] and not _secrets_writable():
+        info = _info(p, status='abort-secrets', reason=_RUN_REASONS['abort-secrets'])
+        _write_last(info, step)
+        return 'abort-secrets', info
+    try:
+        stamp = _backup(spaces.home(), p['space_id'], space_path, step)
+    except (OSError, ValueError):
+        info = _info(p, status='abort-backup', reason=_RUN_REASONS['abort-backup'])
+        _write_last(info, step)
+        return 'abort-backup', info
+    sid = p['space_id']
+    try:
+        for mid, patch in d['copy_secrets'].items():
+            deai_modules.write_secrets(sid, mid, patch)
+    except deai_modules.ModuleError as e:
+        info = _info(p, status='abort-secrets', reason=_RUN_REASONS['abort-secrets'], backup=stamp, error=getattr(e, 'code', 'secrets'))
+        _write_last(info, step)
+        return 'abort-secrets', info
+    try:
+        _merge_settings(space_path, d['copy_settings'])
+        ok = _verify_copies(sid, space_path, d)
+    except (OSError, ValueError, deai_modules.ModuleError):
+        info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
+        _write_last(info, step)
+        return 'abort-write', info
+    if not ok:
+        info = _info(p, status='abort-verify', reason=_REASONS['abort-verify'], backup=stamp)
+        _write_last(info, step)
+        return 'abort-verify', info
+    try:
+        removed = _commit_originals(sid, space_path, d['remove'])
+    except (OSError, ValueError, RecursionError, KeyError, TypeError, deai_modules.ModuleError):
+        info = _info(p, status='abort-originals', reason=_REASONS['abort-originals'], backup=stamp)
+        _write_last(info, step)
+        return 'abort-originals', info
+    kept = sorted(set(p['space_json']['migrations'][step.mark]['kept']) | (set(d['remove']) - set(removed)))
+    try:
+        st = _commit_space(space_path, p, stamp, step, None, mark_patch={'removed': sorted(removed), 'kept': kept})
+    except (OSError, ValueError, deai_modules.ModuleError):
+        info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
+        _write_last(info, step)
+        return 'abort-write', info
+    info = _info(p, status=st, reason=_RUN_REASONS.get(st) or _REASONS.get(st, ''), backup=stamp)
+    info.update(copied=sorted(d['copied']), removed=sorted(removed), kept=kept)
+    if st == 'done':
+        _write_last(info, step)
+    return st, info
 
 
 def _run(home, step=None):
@@ -919,6 +1289,8 @@
             _write_last(info, step)
             return 'abort-changed', info
         space_path = p['space_path']                         # пишемо ТУДИ Ж, звідки рахували
+        if step.originals:
+            return _run_originals(home, step, p, space_path)
         if step.ungated and p.get('records') and not _records_writable(install_config.legacy_tasks_path()):
             # ⛔ постійний збій запису (лише читання): бекап не робимо — кожен старт інакше лишав би по теці бекапу
             info = _info(p, status='abort-records', reason=_REASONS['abort-records'], records=0, records_planned=len(p['records']))
@@ -1109,6 +1481,40 @@
         if mark is not None and not (isinstance(mark, dict) and mark.get('held') is True):
             return (mark.get('backup') if isinstance(mark, dict) else None) or ''
     return None
+
+
+def _restore_root(sp, d, files):
+    """4d-4b: відкат кроку Е повертає в корінь `tasks.json` ЛІГИ видалені ключі — ДОМЕРДЖЕМ, а не перезаписом файла. Перелік — з позначки
+    `removed` ПОТОЧНОГО `space.json` (читається ДО його заміни), запасний шлях — ключі `ORIGINAL_KEYS`, що є в `tasks.json` бекапу й
+    відсутні в живому. Значення — з `tasks.json` БЕКАПУ (sha256 звірено `_load_manifest`). Додається лише ключ, якого в живому корені
+    нема; своє значення людини лишається (`kept-live`). Під `WRITE_LOCK`: `_file_sig`-ретраї, `.bak`, `atomic_write_json`.
+    Повертає `(повернено, kept_live)`; збій — виняток (відкат нічого більше не пише)."""
+    if 'tasks.json' not in files:
+        return [], []
+    with open(os.path.join(d, 'tasks.json'), encoding='utf-8') as f:
+        old = json.load(f)
+    try:
+        mark = (deai_modules._load_space_json(sp).get('migrations') or {}).get(STEP_E.mark)
+    except deai_modules.ModuleError:
+        mark = None
+    listed = mark.get('removed') if isinstance(mark, dict) and isinstance(mark.get('removed'), list) else None
+    path = install_config.legacy_tasks_path()
+    with spaces.WRITE_LOCK:
+        for _attempt in range(_RECORDS_ATTEMPTS):
+            before = _file_sig(path)
+            cur = install_config.load_legacy_tasks()
+            want = [k for k in (listed if listed is not None else ORIGINAL_KEYS) if k in ORIGINAL_KEYS and k in old]
+            back = [k for k in want if k not in cur]
+            live = [k for k in want if k in cur and listed is not None]
+            if not back:
+                return [], live
+            for k in back:
+                cur[k] = old[k]
+            shutil.copy2(path, path + '.bak')
+            if _file_sig(path) == before:
+                atomic_write_json(path, cur)
+                return back, live
+        raise OSError('tasks file keeps changing')
 
 
 def _restore_locked(stamp, hold, home):
@@ -1142,6 +1548,12 @@
         safety = _write_pre_restore(stamp, sid, sp, part)
     except Exception:  # noqa: BLE001 — запобіжної копії нема: нічого не відкочуємо
         return 'abort-restore', {}
+    root_back, kept_live = [], []
+    if step.originals:                                       # ⛔ 4d-4b: СПЕРШУ корінь (збій між записами лишає простір мігрованим І з ключами)
+        try:
+            root_back, kept_live = _restore_root(sp, d, files)
+        except Exception:  # noqa: BLE001 — корінь не повернуто: нічого більше не відкочуємо
+            return 'abort-restore', {}
     # Спершу space.json: збій між двома записами лишає простір НЕмігрованим (секрети без запису нешкідливі), а не навпаки.
     with spaces.WRITE_LOCK:
         if 'space.json' in files:
@@ -1179,16 +1591,186 @@
             _write_space(sp, new)
     info = {'status': 'restored', 'reason': 'простір ЛІГА повернено з бекапу', 'space_id': sid, 'backup': stamp,
             'held': bool(hold), 'safety_copy': safety}
+    if step.originals:
+        info['root_restored'], info['kept_live'] = root_back, kept_live
     _write_last(info, step)
     return 'restored', info
 
 
+# ---------------------------------------------------------------------------------------------------------------- ролі ЛІГИ (4d-4b)
+
+#: Шість ролей ЛІГИ: `(роль, вбудований модуль, крок-власник)`. Запасного постачальника нема (4d-4b): роль працює лише через ЯВНИЙ запис.
+LIGA_ROLES = (('publish', 'vercel-publish', STEP_C), ('comments', 'supabase-comments', STEP_B), ('vcs', 'git-sync', STEP_B),
+              ('dashboard', 'supabase-dashboard', STEP_A), ('tracker', 'jira-tracker', STEP_A), ('notify', 'supabase-teams', STEP_A))
+_ENTRY_FIX = 'додайте адресу й облікові на екрані «Підключення» (змінні оточення й pipeline-feedback більше не читаються)'
+_RUN_FIX = 'python3 bin/migrate_liga.py run'
+#: Код причини → що робити. Рядки без шляхів і значень (друкуються на КОЖНОМУ старті, поки роль вимкнена).
+_ROLE_FIX = {
+    'disabled': 'увімкніть запис на екрані «Підключення»',
+    'no-jira': _ENTRY_FIX, 'no-supabase': _ENTRY_FIX, 'bad-url': _ENTRY_FIX, 'not-migrated': _ENTRY_FIX,
+    'publisher-present': 'публікацію веде інший модуль простору — так і було',
+    'module-present': 'модуль ролі вже є в просторі — так і було',
+    'skip-path-in-git': _HINTS['skip-path-in-git'],
+    'skip-tasks-unreadable': 'виправте старий tasks.json і запустіть: ' + _RUN_FIX,
+    'skip-space-json-unreadable': 'виправте space.json простору ЛІГА і запустіть: ' + _RUN_FIX,
+    'skip-registry-unreadable': 'виправте реєстр просторів (spaces.json) і запустіть: ' + _RUN_FIX,
+    'skip-no-path': 'теки простору ЛІГА не існує: відновіть її чи змініть шлях у реєстрі, далі: ' + _RUN_FIX,
+    'skip-busy': 'повторіть старт: міграцію зараз виконує інший процес',
+    'module-error': 'модуль не завантажився: перевірте його на екрані «Підключення»',
+    'module-untrusted': 'довіртесь модулю на екрані «Підключення»',
+    'bad-settings': 'виправте налаштування запису на екрані «Підключення»',
+    'secrets-unreadable': 'secrets.json не читається: виправте файл у домі Deai',
+    'space-json-unreadable': 'space.json не читається: виправте файл простору ЛІГА',
+    'no-record': 'запустіть: ' + _RUN_FIX,
+}
+
+
+def _held_mark(mig, owner):
+    """Позначка першого кроку до `owner` включно, що утримано (`{held: true}`), чи `None`: `held` раннього кроку тримає й пізніші (спека §1)."""
+    if not isinstance(mig, dict):
+        return None
+    for step in ALL_STEPS:
+        m = mig.get(step.mark)
+        if isinstance(m, dict) and m.get('held') is True:
+            return step.mark
+        if step is owner:
+            break
+    return None
+
+
+def _reason_from_reports(role, owner, mig, last):
+    """Код причини, чому в просторі нема ЗАПИСУ `role` (за порядком спеки §4.1): `skipped` кроку-власника (звіт `last.json` цього кроку) →
+    позначка кроку (`held` — утримано; застосований без ролі — `not-migrated`) → останній звіт кроку (`skip-*`/`abort-*`) → `no-record`."""
+    mark = mig.get(owner.mark) if isinstance(mig, dict) else None
+    rep = ((last or {}).get('steps') or {}).get(owner.mark) if isinstance(last, dict) else None
+    rep = rep if isinstance(rep, dict) else {}
+    skipped = rep.get('skipped') if isinstance(rep.get('skipped'), dict) else {}
+    if _held_mark(mig, owner):                                # `held` власника АБО раннього кроку (ранній тримає пізніші)
+        return 'skip-held'
+    if role in skipped and skipped[role]:
+        return skipped[role]
+    if isinstance(mark, dict):                                # крок застосований, а запису нема: роль пропущено (код не збережено)
+        return 'not-migrated' if role not in (mark.get('roles') or []) else 'no-record'
+    st = rep.get('status')
+    if isinstance(st, str) and (st.startswith('skip-') or st.startswith('abort-')) and st not in ('skip-done', 'skip-nothing', 'skip-layer-off'):
+        return st
+    return 'no-record'
+
+
+def roles_state(home=None):
+    """Стан шести ролей ЛІГИ для старту й `status`: `[{role, module, on, reason, fix}]` (порядок `LIGA_ROLES`) або `[]`, коли шару нема / простору
+    ЛІГА нема. ЧИСТА: без мережі й без коду модуля (`module_ctx` лише збирає налаштування й секрет). `on` — `_provider_for` дає ЯВНИЙ
+    `Module` цієї ролі і `module_ctx` будується. Причина — перша застосовна: `disabled` (запис вимкнено) → причина кроку (`no-jira`,
+    `no-supabase`, `bad-url`, `skip-held`, `skip-path-in-git`, `abort-*`…) → `module-error`/`module-untrusted`/`bad-settings` (запис є, не
+    працює) → `no-record`. `integrations` ЛІГИ вимкнено — усі ролі `on: False`, `reason: 'integrations-off'`, `fix: ''` (так було й у 0.20)."""
+    try:
+        if not spaces.layer_on():
+            return []
+        liga = _liga_entry(home)
+    except _Stop:
+        return []
+    if liga.get('integrations') is not True:
+        return [{'role': r, 'module': m, 'on': False, 'reason': 'integrations-off', 'fix': ''} for r, m, _s in LIGA_ROLES]
+    space = {'id': liga['id'], 'path': liga['path'], 'legacy': True, 'integrations': True}
+    try:
+        data = deai_modules._load_space_json(os.path.join(liga['path'], 'space.json'))
+        mods = deai_modules._raw_modules(data)
+        norm = deai_modules._normalize(mods)
+        mig = data.get('migrations')
+    except deai_modules.ModuleError:
+        return [{'role': r, 'module': m, 'on': False, 'reason': 'space-json-unreadable', 'fix': _ROLE_FIX['space-json-unreadable']}
+                for r, m, _s in LIGA_ROLES]
+    last = _read_last()
+    out = []
+    for role, mid, owner in LIGA_ROLES:
+        reason = None
+        try:
+            prov = deai_modules._provider_for(role, space)
+            if isinstance(prov, deai_modules.Module) and prov.id == mid:
+                deai_modules.module_ctx(space, prov)
+                out.append({'role': role, 'module': mid, 'on': True, 'reason': None, 'fix': ''})
+                continue
+        except deai_modules.ModuleError as e:
+            reason = e.code if e.code in _ROLE_FIX else 'module-error'
+        if reason is None:
+            e_ = norm.get(mid)
+            if e_ is not None and e_.get('enabled') is not True:
+                reason = 'disabled'
+            elif e_ is None:
+                reason = _reason_from_reports(role, owner, mig, last)
+            else:
+                reason = 'module-error'
+        if reason == 'skip-held':
+            fix = 'python3 bin/migrate_liga.py unhold %s, далі: %s' % (_held_mark(mig, owner) or owner.mark, _RUN_FIX)
+        elif reason.startswith('abort-'):
+            fix = 'python3 bin/migrate_liga.py status, усуньте причину, далі: ' + _RUN_FIX
+        else:
+            fix = _ROLE_FIX.get(reason, _RUN_FIX)
+        out.append({'role': role, 'module': mid, 'on': False, 'reason': reason, 'fix': fix})
+    return out
+
+
+def roles_lines(states):
+    """Рядки старту про вимкнені ролі: `ролі ЛІГИ вимкнено: <роль> (<модуль>) — <код>; виправити: <команда>` по рядку на роль. Усі роли
+    ввімкнено чи `integrations` вимкнено (так було й у 0.20) — порожньо."""
+    return ['ролі ЛІГИ вимкнено: %s (%s) — %s; виправити: %s' % (s['role'], s['module'], s['reason'], s['fix'])
+            for s in states if not s['on'] and s['reason'] != 'integrations-off']
+
+
+#: Рядок після кроку Е: де тепер лежать облікові (спека §6, ризик «єдина копія»).
+ORIGINALS_REMOVED_LINE = 'оригінали видалено з tasks.json; єдина копія — secrets.json і backups/ у домі Deai'
+
+
+def originals_summary(info):
+    """Підсумок кроку Е для старту й CLI: `скопійовано: …; видалено: …; лишилось: …; нотатки: …` (імена ключів і коди, без значень)."""
+    parts = []
+    for key, label in (('copied', 'скопійовано'), ('removed', 'видалено'), ('kept', 'лишилось')):
+        if info.get(key):
+            parts.append('%s: %s' % (label, ', '.join(info[key])))
+    if info.get('notes'):
+        parts.append('нотатки: ' + ', '.join(info['notes']))
+    return '; '.join(parts) or 'нічого не змінено'
+
+
+def unhold(mark, home=None):
+    """Знімає `{held: true}` кроку `mark` (ключ позначки, `liga-4d4a`…) у `space.json` ЛІГИ: наступний старт знову виконає крок. Лише позначку,
+    що є РІВНО `{held: true}` (позначка застосованого кроку — відмова `refuse-not-held`); невідомий ключ — `refuse-mark`. Під міжпроцесним
+    замком і `WRITE_LOCK`. Повертає статус: `unheld`, `refuse-mark`, `refuse-not-held`, `refuse-no-liga`, `skip-busy`, `skip-layer-off`, `abort-unhold`."""
+    try:
+        step = next((s for s in ALL_STEPS if s.mark == mark), None)
+        if step is None:
+            return 'refuse-mark'
+        if not spaces.layer_on():
+            return 'skip-layer-off'
+        with _exclusive() as got:
+            if got == 'busy':
+                return 'skip-busy'
+            if got != 'ok':
+                return 'abort-lock'
+            try:
+                liga = _liga_entry(home)
+            except _Stop:
+                return 'refuse-no-liga'
+            sp = os.path.join(liga['path'], 'space.json')
+            with spaces.WRITE_LOCK:
+                cur = deai_modules._load_space_json(sp)
+                marks = cur.get('migrations')
+                if not (isinstance(marks, dict) and marks.get(step.mark) == {'held': True}):
+                    return 'refuse-not-held'
+                new = dict(cur)
+                new['migrations'] = {k: v for k, v in marks.items() if k != step.mark}
+                _write_space(sp, new)
+            return 'unheld'
+    except Exception:  # noqa: BLE001 — без тексту винятку
+        return 'abort-unhold'
+
+
 # ---------------------------------------------------------------------------------------------------------------- статус
 
 def status(home=None):
     """Стан для людини (словник без значень секретів): запис ЛІГИ, позначка, останній звіт, бекапи. Ключі 4d-3a без змін (`mark` —
     позначка кроку 4d-3a), плюс `steps`: `{позначка: {'mark': позначка кроку | None, 'backups': усі бекапи}}` для кожного кроку `STEPS`."""
-    out = {'liga': False, 'space_id': None, 'mark': None, 'last': None, 'backups': [], 'error': None, 'steps': {}}
+    out = {'liga': False, 'space_id': None, 'mark': None, 'last': None, 'backups': [], 'error': None, 'steps': {}, 'roles': []}
     try:
         liga = _liga_entry(home)
     except _Stop as s:
@@ -1202,7 +1784,7 @@
             mig = data.get('migrations')
             for key in marks:
                 mark = mig.get(key) if isinstance(mig, dict) else None
-                marks[key] = ({k: mark[k] for k in ('at', 'roles', 'tracks', 'records', 'notes', 'backup', 'held') if k in mark}
+                marks[key] = ({k: mark[k] for k in ('at', 'roles', 'tracks', 'records', 'notes', 'backup', 'held', 'copied', 'removed', 'kept') if k in mark}
                               if isinstance(mark, dict) else None)
             out['mark'] = marks.get(_step(None).mark)
         except deai_modules.ModuleError:
@@ -1210,6 +1792,10 @@
     out['last'] = _read_last() or None
     out['backups'] = _list_backups()
     out['steps'] = {key: {'mark': m, 'backups': list(out['backups'])} for key, m in marks.items()}
+    try:
+        out['roles'] = roles_state(home)
+    except Exception:  # noqa: BLE001 — `status` не падає через стан ролей
+        out['roles'] = []
     return out
 
 
@@ -1234,6 +1820,8 @@
                 tr = (', напрямки: ' + ('так' if m.get('tracks') else 'ні')) if _step(key).tracks else ''     # рядок напрямків — лише кроку з напрямками
                 if _step(key).ungated:                                       # 4d-4a: записи й нотатки (лише коди, без шляхів і значень)
                     tr += ', записи: %s, нотатки: %s' % (m.get('records', 0), ', '.join(m.get('notes') or []) or '-')
+                if _step(key).originals:                                     # 4d-4b: ключі кореня (імена, без значень)
+                    tr += ', ' + originals_summary(m)
                 lines.append('  позначка: %s, ролі: %s%s, бекап: %s' % (
                     m.get('at'), ', '.join(m.get('roles') or []) or '-', tr, m.get('backup')))
         rep = ((last or {}).get('steps') or {}).get(key) if multi and isinstance(last, dict) else last   # звіт ЦЬОГО кроку
@@ -1248,6 +1836,13 @@
     if multi:
         lines.extend(_skip_lines(last))
     lines.append('  бекапи: ' + (', '.join(st['backups']) or 'нема'))
+    roles = st.get('roles') or []
+    if roles:                                                        # 4d-4b: усі шість ролей ЛІГИ — `так`/`ні (<код>)`
+        lines.append('Ролі ЛІГИ')
+        if all(r['reason'] == 'integrations-off' for r in roles):
+            lines.append('  інтеграції вимкнено — так і було')
+        else:
+            lines.extend('  %s (%s): %s' % (r['role'], r['module'], 'так' if r['on'] else 'ні (%s)' % r['reason']) for r in roles)
     return '\n'.join(lines)
 
 
@@ -1304,14 +1899,14 @@
 
 
 def startup():
-    """Виклик із `serve.serve_main` ПІСЛЯ `make_server` (порт уже зайнято), до `serve_forever`. Ізольований прогін (`implicit.isolated()`) не мігрує, крім шва
+    """Виклик із `serve.serve_main` ПІСЛЯ `make_server` (порт уже зайнято), до `serve_forever`. Ізольований прогін (`isolation.isolated()`) не мігрує, крім шва
     `DC_MIGRATE_LIGA=1` ЛИШЕ з тимчасовим `DEAI_HOME` (справжній `~/.deai` — гучна відмова). Не кидає ніколи: виняток — у stderr
     (імʼя типу, без значень) і в `last.json`. Повертає статус чи `None`. Кроки `STEPS` — по порядку (`run_all`): `abort-*` і `skip-busy`
     зупиняють наступні на цьому старті; `held` раннього кроку теж тримає наступні (їхній `plan` — `skip-held`); решта `skip-*`
     (`skip-nothing`/`skip-done`/…) наступних не блокує. Повертає статус ПЕРШОГО кроку, що не `skip-*` (найважливіше), інакше — першого кроку."""
     done, hints, hints_tracks = [], set(), []
     try:
-        if implicit.isolated():
+        if isolation.isolated():
             if os.environ.get('DC_MIGRATE_LIGA') != '1':
                 return None
             if _real_home():
@@ -1337,6 +1932,10 @@
                     print('  бекап: %s' % stamp, file=sys.stderr)
                 if mark == STEP_D.mark and st == 'done':                     # 4d-4a: що людина бачитиме (нотатки)
                     print('  ' + summary_line(info), file=sys.stderr)
+                if mark == STEP_E.mark and st == 'done':                     # 4d-4b: що скопійовано/видалено/лишилось (імена ключів) і де єдина копія
+                    print('  ' + originals_summary(info), file=sys.stderr)
+                    if info.get('removed'):
+                        print('  ' + ORIGINALS_REMOVED_LINE, file=sys.stderr)
                 skipped = info.get('skipped')
                 if isinstance(skipped, dict) and skipped:
                     print('  не мігровано: ' + ', '.join('%s (%s)' % (r, c) for r, c in sorted(skipped.items())), file=sys.stderr)
@@ -1350,6 +1949,9 @@
                 print('  відкат: bin/migrate_liga.py restore %s --hold' % stamps_done[-1], file=sys.stderr)
                 if len(stamps_done) > 1:
                     print('  раніші кроки (%s) — лише після відкату пізніших, у зворотному порядку' % ', '.join(stamps_done[:-1]), file=sys.stderr)
+        if not isolation.isolated():                                         # 4d-4b: кожна вимкнена роль — рядком, причина й команда виправлення
+            for line in roles_lines(roles_state()):
+                print(line, file=sys.stderr)
         # abort не маскуємо пізнішим успіхом: перший `abort-*`, інакше перший не-`skip-*`, інакше перший
         return (next((s for s in done if s.startswith('abort-')), None) or next((s for s in done if not s.startswith('skip-')), None)
                 or (done[0] if done else None))
````


### `bin/migrate_liga.py`

````diff
--- a/bin/migrate_liga.py
+++ b/bin/migrate_liga.py
@@ -5,6 +5,7 @@
     python3 bin/migrate_liga.py dry-run                      # що мігрувало б (нічого не пише)
     python3 bin/migrate_liga.py run                          # виконати (бекап → секрети → space.json)
     python3 bin/migrate_liga.py restore <бекап> [--hold]     # повернути space.json і секрети ЛІГИ з бекапу (поточні — у backups/<бекап>-pre-restore)
+    python3 bin/migrate_liga.py unhold <позначка>            # зняти `held` кроку (liga-4d4a…), щоб наступний запуск його виконав
 
 Вихід 0 — успіх, 1 — інакше. ⛔ Друкує лише коди, імена ролей і ключів; значень секретів і адрес — ніколи.
 """
@@ -25,6 +26,8 @@
     r = sub.add_parser('restore')
     r.add_argument('stamp')
     r.add_argument('--hold', action='store_true', help='після відкату не мігрувати на наступному старті')
+    u = sub.add_parser('unhold')
+    u.add_argument('mark', help='позначка кроку, напр. liga-4d4a')
     a = ap.parse_args(argv)
     if a.cmd == 'status':
         print(liga_migrate.status_text(liga_migrate.status()))
@@ -46,13 +49,15 @@
             if info.get('hint'):
                 print('  що робити: ' + str(info['hint']))
             if st == 'done':
-                if step.ungated:                                         # 4d-4a: ролей нема — підсумок напрямків, записів і нотаток
+                if step.originals:                                       # 4d-4b: ролей нема — що скопійовано, видалено й лишилось (імена ключів)
+                    print('  %s; бекап: %s' % (liga_migrate.originals_summary(info), info.get('backup')))
+                elif step.ungated:                                       # 4d-4a: ролей нема — підсумок напрямків, записів і нотаток
                     print('  %s; бекап: %s' % (liga_migrate.summary_line(info), info.get('backup')))
                 else:
                     tr = ('; напрямки: ' + ('так' if info.get('tracks') else 'ні')) if step.tracks else ''     # лише крок з напрямками
                     print('  ролі: %s%s; бекап: %s' % (', '.join(info.get('roles') or []) or '-', tr, info.get('backup')))
                 stamps_done.append(info.get('backup'))
-            elif step.ungated and liga_migrate.tracks_not_migrated(st):
+            elif step.ungated and not step.originals and liga_migrate.tracks_not_migrated(st):
                 print('  ' + liga_migrate.TRACKS_NOT_MIGRATED)
             if st not in liga_migrate.BENIGN:
                 code = 1
@@ -63,6 +68,12 @@
             if len(stamps_done) > 1:
                 print('  раніші кроки (%s) — лише після відкату пізніших, у зворотному порядку' % ', '.join(stamps_done[:-1]))
         return code
+    if a.cmd == 'unhold':
+        st = liga_migrate.unhold(a.mark)
+        print('%s unhold: %s' % (a.mark, st))
+        if st == 'unheld':
+            print('  наступний запуск виконає крок: python3 bin/migrate_liga.py run')
+        return 0 if st == 'unheld' else 1
     step = liga_migrate.step_of_stamp(a.stamp) or liga_migrate.ALL_STEPS[0]     # крок визначає імʼя бекапу
     st, info = liga_migrate._restore(a.stamp, hold=a.hold)
     print('%s restore: %s' % (step.mark, st))
````


### `app/deai_modules.py`

````diff
--- a/app/deai_modules.py
+++ b/app/deai_modules.py
@@ -92,7 +92,7 @@
 from collections import OrderedDict
 from urllib.parse import quote, unquote, unquote_plus
 
-import implicit
+import isolation
 import module_trust
 import spaces
 from atomic_io import atomic_write_json
@@ -111,24 +111,9 @@
                   'tracker': ('statuses',), 'notify': ('mute_state', 'mute_set')}
 #: Необовʼязкові функції ролі: беруться з server.py, якщо є й callable; свій модуль без них валідний.
 ROLE_OPTIONAL_FUNCTIONS = {'vcs': ('validate', 'mirror_dir'), 'dashboard': ('open_comments',)}
-#: Ролі, що мають зашитий шлях ЛІГА: простір з `integrations` без явного модуля дає `Implicit` (а не `None`); таблиця — в `implicit.py`.
-IMPLICIT_ROLES = implicit.IMPLICIT_ROLES
-#: Значення неявного постачальника НАЗОВНІ (`capabilities` у `/api/*`): до 4d-3: публічний контракт — рядок `'legacy'`, не `'implicit'`.
-#: Єдине місце, де цей літерал живе в ядрі; решта коду працює з `Implicit` і виходить назовні лише через `api_value()`.
+#: Значення «зашитий шлях ЛІГА» НАЗОВНІ (`capabilities`): з 4d-4b ядро його БІЛЬШЕ НЕ ПОВЕРТАЄ (запасного постачальника нема); літерал живе до 4d-4c
+#: (JS-запасні гілки `connections-model.js`/`spaces-model.js` і охоронці їх ще розбирають).
 API_IMPLICIT = 'legacy'
-#: Які з `IMPLICIT_ROLES` `capabilities()` лишає `'legacy'`, коли роль не вдалось вирішити (`ModuleError`, збій відбитків): зашитий
-#: шлях `publish` і `vcs` — локальний. Без `comments`: його зашитий шлях — СПІЛЬНИЙ Supabase ЛІГА, куди піни несуть знімки
-#: приватних макетів, тож «через помилку» на нього не переходимо (див. `_provider_for`). Без `dashboard` з тієї ж причини:
-#: його зашитий шлях — теж спільний Supabase ЛІГА (рядки команди й картки проєктів), не локальний. Без `tracker` (4c-2): його
-#: зашитий шлях — сайт Jira ЛІГИ (`jira_base` у конфігу установки, облікові людини), а не локальна дія; «через помилку» ним
-#: не ходимо — нема певності, що простір узагалі мусить там бути. Без `notify` (4c-3): його зашитий шлях — спільний Supabase ЛІГИ
-#: й ЖИВИЙ канал Teams команди (тиша на канал), а не локальна дія.
-IMPLICIT_ON_ERROR_ROLES = ('publish', 'vcs')
-#: Ролі, чий зашитий шлях ЛІГА — СПІЛЬНИЙ Supabase (піни, рядки команди й картки) або сайт Jira ЛІГИ з обліковими людини
-#: (`tracker`, 4c-2) чи спільний Supabase ЛІГИ з живим каналом Teams (`notify`, 4c-3): нечитабельний `space.json` у просторі з
-#: інтеграціями для них — `space-json-unreadable`, а не `'legacy'` (не знаємо, чи людина не ввімкнула там свій модуль; див.
-#: `_provider_for`).
-STRICT_IMPLICIT_ROLES = ('comments', 'dashboard', 'tracker', 'notify')
 #: Куди публікує модуль ролі `publish` (необовʼязкове поле маніфесту `publish_target`): `folder` — у локальну теку
 #: (`static-publish`), `url` — на віддалений хост, де результат — адреса (`vercel-publish`). Типово `folder`.
 PUBLISH_TARGETS = ('folder', 'url')
@@ -1813,22 +1798,10 @@
     (`comments`, `dashboard`, `tracker`, `notify`): їхній зашитий шлях — спільний Supabase ЛІГА (`tracker` — сайт Jira ЛІГИ), а не
     знаємо, чи людина не ввімкнула там свій модуль. `_enabled_module_is_lost` (зламаний явно ввімкнений модуль) — лише для `comments`."""
     if spaces._is_implicit(space):
-        # ⛔ Неявний простір (ЛІГА без реєстру: шар вимкнено чи простір запиту не зафіксовано) — одразу, БЕЗ `space_modules` і каталогу:
-        # його порожній `path` інакше читався б як «поточна тека процесу» (`space.json` звідти). Закон колишнього `provider()`.
-        return implicit.for_role(role) if role in IMPLICIT_ROLES else None
-    integrations = spaces.integrations_for(space)
-    strict = integrations and role in STRICT_IMPLICIT_ROLES
-    if integrations:
-        try:
-            explicit = space_modules(space) if explicit_override is None else explicit_override
-        except ModuleError:
-            if strict:
-                raise                                       # не знаємо, що людина вмикала: на спільний сервіс не йдемо
-            explicit = {}                                   # пошкоджений файл не ламає шлях ЛІГА
-        if not any(e['enabled'] for e in explicit.values()):
-            return implicit.for_role(role) if role in IMPLICIT_ROLES else None
-    else:
-        explicit = space_modules(space) if explicit_override is None else explicit_override
+        # ⛔ Неявний простір (шар вимкнено чи простір запиту не зафіксовано) — «стан не справжній»: ролей у ньому нема (4d-4b), БЕЗ
+        # `space_modules` і каталогу (його порожній `path` інакше читався б як «поточна тека процесу»).
+        return None
+    explicit = space_modules(space) if explicit_override is None else explicit_override   # `space-json-unreadable` — для КОЖНОЇ ролі
     cat = get_cat() if get_cat is not None else catalog(space)
     paper = _paper_failure(role, cat, explicit)
     if paper is not None:
@@ -1846,8 +1819,6 @@
         return winners[0][2]
     if role == 'comments' and _enabled_module_is_lost(cat, explicit):
         raise ModuleError('module-error', message=COMMENTS_MODULE_BROKEN)
-    if role in IMPLICIT_ROLES and integrations:
-        return implicit.for_role(role)
     return None
 
 
@@ -1877,16 +1848,13 @@
 
 
 def api_value(p):
-    """Єдина точка відображення постачальника НАЗОВНІ: `Module` → його id, `Implicit` → `API_IMPLICIT` (`'legacy'`, публічний
-    контракт до 4d-3), `None` → `None`. Усе інше (зокрема голий рядок) — `TypeError`: тихе «пропустити як є» знову розмило б
-    межу між внутрішнім `Implicit` і зовнішнім літералом."""
+    """Єдина точка відображення постачальника НАЗОВНІ: `Module` → його id, `None` → `None`. Усе інше (зокрема голий рядок) — `TypeError`:
+    тихе «пропустити як є» розмило б межу між внутрішнім постачальником і зовнішнім літералом (запасного `Implicit` більше нема, 4d-4b)."""
     if p is None:
         return None
     if isinstance(p, Module):
         return p.id
-    if isinstance(p, implicit.Implicit):
-        return API_IMPLICIT
-    raise TypeError(f'постачальник ролі: очікувано Module, Implicit чи None, отримано {type(p).__name__}')
+    raise TypeError(f'постачальник ролі: очікувано Module чи None, отримано {type(p).__name__}')
 
 
 def own_sig(space):
@@ -1966,15 +1934,14 @@
                     caps[role] = None       # роль «на папері» за своїм модулем, що тут не працює: не `'legacy'` і НЕ
                     continue                # `error` — клієнт читає `error` як «space.json не читається» й сховав би картки
                 error = error or e.code
-                caps[role] = API_IMPLICIT if role in IMPLICIT_ON_ERROR_ROLES and spaces.integrations_for(space) else None
+                caps[role] = None
         if error:
             caps['error'] = error
         with _STATE_LOCK:
             _CAPS[sid] = (key, dict(caps), dict(raw))
         return dict(caps), raw
     except Exception:  # noqa: BLE001 — тотальність: збій відбитків/каталогу не ламає опитування
-        legacy = API_IMPLICIT if space.get('integrations') is True else None
-        caps = {role: legacy if role in IMPLICIT_ON_ERROR_ROLES else None for role in ROLES_CALLED}
+        caps = {role: None for role in ROLES_CALLED}
         caps['error'] = 'module-error'
         return caps, {}
 
@@ -2010,14 +1977,31 @@
     рішення читається лише звідси. Лише вбудований І саме цей id: свій модуль простору міг би оголосити власне `compat` з іншим
     змістом, а `compat` інших модулів (`supabase-comments`, `git-sync`…) — про інші ролі."""
     try:
-        if isinstance(prov, implicit.Implicit):
-            return True
         return bool(isinstance(prov, Module) and getattr(prov, 'origin', 'builtin') == 'builtin' and prov.id == PUBLISH_MODULE
                     and compat_of(space or spaces.active_space(), PUBLISH_MODULE) == COMPAT_DESIGN_CANVAS)
     except Exception:  # noqa: BLE001 — тотальність: збій читання не ламає рішення про шлях публікації
         return False
 
 
+def publish_password(space):
+    """Пароль превʼю ЛІГИ з СЕКРЕТУ `password` явного `vercel-publish` (4d-4b: корінь `tasks.json` більше не читається) або `None` — тоді
+    пароль веде задача чи типовий `1100` (`serve.preview_password`). Умова — та сама `publish_legacy_path(prov, space)`, що веде гілку
+    ЛІГИ публікації: вбудований `vercel-publish` із `compat == "design-canvas"`; модуль-режим (`compat` порожній) цього секрета читає
+    САМ (`publish_with_module`), тож тут `None`. ТОТАЛЬНА: не кидає. ⛔ Закон ізоляції (Д6): ізольований прогін у СПРАВЖНЬОМУ домі
+    (`isolation.real_home`) — `None` (спільний секрет не беремо); у тимчасовому домі тесту — секрет фікстури."""
+    try:
+        if not isinstance(space, dict) or not space or spaces._is_implicit(space) or not spaces.layer_on():
+            return None
+        if isolation.isolated() and isolation.real_home(spaces.home()):
+            return None
+        prov = _capabilities_full(space)[1].get('publish')
+        if not publish_legacy_path(prov, space):
+            return None
+        return read_secrets(_space_id(space), PUBLISH_MODULE).get('password') or None
+    except Exception:  # noqa: BLE001 — тотальність: збій читання секрета не ламає `/api/task`
+        return None
+
+
 # ------------------------------------------------------------------------------ роль `comments` (2b-2)
 
 #: Текст відмови, коли `client_config` показує значення НЕпублічного секрету: фіксований, без жодних значень.
@@ -2174,8 +2158,6 @@
     """ЄДИНА умова «коментарі ведуться за схемою comment-layer»: `Implicit` АБО вбудований `Module` `supabase-comments` із
     `compat == "comment-layer"`. ⛔ Лише вбудований І саме цей id (Поправка 3): свій модуль простору міг оголосити власне `compat`
     з іншим змістом, а `supabase-dashboard`/`supabase-teams` мають СВОЄ `compat` (`comment-layer` — публічний ключ сторінки)."""
-    if isinstance(prov, implicit.Implicit):
-        return True
     return (isinstance(prov, Module) and getattr(prov, 'origin', 'builtin') == 'builtin' and prov.id == COMMENTS_MODULE
             and compat_of(space, prov.id) == COMPAT_COMMENT_LAYER)
 
````


### `app/serve.py`

````diff
--- a/app/serve.py
+++ b/app/serve.py
@@ -32,7 +32,7 @@
 
 import pages_model as pm  # чиста модель сторінок ітерації (Task 1)
 import spaces  # простори машини: який файл задач діє для запиту (етап 1 Deai 1.0)
-import implicit  # неявний постачальник ролі (4d-2): `Implicit`, закон ізоляції `route`
+import isolation  # закон ізоляції й шви тестів (4d-4b; раніше `implicit.py`)
 import deai_modules  # вбудовані модулі (етап 2а): хто виконує роль `publish` у просторі запиту
 import dashboard  # командний дашборд (4c-1): збирання карток і читання рядків команди через постачальника ролі
 import tracker  # статуси задач у трекері (4c-2): ядро ролі `tracker` (ключі, пакети, нормалізація, адаптер ЛІГИ)
@@ -101,12 +101,6 @@
 # визначеної з Referer — і тоді власні перевірки обробника не діють. Саме розбіжність
 # між цим переліком і ланцюгом if у do_GET дала перехоплення /shot.
 HANDLED_PREFIXES = ('/app', '/api/', '/commented', '/comments', '/it-assets', '/shot', '/published/')
-
-
-def supabase_config():
-    """Тонка обгортка (`install_config.supabase_config`): ім'я в `serve` лишається точкою підміни для тестів
-    (`mock.patch.object(serve, 'supabase_config', …)`), а всі виклики в самому `serve` ідуть через нього."""
-    return install_config.supabase_config()
 
 
 # Служебное, что НЕ копируется в итерации/публикацию из папки задачи
@@ -536,19 +530,18 @@
 # в `iterations.json` — внутрішня назва стану синку (сумісність тек задач, які читає `task_state.py`).
 
 
-def gitlab_cfg(cfg, task):
-    """Git-sync конфиг задачи или None. cfg = весь tasks.json (для дефолтного ssh)."""
+def gitlab_cfg(task):
+    """Git-sync конфиг задачи или None. Лише поля самої задачі: спільні ключ і IP — налаштування запису `git-sync` (4d-4b: корінь `tasks.json` не читаємо)."""
     gl = task.get('gitlab')
     if not gl or not gl.get('repo') or not gl.get('path'):
         return None
-    key = gl.get('ssh_key') or cfg.get('gitlab_ssh_key')
+    key = gl.get('ssh_key')
     return {'repo': gl['repo'], 'path': gl['path'].strip('/'),
             'ssh_key': os.path.expanduser(key) if key else None,
             'branch': gl.get('branch', 'main'),
-            # Адреса хоста для повтору при збої резолвера (модуль `git-sync`). Береться
-            # з конфіга задачі або зі спільного кореня tasks.json; немає — повтору
-            # не буде, і це правильніше за вигадану адресу.
-            'host_ip': gl.get('host_ip') or cfg.get('gitlab_host_ip')}
+            # Адреса хоста для повтору при збої резолвера (модуль `git-sync`): з конфіга задачі; немає — з налаштувань модуля (їх бере сам
+            # модуль), а ні — повтору не буде, і це правильніше за вигадану адресу.
+            'host_ip': gl.get('host_ip')}
 
 
 def gitlab_web(gl):
@@ -619,8 +612,6 @@
     ті самі. ⛔ Лише вбудований І саме `git-sync` (Поправка 3): свій модуль міг оголосити власне `compat` з іншим змістом.
     Споживачі НЕ перевіряють тип постачальника самі — читають третій елемент `vcs_provider()` (`TextPredicateGuard`).
     ТОТАЛЬНА: нечитабельний `space.json` — `False`, не виняток (`compat_of`)."""
-    if isinstance(prov, implicit.Implicit):
-        return True
     return (isinstance(prov, deai_modules.Module) and getattr(prov, 'origin', 'builtin') == 'builtin'
             and prov.id == deai_modules.VCS_MODULE
             and deai_modules.compat_of(space, prov.id) == deai_modules.COMPAT_DESIGN_CANVAS)
@@ -642,20 +633,12 @@
         raise VcsError(getattr(e, 'code', 'vcs-error'), _frame_reason(e)) from None
     if prov is None:
         return None
-    if isinstance(prov, implicit.Implicit):
-        try:
-            m = deai_modules.catalog().get(VCS_MODULE)                 # лише вбудовані: без простору
-        except Exception as e:  # noqa: BLE001 — шлях ЛІГИ тепер залежить від каталогу: збій = vcs-error, не 500
-            raise VcsError('vcs-error', f'module catalog: {type(e).__name__}') from None
-        if m is None or m.status != 'ok':
-            raise VcsError('vcs-error', f'{VCS_MODULE} module is not loaded')
-        return m, _vcs_legacy_ctx(), vcs_legacy_texts(prov, None)
     try:
         space = spaces.active_space()
         legacy = vcs_legacy_texts(prov, space)                       # ОДИН раз: третій елемент для всіх споживачів текстів
-        if _builtin_shared(space, prov) and implicit.isolated():
+        if _builtin_shared(space, prov) and isolation.isolated():
             # ⛔ Закон ізоляції (4d-3b, спека §5): запис `shared_state` в ізольованому прогоні (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`)
-            # будує `ctx` НЕЯВНОГО шляху — налаштування запису не читаються, дзеркала плоскі в `DC_MIRRORS_DIR`. Місце ізоляції
+            # будує `ctx` ізольованого шляху — налаштування запису не читаються, дзеркала плоскі в `DC_MIRRORS_DIR`. Місце ізоляції
             # одне: ця функція і `comments_route`. Тексти — за `compat` (предикат вище), не за ізоляцією.
             return prov, _vcs_legacy_ctx(), legacy
         ctx = deai_modules.module_ctx(space, prov)
@@ -670,25 +653,23 @@
     return isinstance(v, str) and v.strip() != ''
 
 
-def _vcs_ssh(cfg, settings, *own):
+def _vcs_ssh(*own):
     """`{ssh_key, host_ip}` цілі — лише у просторі з інтеграціями (ЛІГА). Правило ОДНЕ для кожного шляху цілі й окремо для
     кожного з двох полів: перше непорожнє серед `own` (словники самої задачі: `vcs{}`, далі `gitlab{}`) > налаштування модуля
-    (поле тоді НЕ кладемо в ціль — модуль бере своє) > спільний `gitlab_ssh_key`/`gitlab_host_ip` з кореня `tasks.json`."""
+    (поле тоді НЕ кладемо в ціль — модуль бере своє). Кореня `tasks.json` більше нема (4d-4b): його ключ і IP — налаштування запису `git-sync`."""
     if not spaces.integrations_on():
         return {}
     out = {}
-    for name, shared in (('ssh_key', 'gitlab_ssh_key'), ('host_ip', 'gitlab_host_ip')):
+    for name in ('ssh_key', 'host_ip'):
         val = next((d[name] for d in own if isinstance(d, dict) and d.get(name)), None)
         if val is None:
-            if (settings or {}).get(name):
-                continue
-            val = cfg.get(shared)
+            continue                                         # поля нема в задачі: модуль візьме своє з налаштувань
         if isinstance(val, str) and val:
             out[name] = os.path.expanduser(val) if name == 'ssh_key' else val
     return out
 
 
-def vcs_target(cfg, tid, task, settings):
+def vcs_target(tid, task, settings):
     """Ціль задачі для модуля або `None` (задачу не налаштовано). Порядок (спека 4a, «Роль `vcs`»): поле задачі
     `vcs{repo, path?, branch?}` (лише з непорожнім `repo`) → старе `gitlab{…}` (лише простір з інтеграціями; як
     `gitlab_cfg` 0.7.0: без `repo` чи `path` — не налаштована) → налаштування модуля. `{task}` у `path` — id задачі;
@@ -706,26 +687,25 @@
         return {'repo': v['repo'].strip(), 'task': tid,
                 'path': tpath(v['path'] if _vcs_str(v.get('path')) else settings.get('path') or 'mockup/{task}'),
                 'branch': (v['branch'] if _vcs_str(v.get('branch')) else settings.get('branch') or 'main').strip(),
-                **_vcs_ssh(cfg, settings, v, task.get('gitlab'))}
+                **_vcs_ssh(v, task.get('gitlab'))}
     if task.get('gitlab') and spaces.integrations_on():
-        gl = gitlab_cfg(cfg, task)
+        gl = gitlab_cfg(task)
         if gl is None:
             return None
         # Ключі `gl` перезаписуємо НА МІСЦІ (порядок ключів цілі — як у 0.7.0): `gitlab_cfg` бере корінь, не знаючи про налаштування.
-        gl = {**gl, 'ssh_key': None, 'host_ip': None, **_vcs_ssh(cfg, settings, task['gitlab'])}
+        gl = {**gl, 'ssh_key': None, 'host_ip': None, **_vcs_ssh(task['gitlab'])}
         return {**{k: x for k, x in gl.items() if x}, 'task': tid, 'repo': str(gl['repo']).strip()}
     if _vcs_str(settings.get('repo')):
         return {'repo': settings['repo'].strip(), 'task': tid,
                 'path': tpath(settings.get('path') or 'mockup/{task}'),
-                'branch': (settings.get('branch') or 'main').strip(),
-                **_vcs_ssh(cfg, settings)}
+                'branch': (settings.get('branch') or 'main').strip()}
     return None
 
 
-def vcs_task(cfg, tid, task):
+def vcs_task(tid, task):
     """`None` — у просторі запиту нема ролі `vcs`; інакше `(module, ctx, legacy, target | None)`. Відмова — `VcsError`."""
     p = vcs_provider()
-    return None if p is None else (*p, vcs_target(cfg, tid, task, p[1].get('settings') or {}))
+    return None if p is None else (*p, vcs_target(tid, task, p[1].get('settings') or {}))
 
 
 #: Форма результату функцій ролі, які кличе ядро. Свій модуль (довіра 3c) може повернути що завгодно: `None` чи рядок
@@ -1921,9 +1901,9 @@
     для решти, а не вузький перелік: контракт «ніколи не кидає» тримає екран живим для «Моїх» навіть тоді, коли відповідь бази —
     не те, що очікували."""
     try:
-        if isinstance(prov, implicit.Implicit) or _shared_module(space, prov):
-            # ⛔ `shared_state`-модуль іде тим самим законом (4d-3a): шов → ізоляція → живий, роль — з `implicit.for_role`
-            kind, fake = implicit.route(prov if isinstance(prov, implicit.Implicit) else implicit.for_role('dashboard'))
+        if _shared_module(space, prov):
+            # ⛔ `shared_state`-модуль іде законом ізоляції (4d-3a): шов → ізоляція → живий (`isolation.route`)
+            kind, fake = isolation.route('dashboard')
             if kind == 'fake':
                 with open(fake, encoding='utf-8') as fh:
                     data = json.load(fh)
@@ -1932,11 +1912,7 @@
                 return [r for r in data if isinstance(r, dict)], None
             if kind == 'isolated':
                 return [], TEAM_ISOLATED
-            if not isinstance(prov, implicit.Implicit):
-                return dashboard.rows(prov, deai_modules.module_ctx(space, prov)), None
-            # Конфігу установки нема: дашборд команди недосяжний, «Мої» живуть без нього (і без мережі) — `dashboard-unconfigured`.
-            ctx = dashboard.legacy_ctx(*supabase_config(), space_id=spaces.request_space_id() or '')
-            return dashboard.rows(dashboard.legacy_module(), ctx), None
+            return dashboard.rows(prov, deai_modules.module_ctx(space, prov)), None
         return dashboard.rows(prov, deai_modules.module_ctx(space, prov)), None
     except deai_modules.ModuleError as e:
         return [], (e.message or e.code)[:200]
@@ -2039,12 +2015,6 @@
 _TRACKER_LOCK = threading.Lock()
 
 
-def jira_config():
-    """Тонка обгортка (`install_config.jira_config`): ім'я в `serve` лишається точкою підміни для тестів
-    (`mock.patch.object(serve, 'jira_config', …)`), а виклик у самому `serve` іде через нього (як `supabase_config`)."""
-    return install_config.jira_config()
-
-
 def tracker_resolve():
     """`(space, prov)` ролі `tracker` для простору ЗАПИТУ: `prov` — `Module`, неявний постачальник (`Implicit`, ЛІГА) чи `None` (трекера нема). Як
     `team_resolve`: `space` — запис простору лише для модуля. Кидає `spaces.SpacesError` і `deai_modules.ModuleError` (свій модуль
@@ -2070,8 +2040,8 @@
     решта — лише назва класу (`str(e)` чужого винятку не чищений і міг би винести секрет на екран)."""
     keys = list(keys)[:tracker.BATCH]
     try:
-        if isinstance(prov, implicit.Implicit) or _shared_module(space, prov):
-            kind, fake = implicit.route(prov if isinstance(prov, implicit.Implicit) else implicit.for_role('tracker'))
+        if _shared_module(space, prov):
+            kind, fake = isolation.route('tracker')
             if kind == 'fake':
                 with open(fake, encoding='utf-8') as fh:
                     data = json.load(fh)
@@ -2080,11 +2050,7 @@
                 return None
             if not keys:       # ⛔ ПІСЛЯ шва й ізоляції (як у 0.15.0): ізольований прогін без ключів — `None`, а не `({}, None)`
                 return {}, None
-            if isinstance(prov, implicit.Implicit):
-                module = tracker.legacy_module()
-                ctx = tracker.legacy_ctx(*jira_config(), space_id=spaces.request_space_id() or '')
-            else:
-                module, ctx = prov, deai_modules.module_ctx(space, prov)     # `shared_state` (4d-3a): модуль, не легасі-збирач
+            module, ctx = prov, deai_modules.module_ctx(space, prov)         # `shared_state` (4d-3a): модуль із ctx запису
         else:
             if not keys:
                 return {}, None
@@ -2496,7 +2462,7 @@
             if v is not None:
                 legacy = v[2]
                 # Явний `vcs.repo` перемагає `gitlab` репо напрямку (ЛІГА) — як у `vcs_target`.
-                target = vcs_target(cfg, tid, {'vcs': vcs} if vcs else {'gitlab': gitlab}, v[1].get('settings') or {})
+                target = vcs_target(tid, {'vcs': vcs} if vcs else {'gitlab': gitlab}, v[1].get('settings') or {})
                 if target:
                     got = os.path.join(tmp, 'm')
                     os.makedirs(got)
@@ -2655,8 +2621,8 @@
     if prov is None:
         # Нікого: простір без інтеграцій і без модуля (раніше — `IntegrationsOff`). Маршрут відповідає 409 ще до цього виклику.
         raise OSError('сповіщень Teams у просторі нема')
-    if isinstance(prov, implicit.Implicit) or _shared_module(space, prov):
-        kind, fake = implicit.route(prov if isinstance(prov, implicit.Implicit) else implicit.for_role('notify'))
+    if _shared_module(space, prov):
+        kind, fake = isolation.route('notify')
         if kind == 'fake':
             try:
                 with open(fake, encoding='utf-8') as fh:
@@ -2675,11 +2641,7 @@
         # Після шва (він пише лише у свій локальний файл), але ДО будь-якої мережі.
         if kind == 'isolated':
             raise OSError('ізольований конфіг: спільний стан Teams не чіпаємо')
-        if isinstance(prov, implicit.Implicit):
-            module = notify.legacy_module()
-            ctx = notify.legacy_ctx(*supabase_config(), space_id=spaces.request_space_id() or '')
-        else:
-            module, ctx = prov, deai_modules.module_ctx(space, prov)         # `shared_state` (4d-3a): модуль, не легасі-збирач
+        module, ctx = prov, deai_modules.module_ctx(space, prov)             # `shared_state` (4d-3a): модуль із ctx запису
     else:
         module, ctx = prov, deai_modules.module_ctx(space, prov)
     res = deai_modules.call(module, fn, ctx, *args, timeout=notify.NOTIFY_TIMEOUT)
@@ -2794,7 +2756,7 @@
     через `deai_modules.comment_channel_of`. Збій рішення (нема постачальника, `ModuleError`, `channel_for` на непридатному id) —
     схема comment-layer, як у 0.17.0: ні 5xx, ні `None`, помилку бачить сама роль коментарів."""
     prov = deai_modules.comments_prov_cached(sp)
-    if isinstance(prov, (implicit.Implicit, deai_modules.Module)):
+    if isinstance(prov, deai_modules.Module):
         try:
             return deai_modules.comment_channel_of(sp, prov, task, tid, internal=internal)
         except deai_modules.ModuleError:
@@ -3110,49 +3072,24 @@
 #: Кошик Storage ЛІГИ для скріншотів пінів: картка Teams бере `meta.shotUrl` звідти (як старий адаптер 0.9.0). Джерело правди —
 #: `install_config.LEGACY_SHOTS_BUCKET` (його ділить міграція ЛІГИ, 4d-3b); тут — аліас.
 LEGACY_SHOTS_BUCKET = install_config.LEGACY_SHOTS_BUCKET
-COMMENTS_UNCONFIGURED = 'Supabase простору ЛІГА не налаштовано (supabase_url і supabase_key у tasks.json)'
-
+COMMENTS_UNCONFIGURED = 'Supabase простору ЛІГА не налаштовано: додайте адресу й ключ на екрані «Підключення»'
 
-def _comments_legacy_ctx():
-    """`ctx` неявного постачальника коментарів простору ЛІГА: `supabase-comments` з адресою й ключем конфігу установки
-    (`supabase_config`) і кошиком скріншотів ЛІГИ. Нема конфігу — `ModuleError('comments-unconfigured')`.
 
-    ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`, а при вимкненому шарі `spaces.home()` — це
-    справжній `~/.deai` машини (той самий урок, що `_vcs_legacy_ctx`)."""
-    url, key = supabase_config()
-    if url is None:
-        raise deai_modules.ModuleError('comments-unconfigured', message=COMMENTS_UNCONFIGURED)
-    return {'space': {'id': spaces.request_space_id() or '', 'path': ''},
-            'settings': {'url': url, 'shots_bucket': LEGACY_SHOTS_BUCKET},
-            'secrets': {'key': key}, 'ModuleError': deai_modules.ModuleError}
-
-
 def comments_route(space, prov):
-    """Як вести командні коментарі для ВЖЕ вирішеного постачальника `prov` (`Module` чи `Implicit` з `comments_provider`):
-    `(module, ctx, channel)`, де `channel(task, tid, internal=False)` — канал задачі.
+    """Як вести командні коментарі для ВЖЕ вирішеного постачальника `prov` (`Module` з `comments_provider`):
+    `(module, ctx, channel)`, де `channel(task, tid, internal=False)` — канал задачі (`deai_modules.comment_channel_of`: схема comment-layer для
+    мігрованої ЛІГИ — `comment_project` чи `dc/<задача>`, інакше `deai/<простір>/<задача>`) і `ctx` — `module_ctx` запису.
+    Кидає `ModuleError` (`comments-unconfigured`, `module-error`, коди `module_ctx`). Не кличе код модуля.
 
-    `Implicit` (ЛІГА) — вбудований `COMMENTS_MODULE`, `_comments_legacy_ctx()` і канал `comment_channel` (`comment_project`
-    чи `dc/<задача>`: на ньому історія, тиша Teams і лічильники дашборда); модуль — `module_ctx` і `channel_for`.
-    Кидає `ModuleError` (`comments-unconfigured`, `module-error`, коди `module_ctx`). Не кличе код модуля."""
-    if isinstance(prov, implicit.Implicit):
-        try:
-            m = deai_modules.catalog().get(COMMENTS_MODULE)            # лише вбудовані: без простору
-        except Exception as e:  # noqa: BLE001 — збій каталогу = відмова модуля, не 500
-            raise deai_modules.ModuleError('module-error', message=f'module catalog: {type(e).__name__}') from None
-        if m is None or m.status != 'ok':
-            raise deai_modules.ModuleError('module-error', message=f'{COMMENTS_MODULE} module is not loaded')
-        return m, _comments_legacy_ctx(), (lambda task, tid, internal=False:
-                                           deai_modules.comment_channel_of(space, prov, task, tid, internal=internal))
+    ⛔ Закон ізоляції (Д6, 4d-4b): ізольований прогін (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) із вбудованим `shared_state`-записом у СПРАВЖНЬОМУ
+    домі машини (`isolation.real_home`) — спільного ключа не беремо: `comments-unconfigured`. У тимчасовому домі тесту `module_ctx` бере
+    налаштування й секрет ФІКСТУРИ (вигадану пару), а жива мережа відрізана підміною шва `_open` модуля."""
     if not isinstance(prov, deai_modules.Module):
         raise deai_modules.ModuleError('module-error', message='comments: no provider')
-    # Канал — функція `comment_channel_of`: вбудований `supabase-comments` із `compat: "comment-layer"` (мігрована ЛІГА) веде
-    # коментарі схемою comment-layer, решта модулів — `deai/<простір>/<задача>` (`channel_for`).
     channel = (lambda task, tid, internal=False:
                deai_modules.comment_channel_of(space, prov, task, tid, internal=internal))
-    if _builtin_shared(space, prov) and implicit.isolated():
-        # ⛔ Закон ізоляції (4d-3b, спека §5): запис `shared_state` в ізольованому прогоні бере ключ із кореня файла задач, а не з
-        # `secrets.json` (`_comments_legacy_ctx`; нема конфігу — `comments-unconfigured`, як в `Implicit`). Місце ізоляції одне.
-        return prov, _comments_legacy_ctx(), channel
+    if _builtin_shared(space, prov) and isolation.isolated() and isolation.real_home(spaces.home()):
+        raise deai_modules.ModuleError('comments-unconfigured', message=COMMENTS_UNCONFIGURED)
     return prov, deai_modules.module_ctx(space, prov), channel
 
 
@@ -3427,8 +3364,6 @@
     def kind(self):
         if isinstance(self.prov, deai_modules.Module):
             return 'module'
-        if isinstance(self.prov, implicit.Implicit):
-            return 'implicit'       # внутрішній рядок `kind` (читають `bin/state.py` і тести), НЕ значення постачальника
         return 'broken' if self.err is not None else 'off'
 
     @property
@@ -3443,12 +3378,12 @@
         """Хто джерело — для людини (заголовок `inbox`). «Supabase» — лише коли він справді джерело (і для мігрованої ЛІГИ)."""
         if self.kind == 'module' and self.legacy_scheme:
             return 'Supabase'
-        return {'module': lambda: f'модуль {self.prov.id}', 'implicit': lambda: 'Supabase',
+        return {'module': lambda: f'модуль {self.prov.id}',
                 'broken': lambda: 'модуль недоступний', 'off': lambda: 'не підключено'}[self.kind]()
 
     def channel(self, task, tid, internal=False):
         """Канал задачі: модуль чи ЛІГА — `deai_modules.comment_channel_of` (схема за `compat`); нікого/збій — схема comment-layer."""
-        if self.kind in ('module', 'implicit'):
+        if self.kind == 'module':
             return deai_modules.comment_channel_of(self.space, self.prov, task, tid, internal=internal)
         return deai_modules.legacy_comment_channel(task, tid, internal)
 
@@ -3462,8 +3397,6 @@
     def takes_iteration(self):
         """Чи передаємо номер ітерації в `resolve`: лише вбудованому `supabase-comments` (свій модуль простору міг оголосити
         `resolve(ctx, channel, id, reason)` — зайвий аргумент його зламав би). У ЛІГИ — завжди."""
-        if self.kind == 'implicit':
-            return True
         return (self.kind == 'module' and self.prov.id == COMMENTS_MODULE
                 and getattr(self.prov, 'origin', 'builtin') == 'builtin')
 
@@ -3474,8 +3407,6 @@
         ⛔ ЛІГА: `spaces.require_integrations()` ПЕРЕД кожним викликом — простір без інтеграцій не має права йти в мережу
         (колись це робив старий шлях ЛІГА; модуль про простори не знає). `IntegrationsOff` — `OSError`, а не `ModuleError`:
         наявні `except OSError` деградують чесно."""
-        if self.kind == 'implicit':
-            spaces.require_integrations()
         try:
             mod, ctx, channel = comments_route(self.space, self.prov)
             return deai_modules.call(mod, fn, ctx, channel(task, tid, internal), *args,
@@ -4128,8 +4059,10 @@
 DEFAULT_PREVIEW_PW = '1100'
 
 
-def preview_password(cfg, task):
-    """Пароль превʼю задачі. `preview_password` у tasks.json, інакше спільний 1100.
+def preview_password(task, space=None):
+    """Пароль превʼю задачі: `preview_password` ЗАДАЧІ, далі секрет `password` запису `vercel-publish` ЛІГИ (`space`;
+    `deai_modules.publish_password`), інакше спільний 1100. Кореня `tasks.json` більше не читаємо (4d-4b: крок `liga-4d4b` переніс його
+    значення в секрет).
 
     До 03.08.2026 пароль був захардкожений один на ВСІ задачі й усіх людей: одна
     злита ссилка відкривала будь-яке превʼю. Тепер його можна задати на задачу й
@@ -4141,7 +4074,7 @@
     рівні Vercel (Deployment Protection), і вона ламає цей гейт.
     """
     return str((task or {}).get('preview_password')
-               or (cfg or {}).get('preview_password') or DEFAULT_PREVIEW_PW)
+               or deai_modules.publish_password(space) or DEFAULT_PREVIEW_PW)
 
 
 PREVIEW_PW_MAX = 64
@@ -4327,11 +4260,10 @@
     prov, err = comments_provider(space)
     if err is not None:
         return False, err.code
-    is_implicit = isinstance(prov, implicit.Implicit)
-    if prov is None or ((is_implicit or _shared_module(space, prov)) and module_publish):
+    if prov is None or (_shared_module(space, prov) and module_publish):
         return False, None
-    if not is_implicit and not isinstance(prov, deai_modules.Module):
-        return False, None                 # значення, що не є ні постачальником, ні неявним, — «нікого», як і було
+    if not isinstance(prov, deai_modules.Module):
+        return False, None                 # значення, що не є постачальником, — «нікого», як і було
     try:
         mod, ctx, route_channel = comments_route(space, prov)
         channel = route_channel(task, tid)                 # ⛔ канал — ДО коду модуля: непридатний id задачі не доходить до `client_config`
@@ -5391,7 +5323,7 @@
     `isolated`; `last_check` НЕ перезаписуємо (`deai_modules.check` не кличемо): це не результат перевірки модуля, і стара
     правдива відповідь не мусить затертись «відмовою», якої модуль не давав. Усі п'ять ролей (comments/vcs/dashboard/tracker/
     notify): сюди ходять і `POST /api/module-check`, і хвіст `module_write`. Будь-якого походження — відмова безпечна."""
-    if implicit.isolated() and deai_modules.shared_state(space, mid):
+    if isolation.isolated() and deai_modules.shared_state(space, mid):
         return {'ok': False, 'error': 'isolated',
                 'detail': 'Перевірка спільного стану в ізольованому прогоні не виконується.'}
     try:
@@ -5992,8 +5924,8 @@
         if self.path == '/api/task':
             tid, task = self._current_task()
             meta = load_meta(task)
-            pw = preview_password(load_tasks(), task)
             sp = spaces.active_space()
+            pw = preview_password(task, sp)
             out = {'id': tid, 'title': task.get('title', tid),
                    'jira': task.get('jira'),
                    'tags': task_tags(task, sp),
@@ -7212,7 +7144,7 @@
         else:
             task.pop('preview_password', None)
         save_tasks(cfg)
-        now = preview_password(cfg, task)
+        now = preview_password(task, spaces.active_space())
         self._send_json({'ok': True, 'preview_password': now,
                          'preview_password_custom': bool(task.get('preview_password')),
                          'preview_gate': preview_gate_state(task, now)})
@@ -7552,7 +7484,7 @@
         cfg = load_tasks()
         tid, task = self._current_task()
         try:
-            return tid, task, vcs_task(cfg, tid, task), None
+            return tid, task, vcs_task(tid, task), None
         except VcsError as e:
             return tid, task, None, e
 
@@ -7685,25 +7617,16 @@
             return
         if prov is None:
             return
-        legacy = isinstance(prov, implicit.Implicit)     # постачальник неявний: гейти ізоляції/конфігу нижче — саме про нього
         try:
             space = spaces.active_space()
-            shared = (not legacy) and _shared_module(space, prov)
+            shared = _shared_module(space, prov)
             # ⛔ «Простір ЛІГА» (лог `OVERVIEW_LOG`, крок реєстру GitLab) — НЕ «постачальник неявний»: після міграції 4d-3a дашборд
             # ЛІГИ — `Module` із `shared_state`, а запис реєстру лишається з `legacy: True`.
-            liga = legacy or bool(space and space.get('legacy') is True)
+            liga = bool(space and space.get('legacy') is True)
         except Exception:  # noqa: BLE001 — простір не вирішився: як і вище, пушити нікуди
             return
-        if shared and implicit.isolated():
+        if shared and isolation.isolated():
             return                      # ⛔ `shared_state`-модуль (4d-3a): ізольований прогін не пише в спільний стан і за ним
-        if legacy:
-            # ⛔ Закон ізоляції, а не `route`: шов `DC_TEAM_FAKE` синку не стосується (він лише читає), а ізольований прогін
-            # не пише в спільний Supabase і за ним (`DC_NO_OVERVIEW` уже відсічено вище, тож тут це лише `DC_TASKS_FILE`).
-            if implicit.isolated():
-                return
-            sb_url, _ = supabase_config()
-            if sb_url is None:
-                return                  # конфігу установки нема — пушити нікуди (і лога не відкриваємо)
         key, target = _overview_target()
         _overview_launch(key, liga, target)
 
@@ -7967,7 +7890,7 @@
             # запису, — а ціль із ним (`{task}` у `path`) відмовила б раніше й іншим кодом: тут його не чіпаємо.
             if prov[0].fn('validate') is not None and isinstance(tid, str) and NAME_RE.fullmatch(tid):
                 try:
-                    _vcs_call(prov, 'validate', vcs_target({}, tid, {'vcs': vcs}, prov[1].get('settings') or {}),
+                    _vcs_call(prov, 'validate', vcs_target(tid, {'vcs': vcs}, prov[1].get('settings') or {}),
                               timeout=deai_modules.CHECK_TIMEOUT)
                 except VcsError as e:
                     self._space_error(deai_modules.STATUS.get(e.code, 400), e.code, str(e)[:300])
@@ -8229,13 +8152,13 @@
         # Пароль ЛІГА — завжди є (типовий 1100, якщо не задано): гейт тут обовʼязковий, і лише
         # модуль без пароля передає `gate_pw=None` (див. `build_preview`). Читаємо його ДО збірки (раніше
         # — після `rmtree`): збій читання tasks.json більше не лишає напівзібраний `publish/`.
-        pw = preview_password(load_tasks(), task)
+        space = spaces.active_space() if spaces.layer_on() and spaces.request_space_id() is not None else None
+        pw = preview_password(task, space)
         # Коментарі превʼю — з постачальника ролі `comments` простору публікації (а не з `integrations_on()`), раз, ДО
         # збірки: `Implicit` → вбудований `supabase-comments` з конфігом установки й каналом ЛІГИ, модуль → його канал,
         # відмова (в т.ч. `comments-unconfigured`) → без коментарів узагалі + `comments_unavailable` у відповіді (див.
         # `publish_comments`). Простір береться лише
         # коли він зафіксований за запитом: інструменти ЛІГА й заглушки обробника його не мають, і реєстру тоді не читаємо.
-        space = spaces.active_space() if spaces.layer_on() and spaces.request_space_id() is not None else None
         comments, comments_warn = publish_comments(space, task, tid)
         built = build_preview(task, tid, its, comments=comments, gate_pw=pw, build='legacy')
         # ⛔ `pub` потрібен ДАЛІ — деплою (`_publish_legacy_call(…, pub, …)` — модуль запускає `vercel` у цій теці); його
````


### `app/dashboard.py`

````diff
--- a/app/dashboard.py
+++ b/app/dashboard.py
@@ -224,34 +224,8 @@
 LEGACY_TABLE = 'overview_projects'
 LEGACY_MODULE = 'supabase-dashboard'
 UNCONFIGURED = 'Supabase не налаштовано'
-
-
-def legacy_ctx(url, key, space_id=''):
-    """`ctx` неявного постачальника ЛІГИ (`Implicit`): `supabase-dashboard` з адресою й ключем конфігу установки і таблицею
-    `overview_projects`. `url`/`key` — з `supabase_config()` викликача (`serve` кличе СВОЮ обгортку: її підміняють тести);
-    нема конфігу (`url is None`) — `ModuleError('dashboard-unconfigured')` з текстом, який на екрані «Команда» був і раніше.
-
-    ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`, а при вимкненому шарі `spaces.home()` — це
-    справжній `~/.deai` машини (той самий урок, що `serve._vcs_legacy_ctx`/`_comments_legacy_ctx`).
-    `settings.compat = 'comment-layer'` — модуль не відмовляє публічному ключу ЛІГИ (паритет з 0.11.0; `check` ЛІГИ кличеться лише з
-    «Підключення»). `legacy: True` лишено для чужих модулів: вбудовані його НЕ читають (охоронець у `tests/test_liga_migrate.py`)."""
-    if url is None:
-        raise deai_modules.ModuleError('dashboard-unconfigured', message=UNCONFIGURED)
-    return {'space': {'id': space_id, 'path': ''}, 'settings': {'url': url, 'table': LEGACY_TABLE, 'compat': 'comment-layer'},
-            'secrets': {'key': key}, 'ModuleError': deai_modules.ModuleError, 'legacy': True}
 
 
-def legacy_module():
-    """Вбудований `supabase-dashboard` із каталогу БЕЗ простору (шлях ЛІГИ); не завантажився — `ModuleError('module-error')`."""
-    try:
-        m = deai_modules.catalog().get(LEGACY_MODULE)
-    except Exception as e:  # noqa: BLE001 — збій каталогу = відмова модуля, не 500
-        raise deai_modules.ModuleError('module-error', message=f'module catalog: {type(e).__name__}') from None
-    if m is None or m.status != 'ok':
-        raise deai_modules.ModuleError('module-error', message=f'{LEGACY_MODULE} module is not loaded')
-    return m
-
-
 def normalize_rows(data):
     """Рядки команди з відповіді `rows` модуля: лише обʼєкти з рядковим `id`, лише ключі `TEAM_KEYS`, не більше `MAX_ROWS`.
     Не список — `ValueError`. Чужий модуль міг би повернути що завгодно (і зайві колонки таблиці): екран бачить лише це."""
````


### `app/notify.py`

````diff
--- a/app/notify.py
+++ b/app/notify.py
@@ -72,30 +72,3 @@
         raise ValueError('notify: muted must be boolean')
     if not isinstance(by, str) or len(by) > BY_MAX:
         raise ValueError(f'notify: by must be a string of at most {BY_MAX} characters')
-
-
-def legacy_ctx(url, key, space_id=''):
-    """`ctx` неявного постачальника ЛІГИ (`Implicit`): `supabase-teams` з адресою й ключем із конфігу установки
-    (`supabase_config()` викликача — той самий, що в коментарів і дашборда). Нема конфігу (`url is None`) —
-    `ModuleError('notify-unconfigured')` з текстом `UNCONFIGURED`.
-
-    ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`, а при вимкненому шарі `spaces.home()` — це
-    справжній `~/.deai` машини (той самий урок 4c-1, що `dashboard.legacy_ctx`, `tracker.legacy_ctx` і
-    `serve._comments_legacy_ctx`). `settings.compat = 'comment-layer'` — модуль за ним пропускає перевірку публічності ключа й `teams_notify_health`
-    у `check` (у базі ЛІГИ цієї функції нема, а ключ там — публічний ключ сторінки: паритет з 0.13.0).
-    `legacy: True` лишено для чужих модулів: вбудовані його НЕ читають."""
-    if url is None:
-        raise deai_modules.ModuleError('notify-unconfigured', message=UNCONFIGURED)
-    return {'space': {'id': space_id, 'path': ''}, 'settings': {'url': url, 'compat': 'comment-layer'}, 'secrets': {'key': key},
-            'ModuleError': deai_modules.ModuleError, 'legacy': True}
-
-
-def legacy_module():
-    """Вбудований `supabase-teams` із каталогу БЕЗ простору (шлях ЛІГИ); не завантажився — `ModuleError('module-error')`."""
-    try:
-        m = deai_modules.catalog().get(LEGACY_MODULE)
-    except Exception as e:  # noqa: BLE001 — збій каталогу = відмова модуля, не 500
-        raise deai_modules.ModuleError('module-error', message=f'module catalog: {type(e).__name__}') from None
-    if m is None or m.status != 'ok':
-        raise deai_modules.ModuleError('module-error', message=f'{LEGACY_MODULE} module is not loaded')
-    return m
````


### `app/tracker.py`

````diff
--- a/app/tracker.py
+++ b/app/tracker.py
@@ -87,28 +87,3 @@
         except ValueError:
             raise deai_modules.ModuleError('tracker-error', message='модуль трекера віддав відповідь не тієї форми') from None
     return out
-
-
-def legacy_ctx(base, email, token, space_id=''):
-    """`ctx` неявного постачальника ЛІГИ (`Implicit`): `jira-tracker` з адресою, поштою й токеном конфігу установки
-    (`install_config.jira_config()`). `base`/`email`/`token` — з нього викликача; нема конфігу (`base is None`) —
-    `ModuleError('tracker-unconfigured')` з текстом `UNCONFIGURED`.
-
-    ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`, а при вимкненому шарі `spaces.home()` — це
-    справжній `~/.deai` машини (той самий урок 4c-1, що `dashboard.legacy_ctx`, `serve._vcs_legacy_ctx` і
-    `serve._comments_legacy_ctx`). `legacy: True` — модуль цього прапорця не читає (поведінка для ЛІГИ та сама)."""
-    if base is None:
-        raise deai_modules.ModuleError('tracker-unconfigured', message=UNCONFIGURED)
-    return {'space': {'id': space_id, 'path': ''}, 'settings': {'base': base, 'email': email},
-            'secrets': {'token': token}, 'ModuleError': deai_modules.ModuleError, 'legacy': True}
-
-
-def legacy_module():
-    """Вбудований `jira-tracker` із каталогу БЕЗ простору (шлях ЛІГИ); не завантажився — `ModuleError('module-error')`."""
-    try:
-        m = deai_modules.catalog().get(LEGACY_MODULE)
-    except Exception as e:  # noqa: BLE001 — збій каталогу = відмова модуля, не 500
-        raise deai_modules.ModuleError('module-error', message=f'module catalog: {type(e).__name__}') from None
-    if m is None or m.status != 'ok':
-        raise deai_modules.ModuleError('module-error', message=f'{LEGACY_MODULE} module is not loaded')
-    return m
````


### `bin/overview_push.py`

````diff
--- a/bin/overview_push.py
+++ b/bin/overview_push.py
@@ -28,7 +28,6 @@
 from dashboard import build_card as build_row, card_has_pii as row_has_pii, discover_card as discover_row  # noqa: F401
 import dashboard
 import deai_modules
-import implicit
 import install_config
 import spaces
 import tracker
@@ -99,15 +98,6 @@
     return found
 
 
-def _legacy_config():
-    """`(url, key)` ЛІГИ: конфіг установки (файл раніше за оточення); нема — запасна пара `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
-    з оточення (спека §5), і лише так: `supabase_config()` сервісного ключа НЕ бачить (його читають і коментарі)."""
-    url, key = install_config.supabase_config()
-    if url is None:
-        url, key = install_config.service_key_config()
-    return url, key
-
-
 def _target(sp):
     """`(module, ctx, legacy)` постачальника ролі `dashboard` простору `sp`; `(None, None, False)` — постачальника нема.
     неявний постачальник (`Implicit`) — вбудований модуль із `ctx` з конфігу установки (`dashboard.legacy_ctx`, НЕ `module_ctx`: у нього нема
@@ -118,10 +108,7 @@
         prov = deai_modules.provider("dashboard", sp)
         if prov is None:
             return None, None, False
-        liga = isinstance(prov, implicit.Implicit) or sp.get("legacy") is True
-        if isinstance(prov, implicit.Implicit):
-            return dashboard.legacy_module(), dashboard.legacy_ctx(*_legacy_config(), space_id=sp["id"]), liga
-        return prov, deai_modules.module_ctx(sp, prov), liga
+        return prov, deai_modules.module_ctx(sp, prov), sp.get("legacy") is True
     except deai_modules.ModuleError as e:
         raise CliError("⛔ overview: %s" % (e.message or e.code))
     except spaces.SpacesError as e:
@@ -150,10 +137,7 @@
         prov = deai_modules.provider("tracker", sp)
         if prov is None:
             return None
-        if isinstance(prov, implicit.Implicit):
-            module, ctx = tracker.legacy_module(), tracker.legacy_ctx(*install_config.jira_config(), space_id=sp["id"])
-        else:
-            module, ctx = prov, deai_modules.module_ctx(sp, prov)
+        module, ctx = prov, deai_modules.module_ctx(sp, prov)
     except deai_modules.ModuleError as e:
         if e.code == "tracker-unconfigured":        # ЛІГА без `jira_base`/облікових — не збій, а «трекера нема»
             return None
````


### `bin/state.py`

````diff
--- a/bin/state.py
+++ b/bin/state.py
@@ -411,7 +411,7 @@
     # Синк із git — за РОЛЛЮ `vcs` простору, а не за інтеграціями: звичайний простір із `git-sync` синкає так само. Ролі нема
     # (простір без модуля) — «не налаштований», як для задачі без цілі; GitLab-маппінг у файлі такого простору ігнорується.
     try:
-        vcs = vcs_task(cfg, tid, task)
+        vcs = vcs_task(tid, task)
     except OSError as e:            # `VcsError` — відмова постачальника; решта `OSError` — теж не traceback у точці входу в задачу
         vcs, vcs_err = None, e
     else:
````


### `app/install_config.py`

````diff
--- a/app/install_config.py
+++ b/app/install_config.py
@@ -1,14 +1,14 @@
-"""Конфіг УСТАНОВКИ (етап 4c-1): старий файл задач ЛІГИ й адреса/ключ Supabase з нього.
+"""Старий файл задач ЛІГИ й форма облікових, яку знає міграція (етап 4c-1; з 4d-4b — без читачів оригіналів).
 
-Жив у `serve.py`; переїхав сюди, щоб ядро дашборда (`app/dashboard.py`) і CLI-пушер (`bin/overview_push.py`) читали той самий
-конфіг БЕЗ імпорту `serve` (він тягне сервер, мережу й увесь стан). `serve` реекспортує імена: інструменти (`ops/`, `bin/`)
-і тести беруть їх звідти, а `serve.supabase_config` лишається тонкою обгорткою — точкою підміни для тестів.
+Читачі `supabase_config`/`jira_config`/`service_key_config` (корінь файла, оточення, `~/.claude/pipeline-feedback/`) ВИДАЛЕНО: після кроку
+`liga-4d4b` облікові лежать у явних записах `space.json` і `secrets.json`, а рантайм оригіналів не читає (охоронець `tests/test_no_originals.py`).
+Лишилось: шлях і читання старого файла (його потребують міграція, `ops/`, `bin/roots.py`), кошик Storage ЛІГИ й регекспи ФОРМИ (їх потребує
+`liga_migrate`: він один іще знає, як читалися оригінали).
 """
 import json
 import os
 import re
 
-import implicit  # закон ізоляції (`implicit.isolated()`); імпортує лише `os` — циклу з ядром нема
 import spaces  # простори машини: де лежить старий файл задач (`spaces.legacy_tasks_file`)
 
 
@@ -30,124 +30,3 @@
 
 _SUPABASE_URL_RE = re.compile(r'https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?/?', re.ASCII)
 _SUPABASE_KEY_RE = re.compile(r'[\x21-\x7e]+', re.ASCII)
-
-
-def supabase_config():
-    """`(url, key)` проєкту Supabase простору ЛІГА з конфігу УСТАНОВКИ або `(None, None)` (4b-2: констант у коді нема).
-
-    Джерела по черзі: корінь старого `tasks.json` (`supabase_url`, `supabase_key` — той самий файл, що несе
-    `gitlab_ssh_key`), далі змінні оточення `SUPABASE_URL`/`SUPABASE_KEY`. Пара береться ЦІЛОЮ з одного джерела: адреса з
-    файла й ключ з оточення не змішуються. Адреса — ПОВНІСТЮ `https://<хост>[:порт][/]` (хост — літери, цифри, `.`, `-`;
-    без `/` в кінці в результаті), ключ — друковний ASCII без пробілів: так заготовка з документації
-    (`https://<ref>.supabase.co`, `sb_publishable_…`) чи ключ із пробілом дають «конфігу нема» (`comments-unconfigured`), а не
-    мережу з сміттям. Повну перевірку (DNS-імʼя, сервісний ключ) робить модуль `supabase-comments`. Кешу нема: файл маленький.
-    Значень — ні в текстах, ні в журналах.
-
-    ⛔ В ізольованому прогоні (`implicit.isolated()`: `DC_TASKS_FILE` чи `DC_NO_OVERVIEW`) джерело ОДНЕ — корінь файла задач:
-    `SUPABASE_URL`/`SUPABASE_KEY` з оточення ігноруються. Причина: ізольований прогін — «стан не справжній цієї машини», а
-    змінні оточення розробника несуть справжній проєкт ЛІГИ; тест чи демо під `DC_TASKS_FILE` не мусять мовчки дістати його.
-    Під самим `DC_NO_OVERVIEW` (без `DC_TASKS_FILE`) «файл задач» — старий файл установки (`load_legacy_tasks`), як і раніше:
-    відрізаються лише оточення й `pipeline-feedback`, читання файла не змінилось."""
-    try:
-        cfg = load_legacy_tasks()
-    except (OSError, ValueError, RecursionError):      # надто глибока вкладеність JSON — не обвал, а «нема конфігу»
-        cfg = None
-    return supabase_from(cfg)
-
-
-def supabase_from(cfg):
-    """`(url, key)` за вже прочитаним коренем старого `tasks.json` (`cfg`; не словник — як порожній) — та сама логіка й ті самі
-    джерела, що в `supabase_config()` (його тіло, винесене сюди без змін, щоб міграція ЛІГИ `liga_migrate.plan` брала облікові
-    ТИМИ САМИМИ правилами, а не копією; ізоляція `implicit.isolated()` — як там)."""
-    cfg = cfg if isinstance(cfg, dict) else {}
-    sources = [(cfg.get('supabase_url'), cfg.get('supabase_key'))]
-    if not implicit.isolated():                        # ⛔ в ізольованому прогоні оточення не читаємо (див. докстрінг)
-        sources.append((os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY')))
-    for url, key in sources:
-        if not (isinstance(url, str) and isinstance(key, str)):
-            continue
-        url, key = url.strip(), key.strip()
-        # адреса — повністю `https://<хост>[:порт][/]`; ключ — друковний ASCII без пробілів (див. докстрінг)
-        if _SUPABASE_URL_RE.fullmatch(url) and _SUPABASE_KEY_RE.fullmatch(key):
-            return url.rstrip('/'), key
-    return None, None
-
-
-def service_key_config():
-    """`(url, key)` із оточення — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` — або `(None, None)`: ЗАПАСНИЙ ключ ЛІГИ для CLI-пушера
-    (`bin/overview_push.py`), коли `supabase_config()` конфігу не дав (спека 4c-1 §5; так було до 4c-1: сервісний ключ пушер
-    брав з оточення). Та сама перевірка форми, що в `supabase_config`.
-
-    ⛔ Це ОКРЕМА функція, а не четверте джерело `supabase_config()`: його читають і командні коментарі, і Teams, а сервісний
-    ключ (повний доступ до проєкту) туди потрапляти не мусить. Лише пара — адреса з `SUPABASE_URL`, ключ з
-    `SUPABASE_SERVICE_KEY`: так адреса з одного джерела й ключ з іншого не змішуються.
-
-    ⛔ Той самий закон ізоляції, що в `supabase_config()`: в ізольованому прогоні (`implicit.isolated()`: `DC_TASKS_FILE` чи
-    `DC_NO_OVERVIEW`) оточення НЕ читається. Корінь файла задач сервісного ключа не має (форми для нього нема, і заводити її
-    не варто: це найпривілейованіший секрет ЛІГИ), тож у ізоляції результат завжди `(None, None)`. Інакше тест чи демо під
-    `DC_TASKS_FILE` дістали б повний доступ до справжнього проєкту через `bin/overview_push.py` (`_legacy_config`). Поза
-    ізоляцією поведінка 0.15.0 без змін."""
-    if implicit.isolated():                            # ⛔ в ізольованому прогоні оточення не читаємо (див. докстрінг)
-        return None, None
-    url, key = os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_SERVICE_KEY')
-    if isinstance(url, str) and isinstance(key, str):
-        url, key = url.strip(), key.strip()
-        if _SUPABASE_URL_RE.fullmatch(url) and _SUPABASE_KEY_RE.fullmatch(key):
-            return url.rstrip('/'), key
-    return None, None
-
-
-def jira_config():
-    """`(base, email, token)` Jira простору ЛІГА з конфігу УСТАНОВКИ або `(None, None, None)` (4c-2: констант у коді нема).
-
-    Адреса — `jira_base` у корені старого `tasks.json` (той самий файл, що несе `supabase_url`): ПОВНІСТЮ
-    `https://<хост>[:порт][/]`, без `/` в кінці в результаті (форма — як у `supabase_config`: заготовка з документації
-    `https://<сайт>.atlassian.net`, адреса з шляхом чи `user@` дають «конфігу нема», а не мережу з сміттям). Облікові — пара
-    `JIRA_EMAIL`/`JIRA_TOKEN` з оточення, а коли її нема — файли `<HOME>/.claude/pipeline-feedback/jira-email|jira-token`
-    (вміст `strip()`). Пошта й токен читаються НЕЗАЛЕЖНО, як в `_jira_creds` до 4c-2: кожне — значення з оточення, а коли воно
-    порожнє чи негодне, — вміст файла; тож пошта з оточення й токен з файла поєднуються (це не пара Supabase). Пошта —
-    непорожній друкований рядок, токен — друковний ASCII без пробілів. Значень — ні в текстах, ні в журналах; кешу нема: файли маленькі.
-
-    ⛔ В ізольованому прогоні (`implicit.isolated()`: `DC_TASKS_FILE` чи `DC_NO_OVERVIEW`) і адреса, і облікові — ЛИШЕ з кореня
-    файла задач: `jira_base`, `jira_email`, `jira_token` (два останні — нові необовʼязкові ключі для тестових фікстур; форма
-    перевіряється так само, як у джерел оточення). Змінні `JIRA_*` і `<HOME>/.claude/pipeline-feedback/jira-*` НЕ читаються:
-    інакше токен справжньої Jira розробника потрапляв би в тест чи демо. Без облікових у корені — `(None, None, None)`. Під
-    самим `DC_NO_OVERVIEW` (без `DC_TASKS_FILE`) «корінь» — старий файл установки, як і раніше. Поза ізоляцією ключі
-    `jira_email`/`jira_token` кореня ігноруються: поведінка 0.15.0 без змін.
-
-    ⛔ Токен НІКОЛИ не в git/коді/чаті — лише локальний файл (chmod 600). Урок переїхав сюди з `bin/overview_push.py`
-    (`_jira_creds`): у репозиторії живе лише адреса-заготовка, а справжні облікові — на машині людини."""
-    try:
-        cfg = load_legacy_tasks()
-    except (OSError, ValueError, RecursionError):      # надто глибока вкладеність JSON — не обвал, а «нема конфігу»
-        cfg = None
-    return jira_from(cfg)
-
-
-def jira_from(cfg):
-    """`(base, email, token)` за вже прочитаним коренем старого `tasks.json` (`cfg`) — тіло `jira_config()`, винесене без змін
-    (див. його докстрінг: джерела, порядок, ізоляція). Спільний помічник для `liga_migrate.plan`: ті самі правила, не копія."""
-    base = cfg.get('jira_base') if isinstance(cfg, dict) else None
-    if not isinstance(base, str):
-        return None, None, None
-    base = base.strip()
-    if not _SUPABASE_URL_RE.fullmatch(base):           # та сама форма адреси, що в `supabase_config`
-        return None, None, None
-
-    def from_file(name):
-        try:
-            with open(os.path.expanduser('~/.claude/pipeline-feedback/' + name), encoding='utf-8') as f:
-                return f.read()
-        except (OSError, ValueError):
-            return None
-    def pick(env, name, key, valid):
-        if implicit.isolated():                         # ⛔ лише корінь файла задач (ключ `jira_email`/`jira_token`)
-            raw = cfg.get(key)
-            return raw.strip() if isinstance(raw, str) and valid(raw.strip()) else None
-        for raw in (os.environ.get(env), from_file(name)):          # оточення раніше за файл; порожнє/негодне — далі
-            if isinstance(raw, str) and valid(raw.strip()):
-                return raw.strip()
-        return None
-    email = pick('JIRA_EMAIL', 'jira-email', 'jira_email', lambda v: bool(v) and v.isprintable())
-    token = pick('JIRA_TOKEN', 'jira-token', 'jira_token', lambda v: _SUPABASE_KEY_RE.fullmatch(v) is not None)
-    return (base.rstrip('/'), email, token) if (email and token) else (None, None, None)
````


### `bin/registry.py`

````diff
--- a/bin/registry.py
+++ b/bin/registry.py
@@ -258,14 +258,26 @@
     return None
 
 
-def _ssh_key(cfg):
-    key = cfg.get('gitlab_ssh_key') or '~/.ssh/gitlab_ed25519'
-    return os.path.expanduser(key)
+def _ssh_key():
+    """SSH-ключ git спільного реєстру: налаштування `ssh_key` запису `git-sync` простору ЛІГА (4d-4b: корінь `tasks.json` не читаємо), інакше
+    типовий `~/.ssh/gitlab_ed25519`. Простору/запису/шару нема, реєстр просторів чи `space.json` не читаються — типовий."""
+    key = None
+    try:
+        sys.path.insert(0, os.path.join(ROOT, 'app'))
+        import deai_modules
+        import spaces
+        if spaces.layer_on():
+            sp = next((s for s in spaces.read_registry()['spaces'] if s.get('legacy') is True), None)
+            if sp is not None:
+                key = (deai_modules.space_modules(sp).get('git-sync') or {}).get('settings', {}).get('ssh_key')
+    except Exception:  # noqa: BLE001 — реєстр/space.json не читаються: типовий ключ, а не збій синку реєстру
+        key = None
+    return os.path.expanduser(key if isinstance(key, str) and key.strip() else '~/.ssh/gitlab_ed25519')
 
 
 def _git(args, cwd, cfg, check=True, timeout=120):
     env = dict(os.environ,
-               GIT_SSH_COMMAND=f'ssh -i {_ssh_key(cfg)} -o StrictHostKeyChecking=no')
+               GIT_SSH_COMMAND=f'ssh -i {_ssh_key()} -o StrictHostKeyChecking=no')
     r = subprocess.run(['git', *args], cwd=cwd, env=env, text=True,
                        capture_output=True, timeout=timeout)
     if check and r.returncode != 0:
````


### `ops/reseal_gate.py`

````diff
--- a/ops/reseal_gate.py
+++ b/ops/reseal_gate.py
@@ -15,6 +15,7 @@
 # ⛔ Обгортку НЕ збираємо тут своїми руками: і перелік сторінок, і сам HTML
 # віддає serve. До 04.08.2026 цей скрипт мав власний обхід сторінок із власним
 # фільтром — копія логіки публікації, яка мовчки розійшлась би з нею.
+import spaces  # noqa: E402
 from serve import (BUILD_KINDS, BUNDLES, gate_html, load_meta, preview_gate_state,  # noqa: E402
                    preview_index_html, preview_password, legacy_tasks_path)
 
@@ -27,6 +28,15 @@
         return json.load(f)
 
 
+def liga_space():
+    """Запис простору ЛІГА з реєстру (`legacy: true`) або `None`: пароль превʼю — секрет явного `vercel-publish` цього простору (4d-4b).
+    Реєстр не читається — `None` (пароль задачі чи `1100`)."""
+    try:
+        return next((s for s in spaces.read_registry()["spaces"] if s.get("legacy") is True), None)
+    except spaces.SpacesError:
+        return None
+
+
 def rebuild_index(tid, task):
     pub = os.path.join(task["dir"], "publish")
     if not os.path.isfile(os.path.join(pub, "index.html")):
@@ -38,7 +48,7 @@
     # ⚠️ Цей скрипт перезбирає ЛИШЕ обгортку. Гейт у внутрішніх сторінках додає
     # публікація; якщо превʼю зібрано до 03.08.2026, потрібна саме перепублікація,
     # а не reseal — інакше пряме посилання на сторінку так і минатиме пароль.
-    pw = preview_password(load_tasks(), task)
+    pw = preview_password(task, liga_space())
     # ⛔ Обгортка з 02.09.2026 — тонкий каркас: перелік сторінок і назва задачі
     # лежать у `publish/manifest.json`, який пише ЛИШЕ публікація. Тому цей
     # скрипт їх більше не рахує — і не може зістарити (раніше рахував би, а
@@ -115,7 +125,7 @@
                 continue
         # ⛔ Питаємо ДО перезапису обгортки (ревʼю 1.52): інакше після відмови
         # локальний publish/ уже мав би обгортку з новим паролем, а деплой — ні.
-        pw = preview_password(cfg, task)
+        pw = preview_password(task, liga_space())
         gate = preview_gate_state(task, pw)
         if gate["inner_stale"]:
             print(f"⚠ {tid}: {gate['inner_stale']} внутрішніх сторінок зі старим паролем — "
````


### `app/connections-model.js`

````diff
--- a/app/connections-model.js
+++ b/app/connections-model.js
@@ -302,14 +302,11 @@
     && o.status !== "missing" && Array.isArray(o.roles) && o.roles.some((r) => mine.has(r)));
 }
 
-/** Ролі з вбудованим шляхом у ЛІГИ (`'legacy'` у `capabilities`) — вимкнення модуля повертає його, а не «нікого». Токенів ЛІГА не має. */
-const LEGACY_ROLES = new Set(["publish", "comments", "vcs", "dashboard", "tracker", "notify"]);
-
 /**
  * Що станеться з ролями, які `e` зараз ВИКОНУЄ (`capabilities[role] === e.id`), якщо його вимкнути:
- * `[{role, kind: 'legacy'}]` — простір з інтеграціями (ЛІГА) повернеться до вбудованої публікації, коментарів, синку з git, дашборда, трекера чи сповіщень Teams;
  * `[{role, kind: 'none', noneKey}]` — роль лишиться без модуля (для `tracker` і `notify` ще й `consKey` — свій текст наслідку:
- * статуси зникнуть; картки Teams перестануть надходити, а перемикач тиші зникне).
+ * статуси зникнуть; картки Teams перестануть надходити, а перемикач тиші зникне). 4d-4b: у ЛІГИ так само, як деінде, — запасного шляху
+ * (`'legacy'`) після вимкнення запису вже нема, тож «повернеться до вбудованого» було б неправдою.
  */
 export function disableConsequences(e, space) {
   const caps = space?.capabilities;
@@ -317,8 +314,7 @@
   const out = [];
   for (const role of Array.isArray(e.roles) ? e.roles : []) {
     if (role === "error" || !has(caps, role) || caps[role] !== e.id) continue;
-    if (space.integrations === true && LEGACY_ROLES.has(role)) out.push({ role, kind: "legacy" });
-    else if (role === "tracker") out.push({ role, kind: "none", noneKey: roleKeys(role).none, consKey: "cnDisableTracker" });
+    if (role === "tracker") out.push({ role, kind: "none", noneKey: roleKeys(role).none, consKey: "cnDisableTracker" });
     else if (role === "notify") out.push({ role, kind: "none", noneKey: roleKeys(role).none, consKey: "cnDisableNotify" });
     else out.push({ role, kind: "none", noneKey: roleKeys(role)?.none ?? null });
   }
````


### `app/modules/vercel-publish/module.json`

````diff
--- a/app/modules/vercel-publish/module.json
+++ b/app/modules/vercel-publish/module.json
@@ -1,4 +1,4 @@
-{"api": 1, "id": "vercel-publish", "name": "Vercel", "version": "1.2.0",
+{"api": 1, "id": "vercel-publish", "name": "Vercel", "version": "1.3.0",
  "roles": ["publish"], "publish_target": "url", "check_timeout_s": 130,
  "settings": [
    {"key": "auth", "type": "select", "label": "Вхід у Vercel", "default": "token",
@@ -7,6 +7,6 @@
    {"key": "token", "type": "secret", "label": "Токен Vercel (для входу «Токен»)"},
    {"key": "team", "type": "text", "label": "Команда Vercel (slug або team_…; порожньо — особистий акаунт)"},
    {"key": "password", "type": "secret", "label": "Пароль превʼю (необовʼязково)"},
-   {"key": "compat", "type": "select", "label": "Сумісність (⚠ у режимі ЛІГА поля auth, team і password не читаються: вхід, скоуп і пароль превʼю беруться зі старих налаштувань; зміна значення на живому просторі перемикає на шлях модуля — нові проєкти й нові URL)", "required": false, "default": "",
-    "options": [{"value": "", "label": "Немає"}, {"value": "design-canvas", "label": "design-canvas (ЛІГА): проєкти pv-…, скоуп і пароль превʼю з tasks.json"}]}
+   {"key": "compat", "type": "select", "label": "Сумісність (⚠ у режимі ЛІГА поля auth і team не читаються: вхід і скоуп беруться зі старих налаштувань; пароль превʼю — спершу пароль задачі, далі секрет цього модуля; зміна значення на живому просторі перемикає на шлях модуля — нові проєкти й нові URL)", "required": false, "default": "",
+    "options": [{"value": "", "label": "Немає"}, {"value": "design-canvas", "label": "design-canvas (ЛІГА): проєкти pv-…, скоуп з tasks.json, пароль превʼю: задача, далі секрет модуля"}]}
  ]}
````


### Видалено: `app/implicit.py` (48 рядків; `git rm`, Task 10)
