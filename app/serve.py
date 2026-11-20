#!/usr/bin/env python3
"""Design Canvas v2 — менеджер итераций макета.

Открываешь инструмент → видишь текущий макет задачи (live из design-work).
Ядро: итерации (замороженные копии), публикация на Vercel со свитчером,
comment-layer с каналами: internal (локально, для Claude) / external (Vercel).
"""
import collections
import contextlib
import errno
import functools
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.request
from html import escape as html_escape, unescape as html_unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse, urlsplit

import pages_model as pm  # чиста модель сторінок ітерації (Task 1)
import spaces  # простори машини: який файл задач діє для запиту (етап 1 Deai 1.0)
import isolation  # закон ізоляції й шви тестів (4d-4b; раніше `implicit.py`)
import task_trash  # кошик задач простору (етап Д, 0.30.0): видалення без стирання, повернення, знищення
import feedback  # відгук (0.23.0): кільце помилок, збирач діагностики, черга відправки
import agents_md  # AGENTS.md простору (етап Е, 0.31.0): блок з шаблону + «Ваше»
import updater  # оновлення інструмента (0.23.0): перевірка тегів у remote, `update.json`, `GET /api/update`
import deai_modules  # вбудовані модулі (етап 2а): хто виконує роль `publish` у просторі запиту
import dashboard  # командний дашборд (4c-1): збирання карток і читання рядків команди через постачальника ролі
import tracker  # статуси задач у трекері (4c-2): ядро ролі `tracker` (ключі, пакети, нормалізація, адаптер ЛІГИ)
import notify  # тиша сповіщень Teams (4c-3): ядро ролі `notify` (нормалізація стану, вигляд каналу, адаптер ЛІГИ)
import tracks  # напрямки простору (4d-1): чисте ядро — правила мітки, адаптер ЛІГИ, читання напрямку задачі
import install_config  # конфіг установки (4c-1: спільний із ядром дашборда й CLI, без імпорту `serve`)
from install_config import legacy_tasks_path, load_legacy_tasks  # noqa: F401 — реекспорт: ними користуються `ops/`, `bin/` і тести
import module_trust  # довіра своїм модулям простору (етап 3c): мова вікна довіри, шов `DEAI_TRUST_CONFIRM`
from task_state import task_state  # легкий стан задачі: спільний із пушером реєстру
# Розбір подій прогресу зʼємки. Формат рядка — контракт МІЖ процесами:
# пише bin/shots-progress.mjs, читає цей модуль (звірку маркера тримає
# окремий тест у tests/test_shoot_progress.py).
from shoot_progress import ShootProgress, parse_progress_line
# Спільний лист писарів стану. Той самий лок і той самий суфікс, що бачить
# pages_model — два незалежні локи одне одного не бачили б (див. atomic_io).
from atomic_io import TMP_SUFFIX, WRITE_LOCK, atomic_write_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, 'app')
# Час старту ЦЬОГО процесу. Обгортка превʼю не лежить готовим файлом — її збирає
# сам сервер у момент публікації (`preview_index_html`), тому правка в app/*.py
# доїжджає на зовнішній URL лише після ДВОХ кроків: перезапуск канваса + ПОВТОРНА
# публікація. Другий крок легко пропустити: 25.08.2026 на Vercel лишалась стара
# обгортка, хоча джерело на диску вже мало нову. Мітка — база для попередження.
SERVER_STARTED_AT = time.time()
NAME_RE = re.compile(r'^[\w-]+$')
# Ключ кадру: сама сторінка (`poshuk`) АБО сторінка зі станом (`poshuk~30d36f19`),
# і будь-яке з двох — з шириною суфіксом (`poshuk~30d36f19@390`).
# Хвіст стану рахує `shotKey` у app/flow-model.js — рівно 8 шістнадцяткових цифр;
# суфікс ширини — `frameKey` у app/viewport.js (типова ширина суфікса НЕ додає).
# Окреме правило, а не послаблений NAME_RE: ані `~`, ані `@` не входять у `\w`,
# тому без них кадр лежав би на диску, а полотно отримувало б 400 і малювало
# «немає знімка» — тиха неправда рівно на шві клієнта й сервера. Ширина тут це
# ЦИФРИ (2–4), тож ані '/' ані '..' крізь неї не пролізуть; слеш і `..` замкнені
# так само, як і були, а realpath нижче лишається другим замком.
SHOT_RE = re.compile(r'^[\w-]+(~[0-9a-f]{8})?(@[1-9]\d{1,3})?$')
# Межі ширини прогону — ті самі MIN_W/MAX_W, що в app/viewport.js і bin/shoot.mjs.
# Дублікат числами свідомий: Python сюди JS-модуль не імпортує, а розійтися межі
# можуть лише в бік «сервер пустив те, що дитина відкине гучно» — це видно одразу.
MIN_VP, MAX_VP = 240, 3840
SHOOT_TIMEOUT_S = 900   # 15 хвилин: стеля на зʼємку однієї ітерації
HARD_KILL_S = 15        # SIGTERM → стільки чекаємо на добровільний вихід → SIGKILL

# Активні зʼємки: (задача, ітерація) →
# {'proc': Popen | None, 'progress': ShootProgress, 'hard': Timer | None}.
# `proc: None` — заглушка на час fork+exec (ключ уже взято, процесу ще нема),
# `hard` — озброєний SIGKILL після SIGTERM. Перевірка свіжості (`--check`) сюди
# НЕ пишеться взагалі: вона браузера не піднімає й на ту саму теку не претендує.
# У ПАМʼЯТІ процесу, під замком: автостарт робить паралельну зʼємку звичайною
# справою (два входи в «Огляд», дві вкладки, дизайнер плюс Stop-хук автосинку), а
# прапорець `shooting` у канвасі живе в ОДНІЙ вкладці й цього не ловить.
# ⚠️ Замок не переживає другого ПРОЦЕСУ серверу (дві копії інструмента на різних
# портах) — це лишається TD-6 у звуженому вигляді. Обіцяти файловий замок, якого
# немає, гірше за відсутність замка.
_SHOOTS = {}
_SHOOTS_LOCK = threading.Lock()

# Звірка ревізії пакета тюнера і запис — одна дія, а сервер багатопотоковий:
# без замка запис Клода міг лягти МІЖ звіркою і записом вкладки, і `base_rev`
# пропустив би рівно той випадок, заради якого його заведено. Та сама межа, що
# в `_SHOOTS_LOCK`: другий процес сервера замок не бачить.
_TUNER_LOCK = threading.Lock()

# Кожен маршрут, який обробляє наш do_GET, МУСИТЬ бути тут. Усе, чого в цьому переліку
# немає, фолбек у Routed.do_GET намагається віддати як статику з теки ітерації,
# визначеної з Referer — і тоді власні перевірки обробника не діють. Саме розбіжність
# між цим переліком і ланцюгом if у do_GET дала перехоплення /shot.
HANDLED_PREFIXES = ('/app', '/api/', '/commented', '/comments', '/it-assets', '/shot', '/published/')


# Служебное, что НЕ копируется в итерации/публикацию из папки задачи
SKIP = {'iterations', 'iterations.json', 'publish', 'node_modules', '.git',
        '.vercel', '.DS_Store'}

# Стан публікації, який їде колегам разом з макетом (див. gitlab_sync/gitlab_pull).
# Крапка на початку — свідомо: copy_mockup і _mockup_files ігнорують dot-файли,
# тому файл не потрапляє ні в хеш макета, ні в чужу ітерацію після Підтягнути.
STATE_FILE = '.canvas-state.json'

NODE_MISSING_HINT = (
    'Node/npx не знайдено — опублікувати на Vercel з цієї машини не вийде.\n'
    '1) Встанови Node LTS: https://nodejs.org (або `brew install node`).\n'
    '2) Один раз авторизуйся: `npx vercel login`.\n'
    '3) Перезапусти інструмент: ./stop.command і ./start.command.\n'
    'Якщо Node стоїть через nvm — запускай ./start.command з ТЕРМІНАЛА, '
    'а не подвійним кліком з Finder (див. _node_bin).\n'
    'Макет уже зібрано локально — можна попросити Андрія опублікувати.')


def _ssl_context():
    """Проверенный TLS: certifi, если есть (фикс macOS python.org)."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


#: Правила, які інструмент тримає в `.gitignore` ТЕКИ ЗАДАЧІ.
#:
#: `git_autocommit` нижче робить `git add -A`, тож усе, чого тут немає, лягає в
#: історію макета — а за налаштованим remote і пушиться колегам.
#:
#: `*.tmp` — осиротілий недописаний файл `atomic_write_json` (той самий клас,
#: що `*.bak`). `publish/` — зібрана статика. `comments-for-ai*` — вивантаження
#: коментарів. `.pages.lock` — порожній службовий файл міжпроцесного лока
#: `pages_model.pages_lock` (лежить у кожній теці ітерації, куди хтось писав
#: дерево); без правила він потрапив би в історію макета й до колег.
#:
#: ⛔ `.dc-tuner.json` і `.dc-local-comments.json` — РОБОЧЕ ЛИСТУВАННЯ дизайнера
#: з Клодом, а не частина макета: пакет рекомендацій тюнера (з полем `note`
#: вільним текстом) і локальні пін-коментарі. Рішення власника 18.09.2026: не
#: пушити ні те, ні те. Колезі вони шум, а записка тюнера писалась не для
#: чужих очей. Обидва лежать у КОРЕНІ теки задачі, тобто рівно там, куди
#: дивиться `git add -A`.
TASK_IGNORE = ('publish/', '*.bak', '*.tmp', '.DS_Store', 'comments-for-ai*',
               '.vercel/', '.dc-tuner.json', '.dc-local-comments.json',
               '.pages.lock')


def ensure_task_gitignore(task_dir):
    """Дописати в `.gitignore` теки задачі правила, яких там ще немає.

    ⛔ ДОПИСАТИ, А НЕ ПОСІЯТИ ПРИ `git init`. Так було до 18.09.2026, і це
    покривало рівно нові теки: у кожної вже заведеної задачі `.git` існує,
    отже нове правило не доїхало б туди НІКОЛИ. А знахідка саме про вже
    заведені — файли лягають в історію щодня.

    Ідемпотентно й лише додає: чужі рядки (скажімо, `refs/` дизайнера)
    лишаються. Зворотний бік названий чесно: правило, свідомо ВИДАЛЕНЕ руками,
    наступний автокоміт поверне. Це правила інструмента, і він за них
    відповідає; кому треба возити `publish/` у репо макета — це розмова, а не
    локальна правка.

    ⚠️ МЕЖА, і вона тут головна: `.gitignore` не знімає з обліку те, що вже
    ВІДСТЕЖУЄТЬСЯ. У теках, де `.dc-local-comments.json` уже потрапив у
    історію (на 18.09.2026 — сім задач), він і далі комітиться, і вивести його
    може тільки `git rm --cached` — тобто рішення власника, а не тиха правка
    інструмента. Не написати цього тут означало б лишити запис, який
    ЗАСПОКОЮЄ, не даючи захисту, — той самий клас, що на `check_anon_write_scope`.

    @returns список дописаних правил (порожній — усе вже було).
    """
    gi = os.path.join(task_dir, '.gitignore')
    text = ''
    if os.path.isfile(gi):
        with open(gi, encoding='utf-8') as f:
            text = f.read()
    have = {ln.strip() for ln in text.splitlines()}
    missing = [p for p in TASK_IGNORE if p not in have]
    if not missing:
        return []
    with open(gi, 'a', encoding='utf-8') as f:
        if text and not text.endswith('\n'):
            f.write('\n')
        f.write('\n'.join(missing) + '\n')
    return missing


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


def git_autocommit(task_dir, msg, push=None):
    """Автосохранение папки задачи в git — скриптом, без участия AI.
    init при первом вызове; push best-effort, если настроен remote (GitLab).

    Простір без схеми ЛІГИ (`vcs_outbound`) коміт робить, а `git push` — НІ: його
    папка може мати `origin` (клон чужого репо, рука дизайнера), але зовнішніх викликів із такого
    простору не буває. `push` — явне рішення викликача (`True`/`False`); `None` — за простором.

    ⚠️ Питаємо простір ЛІНИВО й лише коли `origin` є: автокоміт без `origin` (кожна нова задача,
    кожна правка сторінки) не читає реєстр просторів. Реєстр, що не читається, — «не пушимо»
    (`_vcs_outbound_here`): коміт уже вийшов, і 503 після нього був би гіршим за пропущений пуш."""
    try:
        if not os.path.isdir(os.path.join(task_dir, '.git')):
            subprocess.run(['git', 'init', '-q'], cwd=task_dir, check=True, timeout=20)
        # ПЕРЕД `add -A` і на КОЖНОМУ виклику, не лише при `init`: див. докстрінг.
        ensure_task_gitignore(task_dir)
        subprocess.run(['git', 'add', '-A'], cwd=task_dir, check=True, timeout=30)
        subprocess.run(['git', 'commit', '-q', '-m', msg],
                       cwd=task_dir, capture_output=True, text=True, timeout=30)
        h = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'],
                           cwd=task_dir, capture_output=True, text=True, timeout=10)
        sha = h.stdout.strip() if h.returncode == 0 else None
        pushed = False
        rem = subprocess.run(['git', 'remote'], cwd=task_dir,
                             capture_output=True, text=True, timeout=10)
        if rem.returncode == 0 and rem.stdout.strip():
            if push is None:
                push = _vcs_outbound_here()
            if push:
                p = subprocess.run(['git', 'push', '-q'], cwd=task_dir,
                                   capture_output=True, text=True, timeout=60)
                pushed = p.returncode == 0
        return {'sha': sha, 'pushed': pushed}
    except (OSError, subprocess.SubprocessError):
        return {'sha': None, 'pushed': False}


def _node_bin(name='npx'):
    """Абсолютний шлях до npx/node або None.

    ⚠️ Чому не досить голого `subprocess.run(['npx', …])`: сервер піднімається
    через `nohup python3 app/serve.py` зі start.command. Якщо .command запустили
    подвійним кліком з Finder, zsh стартує як non-interactive login — читає
    .zprofile, але НЕ .zshrc, а саме туди nvm/volta прописують PATH. Через це
    деплой падав з `[Errno 2] No such file or directory: 'npx'`, хоча в
    терміналі npx працює (інцидент у дизайнера, 03.08.2026).

    Порядок: PATH процесу → типові місця встановлення → login+interactive zsh.
    """
    p = shutil.which(name)
    if p:
        return p
    cands = [f'/opt/homebrew/bin/{name}',            # brew, Apple Silicon
             f'/usr/local/bin/{name}',               # brew Intel / інсталятор nodejs.org
             os.path.expanduser(f'~/.volta/bin/{name}')]
    nvm = os.path.expanduser('~/.nvm/versions/node')
    if os.path.isdir(nvm):
        def _ver(d):  # числове сортування, щоб v20 не програвало v9
            return [int(x) if x.isdigit() else 0 for x in d.lstrip('v').split('.')]
        try:
            for d in sorted(os.listdir(nvm), key=_ver, reverse=True):
                cands.append(os.path.join(nvm, d, 'bin', name))
        except OSError:
            pass
    for c in cands:
        if os.access(c, os.X_OK):
            return c
    try:  # крайній засіб: -lic читає ~/.zshrc, де живе ініціалізація nvm
        r = subprocess.run(['zsh', '-lic', f'command -v {name}'],
                           capture_output=True, text=True, timeout=15)
        lines = [x.strip() for x in (r.stdout or '').splitlines() if x.strip()]
        if r.returncode == 0 and lines and os.access(lines[-1], os.X_OK):
            return lines[-1]
    except (OSError, subprocess.SubprocessError):
        pass
    return None


# 4b-1: модулі (режим `cli` у `vercel-publish`) шукають `npx` так само, як ядро (див. докстрінг вище). Лише реєстрація:
# `_node_bin` не кличеться при імпорті (login-shell повільний) — тільки коли модуль сам попросить `ctx['find_tool']`.
deai_modules.set_tool_finder(_node_bin)


def _file_hash(path):
    import hashlib
    try:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


def tasks_path():
    """Файл задач, що діє для ЦЬОГО запиту (потоку). Звідси `load_tasks()`/`save_tasks()`
    автоматично працюють з файлом простору запиту — у `cfg` нічого не додається, файл лишається
    байт-у-байт сумісним зі старим.

    Звідки файл (спека 2026-10-13-deai-spaces-design.md, «Звідки старий файл…»):

    | оточення                           | шар просторів | файл                                   |
    |------------------------------------|---------------|----------------------------------------|
    | лише `DC_TASKS_FILE` (усі тести)   | ВИМКНЕНО      | `DC_TASKS_FILE`, реєстр не читається   |
    | `DEAI_HOME` (+ `DC_TASKS_FILE`)    | увімкнено     | файл активного простору; старий файл — |
    |                                    |               | простір `legacy` (`DC_TASKS_FILE` або  |
    |                                    |               | `ROOT/tasks.json`)                     |
    | нічого (робота)                    | увімкнено     | те саме, реєстр у `~/.deai`            |

    Активний простір — той, що фіксує вхід запиту (`_take_task`): простір названої задачі або
    поточний машини; поза запитом (CLI) — поточний машини. Просторів нема — `NoTask`; але коли
    старий файл є й не читається (міграція його не взяла), це `SpaceUnavailable(<файл>)`:
    зіпсований `tasks.json` не сміє виглядати як чиста машина.

    DC_TASKS_FILE дає тестам (і будь-кому) підмінити файл, не торкаючись живого.
    До 03.08.2026 перевизначення не було, і tests/test_serve.py писав фікстуру
    ПОВЕРХ робочого tasks.json. Наслідки: тестові рядки `fixture`/`demo2` поїхали
    в прод-Supabase на командний дашборд, а падіння тесту між setUp і tearDown
    лишало робочий конфіг фікстурою. Взірець — DC_MIRRORS_DIR нижче.

    ⚠️ Оточення читається на КОЖЕН виклик (не кешується в константу): інакше
    порядок імпорту serve відносно виставлення змінної став би значущим.

    ⚠️ Може мігрувати (писати реєстр, беручи `WRITE_LOCK`): ніколи не кликати під цим локом.
    """
    if not spaces.layer_on():
        return os.environ['DC_TASKS_FILE']
    try:
        return spaces.active_tasks_file()
    except spaces.NoTask:
        # Просторів нема, але старий файл є й не читається (міграція його не взяла): це не
        # «чиста машина» — 503 `space-unavailable` з назвою файла замість 404 `no-task`/привітання.
        raise_if_legacy_unreadable()
        raise


def raise_if_legacy_unreadable(reg=None):
    """`SpaceUnavailable(<старий файл>)`, коли `spaces.legacy_unreadable(reg)` каже, що старий
    `tasks.json` є, а простору з нього нема, бо його не прочитати; інакше нічого не робить.
    Шар вимкнено — завжди нічого (поведінка як до просторів)."""
    bad = spaces.legacy_unreadable(reg)
    if bad:
        raise SpaceUnavailable(bad)


class SpaceUnavailable(OSError, ValueError):
    """Файл задач простору не прочитати чи він битий (нема, не JSON, не обʼєкт). Одночасно
    `OSError` і `ValueError` — як `io.UnsupportedOperation`: наявні `except (OSError,
    ValueError)` у викликачів деградують чесно, а центральний обробник віддає 503
    `space-unavailable` замість обриву зʼєднання. `path` — файл, який не вдалось прочитати."""

    def __init__(self, path):
        super().__init__(f'tasks file of the space is unreadable: {path}')
        self.path = path


def load_tasks():
    p = tasks_path()
    if not spaces.layer_on():
        with open(p, encoding='utf-8') as f:     # шар вимкнено — рівно як було
            return json.load(f)
    try:
        with open(p, encoding='utf-8') as f:
            cfg = json.load(f)
    except (OSError, ValueError, RecursionError) as e:
        # RecursionError — глибоко вкладений JSON: не ValueError, і зʼєднання рвалось би без відповіді.
        raise SpaceUnavailable(p) from e
    if not spaces.valid_tasks_cfg(cfg):
        # `[]`, `5`, `{"tasks": []}`, `{"tasks": {"x": 5}}`: кожен викликач далі чекає обʼєкт задач з
        # обʼєктів і падав би `AttributeError`-ом посеред відповіді (зʼєднання рветься без слова).
        raise SpaceUnavailable(p)
    return cfg


# `NoTask`/`AmbiguousTask` — з `spaces`, щоб серверний код і CLI ловили одні й ті самі типи.
NoTask = spaces.NoTask
AmbiguousTask = spaces.AmbiguousTask


class UnknownTask(LookupError):
    pass


class TaskNotHere(UnknownTask):
    """Задача Є в реєстрі, але на ЦІЙ машині її теки нема (`/api/tasks` позначає
    такі `missing`): реєстр їде в git, теки — ні. Підклас `UnknownTask`, тож
    кожен, хто вміє відмовити невідомій задачі, відмовить і цій; а хто хоче
    розрізнити причину (CLI, `_take_task`), ловить її ПЕРЕД батьком."""


def task_for(cfg, tid=None):
    """(id, задача): названа явно (заголовок `X-Canvas-Task`, префікс `/t/<id>/`,
    `--task`) або поточна машини.

    fb-07102026-e627c2: `current` один на машину, і паралельна сесія Claude, що
    його перемкнула, відправляла синк і публікацію цієї сесії в ЧУЖУ задачу — без
    жодного сигналу. Невідома назва — `UnknownTask`, а НЕ тихий відкат на поточну:
    інакше помилка в id знову била б у чужу задачу. Рядок мусить бути ключем
    `tasks` дослівно, тож `../x` чи `5` задачею не є й теку диска так не відкрити.

    Названа задача ще й мусить БУТИ на цій машині (`TaskNotHere`): запис без `dir`
    (лише реєстр) валив обробник `KeyError`-ом і рвав зʼєднання, а запис із `dir`,
    якої нема на диску, пропускав далі — і `POST /t/gone/api/iteration` САМ
    створював дерево, а CLI казали «нова/порожня задача». Поточна (`tid is None`)
    — як було: це «задача, в якій працює машина», і її стан не перевіряємо.

    Поточної нема (новий порожній простір, `current` відсутній / `null` / застарілий) —
    `NoTask`, а не `KeyError`: центральний обробник відповідає 404 `no-task`, CLI — повідомленням.
    `NoTask.space` — простір запиту (шар вимкнено — `None`: простору там нема)."""
    if tid is None:
        cur, tasks = cfg.get('current'), cfg.get('tasks')
        if not isinstance(tasks, dict) or not isinstance(cur, str) or cur not in tasks:
            raise NoTask((spaces.request_space_id() if spaces.layer_on() else None) or None)
        return cur, tasks[cur]
    if not isinstance(tid, str) or tid not in cfg['tasks']:
        raise UnknownTask(tid)
    task = cfg['tasks'][tid]
    d = task.get('dir')
    if not isinstance(d, str) or not os.path.isdir(d):
        raise TaskNotHere(tid)
    return tid, task


def task_anywhere(tid=None, load=None):
    """(id, задача) для CLI (`bin/state.py`, `bin/inbox.py`): названа `tid` — у БУДЬ-ЯКОМУ
    просторі, `None` — поточна задача поточного простору. Простір фіксується на потоці
    (`spaces.set_request_space`): далі `load_tasks()`/`save_tasks()` та інтеграції
    працюють саме з ним. Хто викликає, мусить у `finally` зробити
    `spaces.clear_request_space()` (CLI-обгортки `main()` так і роблять).

    Невідома задача — `UnknownTask`; дубль в кількох просторах — `AmbiguousTask`; просторів чи
    поточної задачі нема — `NoTask`; файл простору не прочитати — `SpaceUnavailable` (і старий
    файл, з якого простір не мігровано, бо він не читається, — теж, замість «невідомої»/«просторів
    нема»); реєстр — `spaces.SpacesError`.

    `load` — чим читати конфіг (типово `load_tasks`): CLI передає СВІЙ імпорт `load_tasks`, і
    тести-пастки (`test_inbox.Help` патчить `inbox.load_tasks`, щоб довести «до розбору
    аргументів задач не читаємо») лишаються здатними впасти."""
    if tid is not None:
        sp = spaces.find_task(tid)
        if sp is None:
            raise_if_legacy_unreadable()    # задача могла лежати в старому файлі, який не читається
            raise UnknownTask(tid)
        spaces.set_request_space(sp['id'])
    else:
        spaces.set_request_space(spaces.current_id() or '')
    return task_for((load or load_tasks)(), tid)


def save_tasks(cfg):
    # WRITE_LOCK склеює копію в .bak і сам запис в одну дію — інакше два запити
    # знімають копію з ОДНІЄЇ версії, і .bak відстає на два кроки. Межі лока
    # (він не рятує від read-modify-write) розписані в atomic_io.
    # ⚠️ `tasks_path()` — ПОЗА локом: перша ж його відповідь може мігрувати реєстр, а міграція
    # сама бере `WRITE_LOCK` (він не реентерабельний) — під ним це був би дедлок.
    p = tasks_path()
    with WRITE_LOCK:
        shutil.copy2(p, p + '.bak')   # про людську помилку, не про краш — лишаємо
        atomic_write_json(p, cfg)


def load_meta(task):
    p = os.path.join(task['dir'], 'iterations.json')
    if os.path.isfile(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    return {'iterations': [], 'publish_url': None}


def task_iterations(task):
    return load_meta(task).get('iterations', [])


def save_meta(task, meta):
    p = os.path.join(task['dir'], 'iterations.json')
    with WRITE_LOCK:
        if os.path.isfile(p):
            shutil.copy2(p, p + '.bak')
        atomic_write_json(p, meta)


def _is_tool_junk(name):
    """Службове інструмента у КОРЕНІ макета. Спільний предикат copy_mockup і
    _mockup_files — доти вони збігалися лише на слово в докстрінгу.

    ⚠️ Хто відсіює `.tmp`, а хто ні — точний перелік, без «на всіх рівнях»:
    ВІДСІЮЮТЬ — відбиток (`_mockup_files`), експорт колегам (`copy_mockup`),
    штамп зʼємки (`bin/shots-stamp.mjs`) і `.gitignore`, який сіє
    `git_autocommit`. НЕ ВІДСІЮЄ — `_pages_from_iterations`: він переносить
    вміст старих ітерацій сирим listdir+copytree і взагалі не знає предиката.
    Осиротілий tmp туди потрапить; це відома межа, а не недогляд, бо привести
    той шлях до предиката — окрема правка з власним ризиком для міграції.
    """
    return (name in SKIP or name.endswith(('.py', '.bak', '.zip', '.patch', TMP_SUFFIX))
            or name.startswith(('comments-for-ai', '.')))


def copy_mockup(src_dir, dst_dir):
    """Копия макета без служебного (py-скрипты не тянем)."""
    os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        if _is_tool_junk(name):
            continue
        s, d = os.path.join(src_dir, name), os.path.join(dst_dir, name)
        if os.path.isdir(s):
            # ⚠️ У ПІДТЕКАХ відсіюємо РІВНО .tmp, а не весь предикат вище. Це
            # свідома асиметрія: підтеки завжди їхали цілком, і розширити фільтр
            # означало б тихо перестати возити файли, які возяться сьогодні
            # (напр. shared/notes.py). Прибираємо лише той клас, який породила
            # ця сама задача.
            shutil.copytree(s, d, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('*' + TMP_SUFFIX))
        else:
            shutil.copy2(s, d)


# ---------- Синхронізація з git: роль `vcs` (T-18; етап 4a) ----------
# Модель: локальна папка задачі = робоча копія (tool-стан + свій git). Синхронізація = експорт ЧИСТОГО макета
# (`copy_mockup`) у тимчасову теку й `push` модуля ролі `vcs`; дзеркало (клон спільного репо) веде модуль, не ядро.
#
# Транспорт — модуль `git-sync` (`app/modules/git-sync/server.py`): дзеркало, fetch, push, pull, «відстає/попереду».
# Ядро вирішує, ЩО відправити й ЯК прийняти: чистий макет, `.canvas-state.json`, авторство, форки, ітерації. Старі імена
# (`gitlab_status`/`gitlab_sync`/`gitlab_pull`/`autosync`) лишаються з тими самими формами відповідей до 4d: `gl` у них —
# ЦІЛЬ ролі (`vcs_target`), постачальника вони знаходять самі (`vcs=None`) або беруть готового від маршруту. Ключ `gitlab`
# в `iterations.json` — внутрішня назва стану синку (сумісність тек задач, які читає `task_state.py`).


def gitlab_cfg(task):
    """Git-sync конфиг задачи или None. Лише поля самої задачі: спільні ключ і IP — налаштування запису `git-sync` (4d-4b: корінь `tasks.json` не читаємо)."""
    gl = task.get('gitlab')
    if not gl or not gl.get('repo') or not gl.get('path'):
        return None
    key = gl.get('ssh_key')
    return {'repo': gl['repo'], 'path': gl['path'].strip('/'),
            'ssh_key': os.path.expanduser(key) if key else None,
            'branch': gl.get('branch', 'main'),
            # Адреса хоста для повтору при збої резолвера (модуль `git-sync`): з конфіга задачі; немає — з налаштувань модуля (їх бере сам
            # модуль), а ні — повтору не буде, і це правильніше за вигадану адресу.
            'host_ip': gl.get('host_ip')}


def gitlab_web(gl):
    """SSH-репо → веб-URL історії коммітів по нашому шляху (для лінка в UI)."""
    m = re.match(r'git@([^:]+):(.+?)(?:\.git)?$', gl['repo'])
    if not m:
        return None
    return f'https://{m.group(1)}/{m.group(2)}/-/commits/{gl["branch"]}/{gl["path"]}'


VCS_MODULE = deai_modules.VCS_MODULE          # одне джерело id: його читає й предикат `deai_modules.compat_view`

#: Userinfo адреси (`://TOKEN@`, `://user:pass@`) — те саме правило, що `_USERINFO`/`_mask` модуля `git-sync` (нутрощі модуля
#: не імпортуємо): до ОСТАННЬОГО `@` перед першим `/`, тож `p@ss` у паролі теж.
_USERINFO = re.compile(r'(://)[^/\s]*@')


def _mask_repo(text):
    """Текст без userinfo адреси: `https://TOKEN@host/o/r` → `https://***@host/o/r`. Усе, що ядро віддає назовні й що
    несе адресу репо (`remote`, `web`, тексти помилок, рядок Stop-хука), — лише через цю функцію: токен у позиції
    користувача `validate` модуля від імені не відрізнить, а пароль в адресі лише відхиляє. Не-рядок — як є."""
    return _USERINFO.sub(r'\1***@', text) if isinstance(text, str) else text


class VcsError(OSError):
    """Відмова ролі `vcs` для ядра. `OSError` свідомо: на ньому стоять маршрути синку, автосинк («офлайн» — тихо) і
    бутстрап задачі («не вийшло — стартовий макет»). `code` — `vcs-*` модуля або код каркаса (`space-json-unreadable`,
    `module-error`…). Повідомлення очищене від userinfo адреси ТУТ, при створенні: текст помилки, що побудувало ядро чи
    свій модуль, не донесе токена до відповіді маршруту, автосинку й рядка Stop-хука."""

    def __init__(self, code, message=''):
        super().__init__(_mask_repo(message) or code)
        self.code = code


def _mirrors_base():
    """Тека дзеркал простору ЛІГА: `DC_MIRRORS_DIR` (тести, живі прогони) або `<ROOT>/.mirrors`, як у 0.7.0."""
    return os.environ.get('DC_MIRRORS_DIR') or os.path.join(ROOT, '.mirrors')


def _vcs_legacy_ctx():
    """`ctx` ізольованого шляху `git-sync` ЛІГИ (запис `shared_state` в ізольованому прогоні, 4d-3b; запасного постачальника більше нема):
    фіксовані налаштування, без `space.json`. Дзеркала — старі
    теки 0.7.0 (`mirror_flat`: дизайнери не перегортають великі репо, а незапушені коміти старих дзеркал не осиротіють),
    автосинк увімкнено, як і було. Ключ і IP сервера несе ціль (`gitlab_cfg`), не налаштування.

    ⛔ НЕ `deai_modules.module_ctx()`: `cache_dir` каркаса лежить під `spaces.home()`, а при вимкненому шарі це справжній
    `~/.deai` машини — дзеркала ЛІГИ опинились би там (ревʼю Task 3)."""
    return {'space': {'id': spaces.request_space_id() or '', 'path': ''},
            'settings': {'branch': 'main', 'path': 'mockup/{task}', 'autosync': True},
            'secrets': {}, 'folder_ok': lambda folder: (False, 'bad-folder'),
            'ModuleError': deai_modules.ModuleError,
            # `find_tool` тут не потрібен: `git-sync` кличе лише `git`, а `ctx['find_tool']` (npx/node) — для модуля Vercel (4b-1)
            **_flat_mirror_overlay()}


def _flat_mirror_overlay():
    """Накладка плоских дзеркал 0.7.0: `mirror_flat` і `cache_dir = _mirrors_base()`. ЄДИНА копія: її кладуть і неявний шлях
    (`_vcs_legacy_ctx`), і явний запис `git-sync` із `compat == "design-canvas"` (`vcs_provider`). Модуль не знає ні `ROOT`, ні
    `DC_MIRRORS_DIR`, тож друга копія в ньому розсинхронізувалась би."""
    return {'mirror_flat': True, 'cache_dir': _mirrors_base()}


def vcs_legacy_texts(prov, space):
    """ЄДИНИЙ предикат «легасі-тексти» ЛІГИ (тема коміту «design-canvas: sync», «GitLab», «репозиторію», автокоміт, плоскі дзеркала):
    вбудований `git-sync` із `compat == "design-canvas"` у `space.json` простору (запасного неявного постачальника більше нема, 4d-4b).

    ⛔ ЛІГА — запис реєстру, а не тип постачальника (урок 4d-3a): після міграції ЛІГА веде явний `Module`, а тексти лишаються
    ті самі. ⛔ Лише вбудований І саме `git-sync` (Поправка 3): свій модуль міг оголосити власне `compat` з іншим змістом.
    Споживачі НЕ перевіряють тип постачальника самі — читають третій елемент `vcs_provider()` (`TextPredicateGuard`).
    ТОТАЛЬНА: нечитабельний `space.json` — `False`, не виняток (`compat_of`)."""
    return (isinstance(prov, deai_modules.Module) and getattr(prov, 'origin', 'builtin') == 'builtin'
            and prov.id == deai_modules.VCS_MODULE
            and deai_modules.compat_of(space, prov.id) == deai_modules.COMPAT_DESIGN_CANVAS)


def _frame_reason(e):
    """Текст відмови каркаса (`ModuleError`/`SpacesError`) для `VcsError`: СПЕРШУ маска адреси, ПОТІМ обрізання до 300. Навпаки
    адреса з токеном, що стартує за кілька символів до межі, лишала б `https://ghp_SEC` без `@` — маска такого вже не впізнає,
    а конструктор `VcsError` бачить лише обрізане. (`ModuleError` ріже текст сам, ще в конструкторі, — тут це вже не виправити.)"""
    return _mask_repo(str(getattr(e, 'message', None) or e))[:300]


def vcs_provider():
    """Хто синкає в просторі запиту: `None` (ролі нема) або `(module, ctx, legacy)`. Відмова — `VcsError` (нечитабельний
    `space.json`, свій модуль «на папері», `git-sync` не завантажився), ніколи не 500."""
    try:
        prov = deai_modules.provider('vcs')
    except (deai_modules.ModuleError, spaces.SpacesError) as e:
        raise VcsError(getattr(e, 'code', 'vcs-error'), _frame_reason(e)) from None
    except Exception as e:  # noqa: BLE001 — каталог модулів зламався (раніше це ловив неявний шлях ЛІГИ): збій = vcs-error, не 500
        raise VcsError('vcs-error', f'module catalog: {type(e).__name__}') from None
    if prov is None:
        return None
    try:
        space = spaces.active_space()
        legacy = vcs_legacy_texts(prov, space)                       # ОДИН раз: третій елемент для всіх споживачів текстів
        if _builtin_shared(space, prov) and isolation.isolated():
            # ⛔ Закон ізоляції (4d-3b, спека §5): запис `shared_state` в ізольованому прогоні (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`)
            # будує `ctx` ізольованого шляху — налаштування запису не читаються, дзеркала плоскі в `DC_MIRRORS_DIR`. Місце ізоляції
            # одне: ця функція і `comments_route`. Тексти — за `compat` (предикат вище), не за ізоляцією.
            return prov, _vcs_legacy_ctx(), legacy
        ctx = deai_modules.module_ctx(space, prov)
        if legacy:                                                   # `compat == "design-canvas"` = поведінка ЛІГИ 0.7.0
            ctx = {**ctx, **_flat_mirror_overlay()}
        return prov, ctx, legacy
    except (deai_modules.ModuleError, spaces.SpacesError) as e:
        raise VcsError(getattr(e, 'code', 'vcs-error'), _frame_reason(e)) from None


def _vcs_str(v):
    return isinstance(v, str) and v.strip() != ''


def _vcs_ssh(*own):
    """`{ssh_key, host_ip}` цілі — лише у просторі з інтеграціями (ЛІГА). Правило ОДНЕ для кожного шляху цілі й окремо для
    кожного з двох полів: перше непорожнє серед `own` (словники самої задачі: `vcs{}`, далі `gitlab{}`) > налаштування модуля
    (поле тоді НЕ кладемо в ціль — модуль бере своє). Кореня `tasks.json` більше нема (4d-4b): його ключ і IP — налаштування запису `git-sync`."""
    if not _vcs_outbound_here():
        return {}
    out = {}
    for name in ('ssh_key', 'host_ip'):
        val = next((d[name] for d in own if isinstance(d, dict) and d.get(name)), None)
        if val is None:
            continue                                         # поля нема в задачі: модуль візьме своє з налаштувань
        if isinstance(val, str) and val:
            out[name] = os.path.expanduser(val) if name == 'ssh_key' else val
    return out


def vcs_target(tid, task, settings):
    """Ціль задачі для модуля або `None` (задачу не налаштовано). Порядок (спека 4a, «Роль `vcs`»): поле задачі
    `vcs{repo, path?, branch?}` (лише з непорожнім `repo`) → старе `gitlab{…}` (лише простір з інтеграціями; як
    `gitlab_cfg` 0.7.0: без `repo` чи `path` — не налаштована) → налаштування модуля. `{task}` у `path` — id задачі;
    `path` без `/` по краях.

    ⛔ `repo` кладемо ОБРІЗАНИМ: `validate` модуля відкидає `repo != repo.strip()`, тож пробіл із форми чи ручної правки
    `tasks.json` інакше давав би `vcs-bad-target` замість синку.

    Ключ і IP (`_vcs_ssh`): у просторі з інтеграціями — лише своє поле задачі (`vcs{}`, далі `gitlab{}`); нема — ціль їх не несе, і
    модуль бере налаштування свого запису. Кореня `tasks.json` у ланцюгу нема (4d-4b). У звичайному просторі ціль ключа й IP не несе."""
    def tpath(p):
        return str(p).replace('{task}', tid).strip('/')
    v = task.get('vcs')
    if isinstance(v, dict) and _vcs_str(v.get('repo')):
        return {'repo': v['repo'].strip(), 'task': tid,
                'path': tpath(v['path'] if _vcs_str(v.get('path')) else settings.get('path') or 'mockup/{task}'),
                'branch': (v['branch'] if _vcs_str(v.get('branch')) else settings.get('branch') or 'main').strip(),
                **_vcs_ssh(v, task.get('gitlab'))}
    if task.get('gitlab') and _vcs_outbound_here():
        gl = gitlab_cfg(task)
        if gl is None:
            return None
        # Ключі `gl` перезаписуємо НА МІСЦІ (порядок ключів цілі — як у 0.7.0) за правилом `_vcs_ssh`.
        gl = {**gl, 'ssh_key': None, 'host_ip': None, **_vcs_ssh(task['gitlab'])}
        return {**{k: x for k, x in gl.items() if x}, 'task': tid, 'repo': str(gl['repo']).strip()}
    if _vcs_str(settings.get('repo')):
        return {'repo': settings['repo'].strip(), 'task': tid,
                'path': tpath(settings.get('path') or 'mockup/{task}'),
                'branch': (settings.get('branch') or 'main').strip()}
    return None


def vcs_task(tid, task):
    """`None` — у просторі запиту нема ролі `vcs`; інакше `(module, ctx, legacy, target | None)`. Відмова — `VcsError`."""
    p = vcs_provider()
    return None if p is None else (*p, vcs_target(tid, task, p[1].get('settings') or {}))


#: Форма результату функцій ролі, які кличе ядро. Свій модуль (довіра 3c) може повернути що завгодно: `None` чи рядок
#: замість обʼєкта — це `module-error` тут, а не `AttributeError`/`TypeError` далі (маршрути ловлять лише `OSError`).
_VCS_SHAPE = {'status': dict, 'push': dict, 'pull': dict, 'validate': dict, 'mirror_dir': str}
#: Функції, чий результат може нести ТЕКСТ із адресою репо (`error`, `hint`, `message`…): чужий модуль не кидає, а повертає
#: `{ok: false, error: <текст із адресою>, hint: …}`.
_VCS_TEXTY = ('status', 'push', 'pull')


def _vcs_call(vcs, fn, *args, timeout=None):
    """Виклик функції ролі: `vcs` — `(module, ctx, legacy[, target])` від маршруту чи `None` (знайти самому). Відмова модуля
    — `VcsError` із його кодом; результат не тієї форми — `VcsError('module-error')`, як і в каркаса для кривого `check`.
    `timeout` — межа для КОРОТКИХ викликів: так кличуть `validate`, щоб завислий модуль не тримав маршрут; операції git
    (`status`/`push`/`pull`) тримає сам модуль, їм межі не ставимо.

    ⛔ УСІ верхньорівневі рядкові значення результату `status`/`push`/`pull` (не лише `error`) іде крізь `_mask_repo` ТУТ:
    `gitlab_sync` віддає `{**r, 'remote': …}`, автосинк кладе той самий `r` у відповідь Stop-хука, і `hint`/`message` свого модуля з
    адресою `https://TOKEN@host/…` дійшли б назовні. Маска ідемпотентна й чіпає лише userinfo після `://`; не рядки — як є."""
    v = vcs if vcs is not None else vcs_provider()
    if v is None:
        raise VcsError('vcs-error', 'no git sync in this space')
    try:
        r = deai_modules.call(v[0], fn, v[1], *args, timeout=timeout)
    except deai_modules.ModuleError as e:
        raise VcsError(e.code, e.message) from None
    want = _VCS_SHAPE.get(fn)
    if want is not None and not isinstance(r, want):
        raise VcsError('module-error', f'{fn} returned {type(r).__name__}, expected {want.__name__}')
    if fn in _VCS_TEXTY:
        r = {k: _mask_repo(x) if isinstance(x, str) else x for k, x in r.items()}
    if isinstance(r, dict):
        # Результат іде в `_send_json` ПОЗА `try` маршруту: `set`/`bytes` у відповіді свого модуля обірвали б зʼєднання (а для
        # автосинку — 5xx Stop-хуку). Перевіряємо тут, де `module-error` ще має куди піти.
        try:
            json.dumps(r)
        except (TypeError, ValueError):
            raise VcsError('module-error', f'{fn} returned a result that is not JSON-serializable') from None
    return r


def _last_commit(r):
    """`last_commit` результату `pull` у безпечній формі `{author: str, time: число | None}`. Не обʼєкт чи кривий тип
    поля — як «немає»: застарілість своєї роботи тоді не перевіряється (як для порожнього `time`), але й не падає."""
    lc = r.get('last_commit')
    if not isinstance(lc, dict):
        return {}
    author, at = lc.get('author'), lc.get('time')
    return {'author': author if isinstance(author, str) else '',
            'time': at if isinstance(at, (int, float)) and not isinstance(at, bool) else None}


def vcs_mirror_dir(gl, vcs=None):
    """Тека дзеркала цілі — розкладку знає модуль; ядру й тестам — для діагностики. `None` — ролі нема чи модуль не вміє
    казати (`mirror_dir` необовʼязкова для свого модуля): шлях тоді невідомий і не показується."""
    v = vcs if vcs is not None else vcs_provider()
    if v is None or v[0].fn('mirror_dir') is None:
        return None
    return _vcs_call(v, 'mirror_dir', gl)


#: Керівні символи, які модуль відхиляє в `meta` (`vcs-error` до git): у імені й пошті автора — будь-які, у повідомленні —
#: усі, крім `\n`, `\t`, `\r`. Чистить ядро: заголовок задачі з ESC чи NUL інакше блокував би кожну відправку.
_CTL_LINE = re.compile(r'[\x00-\x1f\x7f]')
_CTL_TEXT = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
#: Підпис коміту, коли в машини нема особи: git без `user.email` не комітить. Лише для коміту — див. `_commit_identity`.
_FALLBACK_NAME, _FALLBACK_EMAIL = 'Designer One', 'designer.one@example.com'


def _vcs_meta(message):
    """`meta` для `push` модуля: повідомлення коміту й підпис автора — очищені від керівних символів."""
    a = _commit_author()
    return {'message': _CTL_TEXT.sub('', message),
            'author': {'name': _CTL_LINE.sub('', a['name']).strip() or _FALLBACK_NAME,
                       'email': _CTL_LINE.sub('', a['email']).strip() or _FALLBACK_EMAIL}}


def _mockup_files(src_dir):
    """Файлы чистого макета (те же правила, что copy_mockup: без .py/служебного)."""
    out = []
    for name in sorted(os.listdir(src_dir)):
        if _is_tool_junk(name):
            continue
        p = os.path.join(src_dir, name)
        if os.path.isdir(p):
            for root, dirnames, names in os.walk(p):
                # Теку з іменем *.tmp теж геть, і на місці: copytree відсіює її
                # через ignore_patterns, а os.walk без цього рядка заходив би
                # усередину — і відбиток розійшовся б із експортом.
                dirnames[:] = [n for n in dirnames if not n.endswith(TMP_SUFFIX)]
                # Той самий вузький фільтр, що і в copytree у copy_mockup: інакше
                # відбиток бачив би файли, яких експорт уже не возить, і кожен
                # осиротілий tmp вічно кричав би «є що синхронізувати».
                out += [os.path.join(root, n) for n in names
                        if not n.endswith(TMP_SUFFIX)]
        else:
            out.append(p)
    return sorted(out)


def mockup_hash(src_dir):
    """Отпечаток чистого макета — чтобы понять, есть ли что синхронизировать."""
    import hashlib
    h = hashlib.md5()
    for f in _mockup_files(src_dir):
        h.update(os.path.relpath(f, src_dir).encode())
        h.update((_file_hash(f) or '').encode())
    return h.hexdigest()


_identity_cache = None


def machine_identity():
    """Підпис ЦІЄЇ машини: `(імʼя, ключ)`. Порожні рядки — коли особи немає.

    Джерело те саме, що вже використовують `bin/registry.py` і
    `bin/overview_push.py` для `owner`/`owner_key`: глобальний git-конфіг.
    Третьої моделі особи в інструменті не заводимо.

    ⛔ Фолбека на конкретну людину тут НЕМАЄ — на відміну від
    `_commit_identity()`, де константа лише підписує коміт у дзеркало. Тут
    значення їде в `author` ітерації, тобто фолбек означав би ПРИПИСАТИ чужу
    роботу конкретному імені. Порожньо — чесно: така ітерація вважається своєю
    на будь-якій машині (див. `iteration_is_mine`).

    `DC_IDENTITY_NAME`/`DC_IDENTITY_EMAIL` перекривають конфіг: тестам треба
    вміти зіграти ДВОХ дизайнерів в одному процесі, а машина без git-конфіга
    має де назватись, не правлячи глобальний конфіг.
    """
    env_name = os.environ.get('DC_IDENTITY_NAME')
    env_key = os.environ.get('DC_IDENTITY_EMAIL')
    if env_name is not None or env_key is not None:
        # ⛔ Env-гілка НЕ кешується: тести в одному процесі грають двох
        # дизайнерів, і закешована відповідь зробила б другого першим.
        return (env_name or '').strip(), (env_key or '').strip()
    global _identity_cache
    if _identity_cache is not None:
        return _identity_cache
    out = []
    for key in ('user.name', 'user.email'):
        try:
            r = subprocess.run(['git', 'config', '--get', key],
                               capture_output=True, text=True, timeout=5)
            out.append(r.stdout.strip() if r.returncode == 0 else '')
        except (OSError, subprocess.SubprocessError):
            out.append('')
    # Кеш на життя процесу: `/api/task` канвас ПОЛИТЬ, а git-конфіг машини за
    # цей час не міняється. Без кешу кожен опит смуги коштував би двох
    # процесів `git config` заради константної відповіді.
    #
    # ⛔ Кешуємо ЛИШЕ непорожнє. `git config` може впасти транзієнтно (таймаут,
    # index.lock, dubious ownership), і закешована порожнеча означала б, що до
    # перезапуску сервера — а він живе днями — усі нові ітерації народжуються
    # без підпису, а всі чужі раптом стають своїми. Те саме, якщо дизайнер
    # полагодить `user.email`, не зупиняючи канвас.
    if out[0] or out[1]:
        _identity_cache = (out[0], out[1])
    return out[0], out[1]


def iteration_is_mine(it, my_key):
    """Чи ця ітерація МОЯ. Порівняння по ключу, не по імені.

    Дві межі, обидві на користь «своя» — бо «чужа» відводить роботу у форк і
    забороняє пуш, тобто хибне спрацювання тут коштує дорожче за пропущене:
      · у записі немає `author_key` (уся історія до цієї задачі) — своя;
      · на машині немає особи — своє все, тобто сьогоднішня поведінка.
    """
    key = (it or {}).get('author_key') or ''
    return not key or not my_key or key == my_key


def _stamp_author(entry):
    """Підписати ЗАПИС ітерації особою цієї машини. Порожня особа — без полів.

    ⛔ Саме БЕЗ полів, а не з порожніми рядками: `author: ''` читалось би як
    «автор відомий і безіменний», а `iteration_is_mine` мусить бачити різницю
    між «підпису немає» і «підпис чужий».
    """
    name, key = machine_identity()
    if name or key:
        entry['author'], entry['author_key'] = name, key
    return entry


def _commit_author():
    """Підпис коміту в дзеркало: особа машини, а без неї — константа (git без `user.email` не комітить). Див.
    `_commit_identity` — чому константа лише тут і ніколи не в даних ітерації."""
    name, key = machine_identity()
    return {'name': name or _FALLBACK_NAME, 'email': key or _FALLBACK_EMAIL}


def _commit_identity():
    """Аргументи -c для коміту в дзеркало: підпис ВЛАСНИКА машини.

    Раніше тут був жорстко зашитий Designer One — через це пуш будь-якого
    дизайнера приходив від імені автора інструменту, а gitlab_pull, який бере
    автора з `log -1 --format=%an` для підпису ітерації, завжди писав те саме
    ім'я. Тепер особу дає `machine_identity()` — ОДНЕ джерело на весь
    інструмент, те саме, що підписує ітерації.

    ⛔ Константний фолбек лишається ЛИШЕ тут і лише тому, що git без
    `user.email` взагалі відмовляється комітити. У дані (`author` ітерації) він
    не потрапляє ніколи: `machine_identity()` там віддає порожньо, і
    `_stamp_author` не пише полів — бо константа в даних означала б приписати
    роботу конкретній людині. Без цього поділу вигадане імʼя витікало довгим
    шляхом: порожній `author` у `.canvas-state.json` → колега падає на
    запасний `git log -1 --format=%an` → а комітив дзеркало саме цей фолбек.
    """
    a = _commit_author()
    return ['-c', f'user.name={a["name"]}', '-c', f'user.email={a["email"]}']


def _iter_dir(task, it):
    return os.path.join(task['dir'], 'iterations', it)


def iteration_pages(task, it):
    return pm.read_pages(_iter_dir(task, it))


def _page_dir(task, it, page):
    """Тека сторінки в теці ітерації ('' для неявної main → корінь ітерації)."""
    return os.path.join(_iter_dir(task, it), pm.page_rel(page))


def _pick_page(task, it, page_id):
    """Об'єкт сторінки за id; None-безпечно повертає першу відкривану
    (тека — `kind: folder` чи легасі-`isGroup` — не відкривається: теж падаємо
    на першу відкривану)."""
    pages = iteration_pages(task, it)
    op = pm.openable_pages(pages)
    if page_id:
        p, _ = pm.find_page(pages, page_id)
        # відкривається рівно те, що входить в `op` (те саме джерело, що й запасний
        # варіант нижче): тип вузла без батька ми б вивели наново й, можливо, інакше
        if p is not None and any(q is p for q in op):
            return p
    return op[0] if op else None


def gitlab_sync(tid, task, gl, it, vcs=None):
    """Експорт ВИБРАНОЇ ітерації в `<path>` дзеркала → коміт → push (усе це робить модуль ролі `vcs`).
    Pull-first guard (модуль): якщо в репо новіше по нашому шляху — не пушимо поверх (інакше мовчки затремо чужий
    макет), просимо спершу «Підтягнути». `gl` — ціль (`vcs_target`); `vcs` — `(module, ctx, legacy)` від маршруту чи
    `None` (знайти самому). Відмова модуля — `VcsError` (це `OSError`: маршрути й автосинк ловлять її як і раніше)."""
    src = _iter_dir(task, it)
    if not os.path.isdir(src):
        raise OSError('iteration not found')
    # ⛔ Чуже не пушимо. Відправити ітерацію колеги під своїм підписом означає
    # стерти авторство рівно так, як воно стиралось до цієї задачі — тільки
    # тепер уже маючи підпис на руках. Перевірка стоїть ПЕРЕД постачальником і
    # мережею: ні дзеркала, ні fetch заради відмови.
    _entry = next((x for x in load_meta(task).get('iterations', [])
                   if x['id'] == it), {})
    _, _my_key = machine_identity()
    if not iteration_is_mine(_entry, _my_key):
        return {'ok': False, 'synced': False, 'blocked': 'foreign', 'it': it,
                'author': _entry.get('author') or _entry.get('author_key') or ''}
    v = vcs or vcs_provider()
    if v is None:
        raise VcsError('vcs-error', 'no git sync in this space')
    legacy = v[2]
    meta_now = load_meta(task)
    it_entry = next((x for x in meta_now.get('iterations', []) if x['id'] == it), {})
    # ⛔ Тека для модуля — у системній теці тимчасових файлів, ПОЗА текою задачі: інакше `git_autocommit` підхопив би її
    # у локальну історію задачі. Прибирається в `finally`, і після відмови теж.
    tmp = tempfile.mkdtemp(prefix='deai-vcs-')
    try:
        out_dir = os.path.join(tmp, 'm')
        copy_mockup(src, out_dir)
        pages = pm.read_pages(src)
        if len(pm.openable_pages(pages)) > 1:
            # Глибина — відступом, тека — рядком БЕЗ теки (`—`): на диску її нема, і
            # `<id>/` у колонці «Тека» вів би в нікуди. Вкладеність тепер довільна,
            # а `↳ ` на будь-якій глибині виглядав однаково.
            # `&emsp;`, а не пробіли: GFM обрізає пробіли на початку комірки, і глибина
            # зникла б (а колись була видима — `↳ `). Назва в один рядок: перенос
            # усередині розірвав би рядок таблиці.
            def _row(f):
                name = ' '.join(f['page']['name'].split()).replace('|', '/')
                indent = '&emsp;' * f['depth']
                if f['kind'] == 'folder':
                    return f"| — | {indent}📁 {name} |"
                return f"| `{pm.page_rel(f['page']) or '.'}/` | {indent}{name} |"
            rows = '\n'.join(_row(f) for f in pm.flatten(pages))
            # Назва інструмента — текст ДАНИХ: у просторі ЛІГА лишається «design-canvas», як у 0.7.0.
            tool = 'design-canvas' if legacy else 'Deai Canvas'
            with open(os.path.join(out_dir, 'README.md'), 'w', encoding='utf-8') as fh:
                fh.write(f"# {task.get('title', tid).replace(chr(10), ' ')}\n\n"
                         f"Мультисторінковий макет ({tool}, задача `{tid}`). "
                         f"Не редагувати тут напряму.\n\n"
                         f"| Тека | Сторінка |\n|---|---|\n{rows}\n")
        # Стан публікації — колегам. Без нього в чужому канвасі ітерації завжди
        # виглядають неопублікованими: iterations.json лежить у SKIP і нікуди не їде.
        # ⛔ Жодних міток часу «коли синкнули» — інакше файл мінявся б щоразу і
        # автосинк робив би порожній коміт на кожну відповідь Claude.
        # Підпис автора — ЗАЯВА тієї машини, що синкає. Колега читає саме її
        # (`gitlab_pull`), а не `git log`: лог це властивість коміту й розходиться
        # з автором макета на першому ж ребейсі чи пуші з CI.
        _author, _author_key = machine_identity()
        with open(os.path.join(out_dir, STATE_FILE), 'w', encoding='utf-8') as fh:
            json.dump({'task': tid, 'source_it': it,
                       'author': _author, 'author_key': _author_key,
                       'published': bool(it_entry.get('published')),
                       'publish_url': meta_now.get('publish_url'),
                       'published_at': meta_now.get('published_at')},
                      fh, ensure_ascii=False, indent=2)
        title = task.get('title', tid)
        # rich-повідомлення: щоб pull/історія були самопояснювальні й легше вирішувати конфлікти
        note = (it_entry.get('note') or '').strip()
        subject = f'{"design-canvas" if legacy else "deai"}: sync {gl["path"]} ({title}) · {it}'
        body = f'Ітерація: {it} · Хеш: {mockup_hash(src)[:12]} · {time.strftime("%d.%m.%Y %H:%M")}'
        if note:
            body += f'\nЩо змінено: {note}'
        r = _vcs_call(v, 'push', gl, out_dir, _vcs_meta(subject + '\n\n' + body))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {**r, 'remote': _mask_repo(f'{gl["repo"]}:{gl["path"]}')}


def gitlab_status(task, gl, meta, it, vcs=None):
    """Є локальні зміни ВИБРАНОЇ ітерації до відправки / новіше в репо. `gl` — ціль; `vcs` — `(module, ctx, legacy)` від
    маршруту чи `None` (знайти самому: ролі нема — `{'configured': False}`). Помилка постачальника чи модуля — стан із
    `error` і `code`, не виняток: опит статусу йде на кожному старті."""
    try:
        v = vcs or vcs_provider()
        if v is None:
            return {'configured': False}
        st = _vcs_call(v, 'status', gl)
    except VcsError as e:
        return {'configured': True, 'error': str(e)[:200], 'code': e.code}
    g = meta.get('gitlab') or {}
    src = _iter_dir(task, it)
    # dirty относительно последней синхронизации ИМЕННО этой итерации
    # багатосторінкова задача (sync-all): порівнюємо з хешем ЦІЄЇ ітерації,
    # бо на GitLab лежать усі, а не одна вибрана
    per_it = (g.get('synced_hashes') or {})
    if it in per_it:
        dirty = (not os.path.isdir(src)) or (mockup_hash(src) != per_it[it])
    else:
        dirty = (not os.path.isdir(src)) or (g.get('synced_it') != it) \
            or (mockup_hash(src) != g.get('synced_hash'))
    # яка локальна ітерація ЗАРАЗ == версії на GitLab (за хешем останньої синхр.)
    sh = g.get('synced_hash')
    gitlab_it = None
    if sh:
        for itd in (meta.get('iterations') or []):
            d = _iter_dir(task, itd['id'])
            if os.path.isdir(d) and mockup_hash(d) == sh:
                gitlab_it = itd['id']
                break
    out = {'configured': True, 'behind': st.get('behind', 0),
           # Окремо від `behind`: «репо попереду» і «теку задачі попереду» —
           # різні новини, і перше не заважає працювати (модуль: `behind_path`
           # блокує відправку, `behind` наздоганяється сам).
           'behind_path': st.get('behind_path', 0),
           # незапушені локальні коміти дзеркала — щоб «✓» більше не могло
           # означати «лежить у мене, а не на GitLab» (давній випадок: коміт лежав лише в дзеркалі)
           'unpushed': st.get('unpushed', 0),
           # чи є тека задачі на origin: «ніколи не пушилось» ≠ «синхронізовано»
           'on_remote': st.get('on_remote'),
           'dirty': bool(dirty), 'synced_at': g.get('synced_at'),
           'synced_it': g.get('synced_it'), 'gitlab_it': gitlab_it,
           'remote_path': gl['path'], 'web': _mask_repo(st['web']) if isinstance(st.get('web'), str) else None,
           'label': _mask_repo(st['label']) if isinstance(st.get('label'), str) and st['label'] else 'Git'}
    if v[2]:
        # Простір ЛІГА (простір з інтеграціями, `git-sync` із `compat: design-canvas`): «Історія» й підпис — як у 0.7.0 (будь-який `git@host:`, і з IP, «GitLab»), до 4d.
        out['web'], out['label'] = gitlab_web(gl), 'GitLab'
    return out


def _read_state(src_dir):
    """Стан публікації з макета, що прийшов від колеги (див. STATE_FILE)."""
    p = os.path.join(src_dir, STATE_FILE)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _dir_mtime(d):
    """Найсвіжіший mtime файлів у теці — де щойно працювали.

    Dot-файли не рахуємо: `.pages.lock` (створюється справжнім записом дерева) і
    `.DS_Store` — службове, а не робота. Вибір робочої ітерації в `autosync` іде
    саме за цим числом, тож свіжий лок-файл на старій ітерації переставив би
    вибір. Так само рахує `_authored_mtime`."""
    newest = 0.0
    for root, _, names in os.walk(d):
        for n in names:
            if n.startswith('.'):
                continue
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, n)))
            except OSError:
                continue
    return newest


def _authored_mtime(d, skip=None):
    """Коли в ітерації востаннє ПРАЦЮВАЛИ: найсвіжіший mtime файлів без `shots/`.

    Кадри перезнімаються самі (автозʼємка при вході в «Огляд», T-34), тож
    свіжий `shots/` означає «інструмент перезняв», а не «дизайнер правив».
    Порівнюється з `last_commit.time` модуля `vcs` — там кадри виключені так само (`opts.ignore`).
    Dot-файли (`.DS_Store` від Finder) — теж не робота: їх не везе й експорт
    (`_is_tool_junk`), тобто на origin їх немає, і рахувати їх лише з одного
    боку означало б «молодшати» тижневу ітерацію від відкриття теки.
    `skip(name)` — предикат для файлів КОРЕНЯ, які не рахуються (`_content_mtime`).
    """
    newest = 0.0
    for root, dirs, names in os.walk(d):
        if root == d:
            dirs[:] = [n for n in dirs if n != 'shots']
        dirs[:] = [n for n in dirs if not n.startswith('.')]
        for n in names:
            if n.startswith('.') or (skip and root == d and skip(n)):
                continue
            try:
                newest = max(newest, os.path.getmtime(os.path.join(root, n)))
            except OSError:
                continue
    return newest


#: Файли кореня ітерації, що НЕ є вмістом рамки: дерево перечитує панель
#: (`refreshPanelFromDisk`), а `flow.json` пише сам канвас на драг вузла.
_NOT_CONTENT = ('pages.json', 'flow.json')


def _content_mtime(d):
    """Коли востаннє змінився ВМІСТ ітерації — те, що показує рамка
    (fb-01102026-309e3b). Як `_authored_mtime`, плюс без `_NOT_CONTENT` і без
    службового (`_is_tool_junk`: `.bak`, `.tmp`…): інакше власний жест дизайнера
    перезавантажував би макет — драг вузла флоу пише `flow.json`, а КОЖНА дія
    над деревом знімає `pages.json.bak` через `copy2` з mtime попередньої
    версії (ревʼю батча 1.47, D1)."""
    return _authored_mtime(d, lambda n: n in _NOT_CONTENT or _is_tool_junk(n))


#: Скільки живе серцебиття Клода (секунди) — за статусом. Ідея 02.09.2026: статус
#: тримається на доказі, що СПЛИВАЄ, а не на прапорці. «Працює» — коротко: мод
#: pipeline-band бʼє на кожному інструменті (не частіше разу на 15 с), тож 3 хв
#: тиші = Клод упав, сесію закрили або довга команда без жодного інструменту
#: (тоді чесніше згаснути, ніж збрехати). «Чекає» / «заблоковано» — стани ходу,
#: між ударами довше, але й вони не вічні: закрита сесія — не «чекає».
CLAUDE_TTL = {'in_progress': 180, 'waiting': 1800, 'blocked': 1800, 'done': 600}
_CLAUDE_STATE = {'in_progress': 'working', 'waiting': 'waiting', 'blocked': 'blocked', 'done': 'done'}
CLAUDE_PHASES = ('understanding', 'design', 'dev', 'checks', 'fixation')
#: Удари за сесією (у памʼяті процесу: рестарт сервера = «нічого не знаю», чесно).
CLAUDE_BEATS = {}
#: Сервер багатопотоковий: запис/витіснення й читання ударів — під одним локом.
CLAUDE_LOCK = threading.Lock()
#: Етап Д: маршрути `task-rename/delete/restore/purge` роблять «прочитати tasks.json → змінити → записати» під ЦИМ замком —
#: два видалення поспіль не перезапишуть одне одного. Решта маршрутів його не бере (наявний борг, `atomic_io.py`).
#: ⛔ Не `WRITE_LOCK`: той нереентрантний і його бере `save_tasks` усередині.
TASK_CRUD_LOCK = threading.Lock()


def _local_origin(origin):
    """Origin відсутній (мод Claude Code, CLI) або локальний — так; чужий сайт — ні."""
    if not origin:
        return True
    host = (urlparse(origin).hostname or '').lower()
    return host in ('localhost', '127.0.0.1', '::1')
#: Сторінка «змінена щойно» — файли молодші за стільки секунд.
RECENT_PAGE_S = 120


def claude_view(beats, now, task_id, aliases=()):
    """Що показати на канвасі для задачі `task_id`. Чиста функція.

    Найсвіжіший удар САМЕ цієї задачі; прострочений за `CLAUDE_TTL` — `state: None`,
    тобто нічого. Так падіння Клода гасить статус саме собою, без нічийого cleanup.

    `aliases` — інші імена тієї ж задачі (її Jira-ключ): мод шле `jira ?? id`, модель —
    тікет Jira (знахідка 12.10.2026). Порожні імена не рахуються."""
    # Лише рядки: ручна правка tasks.json (`"jira": [..]`) не сміє класти опит у 500.
    keys = {k for k in (task_id, *aliases) if k and isinstance(k, str)}
    mine = [b for b in beats.values() if b.get('task') in keys]
    if not mine:
        return {'state': None}
    b = max(mine, key=lambda x: x.get('at') or 0)
    age = max(0, int(now - (b.get('at') or 0)))
    if age > CLAUDE_TTL.get(b.get('status'), 0):
        return {'state': None}
    return {'state': _CLAUDE_STATE[b['status']], 'phase': b.get('phase'),
            'note': b.get('note') or '', 'age_s': age}


def claude_views(beats, now):
    """Статуси всіх задач, де серцебиття ще свіже, — для вкладок канваса (0.25.0). Чиста функція.

    Ключ — те, що шле мод (`id` чи Jira-ключ задачі); клієнт шукає вкладку за обома. Назовні йдуть лише
    `state` і `age_s`: нотатка й фаза — для острівця поточної задачі (`claude_view`), не для списку."""
    keys = {b.get('task') for b in beats.values() if isinstance(b.get('task'), str) and b.get('task')}
    out = {}
    for k in keys:
        v = claude_view(beats, now, k)
        if v.get('state'):
            out[k] = {'state': v['state'], 'age_s': v['age_s']}
    return out


def recent_pages(idir, now=None):
    """Id сторінок, чиї файли змінились за `RECENT_PAGE_S` — «де саме міняє»."""
    now = time.time() if now is None else now
    try:
        tree = pm.read_pages(idir)
    except pm.TreeError:
        return []
    out = []
    for f in pm.flatten(tree):
        rel = pm.page_rel(f['page']) if f['kind'] != 'folder' else ''
        d = os.path.join(idir, rel) if rel else None
        if d and os.path.isdir(d) and now - _authored_mtime(d) < RECENT_PAGE_S:
            out.append(f['page']['id'])
    return out


def _touch_tree(d):
    """Проставити файлам теки поточний час.

    ⛔ Не косметика. `copy_mockup` іде через `shutil.copy2`, який зберігає mtime
    ДЖЕРЕЛА, а `autosync` вибирає робочу ітерацію саме за mtime. Свіжий форк із
    чужими старими часами означав би, що Stop-хук відправить у дзеркало іншу
    ітерацію — ту, де я працював учора.
    """
    now = time.time()
    for root, _, names in os.walk(d):
        for n in names:
            try:
                os.utime(os.path.join(root, n), (now, now))
            except OSError:
                continue


def _record_sync(task, it, sha):
    """Відбиток відправленої ітерації.

    `synced_hashes` накопичуємо по ітераціях і НЕ затираємо: саме за ним автосинк
    розуміє, що ітерація вже поїхала. Без цього кожна відповідь Claude
    закінчувалась би зайвим походом у мережу.
    """
    meta = load_meta(task)
    if not sha:
        # ⛔ Без sha відбитка НЕ пишемо. Запис `synced_at`/`synced_it` при
        # `sha=None` — це готова брехня в мета: саме так bgSanctions вважався
        # синхронізованим 22.07.2026, хоча теки на origin не існувало.
        # Мовчати теж не можна: інакше «не записали» не відрізнити від «записали».
        print(f'⚠ синк {it}: немає sha — відбиток не записано, '
              f'наступний синк спробує знову', file=sys.stderr)
        return meta
    g = dict(meta.get('gitlab') or {})
    hashes = dict(g.get('synced_hashes') or {})
    hashes[it] = mockup_hash(_iter_dir(task, it))
    meta['gitlab'] = {**g, 'synced_at': time.strftime('%d.%m.%Y %H:%M'),
                      'synced_it': it, 'synced_hash': hashes[it],
                      'synced_hashes': hashes, 'sha': sha}
    save_meta(task, meta)
    return meta


def autosync(tid, task, gl, vcs=None):
    """Один крок автосинку: брудна ітерація → локальний коміт → пуш на GitLab.

    Кличе Stop-хук після кожної відповіді Claude — правило «макет пушимо після
    КОЖНОГО оновлення, а не в кінці задачі» (30.07.2026) перестає залежати від
    того, чи згадав про нього Claude.

    Дешевий шлях без мережі: якщо робоча ітерація збігається з відбитком
    останньої синхронізації — виходимо одразу, жодного `git fetch`.
    """
    meta = load_meta(task)
    live = [(x['id'], _iter_dir(task, x['id'])) for x in meta.get('iterations', [])]
    live = [(i, d) for i, d in live if os.path.isdir(d)]
    if not live:
        return {'ok': True, 'changed': False, 'reason': 'no-iterations'}
    # Беремо ОДНУ ітерацію — найсвіжішу за mtime (у канвасі за замовчуванням
    # обрана саме та, в якій працюють). ⛔ Свідомо не скануємо всю історію: тоді
    # ітерація, яку ніколи не пушили, вважалась би брудною вічно, і автосинк
    # вивіз би в репо якусь it1 з минулого тижня замість поточної.
    # ⛔ Чужі ітерації автосинк не розглядає взагалі: відправити чуже під своїм
    # підписом — рівно та втрата авторства, проти якої написана вся задача про
    # іменні ітерації. Мовчазний вибір «хоч чогось», коли своїх немає, був би
    # тим самим — тому причина називається вголос.
    _, my_key = machine_identity()
    by_id = {x['id']: x for x in meta.get('iterations', [])}
    mine = [(i, d) for i, d in live if iteration_is_mine(by_id.get(i, {}), my_key)]
    if not mine:
        return {'ok': True, 'changed': False, 'reason': 'foreign-only'}
    it = max(mine, key=lambda p: _dir_mtime(p[1]))[0]
    g = meta.get('gitlab') or {}
    known = (g.get('synced_hashes') or {}).get(it)
    if known is None and g.get('synced_it') == it:
        known = g.get('synced_hash')  # синк до появи per-iteration відбитків
    if known is not None and mockup_hash(_iter_dir(task, it)) == known:
        return {'ok': True, 'changed': False, 'reason': 'clean', 'it': it}
    # Текст ДАНИХ (історія теки задачі): у просторі ЛІГА лишається «design-canvas», у звичайному — «deai» (поправка 12 до спеки).
    # Постачальника беремо тут, щоб знати, чий це простір; не знайшли — відмову скаже `gitlab_sync` нижче («offline»).
    v = vcs
    if v is None:
        try:
            v = vcs_provider()
        except OSError:
            v = None
    local = git_autocommit(task['dir'], f'{it}: автосинк ({"deai" if v is not None and not v[2] else "design-canvas"})')
    try:
        r = gitlab_sync(tid, task, gl, it, vcs=v)
    except OSError as e:
        # Немає мережі/VPN — це не привід сварити дизайнера після кожної відповіді.
        # Але й «синхронізовано» не пишемо: відбиток лишається старим, і синк
        # повторить спробу наступного разу. Будь-яка відмова модуля (`vcs-offline`/
        # `vcs-auth`/`vcs-busy`/`vcs-error`) — той самий «offline», з `code`: Stop-хук
        # ніколи не отримує 5xx.
        return {'ok': False, 'synced': False, 'changed': False, 'reason': 'offline',
                'it': it, 'error': _mask_repo(str(e))[:300], 'local_sha': local.get('sha'),
                **({'code': e.code} if isinstance(e, VcsError) else {})}
    # ⛔ Гейт саме по `synced`, а не по `ok`: `ok` буває True і тоді, коли макет не
    # змінився, а попередній коміт так і не доїхав до origin. Саме через це
    # bgSanctions 12 днів показував «✓» при незапушеному коміті.
    if r.get('synced'):
        _record_sync(task, it, r.get('sha'))
    return {**r, 'it': it, 'local_sha': local.get('sha')}


def _task_is_mine(task):
    """Чи ЦЯ машина — власник задачі (`owner_key`). Без власника чи без особи — так."""
    owner = (task or {}).get('owner_key') or ''
    _, me = machine_identity()
    return not owner or not me or owner == me


def _not_task_link(task):
    """Імʼя власника, якщо превʼю з ЦІЄЇ машини — НЕ посилання задачі; інакше None.

    Рішення власника 29.09.2026 (fb-29092026-69e9c7, 210ec1): посилання задачі —
    превʼю ВЛАСНИКА; не-власник публікує у своє, і канвас каже це вголос.
    """
    if _task_is_mine(task):
        return None
    return (task or {}).get('owner') or (task or {}).get('owner_key')


def _adopt_publish_state(meta, state, task):
    """Публікація — задачного рівня і належить тому, хто деплоїв.

    ⛔ Лише від ВЛАСНИКА задачі (рішення 29.09.2026). Інакше не-власник, що
    опублікував у СВОЄ превʼю й синкнув макет, підміняв би колегам посилання
    задачі своїм — а в Vercel другого акаунта це взагалі інший проєкт
    (`pv-XXXX-<суфікс>`). Без власника чи без підпису автора — як було.

    Переносимо URL до себе, щоб у канвасі колеги був живий лінк «превью ↗», а не
    порожнеча. Винесено окремо, бо тепер це роблять ДВІ гілки `gitlab_pull`:
    і та, що заводить ітерацію, і та, що впізнала власний вміст і ітерації не
    заводить. Забути другу означало б «підтягнув — і лінк не приїхав».
    """
    owner = (task or {}).get('owner_key')
    author = state.get('author_key')
    if owner and author and owner != author:
        return
    if state.get('publish_url'):
        meta['publish_url'] = state['publish_url']
        meta['published_at'] = state.get('published_at')


def gitlab_pull(task, gl, vcs=None):
    """Чужі правки з репо → нова ітерація локально (робочий макет не чіпаємо). Модуль ролі `vcs` кладе `<path>` у тимчасову
    теку; ядро вирішує, що з цим робити (`_pull_into_task`). `gl` — ціль, `vcs` — як у `gitlab_sync`."""
    v = vcs or vcs_provider()
    if v is None:
        raise VcsError('vcs-error', 'no git sync in this space')
    # Назва джерела — текст ДАНИХ (примітка ітерації): у просторі ЛІГА лишається «GitLab», як у 0.7.0.
    src_name = 'GitLab' if v[2] else 'репозиторію'
    tmp = tempfile.mkdtemp(prefix='deai-vcs-')
    try:
        src = os.path.join(tmp, 'm')
        os.makedirs(src)
        # ⛔ Не ковтати відмову pull: при розходженні дзеркала `--ff-only` падає (`pull --ff-only failed`), і раніше ми
        # копіювали в нову ітерацію ЗАСТАРІЛЕ дзеркало, підписавши його «оновлення з GitLab · <колега>». Тепер це `VcsError`.
        # `shots` — підтека кадрів: їхні комміти не вважаються роботою (див. `_authored_mtime`).
        r = _vcs_call(v, 'pull', gl, src, {'ignore': ['shots']})
        # ⛔ Знайдено — це РІВНО `found is True` і непорожня `dst`. Свій модуль міг віддати `found: 'no'` (правдиве) чи `True` над
        # порожньою текою — і задача діставала порожню нову ітерацію, що ставала «останньою» і вела автосинк на порожнечу.
        if r.get('found') is not True or not (os.path.isdir(src) and os.listdir(src)):
            raise OSError(f'path {gl["path"]} not found in repo')
        return _pull_into_task(task, src, _last_commit(r), src_name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _pull_into_task(task, src, last_commit, src_name):
    """Приймання `src` (копія `<path>` з репо) у задачу: нова ітерація, авторство, форк чужої чи застарілої своєї,
    стан публікації. `last_commit` — `{author, time}` від модуля (`time` — без кадрів, `None` — не перевіряти застарілість)."""
    # автор останнього коміту по нашому шляху — в підпис ітерації (запасний шлях, див. нижче)
    author = last_commit.get('author') or ''
    # ⛔ Імені автора в ПРИМІТЦІ більше немає (15.09.2026). Воно тут стояло,
    # поки в ітерації не було власного поля `author` — і тихо витікало в
    # ПУБЛІЧНЕ превʼю: `publish_manifest` везе `note` як є, а `manifest.json`
    # віддається без пароля (заміряно 11.09.2026). Рішення власника —
    # підпис лише всередині інструмента, тож автор їде полем, а не текстом.
    note = f'оновлення з {src_name}'
    state = _read_state(src)
    meta = load_meta(task)
    its = meta.setdefault('iterations', [])
    # ⛔ ІДЕМПОТЕНТНІСТЬ. Якщо вміст теки задачі на origin збігається з якоюсь
    # ітерацією, що вже лежить локально, — нової ітерації НЕ заводимо. Інакше
    # виходило так: guard блокував пуш «у репо новіше» (через чужий коміт мимо
    # нашої теки), дизайнер тиснув «Підтягнути», і той створював копію СТАРОГО
    # стану, яка ставала «останньою». Канвас відкривав її за перезавантаженням,
    # `state.py` писав «ПРОДОВЖУЄМО з Іт.N», autosync вибирає робочу ітерацію за
    # mtime — тобто зʼявлявся шанс відправити старий макет. Прибрати артефакт
    # користувач не міг: видалення ітерації справедливо блокує класифікатор.
    remote_hash = mockup_hash(src)
    for i in its:
        d = os.path.join(task['dir'], 'iterations', i['id'])
        if os.path.isdir(d) and mockup_hash(d) == remote_hash:
            # ⚠️ Стан ПУБЛІКАЦІЇ переносимо однаково — він задачного рівня, а не
            # ітераційного, і нічого не «привезти» тут було б новою тихою
            # втратою: колега тягне макет саме щоб побачити лінк на превʼю.
            _adopt_publish_state(meta, state, task)
            its_by_id = {x['id']: x for x in its}
            its_by_id[i['id']]['published'] = bool(state.get('published'))
            # Дзеркало вже підтягнуте (ff вище), тож відбиток ставимо: стан
            # «нас обігнали» знято, і повторний pull не крутитиме те саме.
            meta['gitlab'] = {**(meta.get('gitlab') or {}), 'synced_hash': remote_hash}
            save_meta(task, meta)
            return {'ok': True, 'unchanged': True, 'iteration': None, 'same_as': i['id']}
    nums = [int(m.group(1)) for i in its if (m := re.match(r'^it(\d+)$', i['id']))]
    new_id = f'it{max(nums, default=0) + 1}'
    copy_mockup(src, os.path.join(task['dir'], 'iterations', new_id))
    entry = {'id': new_id, 'date': time.strftime('%d.%m.%Y %H:%M'),
             'note': note, 'published': bool(state.get('published')),
             'from_gitlab': True}
    # Автор — із ЗАЯВИ колеги (`.canvas-state.json`). `git log` лишається лише
    # запасним шляхом для станів, записаних версією без підпису: там автор
    # хоча б показується, але ключа немає, тож така ітерація вважається своєю
    # (`iteration_is_mine`) — свідома деградація, не тиха помилка.
    if state.get('author') or state.get('author_key') or author:
        entry['author'] = state.get('author') or author
        entry['author_key'] = state.get('author_key') or ''
    _, my_key = machine_identity()
    # Моя робота ДО цього pull — кандидат на продовження (див. нижче, d64d35).
    mine_before = [(i['id'], d) for i in its if iteration_is_mine(i, my_key)
                   and os.path.isdir(d := os.path.join(task['dir'], 'iterations', i['id']))]
    its.append(entry)
    # ФОРК ОДРАЗУ (рішення власника 15.09.2026): робота ніколи не починається
    # поверх ЧУЖОЇ ітерації. Альтернатива «форкати на першій правці» вимагала б
    # детектора запису, а правки в макет вносить Claude прямо на диску, повз
    # сервер — тобто форк був би заднім числом, уже по чужому.
    #
    # ⛔ Саме чужої. Приїхав мій власний вміст (друга машина того самого
    # дизайнера, або мій же пуш, що повернувся) — форк був би копією моєї
    # роботи без жодної причини, тобто сміттям у переліку ітерацій.
    fork, continue_from = None, None
    if not iteration_is_mine(entry, my_key):
        # Номер ітерації В АВТОРА — лише на ЧУЖІЙ. Саме він зникав назовсім: it3
        # чужої машини ставало it1 моєї, і питання «а це та версія, яку вона
        # показувала?» лишалось без відповіді. Локальний id не чіпаємо — він
        # зашитий у ключах зʼємки, шляхах публікації й глибоких посиланнях.
        # ⛔ На СВОЇЙ ітерації `origin` не має сенсу («у неї це Іт.3» про власний
        # макет) — тому присвоєння стоїть саме тут, а не до перевірки.
        if state.get('source_it'):
            entry['origin'] = {'it': state['source_it'],
                               'at': time.strftime('%d.%m.%Y %H:%M')}
        fork_id = f'it{int(new_id[2:]) + 1}'
        fork_dir = os.path.join(task['dir'], 'iterations', fork_id)
        copy_mockup(os.path.join(task['dir'], 'iterations', new_id), fork_dir)
        _touch_tree(fork_dir)
        fork = _stamp_author({'id': fork_id, 'date': time.strftime('%d.%m.%Y %H:%M'),
                              'note': f'продовження після {note}',
                              'published': False, 'from': new_id})
        its.append(fork)
    elif mine_before:
        # ⛔ Приїхало МОЄ, але СТАРШЕ за мою роботу тут (fb-29092026-d64d35,
        # boss-interface 29.09.2026). Модель «своє з GitLab = продовження»
        # мовчки припускала, що origin новіший. А там лежала Іт.7 від 08.09
        # (пуш із другої машини падав через repo з IP), тут — Іт.14 від
        # сьогодні. Привезене ставало ОСТАННІМ і з mtime «щойно», тож на старе
        # переїжджали всі три вказівники: `state.py` («продовжуємо з…»),
        # `inbox.py` і автосинк (о 11:48 він тричі обрав it6 замість it5).
        # Рішення власника 29.09.2026: привезене лягає історією, а слідом —
        # форк моєї найсвіжішої роботи, як він і зробив руками о 11:56.
        # Порівняння — на секундах: `%ct` цілий, mtime дробовий, і в одній
        # секунді «щойно запушене з другої машини» не мусить ставати старшим.
        work_id, work_dir = max(mine_before, key=lambda p: _authored_mtime(p[1]))
        pulled_at = last_commit.get('time')
        if pulled_at is not None and int(_authored_mtime(work_dir)) > pulled_at:
            fork_id = f'it{int(new_id[2:]) + 1}'
            fork_dir = os.path.join(task['dir'], 'iterations', fork_id)
            copy_mockup(work_dir, fork_dir)
            _touch_tree(fork_dir)
            fork = _stamp_author({'id': fork_id, 'date': time.strftime('%d.%m.%Y %H:%M'),
                                  'note': 'продовження моєї роботи — з '
                                          f'{src_name} приїхала старша версія',
                                  'published': False, 'from': work_id})
            its.append(fork)
            continue_from = work_id
    _adopt_publish_state(meta, state, task)
    # после подтягивания зеркало = origin → отпечаток «синхронизировано с этой версией»
    meta['gitlab'] = {**(meta.get('gitlab') or {}), 'synced_hash': mockup_hash(src)}
    save_meta(task, meta)
    git_autocommit(task['dir'], f'iteration {new_id}: {note}'
                   + (f'; {fork["id"]}: форк для продовження' if fork else ''))
    return {'ok': True, 'iteration': entry, 'fork': fork, 'continue_from': continue_from}


def mark_opened(cfg, tid):
    """Позначити, що задачу ЩОЙНО відкрили: `opened` (ISO UTC) на записі задачі.

    ⛔ НАВІЩО (fb-22092026-ca6975). Дропдаун задач ішов у порядку ВСТАВКИ в
    `tasks.json`, тобто створення: на 20+ задачах ті, з якими працюєш зараз,
    опинялись унизу, за краєм екрана. «Останні відкриті зверху» було неможливим
    узагалі — мітки відкриття не існувало в жодному полі.

    Поле МАШИННЕ: у `registry.SHARED` його немає, тож у спільний реєстр воно не
    їде — «що я відкривав» у кожного своє. ISO-рядок, а не число: сортується
    лексикографічно й читається очима в самому файлі.
    """
    task = cfg.get('tasks', {}).get(tid)
    if task is not None:
        task['opened'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def tasks_by_recent(cfg):
    """Задачі для перемикача: останні відкриті зверху, решта — у хвіст у
    колишньому порядку (задачі, заведені до мітки, не мусять перемішатись).
    Сортування стабільне, тож рівні мітки теж зберігають порядок файла."""
    items = list(cfg.get('tasks', {}).items())
    return sorted(items, key=lambda kv: _opened_mark(kv[1]), reverse=True)


def _opened_mark(task):
    """Мітка «відкрито» для сортування: лише рядок (ISO, її ставить `mark_opened`). `opened`
    правлять і руками — число, список, `true`, `null`: порівняння `int` із `str` — `TypeError`, і
    ним падав `/api/tasks` (зʼєднання рвалось без відповіді). Не-рядок = «без мітки» (`''`):
    у хвіст, у порядку файла, як задачі, заведені до мітки."""
    opened = task.get('opened')
    return opened if isinstance(opened, str) else ''


def _space_id(sp):
    """Id простору для відповідей API; `None`, коли простору нема: шар вимкнено (неявний
    простір — не простір для UI, див. `spaces.describe`) чи просторів нема взагалі."""
    return sp['id'] if sp is not None and spaces.layer_on() else None


#: Межі міток задачі (4b-3): не більше `TAGS_MAX` міток, кожна 1…`tracks.TAG_MAX_LEN` знаків, без коми (вона — роздільник у
#: формі) і без керівних знаків. Самі правила мітки (`TAG_BAD`, `clean_tag`, `read_tag`) — в `tracks`: ті самі читає
#: похідна мітка напрямку, а копії розійшлись би.
TAGS_MAX = 10
#: Дешева відсічка ДО поелементної роботи: список довший за це — `bad-tags` (до `TAGS_MAX` після дедуплікації ще далеко, але
#: мільйонний список не обходимо).
TAGS_RAW_MAX = 100


class TagsError(ValueError):
    """Мітки не за правилами (`bad-tags`): не список, елемент не рядок, задовгий, з комою чи керівним знаком, понад `TAGS_MAX`."""


def normalize_tags(raw):
    """Вхідні мітки (API) → список: обрізані, внутрішні пробіли стиснуті, порожні відкинуто, дублікати без урахування регістру
    відкинуто (лишається перший запис). Порушення правил — `TagsError` (людина бачить, що не так, а не тихе обрізання)."""
    if not isinstance(raw, list):
        raise TagsError('tags must be a list of strings')
    if len(raw) > TAGS_RAW_MAX:
        raise TagsError(f'at most {TAGS_MAX} tags')
    out, seen = [], set()
    for x in raw:
        if not isinstance(x, str):
            raise TagsError('tags must be a list of strings')
        # ⛔ Керівні знаки (і `\n`/`\t` усередині) перевіряються ДО стиснення пробілів: `split()` мовчки склеїв би `a\nb` в `a b`,
        # а людина мусить побачити відмову, а не тихо змінену мітку.
        stripped = x.strip()
        if tracks.TAG_BAD.search(stripped):
            raise TagsError(f'a tag is 1..{tracks.TAG_MAX_LEN} characters without commas or control characters')
        tag = tracks.clean_tag(stripped)
        if not tag:
            continue
        if len(tag) > tracks.TAG_MAX_LEN:
            raise TagsError(f'a tag is 1..{tracks.TAG_MAX_LEN} characters without commas or control characters')
        if tag.casefold() not in seen:
            seen.add(tag.casefold())
            out.append(tag)
    if len(out) > TAGS_MAX:
        raise TagsError(f'at most {TAGS_MAX} tags')
    return out


def task_tags(task, sp=None):
    """Мітки задачі для екрана й API. Є ключ `tags` — лише вони (навіть `[]`: людина свідомо прибрала всі); зіпсовані елементи
    (руками вписаний файл) тихо відкидаються — читання не кидає, і на `TAGS_MAX` скан зупиняється. Ключа нема — похідна мітка
    напрямку задачі (`tracks.label_tag`: `label` напрямку простору, невідомий напрямок — як є) або `[]`. `sp` — простір задачі (запис реєстру) або вже пораховане `_TrackView` цього простору (цикл по задачах рахує його
    ОДИН раз: інакше на кожну задачу читався б `space.json`, реєстр і перевірки шляхів); без нього — простір запиту. ⛔ Похідна проходить ТІ САМІ правила, що
    збережені мітки (`tracks.read_tag`): діалог правки заповнюється поточними мітками, і напрямок із комою чи на 300 знаків
    після збереження розпався б або не пройшов `bad-tags`; такий напрямок — без похідної мітки."""
    if isinstance(task, dict) and 'tags' in task:
        raw = task['tags']
        out, seen = [], set()
        for x in raw if isinstance(raw, list) else []:
            tag = tracks.read_tag(x)
            if tag and tag.casefold() not in seen:
                seen.add(tag.casefold())
                out.append(tag)
                if len(out) >= TAGS_MAX:
                    break
        return out
    if tracks.of_task(task) is None:
        return []                                # простору й напрямків не питаємо, поки похідна мітка справді не потрібна
    view = _as_view(sp)
    tag = tracks.label_tag(view.lite, task)
    return [tag] if tag else []


# ---------- Напрямки простору (4d-1): звідки беруться, тека, репо, ДС ----------
#
# Спека 2026-11-04-space-tracks-design.md §2–§4, §6. Ядро (`tracks`) чисте й про простори не знає; тут — що з кожного простору
# беруться напрямки: УСІ простори (ЛІГА теж) — масив `tracks` у їхньому `space.json`. 4d-4a: неявного адаптера з кореня старого
# `tasks.json` більше нема (його копія — лише в `liga_migrate`, для кроку `liga-4d4a`); шар вимкнено — напрямків нема.

def _request_space():
    """Простір запиту (запис реєстру; шар вимкнено — неявний) або `None`. Не кидає: читач міток не має права обвалити відповідь."""
    try:
        return spaces.active_space()
    except (spaces.SpacesError, OSError):
        return None


def _own_tracks(sp):
    """`(tracks, default_track)` — СИРІ значення з `space.json` простору, коли в ньому є ключ `tracks`-СПИСОК; інакше `None`
    (простору чи теки нема, файл не читається чи не обʼєкт, ключа нема чи він не список)."""
    path = sp.get('path') if isinstance(sp, dict) else None
    if not isinstance(path, str) or not path:
        return None
    try:
        data = spaces._read_json(os.path.join(path, 'space.json'))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get('tracks'), list):
        return None
    return data['tracks'], data.get('default_track')


def _drop_foreign_roots(sp, items):
    """`root: None` для кореня, що збігається зі шляхом ІНШОГО простору реєстру чи лежить у ньому (і навпаки: чужий простір
    усередині кореня) — перевірка `spaces.check_new_path` над реєстром БЕЗ власного запису простору: корінь усередині власного
    простору дозволений. ⛔ `tracks.normalize` перевіряє `root` з ПОРОЖНІМ реєстром (він чистий і реєстру не бачить), тож
    перетин з чужим простором ловиться лише тут: задачі напрямку лягали б у чужий простір і зʼявлялись у його «Задачах».
    Реєстр не прочитати — корені не перевірити, тож їх нема (закрито, а не пропущено)."""
    try:
        others = {'spaces': [e for e in spaces.read_registry()['spaces'] if e.get('id') != sp.get('id')]}
    except spaces.SpacesError:
        others = None
    out = []
    for t in items:
        if t['root'] is not None:
            try:
                ok, why = spaces.check_new_path(t['root'], others, []) if others is not None else (None, 'registry')
            except (OSError, ValueError):
                ok, why = None, 'fs'
            if why is not None:
                t = {**t, 'root': None}
        out.append(t)
    return out


_LAZY = object()


class _TrackView:
    """Напрямки ОДНОГО простору, пораховані один раз і ліниво: `sp`, `tracks`, `default`. Не кидає (як і
    `tracks.normalize`). Цикл по задачах (`_task_rows`, `tasks_overview`, `?all=1`) будує його раз і передає вниз
    (`task_tags`, `task_ds`): інакше КОЖНА задача читала б `space.json`, реєстр і міряла `check_new_path` по кореню кожного
    напрямку (O(задач × напрямків) роботи з файловою системою).

    `roots=False` — для читача, якому потрібні лише `id`/`label`/дефолт (`spaces_listing`): корені напрямків не перевіряються
    ні проти файлової системи (`tracks.normalize(roots=False)`), ні проти реєстру просторів (`_drop_foreign_roots` не кличеться) —
    `root` усіх напрямків тоді `None`, а `repo`/`ds` не змінюються. ⛔ Корінь на відімкненому чи повільному томі інакше гальмував би
    `GET /api/spaces`: перевірка — `realpath` по кожному напрямку кожного простору плюс `read_registry()` на простір.

    `sp` — запис реєстру, `None` (простору нема: нема й напрямків) або `_LAZY` (простір запиту питається аж на першу потребу —
    відповідь без жодної похідної мітки реєстру не читає взагалі). ⛔ Простір передається ЯВНО: `?all=1` обходить простори поза
    `with request_space(...)`, і мітки, пораховані щодо простору того, хто кличе, брехали б."""

    def __init__(self, sp=_LAZY, roots=True):
        self._sp = sp
        self._roots = roots
        self._own = _LAZY
        self._items = _LAZY
        self._lite = _LAZY

    @property
    def sp(self):
        if self._sp is _LAZY:
            self._sp = _request_space()
        return self._sp

    @property
    def _raw(self):
        """Сирі `(tracks, default_track)` з `space.json` простору або `None` (див. `_own_tracks`)."""
        if self._own is _LAZY:
            self._own = _own_tracks(self.sp)
        return self._own

    def _light(self):
        """`(tracks, default)` БЕЗ перевірки коренів (`tracks.normalize(roots=False)`, `root` скрізь `None`) — для читача, якому
        потрібні лише `id`/`label`/`ds`/дефолт (`task_tags`, `task_ds`, `spaces_listing`). Рахується один раз на вигляд.
        ⛔ Перевірка кореня — `realpath` плюс читання реєстру: на /api/task, огляді задач і сторінках задач вона б
        ішла без потреби (корінь потрібен лише створенню задачі: `track_root`)."""
        if self._lite is _LAZY:
            sp = self.sp
            if sp is None or self._raw is None:
                self._lite = ([], None)
            else:
                items = tracks.normalize(self._raw[0], sp.get('path'), roots=False)
                self._lite = (items, tracks.default_id(items, self._raw[1]))
        return self._lite

    @property
    def lite(self):
        return self._light()[0]

    def _load(self):
        if self._items is _LAZY:
            if not self._roots or self.sp is None or self._raw is None:
                self._items = self._light()
            else:
                items = tracks.normalize(self._raw[0], self.sp.get('path'), roots=True)
                self._items = (_drop_foreign_roots(self.sp, items), self._light()[1])
        return self._items

    @property
    def tracks(self):
        return self._load()[0]

    @property
    def default(self):
        return self._load()[1]


def _as_view(sp):
    """`sp` — уже `_TrackView` (лишається), запис реєстру, `None` (простір запиту, ліниво)."""
    if isinstance(sp, _TrackView):
        return sp
    return _TrackView(_LAZY if sp is None else sp)


def space_tracks(sp):
    """Напрямки простору `sp` (запис реєстру) → `(tracks, default_id)`; див. блок вище. Звичайний простір без `tracks`, із
    битим `space.json` чи `sp=None` — `([], None)`."""
    view = _TrackView(sp)
    return view.tracks, view.default


def track_root(sp, track_id):
    """Тека, у якій лягає тека НОВОЇ задачі напрямку `track_id` у просторі `sp` (для ВСІХ просторів однаково): знайдений напрямок
    → його `root`; невідомий → `root` дефолтного; `root` нема чи напрямків нема → шлях простору; простору чи його шляху нема
    (шар вимкнено) → `None` (викликач бере `default_task_root(cfg)`)."""
    view = sp if isinstance(sp, _TrackView) else _TrackView(sp)      # `None` тут — «простору нема», а не «простір запиту»
    if view.sp is None:
        return None
    t = tracks.find(view.tracks, track_id) or tracks.find(view.tracks, view.default)
    if t is not None and t['root']:
        return t['root']
    return view.sp.get('path') or None


def track_repo(sp, track_id):
    """Типовий репозиторій макетів напрямку `track_id` або `''`. Невідомий напрямок репо НЕ бере з дефолтного (маршрут його
    відмовить раніше)."""
    view = sp if isinstance(sp, _TrackView) else _TrackView(sp)
    if not isinstance(track_id, str) or view.sp is None:
        return ''
    t = tracks.find(view.tracks, track_id)
    return t['repo'] if t else ''


def task_ds(task, sp=None):
    """Значення `?ds=` для інспектора в розмітці макета задачі: `ds` напрямку задачі (`tracks.of_task`: `track`) у просторі `sp`
    (запис реєстру чи `_TrackView`; без нього — простір запиту) або `''` (шаблон `[a-z0-9-]{1,32}` і `strip()` перевіряє
    `inspector_ds_arg`). Знайдений напрямок говорить сам — його поле `ds` (`''` — статичної ДС нема, і це відповідь, а не відсутність);
    напрямок не знайдено (простір без напрямків чи невідомий id) — саме значення, як 0.14.0 (еталон
    `page-none-project.html` тримає `?ds=tool&sp=…` для задачі звичайного простору): невідома ДС вимикає звірку в інспекторі.
    Не рядок (`5`) — `''` (0.14.0 рвав зʼєднання: свідома відмінність)."""
    v = tracks.of_task(task)
    if v is None:
        return ''
    view = _as_view(sp)
    t = tracks.find(view.lite, v)                         # простору нема — напрямків нема — значення як є, як 0.14.0
    return t['ds'] if t else v


def _task_rows(cfg, sp=None, items=None):
    """Рядки `GET /api/tasks` одного файла задач (перемикач задач).

    `missing` — теки задачі нема на ЦІЙ машині (реєстр їде в git, теки ні): перемикач не
    пускає в таку задачу й каже причину наперед. Лише `isdir`, без читання вмісту —
    відповідь лишається дешевою.

    `track` — напрямок задачі (`tracks.of_task`: лише `track`); `profile` рядок API більше не віддає (4d-4a).

    `sp` — простір цього файла задач (запис реєстру); без нього — простір запиту. ⛔ `?all=1` передає його ЯВНО: рядки збираються
    поза `with request_space(...)`, і мітки щодо простору того, хто кличе, брехали б. Напрямки простору рахуються ОДИН раз.
    `items` — уже впорядковані `tasks_by_recent(cfg)` (`?all=1` рахує їх у вузькому `try`, див. `_all_space_task_rows`)."""
    sp = _as_view(sp)
    return [{'id': k, 'title': v.get('title', k), 'jira': v.get('jira'),
             'track': tracks.of_task(v),
             'missing': not (isinstance(v.get('dir'), str) and os.path.isdir(v['dir'])),
             'tags': task_tags(v, sp)}
            for k, v in (tasks_by_recent(cfg) if items is None else items)]


def _all_space_task_rows():
    """Рядки `GET /api/tasks?all=1`: задачі ВСІХ просторів реєстру, кожна з `space` (id
    простору; `None`, коли шар вимкнено). Порядок — реєстру, всередині простору — як у
    перемикачі. Простір, файл задач якого не прочитати чи не зібрати в порядок, пропускається:
    список решти просторів важливіший за один битий. Id, що є у двох просторах, видно двічі —
    це й є дубль, який треба побачити.

    Простір запиту переключається `request_space` і ПОВЕРТАЄТЬСЯ: хто кличе, лишається у
    своєму просторі (`with` повертає попереднє значення навіть після винятку).
    Реєстр читається `read_registry()`: вхід запиту вже мігрував його (`_pin_current_space`).

    ⛔ `try` стоїть ЛИШЕ над читанням файла й сортуванням (`load_tasks`, `tasks_by_recent`): файл, який `load_tasks` пропустив, але
    впорядкувати не вийшло (ручна правка), — такий самий битий простір. Складання рядків (мітки, напрямки) — ПОЗА ним: справжня
    вада в обчисленні мітки не мусить мовчки викинути ЦІЛИЙ простір зі списку (так вона лишилась би невидимою)."""
    rows = []
    for sp in spaces.read_registry()['spaces']:
        try:
            with spaces.request_space(sp['id']):
                cfg = load_tasks()
            items = tasks_by_recent(cfg)
        except (SpaceUnavailable, AttributeError, TypeError):
            continue
        rows += [{**r, 'space': _space_id(sp)} for r in _task_rows(cfg, sp, items)]
    return rows


# ---------- Екран «Задачі»: мої + команда (батч 1.52) ----------

TEAM_TTL = 60          # кеш рядків дашборда, с
TEAM_ERR_TTL = 10      # помилку кешуємо коротше — щоб «Спробувати ще» мало сенс
#: Кеш рядків команди НА ПРОСТІР (4c-1): `{id простору: {'at', 'rows', 'error', 'rowsAt', 'who'}}` (`''` — шлях ЛІГИ без простору
#: запиту: інструменти, тести). До 4c-1 кеш був один на процес, і відмова одного простору ставала «останнім відомим» станом
#: іншого. `who` — хто дав рядки (`'legacy'` чи id модуля): інший постачальник = порожній запис, бо рядки старого не можна
#: показувати як «останні відомі» нового.
_TEAM_CACHE = {}
_TEAM_LOCK = threading.Lock()
TEAM_ISOLATED = 'вимкнено в ізольованому прогоні (DC_TASKS_FILE / DC_NO_OVERVIEW)'
TEAM_NO_PROVIDER = 'вимкнено: у просторі нема постачальника командного дашборда'


def _team_fetch(space, prov):
    """Один справжній прохід за рядками команди: `(rows, error)`, не кидає. `prov` — постачальник ролі `dashboard`
    простору запиту (`Module`); `space` — запис простору (для `module_ctx`).

    Порядок джерел важливий, і ⛔ другий пункт — закон ізоляції (той самий, що в `notify_call` і `_registry_push`):
    `DC_TASKS_FILE`/`DC_NO_OVERVIEW` означають «стан не справжній цієї машини», тож ходити з нього в живий Supabase не можна.
    Усі три пункти — лише для запису `shared_state` (ЛІГА):
    1. `DC_TEAM_FAKE` — локальний JSON-масив замість бази (шов для тестів; рядки як є, без відбору ключів);
    2. ізольований прогін без шва — модуль НЕ кличеться, мережі НЕМАЄ, чесне пояснення замість рядків;
    3. інакше модуль із `module_ctx(space, prov)` — налаштування й секрет ЗАПИСУ.
    Виклик модуля — `dashboard.rows` (`READ_TIMEOUT`): екран «Задачі» — перша сторінка, і висіти на ній через мертвий VPN
    довше за кілька секунд не можна.
    `ModuleError` (нема конфігу, збій модуля, `check-timeout`) — це ТЕКСТ для плашки, не помилка коду; `except Exception`
    для решти, а не вузький перелік: контракт «ніколи не кидає» тримає екран живим для «Моїх» навіть тоді, коли відповідь бази —
    не те, що очікували."""
    try:
        if _shared_module(space, prov):
            # ⛔ `shared_state`-модуль іде законом ізоляції (4d-3a): шов → ізоляція → живий (`isolation.route`)
            kind, fake = isolation.route('dashboard')
            if kind == 'fake':
                with open(fake, encoding='utf-8') as fh:
                    data = json.load(fh)
                if not isinstance(data, list):
                    raise ValueError('очікувався масив рядків overview_projects')
                return [r for r in data if isinstance(r, dict)], None
            if kind == 'isolated':
                return [], TEAM_ISOLATED
            return dashboard.rows(prov, deai_modules.module_ctx(space, prov)), None
        return dashboard.rows(prov, deai_modules.module_ctx(space, prov)), None
    except deai_modules.ModuleError as e:
        return [], (e.message or e.code)[:200]
    except Exception as e:  # noqa: BLE001 — «Мої» мусять жити без команди
        if not isinstance(e, (OSError, ValueError)):
            # Не мережа й не формат даних — імовірно, ПОМИЛКА КОДУ: у stderr, щоб
            # вона не маскувалась під «команда недоступна». Поведінка та сама.
            print(f'team_rows: {type(e).__name__}: {e}', file=sys.stderr)
        return [], (str(e) or type(e).__name__)[:200]


def _shared_module(space, prov):
    """4d-3a: явний `Module` із `shared_state: true` — спільний стан ЛІГИ: ролі `dashboard`/`tracker`/`notify` і синк ведуть його за
    законом ізоляції (`isolation.route`); живий виклик — модулем із `module_ctx`."""
    # ⛔ Предикат БЕЗ походження (як у 4d-3a): свій модуль із `shared_state` в ізольованому прогоні й далі йде законом маршруту
    # (`isolation.route`: шов/ізоляція), а не живим викликом зі справжніми секретами. Умова «вбудований» — лише в гілках ізоляції
    # `comments_route`/`vcs_provider` (`_builtin_shared`), де підставляється ключ кореня задач (4d-3b, ревʼю 2).
    return isinstance(prov, deai_modules.Module) and deai_modules.shared_state(space, prov.id)


def _builtin_shared(space, prov):
    """4d-3b: `_shared_module` І вбудований модуль (`origin == 'builtin'`) — ЄДИНА умова гілок ізоляції `comments_route` і
    `vcs_provider`: свій модуль із вручну виставленим `shared_state` не дістає ключ кореня задач і лишається звичайним модулем."""
    return _shared_module(space, prov) and getattr(prov, 'origin', 'builtin') == 'builtin'


def team_resolve():
    """`(space, prov)` ролі `dashboard` для простору ЗАПИТУ: `prov` — `Module` чи `None` (нікого: вкладки «Команда»
    нема). `space` — запис простору (лише для модуля; `None` для решти). Кидає `spaces.SpacesError` (реєстр не прочитати) і
    `deai_modules.ModuleError` (свій модуль «на папері», `space.json` не читається): це НЕ «нікого» — вкладка лишається, а плашка
    називає причину (рішення 4c-1: зламаний власний модуль не ховає вкладку мовчки)."""
    prov = deai_modules.provider('dashboard')
    return (spaces.active_space() if isinstance(prov, deai_modules.Module) else None), prov


def team_snapshot(now=None, refresh=False, resolved=None):
    """`(rows, error, rows_at)`: як `team_rows`, плюс епоха ОСТАННЬОГО УСПІШНОГО
    читання (`None` — успіху ще не було). Не кидає.

    Кеш на `TEAM_TTL`, помилка — на коротший `TEAM_ERR_TTL`; `refresh=True` його
    оминає (лише запис СВОГО простору). Без кешу кожен вхід на екран був би запитом у Supabase, а сервер
    багатопотоковий — тому читання й запис кешу під `_TEAM_LOCK`, ВКЛЮЧНО з самим
    запитом: другий потік чекає перший і бере вже готове, а не б'є в базу ще раз.
    ⛔ Збій НЕ стирає останні відомі рядки: мертвий VPN на хвилину не має робити
    вкладку «Команда» порожньою. На помилці оновлюються лише `error` і `at`
    (щоб повтор ішов за `TEAM_ERR_TTL`); рядки й `rowsAt` лишаються з останнього
    успіху, а екран за `rows_at` пише «дані на <час>».
    `now` — шов для тестів (епоха, с); `0 <= now - at` стереже годинник, що
    стрибнув назад: інакше застарілий кеш жив би, поки час не наздожене.

    Хто дає рядки — `team_resolve()` (маршрут, що вже вирішив, передає `resolved=(space, prov)`: без другого читання реєстру й
    каталогу). Нікого, збій реєстру чи рішення ролі — рання відповідь тієї ж форми (`[]` + пояснення), БЕЗ кешу: відмова
    одного простору не мусить стати «останнім відомим» станом іншого. ⛔ Кеш ключується ПРОСТОРОМ (`_TEAM_CACHE`)."""
    if resolved is None:
        try:
            resolved = team_resolve()
        except spaces.SpacesError as e:
            # Не «простір без дашборда», а збій реєстру: причина називається, запиту так само нема.
            return [], f'реєстр просторів не читається ({e.code})', None
        except deai_modules.ModuleError as e:
            return [], (e.message or e.code)[:200], None
    space, prov = resolved
    if prov is None:
        return [], TEAM_NO_PROVIDER, None
    who = deai_modules.api_value(prov)
    key = spaces.request_space_id() or ''
    now = time.time() if now is None else now
    with _TEAM_LOCK:
        c = _TEAM_CACHE.get(key)
        if c is None or c['who'] != who:
            c = _TEAM_CACHE[key] = {'at': 0.0, 'rows': None, 'error': None, 'rowsAt': None, 'who': who}
        ttl = TEAM_ERR_TTL if c['error'] else TEAM_TTL
        if not refresh and c['rows'] is not None and 0 <= now - c['at'] < ttl:
            return list(c['rows']), c['error'], c['rowsAt']
        rows, error = _team_fetch(space, prov)
        if error:
            rows = c['rows'] or []
            c.update(at=now, rows=rows, error=error)
        else:
            c.update(at=now, rows=rows, error=None, rowsAt=now)
        return list(rows), error, c['rowsAt']


def team_rows(now=None, refresh=False):
    """`(rows, error)` — `team_snapshot` без `rows_at`."""
    return team_snapshot(now, refresh)[:2]


# ---------- Статуси задач від трекера (4c-2): окремий кеш на простір ----------

TRACKER_TTL = 300       # статуси міняються рідко, а Jira повільніший за базу дашборда
TRACKER_ERR_TTL = 30    # помилку кешуємо коротко: «Спробувати ще» має сенс, а мертвий трекер не отримує запит на кожен вхід
#: Кеш статусів трекера НА ПРОСТІР: `{id простору: {'at', 'statuses', 'error', 'okAt', 'who', 'keys'}}` (`''` — шлях ЛІГИ без простору
#: запиту: інструменти, тести). `who` — хто дав статуси (`'legacy'` чи id модуля): інший постачальник = порожній запис (статуси
#: старого не можна показувати як «останні відомі» нового). `keys` — ключі, які ПИТАЛИ (запит бере перші 100 — решта лишається без статусу, а не нескінченно «новою»): новий ключ задачі, якого тут
#: нема, — новий запит, а не «статус невідомо» ще на `TRACKER_TTL`.
_TRACKER_CACHE = {}
#: ⛔ ОКРЕМИЙ від `_TEAM_LOCK`: запит у трекер іде ПІД локом (другий потік чекає перший і бере готове), а мертвий Jira тримає його
#: до `tracker.READ_TIMEOUT`. Спільний лок зробив би так, що трекер, який не відповідає, гальмує й рядки команди (і навпаки).
_TRACKER_LOCK = threading.Lock()


def tracker_resolve():
    """`(space, prov)` ролі `tracker` для простору ЗАПИТУ: `prov` — `Module` чи `None` (трекера нема). Як
    `team_resolve`: `space` — запис простору лише для модуля. Кидає `spaces.SpacesError` і `deai_modules.ModuleError` (свій модуль
    «на папері», `space.json` не читається)."""
    prov = deai_modules.provider('tracker')
    return (spaces.active_space() if isinstance(prov, deai_modules.Module) else None), prov


def _tracker_fetch(space, prov, keys):
    """Один справжній прохід за статусами `keys`: `(statuses, error)` або `None` (= трекера нема: ізоляція ЛІГИ). Не кидає.
    `prov` — постачальник ролі `tracker` простору запиту (`Module`); `space` — запис простору (для `module_ctx`).

    Порядок джерел для запису `shared_state` (ЛІГА); ⛔ другий пункт — закон ізоляції (той самий, що в `_team_fetch`, `notify_call` і `_registry_push`):
    `DC_TASKS_FILE`/`DC_NO_OVERVIEW` означають «стан не справжній цієї машини», тож ходити з нього в живу Jira не можна;
    1. `DC_TRACKER_FAKE` — локальний JSON `{ключ: {name, cat}}` замість Jira (шов для тестів; `tracker.normalize` до `keys`);
    2. ізольований прогін без шва — `None`: екран поводиться як без трекера (`tracker: null`), помилки НЕМАЄ (на відміну від
       «Команди» тут нічого пояснювати: статуси лишаються з рядків дашборда, як і були);
    3. інакше модуль із `module_ctx(space, prov)` — налаштування й секрет ЗАПИСУ; нема конфігу — `tracker-unconfigured` (текст для
       плашки, мережі нема).
    Немає що питати (`keys` порожні) — `({}, None)` БЕЗ виклику й без конфігу: нічого не мовчить, нема за що показувати плашку.
    Виклик — `tracker.statuses` (`READ_TIMEOUT`/`READ_SOCKET_S`): екран «Задачі» — перша сторінка, і висіти на ній через мертвий VPN
    довше за кілька секунд не можна. Помилка — ТЕКСТ для плашки: `ModuleError` — його повідомлення (ядро вже вичистило секрети),
    решта — лише назва класу (`str(e)` чужого винятку не чищений і міг би винести секрет на екран)."""
    keys = list(keys)[:tracker.BATCH]
    try:
        if _shared_module(space, prov):
            kind, fake = isolation.route('tracker')
            if kind == 'fake':
                with open(fake, encoding='utf-8') as fh:
                    data = json.load(fh)
                return tracker.normalize(data, keys), None
            if kind == 'isolated':
                return None
            if not keys:       # ⛔ ПІСЛЯ шва й ізоляції (як у 0.15.0): ізольований прогін без ключів — `None`, а не `({}, None)`
                return {}, None
            module, ctx = prov, deai_modules.module_ctx(space, prov)         # `shared_state` (4d-3a): модуль із ctx запису
        else:
            if not keys:
                return {}, None
            module, ctx = prov, deai_modules.module_ctx(space, prov)
        return tracker.statuses(module, ctx, keys, timeout=tracker.READ_TIMEOUT, socket_s=tracker.READ_SOCKET_S), None
    except deai_modules.ModuleError as e:
        return {}, (e.message or e.code)[:200]
    except Exception as e:  # noqa: BLE001 — «Мої» мусять жити без трекера
        if not isinstance(e, (OSError, ValueError)):
            # Не мережа й не формат даних — імовірно, ПОМИЛКА КОДУ: назва класу в stderr (без `str(e)`), щоб вона не маскувалась
            # під «трекер недоступний». Поведінка та сама.
            print(f'tracker_statuses: {type(e).__name__}', file=sys.stderr)
        return {}, type(e).__name__


def tracker_snapshot(keys, now=None, refresh=False, resolved=None):
    """`None` (трекера нема: екран бере статуси лише з рядків дашборда) чи `(statuses, error, ok_at)`: `statuses` —
    `{ключ: {'name', 'cat'}}`, `ok_at` — епоха ОСТАННЬОГО УСПІШНОГО читання (`None` — успіху ще не було). Не кидає.

    Кеш на простір запиту (`_TRACKER_CACHE`) під `_TRACKER_LOCK`, ВКЛЮЧНО з самим запитом (сервер багатопотоковий: другий потік чекає
    перший і бере готове). `TRACKER_TTL`, помилка — коротший `TRACKER_ERR_TTL`; `refresh=True` оминає кеш (лише СВОГО простору).
    Новий ключ, якого нема серед запитаних у кеші, — теж запит; інший постачальник (`who`) — чистий запис.
    ⛔ Збій НЕ стирає останні відомі статуси: мертвий Jira на хвилину не має знімати бейджі з карток. На помилці оновлюються
    лише `error` і `at` (щоб повтор ішов за `TRACKER_ERR_TTL`), статуси й `okAt` лишаються з останнього успіху. Ключі збійного
    запиту додаються до `keys` запису: інакше новий ключ при мертвому трекері бив би в нього на КОЖЕН вхід, а не раз на
    `TRACKER_ERR_TTL`. `now` — шов для тестів; `0 <= now - at` стереже годинник, що стрибнув назад (як у `team_snapshot`).

    Хто дає статуси — `tracker_resolve()` (маршрут, що вже вирішив, передає `resolved=(space, prov)`). Нікого — `None`. Збій реєстру
    чи рішення ролі — рання відповідь тієї ж форми (порожні статуси + пояснення), БЕЗ кешу: відмова одного простору не мусить
    стати «останнім відомим» станом іншого. Ізоляція ЛІГИ (`_tracker_fetch` → `None`) — теж `None` і теж без кешу."""
    if resolved is None:
        try:
            resolved = tracker_resolve()
        except spaces.SpacesError as e:
            return {}, f'реєстр просторів не читається ({e.code})', None
        except deai_modules.ModuleError as e:
            return {}, (e.message or e.code)[:200], None
    space, prov = resolved
    if prov is None:
        return None
    wanted = list(dict.fromkeys(k for k in keys if isinstance(k, str)))     # чужий ввід: не-рядки не хешуємо й не питаємо
    who = deai_modules.api_value(prov)
    key = spaces.request_space_id() or ''
    now = time.time() if now is None else now
    with _TRACKER_LOCK:
        c = _TRACKER_CACHE.get(key)
        if c is None or c['who'] != who:
            c = {'at': 0.0, 'statuses': None, 'error': None, 'okAt': None, 'who': who, 'keys': frozenset()}
        ttl = TRACKER_ERR_TTL if c['error'] else TRACKER_TTL
        if (not refresh and c['statuses'] is not None and c['keys'].issuperset(wanted)
                and 0 <= now - c['at'] < ttl):
            return dict(c['statuses']), c['error'], c['okAt']
        got = _tracker_fetch(space, prov, wanted)
        if got is None:
            return None
        statuses, error = got
        if error:
            c.update(at=now, statuses=c['statuses'] or {}, error=error, keys=c['keys'] | frozenset(wanted))
        else:
            c.update(at=now, statuses=statuses, error=None, okAt=now, keys=frozenset(wanted))
        _TRACKER_CACHE[key] = c
        return dict(c['statuses']), c['error'], c['okAt']


def task_thumb_path(task):
    """`(abs_path, sha)` кадру для картки задачі, або None. Не кидає.

    Кадр беремо з ОСТАННЬОЇ ітерації (`task_state()['last_iter']`): картка показує
    те, над чим працюють зараз. Спершу відкривані сторінки в їхньому порядку (перша
    сторінка — обличчя задачі), потім решта ключів манифеста; серед решти ширини
    (`…@390`) — у хвіст, щоб картка не показала мобільний кадр, коли є звичайний.
    Береться перший ключ із записом у манифесті І файлом `<key>.webp`.

    ⛔ Ключ із манифеста — чужий ввід (файл правлять руками й `gitlab_pull`): він
    проходить `SHOT_RE`, а realpath файла мусить лежати всередині realpath
    `shots/` — інакше symlink `home.webp → /etc/hosts` віддав би будь-який файл
    диска. Ті самі два замки, що в `_shot`; ціна помилки та сама."""
    try:
        it = task_state(task).get('last_iter')
        if not isinstance(it, str) or not NAME_RE.fullmatch(it):
            return None
        idir = _iter_dir(task, it)
        base = os.path.realpath(os.path.join(idir, 'shots'))
        with open(os.path.join(base, 'manifest.json'), encoding='utf-8') as fh:
            man = json.load(fh)
        shots = man.get('shots') if isinstance(man, dict) else None
        if not isinstance(shots, dict):
            return None
        try:
            ordered = [p.get('id') for p in pm.openable_pages(pm.read_pages(idir))
                       if isinstance(p, dict)]
        except (OSError, ValueError):     # pages.json зіпсований: лишаються ключі манифеста
            ordered = []
        rest = sorted((k for k in shots if k not in ordered), key=lambda k: '@' in str(k))
        for key in ordered + rest:
            entry = shots.get(key) if isinstance(key, str) else None
            if not isinstance(entry, dict) or not SHOT_RE.fullmatch(key):
                continue
            target = os.path.realpath(os.path.join(base, key + '.webp'))
            if not target.startswith(base + os.sep) or not os.path.isfile(target):
                continue
            sha = entry.get('sha')
            return target, (sha if isinstance(sha, str) else '')
        return None
    except Exception:  # noqa: BLE001 — картка без кадру, а не 500 на весь екран
        return None


def _thumb_url(tid, sha):
    """URL кадру картки. `v=<sha>` — ключ вічного кешу (хеш БАЙТІВ кадру, як у
    `shotVersion`): перезйомка дає інший URL. Без sha (старий манифест) `v` не
    додаємо — `/api/task-thumb` тоді віддасть `no-cache`, а не вічний кеш на нічому."""
    return f'/api/task-thumb?task={quote(tid, safe="")}' + (
        f'&v={quote(sha, safe="")}' if sha else '')


def _last_changed(task, st):
    """Епоха (с) останньої РОБОТИ в останній ітерації, або None. Той самий
    `_authored_mtime`, що рахує автосинк: свіжі кадри `shots/` — це «інструмент
    перезняв», а не «дизайнер правив», і картка не мусить молодшати від зйомки."""
    it = st.get('last_iter')
    if not st['dir_exists'] or not isinstance(it, str) or not NAME_RE.fullmatch(it):
        return None
    m = _authored_mtime(_iter_dir(task, it))
    return int(m) if m else None


def _trash_rows(cfg, sp=None):
    """Етап Д: рядки кошика простору для екрана «Задачі» — найновіші першими, без надгробків. Кадр — з ТЕКИ В КОШИКУ
    (`/api/task-thumb?…&trash=1`); мітки — як у «Моїх» (`task_tags`, похідна мітка напрямку для запису без власних)."""
    rows = []
    for tid, rec in task_trash.listing(cfg):
        entry, td = rec['entry'], rec.get('trashDir')
        found = (task_thumb_path({**entry, 'dir': td})
                 if isinstance(td, str) and td and task_trash.inside_trash(td) and NAME_RE.fullmatch(tid) else None)
        rows.append({'id': tid, 'title': entry.get('title', tid), 'jira': entry.get('jira'),
                     'tags': task_tags(entry, sp), 'at': rec.get('at'),
                     'thumb': (_thumb_url(tid, found[1]) + '&trash=1') if found else None})
    return rows


def tasks_overview(cfg, team, now=None, rows_at=None, tracker=None):
    """Відповідь `/api/tasks-overview` без `current`. ЧИСТА збірка: мережі нема,
    `team` = `(rows, error)` від `team_rows()`.

    `mine` — задачі цієї машини в порядку `tasks_by_recent`; `team.rows` — рядки
    дашборда, з позначкою `mine`. Поля Jira й лічильник коментарів живуть ЛИШЕ в
    дашборді, тож до своєї задачі вони підмішуються за id; немає рядка — `None`
    («невідомо»), а не 0: екран не обіцяє тиші, якої не знає.
    Статус Jira (4c-2) має два джерела з ПРІОРИТЕТОМ: свіжий статус від трекера (`tracker` = `(statuses, error, ok_at)` від
    `tracker_snapshot`, ключ — `task['jira']`) → рядок дашборда → `None`. Рядки «Команди» статусів трекера НЕ отримують (це
    чужі задачі й чужі статуси дашборда). Поле відповіді `tracker` — `None` (трекера нема: ізоляція ЛІГИ чи простір без нього)
    або `{'error', 'okAt'}`; `tracker=None` лишає поведінку знімка 0.12.0 з одним доданим `tracker: null`.
    Кадр своєї задачі — локальний (свіжіший), інакше `thumb_url` дашборда; у рядку
    команди — навпаки: те, що бачать усі, а локальний — лише коли його нема.
    `fetchedAt` — епоха, коли зібрано відповідь; `rowsAt` — коли рядки команди
    востаннє успішно прочитано з бази (`None` — ніколи; при помилці з кешованими
    рядками екран пише «дані на <rowsAt>»)."""
    now = time.time() if now is None else now
    rows, error = team
    tr_statuses, tr_error, tr_ok_at = tracker if tracker is not None else ({}, None, None)
    by_id = {r['id']: r for r in rows
             if isinstance(r, dict) and isinstance(r.get('id'), str)}
    mine, local = [], {}
    sp = _TrackView()                         # простір запиту й його напрямки — один раз і лише коли мітка справді потрібна
    for tid, task in tasks_by_recent(cfg):
        st = task_state(task)
        found = task_thumb_path(task) if NAME_RE.fullmatch(tid) else None
        if found:
            local[tid] = _thumb_url(tid, found[1])
        row = by_id.get(tid)
        jkey = task.get('jira')
        trk = tr_statuses.get(jkey) if isinstance(jkey, str) else None
        mine.append({
            'id': tid, 'jira': task.get('jira'), 'title': task.get('title', tid),
            'opened': task.get('opened'),
            'iterations': st['iterations'], 'pages': st['pages'],
            'iter': st['last_iter'], 'changed': _last_changed(task, st),
            'published': st['code_url'], 'missing': not st['dir_exists'],
            'thumb': local.get(tid) or (row.get('thumb_url') if row else None) or None,
            'jiraStatus': trk['name'] if trk else (row.get('jira_status') if row else None),
            'jiraCat': trk['cat'] if trk else (row.get('jira_status_cat') if row else None),
            'comments': (row.get('open_comments') or 0) if row else None,
            'tags': task_tags(task, sp),
        })
    tasks = cfg.get('tasks', {})
    team_out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = r.get('id')
        is_mine = isinstance(rid, str) and rid in tasks
        team_out.append({
            'id': rid, 'title': r.get('name') or rid, 'jira': r.get('jira'),
            'jiraStatus': r.get('jira_status'), 'jiraCat': r.get('jira_status_cat'),
            'comments': r.get('open_comments') or 0,
            'thumb': r.get('thumb_url') or (local.get(rid) if is_mine else None) or None,
            'preview': r.get('code_url'), 'updated': r.get('updated_at'),
            'designer': r.get('designer'), 'iterations': r.get('iterations'),
            'pages': r.get('pages'), 'mine': is_mine,
        })
    return {'mine': mine,
            'team': {'rows': team_out, 'error': error, 'fetchedAt': now,
                     'rowsAt': rows_at},
            'tracker': None if tracker is None else {'error': tr_error, 'okAt': tr_ok_at}}


# ---------- Задача з наявної теки (етап 3b, спека 2026-10-21-first-run-wizard-design.md) ----------

#: Стеля теки-джерела: випадково вибрана домашня тека чи корінь проєкту не мусить скопіювати півдиска. Константи
#: модуля — тест їх зменшує (`mock.patch.object`).
ADOPT_MAX_FILES = 2000
ADOPT_MAX_BYTES = 200 * 1024 * 1024
#: На БУДЬ-ЯКОМУ рівні теки-джерела не копіюються: історія git, залежності, сміття Finder.
_ADOPT_SKIP_ANY = frozenset({'.git', 'node_modules', '.DS_Store'})


#: Результат `Handler._adopt_source`: справжня тека-джерело, перелік файлів, байти й число пропущених посилань.
AdoptPlan = collections.namedtuple('AdoptPlan', 'real files bytes links')


class AdoptRefused(Exception):
    """Відмова прийняти теку-джерело: `code`, HTTP-`status` і додаткові поля тіла відповіді (`extra`)."""

    def __init__(self, code, status, message, **extra):
        super().__init__(message)
        self.code, self.status, self.extra = code, status, extra


def _adopt_walk_error(err):
    """`onerror` обходу: нечитабельна підтека НЕ відсіюється мовчки (макет вийшов би без неї), а зупиняє прийом —
    `OSError` летить у `_adopt_source` (400 `from-not-found`)."""
    raise err


def adopt_scan(src):
    """Обхід теки-джерела ДО будь-якого запису: `(файли, байти, пропущені посилання)`, де файли — відносні шляхи, які
    скопіює `adopt_copy`. Не копіюються ніколи: символьні посилання (файли й теки — копія лягла б вмістом поза
    текою-джерелом), `_ADOPT_SKIP_ANY` на будь-якому рівні, службове інструмента в корені (`_is_tool_junk`) і стан
    публікації `STATE_FILE` у корені (підпис чужої публікації в новій задачі збрехав би). Сокети й fifo — не файли.
    Більше `ADOPT_MAX_FILES` файлів чи `ADOPT_MAX_BYTES` байтів — `AdoptRefused('from-too-big', 413)` одразу, не
    дочитуючи (з числами на момент зупинки). Нечитабельна підтека чи файл, який мав бути скопійований, — `OSError`
    (підтека: `_adopt_walk_error`; файл: `PermissionError` тут) — маршрут відмовляє 400 `from-not-found`."""
    files, total, links = [], 0, 0
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False, onerror=_adopt_walk_error):
        rel = os.path.relpath(dirpath, src)
        top = rel == os.curdir
        keep = []
        for d in sorted(dirnames):
            if os.path.islink(os.path.join(dirpath, d)):
                links += 1
            elif d not in _ADOPT_SKIP_ANY and not (top and _is_tool_junk(d)):
                keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            p = os.path.join(dirpath, f)
            if os.path.islink(p):
                links += 1
                continue
            # `f == STATE_FILE` — паски й шлейки: у корені його вже відсіює `_is_tool_junk` (крапка на початку), тут
            # правило названо прямо, щоб воно не зникло разом зі зміною того предиката.
            if f in _ADOPT_SKIP_ANY or (top and (_is_tool_junk(f) or f == STATE_FILE)):
                continue
            if not os.path.isfile(p):
                continue
            if not os.access(p, os.R_OK):
                # `getsize` читати не просить: без цього файл пройшов би обхід і впав би на копії (500 із шляхом у тексті)
                raise PermissionError(errno.EACCES, 'a file of the folder is not readable')
            files.append(f if top else os.path.join(rel, f))
            total += os.path.getsize(p)
            if len(files) > ADOPT_MAX_FILES or total > ADOPT_MAX_BYTES:
                raise AdoptRefused('from-too-big', 413,
                                   f'the folder is too big for a mockup: over {ADOPT_MAX_FILES} files '
                                   f'or {ADOPT_MAX_BYTES // (1024 * 1024)} MB',
                                   files=len(files), bytes=total)
    return files, total, links


def adopt_copy(src, dst, files):
    """Копія переліку `adopt_scan` у `dst`: `(скопійовано файлів, байтів, пропущено)` — те, що Є на диску, а не те, що
    бачив обхід. Між обходом і копією теку-джерело можуть змінити: файл став посиланням, а ПІДТЕКУ (чи будь-яку
    складову шляху) підмінили посиланням назовні. Тому перед кожним файлом: лист — не посилання, і справжній шлях
    його теки збігається з шляхом від справжнього кореня джерела; інакше файл пропускається й рахується."""
    os.makedirs(dst, exist_ok=True)
    real_src = os.path.realpath(src)
    copied = nbytes = skipped = 0
    for rel in files:
        s = os.path.join(src, rel)
        want = os.path.normpath(os.path.join(real_src, os.path.dirname(rel)))
        if os.path.islink(s) or os.path.realpath(os.path.dirname(s)) != want:
            skipped += 1
            continue
        d = os.path.join(dst, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        copied += 1
        nbytes += os.path.getsize(d)
    return copied, nbytes, skipped


class TaskRefused(ValueError):
    """`task_new` відмовила на вході. Підклас `ValueError` із ТИМ САМИМ текстом, що був у голого
    `ValueError`; код — атрибут (`/api/task-new` відображає за `.code`, а не за текстом)."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


#: Останній рубіж кореня теки нової задачі: простір шляху не має (шар вимкнено) і виклик не дав `root`.
DEFAULT_TASK_ROOT = '~/deai-work'


def default_task_root(cfg):
    """Спільний корінь тек задач із кореня файла задач (`design_work_root`), інакше `DEFAULT_TASK_ROOT`; `~` розгорнуто."""
    shared = cfg.get('design_work_root') if isinstance(cfg, dict) else None
    return os.path.expanduser(shared if isinstance(shared, str) and shared else DEFAULT_TASK_ROOT)


def task_new(cfg, tid, title='', jira='', track=None, gitlab=None, vcs=None, root=None, adopt_src=None,
             adopt_files=(), tags=None, repo=None, legacy=False):
    """Бутстрап задачи: папка в design-work (или клон макета з репо) + запись в tasks.json.
    Идемпотентность обеспечивает вызывающий (проверка на существование).

    `track` — напрямок задачі (id явного напрямку простору): лягає в запис ключем `track`, коли він є (`None` — не пишеться).
    `root` — теку, у якій лягає тека задачі, і `repo` — типовий репозиторій макетів напрямку дає ВИКЛИКАЧ (маршрут:
    `track_root`/`track_repo`; простір без напрямків: `path` простору й без репо); без `root` — `default_task_root(cfg)`. Дефолт
    напрямку ставить маршрут, не ця функція: прямий виклик без `track` лишає `None`. `legacy` — задача простору ЛІГИ:
    ⛔ запис несе й `profile` з тим самим значенням, що `track`: старі колеги й зовнішній dev-pipeline читають `profile`
    зі спільного реєстру і з `tasks.json` (без нього їхня тека, репо й мітка зламались би); нова версія `profile` лише
    пише, не читає. `repo` напрямку стає `gitlab`-маппінгом
    `mockup/<id>`; не-ЛІГА пише `profile: null` (формат запису звичайного простору не міняється), а `repo` стає
    `vcs: {repo}` — лише коли в просторі є постачальник ролі `vcs` і явного `vcs` (чи `gitlab`) нема.

    `fullmatch`, а не `match`: `$` в `NAME_RE` пускав id із хвостовим переводом рядка, і
    тека задачі діставала його в назві. Не-рядок (`5`, `null`) — теж «поганий id», а не
    TypeError, що рве зʼєднання.

    `title` — ввід людини (форма «Нова задача»): у стартовий `index.html` він лягає ЕКРАНОВАНИМ.

    `vcs` — `{repo, path?, branch?}` (етап 4a, роль `vcs`; перевірки й відмову без ролі робить маршрут): ціль синку задачі;
    пишеться в запис задачі й, коли в `<path>` репо є `index.html`, дає першу ітерацію. З `adopt_src` (`from`) отримання
    не робиться: людина вже назвала джерело макета. `gitlab` (ЛІГА) бутстрапить із репо й тоді, як було.

    `adopt_src` — тека-джерело (`from` маршруту, вже перевірена `_adopt_source`), `adopt_files` — її перелік з
    `adopt_scan`: тоді перша ітерація — копія теки, а не стартовий `index.html`, а результат несе `adopted`
    (`{files, bytes, skipped}` — що `adopt_copy` справді скопіював). ⛔ Імена саме `adopt_*`, не `src`: гілка отримання
    з репо в `_task_new_write` мала б власний локальний `src` і затінила б параметр (регресія 0.6.0: нова задача при
    доступному дзеркалі без макета діставала ПОРОЖНЮ `it1`); та гілка цих імен не торкається (її локальні — `got`).
    Теку задачі `adopt_src` ЗАЙМАЄ атомарно (`makedirs` без `exist_ok`: вона вже є — `TaskRefused('task-dir-exists')`,
    чужу теку не чіпаємо). Будь-який збій до запису в `tasks.json` включно прибирає саме її й летить далі (`OSError` →
    маршрут: 500 `task-create-failed`, повтор не впирається в `task-dir-exists`).

    `tags` (4b-3) — уже нормалізований список міток (`normalize_tags` робить маршрут): у запис задачі лягає лише НЕпорожній
    (без ключа — похідна мітка напрямку задачі, див. `task_tags`).
    """
    if not isinstance(tid, str) or not NAME_RE.fullmatch(tid):
        raise TaskRefused('bad-task-id', 'bad task id')
    if tid in cfg.get('tasks', {}):
        raise TaskRefused('task-exists', 'task already exists')
    if task_trash.in_trash(cfg, tid):
        # Етап Д: id зайнятий записом кошика — нова задача з ним зробила б повернення неможливим.
        raise TaskRefused('task-in-trash', 'a task with this id is in the trash')
    tdir = os.path.join(root or default_task_root(cfg), tid)
    if adopt_src is not None:
        try:
            os.makedirs(tdir)                  # БЕЗ `exist_ok`: теку займає рівно один запит
        except FileExistsError:
            raise TaskRefused('task-dir-exists', 'the task folder already exists in the space') from None
    try:
        cloned, adopted = _task_new_write(cfg, tid, title, jira, track, gitlab, vcs, tdir, adopt_src, adopt_files, repo, legacy)
        if tags:
            cfg['tasks'][tid]['tags'] = list(tags)
        cfg['current'] = tid
        mark_opened(cfg, tid)
        task_trash.clear_tombstone(cfg, tid)   # «назавжди» знищену задачу заводять знову — надгробок більше не потрібен
        save_tasks(cfg)
    except BaseException:
        if adopt_src is not None:
            shutil.rmtree(tdir, ignore_errors=True)     # лише те, що створила ЦЯ спроба (див. докстрінг)
        raise
    git_autocommit(tdir, f'task {tid}: bootstrap '
                   f'({"clone from gitlab" if cloned else "from folder" if adopted is not None else "new"})')
    registered = _registry_push(tid)
    out = {'ok': True, 'id': tid, 'cloned': cloned, 'dir': tdir,
           'registered': registered}
    if adopted is not None:
        out['adopted'] = {'files': adopted[0], 'bytes': adopted[1], 'skipped': adopted[2]}
    return out


def _task_new_write(cfg, tid, title, jira, track, gitlab, vcs, tdir, adopt_src, adopt_files, repo, liga):
    """Тіло `task_new` до запису задачі в `cfg` включно (макет першої ітерації, `iterations.json`, `cfg['tasks'][tid]`):
    `(cloned, adopted)`, де `adopted` — `(файлів, байтів, пропущено)` від `adopt_copy` або `None`. Окремою функцією,
    щоб `task_new` могла прибрати зайняту теку при БУДЬ-ЯКОМУ збої тут і в `save_tasks`, але не після запису реєстру.
    `current` і збереження `tasks.json` лишаються в `task_new` (їх читання `current` стереже `CurrentTaskReadGuard`).
    ⛔ `adopt_src`/`adopt_files` — лише з параметрів: гілка отримання нижче має власні локальні (`tmp`, `got`, `target`, `r`) і
    цих імен не торкається."""
    if gitlab and not liga:
        # Остання ланка: маршрут відмовляє раніше, але прямий виклик `task_new` не має клонувати `gitlab`-ціль у просторі без схеми ЛІГИ.
        raise TaskRefused('gitlab-needs-vcs-scheme', 'gitlab mapping needs a space whose git sync uses the design-canvas scheme')
    it1 = os.path.join(tdir, 'iterations', 'it1')   # первая итерация = стартовый макет
    # Типовий репо напрямку (його дає маршрут: `track_repo`). ЛІГА: `gitlab`-маппінг `mockup/<id>`; напрямок без репо —
    # без нього. ⛔ Структура в усіх напрямків одна, тому напрямки розходяться лише репозиторієм, а не логікою.
    if liga:
        if gitlab is None and repo:
            gitlab = {'repo': repo, 'path': f'mockup/{tid}'}
    elif repo and vcs is None and gitlab is None:
        # Звичайний простір: репо напрямку стає `vcs` задачі, але лише коли роль `vcs` справді є (без постачальника — мовчки
        # не застосовується, як і завжди для репо без ролі). Відмова постачальника (`VcsError`) — теж «нема».
        try:
            has_role = vcs_provider() is not None
        except VcsError:
            has_role = False
        if has_role:
            vcs = {'repo': repo}
    cloned = False
    cloned_state = {}
    legacy = True        # чий текст даних у примітці форку: типово ЛІГА (`v[2]`), поки постачальника не знайдено
    # Клон — для `vcs` БЕЗ `from` (`adopt_src`); профільний `gitlab` ЛІГИ бутстрапить, як і було.
    if gitlab or (vcs and adopt_src is None):
        tmp = tempfile.mkdtemp(prefix='deai-vcs-')
        try:  # если макет уже есть в репо — берём его в it1, не начинаем с нуля
            v = vcs_provider()
            if v is not None:
                legacy = v[2]
                # Явний `vcs.repo` перемагає `gitlab` репо напрямку (ЛІГА) — як у `vcs_target`.
                target = vcs_target(tid, {'vcs': vcs} if vcs else {'gitlab': gitlab}, v[1].get('settings') or {})
                if target:
                    got = os.path.join(tmp, 'm')
                    os.makedirs(got)
                    # ⛔ `pull` модуля = дзеркало + `--ff-only` до свіжого origin. Для НОВОЇ задачі це важливо: якщо
                    # дизайнер уже працював із цим репо, на диску лежить старий чекаут — задача заводилась би з
                    # тижневого зрізу чужого макета, ще й із протухлим підписом у `.canvas-state.json`. Не вийшло
                    # наздогнати — `VcsError` (`OSError`) падає в ту саму гілку, що й недоступне дзеркало (порожній
                    # стартовий макет), а не мовчки бере застаріле.
                    r = _vcs_call(v, 'pull', target, got, {'ignore': ['shots']})
                    if r.get('found') is True and os.path.isfile(os.path.join(got, 'index.html')):
                        copy_mockup(got, it1)
                        cloned = True
                        cloned_state = _read_state(got)
        except OSError:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    adopted = None
    if not cloned:
        if adopt_src is not None:
            adopted = adopt_copy(adopt_src, it1, adopt_files)
            # `copy2` зберігає mtime ДЖЕРЕЛА; свіжа задача зі старою датою збрехала б у `_last_changed` і в «Задачах»
            _touch_tree(it1)
        else:
            os.makedirs(it1, exist_ok=True)
            with open(os.path.join(it1, 'index.html'), 'w', encoding='utf-8') as f:
                shown = html_escape(str(title or tid))
                f.write('<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">'
                        f'<title>{shown}</title></head><body>'
                        f'<h1>{shown}</h1>'
                        '<p>Нова ітерація — почни проєктувати.</p></body></html>')
    # meta с первой итерацией
    #
    # ⛔ Підпис БУТСТРАПА не завжди мій. Якщо макет склонований з репо, його
    # зробив хтось інший — і підписати його собою означало б записати на себе
    # чужу роботу (саме той випадок, з якого почалась задача про іменні
    # ітерації: LIGA-7012, «авторство зникло назовсім»; неправильне авторство
    # гірше за відсутнє). Ба більше: після синку цей підпис поїхав би назад, і
    # справжня авторка дістала б ВЛАСНИЙ макет як чужий — із форком і
    # забороною пушу. Тому автор береться з заяви колеги в `.canvas-state.json`,
    # а коли її немає — не пишемо нічого.
    it1_entry = {'id': 'it1', 'date': time.strftime('%d.%m.%Y %H:%M'),
                 'note': 'початкова', 'published': False}
    its = [it1_entry]
    if cloned:
        # Порожнє поле не пишемо (правило `_stamp_author`): `author: ''`
        # читалось би як «автор відомий і безіменний».
        if cloned_state.get('author'):
            it1_entry['author'] = cloned_state['author']
        if cloned_state.get('author_key'):
            it1_entry['author_key'] = cloned_state['author_key']
        _, my_key = machine_identity()
        if not iteration_is_mine(it1_entry, my_key):
            # ПАРА, як у «Підтягнути»: без форку задача починалась без жодної
            # СВОЄЇ ітерації, і `bin/state.py` казав про ту саму Іт.1 дві
            # протилежні речі — «остання своя» і «чужа, read-only». Одна модель
            # на обидва входи чужого макета, а не дві.
            fork_dir = os.path.join(tdir, 'iterations', 'it2')
            copy_mockup(it1, fork_dir)
            _touch_tree(fork_dir)
            its.append(_stamp_author(
                {'id': 'it2', 'date': time.strftime('%d.%m.%Y %H:%M'),
                 'note': f'продовження макета з {"GitLab" if legacy else "репозиторію"}', 'published': False,
                 'from': 'it1'}))
    else:
        _stamp_author(it1_entry)
    with open(os.path.join(tdir, 'iterations.json'), 'w', encoding='utf-8') as f:
        json.dump({'iterations': its, 'publish_url': None},
                  f, ensure_ascii=False, indent=2)
    entry = {'dir': tdir, 'title': title or tid, 'jira': jira, 'profile': track if liga else None}
    if track is not None:
        entry['track'] = track
    if gitlab:
        entry['gitlab'] = gitlab
    if vcs:
        entry['vcs'] = vcs
    cfg.setdefault('tasks', {})[tid] = entry
    return cloned, adopted


def _registry_push(tid):
    """Отдать задачу в реестр (design-office/registry) — он источник истины, поэтому
    коллега увидит задачу без ручного шага. Best-effort: без VPN бутстрап не валим.

    ⛔ Підмінений конфіг = ЗАБОРОНА писати у спільний стан. `DC_TASKS_FILE` виставляють
    тести й будь-який ізольований прогін; це означає «стан не справжній цієї машини»,
    тому пушити його всій команді не можна НІ В ЯКОМУ РАЗІ.

    Інцидент 03.08.2026, знайдений уже після релізу: `tests/test_serve.py` створює
    задачу `demo2` через `/api/task-new`, а цей рядок пушив її у СПІЛЬНУ гілку
    `registry` на GitLab. Кожен прогін сюїти повертав `demo2` у реєстр команди —
    видалив о 16:05, о 16:11 воно було знову. `DC_NO_OVERVIEW` цей шлях не покривав:
    він глушить лише синк Supabase (`_overview_sync`), а тут окремий, git-овий.

    Простір без схеми ЛІГИ (`registry_allowed`) у спільний реєстр команди не пише НІКОЛИ:
    його задачі — особисті, і «зареєструвати» їх колегам означало б вивести їх з простору.
    """
    if not registry_allowed():
        return False
    if os.environ.get('DC_TASKS_FILE') or os.environ.get('DC_NO_OVERVIEW'):
        return False
    try:
        sys.path.insert(0, os.path.join(ROOT, 'bin'))
        import registry
        res = registry.push_tasks([tid])
        # ⛔ Задачу, що вказує в тимчасову теку, `push_tasks` сам відмовляє
        # (інцидент `nova` 15.09.2026: конфіг тоді НЕ був підмінений, тож
        # гвард вище не спрацював). «Зареєстровано» для неї — неправда.
        return tid not in getattr(res, 'refused', {})
    except Exception:  # noqa: BLE001 — нет сети/доступа: задача уже создана локально
        return False


def _vcs_failure(e):
    """Тіло відмови маршрутів `vcs-*` і автосинку: `{ok: false, error, code?}`. Текст — крізь `_mask_repo` (виняток нижче по
    стеку чи чужий модуль міг понести адресу з токеном), `code` — лише у `VcsError`."""
    return {'ok': False, 'error': _mask_repo(str(e))[:300], **({'code': e.code} if isinstance(e, VcsError) else {})}


def integrations_off_body(what):
    """Тіло 409 маршруту, що ходить назовні, коли простір запиту БЕЗ інтеграцій. Модульна
    функція, а не метод `Handler`: зовнішні заглушки обробника (`boss_autopublish.py`) мають
    лише `_current_task/send_error/_send_json/_overview_sync`, і новий метод їх зламав би."""
    return {'ok': False, 'code': 'integrations-off', 'error': what}


def notify_resolve():
    """`(space, prov)` ролі `notify` для простору ЗАПИТУ: `prov` — `Module` чи `None` (сповіщень нема: пункта
    «Сповіщати Teams» нема, маршрут `/api/teams-mute` — 409). Як `team_resolve`: `space` — запис простору лише для модуля.
    Кидає `spaces.SpacesError` (реєстр не прочитати) і `deai_modules.ModuleError` (свій модуль «на папері», `space.json` не
    читається): це НЕ «нікого» — маршрут називає причину, а не прикидається, що сповіщень нема."""
    prov = deai_modules.provider('notify')
    return (spaces.active_space() if isinstance(prov, deai_modules.Module) else None), prov


def notify_call(fn, *args, resolved=None):
    """Один виклик ролі `notify` постачальника простору запиту: `notify_call('mute_state')` → список замовчаних каналів
    (`notify.normalize_mutes`), `notify_call('mute_set', канал, muted, by)` → `bool`. `resolved=(space, prov)` — коли маршрут
    уже вирішив постачальника (без другого читання реєстру й каталогу). Кидає `OSError` (нікого / ізоляція / шов), `ValueError`
    (погані аргументи `mute_set` — ДО модуля) і `deai_modules.ModuleError` (нема конфігу, збій модуля, `check-timeout`).

    ⛔ Підмінений конфіг = ЗАБОРОНА чіпати спільний стан — той самий закон, що в `_registry_push`: `DC_TASKS_FILE`/`DC_NO_OVERVIEW`
    ставлять тести й будь-який ізольований прогін, і замовчати чи увімкнути живий канал Teams команди з фікстури не можна НІ В
    ЯКОМУ РАЗІ. Лише для запису `shared_state` (спільний Supabase ЛІГИ — той самий живий канал), порядок такий:
    1. `DC_TEAMS_FAKE` — локальний JSON замість бази для живих тестів (шов, а не другий шлях: він не пише нікуди, крім свого
       файла); відповідь — у формі модуля (`mute_state` — список, `mute_set` — `bool`). Звичайний простір із модулем шва НЕ бачить;
    2. ізольований прогін без шва — `OSError('ізольований конфіг…')`, модуль НЕ кличеться, мережі НЕМАЄ;
    3. інакше модуль із `module_ctx(space, prov)` запису: нема конфігу — `notify-unconfigured`.
    Звичайний простір: `module_ctx(space, prov)` свого модуля. Виклик — `deai_modules.call(…, timeout=NOTIFY_TIMEOUT)`.
    ⛔ Відповідь модуля не береться на віру: `mute_state`, що не список, і `mute_set`, що не `bool`, — `notify-error` (не «нічого
    не замовчано» і не «успіх»: `1` і `True` — різні відповіді). ⛔ Аргументи `mute_set` перевіряє `notify.check_set_args` ДО
    модуля, і модуль не бачить поганих."""
    space, prov = resolved if resolved is not None else notify_resolve()
    if fn == 'mute_set':
        notify.check_set_args(*args)
    if prov is None:
        # Нікого: роль `notify` у просторі ніхто не веде. Маршрут відповідає 409 ще до цього виклику.
        raise OSError('сповіщень Teams у просторі нема')
    if _shared_module(space, prov):
        kind, fake = isolation.route('notify')
        if kind == 'fake':
            try:
                with open(fake, encoding='utf-8') as fh:
                    db = json.load(fh)
            except (OSError, ValueError):
                db = {}
            if fn == 'mute_set':
                channel, muted, by = args
                if muted:
                    db[channel] = {'muted_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'muted_by': by}
                else:
                    db.pop(channel, None)
                atomic_write_json(fake, db)
                return muted
            return notify.normalize_mutes([{'project_id': k, **v} for k, v in sorted(db.items())])
        # Після шва (він пише лише у свій локальний файл), але ДО будь-якої мережі.
        if kind == 'isolated':
            raise OSError('ізольований конфіг: спільний стан Teams не чіпаємо')
        module, ctx = prov, deai_modules.module_ctx(space, prov)             # `shared_state` (4d-3a): модуль із ctx запису
    else:
        module, ctx = prov, deai_modules.module_ctx(space, prov)
    res = deai_modules.call(module, fn, ctx, *args, timeout=notify.NOTIFY_TIMEOUT)
    if fn == 'mute_state':
        try:
            return notify.normalize_mutes(res)
        except ValueError as e:
            raise deai_modules.ModuleError('notify-error', message=str(e)) from None
    if type(res) is not bool:
        raise deai_modules.ModuleError('notify-error', message='notify: mute_set must return a boolean')
    return res


def _notify_route_gate():
    """Шлюз маршруту `/api/teams-mute`: `(resolved, error)`. `resolved` — `(space, prov)` ролі `notify`; `error` — `ModuleError` збою
    рішення ролі (свій модуль «на папері»): це НЕ «нікого», маршрут називає причину. Нікого — `resolved[1] is None`."""
    try:
        return notify_resolve(), None
    except deai_modules.ModuleError as e:
        return None, e


def _notify_off_body():
    return {'ok': False, 'code': 'notify-off', 'error': 'сповіщень Teams у просторі нема'}


def mute_signature():
    """Хто замовчав канал — БЕЗ ПІБ і пошти: `teams_mute_state` читає будь-хто з
    ключем сторінки (ревʼю 1.52). Короткий хеш пошти з git-конфіга: канвас
    порівнює його зі своїм і пише «ти»/«колега», доктор показує сам хеш."""
    import hashlib
    key = machine_identity()[1].strip().lower()
    return 'k:' + hashlib.sha256(key.encode('utf-8')).hexdigest()[:12] if key else ''


def iter_num(iid):
    """Реальний номер ітерації для показу: 'it4' -> '4' (щоб свитчер збігався з
    інструментом Іт.1/Іт.4, а не нумерував опубліковані позиційно 1,2)."""
    m = re.match(r'it(\d+)$', iid)
    return m.group(1) if m else iid


def iteration_note(it):
    """Очищена примітка ітерації: явний `label` → `note` без префікса
    «LIGA-1234 · » → порожній рядок. БЕЗ префікса «Іт.N».

    Це ДАНІ, не презентація, і тому вони лишаються в Python: яку з двох
    підписок брати й який префікс тікета зрізати — одне правило на всі мови.
    А от «Іт.N» спереду — це вже ПРЕЗЕНТАЦІЯ, і мову для неї вибирає ГЛЯДАЧ у
    своєму браузері (`dc-lang`), тобто складати її мусить словник, а не Python.
    Звідси розділ: `publish_manifest` везе в маніфест `num` і `note`, а тег
    ліпить `t('iterTag', num)` уже в оболонці.

    ⛔ ОДНЕ місце очищення на двох консументів (`iteration_label` для
    `/api/task` і маніфест превʼю). Два власні `re.sub` розійшлися б на першій
    же правці формату тікета, і видно це було б лише в чужому браузері: канвас
    показує одне, превʼю інше. Парний інваріант тримає тест.
    """
    lbl = (it.get('label') or '').strip()
    if not lbl:
        lbl = re.sub(r'^\s*[A-Z]+-\d+\s*[·:-]\s*', '', it.get('note') or '').strip()
    return lbl


def iteration_label(it):
    """Готовий підпис ітерації для `/api/task` (`label_text`): «Іт.N · примітка».

    Дзеркалило itLabel() у app.js — тепер правило ЛИШЕ тут, а канвас бере
    готове поле `label_text`. Коли підпис є, номер лишається спереду: ним
    говорять state.py і синк, тому втрачати його не можна.

    ⚠️ Раніше цим же підписом живився й маніфест зовнішнього превʼю, і
    докстрінг це виправдовував: «тримати одне правило у двох мовах означало б
    гарантовано їх розсинхронити». Для СТАРОЇ обгортки це була правда — у неї
    словника не було. У нової є (`publish/shell/i18n.js` копіюється
    публікацією), тому підпис туди більше не пече: маніфест везе `num` і
    `note`, а «Іт.N»/«It.N» складає `iterTag` мовою глядача. Тут же префікс
    лишається кирилицею СВІДОМО — цей рядок читає канвас, який працює на
    машині дизайнера й сам зрізає той префікс регекспом (`app.js`).
    """
    lbl = iteration_note(it)
    n = iter_num(it['id'])
    # Номер СПЕРЕДУ: у дропдауні довгий підпис обрізається з хвоста, а номер —
    # ідентифікатор, ним говорять state.py і синк. «Design v2 · правки менеджера
    # · Іт.3» у 190px показувало «Design v2 · правки менед…», тобто рівно те, що
    # треба бачити, і зникало (перевірено в браузері 04.08.2026).
    return f'Іт.{n} · {lbl}' if lbl else f'Іт.{n}'


def task_api_iterations(meta):
    """Ітерації для /api/task із доданим `label_text`.

    ⛔ КОПІЯ кожної ітерації, не мутація: `meta` — це вміст iterations.json, і
    дописане поле поїхало б у файл при наступному save_meta, тобто службове
    поле осіло б у даних задачі назавжди.
    """
    return [{**it, 'label_text': iteration_label(it)}
            for it in (meta or {}).get('iterations', [])]


def comment_channel(task, tid, internal=False):
    """Єдиний канал коментарів на ЗАДАЧУ (не на ітерацію): історію проєкту і
    коментарі колег тримаємо в одному потоці, а конкретну ітерацію коментаря
    несе `version` у CommentLayer.init (тег + перенос відкритих по fp). Канал
    береться з tasks.json `comment_project`; internal → підканал робочих пінів."""
    return deai_modules.legacy_comment_channel(task, tid, internal)


def _task_comment_channel(sp, task, tid):
    """`comment_channel` для `/api/task` (Д5): канал є, коли простір має постачальника ролі `comments` (модуль) — не за прапорцем."""
    if isinstance(deai_modules.comments_prov_cached(sp), deai_modules.Module):
        return _comment_channel_in(sp, task, tid)
    return None


def _comment_channel_in(sp, task, tid, internal=False):
    """Канал коментарів задачі для місць, що раніше завжди рахували `comment_channel` (`api/task`, `teams-mute` GET/POST): рішення
    за постачальником ролі `comments` простору `sp` (з кешу `_capabilities_full`, не новим обходом каталогу), як і скрізь —
    через `deai_modules.comment_channel_of`. Збій рішення (нема постачальника, `ModuleError`, `channel_for` на непридатному id) —
    схема comment-layer, як у 0.17.0: ні 5xx, ні `None`. Помилку рішення тут ковтаємо: `/api/task` у такому разі каналу не віддає взагалі
    (`_task_comment_channel` вимагає постачальника), а запасна схема лишається лише для teams-mute."""
    prov = deai_modules.comments_prov_cached(sp)
    if isinstance(prov, deai_modules.Module):
        try:
            return deai_modules.comment_channel_of(sp, prov, task, tid, internal=internal)
        except deai_modules.ModuleError:
            pass
    return deai_modules.legacy_comment_channel(task, tid, internal)


# Інспектор ДС — окремим тегом і за ПРАПОРЦЕМ, не назавжди в шаблоні.
#
# Чому прапорець: сніпет коментарів (`MODULE_COMMENT_SNIPPET`) має двох адресатів — `/commented?ch=project`
# (робоче місце дизайнера) і `_publish` (статика для колег). Спека тримає межу:
# інспектор це інструмент дизайнера, зовнішньому глядачеві його не давали, а в
# `publish/comment-layer/` їдуть лише шар коментатора й файли адаптера — `inspector*.js` там немає,
# тобто тег «у шаблоні завжди» був би ще й 404 у справжньому превʼю.
#
# Чому ПІСЛЯ скриптів коментарів: порядок у сніпеті несучий (див. коментар над
# `_COMMENT_DOWN_BANNER` нижче — банер мусить бути першим тегом, це ловили живцем).
# `type="module"` відкладений за визначенням, тож стоячи в хвості він нічого не
# затримує й послідовності класичних скриптів не рушить.
#
# Чому БЕЗ `onerror="window.__clDown(…)"`: той банер каже «Коментарі
# недоступні». Інспектор до коментарів не має стосунку — його падіння збрехало б
# дизайнеру про справні коментарі, і причину він шукав би в Supabase.
# `?ds=<ДС напрямку>` — єдиний спосіб, яким документ макета дізнається про
# напрямок задачі (`track` у tasks.json): сам він про задачу
# не знає нічого, а статична ДС вибирається саме за напрямком (вендорний інспектор
# знає свої ДС за назвою; напрямок без ДС — інспектор мусить сказати це словами,
# а не мовчки звіряти з чужою). Назву дає `task_ds`. Чому
# параметром URL, а не зайвим тегом чи глобальною змінною — у `inspector.js`,
# там же й виміряна причина (порядок тегів у сніпеті несучий).
INSPECTOR_TAG = '\n<script type="module" src="{assets}/inspector.js{ds}"></script>'


def inspector_ds_arg(ds, sp=None):
    """Хвіст URL інспектора: `?ds=<ДС>`, `?ds=<ДС>&sp=design-1`, `?sp=design-1` або порожньо.

    `ds` — вже ДС напрямку задачі (`task_ds`), не сам напрямок. `?ds=` — ЗАВЖДИ першим (старі розмітки, тести й розбір у
    `inspector.js` на це спираються); `sp` дописується до нього через `&`, а коли ДС нема — відкриває рядок запиту сам.
    Порожньо — і коли ДС немає, і коли вона не схожа на імʼя: у параметр URL, що їде в
    розмітку, не сміє потрапити нічого, крім простого імені, а невідома ДС і так ВИМИКАЄ
    звірку (краще не звіряти, ніж звіряти з вигаданою).

    `sp` — простір СТОРІНКИ (запис реєстру, `spaces.active_space()`; етап 2а, Task 7): документ
    макета про простір не знає нічого, а інспектор мусить спитати `/api/ds-tokens?space=<id>`, тож
    єдина дорога — параметр власного URL. Їде ЛИШЕ коли `spaces.describe(sp)` не `None`, тобто шар
    просторів увімкнено й сторінка належить справжньому простору: неявний простір (шар вимкнено) має id
    `legacy` без шляху, і питати про нього `/api/ds-tokens` — питати про простір, якого в реєстрі нема.
    Id перевіряється так само, як напрямок (`SPACE_ID_RE`): реєстр і так не пропустить іншого, але
    розмітка не повинна триматись на тому, що хтось колись не забув перевірити.

    ⛔ ПУБЛІКАЦІЯ сюди не доходить і не мусить: `/api/ds-tokens` на статиці нема. З 0.32.0 опублікована сторінка НЕ без інспектора:
    вона несе оверлей (`shell/vendor/`) і власний тег — `preview_inspector_tag` (відносний шлях, токени знімком-файлом збірки
    `shell/ds-snapshot.json`), а не цей хвіст; `sp` без `tok` у сторінку превʼю не потрапляє ніколи: це був би запит до
    `/api/…` у глядача."""
    p = (ds or '').strip()
    out = f'?ds={p}' if tracks.ID_RE.fullmatch(p) else ''
    d = spaces.describe(sp)
    if d is not None and spaces.SPACE_ID_RE.fullmatch(str(d['id'])):
        out += ('&' if out else '?') + f'sp={d["id"]}'
    return out


#: Файли оверлея інспектора, що їдуть у превʼю (0.32.0): `publish/shell/vendor/`. Імпорти `../i18n.js` та `../esc.js` оверлея
#: ведуть у `publish/shell/` — туди ж їде оболонка (`SHELL_MODULES`), тож другої копії словника нема. Замкнутість по `./` і `../`
#: рахує тест (`ShellModulesList`): забутий лист — 404 і мертва кнопка «Інспектор» у глядача.
SHELL_VENDOR = ('inspector.js', 'inspector-dom.js', 'inspector-core.js', 'inspector-measure.js', 'inspector-nav.js',
                'insp-report.js', 'ds-tokens.js')
#: Знімок токенів простору: `publish/shell/ds-snapshot.json`. Тег оверлея несе його відносним шляхом від самого оверлея.
PREVIEW_TOKENS_FILE = 'ds-snapshot.json'
#: Поле `profile` відповіді `/api/ds-tokens` (`space:<id>`) — НЕ застаріле поле задачі `profile` (4d-4a, `tests/test_no_adapter.py`):
#: ключ винесено в константу, щоб охоронець «читання `profile` лише на межі» не плутав дві різні речі.
_TOKENS_PROFILE = 'profile'


#: Значення токена, що несе локальний шлях чи завантаження файла: у публічне превʼю не їде (0.32.0).
_LOCAL_VALUE_RE = re.compile(
    r'url\(|file:|/Users/|/home/|/private/|/tmp/|[A-Za-z]:\\|~/|localhost|127\.0\.0\.1|0\.0\.0\.0|::1'
    r'|(?<![\w.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?![\w.])', re.I)


def _public_token_values(tokens):
    """`tokens` без значень із локальними шляхами (`url(`, `file:`, домашня тека, `/Users/` `/home/` `/private/` `/tmp/`, диск Windows, `~/`, localhost/loopback, приватні LAN-адреси);
    імʼя без жодного значення, що лишилось, відпадає. Форма `{імʼя: [значення…]}` не змінюється."""
    home = os.path.expanduser('~')
    out = {}
    for name, vals in tokens.items():
        keep = [v for v in vals if not _LOCAL_VALUE_RE.search(v) and not (len(home) > 1 and home in v)]
        if keep:
            out[name] = keep
    return out


def preview_tokens_snapshot(space):
    """Знімок токенів простору для превʼю (0.32.0): те, що віддає `GET /api/ds-tokens?space=<id>` (`ds_tokens_view`), —
    `{profile, tokens, source}` — або `None`, коли токенів нема (шар просторів вимкнено, простір неявний, нема постачальника ролі
    `tokens`, модуль впав, мапа порожня): тоді файла не буде, а оверлей покаже значення без чипів.

    ⛔ Превʼю ПУБЛІЧНЕ: `source` зводиться до імені файла (власний модуль міг віддати шлях із домашньою текою людини), а імена й
    значення токенів їдуть як є — це зміст дизайн-системи, заради якого знімок і береться. Модуль виконує свій код
    (`CHECK_TIMEOUT`): НЕ кликати під замками публікації й `spaces.WRITE_LOCK` — викликач бере знімок ДО них."""
    d = spaces.describe(space)
    if d is None or not spaces.SPACE_ID_RE.fullmatch(str(d['id'])):
        return None
    view = ds_tokens_view(space)
    if not isinstance(view, dict) or not view.get(_TOKENS_PROFILE) or not view.get('tokens'):
        return None
    tokens = _public_token_values(view['tokens'])
    if not tokens:
        return None
    src = view.get('source')
    src = re.split(r'[\\/]', src)[-1] if isinstance(src, str) else ''
    return {_TOKENS_PROFILE: view[_TOKENS_PROFILE], 'tokens': tokens, 'source': src}


def preview_inspector_tag(depth_up, ds, tokens):
    """Тег оверлея інспектора для сторінки превʼю на глибині `depth_up` (`'../'` × глибина): ВІДНОСНИЙ шлях у
    `shell/vendor/`. `ds` — вже ДС напрямку задачі (`task_ds`), `?ds=` першим, як у Deai. `tokens` — знімок
    (`preview_tokens_snapshot`) чи `None`: лише з ним тег несе `&sp=<id>&tok=../ds-snapshot.json` (відносно самого оверлея);
    без знімка `sp` НЕ їде — він змусив би оверлей питати `/api/ds-tokens`, якого на статиці нема."""
    p = (ds or '').strip()
    arg = f'?ds={p}' if tracks.ID_RE.fullmatch(p) else ''
    if tokens and str(tokens.get(_TOKENS_PROFILE, '')).startswith('space:'):
        sid = tokens[_TOKENS_PROFILE][len('space:'):]
        if spaces.SPACE_ID_RE.fullmatch(sid):
            arg += ('&' if arg else '?') + f'sp={sid}&tok=../{PREVIEW_TOKENS_FILE}'
    return INSPECTOR_TAG.format(assets=f'{depth_up}shell/vendor', ds=arg)


# Вкладки аудиторій — аргументом `init`, і теж за ПРАПОРЦЕМ на виклику.
#
# Перемикач «кому їде цей фідбек» до 02.09.2026 стояв у дропдауні крошки
# ітерації (`data-act="cmode"`) — тобто контрол коментатора у смузі
# інструмента, проти принципу 6 PRODUCT.md. Новий дім — панель самого
# коментатора; спека: «коментарі я розрішаю».
#
# Чому прапорець, а не завжди: сніпет коментарів має двох адресатів, і другий —
# `_publish`. Вкладка «Клод» у статиці для колег вела б у локальний файл на
# машині дизайнера (404 у глядача) і запрошувала б слати робочий фідбек у
# нікуди. Це вимога конфіденційності зі спеки, не косметика.
#
# Чому АРГУМЕНТОМ `init`, а не окремим `<script>` із конфігом: порядок тегів у
# сніпеті коментарів несучий (див. коментар над `_COMMENT_DOWN_BANNER` нижче — баг ловили
# живцем), і зайвий тег між банером і `<script src>` знову зламав би
# показ банера при мертвому CDN.
#
# Чому `active` рахує СЕРВЕР: канал вибрав роут, тобто сніпет знає його точно.
# Підсвічена «Клод» на сторінці, яка пише в Supabase, означала б фідбек,
# відправлений не туди, кого бачив дизайнер.
#
# Чому `onAudience` не навігує сам: стан каналу тоді жив би у двох місцях.
# Рамка лише ПОВІДОМЛЯЄ (`dc-audience` через postMessage). Після 0.27.0 (поправка 3)
# оболонка цього повідомлення НЕ слухає — канал-перемикач у ній прибрано, її рамка
# працює в комбінованому режимі (`host=1`). Посилка лишилась тільки для сторінок
# без `host`, які відкрито поза оболонкою; приймача в `app.js` більше нема.
#
# Підписи українською, без словника: панель коментатора — чужий продукт із
# власним (англійським) словником, у неї нема куди передати мову оболонки, а
# сам `serve.py` мови клієнта не знає (вона в localStorage). Той самий вибір,
# що вже зроблено для банера «Коментарі недоступні» вище.
# Підписи вкладок бере КЛІЄНТ, а не сервер. Причина: мова інтерфейсу — вибір
# людини в `localStorage` (`dc-lang`), а цей сніпет пише сервер, який про той
# вибір не знає й знати не мусить (рамка того самого походження, тож
# `localStorage` там читається). До 02.09.2026 підписи були захардкожені
# українською й лишались «Клод»/«Команда» серед англійського інтерфейсу —
# знайдено живим прогоном, тим самим способом, що й «Іт.N» днем раніше.
#
# Дві копії рядків (тут і в `app/i18n.js`) неминучі: Python не імпортує
# JS-словник. Тому їх приколює тест `test_audience_labels_match_dictionary` —
# той самий підхід, що вже тримає пару `comment_layer_src_hash`.
AUDIENCES_TMPL = """,
        audiences: (function () {{
          var uk = {{ local: 'AI', team: 'Команда' }};
          var en = {{ local: 'AI', team: 'Team' }};
          var L = uk;
          try {{ if (localStorage.getItem('dc-lang') === 'en') L = en; }} catch (e) {{}}
          // `icon` — імена з набору САМОГО коментатора (`bot`/`team`), не наші
          // канали: віджет малює іконку за іменем і не дізнається, що таке
          // «local». Стоїть у хвості обʼєкта свідомо — так регексп охоронця
          // `AudienceTabsPerChannel`, що приколює пару «id ↔ підпис ↔ active»,
          // лишається чинним і не мусить знати про іконки.
          return [{{ id: 'local', label: L.local, active: {local}, icon: 'bot' }},
                  {{ id: 'project', label: L.team, active: {project}, icon: 'team' }}];
        }})(),
        onAudience: function (id) {{
          window.parent.postMessage({{ type: 'dc-audience', ch: id }}, '*');
        }}"""


def audiences_arg(active):
    """Аргумент `audiences`+`onAudience` для `init`, або порожній рядок.

    `active` — id каналу цього сніпета (`'local'`/`'project'`) або `None`, коли
    вкладок не має бути зовсім (publish). Порожній рядок, а не `audiences: []`:
    контракт коментатора — «немає `audiences` → рядка вкладок немає ЗОВСІМ»
    (`comment-layer/src/audiences.js`), і порожній масив був би зайвим знанням
    про канали в чужому продукті.
    """
    if not active:
        return ''
    js = lambda flag: 'true' if flag else 'false'   # noqa: E731
    return AUDIENCES_TMPL.format(local=js(active == 'local'),
                                 project=js(active == 'project'))


# Режим хоста коментатора (Deai 0.26.0) — аргументом `init`, за ПРАПОРЦЕМ на виклику, як `audiences`.
#
# Панель коментарів переїхала в оболонку: коментатор у рамці ховає ручку й свою панель і повідомляє оболонку
# посилками (`postMessage` у батьківське вікно того самого походження), а оболонка керує ним методами
# `window.CommentLayer.*`. Чому лише за `host=1` в URL: оболонка ЗАВЖДИ його додає, а сторінка без нього (відкрита
# напряму, старі еталони `tests/fixtures/comments-role/`) — байт у байт як до 0.26.0. Публікація (0.32.0) отримує `host` у своєму
# вигляді (`PREVIEW_HOST_ARG`, нижче): оболонка превʼю (`ext-shell.js`) теж малює панель. Але режим хоста там умовний: сторінка,
# відкрита напряму (без оболонки, `<превʼю>/it1/alpha/`) чи вбудована чужим вікном, лишається звичайним коментатором із власною
# ручкою й панеллю — інакше схована ручка лишила б колег без коментарів.
# Ключ `dc-cmt-aud` — памʼять вибору адресата піна, спільна для рамки й оболонки (той самий origin, поправка 12 плану Б2).
# Чому `location.origin`, а не `'*'`: батько — оболонка цього ж сервера; чужому вікну посилка не потрібна.
HOST_ARG = """,
        host: (function () {
          var send = function (m) { m.type = 'dc-comments'; window.parent.postMessage(m, location.origin); };
          return {
            onReady: function () { send({ ev: 'ready' }); },
            onChange: function (s) { send({ ev: 'change', snapshot: s }); },
            onSelect: function (id) { send({ ev: 'select', id: id }); },
            onMode: function (on) { send({ ev: 'mode', on: !!on }); },
            defaultAudience: function () { try { return localStorage.getItem('dc-cmt-aud'); } catch (e) { return null; } },
            onAudiencePick: function (id) { try { localStorage.setItem('dc-cmt-aud', id); } catch (e) {} },
            bottomInset: function () { try { var f = window.parent && window.parent.__dcIslandInset; return typeof f === 'function' ? f() : 0; } catch (e) { return 0; } }
          };
        })()"""


# Режим хоста для ОПУБЛІКОВАНОГО превʼю (0.32.0): оболонка превʼю (`ext-shell.js`) малює панель сама, тож сторінка шле їй ті самі
# посилки, що в Deai, плюс `onAdd` (id створеного коментаря — оболонка запише «свій») і `userName` (імʼя з localStorage —
# спільного для оболонки й рамки, бо превʼю статичне, одного походження; його ставить діалог оболонки перед першим коментарем).
# ⛔ `userName` присутній ЗАВЖДИ: він і є ознакою «prompt() не кличеться» (`getUser` у коментаторі). ⛔ Жодного `defaultUser`:
# особа машини дизайнера в публічне превʼю не їде. Адресатів (`defaultAudience`) і `bottomInset` острівця тут нема: у превʼю
# одна аудиторія, а відступ під острівець дає `window.parent.__dcIslandInset` (його ставить `ext-shell.js`, якщо є).
# Непрозоре походження (`location.origin === 'null'`: локальна копія `/published/` під CSP `sandbox`, чужий вбудовувач) — НІЧОГО не
# шлемо (не `'*'`): оболонка там усе одно не дістане `frame.contentWindow.CommentLayer`, тож кнопки панелі були б мертві;
# без `ready` острівець просто не показує «Коментарі». Отримувач і далі перевіряє і `source`, і `origin`.
# `userName`: localStorage, а коли він кидає чи порожній — `window.parent.__dcPreviewUser` (імʼя, яке оболонка тримає в памʼяті).
PREVIEW_HOST_ARG = """,
        host: (function () {
          /* Хост лише всередині НАШОЇ оболонки превʼю: батько — не ми сам, того ж походження й несе мітку `__dcPreviewShell`
             (`ext-shell.js`). Інакше (пряме посилання на внутрішню сторінку, чужий вбудовувач із іншим походженням — доступ до
             батька кидає) — `null`, тобто звичайний коментатор із власною ручкою й панеллю, як до 0.32.0. */
          try { if (window.parent === window || window.parent.__dcPreviewShell !== 2) return null; } catch (e) { return null; }
          var send = function (m) {
            m.type = 'dc-comments';
            try { var o = location.origin; if (o === 'null') return; window.parent.postMessage(m, o); } catch (e) {}
          };
          return {
            onReady: function () { send({ ev: 'ready' }); },
            onChange: function (s) { send({ ev: 'change', snapshot: s }); },
            onSelect: function (id) { send({ ev: 'select', id: id }); },
            onMode: function (on) { send({ ev: 'mode', on: !!on }); },
            onAdd: function (id) { send({ ev: 'add', id: id }); },
            userName: function () {
              var v = '';
              try { v = localStorage.getItem('comment-layer:user') || ''; } catch (e) { v = ''; }
              if (v && v !== 'Anonymous') return v;
              try { return String(window.parent.__dcPreviewUser || ''); } catch (e) { return ''; }
            }
          };
        })()"""


def host_arg(on):
    """Аргумент `host` для `init` (колбеки-посилки в оболонку) або порожній рядок. `HOST_ARG` — готовий JS, без
    плейсхолдерів: у шаблон сніпета він іде ЗНАЧЕННЯМ `format`, тож фігурні дужки в ньому не екрануються.
    `on == 'preview'` — хост опублікованого превʼю (`PREVIEW_HOST_ARG`); будь-яке інше істинне значення — хост Deai."""
    if on == 'preview':
        return PREVIEW_HOST_ARG
    return HOST_ARG if on else ''


LOCAL_COMMENT_SNIPPET = """
<script src="{assets}/local-adapter.js"></script>
<script src="{assets}/comment-layer.min.js"></script>
<script type="module" src="{assets}/inspector.js{ds}"></script>
<script>
(function () {{
  var init = function () {{
    var store = window.CommentLayerLocal({{ endpoint: '{endpoint}' }});
    store.ready.then(function () {{
      window.CommentLayer.init({{ projectId: '{project}', storage: store,
        version: '{version}', local: true{audiences}{host} }});
    }});
  }};
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
}})();
</script>"""


def inject_local_comment_layer(html, endpoint, project, assets_base, version='',
                               audiences=False, profile='', space=None, host=False):
    """Локальний канал (фідбек Клоду у файл задачі). `host=True` — колбеки оболонки (`host_arg`). `audiences=True` — рядок
    вкладок у панелі коментатора; цей сніпет їде ЛИШЕ в робоче місце, але
    прапорець тут симетричний проєктному свідомо: обидва канали мусять уміти
    сказати «немає вкладок», інакше межа publish трималась би на тому, що
    другий сніпет туди просто не потрапляє. `space` — простір сторінки (запис
    реєстру) для `sp=` у URL інспектора, див. `inspector_ds_arg`."""
    snippet = LOCAL_COMMENT_SNIPPET.format(
        endpoint=endpoint, project=project, assets=assets_base, version=version,
        ds=inspector_ds_arg(profile, space),
        audiences=audiences_arg('local' if audiences else None), host=host_arg(host))
    out, n = re.subn(r'</body>', snippet + '</body>', html, count=1, flags=re.I)
    return out if n else html + snippet


# ---------- Роль `comments`: коментарі модуля (2b-2, Task 2; з 4b-2 — єдиний шлях, ЛІГА теж) ----------
#
# Сторінка робочого місця з командним каналом МОДУЛЯ ролі `comments`: власний модуль простору або — для ЛІГИ — вбудований
# `supabase-comments` з конфігом установки (`comments_route`). Шар коментатора той самий (`comment-layer.min.js`), сховище —
# з адаптера модуля: `window.DeaiComments.create(cfg)` (контракт — спека 2b-2). Зашитого сніпета Supabase (`COMMENT_SNIPPET`,
# до 0.10.0) більше нема; локальний (`LOCAL_COMMENT_SNIPPET`) не змінено ні на байт: його приколюють еталони
# `tests/fixtures/comments-role/`. Маркери СТАРОГО сніпета `bin/import_preview.py` тримає замороженими: опубліковані превʼю в
# обігу ще його несуть.
#
# ⛔ Банер `window.__clDown` — ПЕРШИМ тегом, ДО `<script src>` нижче: без async/defer вони виконуються ПОСЛІДОВНО, і
# `onerror` кожного з них спрацьовує РАНІШЕ, ніж встиг би виконатись цей код, якби він (як було до ревʼю старого сніпета)
# жив у скрипті ініціалізації внизу. У тій версії заблокований CDN не показував банер ЗОВСІМ: `window.__clDown` на момент
# `onerror` ще не існував, і охоронець `window.__clDown&&…` мовчки гасив виклик — перевірено живцем. Порядок тут несучий, а не
# косметика. Текст і вигляд банера — ті самі, що були у старому сніпеті.
#
# ⛔ Створення сховища — під СИНХРОННИМ `try/catch`, а НЕ лише `.catch()` на `store.ready`: адаптер сам, ПОЗА промісом, може
# кинути (у старого адаптера — `window.supabase.createClient(...)`, коли CDN не піднявся: мережевий збій АБО 200 із
# порожнім/битим тілом, який `onerror` не ловить узагалі; перевірено живцем: `TypeError: Cannot read properties of
# undefined (reading 'createClient')`). Без цієї гілки виняток летів би необробленим у консоль, а банер так і не
# малювався б.
_COMMENT_DOWN_BANNER = """<script>
window.__clDown = function (why) {{
  if (document.getElementById('cl-down')) return;
  var d = document.createElement('div');
  d.id = 'cl-down';
  d.textContent = 'Коментарі недоступні: ' + why;
  d.style.cssText = 'position:fixed;left:12px;bottom:12px;z-index:2147483647;'
    + 'background:#d14343;color:#fff;font:13px/1.4 system-ui,sans-serif;'
    + 'padding:8px 12px;border-radius:6px;box-shadow:0 4px 14px rgba(0,0,0,.3)';
  (document.body || document.documentElement).appendChild(d);
}};
</script>"""

#: Тег файла адаптера: його падіння — це падіння КОМЕНТАРІВ, тож іде в банер (на відміну від інспектора).
MODULE_CLIENT_TAG = ('\n<script src="{src}" '
                     'onerror="window.__clDown(\'адаптер коментарів не завантажився\')"></script>')

# `__deaiCommentsCfg` — `{...client_config модуля, channel}`: публічна конфігурація, яку вже перевірило ядро
# (`deai_modules.comments_client`), і канал, який будує ЯДРО. `onChange` — гачок із контракту адаптера; шар коментатора
# працює через `store.subscribe`, тож хосту він порожній. Обовʼязкові в сховища `load` і `save` (їх перевіряємо одразу,
# усередині `try`: сховище без них — банер, а не тихо мертвий коментатор); `ready` необовʼязковий — як `subscribe`/
# `remove`/`close`: тому `Promise.resolve`. `projectId` — канал: ним коментатор ключує свій локальний стан.
MODULE_COMMENT_SNIPPET = '\n' + _COMMENT_DOWN_BANNER + """
<script src="{assets}/comment-layer.min.js" onerror="window.__clDown('шар коментарів не завантажився')"></script>{client_tags}{inspector}
<script>
window.__deaiCommentsCfg = {cfg_js};
(function () {{
  var init = function () {{
    var cfg = window.__deaiCommentsCfg, store;
    if (!window.CommentLayer || !window.DeaiComments) {{
      window.__clDown('шар коментарів не піднявся');
      return;
    }}
    try {{
      store = window.DeaiComments.create(Object.assign({{}}, cfg, {{ onChange: function () {{}} }}));
      if (!store || typeof store.load !== 'function' || typeof store.save !== 'function') {{
        throw new Error('адаптер повернув сховище без load/save');
      }}
    }} catch (e) {{
      window.__clDown((e && e.message) || 'адаптер не зміг піднятись');
      return;
    }}
    Promise.resolve(store.ready).then(function () {{
      window.CommentLayer.init({{ projectId: cfg.channel, storage: store,
        version: {version_js}{audiences}{host} }});
    }}).catch(function (e) {{
      window.__clDown((e && e.message) || 'сервіс коментарів не відповів');
    }});
  }};
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
}})();
</script>"""

#: Видима примітка на ЛОКАЛЬНІЙ сторінці, коли командний канал модуля не піднявся (`comments_client` відмовив).
COMMENT_NOTICE_SNIPPET = '\n' + _COMMENT_DOWN_BANNER + '\n<script>window.__clDown({why_js});</script>'


def module_client_urls(prov, space=None):
    """Кореневі адреси файлів браузерного адаптера модуля `prov` у порядку маніфесту: вбудований —
    `/api/module-client/<id>/<файл>`, свій модуль простору (3c) — `/api/module-client/<простір>/<id>/<файл>` (свій модуль
    є лише у своєму просторі; роздається зі знімка). Без `/t/<задача>/`: це маршрут простору, а не задачі."""
    if getattr(prov, 'origin', 'builtin') == 'space':
        sid = quote(str((space or {}).get('id', '')), safe='')
        return [f'{MODULE_CLIENT_PREFIX}{sid}/{prov.id}/{name}' for name in prov.client]
    return [f'{MODULE_CLIENT_PREFIX}{prov.id}/{name}' for name in prov.client]


def inject_module_comment_layer(html, assets_base, client_urls, config, version='',
                                inspector=False, audiences=False, profile='', space=None, host=False, inspector_tag=None):
    """Канал коментарів МОДУЛЯ (`host=True` — колбеки оболонки, `host_arg`): шар коментатора (`<assets_base>/comment-layer.min.js`), файли адаптера (`client_urls`, по
    порядку), `window.__deaiCommentsCfg = config` і завантажувач із `storage: DeaiComments.create(…)`.

    `config` — вже ПЕРЕВІРЕНА публічна конфігурація з `channel` (див. `deai_modules.comments_client`/`channel_for`): тут вона
    лише екранується як JS-літерал для `<script>` (`js_literal`: `<`, `>`, `&`, U+2028/9). Решта аргументів:
    `inspector`/`audiences` лише для робочого місця дизайнера (у publish обидві межі лишаються), `space` — для `sp=` в
    інспектора (`inspector_ds_arg`); без `inspector` він розмітку не міняє зовсім.

    `inspector_tag` (0.32.0, превʼю) — ГОТОВИЙ тег оверлея з відносним шляхом (`preview_inspector_tag`): стає на те саме
    місце, що й тег Deai, — після скриптів коментарів. Він сильніший за `inspector`: превʼю шляху `/app/vendor` не має."""
    assets = html_escape(assets_base, quote=True)         # `origin` береться із заголовка `Host`: в атрибут — лише екранованим
    snippet = MODULE_COMMENT_SNIPPET.format(
        assets=assets,
        client_tags=''.join(MODULE_CLIENT_TAG.format(src=html_escape(u, quote=True)) for u in client_urls),
        inspector=inspector_tag if inspector_tag else (INSPECTOR_TAG.format(
            assets=assets, ds=inspector_ds_arg(profile, space)) if inspector else ''),
        cfg_js=js_literal(config), version_js=js_literal(version),
        audiences=audiences_arg('project' if audiences else None), host=host_arg(host))
    return _insert_before_body(html, snippet)


# Комбінований канал робочого місця (Deai 0.27.0, Б2.1) — лише з `host=1` і командним постачальником: ОДИН шар коментатора на
# ДВА сховища (`app/vendor/dual-store.js`), адресат піна = сховище. Відмінності від `MODULE_COMMENT_SNIPPET`:
#   · теги адаптера модуля — БЕЗ `onerror`-банера: падіння командного не ховає локальних (смуга в панелі оболонки, поправка 4);
#   · `why` від сервера (конфіг модуля не зібрався) — адаптер навіть не пробуємо;
#   · аудиторій дві лише коли командне живе (`team`), інакше одна — і чипів у формі нема (коментатор малює їх від двох).
# Банер `__clDown` — ПЕРШИМ тегом, як у `MODULE_COMMENT_SNIPPET` (порядок несучий, див. коментар над `_COMMENT_DOWN_BANNER`).
DUAL_AUDIENCES_JS = """(function () {
        var uk = { local: 'AI', team: 'Команді', note: 'Командні коментарі видно колегам у превʼю' };
        var en = { local: 'AI', team: 'Team', note: 'Team comments are visible to colleagues in the preview' };
        var L = uk;
        try { if (localStorage.getItem('dc-lang') === 'en') L = en; } catch (e) {}
        return [{ id: 'local', label: L.local, icon: 'bot', color: '#7C6CF0', private: true },
                { id: 'project', label: L.team, icon: 'team', note: L.note }];
      })()"""

DUAL_CLIENT_TAG = '\n<script src="{src}"></script>'

DUAL_COMMENT_SNIPPET = '\n' + _COMMENT_DOWN_BANNER + """
<script src="{assets}/local-adapter.js" onerror="window.__clDown('локальний адаптер не завантажився')"></script>
<script src="{assets}/dual-store.js" onerror="window.__clDown('сховище коментарів не завантажилось')"></script>
<script src="{assets}/comment-layer.min.js" onerror="window.__clDown('шар коментарів не завантажився')"></script>{client_tags}{inspector}
<script>
window.__deaiCommentsCfg = {cfg_js};
(function () {{
  var init = function () {{
    var cfg = window.__deaiCommentsCfg, team = null, why = {why_js};
    if (!window.CommentLayer || !window.CommentLayerLocal || !window.DeaiDualStore) {{
      window.__clDown('шар коментарів не піднявся');
      return;
    }}
    if (!why) {{
      try {{
        if (!window.DeaiComments) throw new Error('адаптер командних коментарів не завантажився');
        team = window.DeaiComments.create(Object.assign({{}}, cfg, {{ onChange: function () {{}} }}));
        if (!team || typeof team.load !== 'function' || typeof team.save !== 'function') {{
          throw new Error('адаптер повернув сховище без load/save');
        }}
      }} catch (e) {{
        if (team && typeof team.close === 'function') {{ try {{ team.close(); }} catch (x) {{}} }}
        team = null;
        why = (e && e.message) || 'адаптер не зміг піднятись';
      }}
    }}
    var auds = {auds_js};
    var store = window.DeaiDualStore({{ local: window.CommentLayerLocal({{ endpoint: {endpoint_js} }}), team: team, teamDown: why }});
    store.ready.then(function () {{
      window.CommentLayer.init({{ projectId: {project_js}, storage: store, version: {version_js},
        audiences: store.teamDown ? auds.slice(0, 1) : auds{host} }});
    }});
  }};
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
}})();
</script>"""


def inject_dual_comment_layer(html, assets_base, client_urls, config, endpoint, project, version='', team_error=None,
                              profile='', space=None):
    """Комбінований канал робочого місця (Deai 0.27.0): локальний адаптер + адаптер модуля через `DeaiDualStore`, режим хоста
    завжди, інспектор завжди (як `inject_module_comment_layer` з `inspector=True`). `team_error` — причина, з якої сервер не
    зібрав конфіг модуля (тоді `client_urls` порожній, `config` — `{}`). ⛔ Публікація сюди не доходить ніколи."""
    assets = html_escape(assets_base, quote=True)
    snippet = DUAL_COMMENT_SNIPPET.format(
        assets=assets,
        client_tags=''.join(DUAL_CLIENT_TAG.format(src=html_escape(u, quote=True)) for u in client_urls),
        inspector=INSPECTOR_TAG.format(assets=assets, ds=inspector_ds_arg(profile, space)),
        cfg_js=js_literal(config or {}), why_js=js_literal(team_error), auds_js=DUAL_AUDIENCES_JS,
        endpoint_js=js_literal(endpoint), project_js=js_literal(project), version_js=js_literal(version),
        host=host_arg(True))
    return _insert_before_body(html, snippet)


def inject_comment_notice(html, why):
    """Видима примітка внизу сторінки (банер `__clDown`): `why` — коротка причина, БЕЗ значень секретів і без тексту
    модуля (лише код відмови ядра)."""
    return _insert_before_body(html, COMMENT_NOTICE_SNIPPET.format(why_js=js_literal(why)))


def comments_provider(space=None):
    """`(постачальник, відмова)` ролі `comments` для простору ЗАПИТУ: `Module` чи `None`; якщо вирішити
    не вдалось (`ModuleError`) — `(None, помилка)`. Хто відповідає людині сторінкою (а не JSON), не мусить ловити виняток
    сам.

    `space` — запис простору, який викликач ВЖЕ вирішив (`spaces.active_space()`, один раз на запит): постачальник, конфіг
    і канал тоді рахуються з ОДНОГО запису, а не з трьох читань реєстру. Без шару просторів чи без простору запиту
    (`provider` читає реєстр лише коли простір зафіксовано) аргумент ігнорується — постачальника нема (`None`).

    Помилка НІКОЛИ не перетворюється на запасного постачальника, навіть у просторі з інтеграціями: ЛІГА — спільний Supabase (запис
    `supabase-comments`), куди піни несуть знімки приватних макетів, а `provider('comments')` кидає лише тоді, коли людина ЯВНО ввімкнула
    модуль коментарів і той не завантажився (чи `space.json` не прочитати, тож невідомо, що вона вмикала). Сторінка
    тоді лишається на локальному шарі з приміткою (`_commented`), а `/api/comment-config` віддає центральну відповідь
    модулів (`_comment_config`). У просторі БЕЗ інтеграцій те саме: явно ввімкнений і загублений модуль коментарів —
    помилка, а не мовчазне `None` («нікого»), щоб людина бачила причину (див. `deai_modules._enabled_module_is_lost`)."""
    if space is not None and (not spaces.layer_on() or spaces.request_space_id() is None):
        space = None
    try:
        return deai_modules.provider('comments', space), None
    except deai_modules.ModuleError as e:
        return None, e


#: Модуль, яким простір ЛІГА веде командні коментарі (4b-2) — той самий вбудований, що й у звичайних просторів.
COMMENTS_MODULE = 'supabase-comments'
#: Кошик Storage ЛІГИ для скріншотів пінів: картка Teams бере `meta.shotUrl` звідти (як старий адаптер 0.9.0). Джерело правди —
#: `install_config.LEGACY_SHOTS_BUCKET` (його ділить міграція ЛІГИ, 4d-3b); тут — аліас.
LEGACY_SHOTS_BUCKET = install_config.LEGACY_SHOTS_BUCKET
COMMENTS_UNCONFIGURED = 'Supabase простору ЛІГА не налаштовано: додайте адресу й ключ на екрані «Налаштування»'
#: Закон ізоляції (Д6): ізольований/тестовий прогін у справжньому домі спільних коментарів не читає. Це не «не налаштовано» — на «Підключення» не посилаємо.
COMMENTS_ISOLATED = 'спільні коментарі вимкнено в тестовому (ізольованому) запуску: він не ходить у спільний проєкт'


def comments_route(space, prov):
    """Як вести командні коментарі для ВЖЕ вирішеного постачальника `prov` (`Module` з `comments_provider`):
    `(module, ctx, channel)`, де `channel(task, tid, internal=False)` — канал задачі (`deai_modules.comment_channel_of`: схема comment-layer для
    мігрованої ЛІГИ — `comment_project` чи `dc/<задача>`, інакше `deai/<простір>/<задача>`) і `ctx` — `module_ctx` запису.
    Кидає `ModuleError` (`comments-isolated`, `module-error`, коди `module_ctx`). Не кличе код модуля.

    ⛔ Закон ізоляції (Д6, 4d-4b): ізольований прогін (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) із вбудованим `shared_state`-записом у СПРАВЖНЬОМУ
    домі машини (`isolation.real_home`) — спільного ключа не беремо: `comments-isolated` (окремий код: це не «не налаштовано», на екран
    «Підключення» не посилаємо). Свій (не вбудований) модуль цим законом не зачіпається (`_builtin_shared`). У тимчасовому домі тесту `module_ctx` бере
    налаштування й секрет ФІКСТУРИ (вигадану пару), а жива мережа відрізана підміною шва `_open` модуля."""
    if not isinstance(prov, deai_modules.Module):
        raise deai_modules.ModuleError('module-error', message='comments: no provider')
    # Канал — функція `comment_channel_of`: вбудований `supabase-comments` із `compat: "comment-layer"` (мігрована ЛІГА) веде
    # коментарі схемою comment-layer, решта модулів — `deai/<простір>/<задача>` (`channel_for`).
    channel = (lambda task, tid, internal=False:
               deai_modules.comment_channel_of(space, prov, task, tid, internal=internal))
    if _builtin_shared(space, prov) and isolation.isolated() and isolation.real_home(spaces.home()):
        raise deai_modules.ModuleError('comments-isolated', message=COMMENTS_ISOLATED)
    return prov, deai_modules.module_ctx(space, prov), channel


# ---------- Агент і командні коментарі (етап 2b-2, Task 4) ----------
#
# `bin/inbox.py`, `bin/state.py` і маршрут `/comments` читають (а `inbox` і закриває) проєктні піни. Звідки — вирішує
# ПОСТАЧАЛЬНИК ролі `comments` ПРОСТОРУ задачі (`ProjectComments`), а не з прапорця простору:
#
#     постачальник        читання                                   закриття
#     Module              `list` модуля → піни у формі REST         `resolve` модуля
#     None                `RoleOff` (роль ніхто не веде:            `RoleOff`
#                         командних коментарів нема)
#     ModuleError         `ModuleError` — лише локальні піни        `ModuleError`
#
# ⛔ `ModuleError` (явно ввімкнений модуль загубився чи `space.json` не прочитати) НІКОЛИ не перетворюється на запасного постачальника:
# Supabase ЛІГИ (запис `supabase-comments`) — СПІЛЬНИЙ проєкт, куди піни несуть знімки приватних макетів (той самий закон, що в `_commented`,
# `_comment_config` і `publish_comments`). Простір — ЯВНИМ аргументом (`spaces.active_space()`, один раз на запит чи
# команду CLI), а не з `threading.local` усередині: так рішення не залежить від того, чий простір зараз зафіксовано.

#: Скільки коментарів модуля бере агент (решту відкидаємо з позначкою) і скільки байтів вони важать разом після очищення.
MAX_AGENT_COMMENTS = 5000
MAX_AGENT_BYTES = 2 << 20
_AGENT_ID_MAX = 200
#: `id` піна: те, що справді дають CommentLayer (`crypto.randomUUID()` чи `c-<цифри>-<base36>`), і нічого більше. `id` іде
#: прямо в `resolve` модуля (а той може класти його в адресу чи запит), тож пробіл, `/`, `?`, `&`, `%`, `#`, перенос рядка
#: чи невидимий символ у ньому — відмова (`skipped`), а не «очищення»: очищений `id` уже не той, що знає модуль.
_AGENT_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}')
#: Символи, яких не місце в тексті для агента й терміналу: керівні C0/C1 (ESC, CSI, BEL, NUL, CR, VT, FF, DEL; `\n` і `\t`
#: лишаються — їх прибирає `agent_line` для однорядкових полів), м'який перенос і сполучники (U+00AD, U+034F), мовні
#: керування (U+061C, U+180B–180F), нульової ширини й керування напрямком (U+200B–200F, U+202A–202E, U+2060–206F:
#: ізоляти, невидима математика, застарілі формати), роздільники рядка й абзацу (U+2028/9), заповнювачі Hangul (U+115F,
#: U+1160, U+3164, U+FFA0), кхмерські невидимі голосні (U+17B4, U+17B5), шрифт Брайля «порожній» (U+2800), музичні
#: керування групуванням (U+1D173–1D17A), селектори варіантів (U+FE00–FE0F, U+E0100–E01EF), BOM (U+FEFF), анотації
#: (U+FFF9–FFFB), символи-теги (U+E0000–E007F) і сурогати (їх не надрукувати — `UnicodeEncodeError`). Текст модуля друкується в ТЕРМІНАЛ і читається
#: LLM-агентом: керівна послідовність міняє екран, а невидимий символ ховає від людини інструкцію, яку агент побачить.
_AGENT_BAD_CHARS = re.compile(
    r'[\x00-\x08\x0b-\x1f\x7f-\x9f\xad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u2028\u2029'
    r'\u202a-\u202e\u2060-\u206f\u2800\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff9-\ufffb\ud800-\udfff'
    r'\U0001d173-\U0001d17a\U000e0000-\U000e007f\U000e0100-\U000e01ef]')
_AGENT_VERSION = re.compile(r'[0-9]{1,9}')


class ModulePins(list):
    """Піни модуля для агента: звичайний список у формі рядків REST (див. `agent_pin`) і лічильники того, що НЕ ввійшло:
    `skipped` — зіпсовані елементи (не обʼєкт, без придатного `id`, дубль `id`, збій при очищенні), `truncated` — відкинуті
    понад межі `MAX_AGENT_COMMENTS`/`MAX_AGENT_BYTES`. Мовчки губити їх не можна: «немає відкритих» — інша відповідь,
    ніж «є, але не прочитались»."""
    skipped = 0
    truncated = 0

    def note(self):
        """Один рядок для людини про те, що не ввійшло, або `''`."""
        parts = []
        if self.skipped:
            parts.append(f'пропущено {self.skipped} зіпсованих елементів')
        if self.truncated:
            parts.append(f'відкинуто {self.truncated} понад межу')
        return ('відповідь модуля коментарів неповна: ' + ', '.join(parts)) if parts else ''


def _agent_text(v, limit):
    """Текст від модуля: лише `str`, обрізаний ДО очищення (гігантський рядок не проганяємо крізь регулярку), без символів
    `_AGENT_BAD_CHARS`; не `str` → `''`. Переноси рядка й табуляції лишаються (текст коментаря багаторядковий)."""
    return _AGENT_BAD_CHARS.sub('', v[:limit]) if isinstance(v, str) else ''


def agent_line(v, limit):
    """Те саме, але ОДИН рядок: переноси рядка й табуляції стають пробілами. Для полів, що друкуються всередині рядка (`author`, `ts`, `fp`,
    `meta.version`, текст помилки): перенос рядка в них підробляв би сусідні рядки виводу (`[dry-run] …`, `• P#9 …`)."""
    return _agent_text(v.replace('\n', ' ').replace('\t', ' ') if isinstance(v, str) else v, limit)


def agent_error(e):
    """`ModuleError` з ОЧИЩЕНИМ текстом: його `message` — текст винятку, який кинув КОД модуля (тож керує ним модуль), а `inbox`
    друкує його в термінал. Код — з таблиці ядра, але теж проходить очищення; `status` зберігається (маршрут віддає його)."""
    return deai_modules.ModuleError(agent_line(e.code, 60) or 'module-error', e.status, agent_line(e.message, 300))


def _agent_json(v, budget, depth=0):
    """Безпечна копія JSON-значення модуля: `dict`/`list` (глибина ≤ 6, ≤ 100 елементів, разом ≤ `budget[0]` вузлів), рядки
    ≤ 2000 символів, цілі в межах ±2^53, скінченні дробові, булеві й `None`; усе інше → `None`. Ключі — непорожні рядки."""
    budget[0] -= 1
    if budget[0] < 0 or depth > 6:
        return None
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v if -2 ** 53 < v < 2 ** 53 else None
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, str):
        return _agent_text(v, 2000)
    if isinstance(v, (list, tuple)):
        return [_agent_json(x, budget, depth + 1) for x in v[:100]]
    if isinstance(v, dict):
        out = {}
        for k, x in itertools.islice(v.items(), 100):
            k = _agent_text(k, 100)
            if k:
                out[k] = _agent_json(x, budget, depth + 1)
        return out
    return None


def _agent_version(v):
    """Номер версії `bornV`/`resolvedV`: невідʼємне ціле чи рядок із цифр; інакше `None` (у REST ЛІГА це `int4`)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v < 2 ** 31 else None
    if isinstance(v, str) and _AGENT_VERSION.fullmatch(v):
        return int(v)
    return None


def _agent_meta(meta):
    """`meta` піна для агента. Усе, що `inbox` друкує чи розбирає, — у строгій формі (одним рядком, малі цілі, обмежені
    списки); решта — безпечна копія JSON (`_agent_json`). `shot` не беремо: ні `inbox`, ні агентові він не потрібен, а
    обрізаний base64 гірший за відсутній."""
    meta = (_agent_json(meta, [300]) if isinstance(meta, dict) else None) or {}
    meta.pop('shot', None)
    if 'version' in meta:                                           # друкується тегом `[itN]` і розбирається `pin_target`
        v = meta['version']
        v = str(v) if isinstance(v, int) and not isinstance(v, bool) else agent_line(v, 200)
        if v:
            meta['version'] = v
        else:
            del meta['version']
    if 'url' in meta:
        meta['url'] = agent_line(meta['url'], 500)
    if 'seq' in meta:                                               # `P#<seq>`
        seq = _agent_version(meta['seq'])
        if seq is None:
            del meta['seq']
        else:
            meta['seq'] = seq
    vp = meta.pop('viewport', None)                                 # `ширина: <w>×<h>`
    if isinstance(vp, dict) and _agent_version(vp.get('w')) is not None:
        meta['viewport'] = {'w': _agent_version(vp.get('w'))}
        if _agent_version(vp.get('h')) is not None:
            meta['viewport']['h'] = _agent_version(vp.get('h'))
    ctx = meta.pop('ctx', None)                                     # `де: «крок» · розділ «…»`: ≤ 20 × 100 + 200 символів
    if isinstance(ctx, dict):
        out = {}
        if agent_line(ctx.get('heading'), 200):
            out['heading'] = agent_line(ctx.get('heading'), 200)
        if isinstance(ctx.get('active'), list):
            active = [agent_line(a, 100) for a in ctx['active'][:20] if isinstance(a, str)]
            if active:
                out['active'] = active
        if out:
            meta['ctx'] = out
    return meta


def _agent_fp(fp):
    """Відбиток елемента для агента: `tag`/`text`/`path[]` — одним рядком і обмежені (друкується `якір: <tag> «text» · path`),
    решта ключів — безпечна копія JSON (їх читає лише `pin-where`).

    ⛔ Межі НЕ вужчі за те, що читає `inbox --where` (`bin/pin-where.mjs` → `anchor.findMatch`): він рахує 0.75·схожість
    ТЕКСТУ + 0.25·схожість ШЛЯХУ при порозі 0.35, а шлях зіставляє з ХВОСТА. Тому `text` — до 2000 знаків (як рядки в
    `_agent_json`; обрізаний до 200 текст контейнера на ~250 слів падав під поріг → «на сторінці не знайдено», чого в 0.9.0,
    що віддавав сирий `fp`, не було), а `path` — ОСТАННІ 50 записів (перші 50 відкидали саме той хвіст, що порівнюється)."""
    fp = _agent_json(fp, [200]) if isinstance(fp, dict) else None
    if not fp:
        return None
    if 'tag' in fp:
        fp['tag'] = agent_line(fp['tag'], 50)
    if 'text' in fp:
        fp['text'] = agent_line(fp['text'], 2000)
    if 'path' in fp:
        fp['path'] = ([agent_line(x, 100) for x in fp['path'][-50:] if isinstance(x, str)]
                      if isinstance(fp['path'], list) else [])
    return fp


def agent_pin(c):
    """Коментар модуля (форма CommentLayer: `id, author, text, status, fp, htmlSnapshot, meta, bornV, resolvedV,
    resolveReason, ts`) → рядок у формі REST ЛІГА (`id, text, status, author, ts, meta, born_v, fp, html_snapshot,
    resolved_v, resolve_reason`), яку чекають `inbox` і маршрут `/comments`; `None` — елемент зіпсований.

    Лише ці поля й лише потрібних типів: `inbox` робить `fp['path'][-3:]`, `meta['viewport'].get(…)`, `str.strip()` — тож
    чужий тип у них був би падінням CLI, а не «поганим піном». `id` — за білим списком `_AGENT_ID`, інакше елемент
    пропускається: чужий `id` іде в `resolve` модуля, а очищений `id` уже не той, що знає модуль. Однорядкові поля (`author`,
    `ts`, `resolve_reason`, `fp`, `meta.version`…) — без переносів рядка; `text` багаторядковий, як і в Supabase."""
    if not isinstance(c, dict):
        return None
    pid = c.get('id')
    if not isinstance(pid, str) or not _AGENT_ID.fullmatch(pid):
        return None
    snap = c.get('htmlSnapshot')
    snap = ({'text': _agent_text(snap.get('text'), 2000), 'outerHTML': _agent_text(snap.get('outerHTML'), 20000)}
            if isinstance(snap, dict) else None)
    return {'id': pid,
            'text': _agent_text(c.get('text'), 10000),
            'status': 'resolved' if c.get('status') == 'resolved' else 'open',
            'author': agent_line(c.get('author'), 200),
            'ts': agent_line(c.get('ts'), 40),
            'meta': _agent_meta(c.get('meta')),
            'born_v': _agent_version(c.get('bornV')),
            'fp': _agent_fp(c.get('fp')),
            'html_snapshot': snap if snap and (snap['text'] or snap['outerHTML']) else None,
            'resolved_v': _agent_version(c.get('resolvedV')),
            'resolve_reason': agent_line(c.get('resolveReason'), 1000) or None}


def agent_pins(raw):
    """Відповідь `list` модуля → `ModulePins`. Не список (чи список, який не читається) — `ModuleError('module-error')`:
    модуль зламаний, і «порожньо» було б брехнею. Зіпсований елемент пропускається й рахується (`skipped`), дубль `id` — теж
    (лишається перший); понад `MAX_AGENT_COMMENTS` штук чи `MAX_AGENT_BYTES` байтів — відкидається й рахується
    (`truncated`)."""
    if not isinstance(raw, list):
        raise deai_modules.ModuleError('module-error', message='the comments module must answer list() with a list')
    out, seen, size = ModulePins(), set(), 0
    try:
        total = len(raw)
        for i, c in enumerate(raw):
            if len(out) >= MAX_AGENT_COMMENTS or size > MAX_AGENT_BYTES:
                out.truncated = total - i
                break
            try:
                pin = agent_pin(c)
            except Exception:  # noqa: BLE001 — чужий об'єкт із норовливим `get`/`items`: це «зіпсований елемент»
                pin = None
            if pin is None or pin['id'] in seen:
                out.skipped += 1
                continue
            seen.add(pin['id'])
            out.append(pin)
            size += len(json.dumps(pin, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — список із норовливим `__iter__`/`__len__`
        raise deai_modules.ModuleError('module-error', message='the comments module answered list() with an unreadable list')
    return out


#: Скільки «нових» віддає `/api/comment-news` (і чекає від `recent` модуля).
MAX_NEWS = 200


def agent_news(raw):
    """Відповідь `recent` модуля → `[{id, ts, author, status: 'open', version}]` лише відкритих, ≤ `MAX_NEWS`. Не список —
    `ModuleError`. Поля — як у `agent_pin`: `id` за `_AGENT_ID` (інакше пропуск), однорядкові тексти без керівних символів."""
    if not isinstance(raw, list):
        raise deai_modules.ModuleError('module-error', message='the comments module must answer recent() with a list')
    out, seen = [], set()
    for c in raw[:MAX_NEWS * 4]:
        if not isinstance(c, dict) or c.get('status') == 'resolved':
            continue
        pid = c.get('id')
        if not isinstance(pid, str) or not _AGENT_ID.fullmatch(pid) or pid in seen:
            continue
        seen.add(pid)
        v = c.get('version')
        ver = str(v) if isinstance(v, int) and not isinstance(v, bool) else agent_line(v, 200)
        out.append({'id': pid, 'ts': agent_line(c.get('ts'), 40), 'author': agent_line(c.get('author'), 200),
                    'status': 'open', 'version': ver or None})
        if len(out) >= MAX_NEWS:
            break
    return out


#: Хто бере командний коментар (Deai 0.27.0, спека Б-Р6): лише доручений Claude — `meta.assignee == 'claude'`.
ASSIGNEE_CLAUDE = 'claude'


def for_agent(c, store):
    """Чи цей пін — робота Claude. `store`: `'local'` (локальний файл задачі — завжди так) чи `'project'` (командний канал —
    лише доручений: `meta.assignee == 'claude'`). ОДНЕ правило для `bin/inbox.py`, `bin/state.py` і маршруту `/comments`
    (спека Б2.3): три копії розійшлися б у числах. Приймає обидві форми піна (CommentLayer і рядок REST): `meta` в них однакове."""
    if store == 'local':
        return True
    meta = c.get('meta') if isinstance(c, dict) else None
    return isinstance(meta, dict) and meta.get('assignee') == ASSIGNEE_CLAUDE


class ProjectComments:
    """Хто веде проєктні коментарі простору `space` для АГЕНТА (див. таблицю вище). Рішення береться ОДИН раз у
    конструкторі, з явного `space`; решта методів лише виконують його для задачі `(task, tid)`.

    `kind`: `'module'` | `'off'` (нікого: простір без інтеграцій і без модуля) | `'broken'` (рішення не вдалось, `err` —
    `ModuleError`). `'module'` іде функціями модуля (`comments_route`); ЛІГА — явний запис `supabase-comments` із каналом `comment_channel`.

    Простір запиту мусить бути ЗАФІКСОВАНИМ (`task_anywhere`, `_take_task`): `comments_provider` без нього ігнорує `space` і
    віддав би `None` (інструменти ЛІГА без простору). Тут це НЕ годиться: викликач передав запис простору, а запиту без простору
    немає — це `broken` (`module-error`), а не мовчазне «нікого». `space=None` без простору запиту — `None`, як і було.

    Усі `ModuleError` назовні — з ОЧИЩЕНИМ текстом (`agent_error`): текст винятку кидає код модуля, а його друкують у термінал.

    ⚠️ Виконує код модуля (`list`/`resolve`): НЕ кликати під `spaces.WRITE_LOCK`."""

    def __init__(self, space):
        self.space = space
        if space is not None and spaces.layer_on() and spaces.request_space_id() is None:
            self.prov, self.err = None, deai_modules.ModuleError(
                'module-error', message='comments: the request has no pinned space')
        else:
            self.prov, self.err = comments_provider(space)
        if isinstance(self.prov, deai_modules.Module) and space is None:
            # Постачальник-модуль без явного простору (його вирішив простір запиту, а викликач не передав запису): без
            # запису не зібрати ні `ctx`, ні канал — це відмова, а не вгадування.
            self.prov, self.err = None, deai_modules.ModuleError(
                'module-error', message='comments: the space of the request is not known')
        if self.err is not None:
            self.err = agent_error(self.err)

    @property
    def kind(self):
        if isinstance(self.prov, deai_modules.Module):
            return 'module'
        return 'broken' if self.err is not None else 'off'

    @property
    def legacy_scheme(self):
        """Чи коментарі ведуться за схемою comment-layer (мігрований вбудований `supabase-comments` із
        `compat`): та сама умова, що в функції каналу. ⛔ Те, що раніше різнилось за `kind == 'module'` («це не ЛІГА»), мусить
        читати ЦЕЙ предикат: `kind` мігрованої ЛІГИ лишається `'module'`."""
        return deai_modules.comment_scheme_legacy(self.space, self.prov)

    @property
    def label(self):
        """Хто джерело — для людини (заголовок `inbox`). «Supabase» — лише коли він справді джерело (і для мігрованої ЛІГИ)."""
        if self.kind == 'module' and self.legacy_scheme:
            return 'Supabase'
        return {'module': lambda: f'модуль {self.prov.id}',
                'broken': lambda: 'модуль недоступний', 'off': lambda: 'не підключено'}[self.kind]()

    def channel(self, task, tid, internal=False):
        """Канал задачі: модуль чи ЛІГА — `deai_modules.comment_channel_of` (схема за `compat`); нікого/збій — схема comment-layer."""
        if self.kind == 'module':
            return deai_modules.comment_channel_of(self.space, self.prov, task, tid, internal=internal)
        return deai_modules.legacy_comment_channel(task, tid, internal)

    def _check(self):
        if self.err is not None:
            raise self.err
        if self.kind == 'off':
            raise spaces.RoleOff('integrations-off')

    @property
    def takes_iteration(self):
        """Чи передаємо номер ітерації в `resolve`: лише вбудованому `supabase-comments` (свій модуль простору міг оголосити
        `resolve(ctx, channel, id, reason)` — зайвий аргумент його зламав би). У мігрованої ЛІГИ — так само (її запис — вбудований)."""
        return (self.kind == 'module' and self.prov.id == COMMENTS_MODULE
                and getattr(self.prov, 'origin', 'builtin') == 'builtin')

    def _module(self, fn, task, tid, internal, *args):
        """Виклик функції модуля (`list`/`resolve`) для каналу задачі — і для модуля простору, і для ЛІГИ (`comments_route`);
        будь-який `ModuleError` — з очищеним текстом.

        Простір без постачальника ролі (`kind == 'off'`) сюди не доходить: `_check` відмовляє раніше (`RoleOff` — `OSError`, а не
        `ModuleError`: наявні `except OSError` деградують чесно). Умови «є інтеграції» тут нема: їх рішення — наявність явного запису
        `supabase-comments` (4d-4b), а закон ізоляції тримає `comments_route`."""
        try:
            mod, ctx, channel = comments_route(self.space, self.prov)
            return deai_modules.call(mod, fn, ctx, channel(task, tid, internal), *args,
                                     timeout=deai_modules.COMMENTS_TIMEOUT)
        except deai_modules.ModuleError as e:
            raise agent_error(e) from None

    def pins(self, task, tid, internal=False):
        """Проєктні піни задачі у формі рядків REST. `RoleOff` — нікого (`'off'`: ролі `comments` ніхто не веде),
        `ModuleError` — рішення чи виклик модуля не вдались (або відповідь не список; ізольований прогін у справжньому домі —
        `comments-isolated`)."""
        self._check()
        return agent_pins(self._module('list', task, tid, internal))

    def recent(self, task, tid):
        """Відкриті командні коментарі каналу задачі для лічильника «нових» (`agent_news` відповіді необовʼязкової
        `recent(ctx, channel)` модуля); модуль без неї — `None` (вкладка просто без числа). Канал — той, у який пише рамка
        (`internal=False`)."""
        self._check()
        if self.prov.fn('recent') is None:
            return None
        return agent_news(self._module('recent', task, tid, False))

    def resolve(self, task, tid, pin_id, reason, iteration=None, internal=False):
        """Закрити пін модулем (`resolve(ctx, channel, id, reason[, iteration])`); номер ітерації — лише коли
        `takes_iteration`. `id` — лише за білим списком `_AGENT_ID` (як і в `list`).

        ⚠️ `meta.resolvedAt` НЕ їде (урок `patch_project_pin`, 15.09.2026): PostgREST міняє jsonb цілком, а в `meta` лежать
        `shot` (base64) і `shotUrl`; переписати весь `meta` заради однієї мітки — ризикнути затерти те, що дописав браузер.
        Модуль пише лише `status`/`resolved_v`/`resolve_reason`. Наслідок: на вкладці «Closed» comment-layer такий пін
        сортується як закритий без часу. (Тиха відсутність рядка тепер не проходить: модуль просить `return=representation`
        і на порожню відповідь каже «коментар не знайдено».)"""
        self._check()
        if not isinstance(pin_id, str) or not _AGENT_ID.fullmatch(pin_id):
            raise deai_modules.ModuleError('module-error', message='comments: the pin id is not a safe identifier')
        args = (pin_id, reason, iteration) if self.takes_iteration and iteration is not None else (pin_id, reason)
        self._module('resolve', task, tid, internal, *args)
        return None


def _insert_before_body(html, snippet):
    """Вставити фрагмент перед `</body>` (або в кінець, якщо тега немає).

    ⛔ НЕ через `re.sub`/`re.subn`: там рядок ЗАМІНИ обробляє бекслеші як escape,
    і фрагмент із `\\uXXXX` (json.dumps кирилиці) або `\\1` тихо ламається або
    кидає `re.error`. Знаходимо позицію регуляркою, склеюємо звичайними рядками.
    """
    m = re.search(r'</body>', html, flags=re.I)
    if not m:
        return html + snippet
    return html[:m.start()] + snippet + html[m.start():]


def _inject_gate(html, gate):
    """Вставити гейт у сторінку макета. Ідемпотентно: повторний виклик нічого не
    додає (сторінка може вже мати гейт, якщо публікують перепубліковане).

    Заголовок вкладки теж нейтралізуємо: до пароля назва задачі й номер тікета не
    мають світитись навіть у title (правило 30.07.2026 — обгортка його дотримує, а
    внутрішня сторінка світила «Віджет «Суди» · … · LIGA-7003»). Після входу
    справжній заголовок повертаємо.
    """
    if 'id="authgate"' in html:
        return html
    m = re.search(r'<title>(.*?)</title>', html, flags=re.I | re.S)
    if m:
        # Скрипт СТАВИМО ПЕРЕД гейтом: його IIFE може розблокувати сторінку
        # одразу (sessionStorage) і мусить уже бачити __origTitle.
        # ⛔ Назву пише дизайнер: літерал — лише через `js_literal` (голий `json.dumps` не чіпає
        # `</`, і `</script>` у `<title>` проривав скрипт — клас інциденту 04.08.2026). І значення
        # РОЗЕКРАНОВУЄМО: у `<title>` сутності — розмітка (`R&amp;D`), а `document.title` — вже
        # текст, тож без `unescape` вкладка після входу показувала б буквальне `R&amp;D`.
        gate = (f'<script>window.__origTitle={js_literal(html_unescape(m.group(1)))};</script>'
                + gate)
        html = html[:m.start()] + '<title>Перегляд макета</title>' + html[m.end():]
    return _insert_before_body(html, gate)


def _gate_logo_svg():
    """Знак Deai для воріт: той самий `LOGO_SVG` (`app/logo.js`), інлайном, без зовнішніх запитів. Ворота стоять ДО
    `shell/styles.css`, тож токен `--logo-in` (білий прямокутник усередині) підставляємо літералом."""
    with open(os.path.join(APP_DIR, 'logo.js'), encoding='utf-8') as fh:
        m = re.search(r'LOGO_SVG\s*=\s*`(<svg.*?</svg>)`', fh.read(), flags=re.S)
    return m.group(1).replace('var(--logo-in)', '#fff') if m else ''


#: Ворота стоять до завантаження `shell/styles.css` (обгортка тягне його лише після входу), тому вигляд — самодостатній:
#: поверхні й тексти типового простору (`--s0`, `--s2`, `--s3`, `--line2`, `--hi`, `--dim`, `--sel`) скопійовані
#: ЛІТЕРАЛАМИ. Це Python, а не CSS: охоронець «без літералів» (`css-guards`) сюди не сягає.
GATE_SNIPPET = """
<style>#authgate{{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px;background:#1a231e;color:#f3f8f5;font-family:system-ui,sans-serif}}
#authform{{width:340px;max-width:100%;display:flex;flex-direction:column;gap:12px;margin:0;padding:28px 26px 24px;background:#323c36;border:1px solid #545e58;border-radius:10px}}
#authform .gmark{{display:flex;align-items:center;gap:10px;color:#969F9A}}
#authform .gmark svg{{width:28px;height:28px;flex:none}}
#authform h1{{margin:0;font-size:18px;font-weight:650;color:#f3f8f5}}
#authform .gsub{{margin:2px 0 4px;font-size:12px;color:#a6afaa}}
#authform input{{width:100%;height:40px;padding:0 10px;font:inherit;font-size:14px;color:#f3f8f5;background:#29332e;border:1px solid #545e58;border-radius:6px}}
#authform input:focus{{border-color:#e2eae6}}
#authform input:focus-visible,#authform button:focus-visible{{outline:2px solid #e2eae6;outline-offset:2px}}
#authform button{{width:100%;height:40px;font:inherit;font-size:14px;color:#1a231e;background:#e2eae6;border:1px solid #e2eae6;border-radius:6px;cursor:pointer}}
#authform button:hover{{background:#f7faf8}}
#agerr{{display:none;margin:0;font-size:12px;color:#F37373}}</style>
<div id="authgate"><form id="authform">
  <!-- До входу назви задачі/тікета НА ЕКРАНІ не показуємо (правило 30.07.2026).
       ⚠️ Але це оверлей у браузері, а не замок: пароль вшитий у джерело цієї ж
       сторінки (`P` нижче), ключ сесії несе id задачі, а `manifest.json` і самі
       сторінки макета лежать статикою й віддаються без жодної перевірки. Тому
       підпис НЕ каже «захищено»: обіцянка захисту тут була б неправдою, а
       повірить у неї не глядач, а дизайнер, який відправляє посилання.
       Справжня приватність = серверний захист (Vercel Deployment Protection). -->
  <div class="gmark">{logo}</div>
  <div><h1>Перегляд макета</h1><div class="gsub">внутрішній матеріал</div></div>
  <input id="agpass" type="password" autocomplete="current-password" placeholder="Пароль" aria-label="Пароль" aria-describedby="agerr">
  <p id="agerr" role="alert" aria-live="polite">Невірний пароль</p><button type="submit">Увійти</button>
</form></div>
<script>(function(){{var KEY={key_js},P={pw_js};
function unlock(){{var g=document.getElementById('authgate');if(g)g.remove();
  // Справжній заголовок — лише після входу (до нього в title нейтральний текст).
  try{{if(window.__origTitle)document.title=window.__origTitle;}}catch(e){{}}
  // Хук для обгортки: вона НЕ вантажить iframe до розблокування, інакше внутрішня
  // сторінка (у якої тепер теж є гейт) показала б свій гейт усередині рамки.
  window.__gateOpen=true;if(window.__onGateOpen)window.__onGateOpen();}}
function save(){{try{{sessionStorage.setItem(KEY,'1')}}catch(e){{}}}}
// Безшовний вхід із Liga Design Office: токен у hash (#k=<код>) → авто-розблокування.
// ⛔ Прибираємо з hash ЛИШЕ свій `k=`, решту лишаємо: там їде `p=<сторінка>` —
// глибоке посилання обгортки. Раніше тут стояв голий pathname+search, і hash
// зносився цілком, тобто посилання «відкрий саме цю ітерацію» гинуло на вході.
try{{var h=location.hash||'',m=h.match(/(?:^#|&)k=([^&]+)/);
  if(m&&decodeURIComponent(m[1])===P){{save();
    var rest=h.replace(/^#/,'').split('&').filter(function(s){{
      return s&&s.indexOf('k=')!==0;}}).join('&');
    history.replaceState(null,'',location.pathname+location.search+(rest?'#'+rest:''));
    unlock();return;}}}}catch(e){{}}
try{{if(sessionStorage.getItem(KEY)==='1'){{unlock();return;}}}}catch(e){{}}
document.getElementById('authform').addEventListener('submit',function(e){{
  e.preventDefault();
  if(document.getElementById('agpass').value===P){{save();unlock();}}
  else document.getElementById('agerr').style.display='block';}});}})();</script>"""


PAGES_PREVIEW_PAGE = """<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- Нейтральний заголовок: URL превʼю може потрапити кому завгодно, а справжню
     назву задачі оболонка ставить уже під ВІДКРИТИМ гейтом (правило
     30.07.2026). Тут її нема звідки взяти — див. `preview_index_html`. -->
<title>Перегляд макета</title>
<link rel="stylesheet" href="shell/styles.css">
</head><body>
{gate}
<div id="sprite"></div>
<div id="bar" class="bar-mount"></div>
<div id="stage" class="cv-stage"><iframe id="frame" class="cv-frame"></iframe></div>
<!-- Панель коментарів (0.32.0): порожня точка монтування справа; наповнює її `ext-shell.js` лише в збірці з командними коментарями. -->
<div id="cmt-panel" class="insp cmt" hidden></div>
<!-- Панель інспектора (0.32.0): та сама точка справа, лише для перегляду; наповнює її `ext-shell.js`, стара оболонка її не чіпає. -->
<div id="insp-panel" class="insp" hidden></div>
<!-- Пароль — рівно для «Копіювати посилання» (`#k=…`, безшовний вхід колеги).
     У маніфест він НЕ їде: той файл читає оболонка, і пароль задачі їй знати
     нізащо, а лежить він і так у тексті гейта поруч. -->
<script>window.__extPw={pw_js};</script>
<script type="module" src="shell/ext-shell.js"></script>
</body></html>"""


# ── Що везе публікація, крім самих макетів ────────────────────────────────────
# Три переліки в одному місці, бо всі три відповідають на одне питання: «що
# мусить лежати в publish/, щоб опубліковане превʼю працювало без сервера».
# Розкидані по коду, вони мовчки розходяться з тим, що превʼю справді вантажить,
# а побачить розбіжність не тест і не дизайнер, а ГЛЯДАЧ — бо `publish/` в
# щоденній роботі не відкривається.

#: Імена бандлів СТАРИХ збірок ЛІГИ (до 0.10.0); нові їх не везуть: шар коментатора + файли адаптера модуля.
#: Перелік лишається — його читають `ops/reseal_gate.py` і перевірка імен файлів адаптера (`_read_module_comments`).
BUNDLES = ('comment-layer.min.js', 'supabase-adapter.min.js')
#: Хто збирає превʼю (`build_preview(build=…)`, `manifest.json` → `"build"`): ЛІГА (далі Vercel) чи модуль публікації.
BUILD_KINDS = ('legacy', 'module')
#: Шар коментатора — єдиний бандл, який їде в збірку і в канал МОДУЛЯ (адаптер сховища дає сам модуль); `supabase-adapter` —
#: лише ЛІГА, і лише збірок ДО 0.10.0 (так само, як у `BUNDLES` вище: нові збірки ЛІГИ везуть файли модуля, не його).
#: Тож збірка, де є ОБИДВА бандли, — збірка ЛІГА: це запасне правило `ops/reseal_gate.py` для збірок БЕЗ мітки
#: `build` у маніфесті (зібраних до неї); для решти рішає мітка (`BUILD_KINDS`).
LAYER_BUNDLE = 'comment-layer.min.js'

#: Спільні модулі оболонки в publish/shell/ — копіюються з app/ БЕЗ правок.
#: Саме тому вони й зроблені чистими (ні DOM-глобалів, ні fetch, ні
#: localStorage): у статиці на Vercel джерела правди, крім `manifest.json`,
#: немає. Перелік мусить бути ЗАМКНУТИМ по імпортах — забутий лист це 404 на
#: `shell/<модуль>` і оболонка, що не піднялась (замкнутість стереже тест).
#: Останні два — ВЛАСНІ модулі зовнішньої оболонки (в інструменті їх немає
#: зовсім): `ext-shell.js` вантажить обгортка, `ext-bar.js` він імпортує.
#: `ask.js` — оверлей замість `prompt()`: фолбек «Копіювати посилання», коли
#: буфер обміну недоступний (правило проєкту, `tests/browser-dialogs.test.mjs`).
#: `esc.js` — спільне екранування (TD-12, 18.09.2026): `shell-panel.js` і
#: `ext-bar.js` більше не носять по власній копії, тож лист став обовʼязковим.
#: Забути його тут означало б 404 і НІМУ оболонку в глядача — і саме це
#: спіймав `test_list_is_closed_under_imports` у ту ж хвилину, коли копії
#: зникли: замкнутість переліку рахується, а не тримається на памʼяті.
#: `tree-model.js` — правила дерева сторінок: від нього залежать `rows-model.js`
#: і `ext-shell.js` (обидва беруть лише `kindOf`), тож без нього оболонка превʼю
#: ловить 404 на імпорті (A7).
#: `ext-inspect.js` (власний модуль превʼю), `shell-inspect.js`, `insp-panel.js`, `insp-model.js` — панель інспектора лише для
#: перегляду (0.32.0). `insp-model.js` імпортує `./vendor/inspector-core.js`, тож `shell/vendor/` (`SHELL_VENDOR`) — частина
#: того самого замикання; сам оверлей з `shell/vendor/` бере `../i18n.js` і `../esc.js` звідси.
#: Модулі їдуть звідси байт у байт. Опція «під зовнішній режим» у спільному модулі допустима, лише коли ДЕФОЛТНИЙ вихід
#: приколений золотими тестами (так 0.32.0 додав `readonly` панелі інспектора); гілка «а в превʼю інакше» без цього ламала б
#: інструмент.
SHELL_MODULES = ('i18n.js', 'icons.js', 'shell-panel.js', 'viewport.js',
                 'camera.js', 'canvas-geom.js', 'layout.js', 'rows-model.js',
                 'styles.css', 'ask.js', 'esc.js', 'ext-shell.js', 'ext-bar.js',
                 'tree-model.js', 'clean-view.js', 'island.js',
                 'ext-comments.js', 'comments-view.js', 'comments-model.js', 'inline-confirm.js',
                 'ext-inspect.js', 'shell-inspect.js', 'insp-panel.js', 'insp-model.js', 'ext-follow.js')

#: Типова ширина кадру. МУСИТЬ дорівнювати `CANVAS_W` у app/viewport.js:
#: саме на ній тримається правило ключа («типова ширина суфікса не додає»), і
#: розбіжність означала б, що публікація складає `frames` за одними ключами, а
#: зовнішній «Огляд» шукає кадри за іншими. Звірку тримає тест.
CANVAS_W = 1280

# Порт `splitFrameKey` з app/viewport.js — включно з тим, що все не схоже на
# ширину лишається частиною ключа: манифест приїжджає з чужої машини, і сміття
# не сміє прикидатись шириною.
# `\Z`, а не `$`: у Python `$` збігається ще й ПЕРЕД кінцевим переносом рядка,
# тобто `'main@768\n'` розібрався б на ширину тут і НЕ розібрався б у браузері —
# порт, який розходиться з оригіналом рівно на одному символі, гірший за явно
# інший алгоритм, бо виглядає однаковим.
_FRAME_W_RE = re.compile(r'^(.*)@([1-9]\d{1,3})\Z')


def split_frame_key(fid):
    """`'main@768'` → `('main', 768)`; `'main'` → `('main', CANVAS_W)`."""
    m = _FRAME_W_RE.match(str(fid))
    return (m.group(1), int(m.group(2))) if m else (str(fid), CANVAS_W)


def _frame_size(rec):
    """`{'w': …, 'h': …}` із запису зʼємки — або ПОРОЖНЄ, якщо міряного немає.

    ⛔ Валідація, а не довіра. `shots/manifest.json` пише наш же конвейєр зʼємки,
    але читаємо ми його як ДАНІ, а не як обіцянку: файл лежить на диску, його
    правлять руками, і прогон могло перервати посередині (та сама межа, заради
    якої вище стоїть попередження про битий манифест).

    Нуль і відʼємне гірші за відсутність: зовнішнє полотно рахує пропорцію
    картки як `h * cardW / w`, тобто нуль у знаменнику дав би `Infinity`, а
    рядок — `NaN`; `rowsLayout` (`app/layout.js`) на такому кидає виняток —
    на світі, який глядач мав побачити. Тому непридатний розмір не їде взагалі,
    і вигаданого числа замість нього теж немає: маніфест не сміє СТВЕРДЖУВАТИ
    розмір, якого ніхто не міряв. Оболонка тоді спитає пропорцію в самого
    знімка (`onFrameLoad` в `ext-shell.js`) — робоча дорога, не аварійна.

    Розмір — ПАРА: половина його не варта нічого, бо пропорція вимагає обох.
    `bool` відсікаємо явно, бо в python `True` — це `int`: без цього `h: true`
    стало б висотою 1px, і то «за даними».
    """
    if not isinstance(rec, dict):
        return {}
    w, h = rec.get('w'), rec.get('h')
    ok = all(isinstance(v, int) and not isinstance(v, bool) and v > 0
             for v in (w, h))
    return {'w': w, 'h': h} if ok else {}


def publish_frames(task, it_id, pages, dst_dir):
    """Кадри ітерації в `publish/<it>/_frames/`.

    → `({frameKey: {'path': relPath, 'w': …, 'h': …}}, warning|None)`, де `w`/`h`
    — розмір ЗНІМКА в пікселях, заміряний зʼємкою, і його може не бути (див.
    `_frame_size`). Зайві поля запису зʼємки (`sha`, `bytes`, `stable`…) не
    їдуть: маніфест лежить статикою в чужому браузері, і там нема кому їх
    читати.

    ⚠️ `w` тут — НЕ ширина вьюпорта. Кадр, знятий із подвоєною щільністю, має
    `w` удвічі більше за ширину в своєму ключі, і саме тому пропорцію рахують
    діленням на `w`, а не беруть `h` як висоту картки. Ширина вьюпорта живе
    ТІЛЬКИ в ключі (`split_frame_key`) — звідти її й бере `publish_manifest`.

    ⛔ Фільтр — ТОЙ САМИЙ, що в сторінок: у превʼю їде кадр лише тієї сторінки,
    яка сама туди їде. Це вимога конфіденційності, а не вага: сторінку знімають
    з превʼю руками, і кадр знятої сторінки показав би менеджеру в «Огляді»
    рівно те, що від нього прибрали. Тому відповідь про «що опубліковано» тут не
    рахується вдруге, а береться з `published_pages` — тієї самої функції, що
    вирішує це для сторінок (див. її докстрінг: дві копії фільтра — рівно та
    пара, що розходиться молча).

    Кадр СТАНУ (`page~30d36f19`) успадковує публікацію своєї сторінки — те саме
    правило, що в `rows-model.js`: стан це та сама сторінка в іншому вигляді, і
    крапки «у превʼю» на одному екрані не сміють суперечити одна одній.

    Джерело переліку — `shots/manifest.json`, а не `listdir`: манифест і є
    записом про те, що зʼємка справді зробила (файл без запису — це або сміття
    від перерваного прогону, або кадр, який зʼємка вже визнала непотрібним).

    ⚠️ Друге значення — попередження, і воно тут не для симетрії. Битий манифест
    не сміє валити публікацію (макети готові, посилання чекають), але й тиха
    гілка була б найгіршою з трьох: превʼю зібралось, «Огляд» у глядача
    порожній, і ніде жодного слова про причину. Тиша належить ЛИШЕ «файла нема»
    — ітерацію могли просто ще не знімати (та сама межа, що в `_shots_manifest`
    і `_flow_get`); усе інше — биті права, тека замість файла, валідний JSON, що
    не обʼєкт — доходить до дизайнера словами.

    ⚠️ Свідома різниця з `_shots_manifest`: там манифест без `shots` тихо стає
    порожнім, бо той роут живить полотно й мусить деградувати до «ще не знімали».
    Тут навпаки: публікація буває раз, після неї йде посилання менеджеру, і
    другого разу подивитись у цей файл ніхто не прийде.
    """
    wanted = {p['page']['id'] for p in pages if p['it'] == it_id}
    src_dir = os.path.join(_iter_dir(task, it_id), 'shots')
    man = os.path.join(src_dir, 'manifest.json')
    try:
        with open(man, encoding='utf-8') as fh:
            data = json.load(fh)
    except FileNotFoundError:
        # ⛔ Ця гілка мусить стояти ВИЩЕ за OSError (FileNotFoundError — його
        # підклас), інакше «ще не знімали» почало б виглядати помилкою.
        return {}, None
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return {}, f'{it_id}: shots/manifest.json не читається ({e}) — кадри не поїхали'
    shots = data.get('shots') if isinstance(data, dict) else None
    if not isinstance(shots, dict):
        return {}, (f'{it_id}: у shots/manifest.json немає обʼєкта `shots` '
                    f'(лежить {type(shots).__name__}) — кадри не поїхали')
    frames = {}
    for fid in sorted(shots):
        # ⛔ Ключ із манифеста стає ІМЕНЕМ ФАЙЛА в publish/ — тому та сама
        # перевірка, що стереже роут /shot, а не послаблена «майже така». Без
        # неї `../../..` у ключі писав би кудись за межі превʼю.
        if not SHOT_RE.match(str(fid)):
            continue
        base, _w = split_frame_key(fid)
        if base.split('~')[0] not in wanted:
            continue
        src = os.path.join(src_dir, f'{fid}.webp')
        if not os.path.isfile(src):
            continue      # запис є, файла немає — кадр просто не малюватиметься
        os.makedirs(dst_dir, exist_ok=True)
        shutil.copy2(src, os.path.join(dst_dir, f'{fid}.webp'))
        # Розмір — із ЦЬОГО ж запису: інакше зовнішнє полотно не знає висоти
        # картки, поки кадр не приїхав, і світ «сідає» під справжні пропорції
        # вже на очах глядача (розкид справжніх висот заміряний — 900…8000px).
        frames[fid] = {'path': f'{it_id}/_frames/{fid}.webp',
                       **_frame_size(shots[fid])}
    return frames, None


#: Покоління оболонки превʼю, що їде в `manifest.json` (`shell`). Обгортка (`PAGES_PREVIEW_PAGE`) і `shell/` змінюються
#: РАЗОМ; `ops/reseal_gate.py` перепечатує лише обгортку, тож відмовляє на збірці зі старшою оболонкою (`shell < 2`).
PREVIEW_SHELL_VERSION = 2


def publish_manifest(task, tid, its, pages, frames, dst_dir, trees=None, build=None, comments=None):
    """`publish/manifest.json` — ЄДИНЕ джерело правди зовнішньої оболонки.

    Без `serve.py` у превʼю немає ні `/api/task`, ні `/api/iteration-pages`, ні
    `/api/shots`; усе, що оболонка знає про задачу, лежить у цьому файлі. Тому
    склад полів стережеться тестом, а не «складеться сам».

    `outline` — усе видиме дерево З ТЕКАМИ для панелі превʼю (рядки
    `{id, it, key, name, kind, depth[, path]}`; у теки `path` нема — файла немає,
    а `id` лежить у тому ж просторі `<it>/<id>`, що й `out_rel` сторінок).
    `pages` лишається переліком ВІДКРИВАНИХ вузлів — з нього живуть сторінка за
    замовчуванням, картки полотна, `pageById`; тому теки туди НЕ додаємо, а
    веземо окремим ключем. Обидва перелічені одним правилом видимості
    (`pm.preview_flat` / `pm.preview_outline`).

    `build` — мітка збирача (`BUILD_KINDS`: `'legacy'` — ЛІГА, `'module'` — модуль публікації), ключ `"build"` ОСТАННІМ у
    файлі. Це для `ops/reseal_gate.py`: оболонка ключа не читає (бере лише названі поля), а `None` (виклик без мітки,
    старі збірки) ключа не пише — тоді reseal сам вгадує за складом `comment-layer/`.

    `comments` — канал командних коментарів збірки (рядок) або `None` (без коментатора). Є — ключ `"comments": {"channel": …}`
    (перед `build`, який лишається останнім): це ЄДИНИЙ сигнал оболонці превʼю (`ext-shell.js`), що в збірці є командні
    коментарі, — кнопка «Коментарі» й панель зʼявляються лише з ним. Канал і так лежить у кожній сторінці збірки
    (`__deaiCommentsCfg`), тож маніфест нічого нового не відкриває; оболонка ключує ним «мої» коментарі в localStorage.

    `trees` — `{it: дерево}`, знятий `_publish` ОДИН раз на всю збірку: `outline`
    і `pages` тоді рахуються з того самого знімка, а не з двох читань pages.json
    (дизайнер міг змінити дерево між ними). Без `trees` читаємо самі.

    Поля `id` і `key` у сторінці — РІЗНІ рядки, і злити їх в одне не можна:
    `id` — шлях у publish (ним ходить глибоке посилання `#p=`), `key` — база
    ключа КАДРУ. У неявної «Головної» вони розходяться назовсім: `id` = `it1`,
    а кадр лежить під `main`. Одне поле на дві ролі означало б «Огляд» без
    кадрів, і причину шукали б у зʼємці.

    `iters` і `frames` накриті ОДНИМ переліком ітерацій — тих, у яких є що
    показати. Правило не нове: дропдаун обгортки відкинув ітерації без сторінок
    саме тому, що інакше він брехав про те, що можна відкрити (`preview_index_html`).

    `iters` — `{'id', 'num', 'note'}`, тобто ІДЕНТИФІКАТОР і ДАНІ, БЕЗ підпису.
    Той самий розділ, що вже двічі лікували 02.09.2026 (`Іт.N` шаблонним
    літералом у `app.js`; підписи вкладок аудиторій, спечені сервером): усе, що
    людина ЧИТАЄ, складає словник у браузері, бо мову вибирає глядач, а не
    збірка. Деталі й межа — у `iteration_note()`.

    `frames` — `{it: {frameKey: {'path': relPath, 'w': …, 'h': …}}}` від
    `publish_frames`; `w`/`h` це розмір ЗНІМКА в пікселях, і його може не бути
    (запис зʼємки не пройшов валідацію — див. `_frame_size`). Оболонці він
    потрібен, щоб знати висоту картки ДО завантаження кадру: без нього «Огляд»
    стоїть заглушкою й сідає під справжні пропорції на очах глядача.

    ⛔ `widths` рахує `split_frame_key`, тобто КЛЮЧІ, і `w` поруч на це не
    впливає. Це не дубль інформації, а дві різні ширини: `w` — скільки пікселів
    у знімку (при подвоєній щільності вдвічі більше), а сегмент ширин пропонує
    глядачу ширини ВЬЮПОРТА, під якими кадри взагалі шукаються. Порахуй його по
    `w` — і в смузі зʼявиться «1536», якого не має ні один ключ: кнопка, що не
    знаходить кадрів.

    ⚠️ Межа, названа вголос: файл лежить статикою, тобто читається БЕЗ гейту.
    Перевірено живою публікацією 11.09.2026: `GET /manifest.json` без пароля
    віддає 200 і в тілі назву задачі, тікет і нотатки всіх ітерацій (там же
    трапляються посилання на Figma-вузли); `GET /itN/<сторінка>/index.html` —
    повний макет. Новим каналом витоку це не є: гейт — оверлей у браузері, а не
    серверний замок, і пароль лежить у тексті `index.html` (`gate_html`), а ключ
    сесії `<tid>_auth` несе id задачі.

    ⛔ Ховати ці поля в ІНШИЙ статичний файл сенсу не має — це той самий
    відкритий GET, лише менш очевидний. Чесних шляхів два: серверний захист
    (Vercel Deployment Protection) або шифрування контексту паролем. Рішення
    власника 14.09.2026: у цьому батчі не ховаємо нічого, а прибираємо ОБІЦЯНКУ
    захисту з інтерфейсу й доків — щоб посилання не відправляли туди, куди не
    можна, вважаючи його закритим.
    """
    with_pages = {p['it'] for p in pages}
    live = [it for it in its if it['id'] in with_pages]
    man = {
        'task': task.get('title', tid),
        # `num` і `note` ОКРЕМО, не спечений підпис: префікс «Іт.N» — це
        # презентація, і мову для неї вибирає ГЛЯДАЧ (`dc-lang` у його
        # браузері), а не Python на машині дизайнера. Спечений тут підпис
        # приїжджав у смугу кирилицею навіть при `dc-lang=en` (заміряно
        # 03.09.2026: «Layout / Overview / Copy link» і поруч «Іт.1 ·
        # фікстура»). Тег складає `iterTag` в оболонці; очищення примітки
        # лишається тут, бо це дані — див. `iteration_note`.
        'iters': [{'id': it['id'], 'num': iter_num(it['id']),
                   'note': iteration_note(it)} for it in live],
        'pages': [{'id': p['out_rel'], 'it': p['it'], 'key': p['page']['id'],
                   'name': p['name'], 'depth': p['depth'],
                   'path': f"{p['out_rel']}/index.html"}
                  for p in pages],
        'frames': {it['id']: frames.get(it['id'], {}) for it in live},
        'widths': sorted({split_frame_key(k)[1]
                          for it in live for k in frames.get(it['id'], {})}),
    }
    outline = []
    for it in live:
        tree = iteration_pages(task, it['id']) if trees is None else trees[it['id']]
        for f in pm.preview_outline(tree):
            node = f['page']
            folder = f['kind'] == 'folder'
            row = {'id': _out_rel(it['id'], node, folder),
                   'it': it['id'], 'key': node['id'], 'name': node['name'],
                   'kind': f['kind'], 'depth': f['depth']}
            if not folder:      # у теки файла немає
                row['path'] = f"{row['id']}/index.html"
            outline.append(row)
    man['outline'] = outline
    man['shell'] = PREVIEW_SHELL_VERSION
    if comments:
        man['comments'] = {'channel': str(comments)}
    if build is not None:
        man['build'] = build
    with open(os.path.join(dst_dir, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(man, fh, ensure_ascii=False, indent=1)
    return man


def _out_rel(it_id, node, folder=False):
    """Шлях вузла в `publish/`: `<it>/<rel>`, а для неявної «Головної» — сам `<it>`.
    У теки каталогу нема, тож її id — `<it>/<id>` у тому ж просторі, і правило
    неявної main (`page_rel` дає '' для id `main`) на неї не поширюється."""
    rel = node['id'] if folder else pm.page_rel(node)
    return f"{it_id}/{rel}" if rel else it_id


def published_pages(task, its, trees=None):
    """Сторінки, які їдуть у превʼю: [{it, rel, out_rel, name, depth, page}].

    ЄДИНЕ місце, де вирішується «що потрапляє в публікацію». Консументи:
    `_publish` (копіює файли й вставляє гейт) і `ops/reseal_gate.py`
    (перезбирає лише обгортку). До 04.08.2026 кожен мав власний обхід із
    власним фільтром — та сама пара «джерело й копія розходяться молча», через
    яку написана вся серія релізів 1.10–1.14.

    Правило видимості — `pm.preview_flat` (приховування на піддерево, рішення
    власника 30.09.2026): схований вузол не везе нікого зі свого піддерева, а
    теки тут узагалі не сторінки — їх відсіює той самий `preview_flat`.
    """
    out = []
    for it in its:
        tree = iteration_pages(task, it['id']) if trees is None else trees[it['id']]
        for f in pm.preview_flat(tree):
            page = f['page']
            rel = pm.page_rel(page)
            out.append({'it': it['id'], 'rel': rel, 'page': page,
                        'out_rel': _out_rel(it['id'], page),
                        'name': page['name'], 'depth': f['depth']})
    return out


def copy_iteration_shared(task, it_id, dst_dir, tree=None):
    """Спільні файли ітерації в publish/<it>/: усе з кореня, крім тек СТОРІНОК.

    ⛔ Без цього кроку багатосторінкова ітерація публікувалась порожньою.
    Цикл у `_publish` копіює лише теки сторінок, а `assets/`, `icons/`, `fonts/`
    лежать у КОРЕНІ ітерації і їхали тільки як побічний ефект сторінки з
    `rel == ''` (неявна `main`). Прибрав кореневу сторінку — і кожна сторінка
    почала тягнути `../assets/<тема>.css` у 404: превʼю відкривалось білим, а
    виглядало як «немає макетів» (LIGA-7010, 31.08.2026).

    Теки сторінок свідомо ВИКЛЮЧЕНІ — і опубліковані, і зняті з превʼю: перші
    везе цикл (з гейтом і комментатором), а другі не мають потрапити в превʼю
    взагалі, інакше «зняти сторінку з публікації» перестало б працювати.
    """
    src_dir = os.path.join(task['dir'], 'iterations', it_id)
    if not os.path.isdir(src_dir):
        return []
    # Тека (kind=folder / isGroup) каталогу на диску НЕ має — її id не імʼя теки,
    # тож у виняток вона не йде: тека «Icons» (id `icons`) інакше відсіяла б
    # справжній спільний `icons/`, і превʼю лишилось би без стилів.
    page_dirs = {pm.page_rel(f['page'])
                 for f in pm.flatten(iteration_pages(task, it_id) if tree is None else tree)
                 if f['kind'] != 'folder'}
    page_dirs.discard('')
    os.makedirs(dst_dir, exist_ok=True)
    carried = []
    for name in sorted(os.listdir(src_dir)):
        # ⛔ `shots/` — сирий склад кадрів, БЕЗ фільтра публікації. Возити його
        # цілком означало б віддати глядачу і кадри сторінок, знятих із превʼю
        # (виміряно на boss-interface 02.09.2026: `publish/it3/shots/` уже лежав
        # у зібраному превʼю й деплоївся). Кадри їдуть окремо й під фільтром
        # сторінок — `publish_frames` → `publish/<it>/_frames/`; фільтр там був
        # би театром, поки поруч лежить повна копія без фільтра.
        # ⛔ pages.json і flow.json — не для превʼю: вони називають і будують
        # структуру СХОВАНИХ вузлів, а читача в оболонці нема (вона живе з
        # manifest.json; ext-shell.js прямо каже, що flow.json не їде).
        s, d = os.path.join(src_dir, name), os.path.join(dst_dir, name)
        # ⛔ HTML-документи КОРЕНЯ — це сторінка `main` (rel ''), а не спільний
        # файл. Їх везе `copy_root_files`, і лише коли `main` опублікована. Тут
        # вони їхали завжди — і знята з превʼю `main` потрапляла в превʼю, ще й
        # БЕЗ гейта: гейт ставить цикл сторінок, а цієї сторінки в ньому нема.
        # Знайдено 07.10.2026 (батч 1.52) звіркою пароля по всіх сторінках:
        # живе превʼю smida-shareholders віддавало `/it2/` без пароля.
        if os.path.isfile(s) and name.lower().endswith(('.html', '.htm')):
            continue
        if (name in page_dirs or name == 'shots' or _is_tool_junk(name)
                or name in ('pages.json', 'flow.json')):
            continue
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('*' + TMP_SUFFIX))
        else:
            shutil.copy2(s, d)
        carried.append(name)
    return carried


def copy_root_files(src_dir, dst_dir):
    """Файли КОРЕНЯ ітерації для сторінки з `rel == ''` (явна `main`) — без тек.

    ⛔ Її src — уся тека ітерації, і `copy_mockup` повіз би в превʼю ВСЕ: теки
    інших (зокрема СХОВАНИХ) сторінок, `shots/`, а з ними й `pages.json` та
    `flow.json` (A4 ревʼю). Спільні теки (assets/icons/fonts) уже привіз
    `copy_iteration_shared`, тож тут лише файли; pages.json і flow.json —
    ті самі виключення, що й там.
    """
    os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        s = os.path.join(src_dir, name)
        if (os.path.isdir(s) or _is_tool_junk(name)
                or name in ('pages.json', 'flow.json')):
            continue
        shutil.copy2(s, os.path.join(dst_dir, name))


def js_literal(value):
    """Значення як JS-літерал усередині `<script>`.

    ⛔ НЕ `_html.escape`: HTML-ентіті в `<script>` не декодуються. Пароль `a'b`
    ставав `a&#x27;b`, тому кнопка «Копіювати посилання» збирала `#k=` з
    екранованого, гейт порівнював із сирим — і безшовний вхід тихо не працював.
    А сирий апостроф у самому гейті — це синтаксична помилка JS, після якої IIFE
    не запускається й оверлей не зникає НІКОЛИ: превʼю не відкрити жодним паролем.

    ⛔ І не голий `json.dumps`: він не чіпає `</`, тому назва сторінки
    `</script><img src=x onerror=…>` (назви пише дизайнер) рвала скрипт, панель
    вмирала, картинка виконувалась — а в тому ж скрипті лежить пароль превʼю.
    Перевірено живцем 04.08.2026. `\\u2028/\\u2029` — бо `ensure_ascii=False`
    віддає їх сирими, а в JS вони розділювачі рядків.
    """
    return (json.dumps(value, ensure_ascii=False)
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
            .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def preview_index_html(gate, pw):
    """HTML обгортки превʼю — ТОНКИЙ КАРКАС. ЄДИНЕ місце збірки: і публікація,
    і `ops/reseal_gate.py` кличуть саме її.

    ⛔ Ні назви задачі, ні переліку ітерацій, ні переліку сторінок ця функція
    БІЛЬШЕ НЕ ПРИЙМАЄ, і вузька сигнатура тут — запобіжник, не косметика.
    Стан оболонки живе в `publish/manifest.json`, який пише ЛИШЕ `_publish`, а
    `ops/reseal_gate.py` перезбирає тільки `index.html` і кадрів не рахує
    взагалі: інлайнений стан означав би, що після кожного перепечатування
    гейту обгортка везе НОВИЙ скрипт і СТАРІ дані — тихо, без жодної ознаки.
    Тепер їй просто нізвідки їх узяти.

    Заодно зникає цілий клас багів, а не один випадок: до 02.09.2026 назви
    сторінок їхали в обгортку JS-літералом, і назва `</script><img src=x
    onerror=…>` рвала скрипт, у якому лежить пароль превʼю (перевірено живцем
    04.08.2026). Через `<script>` вони більше не проходять — назви лежать у
    JSON-файлі, а екранує їх `esc()` у `shell-panel.js`/`ext-bar.js`.

    Ітерації без опублікованих сторінок відсіює тепер `publish_manifest` — там
    же, де складається сам перелік (правило те саме: дропдаун не сміє
    пропонувати те, що не відкривається).
    """
    return PAGES_PREVIEW_PAGE.format(gate=gate, pw_js=js_literal(str(pw)))


def _loaded_app_sources():
    """Python-файли з `app/`, ЗАВАНТАЖЕНІ в цей процес.

    Перелік беремо з sys.modules, а не хардкодимо: обгортку збирає serve.py
    разом із pages_model (розкрій сторінок) і atomic_io, і будь-який новий сусід
    потрапить сюди сам. Захардкоджений список мовчки застарів би — рівно та
    порода розходження «джерело / те, що поїхало», проти якої це й ставиться.
    """
    out = set()
    for mod in list(sys.modules.values()):
        path = getattr(mod, '__file__', None)
        if not path:
            continue
        path = os.path.abspath(path)
        if path.startswith(APP_DIR + os.sep) and path.endswith('.py'):
            out.add(path)
    return sorted(out)


def server_code_staleness(started_at=None):
    """Текст попередження, якщо код на диску новіший за процес; інакше None.

    ⛔ Публікацію НЕ блокує: дизайнер має право свідомо публікувати зі старого
    коду. Це попередження — але голосне, бо інакше на Vercel мовчки лишається
    обгортка, зібрана процесом, а джерело на диску вже інше.
    ⛔ І «не знаю» теж голосне: не прочитався mtime — кажемо про це, а не
    вдаємо, що все свіже.
    """
    started_at = SERVER_STARTED_AT if started_at is None else started_at
    newer, unknown = [], []
    for path in _loaded_app_sources():
        try:
            mtime = os.path.getmtime(path)
        except OSError as e:
            unknown.append(f'{os.path.basename(path)} ({e.strerror or e})')
            continue
        if mtime > started_at:
            newer.append(os.path.basename(path))
    parts = []
    if newer:
        # ⛔ Текст відповідає на ТРИ питання, а не лише «щось старе»
        # (fb-22092026-3a9764): ЩО саме зібрано старим кодом, чи ВАЛІДНЕ
        # опубліковане, і чи треба перевидавати. До цього дизайнер бачив лише
        # «працює зі старішим кодом» і не знав, чи зіпсовано те, що вже в
        # менеджера. Сторінки макета копіюються з диска в момент публікації —
        # вони завжди свіжі; зі старого коду в памʼяті процесу — лише обгортка.
        built = 'обгортку превʼю (оболонка, маніфест, гейт'
        if 'pages_model.py' in newer:
            built += ', розкрій сторінок'
        built += ')'
        parts.append(
            '⚠ Канвас працює зі СТАРІШИМ кодом, ніж на диску: після старту '
            'сервера змінено ' + ', '.join(sorted(newer)) + '.\n'
            '· Сторінки макета взято з диска — вони актуальні.\n'
            f'· Зі старого коду зібрано лише {built}: опубліковане працює, це '
            'обгортка у версії до правки.\n'
            '· Перевидавати треба, лише якщо правка в цих файлах стосується '
            'самого превʼю: після перезапуску канваса (./stop.command → '
            './start.command) опублікуй ще раз — адреса лишиться та сама.')
    if unknown:
        parts.append(
            '⚠ Час зміни не прочитався: ' + ', '.join(sorted(unknown)) +
            ' — чи працює канвас з актуальним кодом, невідомо.')
    return '\n\n'.join(parts) or None


def _preview_domain_warning(url, proj):
    """Попередження, якщо Vercel видав НЕ `<проєкт>.vercel.app`, або None.

    fb-29092026-210ec1: короткий хост зайняв проєкт із тим самим імʼям в ІНШОМУ
    акаунті — цей отримав `pv-XXXX-<суфікс>.vercel.app`. Дизайнери не помічали,
    що в них РІЗНІ посилання, а кожна публікація заміняє деплой цілком.
    """
    host = re.sub(r'^https?://', '', url or '').split('/')[0]
    want = f'{proj}.vercel.app'
    if not proj or not host or host == want:
        return None
    return (f'Vercel видав {host}, а не {want}: проєкт із цим імʼям уже є в ІНШОМУ '
            f'акаунті, тож у тебе й у колеги РІЗНІ посилання, і публікація не бачить '
            f'ітерацій колеги. Звір прив\'язку задачі (vercel_scope у tasks.json).')


DEFAULT_PREVIEW_PW = '1100'
#: Відмова публікації/зміни пароля, коли файл секретів простору є, але не читається (`ModuleError('secrets-unreadable')`).
SECRETS_UNREADABLE_TEXT = 'секрети простору не читаються — пароль превʼю невідомий, дію зупинено'


def preview_password(task, space=None):
    """Пароль превʼю задачі: `preview_password` ЗАДАЧІ, далі секрет `password` запису `vercel-publish` ЛІГИ (`space`;
    `deai_modules.publish_password`), інакше спільний 1100. Кореня `tasks.json` більше не читаємо (4d-4b: крок `liga-4d4b` переніс його
    значення в секрет). ⛔ Файл секретів є, але не читається — `ModuleError('secrets-unreadable')` летить ДО виклику (fail-closed:
    мовчки віддати `1100` означало б відкрите превʼю замість закритого); споживачі відмовляють із ясним текстом.

    До 03.08.2026 пароль був захардкожений один на ВСІ задачі й усіх людей: одна
    злита ссилка відкривала будь-яке превʼю. Тепер його можна задати на задачу й
    ротувати. Поле per-machine (tasks.json поза git), тому в спільний репо не їде.

    ⚠️ Це гейт у DOM, а не автентифікація: пароль лежить у джерелі сторінки, тому
    хто має URL — може прочитати HTML. Сенс поля — обмежити радіус зливу однією
    задачею, а не зробити превʼю приватним. Справжня приватність = захист на
    рівні Vercel (Deployment Protection), і вона ламає цей гейт.
    """
    return str((task or {}).get('preview_password')
               or deai_modules.publish_password(space) or DEFAULT_PREVIEW_PW)


PREVIEW_PW_MAX = 64
_GATE_STATE_CACHE = {}


def check_preview_password(value):
    """Пароль із інтерфейсу: рядок без керуючих символів, до PREVIEW_PW_MAX.
    Порожній (після strip) — «повернути типовий». Повертає (пароль|None, помилка)."""
    if not isinstance(value, str):
        return None, 'password must be a string'
    value = value.strip()
    if not value:
        return '', None
    if len(value) > PREVIEW_PW_MAX:
        return None, f'password is longer than {PREVIEW_PW_MAX}'
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return None, 'password has control characters'
    return value, None


def _publish_pages(pub):
    """Усі сторінки зібраного превʼю, що мусять нести гейт: обгортка й кожна
    внутрішня сторінка. Службові теки (бандли, оболонка, кадри) — без гейта."""
    out = []
    for dirpath, dirnames, files in os.walk(pub):
        rel = os.path.relpath(dirpath, pub)
        if rel.split(os.sep)[0] in ('comment-layer', 'shell', '.vercel') or \
                '_frames' in rel.split(os.sep):
            dirnames[:] = []
            continue
        if 'index.html' in files:
            out.append(os.path.join(dirpath, 'index.html'))
    return out


def preview_gate_state(task, pw):
    """Чи ЗІБРАНЕ превʼю (`publish/`) уже з паролем `pw` — на КОЖНІЙ сторінці.

    ⛔ Дивимось не лише обгортку: `ops/reseal_gate.py` перепечатує ЛИШЕ її, а
    гейт стоїть і в кожній внутрішній сторінці. Обгортка з новим паролем при
    старому в сторінках — це «пароль змінено» на словах, а пряме посилання на
    сторінку відкривається старим. Тому `stale` — кількість сторінок БЕЗ
    поточного пароля, включно з обгорткою.

    Повертає {'state': 'none'|'current'|'stale'|'ungated', 'stale': n,
    'ungated': n, 'inner_stale': n, 'pages': n}. `stale` — сторінки З гейтом, але
    з ІНШИМ паролем (вони й роблять посилання з новим ключем непрацюючим);
    `ungated` — сторінки БЕЗ гейта зовсім (зібрані до фікса TD-37): це не
    «пароль змінено», і плутати їх у підписі — збрехати про причину (ревʼю 1.52).
    `inner_stale` — stale без обгортки: `reseal_gate.py` питає саме його ДО того,
    як перепише обгортку.
    Кеш — за паролем і mtime обгортки: публікація й reseal обидва її пишуть.
    """
    pub = os.path.join(task['dir'], 'publish')
    wrapper = os.path.join(pub, 'index.html')
    try:
        mt = os.stat(wrapper).st_mtime_ns
    except OSError:
        return {'state': 'none', 'stale': 0, 'ungated': 0, 'inner_stale': 0, 'pages': 0}
    key = (pub, pw, mt)
    hit = _GATE_STATE_CACHE.get(pub)
    if hit and hit[0] == key:
        return dict(hit[1])
    want = f'P={js_literal(str(pw))};'
    pages = _publish_pages(pub)
    stale = ungated = inner_stale = 0
    for f in pages:
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
        except OSError:
            text = ''
        if want in text:
            continue
        if 'id="authgate"' in text:
            stale += 1
            if f != wrapper:
                inner_stale += 1
        else:
            ungated += 1
    state = 'stale' if stale else ('ungated' if ungated else 'current')
    res = {'state': state, 'stale': stale, 'ungated': ungated,
           'inner_stale': inner_stale, 'pages': len(pages)}
    _GATE_STATE_CACHE[pub] = (key, res)
    return dict(res)


def gate_html(tid, pw):
    """Гейт для сторінки превʼю. Ключ sessionStorage — на задачу, тому пройдений
    гейт обгортки автоматично відкриває і внутрішні сторінки (той самий origin).

    Пароль і ключ ідуть як JS-літерали (`js_literal`), а не в лапках у шаблоні:
    апостроф у паролі робив із гейта синтаксично невалідний JS, і оверлей уже не
    прибирався НІЯКИМ паролем. Пароль задається руками в tasks.json, тому це
    питання часу, а не гіпотеза."""
    return GATE_SNIPPET.format(key_js=js_literal(f'{tid}_auth'),
                               pw_js=js_literal(str(pw)), logo=_gate_logo_svg())


#: Гейт-заглушка превʼю БЕЗ пароля: обгортка не чекає розблокування, бо розблоковувати нічого. Той самий
#: хук, який ставить справжній гейт в `unlock()` (`window.__gateOpen`): `app/ext-shell.js` відкриває
#: оболонку лише по ньому (`if (window.__gateOpen) open()`), тож без нього превʼю стояло б порожнім.
NO_GATE_OPEN = '<script>window.__gateOpen=true;</script>'


#: Файли адаптера модуля коментарів, прочитані для збірки: `module` — `Module`, `config`/`channel` — з рішення
#: `publish_comments`, `files` — `[(імʼя, байти)]` у порядку маніфесту.
ModuleCommentsBuild = collections.namedtuple('ModuleCommentsBuild', 'module config channel files')


def _read_module_comments(comments):
    """Перевірка словника `comments` модуля й ПРОЧИТАНІ файли його адаптера → `ModuleCommentsBuild`.

    Форма — рівно `{'module', 'config', 'channel'}`: `Module` зі `status == 'ok'` і роллю `comments`, `config` —
    обʼєкт, `channel` — непорожній рядок (інакше `ValueError`: помилка викликача, а не відмова модуля). Кожен файл із
    `client` відкривається `open_module_client` — тим самим захистом, що роздача `/api/module-client/…` (звичайний
    файл, ні симлінк, ні жорстке посилання, дескриптор) — і читається цілком (≤ `MAX_CLIENT_BYTES`: файл міг
    вирости після завантаження каталогу). Відмова — `ModuleError('module-error')` БЕЗ тексту файла; імʼя файла
    (`CLIENT_RE`) і id модуля (`ID_RE`) безпечні для тексту. Імʼя файла, що збігається з бандлом ядра (`BUNDLES`),
    теж відмова: файл модуля затер б шар коментатора чи прикинувся бандлом ЛІГА.
    ⚠️ Викликається ДО `rmtree(publish/)`: відмова не стирає попередню збірку."""
    mod, config, channel = comments.get('module'), comments.get('config'), comments.get('channel')
    if (set(comments) != {'module', 'config', 'channel'} or not isinstance(mod, deai_modules.Module)
            or mod.status != 'ok' or 'comments' not in mod.roles or not isinstance(config, dict)
            or not isinstance(channel, str) or not channel):
        raise ValueError("build_preview: comments — словник {'module': Module ролі comments, 'config': {…}, "
                         "'channel': '…'}")
    files = []
    core = {b.lower() for b in BUNDLES}
    for name in mod.client:
        if name.lower() in core:           # без урахування регістру: на macOS/Windows `Comment-Layer.min.js` — той самий файл
            raise deai_modules.ModuleError(
                'module-error', message=f'adapter file {name} of module {mod.id} has the name of a core '
                                        'comment-layer file')
        opened = open_module_client(mod, name)
        if opened is None:
            raise deai_modules.ModuleError(
                'module-error', message=f'adapter file {name} of module {mod.id} cannot be opened safely '
                                        '(a plain regular file is required)')
        fd, _st = opened
        try:
            fh = os.fdopen(fd, 'rb')
        except Exception:                                  # noqa: BLE001 — дескриптор не лишається висіти
            os.close(fd)
            raise
        with fh:
            data = fh.read(deai_modules.MAX_CLIENT_BYTES + 1)
        if len(data) > deai_modules.MAX_CLIENT_BYTES:
            raise deai_modules.ModuleError(
                'module-error', message=f'adapter file {name} of module {mod.id} is bigger than '
                                        f'{deai_modules.MAX_CLIENT_BYTES} bytes')
        files.append((name, data))
    return ModuleCommentsBuild(mod, config, channel, files)


def publish_comments(space, task, tid, *, module_publish=False):
    """`(comments, warning)` — рішення про коментарі превʼю для `build_preview(comments=…)`, ОДИН раз на публікацію.

    Рішення — з ПОСТАЧАЛЬНИКА ролі `comments` ПРОСТОРУ публікації (`deai_modules.provider('comments', space)` через
    `comments_provider`, простір — явним аргументом), а НЕ з прапорця простору: «ЛІГА ввімкнено» ≠ «коментарі
    — спільний Supabase» (простір ЛІГА може вести коментарі власним модулем, а простір без інтеграцій — теж). `space`
    — запис простору, який викликач ВЖЕ вирішив (одне читання реєстру на публікацію); `None` — шар вимкнено чи простір
    запиту не зафіксовано (інструменти ЛІГА): `comments_provider` тоді віддає `None` БЕЗ читання реєстру. `task` —
    задача публікації: від неї канал ЛІГИ (`comment_project` чи `dc/<задача>`, `comments_route`).

        постачальник        шлях ЛІГИ (`_publish`)                 модуль публікації (`module_publish=True`)
        Module              словник модуля                         словник модуля
        Module+shared_state словник модуля                         False (4d-3b; лишається — стереже збірки модуля від ключа ЛІГИ)
        None               False                                  False
        ModuleError         False + код відмови                    False + код відмови

    ⛔ `Module` із `shared_state` (ЛІГА) у збірці МОДУЛЯ публікації — `False`: Supabase ЛІГА (адреса й ключ спільного проєкту, куди піни
    несуть знімки макетів) не їде в превʼю, яке зібрав модуль, — це був би новий вихід даних, якого людина не вмикала (інакше
    увімкнений модуль публікації ніс би ключ у превʼю, 4d-3b). Шлях `_publish` (`module_publish=False`) не змінюється.
    ⛔ Відмова (`ModuleError`: явно ввімкнений модуль коментарів загубився, `space.json` не прочитати, `client_config`,
    канал чи конфіг установки ЛІГИ — `comments-unconfigured` — не вдались) — ЗАВЖДИ `False` + `warning` (код, без тексту й
    значень): сама публікація йде далі, а відповідь несе `comments_unavailable`. Модуль коментарів виконує свій код
    (`client_config`): НЕ кликати під `spaces.WRITE_LOCK`."""
    prov, err = comments_provider(space)
    if err is not None:
        return False, err.code
    if prov is None or (_shared_module(space, prov) and module_publish):
        return False, None
    if not isinstance(prov, deai_modules.Module):
        return False, None                 # значення, що не є постачальником, — «нікого», як і було
    try:
        mod, ctx, route_channel = comments_route(space, prov)
        channel = route_channel(task, tid)                 # ⛔ канал — ДО коду модуля: непридатний id задачі не доходить до `client_config`
        config = deai_modules.comments_client(space, mod, ctx)
        return {'module': mod, 'config': config, 'channel': channel}, None
    except deai_modules.ModuleError as e:
        return False, e.code


def build_preview(task, tid, its, *, comments, gate_pw, build, space=None, tokens=None):
    """Зібрати `publish/` з ОПУБЛІКОВАНИХ ітерацій `its`: сторінки, спільні файли ітерацій, оболонка,
    кадри, маніфест, обгортка. ЄДИНА збірка превʼю: нею користуються і ЛІГА (`Handler._publish`, далі
    vercel deploy), і модулі публікації (статика в локальну теку) — друга копія збірки розійшлась би з
    першою мовчки.

    `comments` — рішення про коментарі превʼю, яке приймає ВИКЛИКАЧ (`publish_comments`: з постачальника ролі
    `comments`, один раз на публікацію), а збірка лише виконує його:
      * `False` — без коментатора: ні `publish/comment-layer/`, ні ін'єкції в сторінки. Потрібно там, де Supabase
        недосяжний або недоречний;
      * `{'module': <Module ролі comments>, 'config': {…}, 'channel': '…'}` — канал МОДУЛЯ (з 4b-2 — і ЛІГИ: вбудований
        `supabase-comments`): у `publish/comment-layer/`
        лягають `comment-layer.min.js` (ядро) і ЛИШЕ оголошені в `client` файли адаптера (ні старий `supabase-adapter`, ні CDN),
        а в сторінки — сніпет модуля з ВІДНОСНИМИ шляхами (`../` за глибиною сторінки) і `{**config, channel}`. `config` —
        уже перевірена публічна конфігурація (`deai_modules.comments_client`: непублічних секретів у ній нема),
        `channel` — канал ядра (`deai_modules.channel_for`). Без інспектора й вкладок аудиторій: це публікація.
        Файли адаптера читаються ДО `rmtree` через `open_module_client` (без симлінків і жорстких посилань,
        ≤ `MAX_CLIENT_BYTES`): небезпечний файл — `ModuleError('module-error')`, а попередню збірку не стирають.
    Будь-що інше — `ValueError` ДО змін на диску: `True` (з 4b-2 шляху «зашитий Supabase» нема), `'legacy'` (значення
    постачальника, а не рішення) чи `1` не мають мовчки стати шляхом ЛІГА.

    `build` — ХТО збирає, ОБОВʼЯЗКОВИЙ іменований аргумент (як `gate_pw`): `'legacy'` — `Handler._publish` (ЛІГА: далі
    деплой на Vercel), `'module'` — модулі публікації (`publish_with_module`, `_publish_by_url`). Пишеться в
    `manifest.json` (`"build"`) ПОЗИТИВНОЮ міткою: `ops/reseal_gate.py` перепечатує й деплоїть лише збірки `legacy`.
    Склад `publish/comment-layer/` для цього рішення не годиться: збірка ЛІГА з коментарями модуля несе там лише шар
    і файли адаптера, а ЛІГА без коментарів (`comments_unavailable`) — нічого, і обидві не відрізнити від локальної
    збірки модуля. Інше значення — `ValueError` ДО змін на диску.

    `space` і `tokens` (0.32.0) — для ІНСПЕКТОРА превʼю: `space` — запис простору публікації (напрямок задачі `task_ds(task,
    space)` → `?ds=` у тезі оверлея), `tokens` — знімок токенів простору (`preview_tokens_snapshot(space)`), який викликач
    бере РАНІШЕ за замки публікації (модуль виконує свій код). `tokens` → файл `shell/ds-snapshot.json` і `&sp=…&tok=…` у тезі;
    `None` — файла нема, оверлей без чипів. Оверлей їде в КОЖНУ сторінку превʼю (`SHELL_VENDOR`), з відносним шляхом.

    `gate_pw` — пароль гейта, ОБОВʼЯЗКОВИЙ іменований аргумент (забути його не вдасться). `None` — превʼю
    БЕЗ гейта: сторінки не чіпаємо взагалі (`_inject_gate` ще й переписує `<title>`), а обгортка
    відкривається сама (`NO_GATE_OPEN`), із порожнім паролем для «Копіювати посилання». ⚠️ `''` — це НЕ
    «без гейта», а гейт, що відчиняється порожнім полем; «без гейта» лише `None`. Гейт-хелпери кличемо
    лише коли він є: без пароля `gate_html` не має що вшивати, а `str(None)` дав би пароль «None».

    ⛔ Хелпери (`gate_html`, `_inject_gate`, `preview_index_html`, `inject_module_comment_layer`, `BUNDLES`…)
    беремо з модуля ПРИ ВИКЛИКУ, а не захоплюємо аргументами за замовчуванням: так `serve.<хелпер>`
    лишається підмінюваним для майбутніх тестів і модулів (захоплене значення тихо обійшло б підміну).

    `its` — вже відфільтровані ОПУБЛІКОВАНІ ітерації, і порожній перелік — це `ValueError` ДО будь-якої
    зміни на диску: інакше збірка затерла б `publish/` і записала порожній маніфест. Решта «немає
    ітерацій» (400 для дизайнера), `code_stale` і деплой лишаються викликачу.
    → `{'dir', 'iterations', 'frames'[, 'frames_warnings']}`; `ok` і `code_stale` додає викликач.
    """
    if not its:
        raise ValueError('build_preview: порожній перелік ітерацій — нема що збирати')
    if build not in BUILD_KINDS:
        raise ValueError(f'build_preview: build — одне з {BUILD_KINDS}, а не {build!r}')
    adapter = None
    if isinstance(comments, dict):
        adapter = _read_module_comments(comments)        # перевірка й читання файлів адаптера — ДО будь-якої зміни диска
    elif comments is not False:
        raise ValueError(f'build_preview: comments — False чи словник модуля, а не {comments!r}')
    pub = os.path.join(task['dir'], 'publish')
    if os.path.isdir(pub):
        shutil.rmtree(pub)
    os.makedirs(pub)
    if adapter is not None:
        # шар коментатора й файли адаптера модуля — один раз
        vend = os.path.join(pub, 'comment-layer')
        os.makedirs(vend)
        shutil.copy2(os.path.join(ROOT, 'app', 'vendor', LAYER_BUNDLE), os.path.join(vend, LAYER_BUNDLE))
        for name, data in adapter.files:
            with open(os.path.join(vend, name), 'wb') as fh:
                fh.write(data)
    # Спільні модулі зовнішньої оболонки — статика, від сторінок не залежать,
    # тому їдуть тут же, одразу після `rmtree` (порядок важливий: усе нове
    # везеться ПІСЛЯ затирання publish/).
    shell = os.path.join(pub, 'shell')
    os.makedirs(shell)
    for m in SHELL_MODULES:
        shutil.copy2(os.path.join(ROOT, 'app', m), os.path.join(shell, m))
    # Оверлей інспектора й його залежності (0.32.0): `shell/vendor/`, байт у байт. Знімок токенів — поруч із оболонкою, куди
    # ведуть `../i18n.js`/`../esc.js` оверлея: `shell/ds-snapshot.json` (тег несе його як `tok=../ds-snapshot.json`).
    os.makedirs(os.path.join(shell, 'vendor'))
    for m in SHELL_VENDOR:
        shutil.copy2(os.path.join(ROOT, 'app', 'vendor', m), os.path.join(shell, 'vendor', m))
    snapshot = tokens if (tokens and tokens.get('tokens')) else None
    if snapshot:
        with open(os.path.join(shell, PREVIEW_TOKENS_FILE), 'w', encoding='utf-8') as fh:
            json.dump(snapshot, fh, ensure_ascii=False)
    ds_task = task_ds(task, space)
    gated = gate_pw is not None       # ЄДИНЕ рішення «з гейтом чи без»: далі — лише `gated`
    gate = gate_html(tid, gate_pw) if gated else None
    # ОДИН знімок дерев на всю збірку: сторінки, спільні файли й `outline`
    # маніфесту рахуються з нього, а не з окремих читань pages.json.
    trees = {it['id']: iteration_pages(task, it['id']) for it in its}
    pages = published_pages(task, its, trees)
    # Спільні файли ітерації (assets/icons/fonts) — до циклу сторінок:
    # сторінки посилаються на них через `../`, а цикл везе лише свої теки.
    for it in its:
        copy_iteration_shared(task, it['id'], os.path.join(pub, it['id']), trees[it['id']])
    for p in pages:
        src = os.path.join(task['dir'], 'iterations', p['it'], p['rel'])
        dst = os.path.join(pub, p['out_rel'])
        if p['rel']:
            copy_mockup(src, dst)
        else:
            copy_root_files(src, dst)
        page_file = os.path.join(dst, 'index.html')
        with open(page_file, encoding='utf-8') as fh:
            html = fh.read()
        depth_up = '../' * (p['out_rel'].count('/') + 1)
        insp_tag = preview_inspector_tag(depth_up, ds_task, snapshot)
        if adapter is not None:
            html = inject_module_comment_layer(
                html, f'{depth_up}comment-layer',
                [f'{depth_up}comment-layer/{name}' for name, _data in adapter.files],
                {**adapter.config, 'channel': adapter.channel},
                version=pm.page_version_tag(p['it'], p['page']), inspector=False, audiences=False,
                host='preview', inspector_tag=insp_tag)
        else:
            html = _insert_before_body(html, insp_tag)      # без коментарів — лише оверлей, після всього, що було
        if gated:
            # ⛔ Гейт і на ВНУТРІШНІЙ сторінці, не лише в обгортці. До 03.08.2026
            # пряме посилання на неї минало пароль: перевірено живцем —
            # <превʼю>.vercel.app/ пароль просив, а /it4/ віддавав макет.
            html = _inject_gate(html, gate)
        with open(page_file, 'w', encoding='utf-8') as fh:
            fh.write(html)
    # Кадри — ПІСЛЯ сторінок і з тим самим `pages`: фільтр публікації
    # рахується один раз і однаково для обох.
    frames, frame_warnings = {}, []
    for it in its:
        fr, warn = publish_frames(task, it['id'], pages,
                                  os.path.join(pub, it['id'], '_frames'))
        frames[it['id']] = fr
        if warn:
            frame_warnings.append(warn)
    publish_manifest(task, tid, its, pages, frames, pub, trees, build=build,
                     comments=adapter.channel if adapter is not None else None)
    if gated:
        wrapper = preview_index_html(gate, gate_pw)
    else:
        wrapper = preview_index_html(NO_GATE_OPEN, '')
    with open(os.path.join(pub, 'index.html'), 'w', encoding='utf-8') as fh:
        fh.write(wrapper)
    result = {'dir': pub, 'iterations': len(its),
              'frames': sum(len(f) for f in frames.values())}
    # ⛔ Публікація не сміє мовчати про те, що кадри не поїхали: далі йде
    # деплой і посилання менеджеру, а порожній «Огляд» виглядає як «дизайнер
    # нічого не зняв».
    if frame_warnings:
        result['frames_warnings'] = frame_warnings
    return result


# ---------------------------------------------------------------------------------------------------
# Диспетчер ролі `publish` (етап 2а, Task 4b). `Handler._publish` питає `deai_modules.provider('publish')`:
#   `Module` із `compat: design-canvas` — шлях ЛІГА (збірка з коментатором + vercel deploy), відповіді незмінні (`publish_legacy_path`);
#   `None`     — 409 `no-publish-module`;
#   `Module`   — `publish_with_module` нижче: збірка в локальну теку модуля, без жодного виходу назовні (ні Vercel,
#                ні дашборд команди, ні реєстр, ні git-пуш, ні мережа); модуль `publish_target: url` (2b-1) —
#                `_publish_by_url`: без теки, результат — адреса й `state` (ходить лише сам модуль; з ядра так само
#                нічого назовні).
# Коментарі превʼю (2b-2) НЕ залежать від того, хто публікує: на КОЖНОМУ шляху їх вирішує `publish_comments` — з
# постачальника ролі `comments` простору публікації, один раз, ДО збірки. Supabase ЛІГИ із запису `supabase-comments` їде лише у
# збірку самої ЛІГА; модуль коментарів (будь-який) — у всі три шляхи; відмова — без коментарів і `comments_unavailable`.
# ⛔ Усі помічники — МОДУЛЬНІ функції, а не методи `Handler`: зовнішні заглушки обробника
# (`boss_autopublish.py`) мають лише `_current_task/send_error/_send_json/_overview_sync`, і новий метод
# їх зламав би. Обробник `h` сюди передається, але з нього береться лише те, що `_publish` кликав завжди.

#: Правило id задачі для ТЕКИ ПУБЛІКАЦІЇ — ДЗЕРКАЛО `static-publish` (`ID_RE`, `MAX_ID`, `_RESERVED`): `NAME_RE`
#: сервера пускає Unicode, а модуль відмовляє такий id вже ПІСЛЯ збірки (502 `module-error`: `rmtree` + повна
#: збірка задарма), тож диспетчер відмовляє раніше, а роздача `/published/…` пускає лише ті id, що можна
#: опублікувати. Змінюючи правило модуля, міняй і це — паритет стереже `TaskIdParity` (корпус проти обох).
_PUBLISH_ID_RE = re.compile(r'[A-Za-z0-9_-]{1,128}', re.ASCII)
_PUBLISH_ID_RESERVED = re.compile(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]', re.ASCII | re.IGNORECASE)


def publish_id_ok(tid):
    """Чи годиться `tid` як імʼя теки публікації: латиниця, цифри, `_`, `-`, 1..128 символів, не імʼя пристрою
    Windows. Тотальна: не-рядок — `False`. `fullmatch`, а не `$`: «a\\n» не проходить."""
    return (isinstance(tid, str) and _PUBLISH_ID_RE.fullmatch(tid) is not None
            and _PUBLISH_ID_RESERVED.fullmatch(tid) is None)


def no_publish_module_body():
    """Тіло 409, коли в просторі нема КОМУ публікувати: простір без інтеграцій, де `static-publish` явно
    вимкнено (а ЛІГА там нема за побудовою)."""
    return {'ok': False, 'code': 'no-publish-module',
            'error': 'у просторі немає модуля публікації — увімкніть його в налаштуваннях простору'}


#: Замки публікацій модулем: `{ключ призначення: Lock}`. Ключ — `_publish_key`. Словник росте лише парами
#: (тека, задача), яких на машині небагато, тож чистити його нема потреби.
_PUBLISH_LOCKS = {}
_PUBLISH_LOCKS_GUARD = threading.Lock()


def _fold(text):
    """Регістр і юнікодна форма знімаються так, як їх не розрізняє файлова система macOS: NFC до `casefold` і
    після нього (`й` = U+0439 чи `и`+U+0306; `folder_ok` нормалізує так само)."""
    return unicodedata.normalize('NFC', unicodedata.normalize('NFC', text).casefold())


def _publish_key(folder, tid):
    """Ключ замка публікації — ПРИЗНАЧЕННЯ `<тека>/<задача>`, а не пара (простір, задача). Правило `folder_ok`
    пускає ту саму теку для двох просторів (і тека одного — типова тека іншого), тож задачі `t1` двох просторів
    діляться одним `<тека>/t1`: замок на (простір, задача) не виключав би їх одну від одної. `realpath` — бо
    посилання на теку й сама тека суть одне призначення; регістр знімаємо в обох частинах (`casefold`), а
    перед ним і після нього — NFC: файлова система macOS не розрізняє `Foo`/`foo` та NFC/NFD-написання
    (див. `_fold`), а зайва серіалізація шкоди не робить (замок лише відмовляє другому, див.
    `publish_with_module`)."""
    return (_fold(os.path.realpath(folder)), _fold(tid))


def _task_dir_key(task_dir):
    """Ключ замка ТЕКИ ЗБІРКИ задачі. `build_preview` завжди пише `<тека задачі>/publish/`, хоч би в яке
    призначення йшла публікація: замок призначення (`_publish_key`) не виключає двох публікацій тієї самої
    задачі в РІЗНІ теки (налаштування `folder` змінили між двома кліками), а вони стерли б і писали б одну
    `publish/` разом. Одноелементний кортеж — не збігається з ключем призначення (пара) в спільному словнику."""
    return (_fold(os.path.realpath(task_dir)),)


def _publish_lock(key):
    with _PUBLISH_LOCKS_GUARD:
        lock = _PUBLISH_LOCKS.get(key)
        if lock is None:
            lock = _PUBLISH_LOCKS[key] = threading.Lock()
        return lock


@contextlib.contextmanager
def _try_publish_locks(task_dir, folder, tid):
    """Обидва замки публікації БЕЗ очікування, у ФІКСОВАНОМУ порядку: СПОЧАТКУ тека збірки задачі
    (`_task_dir_key`), ПОТІМ призначення (`_publish_key`). Дає `True` — обидва взято; `False` — котрийсь
    зайнятий (те, що вже взято, одразу відпускається: інакше зайняте призначення лишило б задачу «зайнятою»
    назавжди). Усе, що взято, відпускається в ОДНОМУ `finally` — на будь-якому виході з блоку `with`.
    Порядок без очікування взаємного блокування не дає, але він фіксований: зворотний відпуск (`reversed`) і
    читання коду не мають залежати від того, котрий замок упіймано першим."""
    taken = []
    try:
        for key in (_task_dir_key(task_dir), _publish_key(folder, tid)):
            lock = _publish_lock(key)
            if not lock.acquire(blocking=False):
                yield False
                return
            taken.append(lock)
        yield True
    finally:
        for lock in reversed(taken):
            lock.release()


@contextlib.contextmanager
def _try_task_dir_lock(task_dir):
    """Замок ЛИШЕ теки збірки задачі (`_task_dir_key`), БЕЗ очікування: `True` — взято, `False` — зайнятий.
    Для модулів «публікація за адресою» (`publish_target: url`): призначення в них немає, тож `_publish_key` нема.
    Той самий ключ, що в `_try_publish_locks`, а не окремий: збірка `<задача>/publish/` одна для обох гілок, тож
    `folder`-публікація тієї ж задачі теж чекає (відмовляє `publish-busy`)."""
    lock = _publish_lock(_task_dir_key(task_dir))
    if not lock.acquire(blocking=False):
        yield False
        return
    try:
        yield True
    finally:
        lock.release()


def publish_with_module(h, prov, payload):
    """Гілка `Handler._publish` для простору, де публікує МОДУЛЬ `prov` (`Module` із роллю `publish`).

    ⚠️ Нижче — гілка `folder` (модуль пише в локальну теку). Модуль із `publish_target: url` (результат — адреса на
    віддаленому хості) після перевірки «жодної ітерації не позначено» йде в `_publish_by_url`: без теки, без
    `bad-task-id`, із замком лише теки збірки; див. її докстрінг.

    Порядок — і він спостережуваний: (1) «жодної ітерації не позначено» — 400 з тим самим текстом, що в ЛІГА, ДО
    збірки; (2) id задачі, який модуль відмовив би, — 400 `bad-task-id` ДО збірки; (3) `ctx` модуля — ОДИН раз, і
    тека береться З НЬОГО (`ctx['settings']['folder']`): налаштування, змінене між перевіркою й записом, не
    розводить перевірену теку, ключ замка й теку, куди модуль справді пише; (4) тека проходить `folder_ok` —
    інакше 409 `bad-folder` ДО збірки (модуль перевіряє її ще раз сам, але `publish/` до того вже було б
    зібрано: `rmtree` + повна збірка задарма); (5) пароль — секрет модуля `password` (порожній рядок = «пароля
    нема» → `None`: `''` у `build_preview` — гейт, що відчиняється порожнім полем); (6) коментарі превʼю —
    `publish_comments` (постачальник ролі `comments` цього простору: модуль → його канал у збірці; Supabase ЛІГИ
    (`supabase-comments` з конфігом установки) сюди НЕ їде; відмова → без коментарів + `comments_unavailable` у відповіді), потім збірка; (7) `build_only` —
    відповідь про збірку; інакше `publish` модуля й `publish_local` в `iterations.json`, коли модуль повернув саме
    `<тека>/<задача>`.

    Збірка й `publish` модуля йдуть ПІД ДВОМА замками (`_try_publish_locks`): (а) тека збірки задачі
    (`_task_dir_key`) — збірка стирає й пише `<задача>/publish/` незалежно від призначення, а налаштування
    `folder` могли змінити між двома кліками, тож замок призначення сам двох збірок однієї теки не розвів би;
    (б) призначення (`_publish_key`) — друга публікація в той самий `<тека>/<задача>` (навіть із ІНШОГО
    простору) посеред копіювання лишила б напівзібрану теку. Порядок фіксований: спершу (а), потім (б). Замки
    беремо БЕЗ очікування: зайнятий будь-який — одразу 409 `publish-busy` (зависла мережева тека не нагромаджує
    потоки, що чекають, а повторний клік дістає чітку відповідь); це стосується й `build_only`. `publish`
    кличемо БЕЗ `timeout=`: так виклик іде в робочий потік, а той, що не вклався, копіював би далі вже БЕЗ
    замків.

    Ніяких виходів назовні: ні `git_autocommit` (він пушить), ні `_registry_push`, ні `_overview_sync`, ні
    Vercel, ні мережі. `ctx` не серіалізується й не логується: у ньому замикання й клас ядра.
    Помилки модулів (`ModuleError`) летять до `Handler._guarded` — одна відповідь для всіх маршрутів."""
    space = spaces.active_space()
    if space is None:
        h._send_json(no_publish_module_body(), status=409)
        return
    tid, task = h._current_task()
    its = [i for i in load_meta(task).get('iterations', []) if i.get('published')]
    if not its:
        h.send_error(400, 'no iterations marked for publish - '
                          'toggle the green dot first')
        return
    if prov.publish_target == 'url':
        _publish_by_url(h, prov, payload, space, tid, task, its)
        return
    # id, який модуль відмовив би, — 400 ДО будь-якої збірки (правило й причина — коло `publish_id_ok`).
    if not publish_id_ok(tid):
        h._send_json({'ok': False, 'code': 'bad-task-id',
                      'error': 'id задачі не годиться для теки публікації: потрібні лише латинські літери, цифри, '
                               '_ і - (до 128 символів), не імʼя пристрою Windows'}, status=400)
        return
    ctx = deai_modules.module_ctx(space, prov)
    folder = ctx['settings'].get('folder')
    ok, why = deai_modules.folder_ok(space, folder)
    if not ok:
        h._send_json({'ok': False, 'code': 'bad-folder', 'error': why}, status=409)
        return
    gate_pw = ctx['secrets'].get('password') or None
    # Коментарі превʼю: з постачальника ролі `comments` ЦЬОГО простору, раз, ДО збірки (`publish_comments`). Зашитий
    # Supabase ЛІГА (запис `supabase-comments` шляху ЛІГИ) у збірку модуля не їде — `False`, як у 0.3.0. ПОЗА замками: рішення виконує код
    # модуля (до `CHECK_TIMEOUT` = 5 с) і нічого не пише, тож тримати під ним замок збірки задачі — зайве очікування
    # для другого кліку (його `publish-busy` приходить тепер лише коли справді йде збірка чи копіювання).
    comments, comments_warn = publish_comments(space, task, tid, module_publish=True)
    tokens = preview_tokens_snapshot(space)          # знімок токенів для інспектора превʼю: теж виконує код модуля — поза замками
    with _try_publish_locks(task['dir'], folder, tid) as got:
        if not got:
            h._send_json({'ok': False, 'code': 'publish-busy',
                          'error': 'ця задача вже публікується — зачекайте завершення і повторіть'},
                         status=409)
            return
        built = build_preview(task, tid, its, comments=comments, gate_pw=gate_pw, build='module', space=space, tokens=tokens)
        if payload.get('build_only'):
            result = {'ok': True, **built}
        else:
            res = deai_modules.call(prov, 'publish', ctx, built['dir'],
                                    {'id': tid, 'title': task.get('title', tid), 'dir': task['dir']})
            path = res.get('path') if isinstance(res, dict) else None
            if not isinstance(path, str) or not path:
                raise deai_modules.ModuleError('module-error', message='publish returned no path')
            # ⛔ Шлях у `local`/`publish_local` — той, що ПЕРЕВІРЕНО й ЗАМКНЕНО: `<тека>/<задача>` (за `realpath`).
            # Інший — відповідь модуля, якій не вірити: `publish_local` не пишемо. Текст чесний: до цього місця
            # модуль уже ВІДПРАЦЮВАВ, тож файли могли лягти — і в призначення, і за вказаним ним шляхом
            # (самого шляху в тексті нема: це відповідь модуля, а не те, що ядро перевірило).
            if os.path.realpath(path) != os.path.realpath(os.path.join(folder, tid)):
                raise deai_modules.ModuleError(
                    'module-error',
                    message='publish returned a path outside the destination; the module has already run, so '
                            'files may already have been written (to the destination or elsewhere) — check the '
                            'publish folder')
            # ⛔ `iterations.json` перечитуємо ПЕРЕД записом: збірка й копіювання тривали, а дизайнер міг за
            # цей час перемкнути зелену крапку (`publish-toggle`) — запис `meta`, прочитаного на вході,
            # відкотив би її. Пишемо лише своє поле; `publish_url`/`publish_verified` — шлях ЛІГА, не чіпаємо.
            meta = load_meta(task)
            meta['publish_local'] = {'module': prov.id, 'path': path,
                                     'published_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
            save_meta(task, meta)
            result = {'ok': True,
                      'local': {'path': path,
                                'url': f'/published/{quote(space["id"], safe="")}/{quote(tid, safe="")}/'},
                      'iterations': built['iterations'], 'frames': built['frames']}
            if 'frames_warnings' in built:
                result['frames_warnings'] = built['frames_warnings']
    if comments_warn:
        result['comments_unavailable'] = comments_warn
    stale = server_code_staleness()
    if stale:
        result['code_stale'] = stale
    h._send_json(result)


#: Межі відповіді модуля «публікація за адресою»: ядро не вірить модулю на слово, бо збережене ляже в
#: `iterations.json`, а адреса піде в інтерфейс (посилання «Відкрити», «Скопіювати»).
URL_RESULT_MAX_URL = 2048
URL_RESULT_MAX_STATE = 4096           # `len(json.dumps(state))`
URL_RESULT_MAX_WARNINGS = 5
URL_RESULT_MAX_WARNING_LEN = 300
#: Значення секретів модуля коротші за це в його відповіді не шукаємо й не вирізаємо: коротке значення (пароль
#: «1100») збігається зі звичайним текстом, і хибне спрацювання гірше за пропуск.
URL_RESULT_MIN_SECRET = 8
#: Мітка DNS: літери/цифри/дефіс, не з дефіса й не на дефіс, ≤ 63; імена не-ASCII — лише punycode (`xn--…`).
_URL_HOST_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', re.ASCII)
#: Остання мітка (TLD) починається з літери: цифрова (`1` у `127.0.0.1`, `0x7f`) — це IP, а не імʼя.
_URL_HOST_TLD_START = re.compile(r'[a-z]', re.ASCII)


def _utf8_ok(text):
    """Рядок можна записати в UTF-8 файл (самотній сурогат — ні: `iterations.json` зламався б на записі)."""
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        return False
    return True


def _url_host_ok(host):
    """Імʼя хоста — DNS-імʼя з ДВОХ і більше непорожніх міток (`a.b`, `xn--e1afmkfd.example`): без порожніх міток (`.`,
    `a..b`, крапки на початку чи в кінці), без дефіса на краю мітки, ≤ 253 знаків усього, а ОСТАННЯ мітка починається з
    літери (TLD: `com`, `app`, `xn--p1ai`). Тому не проходять IP-адреси в будь-якій формі — `127.0.0.1`, `2130706433`
    (одна мітка з цифр), `0x7f.1` (остання мітка цифрова), `169.254.169.254` — і одномітковий `localhost`; `[::1]`
    не складається з міток. Це не адреса превʼю, а вихід у внутрішню мережу людини: їх не пускаємо. (Імʼя, що
    резолвиться в локальну адресу — `127.0.0.1.nip.io`, — синтаксисом не відсіяти: ядро DNS не питає.)"""
    if not (isinstance(host, str) and 0 < len(host) <= 253):
        return False
    labels = host.split('.')
    return (len(labels) >= 2 and all(_URL_HOST_LABEL.fullmatch(label) for label in labels)
            and _URL_HOST_TLD_START.match(labels[-1]) is not None)


def _url_result_url_ok(url):
    """`https://` без облікових даних і фрагмента, з коректним хостом і портом; ЛИШЕ ASCII (імена IDN — punycode:
    інакше гомогліф чи символ напрямку тексту підмінив би адресу, яку бачить людина), без пробілів, керівних
    символів і зворотної скісної (`urlsplit` мовчки відкидає перенос рядка й табуляцію, тож перевіряємо рядок, а
    не лише розбір). Порт перевіряє `urlsplit` (`:abc`, `:99999` — `ValueError`)."""
    if not isinstance(url, str) or not url.startswith('https://') or len(url) > URL_RESULT_MAX_URL:
        return False
    if not url.isascii() or '#' in url or '\\' in url or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port                        # noqa: B018 — сам доступ кидає `ValueError` на поганому порту
    except ValueError:                    # `https://[::1`, `:abc`, `:99999` та подібні
        return False
    return _url_host_ok(host) and '@' not in parts.netloc and not parts.fragment


def _url_result_state_ok(state):
    """`state` — плаский обʼєкт: ключі — рядки, значення — `str`/`int`/`float`/`bool`/`None` (жодних вкладених
    обʼєктів і списків), скінченні числа, `len(json.dumps(state)) <= 4096`."""
    if not isinstance(state, dict):
        return False
    for key, value in state.items():
        if not isinstance(key, str) or not _utf8_ok(key):
            return False
        if isinstance(value, str):
            if not _utf8_ok(value):
                return False
        elif isinstance(value, float):
            if not math.isfinite(value):
                return False
        elif value is not None and not isinstance(value, (bool, int)):
            return False
    try:
        return len(json.dumps(state)) <= URL_RESULT_MAX_STATE
    except (TypeError, ValueError):       # надвелике ціле: `json.dumps` відмовляє після 4300 цифр
        return False


def _url_result_warnings_ok(warnings):
    return (isinstance(warnings, list) and len(warnings) <= URL_RESULT_MAX_WARNINGS
            and all(isinstance(w, str) and len(w) <= URL_RESULT_MAX_WARNING_LEN and _utf8_ok(w) for w in warnings))


def _checked_url_result(res):
    """`(url, state, verified, warnings)` з відповіді `publish` модуля «за адресою» або `ModuleError('module-error')`.
    Текст чесний: до цього місця модуль уже ВІДПРАЦЮВАВ, тож публікація могла відбутись, хоч ядро її не прийняло;
    самих значень від модуля в тексті нема (це його відповідь, а не те, що ядро перевірило)."""
    if not isinstance(res, dict):
        what = 'result (expected an object)'
    elif not _url_result_url_ok(res.get('url')):
        what = 'url (expected https://host without credentials or a fragment)'
    elif not _url_result_state_ok(res.get('state')):
        what = 'state (expected a flat object of strings and numbers, at most 4096 characters as JSON)'
    elif not isinstance(res.get('verified'), bool):
        what = 'verified (expected true or false)'
    elif 'warnings' in res and not _url_result_warnings_ok(res['warnings']):
        what = 'warnings (expected a list of at most 5 strings of at most 300 characters)'
    else:
        return res['url'], res['state'], res['verified'], list(res.get('warnings', []))
    raise deai_modules.ModuleError(
        'module-error',
        message=f'publish returned an invalid {what}; the module has already run, so the publish may already '
                f'have happened — check the remote before retrying')


def _guarded_url_result_secrets(url, state, warnings, secrets):
    """Відповідь модуля, що пройшла перевірку ФОРМИ, ще не вільна від секретів: модуль міг покласти токен у
    адресу (`?t=…`), у `state` чи в попередження — а `url` і `state` лягають в `iterations.json` і йдуть в
    `/api/task`, `warnings` — у відповідь. Тому: значення секретів модуля (`ctx['secrets']`, не коротші за
    `URL_RESULT_MIN_SECRET`; форми — як у вирізання помилок ядра: сире, repr, JSON, URL-кодоване) у `url` чи
    `json.dumps(state)` → `module-error` без запису (текст без значення). ВИНЯТОК — `password`: пароль превʼю не
    секрет від глядача (вшитий у сторінки), його ядро саме дописує в посилання. У `warnings` вирізаються ВСІ
    такі значення, пароль теж (`***`). Повертає очищені `warnings`."""
    blocked = {k: v for k, v in secrets.items()
               if k != 'password' and isinstance(v, str) and len(v) >= URL_RESULT_MIN_SECRET}
    for text in (url, json.dumps(state)):
        if deai_modules._scrub(text, blocked) != text:
            raise deai_modules.ModuleError(
                'module-error',
                message='publish returned a result that contains a secret of the module; the module has already '
                        'run, so the publish may already have happened — check the remote before retrying; the '
                        'result was not recorded')
    everything = {k: v for k, v in secrets.items() if isinstance(v, str) and len(v) >= URL_RESULT_MIN_SECRET}
    return [deai_modules._scrub(w, everything) for w in warnings]


def _gate_hash(password):
    """Відбиток пароля превʼю для `publish_remote.gate_hash` (ЛИШЕ щоб побачити, що пароль змінився після
    публікації; пароль у метаданих не зберігається): перші 16 hex `sha256`. Не-кодований у UTF-8 пароль — `None`."""
    if not isinstance(password, str) or not _utf8_ok(password):
        return None
    return hashlib.sha256(password.encode('utf-8')).hexdigest()[:16]


def _stored_publish_state(task, prov):
    """`state`, який цей модуль повернув минулого разу (`publish_remote.state` в СВІЖО прочитаному
    `iterations.json`), або `{}`: запису нема, він чужого модуля чи зіпсований."""
    remote = load_meta(task).get('publish_remote')
    if (isinstance(remote, dict) and remote.get('module') == prov.id
            and isinstance(remote.get('state'), dict)):
        return remote['state']
    return {}


def _publish_by_url(h, prov, payload, space, tid, task, its):
    """Гілка `publish_with_module` для модуля `publish_target: url` (етап 2b-1): результат — адреса на віддаленому
    хості, а не тека. Без `published_root`/`folder_ok`/`bad-task-id`: id задачі в адресу не йде (імʼя проєкту
    непрозоре — справа модуля), а теки в модуля нема.

    Порядок: (1) `ctx` модуля — ОДИН раз; пароль — його секрет `password` (порожній = «пароля нема» → `None`);
    (2) замок ЛИШЕ теки збірки задачі (`_try_task_dir_lock`, без очікування: зайнято — 409 `publish-busy`); (3) коментарі
    превʼю (`publish_comments`, як у `publish_with_module`) і збірка; (4) `build_only` — відповідь про збірку, як у
    `folder`; (5) `publish` модуля БЕЗ `timeout=` (у нього свої тайм-аути на запит; `timeout=` пустив би його в
    робочий потік, що не вклався б і працював далі БЕЗ замка) із `task = {id, title, dir, state, gated}`
    (`gated` — чи збірку закрито паролем: модуль пароля не знає, а режиму `cli` це потрібно для перевірки превʼю),
    де `state` — те, що цей модуль повернув минулого разу (СВІЖЕ читання `iterations.json`; чужий чи зіпсований
    запис — `{}`); (6) перевірка відповіді (`_checked_url_result`:
    форма; `_guarded_url_result_secrets`: жодного секрету модуля в `url`/`state`, `warnings` очищено);
    (7) `iterations.json` перечитується ПЕРЕД записом (збірка й публікація тривали, дизайнер міг перемкнути зелену
    крапку) і дістає `publish_url`, `published_at` (`ДД.ММ.РРРР ГГ:ХХ`, як у ЛІГА), `publish_verified` і
    `publish_remote = {module, state, published_at, url, gated[, gate_hash]}`; `publish_local` не чіпається.

    Ніяких виходів назовні з ядра: ні `git_autocommit` (він пушить), ні `_registry_push`, ні `_overview_sync`, ні
    мережі — ходить лише сам модуль."""
    ctx = deai_modules.module_ctx(space, prov)
    gate_pw = ctx['secrets'].get('password') or None
    comments, comments_warn = publish_comments(space, task, tid, module_publish=True)   # поза замком: див. `publish_with_module`
    tokens = preview_tokens_snapshot(space)          # так само поза замком
    with _try_task_dir_lock(task['dir']) as got:
        if not got:
            h._send_json({'ok': False, 'code': 'publish-busy',
                          'error': 'ця задача вже публікується — зачекайте завершення і повторіть'},
                         status=409)
            return
        built = build_preview(task, tid, its, comments=comments, gate_pw=gate_pw, build='module', space=space, tokens=tokens)
        if payload.get('build_only'):
            result = {'ok': True, **built}
        else:
            task_arg = {'id': tid, 'title': task.get('title', tid), 'dir': task['dir'],
                        'state': _stored_publish_state(task, prov), 'gated': gate_pw is not None}
            try:
                res = deai_modules.call(prov, 'publish', ctx, built['dir'], task_arg)
            except deai_modules.ModuleError as e:
                # `message` — ГОЛОВА (300 знаків) останніх 4000 знаків виводу CLI, а причина `vercel deploy` — у КІНЦІ: людині
                # звичайного простору (діалог показує лише `error`) віддаємо хвіст `full`. Інші коди — як є; ЛІГА має свій
                # шлях (`_legacy_deploy_error`).
                if e.code == 'vercel-deploy' and e.full:
                    raise deai_modules.ModuleError(e.code, e.status, e.full[-deai_modules.MAX_MESSAGE:]) from None
                raise
            url, state, verified, warnings = _checked_url_result(res)
            warnings = _guarded_url_result_secrets(url, state, warnings, ctx['secrets'])
            meta = load_meta(task)
            meta['publish_url'] = url
            meta['published_at'] = time.strftime('%d.%m.%Y %H:%M')
            meta['publish_verified'] = verified
            # `url` і `gated`/`gate_hash` — ВЛАСНІ поля ядра (не модуля): що саме опубліковано й з яким паролем.
            # `/api/task` дає посилання з `#k=` лише до адреси, яку записав цей модуль, і судить про гейт за
            # опублікованою збіркою, а не за поточним секретом.
            remote = {'module': prov.id, 'state': state,
                      'published_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      'url': url, 'gated': gate_pw is not None}
            if gate_pw is not None and _gate_hash(gate_pw):
                remote['gate_hash'] = _gate_hash(gate_pw)
            meta['publish_remote'] = remote
            save_meta(task, meta)
            result = {'ok': True, 'url': url, 'verified': verified,
                      'iterations': built['iterations'], 'frames': built['frames']}
            if warnings:
                result['warnings'] = warnings
            if 'frames_warnings' in built:
                result['frames_warnings'] = built['frames_warnings']
    if comments_warn:
        result['comments_unavailable'] = comments_warn
    stale = server_code_staleness()
    if stale:
        result['code_stale'] = stale
    h._send_json(result)


def task_publish_share(space, meta):
    """Поля `/api/task` для простору, де публікує модуль `publish_target: url`. Для неявного постачальника, шляху ЛІГИ
    (`vercel-publish` із `compat == "design-canvas"`: `publish_module` дає `None`), `folder`-модуля і простору без
    постачальника — `{}`.

    • `publish_gate` — чи превʼю ОПУБЛІКОВАНЕ з паролем. Коли є `publish_remote` ЦЬОГО модуля з тією самою адресою,
      що `publish_url` (збіг, див. нижче), — `publish_remote.gated`, тобто те, що справді вийшло (опубліковано без
      пароля, потім пароль задали — превʼю й далі публічне, і застереження «превʼю публічне» мусить лишитись).
      Інакше — чи заданий пароль ЗАРАЗ (публікації цього модуля ще не було чи адреса не його).
    • `publish_gate_stale: true` — лише за збігу й лише коли поточний пароль відрізняється від опублікованого
      (задали, зняли, змінили; порівнюється відбиток `gate_hash`, пароль у метаданих не зберігається): превʼю
      треба опублікувати знову.
    • `publish_share_url` — лише за збігу. Збіг — це `publish_remote.module` == цей модуль І `publish_remote.url`
      == `publish_url`: посилання, що його записало ядро після публікації цього модуля. Адреса від ЛІГА, інша
      адреса після перемикання модулів чи вручну виправлена не збігаються — пароль до чужої адреси не клеїмо.
      Це адреса + `#k=<пароль>`, коли превʼю опубліковане з паролем і він не змінився; інакше сама адреса.

    ⚠️ Свідоме виключення з правила «секрети не йдуть в API»: пароль превʼю — не секрет від глядача (вшитий у
    сторінки, гейт клієнтський), а менеджеру потрібне посилання, що відчиняється одразу. ТОКЕН модуля звідси не
    виходить ніколи: читається лише `password`. Пароль, який не записати в UTF-8 (самотній сурогат у
    `secrets.json`, правленому вручну), — «пароля нема». ТОТАЛЬНА: нечитабельні секрети, `space.json`, каталог,
    зіпсована мета — `{}` чи менше полів, а не 5xx (`/api/task` годує весь інтерфейс); шар вимкнено чи простір запиту
    не зафіксовано — модулів нема (як у `task_preview_gate`)."""
    try:
        mod = deai_modules.publish_module(space)       # `None`: шар вимкнено, простір не зафіксовано, шлях ЛІГИ (`publish_legacy_path`), збій
        if mod is None or mod.status != 'ok' or mod.publish_target != 'url':
            return {}
        # як `deai_modules._ctx`: секрети читаються лише в модуля, що їх оголосив
        secrets = deai_modules.read_secrets(space.get('id'), mod.id) if mod.secret_keys() else {}
        pw = secrets.get('password')
        pw = pw if isinstance(pw, str) and pw and _utf8_ok(pw) else None
        url, remote = meta.get('publish_url'), meta.get('publish_remote')
        if not (isinstance(remote, dict) and remote.get('module') == mod.id
                and isinstance(url, str) and url and remote.get('url') == url):
            return {'publish_gate': pw is not None}
        gated = remote.get('gated') is True
        same = gated == (pw is not None) and (not gated or remote.get('gate_hash') == _gate_hash(pw))
        out = {'publish_gate': gated}
        if not same:
            out['publish_gate_stale'] = True
        out['publish_share_url'] = f'{url}#k={quote(pw, safe="")}' if gated and same and '#' not in url else url
        return out
    except Exception:  # noqa: BLE001 — тотальність: збій читання не ламає `/api/task`
        return {}


#: `preview_gate` для `/api/task`, коли публікує модуль: ТА САМА форма, що в `preview_gate_state` (UI читає ті
#: самі ключі), але `state: 'module'` і нулі — локальна збірка без пароля не «ungated» (це не попередження).
MODULE_GATE_STATE = {'state': 'module', 'stale': 0, 'ungated': 0, 'inner_stale': 0, 'pages': 0}


def task_preview_gate(task, pw, space):
    """`preview_gate` для `/api/task`. Питаємо `deai_modules.capabilities` (ТОТАЛЬНА, не кидає), а не
    `provider`: зіпсований `space.json` не мусить гасити весь `/api/task`. Шар вимкнено чи простір запиту не
    зафіксовано — модулів нема (як у `provider`: без читання реєстру й каталогу модулів). Шлях ЛІГИ (`publish_module` → `None`,
    у т.ч. мігрований `vercel-publish`) — звичайний стан гейта за паролем ЛІГИ."""
    if deai_modules.publish_module(space) is not None:
        return dict(MODULE_GATE_STATE)
    return preview_gate_state(task, pw)


def _vercel_project(tid, task):
    """Опакове ім'я Vercel-проєкту для задачі.

    Правило користувача (30.07.2026): у публічному превью-URL не має бути ні
    назви задачі, ні клієнта, ні номера тікета — лише умовна нумерація. Раніше
    ім'я виводилось із id задачі (`dc-<задача>`), тобто URL сам розповідав контекст.

    Генерується ОДИН раз і зберігається в tasks.json → prod-URL стабільний і
    не змінюється з кожною публікацією.

    ⛔ Якщо задача ВЖЕ публікувалась, а поля немає — не мінтимо нове імʼя молча:
    це змінило б prod-URL, який уже може бути в менеджера. Ризик реальний:
    `publish/` затирається щопублікації разом із `.vercel`, тому зв'язок
    задача→проєкт лишається тільки в цьому полі (03.08.2026 його не було в
    чотирьох задач із живими превʼю). Кидаємо помилку з інструкцією — краще
    відмовити, ніж тихо видати нове посилання.
    """
    if task.get('vercel_project'):
        return task['vercel_project']
    prev = (load_meta(task) or {}).get('publish_url')
    # Не-власник отримав адресу ВЛАСНИКА через «Підтягнути» — це не його посилання,
    # змінювати він його не може, тож і відмовляти нема за що: своє превʼю.
    if prev and _task_is_mine(task):
        raise OSError(
            f'задача вже публікувалась ({prev}), але vercel_project у tasks.json '
            f'немає — нове імʼя змінило б URL, який уже може бути в менеджера. '
            f'Впиши в tasks.json["tasks"]["{tid}"]["vercel_project"] імʼя '
            f'наявного проєкту (видно у Vercel або в publish/.vercel/project.json) '
            f'і повтори публікацію.')
    import secrets
    name = 'pv-' + ''.join(secrets.choice('0123456789') for _ in range(8))
    cfg = load_tasks()
    cfg.setdefault('tasks', {}).setdefault(tid, {})['vercel_project'] = name
    save_tasks(cfg)
    task['vercel_project'] = name
    return name


def _remember_vercel_scope(tid, task, org):
    """Запамʼятати Vercel-скоуп задачі (`org` — `state.scope` з відповіді модуля `vercel-publish`, раніше `orgId` із
    `publish/.vercel/project.json`; `None`, коли модуль скоупу не знає).

    Навіщо окремо від імені: імʼя саме по собі посилання не тримає. У ЧУЖОМУ
    акаунті `vercel link --project <те саме імʼя>` створює ІНШИЙ проєкт — і в
    менеджера з'являється друге посилання, а перше тихо застаріває. Прив'язка =
    пара імʼя+скоуп, тому обидва їдуть у реєстр і обидва підставляються в
    наступну публікацію (`--scope`).

    Наявний скоуп НЕ перезаписується. Best-effort: немає значення — просто не записуємо. Це не аварія:
    `--scope` тоді не підставиться, а інваріант `vercel-binding-unshared` скаже
    про неповну прив'язку вголос.
    """
    if task.get('vercel_scope'):
        return
    if not org or not isinstance(org, str):
        return
    cfg = load_tasks()
    cfg.setdefault('tasks', {}).setdefault(tid, {})['vercel_scope'] = org
    save_tasks(cfg)
    task['vercel_scope'] = org


#: Модуль, яким публікує простір ЛІГА (4b-1): той самий `vercel-publish`, вхід — системний Vercel CLI (режим `cli`).
PUBLISH_LEGACY_MODULE = 'vercel-publish'

#: Тексти ЛІГИ — байт у байт із `_deploy_hint` 0.8.0: модуль віддає КОД відмови, а людський текст — тут, бо він про людей і
#: правила цієї компанії (згадує `tasks.json`). Зникнуть разом із простором ЛІГА (4d). Порядок розпізнавання (вхід → скоуп →
#: доступ; скоуп ПЕРЕД загальним «немає доступу»: тексти перетинаються, а причина конкретніша) — у модулі, `_cli_code`. ⛔ Причину не вигадуємо: код, якого тут
#: нема (`vercel-deploy`, `module-error`…), — не підказка, а сирий хвіст виводу (`_legacy_deploy_error`).
_LEGACY_DEPLOY_HINTS = {
    'vercel-login': ('Vercel не авторизований на цій машині — виконай у терміналі '
                     '`npx vercel login`, тоді натисни «Опублікувати» ще раз.'),
    'vercel-scope': ('Проєкт цієї задачі живе в ІНШОМУ Vercel-скоупі, і цей акаунт до '
                     'нього не має доступу. Публікація звідси створила б ДРУГЕ '
                     'посилання, а те, що вже в менеджера, тихо застаріло б — тому '
                     'vercel відмовив. Попроси власника задачі опублікувати; щоб '
                     'публікувати могли всі, потрібна спільна Vercel-команда, і її '
                     'треба вписати в tasks.json → vercel_scope.'),
    'vercel-auth': ('Немає доступу до Vercel-проєкту під цим акаунтом — або увійди '
                    'тим, що має доступ, або попроси Андрія опублікувати.'),
}
#: Підказка до `verify_error == 'vercel_protection'` — байт у байт із `_check_published` 0.8.0. Захист Vercel (302 на
#: vercel.com/sso-api) ламає гейт превʼю: замість макета редірект, і пароль не показується.
_LEGACY_PROTECTION_HINT = ('Vercel Deployment Protection увімкнена: Project → '
                           'Settings → Deployment Protection → Vercel '
                           'Authentication → Disabled. Інакше замість макета '
                           'редірект на SSO, і наш пароль 1100 не показується.')
#: ⛔ URL НЕ вгадуємо: раніше стояло f'https://{proj}.vercel.app' — і `dc-<задача>` у зоні vercel.app виявилось зайнятим ЧУЖИМ
#: проєктом, тож канвас видавав дизайнеру посилання на сторонній сайт (30.07.2026). Імʼя проєкту в акаунті і хост у
#: vercel.app — різні простори імен. Модуль бере адресу лише з виводу `vercel deploy`/`inspect`; не знайшов — код
#: `vercel-no-url`, і ядро не зберігає нічого.
_LEGACY_NO_URL = ('деплой пройшов, але URL у виводі vercel не знайдено — '
                  'посилання не зберігаю, щоб не вигадати неправильне')


def _publish_legacy_ctx(npx):
    """`ctx` публікації ЛІГИ (запис `vercel-publish` із `compat: design-canvas`). ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`, а секретів
    модуль у режимі `cli` не читає (див. `_vcs_legacy_ctx`). `find_tool` віддає ЛИШЕ `npx` — той самий, що ядро вже знайшло
    (`_node_bin` може запускати login-shell, повторно його не кличемо)."""
    return {'space': {'id': spaces.request_space_id() or '', 'path': ''},
            'settings': {'auth': 'cli', 'team': ''}, 'secrets': {},
            'folder_ok': lambda folder: (False, 'bad-folder'),
            'ModuleError': deai_modules.ModuleError, 'find_tool': lambda name: npx if name == 'npx' else None}


def _publish_legacy_call(task, tid, build_dir, proj, npx):
    """Шов адаптера ЛІГИ: модуль `vercel-publish` у режимі `cli` → його перевірений результат або `ModuleError`. Це ЄДИНЕ
    місце, де ядро публікує ЛІГУ (тести гілки ЛІГИ підміняють саме його).

    `proj` — опакове імʼя проєкту (`_vercel_project`), `build_dir` — зібране `publish/`. Привʼязка задача→проєкт іде модулю
    в `state` (`project`, `task` і — якщо відомий — `scope`; `legacy_state: True` у `task` каже модулю, що стан довірений
    (локальний tasks.json, не git)): ⛔ `--scope` важливий — без нього `vercel link` у ЧУЖОМУ акаунті
    СТВОРИВ БИ проєкт із тим самим імʼям, і задача отримала б друге посилання; зі скоупом vercel відмовляє вголос
    (`vercel-scope`). `gated: True` — гейт ЛІГИ (пароль, типово 1100) вкладає збірка ядра завжди, і превʼю «підтверджене»
    лише з маркером `authgate` на адресі.

    Результат проходить ту саму перевірку форми, що й у модулів «за адресою» (`_checked_url_result`: https-адреса без облікових
    даних, пласкі `state`/`verified`), і мусить нести `deploy_url` (адресу самої публікації — ядро віддає її у відповіді)."""
    m = deai_modules.catalog().get(PUBLISH_LEGACY_MODULE)
    if m is None or m.status != 'ok':
        raise deai_modules.ModuleError('module-error', message=f'{PUBLISH_LEGACY_MODULE} module is not loaded')
    state = {'project': proj, 'task': tid}
    if task.get('vercel_scope'):
        state['scope'] = task['vercel_scope']
    # `legacy_state: True` — ЄДИНЕ місце, що його ставить: стан ЛІГИ береться з локального tasks.json/реєстру (не з git), тож
    # модуль приймає з нього будь-яке безпечне імʼя й скоуп. Звичайний простір (`_publish_by_url`) цього ключа не ставить
    # ніколи: його стан із `iterations.json` (їздить через git) недовірений — див. `_cli_pick` модуля `vercel-publish`.
    arg = {'id': tid, 'title': task.get('title', tid), 'dir': task['dir'], 'gated': True, 'state': state, 'legacy_state': True}
    res = deai_modules.call(m, 'publish', _publish_legacy_ctx(npx), build_dir, arg)
    _checked_url_result(res)
    if not isinstance(res.get('deploy_url'), str):
        raise deai_modules.ModuleError('module-error', message='publish returned no deploy_url')
    return res


#: `vercel deploy` завершився з помилкою, але нічого не надрукував (порожній вивід). 0.8.0 віддавало порожній рядок, який
#: інтерфейс міг прочитати як успіх; тепер — людський рядок (а не непрозорий код `vercel-deploy`).
_LEGACY_EMPTY_OUTPUT = ('vercel завершився з помилкою, але нічого не надрукував — спробуйте ще раз або виконайте '
                        '`npx vercel deploy` у терміналі, щоб побачити причину')


def _legacy_deploy_error(e):
    """`deploy_error` ЛІГИ з відмови модуля — той самий рядок, що в 0.8.0: підказка + «— вивід vercel —» + хвіст (300 знаків)
    для впізнаних причин (`vercel-login`/`-scope`/`-auth`), інакше лише хвіст (400). Хвіст беремо з ПОВНОГО тексту
    (`ModuleError.full`): `message` обрізано до 300 знаків з початку, а 0.8.0 різало з кінця виводу.

    Порожній (чи з самих пробілів) вивід — `_LEGACY_EMPTY_OUTPUT` замість порожнього хвоста (0.8.0 віддавало '', який
    інтерфейс міг прочитати як успіх) і замість непрозорого коду: для впізнаної причини — підказка, порожній рядок і цей
    текст (без заголовка «— вивід vercel —»: виводу нема), інакше лише він."""
    if e.code == 'vercel-no-url':
        return _LEGACY_NO_URL
    raw = e.full or e.message or ''
    hint = _LEGACY_DEPLOY_HINTS.get(e.code)
    if not raw.strip():
        return f'{hint}\n\n{_LEGACY_EMPTY_OUTPUT}' if hint else _LEGACY_EMPTY_OUTPUT
    return f'{hint}\n\n— вивід vercel —\n{raw[-300:]}' if hint else raw[-400:]


def _killpg(child, sig):
    """Сигнал ГРУПІ процесів дитини, а не прямій дитині.

    Chromium — ОНУК процесу node: сигнал самому node до браузера не доходить, і
    headless-Chromium лишався б жити безстроково. Дитина могла померти сама між
    перевіркою і сигналом — це не помилка, тому ProcessLookupError гасимо.
    """
    try:
        os.killpg(child.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _shoot_alive(entry):
    """Чи ще жива зʼємка за цим записом реєстру.

    Заглушка (`proc: None`) — це вікно між взяттям ключа й Popen, і вона
    рахується ЖИВОЮ свідомо. Інакше два запити, що розійшлися в межах fork+exec,
    обидва пройшли б перевірку «чи є жива» й підняли по Chromium на ту саму теку.
    """
    proc = entry.get('proc')
    return proc is None or proc.poll() is None


def _in_space(fn):
    """Загорнути тіло фонового потоку чи таймера в простір запиту, що його ЗАПУСТИВ.

    Простір запиту живе в `threading.local`, а потік, який запускає сервер (читач виводу
    зʼємки, сторож, таймер вбивства), його НЕ успадковує: без явного простору він жив би з
    УВІМКНЕНИМИ інтеграціями (без зафіксованого простору рішення — «неявний простір») і з файлом задач
    ПОТОЧНОГО простору машини, а не того, чиїм запитом його запущено. Простір береться
    тут, у потоці запиту, ДО старту; кожен `threading.Thread`/`threading.Timer` у цьому файлі
    мусить отримати ціль через цю функцію (стереже `tests/test_spaces_serve.py`)."""
    sid = spaces.request_space_id()

    # `wraps` лишає цілі її імʼя/`__qualname__`: за ним тести (і відлагодження) впізнають, ЯКИЙ
    # саме потік це — без нього всі вони звались би `_in_space.<locals>.run`.
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with spaces.request_space(sid):
            return fn(*args, **kwargs)
    return run


def _arm_hard_kill(entry):
    """Озброїти SIGKILL через HARD_KILL_S — РІВНО раз на зʼємку.

    ⚠️ Кличеться ПІД `_SHOOTS_LOCK` (тому власного замка не бере: він не
    реєнтрантний). Це не формальність: озброєння мусить бути в тому самому
    входженні в замок, що й читання запису з реєстру, інакше `finally` у `_shoot`
    встигне між ними прибрати запис — і лишиться таймер, який ніхто не скасує, а
    pid дитини до його спрацювання може вже належати чужому процесу.

    Ескалацію ставлять двоє: сторож на SHOOT_TIMEOUT_S і ручна «Зупинити».
    Без неї ручна зупинка лишалась половинною: node, який не відреагував на
    SIGTERM, добігає цикл, `child.stdout.read()` тримає потік обробника, запис
    висить у реєстрі — і нову зʼємку в цій ітерації вже не запустити.

    Таймер живе в САМОМУ записі, а не в локальній змінній `_shoot`: інакше
    «Зупинити» (інший запит, інший потік) не мала б до чого дотягнутись, а два
    озброєння підряд дали б `RuntimeError` (Timer стартує рівно раз).
    """
    proc = entry.get('proc')
    if proc is None or entry.get('hard') is not None:
        return
    timer = threading.Timer(HARD_KILL_S, _in_space(lambda: _killpg(proc, signal.SIGKILL)))
    timer.daemon = True
    entry['hard'] = timer
    timer.start()


def _consume_stderr_line(line, progress, tail):
    """Один рядок stderr дитини: або подія прогресу, або текст причини.

    Розділення несуче. Текст причини — це те, що побачить дизайнер, коли зʼємка
    впаде ДО звіту (класика: не встановлений chromium), і його зрізають до
    останніх 2000 байт. Пустити туди 22 події прогресу означало б витіснити
    справжню причину рівно тоді, коли вона потрібна.
    """
    ev = parse_progress_line(line)
    if ev is None:
        tail.append(line)
        return
    progress.apply(ev)


# ---------------------------------------------------------------------------------------------------------
# Модулі: API (етап 2а, Task 6). Маршрути `/api/modules`, `/api/module-enable|disable|settings|check`,
# `/api/ds-tokens` — РЕЄСТРОВІ (`Handler._REGISTRY_ROUTES`): простір — параметр `space`, а не заголовок задачі.
# Уся логіка тут — модульні функції (тестуються без сокета); методи `Handler` лише розбирають запит.

#: Відмови `deai_modules.check`, які НЕ стають вердиктом: `unknown-module` (такого модуля нема — нічого перевіряти)
#: і `space-json-unreadable` (простір не прочитати — це про простір, не про модуль): HTTP-відмова центрального
#: обробника (`Handler._guarded`). УСЕ ІНШЕ, що кинула `check` — `bad-settings`, `module-error`, `check-timeout`,
#: `secrets-unreadable`, `bad-manifest` і власна відмова модуля з кодом ядра (`bad-folder`…), — вердикт
#: `check: {ok: false, error: <код>, detail}` (HTTP 200), так само, як `ok: false` від самого модуля, а `GET
#: /api/modules` показує їх тим самим `status: error`. Для `module-enable|settings` це ще й чесність: до `check` стан
#: УЖЕ записано, і 400/409/502/504 збрехали б, що нічого не змінилось (а новий код модуля чи ядра не лишився б
#: HTTP-збоєм через те, що його забули дописати в білий список). `module-untrusted` — свій модуль без довіри (3c): його код
#: не виконувався, вердикту нема (HTTP 409).
CHECK_NOT_A_VERDICT = ('unknown-module', 'space-json-unreadable', 'module-untrusted')


def space_view(sp):
    """`spaces.describe(sp)` + `capabilities` (ТОТАЛЬНА: нечитабельна `space.json` лягає в `capabilities.error`,
    а не в 5xx). `capabilities` додаємо ТУТ, а не в `describe`: точні тести рівності `describe`/`listing`, а
    головне — опитування й списки не мусять вантажити модулі. `None` (шар вимкнено) лишається `None`."""
    out = spaces.describe(sp)
    if out is not None:
        out['capabilities'] = deai_modules.capabilities(sp)
        out['tools'] = spaces.space_tools(sp)           # вимикачі інструментів («В Figma»): смуга й ⌘K
        compat = deai_modules.compat_view(sp, out['capabilities'])
        if compat:                       # ключ лише коли непорожній (Поправка 4): точні тести `describe`/`listing` не зачеплені
            out['compat'] = compat
    return out


def spaces_listing():
    """`spaces.listing()` + `capabilities` і `tracks`/`default_track` у кожному записі. Запис реєстру відновлюється з самого запису
    списку (вдруге реєстр не читаємо — списку вистачає одного знімка). Один збій простору не ламає список:
    `capabilities` і напрямки не кидають.

    `tracks` (4d-1) — `[{id, label}]` напрямків простору й `default_track`; ⛔ БЕЗ `root` і `repo`: шляхи й адреси репо не їдуть у
    браузер (форма «Нова задача» вибирає напрямок за назвою, а теку й репо додає сервер). Напрямки простору — ОДНЕ `_TrackView`
    на простір (`space.json` читається раз, корінь ЛІГИ — раз на простір ЛІГИ), без вартості на рядок. ⛔ Корені напрямків НЕ
    перевіряються (`roots=False`): ні `realpath` по кожному, ні `read_registry()` на простір, ні `check_new_path` проти кожного
    простору — корінь на відімкненому чи повільному томі гальмував би `GET /api/spaces`, а список їх не віддає."""
    out = spaces.listing()
    for e in out['spaces']:
        sp = {'id': e['id'], 'path': e['path']}
        e['capabilities'] = deai_modules.capabilities(sp)
        e['tools'] = spaces.space_tools(sp)         # вимикачі інструментів («В Figma»): смуга й ⌘K читають їх зі списку
        compat = deai_modules.compat_view(sp, e['capabilities'])
        if compat:
            e['compat'] = compat
        view = _TrackView(sp, roots=False)       # корені списку не потрібні: без перевірок диска й реєстру (див. `_TrackView`)
        e['tracks'] = [{'id': t['id'], 'label': t['label']} for t in view.tracks]
        e['default_track'] = view.default
    return out


def _secret_flags(space_id, m):
    """({ключ секрету: задано}, код помилки | `None`). «Задано» — є НЕПОРОЖНЄ значення (порожній рядок —
    не пароль). Файл секретів не читається — `set` невідомий (`None`), а код іде в статус модуля: «не задано»
    збрехало б, а мовчазне зникнення пароля з вікна — рівно те, проти чого `secrets-unreadable`."""
    keys = m.secret_keys()
    if not keys:
        return {}, None
    try:
        got = deai_modules.read_secrets(space_id, m.id)
    except deai_modules.ModuleError as e:
        return {k: None for k in keys}, e.code
    return {k: bool(got.get(k)) for k in keys}, None


def _module_status(m, last, secrets_error):
    """`(status, error)` модуля каталогу:
      * `untrusted` — свій модуль простору без довіри на цьому компʼютері (3c; `m.status == 'untrusted'`, текст — `m.error`):
                      його код не виконувався, потрібна довіра людини — це не помилка;
      * `error`     — не завантажився (`m.status != 'ok'`; текст — `m.error`), чи файл секретів не читається
                      (`secrets-unreadable`), чи ОСТАННІЙ `check` не ok (`error` — його `error`: код ядра
                      `bad-settings|module-error|check-timeout` або власний текст модуля; `detail` — у `last_check`);
      * `unchecked` — завантажився, `check` ще не було (`last` — `None`; сервер щойно стартував чи нічого не
                      запускали: GET модулі НЕ виконує, лише читає запамʼятоване);
      * `ok`        — останній `check` ok.
    `missing` (увімкнений, а в каталозі нема) — окремо, у `module_list`. Вмикання на статус не впливає: це про
    ЗДОРОВ'Я модуля, а не про його роль. Запамʼятований `check` не інвалідується правкою `space.json` руками."""
    if m.status == 'untrusted':
        return 'untrusted', m.error                     # свій модуль без довіри (3c): не «помилка», а «потрібна довіра»
    if m.status != 'ok':
        return 'error', m.error
    if secrets_error:
        return 'error', secrets_error
    if last is None:
        return 'unchecked', None
    if last.get('ok') is True:
        return 'ok', None
    return 'error', last.get('error') or 'check failed'


def module_list(space):
    """Записи `GET /api/modules` для простору `space`: модулі каталогу (за абеткою), далі `missing` — модулі,
    ЯВНО увімкнені в `space.json`, яких на цій машині нема (вимкнений відсутній — не показуємо: це лише
    залишок налаштувань). Секрет — ЛИШЕ `set: true|false|null`, значення сюди не доходить (читаємо лише
    прапорці). Налаштування — СИМВОЛЬНІ (`{home}`, `{space}`…), з типовими значеннями маніфесту.
    Свої модулі простору (3c) — серед модулів каталогу (`catalog(space)`): запис несе ще `builtin: false`, `custom: true`,
    `trust` (`untrusted|trusted|changed|refused`), `record` (чи є запис довіри), `source` (тека в просторі, з `~`), `runs`
    (є цілий знімок, і його код тут виконується; збій завантаження цього коду — не `runs: false`, а `status: error`) і,
    коли є, `trust_error`. Запис вбудованого модуля цих полів не має. `check_timeout_s` — лише коли маніфест його задає
    (4b-1: `vercel-publish`): клієнт ставить стелю запиту `check` не нижчою за нього (`checkPostTimeoutMs`).
    Може кинути `ModuleError('space-json-unreadable')` (центральна 409)."""
    sid = space['id']
    cat = deai_modules.catalog(space)
    state = deai_modules.effective_state(space)
    explicit = deai_modules.space_modules(space)
    out = []
    for mid, m in cat.items():
        st = state.get(mid)
        if st is None:                                  # каталог змінився між двома читаннями
            continue
        flags, secrets_err = _secret_flags(sid, m)
        last = deai_modules.last_check(sid, mid)
        status, error = _module_status(m, last, secrets_err)
        settings = []
        for s in m.settings:
            v = {'key': s['key'], 'type': s['type'], 'label': s['label'], 'required': s['required']}
            if s['type'] == 'secret':
                v['set'] = flags[s['key']]
            elif s['key'] in st['settings']:
                v['value'] = st['settings'][s['key']]
            if 'options' in s:
                v['options'] = [dict(o) for o in s['options']]
            settings.append(v)
        e = {'id': mid, 'name': m.name, 'version': m.version, 'api': m.api, 'roles': list(m.roles),
             'builtin': True, 'enabled': st['enabled'], 'implicit': st['implicit'], 'status': status,
             'settings': settings}
        if m.check_timeout_s is not None:               # довший `check` (маніфест): клієнт чекає на запит не менше за нього
            e['check_timeout_s'] = m.check_timeout_s
        if m.origin == 'space':                         # свій модуль простору (3c); запис вбудованого не змінюється
            e.update(builtin=False, custom=True, trust=m.trust, record=m.record, source=m.source,
                     runs=not deai_modules.untrusted_own(m))      # є цілий знімок і його код виконується (збій — у `status`)
            if m.trust_error:
                e['trust_error'] = m.trust_error
        if last is not None:
            e['last_check'] = last
        if error is not None:
            e['error'] = error
        out.append(e)
    for mid in sorted(explicit):
        if mid not in cat and explicit[mid]['enabled']:
            out.append({'id': mid, 'name': mid, 'version': '', 'api': None, 'roles': [], 'builtin': False,
                        'enabled': True, 'implicit': False, 'status': 'missing', 'settings': [],
                        'error': 'module is not installed on this machine'})
    return out


def modules_payload(space):
    """Тіло `GET /api/modules`: `{modules}` і — ЛИШЕ коли є — `notes` своїх модулів простору (`[{folder, code}]`: теку
    пропущено чи не прочитано) і `deai.authoring` — АБСОЛЮТНИЙ шлях до `docs/modules/authoring.md` цієї установки (від кореня
    репо, як `bin/`): діалог «Свій модуль» кладе його в запит агенту."""
    out = {'modules': module_list(space), 'deai': {'authoring': os.path.join(ROOT, 'docs', 'modules', 'authoring.md')},
           'tools': spaces.space_tools(space)}
    notes = deai_modules.own_notes(space)
    if notes:
        out['notes'] = notes
    return out


def module_entry(space, mid):
    """Запис одного модуля (`module_list`); `None`, коли його щойно не стало."""
    return next((e for e in module_list(space) if e['id'] == mid), None)


def module_check_verdict(space, mid):
    """`deai_modules.check` з усіма відмовами, крім `CHECK_NOT_A_VERDICT`, перетвореними на вердикт
    `{ok: false, error, detail}` — рівно той, що `check` запамʼятав для `last_check` (там, де запамʼятав). Решта летить.

    ⛔ Закон ізоляції (4d-3b, ревʼю): запис із `shared_state` в ізольованому прогоні (`DC_TASKS_FILE`/`DC_NO_OVERVIEW`) НЕ
    перевіряється — ні секрети (`secrets.json` справжнього `DEAI_HOME`), ні код модуля (мережа Supabase/ls-remote). Вердикт
    `isolated`; `last_check` НЕ перезаписуємо (`deai_modules.check` не кличемо): це не результат перевірки модуля, і стара
    правдива відповідь не мусить затертись «відмовою», якої модуль не давав. Усі п'ять ролей (comments/vcs/dashboard/tracker/
    notify): сюди ходять і `POST /api/module-check`, і хвіст `module_write`. Будь-якого походження — відмова безпечна."""
    if isolation.isolated() and deai_modules.shared_state(space, mid):
        return {'ok': False, 'error': 'isolated',
                'detail': 'Перевірка спільного стану в ізольованому прогоні не виконується.'}
    try:
        return deai_modules.check(space, mid)
    except deai_modules.ModuleError as e:
        if e.code in CHECK_NOT_A_VERDICT:
            raise
        return {'ok': False, 'error': e.code, 'detail': e.message}


#: «Ключа `replace` у тілі не було» — відмінне від явного JSON `null` (той — помилка клієнта: `bad-settings`).
_NO_REPLACE = object()


def module_write(space, mid, action, settings, secrets, replace=_NO_REPLACE):
    """Запис `module-enable|settings|disable` у ПОРЯДКУ СПЕКИ: валідація налаштувань (нічого не пише) →
    пре-перевірка → СЕКРЕТИ → `space.json` → (`enable`/`settings`) `check`. Секрет ПЕРШИМ: сирітський секрет
    нешкідливий, а увімкнений модуль без секрету — ні (невдалий запис секрету зупиняє вмикання до `space.json`).
    Усе, що видно ДО запису, відмовляє ДО нього: валідація налаштувань (`bad-settings`) і читання без запису
    (`deai_modules.preflight`: `unknown-module`, `space-json-unreadable`, для вмикання — `role-taken`), інакше 400/409
    лишили б змінений живий пароль. Те, що пре-перевірка бачить інакше за лок (гонка з паралельною правкою) або не
    може записати (`unwritable`), відмовить уже ПІСЛЯ секрету — спека це приймає: сирітський секрет нешкідливий.
    `disable` налаштувань і секретів НЕ чіпає й не читає (серед аргументів воно ігнорується); для відсутнього в
    каталозі (`missing`) модуля це єдина дозволена дія.
    `replace` — лише для `enable`: `_NO_REPLACE` (ключа в тілі не було) чи `bool`; будь-що інше, зокрема явний `null`, —
    `bad-settings` ДО будь-якого запису (до секрету теж). `replace: true` звільняє роль у її поточних постачальників тим
    самим записом `space.json` (`write_module_state`); ціль заміни мусить бути модулем, що завантажився (інакше відмова
    його `error_code` — `module-error`/`bad-manifest` — ДО секрету: заміна лишила б роль без виконавця); для `settings`
    і `disable` ключ ігнорується.
    Повертає `(вердикт | None, replaced | None)`: вердикт `check` або `None` (`disable`; налаштування свого модуля без
    довіри); `replaced` — список id, звільнених заміною, лише коли `replace is True` (інакше `None`)."""
    if action == 'disable':
        deai_modules.write_module_state(space, mid, enabled=False)
        return None, None
    deai_modules.validate_settings(mid, settings, space)
    if action == 'enable' and replace is not _NO_REPLACE and not isinstance(replace, bool):
        raise deai_modules.ModuleError('bad-settings', message='replace: expected a boolean')
    swap = action == 'enable' and replace is True
    deai_modules.preflight(space, mid, enabling=(action == 'enable'), replace=swap)
    if secrets is not None:
        deai_modules.write_secrets(space['id'], mid, secrets, space=space)
    state = deai_modules.write_module_state(space, mid, enabled=True if action == 'enable' else None,
                                            settings=settings, replace=swap)
    m = deai_modules.catalog(space).get(mid)
    replaced = state.get('replaced') if swap else None
    if m is not None and deai_modules.untrusted_own(m):
        return None, replaced                           # свій модуль без довіри: перевіряти нічого (код не виконується)
    return module_check_verdict(space, mid), replaced


def _token_map(raw):
    """`{імʼя: [значення…]}` з відповіді `tokens` модуля, або `None`, коли форма не та (ключі — рядки, значення —
    списки рядків): такий результат не можна віддати інспектору, і він не мусить упасти на ньому."""
    if not isinstance(raw, dict):
        return None
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            return None
    return raw


def ds_tokens_view(space):
    """Тіло `GET /api/ds-tokens` для простору `space`: `{profile: 'space:<id>', tokens, source}`; нема
    постачальника ролі `tokens` чи мапа порожня — `{profile: null}`; помилка модуля (`ModuleError` будь-якого
    коду, зокрема `check-timeout`, нечитабельний `space.json`, не та форма відповіді) — `{profile: null, error:
    <код>}`. НІКОЛИ не 5xx: інспектор мусить працювати й без токенів. `tokens` модуля лише читає, тож тайм-аут
    (`CHECK_TIMEOUT`) тут безпечний — потік-сирота нічого не зіпсує."""
    try:
        prov = deai_modules.provider('tokens', space)
        if not isinstance(prov, deai_modules.Module):
            return {'profile': None}
        res = deai_modules.call(prov, 'tokens', deai_modules.module_ctx(space, prov),
                                timeout=deai_modules.CHECK_TIMEOUT)
    except deai_modules.ModuleError as e:
        return {'profile': None, 'error': e.code}
    tokens = _token_map(res.get('tokens')) if isinstance(res, dict) else None
    if tokens is None:
        return {'profile': None, 'error': 'module-error'}
    if not tokens:
        return {'profile': None}
    source = res.get('source')
    return {'profile': f'space:{space["id"]}', 'tokens': tokens,
            'source': source if isinstance(source, str) else ''}


def _shot_file(task, it, node):
    """Шлях до кадру `<ітерація>/shots/<node>.webp` або `None`: імʼя за `NAME_RE`/`SHOT_RE` (перший замок) і realpath усередині теки
    кадрів (другий) — ціна помилки тут віддача будь-якого файла з диска. Спільна для `Handler._shot` і відгуку."""
    if not isinstance(it, str) or not isinstance(node, str) or not NAME_RE.fullmatch(it) or not SHOT_RE.fullmatch(node):
        return None
    base = os.path.realpath(os.path.join(_iter_dir(task, it), 'shots'))
    target = os.path.realpath(os.path.join(base, node + '.webp'))
    if not target.startswith(base + os.sep) or not os.path.isfile(target):
        return None
    return target


def _guarded_request(method):
    """Декоратор `do_GET`/`do_POST`: тіло методу виконується під `Handler._guarded` (центральні
    відповіді `no-task` / `space-unavailable` / `spaces-*` / `ambiguous-task`). Саме декоратор, а
    не винесення тіла в окремий метод: код маршрутів лишається в `do_POST`/`do_GET`, де його
    шукають і люди, і тести (`inspect.getsource` розгортає `__wrapped__`)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        return self._guarded(lambda: method(self, *args, **kwargs))
    return wrapper


# ---------- Синк дашборда: фоновий процес, один на простір (4c-1) ----------
#: Ключ синку ЛІГИ, коли її запису в реєстрі нема (поза `SPACE_ID_RE`: з id справжнього простору збігтись не може).
LEAGUE_KEY = '@league'
#: Скільки живе дитина синку, перш ніж новий тригер її перерве. ≥ найгіршого проходу: реєстр GitLab (fetch) і Jira — до ~1,5 хв,
#: `open_comments` до 60 с, `push` пакетами по 50 карток × 15 с (500 карток — 150 с): разом до ~5 хв, тож 10 хв — із запасом.
SYNC_DEADLINE_S = 600
#: Годинник дедлайну (шов для тестів).
_SYNC_CLOCK = time.monotonic
_SYNC_LOCK = threading.Lock()
#: `{ключ синку: {'popen', 'pending', 'started', 'target'}}` — стан «один синк на простір» (під `_SYNC_LOCK`).
_SYNC_RUNS = {}


# ---------- Оновлення інструмента (0.23.0) ----------
#: Корінь, який оновлюємо (шов тестів: викидний git-світ).
UPDATER_ROOT = ROOT
_restart = updater.exec_restart          # шов тестів: після `202` викликається без аргументів
_UPDATER = None
_UPDATER_LOCK = threading.Lock()


def _update_busy():
    """Чому зараз не можна міняти код під ногами (`None` — можна): триває зʼємка чи живий процес синку дашборда."""
    with _SHOOTS_LOCK:
        if _SHOOTS:
            return 'shooting'
    with _SYNC_LOCK:
        for run in list(_SYNC_RUNS.values()):
            p = run.get('popen')
            if p is not None and p.poll() is None:
                return 'syncing'
    return None


def _restart_or_flag():
    """Перезапуск після оновлення. Успішний `execv` не повертається; `False` чи виняток — лишаємось на старому процесі: один рядок у
    stderr (лише код) і прапорець у стані (`GET /api/update` → `restart_failed`), щоб інтерфейс попросив перезапустити канвас вручну."""
    try:
        ok = _restart()
        code = 'refused'
    except Exception as e:  # noqa: BLE001
        ok, code = False, type(e).__name__
    if ok is False:
        print('оновлення: перезапуск не вдався (%s); перезапустіть канвас вручну' % code, file=sys.stderr)
        try:
            _updater().mark_restart_failed()
        except Exception:  # noqa: BLE001
            pass


def _updater():
    """Єдиний `Updater` процесу (ліниво: корінь читається при першому зверненні, тож тест підміняє `UPDATER_ROOT` до нього)."""
    global _UPDATER
    with _UPDATER_LOCK:
        if _UPDATER is None:
            _UPDATER = updater.Updater(UPDATER_ROOT, busy=_update_busy)
        return _UPDATER


def _overview_target():
    """`(ключ синку, аргументи простору для CLI)`. Простір запиту фіксований — це його id: `--space <id>` (ключ = id). Не
    фіксований (інструменти ЛІГИ, тести): `provider` вирішує як для ЛІГИ без реєстру, тож і тут беремо ЇЇ — реальний id запису
    реєстру з `legacy` (той самий ключ, що в тригера, фіксованого на ній: ОДИН синк на простір ЛІГИ), а коли запису нема —
    `--legacy` і `LEAGUE_KEY`. ⛔ Не псевдонім-id `legacy`: `SPACE_ID_RE` його пропускає, і справжній простір «Legacy» збігся б із
    ЛІГОЮ (і в CLI, і в `_SYNC_RUNS`). Реєстр лише ЧИТАЄТЬСЯ (`read_registry`: без міграції й запису)."""
    sid = spaces.request_space_id()
    if sid:
        return sid, ['--space', sid]
    try:
        entry = next((sp for sp in spaces.read_registry()['spaces'] if sp.get('legacy')), None)
    except Exception:  # noqa: BLE001 — реєстр не читається: ЛІГА без запису
        entry = None
    if entry is not None:
        return entry['id'], ['--space', entry['id']]
    return LEAGUE_KEY, ['--legacy']


def _overview_log_path():
    """Куди дитина пише: для всіх просторів один файл `<DEAI_HOME>/logs/dashboard-sync.log` (тека лише для власника,
    0o700: у лозі назви задач; `chmod` окремо — `makedirs(mode=)` б'ється об umask). Старого логу ЛІГИ в `~/.claude/pipeline-feedback/` сервер не пише."""
    d = os.path.join(spaces.home(), 'logs')
    os.makedirs(d, mode=0o700, exist_ok=True)
    os.chmod(d, 0o700)
    return os.path.join(d, 'dashboard-sync.log')


def _overview_spawn(target, note=None):
    """Стартувати дитину синку (`target` — аргументи простору для CLI); `None`, коли не вийшло (тека лога, `Popen`) —
    best-effort, не кидає. `note` — один рядок у лог ПЕРЕД стартом (перервали завислу дитину).
    ⛔ argv рівно `[sys.executable, bin/overview_push.py, 'sync', *target]`: той самий інтерпретатор, що веде сервер (було
    літеральне `python3`), і простір ЯВНО (синк веде простір запиту, а не «поточний машини»); конфіг не передається."""
    log = None
    try:
        # Вивід — у лог, а НЕ в /dev/null. Досі цей пуш був подвійно німим: виняток ковтав except, а те, що
        # написав сам скрипт, ішло в нікуди. Саме так ховається клас збоїв «на дашборді старі дані, і ніхто не знає чому».
        path = _overview_log_path()
        log = open(path, 'a', encoding='utf-8')
        os.chmod(path, 0o600)           # у лозі назви задач: файл лише для власника (тека вже 0o700)
        # Лог спільний для всіх просторів: заголовок із часом і ціллю відрізняє рядки одного запуску від іншого.
        log.write('--- %s sync %s\n' % (time.strftime('%Y-%m-%dT%H:%M:%S%z'), ' '.join(target)))
        log.flush()
        if note:
            log.write(note + '\n')
            log.flush()
        return subprocess.Popen(
            [sys.executable, os.path.join(ROOT, 'bin', 'overview_push.py'), 'sync', *target],
            stdout=log, stderr=subprocess.STDOUT)
    except Exception:  # noqa: BLE001
        return None
    finally:
        # Дитина вже має власну копію дескриптора; наш файловий обʼєкт закриваємо сами — і
        # коли `Popen` упав (інакше ResourceWarning і дескриптор до збирача сміття).
        if log is not None:
            with contextlib.suppress(OSError):      # best-effort: збій закриття не кидає з `finally`
                log.close()


def _overview_stop(p):
    """Перервати завислу дитину ЗА ЇЇ ДЕСКРИПТОРОМ (ніколи за шаблоном): `terminate`, за 5 с — `kill`. Best-effort."""
    with contextlib.suppress(Exception):
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def _overview_launch(key, target):
    """Один синк на простір: поки попередня дитина жива (`poll() is None`), новий тригер лише ставить позначку «ще раз» (рівно
    ОДИН повтор після її завершення, а не по одному на тригер); тригер ІНШОГО простору стартує паралельно. До 4c-1 кожен тригер
    був окремим процесом, і два синки одного простору бігли разом (гонка за один рядок). Спостерігач — потік, що чекає `wait()`.
    Дитина, що живе довше `SYNC_DEADLINE_S` (зависла: мережа, git), не блокує простір до перезапуску сервера: новий тригер її
    перериває (`_overview_stop`), пише про це один рядок у лог і стартує свіжу."""
    note = None
    with _SYNC_LOCK:
        run = _SYNC_RUNS.get(key)
        if run is not None and run['popen'].poll() is None:
            if _SYNC_CLOCK() - run['started'] <= SYNC_DEADLINE_S:
                run['pending'] = True
                return
            _overview_stop(run['popen'])
            note = f'⛔ overview: попередній синк завис довше {SYNC_DEADLINE_S} с — перервано, стартую новий'
        p = _overview_spawn(target, note)
        if p is None:
            _SYNC_RUNS.pop(key, None)
            return
        _SYNC_RUNS[key] = {'popen': p, 'pending': False, 'started': _SYNC_CLOCK(), 'target': target}
    # `_in_space`: кожен потік у цьому файлі несе простір запиту (інваріант `tests/test_spaces_serve.py`); спостерігач його не питає,
    # але правило одне на всіх
    threading.Thread(target=_in_space(lambda: _overview_watch(key, p)), name=f'overview-sync-{key}', daemon=True).start()


def _overview_watch(key, p):
    """Чекає дитину `p`; була позначка «ще раз» — стартує рівно одну нову й чекає вже її. Запис простору зник чи належить іншій
    дитині (новий тригер встиг стартувати, коли `p` вже скінчилась, чи перервав її за дедлайном) — виходить: ту дитину веде свій
    спостерігач, а чужий запис не чіпаємо (інакше наступний тригер стартував би другий синк поруч із живим)."""
    while True:
        try:
            p.wait()
        except Exception:  # noqa: BLE001 — спостерігач не падає: найгірше — повтор пропаде до наступного тригера
            pass
        with _SYNC_LOCK:
            run = _SYNC_RUNS.get(key)
            if run is None or run['popen'] is not p:
                return
            if not run['pending']:
                del _SYNC_RUNS[key]
                return
            p = _overview_spawn(run['target'])
            if p is None:
                del _SYNC_RUNS[key]
                return
            _SYNC_RUNS[key] = {'popen': p, 'pending': False, 'started': _SYNC_CLOCK(), 'target': run['target']}


class Handler(SimpleHTTPRequestHandler):
    # Маніфест застосунку (PWA) — `application/manifest+json`. ЯВНИЙ запис, а не
    # везіння версії Python: у таблиці `mimetypes` старих збірок (системний
    # python3 macOS) `.webmanifest` може не бути, і тоді статика віддала б його як
    # `application/octet-stream`. `sw.js` окремого запису не потребує: `.js` —
    # JavaScript в усіх версіях, а `no-cache` йому дає `end_headers` нижче, як і
    # решті статики.
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.webmanifest': 'application/manifest+json'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        if self._successor:                                  # 4d-4c: псевдонім `/api/gitlab-*` живе до 1.0
            self.send_header('Deprecation', 'true')
            self.send_header('Link', '<%s>; rel="successor-version"' % self._successor)
        # dev-инструмент: иначе браузер кэширует ES-модули и «не видит» правок.
        # Але тільки якщо відповідь ще НЕ поставила свій Cache-Control сама
        # (кадр у `_shot` уже поставив): два заголовки Cache-Control браузер
        # читає як один через кому, і `no-cache` у хвості змушує його звіряти
        # кожен кадр з сервером знову — тобто гасить immutable нанівець мовчки,
        # без жодної помилки. Знайдено живим тестом K1: перебудова й далі тягла
        # всі кадри з мережі, хоч заголовок нижче стояв правильний.
        # `_headers_buffer` — ПРИВАТНИЙ, недокументований атрибут реалізації
        # `http.server` (список сирих байтових рядків, накопичених `send_header`
        # ДО `end_headers`). Він може зникнути чи перейменуватись у майбутній
        # версії Python — тоді `getattr(..., [])` тихо поверне порожній список,
        # `any(...)` стане `False`, і код мовчки відкотиться до старої поведінки
        # (подвійний Cache-Control, immutable знову мертвий). Альтернатива —
        # явний прапорець-параметр на кшталт `send_response(..., cacheable=True)`
        # чи власний реєстр «шляхів із власним кешем» — але вона дублювала б
        # знання про те, ЩО САМЕ ставить свій Cache-Control, у другому місці,
        # яке довелось би синхронізувати руками. Обрано ризик мовчазного
        # відкату разом із цим коментарем як компенсацію: якщо колись побачите
        # цей рядок і `_headers_buffer` більше нема — перевірте руками, чи не
        # повернувся подвійний заголовок (issue Task 2, коміт bc56e67).
        buf = getattr(self, '_headers_buffer', [])
        if not any(h.lower().startswith(b'cache-control:') for h in buf):
            self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def _send_json(self, obj, status=200):
        try:
            body = json.dumps(obj, ensure_ascii=False).encode()
        except UnicodeEncodeError:
            # Самотній сурогат (`{"space": "\ud800"}` — валідний JSON, а в Python рядок, що не кодується в UTF-8) у
            # тексті відмови: без запасного шляху `.encode()` падав, і зʼєднання рвалось без відповіді. Екранування
            # (`\ud800`) віддається клієнтові як є; уся решта відповідей (живий UTF-8) іде першим шляхом без змін.
            body = json.dumps(obj, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    #: Відповідь цього запиту вже почата (рядок статусу пішов). Виставляє `send_response_only`;
    #: скидає `_guarded` на вході кожного запиту.
    _resp_started = False
    _successor = None       # 4d-4c: адреса наступника, коли запит прийшов на застарілий псевдонім `/api/gitlab-*`
    #: Тіло POST уже вичитане. Виставляє `do_POST` одразу після `rfile.read`; без нього
    #: центральна відмова ДО читання тіла лишила б його в буфері (RST замість відповіді).
    _body_read = False

    def send_response_only(self, code, message=None):
        # Сигнал «відповідь почата» саме тут, а не з `_headers_buffer`: після `flush_headers`
        # буфер порожній, тож «порожній» не значить «нічого не надіслано» — а друга відповідь
        # поверх першої зіпсувала б потік байтів. Через `send_response_only` проходить і
        # `send_response`, і `send_error`.
        super().send_response_only(code, message)
        self._resp_started = True

    def _space_error(self, status, code, error, **extra):
        """Центральна відмова простору: JSON із кодом замість обірваного зʼєднання.
        Відповідь уже почата — другої не шлемо, зʼєднання закриваємо. До читання тіла POST —
        тіло вичитуємо (див. `_body_read`)."""
        if self._resp_started:
            self.close_connection = True
            return
        if self.command == 'POST' and not self._body_read:
            self._drain_body()
        self._send_json({'ok': False, 'code': code, **extra, 'error': error}, status=status)

    def _guarded(self, run):
        """Обгортка `do_GET`/`do_POST`: чотири виняткові стани простору — одні й ті самі
        відповіді для КОЖНОГО маршруту, а не кожен обробник зі своїм `try`:

        | виняток                          | відповідь                                      |
        |----------------------------------|------------------------------------------------|
        | `NoTask` (просторів чи поточної задачі нема) | 404 `no-task` + `space` (id чи `null`) |
        | `SpaceUnavailable` (файл простору битий/нема) | 503 `space-unavailable` + `path`   |
        | `SpacesError` (реєстр не прочитати/не записати) | 503 `spaces-unreadable` / `spaces-unwritable` + `path` |
        | `AmbiguousTask` (id у двох просторах) | 409 `ambiguous-task`                        |
        | `deai_modules.ModuleError` (провайдер ролі, `call`, налаштування модуля) | `e.status` + `e.code`, без `ctx` |

        `ModuleError` кидають `provider()`, `module_ctx`, `published_root` і сам `call` — із багатьох
        маршрутів; відповідь одна: `{ok: false, code, error}` зі статусом ядра модулів (`deai_modules.STATUS`).
        Текст `e.message` ядро вже очистило від значень секретів і обрізало до 300 символів, тож `ctx` і
        налаштування у відповідь не потрапляють НІКОЛИ (ні `ctx`, ні `settings` тут не читаються).

        `finally` скидає простір запиту — захист для keep-alive (потік обробника живе довше за
        запит). Мутаційно він не доводиться: `_take_task` і так скидає простір першим рядком."""
        self._resp_started = False
        self._successor = None          # keep-alive: заголовок псевдоніма не переходить на наступний запит зʼєднання
        self._body_read = False
        try:
            return run()
        except spaces.NoTask as e:
            self._space_error(404, 'no-task', 'no task in this space', space=e.space)
        except SpaceUnavailable as e:
            feedback.record_error(self.path, e, code='space-unavailable')      # лише код: у тексті шляхи
            self._space_error(503, 'space-unavailable', str(e), path=e.path)
        except spaces.SpacesError as e:
            feedback.record_error(self.path, e, code=e.code)
            self._space_error(503, e.code, str(e), path=e.path)
        except spaces.AmbiguousTask as e:
            tid = e.args[0] if e.args else ''
            self._space_error(409, 'ambiguous-task',
                              f'task {tid!r} exists in several spaces — rename one of them')
        except deai_modules.ModuleError as e:
            if e.status >= 500:                                                # 4xx — очікувані відмови, не пишемо
                feedback.record_error(self.path, e, code=e.code)
            self._space_error(e.status, e.code, e.message)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            raise                                                              # клієнт обірвав зʼєднання: шум, у кільце не пишемо
        except Exception as e:  # noqa: BLE001
            feedback.record_error(self.path, e)                                # невідомий виняток: у кільце й далі, як було
            raise
        finally:
            spaces.clear_request_space()

    # Код відмови дерева → HTTP-статус; усе інше — 400. `stale` — 409 (панель
    # читає заново й повторює), `busy` — 503 (чужий писар тримає лок: повтор
    # виправить), `not-found` — 404 (ітерації чи вузла нема), `corrupt` — 500
    # (pages.json на диску не розбирається: це не помилка запиту, і повтор її не
    # виправить).
    _TREE_STATUS = {'stale': 409, 'busy': 503, 'not-found': 404, 'corrupt': 500}

    def _tree_error(self, e):
        """Відмова правил дерева — JSON із кодом, а не send_error: у send_error
        причина йде в рядок статусу latin-1, і українська назва правила
        впала б UnicodeEncodeError замість відповіді."""
        code = getattr(e, 'code', 'bad-request')
        self._send_json({'ok': False, 'error': str(e), 'code': code},
                        status=self._TREE_STATUS.get(code, 400))

    def _iteration_or_400(self, it):
        """Імʼя ітерації за правилом `NAME_RE` або None (JSON 400 `bad-iteration`
        уже надіслано). Одне місце для ВСІХ обробників сторінок: не-рядок (`5`,
        `null`, список) у `NAME_RE.match` кидав TypeError, і зʼєднання рвалось без
        відповіді. `fullmatch`, а не `match`: `$` у `^…$` пропускає імʼя з переносом рядка в кінці."""
        if not isinstance(it, str) or not NAME_RE.fullmatch(it):
            self._tree_error(pm.TreeError('bad-iteration', 'bad iteration'))
            return None
        return it

    def _ids_or_400(self, payload):
        """`ids` запиту — непорожній список рядків, або None (JSON 400 `bad-ids`
        уже надіслано). Форма — вхід, а не правило дерева, але відповідаємо так
        само JSON-ом: клієнт розбирає тіло відмови однаково. Не-рядок у списку
        інакше впав би TypeError у `set(ids)` (500)."""
        ids = payload.get('ids')
        if (not isinstance(ids, list) or not ids
                or not all(isinstance(i, str) for i in ids)):
            self._tree_error(pm.TreeError('bad-ids', 'ids must be a non-empty list of ids'))
            return None
        return ids

    def _legacy_args(self, payload, need_page=True):
        """Вступ старих обробників сторінок: `(task, idir, it, page)` або None
        (JSON 400 уже надіслано). `page` — порожній рядок, коли `need_page=False`."""
        it = self._iteration_or_400(payload.get('it'))
        if it is None:
            return None
        page = payload.get('page', '')
        if need_page and not page:
            self._tree_error(pm.TreeError('bad-page', 'page is required'))
            return None
        _, task = self._current_task()
        return task, _iter_dir(task, it), it, page

    def _tree_op(self, payload, change, msg, after=None, need_rev=True):
        """Один шлях для всіх нових дій над деревом: лок + rev + validate +
        автокоміт. `change(pages)` → `(дерево, extra)`; повертає
        `{'extra', 'rev', 'idir'}` або None, якщо відповідь (помилку) вже надіслано.

        `need_rev` — ключ `rev` (рядок, може бути порожнім) обовʼязковий, інакше
        400 `missing-rev`: клієнт, що забув rev, мовчки втрачав би захист від
        чужої правки. Порожній рядок — законний rev («файла нема»).

        `after(extra)` іде ПІД тим самим локом одразу після запису (див.
        `pm.mutate`): видалення тек сторінок тут не дає паралельному `page-new`
        з тим самим slug втратити щойно створену теку. rev теж знімає `mutate`
        під локом (`with_rev`), а не окремий `pages_rev` після виходу з нього —
        інакше сусідній запис між ними дав би клієнту відбиток стану, якого він
        не бачив. Коміт у git — лише коли `mutate` щось записав: порожній рух
        інакше підмів би в коміт усе стороннє під повідомленням, якого не робили."""
        it = self._iteration_or_400(payload.get('it'))
        if it is None:
            return None
        if need_rev and not isinstance(payload.get('rev'), str):
            self._tree_error(pm.TreeError('missing-rev', 'rev (string) is required'))
            return None
        _, task = self._current_task()
        idir = _iter_dir(task, it)
        try:
            extra, new_rev, changed = pm.mutate(idir, change, rev=payload.get('rev'),
                                                after=after, with_rev=True)
        except pm.TreeError as e:
            self._tree_error(e)
            return None
        if changed:
            # автокоміт — ПОЗА локом: git і пуш повільні, а лок тримає писарів
            git_autocommit(task['dir'], msg)
        return {'extra': extra, 'rev': new_rev, 'idir': idir}

    #: Задача, названа ЗАПИТОМ (`X-Canvas-Task` чи `/t/<id>/`); None — поточна
    #: машини. Ставиться на вході КОЖНОГО запиту (`_take_task`): обробник живе,
    #: поки живе зʼєднання, і задача першого запиту не сміє прилипнути до другого.
    _task_override = None

    #: `/t/<id>/решта` → id і решта шляху (з запитом). Префікс, а не `?task=`:
    #: `?task=` уже зайнятий `/api/task-thumb`, а корене-абсолютні ассети
    #: Angular-збірки (`/assets/…`) заголовка не несуть — лише Referer, у якому
    #: префікс і лежить.
    _TASK_PREFIX = re.compile(r'^/t/([^/?#]+)(/.*)$')

    #: Маршрути РЕЄСТРУ (задач і просторів): діють на машину (`current`, список задач,
    #: список просторів), а не на дані якоїсь задачі. Заголовок `X-Canvas-Task` тут не
    #: береться й не перевіряється: `task-new` із заголовком на ЩЕ НЕ зареєстрований id давав
    #: «невідома задача», хоча саме вона й створюється; префіксна форма
    #: (`/t/x/api/task-new`) безглузда й відхиляється. Те саме стосується `/api/space*`.
    #: Модулі (етап 2а): `/api/modules`, `/api/module-*` (з 3c і `module-trust`/`module-untrust`), `/api/ds-tokens` — теж реєстрові: простір — параметр
    #: `space`, не задача. Точна відповідність (шлях без query), КОЖЕН маршрут окремо: широкий префікс
    #: `/api/module` зловив би будь-який майбутній маршрут.
    _REGISTRY_ROUTES = ('/api/task-new', '/api/task-switch', '/api/task-tags', '/api/task-rename', '/api/task-delete',
                        '/api/task-restore', '/api/task-purge', '/api/spaces',
                        '/api/space-peek', '/api/space-new', '/api/space-update', '/api/space-tool',
                        '/api/space-switch',
                        '/api/modules', '/api/module-ext', '/api/module-enable', '/api/module-disable',
                        '/api/module-settings', '/api/module-check', '/api/ds-tokens',
                        '/api/module-trust', '/api/module-untrust', '/api/agents-md')

    #: Маршрути МАШИНИ (оновлення, відгук): потрібні саме тоді, коли щось зламано (порожня машина, битий реєстр, нечитабельний
    #: `tasks.json`). `_take_task` для них НЕ фіксує простір і не читає задач; префіксна форма `/t/<id>/api/…` відхиляється 400.
    #: Обробники самі й тотально збирають контекст (простір, задача). Точна відповідність (шлях без query), кожен маршрут окремо.
    _MACHINE_ROUTES = ('/api/update', '/api/update-check', '/api/update-apply', '/api/update-notes',
                       '/api/feedback', '/api/feedback-preview', '/api/claude-statuses')

    def _pin_current_space(self):
        """Не названа задача: простір запиту — поточний простір машини НА ВХОДІ. Запит дочитує
        його, навіть коли хтось перемкне поточний посеред обробки (друге вікно канваса, агент).

        Реєстр не прочитати чи не записати (міграція): API-запит НЕ виконується — `SpacesError`
        летить до центрального обробника (503). Без зафіксованого простору обробник, що дійшов би до мережі, ходив би назовні при битому реєстрі.
        Єдиний виняток — статика UI (`/app/*` та все, що не з `HANDLED_PREFIXES`): вона не читає
        задач, і мусить віддатись, щоб UI показав смугу помилки; простір лишається
        незафіксованим, а перший же `load_tasks()` (якщо він колись буде) підніме ту саму помилку."""
        try:
            spaces.set_request_space(spaces.current_id() or '')
        except spaces.SpacesError:
            if self.path.startswith(HANDLED_PREFIXES) and not self.path.startswith('/app'):
                raise

    def _take_task(self):
        """Вхід запиту: зняти з `self.path` префікс `/t/<id>/`, прочитати
        `X-Canvas-Task`, перевірити, ЗАФІКСУВАТИ ПРОСТІР запиту. False — відповідь (404 JSON
        із назвою) уже надіслано, далі обробляти не треба.

        Префікс сильніший за заголовок: він у самому URL і видний у логах.
        Невідома задача — 404, а НЕ мовчазний відкат на поточну (див. `task_for`);
        так само задача, якої на цій машині нема (є в реєстрі, теки нема).
        Порожній заголовок — 400: «назва є, але порожня» не те саме, що «назви
        нема», а мовчки читати його як «нема» означало б знову бити в поточну.

        Простір запиту (`spaces`, `threading.local`): названа задача — простір, де вона є
        (`find_task`; дубль у двох просторах — `AmbiguousTask`, а помилка реєстру —
        `SpacesError` летять до центрального обробника, див. `_guarded`); не названа — поточний
        простір машини на вході (`_pin_current_space`).
        Лише `do_GET` і `do_POST` (див. `Routed`); `do_HEAD` від
        `SimpleHTTPRequestHandler` до `_current_task` не доходить."""
        self._task_override = None
        # ПЕРШИЙ рядок: обробник живе, поки живе keep-alive зʼєднання, і той самий потік
        # веде кілька запитів поспіль — простір попереднього не сміє прилипнути до цього.
        spaces.clear_request_space()
        m = self._TASK_PREFIX.match(self.path)
        if m:
            tid = unquote(m.group(1))
            self.path = m.group(2)
            # Інтерфейс канваса не привʼязаний до задачі: `/t/beta/app/` відкрив би
            # той самий канвас ПОТОЧНОЇ задачі під адресою beta, тобто адреса
            # брехала б. Лише префіксна форма: заголовок до статики не доходить.
            if self.path == '/app' or self.path.startswith('/app/'):
                self._drain_body()
                self._send_json({'ok': False, 'error': 'інтерфейс канваса не привʼязаний '
                                 'до задачі: відкривай /app/ без префікса /t/<id>/'},
                                status=404)
                return False
            if self.path.split('?')[0] in self._REGISTRY_ROUTES:
                self._drain_body()
                self._send_json({'ok': False, 'error': 'реєстр задач не привʼязаний до '
                                 'задачі: звертайся до /api/task-new, /api/task-switch, '
                                 '/api/space*, /api/modules, /api/module-* і /api/ds-tokens '
                                 'без префікса /t/<id>/'}, status=400)
                return False
            if self.path.split('?')[0] in self._MACHINE_ROUTES:
                self._drain_body()
                self._send_json({'ok': False, 'error': 'маршрути машини (оновлення, відгук, статуси Claude) '
                                 'не привʼязані до задачі: звертайся до них без префікса /t/<id>/'}, status=400)
                return False
        else:
            if self.path.split('?')[0] in self._MACHINE_ROUTES:
                return True          # машина, не простір: без `_pin_current_space` і без читання задач (див. `_MACHINE_ROUTES`)
            if self.path.split('?')[0] in self._REGISTRY_ROUTES:
                self._pin_current_space()
                return True          # заголовок тут не діє (див. `_REGISTRY_ROUTES`)
            raw = self.headers.get('X-Canvas-Task')
            if raw is None:
                self._pin_current_space()
                return True
            tid = raw.strip()
            if not tid:
                self._drain_body()
                self._send_json({'ok': False, 'error': 'empty X-Canvas-Task'}, status=400)
                return False
        sp = spaces.find_task(tid)
        if sp is None:
            # Названа задача могла лежати в старому файлі, який не читається (простору з нього
            # нема): «невідома» збрехало б, тож 503 з назвою файла (центральний обробник).
            raise_if_legacy_unreadable()
            self._drain_body()
            self._send_json({'ok': False, 'error': f'unknown task: {tid}'}, status=404)
            return False
        spaces.set_request_space(sp['id'])
        try:
            task_for(load_tasks(), tid)
        except TaskNotHere:
            self._drain_body()
            self._send_json({'ok': False, 'error': f'task not on this machine: {tid}'},
                            status=404)
            return False
        except UnknownTask:
            # Вилучили між `find_task` і цим читанням: так само «невідома».
            self._drain_body()
            self._send_json({'ok': False, 'error': f'unknown task: {tid}'}, status=404)
            return False
        self._task_override = tid
        return True

    def _drain_body(self):
        """Вичитати тіло POST, яке відмова на вході лишила б непрочитаним: закрити
        зʼєднання з непрочитаним у буфері — це RST, і клієнт міг би не побачити
        навіть самої відмови (ConnectionResetError замість 404/403). Стеля 1 МіБ:
        більшого тіла від локального клієнта не чекаємо."""
        if self.command != 'POST':
            return
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            return
        if n > 0:
            self.rfile.read(min(n, 1 << 20))

    def _task_prefix(self):
        """Префікс `/t/<id>` для адрес, що ми віддаємо клієнтові (`<base>`, `--url`
        зʼємки): задачу НАЗВАНО запитом — отже й посилання в ньому мусять її
        називати, бо ассети сторінки та зворотні виклики дитини заголовка не несуть
        і без префікса пішли б у ПОТОЧНУ. Порожній — задачу не названо."""
        if self._task_override is None:
            return ''
        return f'/t/{quote(self._task_override, safe="")}'

    def _current_task(self):
        return task_for(load_tasks(), self._task_override)

    # ---------- GET ----------

    def do_GET(self):
        if self.path.split('?')[0] == '/api/update':
            self._send_json(_updater().status())
            return
        if self.path.split('?')[0] == '/api/update-notes':
            # ⛔ GET, що може піти в мережу (`fetch` тега): чужа сторінка (`<img src=…>`) не сміє його смикати. `Sec-Fetch-Site` cross-/same-site
            # або чужий `Origin` → 403 до будь-якого `git`; без обох заголовків (curl, старі рушії) — пускаємо.
            if self.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site') or not _local_origin(self.headers.get('Origin')):
                self._send_json({'ok': False, 'error': 'foreign origin'}, status=403)
                return
            self._send_json(_updater().notes())
            return
        if self.path.split('?')[0] == '/api/spaces':
            # Шар вимкнено → `{current: null, spaces: [], off: true}` (рішає `spaces.listing`).
            # Кожен запис ще й несе `capabilities` (див. `spaces_listing`).
            self._send_json(spaces_listing())
            return
        if self.path.split('?')[0] == '/api/modules':
            self._modules_get()
            return
        if self.path.split('?')[0] == '/api/module-ext':
            self._module_ext_get()
            return
        if self.path.split('?')[0] == '/api/module-trust':
            self._module_trust_get()
            return
        if self.path.split('?')[0] == '/api/agents-md':
            self._agents_md(parse_qs(urlparse(self.path).query).get('space', [None])[0], False)
            return
        if self.path.split('?')[0] == '/api/ds-tokens':
            self._ds_tokens_get()
            return
        if self.path.split('?')[0] == '/api/space-peek':
            self._send_json(spaces.peek(parse_qs(urlparse(self.path).query).get('path', [''])[0]))
            return
        if self.path == '/api/task':
            tid, task = self._current_task()
            meta = load_meta(task)
            sp = spaces.active_space()
            try:
                pw, pw_err = preview_password(task, sp), None
            except deai_modules.ModuleError as e:      # секрети не читаються: екран живий, але пароль не вгадуємо
                pw, pw_err = None, e.code
            out = {'id': tid, 'title': task.get('title', tid),
                   'jira': task.get('jira'),
                   'tags': task_tags(task, sp),
                   'track': tracks.of_task(task),
                   # Простір задачі (`describe`: id, name, color, path, legacy,
                   # `capabilities`; `null` — шар вимкнено) і канал коментарів. Канал
                   # лише з інтеграціями: без них командних коментарів нема, і скіл
                   # `comments` не мусить вгадувати це зі старого файла.
                   'space': space_view(sp),
                   'comment_channel': _task_comment_channel(sp, task, tid),
                   'iterations': task_api_iterations(meta),
                   # Ключ ЦІЄЇ машини: браузер не знає git-конфіга, а
                   # «своя/чужа» ітерація рахується саме по ньому.
                   # Імʼя окремо не шлемо — воно вже в кожному записі.
                   'my_key': machine_identity()[1],
                   'publish_url': meta.get('publish_url'),
                   'published_at': meta.get('published_at'),
                   # пароль потрібен канвасу, щоб зібрати посилання
                   # «#k=<код>&p=<сторінка>» для менеджера; він і так
                   # лежить у коді опублікованої сторінки
                   'preview_password': pw,
                   # Свій пароль задачі чи спільний типовий — підпис у
                   # дропдауні публікації не сміє плутати одне з іншим.
                   'preview_password_custom': bool(task.get('preview_password')),
                   # Чи ЗІБРАНЕ превʼю вже з цим паролем (на кожній
                   # сторінці). `stale` — «Копіювати посилання» дало б
                   # менеджеру ключ, який превʼю не відкриває. Публікує
                   # модуль — `state: 'module'` (див. `task_preview_gate`).
                   'preview_gate': (task_preview_gate(task, pw, sp) if pw_err is None
                                    else {'state': 'none', 'stale': 0, 'ungated': 0, 'inner_stale': 0, 'pages': 0})}
            if pw_err:
                out['preview_password_error'] = pw_err
            # Остання ЛОКАЛЬНА публікація модуля (`{module, path, published_at}`) — лише коли вона була:
            # відповідь простору з ЛІГА лишається такою, якою була.
            if meta.get('publish_local'):
                out['publish_local'] = meta['publish_local']
            # Остання публікація модуля «за адресою» (`{module, state, published_at}`) і поля для посилання
            # (`publish_gate`, `publish_share_url` — лише коли публікує такий модуль, див. `task_publish_share`).
            # `gate_hash` (відбиток пароля, лише для порівняння на сервері) у відповідь не йде.
            remote = meta.get('publish_remote')
            if remote:
                out['publish_remote'] = ({k: v for k, v in remote.items() if k != 'gate_hash'}
                                         if isinstance(remote, dict) else remote)
            out.update(task_publish_share(sp, meta))
            self._send_json(out)
            return
        if self.path == '/api/teams-mute':
            resolved, err = _notify_route_gate()
            if err is None and resolved[1] is None:
                self._send_json(_notify_off_body(), status=409)
                return
            tid, task = self._current_task()
            channel = _comment_channel_in(spaces.active_space(), task, tid)
            try:
                if err is not None:
                    raise err
                self._send_json(notify.mute_view(channel, notify_call('mute_state', resolved=resolved), mute_signature()))
            except deai_modules.ModuleError as e:
                # «Не знаю» — це не «увімкнено»: перемикач мусить показати невідомість.
                self._send_json({'channel': channel, 'error': (e.message or e.code)[:200]})
            except (OSError, ValueError) as e:
                self._send_json({'channel': channel, 'error': str(e)[:200]})
            return
        if self.path.split('?')[0] == '/api/tasks':
            every = parse_qs(urlparse(self.path).query).get('all', [''])[0] == '1'
            cfg = None
            try:
                cfg = load_tasks()
            except spaces.NoTask:
                # Просторів нема зовсім: це порожній СПИСОК, а не відмова — UI саме за
                # ним іде на привітання. Єдина задача (`/api/task`) лишається 404 `no-task`.
                if not every:
                    self._send_json({'current': None, 'tasks': [], 'space': None})
                    return
            except SpaceUnavailable:
                if not every:
                    raise
            # `?all=1` (dev-pipeline питає «задача вже є?») від простору запиту НЕ залежить: його
            # нема чи файл битий — рядки решти просторів усе одно віддаються, а `current` —
            # `null`. `space` — простір ЗАПИТУ, і береться ПІСЛЯ обходу (словник рахується
            # зліва направо): обхід мусить його повернути.
            self._send_json({'current': cfg.get('current') if cfg is not None else None,
                             'tasks': _all_space_task_rows() if every else _task_rows(cfg),
                             'space': space_view(spaces.active_space())})
            return
        if self.path.split('?')[0] == '/api/tasks-overview':
            q = parse_qs(urlparse(self.path).query)
            try:
                cfg = load_tasks()
            except spaces.NoTask:
                self._send_json({'current': None, 'mine': [], 'team': None, 'tracker': None, 'trash': [], 'space': None})
                return
            refresh = q.get('refresh', [''])[0] == '1'
            # Статуси трекера (4c-2) — НЕЗАЛЕЖНО від вкладки «Команда»: ключі «Моїх» задач, свій кеш і лок. Збій рішення ролі
            # (зламаний власний модуль «на папері») — плашка з причиною, а не 500 і не мовчання; `SpacesError` — в обробник маршруту.
            try:
                trk_resolved = tracker_resolve()
            except deai_modules.ModuleError as e:
                trk = ({}, (e.message or e.code)[:200], None)
            else:
                trk = tracker_snapshot(tracker.keys_of(cfg.get('tasks')), refresh=refresh, resolved=trk_resolved)
            # Вкладка «Команда» є, коли простір має постачальника ролі `dashboard` (4c-1; було — прапорець `integrations`: для ЛІГИ
            # те саме, бо вона має `'legacy'`). `SpacesError` тут — як і раніше (обробник маршруту).
            try:
                resolved = team_resolve()
            except deai_modules.ModuleError as e:
                # ⛔ Збій рішення ролі (зламаний власний модуль «на папері», `space.json` не читається) — НЕ «нікого»: вкладка
                # лишається, а плашка називає причину; `team: null` мовчки сховав би вкладку, і людина не знала б, чому її нема.
                out = tasks_overview(cfg, ([], (e.message or e.code)[:200]), tracker=trk)
            else:
                if resolved[1] is None:
                    # Постачальника нема: запиту немає, `team: null` (UI ховає вкладку «Команда»). `tasks_overview` чиста
                    # збірка — порожні рядки їй безпечні.
                    out = {**tasks_overview(cfg, ([], None), tracker=trk), 'team': None}
                else:
                    rows, err, rows_at = team_snapshot(refresh=refresh, resolved=resolved)
                    out = tasks_overview(cfg, (rows, err), rows_at=rows_at, tracker=trk)
            out['trash'] = _trash_rows(cfg)      # кошик простору запиту (етап Д): одним місцем для всіх гілок вище
            self._send_json({'current': cfg.get('current'), **out,
                             'space': space_view(spaces.active_space())})
            return
        if self.path.split('?')[0] == '/api/task-thumb':
            self._task_thumb()
            return
        if self.path.startswith('/api/local-comments'):
            self._local_comments_get()
            return
        if self.path.startswith('/api/tuner'):
            self._tuner_get()
            return
        if self.path.startswith('/api/it-stamp'):
            # Опитування вкладки раз на 2 с — без лока й без запису (див. коментар
            # у /api/iteration-pages: лок зсуває mtime теки).
            q = parse_qs(urlparse(self.path).query)
            it = self._iteration_or_400(q.get('it', [''])[0])
            if it is None:
                return
            _, task = self._current_task()
            idir = _iter_dir(task, it)
            here = os.path.isdir(idir)
            self._send_json({'it': it, 'stamp': _content_mtime(idir) if here else 0,
                             'recent': recent_pages(idir) if here else []})
            return
        if self.path == '/api/claude-statuses':
            with CLAUDE_LOCK:
                beats = dict(CLAUDE_BEATS)
            self._send_json({'tasks': claude_views(beats, time.time())})
            return
        if self.path == '/api/claude-status':
            tid, task = self._current_task()
            with CLAUDE_LOCK:
                beats = dict(CLAUDE_BEATS)
            self._send_json(claude_view(beats, time.time(), tid, (task.get('jira'),)))
            return
        if self.path.startswith('/api/iteration-pages'):
            q = parse_qs(urlparse(self.path).query)
            it = self._iteration_or_400(q.get('it', [''])[0])
            if it is None:
                return
            _, task = self._current_task()
            idir = _iter_dir(task, it)
            # Неіснуюча ітерація — порожньо, як було (а не 404).
            if not os.path.isdir(idir):
                self._send_json({'it': it, 'pages': [], 'rev': ''})
                return
            # ⛔ БЕЗ pages_lock. Лок створює `.pages.lock` у теці ітерації, а це
            # піднімає її mtime — за ним автосинк вибирає робочу ітерацію, і
            # простий перегляд тижневої ітерації робив би її «свіжою». Він же падає
            # PermissionError на теці «лише для читання» і змушує читача чекати
            # писаря (чи rmtree). Лок тут і не потрібен: `atomic_write_json`
            # підміняє файл цілком, тож одне читання — узгоджений знімок, а
            # `read_pages_rev` бере і дерево, і rev з тих самих байтів.
            try:
                pages, rev = pm.read_pages_rev(idir)
            except pm.TreeError as e:     # corrupt: pages.json не розбирається
                self._tree_error(e)
                return
            self._send_json({'it': it, 'pages': pages, 'rev': rev})
            return
        # Точне порівняння шляху без query, а не startswith: широкий префікс зловив
        # би будь-який майбутній /shots-* і став би тихим перехопленням.
        if self.path.split('?')[0] == '/shot':
            self._shot()
            return
        if self.path.split('?')[0] == '/shot-geo':
            self._shot_geo()
            return
        if self.path.split('?')[0] == '/api/comment-config':
            self._comment_config()
            return
        if self.path.split('?')[0] == '/api/comment-news':
            self._comment_news()
            return
        if self.path.split('?')[0] == '/api/shots':
            self._shots_manifest()
            return
        if self.path.split('?')[0] == '/api/shoot-progress':
            self._shoot_progress()
            return
        if self.path.split('?')[0] == '/api/flow':
            self._flow_get()
            return
        if self.path.startswith('/commented'):
            self._commented()
            return
        if self.path.startswith('/comments'):
            self._comments()
            return
        # `/api/vcs-status` — нова адреса того самого обробника; `/api/gitlab-status` лишається псевдонімом (Stop-хук dev-pipeline,
        # зовнішні скрипти): псевдоніми до 1.0 із `Deprecation`; видалення — після перемикання скіла dev-pipeline.
        if self.path.startswith('/api/gitlab-status'):
            self._successor = '/api/vcs-status'
            self._gitlab_status()
            return
        if self.path.startswith('/api/vcs-status'):
            self._gitlab_status()
            return
        super().do_GET()

    def _commented(self):
        """Ітерація макета з comment-layer (локально — канал internal)."""
        q = parse_qs(urlparse(self.path).query)
        it = q.get('it', [''])[0]
        if not NAME_RE.match(it):
            self.send_error(400, 'bad iteration')
            return
        bare = q.get('bare', ['0'])[0] == '1'
        host = q.get('host', ['0'])[0] == '1'          # 0.26.0: оболонка завжди додає; сторінка без нього — як була
        if self._task_override is not None and not bare:
            # Коментатор пише піни на `/api/local-comments` і тягне бандли з
            # `/app/vendor` БЕЗ префікса — тобто пін, поставлений на сторінці
            # названої задачі, ліг би в `.dc-local-comments.json` ПОТОЧНОЇ. Чесніше
            # відмовити, ніж віддати сторінку з коментатором, що пише не туди.
            self._send_json({'ok': False,
                             'error': 'коментування під названою задачею не підтримується '
                                      '— коментуй у канвасі (вікно поточної задачі)'},
                            status=400)
            return
        tid, task = self._current_task()
        page = _pick_page(task, it, q.get('page', [''])[0])
        if page is None:
            self.send_error(404, 'no pages in iteration')
            return
        rel = pm.page_rel(page)
        if rel and not NAME_RE.match(rel):
            self.send_error(400, 'bad page')
            return
        page_file = os.path.join(_iter_dir(task, it), rel, 'index.html')
        if not os.path.isfile(page_file):
            self.send_error(404, 'page not found')
            return
        with open(page_file, encoding='utf-8') as f:
            html = f.read()
        # Під названою задачею `<base>` несе префікс: відносні ассети сторінки
        # інакше йшли б у `/it-assets/` ПОТОЧНОЇ задачі (корене-абсолютні й так
        # рятує Referer, див. `Routed._referer_context`).
        base = (f'http://{self.headers.get("Host", "")}{self._task_prefix()}'
                f'/it-assets/{it}/{rel + "/" if rel else ""}')
        html, n = re.subn(r'<head([^>]*)>', rf'<head\1><base href="{base}">',
                          html, count=1, flags=re.I)
        if not n:
            html = f'<base href="{base}">' + html
        # bare=1 — чистый макет без comment-layer (для замороженного обзору на холсте)
        if not bare:
            origin = f'http://{self.headers.get("Host", "localhost:8765")}'
            ch = q.get('ch', ['local'])[0]
            # Хто дає командні коментарі простору: `Module` (роль `comments`; у ЛІГИ — вбудований
            # `supabase-comments`, `comments_route`) чи `None` (нікого — лише локальні). `team` — чи є вкладка «Команда» й канал `project`
            # узагалі. Без постачальника (простір без інтеграцій і без модуля) канал Supabase (і CDN із supabase-js)
            # недоступний, тож `ch=project` ПОНИЖУЄТЬСЯ до локального; вкладок аудиторій нема зовсім — контракт
            # коментатора «нема `audiences` → нема рядка» (з одним «Клод» перемикач був би порожнім жестом, а «Команда»
            # вела б у відмову).
            # Простір СТОРІНКИ для `sp=` у URL інспектора (етап 2а, Task 7). Це простір ЗАДАЧІ, чию
            # сторінку віддаємо: `task` прочитано з файла задач простору запиту (`_current_task` →
            # `load_tasks` → `spaces.active_space()`), а під НАЗВАНОЮ задачею сторінка з коментатором
            # не віддається взагалі (400 вище) — тож розбіжності між «простором запиту» і «простором
            # задачі» тут бути не може. Беремо ОДИН раз і передаємо в усе: постачальник коментарів, їхня
            # конфігурація й канал, обидва канали розмітки: запит зафіксував простір на вході, а реєстр
            # до рендера міг перемкнутись.
            page_space = spaces.active_space()
            prov, prov_err = comments_provider(page_space)
            team = prov is not None
            local_key = f'{tid}/local' + ('' if page.get('id') == 'main' else f'/{page["id"]}')
            if host and (prov is not None or prov_err is not None):
                # Б2 (0.27.0): робоче місце з командним постачальником — ОДИН шар на обидва сховища; `ch` тут не діє.
                # Постачальник не вирішився чи конфіг не зібрався — комбінований сніпет із причиною: локальні працюють, а
                # панель оболонки каже, чому нема командних (поправка 4 плану Б2).
                mod, module_cfg, team_err = None, None, None
                if prov_err is not None:
                    team_err = f'командні коментарі не піднялись ({prov_err.code})'
                else:
                    try:
                        mod, cctx, route_channel = comments_route(page_space, prov)
                        channel = route_channel(task, tid)        # ⛔ канал — ДО коду модуля: непридатний id задачі не доходить до `client_config`
                        module_cfg = {**deai_modules.comments_client(page_space, mod, cctx), 'channel': channel}
                    except deai_modules.ModuleError as e:
                        team_err = f'командні коментарі не піднялись ({e.code})'
                html = inject_dual_comment_layer(
                    html, f'{origin}/app/vendor', module_client_urls(mod, page_space) if module_cfg else [],
                    module_cfg or {}, f'{origin}/api/local-comments', local_key,
                    version=pm.page_version_tag(it, page), team_error=team_err,
                    profile=task_ds(task, page_space), space=page_space)
            else:
                notice = None            # код відмови, який людині ПОКАЗУЄМО на локальній сторінці (див. нижче)
                if ch == 'project' and not team:
                    ch = 'local'
                    notice = prov_err.code if prov_err is not None else None
                # version МУСИТЬ збігатися з publish-конвенцією (iter_num: it1→"1"),
                # інакше піни, народжені у опублікованому/проєктному перегляді (bornV=1),
                # не лягають на ітерацію в канвасі (appVersion "it1" ≠ bornV 1).
                ver = pm.page_version_tag(it, page)
                module_cfg = mod = None
                if ch == 'project' and prov is not None:
                    # Командний канал веде модуль ролі `comments`: власний модуль простору або (ЛІГА) вбудований
                    # `supabase-comments` з конфігом установки й каналом `comment_channel` (`comments_route`). Відмова — не
                    # 5xx: сторінка лишається РОБОЧОЮ (локальні коментарі) і каже, чому нема командних.
                    try:
                        mod, cctx, route_channel = comments_route(page_space, prov)
                        channel = route_channel(task, tid)        # ⛔ канал — ДО коду модуля (як у `publish_comments`)
                        module_cfg = {**deai_modules.comments_client(page_space, mod, cctx), 'channel': channel}
                    except deai_modules.ModuleError as e:
                        # Постачальник є, а його конфіг не піднявся: сторінка локальна, і вкладки «Команда» на ній нема —
                        # вона вела б у ту саму відмову (контракт коментатора: «нема `audiences` → нема рядка»).
                        ch, notice, team = 'local', e.code, False
                if module_cfg is not None:
                    # `inspector=True`: аудиторія коментарів змінює, КОМУ їде фідбек, а не те, чиїми очима дивляться на
                    # макет — це та сама локальна машина дизайнера. До 02.09.2026 інспектор тут був мертвий, і кнопка в смузі
                    # тихо нічого не робила (виміряно в браузері).
                    html = inject_module_comment_layer(
                        html, f'{origin}/app/vendor', module_client_urls(mod, page_space), module_cfg, version=ver,
                        inspector=True, audiences=team, profile=task_ds(task, page_space), space=page_space, host=host)
                else:
                    # режим «Локальні · мені» (дефолт): фідбек Claude у локальний файл, НЕ Supabase
                    html = inject_local_comment_layer(
                        html, f'{origin}/api/local-comments', local_key,
                        f'{origin}/app/vendor', version=ver, audiences=team,
                        profile=task_ds(task, page_space), space=page_space, host=host)
                    if notice:
                        html = inject_comment_notice(html, f'командні коментарі не піднялись ({notice}), показано локальні')
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _task_thumb(self):
        """Кадр картки екрана «Задачі»: останній кадр ОБРАНОЇ задачі (не поточної).
        Id — `fullmatch`: простий `match` пропустив би хвостовий `\\n`. Тільки задачі
        з `tasks.json`: відкрити так довільну теку диска не вийде."""
        q = parse_qs(urlparse(self.path).query)
        tid, ver = q.get('task', [''])[0], q.get('v', [''])[0]
        if not NAME_RE.fullmatch(tid):
            self.send_error(400, 'bad task')
            return
        cfg = load_tasks()
        if q.get('trash', [''])[0] == '1':
            # Етап Д: кадр задачі з кошика — з її теки В КОШИКУ. Лише записи `trash` цього простору: довільної теки так не відкрити.
            rec = task_trash.records(cfg).get(tid)
            td = rec.get('trashDir') if rec else None
            task = ({**rec['entry'], 'dir': td}
                    if isinstance(td, str) and td and task_trash.inside_trash(td) else None)
        else:
            task = cfg.get('tasks', {}).get(tid)
        found = task_thumb_path(task) if isinstance(task, dict) else None
        if not found:
            self.send_error(404, 'no thumb')
            return
        try:
            with open(found[0], 'rb') as f:
                body = f.read()
        except OSError:
            self.send_error(404, 'no thumb')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'image/webp')
        self.send_header('Content-Length', str(len(body)))
        # `v` — хеш байтів кадру (його кладе в URL `tasks_overview`): різні байти —
        # різний URL, тож кеш вічний, але ⛔ лише коли `v` збігається з ПОТОЧНИМ
        # sha: після перезйомки старий `v` отримав би нові байти під вічним кешем.
        # Без `v` чи з чужим — `no-cache`. `private` — не для спільних проксі.
        self.send_header('Cache-Control', 'private, max-age=31536000, immutable'
                         if ver and ver == found[1] else 'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def _shot(self):
        """Кадр вузла з теки ітерації. Тільки .webp, тільки всередині задачі."""
        q = parse_qs(urlparse(self.path).query)
        it, node = q.get('it', [''])[0], q.get('node', [''])[0]
        if not NAME_RE.match(it) or not SHOT_RE.match(node):
            self.send_error(400, 'bad shot')
            return
        _, task = self._current_task()
        target = _shot_file(task, it, node)
        # NAME_RE вже не пускає '/' і '..'; realpath — другий замок (див. `_shot_file`)
        if target is None:
            self.send_error(404, 'no shot')
            return
        with open(target, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'image/webp')
        self.send_header('Content-Length', str(len(body)))
        # Кадр НЕЗМІННИЙ під своїм ключем, тому кеш вічний. Ключ у `<img>` рахує
        # `shotVersion` (app/flow-model.js), і несе він хеш САМИХ БАЙТІВ кадру
        # (`sha` в манифесті) — інші дві складові ключа для цього не годяться:
        # `stamp` це хеш ДЖЕРЕЛ (перезнім при незмінних файлах його не рухає), а
        # `capturedAt` має точність до ХВИЛИНИ.
        # ⚠️ Формулювання тут двічі було неправдою, і другий раз тонкою.
        # Спершу писалось, що досить `stamp`. Потім — що `capturedAt` знімає
        # причину, через яку тут стояв `no-store`: насправді він лише ЗВУЗИВ
        # вікно з «назавжди» до «в межах хвилини», тобто рівно до того вікна, у
        # яке лягає ручна перезйомка («Перезняти» → кадр битий → «Перезняти» ще
        # раз). Причину знімає саме хеш байтів: різні байти = різний URL, і це
        # твердження вже не залежить від годинника.
        self.send_header('Cache-Control', 'public, max-age=31536000, immutable')
        self.end_headers()
        self.wfile.write(body)

    def _shot_geo(self):
        """Геометрія кадру (T-45): де на знімку лежить кожен елемент сторінки,
        щоб піни сіли на «Огляді» туди ж, куди в живому виді. Ті самі два замки,
        що в `_shot`: імʼя за `SHOT_RE` і realpath усередині теки кадрів."""
        q = parse_qs(urlparse(self.path).query)
        it, node = q.get('it', [''])[0], q.get('node', [''])[0]
        if not NAME_RE.match(it) or not SHOT_RE.match(node):
            self.send_error(400, 'bad geo')
            return
        _, task = self._current_task()
        base = os.path.realpath(os.path.join(_iter_dir(task, it), 'shots'))
        target = os.path.realpath(os.path.join(base, node + '.geo.json'))
        if not target.startswith(base + os.sep) or not os.path.isfile(target):
            self.send_error(404, 'no geo')
            return
        with open(target, 'rb') as f:
            body = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        # Як кадр: під ключем версії (`v` = sha кадру) вміст незмінний — кеш
        # вічний. Без `v` ключ нічого не каже про вміст, і вічний кеш віддавав би
        # стару геометрію після перезйомки.
        self.send_header('Cache-Control',
                         'public, max-age=31536000, immutable' if q.get('v', [''])[0] else 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _comment_config(self):
        """Канал коментарів для оболонки — режим «полотно» comment-layer на
        «Огляді» (T-45). Рівно той вибір, що `_commented` робить для рамки:
        «Огляд» і живий вид мусять писати в ОДНЕ місце, інакше пін, лишений на
        полотні, у живому виді не знайшовся б."""
        q = parse_qs(urlparse(self.path).query)
        ch, it = q.get('ch', ['local'])[0], q.get('it', [''])[0]
        if ch not in ('local', 'project') or not NAME_RE.match(it):
            self.send_error(400, 'bad comment config')
            return
        prov = space = None
        if ch == 'project':
            # Командний канал — лише коли його комусь віддано: модуль ролі
            # `comments` (у ЛІГИ — її запис `supabase-comments`); `local` працює скрізь. Не вдалось вирішити (`ModuleError`) — центральна відповідь модулів.
            # Простір — ОДИН раз: з нього постачальник, конфіг і канал.
            space = spaces.active_space()
            prov, prov_err = comments_provider(space)
            if prov_err is not None:
                raise prov_err
            if prov is None:
                self._send_json(integrations_off_body(
                    'командних коментарів у просторі без інтеграцій нема'), status=409)
                return
        tid, task = self._current_task()
        # Тег ІТЕРАЦІЇ, без сторінки: у полотні видно всі сторінки ітерації, а
        # скоуп пінів comment-layer рахує саме за ітерацією (`iterationOf`).
        ver = pm.page_version_tag(it, {'id': pm.IMPLICIT_ID})
        # Особа машини — запасне імʼя автора коментаря (коли `prompt()` недоступний,
        # як у вбудованому браузері). Лише ЛОКАЛЬНА оболонка: у сніпет рамки й
        # публікацію імʼя не йде — ПІБ у відкритому превʼю на Vercel неприпустиме.
        name, _ = machine_identity()
        user = {'user': {'name': name}} if name else {}
        if ch == 'project':
            # Командний канал — модуль ролі `comments` (у ЛІГИ — вбудований `supabase-comments` з конфігом установки,
            # `comments_route`): де його адаптер (кореневі адреси, по порядку), публічна конфігурація, канал. «Огляд»
            # (`overview-comments.js`) складає з цього `DeaiComments.create({...config, channel, onChange})`. `ModuleError`
            # (в т.ч. `comments-unconfigured`) летить у центральний обробник → 409.
            mod, cctx, route_channel = comments_route(space, prov)
            channel = route_channel(task, tid)                # ⛔ канал — ДО коду модуля (як у `publish_comments`)
            self._send_json({'ch': ch, 'module': mod.id, 'client': module_client_urls(mod, space),
                             'config': deai_modules.comments_client(space, mod, cctx), 'channel': channel,
                             'version': ver, **user})
        else:
            # Той самий файл, що в рамки (`_local_comments_*`); `project` — лише
            # ключ бекапу й нумерації в localStorage, як `local_key` у `_commented`.
            self._send_json({'ch': ch, 'project': f'{tid}/local', 'version': ver,
                             'endpoint': '/api/local-comments', **user})

    def _shots_manifest(self):
        """Манифест знімків ітерації. Немає файла — порожній, а не помилка:
        ітерацію могли просто ще не знімати."""
        q = parse_qs(urlparse(self.path).query)
        it = q.get('it', [''])[0]
        if not NAME_RE.match(it):
            self.send_error(400, 'bad iteration')
            return
        _, task = self._current_task()
        path_ = os.path.join(_iter_dir(task, it), 'shots', 'manifest.json')
        try:
            with open(path_, encoding='utf-8') as f:
                data = json.load(f)
            # Валідний JSON, який НЕ обʼєкт (список, рядок, число), — це теж «немає
            # манифеста». Без цієї перевірки наступний рядок кидав TypeError ПОЗА
            # try, зʼєднання рвалось без жодної HTTP-відповіді, і метод, який
            # обіцяє «ніколи не 500», падав саме там.
            if not isinstance(data, dict):
                data = {'checkedAt': None, 'shots': {}}
        except (FileNotFoundError, json.JSONDecodeError):
            # Тільки ці дві: «файла нема» і «файл не JSON». PermissionError та інші
            # проблеми доступу мусять бути ГУЧНИМИ — інакше биті права виглядали б
            # як «кадрів немає», і дизайнер шукав би причину в зʼємці.
            data = {'checkedAt': None, 'shots': {}}
        data['it'] = it
        data.setdefault('shots', {})
        self._send_json(data)

    def _flow_path(self, task, it):
        return os.path.join(_iter_dir(task, it), 'flow.json')

    def _flow_get(self):
        """Граф ітерації. Немає файла — порожньо, а не помилка: флоу ще не описували.
        Усе інше мусить сказати про себе: мовчазне «порожньо» значило б «флоу немає»,
        і дизайнер шукав би пропажу в інструменті, а не у файлі.

        Логіка та сама, що в _shots_manifest поруч: тиша належить ЛИШЕ «файла нема»,
        биті права й решта проблем доступу лишаються гучними. Відрізняється тільки
        те, ЧИМ бути гучним. Там гучність = неспійманий виняток; тут у відповіді вже
        є поле `error`, тому тека замість файла, відібрані права й валідний JSON, що
        не обʼєкт, доходять до канваса причиною, а не обірваним зʼєднанням.
        """
        q = parse_qs(urlparse(self.path).query)
        it = q.get('it', [''])[0]
        if not NAME_RE.match(it):
            self.send_error(400, 'bad iteration')
            return
        _, task = self._current_task()
        try:
            with open(self._flow_path(task, it), encoding='utf-8') as f:
                flow = json.load(f)
        except FileNotFoundError:
            self._send_json({'flow': None})
            return
        # OSError — це IsADirectoryError і PermissionError; FileNotFoundError теж
        # OSError, тому його гілка мусить стояти ВИЩЕ за цю, інакше «файла нема»
        # почало б виглядати помилкою. Ширше за OSError не глушимо.
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            self._send_json({'flow': None, 'error': f'flow.json не читається: {e}'})
            return
        # Валідний JSON, який НЕ обʼєкт (список, рядок, число), — це не граф. Той
        # самий урок, що дав isinstance у _shots_manifest: віддати список далі
        # означає перекласти падіння на клієнта, далеко від причини.
        if not isinstance(flow, dict):
            self._send_json({'flow': None, 'error': 'flow.json не читається: '
                             f'очікувався обʼєкт, а лежить {type(flow).__name__}'})
            return
        self._send_json({'flow': flow})

    def _flow_save(self, payload):
        it = payload.get('it', '')
        flow = payload.get('flow')
        if not NAME_RE.match(it):
            self.send_error(400, 'bad iteration')
            return
        # Тільки обʼєкт: список чи рядок ляжуть на диск і впадуть у клієнта пізніше,
        # далеко від місця помилки.
        if not isinstance(flow, dict):
            self.send_error(400, 'flow must be an object')
            return
        _, task = self._current_task()
        path_ = self._flow_path(task, it)
        try:
            # Цей писар був ПРООБРАЗОМ atomic_write_json — і сам лишався третьою
            # копією патерну, доки не поїхав сюди. Разом із хелпером приходить
            # те, чого власна копія не мала: збереження режиму цілі (flow.json
            # їде колегам через copy_mockup, і 0600 їхав би з ним) і прибирання
            # tmp навіть після Ctrl-C.
            atomic_write_json(path_, flow)
        except OSError as e:
            # Теку ітерації прибрали в сусідній вкладці, відібрали права, скінчилось
            # місце. Раніше це вилітало з обробника, і канвас бачив обірване
            # зʼєднання — «мережа впала» замість «не зберіг, і ось чому». Саме
            # OSError, не Exception: причина мусить лишитись гучною в тексті.
            # Прибирання tmp тут більше не потрібне — хелпер робить його сам.
            self._send_json({'ok': False,
                             'error': f'не вдалося зберегти flow.json: {e}'})
            return
        self._send_json({'ok': True})

    def _shoot(self, payload):
        """Зняти кадри ітерації: запускає bin/shoot.mjs (Node + Playwright).

        Дитина стукає назад у ЦЕЙ сервер за переліком сторінок і за самими
        сторінками — тому передаємо власний порт, а не 8765 зі здогадки. Дедлоку
        немає: сервер ThreadingHTTPServer.
        """
        it = payload.get('it', '')
        if not NAME_RE.match(it):
            self.send_error(400, 'bad iteration')
            return
        # Ширина прогону. Відсутня — прапорця не додаємо, і типову бере сам
        # shoot.mjs (одне місце з дефолтом, а не два розбіжні).
        # Невалідна — 400, а НЕ тихий дефолт: мовчазна підміна дала б кадри однієї
        # ширини під ключами іншої, тобто неправду в манифесті — і симптом
        # найгіршого сорту, бо кадри є, вони свіжі, вони просто не ті.
        # `bool` названо окремо, хоч діапазон його й так відсік би (`True == 1`):
        # у Python `bool` це підклас `int`, і без цього рядка `isinstance(vp, int)`
        # читалось би як «`vp: true` тут дозволено», а воно не ширина.
        vp = payload.get('vp')
        if vp is not None:
            if isinstance(vp, bool) or not isinstance(vp, int) \
                    or not (MIN_VP <= vp <= MAX_VP):
                self.send_error(400, 'bad viewport')
                return
        tid, task = self._current_task()
        node = _node_bin('node')
        if not node:
            self._send_json({'ok': False, 'error': 'node не знайдено — постав Node 22+'})
            return
        args = [node, os.path.join(ROOT, 'bin', 'shoot.mjs'),
                '--dir', _iter_dir(task, it), '--it', it,
                # Названа задача — і в адресі: `bin/shoot.mjs` будує з нього
                # `${url}/api/iteration-pages`, `${url}/api/flow` і
                # `${url}/commented?…&bare=1`, а заголовка не шле. Без префікса
                # дитина питала б ПОТОЧНУ задачу, а кадри писала б у названу.
                '--url', f'http://127.0.0.1:{self.server.server_address[1]}'
                         f'{self._task_prefix()}',
                '--json']
        if vp is not None:
            args += ['--vp', str(vp)]
        if payload.get('all'):
            args.append('--all')
        # Рух. Типово знімаємо з `prefers-reduced-motion: reduce` (див. shoot.mjs):
        # інакше макет із GL чи rAF-циклом дає `stable:false` на КОЖНОМУ кадрі, і
        # бейдж «недостовірний» стоїть вічно. `motion: true` повертає рух — коли
        # зняти треба саме його.
        if payload.get('motion'):
            args.append('--motion')
        # Перевірка свіжості (`freshen()` у канвасі) ходить ЦИМ САМИМ маршрутом,
        # але це НЕ зʼємка: `--check` браузера не піднімає, тільки перезважує
        # штампи. Далі вона свідомо не бере замка й не пишеться в реєстр.
        # ⚠️ Ціна відома й прийнята: `--check` усе-таки ПЕРЕПИСУЄ
        # `shots/manifest.json` (runCheck у bin/shoot.mjs), тож перевірка поряд із
        # живою зʼємкою — це «останній запис виграв»: свіжий кадр може на час
        # випасти з манифеста й піти на перезнім наступним прогоном. Запис
        # атомарний (tmp+rename), кадри на диску цілі, стан самолікується. Обмін
        # свідомий: мовчазна брехня «нічого не застаріло» коштувала дорожче.
        check = bool(payload.get('check'))
        if check:
            args.append('--check')
        if payload.get('only'):
            args += ['--only', ','.join(payload['only'])]

        key = (tid, it)
        progress = ShootProgress()
        # Запис створюємо завжди, але в РЕЄСТР кладемо лише справжню зʼємку.
        # Коли ключ замка не знав про `--check`, перевірка свіжості під час живої
        # зʼємки отримувала `{ok: true, already: true}` БЕЗ `report` — і канвас
        # записував `stale: []`, тобто «нічого не застаріло» як правду. Друга
        # вкладка бачила «Перезняти» без числа рівно тоді, коли застаріло все.
        entry = {'proc': None, 'progress': progress, 'hard': None}
        if not check:
            with _SHOOTS_LOCK:
                live = _SHOOTS.get(key)
                if live and _shoot_alive(live):
                    # Не черга і не помилка: друга спроба ПРИЄДНУЄТЬСЯ до наявної.
                    # Інакше автостарт із двох вкладок підняв би другий Chromium на
                    # ту саму теку, і два процеси писали б ті самі .webp навперейми.
                    self._send_json({'ok': True, 'already': True,
                                     'progress': live['progress'].snapshot()})
                    return
                # Заглушка ПІД ТИМ САМИМ входженням у замок, що й перевірка вище.
                # Поки між ними лежав Popen, два запити, що розійшлися в межах
                # fork+exec, обидва проходили перевірку. `proc` доллємо нижче.
                _SHOOTS[key] = entry

        # ГРУПА ПРОЦЕСІВ, а не subprocess.run(timeout=…). На таймауті `run` вбиває
        # лише ПРЯМУ дитину (node), а Chromium — це ОНУК: сигнал до нього не доходить
        # і headless-браузер лишається жити безстроково. Кожне натискання
        # «Перезняти» на застряглій ітерації додавало б ще один браузер у памʼять
        # машини дизайнера. Відтворено живцем на осиротілому процесі.
        # Спершу SIGTERM групі — щоб Node встиг закрити браузер сам, — і лише потім
        # SIGKILL (див. _arm_hard_kill).
        tail = []
        child = reader = watchdog = None
        timed_out = threading.Event()
        try:
            try:
                child = subprocess.Popen(args, cwd=ROOT, text=True,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         start_new_session=True)
            except (OSError, subprocess.SubprocessError) as e:
                # Вузьке, але реальне вікно: node міг зникнути після перевірки
                # _node_bin. Заглушку з реєстру знімає `finally` нижче — інакше
                # ключ лишився б зайнятим назавжди.
                self._send_json({'ok': False,
                                 'error': f'не вийшло запустити зʼємку: {e}'})
                return
            with _SHOOTS_LOCK:
                entry['proc'] = child

            def pump():
                """Читає stderr ПОРЯДКОВО, поки дитина жива.

                Не `communicate()`: він віддає все лише в кінці, тобто прогрес
                приїхав би разом із результатом — тобто не приїхав би зовсім. І з
                `communicate()` цей потік не вживається взагалі: обидва читали б ту
                саму трубу.
                """
                for raw in child.stderr:
                    _consume_stderr_line(raw.rstrip('\n'), progress, tail)

            reader = threading.Thread(target=_in_space(pump), daemon=True)
            reader.start()

            # Сторож замість `communicate(timeout=)`: убивство ГРУПИ закриває труби,
            # тому `stdout.read()` нижче повертається сам. Chromium — ОНУК процесу
            # node, і сигнал прямій дитині до нього не доходить.
            def on_timeout():
                timed_out.set()
                # SIGKILL другим кроком: node, який не відреагував на SIGTERM,
                # тримав би `stdout.read()` вічно, а разом з ним — і потік
                # обробника запиту. Той самий хелпер, що й у «Зупинити».
                with _SHOOTS_LOCK:
                    _killpg(child, signal.SIGTERM)
                    _arm_hard_kill(entry)

            watchdog = threading.Timer(SHOOT_TIMEOUT_S, _in_space(on_timeout))
            watchdog.daemon = True
            watchdog.start()
            out = child.stdout.read()
            child.wait()
        except BaseException:
            # Виняток дорогою — класика `RuntimeError: can't start new thread` на
            # `reader.start()`. Раніше він летів повз прибирання: запис лишався в
            # реєстрі НАЗАВЖДИ з `running: true`, а дитина (з Chromium-онуком)
            # працювала без нагляду. Дитину — під ніж, решту прибере `finally`.
            if child is not None:
                _killpg(child, signal.SIGTERM)
            raise
        finally:
            if watchdog is not None:
                watchdog.cancel()
            with _SHOOTS_LOCK:
                hard = entry.pop('hard', None)
                # `is entry`, а не просто наявність ключа: перевірка свіжості свого
                # запису в реєстр не клала й не сміє винести звідти чужий, живий.
                if _SHOOTS.get(key) is entry:
                    del _SHOOTS[key]
            if hard is not None:
                hard.cancel()
            if reader is not None:
                reader.join(timeout=5)
            # ЗАВЖДИ, а не лише на `done`: дитину могли вбити, і тоді події
            # `done` не буде ніколи, а `running` мусить згаснути.
            progress.finish()

        err = '\n'.join(tail)
        if timed_out.is_set():
            self._send_json({'ok': False, 'error': 'зʼємка не вклалася у 15 хвилин'})
            return
        if progress.stopped:
            # Зупинив дизайнер — це не провал: кадри, що встигли лягти на диск,
            # лишаються, і канвас має показати саме їх, а не текст помилки.
            self._send_json({'ok': True, 'stopped': True,
                             'progress': progress.snapshot()})
            return
        try:
            report = json.loads(out or '{}')
        except json.JSONDecodeError:
            # Не глушимо: канвас мусить показати, що саме сказала дитина
            report = {'raw': (out or '')[-2000:]}
        # `ok` — це «дитина дійшла до кінця без падіння», а НЕ «усе знято»: скрипт
        # виходить кодом 1, щойно в звіті є хоч один `failed`, навіть коли решта
        # сторінок знялась і вже лежить на диску. Той, хто малює тост, мусить
        # дивитись на `report.shot` і `report.failed` ОКРЕМО, інакше скаже «не знято
        # нічого» там, де знято сім із восьми.
        self._send_json({'ok': child.returncode == 0, 'report': report,
                         'stderr': (err or '')[-2000:]})

    def _shoot_progress(self):
        """Стан зʼємки цієї ітерації. Немає зʼємки — `running: false`, а не 404:
        клієнт опитує РЕГУЛЯРНО, і 404 у консолі виглядав би як поломка."""
        q = parse_qs(urlparse(self.path).query)
        it = q.get('it', [''])[0]
        if not NAME_RE.match(it):
            self.send_error(400, 'bad iteration')
            return
        tid, _ = self._current_task()
        with _SHOOTS_LOCK:
            live = _SHOOTS.get((tid, it))
            snap = live['progress'].snapshot() if live else None
        self._send_json(snap or {'running': False, 'total': None, 'done': 0,
                                 'current': None, 'frames': [], 'failed': [],
                                 'stopped': False})

    def _shoot_stop(self, payload):
        """Зупинити зʼємку: SIGTERM ГРУПІ, а через HARD_KILL_S — SIGKILL.

        Ескалація тут не менш обовʼязкова, ніж на таймауті: node, який SIGTERM
        проігнорував, добігає цикл і тримає `child.stdout.read()` у `_shoot`, а
        разом з ним потік обробника й запис у реєстрі — і нову зʼємку цієї
        ітерації вже не запустити. Таймер скасовує `finally` у `_shoot`.
        """
        it = payload.get('it', '')
        if not NAME_RE.match(it):
            self.send_error(400, 'bad iteration')
            return
        tid, _ = self._current_task()
        # УСЕ під ОДНИМ входженням у замок: між читанням запису й озброєнням
        # ескалації не сміє встрянути `finally` у `_shoot` — інакше SIGKILL-таймер
        # лишився б без того, хто його скасує.
        with _SHOOTS_LOCK:
            live = _SHOOTS.get((tid, it))
            proc = live.get('proc') if live else None
            if proc is not None and proc.poll() is None:
                # Прапорець ДО сигналу: інакше `_shoot` встиг би віддати відповідь
                # про обірвану дитину як про звичайне падіння.
                live['progress'].stopped = True
                _killpg(proc, signal.SIGTERM)
                _arm_hard_kill(live)
            else:
                proc = None
        if proc is None:
            # Зупиняти нічого. Це не помилка: канвас тисне «Зупинити» наосліп,
            # і зʼємка могла добігти саме між опитуванням і натисканням. Сюди ж
            # потрапляє заглушка (`proc: None`): ключ уже взято, а процесу ще
            # немає — сигналити нема кому, і канвас опитує прогрес далі.
            self._send_json({'ok': True, 'stopped': False})
            return
        self._send_json({'ok': True, 'stopped': True})

    def _comments(self):
        """Проєктні піни задачі для агента. Хто їх веде, вирішує постачальник ролі `comments` ПРОСТОРУ запиту
        (`ProjectComments`, простір — явним аргументом), а не прапорця `integrations`:

            нікого (`None`)        409 — «командних коментарів нема», як у просторі без інтеграцій
            модуль                 `{project, comments}` у формі рядків REST, але вже ОЧИЩЕНІ (`agent_pins`) — свідома відмінність
                                   від 0.9.0 (сирі рядки); (+ `warning`, коли щось не ввійшло). ЛІГА — той самий вбудований
                                   `supabase-comments` зі свого запису
            рішення не вдалось     центральна відповідь модулів (`{ok: false, code, error}`, 502/409) — НІКОЛИ не
                                   Supabase ЛІГИ і не порожній список
            виклик модуля не вдався  `{project, comments: [], error}` — як недоступна мережа колись у ЛІГИ (у ЛІГИ без конфігу
                                   `comments-unconfigured`)
        Типово — лише доручені Claude (`for_agent`, + `hidden`); `?all=1` — усі."""
        space = spaces.active_space()
        pc = ProjectComments(space)
        if pc.kind == 'off':
            # 409, а не порожній список: порожнє читалось би як «коментарів нема», а їх не ЧИТАЛИ.
            self._send_json(integrations_off_body(
                'командних коментарів у просторі без інтеграцій нема'), status=409)
            return
        if pc.kind == 'broken':
            raise pc.err
        q = parse_qs(urlparse(self.path).query)
        it = q.get('it', [''])[0]
        channel = q.get('channel', ['internal'])[0]
        show_all = q.get('all', ['0'])[0] == '1'
        tid, task = self._current_task()
        internal = (channel == 'internal')
        project = None
        try:
            project = pc.channel(task, tid, internal)
            pins = pc.pins(task, tid, internal)
            # Б2.3: агентові — лише доручені командні (`for_agent`); `?all=1` — усі, як до 0.27.0.
            mine = pins if show_all else [p for p in pins if for_agent(p, 'project')]
            body = {'project': project, 'comments': mine, 'all': show_all}
            if not show_all:
                body['hidden'] = len(pins) - len(mine)  # усі сховані з цього списку, закриті теж (на відміну від підказки inbox — вона рахує лише відкриті)
            if isinstance(pins, ModulePins) and pins.note():
                body['warning'] = pins.note()
            self._send_json(body)
        except (OSError, json.JSONDecodeError, deai_modules.ModuleError) as e:
            self._send_json({'project': project, 'comments': [], 'error': str(e)})

    def _comment_news(self):
        """`GET /api/comment-news?task=<id>` — легкі відкриті командні коментарі задачі для числа на вкладці (Deai 0.27.0,
        поправка 2 плану Б2: «нові» рахує клієнт за набором побачених id). Лише задачі простору запиту; модуль без `recent`
        чи простір без постачальника — `supported: false`, а не помилка."""
        q = parse_qs(urlparse(self.path).query)
        tid = q.get('task', [''])[0]
        if not NAME_RE.fullmatch(tid):
            self.send_error(400, 'bad task')
            return
        task = load_tasks().get('tasks', {}).get(tid)
        if not isinstance(task, dict):
            self._send_json({'ok': False, 'error': 'unknown task'}, status=404)
            return
        pc = ProjectComments(spaces.active_space())
        if pc.kind != 'module':
            self._send_json({'supported': False, 'items': []})
            return
        try:
            items = pc.recent(task, tid)
        except (OSError, deai_modules.ModuleError) as e:
            self._send_json({'supported': True, 'items': [], 'error': agent_line(str(e), 300)})
            return
        self._send_json({'supported': items is not None, 'items': items or []})

    # ---------- Локальні коментарі (фідбек Claude, НЕ в Supabase, у файлі) ----------
    def _local_file(self, task):
        return os.path.join(task['dir'], '.dc-local-comments.json')

    def _local_comments_get(self):
        tid, task = self._current_task()
        f = self._local_file(task)
        try:
            data = json.loads(open(f, encoding='utf-8').read()) if os.path.isfile(f) else []
        except (OSError, json.JSONDecodeError):
            data = []
        self._send_json({'comments': data})

    def _local_comments_post(self, payload):
        tid, task = self._current_task()
        comments = payload.get('comments')
        if not isinstance(comments, list):
            self.send_error(400, 'comments must be a list')
            return
        # ⛔ `_el` (DOM-вузол якоря) і `_pending` — живі поля коментатора, а не
        # дані піна. Адаптер їх і так не шле; тут — рубіж для будь-якого писаря
        # і самоочищення старих файлів, де `_el` осів у кожному піні (fb 05.11.2026).
        # `_aud` — службова позначка адресата комбінованого сховища (0.27.0).
        comments = [{k: v for k, v in c.items() if k not in ('_el', '_pending', '_aud')}
                    if isinstance(c, dict) else c for c in comments]
        atomic_write_json(self._local_file(task), comments, indent=1)
        self._send_json({'ok': True, 'count': len(comments)})

    # ---------- Пакет ТЮНЕРА (рекомендації Клоду, НЕ правки макета) ----------
    def _tuner_file(self, task):
        """⛔ ОКРЕМИЙ файл ПОРУЧ із `.dc-local-comments.json`, а не всередині нього.

        `comment-layer` — окремий продукт зі своїм каналом і своїм форматом;
        спільний файл означав би, що запис тюнера здатен зіпсувати чужі
        коментарі (і навпаки), а «скинути накручене» чіпало б чуже.
        Тека ЗАДАЧІ, як і в коментатора: пакет описує роботу над цією задачею,
        і переживати перемикання задач у спільному місці йому нічого.
        """
        return os.path.join(task['dir'], '.dc-tuner.json')

    @staticmethod
    def _tuner_rev(f):
        """Ревізія файла пакета: `mtime_ns-розмір`, або `None`, коли файла немає.

        ⛔ НАВІЩО (fb-22092026-c11bff, 22.09.2026). Пакет пишуть ДВОЄ: вкладка
        канваса (на кожен поворот ручки) і Клод (очищає, коли застосував). Вкладка
        читає файл один раз на старті й далі пише ПОВНИЙ пакет зі своєї памʼяті,
        тож перший же її запис після того, як Клод очистив пакет, клав назад
        старий `ready` — і дизайнер бачив «чекає на Клода» на вже застосованих
        правках. Ревізія дає вкладці спосіб сказати «я пишу поверх ОСЬ ЦЬОГО» і
        почути відмову, якщо файл тим часом змінив хтось інший.

        mtime_ns, а не секунди: вкладка пише кілька разів на секунду, і секундна
        точність зливала б сусідні записи в одну ревізію.
        """
        try:
            st = os.stat(f)
        except OSError:
            return None
        return f'{st.st_mtime_ns}-{st.st_size}'

    def _tuner_read(self, task):
        """(пакет або None, ревізія). Побитий файл — `None`, а не 500: єдине, що
        канвас може з ним зробити, — почати заново, і повідомляти про це
        помилкою транспорту означало б назвати відсутність даних поломкою."""
        f = self._tuner_file(task)
        try:
            data = json.loads(open(f, encoding='utf-8').read()) if os.path.isfile(f) else None
        except (OSError, json.JSONDecodeError):
            data = None
        return data, self._tuner_rev(f)

    def _tuner_get(self):
        _, task = self._current_task()
        data, rev = self._tuner_read(task)
        self._send_json({'package': data, 'rev': rev})

    def _tuner_post(self, payload):
        """Записати пакет. Перевіряємо ФОРМУ, а не довіряємо.

        ⛔ Перевірка не косметична: цей файл читає Клод в ІНШІЙ сесії й робить
        за ним правки в коді. Пакет, у якому `elements` — рядок або `note` —
        обʼєкт, тихо ліг би на диск і зіпсував би не інтерфейс, а РОБОТУ, яку
        за ним зроблять. Тому те, від чого залежить сенс пакета, звіряється
        тут, а не «якось розбереться читач».

        Межа перевірки: форма контейнера (`elements` — список, кожен елемент —
        обʼєкт із списком `edits`, `note` — рядок). ВМІСТ правок не звіряємо:
        його формує чиста модель (`app/tuner-model.js`), у неї свої тести, і
        друга, серверна копія знання про поля правки розійшлася б із першою.

        ОЧИЩЕННЯ — `{"action": "clear"}` (і рівнозначне `{"package": null}`, яке
        сесії пробували першим). Це крок Клода ПІСЛЯ того, як він застосував
        пакет (fb-22092026-728266): до цього виправлення очистити можна було лише
        вгадавши форму `{"elements": [], …}`, а `{"package": null}` відбивався
        400 і не міняв нічого — хоча виглядав як очищення.

        `base_rev` — ревізія, поверх якої пише ВКЛАДКА (`_tuner_rev`). Не збіглась
        → 409 разом із тим, що лежить на диску, і файл НЕ чіпаємо: вкладка
        підхоплює чужу зміну, замість мовчки її затерти. Клод `base_rev` не шле —
        його запис безумовний, бо він і є тим «іншим», від кого вкладку береже
        ця перевірка. У файл `base_rev` не потрапляє: це про запит, а не про пакет.
        """
        if not isinstance(payload, dict):
            self.send_error(400, 'package must be an object')
            return
        _, task = self._current_task()
        f = self._tuner_file(task)
        if payload.get('action') == 'clear' or ('package' in payload and payload['package'] is None):
            with _TUNER_LOCK:
                try:
                    os.remove(f)
                except FileNotFoundError:
                    pass
            self._send_json({'ok': True, 'cleared': True, 'rev': None})
            return
        if 'action' in payload:
            self.send_error(400, f'unknown action: {payload.get("action")!r}')
            return
        has_base = 'base_rev' in payload
        base = payload.pop('base_rev', None)
        elements = payload.get('elements')
        if not isinstance(elements, list):
            self.send_error(400, 'elements must be a list')
            return
        for el in elements:
            if not isinstance(el, dict) or not isinstance(el.get('edits'), list):
                self.send_error(400, 'each element must carry a list of edits')
                return
        if not isinstance(payload.get('note', ''), str):
            self.send_error(400, 'note must be a string')
            return
        with _TUNER_LOCK:
            if has_base:
                cur_data, cur_rev = self._tuner_read(task)
                if base != cur_rev:
                    self._send_json({'error': 'conflict', 'rev': cur_rev,
                                     'package': cur_data}, status=409)
                    return
            atomic_write_json(f, payload, indent=1)
            rev = self._tuner_rev(f)
        self._send_json({'ok': True, 'elements': len(elements), 'rev': rev})

    # ---------- POST ----------

    @_guarded_request
    def do_POST(self):
        # ⛔ Origin — ОДНА перевірка на ВСІ POST, до розбору задачі й тіла. Префікс
        # `/t/<id>/` робить POST із назвою задачі «простим запитом», який чужа
        # вебсторінка шле без preflight (CORS нічого не питає); раніше Origin
        # дивились лише `preview-password`, `teams-mute` і `claude-status`.
        # Свої клієнти проходять: канвас шле Origin localhost/127.0.0.1, а curl і
        # мод Claude Code не шлють його зовсім (`_local_origin` пускає обох).
        # Обробникові перевірки лишено — вони нешкідливі й дублюють це.
        if not _local_origin(self.headers.get('Origin')):
            self._drain_body()
            self._send_json({'ok': False, 'error': 'foreign origin'}, status=403)
            return
        if not self._take_task():
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length > feedback.BODY_MAX and self.path in ('/api/feedback', '/api/feedback-preview'):
                self._space_error(413, 'body-too-large', 'feedback body is too large')       # ДО читання: пам'ять не роздуваємо
                return
            raw_body = self.rfile.read(length) if length else b''
            self._body_read = True      # далі центральна відмова тіло вже не вичитує
            payload = json.loads(raw_body) if length else {}
        except RecursionError:
            # глибоко вкладений JSON: це не ValueError, і зʼєднання рвалось без відповіді
            self._tree_error(pm.TreeError('bad-body', 'body is nested too deeply'))
            return
        except (json.JSONDecodeError, ValueError):
            self.send_error(400, 'bad payload')
            return
        # Валідний JSON, але не обʼєкт (`[]`, `"x"`, `5`, `null`): кожен обробник
        # починає з `payload.get(...)` і впав би AttributeError — зʼєднання рвалось
        # без відповіді. Одна перевірка тут, а не в кожному обробнику.
        if not isinstance(payload, dict):
            self._tree_error(pm.TreeError('bad-body', 'body must be a JSON object'))
            return
        if self.path == '/api/iteration':
            self._new_iteration(payload)
        elif self.path == '/api/iteration-rename':
            self._iteration_rename(payload)
        elif self.path == '/api/iteration-delete':
            self._iteration_delete(payload)
        elif self.path == '/api/publish-toggle':
            self._publish_toggle(payload)
        elif self.path == '/api/page-new':
            self._page_new(payload)
        elif self.path == '/api/page-rename':
            self._page_rename(payload)
        elif self.path == '/api/page-delete':
            self._page_delete(payload)
        elif self.path == '/api/page-reparent':
            self._page_reparent(payload)
        elif self.path == '/api/page-move':
            self._page_move(payload)
        elif self.path == '/api/page-publish-toggle':
            self._page_publish_toggle(payload)
        elif self.path == '/api/folder-add':
            self._folder_add(payload)
        elif self.path == '/api/page-group':
            self._page_group(payload)
        elif self.path == '/api/page-ungroup':
            self._page_ungroup(payload)
        elif self.path == '/api/page-kind':
            self._page_kind(payload)
        elif self.path == '/api/page-restore':
            self._page_restore(payload)
        elif self.path == '/api/claude-status':
            self._claude_status(payload)
        elif self.path == '/api/pages-from-iterations':
            self._pages_from_iterations(payload)
        elif self.path == '/api/publish':
            self._publish(payload)
        elif self.path == '/api/preview-password':
            self._preview_password(payload)
        elif self.path == '/api/teams-mute':
            self._teams_mute(payload)
        elif self.path == '/api/local-comments':
            self._local_comments_post(payload)
        elif self.path == '/api/tuner':
            self._tuner_post(payload)
        elif self.path == '/api/shoot':
            self._shoot(payload)
        elif self.path == '/api/shoot-stop':
            self._shoot_stop(payload)
        elif self.path == '/api/flow-save':
            self._flow_save(payload)
        # ⛔ Нові адреси `/api/vcs-push|pull` — ОКРЕМІ гілки, а не кортеж `in (…)`: охоронець `bad-body` (`test_serve`) збирає маршрути
        # регексом `self.path == '/api/…'`, і кортеж пропустив би нову адресу повз перевірку «тіло — не обʼєкт».
        elif self.path == '/api/gitlab-sync':
            self._successor = '/api/vcs-push'
            self._gitlab_sync(payload)
        elif self.path == '/api/vcs-push':
            self._gitlab_sync(payload)
        elif self.path == '/api/autosync':
            self._autosync(payload)
        elif self.path == '/api/gitlab-pull':
            self._successor = '/api/vcs-pull'
            self._gitlab_pull(payload)
        elif self.path == '/api/vcs-pull':
            self._gitlab_pull(payload)
        elif self.path == '/api/task-switch':
            self._task_switch(payload)
        elif self.path == '/api/task-tags':
            self._task_tags(payload)
        elif self.path == '/api/task-rename':
            self._task_rename(payload)
        elif self.path == '/api/task-delete':
            self._task_delete(payload)
        elif self.path == '/api/task-restore':
            self._task_restore(payload)
        elif self.path == '/api/task-purge':
            self._task_purge(payload)
        elif self.path == '/api/task-new':
            self._task_new(payload)
        elif self.path == '/api/space-new':
            self._space_new(payload)
        elif self.path == '/api/space-update':
            self._space_update(payload)
        elif self.path == '/api/space-tool':
            self._space_tool(payload)
        elif self.path == '/api/agents-md':
            self._agents_md_post(payload)
        elif self.path == '/api/space-switch':
            self._space_switch(payload)
        elif self.path == '/api/module-enable':
            self._module_enable(payload)
        elif self.path == '/api/module-disable':
            self._module_disable(payload)
        elif self.path == '/api/module-settings':
            self._module_settings(payload)
        elif self.path == '/api/module-check':
            self._module_check(payload)
        elif self.path == '/api/module-trust':
            self._module_trust_post(payload)
        elif self.path == '/api/module-untrust':
            self._module_untrust(payload)
        elif self.path == '/api/update-check':
            self._update_check(payload)
        elif self.path == '/api/update-apply':
            self._update_apply(payload)
        elif self.path == '/api/feedback-preview':
            self._feedback_preview(payload)
        elif self.path == '/api/feedback':
            self._feedback(payload)
        else:
            self.send_error(404)

    def _feedback_collect(self, payload):
        """`(діагностика, шлях кадру | None)` для відгуку — ТОТАЛЬНО (машинний маршрут: потрібен саме тоді, коли щось зламано). Простір і
        задачу збираємо самі: задачу клієнт називає в тілі (`task`), сервер перевіряє `spaces.find_task`; дубль/невідома/битий реєстр —
        поля `None`, не виняток. Той самий збирач і для «Що буде надіслано», і для самої відправки (клієнтська частина — лише санітизація)."""
        tid = payload.get('task')
        it, node, screen = payload.get('it'), payload.get('node'), payload.get('screen')
        ctx = {'space': None, 'task_id': None, 'iteration': None, 'page': None, 'screen': screen, 'lang': payload.get('lang'),
               'version': updater.current_version(UPDATER_ROOT), 'roots': [(UPDATER_ROOT, '<app>')]}
        sp = task = None
        try:
            if isinstance(tid, str) and tid:
                sp = spaces.find_task(tid)
                if sp is not None:
                    with spaces.request_space(sp['id']):
                        _, task = task_for(load_tasks(), tid)
                    ctx['task_id'] = tid
            if sp is None:
                sp = spaces.active_space()
        except Exception:  # noqa: BLE001 — SpacesError/AmbiguousTask/UnknownTask/NoTask/OSError/ValueError: поля лишаються None
            pass
        ctx['space'] = sp
        if isinstance(sp, dict) and sp.get('path'):
            ctx['roots'].append((sp['path'], '<space>'))
        if isinstance(task, dict) and task.get('dir'):
            ctx['roots'].append((task['dir'], '<task>'))
        if isinstance(it, str) and NAME_RE.fullmatch(it):
            ctx['iteration'] = it
        if isinstance(node, str) and SHOT_RE.fullmatch(node):
            ctx['page'] = node
        shot = None
        if isinstance(task, dict) and ctx['iteration'] and ctx['page']:
            try:
                shot = _shot_file(task, ctx['iteration'], ctx['page'])
            except Exception:  # noqa: BLE001
                shot = None
        # Кільце сервера фіксується номером: перегляд бере поточний (`ring_seq`), відправка — той, що людина бачила; помилки, які
        # зʼявились ПІСЛЯ перегляду, не відправляються (їх вона не бачила) і не можуть заблокувати відправку.
        seq = payload.get('ring_seq')
        if isinstance(seq, bool) or not isinstance(seq, int) or not 0 <= seq <= 2 ** 62:
            seq = feedback.ring_seq()
        return feedback.build_diag(ctx, payload.get('client_errors'), max_seq=seq), shot, seq

    def _feedback_preview(self, payload):
        """`POST /api/feedback-preview` → `{ok, diag, diag_hash, shot: {available, bytes?, skipped?}}`: точно те, що піде з відгуком;
        `diag_hash` — sha256 канонічного JSON цієї діагностики (відправка звіряє його: «що показано = що піде»)."""
        payload = dict(payload, ring_seq=None)                  # перегляд завжди бере кільце на цю мить
        diag, shot, seq = self._feedback_collect(payload)
        self._send_json({'ok': True, 'diag': diag, 'diag_hash': feedback.diag_hash(diag), 'ring_seq': seq, 'shot': feedback.shot_info(shot)})

    def _feedback(self, payload):
        """`POST /api/feedback` → `{ok, id, state: 'sent'|'queued', number, reason?}`; `409 {ok:false, code:'diag-changed', diag, diag_hash, shot}`, коли
        `include_diag` і `diag_hash` не збігається з перерахованим (або його нема). Origin вже перевірено. Спершу запис у локальну чергу, потім одна
        спроба надіслати; мережа ніколи не дає `ok:false` — лише `queued`. Діагностику збирає ТА САМА функція, що й «Що буде надіслано»;
        кадр клієнт називає (`task`/`it`/`node`), сервер перевіряє двома замками (`_shot_file`)."""
        clean, bad = feedback.validate(payload)
        if bad:
            self._send_json({'ok': False, 'code': bad[0], 'error': bad[1]}, status=400)
            return
        diag, shot_file, seq = self._feedback_collect(payload)
        if clean['include_diag']:
            # «що показано = що піде»: діагностика змінилась від перегляду (нова помилка сервера…) або перегляду не було → 409 з новою
            # діагностикою; клієнт показує її й просить натиснути «Надіслати» ще раз. Нічого не записано.
            h = feedback.diag_hash(diag)
            given = payload.get('diag_hash')
            if not isinstance(given, str) or given != h:
                self._send_json({'ok': False, 'code': 'diag-changed', 'error': 'diagnostics changed since the preview',
                                 'diag': diag, 'diag_hash': h, 'ring_seq': seq, 'shot': feedback.shot_info(shot_file)}, status=409)
                return
        shot = None
        if clean['include_shot'] and shot_file and feedback.shot_info(shot_file).get('available'):
            try:
                with open(shot_file, 'rb') as f:
                    shot = (f.read(), 'webp')
            except OSError:
                shot = None
        out = feedback.submit(clean, diag if clean['include_diag'] else {}, shot)
        self._send_json({'ok': True, **out, 'number': out['id'][:8]})

    def _update_apply(self, payload):
        """`POST /api/update-apply`: застосувати `latest` зі стану. Тіло НЕ читається (версію/шлях/remote ззовні не приймаємо). Перезапуск
        планується ПІСЛЯ відправки відповіді (~0,5 с): клієнт встигає її прочитати."""
        status, body = _updater().apply()
        self._send_json(body, status=status)
        if status == 202 and body.get('restart') == 'auto':
            t = threading.Timer(0.5, _in_space(_restart_or_flag))
            t.daemon = True
            t.start()

    def _update_check(self, payload):
        """`POST /api/update-check`: спитати remote зараз (ручна перевірка) → `{ok: true, …status}`. Тіло не читається."""
        u = _updater()
        u.check()
        self._send_json({'ok': True, **u.status()})

    def _new_iteration(self, payload):
        """Створити ітерацію КОПІЄЮ з обраної (from) — форк. Без from: порожня стартова."""
        tid, task = self._current_task()
        meta = load_meta(task)
        its = meta.setdefault('iterations', [])
        nums = [int(m.group(1)) for i in its if (m := re.match(r'^it(\d+)$', i['id']))]
        new_id = f'it{max(nums, default=0) + 1}'
        dst = os.path.join(task['dir'], 'iterations', new_id)
        src_id = payload.get('from')
        if src_id and any(i['id'] == src_id for i in its):
            copy_mockup(os.path.join(task['dir'], 'iterations', src_id), dst)
        else:  # немає джерела (перша ітерація) — порожній стартовий макет
            src_id = None
            os.makedirs(dst, exist_ok=True)
            with open(os.path.join(dst, 'index.html'), 'w', encoding='utf-8') as f:
                f.write('<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">'
                        f'<title>{html_escape(str(task.get("title", tid)))}</title></head><body>'
                        '<h1>Нова ітерація</h1><p>Порожній макет — почни проєктувати.</p>'
                        '</body></html>')
        entry = _stamp_author({'id': new_id, 'date': time.strftime('%d.%m.%Y %H:%M'),
                               'note': str(payload.get('note', ''))[:300],
                               'published': False})
        if src_id:
            entry['from'] = src_id
        its.append(entry)
        save_meta(task, meta)
        g = git_autocommit(task['dir'], f'iteration {new_id}: '
                           f'{("копія " + src_id + " · ") if src_id else ""}'
                           f'{entry["note"] or "без примітки"}')
        if g['sha']:
            entry['git'] = g['sha']
            save_meta(task, meta)
        self._send_json({'ok': True, 'iteration': entry, 'git': g})

    def _iteration_delete(self, payload):
        """Видалити ітерацію (папку + запис). Git-коміт зберігає слід."""
        tid, task = self._current_task()
        iid = payload.get('id', '')
        if not NAME_RE.match(iid):
            self.send_error(400, 'bad id')
            return
        meta = load_meta(task)
        its = meta.get('iterations', [])
        if not any(i['id'] == iid for i in its):
            self.send_error(404, 'iteration not found')
            return
        meta['iterations'] = [i for i in its if i['id'] != iid]
        folder = os.path.join(task['dir'], 'iterations', iid)
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        save_meta(task, meta)
        git_autocommit(task['dir'], f'delete iteration {iid}')
        self._send_json({'ok': True, 'deleted': iid})

    def _iteration_rename(self, payload):
        """Перейменувати ітерацію: `label` — короткий підпис на пілюлі,
        `note` — повна примітка (тултіп/Огляд). Потрібно для задач, де ітерації
        це РІЗНІ СТОРІНКИ одного макета, а не версії однієї (напр. епік блогу):
        «Іт.2» нічого не каже, «Категорія» — каже."""
        tid, task = self._current_task()
        iid = payload.get('id', '')
        if not NAME_RE.match(iid):
            self.send_error(400, 'bad id')
            return
        meta = load_meta(task)
        for it in meta.get('iterations', []):
            if it['id'] != iid:
                continue
            if 'label' in payload:
                lbl = str(payload.get('label') or '').strip()[:40]
                if lbl:
                    it['label'] = lbl
                else:
                    it.pop('label', None)  # порожнє = прибрати, вернутись до «Іт.N»
            if 'note' in payload:
                it['note'] = str(payload.get('note') or '').strip()[:300]
            save_meta(task, meta)
            git_autocommit(task['dir'],
                           f'rename iteration {iid}: {it.get("label") or it.get("note") or "—"}')
            self._send_json({'ok': True, 'id': iid,
                             'label': it.get('label'), 'note': it.get('note')})
            return
        self.send_error(404, 'iteration not found')

    def _preview_password(self, payload):
        """Задати пароль превʼю задачі з інтерфейсу (ідея 02.09.2026).

        Пишемо ЛИШЕ в tasks.json — гейт у `publish/` не чіпаємо. Перепечатати
        тут саму обгортку (як `ops/reseal_gate.py`) означало б збрехати: у
        внутрішніх сторінках лишився б старий пароль. Новий пароль доїжджає в
        превʼю наступною публікацією, а до того `/api/task` чесно каже `stale`.

        ⚠️ Поле per-machine (tasks.json поза git): колега, що перепублікує цю
        задачу зі своєї машини, поставить СВІЙ пароль. Відповідь це не ховає.
        """
        # Пароль — не той запит, який може зробити будь-яка сторінка в браузері
        # простим `text/plain` POST (ревʼю 1.51, той самий клас, що claude-status).
        if not _local_origin(self.headers.get('Origin')):
            self._send_json({'ok': False, 'error': 'foreign origin'}, status=403)
            return
        # Origin — першим (як у `_teams_mute`): чужа сторінка не дізнається навіть про вимикач.
        # Цей пароль — гейт ЛІГА-превʼю (`build_preview(build='legacy')`); модуль публікації має власний
        # (секрет `password`), тож для простору, де публікує модуль чи не публікує ніхто, — та сама 409, що й була
        # без інтеграцій. Нечитабельний `space.json` (`ModuleError`) — теж «не ЛІГА», а не окрема помилка.
        try:
            league = deai_modules.publish_legacy_path(deai_modules.provider('publish'))
        except deai_modules.ModuleError:
            league = False
        if not league:
            self._send_json(integrations_off_body('публікація зʼявиться з модулями'), status=409)
            return
        pw, err = check_preview_password(payload.get('password'))
        if err:
            self._send_json({'ok': False, 'error': err}, status=400)
            return
        space = spaces.active_space()
        if not pw:
            # Зняття власного пароля → пароль повертається до секрету запису: ДО запису перевіряємо, що секрети читаються (інакше він
            # мовчки впав би в 1100). Непорожній свій пароль задачі секретів не питає (m4) — зберігається й за зіпсованого файла.
            try:
                deai_modules.publish_password(space)
            except deai_modules.ModuleError as e:
                self._space_error(deai_modules.STATUS.get(e.code, 409), e.code, SECRETS_UNREADABLE_TEXT)
                return
        cfg = load_tasks()
        # Не `cfg['current']`: пароль піде в ту задачу, яку названо запитом.
        _, task = task_for(cfg, self._task_override)
        if pw:
            task['preview_password'] = pw
        else:
            task.pop('preview_password', None)
        # fp-1: результат — ДО запису. Секрети могли зіпсуватися між пробою вище й цим читанням (TOCTOU): тоді відмова чиста, а `tasks.json` не змінено.
        try:
            now = preview_password(task, space)
        except deai_modules.ModuleError as e:
            self._space_error(deai_modules.STATUS.get(e.code, 409), e.code, SECRETS_UNREADABLE_TEXT)
            return
        save_tasks(cfg)
        self._send_json({'ok': True, 'preview_password': now,
                         'preview_password_custom': bool(task.get('preview_password')),
                         'preview_gate': preview_gate_state(task, now)})

    def _teams_mute(self, payload):
        """Замовчати / увімкнути Teams-сповіщення для КАНАЛУ задачі (проєкт цілком,
        для всіх, хто його коментує). Підпис «хто» — особа машини. Порядок: Origin → постачальник ролі `notify` (нікого — 409
        `notify-off`) → `muted` (400) → модуль. ⛔ Аргументи перевіряються ДО виклику модуля: він не бачить поганих."""
        if not _local_origin(self.headers.get('Origin')):
            self._send_json({'ok': False, 'error': 'foreign origin'}, status=403)
            return
        resolved, err = _notify_route_gate()
        if err is None and resolved[1] is None:
            self._send_json(_notify_off_body(), status=409)
            return
        muted = payload.get('muted')
        if not isinstance(muted, bool):
            self._send_json({'ok': False, 'error': 'muted must be boolean'}, status=400)
            return
        tid, task = self._current_task()
        channel = _comment_channel_in(spaces.active_space(), task, tid)
        me = mute_signature()
        try:
            notify.check_set_args(channel, muted, me)
        except ValueError as e:
            self._send_json({'ok': False, 'error': str(e)[:200]}, status=400)
            return
        try:
            if err is not None:
                raise err
            notify_call('mute_set', channel, muted, me, resolved=resolved)
            view = notify.mute_view(channel, notify_call('mute_state', resolved=resolved), me)
        except deai_modules.ModuleError as e:
            self._send_json({'ok': False, 'channel': channel, 'error': (e.message or e.code)[:200]}, status=502)
            return
        except (OSError, ValueError) as e:
            self._send_json({'ok': False, 'channel': channel, 'error': str(e)[:200]}, status=502)
            return
        self._send_json({'ok': True, **view})

    def _publish_toggle(self, payload):
        """Позначити ітерацію видимою на превью / зняти з публікації."""
        tid, task = self._current_task()
        meta = load_meta(task)
        for it in meta.get('iterations', []):
            if it['id'] == payload.get('id'):
                it['published'] = not it.get('published')
                save_meta(task, meta)
                self._send_json({'ok': True, 'id': it['id'],
                                 'published': it['published']})
                return
        self.send_error(404, 'iteration not found')

    # ---------- Сторінки ітерації (multi-page) ----------

    # Обробники нижче, що пишуть в ІСНУЮЧУ ітерацію, читають-міняють-пишуть
    # pages.json ПІД `pm.pages_lock` (старі — прямо, нові — через
    # `_tree_op`/`pm.mutate`). Без цього старий обробник гнав би паралельну
    # правку нового: обидва прочитали б той самий стан, і другий запис затер би
    # перший. Поза цим — `_pages_from_iterations` і створення ітерації: вони
    # пишуть у НОВУ теку, якої ще ніхто не читає, тож лока там нема.
    # ⚠️ Лок не реентерабельний: всередині `with pm.pages_lock` не можна кликати
    # `pm.mutate` чи інший `pages_lock` — `rename_page`/`set_published`/
    # `add_page`/`move_page`/`reparent_page` самі лок не беруть, тож їх огортати
    # можна. Відповіді й `git_autocommit` — ПОЗА локом: повільний клієнт чи git
    # не мають тримати писарів. Відмова правил дерева (`pm.TreeError`) — JSON із
    # `code` через `_tree_error`; широкого `except ValueError` тут нема, щоб не
    # глушити чужі помилки.

    def _page_new(self, payload):
        args = self._legacy_args(payload, need_page=False)
        if args is None:
            return
        task, idir, it, _ = args
        try:
            with pm.pages_lock(idir):
                pages = pm.read_pages(idir)
                pages, page = pm.add_page(idir, pages, payload.get('name') or 'Сторінка',
                                          parent_id=payload.get('parent') or None,
                                          kind=payload.get('kind') or 'page')
        except pm.TreeError as e:
            self._tree_error(e)
            return
        git_autocommit(task['dir'], f'page {page["id"]}: new in {it}')
        self._send_json({'ok': True, 'page': page})

    def _page_rename(self, payload):
        args = self._legacy_args(payload)
        if args is None:
            return
        task, idir, _, page = args
        try:
            with pm.pages_lock(idir):
                pm.rename_page(idir, pm.read_pages(idir), page, payload.get('name') or '')
        except pm.TreeError as e:      # busy / not-found / corrupt / правило дерева
            self._tree_error(e)
            return
        git_autocommit(task['dir'], f'page {page}: rename')
        self._send_json({'ok': True})

    def _page_delete(self, payload):
        """Видалити вузол: `mode` 'all' (за замовчуванням) — з усім піддеревом,
        'unwrap' — діти лишаються на його місці.

        Форма з `mode` — нова й вимагає `rev`; без `mode` — стара (так кличе
        нинішня панель), і rev їй не потрібен.

        Теки файлів стираємо в `after` — ПІД тим самим локом і лише після запису
        дерева: відмова запису інакше лишала б стерті файли під старим
        pages.json, а стирання поза локом дозволило б паралельному `page-new` з
        тим самим slug втратити щойно створену теку."""
        args = self._legacy_args(payload)
        if args is None:
            return
        _, idir, _, page = args
        mode = payload.get('mode') or 'all'
        failed = []       # теки, які не вдалось стерти: дерево вже записано, це не відмова
        r = self._tree_op(payload, lambda pages: pm.op_delete(pages, page, mode),
                          f'page {page}: delete ({mode})',
                          after=lambda removed: failed.extend(pm.remove_dirs(idir, removed)),
                          need_rev='mode' in payload)
        if r:
            out = {'ok': True, 'rev': r['rev']}
            if failed:
                out['failed'] = failed
            self._send_json(out)

    def _page_reparent(self, payload):
        args = self._legacy_args(payload)
        if args is None:
            return
        _, idir, _, page = args
        try:
            with pm.pages_lock(idir):
                pm.reparent_page(idir, pm.read_pages(idir), page, payload.get('parent') or None)
        except pm.TreeError as e:      # цикл, правила, not-found, busy, corrupt
            self._tree_error(e)
            return
        self._send_json({'ok': True})

    def _page_move(self, payload):
        """Переставити сторінку.

        Нова форма — `{it, ids: [...], parent, index, rev}`: перенести вузли
        (разом, у порядку дерева) під `parent` (None — корінь) на позицію `index`
        серед дітей. Правила дерева й rev перевіряє `_tree_op`, відмова — JSON
        із `code`.

        Стара — `{it, page, index}` (позиція ПІСЛЯ переставлення) або
        `{it, page, delta: ±1}` для «Підняти/Опустити» (fb-09092026-24e49a: форма
        запиту — дослівно з записки): лише серед сусідів, без rev. `parent` у
        старій формі — 400 `bad-form`: переносити під батька вона не вміє, і
        мовчки проігнорувати його означало б виконати не те, про що просили.

        `delta` рахуємо ТУТ, від порядку на диску, а не у вкладці: вкладка могла
        показувати застарілий список (колега щойно переставив), і «на одну вище»
        від застарілого індексу поставило б сторінку не туди. Кривий ввід — 400,
        а не 500: так само, як решта обробників сторінок."""
        if 'ids' in payload:
            ids = self._ids_or_400(payload)
            if ids is None:
                return
            r = self._tree_op(payload, lambda pages: (pm.op_move(
                pages, ids, payload.get('parent') or None, payload.get('index')), None),
                f'page {ids[0]}: move')
            if r:
                self._send_json({'ok': True, 'rev': r['rev']})
            return
        if 'parent' in payload:
            self._tree_error(pm.TreeError(
                'bad-form', 'parent needs the ids form: {ids, parent, index, rev}'))
            return
        args = self._legacy_args(payload)
        if args is None:
            return
        task, idir, _, page = args
        try:
            with pm.pages_lock(idir):
                pages = pm.read_pages(idir)
                index = payload.get('index')
                if 'delta' in payload:
                    delta = payload.get('delta')
                    if delta not in (-1, 1) or isinstance(delta, bool):
                        raise ValueError('delta must be -1 or 1')
                    _, siblings = pm.find_page(pages, page)
                    if siblings is None:
                        raise ValueError('page not found')
                    index = [p['id'] for p in siblings].index(page) + delta
                pm.move_page(idir, pages, page, index)
        except pm.TreeError as e:      # busy / not-found / corrupt / правило дерева
            self._tree_error(e)
            return
        except ValueError as e:        # кривий ввід старої форми (move_page, delta)
            self.send_error(400, str(e))
            return
        git_autocommit(task['dir'], f'page {page}: move')
        self._send_json({'ok': True})

    def _page_publish_toggle(self, payload):
        args = self._legacy_args(payload)
        if args is None:
            return
        _, idir, _, page = args
        try:
            with pm.pages_lock(idir):
                pages = pm.read_pages(idir)
                cur, _ = pm.find_page(pages, page)
                if cur is not None:
                    pm.set_published(idir, pages, page, not cur.get('published', True))
        except pm.TreeError as e:
            self._tree_error(e)
            return
        if cur is None:
            self._tree_error(pm.TreeError('not-found', f'page not found: {page}'))
            return
        self._send_json({'ok': True})

    # Нові дії над деревом — через `_tree_op`: лок, rev (обовʼязковий; 409 на
    # застарілий), правила дерева (JSON-відмова з `code`) і автокоміт в одному місці.

    def _folder_add(self, payload):
        r = self._tree_op(payload, lambda pages: pm.op_add_folder(
            pages, payload.get('name') or '', parent=payload.get('parent') or None,
            index=payload.get('index')), 'folder: add')
        if r:
            self._send_json({'ok': True, 'node': r['extra'], 'rev': r['rev']})

    def _page_group(self, payload):
        ids = self._ids_or_400(payload)
        if ids is None:
            return
        r = self._tree_op(payload, lambda pages: pm.op_group(
            pages, ids, payload.get('name') or ''), f'folder: group {len(ids)}')
        if r:
            self._send_json({'ok': True, 'node': r['extra'], 'rev': r['rev']})

    def _page_ungroup(self, payload):
        nid = payload.get('id', '')
        # «Тека, а не сторінка» — правило моделі (`pm.op_ungroup`): розгрупувати
        # сторінку значило б прибрати її з дерева, не стерши файли.
        r = self._tree_op(payload, lambda pages: (pm.op_ungroup(pages, nid), None),
                          f'folder {nid}: ungroup')
        if r:
            self._send_json({'ok': True, 'rev': r['rev']})

    def _page_kind(self, payload):
        nid, kind = payload.get('id', ''), payload.get('kind', '')
        r = self._tree_op(payload, lambda pages: (pm.op_set_kind(pages, nid, kind), None),
                          f'page {nid}: kind {kind}')
        if r:
            self._send_json({'ok': True, 'rev': r['rev']})

    def _claude_status(self, payload):
        """Серцебиття від мода pipeline-band. Час удару ставить СЕРВЕР, а не клієнт:
        інакше будь-хто «освіжив» би статус заднім числом."""
        # Ревʼю 1.51: будь-яка сторінка в браузері могла простим POST `text/plain`
        # намалювати «Claude працює». Браузер ставить Origin на кросс-доменний POST.
        if not _local_origin(self.headers.get('Origin')):
            self._send_json({'ok': False, 'error': 'foreign origin'}, status=403)
            return
        task, phase, status = payload.get('task'), payload.get('phase'), payload.get('status')
        note, sess = payload.get('note', ''), payload.get('session', '')
        ok = (isinstance(task, str) and 0 < len(task) <= 200 and phase in CLAUDE_PHASES
              and status in CLAUDE_TTL and isinstance(note, str) and len(note) <= 200
              and isinstance(sess, str) and len(sess) <= 200)
        if not ok:
            self._send_json({'ok': False, 'error': 'bad heartbeat'}, status=400)
            return
        with CLAUDE_LOCK:
            CLAUDE_BEATS[sess or task] = {'task': task, 'phase': phase, 'status': status,
                                          'note': note, 'session': sess, 'at': time.time()}
            if len(CLAUDE_BEATS) > 50:      # старі сесії не копляться вічно
                for k in sorted(CLAUDE_BEATS, key=lambda k: CLAUDE_BEATS[k]['at'])[:-50]:
                    CLAUDE_BEATS.pop(k, None)
        self._send_json({'ok': True})

    def _page_restore(self, payload):
        """«Відновити» з плашки «дерево перезаписали ззовні» (fb-01102026-71980b):
        теки й типи з дерева, яке бачила панель, поверх того, що на диску зараз."""
        prev = payload.get('prev')
        r = self._tree_op(payload, lambda pages: pm.op_restore(pages, prev),
                          'tree: restore folders')
        if r:
            self._send_json({'ok': True, 'restored': r['extra'], 'rev': r['rev']})

    def _pages_from_iterations(self, payload):
        """Зводить обрані itN (де ітерації використовувались як сторінки) у сторінки
        нової ітерації. Оригінали не чіпаємо (git-історія ціла)."""
        _, task = self._current_task()
        meta = load_meta(task)
        it_ids = [i for i in (payload.get('itIds') or []) if NAME_RE.match(str(i))]
        src_its = [i for i in meta.get('iterations', []) if i['id'] in it_ids]
        if len(src_its) < 2:
            self.send_error(400, 'need >= 2 iterations')
            return
        nums = [int(m.group(1)) for i in meta['iterations']
                if (m := re.match(r'^it(\d+)$', i['id']))]
        new_id = f'it{max(nums, default=0) + 1}'
        new_dir = _iter_dir(task, new_id)
        pages = []
        for it in src_its:
            name = (it.get('label') or it.get('note') or it['id']).strip() or it['id']
            pages, pg = pm.add_page(new_dir, pages, name)
            # перенести вміст старої ітерації в теку нової сторінки (крім pages.json)
            src_dir = _iter_dir(task, it['id'])
            for n in os.listdir(src_dir):
                # `.pages.lock` — службовий файл лока (див. TASK_IGNORE): у теці
                # нової сторінки він був би порожнім сміттям, що їде колегам
                if n in ('pages.json', 'pages.json.bak', '.pages.lock'):
                    continue
                s = os.path.join(src_dir, n)
                d = os.path.join(new_dir, pg['id'], n)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)  # перезаписує seed index.html вмістом старої ітерації
        meta['iterations'].append(_stamp_author(
            {'id': new_id, 'date': time.strftime('%d.%m.%Y %H:%M'),
             'note': 'зведено зі сторінок', 'published': False}))
        save_meta(task, meta)
        git_autocommit(task['dir'], f'iteration {new_id}: pages from {",".join(it_ids)}')
        self._send_json({'ok': True, 'iteration': new_id, 'pages': len(pages)})

    # ---------- Синхронізація з git: маршрути ролі `vcs` ----------
    #
    # `/api/vcs-status|push|pull` — нові адреси, `/api/gitlab-status|sync|pull` — псевдоніми з тими самими обробниками й формами
    # відповідей (на них спираються Stop-хук dev-pipeline і зовнішні скрипти). Гейт — роль `vcs` простору запиту
    # (`provider('vcs')`), а не прапорця `integrations`: звичайний простір із `git-sync` синкає так само, як ЛІГА.
    #
    # Простір без ролі — це «синку нема», а НЕ 409: UI опитує `vcs-status` на кожному старті, а Stop-хук — `autosync` після кожної
    # відповіді. Перевірка тут, у маршрутах, а НЕ в `gitlab_cfg`: його кличе доктор, і він мусить бачити GitLab-конфіг будь-якої задачі.

    def _vcs_ctx(self):
        """`(tid, task, vcs, err)`: `vcs` — `(module, ctx, legacy, target | None)` або `None` (ролі нема), `err` — `VcsError`
        постачальника (нечитабельний `space.json`, свій модуль «на папері», `git-sync` не завантажився). Ціль будує `vcs_target`
        (обрізана адреса, ключ і IP задачі, `{task}`), а не `gitlab_cfg`."""
        tid, task = self._current_task()
        try:
            return tid, task, vcs_task(tid, task), None
        except VcsError as e:
            return tid, task, None, e

    def _gitlab_status(self):
        """`GET /api/vcs-status?it=` (і `/api/gitlab-status?it=`). Без ролі чи цілі — `{configured: false}`; відмова
        постачальника — `{configured: false, code}` (форма спеки: `gitlab_status(vcs=None)` дав би `configured: true`);
        відмова модуля — 200 `{configured: true, error, code}`, щоб крапка в смузі не брехала."""
        tid, task, vcs, err = self._vcs_ctx()
        if err is not None:
            self._send_json({'configured': False, 'code': err.code})
            return
        if vcs is None or vcs[3] is None:
            self._send_json({'configured': False})
            return
        it = parse_qs(urlparse(self.path).query).get('it', [''])[0]
        # `it` іде в шлях (`_iter_dir`): `../..` хешував би чужу теку. Порожній — штатний (смуга без вибраної ітерації).
        if it and not NAME_RE.fullmatch(it):
            self.send_error(400, 'bad iteration')
            return
        try:
            self._send_json(gitlab_status(task, vcs[3], load_meta(task), it, vcs=vcs[:3]))
        except (OSError, subprocess.SubprocessError) as e:
            # `gitlab_status` сам перетворює відмову модуля (`VcsError`) на словник із `code`; сюди долітає решта `OSError`.
            self._send_json({'configured': True, 'error': _mask_repo(str(e))[:200]})

    def _gitlab_sync(self, payload):
        """`POST /api/vcs-push {it}` (і `/api/gitlab-sync`). Без ролі чи цілі — 400 `no gitlab configured for this task` (текст
        той самий, на ньому стоять тести й клієнт); відмова постачальника чи модуля — 200 `{ok: false, error, code}`."""
        tid, task, vcs, err = self._vcs_ctx()
        if err is not None:
            self._send_json(_vcs_failure(err))
            return
        if vcs is None or vcs[3] is None:
            self.send_error(400, 'no gitlab configured for this task')
            return
        it = payload.get('it', '')
        # ⛔ Не рядок (`5`, `null`, список) у `NAME_RE.match` кидав TypeError, і зʼєднання рвалось; `match` пропускав `it1\n`.
        if not isinstance(it, str) or not NAME_RE.fullmatch(it):
            self.send_error(400, 'bad iteration')
            return
        try:
            r = gitlab_sync(tid, task, vcs[3], it, vcs=vcs[:3])
        except (OSError, subprocess.SubprocessError) as e:
            self._send_json(_vcs_failure(e))
            return
        if r.get('synced'):  # відбиток — лише коли origin реально має наш макет
            _record_sync(task, it, r.get('sha'))
            self._overview_sync()
        self._send_json(r)

    def _autosync(self, payload):
        """Тихий крок автосинку для Stop-хука. Задача без цілі чи простір без ролі — не помилка, а нормальний стан:
        `reason: "no-gitlab"` (контракт хука; відмова постачальника — те саме, з `code`). `autosync` вимкнений у модулі —
        `reason: "autosync-off"` і ні відправки, ні локального автокоміту. Хук мовчить на причинах, яких не знає: реагує лише на
        `blocked`, `foreign-only`, `offline`, `changed`/`catchup`. Далі — `autosync()`: `no-iterations`, `foreign-only`, `clean`,
        а будь-який `OSError` навколо `gitlab_sync` — `reason: "offline"` (з `code` для `VcsError`).

        ⚠️ `offline` — ТИХА причина, і вона ширша за «нема мережі чи VPN»: як у 0.7.0, `autosync()` ловить будь-який `OSError`
        навколо `gitlab_sync`, тож і локальні збої всередині нього (`copy_mockup` → `PermissionError`, `mkdtemp` → `ENOSPC`)
        дають той самий тихий `offline`. Паритет із 0.7.0 свідомо не змінено.

        Хукові НІКОЛИ не віддається 5xx від збою ПОЗА git: усе, що вилетіло з `autosync()` на рівні маршруту, — 200 (текст крізь
        `_mask_repo`):
          * `VcsError` і `ModuleError` (відмова ролі чи каркаса; `ModuleError` через `_guarded` дав би 502/504/500 без маски, а
            `HTTPError` хук мовчить) — `reason: "offline"` + `code`, без traceback;
          * решта (`ValueError` із читання мети задачі, `OSError`, `PermissionError`, `KeyError`…) — `reason: "error"`, traceback — у
            stderr сервера, і хук КРИЧИТЬ: це збій ЛОКАЛЬНИЙ (нечитабельні `iterations.json`, права на теку), а не мережа, і
            незапушений макет лежав би тихо, якби його сховали під `offline`.
        Єдиний виняток — центральні стани простору (`NoTask`, `SpaceUnavailable`, `SpacesError`, `AmbiguousTask`): вони йдуть далі
        в `_guarded` і дають ті самі 404/409/503, що й будь-який маршрут."""
        tid, task, vcs, err = self._vcs_ctx()
        if err is not None or vcs is None or vcs[3] is None:
            out = {'ok': True, 'changed': False, 'reason': 'no-gitlab'}
            self._send_json({**out, 'code': err.code} if err is not None else out)
            return
        if not (vcs[1].get('settings') or {}).get('autosync'):
            self._send_json({'ok': True, 'changed': False, 'reason': 'autosync-off'})
            return
        try:
            r = autosync(tid, task, vcs[3], vcs=vcs[:3])
        except (SpaceUnavailable, spaces.NoTask, spaces.SpacesError, spaces.AmbiguousTask):
            raise
        except Exception as e:  # noqa: BLE001 — Stop-хук не мусить отримати 5xx: див. докстрінг
            if isinstance(e, deai_modules.ModuleError):
                e = VcsError(e.code, _frame_reason(e))                # відмова каркаса — як відмова ролі: тиха, з кодом
            offline = isinstance(e, VcsError)
            if not offline:
                # Причину бачить той, хто дивиться в лог сервера: у відповіді хука лише короткий `error`.
                sys.stderr.write(_mask_repo(traceback.format_exc()))
            self._send_json({**_vcs_failure(e), 'synced': False, 'changed': False, 'reason': 'offline' if offline else 'error'})
            return
        if r.get('changed'):
            self._overview_sync()
        self._send_json(r)

    def _gitlab_pull(self, payload):
        """`POST /api/vcs-pull` (і `/api/gitlab-pull`): ті самі відмови, що в `_gitlab_sync`."""
        tid, task, vcs, err = self._vcs_ctx()
        if err is not None:
            self._send_json(_vcs_failure(err))
            return
        if vcs is None or vcs[3] is None:
            self.send_error(400, 'no gitlab configured for this task')
            return
        try:
            self._send_json(gitlab_pull(task, vcs[3], vcs=vcs[:3]))
        except (OSError, subprocess.SubprocessError) as e:
            self._send_json(_vcs_failure(e))

    def _overview_sync(self):
        """Best-effort: оновити командний дашборд (`bin/overview_push.py sync --space <id>`) після publish/gitlab-sync/autosync.
        Фоново, не блокує основну дію; помилки ковтаємо. Рішення — за ПОСТАЧАЛЬНИКОМ ролі `dashboard` простору запиту, а не за
        прапорцем `integrations` (4c-1): звичайний простір із модулем дашборда синкає так само, як ЛІГА.

        Гейти (кожен — тиша, без лога й без `Popen`): `DC_NO_OVERVIEW` — для БУДЬ-ЯКОГО постачальника; нікого немає (`None`,
        збій реєстру чи рішення ролі); запис `shared_state` (ЛІГА) разом із `DC_TASKS_FILE` — ізольований прогін не має писати в
        спільний Supabase (закон 03.08.2026; у 0.11.0 цей гейт був лише на читанні, а `Popen` стартував і за `DC_TASKS_FILE` —
        дірка закрита свідомо). Конфіг дитині НЕ передається (оточенням чи ще
        чимось): вона читає `install_config` сама. Не більше одного синку на простір одночасно (`_overview_launch`)."""
        if os.environ.get('DC_NO_OVERVIEW'):
            # ⛔ Тести й будь-який офлайн-прогін не мають писати в ПРОД-Supabase.
            # Інцидент 03.08.2026: на командному дашборді (overview_projects)
            # висіли рядки `fixture` (jira=TEST-1) і `demo2` — приїхали саме
            # звідси. Прогін tests/test_serve.py тримав підмінений конфіг задач,
            # а цей Popen успадковував оточення і пушив фікстуру в реальну базу.
            return
        try:
            prov = deai_modules.provider('dashboard')
        except Exception:  # noqa: BLE001 — реєстр/`space.json` не читаються: пушити нікуди, ніхто не мусить про це знати
            return
        if prov is None:
            return
        try:
            space = spaces.active_space()
            shared = _shared_module(space, prov)
        except Exception:  # noqa: BLE001 — простір не вирішився: як і вище, пушити нікуди
            return
        if shared and isolation.isolated():
            return                      # ⛔ `shared_state`-модуль (4d-3a): ізольований прогін не пише в спільний стан і за ним
        key, target = _overview_target()
        _overview_launch(key, target)

    # ---------- Реестр задач (интеграция dev-pipeline) ----------

    def _task_switch(self, payload):
        """Перемкнути поточну задачу машини — і поточний ПРОСТІР, якщо задача з іншого.

        Задача шукається в УСІХ просторах (`find_task`; той самий id у двох — `AmbiguousTask`,
        центральні 409). Простір запиту фіксується на ЇЇ просторі, тож `load_tasks`/`save_tasks`
        нижче — файл ЦЬОГО простору, а не поточного на вході (воно може бути іншим).

        ⚠️ Порядок запису (спека, «Файл задач запиту»): СПЕРШУ файл задач цільового простору
        (`current`, `opened`), ПОТІМ `current` реєстру. Збій другого кроку лишає файл простору
        уже оновленим, а збій першого НЕ перемикає реєстр на простір, у якому `current` ще
        старий — і наступний `space-switch` не відкриє «не ту» задачу."""
        tid = payload.get('id', '')
        sp = spaces.find_task(tid)
        if sp is None:
            raise_if_legacy_unreadable()       # задача могла лежати в файлі, який не читається
            self.send_error(404, 'task not found')
            return
        spaces.set_request_space(sp['id'])
        cfg = load_tasks()
        if tid not in cfg.get('tasks', {}):         # вилучили між `find_task` і читанням
            self.send_error(404, 'task not found')
            return
        cfg['current'] = tid
        mark_opened(cfg, tid)
        save_tasks(cfg)
        spaces.switch_space(sp['id'])
        self._send_json({'ok': True, 'current': tid, 'space': _space_id(sp)})

    def _find_task_cfg(self, tid):
        """`cfg` простору, де лежить задача `tid`, з простором запиту, зафіксованим на ньому; `None` — відмову вже надіслано.
        Нечитабельний файл (старий чи інших просторів) — центральний 503 `space-unavailable`, а не «нема задачі»; нема — 404
        `unknown-task`; дубль id у двох просторах — центральний 409 (`AmbiguousTask` з `find_task`)."""
        sp = spaces.find_task(tid)
        if sp is None:
            raise_if_legacy_unreadable()       # задача могла лежати в файлі, який не читається
            broken = spaces.unreadable_task_files(spaces.read_registry())
            if broken:
                raise SpaceUnavailable(broken[0])
            self._space_error(404, 'unknown-task', 'task not found')
            return None
        spaces.set_request_space(sp['id'])
        cfg = load_tasks()
        if tid not in cfg.get('tasks', {}):         # вилучили між `find_task` і читанням
            self._space_error(404, 'unknown-task', 'task not found')
            return None
        return cfg

    def _payload_space(self, payload):
        """Простір із тіла (`space`): кошик належить простору. Нема такого — 400 `unknown-space`, `None`."""
        want = payload.get('space')
        sp = (next((s for s in spaces.read_registry()['spaces'] if s['id'] == want), None)
              if isinstance(want, str) else None)
        if sp is None:
            self._space_error(400, 'unknown-space', 'unknown space')
            return None
        spaces.set_request_space(sp['id'])
        return sp

    def _task_tags(self, payload):
        """Замінити мітки задачі `id` (4b-3): `{id, tags}` → `{ok, tags}`. Задача шукається в УСІХ просторах (`find_task`), простір
        запиту фіксується на ЇЇ просторі — пишеться файл задач ТОГО простору; поточну задачу й простір машини не міняємо
        (на відміну від `task-switch`: це правка полів, а не перехід). Порожній список валідний (`[]` зберігається: людина
        свідомо прибрала всі, похідна мітка ЛІГИ не воскресає). Нема задачі — 404 `unknown-task`; не за правилами — 400
        `bad-tags`, файл не змінено; дубль id у двох просторах — центральний 409.

        Порядок: СПЕРШУ перевірка міток, ПОТІМ простір і читання — відмова не торкається диска. Після запису — синхронізація
        реєстру тим самим кроком, що й після публікації (`_registry_push`, best-effort: без VPN правку не валимо)."""
        # Мітки — ПЕРШИМИ (дешево, без диска): погані мітки невідомої задачі — 400 `bad-tags`, як і в наявної.
        try:
            tags = normalize_tags(payload.get('tags'))
        except TagsError as e:
            self._space_error(400, 'bad-tags', str(e))
            return
        tid = payload.get('id', '')
        cfg = self._find_task_cfg(tid)
        if cfg is None:
            return
        cfg['tasks'][tid]['tags'] = tags
        save_tasks(cfg)
        _registry_push(tid)
        self._send_json({'ok': True, 'tags': tags})

    def _task_rename(self, payload):
        """Етап Д: нова назва задачі `{id, title}` → `{ok, id, title}`. Лише `title`: id, тека й вкладка (вона показує id)
        лишаються. Назва — `strip`, до 200 символів (як `task-new`); порожня чи не рядок — 400 `bad-title` без читання диска.
        Збій запису — 500 `task-rename-failed`. Після запису — `_registry_push`: у ЛІГИ назва — спільне поле реєстру, як мітки."""
        raw = payload.get('title')
        title = raw.strip()[:200] if isinstance(raw, str) else ''
        if not title:
            self._space_error(400, 'bad-title', 'title must be a non-empty string')
            return
        tid = payload.get('id', '')
        with TASK_CRUD_LOCK:
            cfg = self._find_task_cfg(tid)
            if cfg is None:
                return
            cfg['tasks'][tid]['title'] = title
            try:
                save_tasks(cfg)
            except OSError as e:
                self._space_error(500, 'task-rename-failed', str(e)[:300])
                return
        _registry_push(tid)
        self._send_json({'ok': True, 'id': tid, 'title': title})

    def _task_delete(self, payload):
        """Етап Д: задача → кошик простору (`task_trash.delete`): `{id}` → `{ok, id, current, trash:{id, title, at}}`.
        Тека переїжджає ДО запису `tasks.json`; збій запису вертає її (`undo`) і відповідає 500 `task-delete-failed`.
        Видалена поточна — `current` переходить на найсвіжішу іншу (його й віддаємо: екран оновлює «відкриту зараз»).
        Живий запис кошика з тим самим id — 409 `task-in-trash`."""
        tid = payload.get('id', '')
        with TASK_CRUD_LOCK:
            cfg = self._find_task_cfg(tid)
            if cfg is None:
                return
            order = [k for k, _ in tasks_by_recent(cfg)]
            try:
                rec, undo = task_trash.delete(cfg, tid, task_trash.utcnow(), order)
            except task_trash.TrashError as e:
                self._space_error(409 if e.code == 'task-in-trash' else 400, e.code, str(e))
                return
            except OSError as e:
                self._space_error(500, 'task-delete-failed', str(e)[:300])
                return
            try:
                save_tasks(cfg)
            except OSError as e:
                with contextlib.suppress(OSError):
                    undo()
                self._space_error(500, 'task-delete-failed', str(e)[:300])
                return
        # `current` лише луна: `task_trash.delete` щойно його перенесла, віддаємо для відповіді
        self._send_json({'ok': True, 'id': tid, 'current': cfg.get('current'),
                         'trash': {'id': tid, 'title': rec['entry'].get('title', tid), 'at': rec['at']}})

    def _task_restore(self, payload):
        """Етап Д: запис кошика простору `space` → назад: `{id, space}` → `{ok, id}`. Id зайнятий у БУДЬ-ЯКОМУ просторі —
        409 `task-exists` (дубль між просторами, `AmbiguousTask`, теж «зайнято»); вихідна тека вже є — 409 `task-dir-exists`
        (нічого не рухаємо); збій запису — тека назад у кошик, 500 `task-restore-failed`. `current` не змінюється."""
        tid = payload.get('id', '')
        if not isinstance(tid, str) or not tid:        # не рядок (`[1]`, `{}`) не хешується: без цього — обрив зʼєднання
            self._space_error(404, 'not-in-trash', 'task is not in the trash')
            return
        with TASK_CRUD_LOCK:
            if self._payload_space(payload) is None:
                return
            cfg = load_tasks()
            if not task_trash.in_trash(cfg, tid):
                self._space_error(404, 'not-in-trash', 'task is not in the trash')
                return
            try:
                taken = spaces.find_task(tid) is not None
            except spaces.AmbiguousTask:
                taken = True
            if taken:
                self._space_error(409, 'task-exists', 'a task with this id already exists')
                return
            try:
                _entry, undo = task_trash.restore(cfg, tid)
            except task_trash.TrashError as e:
                self._space_error(409 if e.code in ('task-dir-exists', 'task-exists') else 500, e.code, str(e))
                return
            except OSError as e:
                self._space_error(500, 'task-restore-failed', str(e)[:300])
                return
            try:
                save_tasks(cfg)
            except OSError as e:
                with contextlib.suppress(OSError):
                    undo()
                self._space_error(500, 'task-restore-failed', str(e)[:300])
                return
        self._send_json({'ok': True, 'id': tid})

    def _task_purge(self, payload):
        """Етап Д: знищити запис кошика `{id, space}` → `{ok, id}`. Тека стирається ПЕРШОЮ; збій стирання — 500
        `task-purge-failed`, запис лишається (повтор можливий). Збій запису надгробка — теж 500 `task-purge-failed`: тека вже
        зникла, запис лишається, повторне знищення лише допише надгробок. Надгробок не дає `registry.py pull` воскресити задачу."""
        tid = payload.get('id', '')
        if not isinstance(tid, str) or not tid:        # не рядок (`[1]`, `{}`) не хешується: без цього — обрив зʼєднання
            self._space_error(404, 'not-in-trash', 'task is not in the trash')
            return
        with TASK_CRUD_LOCK:
            if self._payload_space(payload) is None:
                return
            cfg = load_tasks()
            try:
                task_trash.purge(cfg, tid, task_trash.utcnow())
            except task_trash.TrashError as e:
                self._space_error(404 if e.code == 'not-in-trash' else 500, e.code, str(e))
                return
            except OSError as e:
                self._space_error(500, 'task-purge-failed', str(e)[:300])
                return
            try:
                save_tasks(cfg)
            except OSError as e:
                self._space_error(500, 'task-purge-failed', str(e)[:300])
                return
        self._send_json({'ok': True, 'id': tid})

    def _adopt_source(self, sp, tid, src, payload, tdir):
        """Перевірки `from` ДО будь-якого запису (спека 3b, «Сервер: задача з наявної теки»): `AdoptPlan(real, files,
        bytes, links)` або `None` — відмову вже надіслано. Порядок несучий: простір і тип поля — раніше за id (поле не
        для цього простору — відмова без огляду решти), id — раніше за диск (`adopt_scan` не ходить по теці заради
        задачі, якої однаково не буде).

        `tdir` — СПРАВЖНЯ тека майбутньої задачі (`<track_root>/<id>`, її рахує маршрут ДО цього виклику). ⛔ Не `<шлях простору>/<id>`:
        корінь напрямку може лежати поза простором чи в підтеці, і перевірка за шляхом простору пропускала `from` = сам корінь
        (копія в тій самій теці, що джерело; кожне наступне прийняття перепаковувало б попередні задачі)."""
        if payload.get('gitlab'):
            self._space_error(400, 'bad-request', 'from cannot be combined with gitlab')
            return None
        if not isinstance(src, str) or not src.strip():
            self._space_error(400, 'bad-request', 'from must be a non-empty string')
            return None
        if not isinstance(tid, str) or not NAME_RE.fullmatch(tid):
            self._space_error(400, 'bad-task-id', 'bad task id')
            return None
        # Шлях мусить бути АБСОЛЮТНИМ після `~`: відносний розкривався б від теки, звідки запущено сервер. NUL чи
        # самотній сурогат у рядку — `ValueError` із `realpath`: це «нема такої теки», а не обірване зʼєднання.
        real, absolute = None, False
        try:
            path = os.path.expanduser(src.strip())
            absolute = os.path.isabs(path)
            if absolute:
                real = os.path.realpath(path)
        except (ValueError, OSError):
            pass
        if real is None or not os.path.isdir(real):
            # Код один, текст — за справжньою причиною: відносний шлях чи абсолютний, якого нема.
            self._space_error(400, 'from-not-found',
                              'no such folder' if absolute else 'the path must be absolute (or start with ~)')
            return None
        idx = os.path.join(real, 'index.html')
        if os.path.islink(idx) or not os.path.isfile(idx):
            self._space_error(400, 'from-no-index', 'the folder has no index.html')
            return None
        # За ФАЙЛОВОЮ системою, не за рядками: на APFS `<тека простору>.upper()` — та сама тека, і `commonpath` її не
        # бачив би (копія пішла б у саму себе). Предок, якого не можна порівняти (інший диск Windows), — «не той».
        # Обидва напрямки: джерело містить теку задачі (копія пішла б у саму себе) І тека задачі містить джерело.
        if spaces._fs_under(os.path.realpath(tdir), real) or spaces._fs_under(real, os.path.realpath(tdir)):
            self._space_error(400, 'from-contains-space', 'the folder and the task folder contain one another')
            return None
        if os.path.lexists(tdir):
            self._space_error(409, 'task-dir-exists', 'the task folder already exists')
            return None
        try:
            files, total, links = adopt_scan(real)
        except AdoptRefused as e:
            self._space_error(e.status, e.code, str(e), **e.extra)
            return None
        except OSError as e:
            self._space_error(400, 'from-not-found', f'the folder is not readable: {type(e).__name__}')
            return None
        return AdoptPlan(real, files, total, links)

    def _task_new(self, payload):
        """Нова задача. Простір: `space` з тіла (є, але такого нема — 400, НЕ відкат у простір ЛІГА:
        мовчки завести «особисту» задачу в реєстр ЛІГА гірше за відмову); без `space` — простір
        із `legacy: true`, якщо він є, інакше поточний (4d-4c: ознак потоку ЛІГА більше нема —
        `jira`/`profile`/`track` простір не обирають). Просторів нема зовсім — 409 `no-space`.

        Id унікальний на машині через УСІ простори (`find_task`), не лише в цільовому. Але
        `find_task` вважає нечитабельний файл задач порожнім, а id, що лежить у ньому, невидимий:
        тож ПЕРЕД створенням усі файли просторів мусять читатись (`unreadable_task_files`) — інакше
        503 `space-unavailable` із назвою файла, а не дубль через простори.
        Простір без схеми ЛІГИ (`vcs_outbound`): `gitlab` у тілі — 400 `gitlab-needs-vcs-scheme`, `profile` — `null`, тека задачі —
        у `path` простору (ніколи спільний корінь ЛІГИ). Успіх робить цільовий простір поточним —
        як `task_new` уже робить поточною саму задачу; коли реєстр у цю мить не записати, задача
        вже СТВОРЕНА, тож відповідь 200 з `space_switched: false`, а не 503, що збрехав би.

        Етап 3b: необовʼязкове `from` — тека з `index.html`, яку сервер копіює в першу ітерацію замість стартового
        макета (`from` разом із `gitlab` — 400 `bad-request`; усі перевірки й обхід — `_adopt_source`, до будь-якого запису; відповідь
        несе `copied: {files, bytes, skipped_links}` — що скопійовано НАСПРАВДІ; тека задачі займається атомарно, збій
        прибирає її: `task_new`). `from: null` — поля нема.

        Етап 4a, «Нова задача»: необовʼязкове `vcs: {repo, path?, branch?}` (рядки) — ціль синку задачі за роллю `vcs` простору.
        Усе перевіряється ДО будь-якого запису (задача, тека, `tasks.json`; ядро `task_new` кладе `vcs` як є, навіть коли
        модуль ціль відхилив): не той вигляд — 400 `bad-request`; ролі в просторі нема — 400 `vcs-needs-role`; постачальник
        відмовив (`space.json` не читається, модуль «на папері») — 409 із кодом каркаса; `validate` модуля (якщо вона є) —
        400 `vcs-bad-target` (`ext::sh`, пароль в адресі, погана гілка чи шлях), під короткою межею каркаса: завислий свій
        модуль дає `check-timeout`, а не зависання. У задачу пишуться лише непорожні, обрізані значення. Є ціль і в `<path>`
        репо лежить `index.html` — перша ітерація з нього (збій отримання — тихо стартовий макет); з `from` отримання нема.

        Напрямок: `track` (рядок чи `null`) і `profile` (м'який вхід на межі: dev-pipeline досі шле його). Порядок відмов: чужий
        Origin 403 → тіло (`bad-profile`, `bad-track`: не рядок, `bad-tags`) → простір знайдено → конфлікт `track`/`profile`, далі
        для ВСІХ просторів (ЛІГА теж) `bad-track` (не за шаблоном id) і `unknown-track` (добре сформований id, якого нема в
        `space.json`; без напрямків — будь-який) → решта, усе ДО будь-якого запису. `profile`, що не є напрямком простору,
        ІГНОРУЄТЬСЯ (задача — у напрямок за замовчуванням), а `track` суворий; поля нема — `default_track`.

        ⚠️ Порядок: простір запиту фіксується ПЕРЕД `load_tasks()` — конфіг ЦІЛЬОВОГО простору, а не
        поточного на вході, інакше `save_tasks` записав би чужий конфіг у файл цілі."""
        profile = payload.get('profile')
        if profile is not None and not isinstance(profile, str):
            self._space_error(400, 'bad-profile', 'profile must be a string')
            return
        # Напрямок: `track` і `profile` (м'який вхід на межі, див. докстрінг). `null` і `''` — поля нема; `track` не рядок —
        # 400 `bad-track` (`bad-profile` лишається для `profile`). Це лише те, що видно з тіла; усе, що залежить від простору
        # (шаблон id, перелік напрямків, конфлікт двох ключів), перевіряється нижче, як тільки простір знайдено.
        track_in = payload.get('track')
        if track_in is not None and not isinstance(track_in, str):
            self._space_error(400, 'bad-track', 'track must be a string')
            return
        # Мітки (4b-3): `null` — поля нема; не за правилами — 400 ДО будь-якого запису (як `bad-profile`).
        tags = payload.get('tags')
        if tags is not None:
            try:
                tags = normalize_tags(tags)
            except TagsError as e:
                self._space_error(400, 'bad-tags', str(e))
                return
        # Старий файл є, а простору з нього нема, бо він не читається: id в ньому невидимі, тож
        # створювати нічого (як і при інших нечитабельних файлах нижче). ПЕРЕД `no-space`:
        # «створіть простір» тут брехало б — задачі й простір ЛІГА лежать у файлі, який треба лише полагодити.
        raise_if_legacy_unreadable(spaces.read_registry())
        want = payload.get('space')
        if want is None:
            sp = spaces.default_new_task_space()
            if sp is None:
                self._space_error(409, 'no-space', 'no space to put the task in — create a space first')
                return
        else:
            sp = next((s for s in spaces.read_registry()['spaces'] if s['id'] == want), None)
            if sp is None:
                self._space_error(400, 'unknown-space', 'unknown space')
                return
        # Напрямки простору — ОДИН раз на запит (`_TrackView` ліниво читає `space.json`/корінь ЛІГИ). Усе — ДО будь-якого запису:
        # ні теки, ні `tasks.json`.
        # `track` СУВОРО в усіх просторах (ЛІГА теж, 4d-4a): не за шаблоном id — `bad-track`, добре сформований id поза переліком
        # (чи перелік порожній) — `unknown-track`.
        # ⛔ `profile` — застарілий ключ, який шле зовнішній dev-pipeline (імʼя напрямку ЛІГИ, `tool`, інший регістр): він мусить і
        # далі проходити як м'який вхід, тож береться за напрямок лише коли це справжній напрямок простору (за шаблоном id І з
        # переліку); будь-який інший рядок ігнорується (задача — у напрямок за замовчуванням, а без напрямків: корінь = шлях
        # простору, `profile: null`, без ключа `track`). Конфлікт `track` і `profile` (`bad-track`) — лише коли `profile` справді
        # був би використаний; інакше вирішує один `track`.
        view = _TrackView(sp)
        known = bool(profile) and tracks.ID_RE.fullmatch(profile) and tracks.find(view.tracks, profile) is not None
        used_profile = profile if known else None
        if track_in and used_profile and track_in != used_profile:
            self._space_error(400, 'bad-track', 'track and profile name different tracks')
            return
        if track_in:
            if not tracks.ID_RE.fullmatch(track_in):
                self._space_error(400, 'bad-track', 'track must be lowercase letters, digits and dashes')
                return
            if tracks.find(view.tracks, track_in) is None:
                self._space_error(400, 'unknown-track', 'unknown track')
                return
        want_track = track_in or used_profile or None
        spaces.set_request_space(sp['id'])
        liga = deai_modules.vcs_outbound(sp)       # ПІСЛЯ фіксації простору: схема ЛІГИ (`compat`) його git-синку
        tid = payload.get('id', '')
        broken = spaces.unreadable_task_files(spaces.read_registry())
        if broken:
            raise SpaceUnavailable(broken[0])
        try:
            taken = spaces.find_task(tid) is not None
        except spaces.AmbiguousTask:
            taken = True                       # у двох просторах одразу: тим паче зайнятий
        if taken:
            self._space_error(400, 'task-exists', 'task already exists')
            return
        # Ціль синку (етап 4a). ПЕРЕД `adopt` і будь-яким записом: див. докстрінг.
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
                self._space_error(400, 'vcs-needs-role', 'this space has no git sync — connect a module in Settings')
                return
            # `validate` — необовʼязкова функція ролі: свій модуль міг її не мати. Через `_vcs_call`: форма результату й межа часу
            # (`CHECK_TIMEOUT` каркаса). Поганий id (не рядок, не `NAME_RE`) відхилить `task_new` — `bad-task-id`, до будь-якого
            # запису, — а ціль із ним (`{task}` у `path`) відмовила б раніше й іншим кодом: тут його не чіпаємо.
            if prov[0].fn('validate') is not None and isinstance(tid, str) and NAME_RE.fullmatch(tid):
                try:
                    _vcs_call(prov, 'validate', vcs_target(tid, {'vcs': vcs}, prov[1].get('settings') or {}),
                              timeout=deai_modules.CHECK_TIMEOUT)
                except VcsError as e:
                    self._space_error(deai_modules.STATUS.get(e.code, 400), e.code, str(e)[:300])
                    return
        # Задача з наявної теки (етап 3b). `from: null` — поля нема (як і без нього).
        # Теку задачі дає напрямок (`track_root`), тож рахується ДО `from`: усі перевірки джерела — проти справжнього призначення.
        # Напрямок за замовчуванням ставить маршрут (`task_new` без `track` лишає `None`): ЛІГА через адаптер — той самий, що
        # колись `profile or <напрямок за замовчуванням>`; звичайний простір без напрямків — `None` (як було). Теку й типове
        # репо дає напрямок: ЛІГА — `track_root` (спільний корінь для невідомого), звичайний — `root` напрямку чи шлях простору.
        cfg = load_tasks()                     # ПІСЛЯ фіксації простору: файл ЦІЛЬОВОГО простору
        track = want_track or view.default
        root, repo = track_root(view, track) or default_task_root(cfg), track_repo(view, track)
        adopt = None
        if payload.get('from') is not None:
            tdir = os.path.join(root, tid) if isinstance(tid, str) else ''
            adopt = self._adopt_source(sp, tid, payload.get('from'), payload, tdir)
            if adopt is None:
                return
        if not liga and payload.get('gitlab'):
            self._space_error(400, 'gitlab-needs-vcs-scheme',
                              'gitlab mapping needs a space whose git sync uses the design-canvas scheme')
            return
        try:
            r = task_new(cfg, tid,
                         title=str(payload.get('title', ''))[:200],
                         jira=str(payload.get('jira', ''))[:40],
                         track=track, gitlab=payload.get('gitlab'), vcs=vcs, root=root,
                         adopt_src=adopt.real if adopt else None, adopt_files=adopt.files if adopt else (),
                         tags=tags, repo=repo, legacy=liga)
        except TaskRefused as e:
            # `task-dir-exists` — гонка з `from`: теку встигли зайняти між перевіркою й записом (див. `task_new`)
            self._space_error(409 if e.code == 'task-dir-exists' else 400, e.code, str(e))
            return
        except SpaceUnavailable:
            raise
        except ValueError as e:
            self._space_error(400, 'bad-request', str(e))
            return
        except (OSError, subprocess.SubprocessError) as e:
            self._space_error(500, 'task-create-failed', str(e)[:300])
            return
        try:
            spaces.switch_space(sp['id'])
            switched = True
        except spaces.SpacesError:
            switched = False
        out = {**r, 'space': _space_id(sp), 'space_switched': switched}
        done = out.pop('adopted', None)
        if adopt and done:
            # Що скопійовано НАСПРАВДІ (`adopt_copy`), а не що бачив обхід: підмінене між ними — теж у пропущених.
            out['copied'] = {'files': done['files'], 'bytes': done['bytes'],
                             'skipped_links': adopt.links + done['skipped']}
        self._send_json(out)

    # ---------- Простори (реєстр машини: `spaces.py`) ----------

    #: Код відмови валідації простору → HTTP-статус; усе інше (`InputError`) — 400. Конфлікти зі
    #: СТАНОМ — 409, файл задач, що не читається, — 503 (як центральний `space-unavailable`).
    _SPACE_STATUS = {'path-registered': 409, 'task-id-collision': 409, 'space-unavailable': 503,
                     'space-json-unreadable': 409}

    def _space_failed(self, e):
        """Спільне відображення відмов `space-new|update|switch` ЗА ТИПОМ і АТРИБУТОМ (не за
        текстом): `InputError.code` → `{ok: false, code, error[, path]}` зі статусом із
        `_SPACE_STATUS` (типово 400); `KeyError` — 404 `unknown-space`; `spaces-off` — 409.
        Усе інше (`spaces-unreadable|unwritable`, чужий виняток) летить далі — до центрального
        обробника (503) чи в журнал: тут його НЕ ковтаємо. Викликати лише з `except`-блоку."""
        if isinstance(e, KeyError):
            self._space_error(404, 'unknown-space', f'unknown space: {e.args[0] if e.args else ""}')
        elif isinstance(e, spaces.SpacesError) and e.code == 'spaces-off':
            self._space_error(409, 'spaces-off', str(e))
        elif isinstance(e, spaces.InputError):
            self._space_error(self._SPACE_STATUS.get(e.code, 400), e.code, str(e),
                              **({'path': e.path} if e.path else {}))
        else:
            raise

    def _space_new(self, payload):
        """Створити простір (тека, `space.json`, `tasks.json`, запис у реєстр) і зробити поточним."""
        try:
            sid = spaces.create_space(payload.get('name'), payload.get('color'), payload.get('path'))
        except (spaces.InputError, KeyError, spaces.SpacesError) as e:
            self._space_failed(e)
            return
        self._write_space_agents_md(sid)
        self._send_json({'ok': True, 'id': sid})

    @staticmethod
    def _write_space_agents_md(sid):
        """Новий простір дістає AGENTS.md одразу; збій запису НЕ валить створення простору — лише лог (stderr)."""
        try:
            sp = next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)
            agents_md.write(sp['path'], version=updater.current_version(UPDATER_ROOT))
        except Exception as e:    # noqa: BLE001 — навмисно: AGENTS.md — додаток до простору, не його умова
            print(f'agents-md: not written for new space {sid}: {type(e).__name__}', file=sys.stderr)

    def _space_update(self, payload):
        """Змінити назву й колір простору (`space.json`); решта його ключів лишається."""
        sid = payload.get('id')
        try:
            meta = spaces.update_space(sid, payload.get('name'), payload.get('color'))
        except (spaces.InputError, KeyError, spaces.SpacesError) as e:
            self._space_failed(e)
            return
        self._send_json({'ok': True, 'id': sid, **meta})

    def _space_tool(self, payload):
        """`POST /api/space-tool {space, tool, on}` → `{ok, space, tools}`: вимикач інструмента простору (`space.json`, `tools`).
        Ті самі відмови, що `space-update` (невідомий простір — 404, шар вимкнено — 409); невідомий інструмент — 400."""
        sid = payload.get('space')
        try:
            tools = spaces.set_space_tool(sid, payload.get('tool'), payload.get('on'))
        except (spaces.InputError, KeyError, spaces.SpacesError) as e:
            self._space_failed(e)
            return
        self._send_json({'ok': True, 'space': sid, 'tools': tools})

    def _agents_md_post(self, payload):
        """`POST /api/agents-md {space}`: створити/оновити блок."""
        self._agents_md(payload.get('space'), True)

    def _agents_md(self, want, write):
        """`GET|POST /api/agents-md[?space=]` → `{ok, space, …agents_md.status, paths}`. POST створює/оновлює блок (`ValueError('newer')` →
        409 `newer`, файл цілий). Неявний простір чи простір без теки → 409 `no-folder`. `paths` — абсолютні шляхи ЦІЄЇ установки: лише
        у відповіді, у файл вони не потрапляють. Версія — та сама, що `current` у `GET /api/update`."""
        sp = self._module_space(want)
        if sp is None:
            return
        folder = sp.get('path') or ''
        if spaces._is_implicit(sp) or not folder or not os.path.isdir(folder):
            self._space_error(409, 'no-folder', 'no-folder')
            return
        version = updater.current_version(UPDATER_ROOT)
        try:
            if write:
                st = agents_md.write(folder, version=version)
            else:
                st = agents_md.status(folder, version=version)
        except ValueError as e:
            self._space_error(409 if str(e) in ('newer', 'changed') else 503, str(e), str(e))
            return
        except OSError:       # права, тека чи симлінк замість файла: JSON-відповідь, а не обрив зʼєднання
            self._space_error(503, 'unreadable', 'unreadable')
            return
        deai = UPDATER_ROOT
        self._send_json({'ok': True, 'space': sp['id'], **st,
                         'paths': {'deai': deai, 'inbox': os.path.join(deai, 'bin', 'inbox.py'),
                                   'authoring': os.path.join(deai, 'docs', 'modules', 'authoring.md')}})

    def _space_switch(self, payload):
        """Зробити простір поточним; відповідь — його поточна задача (`null`, коли її нема).

        Шар вимкнено → 409 `spaces-off` ЯВНО: `switch_space` там навмисний no-op (і для
        невідомого id), а відповідь `ok` збрехала б, що простір перемкнуто."""
        sid = payload.get('id')
        try:
            if not spaces.layer_on():
                raise spaces.SpacesError('spaces-off', spaces.registry_path(), 'spaces layer is off')
            spaces.switch_space(sid)
            task = spaces.space_current_task(sid)
        except (KeyError, spaces.SpacesError) as e:
            self._space_failed(e)
            return
        self._send_json({'ok': True, 'current': sid, 'task': task})

    # ---------- Модулі (етап 2а, Task 6; логіка — модульні функції `module_*`/`ds_tokens_view` вище) ----------

    def _module_space(self, want):
        """Простір маршрутів модулів: `want` — параметр `space` (`None`/відсутній — простір, зафіксований
        на вході, `spaces.active_space()`); запис реєстру або `None` (відповідь уже надіслана: 404
        `unknown-space`, та сама форма, що в `_space_failed` інших маршрутів просторів). Простору нема зовсім —
        теж `unknown-space`. Названий простір стає простором запиту (воркер `deai_modules.call` його
        успадковує). Порожній `space=` у запиті GET — «не задано» (`parse_qs` відкидає порожні значення);
        у тілі POST порожній рядок — вже невідомий простір."""
        if want is None:
            sp = spaces.active_space()
            if sp is None:
                self._space_error(404, 'unknown-space', 'no space: nothing to ask about')
                return None
            return sp
        sp = next((s for s in spaces.read_registry()['spaces'] if s['id'] == want), None)
        if sp is None:
            self._space_error(404, 'unknown-space', f'unknown space: {str(want)[:60]}')     # ті самі код і форма, що `_space_failed`
            return None
        spaces.set_request_space(sp['id'])
        return sp

    def _modules_get(self):
        """`GET /api/modules?space=` → `{modules: [...][, notes: [...]]}` (`modules_payload`). Модулі НЕ виконуються (лише
        завантажуються й читається запамʼятований `check`): запит дешевий і безпечний для опитування."""
        sp = self._module_space(parse_qs(urlparse(self.path).query).get('space', [None])[0])
        if sp is None:
            return
        self._send_json(modules_payload(sp))

    def _module_ext_get(self):
        """`GET /api/module-ext?space=` → `{tools: [...], actions: [...]}` (`deai_modules.extensions`): простір і відмови — ті самі, що в
        `GET /api/modules` (`_module_space`; `space-json-unreadable` — 409 центрально). Шар просторів вимкнено — неявний простір, порожні списки."""
        sp = self._module_space(parse_qs(urlparse(self.path).query).get('space', [None])[0])
        if sp is None:
            return
        self._send_json(deai_modules.extensions(sp))

    def _ds_tokens_get(self):
        """`GET /api/ds-tokens?space=` → `ds_tokens_view`: завжди 200 для відомого простору (інспектор мусить
        працювати без токенів); невідомий простір — 404."""
        sp = self._module_space(parse_qs(urlparse(self.path).query).get('space', [None])[0])
        if sp is None:
            return
        self._send_json(ds_tokens_view(sp))

    def _module_trust_get(self):
        """`GET /api/module-trust?space=&id=` → `{ok: true, trust: <дані діалогу>}` (`deai_modules.trust_view`)."""
        q = parse_qs(urlparse(self.path).query)
        sp = self._module_space(q.get('space', [None])[0])
        if sp is None:
            return
        self._send_json({'ok': True, 'trust': deai_modules.trust_view(sp, q.get('id', [None])[0])})

    def _module_trust_post(self, payload):
        """`POST /api/module-trust {space, id, hash, lang?}` → `{ok: true, module}`. Лише з браузера канваса: `Origin`
        Є й локальний І `Sec-Fetch-Site: same-origin` — інакше 403 `trust-needs-ui`. Це фільтр від curl агента, а не
        межа: межа — системне вікно ОС у `grant_trust` (скрипт сторінки макета шле ті самі заголовки)."""
        origin = self.headers.get('Origin')
        if not origin or not _local_origin(origin) or self.headers.get('Sec-Fetch-Site') != 'same-origin':
            self._space_error(403, 'trust-needs-ui', 'trust is granted only from the canvas page in a browser')
            return
        sp = self._module_space(payload.get('space'))
        if sp is None:
            return
        mid = payload.get('id')
        lang = payload.get('lang')
        lang = lang if isinstance(lang, str) and lang in module_trust.CONFIRM_TEXT else 'uk'   # `[]` у `in` — TypeError
        deai_modules.grant_trust(sp, mid, payload.get('hash'), lang)
        self._send_json({'ok': True, 'module': module_entry(sp, mid)})

    def _module_untrust(self, payload):
        """`POST /api/module-untrust {space, id}` → `{ok: true, module: <запис> | null}`: зняти довіру — безпечний
        напрям, тож ні `Sec-Fetch-Site`, ні системного вікна (`deai_modules.revoke_trust`)."""
        sp = self._module_space(payload.get('space'))
        if sp is None:
            return
        mid = payload.get('id')
        deai_modules.revoke_trust(sp, mid)
        self._send_json({'ok': True, 'module': module_entry(sp, mid)})

    # По обробнику на маршрут (як скрізь у `do_POST`: тест «тіло не обʼєкт» розбирає `self._xxx(payload)`).
    def _module_enable(self, payload):
        self._module_post(payload, 'enable')

    def _module_disable(self, payload):
        self._module_post(payload, 'disable')

    def _module_settings(self, payload):
        self._module_post(payload, 'settings')

    def _module_check(self, payload):
        self._module_post(payload, 'check')

    def _module_post(self, payload, action):
        """`POST /api/module-enable|disable|settings|check` `{space?, id, settings?, secrets?, replace?}`:
        `{ok: true, module: <запис>[, check: <вердикт>][, replaced: [id…]]}` (порядок запису й коди — `module_write`,
        `module_check_verdict`). `replaced` — лише для `module-enable` з `replace: true`: id модулів, що тримали роль
        і вимкнені тим самим записом (порожній список, коли конфліктів не було). `replace` не `bool` (і явний `null`
        теж) — 400 `bad-settings`; ціль, що не завантажилась, — відмова її `error_code` (`module-error` 502 /
        `bad-manifest` 500). `module` — `null`, коли запису вже нема в списку: так буває лише після `module-disable`
        відсутнього в каталозі (`missing`) модуля — вимкнений відсутній не показується. `ModuleError` (`unknown-module` 404, `bad-settings` 400, `role-taken` 409,
        `space-json-unreadable`/`spaces-off` 409, `unwritable` 500…) відповідає `_guarded` — одна форма
        `{ok: false, code, error}` на всі маршрути; текст уже без секретів, а значення секретів сюди не
        доходять взагалі (відповідь будується з прапорців `set`)."""
        sp = self._module_space(payload.get('space'))
        if sp is None:
            return
        mid = payload.get('id')
        replaced = None
        if action == 'check':
            verdict = module_check_verdict(sp, mid)
        else:
            verdict, replaced = module_write(sp, mid, action, payload.get('settings'), payload.get('secrets'),
                                             payload.get('replace', _NO_REPLACE))
        out = {'ok': True, 'module': module_entry(sp, mid)}
        if action != 'disable' and verdict is not None:
            out['check'] = verdict
        if replaced is not None:
            out['replaced'] = replaced
        self._send_json(out)

    def _publish(self, payload):
        """Собрать publish/ из ОПУБЛИКОВАННЫХ итераций: свитчер+гейт+comment-layer
        (сама сборка — `build_preview`, общая с модулями публикации).
        Затем деплой модулем `vercel-publish` в режиме `cli` (`_publish_legacy_call`: тот же `npx vercel`, без AI); URL
        сохраняется в iterations.json.

        Хто публікує, вирішує `deai_modules.provider('publish')` — ПЕРШИМ рядком, до збірки `publish/` (вона
        `rmtree`-ить теку): шлях ЛІГИ (`deai_modules.publish_legacy_path`: вбудований `vercel-publish` із
        `compat == "design-canvas"`) — цей шлях; `None` — 409 `no-publish-module`;
        решта модулів — `publish_with_module` (локальна тека чи свій деплой). Лише `self._send_json`,
        `send_error`, `_current_task`, `_overview_sync`: зовнішні заглушки обробника мають лише їх, тож
        нові помічники — модульні функції.

        Коментарі збірки ЛІГА (2b-2, з 4b-2) — з `publish_comments`: простір, де публікує ЛІГА, звичайно веде командні
        коментарі вбудованим `supabase-comments` (запис `supabase-comments` → словник модуля з каналом ЛІГИ; без
        запису — без коментарів + `comments_unavailable: comments-unconfigured`), але людина могла ввімкнути там власний
        модуль коментарів — тоді збірка несе ЙОГО канал; а явно ввімкнений модуль, що зламався, дає збірку без коментарів
        узагалі (не спільний Supabase) і `comments_unavailable` у відповіді."""
        prov = deai_modules.provider('publish')
        if prov is None:
            self._send_json(no_publish_module_body(), status=409)
            return
        if not deai_modules.publish_legacy_path(prov):
            publish_with_module(self, prov, payload)
            return
        tid, task = self._current_task()
        meta = load_meta(task)
        its = [i for i in meta.get('iterations', []) if i.get('published')]
        if not its:
            self.send_error(400, 'no iterations marked for publish - '
                                 'toggle the green dot first')
            return
        # Пароль ЛІГА — завжди є (задачі, секрет запису чи типовий 1100): гейт тут обовʼязковий, і лише
        # модуль без пароля передає `gate_pw=None` (див. `build_preview`). Читаємо його ДО збірки (раніше
        # — після `rmtree`): збій читання не лишає напівзібраний `publish/`. Простір береться лише
        # коли він зафіксований за запитом: інструменти ЛІГА й заглушки обробника його не мають, і реєстру тоді не читаємо.
        # (m3: справжній запит завжди зафіксований за простором — `_pin_current_space` на вході, ~5843; гілка `None` — лише для заглушок.)
        space = spaces.active_space() if spaces.layer_on() and spaces.request_space_id() is not None else None
        try:
            pw = preview_password(task, space)
        except deai_modules.ModuleError as e:        # fail-closed (t9-1): нечитабельні секрети — відмова ДО збірки, не мовчки `1100`
            self._send_json({'ok': False, 'code': e.code, 'error': SECRETS_UNREADABLE_TEXT},
                            status=deai_modules.STATUS.get(e.code, 409))
            return
        # Коментарі превʼю — з постачальника ролі `comments` простору публікації (а не з прапорця `integrations`), раз, ДО
        # збірки: запис `supabase-comments` → вбудований модуль з каналом ЛІГИ, свій модуль → його канал,
        # відмова (в т.ч. `comments-unconfigured`) → без коментарів узагалі + `comments_unavailable` у відповіді (див.
        # `publish_comments`).
        comments, comments_warn = publish_comments(space, task, tid)
        tokens = preview_tokens_snapshot(space)      # знімок токенів для інспектора превʼю (`space` — `None`, коли простору запиту нема: тоді без знімка)
        built = build_preview(task, tid, its, comments=comments, gate_pw=pw, build='legacy', space=space, tokens=tokens)
        # ⛔ `pub` потрібен ДАЛІ — деплою (`_publish_legacy_call(…, pub, …)` — модуль запускає `vercel` у цій теці); його
        # читає лише гілка без `build_only`, тож вилучення збірки без цього рядка ламає тільки справжній
        # деплой (`NameError` посеред відповіді), а `build_only`-тести лишаються зеленими.
        pub = built['dir']
        # `ok` — ПЕРШИМ ключем: порядок ключів JSON спостережуваний (відповідь байт у байт як до
        # виносу збірки), тому результат збірки розгортається ПІСЛЯ нього.
        result = {'ok': True, **built}
        if comments_warn:
            result['comments_unavailable'] = comments_warn
        # Попередження їде в КОЖНІЙ відповіді публікації — і при build_only, і при
        # ранньому виході без Node: обгортка вже зібрана кодом процесу, і дизайнер
        # мусить побачити, що вона старіша за диск (фідбек 25.08.2026).
        stale = server_code_staleness()
        if stale:
            result['code_stale'] = stale
        if not payload.get('build_only'):
            # Ім'я проєкту — опакове (див. _vercel_project): у публічному URL не
            # має бути ні назви задачі, ні клієнта, ні тікета.
            proj = _vercel_project(tid, task)
            npx = _node_bin('npx')
            if not npx:
                # ⛔ Не мовчазний Errno 2: дизайнер має зрозуміти, що робити.
                result['deploy_error'] = NODE_MISSING_HINT
                result['deploy_blocked'] = 'no-node'
                git_autocommit(task['dir'], f'publish: {len(its)} iteration(s)')
                self._overview_sync()
                self._send_json(result)
                return
            # ⛔ URL НЕ вгадуємо, `--scope` підставляє модуль зі `state` (див. `_publish_legacy_call`): тут лише відповідь.
            # ⛔ Як у 0.8.0: УЖЕ ВДАЛИЙ деплой, після якого `OSError` (реєстр, `tasks.json`, `iterations.json`) — це `deploy_error`
            # відповіді, а не 500: `git_autocommit`, `_overview_sync` і 200 усе одно відбуваються. `url` пишеться в `result` лише
            # після `save_meta`, тож при такій відмові його в відповіді нема. `_vercel_project` — ПОЗА цим `try` (як і було).
            try:
                try:
                    res = _publish_legacy_call(task, tid, pub, proj, npx)
                except deai_modules.ModuleError as e:
                    result['deploy_error'] = _legacy_deploy_error(e)
                else:
                    url = res['url']
                    # Прив'язка задача→превʼю мусить поїхати В РЕЄСТР, а не
                    # лишитись у tasks.json (per-machine). Раніше `vercel_project`
                    # мінтився тут, а в реєстр їхав ЛИШЕ при створенні задачі —
                    # тобто ніколи для вже опублікованих: 03.08.2026 у 5 задач із 6
                    # прив'язка була тільки на диску мейнтейнера, і публікація з
                    # іншої машини видала б менеджеру друге посилання.
                    _remember_vercel_scope(tid, task, (res.get('state') or {}).get('scope'))
                    _registry_push(tid)
                    # ⛔ `iterations.json` перечитуємо ПЕРЕД записом: деплой тривав хвилини, і дизайнер
                    # міг перемкнути зелену крапку (`publish-toggle`) — запис `meta`, прочитаного на
                    # вході (з якого взято `its`), відкотив би її. Пишемо лише власні поля публікації.
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
                    # прибирання старих публікацій модуля не вдалось — публікація вдала, але людина про це знає (ОСТАННІЙ ключ)
                    if isinstance(res.get('cleanup_warning'), str) and res['cleanup_warning']:
                        result['cleanup_warning'] = res['cleanup_warning']
            except OSError as e:
                result['deploy_error'] = str(e)
            git_autocommit(task['dir'], f'publish: {len(its)} iteration(s)')
        self._overview_sync()
        self._send_json(result)


# ---------------------------------------------------------------------------------------------------
# Роздача опублікованого (етап 2а, Task 5): `GET /published/<простір>/<задача>/<файл>` віддає те, що
# `static-publish` поклав у теку публікації, — у ПІСОЧНИЦІ. Тека лежить ПОЗА простором, тож «що дозволено»
# вирішують не права ФС, а ці перевірки; кожна НЕпройдена — той самий порожній 404 (`not found`): ні шляху, ні
# причини, ні `space-json-unreadable` (статичний файл у чужій сторінці не сміє розповідати про машину).

#: Заголовки КОЖНОЇ відповіді `/published/…` (200, 304, переадресація, 404).
#:  * `sandbox …` БЕЗ `allow-same-origin` — документ дістає непрозорий (opaque) origin: сторінка превʼю не бачить
#:    ні `localStorage` канваса, ні його cookie, а її `fetch` до API канваса йде з `Origin: null`, який `do_POST`
#:    відхиляє (403, `_local_origin`). Скрипти й форми дозволені — макети живі; `allow-modals` теж: без нього
#:    `prompt()`/`confirm()` у сторінці повертають `null`/`false`, і шар коментатора в локальному перегляді
#:    лишає авторів «Anonymous», а «Видалити» нічого не робить (справжній хостинг пісочниці не ставить — локальний
#:    перегляд мусить поводитись так само). Модальні вікна тут нешкідливі: вони не дають сторінці жодного доступу;
#:  * `nosniff` — файл не стане скриптом чи HTML лише через вміст;
#:  * `Access-Control-Allow-Origin: *` — без нього в непрозорому origin не вантажаться ні `<script type=module>`
#:    (модульні скрипти завжди CORS), ні `fetch('manifest.json')`, ні шрифти.
PUBLISHED_HEADERS = (
    ('Content-Security-Policy', 'sandbox allow-scripts allow-forms allow-popups allow-modals'),
    ('X-Content-Type-Options', 'nosniff'),
    ('Access-Control-Allow-Origin', '*'),
)
PUBLISHED_PREFIX = '/published/'
#: Роздає лише ТЕ, що публікує цей модуль (інший publisher простору — ЛІГА, інший модуль — не наш файловий формат).
PUBLISHED_MODULE = 'static-publish'
#: Маркер, яким модуль позначає свої теки (`MARKER` у `modules/static-publish/server.py`): без нього теку НЕ
#: віддаємо. Налаштування `folder` може вказувати на теку з чужим вмістом (вона пройшла `folder_ok`), а `*` у
#: CORS дав би його читати будь-якій сторінці; модуль так само не чіпає немарковану теку. Паритет стереже тест.
PUBLISHED_MARKER = '.deai-published'


def _published_segments(path):
    """`/published/<простір>/<задача>/<rel…>` → `(простір, задача, [rel…], зі_слешем)` або `None`.

    `unquote` — КОЖНОГО сегмента окремо й суворо (`errors='strict'`: `%ff`, `%c0%af` — не U+FFFD, а відмова):
    `%2f` усередині сегмента лишається слешем ВСЕРЕДИНІ імені, тож не створює ні сегмента, ні виходу за теку;
    `%00` теж відмова. Кожен сегмент `rel` — непорожній, БЕЗ крапки на початку (`.`/`..`, `.deai-published`,
    `.tmp-*`/`.old-*`, будь-який прихований файл), без `/`, `\\` (роздільник Windows), `:` (диск і потік NTFS
    `a::$DATA`) і керівних символів. Порожній лише останній (завершальний `/`)."""
    if not path.startswith(PUBLISHED_PREFIX):
        return None
    try:
        parts = [unquote(p, errors='strict') for p in path[len(PUBLISHED_PREFIX):].split('/')]
    except ValueError:                                    # UnicodeDecodeError — підклас ValueError
        return None
    if len(parts) < 2:
        return None
    sid, tid, rel = parts[0], parts[1], parts[2:]
    trailing = bool(rel) and rel[-1] == ''
    if trailing:
        rel = rel[:-1]
    for seg in rel:
        if (not seg or seg.startswith('.') or any(c in '/\\:' or ord(c) < 32 or ord(c) == 127 for c in seg)):
            return None
    return sid, tid, rel, trailing


try:
    import fcntl                       # немає у Windows: там `/published` іде запасним, шляховим способом
except ImportError:
    fcntl = None

#: Прапорці відкриття файла `/published`: `O_NOFOLLOW` — остання складова не посилання; `O_NONBLOCK` — `open` на
#: FIFO без писаря не висить (інакше потік обробника стояв би вічно); `O_CLOEXEC` — дескриптор не тече в
#: підпроцеси; `O_BINARY` — Windows не перекладає кінці рядків. Прапорців, яких ОС не має, просто нема — `0`.
_PUBLISHED_OPEN = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
                   | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_BINARY', 0))
#: Прапорці відкриття ТЕКИ при обході: лише тека (`O_DIRECTORY`) і не посилання (`O_NOFOLLOW`).
_PUBLISHED_OPEN_DIR = (os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
                       | getattr(os, 'O_CLOEXEC', 0))
PUBLISHED_CHUNK = 64 * 1024


def _published_fd_path(fd):
    """Шлях, яким ЯДРО бачить відкритий дескриптор (де він справді лежить зараз, а не куди вів рядок шляху при
    відкритті): macOS — `fcntl(F_GETPATH)`, Linux — `/proc/self/fd/<fd>`. `None` — ОС не дає чи збій (довгий шлях)."""
    if fcntl is not None and hasattr(fcntl, 'F_GETPATH'):
        try:
            return os.fsdecode(fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b'\0', 1)[0]) or None
        except OSError:
            return None
    try:
        return os.readlink(f'/proc/self/fd/{fd}')
    except OSError:
        return None


#: Роздача ходить по ТЕЦІ дескрипторами (`_published_walk`), а не за шляхом, коли ОС дає `open(dir_fd=)`,
#: `stat(dir_fd=, follow_symlinks=False)`, `O_DIRECTORY`/`O_NOFOLLOW` І шлях відкритого дескриптора
#: (`F_GETPATH` / `/proc/self/fd`) — звичайно macOS і Linux. ⚠️ Це перевірка ПРИ ІМПОРТІ: де можливості нема
#: (Windows; macOS із Python < 3.9 без `F_GETPATH`; Linux без `/proc/self/fd`), ТИХО діє слабший запасний шляховий
#: спосіб (`_published_target_by_path`). Вибір — цією перевіркою, а не `except`-ом, і режим, що діє, друкується
#: рядком старту сервера (`published_mode_line`). «Закрито по збою» (нема шляху дескриптора → 404) — це лише в режимі
#: обходу дескрипторами, коли можливість була, а під час запиту дала збій (довгий шлях тощо).
_PUBLISHED_DIRFD = (os.open in os.supports_dir_fd and os.stat in os.supports_dir_fd
                    and os.stat in os.supports_follow_symlinks
                    and hasattr(os, 'O_DIRECTORY') and hasattr(os, 'O_NOFOLLOW')
                    and ((fcntl is not None and hasattr(fcntl, 'F_GETPATH')) or os.path.isdir('/proc/self/fd')))


def extra_modules_line():
    """Рядок старту сервера (stderr) про `DEAI_EXTRA_MODULES`: друга тека вбудованих модулів діє — це тестовий шов
    (модулі звідти виконуються як вбудовані), і оператор мусить бачити його в журналі. Одним рядком (шлях — через
    `repr`, переведення рядка в ньому не пройде); `None`, коли змінної нема чи вона порожня."""
    d = deai_modules.extra_dir()
    if d is None:
        return None
    return f'DEAI_EXTRA_MODULES: додаткова тека вбудованих модулів {d!r} (тестовий шов; модулі звідти діють як вбудовані)'


def published_mode_line():
    """Рядок старту сервера: який режим захисту `/published` діє (див. `_PUBLISHED_DIRFD`)."""
    if _PUBLISHED_DIRFD:
        return '/published: обхід теки дескрипторами (fd walk), закрито по збою'
    return ('/published: ЗАПАСНИЙ шляховий спосіб — ОС без dir_fd чи без шляху дескриптора (Windows; macOS Python < 3.9; '
            'Linux без /proc); слабший захист від підміни файлів посиланнями')


def _published_openat(name, flags, dir_fd=None):
    """`open(name)` відносно відкритої теки `dir_fd` (чи за шляхом, коли `None`). Окрема функція — шов для тестів:
    між попередньою перевіркою й відкриттям диск можна змінити саме тут."""
    return os.open(name, flags, dir_fd=dir_fd)


def _published_statat(name, dir_fd):
    """`lstat` імені в теці `dir_fd` (без переходу за посиланням); шов для тестів, як `_published_openat`."""
    return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)


def _published_fstat(fd):
    return os.fstat(fd)


def _published_same_dir_path(kernel, wanted):
    """Шлях дескриптора теки (`kernel`) і шлях, який ми схвалили (`wanted`, `realpath`), — те саме місце. Рівність
    тексту; де ОС шлях віддає зі справжнім регістром диска (macOS: `F_GETPATH`), а `realpath` лишає написане в
    налаштуванні (`~/Deai-Published`) чи в іншій юнікодній формі, — рівність після `casefold` і NFC. Порівняння
    ТЕКСТОМ, а не `samefile`: підміну предка посиланням `samefile` не відрізнив би (обидва шляхи вели б туди ж)."""
    if kernel == wanted:
        return True
    return (fcntl is not None and hasattr(fcntl, 'F_GETPATH')
            and _fold(kernel) == _fold(wanted))


#: Що вже записано в журнал про розбіжність шляху теки публікації: `{(realpath, шлях_дескриптора_чи_None)}`. Один рядок
#: на пару за життя процесу (сторінка тягне десятки файлів — журнал не засмічуємо), обмежено, щоб не ріс без меж.
_PUBLISHED_WARNED = set()
_PUBLISHED_WARNED_MAX = 64


def _published_log_mismatch(real_folder, kernel):
    """ОДИН рядок у stderr сервера (як решта журналів, НІКОЛИ не у відповіді): шлях теки за `realpath` і шлях її
    відкритого дескриптора розійшлись, тож роздача (закрито по збою) відповідає 404. Таке буває на зовнішніх томах,
    FUSE, iCloud — без цього рядка оператор бачить лише порожні 404."""
    key = (real_folder, kernel)
    if key in _PUBLISHED_WARNED or len(_PUBLISHED_WARNED) >= _PUBLISHED_WARNED_MAX:
        return
    _PUBLISHED_WARNED.add(key)
    what = ('шлях відкритого дескриптора недоступний' if kernel is None
            else f'шлях відкритого дескриптора {kernel!r} не збігається зі схваленим')
    print(f'published: тека {real_folder!r}: {what} — /published віддає 404 (звірка закрита по збою)',
          file=sys.stderr)


def _published_name_ok(name):
    """Імʼя ОДНІЄЇ складової для `openat`: не порожнє, не `.`/`..`, без `/` і NUL. Другий замок за
    `_published_segments` (яка й так не пропустить такого): обхід дескрипторами не сміє залежати від того, що
    викликач почистив імена, бо `..` відносно теки-дескриптора виводить за межі теки без жодного посилання."""
    return (isinstance(name, str) and name not in ('', '.', '..') and '/' not in name and '\0' not in name)


def _published_open_file(name, dir_fd):
    """Відкрити файл `name` теки `dir_fd` для віддачі: `(fd, fstat)` або `None`. Кидає `OSError`, коли файла нема.

    Порядок і причини: (1) `lstat` ДО відкриття — звичайний файл (`S_ISREG`) з `st_nlink == 1`: жорстке посилання
    на чужий файл відсікається ще тут; (2) `open` з `O_NOFOLLOW|O_NONBLOCK` відносно теки (імʼя, а не шлях: підміна
    предка нічого не дає); (3) `fstat` ВІДКРИТОГО — знов `S_ISREG` і `st_nlink == 1` (FIFO, підміна на пристрій чи
    жорстке посилання за мить між (1) і (2)) і ТОЙ САМИЙ `(st_dev, st_ino)`, що в (1): між `lstat` і `open` імʼя
    не вказало на інший файл. Підміна ПІСЛЯ (3) уже нічого не змінює: віддається відкритий дескриптор."""
    st0 = _published_statat(name, dir_fd)
    if not (stat.S_ISREG(st0.st_mode) and st0.st_nlink == 1):
        return None
    fd = _published_openat(name, _PUBLISHED_OPEN, dir_fd)
    try:
        st = _published_fstat(fd)
        if (stat.S_ISREG(st.st_mode) and st.st_nlink == 1
                and (st.st_dev, st.st_ino) == (st0.st_dev, st0.st_ino)):
            opened, fd = (fd, st), None                # власність дескриптора переходить викликачу
            return opened
    finally:
        if fd is not None:
            os.close(fd)
    return None


def _published_walk(folder, tid, rel, trailing, folder_check):
    """Обхід теки ДЕСКРИПТОРАМИ, ніколи за шляхом: `'redirect'`, `(імʼя_файла, (fd, fstat))` або `None`. Не кидає
    (`OSError` — `None`; усі проміжні дескриптори закриваються в `finally`). Це режим, що діє, коли ОС має потрібні
    можливості (`_PUBLISHED_DIRFD`, перевіряється при імпорті); де їх нема, роздача взагалі не сюди йде (запасний
    шляховий спосіб, слабший). ЗАКРИТО ПО ЗБОЮ в цьому режимі: шлях дескриптора теки недоступний чи не збігається —
    відмова (і рядок у журналі), а не відкат на `realpath`.

      0) імена — кожне одна складова (`_published_name_ok`), ДО першого `openat`;
      a) `folder` — те, що схвалив `folder_ok`; сама тека може бути посиланням — розвʼязуємо ОДИН раз
         (`realpath`), відкриваємо, і шлях ВІДКРИТОГО дескриптора (ядро) мусить збігатися з розвʼязаним
         (`_published_same_dir_path`): предка підмінили посиланням між `realpath` і `open` — дескриптор лежить деінде.
         Потім `folder_check(шлях_дескриптора)` — повторна `folder_ok` на ТЕЦІ, яку справді відкрито: посилання-предка
         могли перенаправити ще ДО `realpath`, і тоді обидва шляхи збігаються, але вказують на чужу теку;
      b) `<задача>` — `open(O_DIRECTORY|O_NOFOLLOW, dir_fd=…)` (посилання на задачу — відмова); маркер модуля —
         `lstat` у ЦІЙ теці, звичайний файл;
      c) кожна проміжна тека — так само відносно попередньої; кожне імʼя — одна складова, шляху нема;
      d) останнє імʼя — `lstat`: тека → переадресація без `/`, з `/` — її `index.html`; звичайний файл — лише без `/`;
         файл відкриває `_published_open_file`.
    Тож підмінити можна що завгодно ПІСЛЯ відповідного відкриття — вже відкрите не зміниться; а що ПЕРЕД — стане
    `ELOOP`/`ENOTDIR`/різним `ino` і відмовою."""
    if not all(_published_name_ok(n) for n in (tid, *rel)):
        return None
    fds = []
    try:
        real_folder = os.path.realpath(folder)
        fd0 = _published_openat(real_folder, _PUBLISHED_OPEN_DIR)
        fds.append(fd0)
        kernel = _published_fd_path(fd0)
        if kernel is None or not _published_same_dir_path(kernel, real_folder):
            _published_log_mismatch(real_folder, kernel)
            return None
        if not folder_check(kernel):
            return None
        cur = _published_openat(tid, _PUBLISHED_OPEN_DIR, fd0)
        fds.append(cur)
        if not stat.S_ISREG(_published_statat(PUBLISHED_MARKER, cur).st_mode):
            return None
        for seg in rel[:-1]:
            cur = _published_openat(seg, _PUBLISHED_OPEN_DIR, cur)
            fds.append(cur)
        name = 'index.html'
        if rel:
            last = rel[-1]
            kind = _published_statat(last, cur).st_mode
            if stat.S_ISDIR(kind):
                if not trailing:
                    return 'redirect'
                cur = _published_openat(last, _PUBLISHED_OPEN_DIR, cur)
                fds.append(cur)
            elif stat.S_ISREG(kind) and not trailing:
                name = last
            else:
                return None
        elif not trailing:
            return 'redirect'
        opened = _published_open_file(name, cur)
        return None if opened is None else (name, opened)
    except OSError:
        return None
    finally:
        for fd in fds:
            os.close(fd)


# ---- запасний шляховий спосіб (ОС без `dir_fd`: Windows) ----

def _published_marked(base):
    """У теці `base` є маркер модуля — ЗВИЧАЙНИЙ файл (посилання на чужий файл маркером не вважаємо)."""
    try:
        return stat.S_ISREG(os.lstat(os.path.join(base, PUBLISHED_MARKER)).st_mode)
    except OSError:
        return False


def _published_real_dir(path):
    """Канонічний шлях теки `path` в тій самій формі, що й `_published_fd_path` файлів (де ОС її дає), інакше
    `realpath`. ⚠️ Запасний шлях: збій відкриття теки мовчки веде до `realpath` (посилання, що підмінило теку
    задачі, розвʼяжеться, і «своєю» стане чужа тека) — на ОС з `dir_fd` цього нема (`_published_walk`)."""
    fd = None
    try:
        fd = os.open(path, _PUBLISHED_OPEN_DIR)
        real = _published_fd_path(fd)
    except OSError:
        real = None
    finally:
        if fd is not None:
            os.close(fd)
    return real or os.path.realpath(path)


def _published_inside(real_base, real):
    """Шлях `real` лежить у `real_base` (чи дорівнює йому); обидва вже канонічні."""
    real, base = os.path.normcase(real), os.path.normcase(real_base)
    return real == base or real.startswith(base + os.sep)


def open_published_file(target, real_base):
    """ЗАПАСНИЙ спосіб (ОС без `dir_fd`): відкрити `target` ОДИН раз і перевірити відкрите: `(fd, fstat)` або
    `None` (404). Не кидає. `O_NOFOLLOW` (де є) і `O_NONBLOCK`; `fstat`: звичайний файл з `st_nlink == 1`; шлях
    дескриптора (де ОС його дає) чи, без нього, `realpath(target)` ПІСЛЯ відкриття — усередині `real_base`.
    ⚠️ Слабший за `_published_walk`: підміна проміжної теки чи жорстке посилання, додане й прибране за мить,
    тут не ловляться повністю (немає ні відкриття відносно теки, ні порівняння `ino` з попереднім `lstat`)."""
    fd = None
    try:
        fd = os.open(target, _PUBLISHED_OPEN)
        st = os.fstat(fd)
        if stat.S_ISREG(st.st_mode) and st.st_nlink == 1:
            real = _published_fd_path(fd) or os.path.realpath(target)
            if _published_inside(real_base, real):
                opened, fd = (fd, st), None            # власність дескриптора переходить викликачу
                return opened
    except OSError:
        pass
    finally:
        if fd is not None:
            os.close(fd)
    return None


def _published_target_by_path(folder, tid, rel, trailing, sid):
    """Запасний обхід за шляхом (ОС без `dir_fd`): `('redirect', url)`, `('file', шлях, канонічна_тека_задачі)` або
    `None`. Перевірки тут РАННІ й обходяться підміною; рішення про файл — `open_published_file`."""
    base = os.path.join(folder, tid)
    if os.path.islink(base) or not os.path.isdir(base) or not _published_marked(base):
        return None
    real_base = _published_real_dir(base)
    target = base
    for seg in rel:
        target = os.path.join(target, seg)
        if os.path.islink(target):
            return None
    if os.path.isdir(target):
        if not trailing:
            return 'redirect', _published_redirect_url(sid, tid, rel)
        target = os.path.join(target, 'index.html')
        if os.path.islink(target):
            return None
    elif trailing:
        return None
    if os.path.isfile(target):
        return 'file', target, real_base
    return None


def _published_redirect_url(sid, tid, rel):
    return ''.join(['/published/', quote(sid, safe=''), '/', quote(tid, safe=''), '/',
                    *(quote(seg, safe='') + '/' for seg in rel)])


def published_target(path):
    """Що відповісти на `GET path` (шлях БЕЗ `?query`): `('redirect', '<шлях>/')`; `('opened', імʼя, (fd, fstat))` —
    файл УЖЕ відкрито й перевірено (ОС з `dir_fd`: macOS, Linux; fd віддається викликачу); `('file', шлях,
    канонічна_тека_задачі)` — запасний спосіб (Windows: відкриває викликач через `open_published_file`); або `None`
    (404). НІКОЛИ не кидає: будь-який виняток (зіпсований `space.json`, реєстр, `ModuleError`, помилка ФС) — теж `None`.

    Порядок — від дешевого до дорогого, і ДО першого читання диска сегменти вже синтаксично чисті:
      1. сегменти (`_published_segments`), id простору — `spaces.SPACE_ID_RE`, id задачі — `publish_id_ok` (те
         саме правило, що в диспетчері: опублікувати можна лише такі id, тож інші й не віддаємо);
      2. ПРОСТІР — З URL (реєстр, лише читання), а не простір запиту: `X-Canvas-Task`, поточний простір машини
         і навіть нечитабельний реєстр запиту тут нічого не вирішують;
      3. його publisher — `static-publish` (простір із ЛІГА чи без модуля — 404);
      4. тека — `published_root` ЗАНОВО на кожен запит (не `publish_local.path`: налаштування могли змінити), і
         `folder_ok` на КОЖНУ видачу (`folder_inputs()` — раз на запит);
      5. сам обхід: `_published_walk` (дескрипторами, закрито по збою) або, де ОС не дає `dir_fd`, запасний
         `_published_target_by_path`. Вибір — за можливостями ОС (`_PUBLISHED_DIRFD`), а не за винятком.
    ⚠️ Передумови й межі: тека публікації не змінюється ПІД ЧАС обходу в бік «чужого» — це обіцяє лише обхід
    дескрипторами; він діє, коли ОС має потрібні можливості (перевірка ПРИ ІМПОРТІ, `_PUBLISHED_DIRFD`; режим друкується
    рядком старту), інакше ТИХО працює запасний спосіб — слабший (див. його докстрінги). Повторна `folder_ok` на
    відкритій теці (`folder_check` у обході) є лише в режимі дескрипторів. Файл, що вже відкритий, віддається
    таким, яким відкрито, навіть якщо його потім видалили чи замінили."""
    try:
        segs = _published_segments(path)
        if segs is None:
            return None
        sid, tid, rel, trailing = segs
        if not spaces.SPACE_ID_RE.fullmatch(sid) or not publish_id_ok(tid):
            return None
        space = next((sp for sp in spaces.read_registry()['spaces'] if sp.get('id') == sid), None)
        if space is None:
            return None
        prov = deai_modules.provider('publish', space)
        if not isinstance(prov, deai_modules.Module) or prov.id != PUBLISHED_MODULE:
            return None
        folder = deai_modules.published_root(space, prov)
        inputs = deai_modules.folder_inputs()
        if not isinstance(folder, str) or not folder or inputs is None:
            return None
        if not deai_modules.folder_ok(space, folder, reg=inputs[0], task_dirs=inputs[1])[0]:
            return None
        if not _PUBLISHED_DIRFD:
            return _published_target_by_path(folder, tid, rel, trailing, sid)
        walked = _published_walk(folder, tid, rel, trailing,
                                 lambda opened: deai_modules.folder_ok(space, opened, reg=inputs[0], task_dirs=inputs[1])[0])
        if walked is None:
            return None
        if walked == 'redirect':
            return 'redirect', _published_redirect_url(sid, tid, rel)
        return 'opened', walked[0], walked[1]
    except Exception:  # noqa: BLE001 — статичний файл для чужої сторінки не розповідає, що саме зламалось
        return None


# ---------------------------------------------------------------------------------------------------
# Роздача файлів браузерного адаптера модуля ролі `comments` (етап 2b-2, Task 1; свої модулі — етап 3c):
# `GET /api/module-client/<модуль>/<файл>` (вбудований) і `GET /api/module-client/<простір>/<модуль>/<файл>` (СВІЙ модуль простору).
# Адаптер виконується в сторінках канваса (той самий origin, що API), тож віддаємо РІВНО те, що модуль оголосив у `client` свого
# маніфесту, і лише для справного модуля ролі `comments`: жодного файла за межами списку, жодного прихованого, жодного шляху
# вглиб. Свій модуль роздається зі ЗНІМКА довіри (`mod.dir` свого модуля — тека знімка, а не тека простору), тож адаптер
# недовіреного модуля не віддається ніколи, а правка теки після довіри не доходить до сторінок. Відкриття — з тим самим захистом,
# що й `/published` (`_published_open_file`: звичайний файл, ні посилання, ні жорсткого посилання, `O_NOFOLLOW`, дескриптор).
# Файли — не від задачі (вбудований ресурс чи знімок), тому маршрут обробляється ДО `_take_task`, як `/published/`: заголовок
# `X-Canvas-Task` на ньому не діє, а зіпсований реєстр його не вкладає. Усі відмови — один і той самий 404 зі сталим тілом.
MODULE_CLIENT_PREFIX = '/api/module-client/'
MODULE_CLIENT_HEADERS = (('X-Content-Type-Options', 'nosniff'),)
MODULE_CLIENT_NOT_FOUND = b'not found\n'


def module_client_target(path):
    """`(Module, імʼя файла)` для `path` (БЕЗ `?query`) виду `/api/module-client/<модуль>/<файл>` (вбудований) чи
    `/api/module-client/<простір>/<модуль>/<файл>` (свій модуль простору, 3c — зі знімка) або `None`. НІКОЛИ не кидає. Кожна
    складова — рівно одна, розкодована суворо (`%ff`, `%00`, `%2f` усередині складової не дають ні виходу за теку, ні другої
    складової) і придатна за шаблонами (`SPACE_ID_RE`, `ID_RE`, `CLIENT_RE`: ні `.`, ні `..`, ні прихованих, ні регістру-двійника);
    модуль — з каталогу (для адреси з простором — каталогу ЦЬОГО простору, і лише СВІЙ модуль; без простору — лише вбудований),
    `status == 'ok'`, роль `comments`, файл — зі списку `client`."""
    try:
        if not path.startswith(MODULE_CLIENT_PREFIX):
            return None
        parts = [unquote(p, errors='strict') for p in path[len(MODULE_CLIENT_PREFIX):].split('/')]
        sp = None
        if len(parts) == 3:                             # свій модуль: /<простір>/<модуль>/<файл>
            sid, mid, name = parts
            if not spaces.SPACE_ID_RE.fullmatch(sid):
                return None
            sp = next((s for s in spaces.read_registry()['spaces'] if s['id'] == sid), None)
            if sp is None:
                return None
        elif len(parts) == 2:
            mid, name = parts
        else:
            return None
        if not deai_modules.ID_RE.fullmatch(mid) or not deai_modules.CLIENT_RE.fullmatch(name):
            return None
        # Маршрут стоїть ДО `_take_task`: простір запиту не зафіксовано, а перше (холодне) завантаження довіреного знімка
        # виконує верхній рівень його `server.py` — тож завантажуємо його в просторі, якому модуль належить
        # (`_load_own` успадковує простір запиту; без цього модуль бачив би «не зафіксовано» = інтеграції ввімкнені)
        with spaces.request_space(sp['id'] if sp else None):
            mod = deai_modules.catalog(sp).get(mid)
        if (mod is None or mod.status != 'ok' or 'comments' not in mod.roles or name not in mod.client
                or mod.origin != ('space' if sp else 'builtin')):
            return None
        return mod, name
    except Exception:  # noqa: BLE001 — статичний файл не розповідає, що саме зламалось
        return None


def open_module_client(mod, name):
    """`(fd, fstat)` відкритого файла `name` теки модуля `mod` або `None` (404). НЕ кидає. ОС з `dir_fd` (macOS, Linux):
    теку відкрито `O_DIRECTORY|O_NOFOLLOW` (тека-посилання — відмова), файл — `_published_open_file` відносно її
    дескриптора; без `dir_fd` (Windows) — запасний `open_published_file`. Власність дескриптора переходить викликачу."""
    try:
        if _PUBLISHED_DIRFD:
            dfd = _published_openat(mod.dir, _PUBLISHED_OPEN_DIR)
            try:
                return _published_open_file(name, dfd)
            finally:
                os.close(dfd)
        return open_published_file(os.path.join(mod.dir, name), _published_real_dir(mod.dir))
    except OSError:
        return None


# ---------------------------------------------------------------------------------------------------
# Роздача панелей інструментів модулів (M1, Task 3): `GET /api/module-ui/<простір>/<модуль>/<шлях>` і набір панелі
# `GET /api/module-ui-kit/<імʼя>`. Панель — сторінка стороннього модуля в `<iframe sandbox>` оболонки: непрозорий origin, скрипти
# без доступу до оболонки, мережа закрита (`connect-src 'none'`), а все спілкування — через `postMessage` мосту (`bridge.js`).
# Віддаємо лише теку панелі якогось ІНСТРУМЕНТА модуля (префікс директорій його `panel`) і лише дозволені розширення — `server.py`,
# `module.json` і решта теки недосяжні. Свій модуль — зі знімка довіри (`m.dir`), тож правка теки після довіри сторінок не
# досягає. Маршрути стоять ДО `_take_task`, як `/api/module-client/`: заголовок задачі й реєстр на них не діють; усі відмови —
# той самий 404 зі сталим тілом. Лише GET (HEAD, як і для module-client, окремо не обробляється).
MODULE_UI_PREFIX = '/api/module-ui/'
MODULE_UI_KIT_PREFIX = '/api/module-ui-kit/'
MODULE_UI_TYPES = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
                   '.png': 'image/png', '.json': 'application/json', '.woff2': 'font/woff2'}
MODULE_UI_SEG_RE = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}')
MODULE_UI_HEADERS = (
    ('Content-Security-Policy', "sandbox allow-scripts allow-forms; default-src 'self' 'unsafe-inline' data:; "
                                "connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'"),
    ('X-Content-Type-Options', 'nosniff'),
    ('Access-Control-Allow-Origin', '*'),
    ('Referrer-Policy', 'no-referrer'),
)
MODULE_KIT_FILES = ('kit.css', 'bridge.js')
MODULE_KIT_DIR = os.path.join(APP_DIR, 'module-kit')
#: Підключення набору — одразу після `<!doctype …>` (чи на початок): панель отримує мост і стилі без жодного коду автора.
KIT_TAGS = ('<link rel="stylesheet" href="/api/module-ui-kit/kit.css">'
            '<script src="/api/module-ui-kit/bridge.js"></script>')
_DOCTYPE_RE = re.compile(rb'\A(?:\xef\xbb\xbf)?\s*<!doctype[^>]*>', re.IGNORECASE)


def module_ui_target(path):
    """`(Module, [складові], вид)` для `path` (БЕЗ `?query`) виду `/api/module-ui/<простір>/<модуль>/<складова>/…` або `None`.
    НІКОЛИ не кидає. Кожна складова розкодована суворо (`%ff` → відмова; `%2f`, `%5c`, `%00` усередині складової, порожня — відмова),
    придатна за шаблонами (простір `SPACE_ID_RE` і є в реєстрі, модуль `ID_RE`, файлові складові `MODULE_UI_SEG_RE`: ні `.`/`..`,
    ні прихованих). Файлових складових 2..6. Модуль — `deai_modules.ext_module` (справний, api 2, явно увімкнений, з
    інструментами) у просторі з URL. Дозволено лише шлях у теці панелі якогось інструмента й розширення з `MODULE_UI_TYPES`;
    вид — `'html'` чи `'asset'`."""
    try:
        if not path.startswith(MODULE_UI_PREFIX):
            return None
        parts = [unquote(p, errors='strict') for p in path[len(MODULE_UI_PREFIX):].split('/')]
        if any(p == '' or '/' in p or '\\' in p or '\0' in p for p in parts) or not 4 <= len(parts) <= 8:
            return None
        sid, mid, segs = parts[0], parts[1], parts[2:]
        if not spaces.SPACE_ID_RE.fullmatch(sid) or not deai_modules.ID_RE.fullmatch(mid):
            return None
        if not all(MODULE_UI_SEG_RE.fullmatch(p) for p in segs):
            return None
        ext = os.path.splitext(segs[-1])[1].lower()
        if ext not in MODULE_UI_TYPES:
            return None
        sp = next((s for s in spaces.read_registry()['spaces'] if s['id'] == sid), None)
        if sp is None:
            return None
        # як у `module_client_target`: маршрут до `_take_task`, а завантаження довіреного знімка виконує код модуля — у його просторі
        with spaces.request_space(sp['id']):
            mod = deai_modules.ext_module(sp, mid)
        if mod is None:
            return None
        for t in mod.tools:
            d = t['panel'].split('/')[:-1]
            if len(segs) > len(d) and segs[:len(d)] == d:
                return mod, segs, ('html' if ext == '.html' else 'asset')
        return None
    except Exception:  # noqa: BLE001 — статичний файл не розповідає, що саме зламалось
        return None


def open_module_ui(mod, segs):
    """`(fd, fstat)` відкритого файла `segs` теки модуля `mod` або `None` (404). НЕ кидає. ОС з `dir_fd`: кожну теку шляху
    відкрито `O_DIRECTORY|O_NOFOLLOW` відносно попередньої (тека-посилання — відмова), файл — `_published_open_file` відносно
    останньої (звичайний файл, `nlink == 1`, `O_NOFOLLOW`); проміжні дескриптори закриваються. Без `dir_fd` (Windows) — запасний
    `open_published_file` ПІСЛЯ перевірки, що кожна тека шляху — справжня тека, а не посилання. Власність дескриптора — викликачу."""
    try:
        if _PUBLISHED_DIRFD:
            fds = []
            try:
                cur = _published_openat(mod.dir, _PUBLISHED_OPEN_DIR)
                fds.append(cur)
                for seg in segs[:-1]:
                    if not _published_name_ok(seg):
                        return None
                    cur = _published_openat(seg, _PUBLISHED_OPEN_DIR, cur)
                    fds.append(cur)
                if not _published_name_ok(segs[-1]):
                    return None
                return _published_open_file(segs[-1], cur)
            finally:
                for fd in fds:
                    os.close(fd)
        walk = mod.dir
        for seg in segs[:-1]:
            walk = os.path.join(walk, seg)
            if not stat.S_ISDIR(os.lstat(walk).st_mode):
                return None
        return open_published_file(os.path.join(mod.dir, *segs), _published_real_dir(mod.dir))
    except OSError:
        return None


def open_module_kit(name):
    """`(fd, fstat)` файла набору панелі `name` (рівно з `MODULE_KIT_FILES`) або `None`. НЕ кидає."""
    if name not in MODULE_KIT_FILES:
        return None
    return open_module_ui(deai_modules.Module('kit', dir=MODULE_KIT_DIR), [name])


def module_ui_html(opened):
    """Тіло html-панелі з набором: читає відкритий дескриптор (≤ `MAX_PANEL_BYTES`, більше — `None`) і вставляє `KIT_TAGS`
    після початкового `<!doctype …>` (BOM лишається першим), інакше — на початок (після BOM). Закриває дескриптор."""
    fd, st = opened
    try:
        with os.fdopen(fd, 'rb') as f:
            fd = None
            if st.st_size > deai_modules.MAX_PANEL_BYTES:
                return None
            data = f.read(deai_modules.MAX_PANEL_BYTES + 1)
    finally:
        if fd is not None:
            os.close(fd)
    if len(data) > deai_modules.MAX_PANEL_BYTES:
        return None
    m = _DOCTYPE_RE.match(data)
    at = m.end() if m else (3 if data.startswith(b'\xef\xbb\xbf') else 0)
    return data[:at] + KIT_TAGS.encode('ascii') + data[at:]


def trust_seam_warning():
    """Рядок для журналу старту, коли діє тестовий шов `DEAI_TRUST_CONFIRM` (довіра без системного вікна), інакше `None`."""
    v = module_trust.seam_value()
    if v is None:
        return None
    return f'⚠ DEAI_TRUST_CONFIRM={v}: own-module trust is answered WITHOUT the system window (test seam)'


def make_server(port=0):
    handler = Handler
    # /it-assets/<it>/... — статика итераций текущей задачи
    class Routed(handler):
        def _send_iter_file(self, target, extra_headers=(), utf8=False, opened=None, ctype=None):
            # `extra_headers` — пари (імʼя, значення) на КОЖНУ відповідь цього файла, і на 304 теж (`/published`:
            # захисні заголовки сторінки в пісочниці; 304 без них лишив би кеш без захисту). `utf8` — текстовим
            # типам дописати `; charset=utf-8` (`/published`: сторінки збірка пише в UTF-8, а без `<meta charset>`
            # у макеті браузер читав би їх як windows-1252 — гейт-оверлей, який вкладаємо МИ, виходив кракозябрами;
            # Vercel віддає статику так само, з charset). `opened` — `(fd, fstat)` від обходу `/published`
            # (`_published_walk` чи `open_published_file`): файл уже ВІДКРИТО й перевірено, тож ETag, довжина й тіло беруться з того самого
            # дескриптора (а не з другого `open` за шляхом), тіло йде шматками `PUBLISHED_CHUNK`; дескриптор
            # закривається тут за будь-якого виходу.
            # ВАЛІДАТОР. Без нього `Cache-Control: no-cache` (його дописує
            # `end_headers`) означає «тягни заново ЩОРАЗУ»: кожне відкриття
            # макета перекачувало кожен шрифт і кожну іконку з кодом 200. Для
            # Для макетів ЛІГИ це переверстка тексту рівно у вікні анімації входу — «весь
            # інтерфейс трохи дьоргається» на першому вході, і в того, у кого
            # шрифти теплі, не відтворюється взагалі: дефект виглядає як баг
            # макета, хоч це кеш сервера.
            #
            # ETag із mtime_ns+розміру, і САМЕ ETag, а не `Last-Modified`:
            # у `If-Modified-Since` секундна точність, а дизайнер править файл
            # по кілька разів на секунду — правка в тій самій секунді читалась
            # би як «не мінялось», і сервер віддав би застаріле. Наносекунди
            # такої дірки не мають. `no-cache` лишається: перезвірка щоразу,
            # але без тіла.
            stream = st = None
            if opened is not None:
                try:
                    stream, st = os.fdopen(opened[0], 'rb'), opened[1]
                except BaseException:
                    os.close(opened[0])
                    raise
            try:
                if opened is None:
                    st = os.stat(target)
                etag = '"%x-%x"' % (st.st_mtime_ns, st.st_size)
            except OSError:
                etag = None
            try:
                if etag:
                    inm = self.headers.get('If-None-Match', '')
                    if etag in [x.strip() for x in inm.split(',') if x.strip()]:
                        self.send_response(304)
                        self.send_header('ETag', etag)
                        for key, value in extra_headers:
                            self.send_header(key, value)
                        self.end_headers()
                        return
                if stream is None:
                    with open(target, 'rb') as f:
                        data = f.read()
                self._send_iter_body(target, st, etag, data if stream is None else None, stream,
                                     extra_headers, utf8, ctype)
            finally:
                if stream is not None:
                    stream.close()

        def _send_iter_body(self, target, st, etag, data, stream, extra_headers, utf8, forced=None):
            """200 для `_send_iter_file`: заголовки й тіло — з пам'яті (`data`) або шматками зі `stream`."""
            self.send_response(200)
            if etag:
                self.send_header('ETag', etag)
            # MIME matters: ES-module <script type=module> is refused by
            # the browser without a JS content-type. guess_type covers
            # .js/.css/.json/.svg/.otf/.woff2 → multi-file builds (Angular)
            # render, not just single-file HTML mockups.
            ctype = forced or self.guess_type(target)       # `forced` — точний тип від виклику (панелі модулів)
            if isinstance(ctype, tuple):  # py<3.11 returns (type, enc)
                ctype = ctype[0]
            if not forced and (target.endswith('.js') or target.endswith('.mjs')):
                ctype = 'text/javascript'
            if utf8 and ctype and ctype.startswith('text/'):
                ctype += '; charset=utf-8'
            self.send_header('Content-Type', ctype or 'application/octet-stream')
            self.send_header('Content-Length', str(len(data) if stream is None else st.st_size))
            for key, value in extra_headers:
                self.send_header(key, value)
            self.end_headers()
            if stream is None:
                self.wfile.write(data)
                return
            left = st.st_size                       # рівно стільки, скільки обіцяв Content-Length
            while left > 0:
                chunk = stream.read(min(PUBLISHED_CHUNK, left))
                if not chunk:                       # файл усох під час віддачі: обіцянку не виконати
                    self.close_connection = True
                    return
                self.wfile.write(chunk)
                left -= len(chunk)

        def _send_published_404(self):
            """404 `/published/…`: ті самі захисні заголовки й ПОРОЖНЯ відповідь — без шляху, без причини."""
            body = b'not found\n'
            self.send_response(404)
            for key, value in PUBLISHED_HEADERS:
                self.send_header(key, value)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_module_client_404(self):
            """404 `/api/module-client/…`: СТАЛЕ тіло й `nosniff` — без шляху, без причини (немає модуля, не та роль, файл
            не оголошено, підмінений чи зник — усе однаково)."""
            self.send_response(404)
            for key, value in MODULE_CLIENT_HEADERS:
                self.send_header(key, value)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(MODULE_CLIENT_NOT_FOUND)))
            self.end_headers()
            self.wfile.write(MODULE_CLIENT_NOT_FOUND)

        def _serve_module_client(self):
            """`GET /api/module-client/<модуль>/<файл>` чи `…/<простір>/<модуль>/<файл>` для свого модуля
            (`module_client_target` → `open_module_client`; відповідь — `_send_iter_file`: ETag/304 з відкритого
            дескриптора, `text/javascript; charset=utf-8`, `nosniff`)."""
            found = module_client_target(self.path.partition('?')[0])
            opened = open_module_client(*found) if found else None
            if opened is None:
                self._send_module_client_404()
                return
            try:
                self._send_iter_file(os.path.join(found[0].dir, found[1]), extra_headers=MODULE_CLIENT_HEADERS,
                                     utf8=True, opened=opened)
            except OSError:
                if self._resp_started:                  # обрив посеред віддачі: другу відповідь поверх не шлемо
                    self.close_connection = True
                else:
                    self._send_module_client_404()

        def _send_module_ui_404(self):
            """404 `/api/module-ui…`: СТАЛЕ тіло, `nosniff` і решта захисних заголовків — без шляху й причини."""
            self.send_response(404)
            for key, value in MODULE_UI_HEADERS:
                self.send_header(key, value)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(MODULE_CLIENT_NOT_FOUND)))
            self.end_headers()
            self.wfile.write(MODULE_CLIENT_NOT_FOUND)

        def _send_module_ui_file(self, opened, target, ctype):
            """Віддати відкритий файл `target` з типом `ctype` і `MODULE_UI_HEADERS` (ETag/304 — `_send_iter_file`); обрив до початку
            відповіді — 404, посеред — закрити зʼєднання."""
            try:
                self._send_iter_file(target, extra_headers=MODULE_UI_HEADERS, utf8=True, opened=opened, ctype=ctype)
            except OSError:
                if self._resp_started:
                    self.close_connection = True
                else:
                    self._send_module_ui_404()

        def _serve_module_ui(self):
            """`GET /api/module-ui/<простір>/<модуль>/<шлях>` (`module_ui_target` → `open_module_ui`). html — з набором, без кешу;
            решта — `_send_iter_file` з точним типом із `MODULE_UI_TYPES`."""
            found = module_ui_target(self.path.partition('?')[0])
            opened = open_module_ui(found[0], found[1]) if found else None
            if opened is None:
                self._send_module_ui_404()
                return
            mod, segs, kind = found
            if kind != 'html':
                self._send_module_ui_file(opened, os.path.join(mod.dir, *segs),
                                          MODULE_UI_TYPES[os.path.splitext(segs[-1])[1].lower()])
                return
            try:
                body = module_ui_html(opened)
                if body is None:
                    self._send_module_ui_404()
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                for key, value in MODULE_UI_HEADERS:
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                if self._resp_started:
                    self.close_connection = True
                else:
                    self._send_module_ui_404()

        def _serve_module_ui_kit(self):
            """`GET /api/module-ui-kit/<імʼя>`: лише `MODULE_KIT_FILES` з `app/module-kit/`."""
            try:
                name = unquote(self.path.partition('?')[0][len(MODULE_UI_KIT_PREFIX):], errors='strict')
            except UnicodeDecodeError:
                name = None
            opened = open_module_kit(name) if name else None
            if opened is None:
                self._send_module_ui_404()
                return
            self._send_module_ui_file(opened, os.path.join(MODULE_KIT_DIR, name),
                                      'text/css' if name.endswith('.css') else 'text/javascript')

        def _serve_published(self):
            """`GET /published/…` (рішення — `published_target`; кожна відмова — `_send_published_404`).
            Переадресація зберігає `?query`: кладемо його в `Location` ПЕРЕКОДОВАНИМ (`#`, пробіл і не-ASCII
            стають `%XX`), а шлях — зібраним з уже перевірених сегментів, тож `Location` завжди лишається
            у `/published/…` на тому ж origin (не `//хост`, не CRLF)."""
            path, _, query = self.path.partition('?')
            found = published_target(path)
            if found is None:
                self._send_published_404()
                return
            kind, value = found[:2]
            if kind == 'redirect':
                if query:
                    value += '?' + quote(query, safe="%/?:@&=+$,;!*'()~")
                self.send_response(301)
                self.send_header('Location', value)
                self.send_header('Content-Length', '0')
                for key, hv in PUBLISHED_HEADERS:
                    self.send_header(key, hv)
                self.end_headers()
                return
            if kind == 'opened':                    # ОС з `dir_fd`: файл уже відкрито й перевірено обходом дескрипторами
                opened = found[2]
            else:                                   # запасний шляховий спосіб: відкриваємо тут, раз, і перевіряємо відкрите
                opened = open_published_file(value, found[2])
            if opened is None:                      # зник, підмінений посиланням/FIFO/жорстким посиланням, чи поза текою
                self._send_published_404()
                return
            try:
                self._send_iter_file(value, extra_headers=PUBLISHED_HEADERS, utf8=True, opened=opened)
            except OSError:
                # обрив під час віддачі: 404, якщо відповідь ще не почата; почату обриваємо (друга відповідь поверх
                # першої зіпсувала б потік)
                if self._resp_started:
                    self.close_connection = True
                else:
                    self._send_published_404()

        def _serve_from_iteration(self, it, rel):
            _, task = self._current_task()
            if not task:
                return False
            target = os.path.realpath(os.path.join(
                task['dir'], 'iterations', it, rel))
            base = os.path.realpath(os.path.join(task['dir'], 'iterations'))
            if target.startswith(base + os.sep) and os.path.isfile(target):
                self._send_iter_file(target)
                return True
            return False

        def _referer_context(self):
            """`(задача, ітерація, простір)`, із яких прийшов запит (Referer); `(None, None, None)` —
            Referer не годиться. НІЧОГО не міняє на запиті: задачу й простір ставить викликач
            (`do_GET`), щоб побічний ефект був видний там, де його роблять.

            Задача — лише з префікса `/t/<id>/` у Referer (`None` — префікса нема, і
            діє поточна машини; простір тоді теж `None`). Невідома задача в Referer — Referer
            ігнорується ЦІЛИМ, а не лише її назва: інакше ітерацію «чужої» задачі мовчки віддала б
            поточна. «Невідома» — це й задача, якої нема в жодному просторі, і дубль у двох
            (`AmbiguousTask`), і задача без теки на цій машині (`TaskNotHere` — підклас
            `UnknownTask`). Перевірка йде в ЇЇ просторі (`request_space`), а не в поточному."""
            ref = self.headers.get('Referer', '')
            if not ref:
                return None, None, None
            u = urlparse(ref)
            path, tid, sp = u.path, None, None
            m = self._TASK_PREFIX.match(path)
            if m:
                path, tid = m.group(2), unquote(m.group(1))
                try:
                    sp = spaces.find_task(tid)
                except spaces.AmbiguousTask:
                    return None, None, None
                if sp is None:
                    return None, None, None
                try:
                    with spaces.request_space(sp['id']):
                        task_for(load_tasks(), tid)
                except UnknownTask:
                    return None, None, None
            q = parse_qs(u.query)
            if q.get('it'):               # /commented?it=itN
                return tid, q['it'][0], sp
            mm = re.match(r'^/it-assets/([\w-]+)/', path)  # /it-assets/itN/…
            if mm:
                return tid, mm.group(1), sp
            return None, None, None

        @_guarded_request
        def do_GET(self):
            # ⛔ `/published/…` — ДО `_take_task`: простір тут бере URL, а не запит. Задача запиту (`X-Canvas-Task`,
            # `/t/<id>/`) і поточний простір машини не мають значення, а нечитабельний реєстр чи невідома задача
            # дали б JSON-відмову (503/404/400) БЕЗ захисних заголовків і з шляхом — для статичного файла в
            # пісочниці це витік; `published_target` усі відмови зводить до порожнього 404.
            if self.path.startswith(PUBLISHED_PREFIX):
                self._serve_published()
                return
            # Так само ДО `_take_task`: файли адаптера модуля коментарів — вбудований ресурс, не дані простору чи задачі
            # (див. `MODULE_CLIENT_PREFIX`). Заголовок задачі й зіпсований реєстр на них не діють. Адреса — без `/t/<id>/`.
            if self.path.startswith(MODULE_CLIENT_PREFIX):
                self._serve_module_client()
                return
            # І панелі інструментів модулів та їхній набір (див. `MODULE_UI_PREFIX`): теж ДО `_take_task`, простір бере URL.
            if self.path.startswith(MODULE_UI_PREFIX):
                self._serve_module_ui()
                return
            if self.path.startswith(MODULE_UI_KIT_PREFIX):
                self._serve_module_ui_kit()
                return
            # Задача запиту береться ТУТ, раз на запит: `super().do_GET()` нижче
            # вдруге її не бере (префікс уже знято з `self.path`).
            if not self._take_task():
                return
            m = re.match(r'^/it-assets/([\w-]+)/(.+)$', self.path)
            if m:
                if not self._serve_from_iteration(m.group(1), m.group(2).split('?')[0]):
                    # 404 НАЗИВАЄ ПОТОЧНУ ЗАДАЧУ. Ітерації нумеруються всередині
                    # задачі (`it1` є в кожній), тому з URL не видно, чиєї саме
                    # ітерації просять. Коли `current` перемкнувся (наприклад,
                    # синхронізація реєстру відкотила його — див.
                    # `_save_registry_state` у bin/registry.py), ассети раптом
                    # дають 404, а перелік сторінок приходить порожній: виглядає
                    # як зламана ітерація, і дизайнер іде шукати поломку в
                    # макеті. Один рядок перетворює загадку на факт.
                    try:
                        tid, task = self._current_task()
                        who = f"{tid} ({task.get('title') or tid})"
                    # `UnknownTask` — ЯВНО в переліку, а не підкласом `KeyError`:
                    # підклас мовчки ковтав би будь-який майбутній `except KeyError`
                    # навколо конфіга, тобто повернув би «тиху невідому задачу», проти
                    # якої `task_for` і зроблено. Тут же це лише текст відмови: названу
                    # задачу могли вилучити між входом запиту й цим рядком, а в простору
                    # запиту — зникнути поточна (`NoTask`).
                    except (KeyError, UnknownTask, NoTask, OSError, ValueError):
                        who = '—'
                    if self._task_override is not None:
                        # Задачу НАЗВАНО запитом: «вона перемкнулась» тут було б
                        # брехнею — перемикатись нічому, файлу в названій немає.
                        self.send_error(
                            404, 'iteration asset not found',
                            f'Названа задача — {who}, і в ній цього файлу немає: '
                            f'ітерації нумеруються всередині задачі, тож '
                            f'{m.group(1)} іншої задачі сюди не належить.')
                        return
                    self.send_error(
                        404, 'iteration asset not found',
                        f'Поточна задача — {who}, і в ній цього файлу немає. '
                        f'Якщо очікувалась інша задача, вона перемкнулась: '
                        f'ітерації нумеруються всередині задачі, тож {m.group(1)} '
                        f'іншої задачі сюди не належить.')
                return
            # Angular builds emit some ROOT-ABSOLUTE asset URLs (leading '/'),
            # e.g. the compliance icon service → /assets/compliance-shared-
            # components/icons/<brand>/<Icon>.svg rendered as CSS mask-image.
            # A leading-slash URL ignores <base href>, so it never reaches the
            # /it-assets/<it>/ route → 404 → blank icons. Resolve it against the
            # iteration the request came FROM (Referer) so multi-file builds
            # render fully, not just their relative-path assets.
            if not self.path.startswith(HANDLED_PREFIXES):
                ref_tid, it, ref_sp = self._referer_context()
                if it:
                    # Задачу з Referer (і її простір) ставимо ТУТ і лише коли запит сам
                    # її не назвав (заголовок чи префікс сильніші).
                    if self._task_override is None and ref_tid is not None:
                        self._task_override = ref_tid
                        spaces.set_request_space(ref_sp['id'])
                    if self._serve_from_iteration(
                            it, self.path.split('?')[0].lstrip('/')):
                        return
            super().do_GET()
    return ThreadingHTTPServer(('127.0.0.1', port), Routed)


def serve_main(port):
    """Порт — ПЕРШИМ (`make_server` біндить у конструкторі): зайнятий порт кидає `OSError` ДО міграції ЛІГИ, і простір лишається
    як був (старіший сервер, що тримає порт, не бачить простору, якого не розуміє). Далі міграція (не кидає, ізольовані прогони
    пропускає), далі явний запис `static-publish` наявним просторам (`spaces.materialize_static_publish`, ідемпотентно), і лише потім `serve_forever`: зʼєднання тим часом чекають у черзі, запит обслуговується вже після міграції."""
    srv = make_server(port)
    updater.snapshot_restart()            # знімок «як запущено» — до будь-якого chdir (для `execv` після оновлення)
    import liga_migrate
    liga_migrate.startup()
    try:
        if not (isolation.isolated() and isolation.real_home(spaces.home())):
            for sid in spaces.materialize_static_publish(skip=liga_migrate.liga_space):
                print('простір %s: публікація в теку тепер явний запис static-publish (екран «Підключення»)' % sid, file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — крок не валить старт
        print('static-publish: крок пропущено (%s)' % type(e).__name__, file=sys.stderr)
    try:
        updater.start_background(_updater())          # перша перевірка тегів через ~5 с, далі раз на 6 год; не валить старт
    except Exception as e:  # noqa: BLE001
        print('оновлення: фонову перевірку не запущено (%s)' % type(e).__name__, file=sys.stderr)
    try:
        feedback.start_background()                    # дочищення черги відгуків: лише з налаштованим приймачем і не в ізольованому прогоні
    except Exception as e:  # noqa: BLE001
        print('відгук: фонову чергу не запущено (%s)' % type(e).__name__, file=sys.stderr)
    srv.serve_forever()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    print(f'Design Canvas v2: http://localhost:{port}/app/')
    seam_line = trust_seam_warning()
    if seam_line:
        print(seam_line, file=sys.stderr)
    print(published_mode_line())
    extra_line = extra_modules_line()
    if extra_line:
        print(extra_line, file=sys.stderr)
    serve_main(port)
