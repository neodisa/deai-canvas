#!/usr/bin/env python3
"""Знімок вихідних рішень 0.21.0 (етап 4d-4c): що прапорець `integrations` вирішував — автопуш, пуш у реєстр, `vcs_target`, канал
коментарів, маршрут `task-new`. Еталон `tests/fixtures/outbound/before-4d4c.json` знято ДО змін коду (тег `v0.21.0`); `collect(tmp)` —
та сама функція, яку після 0.22 кличе `tests/test_outbound_parity_4d4c.py`. Запуск ЛИШЕ з замороженої копії:
    D=$(mktemp -d) && git archive v0.21.0 | tar -x -C "$D" && cp tests/make_before_4d4c.py "$D/tests/"
    HOME=$(mktemp -d) python3 -B "$D/tests/make_before_4d4c.py" --out tests/fixtures/outbound/before-4d4c.json
На коді без `spaces.integrations_for` у типовий шлях еталона не пише (код виходу 2). Мережі нема (`urlopen` і `git push` підмінено)."""
import argparse
import contextlib
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for _p in (_HERE, os.path.join(ROOT, 'app'), os.path.join(ROOT, 'bin')):
    sys.path.insert(0, _p)

from make_before_4d3a import NoNet, Server  # noqa: E402
from make_before_4d3b import _call  # noqa: E402
import liga_fixture as lf  # noqa: E402

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'outbound', 'before-4d4c.json')
STANDS = ('liga', 'liga_unmigrated', 'plain', 'plain_git', 'layer_off')
CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DEAI_HOME', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'DC_TRACKER_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
         'JIRA_EMAIL', 'JIRA_TOKEN', 'DEAI_EXTRA_MODULES')
GIT_ENV = {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@example.com', 'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@example.com',
           'GIT_TERMINAL_PROMPT': '0'}
GITLAB = {'repo': 'g/r', 'path': 'mockup/t1', 'ssh_key': '~/.ssh/k', 'host_ip': '203.0.113.7'}
BODIES = {'jira': {'id': 'n-jira', 'jira': 'DEMO-2'}, 'plain': {'id': 'n-plain'},
          'gitlab': {'id': 'n-gl', 'gitlab': {'repo': 'g/r', 'path': 'mockup/n-gl'}}, 'from': {'id': 'n-from'}}


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f)


def _stand(tmp, name):
    """`{home, deai, space_dir, tdir, sid, tasks, env, legacy_file}`: каталог стенду (див. докстрінг модуля)."""
    import spaces
    old = hasattr(spaces, 'integrations_for')
    root = os.path.join(tmp, name)
    home = os.path.join(root, 'home')
    deai, sp_dir, tdir = os.path.join(home, '.deai'), os.path.join(root, 'space'), os.path.join(root, 'work', 't1')
    os.makedirs(home)
    _write(os.path.join(tdir, 'iterations.json'), {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'n', 'published': False}],
                                                   'publish_url': None})
    os.makedirs(os.path.join(tdir, 'iterations', 'it1'))
    with open(os.path.join(tdir, 'iterations', 'it1', 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<html></html>')
    task = {'dir': tdir, 'title': 'T', 'jira': 'DEMO-1', 'profile': None}
    st = {'home': home, 'deai': deai, 'space_dir': sp_dir, 'tdir': tdir, 'sid': None, 'legacy_file': None}
    work = os.path.join(root, 'work')
    if name == 'layer_off':
        st['tasks'] = os.path.join(root, 'tasks.json')
        _write(st['tasks'], {'current': 't1', 'design_work_root': work, 'tasks': {'t1': task}})
        st['env'] = {'HOME': home, 'DC_TASKS_FILE': st['tasks']}
        return st
    os.makedirs(sp_dir)
    if name.startswith('liga'):
        st['tasks'] = st['legacy_file'] = os.path.join(root, 'legacy-tasks.json')
        _write(st['tasks'], {'registry': {'head': 'abc123', 'synced_at': '2026-11-01T10:00:00Z'}, 'design_work_root': work, 'current': 't1',
                             'tasks': {'t1': dict(task, gitlab=GITLAB)}})
        entry, st['sid'] = {'id': 'legacy', 'path': sp_dir, 'legacy': True}, 'legacy'
        if old:
            entry['integrations'] = True
        if name == 'liga':
            lf.write_records(sp_dir, deai, 'legacy')
        else:
            _write(os.path.join(sp_dir, 'space.json'), {'name': 'Liga'})
    else:
        st['tasks'] = os.path.join(sp_dir, 'tasks.json')
        _write(st['tasks'], {'design_work_root': work, 'current': 't1', 'tasks': {'t1': task}})
        entry, st['sid'] = {'id': 'plain', 'path': sp_dir, 'legacy': False}, 'plain'
        if old:
            entry['integrations'] = False
        mods = {'git-sync': {'enabled': True, 'settings': {'branch': 'main', 'path': 'mockup/{task}'}}} if name == 'plain_git' else None
        _write(os.path.join(sp_dir, 'space.json'), dict({'name': 'Plain'}, **({'modules': mods} if mods else {})))
    _write(os.path.join(deai, 'spaces.json'), {'version': 1, 'current': st['sid'], 'spaces': [entry]})
    st['env'] = {'HOME': home, 'DEAI_HOME': deai}
    return st


@contextlib.contextmanager
def _active(st):
    import deai_modules
    import spaces
    with contextlib.ExitStack() as es:
        es.enter_context(mock.patch.dict(os.environ, dict(GIT_ENV, **st['env'])))
        for k in CLEAN:
            if k not in st['env']:
                os.environ.pop(k, None)
        if st['legacy_file']:
            es.enter_context(mock.patch.object(spaces, 'legacy_tasks_file', lambda: st['legacy_file']))
        es.enter_context(mock.patch('urllib.request.urlopen', NoNet()))
        deai_modules.reset_caches()
        yield


def _fixed(st):
    import spaces
    return spaces.request_space(st['sid']) if st['sid'] else contextlib.nullcontext()


def _autocommit(st, tmp, fixed, n):
    import serve
    import spaces
    bare = os.path.join(tmp, '%s-origin-%d.git' % (os.path.basename(os.path.dirname(st['home'])), n))
    d = os.path.join(st['tdir'], '..', 't-%d' % n)
    os.makedirs(d)
    with open(os.path.join(d, 'f.txt'), 'w') as f:
        f.write('x')
    subprocess.run(['git', 'init', '-q', '--bare', bare], check=True)
    subprocess.run(['git', 'init', '-q'], cwd=d, check=True)
    subprocess.run(['git', 'remote', 'add', 'origin', bare], cwd=d, check=True)
    pushes, real = [], subprocess.run

    def run(cmd, *a, **kw):
        if isinstance(cmd, (list, tuple)) and list(cmd[:2]) == ['git', 'push']:
            pushes.append(1)
            return subprocess.CompletedProcess(cmd, 0, '', '')
        return real(cmd, *a, **kw)
    ctx = spaces.request_space(st['sid']) if fixed and st['sid'] else contextlib.nullcontext()
    with ctx, mock.patch.object(subprocess, 'run', run):
        serve.git_autocommit(d, 'parity')
    return {'pushed': bool(pushes)}


def _registry(st):
    import registry
    import serve
    calls = []

    class _Res:
        refused = {}
    with _fixed(st), mock.patch.object(registry, 'push_tasks', lambda tids, *a, **k: calls.append(list(tids)) or _Res()):
        res = serve._registry_push('t1')
    return {'called': bool(calls), 'result': res}


def _targets(st):
    import serve
    with _fixed(st):
        return {'gitlab': serve.vcs_target('t1', {'gitlab': dict(GITLAB)}, {}),
                'vcs': serve.vcs_target('t1', {'vcs': {'repo': 'g/r', 'ssh_key': '~/.ssh/k'}}, {'path': 'mockup/{task}'})}


def _channel(st):
    with Server() as srv:
        status, body = _call(srv, 'GET', '/api/task', task='t1')
    return {'status': status, 'comment_channel': (body or {}).get('comment_channel')}


def _task_new(st, tmp):
    import serve
    src = os.path.join(tmp, 'src-' + os.path.basename(os.path.dirname(st['home'])))
    os.makedirs(src)
    with open(os.path.join(src, 'index.html'), 'w', encoding='utf-8') as f:
        f.write('<html></html>')

    def offline(*a, **k):
        raise serve.VcsError('vcs-offline', 'offline')
    out = {}
    for name, body in BODIES.items():
        body = dict(body, **({'from': src} if name == 'from' else {}))
        with Server() as srv, mock.patch.object(serve, '_registry_push', lambda tid: False), mock.patch.object(serve, '_vcs_call', offline):
            status, resp = _call(srv, 'POST', '/api/task-new', body=body)
        resp = resp or {}
        out[name] = {'status': status, 'code': resp.get('code'), 'space': resp.get('space'), 'created': bool(resp.get('ok'))}
    return out


def _scrub(obj, tmp):
    txt = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    for p in (os.path.realpath(tmp), tmp):
        txt = txt.replace(p, '<tmp>')
    return json.loads(txt)


def collect(tmp):
    """`{стенд: {розділ: значення}}` для всіх п'яти стендів у тимчасовій теці `tmp`."""
    out = {}
    for name in STANDS:
        st = _stand(tmp, name)
        with _active(st):
            out[name] = {'autocommit': _autocommit(st, tmp, True, 1), 'autocommit_unfixed': _autocommit(st, tmp, False, 2),
                         'registry': _registry(st), 'targets': _targets(st), 'comment_channel': _channel(st),
                         'task_new': _task_new(st, tmp)}
    return _scrub(out, tmp)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT_DEFAULT)
    a = ap.parse_args(argv)
    import spaces
    if os.path.abspath(a.out) == OUT_DEFAULT and not hasattr(spaces, 'integrations_for'):
        print('відмова: еталон знімається лише з коду 0.21.0 (тег v0.21.0)', file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix='before-4d4c-') as tmp:
        data = collect(tmp)
    data['_meta'] = {'code': '0.21.0', 'what': 'вихідні рішення за прапорцем integrations'}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
