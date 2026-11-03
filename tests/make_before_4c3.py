#!/usr/bin/env python3
"""Генератор знімка поведінки тиші Teams на 0.13.0: `tests/fixtures/notify/before-4c3.json` (етап 4c-3, Task 1).

Знімок знято ДО змін коду (код = 0.13.0, коміт `0267024`; після нього лише docs 4c-3) і лишається в репо як еталон паритету:
тести наступних задач (`tests/test_notify.py`: ядро, маршрут, запити RPC, меню) читають JSON, а не переганяють цей
генератор. Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме знято (запуск на НОВОМУ коді дасть не «до», а «після»: еталон
не перезаписувати).

Що знято (усе — на заглушках, жодної мережі й жодних файлів поза тимчасовою текою):
  * `rpc_requests` — справжній `serve.teams_rpc` зі підміненими `serve.supabase_config` (→ вигадані адреса й ключ) і
    `urllib.request.urlopen`: метод, шлях URL (БЕЗ хоста), тіло JSON, заголовки (значення ключа → `<key>`), тайм-аут, наявність
    TLS-контексту; відповідь-заглушка і розібраний результат — для стану (`teams_mute_state`) і перемикання
    (`teams_mute_set`). Плюс відмови: ізоляція (`DC_TASKS_FILE` / `DC_NO_OVERVIEW`) → текст `OSError` і нуль викликів `urlopen`;
    Supabase не налаштовано; простір без інтеграцій → тип винятку; мережа впала;
  * `route` — справжній сервер у процесі (ефемерний порт) у двох просторах: `liga` (інтеграції ввімкнено) і `plain` (вимкнено).
    ЛІГА на шві `DC_TEAMS_FAKE` (тимчасовий JSON замість бази): GET `/api/teams-mute` — не замовчано / замовчано мною / колегою
    / замовчано ПАРЕНТСЬКИЙ канал при каналі `dc/t1/internal` / колізії префікса (`dc/t10`, `dc/t1x`) / застарілі
    рядки без `muted_by` / порожній підпис машини; POST `{muted: true|false}` (з дозволеним Origin, з підписом
    `k:0123456789ab`), чужий Origin (403), `muted: "yes"` (400); шлях БЕЗ шва (підмінені `supabase_config` і `urlopen`) —
    GET/POST і збій мережі; ізоляція (`DC_TASKS_FILE` / `DC_NO_OVERVIEW`) — GET/POST; простір без інтеграцій — GET/POST (409);
  * `menu` — пункти дропдауна публікації (`app/bar-model.js`, `barModel`) через `node` для станів «з інтеграціями» і «без» та
    різних станів тиші: список `id` пунктів і сам пункт `teamsnotify`.

Виключено з JSON усе мінливе: `muted_at` (час запису тиші; лишено тип), абсолютні шляхи (тека → `<tmp>`), значення ключа
(→ `<key>`). Прогін двічі дає той самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 tests/make_before_4c3.py [--out ШЛЯХ]   (типово — `tests/fixtures/notify/before-4c3.json`)

⚠️ ГЕНЕРАТОР РОБИТЬ ЗНІМОК v0.13.0 (код — коміт 0267024) і мусить запускатись проти ЗАМОРОЖЕНОЇ копії старого коду, а не проти
робочої теки (з Task 2–5 `app/`/`bin/` змінюються — і знімок з міткою `source_commit: 0267024` містив би дані «після»). Як:
    git archive 0267024 | tar -x -C <тека>             # заморожена копія коду v0.13.0
    cp tests/make_before_4c3.py <тека>/tests/          # лише сам генератор (він бере ROOT від свого розташування)
    python3 -B <тека>/tests/make_before_4c3.py --out tests/fixtures/notify/before-4c3.json
Прогін на новому коді — лише як документація: запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від
0267024, генератор ВІДМОВЛЯЄ (код виходу 2); копія з `git archive` не git-теку — там довіряємо рецепту.

⛔ Ізоляція: власні тимчасові `HOME` і (для просторів) `DEAI_HOME`, чисте оточення (`DC_TEAMS_FAKE`/`SUPABASE_*` тощо прибрані й
виставляються лише на час випадку), `urlopen` — завжди заглушка (живий канал Teams і Supabase ЛІГИ недосяжні), справжній
`~/.deai` стереже `spaces_guard`.
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
from urllib.parse import urlsplit

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'notify', 'before-4c3.json')
URL = 'https://demo.supabase.example'
KEY = 'pk-test-1'
#: Підпис «цієї машини» у знімку (підміна `serve.mute_signature`); колега — інший.
MINE = 'k:0123456789ab'
COLLEAGUE = 'k:ffffffffffff'
EMAIL = 'alpha@example.com'
#: Змінні оточення, що ізолюють прогін або задають конфіг, — у знімку їх нема (чисте оточення).
CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
         'SUPABASE_SERVICE_KEY', 'DEAI_EXTRA_MODULES', 'DEAI_HOME', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DC_IDENTITY_NAME',
         'DC_IDENTITY_EMAIL')
#: Відповіді-заглушки RPC: стан — рядки тиші, перемикання — булеве.
STATE_ROWS = [{'project_id': 'dc/t1', 'muted_at': '2026-11-01T10:00:00', 'muted_by': COLLEAGUE}]


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))


def scrub(text, tmp):
    """Текст без абсолютних шляхів (тимчасова тека → `<tmp>`, у тому числі після `realpath`)."""
    for root in {tmp, os.path.realpath(tmp)}:
        text = text.replace(root, '<tmp>')
    return text


def stamp_type(obj):
    """Копія, де `muted_at` (час запису тиші, мінливий) замінено на імʼя типу; решта — як є (на будь-якій глибині)."""
    if isinstance(obj, dict):
        return {k: (type(v).__name__ if k == 'muted_at' else stamp_type(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [stamp_type(v) for v in obj]
    return obj


class _Resp:
    """Відповідь-заглушка `urlopen`: контекстний менеджер, що читається `json.loads`."""

    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *limit):
        return self._body


class Recorder:
    """Підміна `urllib.request.urlopen`: пише кожен виклик (метод, шлях без хоста, тіло, заголовки з ключем → `<key>`,
    тайм-аут, чи є TLS-контекст) і віддає `body` (чи кидає `exc`). Без мережі за будь-яких умов."""

    def __init__(self, body=b'[]', exc=None):
        self.calls, self.body, self.exc = [], body, exc

    def __call__(self, req, timeout=None, context=None, **kw):
        parts = urlsplit(req.full_url)
        headers = {k.lower(): str(v).replace(KEY, '<key>') for k, v in req.header_items()}
        self.calls.append({
            'method': req.get_method(), 'host_is_demo': parts.scheme + '://' + parts.netloc == URL, 'path': parts.path,
            'query': parts.query, 'body': json.loads(req.data.decode('utf-8')) if req.data else None,
            'headers': headers, 'timeout': timeout, 'ssl_context': context is not None,
        })
        if self.exc:
            raise self.exc
        return _Resp(self.body)


# ---------------------------------------------------------------------------------- запити RPC (teams_rpc)

def rpc_requests(tmp):
    import serve
    import spaces
    out = {}
    cfg = mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY))
    state_args = ('teams_mute_state', {})
    set_args = ('teams_mute_set', {'p_project': 'dc/t1', 'p_muted': True, 'p_by': MINE})

    # (1) стан і перемикання: справжній запит до «бази» (URL, метод, тіло, заголовки, тайм-аут) і розбір відповіді
    for key, args, stub in (('state', state_args, STATE_ROWS), ('set', set_args, True)):
        rec = Recorder(json.dumps(stub).encode('utf-8'))
        with cfg, mock.patch.object(serve.urllib.request, 'urlopen', rec):
            result = serve.teams_rpc(*args)
        out[key] = {'args': list(args), 'calls': rec.calls, 'stub_response': stub, 'result': result}
    # зворотне перемикання: те саме тіло з `p_muted: false`
    rec = Recorder(json.dumps(False).encode('utf-8'))
    with cfg, mock.patch.object(serve.urllib.request, 'urlopen', rec):
        result = serve.teams_rpc('teams_mute_set', {'p_project': 'dc/t1', 'p_muted': False, 'p_by': MINE})
    out['unset'] = {'calls': rec.calls, 'result': result}

    # (2) ізоляція: `DC_TASKS_FILE` / `DC_NO_OVERVIEW` → `OSError` ДО мережі, жодного `urlopen`
    for key, env in (('isolated_tasks_file', {'DC_TASKS_FILE': os.path.join(tmp, 'x-tasks.json')}),
                     ('isolated_no_overview', {'DC_NO_OVERVIEW': '1'})):
        rec = Recorder(json.dumps(STATE_ROWS).encode('utf-8'))
        with cfg, mock.patch.dict(os.environ, env), mock.patch.object(serve.urllib.request, 'urlopen', rec):
            out[key] = {**_raises(lambda: serve.teams_rpc(*state_args), tmp), 'urlopen_calls': len(rec.calls)}

    # (3) Supabase не налаштовано (`supabase_config` → `(None, None)`)
    rec = Recorder()
    with mock.patch.object(serve, 'supabase_config', return_value=(None, None)), \
            mock.patch.object(serve.urllib.request, 'urlopen', rec):
        out['no_supabase'] = {**_raises(lambda: serve.teams_rpc(*state_args), tmp), 'urlopen_calls': len(rec.calls)}

    # (4) мережа впала: `OSError` летить викликачу
    rec = Recorder(exc=OSError('мережі нема'))
    with cfg, mock.patch.object(serve.urllib.request, 'urlopen', rec):
        out['network_error'] = {**_raises(lambda: serve.teams_rpc(*state_args), tmp), 'urlopen_calls': len(rec.calls)}

    # (5) простір без інтеграцій: `IntegrationsOff` (`OSError`) ДО будь-якої мережі
    rec = Recorder(json.dumps(STATE_ROWS).encode('utf-8'))
    with cfg, spaces.request_space(''), mock.patch.object(serve.urllib.request, 'urlopen', rec):
        out['integrations_off'] = {**_raises(lambda: serve.teams_rpc(*state_args), tmp), 'urlopen_calls': len(rec.calls)}
    return out


def _raises(fn, tmp):
    """`{raised: <тип>, is_oserror, message}` — відмова, яку викликач мусить ловити як `OSError`."""
    try:
        res = fn()
    except Exception as e:  # noqa: BLE001 — знімаємо тип і текст відмови, а не ловимо її
        return {'raised': type(e).__name__, 'is_oserror': isinstance(e, OSError), 'message': scrub(str(e), tmp)}
    return {'raised': None, 'result': res}


# ---------------------------------------------------------------------------------- простори й сервер

def setup_spaces(tmp):
    """Два простори в тимчасовому `DEAI_HOME`: `liga` (інтеграції ввімкнено; задачі `t1` — канал `dc/t1`, `t2` — підканал
    `dc/t1/internal`) і `plain` (вимкнено; задача `p1`). Ідентифікатори задач різні: заголовок `X-Canvas-Task` фіксує простір."""
    import spaces
    ids = {}
    for name, integ, tasks_def in (
            ('Liga', True, (('t1', None), ('t2', 'dc/t1/internal'))),
            ('Plain', False, (('p1', None),))):
        path = os.path.join(os.environ['HOME'], 'work', name.lower())      # простір мусить лежати під домівкою
        sid = spaces.create_space(name, 'space-1', path)
        if integ:
            reg_file = spaces.registry_path()
            with open(reg_file, encoding='utf-8') as f:
                reg = json.load(f)
            for sp in reg['spaces']:
                if sp['id'] == sid:
                    sp['integrations'] = True
            _write(reg_file, reg)
        tasks = {}
        for tid, channel in tasks_def:
            d = os.path.join(path, tid)
            _write(os.path.join(d, 'iterations.json'), {
                'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00', 'published': False}], 'publish_url': None})
            task = {'title': 'Demo ' + tid, 'dir': d, 'profile': 'tool', 'opened': '2026-11-01T10:00:00Z'}
            if channel:
                task['comment_project'] = channel
            tasks[tid] = task
        _write(os.path.join(path, 'tasks.json'),
               {'design_work_root': path, 'current': tasks_def[0][0], 'tasks': tasks})
        ids[name.lower()] = sid
    return ids


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

    def req(self, method, path, task, payload=None, origin='local'):
        """`(status, тіло)`; `origin`: `'local'` — Origin самого сервера, `None` — без заголовка, інакше — як є."""
        headers = {'X-Canvas-Task': task}
        if origin == 'local':
            origin = 'http://127.0.0.1:%d' % self.port
        if origin:
            headers['Origin'] = origin
        body = None
        if payload is not None:
            body = json.dumps(payload).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers)
            r = conn.getresponse()
            return r.status, json.loads(r.read().decode('utf-8'))
        finally:
            conn.close()


# ---------------------------------------------------------------------------------- маршрут /api/teams-mute

def route(tmp):
    import serve
    out = {}
    fake = os.path.join(tmp, 'teams-fake.json')
    row = lambda by: {'muted_at': '2026-11-01T10:00:00', 'muted_by': by}  # noqa: E731
    sig = mock.patch.object(serve, 'mute_signature', lambda: MINE)

    def get(srv, task, tmp_=tmp):
        st, body = srv.req('GET', '/api/teams-mute', task)
        return {'status': st, 'body': stamp_type(body)}

    def post(srv, task, payload, origin='local'):
        st, body = srv.req('POST', '/api/teams-mute', task, payload, origin)
        return {'status': st, 'body': stamp_type(body)}

    def db_now():
        try:
            with open(fake, encoding='utf-8') as f:
                return stamp_type(json.load(f))
        except (OSError, ValueError):
            return None

    out['signature_real'] = _real_signature()      # ДО підміни `mute_signature`: справжня функція на вигаданій пошті
    with Server() as srv, sig:
        # ---- ЛІГА на шві DC_TEAMS_FAKE: стан ----
        with mock.patch.dict(os.environ, {'DC_TEAMS_FAKE': fake}):
            gets = {}
            for key, db, task in (
                    ('not_muted', {}, 't1'),
                    ('muted_by_me', {'dc/t1': row(MINE)}, 't1'),
                    ('muted_by_colleague', {'dc/t1': row(COLLEAGUE)}, 't1'),
                    ('parent_muted_subchannel', {'dc/t1': row(COLLEAGUE)}, 't2'),
                    ('other_channel_muted', {'dc/other': row(COLLEAGUE)}, 't1'),
                    # колізії префікса: `dc/t10` і `dc/t1x` — НЕ батьки `dc/t1` (правило `pid + '/'`, а не голий префікс)
                    ('prefix_collision_t10', {'dc/t10': row(COLLEAGUE)}, 't1'),
                    ('prefix_collision_t1x', {'dc/t1x': row(COLLEAGUE)}, 't1'),
                    # застарілі рядки: без `muted_by` / з порожнім / `muted_at: None` — `mine` завжди False
                    ('legacy_no_muted_by', {'dc/t1': {'muted_at': None}}, 't1'),
                    ('legacy_empty_muted_by', {'dc/t1': {'muted_at': None, 'muted_by': ''}}, 't1'),
                    ('legacy_empty_muted_by_with_time', {'dc/t1': row('')}, 't1')):
                _write(fake, db)
                gets[key] = {'db': stamp_type(db), 'task': task, **get(srv, task)}
            # машина без git-особи: `mute_signature()` = '' і рядок із порожнім `muted_by` — НЕ «моє» (порожнє ≠ порожнє)
            _write(fake, {'dc/t1': row('')})
            with mock.patch.object(serve, 'mute_signature', lambda: ''):
                gets['empty_signature_empty_muted_by'] = {'db': stamp_type({'dc/t1': row('')}), 'task': 't1',
                                                          'signature': '', **get(srv, 't1')}
            out['fake_get'] = gets

            # ---- ЛІГА: перемикання (POST) із підписом; база після кожного кроку ----
            _write(fake, {})
            posts = {}
            posts['mute'] = {**post(srv, 't1', {'muted': True}), 'db_after': db_now()}
            posts['unmute'] = {**post(srv, 't1', {'muted': False}), 'db_after': db_now()}
            posts['mute_subchannel'] = {**post(srv, 't2', {'muted': True}), 'db_after': db_now()}
            _write(fake, {})
            # відмовлені запити базу не чіпають
            posts['bad_muted'] = {**post(srv, 't1', {'muted': 'yes'}), 'db_after': db_now()}
            posts['foreign_origin'] = {**post(srv, 't1', {'muted': True}, origin='https://evil.example'),
                                       'db_after': db_now()}
            posts['no_origin_header'] = {**post(srv, 't1', {'muted': True}, origin=None), 'db_after': db_now()}
            out['fake_post'] = posts

        # ---- ЛІГА без шва: справжній шлях RPC (підмінені `supabase_config` і `urlopen`) ----
        real = {}
        cfg = mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY))
        rec = Recorder(json.dumps(STATE_ROWS).encode('utf-8'))
        with cfg, mock.patch.object(serve.urllib.request, 'urlopen', rec):
            real['get'] = {'task': 't1', **get(srv, 't1'), 'rpc_calls': rec.calls}
        rec = Recorder(json.dumps(STATE_ROWS).encode('utf-8'))
        with cfg, mock.patch.object(serve.urllib.request, 'urlopen', rec):
            real['post_mute'] = {**post(srv, 't1', {'muted': True}), 'rpc_calls': rec.calls}
        for key, call in (('get_network_error', lambda: get(srv, 't1')),
                          ('post_network_error', lambda: post(srv, 't1', {'muted': True}))):
            rec = Recorder(exc=OSError('мережі нема'))
            with cfg, mock.patch.object(serve.urllib.request, 'urlopen', rec):
                real[key] = {**call(), 'rpc_calls': rec.calls}
        out['real_path'] = real

        # ---- ізоляція: підмінений конфіг не пускає в мережу (GET → «не знаю», POST → 502) ----
        iso = {}
        for key, env in (('tasks_file', {'DC_TASKS_FILE': os.path.join(tmp, 'x-tasks.json')}),
                         ('no_overview', {'DC_NO_OVERVIEW': '1'})):
            rec = Recorder(json.dumps(STATE_ROWS).encode('utf-8'))
            with cfg, mock.patch.dict(os.environ, env), mock.patch.object(serve.urllib.request, 'urlopen', rec):
                iso[key] = {'get': get(srv, 't1'), 'post': post(srv, 't1', {'muted': True}),
                            'urlopen_calls': len(rec.calls)}
        out['isolated'] = iso

        # ---- простір без інтеграцій: 409 на GET і POST, жодного звернення назовні ----
        off = {}
        with mock.patch.dict(os.environ, {'DC_TEAMS_FAKE': fake}):
            _write(fake, {'dc/p1': row(COLLEAGUE)})
            rec = Recorder(json.dumps(STATE_ROWS).encode('utf-8'))
            with cfg, mock.patch.object(serve.urllib.request, 'urlopen', rec):
                off['get'] = get(srv, 'p1')
                off['post_mute'] = post(srv, 'p1', {'muted': True})
                off['post_bad_muted'] = post(srv, 'p1', {'muted': 'yes'})
                off['post_foreign_origin'] = post(srv, 'p1', {'muted': True}, origin='https://evil.example')
                off['urlopen_calls'] = len(rec.calls)
            off['db_after'] = db_now()
        out['integrations_off'] = off
    return out


def _real_signature():
    """Справжній `mute_signature` на вигаданій пошті (без підміни): формат `k:<12 hex>`, детермінований."""
    import serve
    with mock.patch.dict(os.environ, {'DC_IDENTITY_NAME': 'Alpha', 'DC_IDENTITY_EMAIL': EMAIL}):
        return serve.mute_signature()


# ---------------------------------------------------------------------------------- меню (bar-model)

_NODE = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const { barModel } = await import(pathToFileURL(process.argv[1]).href);
const cases = JSON.parse(readFileSync(0, "utf8"));
const base = {
  mode: "layout", view: "grid", vp: "desktop", vpw: "", taskId: "T-1", iterLabel: "It.1", iterNote: "",
  hasIteration: true, flowRaw: true, pagesError: "", flowError: "",
  gl: "sync", published: true, pubStale: false, iterPub: true, pagePub: true, iterOnGl: true, tasksErr: "", right: null,
};
const out = {};
for (const [key, s] of Object.entries(cases)) {
  const pub = barModel({ ...base, ...s }).zone3.find((x) => x.id === "publish");
  out[key] = pub ? { items: pub.items.map((x) => x.id), teamsnotify: pub.items.find((x) => x.id === "teamsnotify") || null }
                 : { items: null, teamsnotify: null };
}
process.stdout.write(JSON.stringify(out));
"""


def menu():
    space = lambda publish, integ: {'id': 'p', 'name': 'P', 'color': 'space-2', 'integrations': integ,  # noqa: E731
                                    'capabilities': {'publish': publish, 'tokens': None}}
    teams = lambda **kw: {'channel': 'dc/t1', 'muted': False, **kw}  # noqa: E731
    liga = space('legacy', True)
    cases = {
        # ЛІГА (інтеграції ввімкнено): усі стани перемикача тиші
        'liga_on': {'space': liga, 'teams': teams()},
        'liga_loading': {'space': liga, 'teams': None},
        'liga_error': {'space': liga, 'teams': {'channel': 'dc/t1', 'error': 'x'}},
        'liga_muted_by_me': {'space': liga, 'teams': teams(muted=True, mine=True, muted_by=MINE)},
        'liga_muted_by_colleague': {'space': liga, 'teams': teams(muted=True, mine=False, muted_by=COLLEAGUE)},
        # простір без інтеграцій: пункта нема, хоч би дані й були
        'plain_no_teams_data': {'space': space('static-publish', False), 'teams': None},
        'plain_with_teams_data': {'space': space('static-publish', False), 'teams': teams()},
        # без постачальника публікації: кнопки «Опублікувати» (а з нею й пункта) нема
        'plain_no_publish': {'space': space(None, False), 'teams': teams()},
        # модуль публікації + інтеграції: пункт Teams є, пароля ЛІГА нема
        'module_with_integrations': {'space': space('static-publish', True), 'teams': teams()},
        # стара форма відповіді (без `capabilities`): рішення за `integrations`, рівно `=== false`
        'old_shape_false': {'space': {'id': 'p', 'integrations': False}, 'teams': teams()},
        'old_shape_true': {'space': {'id': 'p', 'integrations': True}, 'teams': teams()},
        'no_space': {'teams': teams()},
    }
    r = subprocess.run(['node', '--input-type=module', '-e', _NODE, os.path.join(ROOT, 'app', 'bar-model.js')],
                       input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError('node: ' + r.stderr[-500:])
    out = json.loads(r.stdout)
    return {'input': cases, 'result': out}


# ---------------------------------------------------------------------------------- збирання

def build():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4c3-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}):
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.13.0', 'source_commit': _source_commit(),
                             'generator': 'tests/make_before_4c3.py', 'volatile_stripped': ['muted_at']}}
            # Шар просторів вмикає власний тимчасовий `DEAI_HOME`; запити без `request_space` = ЛІГА (інтеграції ввімкнено).
            with mock.patch.dict(os.environ, {'DEAI_HOME': os.path.join(tmp, 'deai')}):
                setup_spaces(tmp)
                snap['rpc_requests'] = rpc_requests(tmp)
                snap['route'] = route(tmp)
            snap['menu'] = menu()
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.13.0 = `0267024`; після нього лише docs 4c-3). Зашито, щоб прогін на новому
    коді не видавав себе за «до»."""
    return '0267024'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` цієї теки відрізняються від `_source_commit()`. `None` — перевірити нема як (не git-теку:
    копія з `git archive`; git відсутній; коміту нема): тоді довіряємо рецепту з докстрінга. ⛔ Саме `show-toplevel == ROOT`:
    тека-копія всередині чужого git-репо інакше питала б ЧУЖИЙ репозиторій."""
    try:
        top = subprocess.run(['git', '-C', ROOT, 'rev-parse', '--show-toplevel'], capture_output=True, text=True, timeout=30)
        if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != os.path.realpath(ROOT):
            return None
        src = _source_commit()
        if subprocess.run(['git', '-C', ROOT, 'cat-file', '-e', src + '^{commit}'], capture_output=True, timeout=30).returncode != 0:
            return None
        diff = subprocess.run(['git', '-C', ROOT, 'diff', '--quiet', src, '--', 'app', 'bin'], capture_output=True, timeout=60)
        # Нові (неіндексовані) файли в app/ і bin/ — теж «код відрізняється»: `git diff` їх не бачить.
        untracked = subprocess.run(['git', '-C', ROOT, 'ls-files', '--others', '--exclude-standard', '--', 'app', 'bin'],
                                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    # ⛔ Закрито за замовчуванням: будь-який ненульовий код `git diff` (1 = є різниця, 128 = збій) і будь-який збій
    # `ls-files` — «відрізняється», а не «однакове». Лише чисте `0` + порожній список нових файлів дозволяє перезапис.
    if untracked.returncode != 0:
        return True
    return diff.returncode != 0 or bool(untracked.stdout.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    if os.path.abspath(args.out) == os.path.abspath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4c3: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
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
