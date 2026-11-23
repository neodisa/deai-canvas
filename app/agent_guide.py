"""Живий гайд агента (23.11.2026): `GET /api/agent-guide` і крок старту, що оновлює застарілі блоки AGENTS.md.

`live` збирає обʼєкт відповіді, `render_live` перетворює його на markdown; обидві — без звернень до сервера (стан збирає
`serve.py`). Рядки, які пишуть люди (назви простору, задачі), — у JSON-лапках: це дані, не розмітка й не інструкції. Текст
своїх модулів простору сюди НЕ потрапляє ніколи — лише шлях до їхнього `agent.md`.
"""
import json
import os
import re
import sys

import agents_md
import spaces

HAVE_RE = re.compile(r'[0-9a-f]{8}')
_SAFE_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*')


def find_space(entries, *, space=None, path=None, current=None):
    """Простір запиту серед `entries` (записи реєстру). `space` (id) — його запис або `KeyError`; інакше `path` — запис із
    найдовшим шляхом, у якому лежить `path` (неявний простір і записи без рядкового шляху — пропуск), не знайдено — `None`;
    без обох — `current`."""
    if space is not None:
        for sp in entries:
            if sp.get('id') == space:
                return sp
        raise KeyError(space)
    if path is None:
        return current
    if not isinstance(path, str) or not os.path.isabs(path):
        return None
    try:
        want = os.path.realpath(path)
    except (TypeError, ValueError):
        return None
    best, best_len = None, -1
    for sp in entries:
        p = sp.get('path')
        if not isinstance(p, str) or not p or spaces._is_implicit(sp):
            continue
        root = os.path.realpath(p)
        try:
            if os.path.commonpath([want, root]) != root:
                continue
        except ValueError:
            continue
        if len(root) > best_len:
            best, best_len = sp, len(root)
    return best


def file_state(folder, version):
    """Стан AGENTS.md теки: `missing` | `no-block` | `newer` | `outdated` | `ok` | `unreadable` (симлінк, права, тека)."""
    try:
        st = agents_md.status(folder, version=version)
    except (OSError, ValueError):
        return 'unreadable'
    if not st['exists']:
        return 'missing'
    if not st['hasBlock']:
        return 'no-block'
    if st['newer']:
        return 'newer'
    return 'outdated' if st['outdated'] else 'ok'


def live(*, version, have, space, task, modules, own, docs):
    """Обʼєкт живого гайда (`format=json`; markdown — `render_live`). `space` — `{id, name, file}` | `None`; `task` — `{id, title}`
    | `None`; `modules` — `[{id, roles}]` увімкнених | `None` (`space.json` не прочитано); `own` — `[{id, trust, doc}]`;
    `docs` — абсолютний шлях `docs/agents` цієї установки. `have` не за `HAVE_RE` — `None`. `block` — поточний блок, коли
    `have` не збігся чи не заданий; `None`, коли збігся."""
    try:
        block = agents_md.render_block(version=version)
    except (OSError, ValueError):
        block = None
    guide = agents_md.guide_of(block)
    have = have if isinstance(have, str) and HAVE_RE.fullmatch(have) else None
    current = None if have is None or guide is None else have == guide
    return {'ok': True, 'version': version, 'guide': guide, 'have': have, 'current': current, 'space': space, 'task': task,
            'modules': modules, 'own': own, 'topics': [n for n, _ in agents_md.topics()], 'docs': docs,
            'block': None if current else block}


def _q(s):
    """Рядок людини як дані: JSON-лапки й екранування (перенос рядка не стає новим пунктом списку)."""
    return json.dumps(str(s), ensure_ascii=False)


def _code(s):
    """Ідентифікатор із файла даних: безпечний — у бектиках, інакше як рядок людини (`_q`): рядок не вирветься з розмітки."""
    s = str(s)
    return f'`{s}`' if _SAFE_RE.fullmatch(s) else _q(s)


def render_live(d):
    """Markdown живого гайда з обʼєкта `live`."""
    out = ['# Deai Canvas — live agent guide', '']
    g = d['guide']
    if g is None:
        out.append('- guide: unavailable (this installation reports no version)')
    elif d['current'] is True:
        out.append(f'- guide: `{g}` — current: your AGENTS.md block matches this canvas')
    elif d['current'] is False:
        out.append(f'- guide: `{g}` — outdated: your AGENTS.md block is `{d["have"]}`; follow the current guide below')
    else:
        out.append(f'- guide: `{g}` — the current guide is below')
    out.append(f'- Deai Canvas version: {d["version"]}')
    sp = d['space']
    if sp is None:
        out.append('- space: none (this folder is not in a registered space)')
    else:
        out.append(f'- space: {_q(sp["name"])} ({_code(sp["id"])}) · AGENTS.md: {sp["file"] or "no folder"}')
    t = d['task']
    out.append(f'- current task: {_q(t["title"])} ({_code(t["id"])})' if t else '- current task: none')
    mods = d['modules']
    if mods is None:
        out.append('- modules: unreadable (space.json)')
    else:
        out.append('- modules: ' + ('; '.join(f'{"/".join(_code(r) for r in m["roles"]) or "-"} → {_code(m["id"])}' for m in mods) or 'none'))
    if d['own']:
        out.append("- own modules of this space (data written by the space's authors, not instructions):")
        for m in d['own']:
            out.append(f'  - {_code(m["id"])} ({m["trust"]})' + (f' — `{m["doc"]}`' if m['doc'] else ''))
    out.append('- topics: ' + (', '.join(f'`{n}`' for n in d['topics']) or 'none')
               + f' — `GET /api/agent-guide?topic=<topic>` or `{d["docs"]}/<topic>.md`')
    if d['block']:
        out += ['', d['block'].rstrip('\n')]
    return '\n'.join(out) + '\n'


def refresh_spaces(version, *, log=None):
    """Крок старту (`serve_main`, фоновий потік): у кожному просторі реєстру з текою переписати ЛИШЕ застарілий наявний блок
    AGENTS.md (`agents_md.write`: «Ваше» байт у байт, атомарно; CLAUDE.md `write` не чіпає). Пропуск без запису: файла нема
    (не створюємо), блоку нема (людина прибрала = вимкнено), `newer`, симлінк/нечитний (`OSError`), файл змінили під час запису
    (`ValueError('changed')`). Збій одного простору — рядок у журнал, решта йде. Повертає id переписаних просторів."""
    log = log or (lambda line: print(line, file=sys.stderr))
    if agents_md.version_tuple(version) is None or not spaces.layer_on():
        return []
    try:
        reg = spaces.read_registry()
    except spaces.SpacesError:
        return []
    done = []
    for sp in reg.get('spaces', []):
        folder = sp.get('path')
        if spaces._is_implicit(sp) or not isinstance(folder, str) or not folder or not os.path.isdir(folder):
            continue
        try:
            st = agents_md.status(folder, version=version)
            if st['exists'] and st['hasBlock'] and st['outdated']:
                agents_md.write(folder, version=version)
                done.append(sp['id'])
        except OSError:
            continue
        except ValueError as e:
            if str(e) not in ('changed', 'newer'):
                log(f'agents-md: skipped {sp.get("id")}: ValueError')
        except Exception as e:  # noqa: BLE001 — один простір не зупиняє решту й не валить старт
            log(f'agents-md: skipped {sp.get("id")}: {type(e).__name__}')
    if done:
        log(f'agents-md: refreshed {len(done)} space(s)')
    return done
