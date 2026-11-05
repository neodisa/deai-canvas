#!/usr/bin/env python3
"""Генератор знімка поведінки «неявного постачальника» на 0.15.0: `tests/fixtures/implicit/before-4d2.json` (етап 4d-2, Task 1).

Знімок знято ДО змін коду (код = 0.15.0, коміт `6e68250`; після нього лише docs 4d-2) і лишається в репо як еталон паритету:
тести наступних задач (`tests/test_implicit.py`: ядро, диференційні, API, ізоляція) читають JSON, а не переганяють цей
генератор. Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме знято (запуск на НОВОМУ коді дасть не «до», а «після»: еталон не
перезаписувати).

Що знято (усе — у тимчасових теках, без мережі й без справжніх репо, дзеркал, Supabase, Jira чи Teams):
  * `caps` — `deai_modules.capabilities(space)` для: ЛІГИ (`integrations: True`, без `space.json`); ЛІГИ з нечитабельним
    `space.json`; звичайного простору без модулів; звичайного з явним `static-publish`; звичайного з нечитабельним `space.json`;
    звичайного зі своїм модулем «на папері» (недовірений); збою відбитків (підміна `_caps_key` → виняток; ЛІГА і звичайний);
  * `provider` — `deai_modules.provider(role)` для кожної ролі (`ROLES_CALLED`) при {шар вимкнено (`DC_TASKS_FILE` без
    `DEAI_HOME`); шар увімкнено, простір запиту не зафіксовано}: значення (`'legacy'`/`None`/id) і ЛІЧИЛЬНИКИ читання реєстру
    (`spaces.load_registry`), `space.json` (`deai_modules.space_modules`) і каталогу (`deai_modules.catalog`);
  * `api` — справжній сервер у процесі на ефемерному порту: `GET /api/spaces` (ключ `capabilities` кожного простору), `GET /api/space`
    (⚠️ такого маршруту нема — знято його фактичну відповідь; простір задачі — поле `space` в `GET /api/task`), `GET /api/task`
    (заголовок `X-Canvas-Task`): `space.capabilities`, `publish_gate`, `preview_gate`. Два режими: ЛІГА в реєстрі тимчасового
    `DEAI_HOME`; шар вимкнено;
  * `isolation` — закон ізоляції для постачальника `'legacy'` у ролях `dashboard` (`serve._team_fetch` / `serve.team_rows`),
    `tracker` (`serve._tracker_fetch`), `notify` (`serve.notify_call`: `mute_state`, `mute_set`) і синку дашборда
    (`Handler._overview_sync` — чи запущено дитину; `_overview_launch` підмінено): (а) зі швом/фейком — результат;
    (б) з `DC_TASKS_FILE` без шва — результат чи клас і текст винятку; (в) з `DC_NO_OVERVIEW` без `DC_TASKS_FILE` — те саме;
    модуль при (б)/(в) НЕ кличеться (лічильник підмінених `deai_modules.call` і виклику модуля ролі);
  * `install` — `install_config.supabase_config()` і `jira_config()` під `DC_TASKS_FILE` (корінь фікстури з парою / без пари) ×
    {змінні `SUPABASE_URL`/`SUPABASE_KEY`/`JIRA_EMAIL`/`JIRA_TOKEN` вигадані / ні} × {файли
    `<HOME>/.claude/pipeline-feedback/jira-email|jira-token` у ТИМЧАСОВОМУ HOME є / нема}: значення (вигадані — можна писати);
  * `build` — `"build"` у `manifest.json`, який пише `serve.build_preview` (збірка ЛІГИ — `legacy`, збірка модуля — `module`; без
    мітки), `serve.BUILD_KINDS` і відмова на невідомій мітці.

Виключено з JSON усе мінливе: часові поля, абсолютні шляхи (тека → `~/…`/`<tmp>`). Прогін двічі дає той самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 tests/make_before_4d2.py [--out ШЛЯХ]   (типово — `tests/fixtures/implicit/before-4d2.json`)

⚠️ ГЕНЕРАТОР РОБИТЬ ЗНІМОК v0.15.0 (код — коміт 6e68250) і мусить запускатись проти ЗАМОРОЖЕНОЇ копії старого коду, а не
проти робочої теки (з Task 2–6 `app/`/`bin/` змінюються — і знімок з міткою `source_commit: 6e68250` містив би дані «після»).
Як:
    git archive 6e68250 | tar -x -C <тека>             # заморожена копія коду v0.15.0
    cp tests/make_before_4d2.py <тека>/tests/          # лише сам генератор (він бере ROOT від свого розташування)
    python3 -B <тека>/tests/make_before_4d2.py --out tests/fixtures/implicit/before-4d2.json
Прогін на новому коді — лише як документація: запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від
6e68250, генератор ВІДМОВЛЯЄ (код виходу 2); копія з `git archive` — не git-тека, там довіряємо рецепту.

⛔ Ізоляція: власні тимчасові `HOME` (звідси `~/.deai` і `~/.claude/pipeline-feedback/` — тимчасові) і `DEAI_HOME`, чисте
оточення (змінні конфігу прибрані на час прогону; потрібні виставляються ЛИШЕ тут, через `mock.patch.dict`, вигаданими значеннями),
жодної мережі (`urllib.request.urlopen` — заглушка-лічильник), `serve.vcs_provider` → `None` (жодного дзеркала й git-синку),
`Popen` і `_overview_launch` — заглушки; справжній `~/.deai` стереже `spaces_guard`.
"""
import argparse
import http.client
import json
import os
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

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'implicit', 'before-4d2.json')
#: Змінні оточення, що ізолюють прогін або задають конфіг, — у знімку їх нема (чисте оточення).
CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'DC_TRACKER_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
         'SUPABASE_SERVICE_KEY', 'DEAI_EXTRA_MODULES', 'DEAI_HOME', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DC_IDENTITY_NAME',
         'DC_IDENTITY_EMAIL', 'DC_REGISTRY_DIR', 'DC_MIRRORS_DIR', 'DC_REGISTRY_TTL_H', 'DC_PAGES_LOCK_TIMEOUT', 'PORT',
         'DEAI_CONFIRM_MSG', 'DEAI_CONFIRM_TITLE', 'DEAI_TRUST_CONFIRM', 'DEAI_OWN_CANARY', 'GIT_DIR', 'GIT_WORK_TREE',
         'GIT_INDEX_FILE')

# Вигадані значення (репо приватне й знеособлене: жодних справжніх хостів, ключів, імен).
SB_URL = 'https://sb.example.com'
SB_KEY = 'sb_test_key'
SB_ENV_URL = 'https://sb-env.example.com'
SB_ENV_KEY = 'sb_env_key'
JIRA_BASE = 'https://jira.example.com'
JIRA_ENV_EMAIL, JIRA_ENV_TOKEN = 'alpha@example.com', 'jira_env_token'
JIRA_FILE_EMAIL, JIRA_FILE_TOKEN = 'file@example.com', 'jira_file_token'


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


def _outcome(fn, home):
    """`{result: …}` або `{raised: <клас>, message: <текст без шляхів>}` — відмову знімаємо, а не ловимо мовчки."""
    try:
        return {'result': fn()}
    except Exception as e:  # noqa: BLE001
        return {'raised': type(e).__name__, 'message': rel(str(e), home)}


class NoNet:
    """Підміна `urllib.request.urlopen`: рахує виклики й завжди кидає `OSError` — мережі нема за будь-яких умов."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        raise OSError('мережі нема')


class Vcs:
    """Підміна `serve.vcs_provider` → `None` (ролі `vcs` нема): без дзеркал і git-синку."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return None


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

    def req(self, method, path, task=None):
        """`(status, тіло-JSON чи None)`; Origin — самого сервера; `task` — заголовок `X-Canvas-Task`."""
        headers = {'Origin': 'http://127.0.0.1:%d' % self.port}
        if task:
            headers['X-Canvas-Task'] = task
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            conn.request(method, path, headers=headers)
            r = conn.getresponse()
            raw = r.read().decode('utf-8', 'replace')
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, None
        finally:
            conn.close()


# ---------------------------------------------------------------------------------- caps

def caps(tmp):
    """`capabilities(space)` для сімох сценаріїв. Шар увімкнено (тимчасовий `DEAI_HOME`): тільки так видно свої модулі простору."""
    import deai_modules as dm
    home = os.path.join(tmp, 'caps', 'home')
    os.makedirs(home)
    out = {}

    def space(sid, integrations=None, legacy=False):
        path = os.path.join(tmp, 'caps', sid)
        os.makedirs(path)
        sp = {'id': sid, 'path': path}
        if integrations is not None:
            sp['integrations'] = integrations
        if legacy:
            sp['legacy'] = True
        return sp

    def snap(name, sp, fn=None):
        dm.reset_caches()
        out[name] = {'space': {k: rel(v, home) if k == 'path' else v for k, v in sp.items()},
                     'caps': (fn or (lambda: dm.capabilities(sp)))()}

    with mock.patch.dict(os.environ, {'DEAI_HOME': os.path.join(home, '.deai')}):
        liga = space('legacy', True, legacy=True)
        snap('liga', liga)
        liga_bad = space('legacy-bad', True, legacy=True)
        _write(os.path.join(liga_bad['path'], 'space.json'), '{не json')
        snap('liga_unreadable_space_json', liga_bad)
        snap('plain_no_modules', space('plain'))
        plain_sp = space('plain-static')
        _write(os.path.join(plain_sp['path'], 'space.json'), {'modules': {'static-publish': {'enabled': True}}})
        snap('plain_static_publish', plain_sp)
        plain_bad = space('plain-bad')
        _write(os.path.join(plain_bad['path'], 'space.json'), '{не json')
        snap('plain_unreadable_space_json', plain_bad)
        # свій модуль «на папері»: теку модуля є, довіри до нього нема (недовірений), у `space.json` він явно ввімкнений
        own = space('plain-own')
        _write(os.path.join(own['path'], 'modules', 'acme', 'module.json'),
               {'api': 1, 'id': 'acme', 'name': 'Acme', 'version': '1.0.0', 'roles': ['publish'], 'settings': []})
        _write(os.path.join(own['path'], 'modules', 'acme', 'server.py'), 'def publish(ctx, build_dir, task):\n    return {}\n')
        _write(os.path.join(own['path'], 'space.json'), {'modules': {'acme': {'enabled': True, 'roles': ['publish']}}})
        snap('plain_own_module_untrusted', own)
        # збій відбитків: `_caps_key` кидає — `capabilities` тотальна й віддає запасну форму
        boom = mock.patch.object(dm, '_caps_key', side_effect=RuntimeError('збій відбитків'))
        with boom:
            snap('fingerprint_failure_liga', space('legacy-fp', True, legacy=True))
            snap('fingerprint_failure_plain', space('plain-fp'))
        dm.reset_caches()
    return out


# ---------------------------------------------------------------------------------- provider

def provider(tmp):
    """`provider(role)` без явного простору: шар вимкнено чи простір запиту не зафіксовано. Лічильники читання — обгортки зі
    `wraps` (виклик іде крізь), тож змін поведінки вони не вносять."""
    import deai_modules as dm
    import spaces
    out = {}
    modes = {
        'layer_off': {'DC_TASKS_FILE': os.path.join(tmp, 'prov', 'off', 'tasks.json')},
        'layer_on_request_not_fixed': {'DEAI_HOME': os.path.join(tmp, 'prov', 'on', 'deai')},
    }
    for mode, env in modes.items():
        rows = {}
        for role in dm.ROLES_CALLED + ('git-sync', 'zzz'):          # відомі ролі + роль, якої нема, + інша роль каталогу
            dm.reset_caches()
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(spaces, 'load_registry', wraps=spaces.load_registry) as reg, \
                    mock.patch.object(dm, 'space_modules', wraps=dm.space_modules) as sm, \
                    mock.patch.object(dm, 'catalog', wraps=dm.catalog) as cat:
                assert spaces.request_space_id() is None
                value = dm.provider(role)
            rows[role] = {'value': value if isinstance(value, (str, type(None))) else getattr(value, 'id', repr(type(value))),
                          'registry_reads': reg.call_count, 'space_json_reads': sm.call_count, 'catalog_reads': cat.call_count}
        out[mode] = {'layer_on': mode != 'layer_off', 'roles': rows}
    return out


# ---------------------------------------------------------------------------------- api

def _seeded(home):
    d = os.path.join(home, 'work', 'api', 'a-1')
    _write(os.path.join(d, 'iterations.json'), {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00'}], 'publish_url': None})
    return {'gitlab_ssh_key': '~/.ssh/example', 'design_work_root': os.path.join(home, 'work', 'api'),
            'tasks': {'a-1': {'dir': d, 'title': 'Alpha demo', 'jira': ''}}, 'current': 'a-1'}


def api(tmp):
    """Відповіді справжнього сервера: ЛІГА в реєстрі (шар увімкнено) і шар вимкнено. Лише ключі, які тримає контракт."""
    import serve
    import spaces
    out = {}
    for mode in ('liga_in_registry', 'layer_off'):
        home = os.path.join(tmp, 'api-' + mode, 'home')
        os.makedirs(home)
        path = os.path.join(home, 'tasks.json')
        _write(path, _seeded(home))
        env = {'HOME': home, 'DC_TASKS_FILE': path, 'DC_NO_OVERVIEW': '1'}
        if mode == 'liga_in_registry':
            env['DEAI_HOME'] = os.path.join(home, '.deai')
        vcs, net = Vcs(), NoNet()
        with mock.patch.dict(os.environ, env), mock.patch.object(serve, 'vcs_provider', vcs), \
                mock.patch.object(serve.urllib.request, 'urlopen', net):
            serve.deai_modules.reset_caches()
            if mode == 'liga_in_registry':
                spaces.load_registry()      # міграція старого файла в тимчасовий реєстр: простір `legacy` (ЛІГА)
            with Server() as srv:
                row = {'layer_on': spaces.layer_on()}
                st, body = srv.req('GET', '/api/spaces')
                row['spaces'] = {'status': st, 'keys': sorted(body), 'off': body.get('off'),
                                 'rows': [{'id': s['id'], 'integrations': s.get('integrations'), 'legacy': s.get('legacy'),
                                           'capabilities': s.get('capabilities')} for s in body.get('spaces', [])]}
                st, body = srv.req('GET', '/api/space')
                row['space_route'] = {'status': st, 'body_is_json': body is not None,
                                      'note': 'маршруту GET /api/space нема; простір задачі — поле `space` у GET /api/task'}
                st, body = srv.req('GET', '/api/task', task='a-1')
                space = body.get('space') if isinstance(body, dict) else None
                row['task'] = {'status': st, 'space': None if space is None else {
                                   'id': space.get('id'), 'integrations': space.get('integrations'),
                                   'legacy': space.get('legacy'), 'capabilities': space.get('capabilities')},
                               'has_publish_gate': isinstance(body, dict) and 'publish_gate' in body,
                               'publish_gate': body.get('publish_gate') if isinstance(body, dict) else None,
                               'preview_gate': body.get('preview_gate') if isinstance(body, dict) else None}
                row['vcs_provider_calls'] = vcs.calls
                row['urlopen_calls'] = net.calls
            out[mode] = row
        serve.deai_modules.reset_caches()
    return out


# ---------------------------------------------------------------------------------- isolation

class Calls:
    """Лічильники викликів модуля: підміна `deai_modules.call` (і виклику модуля ролі) — раз кличуть, значить закон не стримав."""

    def __init__(self):
        self.n = 0

    def __call__(self, *a, **kw):
        self.n += 1
        raise AssertionError('модуль викликано')


def isolation(tmp):
    import dashboard
    import deai_modules as dm
    import serve
    import tracker
    home = os.environ['HOME']
    iso = os.path.join(tmp, 'iso')
    os.makedirs(iso)
    live_tasks = os.path.join(iso, 'tasks.json')
    team_fake = os.path.join(iso, 'team.json')
    teams_fake = os.path.join(iso, 'teams.json')
    tracker_fake = os.path.join(iso, 'tracker.json')
    _write(team_fake, [{'project_id': 'demo-1', 'title': 'Alpha demo'}, 'сміття'])
    _write(tracker_fake, {'DEMO-1': {'name': 'In progress', 'cat': 'indeterminate'}})
    # три оточення закону: (а) шов/фейк, (б) лише DC_TASKS_FILE, (в) лише DC_NO_OVERVIEW
    envs = {'a_seam': {}, 'b_dc_tasks_file': {'DC_TASKS_FILE': live_tasks}, 'c_dc_no_overview': {'DC_NO_OVERVIEW': '1'}}

    def case(env, seam, body):
        """Один прогін: чисте оточення + `env` (+ шов `seam`), лічильник модуля; `body(calls)` → результат."""
        calls = Calls()
        net = NoNet()
        dm.reset_caches()
        with mock.patch.dict(os.environ, {**env, **seam}), \
                mock.patch.object(dm, 'call', calls), mock.patch.object(dashboard.deai_modules, 'call', calls), \
                mock.patch.object(serve.urllib.request, 'urlopen', net):
            res = _outcome(lambda: body(), home)
        return {'outcome': res, 'module_calls': calls.n, 'urlopen_calls': net.calls}

    out = {}
    # ---- dashboard: `_team_fetch` і `team_rows` (шов — DC_TEAM_FAKE)
    dash = {}
    for name, env in envs.items():
        seam = {'DC_TEAM_FAKE': team_fake} if name == 'a_seam' else {}
        row = {'team_fetch': case(env, seam, lambda: list(serve._team_fetch(None, 'legacy')))}
        serve._TEAM_CACHE.clear()
        row['team_rows'] = case(env, seam, lambda: list(serve.team_rows(refresh=True)))
        serve._TEAM_CACHE.clear()
        dash[name] = row
    out['dashboard'] = dash
    # ---- tracker: функція статусів `_tracker_fetch` (шов — DC_TRACKER_FAKE); `tracker.statuses` теж не має кликатись
    trk = {}
    for name, env in envs.items():
        seam = {'DC_TRACKER_FAKE': tracker_fake} if name == 'a_seam' else {}
        got = {}

        def run():
            r = serve._tracker_fetch(None, 'legacy', ['DEMO-1'])
            return None if r is None else [r[0], r[1]]
        with mock.patch.object(tracker, 'statuses', Calls()) as st_calls:
            got = case(env, seam, run)
            got['tracker_statuses_calls'] = st_calls.n
        trk[name] = got
    out['tracker'] = trk
    # ---- notify: `notify_call('mute_state')` і `notify_call('mute_set', …)` (шов — DC_TEAMS_FAKE)
    ntf = {}
    for name, env in envs.items():
        seam = {'DC_TEAMS_FAKE': teams_fake} if name == 'a_seam' else {}
        _write(teams_fake, {})
        row = {'mute_state': case(env, seam, lambda: serve.notify_call('mute_state', resolved=(None, 'legacy')))}
        row['mute_set'] = case(env, seam, lambda: serve.notify_call('mute_set', 'demo-channel', True, 'k:demo', resolved=(None, 'legacy')))
        if name == 'a_seam':        # шов пише лише у свій локальний файл: знімаємо, що в ньому після `mute_set`
            with open(teams_fake, encoding='utf-8') as fh:
                row['seam_file_after_set'] = sorted(json.load(fh))
        ntf[name] = row
    out['notify'] = ntf
    # ---- синк дашборда: `Handler._overview_sync` (шва нема — (а) — це оточення без жодної ізоляції і з конфігом установки)
    syn = {}
    for name, env in envs.items():
        launches = []
        calls = Calls()
        dm.reset_caches()
        with mock.patch.dict(os.environ, env), mock.patch.object(serve, 'supabase_config', return_value=(SB_URL, SB_KEY)), \
                mock.patch.object(serve, '_overview_target', return_value=('legacy-key', ['--legacy'])), \
                mock.patch.object(serve, '_overview_launch', lambda key, legacy, target: launches.append([key, legacy, target])), \
                mock.patch.object(serve.subprocess, 'Popen', calls), mock.patch.object(dm, 'call', calls):
            res = _outcome(lambda: serve.Handler._overview_sync(None), home)
        syn[name] = {'outcome': res, 'launched': launches, 'popen_calls': calls.n}
    # без конфігу установки навіть без ізоляції — тиша (пушити нікуди)
    launches = []
    with mock.patch.dict(os.environ, {}), mock.patch.object(serve, 'supabase_config', return_value=(None, None)), \
            mock.patch.object(serve, '_overview_target', return_value=('legacy-key', ['--legacy'])), \
            mock.patch.object(serve, '_overview_launch', lambda key, legacy, target: launches.append([key, legacy, target])):
        res = _outcome(lambda: serve.Handler._overview_sync(None), home)
    syn['a_seam_no_install_config'] = {'outcome': res, 'launched': launches}
    out['sync'] = syn
    out['note'] = ('для `sync` шва нема: (а) — оточення без `DC_TASKS_FILE`/`DC_NO_OVERVIEW` з вигаданою парою конфігу установки '
                   '(`supabase_config` підмінено); у `dashboard`/`tracker`/`notify` шов — DC_TEAM_FAKE/DC_TRACKER_FAKE/DC_TEAMS_FAKE')
    return out


# ---------------------------------------------------------------------------------- install

def install(tmp):
    """`install_config.supabase_config()` і `jira_config()` під `DC_TASKS_FILE`: корінь фікстури × оточення × файли `pipeline-feedback`.
    Усе — вигадані значення; файли `jira-email|jira-token` лежать лише в ТИМЧАСОВОМУ HOME."""
    import install_config
    out = {}
    root_pair = {'supabase_url': SB_URL, 'supabase_key': SB_KEY, 'jira_base': JIRA_BASE}
    root_none = {'design_work_root': '~/work'}
    env_on = {'SUPABASE_URL': SB_ENV_URL, 'SUPABASE_KEY': SB_ENV_KEY, 'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN}
    n = 0
    for root_name, root in (('root_with_pair', root_pair), ('root_without_pair', root_none)):
        for env_name, env in (('env_set', env_on), ('env_unset', {})):
            for files_name, files in (('files_present', True), ('files_absent', False)):
                n += 1
                home = os.path.join(tmp, 'inst', 'c%d' % n, 'home')
                os.makedirs(home)
                tasks = os.path.join(home, 'tasks.json')
                _write(tasks, root)
                if files:
                    fb = os.path.join(home, '.claude', 'pipeline-feedback')
                    _write(os.path.join(fb, 'jira-email'), JIRA_FILE_EMAIL + '\n')
                    _write(os.path.join(fb, 'jira-token'), JIRA_FILE_TOKEN + '\n')
                with mock.patch.dict(os.environ, {'HOME': home, 'DC_TASKS_FILE': tasks, **env}):
                    out['%s/%s/%s' % (root_name, env_name, files_name)] = {
                        'supabase_config': list(install_config.supabase_config()),
                        'jira_config': list(install_config.jira_config())}
    return out


# ---------------------------------------------------------------------------------- build

def build(tmp):
    """`manifest.json` збірки: `serve.build_preview(…, build=…)` на тимчасовій задачі (дві опубліковані ітерації), без гейта."""
    import serve
    out = {'BUILD_KINDS': list(serve.BUILD_KINDS)}
    home = os.path.join(tmp, 'build', 'home')
    task_dir = os.path.join(home, 'work', 'b-1')
    os.makedirs(task_dir)
    for it in ('it1', 'it2'):
        _write(os.path.join(task_dir, 'iterations', it, 'index.html'),
               '<!DOCTYPE html><html><head><title>t</title></head><body><h1>Alpha</h1></body></html>')
    _write(os.path.join(task_dir, 'iterations.json'), {'iterations': [
        {'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'перша', 'published': True},
        {'id': 'it2', 'date': '02.01.2026 10:00', 'note': 'друга', 'published': True}]})
    tasks = os.path.join(home, 'tasks.json')
    _write(tasks, {'current': 'b-1', 'design_work_root': os.path.join(home, 'work'),
                   'tasks': {'b-1': {'dir': task_dir, 'title': 'Alpha demo', 'jira': ''}}})
    net = NoNet()
    env = {'HOME': home, 'DC_TASKS_FILE': tasks, 'DC_NO_OVERVIEW': '1', 'SUPABASE_URL': SB_URL, 'SUPABASE_KEY': SB_KEY}
    with mock.patch.dict(os.environ, env), mock.patch.object(serve.urllib.request, 'urlopen', net):
        tid, task = serve.task_for(serve.load_tasks(), None)
        its = [i for i in serve.load_meta(task).get('iterations', []) if i.get('published')]
        league, warn = serve.publish_comments(None, task, tid)         # рішення про коментарі для збірки ЛІГА (шар вимкнено)
        out['league_comments'] = {'warn': warn, 'is_dict': isinstance(league, dict),
                                  'module': league['module'].id if isinstance(league, dict) else None,
                                  'keys': sorted(league) if isinstance(league, dict) else None}
        cases = (('legacy_with_league_comments', league, 'legacy'), ('legacy_no_comments', False, 'legacy'),
                 ('module_no_comments', False, 'module'))
        for name, comments, kind in cases:
            pub = serve.build_preview(task, tid, its, comments=comments, gate_pw=None, build=kind)['dir']
            with open(os.path.join(pub, 'manifest.json'), encoding='utf-8') as fh:
                man = json.load(fh)
            out[name] = {'build_arg': kind, 'manifest_build': man.get('build'), 'build_is_last_key': list(man)[-1] == 'build',
                         'manifest_keys': sorted(man), 'has_comment_layer_dir': os.path.isdir(os.path.join(pub, 'comment-layer'))}
        # мітки нема (старі збірки): `publish_manifest` без `build=` ключа не пише
        pub = os.path.join(task_dir, 'publish')
        direct = serve.publish_manifest(task, tid, its, serve.published_pages(task, its), {}, pub)
        out['publish_manifest_without_mark'] = {'has_build_key': 'build' in direct}
        for bad in ('Legacy', '', None, 'implicit'):
            try:
                serve.build_preview(task, tid, its, comments=False, gate_pw=None, build=bad)
                out['bad_build_%r' % (bad,)] = {'raised': None}
            except Exception as e:  # noqa: BLE001
                out['bad_build_%r' % (bad,)] = {'raised': type(e).__name__}
        out['urlopen_calls'] = net.calls
    return out


# ---------------------------------------------------------------------------------- збирання

def make():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d2-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}):
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.15.0', 'source_commit': _source_commit(),
                             'generator': 'tests/make_before_4d2.py', 'volatile_stripped': []}}
            snap['caps'] = caps(tmp)
            snap['provider'] = provider(tmp)
            snap['api'] = api(tmp)
            snap['isolation'] = isolation(tmp)
            snap['install'] = install(tmp)
            snap['build'] = build(tmp)
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.15.0 = `6e68250`; після нього лише docs 4d-2). Зашито, щоб прогін на новому
    коді не видавав себе за «до»."""
    return '6e68250'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` цієї теки відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — лише коли
    у `ROOT` нема `.git` зовсім (заморожена копія з `git archive`: довіряємо рецепту з докстрінга).

    ⛔ Закрито за замовчуванням ВСЕРЕДИНІ git-теки: нема `git`, збій чи тайм-аут, зламаний `rev-parse`, чужий toplevel, нема
    коміту-джерела, ненульовий `git diff` (1 = різниця, 128 = збій), збій `ls-files` або будь-який новий файл у `app/`/`bin/`
    (`git diff` їх не бачить) — усе це «відрізняється». Лише чисте `0` + порожній список дозволяє перезапис."""
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
        print('⛔ make_before_4d2: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
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
