#!/usr/bin/env python3
"""Генератор знімка поведінки профілю задачі на 0.14.0: `tests/fixtures/tracks/before-4d1.json` (етап 4d-1, Task 1).

Знімок знято ДО змін коду (код = 0.14.0, коміт `c8c3a8b`; після нього лише docs 4d-1) і лишається в репо як еталон паритету:
тести наступних задач (`tests/test_tracks.py`: ядро, диференційні, API) читають JSON, а не переганяють цей генератор.
Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме знято (запуск на НОВОМУ коді дасть не «до», а «після»: еталон не
перезаписувати).

Що знято (усе — у тимчасових теках, без мережі й без справжніх репо чи дзеркал):
  * `roots` — `serve.work_root(cfg, profile)` для конфігів {обидва ключі: `design_work_roots` (united + seo) і
    `design_work_root`; лише `design_work_root`; нічого; порожнє значення в `design_work_roots`; `design_work_roots` не
    словник} × профілів {`united`, `liga360`, `seo`, `zzz`, `None`}; шлях — ВІДНОСНО тимчасового HOME (`~/…`);
  * `repos` — `serve.profile_repos()` для різних `tasks.json`: добрі й погані пари (`'United'` — поганий ключ, `'-x'` —
    погане репо, не рядок, пробіл усередині, межі довжини ключа), не словник, ключа нема, файла нема, не JSON;
  * `tags` — `serve.task_tags(t)` для задач: без `tags` з різними профілями (відомі, невідомий, з комою, на 40 знаків,
    не рядок, з пробілами), з `tags: []`, з `tags: ['A']`, зіпсовані `tags`, не словник;
  * `ds` — `serve.inspector_ds_arg(p, None)` для профілів {`united`, `seo`, `zzz`, `Bad!`, `''`, `None`};
  * `task_new` — `serve.task_new(cfg, 't1', profile=p)` для профілів {`united`, `liga360`, `seo`, `zzz`, `None`}: запис
    задачі (`dir` відносно HOME, `profile`, `gitlab`, `title`, `jira`, множина ключів) і відповідь; постачальник `vcs`
    підмінено на `None` (скільки разів його питали — теж у знімку: рівно тоді, коли в задачі є `gitlab`);
  * `route` — справжній сервер у процесі на ефемерному порту при ВИМКНЕНОМУ шарі просторів (`DC_TASKS_FILE` на файл ЛІГИ
    без `DEAI_HOME`): `POST /api/task-new` (без `profile`, `seo`, `liga360`, `zzz`, `''`, `null`, `5`, `United`, з `tags`)
    → статус, код, запис задачі; `GET /api/tasks` (рядки: `id`, `profile`, `tags`) і `GET /api/task` (поле `profile`,
    `tags`; задача — заголовком `X-Canvas-Task`, а не `?id=`, див. `task_get_query_id`).

Виключено з JSON усе мінливе: часові поля (`opened`; лишено лише факт наявності), абсолютні шляхи (тека → `~/…`/`<tmp>`).
Прогін двічі дає той самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 tests/make_before_4d1.py [--out ШЛЯХ]   (типово — `tests/fixtures/tracks/before-4d1.json`)

⚠️ ГЕНЕРАТОР РОБИТЬ ЗНІМОК v0.14.0 (код — коміт c8c3a8b) і мусить запускатись проти ЗАМОРОЖЕНОЇ копії старого коду, а не
проти робочої теки (з Task 2–5 `app/`/`bin/` змінюються — і знімок з міткою `source_commit: c8c3a8b` містив би дані «після»).
Як:
    git archive c8c3a8b | tar -x -C <тека>             # заморожена копія коду v0.14.0
    cp tests/make_before_4d1.py <тека>/tests/          # лише сам генератор (він бере ROOT від свого розташування)
    python3 -B <тека>/tests/make_before_4d1.py --out tests/fixtures/tracks/before-4d1.json
Прогін на новому коді — лише як документація: запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від
c8c3a8b, генератор ВІДМОВЛЯЄ (код виходу 2); копія з `git archive` не git-теку — там довіряємо рецепту.

⛔ Ізоляція: власні тимчасові `HOME` (і лише `DC_TASKS_FILE` + `DC_NO_OVERVIEW` — `DEAI_HOME` НЕ виставляється, шар просторів
вимкнено), чисте оточення (змінні конфігу прибрані на час прогону), `serve.vcs_provider` → `None` (жодного дзеркала й git-синку),
`urllib.request.urlopen` — завжди заглушка-лічильник (мережа недосяжна), справжній `~/.deai` стереже `spaces_guard`.
"""
import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'tracks', 'before-4d1.json')
#: Профілі сценаріїв (`None` — запис без профілю). Ключ у JSON для `None` — рядок `'None'`.
PROFILES = ('united', 'liga360', 'seo', 'zzz', None)
#: Профілі для `roots`/`bin` (ще «не той регістр» і порожній рядок: `work_root` бере їх як є).
ROOT_PROFILES = PROFILES + ('United', '')
#: Репо вигаданих напрямків (ЛІГА-подібна таблиця `profile_repos` кореня `tasks.json`).
REPOS = {'united': 'ssh://git@example.com/o/r.git', 'seo': 'git@example.com:studio/web.git'}
#: Змінні оточення, що ізолюють прогін або задають конфіг, — у знімку їх нема (чисте оточення).
CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
         'SUPABASE_SERVICE_KEY', 'DEAI_EXTRA_MODULES', 'DEAI_HOME', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DC_IDENTITY_NAME',
         'DC_IDENTITY_EMAIL', 'DC_TRACKER_FAKE', 'DC_REGISTRY_DIR', 'DC_MIRRORS_DIR', 'DC_REGISTRY_TTL_H',
         'DC_PAGES_LOCK_TIMEOUT', 'PORT', 'DEAI_CONFIRM_MSG', 'DEAI_CONFIRM_TITLE', 'DEAI_TRUST_CONFIRM', 'GIT_DIR',
         'GIT_WORK_TREE', 'GIT_INDEX_FILE')


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))


def rel(text, home):
    """Текст без абсолютних шляхів: домівка → `~` (у тому числі після `realpath`), решта тимчасової теки → `<tmp>`."""
    if not isinstance(text, str):
        return text
    tmp = os.path.dirname(home)
    for root in sorted({home, os.path.realpath(home)}, key=len, reverse=True):
        text = text.replace(root, '~')
    for root in sorted({tmp, os.path.realpath(tmp)}, key=len, reverse=True):
        text = text.replace(root, '<tmp>')
    return text


def _raises(fn):
    """`{raised: <тип>}` — відмова (знімаємо тип, а не ловимо її мовчки) або `{result: …}`."""
    try:
        return {'result': fn()}
    except Exception as e:  # noqa: BLE001
        return {'raised': type(e).__name__}


class NoNet:
    """Підміна `urllib.request.urlopen`: рахує виклики й завжди кидає `OSError` — мережі нема за будь-яких умов."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        raise OSError('мережі нема')


class Vcs:
    """Підміна `serve.vcs_provider` → `None` (ролі `vcs` нема): рахує, скільки разів питали. Без дзеркал і git-синку."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return None


# ---------------------------------------------------------------------------------- roots

def roots(home):
    import serve
    cfgs = {
        'both': {'design_work_roots': {'united': '~/work/united', 'seo': '~/work/seo'}, 'design_work_root': '~/work/shared'},
        'shared_only': {'design_work_root': '~/work/shared'},
        'nothing': {},
        'roots_only': {'design_work_roots': {'united': '~/work/united'}},
        'empty_value': {'design_work_roots': {'united': '', 'seo': '~/work/seo'}, 'design_work_root': '~/work/shared'},
        'roots_null': {'design_work_roots': None, 'design_work_root': '~/work/shared'},
        'absolute': {'design_work_roots': {'united': '/srv/designs/united'}, 'design_work_root': '/srv/designs/shared'},
        'roots_not_dict': {'design_work_roots': ['united'], 'design_work_root': '~/work/shared'},
    }
    out = {}
    for name, cfg in cfgs.items():
        out[name] = {'cfg': cfg, 'by_profile': {
            str(p): _raises(lambda: rel(serve.work_root(cfg, p), home)) for p in ROOT_PROFILES}}
    out['fallback_constant'] = rel(os.path.expanduser(serve.FALLBACK_WORK_ROOT), home)
    return out


# ---------------------------------------------------------------------------------- repos

def repos(tmp):
    import serve
    cases = {
        'good_pairs': {'profile_repos': {'united': 'ssh://git@example.com/o/r.git', 'liga360': 'git@example.com:studio/web.git',
                                         'seo': 'https://example.com/o/seo.git'}},
        'bad_key_uppercase': {'profile_repos': {'United': 'ssh://git@example.com/o/r.git', 'seo': 'git@example.com:s/w.git'}},
        'bad_key_chars': {'profile_repos': {'a b': 'git@example.com:s/w.git', 'a_b': 'git@example.com:s/w.git',
                                            '': 'git@example.com:s/w.git', 'ok-1': 'git@example.com:s/w.git'}},
        'key_len_32_ok_33_bad': {'profile_repos': {'a' * 32: 'git@example.com:s/w.git', 'a' * 33: 'git@example.com:s/w.git'}},
        'bad_repo_dash': {'profile_repos': {'united': '-x', 'seo': '--upload-pack=x', 'liga360': 'git@example.com:s/w.git'}},
        'bad_repo_space': {'profile_repos': {'united': 'git@example.com:s/a b.git', 'seo': 'git@example.com:s/w.git'}},
        'bad_repo_types': {'profile_repos': {'united': 5, 'seo': None, 'liga360': ['x'], 'zzz': {'a': 1}, 'ok': 'g@e:s/w'}},
        'bad_repo_empty': {'profile_repos': {'united': '', 'seo': '   ', 'liga360': 'git@example.com:s/w.git'}},
        'repo_stripped': {'profile_repos': {'united': '  ssh://git@example.com/o/r.git  '}},
        'repo_non_ascii': {'profile_repos': {'united': 'git@example.com:s/в.git'}},
        'not_a_dict': {'profile_repos': ['united']},
        'string_value': {'profile_repos': 'united'},
        'null_value': {'profile_repos': None},
        'no_key': {'design_work_root': '~/work/shared'},
        'cfg_not_dict': ['profile_repos'],
    }
    out = {}
    path = os.path.join(tmp, 'repos-tasks.json')
    for name, cfg in cases.items():
        _write(path, cfg)
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': path}):
            out[name] = {'cfg': cfg, 'result': _raises(serve.profile_repos)}
    with mock.patch.dict(os.environ, {'DC_TASKS_FILE': os.path.join(tmp, 'нема-файла.json')}):
        out['no_file'] = {'result': _raises(serve.profile_repos)}
    _write(path, '{not json')
    with mock.patch.dict(os.environ, {'DC_TASKS_FILE': path}):
        out['not_json'] = {'result': _raises(serve.profile_repos)}
    return out


# ---------------------------------------------------------------------------------- tags

def _short(v):
    """Ключ сценарію зі значення: довгі рядки — `x*40`, решта — `repr`."""
    return 'x*%d' % len(v) if isinstance(v, str) and len(v) > 20 else repr(v)


def tags():
    import serve
    cases = {}
    for p in ('united', 'liga360', 'seo', 'zzz', 'Bad,Comma', 'x' * 32, 'x' * 40, 5, None, '', '  seo  ', 'Seo', ' ', 'a\tb'):
        cases['no_tags_profile_%s' % _short(p)] = {'profile': p}
    cases['no_tags_no_profile'] = {}
    cases['tags_empty_with_profile'] = {'profile': 'united', 'tags': []}
    cases['tags_A_with_profile'] = {'profile': 'united', 'tags': ['A']}
    cases['tags_null_with_profile'] = {'profile': 'united', 'tags': None}
    cases['tags_string_with_profile'] = {'profile': 'united', 'tags': 'x'}
    cases['tags_bad_elements'] = {'profile': 'seo', 'tags': ['ok', 5, '', 'a,b', ' Dup ', 'dup', None, ['x']]}
    cases['tags_over_max'] = {'tags': ['t%d' % i for i in range(14)]}
    cases['tags_spaces_collapsed'] = {'tags': ['  a   b  ']}
    cases['not_a_dict_none'] = None
    cases['not_a_dict_list'] = ['united']
    return {k: {'task': v, 'result': _raises(lambda: serve.task_tags(v))} for k, v in cases.items()}


# ---------------------------------------------------------------------------------- ds

def ds():
    import serve
    out = {}
    for p in ('united', 'liga360', 'seo', 'zzz', 'Bad!', '', None, ' united ', 'x' * 32, 'x' * 33, 'a_b', 'United', 5):
        out[_short(p)] = {'profile': p, 'result': _raises(lambda: serve.inspector_ds_arg(p, None))}
    return out


# ---------------------------------------------------------------------------------- task_new

def _liga_cfg(repos_table):
    return {'design_work_roots': {'united': '~/work/united', 'seo': '~/work/seo'}, 'design_work_root': '~/work/shared',
            'profile_repos': dict(repos_table), 'tasks': {}, 'current': None}


def _entry_view(entry, home):
    """Запис задачі без мінливого: `dir` відносно HOME, `opened` → лише факт наявності."""
    view = {k: rel(v, home) if k == 'dir' else v for k, v in entry.items() if k != 'opened'}
    return {'entry': view, 'keys': sorted(entry), 'has_opened': isinstance(entry.get('opened'), str)}


def task_new(tmp):
    import serve
    out = {}
    for i, p in enumerate(PROFILES):
        home = os.path.join(tmp, 'tn%d' % i, 'home')
        os.makedirs(home)
        path = os.path.join(home, 'tasks.json')
        _write(path, _liga_cfg({'united': REPOS['united']}))      # як у плані: репо лише в `united`
        vcs, net = Vcs(), NoNet()
        with mock.patch.dict(os.environ, {'HOME': home, 'DC_TASKS_FILE': path, 'DC_NO_OVERVIEW': '1'}), \
                mock.patch.object(serve, 'vcs_provider', vcs), mock.patch.object(serve.urllib.request, 'urlopen', net):
            cfg = serve.load_tasks()
            res = serve.task_new(cfg, 't1', profile=p)
            saved = serve.load_tasks()
        it1 = os.path.join(res['dir'], 'iterations', 'it1', 'index.html')
        out[str(p)] = {
            'profile': p,
            'result': {**{k: v for k, v in res.items() if k != 'dir'}, 'dir': rel(res['dir'], home)},
            **_entry_view(saved['tasks']['t1'], home),
            'current': saved['current'], 'it1_index_exists': os.path.isfile(it1),
            'vcs_provider_calls': vcs.calls, 'urlopen_calls': net.calls,
        }
    return out


# ---------------------------------------------------------------------------------- route

class Server:
    """Справжній сервер у процесі на ефемерному порту 127.0.0.1 (не 8765/4317); запити — лише `http.client`."""

    def __enter__(self):
        import serve
        self._quiet = mock.patch.object(serve.Handler, 'log_message', lambda *a, **k: None)
        self._quiet.start()
        self.httpd = serve.make_server(0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.port = self.httpd.server_address[1]
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self._quiet.stop()

    def req(self, method, path, payload=None, task=None, raw_text=False):
        """`(status, тіло)`; Origin — самого сервера; `task` — заголовок `X-Canvas-Task`. Не-JSON тіло → `None` (`raw_text` — тіло рядком)."""
        headers = {'Origin': 'http://127.0.0.1:%d' % self.port}
        if task:
            headers['X-Canvas-Task'] = task
        body = None
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            conn.request(method, path, body=body, headers=headers)
            r = conn.getresponse()
            raw = r.read().decode('utf-8', 'replace')
            if raw_text:
                return r.status, raw
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, None
        finally:
            conn.close()


#: Тіла `POST /api/task-new` без `profile`/з різним `profile`. Ключ — назва сценарію, id задач різні (одна `tasks.json`).
_POSTS = (
    ('no_profile', {'id': 'r-none', 'title': 'Alpha demo'}),
    ('seo', {'id': 'r-seo', 'title': 'Alpha seo', 'profile': 'seo'}),
    ('liga360', {'id': 'r-liga360', 'title': 'Alpha liga360', 'profile': 'liga360', 'jira': 'DEMO-1'}),
    ('united', {'id': 'r-united', 'title': 'Alpha united', 'profile': 'united'}),
    ('unknown_zzz', {'id': 'r-zzz', 'title': 'Alpha zzz', 'profile': 'zzz'}),
    ('empty_string', {'id': 'r-empty', 'title': 'Alpha empty', 'profile': ''}),
    ('null', {'id': 'r-null', 'title': 'Alpha null', 'profile': None}),
    ('uppercase_United', {'id': 'r-upper', 'title': 'Alpha upper', 'profile': 'United'}),
    ('with_tags', {'id': 'r-tags', 'title': 'Alpha tags', 'profile': 'seo', 'tags': ['A', 'B']}),
    ('with_empty_tags', {'id': 'r-notags', 'title': 'Alpha notags', 'profile': 'united', 'tags': []}),
    ('explicit_gitlab', {'id': 'r-gl', 'title': 'Alpha gl', 'profile': 'zzz',
                         'gitlab': {'repo': 'git@example.com:studio/web.git', 'path': 'mockup/r-gl'}}),
    ('not_a_string_5', {'id': 'r-five', 'title': 'Alpha five', 'profile': 5}),
)


def _seeded(home):
    """Файл ЛІГИ з готовими задачами для `GET /api/tasks` / `GET /api/task` (без `opened` — порядок файла стабільний)."""
    specs = (
        ('s-united', {'profile': 'united'}), ('s-liga360', {'profile': 'liga360'}), ('s-seo', {'profile': 'seo'}),
        ('s-zzz', {'profile': 'zzz'}), ('s-tags', {'profile': 'united', 'tags': ['Custom']}),
        ('s-notags', {'profile': 'united', 'tags': []}), ('s-noprofile', {}),
        ('s-comma', {'profile': 'Bad,Comma'}), ('s-five', {'profile': 5}), ('s-upper', {'profile': 'United'}),
    )
    tasks = {}
    for tid, extra in specs:
        d = os.path.join(home, 'work', 'seeded', tid)
        _write(os.path.join(d, 'iterations.json'), {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00'}], 'publish_url': None})
        tasks[tid] = {'dir': d, 'title': 'Seed ' + tid, 'jira': '', **extra}
    return {'design_work_root': os.path.join(home, 'work', 'seeded'), 'profile_repos': dict(REPOS), 'tasks': tasks,
            'current': 's-united'}, [t for t, _ in specs]


def route(tmp):
    import serve
    out = {}
    home = os.path.join(tmp, 'route', 'home')
    os.makedirs(home)
    live = os.path.join(home, 'tasks.json')
    seed = os.path.join(home, 'seeded-tasks.json')
    _write(live, _liga_cfg(REPOS))
    seeded_cfg, seeded_ids = _seeded(home)
    _write(seed, seeded_cfg)
    vcs, net = Vcs(), NoNet()
    env = {'HOME': home, 'DC_TASKS_FILE': live, 'DC_NO_OVERVIEW': '1'}
    with mock.patch.dict(os.environ, env), mock.patch.object(serve, 'vcs_provider', vcs), \
            mock.patch.object(serve.urllib.request, 'urlopen', net), Server() as srv:
        out['layer_on'] = serve.spaces.layer_on()
        # ---- POST /api/task-new: статус, код, запис задачі ----
        posts = {}
        for name, body in _POSTS:
            before = vcs.calls
            st, resp = srv.req('POST', '/api/task-new', body)
            row = {'body': body, 'status': st, 'vcs_provider_calls': vcs.calls - before}
            if isinstance(resp, dict):
                row['ok'] = resp.get('ok')
                row['code'] = resp.get('code')
                row['response_keys'] = sorted(resp)
                for k in ('id', 'cloned', 'registered', 'space', 'space_switched'):
                    if k in resp:
                        row[k] = resp[k]
                if 'dir' in resp:
                    row['dir'] = rel(resp['dir'], home)
            tid = body['id']
            with mock.patch.dict(os.environ, {'DC_TASKS_FILE': live}):
                saved = serve.load_tasks()
            if tid in saved['tasks']:
                row.update(_entry_view(saved['tasks'][tid], home))
            else:
                row['entry'] = None
            posts[name] = row
        out['task_new'] = posts
        with mock.patch.dict(os.environ, {'DC_TASKS_FILE': live}):
            saved = serve.load_tasks()
        out['task_new_current_after'] = saved['current']
        # `GET /api/tasks` після створення: порядок — за `opened` (секунди), тож рядки впорядковано за id
        st, body = srv.req('GET', '/api/tasks')
        out['tasks_after_create'] = {'status': st, 'current': body.get('current'), 'space': body.get('space'),
                                     'rows': sorted(({k: r.get(k) for k in ('id', 'profile', 'tags')} for r in body['tasks']),
                                                    key=lambda r: r['id'])}
        # ---- GET на готових задачах ----
        os.environ['DC_TASKS_FILE'] = seed          # у межах `mock.patch.dict` вище: після виходу значення повертається
        st, body = srv.req('GET', '/api/tasks')
        out['tasks_seeded'] = {'status': st, 'current': body.get('current'), 'space': body.get('space'),
                               'rows': [{k: r.get(k) for k in ('id', 'profile', 'tags', 'title')} for r in body['tasks']]}
        one = {}
        for tid in seeded_ids:
            st, body = srv.req('GET', '/api/task', task=tid)
            one[tid] = {'status': st, 'id': body.get('id'), 'has_profile_key': 'profile' in body,
                        'profile': body.get('profile'), 'tags': body.get('tags'), 'title': body.get('title')}
        out['task_seeded'] = one
        # ⚠️ Плани писали `GET /api/task?id=…`, але маршрут — рівно `/api/task`, задачу обирає заголовок (або `current`):
        # `?id=` не діє. Знімаємо, що саме буде.
        st, body = srv.req('GET', '/api/task?id=s-seo')
        out['task_get_query_id'] = {'status': st, 'body_is_json': body is not None,
                                    'id': body.get('id') if isinstance(body, dict) else None}
        st, body = srv.req('GET', '/api/task')
        out['task_get_no_header'] = {'status': st, 'id': body.get('id'), 'profile': body.get('profile')}
        out['vcs_provider_calls_total'] = vcs.calls
        out['urlopen_calls'] = net.calls
    return out


# ---------------------------------------------------------------------------------- pages (хвіст `?ds=` у розмітці)

#: Хвіст URL інспектора в розмітці сторінки: усе, що йде в `src` одразу за `inspector.js` (`?ds=…&sp=…` або нічого).
_INSPECTOR_SRC = re.compile(r'inspector\.js([^"\'<>\s]*)')


def pages(tmp):
    """Розмітка робочого місця (`GET /commented?it=it1`, БЕЗ `X-Canvas-Task`: сторінка з коментатором під названою задачею
    відмовляється) для кожної готової задачі: хвіст `inspector.js…` — `?ds=<профіль>` (+ `&sp=` лише з простором; шар вимкнено —
    без нього) або його відсутність. Задачу обирає `current` файла (його переписуємо перед кожним запитом). Два входи розмітки
    (`serve.py`, два виклики `profile=task.get('profile') or ''`): локальний канал (типово) і канал модуля (`ch=project`, потрібен
    вигаданий конфіг Supabase у корені файла)."""
    import serve
    home = os.path.join(tmp, 'pages', 'home')
    os.makedirs(home)
    path = os.path.join(home, 'tasks.json')
    cfg, ids = _seeded(home)
    cfg['supabase_url'], cfg['supabase_key'] = 'https://demo.supabase.example', 'pk-test-1'
    for tid in ids:
        _write(os.path.join(cfg['tasks'][tid]['dir'], 'iterations', 'it1', 'index.html'),
               '<!DOCTYPE html><html><head><title>t</title></head><body><h1>Alpha</h1></body></html>')
    out = {}
    net = NoNet()
    with mock.patch.dict(os.environ, {'HOME': home, 'DC_TASKS_FILE': path, 'DC_NO_OVERVIEW': '1'}), \
            mock.patch.object(serve, 'vcs_provider', Vcs()), mock.patch.object(serve.urllib.request, 'urlopen', net), \
            Server() as srv:
        for tid in ids:
            row = {'profile': cfg['tasks'][tid].get('profile', '<нема>')}
            for key, query in (('local', '/commented?it=it1'), ('project', '/commented?it=it1&ch=project')):
                _write(path, {**cfg, 'current': tid})
                try:
                    st, html = srv.req('GET', query, raw_text=True)
                except (http.client.HTTPException, OSError) as e:       # обрив зʼєднання без відповіді — теж поведінка
                    row[key] = {'status': None, 'error': type(e).__name__}
                    continue
                found = _INSPECTOR_SRC.findall(html or '')
                row[key] = {'status': st, 'inspector_tails': found,
                            'project_channel': isinstance(html, str) and '__deaiCommentsCfg' in html}
            out[tid] = row
        out['urlopen_calls'] = net.calls
    return out


# ---------------------------------------------------------------------------------- bin (roots.py, registry.py)

def bin_tools(tmp):
    """`bin/roots.py` (`plan`, `roots_in_use`) на готовому файлі ЛІГИ й `bin/registry.py::_work_root` для тих самих профілів.
    Усе в тимчасовій теці, шляхи — `~/…`; мережі й справжнього реєстру нема (чисті функції над `cfg`)."""
    import registry
    import roots as roots_tool
    home = os.path.join(tmp, 'bin', 'home')
    os.makedirs(home)
    shared, united, seo = (os.path.join(home, 'work', n) for n in ('shared', 'united', 'seo'))
    for d in (os.path.join(shared, 'b-united'), os.path.join(shared, 'b-seo'), os.path.join(shared, 'b-liga360'),
              os.path.join(shared, 'b-zzz'), os.path.join(shared, 'b-upper'), os.path.join(shared, 'b-clash'),
              os.path.join(united, 'b-home'), os.path.join(united, 'b-clash')):
        os.makedirs(d)
    # `~/…` у конфігу — `work_root` розгортає через `expanduser`; `dir` задач — абсолютні (як їх пише `task_new`)
    cfg = {'design_work_roots': {'united': '~/work/united', 'seo': '~/work/seo'}, 'design_work_root': '~/work/shared',
           'tasks': {
               'b-united': {'dir': os.path.join(shared, 'b-united'), 'profile': 'united'},     # переїде в united
               'b-seo': {'dir': os.path.join(shared, 'b-seo'), 'profile': 'seo'},             # переїде в seo
               'b-liga360': {'dir': os.path.join(shared, 'b-liga360'), 'profile': 'liga360'},  # свого кореня нема: на місці
               'b-zzz': {'dir': os.path.join(shared, 'b-zzz'), 'profile': 'zzz'},             # невідомий: спільний, на місці
               'b-upper': {'dir': os.path.join(shared, 'b-upper'), 'profile': 'United'},      # не той регістр: спільний, на місці
               'b-home': {'dir': os.path.join(united, 'b-home'), 'profile': 'united'},        # уже на місці
               'b-clash': {'dir': os.path.join(shared, 'b-clash'), 'profile': 'united'},      # ціль уже існує — стоп
               'b-gone': {'dir': os.path.join(shared, 'b-gone'), 'profile': 'seo'},           # теки нема на диску — стоп
               'b-nodir': {'profile': 'seo'},                                                  # нема `dir` — стоп
               'b-noprofile': {'dir': os.path.join(shared, 'b-noprofile')},                    # без профілю: спільний
           }}
    os.makedirs(os.path.join(shared, 'b-noprofile'))
    cfg_five = {**cfg, 'tasks': {**cfg['tasks'], 'b-five': {'dir': os.path.join(shared, 'b-zzz'), 'profile': 5}}}
    cfg_nothing = {'tasks': {'b-n': {'dir': os.path.join(home, 'deai-work', 'b-n'), 'profile': 'united'}}}

    def view(v):
        """Кортежі → списки; шляхи → `~/…`."""
        if isinstance(v, (list, tuple)):
            return [view(x) for x in v]
        return rel(v, home)

    out = {}
    with mock.patch.dict(os.environ, {'HOME': home}):
        for name, c in (('liga', cfg), ('with_int_profile', cfg_five), ('no_roots', cfg_nothing)):
            out[name] = {'plan': _raises_view(lambda: roots_tool.plan(c), view),
                         'roots_in_use': _raises_view(lambda: roots_tool.roots_in_use(c), view)}
        out['registry_work_root'] = {str(p): _raises_view(lambda: registry._work_root(cfg, p), view) for p in ROOT_PROFILES}
        out['registry_work_root_5'] = _raises_view(lambda: registry._work_root(cfg, 5), view)
        out['registry_work_root_nothing'] = _raises_view(lambda: registry._work_root({}, 'united'), view)
    return out


def _raises_view(fn, view):
    """`_raises` з відносними шляхами в результаті."""
    r = _raises(fn)
    return {'result': view(r['result'])} if 'result' in r else r


# ---------------------------------------------------------------------------------- збирання

def build():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d1-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}):
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.14.0', 'source_commit': _source_commit(),
                             'generator': 'tests/make_before_4d1.py', 'volatile_stripped': ['opened']}}
            snap['roots'] = roots(home)
            snap['repos'] = repos(tmp)
            snap['tags'] = tags()
            snap['ds'] = ds()
            snap['task_new'] = task_new(tmp)
            snap['route'] = route(tmp)
            snap['pages'] = pages(tmp)
            snap['bin'] = bin_tools(tmp)
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.14.0 = `c8c3a8b`; після нього лише docs 4d-1). Зашито, щоб прогін на новому
    коді не видавав себе за «до»."""
    return 'c8c3a8b'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` цієї теки відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — лише коли
    у `ROOT` нема `.git` зовсім (заморожена копія з `git archive`: довіряємо рецепту з докстрінга).

    ⛔ Закрито за замовчуванням ВСЕРЕДИНІ git-теки (ревʼю Task 1: клон зі зміненим `app/serve.py` і `PATH=/nonexistent` чи
    `GIT_DIR=/nonexistent` давав «довіряємо» й перезаписував еталон). Нема `git`, збій чи тайм-аут, зламаний `rev-parse`, чужий
    toplevel, нема коміту-джерела, ненульовий `git diff` (1 = різниця, 128 = збій), збій `ls-files` або будь-який новий файл у
    `app/`/`bin/` (`git diff` їх не бачить) — усе це «відрізняється». Лише чисте `0` + порожній список дозволяє перезапис."""
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
    if untracked.returncode != 0:
        return True
    return diff.returncode != 0 or bool(untracked.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if os.path.abspath(args.out) == os.path.abspath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4d1: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
              'Запускай із замороженої копії (git archive %s | tar -x -C <тека>), див. докстрінг.'
              % (_source_commit(), _source_commit()), file=sys.stderr)
        sys.exit(2)
    snap = build()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print('знімок записано:', args.out)


if __name__ == '__main__':
    main()
