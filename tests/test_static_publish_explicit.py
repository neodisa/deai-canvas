"""`static-publish` — явний запис (4d-4c, Р3): `create_space` пише його, наявні простори добирає ідемпотентний стартовий крок."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), 'app'))
import spaces_guard  # noqa: E402
import deai_modules  # noqa: E402
import spaces  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class Base(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix='sp-pub-')
        self.addCleanup(d.cleanup)
        self.tmp = os.path.realpath(d.name)
        self.deai = os.path.join(self.tmp, 'home', '.deai')
        p = mock.patch.dict(os.environ, {'HOME': os.path.join(self.tmp, 'home'), 'DEAI_HOME': self.deai})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop('DC_TASKS_FILE', None)
        deai_modules.reset_caches()

    def space(self, name, data, legacy=False):
        path = os.path.join(self.tmp, name)
        os.makedirs(path)
        if data is not None:
            with open(os.path.join(path, 'space.json'), 'w') as f:
                f.write(data if isinstance(data, str) else json.dumps(data))
        reg_path = os.path.join(self.deai, 'spaces.json')
        os.makedirs(self.deai, exist_ok=True)
        reg = json.load(open(reg_path)) if os.path.exists(reg_path) else {'version': 1, 'current': name, 'spaces': []}
        reg['spaces'].append({'id': name, 'path': path, 'legacy': legacy})
        json.dump(reg, open(reg_path, 'w'))
        return path

    def read(self, path):
        with open(os.path.join(path, 'space.json'), 'rb') as f:
            return f.read()


class Materialise(Base):
    REC = {'static-publish': {'enabled': True}}

    def test_a_new_space_has_the_record(self):
        sid = spaces.create_space('Alpha', 'space-1', os.path.join(self.tmp, 'home', 'deai-work', 'alpha'))
        sp = next(s for s in spaces.read_registry()['spaces'] if s['id'] == sid)
        self.assertEqual(json.loads(self.read(sp['path']))['modules'], self.REC)
        self.assertEqual(deai_modules.provider('publish', sp).id, 'static-publish')

    def test_an_adopted_folder_with_its_own_space_json_gets_the_record_too(self):
        """`create_space` не перезаписує готовий `space.json` усиновленої теки, але запис добирає."""
        path = os.path.join(self.tmp, 'home', 'deai-work', 'adopted')
        os.makedirs(path)
        with open(os.path.join(path, 'space.json'), 'w') as f:
            json.dump({'name': 'Own', 'color': 'space-2'}, f)
        spaces.create_space('Ignored', 'space-1', path)
        data = json.loads(self.read(path))
        self.assertEqual((data['name'], data['color'], data['modules']), ('Own', 'space-2', self.REC))

    def test_a_space_without_a_record_gets_one_and_publishes(self):
        p = self.space('a', {'name': 'A', 'color': 'space-2'})
        self.assertEqual(spaces.materialize_static_publish(), ['a'])
        data = json.loads(self.read(p))
        self.assertEqual((data['name'], data['color'], data['modules']), ('A', 'space-2', self.REC))

    def test_idempotent_to_the_byte(self):
        p = self.space('a', {'name': 'A'})
        spaces.materialize_static_publish()
        first = self.read(p)
        self.assertEqual(spaces.materialize_static_publish(), [])
        self.assertEqual(self.read(p), first)

    def test_a_disabled_record_is_a_human_decision(self):
        p = self.space('a', {'modules': {'static-publish': {'enabled': False}}})
        before = self.read(p)
        self.assertEqual(spaces.materialize_static_publish(), [])
        self.assertEqual(self.read(p), before)

    def test_liga_and_unreadable_and_foreign_shapes_are_untouched(self):
        cases = {'liga': ({'name': 'L'}, True), 'bad': ('{not json', False), 'arr': ('[]', False),
                 'modsarr': ({'modules': []}, False)}
        paths = {n: self.space(n, d, legacy=lg) for n, (d, lg) in cases.items()}
        before = {n: self.read(p) for n, p in paths.items()}
        self.assertEqual(spaces.materialize_static_publish(), [])
        self.assertEqual({n: self.read(p) for n, p in paths.items()}, before)

    def test_an_enabled_other_publisher_keeps_the_role(self):
        p = self.space('a', {'modules': {'vercel-publish': {'enabled': True}}})
        before = self.read(p)
        self.assertEqual(spaces.materialize_static_publish(), [])
        self.assertEqual(self.read(p), before)

    def test_a_disabled_other_publisher_does_not_cancel_the_default(self):
        """Паритет 0.21: неявний `static-publish` програвав лише ВВІМКНЕНОМУ явному публікатору."""
        p = self.space('a', {'modules': {'vercel-publish': {'enabled': False}}})
        self.assertEqual(spaces.materialize_static_publish(), ['a'])
        mods = json.loads(self.read(p))['modules']
        self.assertEqual(mods['vercel-publish'], {'enabled': False})
        self.assertEqual(mods['static-publish'], {'enabled': True})

    def test_an_own_publisher_by_roles_keeps_the_role(self):
        p = self.space('a', {'modules': {'acme-pub': {'enabled': True, 'roles': ['publish']}}})
        before = self.read(p)
        self.assertEqual(spaces.materialize_static_publish(), [])
        self.assertEqual(self.read(p), before)

    def test_layer_off_and_missing_folder_do_nothing(self):
        with mock.patch.object(spaces, 'layer_on', return_value=False):
            self.assertEqual(spaces.materialize_static_publish(), [])
        self.assertFalse(spaces.ensure_static_publish(os.path.join(self.tmp, 'nope')))


class NoImplicitDefault(Base):
    def test_the_implicit_default_is_gone(self):
        for name in ('IMPLICIT_MODULE', '_implicit_on'):
            self.assertFalse(hasattr(deai_modules, name), name)
        p = self.space('a', {'name': 'A'})
        sp = {'id': 'a', 'path': p, 'legacy': False}
        self.assertIsNone(deai_modules.provider('publish', sp))                 # без запису публікатора нема
        st = deai_modules.effective_state(sp)['static-publish']
        self.assertEqual((st['enabled'], st['implicit']), (False, False))


class StartupStep(Base):
    """`serve.serve_main`: після міграції ЛІГИ наявним просторам добирається запис; ізольований прогін на справжньому `~/.deai` — ні."""

    def run_main(self, real_home, boom=None):
        import serve
        import liga_migrate
        srv = mock.Mock()
        calls = []
        real = spaces.materialize_static_publish
        side = boom if boom is not None else (lambda: calls.append(1) or real())
        with mock.patch.object(serve, 'make_server', return_value=srv), \
                mock.patch.object(liga_migrate, 'startup'), \
                mock.patch.object(serve.isolation, 'real_home', return_value=real_home), \
                mock.patch.object(spaces, 'materialize_static_publish', side_effect=side):
            serve.serve_main(0)
        srv.serve_forever.assert_called_once()
        return calls

    def test_the_step_adds_the_record_before_serving(self):
        p = self.space('a', {'name': 'A'})
        self.assertEqual(self.run_main(False), [1])
        self.assertEqual(json.loads(self.read(p))['modules'], {'static-publish': {'enabled': True}})

    def test_an_isolated_run_on_the_real_home_does_not_touch_it(self):
        with mock.patch.dict(os.environ, {'DC_NO_OVERVIEW': '1'}):
            self.assertEqual(self.run_main(True), [])

    def test_a_failing_step_does_not_stop_the_server(self):
        def boom():
            raise RuntimeError('disk')
        self.run_main(False, boom=boom)                      # `serve_forever` усе одно викликано (перевірка в `run_main`)


if __name__ == '__main__':
    unittest.main()
