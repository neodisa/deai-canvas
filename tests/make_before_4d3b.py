#!/usr/bin/env python3
"""Генератор знімка поведінки простору ЛІГА на 0.17.0 для ролей `comments` і `vcs`: `tests/fixtures/liga-migration/before-4d3b.json`
(етап 4d-3b, Task 1).

Знімок знято ДО змін коду (код = 0.17.0, коміт `6906621`, тег `v0.17.0`) і лишається в репо як еталон паритету другого кроку
міграції ЛІГИ: після 0.18 ЛІГА має ту саму поведінку для людини, хоч `comments` і `vcs` стають ЯВНИМИ модулями `space.json`
(`supabase-comments`, `git-sync`). Тести наступних задач (`tests/test_liga_migrate_b.py`) читають JSON, а не переганяють цей
генератор. Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме знято (запуск на НОВОМУ коді дасть не «до», а «після»: еталон не
перезаписувати).

Спільні помічники (`Rig`, `Server`, `Recorder`, `san_ctx`, `NoNet`, `SocketTripwire`, `scrub`, `rel`, `CLEAN`, вигадані константи)
ІМПОРТУЮТЬСЯ з `make_before_4d3a.py`: друга копія розійшлась би. Власне тут лише те, чого там нема (запис аргументів виклику
модуля, стенд із задачами для синку, секції `comments` і `vcs`).

Що знято (усе — у тимчасових теках, без мережі й без справжніх репо, дзеркал, Supabase, Jira чи Teams). Простір ЛІГА — запис
реєстру тимчасового `DEAI_HOME` з `legacy: true` і `integrations: true`, тека простору — тимчасова, `space.json` у ній НЕМАЄ
(ЛІГА живе на неявному постачальнику):
  * `comments` — канал коментарів: `serve.comment_channel` (задачі з `comment_project` і без × `internal`), `ProjectComments`
    (`kind`, `label`, `takes_iteration`, `channel`, виклик `list` модулем: ctx і канал), `comments_route` (санітизований ctx,
    канали), `GET /api/comment-config?ch=project`, `GET /api/task` → `comment_channel`, `GET`/`POST /api/teams-mute` (канал; шов
    `DC_TEAMS_FAKE`), ключ лічильника дашборда (`dashboard.sync` із фейковим модулем: які ключі питає лічильник), `inbox resolve`
    (поведінка щодо короткого префікса й підпис джерела в dry-run);
  * `vcs` — справжній `serve.vcs_provider()` (НЕ підмінений): `ctx` (налаштування, `mirror_flat`, `cache_dir` відносно
    `DC_MIRRORS_DIR`), `vcs_mirror_dir` для зразкових репо (SSH, https, вкладений шлях), тексти (тема коміту й README
    `gitlab_sync`, `gitlab_status` — `web`/`label`, `gitlab_pull` — підпис джерела, автокоміт `autosync`, примітка форку
    `_task_new_write`, рядок `bin/state.py`), прапорець форми «Нова задача» (`app/spaces-model.js` через `node` на записі
    `GET /api/spaces`), `capabilities`. Git НЕ запускається: `deai_modules.call` замінено записувачем (`mirror_dir` — чиста функція
    модуля, вона йде справжнім викликом), а `serve.git_autocommit` (єдине місце, що кликало б справжній `git`) — записувачем
    повідомлення коміту.

Виключено з JSON усе мінливе: часові поля (час і хеш у тілі коміту → `<time>`/`<hash>`), абсолютні шляхи (тека → `~/…`/`<tmp>`),
значення секретів (→ `<secret:ДОВЖИНА>`). Прогін двічі дає той самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 -B tests/make_before_4d3b.py [--out ШЛЯХ]   (типово — `tests/fixtures/liga-migration/before-4d3b.json`)

⚠️ ГЕНЕРАТОР РОБИТЬ ЗНІМОК v0.17.0 (код — коміт 6906621) і мусить запускатись проти ЗАМОРОЖЕНОЇ копії старого коду, а не
проти робочої теки (з Task 2–7 `app/`/`bin/` змінюються — і знімок з міткою `source_commit: 6906621` містив би дані «після»).
Як:
    D=$(mktemp -d) && git archive v0.17.0 | tar -x -C "$D"      # заморожена копія коду v0.17.0
    cp tests/make_before_4d3b.py "$D/tests/"                    # лише сам генератор (він бере ROOT від свого розташування)
    python3 -B "$D/tests/make_before_4d3b.py" --out tests/fixtures/liga-migration/before-4d3b.json
Прогін на новому коді — лише як документація: запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від
6906621, генератор ВІДМОВЛЯЄ (код виходу 2); копія з `git archive` — не git-тека, там довіряємо рецепту.

⛔ Ізоляція: власні тимчасові `HOME` і `DEAI_HOME` (звідси `~/.deai` і `~/.claude/pipeline-feedback/` — тимчасові), чисте
оточення (змінні конфігу прибрані на час прогону; потрібні виставляються ЛИШЕ тут, через `mock.patch.dict`, вигаданими значеннями),
жодної мережі (розтяжка сокетів + `urllib.request.urlopen` — заглушка-лічильник); справжній `~/.deai` стереже `spaces_guard`.
"""
import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

# ⛔ Спільне — з генератора 4d-3a (друга копія розійшлась би).
from make_before_4d3a import (CLEAN, JIRA_BASE, REPO_SEO, REPO_UNITED, SB_KEY, SB_URL, SPACE_ID, NoNet, Recorder, Rig,  # noqa: E402
                              Server, SocketTripwire, _jsonable, _outcome, _write, rel, san_ctx, scrub)

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d3b.json')
#: Змінні, яких у чистому оточенні нема, а знімку потрібні: особа машини (без неї `machine_identity()` кликав би `git config`) і
#: тека дзеркал (без неї вона — `<ROOT>/.mirrors`, тобто абсолютний шлях замороженої копії).
IDENTITY = ('Alpha Designer', 'alpha@example.com')
OTHER_KEY = 'beta@example.com'

REPO_HTTPS = 'https://git.example.com/studio/web.git'
REPO_NESTED = 'https://git.example.com/group/sub/web.git'


# ---------------------------------------------------------------------------------- стенд

class Rec(Recorder):
    """Записувач виклику модуля: `(module, fn, ctx, timeout)` як у `Recorder` + аргументи (`args`). Відповіді — `answers[fn]`
    (значення чи функція `(ctx, *args)`), інакше порожні, але валідні. `mirror_dir` — чиста функція модуля (нічого не створює,
    git не кличе): вона йде справжнім викликом, решта — ні."""

    def __init__(self, answers=None):
        super().__init__()
        self.args = []
        self.answers = answers or {}
        import deai_modules
        self._real = deai_modules.call

    def __call__(self, module, fn, ctx, *args, timeout=None):
        self.args.append(args)
        self.calls.append((module.id, fn, ctx, timeout))
        if fn == 'mirror_dir':
            return self._real(module, fn, ctx, *args, timeout=timeout)
        ans = self.answers.get(fn, self.EMPTY.get(fn, []))
        return ans(ctx, *args) if callable(ans) else ans


def _env_extra(rig, **more):
    """Оточення прогону: особа машини й тека дзеркал у теці стенду (DC_TASKS_FILE/DC_NO_OVERVIEW НЕ виставляємо — не ізоляція)."""
    return {'DC_IDENTITY_NAME': IDENTITY[0], 'DC_IDENTITY_EMAIL': IDENTITY[1],
            'DC_MIRRORS_DIR': os.path.join(rig.home, 'mirrors'), **more}


def liga(tmp, name):
    """Стенд ЛІГИ: три задачі (`a-1` із `comment_project` і двосторінковим макетом, `a-2`/`a-3` без; різні адреси репо), реєстр
    без `space.json`, старий `tasks.json` у теці стенду. → `(rig, space, cfg)`."""
    rig = Rig(tmp, name)
    w = os.path.join(rig.home, 'work')
    tasks = {'a-1': {'dir': os.path.join(w, 'a-1'), 'title': 'Alpha demo', 'jira': 'DEMO-1', 'track': 'seo',
                     'comment_project': 'liga-shared', 'gitlab': {'repo': REPO_UNITED, 'path': 'mockup/a-1'}},
             'a-2': {'dir': os.path.join(w, 'a-2'), 'title': 'Beta demo', 'jira': '', 'profile': 'united',
                     'gitlab': {'repo': REPO_HTTPS, 'path': 'mockup/a-2'}},
             'a-3': {'dir': os.path.join(w, 'a-3'), 'title': 'Gamma demo', 'jira': '',
                     'gitlab': {'repo': REPO_NESTED, 'path': 'mockup/a-3'}},
             'p-1': {'dir': os.path.join(w, 'p-1'), 'title': 'Pull demo', 'jira': '',
                     'gitlab': {'repo': REPO_UNITED, 'path': 'mockup/p-1'}}}
    cfg = rig.config(extra={'tasks': tasks, 'current': 'a-1'})
    _write(os.path.join(rig.home, '.ssh', 'example'), 'not a real key\n')        # `validate` модуля вимагає файл ключа з `gitlab_ssh_key`
    for tid, task in tasks.items():
        it1 = os.path.join(task['dir'], 'iterations', 'it1')
        _write(os.path.join(task['dir'], 'iterations.json'),
               {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'first', 'published': False}],
                'publish_url': None})
        if tid == 'a-1':           # два сторінки без кореневої: `gitlab_sync` пише README
            for pg in ('alpha', 'beta'):
                _write(os.path.join(it1, pg, 'index.html'), '<body>%s</body>' % pg)
            _write(os.path.join(it1, 'pages.json'), {'pages': [{'id': 'alpha', 'name': 'Альфа', 'published': True},
                                                              {'id': 'beta', 'name': 'Бета', 'published': False}]})
        else:
            _write(os.path.join(it1, 'index.html'), '<body>%s</body>' % tid)
    return rig, rig.registry(), cfg


def _stack(rig, env, *patches):
    """Один контекст: HOME/DEAI_HOME/особа/дзеркала + підміна `legacy_tasks_file` + простір запиту ЛІГА + довільні `patches`."""
    import spaces
    es = contextlib.ExitStack()
    es.enter_context(rig.activate(env))
    es.enter_context(spaces.request_space(SPACE_ID))
    for p in patches:
        es.enter_context(p)
    return es


def _hide(obj, secrets):
    """Значення секретів у знімку — `<secret:ДОВЖИНА>` (відповідь `comment-config` несе публічну конфігурацію з ключем)."""
    if isinstance(obj, str):
        for s in secrets:
            obj = obj.replace(s, '<secret:%d>' % len(s))
        return obj
    if isinstance(obj, dict):
        return {_hide(k, secrets): _hide(v, secrets) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_hide(v, secrets) for v in obj]
    return obj


def _call(srv, method, path, task=None, body=None):
    """`(status, JSON | None)`; як `Server.req`, але з тілом (POST). Origin — самого сервера."""
    import http.client
    headers = {'Origin': 'http://127.0.0.1:%d' % srv.port}
    if task:
        headers['X-Canvas-Task'] = task
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    conn = http.client.HTTPConnection('127.0.0.1', srv.port, timeout=15)
    try:
        conn.request(method, path, body=raw, headers=headers)
        r = conn.getresponse()
        txt = r.read().decode('utf-8', 'replace')
        try:
            return r.status, json.loads(txt)
        except ValueError:
            return r.status, None
    finally:
        conn.close()


# ---------------------------------------------------------------------------------- comments

def _channels(serve, cfg, rig):
    """Канал кожної задачі × `internal`: `serve.comment_channel`."""
    out = {}
    for tid, task in cfg['tasks'].items():
        if tid == 'p-1':
            continue
        out[tid] = {'comment_project': task.get('comment_project'),
                    'plain': serve.comment_channel(task, tid), 'internal': serve.comment_channel(task, tid, internal=True)}
    return out


def _project_comments(serve, cfg, rig, liga_space):
    """`ProjectComments` ЛІГИ: рішення, підпис, `takes_iteration`, канали і виклик `list`/`resolve` модулем (ctx і канал)."""
    import deai_modules as dm
    rec = Rec({'list': []})
    out = {}
    with mock.patch.object(dm, 'call', rec):
        dm.reset_caches()
        pc = serve.ProjectComments(liga_space)
        out['kind'], out['label'], out['takes_iteration'] = pc.kind, pc.label, pc.takes_iteration
        out['provider'] = type(pc.prov).__name__
        out['channels'] = {tid: {'plain': pc.channel(t, tid), 'internal': pc.channel(t, tid, internal=True)}
                           for tid, t in cfg['tasks'].items() if tid != 'p-1'}
        before = len(rec.calls)
        pins = _outcome(lambda: list(pc.pins(cfg['tasks']['a-1'], 'a-1')), rig.home)
        pins2 = _outcome(lambda: list(pc.pins(cfg['tasks']['a-2'], 'a-2', internal=True)), rig.home)
        res = _outcome(lambda: pc.resolve(cfg['tasks']['a-1'], 'a-1', 'abcdef12', 'ok', iteration=1), rig.home)
        out['calls'] = [{'module': m, 'fn': fn, 'timeout': t, 'ctx': san_ctx(c), 'args': _jsonable(list(a))}
                        for (m, fn, c, t), a in zip(rec.calls[before:], rec.args[before:])]
        out['outcomes'] = {'pins_a1': pins, 'pins_a2_internal': pins2, 'resolve_a1': res}
        dm.reset_caches()
    return out


def _route(serve, cfg, liga_space):
    """`comments_route`: модуль, санітизований ctx, канали (без виклику модуля)."""
    import deai_modules as dm
    dm.reset_caches()
    prov, err = serve.comments_provider(liga_space)
    out = {'provider': type(prov).__name__, 'provider_error': None if err is None else getattr(err, 'code', 'err')}
    mod, ctx, channel = serve.comments_route(liga_space, prov)
    out['module'] = mod.id
    out['ctx'] = san_ctx(ctx)
    out['channels'] = {tid: {'plain': channel(t, tid), 'internal': channel(t, tid, internal=True)}
                       for tid, t in cfg['tasks'].items() if tid != 'p-1'}
    dm.reset_caches()
    return out


class _Counts(dict):
    """Лічильник відкритих коментарів, що пише, ПО ЯКИХ КЛЮЧАХ його питали (`dashboard.sync` бере `counts.get(<канал>, 0)`)."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.asked = []

    def get(self, key, default=None):
        self.asked.append(key)
        return super().get(key, default)


class _FakeDash:
    """Фейковий модуль дашборда: має `open_comments` і `push`; нічого не пише."""
    id = 'supabase-dashboard'

    def __init__(self, counts):
        self.counts = counts
        self.sent = []

    def fn(self, name):
        return (lambda ctx: self.counts) if name == 'open_comments' else (lambda *a, **k: None)


def _dashboard(cfg, rig):
    """Який ключ лічильника відкритих коментарів питає синк для кожної задачі, і який статус картки з цього виходить
    (`review` — коментарі є; `work` — нема). У лічильнику є значення для обох схем каналу, тож за статусом видно, яка схема."""
    import dashboard
    import registry
    channels = {'liga-shared': 3, 'dc/a-2': 2, 'deai/legacy/a-1': 5, 'deai/legacy/a-2': 7, 'deai/legacy/a-3': 11}
    counts = _Counts(channels)
    mod = _FakeDash(counts)
    sent = []

    def call(module, fn, ctx, cards=None, mode=None, timeout=None):
        if fn == 'open_comments':
            return counts                       # лічильник, що пише, які ключі питали
        sent.append({'fn': fn, 'mode': mode, 'cards': [{'id': c['id'], 'status': c['status'],
                                                        'comment_project': c.get('comment_project'),
                                                        'has_open_comments_field': 'open_comments' in c}
                                                       for c in cards or []]})
        return {'ok': len(cards or []), 'failed': {}}
    keep = {tid: t for tid, t in cfg['tasks'].items() if tid != 'p-1'}
    lines = []
    with mock.patch.object(registry, '_temp_roots', return_value=['/nonexistent-fixture-root']):
        dashboard.sync({'tasks': keep}, mod, {'secrets': {}}, identity=IDENTITY, log=lines.append, call=call)
    return {'counter_keys_asked': counts.asked, 'counts_given': channels, 'pushed': sent,
            'log': [rel(x, rig.home) for x in lines]}


def _inbox(cfg, rig, liga_space):
    """`inbox resolve` на ЛІГІ (dry-run): короткий префікс (3 символи) і повний id проєктного піна: код виходу, stdout/stderr
    (підпис джерела, канал, «Іт.N»). Проєктні піни дає записувач `list`."""
    import argparse as ap
    import deai_modules as dm
    import inbox
    import spaces
    pin = {'id': 'abcdef12deadbeef', 'text': 'Alpha pin', 'status': 'open', 'author': 'Beta', 'ts': 'x', 'fp': 'a/b/c',
           'meta': {}, 'bornV': 'it1'}
    out = {}
    for label, tid, prefixes in (('short_prefix', 'a-1', ['abc']), ('full_prefix', 'a-1', ['abcdef12']),
                                 ('a2_short_prefix', 'a-2', ['abc']), ('a2_full_prefix', 'a-2', ['abcdef12'])):
        rec = Rec({'list': [pin]})
        so, se = io.StringIO(), io.StringIO()
        with mock.patch.object(dm, 'call', rec), contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            dm.reset_caches()
            try:
                rc = inbox.cmd_resolve(ap.Namespace(task=tid, prefixes=prefixes, reason='ok', it=1, dry_run=True))
            finally:
                spaces.clear_request_space()
        out[label] = {'rc': rc, 'stdout': rel(so.getvalue(), rig.home).splitlines(),
                      'stderr': rel(se.getvalue(), rig.home).splitlines(),
                      'module_calls': [{'module': m, 'fn': fn} for m, fn, _c, _t in rec.calls]}
    dm.reset_caches()
    return out


def _comments_api(rig, cfg):
    """Відповіді справжнього сервера (ізольований прогін, як у 4d-3a): `comment-config`, `api/task`, `teams-mute` (шов `DC_TEAMS_FAKE`)."""
    import serve
    net = NoNet()
    fake = os.path.join(rig.home, 'teams-fake.json')
    _write(fake, {})
    env = {'HOME': rig.home, 'DEAI_HOME': rig.deai, 'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1',
           'DC_TEAMS_FAKE': fake, **_env_extra(rig)}
    out = {}
    with mock.patch.dict(os.environ, env), mock.patch.object(serve.urllib.request, 'urlopen', net):
        serve.deai_modules.reset_caches()
        with Server() as srv:
            cc = {}
            for tid in ('a-1', 'a-2'):
                st, body = _call(srv, 'GET', '/api/comment-config?ch=project&it=it1', task=tid)
                cc[tid] = {'status': st, 'keys': sorted(body or {}), 'ch': (body or {}).get('ch'),
                           'module': (body or {}).get('module'), 'channel': (body or {}).get('channel'),
                           'client': (body or {}).get('client'), 'config': (body or {}).get('config'),
                           'version': (body or {}).get('version')}
            out['comment_config'] = cc
            st, body = _call(srv, 'GET', '/api/comment-config?ch=local&it=it1', task='a-1')
            out['comment_config_local'] = {'status': st, 'keys': sorted(body or {})}
            out['task_comment_channel'] = {tid: _call(srv, 'GET', '/api/task', task=tid)[1].get('comment_channel')
                                           for tid in ('a-1', 'a-2', 'a-3')}
            mute = {}
            for tid in ('a-1', 'a-2'):
                st, body = _call(srv, 'GET', '/api/teams-mute', task=tid)
                mute[tid] = {'status': st, 'body': body}
            out['teams_mute_get'] = mute
            st, body = _call(srv, 'POST', '/api/teams-mute', task='a-1', body={'muted': True})
            with open(fake, encoding='utf-8') as fh:
                written = sorted(json.load(fh))
            st2, body2 = _call(srv, 'GET', '/api/teams-mute', task='a-1')
            st3, body3 = _call(srv, 'GET', '/api/teams-mute', task='a-2')
            out['teams_mute_post'] = {'status': st, 'ok': (body or {}).get('ok'), 'channel': (body or {}).get('channel'),
                                      'muted': (body or {}).get('muted'), 'fake_file_keys': written,
                                      'a1_after': {k: body2.get(k) for k in ('channel', 'muted', 'via')} if body2 else None,
                                      'a2_after': {k: body3.get(k) for k in ('channel', 'muted', 'via')} if body3 else None}
            out['urlopen_calls'] = net.calls
        serve.deai_modules.reset_caches()
    return out


def comments(tmp):
    import serve
    rig, space, cfg = liga(tmp, 'comments')
    out = {}
    with _stack(rig, _env_extra(rig)):
        out['space'] = scrub(space, rig.home)
        out['channels'] = _channels(serve, cfg, rig)
        out['route'] = _route(serve, cfg, space)
        out['project_comments'] = _project_comments(serve, cfg, rig, space)
        out['dashboard'] = _dashboard(cfg, rig)
        out['inbox'] = _inbox(cfg, rig, space)
    out['api'] = _comments_api(rig, cfg)
    return _hide(scrub(out, rig.home), (SB_KEY,))


# ---------------------------------------------------------------------------------- vcs

#: Тіло коміту несе час і хеш вмісту — мінливе; лишається форма.
_BODY_TIME = re.compile(r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}')
_BODY_HASH = re.compile(r'Хеш: [0-9a-f]{12}')


def _push_answer(seen):
    """`push`: запис ціль, мету (тема/тіло/автор), список файлів теки й README; відповідь «нічого не змінилось»."""
    def answer(ctx, target, src, meta):
        files = sorted(os.path.relpath(os.path.join(r, n), src) for r, _d, ns in os.walk(src) for n in ns)
        readme = None
        p = os.path.join(src, 'README.md')
        if os.path.isfile(p):
            with open(p, encoding='utf-8') as fh:
                readme = fh.read()
        msg = meta['message']
        subject, _, body = msg.partition('\n\n')
        seen.append({'target': dict(target), 'subject': subject,
                     'body_shape': _BODY_HASH.sub('Хеш: <hash>', _BODY_TIME.sub('<time>', body)),
                     'author': meta['author'], 'files': files, 'readme': readme})
        return {'ok': True, 'synced': False, 'changed': False, 'sha': None}
    return answer


def _nodate(obj):
    """Без полів `date` (час запису ітерації — мінливе)."""
    if isinstance(obj, dict):
        return {k: _nodate(v) for k, v in obj.items() if k != 'date'}
    if isinstance(obj, list):
        return [_nodate(v) for v in obj]
    return obj


def _status_answer(web):
    return {'behind': 0, 'behind_path': 0, 'unpushed': 0, 'on_remote': True, 'web': web, 'label': 'Example'}


def _pull_answer(note_author_key=None):
    """`pull`: кладе в `dst` макет (а з `note_author_key` — ще й заяву чужого автора, як макет колеги)."""
    def answer(ctx, target, dst, opts=None):
        _write(os.path.join(dst, 'index.html'), '<body>remote %s</body>' % target['path'])
        if note_author_key:
            _write(os.path.join(dst, '.canvas-state.json'),
                   {'task': 'n-1', 'source_it': 'it1', 'author': 'Beta Designer', 'author_key': note_author_key,
                    'published': False, 'publish_url': None, 'published_at': None})
        return {'found': True, 'last_commit': {'author': 'Beta Designer', 'time': 1}}
    return answer


def _vcs_ctx(serve, rig):
    import deai_modules as dm
    prov = dm.provider('vcs', rig.registry())
    v = serve.vcs_provider()
    return {'provider': type(prov).__name__, 'tuple_len': len(v), 'module': v[0].id, 'legacy': v[2],
            'ctx': san_ctx(v[1])}


def _mirrors(serve, cfg, rig, v):
    """`vcs_target` + `vcs_mirror_dir` для зразкових адрес (SSH, https, вкладений шлях, `ssh://`) — і для `gitlab`, і для `vcs` задачі."""
    rows = []
    cases = [(tid, t) for tid, t in cfg['tasks'].items() if tid in ('a-1', 'a-2', 'a-3')]
    cases += [('v-ssh', {'vcs': {'repo': REPO_UNITED, 'path': 'mockup/{task}'}}),
              ('v-seo', {'vcs': {'repo': REPO_SEO}}),
              ('v-https', {'vcs': {'repo': REPO_HTTPS, 'branch': 'dev'}}),
              ('v-nested', {'vcs': {'repo': REPO_NESTED}})]
    for tid, task in cases:
        tgt = serve.vcs_target(cfg, tid, task, v[1].get('settings') or {})
        row = {'task': tid, 'target': scrub(tgt, rig.home)}
        row['mirror_dir'] = _outcome(lambda: rel(serve.vcs_mirror_dir(tgt, vcs=v), rig.home), rig.home) if tgt else None
        rows.append(row)
    return rows


def _texts(serve, cfg, rig, v):
    """Усі споживачі «текстів ЛІГИ»: тема коміту й README (`gitlab_sync`), `web`/`label` (`gitlab_status`), примітка «оновлення з …»
    (`gitlab_pull`), автокоміт (`autosync`), примітка форку (`_task_new_write`), рядок `bin/state.py`. Усе — з записувачем модуля."""
    import deai_modules as dm
    import state
    out = {}
    seen_push = []
    rec = Rec({'push': _push_answer(seen_push), 'pull': _pull_answer()})
    rec.answers['status'] = lambda ctx, t: _status_answer('https://example.com/web/' + t['path'])
    committed = []

    def autocommit(task_dir, msg, push=None):
        committed.append(rel(msg, rig.home))
        return {'sha': 'abc1234', 'pushed': False}
    with mock.patch.object(dm, 'call', rec), mock.patch.object(serve, 'git_autocommit', autocommit):
        dm.reset_caches()
        tasks = cfg['tasks']
        gl = {tid: serve.vcs_target(cfg, tid, tasks[tid], v[1].get('settings') or {}) for tid in ('a-1', 'a-2', 'a-3', 'p-1')}
        # gitlab_sync: двосторінкова a-1 (README) і односторінкова a-2
        for tid in ('a-1', 'a-2'):
            seen_push.clear()
            res = _outcome(lambda: _jsonable(serve.gitlab_sync(tid, tasks[tid], gl[tid], 'it1', vcs=v)), rig.home)
            out.setdefault('sync', {})[tid] = {'outcome': res, 'push': scrub(list(seen_push), rig.home)}
        # gitlab_status: ssh (web з адреси), https (web нема), вкладений
        meta = {'iterations': [{'id': 'it1'}]}
        out['status'] = {tid: _outcome(lambda: _jsonable(serve.gitlab_status(tasks[tid], gl[tid], meta, 'it1', vcs=v)), rig.home)
                         for tid in ('a-1', 'a-2', 'a-3')}
        # без постачальника в аргументі (знаходить сам)
        out['status_self_lookup'] = _outcome(
            lambda: _jsonable(serve.gitlab_status(tasks['a-1'], gl['a-1'], meta, 'it1')), rig.home)
        # автосинк: тема автокоміту і тема коміту модуля
        seen_push.clear()
        res = _outcome(lambda: _jsonable(serve.autosync('a-1', tasks['a-1'], gl['a-1'])), rig.home)
        out['autosync'] = {'outcome': res, 'commit_messages': list(committed),
                           'push_subjects': [p['subject'] for p in seen_push]}
        # gitlab_pull: підпис джерела в примітці нової ітерації
        res = _outcome(lambda: _nodate(_jsonable(serve.gitlab_pull(tasks['p-1'], gl['p-1'], vcs=v))), rig.home)
        with open(os.path.join(tasks['p-1']['dir'], 'iterations.json'), encoding='utf-8') as fh:
            its = json.load(fh)['iterations']
        out['pull'] = {'outcome': res, 'notes': [i.get('note') for i in its]}
        # примітка форку нової задачі: клон макета колеги (чужий автор) → друга ітерація «продовження макета з …»
        rec.answers['pull'] = _pull_answer(OTHER_KEY)
        ncfg = {'tasks': {}, 'gitlab_ssh_key': cfg.get('gitlab_ssh_key')}
        tdir = os.path.join(rig.home, 'work', 'n-1')
        res = _outcome(lambda: _jsonable(serve._task_new_write(
            ncfg, 'n-1', 'New demo', '', 'seo', {'repo': REPO_UNITED, 'path': 'mockup/n-1'}, None, tdir, None, (), None, True)),
            rig.home)
        with open(os.path.join(tdir, 'iterations.json'), encoding='utf-8') as fh:
            its = json.load(fh)['iterations']
        out['task_new_fork'] = {'outcome': res, 'notes': [i.get('note') for i in its]}
        # рядок `bin/state.py` про git: підпис і статус (порти канвасу не опитуємо)
        so = io.StringIO()
        with mock.patch.object(state, 'find_canvas_port', lambda *a, **k: None), contextlib.redirect_stdout(so):
            try:
                rc = state.main(['--task', 'a-1'])
            finally:
                import spaces
                spaces.clear_request_space()
        lines = [rel(x, rig.home) for x in so.getvalue().splitlines()]
        out['state'] = {'rc': rc, 'git_lines': [x for x in lines if 'GitLab' in x or x.startswith('Git')]}
        dm.reset_caches()
    return out


NODE_FORM = r"""
import { pathToFileURL } from 'node:url';
const inp = JSON.parse(await new Promise((res) => { let s = ''; process.stdin.on('data', (d) => { s += d; }); process.stdin.on('end', () => res(s)); }));
const m = await import(pathToFileURL(inp.model).href);
const sp = inp.space;
console.log(JSON.stringify({
  has_vcs: m.hasVcs(sp), is_legacy_vcs: m.isLegacyVcs(sp), with_repo: m.hasVcs(sp) && !m.isLegacyVcs(sp),
  label_empty: m.vcsLabel('', sp), label_git: m.vcsLabel('Git', sp), brand_empty: m.vcsBrand('', sp),
  fail_key_target: m.vcsFailKey('vcs-bad-target', sp), clones: m.taskCreateClones(sp, {}),
  has_notify: m.hasNotify(sp), has_publish: m.hasPublish(sp), space_keys: Object.keys(sp).sort(),
}));
"""


def _form(rig):
    """Прапорець форми «Нова задача» й підписи: `app/spaces-model.js` на записі ЛІГИ з відповіді справжнього сервера `/api/spaces`."""
    import serve
    net = NoNet()
    env = {'HOME': rig.home, 'DEAI_HOME': rig.deai, 'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1', **_env_extra(rig)}
    with mock.patch.dict(os.environ, env), mock.patch.object(serve.urllib.request, 'urlopen', net):
        serve.deai_modules.reset_caches()
        with Server() as srv:
            st, body = _call(srv, 'GET', '/api/spaces')
        serve.deai_modules.reset_caches()
    row = next(s for s in body['spaces'] if s['id'] == SPACE_ID)
    payload = json.dumps({'model': os.path.join(ROOT, 'app', 'spaces-model.js'), 'space': row})
    r = subprocess.run(['node', '--input-type=module', '-e', NODE_FORM], input=payload, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError('node: ' + r.stderr[-500:])
    return {'status': st, 'space_row': scrub(row, rig.home), 'capabilities': row.get('capabilities'),
            'model': json.loads(r.stdout), 'urlopen_calls': net.calls}


def vcs(tmp):
    import serve
    rig, space, cfg = liga(tmp, 'vcs')
    net = NoNet()
    out = {}
    with _stack(rig, _env_extra(rig), mock.patch.object(serve.urllib.request, 'urlopen', net)):
        import deai_modules as dm
        dm.reset_caches()
        out['space'] = scrub(space, rig.home)
        out['provider'] = _vcs_ctx(serve, rig)
        v = serve.vcs_provider()
        out['mirrors'] = _mirrors(serve, cfg, rig, v)
        out['texts'] = _texts(serve, cfg, rig, v)
        out['mirrors_base'] = rel(serve._mirrors_base(), rig.home)
        dm.reset_caches()
    out['form'] = _form(rig)
    out['urlopen_calls'] = net.calls
    return scrub(out, rig.home)


# ---------------------------------------------------------------------------------- збирання

def make():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d3b-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire:
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.17.0', 'source_commit': _source_commit(),
                             'generator': 'tests/make_before_4d3b.py', 'volatile_stripped': []}}
            snap['comments'] = comments(tmp)
            snap['vcs'] = vcs(tmp)
            snap['non_loopback_attempts'] = wire.count
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.17.0 = `6906621`, тег `v0.17.0`). Зашито, щоб прогін на новому коді не видавав себе
    за «до»."""
    return '6906621'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` цієї теки відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — лише коли
    у `ROOT` нема `.git` зовсім (заморожена копія з `git archive`: довіряємо рецепту з докстрінга). Рецепт —
    `make_before_4d3a._code_differs_from_source`, але з ІНШИМ коммітом-джерелом (тому окрема копія): закрито за замовчуванням
    всередині git-теки (нема `git`, збій, чужий toplevel, нема коміту, ненульовий `git diff`, новий файл у `app/`/`bin/`)."""
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
    if os.path.realpath(args.out) == os.path.realpath(OUT_DEFAULT) and _code_differs_from_source():
        print('⛔ make_before_4d3b: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
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
