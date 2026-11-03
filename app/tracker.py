"""Статуси задач у трекері (етап 4c-2): чиста логіка ролі `tracker`, спільна для CLI-пушера й сервера.

Ядро фільтрує ключі, ділить їх на пакети, кличе `statuses(ctx, keys)` модуля й нормалізує відповідь; сам модуль лише ходить у
трекер. ⛔ Цей модуль НЕ імпортує `serve` (тягне сервер, мережу й увесь стан) — його читають і CLI, і сервер (як `app/dashboard.py`).
"""
import re
import unicodedata

import deai_modules

#: Ключ задачі трекера (і Jira, і Linear): `DEMO-1`. Лише `fullmatch`: сміття з ручної правки `tasks.json` не потрапляє в JQL.
KEY_RE = re.compile(r'[A-Z][A-Z0-9_]{0,31}-[1-9][0-9]{0,9}', re.ASCII)
#: Категорії статусу (як у Jira); інше значення від модуля → `None`.
CATS = ('new', 'indeterminate', 'done')
#: Скільки ключів іде в один виклик `statuses`.
BATCH = 100
#: Довжина назви статусу в відповіді.
NAME_MAX = 80
#: Екран «Задачі»: скільки секунд ядро чекає виклику й який бюджет сокета дістає модуль (`ctx['timeout_s']`). Модуль мусить
#: вкластись РАНІШЕ й відповісти своїм текстом помилки, інакше людина бачить `check-timeout` ядра замість причини.
READ_TIMEOUT, READ_SOCKET_S = 6, 4
#: Синк дашборда: сокет 15 с — як було в 0.12.0, ядро чекає 30 с на пакет.
SYNC_TIMEOUT, SYNC_SOCKET_S = 30, 15
#: Вбудований модуль, яким ходить шлях ЛІГИ (неявний постачальник).
LEGACY_MODULE = 'jira-tracker'
UNCONFIGURED = 'Jira не налаштовано: додайте jira_base у tasks.json і облікові JIRA_EMAIL/JIRA_TOKEN'


def keys_of(tasks):
    """Унікальні валідні ключі трекера задач (`task['jira']`) у порядку файла. Не-словник чи задача без рядкового ключа за
    `KEY_RE` — пропускаються."""
    out = []
    if not isinstance(tasks, dict):
        return out
    for task in tasks.values():
        key = task.get('jira') if isinstance(task, dict) else None
        if isinstance(key, str) and KEY_RE.fullmatch(key) and key not in out:
            out.append(key)
    return out


def _clean_name(name):
    """Назва статусу, обрізана до `NAME_MAX`, чи `None`: не рядок, порожня або з керівним символом (`Cc`, `Cf` — напр. bidi-перевизначення U+202E, роздільники рядків)."""
    if not isinstance(name, str) or not name.strip():
        return None
    if any(unicodedata.category(c) in ('Cc', 'Cf', 'Zl', 'Zp') for c in name):
        return None
    return name[:NAME_MAX]


def normalize(data, keys):
    """Відповідь модуля → `{ключ: {'name': str, 'cat': str|None}}` лише для запитаних `keys`. Запис із негодною назвою
    відкидається; `cat` поза `CATS` → `None`. Не словник → `ValueError`."""
    if not isinstance(data, dict):
        raise ValueError('tracker answer is not a dict')
    out = {}
    for key in keys:
        entry = data.get(key)
        if not isinstance(entry, dict):
            continue
        name = _clean_name(entry.get('name'))
        if name is None:
            continue
        cat = entry.get('cat')
        out[key] = {'name': name, 'cat': cat if isinstance(cat, str) and cat in CATS else None}
    return out


def statuses(module, ctx, keys, *, timeout, socket_s, call=None):
    """Статуси `keys` з трекера модуля `module`: `{ключ: {'name', 'cat'}}`.

    Сміття (не рядок, не за `KEY_RE`) і повтори відкидаються ДО виклику; жодного валідного ключа → `{}` без виклику. Решта йде
    пакетами по `BATCH`: кожен — `call(module, 'statuses', ctx2, chunk, timeout=timeout)`, де `ctx2` — копія `ctx` з
    `timeout_s = socket_s` (бюджет сокета модуля; вихідний `ctx` не змінюється). Збій пакета (`ModuleError`) піднімається вгору,
    решту пакетів не питаємо; відповідь не словник — теж `ModuleError('tracker-error')`. `call` — шов тестів (типово
    `deai_modules.call`)."""
    call = call or deai_modules.call
    wanted = list(dict.fromkeys(k for k in keys if isinstance(k, str) and KEY_RE.fullmatch(k)))
    ctx2 = dict(ctx)
    ctx2['timeout_s'] = socket_s
    out = {}
    for i in range(0, len(wanted), BATCH):
        chunk = wanted[i:i + BATCH]
        data = call(module, 'statuses', ctx2, chunk, timeout=timeout)
        try:
            out.update(normalize(data, chunk))
        except ValueError:
            raise deai_modules.ModuleError('tracker-error', message='модуль трекера віддав відповідь не тієї форми') from None
    return out


def legacy_ctx(base, email, token, space_id=''):
    """`ctx` неявного постачальника ЛІГИ (`'legacy'`): `jira-tracker` з адресою, поштою й токеном конфігу установки
    (`install_config.jira_config()`). `base`/`email`/`token` — з нього викликача; нема конфігу (`base is None`) —
    `ModuleError('tracker-unconfigured')` з текстом `UNCONFIGURED`.

    ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`, а при вимкненому шарі `spaces.home()` — це
    справжній `~/.deai` машини (той самий урок 4c-1, що `dashboard.legacy_ctx`, `serve._vcs_legacy_ctx` і
    `serve._comments_legacy_ctx`). `legacy: True` — модуль цього прапорця не читає (поведінка для ЛІГИ та сама)."""
    if base is None:
        raise deai_modules.ModuleError('tracker-unconfigured', message=UNCONFIGURED)
    return {'space': {'id': space_id, 'path': ''}, 'settings': {'base': base, 'email': email},
            'secrets': {'token': token}, 'ModuleError': deai_modules.ModuleError, 'legacy': True}


def legacy_module():
    """Вбудований `jira-tracker` із каталогу БЕЗ простору (шлях ЛІГИ); не завантажився — `ModuleError('module-error')`."""
    try:
        m = deai_modules.catalog().get(LEGACY_MODULE)
    except Exception as e:  # noqa: BLE001 — збій каталогу = відмова модуля, не 500
        raise deai_modules.ModuleError('module-error', message=f'module catalog: {type(e).__name__}') from None
    if m is None or m.status != 'ok':
        raise deai_modules.ModuleError('module-error', message=f'{LEGACY_MODULE} module is not loaded')
    return m
