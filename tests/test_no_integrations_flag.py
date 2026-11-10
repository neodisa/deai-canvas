"""Охоронці 4d-4c: прапорець `integrations` і значення API `'legacy'` не вертаються в рантайм."""
import ast
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GONE = {'integrations_on', 'integrations_for', 'require_integrations', 'IntegrationsOff', '_outbound_ok', '_liga_like', '_liga_flow',
        '_liga_track_repos', 'API_IMPLICIT', 'IMPLICIT_MODULE', '_implicit_on', 'NO_INTEGRATIONS_SPACE_MSG', 'OVERVIEW_LOG',
        'has_markers', 'LEGACY_MARKERS'}
#: Винятки — за парою (файл, функція), а не за файлом цілим (Поправки 1, 4): інакше нове читання в тому ж файлі пройшло б непоміченим.
ALLOWED = {
    ('app/spaces.py', '_validate'): 'реєстр толерує bool-ключ integrations (відкат 0.22 → 0.21 безпечний)',
    ('app/liga_migrate.py', '_liga_integrations'): 'єдине місце, що читає ключ: історичні записи 0.21 (Поправка 1)',
}


def _docstrings(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = getattr(n, 'body', None)
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                out.add(b[0].value)
    return out


class NoIntegrationsFlag(unittest.TestCase):
    """AST: у `app/**/*.py`, `bin/*.py`, `ops/*.py` (без `test_*`) нема ні літерала `'integrations'`, ні ключового аргумента
    `integrations=`, ні жодного імені з `GONE` (імʼя, атрибут, визначення) — окрім пар із `ALLOWED`."""

    @staticmethod
    def offenders(source, name='<src>'):
        tree = ast.parse(source)
        doc = _docstrings(tree)
        found = []

        def walk(node, fn):
            for ch in ast.iter_child_nodes(node):
                cur = ch.name if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)) else fn
                hit = ((isinstance(ch, ast.Constant) and ch.value == 'integrations' and ch not in doc)
                       or (isinstance(ch, ast.Name) and ch.id in GONE) or (isinstance(ch, ast.Attribute) and ch.attr in GONE)
                       or (isinstance(ch, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and ch.name in GONE)
                       or (isinstance(ch, ast.keyword) and ch.arg == 'integrations')
                       or (isinstance(ch, ast.alias) and ch.name in GONE))
                if hit and (name, cur) not in ALLOWED:
                    found.append((name, cur, getattr(ch, 'lineno', 0)))
                walk(ch, cur)
        walk(tree, 'module')
        return found

    def test_the_runtime_has_no_flag(self):
        files = [p for pat in ('app/**/*.py', 'bin/*.py', 'ops/*.py') for p in glob.glob(os.path.join(ROOT, pat), recursive=True)
                 if not os.path.basename(p).startswith('test_')]
        self.assertGreater(len(files), 20)
        bad = []
        for p in sorted(files):
            with open(p, encoding='utf-8') as f:
                bad += self.offenders(f.read(), os.path.relpath(p, ROOT))
        self.assertEqual(bad, [])

    def test_the_detector_catches_every_form(self):
        for src in ("x = sp['integrations']", "sp.get('integrations')", "spaces.integrations_on()", "def integrations_for(sp): pass",
                    "f(integrations=True)", "raise IntegrationsOff('x')", "from spaces import require_integrations",
                    "API_IMPLICIT = 'legacy'"):
            with self.subTest(src=src):
                self.assertTrue(self.offenders(src), src)
        for src in ("'''integrations'''", "def f():\n    '''integrations'''", "x = 'integrations-off'"):
            with self.subTest(src=src):
                self.assertEqual(self.offenders(src), [], src)

    def test_the_allowed_exceptions_are_exactly_two_functions(self):
        self.assertEqual(sorted(ALLOWED), [('app/liga_migrate.py', '_liga_integrations'), ('app/spaces.py', '_validate')])
        for rel, extra in (('app/spaces.py', "\ndef other(sp):\n    return sp.get('integrations')\n"),
                           ('app/liga_migrate.py', "\ndef other(sp):\n    return sp.get('integrations')\n")):
            with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
                src = f.read()
            self.assertEqual(self.offenders(src, rel), [], rel)
            self.assertTrue(self.offenders(src + extra, rel), rel)


class NoLegacyApiValue(unittest.TestCase):
    """У `app/*.js` нема порівнянь із `"legacy"`; виняток — вигляд `publishReaction` (`view.kind`, `app.js`)."""
    CMP = re.compile(r'[!=]==?\s*["\']legacy["\']|["\']legacy["\']\s*[!=]==?')

    @classmethod
    def offenders(cls, text, name='<src>'):
        return [(name, i + 1) for i, line in enumerate(text.splitlines()) if cls.CMP.search(line) and 'view.kind' not in line]

    def test_no_comparison_with_the_literal_in_the_client(self):
        files = sorted(glob.glob(os.path.join(ROOT, 'app', '*.js')))
        self.assertGreater(len(files), 10)
        bad = []
        for p in files:
            with open(p, encoding='utf-8') as f:
                bad += self.offenders(f.read(), os.path.basename(p))
        self.assertEqual(bad, [])

    def test_detector(self):
        for src in ('caps.vcs === "legacy"', "p.kind === 'legacy'", 'v !== "legacy"', '"legacy" === v'):
            self.assertEqual(len(self.offenders(src)), 1, src)
        for src in ("if (view.kind === 'legacy') {}", 'kind: "legacy"', 'x === "legacyx"'):
            self.assertEqual(self.offenders(src), [], src)


class NoIntegrationsInClient(unittest.TestCase):
    """У коді (не в коментарях) `app/*.js` нема ЧИТАННЯ `integrations` (доступ до властивості, ключ обʼєкта, порівняння, деструктуризація).
    Слово в рядку-ключовому слові пошуку (`shell-palette.js`, `space-conn`) читанням не є — регулярний вираз його не ловить."""
    READ = re.compile(r'''\??\.integrations\b|["']integrations["']|\bintegrations\s*(?:[:=!]|\?\.)|[{,]\s*integrations\s*[},]''')

    @staticmethod
    def strip(text):
        return re.sub(r'(?m)^\s*//[^\n]*|(?<![:"\'])//[^\n]*', '', re.sub(r'/\*.*?\*/', '', text, flags=re.S))

    @classmethod
    def offenders(cls, text, name='<src>'):
        return [(name, m.group(0)) for m in cls.READ.finditer(cls.strip(text))]

    def test_clean(self):
        files = sorted(glob.glob(os.path.join(ROOT, 'app', '*.js')))
        self.assertGreater(len(files), 10)
        bad = []
        for p in files:
            with open(p, encoding='utf-8') as f:
                bad += self.offenders(f.read(), os.path.basename(p))
        self.assertEqual(bad, [])

    def test_detector(self):
        for src in ("const a = data?.space?.integrations;", "if (sp.integrations === false) {}", "x['integrations']", "({ integrations: true })",
                    "const { integrations } = sp;", "const { a, integrations } = sp;"):
            self.assertEqual(len(self.offenders(src)), 1, src)
        for src in ('"space-conn": "підключення connections integrations інтеграції модулі",', "// sp.integrations === false",
                    "/* data.integrations */ const x = 1;", "const integrationsList = [];"):
            self.assertEqual(self.offenders(src), [], src)
