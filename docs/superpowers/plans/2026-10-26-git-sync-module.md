# Етап 4a «Синхронізація з git як модуль (роль `vcs`)» — план реалізації

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** роль `vcs`, яку ядро кличе, і вбудований модуль `git-sync`. Будь-який простір синхронізує ітерації з будь-яким git-репо. Простір ЛІГА працює як раніше: неявний `'legacy'` виконується тим самим модулем. Реліз 0.8.0.

**Architecture:** транспорт переїжджає з `serve.py` у `app/modules/git-sync/server.py`: перевірки цілі, дзеркало, лок, `status`/`push`/`pull`/`check`/`validate`. Ядро лишає модель ітерацій і старі імена `gitlab_status`/`gitlab_sync`/`gitlab_pull`/`autosync` з тими самими сигнатурами (`gl` = ціль ролі). Помилки модуля ядро перетворює на `VcsError(OSError)` з `code`. Маршрути отримують нові адреси `/api/vcs-*`, старі лишаються псевдонімами. Клієнт показує зону синку за `hasVcs(space)`, а «Підключення» — секцію ролі.

**Tech Stack:** Python 3 stdlib (`unittest`, `subprocess`, `fcntl`), реальний git на локальних bare-репо, ванільний ES-модульний JS (`node:test`), Playwright Chromium для живого тесту.

**Спека:** `docs/superpowers/specs/2026-10-26-git-sync-module-design.md` (ревізія 2 + поправки нижче). Читати перед кожною задачею.

---

## Правила для кожної задачі (обовʼязкові)

**Git**

- Репо: `<repo>`, гілка `main`. Коміти лише так (особиста пошта в локальному git — НЕ використовувати):
  ```bash
  git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "…

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Рядок `Co-Authored-By` — рівно такий (Opus 5.5), навіть якщо твоя власна модель інша.
- В індекс додавати лише свої файли поіменно. **Ніколи** `git add -A` / `git add .`: у робочій теці лежить чужий файл `docs/superpowers/specs/2026-10-20-agents-in-canvas-design.md` — не чіпати й не комітити.

**Прогони й середовище**

- Кожен прогін тестів — через охоронця памʼяті: `python3 "$G" <секунд> <МБ> <команда…>`. Шлях `$G` дає контролер. Приклад: `python3 "$G" 900 3000 npm test`. Охоронця нема — сказати контролеру, а не запускати без нього.
- Не виставляти `DEAI_HOME` у шелі. Не чіпати:
  - порти 8765 і 4317;
  - справжні `~/.deai`, `~/deai-published`, `~/.gitconfig`, `tasks.json` дизайнера.
- Процеси зупиняти лише за PID. Ніколи `pkill`/`killall` за шаблоном.
- **Жодної мережі в тестах.** Git — лише на локальних bare-репо (абсолютний шлях або `file://`). Переходи за `ssh`/`https` — лише через підставний `subprocess.run`.

**Конвенції коду**

- Коментарі українською.
- Тексти інтерфейсу лише через `t()`, обидві мови (`UK` і `EN` у `app/i18n.js`). Кирилиці в літералах `app/**/*.js` поза словником бути не може (`tests/i18n-literals.test.mjs`).
- Дані в розмітку лише через `esc()`.
- Іконки лише відомі `ico()` (`app/icons.js`).
- CSS лише токенами.

**ЛІГА-golden і мутації**

- `tests/legacy-golden.test.mjs` мусить лишатись зеленим БЕЗ `UPDATE_GOLDEN=1`.
- Кожна нова перевірка доводиться мутацією:
  1. прибрати охорону одним рядком;
  2. потрібний тест червоніє;
  3. файл відновлено побайтно.

  Мутації Python — лише `python3 -B`, з охоронцем і тайм-аутом. Мутації по одній.

**Набори тестів**

- Повний набір юнітів: `npm test`. Він включає Python-набори; якщо ні — додатково `python3 -B -m unittest discover -s tests -p 'test_*.py'`.
- Живі тести — лише послідовно: `node --test --test-concurrency=1 tests/live/<файл>`.
- Номери рядків у плані — орієнтир («≈»): шукати за назвою функції.

## Поправки до спеки, знайдені під час планування

Вносяться в спеку тим самим комітом, що й план.

1. **Команда ssh.** Модуль складає `GIT_SSH_COMMAND` лише тоді, коли сам щось додає: `ssh_key` або повтор через `host_ip`.
   - Основа — наявна `GIT_SSH_COMMAND` оточення, інакше `ssh`. До неї `-o BatchMode=yes` і решта опцій.
   - `git config core.sshCommand` модуль НЕ читає. Без ключа й IP команду ssh людини (`core.sshCommand`, `~/.ssh/config`) git бере сам.
   - Причина: зайвий підпроцес перед клоном ламав би розтяжку `tests/test_integrations_off.py` (рівно один зовнішній запуск — `git clone`). До того ж перекрити налаштування людини означало б зламати її ssh.
2. **Гілка** перевіряється правилами `check-ref-format` для `refs/heads/<branch>`, реалізованими в Python: жодного git до перевірки.
3. **`ssh_key`** — налаштування типу `text`, не `path`. Каркас перетворює порожній `path` на теку простору. Модуль сам робить `expanduser` і вимагає абсолютного шляху до наявного файла.
4. **Результати `push`/`pull`** мають ті самі форми, що й `gitlab_sync`/`gitlab_pull` 0.7.0 з боку git: `ok`, `synced`, `changed`, `pushed`, `sha`, `catchup`, `error` (+ `code` при помилці).
   - Поля `remote` модуль не віддає — його додає ядро.
   - Відмова git — `ModuleError` з текстами 0.7.0: `clone failed: …`, `fetch failed: …`, `pull --ff-only failed: ….<підказка>`.
5. **Старі імена ядра** перетворюють `ModuleError` модуля на `VcsError(OSError)` з `code`. Маршрути, автосинк («офлайн — тихо») і бутстрап задачі й далі ловлять `OSError`.
6. **Модуль має ще дві функції поза `ROLE_FUNCTIONS`:**
   - `validate(ctx, target)` — нормалізована ціль або `vcs-bad-target`, без жодного git. Необовʼязкова в контракті ролі. Ядро кличе її, якщо вона є, на `task-new`: відмова → 400 з кодом `vcs-bad-target`.
   - `mirror_dir(ctx, target)` — тека дзеркала, для діагностики й тестів ядра.

   `task-new` з `vcs` у просторі без ролі → 400 `vcs-needs-role`.
7. **Простір ЛІГА: ключ і IP** несе ціль: `gitlab_cfg` — ключ/IP задачі, інакше спільні з кореня `tasks.json`, як у 0.7.0, — і для неявного, і для явного `git-sync`. `ctx` неявного `'legacy'` їх у `settings` не має.
8. **Порожній віддалений репо.** Після `git clone --branch`, що впав на «not found in upstream»:
   - клон без `--branch`;
   - якщо `HEAD` не народжений (репо порожній) → `git symbolic-ref HEAD refs/heads/<branch>`, і перший push створить гілку;
   - якщо репо не порожній (інша типова гілка) → відмова `clone failed`, як у 0.7.0.

   `fetch` із «couldn't find remote ref» — не помилка: гілки ще нема.
9. **Клієнт:**
   - **Стеля запиту.** Довга стеля запиту створення задачі — окрема функція `taskPost`, як `trustPost` у 3c. Тіло `formApi` дослівно стереже `tests/spaces-wiring.test.mjs`.
   - **Підпис зони.** Смуга бере `labelKey` за підписом: `gitlab` (типово), `vcsGitHub`, `vcsGit`. Поле `brand` (`'GitHub'`/`'Git'`) — лише для нетипового підпису. Тексти з «GitLab» отримують підпис останнім аргументом зі значенням за замовчуванням `'GitLab'`.
   - **Причина «збігається».** Для нетипового підпису — `vcsSyncWhy` замість `glSync`.
10. **`check` модуля:** межа — тайм-аут процесу 4 с. `ConnectTimeout=3` додається лише тоді, коли модуль складає команду ssh (п. 1).
11. **Автосинк.** Відмова постачальника (нечитабельний `space.json`, свій модуль «на папері») → тихе `reason: "no-gitlab"` з `code`. Зламаний модуль видно на «Підключенні», а Stop-хук не мусить кричати на кожній відповіді.
12. **Тексти даних (українською незалежно від мови інтерфейсу).** У просторі ЛІГА лишаються:
    - `design-canvas: sync …`;
    - «оновлення з GitLab»;
    - «продовження макета з GitLab»;
    - README «(design-canvas, задача …)».

    У звичайному просторі:
    - `deai: sync …`;
    - «оновлення з репозиторію»;
    - «продовження макета з репозиторію»;
    - README «(Deai Canvas, задача …)».

## Структура файлів

| файл | відповідальність |
|---|---|
| `app/modules/git-sync/server.py` (новий) | перевірки цілі (`validate`), slug дзеркала (`mirror_dir`), `_Git` (оточення, ssh, повтор через IP, класифікація помилок), лок між процесами, дзеркало (`_ensure`, `_checkout`, `_align_remote`), `status`/`push`/`pull`/`check`, `web_url`/`label_of` |
| `app/modules/git-sync/module.json` (новий, Task 3) | маніфест: `roles: ["vcs"]`, шість налаштувань |
| `app/deai_modules.py` | `vcs` у `ROLES_CALLED`/`LEGACY_ROLES`/`ROLE_FUNCTIONS`, коди `vcs-*` у `STATUS`, `cache_dir` у `_ctx`, `git-sync` у `KNOWN_OTHER_MODULES`, `vcs` у запасних словниках `capabilities` |
| `app/serve.py` | розділ «роль `vcs`»: `VcsError`, `vcs_provider`, `vcs_target`, `vcs_task`, `_vcs_call`, `vcs_mirror_dir`, `_commit_author`; старі імена через модуль; транспорт геть; маршрути `/api/vcs-*`, псевдоніми, автосинк, `task-new` з `vcs` |
| `bin/state.py` | гейт за роллю, підпис з `label` |
| `app/spaces-model.js` | `hasVcs`, `isLegacyVcs`, `TASK_VCS_POST_TIMEOUT_MS`, коди `vcs-*` у `TASK_ERR_KEYS`/`taskErrField` |
| `app/bar-model.js`, `app/shell-bar.js`, `app/shell-palette.js` | зона синку за `hasVcs`, `labelKey`/`brand`, причина `vcsSyncWhy` |
| `app/app.js` | `noVcs`, `refreshGitlab` на `/api/vcs-status`, дії на `/api/vcs-push`/`/api/vcs-pull`, `glsetup` → «Підключення» поза ЛІГОЮ, `afterModulesChange` → `refreshGitlab`, поле «Репозиторій», `taskPost`, мапер помилок дій |
| `app/connections-model.js` | роль `vcs` у `ROLE_ORDER`/`ROLE_KEYS`/`ROLE_ICONS`, `BUILTIN_TEXT['git-sync']`, `CHECK_KEYS` для `vcs-*`, `disableConsequences` |
| `app/space-dialogs.js`, `app/wizard.js` | поле «Репозиторій» у `taskFormHTML`; `deps.postTask` |
| `app/i18n.js` | нові ключі, тексти з підписом, 15 мертвих `gl*` геть |
| `tests/test_git_sync_module.py` (новий) | модуль: перевірки, slug, транспорт, лок, status/push/pull/check |
| `tests/test_vcs_core.py` (новий) | ядро: ціль, постачальник, `'legacy'`, звичайний простір, маршрути, `task-new` з `vcs` |
| `tests/test_gitlab_sync.py`, `tests/test_serve.py`, `tests/test_integrations_off.py`, `tests/test_state.py`, `tests/test_spaces_serve.py`, `tests/test_comments_role.py`, `tests/test_modules_api.py`, `tests/test_modules.py`, `tests/test_static_publish.py` | переїзд і нові ключі `capabilities` |
| `tests/*.test.mjs` (зміни) і `tests/vcs-client.test.mjs` (новий) | клієнт |
| `tests/live/git-sync.test.mjs` (новий), `tests/live/gitlab-pull-older.test.mjs` | живі |
| `docs/modules/authoring.md`, `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json` | документи й версія 0.8.0 |

---

### Task 1: модуль `git-sync` — перевірки цілі, дзеркало, транспорт, лок

Тести вантажать `server.py` напряму (`exec`, як ядро). Тут — перевірки, транспорт, лок, а також `check`, `module.json` і списки вбудованих модулів (див. «Поправки ревʼю» в кінці задачі: тека без маніфесту — це зламаний вбудований модуль для каталогу).

**Files:**
- Create: `app/modules/git-sync/server.py`
- Create: `tests/test_git_sync_module.py`

- [ ] **Step 1: Тести (червоні)** — `tests/test_git_sync_module.py`:

```python
"""`app/modules/git-sync` (роль `vcs`, етап 4a): транспорт синку макетів із git.

Модуль вантажиться так само, як його виконує ядро: `exec` у свіжий `types.ModuleType`, без `sys.modules`. Git — СПРАВЖНІЙ,
на локальних bare-репо в тимчасовій теці (абсолютний шлях і `file://`); мережа — лише через підставний `subprocess.run`.
Кожен тест — свій `HOME` у тимчасовій теці: глобальний git-конфіг людини не читається й не пишеться.
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(os.path.dirname(_HERE), 'app', 'modules', 'git-sync', 'server.py')


class FakeModuleError(Exception):
    def __init__(self, code, status=None, message=''):
        super().__init__(f'{code}: {message}')
        self.code, self.message = code, message


def load():
    m = types.ModuleType('deai_mod_git_sync_test')
    with open(SERVER, encoding='utf-8') as f:
        exec(compile(f.read(), SERVER, 'exec', dont_inherit=True), m.__dict__)
    return m


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='git-sync-mod-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = {'HOME': self.tmp, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@t',
               'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@t'}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('GIT_SSH_COMMAND', None)
        self.m = load()
        self.cache = os.path.join(self.tmp, 'cache')

    def ctx(self, **settings):
        return {'space': {'id': 's', 'path': self.tmp}, 'settings': settings, 'secrets': {},
                'ModuleError': FakeModuleError, 'cache_dir': self.cache}

    def bare(self, name='origin.git', seed=True):
        """Bare-репо; `seed` — з першим комітом у `main` (README) через «колегу»."""
        origin = os.path.join(self.tmp, name)
        os.makedirs(origin)
        sh(['git', 'init', '--bare', '-q', '-b', 'main', '.'], origin)
        if seed:
            self.peer = os.path.join(self.tmp, 'peer-' + name)
            sh(['git', 'clone', '-q', origin, self.peer], self.tmp)
            with open(os.path.join(self.peer, 'README.md'), 'w') as f:
                f.write('seed\n')
            sh(['git', 'add', '-A'], self.peer)
            sh(['git', 'commit', '-qm', 'seed'], self.peer)
            sh(['git', 'push', '-q', 'origin', 'HEAD:main'], self.peer)
        return origin
```

Тести перевірок цілі: клас `Validate(Base)`, кожен — `with self.assertRaises(FakeModuleError) as cm: self.m.validate(self.ctx(), t)` і `cm.exception.code == 'vcs-bad-target'`.

- Приймаються:
  - `/abs/origin.git`;
  - `file:///abs/origin.git`;
  - `ssh://git@h:2222/o/r.git`;
  - `https://user@h/o/r.git`;
  - `git@gitlab.internal.example:ORG/r.git`;
  - `h:o/r.git`.
- Відхиляються:
  - `''`, `' x'`, `'a b'`, `'x\n'`, `'-oProxyCommand=x'`;
  - `ext::sh`, `fd::3`, `http://h/r.git`, `ftp://h/r`;
  - `https://u:p@h/r.git` — і текст помилки не містить `p@`;
  - `ssh://-oProxy/r`, `file://host/x`, `relative/dir`.
- Гілка:
  - приймається `main`, `feature/x`;
  - відхиляються `-x`, `a..b`, `@{-1}`, `x.lock`, `.x`, `a//b`, `a/`, `a b`, `a~1`, `a:b`, `@`.
- `path` (після `strip('/')`):
  - приймається `mockup/t1`, а `/mockup/t1/` → `mockup/t1`;
  - відхиляються `.`, `a/./b`, `a/../b`, `''`, `-x`, `:/x`, `a*`, `a?`, `a[`, `a\\b`, `.git`, `a/.GIT/b`, `a\x00b`.
- `ssh_key`:
  - наявний файл під `~` (`~/k`, де `HOME` — `self.tmp`) приймається й розгортається;
  - тека, відносний шлях і неіснуючий файл — відмова.
- `host_ip`:
  - `10.0.0.7` і `::1` — так;
  - `host`, `10.0.0` — ні.
- Ціль перемагає налаштування: `settings={'ssh_key': <файл A>}`, `target.ssh_key=<файл B>` → B.
- Порожній рядок цілі — «не задано»: береться з налаштувань.

`MirrorDir(Base)`:

- `mirror_dir(ctx, {'repo': '/x/origin.git', 'path': 'p', 'branch': 'main'})` == `<cache>/mirrors/local/x-origin.git`.
- `ssh://git@h:2222/o/r.git` → `<cache>/mirrors/h-2222/o-r.git`.
- `git@gitlab.internal.example:ORG/r.git` → `<cache>/mirrors/gitlab.internal.example/ORG-r.git`.
- GitHub і GitLab з тим самим шляхом — різні теки.
- `ctx['mirror_flat']=True` → `<cache>/<slug за правилом 0.7.0>`. Для `git@h:ORG/r.git` це `ORG-r.git`, для `/x/origin.git` — `x-origin.git`.
- `file:///..` (шлях `/..`) — slug порожній чи `..` → `vcs-bad-target`. Тека ніколи не виходить за `cache_dir`: перевірити `os.path.commonpath`.

`Transport(Base)` — підставний `subprocess.run` модуля (`mock.patch.object(self.m.subprocess, 'run', fake)`), як `ResolverRetryByIp` у `tests/test_gitlab_sync.py`:

- **Повтор через IP:**
  - резолвер упав (`ssh: Could not resolve hostname h`) і є `host_ip` → рівно дві спроби;
  - друга несе `-c url.git@10.0.0.7:.insteadOf=git@h:`, а `GIT_SSH_COMMAND` другої спроби містить `HostKeyAlias=h`;
  - без `host_ip` — одна спроба;
  - інша відмова (`failed to push some refs`) — одна спроба;
  - IPv6 → `git@[::1]:`.
- **Оточення кожного виклику:** `GIT_TERMINAL_PROMPT=0`, `GIT_ALLOW_PROTOCOL=ssh:https:file`, `GIT_LITERAL_PATHSPECS=1`.
- **`GIT_SSH_COMMAND`:**
  - без ключа й IP — НЕ виставлено (значення людини з оточення лишається як є);
  - з ключем `<tmp>/my key` — `ssh -o BatchMode=yes -i '<tmp>/my key' -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new`;
  - з основою `GIT_SSH_COMMAND=false` в оточенні — починається з `false `.
- **Класифікація:**
  - `subprocess.TimeoutExpired` → `vcs-offline`;
  - stderr `Permission denied (publickey)` → `vcs-auth`;
  - `Host key verification failed` → `vcs-auth`;
  - `Could not resolve hostname` без IP → `vcs-offline`;
  - `index.lock': File exists` → `vcs-busy`;
  - решта → `vcs-error`, текст ≤300 і без `://u:p@`.

`Lock(Base)`:

- Поки один потік тримає `_Lock(ctx, md, wait=60)`, другий `_Lock(ctx, md, wait=0)` → `vcs-busy` одразу. Після виходу першого — бере.
- `wait=1` чекає й кидає `vcs-busy` не раніше ніж за ~1 с.
- **Між процесами:** дочірній `python3 -c` бере `fcntl.flock` на `<md>@lock` і спить. Наш `wait=0` → `vcs-busy`. Дочірній процес зупинити за PID (`proc.kill()`, `proc.wait()`).

`SourceShape(unittest.TestCase)` — за зразком `tests/test_static_publish.py` (`SourceShape`):

- `ALLOWED_IMPORTS = {'fcntl', 'ipaddress', 'msvcrt', 'os', 're', 'shlex', 'shutil', 'subprocess', 'sys', 'tempfile', 'time', 'urllib'}`;
- без `serve`/`deai_modules`/`spaces`/`importlib`;
- без `exec`/`eval`/`compile`/`__import__`;
- без `__file__`;
- немає `shell=True` (`ast`: жодного `keyword(arg='shell')`).

- [ ] **Step 2: Прогнати — червоні** (`python3 "$G" 300 2000 python3 -B -m unittest tests.test_git_sync_module -v` → `FileNotFoundError`/помилки імпорту).

- [ ] **Step 3: Реалізація** — `app/modules/git-sync/server.py` (повний текст нижче, без функцій ролі — вони в Task 2):

```python
"""Вбудований модуль `git-sync` (роль `vcs`, етап 4a): ітерації задачі ↔ будь-який git-репозиторій.

Модуль — ТРАНСПОРТ: дзеркало (локальний клон віддаленого репо), fetch, «відстає/попереду», заміна теки `<path>` вмістом,
який підготувало ядро, коміт, push без force, pull --ff-only, копіювання `<path>` назовні, адреса історії у вебі. Про
ітерації, авторство й `iterations.json` модуль не знає нічого — це ядро (`serve.py`, спека 4a, «Межа»).

Виконується ядром через `exec`: лише stdlib, без `serve`/`deai_modules`. Помилки — `ctx['ModuleError']` з кодами
`vcs-offline`/`vcs-auth`/`vcs-bad-target`/`vcs-busy`/`vcs-error` (вони в `STATUS` ядра); рукописний `ctx` без класу —
`RuntimeError` із кодом у тексті.

Ціль (`target`) дає ядро: `{repo, path, branch, task?, ssh_key?, host_ip?}`. `ssh_key`/`host_ip` цілі перемагають
налаштування модуля; порожній рядок — «не задано». Перевірка (`validate`) — до БУДЬ-ЯКОГО виклику git і без нього.

Дзеркало: `<cache_dir>/mirrors/<host>/<шлях>`; `ctx['mirror_flat']` (лише неявний постачальник простору ЛІГА) —
`<cache_dir>/<slug>` за правилом 0.7.0, щоб старі клони не перегортались. Одна операція на дзеркало: `flock` на
`<дзеркало>@lock` (між процесами — `bin/state.py` питає статус окремим процесом; модуль ще й перевантажується `exec`-ом).

Команду ssh модуль складає лише тоді, коли сам щось додає (`ssh_key`, повтор через `host_ip`): основа — `GIT_SSH_COMMAND`
оточення, інакше `ssh`. Інакше git бере ssh людини (`core.sshCommand`, `~/.ssh/config`) сам — модуль його не перекриває.
"""
import ipaddress
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit

try:
    import fcntl
except ImportError:                          # Windows
    fcntl = None
    import msvcrt

#: Тайм-аути git (секунди): як у 0.7.0 — звичайна операція, клон, перевірка на «Підключенні» (каркас чекає `check` 5 с).
GIT_TIMEOUT = 120
CLONE_TIMEOUT = 180
CHECK_GIT_TIMEOUT = 4
#: Скільки `push`/`pull` чекають на зайняте дзеркало; `status` не чекає (`vcs-busy`).
LOCK_WAIT = 60
LOCK_POLL = 0.2
MAX_MSG = 300
ALLOWED_SCHEMES = ('ssh://', 'https://', 'file://')
_RESOLVER_FAIL = 'could not resolve hostname'
_AUTH_MARKS = ('permission denied', 'authentication failed', 'could not read username',
               'could not read password', 'host key verification failed')
_OFFLINE_MARKS = ('could not resolve hostname', 'could not resolve host', 'connection timed out',
                  'operation timed out', 'network is unreachable', 'no route to host', 'connection refused')
_NO_BRANCH_MARKS = ('not found in upstream', "couldn't find remote ref", 'could not find remote ref')
_SCP = re.compile(r'(?:([^@/:\s]+)@)?([^/:\s]+):(.+)')
_PASSWORD = re.compile(r'(://[^/@:\s]*):[^/@\s]*@')
_BAD_BRANCH_CHARS = set(' ~^:?*[\\')
_BAD_PATH_CHARS = set('*?[\\')


def _err(ctx, code, message=''):
    text = _mask(str(message))[:MAX_MSG]
    cls = ctx.get('ModuleError') if isinstance(ctx, dict) else None
    return cls(code, message=text) if cls is not None else RuntimeError(f'{code}: {text}')


def _mask(text):
    """Пароль з адреси (`://user:pass@`) ніколи не йде в текст: такі адреси відхиляє `validate`, але stderr git — чужий текст."""
    return _PASSWORD.sub(r'\1:***@', text)


def _empty(v):
    return not isinstance(v, str) or not v.strip()


def _ctl(s):
    return any(ord(c) < 32 or c == '\x7f' for c in s)


def _slug(s):
    return re.sub(r'[^\w.-]+', '-', s).strip('-')


def _split_repo(repo):
    """(host, шлях) адреси. Локальний шлях і `file://` — хост `local`; `ssh://` з портом — `host:port`."""
    if repo.startswith(ALLOWED_SCHEMES):
        u = urlsplit(repo)
        if u.scheme == 'file':
            return 'local', u.path
        return (u.hostname or '') + (f':{u.port}' if u.port else ''), u.path
    m = _SCP.fullmatch(repo)
    if m and not os.path.isabs(repo):
        return m.group(2), m.group(3)
    return 'local', repo


def _repo_why(repo):
    if _empty(repo) or repo != repo.strip() or _ctl(repo) or any(c.isspace() for c in repo):
        return 'repo: empty or contains spaces or control characters'
    if repo.startswith('-'):
        return 'repo: must not start with "-"'
    if '::' in repo:
        return 'repo: transport helpers (ext::, fd::) are not allowed'
    if repo.startswith(ALLOWED_SCHEMES):
        try:
            u = urlsplit(repo)
            u.port
        except ValueError:
            return 'repo: bad address'
        if u.scheme == 'file':
            return None if u.netloc in ('', 'localhost') and u.path.startswith('/') else \
                'repo: file:// needs an absolute local path'
        if not u.hostname or u.hostname.startswith('-'):
            return 'repo: bad host'
        if u.password is not None:
            return 'repo: a password in the address is not accepted — keep credentials in git (credential helper)'
        return None
    if '://' in repo:
        return 'repo: only ssh://, https:// and file:// addresses'
    if os.path.isabs(repo):
        return None
    m = _SCP.fullmatch(repo)
    if m and not m.group(2).startswith('-') and not m.group(3).startswith('-'):
        return None
    return 'repo: use ssh://, https://, file://, user@host:path or an absolute local path'


def _branch_why(b):
    """Правила `git check-ref-format` для `refs/heads/<b>` — у Python, без git (`--branch` розгортає `@{-N}`)."""
    if _empty(b) or b.startswith('-') or b == '@' or _ctl(b) or any(c in _BAD_BRANCH_CHARS for c in b):
        return 'branch: not a valid branch name'
    if '..' in b or '@{' in b or '//' in b or b.startswith('/') or b.endswith(('/', '.')):
        return 'branch: not a valid branch name'
    if any(c.startswith('.') or c.endswith('.lock') for c in b.split('/')):
        return 'branch: not a valid branch name'
    return None


def _path_why(p, what='path'):
    """`p` — уже без `/` по краях. Сегменти `.`/`..`/порожні, магія pathspec, глоби й `.git` (будь-який регістр) — ні."""
    if not p or p.startswith(('-', ':')) or _ctl(p) or any(c in _BAD_PATH_CHARS for c in p):
        return f'{what}: not a valid folder in the repository'
    if any(seg in ('', '.', '..') or seg.lower() == '.git' for seg in p.split('/')):
        return f'{what}: not a valid folder in the repository'
    return None


def _pick(target, settings, key):
    v = target.get(key)
    if _empty(v):
        v = settings.get(key)
    return None if _empty(v) else v.strip()


def validate(ctx, target):
    """Нормалізована ціль `{repo, path, branch, ssh_key, host_ip}` або `vcs-bad-target`. Жодного виклику git."""
    if not isinstance(target, dict):
        raise _err(ctx, 'vcs-bad-target', 'target must be an object')
    settings = (ctx.get('settings') if isinstance(ctx, dict) else None) or {}
    repo = target.get('repo')
    branch = target.get('branch') if not _empty(target.get('branch')) else 'main'
    path = target.get('path').strip().strip('/') if isinstance(target.get('path'), str) else ''
    why = _repo_why(repo) or _branch_why(branch) or _path_why(path)
    key, ip = _pick(target, settings, 'ssh_key'), _pick(target, settings, 'host_ip')
    if not why and key is not None:
        key = os.path.expanduser(key)
        if not (os.path.isabs(key) and os.path.isfile(key)):
            why = 'ssh_key: not an existing file (use an absolute path or ~)'
    if not why and ip is not None:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            why = 'host_ip: not an IP address'
    if why:
        raise _err(ctx, 'vcs-bad-target', why)
    return {'repo': repo, 'path': path, 'branch': branch.strip(), 'ssh_key': key, 'host_ip': ip}


def _mirror(ctx, t):
    base = ctx.get('cache_dir') if isinstance(ctx, dict) else None
    if _empty(base):
        raise _err(ctx, 'vcs-error', 'no cache_dir in ctx')
    if ctx.get('mirror_flat'):
        parts = [_slug(t['repo'].split(':')[-1])]             # правило `_mirror_dir` 0.7.0: старі клони ЛІГИ
    else:
        host, rpath = _split_repo(t['repo'])
        parts = ['mirrors', _slug(host), _slug(rpath)]
    if any(p in ('', '.', '..') for p in parts):
        raise _err(ctx, 'vcs-bad-target', 'repo: cannot name a mirror folder for this address')
    return os.path.join(base, *parts)


def mirror_dir(ctx, target):
    """Тека дзеркала цілі (діагностика й тести ядра). Нічого не створює."""
    return _mirror(ctx, validate(ctx, target))


class _Git:
    """git для однієї цілі: оточення, ssh, ОДИН повтор через `host_ip` на збої резолвера, тайм-аут → `vcs-offline`."""

    def __init__(self, ctx, t, connect_timeout=None):
        self.ctx, self.t, self.connect_timeout = ctx, t, connect_timeout

    def _ssh(self, alias):
        key = self.t.get('ssh_key')
        if not key and not alias:
            return None
        parts = [os.environ.get('GIT_SSH_COMMAND') or 'ssh', '-o BatchMode=yes']
        if self.connect_timeout:
            parts.append(f'-o ConnectTimeout={int(self.connect_timeout)}')
        if key:
            parts += [f'-i {shlex.quote(key)}', '-o IdentitiesOnly=yes', '-o StrictHostKeyChecking=accept-new']
        if alias:
            # Ключ хоста має збігтися з тим, що вже в known_hosts — інакше повтор упреться в перевірку ключа.
            parts.append(f'-o HostKeyAlias={alias}')
        return ' '.join(parts)

    def _env(self, alias=None, literal=True):
        env = dict(os.environ)
        env['GIT_TERMINAL_PROMPT'] = '0'
        env['GIT_ALLOW_PROTOCOL'] = 'ssh:https:file'
        if literal:
            env['GIT_LITERAL_PATHSPECS'] = '1'
        else:
            env.pop('GIT_LITERAL_PATHSPECS', None)
        ssh = self._ssh(alias)
        if ssh:
            env['GIT_SSH_COMMAND'] = ssh
        return env

    def _once(self, args, cwd, timeout, ip, literal):
        pre, alias = [], None
        if ip:
            m = _SCP.fullmatch(self.t['repo'])
            user = f'{m.group(1)}@' if m.group(1) else ''
            addr = f'[{ip}]' if ':' in ip else ip
            # `url.…insteadOf`, а не правка аргументу: у fetch/push адреса — `origin`, не в рядку команди.
            pre = ['-c', f'url.{user}{addr}:.insteadOf={user}{m.group(2)}:']
            alias = m.group(2)
        try:
            return subprocess.run(['git', *pre, *args], cwd=cwd, env=self._env(alias, literal),
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise _err(self.ctx, 'vcs-offline', f'git {args[0]}: no answer in {timeout} s') from None

    def run(self, args, cwd, timeout=GIT_TIMEOUT, literal=True):
        r = self._once(args, cwd, timeout, None, literal)
        ip = self.t.get('host_ip')
        if (r.returncode != 0 and ip and _RESOLVER_FAIL in (r.stderr or '').lower()
                and _SCP.fullmatch(self.t['repo']) and not self.t['repo'].startswith(ALLOWED_SCHEMES)
                and not os.path.isabs(self.t['repo'])):
            return self._once(args, cwd, timeout, ip, literal)
        return r

    def code_of(self, r):
        low = (r.stderr or r.stdout or '').lower()
        if any(m in low for m in _AUTH_MARKS):
            return 'vcs-auth'
        if any(m in low for m in _OFFLINE_MARKS):
            return 'vcs-offline'
        if 'index.lock' in low:
            return 'vcs-busy'
        return 'vcs-error'

    def fail(self, what, r, tail='', keep=300):
        err = r.stderr or r.stdout or ''
        return _err(self.ctx, self.code_of(r), f'{what} failed: {err[-keep:]}{tail}')

    def must(self, args, cwd, what, timeout=GIT_TIMEOUT, keep=300):
        r = self.run(args, cwd, timeout)
        if r.returncode != 0:
            raise self.fail(what, r, keep=keep)
        return r


def _try_lock(fh):
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)


def _unlock(fh):
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    else:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


class _Lock:
    """Одна операція на дзеркало, між процесами й потоками: `flock` на `<дзеркало>@lock` (окремий `open` — окремий опис
    файла, тож потоки одного процесу теж виключають один одного). `wait=0` — одна спроба."""

    def __init__(self, ctx, md, wait):
        self.ctx, self.path, self.wait, self.fh = ctx, md + '@lock', wait, None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        self.fh = open(self.path, 'a+')
        deadline = time.monotonic() + self.wait
        while True:
            try:
                _try_lock(self.fh)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    self.fh.close()
                    raise _err(self.ctx, 'vcs-busy', 'the mirror is busy with another operation') from None
                time.sleep(LOCK_POLL)

    def __exit__(self, *exc):
        try:
            _unlock(self.fh)
        finally:
            self.fh.close()
        return False
```

Функції `_ensure`, `_checkout`, `_align_remote`, `_count`, `_on_remote`, `_behind_top`, `web_url`, `label_of` і функції ролі — Task 2.

- [ ] **Step 4: Прогнати — зелені.** Зелені всі класи цієї задачі, а `SourceShape` — на функціях, що вже є. Тест «функції ролі є» додає Task 2.

- [ ] **Step 5: Мутації** (по одній, `python3 -B`):
  1. прибрати `'::' in repo` → червоніє тест `ext::`/`fd::`;
  2. прибрати `seg.lower() == '.git'` → `.GIT`;
  3. прибрати `'..' in b` → `a..b`;
  4. прибрати `env['GIT_LITERAL_PATHSPECS'] = '1'` → тест оточення;
  5. прибрати перевірку `_RESOLVER_FAIL` → «інша відмова — одна спроба»;
  6. `deadline = time.monotonic() + self.wait` → `+ 0` → тест `wait=1`;
  7. прибрати `if any(p in ('', '.', '..') …)` у `_mirror` → тест `file:///..`.

  Кожну — назад побайтно (`git diff --stat` порожній).

- [ ] **Step 6: Коміт**
```bash
git add app/modules/git-sync/server.py tests/test_git_sync_module.py
git -c user.name=neodisa -c user.email=neodisa@users.noreply.github.com commit -m "feat(4a): git-sync — перевірки цілі, дзеркало, транспорт і лок між процесами

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Поправки ревʼю плану (26.10.2026, обовʼязкові; перекривають текст задачі вище):**

1. **Безпека: хост і користувач scp-адреси.** При повторі через `host_ip` git виконує `GIT_SSH_COMMAND` через shell.
   - `_Git._ssh`: `-o HostKeyAlias={shlex.quote(alias)}`.
   - У scp-гілці `_repo_why`: хост — `re.fullmatch(r'[A-Za-z0-9._-]+', m.group(2))`, користувач — `m.group(1) is None or re.fullmatch(r'[A-Za-z0-9._-]+', m.group(1))`.
   - У «відхиляються» — `h;id>x:o/r.git` і `u$(x)@h:o/r.git`. Мутація: прибрати перевірку хоста → тест червоніє.
2. **`check`, `module.json` і списки вбудованих — тут, а не в Task 2/3.** Підтека `app/modules/git-sync` без маніфесту — для каталогу зламаний вбудований модуль (`bad-manifest`), і повний набір червоніє.
   - `check(ctx)` — код дослівно з Task 2 Step 3, і тести `Check` з Task 2 Step 1.
   - `module.json` — дослівно з Task 3 Step 1. Поки `vcs` у `ROLES_RESERVED`, каркас вимагає лише `check`.
   - `BUILTIN_IDS` (`tests/test_comments_role.py:52`, `tests/test_modules_api.py:68`) з `git-sync`.
   - `KNOWN_OTHER_MODULES` з `git-sync`.
   - Тест: `deai_modules.catalog()['git-sync'].status == 'ok'`.
   - Після задачі ПОВНИЙ набір зелений.
3. **`SourceShape`** у Task 1: `{'check', 'validate', 'mirror_dir'} <= funcs`.

---

### Task 2: модуль `git-sync` — `status`/`push`/`pull`/`check` на справжньому git

Переносимо git-частину `ensure_mirror`, `_align_mirror_remote`, `_rev_count`, `_on_remote`, `_behind_top`, `gitlab_status`, `gitlab_sync` (після перевірки «чужа» і до `_record_sync`), `gitlab_pull` (до копіювання в ітерацію) і `_authored_at_origin` з `app/serve.py` (≈590–1060, ≈1220–1250, ≈1383–1410). У `serve.py` поки НІЧОГО не змінюється — ядро переходить на модуль у Task 4.

**Files:**
- Modify: `app/modules/git-sync/server.py`
- Modify: `tests/test_git_sync_module.py`

- [ ] **Step 1: Тести (червоні)** — нові класи в `tests/test_git_sync_module.py`, усе на справжньому git (`Base.bare()`).

**`Status`:**
- **Перший статус клонує:**
  - тека `mirror_dir(...)` має `.git`;
  - результат має рівно ключі `{'behind', 'behind_path', 'unpushed', 'on_remote', 'web', 'label'}`;
  - для локального репо `web is None`, `label == 'Git'`;
  - `on_remote is False`, поки `<path>` нема в репо.
- **Коміт колеги:**
  - мимо `<path>` → `behind == 1`, `behind_path == 0`;
  - у `<path>` → `behind_path == 1`.
- **Перерваний клон:** підставний `run` для `clone` кидає `TimeoutExpired`. Після `vcs-offline` у теці `mirrors/local/` нема ні дзеркала, ні `.clone-*`.
- **`origin` дзеркала:** звіряється з ціллю — та сама тека, інша адреса (друге bare-репо з тим самим slug через `mirror_flat`) → `git config --get remote.origin.url` дзеркала = нова адреса.
- **Офлайн:** origin перейменовано → `vcs-error` або `vcs-offline` (`fetch failed` у тексті), без «тихого нуля».
- **Порожній bare-репо (`seed=False`):**
  - статус не падає;
  - `on_remote is None`, `behind == 0`;
  - дзеркало має `HEAD` → `refs/heads/main`.

**`Push`:** `src` — тимчасова тека з `index.html` і `.canvas-state.json`; `meta = {'message': 'deai: sync mockup/t1 (Т) · it1\n\nтіло', 'author': {'name': 'Анна', 'email': 'a@x'}}`.
- **Перший push:**
  - `{'ok': True, 'synced': True, 'changed': True, 'pushed': True, 'sha': <непорожній>, 'error': None}`;
  - у bare-репо `git log -1 --format=%an%n%s main` = `Анна` і перший рядок повідомлення;
  - `.canvas-state.json` лежить у `<path>`.
- **Повтор без змін:** `{'ok': True, 'synced': True, 'changed': False, 'pushed': False}`.
- **Видалений у `src` файл** зникає з репо (заміна теки, а не накладання).
- **Колега в `<path>`:** `{'ok': False, 'synced': False, 'blocked': 'behind', 'behind': 1, 'behind_path': 1, 'behind_top': {'author': <колега>, 'date': …, 'subject': …}}`; репо не змінилось.
- **Колега мимо `<path>`:** `merge --ff-only`, потім push проходить (`pushed: True`).
- **Розходження:**
  - локальний коміт у дзеркалі поверх origin + коміт колеги мимо `<path>` → `blocked: 'diverged'` з `ahead >= 1` і `error`;
  - нічого не запушено.
- **Наздоганяння:** незапушений коміт у дзеркалі й `src` без змін → `{'changed': False, 'catchup': True, 'pushed': True}`.
- **Порожній bare-репо:** перший push створює `main`, `git ls-remote` бачить гілку.
- **Відмова push:** підставний `run` лише для `push` повертає `returncode=1`, stderr `Permission denied` → `{'ok': False, 'synced': False, 'pushed': False, 'code': 'vcs-auth', 'error': …}`.
- **Зламаний `src`:** `src` не тека → `vcs-error`.

**`Pull`:** `dst` — порожня тека.
- **Колега поклав `<path>/index.html`:**
  - `{'found': True, 'last_commit': {'author': <колега>, 'time': int}}`;
  - `dst/index.html` є.
- **`<path>` нема** → `{'found': False, 'last_commit': None}`, `dst` порожня.
- **Коміт лише кадрів** (`<path>/shots/a.png`) після коміту макета: `author` — автор кадрів, `time` — час коміту МАКЕТА (дві множини, `opts={'ignore': ['shots']}`). Без `opts` — час кадрів.
- **Розходження** → `ModuleError` з `pull --ff-only failed` і `локальний(х) коміт(ів)` у тексті.
- **Зламані аргументи:**
  - `opts={'ignore': ['../x']}` → `vcs-bad-target`;
  - `dst` непорожня → `vcs-error`.

**`Check`:**
- без `repo` → `{'ok': True, 'detail': …}`, жодного `subprocess.run` (підставний рахує);
- локальний bare з `main` → `ok: True`, деталь «found»;
- порожній bare → `ok: True`, деталь «not on the remote yet»;
- погана адреса → `{'ok': False, 'error': 'vcs-bad-target'}` без git;
- підставний `run` кидає `TimeoutExpired` → `{'ok': False, 'error': 'vcs-offline'}`;
- тайм-аут, який модуль передав у `run`, — 4.

**`WebLabel`:**
- `git@github.com:o/r.git` → `('GitHub', 'https://github.com/o/r/commits/main/mockup/t1')`;
- `ssh://git@gitlab.example.test:2222/g/r.git` → `('GitLab', 'https://gitlab.example.test/g/r/-/commits/main/mockup/t1')`;
- `https://git.example.test/o/r` → `('Git', None)`;
- `file:///x/r.git` → `('Git', None)`;
- пробіл у `path` — у `web` закодований `%20`.

**`SourceShape`:** `{'check', 'status', 'push', 'pull', 'validate', 'mirror_dir'} <= funcs`.

- [ ] **Step 2: Прогнати — червоні.**

- [ ] **Step 3: Реалізація** — дописати в `server.py`:

```python
def _no_branch(r):
    low = (r.stderr or r.stdout or '').lower()
    return any(m in low for m in _NO_BRANCH_MARKS)


def _ensure(g, md, fetch=True):
    """Дзеркало цілі: клон за потреби (у тимчасову теку поруч + `rename`: перерваний клон не лишає напівдзеркала),
    `origin` = адреса цілі, свіжий fetch. ⛔ Відмову fetch не ковтаємо: без свіжого origin «відстає» бреше нулем."""
    if not os.path.isdir(os.path.join(md, '.git')):
        if os.path.exists(md):
            raise _err(g.ctx, 'vcs-error', f'mirror folder exists but is not a git clone: {os.path.basename(md)}')
        parent = os.path.dirname(md)
        os.makedirs(parent, mode=0o700, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix='.clone-', dir=parent)
        try:
            r = g.run(['clone', '--quiet', '--branch', g.t['branch'], '--', g.t['repo'], tmp], parent, CLONE_TIMEOUT)
            if r.returncode != 0 and _no_branch(r):
                shutil.rmtree(tmp, ignore_errors=True)
                os.makedirs(tmp)
                r2 = g.run(['clone', '--quiet', '--', g.t['repo'], tmp], parent, CLONE_TIMEOUT)
                if r2.returncode == 0 and g.run(['rev-parse', '--verify', '--quiet', 'HEAD'], tmp).returncode != 0:
                    # порожній репо: HEAD → ненароджена `<branch>`, перший push її створить
                    g.must(['symbolic-ref', 'HEAD', f'refs/heads/{g.t["branch"]}'], tmp, 'symbolic-ref')
                    r = r2
            if r.returncode != 0:
                raise g.fail('clone', r)
            os.rename(tmp, md)
        finally:
            if os.path.isdir(tmp):
                shutil.rmtree(tmp, ignore_errors=True)
        return
    _align_remote(g, md)
    if fetch:
        r = g.run(['fetch', '--quiet', 'origin', g.t['branch']], md)
        if r.returncode != 0 and not _no_branch(r):
            raise g.fail('fetch', r)


def _align_remote(g, md):
    """`origin` дзеркала = адреса цілі (fb-29092026-d64d35: дзеркало, склоноване з обхідною IP-адресою, тримало її в
    origin тижнями). ЗАПИСАНЕ значення, а не `remote get-url`: той розгортає `url.*.insteadOf`."""
    r = g.run(['config', '--get', 'remote.origin.url'], md)
    have = (r.stdout or '').strip() if r.returncode == 0 else ''
    if have == g.t['repo']:
        return
    g.must(['remote', 'set-url', 'origin', g.t['repo']], md, 'remote set-url')
    print(_mask(f'дзеркало {os.path.basename(md)}: origin {have or "—"} → {g.t["repo"]} (за ціллю синку)'),
          file=sys.stderr)


def _checkout(g, md):
    b = g.t['branch']
    if g.run(['rev-parse', '--verify', '--quiet', f'refs/heads/{b}'], md).returncode == 0:
        g.must(['checkout', '-q', b, '--'], md, f'checkout {b}', keep=200)
    elif g.run(['rev-parse', '--verify', '--quiet', f'refs/remotes/origin/{b}'], md).returncode == 0:
        g.must(['checkout', '-q', '-b', b, '--track', f'origin/{b}'], md, f'checkout {b}', keep=200)
    else:
        g.must(['symbolic-ref', 'HEAD', f'refs/heads/{b}'], md, 'symbolic-ref')


def _count(g, md, rng, path=None):
    r = g.run(['rev-list', '--count', rng] + (['--', path] if path else []), md)
    out = (r.stdout or '').strip()
    return int(out) if r.returncode == 0 and out.isdigit() else 0


def _on_remote(g, md):
    """Три стани: True / False / None («гілки на origin нема — питання без відповіді»). Не зливати None у False."""
    b, p = g.t['branch'], g.t['path']
    if g.run(['cat-file', '-e', f'origin/{b}:{p}'], md).returncode == 0:
        return True
    if g.run(['rev-parse', '--verify', '--quiet', f'origin/{b}'], md).returncode != 0:
        return None
    return False


def _behind_top(g, md):
    r = g.run(['log', '-1', '--format=%an%x1f%ad%x1f%s', '--date=format:%d.%m.%Y %H:%M', f'origin/{g.t["branch"]}'], md)
    if r.returncode != 0 or '\x1f' not in r.stdout:
        return {}
    author, date, subject = (r.stdout.strip().split('\x1f') + ['', '', ''])[:3]
    return {'author': author, 'date': date, 'subject': subject[:120]}


def _web_host(t):
    host, rpath = _split_repo(t['repo'])
    rpath = rpath.strip('/')
    return host.split(':')[0].lower(), rpath[:-4] if rpath.endswith('.git') else rpath


def label_of(t):
    host, _ = _web_host(t)
    return 'GitHub' if host == 'github.com' else 'GitLab' if 'gitlab' in host else 'Git'


def web_url(t):
    """Історія комітів `<path>` у вебі: GitHub і GitLab (хост містить `gitlab`); інше — `None`."""
    host, proj = _web_host(t)
    if host in ('', 'local') or not proj:
        return None
    tail = quote(f'{t["branch"]}/{t["path"]}', safe='/')
    proj = quote(proj, safe='/')
    if host == 'github.com':
        return f'https://github.com/{proj}/commits/{tail}'
    if 'gitlab' in host:
        return f'https://{host}/{proj}/-/commits/{tail}'
    return None


def status(ctx, target):
    t = validate(ctx, target)
    g, md = _Git(ctx, t), _mirror(ctx, t)
    with _Lock(ctx, md, wait=0):
        _ensure(g, md, fetch=True)
        b = t['branch']
        return {'behind': _count(g, md, f'{b}..origin/{b}'),
                'behind_path': _count(g, md, f'{b}..origin/{b}', t['path']),
                'unpushed': _count(g, md, f'origin/{b}..{b}'),
                'on_remote': _on_remote(g, md), 'web': web_url(t), 'label': label_of(t)}


def _pushed(g, r, changed, catchup=False):
    ok = r.returncode == 0
    out = {'ok': ok, 'synced': ok, 'changed': changed, 'pushed': ok,
           'error': None if ok else _mask((r.stderr or r.stdout or '')[-300:])}
    if catchup:
        out['catchup'] = True
    if not ok:
        out['code'] = g.code_of(r)
    return out


def push(ctx, target, src, meta):
    """Вміст `src` стає `<path>` (заміна теки, з dot-файлами) → коміт → push без force. Форми результату — як
    `gitlab_sync` 0.7.0 без `remote` (його додає ядро). «Відстає» по ВСЬОМУ репо (інакше non-fast-forward назавжди);
    блокує лише тека задачі (`behind_path`), решту наздоганяє `merge --ff-only`."""
    t = validate(ctx, target)
    if not isinstance(src, str) or not os.path.isdir(src):
        raise _err(ctx, 'vcs-error', 'push: src is not a folder')
    meta = meta if isinstance(meta, dict) else {}
    g, md = _Git(ctx, t), _mirror(ctx, t)
    b, p = t['branch'], t['path']
    with _Lock(ctx, md, wait=LOCK_WAIT):
        _ensure(g, md, fetch=True)
        _checkout(g, md)
        behind = _count(g, md, f'{b}..origin/{b}')
        if behind > 0:
            behind_path = _count(g, md, f'{b}..origin/{b}', p)
            if behind_path > 0:
                return {'ok': False, 'synced': False, 'blocked': 'behind', 'behind': behind,
                        'behind_path': behind_path, 'behind_top': _behind_top(g, md)}
            ff = g.run(['merge', '--ff-only', '--quiet', f'origin/{b}'], md)
            if ff.returncode != 0:
                return {'ok': False, 'synced': False, 'blocked': 'diverged', 'behind': behind,
                        'ahead': _count(g, md, f'origin/{b}..{b}'), 'behind_top': _behind_top(g, md),
                        'error': _mask((ff.stderr or ff.stdout or '')[-200:])}
        dst = os.path.join(md, p)
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst, symlinks=True)
        g.run(['add', '-A', '--', p], md)
        st = g.run(['status', '--porcelain', '--', p], md)
        if not (st.stdout or '').strip():
            # Не змінився — ще НЕ «лежить на origin»: попередній коміт міг не доїхати (bgSanctions, 12 днів «✓»).
            if _count(g, md, f'origin/{b}..{b}') == 0 and g.run(
                    ['rev-parse', '--verify', '--quiet', f'origin/{b}'], md).returncode == 0:
                return {'ok': True, 'synced': True, 'changed': False, 'pushed': False}
            return _pushed(g, g.run(['push', '--quiet', 'origin', b], md), changed=False, catchup=True)
        author = meta.get('author') if isinstance(meta.get('author'), dict) else {}
        ident = ['-c', f'user.name={author.get("name") or "Deai Canvas"}',
                 '-c', f'user.email={author.get("email") or "deai@localhost"}']
        c = g.run(ident + ['commit', '-q', '-m', str(meta.get('message') or 'deai: sync')], md)
        if c.returncode != 0:
            raise g.fail('commit', c)
        out = _pushed(g, g.run(['push', '--quiet', 'origin', b], md), changed=True)
        out['sha'] = (g.run(['rev-parse', '--short', 'HEAD'], md).stdout or '').strip()
        return out


def _ignore_list(ctx, opts):
    ign = (opts or {}).get('ignore') if isinstance(opts, dict) else None
    out = []
    for x in ign or []:
        x = x.strip('/') if isinstance(x, str) else ''
        why = _path_why(x, 'ignore')
        if why:
            raise _err(ctx, 'vcs-bad-target', why)
        out.append(x)
    return out


def pull(ctx, target, dst, opts=None):
    """Свіжий `<path>` з origin → порожня `dst`. `last_commit`: `author` — останній коміт `<path>`; `time` — останній
    коміт `<path>` ПОЗА підтеками `opts.ignore` (кадри перезнімаються самі — це не робота), `None`, якщо такого нема."""
    t = validate(ctx, target)
    ignore = _ignore_list(ctx, opts)
    if not isinstance(dst, str) or not os.path.isdir(dst) or os.listdir(dst):
        raise _err(ctx, 'vcs-error', 'pull: dst must be an empty folder')
    g, md = _Git(ctx, t), _mirror(ctx, t)
    b, p = t['branch'], t['path']
    with _Lock(ctx, md, wait=LOCK_WAIT):
        _ensure(g, md, fetch=True)
        _checkout(g, md)
        # ⛔ Не ковтати: при розходженні --ff-only падає, і в ітерацію поїхало б ЗАСТАРІЛЕ дзеркало з чужим підписом.
        pl = g.run(['pull', '--ff-only', '--quiet', 'origin', b], md)
        if pl.returncode != 0:
            ahead = _count(g, md, f'origin/{b}..{b}')
            hint = (f' Дзеркало має {ahead} локальний(х) коміт(ів) поверх origin — розходження треба розвести вручну.'
                    if ahead else '')
            raise g.fail('pull --ff-only', pl, tail='.' + hint, keep=200)
        src = os.path.join(md, p)
        if not os.path.isdir(src):
            return {'found': False, 'last_commit': None}
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
        a = g.run(['log', '-1', '--format=%an', '--', p], md)
        excl = [f':(exclude){p}/{x}' for x in ignore]
        # Магія `:(exclude)` — лише тут і лише з нашим префіксом: `p`/`ignore` перевірені (`_path_why`).
        tm = g.run(['log', '-1', '--format=%ct', '--', p, *excl], md, literal=False)
        try:
            when = int((tm.stdout or '').strip())
        except ValueError:
            when = None
        return {'found': True,
                'last_commit': {'author': (a.stdout or '').strip() if a.returncode == 0 else '', 'time': when}}


def check(ctx):
    """Для «Підключення»: є типовий `repo` → `ls-remote` з межею `CHECK_GIT_TIMEOUT` (каркас чекає 5 с). Звичайні відмови —
    `{"ok": false, "error": <код>, "detail": …}`, не виняток."""
    s = (ctx.get('settings') if isinstance(ctx, dict) else None) or {}
    if _empty(s.get('repo')):
        return {'ok': True, 'detail': 'the repository is set per task'}
    try:
        t = validate(ctx, {'repo': s['repo'].strip(), 'branch': s.get('branch'),
                           'path': str(s.get('path') or 'mockup/{task}').replace('{task}', 'task')})
    except Exception as e:  # noqa: BLE001 — клас помилки приходить з ctx
        return {'ok': False, 'error': 'vcs-bad-target', 'detail': getattr(e, 'message', None) or str(e)}
    g = _Git(ctx, t, connect_timeout=3)
    try:
        r = g.run(['ls-remote', '--heads', '--', t['repo'], t['branch']], tempfile.gettempdir(), CHECK_GIT_TIMEOUT)
    except Exception as e:  # noqa: BLE001 — `vcs-offline` від тайм-ауту
        return {'ok': False, 'error': getattr(e, 'code', 'vcs-offline'), 'detail': getattr(e, 'message', None) or str(e)}
    if r.returncode != 0:
        e = g.fail('ls-remote', r)
        return {'ok': False, 'error': getattr(e, 'code', 'vcs-error'), 'detail': getattr(e, 'message', None) or str(e)}
    if (r.stdout or '').strip():
        return {'ok': True, 'detail': f'branch {t["branch"]} found'}
    return {'ok': True, 'detail': f'branch {t["branch"]} is not on the remote yet — the first send creates it'}
```

Примітка до «без змін» у `push`. На порожньому репо, де гілки на origin ще нема, `origin/<b>..<b>` — помилка (0), тож перевіряємо, чи `origin/<b>` взагалі є. Без цього перший push порожнього `src` після невдалого брехав би «synced».

- [ ] **Step 4: Прогнати — зелені.** Плюс старий набір `tests/test_gitlab_sync.py` теж зелений: `serve.py` не чіпали.

- [ ] **Step 5: Мутації** (по одній):
  1. прибрати `excl` (`time` з кадрами) → тест «коміт лише кадрів»;
  2. `_count(…, p)` → без `p` у `behind_path` → «колега мимо `<path>`»;
  3. прибрати перевірку `pl.returncode` → «розходження»;
  4. прибрати `os.rename` через тимчасову теку (клонувати прямо в `md`) → «перерваний клон»;
  5. прибрати `_align_remote` з `_ensure` → тест `origin`;
  6. прибрати гілку `symbolic-ref` у `_ensure` → «порожній bare»;
  7. у `check` поставити `GIT_TIMEOUT` замість `CHECK_GIT_TIMEOUT` → тест тайм-ауту 4.

- [ ] **Step 6: Коміт** — `feat(4a): git-sync — status, push, pull і check на справжньому git`.

**Поправки ревʼю плану (26.10.2026, обовʼязкові; перекривають текст задачі вище):**

1. **`check` уже зроблено в Task 1** — тут лише `status`/`push`/`pull`/`web_url`/`label_of` та їхні тести. `SourceShape` — повний набір `{'check', 'status', 'push', 'pull', 'validate', 'mirror_dir'}`.
2. **Безпека: симлінки в чужому репо.** `<path>` чи проміжна тека може бути симлінком (`mockup -> /`): `isdir`/`copytree`/`rmtree` пішли б за ним поза дзеркало. Додати:
   ```python
   def _inside(ctx, md, p):
       """`<md>/<p>`, якщо після розгортання симлінків він лишається в дзеркалі; інакше `vcs-error`."""
       root = os.path.realpath(md)
       full = os.path.realpath(os.path.join(md, p))
       if full != root and not full.startswith(root + os.sep):
           raise _err(ctx, 'vcs-error', 'path leaves the mirror (symlink in the repository)')
       return os.path.join(md, p)
   ```
   - `push`: `dst = _inside(ctx, md, p)` перед `isdir`/`rmtree`.
   - `pull`: `src = _inside(ctx, md, p)` перед `isdir`; копіювати з `ignore=lambda d, names: [n for n in names if os.path.islink(os.path.join(d, n))]` (симлінки з чужого репо не везуться).
   - Тести:
     - bare, де `mockup` — симлінк на теку поза дзеркалом → і `push`, і `pull` дають `vcs-error`, поза дзеркалом нічого не змінено й не скопійовано;
     - симлінк-файл усередині `<path>` у `pull` не потрапляє в `dst`.
3. **`pull` на порожньому віддаленому репо.** Одразу після `_checkout(g, md)`:
   ```python
   if g.run(['rev-parse', '--verify', '--quiet', f'refs/remotes/origin/{b}'], md).returncode != 0:
       return {'found': False, 'last_commit': None}
   ```
   Тест: порожній bare → `pull` → `found False`.

---

### Task 3: каркас — роль `vcs`, `module.json`, коди, `cache_dir`

**Files:**
- Create: `app/modules/git-sync/module.json`
- Modify: `app/deai_modules.py` (константи ≈118–141, `capabilities` ≈1761–1812, `_ctx` ≈1516, `KNOWN_OTHER_MODULES` ≈1598, докстрінг модуля)
- Modify: `tests/test_modules.py`, `tests/test_comments_role.py`, `tests/test_modules_api.py`, `tests/test_spaces_serve.py`, `tests/test_static_publish.py` (та будь-які інші, що порівнюють `capabilities` точним словником), `tests/test_git_sync_module.py`

- [ ] **Step 1: `module.json`:**

```json
{"api": 1, "id": "git-sync", "name": "Синхронізація з git", "version": "1.0.0",
 "roles": ["vcs"],
 "settings": [
   {"key": "repo", "type": "text", "label": "Репозиторій (типовий для задач простору)"},
   {"key": "branch", "type": "text", "label": "Гілка", "default": "main"},
   {"key": "path", "type": "text", "label": "Тека в репозиторії", "default": "mockup/{task}"},
   {"key": "ssh_key", "type": "text", "label": "SSH-ключ (необовʼязково)"},
   {"key": "host_ip", "type": "text", "label": "IP сервера (необовʼязково)"},
   {"key": "autosync", "type": "bool", "label": "Відправляти після кожної відповіді агента", "default": false}
 ]}
```

- [ ] **Step 2: Тести (червоні):**
  - **`tests/test_modules.py::test_roles`:**
    - `ROLES_CALLED == ('publish', 'tokens', 'comments', 'vcs')`;
    - `ROLES_RESERVED == ('tracker', 'dashboard', 'notify')`;
    - `ROLE_FUNCTIONS['vcs'] == ('status', 'push', 'pull')`;
    - `LEGACY_ROLES == ('publish', 'comments', 'vcs')`.
  - **Коди `vcs-*`.** Розширити наявний тест статусів (той, що з `want.items()`): `{'vcs-offline': 502, 'vcs-auth': 502, 'vcs-bad-target': 400, 'vcs-busy': 409, 'vcs-error': 502}`.
  - **`BUILTIN_IDS`** у `test_comments_role.py` і `test_modules_api.py`: `['css-tokens', 'git-sync', 'static-publish', 'supabase-comments', 'vercel-publish']`. Інваріант `KNOWN_*` (≈892) сам вимагатиме `git-sync` в `KNOWN_OTHER_MODULES`.
  - **`capabilities()`** — новий тест у `tests/test_modules.py` (поруч із наявними тестами `capabilities`):
    - простір без інтеграцій → `'vcs': None`;
    - з `git-sync` у `space.json` → `'vcs': 'git-sync'`;
    - простір з інтеграціями без явних модулів → `'vcs': 'legacy'`;
    - запасний словник при винятку (підмінити `_caps_key`, щоб кидав) → має ключ `vcs` (`'legacy'` для `integrations: true`, інакше `None`);
    - у просторі з інтеграціями й нечитабельним `space.json` `vcs` лишається `'legacy'`, як `publish`.
  - **`cache_dir`.** `module_ctx(space, 'git-sync')['cache_dir'] == os.path.join(spaces.home(), 'cache', <id простору>, 'git-sync')`. Теки НЕ існує після виклику: ядро її не створює.
  - **`check` вбудованого `git-sync` через каркас.** `dm.check(space, 'git-sync')` без `repo` → `{'ok': True, …}`. З `repo` = локальний bare → `ok: True`.
  - **`tests/test_git_sync_module.py`:** тест «маніфест розбирається каталогом». `dm.catalog()['git-sync'].status == 'ok'`, ролі `['vcs']`, ключі налаштувань як у Step 1.
- [ ] **Step 3: Прогнати — червоні.**
- [ ] **Step 4: Реалізація** у `app/deai_modules.py`:

```python
ROLES_CALLED = ('publish', 'tokens', 'comments', 'vcs')
ROLES_RESERVED = ('tracker', 'dashboard', 'notify')
ROLE_FUNCTIONS = {'publish': ('publish',), 'tokens': ('tokens',), 'comments': ('client_config', 'list', 'resolve'),
                  'vcs': ('status', 'push', 'pull')}
LEGACY_ROLES = ('publish', 'comments', 'vcs')
```

- **`STATUS`.** Додати коментар і коди:
  ```python
  # роль `vcs` (4a): мережа/DNS/тайм-аут git, відмова в доступі, погана ціль, зайняте дзеркало, решта відмов git
  'vcs-offline': 502, 'vcs-auth': 502, 'vcs-bad-target': 400, 'vcs-busy': 409, 'vcs-error': 502,
  ```
- **`_ctx`.** Додати `'cache_dir': os.path.join(spaces.home(), 'cache', _space_id(space) or '_', m.id)` — лише шлях. Коментар: «теку створює модуль (`makedirs` 0700): `_ctx` будується для кожного `check`, і створення тут падало б на незаписуваному `DEAI_HOME`».
- **`KNOWN_OTHER_MODULES`:** `frozenset({'css-tokens', 'git-sync', 'static-publish', 'vercel-publish'})`.
- **`capabilities`.** У гілці `except ModuleError`:
  ```python
  caps[role] = 'legacy' if role in ('publish', 'vcs') and spaces.integrations_for(space) else None
  ```
  Запасний словник `except Exception`:
  ```python
  {'publish': legacy, 'tokens': None, 'comments': None, 'vcs': legacy, 'error': 'module-error'}
  ```
  Докстрінг `capabilities`/`provider` — `vcs` поруч із `publish` (`'legacy'` у ЛІГА, неявного модуля нема).
- **Докстрінг модуля** (рядки 4–5). `vcs` тепер роль, яку ядро кличе (етап 4a). Зарезервовані — `tracker`, `dashboard`, `notify`. Абзац «Шлях ЛІГА недоторканий»: `LEGACY_ROLES` — `publish`, `comments`, `vcs`.
- [ ] **Step 5: Фікстури `capabilities`.** Прогнати повний Python-набір і в КОЖНОМУ точному словнику `capabilities`/`/api/spaces` додати ключ `vcs`:
  - простір з `integrations: true` → `'legacy'`;
  - інакше → `None`.

  Знайти всі:
  ```bash
  grep -rn "'comments': None\|'comments': 'legacy'\|\"comments\": null" tests/*.py
  ```
  Нічого не вгадувати: значення — з того, що віддає `capabilities()` для цього простору. JS-фікстури НЕ чіпати: без ключа `vcs` клієнт іде за `integrations` (Task 6).
- [ ] **Step 6: Прогнати** `python3 "$G" 1200 3000 npm test` — зелені, `legacy-golden` теж.
- [ ] **Step 7: Мутації:**
  1. прибрати `'vcs'` з `LEGACY_ROLES` → червоніє тест `'legacy'`;
  2. прибрати `'git-sync'` з `KNOWN_OTHER_MODULES` → інваріант;
  3. прибрати `'vcs-bad-target'` зі `STATUS` → тест кодів.
- [ ] **Step 8: Коміт** — `feat(4a): роль vcs у каркасі, маніфест git-sync, cache_dir у ctx`.

**Поправки ревʼю плану (26.10.2026, обовʼязкові; перекривають текст задачі вище):**

1. **`module.json`, `BUILTIN_IDS` і `KNOWN_OTHER_MODULES` уже зроблено в Task 1.** Step 1 і відповідні пункти Step 2/4 — лише перевірити.
2. **Необовʼязкові функції ролі.** `_build` кладе в `fns` лише `check` і `ROLE_FUNCTIONS`, тож `Module.fn('validate')`/`call(m, 'mirror_dir', …)` інакше недосяжні. Додати біля `ROLE_FUNCTIONS`:
   ```python
   #: Необовʼязкові функції ролі: беруться з server.py, якщо є й callable; свій модуль без них валідний.
   ROLE_OPTIONAL_FUNCTIONS = {'vcs': ('validate', 'mirror_dir')}
   ```
   У `_build` після циклу обовʼязкових функцій, перед `return Module(...)`:
   ```python
       for opt in dict.fromkeys(fn for r in meta['roles'] for fn in ROLE_OPTIONAL_FUNCTIONS.get(r, ())):
           f = ns.__dict__.get(opt)
           if callable(f):
               fns[opt] = f
   ```
   Назви змінних (`meta`, `ns`, `fns`) звірити з реальним `_build`.

   Тести:
   - модуль `roles: ["vcs"]` з `check/status/push/pull` без `validate` → `status == 'ok'`, `fn('validate') is None`;
   - з `validate` → `callable(m.fn('validate'))` і `dm.call(m, 'validate', ctx, t)` працює;
   - `git-sync` з каталогу → `callable(m.fn('mirror_dir'))`.

   Не робити їх обовʼязковими.
3. **`tests/test_modules.py:84`:** `CORE_CTX_KEYS = ('folder_ok', 'ModuleError', 'cache_dir')` (інакше червоніють усі тести, що порівнюють дані `ctx`).
4. **`tests/test_modules.py:411-415`** (`test_reserved_roles_need_no_function`):
   - зарезервовані тепер `('tracker', 'dashboard', 'notify')` / `['tracker', 'dashboard', 'notify']`;
   - новий тест: `roles=('vcs',)` із сервером `CHECK_ONLY` → `status == 'error'`, у тексті `status`.
5. **Пошук точних словників `capabilities` (Step 5).** Шаблон `grep -rn "'tokens': \(None\|'\)" tests/*.py`; попередній пропускав `'comments': 'cm'` і `LEGACY_SHAPE` (`tests/test_modules_api.py:≈1318`).

---

### Task 4: ядро — ціль, постачальник, `'legacy'`, старі імена через модуль; транспорт геть із `serve.py`

**Files:**
- Modify: `app/serve.py`:
  - розділ «GitLab-синхронізація» ≈585–1060;
  - `gitlab_pull` ≈1383;
  - `autosync` ≈1280;
  - `_task_new_write`/`task_new` ≈1919–2070;
  - `_commit_identity`.
- Modify: `tests/test_gitlab_sync.py`
- Create: `tests/test_vcs_core.py`

**Видалити з `serve.py` (тепер у модулі):**

- `_RESOLVER_FAIL`, `_git_once`, `_git`;
- `_mirror_dir`, `ensure_mirror`, `_align_mirror_remote`;
- `_rev_count`, `_on_remote`, `_behind_count`, `_behind_path_count`, `_ahead_count`, `_behind_top`;
- `_authored_at_origin`.

Лишаються: `gitlab_cfg`, `gitlab_web`, `mockup_hash`, `_mockup_files`, `machine_identity`, `iteration_is_mine`, `_stamp_author`, `_record_sync`, `_read_state`, `_adopt_publish_state`, `_authored_mtime`, `_touch_tree`. Будь-яке інше місце `serve.py`, що кличе видалене, знайти `grep -n` і перевести на модуль.

- [ ] **Step 1: Тести (червоні)** — `tests/test_vcs_core.py`. Ізоляція — як у `tests/test_gitlab_sync.py`:
  - тимчасові `DC_TASKS_FILE` (файл існує);
  - `DC_MIRRORS_DIR`;
  - `DC_IDENTITY_NAME`/`DC_IDENTITY_EMAIL`;
  - `HOME`.

  **`Legacy`** (шар просторів вимкнено, як у старих тестах):
  - **Постачальник:**
    - `serve.vcs_provider()` → `(Module git-sync, ctx, True)`;
    - `ctx['cache_dir'] == os.environ['DC_MIRRORS_DIR']`, `ctx['mirror_flat'] is True`, `ctx['settings']['autosync'] is True`.
  - **Тека дзеркала:** `serve.vcs_mirror_dir(gl)` == `<DC_MIRRORS_DIR>/<slug 0.7.0>` (для `/abs/x/origin.git` → `abs-x-origin.git` без першого `-`).
  - **Ціль `vcs_target`:**
    - задача з `gitlab{repo, path}` → ціль з `task`, без `None`-полів;
    - `gitlab{repo}` без `path` → `None`;
    - `vcs{repo}` у задачі перемагає `gitlab{}`;
    - `{task}` у `path` налаштувань → id;
    - `/x/` → `x`.
  - **Статус:**
    - `gitlab_status(task, gl, meta, 'it1')` після першого синку має `label == 'GitLab'`;
    - `web == serve.gitlab_web(gl)` — для `git@h:o/r.git` з підставним модулем; для локального репо `None`, як у 0.7.0.
  - **Тема коміту:** `gitlab_sync` пише `design-canvas: sync mockup/t1 (Тест) · it1` (`git log -1 --format=%s` у bare-репо).
  - **README** багатосторінкового макета містить `(design-canvas, задача`.
  - **`ModuleError` → `VcsError`:** origin сховано → `gitlab_sync` кидає `serve.VcsError` (і `OSError`), `code` ∈ `{'vcs-error', 'vcs-offline'}`, текст містить `fetch failed`.
  - **Тимчасова `src`:** після `gitlab_sync` у теці задачі нема нових файлів поза `iterations/` і `.git` (`src` — поза нею). У системній теці тимчасових файлів не лишилось `deai-vcs-*` від цього виклику — порівняти до й після.

  **`Plain`** (звичайний простір: ізольований `DEAI_HOME`, реєстр із простором без інтеграцій, `space.json` з `git-sync` увімкненим і `repo` = локальний bare, `spaces.request_space(<id>)`). Створювати реєстр — як у `tests/test_static_publish.py`/`tests/test_spaces_serve.py`; файл тестів САМ присвоює `DEAI_HOME` (охоронець `test_serve.SPACE_WRITERS`).
  - **Постачальник:**
    - `vcs_provider()` → `(Module, ctx, False)`;
    - `ctx['cache_dir']` під `<DEAI_HOME>/cache/<id>/git-sync`.
  - **Ціль:** `vcs_task(cfg, 't1', task)[3]` — ціль з налаштувань, `path == 'mockup/t1'`.
  - **Повний цикл:**
    - `gitlab_sync` → тема `deai: sync mockup/t1 (…) · it1`, автор коміту = `DC_IDENTITY_NAME`;
    - `gitlab_status` → `label == 'Git'`, `web is None`;
    - коміт колеги → `gitlab_pull` → нова ітерація з `note == 'оновлення з репозиторію'`;
    - чужий автор → форк.
  - **Без ролі.** Простір без `git-sync` → `vcs_provider() is None`; `gitlab_status(..., vcs=None)` → `{'configured': False}`.

  **`TaskNew`:**
  - звичайний простір з `git-sync`;
  - `task_new(cfg, 't2', vcs={'repo': <bare>}, profile=None, root=<простір>)`, коли в репо є `mockup/t2/index.html` → `cloned True`, it1 з репо, запис задачі має `vcs: {'repo': …}`;
  - без `index.html` → стартовий макет;
  - origin недоступний → стартовий макет, без винятку.

  **`PullTimes`:** перенести `test_frames_only_commit_on_origin_is_not_work` — вже має бути зеленим після переходу на `last_commit.time`.

- [ ] **Step 2: Прогнати — червоні.**

- [ ] **Step 3: Реалізація.** Новий розділ замість «GitLab-синхронизация» (≈585). Код:

```python
# ---------- Синхронізація з git: роль `vcs` (етап 4a) ----------
#
# Транспорт — модуль `git-sync` (`app/modules/git-sync/server.py`); ядро вирішує, ЩО відправити й ЯК прийняти (чистий
# макет, `.canvas-state.json`, авторство, форки). Старі імена (`gitlab_status`/`gitlab_sync`/`gitlab_pull`/`autosync`)
# лишаються з тими самими сигнатурами до 4d: `gl` — ціль ролі; постачальника вони знаходять самі (`vcs=None`) або
# беруть готового від маршруту. Ключ `gitlab` в `iterations.json` — внутрішня назва стану синку (сумісність тек задач).

VCS_MODULE = 'git-sync'


class VcsError(OSError):
    """Відмова ролі `vcs` для ядра. `OSError` свідомо: на ньому стоять маршрути синку, автосинк («офлайн» — тихо) і
    бутстрап задачі («не вийшло — стартовий макет»). `code` — `vcs-*` модуля або код каркаса."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


def _mirrors_base():
    return os.environ.get('DC_MIRRORS_DIR') or os.path.join(ROOT, '.mirrors')


def _vcs_legacy_ctx():
    """`ctx` неявного постачальника простору ЛІГА (`'legacy'`): той самий `git-sync`, без `space.json`. Дзеркала —
    старі теки 0.7.0 (`mirror_flat`: дизайнери не перегортають великі репо, незапушені коміти не осиротіють),
    автосинк увімкнено, як і було. Ключ і IP сервера несе ціль (`gitlab_cfg`)."""
    return {'space': {'id': spaces.request_space_id() or '', 'path': ''},
            'settings': {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True},
            'secrets': {}, 'folder_ok': lambda folder: (False, 'bad-folder'),
            'ModuleError': deai_modules.ModuleError,
            'cache_dir': _mirrors_base(), 'mirror_flat': True}


def vcs_provider():
    """Хто синкає в просторі запиту: `None` (ролі нема) або `(module, ctx, legacy)`. Відмова — `VcsError`
    (нечитабельний `space.json`, свій модуль «на папері», `git-sync` не завантажився), ніколи не 500."""
    try:
        prov = deai_modules.provider('vcs')
    except (deai_modules.ModuleError, spaces.SpacesError) as e:
        raise VcsError(getattr(e, 'code', 'vcs-error'), str(e)[:300]) from None
    if prov is None:
        return None
    if prov == 'legacy':
        try:
            m = deai_modules.catalog().get(VCS_MODULE)                 # лише вбудовані: без простору
        except Exception as e:  # noqa: BLE001 — шлях ЛІГА тепер залежить від каталогу: збій = vcs-error, не 500
            raise VcsError('vcs-error', f'module catalog: {type(e).__name__}') from None
        if m is None or m.status != 'ok':
            raise VcsError('vcs-error', f'{VCS_MODULE} module is not loaded')
        return m, _vcs_legacy_ctx(), True
    try:
        return prov, deai_modules.module_ctx(spaces.active_space(), prov), False
    except deai_modules.ModuleError as e:
        raise VcsError(e.code, e.message) from None


def _vcs_str(v):
    return isinstance(v, str) and v.strip() != ''


def vcs_target(cfg, tid, task, settings):
    """Ціль задачі для модуля або `None` (задачу не налаштовано). Порядок (спека 4a, «Роль `vcs`»): поле задачі
    `vcs{repo, path?, branch?}` (лише з непорожнім `repo`) → старе `gitlab{…}` (лише простір з інтеграціями; як
    `gitlab_cfg` 0.7.0: без `repo` чи `path` — не налаштована, ключ і IP — задачі чи спільні з `tasks.json`) →
    налаштування модуля. `{task}` у `path` — id задачі; `path` без `/` по краях."""
    def tpath(p):
        return str(p).replace('{task}', tid).strip('/')
    v = task.get('vcs')
    if isinstance(v, dict) and _vcs_str(v.get('repo')):
        return {'repo': v['repo'].strip(), 'task': tid,
                'path': tpath(v['path'] if _vcs_str(v.get('path')) else settings.get('path') or 'mockup/{task}'),
                'branch': (v['branch'] if _vcs_str(v.get('branch')) else settings.get('branch') or 'main').strip()}
    if task.get('gitlab') and spaces.integrations_on():
        gl = gitlab_cfg(cfg, task)
        return None if gl is None else {**{k: x for k, x in gl.items() if x}, 'task': tid}
    if _vcs_str(settings.get('repo')):
        return {'repo': settings['repo'].strip(), 'task': tid,
                'path': tpath(settings.get('path') or 'mockup/{task}'),
                'branch': (settings.get('branch') or 'main').strip()}
    return None


def vcs_task(cfg, tid, task):
    """`None` — у просторі запиту нема ролі `vcs`; інакше `(module, ctx, legacy, target | None)`. Відмова — `VcsError`."""
    p = vcs_provider()
    return None if p is None else (*p, vcs_target(cfg, tid, task, p[1].get('settings') or {}))


def _vcs_call(vcs, fn, *args):
    m, ctx, _legacy = vcs if vcs is not None else (vcs_provider() or (None, None, None))
    if m is None:
        raise VcsError('vcs-error', 'no git sync in this space')
    try:
        return deai_modules.call(m, fn, ctx, *args)
    except deai_modules.ModuleError as e:
        raise VcsError(e.code, e.message) from None


def vcs_mirror_dir(gl, vcs=None):
    """Тека дзеркала цілі — розкладку знає модуль; ядру й тестам — для діагностики."""
    return _vcs_call(vcs, 'mirror_dir', gl)
```

**`_commit_identity`.** Розщепити, не змінюючи її відповіді (на неї стоїть `test_serve.py::test_commit_identity_uses_one_source_of_truth`):

```python
def _commit_author():
    """Підпис коміту в дзеркало: особа машини, а без неї — константа (git без `user.email` не комітить). Див.
    `_commit_identity` — чому константа лише тут і ніколи не в даних ітерації."""
    name, key = machine_identity()
    return {'name': name or 'Designer One', 'email': key or 'designer.one@example.com'}


def _commit_identity():
    a = _commit_author()
    return ['-c', f'user.name={a["name"]}', '-c', f'user.email={a["email"]}']
```

Докстрінг `_commit_identity` лишити.

**`gitlab_status(task, gl, meta, it, vcs=None)`:**

```python
    try:
        v = vcs or vcs_provider()
        if v is None:
            return {'configured': False}
        st = _vcs_call(v, 'status', gl)
    except VcsError as e:
        return {'configured': True, 'error': str(e)[:200], 'code': e.code}
    g = meta.get('gitlab') or {}
    # … (dirty / gitlab_it — дослівно як у 0.7.0) …
    out = {'configured': True, 'behind': st.get('behind', 0), 'behind_path': st.get('behind_path', 0),
           'unpushed': st.get('unpushed', 0), 'on_remote': st.get('on_remote'),
           'dirty': bool(dirty), 'synced_at': g.get('synced_at'), 'synced_it': g.get('synced_it'),
           'gitlab_it': gitlab_it, 'remote_path': gl['path'], 'web': st.get('web'), 'label': st.get('label') or 'Git'}
    if v[2]:
        # Простір ЛІГА (`'legacy'`): «Історія» й підпис — як у 0.7.0 (будь-який `git@host:`, і з IP) — до 4d.
        out['web'], out['label'] = gitlab_web(gl), 'GitLab'
    return out
```

Коментарі 0.7.0 біля полів (`behind_path`, `unpushed`, `on_remote`) переносяться разом із полями.

**`gitlab_sync(tid, task, gl, it, vcs=None)`:**

- Перевірка теки ітерації й «чужої» — як було, ДО постачальника й мережі.
- Далі:

```python
    v = vcs or vcs_provider()
    if v is None:
        raise VcsError('vcs-error', 'no git sync in this space')
    legacy = v[2]
    meta_now = load_meta(task)
    it_entry = next((x for x in meta_now.get('iterations', []) if x['id'] == it), {})
    tmp = tempfile.mkdtemp(prefix='deai-vcs-')     # ПОЗА текою задачі: інакше git_autocommit підхопив би
    try:
        out_dir = os.path.join(tmp, 'm')
        copy_mockup(src, out_dir)
        # README.md для багатосторінкових — код 0.7.0 дослівно, лише назва інструмента:
        #   'design-canvas' (legacy) / 'Deai Canvas' (звичайний простір), і запис у out_dir.
        # STATE_FILE — код 0.7.0 дослівно, запис у out_dir.
        title = task.get('title', tid)
        note = (it_entry.get('note') or '').strip()
        subject = f'{"design-canvas" if legacy else "deai"}: sync {gl["path"]} ({title}) · {it}'
        body = f'Ітерація: {it} · Хеш: {mockup_hash(src)[:12]} · {time.strftime("%d.%m.%Y %H:%M")}'
        if note:
            body += f'\nЩо змінено: {note}'
        r = _vcs_call(v, 'push', gl, out_dir, {'message': subject + '\n\n' + body, 'author': _commit_author()})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {**r, 'remote': f'{gl["repo"]}:{gl["path"]}'}
```

`tempfile` імпортувати, якщо його ще нема.

**`gitlab_pull(task, gl, vcs=None)`:**

```python
    v = vcs or vcs_provider()
    if v is None:
        raise VcsError('vcs-error', 'no git sync in this space')
    src_name = 'GitLab' if v[2] else 'репозиторію'
    tmp = tempfile.mkdtemp(prefix='deai-vcs-')
    try:
        src = os.path.join(tmp, 'm')
        os.makedirs(src)
        r = _vcs_call(v, 'pull', gl, src, {'ignore': ['shots']})
        if not r.get('found'):
            raise OSError(f'path {gl["path"]} not found in repo')
        lc = r.get('last_commit') or {}
        author = lc.get('author') or ''
        note = f'оновлення з {src_name}'
        # … далі тіло 0.7.0 дослівно (state, ідемпотентність, нова itN, форк чужої, «старше за мою роботу»), з двома
        #    замінами: `pulled_at = lc.get('time')` замість `_authored_at_origin(...)`, і примітка форка
        #    f'продовження моєї роботи — з {src_name} приїхала старша версія'. `src` тепер — копія в tmp.
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
```

Повернення — як було. Коментар 0.7.0 про примітку без імені автора лишити.

**`autosync(tid, task, gl, vcs=None)`:**

- `gitlab_sync(tid, task, gl, it, vcs=vcs)`.
- Гілка `except OSError as e` додає `**({'code': e.code} if isinstance(e, VcsError) else {})`.

**`_task_new_write` / `task_new`.**

- Новий параметр `vcs=None` (після `gitlab`) в обох; `task_new` передає його далі.
- Гілку `if gitlab:` замінити:

```python
    if (gitlab or vcs) and adopt_src is None:
        if gitlab:
            # ⛔ ПЕРЕД `try` нижче: `IntegrationsOff` — підклас `OSError` (коментар 0.7.0 лишити).
            spaces.require_integrations()
        tmp = tempfile.mkdtemp(prefix='deai-vcs-')
        try:  # макет уже є в репо — беремо його в it1, не починаємо з нуля
            v = vcs_provider()
            target = None if v is None else vcs_target(
                cfg, tid, {'gitlab': gitlab} if gitlab else {'vcs': vcs}, v[1].get('settings') or {})
            if target:
                got = os.path.join(tmp, 'm')
                os.makedirs(got)
                # `pull` модуля = дзеркало + ff-only (коментар 0.7.0 про тижневий зріз чужого макета лишити)
                r = _vcs_call(v, 'pull', target, got, {'ignore': ['shots']})
                if r.get('found') and os.path.isfile(os.path.join(got, 'index.html')):
                    copy_mockup(got, it1)
                    cloned = True
                    cloned_state = _read_state(got)
        except OSError:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
```

- Примітка it2 при `cloned`: `'продовження макета з GitLab'` (legacy) / `'продовження макета з репозиторію'`. Хто legacy — запамʼятати з `v[2]` у змінну до `try`, за замовчуванням `True`.
- Запис задачі: `if vcs: entry['vcs'] = vcs`.
- Повідомлення автокоміту `clone from gitlab` лишається.

**`tests/test_gitlab_sync.py` — переїзд:**

- **Дзеркало:** `self.serve._mirror_dir(self.gl)` → `self.serve.vcs_mirror_dir(self.gl)`.
- **Лічильники й `_git`:**
  - `self.serve._behind_count(md, gl)` / `_ahead_count` / `_on_remote` → прямий git у `md`: `int(sh(['git', 'rev-list', '--count', 'main..origin/main'], md).stdout)` і т. ін.;
  - `_on_remote` → `cat-file -e` / `rev-parse --verify`, як у модулі;
  - `self.serve._git([...], md, gl)` → `sh(['git', ...], md)`.
- **`ensure_mirror`:** `self.serve.ensure_mirror(gl, fetch=True)` → `self.serve.gitlab_status(self.task, gl, self._meta(), 'it1')` (клон + fetch + звірка origin).
- **`ResolverRetryByIp`** — повністю переїжджає в `tests/test_git_sync_module.py` (Task 1 уже має еквівалент — перевірити, що всі три сценарії там є, і видалити клас тут).
- **Тести на `OSError`** (`fetch failed`, `pull --ff-only failed`) лишаються: `VcsError` — `OSError`, тексти ті самі.

Кожен тест, що перевіряв поведінку, лишається. Тест про внутрішню функцію, якої вже нема, — переїжджає в модульний набір з тією самою перевіркою. Нічого не видаляти мовчки: у звіті задачі — таблиця «тест → де тепер».

- [ ] **Step 4: Прогнати** `python3 "$G" 1200 3000 npm test` — усе зелене. Окремо: `tests/test_integrations_off.py`, де розтяжка чекає рівно одного зовнішнього `git clone`.

- [ ] **Step 5: Мутації:**
  1. `_vcs_legacy_ctx` без `mirror_flat` → тест старої теки дзеркала;
  2. `gitlab_status` без перекриття `web`/`label` у legacy → тест `label == 'GitLab'`;
  3. `pulled_at = None` → `test_frames_only_commit…`/«старша версія» червоніють;
  4. прибрати `finally: shutil.rmtree(tmp…)` у `gitlab_sync` → тест тимчасової теки;
  5. `vcs_target` без умови `spaces.integrations_on()` для `gitlab{}` → `tests/test_integrations_off.py`.

- [ ] **Step 6: Коміт** — `refactor(4a): ядро синкає через роль vcs — транспорт переїхав у git-sync`.

**Поправки ревʼю плану (26.10.2026, обовʼязкові; перекривають текст задачі вище):**

1. **Клон лише для `vcs` без `from`; ЛІГА — як була.** Умова в `_task_new_write`:
   ```python
       if gitlab or (vcs and adopt_src is None):
           if gitlab:
               spaces.require_integrations()   # ⛔ ПЕРЕД try (коментар 0.7.0 лишити)
   ```
   а не `if (gitlab or vcs) and adopt_src is None:`.
2. **Ціль клону:** `{'vcs': vcs} if vcs else {'gitlab': gitlab}` (явний `vcs.repo` перемагає профільний `gitlab`, як у `vcs_target`).

---

### Task 5: маршрути `/api/vcs-*`, псевдоніми, автосинк, `task-new` з `vcs`, `bin/state.py`

**Files:**
- Modify: `app/serve.py`:
  - диспетчери GET ≈5446 і POST ≈6307;
  - `_gitlab_status`/`_gitlab_sync`/`_autosync`/`_gitlab_pull` ≈6775–6845;
  - маршрут `task-new` ≈6976–7060.
- Modify: `bin/state.py` (`gitlab_line`, блок ≈400–415, імпорт ≈22)
- Modify: `tests/test_vcs_core.py`, `tests/test_state.py`, `tests/test_integrations_off.py` (за потреби), `tests/test_spaces_serve.py` (за потреби)

- [ ] **Step 1: Тести (червоні)** — HTTP у `tests/test_vcs_core.py`. Сервер у процесі, як у `tests/test_spaces_serve.py`: два простори — ЛІГА (інтеграції, задача з `gitlab{repo: <bare>, path}`) і звичайний з `git-sync`.

- **`/api/vcs-status` і `/api/gitlab-status`** дають той самий JSON (без `synced_at`-часу різниці нема).
  - Звичайний простір без модуля → `{'configured': False}`.
  - Нечитабельний `space.json` у звичайному просторі → 200 `{'configured': False, 'code': 'space-json-unreadable'}`.
- **`/api/vcs-push` і `/api/gitlab-sync`:**
  - без цілі → 400 з `no gitlab configured`;
  - origin сховано → 200 `{'ok': False, 'error': …, 'code': …}`.
- **`/api/vcs-pull` / `/api/gitlab-pull`** — так само.
- **`/api/autosync`:**
  - без ролі → `{'ok': True, 'changed': False, 'reason': 'no-gitlab'}` дослівно;
  - звичайний простір з `autosync: false` → `reason: 'autosync-off'`, жодного коміту в bare;
  - з `autosync: true` і зміною → `changed: True`;
  - origin сховано → `reason: 'offline'` і `code`, статус 200;
  - відмова постачальника → `reason: 'no-gitlab'` з `code`.
- **`task-new`** у звичайному просторі:
  - `vcs: {'repo': <bare>}` → 200, запис задачі з `vcs`;
  - `vcs: {'repo': 'ext::sh'}` → 400 `vcs-bad-target`, теки задачі нема;
  - `vcs` у просторі без ролі → 400 `vcs-needs-role`;
  - `vcs: 'x'` чи зайвий ключ → 400 `bad-request`.
- **`bin/state.py`** (`tests/test_state.py`):
  - `gitlab_line(st, 'p', label='GitHub')` → рядки з «GitHub (p)» і «на GitHub НОВІШЕ»;
  - без `label` — дослівно 0.7.0;
  - наявні патчі `state.gitlab_cfg` (≈413) → `state.vcs_task` (`lambda cfg, tid, task: (None, {}, True, {'path': 'p'})`), а `state.gitlab_status` лишається.

- [ ] **Step 2: Прогнати — червоні.**

- [ ] **Step 3: Реалізація маршрутів.**

**Диспетчер GET:**

```python
        if self.path.startswith('/api/gitlab-status') or self.path.startswith('/api/vcs-status'):
            self._gitlab_status()
            return
```

**Диспетчер POST:** `elif self.path in ('/api/gitlab-sync', '/api/vcs-push'):` і `elif self.path in ('/api/gitlab-pull', '/api/vcs-pull'):`. Якщо є перелік маршрутів, що змінюють стан (перевірка Origin/`Sec-Fetch-Site`), — нові адреси туди ж, де старі (`grep -n "gitlab-sync" app/serve.py`).

**Спільне для чотирьох обробників:**

```python
    def _vcs_ctx(self):
        """`(tid, task, vcs, err)`: `vcs` — `(module, ctx, legacy, target|None)` або `None` (ролі нема); `err` — `VcsError`
        постачальника. Простір без ролі — «нема синку», а не 409: UI опитує статус на кожному старті."""
        cfg = load_tasks()
        tid, task = self._current_task()
        try:
            return tid, task, vcs_task(cfg, tid, task), None
        except VcsError as e:
            return tid, task, None, e
```

**`_gitlab_status`:**

- `err` → `{'configured': False, 'code': err.code}`;
- `vcs is None or vcs[3] is None` → `{'configured': False}`;
- інакше `gitlab_status(task, vcs[3], load_meta(task), it, vcs=vcs[:3])`, із тим самим `except (OSError, subprocess.SubprocessError)`.

**`_gitlab_sync` / `_gitlab_pull`:**

- `err` → 200 `{'ok': False, 'error': str(err)[:300], 'code': err.code}`;
- без ролі чи цілі → `send_error(400, 'no gitlab configured for this task')`;
- виклик з `vcs=vcs[:3]`;
- `except (OSError, subprocess.SubprocessError) as e` → `{'ok': False, 'error': str(e)[:300], **({'code': e.code} if isinstance(e, VcsError) else {})}`.

Після синку `_record_sync` і `_overview_sync()` — як було: `_overview_sync` сам мовчить поза інтеграціями.

**`_autosync`:**

```python
        tid, task, vcs, err = self._vcs_ctx()
        if err is not None or vcs is None or vcs[3] is None:
            out = {'ok': True, 'changed': False, 'reason': 'no-gitlab'}
            self._send_json({**out, 'code': err.code} if err is not None else out)
            return
        if not (vcs[1].get('settings') or {}).get('autosync'):
            self._send_json({'ok': True, 'changed': False, 'reason': 'autosync-off'})
            return
        # далі як було, autosync(tid, task, vcs[3], vcs=vcs[:3])
```

Докстрінг `_autosync` — про обидві причини й про те, що Stop-хук мовчить на причинах, яких не знає.

**`task-new`.** Після `spaces.set_request_space(sp['id'])` і перевірки `taken`, ДО `adopt`:

```python
        vcs = payload.get('vcs')
        if vcs is not None:
            if (not isinstance(vcs, dict) or not _vcs_str(vcs.get('repo'))
                    or any(k not in ('repo', 'path', 'branch') for k in vcs)
                    or any(x is not None and not isinstance(x, str) for x in vcs.values())):
                self._space_error(400, 'bad-request', 'vcs must be {repo, path?, branch?} of strings')
                return
            vcs = {k: x.strip() for k, x in vcs.items() if _vcs_str(x)}
            try:
                prov = vcs_provider()
            except VcsError as e:
                self._space_error(409, e.code, str(e)[:300])
                return
            if prov is None:
                self._space_error(400, 'vcs-needs-role', 'this space has no git sync — connect a module on Connections')
                return
            if prov[0].fn('validate') is not None:
                try:
                    _vcs_call(prov, 'validate', vcs_target({}, tid, {'vcs': vcs}, prov[1].get('settings') or {}))
                except VcsError as e:
                    self._space_error(400, e.code, str(e)[:300])
                    return
```

Далі `task_new(..., vcs=vcs, ...)`. Докстрінг маршруту — абзац про `vcs` (спека 4a, «Нова задача»).

- [ ] **Step 4: `bin/state.py`:**
  - **Імпорт:** `vcs_task`, `VcsError` замість `gitlab_cfg` (і `gitlab_status` лишається).
  - **`gitlab_line(st, path, tid=None, label='GitLab')`:** кожне `GitLab` у рядках → `{label}`, включно з «на {label} НОВІШЕ». Підказки з `/api/gitlab-sync`/`/api/gitlab-pull` не міняти: це псевдоніми, і вони діють у будь-якому просторі.
  - **Блок ≈400:**

```python
    integrations = spaces.integrations_on()
    try:
        vcs = vcs_task(cfg, tid, task)
    except VcsError as e:
        vcs, vcs_err = None, e
    else:
        vcs_err = None
    label = 'Git' if vcs and not vcs[2] else 'GitLab'
    if vcs and vcs[3]:
        try:
            work = working_iteration(its, machine_identity()[1])
            st = gitlab_status(task, vcs[3], meta, work['id'] if work else None, vcs=vcs[:3])
            print(gitlab_line(st, vcs[3]['path'], tid if named else None, label=st.get('label') or label))
        except Exception as e:  # noqa: BLE001
            print(f'{label}: не дістати статус ({e})')
    elif vcs_err is not None:
        print(f'{label}: не дістати статус ({vcs_err})')
    else:
        print(f'{label}: не налаштований для задачі')
```

Змінну `integrations` лишити: її читає решта функції.

- [ ] **Step 5: Прогнати** `python3 "$G" 1200 3000 npm test` — зелені.
- [ ] **Step 6: Мутації:**
  1. `_autosync` без гілки `autosync-off` → тест;
  2. повернути `reason: 'no-vcs'` → `test_integrations_off`;
  3. прибрати `validate` у `task-new` → тест `ext::sh`;
  4. прибрати `/api/vcs-status` з диспетчера → тест псевдоніма.
- [ ] **Step 7: Коміт** — `feat(4a): маршрути /api/vcs-*, автосинк за модулем, task-new з vcs, state.py за роллю`.

**Поправки ревʼю плану (26.10.2026, обовʼязкові; перекривають текст задачі вище):**

1. **Диспетчер POST — чотири окремі гілки** `elif self.path == '/api/gitlab-sync':` / `elif self.path == '/api/vcs-push':` (обидві → `self._gitlab_sync(payload)`), так само `gitlab-pull`/`vcs-pull` → `_gitlab_pull`. Охоронець `bad-body` (`tests/test_serve.py:≈1393`) збирає маршрути регексом `self\.path == '(/api/[a-z-]+)'` і кортеж `in (…)` пропустив би.
   - У `tests/test_spaces_serve.py:≈747` додати `('POST', '/api/vcs-push', '_gitlab_sync')`.
   - Речення про «перелік маршрутів з перевіркою Origin» — не застосовне: перевірка Origin глобальна.
2. **`bin/state.py`.** Гілка `elif vcs_err is not None`: коли в задачі нема ні `gitlab`, ні `vcs`, друкувати «`{label}`: не налаштований для задачі», а не «не дістати статус».

---

### Task 6: клієнт — смуга, палітра, дії, тексти

**Files:**
- Modify:
  - `app/spaces-model.js`, `app/bar-model.js`, `app/shell-bar.js`, `app/shell-palette.js`, `app/app.js`;
  - `app/i18n.js`.
- Create: `tests/vcs-client.test.mjs`
- Modify: тести смуги/палітри/словника, що впадуть (`bar-model`, `shell-bar`, `shell-palette`, `i18n-*`) — лише там, де змінився контракт.

- [ ] **Step 1: Тести (червоні)** — `tests/vcs-client.test.mjs`:
  - **`hasVcs` — обидві форми:**
    - `{integrations: false, capabilities: {vcs: 'git-sync'}}` → true;
    - `{integrations: true, capabilities: {vcs: null}}` → false;
    - `{integrations: true, capabilities: {publish: 'legacy'}}` (без ключа) → true;
    - `{integrations: false}` → false;
    - `null` → true (як `hasTeamComments`), `isLegacyVcs(null)` → true.
  - **`isLegacyVcs`:**
    - `capabilities.vcs === 'legacy'` → true;
    - без ключа і `integrations !== false` → true;
    - `'git-sync'` → false.
  - **`barModel`:**
    - зона `gl` є за `hasVcs`;
    - `glLabel: 'GitHub'` → `labelKey: 'vcsGitHub'`, `brand: 'GitHub'`; `'Git'` → `vcsGit`/`brand: 'Git'`;
    - `'GitLab'` чи порожньо → `labelKey: 'gitlab'` і поля `brand` НЕМА (`!('brand' in zone)`);
    - при `gl: 'sync'` і `brand` → `whyKey: 'vcsSyncWhy'`, без `brand` → `glSync`.
  - **Палітра:** пункти `glpush`/`glpull` при `glBrand: 'GitHub'` несуть `labelArgs: [iterLabel, 'GitHub']`, без бренду — без `labelArgs` (форма 0.7.0).
  - **Словник:**
    - `t('glPush', 'Іт.2', 'GitHub')` містить «GitHub», `t('glPush', 'Іт.2')` — дослівно 0.7.0 («Надіслати Іт.2 на GitLab»);
    - те саме для `glPull`, `glHistory`, `glBehindMsg`, `glSyncFailedMsg`, `glCatchupToast`, `glNothingToSendToast`, `glPushedToast`, `glPullConfirmMsg`, `glPullUnchangedToast`, `glPullOlderToast` — обома мовами;
    - 15 мертвих ключів (перелік у спеці, «Тексти») відсутні в `UK` і `EN`.
  - **Мапер помилок дій** `vcsErrKey(code)`: `vcs-offline` → `vcsErrOffline`, `vcs-auth` → `vcsErrAuth`, `vcs-busy` → `vcsErrBusy`, `vcs-bad-target` → `vcsErrTarget`, інше → `null`.
  - **Підключення в `app.js`.** Статичні перевірки джерела, як у `tests/spaces-wiring.test.mjs`:
    - `refreshGitlab` питає `/api/vcs-status`, `glpush` — `/api/vcs-push`, `glpull` — `/api/vcs-pull`;
    - у тілі `afterModulesChange` порядок підрядків `render(` < `refreshGitlab(` < `paintBar(`;
    - `refreshGitlab` гейтиться `noVcs()`, а `loadTeamsMute` — як і було (`noOutward()`);
    - `glsetup` кличе `enterConnections()`, коли НЕ `isLegacyVcs(spaceNow())`.

- [ ] **Step 2: Прогнати — червоні** (`python3 "$G" 300 2000 node --test tests/vcs-client.test.mjs`).

- [ ] **Step 3: Реалізація.**

**`app/spaces-model.js`** — поруч із `hasTeamComments`:

```js
/**
 * Чи є в просторі синхронізація з git (роль `vcs`, етап 4a). Є ключ `capabilities.vcs` — він і вирішує (`'legacy'` —
 * зашитий шлях ЛІГА, id модуля — модуль, `null` — нема). Ключа нема (стара форма відповіді, шар вимкнено, фікстури
 * `legacy-golden`) — за `integrations`, як було до 4a: простір без відомостей не краде в людини синк.
 */
export const hasVcs = (space) => {
  const caps = space?.capabilities;
  return caps && typeof caps === "object" && "vcs" in caps ? caps.vcs != null : space?.integrations !== false;
};

/** Синк простору — зашитий шлях ЛІГА (налаштовується в `tasks.json`, не на «Підключенні»). */
export const isLegacyVcs = (space) => {
  const caps = space?.capabilities;
  return caps && typeof caps === "object" && "vcs" in caps ? caps.vcs === "legacy" : space?.integrations !== false;
};

/** Стеля запиту створення задачі в просторі з синком: перший клон репозиторію триває хвилини (модуль чекає до 180 с). */
export const TASK_VCS_POST_TIMEOUT_MS = 200000;
```

`hasVcs(null)` — `true`, як `hasTeamComments(null)`: невідомий простір (шар вимкнено) не краде в людини синк.

**`app/bar-model.js`.**

- `noInteg` лишається для Teams (`teamsItem`). Для зони `gl` — нова `const noVcs = !hasVcs(s.space);` (імпорт з `spaces-model.js`).
- Підпис:

```js
const VCS_LABEL_KEYS = { GitHub: "vcsGitHub", Git: "vcsGit" };
const brand = VCS_LABEL_KEYS[s.glLabel] ? s.glLabel : "";
```

- Елемент зони:

```js
{ id: "gl", tier: 0, labelTier: TIERS.gl, labelKey: brand ? VCS_LABEL_KEYS[brand] : "gitlab", status: s.gl, items: glItems, ...(brand ? { brand } : {}) }
```

- У `glItems` для `glpush`: `whyKey: s.gl === "sync" ? (brand ? "vcsSyncWhy" : "glSync") : ""` (порахувати `brand` вище за `glItems`).
- Коментар «Вимикач» — оновити: зона синку тепер за роллю `vcs`.

**`app/shell-bar.js`, `ddGitlab`.** `t(sub.labelKey, iterLabel)` → `t(sub.labelKey, iterLabel, ...(c.brand ? [c.brand] : []))`; `glhistory` — `t(sub.labelKey, ...(c.brand ? [c.brand] : []))`.

**`app/shell-palette.js`.**

- `noOutward` (≈207, ≈381 — він обслуговує лише GitLab) перейменувати на `noVcs = !hasVcs(s.space)`.
- `glpull`/`glpush`: `...(s.glBrand ? { labelArgs: [s.iterLabel, s.glBrand] } : {})`.
- `whyKey` для `glpush` — як у смузі.

**`app/app.js`:**

- **Гейт:** `const noVcs = () => needsWelcome(spacesResp) || !hasVcs(spaceNow());` поруч із `noOutward`. Коментар: Teams лишається на `integrations`.
- **`barState()`:** `glLabel: glCache?.label || ''`. Палітрі — `glBrand` (там, де стан палітри збирається з того самого, що й смуга): `glBrand: ({ GitHub: 'GitHub', Git: 'Git' })[glCache?.label] || ''`.
- **`refreshGitlab`:** `if (noVcs()) { glCache = null; return; }` і `/api/vcs-status?it=…`.
- **`glpush`:** `post('/api/vcs-push', …)`. Для `!r.ok` з `r.code` — `vcsErrKey(r.code)`:

  ```js
  tell(t(key, glCache?.label || 'GitLab'))
  ```

  Інакше `glSyncFailedMsg`. Кожен виклик тексту з «GitLab» отримує підпис останнім аргументом лише коли `glCache?.label` не `GitLab`.
- **`glpull`:** `post('/api/vcs-pull', {})`. `catch (e)`: `e.code` з мапера → свій текст.
- **`glsetup`:**

  ```js
  () => { if (isLegacyVcs(spaceNow())) tell(t('glSetupMsg')); else enterConnections(); }
  ```

  Коментар — чому в ЛІГА лишається повідомлення (спека, «Простір ЛІГА»).
- **`afterModulesChange`:** `await refreshGitlab();` між `await render({ keepFrame: homeOpen });` і `paintBar();`. Не відразу після `loadSpaces()`: `spaceNow()` бере `curTask?.space`, який оновлює `render()`, тож раніше він читав би старі `capabilities`.

**`vcsErrKey`** — у `app/spaces-model.js` (чиста функція, тестується):

```js
const VCS_ERR_KEYS = new Map([
  ["vcs-offline", "vcsErrOffline"], ["vcs-auth", "vcsErrAuth"], ["vcs-busy", "vcsErrBusy"], ["vcs-bad-target", "vcsErrTarget"],
]);
export const vcsErrKey = (code) => VCS_ERR_KEYS.get(code) ?? null;
```

**`app/i18n.js`.**

- Видалити 15 мертвих ключів з `UK` і `EN`.
- Тексти з «GitLab» — останнім параметром `label = 'GitLab'`:

  ```js
  glPush: (it, label = 'GitLab') => `Надіслати ${it} на ${label}`
  ```

  Рядкові ключі (`glHistory`, `glCatchupToast`, `glNothingToSendToast`, `glPullConfirmMsg` та ін.) стають функціями. Відмінювання: «на GitHub», «на Git» — нейтрально, прийнятно.
- Нові ключі, обидві мови:

| ключ | uk | en |
|---|---|---|
| `vcsGitHub` | `GitHub` | `GitHub` |
| `vcsGit` | `Git` | `Git` |
| `vcsSyncWhy` | `Збігається з репозиторієм` | `Matches the repository` |
| `vcsErrOffline` | `(label) => \`${label} не відповідає — немає мережі чи VPN. Макет лишився на цьому компʼютері.\`` | `(label) => \`${label} is not answering — no network or VPN. The layout stayed on this computer.\`` |
| `vcsErrAuth` | `(label) => \`${label} не пускає — перевір SSH-ключ чи вхід у git на цьому компʼютері.\`` | `(label) => \`${label} refused access — check the SSH key or the git sign-in on this computer.\`` |
| `vcsErrBusy` | `Синхронізація вже йде — спробуй за хвилину.` | `A sync is already running — try again in a minute.` |
| `vcsErrTarget` | `Адреса репозиторію, гілка чи тека не підходять — виправ їх на «Підключенні».` | `The repository address, branch or folder is not valid — fix them on Connections.` |

- [ ] **Step 4: Прогнати** `python3 "$G" 900 3000 npm test`: зелені, `legacy-golden` — побайтно. Якщо golden червоніє, проблема в гейті чи формі моделі, а не в golden.
- [ ] **Step 5: Мутації:**
  1. `hasVcs` без гілки «ключа нема» (лише `caps.vcs != null`) → `legacy-golden`/тест `hasVcs`;
  2. `afterModulesChange` без `refreshGitlab` → тест підключення;
  3. завжди `brand` у зоні → тест «поля `brand` нема».
- [ ] **Step 6: Коміт** — `feat(4a): смуга й палітра синку за роллю vcs, підпис репозиторію, нові адреси`.

**Поправки ревʼю плану (26.10.2026, обовʼязкові; перекривають текст задачі вище):**

1. **`glpull` — відмова git приходить як 200 `{ok: false, error, code}`.** `catch` її не бачить. Після гілок `r.unchanged` / `r.continue_from && r.fork`:
   ```js
   else if (r.ok === false) { const k = vcsErrKey(r.code); tell(k ? t(k, glCache?.label || 'GitLab') : t('glSyncFailedMsg', r.error || '—')); }
   ```
   `catch (e)` лишається `tell(t('errFailed', e.message))`. Тест на цю гілку.
2. **`refreshGitlab` — `vcs-busy` лишає попередній стан** (спека):
   ```js
   try { const r = await api(`/api/vcs-status?it=${encodeURIComponent(picked || '')}`); glCache = (r.code === 'vcs-busy' && glCache) ? glCache : r; }
   ```
   Статичний пін на це.
3. **Стан палітри копіюється поіменно** (`paletteState()` ≈6871: `gl: st.gl, iterLabel: st.iterLabel`).
   - `barState()` (біля `iterOnGl`): `glLabel: glCache?.label || ''`.
   - `paletteState()`: `gl: st.gl, glBrand: ({ GitHub: 'GitHub', Git: 'Git' })[st.glLabel] || '', iterLabel: st.iterLabel`.
4. **Піни, що зміняться разом із кодом:**
   - `tests/spaces-wiring.test.mjs:≈59` — `if \(noOutward\(\)\) \{ glCache = null; return; \}` → `noVcs`;
   - `:≈452` — `if \(!noOutward\) \{…` у палітрі → `!noVcs`; заголовок тесту «GitLab — на integrations» → «на hasVcs».

   Решта пінів `noOutward` (Teams, `:61`, `:469`) лишаються.

---

### Task 7: клієнт — «Підключення», майстер, форма нової задачі

**Files:**
- Modify: `app/connections-model.js`, `app/space-dialogs.js`, `app/app.js`, `app/wizard.js`, `app/spaces-model.js`, `app/i18n.js`
- Modify: `tests/connections-model.test.mjs` (`ROLE_ORDER`), `tests/vcs-client.test.mjs`, тести майстра/форми, що впадуть

- [ ] **Step 1: Тести (червоні)** — у `tests/vcs-client.test.mjs` і наявних:
  - **Таблиці «Підключень»:**
    - `ROLE_ORDER` → `["publish", "comments", "vcs", "tokens"]`. Секція після `comments`; оновити `deepEqual` у `tests/connections-model.test.mjs`;
    - `roleKeys('vcs')` → `{title: 'cnRoleVcs', lead: 'cnRoleVcsLead', none: 'cnNoneVcs'}`;
    - `roleIcon('vcs')` → `cloud`;
    - `builtinText('git-sync')` — назва, опис, шість полів.
  - **`verdictText`:** `verdictText({ok: false, error: 'vcs-offline'})` → `cnErrVcsOffline`, так само для `vcs-auth`/`vcs-bad-target`/`vcs-busy`/`vcs-error`.
  - **`disableConsequences`:** `git-sync` у просторі `integrations: true` з `capabilities.vcs === 'git-sync'` → `[{role: 'vcs', kind: 'legacy'}]`; без інтеграцій → `kind: 'none'`, `noneKey: 'cnNoneVcs'`.
  - **Помилки створення задачі:**
    - `taskErrKey('vcs-bad-target')` → `taskErrVcsTarget`, `taskErrField('taskErrVcsTarget')` → `repo`;
    - `taskErrKey('vcs-needs-role')` → `taskErrVcsRole`.
  - **Розмітка форми:**
    - `taskFormHTML({repo: {placeholder: 'git@x:y.git'}})` має `<input id="tf-repo" name="repo"` з `placeholder` (через `esc`) і підпис `newTaskRepo`;
    - без `repo` — розмітка дослівно 0.7.0 (порівняти з викликом без аргументу).
  - **Підключення в `app.js`.** Статичні перевірки:
    - `newTaskDialog` передає `repo`, коли `hasVcs(sp) && !isLegacyVcs(sp)`;
    - тіло запиту несе `vcs: {repo}` лише з непорожнім значенням;
    - запит іде через `taskPost`, коли `hasVcs(sp)`;
    - `formApi` не змінився (наявний пін `tests/spaces-wiring.test.mjs` зелений).
  - **Майстер:** `wizard.js` створює задачу через `deps.postTask ?? deps.post`.

- [ ] **Step 2: Прогнати — червоні.**

- [ ] **Step 3: Реалізація.**

**`connections-model.js`:**

- `ROLE_ORDER = ["publish", "comments", "vcs", "tokens"]`;
- `ROLE_KEYS.vcs = { title: "cnRoleVcs", lead: "cnRoleVcsLead", none: "cnNoneVcs" }`;
- `ROLE_ICONS.vcs = "cloud"`;
- `BUILTIN_TEXT["git-sync"]`:

  ```js
  { name: "cnModGitName", desc: "cnModGitDesc", fields: { repo: "cnFieldGitRepo", branch: "cnFieldGitBranch", path: "cnFieldGitPath", ssh_key: "cnFieldGitSshKey", host_ip: "cnFieldGitHostIp", autosync: "cnFieldGitAutosync" } }
  ```

- `CHECK_KEYS` += `["vcs-offline", "cnErrVcsOffline"], ["vcs-auth", "cnErrVcsAuth"], ["vcs-bad-target", "cnErrVcsTarget"], ["vcs-busy", "cnErrVcsBusy"], ["vcs-error", "cnErrVcsError"]`;
- `disableConsequences`: `(role === "publish" || role === "comments" || role === "vcs")` у гілці `legacy`.

**`space-dialogs.js`.** `taskFormHTML({ title = "", id = "", errorKey = "", repo = null } = {})` — після поля id, лише коли `repo`:

```js
    ${repo ? `<div class="cv-field">
      <label for="tf-repo">${esc(t("newTaskRepo"))}</label>
      <input id="tf-repo" name="repo" type="text" value="" autocomplete="off" spellcheck="false"
        placeholder="${esc(repo.placeholder || t("newTaskRepoPh"))}" aria-describedby="${ERR_ID}">
    </div>` : ""}
```

Збір значень форми (`askForm`/`wireTaskForm`) мусить віддати `vals.repo`. Перевірити, як `askForm` збирає `name=` полів, і, якщо поле треба додати явно, — додати.

**`spaces-model.js`:**

- `TASK_ERR_KEYS` += `["vcs-bad-target", "taskErrVcsTarget"], ["vcs-needs-role", "taskErrVcsRole"]`;
- `taskErrField`: `key === "taskErrVcsTarget" ? "repo" : …`.

Переконатися, що `ctl.focus('repo')` у майстрі (поля нема) нічого не ламає: якщо `focus` кидає на невідоме поле — повертати `null` для майстра. Простіше: `ctl.focus` уже стійкий — перевірити тестом.

**`app.js`:**

- **`taskPost`** — поруч із `trustPost`, та сама форма з `TASK_VCS_POST_TIMEOUT_MS`. Обрив → `code: 'timeout'`.
- **`newTaskDialog`:**

```js
  const withRepo = hasVcs(sp) && !isLegacyVcs(sp);
  const repoHint = withRepo
    ? api(`/api/modules?space=${encodeURIComponent(sp.id)}`).then((r) => {
      const m = (r.modules || []).find((e) => e.enabled === true && (e.roles || []).includes('vcs'));
      return m?.settings?.find((s) => s.key === 'repo')?.value || '';
    }).catch(() => '')
    : Promise.resolve('');
```

  Підказка вставляється при монтуванні (`onMount`: `form.querySelector('#tf-repo')?.setAttribute('placeholder', await repoHint)`, якщо непорожня). Перевірити реальну форму відповіді `GET /api/modules` у `serve.py` (ключ списку й поле `value` налаштування) і взяти саме її.
- **Тіло запиту:**

  ```js
  { id, title, space: sp.id, ...(withRepo && vals.repo?.trim() ? { vcs: { repo: vals.repo.trim() } } : {}) }
  ```

  Запит — `hasVcs(sp) ? taskPost(body) : postForm('/api/task-new', body)`.
- **Залежності майстра** (≈1343): `postTask: (p, body) => taskPost(body)`. Перевірити, що `taskPost` шле саме на `/api/task-new`, або зробити його `(path, body)`.

**`wizard.js` ≈597.** `(deps.postTask ?? deps.post)("/api/task-new", …)`. Коментар у шапці файла (перелік `deps`): `postTask` — створення задачі з довшою стелею.

**`i18n.js`** — нові ключі, обидві мови:

| ключ | uk | en |
|---|---|---|
| `cnRoleVcs` | `Синхронізація з git` | `Git sync` |
| `cnRoleVcsLead` | `Відправляти ітерації в git-репозиторій і отримувати правки колег.` | `Send iterations to a git repository and pull colleagues’ changes.` |
| `cnNoneVcs` | `Без синхронізації — макети лише на цьому компʼютері.` | `No sync — layouts stay on this computer only.` |
| `cnModGitName` | `Git` | `Git` |
| `cnModGitDesc` | `Будь-який git-репозиторій — GitHub, GitLab чи свій сервер. Доступ — через git цього компʼютера (SSH-ключ чи збережений вхід), Deai паролів не зберігає.` | `Any git repository — GitHub, GitLab or your own server. Access goes through this computer’s git (SSH key or saved sign-in); Deai stores no passwords.` |
| `cnFieldGitRepo` | `Репозиторій (типовий для задач)` | `Repository (default for tasks)` |
| `cnFieldGitBranch` | `Гілка` | `Branch` |
| `cnFieldGitPath` | `Тека в репозиторії ({task} — id задачі)` | `Folder in the repository ({task} is the task id)` |
| `cnFieldGitSshKey` | `SSH-ключ (необовʼязково)` | `SSH key (optional)` |
| `cnFieldGitHostIp` | `IP сервера, коли DNS у VPN не відповідає (необовʼязково)` | `Server IP when DNS over VPN fails (optional)` |
| `cnFieldGitAutosync` | `Відправляти після кожної відповіді агента` | `Send after every agent reply` |
| `cnErrVcsOffline` | `Репозиторій не відповідає — немає мережі чи VPN.` | `The repository is not answering — no network or VPN.` |
| `cnErrVcsAuth` | `Немає доступу — перевір SSH-ключ чи вхід у git.` | `No access — check the SSH key or the git sign-in.` |
| `cnErrVcsTarget` | `Адреса, гілка чи тека не підходять.` | `The address, branch or folder is not valid.` |
| `cnErrVcsBusy` | `Синхронізація вже йде — перевір за хвилину.` | `A sync is running — check again in a minute.` |
| `cnErrVcsError` | `Git відмовив.` | `Git refused.` |
| `newTaskRepo` | `Репозиторій (необовʼязково)` | `Repository (optional)` |
| `newTaskRepoPh` | `типовий з «Підключення»` | `the default from Connections` |
| `taskErrVcsTarget` | `Адреса репозиторію не підходить: ssh://, https://, git@сервер:шлях або тека на диску.` | `The repository address is not valid: ssh://, https://, git@host:path or a local folder.` |
| `taskErrVcsRole` | `У просторі немає синхронізації з git — підключи її на «Підключенні».` | `This space has no git sync — connect it on Connections.` |

Якщо є тест «кожен ключ моделі «Підключень» є в обох мовах» (`tests/connections-own.test.mjs` чи схожий) — нові ключі мусять пройти й там.

- [ ] **Step 4: Прогнати** `python3 "$G" 900 3000 npm test` — зелені, `legacy-golden` побайтно.
- [ ] **Step 5: Мутації:**
  1. `ROLE_ORDER` без `vcs` → тест;
  2. `disableConsequences` без `vcs` у гілці `legacy` → тест;
  3. `newTaskDialog` шле `vcs` і з порожнім полем → тест тіла.
- [ ] **Step 6: Коміт** — `feat(4a): «Підключення» й майстер — секція синхронізації з git; поле «Репозиторій» у новій задачі`.

**Поправки ревʼю плану (26.10.2026, обовʼязкові; перекривають текст задачі вище):**

1. **Тести «Підключень», що використовували `vcs` як «чужу» роль, — на ще зарезервовану `tracker`:**
   - `tests/connections-model.test.mjs`: `:17` (`roleKeys`), `:23` (`roleIcon`), `:40`, `:46` (групування; рядок `:46` → `["publish","comments","tokens","alpha","tracker",""]`), `:60`, `:292` (`providerLine`);
   - `tests/connections-view.test.mjs`: `:90`, `:92`, `:138`.

   `:13` → `["publish","comments","vcs","tokens"]`.

---

### Task 8: живі тести

**Files:**
- Create: `tests/live/git-sync.test.mjs`
- Modify: `tests/live/gitlab-pull-older.test.mjs` (моки `**/api/gitlab-status*` → `**/api/vcs-status*`, `**/api/gitlab-pull` → `**/api/vcs-pull`)
- Modify (лише якщо впали): `tests/live/connections.test.mjs`, `tests/live/wizard.test.mjs` — нова секція ролі змінює кількість секцій/карток

- [ ] **Step 1: `tests/live/git-sync.test.mjs`.** За зразком `tests/live/own-modules.test.mjs` і `tests/live/connections.test.mjs`:
  - ізольований `HOME`/`DEAI_HOME`, сервер у смузі портів 13600–13699;
  - `_spaces-kit.mjs`, охоронець справжнього `~/.deai` — останнім тестом.

  Bare-репо — `execFileSync('git', …)` у тимчасовій теці (`file://`). Колега — окрема робоча копія з `user.name=Колега`.

  Сценарії:
  1. **Без модуля.** Звичайний простір із задачею; зони синку в смузі нема (`[data-dd="gl"]` відсутній).
  2. **Підключення.**
     - «Підключення» → секція «Синхронізація з git» → увімкнути `git-sync`, `repo` = `file:///…/origin.git`, зберегти;
     - «Перевірити» → вердикт «гаразд» з деталлю про гілку;
     - повернутись до задачі → зона є, підпис `Git`.
  3. **Перший push.**
     - «Надіслати Іт.1» → тост «Надіслано на Git · комміт …»;
     - у bare `git log -1 --format=%s main` починається з `deai: sync mockup/<id>`.
  4. **Pull.**
     - Колега змінює `mockup/<id>/index.html` і пушить;
     - опит статусу (перезавантаження чи `refreshGitlab` через перемикання) → крапка `behind`, у меню «Підтягнути…»;
     - підтвердити → зʼявилась нова ітерація (і форк: автор чужий).
  5. **Автосинк.**
     - `POST /api/autosync` (із заголовками, як `fixture.mjs` шле запити агента) при `autosync: false` → `reason: 'autosync-off'`;
     - увімкнути `autosync` на «Підключенні», змінити файл ітерації → `changed: true`.
  6. **Нова задача з репозиторієм.**
     - «Нова задача» з полем «Репозиторій» = той самий `file://` і id, для якого колега заздалегідь поклав `mockup/<id2>/index.html`;
     - задача відкривається з макетом колеги в Іт.1.
  7. **ЛІГА без змін.** Задача з `gitlab{repo: <bare>, path}`: підпис «GitLab», «Налаштувати…» для задачі без маппінгу показує повідомлення про `tasks.json`, а не «Підключення». Задача в просторі з інтеграціями — через `fixture.mjs`, як інші живі тести ЛІГИ.

  Жодної мережі: `GIT_SSH_COMMAND=false` в оточенні сервера (як `fixture.mjs`), репо — лише `file://`.
- [ ] **Step 2: Прогнати по одному:**
  ```bash
  python3 "$G" 900 3000 node --test --test-concurrency=1 tests/live/git-sync.test.mjs
  ```
  Потім `gitlab-pull-older`, `connections`, `wizard`, `modules`, `spaces-flows` — кожен окремо.
- [ ] **Step 3: Мутація живого.** Повернути в `refreshGitlab` адресу `/api/gitlab-status` і прибрати з диспетчера сервера `/api/gitlab-status` (тимчасово) → сценарій 2 червоніє. Відновити обидва побайтно.
- [ ] **Step 4: Коміт** — `test(4a): живий сценарій git-sync; gitlab-pull-older на нових адресах`.

---

### Task 9: документи й версія 0.8.0

**Files:**
- Modify: `docs/modules/authoring.md`, `README.md`, `CHANGELOG.md`, `docs/design/spaces-and-modules.md`, `package.json`

- [ ] **Step 1: `docs/modules/authoring.md`.** Розділ «Роль `vcs`» (англійською, як решта файла):
  - ціль `target` (поля, порядок, `{task}`, порожній рядок);
  - функції `status`/`push`/`pull(ctx, target, dst, opts)` з формами результатів;
  - необовʼязкова `validate`;
  - `ctx['cache_dir']` (шлях; теку створює модуль);
  - коди `vcs-*` і коли їх кидати;
  - «транспорт, не модель ітерацій»;
  - свій модуль ролі `vcs` — за довірою 3c.
- [ ] **Step 2: `README.md`:**
  - модуль `git-sync` і роль у таблиці модулів;
  - дорожня карта: етап 4 = 4a–4d (виправити розбіжність із дизайн-документом, де 4 — «компанійні інтеграції», а не плагін Claude Code);
  - рядок про прогони Python-наборів для 0.8.0 — ЛИШЕ з тими версіями Python, на яких контролер реально прогнав.
- [ ] **Step 3: `CHANGELOG.md`.** `## [0.8.0] — <DD.MM.YYYY>` (дата релізу дає контролер) за форматом `[0.7.0]`:
  - **Added:**
    - роль `vcs`, модуль `git-sync`;
    - `/api/vcs-*`;
    - поле «Репозиторій»;
    - секція «Підключень».
  - **Changed:**
    - синк ЛІГИ через модуль;
    - `autosync-off`;
    - тайм-аут git → `offline`.
  - **Removed:** 15 мертвих ключів.
  - **Known limits:**
    - HTTPS без збережених даних;
    - `host_ip` лише `user@host:`;
    - Windows без перевірки;
    - старі `.mirrors` у звичайних просторах не читаються;
    - глобальний `git_autocommit`-push — як був.
- [ ] **Step 4: `docs/design/spaces-and-modules.md`** — статус 4a. **`package.json`** — `"version": "0.8.0"`.
- [ ] **Step 5: Коміт** — `docs(4a): контракт ролі vcs, README, CHANGELOG [0.8.0], версія 0.8.0`.

---

## Після всіх задач (контролер)

1. **Фінальне ревʼю** всієї гілки від `bc857b9` (Sonnet, `git archive`-експорт). Фокус:
   - межа ядро/модуль;
   - безпека перевірок цілі;
   - ЛІГА побайтно;
   - нічого з транспорту не лишилось у `serve.py` (`grep -n "_git(\|ensure_mirror\|_mirror_dir" app/serve.py` порожній).
2. **Повні прогони:**
   - `npm test`;
   - Python-набори на 3.13 і 3.9.6;
   - живі — по одному.
3. **Реліз:**
   - дата в `CHANGELOG`;
   - тег `v0.8.0`, анотований, від neodisa;
   - явний `git push origin <sha>:refs/heads/main` і `git push origin refs/tags/v0.8.0`.
4. **Памʼять:** `project-deai-opensource.md`, рядок 4a.
