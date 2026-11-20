"""Інструменти простору (етап Е, 0.31.0, Task 4): `POST /api/space-tool`, `tools` у `GET /api/modules` і `GET /api/spaces`.

«В Figma» — не модуль, а прапорець простору: `space.json` → `"tools": {"figma": false}`; ключа/обʼєкта нема = увімкнено.
Фікстура — та сама, що в `test_spaces_serve` (тимчасові HOME/DEAI_HOME/DC_TASKS_FILE, сервер у процесі, порт 0).
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_spaces_serve as base  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


class SpaceTools(base.Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()                           # тимчасові HOME/DEAI_HOME/DC_TASKS_FILE і сервер — у `Fixture`
        os.environ['DEAI_HOME'] = cls.deai             # те саме значення: ізоляція видима й у цьому файлі (охоронець `test_serve`)

    @property
    def space_json(self):
        return os.path.join(self.p_path, 'space.json')

    def tool(self, on, **kw):
        payload = {'space': self.p_id, 'tool': 'figma', 'on': on}
        payload.update(kw)
        return self.post('/api/space-tool', payload)

    def setUp(self):
        super().setUp()
        self.restore_bytes(self.space_json)

    def test_missing_key_means_on(self):
        st, body = self.jget(f'/api/modules?space={self.p_id}')
        self.assertEqual((st, body['tools']), (200, {'figma': True}))

    def test_off_writes_the_key_and_keeps_the_rest_of_space_json(self):
        before = _json(self.space_json)
        st, body = self.tool(False)
        self.assertEqual((st, body), (200, {'ok': True, 'space': self.p_id, 'tools': {'figma': False}}))
        after = _json(self.space_json)
        self.assertEqual(after.pop('tools'), {'figma': False})
        self.assertEqual(after, before)
        self.assertEqual(self.jget(f'/api/modules?space={self.p_id}')[1]['tools'], {'figma': False})

    def test_on_removes_the_key_and_the_empty_object(self):
        before = _json(self.space_json)
        self.tool(False)
        st, body = self.tool(True)
        self.assertEqual((st, body['tools']), (200, {'figma': True}))
        self.assertEqual(_json(self.space_json), before)           # файл мінімальний: ні `tools`, ні `figma: true`
        self.assertEqual(self.jget(f'/api/modules?space={self.p_id}')[1]['tools'], {'figma': True})

    def test_the_listing_carries_tools_per_space(self):
        self.tool(False)
        rows = {s['id']: s for s in self.jget('/api/spaces')[1]['spaces']}
        self.assertEqual(rows[self.p_id]['tools'], {'figma': False})
        self.assertEqual(rows[self.e_id]['tools'], {'figma': True})

    def test_only_figma_is_a_tool(self):
        before = self.get_bytes()
        for tool in ('shell', '', None, ['figma'], 'FIGMA'):
            with self.subTest(tool=tool):
                st, body = self.post('/api/space-tool', {'space': self.p_id, 'tool': tool, 'on': False})
                self.assertEqual((st, body['ok'], body['code']), (400, False, 'unknown-tool'), body)
        self.assertEqual(self.get_bytes(), before)

    def test_on_must_be_a_boolean(self):
        before = self.get_bytes()
        for on in ('false', 0, None, 'no'):
            with self.subTest(on=on):
                st, body = self.tool(on)
                self.assertEqual((st, body['ok'], body['code']), (400, False, 'bad-value'), body)
        self.assertEqual(self.get_bytes(), before)

    def test_unknown_space_is_the_same_404_as_space_update(self):
        before = self.get_bytes()
        for sp in ('nope', None, ['p']):
            with self.subTest(space=sp):
                st, body = self.tool(False, space=sp)
                self.assertEqual((st, body['ok'], body['code']), (404, False, 'unknown-space'), body)
        self.assertEqual(self.get_bytes(), before)

    def test_a_foreign_origin_gets_403_and_nothing_is_written(self):
        before = self.get_bytes()
        for origin in ('http://evil.example', 'null'):
            with self.subTest(origin=origin):
                st, body = self.post('/api/space-tool', {'space': self.p_id, 'tool': 'figma', 'on': False}, {'Origin': origin})
                self.assertEqual((st, body), (403, {'ok': False, 'error': 'foreign origin'}))
        self.assertEqual(self.get_bytes(), before)

    def test_it_is_a_registry_route_without_the_task_prefix(self):
        self.assertIn('/api/space-tool', base.serve.Handler._REGISTRY_ROUTES)
        st, body = self.post('/t/x/api/space-tool', {'space': self.p_id, 'tool': 'figma', 'on': False})
        self.assertEqual(st, 400)

    def test_a_non_true_value_in_the_file_is_not_off(self):
        spaces.set_space_tool(self.p_id, 'figma', False)
        data = _json(self.space_json)
        data['tools']['figma'] = 'false'                            # лише справжній `false` вимикає
        with open(self.space_json, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        self.assertEqual(spaces.space_tools({'path': self.p_path}), {'figma': True})
        self.assertEqual(spaces.space_tools({'path': ''}), {'figma': True})        # неявний простір — без диска

    def test_a_corrupt_space_json_is_refused_and_left_byte_identical(self):
        junk = b'<<<<<<< HEAD\n{"name": "x", "modules": {"publish": {}}}\n=======\n{}\n>>>>>>> other\n'
        with open(self.space_json, 'wb') as f:
            f.write(junk)
        st, body = self.post('/api/space-tool', {'space': self.p_id, 'tool': 'figma', 'on': False})
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'space-json-unreadable'))
        self.assertEqual(self.get_bytes(), junk)
        with self.assertRaises(spaces.InputError) as cm:
            spaces.set_space_tool(self.p_id, 'figma', False)
        self.assertEqual(cm.exception.code, 'space-json-unreadable')
        self.assertEqual(self.get_bytes(), junk)

    def get_bytes(self):
        with open(self.space_json, 'rb') as f:
            return f.read()


if __name__ == '__main__':
    unittest.main()
