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
import shutil
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
from test_modules import Env, _write, _read, _bytes, ALL_FNS, race, VCS_SERVER, VCS_OPTIONAL  # noqa: E402

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

    def publish_record(self, sp=None):
        """Явний запис `static-publish` у `space.json` (4d-4c: неявного типового нема; `new_space` його знімає)."""
        p = self.space_json(sp or self.sp)
        data = _read(p)
        data.setdefault('modules', {})['static-publish'] = {'enabled': True}
        _write(p, data)

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


# ================================================================================ Task 4: ролі «на папері» і довіра в ядрі

class OwnVcsRoleTest(OwnEnv):
    """Свій ДОВІРЕНИЙ модуль ролі `vcs` (4a) вантажиться зі знімка тим самим `_build` і віддається `_clone`-ом: необовʼязкові
    `validate`/`mirror_dir` досяжні через `fn()`/`call()`, а без них модуль валідний і `fn()` дає `None`."""
    SETTINGS = [{'key': 'repo', 'type': 'text', 'label': 'Repo'}]

    def test_a_trusted_own_vcs_module_gets_its_optional_functions(self):
        self.own('gitx', roles=('vcs',), server=VCS_SERVER + VCS_OPTIONAL, settings=self.SETTINGS)
        h = self.trust('gitx')
        m = dm.catalog(self.sp)['gitx']
        self.assertEqual((m.origin, m.trust, m.status, m.roles), ('space', 'trusted', 'ok', ['vcs']))
        self.assertEqual(m.dir, mt.snapshot_dir(h))
        for name in ('check', 'status', 'push', 'pull', 'validate', 'mirror_dir'):
            self.assertTrue(callable(m.fn(name)), name)
        ctx = dm.module_ctx(self.sp, m)
        self.assertEqual(dm.call(m, 'validate', ctx, {'repo': 'r'}), {'repo': 'r', 'checked': True})
        self.assertEqual(dm.call(m, 'mirror_dir', ctx, {'repo': 'r'}), '/m/r')
        dm.write_module_state(self.sp, 'gitx', enabled=True)
        self.assertEqual(dm.capabilities(self.sp)['vcs'], 'gitx')
        self.assertIs(dm.provider('vcs', self.sp).fn('validate'), dm.catalog(self.sp)['gitx'].fn('validate'))

    def test_a_trusted_own_vcs_module_without_the_optional_functions_is_valid(self):
        self.own('gitz', roles=('vcs',), server=VCS_SERVER, settings=self.SETTINGS)
        self.trust('gitz')
        m = dm.catalog(self.sp)['gitz']
        self.assertEqual((m.trust, m.status, m.error), ('trusted', 'ok', None))
        for name in ('check', 'status', 'push', 'pull'):
            self.assertTrue(callable(m.fn(name)), name)
        self.assertIsNone(m.fn('validate'))
        self.assertIsNone(m.fn('mirror_dir'))


class RolesTest(OwnEnv):
    def test_space_json_roles_survive_normalize(self):
        self.enable_raw()
        self.assertEqual(dm.space_modules(self.sp)['acme']['roles'], ['publish'])

    def test_normalize_keeps_only_well_formed_roles(self):
        p = self.space_json(self.sp)
        data = _read(p)
        data['modules'] = {
            'dup': {'enabled': True, 'roles': ['publish', 'publish', 'tokens']},
            'reserved': {'enabled': True, 'roles': ['vcs']},
            'empty': {'enabled': True, 'roles': []},
            'unknown': {'enabled': True, 'roles': ['publish', 'nope']},
            'notlist': {'enabled': True, 'roles': 'publish'},
            'notstr': {'enabled': True, 'roles': ['publish', 5]},
            'plain': {'enabled': True}}
        _write(p, data)
        got = dm.space_modules(self.sp)
        self.assertEqual(got['dup']['roles'], ['publish', 'tokens'])
        self.assertEqual(got['reserved']['roles'], ['vcs'])
        for mid in ('empty', 'unknown', 'notlist', 'notstr', 'plain'):
            self.assertNotIn('roles', got[mid], mid)
            self.assertTrue(got[mid]['enabled'], mid)

    def test_untrusted_enabled_own_module_holds_its_role_on_paper(self):
        self.mk('pub')
        self.own()
        self.enable_raw()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(self.sp, 'pub', enabled=True)
        self.assertEqual(cm.exception.code, 'role-taken')
        st = dm.write_module_state(self.sp, 'pub', enabled=True, replace=True)
        self.assertEqual(st['replaced'], ['acme'])
        self.assertFalse(dm.space_modules(self.sp)['acme']['enabled'])

    def test_a_disabled_own_module_holds_nothing(self):
        self.mk('pub')
        self.own()
        self.enable_raw()
        dm.write_module_state(self.sp, 'acme', enabled=False)
        dm.write_module_state(self.sp, 'pub', enabled=True)           # роль вільна: без `role-taken`
        self.assertEqual(dm.provider('publish', self.sp).id, 'pub')

    def test_missing_or_broken_own_module_still_holds_its_role(self):
        self.mk('pub')
        self.enable_raw('ghost', ('publish',))                 # тека не приїхала з git — ролі лише в записі
        with self.assertRaises(dm.ModuleError) as cm:
            dm.write_module_state(self.sp, 'pub', enabled=True)
        self.assertEqual((cm.exception.code, cm.exception.message), ('role-taken', 'publish is already provided by ghost'))
        _write(os.path.join(self.sp['path'], 'modules', 'acme', 'module.json'), '{oops')   # маніфест не розбирається
        self.enable_raw('acme', ('publish',))
        st = dm.write_module_state(self.sp, 'pub', enabled=True, replace=True)
        self.assertEqual(st['replaced'], ['acme', 'ghost'])
        mods = dm.space_modules(self.sp)
        self.assertEqual((mods['acme']['enabled'], mods['ghost']['enabled'], mods['pub']['enabled']), (False, False, True))

    def test_a_disabled_record_of_a_missing_folder_holds_nothing(self):
        self.mk('pub')
        p = self.space_json(self.sp)
        data = _read(p)
        data['modules'] = {'ghost': {'enabled': False, 'settings': {}, 'roles': ['publish']}}
        _write(p, data)
        st = dm.write_module_state(self.sp, 'pub', enabled=True, replace=True)
        self.assertEqual(st['replaced'], [])
        dm.write_module_state(self.sp, 'pub', enabled=False)
        dm.write_module_state(self.sp, 'pub', enabled=True)           # без `replace`: вимкнений запис ролі не тримає

    def test_a_stale_builtin_entry_without_roles_holds_nothing(self):
        self.mk('pub')
        p = self.space_json(self.sp)
        data = _read(p)
        data['modules'] = {'old-builtin': {'enabled': True, 'settings': {}}}
        _write(p, data)
        dm.write_module_state(self.sp, 'pub', enabled=True)           # без `replace`: чужий пил роль не тримає

    def test_the_roles_of_a_builtin_come_only_from_its_manifest(self):
        self.mk('pub')
        self.mk('ds', roles=('tokens',))
        p = self.space_json(self.sp)
        data = _read(p)
        data['modules'] = {'pub': {'enabled': True, 'settings': {}, 'roles': ['tokens']}}      # дописано вручну
        _write(p, data)
        dm.write_module_state(self.sp, 'ds', enabled=True)           # `pub` роль `tokens` не веде: запис не в рахунок
        dm.write_module_state(self.sp, 'ds', enabled=False)
        self.mk('bare', roles=())                                    # вбудований без ролей: порожній маніфест — не «ролі з запису»
        data = _read(p)
        data['modules']['bare'] = {'enabled': True, 'settings': {}, 'roles': ['tokens']}
        _write(p, data)
        dm.write_module_state(self.sp, 'ds', enabled=True)

    def test_a_builtin_that_did_not_load_still_holds_nothing(self):
        self.mk('broken', server='def check(:\n')
        self.mk('pub')
        dm.write_module_state(self.sp, 'broken', enabled=True)
        self.assertEqual(dm.catalog(self.sp)['broken'].status, 'error')
        dm.write_module_state(self.sp, 'pub', enabled=True)           # зламаний ВБУДОВАНИЙ ролі не тримає, як і було

    def test_provider_raises_for_untrusted_own_without_falling_back(self):
        self.mk('static-publish')                              # неявний типовий у просторі без інтеграцій
        self.own()
        self.enable_raw()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')
        self.assertEqual(cm.exception.message, 'acme: module is not trusted on this computer')
        caps = dm.capabilities(self.sp)
        self.assertEqual((caps['publish'], caps.get('error')), (None, None), 'стан ролі, а не «space.json не читається»')

    def test_integrations_space_no_legacy_for_untrusted_publish_or_comments(self):
        sp = self.new_space('Liga', integrations=True)
        self.own('acme', roles=('publish',), sp=sp)
        self.own('talk', roles=('comments',), sp=sp, extra={'client': ['a.js']})
        _write(os.path.join(sp['path'], 'modules', 'talk', 'a.js'), '//')
        self.enable_raw('acme', ('publish',), sp=sp)
        self.enable_raw('talk', ('comments',), sp=sp)
        for role in ('publish', 'comments'):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.provider(role, sp)
            self.assertEqual(cm.exception.code, 'module-untrusted', role)
        caps = dm.capabilities(sp)
        self.assertEqual((caps['publish'], caps['comments']), (None, None))
        self.assertNotIn('error', caps)

    def test_missing_own_comments_module_is_an_error_not_legacy(self):
        sp = self.new_space('Liga', integrations=True)
        self.enable_raw('talk', ('comments',), sp=sp)          # тека не приїхала з git
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('comments', sp)
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertEqual(dm.capabilities(sp)['comments'], None)
        self.assertNotIn('error', dm.capabilities(sp))

    def test_a_missing_own_module_of_another_role_does_not_touch_the_comments_path(self):
        sp = self.new_space('Liga', integrations=True)
        self.enable_raw('acme', ('publish',), sp=sp)           # тека не приїхала; роль `publish`, не `comments`
        self.assertIsNone(dm.provider('comments', sp))          # було `implicit.for_role('comments')`: запасного постачальника нема (4d-4b)

    def test_an_implicit_space_never_reads_the_catalog(self):
        """Замість «простір з інтеграціями без явних модулів не читає каталог» (4d-4b: шляху ЛІГА без запису нема — простір з інтеграціями
        вирішується як будь-який). Незмінним лишився інший бік: НЕЯВНИЙ простір (запит не закріплено) — ролей нема й без каталогу."""
        sp = self.new_space('Liga', integrations=True)
        self.own('acme', sp=sp)
        spaces.clear_request_space()
        with mock.patch.object(dm, 'catalog', side_effect=AssertionError('каталог для неявного простору')), \
                mock.patch.object(dm, 'space_modules', side_effect=AssertionError('space.json для неявного простору')):
            self.assertIsNone(dm.provider('publish'))
            self.assertIsNone(dm.provider('comments'))

    def test_capabilities_builds_the_catalog_once_and_only_when_needed(self):
        self.mk('static-publish')
        calls = []
        real = dm.catalog

        def spy(space=None):
            calls.append(space)
            return real(space)
        with mock.patch.object(dm, 'catalog', spy):
            dm.capabilities(self.sp)
            self.assertEqual(len(calls), 1, 'три ролі — один каталог')
            self.assertIs(calls[0], self.sp, 'каталог простору, а не лише вбудовані')
            calls.clear()
            ig = self.new_space('Liga', integrations=True)
            dm.capabilities(ig)
            self.assertEqual(len(calls), 1, 'простір з інтеграціями — як будь-який: один каталог (було — без каталогу, шлях ЛІГА, 4d-4b)')

    def test_tokens_role_errors_too(self):
        self.own('ds', roles=('tokens',))
        self.enable_raw('ds', ('tokens',))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('tokens', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')

    def test_paper_error_is_per_role_of_the_own_module(self):
        self.mk('static-publish')
        self.publish_record()
        self.own('ds', roles=('tokens',))
        self.enable_raw('ds', ('tokens',))
        self.assertEqual(dm.provider('publish', self.sp).id, 'static-publish', 'роль `publish` модуль `ds` не веде')
        with self.assertRaises(dm.ModuleError):
            dm.provider('tokens', self.sp)
        caps = dm.capabilities(self.sp)
        self.assertEqual((caps['publish'], caps['tokens'], caps.get('error')), ('static-publish', None, None))

    def test_a_disabled_untrusted_own_module_is_no_paper_provider(self):
        self.mk('static-publish')
        self.publish_record()
        self.own()
        self.assertEqual(dm.provider('publish', self.sp).id, 'static-publish')
        p = self.space_json(self.sp)
        data = _read(p)
        data['modules'] = {'static-publish': {'enabled': True}, 'acme': {'enabled': False, 'settings': {}, 'roles': ['publish']}}
        _write(p, data)
        self.assertEqual(dm.provider('publish', self.sp).id, 'static-publish')

    def test_a_broken_builtin_is_no_paper_provider(self):
        self.mk('static-publish')
        self.mk('broken', server='def check(:\n')
        sj = self.space_json(self.sp)
        data = _read(sj)
        data['modules'] = {'static-publish': {'enabled': True}, 'broken': {'enabled': True, 'settings': {}}}   # напряму: `role-taken` з явним записом
        _write(sj, data)
        self.assertEqual(dm.catalog(self.sp)['broken'].status, 'error')
        self.assertEqual(dm.provider('publish', self.sp).id, 'static-publish')     # як і було: зламаний вбудований не веде роль

    def test_a_trusted_own_module_that_fails_to_load_is_a_module_error_on_paper(self):
        self.mk('static-publish')
        self.own(server='raise RuntimeError("boom")\n')
        self.trust()
        self.enable_raw()
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-error')
        self.assertIn('boom', cm.exception.message)
        self.assertTrue(cm.exception.message.startswith('acme: '))
        caps = dm.capabilities(self.sp)
        self.assertEqual((caps['publish'], caps.get('error')), (None, None))

    def test_a_working_trusted_own_module_provides_the_role(self):
        self.mk('static-publish')
        self.own()
        self.trust()
        self.enable_raw()
        self.assertEqual(dm.provider('publish', self.sp).id, 'acme')
        self.assertEqual(dm.capabilities(self.sp)['publish'], 'acme')

    def test_a_broken_manifest_enabled_with_roles_is_a_paper_error_and_leaves_comments_alone(self):
        self.mk('static-publish')
        _write(os.path.join(self.sp['path'], 'modules', 'acme', 'module.json'), '{oops')
        self.enable_raw('acme', ('publish',))
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')
        self.assertIn('bad-manifest', cm.exception.message)
        caps = dm.capabilities(self.sp)
        self.assertEqual((caps['publish'], caps['comments'], caps.get('error')), (None, None, None),
                         'модуль веде лише `publish`: коментарі й простір не страждають')

    def test_roles_recorded_for_a_broken_builtin_do_not_clear_it_of_leading_comments(self):
        sp = self.new_space('Liga', integrations=True)
        self.mk('weird', patch={'api': 99})                      # маніфест не проходить: ролі невідомі
        p = self.space_json(sp)
        data = _read(p)
        data['modules'] = {'weird': {'enabled': True, 'settings': {}, 'roles': ['publish']}}   # ролі із запису — лише для СВОЇХ
        _write(p, data)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('comments', sp)
        self.assertEqual((cm.exception.code, cm.exception.message), ('module-error', dm.COMMENTS_MODULE_BROKEN))

    def test_a_broken_own_manifest_without_recorded_roles_may_have_led_comments(self):
        # Ролей не знаємо ні з маніфесту, ні із запису (запис без `roles` — вручну): консервативно, як і для вбудованих
        sp = self.new_space('Liga', integrations=True)
        _write(os.path.join(sp['path'], 'modules', 'acme', 'module.json'), '{oops')
        p = self.space_json(sp)
        data = _read(p)
        data['modules'] = {'acme': {'enabled': True, 'settings': {}}}
        _write(p, data)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('comments', sp)
        self.assertEqual((cm.exception.code, cm.exception.message), ('module-error', dm.COMMENTS_MODULE_BROKEN))
        self.assertFalse(getattr(cm.exception, 'paper', False), 'це не роль «на папері»: ролей нема')

    def test_caps_key_sees_trust_and_folder_changes(self):
        self.own()
        self.enable_raw()
        self.assertIsNone(dm.capabilities(self.sp)['publish'])
        self.trust()
        self.assertEqual(dm.capabilities(self.sp)['publish'], 'acme')

    def test_caps_key_sees_a_changed_module_folder(self):
        self.mk('static-publish')
        self.publish_record()
        d = self.own()
        self.enable_raw()
        self.assertIsNone(dm.capabilities(self.sp)['publish'])
        man = _read(os.path.join(d, 'module.json'))
        man['roles'] = ['tokens']                               # тека більше не веде `publish`
        _write(os.path.join(d, 'module.json'), man)
        self.assertEqual(dm.capabilities(self.sp)['publish'], 'static-publish', 'ключ кешу не побачив зміну теки')

    def test_a_dropped_role_is_free_even_though_space_json_still_records_it(self):
        # Запис `roles` у `space.json` пише вмикання; нова довірена версія теки роль прибрала — запис застарів. Ролі запису
        # додаються лише тоді, коли маніфест ролей не дав (зламаний), інакше застарілий запис тримав би чужу роль
        self.mk('ds', roles=('tokens',))
        d = self.own('acme', roles=('publish', 'tokens'))
        self.trust()
        dm.write_module_state(self.sp, 'acme', enabled=True)
        self.assertEqual(dm.space_modules(self.sp)['acme']['roles'], ['publish', 'tokens'])
        man = _read(os.path.join(d, 'module.json'))
        man['roles'] = ['publish']
        _write(os.path.join(d, 'module.json'), man)
        os.environ[mt.SEAM_ENV] = 'yes'
        dm.grant_trust(self.sp, 'acme', dm.trust_view(self.sp, 'acme')['hash'], 'uk')
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.roles), ('ok', 'trusted', ['publish']))
        st = dm.write_module_state(self.sp, 'ds', enabled=True, replace=True)
        self.assertEqual(st['replaced'], [], 'робочий `acme` не вимкнено: `tokens` він уже не веде')
        self.assertTrue(dm.space_modules(self.sp)['acme']['enabled'])
        dm.revoke_trust(self.sp, 'acme')                        # недовірений: роль «на папері» — лише `publish`, а не й `tokens`
        self.assertEqual(dm.provider('tokens', self.sp).id, 'ds')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')

    def test_caps_cache_sees_a_damaged_snapshot(self):
        self.own()
        h = self.trust()
        self.enable_raw()
        self.assertEqual(dm.capabilities(self.sp)['publish'], 'acme')
        snap = mt.snapshot_dir(h)
        os.chmod(snap, 0o700)
        os.chmod(os.path.join(snap, 'server.py'), 0o600)
        with open(os.path.join(snap, 'server.py'), 'a') as f:
            f.write('\n# tampered\n')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')
        caps = dm.capabilities(self.sp)
        self.assertEqual((caps['publish'], caps.get('error')), (None, None), 'кеш `capabilities` не побачив пошкодження знімка')

    def test_caps_with_an_unreadable_trust_file_is_a_role_state_not_a_space_error(self):
        self.own()
        self.trust()
        self.enable_raw()
        self.assertEqual(dm.capabilities(self.sp)['publish'], 'acme')
        _write(mt.trust_file(), '{oops')                        # довіру не прочитати: модуль недовірений, але простір цілий
        caps = dm.capabilities(self.sp)
        self.assertEqual((caps['publish'], caps.get('error')), (None, None))
        self.assertIsNotNone(dm.own_sig(self.sp))

    def test_own_sig_follows_the_snapshot_of_a_trusted_module_of_this_space_only(self):
        self.own()
        h = self.trust()
        sp2 = self.rec(spaces.create_space('Beta', 'space-2', self.hp('work', 'beta')))
        self.own(sp=sp2, server=OWN_SERVER.replace('"v1"', '"v2"'))
        h2 = self.trust(sp=sp2)
        a, b = dm.own_sig(self.sp), dm.own_sig(sp2)
        snap2 = mt.snapshot_dir(h2)
        os.chmod(snap2, 0o700)
        os.chmod(os.path.join(snap2, 'server.py'), 0o600)
        with open(os.path.join(snap2, 'server.py'), 'a') as f:
            f.write('\n# tampered\n')
        self.assertEqual(dm.own_sig(self.sp), a, 'знімок чужого простору в відбиток цього не входить')
        self.assertNotEqual(dm.own_sig(sp2), b)
        self.assertNotEqual(h, h2)

    def test_own_sig_is_none_without_a_space_folder_and_tracks_the_folders(self):
        self.assertIsNone(dm.own_sig({'id': 'x', 'path': ''}))
        self.assertIsNone(dm.own_sig(None))
        base = dm.own_sig(self.sp)
        d = self.own()
        a = dm.own_sig(self.sp)
        self.assertNotEqual(base, a)
        self.assertEqual(dm.own_sig(self.sp), a, 'нічого не змінилось — відбиток той самий')
        self.trust()
        self.assertNotEqual(dm.own_sig(self.sp), a, 'довіра — теж зміна')
        self.assertTrue(dm.own_sig(self.sp)[0][0][0] == 'acme' and d)


class TrustCoreTest(OwnEnv):
    def setUp(self):
        super().setUp()
        os.environ[mt.SEAM_ENV] = 'yes'
        self.d = self.own()

    def view(self, mid='acme'):
        return dm.trust_view(self.sp, mid)

    def test_view_shape_and_no_execution(self):
        v = self.view()
        self.assertEqual((v['id'], v['state'], v['record'], v['roles']), ('acme', 'untrusted', False, ['publish']))
        self.assertRegex(v['hash'], r'^[0-9a-f]{64}$')
        self.assertEqual({f['change'] for f in v['files']}, {'new'})
        self.assertEqual(v['settings'], [{'key': 'token', 'type': 'secret', 'label': 'Token', 'public': False}])
        self.assertEqual(v['path'], os.path.join('~', 'work', 'alpha', 'modules', 'acme'))
        self.assertEqual(self.ran(), [])
        with self.assertRaises(dm.ModuleError) as cm:
            dm.trust_view(self.sp, 'nope')
        self.assertEqual(cm.exception.code, 'unknown-module')

    def test_view_of_a_non_own_or_malformed_id_is_unknown_module(self):
        self.mk('pub')
        for bad in ('pub', '../acme', 'ACME', '', None, 5, ['acme'], {}):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.trust_view(self.sp, bad)
            self.assertEqual(cm.exception.code, 'unknown-module', repr(bad))
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, bad, 'a' * 64, 'uk')
            self.assertEqual(cm.exception.code, 'unknown-module', repr(bad))
            if bad == 'pub':
                continue                                        # «Забрати довіру» не вимагає теки: коректний id без запису — `False`
            with self.assertRaises(dm.ModuleError) as cm:
                dm.revoke_trust(self.sp, bad)
            self.assertEqual(cm.exception.code, 'unknown-module', repr(bad))
        self.assertFalse(dm.revoke_trust(self.sp, 'pub'))
        self.assertFalse(dm.revoke_trust(self.sp, 'ghost'))

    def test_view_numbers_and_total(self):
        v = self.view()
        self.assertEqual(v['total'], {'files': 2, 'bytes': sum(os.path.getsize(os.path.join(self.d, f))
                                                                for f in ('module.json', 'server.py'))})
        self.assertEqual((v['removed'], v['name'], v['version']), ([], 'Acme', '1.0.0'))

    def test_view_of_a_refused_folder_and_a_bad_manifest(self):
        _write(os.path.join(self.d, 'CON'), 'x')
        v = self.view()
        self.assertEqual((v['state'], v['refused']['code']), ('refused', 'bad-name'))
        self.assertEqual((v['name'], v['version'], v['roles'], v['record']), ('acme', '', [], False),
                         'теку не просканувати — маніфесту ще не бачили')
        self.assertNotIn('hash', v)
        os.remove(os.path.join(self.d, 'CON'))
        _write(os.path.join(self.d, 'module.json'), '{oops')
        v = self.view()
        self.assertEqual((v['state'], v['refused']['code']), ('refused', 'bad-manifest'))
        self.assertEqual((v['name'], v['version'], v['roles'], v['settings']), ('acme', '', [], []))
        self.assertIn('module.json', v['refused']['detail'])
        self.assertEqual(self.ran(), [])

    def test_view_of_a_refused_new_version_still_names_the_working_snapshot(self):
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        _write(os.path.join(self.d, 'CON'), 'x')
        v = self.view()
        self.assertEqual((v['state'], v['record'], v['refused']['code']), ('refused', True, 'bad-name'))
        self.assertEqual((v['name'], v['version'], v['roles']), ('Acme', '1.0.0', ['publish']))
        self.assertNotIn('hash', v)
        self.assertNotIn('files', v)

    def test_grant_runs_the_snapshot_and_clears_the_last_check(self):
        dm.write_secrets(self.sp['id'], 'acme', {'token': 's'}, space=self.sp)
        dm._remember(self.sp, 'acme', {'ok': False, 'error': 'old'})
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertIsNone(dm.last_check(self.sp['id'], 'acme'))
        self.assertEqual(dm.catalog(self.sp)['acme'].trust, 'trusted')
        self.assertEqual(self.view()['state'], 'trusted')
        self.assertEqual({f['change'] for f in self.view()['files']}, {'same'})

    def test_grant_writes_the_record_of_the_shown_version(self):
        v = self.view()
        dm.grant_trust(self.sp, 'acme', v['hash'], 'uk')
        rec = mt.load_records()[mt.key_for(self.sp['path'], 'acme')]
        self.assertEqual((rec['id'], rec['name'], rec['version'], rec['roles'], rec['hash']),
                         ('acme', 'Acme', '1.0.0', ['publish'], v['hash']))
        self.assertEqual([(f['path'], f['size']) for f in rec['files']], [(f['path'], f['size']) for f in v['files']])
        self.assertRegex(rec['trusted_at'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')
        self.assertTrue(mt.verify_snapshot(v['hash']))
        self.assertEqual(self.ran(), [], 'довіра сама код не виконує — лише `catalog` після неї')

    def test_changed_view_and_regrant(self):
        h0 = self.view()['hash']
        dm.grant_trust(self.sp, 'acme', h0, 'uk')
        _write(os.path.join(self.d, 'server.py'), OWN_SERVER.replace('"v1"', '"v2"'))
        _write(os.path.join(self.d, 'new.js'), '//')
        v = self.view()
        self.assertEqual(v['state'], 'changed')
        self.assertEqual({f['path']: f['change'] for f in v['files']},
                         {'module.json': 'same', 'server.py': 'changed', 'new.js': 'new'})
        dm.grant_trust(self.sp, 'acme', v['hash'], 'uk')
        self.assertEqual(dm.check(self.sp, 'acme')['detail'], 'own v2')

    def test_view_shows_the_manifest_of_the_folder_not_of_the_snapshot(self):
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        man = _read(os.path.join(self.d, 'module.json'))
        man.update(name='Acme Two', version='2.0.0', roles=['publish', 'tokens'],
                   settings=[{'key': 'site', 'type': 'text', 'label': 'Site'}])
        _write(os.path.join(self.d, 'module.json'), man)
        v = self.view()
        self.assertEqual((v['state'], v['name'], v['version'], v['roles']),
                         ('changed', 'Acme Two', '2.0.0', ['publish', 'tokens']))
        self.assertEqual([s['key'] for s in v['settings']], ['site'])
        self.assertEqual(dm.catalog(self.sp)['acme'].roles, ['publish'], 'а працює й далі знімок')

    def test_view_lists_files_removed_since_the_trust(self):
        _write(os.path.join(self.d, 'extra.txt'), 'abc')
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        os.remove(os.path.join(self.d, 'extra.txt'))
        v = self.view()
        self.assertEqual((v['state'], v['removed']), ('changed', [{'path': 'extra.txt', 'size': 3}]))

    def test_grant_refusals(self):
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', '0' * 64, 'uk')
        self.assertEqual(cm.exception.code, 'module-changed')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', 'short', 'uk')
        self.assertEqual(cm.exception.code, 'bad-settings')
        _write(os.path.join(self.d, 'CON'), 'x')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', '0' * 64, 'uk')
        self.assertEqual(cm.exception.code, 'module-refused')
        self.assertEqual(self.ran(), [])

    def test_grant_refuses_a_bad_manifest_and_a_non_string_hash(self):
        h = self.view()['hash']
        for bad in (None, 5, ['a' * 64], 'A' * 64):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', bad, 'uk')
            self.assertEqual(cm.exception.code, 'bad-settings', repr(bad))
        _write(os.path.join(self.d, 'module.json'), '{oops')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', h, 'uk')
        self.assertEqual(cm.exception.code, 'module-refused')
        self.assertIn('bad-manifest', cm.exception.message)
        self.assertEqual(mt.load_records(), {})

    def test_grant_maps_the_system_window(self):
        h = self.view()['hash']
        for answer, code in (('no', 'trust-declined'), ('declined', 'trust-declined'),
                             ('unavailable', 'trust-no-confirm'), ('busy', 'trust-busy')):
            with mock.patch.object(mt, 'ask', return_value=answer):
                with self.assertRaises(dm.ModuleError) as cm:
                    dm.grant_trust(self.sp, 'acme', h, 'uk')
            self.assertEqual(cm.exception.code, code, answer)
        self.assertEqual(mt.load_records(), {})
        self.assertFalse(os.path.lexists(mt.snapshot_dir(h)), 'знімок пишеться лише після «так»: відмова не лишає сиріт')

    def test_grant_passes_language_and_cleaned_texts(self):
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='yes') as ask:
            dm.grant_trust(self.sp, 'acme', h, 'en')
        key, got_hash, texts = ask.call_args[0]
        self.assertEqual((key, got_hash), (mt.key_for(self.sp['path'], 'acme'), h))
        title, msg, yes, no = texts
        self.assertEqual((yes, no), ('Trust', 'Cancel'))
        self.assertIn('acme', msg)
        self.assertIn(h[:12], msg)

    def test_grant_refuses_a_second_provider(self):
        self.mk('pub')
        dm.write_module_state(self.sp, 'pub', enabled=True)
        self.enable_raw()                                       # колега закомітив і свій модуль
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertEqual(cm.exception.code, 'role-taken')
        self.assertEqual(cm.exception.message, 'publish is already provided by pub')
        self.assertEqual(mt.load_records(), {})

    def test_grant_does_not_check_roles_of_a_module_that_is_not_enabled(self):
        self.mk('pub')
        dm.write_module_state(self.sp, 'pub', enabled=True)
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')                 # `acme` не ввімкнений: роль не його
        self.assertEqual(dm.catalog(self.sp)['acme'].trust, 'trusted')

    def test_grant_checks_the_roles_of_the_new_version_of_the_folder(self):
        self.mk('ds', roles=('tokens',))
        dm.write_module_state(self.sp, 'ds', enabled=True)
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        dm.write_module_state(self.sp, 'acme', enabled=True)
        man = _read(os.path.join(self.d, 'module.json'))
        man['roles'] = ['publish', 'tokens']                    # нова версія теки бере ще й роль, яку тримає `ds`
        _write(os.path.join(self.d, 'module.json'), man)
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertEqual((cm.exception.code, cm.exception.message), ('role-taken', 'tokens is already provided by ds'))

    def test_grant_needs_the_spaces_layer(self):
        h = self.view()['hash']
        with mock.patch.dict(os.environ):
            os.environ.pop('DEAI_HOME')
            for call in (lambda: dm.grant_trust(self.sp, 'acme', h, 'uk'), lambda: dm.revoke_trust(self.sp, 'acme')):
                with self.assertRaises(dm.ModuleError) as cm:
                    call()
                self.assertEqual(cm.exception.code, 'spaces-off')

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_link_alias_has_no_trust_of_its_own_and_revoke_leaves_the_target(self):
        d = self.own()
        self.trust()
        os.symlink(d, os.path.join(self.sp['path'], 'modules', 'aaa'))
        v = dm.trust_view(self.sp, 'aaa')
        self.assertEqual((v['state'], v['record'], v['refused']['code']), ('refused', False, 'symlink'))
        self.assertFalse(dm.revoke_trust(self.sp, 'aaa'))
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.trust, m.record), ('trusted', True), 'довіру acme не знято через аліас')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.grant_trust(self.sp, 'aaa', 'a' * 64, 'uk')
        self.assertEqual(cm.exception.code, 'module-refused')

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_modules_folder_that_links_to_another_space_has_no_trust_to_revoke(self):
        # `key_for` бере `realpath`, а `lstat(modules/acme)` проміжного посилання не бачить: без окремої перевірки `modules`
        # «Забрати довіру» у просторі Beta зняла б довіру простору Alpha
        h = self.trust()
        sp2 = self.rec(spaces.create_space('Beta', 'space-2', self.hp('work', 'beta')))
        os.symlink(os.path.join(self.sp['path'], 'modules'), os.path.join(sp2['path'], 'modules'))
        self.assertFalse(dm.revoke_trust(sp2, 'acme'))
        self.assertEqual(sorted(r['id'] for r in mt.load_records().values()), ['acme'], 'запис Alpha цілий')
        m = dm.catalog(self.sp)['acme']
        self.assertEqual((m.status, m.trust, m.record), ('ok', 'trusted', True))
        self.assertTrue(mt.verify_snapshot(h))
        for call in (lambda: dm.trust_view(sp2, 'acme'), lambda: dm.grant_trust(sp2, 'acme', 'a' * 64, 'uk')):
            with self.assertRaises(dm.ModuleError) as cm:
                call()
            self.assertEqual(cm.exception.code, 'unknown-module')

    @unittest.skipIf(os.name == 'nt', 'посилання')
    def test_a_space_folder_reached_through_a_link_is_not_an_alias(self):
        h = self.trust()
        link = os.path.join(self.tmp, 'alpha-link')
        os.symlink(self.sp['path'], link)                       # сам простір — за посиланням: ключ `realpath` той самий
        via = dict(self.sp, path=link)
        self.assertFalse(dm._is_alias(via, 'acme'))
        self.assertTrue(dm.revoke_trust(via, 'acme'))
        self.assertEqual(mt.load_records(), {})
        self.assertFalse(mt.verify_snapshot(h), 'знімок без записів прибрано')

    def test_no_window_before_the_hash_and_the_refusal_are_checked(self):
        with mock.patch.object(mt, 'ask', side_effect=AssertionError('вікно до перевірок')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', '0' * 64, 'uk')
            self.assertEqual(cm.exception.code, 'module-changed')
            _write(os.path.join(self.d, 'CON'), 'x')
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', '0' * 64, 'uk')
            self.assertEqual(cm.exception.code, 'module-refused')
        self.assertEqual(mt.load_records(), {})

    def test_no_window_before_role_taken(self):
        self.mk('pub')
        dm.write_module_state(self.sp, 'pub', enabled=True)
        self.enable_raw()
        with mock.patch.object(mt, 'ask', side_effect=AssertionError('вікно до role-taken')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
            self.assertEqual(cm.exception.code, 'role-taken')

    def test_the_snapshot_is_the_shown_bytes_even_if_the_folder_changes_during_the_window(self):
        h = self.view()['hash']
        shown = _bytes(os.path.join(self.d, 'server.py'))

        def window(key, got_hash, texts):
            _write(os.path.join(self.d, 'server.py'), OWN_SERVER + '\n# підмінено, поки вікно відкрите\n')
            return 'yes'
        with mock.patch.object(mt, 'ask', window):
            dm.grant_trust(self.sp, 'acme', h, 'uk')
        rec = mt.load_records()[mt.key_for(self.sp['path'], 'acme')]
        self.assertEqual(rec['hash'], h, 'довіра — показаній версії, а не тій, що в теці після вікна')
        self.assertTrue(mt.verify_snapshot(h))
        self.assertEqual(_bytes(os.path.join(mt.snapshot_dir(h), 'server.py')), shown)
        self.assertEqual(dm.catalog(self.sp)['acme'].trust, 'changed', 'нова версія теки ще не довірена')

    def test_view_takes_its_state_only_from_its_own_scan(self):
        # Два скани (каталог і сам діалог) можуть розійтись: стан і причина відмови — лише з другого, з тим самим набором полів
        real = dm.catalog(self.sp)['acme']
        stale_refused = dm._clone(real, trust='refused', trust_error='symlink')
        with mock.patch.object(dm, '_own_module', return_value=stale_refused):
            v = self.view()
        self.assertEqual((v['state'], v['record']), ('untrusted', False))
        self.assertNotIn('refused', v)
        self.assertRegex(v['hash'], r'^[0-9a-f]{64}$')
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        trusted = dm.catalog(self.sp)['acme']
        _write(os.path.join(self.d, 'new.js'), '//')            # теку змінили після того, як каталог її бачив
        with mock.patch.object(dm, '_own_module', return_value=trusted):
            self.assertEqual(self.view()['state'], 'changed')
        _write(os.path.join(self.d, 'CON'), 'x')                # а тепер скан відмовляє, хоч каталог бачив її цілою
        with mock.patch.object(dm, '_own_module', return_value=trusted):
            v = self.view()
        self.assertEqual((v['state'], v['refused']['code']), ('refused', 'bad-name'))
        self.assertNotIn('hash', v)
        self.assertNotIn('files', v)

    def test_view_of_a_damaged_snapshot_stays_untrusted_with_a_record(self):
        h = self.trust()
        snap = mt.snapshot_dir(h)
        os.chmod(snap, 0o700)
        os.chmod(os.path.join(snap, 'server.py'), 0o600)
        _write(os.path.join(snap, 'server.py'), 'raise SystemExit')
        mt.forget(snap)
        v = self.view()
        self.assertEqual((v['state'], v['record']), ('untrusted', True))
        self.assertEqual({f['change'] for f in v['files']}, {'same'})
        self.assertEqual(self.ran(), [])

    def test_view_of_a_damaged_snapshot_is_untrusted_even_when_the_catalog_scan_saw_a_refusal(self):
        """Гонка: знімок пошкоджено, скан каталогу ще бачив теку `refused`, а власний скан діалогу вже чистий — стан не
        мусить братись за хешем (`trusted`/`changed`), коли знімок не цілий і код із нього не виконується."""
        h = self.trust()
        snap = mt.snapshot_dir(h)
        os.chmod(snap, 0o700)
        os.chmod(os.path.join(snap, 'server.py'), 0o600)
        _write(os.path.join(snap, 'server.py'), 'raise SystemExit')
        mt.forget(snap)
        stale = dm._clone(dm.catalog(self.sp)['acme'], trust='refused', trust_error='symlink', record=True)
        with mock.patch.object(dm, '_own_module', return_value=stale):
            v = self.view()
        self.assertEqual((v['state'], v['record']), ('untrusted', True))
        self.assertNotIn('refused', v)
        self.assertRegex(v['hash'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.ran(), [])

    def test_view_loads_only_the_asked_module(self):
        self.own('beta')
        h = self.trust()
        self.trust('beta')
        v = self.view()
        self.assertEqual(v['state'], 'trusted')
        ran = self.ran()
        self.assertEqual(len(ran), 1, ran)
        self.assertTrue(ran[0].startswith(mt.snapshot_dir(h)), 'виконано знімок не того модуля')

    def test_view_with_an_unreadable_trust_file_has_no_record(self):
        self.trust()
        _write(mt.trust_file(), '{oops')
        v = self.view()
        self.assertEqual((v['state'], v['record']), ('untrusted', False))
        self.assertEqual({f['change'] for f in v['files']}, {'new'})
        self.assertEqual(self.ran(), [])

    def test_forget_own_raises_the_generation(self):
        g = dm._OWN_GEN
        dm.forget_own('a' * 64)
        self.assertEqual(dm._OWN_GEN, g + 1)

    def test_forget_own_during_a_load_keeps_that_load_out_of_the_cache(self):
        """Повторна довіра, поки перше (збійне) завантаження ще в польоті: його результат не мусить пережити довіру."""
        self.own(server=SLEEPY)                               # `SLEEPY` і ворота — з Task 3
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='yes'):
            dm.grant_trust(self.sp, 'acme', h, 'uk')
        with mock.patch.object(dm, 'LOAD_TIMEOUT', 0.5):
            t = threading.Thread(target=dm.catalog, args=(self.sp,))
            t.start()
            for _ in range(100):                              # дочекатись потоку завантаження
                if any(x.name == 'deai-own-load-acme' for x in threading.enumerate()):
                    break
                time.sleep(0.01)
            dm.forget_own(h)
            t.join(5)
        self.assertNotIn((mt.snapshot_dir(h), 'acme'), dm._OWN_CACHE)

    def test_a_load_without_a_forget_is_cached(self):
        self.own(server=SLEEPY)
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='yes'):
            dm.grant_trust(self.sp, 'acme', h, 'uk')
        with mock.patch.object(dm, 'LOAD_TIMEOUT', 0.3):
            dm.catalog(self.sp)
        self.assertIn((mt.snapshot_dir(h), 'acme'), dm._OWN_CACHE)

    def test_retrust_forgets_a_cached_load_failure(self):
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', return_value='yes'):
            dm.grant_trust(self.sp, 'acme', h, 'uk')
        d = mt.snapshot_dir(h)
        bad = dm._failed('acme', d, 'module-error', 'load timed out after 5 s')
        with dm._LOAD_LOCK:
            dm._OWN_CACHE[(d, 'acme')] = (mt.fingerprint(d), bad)      # ніби перше завантаження не встигло
        self.assertEqual(dm.catalog(self.sp)['acme'].status, 'error')
        with mock.patch.object(mt, 'ask', return_value='yes'):
            dm.grant_trust(self.sp, 'acme', h, 'uk')                   # ті самі байти — знімок той самий
        self.assertEqual(dm.catalog(self.sp)['acme'].status, 'ok')

    def test_snapshot_removed_meanwhile_is_module_changed(self):
        with mock.patch.object(mt, 'put_record', side_effect=mt.SnapshotGone('x')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertEqual(cm.exception.code, 'module-changed')

    def test_an_unwritable_trust_record_is_unwritable(self):
        with mock.patch.object(mt, 'put_record', side_effect=OSError('disk')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertEqual(cm.exception.code, 'unwritable')
        self.assertEqual(cm.exception.message, 'trust: OSError')

    def test_unreadable_trust_file(self):
        _write(mt.trust_file(), '{oops')
        h = self.view()['hash']
        with mock.patch.object(mt, 'ask', side_effect=AssertionError('вікно показано, хоч довіру не буде куди записати')):
            for call in (lambda: dm.grant_trust(self.sp, 'acme', h, 'uk'), lambda: dm.revoke_trust(self.sp, 'acme')):
                with self.assertRaises(dm.ModuleError) as cm:
                    call()
                self.assertEqual(cm.exception.code, 'trust-unreadable')
        self.assertEqual(_bytes(mt.trust_file()), b'{oops', 'нечитабельний файл довіри не переписано')

    def test_the_trust_file_turning_unreadable_during_the_grant(self):
        with mock.patch.object(mt, 'put_record', side_effect=mt.TrustUnreadable('x')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        self.assertEqual(cm.exception.code, 'trust-unreadable')

    def test_a_failing_revoke_write_is_unwritable_and_keeps_the_last_check(self):
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        dm.check(self.sp, 'acme')
        with mock.patch.object(mt, 'drop_record', side_effect=OSError('disk')):
            with self.assertRaises(dm.ModuleError) as cm:
                dm.revoke_trust(self.sp, 'acme')
        self.assertEqual((cm.exception.code, cm.exception.message), ('unwritable', 'trust: OSError'))
        self.assertIsNotNone(dm.last_check(self.sp['id'], 'acme'), 'довіру не знято — результат перевірки лишається')

    def test_revoke_keeps_space_json_and_works_without_the_folder(self):
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        dm.write_module_state(self.sp, 'acme', enabled=True, replace=True)
        before = _bytes(self.space_json(self.sp))
        self.assertTrue(dm.revoke_trust(self.sp, 'acme'))
        self.assertEqual(_bytes(self.space_json(self.sp)), before)
        self.assertEqual(dm.catalog(self.sp)['acme'].trust, 'untrusted')
        with self.assertRaises(dm.ModuleError) as cm:
            dm.provider('publish', self.sp)
        self.assertEqual(cm.exception.code, 'module-untrusted')
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        shutil.rmtree(self.d)
        self.assertTrue(dm.revoke_trust(self.sp, 'acme'))
        self.assertFalse(dm.revoke_trust(self.sp, 'acme'))

    def test_revoke_clears_the_last_check(self):
        dm.grant_trust(self.sp, 'acme', self.view()['hash'], 'uk')
        dm.check(self.sp, 'acme')
        self.assertIsNotNone(dm.last_check(self.sp['id'], 'acme'))
        self.assertTrue(dm.revoke_trust(self.sp, 'acme'))
        self.assertIsNone(dm.last_check(self.sp['id'], 'acme'))
