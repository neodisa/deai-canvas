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
_AI_RX = re.compile(r'(?m)^Deai-Actor:\s*ai\s*$')
_RS, _FS = '\x1e', '\x1f'

_RULES = (
    (re.compile(r'^iteration (?P<it>[\w-]+): копія (?P<from>[\w-]+) · (?P<note>.*)$'), 'copy'),
    (re.compile(r'^iteration (?P<it>[\w-]+): pages from (?P<list>.*)$'), 'merge'),
    (re.compile(r'^iteration (?P<it>[\w-]+): (?P<note>.*)$'), 'create'),
    (re.compile(r'^rename iteration (?P<it>[\w-]+): (?P<name>.*)$'), 'rename'),
    (re.compile(r'^delete iteration (?P<it>[\w-]+)$'), 'delete'),
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
    """Один виклик git. Будь-яка невдача (код ≠ 0, таймаут, не-UTF-8, ValueError) → `OSError`."""
    try:
        r = run(['git', '--no-optional-locks', '-c', 'core.quotepath=false', *args], cwd=task_dir,
                capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
        if r.returncode != 0:
            raise OSError((r.stderr or '').strip() or f'git {args[0]} failed')
        return r.stdout
    except OSError:
        raise
    except (subprocess.SubprocessError, UnicodeError, ValueError) as e:
        raise OSError(f'git {args[0]}: {e}') from e


def _mentions(subject, iid):
    return re.search(rf'(?<![\w-]){re.escape(iid)}(?![\w-])', subject) is not None


def _note(v):
    return '' if v == 'без примітки' else v


def _classify(subject, body, page_names):
    """`(kind, args, is_ai, owners)`; `owners` — id з СТРУКТУРНИХ груп теми (не з вільного тексту) або `None` для `other`."""
    kind, args, owners = 'other', {}, None
    for rx, k in _RULES:
        m = rx.match(subject)
        if not m:
            continue
        kind, g = k, m.groupdict()
        owners = {g['it']} if 'it' in g else set()
        if k == 'copy':
            args = {'from': g['from'], 'note': _note(g['note'])}
        elif k == 'create':
            args = {'note': _note(g['note'])}
        elif k == 'merge':
            args = {'from': [x.strip() for x in g['list'].split(',') if x.strip()]}
        elif k == 'rename':
            args = {'name': g['name']}
        elif k in ('page-new', 'page-rename', 'page-move'):
            args = {'page': g['page'], 'name': page_names.get(g['page']) or g['page']}
        elif k == 'publish':
            owners = set(subject.split(' · ', 1)[1].split()) if ' · ' in subject else set()
        break
    ai = _AI_RX.search(body or '') is not None or kind == 'ai'
    if ai:
        args = {**args, 'synced': kind == 'sync'}
        kind = 'ai'
    return kind, args, ai, owners


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
    """Шляхи з `status --porcelain -z --no-renames` (запис — `XY шлях`)."""
    return [rec[3:] for rec in out.split('\0') if len(rec) > 3]


def dirty_iterations(task_dir, run=subprocess.run):
    """Ідентифікатори ітерацій із незакоміченими змінами. Без власного `.git` — усі ТЕКИ `iterations/`.
    Кидає лише `OSError` (збій git, таймаут тощо)."""
    if not os.path.exists(os.path.join(task_dir, '.git')):
        it_dir = os.path.join(task_dir, 'iterations')
        if not os.path.isdir(it_dir):
            return set()
        return {n for n in os.listdir(it_dir) if os.path.isdir(os.path.join(it_dir, n))}
    out = _git(task_dir, ['status', '--porcelain', '-z', '--no-renames', '--untracked-files=all', '--', ':(literal)iterations/'], run)
    ids = set()
    for path in _porcelain_paths(out):
        parts = path.split('/')
        if len(parts) >= 3 and parts[0] == 'iterations':
            ids.add(parts[1])
    return ids


def _pending(task_dir, iid, run):
    prefix = f'iterations/{iid}/'
    out = _git(task_dir, ['status', '--porcelain', '-z', '--no-renames', '--untracked-files=all', '--', f':(literal){prefix}'], run)
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
    if not os.path.exists(os.path.join(task_dir, '.git')):
        return {'entries': [_created_from_meta(entry)], 'pending': None, 'degraded': True}
    try:
        raw = _git(task_dir, ['log', f'-n{int(limit)}', '--name-only', '--no-renames',
                              f'--format={_RS}%h{_FS}%an{_FS}%aI{_FS}%s{_FS}%b{_FS}'], run)
        pending = _pending(task_dir, iid, run)
    except OSError:
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
        kind, args, ai, owners = _classify(subject, body, page_names)
        owned = _mentions(subject, iid) if owners is None else iid in owners
        if mine or owned:
            entries.append({'sha': sha, 'at': at, 'actor': {'kind': 'ai', 'name': 'AI'} if ai else {'kind': 'person', 'name': author},
                            'kind': kind, 'args': args, 'text': subject[:TEXT_MAX],
                            'files': sorted(mine)[:FILES_MAX], 'more': max(0, len(mine) - FILES_MAX)})
        if created and (sha.startswith(created) or created.startswith(sha)):
            break
    if not entries:
        entries = [_created_from_meta(entry)]
    return {'entries': entries, 'pending': pending, 'degraded': False}
