"""Свої модулі простору в каталозі ядра (етап 3c, Task 3–4): `catalog(space)`, недовірений код не виконується,
довірений — зі знімка, примітки, тайм-аут завантаження; ролі «на папері», постачальник без запасного шляху, довіра в
ядрі (`trust_view`, `grant_trust`, `revoke_trust`). Спека `docs/superpowers/specs/2026-10-22-own-modules-trust-design.md`.

Оточення — `Env` з `test_modules` (тимчасові `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`, тека вбудованих — тимчасова). Системне
вікно НІКОЛИ не показується: шов `DEAI_TRUST_CONFIRM` (діє з тимчасовим `DEAI_HOME`) чи підмінений `module_trust.ask`.
Мітка-файл `DEAI_OWN_CANARY`: `server.py` фікстури дописує в неї свій `__file__` при КОЖНОМУ виконанні верхнього рівня.
"""
import builtins
import json
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import deai_modules as dm  # noqa: E402
import module_trust as mt  # noqa: E402
from test_modules import Env, _write, _read, ALL_FNS, race  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


OWN_SERVER = '''import os
VERSION = "v1"
_p = os.environ.get("DEAI_OWN_CANARY")
if _p:
    with open(_p, "a") as _f:
        _f.write(__file__ + "\\n")


def check(ctx):
    return {"ok": True, "detail": "own " + VERSION}


def publish(ctx, build_dir, task):
    return {"folder": build_dir}


def tokens(ctx):
    return {"tokens": {}, "source": "own"}


def client_config(ctx):
    return {}


def list(ctx, channel):
    return []


def resolve(ctx, channel, pin_id, resolved):
    return {"ok": True}
'''


#: Той самий модуль, що засинає на верхньому рівні ПІСЛЯ запису мітки: ворота відчиняє `Env.tearDown` (потік-сирота не
#: прокинеться посеред чужого тесту й не допише в чужу мітку, на відміну від `time.sleep` до запису).
SLEEPY = OWN_SERVER + 'import builtins\nbuiltins._DEAI_GATE.wait(10)\n'


def _unlock(tree):
    """Знімки довіри — 0500/0400, а тести ставлять ще й chmod 0: `rmtree(…, ignore_errors=True)` мовчки лишив би такі
    теки на диску. Повертає право запису ТЕКАМ (файлам не треба: видалення — право теки, що їх містить)."""
    for root, dirs, _files in os.walk(tree):
        for d in dirs:
            try:
                os.chmod(os.path.join(root, d), 0o700)
            except OSError:
                pass


class OwnEnv(Env):
    def setUp(self):
        super().setUp()
        # Власне присвоєння, хоч `Env` уже поставив те саме: охоронець `test_serve` (`SPACE_WRITERS` →
        # `_assigns_deai_home`) розбирає джерело САМЕ цього файла — присвоєння в імпортованому `Env` він не бачить
        os.environ['DEAI_HOME'] = self.deai
        self.canary = os.path.join(self.tmp, 'canary.log')
        os.environ['DEAI_OWN_CANARY'] = self.canary
        self.addCleanup(os.environ.pop, 'DEAI_OWN_CANARY', None)
        os.environ.pop(mt.SEAM_ENV, None)
        self.addCleanup(os.environ.pop, mt.SEAM_ENV, None)
        # Сітка: справжнє системне вікно в тесті недосяжне. Шов `DEAI_TRUST_CONFIRM` відповідає в `confirm` РАНІШЕ за
        # `confirm_command`, тож тестам зі швом чи підміненим `ask` вона не заважає, а `subprocess` решти коду не чіпає
        net = mock.patch.object(mt, 'confirm_command', side_effect=AssertionError('системне вікно в тесті'))
        net.start()
        self.addCleanup(net.stop)
        mt.clear_declined()
        self.sp = self.new_space()

    def tearDown(self):
        _unlock(self.tmp)                  # до `Env.tearDown`: той робить `rmtree(…, ignore_errors=True)`
        super().tearDown()

    def own(self, mid='acme', roles=('publish',), sp=None, server=OWN_SERVER, settings=None, extra=None):
        d = os.path.join((sp or self.sp)['path'], 'modules', mid)
        man = {'api': 1, 'id': mid, 'name': mid.title(), 'version': '1.0.0', 'roles': list(roles),
               'settings': settings or [{'key': 'token', 'type': 'secret', 'label': 'Token'}]}
        man.update(extra or {})
        _write(os.path.join(d, 'module.json'), man)
        _write(os.path.join(d, 'server.py'), server)
        return d

    def trust(self, mid='acme', sp=None):
        """Довіра в обхід ядра (Task 3 ще не має `grant_trust`): знімок + запис."""
        sp = sp or self.sp
        sc = mt.scan(os.path.join(sp['path'], 'modules', mid), with_data=True)
        mt.ensure_snapshot(sc)
        mt.put_record(mt.key_for(sp['path'], mid), {
            'id': mid, 'name': mid, 'version': '1', 'roles': ['publish'], 'hash': sc.hash,
            'files': [{'path': p, 'size': n, 'sha256': h} for p, n, h in sc.files], 'trusted_at': 'x'})
        return sc.hash

    def ran(self):
        try:
            with open(self.canary) as f:
                return [ln for ln in f.read().splitlines() if ln]
        except FileNotFoundError:
            return []

    def enable_raw(self, mid='acme', roles=('publish',), sp=None):
        """Як колега, що закомітив `space.json`: запис увімкненого свого модуля без жодної довіри тут."""
        p = self.space_json(sp or self.sp)
        data = _read(p)
        data.setdefault('modules', {})[mid] = {'enabled': True, 'settings': {}, 'roles': list(roles)}
        _write(p, data)


class CatalogTest(OwnEnv):
    def test_catalog_without_space_is_builtin_only(self):
        self.mk('pub')
        self.own()
        self.assertEqual(sorted(dm.catalog()), ['pub'])
        self.assertEqual(sorted(dm.catalog(self.sp)), ['acme', 'pub'])

    def test_untrusted_is_listed_from_its_manifest_and_never_runs(self):
        self.own(settings=[{'key': 'site', 'type': 'text', 'label': 'Site'}])
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.origin, m.trust, m.record, m.status, m.error_code),
                         ('space', 'untrusted', False, 'untrusted', 'module-untrusted'))
        self.assertEqual((m.name, m.roles, [s['key'] for s in m.settings]), ('Acme', ['publish'], ['site']))
        self.assertEqual(m.source, os.path.join('~', 'work', 'alpha', 'modules', 'acme'))
        dm.effective_state(self.sp)
        dm.capabilities(self.sp)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'acme')
        self.assertEqual((cm.exception.code, cm.exception.status), ('module-untrusted', 409))
        for call in (lambda: dm.preflight(self.sp, 'acme', enabling=True),
                     lambda: dm.preflight(self.sp, 'acme', enabling=True, replace=True),
                     lambda: dm.write_module_state(self.sp, 'acme', enabled=True)):
            with self.assertRaises(dm.ModuleError) as cm:
                call()
            self.assertEqual(cm.exception.code, 'module-untrusted')
        self.assertEqual(self.ran(), [], 'код недовіреного модуля виконано')
        self.assertNotIn('acme', dm.space_modules(self.sp))

    def test_settings_secrets_and_disable_of_untrusted_are_allowed(self):
        self.own()
        dm.validate_settings('acme', {}, self.sp)
        dm.write_secrets(self.sp['id'], 'acme', {'token': 's3'}, space=self.sp)
        dm.write_module_state(self.sp, 'acme', enabled=False)
        self.assertEqual(self.ran(), [])

    def test_trusted_runs_from_the_snapshot(self):
        self.own()
        h = self.trust()
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.record), ('ok', 'trusted', True))
        self.assertEqual(m.dir, mt.snapshot_dir(h))
        self.assertEqual(dm.check(self.sp, 'acme'), {'ok': True, 'detail': 'own v1'})
        self.assertTrue(self.ran())
        self.assertTrue(all(p.startswith(mt.trusted_root()) for p in self.ran()), self.ran())

    def test_changed_folder_keeps_running_the_trusted_snapshot(self):
        d = self.own()
        self.trust()
        _write(os.path.join(d, 'server.py'), OWN_SERVER.replace('"v1"', '"v2"'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.trust, m.status), ('changed', 'ok'))
        self.assertEqual(dm.check(self.sp, 'acme')['detail'], 'own v1')

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_refused_folder(self):
        d = self.own()
        os.symlink(os.path.join(d, 'server.py'), os.path.join(d, 'alias.py'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.trust_error, m.error_code), ('error', 'refused', 'symlink', 'module-untrusted'))
        self.assertIn('alias.py', m.error)
        os.remove(os.path.join(d, 'alias.py'))
        self.trust()
        os.symlink(os.path.join(d, 'server.py'), os.path.join(d, 'alias.py'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.record), ('ok', 'refused', True), 'знімок працює, нова версія — ні')

    def test_damaged_snapshot_is_untrusted_with_a_record(self):
        self.own()
        h = self.trust()
        snap = mt.snapshot_dir(h)
        os.chmod(snap, 0o700)
        os.chmod(os.path.join(snap, 'server.py'), 0o600)
        _write(os.path.join(snap, 'server.py'), 'raise SystemExit')
        mt.forget(snap)
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.trust_error, m.record), ('untrusted', 'untrusted', 'snapshot-damaged', True))
        self.assertEqual(self.ran(), [])

    def test_unreadable_trust_file_means_untrusted(self):
        self.own()
        self.trust()
        _write(mt.trust_file(), '{oops')
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust_error), ('untrusted', 'trust-unreadable'))

    def test_notes_and_ignored_folders(self):
        self.mk('pub')
        self.own('pub')                                     # id вбудованого
        os.makedirs(os.path.join(self.sp['path'], 'modules', '_drafts'))
        os.makedirs(os.path.join(self.sp['path'], 'modules', 'nomanifest'))
        _write(os.path.join(self.sp['path'], 'modules', 'README'), 'x')
        self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules/pub', 'code': 'id-taken'}])
        self.assertNotIn('nomanifest', dm.catalog(self.sp))
        self.assertEqual(dm.catalog(self.sp)['pub'].origin, 'builtin')

    def test_too_many_modules(self):
        for i in range(dm.MAX_OWN_MODULES + 1):
            self.own(f'm{i:02}')
        cat = dm.catalog(self.sp)
        self.assertEqual(sum(1 for m in cat.values() if m.origin == 'space'), dm.MAX_OWN_MODULES)
        self.assertEqual(dm.own_notes(self.sp), [{'folder': f'modules/m{dm.MAX_OWN_MODULES:02}', 'code': 'too-many-modules'}])

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_modules_link_and_unreadable(self):
        real = os.path.join(self.tmp, 'elsewhere')
        os.makedirs(real)
        os.symlink(real, os.path.join(self.sp['path'], 'modules'))
        self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules', 'code': 'modules-link'}])
        os.remove(os.path.join(self.sp['path'], 'modules'))
        self.own()
        base = os.path.join(self.sp['path'], 'modules')
        os.chmod(base, 0)
        try:                                   # не `addCleanup`: ті йдуть ПІСЛЯ `tearDown`, що вже стер тимчасову теку
            if os.access(base, os.R_OK):
                self.skipTest('root читає все')
            self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules', 'code': 'modules-unreadable'}])
        finally:
            os.chmod(base, 0o755)

    def test_two_spaces_with_the_same_bytes_do_not_share_module_objects(self):
        sp2 = self.rec(spaces.create_space('Beta', 'space-2', self.hp('work', 'beta')))
        self.own()
        self.own(sp=sp2)
        self.trust()
        self.trust(sp=sp2)
        a, b = dm.catalog(self.sp)['acme'], dm.catalog(sp2)['acme']
        self.assertEqual(a.dir, b.dir, 'одна тека знімка')
        self.assertIsNot(a, b)
        self.assertNotEqual(a.source, b.source)

    def test_load_timeout(self):
        self.own(server=SLEEPY)
        self.trust()
        with mock.patch.object(dm, 'LOAD_TIMEOUT', 0.3):
            t0 = time.monotonic()
            m = dm.catalog(self.sp)['acme']
            self.assertLess(time.monotonic() - t0, 3)
            self.assertEqual((m.status, m.error_code), ('error', 'module-error'))
            self.assertIn('timed out', m.error)
            t0 = time.monotonic()
            dm.catalog(self.sp)
            self.assertLess(time.monotonic() - t0, 1, 'результат тайм-ауту не закешовано')

    def test_enabling_a_trusted_own_module_writes_its_roles(self):
        self.own()
        self.trust()
        dm.write_module_state(self.sp, 'acme', enabled=True, replace=True)
        self.assertEqual(_read(self.space_json(self.sp))['modules']['acme']['roles'], ['publish'])

    def test_builtin_cache_eviction_does_not_drop_snapshots(self):
        self.mk('pub')
        self.own()
        self.trust()
        dm.catalog(self.sp)
        n = len(self.ran())
        dm.catalog()
        dm.catalog(self.sp)
        self.assertEqual(len(self.ran()), n, 'знімок виконано вдруге без змін')


class CatalogExtraTest(OwnEnv):
    """Те, що `CatalogTest` лишає без свідка: помилки маніфесту, теки-посилання, межі кешу, паралельність, коди ядра."""

    def _manifest(self, d, body):
        with open(os.path.join(d, 'module.json'), 'wb') as f:
            f.write(body if isinstance(body, bytes) else body.encode('utf-8'))

    def test_a_bad_manifest_is_refused_without_running_anything(self):
        d = self.own()
        deep = '[' * 200000 + ']' * 200000
        big = '{"api": 1, "pad": "' + 'x' * spaces.MAX_JSON_BYTES + '"}'
        other = json.dumps({'api': 1, 'id': 'other', 'roles': ['publish']})
        cases = [('not json', '{oops', 'module.json:'), ('not utf-8', b'\xff\xfe{', 'module.json:'),
                 ('not an object', '[]', 'not an object'), ('other id', other, "differs from the folder name"),
                 ('too big', big, 'bigger than'), ('too deep', deep, 'nested too deep'),
                 ('bad role', json.dumps({'api': 1, 'id': 'acme', 'roles': ['nope']}), 'unknown role')]
        for name, body, why in cases:
            with self.subTest(name):
                self._manifest(d, body)
                m = dm.catalog(self.sp)['acme']
                self.assertEqual((m.status, m.trust, m.trust_error, m.error_code, m.record),
                                 ('error', 'refused', 'bad-manifest', 'module-untrusted', False))
                self.assertTrue(m.error.startswith('bad-manifest: '), m.error)
                self.assertIn(why, m.error)
                self.assertTrue(dm.untrusted_own(m))
        os.remove(os.path.join(d, 'module.json'))
        os.mkdir(os.path.join(d, 'module.json'))                 # `module.json` — тека: маніфесту нема
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust_error), ('error', 'bad-manifest'))
        self.assertIn('not found', m.error)
        self.assertEqual(self.ran(), [])

    def test_a_bad_manifest_in_the_folder_does_not_hide_a_working_snapshot(self):
        d = self.own()
        self.trust()
        self._manifest(d, '{oops')
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.trust_error, m.record), ('ok', 'refused', 'bad-manifest', True))
        self.assertEqual(dm.check(self.sp, 'acme')['detail'], 'own v1')
        self.assertFalse(dm.untrusted_own(m))

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_module_folder_that_is_a_link_is_refused(self):
        d = self.own()
        moved = os.path.join(self.tmp, 'moved')
        os.rename(d, moved)
        os.symlink(moved, d)
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.trust_error, m.error), ('error', 'refused', 'symlink', 'symlink: .'))
        self.assertEqual(self.ran(), [])

    def test_a_space_without_a_modules_folder_has_no_own_modules_and_no_notes(self):
        self.mk('pub')
        self.assertEqual(dm.own_notes(self.sp), [])
        self.assertEqual(sorted(dm.catalog(self.sp)), ['pub'])

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_modules_that_is_a_file_is_a_note_and_gives_no_module(self):
        self.mk('pub')
        _write(os.path.join(self.sp['path'], 'modules'), 'not a folder')
        self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules', 'code': 'modules-link'}])
        self.assertEqual(sorted(dm.catalog(self.sp)), ['pub'])

    def test_notes_never_become_modules(self):
        self.mk('pub')
        self.own('pub')
        for i in range(dm.MAX_OWN_MODULES + 1):
            self.own(f'm{i:02}')
        cat = dm.catalog(self.sp)
        self.assertNotIn(f'm{dm.MAX_OWN_MODULES:02}', cat)
        self.assertEqual(cat['pub'].origin, 'builtin')
        self.assertEqual({n['code'] for n in dm.own_notes(self.sp)}, {'id-taken', 'too-many-modules'})

    def test_an_id_from_the_extra_modules_folder_is_taken_too(self):
        extra = os.path.join(self.tmp, 'extra')
        for mid in ('xmod',):
            _write(os.path.join(extra, mid, 'module.json'), {'api': 1, 'id': mid, 'roles': ['publish']})
            _write(os.path.join(extra, mid, 'server.py'), ALL_FNS)
        os.environ['DEAI_EXTRA_MODULES'] = extra          # `Env.tearDown` повертає змінну
        self.own('xmod')
        self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules/xmod', 'code': 'id-taken'}])
        self.assertEqual(dm.catalog(self.sp)['xmod'].origin, 'builtin')

    def test_layer_off_means_no_own_modules(self):
        self.mk('pub')
        self.own()
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_HOME')                     # `DC_TASKS_FILE` лишився: шар просторів вимкнено
            self.assertFalse(spaces.layer_on())
            self.assertEqual(dm.own_notes(self.sp), [])
            self.assertEqual(dm.own_modules(self.sp), {})
            self.assertEqual(sorted(dm.catalog(self.sp)), ['pub'])

    def test_a_space_without_a_path_has_no_own_modules(self):
        self.own()
        _write(os.path.join(self.tmp, 'cwd', 'modules', 'acme', 'module.json'), {'api': 1, 'id': 'acme', 'roles': []})
        here = os.getcwd()
        os.chdir(os.path.join(self.tmp, 'cwd'))               # шлях «простору» порожній: `modules` від поточної теки — не модулі
        try:
            self.assertEqual(dm.own_modules({'id': 'x', 'path': ''}), {})
            self.assertEqual(dm.own_notes({'id': 'x'}), [])
        finally:
            os.chdir(here)

    def test_a_modules_folder_that_is_a_reparse_point_is_a_note(self):
        # Точка повторного розбору Windows (junction) для `lstat` — тека: рішає `is_link`, а не `S_ISDIR`
        self.own()
        with mock.patch.object(mt, 'is_link', return_value=True):
            self.assertEqual(dm.own_notes(self.sp), [{'folder': 'modules', 'code': 'modules-link'}])
            self.assertEqual(dm.own_modules(self.sp), {})

    def test_untrusted_settings_can_be_written_and_it_can_be_preflighted_without_enabling(self):
        self.own(settings=[{'key': 'site', 'type': 'text', 'label': 'Site'}])
        dm.preflight(self.sp, 'acme')                         # не вмикання — можна
        st = dm.write_module_state(self.sp, 'acme', settings={'site': 'a'})
        self.assertEqual((st['enabled'], st['settings']), (False, {'site': 'a'}))
        entry = _read(self.space_json(self.sp))['modules']['acme']
        self.assertEqual(entry, {'enabled': False, 'settings': {'site': 'a'}})     # без `roles`: не ввімкнено
        with self.assertRaises(dm.ModuleError) as cm:
            dm.validate_settings('acme', {'site': 5}, self.sp)
        self.assertEqual(cm.exception.code, 'bad-settings')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.validate_settings('acme', {}, None)            # без простору своїх модулів не видно
        self.assertEqual(cm.exception.code, 'unknown-module')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_secrets(self.sp['id'], 'acme', {'token': 'x'})
        self.assertEqual(cm.exception.code, 'unknown-module')
        self.assertEqual(self.ran(), [])

    def test_enabling_a_builtin_module_writes_no_roles(self):
        self.mk('pub')
        dm.write_module_state(self.sp, 'pub', enabled=True)
        self.assertEqual(_read(self.space_json(self.sp))['modules']['pub'], {'enabled': True})

    def test_module_ctx_and_published_root_find_an_own_module_by_space(self):
        self.own(settings=[{'key': 'folder', 'type': 'path', 'label': 'Folder', 'default': '{space}/out'}])
        self.trust()
        want = os.path.join(self.sp['path'], 'out')
        self.assertEqual(dm.published_root(self.sp, 'acme'), want)
        self.assertEqual(dm.module_ctx(self.sp, 'acme')['settings'], {'folder': want})
        for call in (lambda: dm.published_root(self.sp, 'nope'), lambda: dm.module_ctx(self.sp, 'nope')):
            with self.assertRaises(dm.ModuleError) as cm:
                call()
            self.assertEqual(cm.exception.code, 'unknown-module')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.module_ctx(None, 'acme')                       # без простору своїх модулів не видно
        self.assertEqual(cm.exception.code, 'unknown-module')

    def test_effective_state_lists_own_modules(self):
        self.mk('pub')
        self.own()
        st = dm.effective_state(self.sp)
        self.assertEqual(sorted(st), ['acme', 'pub'])
        self.assertEqual(st['acme'], {'enabled': False, 'implicit': False, 'settings': {}})

    def test_core_codes_have_their_statuses_and_a_module_cannot_throw_them(self):
        want = {'module-untrusted': 409, 'module-changed': 409, 'module-refused': 409, 'trust-needs-ui': 403,
                'trust-declined': 409, 'trust-no-confirm': 409, 'trust-busy': 409, 'trust-unreadable': 409}
        self.assertEqual(dm.CORE_STATUS, want)
        for code, status in want.items():
            self.assertEqual(dm.ModuleError(code).status, status, code)
        self.assertEqual(dm.ModuleError('module-untrusted', 418).status, 418)        # явний статус сильніший
        self.assertEqual(dm.ModuleError('no-such-code').status, 500)
        self.assertEqual(dm.ModuleError('bad-folder').status, 409)                   # таблиця модулів не зачеплена
        self.assertFalse(set(want) & set(dm.STATUS), 'коди ядра — поза `STATUS`: модуль не кине їх від свого імені')
        self.own(server=OWN_SERVER.replace('return {"ok": True, "detail": "own " + VERSION}',
                                           'raise ctx["ModuleError"]("module-untrusted", message="x")'))
        self.trust()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'acme')
        self.assertEqual((cm.exception.code, cm.exception.status), ('module-error', 502))

    def test_folders_with_a_bad_id_are_ignored_even_with_a_manifest(self):
        base = os.path.join(self.sp['path'], 'modules')
        for name in ('_drafts', 'Upper', 'with space', '-dash', 'x' * 41):
            _write(os.path.join(base, name, 'module.json'), {'api': 1, 'id': name, 'roles': ['publish']})
        self.assertEqual(dm.own_notes(self.sp), [])
        self.assertEqual(dm.own_modules(self.sp), {})

    def test_a_space_without_own_modules_does_not_touch_trust_json(self):
        _write(mt.trust_file(), '{oops')
        with mock.patch.object(mt, 'load_records', side_effect=AssertionError('trust.json прочитано без потреби')):
            self.assertEqual(dm.catalog(self.sp), {})

    def test_catalog_is_alphabetical_across_builtin_and_own_modules(self):
        self.mk('pub')
        self.mk('zed')
        self.own('acme')
        self.own('mid')
        self.assertEqual(list(dm.catalog(self.sp)), ['acme', 'mid', 'pub', 'zed'])

    def test_an_untrusted_card_carries_the_whole_manifest(self):
        self.own(extra={'publish_target': 'url', 'version': '2.3.4'},
                 settings=[{'key': 'site', 'type': 'text', 'label': 'Site', 'default': 'x'}])
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.version, m.api, m.publish_target, m.settings[0]['default']), ('2.3.4', 1, 'url', 'x'))
        self.assertEqual((m.client, m.fn('check'), m.dir), ((), None, os.path.join(self.sp['path'], 'modules', 'acme')))

    def test_clones_do_not_share_lists_with_each_other_or_with_the_cache(self):
        self.own()
        self.trust()
        a = dm.catalog(self.sp)['acme']
        b = dm.catalog(self.sp)['acme']
        self.assertIsNot(a, b)
        self.assertIsNot(a.roles, b.roles)
        self.assertIsNot(a.settings, b.settings)
        self.assertIsNot(a.settings[0], b.settings[0])
        a.roles.append('tokens')
        a.settings[0]['label'] = 'changed'
        c = dm.catalog(self.sp)['acme']
        self.assertEqual((c.roles, c.settings[0]['label']), (['publish'], 'Token'))

    def test_a_long_refusal_text_is_clipped(self):
        d = self.own()
        deep = os.path.join(d, 'a' * 100, 'b' * 100, 'c' * 100)
        _write(os.path.join(deep, 'f\x07'), 'x')
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust_error), ('error', 'bad-name'))
        self.assertEqual(len(m.error), dm.MAX_MESSAGE)
        self.assertTrue(m.error.startswith('bad-name: '))

    def test_a_trusted_module_that_fails_to_load_is_an_error_not_untrusted(self):
        self.own(server='raise RuntimeError("boom")\n')
        self.trust()
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.error_code, m.trust, m.record), ('error', 'module-error', 'trusted', True))
        self.assertIn('boom', m.error)
        self.assertEqual((m.roles, m.version, [x['key'] for x in m.settings]), (['publish'], '1.0.0', ['token']))
        self.assertFalse(dm.untrusted_own(m), 'це збій модуля, а не відсутність довіри')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.check(self.sp, 'acme')
        self.assertEqual(cm.exception.code, 'module-error')

    def test_a_repaired_snapshot_is_loaded_again(self):
        self.own()
        h = self.trust()
        dm.catalog(self.sp)
        self.assertEqual(len(self.ran()), 1)
        snap = mt.snapshot_dir(h)
        os.chmod(snap, 0o700)
        os.chmod(os.path.join(snap, 'server.py'), 0o600)
        _write(os.path.join(snap, 'server.py'), OWN_SERVER.replace('"v1"', '"hacked"'))
        mt.forget(snap)
        self.assertEqual(dm.catalog(self.sp)['acme'].status, 'untrusted')
        self.trust()                                              # повторна довіра заміняє пошкоджений знімок тими самими байтами
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust), ('ok', 'trusted'))
        self.assertEqual(len(self.ran()), 2, 'новий знімок у тій самій теці — нове завантаження, а не застарілий кеш')
        self.assertEqual(dm.check(self.sp, 'acme')['detail'], 'own v1')

    # ---- аліас-посилання не успадковує довіру

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_link_to_a_trusted_module_does_not_inherit_its_trust_in_either_name_order(self):
        # `key_for` бере `realpath`: `modules/aaa -> acme` ділив би запис довіри з `acme` і вантажив його знімок під чужим id
        d = self.own()
        base = os.path.dirname(d)
        for alias in ('aaa', 'zzz'):                           # до `acme` за абеткою і після нього
            os.symlink(d, os.path.join(base, alias))
        self.trust()
        cat = dm.catalog(self.sp)
        acme = cat['acme']
        self.assertEqual((acme.status, acme.trust, acme.record, acme.id), ('ok', 'trusted', True, 'acme'))
        for alias in ('aaa', 'zzz'):
            m = cat[alias]
            self.assertEqual((m.id, m.status, m.trust, m.trust_error, m.record, m.error_code),
                             (alias, 'error', 'refused', 'symlink', False, 'module-untrusted'), alias)
            self.assertTrue(dm.untrusted_own(m))
            with self.assertRaises(dm.ModuleError) as cm:
                dm.write_module_state(self.sp, alias, enabled=True)
            self.assertEqual(cm.exception.code, 'module-untrusted')
        self.assertEqual(dm.check(self.sp, 'acme')['detail'], 'own v1')
        self.assertEqual(len(self.ran()), 1, 'виконано лише знімок `acme`, і один раз')
        self.assertTrue(self.ran()[0].startswith(mt.trusted_root()))

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_link_to_a_module_trusted_in_another_space_does_not_inherit_its_trust(self):
        sp2 = self.rec(spaces.create_space('Beta', 'space-2', self.hp('work', 'beta')))
        d = self.own()
        self.trust()
        os.makedirs(os.path.join(sp2['path'], 'modules'))
        os.symlink(d, os.path.join(sp2['path'], 'modules', 'acme'))
        m = dm.catalog(sp2)['acme']
        self.assertEqual((m.status, m.trust, m.trust_error, m.record), ('error', 'refused', 'symlink', False))
        self.assertTrue(dm.untrusted_own(m))
        self.assertEqual(dm.catalog(self.sp)['acme'].status, 'ok', 'у власному просторі довіра на місці')
        self.assertEqual(len(self.ran()), 1)

    @unittest.skipIf(os.name == 'nt', 'права доступу')
    def test_an_unreadable_module_folder_is_not_a_link_and_keeps_its_trust(self):
        # `Refused('unreadable', '.')` має ту саму `detail`, що й посилання-корінь, але це не аліас: знімок із записом працює
        d = self.own()
        self.trust()
        os.chmod(d, 0o300)                                     # заходити можна (маніфест видно), читати перелік — ні
        try:
            if os.access(d, os.R_OK):
                self.skipTest('root читає все')
            m = dm.catalog(self.sp)['acme']
            self.assertEqual((m.status, m.trust, m.trust_error, m.record), ('ok', 'refused', 'unreadable', True))
        finally:
            os.chmod(d, 0o700)

    def test_the_load_cache_is_per_snapshot_and_id(self):
        # Той самий знімок під іншим id (запис довіри, що вказує на чужий хеш) — НЕ той самий закешований модуль
        self.own()
        snap = mt.snapshot_dir(self.trust())
        first = dm._load_own(snap, 'acme')
        other = dm._load_own(snap, 'other')
        self.assertEqual((first.id, first.status), ('acme', 'ok'))
        self.assertEqual((other.id, other.status, other.error_code), ('other', 'error', 'bad-manifest'))
        self.assertEqual(sorted(dm._OWN_CACHE), [(snap, 'acme'), (snap, 'other')])
        self.assertIs(dm._load_own(snap, 'acme'), first, 'власний запис — з кешу')

    # ---- збій завантаження не губить маніфест

    def _failed_load_keeps_the_manifest(self, m):
        self.assertEqual((m.status, m.error_code, m.trust, m.record), ('error', 'module-error', 'trusted', True))
        self.assertEqual((m.name, m.version, m.roles, [x['key'] for x in m.settings]),
                         ('Acme', '1.0.0', ['publish'], ['token']))
        self.assertFalse(dm.untrusted_own(m))
        # роль тримає й той, що не завантажився: інший постачальник без `replace` не проходить
        self.mk('pub')
        dm.write_module_state(self.sp, 'pub', enabled=True)
        for call in (lambda: dm.preflight(self.sp, 'acme', enabling=True),
                     lambda: dm.write_module_state(self.sp, 'acme', enabled=True)):
            with self.assertRaises(dm.ModuleError) as cm:
                call()
            self.assertEqual((cm.exception.code, cm.exception.message), ('role-taken', 'publish is already provided by pub'))
        self.assertNotIn('acme', dm.space_modules(self.sp))
        dm.write_module_state(self.sp, 'pub', enabled=False)
        dm.write_module_state(self.sp, 'acme', enabled=True)       # роль вільна: вмикається, і в `space.json` її ролі
        self.assertEqual(_read(self.space_json(self.sp))['modules']['acme']['roles'], ['publish'])

    def test_a_load_timeout_keeps_the_manifest(self):
        self.own(server=SLEEPY)
        self.trust()
        with mock.patch.object(dm, 'LOAD_TIMEOUT', 0.3):
            m = dm.catalog(self.sp)['acme']
        self.assertIn('timed out', m.error)
        self._failed_load_keeps_the_manifest(m)

    def test_an_exception_in_the_top_level_keeps_the_manifest(self):
        self.own(server='raise RuntimeError("boom")\n')
        self.trust()
        m = dm.catalog(self.sp)['acme']
        self.assertIn('boom', m.error)
        self._failed_load_keeps_the_manifest(m)

    def test_a_keyboard_interrupt_in_the_top_level_is_a_module_error_that_keeps_the_manifest(self):
        # `_build` пропускає `KeyboardInterrupt` далі — її ловить гілка винятку в потоці завантаження
        self.own(server=OWN_SERVER + 'raise KeyboardInterrupt()\n')
        self.trust()
        m = dm.catalog(self.sp)['acme']
        self.assertEqual(m.error, 'KeyboardInterrupt', 'не «timed out» і сервер не впав')
        self._failed_load_keeps_the_manifest(m)

    def test_a_snapshot_that_cannot_be_scanned_fails_without_a_manifest_and_without_raising(self):
        m = dm._load_own(os.path.join(self.tmp, 'nope'), 'ghost')
        self.assertEqual((m.status, m.error_code, m.roles), ('error', 'bad-manifest', []))

    def test_the_load_thread_is_a_named_daemon(self):
        self.own()
        self.trust()
        made = []

        class Spy(threading.Thread):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                made.append(self)
        with mock.patch.object(threading, 'Thread', Spy):
            self.assertEqual(dm.catalog(self.sp)['acme'].status, 'ok')
        loaders = [t for t in made if t.name.startswith('deai-own-load-')]
        self.assertEqual([(t.name, t.daemon) for t in loaders], [('deai-own-load-acme', True)])

    # ---- forget_own

    def test_forget_own_drops_only_that_snapshot(self):
        d1, d2 = mt.snapshot_dir('a' * 64), mt.snapshot_dir('b' * 64)
        for key in ((d1, 'a'), (d1, 'b'), (d2, 'a')):
            dm._OWN_CACHE[key] = (None, None)
            dm._OWN_LOCKS[key] = threading.Lock()
        dm.forget_own('a' * 64)
        self.assertEqual(list(dm._OWN_CACHE), [(d2, 'a')])
        self.assertEqual(list(dm._OWN_LOCKS), [(d2, 'a')])
        dm.forget_own('c' * 64)                                    # нічого не кешовано — не помилка
        self.assertEqual(list(dm._OWN_CACHE), [(d2, 'a')])

    def test_forget_own_waits_for_the_load_lock(self):
        # Детерміновано: лок тримаємо ми (RLock — з іншого потоку він не реентерабельний), писар мусить чекати
        key = (mt.snapshot_dir('a' * 64), 'a')
        dm._OWN_CACHE[key] = (None, None)
        th = threading.Thread(target=dm.forget_own, args=('a' * 64,), daemon=True)
        dm._LOAD_LOCK.acquire()
        try:
            th.start()
            th.join(0.3)
            waiting = th.is_alive()
            still_there = key in dm._OWN_CACHE
        finally:
            dm._LOAD_LOCK.release()
        th.join(5)
        self.assertTrue(waiting, 'forget_own не чекав `_LOAD_LOCK`')
        self.assertTrue(still_there)
        self.assertFalse(th.is_alive())
        self.assertNotIn(key, dm._OWN_CACHE)

    def test_forget_own_makes_the_next_catalog_load_the_snapshot_again(self):
        self.own()
        h = self.trust()
        dm.catalog(self.sp)
        dm.catalog(self.sp)
        self.assertEqual(len(self.ran()), 1)
        dm.forget_own(h)
        self.assertEqual(dm.catalog(self.sp)['acme'].status, 'ok')
        self.assertEqual(len(self.ran()), 2)

    def test_a_sleeping_module_does_not_block_other_catalogs(self):
        sp2 = self.rec(spaces.create_space('Beta', 'space-2', self.hp('work', 'beta')))
        self.mk('pub')
        self.own(server=SLEEPY)
        self.trust()
        self.own(sp=sp2, server=OWN_SERVER.replace('"v1"', '"v2"'))     # інші байти — інший знімок і інший лок
        self.trust(sp=sp2)
        with mock.patch.object(dm, 'LOAD_TIMEOUT', 30):
            box = []
            th = threading.Thread(target=lambda: box.append(dm.catalog(self.sp)['acme']), daemon=True)
            th.start()
            for _ in range(100):                                       # мітка пишеться ДО очікування: модуль уже всередині
                if self.ran():
                    break
                time.sleep(0.05)
            self.assertEqual(len(self.ran()), 1)
            t0 = time.monotonic()
            self.assertEqual(sorted(dm.catalog()), ['pub'])
            self.assertEqual(dm.catalog(sp2)['acme'].status, 'ok')
            self.assertLess(time.monotonic() - t0, 2, 'каталог чекав на сплячий модуль іншого простору')
            builtins._DEAI_GATE.set()
            th.join(5)
            self.assertFalse(th.is_alive())
            self.assertEqual(box[0].status, 'ok')

    def test_concurrent_catalogs_build_a_snapshot_once(self):
        self.own(server='import time\ntime.sleep(0.3)\n' + OWN_SERVER)       # довго будується: гонка справжня
        self.trust()
        out = race(6, lambda i: dm.catalog(self.sp)['acme'].status)
        self.assertEqual([r[0] for r in out], ['ok'] * 6, out)
        self.assertEqual([r[1] for r in out], ['ok'] * 6)
        self.assertEqual(len(self.ran()), 1, 'лок на теку знімка: будується один раз')

    def test_the_snapshot_loads_in_the_request_space(self):
        self.own(server=OWN_SERVER + 'import builtins\nbuiltins._DEAI_SEEN = __import__("spaces").request_space_id()\n')
        self.trust()
        spaces.set_request_space('some-space')
        dm.catalog(self.sp)
        self.assertEqual(builtins._DEAI_SEEN, 'some-space')

    def test_own_cache_is_bounded_and_evicts_what_is_not_used(self):
        for mid in ('a1', 'b1', 'c1'):
            self.own(mid)
        snap = {mid: mt.snapshot_dir(self.trust(mid)) for mid in ('a1', 'b1', 'c1')}
        a, b, c = snap['a1'], snap['b1'], snap['c1']
        with mock.patch.object(dm, 'OWN_CACHE_MAX', 2):
            dm._load_own(a, 'a1')
            dm._load_own(b, 'b1')
            dm._load_own(a, 'a1')                              # хіт: `a` стає найновішим
            dm._load_own(c, 'c1')                              # місця нема: витісняється `b`, а не `a`
            self.assertEqual(list(dm._OWN_CACHE), [(a, 'a1'), (c, 'c1')])
            self.assertEqual(sorted(dm._OWN_LOCKS), sorted([(a, 'a1'), (c, 'c1')]), 'лок витісненого знімка не лишається')
            with mock.patch.object(mt, 'fingerprint', return_value=('змінився',)):
                dm._load_own(a, 'a1')                          # відбиток інший — перебудова; запис стає найновішим
            self.assertEqual(list(dm._OWN_CACHE), [(c, 'c1'), (a, 'a1')])

    def test_reset_caches_drops_the_own_caches_and_the_scan_cache(self):
        self.own()
        self.trust()
        dm.catalog(self.sp)
        self.assertTrue(dm._OWN_CACHE and dm._OWN_LOCKS and mt._CACHE)
        dm.reset_caches()
        self.assertEqual((len(dm._OWN_CACHE), len(dm._OWN_LOCKS), len(mt._CACHE)), (0, 0, 0))

    def test_forget_check_drops_that_modules_check_and_the_capabilities_cache(self):
        self.own()
        self.trust()
        sid = self.sp['id']
        dm.check(self.sp, 'acme')
        dm._remember(self.sp, 'other', {'ok': True})
        dm.capabilities(self.sp)
        self.assertIsNotNone(dm.last_check(sid, 'acme'))
        self.assertIn(sid, dm._CAPS)
        dm.forget_check(sid, 'acme')
        self.assertIsNone(dm.last_check(sid, 'acme'))
        self.assertNotIn(sid, dm._CAPS)
        self.assertEqual(dm.last_check(sid, 'other'), {'ok': True}, 'чужий модуль не чіпаємо')
