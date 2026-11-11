# Реліз 0.23.0 «Зворотний звʼязок і оновлення» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (А) канвас сам помічає новий тег `vX.Y.Z` у git-репозиторії, з якого поставлено установку, підсвічує пігулку в смузі і за один клік робить `fetch` тега → `merge --ff-only` → димова перевірка → перезапуск (`os.execv`), а коли щось заважає — нічого не чіпає й пояснює людською мовою. (Б) кнопка «Відгук» (і ⌘K «Баг / ідея») у смузі на всіх екранах збирає діагностику (версія, ОС, простір, задача, кільця помилок сервера й клієнта) із редагуванням секретів, показує людині, що піде, і надсилає в окремий Supabase-проєкт Deai (таблиця лише на запис); без мережі чи без налаштованого приймача відгук лягає в локальну чергу й дочищується у фоні.

**Architecture:** три нові чисті Python-модулі без імпорту `serve` (`app/redact.py`, `app/updater.py`, `app/feedback.py`); `serve.py` лише проводить маршрути, фонові потоки в `serve_main` і хук кільця помилок у `_guarded`. Усе, що ходить у мережу чи пише в `<DEAI_HOME>`, проходить через **один** предикат ізоляції (`isolation.isolated()` + `isolation.real_home(spaces.home())`) — тож жоден тест не торкається мережі, справжнього `~/.deai` і справжнього репо. Клієнт: чисті моделі (`update-model.js`, `feedback-model.js`, `err-ring.js`), розмітка рядками (`update-view.js`, `feedback-view.js`), проводка в `app.js` через наявні `BAR_ACTIONS`/`askForm`/`toast`.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний: без `match`, без `X | Y` в анотаціях), `git` зі списком аргументів (без shell), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі), SQL для Supabase (`ops/feedback-collector.sql`, лише текст; сам проєкт створює власник).

**Спека:** `docs/superpowers/specs/2026-11-11-feedback-and-updates-design.md`. Читати перед кожною задачею; **ПОПРАВКИ НИЖЧЕ мають перевагу над текстом спеки й задач.** Попередній етап (зразок процесу): `docs/superpowers/plans/2026-11-10-legacy-surface-gone.md`.

Базова лінія на `3302f2a` (перед T1): JS `node --test tests/*.test.mjs` — 1986 pass / 0 fail (≈3,5 с). Python-пакет `tests/` — записати число з першого прогону в звіті T1 (повний прогін триває >3 хв, запускати у фоні).

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так, з переліком шляхів; новий файл спершу `git add -- <шлях>`:
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<тема>

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  **Ніколи** `git add -A` / `git add .`; не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`; ніколи `--amend`. Після кожної задачі `git diff HEAD | grep '^-[^-]'` показує лише заплановані видалення.
- ⛔ **Живий канвас працює з робочого дерева цього репо на :8765.** Жоден крок не робить у `<repo>` `git checkout`, `git reset`, `git stash`, `git merge`, `git rebase`, `git clean`, `git pull`, `git fetch`, не перезапускає сервер, не викликає `POST /api/update-apply` проти справжнього сервера. Усе, що вчить `git` писати (merge, reset, fetch, tag), тести роблять **лише у викидних репо у тимчасових теках** (`tempfile.mkdtemp`), з підробним `ROOT`.
- ⛔ У жоден комітований файл не пишемо справжніх імен, хостів, імен користувачів машини, ключів чи адрес проєктів; шляхів з імʼям користувача, scratchpad чи тимчасових тек; лише `<repo>`, `<DEAI_HOME>`, `os.path.expanduser('~')` і вигадані значення (`https://sb.example.com`, `git@git.example:org/x.git`, `alpha@example.com`, `sb_publishable_test`). Справжні адреса Supabase і publishable-ключ додасть власник пізніше; **до цього `app/feedback.json` лежить із порожніми `url`/`key`**, і відгуки йдуть у локальну чергу.
- Правки наявних файлів — точкові (`Edit`); нові файли — `Write`.

**Прогони й середовище** (кожен Python-прогін — під тимчасовим `HOME`, без `DC_TASKS_FILE`/`DEAI_HOME` в оточенні; без `.pyc`)

- `PYT` = `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest`
  - один файл: `$PYT tests.test_updater -v`; весь пакет:
    ```bash
    env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s tests -p 'test_*.py'
    env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s bin -p 'test_*.py'
    env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s app -p 'test_*.py'
    ```
- JS: `node --test tests/*.test.mjs && node tests/inspector-core.test.mjs`.
- Живі — по одному файлу, ПОСЛІДОВНО (`test-concurrency=1`):
  `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs`.
- **Мережі в жодному тесті.** Робота з «мережею» в тестах — лише: `git` проти локальних bare-репо в тимчасових теках (remote = шлях файлової системи), HTTP лише на `127.0.0.1` (підробний приймач на порту тесту). `DEAI_NO_UPDATE_CHECK=1` стоїть в оточенні всіх живих серверів (T2 править `tests/live/fixture.mjs`) і в `setUp` Python-тестів, що підіймають `make_server`.
- Після прогонів справжні `~/.deai`, `~/deai-work`, `~/deai-published`, `~/.claude/pipeline-feedback/`, `~/.gitconfig`, справжній `tasks.json` не змінились; порти 8765/4317 не чіпаються; процеси — лише за PID (ніколи `pkill -f`). Кожен новий Python-файл тестів, що пише файли в `<DEAI_HOME>`, підключає `tests/spaces_guard.py` (`setUpModule`/`tearDownModule`, як `tests/test_outbound_parity_4d4c.py`).
- ≤ 1 виконавець + ≤ 1 ревʼюер одночасно; мутації з тайм-аутом; сирот прибирати за PID.
- Кожна нова перевірка доводиться мутацією (`python3 -B`, один рядок → червоніє → відновлено, `sha256` до/після збігається). Охоронець, який не може впасти, — фікція. Еталони (`legacy-golden`, знімки `before-4c1…4d4c`) — зелені БЕЗ `UPDATE_*`.
- **Порядок.** Після кожної задачі ВЕСЬ пакет (Python ×3 + JS) зелений; тести, які ламає задача, правляться в ТІЙ САМІЙ задачі й згадуються у звіті одним рядком із причиною. Живі — лише ті, що названі в задачі, плюс повний прогін у T10.

---

## Поправки до спеки (звірено з кодом на `3302f2a`; мають перевагу)

1. **Маршрути — пласкі, не вкладені.** Спека: `POST /api/update/check`, `/api/update/apply`, `GET /api/update/notes`. Охоронець `bad-body` (`tests/test_serve.py:1415-1437`, `test_a_body_that_is_not_a_json_object_is_json_bad_body_on_every_route`) збирає маршрути регексом `self\.path == '(/api/[a-z-]+)'` — вкладений шлях (`…/update/apply'`) регекс **мовчки пропустить**, і перевірка «тіло — не обʼєкт» його не покриє. Назви: `GET /api/update`, `GET /api/update-notes`, `POST /api/update-check`, `POST /api/update-apply`, `POST /api/feedback-preview`, `POST /api/feedback`. Кожен — окрема гілка `elif self.path == '/api/…'` з обробником `self._x(payload)` (так само, як `/api/gitlab-sync` у `serve.py:6967+`: кортеж `in (…)` теж пропустив би адресу). T2/T3/T6/T7 додають до охоронця перевірку, що нові маршрути знайдено (`assertIn`).
2. **Маршрути «машини», не реєстру й не задачі.** `_take_task` (`serve.py:5776-5846`) для маршруту без заголовка викликає `_pin_current_space`, який при битому реєстрі кидає `SpacesError` → 503 (`serve.py:5757-5774`, `HANDLED_PREFIXES` містить `/api/`). Відгук і оновлення потрібні саме тоді, коли щось зламано (на порожній машині без просторів, при битому реєстрі, з нечитабельним `tasks.json`). Нова кортеж-константа `Handler._MACHINE_ROUTES` (поруч із `_REGISTRY_ROUTES`, `serve.py:5748`): для таких шляхів `_take_task` повертає `True` **без** `_pin_current_space` і без читання задач; префіксна форма `/t/<id>/api/…` відхиляється 400 (як для реєстрових). Обробники збирають контекст (простір, задача) **самі, тотально**: `try/except` на `SpacesError`/`UnknownTask`/`NoTask`/`OSError`/`ValueError` → `None`-поля. Задачу клієнт називає в тілі (`task`), сервер перевіряє `spaces.find_task(tid)` (`AmbiguousTask` → `None`).
3. **Service worker нічого не кешує, тож «нова версія = новий кеш» неприйнятне.** `app/sw.js` — лише мережа (рядки 1-14, 40-52: `respondWith(fetch(req).catch(offlinePage))` лише для навігацій), імені кешу нема. Усе статичне віддається з `Cache-Control: no-cache` (`Handler.end_headers`, `serve.py:5541-5568`). Тож ризик «старий кеш віддає стару оболонку» з спеки — **порожній**; реальні ризики: (а) вікно змішаних версій між `merge` і `execv` (~0,5 с) та запити, що летять під час `execv`; (б) опит `GET /api/update` може відповісти ще **старим** процесом до обміну (див. 9). Замість «версії в імені кешу» T5 фіксує тести-піни: `sw.js` без `caches.`, `app/app.js` віддається з `Cache-Control: no-cache`, і після рестарту сторінка перезавантажується, поки `boot` у відповіді не змінився.
4. **«Що нового» не можна взяти з локального `CHANGELOG.md`:** розділу нової версії там ще нема (він зʼявиться лише після `merge`). Рішення (R-C): `GET /api/update-notes` ледачо робить `git fetch <remote> refs/tags/vX.Y.Z:refs/tags/vX.Y.Z` (додає лише обʼєкти й тег, робоче дерево й гілку не чіпає), далі `git show vX.Y.Z:CHANGELOG.md` і парсить розділи `## [X.Y.Z] — DD.MM.YYYY` у проміжку `(current, latest]`; результат кешується в `update.json` під `notes`. Збій (`offline`) — діалог працює без блоку «Що нового». Тексти CHANGELOG — англійською (формат репо) і не перекладаються: це свідомо, у діалозі підпис «англійською».
5. **`/shot` віддає `image/webp`, а не PNG** (`serve.py:6256-6290`, `Content-Type: image/webp`), і знімка «на вимогу» нема — кадри лежать у `<ітерація>/shots/<node>.webp` і в `manifest.json`. Спека (бакет: PNG ≤ 2 МБ) уточнюється: бакет приймає `image/webp` і `image/png`, ≤ 2 МБ; кадр **більший за 2 МБ не надсилається** (діагностика містить `shot: {skipped: 'too-big'}`). Клієнт називає кадр (`it` + `node` із свого `shotManifest`), сервер перевіряє `NAME_RE`/`SHOT_RE` і читає файл тими самими двома замками, що `_shot` — тож двозамкова логіка виноситься в `serve._shot_file(task, it, node)` (T6), а `_shot` викликає її (без зміни поведінки; наявні тести `shots-*` і `test_serve` пінять).
6. **`_guarded` не має загального `except`** (`serve.py:5611-5655`): невідомий виняток летить повз і потрапляє в `socketserver.handle_error` (stderr). Кільце «50 останніх винятків `_guarded`» вимагає **додати** гілку `except Exception` ПІСЛЯ всіх наявних, яка записує в кільце й **re-raise** (поведінка відповіді не змінюється). Обривання клієнтом (`BrokenPipeError`, `ConnectionResetError`, `ConnectionAbortedError`) у кільце не пишемо — шум. Операційні відмови (`SpaceUnavailable`, `SpacesError`, `ModuleError` зі статусом ≥ 500) пишуться лише кодом (без `str(e)`, бо там шляхи); `NoTask`/`AmbiguousTask`/`ModuleError` < 500 — очікувані 4xx, не пишемо.
7. **Ізоляція: сервери тестів без `DEAI_HOME` пишуть у справжній `~/.deai`.** `spaces.home()` = `DEAI_HOME` або `~/.deai` (`spaces.py:87-88`); живі тести без опції `spaces` не підміняють `HOME`/`DEAI_HOME` (`tests/live/fixture.mjs:176-199`), а `layer_on()` при `DC_TASKS_FILE` без `DEAI_HOME` — `False` (`spaces.py:95-99`). Тому `update.json` і `feedback/` **не пишуться**, коли `isolation.isolated() and isolation.real_home(spaces.home())` (той самий предикат, що в `serve_main`, `serve.py:9018`): стан тоді живе лише в памʼяті процесу. Одна спільна реалізація: у `isolation.py` додається `def writes_allowed(home)` (чиста; T2), її використовують і `updater`, і `feedback`.
8. **Живі сервери крутяться на справжньому `ROOT`** (`startServer(..., root = ROOT)`, `fixture.mjs`). Без захисту фоновий потік оновлення робив би `git ls-remote` у справжнього репо, а `GET /api/update` — `git status` у ньому. Захист у трьох шарах: (а) `DEAI_NO_UPDATE_CHECK=1` у оточенні фікстури; (б) мережевий предикат `updater.network_allowed(remote)`: remote-**шлях файлової системи** (без `://` і без scp-форми `host:path`) дозволений завжди (мережі нема), будь-який інший — лише коли НЕ (`DEAI_NO_UPDATE_CHECK` або `isolation.isolated()`); (в) усі `git`-виклики лише читальні для робочого репо мають `GIT_OPTIONAL_LOCKS=0` (щоб `git status` не оновлював індекс живого дерева). Додатковий стан `state: 'disabled'` (поза переліком спеки `ok|offline|no-git|error`): перевірку вимкнено оточенням; UI мовчить, як при `offline`.
9. **Опит після перезапуску: старий процес ще відповідає.** Між відповіддю `202` і `execv` минає ~0,5 с, і `GET /api/update` у цей час відповідає ще **старим** процесом, але `current` він читає з `package.json` на диску, тобто вже **нову** версію. Опит, що чекає лише `current == target`, перезавантажив би сторінку до рестарту. Тому `GET /api/update` несе `boot` — випадковий токен, що генерується при **імпорті** `updater` (після `execv` модуль імпортується наново → новий токен). Клієнт завершує очікування, коли `boot` ≠ попереднього І `current` = цільова версія.
10. **Перезапуск: `sys.orig_argv` і знімок робочої теки.** `start.command:10` запускає `python3 app/serve.py` з відносним шляхом, `PORT` — зі змінної оточення. `sys.argv` губить прапорці інтерпретатора (`-B`). Знімок береться на старті `serve_main` (до будь-якого `chdir`): `{'cwd': os.getcwd(), 'argv': [sys.executable, *sys.orig_argv[1:]]}` (`sys.orig_argv` є з 3.10; нижче — `[sys.executable, *sys.argv]`). `execv` після `os.chdir(cwd)`. На Windows (`os.name == 'nt'`) `execv` не замінює процес — перезапуск **не** робимо: відповідь `restart: 'manual'` і підказка в діалозі. Дочірні процеси (`shoot`, синк дашборда) при `execv` лишаються сиротами зі старим кодом — тому `busy` (див. 11).
11. **`busy` спеки («міграція чи інше оновлення») уточнено.** Міграція ЛІГИ виконується в `serve_main` ДО `serve_forever` (`serve.py:9009-9011`), тож під час обслуговування її не буває. Справжні випадки: триває інше `apply`; триває зʼємка (`serve._SHOOTS` непорожній, `serve.py:90`); живе процес синку дашборда (`serve._SYNC_RUNS`, `serve.py:5409`). `Updater(busy=callable)`: `serve._update_busy()` повертає перший збіг.
12. **Ціль `apply` — з файла стану, не з запиту.** `POST /api/update-apply` приймає порожнє тіло (шляхи/версії ззовні не приймає); цільова версія = `latest` з `update.json` (нема — `409 nothing-to-update`). Тег перевіряється регексом `^v\d+\.\d+\.\d+$` до **будь-якого** виклику `git`. Локальний тег з тим самим імʼям, але іншим обʼєктом, `fetch` без `+` відхилить (`would clobber existing tag`) → код `tag-conflict`, нічого не змінено.
13. **Валідація remote.** `DEAI_UPDATE_REMOTE` і upstream гілки — недовірені рядки для `git`: перед викликом дозволені лише імʼя remote `^[A-Za-z0-9][\w.-]*$`, URL `https://`/`ssh://`/`git@host:path` або абсолютний шлях; усе інше — `state: 'error', reason: 'bad-remote'`. Усі виклики з `-c protocol.ext.allow=never` і з `--` перед адресою. У відповіді API — лише **хост** (`remote_host`), включно зі scp-формою; userinfo (`https://TOKEN@host`) не витікає (`redact.userinfo`, той самий регекс, що `serve._USERINFO`, пінується тестом на рівність результатів).
14. **Insert-only і ідемпотентність відправки.** Анонімна роль не має `select`, тож `Prefer: return=representation` і `upsert` не працюють: надсилаємо `Prefer: return=minimal`, `id` — uuid клієнта (спека), дубль (`409`, `23505`) після втраченої відповіді = «вже надіслано». Скриншот: `x-upsert: false`, `409 Duplicate` = «вже є». `created_at` клієнт **не надсилає** (колонкові права `insert (id, kind, text, contact, version, os, diag, shot_path)`, час — `default now()`): анонім не підробляє час; локальний `created_at` у черзі лишається для 30-денного ліміту.
15. **Попередній перегляд — `POST`, не `GET` (R-B).** Те, що піде, містить **клієнтську** частину (кільце помилок браузера, мова), якої сервер не має; `GET` показав би неповне. `POST /api/feedback-preview {task?, it?, node?, screen?, lang?, client_errors?}` повертає точну `diag` (те, що піде при `include_diag`) + `shot: {available, bytes, skipped?}` — діалог показує саме це, і `POST /api/feedback` збирає **ту саму** функцію `feedback.build_diag` (серверна частина перераховується, клієнтська проходить санітизацію).
16. **`<DEAI_HOME>/config.json` у коді поки нема** (grep `'config.json'` у `app/*.py` — порожньо). Це новий файл лише для читання (код його ніколи не пише): `{"feedback": {"url", "key"}}`, нечитабельний/невалідний — ігнорується (не кидає). Порядок джерел конфігу відгуку: `DEAI_FEEDBACK_URL`/`DEAI_FEEDBACK_KEY` > `<DEAI_HOME>/config.json` > `app/feedback.json`. Прийняті лише `https://`-адреси; `http://127.0.0.1|localhost|[::1]` — лише коли `isolation.isolated()` (живі тести з фейковим приймачем).
17. **Наявні тести, що фіксують склад `zone1`:** `tests/bar-model.test.mjs:349-395` (`m.zone1.length === 3`, `deepEqual(ids, ["home","palette","crumb-tasks","back"])`, індекси `[0]…[3]`). Нові контроли `feedback` і `update` додаються у **кінець** `zone1` у кожному з трьох повернень `barModel` (`bar-model.js:193, 200, 217+`), так індекси `[0]…[3]` лишаються, а `length`/`deepEqual` оновлюються (T5/T8; кожна правка — рядком у звіті). Розмітка ставить їх **одразу після** кнопки палітри (поруч із `.pal-open`), а не в кінці крошок.
18. **Палітра на екранах «Задачі»/«Підключення»/майстер** повертається раніше (`shell-palette.js:230`: `if (s.homeOpen) return [...spaceActions(s), ...langActions(s), ...installActions(s)]`). «Баг / ідея» і «Перевірити оновлення» мусять бути й там → нова функція `appActions(s)` додається в обидва місця (T5/T8). Виконання дії — `BAR_ACTIONS[a.act] || PANEL_ACTIONS[a.act]` (`app.js:2016-2018`), тож `act: 'feedback'`/`'updatecheck'`/`'updatenotes'`/`'update'` додаються в `BAR_ACTIONS` (`app.js:1742`).
19. **Смоук-перевірка нового коду — не `py_compile`** (спека). `py_compile.compile` пише `.pyc` у `__pycache__` навіть при `-B` (вихідний файл задається явно), тобто «перевірка» забруднила б дерево. Рішення (R-E): дочірній `python3 -B` із `compile(open(p,'rb').read(), p, 'exec')` для всіх `app/*.py` і `bin/*.py` **плюс** `import serve` (`sys.path[0] = <ROOT>/app`) під ізольованим оточенням (`HOME`, `DEAI_HOME`, `DC_TASKS_FILE` — тимчасові, `DEAI_NO_UPDATE_CHECK=1`, `PYTHONDONTWRITEBYTECODE=1`); тайм-аут 30 с. Ловить і синтаксис, і зламаний імпорт. JS синтаксис не перевіряється (Node у користувача може не бути).
20. **Версія в двох місцях:** `package.json` (єдине джерело, спека) і `liga_migrate._tool_version` (`liga_migrate.py:850`, для маніфесту бекапу). `updater.current_version(root)` читає `package.json` сам; тест пінить, що обидві функції на реальному `package.json` дають те саме.
21. **Звичайний dev-checkout завжди `diverged`.** Власний чекаут мейнтейнера (цей репо: `main` на 1 коміт попереду `origin`) ніколи не буде предком релізного тега — для нього «Оновити» чесно відповість `diverged` і підкаже команду. Це не вада, але і пігулка в такого чекаута має поводитись так само, як у всіх (показувати доступну версію): так відомо, що вона вийшла.
22. **Python 3.9** (`X | Y`, `match`, `str.removeprefix` — ні); `subprocess.run(..., capture_output=True, text=True, timeout=…)` — ок. Усі нові рядки інтерфейсу — **лише** в `app/i18n.js` в обох мовах (`tests/i18n-literals.test.mjs`, `tests/i18n-keys.test.mjs`, `tests/i18n.test.mjs`); нові `.js` — без сирих керуючих байтів (`tests/no-control-bytes.test.mjs`); CSS — лише наявні токени (`tests/css-guards.test.mjs`, `tests/test_css_tokens.py`).

### Рішення контролера (потрібні до старту)

- **R-A** Пласкі імена маршрутів (Поправка 1). Рекомендація: так (інакше охоронець `bad-body` сліпий до нових `POST`).
- **R-B** `POST /api/feedback-preview` замість `GET` (Поправка 15). Рекомендація: так.
- **R-C** «Що нового» — ледачий `fetch` тега при відкритті діалогу (Поправка 4). Альтернатива — без блоку «Що нового» до застосування. Рекомендація: ледачий `fetch` (додає лише обʼєкти й тег; збій не блокує оновлення).
- **R-D** Бакет приймає `webp`+`png`, кадр > 2 МБ не надсилається (Поправка 5). Рекомендація: так.
- **R-E** Смоук = `compile` усіх файлів + `import serve` в ізольованому дочірньому процесі (Поправка 19). Рекомендація: так.
- **R-F** Тестовий шов `DEAI_UPDATE_TEST_APPLY=1`: у ізольованому процесі (`DC_TASKS_FILE`) `apply` і `execv` **відмовляють**, якщо шва нема. Він потрібен рівно одному живому тесту (викидний клон репо з власним сервером, T10). Рекомендація: так — без нього жоден живий тест не зможе довести «apply → рестарт → сторінка перезавантажилась», а з ним випадковий виклик проти справжнього `ROOT` відсікається.
- **R-G** Маршрути оновлення й відгуку — «машинні» (Поправка 2). Рекомендація: так.
- **R-H** Кільце помилок сервера — лише в памʼяті (рестарт, зокрема й після оновлення, його скидає). Рекомендація: так; персистентність — не в цьому релізі.

---

## Структура файлів

**Нові:** `app/redact.py`, `app/updater.py`, `app/feedback.py`, `app/feedback.json`, `app/err-ring.js`, `app/update-model.js`, `app/update-view.js`, `app/feedback-model.js`, `app/feedback-view.js`, `ops/feedback-collector.sql`; тести: `tests/test_redact.py`, `tests/test_updater.py`, `tests/test_updater_apply.py`, `tests/test_updater_notes.py`, `tests/test_update_api.py`, `tests/test_feedback_diag.py`, `tests/test_feedback_outbox.py`, `tests/test_feedback_api.py`, `tests/test_feedback_sql.py`, `tests/test_no_network.py`, `tests/update-model.test.mjs`, `tests/feedback-model.test.mjs`, `tests/err-ring.test.mjs`, `tests/live/update.test.mjs`, `tests/live/update-apply.test.mjs`, `tests/live/feedback.test.mjs`, `tests/live/_fake-feedback.mjs`.
**Змінюються (код):** `app/serve.py`, `app/isolation.py`, `app/bar-model.js`, `app/shell-bar.js`, `app/shell-palette.js`, `app/i18n.js`, `app/app.js`, `app/styles.css`.
**Змінюються (тести/документи):** `tests/live/fixture.mjs`, `tests/test_serve.py`, `tests/bar-model.test.mjs`, `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs`, `tests/pwa.test.mjs`, `tests/test_pwa.py`, `tests/test_isolation.py`; `CHANGELOG.md`, `README.md`, `package.json`.

---

### Task 1: `app/redact.py` — редагування рядків (чиста функція, без залежностей)

**Files:** Create `app/redact.py`, `tests/test_redact.py`.

Одна реалізація фільтра для тексту помилок, діагностики й повідомлень кілець. Імпортує лише `os`, `re`, `pwd` (як `isolation.real_home`); **не** імпортує `serve`/`spaces`.

- [ ] **Step 1: тест (червоний).** `tests/test_redact.py` — приклади:
  ```python
  """Редагування діагностики (0.23, T1): домашній шлях → `~`, ключі/токени → `‹приховано›`, e-mail → `‹e-mail›`, query URL відрізається."""
  import os
  import sys
  import unittest

  sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
  import redact  # noqa: E402

  HIDDEN, MAIL = '‹приховано›', '‹e-mail›'


  class Redact(unittest.TestCase):
      def test_home_becomes_tilde_both_forms(self):
          home = os.path.expanduser('~')
          self.assertEqual(redact.text('open %s/work/x.json failed' % home), 'open ~/work/x.json failed')
          self.assertEqual(redact.text('%s' % home), '~')

      def test_roots_are_labelled_longest_first(self):
          roots = [('/data/space/a', '<space>'), ('/data/space/a/tasks', '<tasks>')]
          self.assertEqual(redact.text('x /data/space/a/tasks/it1 y', roots=roots), 'x <tasks>/it1 y')

      def test_key_like_strings(self):
          samples = [
              'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiJ9.abcDEF123_-xyz',   # JWT
              'sk-' + 'A1b2C3d4E5f6G7h8I9j0',                                                # sk-…
              'sb_publishable_' + 'Abc123Def456Ghi789Jkl',
              'ghp_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8',
              'glpat-' + 'A1b2C3d4E5f6G7h8I9j0',
              'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0',                                     # довгий base64-подібний
              '0123456789abcdef0123456789abcdef01234567',                                    # довгий hex
          ]
          for s in samples:
              with self.subTest(s=s[:12]):
                  out = redact.text('token=%s end' % s)
                  self.assertNotIn(s, out)
                  self.assertIn(HIDDEN, out)

      def test_innocent_long_words_and_paths_survive(self):
          for s in ('internationalization-and-localization-settings',      # лише літери
                    '/very/long/path/segment/that/goes/on/and/on/file.js',
                    'iterations/it1/holovna/index.html', '1234567890'):
              self.assertEqual(redact.text(s), s, s)

      def test_email_and_url_query(self):
          self.assertEqual(redact.text('write alpha@example.com now'), 'write %s now' % MAIL)
          self.assertEqual(redact.text('GET https://h.example/a/b?token=zzz&x=1 failed'), 'GET https://h.example/a/b failed')
          self.assertEqual(redact.text('GET /api/task?it=it1'), 'GET /api/task')

      def test_userinfo_same_as_serve_mask_repo(self):
          import serve
          for s in ('clone https://TOKEN@git.example/o/r.git', 'x ssh://user:p@ss@host/r', 'plain text'):
              self.assertEqual(redact.userinfo(s), serve._mask_repo(s), s)

      def test_limit_and_non_string(self):
          self.assertEqual(len(redact.text('x' * 1000, limit=300)), 300)
          self.assertEqual(redact.text(None), '')
          self.assertEqual(redact.text(5), '5')

      def test_order_secret_before_email_inside_url_and_idempotent(self):
          once = redact.text('https://u:pw@h.example/x?k=1 alpha@example.com ' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0')
          self.assertEqual(redact.text(once), once)
  ```
  `$PYT tests.test_redact` → `ModuleNotFoundError: redact`.
- [ ] **Step 2: код.** `app/redact.py`:
  ```python
  HIDDEN = '‹приховано›'
  EMAIL = '‹e-mail›'
  _USERINFO = re.compile(r'(://)[^/\s]*@')            # те саме правило, що `serve._USERINFO`
  def userinfo(text): ...                              # `_USERINFO.sub(r'\1***@', text)` для рядка
  def text(value, roots=(), limit=300): ...
  ```
  Порядок застосування (несучий, тест `test_order…`): 1) `roots` (довші префікси першими, за `os.path` межею: після збігу далі `/` чи кінець); 2) домашній шлях → `~` (і `os.path.expanduser('~')`, і `pwd`-дім, довший першим); 3) `userinfo`; 4) відрізання query `(https?://\S*?|/api/\S*?)\?[^\s'")]*` → без `?…`; 5) ключоподібні: JWT `eyJ[\w-]{8,}\.[\w-]{8,}(\.[\w-]*)?`, префікси `sk-`, `sb_(publishable|secret)_`, `ghp_`, `gho_`, `glpat-`, `xox[bap]-` з `[\w-]{12,}`, та загальний `(?<![\w/.-])[A-Za-z0-9_+=-]{32,}(?![\w/.-])` **лише коли** збіг містить і цифру, і літеру (імена з самих літер і числа не чіпає); 6) e-mail `[\w.+-]+@[\w-]+\.[\w.-]+`; 7) обрізання до `limit` (знаків, без розриву сурогатної пари). Не-рядок → `str()`, `None` → `''`. Ідемпотентна.
- [ ] **Step 3: повний прогін** (Python ×3 + JS зелені). **Мутації** (T1, таблиця в кінці): M1 `redact.text` без кроку 5 → `test_key_like_strings`; M2 без домашнього шляху → `test_home…`; M3 загальний регекс без перевірки «цифра+літера» → `test_innocent…`; M4 e-mail до userinfo (змінити порядок) → `test_order…`.
- [ ] **Step 4: коміт** `feat(0.23): redact — редагування шляхів, ключів, e-mail і query у діагностиці` (`app/redact.py`, `tests/test_redact.py`).

---

### Task 2: оновлення — ядро: версія, remote, перевірка, стан, `GET /api/update`, `POST /api/update-check`, фоновий потік

**Files:** Create `app/updater.py`, `tests/test_updater.py`, `tests/test_update_api.py`; Modify `app/isolation.py`, `app/serve.py` (імпорт `:36`-блок; `_MACHINE_ROUTES` біля `:5748`; `_take_task` `:5776`; `do_GET` біля `:5897`; `do_POST` перед `else:` `:7008`; `serve_main` `:9006`), `tests/live/fixture.mjs` (`:176-199`), `tests/test_serve.py` (охоронець `:1415`), `tests/test_isolation.py`.

- [ ] **Step 0: розвідка в коментарі до коміту.** `git remote -v`, `git config --get branch.main.remote` — лише читання. Переконатись, що `tasks.json` у `.gitignore` (так: `.gitignore:14`), тож робочий чекаут із працюючим канвасом проходить `git status --porcelain --untracked-files=no` чистим.
- [ ] **Step 1: `isolation.writes_allowed(home)`** (Поправка 7). Червоний тест у `tests/test_isolation.py`: `writes_allowed(<tmp>) is True`; з `DC_TASKS_FILE` і `home` = `<pwd-дім>/.deai` → `False`; з `DC_TASKS_FILE` і тимчасовим `home` → `True`. Код: `return not (isolated() and real_home(home))`. Мутація: `or` замість `and` → червоніє.
- [ ] **Step 2: червоні тести ядра** `tests/test_updater.py` (реальні git-репо в тимчасових теках; **без мережі**: remote — шлях bare-репо):
  ```python
  def make_world(tmp, version='0.1.0', tags=('v0.1.0',)):
      """bare-remote + клон `work` з package.json і тегами; повертає (remote, work)."""
      remote, work = os.path.join(tmp, 'remote.git'), os.path.join(tmp, 'work')
      git(['init', '--bare', '-b', 'main', remote])
      git(['clone', remote, work]); ...                        # commit package.json {"version": version}; tag; push --tags
      return remote, work

  class TagParsing(unittest.TestCase):
      def test_semver_tags_only(self):
          out = '\n'.join('%040d\trefs/tags/%s' % (i, t) for i, t in enumerate(
              ['v0.9.0', 'v0.10.0', 'v0.10.0-rc1', 'v1.0', 'vX.Y.Z', 'latest', 'v0.2.0.1', 'v0.10.1']))
          self.assertEqual(updater.latest_tag(out), '0.10.1')       # 10 > 9 за числами, не за рядками
      def test_none_when_no_tags(self): self.assertIsNone(updater.latest_tag(''))
      def test_tag_regex_blocks_option_injection(self):
          for bad in ('v1.2.3 --upload-pack=x', '-v1.2.3', 'v1.2.3\n', 'v1.2'):
              self.assertIsNone(updater.parse_tag(bad))

  class RemoteChoice(unittest.TestCase):
      def test_upstream_then_origin_then_env_override(self): ...      # реальні репо: upstream з branch.main.remote
      def test_bad_remote_is_refused_before_any_git_call(self):
          for r in ('-oProxyCommand=x', 'ext::sh -c id', 'file:///etc/passwd;x', ''):
              self.assertEqual(updater.check_remote(r), False)
      def test_remote_host_only_never_userinfo(self):
          self.assertEqual(updater.remote_host('https://TOKEN@git.example/o/r.git'), 'git.example')
          self.assertEqual(updater.remote_host('git@git.example:o/r.git'), 'git.example')
          self.assertEqual(updater.remote_host('/tmp/x/remote.git'), 'local')

  class Check(unittest.TestCase):
      def test_available_and_state_file_0600(self): ...                # work@0.1.0, remote має v0.2.0 → available, update.json 0600, ключі checked_at/latest/state/reason/last_update
      def test_not_available_when_equal_or_older(self): ...
      def test_offline_keeps_previous_latest(self): ...                # remote видалено → state 'offline', latest із попереднього ok лишається
      def test_not_a_git_clone_is_no_git(self): ...                    # root без .git → state 'no-git'
      def test_status_has_no_paths_or_urls(self):                      # серіалізація status() не містить tmp-шляху й remote-шляху
          ...
      def test_blocked_codes(self):                                    # dirty (змінений відстежуваний файл), untracked ігнорується, detached, worktree, busy(callable), not-git
          ...
      def test_blocked_not_computed_when_nothing_to_update(self): ... # git status не викликається (підробний runner рахує виклики)
      def test_status_uses_optional_locks_off(self): ...              # runner отримав env GIT_OPTIONAL_LOCKS=0 для status
      def test_network_remote_refused_when_isolated_or_disabled(self):
          # remote 'https://git.example/o/r.git' + DEAI_NO_UPDATE_CHECK=1 → state 'disabled', runner НЕ викликано
          # remote — шлях bare-репо + DEAI_NO_UPDATE_CHECK=1 → перевірка ВИКОНАНА (мережі нема)
          ...
      def test_no_state_file_in_real_home_when_isolated(self): ...    # isolated()+real_home → update.json не створено, стан у памʼяті
      def test_boot_token_is_stable_in_process_and_random(self): ...
      def test_current_version_matches_liga_migrate_tool_version(self):
          import liga_migrate
          self.assertEqual(updater.current_version(updater.PRODUCT_ROOT), liga_migrate._tool_version())
  ```
  Підробний runner (`runner(args, cwd, timeout, env)` → `(rc, out, err)`) — для тестів, які рахують виклики; реальні — через `updater.run_git`.
- [ ] **Step 3: код `app/updater.py`** (без імпорту `serve`; імпортує `isolation`, `spaces`, `atomic_io`):
  - константи `TAG_RE = re.compile(r'^v(\d+)\.(\d+)\.(\d+)$')`, `CHECK_EVERY_S = 6 * 3600`, `LS_REMOTE_TIMEOUT_S = 15`, `FETCH_TIMEOUT_S = 60`, `PRODUCT_ROOT`, `BOOT = secrets.token_hex(8)` (при імпорті), `STATES = ('ok', 'offline', 'no-git', 'error', 'disabled')`.
  - `run_git(args, cwd, timeout, env_extra=None)`: `subprocess.run(['git', '-c', 'protocol.ext.allow=never', *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0', **({} if 'GIT_SSH_COMMAND' in os.environ else {'GIT_SSH_COMMAND': 'ssh -o BatchMode=yes -o ConnectTimeout=10'}), **(env_extra or {})})`; `TimeoutExpired` → `(124, '', 'timeout')`; `FileNotFoundError` (нема `git`) → `(127, '', 'no-git-binary')`. Без `shell`.
  - `parse_tag`, `latest_tag(ls_remote_out)`, `version_tuple(str)`, `current_version(root)`, `check_remote(r)`, `remote_host(r)`, `network_allowed(remote)`, `remote_for(root, run)`.
  - `class Updater(root, run=run_git, home=spaces.home, busy=lambda: None, clock=time.time)`: `check()` (мережа лише через `network_allowed`), `status()` (читає `update.json`; `blocked` лише коли `available`), `_blocked()`, `_save()`/`_load()` (`atomic_write_json`, 0600, тека 0700; не пише, коли `not isolation.writes_allowed(home())`; тоді тримає стан у `self._mem`).
  - `start_background(updater, stop=None)`: daemon-потік: перша перевірка через 5 с після старту (не блокує порт), далі кожні `CHECK_EVERY_S`; **не стартує**, коли `os.environ.get('DEAI_NO_UPDATE_CHECK') == '1'` (але `check()` лишається доступною вручну проти локального remote).
- [ ] **Step 4: проводка в `serve.py`.** (а) `import updater` у блоці `:34-36`; (б) `UPDATER_ROOT = ROOT`, `_UPDATER = None`, `def _updater()` (ліниво: `updater.Updater(UPDATER_ROOT, busy=_update_busy)`), `def _update_busy()` (`_SHOOTS` під `_SHOOTS_LOCK` непорожній → `'shooting'`; `_SYNC_RUNS` має живий `popen.poll() is None` → `'syncing'`; інакше `None`); (в) `Handler._MACHINE_ROUTES = ('/api/update', '/api/update-check', '/api/update-apply', '/api/update-notes', '/api/feedback', '/api/feedback-preview')` (Поправка 2) і гілка у `_take_task`: для префіксної форми — 400 (текст як для реєстрових), без префікса — `return True` до `_pin_current_space`; (г) `do_GET`: `if self.path.split('?')[0] == '/api/update': self._send_json(_updater().status()); return`; (д) `do_POST`: `elif self.path == '/api/update-check': self._update_check(payload)` перед `else: send_error(404)` (`:7008`); `_update_check` повертає `{'ok': True, **status()}` після `check()`; (е) `serve_main`: після блоку `static-publish` (`:9013-9022`) — `updater.snapshot_restart()` (T3) і `updater.start_background(_updater())` у `try/except Exception` (крок не валить старт, як сусідній).
- [ ] **Step 5: фікстура й охоронці.** `tests/live/fixture.mjs`: у `env:` дочірнього процесу (перед `...(iso ? {…} : {})`, `:179-186`) додати `DEAI_NO_UPDATE_CHECK: "1"`, `DEAI_FEEDBACK_URL: ""`, `DEAI_FEEDBACK_KEY: ""` (T7 використовує). `tests/test_no_network.py`: розбирає `fixture.mjs` як текст і перевіряє наявність усіх трьох ключів у обʼєкті `env` (мутація: прибрати рядок → червоніє). `tests/test_serve.py::test_a_body_that_is_not_a_json_object_…` (`:1415`): додати `for r in ('/api/update-check', '/api/update-apply'): self.assertIn(r, routes)` — **лише для вже доданих у цій задачі** (`update-apply` — у T3, `feedback*` — у T6/T7: кожна задача дописує свої).
- [ ] **Step 6: HTTP-тести** `tests/test_update_api.py` (`make_server(0)` з `DC_TASKS_FILE`+`DEAI_NO_UPDATE_CHECK=1`, `serve.UPDATER_ROOT` і `serve._UPDATER` підмінені на викидний світ із `make_world`, `DEAI_HOME` тимчасовий; `spaces_guard`): `GET /api/update` → 200 `{current, latest, available, checked_at, state, reason, blocked, remote_host, boot}`; `POST /api/update-check` (Origin `https://evil.example` → 403, без Origin/localhost → 200, `available: true` після появи тега в remote); GET працює **без жодної задачі й без реєстру** (порожня машина) і при битому `spaces.json` (запис `{` у реєстр → усе одно 200; Поправка 2); префіксна форма `/t/x/api/update` → 400; відповідь без шляхів (`assertNotIn(tmp, body)`).
- [ ] **Step 7: повний прогін** + **мутації** M5…M13 (таблиця). **Коміт** `feat(0.23): оновлення — перевірка тегів у remote, стан update.json, GET /api/update, POST /api/update-check` (`app/updater.py`, `app/isolation.py`, `app/serve.py`, `tests/live/fixture.mjs`, `tests/test_serve.py`, `tests/test_isolation.py`, `tests/test_updater.py`, `tests/test_update_api.py`, `tests/test_no_network.py`).

---

### Task 3: оновлення — застосування (передумови, fetch, ff, смоук, відкат, `execv`)

**Files:** Modify `app/updater.py`, `app/serve.py` (маршрут `elif self.path == '/api/update-apply'` поруч із `update-check`; `serve_main`), `tests/test_serve.py` (охоронець); Create `tests/test_updater_apply.py`.

- [ ] **Step 0: перевірка смоуку (лише читання/тимчасове оточення):** `env HOME=$(mktemp -d) DEAI_HOME=$(mktemp -d) DC_TASKS_FILE=$(mktemp -d)/t.json PYTHONDONTWRITEBYTECODE=1 python3 -B -c "import sys; sys.path.insert(0,'app'); import serve"` із `<repo>` завершується < 3 с, нічого не друкує й не створює файлів поза `/tmp`. Результат — рядком у звіті (від цього залежить R-E).
- [ ] **Step 1: червоні тести** `tests/test_updater_apply.py` — усі на викидних світах (`make_world`), `Updater(root=work, restart=fake)`:
  ```python
  class Apply(unittest.TestCase):
      def test_fast_forward_then_restart_scheduled(self): ...         # work@0.1.0, remote v0.2.0 (+commit з package.json 0.2.0) → ok, HEAD == tag, current_version == '0.2.0', last_update {from,to,at} у update.json, restart викликано РІВНО раз
      def test_nothing_to_update(self): ...                           # state без latest → (409,'nothing-to-update'), git не викликано
      def test_dirty_blocks_and_changes_nothing(self):                # змінений відстежуваний файл → 'dirty'; HEAD і файл побайтно ті самі; fetch не викликано
          ...
      def test_untracked_file_does_not_block(self): ...
      def test_detached_and_worktree_and_not_git(self): ...
      def test_busy_blocks(self): ...                                  # busy() == 'shooting'
      def test_diverged_local_commit(self):                            # локальний коміт, якого нема в релізі → 'diverged'; HEAD не змінено; відповідь несе команду-підказку (без шляхів)
          ...
      def test_offline_fetch_fails_changes_nothing(self): ...          # remote видалено → 'offline'
      def test_tag_conflict(self):                                     # локальний тег v0.2.0 на ІНШОМУ коміті → 'tag-conflict', HEAD не змінено
          ...
      def test_smoke_failure_rolls_back_to_old_head(self):             # новий коміт має синтаксичну помилку в app/x.py → 'rolled-back', HEAD == старий, `git status` чистий, restart НЕ викликано
          ...
      def test_smoke_failure_import_error_also_rolls_back(self): ...  # app/serve.py з `import nonexistent_module`
      def test_rollback_resets_only_to_the_recorded_head(self):        # підробний runner: єдиний `reset` — `--hard <старий sha>`, і лише ПІСЛЯ успішного merge
          ...
      def test_target_comes_from_state_not_request(self): ...         # apply(body={'version':'9.9.9'}) ігнорує тіло
      def test_second_apply_while_running_is_busy(self): ...          # замок
      def test_isolated_process_refuses_apply_on_product_root_without_the_seam(self):
          # DC_TASKS_FILE виставлено, root == updater.PRODUCT_ROOT, шва нема → 'isolated'; із DEAI_UPDATE_TEST_APPLY=1 → проходить до git
          ...
      def test_no_pyc_written_by_the_smoke(self): ...                  # у викидному `work` після apply нема __pycache__/*.pyc

  class Restart(unittest.TestCase):
      def test_exec_restart_uses_snapshot_cwd_and_argv(self):          # fake execv: аргументи == [sys.executable, *orig_argv[1:]], chdir на знімок
          ...
      def test_exec_restart_refused_when_isolated_without_seam(self): ...  # execv НЕ викликано
      def test_windows_is_manual(self): ...                            # os.name == 'nt' (patch) → restart 'manual', execv не викликано
      def test_snapshot_taken_before_chdir(self): ...
  ```
- [ ] **Step 2: код.** `Updater.apply(restart=None)` → `(status_code, body)`:
  1. `isolated`-шов (Поправка/R-F): `if isolation.isolated() and not os.environ.get('DEAI_UPDATE_TEST_APPLY') and realpath(root) == realpath(PRODUCT_ROOT): return 409 'isolated'`;
  2. замок `self._apply_lock.acquire(blocking=False)` → інакше `409 busy`; `busy()` → `409 busy`;
  3. ціль = `latest` зі стану; нема/не `available` → `409 nothing-to-update`; `TAG_RE` на `v<latest>` **до** будь-якого `git`;
  4. `blocked` (`not-git`, `dirty`, `detached`, `worktree`) → `409` з кодом і без змін;
  5. `git rev-parse HEAD` → `old`; `git fetch -- <remote> refs/tags/vX:refs/tags/vX` (60 с): `rc != 0` → `offline` (503), а якщо stderr містить `clobber`/`would clobber` → `tag-conflict` (409);
  6. `git merge-base --is-ancestor HEAD vX^{commit}`: rc 1 → `409 diverged` (`hint`: `merge-hint` — рядок-ключ для i18n, команда збирається клієнтом з `latest`); rc ≥ 2 → `500 error`;
  7. `git merge --ff-only vX^{commit}`: збій → `500 merge-failed` (нічого не змінено: `ff-only` атомарний);
  8. смоук (Поправка 19) у дочірньому процесі; збій → `git reset --hard <old>` (єдиний `reset` у модулі; тільки тут, лише після успішного кроку 7) → `500 rolled-back`;
  9. `last_update = {from, to, at}` у стан; повертає `(202, {'ok': True, 'to': latest, 'restart': 'auto'|'manual'})`; **після** відправки відповіді `serve` викликає `threading.Timer(0.5, restart).start()` (сам `apply` рестарт не планує — так тест бачить відповідь до `execv`).
  - `snapshot_restart()` / `exec_restart(snapshot=None, execv=os.execv)` (Поправка 10; `isolated()` без шва → `False`, нічого не викликає; `os.name == 'nt'` → `False`); `serve_main` викликає `updater.snapshot_restart()` **першим рядком** після `make_server`.
  - `serve._update_apply(payload)`: `status, body = _updater().apply(); self._send_json(body, status=status)`; при `202` — `threading.Timer(0.5, lambda: _restart()).start()`, де `_restart = updater.exec_restart` (підміняється в тестах: `serve._restart = fake`).
- [ ] **Step 3: HTTP-тест** (у `tests/test_update_api.py`): `POST /api/update-apply` проти викидного світу з підробним `serve._restart` → `202`, `restart` викликано один раз **після** відповіді, `GET /api/update` показує нову `current`; чужий Origin → 403; тіло `[]` → 400 `bad-body`. Охоронець `tests/test_serve.py`: `assertIn('/api/update-apply', routes)`.
- [ ] **Step 4: повний прогін** + мутації M14…M22. Перед стартом мутацій — `sha256` усіх змінюваних файлів. **Ні в одному кроці** `apply` не викликається проти `<repo>`: перевірити `git -C <repo> log -1 --format=%H` до/після — однаково. **Коміт** `feat(0.23): оновлення — застосування тега (fetch, ff-only, смоук, відкат, перезапуск)` (`app/updater.py`, `app/serve.py`, `tests/test_serve.py`, `tests/test_updater_apply.py`, `tests/test_update_api.py`).

---

### Task 4: оновлення — «Що нового» з CHANGELOG віддаленого тега

**Files:** Modify `app/updater.py`, `app/serve.py` (`do_GET`: `/api/update-notes`); Create `tests/test_updater_notes.py`.

- [ ] **Step 1: червоні тести.** Парсер — чиста функція `updater.parse_changelog(text, after, upto)`:
  ```python
  SAMPLE = '''# Changelog\n\n## [0.3.0] — 12.11.2026\n\nThree.\n\n### Added\n\n- c\n\n## [0.2.0] — 11.11.2026\n\nTwo.\n\n## [0.1.0] — 10.11.2026\n\nOne.\n'''
  def test_sections_between_current_exclusive_and_latest_inclusive(self):
      got = updater.parse_changelog(SAMPLE, after='0.1.0', upto='0.3.0')
      self.assertEqual([s['version'] for s in got], ['0.3.0', '0.2.0'])
      self.assertEqual(got[1]['date'], '11.11.2026')
  def test_text_only_no_html_and_capped(self):                # `<script>` лишається ТЕКСТОМ; розділ ≤ 8 КБ, усього ≤ 40 КБ; керуючі символи (Cc/Cf крім \n) вирізано
  def test_malformed_headings_ignored(self): ...             # `## [x.y.z]`, `## [0.2]`, без дати → пропуск
  def test_unreleased_ignored(self): ...
  ```
  Інтеграція на викидних світах: `notes()` робить `fetch` тега, `git show vX:CHANGELOG.md` (`-- ` не потрібен: `rev:path` один аргумент, який збирає код із **перевіреного** тега), кешує в `update.json` `notes: {version, sections}`; повторний виклик без мережі (remote видалено) віддає кеш; `offline` без кешу → `{'ok': True, 'sections': [], 'reason': 'offline'}`; `no-git` → `reason: 'no-git'`; після `fetch` **робоче дерево й HEAD не змінились** (SHA до/після); тег з нормалізованим CHANGELOG > 1 МБ → читаємо перші 1 МБ.
- [ ] **Step 2: код** `Updater.notes()` + `serve._update_notes` (`GET /api/update-notes` → `{ok, version, sections: [{version, date, body}], reason?}`; машинний маршрут, без шляхів у відповіді). Додати `/api/update-notes` у `Handler._MACHINE_ROUTES` (вже в кортежі з T2).
- [ ] **Step 3: повний прогін** + мутації M23, M24. **Коміт** `feat(0.23): оновлення — «Що нового» з CHANGELOG віддаленого тега` (`app/updater.py`, `app/serve.py`, `tests/test_updater_notes.py`).

---

### Task 5: оновлення — інтерфейс (пігулка, діалог, ⌘K, опит після рестарту)

**Files:** Create `app/update-model.js`, `app/update-view.js`, `tests/update-model.test.mjs`; Modify `app/bar-model.js` (`:193, :200, :217-…`), `app/shell-bar.js` (поруч із `paletteBtn`, `:549`; виклик у `barHTML`, `:591+`), `app/shell-palette.js` (`:230`, нова `appActions`), `app/i18n.js` (обидві мови), `app/app.js` (імпорти `:15-55`, `barState` `:878`, `BAR_ACTIONS` `:1742`, `paletteState` `:7148`, опит біля `:5203`), `app/styles.css`, `tests/bar-model.test.mjs`, `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs`, `tests/pwa.test.mjs`, `tests/test_pwa.py`.

- [ ] **Step 1: червоні JS-тести моделі** `tests/update-model.test.mjs`:
  ```js
  import { pillModel, blockedHelp, restartStep, notesToBlocks, RESTART_DEADLINE_MS } from "../app/update-model.js";
  test("пігулка лише коли available; offline/error/disabled мовчать", ...);
  test("blockedHelp: кожен код blocked дає ключ i18n і (де є) команду; невідомий код → generic", ...);   // dirty→git stash; diverged→git merge v<latest>; not-git/worktree/detached/busy/isolated без команди або з generic
  test("restartStep: чекаємо, поки boot змінився І current == target; помилка мережі = wait; дедлайн = fail", () => {
    const s = (o) => restartStep({ prevBoot: "a", target: "0.2.0", startedAt: 0, now: 1000 }, o);
    assert.equal(s({ ok: false }), "wait");                                       // сервер ще лежить
    assert.equal(s({ ok: true, boot: "a", current: "0.2.0" }), "wait");           // старий процес уже бачить нову версію на диску (Поправка 9)
    assert.equal(s({ ok: true, boot: "b", current: "0.1.0" }), "fail");           // новий процес, але версія не та (відкат)
    assert.equal(s({ ok: true, boot: "b", current: "0.2.0" }), "done");
    assert.equal(restartStep({ prevBoot: "a", target: "0.2.0", startedAt: 0, now: RESTART_DEADLINE_MS + 1 }, { ok: false }), "fail");
  });
  test("notesToBlocks: лише текст — `<script>` лишається рядком, заголовки ### і пункти '- ' розпізнано", ...);
  ```
  + `tests/update-view` перевірки розмітки (у тому ж файлі): діалог — `<form class="cv-form up" … role="dialog" aria-modal="true" aria-labelledby="up-h">`, кнопка `button[type=submit][data-a=ok]` має `disabled` + видиму причину (`.up-why`), коли `blocked`; блок команди має `data-copy`; усі дані через `esc`; тексти CHANGELOG — в `<pre>`/`<li>` лише через `esc`.
- [ ] **Step 2: код моделі й вигляду.** `update-model.js` (чисте): `pillModel(update)` → `null | {version, labelKey: 'upPill'}`; `blockedHelp(blocked, latest)` → `{key, command?}` (команди — **шаблони без шляхів**: `git stash`, `git merge v<latest>`; перелік кодів з Поправок: `not-git`, `dirty`, `detached`, `worktree`, `busy`, `isolated`, `diverged`, `tag-conflict`, `offline`, `rolled-back`, `merge-failed`, `nothing-to-update`); `restartStep`; `notesToBlocks`. `update-view.js`: `updateDialogHTML({current, latest, blocked, state, reason, sections, applying, error})`, `updatePillHTML(model)`. Кнопка пігулки: `data-act="update"` (клас `ctl upd-pill`).
- [ ] **Step 3: i18n (обидві мови, ключі з префіксом `up`).** Мінімум: `upPill(v)` («Оновлення {v}»), `upTitle`, `upFromTo(a, b)`, `upWhatsNew`, `upNotesEnglish`, `upApply`, `upApplying`, `upDone`, `upBlocked_<код>` для кожного коду (людською мовою, з порадою), `upCopyCmd`, `upCopied`, `upCheck` («Перевірити оновлення»), `upChecking`, `upUpToDate(v)`, `upCheckFailed`, `upRestartManual`, `upNotesOffline`, `upErrRolledBack`. Тексти правил Windows: «Перезапустіть Deai Canvas вручну». Охоронці i18n зелені.
- [ ] **Step 4: смуга й палітра.** `bar-model.js`: у кінець `zone1` кожного з трьох повернень — `{ id: "update", tier: 0, labelTier: TIERS.mode, version: s.update.latest }` (лише коли `s.update?.available`); оновити `tests/bar-model.test.mjs:384, :392` (`length`, `deepEqual`) — звіт: «зміна: нові контроли в кінці zone1». `shell-bar.js`: `updateBtn(model)` — `<button class="ctl ctl--out upd-pill" data-act="update" title=…>${ico("down")}<span class="lbl-upd">…</span></button>`, виводиться **одразу після** `paletteBtn(model)` у `barHTML` (і на екранах «Задачі»). `shell-palette.js`: `appActions(s)` → `[{ id: "update-check", group: "gSet", labelKey: "upCheck", icon: "refresh", act: "updatecheck" }, …(s.update?.available ? [{ id: "update-notes", group: "gSet", labelKey: "upWhatsNew", icon: "info", act: "updatenotes" }] : [])]`; додати в обидва місця (Поправка 18). Тести: `shell-bar.test.mjs` (пігулка є лише при `available`; `data-act="update"` ↔ `id` моделі; порядок: після палітри, перед крошками), `shell-palette.test.mjs` (дії є в `homeOpen` і поза ним; `labelKey` у обох словниках).
- [ ] **Step 5: проводка `app.js`.** `let updateInfo = null` (модульна змінна); `async function pollUpdate()` — `GET /api/update` через `api()` (збій → `updateInfo = null` без шуму), на старті й кожні 30 хв (`setInterval`, поряд із `:5203`), `paintBar()` при зміні; `barState()` дає `update: updateInfo`; `paletteState()` теж. `BAR_ACTIONS.update`/`.updatenotes` → `openUpdateDialog()`; `.updatecheck` → `POST /api/update-check`, тост `upUpToDate`/`upCheckFailed`, оновлює `updateInfo`. `openUpdateDialog()`: `GET /api/update-notes` (не блокує відкриття: діалог малюється одразу з `sections: null`, перемальовується по відповіді) → `askForm(() => updateDialogHTML(...), { onSubmit })`; `onSubmit` → `POST /api/update-apply`; `202` → `aria-busy` + «Оновлюю…» і цикл `restartStep` кожні 1 с (`fetch('/api/update')` без `api()`-кидання), `done` → `location.reload()`; `fail`/помилка → рядок помилки в діалозі (`ctl.error`). Windows (`restart: 'manual'`) → повідомлення `upRestartManual`, без опиту.
- [ ] **Step 6: піни PWA/кешу** (Поправка 3): `tests/pwa.test.mjs` — `sw.js` не містить `caches.` і `CacheStorage`; `tests/test_pwa.py` — `GET /app/app.js` і `/app/update-model.js` повертають `Cache-Control: no-cache`.
- [ ] **Step 7: CSS** — `.upd-pill`, `.up`-діалог (за зразком `.pal-open`, `.tr`): лише наявні токени. Прогін `css-guards` і `test_css_tokens`.
- [ ] **Step 8: повний прогін** (JS + Python ×3). Живих у цій задачі нема (T10). **Мутації** M25…M30. **Коміт** `feat(0.23): оновлення — пігулка в смузі, діалог «Що нового», ⌘K, опит після рестарту` (усі файли задачі).

---

### Task 6: відгук — ядро: кільце помилок сервера, збирач діагностики, `POST /api/feedback-preview`

**Files:** Modify `app/feedback.py` (Create), `app/serve.py` (`_guarded` `:5611`; `_shot` `:6256`; `do_POST` гілка; імпорт), `tests/test_serve.py` (охоронець `:1415`); Create `tests/test_feedback_diag.py`.

- [ ] **Step 1: червоні тести** `tests/test_feedback_diag.py` (+ `spaces_guard`):
  ```python
  class ErrorRing(unittest.TestCase):
      def test_ring_keeps_last_50_newest_last(self): ...
      def test_entry_shape_route_type_message_redacted(self):
          feedback.record_error('/api/task?it=it1&secret=zzz', OSError('open %s/x failed' % os.path.expanduser('~')))
          e = feedback.server_errors()[-1]
          self.assertEqual((e['route'], e['type']), ('/api/task', 'OSError'))
          self.assertNotIn(os.path.expanduser('~'), e['msg']); self.assertLessEqual(len(e['msg']), 300)
      def test_route_never_carries_names(self):                 # `/it-assets/it1/секретна-назва/x.png` → `/it-assets`; `/t/<id>/api/x` → `/api/x`; `/api/a/b/c/d` → перші 3 сегменти
      def test_thread_safe(self): ...                            # 8 потоків × 100 записів, довжина ≤ 50, без винятків
      def test_disconnects_not_recorded(self):                   # через `_guarded`: BrokenPipeError не в кільці
      def test_guarded_records_unexpected_and_reraises(self):    # маршрут, що кидає RuntimeError → зʼєднання рветься, як раніше, і запис у кільці
      def test_expected_4xx_not_recorded(self): ...              # NoTask / AmbiguousTask
      def test_operational_failures_recorded_by_code_only(self): # SpacesError/SpaceUnavailable/ModuleError(status≥500): є `code`, нема str(e)
  class BuildDiag(unittest.TestCase):
      def test_fields_exactly(self):                              # ключі: version, os{system,release,python}, lang, space{kind,roles,migration}, task{id,iteration,page,screen}, errors{server,client}
      def test_no_task_title_no_paths_no_settings(self):
          # простір з назвою «Конфіденційно», задача з title «Секрет», модуль з settings{url,key}: серіалізована діагностика не містить жодного з цих рядків, ні шляху простору/тека задачі
      def test_roles_are_ids_only_and_own_modules_are_anonymised(self): ...
      def test_migration_names_whitelisted(self): ...            # лише ключі виду `liga-4d…`
      def test_client_errors_sanitised_and_capped(self):          # 100 елементів → 20; msg>300 → 300; file без `app/` → ''; не-словники відкинуто; ключі лише msg/file/line
      def test_size_cap_64k_drops_errors_first(self): ...
      def test_total_function_on_broken_registry_and_no_task(self): # SpacesError/UnknownTask → поля None, не виняток
      def test_secret_like_strings_in_errors_are_hidden(self): ...
  class ShotChoice(unittest.TestCase):
      def test_shot_file_double_lock(self): ...                   # `serve._shot_file(task, 'it1', '../x')` → None; симлінк назовні → None; відсутній → None
      def test_shot_over_2mb_is_skipped_not_truncated(self): ...
  ```
  HTTP: `POST /api/feedback-preview` (машинний маршрут, Origin-гейт — 403 чужий, 400 `bad-body` на `[]`), працює на порожній машині й при битому реєстрі; відповідь `{ok, diag, shot: {available, bytes?, skipped?}}`; вхідні `it`/`node` лише за `NAME_RE`/`SHOT_RE` (інакше `shot.available=false`, без помилки).
- [ ] **Step 2: код.** `app/feedback.py` (без імпорту `serve`; імпортує `redact`, `isolation`, `spaces`, `deai_modules`, `atomic_io`): `record_error(path, exc, code=None)`, `server_errors()`, `build_diag(ctx, client)` де `ctx` — **готовий** словник від `serve` (`{'space': sp|None, 'task_id', 'iteration', 'page', 'screen', 'lang'}`), щоб модуль не знав про `serve`; `sanitize_client_errors(raw)`. `serve.py`: `_guarded` — гілка `except Exception` після `deai_modules.ModuleError` з виключенням на `(BrokenPipeError, ConnectionResetError, ConnectionAbortedError)` (re-raise без запису) і `raise` для решти після `feedback.record_error`; у гілках `SpaceUnavailable`/`SpacesError`/`ModuleError(status>=500)` — `feedback.record_error(self.path, e, code=…)`; `_shot_file(task, it, node)` винесено з `_shot` (Поправка 5; `_shot` викликає її); `_feedback_context(payload)` — тотальний збирач контексту (Поправка 2); `_feedback_preview(payload)`; `elif self.path == '/api/feedback-preview'`. Охоронець `test_serve`: `assertIn('/api/feedback-preview', routes)`.
- [ ] **Step 3: повний прогін** + мутації M31…M38. **Коміт** `feat(0.23): відгук — кільце помилок, збирач діагностики з редагуванням, POST /api/feedback-preview` (`app/feedback.py`, `app/serve.py`, `tests/test_serve.py`, `tests/test_feedback_diag.py`).

---

### Task 7: відгук — надсилання: черга, ретраї, Supabase (insert + Storage), конфіг

**Files:** Modify `app/feedback.py`, `app/serve.py` (`do_POST` гілка `/api/feedback`; `serve_main`), `tests/test_serve.py`; Create `app/feedback.json`, `tests/test_feedback_outbox.py`, `tests/test_feedback_api.py`.

`app/feedback.json` — рівно `{"url": "", "key": ""}`.

- [ ] **Step 1: червоні тести** `tests/test_feedback_outbox.py` (HTTP-приймач — `http.server` на `127.0.0.1:0` у потоці тесту; нічого поза loopback):
  ```python
  class Config(unittest.TestCase):
      def test_precedence_env_over_home_config_over_app_file(self): ...
      def test_empty_config_means_local_queue_only(self): ...         # (None) → send повертає 'queued', мережі не було
      def test_only_https_or_isolated_loopback(self):                  # `http://example.com` → None; `http://127.0.0.1:1` лише при isolated(); `javascript:`/`file://` → None
      def test_unreadable_or_invalid_home_config_ignored(self): ...    # битий JSON, не словник, `feedback` не словник
      def test_shipped_feedback_json_is_safe(self):                    # app/feedback.json: ключі лише url/key; url порожній АБО https://<хост>.supabase.co(/); key порожній АБО `sb_publishable_…` чи JWT з role=anon; `sb_secret_`/role=service_role → ПАДАЄ
          ...
  class Outbox(unittest.TestCase):
      def test_record_is_written_before_any_network(self):             # приймач недоступний → файл `outbox/<id>.json` 0600, тека 0700, поля id/created_at/kind/text/contact/version/os/diag/shot_path/attempts
      def test_offline_then_sent_moves_to_sent(self): ...              # 1-й виклик: приймач віддає 503 → 'queued'; 2-й (flush) → 'sent', файл у sent/
      def test_duplicate_409_counts_as_sent(self): ...                 # PostgREST 409 23505 → sent
      def test_request_shape(self):                                    # POST /rest/v1/feedback; заголовки apikey, Authorization Bearer <key>, Content-Type, Prefer: return=minimal; тіло — рівно колонки з права insert (БЕЗ created_at); id — uuid4; ключ НЕ в тілі й не в логах
      def test_shot_goes_first_to_storage_then_row_has_shot_path(self): # POST /storage/v1/object/feedback-shots/<id>.webp, Content-Type image/webp, x-upsert: false; shot_path у рядку
      def test_shot_409_is_ok_shot_4xx_drops_shot_but_sends_row(self): ...
      def test_shot_over_2mb_never_sent(self): ...
      def test_old_or_20_attempts_go_to_failed_not_deleted(self): ...  # 31 день / 20 спроб → failed/, файл ЦІЛИЙ
      def test_validation(self):                                       # kind ∉ {bug,idea}; text <10 або >10000; contact >200; include_* не bool; тіло >256 КБ → 413/400 коди; жодного запису в outbox
      def test_concurrent_flush_sends_each_once(self): ...             # 2 потоки → приймач отримав рядок 1 раз
      def test_no_writes_in_real_home_when_isolated(self): ...         # isolated()+real_home → черга в памʼяті, файлів нема
      def test_network_refused_for_non_loopback_when_isolated(self):   # url https://sb.example.com + isolated() → opener НЕ викликано, 'queued'
      def test_key_and_url_never_in_exception_text_or_state(self): ...
  ```
  `tests/test_feedback_api.py`: `POST /api/feedback` → `{ok, id, state, number}` (`number == id[:8]`); чужий Origin 403; `[]` → 400 `bad-body`; працює на порожній машині; з приймачем-фейком у потоці → рядок отримано з діагностикою (редагованою, без назви задачі); `include_diag: false` → у рядку `diag` порожній обʼєкт `{}`; `include_shot: true` без кадру → відправка без скриншота (`shot_path` null), не помилка; відправка не повертає `ok:false` через мережу — лише `queued`. Охоронець `test_serve`: `assertIn('/api/feedback', routes)`.
- [ ] **Step 2: код** (`app/feedback.py`): `config(env, home)`, `net_allowed(url)`, `class Outbox(home_fn)` (`add`, `pending`, `mark_sent/failed`, `flush(sender)` під `threading.Lock`), `class SupabaseSender(url, key, opener=urllib.request.urlopen)` (єдине місце з `apikey`/`Authorization`; тайм-аут 10 с; відповідь ≤ 64 КБ; збій → `Transient`/`Permanent` без значень ключа/URL у тексті), `submit(request, ctx, shot_bytes)` → `{id, state}`. `serve._feedback(payload)`: Origin уже перевірено; валідація; `shot` — через `_shot_file` за `payload.get('shot')` `{task, it, node}`; після `submit` — best-effort `flush` решти черги (так «офлайн → надіслано» доводиться без додаткового маршруту). `serve_main`: `feedback.start_background(...)` — перше спорожнення через 10 с і далі щогодини; не стартує, коли конфігу нема.
- [ ] **Step 3: повний прогін** + мутації M39…M50. **Коміт** `feat(0.23): відгук — черга, ретраї, надсилання в Supabase (insert + Storage), POST /api/feedback` (`app/feedback.py`, `app/feedback.json`, `app/serve.py`, `tests/test_serve.py`, `tests/test_feedback_outbox.py`, `tests/test_feedback_api.py`).

---

### Task 8: відгук — інтерфейс (кнопка, ⌘K, діалог, кільце помилок клієнта)

**Files:** Create `app/err-ring.js`, `app/feedback-model.js`, `app/feedback-view.js`, `tests/err-ring.test.mjs`, `tests/feedback-model.test.mjs`; Modify `app/bar-model.js`, `app/shell-bar.js`, `app/shell-palette.js` (`appActions`), `app/i18n.js`, `app/app.js` (ПЕРШИЙ імпорт `./err-ring.js`; `BAR_ACTIONS.feedback` `:1742`), `app/styles.css`, `tests/bar-model.test.mjs`, `tests/shell-bar.test.mjs`, `tests/shell-palette.test.mjs`.

- [ ] **Step 1: червоні JS-тести.** `err-ring.test.mjs`: `normalize({type:'error', message, filename, lineno})` → `{msg, file, line}`, де `file` — частина від `/app/` включно (`http://localhost:8765/app/app.js` → `app/app.js`), решта URL → `''`; `unhandledrejection` → `msg` з `reason.message`/рядка; кільце ≤ 20 (найновіші), `msg` ≤ 300; `init(win)` ставить рівно два слухачі й повертає `list()` — копію; повторний `init` не дублює; `push` не кидає на вхід-сміття. `feedback-model.test.mjs`: `validate({kind,text,contact})` → ключ помилки (`fbErrShort` при trim < 10, `fbErrLong` > 10000, `fbErrContact` > 200, `fbErrKind`), `null` — ок; `buildRequest(state)` → тіло POST (`kind,text,contact,include_diag,include_shot,client_errors,task,it,node,screen,lang`; `include_shot` лише коли є кадр); `outcome({state:'sent', number})` → `{key:'fbSent', args:[n]}`, `queued` → `fbQueued`; `previewText(diag)` — стабільний `JSON.stringify(…, null, 2)`. Розмітка (`feedback-view.js`): `form[data-form="feedback"]`, перемикач `input[type=radio][name=kind]` (bug/idea; `bug` вибраний), `textarea#fb-text[name=text][required][aria-describedby=cv-form-err]`, `input#fb-contact`, чекбокси `#fb-diag` (checked) і `#fb-shot` (disabled з причиною, коли кадру нема), `<details data-fb-preview><pre>` з JSON, слот помилки `[data-form-error]`, кнопки `data-a=cancel`/`data-a=ok`; усе з даних — через `esc`.
- [ ] **Step 2: код** моделей/вигляду; `err-ring.js` (`initErrRing(win = window)`; підключається **першим** імпортом у `app.js`, щоб ловити й помилки завантаження наступних модулів); `bar-model.js`: у кінець `zone1` у всіх трьох поверненнях — `{ id: "feedback", tier: 0 }` (**без** `labelTier`: лише іконка — так не множимо яруси; `tests/bar-model.test.mjs` оновити, звіт); `shell-bar.js`: `feedbackBtn(model)` одразу після палітри (перед пігулкою оновлення): `<button class="ctl ctl--icon fb-btn" data-act="feedback" title aria-label>${ico("comment")}</button>`; `shell-palette.js::appActions` — `{ id: "feedback", group: "gSet", labelKey: "fbOpen", icon: "comment", act: "feedback" }` (також у `homeOpen`-поверненні).
- [ ] **Step 3: i18n (префікс `fb`).** `fbOpen`, `fbTitle`, `fbKindBug`, `fbKindIdea`, `fbText`, `fbTextPh`, `fbContact`, `fbContactPh`, `fbDiag`, `fbShot`, `fbShotNone`, `fbWhat`, `fbWhatHint`, `fbSend`, `fbErrShort(n)`, `fbErrLong`, `fbErrContact`, `fbErrKind`, `fbErrGeneric(msg)`, `fbSent(n)` («Дякуємо! №{n}»), `fbQueued(n)` («Збережено — надішлемо, щойно буде мережа (№{n})»). Обидві мови; охоронці i18n зелені.
- [ ] **Step 4: проводка `app.js`.** `BAR_ACTIONS.feedback = openFeedback`; `openFeedback()`: збирає контекст (`curTask?.id`, `picked`, `pickedPage`, екран: `homeOpen ? homePage || 'tasks' : (mode)`; кадр — `shotManifest.shots?.[frameKey(pickedPage, canvasW)]` → `{it: picked, node}` або `null`), `POST /api/feedback-preview` (збій → діалог працює без «Що буде надіслано», з рядком про це), `askForm(…)`; `onSubmit` → валідація моделлю (`ctl.focus('text')` + повернення тексту) → `POST /api/feedback` → `toast(t(outcome.key, …))`. Помилка мережі до самого сервера (`api()` кинув) → `ctl.error(t('fbErrGeneric', …))`, форма лишається. Діалог доступний на всіх екранах (Поправка 17) і не залежить від задачі.
- [ ] **Step 5: CSS** `.fb`, `.fb-btn`; лише наявні токени.
- [ ] **Step 6: повний прогін** (JS + Python ×3) + **мутації** M51…M58. **Коміт** `feat(0.23): відгук — кнопка «Відгук» і ⌘K «Баг / ідея», діалог, кільце помилок клієнта` (усі файли задачі).

---

### Task 9: `ops/feedback-collector.sql` — приймач (таблиця, RLS лише insert, бакет, тригер → pg_net → Teams)

**Files:** Create `ops/feedback-collector.sql`, `tests/test_feedback_sql.py`.

Скрипт ідемпотентний, **без секретів і без адрес**; англійською, у стилі `app/modules/supabase-teams/schema.sql` (шапка з попередженнями: «ВИКОРИСТОВУЙТЕ ОКРЕМИЙ ПРОЄКТ Supabase Deai», «publishable-ключ — лише insert»; секрет вебхука Teams — у Vault: `select vault.create_secret('<webhook address>', 'teams_feedback_webhook_url');`).

- [ ] **Step 1: червоний тест** `tests/test_feedback_sql.py` (текстовий розбір файла, без БД):
  - `create table if not exists public.feedback` із колонками `id uuid primary key`, `created_at timestamptz not null default now()`, `kind text not null check (kind in ('bug','idea'))`, `text … check (char_length(text) between 10 and 10000)`, `contact … check (contact is null or char_length(contact) <= 200)`, `version`, `os`, `diag jsonb … check (octet_length(diag::text) <= 65536)`, `shot_path … check (shot_path is null or shot_path ~ '^[0-9a-f-]{36}\.(webp|png)$')`;
  - `alter table public.feedback enable row level security`;
  - **рівно одна** політика на `public.feedback`: `for insert to anon` (з `with check (true)` або перевірками); **жодної** `for select|update|delete|all` для `anon`, `authenticated`, `public` — регекс по всіх `create policy` у файлі: кожна, що стосується `public.feedback` чи `storage.objects`, має `for insert` і лише `to anon`;
  - `revoke all on public.feedback from anon, authenticated, public` **до** `grant insert (id, kind, text, contact, version, os, diag, shot_path) on public.feedback to anon` (колонковий; `created_at` у списку нема); немає `grant select|update|delete`; немає `grant … to authenticated`;
  - бакет: `insert into storage.buckets … 'feedback-shots' … public => false`, `file_size_limit = 2097152`, `allowed_mime_types` лише `image/webp`, `image/png`; політика `on storage.objects for insert to anon with check (bucket_id = 'feedback-shots' and name ~ …)`; немає політик select/update/delete на `storage.objects` для anon;
  - тригер `after insert on public.feedback` → функція `security definer` із `set search_path = pg_catalog, public, vault, net`, секрет читає з `vault.decrypted_secrets where name = 'teams_feedback_webhook_url'`, відмовляє, коли URL не `https://`, картка будується лише `jsonb_build_object`/`jsonb_build_array` (без конкатенації полів відгуку — єдина дозволена `||` — обрізання тексту до 500), `exception when others then raise warning '… sqlstate %', sqlstate; return new;` (відгук ніколи не падає через Teams);
  - **немає секретів:** жодного `eyJ`, `sb_secret_`, `sb_publishable_`, `service_role` як значення, жодного `https://` з реальним хостом (дозволено лише `https://` у регексі перевірки схеми) і жодного вебхука.
- [ ] **Step 2: файл** `ops/feedback-collector.sql` за переліком вище (+ `revoke all on function … from public, anon, authenticated` для функції тригера).
- [ ] **Step 3: повний прогін** + **мутації** M59…M63 (доданий `create policy … for select to anon`; `grant select … to anon`; прибраний `enable row level security`; `public => true` у бакеті; літерал `sb_secret_` у файлі → кожна червоніє). **Коміт** `feat(0.23): ops/feedback-collector.sql — приймач відгуків (RLS лише insert, бакет, Teams через pg_net)` (`ops/feedback-collector.sql`, `tests/test_feedback_sql.py`).

---

### Task 10: живі тести — пігулка/діалог оновлення, apply у викидному клоні, діалог відгуку з фейковим приймачем

**Files:** Create `tests/live/update.test.mjs`, `tests/live/update-apply.test.mjs`, `tests/live/feedback.test.mjs`, `tests/live/_fake-feedback.mjs`; Modify `tests/live/fixture.mjs` (лише якщо потрібна опція, див. Step 2).

Усі три — **по одному файлу, послідовно**; порти — з діапазонів інших живих тестів, не 8765/4317.

- [ ] **Step 1: `tests/live/update.test.mjs`** (сервер із `spaces`, `startServer(…, { spaces: [...] })`; `update.json` пишеться тестом у повернений `deaiHome` ПІСЛЯ старту — `GET /api/update` читає файл щоразу):
  - без файла — пігулки в DOM нема; запис `{checked_at, latest: "99.0.0", state: "ok", reason: ""}` + перезавантаження сторінки → пігулка «Оновлення 99.0.0» є на екрані задачі, на «Задачах» і на «Підключеннях» (Поправка 17);
  - клік → діалог: «Встановлено <поточна> → доступно 99.0.0»; кнопка `[data-a=ok]` **вимкнена** з видимою причиною (сервер ізольований без шва → `blocked: 'isolated'`) — реального `apply` не буває; блок команди для `dirty` перевіряється **юніт-тестом** (T5), тут — лише що причина видима й текст не порожній;
  - ⌘K → «Перевірити оновлення» → тост (`DEAI_NO_UPDATE_CHECK=1`: `state: 'disabled'` → діалог/тост без помилки);
  - `state: "offline"` у файлі → пігулки нема; жодного запиту поза `127.0.0.1` (`page.on('request')` збирає хости).
- [ ] **Step 2: `tests/live/update-apply.test.mjs`** — єдиний тест, що доводить «apply → рестарт → перезавантаження» (R-F; викидний клон, справжній репо — лише джерело клону для читання):
  1. `tmp/` : `git init --bare remote.git`; `git clone --no-hardlinks <ROOT> work` (локальний клон, мережі нема); у `work` — `git remote set-url origin <tmp>/remote.git`, `git push origin HEAD:refs/heads/main`, тег `v<поточна>` (якщо нема), далі **в `work`** коміт-крок: `package.json` → `"version": "99.0.0"` + розділ `## [99.0.0] — 11.11.2026` у `CHANGELOG.md`, `git tag v99.0.0`, `git push origin main v99.0.0`, **потім** `git reset --hard HEAD~1` **у `work`** (викидний клон; тег лишився у remote) — тепер `work` на 1 коміт позаду;
  2. `startServer(taskDir, { root: <tmp>/work, env: { DEAI_UPDATE_REMOTE: <tmp>/remote.git, DEAI_UPDATE_TEST_APPLY: "1", DEAI_NO_UPDATE_CHECK: "1" }, spaces: [...] })` — сервер із коду `work`;
  3. `POST /api/update-check` (fetch із Node) → `available: true`; сторінка → пігулка → діалог із блоком «Що нового» (текст розділу 99.0.0); клік «Оновити й перезапустити» → «Оновлюю…» → сторінка сама перезавантажилась; `GET /api/update` → `current: "99.0.0"`, `boot` інший, ніж до кліку; **PID дочірнього процесу той самий** (`child.pid` живий; `process.kill(pid, 0)`);
  4. друга перевірка: `POST /api/update-apply` вдруге → `409 nothing-to-update`;
  5. у `finally`: `child.kill()` **за PID**, `rmSync(tmp)`; перевірка, що `git -C <ROOT> rev-parse HEAD` до/після однаковий і `git -C <ROOT> status --porcelain --untracked-files=no` не змінився.
- [ ] **Step 3: `tests/live/_fake-feedback.mjs`** — `http.createServer` на `127.0.0.1:0`: `POST /rest/v1/feedback` (перевіряє `apikey`/`Authorization`/`Prefer`, зберігає рядки; дубль `id` → 409), `POST /storage/v1/object/feedback-shots/<name>` (зберігає байти; 409 на дубль), режими `up`/`down` (503), `rows()`, `shots()`, `close()`.
- [ ] **Step 4: `tests/live/feedback.test.mjs`** (сервер із `spaces`, `env: { DEAI_FEEDBACK_URL: "http://127.0.0.1:<порт>", DEAI_FEEDBACK_KEY: "sb_publishable_test", DEAI_NO_UPDATE_CHECK: "1" }`; Playwright):
  - кнопка «Відгук» є на екрані задачі, на «Задачах», на «Підключеннях», у майстрі; ⌘K → «Баг / ідея» відкриває той самий діалог;
  - валідація: пусто/<10 знаків → помилка під полем, фокус у полі, нічого не надіслано;
  - приймач у режимі `down`: ввести текст → «Збережено — надішлемо… (№…)», у `<DEAI_HOME>/feedback/outbox/` один файл 0600; приймач `up` + другий відгук → обидва надійшли (`rows().length === 2`), `outbox/` порожній, `sent/` — два файли;
  - що надійшло: `diag` має `version`, `space.roles`, `task.id`, **не** містить назви задачі й домашнього шляху (`assertNotMatch`); «Що буде надіслано» показує той самий JSON; знята галочка «Додати діагностику» → `diag: {}`;
  - `include_shot`: фікстура кладе `shots/<node>.webp` у ітерацію (мінімальний валідний `RIFF…WEBP`-буфер) + `manifest.json`; у рядку `shot_path`, у Storage-фейку байти збігаються; без кадру чекбокс вимкнений з причиною;
  - помилка клієнта в кільці: `page.evaluate(() => setTimeout(() => { throw new Error('boom') }))` → у попередньому перегляді `errors.client[0].msg === 'boom'`;
  - запити сторінки — лише на `127.0.0.1`.
- [ ] **Step 5: повний набір живих задачі, по одному**: `update`, `update-apply`, `feedback`, а також регресійно `shell-bar`, `shell-palette`, `shell`, `pwa`, `tasks-home`, `connections`, `spaces` (смуга й палітра змінились у T5/T8). Падіння, не повʼязані з кодом (браузер, `HOME`), — окремо у звіті. `ls ~/.deai ~/deai-published` не змінились; `git -C <repo> status --porcelain --untracked-files=no` порожній, `git -C <repo> log -1 --format=%H` той самий.
- [ ] **Step 6: коміт** `test(0.23): живі — пігулка й діалог оновлення, apply у викидному клоні, діалог відгуку з фейковим приймачем` (`tests/live/update.test.mjs`, `tests/live/update-apply.test.mjs`, `tests/live/feedback.test.mjs`, `tests/live/_fake-feedback.mjs`, за потреби `tests/live/fixture.mjs`).

---

### Task 11: документи, версія 0.23.0

**Files:** Modify `package.json`, `CHANGELOG.md`, `README.md`.

- [ ] **Step 1: `package.json`** `"version": "0.23.0"`.
- [ ] **Step 2: `CHANGELOG.md`** — розділ `## [0.23.0] — <дата DD.MM.YYYY>` англійською, у стилі попередніх: абзац-підсумок («feedback + updates»); **Added** (`updater`, `feedback`, `redact`, маршрути `GET /api/update`, `GET /api/update-notes`, `POST /api/update-check|update-apply|feedback-preview|feedback`, пігулка й діалог оновлення, кнопка «Відгук», `ops/feedback-collector.sql`, `app/feedback.json`, `<DEAI_HOME>/update.json`, `<DEAI_HOME>/feedback/{outbox,sent,failed}`, змінні `DEAI_NO_UPDATE_CHECK`, `DEAI_UPDATE_REMOTE`, `DEAI_FEEDBACK_URL`, `DEAI_FEEDBACK_KEY`, шов `DEAI_UPDATE_TEST_APPLY` лише для тестів, охоронці `NoNetwork`/`FeedbackSqlInsertOnly`/`FeedbackJsonSafe`); **Changed** (`zone1` смуги; `_guarded` пише кільце помилок; `isolation.writes_allowed`; Поправки до спеки одним рядком: пласкі маршрути, webp, `boot`, `disabled`); «Differences for a person»; «Rolling back 0.23 → 0.22» (`git checkout v0.22.0` + перезапуск; 0.22 ігнорує `update.json` і `feedback/`); «Left for 1.0 / next» (rate-limit у приймачі, адмінка читання відгуків, Windows-перезапуск, персистентне кільце помилок); «What the owner does» (3 кроки зі спеки). Рядки «Design: `docs/superpowers/specs/2026-11-11-feedback-and-updates-design.md`; plan: `docs/superpowers/plans/2026-11-11-feedback-and-updates.md`».
- [ ] **Step 3: `README.md`:** таблиця Module API — шість нових рядків (форми відповідей, коди відмов `409 not-git|dirty|detached|worktree|busy|diverged|tag-conflict|nothing-to-update|isolated`, `503 offline`, `500 rolled-back|merge-failed`); новий розділ «Feedback and updates» (що збирається, що редагується, де лежить черга, як вимкнути перевірку оновлень, як налаштувати свій приймач `DEAI_FEEDBACK_URL/KEY` або `<DEAI_HOME>/config.json`); дорожня карта — рядок про 0.23.
- [ ] **Step 4: перевірки.** `grep -rn "/Users/" app ops CHANGELOG.md README.md` порожньо (сам цей план з перевірки виключено); так само перевірка на імʼя користувача машини (`$(id -un)`) у тих самих файлах; повний пакет (Python ×3 + JS) і живі з T10 зелені; `git status --short` лише заплановане.
- [ ] **Step 5: коміт** `docs(0.23): CHANGELOG 0.23.0, README, версія` (три файли; не пушити, не тегувати — це робить контролер).

---

## Таблиця мутацій (кожна має червоніти; `python3 -B`, по одній, файл відновлюється, `sha256` до/після збігається)

| # | Мутація | Червоніє |
|---|---|---|
| M1 | `redact.text` без кроку ключоподібних рядків | `test_key_like_strings` |
| M2 | `redact.text` без заміни домашнього шляху | `test_home_becomes_tilde_both_forms` |
| M3 | загальний регекс без вимоги «цифра і літера» | `test_innocent_long_words_and_paths_survive` |
| M4 | e-mail замінюється ДО userinfo | `test_order_secret_before_email…` |
| M5 | `isolation.writes_allowed`: `or` замість `and` | `test_isolation` (writes_allowed) |
| M6 | `TAG_RE` без якорів `^…$` | `test_tag_regex_blocks_option_injection` |
| M7 | `latest_tag` порівнює рядки, не числа | `test_semver_tags_only` |
| M8 | `check_remote` пропускає `-oProxyCommand=…`/`ext::` | `test_bad_remote_is_refused_before_any_git_call` |
| M9 | `remote_host` повертає весь URL (userinfo) | `test_remote_host_only_never_userinfo` |
| M10 | `network_allowed` → завжди `True` | `test_network_remote_refused_when_isolated_or_disabled` |
| M11 | `_save` пише без `writes_allowed` | `test_no_state_file_in_real_home_when_isolated` |
| M12 | `blocked` рахується й коли `available == False` | `test_blocked_not_computed_when_nothing_to_update` |
| M13 | з `run_git` прибрано `GIT_OPTIONAL_LOCKS` | `test_status_uses_optional_locks_off`; прибрано `DEAI_NO_UPDATE_CHECK` із `fixture.mjs` → `test_no_network` |
| M14 | `apply` без перевірки `dirty` | `test_dirty_blocks_and_changes_nothing` |
| M15 | `apply` бере версію з тіла запиту | `test_target_comes_from_state_not_request` |
| M16 | `diverged`: `merge` замість `--ff-only` | `test_diverged_local_commit` |
| M17 | смоук пропущено (`return True`) | `test_smoke_failure_rolls_back_to_old_head`, `…_import_error_…` |
| M18 | `reset --hard` не до `old`, а до `HEAD~1` | `test_rollback_resets_only_to_the_recorded_head` |
| M19 | відкат виконується й коли `merge` не вдався | `test_offline_fetch_fails_changes_nothing`, `test_tag_conflict` |
| M20 | `exec_restart` без перевірки ізоляції/шва | `test_exec_restart_refused_when_isolated_without_the_seam` |
| M21 | `isolated`-гейт `apply` прибрано | `test_isolated_process_refuses_apply_on_product_root_without_the_seam` |
| M22 | смоук викликає `py_compile` | `test_no_pyc_written_by_the_smoke` |
| M23 | `parse_changelog`: `after` включно | `test_sections_between_current_exclusive_and_latest_inclusive` |
| M24 | `notes` не кешує / не відсікає > 1 МБ | кеш-тест / тест ліміту |
| M25 | `restartStep`: `done` лише за `current` (без `boot`) | `restartStep` (старий процес з новою версією на диску) |
| M26 | `pillModel` показує при `offline` | `пігулка лише коли available` |
| M27 | `notesToBlocks` віддає HTML без `esc` | перевірка `<script>` у `update-model.test.mjs` |
| M28 | `bar-model`: `update` з'являється без `available` | `shell-bar`/`bar-model` тести |
| M29 | `appActions` не додано в `homeOpen`-повернення | `shell-palette.test.mjs` |
| M30 | у `sw.js` додано `caches.open` | `pwa.test.mjs` пін |
| M31 | `record_error` не обрізає `route` до сегментів | `test_route_never_carries_names` |
| M32 | `_guarded`: без `raise` після запису | `test_guarded_records_unexpected_and_reraises` |
| M33 | `_guarded` пише `BrokenPipeError` | `test_disconnects_not_recorded` |
| M34 | `build_diag` додає `task.title` | `test_no_task_title_no_paths_no_settings` |
| M35 | `sanitize_client_errors` без ліміту 20 / 300 | `test_client_errors_sanitised_and_capped` |
| M36 | кап 64 КБ прибрано | `test_size_cap_64k_drops_errors_first` |
| M37 | `_shot_file` без `realpath`-замка | `test_shot_file_double_lock` |
| M38 | кадр > 2 МБ обрізається, а не пропускається | `test_shot_over_2mb_is_skipped_not_truncated` |
| M39 | `config`: `http://` приймається поза ізоляцією | `test_only_https_or_isolated_loopback` |
| M40 | пріоритет конфігу: `app/feedback.json` вище env | `test_precedence_env_over_home_config_over_app_file` |
| M41 | `Outbox.add` після мережевого виклику | `test_record_is_written_before_any_network` |
| M42 | `409` не вважається «надіслано» | `test_duplicate_409_counts_as_sent` |
| M43 | у тіло додано `created_at` | `test_request_shape` |
| M44 | `Prefer: return=representation` | `test_request_shape` |
| M45 | ключ потрапляє в текст винятку | `test_key_and_url_never_in_exception_text_or_state` |
| M46 | `failed/` → файл видаляється | `test_old_or_20_attempts_go_to_failed_not_deleted` |
| M47 | `flush` без замка | `test_concurrent_flush_sends_each_once` |
| M48 | відправка не-loopback при `isolated()` | `test_network_refused_for_non_loopback_when_isolated` |
| M49 | `app/feedback.json` із `sb_secret_…` | `test_shipped_feedback_json_is_safe` |
| M50 | валідація `text` без нижньої межі | `test_validation` |
| M51 | `err-ring` без ліміту 20 | `err-ring.test.mjs` |
| M52 | `normalize` лишає повний URL у `file` | `err-ring.test.mjs` |
| M53 | `validate` приймає 9 знаків | `feedback-model.test.mjs` |
| M54 | `buildRequest`: `include_shot: true` без кадру | `feedback-model.test.mjs` |
| M55 | `feedback-view`: текст без `esc` | перевірка розмітки |
| M56 | `err-ring.js` не першим імпортом `app.js` | пін-тест порядку імпортів (T8) |
| M57 | `bar-model`: `feedback` лише на екрані задачі | `bar-model.test.mjs` (екрани «Задачі»/«Підключення»/майстер) |
| M58 | `appActions`: `feedback` без `homeOpen`-гілки | `shell-palette.test.mjs` |
| M59 | у SQL додано `create policy … for select to anon` | `test_feedback_sql.py` |
| M60 | у SQL `grant select … to anon` | `test_feedback_sql.py` |
| M61 | у SQL прибрано `enable row level security` | `test_feedback_sql.py` |
| M62 | бакет `public => true` / без `file_size_limit` | `test_feedback_sql.py` |
| M63 | літерал `sb_secret_` у SQL | `test_feedback_sql.py` |

## Після всіх задач (контролер)

- Повний пакет Python ×3 + JS + живі з T10 зелені; `git log --oneline` — 11 комітів, кожен із зеленим деревом; ніщо з `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `2026-11-09-agents-sdk-policy-addendum.md` не застейджено; `git status --short` у `<repo>` — лише те, що було до початку (ніяких `reset`/`merge`/`checkout` у цьому репо); живий канвас на :8765 не перезапускався.
- Контролер вирішує: R-A…R-H (див. «Рішення контролера»), тег `v0.23.0`, пуш у `origin` і (для ЛІГИ) дзеркалення тегів на корпоративний GitLab.
- **Власник (пізніше, окремо від релізу):** (1) створити Supabase-проєкт «deai», виконати `ops/feedback-collector.sql`, покласти URL вебхука Teams у Vault (`teams_feedback_webhook_url`); (2) передати адресу проєкту й **publishable**-ключ — їх вписують в `app/feedback.json` окремим комітом (до цього відгуки лягають у локальну чергу `<DEAI_HOME>/feedback/outbox/`); (3) налаштувати дзеркало GitLab на отримання тегів із GitHub. Перший реальний `apply` на справжній установці — вручну, на копії, а не на живому :8765.
