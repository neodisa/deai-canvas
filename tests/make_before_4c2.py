#!/usr/bin/env python3
"""Генератор знімка поведінки статусів трекера на 0.12.0: `tests/fixtures/tracker/before-4c2.json` (етап 4c-2, Task 1).

Знімок знято ДО змін коду (`HEAD` = 0.12.0 + спека/план 4c-2) і лишається в репо як еталон паритету: тести наступних задач
(`tests/test_tracker.py`: паритет модуля `jira-tracker`, синку й екрана «Задачі») читають JSON, а не переганяють цей генератор.
Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме знято (запуск на НОВОМУ коді дасть не «до», а «після»: еталон не
перезаписувати).

Що знято (усе — на заглушках, жодної мережі й жодних файлів поза тимчасовою текою):
  * `jira_request` — справжній `overview_push.jira_statuses` (не заглушка) зі підміненим `urllib.request.urlopen`: метод,
    шлях URL (БЕЗ хоста: `_JIRA_BASE` у знімок не йде), тіло (JSON), заголовки (`Authorization` → `<basic>`), тайм-аут, наявність
    TLS-контексту; відповідь-заглушка і розібраний результат. Плюс: без облікових → `{}` і жодного `urlopen`; `urlopen` кидає
    `OSError` → `{}`;
  * `sync_cards` — `dashboard.sync(...)` зі `statuses` = заглушка з результатом вище, `identity`, записувачем `call` (push) і двома
    задачами з теками в tmp (`jira: DEMO-1`/`DEMO-2`): список `(mode, картки)` і рядки логу;
  * `tasks_overview` — шлях ЛІГИ: тіло `GET /api/tasks-overview` на `DC_TASKS_FILE` + `DC_TEAM_FAKE` (рядок `t1` зі
    `jira_status`/`jira_status_cat`).

Виключено з JSON усе мінливе: `fetchedAt`, `rowsAt`, `changed`, `synced_at`, `updated_at`, `jira_synced_at`, абсолютні шляхи
(тека → `<tmp>`). Прогін двічі дає той самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 tests/make_before_4c2.py [--out ШЛЯХ]   (типово — `tests/fixtures/tracker/before-4c2.json`)

⛔ Ізоляція: власний тимчасовий `HOME` (файли облікових Jira й лог синку у `~/.claude/pipeline-feedback/` — лише там), без
`DEAI_HOME` (шар просторів вимкнено: ЛІГА = `DC_TASKS_FILE`), `JIRA_*`/`SUPABASE_*` у чистому оточенні. Реєстр GitLab, Jira й
Supabase — заглушки; `registry._temp_roots` підмінено, щоб тимчасові теки генератора не вважались «фікстурами тесту».
"""
import argparse
import base64
import http.client
import json
import os
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

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'tracker', 'before-4c2.json')
#: Поля, що змінюються між прогонами: з відповіді/рядків їх вирізано.
VOLATILE = ('fetchedAt', 'rowsAt', 'changed', 'synced_at', 'updated_at', 'jira_synced_at')
#: Вигаданий «тимчасовий корінь» для `registry._temp_roots` (запис під ним — фікстура тесту; тут таких нема).
FAKE_TMP = '/deai-fixture-tmp'
#: Змінні оточення, що ізолюють прогін або задають конфіг, — у знімку їх нема (чисте оточення).
CLEAN = ('DC_TASKS_FILE', 'DC_NO_OVERVIEW', 'DC_TEAM_FAKE', 'DC_TEAMS_FAKE', 'SUPABASE_URL', 'SUPABASE_KEY',
         'SUPABASE_SERVICE_KEY', 'DEAI_EXTRA_MODULES', 'DEAI_HOME', 'JIRA_EMAIL', 'JIRA_TOKEN', 'DC_IDENTITY_NAME',
         'DC_IDENTITY_EMAIL')
EMAIL = 'alpha@example.com'
TOKEN = 'tok-test-1'
#: Відповідь-заглушка Jira (`/rest/api/3/search/jql`) на два ключі.
JIRA_RESPONSE = {'issues': [
    {'key': 'DEMO-1', 'fields': {'status': {'name': 'In Review', 'statusCategory': {'key': 'indeterminate'}}}},
    {'key': 'DEMO-2', 'fields': {'status': {'name': 'Done', 'statusCategory': {'key': 'done'}}}},
]}


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


class _Resp:
    """Відповідь-заглушка `urlopen`: контекстний менеджер, що читається `json.load`."""

    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *limit):
        return self._body


class Recorder:
    """Підміна `urllib.request.urlopen`: пише кожен виклик (метод, шлях без хоста, тіло, заголовки, тайм-аут) і віддає `body`
    (чи кидає `exc`). `Authorization` → `<basic>` (значення — похідне від пари облікових; у знімку його нема)."""

    def __init__(self, body=b'{}', exc=None):
        self.calls, self.body, self.exc = [], body, exc

    def __call__(self, req, timeout=None, context=None, **kw):
        parts = urlsplit(req.full_url)
        headers = {}
        for k, v in req.header_items():
            headers[k.lower()] = '<basic>' if k.lower() == 'authorization' and str(v).startswith('Basic ') else str(v)
        auth = dict(req.header_items()).get('Authorization', '')
        self.calls.append({
            'method': req.get_method(), 'path': parts.path, 'query': parts.query,
            'body': json.loads(req.data.decode('utf-8')) if req.data else None,
            'headers': headers, 'timeout': timeout, 'ssl_context': context is not None,
            # Чи `Authorization` справді Basic від пари `email:token` — без значення у знімку.
            'authorization_is_basic_of_credentials':
                auth == 'Basic ' + base64.b64encode(f'{EMAIL}:{TOKEN}'.encode('utf-8')).decode('ascii'),
        })
        if self.exc:
            raise self.exc
        return _Resp(self.body)


# ---------------------------------------------------------------------------------- запит до Jira

def jira_request():
    import overview_push as ov
    out = {}
    keys = ['DEMO-1', 'DEMO-2', 'DEMO-1', '', None]
    env = {'JIRA_EMAIL': EMAIL, 'JIRA_TOKEN': TOKEN}

    # (1) облікові є: один запит, унікальні ключі в порядку появи, порожні відкинуто
    rec = Recorder(json.dumps(JIRA_RESPONSE).encode('utf-8'))
    with mock.patch.dict(os.environ, env), mock.patch.object(ov.urllib.request, 'urlopen', rec):
        result = ov.jira_statuses(keys)
    out['request'] = {'input_keys': keys, 'calls': rec.calls, 'stub_response': JIRA_RESPONSE, 'result': result}

    # (2) облікових нема (ні оточення, ні файлів у тимчасовому HOME): {} і жодного запиту
    rec = Recorder(json.dumps(JIRA_RESPONSE).encode('utf-8'))
    with mock.patch.object(ov.urllib.request, 'urlopen', rec):
        result = ov.jira_statuses(keys)
    out['no_credentials'] = {'result': result, 'urlopen_calls': len(rec.calls)}

    # (3) мережа впала: {} (наявні статуси не затираються)
    rec = Recorder(exc=OSError('мережі нема'))
    with mock.patch.dict(os.environ, env), mock.patch.object(ov.urllib.request, 'urlopen', rec):
        result = ov.jira_statuses(keys)
    out['network_error'] = {'result': result, 'urlopen_calls': len(rec.calls)}
    return out


# ---------------------------------------------------------------------------------- синк карток

def sync_cards(tmp):
    import dashboard
    import registry
    d = os.path.join(tmp, 'sync')
    tasks = {}
    for tid, title, jira in (('t1', 'Demo one', 'DEMO-1'), ('t2', 'Demo two', 'DEMO-2')):
        tdir = os.path.join(d, tid)
        _write(os.path.join(tdir, 'iterations.json'),
               {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00', 'published': False}], 'publish_url': None})
        tasks[tid] = {'title': title, 'dir': tdir, 'profile': 'tool', 'jira': jira, 'opened': '2026-11-01T10:00:00Z'}
    cfg = {'current': 't1', 'tasks': tasks}
    jira = {'DEMO-1': {'name': 'In Review', 'cat': 'indeterminate'}, 'DEMO-2': {'name': 'Done', 'cat': 'done'}}
    asked, pushes, lines = [], [], []

    def statuses(keys):
        asked.append(list(keys))
        return jira

    def call(module, name, ctx, *args, **kw):
        # Єдиний очікуваний виклик модуля — `push(cards, mode)`; усе інше — помилка знімка.
        assert name == 'push', name
        cards, mode = args
        pushes.append({'mode': mode, 'cards': strip(cards)})
        return {'ok': len(cards), 'failed': {}}

    with mock.patch.object(registry, '_temp_roots', return_value=[FAKE_TMP]):
        summary = dashboard.sync(cfg, object(), {}, statuses=statuses, identity=('Alpha', EMAIL), log=lines.append, call=call)

    def rel(text):
        return scrub(text, tmp).replace('<tmp>/sync/', '<dir>/')
    return {
        'input': {'jira': jira, 'identity': ['Alpha', EMAIL], 'tasks': {tid: {**t, 'dir': '<dir>/' + tid} for tid, t in tasks.items()}},
        'statuses_asked': asked,
        'pushes': pushes,
        'log': [rel(line) for line in lines],
        'summary': summary,
    }


# ---------------------------------------------------------------------------------- екран «Задачі», шлях ЛІГИ

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


def tasks_overview(tmp):
    import serve
    d = os.path.join(tmp, 'overview')
    tdir = os.path.join(d, 't1')
    _write(os.path.join(tdir, 'iterations.json'),
           {'iterations': [{'id': 'it1', 'date': '01.11.2026 10:00', 'published': False}], 'publish_url': None})
    tasks_file = os.path.join(d, 'tasks.json')
    _write(tasks_file, {'current': 't1', 'tasks': {
        't1': {'title': 'Demo one', 'dir': tdir, 'profile': 'tool', 'jira': 'DEMO-1', 'opened': '2026-11-01T10:00:00Z'}}})
    row = {'id': 't1', 'name': 'Demo one', 'jira': 'DEMO-1', 'jira_status': 'In Review',
           'jira_status_cat': 'indeterminate', 'open_comments': 2, 'thumb_url': None,
           'code_url': 'https://dc-t1.vercel.example', 'updated_at': '2026-11-01T10:00:00Z', 'designer': 'Alpha',
           'iterations': 1, 'pages': 1}
    fake = os.path.join(d, 'team-fake.json')
    _write(fake, [row])
    serve._TEAM_CACHE.update(at=0.0, rows=None, error=None, rowsAt=None)
    with mock.patch.dict(os.environ, {'DC_TASKS_FILE': tasks_file, 'DC_TEAM_FAKE': fake}), Server() as srv:
        status, body = srv.get('/api/tasks-overview?refresh=1')
    data = json.loads(scrub(body, tmp))
    team = data.get('team')
    volatile = {k: (type(team.get(k)).__name__ if isinstance(team, dict) else None) for k in ('fetchedAt', 'rowsAt')}
    serve._TEAM_CACHE.update(at=0.0, rows=None, error=None, rowsAt=None)
    return {'status': status, 'body': strip(data), 'volatile': volatile, 'input_rows': [row]}


# ---------------------------------------------------------------------------------- збирання

def build():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4c2-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}):
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {
                'meta': {'version': '0.12.0', 'source_commit': _source_commit(), 'generator': 'tests/make_before_4c2.py',
                         'volatile_stripped': list(VOLATILE)},
                'jira_request': jira_request(),
                'sync_cards': sync_cards(tmp),
                'tasks_overview': tasks_overview(tmp),
            }
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.12.0 = `3065dac`; після нього лише docs 4c-2). Зашито, щоб прогін на новому коді не
    видавав себе за «до»."""
    return '3065dac'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    snap = build()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(json.dumps(snap, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print('знімок записано:', args.out)


if __name__ == '__main__':
    main()
