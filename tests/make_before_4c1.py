#!/usr/bin/env python3
"""Генератор знімка поведінки командного дашборда на 0.11.0: `tests/fixtures/dashboard/before-4c1.json` (етап 4c-1, Task 1).

Знімок знято ДО змін коду (`HEAD` = 0.11.0 + спека/план) і лишається в репо як еталон паритету: тести Task 2–7
(`tests/test_dashboard.py`: `CardsParity`, `SyncParity`, `ReadParity`, `GateParity`) читають JSON, а не переганяють цей
генератор. Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме знято (запускати його на НОВОМУ коді можна, але знімок вже
не буде «до»: порівнювати з ним треба нову поведінку, а не перезаписувати еталон).

Що знято (усе — на заглушках, жодної мережі й жодних файлів поза тимчасовою текою):
  * `team_read` — шлях ЧИТАННЯ вкладки «Команда»: тіло `GET /api/tasks-overview` (`_team_fetch`/`team_snapshot` → `tasks_overview`)
    у п'яти випадках: шов `DC_TEAM_FAKE`; справжній запит (`supabase_config` + підмінений `urlopen`: URL, заголовки з ключем
    `<key>`, тайм-аут); помилка мережі; конфігу нема; простір без інтеграцій (`team: null`, жодного виклику `urlopen`);
  * `sync_push` — шлях ЗАПИСУ: `bin/overview_push.py cmd_sync()` на фікстурі `tasks.json` (реєстр, лічильники коментарів,
    статуси Jira, `upsert_project` — заглушки): список `(рядок, ignore)` у порядку викликів + вивід;
  * `upsert_http` / `supabase_choice` — справжня HTTP-форма `upsert_project` (URL, `Prefer`, тайм-аут, тіло) і вибір пари `_supabase()`;
  * `sync_gate` — гейт запуску синку `Handler._overview_sync`: чи стартував `Popen`, з яким `argv` і оточенням.

Виключено з JSON усе мінливе: `fetchedAt`, `rowsAt`, `changed`, `synced_at`, `updated_at`, `jira_synced_at`, абсолютні
шляхи (тека → `<tmp>`), значення ключа Supabase (→ `<key>`). Прогін двічі дає той самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 tests/make_before_4c1.py [--out ШЛЯХ]   (типово — `tests/fixtures/dashboard/before-4c1.json`)

⚠️ ГЕНЕРАТОР РОБИТЬ ЗНІМОК v0.11.0 (коміт 6e0a0a5) і мусить запускатись проти ЗАМОРОЖЕНОЇ копії старого коду, а не проти
робочої теки (з 4c-1 `app/`/`bin/` змінюються — і знімок перестав би бути «до»). Як:
    git archive 6e0a0a5 | tar -x -C <тека>             # заморожена копія коду v0.11.0
    cp tests/make_before_4c1.py <тека>/tests/          # лише сам генератор (він бере ROOT від свого розташування)
    python3 -B <тека>/tests/make_before_4c1.py --out tests/fixtures/dashboard/before-4c1.json
Прогін на новому коді — лише як документація (див. вище): еталон перезаписувати не можна.

⛔ Ізоляція: власні тимчасові `HOME`/`DEAI_HOME` (лог синку `~/.claude/pipeline-feedback/overview-sync.log` — у тимчасовому
`HOME`), `DC_TASKS_FILE`/`SUPABASE_*` у чистому оточенні, справжній `~/.deai` стереже `spaces_guard`. Реєстр GitLab, Jira й
`Popen` — заглушки; `_temp_roots` реєстру підмінено, щоб тимчасові теки генератора не вважались «фікстурами тесту», а один
навмисний запис — вважався (`_drop_fixtures` проходить НАСПРАВДІ).
"""
import argparse
import contextlib
import http.client
import io
import json
import os
import sys
import tempfile
import threading
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

URL = 'https://demo.supabase.example'
KEY = 'pk-test-1'
OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'dashboard', 'before-4c1.json')
#: Поля, що змінюються між прогонами: з відповіді/рядків їх вирізано (їхню ПРИСУТНІСТЬ лишено в `volatile`).
VOLATILE = ('fetchedAt', 'rowsAt', 'changed', 'synced_at', 'updated_at', 'jira_synced_at')
#: Вигаданий «тимчасовий корінь» для `registry._temp_roots`: запис, що лежить під ним, — фікстура тесту (відкидається).
FAKE_TMP = '/deai-fixture-tmp'
#: Змінні оточення, що ізолюють прогін або задають конфіг, — у знімку їх нема (чисте оточення).
CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
         'SUPABASE_SERVICE_KEY', 'DEAI_EXTRA_MODULES', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DC_IDENTITY_NAME',
         'DC_IDENTITY_EMAIL')


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False))


def strip(obj):
    """Копія без мінливих полів (на будь-якій глибині)."""
    if isinstance(obj, dict):
        return {k: strip(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [strip(v) for v in obj]
    return obj


def scrub(text, tmp):
    """Текст без абсолютних шляхів (тимчасова тека → `<tmp>`, у тому числі після `realpath`)."""
    for root in {tmp, os.path.realpath(tmp)}:
        text = text.replace(root, '<tmp>')
    return text


# ---------------------------------------------------------------------------------- простори й сервер

def setup_spaces(tmp):
    """Два простори в тимчасових `DEAI_HOME`: `liga` (інтеграції ввімкнено) і `plain` (вимкнено); у кожному — задачі
    `t1` (є рядок команди) і `t2` (рядка команди нема). Повертає `{'liga': id, 'plain': id}`."""
    import spaces
    ids = {}
    for name, integ in (('Liga', True), ('Plain', False)):
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
        for tid, title, jira in (('t1', 'Demo one', 'LIGA-1'), ('t2', 'Demo two', 'LIGA-2')):
            d = os.path.join(path, tid)
            _write(os.path.join(d, 'iterations.json'), {
                'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00', 'published': False}], 'publish_url': None})
            tasks[tid] = {'title': title, 'dir': d, 'profile': 'tool', 'jira': jira, 'opened': '2026-11-01T10:00:00Z'}
        _write(os.path.join(path, 'tasks.json'), {'design_work_root': path, 'current': 't1', 'tasks': tasks})
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

    def get(self, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request('GET', path)
            r = conn.getresponse()
            return r.status, r.read().decode('utf-8')
        finally:
            conn.close()


def reset_team_cache():
    import serve
    serve._TEAM_CACHE.update(at=0.0, rows=None, error=None, rowsAt=None)


def overview(srv, tmp):
    """Тіло `/api/tasks-overview?refresh=1` без мінливого; `volatile` — типи вирізаних полів. Простір: без `id`/`path`."""
    reset_team_cache()
    status, body = srv.get('/api/tasks-overview?refresh=1')
    data = json.loads(scrub(body, tmp))
    team = data.get('team')
    # `fetchedAt` і `rowsAt` живуть у `team`; `team: null` (простір без інтеграцій) — їх нема зовсім.
    volatile = {k: (type(team.get(k)).__name__ if isinstance(team, dict) else None) for k in ('fetchedAt', 'rowsAt')}
    sp = data.get('space')
    if isinstance(sp, dict):
        sp.pop('id', None)
        sp.pop('path', None)
    return {'status': status, 'body': strip(data), 'volatile': volatile}


class Recorder:
    """Підміна `urllib.request.urlopen`: пише кожен виклик (URL, заголовки з ключем → `<key>`, тайм-аут) і віддає
    `body` (чи кидає `exc`). Без мережі за будь-яких умов."""

    def __init__(self, body=b'[]', exc=None, keys=(KEY,), with_body=False):
        self.calls, self.body, self.exc, self.keys, self.with_body = [], body, exc, keys, with_body

    def __call__(self, req, timeout=None, context=None, **kw):
        headers = {}
        for k, v in req.header_items():
            v = str(v)
            for key in self.keys:
                v = v.replace(key, '<key>')
            headers[k.lower()] = v
        call = {'url': req.full_url, 'method': req.get_method(), 'headers': headers,
                'timeout': timeout, 'ssl_context': context is not None}
        if self.with_body:
            call['body'] = json.loads(req.data.decode('utf-8')) if req.data else None
        self.calls.append(call)
        if self.exc:
            raise self.exc
        return _Resp(self.body)


class _Resp:
    status = 201            # `upsert_project` повертає `r.status`

    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *limit):
        return self._body


def team_read(ids, tmp):
    import serve
    import spaces
    out = {}
    fake = os.path.join(tmp, 'team-fake.json')
    rows3 = [
        {'id': 't1', 'name': 'Demo one', 'jira': 'LIGA-1', 'jira_status': 'In Review',
         'jira_status_cat': 'indeterminate', 'open_comments': 2, 'thumb_url': None,
         'code_url': 'https://dc-t1.vercel.example', 'updated_at': '2026-11-01T10:00:00Z', 'designer': 'Alpha',
         'iterations': 1, 'pages': 2},
        {'id': 'x9', 'name': 'Другий дизайнер', 'jira': 'LIGA-9', 'jira_status': 'Done', 'jira_status_cat': 'done',
         'open_comments': 0, 'thumb_url': 'https://demo.supabase.example/storage/x9.jpg',
         'code_url': None, 'updated_at': '2026-10-30T09:00:00Z', 'designer': 'Bob', 'iterations': 3, 'pages': None},
        {'name': 'Рядок без id', 'open_comments': 1},
    ]
    with Server() as srv:
        # (1) шов `DC_TEAM_FAKE`: файл замість бази
        spaces.switch_space(ids['liga'])
        _write(fake, rows3)
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}), \
                mock.patch.object(serve.urllib.request, 'urlopen', Recorder()) as uo:
            case = overview(srv, tmp)
        case['urlopen_calls'] = 0
        case['input_rows'] = rows3
        out['fake_three_rows'] = case

        # (2) справжній запит без шва: `supabase_config` → (адреса, ключ), `urlopen` — записувач
        rec = Recorder(json.dumps(rows3[:2]).encode('utf-8'))
        with mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY)), \
                mock.patch.object(serve.urllib.request, 'urlopen', rec):
            case = overview(srv, tmp)
        case['urlopen_calls'] = rec.calls
        case['input_rows'] = rows3[:2]
        out['supabase_request'] = case

        # (2b) мережа впала: рядків нема, помилка в `team.error`, у «Моїх» чужих рядків нема
        rec = Recorder(exc=OSError('мережі нема'))
        with mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY)), \
                mock.patch.object(serve.urllib.request, 'urlopen', rec):
            case = overview(srv, tmp)
        case['urlopen_calls'] = len(rec.calls)
        out['supabase_error'] = case

        # (2c) конфігу установки нема: чесне «не налаштовано», жодної мережі
        rec = Recorder()
        with mock.patch.object(serve, 'supabase_config', return_value=(None, None)), \
                mock.patch.object(serve.urllib.request, 'urlopen', rec):
            case = overview(srv, tmp)
        case['urlopen_calls'] = len(rec.calls)
        out['no_config'] = case

        # (2d) закон ізоляції: `DC_TASKS_FILE`/`DC_NO_OVERVIEW` БЕЗ шва `DC_TEAM_FAKE` — мережі нема, чесне пояснення, і
        # навіть валідний конфіг не рятує (`urlopen` — записувач: 0 викликів)
        for name, var in (('isolation_dc_tasks_file', 'DC_TASKS_FILE'), ('isolation_dc_no_overview', 'DC_NO_OVERVIEW')):
            rec = Recorder()
            with mock.patch.dict(os.environ, {var: os.path.join(tmp, 'x-tasks.json') if var == 'DC_TASKS_FILE' else '1'}), \
                    mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY)), \
                    mock.patch.object(serve.urllib.request, 'urlopen', rec):
                case = overview(srv, tmp)
            case['urlopen_calls'] = len(rec.calls)
            out[name] = case

        # (2e) відповідь бази — не масив: `ValueError` → текст у `team.error`, рядків нема (кеш порожній)
        rec = Recorder(b'{"message": "not an array"}')
        with mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY)), \
                mock.patch.object(serve.urllib.request, 'urlopen', rec):
            case = overview(srv, tmp)
        case['urlopen_calls'] = len(rec.calls)
        out['non_array_response'] = case

        # (2f) масив із сміттям: лишаються лише обʼєкти
        rec = Recorder(json.dumps([rows3[1], 5, 'x', None, ['y']]).encode('utf-8'))
        with mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY)), \
                mock.patch.object(serve.urllib.request, 'urlopen', rec):
            case = overview(srv, tmp)
        case['urlopen_calls'] = len(rec.calls)
        out['array_with_junk'] = case

        # (3) простір без інтеграцій: `team: null`, жодного виклику `urlopen` (навіть коли шов і конфіг є)
        spaces.switch_space(ids['plain'])
        rec = Recorder()
        with mock.patch.dict(os.environ, {'DC_TEAM_FAKE': fake}), \
                mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY)), \
                mock.patch.object(serve.urllib.request, 'urlopen', rec):
            case = overview(srv, tmp)
        case['urlopen_calls'] = len(rec.calls)
        out['integrations_off'] = case
        spaces.switch_space(ids['liga'])

    # (4) реєстр просторів не читається (`SpacesError` з `integrations_on`): `team_snapshot` повертає `([], пояснення, None)`
    # без запиту й без кешу. Викликаємо НАПРЯМУ: маршрут перед `team_snapshot` сам питає простір і при збої реєстру не дійшов би сюди.
    reset_team_cache()
    rec = Recorder()
    boom = spaces.SpacesError('spaces-unreadable', '<registry>', 'тест')
    with mock.patch.object(spaces, 'integrations_on', side_effect=boom), \
            mock.patch.object(serve, 'supabase_config', return_value=(URL, KEY)), \
            mock.patch.object(serve.urllib.request, 'urlopen', rec):
        rows, error, rows_at = serve.team_snapshot(refresh=True)
    out['team_snapshot_spaces_error'] = {'rows': rows, 'error': error, 'rows_at': rows_at, 'urlopen_calls': len(rec.calls),
                                         'cache_untouched': serve._TEAM_CACHE['rows'] is None}
    reset_team_cache()
    return out


# ---------------------------------------------------------------------------------- шлях запису: cmd_sync

def sync_push(tmp):
    import overview_push as ov
    import registry
    d = os.path.join(tmp, 'sync')

    def iters(name, body):
        _write(os.path.join(d, name, 'iterations.json'), body)
        return os.path.join(d, name)

    gl = {'repo': 'git@git.example:org/demo-design.git', 'path': 'mockup/t1'}
    t1_iters = {'iterations': [{'id': 'it1', 'date': '30.10.2026 10:00', 'published': False},
                               {'id': 'it2', 'date': '01.11.2026 12:30', 'published': False}],
                'gitlab': {'synced_at': '31.10.2026 18:00'}}
    t2_iters = {'iterations': [{'id': 'it1', 'date': '02.11.2026 09:00', 'published': True}],
                'publish_url': 'https://dc-t2.vercel.example', 'published_at': '02.11.2026 09:30'}
    t3_iters = {'iterations': [{'id': 'it1', 'date': '28.10.2026 08:00', 'published': True}],
                'publish_url': 'https://dc-t3.vercel.example'}
    t5_iters = {'iterations': [{'id': 'it1', 'date': '29.10.2026 08:00', 'published': False}]}
    tasks = {
        # свій, із відкритим коментарем і статусом Jira → status=review, jira_status=Done
        't1': {'title': 'Demo one', 'dir': iters('t1', t1_iters), 'jira': 'LIGA-1', 'profile': 'united',
               'gitlab': gl, 'owner_key': 'alpha@example.com', 'figma': 'https://figma.example/file/1'},
        # опублікований свій без Jira-статусу, зі своїм comment_project (лічильників нема → 0)
        't2': {'title': 'Demo two', 'dir': iters('t2', t2_iters), 'jira': 'LIGA-2', 'profile': 'liga360',
               'comment_project': 'proj/alpha'},
        # чужа (owner_key іншого дизайнера): авторство не присвоюється, посилання превʼю — власника
        't3': {'title': 'Demo three', 'dir': iters('t3', t3_iters), 'profile': 'seo', 'owner_key': 'bob@example.com'},
        # теки на цій машині нема: пропускається, вихолощувати картку не можна
        't4': {'title': 'Demo four', 'dir': os.path.join(d, 't4-missing'), 'jira': 'LIGA-4', 'profile': 'tool'},
        # PII в назві (10 цифр): картка не відправляється
        't5': {'title': 'Справа 1234567890', 'dir': iters('t5', t5_iters), 'profile': 'tool'},
        # фікстура: gitlab.repo у «тимчасовому» корені → відкидається вголос, ще до перевірки теки
        'nova': {'title': 'Нова', 'profile': 'tool', 'gitlab': {'repo': f'{FAKE_TMP}/nova.git', 'path': 'mockup/nova'}},
    }
    cfg = {'current': 't1', 'tasks': tasks}
    tasks_file = os.path.join(d, 'tasks.json')
    _write(tasks_file, cfg)
    reg = {
        'reg1': {'title': 'Registry one', 'jira': 'LIGA-11', 'gitlab': {'repo': 'git@git.example:org/demo-design.git'},
                 'owner': 'Alpha', 'owner_key': 'alpha@example.com', 'figma': 'https://figma.example/file/11',
                 'updated_at': '2026-11-01T10:00:00Z', 'comment_project': 'proj/reg1'},
        # фікстура реєстру: теж відкидається вголос (інцидент 15.09.2026)
        'regfix': {'title': 'Fixture', 'gitlab': {'repo': f'{FAKE_TMP}/regfix.git'}},
    }
    counts = {'dc/t1': 1}
    jira = {'LIGA-1': {'name': 'Done', 'cat': 'done'}}
    calls, jira_asked = [], []

    def upsert(row, ignore=False):
        calls.append({'row': strip(row), 'ignore': ignore,
                      'volatile_present': sorted(k for k in VOLATILE if k in row)})

    def jira_statuses(keys):
        jira_asked.append(list(keys))
        return jira

    buf = io.StringIO()
    with mock.patch.dict(os.environ, {'DC_TASKS_FILE': tasks_file}), \
            mock.patch.object(registry, '_temp_roots', return_value=[FAKE_TMP]), \
            mock.patch.object(ov, '_identity', return_value=('Alpha', 'alpha@example.com')), \
            mock.patch.object(ov, 'discover_projects', return_value=reg), \
            mock.patch.object(ov, 'open_comment_counts', return_value=counts), \
            mock.patch.object(ov, 'jira_statuses', jira_statuses), \
            mock.patch.object(ov, 'upsert_project', upsert), \
            contextlib.redirect_stdout(buf):
        ov.cmd_sync()

    def rel(path):
        return scrub(path, tmp).replace('<tmp>/sync/', '<dir>/')
    inp_tasks = {tid: {**t, 'dir': rel(t['dir']) if t.get('dir') else None} for tid, t in tasks.items()}
    for t in inp_tasks.values():
        if t['dir'] is None:
            del t['dir']
    return {
        'input': {'tasks': inp_tasks,
                  'iterations_json': {'t1': t1_iters, 't2': t2_iters, 't3': t3_iters, 't5': t5_iters},
                  'registry': reg, 'open_comment_counts': counts, 'jira_statuses': jira,
                  'identity': ['Alpha', 'alpha@example.com'], 'fake_temp_root': FAKE_TMP},
        'jira_keys_asked': jira_asked,
        'upserts': calls,
        'stdout': [rel(line) for line in buf.getvalue().splitlines()],
    }


# ---------------------------------------------------------------------------------- HTTP-форма запису й вибір конфігу

def upsert_http():
    """Справжній `overview_push.upsert_project` (не заглушка) з записувачем замість `urlopen`: URL, метод, заголовки, тайм-аут, тіло
    — для `ignore=False` (merge-duplicates) і `ignore=True` (ignore-duplicates). Ключ у заголовках → `<key>`."""
    import overview_push as ov
    out = {}
    row = {'id': 't1', 'name': 'Demo one', 'status': 'pub', 'iterations': 2, 'source': 'canvas'}
    for name, ignore in (('merge_duplicates', False), ('ignore_duplicates', True)):
        rec = Recorder(with_body=True)
        env = {'SUPABASE_URL': URL, 'SUPABASE_KEY': KEY}
        with mock.patch.dict(os.environ, env), mock.patch.object(ov.urllib.request, 'urlopen', rec):
            status = ov.upsert_project(row, ignore=ignore)
        out[name] = {'ignore': ignore, 'returned_status': status, 'calls': rec.calls, 'input_row': row}
    return out


def supabase_choice():
    """`overview_push._supabase()`: з якого джерела береться пара. Значення замінено мітками джерел (жодних значень у знімку):
    env `SUPABASE_URL`+`SUPABASE_KEY` → env; `SUPABASE_URL`+`SUPABASE_SERVICE_KEY` → сервісний ключ; обидва ключі → `SUPABASE_KEY`;
    без env → `serve.supabase_config()`; нічого → `RuntimeError` зі сталим текстом."""
    import overview_push as ov
    import serve
    urls = {'env': 'https://env.supabase.example', 'config': 'https://config.supabase.example'}
    keys = {'env-key': 'sk-test-env', 'env-service-key': 'sk-test-service', 'config-key': 'sk-test-config'}
    label = {v: k for k, v in keys.items()}
    label.update({v: k + '-url' for k, v in urls.items()})

    def run(env, config):
        with mock.patch.dict(os.environ, env), mock.patch.object(serve, 'supabase_config', return_value=config):
            try:
                url, key = ov._supabase()
            except RuntimeError as e:
                return {'error': str(e)}
        return {'url': label.get(url, '?'), 'key': label.get(key, '?')}
    cfg = (urls['config'], keys['config-key'])
    return {
        'env_url_and_key': run({'SUPABASE_URL': urls['env'], 'SUPABASE_KEY': keys['env-key']}, cfg),
        'env_url_and_service_key': run({'SUPABASE_URL': urls['env'], 'SUPABASE_SERVICE_KEY': keys['env-service-key']}, cfg),
        'env_both_keys_key_wins': run({'SUPABASE_URL': urls['env'], 'SUPABASE_KEY': keys['env-key'],
                                       'SUPABASE_SERVICE_KEY': keys['env-service-key']}, cfg),
        'env_url_only_falls_back_to_config': run({'SUPABASE_URL': urls['env']}, cfg),
        'no_env_uses_config': run({}, cfg),
        'neither': run({}, (None, None)),
    }


# ---------------------------------------------------------------------------------- гейт запуску синку

def sync_gate(ids, tmp):
    import serve
    import spaces
    home = os.environ['HOME']
    log = os.path.join(home, '.claude', 'pipeline-feedback', 'overview-sync.log')
    os.makedirs(os.path.dirname(log), exist_ok=True)

    def run(space, env=None, config=(URL, KEY)):
        if os.path.exists(log):
            os.remove(log)
        # Оточення дитини = `os.environ` + пара `SUPABASE_*`. Щоб імена ключів не залежали від машини, на час прогону оточення
        # КОНТРОЛЬОВАНЕ (`clear=True`): лише `HOME`, `DEAI_HOME`, `PATH` + змінні випадку.
        base = {'HOME': home, 'DEAI_HOME': os.environ['DEAI_HOME'], 'PATH': '/usr/bin'}
        with mock.patch.dict(os.environ, {**base, **(env or {})}, clear=True), \
                mock.patch.object(serve, 'supabase_config', return_value=config), \
                mock.patch.object(serve.subprocess, 'Popen') as popen, \
                spaces.request_space(space):
            serve.Handler._overview_sync(None)
        res = {'popen_started': popen.called, 'log_created': os.path.exists(log)}
        if popen.called:
            args, kw = popen.call_args
            argv = [os.path.relpath(a, ROOT) if os.path.isabs(a) else a for a in args[0]]
            child = kw['env']
            res.update(argv=argv, env_url=kw['env'].get('SUPABASE_URL'),
                       # лише ІМЕНА ключів (без значень); `SUPABASE_*` — окремо (пара), решта успадкована з `os.environ`
                       env_other_key_names=sorted(k for k in child if not k.startswith('SUPABASE_')),
                       env_supabase_key_names=sorted(k for k in child if k.startswith('SUPABASE_')),
                       log_relpath=os.path.relpath(kw['stdout'].name, home), log_mode=kw['stdout'].mode,
                       env_key_is_config_key=kw['env'].get('SUPABASE_KEY') == config[1],
                       stdout_is_log=kw['stdout'].name == log,
                       stderr_is_stdout=kw['stderr'] == serve.subprocess.STDOUT,
                       kwargs=sorted(kw))
        return res
    return {
        'integrations_on_with_config': run(ids['liga']),
        'integrations_off': run(ids['plain']),
        'dc_no_overview': run(ids['liga'], env={'DC_NO_OVERVIEW': '1'}),
        'no_config': run(ids['liga'], config=(None, None)),
        # `DC_TASKS_FILE` гейт НЕ глушить (глушить лише `DC_NO_OVERVIEW`): запис — інший закон, ніж читання `_team_fetch`
        'dc_tasks_file_with_integrations_on': run(ids['liga'], env={'DC_TASKS_FILE': os.path.join(tmp, 'x-tasks.json')}),
        'notes': [
            '4c-1 змінить навмисно: argv дитини дістане `--space <id>` (синк веде простір, а не «поточний машини»);',
            '4c-1 змінить навмисно: перший елемент argv — `sys.executable`, а не літерал `python3`;',
            'решта (оточення дитини = os.environ + пара SUPABASE_*, лог у ~/.claude/pipeline-feedback/overview-sync.log, режим `a`,',
            'stderr→stdout, гейти integrations/DC_NO_OVERVIEW/конфіг) лишається як у цьому знімку.',
        ],
    }


# ---------------------------------------------------------------------------------- збирання

def build():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4c1-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        env = {'HOME': home, 'DEAI_HOME': os.path.join(tmp, 'deai')}
        with mock.patch.dict(os.environ, env):
            for name in CLEAN:
                os.environ.pop(name, None)
            import spaces
            # Старий файл задач — тимчасовий (шар просторів увімкнено, бо є `DEAI_HOME`): справжнього `tasks.json` не читаємо.
            with mock.patch.object(spaces, 'legacy_tasks_file', return_value=os.path.join(tmp, 'legacy', 'tasks.json')):
                ids = setup_spaces(tmp)
                snap = {
                    'meta': {'version': '0.11.0', 'source_commit': '6e0a0a5', 'generator': 'tests/make_before_4c1.py',
                             'volatile_stripped': list(VOLATILE)},
                    'team_read': team_read(ids, tmp),
                    'sync_push': sync_push(tmp),
                    'upsert_http': upsert_http(),
                    'supabase_choice': supabase_choice(),
                    'sync_gate': sync_gate(ids, tmp),
                }
    spaces_guard.assert_untouched(real)
    return snap


def dump(snap):
    return json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args()
    text = dump(build())
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f'записано {args.out} ({len(text)} байт)')


if __name__ == '__main__':
    main()
