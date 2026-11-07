import ast
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _docstring_nodes(tree):
    """Вузли-літерали, що є докстрінгами модуля/класу/функції: пояснення про оригінали дозволені, код — ні."""
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = getattr(n, 'body', None)
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                out.add(b[0].value)
    return out


class NoOriginalsRead(unittest.TestCase):
    """⛔ Оригінали ЛІГИ (корінь `tasks.json`, оточення, `pipeline-feedback`) читає ЛИШЕ `app/liga_migrate.py` (4d-4b). Охоронець — AST:
    рядкові константи, імена, атрибути, визначення й імпорти. Сканує `app/**/*.py` (крім `liga_migrate.py`), `bin/*.py`, `ops/*.py`
    без `test_*`; докстрінги й коментарі не рахуються."""

    STRINGS = {'supabase_url', 'supabase_key', 'jira_base', 'jira_email', 'jira_token', 'gitlab_ssh_key', 'gitlab_host_ip',
               'SUPABASE_URL', 'SUPABASE_KEY', 'SUPABASE_SERVICE_KEY', 'JIRA_EMAIL', 'JIRA_TOKEN'}
    NAMES = {'supabase_from', 'jira_from', 'service_key_config', 'supabase_config', 'jira_config', 'legacy_ctx', 'legacy_module'}
    #: `preview_password` дозволено лише: імʼя функції; `.get`/`.pop('preview_password')`/`['preview_password']` на ЗАДАЧІ (`task`/`t`, також
    #: `(task or {})`); ключ літерала-словника (форма ВІДПОВІДІ API). Будь-що інше — читання кореня.
    TASK_VARS = {'task', 't'}
    #: Єдині свідомі винятки (файл, значення), кожен — з причиною: `LEGACY_MARKERS` (охоронець маркера, живий до 4d-4c) і журнал синку
    #: огляду `OVERVIEW_LOG` (шлях ЖУРНАЛУ, а не облікових).
    ALLOWED = {('app/spaces.py', 'str:gitlab_host_ip'), ('app/spaces.py', 'str:gitlab_ssh_key'), ('app/serve.py', 'str:pipeline-feedback')}

    @staticmethod
    def _files():
        out = []
        for base, _d, fs in os.walk(os.path.join(ROOT, 'app')):
            out += [os.path.join(base, f) for f in fs if f.endswith('.py') and not f.startswith('test_')]
        for sub in ('bin', 'ops'):
            out += [p for p in glob.glob(os.path.join(ROOT, sub, '*.py')) if not os.path.basename(p).startswith('test_')]
        return sorted(p for p in out if os.path.basename(p) != 'liga_migrate.py')

    @classmethod
    def scan(cls, tree):
        """Що в дереві порушує закон: `{'str:<значення>', 'name:<імʼя>', 'preview_password'}`."""
        doc = _docstring_nodes(tree)
        hits = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n not in doc:
                if n.value in cls.STRINGS:
                    hits.add('str:' + n.value)
                if 'pipeline-feedback' in n.value:
                    hits.add('str:pipeline-feedback')
            ident = None
            if isinstance(n, ast.Name):
                ident = n.id
            elif isinstance(n, ast.Attribute):
                ident = n.attr
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                ident = n.name
            elif isinstance(n, ast.alias):
                ident = n.name.split('.')[-1]
            elif isinstance(n, ast.arg):
                ident = n.arg
            if ident in cls.NAMES:
                hits.add('name:' + ident)
        hits |= cls._preview_password_misuse(tree, doc)
        return hits

    @classmethod
    def _is_task(cls, recv):
        if isinstance(recv, ast.BoolOp) and recv.values:
            recv = recv.values[0]
        return isinstance(recv, ast.Name) and recv.id in cls.TASK_VARS

    @classmethod
    def _preview_password_misuse(cls, tree, doc):
        """`'preview_password'` як рядок — лише `<task|t>.get('preview_password')` чи `<task|t>['preview_password']`."""
        allowed = set()
        for n in ast.walk(tree):
            recv = None
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('get', 'pop') and n.args
                    and isinstance(n.args[0], ast.Constant) and n.args[0].value == 'preview_password'):
                recv, const = n.func.value, n.args[0]
            elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and n.slice.value == 'preview_password':
                recv, const = n.value, n.slice
            if cls._is_task(recv):
                allowed.add(const)
            if isinstance(n, ast.Dict):
                allowed |= {k for k in n.keys if isinstance(k, ast.Constant) and k.value == 'preview_password'}
        bad = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and n.value == 'preview_password'
               and n not in doc and n not in allowed]
        return {'preview_password'} if bad else set()

    def test_the_runtime_does_not_read_originals(self):
        bad = {}
        for p in self._files():
            with open(p, encoding='utf-8') as f:
                hit = self.scan(ast.parse(f.read()))
            rel = os.path.relpath(p, ROOT)
            hit = {h for h in hit if (rel, h) not in self.ALLOWED}
            if hit:
                bad[rel] = sorted(hit)
        self.assertEqual(bad, {})

    def test_the_guard_can_fail(self):
        """Охоронець, який не може впасти, — фікція: кожна форма порушення дає червоне, чисте читання задачі — ні."""
        for src, want in (("cfg.get('supabase_url')", 'str:supabase_url'), ("os.environ.get('JIRA_TOKEN')", 'str:JIRA_TOKEN'),
                          ("os.path.join(h, '.claude', 'pipeline-feedback')", 'str:pipeline-feedback'),
                          ("import x\nx.supabase_from(cfg)", 'name:supabase_from'),
                          ("def legacy_ctx():\n    return 1", 'name:legacy_ctx'),
                          ("cfg.get('preview_password')", 'preview_password'), ("cfg['preview_password']", 'preview_password'),
                          ("cfg.pop('preview_password', None)", 'preview_password')):
            with self.subTest(src=src):
                self.assertIn(want, self.scan(ast.parse(src)))
        self.assertEqual(self.scan(ast.parse("task.get('preview_password')")), set())
        self.assertEqual(self.scan(ast.parse("t['preview_password']")), set())
        self.assertEqual(self.scan(ast.parse("(task or {}).get('preview_password')")), set())
        self.assertEqual(self.scan(ast.parse("r = {'preview_password': pw}")), set())
        self.assertEqual(self.scan(ast.parse('def f():\n    """supabase_url лишилась лише в докстрінгу"""\n    return 1')), set())

    def test_the_scan_sees_the_migration_module(self):
        """Охоронець не порожній: у `liga_migrate.py` (виключеному зі сканування) оригінали справді є."""
        with open(os.path.join(ROOT, 'app', 'liga_migrate.py'), encoding='utf-8') as f:
            self.assertIn('str:supabase_url', self.scan(ast.parse(f.read())))
        self.assertTrue(self._files())


class NoImplicit(unittest.TestCase):
    """⛔ Запасного постачальника `Implicit` нема (4d-4b): модуля `app/implicit.py` нема, ніхто його не імпортує, імені `Implicit` у коді нема."""

    @staticmethod
    def _files():
        out = []
        for base, _d, fs in os.walk(os.path.join(ROOT, 'app')):
            out += [os.path.join(base, f) for f in fs if f.endswith('.py')]
        for sub in ('bin', 'ops'):
            out += glob.glob(os.path.join(ROOT, sub, '*.py'))
        return sorted(p for p in out if not os.path.basename(p).startswith('test_'))

    @staticmethod
    def scan(tree):
        hits = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                hits |= {'import:' + a.name for a in n.names if a.name.split('.')[-1] == 'implicit'}
            elif isinstance(n, ast.ImportFrom):
                if (n.module or '').split('.')[-1] == 'implicit':
                    hits.add('from:implicit')
                hits |= {'import:' + a.name for a in n.names if a.name in ('implicit', 'Implicit')}
            elif isinstance(n, ast.Name) and n.id == 'Implicit':
                hits.add('name:Implicit')
            elif isinstance(n, ast.Attribute) and (n.attr == 'Implicit' or (isinstance(n.value, ast.Name) and n.value.id == 'implicit')):
                hits.add('attr:' + n.attr)
            elif isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == 'Implicit':
                hits.add('def:Implicit')
        return hits

    def test_no_implicit_provider(self):
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'app', 'implicit.py')))
        bad = {}
        for p in self._files():
            with open(p, encoding='utf-8') as f:
                hit = self.scan(ast.parse(f.read()))
            if hit:
                bad[os.path.relpath(p, ROOT)] = sorted(hit)
        self.assertEqual(bad, {})

    def test_the_guard_can_fail(self):
        for src in ('import implicit', 'from app import implicit', 'from implicit import route', 'x = implicit.route(p)',
                    'isinstance(p, deai_modules.Implicit)', 'class Implicit:\n    pass'):
            with self.subTest(src=src):
                self.assertTrue(self.scan(ast.parse(src)), src)
        self.assertEqual(self.scan(ast.parse('import isolation\nisolation.route("x")')), set())


if __name__ == '__main__':
    unittest.main()
