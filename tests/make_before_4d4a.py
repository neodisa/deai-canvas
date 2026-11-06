#!/usr/bin/env python3
"""Генератор знімка поведінки напрямків ЛІГИ на 0.19.0: `tests/fixtures/liga-migration/before-4d4a.json` (етап 4d-4a, Task 1).

Знімок знято ДО змін коду (код = 0.19.0, коміт `80dc34a`, тег `v0.19.0`) і лишається в репо еталоном паритету четвертого кроку
міграції ЛІГИ: після 0.20 мітки, `?ds=`, репозиторії, корені нових задач відомих напрямків, `bin/roots.py`, теки задач із
реєстру й відповіді API — ті самі для людини, хоч адаптер напрямків зник (їх веде явний `tracks` у `space.json`), а `profile`
більше не читається з записів. Тести наступних задач (`tests/test_liga_migrate_d.py`) читають JSON, а не переганяють генератор.
Запуск на НОВОМУ коді дасть не «до», а «після»: еталон не перезаписувати.

Спільні помічники (`Rig`, `NoNet`, `SocketTripwire`, `scrub`, `rel`, `CLEAN`, `_write`, вигадані константи, `_call`) ІМПОРТУЮТЬСЯ з
`make_before_4d3a.py`/`make_before_4d3b.py`: друга копія розійшлась би.

Чотири стенди; на кожному — ті самі секції:
  * `parity`   — ЛІГА з адаптером і повним паритетом (`united` без власного кореня), `space.json` нема;
  * `notes`    — ЛІГА, де розбіжності з адаптером є всіх типів (корінь системної теки, відносний корінь, власний корінь `united`
                 ≠ спільного, значення поза переліком, ключі поза `ID_RE`);
  * `explicit` — ЛІГА з уже явним `tracks` у `space.json` (як після 4d-3a);
  * `plain`    — звичайний простір (без інтеграцій) зі своїми `tracks`.
Секції: `labels` (`serve.task_tags`), `ds` (`serve.task_ds`), `repos` (`serve.track_repo`), `roots` (`serve.track_root`),
`view` (`serve.space_tracks`), `task_new` (`POST /api/task-new`: статус, код, запис), `roots_cli` (`roots.plan`/`roots_in_use`),
`registry` (`registry._work_root` для записів реєстру з `profile`/`track`), `api` (`GET /api/task`, `GET /api/tasks`: ключі й
значення; `profile` у відповіді — ТАК, у знімку).

⚠️ ПІДПИСИ 0.19.0: `serve.track_root(sp, cfg, tid)` (три аргументи); у новому коді — `track_root(sp, tid)`. Тести «після» кличуть
нову форму. Не міняти тут: це документація того, як знято.

Запуск (з кореня репо): проти ЗАМОРОЖЕНОЇ копії старого коду:
    D=$(mktemp -d) && git archive v0.19.0 | tar -x -C "$D" && cp tests/make_before_4d4a.py "$D/tests/"
    python3 -B "$D/tests/make_before_4d4a.py" --out tests/fixtures/liga-migration/before-4d4a.json
Запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від `80dc34a`, генератор ВІДМОВЛЯЄ (код виходу 2).

⛔ Ізоляція: власні тимчасові `HOME` і `DEAI_HOME`, чисте оточення, жодної мережі (розтяжка сокетів), `serve.vcs_provider` →
`None`, шпигуни замість `serve._registry_push`/`serve.git_autocommit`/`Handler._overview_sync`; справжній `~/.deai` стереже
`spaces_guard`; порти 8765/4317 не чіпаємо (ефемерний порт loopback).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

from make_before_4d3a import (CLEAN, REPO_SEO, REPO_UNITED, NoNet, Rig, Server, SocketTripwire, Vcs,  # noqa: E402
                              _write, rel, scrub)
from make_before_4d3b import _call  # noqa: E402

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d4a.json')
STANDS = ('parity', 'notes', 'explicit', 'plain')
#: Значення напрямку в сценаріях (`7` і `None` — не рядки). Ключ у JSON — `repr`.
VALUES = ('united', 'liga360', 'seo', 'custom-x', 'United', 'zzz', '', None, 7)
#: Задачі стендів: різна форма запису напрямку (старий лише `profile`, новий `track`, обидва, жодного, не рядок).
TASKS = {
    'a-1': {'track': 'seo'},
    'a-2': {'profile': 'united'},
    'a-3': {'profile': 'liga360', 'track': 'liga360'},
    'a-4': {'track': 'zzz'},
    'a-5': {'track': 'United'},
    'a-6': {},
    'a-7': {'track': 'seo', 'profile': 'united'},
    'a-8': {'profile': 5},
}
#: Задачі зі значенням поза переліком (`zzz`, `United`) — лише на стенді `notes` (на `parity` вони дали б нотатку `unknown-values`).
UNKNOWN_ONLY_IN_NOTES = ('a-4', 'a-5')
#: Тіла `POST /api/task-new` (ключ — назва сценарію; `id` різні, `space` додається генератором).
POSTS = (
    ('none', {'id': 'n-none', 'title': 'Alpha'}),
    ('track_seo', {'id': 'n-seo', 'title': 'Alpha', 'track': 'seo'}),
    ('profile_seo', {'id': 'n-pseo', 'title': 'Alpha', 'profile': 'seo'}),
    ('profile_united_track_seo', {'id': 'n-conf', 'title': 'Alpha', 'profile': 'united', 'track': 'seo'}),
    ('track_upper', {'id': 'n-up', 'title': 'Alpha', 'track': 'United'}),
    ('profile_upper', {'id': 'n-pup', 'title': 'Alpha', 'profile': 'United'}),
    ('track_zzz', {'id': 'n-zzz', 'title': 'Alpha', 'track': 'zzz'}),
    ('profile_zzz', {'id': 'n-pzzz', 'title': 'Alpha', 'profile': 'zzz'}),
    ('track_not_a_string', {'id': 'n-five', 'title': 'Alpha', 'track': 5}),
    ('profile_not_a_string', {'id': 'n-pfive', 'title': 'Alpha', 'profile': 5}),
    ('track_with_slash', {'id': 'n-bad', 'title': 'Alpha', 'track': 'Bad/Id'}),
)
#: Записи спільного реєстру колег: старий інструмент шле лише `profile`.
REGISTRY_ENTRIES = {'profile_only_seo': {'profile': 'seo'}, 'track_only_seo': {'track': 'seo'},
                    'both_conflict': {'profile': 'united', 'track': 'seo'}, 'none': {}, 'profile_unknown': {'profile': 'zzz'}}


def _tasks(rig, notes):
    w = os.path.join(rig.home, 'work')
    out = {}
    for tid, extra in TASKS.items():
        if tid in UNKNOWN_ONLY_IN_NOTES and not notes:
            continue
        d = os.path.join(w, tid)
        _write(os.path.join(d, 'iterations.json'), {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00'}], 'publish_url': None})
        out[tid] = {'dir': d, 'title': 'Task ' + tid, 'jira': '', **extra}
    return out


def _stand(tmp, name):
    """`(rig, sp, cfg)`: ЛІГА (`sp` — запис ЛІГИ) чи звичайний простір (`plain`), старий `tasks.json` із задачами `TASKS`."""
    rig = Rig(tmp, name)
    w = os.path.join(rig.home, 'work')
    extra = {'tasks': _tasks(rig, name == 'notes'), 'current': 'a-1'}
    if name == 'notes':
        extra['design_work_roots'] = {'united': os.path.join(w, 'united'), 'seo': os.path.join(rig.home, '.hidden', 'seo'), 'liga360': 'rel/l360',
                                      'custom-x': os.path.join(w, 'custom'), 'Bad_Key': os.path.join(w, 'bad')}
        extra['profile_repos'] = {'united': REPO_UNITED, 'seo': REPO_SEO, 'Bad_Key': REPO_UNITED}
        extra['tasks']['a-9'] = {'dir': os.path.join(w, 'a-9'), 'title': 'Task a-9', 'jira': '', 'profile': 'Weird'}
    elif name == 'explicit':                             # `space.json` дзеркалить корінь `tasks.json`, як записала б міграція
        extra['design_work_roots'] = {'seo': os.path.join(w, 'seo'), 'custom-x': os.path.join(w, 'custom')}
    elif name in ('parity', 'plain'):
        extra['design_work_roots'] = {'custom-x': os.path.join(w, 'custom')}      # `united` без власного кореня: паритет повний
    cfg = rig.config(extra=extra)
    if name == 'explicit':
        shared = os.path.join(w, 'shared')
        liga = rig.registry(space_json={
            'tracks': [{'id': 'united', 'label': 'United', 'root': shared, 'repo': REPO_UNITED, 'ds': 'united'},
                       {'id': 'liga360', 'label': 'LIGA360', 'root': shared, 'repo': '', 'ds': 'liga360'},
                       {'id': 'seo', 'label': 'SEO', 'root': os.path.join(w, 'seo'), 'repo': REPO_SEO, 'ds': 'seo'},
                       {'id': 'custom-x', 'label': 'custom-x', 'root': os.path.join(w, 'custom'), 'repo': '', 'ds': 'custom-x'}],
            'default_track': 'united'})
    else:
        liga = rig.registry()
    sp = liga
    if name == 'plain':
        plain_dir = os.path.join(rig.home, 'plain-space')       # у HOME: корінь поза HOME `tracks.normalize` відкинув би
        _write(os.path.join(plain_dir, 'space.json'), {'tracks': [
            {'id': 'web', 'label': 'Web', 'root': os.path.join(plain_dir, 'web'), 'repo': REPO_UNITED, 'ds': 'web'},
            {'id': 'app', 'label': 'App', 'root': None, 'repo': '', 'ds': ''}], 'default_track': 'web'})
        _write(os.path.join(plain_dir, 'tasks.json'), {'tasks': {}, 'current': ''})
        sp = {'id': 'plain', 'path': plain_dir, 'legacy': False, 'integrations': False}
        reg = {'version': 1, 'current': 'legacy', 'spaces': [liga, sp]}
        _write(os.path.join(rig.deai, 'spaces.json'), reg)
    return rig, sp, cfg


def _entry_view(entry, home):
    """Запис задачі для знімка: ключі напрямку + `dir` відносно HOME + множина ключів."""
    return {'track': entry.get('track', '<absent>'), 'profile': entry.get('profile', '<absent>'),
            'dir': rel(entry.get('dir'), home), 'keys': {k: True for k in sorted(entry)}}


def _scenarios(tmp, name):
    import registry
    import roots
    import serve
    rig, sp, cfg = _stand(tmp, name)
    out = {}
    spy = mock.MagicMock(return_value=False)
    with rig.activate(), mock.patch.object(serve, 'vcs_provider', Vcs()), mock.patch.object(serve, '_registry_push', spy), \
            mock.patch.object(serve, 'git_autocommit', lambda *a, **k: None), \
            mock.patch.object(serve.Handler, '_overview_sync', lambda *a, **k: None):
        tasks = cfg['tasks']
        out['labels'] = {tid: serve.task_tags(t, sp) for tid, t in tasks.items()}
        out['ds'] = {tid: serve.task_ds(t, sp) for tid, t in tasks.items()}
        items, default = serve.space_tracks(sp)
        out['view'] = {'ids': [t['id'] for t in items], 'labels': [t['label'] for t in items], 'default': default,
                       'repos': {t['id']: t['repo'] for t in items}, 'ds': {t['id']: t['ds'] for t in items},
                       'roots': {t['id']: rel(t['root'], rig.home) for t in items}}
        values = VALUES + (('web', 'app') if name == 'plain' else ())
        out['repos'] = {repr(v): serve.track_repo(sp, v) for v in values}
        out['roots'] = {repr(v): rel(serve.track_root(sp, cfg, v), rig.home) for v in values}     # 0.19.0: (sp, cfg, track)
        if name != 'plain':                              # `bin/roots.py` і реєстр — інструменти ЛІГИ
            with serve.spaces.request_space(sp['id']):
                out['roots_cli'] = {
                    'plan': {r[0]: r[1:] for r in scrub([list(r) for r in roots.plan(cfg)], rig.home)},
                    'in_use': {r[0]: r[1:] for r in scrub([list(r) for r in roots.roots_in_use(cfg)], rig.home)}}
            out['registry'] = {k: rel(registry._work_root(cfg, e), rig.home) for k, e in REGISTRY_ENTRIES.items()}
        with Server() as srv:
            posts = {}
            for key, body in POSTS:
                body = dict(body, space=sp['id'])
                st, resp = _call(srv, 'POST', '/api/task-new', body=body)
                row = {'status': st, 'code': resp.get('code') if isinstance(resp, dict) else None}
                tf = spaces_tasks_file(sp)
                with open(tf, encoding='utf-8') as f:
                    saved = json.load(f)['tasks']
                row['entry'] = _entry_view(saved[body['id']], rig.home) if body['id'] in saved else None
                posts[key] = row
            out['task_new'] = posts
            api = {'task': {}}
            for tid in ('a-1', 'a-2', 'a-3', 'a-6', 'a-8'):
                if name == 'plain':
                    break
                st, body = srv.req('GET', '/api/task', task=tid)
                api['task'][tid] = {'status': st, 'keys': {k: True for k in sorted(body)} if isinstance(body, dict) else None,
                                    'profile': body.get('profile', '<absent>'), 'track': body.get('track'), 'tags': body.get('tags')}
            st, body = srv.req('GET', '/api/tasks')
            api['tasks'] = {'status': st, 'rows': [{k: r.get(k, '<absent>') for k in ('id', 'profile', 'track', 'tags')}
                                                    for r in sorted(body.get('tasks', []), key=lambda r: r['id'])
                                                    if r['id'].startswith('a-')]}
            st, body = srv.req('GET', '/api/spaces')
            row = next(r for r in body['spaces'] if r['id'] == sp['id'])
            api['space_row'] = {'tracks': row.get('tracks'), 'default_track': row.get('default_track')}
            out['api'] = api
    return scrub(out, rig.home)


def spaces_tasks_file(sp):
    import spaces
    return spaces.tasks_file(sp)


def make():
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d4a-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire, mock.patch('urllib.request.urlopen', NoNet()):
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.19.0', 'source_commit': _source_commit(), 'generator': 'tests/make_before_4d4a.py',
                             'volatile_stripped': []}, 'stands': {}}
            for name in STANDS:
                snap['stands'][name] = _scenarios(tmp, name)
            snap['non_loopback_attempts'] = wire.count
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.19.0 = `80dc34a`; після нього лише docs 4d-4a). Зашито."""
    return '80dc34a'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — у `ROOT` нема `.git`
    (заморожена копія з `git archive`: довіряємо рецепту). Закрито за замовчуванням усередині git-теки (рецепт 4d-3a)."""
    if not os.path.lexists(os.path.join(ROOT, '.git')):
        return None
    try:
        top = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=30)
        if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
            return True
        src = _source_commit()
        if subprocess.run(['git', '-C', ROOT, 'cat-file', '-e', src + '^{commit}'], capture_output=True, timeout=30).returncode != 0:
            return True
        diff = subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', src, '--', 'app', 'bin'], capture_output=True, timeout=60)
        untracked = subprocess.run(['git', '-C', ROOT, 'ls-files', '--others', '--exclude-standard', '--', 'app', 'bin'],
                                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return True
    return untracked.returncode != 0 or diff.returncode != 0 or bool(untracked.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if os.path.realpath(args.out) == os.path.realpath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4d4a: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
              'Запускай із замороженої копії (git archive %s | tar -x -C <тека>), див. докстрінг.'
              % (_source_commit(), _source_commit()), file=sys.stderr)
        sys.exit(2)
    snap = make()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print('знімок записано:', args.out)


if __name__ == '__main__':
    main()
