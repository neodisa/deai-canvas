#!/usr/bin/env python3
"""Генератор знімка поведінки простору ЛІГА на 0.18.0 для ролі `publish`: `tests/fixtures/liga-migration/before-4d3c.json`
(етап 4d-3c, Task 1).

Знімок знято ДО змін коду (код = 0.18.0, коміт `6ce8e61`, тег `v0.18.0`) і лишається в репо як еталон паритету третього кроку
міграції ЛІГИ: після 0.19 ЛІГА публікує так само для людини (ті самі проєкти `pv-…`, скоуп, URL, пароль превʼю, побічні дії), хоч
`publish` стає ЯВНИМ модулем `space.json` (`vercel-publish` з `compat: "design-canvas"`). Тести наступних задач
(`tests/test_liga_migrate_c.py`) читають JSON, а не переганяють цей генератор. Генератор лишається поруч як ДОКУМЕНТАЦІЯ — як саме
знято (запуск на НОВОМУ коді дасть не «до», а «після»: еталон не перезаписувати).

Спільні помічники (`Rig`, `Server`, `Recorder`, `NoNet`, `SocketTripwire`, `scrub`, `rel`, `CLEAN`, `_write`, вигадані константи)
ІМПОРТУЮТЬСЯ з `make_before_4d3a.py`/`make_before_4d3b.py` (`liga`-стенд тут власний — публікації потрібна задача з опублікованими
ітераціями): друга копія розійшлась би.

Два стенди, на кожному ОДИН набір сценаріїв:
  * `unmigrated` — ЛІГА, нічого не мігровано (запис реєстру `legacy: true`, `integrations: true`, `space.json` нема);
  * `ab` — ЛІГА після 4d-3a + 4d-3b (генератор кличе `liga_migrate.run_all()` КОДОМ 0.18 у тимчасовому домі).

Що знято (усе — у тимчасових теках, без мережі й без справжніх Vercel, Supabase, Jira чи Teams):
  * `publish` — 13 сценаріїв `POST /api/publish` (`first`, `second`, `pw_default`, `pw_task`, `pw_root`, `build_only`, `no_node`,
    `err_login`, `err_scope`, `err_no_url`, `protection`, `comments_on`, `comments_off`): тіло відповіді (ПОРЯДОК ключів — список
    пар), записи `tasks.json` (`vercel_project`, `vercel_scope`) і `iterations.json` (`publish_url`, `published_at`→`<time>`,
    `publish_verified`; `publish_remote` відсутній), argv фальшивого `npx` (`tests/fake_npx.py` через `serve._node_bin`), мітка
    `build` у `manifest.json`, шиті сторінки (гейт `authgate`, пароль, канал/ключі коментарів), шпигуни побічних дій
    (`serve._registry_push`, `Handler._overview_sync`, `serve.git_autocommit` — порядок і аргументи). Перевірка превʼю —
    підмінений `_fetch_page` модуля `vercel-publish` (мережі нема). `first` мінтить `pv-…`: `secrets.choice` під час мінту дає
    детерміновані цифри (`12345678`) — інакше імʼя в знімку було б випадковим;
  * `task` — `GET /api/task`: `preview_password`, `preview_password_custom`, `preview_gate`, відсутність `publish_gate`/
    `publish_share_url`; `password` — `POST /api/preview-password` (200 + запис у `tasks.json`; 400; 409 для простору без ЛІГИ);
    `api_spaces` — `capabilities`, `compat` запису ЛІГИ; `modules_card` — картка `vercel-publish` з `GET /api/modules`;
    `js` — читання `app/spaces-model.js`/`app/bar-model.js` через `node` на записі `/api/spaces` і відповіді `/api/task`:
    `isLegacyPublish`, `pwView`, `previewTarget`, `copyUrl` (`#k=<пароль>&p=<сторінка>`), `publishReaction`, `barModel` (рядок `pubpw`).

Виключено з JSON усе мінливе: час (`published_at` → `<time>`), абсолютні шляхи (тека → `~/…`/`<tmp>`), значення секретів (лише
булеві «є в сторінці»). Прогін двічі дає той самий байт-у-байт JSON.

Запуск (з кореня репо):  python3 -B tests/make_before_4d3c.py [--out ШЛЯХ]   (типово — `tests/fixtures/liga-migration/before-4d3c.json`)

⚠️ ГЕНЕРАТОР РОБИТЬ ЗНІМОК v0.18.0 (код — коміт 6ce8e61) і мусить запускатись проти ЗАМОРОЖЕНОЇ копії старого коду, а не
проти робочої теки (з Task 2–7 `app/`/`bin/` змінюються — і знімок з міткою `source_commit: 6ce8e61` містив би дані «після»).
Як:
    D=$(mktemp -d) && git archive v0.18.0 | tar -x -C "$D"      # заморожена копія коду v0.18.0
    cp tests/make_before_4d3c.py "$D/tests/"                    # лише сам генератор (він бере ROOT від свого розташування)
    python3 -B "$D/tests/make_before_4d3c.py" --out tests/fixtures/liga-migration/before-4d3c.json
Прогін на новому коді — лише як документація: запис у типовий шлях еталона з робочої теки, де `app/`/`bin/` відрізняються від
6ce8e61, генератор ВІДМОВЛЯЄ (код виходу 2); копія з `git archive` — не git-тека, там довіряємо рецепту.

⛔ Ізоляція: власні тимчасові `HOME` і `DEAI_HOME` (звідси `~/.deai` і `~/.claude/pipeline-feedback/` — тимчасові), чисте
оточення (змінні конфігу прибрані на час прогону; потрібні виставляються ЛИШЕ тут, через `mock.patch.dict`, вигаданими значеннями),
жодної мережі (розтяжка сокетів + `urllib.request.urlopen` — заглушка-лічильник); справжній `~/.deai` стереже `spaces_guard`.
"""
import argparse
import contextlib
import http.client
import itertools
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)

# ⛔ Спільне — з генераторів 4d-3a/4d-3b (друга копія розійшлась би).
from make_before_4d3a import (CLEAN, REPO_SEO, REPO_UNITED, SB_KEY, SB_URL, SPACE_ID, NoNet, Rig, Server,  # noqa: E402
                              SocketTripwire, _write, rel, scrub)
from make_before_4d3b import _env_extra  # noqa: E402
import fake_npx  # noqa: E402

OUT_DEFAULT = os.path.join(_HERE, 'fixtures', 'liga-migration', 'before-4d3c.json')

#: Ідентифікатори сценаріїв `publish` — рівно ці (порядок — порядок прогону: `second` іде ПІСЛЯ `first` на тому самому світі).
SCENARIOS = ('first', 'second', 'pw_default', 'pw_task', 'pw_root', 'build_only', 'no_node', 'err_login', 'err_scope',
             'err_no_url', 'protection', 'comments_on', 'comments_off')
STANDS = ('unmigrated', 'ab')

TID = 'a-1'
PROJECT = 'pv-12345678'            # детермінований мінт (`secrets.choice` підмінено лише на час мінту)
SCOPE = 'team_x'
URL_D = 'https://pv-12345678-abc.vercel.app'
URL_A = 'https://pv-12345678.vercel.app'
PW_TASK = 'taskpw-alpha'
PW_ROOT = 'rootpw-alpha'
#: Успішний сценарій фальшивого `npx` (ті самі відповіді, що в знімку 0.8.0 і `tests/test_publish_module.py`).
NPX_OK = {'link': {'code': 0, 'org': SCOPE},
          'deploy': {'code': 0, 'stdout': 'Production: %s\nAliased: %s\n' % (URL_D, URL_A)},
          'inspect': {'code': 0, 'stdout': URL_A + '\n'}, 'list': {'code': 0, 'stdout': '{"deployments": []}'}}
#: Що модуль бачить на адресі превʼю (шов `_fetch_page`): гейт на місці / захист Vercel (302 на SSO).
PAGE_GATE = (200, '', '<html><div id="authgate"></div></html>')
PAGE_SSO = (302, 'https://vercel.com/sso-api?next=x', '')

#: Вигадані джерела сторінок: два макети ітерації `it1` і односторінкова `it2`.
SOURCE_PAGES = {'it1/alpha/index.html': 'Альфа', 'it1/gamma/index.html': 'Гамма', 'it2/index.html': 'Друга ітерація'}


# ---------------------------------------------------------------------------------- стенд

def _tasks_cfg(rig, with_sb=True, task_extra=None, root_extra=None):
    """Корінь старого `tasks.json`: одна задача `a-1` з опублікованими ітераціями (теку `work/a-1` створює `_world`)."""
    w = os.path.join(rig.home, 'work')
    task = {'dir': os.path.join(w, TID), 'title': 'Alpha demo', 'jira': 'DEMO-1', 'track': 'seo', **(task_extra or {})}
    cfg = {'gitlab_ssh_key': '~/.ssh/example', 'design_work_root': os.path.join(w, 'shared'),
           'design_work_roots': {'united': os.path.join(w, 'united'), 'custom-x': os.path.join(w, 'custom')},
           'profile_repos': {'united': REPO_UNITED, 'seo': REPO_SEO}, 'jira_base': 'https://jira.example.com',
           'tasks': {TID: task}, 'current': TID, **(root_extra or {})}
    if with_sb:
        cfg.update(supabase_url=SB_URL, supabase_key=SB_KEY)
    return cfg


def _fresh_task_files(rig):
    """Тека задачі з нуля: джерела сторінок, `pages.json`, `iterations.json` (обидві ітерації опубліковані), без `publish/`."""
    import shutil
    task_dir = os.path.join(rig.home, 'work', TID)
    shutil.rmtree(task_dir, ignore_errors=True)
    for relp, title in SOURCE_PAGES.items():
        _write(os.path.join(task_dir, 'iterations', relp),
               '<!DOCTYPE html><html><head><title>%s</title></head><body><h1>%s</h1></body></html>' % (title, relp))
    _write(os.path.join(task_dir, 'iterations', 'it1', 'pages.json'),
           {'pages': [{'id': 'alpha', 'name': 'Альфа'}, {'id': 'gamma', 'name': 'Гамма'}]})
    _write(os.path.join(task_dir, 'iterations.json'),
           {'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'first', 'published': True},
                           {'id': 'it2', 'date': '02.01.2026 10:00', 'note': 'second', 'published': True}],
            'publish_url': None})
    return task_dir


def _stand(tmp, name, migrate):
    """Стенд ЛІГИ → `rig`. `migrate` — крок 4d-3a + 4d-3b КОДОМ 0.18 (`liga_migrate.run_all()`); інакше нічого не мігровано."""
    rig = Rig(tmp, name)
    cfg = _tasks_cfg(rig)
    _write(rig.tasks_path, cfg)
    _write(os.path.join(rig.home, '.ssh', 'example'), 'not a real key\n')
    rig.registry()
    _fresh_task_files(rig)
    if migrate:
        import liga_migrate as lm
        with rig.activate():
            res = [(m, st) for m, st, _info in lm.run_all()]
        if res != [('liga-4d3a', 'done'), ('liga-4d3b', 'done')]:
            raise RuntimeError('стенд ab: міграція не відбулась: %r' % (res,))
    return rig


def _env(rig):
    """Оточення прогону сервера: ізольований шлях задач (як у 4d-3a/4d-3b), особа машини, дзеркала у теці стенду."""
    return {'HOME': rig.home, 'DEAI_HOME': rig.deai, 'DC_TASKS_FILE': rig.tasks_path, 'DC_NO_OVERVIEW': '1', **_env_extra(rig)}


# ---------------------------------------------------------------------------------- HTTP

def _raw(srv, method, path, task=None, body=None, hook=None):
    """`(status, тіло)`: JSON; `hook` (наприклад, `object_pairs_hook`) зберігає ПОРЯДОК ключів; не JSON → `None`."""
    headers = {'Origin': 'http://127.0.0.1:%d' % srv.port}
    if task:
        headers['X-Canvas-Task'] = task
    raw = None
    if body is not None:
        raw = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    conn = http.client.HTTPConnection('127.0.0.1', srv.port, timeout=60)
    try:
        conn.request(method, path, body=raw, headers=headers)
        r = conn.getresponse()
        txt = r.read().decode('utf-8', 'replace')
        try:
            return r.status, json.loads(txt, object_pairs_hook=hook)
        except ValueError:
            return r.status, None
    finally:
        conn.close()


def _pairs(pairs):
    return [[k, v] for k, v in pairs]


# ---------------------------------------------------------------------------------- publish

class _Mint:
    """`secrets.choice` лише для цифр мінту імені `pv-NNNNNNNN`: детерміновано `12345678`; решта виклики — справжні."""

    def __init__(self):
        self._real = secrets.choice
        self._digits = itertools.cycle('12345678')

    def __call__(self, seq):
        return next(self._digits) if seq == '0123456789' else self._real(seq)


_P = re.compile(r'P=("(?:[^"\\]|\\.)*");')
_CH = re.compile(r'"channel"\s*:\s*"([^"]*)"')


def _pages(task_dir, home):
    """Шиті сторінки `publish/`: для кожної HTML — гейт, пароль (літерал `P=…;`), шар коментарів, канал, чи є адреса/ключ Supabase
    (значення секретів у знімок не йдуть — лише булеві); склад `comment-layer/`, сторінки з маніфесту, мітка `build`."""
    pub = os.path.join(task_dir, 'publish')
    pages = {}
    for dirpath, _dirs, files in sorted(os.walk(pub)):
        for fn in sorted(files):
            if not fn.endswith('.html'):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, encoding='utf-8', errors='replace') as fh:
                text = fh.read()
            pm, cm = _P.search(text), _CH.search(text)
            pages[os.path.relpath(p, pub)] = {
                'authgate': 'id="authgate"' in text, 'password': json.loads(pm.group(1)) if pm else None,
                'comment_layer': 'comment-layer' in text, 'channel': cm.group(1) if cm else None,
                'has_supabase_url': SB_URL in text, 'has_supabase_key': SB_KEY in text}
    layer = os.path.join(pub, 'comment-layer')
    with open(os.path.join(pub, 'manifest.json'), encoding='utf-8') as fh:
        man = json.load(fh)
    return {'html': pages, 'comment_layer_files': sorted(os.listdir(layer)) if os.path.isdir(layer) else None,
            'manifest_pages': [p.get('path') for p in man.get('pages', [])]}, man.get('build')


def _publish_once(rig, srv, npx_scenario, body=None, page=PAGE_GATE, npx=True, mint=False):
    """Одна публікація `POST /api/publish` на ПОТОЧНОМУ світі (задачу/файли готує викликач). → знімок сценарію."""
    import deai_modules as dm
    import serve
    npxdir = os.path.join(rig.home, 'fake-npx')
    npx_path = fake_npx.make(npxdir, npx_scenario) if npx else None
    task_dir = os.path.join(rig.home, 'work', TID)
    calls, fetched = [], []

    def fetch(url):
        fetched.append(url)
        return page
    dm.reset_caches()
    module_globals = dm.catalog()['vercel-publish'].fn('publish').__globals__
    with contextlib.ExitStack() as st:
        st.enter_context(mock.patch.dict(module_globals, {'_fetch_page': fetch}))
        st.enter_context(mock.patch.object(serve, '_node_bin', lambda name='npx': npx_path))
        st.enter_context(mock.patch.object(serve, '_registry_push', lambda tid: calls.append(['registry_push', tid]) or False))
        st.enter_context(mock.patch.object(serve, 'git_autocommit',
                                           lambda d, msg, push=None: calls.append(['git_autocommit', rel(d, rig.home), msg])))
        st.enter_context(mock.patch.object(serve.Handler, '_overview_sync', lambda handler: calls.append(['overview_sync'])))
        st.enter_context(mock.patch.object(serve, 'server_code_staleness', lambda *a, **kw: None))
        if mint:
            st.enter_context(mock.patch.object(secrets, 'choice', _Mint()))
        status, resp = _raw(srv, 'POST', '/api/publish', task=TID, body=body or {}, hook=_pairs)
    with open(rig.tasks_path, encoding='utf-8') as fh:
        task = json.load(fh)['tasks'][TID]
    with open(os.path.join(task_dir, 'iterations.json'), encoding='utf-8') as fh:
        meta = json.load(fh)
    pages, build = _pages(task_dir, rig.home)
    snap = {'response': {'status': status, 'pairs': resp},
            'tasks_after': {'vercel_project': task.get('vercel_project'), 'vercel_scope': task.get('vercel_scope')},
            'iterations_after': {'publish_url': meta.get('publish_url'),
                                 'published_at': '<time>' if meta.get('published_at') else None,
                                 'publish_verified': meta.get('publish_verified'),
                                 'publish_remote': 'present' if 'publish_remote' in meta else 'absent'},
            'npx_argv': [c['argv'] for c in fake_npx.calls(npxdir)] if npx else [],
            'build': build, 'pages': pages, 'spies': {'calls': calls, 'fetched_urls': fetched}}
    return scrub(snap, rig.home)


def _reset_world(rig, task_extra=None, root_extra=None, with_sb=True):
    """Світ сценарію з нуля: `tasks.json` (скидає `vercel_*`, пароль задачі/кореня), `iterations.json`, сторінки; без `publish/`."""
    _write(rig.tasks_path, _tasks_cfg(rig, with_sb=with_sb, task_extra=task_extra, root_extra=root_extra))
    _fresh_task_files(rig)


def publish(rig, srv):
    """13 сценаріїв `POST /api/publish`. `first` мінтить проєкт і скоуп; `second` — друга публікація ТОГО САМОГО світу (без скидання);
    усі решта — на чистому світі з уже відомим проєктом (`vercel_project`), щоб мінту не було."""
    out = {}
    known = {'vercel_project': PROJECT}                      # проєкт відомий, скоуп — ні (як після першої публікації старого коду)
    _reset_world(rig)
    out['first'] = _publish_once(rig, srv, NPX_OK, mint=True)
    out['second'] = _publish_once(rig, srv, NPX_OK)          # той самий світ: проєкт і скоуп уже в tasks.json
    _reset_world(rig, task_extra=known)
    out['pw_default'] = _publish_once(rig, srv, NPX_OK)
    _reset_world(rig, task_extra={**known, 'preview_password': PW_TASK})
    out['pw_task'] = _publish_once(rig, srv, NPX_OK)
    _reset_world(rig, task_extra=known, root_extra={'preview_password': PW_ROOT})
    out['pw_root'] = _publish_once(rig, srv, NPX_OK)
    _reset_world(rig, task_extra=known)
    out['build_only'] = _publish_once(rig, srv, NPX_OK, body={'build_only': True})
    _reset_world(rig, task_extra=known)
    out['no_node'] = _publish_once(rig, srv, None, npx=False)
    _reset_world(rig, task_extra=known)
    out['err_login'] = _publish_once(rig, srv, {**NPX_OK, 'deploy': {'code': 1, 'stderr': 'Error: Please run vercel login'}})
    _reset_world(rig, task_extra=known)
    out['err_scope'] = _publish_once(rig, srv, {**NPX_OK, 'deploy': {'code': 1, 'stderr': "Error: You don't have access to the team 'x'"}})
    _reset_world(rig, task_extra=known)
    out['err_no_url'] = _publish_once(rig, srv, {**NPX_OK, 'deploy': {'code': 0, 'stdout': 'Deployed, but nothing to see\n'}})
    _reset_world(rig, task_extra=known)
    out['protection'] = _publish_once(rig, srv, NPX_OK, page=PAGE_SSO)
    _reset_world(rig, task_extra={**known, 'comment_project': 'liga-shared'})
    out['comments_on'] = _publish_once(rig, srv, NPX_OK)
    _reset_world(rig, task_extra=known, with_sb=False)
    out['comments_off'] = _publish_once(rig, srv, NPX_OK)
    if tuple(out) != SCENARIOS:
        raise RuntimeError('набір сценаріїв розійшовся з SCENARIOS: %r' % (list(out),))
    return out


# ---------------------------------------------------------------------------------- решта секцій

def _task_view(srv):
    """`GET /api/task` — лише те, що стосується публікації."""
    st, body = _raw(srv, 'GET', '/api/task', task=TID)
    return {'status': st, 'preview_password': body.get('preview_password'),
            'preview_password_custom': body.get('preview_password_custom'), 'preview_gate': body.get('preview_gate'),
            'publish_url': body.get('publish_url'), 'has_publish_gate': 'publish_gate' in body,
            'has_publish_share_url': 'publish_share_url' in body, 'has_publish_remote': 'publish_remote' in body,
            'space_capabilities_publish': (body.get('space') or {}).get('capabilities', {}).get('publish')}, body


def task_and_password(rig, srv):
    """Секції `task` і `password`. Світ: після публікації з типовим паролем; далі пароль задачі міняється з екрана.
    ⛔ Другий запис реєстру (`plain`, без ЛІГИ) лише для 409: на час запиту він — поточний, потім повертаємо ЛІГУ."""
    _reset_world(rig, task_extra={'vercel_project': PROJECT})
    task = {}
    task['fresh'], _ = _task_view(srv)
    _publish_once(rig, srv, NPX_OK)
    task['published'], published_body = _task_view(srv)
    pw = {}
    st, body = _raw(srv, 'POST', '/api/preview-password', task=TID, body={'password': 'newpw-alpha'}, hook=_pairs)
    with open(rig.tasks_path, encoding='utf-8') as fh:
        saved = json.load(fh)['tasks'][TID].get('preview_password')
    pw['set'] = {'status': st, 'pairs': body, 'saved_in_tasks_json': saved}
    task['after_change'], _ = _task_view(srv)
    st, body = _raw(srv, 'POST', '/api/preview-password', task=TID, body={'password': ''}, hook=_pairs)
    with open(rig.tasks_path, encoding='utf-8') as fh:
        saved = json.load(fh)['tasks'][TID].get('preview_password')
    pw['clear'] = {'status': st, 'pairs': body, 'saved_in_tasks_json': saved}
    st, body = _raw(srv, 'POST', '/api/preview-password', task=TID, body={'password': 'x' * 200}, hook=_pairs)
    pw['too_long'] = {'status': st, 'pairs': body}
    # 409: простір без ЛІГИ (`plain`: не legacy, без інтеграцій → публікує модуль, пароль ЛІГИ там не має сенсу)
    plain_dir = os.path.join(os.path.dirname(rig.space_dir), 'plain-space')
    os.makedirs(plain_dir, exist_ok=True)
    reg_path = os.path.join(rig.deai, 'spaces.json')
    with open(reg_path, encoding='utf-8') as fh:
        keep = fh.read()
    reg = json.loads(keep)
    reg['spaces'].append({'id': 'plain', 'path': plain_dir, 'legacy': False, 'integrations': False})
    reg['current'] = 'plain'
    _write(reg_path, reg)
    try:
        st, body = _raw(srv, 'POST', '/api/preview-password', body={'password': 'abcd'}, hook=_pairs)
    finally:
        _write(reg_path, keep)
    pw['no_liga_space'] = {'status': st, 'pairs': body}
    return task, pw, published_body


NODE_JS = r"""
import { pathToFileURL } from 'node:url';
const inp = JSON.parse(await new Promise((res) => { let s = ''; process.stdin.on('data', (d) => { s += d; }); process.stdin.on('end', () => res(s)); }));
const m = await import(pathToFileURL(inp.model).href);
const b = await import(pathToFileURL(inp.bar).href);
const sp = inp.space, task = inp.task;
const view = m.pwView(task, sp);
const target = m.previewTarget(task, sp);
const base = { mode: 'layout', view: 'grid', vp: 'desktop', vpw: '', taskId: 'A-1', iterLabel: 'It1', iterNote: 'n', hasIteration: true,
  flowRaw: true, pagesError: '', flowError: '', gl: 'sync', published: true, pubStale: false, iterPub: true, pagePub: true,
  iterOnGl: true, tasksErr: '', right: null };
const bar = b.barModel({ ...base, space: sp, ...view });
const items = [...bar.zone1, ...bar.zone2, ...bar.zone3].flatMap((x) => [x, ...(Array.isArray(x.items) ? x.items : [])]);
const pub = items.find((x) => x.id === 'publish') || null;
console.log(JSON.stringify({
  is_legacy_publish: m.isLegacyPublish(sp), is_vercel_publish: m.isVercelPublish(sp), is_remote_publish: m.isRemotePublish(task, sp),
  pw_view: view, preview_target: target,
  copy_url: m.copyUrl(target, { origin: 'http://canvas.example.com', pageId: 'alpha', password: task.preview_password }),
  publish_reaction: m.publishReaction({ url: task.publish_url }, sp, true),
  publish_reaction_other_task: m.publishReaction({ url: task.publish_url }, sp, false),
  bar_pubpw: items.find((x) => x.id === 'pubpw') || null,
  bar_item_ids: items.map((x) => x.id), bar_publish: pub ? { legacy: pub.legacy, notes: pub.notes } : null,
}));
"""


def js_section(space_row, task_body):
    payload = json.dumps({'model': os.path.join(ROOT, 'app', 'spaces-model.js'), 'bar': os.path.join(ROOT, 'app', 'bar-model.js'),
                          'space': space_row, 'task': task_body})
    r = subprocess.run(['node', '--input-type=module', '-e', NODE_JS], input=payload, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError('node: ' + r.stderr[-500:])
    return json.loads(r.stdout)


def api_sections(rig, srv, published_body):
    """`api_spaces` (запис ЛІГИ), `modules_card` (картка `vercel-publish`), `js`."""
    st, body = _raw(srv, 'GET', '/api/spaces')
    row = next(s for s in body['spaces'] if s['id'] == SPACE_ID)
    api_spaces = {'status': st, 'capabilities': row.get('capabilities'), 'compat': row.get('compat')}
    st, mods = _raw(srv, 'GET', '/api/modules?space=%s' % SPACE_ID)
    card = next((m for m in mods['modules'] if m.get('id') == 'vercel-publish'), None)
    modules_card = {'status': st, 'card': scrub(card, rig.home)}
    return api_spaces, modules_card, js_section(row, published_body)


def stand(tmp, name):
    import deai_modules
    import serve
    rig = _stand(tmp, name, migrate=(name == 'ab'))
    net = NoNet()
    with mock.patch.dict(os.environ, _env(rig)), mock.patch.object(serve.urllib.request, 'urlopen', net):
        deai_modules.reset_caches()
        with Server() as srv:
            out = {'publish': publish(rig, srv)}
            out['task'], out['password'], published_body = task_and_password(rig, srv)
            out['api_spaces'], out['modules_card'], out['js'] = api_sections(rig, srv, published_body)
        deai_modules.reset_caches()
    if net.calls:
        raise RuntimeError('urlopen: %d' % net.calls)
    return scrub(out, rig.home)


# ---------------------------------------------------------------------------------- збирання

def make():
    """Збирає знімок у тимчасовому оточенні; справжній `~/.deai` стереже `spaces_guard`."""
    import spaces_guard
    real = spaces_guard.snapshot()
    with tempfile.TemporaryDirectory(prefix='before-4d3c-') as tmp:
        tmp = os.path.normpath(tmp)
        home = os.path.join(tmp, 'home')
        os.makedirs(home)
        with mock.patch.dict(os.environ, {'HOME': home}), SocketTripwire() as wire:
            for name in CLEAN:
                os.environ.pop(name, None)
            snap = {'meta': {'version': '0.18.0', 'source_commit': _source_commit(),
                             'generator': 'tests/make_before_4d3c.py', 'volatile_stripped': []}}
            snap['stands'] = {name: stand(tmp, name) for name in STANDS}
            snap['non_loopback_attempts'] = wire.count
    spaces_guard.assert_untouched(real)
    return snap


def _source_commit():
    """Коміт коду, з якого знято знімок (код 0.18.0 = `6ce8e61`, тег `v0.18.0`). Зашито, щоб прогін на новому коді не видавав себе
    за «до»."""
    return '6ce8e61'


def _code_differs_from_source():
    """`True`, якщо `app/`/`bin/` цієї теки відрізняються від `_source_commit()` АБО перевірити не вдалося; `None` — лише коли
    у `ROOT` нема `.git` зовсім (заморожена копія з `git archive`: довіряємо рецепту з докстрінга). Рецепт —
    `make_before_4d3b._code_differs_from_source`, але з ІНШИМ коммітом-джерелом: закрито за замовчуванням всередині git-теки (нема
    `git`, збій, чужий toplevel, нема коміту, ненульовий `git diff`, новий файл у `app/`/`bin/`)."""
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
        print('⛔ make_before_4d3c: app/ або bin/ відрізняються від %s — це знімок «після», еталон «до» не перезаписую. '
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
