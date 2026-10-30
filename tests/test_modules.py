"""`app/deai_modules.py`: каркас вбудованих модулів — маніфест, завантаження через `exec`,
налаштування в `space.json`, секрети в `<DEAI_HOME>/secrets.json`, постачальник ролі,
`capabilities`, виклик модуля із захистом.

Модулі-фікстури живуть у ТИМЧАСОВІЙ теці (`builtin_dir` патчиться), а не в `app/modules/`.
Кожен тест має власні `HOME`, `DEAI_HOME` і `DC_TASKS_FILE`; справжній `~/.deai` стереже
`spaces_guard` (знімок на вході в модуль, звірка на виході) — модуль створює простори.
"""
import ast
import builtins
import contextlib
import glob
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
import unicodedata
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # пакета `tests` нема — охоронець поруч
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules as dm  # noqa: E402

_ENV = ('HOME', 'DEAI_HOME', 'DC_TASKS_FILE', 'DEAI_EXTRA_MODULES')
_REAL = None
_DEL = object()          # «прибрати ключ» у `manifest_patch`
_REAL_BUILTIN_DIR = dm.builtin_dir     # до того, як `Env.setUp` її підмінить


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)


def _read(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def _md5(path):
    return hashlib.md5(_bytes(path)).hexdigest()


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def _bump(path, seconds=5):
    """Посунути mtime файла вперед: тест про кеш за mtime не мусить покладатись на таймер ФС."""
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 10 ** 9))


#: Що ядро кладе в `ctx` для модуля, але що НЕ дані: правило теки публікації (модуль не імпортує
#: `deai_modules`, тож отримує його в `ctx`), клас помилки (його `call()` пропускає як є) і `cache_dir` — шлях теки
#: кешу модуля (4a: дзеркала `git-sync`; ядро теку не створює), `find_tool` — шукач npx/node (4b-1).
CORE_CTX_KEYS = ('folder_ok', 'ModuleError', 'cache_dir', 'find_tool')


def _plain(ctx):
    """`ctx` без частин, які ядро додає модулю як ЗАСОБИ (не дані): решту можна порівнювати словником."""
    return {k: v for k, v in ctx.items() if k not in CORE_CTX_KEYS}


def _fs_case_insensitive(path):
    """Чи файлова система в `path` не розрізняє регістр (APFS за замовчуванням): тести «варіант регістру»
    на чутливій ФС нічого б не доводили, тож пропускаються."""
    os.makedirs(os.path.join(path, 'CaseProbe-x'), exist_ok=True)
    return os.path.isdir(os.path.join(path, 'caseprobe-x'))


def race(n, fn):
    """`n` потоків стартують разом (Barrier) і кличуть `fn(i)`; `[('ok', res) | ('err', exc)]`."""
    bar = threading.Barrier(n)
    out = [None] * n

    def run(i):
        try:
            bar.wait(10)
            out[i] = ('ok', fn(i))
        except BaseException as e:  # noqa: BLE001 — збираємо будь-який виняток потоку
            out[i] = ('err', e)
    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    return out


CHECK_ONLY = 'def check(ctx):\n    return {"ok": True}\n'
ALL_FNS = (CHECK_ONLY
           + 'def publish(ctx, build_dir, task):\n    return {"path": "/p"}\n'
           + 'def tokens(ctx):\n    return {"tokens": {}, "source": "t"}\n')

#: Модуль ролі `vcs`: `check` і три обовʼязкові функції; необовʼязкові (`validate`, `mirror_dir`) — окремо, у `VCS_OPTIONAL`.
VCS_FNS = ('def status(ctx, target):\n    return {}\n'
           'def push(ctx, target, src, meta):\n    return {"ok": True}\n'
           'def pull(ctx, target, dst, opts):\n    return {"found": False, "last_commit": None}\n')
VCS_SERVER = CHECK_ONLY + VCS_FNS
VCS_OPTIONAL = ('def validate(ctx, target):\n    return dict(target, checked=True)\n'
                'def mirror_dir(ctx, target):\n    return "/m/" + target["repo"]\n')

#: `check`/`publish` лишають ctx у `builtins._DEAI_SEEN`, щоб тест побачив, що саме отримав модуль.
SEEN_SERVER = '''import builtins
def check(ctx):
    builtins._DEAI_SEEN = ctx
    return {"ok": True}
def publish(ctx, build_dir, task):
    builtins._DEAI_SEEN = (ctx, build_dir, task)
    return {"path": "/p"}
'''

#: Модуль, що падає по-різному залежно від `task["kind"]`; `slow` чекає на `builtins._DEAI_GATE`.
FAILING_SERVER = '''import builtins, json, urllib.parse
def check(ctx):
    return {"ok": True}
def publish(ctx, build_dir, task):
    kind = task["kind"]
    if kind == "exit":
        raise SystemExit(3)
    if kind == "value":
        raise ValueError("boom " + ctx["secrets"]["password"])
    if kind == "repr":
        raise ValueError(repr(ctx["secrets"]["password"]))
    if kind == "json":
        raise ValueError(json.dumps(ctx["secrets"]["password"]))
    if kind == "json-utf8":
        raise ValueError(json.dumps(ctx["secrets"]["password"], ensure_ascii=False))
    if kind == "quote":
        raise ValueError(urllib.parse.quote(ctx["secrets"]["password"], safe=""))
    if kind == "long":
        raise ValueError("x" * 280 + ctx["secrets"]["password"] + "y" * 50)
    if kind == "kbd":
        raise KeyboardInterrupt()
    if kind == "slow":
        builtins._DEAI_GATE.wait(10)
        return {"path": "late"}
    return {"path": "/ok"}
'''


#: Модуль кидає `ModuleError` із кодами, відомими ядру (проходять як є) і невідомим (сплющується).
PASS_SERVER = """import deai_modules
def check(ctx):
    if ctx["secrets"].get("password") == "boom":
        raise deai_modules.ModuleError("bad-folder", 409, "check says no")
    return {"ok": True}
def publish(ctx, build_dir, task):
    kind = task["kind"]
    if kind == "folder":
        raise deai_modules.ModuleError("bad-folder", 409, "folder " + ctx["secrets"]["password"] + "x" * 400)
    if kind == "role":
        raise deai_modules.ModuleError("role-taken", message="r")
    if kind == "status":
        raise deai_modules.ModuleError("bad-folder", 200, "wrong status is ignored")
    if kind == "weird":
        raise deai_modules.ModuleError("weird-code", 418, "teapot " + ctx["secrets"]["password"])
    if kind == "straddle":
        raise deai_modules.ModuleError("bad-folder", 409, "y" * 290 + ctx["secrets"]["password"])
    if kind == "weird-straddle":
        raise deai_modules.ModuleError("weird-code", 418, "y" * 260 + ctx["secrets"]["password"])
    return {"path": "/ok"}
"""


class Env(unittest.TestCase):
    """Тимчасові HOME/DEAI_HOME/DC_TASKS_FILE, тека вбудованих модулів, сторож дедлоку."""

    def setUp(self):
        self.tmp = os.path.normpath(tempfile.mkdtemp(prefix='modules-'))
        self.saved = {k: os.environ.get(k) for k in _ENV}
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        self.deai = os.path.join(self.tmp, 'deai')
        self.legacy = os.path.join(self.tmp, 'legacy', 'tasks.json')
        os.environ['HOME'] = self.home
        os.environ['DEAI_HOME'] = self.deai
        os.environ['DC_TASKS_FILE'] = self.legacy
        # Каталог тесту — рівно `self.mods`: друга тека вбудованих модулів із оточення (`DEAI_EXTRA_MODULES`, шов тестів 2b-2) сюди
        # не належить, і її модулі не можна ні перелічувати, ні — головне — переписувати (`tearDown` повертає змінну).
        os.environ.pop('DEAI_EXTRA_MODULES', None)
        spaces.clear_request_space()
        self.mods = os.path.join(self.tmp, 'builtin')
        os.makedirs(self.mods)
        patch = mock.patch.object(dm, 'builtin_dir', lambda: self.mods)
        patch.start()
        self.addCleanup(patch.stop)
        dm.reset_caches()
        builtins._DEAI_GATE = threading.Event()
        # Сторож: `WRITE_LOCK` не реентерабельний, і виклик `load_registry()`/завантаження модулів
        # під ним — дедлок, тобто ЗАВИСЛИЙ набір замість червоного тесту (див. test_spaces).
        self.deadlock = threading.Event()

        def wake():
            self.deadlock.set()
            try:
                spaces.WRITE_LOCK.release()
            except RuntimeError:
                pass
        self.watchdog = threading.Timer(10, wake)
        self.watchdog.daemon = True
        self.watchdog.start()

    def tearDown(self):
        self.watchdog.cancel()
        builtins._DEAI_GATE.set()
        for name in ('_DEAI_GATE', '_DEAI_SEEN'):
            if hasattr(builtins, name):
                delattr(builtins, name)
        spaces.clear_request_space()
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        dm.reset_caches()
        shutil.rmtree(self.tmp, ignore_errors=True)
        if self.deadlock.is_set():
            self.fail('тест завис на WRITE_LOCK довше 10 с — схоже на дедлок (модулі/реєстр під локом?)')

    # ---- фікстури ----
    def hp(self, *parts):
        return os.path.join(self.home, *parts)

    @property
    def reg_file(self):
        return os.path.join(self.deai, 'spaces.json')

    @property
    def secrets_file(self):
        return os.path.join(self.deai, 'secrets.json')

    def mk(self, mid, roles=('publish',), settings=None, server=ALL_FNS, patch=None, dirname=None):
        """Модуль-фікстура в `self.mods/<dirname or mid>`; `patch` править маніфест (`_DEL` — прибрати
        ключ); `server=None` — без `server.py`."""
        man = {'api': 1, 'id': mid, 'name': mid.title(), 'version': '1.0.0',
               'roles': list(roles), 'settings': settings or []}
        for k, v in (patch or {}).items():
            if v is _DEL:
                man.pop(k, None)
            else:
                man[k] = v
        d = os.path.join(self.mods, dirname or mid)
        _write(os.path.join(d, 'module.json'), man)
        if server is not None:
            _write(os.path.join(d, 'server.py'), server)
        return d

    def new_space(self, name='Alpha', integrations=False):
        """Запис реєстру `{id, path, legacy, integrations}` нового простору (як віддає `spaces`)."""
        sid = spaces.create_space(name, 'space-1', self.hp('work', name.lower()))
        if integrations:
            reg = _read(self.reg_file)
            for s in reg['spaces']:
                if s['id'] == sid:
                    s['integrations'] = True
            _write(self.reg_file, reg)
        return self.rec(sid)

    def rec(self, sid):
        return next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)

    def space_json(self, sp):
        return os.path.join(sp['path'], 'space.json')

    def pub_secret_module(self, mid='pub', roles=('publish',), server=ALL_FNS):
        return self.mk(mid, roles=roles, server=server, settings=[
            {'key': 'folder', 'type': 'path', 'label': 'Folder', 'default': '{home}/pub/{space_id}',
             'required': True},
            {'key': 'password', 'type': 'secret', 'label': 'Password'},
            {'key': 'token', 'type': 'secret', 'label': 'Token'}])


# --------------------------------------------------------------------------------------- ModuleError

class ModuleErrorTest(unittest.TestCase):
    def test_code_status_message(self):
        e = dm.ModuleError('space-json-unreadable', 409)
        self.assertEqual((e.code, e.status, e.message), ('space-json-unreadable', 409, ''))
        e = dm.ModuleError('bad-settings', message='folder: expected path')
        self.assertEqual((e.code, e.status), ('bad-settings', 400))
        self.assertIn('folder: expected path', str(e))
        self.assertIn('bad-settings', str(e))
        e = dm.ModuleError('module-error', 'ValueError: boom')      # рядок другим аргументом — це текст
        self.assertEqual((e.status, e.message), (502, 'ValueError: boom'))

    def test_every_code_has_an_http_status(self):
        want = {'bad-manifest': 500, 'module-error': 502, 'role-taken': 409, 'unknown-module': 404,
                'bad-settings': 400, 'space-json-unreadable': 409, 'spaces-off': 409,
                'check-timeout': 504, 'secrets-unreadable': 409, 'unwritable': 500, 'bad-folder': 409,
                'vercel-auth': 409, 'vercel-busy': 409,
                # роль `vcs` (4a): мережа/DNS/тайм-аут git, відмова в доступі, погана ціль, зайняте дзеркало, решта відмов git
                'vcs-offline': 502, 'vcs-auth': 502, 'vcs-bad-target': 400, 'vcs-busy': 409, 'vcs-error': 502}
        for code, status in want.items():
            self.assertEqual(dm.ModuleError(code).status, status, code)

    def test_roles(self):
        self.assertEqual(dm.ROLES_CALLED, ('publish', 'tokens', 'comments', 'vcs'))     # 2b-2: `comments`, 4a: `vcs` — ролі, які ядро кличе
        self.assertEqual(dm.ROLES_RESERVED, ('tracker', 'dashboard', 'notify'))
        self.assertEqual(dm.ROLE_FUNCTIONS['vcs'], ('status', 'push', 'pull'))
        self.assertEqual(dm.LEGACY_ROLES, ('publish', 'comments', 'vcs'))               # у ЛІГА `vcs` — зашитий шлях, як `publish`
        # що з ролей ЛІГА лишається `'legacy'` у `capabilities()`, коли роль не вирішилась: без `comments` (спільний Supabase ЛІГА)
        self.assertEqual(dm.LEGACY_ON_ERROR_ROLES, ('publish', 'vcs'))
        self.assertTrue(set(dm.LEGACY_ON_ERROR_ROLES) <= set(dm.LEGACY_ROLES))
        self.assertEqual(dm.ROLE_OPTIONAL_FUNCTIONS, {'vcs': ('validate', 'mirror_dir')})


# ------------------------------------------------------------------------------------------ маніфест

class ManifestTest(Env):
    def error_of(self, mid):
        m = dm.catalog()[mid]
        self.assertEqual(m.status, 'error', f'{mid}: {m.error!r}')
        self.assertTrue(m.error and isinstance(m.error, str))
        self.assertEqual(m.error_code, 'bad-manifest')
        self.assertIsNone(m.fn('check'))            # модуль із помилкою нічого не віддає
        return m.error

    def test_valid_manifest_loads(self):
        self.mk('alpha', roles=('publish', 'tokens'), settings=[
            {'key': 'folder', 'type': 'path', 'label': 'Folder', 'default': '{home}/x', 'required': True},
            {'key': 'mode', 'type': 'select', 'options': [{'value': 'a', 'label': 'A'}]},
            {'key': 'flag', 'type': 'bool', 'default': True},
            {'key': 'note', 'type': 'text'},
            {'key': 'password', 'type': 'secret'}])
        m = dm.catalog()['alpha']
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertEqual((m.id, m.name, m.version, m.api), ('alpha', 'Alpha', '1.0.0', 1))
        self.assertEqual(m.roles, ['publish', 'tokens'])
        self.assertEqual([s['key'] for s in m.settings], ['folder', 'mode', 'flag', 'note', 'password'])
        self.assertEqual(m.settings[0]['default'], '{home}/x')
        self.assertTrue(m.settings[0]['required'])
        self.assertEqual(m.settings[1]['options'], [{'value': 'a', 'label': 'A'}])
        self.assertTrue(callable(m.fn('check')) and callable(m.fn('publish')) and callable(m.fn('tokens')))
        self.assertIsNone(m.fn('comments'))

    def test_api_must_be_exactly_one(self):
        for mid, api in (('api-two', 2), ('api-zero', 0), ('api-str', '1'), ('api-true', True),
                         ('api-float', 1.0), ('api-null', None), ('api-list', [1]), ('api-none', _DEL)):
            self.mk(mid, patch={'api': api})
        for mid in ('api-two', 'api-zero', 'api-str', 'api-true', 'api-float', 'api-null', 'api-list',
                    'api-none'):
            self.assertIn('api', self.error_of(mid), mid)

    def test_id_must_match_folder_and_pattern(self):
        self.mk('folder-name', patch={'id': 'other-id'})
        self.assertIn('id', self.error_of('folder-name'))
        for bad in ('Upper', '-dash', 'a_b', 'a' * 41, 'dot.s'):
            self.mk(bad, dirname=bad)
            self.assertIn('id', self.error_of(bad), bad)
        self.mk('a' * 40)                                  # межа: 40 знаків ще можна
        self.assertEqual(dm.catalog()['a' * 40].status, 'ok')
        self.mk('x')                                       # 1 знак — теж можна
        self.assertEqual(dm.catalog()['x'].status, 'ok')

    def test_roles_rules(self):
        self.mk('role-unknown', patch={'roles': ['publish', 'bogus']})
        self.mk('role-string', patch={'roles': 'publish'})
        self.mk('role-missing', patch={'roles': _DEL})
        self.mk('role-nonstr', patch={'roles': [1]})
        for mid in ('role-unknown', 'role-string', 'role-missing', 'role-nonstr'):
            self.assertIn('roles', self.error_of(mid), mid)

    def test_publish_target_is_optional_folder_or_url_and_validated_for_every_role(self):
        marker = os.path.join(self.tmp, 'marker')
        self.mk('pt-none')
        self.mk('pt-folder', patch={'publish_target': 'folder'})
        self.mk('pt-url', patch={'publish_target': 'url'})
        self.mk('pt-tokens', roles=('tokens',), server=CHECK_ONLY + 'def tokens(ctx):\n    return {}\n',
                patch={'publish_target': 'url'})
        for mid, bad in (('pt-ftp', 'ftp'), ('pt-empty', ''), ('pt-upper', 'URL'), ('pt-null', None), ('pt-int', 1),
                         ('pt-list', ['url'])):
            self.mk(mid, patch={'publish_target': bad}, server=f'open({marker!r}, "w").close()\n' + ALL_FNS)
        self.mk('pt-bad-tokens', roles=('tokens',), patch={'publish_target': 'nope'})
        cat = dm.catalog()
        self.assertEqual([(cat[m].status, cat[m].publish_target)
                          for m in ('pt-none', 'pt-folder', 'pt-url', 'pt-tokens')],
                         [('ok', 'folder'), ('ok', 'folder'), ('ok', 'url'), ('ok', 'url')])
        for mid in ('pt-ftp', 'pt-empty', 'pt-upper', 'pt-null', 'pt-int', 'pt-list', 'pt-bad-tokens'):
            self.assertIn('publish_target', self.error_of(mid), mid)
        self.assertFalse(os.path.exists(marker), 'server.py модуля з поганим publish_target не мусить виконуватись')
        self.assertEqual(dm.Module('m').publish_target, 'folder')
        self.assertEqual(dm.Module('m', publish_target='url').publish_target, 'url')

    def test_check_timeout_s_is_optional_and_an_integer_in_1_150(self):
        """Необовʼязковий ключ маніфесту `check_timeout_s` (4b-1, фінальне ревʼю): довший тайм-аут `check` для модуля, що запускає
        процес. Ціле 1..150; все інше (0, 151, дріб, рядок, bool, null, список) — `bad-manifest` ДО виконання `server.py`."""
        marker = os.path.join(self.tmp, 'marker-cts')
        self.mk('cts-none')
        self.mk('cts-1', patch={'check_timeout_s': 1})
        self.mk('cts-130', patch={'check_timeout_s': 130})
        self.mk('cts-150', patch={'check_timeout_s': 150})
        bad = (('cts-zero', 0), ('cts-151', 151), ('cts-neg', -1), ('cts-float', 5.0), ('cts-str', '5'),
               ('cts-true', True), ('cts-null', None), ('cts-list', [5]))
        for mid, v in bad:
            self.mk(mid, patch={'check_timeout_s': v}, server=f'open({marker!r}, "w").close()\n' + ALL_FNS)
        cat = dm.catalog()
        self.assertEqual([(cat[m].status, cat[m].check_timeout_s) for m in ('cts-none', 'cts-1', 'cts-130', 'cts-150')],
                         [('ok', None), ('ok', 1), ('ok', 130), ('ok', 150)])
        for mid, _v in bad:
            self.assertEqual(cat[mid].error_code, 'bad-manifest', mid)
            self.assertIn('check_timeout_s', self.error_of(mid), mid)
        self.assertFalse(os.path.exists(marker), 'server.py модуля з поганим check_timeout_s не мусить виконуватись')
        self.assertIsNone(dm.Module('m').check_timeout_s)
        self.assertEqual(dm.Module('m', check_timeout_s=7).check_timeout_s, 7)

    def test_called_role_needs_a_function(self):
        self.mk('no-publish', roles=('publish',), server=CHECK_ONLY)
        self.mk('no-tokens', roles=('tokens',), server=CHECK_ONLY)
        self.mk('both-ok', roles=('publish', 'tokens'), server=ALL_FNS)
        self.assertIn('publish', self.error_of('no-publish'))
        self.assertIn('tokens', self.error_of('no-tokens'))
        self.assertEqual(dm.catalog()['both-ok'].status, 'ok')

    def test_check_is_required_and_callable(self):
        self.mk('no-check', server='def publish(ctx, b, t):\n    return {}\n')
        self.mk('check-not-callable', server='check = 5\ndef publish(ctx, b, t):\n    return {}\n')
        self.assertIn('check', self.error_of('no-check'))
        self.assertIn('check', self.error_of('check-not-callable'))

    def test_reserved_roles_need_no_function(self):
        self.mk('reserved', roles=('tracker', 'dashboard', 'notify'), server=CHECK_ONLY)
        m = dm.catalog()['reserved']
        self.assertEqual(m.status, 'ok')
        self.assertEqual(m.roles, ['tracker', 'dashboard', 'notify'])

    def test_vcs_role_needs_its_functions(self):
        """`vcs` — роль, яку ядро кличе (4a): модуль без `status`/`push`/`pull` — зламаний, а не «зарезервований»."""
        self.mk('vcs-bare', roles=('vcs',), server=CHECK_ONLY)
        self.assertIn('status', self.error_of('vcs-bare'))
        for gap in ('status', 'push', 'pull'):
            src = VCS_SERVER.replace(f'def {gap}(', f'def _not_{gap}(')
            self.mk(f'vcs-no-{gap}', roles=('vcs',), server=src)
            self.assertIn(gap, self.error_of(f'vcs-no-{gap}'), gap)
        self.mk('vcs-ok', roles=('vcs',), server=VCS_SERVER)
        self.assertEqual(dm.catalog()['vcs-ok'].status, 'ok')

    def test_optional_role_functions_are_taken_when_present_and_never_required(self):
        """`validate`/`mirror_dir` ролі `vcs` — необовʼязкові: беруться з `server.py`, якщо є й callable (інакше
        `Module.fn('validate')` і `call(m, 'validate', …)` були б недосяжні), а свій модуль без них валідний."""
        self.mk('vcs-plain', roles=('vcs',), server=VCS_SERVER)
        self.mk('vcs-full', roles=('vcs',), server=VCS_SERVER + VCS_OPTIONAL)
        self.mk('vcs-junk', roles=('vcs',), server=VCS_SERVER + 'validate = 5\nmirror_dir = None\n')
        cat = dm.catalog()
        self.assertEqual(cat['vcs-plain'].status, 'ok')
        self.assertIsNone(cat['vcs-plain'].fn('validate'))
        self.assertIsNone(cat['vcs-plain'].fn('mirror_dir'))
        full = cat['vcs-full']
        self.assertEqual(full.status, 'ok')
        self.assertTrue(callable(full.fn('validate')) and callable(full.fn('mirror_dir')))
        ctx = {'space': {'id': 's', 'path': '/x'}, 'settings': {}, 'secrets': {}}
        self.assertEqual(dm.call(full, 'validate', ctx, {'repo': 'r'}), {'repo': 'r', 'checked': True})
        self.assertEqual(dm.call(full, 'mirror_dir', ctx, {'repo': 'r'}), '/m/r')
        self.assertEqual(cat['vcs-junk'].status, 'ok', 'не-функція замість необовʼязкової — не помилка')
        self.assertIsNone(cat['vcs-junk'].fn('validate'))
        self.assertIsNone(cat['vcs-junk'].fn('mirror_dir'))

    def test_optional_functions_belong_to_their_role_only(self):
        """Модуль іншої ролі, що має функцію з таким самим іменем, її не віддає: перелік іде за ролями маніфесту."""
        self.mk('pub-with-validate', roles=('publish',), server=ALL_FNS + VCS_OPTIONAL)
        self.mk('vcs-and-pub', roles=('publish', 'vcs'), server=ALL_FNS + VCS_FNS + VCS_OPTIONAL)
        cat = dm.catalog()
        self.assertEqual(cat['pub-with-validate'].status, 'ok')
        self.assertIsNone(cat['pub-with-validate'].fn('validate'))
        self.assertEqual(cat['vcs-and-pub'].status, 'ok', cat['vcs-and-pub'].error)
        self.assertTrue(callable(cat['vcs-and-pub'].fn('validate')))

    def test_setting_rules(self):
        self.mk('s-bad-type', settings=[{'key': 'a', 'type': 'number'}])
        self.mk('s-no-type', settings=[{'key': 'a'}])
        self.mk('s-no-key', settings=[{'type': 'text'}])
        self.mk('s-dup-key', settings=[{'key': 'a', 'type': 'text'}, {'key': 'a', 'type': 'bool'}])
        self.mk('s-not-list', patch={'settings': {}})
        self.mk('s-not-dict', patch={'settings': ['a']})
        self.mk('s-select-no-opts', settings=[{'key': 'a', 'type': 'select'}])
        self.mk('s-select-empty', settings=[{'key': 'a', 'type': 'select', 'options': []}])
        self.mk('s-select-no-label', settings=[{'key': 'a', 'type': 'select', 'options': [{'value': 'x'}]}])
        self.mk('s-select-strs', settings=[{'key': 'a', 'type': 'select', 'options': ['x']}])
        self.mk('s-secret-default', settings=[{'key': 'a', 'type': 'secret', 'default': 'x'}])
        self.mk('s-bool-default', settings=[{'key': 'a', 'type': 'bool', 'default': 'yes'}])
        for mid in ('s-bad-type', 's-no-type', 's-no-key', 's-dup-key', 's-not-list', 's-not-dict',
                    's-select-no-opts', 's-select-empty', 's-select-no-label', 's-select-strs',
                    's-secret-default', 's-bool-default'):
            self.assertIn('settings', self.error_of(mid), mid)

    def test_name_and_version_are_strings_when_present(self):
        self.mk('name-int', patch={'name': 5})
        self.mk('ver-int', patch={'version': 1})
        self.mk('no-name-ver', patch={'name': _DEL, 'version': _DEL})
        self.error_of('name-int')
        self.error_of('ver-int')
        m = dm.catalog()['no-name-ver']
        self.assertEqual((m.status, m.name, m.version), ('ok', 'no-name-ver', ''))

    def test_unreadable_manifest_is_an_error_not_a_crash(self):
        self.mk('broken-json')
        _write(os.path.join(self.mods, 'broken-json', 'module.json'), '{not json')
        self.mk('top-list')
        _write(os.path.join(self.mods, 'top-list', 'module.json'), '[1, 2]')
        os.makedirs(os.path.join(self.mods, 'no-manifest'))
        _write(os.path.join(self.mods, 'no-manifest', 'server.py'), ALL_FNS)
        self.mk('no-server', server=None)
        huge = os.path.join(self.mods, 'huge')
        _write(os.path.join(huge, 'module.json'), ' ' * (spaces.MAX_JSON_BYTES + 10))
        _write(os.path.join(huge, 'server.py'), ALL_FNS)
        for mid in ('broken-json', 'top-list', 'no-manifest', 'huge'):
            self.error_of(mid)
        m = dm.catalog()['no-server']
        self.assertEqual(m.status, 'error')
        self.assertIn('server.py', m.error)

    def test_invalid_manifest_never_executes_server(self):
        marker = os.path.join(self.tmp, 'marker')
        code = f'open({marker!r}, "w").close()\n' + ALL_FNS
        self.mk('bad-api', patch={'api': 2}, server=code)
        self.assertEqual(dm.catalog()['bad-api'].status, 'error')
        self.assertFalse(os.path.exists(marker), 'server.py модуля з поганим маніфестом не мусить виконуватись')
        self.mk('good', server=code)                         # контроль: валідний — виконується
        self.assertEqual(dm.catalog()['good'].status, 'ok')
        self.assertTrue(os.path.exists(marker))

    def test_catalog_lists_only_module_folders_sorted(self):
        self.mk('b-mod')
        self.mk('a-mod')
        os.makedirs(os.path.join(self.mods, '.hidden'))
        os.makedirs(os.path.join(self.mods, '__pycache__'))
        _write(os.path.join(self.mods, 'stray.txt'), 'x')
        self.assertEqual(list(dm.catalog()), ['a-mod', 'b-mod'])

    def test_missing_builtin_dir_is_an_empty_catalog(self):
        shutil.rmtree(self.mods)
        self.assertEqual(dm.catalog(), {})

    def test_builtin_dir_default_is_app_modules(self):
        want = os.path.join(os.path.dirname(os.path.abspath(dm.__file__)), 'modules')
        self.assertEqual(_REAL_BUILTIN_DIR(), want)


# ----------------------------------------------------------------------- роль `comments` (2b-2): `client`, `public`

#: Серверна половина модуля ролі `comments`: `client_config`, `list`, `resolve` + обовʼязковий `check`.
COMMENTS_FNS = (CHECK_ONLY
                + 'def client_config(ctx):\n    return {}\n'
                + 'def list(ctx, channel):\n    return []\n'
                + 'def resolve(ctx, channel, id, reason):\n    return None\n')
CLIENT_JS = 'window.DeaiComments = { create(cfg) { return {}; } };\n'
MAX_CLIENT = 512 * 1024            # межа розміру одного файла адаптера (спека 2b-2): рівно 512 КіБ ще можна


class ManifestClientTest(Env):
    """`client` — список файлів браузерного адаптера: обовʼязковий для ролі `comments`, заборонений без неї,
    1–8 імен за шаблоном, кожне — звичайний файл у теці модуля ≤ 512 КіБ без посилань. Порушення — `bad-manifest`
    БЕЗ виконання `server.py`."""

    NAME = r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}\.js'

    def mkc(self, mid, client=('a.js',), files=None, **kw):
        """Модуль `comments` з файлами адаптера. `files` — `{імʼя: вміст}`; типово — кожне валідне імʼя з `client`."""
        kw.setdefault('server', COMMENTS_FNS)
        kw.setdefault('roles', ('comments',))
        patch = dict(kw.pop('patch', None) or {})
        patch['client'] = _DEL if client is _DEL else (list(client) if isinstance(client, tuple) else client)
        d = self.mk(mid, patch=patch, **kw)
        if files is None:
            names = client if isinstance(client, (list, tuple)) else ()
            files = {n: CLIENT_JS for n in names if isinstance(n, str) and re.fullmatch(self.NAME, n)}
        for name, text in files.items():
            _write(os.path.join(d, name), text)
        return d

    def error_of(self, mid, want='client'):
        m = dm.catalog()[mid]
        self.assertEqual(m.status, 'error', f'{mid}: модуль мав відмовитись')
        self.assertEqual(m.error_code, 'bad-manifest', mid)
        self.assertIn(want, m.error, f'{mid}: {m.error!r}')
        self.assertIsNone(m.fn('check'))
        self.assertEqual(m.client, (), 'модуль із помилкою нічого не віддає')
        return m.error

    def test_a_comments_module_loads_with_its_client_files_in_order(self):
        self.mkc('cm', client=('b.js', 'a.js', '_c-1.x.js'))
        m = dm.catalog()['cm']
        self.assertEqual((m.status, m.error), ('ok', None))
        self.assertEqual(m.client, ('b.js', 'a.js', '_c-1.x.js'))      # порядок маніфесту — порядок вантаження
        self.assertIsInstance(m.client, tuple)
        self.assertEqual(m.roles, ['comments'])
        for name in ('client_config', 'list', 'resolve', 'check'):
            self.assertTrue(callable(m.fn(name)), name)
        self.assertIsNone(m.fn('comments'))

    def test_modules_without_the_role_have_no_client(self):
        self.mk('plain')
        self.assertEqual(dm.catalog()['plain'].client, ())
        self.assertEqual(dm.Module('x').client, ())
        self.assertEqual(dm.Module('x', client=['a.js']).client, ('a.js',))

    def test_client_is_required_for_the_role(self):
        self.mkc('no-client', client=_DEL)
        self.assertIn('comments', self.error_of('no-client'))

    def test_client_is_forbidden_without_the_role(self):
        self.mkc('pub-client', roles=('publish',), server=ALL_FNS)
        self.mkc('both-roles', roles=('publish', 'comments'), server=ALL_FNS + COMMENTS_FNS)   # з роллю — можна
        self.mkc('no-roles', roles=())
        self.mkc('tok-client', roles=('tokens',), server=ALL_FNS)
        self.error_of('pub-client')
        self.error_of('no-roles')
        self.error_of('tok-client')
        self.assertEqual(dm.catalog()['both-roles'].status, 'ok')

    def test_client_must_be_a_list_of_one_to_eight(self):
        for mid, bad in (('c-str', 'a.js'), ('c-dict', {'a.js': 1}), ('c-null', None), ('c-int', 5), ('c-empty', []),
                         ('c-true', True)):
            self.mkc(mid, client=bad, files={'a.js': CLIENT_JS})
            self.error_of(mid)
        names = [f'f{i}.js' for i in range(9)]
        self.mkc('c-nine', client=names)
        self.error_of('c-nine')
        self.mkc('c-eight', client=names[:8])
        self.assertEqual(dm.catalog()['c-eight'].status, 'ok')
        self.mkc('c-one', client=names[:1])
        self.assertEqual(dm.catalog()['c-one'].status, 'ok')

    def test_entries_must_be_unique_strings(self):
        for mid, bad in (('e-int', [1]), ('e-null', [None]), ('e-list', [['a.js']]), ('e-dict', [{'a.js': 1}]),
                         ('e-dup', ['a.js', 'a.js'])):
            self.mkc(mid, client=bad, files={'a.js': CLIENT_JS})
            self.error_of(mid)

    def test_names_follow_the_pattern(self):
        """Кожне погане імʼя вказує на РЕАЛЬНИЙ звичайний файл (за адресою, на яку веде `os.path.join(теки_модуля, імʼя)`):
        відмову дає саме шаблон, а не відсутність файла. Тож розширення шаблону (`../`, `/`, крапка на початку, інший
        регістр чи розширення) цей тест ловить."""
        bad = {'dotdot': '../a.js', 'slash': 'a/b.js', 'subdir': 'sub/b.js', 'dotfile': '.a.js', 'ext': 'a.txt',
               'upper': 'a.JS', 'bare': 'a', 'justext': '.js', 'space': 'a b.js', 'newline': 'a.js\n', 'empty': '',
               'long': 'a' * 65 + '.js', 'cyr': 'ї.js', 'bslash': 'a\\b.js', 'dash': '-a.js', 'map': 'a.js.map',
               'abs': os.path.join(self.tmp, 'abs.js'), 'nul': 'a\0.js', 'dotdot2': '../../a.js'}
        for key, name in bad.items():
            mid = f'n-{key}'
            d = self.mkc(mid, client=[name], files={})
            target = os.path.join(d, name)
            if name and '\0' not in name:
                _write(target, CLIENT_JS)                              # файл Є: інакше відмова була б «нема файла»
                self.assertTrue(os.path.isfile(target), name)
            self.error_of(mid, want='must match')
        self.mkc('n-longest', client=['a' * 64 + '.js'])          # межа: 67 знаків
        self.mkc('n-misc', client=['_x.js', 'A-b.c_d.js', '0.js', 'a.b.js'])
        self.assertEqual(dm.catalog()['n-longest'].status, 'ok')
        self.assertEqual(dm.catalog()['n-misc'].status, 'ok')

    def test_the_name_must_be_exactly_the_name_on_disk(self):
        """ФС без урахування регістру (APFS) віддала б `adapter.js` на запит `ADAPTER.js`, а `["Adapter.js", "adapter.js"]`
        пройшло б перевірку дублів: імʼя з маніфесту мусить бути в `os.listdir(теки)` БУКВА В БУКВУ."""
        self.mkc('x-case', client=['ADAPTER.js'], files={'adapter.js': CLIENT_JS})
        self.mkc('x-dup', client=['Adapter.js', 'adapter.js'], files={'adapter.js': CLIENT_JS})
        self.mkc('x-lower', client=['adapter.js'], files={'Adapter.js': CLIENT_JS})
        for mid in ('x-case', 'x-dup', 'x-lower'):
            self.assertIn('is not a file of the module', self.error_of(mid))
        self.mkc('x-ok', client=['Adapter.js', 'b.js'], files={'Adapter.js': CLIENT_JS, 'b.js': CLIENT_JS})
        self.assertEqual(dm.catalog()['x-ok'].client, ('Adapter.js', 'b.js'))

    def test_a_declared_file_must_exist_and_be_a_regular_file(self):
        self.mkc('f-missing', client=['a.js'], files={})
        d = self.mkc('f-dir', client=['a.js'], files={})
        os.makedirs(os.path.join(d, 'a.js'))
        d = self.mkc('f-fifo', client=['a.js'], files={})
        os.mkfifo(os.path.join(d, 'a.js'))
        for mid in ('f-missing', 'f-dir', 'f-fifo'):
            self.error_of(mid)

    def test_a_symlink_is_refused_even_inside_the_folder(self):
        d = self.mkc('l-in', client=['a.js'], files={'real.js': CLIENT_JS})
        os.symlink(os.path.join(d, 'real.js'), os.path.join(d, 'a.js'))
        outside = os.path.join(self.tmp, 'outside.js')
        _write(outside, CLIENT_JS)
        d = self.mkc('l-out', client=['a.js'], files={})
        os.symlink(outside, os.path.join(d, 'a.js'))
        d = self.mkc('l-dangling', client=['a.js'], files={})
        os.symlink(os.path.join(self.tmp, 'nowhere.js'), os.path.join(d, 'a.js'))
        for mid in ('l-in', 'l-out', 'l-dangling'):
            self.error_of(mid)

    def test_a_hard_link_is_refused(self):
        """Жорстке посилання на чужий файл — не «лише звичайні файли теки»: роздача його теж не відкриє, тож
        модуль, що його оголосив, не вважається справним."""
        outside = os.path.join(self.tmp, 'outside.js')
        _write(outside, CLIENT_JS)
        d = self.mkc('h-link', client=['a.js'], files={})
        os.link(outside, os.path.join(d, 'a.js'))
        self.error_of('h-link')

    def test_the_size_limit_is_512_kib(self):
        self.mkc('s-at', client=['a.js'], files={'a.js': 'x' * MAX_CLIENT})
        self.mkc('s-over', client=['a.js'], files={'a.js': 'x' * (MAX_CLIENT + 1)})
        self.assertEqual(dm.catalog()['s-at'].status, 'ok')
        self.error_of('s-over')
        self.mkc('s-two', client=['a.js', 'b.js'], files={'a.js': CLIENT_JS, 'b.js': 'x' * (MAX_CLIENT + 1)})
        self.error_of('s-two')                                       # межа — на КОЖЕН файл

    def test_a_bad_client_never_executes_server_py(self):
        marker = os.path.join(self.tmp, 'marker')
        code = f'open({marker!r}, "w").close()\n' + COMMENTS_FNS
        self.mkc('bad', client=['../x.js'], files={}, server=code)
        self.error_of('bad')
        self.assertFalse(os.path.exists(marker), 'server.py модуля з поганим client не мусить виконуватись')
        self.mkc('good', server=code)                                # контроль: валідний — виконується
        self.assertEqual(dm.catalog()['good'].status, 'ok')
        self.assertTrue(os.path.exists(marker))

    def test_the_comments_role_needs_its_four_functions(self):
        base = {'client_config': 'def client_config(ctx):\n    return {}\n',
                'list': 'def list(ctx, channel):\n    return []\n',
                'resolve': 'def resolve(ctx, channel, id, reason):\n    return None\n',
                'check': CHECK_ONLY}
        for missing in base:
            mid = f'm-{missing.replace("_", "-")}'
            self.mkc(mid, server=''.join(v for k, v in base.items() if k != missing))
            self.error_of(mid, want=missing)
        self.mkc('m-not-callable', server=COMMENTS_FNS + 'resolve = 5\n')
        self.error_of('m-not-callable', want='resolve')
        self.mkc('m-all', server=''.join(base.values()))
        self.assertEqual(dm.catalog()['m-all'].status, 'ok')

    def test_a_change_of_the_adapter_files_reloads_the_module(self):
        """Кеш модуля бачить не лише `module.json` і `server.py`, а й файли адаптера: підміна на посилання чи
        видалення робить модуль помилковим, поява файла — справним."""
        d = self.mkc('live', client=['a.js'])
        a = dm.catalog()['live']
        self.assertEqual(a.status, 'ok')
        self.assertIs(dm.catalog()['live'], a)                       # без змін — той самий обʼєкт
        target = os.path.join(d, 'a.js')
        os.remove(target)
        self.assertEqual(dm.catalog()['live'].status, 'error')
        _write(target, CLIENT_JS)
        self.assertEqual(dm.catalog()['live'].status, 'ok')
        _write(os.path.join(d, 'real.js'), CLIENT_JS)
        os.remove(target)
        os.symlink(os.path.join(d, 'real.js'), target)
        self.assertEqual(dm.catalog()['live'].status, 'error')
        os.remove(target)
        _write(target, 'y' * (MAX_CLIENT + 1))
        self.assertEqual(dm.catalog()['live'].status, 'error')
        _write(target, CLIENT_JS)
        self.assertEqual(dm.catalog()['live'].status, 'ok')


class ManifestPublicSecretTest(Env):
    """`"public": true` — лише на `secret`: значення живе в `secrets.json`, але може потрапити в сторінки."""

    def error_of(self, mid):
        m = dm.catalog()[mid]
        self.assertEqual((m.status, m.error_code), ('error', 'bad-manifest'), f'{mid}: {m.error!r}')
        self.assertIn('public', m.error)
        return m.error

    def test_public_on_a_secret_is_accepted_and_normalised(self):
        self.mk('pub-ok', roles=(), settings=[
            {'key': 'a', 'type': 'secret', 'public': True},
            {'key': 'b', 'type': 'secret', 'public': False},
            {'key': 'c', 'type': 'secret'}])
        m = dm.catalog()['pub-ok']
        self.assertEqual((m.status, m.error), ('ok', None))
        by = {s['key']: s for s in m.settings}
        self.assertIs(by['a'].get('public'), True)
        self.assertFalse(by['b'].get('public'))
        self.assertFalse(by['c'].get('public'))
        self.assertEqual(m.secret_keys(), ['a', 'b', 'c'])
        self.assertEqual(m.private_secret_keys(), ['b', 'c'])        # без `public: true`

    def test_public_on_any_other_type_is_refused(self):
        for t in ('text', 'path', 'bool', 'select'):
            extra = {'options': [{'value': 'x', 'label': 'X'}]} if t == 'select' else {}
            for val in (True, False):
                mid = f'p-{t}-{str(val).lower()}'
                self.mk(mid, roles=(), settings=[{'key': 'k', 'type': t, 'public': val, **extra}])
                self.assertIn('settings[0]', self.error_of(mid))

    def test_public_must_be_a_boolean(self):
        for key, bad in (('str', 'yes'), ('int1', 1), ('int0', 0), ('null', None), ('list', []), ('dict', {})):
            mid = f'pb-{key}'
            self.mk(mid, roles=(), settings=[{'key': 'k', 'type': 'secret', 'public': bad}])
            self.error_of(mid)


# ---------------------------------------------------------------------------------------- завантаження

class LoadTest(Env):
    def test_exec_loading_leaves_no_pycache_and_no_sys_modules(self):
        d = self.mk('alpha')
        with mock.patch.object(sys, 'dont_write_bytecode', False):   # -B не мусить рятувати тест
            m = dm.catalog()['alpha']
        self.assertEqual(m.status, 'ok')
        self.assertFalse(os.path.exists(os.path.join(d, '__pycache__')))
        self.assertEqual(sorted(os.listdir(d)), ['module.json', 'server.py'])
        self.assertNotIn('deai_mod_alpha', sys.modules)
        self.assertEqual(m.fn('check').__module__, 'deai_mod_alpha')
        self.assertEqual(m.fn('check').__globals__['__file__'], os.path.join(d, 'server.py'))

    def test_unchanged_files_are_not_reloaded(self):
        self.mk('alpha')
        a = dm.catalog()['alpha']
        b = dm.catalog()['alpha']
        self.assertIs(a, b)
        self.assertIs(a.fn('check'), b.fn('check'))

    def test_changed_file_reloads_by_mtime(self):
        """Правка ТОГО Ж РОЗМІРУ зі зсунутим mtime: інакше кеш за розміром її б не побачив."""
        d = self.mk('alpha', roles=(), server='def check(ctx):\n    return {"ok": True}\n')
        a = dm.catalog()['alpha']
        self.assertEqual(a.fn('check')({}), {'ok': True})
        sv = os.path.join(d, 'server.py')
        _write(sv, 'def check(ctx):\n    return {"ok": 1234}\n')
        self.assertEqual(len(_bytes(sv)), len('def check(ctx):\n    return {"ok": True}\n'))
        _bump(sv)
        b = dm.catalog()['alpha']
        self.assertIsNot(a, b)
        self.assertEqual(b.fn('check')({}), {'ok': 1234})

    def test_changed_manifest_reloads(self):
        d = self.mk('alpha')
        a = dm.catalog()['alpha']
        man = _read(os.path.join(d, 'module.json'))
        man['name'] = 'Renamed!'
        _write(os.path.join(d, 'module.json'), man)
        _bump(os.path.join(d, 'module.json'))
        self.assertEqual(dm.catalog()['alpha'].name, 'Renamed!')
        self.assertIsNot(dm.catalog()['alpha'], a)

    def test_syntax_error_is_an_error_with_text_and_recovers(self):
        d = self.mk('alpha', server='def check(ctx:\n    return 1\n')
        m = dm.catalog()['alpha']
        self.assertEqual(m.status, 'error')
        self.assertIn('SyntaxError', m.error)
        self.assertIn('server.py', m.error)
        self.assertLessEqual(len(m.error), 300)
        self.assertEqual(m.error_code, 'module-error')
        self.assertIs(dm.catalog()['alpha'], m)             # помилка кешується до зміни файла
        _write(os.path.join(d, 'server.py'), ALL_FNS)
        _bump(os.path.join(d, 'server.py'))
        self.assertEqual(dm.catalog()['alpha'].status, 'ok')

    def test_import_time_exceptions_are_errors(self):
        self.mk('raises', server='raise RuntimeError("no import for you")\n')
        self.mk('exits', server='import sys\nsys.exit(4)\n')
        self.mk('bad-import', server='import definitely_not_a_module_xyz\n' + ALL_FNS)
        for mid, part in (('raises', 'RuntimeError'), ('exits', 'SystemExit'), ('bad-import', 'ModuleNotFoundError')):
            m = dm.catalog()[mid]
            self.assertEqual(m.status, 'error', mid)
            self.assertIn(part, m.error, mid)
            self.assertEqual(m.error_code, 'module-error')

    def test_module_with_manifest_data_keeps_it_when_the_server_fails(self):
        self.mk('alpha', server='raise RuntimeError("x")\n')
        m = dm.catalog()['alpha']
        self.assertEqual((m.status, m.name, m.roles), ('error', 'Alpha', ['publish']))

    def test_a_replaced_file_with_the_same_size_and_mtime_is_reloaded(self):
        """Заміна перейменуванням: той самий розмір, повернутий mtime — відрізняє лише inode."""
        d = self.mk('alpha', roles=(), server='def check(ctx):\n    return {"ok": True}\n')
        a = dm.catalog()['alpha']
        sv = os.path.join(d, 'server.py')
        st = os.stat(sv)
        new = sv + '.new'
        _write(new, 'def check(ctx):\n    return {"ok": 1234}\n')
        os.utime(new, ns=(st.st_atime_ns, st.st_mtime_ns))
        os.replace(new, sv)
        now = os.stat(sv)
        self.assertEqual((now.st_size, now.st_mtime_ns), (st.st_size, st.st_mtime_ns))
        if now.st_ino == st.st_ino:
            self.skipTest('файлова система повторно віддала той самий inode')
        b = dm.catalog()['alpha']
        self.assertIsNot(a, b)
        self.assertEqual(b.fn('check')({}), {'ok': 1234})

    def test_an_in_place_rewrite_with_a_different_size_and_restored_mtime_is_reloaded(self):
        d = self.mk('alpha', roles=(), server='def check(ctx):\n    return {"ok": True}\n')
        a = dm.catalog()['alpha']
        sv = os.path.join(d, 'server.py')
        st = os.stat(sv)
        _write(sv, 'def check(ctx):\n    return {"ok": 12345}\n')          # довший файл, той самий inode
        os.utime(sv, ns=(st.st_atime_ns, st.st_mtime_ns))
        now = os.stat(sv)
        self.assertEqual((now.st_ino, now.st_mtime_ns), (st.st_ino, st.st_mtime_ns))
        self.assertNotEqual(now.st_size, st.st_size)
        b = dm.catalog()['alpha']
        self.assertIsNot(a, b)
        self.assertEqual(b.fn('check')({}), {'ok': 12345})

    def test_a_file_changed_while_loading_is_picked_up_by_the_next_call(self):
        """Відбиток береться ДО читання: правка під час вантаження не лишає в кеші старий код під новим відбитком."""
        d = self.mk('alpha', roles=(), server='def check(ctx):\n    return {"ok": True}\n')
        real = dm._build

        def build_then_edit(dd, folder):
            m = real(dd, folder)
            if os.path.dirname(dd) != self.mods:          # правимо лише модулі ЦЬОГО тесту, а не чужі теки (фікстури репо)
                return m
            sv = os.path.join(dd, 'server.py')
            _write(sv, 'def check(ctx):\n    return {"ok": 1234}\n')
            _bump(sv)
            return m
        with mock.patch.object(dm, '_build', build_then_edit):
            first = dm.catalog()['alpha']
        self.assertEqual(first.fn('check')({}), {'ok': True})
        self.assertEqual(dm.catalog()['alpha'].fn('check')({}), {'ok': 1234})

    def test_a_module_can_import_the_core(self):
        self.mk('uses-core', server='import builtins, deai_modules\nbuiltins._DEAI_SEEN = deai_modules\n' + ALL_FNS)
        self.assertEqual(dm.catalog()['uses-core'].status, 'ok')
        self.assertIs(builtins._DEAI_SEEN, dm)

    @staticmethod
    def imports_serve(src):
        """Чи імпортує джерело `serve` (`import serve`, `import serve as x`, `from serve import …`, у функції теж)."""
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import) and any(a.name.split('.')[0] == 'serve' for a in n.names):
                return True
            if isinstance(n, ast.ImportFrom) and n.level == 0 and (n.module or '').split('.')[0] == 'serve':
                return True
        return False

    def test_the_serve_import_detector_tells_an_import_from_a_mention(self):
        for src in ('import serve', 'import os, serve', 'import serve as sv', 'from serve import Handler',
                    'from serve.x import y', 'def f():\n    import serve\n'):
            self.assertTrue(self.imports_serve(src), src)
        for src in ('# import serve', 'x = "import serve"', 'import server', 'from servers import x',
                    'import deai_modules', 'from . import serve', 'import os.serve_x'):
            self.assertFalse(self.imports_serve(src), src)

    def test_real_builtin_modules_never_import_serve(self):
        """Вбудовані модулі живуть у `app/modules/` (їх додають Task 2/4; у Task 1 тека може бути
        порожньою — тут не стверджуємо, що вони є). Спільні правила беруть із `deai_modules`, не з `serve`."""
        for server in sorted(glob.glob(os.path.join(_REAL_BUILTIN_DIR(), '*', 'server.py'))):
            with open(server, encoding='utf-8') as f:
                self.assertFalse(self.imports_serve(f.read()), server)

    def test_caches_are_independent_per_folder(self):
        self.mk('one')
        self.mk('two')
        a, b = dm.catalog()['one'], dm.catalog()['two']
        self.assertIsNot(a, b)
        self.assertIsNot(a.fn('check'), b.fn('check'))


# ------------------------------------------------------------------------- вбудований `git-sync` через каркас

class RealGitSyncTest(Env):
    """Справжній `app/modules/git-sync` (а не фікстура), якого ядро вантажить і кличе: що `ctx` дає модулю `cache_dir`, що коди
    `vcs-*` проходять як є (`STATUS`), що необовʼязкові функції ролі досяжні, що `check` працює через `dm.check`."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(dm, 'builtin_dir', _REAL_BUILTIN_DIR)         # `Env` підмінив її на порожню теку
        p.start()
        self.addCleanup(p.stop)
        dm.reset_caches()
        self.sp = self.new_space()

    GIT_ENV = {'GIT_CONFIG_NOSYSTEM': '1', 'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@t',
               'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@t'}

    def git(self, args, cwd):
        subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True,
                       env=dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, **self.GIT_ENV))

    def bare(self, seed=False):
        """Локальний bare-репо (абсолютний шлях, без мережі); `seed` — з одним комітом у `main` (через «колегу»)."""
        origin = os.path.join(self.tmp, 'origin.git')
        os.makedirs(origin)
        self.git(['init', '--bare', '-q', '-b', 'main', '.'], origin)
        if seed:
            peer = os.path.join(self.tmp, 'peer')
            self.git(['clone', '-q', origin, peer], self.tmp)
            _write(os.path.join(peer, 'README.md'), 'seed\n')
            self.git(['add', '-A'], peer)
            self.git(['commit', '-qm', 'seed'], peer)
            self.git(['push', '-q', 'origin', 'HEAD:main'], peer)
        return origin

    def test_the_catalog_loads_it_as_a_vcs_module_with_the_optional_functions(self):
        m = dm.catalog()['git-sync']
        self.assertEqual((m.status, m.error, m.roles), ('ok', None, ['vcs']))
        for name in ('check', 'status', 'push', 'pull', 'validate', 'mirror_dir'):
            self.assertTrue(callable(m.fn(name)), name)
        self.assertIn('git-sync', dm.KNOWN_OTHER_MODULES)

    def test_check_without_a_repo_is_ok_through_the_frame(self):
        res = dm.check(self.sp, 'git-sync')
        self.assertIs(res['ok'], True)
        self.assertEqual(dm.last_check(self.sp['id'], 'git-sync'), res)

    def test_check_reads_the_settings_of_the_space_through_the_frame(self):
        """Без `repo` модуль теж каже `ok`, тож лише ДЕТАЛЬ доводить, що `ctx['settings']` дійшов до модуля: порожній
        віддалений репо → «гілки ще нема», з гілкою → «знайдено»."""
        dm.write_module_state(self.sp, 'git-sync', enabled=True, settings={'repo': self.bare()})
        res = dm.check(self.sp, 'git-sync')
        self.assertIs(res['ok'], True)
        self.assertIn('not on the remote yet', res['detail'])
        self.assertEqual(dm.last_check(self.sp['id'], 'git-sync'), res)
        shutil.rmtree(os.path.join(self.tmp, 'origin.git'))
        shutil.rmtree(os.path.join(self.tmp, 'peer'), ignore_errors=True)
        dm.write_module_state(self.sp, 'git-sync', enabled=True, settings={'repo': self.bare(seed=True), 'branch': 'main'})
        res = dm.check(self.sp, 'git-sync')
        self.assertIs(res['ok'], True)
        self.assertIn('branch main found', res['detail'])
        dm.write_module_state(self.sp, 'git-sync', enabled=True, settings={'branch': 'feature/x'})   # `repo` лишився з попереднього запису
        self.assertIn('branch feature/x is not on the remote yet', dm.check(self.sp, 'git-sync')['detail'])

    def test_check_refuses_a_missing_local_repo_and_a_bad_address_through_the_frame(self):
        """Відмови модуля — не винятки каркаса, а `ok: false` з кодом `vcs-*` (ядро кладе їх у `check`-результат як є)."""
        gone = os.path.join(self.tmp, 'nope.git')
        dm.write_module_state(self.sp, 'git-sync', enabled=True, settings={'repo': gone})
        res = dm.check(self.sp, 'git-sync')
        self.assertEqual((res['ok'], res['error']), (False, 'vcs-error'))
        self.assertIn('ls-remote failed', res['detail'])
        self.assertEqual(dm.last_check(self.sp['id'], 'git-sync'), res)
        dm.write_module_state(self.sp, 'git-sync', enabled=True, settings={'repo': 'ftp://example.invalid/x'})
        res = dm.check(self.sp, 'git-sync')
        self.assertEqual((res['ok'], res['error']), (False, 'vcs-bad-target'))

    def test_a_vcs_code_of_the_module_passes_through_call_with_its_status(self):
        """`validate` кидає `ctx['ModuleError']('vcs-bad-target')`: код у `STATUS` — `call()` не сплющує його в `module-error`."""
        m = dm.catalog()['git-sync']
        ctx = dm.module_ctx(self.sp, 'git-sync')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(m, 'validate', ctx, {'repo': '', 'task': 't1'})
        self.assertEqual((cm.exception.code, cm.exception.status), ('vcs-bad-target', 400))

    def test_the_cache_dir_never_leaves_the_cache_whatever_the_ids(self):
        """Id простору лишається в `cache_dir` лише коли він — `spaces.SPACE_ID_RE`; решта (чужа форма запису, `..`, абсолютний шлях,
        слеш, регістр, довжина) → `_`: шлях не виходить з `<DEAI_HOME>/cache`. Id модуля з каталогу вже перевірено маніфестом."""
        cache = os.path.join(spaces.home(), 'cache')
        for bad in ('../../x', '/abs', '..', '.', 'a/b', 'a\\b', '', 'A', '-x', 'x' * 41, 'a\x00b', None, 5, 5.5, ['a']):
            with self.subTest(bad=bad):
                got = dm.module_ctx({'id': bad, 'path': ''}, 'git-sync')['cache_dir']
                self.assertEqual(got, os.path.join(cache, '_', 'git-sync'))
        self.assertEqual(dm.module_ctx({'id': 'ok-1', 'path': ''}, 'git-sync')['cache_dir'],
                         os.path.join(cache, 'ok-1', 'git-sync'))
        self.assertEqual(dm.module_ctx(dict(spaces.IMPLICIT), 'git-sync')['cache_dir'],
                         os.path.join(cache, 'legacy', 'git-sync'))

    def test_an_invalid_module_id_is_refused_instead_of_becoming_a_path(self):
        """Модуль із каталогу має `id` за `ID_RE`; обʼєкт з іншим — помилка ядра, а не спільне відро `_` для різних модулів."""
        for bad in ('../evil', '/abs', '..', 'a/b', '', 'A', 'x' * 41):
            with self.subTest(bad=bad):
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.module_ctx(self.sp, dm.Module(bad, roles=['vcs']))
                self.assertEqual(cm.exception.code, 'module-error')

    def test_the_mirror_folder_lies_under_the_cache_dir_of_the_context_and_is_not_created(self):
        m = dm.catalog()['git-sync']
        ctx = dm.module_ctx(self.sp, 'git-sync')
        base = os.path.join(spaces.home(), 'cache', self.sp['id'], 'git-sync')
        self.assertEqual(ctx['cache_dir'], base)
        got = dm.call(m, 'mirror_dir', ctx, {'repo': 'git@github.com:o/r.git', 'path': 'mockup/t1', 'task': 't1'})
        self.assertTrue(got.startswith(base + os.sep), got)
        self.assertFalse(os.path.exists(base), 'mirror_dir нічого не створює')
        good = dm.call(m, 'validate', ctx, {'repo': 'git@github.com:o/r.git', 'path': '/mockup/t1/'})
        self.assertEqual((good['repo'], good['path'], good['branch']), ('git@github.com:o/r.git', 'mockup/t1', 'main'))


# ---------------------------------------------------------------------------------------------- виклик

class FindToolAndFullText(unittest.TestCase):
    """4b-1: `ctx['find_tool']` (лише npx/node) і повний текст помилки модуля (`ModuleError.full`)."""

    def tearDown(self):
        dm.set_tool_finder(None)

    def test_find_tool_only_known_names(self):
        seen = []
        dm.set_tool_finder(lambda name: seen.append(name) or f'/x/{name}')
        f = dm._find_tool
        self.assertEqual(f('npx'), '/x/npx')
        self.assertEqual(f('node'), '/x/node')
        self.assertIsNone(f('sh'))
        self.assertIsNone(f('../npx'))
        self.assertEqual(seen, ['npx', 'node'])           # невідоме імʼя шукач навіть не бачить

    def test_find_tool_default_is_which(self):
        dm.set_tool_finder(None)
        with mock.patch('shutil.which', lambda n: '/w/' + n):
            self.assertEqual(dm._find_tool('npx'), '/w/npx')

    def test_find_tool_finder_non_path_answers_are_none(self):
        for bad in ('', 5):
            dm.set_tool_finder(lambda name, bad=bad: bad)
            self.assertIsNone(dm._find_tool('npx'), repr(bad))

    def test_module_error_full_text_survives_call_in_the_timeout_thread(self):
        secret = 'S3CR3T-value-long-enough'
        long = ('x' * 900) + secret + ('y' * 100)

        def fn(ctx):
            raise dm.ModuleError('vercel-deploy', message=long)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(types.SimpleNamespace(id='t'), fn, {'secrets': {'token': secret}}, timeout=2)   # потік іменується за module.id
        e = cm.exception
        self.assertEqual((e.code, len(e.message)), ('vercel-deploy', 300))
        self.assertNotIn(secret, e.full)
        self.assertIn('***', e.full)
        self.assertTrue(e.full.endswith('y' * 100))

    def test_secret_across_the_full_text_limit_leaves_no_prefix(self):
        """Секрет, що перетинає межу `MAX_FULL_MESSAGE`: конструктор обрізав його посередині, тож ціле значення `_scrub`
        не знайде — `full` не має закінчуватись префіксом секрету (≥4 знаки)."""
        secret = 'S3CR3T-value-long-enough'
        for cut in (1, 4, 10, len(secret) - 1):
            long = ('x' * (dm.MAX_FULL_MESSAGE - cut)) + secret + 'tail'

            def fn(ctx, long=long):
                raise dm.ModuleError('vercel-deploy', message=long)
            with self.assertRaises(dm.ModuleError) as cm:
                dm.call(fn, fn, {'secrets': {'token': secret}})
            full = cm.exception.full
            self.assertLessEqual(len(full), dm.MAX_FULL_MESSAGE)
            for n in range(4, len(secret) + 1):
                self.assertFalse(full.endswith(secret[:n]), (cut, n))

    def test_find_tool_finder_failure_is_none(self):
        def boom(name):
            raise OSError('no')
        dm.set_tool_finder(boom)
        self.assertIsNone(dm._find_tool('npx'))

    def test_module_error_full_text_survives_call(self):
        secret = 'S3CR3T-value-long-enough'
        long = ('x' * 900) + secret + ('y' * 100)

        def fn(ctx):
            raise dm.ModuleError('vercel-deploy', message=long)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(fn, fn, {'secrets': {'token': secret}})
        e = cm.exception
        self.assertEqual(e.code, 'vercel-deploy')
        self.assertEqual(len(e.message), 300)
        self.assertNotIn(secret, e.full)
        self.assertIn('***', e.full)
        self.assertTrue(e.full.endswith('y' * 100))

    def test_new_codes_have_status(self):
        for code, st in (('no-node', 409), ('vercel-login', 409), ('vercel-scope', 409),
                         ('vercel-deploy', 502), ('vercel-no-url', 502)):
            self.assertEqual(dm.STATUS[code], st, code)


class CallTest(Env):
    SECRET = 's3cr3t-Pa55'

    def setUp(self):
        super().setUp()
        self.mk('fail', server=FAILING_SERVER)
        self.m = dm.catalog()['fail']
        self.ctx = {'space': {'id': 's', 'path': '/x'}, 'settings': {}, 'secrets': {'password': self.SECRET}}

    def call(self, kind, **kw):
        return dm.call(self.m, 'publish', self.ctx, '/build', {'kind': kind}, **kw)

    def test_result_passes_through(self):
        self.assertEqual(self.call('ok'), {'path': '/ok'})
        self.assertEqual(dm.call(self.m, 'check', self.ctx), {'ok': True})

    def test_base_exceptions_become_module_error(self):
        for kind, part in (('value', 'ValueError'), ('exit', 'SystemExit')):
            with self.assertRaises(dm.ModuleError) as cm:
                self.call(kind)
            self.assertEqual((cm.exception.code, cm.exception.status), ('module-error', 502), kind)
            self.assertIn(part, cm.exception.message, kind)

    def test_keyboard_interrupt_is_not_swallowed(self):
        with self.assertRaises(KeyboardInterrupt):
            self.call('kbd')

    def test_secret_values_are_cut_out_of_the_message(self):
        with self.assertRaises(dm.ModuleError) as cm:
            self.call('value')
        msg = cm.exception.message
        self.assertNotIn(self.SECRET, msg)
        self.assertIn('boom', msg)
        self.assertIn('***', msg)
        self.assertNotIn(self.SECRET, str(cm.exception))

    def test_secret_in_repr_form_is_cut_too(self):
        self.ctx['secrets']['password'] = 'pa"ss\'wd\\é'
        with self.assertRaises(dm.ModuleError) as cm:
            self.call('repr')
        self.assertNotIn('ss', cm.exception.message.replace('***', ''))

    def test_json_and_url_quoted_forms_of_a_secret_are_cut_too(self):
        self.ctx['secrets']['password'] = '/@ö"'
        for kind, leak in (('json', ('u00f6', '/@')), ('json-utf8', ('/@ö',)), ('quote', ('%2F', '%C3', '%40'))):
            for timeout in (None, 3):
                with self.assertRaises(dm.ModuleError) as cm:
                    self.call(kind, timeout=timeout)
                msg = cm.exception.message
                self.assertIn('***', msg, kind)
                for bit in leak:
                    self.assertNotIn(bit, msg, f'{kind}: {msg!r}')

    def test_known_codes_raised_by_a_module_pass_through_and_unknown_ones_do_not(self):
        self.mk('passer', server=PASS_SERVER, settings=[{'key': 'password', 'type': 'secret'}])
        m = dm.catalog()['passer']
        ctx = {'space': {'id': 's', 'path': '/x'}, 'settings': {}, 'secrets': {'password': 'hunter2-secret'}}
        for timeout in (None, 3):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.call(m, 'publish', ctx, '/b', {'kind': 'folder'}, timeout=timeout)
            e = cm.exception
            self.assertEqual((e.code, e.status), ('bad-folder', 409))
            self.assertNotIn('hunter2-secret', e.message)
            self.assertIn('***', e.message)
            self.assertLessEqual(len(e.message), 300)
            self.assertIsNone(e.__context__)
            with self.assertRaises(dm.ModuleError) as cm:
                dm.call(m, 'publish', ctx, '/b', {'kind': 'role'}, timeout=timeout)
            self.assertEqual((cm.exception.code, cm.exception.status), ('role-taken', 409))
            with self.assertRaises(dm.ModuleError) as cm:           # статус — з таблиці, не від модуля
                dm.call(m, 'publish', ctx, '/b', {'kind': 'status'}, timeout=timeout)
            self.assertEqual((cm.exception.code, cm.exception.status), ('bad-folder', 409))
            with self.assertRaises(dm.ModuleError) as cm:           # невідомий код → module-error
                dm.call(m, 'publish', ctx, '/b', {'kind': 'weird'}, timeout=timeout)
            e = cm.exception
            self.assertEqual((e.code, e.status), ('module-error', 502))
            self.assertIn('weird-code', e.message)
            self.assertNotIn('hunter2-secret', e.message)

    def test_a_secret_straddling_the_cut_does_not_leak_a_prefix_through_a_passed_through_error(self):
        """`ModuleError` ріже текст до 300 ще в конструкторі; вирізати секрет треба з ПОВНОГО тексту.
        Секрет довгий навмисно: у гілці `module-error` до тексту додається префікс `ModuleError: код: `, тож
        у вікно ≤300 потрапляють лише перші ~275 символів повідомлення, а недорізаний секрет (його початок
        стоїть ДО 275 і кінець ПІСЛЯ 300) лишив би там видимий префікс."""
        self.mk('passer', server=PASS_SERVER, settings=[{'key': 'password', 'type': 'secret'}])
        m = dm.catalog()['passer']
        secret = 'hunter2-' + 'Q' * 50
        ctx = {'space': {'id': 's', 'path': '/x'}, 'settings': {}, 'secrets': {'password': secret}}
        for kind in ('straddle', 'weird-straddle'):
            for timeout in (None, 3):
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.call(m, 'publish', ctx, '/b', {'kind': kind}, timeout=timeout)
                msg = cm.exception.message
                self.assertLessEqual(len(msg), 300, kind)
                for piece in ('hun', 'QQ'):                          # навіть короткий початок чи шматок секрету — витік
                    self.assertNotIn(piece, msg, f'{kind}: {msg[-30:]!r}')
                self.assertIn('***', msg, kind)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(m, 'publish', ctx, '/b', {'kind': 'straddle'})
        self.assertEqual(cm.exception.code, 'bad-folder')

    def test_the_error_keeps_the_full_text_but_exposes_300_characters(self):
        e = dm.ModuleError('bad-folder', 409, 'z' * 1000)
        self.assertEqual(len(e.message), 300)
        self.assertEqual(len(str(e)), len('bad-folder: ') + 300)
        self.assertEqual(e._full, 'z' * 1000)                   # а `_run` вирізає секрети саме з нього

    def test_the_full_text_is_capped_at_64_kib(self):
        """Повний текст — для вирізання секретів, а не безмежне сховище: модуль може кинути гігабайтний рядок."""
        self.assertEqual(dm.MAX_FULL_MESSAGE, 65536)
        e = dm.ModuleError('bad-folder', 409, 'z' * 200000)
        self.assertEqual(len(e._full), 65536)
        self.assertEqual(len(e.message), 300)

    def test_a_lone_surrogate_already_in_secrets_json_does_not_break_the_scrubbing(self):
        self.mk('passer', server=PASS_SERVER, settings=[{'key': 'password', 'type': 'secret'}])
        sp = self.new_space()
        os.makedirs(self.deai, exist_ok=True)
        _write(self.secrets_file, '{"%s": {"passer": {"password": "\\ud800hunter2"}}}' % sp['id'])
        ctx = dm.module_ctx(sp, 'passer')
        self.assertEqual(ctx['secrets']['password'], '\ud800hunter2')
        m = dm.catalog()['passer']
        for timeout in (None, 3):
            with self.assertRaises(dm.ModuleError) as cm:        # а не `UnicodeEncodeError` із `quote()`
                dm.call(m, 'publish', ctx, '/b', {'kind': 'weird'}, timeout=timeout)
            self.assertEqual(cm.exception.code, 'module-error')
            self.assertNotIn('hunter2', cm.exception.message)

    def test_a_check_that_raises_a_known_code_is_remembered_under_that_code(self):
        self.mk('passer', server=PASS_SERVER, settings=[{'key': 'password', 'type': 'secret'}])
        sp = self.new_space()
        dm.write_secrets(sp['id'], 'passer', {'password': 'boom'})
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(sp, 'passer')
        self.assertEqual(cm.exception.code, 'bad-folder')
        last = dm._LAST_CHECK[(sp['id'], 'passer')]
        self.assertEqual((last['ok'], last['error'], last['detail']), (False, 'bad-folder', 'check says no'))

    def test_scrub_happens_before_truncation(self):
        """Секрет, що перетинає межу 300 символів, не мусить пролізти кінцівкою."""
        with self.assertRaises(dm.ModuleError) as cm:
            self.call('long')
        msg = cm.exception.message
        self.assertLessEqual(len(msg), 300)
        self.assertNotIn(self.SECRET[:5], msg)

    def test_the_error_carries_no_traceback_with_the_secret(self):
        with self.assertRaises(dm.ModuleError) as cm:
            self.call('value')
        e = cm.exception
        self.assertIsNone(e.__cause__)
        self.assertIsNone(e.__context__)
        self.assertNotIn(self.SECRET, ''.join(traceback.format_exception(type(e), e, e.__traceback__)))

    def test_timeout_raises_check_timeout_and_does_not_wait(self):
        t0 = time.monotonic()
        with self.assertRaises(dm.ModuleError) as cm:
            self.call('slow', timeout=0.2)
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual((cm.exception.code, cm.exception.status), ('check-timeout', 504))

    def test_the_abandoned_worker_is_a_daemon_thread(self):
        """Потік, що не вклався в тайм-аут, не мусить тримати процес сервера при виході."""
        with self.assertRaises(dm.ModuleError):
            self.call('slow', timeout=0.2)
        workers = [t for t in threading.enumerate() if t.name == 'deai-module-fail-publish']
        self.assertEqual(len(workers), 1)
        self.assertTrue(workers[0].daemon)

    def test_with_timeout_results_and_errors_still_work(self):
        self.assertEqual(self.call('ok', timeout=3), {'path': '/ok'})
        for kind in ('value', 'exit'):
            with self.assertRaises(dm.ModuleError) as cm:
                self.call(kind, timeout=3)
            self.assertEqual(cm.exception.code, 'module-error', kind)
        with self.assertRaises(dm.ModuleError) as cm:
            self.call('value', timeout=3)
        self.assertNotIn(self.SECRET, cm.exception.message)

    def test_worker_thread_inherits_the_request_space(self):
        self.mk('whoami', server='import spaces\ndef check(ctx):\n'
                                 '    return {"ok": True, "detail": repr(spaces.request_space_id())}\n'
                                 'def publish(ctx, b, t):\n    return {}\n')
        m = dm.catalog()['whoami']
        with spaces.request_space('abc'):
            self.assertEqual(dm.call(m, 'check', self.ctx, timeout=3)['detail'], "'abc'")
            self.assertEqual(dm.call(m, 'check', self.ctx)['detail'], "'abc'")

    def test_unknown_function_and_broken_module(self):
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(self.m, 'tokens', self.ctx)             # роль, якої модуль не має
        self.assertEqual(cm.exception.code, 'module-error')
        self.mk('broken', patch={'api': 2})
        with self.assertRaises(dm.ModuleError) as cm:
            dm.call(dm.catalog()['broken'], 'check', self.ctx)
        self.assertEqual(cm.exception.code, 'bad-manifest')

    def test_a_callable_may_be_passed_instead_of_a_name(self):
        self.assertEqual(dm.call(self.m, self.m.fn('check'), self.ctx), {'ok': True})


# ------------------------------------------------------------------------------------ стан у space.json

class StateTest(Env):
    def test_space_modules_reads_normalised_entries(self):
        sp = self.new_space()
        _write(self.space_json(sp), {'name': 'Alpha', 'modules': {
            'a': {'enabled': True, 'settings': {'x': '1'}},
            'b': {'enabled': 'yes'},                         # не рівно True — вимкнений
            'c': 'garbage',                                  # не обʼєкт — як відсутній
            'd': {'settings': ['no']}}})
        self.assertEqual(dm.space_modules(sp), {
            'a': {'enabled': True, 'settings': {'x': '1'}},
            'b': {'enabled': False, 'settings': {}},
            'd': {'enabled': False, 'settings': {}}})

    def test_space_modules_without_file_or_path_is_empty(self):
        sp = self.new_space()
        os.remove(self.space_json(sp))
        self.assertEqual(dm.space_modules(sp), {})
        self.assertEqual(dm.space_modules(dict(spaces.IMPLICIT)), {})       # шлях порожній — диска нема
        _write(self.space_json(sp), {'name': 'A'})
        self.assertEqual(dm.space_modules(sp), {})
        _write(self.space_json(sp), {'name': 'A', 'modules': None})
        self.assertEqual(dm.space_modules(sp), {})

    def test_unreadable_space_json_is_409(self):
        sp = self.new_space()
        for bad in ('{nope', '[]', '"s"', json.dumps({'modules': []}),
                    ' ' * (spaces.MAX_JSON_BYTES + 10)):
            _write(self.space_json(sp), bad)
            with self.assertRaises(dm.ModuleError) as cm:
                dm.space_modules(sp)
            self.assertEqual((cm.exception.code, cm.exception.status), ('space-json-unreadable', 409), bad[:12])
        os.remove(self.space_json(sp))
        os.makedirs(self.space_json(sp))                    # папка замість файла — теж «не прочитати»
        with self.assertRaises(dm.ModuleError) as cm:
            dm.space_modules(sp)
        self.assertEqual(cm.exception.code, 'space-json-unreadable')

    # ---- неявне типове ----
    def test_static_publish_is_implicitly_on_without_integrations_and_writes_nothing(self):
        self.mk('static-publish', settings=[{'key': 'folder', 'type': 'path', 'default': '{home}/p/{space_id}'}])
        sp = self.new_space()
        before = _md5(self.space_json(sp))
        st = dm.effective_state(sp)['static-publish']
        self.assertEqual((st['enabled'], st['implicit']), (True, True))
        self.assertEqual(st['settings'], {'folder': '{home}/p/{space_id}'})     # символьно, з типового
        self.assertEqual(dm.provider('publish', sp).id, 'static-publish')
        dm.capabilities(sp)
        self.assertEqual(_md5(self.space_json(sp)), before, 'неявне типове не пише на диск')

    def test_static_publish_is_not_implicit_in_an_integrations_space(self):
        self.mk('static-publish')
        sp = self.new_space(integrations=True)
        st = dm.effective_state(sp)['static-publish']
        self.assertEqual((st['enabled'], st['implicit']), (False, False))

    def test_explicit_decision_replaces_the_implicit_one(self):
        self.mk('static-publish')
        sp = self.new_space()
        _write(self.space_json(sp), {'modules': {'static-publish': {'enabled': False}}})
        st = dm.effective_state(sp)['static-publish']
        self.assertEqual((st['enabled'], st['implicit']), (False, False))
        _write(self.space_json(sp), {'modules': {'static-publish': {'enabled': True}}})
        st = dm.effective_state(sp)['static-publish']
        self.assertEqual((st['enabled'], st['implicit']), (True, False))

    def test_only_static_publish_is_implicit(self):
        self.mk('other-publish')
        sp = self.new_space()
        st = dm.effective_state(sp)['other-publish']
        self.assertEqual((st['enabled'], st['implicit']), (False, False))

    def test_effective_state_hides_secret_keys_and_merges_defaults(self):
        self.pub_secret_module()
        sp = self.new_space()
        _write(self.space_json(sp), {'modules': {'pub': {'enabled': True, 'settings': {
            'password': 'leaked-by-hand', 'folder': '~/mine'}}}})
        st = dm.effective_state(sp)['pub']
        self.assertEqual(st['settings'], {'folder': '~/mine'})
        self.assertNotIn('leaked-by-hand', json.dumps(dm.effective_state(sp)))

    # ---- запис ----
    def test_write_preserves_unknown_keys_and_other_modules(self):
        self.mk('alpha', settings=[{'key': 'note', 'type': 'text'}])
        self.mk('beta', roles=('tokens',))
        sp = self.new_space()
        _write(self.space_json(sp), {'name': 'Alpha', 'color': 'space-1', 'future': {'a': [1, 2]},
                                     'modules': {'beta': {'enabled': True, 'extra': 7,
                                                          'settings': {'k': 'v'}},
                                                 'ghost': {'enabled': True}}})
        dm.write_module_state(sp, 'alpha', enabled=True, settings={'note': None})
        data = _read(self.space_json(sp))
        self.assertEqual(data['future'], {'a': [1, 2]})
        self.assertEqual((data['name'], data['color']), ('Alpha', 'space-1'))
        self.assertEqual(data['modules']['beta'], {'enabled': True, 'extra': 7, 'settings': {'k': 'v'}})
        self.assertEqual(data['modules']['ghost'], {'enabled': True})
        self.assertTrue(data['modules']['alpha']['enabled'])
        dm.write_module_state(sp, 'beta', enabled=False)
        self.assertEqual(_read(self.space_json(sp))['modules']['beta'],
                         {'enabled': False, 'extra': 7, 'settings': {'k': 'v'}})

    def test_symbolic_paths_are_stored_as_given(self):
        self.mk('alpha', settings=[{'key': 'folder', 'type': 'path'}])
        sp = self.new_space()
        dm.write_module_state(sp, 'alpha', enabled=True, settings={'folder': '{home}/pub/{space_id}'})
        self.assertEqual(_read(self.space_json(sp))['modules']['alpha']['settings'],
                         {'folder': '{home}/pub/{space_id}'})
        dm.write_module_state(sp, 'alpha', settings={'folder': '~/x'})
        self.assertEqual(_read(self.space_json(sp))['modules']['alpha']['settings'], {'folder': '~/x'})

    def test_settings_patch_merges_and_none_removes(self):
        self.mk('alpha', settings=[{'key': 'a', 'type': 'text'}, {'key': 'b', 'type': 'text'}])
        sp = self.new_space()
        dm.write_module_state(sp, 'alpha', enabled=True, settings={'a': '1', 'b': '2'})
        dm.write_module_state(sp, 'alpha', settings={'a': '9', 'b': None})
        self.assertEqual(_read(self.space_json(sp))['modules']['alpha']['settings'], {'a': '9'})

    def test_unreadable_space_json_is_409_and_untouched(self):
        self.mk('alpha')
        sp = self.new_space()
        _write(self.space_json(sp), '{"modules": {"alpha": ')
        before = _md5(self.space_json(sp))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'alpha', enabled=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('space-json-unreadable', 409))
        self.assertEqual(_md5(self.space_json(sp)), before)
        self.assertEqual([n for n in os.listdir(sp['path']) if n.endswith('.tmp')], [])

    def test_layer_off_or_empty_path_is_spaces_off(self):
        self.mk('alpha')
        sp = self.new_space()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(dict(spaces.IMPLICIT), 'alpha', enabled=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('spaces-off', 409))
        del os.environ['DEAI_HOME']                          # лишився лише DC_TASKS_FILE — шар вимкнено
        self.assertFalse(spaces.layer_on())
        before = _md5(self.space_json(sp))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'alpha', enabled=True)
        self.assertEqual(cm.exception.code, 'spaces-off')
        self.assertEqual(_md5(self.space_json(sp)), before)

    def test_role_taken(self):
        self.mk('pub-a')
        self.mk('pub-b')
        sp = self.new_space()
        dm.write_module_state(sp, 'pub-a', enabled=True)
        before = _md5(self.space_json(sp))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'pub-b', enabled=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('role-taken', 409))
        self.assertIn('pub-a', cm.exception.message)
        self.assertEqual(_md5(self.space_json(sp)), before)
        dm.write_module_state(sp, 'pub-a', enabled=True)     # сам себе — не конфлікт
        dm.write_module_state(sp, 'pub-b', settings={})      # налаштування вимкненого — теж
        dm.write_module_state(sp, 'pub-a', enabled=False)
        dm.write_module_state(sp, 'pub-b', enabled=True)     # звільнена роль — можна
        self.assertEqual(dm.provider('publish', sp).id, 'pub-b')

    def test_role_taken_counts_the_implicit_static_publish(self):
        self.mk('static-publish')
        self.mk('other-publish')
        sp = self.new_space()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'other-publish', enabled=True)
        self.assertEqual(cm.exception.code, 'role-taken')
        dm.write_module_state(sp, 'static-publish', enabled=False)
        dm.write_module_state(sp, 'other-publish', enabled=True)
        ig = self.new_space('Beta', integrations=True)       # з інтеграціями неявного нема — роль вільна
        dm.write_module_state(ig, 'other-publish', enabled=True)

    def test_role_taken_ignores_modules_that_cannot_provide(self):
        self.mk('pub-a')
        self.mk('pub-broken', server='def check(:\n')
        sp = self.new_space()
        dm.write_module_state(sp, 'pub-broken', enabled=True)       # зламаний не постачальник
        dm.write_module_state(sp, 'pub-a', enabled=True)
        _write(self.space_json(sp), {'modules': {'ghost': {'enabled': True}}})   # відсутній — теж
        dm.write_module_state(sp, 'pub-a', enabled=True)

    def test_role_taken_across_different_roles_is_fine(self):
        self.mk('pub-a', roles=('publish',))
        self.mk('tok-a', roles=('tokens',))
        sp = self.new_space()
        dm.write_module_state(sp, 'pub-a', enabled=True)
        dm.write_module_state(sp, 'tok-a', enabled=True)

    def test_role_taken_holds_under_a_race(self):
        """Перевірка на СВІЖО прочитаному стані ПІД локом: п'ять потоків, одна роль — переможе один.
        Читання `space.json` штучно сповільнене, щоб перевірка до локу гарантовано бачила порожній стан."""
        for i in range(5):
            self.mk(f'pub-{i}')
        sp = self.new_space()
        real = dm._load_space_json

        def slow(path):
            data = real(path)
            time.sleep(0.03)
            return data
        with mock.patch.object(dm, '_load_space_json', slow):
            out = race(5, lambda i: dm.write_module_state(sp, f'pub-{i}', enabled=True))
        ok = [r for r in out if r[0] == 'ok']
        errs = [r[1] for r in out if r[0] == 'err']
        self.assertEqual(len(ok), 1, out)
        self.assertEqual({e.code for e in errs}, {'role-taken'})
        enabled = [k for k, v in _read(self.space_json(sp))['modules'].items() if v['enabled']]
        self.assertEqual(len(enabled), 1)

    def test_nothing_is_loaded_under_the_write_lock(self):
        self.pub_secret_module()
        sp = self.new_space()
        real = dm.catalog
        held = []

        def spy(space=None):
            held.append(spaces.WRITE_LOCK.locked())
            return real(space)
        with mock.patch.object(dm, 'catalog', spy):
            dm.write_module_state(sp, 'pub', enabled=True)
            dm.write_secrets(sp['id'], 'pub', {'password': 'x'})
        self.assertGreaterEqual(len(held), 2)
        self.assertFalse(any(held), 'каталог/модулі вантажимо ДО локу, не під ним')

    def test_validation_errors(self):
        self.mk('alpha', settings=[
            {'key': 'text', 'type': 'text'}, {'key': 'flag', 'type': 'bool'},
            {'key': 'mode', 'type': 'select', 'options': [{'value': 'a', 'label': 'A'}]},
            {'key': 'folder', 'type': 'path'}, {'key': 'pw', 'type': 'secret'}])
        sp = self.new_space()
        before = _md5(self.space_json(sp))
        for bad in ({'nope': 'x'}, {'text': 5}, {'flag': 'yes'}, {'mode': 'zzz'}, {'folder': ''},
                    {'folder': 7}, {'pw': 'secret-in-space-json'}, {'text': 'x' * 5000}, 'not-a-dict'):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_module_state(sp, 'alpha', enabled=True, settings=bad)
            self.assertEqual((cm.exception.code, cm.exception.status), ('bad-settings', 400), bad)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'alpha', enabled='yes')
        self.assertEqual(cm.exception.code, 'bad-settings')
        self.assertEqual(_md5(self.space_json(sp)), before, 'відмова валідації нічого не пише')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'ghost', enabled=True)
        self.assertEqual((cm.exception.code, cm.exception.status), ('unknown-module', 404))

    def test_a_settings_write_never_flips_the_implicit_state(self):
        self.mk('static-publish', settings=[{'key': 'folder', 'type': 'path'}])
        sp = self.new_space()
        st = dm.write_module_state(sp, 'static-publish', settings={'folder': '~/p'})
        self.assertEqual(st['enabled'], True)
        self.assertEqual(_read(self.space_json(sp))['modules']['static-publish']['enabled'], True)
        self.assertEqual(dm.provider('publish', sp).id, 'static-publish')

    def test_disable_keeps_settings(self):
        self.mk('alpha', settings=[{'key': 'a', 'type': 'text'}])
        sp = self.new_space()
        dm.write_module_state(sp, 'alpha', enabled=True, settings={'a': 'v'})
        st = dm.write_module_state(sp, 'alpha', enabled=False)
        self.assertEqual((st['enabled'], st['settings']), (False, {'a': 'v'}))
        self.assertEqual(_read(self.space_json(sp))['modules']['alpha'],
                         {'enabled': False, 'settings': {'a': 'v'}})

    def test_an_unwritable_space_folder_is_unwritable_not_a_crash(self):
        if os.geteuid() == 0:
            self.skipTest('root обходить права на теку')
        self.mk('alpha')
        sp = self.new_space()
        before = _md5(self.space_json(sp))
        os.chmod(sp['path'], 0o555)
        try:
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_module_state(sp, 'alpha', enabled=True)
        finally:
            os.chmod(sp['path'], 0o755)                      # інакше tearDown не зніме тимчасову теку
        self.assertEqual((cm.exception.code, cm.exception.status), ('unwritable', 500))
        self.assertEqual(_md5(self.space_json(sp)), before)

    def test_lone_surrogates_are_bad_settings_or_unwritable_never_a_crash(self):
        self.mk('alpha', settings=[{'key': 'text', 'type': 'text'}, {'key': 'folder', 'type': 'path'}])
        sp = self.new_space()
        for bad in ({'text': '\ud800'}, {'folder': '/a/\udcff'}):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_module_state(sp, 'alpha', enabled=True, settings=bad)
            self.assertEqual(cm.exception.code, 'bad-settings', bad)
        # сурогат, що вже лежить у файлі (валідний JSON-екран `\ud800`), на диск не запишеться
        _write(self.space_json(sp), '{"note": "\\ud800"}')
        before = _md5(self.space_json(sp))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(sp, 'alpha', enabled=True)
        self.assertEqual(cm.exception.code, 'unwritable')
        self.assertEqual(_md5(self.space_json(sp)), before)
        self.assertEqual([n for n in os.listdir(sp['path']) if n.endswith('.tmp')], [])

    def test_empty_write_does_not_touch_the_disk(self):
        self.mk('static-publish')
        sp = self.new_space()
        before = _md5(self.space_json(sp))
        st = dm.write_module_state(sp, 'static-publish')
        self.assertEqual((st['enabled'], st['implicit']), (True, True))
        self.assertEqual(_md5(self.space_json(sp)), before)

    def test_new_space_json_is_0644_and_existing_mode_is_kept(self):
        self.mk('alpha')
        sp = self.new_space()
        os.remove(self.space_json(sp))
        dm.write_module_state(sp, 'alpha', enabled=True)
        self.assertEqual(_mode(self.space_json(sp)), 0o644)
        os.chmod(self.space_json(sp), 0o664)
        dm.write_module_state(sp, 'alpha', enabled=False)
        self.assertEqual(_mode(self.space_json(sp)), 0o664)

    def test_space_folder_is_created_when_missing(self):
        self.mk('alpha')
        sp = {'id': 'ghost', 'path': self.hp('not-yet', 'there'), 'legacy': False, 'integrations': False}
        dm.write_module_state(sp, 'alpha', enabled=True)
        self.assertTrue(_read(os.path.join(sp['path'], 'space.json'))['modules']['alpha']['enabled'])


# ------------------------------------------------------------------------------------------- секрети

class SecretsTest(Env):
    def setUp(self):
        super().setUp()
        self.pub_secret_module('pub')
        self.pub_secret_module('other')

    def test_write_creates_the_file_0600_in_a_0700_home(self):
        self.assertFalse(os.path.exists(self.deai))
        dm.write_secrets('sp', 'pub', {'password': 'pw1'})
        self.assertEqual(_mode(self.secrets_file), 0o600)
        self.assertEqual(_mode(self.deai), 0o700)
        self.assertEqual(_read(self.secrets_file), {'sp': {'pub': {'password': 'pw1'}}})

    def test_write_tightens_a_loose_file_and_home(self):
        os.makedirs(self.deai)
        os.chmod(self.deai, 0o755)
        _write(self.secrets_file, {})
        os.chmod(self.secrets_file, 0o644)
        dm.write_secrets('sp', 'pub', {'password': 'pw1'})
        self.assertEqual(_mode(self.secrets_file), 0o600)
        self.assertEqual(_mode(self.deai), 0o700)
        dm.write_secrets('sp', 'pub', {'token': 'tk'})
        self.assertEqual(_mode(self.secrets_file), 0o600)

    def test_patch_semantics_absent_keeps_none_deletes_string_writes(self):
        dm.write_secrets('sp', 'pub', {'password': 'pw1', 'token': 'tk1'})
        dm.write_secrets('sp', 'pub', {'password': 'pw2'})                 # token відсутній — лишився
        self.assertEqual(dm.read_secrets('sp', 'pub'), {'password': 'pw2', 'token': 'tk1'})
        dm.write_secrets('sp', 'pub', {'token': None})                      # None — видалено
        self.assertEqual(dm.read_secrets('sp', 'pub'), {'password': 'pw2'})
        dm.write_secrets('sp', 'pub', {})                                   # порожній патч — без змін
        self.assertEqual(dm.read_secrets('sp', 'pub'), {'password': 'pw2'})

    def test_empty_containers_are_cleaned(self):
        dm.write_secrets('sp', 'pub', {'password': 'pw1'})
        dm.write_secrets('sp', 'pub', {'password': None})
        self.assertEqual(_read(self.secrets_file), {})

    def test_other_space_and_module_are_isolated(self):
        dm.write_secrets('sp', 'pub', {'password': 'pw1'})
        dm.write_secrets('sp2', 'pub', {'password': 'pw-other-space'})
        dm.write_secrets('sp', 'other', {'password': 'pw-other-module'})
        self.assertEqual(dm.read_secrets('sp', 'pub'), {'password': 'pw1'})
        self.assertEqual(dm.read_secrets('sp3', 'pub'), {})                 # чужий простір — порожньо
        self.assertEqual(dm.read_secrets('sp', 'ghost'), {})
        dm.write_secrets('sp', 'pub', {'password': None})
        self.assertEqual(dm.read_secrets('sp2', 'pub'), {'password': 'pw-other-space'})
        self.assertEqual(dm.read_secrets('sp', 'other'), {'password': 'pw-other-module'})

    def test_read_without_file_is_empty_and_creates_nothing(self):
        self.assertEqual(dm.read_secrets('sp', 'pub'), {})
        self.assertFalse(os.path.exists(self.deai))

    def test_validation(self):
        before = None
        for mid, patch in (('ghost', {'password': 'x'}),):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_secrets('sp', mid, patch)
            self.assertEqual((cm.exception.code, cm.exception.status), ('unknown-module', 404))
        for bad in ({'folder': 'x'}, {'nope': 'x'}, {'password': 5}, {'password': ['x']}, 'str', {5: 'x'}):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_secrets('sp', 'pub', bad)
            self.assertEqual((cm.exception.code, cm.exception.status), ('bad-settings', 400), bad)
        self.assertFalse(os.path.exists(self.secrets_file), before)

    def test_corrupt_file_is_not_overwritten_and_not_silently_empty(self):
        os.makedirs(self.deai)
        for bad in ('{nope', '[]', '"x"'):
            _write(self.secrets_file, bad)
            with self.assertRaises(dm.ModuleError) as cm:
                dm.read_secrets('sp', 'pub')
            self.assertEqual((cm.exception.code, cm.exception.status), ('secrets-unreadable', 409), bad)
            before = _md5(self.secrets_file)
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_secrets('sp', 'pub', {'password': 'x'})
            self.assertEqual(cm.exception.code, 'secrets-unreadable')
            self.assertEqual(_md5(self.secrets_file), before)

    def test_garbage_inside_the_file_degrades_to_empty(self):
        os.makedirs(self.deai)
        _write(self.secrets_file, {'sp': 'junk', 'sp2': {'pub': ['x']}, 'sp3': {'pub': {'password': 5}}})
        for sid in ('sp', 'sp2', 'sp3'):
            self.assertEqual(dm.read_secrets(sid, 'pub'), {}, sid)
        dm.write_secrets('sp', 'pub', {'password': 'ok'})                   # і перезаписується акуратно
        self.assertEqual(dm.read_secrets('sp', 'pub'), {'password': 'ok'})
        self.assertEqual(_read(self.secrets_file)['sp3'], {'pub': {'password': 5}})

    def test_layer_off_never_touches_deai_home(self):
        # справжній файл за `<HOME>/.deai/secrets.json` із значенням: шар вимкнено — його ніхто не читає
        _write(self.hp('.deai', 'secrets.json'), {'sp': {'pub': {'password': 'real-secret'}}})
        before = _md5(self.hp('.deai', 'secrets.json'))
        del os.environ['DEAI_HOME']
        self.assertFalse(spaces.layer_on())
        self.assertEqual(spaces.home(), self.hp('.deai'))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_secrets('sp', 'pub', {'password': 'x'})
        self.assertEqual((cm.exception.code, cm.exception.status), ('spaces-off', 409))
        self.assertEqual(dm.read_secrets('sp', 'pub'), {})
        self.assertEqual(_md5(self.hp('.deai', 'secrets.json')), before)

    def test_unwritable_secrets_are_reported_not_crashed(self):
        with mock.patch.object(dm, 'atomic_write_json', side_effect=PermissionError('nope')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_secrets('sp', 'pub', {'password': 'pw1'})
        self.assertEqual((cm.exception.code, cm.exception.status), ('unwritable', 500))
        self.assertNotIn('pw1', cm.exception.message)
        self.assertEqual(dm.read_secrets('sp', 'pub'), {})

    def test_lone_surrogates_in_secrets(self):
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_secrets('sp', 'pub', {'password': '\ud800'})
        self.assertEqual(cm.exception.code, 'bad-settings')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_secrets('sp\udc80', 'pub', {'password': 'x'})
        self.assertEqual(cm.exception.code, 'bad-settings')
        os.makedirs(self.deai)
        _write(self.secrets_file, '{"other": {"m": {"k": "\\ud800"}}}')       # сурогат, що вже лежить у файлі
        before = _md5(self.secrets_file)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_secrets('sp', 'pub', {'password': 'ok'})
        self.assertEqual(cm.exception.code, 'unwritable')
        self.assertEqual(_md5(self.secrets_file), before)

    def test_the_file_and_home_are_tightened_before_the_atomic_write(self):
        os.makedirs(self.deai)
        os.chmod(self.deai, 0o755)
        _write(self.secrets_file, {})
        os.chmod(self.secrets_file, 0o644)
        seen = []
        real = dm.atomic_write_json

        def spy(path, data, *a, **kw):
            seen.append((_mode(path), _mode(os.path.dirname(path))))
            return real(path, data, *a, **kw)
        with mock.patch.object(dm, 'atomic_write_json', spy):
            dm.write_secrets('sp', 'pub', {'password': 'pw1'})
        self.assertEqual(seen, [(0o600, 0o700)], 'у мить запису цільовий файл уже 0600, а тека 0700')

    def test_perms_are_tightened_even_when_nothing_changes(self):
        dm.write_secrets('sp', 'pub', {'password': 'pw1'})
        os.chmod(self.secrets_file, 0o644)
        os.chmod(self.deai, 0o755)
        dm.write_secrets('sp', 'pub', {'password': 'pw1'})                 # те саме значення
        self.assertEqual((_mode(self.secrets_file), _mode(self.deai)), (0o600, 0o700))
        os.chmod(self.secrets_file, 0o644)
        dm.write_secrets('sp', 'pub', {'token': None})                      # нічого видаляти
        self.assertEqual(_mode(self.secrets_file), 0o600)

    def test_a_noop_write_creates_nothing(self):
        dm.write_secrets('sp', 'pub', {'token': None})
        dm.write_secrets('sp', 'pub', {})
        self.assertFalse(os.path.exists(self.deai))

    def test_concurrent_writes_do_not_lose_keys(self):
        names = ('password', 'token')
        out = race(2, lambda i: dm.write_secrets('sp', 'pub', {names[i]: f'v{i}'}))
        self.assertEqual([r[0] for r in out], ['ok', 'ok'], out)
        self.assertEqual(dm.read_secrets('sp', 'pub'), {'password': 'v0', 'token': 'v1'})
        for _ in range(3):
            race(2, lambda i: dm.write_secrets('sp', 'other', {names[i]: f'x{i}'}))
        self.assertEqual(dm.read_secrets('sp', 'other'), {'password': 'x0', 'token': 'x1'})

    def test_secrets_never_reach_space_json_or_state(self):
        sp = self.new_space()
        dm.write_secrets(sp['id'], 'pub', {'password': 'top-secret-value'})
        dm.write_module_state(sp, 'pub', enabled=True, settings={'folder': '~/p'})
        self.assertNotIn('top-secret-value', _bytes(self.space_json(sp)).decode())
        self.assertNotIn('top-secret-value', json.dumps(dm.effective_state(sp)))
        self.assertNotIn('top-secret-value', json.dumps(dm.resolve_settings(
            sp, dm.catalog()['pub'], dm.effective_state(sp)['pub']['settings'])))


# --------------------------------------------------------------------------------- resolve_settings

class ResolveTest(Env):
    def setUp(self):
        super().setUp()
        self.mk('alpha', settings=[
            {'key': 'folder', 'type': 'path', 'default': '{home}/deai-published/{space_id}', 'required': True},
            {'key': 'text', 'type': 'text'},
            {'key': 'flag', 'type': 'bool', 'default': False},
            {'key': 'mode', 'type': 'select', 'options': [{'value': 'a', 'label': 'A'}, {'value': 'b', 'label': 'B'}]},
            {'key': 'pw', 'type': 'secret'}])
        self.m = dm.catalog()['alpha']
        self.sp = {'id': 'sp-1', 'path': os.path.join(self.tmp, 'space dir'), 'legacy': False,
                   'integrations': False}

    def rs(self, symbolic, space=None):
        return dm.resolve_settings(space or self.sp, self.m, symbolic)

    def test_default_path_gets_home_and_space_id(self):
        out = self.rs({})
        self.assertEqual(out['folder'], os.path.join(self.home, 'deai-published', 'sp-1'))
        self.assertEqual(out['flag'], False)
        self.assertNotIn('text', out)                      # без типового й не обовʼязкове — відсутнє
        self.assertNotIn('pw', out)                        # секрет у налаштуваннях не живе

    def test_placeholders_and_tilde_and_relative(self):
        self.assertEqual(self.rs({'folder': '{space}/out'})['folder'], os.path.join(self.sp['path'], 'out'))
        self.assertEqual(self.rs({'folder': '~/x/{space_id}'})['folder'], os.path.join(self.home, 'x', 'sp-1'))
        self.assertEqual(self.rs({'folder': 'rel/dir'})['folder'], os.path.join(self.sp['path'], 'rel', 'dir'))
        self.assertEqual(self.rs({'folder': '/abs/p'})['folder'], '/abs/p')
        self.assertEqual(self.rs({'folder': '{home}/a/../b'})['folder'], os.path.join(self.home, 'b'))

    def test_placeholders_are_substituted_in_one_pass(self):
        os.environ['HOME'] = os.path.join(self.tmp, 'we{space}ird')
        out = self.rs({'folder': '{home}/x'})['folder']
        self.assertEqual(out, os.path.join(self.tmp, 'we{space}ird', 'x'))

    def test_relative_path_without_a_space_folder_is_refused(self):
        for p in ('rel/dir', '{space}/x'):
            with self.assertRaises(dm.ModuleError) as cm:
                self.rs({'folder': p}, space=dict(spaces.IMPLICIT))
            self.assertEqual(cm.exception.code, 'bad-settings', p)
        self.assertEqual(self.rs({'folder': '/abs'}, space=dict(spaces.IMPLICIT))['folder'], '/abs')

    def test_types_are_checked(self):
        for bad in ({'folder': 5}, {'folder': ''}, {'folder': '  '}, {'folder': 'a\0b'}, {'text': 3},
                    {'flag': 1}, {'flag': 'true'}, {'mode': 'c'}, {'mode': 1}, {'text': 'x' * 5000}):
            with self.assertRaises(dm.ModuleError) as cm:
                self.rs(bad)
            self.assertEqual((cm.exception.code, cm.exception.status), ('bad-settings', 400), bad)
        ok = self.rs({'text': 'hi', 'flag': True, 'mode': 'b'})
        self.assertEqual((ok['text'], ok['flag'], ok['mode']), ('hi', True, 'b'))

    def test_required_without_value_or_default_is_refused(self):
        self.mk('beta', settings=[{'key': 'file', 'type': 'path', 'required': True}])
        beta = dm.catalog()['beta']
        with self.assertRaises(dm.ModuleError) as cm:
            dm.resolve_settings(self.sp, beta, {})
        self.assertEqual(cm.exception.code, 'bad-settings')
        self.assertIn('file', cm.exception.message)
        self.assertEqual(dm.resolve_settings(self.sp, beta, {'file': '/f.css'})['file'], '/f.css')

    def test_unknown_keys_are_dropped_and_none_means_default(self):
        out = self.rs({'junk': 'x', 'folder': None})
        self.assertNotIn('junk', out)
        self.assertEqual(out['folder'], os.path.join(self.home, 'deai-published', 'sp-1'))


# --------------------------------------------------------------------------------------- постачальник

class ProviderTest(Env):
    def test_explicit_module(self):
        self.mk('pub-a')
        sp = self.new_space()
        self.assertIsNone(dm.provider('publish', sp))
        dm.write_module_state(sp, 'pub-a', enabled=True)
        self.assertEqual(dm.provider('publish', sp).id, 'pub-a')
        self.assertIsNone(dm.provider('tokens', sp))
        dm.write_module_state(sp, 'pub-a', enabled=False)
        self.assertIsNone(dm.provider('publish', sp))

    def test_implicit_static_publish(self):
        self.mk('static-publish')
        sp = self.new_space()
        self.assertEqual(dm.provider('publish', sp).id, 'static-publish')
        self.assertIsNone(dm.provider('tokens', sp))
        dm.write_module_state(sp, 'static-publish', enabled=False)
        self.assertIsNone(dm.provider('publish', sp))

    def test_integrations_space_is_legacy_for_publish_only(self):
        self.mk('static-publish')
        self.mk('css-tokens', roles=('tokens',))
        sp = self.new_space(integrations=True)
        self.assertEqual(dm.provider('publish', sp), 'legacy')
        self.assertIsNone(dm.provider('tokens', sp))

    def test_explicit_publish_module_beats_legacy(self):
        self.mk('pub-a')
        sp = self.new_space(integrations=True)
        dm.write_module_state(sp, 'pub-a', enabled=True)
        self.assertEqual(dm.provider('publish', sp).id, 'pub-a')

    def test_a_broken_enabled_module_is_not_a_provider(self):
        self.mk('pub-broken', server='def check(:\n')
        sp = self.new_space()
        dm.write_module_state(sp, 'pub-broken', enabled=True)
        self.assertIsNone(dm.provider('publish', sp))
        ig = self.new_space('Beta', integrations=True)
        dm.write_module_state(ig, 'pub-broken', enabled=True)
        self.assertEqual(dm.provider('publish', ig), 'legacy')

    def test_an_enabled_module_missing_on_this_machine_is_not_a_provider(self):
        sp = self.new_space()
        _write(self.space_json(sp), {'modules': {'ghost': {'enabled': True}}})
        self.assertIsNone(dm.provider('publish', sp))

    def untouched(self):
        """Контекст: будь-яке звернення до каталогу модулів, реєстру чи `space.json` валить тест."""
        boom = AssertionError('шлях ЛІГА не мусить читати каталог/реєстр/space.json')
        stack = contextlib.ExitStack()
        for target, name in ((dm, 'catalog'), (dm, '_load_space_json'), (spaces, 'read_registry'),
                             (spaces, 'load_registry'), (spaces, 'active_space')):
            stack.enter_context(mock.patch.object(target, name, side_effect=boom))
        return stack

    def test_request_space_unfixed_is_legacy_for_publish(self):
        self.mk('static-publish')
        self.new_space()
        self.assertIsNone(spaces.request_space_id())
        with self.untouched():                               # без читання реєстру, space.json і каталогу
            self.assertEqual(dm.provider('publish'), 'legacy')
            self.assertIsNone(dm.provider('tokens'))
            self.assertEqual(dm.provider('comments'), 'legacy')      # 2b-2: інструменти ЛІГА мають командні коментарі
            self.assertEqual(dm.provider('vcs'), 'legacy')           # 4a: і зашитий синк із git — той самий шлях ЛІГА

    def test_request_space_none_is_no_provider(self):
        self.mk('static-publish')
        self.new_space()
        with spaces.request_space(''):
            self.assertIsNone(dm.provider('publish'))
        with spaces.request_space('no-such-space'):
            self.assertIsNone(dm.provider('publish'))

    def test_request_space_fixed_resolves_that_space(self):
        self.mk('static-publish')
        a = self.new_space('Alpha')
        b = self.new_space('Beta', integrations=True)
        with spaces.request_space(a['id']):
            self.assertEqual(dm.provider('publish').id, 'static-publish')
        with spaces.request_space(b['id']):
            self.assertEqual(dm.provider('publish'), 'legacy')

    def test_explicit_space_wins_over_an_unfixed_request(self):
        self.mk('static-publish')
        sp = self.new_space()
        self.assertIsNone(spaces.request_space_id())
        self.assertEqual(dm.provider('publish', sp).id, 'static-publish')

    def test_layer_off_is_legacy(self):
        self.mk('static-publish')
        del os.environ['DEAI_HOME']
        self.assertFalse(spaces.layer_on())
        with self.untouched():
            self.assertEqual(dm.provider('publish'), 'legacy')
            self.assertIsNone(dm.provider('tokens'))
            self.assertEqual(dm.provider('comments'), 'legacy')
            self.assertEqual(dm.provider('vcs'), 'legacy')
            with spaces.request_space('whatever'):
                self.assertEqual(dm.provider('publish'), 'legacy')
                self.assertIsNone(dm.provider('tokens'))
                self.assertEqual(dm.provider('comments'), 'legacy')
                self.assertEqual(dm.provider('vcs'), 'legacy')
        self.assertEqual(dm.provider('publish', dict(spaces.IMPLICIT)), 'legacy')   # явний простір: диск не потрібен
        self.assertIsNone(dm.provider('tokens', dict(spaces.IMPLICIT)))
        self.assertEqual(dm.provider('comments', dict(spaces.IMPLICIT)), 'legacy')
        self.assertEqual(dm.provider('vcs', dict(spaces.IMPLICIT)), 'legacy')

    def test_a_broken_space_json_is_409_without_integrations_and_harmless_with_them(self):
        self.mk('static-publish')
        sp = self.new_space()
        _write(self.space_json(sp), '{broken')
        with self.assertRaises(dm.ModuleError) as cm:        # без інтеграцій треба знати явні рішення
            dm.provider('publish', sp)
        self.assertEqual((cm.exception.code, cm.exception.status), ('space-json-unreadable', 409))
        with self.assertRaises(dm.ModuleError) as cm:        # і для `vcs` (4a)
            dm.provider('vcs', sp)
        self.assertEqual((cm.exception.code, cm.exception.status), ('space-json-unreadable', 409))
        ig = self.new_space('Integ', integrations=True)
        _write(self.space_json(ig), '{broken')
        self.assertEqual(dm.provider('publish', ig), 'legacy')   # шлях ЛІГА пошкодженим файлом не ламається
        self.assertEqual(dm.provider('vcs', ig), 'legacy')       # `vcs` — так само (4a): зашитий синк, а не 409
        self.assertIsNone(dm.provider('tokens', ig))
        with self.assertRaises(dm.ModuleError) as cm:            # а коментарі — ні: спільний Supabase не запасний варіант
            dm.provider('comments', ig)
        self.assertEqual((cm.exception.code, cm.exception.status), ('space-json-unreadable', 409))

    def test_integrations_space_without_an_enabled_module_never_touches_the_catalog(self):
        self.mk('pub-a')
        ig = self.new_space(integrations=True)
        with mock.patch.object(dm, 'catalog', side_effect=AssertionError('каталог не потрібен')):
            self.assertEqual(dm.provider('publish', ig), 'legacy')
            self.assertIsNone(dm.provider('tokens', ig))
            self.assertEqual(dm.provider('comments', ig), 'legacy')
            self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy'})
        dm.write_module_state(ig, 'pub-a', enabled=False)            # явне «вимкнено» — теж не модуль
        with mock.patch.object(dm, 'catalog', side_effect=AssertionError('каталог не потрібен')):
            self.assertEqual(dm.provider('publish', ig), 'legacy')
        dm.write_module_state(ig, 'pub-a', enabled=True)             # а явно ввімкнений — каталог потрібен
        self.assertEqual(dm.provider('publish', ig).id, 'pub-a')

    def test_a_broken_builtin_does_not_break_the_legacy_path(self):
        self.mk('pub-broken', server='raise RuntimeError("x")\n')
        ig = self.new_space(integrations=True)
        self.assertEqual(dm.provider('publish', ig), 'legacy')
        dm.write_module_state(ig, 'pub-broken', enabled=True)
        self.assertEqual(dm.provider('publish', ig), 'legacy')       # зламаний модуль — не постачальник

    def test_explicit_beats_implicit_when_both_somehow_match(self):
        self.mk('static-publish')
        self.mk('zzz-pub')
        sp = self.new_space()
        _write(self.space_json(sp), {'modules': {'zzz-pub': {'enabled': True}}})
        self.assertEqual(dm.provider('publish', sp).id, 'zzz-pub')


# ------------------------------------------------------------------------------------ тека публікації

class FolderTest(Env):
    def code(self, sp, folder):
        ok, code = dm.folder_ok(sp, folder)
        self.assertEqual(ok, code is None, (folder, ok, code))
        return code

    def test_a_plain_folder_outside_everything_is_fine(self):
        sp = self.new_space()
        self.assertEqual(dm.folder_ok(sp, self.hp('pub', 'alpha')), (True, None))
        self.assertEqual(dm.folder_ok(sp, '~/pub/alpha'), (True, None))          # `~` — домівка користувача

    def test_the_home_folder_and_its_ancestors_are_too_broad(self):
        sp = self.new_space()
        self.assertEqual(self.code(sp, self.home), 'path-too-broad')
        self.assertEqual(self.code(sp, os.path.dirname(self.home)), 'path-too-broad')
        self.assertEqual(self.code(sp, '/'), 'path-too-broad')

    def test_a_space_folder_its_insides_and_its_ancestors_are_refused(self):
        a = self.new_space('Alpha')
        b = self.new_space('Beta')
        self.assertEqual(self.code(a, a['path']), 'path-registered')
        self.assertEqual(self.code(a, os.path.join(a['path'], 'pub')), 'path-overlap')
        self.assertEqual(self.code(a, os.path.dirname(a['path'])), 'path-overlap')     # над текою простору
        self.assertEqual(self.code(a, os.path.join(b['path'], 'pub')), 'path-overlap')  # чужий простір теж
        self.assertEqual(self.code(a, b['path']), 'path-registered')

    def test_task_folders_their_insides_and_ancestors_are_refused(self):
        sp = self.new_space()
        _write(os.path.join(sp['path'], 'tasks.json'),
               {'tasks': {'t1': {'dir': self.hp('designs', 't1')}}})
        self.assertEqual(self.code(sp, self.hp('designs', 't1')), 'path-overlap')
        self.assertEqual(self.code(sp, self.hp('designs', 't1', 'pub')), 'path-overlap')
        self.assertEqual(self.code(sp, self.hp('designs')), 'path-overlap')
        self.assertIsNone(self.code(sp, self.hp('designs-pub')))                  # сусід за префіксом — не вкладений

    def test_deai_home_equal_inside_and_above_are_refused(self):
        os.environ['DEAI_HOME'] = self.hp('stuff', 'deai')
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        self.assertEqual(self.code(sp, self.hp('stuff', 'deai')), 'path-deai-home')
        self.assertEqual(self.code(sp, self.hp('stuff', 'deai', 'pub')), 'path-deai-home')   # ВСЕРЕДИНІ
        self.assertEqual(self.code(sp, self.hp('stuff')), 'path-deai-home')                 # над
        self.assertIsNone(self.code(sp, self.hp('stuff', 'other')))
        self.assertIsNone(self.code(sp, self.hp('stuff2')))

    def tool_dir(self):
        tool = self.hp('tools', 'dc')
        os.makedirs(tool)
        return tool

    def test_the_tool_folder_is_refused(self):
        """Тека інструмента — підміняємо `spaces.ROOT` на теку в тимчасовій домівці (поза системними теками),
        щоб причина була саме `path-tool`, а не випадково `path-system`."""
        sp = self.new_space()
        tool = self.tool_dir()
        with mock.patch.object(spaces, 'ROOT', tool):
            for f in (tool, os.path.join(tool, 'x'), self.hp('tools')):
                self.assertEqual(self.code(sp, f), 'path-tool', f)
            self.assertIsNone(self.code(sp, self.hp('tools-pub')))

    def need_case_insensitive_fs(self):
        if not _fs_case_insensitive(self.tmp):
            self.skipTest('файлова система розрізняє регістр — тест варіанта регістру нічого б не довів')

    def test_tool_folder_case_variants_are_refused_by_the_filesystem(self):
        self.need_case_insensitive_fs()
        sp = self.new_space()
        tool = self.tool_dir()
        with mock.patch.object(spaces, 'ROOT', tool):
            self.assertEqual(self.code(sp, self.hp('TOOLS', 'DC')), 'path-tool')
            self.assertEqual(self.code(sp, self.hp('TOOLS', 'DC', 'pub')), 'path-tool')    # всередині
            self.assertEqual(self.code(sp, self.hp('TOOLS')), 'path-tool')                 # над

    def test_home_dot_dirs_and_library_are_refused_by_the_filesystem_too(self):
        self.need_case_insensitive_fs()
        sp = self.new_space()
        os.makedirs(self.hp('Library'))
        up = self.home.upper()                                   # той самий каталог, написаний інакше
        # тимчасова домівка живе під `/var`, і текстове правило системних тек відмовило б з `path-system`
        # само, не доходячи до нашого: вимикаємо його, щоб доводилась саме перевірка файловою системою
        with mock.patch.object(spaces, 'SYSTEM_DIRS', ()):
            self.assertEqual(self.code(sp, up + '/.SSH/pub'), 'path-system')
            self.assertEqual(self.code(sp, up + '/.ssh'), 'path-system')
            self.assertEqual(self.code(sp, up + '/LIBRARY/pub'), 'path-system')
            self.assertEqual(self.code(sp, up + '/LIBRARY'), 'path-system')
            self.assertIsNone(self.code(sp, up + '/PUB/alpha'))   # звичайна тека під таким написанням — можна

    def test_system_folders_in_another_spelling_are_refused(self):
        self.need_case_insensitive_fs()
        if not os.path.isdir('/Applications'):
            self.skipTest('нема /Applications')
        sp = self.new_space()
        self.assertEqual(self.code(sp, '/APPLICATIONS/pub'), 'path-system')

    def test_deai_home_in_another_spelling_is_refused(self):
        self.need_case_insensitive_fs()
        deai = self.hp('stuff', 'deai')
        os.makedirs(deai)
        os.environ['DEAI_HOME'] = deai
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        self.assertEqual(self.code(sp, self.hp('STUFF', 'DEAI', 'pub')), 'path-deai-home')   # всередині
        self.assertEqual(self.code(sp, self.hp('STUFF')), 'path-deai-home')                  # над
        self.assertIsNone(self.code(sp, self.hp('STUFF', 'OTHER')))

    def test_a_symlink_to_deai_home_is_refused_even_when_the_target_is_missing(self):
        """`DEAI_HOME` — висяче посилання: `exists()` бреше, лишається лише `realpath` обох сторін."""
        target = self.hp('stuff', 'nowhere')
        os.makedirs(self.hp('stuff'))
        os.symlink(target, self.hp('stuff', 'deai-link'))
        os.environ['DEAI_HOME'] = self.hp('stuff', 'deai-link')
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        self.assertEqual(self.code(sp, os.path.join(target, 'pub')), 'path-deai-home')
        self.assertEqual(self.code(sp, target), 'path-deai-home')
        self.assertIsNone(self.code(sp, self.hp('stuff', 'else')))

    def test_a_dotdot_through_a_symlink_is_judged_by_its_lexical_form_too(self):
        """`link/../stuff/deai/pub`: текстово це всередині DEAI_HOME, а фізично — деінде. Відмовляємо за обома."""
        os.makedirs(self.hp('a', 'b'))
        os.symlink(self.hp('a', 'b'), self.hp('lnk'))
        os.environ['DEAI_HOME'] = self.hp('stuff', 'deai')        # теки нема: лише текст і realpath
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        self.assertEqual(self.code(sp, os.path.join(self.hp('lnk'), '..', 'stuff', 'deai', 'pub')),
                         'path-deai-home')

    def test_the_home_folder_and_its_ancestors_in_another_spelling_are_too_broad(self):
        self.need_case_insensitive_fs()
        other = tempfile.mkdtemp(prefix='deai-other-')
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        os.environ['DEAI_HOME'] = other                          # поза домівкою й без просторів: рішає лише це правило
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        with mock.patch.object(spaces, 'SYSTEM_DIRS', ()):       # тимчасова домівка під `/var`: без цього відмовило б текстове правило
            self.assertEqual(self.code(sp, self.home.upper()), 'path-too-broad')                          # сама домівка
            self.assertEqual(self.code(sp, os.path.dirname(self.home).upper()), 'path-too-broad')         # предок
            self.assertEqual(self.code(sp, os.path.dirname(os.path.dirname(self.home)).upper()), 'path-too-broad')
            self.assertIsNone(self.code(sp, self.home.upper() + '/PUB'))                                  # а підтека — можна

    def test_the_home_rule_comes_before_the_tool_rule(self):
        """Та сама причина, що й для самої `~` за текстом: `path-too-broad`, а не `path-tool` (теку інструмента
        на машині власника саму лежить у домівці)."""
        self.need_case_insensitive_fs()
        other = tempfile.mkdtemp(prefix='deai-other-')
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        os.environ['DEAI_HOME'] = other
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        tool = self.tool_dir()
        with mock.patch.object(spaces, 'SYSTEM_DIRS', ()), mock.patch.object(spaces, 'ROOT', tool):
            self.assertEqual(self.code(sp, self.home.upper()), 'path-too-broad')
            self.assertEqual(self.code(sp, self.hp('TOOLS', 'DC')), 'path-tool')

    def test_a_symlink_in_the_home_to_a_system_folder_in_another_spelling_is_refused(self):
        self.need_case_insensitive_fs()
        if not os.path.isdir('/Applications'):
            self.skipTest('нема /Applications')
        sp = self.new_space()
        os.symlink('/APPLICATIONS', self.hp('lnk'))
        self.assertEqual(self.code(sp, self.hp('lnk', 'pub')), 'path-system')
        self.assertEqual(self.code(sp, self.hp('lnk')), 'path-system')
        os.makedirs(self.hp('real'))
        os.symlink(self.hp('real'), self.hp('ok-lnk'))
        self.assertIsNone(self.code(sp, self.hp('ok-lnk', 'pub')))     # посилання на звичайну теку — можна

    def test_deai_home_is_compared_in_nfc(self):
        deai = self.hp('stuff', unicodedata.normalize('NFC', 'déai'))
        os.environ['DEAI_HOME'] = deai                            # теки нема: порівнює лише текст
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        nfd = unicodedata.normalize('NFD', 'déai')
        self.assertNotEqual(nfd, 'déai')
        self.assertEqual(self.code(sp, self.hp('stuff', nfd, 'pub')), 'path-deai-home')
        self.assertEqual(self.code(sp, self.hp('stuff', nfd)), 'path-deai-home')
        self.assertIsNone(self.code(sp, self.hp('stuff', 'dei')))

    def test_a_space_with_an_unreadable_tasks_file_refuses_everything(self):
        """`all_task_dirs` читає такий файл як порожній — а в ньому можуть лежати теки задач."""
        a = self.new_space('Alpha')
        b = self.new_space('Beta')
        _write(os.path.join(b['path'], 'tasks.json'), '{broken')
        self.assertEqual(dm.folder_ok(a, self.hp('pub')), (False, 'spaces-unreadable'))
        _write(os.path.join(b['path'], 'tasks.json'), {'tasks': {}})
        self.assertEqual(dm.folder_ok(a, self.hp('pub')), (True, None))

    def test_an_unreadable_legacy_tasks_file_refuses(self):
        sp = self.new_space()
        _write(self.legacy, '{broken')
        self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (False, 'spaces-unreadable'))

    # ---- вхідні дані: явні й кеш на пару секунд ----
    def spy_registry(self):
        calls = []
        real = spaces.read_registry

        def spy():
            calls.append(1)
            return real()
        return calls, mock.patch.object(spaces, 'read_registry', spy)

    def test_inputs_are_cached_for_a_couple_of_seconds(self):
        sp = self.new_space()
        calls, patch = self.spy_registry()
        now = [1000.0]
        with patch, mock.patch.object(dm, '_now', lambda: now[0]):
            for _ in range(3):
                self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (True, None))
            self.assertEqual(len(calls), 1)
            now[0] += dm.FOLDER_INPUTS_TTL - 0.1
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 1)
            now[0] += 0.2
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 2, 'після TTL читаємо знову')
        self.assertEqual(dm.FOLDER_INPUTS_TTL, 2)

    def test_the_cache_follows_the_environment(self):
        sp = self.new_space()
        calls, patch = self.spy_registry()
        with patch, mock.patch.object(dm, '_now', lambda: 1000.0):
            dm.folder_ok(sp, self.hp('pub'))
            os.environ['DEAI_HOME'] = self.hp('other-deai')              # інший реєстр — кеш не годиться
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 2)

    def test_the_inputs_key_follows_the_registry_and_the_legacy_file(self):
        """Простір щойно створили чи змінили старий файл задач — читаємо знову, не чекаючи кінця TTL."""
        sp = self.new_space()
        calls, patch = self.spy_registry()

        def reads_after(change):
            """Скільки разів прочитано реєстр після `change` при двох підряд викликах (другий — із кешу)."""
            change()
            calls.clear()
            dm.folder_ok(sp, self.hp('pub'))
            dm.folder_ok(sp, self.hp('pub'))
            return len(calls)
        with patch, mock.patch.object(dm, '_now', lambda: 1000.0):
            self.assertEqual(reads_after(lambda: None), 1)
            self.assertEqual(reads_after(lambda: self.new_space('Beta')), 1)             # змінився реєстр
            self.assertEqual(reads_after(lambda: _write(self.legacy, {'tasks': {}})), 1)    # зʼявився файл старих задач
            self.assertEqual(reads_after(lambda: _write(
                self.legacy, {'tasks': {'t': {'dir': self.hp('d', 't')}}})), 1)           # змінився
            _write(self.legacy, '{broken')                                                # а тепер не читається — одразу відмова
            self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (False, 'spaces-unreadable'))
            _write(self.legacy, {'tasks': {}})
            self.assertEqual(reads_after(lambda: os.environ.update(
                DC_TASKS_FILE=self.hp('other-tasks.json'))), 1)                           # інший шлях старого файла

    def test_the_inputs_key_follows_the_paths_even_when_no_file_exists(self):
        """Реєстру й старого файла нема за жодним зі шляхів — відбитки однакові (`None`), різнить лише шлях."""
        os.environ['DEAI_HOME'] = self.hp('d1')
        calls, patch = self.spy_registry()
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        with patch, mock.patch.object(dm, '_now', lambda: 1000.0):
            dm.folder_ok(sp, self.hp('pub'))
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 1)
            os.environ['DEAI_HOME'] = self.hp('d2')                       # інший (теж неіснуючий) реєстр
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 2)
            os.environ['DC_TASKS_FILE'] = self.hp('nowhere', 'tasks.json')  # інший (теж неіснуючий) старий файл
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 3)

    def test_the_layer_flag_is_part_of_the_inputs_key(self):
        os.environ['DEAI_HOME'] = self.hp('.deai')                # шар увімкнено, але шлях реєстру той самий, що в `~/.deai`
        sp = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        calls, patch = self.spy_registry()
        with patch, mock.patch.object(dm, '_now', lambda: 1000.0):
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 1)
            del os.environ['DEAI_HOME']                           # шар вимкнено: `registry_path()` і шлях старого файла — ті самі
            self.assertFalse(spaces.layer_on())
            self.assertEqual(spaces.registry_path(), self.hp('.deai', 'spaces.json'))
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 2)

    def test_reset_caches_drops_the_inputs(self):
        sp = self.new_space()
        calls, patch = self.spy_registry()
        with patch, mock.patch.object(dm, '_now', lambda: 1000.0):
            dm.folder_ok(sp, self.hp('pub'))
            dm.reset_caches()
            dm.folder_ok(sp, self.hp('pub'))
            self.assertEqual(len(calls), 2)

    def test_a_refusal_is_not_cached(self):
        a = self.new_space('Alpha')
        b = self.new_space('Beta')
        _write(os.path.join(b['path'], 'tasks.json'), '{broken')
        with mock.patch.object(dm, '_now', lambda: 1000.0):
            self.assertEqual(dm.folder_ok(a, self.hp('pub')), (False, 'spaces-unreadable'))
            _write(os.path.join(b['path'], 'tasks.json'), {'tasks': {}})
            self.assertEqual(dm.folder_ok(a, self.hp('pub')), (True, None))     # тієї ж миті

    def test_an_unreadable_registry_refusal_is_not_cached_even_under_the_same_signature(self):
        """Відбиток зіпсованого й полагодженого реєстру збігається (той самий inode, розмір і mtime): якби
        відмову закешували, наступний виклик віддав би її знову."""
        sp = self.new_space()
        good = _bytes(self.reg_file)
        bad = good[:-1] + b' '                                      # обірваний JSON тієї ж довжини
        with open(self.reg_file, 'wb') as f:
            f.write(bad)
        st = os.stat(self.reg_file)
        with mock.patch.object(dm, '_now', lambda: 1000.0):
            self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (False, 'spaces-unreadable'))
            with open(self.reg_file, 'wb') as f:
                f.write(good)
            os.utime(self.reg_file, ns=(st.st_atime_ns, st.st_mtime_ns))
            now = os.stat(self.reg_file)
            self.assertEqual((now.st_ino, now.st_size, now.st_mtime_ns), (st.st_ino, st.st_size, st.st_mtime_ns))
            self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (True, None))

    def test_an_unreadable_registry_is_not_cached(self):
        sp = self.new_space()
        good = _bytes(self.reg_file).decode('utf-8')
        with mock.patch.object(dm, '_now', lambda: 1000.0):
            _write(self.reg_file, '{broken')
            self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (False, 'spaces-unreadable'))
            _write(self.reg_file, good)
            self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (True, None))       # тієї ж миті

    def test_explicit_inputs_are_used_and_skip_the_reads(self):
        sp = self.new_space()
        reg = spaces.read_registry()
        dirs = spaces.all_task_dirs(reg)
        boom = AssertionError('читати не мали')
        with mock.patch.object(spaces, 'read_registry', side_effect=boom), \
                mock.patch.object(spaces, 'all_task_dirs', side_effect=boom), \
                mock.patch.object(spaces, 'unreadable_task_files', side_effect=boom):
            self.assertEqual(dm.folder_ok(sp, self.hp('pub'), reg=reg, task_dirs=dirs), (True, None))
            self.assertEqual(dm.folder_ok(sp, sp['path'], reg=reg, task_dirs=dirs), (False, 'path-registered'))
            # дані з аргументів, а не з диска: у цьому «реєстрі» простору нема, а в «задач» є одна тека
            empty = {'version': 1, 'current': None, 'spaces': []}
            self.assertEqual(dm.folder_ok(sp, sp['path'], reg=empty, task_dirs=[]), (True, None))
            self.assertEqual(dm.folder_ok(sp, self.hp('t', 'pub'), reg=empty, task_dirs=[self.hp('t')]),
                             (False, 'path-overlap'))

    def test_a_given_registry_still_gets_its_task_files_checked(self):
        sp = self.new_space()
        _write(os.path.join(sp['path'], 'tasks.json'), '{broken')
        reg = spaces.read_registry()
        self.assertEqual(dm.folder_ok(sp, self.hp('pub'), reg=reg), (False, 'spaces-unreadable'))
        self.assertEqual(dm.folder_ok(sp, self.hp('pub'), task_dirs=[]), (False, 'spaces-unreadable'))
        self.assertIsNone(dm.folder_inputs())

    def test_folder_inputs_gives_the_pair_for_the_callers(self):
        sp = self.new_space()
        _write(os.path.join(sp['path'], 'tasks.json'), {'tasks': {'t': {'dir': self.hp('d', 't')}}})
        reg, dirs = dm.folder_inputs()
        self.assertEqual([s['id'] for s in reg['spaces']], [sp['id']])
        self.assertEqual(dirs, [self.hp('d', 't')])
        self.assertEqual(dm.folder_ok(sp, self.hp('d', 't', 'pub'), reg=reg, task_dirs=dirs), (False, 'path-overlap'))

    def test_symlinks_are_resolved(self):
        sp = self.new_space()
        os.symlink(sp['path'], self.hp('link'))
        self.assertEqual(self.code(sp, self.hp('link')), 'path-registered')
        self.assertEqual(self.code(sp, self.hp('link', 'pub')), 'path-overlap')
        os.makedirs(self.hp('real-pub'))
        os.symlink(self.hp('real-pub'), self.hp('ok-link'))
        self.assertIsNone(self.code(sp, self.hp('ok-link')))

    def test_relative_empty_and_odd_input(self):
        sp = self.new_space()
        self.assertEqual(self.code(sp, 'rel/pub'), 'path-overlap')           # відносна — від теки простору, а там не можна
        no_path = {'id': 'x', 'path': '', 'legacy': False, 'integrations': False}
        for bad in ('rel/pub', '', '   ', None, 5, 'a\0b'):
            self.assertEqual(self.code(no_path, bad), 'path-not-absolute', bad)

    def test_an_existing_file_is_not_a_folder(self):
        sp = self.new_space()
        _write(self.hp('afile'), 'x')
        self.assertEqual(self.code(sp, self.hp('afile')), 'path-not-dir')

    def test_unreadable_registry_refuses(self):
        sp = self.new_space()
        _write(self.reg_file, '{broken')
        self.assertEqual(dm.folder_ok(sp, self.hp('pub')), (False, 'spaces-unreadable'))

    def test_layer_off_takes_the_old_tasks_file_into_account(self):
        _write(self.legacy, {'tasks': {'t': {'dir': self.hp('old', 't')}}})
        del os.environ['DEAI_HOME']
        self.assertFalse(spaces.layer_on())
        imp = dict(spaces.IMPLICIT)
        self.assertEqual(dm.folder_ok(imp, self.hp('pub')), (True, None))
        self.assertEqual(self.code(imp, self.hp('old', 't', 'pub')), 'path-overlap')
        self.assertEqual(self.code(imp, self.home), 'path-too-broad')

    def test_published_root_is_the_resolved_folder_setting(self):
        self.mk('pub', settings=[{'key': 'folder', 'type': 'path', 'default': '{home}/deai-published/{space_id}'}])
        self.mk('nofolder', roles=('tokens',), settings=[{'key': 'file', 'type': 'path'}])
        sp = self.new_space()
        want = os.path.join(self.home, 'deai-published', sp['id'])
        self.assertEqual(dm.published_root(sp, 'pub'), want)
        self.assertEqual(dm.published_root(sp, dm.catalog()['pub']), want)
        self.assertEqual(dm.folder_ok(sp, dm.published_root(sp, 'pub')), (True, None))
        dm.write_module_state(sp, 'pub', settings={'folder': '~/elsewhere/{space_id}'})
        self.assertEqual(dm.published_root(sp, 'pub'), os.path.join(self.home, 'elsewhere', sp['id']))
        self.assertIsNone(dm.published_root(sp, 'nofolder'))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.published_root(sp, 'ghost')
        self.assertEqual(cm.exception.code, 'unknown-module')

    def test_home_placeholder_is_the_users_home_not_deai_home(self):
        self.mk('pub', settings=[{'key': 'folder', 'type': 'path', 'default': '{home}/p'}])
        sp = self.new_space()
        self.assertNotEqual(spaces.home(), os.path.expanduser('~'))
        self.assertEqual(dm.published_root(sp, 'pub'), os.path.join(os.path.expanduser('~'), 'p'))
        self.assertEqual(dm.published_root(sp, 'pub'), os.path.join(self.home, 'p'))


# ----------------------------------------------------------------------------------------- capabilities

class CapabilitiesTest(Env):
    def test_shape_for_every_branch(self):
        self.mk('static-publish')
        self.mk('css-tokens', roles=('tokens',))
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        self.assertEqual(dm.capabilities(plain), {'publish': 'static-publish', 'tokens': None, 'comments': None, 'vcs': None})
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy'})
        dm.write_module_state(plain, 'css-tokens', enabled=True)
        self.assertEqual(dm.capabilities(plain), {'publish': 'static-publish', 'tokens': 'css-tokens', 'comments': None, 'vcs': None})
        self.assertEqual(dm.capabilities(dict(spaces.IMPLICIT)), {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy'})
        self.assertEqual(dm.capabilities(None), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None})

    def test_vcs_has_no_implicit_module_and_is_legacy_only_in_an_integrations_space(self):
        """`vcs` (4a): неявного модуля нема, тож у звичайному просторі — `None`, навіть коли `git-sync` лежить у каталозі
        (його ще не підключили); у просторі з `integrations` без явного модуля — `'legacy'`, ДО каталогу."""
        self.mk('git-sync', roles=('vcs',), server=VCS_SERVER)
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        self.assertIsNone(dm.capabilities(plain)['vcs'])
        self.assertEqual(dm.capabilities(ig)['vcs'], 'legacy')
        self.assertIsNone(dm.provider('vcs', plain))
        self.assertEqual(dm.provider('vcs', ig), 'legacy')
        with mock.patch.object(dm, 'catalog', side_effect=AssertionError('каталог не потрібен')):
            self.assertEqual(dm.provider('vcs', ig), 'legacy')

    def test_vcs_follows_an_explicitly_enabled_module_and_the_cache_follows_it(self):
        self.mk('git-sync', roles=('vcs',), server=VCS_SERVER)
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        dm.write_module_state(plain, 'git-sync', enabled=True)
        dm.write_module_state(ig, 'git-sync', enabled=True)
        self.assertEqual(dm.capabilities(plain)['vcs'], 'git-sync')
        caps = dm.capabilities(ig)
        self.assertEqual((caps['vcs'], caps['publish']), ('git-sync', 'legacy'))     # `publish` лишився зашитим
        dm.write_module_state(plain, 'git-sync', enabled=False)
        dm.write_module_state(ig, 'git-sync', enabled=False)
        self.assertIsNone(dm.capabilities(plain)['vcs'])
        self.assertEqual(dm.capabilities(ig)['vcs'], 'legacy')

    def test_vcs_in_an_integrations_space_survives_an_unreadable_space_json_like_publish(self):
        ig = self.new_space('Integ', integrations=True)
        _write(self.space_json(ig), '{broken')
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy',
                                               'error': 'space-json-unreadable'})
        plain = self.new_space('Plain')
        _write(self.space_json(plain), '{broken')                        # без інтеграцій рішення невідомі
        self.assertEqual(dm.capabilities(plain), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None,
                                                  'error': 'space-json-unreadable'})

    def test_the_fallback_dict_names_vcs_when_the_cache_key_itself_breaks(self):
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        with mock.patch.object(dm, '_caps_key', side_effect=RuntimeError('bug')):
            self.assertEqual(dm.capabilities(plain), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None,
                                                      'error': 'module-error'})
            self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None,
                                                   'vcs': 'legacy', 'error': 'module-error'})

    def test_a_module_error_of_one_role_keeps_vcs_legacy_in_an_integrations_space(self):
        """Гілка `except ModuleError` (роль не вирішилась): `publish` і `vcs` — зашитий шлях ЛІГА, решта — `None`."""
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        with mock.patch.object(dm, '_provider_for', side_effect=dm.ModuleError('bad-manifest', message='x')):
            self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None,
                                                   'vcs': 'legacy', 'error': 'bad-manifest'})
            self.assertEqual(dm.capabilities(plain), {'publish': None, 'tokens': None, 'comments': None,
                                                      'vcs': None, 'error': 'bad-manifest'})

    def test_no_modules_at_all(self):
        plain = self.new_space('Plain')
        ig = self.new_space('Integ', integrations=True)
        self.assertEqual(dm.capabilities(plain), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None})
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': 'legacy', 'vcs': 'legacy'})

    def counting(self):
        calls = []
        real = dm._provider_for

        def spy(role, space, *rest):               # `capabilities` передає ще й ледачий каталог (`get_cat`)
            calls.append(role)
            return real(role, space, *rest)
        return calls, mock.patch.object(dm, '_provider_for', spy)

    def test_cached_until_space_json_changes(self):
        self.mk('static-publish')
        sp = self.new_space()
        calls, patch = self.counting()
        with patch:
            self.assertEqual(dm.capabilities(sp)['publish'], 'static-publish')
            n = len(calls)
            self.assertGreater(n, 0)
            for _ in range(3):
                dm.capabilities(sp)
            self.assertEqual(len(calls), n, 'повторні виклики беруть кеш')
            dm.write_module_state(sp, 'static-publish', enabled=False)
            self.assertIsNone(dm.capabilities(sp)['publish'])
            self.assertGreater(len(calls), n, 'зміна space.json скидає кеш')

    def test_cached_until_a_manifest_changes(self):
        d = self.mk('static-publish')
        sp = self.new_space()
        calls, patch = self.counting()
        with patch:
            self.assertEqual(dm.capabilities(sp)['publish'], 'static-publish')
            n = len(calls)
            man = _read(os.path.join(d, 'module.json'))
            man['roles'] = ['tokens']
            _write(os.path.join(d, 'module.json'), man)
            _bump(os.path.join(d, 'module.json'))
            # неявний `static-publish` лишається ввімкненим, але вже з іншою роллю
            self.assertEqual(dm.capabilities(sp), {'publish': None, 'tokens': 'static-publish', 'comments': None, 'vcs': None})
            self.assertGreater(len(calls), n)

    def test_cache_follows_a_server_py_that_starts_to_fail(self):
        d = self.mk('static-publish')
        sp = self.new_space()
        self.assertEqual(dm.capabilities(sp)['publish'], 'static-publish')
        _write(os.path.join(d, 'server.py'), 'def check(:\n')
        _bump(os.path.join(d, 'server.py'))
        self.assertIsNone(dm.capabilities(sp)['publish'])

    def test_cache_is_per_space_and_follows_integrations_flag(self):
        self.mk('static-publish')
        a = self.new_space('Alpha')
        b = self.new_space('Beta')
        self.assertEqual(dm.capabilities(a)['publish'], 'static-publish')
        self.assertEqual(dm.capabilities(b)['publish'], 'static-publish')
        b2 = dict(b, integrations=True)                      # реєстр змінив прапорець — ключ кешу інший
        self.assertEqual(dm.capabilities(b2)['publish'], 'legacy')

    def test_returned_dict_is_a_copy(self):
        self.mk('static-publish')
        sp = self.new_space()
        dm.capabilities(sp)['publish'] = 'hacked'
        self.assertEqual(dm.capabilities(sp)['publish'], 'static-publish')

    def test_broken_space_json_reports_the_error_instead_of_raising(self):
        self.mk('static-publish')
        sp = self.new_space()
        _write(self.space_json(sp), '{broken')
        self.assertEqual(dm.capabilities(sp),
                         {'publish': None, 'tokens': None, 'comments': None, 'vcs': None, 'error': 'space-json-unreadable'})
        _write(self.space_json(sp), json.dumps({'name': 'fixed'}))            # полагодили — помилка зникла
        self.assertEqual(dm.capabilities(sp), {'publish': 'static-publish', 'tokens': None, 'comments': None, 'vcs': None})
        ig = self.new_space('Integ', integrations=True)
        _write(self.space_json(ig), '{broken')
        self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy',
                                               'error': 'space-json-unreadable'})   # publish — ЛІГА-шлях; коментарі — не 'legacy'

    def test_capabilities_is_total(self):
        sp = self.new_space()
        ig = self.new_space('Integ', integrations=True)
        with mock.patch.object(dm, '_provider_for', side_effect=dm.ModuleError('bad-manifest', message='x')):
            self.assertEqual(dm.capabilities(sp), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None, 'error': 'bad-manifest'})
            self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy',
                                                   'error': 'bad-manifest'})
        dm.reset_caches()
        with mock.patch.object(dm, '_provider_for', side_effect=RuntimeError('bug')):
            self.assertEqual(dm.capabilities(sp), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None, 'error': 'module-error'})
            self.assertEqual(dm.capabilities(ig), {'publish': 'legacy', 'tokens': None, 'comments': None, 'vcs': 'legacy',
                                                   'error': 'module-error'})
        dm.reset_caches()
        with mock.patch.object(dm, '_catalog_sig', side_effect=OSError('disk')):
            self.assertEqual(dm.capabilities(sp)['error'], 'module-error')
        self.assertEqual(dm.capabilities({'id': 'x'}), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None})   # чужа форма запису

    def test_the_cache_key_is_taken_before_the_compute(self):
        """Файл змінився ПІСЛЯ того, як роль обчислено: у кеш іде ключ ДО обчислення, тож наступний виклик
        бачить новий стан, а не застарілий результат під новим ключем."""
        self.mk('static-publish')
        sp = self.new_space()
        real = dm._provider_for
        flipped = []

        def spy(role, space, *rest):
            res = real(role, space, *rest)
            if not flipped:
                flipped.append(1)
                dm.write_module_state(sp, 'static-publish', enabled=False)
            return res
        with mock.patch.object(dm, '_provider_for', spy):
            self.assertEqual(dm.capabilities(sp)['publish'], 'static-publish')     # обчислено за старим станом
        self.assertIsNone(dm.capabilities(sp)['publish'])

    def test_capabilities_is_total_for_non_dict_input(self):
        for bad in ('x', 5, ['a'], ('a',), True, object(), 3.5):
            self.assertEqual(dm.capabilities(bad), {'publish': None, 'tokens': None, 'comments': None, 'vcs': None}, repr(bad))

    def test_the_cache_key_is_per_space_flag_space_json_and_every_module_file(self):
        d = self.mk('pub-a')
        sp = self.new_space()
        k1 = dm._caps_key(sp)
        self.assertEqual(dm._caps_key(sp), k1)
        self.assertNotEqual(dm._caps_key(dict(sp, integrations=True)), k1)
        self.assertNotEqual(dm._caps_key(dict(sp, id='other')), k1)
        for name in ('module.json', 'server.py'):
            path = os.path.join(d, name)
            _bump(path)
            self.assertNotEqual(dm._caps_key(sp), k1, name)
            k1 = dm._caps_key(sp)
        _bump(self.space_json(sp))
        self.assertNotEqual(dm._caps_key(sp), k1)
        k1 = dm._caps_key(sp)
        self.mk('pub-b')                                     # новий модуль — теж інший ключ
        self.assertNotEqual(dm._caps_key(sp), k1)


# --------------------------------------------------------------------------------------------- check

class CheckTest(Env):
    def setUp(self):
        super().setUp()
        self.pub_secret_module('chk', server=SEEN_SERVER)
        self.sp = self.new_space()

    def test_ctx_has_resolved_settings_and_only_own_secrets(self):
        self.pub_secret_module('other', server=SEEN_SERVER)
        dm.write_secrets(self.sp['id'], 'chk', {'password': 'pw-chk'})
        dm.write_secrets(self.sp['id'], 'other', {'password': 'pw-other', 'token': 'tk-other'})
        dm.write_module_state(self.sp, 'chk', enabled=True, settings={'folder': '{home}/mine/{space_id}'})
        self.assertEqual(dm.check(self.sp, 'chk'), {'ok': True})
        # `_plain`: до даних ctx ядро додає ще два засоби (`folder_ok`, `ModuleError`) — їх окремий тест нижче
        self.assertEqual(_plain(builtins._DEAI_SEEN), {
            'space': {'id': self.sp['id'], 'path': self.sp['path']},
            'settings': {'folder': os.path.join(self.home, 'mine', self.sp['id'])},
            'secrets': {'password': 'pw-chk'}})

    def test_module_ctx_is_what_check_gets_and_accepts_an_id(self):
        dm.write_secrets(self.sp['id'], 'chk', {'password': 'pw-chk'})
        dm.write_module_state(self.sp, 'chk', enabled=True)
        want = {'space': {'id': self.sp['id'], 'path': self.sp['path']},
                'settings': {'folder': os.path.join(self.home, 'pub', self.sp['id'])},
                'secrets': {'password': 'pw-chk'}}
        self.assertEqual(_plain(dm.module_ctx(self.sp, 'chk')), want)
        self.assertEqual(_plain(dm.module_ctx(self.sp, dm.catalog()['chk'])), want)
        dm.check(self.sp, 'chk')
        self.assertEqual(_plain(builtins._DEAI_SEEN), want)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.module_ctx(self.sp, 'ghost')
        self.assertEqual(cm.exception.code, 'unknown-module')

    def test_ctx_carries_the_folder_rule_and_the_error_class_for_modules_that_cannot_import_the_core(self):
        """Модуль публікації не імпортує ні `serve`, ні `deai_modules`: правило теки (привʼязане до ЦЬОГО простору)
        й клас `ModuleError` (його код `call()` пропускає як є) він бере з `ctx`."""
        ctx = dm.module_ctx(self.sp, 'chk')
        self.assertEqual(set(ctx) - set(CORE_CTX_KEYS), {'space', 'settings', 'secrets'})
        self.assertIs(ctx['ModuleError'], dm.ModuleError)
        self.assertTrue(callable(ctx['find_tool']))
        rule = ctx['folder_ok']
        self.assertTrue(callable(rule))
        self.assertEqual(rule(self.hp('pub', 'x')), (True, None))
        self.assertEqual(rule(self.sp['path']), (False, 'path-registered'))        # той самий простір, що в ctx
        self.assertEqual(rule(self.home), (False, 'path-too-broad'))
        self.assertEqual(rule('rel/pub'), dm.folder_ok(self.sp, 'rel/pub'))        # відносна — від теки ЦЬОГО простору
        other = self.new_space('Beta')
        self.assertEqual(dm.module_ctx(other, 'chk')['folder_ok'](other['path']), (False, 'path-registered'))
        self.assertEqual(dm.module_ctx(other, 'chk')['folder_ok'](self.sp['path']), (False, 'path-registered'))
        # ctx живе лише в пам'яті ядра: дані з нього серіалізуються без засобів
        json.dumps(_plain(ctx))

    def test_ctx_carries_a_cache_dir_per_space_and_module_that_the_core_never_creates(self):
        """`cache_dir` (4a) — лише ШЛЯХ `<DEAI_HOME>/cache/<простір>/<модуль>`: теку створює модуль (`_ctx` будується на
        кожен `check`, і створення тут падало б на незаписуваному `DEAI_HOME`)."""
        want = os.path.join(spaces.home(), 'cache', self.sp['id'], 'chk')
        self.assertEqual(dm.module_ctx(self.sp, 'chk')['cache_dir'], want)
        dm.check(self.sp, 'chk')
        self.assertEqual(builtins._DEAI_SEEN['cache_dir'], want)
        self.assertFalse(os.path.exists(os.path.join(spaces.home(), 'cache')), 'ядро не створює ні кеш, ні його теки')
        other = self.new_space('Beta')
        self.assertEqual(dm.module_ctx(other, 'chk')['cache_dir'], os.path.join(spaces.home(), 'cache', other['id'], 'chk'))
        self.pub_secret_module('second')
        self.assertEqual(dm.module_ctx(self.sp, 'second')['cache_dir'], os.path.join(spaces.home(), 'cache', self.sp['id'], 'second'))

    def test_the_cache_dir_of_a_space_without_an_id_is_still_a_path_under_the_cache(self):
        """Запис без `id` (чужа форма) шлях не ламає: підставляється `_`, а не порожній сегмент (тоді шлях збігся б із кешем модуля)."""
        ctx = dm.module_ctx({'path': self.sp['path']}, 'chk')
        self.assertEqual(ctx['cache_dir'], os.path.join(spaces.home(), 'cache', '_', 'chk'))

    def test_secrets_are_read_only_for_modules_that_declare_them(self):
        """Зіпсований `secrets.json` не мусить ламати модуль без секретів (css-tokens)."""
        self.mk('plain', roles=('tokens',), settings=[{'key': 'file', 'type': 'path', 'default': '/f.css'}])
        os.makedirs(self.deai, exist_ok=True)
        _write(self.secrets_file, '{broken')
        self.assertEqual(dm.module_ctx(self.sp, 'plain')['secrets'], {})
        self.assertEqual(dm.check(self.sp, 'plain'), {'ok': True})
        with self.assertRaises(dm.ModuleError) as cm:                    # а з оголошеним секретом — вголос
            dm.module_ctx(self.sp, 'chk')
        self.assertEqual(cm.exception.code, 'secrets-unreadable')

    def test_last_result_is_cached_for_the_listing(self):
        self.assertNotIn((self.sp['id'], 'chk'), dm._LAST_CHECK)
        res = dm.check(self.sp, 'chk')
        self.assertEqual(dm._LAST_CHECK[(self.sp['id'], 'chk')], res)
        self.assertEqual(dm.last_check(self.sp['id'], 'chk'), res)
        self.assertIsNone(dm.last_check(self.sp['id'], 'nope'))

    def test_a_negative_result_is_returned_not_raised(self):
        self.mk('neg', server='def check(ctx):\n    return {"ok": False, "error": "no-folder", "detail": "x", "junk": 1}\n'
                              'def publish(ctx, b, t):\n    return {}\n')
        res = dm.check(self.sp, 'neg')
        self.assertEqual(res, {'ok': False, 'error': 'no-folder', 'detail': 'x'})
        self.assertEqual(dm._LAST_CHECK[(self.sp['id'], 'neg')], res)

    def test_a_crashing_check_raises_and_is_remembered(self):
        self.mk('crash', server='def check(ctx):\n    raise ValueError("bad " + ctx["secrets"].get("password", ""))\n'
                                'def publish(ctx, b, t):\n    return {}\n',
                settings=[{'key': 'password', 'type': 'secret'}])
        dm.write_secrets(self.sp['id'], 'crash', {'password': 'hunter2-secret'})
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'crash')
        self.assertEqual(cm.exception.code, 'module-error')
        last = dm._LAST_CHECK[(self.sp['id'], 'crash')]
        self.assertEqual((last['ok'], last['error']), (False, 'module-error'))
        self.assertNotIn('hunter2-secret', json.dumps(last))
        self.assertIn('ValueError', last['detail'])

    def test_a_secret_in_the_result_text_is_cut(self):
        self.mk('leaky', server='def check(ctx):\n    return {"ok": False, "error": "x", "detail": "pw=" + ctx["secrets"]["password"]}\n'
                                'def publish(ctx, b, t):\n    return {}\n',
                settings=[{'key': 'password', 'type': 'secret'}])
        dm.write_secrets(self.sp['id'], 'leaky', {'password': 'hunter2-secret'})
        res = dm.check(self.sp, 'leaky')
        self.assertNotIn('hunter2-secret', json.dumps(res))
        self.assertNotIn('hunter2-secret', repr(dm._LAST_CHECK))

    def test_a_malformed_result_is_a_module_error(self):
        for i, body in enumerate(('return "fine"', 'return {"ok": "yes"}', 'return None', 'return {}')):
            self.mk(f'bad-{i}', server=f'def check(ctx):\n    {body}\ndef publish(ctx, b, t):\n    return {{}}\n')
            with self.assertRaises(dm.ModuleError) as cm:
                dm.check(self.sp, f'bad-{i}')
            self.assertEqual(cm.exception.code, 'module-error', body)

    def test_timeout(self):
        self.mk('slow', server='import builtins\ndef check(ctx):\n    builtins._DEAI_GATE.wait(10)\n'
                               '    return {"ok": True}\ndef publish(ctx, b, t):\n    return {}\n')
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            t0 = time.monotonic()
            with self.assertRaises(dm.ModuleError) as cm:
                dm.check(self.sp, 'slow')
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual((cm.exception.code, cm.exception.status), ('check-timeout', 504))
        self.assertEqual(dm._LAST_CHECK[(self.sp['id'], 'slow')]['error'], 'check-timeout')

    def test_a_module_with_check_timeout_s_gets_that_long_for_its_check(self):
        """Ключ реально діє: `check` модуля, що відповідає за 1 с, при `CHECK_TIMEOUT` 0.2 — `check-timeout` без ключа
        і вердикт із `check_timeout_s: 3`."""
        body = 'import time\ndef check(ctx):\n    time.sleep(1)\n    return {"ok": True}\ndef publish(ctx, b, t):\n    return {}\n'
        self.mk('cts-slow', server=body)
        self.mk('cts-patient', server=body, patch={'check_timeout_s': 3})
        with mock.patch.object(dm, 'CHECK_TIMEOUT', 0.2):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.check(self.sp, 'cts-slow')
            self.assertEqual(cm.exception.code, 'check-timeout')
            self.assertEqual(dm.check(self.sp, 'cts-patient'), {'ok': True})

    def test_default_timeout_is_five_seconds(self):
        self.assertEqual(dm.CHECK_TIMEOUT, 5)

    def test_bad_stored_settings_become_a_remembered_failure(self):
        self.mk('needs', roles=('tokens',), server=ALL_FNS,
                settings=[{'key': 'file', 'type': 'path', 'required': True}])
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'needs')
        self.assertEqual(cm.exception.code, 'bad-settings')
        last = dm._LAST_CHECK[(self.sp['id'], 'needs')]
        self.assertEqual((last['ok'], last['error']), (False, 'bad-settings'))
        self.assertIn('file', last['detail'])

    def test_unknown_and_broken_module(self):
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'ghost')
        self.assertEqual((cm.exception.code, cm.exception.status), ('unknown-module', 404))
        self.mk('broken', patch={'api': 3})
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'broken')
        self.assertEqual(cm.exception.code, 'bad-manifest')

    def test_unreadable_space_json_is_reported_not_swallowed(self):
        _write(self.space_json(self.sp), '{broken')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'chk')
        self.assertEqual(cm.exception.code, 'space-json-unreadable')

    def test_check_of_a_disabled_module_still_runs(self):
        self.assertEqual(dm.check(self.sp, 'chk'), {'ok': True})


if __name__ == '__main__':
    unittest.main()
