import ast
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NoTracksAdapter(unittest.TestCase):
    """⛔ Адаптер ЛІГИ живе ЛИШЕ в `app/liga_migrate.py` (4d-4a). Охоронець — AST, а не grep: ловить імʼя, атрибут, визначення,
    імпорт-псевдонім і аргумент, тож «обхід» перейменуванням у `import … as` чи в `getattr`-подібному вигляді не проходить без
    правки самого списку. Сканує `app/**/*.py` і `bin/*.py`, крім `liga_migrate.py` і `test_*`."""

    FORBIDDEN = {'legacy_tracks', 'legacy_root', 'legacy_repos', '_LEGACY_LABELS', 'profile_repos', '_legacy_cfg',
                 'FALLBACK_ROOT', 'FALLBACK_WORK_ROOT'}
    #: Єдине місце, де `adapter_applies` дозволено згадувати (крім `liga_migrate.py`, який сканер пропускає).
    ADAPTER_APPLIES_OK = {'tracks.py'}
    #: Читання `profile` з запису задачі дозволене лише на межах (спека: `profile` — тільки на вході `task-new`, у реєстрі й у
    #: `SHARED`). Ключ — імʼя функції, у якій воно стоїть.
    PROFILE_OK = {'_task_new', '_track_of_entry', '<module>'}

    @staticmethod
    def _files():
        out = []
        for base, _d, fs in os.walk(os.path.join(ROOT, 'app')):
            out += [os.path.join(base, f) for f in fs if f.endswith('.py') and not f.startswith('test_')]
        out += [p for p in glob.glob(os.path.join(ROOT, 'bin', '*.py')) if not os.path.basename(p).startswith('test_')]
        return sorted(p for p in out if os.path.basename(p) != 'liga_migrate.py')

    @staticmethod
    def _idents(tree):
        s = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Name):
                s.add(n.id)
            elif isinstance(n, ast.Attribute):
                s.add(n.attr)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                s.add(n.name)
            elif isinstance(n, ast.alias):
                s.add(n.name.split('.')[-1])
                s.add(n.asname or '')
            elif isinstance(n, ast.arg):
                s.add(n.arg)
        return s

    @staticmethod
    def _adapter_member(tree):
        """`X.adapter` і `def adapter` — адаптер-властивість; голе імʼя `adapter` у `serve` — звичайна локальна змінна (не ловимо)."""
        hits = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr == 'adapter':
                hits.add('adapter')
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'adapter':
                hits.add('adapter')
        return hits

    @staticmethod
    def _reads_profile(n):
        """Вузол, що читає ключ `profile`: `x.get('profile')`, `x['profile']` або літерал-перелік із ним (кортеж, список, множина:
        `for key in ('track', 'profile')` — запасний хід через цикл, а не лише кортеж)."""
        is_get = (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'get' and n.args
                  and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'profile')
        is_sub = isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == 'profile'
        is_seq = (isinstance(n, (ast.Tuple, ast.List, ast.Set))
                  and any(isinstance(e, ast.Constant) and e.value == 'profile' for e in n.elts))
        return is_get or is_sub or is_seq

    def test_the_runtime_has_no_adapter(self):
        bad = {}
        for p in self._files():
            with open(p, encoding='utf-8') as f:
                tree = ast.parse(f.read())
            hit = (self._idents(tree) & self.FORBIDDEN) | self._adapter_member(tree)
            if 'adapter_applies' in self._idents(tree) and os.path.basename(p) not in self.ADAPTER_APPLIES_OK:
                hit.add('adapter_applies')
            if hit:
                bad[os.path.relpath(p, ROOT)] = sorted(hit)
        self.assertEqual(bad, {})

    def test_profile_is_read_only_at_the_boundary(self):
        seen = []
        for p in self._files():
            with open(p, encoding='utf-8') as f:
                tree = ast.parse(f.read())
            parents = {}
            for n in ast.walk(tree):
                for c in ast.iter_child_nodes(n):
                    parents[c] = n

            def fn_of(n):
                while n in parents:
                    n = parents[n]
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        return n.name
                return '<module>'
            for n in ast.walk(tree):
                if self._reads_profile(n):
                    seen.append((os.path.relpath(p, ROOT), fn_of(n)))
        self.assertTrue(seen, 'межі зникли: охоронець порожній')
        stray = [x for x in seen if x[1] not in self.PROFILE_OK]
        self.assertEqual(stray, [], 'читання `profile` поза межею: %s' % stray)

    def test_the_guard_can_fail(self):
        """Охоронець, який не може впасти, — фікція: підсовуємо сканеру зіпсований код і бачимо червоне."""
        src = 'import tracks\ntracks.legacy_root(cfg, "x")\nclass V:\n    @property\n    def adapter(self):\n        return 1\n'
        tree = ast.parse(src)
        self.assertEqual((self._idents(tree) & self.FORBIDDEN) | self._adapter_member(tree), {'legacy_root', 'adapter'})
        self.assertEqual(self._adapter_member(ast.parse('adapter = 1\nprint(adapter)')), set())

    def test_the_profile_detector_catches_every_fallback_shape(self):
        """Запасний хід `profile` у циклі: кортеж, СПИСОК і МНОЖИНА літералів, `.get`, індекс — усе червоніє; чисте читання `track` — ні."""
        for src in ("for key in ('track', 'profile'):\n    v = t.get(key)",
                    "for key in ['track', 'profile']:\n    v = t.get(key)",
                    "for key in {'track', 'profile'}:\n    v = t.get(key)",
                    "v = t.get('profile')", "v = t['profile']"):
            with self.subTest(src=src):
                self.assertTrue(any(self._reads_profile(n) for n in ast.walk(ast.parse(src))), src)
        self.assertFalse(any(self._reads_profile(n) for n in ast.walk(ast.parse("for key in ['track']:\n    v = t.get('track')"))))


if __name__ == '__main__':
    unittest.main()
