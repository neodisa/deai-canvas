# Етап 4b-1 «Публікація ЛІГИ через `vercel-publish`» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** модуль `vercel-publish` отримує вхід через системний Vercel CLI (`auth: cli`) з прибиранням старих публікацій;
простір ЛІГА публікує через нього як неявний постачальник; транспорт Vercel зникає з `serve.py`. Реліз 0.9.0.

**Architecture:** режим `cli` — окрема гілка в `app/modules/vercel-publish/server.py`, яка запускає
`npx --yes vercel …` (ті самі команди й таймаути, що гілка ЛІГИ 0.8.0) і повертає КОДИ (класифікація виводу) та сирий
текст; людські тексти ЛІГИ лишаються в ядрі як адаптер (`_LEGACY_*` у `serve.py`) до 4d. Ядро для ЛІГИ будує `ctx`
вручну (як `_vcs_legacy_ctx` у 4a), кличе модуль через один шов `_publish_legacy_call` і складає відповідь
`/api/publish` байт у байт як у 0.8.0 (+ `cleanup_warning`). Каркас дає модулям `ctx['find_tool']` і повний текст
`ModuleError.full`.

**Tech Stack:** Python 3 stdlib (`unittest`, `subprocess`), фальшивий `npx` (виконуваний Python-скрипт у тимчасовій
теці), ванільний ES-модульний JS (`node:test`), Playwright Chromium для живого тесту.

**Спека:** `docs/superpowers/specs/2026-10-30-legacy-publish-module-design.md` (+ поправки нижче). Читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- <шляхи>
  ```
  Рядок `Co-Authored-By` — рівно такий (Opus 5.5), навіть якщо твоя власна модель інша. Коміт — лише з переліком шляхів.
- В індекс додавати лише свої файли поіменно. **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий файл
  `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` — не чіпати й не комітити.

**Прогони й середовище**

- Кожен прогін тестів — через охоронця памʼяті: `python3 "$G" <секунд> <МБ> <команда…>`. Шлях `$G` дає контролер.
- Не виставляти `DEAI_HOME` у шелі. Не чіпати: порти 8765 і 4317; справжні `~/.deai`, `~/deai-published`,
  `~/.gitconfig`, `tasks.json` дизайнера.
- Процеси зупиняти лише за PID. Ніколи `pkill`/`killall` за шаблоном.
- **Жодної мережі в тестах і жодного справжнього `vercel`.** `npx` — лише фальшивий (Task 2 дає помічник); перевірка
  превʼю — лише через підмінений шов `_fetch_page` модуля.

**Конвенції коду**

- Коментарі українською. Тексти інтерфейсу лише через `t()`, обидві мови (`UK` і `EN` у `app/i18n.js`); кирилиці в
  літералах `app/**/*.js` поза словником бути не може (`tests/i18n-literals.test.mjs`). Дані в розмітку лише через `esc()`.

**ЛІГА-golden і мутації**

- `tests/legacy-golden.test.mjs` і `tests/test_comments_role.py` (`GoldenPinTest`) — зелені БЕЗ `UPDATE_GOLDEN=1` /
  `UPDATE_COMMENTS_GOLDEN=1`.
- Кожна нова перевірка доводиться мутацією: прибрати охорону одним рядком → потрібний тест червоніє → файл відновлено
  побайтно (sha256). Мутації Python — лише `python3 -B`, з охоронцем і тайм-аутом, по одній.

**Набори тестів**

- Юніти: `npm test` (включає Python-набори `tests`, `bin`, `app`).
- Живі — лише послідовно: `node --test --test-concurrency=1 tests/live/<файл>`.
- Номери рядків — орієнтир («≈»): шукати за назвою функції.

---

## Поправки до спеки, знайдені під час планування

Вносяться в спеку тим самим комітом, що й план.

1. **`ctx['find_tool']` замість `ctx['npx']`.** `_node_bin` може запустити login-shell (повільно), а `ctx` будується
   для кожного `check`. Тому каркас кладе в `ctx` ФУНКЦІЮ `find_tool(name)` (лише `'npx'`/`'node'`, інше → `None`),
   яку ядро реєструє один раз (`deai_modules.set_tool_finder(_node_bin)`); модуль кличе її лише в режимі `cli`.
2. **`task['gated']`.** Модуль не знає пароля (гейт вкладає збірка ядра), тож ядро передає `gated: bool` у `task`.
   Режим `cli`: `gated` → `verified` лише з маркером `authgate` у тілі (як ЛІГА); без гейта → `verified` = 200. Режим
   `token` поле ігнорує.
3. **Тексти ЛІГИ лишаються в ядрі.** Підказки `_deploy_hint` і `_check_published` згадують конкретну людину, пароль
   `1100` і `tasks.json` — це тексти компанії, не модуля. Модуль класифікує вивід у коди (`vercel-login`,
   `vercel-scope`, `vercel-auth`, `vercel-deploy`, `vercel-no-url`, `no-node`) і віддає сирий текст; адаптер ЛІГИ в
   `serve.py` складає `deploy_error`/`verify_hint` тими самими рядками, що 0.8.0 (`_LEGACY_DEPLOY_HINTS`,
   `_LEGACY_PROTECTION_HINT`, `_LEGACY_NO_URL`). Звичайний простір бачить ці коди через i18n.
4. **Повний текст помилки.** `deai_modules._run` віддає вичищений, але НЕ обрізаний текст; обрізання до 300 робить
   конструктор `ModuleError` (`message`), повний лишається в новій властивості `ModuleError.full`.
5. **Поле токена не ховається.** Генеративна форма «Підключень» не має умовних полів; YAGNI — лише `required: false` і
   підпис «Токен Vercel (для входу «Токен»)». Обовʼязковість у режимі `token` перевіряє модуль, як і зараз.
6. **Нові коди в `STATUS` каркаса:** `no-node` 409, `vercel-login` 409, `vercel-scope` 409, `vercel-deploy` 502,
   `vercel-no-url` 502.
7. **Шов адаптера ЛІГИ** — одна функція ядра `_publish_legacy_call(task, tid, build_dir, proj, npx)`: тести гілки ЛІГИ
   підміняють її (замість `serve.subprocess.run`, `_stable_alias`, `_check_published`, `_remember_vercel_scope`).
8. **Живий тест** — шлях без мережі: фальшивий `npx` через `PATH` сервера, `deploy` без адреси у виводі → смуга ЛІГИ
   показує текст `_LEGACY_NO_URL`. Успішний шлях доводять Python-тести (перевірка превʼю — мережа).

---

## Структура файлів

| Файл | Що змінюється |
|---|---|
| `app/deai_modules.py` | `find_tool`/`set_tool_finder`, `ModuleError.full`, `_run` без обрізання, коди в `STATUS` |
| `app/modules/vercel-publish/module.json` | `auth` (select), `token` необовʼязковий, версія 1.1.0 |
| `app/modules/vercel-publish/server.py` | гілка `cli`: `_publish_cli`, `_cli_*`, `check` у режимі `cli`, прибирання CLI |
| `app/serve.py` | `set_tool_finder`, `gated` у `task_arg`, адаптер ЛІГИ (`_publish_legacy_ctx`, `_publish_legacy_call`, `_legacy_deploy_error`, `_LEGACY_*`), `_remember_vercel_scope(tid, task, org)`; геть: `_deploy_urls`, `_stable_alias`, `_check_published`, `_deploy_hint`, блок `subprocess.run([... 'vercel' ...])` |
| `app/app.js` | показ `cleanup_warning` у результаті публікації ЛІГИ |
| `app/connections-model.js`, `app/spaces-model.js`, `app/i18n.js` | коди `no-node`, `vercel-login`, `vercel-scope`, `vercel-deploy`, `vercel-no-url`; текст прибирання |
| `tests/fake_npx.py` (новий) | фальшивий `npx`: сценарій + журнал argv |
| `tests/test_vercel_publish_cli.py` (новий) | режим `cli` модуля |
| `tests/test_modules.py` | `find_tool`, `full`, коди |
| `tests/test_serve.py`, `tests/test_publish_module.py` | тести гілки ЛІГИ — на шов `_publish_legacy_call`; диференційний тест |
| `tests/fixtures/legacy-publish/before-4b1.json` (новий) | знімок поведінки 0.8.0 (Task 4, крок 1) |
| `tests/live/legacy-publish-cli.test.mjs` (новий) | живий тест, `PORT_BASE = 13800` |
| `CHANGELOG.md`, `README.md`, `docs/design/spaces-and-modules.md`, `docs/modules/authoring.md`, `package.json` | Task 7 |

---

### Task 1: каркас — `find_tool`, `ModuleError.full`, нові коди

**Files:**
- Modify: `app/deai_modules.py` (`ModuleError` ≈166, `STATUS` ≈144, `_run` ≈1461, `_ctx` ≈1543)
- Modify: `app/serve.py` (одразу після `def _node_bin`: реєстрація)
- Test: `tests/test_modules.py`

- [ ] **Step 1: Failing tests** — у `tests/test_modules.py` новий клас:

```python
class FindToolAndFullText(unittest.TestCase):
    """4b-1: `ctx['find_tool']` (лише npx/node) і повний текст помилки модуля (`ModuleError.full`)."""

    def tearDown(self):
        dm.set_tool_finder(None)

    def test_find_tool_only_known_names(self):
        seen = []
        dm.set_tool_finder(lambda name: seen.append(name) or f'/x/{name}')
        f = dm._find_tool
        self.assertEqual(f('npx'), '/x/npx')
        self.assertEqual(f('node'), '/x/node')
        self.assertIsNone(f('sh'))
        self.assertIsNone(f('../npx'))
        self.assertEqual(seen, ['npx', 'node'])           # невідоме імʼя шукач навіть не бачить

    def test_find_tool_default_is_which(self):
        dm.set_tool_finder(None)
        with mock.patch('shutil.which', lambda n: '/w/' + n):
            self.assertEqual(dm._find_tool('npx'), '/w/npx')

    def test_find_tool_finder_failure_is_none(self):
        def boom(name):
            raise OSError('no')
        dm.set_tool_finder(boom)
        self.assertIsNone(dm._find_tool('npx'))

    def test_module_error_full_text_survives_call(self):
        secret = 'S3CR3T-value-long-enough'
        long = ('x' * 900) + secret + ('y' * 100)

        def fn(ctx):
            raise dm.ModuleError('vercel-deploy', message=long)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(fn, fn, {'secrets': {'token': secret}})
        e = cm.exception
        self.assertEqual(e.code, 'vercel-deploy')
        self.assertEqual(len(e.message), 300)
        self.assertNotIn(secret, e.full)
        self.assertIn('***', e.full)
        self.assertTrue(e.full.endswith('y' * 100))

    def test_new_codes_have_status(self):
        for code, st in (('no-node', 409), ('vercel-login', 409), ('vercel-scope', 409),
                         ('vercel-deploy', 502), ('vercel-no-url', 502)):
            self.assertEqual(dm.STATUS[code], st, code)
```

Також перевірити `ctx`: у наявному тесті `module_ctx` (знайти за `'cache_dir'` у `tests/test_modules.py`) додати
`self.assertTrue(callable(ctx['find_tool']))`.

- [ ] **Step 2:** `python3 "$G" 300 2000 python3 -B -m unittest tests.test_modules -k FindToolAndFullText` → FAIL
  (`set_tool_finder` нема).

- [ ] **Step 3: Implementation** у `app/deai_modules.py`:

```python
#: Шукач інструментів машини для модулів (`ctx['find_tool']`): ядро реєструє свій (`serve._node_bin` знає
#: про nvm/volta/brew, яких нема в PATH GUI-застосунку); без реєстрації — `shutil.which`. Лише ці імена:
#: модуль не отримує загального «знайди мені будь-яку програму».
TOOL_NAMES = ('npx', 'node')
_TOOL_FINDER = [None]


def set_tool_finder(fn):
    """Зареєструвати шукач `fn(name) -> шлях | None` (`None` — назад до `shutil.which`)."""
    _TOOL_FINDER[0] = fn


def _find_tool(name):
    if name not in TOOL_NAMES:
        return None
    fn = _TOOL_FINDER[0] or shutil.which
    try:
        p = fn(name)
    except Exception:  # noqa: BLE001 — шукач не валить виклик модуля: «не знайдено»
        return None
    return p if isinstance(p, str) and p else None
```

(`import shutil` угорі, якщо його нема.) У `_ctx` — ключ `'find_tool': _find_tool` (і рядок у докстрінгах `_ctx` /
`module_ctx`). У `STATUS` — пʼять кодів поправки 6 з коментарем «модуль Vercel у режимі `cli` (4b-1)».

`ModuleError`: додати властивість

```python
    @property
    def full(self):
        """Повний текст (≤ `MAX_FULL_MESSAGE`); `message` — його перші 300 знаків."""
        return self._full
```

`_run`: у гілці коду з `STATUS` повертати `_scrub(e._full, secrets)` БЕЗ `[:MAX_MESSAGE]` (конструктор `ModuleError`
у `call` обріже `message` сам). Інші гілки `_run` — без змін. Перевірити ВСІХ споживачів `_run`/`val[1]` (`grep -n
"_run(" app/deai_modules.py`): де текст іде не в `ModuleError(...)`, а прямо в відповідь (наприклад, `check`), —
обрізати там `[:MAX_MESSAGE]`, щоб жодна відповідь не подовшала.

У `app/serve.py` одразу після визначення `_node_bin`:

```python
# 4b-1: модулі (режим `cli` у `vercel-publish`) шукають `npx` так само, як ядро (див. докстрінг вище).
deai_modules.set_tool_finder(_node_bin)
```

(якщо `deai_modules` імпортується нижче за `_node_bin` — поставити реєстрацію після імпорту.)

- [ ] **Step 4:** той самий прогін → PASS; потім `python3 "$G" 900 3000 python3 -B -m unittest discover -s tests -p 'test_modules*.py'` → PASS.
- [ ] **Step 5: Мутації** (по одній): (а) прибрати перевірку `name not in TOOL_NAMES` → `test_find_tool_only_known_names`
  червоніє; (б) повернути `[:MAX_MESSAGE]` у `_run` → `test_module_error_full_text_survives_call` червоніє.
- [ ] **Step 6: Commit** — `feat(4b-1): каркас — find_tool, ModuleError.full, коди режиму cli`.

---

### Task 2: модуль — режим `cli`: публікація (без прибирання) і `check`

**Files:**
- Create: `tests/fake_npx.py`
- Create: `tests/test_vercel_publish_cli.py`
- Modify: `app/modules/vercel-publish/module.json`, `app/modules/vercel-publish/server.py`

- [ ] **Step 1: Помічник `tests/fake_npx.py`**

```python
"""Фальшивий `npx` для тестів режиму `cli` (4b-1): справжній виконуваний файл у тимчасовій теці. Читає
`scenario.json` поруч із собою, дописує свій argv і cwd у `log.jsonl`, відповідає за підкомандою `vercel`.
Сценарій: {"<підкоманда>": {"code": 0, "stdout": "...", "stderr": "...", "org": "team_x"} | [ {...}, {...} ]}
(список — відповіді по черзі; останню повторює), `"org"` у `link` пише `.vercel/project.json` у cwd.
Мережі нема й бути не може: це лише Python, що друкує текст."""
import json
import os
import stat
import sys

SCRIPT = r'''#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(here, 'log.jsonl'), 'a', encoding='utf-8') as f:
    f.write(json.dumps({'argv': args, 'cwd': os.getcwd()}) + '\n')
sub = args[2] if len(args) > 2 and args[:2] == ['--yes', 'vercel'] else '?'
with open(os.path.join(here, 'scenario.json'), encoding='utf-8') as f:
    sc = json.load(f)
ans = sc.get(sub, {'code': 0})
if isinstance(ans, list):
    cnt_path = os.path.join(here, f'.n-{sub}')
    n = int(open(cnt_path).read()) if os.path.exists(cnt_path) else 0
    open(cnt_path, 'w').write(str(n + 1))
    ans = ans[min(n, len(ans) - 1)]
if ans.get('org'):
    os.makedirs('.vercel', exist_ok=True)
    with open(os.path.join('.vercel', 'project.json'), 'w') as f:
        json.dump({'orgId': ans['org'], 'projectId': 'prj_fake'}, f)
sys.stdout.write(ans.get('stdout', ''))
sys.stderr.write(ans.get('stderr', ''))
sys.exit(ans.get('code', 0))
'''


def make(dirpath, scenario):
    """Покласти `npx` + `scenario.json` у `dirpath`; повертає шлях до `npx`."""
    os.makedirs(dirpath, exist_ok=True)
    p = os.path.join(dirpath, 'npx')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(SCRIPT.replace('/usr/bin/env python3', sys.executable, 1))
    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    with open(os.path.join(dirpath, 'scenario.json'), 'w', encoding='utf-8') as f:
        json.dump(scenario, f)
    return p


def calls(dirpath):
    """Список `{'argv', 'cwd'}` у порядку викликів."""
    path = os.path.join(dirpath, 'log.jsonl')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]
```

(шебанг — справжній `sys.executable`, бо `env python3` у тестовому оточенні може вказати не туди.)

- [ ] **Step 2: Failing tests** `tests/test_vercel_publish_cli.py`. Модуль вантажити тим самим шляхом, що
  `tests/test_vercel_publish.py` (через `dm.catalog()`; з нього ж узяти обвʼязку `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`,
  `spaces_guard` і `Tripwire`, що забороняє будь-яке зʼєднання, крім `127.0.0.1`). `ctx` — `dm.module_ctx(space, MID)`
  простору з `settings: {auth: 'cli'}` АБО рукописний `{'settings': {'auth': 'cli', 'team': ''}, 'secrets': {},
  'find_tool': lambda n: npx, 'ModuleError': dm.ModuleError}` для гілок, де каркас не потрібен. Перевірка превʼю —
  через підміну `_fetch_page` у глобалах модуля: `(status, location, body)`.

Обовʼязкові сценарії (кожен — окремий тест; `D = 'https://pv-12345678-abc.vercel.app'`, `A = 'https://pv-12345678.vercel.app'`):

1. Успіх з гейтом: `deploy` друкує `D`, `inspect` друкує `A`, `link` з `org: 'team_x'`; сторінка `(200, '', '<div id="authgate">')`;
   `task = {'id': 't1', 'title': 'T', 'dir': d, 'gated': True, 'state': {'project': 'pv-12345678', 'task': 't1'}}` →
   результат `{'url': A, 'deploy_url': D, 'verified': True, 'verify': None, 'warnings': [], 'cleanup_warning': None,
   'state': {'project': 'pv-12345678', 'scope': 'team_x', 'task': 't1'}}` (прибирання з'явиться в Task 3 — тут
   сценарій `list` віддає `{"deployments": []}`); журнал: `['--yes','vercel','link','--yes','--project','pv-12345678']`,
   `['--yes','vercel','deploy','--prod','--yes']`, `['--yes','vercel','inspect', D]` — рівно в такому порядку, `cwd` = тека збірки.
2. Скоуп зі стану: `state.scope = 'team_a'` → `--scope team_a` у `link`, `deploy`, `inspect` НЕ отримує скоуп (як 0.8.0); налаштування `team` ігнорується, коли є стан.
3. Скоуп з налаштувань: стану нема, `settings.team = 'acme'` → `--scope acme`.
4. Імʼя зі стану чужої задачі (`state.task = 't2'`) → новий `pv-\d{8}`, відмінний від стану.
5. Імʼя зі стану не `pv-` (`'dc-x'`) — приймається (сумісність ЛІГИ).
6. Небезпечне імʼя/скоуп (`'--yes'`, `'a b'`, `'A'*101`, `'pv;rm'`) → `ModuleError('module-error')`, журнал порожній.
7. Нема `npx` (`find_tool` → `None`) → `ModuleError('no-node')`, журнал порожній.
8. Класифікація відмови `deploy` (код 1): `stderr` «Error: No existing credentials found. Please run `vercel login`» →
   `vercel-login`; «Error: You don't have access to the team 'x'» → `vercel-scope`; «Error: Forbidden» → `vercel-auth`;
   інше → `vercel-deploy`. У всіх `e.full` = останні ≤ 4000 знаків `stderr or stdout` (порядок як у 0.8.0: `stderr or stdout`).
9. `deploy` без жодної адреси `*.vercel.app` → `vercel-no-url`.
10. Таймаут `deploy` (підмінити `subprocess.run` модуля, що кидає `TimeoutExpired`) → `vercel-deploy`, `e.full` = `str(виняток)`.
11. Без гейта: сторінка `(200, '', '<html>')`, `gated: False` → `verified: True`; з гейтом і тим самим тілом → `verified: False`,
    `verify = {'reason': 'на URL відповідає не наш макет (немає гейта)'}` і попередження в `warnings`.
12. Захист Vercel: `(302, 'https://vercel.com/sso-api?…', '')` → `verify = {'reason': 'vercel_protection'}`, у `warnings` —
    той самий текст про Deployment Protection, що режим `token` (`_verify`), з іменем проєкту.
13. Найкоротша адреса: `deploy` друкує `D` і `A`, `inspect` нічого → `url == A`; `inspect` падає (код 1) → адреси з `deploy` лишаються.
14. Жодного токена: `ctx['secrets'] = {'token': 'vcp_SECRET-x'}` → у журналі (argv) і в оточенні фальшивого процесу (додати в
    сценарій збереження `os.environ` у журнал? — ні: перевірити, що модуль НЕ передає `env=`, тобто `subprocess.run`
    кличеться без `env`) токена нема.
15. `check` у режимі `cli`: `whoami` друкує `someone` → `{'ok': True, 'detail': 'someone'}`; код 1 → `{'ok': False, 'error':
    'vercel-login', 'detail': …}`; нема `npx` → `{'ok': False, 'error': 'no-node'}`; режим `token` — без змін (наявні тести).
16. Режим `token` не змінився: `tests/test_vercel_publish.py` зелений без правок.

- [ ] **Step 3:** прогін нового файла → FAIL.

- [ ] **Step 4: Implementation.**

`module.json` (версія `1.1.0`):

```json
{"api": 1, "id": "vercel-publish", "name": "Vercel", "version": "1.1.0",
 "roles": ["publish"], "publish_target": "url",
 "settings": [
   {"key": "auth", "type": "select", "label": "Вхід у Vercel", "default": "token",
    "options": [{"value": "token", "label": "Токен"},
                {"value": "cli", "label": "Системний Vercel CLI (vercel login на цій машині)"}]},
   {"key": "token", "type": "secret", "label": "Токен Vercel (для входу «Токен»)"},
   {"key": "team", "type": "text", "label": "Команда Vercel (slug або team_…; порожньо — особистий акаунт)"},
   {"key": "password", "type": "secret", "label": "Пароль превʼю (необовʼязково)"}
 ]}
```

`server.py` — нова секція «режим cli» (докстрінг модуля доповнити абзацом про режим `cli`, коди й відсутність токена):

```python
import subprocess
import ssl

CLI_LINK_S, CLI_DEPLOY_S, CLI_INSPECT_S = 120, 300, 120
CLI_WHOAMI_S = 30
CLI_RAW_MAX = 4000
CLI_PROJECT_RE = re.compile(r'[a-z0-9][a-z0-9._-]{0,99}')
CLI_SCOPE_RE = re.compile(r'[A-Za-z0-9_-]{1,100}')
_CLI_URL_RE = re.compile(r'https://[a-z0-9.-]+\.vercel\.app')
NO_GATE_REASON = 'на URL відповідає не наш макет (немає гейта)'


def _auth(ctx):
    s = ctx.get('settings') if isinstance(ctx, dict) else None
    return 'cli' if isinstance(s, dict) and s.get('auth') == 'cli' else 'token'


def _cli_npx(ctx):
    find = ctx.get('find_tool') if isinstance(ctx, dict) else None
    p = find('npx') if callable(find) else None
    if not p:
        raise _error(ctx, 'no-node', 'Не знайдено npx (Node.js): режим «Системний Vercel CLI» запускає `npx vercel`.')
    return p


def _vc(npx, args, cwd, timeout):
    """`npx --yes vercel <args>` у `cwd`; оточення — як у процесу (без `env=`: токенів модуль не додає)."""
    return subprocess.run([npx, '--yes', 'vercel', *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def _cli_urls(stdout, stderr):
    """Справжні адреси `*.vercel.app` з виводу (без дублів, порядок збережено) — НЕ вгадуємо (історія — `serve.py` 0.8.0)."""
    seen, out = set(), []
    for u in _CLI_URL_RE.findall((stdout or '') + '\n' + (stderr or '')):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _cli_code(raw):
    """Код відмови `deploy` за виводом CLI; порядок і шаблони — `_deploy_hint` 0.8.0 (вхід → скоуп → доступ)."""
    e = (raw or '').lower()
    if any(k in e for k in ('not authenticated', 'credentials', 'please log in', 'vercel login', 'no existing credentials')):
        return 'vercel-login'
    if any(k in e for k in ('--scope', 'scope not found', 'no such team', 'not a member of',
                            "don't have access to the team", 'team not found')):
        return 'vercel-scope'
    if any(k in e for k in ('forbidden', 'not authorized', 'access denied', 'do not have permission')):
        return 'vercel-auth'
    return 'vercel-deploy'


def _cli_alias(npx, dep_url, cwd, extra=()):
    """Найкоротша з адрес виводу `deploy` і `vercel inspect` (див. `_stable_alias` 0.8.0: коротка — продакшн-адреса)."""
    cands = list(extra) + [dep_url]
    try:
        r = _vc(npx, ['inspect', dep_url], cwd, CLI_INSPECT_S)
        cands += _cli_urls(r.stdout, r.stderr)
    except (OSError, subprocess.SubprocessError):
        pass
    return min(cands, key=len) if cands else dep_url


def _ssl_ctx():
    """certifi, якщо є (python.org на macOS не бачить системних сертифікатів), інакше типовий контекст."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch_page(url):
    """`(статус | None, Location, тіло ≤60000)` без облікових даних і без переходів; шов тестів."""
    try:
        op = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_ssl_ctx()))
        req = urllib.request.Request(url, method='GET', headers={'User-Agent': UA, 'Accept': 'text/html,*/*'})
        with op.open(req, timeout=PREVIEW_TIMEOUT_S) as r:
            return r.status, '', r.read(60000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.headers.get('Location') or '', ''
        finally:
            e.close()
    except Exception:  # noqa: BLE001 — перевірка лише інформує
        return None, '', ''


def _cli_verify(url, gated):
    """`None` — підтверджено; інакше `{'reason': …}`. З гейтом — лише маркер `authgate` у тілі (як ЛІГА 0.8.0)."""
    status, location, body = _fetch_page(url)
    if status == 200:
        if not gated or 'authgate' in body:
            return None
        return {'reason': NO_GATE_REASON}
    if status in REDIRECTS and 'vercel.com/sso' in location:
        return {'reason': 'vercel_protection'}
    return {'reason': f'HTTP {status}' if status is not None else 'адреса не відповіла'}


def _cli_link_scope(build_dir):
    try:
        with open(os.path.join(build_dir, '.vercel', 'project.json'), encoding='utf-8') as f:
            org = (json.load(f) or {}).get('orgId')
    except (OSError, ValueError):
        return None
    return org if isinstance(org, str) and CLI_SCOPE_RE.fullmatch(org) else None


def _cli_pick(ctx, state, task_id):
    st = state if isinstance(state, dict) else {}
    mine = st.get('task') == task_id
    project = st.get('project') if mine else None
    if project is None:
        project = 'pv-' + ''.join(secrets.choice('0123456789') for _ in range(8))
    scope = (st.get('scope') if mine else None) or (ctx.get('settings') or {}).get('team') or None
    if not isinstance(project, str) or not CLI_PROJECT_RE.fullmatch(project):
        raise RuntimeError('Імʼя проєкту в стані задачі недійсне — публікацію не запущено')
    if scope is not None and (not isinstance(scope, str) or not CLI_SCOPE_RE.fullmatch(scope)):
        raise RuntimeError('Команда Vercel (scope) недійсна — публікацію не запущено')
    return project, scope


def _publish_cli(ctx, build_dir, task):
    if not isinstance(build_dir, str) or not os.path.isdir(build_dir):
        raise RuntimeError('Збірка превʼю не є текою')
    task = task if isinstance(task, dict) else {}
    task_id = task.get('id') if isinstance(task.get('id'), str) else ''
    project, scope = _cli_pick(ctx, task.get('state'), task_id)   # ДО будь-якого запуску
    npx = _cli_npx(ctx)
    sc = ['--scope', scope] if scope else []
    try:
        _vc(npx, ['link', '--yes', *sc, '--project', project], build_dir, CLI_LINK_S)
        out = _vc(npx, ['deploy', '--prod', '--yes', *sc], build_dir, CLI_DEPLOY_S)
    except (OSError, subprocess.SubprocessError) as e:
        raise _error(ctx, 'vercel-deploy', str(e)) from None
    if out.returncode != 0:
        raw = out.stderr or out.stdout or ''
        raise _error(ctx, _cli_code(raw), raw[-CLI_RAW_MAX:])
    urls = _cli_urls(out.stdout, out.stderr)
    if not urls:
        raise _error(ctx, 'vercel-no-url', 'Vercel не надрукував адреси публікації')
    url = _cli_alias(npx, urls[-1], build_dir, extra=urls)
    verify = _cli_verify(url, bool(task.get('gated')))
    warnings = []
    if verify is not None:
        warnings.append(_PROTECTION_TEXT.format(project=project) if verify['reason'] == 'vercel_protection'
                        else f'Не вдалося підтвердити превʼю: {verify["reason"]}')
    cleanup_warning = None                                         # Task 3
    state = {'project': project, 'task': task_id}
    got = scope or _cli_link_scope(build_dir)
    if got:
        state['scope'] = got
    return {'url': url, 'deploy_url': urls[-1], 'verified': verify is None, 'verify': verify,
            'warnings': [_utf8(w)[:WARN_MAX] for w in warnings[:MAX_WARNINGS]],
            'cleanup_warning': cleanup_warning, 'state': state}
```

Текст про захист: винести наявний рядок із `_verify` у константу `_PROTECTION_TEXT = ('Превʼю закрите захистом Vercel
… проєкт {project} …')` і використати в обох місцях (режим `token` — той самий рядок, побайтно; тест 16 це стереже).
`REDIRECTS` — наявна константа модуля (перевірити імʼя). `state` без `scope`, коли його нема: `_checked_url_result`
ядра приймає лише рядки й числа.

`publish`: на початку `_publish` — `if _auth(ctx) == 'cli': return _publish_cli(ctx, build_dir, task)` (ДО
`_need_token`); обгортка `publish` уже перетворює `RuntimeError` на `module-error` з чистим текстом, а `_error(...)`
дає `ModuleError` ядра з потрібним кодом.

`check`: на початку — гілка `cli`:

```python
    if _auth(ctx) == 'cli':
        find = ctx.get('find_tool')
        npx = find('npx') if callable(find) else None
        if not npx:
            return {'ok': False, 'error': 'no-node', 'detail': 'npx (Node.js) не знайдено'}
        sc = (ctx.get('settings') or {}).get('team')
        try:
            r = _vc(npx, ['whoami', *(['--scope', sc] if sc and CLI_SCOPE_RE.fullmatch(sc) else [])], None, CLI_WHOAMI_S)
        except (OSError, subprocess.SubprocessError) as e:
            return {'ok': False, 'error': 'vercel-login', 'detail': _utf8(str(e))[:200]}
        if r.returncode != 0:
            return {'ok': False, 'error': 'vercel-login', 'detail': _utf8((r.stderr or r.stdout or '')[-200:])}
        lines = (r.stdout or '').strip().splitlines()
        return {'ok': True, 'detail': _utf8(lines[-1] if lines else '')[:100]}
```

- [ ] **Step 5:** новий файл і `tests/test_vercel_publish.py` → PASS.
- [ ] **Step 6: Мутації** (по одній): (а) прибрати `gated`-умову (`if not gated or 'authgate' in body` → `return None`) →
  тест 11 червоніє; (б) передати `env={**os.environ, 'VERCEL_TOKEN': …}` у `_vc` → тест 14 червоніє; (в) прибрати
  `fullmatch` імені → тест 6 червоніє; (г) поміняти порядок класифікації (доступ перед скоупом) → тест 8 червоніє.
- [ ] **Step 7: Commit** — `feat(4b-1): vercel-publish — вхід через системний Vercel CLI`.

---

### Task 3: модуль — прибирання в режимі `cli`

**Files:**
- Modify: `app/modules/vercel-publish/server.py`
- Test: `tests/test_vercel_publish_cli.py`

Форма `vercel list <проєкт> --json` (CLI 65.8.0, перевірено 30.10.2026 лише читанням):
`{"contextName": str, "deployments": [{"url": "<хост без схеми>", "name": str, "state": str, "target": str,
"createdAt": int, …}], "pagination": {"count": int, "next": int | null, "prev": int}}`.

- [ ] **Step 1: Failing tests** (фальшивий `npx`; сценарій `list` — список відповідей по сторінках):

1. 5 записів `name == P` (`createdAt` 1…5, поточна = найновіша з `url` без схеми, що відповідає `deploy_url`) → `remove` кличеться
   для 2 найстаріших: `['--yes','vercel','remove','<url1>','--safe','--yes']` і для `<url2>`; `cleanup_warning is None`.
2. Поточна НЕ найновіша в списку (хтось опублікував паралельно) → поточна лишається завжди; лишається 3 разом із нею.
3. Записи з `name != P` не видаляються ніколи (навіть найстаріші).
4. ⛔ Жоден виклик `remove` не містить `P` як окремий аргумент (`P not in argv[3:]` для кожного `remove`).
5. `list` код 1 / не JSON / `deployments` не список / запис без `url` чи `createdAt` → жодного `remove`; `cleanup_warning` —
   рядок («Старі публікації не прибрано: …»); результат публікації успішний.
6. `remove` одного з двох падає → другий все одно пробується; `cleanup_warning` згадує, скільки не прибрано.
7. Пагінація: перша сторінка з `pagination.next = 123` → другий виклик із `--next 123`; не більше `CLI_LIST_PAGES = 5` сторінок.
8. Скоуп: є `scope` → `--scope S` і в `list`, і в `remove`; нема → без `--scope` (CLI бере привʼязку теки, `cwd` = тека збірки).
9. Межа часу: `CLEANUP_MAX_S` вичерпано (підмінити `time.monotonic`) → решта не видаляється, `cleanup_warning`.
10. `cleanup_warning` (коли є) також у `warnings` (звичайний простір бачить його через наявний ланцюжок `warnings`).

- [ ] **Step 2:** → FAIL.
- [ ] **Step 3: Implementation**

```python
CLI_LIST_S, CLI_REMOVE_S, CLI_LIST_PAGES = 60, 60, 5


def _cli_cleanup(npx, project, scope, current_url, cwd):
    """Прибрати старі публікації проєкту `project`, лишивши `KEEP` разом із поточною. `None` або текст попередження.
    ⛔ `vercel remove` отримує ЛИШЕ адреси публікацій: з іменем проєкту CLI видаляє ВЕСЬ проєкт. `--safe` — CLI сам
    пропускає публікації з активним alias. Чіпаємо лише записи з `name == project`."""
    deadline = time.monotonic() + CLEANUP_MAX_S
    sc = ['--scope', scope] if scope else []
    items, nxt = [], None
    for _ in range(CLI_LIST_PAGES):
        try:
            r = _vc(npx, ['list', project, '--json', *sc, *(['--next', str(nxt)] if nxt else [])], cwd, CLI_LIST_S)
            data = json.loads(r.stdout) if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError):
            data = None
        deps = data.get('deployments') if isinstance(data, dict) else None
        if not isinstance(deps, list):
            return 'Старі публікації не прибрано: Vercel CLI не віддав список публікацій.'
        for d in deps:
            if not (isinstance(d, dict) and d.get('name') == project):
                continue
            u, t = d.get('url'), d.get('createdAt')
            if not isinstance(u, str) or not u or not isinstance(t, (int, float)):
                return 'Старі публікації не прибрано: список публікацій має незнайому форму.'
            items.append((t, u))
        pg = data.get('pagination') if isinstance(data.get('pagination'), dict) else {}
        nxt = pg.get('next')
        if not isinstance(nxt, int) or nxt <= 0:
            break
    cur = _host(current_url)
    old = [u for _t, u in sorted(items, reverse=True) if _host(u) != cur]
    doomed = old[KEEP - 1:]
    failed = 0
    for u in doomed:
        if time.monotonic() >= deadline:
            failed += 1
            continue
        try:
            r = _vc(npx, ['remove', u, '--safe', '--yes', *sc], cwd, CLI_REMOVE_S)
            failed += r.returncode != 0
        except (OSError, subprocess.SubprocessError):
            failed += 1
    return f'Старі публікації прибрано не всі: не вдалося {failed} з {len(doomed)}.' if failed else None
```

`_host` — наявна функція модуля (нормалізує `https://host` і голий `host`; перевірити, що голий хост вона приймає;
інакше — нормалізувати тут: `u.split('://')[-1].split('/')[0].lower()`). У `_publish_cli` замість заглушки:

```python
    cleanup_warning = _cli_cleanup(npx, project, scope, urls[-1], build_dir)
    if cleanup_warning:
        warnings.append(cleanup_warning)
```

(ПІСЛЯ перевірки, до формування результату; збій прибирання ніколи не кидає.)

- [ ] **Step 4:** → PASS.
- [ ] **Step 5: Мутації:** (а) прибрати фільтр `name == project` → тест 3 червоніє; (б) додати `project` в аргументи `remove` → тест 4; (в) прибрати `--safe` → тест 1; (г) прибрати виключення поточної
  (`if _host(u) != cur`) → тест 2.
- [ ] **Step 6: Commit** — `feat(4b-1): vercel-publish — прибирання старих публікацій у режимі cli`.

---

### Task 4: ядро — ЛІГА через модуль; транспорт Vercel геть із `serve.py`

**Files:**
- Create: `tests/fixtures/legacy-publish/before-4b1.json`
- Modify: `app/serve.py` (`Handler._publish` ≈7392–7552, `_publish_by_url` ≈4373, `_remember_vercel_scope` ≈4541,
  `_deploy_hint` ≈317, `_deploy_urls` ≈3622, `_stable_alias` ≈4569, `_check_published` ≈4590)
- Modify: `tests/test_serve.py` (≈2600–2660 `VercelScopeBinding`, ≈3660), `tests/test_publish_module.py` (≈580–645, ≈825)
- Test: новий клас `LegacyPublishViaModule` у `tests/test_publish_module.py`

- [ ] **Step 1: Знімок 0.8.0 (ДО будь-якої зміни коду).** Тимчасовий скрипт у скретчпаді (НЕ в репо), що на ПОТОЧНОМУ коді:
  створює задачу ЛІГИ (як `BuildPreview`-тести гілки ЛІГИ в `tests/test_publish_module.py`: тимчасовий `DC_TASKS_FILE`,
  `DC_NO_OVERVIEW=1`, тека задачі з однією опублікованою ітерацією), підміняє `serve._node_bin` → фальшивий `npx`
  (`tests/fake_npx.py`; `deploy` друкує `D` і `A`, `link` з `org: 'team_x'`, `inspect` друкує `A`), `serve._check_published` →
  `{'verified': True}`, `serve._registry_push` і `git_autocommit` → шпигуни, і викликає `POST /api/publish` чотири рази
  (успіх; `deploy` код 1 зі `stderr` «Please run vercel login»; `deploy` без адреси; без `npx`). Для кожного пише в JSON:
  тіло відповіді (з порядком ключів — як список пар), `vercel_project`/`vercel_scope` з `tasks.json`, поля публікації з
  `iterations.json` (без `published_at` — лише його наявність), argv-журнал фальшивого `npx`, виклики шпигунів. Результат —
  `tests/fixtures/legacy-publish/before-4b1.json`. Комітити лише JSON (з поясненням у коміті, яким скриптом знято).
- [ ] **Step 2: Failing tests** `LegacyPublishViaModule`:
  1. **Диференційний:** ті самі чотири сценарії на НОВОМУ коді: справжній модуль, фальшивий `npx` через
     `serve._node_bin`, перевірка превʼю — підміна `_fetch_page` модуля (`(200, '', 'authgate')`; знайти модуль через
     `deai_modules.catalog().get('vercel-publish')` і підмінити функцію в його просторі імен — так само, як
     `tests/test_vercel_publish.py` підміняє `_fetch_preview`), сценарій `list` → `{"deployments": []}`. Порівняння зі
     знімком: тіло (ключі й порядок, значення), `tasks.json`, `iterations.json`, шпигуни — РІВНІ; argv-журнал — знімок є
     ПРЕФІКСОМ нового, а решта — лише `list` (і `remove`, якщо є).
  2. Прибирання ЛІГИ: `list` з 5 записами → `remove` двох; `cleanup_warning` відсутній у відповіді. `list` падає →
     `cleanup_warning` — ОСТАННІЙ ключ відповіді.
  3. Відповідь `deploy_error` для кодів: `vercel-login`/`vercel-scope`/`vercel-auth` → `f'{hint}\n\n— вивід vercel —\n{raw[-300:]}'`
     з рядками `_LEGACY_DEPLOY_HINTS`; `vercel-deploy` → `raw[-400:]`; `raw` довжиною 1000 → хвіст справді 300/400 (доказ, що
     повний текст дійшов через `ModuleError.full`).
  4. `verify.reason == 'vercel_protection'` → `verify_error = 'vercel_protection'`, `verify_hint = _LEGACY_PROTECTION_HINT`.
  5. Імʼя мінтиться ДО деплою: `deploy` падає → `vercel_project` у `tasks.json` уже записано (як 0.8.0).
  6. Скоуп: модуль повернув `state.scope = 'team_x'`, у задачі `vercel_scope` нема → записано; є інший → НЕ перезаписано.
  7. `publish_remote` в `iterations.json` ЛІГИ не з'являється.
  8. Модуль не завантажився (підмінити каталог) → `deploy_error` з текстом «vercel-publish module is not loaded», не 500;
     `git_autocommit` і `_overview_sync` викликано.
  9. Звичайний простір: `_publish_by_url` передає `gated` у `task` модуля (`True` з паролем, `False` без).
  10. Статичний: у `app/serve.py` нема `'vercel', 'deploy'`, `'vercel', 'link'`, `def _deploy_urls`, `def _stable_alias`,
      `def _check_published`, `def _deploy_hint`.
- [ ] **Step 3:** → FAIL.
- [ ] **Step 4: Implementation** у `app/serve.py`:

```python
#: Модуль, яким публікує простір ЛІГА (4b-1): той самий `vercel-publish`, вхід — системний Vercel CLI.
PUBLISH_LEGACY_MODULE = 'vercel-publish'

#: Тексти ЛІГИ (байт у байт із `_deploy_hint`/`_check_published` 0.8.0): модуль віддає КОД, людський текст — тут,
#: бо він про людей і правила цієї компанії. Зникнуть разом із простором ЛІГА (4d).
_LEGACY_DEPLOY_HINTS = {
    'vercel-login': <рядок гілки «not authenticated» з _deploy_hint>,
    'vercel-scope': <рядок гілки скоупу з _deploy_hint>,
    'vercel-auth': <рядок гілки «forbidden» з _deploy_hint>,
}
_LEGACY_PROTECTION_HINT = <рядок 'hint' з _check_published>
_LEGACY_NO_URL = ('деплой пройшов, але URL у виводі vercel не знайдено — '
                  'посилання не зберігаю, щоб не вигадати неправильне')


def _publish_legacy_ctx(npx):
    """`ctx` неявного постачальника публікації ЛІГИ. ⛔ НЕ `module_ctx()`: у ЛІГИ нема `space.json`, а секретів модуль
    у режимі `cli` не читає (див. `_vcs_legacy_ctx`)."""
    return {'space': {'id': spaces.request_space_id() or '', 'path': ''},
            'settings': {'auth': 'cli', 'team': ''}, 'secrets': {},
            'folder_ok': lambda folder: (False, 'bad-folder'),
            'ModuleError': deai_modules.ModuleError, 'find_tool': lambda name: npx if name == 'npx' else None}


def _publish_legacy_call(task, tid, build_dir, proj, npx):
    """Шов адаптера ЛІГИ: модуль `vercel-publish` у режимі `cli` → його результат (перевірений) або `ModuleError`."""
    m = deai_modules.catalog().get(PUBLISH_LEGACY_MODULE)
    if m is None or m.status != 'ok':
        raise deai_modules.ModuleError('module-error', message=f'{PUBLISH_LEGACY_MODULE} module is not loaded')
    state = {'project': proj, 'task': tid}
    if task.get('vercel_scope'):
        state['scope'] = task['vercel_scope']
    arg = {'id': tid, 'title': task.get('title', tid), 'dir': task['dir'], 'gated': True, 'state': state}
    res = deai_modules.call(m, 'publish', _publish_legacy_ctx(npx), build_dir, arg)
    _checked_url_result(res)
    if not isinstance(res.get('deploy_url'), str):
        raise deai_modules.ModuleError('module-error', message='publish returned no deploy_url')
    return res


def _legacy_deploy_error(e):
    """`deploy_error` ЛІГИ з відмови модуля — рядок 0.8.0: підказка + хвіст виводу, або лише хвіст."""
    if e.code == 'vercel-no-url':
        return _LEGACY_NO_URL
    raw = e.full or e.message or e.code
    hint = _LEGACY_DEPLOY_HINTS.get(e.code)
    return f'{hint}\n\n— вивід vercel —\n{raw[-300:]}' if hint else raw[-400:]
```

`_remember_vercel_scope(tid, task, org)` — тепер бере значення (`org` або `None`), а не теку; решта логіки (не
перезаписувати наявний, запис у `tasks.json`, `task['vercel_scope'] = org`) — та сама.

Гілка `'legacy'` у `Handler._publish` після `if not npx: …return` (той блок — без змін):

```python
            try:
                res = _publish_legacy_call(task, tid, pub, proj, npx)
            except deai_modules.ModuleError as e:
                result['deploy_error'] = _legacy_deploy_error(e)
            else:
                url = res['url']
                _remember_vercel_scope(tid, task, (res.get('state') or {}).get('scope'))
                _registry_push(tid)
                fresh = load_meta(task)
                fresh['publish_url'] = url
                fresh['published_at'] = time.strftime('%d.%m.%Y %H:%M')
                fresh['publish_verified'] = res['verified']
                save_meta(task, fresh)
                result['url'] = url
                result['deploy_url'] = res['deploy_url']
                warn = _preview_domain_warning(url, proj)
                if warn:
                    result['domain_warning'] = warn
                owner = _not_task_link(task)
                if owner:
                    result['not_task_link'] = owner
                result['verified'] = res['verified']
                if not res['verified']:
                    v = res.get('verify') or {}
                    result['verify_error'] = v.get('reason')
                    if v.get('reason') == 'vercel_protection':
                        result['verify_hint'] = _LEGACY_PROTECTION_HINT
                if isinstance(res.get('cleanup_warning'), str) and res['cleanup_warning']:
                    result['cleanup_warning'] = res['cleanup_warning']
            git_autocommit(task['dir'], f'publish: {len(its)} iteration(s)')
```

Звірити з 0.8.0: `verify_error` = `check.get('reason')` (`None`, коли причини нема — ключ таки писався); порядок ключів —
як у старому блоці. Перенести всі коментарі-уроки старого блоку (чому не вгадуємо URL, чому перечитуємо
`iterations.json`, чому скоуп іде в реєстр) — у докстрінги нових функцій або в модуль, не губити.

`_publish_by_url`: `task_arg` отримує `'gated': gate_pw is not None`.

Видалити: `_deploy_urls`, `_stable_alias`, `_check_published`, `_deploy_hint`, старий блок `subprocess.run`. `_ssl_context`
лишити, якщо його ще хтось кличе (`grep`), інакше теж видалити.

Тести гілки ЛІГИ: місця, що підміняють `serve.subprocess.run`/`_stable_alias`/`_check_published`/`_remember_vercel_scope`
(`tests/test_publish_module.py` ≈600–645, ≈825; `tests/test_serve.py` ≈3660), переходять на підміну
`serve._publish_legacy_call` (повертає `{'url', 'deploy_url', 'verified', 'verify', 'warnings', 'cleanup_warning',
'state'}`) — суть перевірок та сама. `toggled_meanwhile` (≈619) перемикає зелену крапку ВСЕРЕДИНІ підміненого шва. Тести
`_deploy_hint` (`tests/test_serve.py` ≈2646–2655) → тести `_legacy_deploy_error` з тими ж очікуваними рядками; тести
`_remember_vercel_scope` (≈2625–2640) → нова сигнатура. Кожну зміну наявного тесту — рядком у звіті.

- [ ] **Step 5:** `python3 "$G" 1500 3000 npm test` → PASS (усе); `legacy-golden` без `UPDATE_GOLDEN`.
- [ ] **Step 6: Мутації:** (а) `raw[-300:]` → `raw[-299:]` → тест 3; (б) прибрати `_remember_vercel_scope(...)` → тест 6;
  (в) прибрати `gated` з `_publish_by_url` → тест 9; (г) пропустити `cleanup_warning` → тест 2.
- [ ] **Step 7: Commit(и)** — знімок окремим комітом ДО змін коду (`test(4b-1): знімок публікації ЛІГИ 0.8.0`), потім
  `feat(4b-1): ЛІГА публікує через vercel-publish; транспорт Vercel геть із ядра`.

---

### Task 5: клієнт — коди, `cleanup_warning`, тексти

**Files:**
- Modify: `app/connections-model.js` (≈186), `app/spaces-model.js` (≈809–860), `app/app.js` (≈1881–1944), `app/i18n.js`
- Test: наявні JS-тести моделей (`tests/connections-model*.test.mjs`, `tests/spaces-publish.test.mjs`) + нові випадки

- [ ] **Step 1: Failing tests:**
  - `connections-model`: `verdictText`/мапа помилок перевірки дає тексти для `no-node` і `vercel-login` (обидві мови).
  - `spaces-model`: мапа відмов публікації — `no-node`, `vercel-login`, `vercel-scope`, `vercel-deploy`, `vercel-no-url`;
    `vercel-deploy` несе текст сервера другим абзацом (як `module-error`), інші — без.
  - результат публікації ЛІГИ з `cleanup_warning` показує його окремим рядком (функція, що складає повідомлення
    результату в `app.js` чи моделі — знайти, де читаються `domain_warning`/`verify_error`, і додати поруч тим самим
    способом); без ключа — повідомлення побайтно як було.
  - `tests/i18n-literals.test.mjs` і перевірка паритету UK/EN — зелені.
- [ ] **Step 2:** → FAIL. **Step 3:** реалізація (ключі `cnErrNoNode`, `cnErrVercelLogin`, `publishErrNoNode`,
  `publishErrVercelLogin`, `publishErrVercelScope`, `publishErrVercelDeploy`, `publishErrVercelNoUrl`,
  `publishCleanupWarn`). Тексти — коротко, без імен людей і без `tasks.json`; «Системний Vercel CLI не увійшов — виконайте
  `npx vercel login` на цій машині» тощо. **Step 4:** `npm test` → PASS. **Step 5:** мутація — прибрати один код із
  мапи → його тест червоніє. **Step 6: Commit** — `feat(4b-1): клієнт — коди входу через CLI, попередження прибирання`.

---

### Task 6: живий тест

**Files:** Create `tests/live/legacy-publish-cli.test.mjs` (`const PORT_BASE = 13800;`)

- [ ] Простір ЛІГА (як `tests/live/publish-not-task-link.test.mjs`: `startServer(dir, { portBase: PORT_BASE, env })`),
  `env.PATH = <тимчасова тека з фальшивим npx> + ':' + process.env.PATH` (фальшивий `npx` — той самий скрипт; для Node
  записати його з `tests/fake_npx.py` через `python3 -c "import sys; sys.path.insert(0,'tests'); import fake_npx;
  fake_npx.make(<тека>, <сценарій>)"`), сценарій: `deploy` код 0 без жодної адреси. Позначити ітерацію опублікованою,
  натиснути «Опублікувати» в смузі → у результаті видно текст `_LEGACY_NO_URL`; журнал фальшивого `npx` містить `link` і
  `deploy`; `tests/live-ports.test.mjs` зелений. Жодної мережі (сторінка не ходить на `*.vercel.app`, бо адреси нема).
- [ ] Прогін: `python3 "$G" 900 3000 node --test --test-concurrency=1 tests/live/legacy-publish-cli.test.mjs` → PASS;
  `tests/live/vercel.test.mjs` і `tests/live/publish-not-task-link.test.mjs` — теж PASS.
- [ ] Commit — `test(4b-1): живий тест публікації ЛІГИ через модуль`.

---

### Task 7: документи й версія 0.9.0

- [ ] `CHANGELOG.md` `## [0.9.0] — <дата релізу>`: Added (вхід `auth: cli`, прибирання в `cli`, `ctx['find_tool']`,
  `ModuleError.full`, коди), Changed (ЛІГА публікує через модуль; ЛІГА прибирає старі публікації — рішення власника;
  `cleanup_warning`; `gated` у `task`), Removed (транспорт Vercel із `serve.py`), For module authors (необовʼязкові
  ключі результату `publish`: `deploy_url`, `verify`, `cleanup_warning`; `find_tool`; `full`; `gated`).
- [ ] `README.md`: вхід Vercel через CLI; дорожня карта 4b = 4b-1 ✅ / 4b-2 / 4b-3.
- [ ] `docs/design/spaces-and-modules.md`: розділ «Stage 4b-1 (0.9.0)» + дорожня карта.
- [ ] `docs/modules/authoring.md`: `ctx['find_tool']`, `task['gated']`, необовʼязкові ключі результату, `ModuleError.full`.
- [ ] `package.json` → `"version": "0.9.0"`.
- [ ] Спека: «Відомі обмеження» — звірити з тим, що вийшло (зокрема: випадкове імʼя в режимі `cli` без проби на зайнятість).
- [ ] Кожне твердження в документах — звірити з кодом. Commit — `docs(4b-1): 0.9.0`.

---

## Після всіх задач (контролер)

1. Фінальне ревʼю всієї гілки від коміту спеки (`0ffd2f8`).
2. Повні прогони: `npm test`; Python 3.13 і `/usr/bin/python3` 3.9.6; живі — по одному (`inspector-ds` 2/4 — стара червона з v0.7.0).
3. Дата в CHANGELOG → тег `v0.9.0` (анотований, від neodisa) → явний `git push origin <sha>:refs/heads/main` і тег → звірити віддалений sha.
4. Памʼять (`project-deai-opensource.md`), статус пайплайна, звіт власнику.
