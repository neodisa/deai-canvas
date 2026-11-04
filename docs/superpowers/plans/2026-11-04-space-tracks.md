# Етап 4d-1 «Напрямки простору замість профілю» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** загальний механізм «напрямків» простору (`tracks` у `space.json`: тека, репо, ДС, назва) і ключ задачі `track`
замість профілю ЛІГИ; ЛІГА — через неявний адаптер із кореня `tasks.json`, без жодної зміни для дизайнерів; `profile` —
синонім до 4d-4. Реліз 0.15.0.

**Architecture:** нове чисте ядро `app/tracks.py` (без імпорту `serve`, без мережі): нормалізація напрямків, адаптер ЛІГИ
`legacy_tracks(cfg)`, читання напрямку задачі й похідної мітки. `serve.py`: `space_tracks(sp)` і `track_root(...)` замість
`work_root(cfg, profile)` / `profile_repos()`; `task_tags`, `inspector_ds_arg`, `task_new`, маршрут `task-new`,
`/api/tasks`, `/api/task`, опис простору — через напрямки. `bin/registry.py`, `bin/roots.py`, `bin/state.py` — через `tracks`.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-04-space-tracks-design.md`. Читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  Рядок `Co-Authored-By` — рівно такий (Opus 5.5). Коміт — лише з переліком шляхів; новий файл спершу `git add -- <шлях>`.
- **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md`.

**Прогони й середовище**

- Кожен прогін — через охоронця памʼяті `python3 "$G" <секунд> <МБ> <команда…>` (шлях `$G` дає контролер).
- Не виставляти `DEAI_HOME`; не чіпати порти 8765/4317, справжні `~/.deai`, `~/deai-published`, `~/.gitconfig`, `tasks.json`
  дизайнера, `~/.claude/pipeline-feedback/`. Процеси — лише за PID. Фонові прогони — дочекатися й зупинити до звіту.
- **Жодної мережі в тестах.** Репо/дзеркала — лише локальні фікстури й фейкові модулі. Ізоляцію `DC_TASKS_FILE`/`DC_NO_OVERVIEW`
  не послаблювати.
- Знеособлено: лише вигадані значення (репо `git@example.com:studio/web.git`, `ssh://git@example.com/o/r.git`, теки в
  тимчасових каталогах, дизайнер Alpha / `alpha@example.com`). Жодних справжніх хостів, репо, ключів Jira, імен.

**Конвенції коду**

- Коментарі українською, у стилі навколишнього коду; ⛔-уроки прибраного коду переносяться в нове місце, не губляться.
- Тексти інтерфейсу лише через `t()` з UK і EN (`app/i18n.js`); дані в розмітку — лише через `esc()`.
- Python 3.9: без `match`, без `X | Y` в анотаціях.

**Еталони й мутації**

- `tests/legacy-golden.test.mjs` і `GoldenPinTest` — зелені БЕЗ `UPDATE_*`.
- Кожна нова перевірка доводиться мутацією (один рядок → потрібний тест червоніє → файл відновлено побайтно, sha256).
  Мутації Python — лише `python3 -B`, з охоронцем, по одній.

**Набори тестів:** юніти — `npm test`; живі — лише послідовно `node --test --test-concurrency=1 tests/live/<файл>`.
Номери рядків — орієнтир («≈»). Кожна зміна наявного тесту — у звіті одним рядком із причиною.

---

## Структура файлів

| Файл | Що змінюється |
|---|---|
| `tests/make_before_4d1.py`, `tests/fixtures/tracks/before-4d1.json` (нові) | знімок 0.14.0 (Task 1) |
| `app/tracks.py` (новий) | `ID_RE`, `MAX_TRACKS`, `normalize`, `default_id`, `of_task`, `find`, `label_tag`, `legacy_tracks`, `_LEGACY_LABELS` |
| `app/serve.py` | `space_tracks`, `track_root`; `task_tags`, `inspector_ds_arg`, `task_new`, `_task_new_write`; маршрут `task-new`; `_task_rows`, `/api/task`, `spaces_listing`; геть `_LEGACY_PROFILE_TAGS`, `_PROFILE_KEY`, `work_root`, `profile_repos` (або тонкі обгортки — з причиною) |
| `bin/registry.py`, `bin/roots.py`, `bin/state.py` | `track` у `SHARED`; теки й підписи через `tracks` |
| `tests/test_tracks.py` (новий) | знімок, ядро, диференційні, API |
| `tests/live/tracks.test.mjs` (новий) | живий |
| `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `package.json` | Task 7 |

---

### Task 1: знімок 0.14.0 (до змін коду)

**Files:** Create `tests/make_before_4d1.py` (зразок — `tests/make_before_4c3.py`: рецепт замороженої копії `git archive
c8c3a8b | tar -x -C <тека>` у докстрінгу; охорона fail-closed — відмова писати типовий шлях, коли `app/`/`bin/` відрізняються від
`c8c3a8b`, включно з невідстежуваними файлами й помилками git), `tests/fixtures/tracks/before-4d1.json`; тест-читач
`tests/test_tracks.py` (клас `Before4d1Shape`: ключі, типи, кількість сценаріїв).

- [ ] **Step 1:** генератор на HEAD без змін коду, усе в тимчасових теках, шлях `HOME` підмінено:
  - `roots`: `serve.work_root(cfg, p)` для конфігів {з `design_work_roots` (united + seo) і `design_work_root`; лише
    `design_work_root`; нічого} × профілі {`united`, `liga360`, `seo`, `zzz`, `None`} — шлях **відносно** тимчасового HOME
    (`~/…`), щоб знімок не залежав від машини;
  - `repos`: `serve.profile_repos()` для `tasks.json` з добрими й поганими парами (`'United'` — поганий ключ, `'-x'` — погане
    репо, не рядок, не словник, нема ключа);
  - `tags`: `serve.task_tags(t)` для задач {без `tags` з кожним профілем, невідомим, з комою, на 40 знаків, не рядком; з
    `tags: []`; з `tags: ['A']`};
  - `ds`: `serve.inspector_ds_arg(p, None)` для профілів {`united`, `seo`, `zzz`, `Bad!`, `''`, `None`};
  - `task_new`: `serve.task_new(cfg, 't1', profile=p)` у тимчасовій теці для профілів {`united`, `liga360`, `seo`, `zzz`, `None`}
    з `profile_repos` = {`united`: `ssh://git@example.com/o/r.git`} і ВИМКНЕНИМ постачальником `vcs` (підмінити
    `serve.vcs_provider` → `None`): запис задачі (`dir` відносно HOME, `profile`, `gitlab`, `title`, `jira`; без часових полів);
  - `route`: справжній сервер у процесі на ефемерному порту (як у `make_before_4c3.py`) з шаром ВИМКНЕНО (`DC_TASKS_FILE` на
    тимчасовий файл ЛІГИ з `design_work_root` у тимчасовій теці й `profile_repos`; `vcs_provider` → `None`):
    `POST /api/task-new` {без `profile`; `profile: 'seo'`; `profile: 5`} → статус, код, запис задачі; `GET /api/tasks` (рядки:
    `id`, `profile`, `tags`); `GET /api/task` із заголовком `X-Canvas-Task` (поле `profile`).
- [ ] **Step 2:** запустити двічі (байт-у-байт), закомітити JSON + генератор + `Before4d1Shape`. Жодних змін у `app/`/`bin/`.

---

### Поправки контролера після Task 1 (04.11.2026) — мають перевагу над текстом Task 2–6

Знімок показав справжню поведінку 0.14.0; спека доповнена §6. Для Task 2–6:
- `tracks.legacy_tracks(cfg)` повертає `(tracks, default_id, fallback_root)`; `fallback_root` = `design_work_root` →
  `~/deai-work`; `design_work_roots` не словник → `{}`. `track_root` для ЛІГИ: id з власним коренем → він, інакше
  `fallback_root` (НЕ корінь дефолтного напрямку).
- `tracks.of_task(task)` повертає збережений рядок (`track`, інакше `profile`), без звірки з `ID_RE`; не рядок / порожній →
  `None`. `label_tag` застосовує правила мітки до `_LEGACY_LABELS.get(v, v)` (ЛІГА) / `label` (звичайний).
- ЛІГА в маршруті: будь-який рядок приймається як є (`'United'` теж); `null`/`''`/нема → `united`; `bad-track` — лише не рядок
  або конфлікт `track`/`profile`; `unknown-track` — ніколи. Звичайний простір — суворо за `ID_RE` і переліком.
- `inspector_ds_arg` лишає `strip()` і шаблон як у 0.14.0 (`?ds=zzz` для невідомого напрямку ЛІГИ).
- `/api/task` — через заголовок `X-Canvas-Task`, не `?id=` (у Task 4 й 6 так само).

---

### Task 2: ядро `app/tracks.py`

**Files:** Create `app/tracks.py`; Test `tests/test_tracks.py` (класи `Normalize`, `LegacyTracks`, `TaskTrack`).

- [ ] **Step 1: Падаючі тести** (кожне правило спеки §1–§2 — свій тест):
  - `normalize(raw, space_path)`: не список → `[]`; запис не словник / `id` поза `ID_RE` (`[a-z0-9-]{1,32}`) / дубль `id` →
    відкинуто (перший перемагає); `label` за правилами мітки (1…32, без коми й керівних, ті самі, що `serve._read_tag` —
    перенести правило в `tracks.py` і імпортувати в `serve`, а не дублювати), інакше `id`; `root` — абсолютний / `~/…` /
    відносний до `space_path` → абсолютний шлях; системна тека (`spaces.SYSTEM_DIRS`, з підтеками) чи не рядок → поле відсутнє
    (`root: None`); `repo` за `_REPO_OK` (перенести з `serve`) інакше `''`; `ds` за `ID_RE` інакше `''`; понад `MAX_TRACKS = 20`
    → перші 20; результат `[{id, label, root, repo, ds}]`; функція не кидає на будь-якому JSON (рекурсивні/величезні входи —
    як `[]`);
  - `default_id(tracks, raw)`: `raw` з переліку → він; інакше перший; порожньо → `None`;
  - `of_task(task)`: `track` за `ID_RE` → він; інакше `profile` за `ID_RE` → він; інакше `None`; не словник → `None`;
  - `find(tracks, id)`; `label_tag(tracks, task)`: знайдений → `label`; не знайдений, але id є → сам id (паритет «невідомий —
    як є»); `None` → `None`;
  - `legacy_tracks(cfg)` (спека §2): перелік `united`, `liga360`, `seo` + ключі `design_work_roots` і `profile_repos` (за
    `ID_RE`, порядок, без дублів); `root` = `design_work_roots[id]` → `design_work_root` → `~/deai-work` (розгорнутий); `repo` —
    `profile_repos[id]` за `_REPO_OK` (обрізаний) або `''`; `label` — `_LEGACY_LABELS` або `id`; `ds` = `id`; дефолт
    `united`. Повертає `(tracks, default_id)`. Не кидає на поганому `cfg`.
  - **Паритет із знімком:** для кожного сценарію `roots` / `repos` / `tags` у `before-4d1.json` — те саме значення, отримане
    через `tracks` (корінь, репо, похідна мітка).
- [ ] **Step 2: Реалізація** — `app/tracks.py` з модульним докстрінгом (що таке напрямок, звідки береться, чому адаптер ЛІГИ
  тимчасовий — до 4d-3). ⛔-уроки `work_root` (не вигадувати теку профілю без власного кореня) і `profile_repos` (репо без `-`
  на початку — інакше git прочитає як опцію; значень — ні в текстах, ні в журналах) переносяться в докстрінги.
- [ ] **Step 3:** мутації: прибрати відсів дубля `id`; прибрати перевірку системної теки; `of_task` без фолбеку на `profile`;
  `label_tag` повертає `None` для невідомого id. Коміт.

---

### Task 3: сервер — напрямки замість профілю (тека, репо, ДС, мітка)

**Files:** Modify `app/serve.py` (`work_root` ≈116, `profile_repos` ≈139, `_LEGACY_PROFILE_TAGS` ≈1604, `task_tags` ≈1650,
`task_new` ≈2178, `_task_new_write` ≈2240, `inspector_ds_arg` ≈2582 і його виклики ≈2716/2824/6000/6007); Test
`tests/test_tracks.py` (`ServerTracks`), наявні тести, що кличуть прибране (кожен — з причиною).

- [ ] **Step 1: Падаючі тести:**
  - `serve.space_tracks(sp)`: звичайний простір — з його `space.json` (`tracks.normalize` з `sp['path']`); простір ЛІГИ
    (`integrations`) без `tracks` у `space.json` — `tracks.legacy_tracks(load_legacy_tasks())`; простір ЛІГИ З `tracks` у
    `space.json` — саме вони (адаптер не застосовується); шар вимкнено (неявний простір) — як ЛІГА; битий `space.json` —
    `([], None)` для звичайного, адаптер для ЛІГИ;
  - `serve.track_root(sp, cfg, track_id)` (спека §3): знайдений → `root` напрямку (або шлях простору, коли `root` нема);
    не знайдений → `root` дефолтного; напрямків нема → шлях простору (звичайний) / `design_work_root` → `~/deai-work` (ЛІГА);
  - **диференційний `task_new`** для ЛІГИ (усі сценарії `task_new` знімка): той самий `dir`, `gitlab`, `title`, `jira`, і
    `profile` ТАКИЙ САМИЙ, плюс новий ключ `track` з тим самим значенням (крім `None`: `track` не пишеться);
  - звичайний простір із двома напрямками (`web` з `root` і `repo`, `mobile` без) і фейковим постачальником `vcs`
    (зразок — наявні тести `vcs`-бутстрапу в `tests/test_vcs_core.py`): `task_new(..., track='web')` → тека під `root`
    напрямку, запис `track: 'web'`, `vcs: {repo: …}` (бутстрап кличе фейковий `pull` з цим репо), БЕЗ `profile`-ключа зі
    значенням (ключ `profile: None` як сьогодні — так, щоб формат запису звичайного простору не мінявся, див. спеку §4);
    `track='mobile'` → без `vcs`; явний `vcs` у виклику перемагає репо напрямку; без постачальника `vcs` — репо напрямку не
    застосовується;
  - **диференційний `ds`**: для ЛІГИ хвіст `inspector_ds_arg` у розмітці макета (`/it/<n>/` задачі з `profile`) — як у знімку;
    звичайний простір із `ds: ''` — лише `?sp=<id>`; з `ds: 'united'` — `?ds=united&sp=<id>`;
  - **диференційний `tags`**: усі сценарії `tags` знімка через `task_tags(task, sp)` для ЛІГИ — те саме; звичайний простір —
    `label` напрямку;
  - `hasattr(serve, '_LEGACY_PROFILE_TAGS')` → `False`; у `app/serve.py` нема рядків `'united'`, `'liga360'`, `'seo'`
    (перевірка тексту файла, коментарі теж — імена напрямків ЛІГИ живуть лише в `tracks.py`).
- [ ] **Step 2: Реалізація** (спека §2–§5): `space_tracks`, `track_root`; `task_tags(task, sp=None)` (без `sp` — простір
  запиту; усі наявні виклики оновити); `inspector_ds_arg(ds, sp)` — викликачі передають `ds` напрямку задачі
  (`tracks.find(...)['ds']`; невідомий напрямок ЛІГИ — адаптер дає `ds = id`, тож байт-у-байт); `task_new(cfg, tid, …,
  track=None, root=None, repo=None, legacy=False)` — маршрут передає готові `root` і `repo` напрямку, у запис лягає `track`
  (коли є) і `profile` (ЛІГА — те саме значення; звичайний простір — `None`, як сьогодні); `_task_new_write` — `gitlab` з
  `repo` напрямку для ЛІГИ, `vcs: {repo}` для звичайного простору з постачальником `vcs`. Прибрати `_LEGACY_PROFILE_TAGS`,
  `_PROFILE_KEY`, `_REPO_OK` (→ `tracks`), `work_root`, `profile_repos` — якщо на них тримаються наявні тести чи `bin/`,
  лишити тонку обгортку над `tracks` з докстрінгом «до 4d-4» і назвати в звіті.
- [ ] **Step 3:** мутації: адаптер ЛІГИ застосовується навіть коли в `space.json` є `tracks`; `profile` не пишеться для ЛІГИ;
  репо напрямку застосовується без постачальника `vcs`; `inspector_ds_arg` бере `track` замість `ds`. `npm test`. Коміт.

---

### Task 4: API — `track` у `task-new`, `/api/tasks`, `/api/task`, опис простору

**Files:** Modify `app/serve.py` (маршрут `task-new` ≈7530–7660, `_task_rows` ≈1678, `/api/task` ≈5709, рядок ≈2045,
`spaces_listing` ≈4982); Test `tests/test_tracks.py` (`ApiTracks`), `tests/test_spaces_serve.py` (опис простору).

- [ ] **Step 1: Падаючі тести** (спека §4):
  - `POST /api/task-new`: `track: 'web'` → задача в напрямку; `profile: 'web'` (синонім) → те саме; обидва однакові → ок;
    різні → 400 `bad-track`; `track: 5` → 400 `bad-track`; `track: 'Bad!'` → 400 `bad-track`; `profile: 5` → 400 `bad-profile`
    (як було); невідомий `track` у просторі з явними напрямками → 400 `unknown-track`, ДО будь-якого запису (тека не
    створена, `tasks.json` не змінено); нема поля → `default_track`; звичайний простір без напрямків + `track: 'x'` → 400
    `unknown-track`; без поля → як сьогодні (`root` = шлях простору);
  - **диференційний `route`** для ЛІГИ: усі сценарії `route` знімка — ті самі статуси, коди й записи задач (+ ключ `track`);
    невідомий профіль ЛІГИ (`zzz`) і далі дозволений;
  - `GET /api/tasks`: кожен рядок має `track` (`tracks.of_task`) і `profile` як був; `GET /api/task`: те саме;
  - `GET /api/spaces`: кожен запис має `tracks: [{id, label}]` і `default_track`; у відповіді НЕМА `root` / `repo` напрямків
    (перевірка: значення шляху й репо з `space.json` фікстури не зустрічаються в тілі);
  - порядок перевірок маршруту: Origin 403 → тіло → `bad-track` / `bad-profile` → `unknown-track` → решта, як була.
- [ ] **Step 2: Реалізація.** Маршрут: `track = payload.get('track')`, `profile = payload.get('profile')` (синонім, правила
  вище) → `space_tracks(sp)` → `track_root` / `repo` напрямку → `task_new(...)`. Рядок `profile or 'united'` прибрати
  (дефолт — `default_track`). `NO_INTEGRATIONS_SPACE_MSG` і гілки `gitlab-needs-integrations` / `from-needs-plain-space` — без
  змін (це 4d-4).
- [ ] **Step 3:** мутації: синонім `profile` не читається; `unknown-track` після запису; `root`/`repo` протікають в опис
  простору. `npm test`. Коміт.

---

### Task 5: інструменти `bin/` — реєстр, корені, стан

**Files:** Modify `bin/registry.py` (`SHARED` ≈38, `_work_root` ≈430, підсумок напрямків ≈713), `bin/roots.py`
(≈34–92), `bin/state.py` (≈394); Test `bin/test_registry.py`, `bin/test_roots.py`, `bin/test_state.py` (якщо таких нема —
відповідні тести в `tests/`; знайти через `git grep -l registry tests bin`).

- [ ] **Step 1: Падаючі тести:**
  - `registry.SHARED` містить `track`; запис із реєстру з лише `profile` (машина на 0.14.0) дає локальній задачі ту саму теку,
    що з `track` (через `tracks.of_task`); запис з `track` і `profile` — `track` перемагає;
  - `roots.py`: план переносів і перелік коренів — за `tracks.of_task` і `tracks.legacy_tracks` (ті самі шляхи, що сьогодні
    для `profile`; задача лише з `track` — теж);
  - `state.py`: рядок шапки показує напрямок (`track`, інакше `profile`, інакше `—`); текст — «Напрямок:».
- [ ] **Step 2: Реалізація** — `bin/` імпортує `tracks` (так само, як імпортує `serve`/`install_config`); логіка коренів не
  дублюється.
- [ ] **Step 3:** мутація: `SHARED` без `track`; `_work_root` ігнорує `track`. Набори `bin` (`python3 -m unittest discover -s bin
  -p 'test_*.py'`) і `npm test`. Коміт.

---

### Task 6: живий тест

**Files:** Create `tests/live/tracks.test.mjs` (`PORT_BASE` — вільний, напр. `23000`; перевірити `tests/live-ports.test.mjs`;
теки `.live-tracks-*` + `.gitignore` + прибирання), зразок — `tests/live/notify-role.test.mjs`.

- [ ] Спершу прогнати наявні `spaces`, `tasks-home`, `wizard` як є — список падінь.
- [ ] Сценарії: (1) звичайний простір із двома напрямками в `space.json` (`web` з `root`, `mobile` без) → `POST /api/task-new`
  з `track: 'web'` → тека задачі під `root`, на «Задачах» у картки мітка `Web`; (2) задача з `profile: 'mobile'` (синонім) →
  мітка `Mobile`, тека — шлях простору; (3) `track: 'nope'` → 400 `unknown-track`, теки нема, задачі в списку нема; (4) ЛІГА
  (шар вимкнено, `DC_TASKS_FILE`) — нова задача без поля → мітка `United`, запис має і `track`, і `profile` = `united`;
  (5) `GET /api/spaces` — `tracks` без `root`/`repo`.
- [ ] Кожен змінений живий файл — по одному; потім `npm test`. Коміт.

---

### Task 7: документи й версія 0.15.0

- [ ] `CHANGELOG.md` — `## [0.15.0] — unreleased` у стилі `[0.14.0]`: Added (напрямки, `app/tracks.py`, `track` в API) /
  Changed / Removed (`_LEGACY_PROFILE_TAGS`, `work_root`, `profile_repos` як ядро — або «лишились обгортками до 4d-4») /
  Upgrading (ЛІГА: нічого; змішані версії в команді — записи пишуть і `track`, і `profile`; звичайний простір: як описати
  напрямки в `space.json`) / Deliberate differences (зі спеки) / Known limits (зі спеки + відхилення з нотаток контролера).
- [ ] `README.md` — розділ «Напрямки простору» (формат `space.json`, правила полів, приклад з вигаданими значеннями);
  `docs/design/spaces-and-modules.md` — шапка, «Stage 4d-1», розбиття 4d на 4d-1…4d-4 (рішення власника 04.11.2026), «Left for
  4d-2…4d-4»; README «Roadmap» — 4d з чотирма пунктами.
- [ ] Спека — «Implementation notes» (відхилення, прийняті на ревʼю). `package.json` 0.15.0; `npm test`; коміт.

---

## Після всіх задач (контролер)

1. Фінальне ревʼю всієї гілки від коміту спеки (`97f0971`).
2. Повні прогони на знімку: `npm test`; `/usr/bin/python3` 3.9.6; живі — по одному (`inspector-ds` 2/4 — стара червона;
   `dashboard-role` тест 6 — артефакт знімка в `/tmp`, перевіряти в робочій теці; випадкові падіння — перезапуск у робочій теці).
3. Дата в CHANGELOG → тег `v0.15.0` (анотований, neodisa) → `git push origin <sha>:refs/heads/main` і тег → звірити віддалений sha.
4. Памʼять, статус пайплайна, звіт власнику.
