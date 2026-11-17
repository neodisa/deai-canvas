"""Кошик задач простору (етап Д, 0.30.0): видалення без стирання, повернення, знищення.

Запис кошика живе в `tasks.json` простору (ключ `trash`). Задача й її запис у кошику міняються ОДНИМ записом файла: немає
стану, де задача є і там, і там. Тека задачі переїжджає `os.rename` у `<батьківська>/.deai-trash/<id>-<штамп>`, тобто
поруч, на тому самому диску, без копіювання: тека задачі може лежати поза текою простору (корінь напрямку,
`design_work_root`). Після «назавжди» лишається надгробок `{"purged": …}`, щоб `bin/registry.py pull` не воскресив задачу
ЛІГИ зі спільного реєстру.

Функції змінюють `cfg` і диск, але НЕ пишуть `tasks.json`: це робить маршрут (`save_tasks`). Якщо запис упав, маршрут кличе
повернуту `undo()`. Час — параметр (`now`, aware UTC), тож тести детерміновані.
"""
import datetime
import os
import shutil

TRASH_DIRNAME = '.deai-trash'


class TrashError(Exception):
    """Відмова з кодом відповіді маршруту: `not-in-trash`, `task-exists`, `task-dir-exists`, `task-restore-failed`,
    `task-purge-failed`, `bad-id`, `task-in-trash`."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(now):
    return now.strftime('%Y-%m-%dT%H:%M:%SZ')


def trash_dir_for(task_dir, tid, now):
    """Вільний шлях у кошику поруч із текою задачі: `<батьківська>/.deai-trash/<id>-<РРРРММДД-ГГХХСС>[-N]`."""
    if not (isinstance(tid, str) and tid and tid not in ('.', '..') and os.path.basename(tid) == tid
            and '/' not in tid and os.sep not in tid):
        raise TrashError('bad-id', 'the task id is not a safe folder name')
    parent = os.path.dirname(os.path.normpath(task_dir))
    base = os.path.join(parent, TRASH_DIRNAME, f"{tid}-{now.strftime('%Y%m%d-%H%M%S')}")
    cand, n = base, 2
    while os.path.lexists(cand):
        cand, n = f'{base}-{n}', n + 1
    return cand


def _bucket(cfg):
    tr = cfg.get('trash')
    return tr if isinstance(tr, dict) else {}


def records(cfg):
    """Живі записи кошика `{id: запис}`: без надгробків і без сміття, яке правили руками."""
    return {k: v for k, v in _bucket(cfg).items() if isinstance(v, dict) and isinstance(v.get('entry'), dict)}


def in_trash(cfg, tid):
    return tid in records(cfg)


def listing(cfg):
    """`[(id, запис)]` кошика, найновіші першими (за `at`)."""
    return sorted(records(cfg).items(), key=lambda kv: str(kv[1].get('at') or ''), reverse=True)


def clear_tombstone(cfg, tid):
    """Нова задача з тим самим id знімає надгробок. Живого запису кошика не чіпає: його id зайнятий (`task-in-trash`)."""
    tr = _bucket(cfg)
    v = tr.get(tid)
    if isinstance(v, dict) and 'purged' in v and 'entry' not in v:
        del tr[tid]


def delete(cfg, tid, now, order=()):
    """Задача `tid` → кошик. Тека (якщо є) переїжджає; запис задачі стає `entry` запису кошика; `current`, що вказував на неї,
    переходить на першу іншу з `order` (порядок «нещодавно відкриті» маршруту), а без інших — прибирається.
    Повертає `(запис, undo)`; `undo()` вертає теку на місце (для збою запису `tasks.json`). `OSError` переносу — маршруту."""
    if in_trash(cfg, tid):
        raise TrashError('task-in-trash', 'a trash record with this id already exists')
    entry = cfg['tasks'][tid]
    d = entry.get('dir')
    src = d if isinstance(d, str) and d and os.path.isdir(d) else None
    dst = trash_dir_for(src, tid, now) if src else None
    if src:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
    rec = {'entry': entry, 'dir': d if isinstance(d, str) else None, 'trashDir': dst, 'at': _iso(now)}
    del cfg['tasks'][tid]
    if not isinstance(cfg.get('trash'), dict):
        cfg['trash'] = {}
    cfg['trash'][tid] = rec
    if cfg.get('current') == tid:
        rest = [k for k in [*order, *cfg['tasks']] if k != tid and k in cfg['tasks']]
        if rest:
            cfg['current'] = rest[0]
        else:
            cfg.pop('current', None)

    def undo():
        if src:
            os.rename(dst, src)
    return rec, undo


def restore(cfg, tid):
    """Запис кошика `tid` → назад у `tasks`. Тека вертається на ВИХІДНИЙ шлях. Він уже зайнятий (агент записав туди нову) —
    `task-dir-exists`, нічого не рухаємо. Id зайнятий у цьому файлі — `task-exists` (між просторами перевіряє маршрут).
    Повертає `(запис задачі, undo)`; `undo()` кладе теку назад у кошик."""
    rec = records(cfg).get(tid)
    if rec is None:
        raise TrashError('not-in-trash', 'task is not in the trash')
    if tid in (cfg.get('tasks') or {}):
        raise TrashError('task-exists', 'a task with this id already exists')
    src, dst = rec.get('trashDir'), rec.get('dir')
    moved = False
    if isinstance(src, str) and src and os.path.isdir(src):
        if not isinstance(dst, str) or not dst:
            raise TrashError('task-restore-failed', 'the trash record has no original folder')
        if os.path.lexists(dst):
            raise TrashError('task-dir-exists', 'the task folder already exists')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.rename(src, dst)
        moved = True
    if not isinstance(cfg.get('tasks'), dict):
        cfg['tasks'] = {}
    cfg['tasks'][tid] = rec['entry']
    del cfg['trash'][tid]

    def undo():
        if moved:
            os.rename(dst, src)
    return rec['entry'], undo


def _inside_trash(path):
    """Шлях — безпосередня дитина теки `.deai-trash`. ⛔ `trashDir` у `tasks.json` правлять руками: без цієї перевірки
    «назавжди» стерло б будь-яку теку диска."""
    norm = os.path.normpath(path)
    return os.path.basename(os.path.dirname(norm)) == TRASH_DIRNAME and os.path.basename(norm) not in ('', '.', '..')


def inside_trash(path):
    """Публічна форма `_inside_trash`: кадр із кошика теж читається лише з теки в `.deai-trash` (як і знищення)."""
    return _inside_trash(path)


def purge(cfg, tid, now):
    """Знищити запис кошика `tid`: тека йде з диска (посилання — лише саме посилання), запис стає надгробком. Шлях поза
    `.deai-trash` — `task-purge-failed`, нічого не стерто. `OSError` стирання — маршруту; запис лишається, тож знищення
    можна повторити."""
    rec = records(cfg).get(tid)
    if rec is None:
        raise TrashError('not-in-trash', 'task is not in the trash')
    td = rec.get('trashDir')
    if isinstance(td, str) and td and os.path.lexists(td):
        if not _inside_trash(td):
            raise TrashError('task-purge-failed', 'refusing to delete a folder outside the trash')
        if os.path.islink(td):
            os.unlink(td)
        else:
            shutil.rmtree(td)
    cfg['trash'][tid] = {'purged': _iso(now)}
