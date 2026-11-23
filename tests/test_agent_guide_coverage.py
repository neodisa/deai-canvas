"""Сторож гайда агента (23.11.2026): кожен публічний маршрут `/api/*` з `app/serve.py`, кожен файл `bin/` і кожна підкоманда
`bin/inbox.py`, кожна роль вбудованого модуля — описані для агента (каркас `app/templates/agents.md`, теми `docs/agents/*.md`,
`app/modules/<id>/agent.md`) або явно внутрішні (`docs/agents/_internal.txt`: `<маршрут чи bin/файл> — <причина>`). І навпаки:
доки не згадують маршрутів і файлів, яких нема. Нова фіча без рядка для агента валить цей тест — так задумано."""
import ast
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'app'))
import agents_md  # noqa: E402

SERVE = os.path.join(REPO, 'app', 'serve.py')
TEMPLATE = os.path.join(REPO, 'app', 'templates', 'agents.md')
DOCS = os.path.join(REPO, 'docs', 'agents')
MODULES = os.path.join(REPO, 'app', 'modules')
BIN = os.path.join(REPO, 'bin')
INTERNAL = os.path.join(DOCS, '_internal.txt')
ROUTE_RE = re.compile(r'/api/[a-z0-9]+(?:-[a-z0-9]+)*')
#: Маршрут у коді: рядок у будь-яких лапках; хвіст (`/`, `/файл`) — маршрут із префіксною роздачею (`/api/module-ui/…`).
ROUTE_LITERAL_RE = re.compile(r"""['"](/api/[a-z0-9-]+)(?:/[^'"]*)?['"]""")
#: `bin/` не після слова чи крапки (`.bin/x`, `node_modules/.bin/x` — не наше); жадібно, кінцева крапка речення — не частина імені.
BIN_RE = re.compile(r'(?<![\w.])bin/[\w.-]+')
INTERNAL_TOKEN_RE = re.compile(r'/api/[a-z0-9-]+|bin/[\w.-]+')
HOW = ('Describe it for agents in docs/agents/<topic>.md (or the skeleton app/templates/agents.md), '
       'or add it to docs/agents/_internal.txt as «<token> — <reason>».')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def extract_routes(code):
    """Маршрути `/api/*` з тексту коду: одинарні й подвійні лапки, з хвостом префіксної роздачі чи без."""
    return sorted(set(ROUTE_LITERAL_RE.findall(code)))


def bin_tokens(text):
    """`bin/<файл>` із тексту; кінцева крапка (кінець речення) відкидається."""
    return sorted({t.rstrip('.') for t in BIN_RE.findall(text)})


def tripwire(code, routes):
    """Рядки коду, що починаються з `/api/`, але не є відомим маршрутом (склеєний чи f-рядковий маршрут): `[літерал]`.
    Константи в `HANDLED_PREFIXES = (…)` (голі префікси) пропускаються. Докстрінги пропускаються; рядок-продовження — лише `/`, `?` після маршруту."""
    bad = []
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                first.value.value = ''
    skip = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HANDLED_PREFIXES' for t in node.targets):
            skip |= {id(c) for c in ast.walk(node.value) if isinstance(c, ast.Constant)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and id(node) not in skip and isinstance(node.value, str) and node.value.startswith('/api/'):
            m = ROUTE_RE.match(node.value)
            rest = node.value[m.end():] if m else node.value
            if not m or m.group(0) not in routes or (rest and rest[0] not in '/?'):
                bad.append(node.value)
    return sorted(set(bad))


def agent_texts():
    """`{мітка: текст}`: каркас і теми, які справді бачить агент (`agents_md.topics()`: `docs/agents/*.md`, `module-<id>`)."""
    out = {'app/templates/agents.md': _read(TEMPLATE)}
    for name, _ in agents_md.topics():
        out[f'topic:{name}'] = agents_md.topic_text(name)
    return out


def internal_entries():
    """`[(токен, причина, рядок)]` з `_internal.txt` (з дублями); порожні рядки й `#` — пропуск."""
    out = []
    for n, line in enumerate(_read(INTERNAL).splitlines(), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        token, _, reason = s.partition(' — ')
        out.append((token.strip(), reason.strip(), n))
    return out


def internal_problems(entries, described):
    """Вади `_internal.txt`: дубль, токен не за формою, токен, який уже описано (`described(токен)`), порожня причина."""
    out, seen = [], set()
    for tok, reason, n in entries:
        if tok in seen:
            out.append(f'_internal.txt:{n}: duplicate token `{tok}`')
        seen.add(tok)
        if not INTERNAL_TOKEN_RE.fullmatch(tok):
            out.append(f'_internal.txt:{n}: `{tok}` is neither /api/<route> nor bin/<file>')
        if not reason:
            out.append(f'_internal.txt:{n}: `{tok}` needs « — <reason>»')
        if described(tok):
            out.append(f'_internal.txt:{n}: `{tok}` is described for agents — remove from _internal.txt')
    return out


def mentioned(token, text):
    """Токен із межею праворуч: `/api/page-new` не зараховує `/api/page`, `bin/inbox.py.bak` — `bin/inbox.py`;
    для `bin/…` ще й ліва межа (`.bin/x` не рахується)."""
    left = r'(?<![\w.])' if token.startswith('bin/') else ''
    return re.search(left + re.escape(token) + r'(?![\w-]|\.\w)', text) is not None


def inbox_documented(sub, text):
    """Підкоманда `inbox.py` — аргумент одразу після `inbox.py` (перед нею дозволено лише `--task X`, `--all`, `--where`)."""
    return re.search(r'inbox\.py(?:\s+(?:--task(?:=|\s+)\S+|--all|--where))*\s+' + re.escape(sub) + r'(?=\s|$)', text) is not None


class Helpers(unittest.TestCase):
    """Сторож сам перевіряється на вигаданих входах: що саме він ловить."""

    def test_extract_sees_prefix_and_double_quoted_routes(self):
        code = "a = '/api/x-y'\nb = '/api/pre/'\nc = \"/api/kit/kit.css\"\nd = '<a href=\"/api/z/w\">'"
        self.assertEqual(extract_routes(code), ['/api/kit', '/api/pre', '/api/x-y', '/api/z'])

    def test_tripwire_catches_built_routes(self):
        routes = ['/api/known']
        self.assertEqual(tripwire("x = '/api/known'\ny = '/api/known/f?q=1'", routes), [])
        self.assertEqual(tripwire("x = '/api/' + name", routes), ['/api/'])
        both = "HANDLED_PREFIXES = ('/app', '/api/')\nx = '/api/' + name"
        self.assertEqual(tripwire(both, routes), ['/api/'])
        self.assertEqual(tripwire("HANDLED_PREFIXES = ('/api/',)", routes), [])
        self.assertEqual(tripwire("x = f'/api/new-{k}'", routes), ['/api/new-'])
        self.assertEqual(tripwire("x = '/api/other'", routes), ['/api/other'])
        self.assertEqual(tripwire('def f():\n    """see /api/other"""\n', routes), [])

    def test_bin_tokens(self):
        self.assertEqual(bin_tokens('run <deai>/bin/a.py. and node_modules/.bin/x and bin/b.py.bak'), ['bin/a.py', 'bin/b.py.bak'])
        self.assertFalse(mentioned('bin/a.py', 'see bin/a.py.bak'))
        self.assertTrue(mentioned('bin/a.py', 'see <deai>/bin/a.py.'))
        self.assertFalse(mentioned('bin/a.py', 'x/.bin/a.py'))

    def test_internal_problems(self):
        e = [('/api/a', 'r', 1), ('/api/a', 'r', 2), ('/api/A', 'r', 3), ('bin/x.py', '', 4), ('bin/y.py', 'r', 5)]
        got = internal_problems(e, lambda t: t == 'bin/y.py')
        self.assertEqual(len(got), 4)
        self.assertTrue(any('duplicate' in g for g in got) and any('neither' in g for g in got))
        self.assertTrue(any('remove' in g for g in got) and any('reason' in g for g in got))

    def test_inbox_documented(self):
        self.assertTrue(inbox_documented('reply', 'python3 <deai>/bin/inbox.py --task t reply <id> --text x'))
        self.assertTrue(inbox_documented('reply', 'inbox.py reply <id>'))
        self.assertFalse(inbox_documented('reply', 'inbox.py --all then reply later'))
        self.assertFalse(inbox_documented('reply', 'inbox.py resolve <id> --reason reply '))


class Coverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serve = _read(SERVE)
        cls.routes = extract_routes(cls.serve)
        cls.texts = agent_texts()
        cls.all = '\n'.join(cls.texts.values())
        cls.internal = internal_entries()
        cls.internal_tokens = {t for t, _, _ in cls.internal}

    def test_internal_file_is_well_formed(self):
        self.assertTrue(self.internal)
        self.assertEqual(internal_problems(self.internal, lambda t: mentioned(t, self.all)), [])

    def test_routes_are_extracted_completely(self):
        self.assertEqual(tripwire(self.serve, self.routes), [],
                         'app/serve.py builds or names an /api route the guard cannot see: spell it as a plain literal')
        for r in ('/api/module-client', '/api/module-ui', '/api/module-ui-kit'):
            self.assertIn(r, self.routes)

    def test_every_topic_file_is_a_topic(self):
        topics = {n for n, _ in agents_md.topics()}
        files = {f[:-3] for f in os.listdir(DOCS) if f.endswith('.md') and not f.startswith('_')}
        self.assertEqual(sorted(files - topics), [], 'file in docs/agents/ that agents never see (bad name or module- prefix)')
        self.assertGreaterEqual(len(topics), 12)

    def test_every_route_is_described_or_internal(self):
        self.assertGreater(len(self.routes), 50)
        for r in self.routes:
            with self.subTest(route=r):
                if r not in self.internal_tokens and not mentioned(r, self.all):
                    self.fail(f'{r}: not described in docs/agents/*.md or app/templates/agents.md, '
                              f'and not listed in docs/agents/_internal.txt. {HOW}')

    def test_docs_mention_only_real_routes(self):
        for label, text in {**self.texts, 'docs/agents/_internal.txt': _read(INTERNAL)}.items():
            for r in sorted(set(ROUTE_RE.findall(text))):
                with self.subTest(file=label, route=r):
                    self.assertIn(r, self.routes, f'{label} mentions {r}, which app/serve.py does not have')

    def test_every_bin_tool_is_described_or_internal(self):
        tools = sorted(f for f in os.listdir(BIN)
                       if not f.startswith(('test_', '.')) and os.path.isfile(os.path.join(BIN, f)))
        self.assertIn('inbox.py', tools)
        for f in tools:
            with self.subTest(tool=f):
                if f'bin/{f}' not in self.internal_tokens and not mentioned(f'bin/{f}', self.all):
                    self.fail(f'bin/{f}: not described in docs/agents/*.md or app/templates/agents.md, '
                              f'and not listed in docs/agents/_internal.txt. {HOW}')

    def test_docs_mention_only_real_bin_tools(self):
        for label, text in {**self.texts, 'docs/agents/_internal.txt': _read(INTERNAL)}.items():
            for tok in bin_tokens(text):
                with self.subTest(file=label, tool=tok):
                    self.assertTrue(os.path.isfile(os.path.join(REPO, tok)), f'{label} mentions {tok}, which does not exist')

    def test_every_inbox_subcommand_is_described(self):
        subs = re.findall(r"""add_parser\(\s*['"]([a-z][a-z-]*)['"]""", _read(os.path.join(BIN, 'inbox.py')))
        self.assertGreaterEqual(len(subs), 2)
        for s in subs:
            with self.subTest(subcommand=s):
                self.assertTrue(inbox_documented(s, self.all), f'inbox.py {s}: no example `inbox.py [--task X] {s} …` in the docs')

    def test_module_roles_match_the_modules_topic(self):
        text = _read(os.path.join(DOCS, 'modules.md'))
        roles = set()
        for mid in os.listdir(MODULES):
            p = os.path.join(MODULES, mid, 'module.json')
            if os.path.isfile(p):
                roles |= set(json.loads(_read(p)).get('roles', []))
        self.assertGreaterEqual(len(roles), 5)
        for r in sorted(roles):
            with self.subTest(role=r):
                self.assertIn(f'`{r}`', text, f'role {r} of a built-in module is not in docs/agents/modules.md')
        documented = set(re.findall(r'^- `([a-z]+)`:', text, re.M))
        self.assertTrue(documented)
        for r in sorted(documented - roles):
            with self.subTest(documented_role=r):
                self.fail(f'docs/agents/modules.md lists role `{r}`, which no app/modules/*/module.json has')


if __name__ == '__main__':
    unittest.main()
