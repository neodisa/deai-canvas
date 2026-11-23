"""Кошик ітерацій задачі (фаза И, Р6): видалення без стирання, повернення, прибирання через 7 днів.

Тека `iterations/<id>` переїжджає `os.rename` у `<тека задачі>/.trash/iterations/<id>--<РРРРММДД-ГГХХСС>[-N]/files`, поруч —
`entry.json` (запис ітерації з `iterations.json` і час видалення). Той самий диск — без копіювання.

Функції змінюють диск, але НЕ пишуть `iterations.json`: це робить маршрут (`save_meta`). Час — параметр (`now`, aware UTC),
тож тести детерміновані. `.trash/` стоїть у `TASK_IGNORE` (git), а `copy_mockup`/`_mockup_files` пропускають теки з крапкою.
"""
import datetime
import json
import os
import re
import shutil

TRASH_REL = os.path.join('.trash', 'iterations')
KEEP_DAYS = 7
ID_RE = re.compile(r'^[\w-]{1,64}$')
NUM_RE = re.compile(r'^it(\d+)$')
SLOT_RE = re.compile(r'^([\w-]{1,64})--(\d{8}-\d{6})(?:-\d+)?$')


class IterTrashError(Exception):
    """Відмова з кодом: `bad-id`, `bad-slot`, `not-in-trash`."""

    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def trash_root(task_dir):
    return os.path.join(task_dir, TRASH_REL)


def _safe_id(iid):
    return isinstance(iid, str) and iid not in ('.', '..') and ID_RE.fullmatch(iid) is not None


def move_to_trash(task_dir, entry, now):
    """Перенести теку ітерації й її запис у кошик. Повертає імʼя слота (`it2--20261123-100000`)."""
    iid = entry.get('id') if isinstance(entry, dict) else None
    if not _safe_id(iid):
        raise IterTrashError('bad-id', 'the iteration id is not a safe folder name')
    root = trash_root(task_dir)
    os.makedirs(root, exist_ok=True)
    base = f'{iid}--{now.strftime("%Y%m%d-%H%M%S")}'
    slot, n = base, 1
    while os.path.exists(os.path.join(root, slot)):
        n += 1
        slot = f'{base}-{n}'
    dst = os.path.join(root, slot)
    os.makedirs(dst)
    src = os.path.join(task_dir, 'iterations', iid)
    # Спершу запис, потім перенесення: збій посередині лишає теку на місці (слот знімаємо), а не «сироту» без запису.
    try:
        with open(os.path.join(dst, 'entry.json'), 'w', encoding='utf-8') as f:
            json.dump({'entry': entry, 'deleted_at': now.strftime('%Y-%m-%dT%H:%M:%SZ')}, f, ensure_ascii=False)
        if os.path.isdir(src):
            os.rename(src, os.path.join(dst, 'files'))
    except BaseException:
        shutil.rmtree(dst, ignore_errors=True)
        raise
    return slot


def _slot_entry(task_dir, slot):
    """`(тека слота, запис)` з перевіркою імені слота й id із `entry.json` (файл могли підмінити)."""
    if not isinstance(slot, str) or not SLOT_RE.fullmatch(slot):
        raise IterTrashError('bad-slot', 'not a trash slot name')
    base = os.path.join(trash_root(task_dir), slot)
    meta_p = os.path.join(base, 'entry.json')
    if not os.path.isfile(meta_p):
        raise IterTrashError('not-in-trash', 'nothing to restore')
    with open(meta_p, encoding='utf-8') as f:
        entry = dict(json.load(f)['entry'])
    if not _safe_id(entry.get('id')):
        raise IterTrashError('bad-id', 'the iteration id in the trash entry is not a safe folder name')
    return base, entry


def undo_move(task_dir, slot):
    """Скасувати `move_to_trash`: теку назад у `iterations/<id>`, слот прибрати (коли не вдалось записати `iterations.json`)."""
    base, entry = _slot_entry(task_dir, slot)
    files = os.path.join(base, 'files')
    if os.path.isdir(files):
        os.rename(files, os.path.join(task_dir, 'iterations', entry['id']))
    shutil.rmtree(base)


def next_id(task_dir, ids):
    """Наступний вільний `itN`: максимум по записах, кошику й теках `iterations/` (номер видаленої не повторюється)."""
    nums = [int(m.group(1)) for i in ids if isinstance(i, str) and (m := NUM_RE.match(i))]
    root = trash_root(task_dir)
    if os.path.isdir(root):
        for name in os.listdir(root):
            s = SLOT_RE.fullmatch(name)
            if s and (m := NUM_RE.match(s.group(1))):
                nums.append(int(m.group(1)))
    it_dir = os.path.join(task_dir, 'iterations')
    if os.path.isdir(it_dir):
        for name in os.listdir(it_dir):
            if m := NUM_RE.match(name):
                nums.append(int(m.group(1)))
    return f'it{max(nums, default=0) + 1}'


def restore_prepare(task_dir, slot, taken_ids):
    """Крок 1 повернення: вибрати id, перенести `files` у `iterations/<id>`; слот (з `entry.json`) ЛИШАЄТЬСЯ.
    `(entry, renamed)`; id зайнятий → наступний вільний номер, `git` прибирається (історія нової теки починається
    з повернення). Після запису `iterations.json` — `restore_finish`, при збої — `restore_rollback`."""
    base, entry = _slot_entry(task_dir, slot)
    iid, renamed = entry['id'], False
    if iid in taken_ids or os.path.exists(os.path.join(task_dir, 'iterations', iid)):
        iid = next_id(task_dir, list(taken_ids) + [entry['id']])
        entry['id'] = iid
        entry.pop('git', None)
        renamed = True
    target = os.path.join(task_dir, 'iterations', iid)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    files = os.path.join(base, 'files')
    if os.path.isdir(files):
        os.rename(files, target)
    else:
        os.makedirs(target)
    return entry, renamed


def restore_finish(task_dir, slot):
    """Крок 2: прибрати слот (лише після успішного запису `iterations.json`)."""
    base, _ = _slot_entry(task_dir, slot)
    # Спершу `entry.json`: слот без нього відповідає `not-in-trash`, тож повторне повернення не створить порожню копію,
    # навіть якщо дальше видалення теки не вдалось.
    os.remove(os.path.join(base, 'entry.json'))
    shutil.rmtree(base, ignore_errors=True)


def restore_rollback(task_dir, slot, entry):
    """Скасувати `restore_prepare`: `iterations/<id>` назад у `slot/files`."""
    base = os.path.join(trash_root(task_dir), slot)
    target = os.path.join(task_dir, 'iterations', entry['id'])
    if os.path.isdir(target) and not os.path.exists(os.path.join(base, 'files')):
        os.rename(target, os.path.join(base, 'files'))


def restore(task_dir, slot, taken_ids):
    """Зручність для тестів: prepare + finish. Маршрут викликає кроки окремо."""
    entry, renamed = restore_prepare(task_dir, slot, taken_ids)
    restore_finish(task_dir, slot)
    return entry, renamed


def purge(task_dir, now, keep_days=KEEP_DAYS):
    """Стерти слоти, старші за `keep_days`. Повертає їхні імена (відсортовані)."""
    root = trash_root(task_dir)
    if not os.path.isdir(root):
        return []
    edge = now - datetime.timedelta(days=keep_days)
    gone = []
    for name in sorted(os.listdir(root)):
        s = SLOT_RE.fullmatch(name)
        if not s:
            continue
        try:
            at = datetime.datetime.strptime(s.group(2), '%Y%m%d-%H%M%S').replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue                   # зіпсована дата в імені — слот не чіпаємо
        if at < edge:
            shutil.rmtree(os.path.join(root, name), ignore_errors=True)
            gone.append(name)
    return gone


def insert_ordered(its, entry):
    """Вставити запис за номером (`it4` між `it3` і `it5`); не-`itN` — у кінець. Змінює `its` на місці."""
    m = NUM_RE.match(entry.get('id', ''))
    if not m:
        its.append(entry)
        return
    n = int(m.group(1))
    for i, x in enumerate(its):
        k = NUM_RE.match(x.get('id', ''))
        if k and int(k.group(1)) > n:
            its.insert(i, entry)
            return
    its.append(entry)
