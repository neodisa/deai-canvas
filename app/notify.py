"""Тиша сповіщень Teams (етап 4c-3): чиста логіка ролі `notify`, спільна для сервера й модулів.

Ядро нормалізує стан тиші від модуля, рахує вигляд каналу задачі й перевіряє аргументи перемикання; сам модуль лише ходить
у сховище (RPC `teams_mute_state` / `teams_mute_set`). ⛔ Цей модуль НЕ імпортує `serve` (тягне сервер, мережу й увесь
стан) — як `app/tracker.py` і `app/dashboard.py`. `mute_signature()` (особа машини) лишається в `serve` і сюди приходить
аргументом `me`.
"""
import deai_modules

#: Скільки секунд ядро чекає на виклик модуля (`mute_state`/`mute_set`); власний тайм-аут сокета модуля — 8 с, тож модуль
#: відповідає СВОЇМ текстом помилки раніше, ніж спрацює `check-timeout` ядра.
NOTIFY_TIMEOUT = 10
#: Скільки замовчаних каналів ядро бере зі стану (решту відкидає): стіна проти розпухлої відповіді.
MAX_MUTES = 1000
#: Найдовший канал (`project_id`) і найдовший підпис того, хто замовчав.
CHANNEL_MAX = BY_MAX = 200
#: Довжина позначки часу в рядку стану (ISO 8601 з поясом вкладається з запасом).
AT_MAX = 40
#: Вбудований модуль, яким ходить шлях ЛІГИ (неявний постачальник; адаптер — Task 3).
LEGACY_MODULE = 'supabase-teams'
UNCONFIGURED = 'Supabase не налаштовано'


def normalize_mutes(data):
    """Стан тиші від модуля → `[{'project_id': str, 'muted_at': str | None, 'muted_by': str}]`.

    Лишаються лише словники з рядковим непорожнім `project_id` ≤ `CHANNEL_MAX` (решта — сміття зі сховища, мовчки
    відкидається); `muted_by` не рядок чи довший за `BY_MAX` → `''` (застарілі рядки без підпису — «не мій ні за яких
    умов», див. `mute_view`); `muted_at` не рядок чи довший за `AT_MAX` → `None`. Не більше `MAX_MUTES` рядків. Не список
    (словник, рядок, `None`) — `ValueError`: «не знаю» ≠ «нічого не замовчано»."""
    if not isinstance(data, list):
        raise ValueError('notify: mute_state must return a list')
    out = []
    for r in data:
        if not isinstance(r, dict):
            continue
        pid = r.get('project_id')
        if not isinstance(pid, str) or not 1 <= len(pid) <= CHANNEL_MAX:
            continue
        by, at = r.get('muted_by'), r.get('muted_at')
        out.append({'project_id': pid,
                    'muted_at': at if isinstance(at, str) and len(at) <= AT_MAX else None,
                    'muted_by': by if isinstance(by, str) and len(by) <= BY_MAX else ''})
        if len(out) >= MAX_MUTES:
            break
    return out


def mute_view(channel, rows, me):
    """Чи замовчано канал задачі. Тиша каналу покриває його підканали (`<канал>/internal`) — так само рахує `cl_send_teams`
    у базі. ⛔ Підканал — лише за `<канал>/`, а не за голим префіксом: `dc/t10` і `dc/t1x` — не підканали `dc/t1`.

    `me` — підпис цієї машини (`serve.mute_signature()`); `mine` — лише коли підпис НЕпорожній і збігається: рядок без
    `muted_by` (застарілий) чи порожній підпис машини ніколи не «мої»."""
    for r in rows or []:
        pid = r.get('project_id') or ''
        if pid and (channel == pid or channel.startswith(pid + '/')):
            by = r.get('muted_by') or ''
            return {'channel': channel, 'muted': True, 'muted_by': by,
                    'mine': bool(by) and by == me,
                    'muted_at': r.get('muted_at'), 'via': pid}
    return {'channel': channel, 'muted': False}


def check_set_args(channel, muted, by):
    """Аргументи `mute_set` — ДО виклику модуля: `channel` — непорожній рядок ≤ `CHANNEL_MAX`; `muted` — саме `bool`
    (не `1`/`'true'`: перемикач не вгадує); `by` — рядок ≤ `BY_MAX` (порожній підпис дозволений: нема git-пошти). Інакше
    `ValueError`."""
    if not isinstance(channel, str) or not 1 <= len(channel) <= CHANNEL_MAX:
        raise ValueError(f'notify: channel must be a string of 1..{CHANNEL_MAX} characters')
    if type(muted) is not bool:
        raise ValueError('notify: muted must be boolean')
    if not isinstance(by, str) or len(by) > BY_MAX:
        raise ValueError(f'notify: by must be a string of at most {BY_MAX} characters')


def legacy_ctx(url, key, space_id=''):
    """`ctx` неявного постачальника ЛІГИ (`Implicit`): `supabase-teams` з адресою й ключем із конфігу установки
    (`supabase_config()` викликача — той самий, що в коментарів і дашборда). Нема конфігу (`url is None`) —
    `ModuleError('notify-unconfigured')` з текстом `UNCONFIGURED`.

    ⛔ НЕ `deai_modules.module_ctx()`: у ЛІГИ нема `space.json`/`secrets.json`, а при вимкненому шарі `spaces.home()` — це
    справжній `~/.deai` машини (той самий урок 4c-1, що `dashboard.legacy_ctx`, `tracker.legacy_ctx` і
    `serve._comments_legacy_ctx`). `legacy: True` — модуль за ним пропускає перевірку публічності ключа й `teams_notify_health`
    у `check` (у базі ЛІГИ цієї функції нема, а ключ там — публічний ключ сторінки: паритет з 0.13.0)."""
    if url is None:
        raise deai_modules.ModuleError('notify-unconfigured', message=UNCONFIGURED)
    return {'space': {'id': space_id, 'path': ''}, 'settings': {'url': url}, 'secrets': {'key': key},
            'ModuleError': deai_modules.ModuleError, 'legacy': True}


def legacy_module():
    """Вбудований `supabase-teams` із каталогу БЕЗ простору (шлях ЛІГИ); не завантажився — `ModuleError('module-error')`."""
    try:
        m = deai_modules.catalog().get(LEGACY_MODULE)
    except Exception as e:  # noqa: BLE001 — збій каталогу = відмова модуля, не 500
        raise deai_modules.ModuleError('module-error', message=f'module catalog: {type(e).__name__}') from None
    if m is None or m.status != 'ok':
        raise deai_modules.ModuleError('module-error', message=f'{LEGACY_MODULE} module is not loaded')
    return m
