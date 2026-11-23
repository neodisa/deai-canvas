"""Історія змін ітерації (фаза И, Р8) з git теки задачі: `git log` → записи панелі «Історія».

Нової бази немає: канвас уже комітить кожну дію (`git_autocommit`). Ітерації належить коміт, що чіпає `iterations/<id>/`, або той,
у темі якого стоїть її id. Коміти, старші за коміт створення (`entry['git']`), відкидаються — історія не змішується з давно
видаленою ітерацією, що мала той самий номер. Тексти записів складає клієнт за `kind` (i18n); `text` — тема як є (≤120).
"""
import datetime
import os
import re
import subprocess

LOG_LIMIT = 300
FILES_MAX = 5
TEXT_MAX = 120
AI_TRAILER = 'Deai-Actor: ai'
_RS, _FS = '\x1e', '\x1f'

_RULES = (
    (re.compile(r'^iteration (?P<it>[\w-]+): копія (?P<from>[\w-]+) · (?P<note>.*)$'), 'copy'),
    (re.compile(r'^iteration (?P<it>[\w-]+): pages from (?P<list>.*)$'), 'merge'),
    (re.compile(r'^iteration (?P<it>[\w-]+): (?P<note>.*)$'), 'create'),
    (re.compile(r'^rename iteration (?P<it>[\w-]+): (?P<name>.*)$'), 'rename'),
    (re.compile(r'^restore iteration (?P<it>[\w-]+)$'), 'restore'),
    (re.compile(r'^page (?P<page>\S+): new in (?P<it>[\w-]+)$'), 'page-new'),
    (re.compile(r'^page (?P<page>\S+): rename$'), 'page-rename'),
    (re.compile(r'^page (?P<page>\S+): move$'), 'page-move'),
    (re.compile(r'^tree: (?P<what>.*)$'), 'tree'),
    (re.compile(r'^publish: '), 'publish'),
    (re.compile(r'^(?P<it>[\w-]+): зміни AI$'), 'ai'),
    (re.compile(r'^(?P<it>[\w-]+): автосинк'), 'sync'),
)


def _git(task_dir, args, run):
    r = run(['git', '-c', 'core.quotepath=false', *args], cwd=task_dir, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        raise OSError(r.stderr.strip() or f'git {args[0]} failed')
    return r.stdout


def _mentions(subject, iid):
    return re.search(rf'(?<![\w-]){re.escape(iid)}(?![\w-])', subject) is not None


def _classify(subject, body, page_names):
    kind, args = 'other', {}
    for rx, k in _RULES:
        m = rx.match(subject)
        if not m:
            continue
        kind, g = k, m.groupdict()
        if k == 'copy':
            args = {'from': g['from'], 'note': '' if g['note'] == 'без примітки' else g['note']}
        elif k == 'create':
            args = {'note': '' if g['note'] == 'без примітки' else g['note']}
        elif k == 'merge':
            args = {'from': [x.strip() for x in g['list'].split(',') if x.strip()]}
        elif k == 'rename':
            args = {'name': g['name']}
        elif k.startswith('page-'):
            args = {'page': g['page'], 'name': page_names.get(g['page']) or g['page']}
        break
    ai = AI_TRAILER in (body or '')
    if ai:
        args = {**args, 'synced': kind == 'sync'}
        kind = 'ai'
    return kind, args, ai


def _to_local_iso(date_text):
    """`ДД.ММ.РРРР ГГ:ХХ` з `iterations.json` → ISO з поясом машини; не розібрали — порожньо."""
    try:
        dt = datetime.datetime.strptime(date_text, '%d.%m.%Y %H:%M')
    except (TypeError, ValueError):
        return ''
    return dt.astimezone().isoformat(timespec='seconds')


def _created_from_meta(entry):
    return {'sha': '', 'at': _to_local_iso(entry.get('date')),
            'actor': {'kind': 'person', 'name': str(entry.get('author') or '')},
            'kind': 'create', 'args': {'note': str(entry.get('note') or '')}, 'text': '', 'files': [], 'more': 0}


def _porcelain_paths(out):
    """Шляхи з `status --porcelain -z`: запис перейменування/копії несе ще один шлях (старий) без `XY `."""
    recs = out.split('\0')
    i = 0
    while i < len(recs):
        rec = recs[i]
        i += 1
        if len(rec) <= 3:
            continue
        if rec[0] in 'RC' or rec[1] in 'RC':
            i += 1
        yield rec[3:]


def dirty_iterations(task_dir, run=subprocess.run):
    """Ідентифікатори ітерацій із незакоміченими змінами. Без `.git` — усі теки `iterations/`."""
    if not os.path.isdir(os.path.join(task_dir, '.git')):
        it_dir = os.path.join(task_dir, 'iterations')
        return set(os.listdir(it_dir)) if os.path.isdir(it_dir) else set()
    out = _git(task_dir, ['status', '--porcelain', '-z', '--untracked-files=all', '--', 'iterations/'], run)
    ids = set()
    for path in _porcelain_paths(out):
        parts = path.split('/')
        if len(parts) >= 3 and parts[0] == 'iterations':
            ids.add(parts[1])
    return ids


def _pending(task_dir, iid, run):
    prefix = f'iterations/{iid}/'
    out = _git(task_dir, ['status', '--porcelain', '-z', '--untracked-files=all', '--', prefix], run)
    files, newest = [], 0.0
    for path in _porcelain_paths(out):
        if not path.startswith(prefix):
            continue
        files.append(path[len(prefix):])
        try:
            newest = max(newest, os.path.getmtime(os.path.join(task_dir, path)))
        except OSError:
            pass
    if not files:
        return None
    at = datetime.datetime.fromtimestamp(newest).astimezone().isoformat(timespec='seconds') if newest else ''
    return {'files': sorted(files)[:FILES_MAX], 'more': max(0, len(files) - FILES_MAX), 'at': at}


def history(task_dir, entry, page_names=None, *, limit=LOG_LIMIT, run=subprocess.run):
    """`{'entries': [...], 'pending': {...}|None, 'degraded': bool}` для ітерації `entry` (запис з `iterations.json`)."""
    iid = entry['id']
    page_names = page_names or {}
    if not os.path.isdir(os.path.join(task_dir, '.git')):
        return {'entries': [_created_from_meta(entry)], 'pending': None, 'degraded': True}
    try:
        raw = _git(task_dir, ['log', f'-n{int(limit)}', '--name-only',
                              f'--format={_RS}%h{_FS}%an{_FS}%aI{_FS}%s{_FS}%b{_FS}'], run)
        pending = _pending(task_dir, iid, run)
    except (OSError, subprocess.SubprocessError):
        return {'entries': [_created_from_meta(entry)], 'pending': None, 'degraded': True}
    created = str(entry.get('git') or '')
    prefix = f'iterations/{iid}/'
    entries = []
    for chunk in raw.split(_RS):
        if not chunk.strip():
            continue
        parts = chunk.split(_FS)
        if len(parts) < 6:
            continue
        sha, author, at, subject, body, rest = parts[:6]
        files_all = [ln for ln in rest.strip().splitlines() if ln]
        mine = [f[len(prefix):] for f in files_all if f.startswith(prefix)]
        if mine or _mentions(subject, iid):
            kind, args, ai = _classify(subject, body, page_names)
            entries.append({'sha': sha, 'at': at, 'actor': {'kind': 'ai', 'name': 'AI'} if ai else {'kind': 'person', 'name': author},
                            'kind': kind, 'args': args, 'text': subject[:TEXT_MAX],
                            'files': sorted(mine)[:FILES_MAX], 'more': max(0, len(mine) - FILES_MAX)})
        if created and (sha.startswith(created) or created.startswith(sha)):
            break
    if not entries:
        entries = [_created_from_meta(entry)]
    return {'entries': entries, 'pending': pending, 'degraded': False}
