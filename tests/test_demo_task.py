"""`POST /api/demo-task` (0.33.0): демо-задача «Tally» в просторі — копія шаблону в it1, дерево, флоу, два піни в локальному
каналі задачі з адресою цього сервера; вільний id на машині; `reuse` віддає наявну `tally-demo` цього простору."""
import json
import os
import sys
import unittest
import unittest.mock
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
sys.path.insert(0, HERE)
import serve  # noqa: E402
import spaces_guard  # noqa: E402
import test_spaces_serve as base  # noqa: E402


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _json(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


class DemoTask(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['DEAI_NO_UPDATE_CHECK'] = '1'
        cls.addClassCleanup(os.environ.pop, 'DEAI_NO_UPDATE_CHECK', None)

    def setUp(self):
        super().setUp()
        # Задачі пишемо в `DEAI_HOME` фікстури (вже тимчасовий); явне присвоєння — для статичного охоронця `test_serve`.
        patcher = mock.patch.dict(os.environ, {'DEAI_HOME': self.deai})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_seed_reuse_and_unique_ids(self):
        st, body = self.post('/api/demo-task', {'space': self.p_id, 'title': 'Tally — демо'})
        self.assertEqual(st, 200, body)
        self.assertEqual((body['ok'], body['id'], body['space']), (True, 'tally-demo', self.p_id))
        it1 = os.path.join(self.p_path, 'tally-demo', 'iterations', 'it1')
        tpl = serve.DEMO_DIR
        self.assertEqual(_json(os.path.join(it1, 'pages.json')), _json(os.path.join(tpl, 'pages.json')))
        self.assertEqual(_json(os.path.join(it1, 'flow.json')), _json(os.path.join(tpl, 'flow.json')))
        self.assertTrue(os.path.isfile(os.path.join(it1, 'dashboard', 'index.html')))
        pins = _json(os.path.join(self.p_path, 'tally-demo', '.dc-local-comments.json'))
        self.assertEqual(sorted(p['status'] for p in pins), ['open', 'resolved'])
        for p in pins:
            self.assertTrue(p['meta']['url'].startswith(f'{self.base}/commented?it=it1&page='), p['meta']['url'])
            self.assertIsInstance(p['fp'], dict)
        self.assertTrue(next(p for p in pins if p['status'] == 'resolved')['resolveReason'])
        self.assertEqual(self.jget('/api/spaces')[1]['current'], self.p_id, 'простір демо став поточним')

        st, again = self.post('/api/demo-task', {'space': self.p_id, 'reuse': True})
        self.assertEqual((st, again['id'], again.get('existed')), (200, 'tally-demo', True))
        self.assertFalse(os.path.exists(os.path.join(self.p_path, 'tally-demo-2')), '`reuse` нічого не створює')

        st, second = self.post('/api/demo-task', {'space': self.p_id})
        self.assertEqual((st, second['id']), (200, 'tally-demo-2'))

        st, other = self.post('/api/demo-task', {'space': self.e_id, 'reuse': True})
        self.assertEqual((st, other['id'], other.get('existed')), (200, 'tally-demo-3', None),
                         '`tally-demo` живе в іншому просторі — тут нова')

    def test_refusals(self):
        st, body = self.post('/api/demo-task', {'space': 'nope-space'})
        self.assertEqual((st, body['code']), (400, 'unknown-space'))
        for bad in (None, '', 5):
            with self.subTest(space=bad):
                st, body = self.post('/api/demo-task', {'space': bad})
                self.assertEqual((st, body['code']), (400, 'bad-request'))

    def test_demo_task_id_skips_taken_ids(self):
        taken = {'tally-demo', 'tally-demo-2'}
        with unittest.mock.patch.object(serve.spaces, 'find_task', side_effect=lambda t: {} if t in taken else None):
            self.assertEqual(serve.demo_task_id(), 'tally-demo-3')


if __name__ == '__main__':
    unittest.main()
