#!/usr/bin/env python3
"""Генератор знімка поведінки простору ЛІГА на 0.16.0: `tests/fixtures/liga-migration/before-4d3a.json` (етап 4d-3a, Task 1).

Знімок знято ДО змін коду (код = 0.16.0, коміт `bf9bb5b`; після нього лише docs 4d-3a) і лишається в репо як еталон паритету
міграції ЛІГИ: після 0.17 ЛІГА має ту саму поведінку для людини, хоч `tracks` і модулі `jira-tracker`/`supabase-dashboard`/
`supabase-teams` стають ЯВНИМИ записами `space.json`. Тести наступних задач (`tests/test_liga_migrate.py`) читають JSON, а не
переганяють цей генератор. Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме знято (запуск на НОВОМУ коді дасть не «до», а
«після»: еталон не перезаписувати).

Що знято (усе — у тимчасових теках, без мережі й без справжніх репо, дзеркал, Supabase, Jira чи Teams). Простір ЛІГА — запис
реєстру тимчасового `DEAI_HOME` з `legacy: true` і `integrations: true`, тека простору — тимчасова, `space.json` у ній НЕМАЄ
(ЛІГА живе на неявному постачальнику й адаптері напрямків):
  * `caps` — `deai_modules.capabilities(ЛІГА)`;
  * `tracks` — `serve.space_tracks(ЛІГА)` (id, label, root, repo, ds; корені відносно HOME), дефолт, ознака адаптера, `track_root`
    для кожного id і для невідомих рядків (`'United'`, `'zzz'`, `None`), `track_repo` для кожного id;
  * `ctx` — ctx, який отримав би модуль від неявного постачальника (`_team_fetch`, `_tracker_fetch`, `notify_call` з підміненим
    `deai_modules.call`, що записує `(module, fn, ctx)`), ПОЗА ізоляцією (`DC_TASKS_FILE`/`DC_NO_OVERVIEW` не виставлені; старий
    файл задач — тимчасовий, через підміну `spaces.legacy_tasks_file`). Секрети → `"<secret:ДОВЖИНА>"`. Випадки: Jira з
    оточення (`JIRA_*`), Jira з файлів `pipeline-feedback` у тимчасовому HOME, обидва (оточення раніше), Supabase лише з
    оточення (корінь без пари), конфігу нема;
  * `check` — вердикти `check` трьох модулів на ctx з секції `ctx` (мережа — підміна шва `_open` модуля; без неї збирається
    запис запитів `[метод, адреса]`): ok / відмова ключа / мережа; окремо `legacy: True` проти `legacy` без прапорця для
    публічного ключа (різниця, яку 4d-3a Task 2 прибере налаштуванням `compat`); шлях ядра `deai_modules.check(ЛІГА, id)` —
    те, що викликає кнопка «Перевірити» на екрані «Підключення» (у ЛІГИ нема `space.json`/секретів, тож конфіг неявного
    постачальника туди НЕ доходить);
  * `api` — справжній сервер у процесі на ефемерному порту: `GET /api/spaces` (запис ЛІГИ, `capabilities`), `GET /api/modules?
    space=legacy`, `GET /api/task` (заголовок `X-Canvas-Task`) для двох задач: `track`, `tags`, `space`;
  * `connections` — `app/connections-model.js` (через `node`) на записах `GET /api/modules` і `capabilities` ЛІГИ: рядок
    «Зараз» кожної ролі, картка-фокус ролі, секції за `groupModules` і вигляд кожної картки (`cardView`). Окремо
    `hypothetical_explicit` — ТОЙ САМИЙ код 0.16.0 на просторі, де три модулі вже явно ввімкнені в `space.json` (стан, у який
    міграція переведе ЛІГУ): чи з'являється дубль картки.

Виключено з JSON усе мінливе: часові поля, абсолютні шляхи (тека → `~/…`/`<tmp>`), ідентичність машини. Прогін двічі дає той
самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 -B tests/make_before_4d3a.py [--out ШЛЯХ]   (типово — `tests/fixtures/liga-migration/before-4d3a.json`)

⚠️ ГЕНЕРАТОР РОБИТЬ ЗНІМОК v0.16.0 (код — коміт bf9bb5b) і мусить запускатись проти ЗАМОРОЖЕНОЇ копії старого коду, а не
проти робочої теки (з Task 2–6 `app/`/`bin/` змінюються — і знімок з міткою `source_commit: bf9bb5b` містив би дані «після»).
Як:
    git archive bf9bb5b | tar -x -C <тека>             # заморожена копія коду v0.16.0
    cp tests/make_before_4d3a.py <тека>/tests/         # лише сам генератор (він бере ROOT від свого розташування)
    python3 -B <тека>/tests/make_before_4d3a.py --out tests/fixtures/liga-migration/before-4d3a.json
Прогін на новому коді — лише як документація: запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від
bf9bb5b, генератор ВІДМОВЛЯЄ (код виходу 2); копія з `git archive` — не git-тека, там довіряємо рецепту.

⛔ Ізоляція: власні тимчасові `HOME` і `DEAI_HOME` (звідси `~/.deai` і `~/.claude/pipeline-feedback/` — тимчасові), чисте
оточення (змінні конфігу прибрані на час прогону; потрібні виставляються ЛИШЕ тут, через `mock.patch.dict`, вигаданими значеннями),
жодної мережі (розтяжка сокетів + `urllib.request.urlopen` — заглушка-лічильник), `serve.vcs_provider` → `None` (жодного дзеркала
й git-синку); справжній `~/.deai` стереже `spaces_guard`.
"""
import argparse
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d3a.json')
#: Змінні оточення, що ізолюють прогін або задають конфіг, — у знімку їх нема (чисте оточення).
CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'DC_TRACKER_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
         'SUPABASE_SERVICE_KEY', 'DEAI_EXTRA_MODULES', 'DEAI_HOME', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DC_IDENTITY_NAME',
         'DC_IDENTITY_EMAIL', 'DC_REGISTRY_DIR', 'DC_MIRRORS_DIR', 'DC_REGISTRY_TTL_H', 'DC_PAGES_LOCK_TIMEOUT', 'PORT',
         'DEAI_CONFIRM_MSG', 'DEAI_CONFIRM_TITLE', 'DEAI_TRUST_CONFIRM', 'DEAI_OWN_CANARY', 'GIT_DIR', 'GIT_WORK_TREE',
         'GIT_INDEX_FILE')

# Вигадані значення (репо приватне й знеособлене: жодних справжніх хостів, ключів, імен).
SB_URL = 'https://sb.example.com'
SB_KEY = 'sb_test_key_alpha'
SB_ENV_URL = 'https://sb-env.example.com'
SB_ENV_KEY = 'sb_env_key_alpha'
JIRA_BASE = 'https://jira.example.com'
JIRA_ENV_EMAIL, JIRA_ENV_TOKEN = 'alpha@example.com', 'jira_env_token_alpha'
JIRA_FILE_EMAIL, JIRA_FILE_TOKEN = 'file@example.com', 'jira_file_token_alpha'
REPO_UNITED = 'git@example.com:studio/web.git'
REPO_SEO = 'ssh://git@example.com/o/r.git'
SPACE_ID = 'legacy'


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


def scrub(obj, home):
    """Рекурсивно `rel` для всіх рядків (ключі теж): у знімку не лишається жодного абсолютного шляху тимчасових тек."""
    if isinstance(obj, str):
        return rel(obj, home)
    if isinstance(obj, dict):
        return {rel(k, home) if isinstance(k, str) else k: scrub(v, home) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub(v, home) for v in obj]
    return obj


def _outcome(fn, home):
    """`{result: …}` або `{raised: <клас>, code?, message: <текст без шляхів>}` — відмову знімаємо, а не ловимо мовчки."""
    try:
        return {'result': fn()}
    except Exception as e:  # noqa: BLE001
        out = {'raised': type(e).__name__, 'message': rel(str(e), home)}
        if getattr(e, 'code', None):
            out['code'] = e.code
        return out


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


# ---------------------------------------------------------------------------------- стенд

class Rig:
    """Стенд ЛІГИ у тимчасовій теці: `home` (= HOME), `deai` (= DEAI_HOME з реєстром), тека простору БЕЗ `space.json`, старий
    `tasks.json` з вигаданим конфігом. `activate()` — контекст: HOME/DEAI_HOME + підміна `spaces.legacy_tasks_file` на тимчасовий
    файл (так `DC_TASKS_FILE` лишається невиставленим: ізоляції нема, а справжнього `tasks.json` машини ми не читаємо)."""

    def __init__(self, tmp, name):
        self.home = os.path.join(tmp, name, 'home')
        self.deai = os.path.join(self.home, '.deai')
        self.space_dir = os.path.join(tmp, name, 'liga-space')
        self.tasks_path = os.path.join(self.home, 'legacy', 'tasks.json')
        os.makedirs(self.home)
        os.makedirs(self.space_dir)
        self.cfg = None

    def registry(self, space_json=None):
        _write(os.path.join(self.deai, 'spaces.json'),
               {'version': 1, 'current': SPACE_ID, 'spaces': [{'id': SPACE_ID, 'path': self.space_dir, 'legacy': True,
                                                               'integrations': True}]})
        if space_json is not None:
            _write(os.path.join(self.space_dir, 'space.json'), space_json)
        return {'id': SPACE_ID, 'path': self.space_dir, 'legacy': True, 'integrations': True}

    def config(self, with_supabase=True, with_jira=True, extra=None):
        w = os.path.join(self.home, 'work')
        d = os.path.join(w, 'a-1')
        cfg = {'gitlab_ssh_key': '~/.ssh/example',
               'design_work_root': os.path.join(w, 'shared'),
               'design_work_roots': {'united': os.path.join(w, 'united'), 'custom-x': os.path.join(w, 'custom')},
               'profile_repos': {'united': REPO_UNITED, 'seo': REPO_SEO},
               'tasks': {'a-1': {'dir': d, 'title': 'Alpha demo', 'jira': 'DEMO-1', 'track': 'seo'},
                         'a-2': {'dir': os.path.join(w, 'a-2'), 'title': 'Beta demo', 'jira': '', 'profile': 'united'}},
               'current': 'a-1'}
        if with_supabase:
            cfg.update(supabase_url=SB_URL, supabase_key=SB_KEY)
        if with_jira:
            cfg['jira_base'] = JIRA_BASE
        cfg.update(extra or {})
        self.cfg = cfg
        _write(self.tasks_path, cfg)
        for tid in ('a-1', 'a-2'):
            _write(os.path.join(w, tid, 'iterations.json'), {'iterations': [], 'publish_url': None})
        return cfg

    def feedback_files(self):
        fb = os.path.join(self.home, '.claude', 'pipeline-feedback')
        _write(os.path.join(fb, 'jira-email'), JIRA_FILE_EMAIL + '\n')
        _write(os.path.join(fb, 'jira-token'), JIRA_FILE_TOKEN + '\n')

    def activate(self, env=None):
        import spaces
        stack = _Stack()
        stack.add(mock.patch.dict(os.environ, {'HOME': self.home, 'DEAI_HOME': self.deai, **(env or {})}))
        stack.add(mock.patch.object(spaces, 'legacy_tasks_file', lambda: self.tasks_path))
        return stack


class _Stack:
    def __init__(self):
        self._ps = []

    def add(self, p):
        self._ps.append(p)

    def __enter__(self):
        for p in self._ps:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self._ps):
            p.stop()


# ---------------------------------------------------------------------------------- caps

def caps(tmp):
    import deai_modules as dm
    rig = Rig(tmp, 'caps')
    rig.config()
    liga = rig.registry()
    with rig.activate():
        dm.reset_caches()
        out = {'space': scrub(liga, rig.home), 'caps': dm.capabilities(liga)}
        dm.reset_caches()
    return out


# ---------------------------------------------------------------------------------- tracks

def tracks(tmp):
    """`space_tracks`, дефолт, адаптер, `track_root`/`track_repo`. Підпис `serve.space_tracks(sp) -> (tracks, default_id)` — як у плані."""
    import serve
    rig = Rig(tmp, 'tracks')
    cfg = rig.config()
    liga = rig.registry()
    with rig.activate():
        items, default = serve.space_tracks(liga)
        view = serve._TrackView(liga)
        ids = [t['id'] for t in items]
        out = {'tracks': scrub(items, rig.home), 'default_track': default, 'adapter': bool(view.adapter),
               'ids': ids,
               'track_root': {}, 'track_root_unknown': {}, 'track_repo': {}}
        for i in ids:
            out['track_root'][i] = rel(serve.track_root(liga, cfg, i), rig.home)
            out['track_repo'][i] = serve.track_repo(liga, i)
        for raw in ('United', 'zzz', '', None, 7):
            out['track_root_unknown'][repr(raw)] = rel(serve.track_root(liga, cfg, raw), rig.home)
        out['track_repo']['zzz'] = serve.track_repo(liga, 'zzz')
        out['track_repo']['None'] = serve.track_repo(liga, None)
        out['legacy_repos'] = serve.profile_repos()
    return out


# ---------------------------------------------------------------------------------- ctx

class Recorder:
    """Підміна `deai_modules.call`: записує `(module, fn, ctx)` і віддає порожню, але валідну відповідь (мережі нема)."""
    EMPTY = {'rows': [], 'statuses': {}, 'mute_state': []}

    def __init__(self):
        self.calls = []

    def __call__(self, module, fn, ctx, *args, timeout=None):
        self.calls.append((module.id, fn, ctx, timeout))
        return self.EMPTY.get(fn, [])


def san_ctx(ctx):
    """ctx модуля без секретів і без не-JSON: секрети → `"<secret:ДОВЖИНА>"`, класи/функції → імʼя типу."""
    out = {}
    for k, v in ctx.items():
        if k == 'secrets':
            out[k] = {sk: '<secret:%d>' % len(sv) if isinstance(sv, str) else repr(sv) for sk, sv in v.items()}
        elif isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v
        elif isinstance(v, dict):
            out[k] = san_ctx(v)
        elif isinstance(v, (list, tuple)):
            out[k] = list(v)
        else:
            out[k] = '<%s>' % (getattr(v, '__name__', None) or type(v).__name__)
    return out


def _ctx_case(rig, env):
    """Три потоки неявного постачальника ЛІГИ під підміненим `deai_modules.call`: `{role: {module, fn, timeout, ctx}|raised}`."""
    import deai_modules as dm
    import install_config
    import serve
    import spaces
    liga = rig.registry()
    rec = Recorder()
    out = {}
    with rig.activate(env), mock.patch.object(dm, 'call', rec), spaces.request_space(SPACE_ID):
        dm.reset_caches()
        provs = {role: dm.provider(role, liga) for role in ('dashboard', 'tracker', 'notify')}
        serve._TEAM_CACHE.clear()
        out['config'] = {'supabase_config': [None if v is None else ('<secret:%d>' % len(v) if i == 1 else v)
                                             for i, v in enumerate(install_config.supabase_config())],
                         'jira_config': [None if v is None else ('<secret:%d>' % len(v) if i == 2 else v)
                                         for i, v in enumerate(install_config.jira_config())]}
        flows = {'dashboard': lambda: serve._team_fetch(liga, provs['dashboard']),
                 'tracker': lambda: serve._tracker_fetch(liga, provs['tracker'], ['DEMO-1']),
                 'notify': lambda: serve.notify_call('mute_state', resolved=(liga, provs['notify']))}
        for role, flow in flows.items():
            before = len(rec.calls)
            res = _outcome(lambda: _jsonable(flow()), rig.home)
            new = rec.calls[before:]
            row = {'provider': type(provs[role]).__name__, 'flow_outcome': res,
                   'calls': [{'module': m, 'fn': fn, 'timeout': t, 'ctx': san_ctx(c)} for m, fn, c, t in new]}
            out[role] = row
        dm.reset_caches()
    return out


def _jsonable(v):
    return json.loads(json.dumps(v, default=lambda o: '<%s>' % type(o).__name__))


def ctx(tmp):
    out = {}
    # 1) Jira з оточення (файлів pipeline-feedback нема), Supabase і Jira-адреса — з кореня старого файла
    rig = Rig(tmp, 'ctx-env')
    rig.config()
    out['jira_from_env'] = _ctx_case(rig, {'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN})
    # 2) Jira з файлів pipeline-feedback ТИМЧАСОВОГО HOME (оточення порожнє)
    rig = Rig(tmp, 'ctx-files')
    rig.config()
    rig.feedback_files()
    out['jira_from_files'] = _ctx_case(rig, {})
    # 3) і оточення, і файли: оточення раніше
    rig = Rig(tmp, 'ctx-both')
    rig.config()
    rig.feedback_files()
    out['jira_env_beats_files'] = _ctx_case(rig, {'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN})
    # 4) корінь без пари Supabase: пара з оточення
    rig = Rig(tmp, 'ctx-sbenv')
    rig.config(with_supabase=False)
    out['supabase_from_env'] = _ctx_case(rig, {'SUPABASE_URL': SB_ENV_URL, 'SUPABASE_KEY': SB_ENV_KEY})
    # 5) конфігу нема ніде
    rig = Rig(tmp, 'ctx-none')
    rig.config(with_supabase=False, with_jira=False)
    out['unconfigured'] = _ctx_case(rig, {})
    return out


# ---------------------------------------------------------------------------------- check

class Resp:
    """Відповідь, що вміє `with`, `.status` і `.read(n)`."""

    def __init__(self, status, body):
        self.status = status
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self._body if n < 0 else self._body[:n]


def _run_check(mid, ctx_, scenario):
    """`deai_modules.call(module, 'check', ctx)` з підміненим швом `_open` модуля. `scenario` — `ok`/`denied`/`network`.
    Повертає `{outcome, requests: [[метод, адреса], …]}`; мережі справжньої нема (шов підмінено, сокети під розтяжкою)."""
    import deai_modules as dm
    dm.reset_caches()
    mod = dm.catalog()[mid]
    g = mod.fn('check').__globals__
    reqs = []
    ok_body = {'supabase-dashboard': [], 'supabase-teams': [], 'jira-tracker': {'accountId': 'x'}}[mid]

    def fake(req, timeout):
        reqs.append([req.get_method(), req.full_url])
        if scenario == 'network':
            raise urllib.error.URLError(OSError('мережі нема'))
        if scenario == 'denied':
            raise urllib.error.HTTPError(req.full_url, 401, 'denied', {}, __import__('io').BytesIO(b'{}'))
        return Resp(200, ok_body)
    with mock.patch.dict(g, {'_open': fake}):
        try:
            res = {'result': dm.call(mod, 'check', ctx_)}
        except Exception as e:  # noqa: BLE001
            res = {'raised': type(e).__name__, 'code': getattr(e, 'code', None), 'message': str(e)[:200]}
    return {'outcome': res, 'requests': reqs}


def _jwt_anon():
    import base64

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip('=')
    return '.'.join([b64({'alg': 'HS256'}), b64({'role': 'anon', 'iss': 'supabase-demo'}), 'c2ln'])


def check(tmp):
    import deai_modules as dm
    import dashboard
    import install_config
    import notify
    import spaces
    import tracker
    rig = Rig(tmp, 'check')
    rig.config()
    liga = rig.registry()
    out = {}
    with rig.activate({'JIRA_EMAIL': JIRA_ENV_EMAIL, 'JIRA_TOKEN': JIRA_ENV_TOKEN}), spaces.request_space(SPACE_ID):
        url, key = install_config.supabase_config()
        ctxs = {'supabase-dashboard': dashboard.legacy_ctx(url, key, space_id=SPACE_ID),
                'supabase-teams': notify.legacy_ctx(url, key, space_id=SPACE_ID),
                'jira-tracker': tracker.legacy_ctx(*install_config.jira_config(), space_id=SPACE_ID)}
        for mid, c in ctxs.items():
            out[mid] = {sc: _run_check(mid, c, sc) for sc in ('ok', 'denied', 'network')}
        # прапорець `legacy` у ctx: публічний ключ у ЛІГИ проходить, у ctx без прапорця — `public-key` (мережі до відмови нема)
        pub = {}
        for mid in ('supabase-dashboard', 'supabase-teams'):
            c = dict(ctxs[mid])
            c['secrets'] = {'key': 'sb_publishable_alpha'}
            c_no = {k: v for k, v in c.items() if k != 'legacy'}
            pub[mid] = {'legacy_true': _run_check(mid, c, 'ok'), 'legacy_absent': _run_check(mid, c_no, 'ok')}
            c['secrets'] = {'key': _jwt_anon()}
            c_no = {k: v for k, v in c.items() if k != 'legacy'}
            pub[mid]['jwt_anon_legacy_true'] = _run_check(mid, c, 'ok')
            pub[mid]['jwt_anon_legacy_absent'] = _run_check(mid, c_no, 'ok')
        out['public_key'] = pub
        # шлях ядра: кнопка «Перевірити» на «Підключення» — `deai_modules.check(ЛІГА, id)`; у ЛІГИ нема space.json/секретів
        core = {}
        for mid in ctxs:
            dm.reset_caches()
            mod = dm.catalog()[mid]
            g = mod.fn('check').__globals__
            reqs = []

            def fake(req, timeout, _reqs=reqs):
                _reqs.append([req.get_method(), req.full_url])
                return Resp(200, [] if mid != 'jira-tracker' else {})
            with mock.patch.dict(g, {'_open': fake}):
                core[mid] = {'outcome': _outcome(lambda: dm.check(liga, mid), rig.home), 'requests': reqs}
            dm.forget_check(SPACE_ID, mid)
        out['core_check'] = core
        dm.reset_caches()
    return scrub(out, rig.home)


# ---------------------------------------------------------------------------------- api

def _api_rig(tmp, name, space_json=None):
    rig = Rig(tmp, name)
    rig.config()
    rig.registry(space_json)
    return rig


def _api_pass(rig):
    """Відповіді справжнього сервера для ЛІГИ в реєстрі тимчасового `DEAI_HOME`. Лише ключі, які тримає контракт."""
    import serve
    import spaces
    vcs, net = Vcs(), NoNet()
    env = {'HOME': rig.home, 'DEAI_HOME': rig.deai, 'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1'}
    out = {}
    with mock.patch.dict(os.environ, env), mock.patch.object(serve, 'vcs_provider', vcs), \
            mock.patch.object(serve.urllib.request, 'urlopen', net):
        serve.deai_modules.reset_caches()
        with Server() as srv:
            out['layer_on'] = spaces.layer_on()
            st, body = srv.req('GET', '/api/spaces')
            out['spaces'] = {'status': st, 'keys': sorted(body), 'off': body.get('off'), 'current': body.get('current'),
                             'rows': [{'id': s['id'], 'keys': sorted(s), 'integrations': s.get('integrations'),
                                       'legacy': s.get('legacy'), 'capabilities': s.get('capabilities'),
                                       'tracks': s.get('tracks'), 'default_track': s.get('default_track')}
                                      for s in body.get('spaces', [])]}
            st, mods = srv.req('GET', '/api/modules?space=' + SPACE_ID)
            out['modules'] = {'status': st, 'keys': sorted(mods), 'list': mods.get('modules')}
            tasks = {}
            for tid in ('a-1', 'a-2'):
                st, body = srv.req('GET', '/api/task', task=tid)
                sp = body.get('space') if isinstance(body, dict) else None
                tasks[tid] = {'status': st, 'track': body.get('track'), 'profile': body.get('profile'), 'tags': body.get('tags'),
                              'jira': body.get('jira'), 'comment_channel': body.get('comment_channel'),
                              'space': None if sp is None else {'keys': sorted(sp), 'id': sp.get('id'),
                                                                'integrations': sp.get('integrations'),
                                                                'legacy': sp.get('legacy'),
                                                                'capabilities': sp.get('capabilities')}}
            out['tasks'] = tasks
            out['vcs_provider_calls'] = vcs.calls
            out['urlopen_calls'] = net.calls
        serve.deai_modules.reset_caches()
    return out


def api(tmp):
    rig = _api_rig(tmp, 'api')
    return scrub(_api_pass(rig), rig.home)


# ---------------------------------------------------------------------------------- connections

NODE_PROG = r"""
import { pathToFileURL } from 'node:url';
const inp = JSON.parse(await new Promise((res) => { let s = ''; process.stdin.on('data', (d) => { s += d; }); process.stdin.on('end', () => res(s)); }));
const m = await import(pathToFileURL(inp.model).href);
const list = inp.modules, caps = inp.capabilities;
const out = { role_order: m.ROLE_ORDER, roles: {}, sections: [], missing: [], cards: {} };
for (const role of m.ROLE_ORDER) {
  const line = m.providerLine(role, caps, list);
  out.roles[role] = { provider: line === null ? null : { kind: line.kind, id: line.id ?? null, entry: line.entry ? line.entry.id : null, noneKey: line.noneKey ?? null },
                      focus_card: m.roleCardId(role, caps, list) };
}
const g = m.groupModules(list);
out.sections = g.sections.map((s) => ({ role: s.role, modules: s.modules.map((e) => e.id) }));
out.missing = g.missing.map((e) => e.id);
for (const e of list) out.cards[e.id] = { view: m.cardView(e), roles: e.roles, enabled: e.enabled, implicit: e.implicit, status: e.status };
// скільки карток несе кожна роль серед усіх секцій і чи є модуль у двох секціях (дубль)
const seen = {};
for (const s of out.sections) for (const id of s.modules) seen[id] = (seen[id] || 0) + 1;
out.duplicate_cards = Object.keys(seen).filter((id) => seen[id] > 1).sort();
console.log(JSON.stringify(out));
"""


def _node(modules, capabilities):
    payload = json.dumps({'model': os.path.join(ROOT, 'app', 'connections-model.js'), 'modules': modules,
                          'capabilities': capabilities})
    r = subprocess.run(['node', '--input-type=module', '-e', NODE_PROG], input=payload, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError('node: ' + r.stderr[-500:])
    return json.loads(r.stdout)


def _connections_from(api_out):
    row = next(s for s in api_out['spaces']['rows'] if s['id'] == SPACE_ID)
    return _node(api_out['modules']['list'], row['capabilities'])


def connections(tmp):
    """Екран «Підключення» для ЛІГИ: за відповідями справжнього сервера (`api`) і за гіпотетичним `space.json` з трьома явними
    модулями (той самий код 0.16.0). Мережі й тут нема (сервер під розтяжкою, `urlopen` — заглушка)."""
    rig = _api_rig(tmp, 'conn-now')
    now = _api_pass(rig)
    out = {'now': _connections_from(now)}
    explicit = {'modules': {
        'jira-tracker': {'enabled': True, 'roles': ['tracker'], 'settings': {'base': JIRA_BASE, 'email': JIRA_ENV_EMAIL}},
        'supabase-dashboard': {'enabled': True, 'roles': ['dashboard'], 'settings': {'url': SB_URL, 'table': 'overview_projects'}},
        'supabase-teams': {'enabled': True, 'roles': ['notify'], 'settings': {'url': SB_URL}}}}
    rig2 = _api_rig(tmp, 'conn-explicit', explicit)
    hyp = _api_pass(rig2)
    row = next(s for s in hyp['spaces']['rows'] if s['id'] == SPACE_ID)
    out['hypothetical_explicit'] = {
        'space_json': explicit,
        'capabilities': row['capabilities'],
        'modules_roles_enabled': {e['id']: {'enabled': e['enabled'], 'implicit': e['implicit'], 'roles': e['roles'],
                                            'status': e['status']}
                                  for e in hyp['modules']['list'] if e['id'] in explicit['modules']},
        'screen': _connections_from(hyp),
    }
    return scrub(out, rig.home)


# ---------------------------------------------------------------------------------- збирання

class SocketTripwire:
    """Розтяжка на рівні сокетів (модулі ходять власним `build_opener`, повз `urlopen`): `socket.getaddrinfo` і
    `socket.create_connection` на час усього прогону. Loopback проходить (справжній сервер у процесі), будь-який інший хост
    рахується й відмовляється (`OSError`)."""
    LOOPBACK = ('127.0.0.1', 'localhost', '::1')

    def __init__(self):
        import socket
        self.socket = socket
        self.count = 0
        self._gai, self._cc = socket.getaddrinfo, socket.create_connection

    def _host_ok(self, host):
        if isinstance(host, bytes):
            host = host.decode('ascii', 'replace')
        return host in self.LOOPBACK

    def getaddrinfo(self, host, *a, **kw):
        if not self._host_ok(host):
            self.count += 1
            raise OSError('мережі нема (розтяжка getaddrinfo)')
        return self._gai(host, *a, **kw)

    def create_connection(self, address, *a, **kw):
        if not self._host_ok(address[0]):
            self.count += 1
            raise OSError('мережі нема (розтяжка create_connection)')
        return self._cc(address, *a, **kw)

    def __enter__(self):
        self.socket.getaddrinfo, self.socket.create_connection = self.getaddrinfo, self.create_connection
        return self

    def __exit__(self, *exc):
        self.socket.getaddrinfo, self.socket.create_connection = self._gai, self._cc


def make():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d3a-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire:
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.16.0', 'source_commit': _source_commit(),
                             'generator': 'tests/make_before_4d3a.py', 'volatile_stripped': []}}
            snap['caps'] = caps(tmp)
            snap['tracks'] = tracks(tmp)
            snap['ctx'] = ctx(tmp)
            snap['check'] = check(tmp)
            snap['api'] = api(tmp)
            snap['connections'] = connections(tmp)
            snap['non_loopback_attempts'] = wire.count
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.16.0 = `bf9bb5b`; після нього лише docs 4d-3a). Зашито, щоб прогін на новому
    коді не видавав себе за «до»."""
    return 'bf9bb5b'


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
        # `--exclude-standard`: ігноровані файли (`__pycache__`, `*.pyc`) не мають рвати охорону; будь-який ІНШИЙ новий файл — рве
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
    if os.path.realpath(args.out) == os.path.realpath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4d3a: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
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
