# Етап 4d-4c «Прапорця `integrations` і значення `'legacy'` нема» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** після 0.22 жодне рішення рантайму не залежить від прапорця простору `integrations`: роль = явний запис `space.json`, вихідна дія (автопуш, пуш у реєстр команди, `ssh`/`gitlab`-ціль, `profile` у новій задачі) = ввімкнений запис `vcs` зі схемою ЛІГИ (`compat: design-canvas`) — предикат `deai_modules.vcs_outbound(space)`. `static-publish` стає явним записом (новий простір пише його сам, наявні — ідемпотентний стартовий крок). Значення API `'legacy'`, `_liga_flow`, 409 `no-integrations-space`, `OVERVIEW_LOG`, запасні гілки JS — геть; `/api/gitlab-*` лишаються до 1.0 із заголовком `Deprecation`.

**Architecture:** `vcs_outbound` читає той самий кеш `_capabilities_full`, що й `capabilities` (ключ кешу `_caps_key` уже містить відбиток `space.json`, тож зміна `compat` — промах кешу; окремого кешу не треба). Споживачі беруть простір запиту через `spaces.effective_space()` (неявний простір → `False`, закрито). Паритет доводиться знімком вихідних рішень 0.21 (`tests/make_before_4d4c.py`) і порівнянням «після» з явним переліком `EXPECT_DIFF`.

**Tech Stack:** Python 3 stdlib (`unittest`, 3.9-сумісний: без `match`, без `X | Y` в анотаціях), ванільний ES-модульний JS (`node:test`), Playwright Chromium (живі).

**Спека:** `docs/superpowers/specs/2026-11-10-legacy-surface-gone-design.md`. Читати перед кожною задачею; **ПОПРАВКИ НИЖЧЕ мають перевагу над текстом спеки й задач.** Попередній етап (зразок процесу): `docs/superpowers/plans/2026-11-07-liga-originals-gone.md`.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так, з переліком шляхів; новий файл спершу `git add -- <шлях>`:
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "<тема>

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  **Ніколи** `git add -A` / `git add .`; не стейджити `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `docs/superpowers/specs/2026-11-09-agents-sdk-policy-addendum.md`; ніколи `--amend`. Після кожної задачі `git diff HEAD | grep '^-[^-]'` показує лише заплановані видалення.
- ⛔ У жоден комітований файл не пишемо шляхів з імʼям користувача машини, шляхів scratchpad чи тимчасових тек; лише `<repo>`, `<DEAI_HOME>`, `os.path.expanduser('~')`.
- Правки наявних файлів — точкові (`Edit`); нові файли — `Write`.

**Прогони й середовище** (кожен Python-прогін — під тимчасовим `HOME`, без `DC_TASKS_FILE`/`DEAI_HOME` в оточенні; без `.pyc`)

- `PYT` = `env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest`
  - один файл: `$PYT tests.test_outbound -v`; весь пакет:
    ```bash
    env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s tests -p 'test_*.py'
    env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s bin -p 'test_*.py'
    env -u DC_TASKS_FILE -u DEAI_HOME HOME=$(mktemp -d) python3 -B -m unittest discover -s app -p 'test_*.py'
    ```
- JS: `node --test tests/*.test.mjs && node tests/inspector-core.test.mjs`.
- Живі — по одному файлу, ПОСЛІДОВНО (`test-concurrency=1`):
  `HOME=$(mktemp -d) node --test --test-concurrency=1 --import ./tests/live/_env.mjs tests/live/<файл>.test.mjs`.
- Після прогонів справжні `~/.deai`, `~/deai-work`, `~/deai-published`, `~/.claude/pipeline-feedback/` не змінились; порти 8765/4317 і мережа не чіпаються; процеси — лише за PID.
- Знеособлено: лише вигадані значення (`https://sb.example.com`, `git@git.example:org/x.git`, `203.0.113.7`, `alpha@example.com`).
- Кожна нова перевірка доводиться мутацією (`python3 -B`, один рядок → червоніє → відновлено, `sha256` до/після збігається). Охоронець, який не може впасти, — фікція. Еталони (`legacy-golden`, знімки `before-4c1…4d4b`) — зелені БЕЗ `UPDATE_*`.
- **Порядок.** Після кожної задачі ВЕСЬ пакет (Python + JS) зелений; тести, які ламає задача, правляться в ТІЙ САМІЙ задачі. Невідомі падіння шукаються повним прогоном; кожна зміна наявного тесту — у звіті одним рядком із причиною, нічого не видаляємо мовчки.

---

## Поправки до спеки (звірено з кодом на `ef47f46`; мають перевагу)

1. **[КРИТИЧНО] Міграція ЛІГИ гейтиться сирим ключем `integrations`, а перша міграція реєстру його більше не пише.** `app/liga_migrate.py:651` (`if liga.get('integrations') is not True: raise _Stop('skip-integrations-off')`), `:610/:686/:730/:1778-1780`; ключ досі ставить `spaces.load_registry` (`app/spaces.py:317`, `has_markers(cfg)`). Спека Р1 («не виставляє») без доповнення зробила б так, що **свіжа ЛІГА (справжній перехід) назавжди `skip-integrations-off`**. Рішення: у `liga_migrate` приватна `_liga_integrations(liga)` — явний `bool` ключа виграє (історичні записи 0.21), а коли ключа нема — за маркерами кореня `tasks.json` (`_has_markers`, переїхала з `spaces`); охоронець маркера `marker-kept` лишається. Усі шість читань ключа в `liga_migrate` ідуть через неї (T6).
2. **Д6 спеки спирається на хибну передумову.** Фонових воркерів без простору в сервері нема: обробник фіксує простір на вході кожного запиту (`serve.py:5797`, `:5864`, `:7673`), усі потоки обгорнуті `_in_space` (`serve.py:5099`, `:5531`, `:6614`); `request_space_id() is None` буває лише в CLI-інструментах і тестах. `git_autocommit(task_dir, msg, push=None)` (`serve.py:208`) має лише `task_dir`, без id задачі, тож `spaces.find_task` недоступний. Рішення: вихідне рішення — `deai_modules.vcs_outbound(spaces.effective_space())`; незафіксований простір = неявний (`IMPLICIT`, записів нема) → `False`, закрито, БЕЗ `find_task` і БЕЗ зміни підписів. Усі виклики `git_autocommit` — з обробників запиту (`serve.py:1306, 1502, 2418, 5757, 7058, 7083, 7109, 7253, 7267, 7365, 7490, 8214, 8264`); тест T3 пінить, що потік через `_in_space` несе простір.
3. **`IntegrationsOff` не мертвий.** Кидається в `serve.py:3396` (`ProjectComments._check`), ловиться в `bin/inbox.py:377,482`, `bin/state.py:305`; код відповіді `integrations-off` — у `serve.py:2591, 6363, 6750, 7141` і в живому `tests/live/comments.test.mjs:639`. Рішення (за замовчуванням; див. «Рішення контролера»): клас перейменовується в `spaces.RoleOff(OSError)` («роль ніхто не веде»), рядок коду API `integrations-off` лишається.
4. **`NoIntegrationsFlag` мусить мати один виняток:** `spaces._validate` (`spaces.py:160`) терпить ключ (Р1) → літерал `'integrations'`. Дозвіл за парою `(файл, функція)`; мутація доводить, що читання деінде — червоне.
5. **У інвентарі спеки нема `serve.py:5198`** — `spaces_listing` читає `e['integrations']` (`sp = {'id', 'path', 'integrations'}`). Прибирається в T6.
6. **Правило матеріалізації `static-publish` («нема жодного запису ролі `publish`») нерозв'язне за сирим JSON без каталогу.** Паритет 0.21: неявний `static-publish` програвав лише ВВІМКНЕНОМУ явному публікатору (`deai_modules.py:949-960`: явні — перед неявним), вимкнений `vercel-publish` його НЕ скасовував. Точне правило (T5): додаємо запис, якщо (а) `modules` не містить ключа `static-publish` (будь-який стан — рішення людини) і (б) нема ВВІМКНЕНОГО запису, що веде `publish` (`id == 'vercel-publish'` або `roles` містить `'publish'`). `create_space` бере блокування `WRITE_LOCK` (нереентерабельне, `spaces.py:~790`), тож матеріалізація — пара «`_ensure_…_locked` / публічна з локом». Усиновлена тека з готовим `space.json` (`create_space` його не чіпає) теж проходить `ensure`.
7. **Точка старту:** `serve.serve_main` (`serve.py:9041-9046`) — після `liga_migrate.startup()`. `liga_migrate.startup()` у ізольованому прогоні виходить рано, але крок `static-publish` НЕ мусить (живі тести ізольовані з тимчасовим `DEAI_HOME`): умова — `spaces.layer_on()` і НЕ (`isolation.isolated()` і `isolation.real_home(spaces.home())`).
8. **Д2: `from` + `gitlab` разом** спека не покриває; `_task_new_write` і усиновив би теку, і клонував. Рішення: 400 `bad-request` («from cannot be combined with gitlab»), без нового коду/i18n. `gitlab` у тілі для простору без `vcs_outbound` — 400 `gitlab-needs-vcs-scheme`, **і для немігрованої ЛІГИ, і в режимі «шар вимкнено»** (спека §Свідомі відмінності 3 каже «як у 0.21» лише про маршрутизацію).
9. **Порядок у `_task_new`:** `liga = integrations_for(sp)` обчислюється ДО `spaces.set_request_space(sp['id'])` (`serve.py:7865` проти `:7880`). `vcs_outbound(sp)` рахуємо ПІСЛЯ фіксації простору (каталог може вантажити свої модулі в потоці, що успадковує простір запиту). `_adopt_source` має власну перевірку `integrations_for(sp)` (`serve.py:7729`) — теж іде.
10. **`comment_channel` у `/api/task` (Д5):** виноситься в `serve._task_comment_channel(sp, task, tid)` (тестується без HTTP). Зміни поведінки, що йдуть у `EXPECT_DIFF`: звичайний простір із модулем коментарів тепер має канал (додається); немігрована ЛІГА без запису `comments` — `None`. `comments_prov_cached` вимагає зафіксований простір (в обробнику завжди так).
11. **`default_new_task_space` (Д1):** запис ЛІГИ з `integrations: false` (старий файл без маркерів) тепер обирається за `legacy: true` — свідома зміна (снап-шот її не вимірює: стенди мають маркери).
12. **Ключ `implicit` у записах `/api/modules`** (`deai_modules.py:944`, `connections-view.js:120`, `wizard-view.js:125`) лишається (завжди `False`, тег `cnImplicit` мертвий) — прибрати до 1.0; спека його не згадує. Тести `test_modules_api.py:324,367-374,452-454,746` міняють очікування.
13. **Окремий «after-колектор» не потрібен:** підписи `git_autocommit(task_dir, msg)`, `vcs_target(tid, task, settings)`, `_registry_push(tid)` однакові в 0.21 і 0.22, тож `tests/make_before_4d4c.py` має одну функцію `collect(tmp)`; еталон знято з `v0.21.0`, «після» — та сама функція на новому коді.
14. **JS:** сервер перестає слати `integrations` (T6), тож `space?.integrations !== false` вже тривіально `true` — запасні гілки замінюються на `true` (поведінка на справжніх відповідях та сама). `isLegacyVcs`/`isLegacyPublish` лишають запасний «невідомо → ЛІГА» (`!caps` / ключа `vcs` нема), інакше мітки «GitLab» для `null`-простору зміняться. Лише коментарі: `bar-model.js`, `shell-palette.js`, `shell-bar.js`, `connections-view.js`; код: `spaces-model.js`, `tasks-home.js`, `app.js:7176`. Золота розмітка тримається, бо ЛІГА в наборі виражається через `compat`.
15. **Охоронці:** `NoLegacyLiteral` (Python AST) лишається — він пройде і охороняє ядро; `LigaLikePin` (`test_implicit.py:622-631`) видаляється з `_liga_like`; `PROFILE_OK` у `test_no_adapter.py:20` втрачає `_liga_flow`; `NoOriginalsRead.ALLOWED` стає порожнім (T6/T7); `PublishJsGuard` (`test_liga_migrate_c.py:765-777`) очікує `{}`.
16. **`app.js:1960` `view.kind === 'legacy'` — вигляд `publishReaction`, лишається** (Д7); `NoLegacyApiValue` дозволяє лише рядки з `view.kind`.
17. **Заголовок `Deprecation`:** у `Handler.end_headers` (покриває й `send_error`), атрибут `_successor` скидається в `_guarded` (поруч із `_resp_started`, `serve.py:5656`).
18. **Журнал синку без `legacy`:** `_overview_log_path()` бере `spaces.home()`; до запуску синку доходить лише простір із постачальником `dashboard` (шар увімкнено), тож у шарі «вимкнено» справжній `~/.deai` не пишеться.
19. **Тестовий інвентар** (за `grep`): Python — `test_spaces.py` (58 згадок), `test_modules.py` (48), `test_dashboard.py` (34), `test_spaces_serve.py` (31), `test_integrations_off.py`, `test_comments_role.py`, `test_notify.py`, `test_publish_module.py`, `test_liga_migrate*.py`, `test_vcs_core.py`, `test_comments_agent.py`, `test_legacy_comments.py`, `test_task_tags.py`, `test_task_from.py`, `test_tasks_overview.py`, `test_tracks.py`, `test_serve.py`, `test_static_publish.py`, `test_modules_api.py`, `bin/test_overview_push.py`; JS — `bar-model`, `connections-model`, `connections-view`, `shell-palette`, `shell-bar`, `spaces-model`, `spaces-state`, `spaces-wiring`, `spaces-publish`, `tasks-home`, `vcs-client`, `caps-role-errors`, `_legacy-golden-kit.mjs`; живі — `tests/live/{fixture,modules,spaces,comments,dashboard-role}`. Знімки `make_before_*.py`/`after_4d4b_collect.py` — заморожені, їх не чіпаємо (ключ `integrations` реєстр толерує).
20. **Уточнення Р3 (після ревʼю T5): `legacy`-простір без ЛІГИ матеріалізується.** «Без `legacy: true`» зі спеки уточнено: `legacy`-простір, що не є ЛІГОЮ за `liga_migrate._liga_integrations` (явний `bool` ключа `integrations` виграє, інакше — маркери кореня старого `tasks.json`, збій читання = ЛІГА), теж дістає запис `static-publish` — паритет із 0.21 `_implicit_on` (`not integrations`); інакше старий звичайний простір без маркерів утратив би публікацію (409 `no-publish-module`). Немігрована ЛІГА не чіпається. `spaces.materialize_static_publish(skip=None)`: без предиката пропускає кожен `legacy`, `serve_main` передає `liga_migrate.liga_space`; `spaces` не імпортує `liga_migrate`. Збій одного запису реєстру решту не зупиняє.

### Рішення контролера (потрібні до старту)

- **R-A** `IntegrationsOff` → `spaces.RoleOff` (Поправка 3). Рекомендація: так.
- **R-B** `gitlab` у `task-new` для немігрованої ЛІГИ — 400 (Поправка 8) чи дозволяти за `legacy: true`. Рекомендація: 400 за спекою (ролі вимкнені, бутстрапити нічим).
- **R-C** Ключ `implicit` у `/api/modules` лишити до 1.0 (Поправка 12). Рекомендація: лишити.

**Прийнято контролером 10.11.2026:** R-A — так (`RoleOff`, код API `integrations-off` лишається); R-B — 400 `gitlab-needs-vcs-scheme`;
R-C — лишити. Поправки 1–19 прийнято. `bin/state.py` (`_registry_line`) бере простір задачі, який фіксує `task_anywhere`, а не
незафіксований (інакше CLI-рядок реєстру ЛІГИ зник би) — перевірити тестом у T3.

---

## Структура файлів

**Нові:** `tests/make_before_4d4c.py`, `tests/fixtures/outbound/before-4d4c.json`, `tests/test_before_4d4c.py`, `tests/test_outbound.py`, `tests/test_static_publish_explicit.py`, `tests/test_overview_log.py`, `tests/test_gitlab_aliases.py`, `tests/test_no_integrations_flag.py`, `tests/test_outbound_parity_4d4c.py`, `tests/space-predicates.test.mjs`, `tests/_space-fixtures.mjs`.
**Змінюються (код):** `app/deai_modules.py`, `app/spaces.py`, `app/serve.py`, `app/liga_migrate.py`, `bin/state.py`, `bin/inbox.py`, `app/spaces-model.js`, `app/connections-model.js`, `app/connections-view.js`, `app/tasks-home.js`, `app/app.js`, `app/i18n.js`, `app/modules/static-publish/server.py` (лише коментар).
**Змінюються (тести/документи):** див. задачі; документи — `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `package.json`.

---

### Task 1: знімок вихідних рішень 0.21.0 (ДО будь-якої правки коду)

**Files:** Create `tests/make_before_4d4c.py`, `tests/fixtures/outbound/before-4d4c.json` (генерується), `tests/test_before_4d4c.py`.

Знімок фіксує, що 0.21 вирішує через прапорець: автопуш (стенд із фіксованим простором і без), пуш у реєстр, `vcs_target` (`gitlab`/`vcs`), `comment_channel`, маршрут `task-new` (`jira`/`plain`/`gitlab`/`from`) на п'яти стендах: `liga` (мігрована: шість явних записів), `liga_unmigrated`, `plain`, `plain_git` (запис `git-sync` без `compat`), `layer_off`.

- [ ] **Step 1: тест форми (червоний).** `tests/test_before_4d4c.py`:
  ```python
  """Форма знімка вихідних рішень 0.21.0 (етап 4d-4c, Task 1): сам знімок — еталон, цей тест лише стереже його форму й машинонезалежність."""
  import json
  import os
  import unittest

  FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'outbound', 'before-4d4c.json')
  STANDS = ('liga', 'liga_unmigrated', 'plain', 'plain_git', 'layer_off')
  SECTIONS = ('autocommit', 'autocommit_unfixed', 'registry', 'targets', 'comment_channel', 'task_new')
  BODIES = ('jira', 'plain', 'gitlab', 'from')


  class Before4d4cShape(unittest.TestCase):
      @classmethod
      def setUpClass(cls):
          with open(FIX, encoding='utf-8') as f:
              cls.snap = json.load(f)

      def test_meta_and_stands(self):
          self.assertEqual(self.snap['_meta']['code'], '0.21.0')
          self.assertEqual(sorted(k for k in self.snap if not k.startswith('_')), sorted(STANDS))

      def test_every_stand_has_every_section(self):
          for st in STANDS:
              self.assertEqual(sorted(self.snap[st]), sorted(SECTIONS), st)
              self.assertEqual(sorted(self.snap[st]['task_new']), sorted(BODIES), st)

      def test_values_that_0_21_decided_by_the_flag(self):
          s = self.snap
          self.assertIs(s['layer_off']['autocommit']['pushed'], True)          # шар вимкнено: «інтеграції ввімкнено»
          self.assertIs(s['liga']['autocommit_unfixed']['pushed'], True)       # простір не зафіксовано: так само
          self.assertIs(s['plain']['autocommit']['pushed'], False)
          self.assertEqual(s['plain']['task_new']['jira']['code'], 'no-integrations-space')
          self.assertEqual(s['liga']['task_new']['from']['code'], 'from-needs-plain-space')

      def test_machine_independent(self):
          raw = open(FIX, encoding='utf-8').read()
          for bad in (os.path.expanduser('~'), os.path.realpath(__import__('tempfile').gettempdir())):
              self.assertNotIn(bad, raw)
  ```
  `$PYT tests.test_before_4d4c` → `FileNotFoundError` (файла знімка нема).
- [ ] **Step 2: генератор** `tests/make_before_4d4c.py` (одна функція `collect(tmp)`; працює на 0.21 і 0.22: ключ `integrations` пишеться лише коли код його ще має):
  ```python
  #!/usr/bin/env python3
  """Знімок вихідних рішень 0.21.0 (етап 4d-4c): що прапорець `integrations` вирішував — автопуш, пуш у реєстр, `vcs_target`, канал
  коментарів, маршрут `task-new`. Еталон `tests/fixtures/outbound/before-4d4c.json` знято ДО змін коду (тег `v0.21.0`); `collect(tmp)` —
  та сама функція, яку після 0.22 кличе `tests/test_outbound_parity_4d4c.py`. Запуск ЛИШЕ з замороженої копії:
      D=$(mktemp -d) && git archive v0.21.0 | tar -x -C "$D" && cp tests/make_before_4d4c.py "$D/tests/"
      HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4c.py" --out tests/fixtures/outbound/before-4d4c.json
  На коді без `spaces.integrations_for` у типовий шлях еталона не пише (код виходу 2). Мережі нема (`urlopen` і `git push` підмінено)."""
  import argparse
  import contextlib
  import json
  import os
  import subprocess
  import sys
  import tempfile
  from unittest import mock

  _HERE = os.path.dirname(os.path.abspath(__file__))
  ROOT = os.path.dirname(_HERE)
  for _p in (_HERE, os.path.join(ROOT, 'app'), os.path.join(ROOT, 'bin')):
      sys.path.insert(0, _p)

  from make_before_4d3a import NoNet, Server  # noqa: E402
  from make_before_4d3b import _call  # noqa: E402
  import liga_fixture as lf  # noqa: E402

  OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'outbound', 'before-4d4c.json')
  STANDS = ('liga', 'liga_unmigrated', 'plain', 'plain_git', 'layer_off')
  CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DEAI_HOME', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'DC_TRACKER_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
           'JIRA_EMAIL', 'JIRA_TOKEN', 'DEAI_EXTRA_MODULES')
  GIT_ENV = {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@example.com',
             'GIT_TERMINAL_PROMPT': '0'}
  GITLAB = {'repo': 'g/r', 'path': 'mockup/t1', 'ssh_key': '~/.ssh/k', 'host_ip': '203.0.113.7'}
  BODIES = {'jira': {'id': 'n-jira', 'jira': 'DEMO-2'}, 'plain': {'id': 'n-plain'},
            'gitlab': {'id': 'n-gl', 'gitlab': {'repo': 'g/r', 'path': 'mockup/n-gl'}}, 'from': {'id': 'n-from'}}


  def _write(path, obj):
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(path, 'w', encoding='utf-8') as f:
          json.dump(obj, f)


  def _stand(tmp, name):
      """`{home, deai, space_dir, tdir, sid, tasks, env, legacy_file}`: каталог стенду (див. докстрінг модуля)."""
      import spaces
      old = hasattr(spaces, 'integrations_for')
      root = os.path.join(tmp, name)
      home = os.path.join(root, 'home')
      deai, sp_dir, tdir = os.path.join(home, '.deai'), os.path.join(root, 'space'), os.path.join(root, 'work', 't1')
      os.makedirs(home)
      _write(os.path.join(tdir, 'iterations.json'), {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'n', 'published': False}],
                                                     'publish_url': None})
      os.makedirs(os.path.join(tdir, 'iterations', 'it1'))
      with open(os.path.join(tdir, 'iterations', 'it1', 'index.html'), 'w', encoding='utf-8') as f:
          f.write('<html></html>')
      task = {'dir': tdir, 'title': 'T', 'jira': 'DEMO-1', 'profile': None}
      st = {'home': home, 'deai': deai, 'space_dir': sp_dir, 'tdir': tdir, 'sid': None, 'legacy_file': None}
      work = os.path.join(root, 'work')
      if name == 'layer_off':
          st['tasks'] = os.path.join(root, 'tasks.json')
          _write(st['tasks'], {'current': 't1', 'design_work_root': work, 'tasks': {'t1': task}})
          st['env'] = {'HOME': home, 'DC_TASKS_FILE': st['tasks']}
          return st
      os.makedirs(sp_dir)
      if name.startswith('liga'):
          st['tasks'] = st['legacy_file'] = os.path.join(root, 'legacy-tasks.json')
          _write(st['tasks'], {'registry': {'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'}, 'design_work_root': work, 'current': 't1',
                               'tasks': {'t1': dict(task, gitlab=GITLAB)}})
          entry, st['sid'] = {'id': 'legacy', 'path': sp_dir, 'legacy': True}, 'legacy'
          if old:
              entry['integrations'] = True
          if name == 'liga':
              lf.write_records(sp_dir, deai, 'legacy')
          else:
              _write(os.path.join(sp_dir, 'space.json'), {'name': 'Liga'})
      else:
          st['tasks'] = os.path.join(sp_dir, 'tasks.json')
          _write(st['tasks'], {'design_work_root': work, 'current': 't1', 'tasks': {'t1': task}})
          entry, st['sid'] = {'id': 'plain', 'path': sp_dir, 'legacy': False}, 'plain'
          if old:
              entry['integrations'] = False
          mods = {'git-sync': {'enabled': True, 'settings': {'branch': 'main', 'path': 'mockup/{task}'}}} if name == 'plain_git' else None
          _write(os.path.join(sp_dir, 'space.json'), dict({'name': 'Plain'}, **({'modules': mods} if mods else {})))
      _write(os.path.join(deai, 'spaces.json'), {'version': 1, 'current': st['sid'], 'spaces': [entry]})
      st['env'] = {'HOME': home, 'DEAI_HOME': deai}
      return st


  @contextlib.contextmanager
  def _active(st):
      import deai_modules
      import spaces
      with contextlib.ExitStack() as es:
          es.enter_context(mock.patch.dict(os.environ, dict(GIT_ENV, **st['env'])))
          for k in CLEAN:
              if k not in st['env']:
                  os.environ.pop(k, None)
          if st['legacy_file']:
              es.enter_context(mock.patch.object(spaces, 'legacy_tasks_file', lambda: st['legacy_file']))
          es.enter_context(mock.patch('urllib.request.urlopen', NoNet()))
          deai_modules.reset_caches()
          yield


  def _fixed(st):
      import spaces
      return spaces.request_space(st['sid']) if st['sid'] else contextlib.nullcontext()


  def _autocommit(st, tmp, fixed, n):
      import serve
      import spaces
      bare = os.path.join(tmp, '%s-origin-%d.git' % (os.path.basename(os.path.dirname(st['home'])), n))
      d = os.path.join(st['tdir'], '..', 't-%d' % n)
      os.makedirs(d)
      with open(os.path.join(d, 'f.txt'), 'w') as f:
          f.write('x')
      subprocess.run(['git', 'init', '-q', '--bare', bare], check=True)
      subprocess.run(['git', 'init', '-q'], cwd=d, check=True)
      subprocess.run(['git', 'remote', 'add', 'origin', bare], cwd=d, check=True)
      pushes, real = [], subprocess.run

      def run(cmd, *a, **kw):
          if isinstance(cmd, (list, tuple)) and list(cmd[:2]) == ['git', 'push']:
              pushes.append(1)
              return subprocess.CompletedProcess(cmd, 0, '', '')
          return real(cmd, *a, **kw)
      ctx = spaces.request_space(st['sid']) if fixed and st['sid'] else contextlib.nullcontext()
      with ctx, mock.patch.object(subprocess, 'run', run):
          serve.git_autocommit(d, 'parity')
      return {'pushed': bool(pushes)}


  def _registry(st):
      import registry
      import serve
      calls = []

      class _Res:
          refused = {}
      with _fixed(st), mock.patch.object(registry, 'push_tasks', lambda tids, *a, **k: calls.append(list(tids)) or _Res()):
          res = serve._registry_push('t1')
      return {'called': bool(calls), 'result': res}


  def _targets(st):
      import serve
      with _fixed(st):
          return {'gitlab': serve.vcs_target('t1', {'gitlab': dict(GITLAB)}, {}),
                  'vcs': serve.vcs_target('t1', {'vcs': {'repo': 'g/r', 'ssh_key': '~/.ssh/k'}}, {'path': 'mockup/{task}'})}


  def _channel(st):
      with Server() as srv:
          status, body = _call(srv, 'GET', '/api/task', task='t1')
      return {'status': status, 'comment_channel': (body or {}).get('comment_channel')}


  def _task_new(st, tmp):
      import serve
      src = os.path.join(tmp, 'src-' + os.path.basename(os.path.dirname(st['home'])))
      os.makedirs(src)
      with open(os.path.join(src, 'index.html'), 'w', encoding='utf-8') as f:
          f.write('<html></html>')

      def offline(*a, **k):
          raise serve.VcsError('vcs-offline', 'offline')
      out = {}
      for name, body in BODIES.items():
          body = dict(body, **({'from': src} if name == 'from' else {}))
          with Server() as srv, mock.patch.object(serve, '_registry_push', lambda tid: False), mock.patch.object(serve, '_vcs_call', offline):
              status, resp = _call(srv, 'POST', '/api/task-new', body=body)
          resp = resp or {}
          out[name] = {'status': status, 'code': resp.get('code'), 'space': resp.get('space'), 'created': bool(resp.get('ok'))}
      return out


  def _scrub(obj, tmp):
      txt = json.dumps(obj, ensure_ascii=False, sort_keys=True)
      for p in (os.path.realpath(tmp), tmp):
          txt = txt.replace(p, '<tmp>')
      return json.loads(txt)


  def collect(tmp):
      """`{стенд: {розділ: значення}}` для всіх п'яти стендів у тимчасовій теці `tmp`."""
      out = {}
      for name in STANDS:
          st = _stand(tmp, name)
          with _active(st):
              out[name] = {'autocommit': _autocommit(st, tmp, True, 1), 'autocommit_unfixed': _autocommit(st, tmp, False, 2),
                           'registry': _registry(st), 'targets': _targets(st), 'comment_channel': _channel(st),
                           'task_new': _task_new(st, tmp)}
      return _scrub(out, tmp)


  def main(argv=None):
      ap = argparse.ArgumentParser()
      ap.add_argument('--out', default=OUT_DEFAULT)
      a = ap.parse_args(argv)
      import spaces
      if os.path.abspath(a.out) == OUT_DEFAULT and not hasattr(spaces, 'integrations_for'):
          print('відмова: еталон знімається лише з коду 0.21.0 (тег v0.21.0)', file=sys.stderr)
          return 2
      with tempfile.TemporaryDirectory(prefix='before-4d4c-') as tmp:
          data = collect(tmp)
      data['_meta'] = {'code': '0.21.0', 'what': 'вихідні рішення за прапорцем integrations'}
      os.makedirs(os.path.dirname(a.out), exist_ok=True)
      with open(a.out, 'w', encoding='utf-8') as f:
          json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
          f.write('\n')
      return 0


  if __name__ == '__main__':
      sys.exit(main())
  ```
- [ ] **Step 3: зняти знімок із ЗАМОРОЖЕНОЇ копії** (двічі, `cmp` мовчить — детермінізм):
  ```bash
  D=$(mktemp -d) && git archive v0.21.0 | tar -x -C "$D" && cp tests/make_before_4d4c.py "$D/tests/"
  HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4c.py" --out tests/fixtures/outbound/before-4d4c.json
  HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4c.py" --out "$D/second.json" && cmp tests/fixtures/outbound/before-4d4c.json "$D/second.json"
  ```
  Якщо стенд падає на `/api/task` чи `task-new` — виправляти СТЕНД (генератор), а не очікування.
- [ ] **Step 4:** `$PYT tests.test_before_4d4c` → 4 тести OK (якщо `test_values_that_0_21_decided_by_the_flag` показує інакше — знімок не відповідає 0.21: зупинитись і доповісти). Весь пакет зелений.
- [ ] **Step 5: коміт.**
  ```bash
  git add -- tests/make_before_4d4c.py tests/test_before_4d4c.py tests/fixtures/outbound/before-4d4c.json
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "test(4d-4c): знімок вихідних рішень 0.21.0 (автопуш, реєстр, vcs_target, канал, task-new)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/make_before_4d4c.py tests/test_before_4d4c.py tests/fixtures/outbound/before-4d4c.json
  ```

---

### Task 2: `deai_modules.vcs_outbound(space)`

**Files:** Modify `app/deai_modules.py` (після `COMPAT_ALLOWED`, ~рядок 2162); Create `tests/test_outbound.py` (клас `VcsOutbound`; клас `OutboundGates` додає T3).

- [ ] **Step 1: тест (червоний).** `tests/test_outbound.py`:
  ```python
  """Вихідні дії вирішує запис ролі `vcs`, а не прапорець простору (етап 4d-4c): предикат `vcs_outbound` і його споживачі."""
  import contextlib
  import json
  import os
  import subprocess
  import sys
  import threading
  import unittest
  from unittest import mock

  _HERE = os.path.dirname(os.path.abspath(__file__))
  sys.path.insert(0, _HERE)
  for _p in ('app', 'bin'):
      sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
  import liga_fixture as lf  # noqa: E402
  import spaces_guard  # noqa: E402
  import deai_modules  # noqa: E402
  import spaces  # noqa: E402
  import serve  # noqa: E402

  _REAL = None


  def setUpModule():
      global _REAL
      _REAL = spaces_guard.snapshot()


  def tearDownModule():
      spaces_guard.assert_untouched(_REAL)


  def _liga(fx):
      return {'id': 'legacy', 'path': fx.space_dir, 'legacy': True}


  class VcsOutbound(unittest.TestCase):
      def test_a_migrated_liga_is_outbound(self):
          fx = lf.LigaFixture(self).env().build()
          self.assertIs(deai_modules.vcs_outbound(_liga(fx)), True)

      def test_no_record_is_closed(self):
          fx = lf.LigaFixture(self).env().build(roles=())
          self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

      def test_a_disabled_record_is_closed(self):
          fx = lf.LigaFixture(self).env().build(overrides={'vcs': {'enabled': False}})
          self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

      def test_git_sync_without_the_liga_scheme_is_closed(self):
          fx = lf.LigaFixture(self).env().build(overrides={'vcs': {'settings': {'compat': ''}}})
          self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

      def test_unreadable_space_json_is_closed(self):
          fx = lf.LigaFixture(self).env().build()
          with open(os.path.join(fx.space_dir, 'space.json'), 'w') as f:
              f.write('{not json')
          deai_modules.reset_caches()
          self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

      def test_nobody_layer_off_and_the_implicit_space_are_closed(self):
          fx = lf.LigaFixture(self).env().build()
          for sp in (None, {}, dict(spaces.IMPLICIT)):
              self.assertIs(deai_modules.vcs_outbound(sp), False, sp)
          with mock.patch.object(spaces, 'layer_on', return_value=False):
              self.assertIs(deai_modules.vcs_outbound(_liga(fx)), False)

      def test_it_is_the_same_fact_as_the_client_reads(self):
          """Той самий факт, що `serve.vcs_legacy_texts` (і JS `isLegacyVcs`): рішення не розходяться."""
          for kw in ({}, {'roles': ()}, {'overrides': {'vcs': {'settings': {'compat': ''}}}}):
              fx = lf.LigaFixture(self).env().build(**kw)
              sp = _liga(fx)
              self.assertIs(deai_modules.vcs_outbound(sp),
                            serve.vcs_legacy_texts(deai_modules.provider('vcs', sp), sp), kw)

      def test_the_second_call_does_not_walk_the_catalog_again(self):
          fx = lf.LigaFixture(self).env().build()
          sp = _liga(fx)
          self.assertIs(deai_modules.vcs_outbound(sp), True)
          with mock.patch.object(deai_modules, 'catalog', side_effect=AssertionError('каталог')):
              self.assertIs(deai_modules.vcs_outbound(sp), True)
  ```
  `$PYT tests.test_outbound` → `AttributeError: … vcs_outbound`.
- [ ] **Step 2: реалізація** (`app/deai_modules.py`, одразу після `COMPAT_ALLOWED`):
  ```python
  def vcs_outbound(space):
      """Чи може простір ходити назовні гітом за схемою ЛІГИ (4d-4c): простір має ВВІМКНЕНИЙ вбудований запис `git-sync` із
      `compat == "design-canvas"` — той самий факт, який клієнт читає як `isLegacyVcs`. Замінює прапорець `integrations`: автопуш,
      пуш у реєстр команди, `ssh_key`/`host_ip` цілі й `gitlab`-маппінг нової задачі питають лише це.
      ТОТАЛЬНА: нема простору, неявний простір, шар вимкнено, `ModuleError`, нечитабельний `space.json`, збій відбитків — `False`
      (закрито, не виняток). Кеш — той самий `_capabilities_full` (ключ `_caps_key` містить відбиток `space.json`)."""
      try:
          if not isinstance(space, dict) or not space or spaces._is_implicit(space) or not spaces.layer_on():
              return False
          p = _capabilities_full(space)[1].get('vcs')
          return (isinstance(p, Module) and getattr(p, 'origin', 'builtin') == 'builtin' and p.id == VCS_MODULE
                  and compat_of(space, VCS_MODULE) == COMPAT_DESIGN_CANVAS)
      except Exception:  # noqa: BLE001 — тотальність
          return False
  ```
- [ ] **Step 3:** `$PYT tests.test_outbound -v` → OK; весь пакет зелений. Мутація: у `vcs_outbound` прибрати `compat_of(...) == COMPAT_DESIGN_CANVAS` → `test_git_sync_without_the_liga_scheme_is_closed` червоніє; відновити.
- [ ] **Step 4: коміт** `feat(4d-4c): deai_modules.vcs_outbound — вихідна дія за записом vcs зі схемою ЛІГИ` — шляхи `app/deai_modules.py tests/test_outbound.py` (новий файл спершу `git add --`).

---

### Task 3: вихідні ворота — на `vcs_outbound` (автопуш, реєстр, `_vcs_ssh`, `vcs_target`, канал, `bin/state.py`)

**Files:** Modify `app/serve.py` (196-203, 208-240, 659-700, 2548-2570, 5944), `bin/state.py` (272-280, імпорт), `tests/test_outbound.py` (клас `OutboundGates`), тести, що ламаються (див. Step 5).

- [ ] **Step 1: тести (червоні)** — дописати в `tests/test_outbound.py`:
  ```python
  class OutboundGates(unittest.TestCase):
      """Ворота серверу: автопуш, реєстр команди, ціль `gitlab`/`ssh`, канал коментарів. Реальний `git push` перехоплено — мережі нема."""

      def setUp(self):
          self.fx = lf.LigaFixture(self).env().build(key_file=True)
          p = mock.patch.dict(os.environ, {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@example.com',
                                           'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@example.com'})
          p.start()
          self.addCleanup(p.stop)
          self.n = 0

      def add_plain(self, modules=None):
          """Другий (звичайний) простір у реєстрі: `{'id': 'plain', …}`."""
          p = os.path.join(self.fx.tmp, 'plain')
          os.makedirs(p)
          with open(os.path.join(p, 'space.json'), 'w') as f:
              json.dump(dict({'name': 'Plain'}, **({'modules': modules} if modules else {})), f)
          reg_path = os.path.join(self.fx.deai, 'spaces.json')
          with open(reg_path) as f:
              reg = json.load(f)
          reg['spaces'].append({'id': 'plain', 'path': p, 'legacy': False})
          with open(reg_path, 'w') as f:
              json.dump(reg, f)
          deai_modules.reset_caches()
          return {'id': 'plain', 'path': p, 'legacy': False}

      def autocommit(self, sid):
          """`True`, коли `git_autocommit` спробував `git push`; `sid=None` — простір запиту не зафіксовано."""
          self.n += 1
          d = os.path.join(self.fx.tmp, 'work', 't%d' % self.n)
          os.makedirs(d)
          with open(os.path.join(d, 'f.txt'), 'w') as f:
              f.write('x')
          subprocess.run(['git', 'init', '-q'], cwd=d, check=True)
          subprocess.run(['git', 'remote', 'add', 'origin', os.path.join(self.fx.tmp, 'nowhere.git')], cwd=d, check=True)
          pushes, real = [], subprocess.run

          def run(cmd, *a, **kw):
              if isinstance(cmd, (list, tuple)) and list(cmd[:2]) == ['git', 'push']:
                  pushes.append(1)
                  return subprocess.CompletedProcess(cmd, 0, '', '')
              return real(cmd, *a, **kw)
          ctx = spaces.request_space(sid) if sid is not None else contextlib.nullcontext()
          with ctx, mock.patch.object(subprocess, 'run', run):
              serve.git_autocommit(d, 'x')
          return bool(pushes)

      def test_liga_pushes_a_plain_git_sync_space_does_not(self):
          self.add_plain({'git-sync': {'enabled': True, 'settings': {'branch': 'main', 'path': 'mockup/{task}'}}})
          self.assertTrue(self.autocommit('legacy'))
          self.assertFalse(self.autocommit('plain'))

      def test_an_unfixed_request_space_is_closed(self):
          """Поправка 2: незафіксований простір = неявний, `False` (раніше «інтеграції ввімкнено» й пуш)."""
          self.assertFalse(self.autocommit(None))

      def test_a_worker_thread_carries_its_space(self):
          out = []
          with spaces.request_space('legacy'):
              fn = serve._in_space(lambda: out.append(self.autocommit(None)))
          t = threading.Thread(target=fn)
          t.start()
          t.join()
          bare = threading.Thread(target=lambda: out.append(self.autocommit(None)))
          bare.start()
          bare.join()
          self.assertEqual(out, [True, False])

      def test_the_registry_is_for_a_liga_with_its_scheme_only(self):
          self.add_plain()
          with spaces.request_space('legacy'):
              self.assertTrue(serve.registry_allowed())
          with spaces.request_space('plain'):
              self.assertFalse(serve.registry_allowed())
          self.assertFalse(serve.registry_allowed())                      # не зафіксовано
          fx2 = lf.LigaFixture(self).env().build(roles=())               # немігрована ЛІГА
          with spaces.request_space('legacy'):
              self.assertFalse(serve.registry_allowed())

      def test_the_gitlab_target_and_ssh_follow_the_scheme(self):
          self.add_plain()
          task = {'gitlab': {'repo': 'g/r', 'path': 'mockup/t1', 'ssh_key': '~/.ssh/k', 'host_ip': '203.0.113.7'}}
          with spaces.request_space('legacy'):
              got = serve.vcs_target('t1', task, {})
              self.assertEqual(got['repo'], 'g/r')
              self.assertEqual(got['host_ip'], '203.0.113.7')
              self.assertEqual(serve._vcs_ssh(task['gitlab'])['host_ip'], '203.0.113.7')
          with spaces.request_space('plain'):
              self.assertIsNone(serve.vcs_target('t1', task, {}))
              self.assertEqual(serve._vcs_ssh(task['gitlab']), {})

      def test_the_task_comment_channel_follows_the_comments_provider(self):
          self.add_plain()
          with spaces.request_space('legacy'):
              self.assertEqual(serve._task_comment_channel(_liga(self.fx), {}, 't1'), 'dc/t1')
          with spaces.request_space('plain'):
              self.assertIsNone(serve._task_comment_channel({'id': 'plain', 'path': os.path.join(self.fx.tmp, 'plain'), 'legacy': False}, {}, 't1'))

      def test_state_registry_line(self):
          import state
          import registry
          self.add_plain()
          fresh = {'age_h': 1, 'state': 'fresh', 'hint': ''}
          with mock.patch.object(registry, 'staleness', return_value=fresh) as st:
              with spaces.request_space('plain'):
                  self.assertEqual(state._registry_line({}), '')
                  st.assert_not_called()
              with spaces.request_space('legacy'):
                  self.assertIn('Реєстр', state._registry_line({}))
  ```
  `$PYT tests.test_outbound` → червоні (нема `registry_allowed`, `_task_comment_channel`; автопуш ще за прапорцем).
- [ ] **Step 2: код `serve.py`.** Замінити `_outbound_ok` (196-203):
  ```python
  def _vcs_outbound_here():
      """Чи може простір запиту ходити назовні гітом за схемою ЛІГИ (`deai_modules.vcs_outbound`). Простір запиту не зафіксовано — неявний
      простір, записів нема → `False` (закрито; Поправка 2 плану 4d-4c). Реєстр, що зіпсувався посеред запиту (`SpacesError`), — теж
      `False`: те, що ВЖЕ зроблено (коміт, нова задача), через це не стає 503."""
      try:
          return deai_modules.vcs_outbound(spaces.effective_space())
      except spaces.SpacesError:
          return False


  def registry_allowed():
      """Спільний реєстр задач команди — лише для простору ЛІГА (`legacy: true`) із його схемою git (`vcs_outbound`). Звичайні простори,
      немігрована ЛІГА, шар вимкнено й незафіксований простір у спільний реєстр не пишуть НІКОЛИ."""
      try:
          sp = spaces.effective_space()
      except spaces.SpacesError:
          return False
      return bool(sp) and sp.get('legacy') is True and deai_modules.vcs_outbound(sp)
  ```
  У `git_autocommit`: `push = _outbound_ok()` → `push = _vcs_outbound_here()`; у докстрінгу «Простір без інтеграцій (`spaces.integrations_on()`)» → «Простір без схеми ЛІГИ (`vcs_outbound`)». `_vcs_ssh`: `if not spaces.integrations_on():` → `if not _vcs_outbound_here():`. `vcs_target`: `task.get('gitlab') and spaces.integrations_on()` → `task.get('gitlab') and _vcs_outbound_here()`. `_registry_push`: `if not _outbound_ok(): return False` → `if not registry_allowed(): return False` (докстрінг: «Простір без схеми ЛІГИ…»). Додати поруч із `_comment_channel_in`:
  ```python
  def _task_comment_channel(sp, task, tid):
      """`comment_channel` для `/api/task` (Д5): канал є, коли простір має постачальника ролі `comments` (модуль) — не за прапорцем."""
      if isinstance(deai_modules.comments_prov_cached(sp), deai_modules.Module):
          return _comment_channel_in(sp, task, tid)
      return None
  ```
  та в `/api/task` (5942-5944): `'comment_channel': (_comment_channel_in(sp, task, tid) if spaces.integrations_on() else None)` → `'comment_channel': _task_comment_channel(sp, task, tid),`. Рядки 2456-2460 (`spaces.require_integrations()` у `_task_new_write`) НЕ чіпати до T4.
- [ ] **Step 3: `bin/state.py`.** Імпорт `from serve import (…, registry_allowed, …)`; `_registry_line`: `if not spaces.integrations_on(): return ''` → `if not registry_allowed(): return ''`; докстрінг «Простір без схеми ЛІГИ: реєстру команди для нього нема».
- [ ] **Step 4:** `$PYT tests.test_outbound -v` → OK.
- [ ] **Step 5: тести, які ламає T3, — правимо тут.** Прогнати повний пакет; очікувані групи:
  - підміни `serve._outbound_ok` (`tests/test_legacy_comments.py:526`) → `mock.patch.object(serve, '_vcs_outbound_here', return_value=True)`;
  - тести, що чекали `pushed: True` / пуш у шарі «вимкнено» чи в просторі з прапорцем `integrations: True` без запису `git-sync`: будують явний простір із записом `git-sync` + `compat: design-canvas` (`lf.write_records(..., roles=('vcs',))`) і фіксують його `spaces.request_space('legacy')`; шар вимкнено → очікують `pushed: False` (Свідома відмінність 5 спеки);
  - тести `vcs_target` з `gitlab` у шарі «вимкнено» (`tests/test_vcs_core.py`, `tests/test_gitlab_sync.py`): те саме — явна ЛІГА;
  - `tests/test_spaces_serve.py:1213` (`seen.append((…, spaces.integrations_on()))`) — лишається до T6.
  Кожна правка — у звіті одним рядком із причиною.
- [ ] **Step 6: паритет-мутації.** `_vcs_outbound_here` → `return True` — `test_an_unfixed_request_space_is_closed` і `test_liga_pushes_a_plain_git_sync_space_does_not` червоніють; `registry_allowed` без `legacy`-умови — `test_the_registry_…` червоніє. Відновити.
- [ ] **Step 7: коміт** `feat(4d-4c): вихідні ворота (автопуш, реєстр, ssh, gitlab-ціль, канал) — за vcs_outbound` — шляхи `app/serve.py bin/state.py tests/test_outbound.py` + змінені тести.

---

### Task 4: `task-new` без `_liga_flow` і без 409; гейти `from`/`gitlab`; `profile` за `vcs_outbound`

**Files:** Modify `app/spaces.py` (`default_new_task_space`, ~859), `app/serve.py` (`_liga_flow`/`_liga_track_repos`/`NO_INTEGRATIONS_SPACE_MSG` 1541-1570; `_liga_like` 1675-1678; `_adopt_source` 7729; `_task_new` 7843-7934; `_task_new_write` 2456-2460), `app/spaces-model.js` + `app/i18n.js` (мапа `from-needs-plain-space`), тести.

- [ ] **Step 1: тести (червоні).** У `tests/test_spaces_serve.py`, клас `TaskNew` (допоміжні `self.post`, `self.made`, `_read`, `self.p_id`, `self.p_file`, `self.legacy_id`, `self.reg_path`, `_write` уже є):
  - **`no_liga()`** (рядок 2152) переписати: «Реєстр БЕЗ простору ЛІГА»: `reg['spaces'] = [s for s in reg['spaces'] if not s.get('legacy')]; reg['current'] = self.p_id` (ключа `integrations` більше нема). Тести, що після `no_liga()` читають `liga_tracks`/`legacy_file`, беруть дані ДО виклику.
  - `test_liga_signs_without_space_and_without_a_liga_space_are_409_and_create_nothing` → `test_liga_signs_without_a_liga_space_go_to_the_current_space`: для кожного знака з циклу (крім тіла з `gitlab`) `st == 200`, `body['space'] == self.p_id`, запис у `self.p_file`; для `{'gitlab': {...}}` — `(400, 'gitlab-needs-vcs-scheme')` і нічого не створено (`md5` файлів і тек, як у старому тесті). Напрямок `profile` поза переліком просторуp — ігнорується; `track` суворий (`unknown-track` 400).
  - `test_liga_signs_with_a_liga_space_or_an_explicit_space_are_not_refused`: останнє твердження `gitlab-needs-integrations` → `gitlab-needs-vcs-scheme`.
  - інші місця з `no-integrations-space` (рядки ~2229, 2396, 2424, 2563) — той самий перехід (200 у поточному просторі або `gitlab-needs-vcs-scheme`); `test_task_from.py:135,138` (`from-needs-plain-space`): `from` у просторі ЛІГА тепер дозволено → очікують 200 (`copied` у відповіді); `from` разом з `gitlab` → `(400, 'bad-request')`.
  - новий тест у тому ж класі:
    ```python
    def test_default_space_is_the_legacy_entry_and_profile_follows_the_scheme(self):
        self.made(self.old_dir('n30'), os.path.join(self.p_path, 'n31'))
        spaces.switch_space(self.p_id)
        st, body = self.post('/api/task-new', {'id': 'n30'})
        self.assertEqual((st, body['space']), (200, self.legacy_id), body)          # `legacy: true`, не прапорець
        st, body = self.post('/api/task-new', {'id': 'n31', 'space': self.p_id})
        self.assertEqual((st, body['space']), (200, self.p_id), body)
        self.assertIsNone(_read(self.p_file)['tasks']['n31']['profile'])
    ```
  `$PYT tests.test_spaces_serve tests.test_task_from tests.test_task_tags` → червоні.
- [ ] **Step 2: код.**
  - `spaces.default_new_task_space`: `if sp.get('integrations'):` → `if sp.get('legacy') is True:`; докстрінг «перший запис із `legacy: true`, інакше поточний».
  - `serve.py`: видалити `NO_INTEGRATIONS_SPACE_MSG`, `_liga_flow`, `_liga_track_repos`, `_liga_like`; у `_task_new` блок `want is None` лишає лише `sp = spaces.default_new_task_space()` і перевірку `sp is None` → 409 `no-space`; докстрінг оновити (прибрати «ознаки потоку ЛІГА», «без інтеграцій»).
  - `liga = spaces.integrations_for(sp)` (рядок ~7865) видалити; ПІСЛЯ `spaces.set_request_space(sp['id'])` додати `liga = deai_modules.vcs_outbound(sp)` (Поправка 9). Гейт `if not liga and payload.get('gitlab'):` → код `gitlab-needs-vcs-scheme`, текст `'gitlab mapping needs a space whose git sync uses the design-canvas scheme'`.
  - `_adopt_source`: `if spaces.integrations_for(sp) or payload.get('gitlab'): … 'from-needs-plain-space'` → `if payload.get('gitlab'): self._space_error(400, 'bad-request', 'from cannot be combined with gitlab'); return None`.
  - `_task_new_write`: видалити блок `if gitlab: spaces.require_integrations()` (гейт `task-new` уже відхилив такий `gitlab`); коментар «`IntegrationsOff` — підклас `OSError`…» стерти. Параметр `liga` (`legacy=liga`) лишається — тепер це «схема ЛІГИ» (`profile: track if liga else None`, Д5 спеки: `profile` пишемо до 1.0).
  - `app/spaces-model.js`: видалити рядок `["from-needs-plain-space", "wzErrFromPlain"]` і перше речення коментаря над `FROM_KEYS` про `wzErrFromPlain`; `app/i18n.js`: видалити `wzErrFromPlain` в обох мовах (1155, 2117); `tests/spaces-state.test.mjs:195` і `tests/spaces-model.test.mjs:193,203` — прибрати рядки про `from-needs-plain-space`/`wzErrFromPlain`; у `spaces-state` цикл «інших кодів» лишає `gitlab-needs-integrations` як приклад «невідомий код → загальний» (це й так так).
- [ ] **Step 3:** `$PYT tests.test_spaces_serve tests.test_task_from tests.test_task_tags tests.test_liga_migrate_d tests.test_no_adapter`: `test_task_tags.py:440-479` і `test_liga_migrate_d.py:1350-1370` (`_liga_flow`) — тести видаляються з таблицею відповідності в звіті (їхній зміст — «простір `track` з репо» — тепер охоплює `TaskNew` вище); `tests/test_no_adapter.py:20` `PROFILE_OK` без `_liga_flow`; `tests/test_implicit.py` клас `LigaLikePin` видалити. Весь пакет + JS зелені.
- [ ] **Step 4: мутація.** Повернути `if sp.get('legacy') is True` → `if False` у `default_new_task_space`: `test_default_space_is_the_legacy_entry…` червоніє. Відновити.
- [ ] **Step 5: коміт** `feat(4d-4c): task-new без _liga_flow і 409; from/gitlab-ворота; профіль за схемою ЛІГИ` (усі змінені файли переліком).

---

### Task 5: `static-publish` — явний запис

**Files:** Modify `app/spaces.py` (`create_space`, нові функції), `app/deai_modules.py` (`IMPLICIT_MODULE`, `_implicit_on`, `_enabled_in`, `_entry_state`, `_caps_key`), `app/serve.py` (`serve_main`), `app/modules/static-publish/server.py` (коментар); Create `tests/test_static_publish_explicit.py`; тести.

- [ ] **Step 1: тести (червоні)** `tests/test_static_publish_explicit.py`:
  ```python
  """`static-publish` — явний запис (4d-4c, Р3): `create_space` пише його, наявні простори добирає ідемпотентний стартовий крок."""
  import json
  import os
  import sys
  import tempfile
  import unittest
  from unittest import mock

  _HERE = os.path.dirname(os.path.abspath(__file__))
  sys.path.insert(0, _HERE)
  for _p in ('app',):
      sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
  import spaces_guard  # noqa: E402
  import deai_modules  # noqa: E402
  import spaces  # noqa: E402

  _REAL = None


  def setUpModule():
      global _REAL
      _REAL = spaces_guard.snapshot()


  def tearDownModule():
      spaces_guard.assert_untouched(_REAL)


  class Base(unittest.TestCase):
      def setUp(self):
          d = tempfile.TemporaryDirectory(prefix='sp-pub-')
          self.addCleanup(d.cleanup)
          self.tmp = os.path.realpath(d.name)
          self.deai = os.path.join(self.tmp, 'home', '.deai')
          p = mock.patch.dict(os.environ, {'HOME': os.path.join(self.tmp, 'home'), 'DEAI_HOME': self.deai})
          p.start()
          self.addCleanup(p.stop)
          os.environ.pop('DC_TASKS_FILE', None)
          deai_modules.reset_caches()

      def space(self, name, data, legacy=False):
          path = os.path.join(self.tmp, name)
          os.makedirs(path)
          if data is not None:
              with open(os.path.join(path, 'space.json'), 'w') as f:
                  f.write(data if isinstance(data, str) else json.dumps(data))
          reg_path = os.path.join(self.deai, 'spaces.json')
          os.makedirs(self.deai, exist_ok=True)
          reg = json.load(open(reg_path)) if os.path.exists(reg_path) else {'version': 1, 'current': name, 'spaces': []}
          reg['spaces'].append({'id': name, 'path': path, 'legacy': legacy})
          json.dump(reg, open(reg_path, 'w'))
          return path

      def read(self, path):
          with open(os.path.join(path, 'space.json'), 'rb') as f:
              return f.read()


  class Materialise(Base):
      REC = {'static-publish': {'enabled': True}}

      def test_a_new_space_has_the_record(self):
          sid = spaces.create_space('Alpha', 'space-1', os.path.join(self.tmp, 'alpha'))
          sp = next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)
          self.assertEqual(json.loads(self.read(sp['path']))['modules'], self.REC)
          self.assertEqual(deai_modules.provider('publish', sp).id, 'static-publish')
          self.assertNotIn('integrations', sp)

      def test_a_space_without_a_record_gets_one_and_publishes(self):
          p = self.space('a', {'name': 'A', 'color': 'space-2'})
          self.assertEqual(spaces.materialize_static_publish(), ['a'])
          data = json.loads(self.read(p))
          self.assertEqual((data['name'], data['color'], data['modules']), ('A', 'space-2', self.REC))

      def test_idempotent_to_the_byte(self):
          p = self.space('a', {'name': 'A'})
          spaces.materialize_static_publish()
          first = self.read(p)
          self.assertEqual(spaces.materialize_static_publish(), [])
          self.assertEqual(self.read(p), first)

      def test_a_disabled_record_is_a_human_decision(self):
          p = self.space('a', {'modules': {'static-publish': {'enabled': False}}})
          before = self.read(p)
          self.assertEqual(spaces.materialize_static_publish(), [])
          self.assertEqual(self.read(p), before)

      def test_liga_and_unreadable_and_foreign_shapes_are_untouched(self):
          cases = {'liga': ({'name': 'L'}, True), 'bad': ('{not json', False), 'arr': ('[]', False),
                   'modsarr': ({'modules': []}, False)}
          paths = {n: self.space(n, d, legacy=lg) for n, (d, lg) in cases.items()}
          before = {n: self.read(p) for n, p in paths.items()}
          self.assertEqual(spaces.materialize_static_publish(), [])
          self.assertEqual({n: self.read(p) for n, p in paths.items()}, before)

      def test_an_enabled_other_publisher_keeps_the_role(self):
          p = self.space('a', {'modules': {'vercel-publish': {'enabled': True}}})
          before = self.read(p)
          self.assertEqual(spaces.materialize_static_publish(), [])
          self.assertEqual(self.read(p), before)

      def test_a_disabled_other_publisher_does_not_cancel_the_default(self):
          """Паритет 0.21: неявний `static-publish` програвав лише ВВІМКНЕНОМУ явному публікатору."""
          p = self.space('a', {'modules': {'vercel-publish': {'enabled': False}}})
          self.assertEqual(spaces.materialize_static_publish(), ['a'])
          mods = json.loads(self.read(p))['modules']
          self.assertEqual(mods['vercel-publish'], {'enabled': False})
          self.assertEqual(mods['static-publish'], {'enabled': True})

      def test_an_own_publisher_by_roles_keeps_the_role(self):
          p = self.space('a', {'modules': {'acme-pub': {'enabled': True, 'roles': ['publish']}}})
          before = self.read(p)
          self.assertEqual(spaces.materialize_static_publish(), [])
          self.assertEqual(self.read(p), before)

      def test_layer_off_and_missing_folder_do_nothing(self):
          with mock.patch.object(spaces, 'layer_on', return_value=False):
              self.assertEqual(spaces.materialize_static_publish(), [])
          self.assertFalse(spaces.ensure_static_publish(os.path.join(self.tmp, 'nope')))


  class NoImplicitDefault(Base):
      def test_the_implicit_default_is_gone(self):
          for name in ('IMPLICIT_MODULE', '_implicit_on'):
              self.assertFalse(hasattr(deai_modules, name), name)
          p = self.space('a', {'name': 'A'})
          sp = {'id': 'a', 'path': p, 'legacy': False}
          self.assertIsNone(deai_modules.provider('publish', sp))                 # без запису публікатора нема
          st = deai_modules.effective_state(sp)['static-publish']
          self.assertEqual((st['enabled'], st['implicit']), (False, False))
  ```
  `$PYT tests.test_static_publish_explicit` → червоні.
- [ ] **Step 2: `app/spaces.py`.**
  ```python
  #: Вбудований модуль публікації «у теку»: типовий запис нового простору (до 4d-4c був неявним типовим).
  STATIC_PUBLISH_ID = 'static-publish'


  def _ensure_static_publish_locked(space_path):
      """`True`, коли `space.json` змінено. Додає `modules.static-publish = {enabled: true}`, якщо ключа нема (будь-який стан запису —
      рішення людини) і нема ВВІМКНЕНОГО запису, що веде `publish` (`vercel-publish` чи `roles` зі `publish`). Нечитаний/не-обʼєкт файл і
      `modules` не-обʼєкт — не чіпаємо; тека, якої нема, — теж. Лише додає ключ: решта файла збережена. Кличе той, хто ТРИМАЄ `WRITE_LOCK`."""
      if not os.path.isdir(space_path):
          return False
      p = os.path.join(space_path, 'space.json')
      try:
          data = _read_json(p)
      except FileNotFoundError:
          data = {}
      except (OSError, ValueError):
          return False
      if not isinstance(data, dict):
          return False
      mods = data.get('modules')
      if mods is None:
          mods = {}
      elif not isinstance(mods, dict):
          return False
      if STATIC_PUBLISH_ID in mods:
          return False
      for mid, e in mods.items():
          if isinstance(e, dict) and e.get('enabled') is True and (
                  mid == 'vercel-publish' or (isinstance(e.get('roles'), list) and 'publish' in e['roles'])):
              return False
      out = dict(data)
      out['modules'] = dict(mods, **{STATIC_PUBLISH_ID: {'enabled': True}})
      try:
          _write_public(p, out)
      except OSError:
          return False
      return True


  def ensure_static_publish(space_path):
      with WRITE_LOCK:
          return _ensure_static_publish_locked(space_path)


  def materialize_static_publish():
      """Стартовий крок 0.22 (не крок ЛІГИ): кожному простору без `legacy: true` добирає запис `static-publish` (див.
      `_ensure_static_publish_locked`). Ідемпотентний; шар вимкнено — нічого. Повертає id просторів, чий файл змінено."""
      if not layer_on():
          return []
      try:
          reg = read_registry()
      except SpacesError:
          return []
      return [sp['id'] for sp in reg['spaces'] if sp.get('legacy') is not True and ensure_static_publish(sp['path'])]
  ```
  `create_space`: новий `space.json` — `{'name': name, 'color': color, 'modules': {STATIC_PUBLISH_ID: {'enabled': True}}}`; після блоку створення файлів (усередині `with WRITE_LOCK`, до `sid = …`) — `_ensure_static_publish_locked(p)` (усиновлена тека з готовим `space.json`); у реєстр пишемо `{'id': sid, 'path': p, 'legacy': False}` (прапорець `integrations` прибирає T6 — тут лишити, щоб комміт T5 був малим).
- [ ] **Step 3: `deai_modules.py`.** Видалити `IMPLICIT_MODULE` (+ коментар 118-120) і `_implicit_on`; `_enabled_in`:
  ```python
  def _enabled_in(m, space, explicit):
      """(увімкнено, неявно) за явними рішеннями `explicit`. Неявного типового нема (4d-4c): `implicit` — завжди `False` (ключ API до 1.0)."""
      e = explicit.get(m.id)
      return (e['enabled'], False) if e is not None else (False, False)
  ```
  `_caps_key`: прибрати `spaces.integrations_for(space)` (залишити `(_space_id(space), _space_path(space), …)`); докстрінги `effective_state`/`capabilities` («без інтеграцій», «прапорець `integrations`») — переписати; коментар `app/modules/static-publish/server.py:4` без `IMPLICIT_MODULE`.
- [ ] **Step 4: старт.** `serve.serve_main` після `liga_migrate.startup()`:
  ```python
      try:
          if not (isolation.isolated() and isolation.real_home(spaces.home())):
              for sid in spaces.materialize_static_publish():
                  print('простір %s: публікація в теку тепер явний запис static-publish (екран «Підключення»)' % sid, file=sys.stderr)
      except Exception as e:  # noqa: BLE001 — крок не валить старт
          print('static-publish: крок пропущено (%s)' % type(e).__name__, file=sys.stderr)
  ```
  (перед `srv.serve_forever()`; докстрінг `serve_main` доповнити).
- [ ] **Step 5: тести, що ламає T5.** Повний прогін; групи: `tests/test_modules_api.py:324,367-374,452-454,746` (`implicit` тепер `False`; простори, створені `create_space`, мають явний запис `enabled: True`; руками складені реєстри — дописують `{'modules': {'static-publish': {'enabled': True}}}` у `space.json`, для цього `tests/liga_fixture.py` отримує константу `PLAIN_PUBLISH = {'static-publish': {'enabled': True}}`); `tests/test_static_publish.py`, `tests/test_publish_module.py`, `tests/test_modules.py` (поведінка «неявний» → явний), `tests/test_css_tokens.py:1157`. Нічого не видаляється без таблиці відповідності.
- [ ] **Step 6: мутації.** Прибрати `_ensure_static_publish_locked(p)` з `create_space` — `test_a_new_space_has_the_record` (усиновлена гілка — додати рядок у тест на теці з готовим `space.json`) червоніє; прибрати умову «`STATIC_PUBLISH_ID in mods`» — `test_a_disabled_record_is_a_human_decision` червоніє. Відновити.
- [ ] **Step 7: коміт** `feat(4d-4c): static-publish — явний запис (create_space + стартовий крок), неявного типового нема`.

---

### Task 6: прапорець геть з `spaces.py`; `RoleOff`; маркери — у `liga_migrate`

> Примітка (Поправка 20): збій читання кореня в `_liga_integrations` — це ЛІГА (`True`, безпечний бік: не чіпаємо), читання — `spaces._read_json(spaces.legacy_tasks_file())`; сніпет Кроку 3 нижче приведено до коду, а тести `test_a_broken_legacy_root_counts_as_liga` / `test_a_missing_legacy_root_counts_as_liga` пінять це (план тоді дає `skip-tasks-unreadable`). `liga_migrate._liga_integrations` і `liga_space` уже існують з T5. Task 6 лише переспрямовує на неї шість читань ключа й переносить маркери (`has_markers`).

**Files:** Modify `app/spaces.py` (20, 44, 51, 82-85, 160, 281-285, 317, 365, 427-458, 808, 861-870), `app/liga_migrate.py` (470-481, 577-580, 610, 651, 686, 730, 1778-1780), `app/serve.py` (3110, 3396, 5198, 5791-5792 коментарі), `bin/inbox.py`, `bin/state.py`, `tests/liga_fixture.py`; Create `tests/test_no_integrations_flag.py` (Python-частина охоронця); тести.

- [ ] **Step 1: тести (червоні).** `tests/test_liga_migrate_e.py` (або новий клас у `test_liga_migrate.py`):
  ```python
  class LigaIntegrationsWithoutTheKey(unittest.TestCase):
      """Поправка 1: запис ЛІГИ без ключа `integrations` (створено 0.22) мігрує за маркерами кореня; явний `false` 0.21 — поважаємо."""
      def test_has_markers(self):
          import liga_migrate as lm
          self.assertTrue(lm._has_markers({'registry': {}}))
          self.assertTrue(lm._has_markers({'gitlab_host_ip': '203.0.113.7'}))
          self.assertTrue(lm._has_markers({'tasks': {'a': {'gitlab': {'repo': 'g/r'}}}}))
          self.assertFalse(lm._has_markers({'tasks': {'a': {}}}))

      def test_the_key_wins_when_present_else_the_markers(self):
          import liga_migrate as lm
          fx = lf.LigaFixture(self).env()
          fx.legacy_root()                                   # є маркер `registry`
          self.assertTrue(lm._liga_integrations({'id': 'legacy'}))
          self.assertFalse(lm._liga_integrations({'id': 'legacy', 'integrations': False}))
          fx.legacy_root(registry=None, gitlab_ssh_key=None, gitlab_host_ip=None)
          self.assertFalse(lm._liga_integrations({'id': 'legacy'}))

      def test_a_fresh_liga_without_the_key_migrates(self):
          fx = lf.LigaFixture(self).env()
          fx.registry()
          reg_path = os.path.join(fx.deai, 'spaces.json')
          reg = json.load(open(reg_path))
          reg['spaces'][0].pop('integrations')
          json.dump(reg, open(reg_path, 'w'))
          fx._write(os.path.join(fx.space_dir, 'space.json'), {'name': 'Liga'})
          fx.legacy_root()
          import liga_migrate
          self.assertNotEqual(liga_migrate.plan()['status'], 'skip-integrations-off')
  ```
  Та тести `spaces`: у `tests/test_spaces.py` замінити (а) `test_marker_only_in_a_task_means_integrations_on`/`test_top_level_markers_each_switch_integrations_on` (235/240) → той самий зміст на `liga_migrate._has_markers`; (б) `integrations_for/_on/require_integrations` (451, 593-632, 714, 736) → один тест `test_the_flag_api_is_gone` (`for n in ('integrations_for','integrations_on','require_integrations','IntegrationsOff','has_markers','LEGACY_MARKERS'): assertFalse(hasattr(spaces, n))`, `assertTrue(hasattr(spaces, 'RoleOff'))`, `assertTrue(issubclass(spaces.RoleOff, OSError))`); (в) `create_space`/`describe`/`listing` без ключа: `assertNotIn('integrations', sp)` для запису реєстру й `describe(sp)`; (г) перша міграція реєстру: запис без `integrations`; (д) `_validate` приймає запис без ключа й з `bool`-ключем, відхиляє `'integrations': 'yes'` (відкат на 0.21 безпечний).
  Охоронець `tests/test_no_integrations_flag.py` — див. T10; тут лише перевірка в `test_spaces.py`: `IMPLICIT` без `integrations` (`assertEqual(spaces.IMPLICIT, {'id': 'legacy', 'path': '', 'legacy': True})`).
- [ ] **Step 2: `spaces.py`.** `IMPLICIT = {'id': 'legacy', 'path': '', 'legacy': True}`; `class RoleOff(OSError)` замість `IntegrationsOff` (докстрінг: «зовнішній виклик у ролі, яку ніхто не веде; підклас `OSError`: наявні `except OSError` деградують чесно»; шапка модуля 20 і 6-7); видалити `LEGACY_MARKERS`, `has_markers`, `integrations_for`, `integrations_on`, `require_integrations`; `load_registry`: `entry = {'id': …, 'path': path, 'legacy': True}`; `describe`: без `'integrations'`; `create_space`: `{'id': sid, 'path': p, 'legacy': False}`; `_validate` лишається (терпимий ключ; коментар: «відкат на 0.21»).
- [ ] **Step 3: `liga_migrate.py`.** Замінити `spaces.has_markers`/`spaces.LEGACY_MARKERS`:
  ```python
  #: Ключі кореня, що роблять файл «файлом ЛІГИ» (охоронець маркера кроку `liga-4d4b` і вивід інтеграцій запису без ключа).
  _LEGACY_MARKERS = ('registry',) + _MARKER_KEYS


  def _has_markers(cfg):
      if any(k in cfg for k in _LEGACY_MARKERS):
          return True
      tasks = cfg.get('tasks') if isinstance(cfg.get('tasks'), dict) else {}
      return any(isinstance(t, dict) and t.get('gitlab') for t in tasks.values())


  def _liga_integrations(liga):
      """Чи мала ЛІГА «інтеграції» (рішення міграції): явний `bool` ключа запису реєстру (історія 0.21) виграє; запис без ключа (створено 0.22+,
      прапорець більше не пишеться) — за маркерами кореня `tasks.json` (як рахувала перша міграція реєстру)."""
      v = liga.get('integrations')
      if isinstance(v, bool):
          return v
      try:
          cfg = spaces._read_json(spaces.legacy_tasks_file())
          return bool(isinstance(cfg, dict) and _has_markers(cfg))
      except Exception:  # noqa: BLE001 — будь-який збій = «ЛІГА» (Поправка 20)
          return True
  ```
  `spaces.has_markers(cfg)` (577, 580) → `_has_markers`; `liga.get('integrations') is not True` (651, 1778) → `not _liga_integrations(liga)`; словники `space = {…, 'integrations': liga.get('integrations') is True}` (610, 686, 730) і `{…, 'integrations': True}` (1780) → без ключа.
- [ ] **Step 4: `serve.py`/`bin`.** `IntegrationsOff` → `spaces.RoleOff` (`serve.py:3396`; `bin/inbox.py:377,482`; `bin/state.py:305`; коментарі 3110, 2624); `spaces_listing`: `sp = {'id': e['id'], 'path': e['path']}`; коментарі «`integrations_on()` без простору» (5098, 5791) — стерти. `tests/liga_fixture.py::registry` → без ключа (параметр `integrations` видалити), `tests/test_liga_fixture.py:20` — без ключа.
- [ ] **Step 5: тести, що ламає T6** (повний прогін): `integrations`-ключі у фікстурах реєстрів (`test_spaces`, `test_modules`, `test_dashboard`, `test_tasks_overview`, `test_publish_module`, `test_liga_migrate*`, `test_serve`, `test_integrations_off`, `test_comments_role`, `bin/test_overview_push.py`, `test_vcs_core`) прибираються; де фікстура задавала `integrations: False` для звичайного простору — нічого, для ЛІГИ — `legacy: True` + явні записи (`LigaFixture`); `spaces.IntegrationsOff` → `spaces.RoleOff` у тестах (`test_comments_agent`, `test_integrations_off`, `test_legacy_comments`, `test_vcs_core`, `test_notify`); `mock.patch.object(spaces, 'integrations_on', …)` — гасильники прибираються (`test_comments_agent.py:709-774`, `test_publish_module.py:5004`, `test_integrations_off.py:667,676`); `tests/test_spaces_serve.py:742,1213` — без третього елемента; `tests/test_no_originals.py::ALLOWED` — прибрати `('app/spaces.py', …)` (залишається лише `('app/serve.py', 'str:pipeline-feedback')` до T7). Заморожені знімки (`before-*.json`, `make_before_*`) не чіпаємо; `tests/test_notify.py:82` порівнює рядок ЗІ ЗНІМКА — перевірити, що він не читає живий клас.
- [ ] **Step 6: мутація.** У `_liga_integrations` повернути `liga.get('integrations') is True` — `test_a_fresh_liga_without_the_key_migrates` червоніє. Відновити.
- [ ] **Step 7: коміт** `refactor(4d-4c): прапорець integrations геть зі spaces.py (RoleOff, маркери — у liga_migrate)`.

---

### Task 7: журнал синку дашборда — один для всіх; `OVERVIEW_LOG` і параметр `legacy` геть

**Files:** Modify `app/serve.py` (5426-5554, 7618-7652), `tests/test_dashboard.py`, `tests/test_serve.py`, `tests/test_liga_migrate.py`, `tests/test_legacy_comments.py`, `tests/test_integrations_off.py`, `tests/test_no_originals.py`; Create `tests/test_overview_log.py`.

- [ ] **Step 1: тест (червоний)** `tests/test_overview_log.py`:
  ```python
  """Журнал синку дашборда (4d-4c, Д8): один для всіх просторів — `<DEAI_HOME>/logs/dashboard-sync.log`."""
  import inspect
  import os
  import stat
  import sys
  import tempfile
  import unittest
  from unittest import mock

  _HERE = os.path.dirname(os.path.abspath(__file__))
  sys.path.insert(0, _HERE)
  for _p in ('app', 'bin'):
      sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
  import serve  # noqa: E402


  class OverviewLog(unittest.TestCase):
      def setUp(self):
          d = tempfile.TemporaryDirectory(prefix='ovlog-')
          self.addCleanup(d.cleanup)
          self.tmp = os.path.realpath(d.name)
          p = mock.patch.dict(os.environ, {'HOME': self.tmp, 'DEAI_HOME': os.path.join(self.tmp, '.deai')})
          p.start()
          self.addCleanup(p.stop)

      def test_the_log_is_under_the_deai_home_with_private_modes(self):
          path = serve._overview_log_path()
          self.assertEqual(path, os.path.join(self.tmp, '.deai', 'logs', 'dashboard-sync.log'))
          self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)

      def test_there_is_no_legacy_log_and_no_legacy_parameter(self):
          self.assertFalse(hasattr(serve, 'OVERVIEW_LOG'))
          self.assertEqual(list(inspect.signature(serve._overview_spawn).parameters), ['target', 'note'])
          self.assertEqual(list(inspect.signature(serve._overview_launch).parameters), ['key', 'target'])

      def test_spawn_writes_to_that_log_with_0600(self):
          with mock.patch.object(serve.subprocess, 'Popen') as popen:
              serve._overview_spawn(['--space', 'x'], note='n')
          path = serve._overview_log_path()
          self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
          self.assertEqual(popen.call_args[0][0][-2:], ['--space', 'x'])
  ```
- [ ] **Step 2: код.** `_overview_log_path()` без параметра — лише гілка `<DEAI_HOME>/logs` (+ `makedirs(mode=0o700)`, `chmod 0o700`); `_overview_spawn(target, note=None)`: `path = _overview_log_path()`, `os.chmod(path, 0o600)` безумовно; `_overview_launch(key, target)`; `_SYNC_RUNS[key] = {'popen', 'pending', 'started', 'target'}` (прибрати `'legacy'`, також у `_overview_watch`); видалити `OVERVIEW_LOG` і його коментар; `_overview_sync`: прибрати змінну `liga` і виклик `_overview_launch(key, target)`. `_overview_target` (`--legacy`/`LEAGUE_KEY`) і CLI `bin/overview_push.py --legacy` — без змін.
- [ ] **Step 3: тести, що ламає T7:** підміни `serve.OVERVIEW_LOG` (`test_dashboard.py:1303-1435`, `test_serve.py:2207-2267`, `test_legacy_comments.py:530`, `test_integrations_off.py:617-620`, `test_liga_migrate.py:552-569`) → тимчасовий `DEAI_HOME` (лог читається з `serve._overview_log_path()`); твердження «лог ЛІГИ — `OVERVIEW_LOG`, а не `<DEAI_HOME>/logs/…`» (`test_liga_migrate.py:552`) стають «той самий лог»; виклики `_overview_launch(key, legacy, target)` → `(key, target)`; у `tests/test_no_originals.py` `ALLOWED = set()`. Повний пакет зелений; `ls <справжній ~/.claude/pipeline-feedback>` не змінився.
- [ ] **Step 4: мутація:** повернути `legacy`-гілку (`if legacy: return os.path.expanduser('~/.claude/pipeline-feedback/x.log')`) у `_overview_log_path` — `NoOriginalsRead` (рядок `pipeline-feedback`) і `test_the_log_is_under_the_deai_home…` червоніють.
- [ ] **Step 5: коміт** `refactor(4d-4c): журнал синку дашборда — один (<DEAI_HOME>/logs), OVERVIEW_LOG і legacy-параметр геть`.

---

### Task 8: `/api/gitlab-*` — `Deprecation`; підказки `bin/state.py` — на `/api/vcs-*`

**Files:** Modify `app/serve.py` (`end_headers` 5571, `_guarded` 5656, маршрути 6134-6137, 6995-7001), `bin/state.py` (56, 74, 89), `tests/test_state.py`; Create `tests/test_gitlab_aliases.py`.

- [ ] **Step 1: тест (червоний)** `tests/test_gitlab_aliases.py`:
  ```python
  """Псевдоніми `/api/gitlab-*` (4d-4c, Р4): ті самі відповіді, що `vcs-*`, плюс `Deprecation` і `Link` на наступника."""
  import http.client
  import json
  import os
  import sys
  import tempfile
  import threading
  import unittest
  from unittest import mock

  _HERE = os.path.dirname(os.path.abspath(__file__))
  sys.path.insert(0, _HERE)
  for _p in ('app', 'bin'):
      sys.path.insert(0, os.path.join(os.path.dirname(_HERE), _p))
  import serve  # noqa: E402


  class AliasDeprecation(unittest.TestCase):
      def setUp(self):
          d = tempfile.TemporaryDirectory(prefix='alias-')
          self.addCleanup(d.cleanup)
          tmp = os.path.realpath(d.name)
          tdir = os.path.join(tmp, 't1')
          os.makedirs(tdir)
          with open(os.path.join(tdir, 'iterations.json'), 'w') as f:
              json.dump({'iterations': [], 'publish_url': None}, f)
          cfg = os.path.join(tmp, 'tasks.json')
          with open(cfg, 'w') as f:
              json.dump({'current': 't1', 'design_work_root': tmp, 'tasks': {'t1': {'dir': tdir, 'title': 'T'}}}, f)
          p = mock.patch.dict(os.environ, {'HOME': tmp, 'DC_TASKS_FILE': cfg})
          p.start()
          self.addCleanup(p.stop)
          os.environ.pop('DEAI_HOME', None)
          q = mock.patch.object(serve.Handler, 'log_message', lambda *a, **k: None)
          q.start()
          self.addCleanup(q.stop)
          self.httpd = serve.make_server(0)
          threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
          self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))
          self.port = self.httpd.server_address[1]

      def call(self, method, path, body=None):
          c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
          h = {'Origin': 'http://127.0.0.1:%d' % self.port}
          if body is not None:
              h['Content-Type'] = 'application/json'
          c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
          r = c.getresponse()
          data = r.read()
          out = (r.status, r.getheader('Deprecation'), r.getheader('Link'), data)
          c.close()
          return out

      def test_aliases_carry_the_headers_and_the_same_answer(self):
          for method, old, new, body in (('GET', '/api/gitlab-status', '/api/vcs-status', None),
                                         ('POST', '/api/gitlab-sync', '/api/vcs-push', {'it': 'it1'}),
                                         ('POST', '/api/gitlab-pull', '/api/vcs-pull', {})):
              s1, dep, link, b1 = self.call(method, old, body)
              s2, dep2, link2, b2 = self.call(method, new, body)
              self.assertEqual((s1, b1), (s2, b2), old)
              self.assertEqual(dep, 'true', old)
              self.assertEqual(link, '<%s>; rel="successor-version"' % new, old)
              self.assertIsNone(dep2, new)
              self.assertIsNone(link2, new)
  ```
- [ ] **Step 2: код.** Клас `Handler`: `_successor = None`; у `_guarded` поряд із `self._resp_started = False` — `self._successor = None`; у `end_headers` ПЕРШИМИ рядками:
  ```python
          if self._successor:                                  # 4d-4c: псевдонім `/api/gitlab-*` живе до 1.0
              self.send_header('Deprecation', 'true')
              self.send_header('Link', '<%s>; rel="successor-version"' % self._successor)
  ```
  Маршрути: `GET`: `if self.path.startswith('/api/gitlab-status'): self._successor = '/api/vcs-status'` перед викликом `_gitlab_status()` (гілку розділити на дві, як у POST); `POST`: `/api/gitlab-sync` → `self._successor = '/api/vcs-push'`, `/api/gitlab-pull` → `'/api/vcs-pull'`. Коментар над маршрутами: «псевдоніми до 1.0; видалення — після перемикання скіла dev-pipeline». `bin/state.py`: `/api/gitlab-sync` → `/api/vcs-push`, `/api/gitlab-pull` → `/api/vcs-pull` у підказках (рядки 74, 89 і докстрінг 56); `tests/test_state.py` — очікувані тексти.
- [ ] **Step 3:** `$PYT tests.test_gitlab_aliases tests.test_state` OK; пакет зелений. Мутація: не скидати `_successor` у `_guarded` → другий запит того ж зʼєднання отримує заголовок (додати в тест keep-alive-випадок за потреби) — перевірити вручну одним рядком, відновити.
- [ ] **Step 4: коміт** `feat(4d-4c): псевдоніми /api/gitlab-* — Deprecation + Link; підказки state на /api/vcs-*`.

---

### Task 9: JS — без `'legacy'` і без `integrations`

**Files:** Modify `app/spaces-model.js` (247, 272, 288, 296, 313, 565, 576 + коментарі), `app/connections-model.js` (141-179, 325), `app/connections-view.js` (134), `app/tasks-home.js` (99-105, 294, 324), `app/app.js` (2959-2960, 7176), `app/i18n.js` (`cnNowLegacy`, `cnDisableLegacy` в обох мовах); Create `tests/_space-fixtures.mjs`, `tests/space-predicates.test.mjs`; тести з Поправки 19.

- [ ] **Step 1: спільні фікстури й тест (червоні).** `tests/_space-fixtures.mjs`:
  ```js
  /* Простори для JS-тестів без ключа `integrations` (4d-4c): роль — це `capabilities`, ЛІГА — це `compat`. */
  export const NO_ROLES = { publish: null, tokens: null, comments: null, vcs: null, notify: null, dashboard: null, tracker: null };
  export const plainSpace = (caps = {}) => ({ id: "p", name: "P", color: "space-1", capabilities: { ...NO_ROLES, ...caps } });
  export const LIGA_SPACE = {
    id: "liga", name: "ЛІГА", color: "space-1",
    capabilities: { publish: "vercel-publish", tokens: null, comments: "supabase-comments", vcs: "git-sync", notify: "supabase-teams",
      dashboard: "supabase-dashboard", tracker: "jira-tracker" },
    compat: { publish: "design-canvas", vcs: "design-canvas", comments: "comment-layer" },
  };
  ```
  `tests/space-predicates.test.mjs`:
  ```js
  import test from "node:test";
  import assert from "node:assert/strict";
  import { hasNotify, hasPublish, hasTeamComments, hasVcs, isLegacyPublish, isLegacyVcs, taskCreateClones } from "../app/spaces-model.js";
  import { LIGA_SPACE, plainSpace } from "./_space-fixtures.mjs";

  test("роль без запису: плоский простір нічого не має", () => {
    const s = plainSpace();
    for (const f of [hasPublish, hasVcs, hasNotify, hasTeamComments]) assert.equal(f(s), false, f.name);
    assert.equal(isLegacyVcs(s), false);
    assert.equal(isLegacyPublish(s), false);
  });

  test("ЛІГА — це compat, а не значення 'legacy' і не прапорець", () => {
    assert.equal(isLegacyVcs(LIGA_SPACE), true);
    assert.equal(isLegacyPublish(LIGA_SPACE), true);
    for (const f of [hasPublish, hasVcs, hasNotify, hasTeamComments]) assert.equal(f(LIGA_SPACE), true, f.name);
    /* значення 'legacy' сервер не шле, і клієнт його не знає */
    assert.equal(isLegacyVcs({ capabilities: { vcs: "legacy" } }), false);
    assert.equal(isLegacyPublish({ capabilities: { publish: "legacy" } }), false);
  });

  test("невідомий простір (null, стара форма без capabilities) — як було: нічого не відбираємо", () => {
    for (const s of [null, undefined, { id: "x" }]) {
      for (const f of [hasPublish, hasVcs, hasNotify, hasTeamComments, isLegacyVcs, isLegacyPublish]) assert.equal(f(s), true, `${f.name} ${JSON.stringify(s)}`);
    }
  });

  test("taskCreateClones: клон — коли в тілі є vcs або простір зі схемою ЛІГИ й роллю vcs", () => {
    assert.equal(taskCreateClones(plainSpace({ vcs: "git-sync" }), {}), false);
    assert.equal(taskCreateClones(plainSpace({ vcs: "git-sync" }), { vcs: { repo: "g/r" } }), true);
    assert.equal(taskCreateClones(LIGA_SPACE, {}), true);
    assert.equal(taskCreateClones(plainSpace(), {}), false);
    assert.equal(taskCreateClones(null, {}), true);
  });
  ```
  `node --test tests/space-predicates.test.mjs` → червоніє (`integrations !== false` запасні гілки, `'legacy'`).
- [ ] **Step 2: `spaces-model.js`.**
  ```js
  export const hasTeamComments = (space) => {
    const caps = space?.capabilities;
    return caps && typeof caps === "object" && "comments" in caps ? caps.comments != null : true;
  };
  export const hasVcs = (space) => {
    const caps = space?.capabilities;
    return caps && typeof caps === "object" && "vcs" in caps ? caps.vcs != null : true;
  };
  export const hasNotify = (space) => {
    const caps = space?.capabilities;
    return caps && typeof caps === "object" && "notify" in caps ? caps.notify != null : true;
  };
  export const isLegacyVcs = (space) => {
    if (space?.compat?.vcs === "design-canvas") return true;
    const caps = space?.capabilities;
    return !(caps && typeof caps === "object" && "vcs" in caps);          /* ролі невідомо — як було */
  };
  export const taskCreateClones = (space, body) =>
    (body != null && "vcs" in body) || (hasVcs(space) && isLegacyVcs(space));
  export const hasPublish = (space) => (space?.capabilities ? !!space.capabilities.publish : true);
  export const isLegacyPublish = (space) => space?.compat?.publish === "design-canvas" || !space?.capabilities;
  ```
  Коментарі (докблоки над цими функціями): прибрати «за `integrations`», «`'legacy'` — зашитий шлях», «простір з `integrations` (`integrations_for`)»; пояснити «ключа нема → не знаємо → не крадемо (сервер ключа `integrations` більше не шле)».
- [ ] **Step 3: решта клієнта.**
  - `connections-model.js`: у `providerLine` видалити `if (v === "legacy") return { kind: "legacy" };`; у `roleCardId` — `prov !== "legacy" &&`; JSDoc `{kind: 'legacy'}`, коментар 325 («`'legacy'` після вимкнення…») — стерти. `connections-view.js:134`: `const txt = p.kind === "legacy" ? t("cnNowLegacy") : p.kind === "error" …` → починається з `p.kind === "error"`. `app.js:2959-2960`: `.map((c) => (c.consKey ? t(c.consKey) : t('cnDisableNone', roleTitle(c.role), c.noneKey ? t(c.noneKey) : '')))`. `i18n.js`: видалити `cnNowLegacy`, `cnDisableLegacy` (uk 892, 985; en 1856, 1947).
  - `tasks-home.js`: `const noIntegrations = (data) => data?.space?.integrations === false;` →
    ```js
    /** Простір без дашборда команди: відповідь знає `capabilities` і роль `dashboard` у ній порожня (4d-4c; було `integrations === false`). */
    const noDashboard = (data) => {
      const caps = data?.space?.capabilities;
      return !!(caps && typeof caps === "object" && "dashboard" in caps && caps.dashboard == null);
    };
    ```
    і всі використання `noIntegrations(` → `noDashboard(` (105, 294, 324); коментарі «Простір без інтеграцій» → «Простір без дашборда».
  - `app.js:7176`: `space: st.space ? { id: st.space.id, capabilities: st.space.capabilities, compat: st.space.compat } : null,`. Коментарі `app.js` 240/254/257/261/264, `shell-palette.js`, `shell-bar.js`, `bar-model.js` — прибрати згадки `integrations`.
- [ ] **Step 4: тести з Поправки 19 (правило).** `grep -n integrations <файл>` і для кожного входження: (а) фікстура `integrations: false` без `capabilities` → `...plainSpace()` (імпорт із `_space-fixtures.mjs`); (б) `integrations: true` без `capabilities` — видалити ключ (невідомо → як було); з `capabilities: {publish: "legacy"…}` → `LIGA_SPACE` (або фрагмент `compat`); (в) тести «запасна гілка за `integrations`, рівно `=== false`» → «ключа ролі нема → не крадемо» (ті самі твердження про `true`); (г) заголовки/коментарі — переписати; (д) `tests/spaces-publish.test.mjs`, `tests/vcs-client.test.mjs` (`taskCreateClones`: 47 входжень) — за таблицею Step 1. Золотий набір `tests/_legacy-golden-kit.mjs`: `LIGA = { id: "liga", name: "ЛІГА", color: "space-1", capabilities: { publish: "vercel-publish", tokens: null }, compat: { publish: "design-canvas" } }` і `space: { id: LIGA.id, capabilities: LIGA.capabilities, compat: LIGA.compat }` у `PALETTE`; `node --test tests/legacy-golden.test.mjs` ЗЕЛЕНИЙ без `UPDATE_GOLDEN` (розмітка байт у байт та сама; якщо ні — виправляти набір, не еталон).
- [ ] **Step 5:** `node --test tests/*.test.mjs && node tests/inspector-core.test.mjs` зелені; `i18n-keys.test.mjs` бачить обидві мови. Мутація: повернути `caps.vcs === "legacy"` у `isLegacyVcs` — `space-predicates` червоніє.
- [ ] **Step 6: коміт** `refactor(4d-4c): клієнт без 'legacy' і без integrations (предикати за capabilities/compat)`.

---

### Task 10: охоронці з мутаціями і паритет «після»

**Files:** Create `tests/test_no_integrations_flag.py`, `tests/test_outbound_parity_4d4c.py`; Modify `tests/test_liga_migrate_c.py` (`PublishJsGuard`).

- [ ] **Step 1: охоронці.** `tests/test_no_integrations_flag.py`:
  ```python
  """Охоронці 4d-4c: прапорець `integrations` і значення API `'legacy'` не вертаються в рантайм."""
  import ast
  import glob
  import os
  import re
  import unittest

  ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  GONE = {'integrations_on', 'integrations_for', 'require_integrations', 'IntegrationsOff', '_outbound_ok', '_liga_like', '_liga_flow',
          '_liga_track_repos', 'API_IMPLICIT', 'IMPLICIT_MODULE', '_implicit_on', 'NO_INTEGRATIONS_SPACE_MSG', 'OVERVIEW_LOG',
          'has_markers', 'LEGACY_MARKERS'}
  #: Єдиний виняток: валідатор реєстру толерує ключ (відкат 0.22 → 0.21 безпечний; Поправка 4).
  ALLOWED = {('app/spaces.py', '_validate'): 'реєстр толерує bool-ключ integrations'}


  def _docstrings(tree):
      out = set()
      for n in ast.walk(tree):
          if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
              b = getattr(n, 'body', None)
              if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                  out.add(b[0].value)
      return out


  class NoIntegrationsFlag(unittest.TestCase):
      """AST: у `app/**/*.py`, `bin/*.py`, `ops/*.py` (без `test_*`, без `app/liga_migrate.py`) нема ні літерала `'integrations'`, ні
      ключового аргумента `integrations=`, ні жодного імені з `GONE` (імʼя, атрибут, визначення)."""

      @staticmethod
      def offenders(source, name='<src>'):
          tree = ast.parse(source)
          doc = _docstrings(tree)
          found = []

          def walk(node, fn):
              for ch in ast.iter_child_nodes(node):
                  cur = ch.name if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
                  hit = ((isinstance(ch, ast.Constant) and ch.value == 'integrations' and ch not in doc)
                         or (isinstance(ch, ast.Name) and ch.id in GONE) or (isinstance(ch, ast.Attribute) and ch.attr in GONE)
                         or (isinstance(ch, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and ch.name in GONE)
                         or (isinstance(ch, ast.keyword) and ch.arg == 'integrations'))
                  if hit and (name, cur) not in ALLOWED:
                      found.append((name, cur, getattr(ch, 'lineno', 0)))
                  walk(ch, cur)
          walk(tree, 'module')
          return found

      def test_the_runtime_has_no_flag(self):
          files = [p for pat in ('app/**/*.py', 'bin/*.py', 'ops/*.py') for p in glob.glob(os.path.join(ROOT, pat), recursive=True)
                   if not os.path.basename(p).startswith('test_') and os.path.basename(p) != 'liga_migrate.py']
          self.assertGreater(len(files), 20)
          bad = []
          for p in sorted(files):
              with open(p, encoding='utf-8') as f:
                  bad += self.offenders(f.read(), os.path.relpath(p, ROOT))
          self.assertEqual(bad, [])

      def test_the_detector_catches_every_form(self):
          for src in ("x = sp['integrations']", "sp.get('integrations')", "spaces.integrations_on()", "def integrations_for(sp): pass",
                      "f(integrations=True)", "raise IntegrationsOff('x')", "from spaces import require_integrations"):
              with self.subTest(src=src):
                  self.assertTrue(self.offenders(src), src)
          for src in ("'''integrations'''", "def f():\n    '''integrations'''", "x = 'integrations-off'"):
              with self.subTest(src=src):
                  self.assertEqual(self.offenders(src), [], src)

      def test_the_allowed_exception_is_exactly_the_validator(self):
          with open(os.path.join(ROOT, 'app', 'spaces.py'), encoding='utf-8') as f:
              src = f.read()
          self.assertEqual(self.offenders(src, 'app/spaces.py'), [])
          self.assertTrue(self.offenders(src + "\ndef other(sp):\n    return sp.get('integrations')\n", 'app/spaces.py'))


  class NoLegacyApiValue(unittest.TestCase):
      """У `app/*.js` нема порівнянь із `"legacy"`; виняток — вигляд `publishReaction` (`view.kind`, `app.js`)."""
      CMP = re.compile(r'[!=]==?\s*["\']legacy["\']|["\']legacy["\']\s*[!=]==?')

      @classmethod
      def offenders(cls, text, name='<src>'):
          return [(name, i + 1) for i, line in enumerate(text.splitlines()) if cls.CMP.search(line) and 'view.kind' not in line]

      def test_no_comparison_with_the_literal_in_the_client(self):
          bad = []
          for p in sorted(glob.glob(os.path.join(ROOT, 'app', '*.js'))):
              with open(p, encoding='utf-8') as f:
                  bad += self.offenders(f.read(), os.path.basename(p))
          self.assertEqual(bad, [])

      def test_detector(self):
          for src in ('caps.vcs === "legacy"', "p.kind === 'legacy'", 'v !== "legacy"', '"legacy" === v'):
              self.assertEqual(len(self.offenders(src)), 1, src)
          for src in ("if (view.kind === 'legacy') {}", 'kind: "legacy"', 'x === "legacyx"'):
              self.assertEqual(self.offenders(src), [], src)


  class NoIntegrationsInClient(unittest.TestCase):
      """У коді (не в коментарях) `app/*.js` нема читання `integrations`."""
      @staticmethod
      def strip(text):
          return re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', text, flags=re.S))

      def test_clean(self):
          bad = []
          for p in sorted(glob.glob(os.path.join(ROOT, 'app', '*.js'))):
              with open(p, encoding='utf-8') as f:
                  if re.search(r'\bintegrations\b', self.strip(f.read())):
                      bad.append(os.path.basename(p))
          self.assertEqual(bad, [])
  ```
  У `tests/test_liga_migrate_c.py::PublishJsGuard` очікування `{'spaces-model.js': 1}` → `{}` (прогін `publish === "legacy"` у `app/*.js`).
  `$PYT tests.test_no_integrations_flag tests.test_liga_migrate_c` — зелені (після T4–T9 код чистий). **Мутації (по одній, `python3 -B`, `sha256` до/після):** (1) `serve.py`: `spaces.integrations_on()` у будь-якій функції → `test_the_runtime_has_no_flag` червоніє; (2) `spaces.py`: `sp.get('integrations')` поза `_validate` → `test_the_allowed_exception_is_exactly_the_validator`/основний; (3) `spaces-model.js`: `caps.vcs === "legacy"` → `NoLegacyApiValue`; (4) `tasks-home.js`: `data?.space?.integrations` → `NoIntegrationsInClient`; (5) `spaces-model.js`: `publish === "legacy"` → `PublishJsGuard`.
- [ ] **Step 2: паритет «після».** `tests/test_outbound_parity_4d4c.py`:
  ```python
  """Паритет 4d-4c: вихідні рішення 0.22 дорівнюють знімку 0.21, крім переліку `EXPECT_DIFF` (кожен елемент — свідома відмінність спеки)."""
  import json
  import os
  import sys
  import tempfile
  import unittest

  _HERE = os.path.dirname(os.path.abspath(__file__))
  sys.path.insert(0, _HERE)
  import make_before_4d4c as mk  # noqa: E402
  import spaces_guard  # noqa: E402

  FIX = os.path.join(_HERE, 'fixtures', 'outbound', 'before-4d4c.json')
  _REAL = None


  def setUpModule():
      global _REAL
      _REAL = spaces_guard.snapshot()


  def tearDownModule():
      spaces_guard.assert_untouched(_REAL)


  #: `шлях (стенд.розділ[.тіло]) → {листок: очікуване значення «після»}`. Лише ці піддерева можуть відрізнятись; решта — рівна знімку.
  EXPECT_DIFF = {
      # шар вимкнено й незафіксований простір — автопуш закрито (Поправка 2, свідома відмінність 5)
      'layer_off.autocommit': {'pushed': False},
      'liga.autocommit_unfixed': {'pushed': False},
      'liga_unmigrated.autocommit_unfixed': {'pushed': False},
      'plain.autocommit_unfixed': {'pushed': False},
      'plain_git.autocommit_unfixed': {'pushed': False},
      'layer_off.autocommit_unfixed': {'pushed': False},
      # немігрована ЛІГА: записів нема → закрито
      'liga_unmigrated.autocommit': {'pushed': False},
      'liga_unmigrated.registry': {'called': False, 'result': False},
      'liga_unmigrated.targets': {'gitlab': None},
      'liga_unmigrated.comment_channel': {'comment_channel': None},
      'layer_off.targets': {'gitlab': None},
      'layer_off.comment_channel': {'comment_channel': None},
      # Поправка 10 (T3): звичайний простір із ввімкненим модулем коментарів тепер отримує `comment_channel` — знімок 0.21 такого стенду
      # не має (`plain` без модуля коментарів), тож рядка в EXPECT_DIFF нема; факт закріплений прямо: `tests/test_outbound.py`
      # `test_a_plain_space_with_a_comments_module_gets_a_channel`.
      # task-new
      'plain.task_new.jira': {'status': 200, 'code': None, 'space': 'plain', 'created': True},        # було 409 no-integrations-space
      'plain.task_new.gitlab': {'status': 400, 'code': 'gitlab-needs-vcs-scheme', 'created': False},  # було 409
      'liga.task_new.from': {'status': 200, 'code': None, 'space': 'legacy', 'created': True},        # було 400 from-needs-plain-space
      'liga_unmigrated.task_new.from': {'status': 200, 'code': None, 'space': 'legacy', 'created': True},
      'liga_unmigrated.task_new.gitlab': {'status': 400, 'code': 'gitlab-needs-vcs-scheme', 'created': False},
      'layer_off.task_new.from': {'status': 200, 'code': None, 'created': True},
      'layer_off.task_new.gitlab': {'status': 400, 'code': 'gitlab-needs-vcs-scheme', 'created': False},
  }


  def _get(d, path):
      for k in path.split('.'):
          d = d[k]
      return d


  def _leaves(prefix, node, out):
      if isinstance(node, dict):
          for k, v in node.items():
              _leaves(prefix + (k,), v, out)
      else:
          out['.'.join(prefix)] = node


  class ParityAfter4d4c(unittest.TestCase):
      def test_after_equals_before_except_the_listed(self):
          with open(FIX, encoding='utf-8') as f:
              before = json.load(f)
          with tempfile.TemporaryDirectory(prefix='after-4d4c-') as tmp:
              after = mk.collect(tmp)
          b, a = {}, {}
          _leaves((), {k: v for k, v in before.items() if not k.startswith('_')}, b)
          _leaves((), after, a)
          allowed = [p + '.' for p in EXPECT_DIFF]
          changed = sorted(k for k in set(b) | set(a) if b.get(k, '<нема>') != a.get(k, '<нема>'))
          stray = [k for k in changed if not any(k.startswith(p) for p in allowed)]
          self.assertEqual(stray, [], 'вимірюна відмінність поза EXPECT_DIFF — ЗУПИНИТИСЬ і доповісти, перелік мовчки не розширювати')
          for path, want in EXPECT_DIFF.items():
              for leaf, val in want.items():
                  self.assertEqual(_get(after, path)[leaf], val, '%s.%s' % (path, leaf))
  ```
  Прогін. Вимірюваний набір може відрізнятись від таблиці (вона виведена з коду): якщо `stray` непорожній — це або вада коду, або неточність таблиці; рішення ухвалює контролер, перелік мовчки не розширюємо. Вилучені з таблиці рядки, що збіглися (`liga.autocommit`, `liga.registry`, `liga.targets`, `liga.comment_channel`, `plain*` рівні) — це доказ паритету.
- [ ] **Step 3:** повний пакет + JS зелені. **Коміт** `test(4d-4c): охоронці (NoIntegrationsFlag, NoLegacyApiValue, клієнт) і паритет «після» з EXPECT_DIFF`.

---

### Task 11: живі тести без `integrations`

**Files:** Modify `tests/live/fixture.mjs` (124-152, 248-256), `tests/live/{modules,spaces,comments,dashboard-role}.test.mjs`; перевірити `git-sync`, `vercel`, `liga-migrate`, `tasks-home`, `connections`.

- [ ] **Step 1: фікстура.** `isolatedMachine`: запис простору `{ id, name, path: spPath, legacy }` (без `integrations`) і в реєстр — `({ id, path: p, legacy })`; опція `integrations?: boolean` у JSDoc видалити; тека звичайного простору отримує `space.json` із `modules: { "static-publish": { enabled: true } }`, якщо тест не просить інакше (`sp.publish === false`) — це те, що 0.22 і так матеріалізує на старті, фікстура лише робить його видимим до першого запиту; повернення `{… spaces: [{id, name, path, legacy}]}`.
- [ ] **Step 2: свідки.** `modules.test.mjs:356` `assert.equal(spaces[0].integrations, false, …)` → `assert.equal(spaces[0].capabilities.vcs, null, "свідок: у звичайному просторі синку нема")`; `:472` `liga.integrations === true` → `liga.compat?.vcs === "design-canvas"` (ЛІГА з явними записами); `comments.test.mjs:589` — те саме для `ligaSpace`; `spaces.test.mjs:233` `made.integrations === false` → `made.capabilities.vcs === null`, плюс новий свідок: `GET /api/modules?space=<made.id>` → запис `static-publish` має `enabled === true`, `implicit === false`; `comments.test.mjs:639` (`integrations-off`) лишається — код API не змінився. Коментарі «`IMPLICIT_MODULE`» (`modules.test.mjs:14`) переписати.
- [ ] **Step 3: прогін по одному, послідовно:** `modules`, `spaces`, `git-sync`, `vercel`, `liga-migrate`, `comments`, `dashboard-role`, `tasks-home`, `connections` (команда з «Правил»). Падіння, не пов'язані з кодом (браузер, `HOME`), — окремо в звіті. `ls ~/deai-published ~/.deai` не змінились.
- [ ] **Step 4: коміт** `test(4d-4c): живі тести без integrations (capabilities/compat як свідки)`.

---

### Task 12: документи, версія 0.22.0

**Files:** Modify `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `package.json`.

- [ ] **Step 1: `package.json`** `"version": "0.22.0"`.
- [ ] **Step 2: `CHANGELOG.md`** — новий розділ `## [0.22.0] — <дата DD.MM.YYYY>` англійською, у стилі попередніх (Stage 4d-4c): абзац-підсумок (прапорець `integrations` і значення API `'legacy'` пішли; вихідна дія = запис `vcs` зі схемою ЛІГИ; для людини нічого не міняється у звичайному випадку); **Added** (`deai_modules.vcs_outbound`, `spaces.ensure_static_publish`/`materialize_static_publish`, `spaces.RoleOff`, заголовки `Deprecation`/`Link`, код `gitlab-needs-vcs-scheme`, охоронці `NoIntegrationsFlag`/`NoLegacyApiValue`); **Changed** (`task-new` без `space` — перший запис із `legacy: true`; `from` дозволено в будь-якому просторі без `gitlab`; `gitlab` лише за схемою ЛІГИ; `static-publish` — явний запис; журнал синку — `<DEAI_HOME>/logs/dashboard-sync.log`; `describe` без `integrations`); **Removed** (`spaces.integrations_for/_on/require_integrations`, `IntegrationsOff`, `_outbound_ok`, `_liga_flow`, `_liga_like`, 409 `no-integrations-space`, `gitlab-needs-integrations`, `from-needs-plain-space`, `OVERVIEW_LOG`, `API_IMPLICIT`, `IMPLICIT_MODULE`, i18n `cnNowLegacy`/`cnDisableLegacy`/`wzErrFromPlain`); **Fixed**-подібне — «міграція ЛІГИ без ключа `integrations` рахує його за маркерами кореня» (Поправка 1); розділ «Differences for a person» (5 пунктів спеки + `comment_channel`, `gitlab` у немігрованій ЛІГІ, шар вимкнено — без автопушу); «Rolling back 0.22 → 0.21»; «Left for 1.0» (`/api/gitlab-*`, запис `profile`, `design_work_roots`/`profile_repos`, ключ `implicit` у `/api/modules`); рядки «Design: `docs/superpowers/specs/2026-11-10-legacy-surface-gone-design.md`; plan: `docs/superpowers/plans/2026-11-10-legacy-surface-gone.md`; behaviour of 0.21.0 pinned by `tests/fixtures/outbound/before-4d4c.json`». Також у шапці «Next: stage 4d-4c…» (рядки 19-21) → «Next: Deai 1.0».
- [ ] **Step 3: `README.md`:** рядки 716-722 — `4d-4c (0.22)` позначити ✅ з коротким описом; рядок таблиці API `POST /api/task-new` (265) — прибрати «лише простір без інтеграцій» щодо `from`, дописати коди `gitlab-needs-vcs-scheme`; додати примітку «`/api/gitlab-*` — застарілі псевдоніми (`Deprecation`), видалення в 1.0». **`docs/design/spaces-and-modules.md`** (130-134): `4d-4c` ✅ (0.22.0) з переліком; «Left for 4d-4c» → «Left for 1.0».
- [ ] **Step 4: перевірки.** `grep -rn "integrations_on\|integrations_for\|require_integrations\|_liga_flow\|OVERVIEW_LOG" app bin ops` порожньо; `git diff --cached | grep -nE "<домашні префікси>"` нуль; повний пакет (Python ×3 + JS) і живі з Task 11 зелені; `git status --short` лише заплановане.
- [ ] **Step 5: коміт** `docs(4d-4c): CHANGELOG 0.22.0, README, дорожня карта; версія 0.22.0` (чотири файли; не пушити, не тегувати — це робить контролер).

---

## Таблиця мутацій (кожна має червоніти; `python3 -B`, по одній, файл відновлюється, `sha256` до/після збігається)

| # | Мутація | Червоніє |
|---|---|---|
| 1 | `deai_modules.vcs_outbound` без перевірки `compat` | `VcsOutbound.test_git_sync_without_the_liga_scheme_is_closed` |
| 2 | `serve._vcs_outbound_here` → `return True` | `OutboundGates.test_an_unfixed_request_space_is_closed`, `test_liga_pushes_a_plain_git_sync_space_does_not`, паритет |
| 3 | `registry_allowed` без умови `legacy` | `test_the_registry_is_for_a_liga_with_its_scheme_only` |
| 4 | `_task_comment_channel` → завжди канал | `test_the_task_comment_channel_follows_the_comments_provider` |
| 5 | `default_new_task_space` знову за `integrations` | `TaskNew.test_default_space_is_the_legacy_entry…` |
| 6 | `_ensure_static_publish_locked` без перевірки `STATIC_PUBLISH_ID in mods` | `test_a_disabled_record_is_a_human_decision`, `test_idempotent_to_the_byte` |
| 7 | `create_space` без запису `static-publish` | `test_a_new_space_has_the_record` |
| 8 | `_liga_integrations` → `liga.get('integrations') is True` | `LigaIntegrationsWithoutTheKey.test_a_fresh_liga_without_the_key_migrates` |
| 9 | `_overview_log_path` знову з гілкою `legacy` | `test_the_log_is_under_the_deai_home…`, `NoOriginalsRead` |
| 10 | не скидати `_successor` у `_guarded` | `AliasDeprecation` (keep-alive) |
| 11 | `caps.vcs === "legacy"` у `isLegacyVcs` | `space-predicates.test.mjs`, `NoLegacyApiValue` |
| 12 | `data?.space?.integrations` у `tasks-home.js` | `NoIntegrationsInClient`, `tasks-home.test.mjs` |
| 13 | будь-яке `spaces.integrations_on()` в `serve.py` | `NoIntegrationsFlag.test_the_runtime_has_no_flag` |
| 14 | прибрати рядок з `EXPECT_DIFF` (напр. `plain.task_new.jira`) | `ParityAfter4d4c` (`stray`) |

## Після всіх задач (контролер)

- Повний пакет Python ×3 + JS + живі з Task 11 зелені; `git log --oneline` — 12 комітів, кожен із зеленим деревом; ніщо з `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` і `2026-11-09-agents-sdk-policy-addendum.md` не застейджено.
- Контролер вирішує: R-A, R-B, R-C (див. «Рішення контролера»), тег `v0.22.0`, пуш.
- Чекліст переходу ЛІГИ (окремо, не цей етап): облікові Supabase/Jira — на «Підключеннях» після переходу; скіл dev-pipeline переходить з `gitlab-*` на `vcs-*` до видалення псевдонімів (1.0).
