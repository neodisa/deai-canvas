# Етап 4d-4a «Напрямки ЛІГИ остаточно явні, `profile` лише на межі» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** на першому старті 0.20 простір ЛІГА четвертим незалежним кроком `liga-4d4a` (свій датований бекап, позначка, відкат; усе або нічого) дістає напрямки з адаптера ЯВНИМИ в `space.json` (коли адаптер ще діє), а старим записам задач з `profile`, але без `track`, дописується `track = profile` у `tasks.json` (з `.bak`). Після кроку рантайм НЕ має адаптера: `tracks.of_task` читає лише `track`, API не віддає `profile`, `profile` читається тільки на трьох межах (`task-new`, реєстр, `_liga_flow`), `track_root` більше не знає про `cfg`.

**Architecture:** `tracks.adapter_applies(raw, path)` — єдиний критерій «адаптер діє» (для `_TrackView.adapter` у Task 2 і для міграції). Адаптер переїжджає з `tracks.py`/`serve.py` у приватні імена `liga_migrate` (Task 2 копіює, Task 4 видаляє з рантайму). Крок D — перший `Step` БЕЗ ролей і БЕЗ воріт паритету (`ungated`): ворота 4d-3a лишаються як були для кроку A. Записи задач пишуться під `spaces.WRITE_LOCK` із `.bak`; `restore` повертає `space.json`, але НЕ `tasks.json` (див. Поправку 1). `bin/registry.py::_track_of_entry` — єдина межа `track`/`profile` для реєстру. Охоронець `NoTracksAdapter` (AST) не дає адаптеру повернутися.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-07-liga-tracks-final-design.md`. Читати перед кожною задачею; ПОПРАВКИ НИЖЧЕ мають перевагу над текстом спеки й задач. Попередній етап: `docs/superpowers/plans/2026-11-06-liga-migration-c.md` (шаблон процесу: знімок → крок → LIFO → паритет → живі → документи).

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  Коміт — лише з переліком шляхів; новий файл спершу `git add -- <шлях>`. **Ніколи** `git add -A` / `git add .`; не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md`; ніколи `--amend`.
- ⛔ Лише точкові правки наявних файлів інструментом `Edit`; жодних скриптів `sed`/Python-заміни, жодного переписування файла цілком. Унифіковані diff-и нижче — ЕТАЛОН результату: застосовувати їх hunk за hunk через `Edit`, а не `patch`. Після КОЖНОЇ задачі: `git diff HEAD | grep '^-[^-]'` показує лише заплановані видалення.
- ⛔ У ЖОДЕН комітований файл (план, спека, докстрінги, тести, фікстури, CHANGELOG, памʼять) не пишемо ні шляху scratchpad, ні шляху охоронця, ні жодного шляху з імʼям користувача машини чи префіксом домашньої/тимчасової теки; імʼя користувача — лише з оточення (`os.path.expanduser('~')`). Перед кожним комітом: `git diff --cached | grep -nE "$(basename "$HOME")|<префікс домашніх тек macOS>|<префікс тимчасових тек macOS>"` → нуль (префікси — літерали, які виконавець складає сам; у файлах плану їх не друкуємо).

**Прогони й середовище**

- `G=<scratchpad>/bin/guard.py` — справжній шлях контролер дає в кожному брифі; кожна важка команда — `python3 "$G" <секунд> <МБ> <команда…>`. Живі тести — по одному файлу, ПОСЛІДОВНО: `node --test --test-concurrency=1 tests/live/<файл>.test.mjs`.
- Python-тести — під `python3` і під `/usr/bin/python3` (3.9): без `match`, без `X | Y` в анотаціях.
- ⛔ **Кожен прогін Python-тестів — з тимчасовим `HOME`** (`HOME=$(mktemp -d) python3 -B -m unittest …`). Причина (інцидент під час складання цього плану): старі тести `bin/roots.py` без підміни `HOME` створили порожні теки `blog`/`widget` у справжньому `~/deai-work` (прибрано `rmdir`-ом, нічого іншого не зачеплено). Після Task 6 `roots`/`task_new` без `root` пишуть у `default_task_root(cfg)` = `~/deai-work`; кожен тестовий клас, що викликає їх, мусить мати `mock.patch.dict(os.environ, {'HOME': …})` у `setUp`. Після кожного прогону: `ls ~/deai-work` не змінився.
- ⛔ Міграцію НІКОЛИ не запускати проти справжнього `~/.deai`; `DC_MIGRATE_LIGA=1` — лише з тимчасовим `DEAI_HOME`; не виставляти `DEAI_HOME` у шелі. Нових тестових стендів без `mock.patch.dict(os.environ, {'HOME': …, 'DEAI_HOME': …})` у `setUp` нема (`tests/test_serve.py::TestsCannotWriteLiveConfig` вимагає присвоєння `DEAI_HOME` у файлі, що пише простори, і `spaces_guard` у `setUpModule`/`tearDownModule`). Жодної мережі (`NoNet`/`SocketTripwire`), порти 8765/4317 не чіпати, процеси — лише за PID (ніяких `pkill`/`killall` за шаблоном). Не чіпати `~/deai-published`, справжній `tasks.json`, `~/.gitconfig`, `~/.claude/pipeline-feedback/`.
- Знеособлено: лише вигадані значення (`https://sb.example.com`, `pv-12345678`, `team_x`, `alpha@example.com`). ПІБ/ЄДРПОУ/ІПН/реквізити у фікстурах — нуль.
- ⛔ Живі тести ізольовані (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) → доводять ізольований шлях, а НЕ шлях власника; кожне твердження про шлях власника має НЕізольований юніт-тест із справжніми ефектами (стенд `AfterMigrationParity4d4a`, Task 7).

**Конвенції:** коментарі коду українською, ⛔-уроки переносяться в нове місце; TDD (тест червоний → код → зелений); кожна нова перевірка доводиться мутацією: один рядок → потрібний тест червоніє → файл відновлено, `sha256` до/після збігається; мутації — лише `python3 -B` (застарілий `.pyc` дає ложне «вижила»), по одній. Еталони (`tests/legacy-golden.test.mjs`, `GoldenPinTest`, знімки `before-4c1…4d4a`, `AfterMigrationParity`, `…4d3b`, `…4d3c`, `…4d4a`) — зелені БЕЗ `UPDATE_*`. Кожна зміна наявного тесту — у звіті одним рядком із причиною; НІЧОГО не видаляємо мовчки (див. таблицю відповідності в Task 4/5). Номери рядків — за `v0.19.0` (commit `80dc34a`; `app/`, `bin/` на HEAD `8e774f7` ідентичні тегу, відрізняється лише документ спеки). Усі hunk-и нижче — реальний результат прототипу, прогнаного поверх `git archive v0.19.0` (поза репо); виконавець застосовує їх і доводить тестами, не копіює наосліп.

**Типові пастки цього етапу (⛔):** (1) `restore` НЕ повертає `tasks.json`; (2) `_commit_space` не має перезаписувати `tracks`, які власник дописав між планом і записом; (3) `Step.roles` — кортеж пар, а не словник; (4) `track_root` втратив `cfg`, тож шлях «без кореня» тепер `None` і вирішується викликачем (`default_task_root`); (5) зростання `ALL_STEPS` до чотирьох ламає стенди 4d-3c — піни `STEPS[:3]` (Поправка 10).

---
## Поправки до спеки (виявлено при звірці з кодом; мають перевагу над текстом задач і спеки)

Звірено з `v0.19.0`. Кожна — з доказом `файл:рядок` і тим, що робити.

1. **`restore` не повертає `tasks.json`.** Спека каже, що відкат повертає і записи. У коді `_restore_locked` (`app/liga_migrate.py:893`) пише лише `space.json` і секрети, а докстрінг `_restore` (≈855) прямо каже, що дані задач не чіпає; `_commit_space` (644) теж пише тільки `space.json`. Відкат `tasks.json` перетер би живий файл власника (нові задачі, статуси). Правильно: `restore` повертає `space.json` (без напрямків, мітка D зникає); записи лишаються `track = profile` — для 0.19 це нешкідливо (`of_task` 0.19 читає `track`, потім `profile`; обидва однакові). Крок сам пише `tasks.json` і лишає `tasks.json.bak` поруч (`shutil.copy2` під `WRITE_LOCK`). У тексті спеки й CHANGELOG: «відкат повертає `space.json`; `tasks.json.bak` — ручний».
2. **`Step.roles` — кортеж пар** (`app/liga_migrate.py:397`), тож у спеці «roles: {}» читати як `()`. Потрібне нове поле `ungated` (крок без воріт паритету й без ролей): `Step('mark roles tracks suffix stamp_re entries ungated', defaults=(None, False))`; `STEP_D = Step('liga-4d4a', (), True, '-liga-4d4a', re, lambda cfg, present: {}, True)`; `ALL_STEPS = (A, B, C, D)`.
3. **`_unknown_values` рахує задачі БЕЗ значення як невідомі** (використовується воротами 4d-3a). Нова нотатка `unknown-values` кроку D рахує лише НЕпорожні значення поза переліком; ворота кроку A не міняються (`app/liga_migrate.py`, `_unknown_values`).
4. **Відносний корінь адаптера.** `tracks.normalize` перебазовує його на теку простору, а не відкидає (`root-rebased:<id>`) — у спеці є лише `root-dropped`. Нотатки кроку D: п’ять кодів — `root-dropped:<id>`, `root-rebased:<id>`, `unknown-values`, `default-root-differs`, `non-id-keys`; порядок — кореневі, потім `unknown-values`, `default-root-differs`, `non-id-keys`.
5. **`task_new` без `root` не може взяти «теку простору».** Неявний простір шару-OFF має `path == ''` (`app/spaces.py:51`, `IMPLICIT = {'id':'legacy','path':'', …}`). Тому лишається cfg-залежний `default_task_root(cfg)` (`design_work_root` із cfg, інакше `DEFAULT_TASK_ROOT = '~/deai-work'`), а `track_root(sp, track_id)` без `cfg` повертає: корінь знайденого напрямку → корінь дефолтного → шлях простору → `None` (безшляховий неявний простір). ≈25 тестових викликачів `task_new(cfg, …)` без `root` лишаються робочими.
6. **Шар-OFF (`DC_TASKS_FILE` без `DEAI_HOME`) — ізольований/тестовий режим, де адаптер діяв** (`_liga_like(IMPLICIT)`). Після 0.20 це «нема напрямків»: мітка — нижній регістр id, `?ds=` порожній для записів лише з `profile`. Класи 0.14.0 `LegacyTracks`, `ServerLegacyParity`, `LegacyParity`, `BinParity` перестають мати предмет — переносимо адаптерні в `tests/test_liga_adapter.py` (націлені на `liga_migrate._legacy_*`), решту ретайримо з таблицею відповідності (Task 4/5).
7. **Потрібен новий код `abort-records`.** Крок D — перший, що пише `tasks.json`; збій запису (`copy2`/`atomic_write_json`) → `abort-records`, `space.json` не змінено. Є й `abort-tracks` (спека): `normalize(raw, path, roots=False)` мусить дати ті ж id і дефолт, що й адаптер; для >20 id (`MAX_TRACKS = 20`) — завжди `abort-tracks`, і це ПОСТІЙНО (власник чистить `profile_repos`/`design_work_roots`). `skip-nothing` тепер вимагає й відсутності записів до виправлення.
8. **`legacy_*` має більше читачів, ніж у спеці:** `serve.task_new` (`app/serve.py:2456`), `bin/registry.py:441`, `bin/roots.py:48,70`, а також `liga_migrate._compute_tracks`/`_unknown_values` (`tracks.of_task`, `legacy_*`, `label_tag(legacy=True)`). Тому в `liga_migrate` — приватні `_legacy_of_task`, `_legacy_label`, `_legacy_roots_of`, `_legacy_fallback`, `_legacy_root`, `_legacy_repos`, `_legacy_tracks`, `_FALLBACK_ROOT`, `_LEGACY_IDS/_DEFAULT/_LABELS`.
9. **`serve._legacy_cfg` не має інших читачів** (лише `:116` і `:1789`) — видаляється разом з `profile_repos` (`:112`).
10. **Зростання `ALL_STEPS` ламає стенди 4d-3c** (~16 тестів): піни `STEPS = ALL_STEPS[:3]` у `_StepC` (`tests/test_liga_migrate_c.py` ≈780), тести розпаковки/рівності `ALL_STEPS` (≈819–840), стенди паритету й старту; те саме у 3a/3b (`AfterMigrationParity` — `.adapter` і триаргументний `track_root`; `…4d3b` — листинг `/vcs/form/space_row/tracks`): у `_build` додати прогін D або оновити очікування (так робила Поправка 1 плану 4d-3c).
11. **Точна поведінка 0.19 для `tracks: []` чи непридатного списку:** рантайм застосовує адаптер (`_TrackView.adapter`), 4d-3a звітує `tracks-present`, **4d-4a перезаписує** (критерій `adapter_applies`). Для НЕмігрованої ЛІГИ: адаптер із кореня `tasks.json`. Після 0.20: нема напрямків, і старі записи лише з `profile` втрачають мітку й `ds` (ширша відмінність, ніж у спеці, різниця 4) — крок D саме тому дописує `track`.
12. **`bin/roots.py`:** `plan` і `roots_in_use` отримують параметр `view` (`serve._TrackView(spaces.active_space())`); `_root_of(cfg, view, track) = serve.track_root(view, track) or serve.default_task_root(cfg)`; прапорець «свій» = явний напрямок має корінь. Тести `tests/test_roots.py` (13 із 14 червоніють) і `bin/test_registry.py::TestTrack` — переписати з тимчасовим `HOME`.
13. **Реєстр: pull мусить сам виставляти `track` з `profile`** (межа), інакше запис кеша лише з `profile` у 0.20 не має напрямку (`of_task` лише `track`). Реалізація — у циклі після копіювання `SHARED` (`bin/registry.py` ≈ 531–540, Task 6). Побічний ефект: перший `push` машини 0.20 дописує `track` у записи реєстру (дрейфу `status` це не дає: порівнюються лише ключі, що є в записі реєстру).
14. **`abort-tracks` для >20 id — постійний** (див. 7): у `Known limits` CHANGELOG, у `status`/CLI показати як є; ЛІГА лишається без напрямків у `space.json` (нові задачі кладуться в `default_task_root`).
15. **Зовнішній dev-pipeline** читає `profile` прямо з записів `tasks.json` (`preflight.py:127` скіла) — записи `profile` ЗБЕРІГАЮТЬ, не ламається; і постить `profile` у `task-new` — покрито правилами межі (Task 6). Це ризик зовнішнього інструмента, не код цього репо.
16. **`_liga_flow` без LIGA-простору в реєстрі** тепер дає `no-space` замість `no-integrations-space` для знака лише з `profile`; `NoSpaces.test_liga_signs…` потребує простору ЛІГИ з явними напрямками.

---

## Структура файлів

- **Створити:** `tests/make_before_4d4a.py` (генератор знімка), `tests/fixtures/liga-migration/before-4d4a.json`, `tests/test_liga_migrate_d.py` (крок D, LIFO на чотири кроки, старт/CLI), `tests/test_liga_adapter.py` (перенесені адаптерні класи), `tests/test_no_adapter.py` (охоронець).
- **Змінити:** `app/liga_migrate.py` (адаптер, крок D, вивід), `app/tracks.py` (`adapter_applies`; без `legacy_*`; `of_task`, `label_tag`), `app/serve.py` (без адаптера; `default_task_root`; `_task_new`, `_liga_flow`; API без `profile`), `bin/registry.py` (`_track_of_entry`, pull), `bin/roots.py` (`view`), `bin/migrate_liga.py` (вивід D), `tests/test_tracks.py`, `tests/test_task_tags.py`, `tests/test_roots.py`, `tests/test_spaces_serve.py`, `tests/test_state.py`, `tests/test_comments_role.py`, `tests/test_dashboard.py`, `tests/test_tasks_overview.py`, `bin/test_registry.py`, `tests/test_liga_migrate*.py` (піни), живі `tests/live/{fixture.mjs,tasks-home,modules,tracks,inspector-ds,liga-migrate}.test.mjs`, `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, спека (Implementation notes), `package.json`.
- **Не чіпати:** `app/spaces.py` (`IMPLICIT`, `layer_on`, `tasks_file`), JS застосунку (не читає `profile` з `/api/task` чи рядків задач), записи `profile` у `tasks.json` на диску.

---
### Task 1: знімок 0.19.0 (ДО будь-якої правки коду)

**Files:** створити `tests/make_before_4d4a.py`, `tests/fixtures/liga-migration/before-4d4a.json`; додати клас `Before4d4aShape` у `tests/test_liga_migrate_d.py`.

Знімок знімає ПОВЕДІНКУ 0.19.0 на чотирьох стендах: `parity` (А-ворота паритету проходять), `notes` (прихований корінь під `HOME`, відносний корінь, власний корінь `united`, задача з `profile: 'Weird'`, нетиповий ключ `Bad_Key`), `explicit` (напрямки вже явні в `space.json`) і `plain` (звичайний простір без ЛІГИ, запис лише з `profile`). Розділи: `labels`, `ds`, `repos`, `roots` (триаргументний `track_root` у 0.19), `view`, `roots_cli` (лише стенди ЛІГИ, за id), `registry` (лише ЛІГА), `task_new` (11 сценаріїв), `api` (ключі як словник `{k: True}`); `meta`: `version 0.19.0`, `source_commit 80dc34a`.

- [ ] **Step 1:** Покласти генератор нижче як `tests/make_before_4d4a.py` (новий файл — `Write` дозволено). Він детермінований: два прогони побайтово однакові, шляхів машини в виході нема (`scrub`/`rel`).
- [ ] **Step 2:** ⛔ Знімати лише з ЧИСТОГО `v0.19.0`: `git archive v0.19.0` у тимчасову теку + копія генератора + прогін. `_code_differs_from_source()` у генераторі відмовляє (exit 2), якщо `app/`/`bin/` відрізняються від `git show v0.19.0:…` — це гарантує, що знімок не «забруднений» правками цього етапу.
- [ ] **Step 3:** `python3 -B tests/make_before_4d4a.py` двічі → `cmp` ідентичні → результат як `tests/fixtures/liga-migration/before-4d4a.json`. Комітити лише `tests/make_before_4d4a.py` і фікстуру ПЕРШИМ комітом етапу.
- [ ] **Step 4:** `Before4d4aShape` (код нижче, у `tests/test_liga_migrate_d.py` разом з рештою) — форма знімка: чотири стенди, обовʼязкові розділи, `meta`, ≥ N листків, немає шляхів машини.

#### Генератор (повний текст)

```python
#!/usr/bin/env python3
"""Генератор знімка поведінки напрямків ЛІГИ на 0.19.0: `tests/fixtures/liga-migration/before-4d4a.json` (етап 4d-4a, Task 1).

Знімок знято ДО змін коду (код = 0.19.0, коміт `80dc34a`, тег `v0.19.0`) і лишається в репо еталоном паритету четвертого кроку
міграції ЛІГИ: після 0.20 мітки, `?ds=`, репозиторії, корені нових задач відомих напрямків, `bin/roots.py`, теки задач із
реєстру й відповіді API — ті самі для людини, хоч адаптер напрямків зник (їх веде явний `tracks` у `space.json`), а `profile`
більше не читається з записів. Тести наступних задач (`tests/test_liga_migrate_d.py`) читають JSON, а не переганяють генератор.
Запуск на НОВОМУ коді дасть не «до», а «після»: еталон не перезаписувати.

Спільні помічники (`Rig`, `NoNet`, `SocketTripwire`, `scrub`, `rel`, `CLEAN`, `_write`, вигадані константи, `_call`) ІМПОРТУЮТЬСЯ з
`make_before_4d3a.py`/`make_before_4d3b.py`: друга копія розійшлась би.

Чотири стенди; на кожному — ті самі секції:
  * `parity`   — ЛІГА з адаптером і повним паритетом (`united` без власного кореня), `space.json` нема;
  * `notes`    — ЛІГА, де розбіжності з адаптером є всіх типів (корінь системної теки, відносний корінь, власний корінь `united`
                 ≠ спільного, значення поза переліком, ключі поза `ID_RE`);
  * `explicit` — ЛІГА з уже явним `tracks` у `space.json` (як після 4d-3a);
  * `plain`    — звичайний простір (без інтеграцій) зі своїми `tracks`.
Секції: `labels` (`serve.task_tags`), `ds` (`serve.task_ds`), `repos` (`serve.track_repo`), `roots` (`serve.track_root`),
`view` (`serve.space_tracks`), `task_new` (`POST /api/task-new`: статус, код, запис), `roots_cli` (`roots.plan`/`roots_in_use`),
`registry` (`registry._work_root` для записів реєстру з `profile`/`track`), `api` (`GET /api/task`, `GET /api/tasks`: ключі й
значення; `profile` у відповіді — ТАК, у знімку).

⚠️ ПІДПИСИ 0.19.0: `serve.track_root(sp, cfg, tid)` (три аргументи); у новому коді — `track_root(sp, tid)`. Тести «після» кличуть
нову форму. Не міняти тут: це документація того, як знято.

Запуск (з кореня репо): проти ЗАМОРОЖЕНОЇ копії старого коду:
    D=$(mktemp -d) && git archive v0.19.0 | tar -x -C "$D" && cp tests/make_before_4d4a.py "$D/tests/"
    python3 -B "$D/tests/make_before_4d4a.py" --out tests/fixtures/liga-migration/before-4d4a.json
Запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від `80dc34a`, генератор ВІДМОВЛЯЄ (код виходу 2).

⛔ Ізоляція: власні тимчасові `HOME` і `DEAI_HOME`, чисте оточення, жодної мережі (розтяжка сокетів), `serve.vcs_provider` →
`None`, шпигуни замість `serve._registry_push`/`serve.git_autocommit`/`Handler._overview_sync`; справжній `~/.deai` стереже
`spaces_guard`; порти 8765/4317 не чіпаємо (ефемерний порт loopback).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

from make_before_4d3a import (CLEAN, REPO_SEO, REPO_UNITED, NoNet, Rig, Server, SocketTripwire, Vcs,  # noqa: E402
                              _write, rel, scrub)
from make_before_4d3b import _call  # noqa: E402

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4a.json')
STANDS = ('parity', 'notes', 'explicit', 'plain')
#: Значення напрямку в сценаріях (`7` і `None` — не рядки). Ключ у JSON — `repr`.
VALUES = ('united', 'liga360', 'seo', 'custom-x', 'United', 'zzz', '', None, 7)
#: Задачі стендів: різна форма запису напрямку (старий лише `profile`, новий `track`, обидва, жодного, не рядок).
TASKS = {
    'a-1': {'track': 'seo'},
    'a-2': {'profile': 'united'},
    'a-3': {'profile': 'liga360', 'track': 'liga360'},
    'a-4': {'track': 'zzz'},
    'a-5': {'track': 'United'},
    'a-6': {},
    'a-7': {'track': 'seo', 'profile': 'united'},
    'a-8': {'profile': 5},
}
#: Задачі зі значенням поза переліком (`zzz`, `United`) — лише на стенді `notes` (на `parity` вони дали б нотатку `unknown-values`).
UNKNOWN_ONLY_IN_NOTES = ('a-4', 'a-5')
#: Тіла `POST /api/task-new` (ключ — назва сценарію; `id` різні, `space` додається генератором).
POSTS = (
    ('none', {'id': 'n-none', 'title': 'Alpha'}),
    ('track_seo', {'id': 'n-seo', 'title': 'Alpha', 'track': 'seo'}),
    ('profile_seo', {'id': 'n-pseo', 'title': 'Alpha', 'profile': 'seo'}),
    ('profile_united_track_seo', {'id': 'n-conf', 'title': 'Alpha', 'profile': 'united', 'track': 'seo'}),
    ('track_upper', {'id': 'n-up', 'title': 'Alpha', 'track': 'United'}),
    ('profile_upper', {'id': 'n-pup', 'title': 'Alpha', 'profile': 'United'}),
    ('track_zzz', {'id': 'n-zzz', 'title': 'Alpha', 'track': 'zzz'}),
    ('profile_zzz', {'id': 'n-pzzz', 'title': 'Alpha', 'profile': 'zzz'}),
    ('track_not_a_string', {'id': 'n-five', 'title': 'Alpha', 'track': 5}),
    ('profile_not_a_string', {'id': 'n-pfive', 'title': 'Alpha', 'profile': 5}),
    ('track_with_slash', {'id': 'n-bad', 'title': 'Alpha', 'track': 'Bad/Id'}),
)
#: Записи спільного реєстру колег: старий інструмент шле лише `profile`.
REGISTRY_ENTRIES = {'profile_only_seo': {'profile': 'seo'}, 'track_only_seo': {'track': 'seo'},
                    'both_conflict': {'profile': 'united', 'track': 'seo'}, 'none': {}, 'profile_unknown': {'profile': 'zzz'}}


def _tasks(rig, notes):
    w = os.path.join(rig.home, 'work')
    out = {}
    for tid, extra in TASKS.items():
        if tid in UNKNOWN_ONLY_IN_NOTES and not notes:
            continue
        d = os.path.join(w, tid)
        _write(os.path.join(d, 'iterations.json'), {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00'}], 'publish_url': None})
        out[tid] = {'dir': d, 'title': 'Task ' + tid, 'jira': '', **extra}
    return out


def _stand(tmp, name):
    """`(rig, sp, cfg)`: ЛІГА (`sp` — запис ЛІГИ) чи звичайний простір (`plain`), старий `tasks.json` із задачами `TASKS`."""
    rig = Rig(tmp, name)
    w = os.path.join(rig.home, 'work')
    extra = {'tasks': _tasks(rig, name == 'notes'), 'current': 'a-1'}
    if name == 'notes':
        extra['design_work_roots'] = {'united': os.path.join(w, 'united'), 'seo': os.path.join(rig.home, '.hidden', 'seo'), 'liga360': 'rel/l360',
                                      'custom-x': os.path.join(w, 'custom'), 'Bad_Key': os.path.join(w, 'bad')}
        extra['profile_repos'] = {'united': REPO_UNITED, 'seo': REPO_SEO, 'Bad_Key': REPO_UNITED}
        extra['tasks']['a-9'] = {'dir': os.path.join(w, 'a-9'), 'title': 'Task a-9', 'jira': '', 'profile': 'Weird'}
    elif name == 'explicit':                             # `space.json` дзеркалить корінь `tasks.json`, як записала б міграція
        extra['design_work_roots'] = {'seo': os.path.join(w, 'seo'), 'custom-x': os.path.join(w, 'custom')}
    elif name in ('parity', 'plain'):
        extra['design_work_roots'] = {'custom-x': os.path.join(w, 'custom')}      # `united` без власного кореня: паритет повний
    cfg = rig.config(extra=extra)
    if name == 'explicit':
        shared = os.path.join(w, 'shared')
        liga = rig.registry(space_json={
            'tracks': [{'id': 'united', 'label': 'United', 'root': shared, 'repo': REPO_UNITED, 'ds': 'united'},
                       {'id': 'liga360', 'label': 'LIGA360', 'root': shared, 'repo': '', 'ds': 'liga360'},
                       {'id': 'seo', 'label': 'SEO', 'root': os.path.join(w, 'seo'), 'repo': REPO_SEO, 'ds': 'seo'},
                       {'id': 'custom-x', 'label': 'custom-x', 'root': os.path.join(w, 'custom'), 'repo': '', 'ds': 'custom-x'}],
            'default_track': 'united'})
    else:
        liga = rig.registry()
    sp = liga
    if name == 'plain':
        plain_dir = os.path.join(rig.home, 'plain-space')       # у HOME: корінь поза HOME `tracks.normalize` відкинув би
        _write(os.path.join(plain_dir, 'space.json'), {'tracks': [
            {'id': 'web', 'label': 'Web', 'root': os.path.join(plain_dir, 'web'), 'repo': REPO_UNITED, 'ds': 'web'},
            {'id': 'app', 'label': 'App', 'root': None, 'repo': '', 'ds': ''}], 'default_track': 'web'})
        _write(os.path.join(plain_dir, 'tasks.json'), {'tasks': {}, 'current': ''})
        sp = {'id': 'plain', 'path': plain_dir, 'legacy': False, 'integrations': False}
        reg = {'version': 1, 'current': 'legacy', 'spaces': [liga, sp]}
        _write(os.path.join(rig.deai, 'spaces.json'), reg)
    return rig, sp, cfg


def _entry_view(entry, home):
    """Запис задачі для знімка: ключі напрямку + `dir` відносно HOME + множина ключів."""
    return {'track': entry.get('track', '<absent>'), 'profile': entry.get('profile', '<absent>'),
            'dir': rel(entry.get('dir'), home), 'keys': {k: True for k in sorted(entry)}}


def _scenarios(tmp, name):
    import registry
    import roots
    import serve
    rig, sp, cfg = _stand(tmp, name)
    out = {}
    spy = mock.MagicMock(return_value=False)
    with rig.activate(), mock.patch.object(serve, 'vcs_provider', Vcs()), mock.patch.object(serve, '_registry_push', spy), \
            mock.patch.object(serve, 'git_autocommit', lambda *a, **k: None), \
            mock.patch.object(serve.Handler, '_overview_sync', lambda *a, **k: None):
        tasks = cfg['tasks']
        out['labels'] = {tid: serve.task_tags(t, sp) for tid, t in tasks.items()}
        out['ds'] = {tid: serve.task_ds(t, sp) for tid, t in tasks.items()}
        items, default = serve.space_tracks(sp)
        out['view'] = {'ids': [t['id'] for t in items], 'labels': [t['label'] for t in items], 'default': default,
                       'repos': {t['id']: t['repo'] for t in items}, 'ds': {t['id']: t['ds'] for t in items},
                       'roots': {t['id']: rel(t['root'], rig.home) for t in items}}
        values = VALUES + (('web', 'app') if name == 'plain' else ())
        out['repos'] = {repr(v): serve.track_repo(sp, v) for v in values}
        out['roots'] = {repr(v): rel(serve.track_root(sp, cfg, v), rig.home) for v in values}     # 0.19.0: (sp, cfg, track)
        if name != 'plain':                              # `bin/roots.py` і реєстр — інструменти ЛІГИ
            with serve.spaces.request_space(sp['id']):
                out['roots_cli'] = {
                    'plan': {r[0]: r[1:] for r in scrub([list(r) for r in roots.plan(cfg)], rig.home)},
                    'in_use': {r[0]: r[1:] for r in scrub([list(r) for r in roots.roots_in_use(cfg)], rig.home)}}
            out['registry'] = {k: rel(registry._work_root(cfg, e), rig.home) for k, e in REGISTRY_ENTRIES.items()}
        with Server() as srv:
            posts = {}
            for key, body in POSTS:
                body = dict(body, space=sp['id'])
                st, resp = _call(srv, 'POST', '/api/task-new', body=body)
                row = {'status': st, 'code': resp.get('code') if isinstance(resp, dict) else None}
                tf = spaces_tasks_file(sp)
                with open(tf, encoding='utf-8') as f:
                    saved = json.load(f)['tasks']
                row['entry'] = _entry_view(saved[body['id']], rig.home) if body['id'] in saved else None
                posts[key] = row
            out['task_new'] = posts
            api = {'task': {}}
            for tid in ('a-1', 'a-2', 'a-3', 'a-6', 'a-8'):
                if name == 'plain':
                    break
                st, body = srv.req('GET', '/api/task', task=tid)
                api['task'][tid] = {'status': st, 'keys': {k: True for k in sorted(body)} if isinstance(body, dict) else None,
                                    'profile': body.get('profile', '<absent>'), 'track': body.get('track'), 'tags': body.get('tags')}
            st, body = srv.req('GET', '/api/tasks')
            api['tasks'] = {'status': st, 'rows': [{k: r.get(k, '<absent>') for k in ('id', 'profile', 'track', 'tags')}
                                                    for r in sorted(body.get('tasks', []), key=lambda r: r['id'])
                                                    if r['id'].startswith('a-')]}
            st, body = srv.req('GET', '/api/spaces')
            row = next(r for r in body['spaces'] if r['id'] == sp['id'])
            api['space_row'] = {'tracks': row.get('tracks'), 'default_track': row.get('default_track')}
            out['api'] = api
    return scrub(out, rig.home)


def spaces_tasks_file(sp):
    import spaces
    return spaces.tasks_file(sp)


def make():
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d4a-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire, mock.patch('urllib.request.urlopen', NoNet()):
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.19.0', 'source_commit': _source_commit(), 'generator': 'tests/make_before_4d4a.py',
                             'volatile_stripped': []}, 'stands': {}}
            for name in STANDS:
                snap['stands'][name] = _scenarios(tmp, name)
            snap['non_loopback_attempts'] = wire.count
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.19.0 = `80dc34a`; після нього лише docs 4d-4a). Зашито."""
    return '80dc34a'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — у `ROOT` нема `.git`
    (заморожена копія з `git archive`: довіряємо рецепту). Закрито за замовчуванням усередині git-теки (рецепт 4d-3a)."""
    if not os.path.lexists(os.path.join(ROOT, '.git')):
        return None
    try:
        top = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=30)
        if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
            return True
        src = _source_commit()
        if subprocess.run(['git', '-C', ROOT, 'cat-file', '-e', src + '^{commit}'], capture_output=True, timeout=30).returncode != 0:
            return True
        diff = subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', src, '--', 'app', 'bin'], capture_output=True, timeout=60)
        untracked = subprocess.run(['git', '-C', ROOT, 'ls-files', '--others', '--exclude-standard', '--', 'app', 'bin'],
                                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return True
    return untracked.returncode != 0 or diff.returncode != 0 or bool(untracked.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if os.path.realpath(args.out) == os.path.realpath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4d4a: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
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
```

---
### Task 2: крок `liga-4d4a` — критерій, розрахунок, записи, запис, коди

**Files:** `app/tracks.py` (додати `adapter_applies`), `app/liga_migrate.py` (hunks 1–15 нижче), `tests/test_liga_migrate_d.py` (класи `StepDConstants`, `AdapterApplies`, `StepDPlanTest`, `StepDRunTest`), піни в `tests/test_liga_migrate_c.py` (+ 3a/3b паритети).

**Що робить крок (рішення):**

- `tracks.adapter_applies(raw, path) = raw is None or not normalize(raw, path, roots=False)` — єдиний критерій «адаптер діє»; `raw` — значення `space.json['tracks']`. У Task 2 його читає `_TrackView.adapter` (замість власної умови) і міграція; після Task 4 — лише `tracks.py` і `liga_migrate.py` (охоронець).
- `_adapter_tracks(cfg, path, others)` → `(raw, norm, default, root_notes)`; `_compute_tracks` — обгортка з воротами паритету для кроку A (поведінка A не змінюється: покриває знімок 4d-3a).
- `_records_to_fix(cfg)` — id задач, у яких `track` не непорожній рядок, а `profile` — непорожній рядок.
- `_commit_records(p, step)` — під `spaces.WRITE_LOCK` перечитує `tasks.json`, виставляє `track = profile`, `shutil.copy2(path, path + '.bak')`, `atomic_write_json`; повертає ФАКТИЧНУ кількість.
- `_commit_space` для `ungated`: перезаписує `tracks` лише якщо `adapter_applies(cur.get('tracks'))` ще істинний ПІД замком (власник міг дописати напрямки між планом і записом); у позначці `tracks = wrote`, `records = actual`.
- Позначка: `{roles: [], tracks: bool, records: N, notes: [...], at, backup}`.
- Нові коди: `abort-tracks`, `abort-records` (Поправка 7); `skip-nothing` вимагає й «нема записів».
- Нотатки (Поправка 4): порядок `root-dropped|root-rebased`, `unknown-values`, `default-root-differs`, `non-id-keys`; без шляхів.
- ⛔ Рантайм у Task 2 ще з адаптером: `_legacy_*` у `liga_migrate` — КОПІЇ (Task 4 видалить оригінали з `tracks.py`/`serve.py`). Тому тест `test_the_view_asks_the_same_function` дійсний лише тут і в Task 4 замінюється охоронцем.

- [ ] **Step 1 (червоне):** вставити в `tests/test_liga_migrate_d.py` класи `StepDConstants`, `AdapterApplies`, `StepDPlanTest`, `StepDRunTest` з повного тексту файла нижче (розділ «Повний `tests/test_liga_migrate_d.py`»). Прогін → `AttributeError: STEP_D`.
- [ ] **Step 2 (зелене):** застосувати hunks (diff 0.19.0 → прототип) до `app/liga_migrate.py` — перші 15, до `_run_locked` включно:

```diff
--- a/app/liga_migrate.py
+++ b/app/liga_migrate.py
@@ -55,7 +55,7 @@
 COMPAT = 'comment-layer'
 SKIP_CODES = ('skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-held', 'skip-no-path', 'skip-path-in-git',
               'skip-space-json-unreadable', 'skip-registry-unreadable', 'skip-tasks-unreadable', 'skip-nothing', 'skip-busy', 'skip-integrations-off')
-ABORT_CODES = ('abort-provider', 'abort-internal', 'abort-lock')
+ABORT_CODES = ('abort-provider', 'abort-internal', 'abort-lock', 'abort-tracks', 'abort-records')
 _REASONS = {
     'skip-layer-off': 'шар просторів вимкнено: міграція не біжить',
     'skip-no-liga': 'у реєстрі нема простору ЛІГА',
@@ -67,11 +67,13 @@
     'skip-space-json-unreadable': 'space.json простору ЛІГА не читається',
     'skip-registry-unreadable': 'реєстр просторів не читається',
     'skip-tasks-unreadable': 'старий tasks.json не читається: конфіг ЛІГИ невідомий',
-    'skip-nothing': 'нічого мігрувати (нема ні ролей, ні напрямків): позначку не пишемо, наступний старт перевірить знову',
+    'skip-nothing': 'нічого мігрувати (нема ні ролей, ні напрямків, ні записів задач): позначку не пишемо, наступний старт перевірить знову',
     'publisher-present': 'публікацію вже веде інший модуль простору: крок його не перебиває',
     'skip-busy': 'міграція вже виконується іншим процесом (замок migrations/.lock зайнятий)',
     'abort-provider': 'ядро не вирішує мігровану роль на розрахованому space.json: міграція нічого не пише',
     'abort-internal': 'непередбачена помилка розрахунку: міграція нічого не пише',
+    'abort-tracks': 'розраховані напрямки не збігаються з адаптером за id чи дефолтом: міграція нічого не пише',
+    'abort-records': 'tasks.json не записано: space.json не змінено, наступний запуск почне заново',
     'abort-lock': 'міжпроцесний замок недоступний (flock не працює на цій файловій системі): міграція нічого не пише, щоб не йти без замка',
 }
 
@@ -85,7 +87,7 @@
 
 def _result(status, space_id=None, **kw):
     out = {'status': status, 'reason': _REASONS.get(status, ''), 'space_id': space_id, 'roles': {}, 'tracks': False,
-           'tracks_reason': None, 'space_json': None, 'secrets': {}, 'space_path': None}
+           'tracks_reason': None, 'space_json': None, 'secrets': {}, 'space_path': None, 'records': [], 'notes': []}
     out.update(kw)
     return out
 
@@ -116,6 +118,98 @@
     return False
 
 
+#: Адаптер ЛІГИ (4d-4a: ЛИШЕ тут, для міграції): останній рубіж кореня, перелік id, дефолт і підписи.
+_FALLBACK_ROOT = '~/deai-work'
+_LEGACY_IDS = ('united', 'liga360', 'seo')
+_LEGACY_DEFAULT = 'united'
+_LEGACY_LABELS = {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO'}
+
+
+def _legacy_of_task(task):
+    """Старе читання напрямку задачі: `track`, інакше `profile` (лише міграція: `tracks.of_task` читає один `track`)."""
+    if not isinstance(task, dict):
+        return None
+    for key in ('track', 'profile'):
+        v = task.get(key)
+        if isinstance(v, str) and v:
+            return v
+    return None
+
+
+def _legacy_label(value):
+    return tracks_core.read_tag(_LEGACY_LABELS.get(value, value))
+
+
+# ── адаптер ЛІГИ: корінь старого `tasks.json` → напрямки ──────────────────────────────────────────────────────────────
+
+def _legacy_roots_of(cfg):
+    """`design_work_roots` ЛІГИ. ⛔ Не словник → `{}` (0.14.0 тут падав `AttributeError`; свідома відмінність спеки §6.4: спільний
+    корінь замість обвалу)."""
+    raw = cfg.get('design_work_roots') if isinstance(cfg, dict) else None
+    return raw if isinstance(raw, dict) else {}
+
+
+def _legacy_fallback(cfg):
+    shared = cfg.get('design_work_root') if isinstance(cfg, dict) else None
+    return os.path.expanduser(shared if isinstance(shared, str) and shared else _FALLBACK_ROOT)
+
+
+def _legacy_root(cfg, value):
+    """Корінь робочих тек ДЛЯ ЦЬОГО НАПРЯМКУ ЛІГИ (раніше `serve.work_root(cfg, profile)`), з розгорнутим `~`.
+
+    Вимога користувача 31.08.2026: три напрямки — три теки і три репозиторії. Порядок: свій корінь напрямку →
+    спільний `design_work_root` → історичний фолбек. ⛔ Напрямок без власного кореня НЕ вигадується (і не береться з
+    дефолтного): краще чесно покласти в спільний корінь і сказати про це (`bin/roots.py`), ніж створити теку за вигаданим
+    шляхом. `value` — що завгодно (`'United'`, `''`, число, `None`): невідоме — спільний корінь. Не кидає на поганому `cfg`.
+
+    Свідома відмінність від 0.14.0: НЕ рядок у власному корені напрямку чи в `design_work_root` (число, список) раніше
+    давав `TypeError` у `expanduser` (500); тепер таке значення вважається відсутнім і діє наступна ланка ланцюга
+    (власний → спільний → `~/deai-work`)."""
+    own = _legacy_roots_of(cfg).get(value) if isinstance(value, str) else None
+    if isinstance(own, str) and own:
+        return os.path.expanduser(own)
+    return _legacy_fallback(cfg)
+
+
+def _legacy_repos(cfg):
+    """Таблиця «напрямок → репозиторій макетів» ЛІГИ з кореня `tasks.json` (раніше `serve.profile_repos` без читання файла).
+    Ключ — за `ID_RE`, репо — `repo_ok` (обрізане); погані пари відкидаються, `cfg` не словник / ключа нема / не словник —
+    `{}`. ⛔ Структура в усіх напрямків одна — `mockup/<task-id>`, тому напрямки розходяться лише репозиторієм, а не логікою
+    (урок колишньої константи `PROFILE_REPOS`). Значень — ні в текстах, ні в журналах."""
+    raw = cfg.get('profile_repos') if isinstance(cfg, dict) else None
+    if not isinstance(raw, dict):
+        return {}
+    out = {}
+    for k, v in raw.items():
+        r = tracks_core.repo_ok(v)
+        if r and tracks_core._is_id(k):
+            out[k] = r
+    return out
+
+
+def _legacy_tracks(cfg):
+    """Неявні напрямки ЛІГИ → `(tracks, default_id, fallback_root)`.
+
+    Перелік id: `united`, `liga360`, `seo`, далі ключі `design_work_roots` і `profile_repos` (лише за `ID_RE`, у такому
+    порядку, без дублів). `root` — `_legacy_root` (свій → спільний → `~/deai-work`, розгорнутий); `repo` — з `_legacy_repos`
+    або `''`; `label` — `_LEGACY_LABELS` або `id`; `ds` = `id` (вендорний інспектор сам каже «ДС нема» для невідомого);
+    дефолт — `united`. `fallback_root` — корінь для будь-якого значення поза переліком (`'United'`, невідомий, `None`):
+    не корінь дефолтного напрямку (спека §6.1). Перелік не обмежений `MAX_TRACKS`: адаптер дзеркалить довільний конфіг, а
+    репо 21-го ключа 0.14.0 теж віддавав. Не кидає на поганому `cfg`."""
+    ids = list(_LEGACY_IDS)
+    seen = set(ids)
+    raw_repos = cfg.get('profile_repos') if isinstance(cfg, dict) else None
+    for src in (_legacy_roots_of(cfg), raw_repos if isinstance(raw_repos, dict) else {}):
+        for k in src:
+            if tracks_core._is_id(k) and k not in seen:
+                seen.add(k)
+                ids.append(k)
+    repos = _legacy_repos(cfg)
+    tracks = [{'id': i, 'label': _LEGACY_LABELS.get(i, i), 'root': _legacy_root(cfg, i),
+               'repo': repos.get(i, ''), 'ds': i} for i in ids]
+    return tracks, _LEGACY_DEFAULT, _legacy_fallback(cfg)
+
+
 def _foreign_dropped(root, others):
     """Так само, як `serve._drop_foreign_roots`: корінь, що перетинається з ІНШИМ простором реєстру, у явних напрямках стає
     `None` (в адаптері ЛІГИ він лишився б). `others` — реєстр без запису ЛІГИ."""
@@ -126,18 +220,32 @@
     return why is not None
 
 
-def _compute_tracks(cfg, path, others):
-    """Явні напрямки з адаптера + перевірка паритету → `(список для space.json, нормалізований, дефолт)` чи `None` (паритету нема)."""
-    items, default, _fallback = tracks_core.legacy_tracks(cfg)
+def _adapter_tracks(cfg, path, others):
+    """Явні напрямки з адаптера БЕЗ воріт паритету → `(список для space.json, нормалізований, дефолт, нотатки-про-корені)`.
+    `нотатки-про-корені` — `root-dropped:<id>` (корінь відкинув `normalize` чи перетин з іншим простором) і `root-rebased:<id>`
+    (відносний корінь став відносним до теки простору)."""
+    items, default, _fallback = _legacy_tracks(cfg)
     raw = [{'id': t['id'], 'label': t['label'], 'root': t['root'], 'repo': t['repo'], 'ds': t['ds']} for t in items]
     norm = tracks_core.normalize(raw, path)
     norm = [{**t, 'root': None} if t['root'] is not None and _foreign_dropped(t['root'], others) else t for t in norm]
+    notes = []
+    for a in items:
+        n = tracks_core.find(norm, a['id'])
+        if n is not None and n['root'] != os.path.normpath(a['root']):
+            notes.append(('root-dropped:' if n['root'] is None else 'root-rebased:') + a['id'])
+    return raw, norm, default, notes
+
+
+def _compute_tracks(cfg, path, others):
+    """4d-3a: явні напрямки + ВОРОТА паритету → `(список для space.json, нормалізований, дефолт)` чи `None` (паритету нема)."""
+    raw, norm, default, _notes_roots = _adapter_tracks(cfg, path, others)
+    items = _legacy_tracks(cfg)[0]
     if tracks_core.default_id(norm, default) != default:
         return None
     for a in items:
         n = tracks_core.find(norm, a['id'])
         if (n is None or n['root'] != os.path.normpath(a['root']) or n['repo'] != a['repo'] or n['ds'] != a['ds']
-                or n['label'] != tracks_core.label_tag([], {'track': a['id']}, legacy=True)):
+                or n['label'] != _legacy_label(a['id'])):
             return None
     return raw, norm, default
 
@@ -154,12 +262,44 @@
             return True
     tasks = cfg.get('tasks') if isinstance(cfg, dict) else None
     for t in (tasks.values() if isinstance(tasks, dict) else ()):
-        if isinstance(t, dict) and tracks_core.of_task(t) not in ids:
+        if isinstance(t, dict) and _legacy_of_task(t) not in ids:
             return True
     default = tracks_core.find(norm, 'united')
-    return default is None or default['root'] != os.path.normpath(tracks_core.legacy_root(cfg, None))
+    return default is None or default['root'] != os.path.normpath(_legacy_root(cfg, None))
+
+
+def _nonempty_str(v):
+    return isinstance(v, str) and bool(v)
+
+
+def _notes(cfg, ids, norm, root_notes):
+    """Нотатки четвертого кроку (коди без шляхів і значень; id напрямків — можна), у порядку: корені, `unknown-values`,
+    `default-root-differs`, `non-id-keys`. `unknown-values` — задача зі значенням напрямку (`_legacy_of_task`), якого нема в
+    переліку (задачі БЕЗ значення нотатки не дають: мітка й ДС у них і так порожні)."""
+    notes = list(root_notes)
+    tasks = cfg.get('tasks') if isinstance(cfg, dict) else None
+    if any(isinstance(t, dict) and _legacy_of_task(t) is not None and _legacy_of_task(t) not in ids
+           for t in (tasks.values() if isinstance(tasks, dict) else ())):
+        notes.append('unknown-values')
+    default = tracks_core.find(norm, 'united')
+    if default is None or default['root'] != os.path.normpath(_legacy_root(cfg, None)):
+        notes.append('default-root-differs')
+    for key in ('design_work_roots', 'profile_repos'):
+        raw = cfg.get(key) if isinstance(cfg, dict) else None
+        if isinstance(raw, dict) and any(not tracks_core._is_id(k) for k in raw):
+            notes.append('non-id-keys')
+            break
+    return notes
 
 
+def _records_to_fix(cfg):
+    """Ідентифікатори задач ЛІГИ, у яких `track` — не непорожній рядок, а `profile` — непорожній: їм крок пише `track = profile`
+    (старий запис до 0.15.0 мав лише `profile`; після 4d-4a `tracks.of_task` читає один `track`)."""
+    tasks = cfg.get('tasks') if isinstance(cfg, dict) else None
+    return sorted(tid for tid, t in (tasks.items() if isinstance(tasks, dict) else ())
+                  if isinstance(t, dict) and not _nonempty_str(t.get('track')) and _nonempty_str(t.get('profile')))
+
+
 def _has_userinfo(url):
     """Адреса з `userinfo` (`user:pass@хост`): такий рядок не мігрує — облікові лежали б у `space.json` відкритим текстом."""
     try:
@@ -319,9 +459,21 @@
                 secrets[mid] = secret
     out_roles = {r: {'module': m, 'migrate': skip is None, 'reason': skip} for r, (m, skip, _e, _s) in roles.items()}
 
-    do_tracks, tracks_reason, new_tracks = False, None, None
-    if not step.tracks:                                     # напрямки мігрує лише 4d-3a
+    do_tracks, tracks_reason, new_tracks, notes = False, None, None, []
+    records = _records_to_fix(cfg) if step.ungated else []
+    if not step.tracks:                                     # напрямки мігрують лише 4d-3a і 4d-4a
         pass
+    elif step.ungated:                                      # 4d-4a: рівно тоді, коли ЗАРАЗ діє адаптер (та сама функція, що в рантаймі)
+        if not tracks_core.adapter_applies(data.get('tracks'), path):
+            tracks_reason = 'tracks-present'
+        else:
+            others = {'spaces': [s for s in reg['spaces'] if s.get('id') != sid]}
+            raw, norm, default, root_notes = _adapter_tracks(cfg, path, others)
+            chk = tracks_core.normalize(raw, path, roots=False)          # перевірка В ПАМʼЯТІ: ті самі id і дефолт, що адаптер
+            if [x['id'] for x in chk] != [x['id'] for x in raw] or tracks_core.default_id(chk, default) != default:
+                raise _Stop('abort-tracks', space_id=sid)
+            do_tracks, new_tracks = True, (raw, default)
+            notes = _notes(cfg, {x['id'] for x in raw}, norm, root_notes)
     elif data.get('tracks') is not None:                    # навіть `[]`: власник свідомо обрав «жодного напрямку»
         tracks_reason = 'tracks-present'
     else:
@@ -336,7 +488,7 @@
             else:
                 do_tracks, new_tracks = True, (raw, default)
 
-    if not do_tracks and not any(skip is None for (_m, skip, _e, _s) in roles.values()):
+    if not do_tracks and not records and not any(skip is None for (_m, skip, _e, _s) in roles.values()):
         raise _Stop('skip-nothing', space_id=sid, roles=out_roles, tracks_reason=tracks_reason)
 
     # Перевірка В ПАМʼЯТІ: ядро вирішує кожну мігровану роль саме цим модулем на розрахованому `space.json` (нічого не пишемо).
@@ -358,11 +510,13 @@
         space_json['tracks'], space_json['default_track'] = new_tracks
     marks = dict(mig) if isinstance(mig, dict) else {}
     marks[step.mark] = {'roles': [r for r, (_m, skip, _e, _s) in roles.items() if skip is None]}
-    if step.tracks:                                         # позначка 4d-3b — без `tracks`
+    if step.tracks:                                         # позначка 4d-3b/3c — без `tracks`
         marks[step.mark]['tracks'] = do_tracks
+    if step.ungated:
+        marks[step.mark]['records'], marks[step.mark]['notes'] = len(records), notes
     space_json['migrations'] = marks
     return _result('ready', space_id=sid, space_path=path, roles=out_roles, tracks=do_tracks, tracks_reason=tracks_reason,
-                   space_json=space_json, secrets=secrets)
+                   space_json=space_json, secrets=secrets, records=records, notes=notes)
 
 
 def report(p, step=None):
@@ -376,6 +530,8 @@
     if p.get('status') == 'ready':
         if _step(step).tracks:
             lines.append('  tracks: ' + ('migrate' if p.get('tracks') else 'skip: ' + str(p.get('tracks_reason'))))
+        if _step(step).ungated:
+            lines.append('  records: %d; notes: %s' % (len(p.get('records') or []), ', '.join(p.get('notes') or []) or '-'))
         for mid, sec in (p.get('secrets') or {}).items():
             lines.append('  secrets %s: %s' % (mid, ', '.join(sorted(sec)) or '-'))
     return '\n'.join(lines)
@@ -394,14 +550,17 @@
 #: `roles` — `((роль, модуль), …)` у порядку запису; `tracks` — чи мігрує напрямки (лише 4d-3a); `suffix` — хвіст імені бекапу;
 #: `stamp_re` — строге імʼя бекапу (імʼя однозначно каже, чий це крок); `entries(cfg, present)` — розрахунок ролей кроку
 #: (`None` = `_role_entries`, 4d-3a; `_entries_b` додає Task 6). `hold` кроку — це `{held: True}` у ЙОГО позначці.
-Step = namedtuple('Step', 'mark roles tracks suffix stamp_re entries', defaults=(None,))
+Step = namedtuple('Step', 'mark roles tracks suffix stamp_re entries ungated', defaults=(None, False))
 STEP_A = Step(MARK, ROLE_MODULES, True, BACKUP_SUFFIX, STAMP_RE)
 #: Другий крок (4d-3b, 0.18.0): `comments` і `vcs` ЛІГИ — явні модулі; без напрямків (`tracks=False`), свій бекап і позначка без `tracks`.
 STEP_B = Step('liga-4d3b', ROLE_MODULES_B, False, '-liga-4d3b', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3b(?:-[0-9]{1,3})?'), _entries_b)
 #: Усі відомі кроки в порядку застосування (відкат — у зворотному: LIFO) і ті, що біжать на старті/в CLI.
 #: Третій крок (4d-3c, 0.19.0): `publish` ЛІГИ — явний `vercel-publish` з `compat`; без напрямків і секретів, свій бекап і позначка.
 STEP_C = Step('liga-4d3c', ROLE_MODULES_C, False, '-liga-4d3c', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d3c(?:-[0-9]{1,3})?'), _entries_c)
-ALL_STEPS = (STEP_A, STEP_B, STEP_C)
+#: Четвертий крок (4d-4a, 0.20.0): напрямки ЛІГИ — остаточно явні (БЕЗ воріт паритету, розбіжності — нотатки позначки) і записи задач
+#: (`track = profile`). Ролей нема; `ungated=True` — крок без воріт паритету й з записом `tasks.json`.
+STEP_D = Step('liga-4d4a', (), True, '-liga-4d4a', re.compile(r'[0-9]{8}-[0-9]{6}-liga-4d4a(?:-[0-9]{1,3})?'), lambda cfg, present: {}, True)
+ALL_STEPS = (STEP_A, STEP_B, STEP_C, STEP_D)
 STEPS = ALL_STEPS
 
 
@@ -487,7 +646,8 @@
     out = {'status': p.get('status'), 'reason': p.get('reason') or '', 'space_id': p.get('space_id'),
            'roles': [r for r, v in (p.get('roles') or {}).items() if v.get('migrate')],
            'skipped': {r: v.get('reason') for r, v in (p.get('roles') or {}).items() if not v.get('migrate')},
-           'tracks': bool(p.get('tracks')), 'tracks_reason': p.get('tracks_reason')}
+           'tracks': bool(p.get('tracks')), 'tracks_reason': p.get('tracks_reason'),
+           'records': len(p.get('records') or []), 'notes': list(p.get('notes') or [])}
     if p.get('status') in _HINTS:
         out['hint'] = _HINTS[p['status']]
     out.update(extra)
@@ -641,7 +801,7 @@
     return name
 
 
-def _commit_space(space_path, p, stamp, step=None):
+def _commit_space(space_path, p, stamp, step=None, records=None):
     """ОДИН атомарний запис `space.json`: злиття з ПОТОЧНИМ вмістом диска (перечитуємо під замком, відразу перед записом): чужі
     ключі й правки, зроблені після `plan()`, не губляться. Модуль, що зʼявився тим часом, не перезаписуємо. Позначка вже є — `skip-done`."""
     step = _step(step)
@@ -659,12 +819,35 @@
                 mods[r['module']] = planned['modules'][r['module']]
         new = dict(cur)
         new['modules'] = mods
-        if step.tracks and p['tracks'] and cur.get('tracks') is None:
+        wrote = False
+        if step.tracks and p['tracks'] and (tracks_core.adapter_applies(cur.get('tracks'), space_path) if step.ungated else cur.get('tracks') is None):
             new['tracks'], new['default_track'] = planned['tracks'], planned['default_track']
+            wrote = True
         marks[step.mark] = dict(planned['migrations'][step.mark], at=time.strftime('%Y-%m-%dT%H:%M:%S'), backup=stamp)
+        if step.ungated:                                    # 4d-4a: позначка каже, що крок записав НАСПРАВДІ (власні напрямки, що зʼявились, не затираємо)
+            marks[step.mark]['tracks'], marks[step.mark]['records'] = wrote, records
         new['migrations'] = marks
         _write_space(sp, new)
     return 'done'
+
+
+def _commit_records(p, step):
+    """4d-4a: `track = profile` у записах задач ЛІГИ (файл задач ЛІГИ — `install_config.legacy_tasks_path()`, той самий, що читав
+    `plan`). Файл ПЕРЕЧИТУЄМО під `WRITE_LOCK` відразу перед записом (задача, додана після `plan()`, теж виправляється; чужі правки не
+    губляться), `.bak` — як `serve.save_tasks`. Повертає кількість записаних записів; не кидає лише коли писати нічого. Крок
+    без `ungated` чи без записів — `0` без дотику до диска."""
+    if not step.ungated or not p.get('records'):
+        return 0
+    path = install_config.legacy_tasks_path()
+    with spaces.WRITE_LOCK:
+        cfg = install_config.load_legacy_tasks()
+        todo = _records_to_fix(cfg)
+        for tid in todo:
+            cfg['tasks'][tid]['track'] = cfg['tasks'][tid]['profile']
+        if todo:
+            shutil.copy2(path, path + '.bak')
+            atomic_write_json(path, cfg)
+    return len(todo)
 
 
 def _run(home, step=None):
@@ -728,12 +911,20 @@
             _write_last(info, step)
             return 'abort-secrets', info
         try:
-            st = _commit_space(space_path, p, stamp, step)
+            n_records = _commit_records(p, step)
+        except (OSError, ValueError, RecursionError, KeyError, TypeError):
+            info = _info(p, status='abort-records', reason=_REASONS['abort-records'], backup=stamp)
+            _write_last(info, step)
+            return 'abort-records', info
+        try:
+            st = _commit_space(space_path, p, stamp, step, n_records if step.ungated else None)
         except (OSError, ValueError, deai_modules.ModuleError):
             info = _info(p, status='abort-write', reason=_RUN_REASONS['abort-write'], backup=stamp)
             _write_last(info, step)
             return 'abort-write', info
         info = _info(p, status=st, reason=_RUN_REASONS.get(st) or _REASONS.get(st, ''), backup=stamp)
+        if step.ungated:
+            info['records'] = n_records
         if st == 'done':
             info['secrets'] = {m: sorted(s) for m, s in p['secrets'].items()}      # лише імена ключів
             _write_last(info, step)
```

  і до `app/tracks.py` додати (поруч з `normalize`):

```python
def adapter_applies(raw, path):
    """Чи діє адаптер ЛІГИ: напрямків у `space.json` нема (`None`) або список непридатний (`normalize` дає порожнє).
    Єдиний критерій для рантайму (до 4d-4a) і для кроку `liga-4d4a`; ⛔ не дублювати умову в інших місцях."""
    return raw is None or not normalize(raw, path, roots=False)
```

  а в `serve._TrackView.adapter` замінити власну умову викликом `tracks.adapter_applies(raw, path)`.
- [ ] **Step 3 (піни 4d-3c, Поправка 10):** у `tests/test_liga_migrate_c.py` — `_StepC.STEPS = ALL_STEPS[:3]`, тести розпаковки/рівності `ALL_STEPS` ≈819–840 → `ALL_STEPS[:3]` + новий тест «четвертий — `liga-4d4a`»; стенди паритету й старту — піни `mock.patch.object(lm, 'STEPS', lm.ALL_STEPS[:3])`; ту саму правку — у `tests/test_liga_migrate.py::AfterMigrationParity` і `…_b.py::AfterMigrationParity4d3b` (`_build` запускає D або очікування змінено — рішення виконавця, але в звіті одним рядком). Кожен пін — доведено мутацією (прибрати пін → червоніє названий тест).
- [ ] **Step 4:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_d tests.test_liga_migrate tests.test_liga_migrate_b tests.test_liga_migrate_c` під `python3` і `/usr/bin/python3` → зелено (крім `test_the_view_asks_the_same_function`, якщо вже видалено адаптер — у Task 2 він ще зелений).
- [ ] **Step 5:** коміт `feat(4d-4a): крок liga-4d4a — явні напрямки й track у записах` — шляхи: `app/liga_migrate.py app/tracks.py app/serve.py tests/test_liga_migrate_d.py tests/test_liga_migrate_c.py tests/test_liga_migrate.py tests/test_liga_migrate_b.py`.

---
### Task 3: вивід кроку, `status`, CLI, LIFO на чотири кроки

**Files:** `app/liga_migrate.py` (hunks 16–end), `bin/migrate_liga.py`, `tests/test_liga_migrate_d.py` (`LifoFourSteps`, `FourStepsStartup`).

**Рішення:**

- `summary_line(info)` → `напрямки: записано | вже явні | не змінено (<reason>); записи: N; нотатки: a, b`. «вже явні» — коли причина `tracks-present` (крок A уже записав напрямки: типовий випадок на чистій ЛІЗІ).
- `TRACKS_NOT_MIGRATED = 'напрямки ЛІГИ не мігровані — нові задачі лягають у теку простору'` друкується для D, коли статус не з `TRACKS_QUIET` (`done`, `skip-layer-off`, `skip-no-liga`, `skip-done`, `skip-nothing`, `skip-integrations-off`, `skip-busy`), і лише там, де `announce` уже друкує (старт; CLI `run`). `skip-held`, `skip-path-in-git`, `abort-*` — друкують.
- `status()` → ключі позначки `records`, `notes`; `status_text` для `ungated` додає `, записи: N, нотатки: …`; `report()` — `records: N; notes: …`; `_info` — `records` (кількість), `notes`.
- CLI `run`: для D друкується `summary_line` + бекап; `stamps_done.append` — у гілці `if st == 'done'` (НЕ в `elif`); `elif step.ungated and tracks_not_migrated(st)` друкує `TRACKS_NOT_MIGRATED`.
- LIFO: `_applied_later` ітерує `reversed(ALL_STEPS[idx+1:])` — на чотирьох кроках `restore <a>` вимагає спершу відкату d, c, b (ця поведінка — вже коректна; тест доводить).
- ⛔ `restore` повертає `space.json`, не `tasks.json` (Поправка 1): текст підказки відкату й CHANGELOG — відповідно.

- [ ] **Step 1 (червоне):** класи `LifoFourSteps`, `FourStepsStartup` з повного тексту нижче.
- [ ] **Step 2 (зелене):** hunks 16–кінець `app/liga_migrate.py`:

```diff
--- a/app/liga_migrate.py
+++ b/app/liga_migrate.py
@@ -981,7 +1172,7 @@
             mig = data.get('migrations')
             for key in marks:
                 mark = mig.get(key) if isinstance(mig, dict) else None
-                marks[key] = ({k: mark[k] for k in ('at', 'roles', 'tracks', 'backup', 'held') if k in mark}
+                marks[key] = ({k: mark[k] for k in ('at', 'roles', 'tracks', 'records', 'notes', 'backup', 'held') if k in mark}
                               if isinstance(mark, dict) else None)
             out['mark'] = marks.get(_step(None).mark)
         except deai_modules.ModuleError:
@@ -1011,6 +1202,8 @@
                 lines.append('  позначка: вимкнено вручну (held)')
             else:
                 tr = (', напрямки: ' + ('так' if m.get('tracks') else 'ні')) if _step(key).tracks else ''     # рядок напрямків — лише кроку з напрямками
+                if _step(key).ungated:
+                    tr += ', записи: %s, нотатки: %s' % (m.get('records', 0), ', '.join(m.get('notes') or []) or '-')
                 lines.append('  позначка: %s, ролі: %s%s, бекап: %s' % (
                     m.get('at'), ', '.join(m.get('roles') or []) or '-', tr, m.get('backup')))
         rep = ((last or {}).get('steps') or {}).get(key) if multi and isinstance(last, dict) else last   # звіт ЦЬОГО кроку
@@ -1028,6 +1221,33 @@
     return '\n'.join(lines)
 
 
+#: Рядок для старту й CLI, коли напрямки ЛІГИ НЕ мігровано (крок 4d-4a пропущено чи не вдався): що бачитиме людина.
+TRACKS_NOT_MIGRATED = 'напрямки ЛІГИ не мігровані — нові задачі лягають у теку простору'
+
+
+#: Статуси кроку 4d-4a, після яких про «напрямки не мігровані» мовчимо: нічого не зламано, або кроку тут нема, або він уже виконаний.
+TRACKS_QUIET = ('done', 'skip-layer-off', 'skip-no-liga', 'skip-done', 'skip-nothing', 'skip-integrations-off', 'skip-busy')
+
+
+def tracks_not_migrated(status):
+    """Чи казати людині «напрямки ЛІГИ не мігровані» після цього статусу кроку 4d-4a (held, пропуски, `abort-*`)."""
+    return status not in TRACKS_QUIET
+
+
+def summary_line(info):
+    """Підсумок кроку 4d-4a для старту й CLI: `напрямки: записано|вже явні; записи: N; нотатки: a, b` (нотатки — коди без шляхів)."""
+    if info.get('tracks'):
+        head = 'записано'
+    else:
+        head = 'вже явні' if info.get('tracks_reason') == 'tracks-present' else 'не змінено (%s)' % (info.get('tracks_reason') or '-')
+    parts = ['напрямки: ' + head]
+    if info.get('records'):
+        parts.append('записи: %d' % info['records'])
+    if info.get('notes'):
+        parts.append('нотатки: ' + ', '.join(info['notes']))
+    return '; '.join(parts)
+
+
 def _skip_lines(last):
     """Рядки ПОСТІЙНОГО пропуску (`skip` у `last.json`, напр. тека простору в git) — одні на всі кроки."""
     lines = []
@@ -1060,7 +1280,7 @@
     (імʼя типу, без значень) і в `last.json`. Повертає статус чи `None`. Кроки `STEPS` — по порядку (`run_all`): `abort-*` і `skip-busy`
     зупиняють наступні на цьому старті; `held` раннього кроку теж тримає наступні (їхній `plan` — `skip-held`); решта `skip-*`
     (`skip-nothing`/`skip-done`/…) наступних не блокує. Повертає статус ПЕРШОГО кроку, що не `skip-*` (найважливіше), інакше — першого кроку."""
-    done, hints = [], set()
+    done, hints, hints_tracks = [], set(), []
     try:
         if implicit.isolated():
             if os.environ.get('DC_MIGRATE_LIGA') != '1':
@@ -1073,6 +1293,8 @@
 
         def announce(mark, st, info):
             done.append(st)
+            if mark == STEP_D.mark and tracks_not_migrated(st):             # 4d-4a: що буде з напрямками, коли крок не виконано
+                hints_tracks.append(TRACKS_NOT_MIGRATED)
             if st not in ('skip-layer-off', 'skip-done', 'skip-integrations-off') and not st.startswith('skip-no'):
                 print('%s: %s — %s' % (mark, st, info.get('reason') or ''), file=sys.stderr)
                 if info.get('hint') and info['hint'] not in hints:           # однакова підказка (тека в git) — раз на старт
@@ -1084,12 +1306,16 @@
                 if st == 'done' and step_of_stamp(stamp):                    # лише імʼя бекапу (без шляху до дому)
                     stamps_done.append(stamp)
                     print('  бекап: %s' % stamp, file=sys.stderr)
+                if mark == STEP_D.mark and st == 'done':                     # 4d-4a: що людина бачитиме (нотатки)
+                    print('  ' + summary_line(info), file=sys.stderr)
                 skipped = info.get('skipped')
                 if isinstance(skipped, dict) and skipped:
                     print('  не мігровано: ' + ', '.join('%s (%s)' % (r, c) for r, c in sorted(skipped.items())), file=sys.stderr)
         try:
             run_all(None, on_result=announce)
         finally:
+            for line in hints_tracks:                                       # після рядка статусу кроку (він друкується в `announce`)
+                print('  ' + line, file=sys.stderr)
             # ⛔ LIFO: підказка відкату — ОДНА, для найпізнішого виконаного кроку (відкат раннього при застосованому пізнішому — відмова).
             if stamps_done:
                 print('  відкат: bin/migrate_liga.py restore %s --hold' % stamps_done[-1], file=sys.stderr)
```

  і `bin/migrate_liga.py`:

```diff
--- a/bin/migrate_liga.py
+++ b/bin/migrate_liga.py
@@ -46,9 +46,14 @@
             if info.get('hint'):
                 print('  що робити: ' + str(info['hint']))
             if st == 'done':
-                tr = ('; напрямки: ' + ('так' if info.get('tracks') else 'ні')) if step.tracks else ''     # лише крок з напрямками
-                print('  ролі: %s%s; бекап: %s' % (', '.join(info.get('roles') or []) or '-', tr, info.get('backup')))
+                if step.ungated:                                         # 4d-4a: ролей нема — підсумок напрямків, записів і нотаток
+                    print('  %s; бекап: %s' % (liga_migrate.summary_line(info), info.get('backup')))
+                else:
+                    tr = ('; напрямки: ' + ('так' if info.get('tracks') else 'ні')) if step.tracks else ''     # лише крок з напрямками
+                    print('  ролі: %s%s; бекап: %s' % (', '.join(info.get('roles') or []) or '-', tr, info.get('backup')))
                 stamps_done.append(info.get('backup'))
+            elif step.ungated and liga_migrate.tracks_not_migrated(st):
+                print('  ' + liga_migrate.TRACKS_NOT_MIGRATED)
             if st not in liga_migrate.BENIGN:
                 code = 1
             if st.startswith('abort-') or st == 'skip-busy':     # як на старті: `abort-*`/`skip-busy` зупиняють наступні кроки
```

- [ ] **Step 3:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_liga_migrate_d` → зелено, крім `test_the_view_asks_the_same_function` (до Task 4 зелений; з Task 4 — видалити, його замінює охоронець).
- [ ] **Step 4:** коміт `feat(4d-4a): вивід, status і CLI кроку d; LIFO на чотири кроки`.

---
### Task 4: рантайм без адаптера + охоронець `NoTracksAdapter`

**Files:** `app/tracks.py`, `app/serve.py`, `bin/registry.py`, `bin/roots.py` (повний diff нижче — застосовується ОДНИМ кроком: `tracks.legacy_*` прибрано, тож усі викликачі міняються разом), `tests/test_no_adapter.py` (новий), `tests/test_liga_adapter.py` (новий), `tests/test_liga_migrate_d.py` (видалити `test_the_view_asks_the_same_function`).

**Рішення (з прототипу):**

- З `tracks.py` зникають: `FALLBACK_ROOT`, `_LEGACY_*`, `legacy_*`, параметр `label_tag(legacy=)`. `of_task(task)` читає ЛИШЕ `track`. `label_tag(tracks, task)`.
- З `serve.py` зникають: `profile_repos` (`:112`), `_legacy_cfg`, `_TrackView.adapter` (`:1764`) і всі гілки «адаптер»; `track_root(sp, track_id)` без `cfg`: корінь знайденого напрямку → корінь дефолтного → шлях простору → `None`.
- Нове в `serve.py`: `DEFAULT_TASK_ROOT = '~/deai-work'` і `default_task_root(cfg)` (спільний `design_work_root` із cfg, інакше `DEFAULT_TASK_ROOT`, з розгорнутим `~`); `task_new` бере `root or default_task_root(cfg)`; обробник — `track_root(view, track) or default_task_root(cfg)`.
- `bin/registry.py`: `_track_of_entry(e)` = `track`, інакше `profile` — ЄДИНА межа; `_work_root` шукає простір реєстру з `legacy is True`; `status` by_track — через `_track_of_entry`; `SHARED` не змінюється.
- `bin/roots.py`: `view`-параметр (Поправка 12).
- Охоронець — AST (код нижче). Прототип дав єдину помилкову спрацьовку — голе імʼя `adapter` у `serve.py` (локальна змінна); правило звужене до `Attribute.attr == 'adapter'` і `def adapter`.
- Адаптерні тести `test_tracks.py` (`LegacyTracks`, `LegacyParity`, legacy-мітки) переносяться в `tests/test_liga_adapter.py` на `liga_migrate._legacy_*`.

- [ ] **Step 1 (червоне):** `tests/test_no_adapter.py` з кодом охоронця (нижче) + `test_the_guard_can_fail`. Червоніє на `app/`.
- [ ] **Step 2 (зелене):** diff `tracks.py`:

```diff
--- a/app/tracks.py
+++ b/app/tracks.py
@@ -33,14 +33,6 @@
 #: U+FEFF) і двоспрямовані керування (U+202A–U+202E, U+2066–U+2069): мітка з U+202E виглядала б не тим, чим є.
 TAG_BAD = re.compile('[\\x00-\\x1f\\x7f-\\x9f,\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]')
 TAG_MAX_LEN = 32
-#: Останній рубіж кореня задач ЛІГИ, коли в `tasks.json` нема нічого. Історична тека United — саме тому вона й муляє: у ній
-#: лежали задачі всіх трьох напрямків.
-FALLBACK_ROOT = '~/deai-work'
-#: Напрямки ЛІГИ, що є завжди (порядок = порядок переліку адаптера) і дефолт для задачі без напрямку.
-_LEGACY_IDS = ('united', 'liga360', 'seo')
-_LEGACY_DEFAULT = 'united'
-#: Підписи адаптера ЛІГИ (раніше `serve._LEGACY_PROFILE_TAGS`): невідомий напрямок показується як є. Піде в 4d-3.
-_LEGACY_LABELS = {'united': 'United', 'liga360': 'LIGA360', 'seo': 'SEO'}
 #: Керівні знаки в шляху `root`: NUL ламає `realpath`, решта — явне сміття.
 _PATH_BAD = re.compile('[\\x00-\\x1f\\x7f]')
 #: Найдовший `root` у `space.json` (знаків); довший вважається відсутнім. `spaces` власної межі шляху не має.
@@ -147,16 +139,12 @@
 
 
 def of_task(task):
-    """Напрямок задачі — збережений РЯДОК: `track`, інакше `profile` (синонім до 4d-4). Без звірки з `ID_RE`: ЛІГА приймає
-    будь-який рядок як є (`'United'` теж, як 0.14.0), а перевірка шаблону — справа того місця, що читає (звичайний простір,
-    `?ds=`). Не словник, не рядок чи порожній — `None`; порожній/не рядок `track` не затуляє валідний `profile`."""
+    """Напрямок задачі — збережений РЯДОК `track` (4d-4a: `profile` з записів більше не читається). Без звірки з `ID_RE`:
+    значення вільне, перевірка шаблону — справа того, хто читає. Не словник, не рядок чи порожній — `None`."""
     if not isinstance(task, dict):
         return None
-    for key in ('track', 'profile'):
-        v = task.get(key)
-        if isinstance(v, str) and v:
-            return v
-    return None
+    v = task.get('track')
+    return v if isinstance(v, str) and v else None
 
 
 def find(tracks, tid):
@@ -169,90 +157,18 @@
     return None
 
 
-def label_tag(tracks, task, legacy=False):
-    """Похідна мітка задачі (рядок) або `None`; список `[tag]` / `[]` складає той, хто кличе (`serve.task_tags`).
-
-    Звичайний простір: напрямок знайдено → його `label`; не знайдено, але id є → сам id (паритет «невідомий — як є»). ЛІГА
-    (`legacy=True`, неявний адаптер): значення — вільний рядок, не обовʼязково з переліку, тож береться `_LEGACY_LABELS.get(v,
-    v)` без звірки з `tracks`. Обидва шляхи проходять ті самі правила мітки (`read_tag`): ⛔ діалог правки заповнюється
-    поточними мітками, і значення з комою чи на 300 знаків після збереження розпалося б або не пройшло `bad-tags`; такий
-    напрямок — без похідної мітки."""
+def label_tag(tracks, task):
+    """Похідна мітка задачі або `None`: знайдений напрямок → його `label`; не знайдений, але значення є → воно саме
+    (`read_tag`); усе проходить правила мітки."""
     v = of_task(task)
     if v is None:
         return None
-    if legacy:
-        return read_tag(_LEGACY_LABELS.get(v, v))
     t = find(tracks, v)
     if t is None:
         return read_tag(v)
     return read_tag(t.get('label')) or read_tag(v)
 
 
-# ── адаптер ЛІГИ: корінь старого `tasks.json` → напрямки ──────────────────────────────────────────────────────────────
-
-def _legacy_roots(cfg):
-    """`design_work_roots` ЛІГИ. ⛔ Не словник → `{}` (0.14.0 тут падав `AttributeError`; свідома відмінність спеки §6.4: спільний
-    корінь замість обвалу)."""
-    raw = cfg.get('design_work_roots') if isinstance(cfg, dict) else None
-    return raw if isinstance(raw, dict) else {}
-
-
-def _legacy_fallback(cfg):
-    shared = cfg.get('design_work_root') if isinstance(cfg, dict) else None
-    return os.path.expanduser(shared if isinstance(shared, str) and shared else FALLBACK_ROOT)
-
-
-def legacy_root(cfg, value):
-    """Корінь робочих тек ДЛЯ ЦЬОГО НАПРЯМКУ ЛІГИ (раніше `serve.work_root(cfg, profile)`), з розгорнутим `~`.
-
-    Вимога користувача 31.08.2026: три напрямки — три теки і три репозиторії. Порядок: свій корінь напрямку →
-    спільний `design_work_root` → історичний фолбек. ⛔ Напрямок без власного кореня НЕ вигадується (і не береться з
-    дефолтного): краще чесно покласти в спільний корінь і сказати про це (`bin/roots.py`), ніж створити теку за вигаданим
-    шляхом. `value` — що завгодно (`'United'`, `''`, число, `None`): невідоме — спільний корінь. Не кидає на поганому `cfg`.
-
-    Свідома відмінність від 0.14.0: НЕ рядок у власному корені напрямку чи в `design_work_root` (число, список) раніше
-    давав `TypeError` у `expanduser` (500); тепер таке значення вважається відсутнім і діє наступна ланка ланцюга
-    (власний → спільний → `~/deai-work`)."""
-    own = _legacy_roots(cfg).get(value) if isinstance(value, str) else None
-    if isinstance(own, str) and own:
-        return os.path.expanduser(own)
-    return _legacy_fallback(cfg)
-
-
-def legacy_repos(cfg):
-    """Таблиця «напрямок → репозиторій макетів» ЛІГИ з кореня `tasks.json` (раніше `serve.profile_repos` без читання файла).
-    Ключ — за `ID_RE`, репо — `repo_ok` (обрізане); погані пари відкидаються, `cfg` не словник / ключа нема / не словник —
-    `{}`. ⛔ Структура в усіх напрямків одна — `mockup/<task-id>`, тому напрямки розходяться лише репозиторієм, а не логікою
-    (урок колишньої константи `PROFILE_REPOS`). Значень — ні в текстах, ні в журналах."""
-    raw = cfg.get('profile_repos') if isinstance(cfg, dict) else None
-    if not isinstance(raw, dict):
-        return {}
-    out = {}
-    for k, v in raw.items():
-        r = repo_ok(v)
-        if r and _is_id(k):
-            out[k] = r
-    return out
-
-
-def legacy_tracks(cfg):
-    """Неявні напрямки ЛІГИ → `(tracks, default_id, fallback_root)`.
-
-    Перелік id: `united`, `liga360`, `seo`, далі ключі `design_work_roots` і `profile_repos` (лише за `ID_RE`, у такому
-    порядку, без дублів). `root` — `legacy_root` (свій → спільний → `~/deai-work`, розгорнутий); `repo` — з `legacy_repos`
-    або `''`; `label` — `_LEGACY_LABELS` або `id`; `ds` = `id` (вендорний інспектор сам каже «ДС нема» для невідомого);
-    дефолт — `united`. `fallback_root` — корінь для будь-якого значення поза переліком (`'United'`, невідомий, `None`):
-    не корінь дефолтного напрямку (спека §6.1). Перелік не обмежений `MAX_TRACKS`: адаптер дзеркалить довільний конфіг, а
-    репо 21-го ключа 0.14.0 теж віддавав. Не кидає на поганому `cfg`."""
-    ids = list(_LEGACY_IDS)
-    seen = set(ids)
-    raw_repos = cfg.get('profile_repos') if isinstance(cfg, dict) else None
-    for src in (_legacy_roots(cfg), raw_repos if isinstance(raw_repos, dict) else {}):
-        for k in src:
-            if _is_id(k) and k not in seen:
-                seen.add(k)
-                ids.append(k)
-    repos = legacy_repos(cfg)
-    tracks = [{'id': i, 'label': _LEGACY_LABELS.get(i, i), 'root': legacy_root(cfg, i),
-               'repo': repos.get(i, ''), 'ds': i} for i in ids]
-    return tracks, _LEGACY_DEFAULT, _legacy_fallback(cfg)
+def adapter_applies(raw, path):
+    """Чи діє неявний адаптер напрямків ЛІГИ на цьому `space.json` (`raw` — вміст ключа `tracks` або `None`)."""
+    return raw is None or not normalize(raw, path, roots=False)
```

  diff `serve.py`:

```diff
--- a/app/serve.py
+++ b/app/serve.py
@@ -109,13 +109,6 @@
     return install_config.supabase_config()
 
 
-def profile_repos():
-    """до 4d-4: тонка обгортка для `_liga_flow` (ознака потоку ЛІГА в тілі `task-new`), `track_repo` і тестів, що її підміняють: таблиця
-    «напрямок → репозиторій макетів» ЛІГИ з кореня старого `tasks.json` УСТАНОВКИ — `tracks.legacy_repos`. Файл не
-    читається / не JSON / ключа нема — `{}`. Кешу нема: файл маленький. Значень — ні в текстах, ні в журналах."""
-    return tracks.legacy_repos(_legacy_cfg())
-
-
 # Служебное, что НЕ копируется в итерации/публикацию из папки задачи
 SKIP = {'iterations', 'iterations.json', 'publish', 'node_modules', '.git',
         '.vercel', '.DS_Store'}
@@ -1571,12 +1564,28 @@
     """Тіло `task-new` несе ознаки потоку ЛІГА (Jira → профіль напрямку → GitLab-бутстрап):
     `jira` — непорожній (не лише пробіли) рядок, `profile` — один із `profile_repos()`, `gitlab`
     непорожній. Не-рядок у `jira`/`profile` ознакою не є (так само як порожнє й `null`)."""
-    jira, profile = payload.get('jira'), payload.get('profile')
-    return bool((isinstance(jira, str) and jira.strip())
-                or (isinstance(profile, str) and profile in profile_repos())
-                or payload.get('gitlab'))
+    jira = payload.get('jira')
+    repos = None
+    for key in ('profile', 'track'):
+        v = payload.get(key)
+        if isinstance(v, str) and v:
+            repos = _liga_track_repos() if repos is None else repos
+            if v in repos:
+                return True
+    return bool((isinstance(jira, str) and jira.strip()) or payload.get('gitlab'))
 
 
+def _liga_track_repos():
+    """Ідентифікатори напрямків простору ЛІГИ реєстру, що мають непорожній `repo` (явні `tracks` його `space.json`)."""
+    try:
+        liga = next((s for s in spaces.read_registry()['spaces'] if s.get('legacy') is True), None)
+    except spaces.SpacesError:
+        return set()
+    if liga is None:
+        return set()
+    return {t['id'] for t in _TrackView(liga).lite if t['repo']}
+
+
 def _space_id(sp):
     """Id простору для відповідей API; `None`, коли простору нема: шар вимкнено (неявний
     простір — не простір для UI, див. `spaces.describe`) чи просторів нема взагалі."""
@@ -1647,7 +1656,7 @@
     if tracks.of_task(task) is None:
         return []                                # простору й напрямків не питаємо, поки похідна мітка справді не потрібна
     view = _as_view(sp)
-    tag = tracks.label_tag([] if view.adapter else view.lite, task, legacy=view.adapter)
+    tag = tracks.label_tag(view.lite, task)
     return [tag] if tag else []
 
 
@@ -1667,15 +1676,6 @@
         return None
 
 
-def _legacy_cfg():
-    """Корінь старого `tasks.json` УСТАНОВКИ для адаптера ЛІГИ; файла нема / не читається / не JSON — `{}` (адаптер читає
-    порожній конфіг як «нічого не задано»). Надто глибока вкладеність JSON — теж не обвал."""
-    try:
-        return load_legacy_tasks()
-    except (OSError, ValueError, RecursionError):
-        return {}
-
-
 def _own_tracks(sp):
     """`(tracks, default_track)` — СИРІ значення з `space.json` простору, коли в ньому є ключ `tracks`-СПИСОК; інакше `None`
     (простору чи теки нема, файл не читається чи не обʼєкт, ключа нема чи він не список)."""
@@ -1745,7 +1745,6 @@
         self._own = _LAZY
         self._items = _LAZY
         self._lite = _LAZY
-        self._adapter = _LAZY
 
     @property
     def sp(self):
@@ -1760,22 +1759,6 @@
             self._own = _own_tracks(self.sp)
         return self._own
 
-    @property
-    def adapter(self):
-        """Напрямки дає неявний адаптер ЛІГИ: простір ЛІГИ (чи шар вимкнено), у чиєму `space.json` нема списку `tracks`.
-        ⛔ Лише для ЛІГИ порожній власний список (`tracks: []`, чи такий, що після `tracks.normalize` порожній) теж віддає адаптер:
-        інакше він мовчки спорожнив би все (спільний корінь, нема репо, мітки малими літерами, нема напрямку за замовчуванням). Звичайний
-        простір порожній список лишає порожнім — напрямків нема. Непорожній власний список ЛІГИ адаптер вимикає (4d-3)."""
-        if self._adapter is _LAZY:
-            if not _liga_like(self.sp):
-                self._adapter = False
-            elif self._raw is None:
-                self._adapter = True
-            else:
-                path = self.sp.get('path') if isinstance(self.sp, dict) else None
-                self._adapter = not tracks.normalize(self._raw[0], path, roots=False)
-        return self._adapter
-
     def _light(self):
         """`(tracks, default)` БЕЗ перевірки коренів (`tracks.normalize(roots=False)`, `root` скрізь `None`) — для читача, якому
         потрібні лише `id`/`label`/`ds`/дефолт (`task_tags`, `task_ds`, `spaces_listing`). Рахується один раз на вигляд.
@@ -1783,11 +1766,8 @@
         ішла без потреби (корінь потрібен лише створенню задачі: `track_root`)."""
         if self._lite is _LAZY:
             sp = self.sp
-            if sp is None or (self._raw is None and not self.adapter):
+            if sp is None or self._raw is None:
                 self._lite = ([], None)
-            elif self.adapter:
-                items, default, _fallback = tracks.legacy_tracks(_legacy_cfg())
-                self._lite = (items, default)
             else:
                 items = tracks.normalize(self._raw[0], sp.get('path'), roots=False)
                 self._lite = (items, tracks.default_id(items, self._raw[1]))
@@ -1799,7 +1779,7 @@
 
     def _load(self):
         if self._items is _LAZY:
-            if not self._roots or self.adapter or self.sp is None or self._raw is None:
+            if not self._roots or self.sp is None or self._raw is None:
                 self._items = self._light()
             else:
                 items = tracks.normalize(self._raw[0], self.sp.get('path'), roots=True)
@@ -1829,31 +1809,25 @@
     return view.tracks, view.default
 
 
-def track_root(sp, cfg, track_id):
-    """Тека, у якій лягає тека НОВОЇ задачі напрямку `track_id` у просторі `sp`; `cfg` — файл задач (корінь старого
-    `tasks.json` для ЛІГИ).
-
-    ЛІГА через адаптер — ЛИШЕ `tracks.legacy_root(cfg, track_id)` (спека §6.1): будь-який рядок як є (й «не той регістр»), невідомий —
-    спільний корінь. ⛔ НЕ через `tracks.find`: адаптер перелічує лише id за шаблоном, а 0.14.0 шанував власний корінь будь-якого
-    ключа. Інші простори: знайдений напрямок → його `root`; невідомий → `root` дефолтного; `root` нема → шлях простору;
-    напрямків нема → шлях простору (звичайний) / спільний корінь ЛІГИ."""
+def track_root(sp, track_id):
+    """Тека, у якій лягає тека НОВОЇ задачі напрямку `track_id` у просторі `sp` (для ВСІХ просторів однаково): знайдений напрямок
+    → його `root`; невідомий → `root` дефолтного; `root` нема чи напрямків нема → шлях простору; простору чи його шляху нема
+    (шар вимкнено) → `None` (викликач бере `default_task_root(cfg)`)."""
     view = sp if isinstance(sp, _TrackView) else _TrackView(sp)      # `None` тут — «простору нема», а не «простір запиту»
-    if view.sp is None or view.adapter:
-        return tracks.legacy_root(cfg, track_id)
+    if view.sp is None:
+        return None
     t = tracks.find(view.tracks, track_id) or tracks.find(view.tracks, view.default)
-    if t is not None:
-        return t['root'] or view.sp['path']
-    return tracks.legacy_root(cfg, None) if _liga_like(view.sp) else view.sp['path']
+    if t is not None and t['root']:
+        return t['root']
+    return view.sp.get('path') or None
 
 
 def track_repo(sp, track_id):
     """Типовий репозиторій макетів напрямку `track_id` або `''`. Невідомий напрямок репо НЕ бере з дефолтного (маршрут його
-    відмовить раніше). ЛІГА через адаптер — `profile_repos()` (ключ за `ID_RE`, як у 0.14.0)."""
+    відмовить раніше)."""
     view = sp if isinstance(sp, _TrackView) else _TrackView(sp)
     if not isinstance(track_id, str) or view.sp is None:
         return ''
-    if view.adapter:
-        return profile_repos().get(track_id, '')           # одне джерело з `_liga_flow` (і з тестами, що його підміняють)
     t = tracks.find(view.tracks, track_id)
     return t['repo'] if t else ''
 
@@ -1870,8 +1844,6 @@
     if v is None:
         return ''
     view = _as_view(sp)
-    if view.adapter:
-        return v
     t = tracks.find(view.lite, v)                           # простору нема — напрямків нема — значення як є, як 0.14.0
     return t['ds'] if t else v
 
@@ -1891,7 +1863,7 @@
     `items` — уже впорядковані `tasks_by_recent(cfg)` (`?all=1` рахує їх у вузькому `try`, див. `_all_space_task_rows`)."""
     sp = _as_view(sp)
     return [{'id': k, 'title': v.get('title', k), 'jira': v.get('jira'),
-             'profile': v.get('profile'), 'track': tracks.of_task(v),
+             'track': tracks.of_task(v),
              'missing': not (isinstance(v.get('dir'), str) and os.path.isdir(v['dir'])),
              'tags': task_tags(v, sp)}
             for k, v in (tasks_by_recent(cfg) if items is None else items)]
@@ -2279,7 +2251,7 @@
         trk = tr_statuses.get(jkey) if isinstance(jkey, str) else None
         mine.append({
             'id': tid, 'jira': task.get('jira'), 'title': task.get('title', tid),
-            'profile': task.get('profile'), 'opened': task.get('opened'),
+            'opened': task.get('opened'),
             'iterations': st['iterations'], 'pages': st['pages'],
             'iter': st['last_iter'], 'changed': _last_changed(task, st),
             'published': st['code_url'], 'missing': not st['dir_exists'],
@@ -2410,6 +2382,16 @@
     def __init__(self, code, message):
         super().__init__(message)
         self.code = code
+
+
+#: Останній рубіж кореня теки нової задачі: простір шляху не має (шар вимкнено) і виклик не дав `root`.
+DEFAULT_TASK_ROOT = '~/deai-work'
+
+
+def default_task_root(cfg):
+    """Спільний корінь тек задач із кореня файла задач (`design_work_root`), інакше `DEFAULT_TASK_ROOT`; `~` розгорнуто."""
+    shared = cfg.get('design_work_root') if isinstance(cfg, dict) else None
+    return os.path.expanduser(shared if isinstance(shared, str) and shared else DEFAULT_TASK_ROOT)
 
 
 def task_new(cfg, tid, title='', jira='', track=None, gitlab=None, vcs=None, root=None, adopt_src=None,
@@ -2453,7 +2435,7 @@
         raise TaskRefused('bad-task-id', 'bad task id')
     if tid in cfg.get('tasks', {}):
         raise TaskRefused('task-exists', 'task already exists')
-    tdir = os.path.join(root or tracks.legacy_root(cfg, track), tid)
+    tdir = os.path.join(root or default_task_root(cfg), tid)
     if adopt_src is not None:
         try:
             os.makedirs(tdir)                  # БЕЗ `exist_ok`: теку займає рівно один запит
@@ -6019,7 +6001,6 @@
             sp = spaces.active_space()
             out = {'id': tid, 'title': task.get('title', tid),
                    'jira': task.get('jira'),
-                   'profile': task.get('profile'),
                    'tags': task_tags(task, sp),
                    'track': tracks.of_task(task),
                    # Простір задачі (`describe`: id, name, color, path, legacy,
@@ -7945,15 +7926,12 @@
         # (`bad-track`) — лише коли `profile` справді був би використаний; інакше вирішує один `track`.
         liga = spaces.integrations_for(sp)
         view = _TrackView(sp)
-        if liga:
-            used_profile = profile or None
-        else:
-            known = bool(profile) and tracks.ID_RE.fullmatch(profile) and tracks.find(view.tracks, profile) is not None
-            used_profile = profile if known else None
+        known = bool(profile) and tracks.ID_RE.fullmatch(profile) and tracks.find(view.tracks, profile) is not None
+        used_profile = profile if known else None
         if track_in and used_profile and track_in != used_profile:
             self._space_error(400, 'bad-track', 'track and profile name different tracks')
             return
-        if track_in and not liga:
+        if track_in:
             if not tracks.ID_RE.fullmatch(track_in):
                 self._space_error(400, 'bad-track', 'track must be lowercase letters, digits and dashes')
                 return
@@ -8007,7 +7985,7 @@
         # репо дає напрямок: ЛІГА — `track_root` (спільний корінь для невідомого), звичайний — `root` напрямку чи шлях простору.
         cfg = load_tasks()                     # ПІСЛЯ фіксації простору: файл ЦІЛЬОВОГО простору
         track = want_track or view.default
-        root, repo = track_root(view, cfg, track), track_repo(view, track)
+        root, repo = track_root(view, track) or default_task_root(cfg), track_repo(view, track)
         adopt = None
         if payload.get('from') is not None:
             tdir = os.path.join(root, tid) if isinstance(tid, str) else ''
```

  diff `bin/registry.py` (без pull-циклу — він у Task 6):

```diff
--- a/bin/registry.py
+++ b/bin/registry.py
@@ -429,16 +429,25 @@
     return {'state': 'fresh', 'age_h': age, 'hint': ''}
 
 
-def _work_root(cfg, task):
-    """Корінь напрямку ЗАДАЧІ через `tracks` (`of_task` + `legacy_root`) — щоб правило жило в ОДНОМУ місці.
+def _track_of_entry(e):
+    """Напрямок запису спільного реєстру (МЕЖА 4d-4a): `track`, коли непорожній рядок, інакше `profile` (колеги на старому
+    інструменті шлють лише `profile`). Єдине місце, де `profile` ще читається."""
+    if not isinstance(e, dict):
+        return None
+    for key in ('track', 'profile'):
+        v = e.get(key)
+        if isinstance(v, str) and v:
+            return v
+    return None
 
-    `task` — запис задачі чи запис реєстру: напрямок береться як у всіх (`track`, інакше `profile`; запис машини на 0.14.0
-    має лише `profile` і дає ту саму теку). ⛔ Читати лише ключ `profile` не можна: задача лише з `track` лягла б у спільний корінь.
 
-    Імпорт лінивий і всередині функції: реєстр запускають і як окремий CLI, а шлях до `app/` у нього свій."""
+def _work_root(cfg, task):
+    """Корінь теки задачі через ЯВНІ напрямки простору ЛІГИ (`serve.track_root`); простору/напрямків нема → `None`."""
     sys.path.insert(0, os.path.join(ROOT, 'app'))
-    import tracks
-    return tracks.legacy_root(cfg, tracks.of_task(task))
+    import serve
+    import spaces
+    sp = next((s for s in spaces.read_registry()['spaces'] if s.get('legacy') is True), None)
+    return serve.track_root(sp, _track_of_entry(task)) or serve.default_task_root(cfg)
 
 
 def split_fixtures(entries):
@@ -716,7 +725,7 @@
     import tracks
     by_track, by_owner = {}, {}
     for e in reg.values():
-        k = tracks.of_task(e) or '?'
+        k = _track_of_entry(e) or '?'
         by_track[k] = by_track.get(k, 0) + 1
         by_owner[e.get('owner') or '—'] = by_owner.get(e.get('owner') or '—', 0) + 1
     print('   напрямки: ' + ', '.join(f'{k} {v}' for k, v in sorted(by_track.items())))
```

  diff `bin/roots.py`:

```diff
--- a/bin/roots.py
+++ b/bin/roots.py
@@ -25,18 +25,28 @@
 sys.path.insert(0, os.path.join(ROOT, 'app'))
 sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
 import spaces  # noqa: E402
-import tracks  # noqa: E402  (напрямок задачі й корінь ЛІГИ — одне місце правди; `serve` лишився лише для файла задач)
+import tracks  # noqa: E402
+import serve  # noqa: E402
 from serve import load_tasks, save_tasks  # noqa: E402
 
 
-def plan(cfg):
-    """Що куди має переїхати. Чиста функція — тому й перевіряється тестами.
+def _view():
+    """Напрямки простору ЛІГИ на час команди (`serve._TrackView`); простору нема — порожній вигляд."""
+    sp = spaces.active_space()
+    return serve._TrackView(sp)
 
-    Повертає список записів: (tid, напрямок, звідки, куди, причина-стоп або None). Напрямок задачі — `tracks.of_task`
-    (`track`, інакше `profile`: запис, створений до 0.15.0, має лише `profile`, новий — обидва чи лише `track`).
-    Стоп-причини НЕ приховуємо: мовчазний пропуск задачі в міграції означав би,
-    що дизайнер вважає переїзд завершеним, а частина лишилась на місці.
-    """
+
+def _root_of(cfg, view, track):
+    return serve.track_root(view, track) or serve.default_task_root(cfg)
+
+
+def plan(cfg, view=None):
+    """Що куди має переїхати. Чиста функція — тому й перевіряється тестами. Корені — з ЯВНИХ напрямків простору ЛІГИ
+    (`serve.track_root`); `view` — `serve._TrackView` цього простору (типово — активний).
+
+    Повертає список записів: (tid, напрямок, звідки, куди, причина-стоп або None). Напрямок задачі — `tracks.of_task` (`track`).
+    Стоп-причини НЕ приховуємо."""
+    view = view or _view()
     out = []
     for tid, t in sorted((cfg.get('tasks') or {}).items()):
         track = tracks.of_task(t)
@@ -45,7 +55,7 @@
             out.append((tid, track, None, None, 'немає dir у tasks.json'))
             continue
         cur = os.path.expanduser(cur)
-        want = os.path.join(tracks.legacy_root(cfg, track), tid)
+        want = os.path.join(_root_of(cfg, view, track), tid)
         if os.path.normpath(cur) == os.path.normpath(want):
             continue
         stop = None
@@ -57,25 +67,21 @@
     return out
 
 
-def roots_in_use(cfg):
-    """Корінь на кожен напрямок + позначка, чи він СВІЙ, чи спільний фолбек.
+def roots_in_use(cfg, view=None):
+    """Корінь на кожен напрямок + позначка, чи він СВІЙ (`root` напрямку), чи тека простору. Напрямки — ті, що є в задачах
+    (`tracks.of_task`, без напрямку — «—»), і явні напрямки простору."""
+    view = view or _view()
+    found = sorted({(tracks.of_task(t) or '—') for t in (cfg.get('tasks') or {}).values()} | {t['id'] for t in view.tracks})
+    own = {t['id'] for t in view.tracks if t['root']}
+    return [(p, _root_of(cfg, view, p), p in own) for p in found]
 
-    Напрямки — ті, що є в задачах (`tracks.of_task`, без напрямку — «—»), і ті, що мають власний корінь. «Свій» — ключ є в
-    `design_work_roots` (як і було: порожнє значення теж «свій», хоч корінь тоді спільний). Свідомі відмінності від 0.14.0:
-    не рядок у `profile` (число) тепер читається як «без напрямку» (раніше `sorted` падав `TypeError` на суміші числа з
-    рядками), а `design_work_roots` не словник — як `{}` (спільний корінь, спека §6.4; раніше `AttributeError`)."""
-    roots = cfg.get('design_work_roots')
-    roots = roots if isinstance(roots, dict) else {}
-    found = sorted({(tracks.of_task(t) or '—') for t in (cfg.get('tasks') or {}).values()} | set(roots))
-    return [(p, tracks.legacy_root(cfg, p), p in roots) for p in found]
 
-
-def cmd_status(cfg):
+def cmd_status(cfg, view=None):
     print('Корені напрямків:')
-    for track, root, own in roots_in_use(cfg):
+    for track, root, own in roots_in_use(cfg, view):
         mark = '✅ свій' if own else '⚠️ спільний (свого кореня немає)'
         print(f'   {track:10} → {root}  [{mark}]')
-    moves = plan(cfg)
+    moves = plan(cfg, view)
     if not moves:
         print('Усі задачі лежать у корені свого напрямку.')
         return 0
@@ -87,8 +93,8 @@
     return 0
 
 
-def cmd_migrate(cfg, apply):
-    moves = plan(cfg)
+def cmd_migrate(cfg, apply, view=None):
+    moves = plan(cfg, view)
     if not moves:
         print('Переселяти нічого.')
         return 0
```

- [ ] **Step 3:** перенести адаптерні класи `test_tracks.py` у `tests/test_liga_adapter.py` (націлити на `liga_migrate._legacy_*`; кожен тест лишається, змінюється лише обʼєкт). Таблиця відповідності ретайрених `ServerLegacyParity` і `BinParity` (по тесту → чим покрито: `AfterMigrationParity4d4a`/`test_liga_adapter`) — у звіті; НІЧОГО не видаляти без рядка в таблиці.
- [ ] **Step 4:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_no_adapter tests.test_liga_adapter` → зелено. Решта тестів (Task 5–6) тут червона — це і є червона планка наступних задач.
- [ ] **Step 5:** коміт `refactor(4d-4a): рантайм без адаптера ЛІГИ; охоронець NoTracksAdapter`.

#### Охоронець (`tests/test_no_adapter.py`)

```python
import ast
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NoTracksAdapter(unittest.TestCase):
    """⛔ Адаптер ЛІГИ живе ЛИШЕ в `app/liga_migrate.py` (4d-4a). Охоронець — AST, а не grep: ловить імʼя, атрибут, визначення,
    імпорт-псевдонім і аргумент, тож «обхід» перейменуванням у `import … as` чи в `getattr`-подібному вигляді не проходить без
    правки самого списку. Сканує `app/**/*.py` і `bin/*.py`, крім `liga_migrate.py` і `test_*`."""

    FORBIDDEN = {'legacy_tracks', 'legacy_root', 'legacy_repos', '_LEGACY_LABELS', 'profile_repos', '_legacy_cfg',
                 'FALLBACK_ROOT', 'FALLBACK_WORK_ROOT'}
    #: Єдине місце, де `adapter_applies` дозволено згадувати (крім `liga_migrate.py`, який сканер пропускає).
    ADAPTER_APPLIES_OK = {'tracks.py'}
    #: Читання `profile` з запису задачі дозволене лише на межах (спека: `profile` — тільки на вході `task-new`, у реєстрі й у
    #: `SHARED`). Ключ — імʼя функції, у якій воно стоїть.
    PROFILE_OK = {'_task_new', '_liga_flow', '_track_of_entry', '<module>'}

    @staticmethod
    def _files():
        out = []
        for base, _d, fs in os.walk(os.path.join(ROOT, 'app')):
            out += [os.path.join(base, f) for f in fs if f.endswith('.py') and not f.startswith('test_')]
        out += [p for p in glob.glob(os.path.join(ROOT, 'bin', '*.py')) if not os.path.basename(p).startswith('test_')]
        return sorted(p for p in out if os.path.basename(p) != 'liga_migrate.py')

    @staticmethod
    def _idents(tree):
        s = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Name):
                s.add(n.id)
            elif isinstance(n, ast.Attribute):
                s.add(n.attr)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                s.add(n.name)
            elif isinstance(n, ast.alias):
                s.add(n.name.split('.')[-1])
                s.add(n.asname or '')
            elif isinstance(n, ast.arg):
                s.add(n.arg)
        return s

    @staticmethod
    def _adapter_member(tree):
        """`X.adapter` і `def adapter` — адаптер-властивість; голе імʼя `adapter` у `serve` — звичайна локальна змінна (не ловимо)."""
        hits = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr == 'adapter':
                hits.add('adapter')
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'adapter':
                hits.add('adapter')
        return hits

    def test_the_runtime_has_no_adapter(self):
        bad = {}
        for p in self._files():
            tree = ast.parse(open(p, encoding='utf-8').read())
            hit = (self._idents(tree) & self.FORBIDDEN) | self._adapter_member(tree)
            if 'adapter_applies' in self._idents(tree) and os.path.basename(p) not in self.ADAPTER_APPLIES_OK:
                hit.add('adapter_applies')
            if hit:
                bad[os.path.relpath(p, ROOT)] = sorted(hit)
        self.assertEqual(bad, {})

    def test_profile_is_read_only_at_the_boundary(self):
        seen = []
        for p in self._files():
            tree = ast.parse(open(p, encoding='utf-8').read())
            parents = {}
            for n in ast.walk(tree):
                for c in ast.iter_child_nodes(n):
                    parents[c] = n

            def fn_of(n):
                while n in parents:
                    n = parents[n]
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        return n.name
                return '<module>'
            for n in ast.walk(tree):
                is_get = (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get' and n.args
                          and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'profile')
                is_sub = isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == 'profile'
                is_tup = isinstance(n, ast.Tuple) and any(isinstance(e, ast.Constant) and e.value == 'profile' for e in n.elts)
                if is_get or is_sub or is_tup:
                    seen.append((os.path.relpath(p, ROOT), fn_of(n)))
        self.assertTrue(seen, 'межі зникли: охоронець порожній')
        stray = [x for x in seen if x[1] not in self.PROFILE_OK]
        self.assertEqual(stray, [], 'читання `profile` поза межею: %s' % stray)

    def test_the_guard_can_fail(self):
        """Охоронець, який не може впасти, — фікція: підсовуємо сканеру зіпсований код і бачимо червоне."""
        src = 'import tracks\ntracks.legacy_root(cfg, "x")\nclass V:\n    @property\n    def adapter(self):\n        return 1\n'
        tree = ast.parse(src)
        self.assertEqual((self._idents(tree) & self.FORBIDDEN) | self._adapter_member(tree), {'legacy_root', 'adapter'})
        self.assertEqual(self._adapter_member(ast.parse('adapter = 1\nprint(adapter)')), set())


if __name__ == '__main__':
    unittest.main()
```

---
### Task 5: `of_task` лише `track`, API без `profile` — тести

**Files:** `app/serve.py` (рядки `_task_rows` `:1879`, `tasks_overview` `:2282`, `/api/task` `:6022` — стоп `profile`; уже в diff Task 4), тести нижче.

**Що змінюється для користувача:** `/api/task`, `/api/tasks` і `tasks_overview` більше не віддають `profile`; мітка й `?ds=` читаються з `track`. `entry['profile'] = track if liga else None` у `_task_new_write` ЛИШАЄТЬСЯ (колеги на старіших машинах).

Виміряна (на прототипі з тимчасовим `HOME`) інвентаризація тестів, що ламаються, і що з ними робити — НІЧОГО не видаляти мовчки:

| Файл | Зламано | Що робити |
|---|---|---|
| `tests/test_tracks.py` | 96 із 161 (підтести включно): `ServerTracks` 19, `ServerTrackView` 17, `LegacyTracks` 17, `ServerLegacyParity` 13, `LegacyParity` 10, `ApiTracks` 7, `TaskTrack` 6, `BinParity` 3, `ApiTracksImplicitSpace` 3, `ServerHygiene` 1 | адаптерні — у `test_liga_adapter.py` (Task 4); `ServerLegacyParity`/`BinParity` — ретайр з таблицею відповідності; `ServerTracks`, `ServerTrackView`, `ApiTracks*`, `TaskTrack` — переписати на явні напрямки (фікстура з `space.json['tracks']`), `ServerHygiene` — оновити очікування |
| `tests/test_task_tags.py` | 24 (`ProfileReposTest` 15, `TaskTags` 5, `TagsApi` 4) | `ProfileReposTest` → адаптерний файл (`_legacy_repos`); `TaskTags`, `TagsApi` — записи з `track`; мітка профіль-only = нижній регістр id |
| `tests/test_spaces_serve.py` | 22 (`TaskNew` 9, `InspectorSpace` 4, `NoSpaces` 3, `TaskResponses` 2, `LayerOff` 2, `FirstSpace` 1, `Cli` 1) | у Task 6 (task-new/`_liga_flow`) |
| `tests/test_roots.py` | 13 із 14 | Task 6 |
| `tests/test_comments_role.py` | 7 | еталони залежали від `?ds=tool` із `profile: 'tool'` → у фікстурі `profile` → `track` |
| `tests/test_dashboard.py` `ReadParity` | 9 | знімок рядків містив `profile`/теги → оновити еталон (різниця з причиною в звіті) |
| `tests/test_tasks_overview.py` | 1 | рядок без `profile` |
| `tests/test_state.py` | 1 | `bin/state.py:395` читає `tracks.of_task` → фікстура з `track` |
| `bin/test_registry.py` | 2 (`TestTrack`) | Task 6 |

Незачеплені: `test_vcs_core`, `test_gitlab_sync`, `test_serve`, `test_implicit`, `test_integrations_off`, `test_modules_api`, `test_task_from`, `test_vercel_publish_cli`, `test_dashboard_module`, `test_legacy_comments`, `test_modules_trust_api`, `bin/test_overview_push`.

- [ ] **Step 1 (червоне):** новий клас `OfTaskTrackOnly` у `tests/test_tracks.py`: `of_task({'profile': 'united'}) is None`; `of_task({'track': 'seo', 'profile': 'united'}) == 'seo'`; `label_tag` без параметра `legacy`; `/api/task`, `/api/tasks` не мають ключа `profile` (а `track` — є); `task_tags` для запису лише з `profile` у звичайному просторі → `[]`, `task_ds` → `''` (виміряна різниця: стенд `plain`, `a-2`).
- [ ] **Step 2:** перебрати класи таблиці вище, по одному файлу за раз, `HOME=$(mktemp -d) python3 -B -m unittest tests.<файл>`; для кожної зміни наявного тесту — рядок із причиною для звіту.
- [ ] **Step 3:** `tests/test_state.py`, `tests/test_comments_role.py`, `tests/test_dashboard.py` (`ReadParity`), `tests/test_tasks_overview.py` — оновити фікстури/еталони без `UPDATE_*`-прапорців (ручно, диф-ом, з поясненням).
- [ ] **Step 4:** коміт `test(4d-4a): of_task лише track, API без profile`.

---
### Task 6: `task-new`, `_liga_flow`, реєстр, `bin/roots.py`

**Files:** `app/serve.py` (`_task_new`, `_task_new_write`, `_liga_flow`), `bin/registry.py` (pull-цикл), `bin/roots.py`, `tests/test_spaces_serve.py`, `tests/test_roots.py`, `bin/test_registry.py`.

**Правила `task-new` (рішення; код уже в diff Task 4):**

- Сувора перевірка `track` (`bad-track` для не-`ID_RE`, `unknown-track` для невідомого напрямку простору) діє для ВСІХ просторів; раніше — лише для явних.
- `profile` на вході береться лише коли він збігається з `ID_RE` і є напрямком простору; інакше ігнорується. Якщо `track` і `profile` обидва задані й різні — `bad-track` (конфлікт).
- `_liga_flow`: `_liga_track_repos()` — множина id напрямків із репо у просторі реєстру з `legacy is True`, читана через `_TrackView(liga).lite`; `SpacesError` → порожня множина. Знак «це ЛІГА-задача» — `track` або `profile`, що входить у цю множину; без простору ЛІГИ — `no-space` (Поправка 16).
- ⛔ Тести, що викликають `roots`/`task_new` без `root`, — з тимчасовим `HOME` (інцидент у «Правилах»).

**Реєстр — pull-цикл (ще не прототипований; нове в цьому плані):** у `bin/registry.py`, у циклі `pull`, одразу після копіювання `SHARED`:

```python
        t = _track_of_entry(e)                # межа: запис реєстру старої машини має лише `profile`
        if t and not local.get('track'):
            local['track'] = t
            mine['track'] = t
```

Тести (нові, `bin/test_registry.py`): (а) запис реєстру з лише `profile` після `pull` дає `local['track'] == profile` і потрапляє у `writes`; (б) запис з `track` і `profile` — виграє `track`; (в) `status` після такого `pull` не показує дрейфу (порівнюються лише ключі, що є в записі реєстру); (г) `_work_root` для запису лише з `profile` дає корінь напрямку; (д) `_track_of_entry` без обох → `None`.

- [ ] **Step 1 (червоне):** тести (а)–(д); у `tests/test_spaces_serve.py::TaskNew` — таблиця з 11 сценаріїв знімка (`track_upper`, `track_with_slash`, `track_zzz` → 400 `bad-track`/`bad-track`/`unknown-track`; `profile_upper`, `profile_zzz` → запис з `track=profile=united`); `NoSpaces.test_liga_signs…` з простором ЛІГИ.
- [ ] **Step 2 (зелене):** pull-цикл (фрагмент вище) + решта вже в diff Task 4.
- [ ] **Step 3:** `tests/test_roots.py` — переписати на `view` (з тимчасовим `HOME`, фікстура простору з явними напрямками); `bin/test_registry.py::TestTrack` — на `_track_of_entry`.
- [ ] **Step 4:** `HOME=$(mktemp -d) python3 -B -m unittest tests.test_spaces_serve tests.test_roots` і `python3 -B bin/test_registry.py` → зелено; `ls ~/deai-work` — без змін.
- [ ] **Step 5:** коміт `feat(4d-4a): task-new без профілю-адаптера; межа track/profile у реєстрі; roots через view`.

---
### Task 7: паритет після міграції `AfterMigrationParity4d4a`, мутації, живі тести

**Files:** `tests/test_liga_migrate_d.py` (клас `AfterMigrationParity4d4a`), `tests/live/*.test.mjs` (список нижче).

**Колектор (прототип; з нього збирається `setUpClass`):** стенди знімка 0.19.0 запускаються з МІГРОВАНОЮ ЛІГОЮ (`lm.run(step=lm.STEP_D)` до збору; стенд `plain` — без D), збирається той самий набір розділів, після D `tasks.json` перечитується (`load_legacy_tasks`), потім `roots_cli`/`registry`/`task_new`/`api`. API-розділ нормалізується: ключ `profile` вилучається з порівняння (його відсутність перевіряє окремий тест).

```python
import json, os, sys, tempfile
from unittest import mock
S = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [S + '/r/tests', S + '/r/app', S + '/r/bin']
import make_before_4d4a as g
from make_before_4d3a import CLEAN, NoNet, SocketTripwire, Vcs, rel, scrub, Server
from make_before_4d3b import _call


def collect(tmp, name, run_d=True, steps=None):
    import registry, roots, serve, liga_migrate as lm
    rig, sp, cfg = g._stand(tmp, name)
    out = {}
    spy = mock.MagicMock(return_value=False)
    with rig.activate(), mock.patch.object(serve, 'vcs_provider', Vcs()), mock.patch.object(serve, '_registry_push', spy), \
            mock.patch.object(serve, 'git_autocommit', lambda *a, **k: None), \
            mock.patch.object(serve.Handler, '_overview_sync', lambda *a, **k: None):
        if run_d and name != 'plain':
            out['_d'] = (lm.run(step=lm.STEP_D), lm.status()['steps']['liga-4d4a']['mark'])
        tasks = cfg['tasks']
        out['labels'] = {tid: serve.task_tags(t, sp) for tid, t in tasks.items()}
        out['ds'] = {tid: serve.task_ds(t, sp) for tid, t in tasks.items()}
        items, default = serve.space_tracks(sp)
        out['view'] = {'ids': [t['id'] for t in items], 'labels': [t['label'] for t in items], 'default': default,
                       'repos': {t['id']: t['repo'] for t in items}, 'ds': {t['id']: t['ds'] for t in items},
                       'roots': {t['id']: rel(t['root'], rig.home) for t in items}}
        values = g.VALUES + (('web', 'app') if name == 'plain' else ())
        out['repos'] = {repr(v): serve.track_repo(sp, v) for v in values}
        out['roots'] = {repr(v): rel(serve.track_root(sp, v), rig.home) for v in values}
        # tasks.json після D (записи читає й `roots`, і API)
        cfg = serve.load_legacy_tasks() if name != 'plain' else cfg
        tasks = cfg['tasks']
        out['labels'] = {tid: serve.task_tags(t, sp) for tid, t in tasks.items()}
        out['ds'] = {tid: serve.task_ds(t, sp) for tid, t in tasks.items()}
        if name != 'plain':
            with serve.spaces.request_space(sp['id']):
                out['roots_cli'] = {'plan': {r[0]: r[1:] for r in scrub([list(r) for r in roots.plan(cfg)], rig.home)},
                                    'in_use': {r[0]: r[1:] for r in scrub([list(r) for r in roots.roots_in_use(cfg)], rig.home)}}
            out['registry'] = {k: rel(registry._work_root(cfg, e), rig.home) for k, e in g.REGISTRY_ENTRIES.items()}
        with Server() as srv:
            posts = {}
            for key, body in g.POSTS:
                body = dict(body, space=sp['id'])
                st, resp = _call(srv, 'POST', '/api/task-new', body=body)
                row = {'status': st, 'code': resp.get('code') if isinstance(resp, dict) else None}
                with open(g.spaces_tasks_file(sp), encoding='utf-8') as f:
                    saved = json.load(f)['tasks']
                row['entry'] = g._entry_view(saved[body['id']], rig.home) if body['id'] in saved else None
                posts[key] = row
            out['task_new'] = posts
            api = {'task': {}}
            for tid in ('a-1', 'a-2', 'a-3', 'a-6', 'a-8'):
                if name == 'plain':
                    break
                st, body = srv.req('GET', '/api/task', task=tid)
                api['task'][tid] = {'status': st, 'keys': {k: True for k in sorted(body)} if isinstance(body, dict) else None,
                                    'profile': body.get('profile', '<absent>'), 'track': body.get('track'), 'tags': body.get('tags')}
            st, body = srv.req('GET', '/api/tasks')
            api['tasks'] = {'status': st, 'rows': [{k: r.get(k, '<absent>') for k in ('id', 'profile', 'track', 'tags')}
                                                    for r in sorted(body.get('tasks', []), key=lambda r: r['id']) if r['id'].startswith('a-')]}
            st, body = srv.req('GET', '/api/spaces')
            row = next(r for r in body['spaces'] if r['id'] == sp['id'])
            api['space_row'] = {'tracks': row.get('tracks'), 'default_track': row.get('default_track')}
            out['api'] = api
    return scrub(out, rig.home)


def flat(o, p=''):
    out = {}
    if isinstance(o, dict):
        for k, v in o.items():
            out.update(flat(v, p + '/' + str(k)))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            out.update(flat(v, p + '[%d]' % i))
        if not o: out[p + '[]'] = []
    else:
        out[p] = o
    return out


if __name__ == '__main__':
    before = json.load(open(S + '/b1.json'))['stands']
    with tempfile.TemporaryDirectory(prefix='after-4d4a-') as tmp:
        tmp = os.path.normpath(tmp); home = os.path.join(tmp, 'home'); os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire(), mock.patch('urllib.request.urlopen', NoNet()):
            for n in CLEAN: os.environ.pop(n, None)
            res = {}
            for name in g.STANDS:
                res[name] = collect(tmp, name)
    json.dump(res, open(S + '/after.json', 'w'), ensure_ascii=False, indent=1, sort_keys=True)
    for name in g.STANDS:
        a, b = flat(before[name]), flat(res[name])
        print('=====', name, res[name].get('_d'))
        for k in sorted(set(a) | set(b)):
            if a.get(k, '<ABSENT>') != b.get(k, '<ABSENT>'):
                print(k, '|', a.get(k, '<ABSENT>'), '->', b.get(k, '<ABSENT>'))
```

**EXPECT_DIFF (виміряно; точні листки генерувати з знімка програмно, не вручну):**

- Нормалізація: списки `keys` → словники, `roots_cli` списки → словники за id.
- `labels`, `ds`, `repos`, `view`, `roots` — ідентичні на `parity` і `explicit`.
- `parity`/`explicit`: `roots_cli.in_use.<id>[own]` False → True для id із спільним коренем, що тепер явні напрямки (parity: liga360, seo, united; explicit: liga360, united); `task_new`: `track_upper`, `track_with_slash`, `track_zzz` 200 → 400 (`bad-track`, `bad-track`, `unknown-track`), їхні `entry`-листки → ABSENT; `profile_upper`, `profile_zzz` — запис стає `track=profile=united` + `keys.gitlab`.
- `notes` (додатково до вищого): корені змінюються — `seo` → шлях простору; `liga360` `rel/l360` → шлях простору; невідомі значення зі спільного кореня → корінь united; `view.roots.{liga360,seo}` → `None`; `registry`, `roots_cli.plan/in_use` — інші корені; `Bad_Key` перестає бути напрямком; теки `task_new` інші; нотатки позначки D: `root-dropped:liga360, root-dropped:seo, unknown-values, default-root-differs, non-id-keys`.
- `plain`: лише `labels.a-2` `['united']` → `[]` і `ds.a-2` `'united'` → `''` (запис з `profile` у звичайному просторі).
- Охоронець порівняння (як у 4d-3c): зайвий листок і зниклий очікуваний — обидва червоніють; «що бачить людина» (`/task`, `/api/task` крім `profile`) — без різниць.

- [ ] **Step 1 (червоне → зелене):** клас `AfterMigrationParity4d4a` за зразком `AfterMigrationParity4d3c` (`test_all_steps_ran`, `test_snapshot_is_big_enough_to_mean_something`, `test_only_expected_differences_<стенд>` ×4, `test_expected_diff_is_exact_not_loose`, `test_nothing_a_person_sees_changed`, `test_api_has_no_profile`). Обовʼязково: `HOME` у тимчасовій теці, `NoNet`, `SocketTripwire`.
- [ ] **Step 2: живі тести (по одному, послідовно).** Червоні між Task 2 і Task 7, поки не оновлені: `tests/live/fixture.mjs` (пише `profile` → додати `track`); `tasks-home.test.mjs` (профіль-only задачі → чипи стануть `united`/`liga360` нижнім регістром); `modules.test.mjs:352` (`cfg.tasks.lab.profile = "tool"` → `track`); `tracks.test.mjs` (профільні тести); `inspector-ds.test.mjs:234`; `liga-migrate.test.mjs` (чотири бекапи, стенд `notes`). Прогін: `node --test --test-concurrency=1 tests/live/<файл>.test.mjs`.
- [ ] **Step 3: мутаційні докази** (кожна мутація — один рядок, `python3 -B`, відновлення + `sha256` до/після; кожна має зробити червоним названий тест):

| Мутація | Червоний тест |
|---|---|
| `of_task` повертає `track`, інакше `profile` | `OfTaskTrackOnly`, `AfterMigrationParity4d4a.plain` |
| прибрати крок записів (б) із `_plan`/`_run_locked` | `StepDRunTest` (записи), `AfterMigrationParity4d4a` |
| прибрати ворота «адаптер діє» в `_commit_space`/плані | `StepDPlanTest` (`tracks-present`), тест гонки «власник дописав напрямки» |
| `_track_of_entry` ігнорує `profile` | `bin/test_registry.py` (а), (г) |
| `_task_new` поблажливий до `track` для ЛІГИ | `TaskNew` (`track_zzz` → 400) |
| прибрати `abort-tracks` | `StepDPlanTest` (21 id → `abort-tracks`) |
| `_applied_later` повертає перший застосований | `LifoFourSteps` |
| зняти піни `STEPS[:3]` | `_StepC`-класи 4d-3c |
| `restore` пише `tasks.json` | тест «restore не чіпає tasks.json» |
| змінити критерій `adapter_applies` (`raw == []`) | `AdapterApplies` |
| згенерувати знімок із зміненим кодом | `_code_differs_from_source` (exit 2) |
| додати `legacy_root` у `serve.py` | `NoTracksAdapter.test_the_runtime_has_no_adapter` |
| читати `profile` у новому місці | `NoTracksAdapter.test_profile_is_read_only_at_the_boundary` |
| `_liga_flow` без `SpacesError`-гілки | `NoSpaces`/`LigaFlow` |

- [ ] **Step 4:** результати мутацій і живих — у звіті (зведена таблиця — у спеці «Implementation notes»). Коміт `test(4d-4a): паритет після міграції, живі тести`.

---
### Task 8: документи, версія 0.20.0

- [ ] **Документи (англійською, як наявні):**
  - `CHANGELOG.md`: `## [0.20.0] — <дата DD.MM.YYYY — вписує контролер>`; підрозділи **Upgrading** (четвертий крок `liga-4d4a`, чотири бекапи; відкат на 0.19 — `bin/migrate_liga.py restore <stamp-d> --hold`; ⚠️ `restore` повертає `space.json`, `tasks.json` лишається з `track = profile` — це безпечно для 0.19; `tasks.json.bak` — ручний), **Deliberate differences** (зі спеки + Поправки 3, 4, 6, 11: профіль-only записи в звичайних просторах втрачають мітку/`ds`; шар-OFF без напрямків; сувора перевірка `track` у всіх просторах), **Known limits** (`abort-tracks` для >20 id — постійний; `profile` у записах `tasks.json` не прибирається; зовнішній dev-pipeline читає `profile` напряму — Поправка 15; перший `push` 0.20 дописує `track` у реєстр — Поправка 13).
  - `README.md`: рядок дорожньої карти (≈683) «4d-4 (0.20) — прапорець `integrations` і старі аліаси (зокрема `profile`) зникають» → «4d-4a (0.20) напрямки ЛІГИ явні, `profile` лише на межі; 4d-4b (0.21) …; 4d-4c (0.22) …»; розділ міграції (≈600–626): кроки a–d і текст «часткова міграція — остаточна».
  - `docs/design/spaces-and-modules.md` (≈129 і 673–677 «Left for 4d-4»): оновити.
  - Спека: «Implementation notes» з таблицею мутацій і Поправками.
- [ ] **`package.json`:** `version` → `0.20.0` (шлях релізу контролера: bump, CHANGELOG-дата, тег, дистрибуція скіла).
- [ ] **Повні прогони:** `python3 "$G" 1800 3072 npm test` (обидва Python окремо під `/usr/bin/python3`), живі по одному (перелік Task 7 + `shell`, `canvas`); голдени без `UPDATE_*`; `git status` — лише заплановані файли; `ls ~/deai-work` без змін.

---

## Після всіх задач (контролер)

Фінальне ревʼю (Sonnet, послідовно: живі тести) → виправлення → повторне ревʼю → прогони на знімку → дата в CHANGELOG → тег `v0.20.0` → push → памʼять. ⛔ Міграцію на справжньому `~/.deai` власника не запускати: вона станеться сама при першому старті канваса 0.20 (порядок серверного старту — порт, потім міграція, потім serve — не міняти). Перевірити перед тегом: `git diff v0.19.0 -- app bin | grep -nE "<імʼя користувача>"` → нуль.

---

## Додаток: повний `tests/test_liga_migrate_d.py` (прототип, 46 тестів; джерело для класів Task 1–3)

Класи: `Before4d4aShape` (Task 1), `StepDConstants`, `AdapterApplies`, `StepDPlanTest`, `StepDRunTest` (Task 2), `LifoFourSteps`, `FourStepsStartup` (Task 3). У прототипі лишилась одна навмисно «термінова» помилка: `test_the_view_asks_the_same_function` — дійсний лише у Task 2 (адаптер ще є у `_TrackView`); з Task 4 його видаляють, а місце займає `NoTracksAdapter`.

```python
"""Міграція ЛІГИ, четвертий крок — напрямки остаточно явні (етап 4d-4a, 0.20.0).

Тут: знімок поведінки 0.19.0 (`Before4d4aShape`, Task 1); крок `liga-4d4a` — розрахунок, запис, відкат LIFO на чотири кроки, старт
і CLI (Task 2–3); паритет після міграції (`AfterMigrationParity4d4a`, Task 7). Спека
`docs/superpowers/specs/2026-11-07-liga-tracks-final-design.md`.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
BEFORE = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4a.json')

for _p in (os.path.join(os.path.dirname(_HERE), 'app'), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import spaces_guard  # noqa: E402
from make_before_4d4a import POSTS, STANDS, UNKNOWN_ONLY_IN_NOTES, VALUES  # noqa: E402  (сценарії — ті самі, що в генераторі)
from test_liga_migrate import _WriteStand  # noqa: E402  (стенд запису 4d-3a: тимчасові HOME/DEAI_HOME, CLI, пошук секретів)

_REAL = None


def setUpModule():
    """⛔ Справжній реєстр `~/.deai` стереже `spaces_guard`."""
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


SECTIONS_LIGA = ['api', 'ds', 'labels', 'registry', 'repos', 'roots', 'roots_cli', 'task_new', 'view']
SECTIONS_PLAIN = ['api', 'ds', 'labels', 'repos', 'roots', 'task_new', 'view']


class Before4d4aShape(unittest.TestCase):
    """Знімок 0.19.0 на місці й має ключі, типи та кількості сценаріїв, на які спираються тести паритету."""

    @classmethod
    def setUpClass(cls):
        with open(BEFORE, encoding='utf-8') as f:
            cls.raw = f.read()
        cls.snap = json.loads(cls.raw)

    def test_top_level_and_meta(self):
        self.assertEqual(sorted(self.snap), ['meta', 'non_loopback_attempts', 'stands'])
        self.assertEqual(sorted(self.snap['stands']), sorted(STANDS))
        self.assertEqual(self.snap['meta'], {'version': '0.19.0', 'source_commit': '80dc34a',
                                             'generator': 'tests/make_before_4d4a.py', 'volatile_stripped': []})
        self.assertEqual(self.snap['non_loopback_attempts'], 0)

    def test_machine_independent(self):
        """⛔ Ні справжніх шляхів, ні імені користувача, ні тимчасових тек, ні штампів часу: лише `~/…`/`<tmp>`."""
        me = os.path.basename(os.path.expanduser('~'))
        for bad in ('/' + 'Users/', '/home/', '/var/' + 'folders', '/' + 'private/', '/tmp/', 'before-4d4a-', 'C:\\') + ((me,) if len(me) > 2 else ()):
            self.assertNotIn(bad, self.raw, bad)
        self.assertIsNone(re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', self.raw))

    def test_sections_and_scenarios_are_exact(self):
        want_values = sorted(repr(v) for v in VALUES)
        for name, st in self.snap['stands'].items():
            self.assertEqual(sorted(st), SECTIONS_PLAIN if name == 'plain' else SECTIONS_LIGA, name)
            self.assertEqual(sorted(st['task_new']), sorted(k for k, _ in POSTS), name)
            self.assertEqual(sorted(st['roots']), sorted(want_values + (["'app'", "'web'"] if name == 'plain' else [])), name)
            tasks = ['a-%d' % i for i in range(1, 9)] + (['a-9'] if name == 'notes' else [])
            tasks = [t for t in tasks if not (name != 'notes' and t in UNKNOWN_ONLY_IN_NOTES)]
            self.assertEqual(sorted(st['labels']), tasks, name)

    def test_the_stands_witness_the_adapter(self):
        """Знімок ловить саме те, що зникне: адаптерні мітки старого запису, `profile` у відповіді API, корені адаптера."""
        s = self.snap['stands']
        self.assertEqual(s['parity']['labels']['a-2'], ['United'], 'запис лише з `profile` дає мітку адаптера')
        self.assertEqual(s['parity']['roots']["'united'"], '~/work/shared')
        for name in ('parity', 'notes', 'explicit'):
            for tid, row in s[name]['api']['task'].items():
                self.assertIn('profile', row['keys'], (name, tid))
        self.assertEqual(s['notes']['roots']["'seo'"], '~/.hidden/seo')
        self.assertEqual(s['notes']['roots']["'liga360'"], 'rel/l360')
        self.assertEqual(s['notes']['roots']["'united'"], '~/work/united', 'власний корінь united ≠ спільного')
        self.assertEqual(s['plain']['labels']['a-2'], ['united'])
        self.assertEqual(s['parity']['task_new']['track_upper']['status'], 200, 'ЛІГА 0.19 приймає будь-який рядок напрямку')
        self.assertEqual(s['plain']['task_new']['track_zzz']['code'], 'unknown-track')


# ---------------------------------------------------------------------------------------------------------------- Task 2: крок liga-4d4a

D = 'liga-4d4a'
ORIG_SPACE = b'{"name": "Liga",\n  "x": {"k": [1,  2]}}\n'


class _StepD(_WriteStand):
    """Стенд РЕАЛЬНИХ чотирьох кроків (`ALL_STEPS = (A, B, C, D)`); `_Stand.setUp` ставить `STEPS = ALL_STEPS[:1]` — тут перекриваємо.
    Конфіг `_Stand.config()`: `united` без власного кореня (паритет повний), `custom-x` зі своїм; задачі `a-1` (`track: seo`) і
    `a-2` (лише `profile: united`). `HOME`/`DEAI_HOME` патчить `_Stand.setUp`; значення вигадані."""

    def setUp(self):
        super().setUp()
        p = self.mock.patch.object(self.lm, 'STEPS', self.lm.ALL_STEPS)
        p.start()
        self.addCleanup(p.stop)

    def plan_d(self, **kw):
        return self.lm.plan(step=D, **kw)

    def marks(self):
        return self.read_json(self.space_path()).get('migrations') or {}

    def tasks(self):
        return self.read_json(self.tasks_path)['tasks']

    def hidden_root(self):
        return os.path.join(self.home, '.hidden', 'seo')         # прихована тека в домівці: `tracks.normalize` кореня не прийме

    def start(self):
        return self.quiet(self.lm.startup)


class StepDConstants(_StepD):
    def test_steps_list_and_shape(self):
        lm = self.lm
        self.assertEqual([s.mark for s in lm.ALL_STEPS], ['liga-4d3a', 'liga-4d3b', 'liga-4d3c', D])
        self.assertIs(lm.ALL_STEPS[3], lm.STEP_D)
        self.assertEqual(lm.STEPS, lm.ALL_STEPS)
        d = lm.STEP_D
        self.assertEqual((d.mark, d.roles, d.tracks, d.suffix, d.ungated), (D, (), True, '-liga-4d4a', True))
        self.assertEqual(d.entries(self.cfg, set()), {}, 'ролей крок не має')

    def test_stamp_names_tell_the_steps_apart(self):
        lm = self.lm
        self.assertIs(lm.step_of_stamp('20261107-120000-liga-4d4a'), lm.STEP_D)
        self.assertIs(lm.step_of_stamp('20261107-120000-liga-4d4a-2'), lm.STEP_D)
        self.assertIsNone(lm.step_of_stamp('20261107-120000-liga-4d4a-pre-restore'))
        self.assertIs(lm.step_of_stamp('20261107-120000-liga-4d3c'), lm.STEP_C)

    def test_new_abort_codes(self):
        self.assertIn('abort-tracks', self.lm.ABORT_CODES)
        self.assertIn('abort-records', self.lm.ABORT_CODES)
        for code in ('abort-tracks', 'abort-records'):
            self.assertTrue(self.lm._REASONS[code])
            self.assertNotIn(code, self.lm.BENIGN)


class AdapterApplies(unittest.TestCase):
    """`tracks.adapter_applies(raw, path)` — ОДИН критерій «зараз діє адаптер» (рантайм і міграція кличуть його)."""

    def test_matrix(self):
        import tracks
        good = [{'id': 'united'}]
        for raw, want in ((None, True), ([], True), ({}, True), ('x', True), (5, True), ([{'id': 'Bad'}], True),
                          ([5, None], True), (good, False), ([{'id': 'united'}, {'id': 'Bad'}], False)):
            self.assertEqual(tracks.adapter_applies(raw, '/x'), want, repr(raw))

    def test_the_view_asks_the_same_function(self):
        import serve
        import spaces
        import tracks
        liga = {'id': 'legacy', 'path': '', 'legacy': True, 'integrations': True}
        with mock.patch.object(tracks, 'adapter_applies', return_value=False) as m, \
                mock.patch.object(spaces, '_read_json', side_effect=OSError):
            self.assertFalse(serve._TrackView(liga).adapter)
        self.assertEqual(m.call_count, 1, 'вигляд питає `tracks.adapter_applies`, а не має власної копії критерію')


class StepDPlanTest(_StepD):
    """`plan(step='liga-4d4a')` — чистий розрахунок: напрямки БЕЗ воріт паритету, нотатки, записи задач."""

    def test_ready_without_the_parity_gate(self):
        """Конфіг, на якому 4d-3a відмовляється (`united` зі своїм коренем), для 4d-4a — звичайний випадок із нотаткою."""
        work = os.path.join(self.home, 'work')
        self.config(design_work_roots={'united': os.path.join(work, 'united'), 'custom-x': os.path.join(work, 'custom')})
        a = self.lm.plan(step='liga-4d3a')
        self.assertEqual(a['tracks_reason'], 'tracks-unknown-values', 'свідок: ворота 4d-3a тут закриті')
        p = self.plan_d()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', True, None))
        sj = p['space_json']
        self.assertEqual([(t['id'], t['label'], t['root'], t['repo'], t['ds']) for t in sj['tracks']], [
            ('united', 'United', os.path.join(work, 'united'), self.REPO_U, 'united'),
            ('liga360', 'LIGA360', os.path.join(work, 'shared'), '', 'liga360'),
            ('seo', 'SEO', os.path.join(work, 'shared'), self.REPO_S, 'seo'),
            ('custom-x', 'custom-x', os.path.join(work, 'custom'), '', 'custom-x')])
        self.assertEqual(sj['default_track'], 'united')
        self.assertEqual(p['notes'], ['default-root-differs'])
        self.assertEqual(sj['migrations'], {D: {'roles': [], 'tracks': True, 'records': 1, 'notes': ['default-root-differs']}})
        self.assertEqual((p['roles'], p['secrets']), ({}, {}), 'ролей і секретів крок не має')

    def test_full_parity_has_no_notes(self):
        p = self.plan_d()
        self.assertEqual((p['status'], p['tracks'], p['notes'], p['records']), ('ready', True, [], ['a-2']))

    def test_every_kind_of_note_in_a_fixed_order(self):
        work = os.path.join(self.home, 'work')
        tasks = dict(self.cfg['tasks'], w={'dir': os.path.join(work, 'w'), 'profile': 'Weird'})
        self.config(tasks=tasks,
                    design_work_roots={'united': os.path.join(work, 'united'), 'seo': self.hidden_root(), 'Bad_Key': os.path.join(work, 'b')},
                    profile_repos={'united': self.REPO_U, 'Other_Key': self.REPO_S})
        p = self.plan_d()
        self.assertEqual(p['notes'], ['root-dropped:seo', 'unknown-values', 'default-root-differs', 'non-id-keys'])
        seo = next(t for t in p['space_json']['tracks'] if t['id'] == 'seo')
        self.assertIsNotNone(seo['root'], 'у `space.json` лежить розгорнутий корінь адаптера, відкидає його читач (`normalize`)')

    def test_a_relative_root_is_rebased_not_dropped(self):
        """Відносний корінь адаптера (вів у теку відносно процесу) став відносним до теки простору — окрема нотатка."""
        sub = os.path.join(self.home, 'sp')
        os.makedirs(sub)
        self.registry(path=sub)
        self.config(design_work_roots={'liga360': 'rel/l360'})
        p = self.plan_d()
        self.assertEqual(p['notes'], ['root-rebased:liga360', 'default-root-differs'][:1] if False else p['notes'])
        self.assertIn('root-rebased:liga360', p['notes'])
        got = next(t for t in p['space_json']['tracks'] if t['id'] == 'liga360')['root']
        self.assertEqual(got, 'rel/l360', 'у `space.json` лишається значення адаптера; відносність розвʼяже `normalize`')

    def test_tasks_without_a_value_give_no_unknown_note(self):
        tasks = dict(self.cfg['tasks'], n1={'dir': '/x'}, n2={'dir': '/x', 'track': 5}, n3={'dir': '/x', 'profile': ''})
        self.config(tasks=tasks)
        self.assertNotIn('unknown-values', self.plan_d()['notes'])

    def test_notes_carry_no_paths_or_values(self):
        self.config(design_work_roots={'seo': self.hidden_root()})
        for n in self.plan_d()['notes']:
            self.assertRegex(n, r'^[a-z-]+(:[a-z0-9-]+)?$', n)

    def test_own_valid_tracks_are_kept(self):
        own = [{'id': 'web', 'label': 'Web'}]
        self.space_json({'tracks': own, 'default_track': 'web'})
        p = self.plan_d()
        self.assertEqual((p['status'], p['tracks'], p['tracks_reason']), ('ready', False, 'tracks-present'))
        self.assertEqual(p['space_json']['tracks'], own)
        self.assertEqual(p['space_json']['default_track'], 'web')
        self.assertEqual(p['records'], ['a-2'], 'записи задач крок виправляє й тоді')

    def test_empty_or_unusable_tracks_are_replaced_exactly_where_the_runtime_applies_the_adapter(self):
        for raw in ([], {}, [{'id': 'Bad'}], [5, None], None):
            self.space_json({'tracks': raw})
            p = self.plan_d()
            self.assertEqual((p['status'], p['tracks']), ('ready', True), repr(raw))

    def test_records_matrix(self):
        recs = {'fix1': {'profile': 'seo'}, 'fix2': {'track': '', 'profile': 'seo'}, 'fix3': {'track': 5, 'profile': 'seo'},
                'fix4': {'track': None, 'profile': 'zzz'}, 'keep1': {'track': 'a', 'profile': 'b'}, 'keep2': {'profile': ''},
                'keep3': {'profile': 5}, 'keep4': {}, 'keep5': 'not a dict', 'keep6': {'track': 'x'}}
        self.assertEqual(self.lm._records_to_fix({'tasks': recs}), ['fix1', 'fix2', 'fix3', 'fix4'])
        for bad in (None, [], {}, {'tasks': None}, {'tasks': []}):
            self.assertEqual(self.lm._records_to_fix(bad), [])

    def test_skip_nothing_when_there_is_nothing_to_write(self):
        self.space_json({'tracks': [{'id': 'web'}]})
        self.config(tasks={'a-1': {'dir': '/x', 'track': 'seo'}, 'a-2': {'dir': '/y', 'profile': ''}})
        before = self.snapshot_tree()
        p = self.plan_d()
        self.assertEqual((p['status'], p['space_json']), ('skip-nothing', None))
        self.assertEqual(self.lm.run(step=D), 'skip-nothing')
        self.assertEqual(self.snapshot_tree(), before, 'позначки й бекапу нема: наступний старт перевірить знову')

    def test_abort_tracks_when_the_calculated_list_differs_from_the_adapter(self):
        """Понад `MAX_TRACKS` (20) id: `normalize` відкинув би зайві, тож явний список ≠ адаптеру — нічого не пишемо."""
        keys = {'t%02d' % i: self.REPO_U for i in range(21)}
        self.config(profile_repos=keys)
        p = self.plan_d()
        self.assertEqual((p['status'], p['space_json']), ('abort-tracks', None))
        self.assertTrue(p['reason'])
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(step=D), 'abort-tracks')
        self.assertEqual({k: v for k, v in self.snapshot_tree().items() if os.sep + 'migrations' + os.sep not in k},
                         {k: v for k, v in before.items() if os.sep + 'migrations' + os.sep not in k}, 'жодного запису, крім журналу')

    def test_skip_codes(self):
        cases = {'skip-integrations-off': lambda: self._write(os.path.join(self.deai, 'spaces.json'), json.dumps(
                     {'version': 1, 'current': 'legacy', 'spaces': [{'id': 'legacy', 'path': self.space_dir, 'legacy': True, 'integrations': False}]})),
                 'skip-done': lambda: self.space_json({'migrations': {D: {'at': 'x', 'roles': []}}}),
                 'skip-held': lambda: self.space_json({'migrations': {D: {'held': True}}}),
                 'skip-path-in-git': lambda: os.makedirs(os.path.join(self.space_dir, '.git')),
                 'skip-space-json-unreadable': lambda: self.space_json('{broken'),
                 'skip-tasks-unreadable': lambda: self._write(self.tasks_path, '{broken')}
        for code, arrange in cases.items():
            self.setUp_clean()
            arrange()
            self.assertEqual(self.plan_d()['status'], code, code)

    def setUp_clean(self):
        for p in (self.space_path(), os.path.join(self.space_dir, '.git')):
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)
        self.registry()
        self.config()

    def test_an_earlier_held_step_holds_d_with_its_own_text(self):
        self.space_json({'migrations': {'liga-4d3c': {'held': True}}})
        p = self.plan_d()
        self.assertEqual(p['status'], 'skip-held')
        self.assertIn('liga-4d3c', p['reason'])

    def test_plan_is_pure_and_the_report_has_the_counts(self):
        before = self.snapshot_tree()
        p = self.plan_d()
        self.assertEqual(self.snapshot_tree(), before)
        text = self.lm.report(p, D)
        self.assertIn('liga-4d4a: ready', text)
        self.assertIn('tracks: migrate', text)
        self.assertIn('records: 1; notes: -', text)
        self.assert_no_secrets(text)


class StepDRunTest(_StepD):
    """`run(step='liga-4d4a')`: бекап → записи задач → ОДИН запис `space.json` з позначкою."""

    def seed(self):
        self._write(self.space_path(), ORIG_SPACE.decode('utf-8'))
        os.chmod(self.space_path(), 0o644)

    def test_run_writes_tracks_records_mark_and_backup(self):
        self.seed()
        old_tasks = self.read(self.tasks_path)
        old_a1 = self.tasks()['a-1']
        self.assertEqual(self.lm.run(step=D), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual((sj['name'], sj['x']), ('Liga', {'k': [1, 2]}), 'чужі ключі space.json збережено')
        self.assertEqual([t['id'] for t in sj['tracks']], ['united', 'liga360', 'seo', 'custom-x'])
        mark = sj['migrations'][D]
        self.assertEqual(sorted(mark), ['at', 'backup', 'notes', 'records', 'roles', 'tracks'])
        self.assertEqual((mark['roles'], mark['tracks'], mark['records'], mark['notes']), ([], True, 1, []))
        t = self.tasks()
        self.assertEqual((t['a-2']['track'], t['a-2']['profile']), ('united', 'united'), '`profile` лишається (спільний реєстр)')
        self.assertEqual(t['a-1'], old_a1, 'запис, що вже має `track`, не чіпаємо')
        self.assertEqual(self.read(self.tasks_path + '.bak'), old_tasks, '`.bak` — як у `serve.save_tasks`')
        b = os.path.join(self.deai, 'backups', mark['backup'])
        self.assertEqual(self.read(b, 'tasks.json'), old_tasks, 'бекап кроку містить tasks.json ДО запису')
        self.assertEqual(self.read_json(b, 'manifest.json')['migration'], D)
        self.assertEqual(self.backups(), [mark['backup']])
        self.assert_no_secrets_in_logs()

    def test_the_second_start_is_skip_done_and_writes_nothing(self):
        self.assertEqual(self.lm.run(step=D), 'done')
        before = self.snapshot_tree()
        self.assertEqual(self.lm.run(step=D), 'skip-done')
        self.assertEqual(self.snapshot_tree(), before)

    def test_tasks_file_is_reread_under_the_lock_before_writing(self):
        """Задача, додана між розрахунком і записом, теж виправляється; чужі правки не губляться."""
        real = self.lm._backup

        def backup_then_add_a_task(*a, **kw):
            name = real(*a, **kw)
            cfg = self.read_json(self.tasks_path)
            cfg['tasks']['late'] = {'dir': '/x', 'profile': 'seo'}
            cfg['jira_base'] = 'https://jira.example.com/changed'
            self._write(self.tasks_path, cfg)
            return name
        with self.mock.patch.object(self.lm, '_backup', backup_then_add_a_task):
            self.assertEqual(self.lm.run(step=D), 'done')
        cfg = self.read_json(self.tasks_path)
        self.assertEqual((cfg['tasks']['late']['track'], cfg['tasks']['a-2']['track']), ('seo', 'united'))
        self.assertEqual(cfg['jira_base'], 'https://jira.example.com/changed')
        self.assertEqual(self.marks()[D]['records'], 2, 'у позначці — скільки записано насправді')

    def test_a_failed_space_write_leaves_harmless_records_and_the_next_run_starts_over(self):
        with self.mock.patch.object(self.lm, '_write_space', side_effect=OSError):
            self.assertEqual(self.lm.run(step=D), 'abort-write')
        self.assertNotIn(D, self.marks() if os.path.exists(self.space_path()) else {})
        self.assertEqual(self.tasks()['a-2']['track'], 'united', 'записи вже є — нешкідливо (`track` = `profile`)')
        self.assertEqual(self.lm.run(step=D), 'done')
        mark = self.marks()[D]
        self.assertEqual((mark['tracks'], mark['records']), (True, 0), 'другий прогін: напрямки пишуться, записів уже нема')

    def test_a_failed_tasks_write_is_abort_records_and_space_json_stays(self):
        self.seed()
        before_space = self.read(self.space_path())
        with self.mock.patch.object(self.lm.shutil, 'copy2', side_effect=OSError):
            self.assertEqual(self.lm.run(step=D), 'abort-records')
        self.assertEqual(self.read(self.space_path()), before_space)
        self.assertEqual(self.read_json(self.deai, 'migrations', 'last.json')['status'], 'abort-records')
        self.assertEqual(self.lm.run(step=D), 'done')

    def test_owner_tracks_written_after_the_plan_are_not_overwritten(self):
        """Між розрахунком і записом власник додав свої напрямки: ворота «адаптер діє» перевіряються ще раз під замком."""
        real = self.lm._backup

        def backup_then_own_tracks(*a, **kw):
            name = real(*a, **kw)
            self._write(self.space_path(), json.dumps({'tracks': [{'id': 'web', 'label': 'Web'}], 'default_track': 'web'}))
            return name
        with self.mock.patch.object(self.lm, '_backup', backup_then_own_tracks):
            self.assertEqual(self.lm.run(step=D), 'done')
        sj = self.read_json(self.space_path())
        self.assertEqual([t['id'] for t in sj['tracks']], ['web'])
        self.assertEqual(sj['migrations'][D]['tracks'], False, 'позначка каже, що напрямків крок НЕ писав')

    def test_restore_puts_back_space_json_only_and_keeps_the_tasks_file(self):
        """⛔ Відкат повертає `space.json` (як і для 4d-3a…c) і НЕ чіпає `tasks.json`: той файл — жива база, у ній уже нові задачі."""
        self.seed()
        before_space = self.read(self.space_path())
        self.assertEqual(self.lm.run(step=D), 'done')
        stamp = self.backups()[0]
        cfg = self.read_json(self.tasks_path)
        cfg['tasks']['fresh'] = {'dir': '/x', 'title': 'created after the migration'}
        self._write(self.tasks_path, cfg)
        self.assertEqual(self.lm.restore(stamp), 'restored')
        self.assertEqual(self.read(self.space_path()), before_space)
        t = self.tasks()
        self.assertIn('fresh', t)
        self.assertEqual(t['a-2']['track'], 'united', '`track = profile` безпечний для 0.19: мітка й ДС ті самі')

    def test_no_secret_anywhere(self):
        code, out, err = self.cli('run')
        self.assertEqual(code, 0)
        self.assert_no_secrets(out, err)
        self.assert_no_secrets_in_logs()


# ---------------------------------------------------------------------------------------------------------------- Task 3: LIFO, старт, CLI

class LifoFourSteps(_StepD):
    """Відкат LIFO на чотири кроки; відмова називає ОСТАННІЙ застосований бекап (тепер це бекап кроку d)."""

    def setUp(self):
        super().setUp()
        self._write(self.space_path(), ORIG_SPACE.decode('utf-8'))
        for s in self.lm.ALL_STEPS[:3]:
            self.assertEqual(self.lm.run(step=s), 'done', s.mark)
        self.after_abc = (self.read(self.space_path()), os.path.exists(self.secrets_path()) and self.read(self.secrets_path()))
        self.assertEqual(self.lm.run(step=D), 'done')
        self.a, self.b, self.c, self.d = [next(x for x in self.backups() if x.endswith(s)) for s in ('4d3a', '4d3b', '4d3c', '4d4a')]

    def test_restore_of_an_earlier_step_is_refused_naming_d_and_writes_nothing(self):
        for stamp in (self.a, self.b, self.c):
            before = self.snapshot_tree()
            st, info = self.lm._restore(stamp)
            self.assertEqual((st, info['rollback_first']), ('refuse-later-applied', self.d), stamp)
            self.assertEqual(self.lm.restore(stamp, hold=True), 'refuse-later-applied')
            self.assertEqual(self.snapshot_tree(), before)

    def test_cli_names_d_and_exits_nonzero(self):
        code, out, _err = self.cli('restore', self.c)
        self.assertEqual(code, 1)
        self.assertIn(self.d, out)
        self.assertNotIn(self.b, out)

    def test_in_order_d_then_c_then_b_then_a(self):
        self.assertEqual(self.lm.restore(self.d), 'restored')
        self.assertEqual(self.read(self.space_path()), self.after_abc[0], 'space.json — побайтно стан після c')
        self.assertEqual(self.lm.restore(self.b), 'refuse-later-applied')
        self.assertEqual(self.lm.restore(self.c), 'restored')
        self.assertEqual(self.lm.restore(self.b), 'restored')
        self.assertEqual(self.lm.restore(self.a), 'restored')

    def test_hold_of_d_holds_only_d(self):
        self.assertEqual(self.lm.restore(self.d, hold=True), 'restored')
        marks = self.marks()
        self.assertEqual(marks[D], {'held': True})
        self.assertEqual({k: ('held' in v) for k, v in marks.items() if k != D}, {'liga-4d3a': False, 'liga-4d3b': False, 'liga-4d3c': False})
        self.assertEqual(self.plan_d()['status'], 'skip-held')
        self.assertEqual(self.lm.run(step=D), 'skip-held')

    def test_a_held_d_does_not_hold_the_earlier_steps(self):
        self.assertEqual(self.lm.restore(self.d, hold=True), 'restored')
        self.assertEqual(self.lm.restore(self.c), 'restored', 'ранні кроки відкочуються далі')

    def test_a_held_c_holds_d_on_the_next_start(self):
        self.assertEqual(self.lm.restore(self.d), 'restored')
        self.assertEqual(self.lm.restore(self.c, hold=True), 'restored')
        p = self.plan_d()
        self.assertEqual(p['status'], 'skip-held')
        self.assertIn('liga-4d3c', p['reason'])


class FourStepsStartup(_StepD):
    """`startup()`/CLI: чотири кроки по порядку; підсумок напрямків одним рядком; підказка відкату — для останнього кроку."""

    def test_order_backups_and_one_restore_hint(self):
        st, err = self.start()
        self.assertEqual(st, 'done')
        marks = [m for m in re.findall(r'^(liga-4d\w+): done', err, re.M)]
        self.assertEqual(marks, ['liga-4d3a', 'liga-4d3b', 'liga-4d3c', D])
        stamps = self.backups()
        self.assertEqual(len(stamps), 4)
        self.assertEqual(err.count('відкат:'), 1)
        self.assertIn('відкат: bin/migrate_liga.py restore %s --hold' % stamps[-1], err)
        self.assertIn('раніші кроки (%s)' % ', '.join(stamps[:3]), err)
        last = self.read_json(self.deai, 'migrations', 'last.json')
        self.assertEqual(sorted(last['steps']), ['liga-4d3a', 'liga-4d3b', 'liga-4d3c', D], 'звіт d не стирає звіти a, b, c')
        self.assertEqual(last['step'], D)

    def test_the_tracks_line_has_the_notes_and_no_paths(self):
        work = os.path.join(self.home, 'work')
        self.config(design_work_roots={'united': os.path.join(work, 'united'), 'seo': self.hidden_root()})
        _st, err = self.start()
        line = next(x for x in err.splitlines() if x.strip().startswith('напрямки:'))
        self.assertEqual(line.strip(), 'напрямки: записано; записи: 1; нотатки: root-dropped:seo, default-root-differs')
        self.assertNotIn(self.home, err)
        self.assert_no_secrets(err)

    def test_a_clean_parity_run_says_only_the_tracks_and_records(self):
        _st, err = self.start()
        line = next(x for x in err.splitlines() if x.strip().startswith('напрямки:'))
        self.assertEqual(line.strip(), 'напрямки: вже явні; записи: 1', 'крок а уже записав напрямки — d дописує лише записи')

    def test_skip_nothing_of_d_is_silent_and_the_second_start_prints_nothing(self):
        self.start()
        st, err = self.start()
        self.assertEqual((st, err), ('skip-done', ''))

    def test_the_not_migrated_line_when_d_is_skipped_for_a_reason(self):
        self.space_json({'migrations': {D: {'held': True}}})
        _st, err = self.start()
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, err)
        self.assertIn('нові задачі лягають у теку простору', err)
        os.makedirs(os.path.join(self.space_dir, '.git'))
        self.space_json({})
        _st, err = self.start()
        self.assertIn('liga-4d4a: skip-path-in-git', err)
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, err)

    def test_not_said_when_nothing_is_wrong(self):
        self.start()
        _st, err = self.start()
        self.assertNotIn(self.lm.TRACKS_NOT_MIGRATED, err)

    def test_an_abort_of_d_is_the_start_result_and_is_not_masked(self):
        self.config(profile_repos={'t%02d' % i: self.REPO_U for i in range(21)})
        st, err = self.start()
        self.assertEqual(st, 'abort-tracks')
        self.assertIn('liga-4d4a: abort-tracks', err)
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, err)
        self.assertEqual(len([m for m in re.findall(r'^liga-4d\w+: done', err, re.M)]), 3, 'a, b, c пройшли')

    def test_cli_run_dry_run_and_status(self):
        code, out, _err = self.cli('dry-run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4a: ready', out)
        self.assertIn('records: 1; notes: -', out)
        code, out, _err = self.cli('run')
        self.assertEqual(code, 0)
        self.assertIn('liga-4d4a: done', out)
        self.assertIn('  напрямки: вже явні; записи: 1; бекап: ', out)
        self.assertEqual(out.count('відкат:'), 1)
        code, out, _err = self.cli('status')
        self.assertEqual(code, 0)
        self.assertIn('ролі: -, напрямки: ні, записи: 1, нотатки: -', out)
        self.assert_no_secrets(out)

    def test_cli_prints_the_not_migrated_line_for_a_refused_step(self):
        self.space_json({'migrations': {D: {'held': True}}})
        code, out, _err = self.cli('run')
        self.assertEqual(code, 0, 'skip-held — не помилка')
        self.assertIn(self.lm.TRACKS_NOT_MIGRATED, out)
```

