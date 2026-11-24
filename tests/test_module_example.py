"""Приклад-модуль `docs/modules/examples/page-notes/` (M1, Task 7): його маніфест проходить перевірку ядра, `server.py`
завантажується з очікуваними функціями, а `tool_*`/`action_*` працюють крізь справжні `call_tool`/`run_action`.
Приклад копіюють люди, тож зміна контракту не має мовчки його ламати.
"""
import os
import shutil
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
sys.path.insert(0, HERE)
import spaces_guard  # noqa: E402
import deai_modules as dm  # noqa: E402
from test_modules_own import OwnEnv  # noqa: E402

EXAMPLE = os.path.join(REPO, 'docs', 'modules', 'examples', 'page-notes')
_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


class PageNotesExampleTest(OwnEnv):
    def setUp(self):
        super().setUp()
        self.dst = os.path.join(self.sp['path'], 'modules', 'page-notes')
        shutil.copytree(EXAMPLE, self.dst, ignore=shutil.ignore_patterns('__pycache__'))
        self.trust('page-notes')
        self.enable_raw('page-notes', roles=())

    def module(self):
        return dm.catalog(self.sp)['page-notes']

    def test_manifest_passes_and_module_loads(self):
        m = self.module()
        self.assertEqual((m.status, m.trust, m.api), ('ok', 'trusted', 2), m.error)
        self.assertEqual(m.roles, [])
        self.assertEqual([(t['id'], t['icon'], t['key'], t['panel']) for t in m.tools],
                         [('notes', 'doc', 'N', 'panel/index.html')])
        self.assertEqual([(a['id'], a['where']) for a in m.actions], [('summary', ('palette', 'task'))])
        for fn in ('check', 'tool_load', 'tool_save', 'action_summary'):
            self.assertTrue(callable(m.fn(fn)), fn)

    def test_panel_files_exist_and_are_served_names(self):
        for rel in ('panel/index.html', 'panel/notes.js', 'panel/notes.css'):
            self.assertTrue(os.path.isfile(os.path.join(EXAMPLE, rel)), rel)

    def test_tools_and_action_end_to_end(self):
        call = lambda fn, args: dm.call_tool(self.sp, 'page-notes', fn, args)  # noqa: E731
        self.assertEqual(call('tool_load', {'task': 't1', 'page': 'p1'}), {'text': ''})
        self.assertEqual(call('tool_save', {'task': 't1', 'page': 'p1', 'text': 'Привіт'}), {'ok': True})
        call('tool_save', {'task': 't1', 'page': 'p2', 'text': '   '})        # пробіли — теж не порожньо для файла
        call('tool_save', {'task': 't2', 'page': 'p1', 'text': 'інша задача'})
        self.assertEqual(call('tool_load', {'task': 't1', 'page': 'p1'}), {'text': 'Привіт'})
        self.assertEqual(call('tool_load', {'task': 't1', 'page': 'p3'}), {'text': ''})
        r = dm.run_action(self.sp, 'page-notes', 'summary', {'from': 'palette', 'task': {'id': 't1', 'name': 'T', 'dir': '/x'},
                                                            'iteration': None})
        self.assertEqual(r, {'ok': True, 'text': 'Нотаток: 1'})                # лише непорожні
        call('tool_save', {'task': 't1', 'page': 'p1', 'text': ''})            # порожній текст видаляє
        r = dm.run_action(self.sp, 'page-notes', 'summary', {'from': 'task', 'task': {'id': 't1', 'name': 'T', 'dir': '/x'},
                                                            'iteration': None})
        self.assertEqual(r['text'], 'Нотаток: 0')

    def test_ids_never_become_paths_and_bad_args_are_refused(self):
        call = lambda fn, args: dm.call_tool(self.sp, 'page-notes', fn, args)  # noqa: E731
        call('tool_save', {'task': '../../x', 'page': '/etc/passwd', 'text': 'a'})
        cache = dm.module_ctx(self.sp, 'page-notes')['cache_dir']
        self.assertEqual(sorted(os.listdir(cache)), ['notes.json'])           # жодних сторонніх файлів і тимчасових решток
        self.assertEqual(oct(os.stat(cache).st_mode & 0o777), '0o700')
        for args in ({'task': 't', 'page': 'p', 'text': 'x' * 20001}, {'task': 't', 'page': 'p', 'text': 5},
                     {'task': '', 'page': 'p', 'text': 'a'}, {'task': 't', 'page': 7, 'text': 'a'}, 'x'):
            with self.assertRaises(dm.ModuleError) as c:
                call('tool_save', args)
            self.assertEqual(c.exception.code, 'module-error', repr(args)[:60])   # свій код ядро віддає як `module-error`
        call('tool_save', {'task': 't', 'page': 'p', 'text': 'x' * 20000})     # рівно ліміт — можна

    def test_check_creates_cache_dir(self):
        v = dm.call(self.module(), self.module().fn('check'), dm.module_ctx(self.sp, 'page-notes'))
        self.assertEqual(v, {'ok': True})


CONTRAST = os.path.join(REPO, 'docs', 'modules', 'examples', 'contrast')


class ContrastExampleTest(OwnEnv):
    """Приклад «Контраст» (M2): інструмент із дозволами `page`; уся логіка в панелі, `server.py` порожній."""

    def setUp(self):
        super().setUp()
        self.dst = os.path.join(self.sp['path'], 'modules', 'contrast')
        shutil.copytree(CONTRAST, self.dst, ignore=shutil.ignore_patterns('__pycache__'))
        self.trust('contrast')
        self.enable_raw('contrast', roles=())

    def test_manifest_passes_and_module_loads(self):
        m = dm.catalog(self.sp)['contrast']
        self.assertEqual((m.status, m.trust, m.api), ('ok', 'trusted', 2), m.error)
        self.assertEqual(m.roles, [])
        self.assertEqual([(t['id'], t['icon'], t['key'], t['panel'], tuple(t['page'])) for t in m.tools],
                         [('contrast', 'eye', 'K', 'panel/index.html', ('read', 'mark', 'change', 'listen'))])
        self.assertEqual(m.actions, ())
        self.assertTrue(callable(m.fn('check')))
        self.assertFalse([n for n in ('tool_load', 'tool_save') if callable(m.fn(n))])

    def test_folder_has_exactly_the_listed_files(self):
        found = sorted(os.path.relpath(os.path.join(r, f), CONTRAST).replace(os.sep, '/')
                       for r, ds, fs in os.walk(CONTRAST) for f in fs if '__pycache__' not in r)
        self.assertEqual(found, ['module.json', 'panel/contrast.css', 'panel/contrast.js', 'panel/index.html', 'server.py'])

    def test_check_is_ok(self):
        m = dm.catalog(self.sp)['contrast']
        v = dm.call(m, m.fn('check'), dm.module_ctx(self.sp, 'contrast'))
        self.assertEqual(v, {'ok': True})


if __name__ == '__main__':
    unittest.main()
