"""Сторож гайда агента (23.11.2026): кожен публічний маршрут `/api/*` з `app/serve.py`, кожен файл `bin/` і кожна підкоманда
`bin/inbox.py`, кожна роль вбудованого модуля — описані для агента (каркас `app/templates/agents.md`, теми `docs/agents/*.md`,
`app/modules/<id>/agent.md`) або явно внутрішні (`docs/agents/_internal.txt`: `<маршрут чи bin/файл> — <причина>`). І навпаки:
доки не згадують маршрутів і файлів, яких нема. Нова фіча без рядка для агента валить цей тест — так задумано."""
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SERVE = os.path.join(REPO, 'app', 'serve.py')
TEMPLATE = os.path.join(REPO, 'app', 'templates', 'agents.md')
DOCS = os.path.join(REPO, 'docs', 'agents')
MODULES = os.path.join(REPO, 'app', 'modules')
BIN = os.path.join(REPO, 'bin')
INTERNAL = os.path.join(DOCS, '_internal.txt')
ROUTE_RE = re.compile(r'/api/[a-z0-9]+(?:-[a-z0-9]+)*')
BIN_RE = re.compile(r'\bbin/[A-Za-z0-9_.-]*[A-Za-z0-9_]')
HOW = ('Describe it for agents in docs/agents/<topic>.md (or the skeleton app/templates/agents.md), '
       'or add it to docs/agents/_internal.txt as «<token> — <reason>».')


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def agent_texts():
    """`{мітка: текст}`: каркас, теми `docs/agents/*.md`, `agent.md` вбудованих модулів."""
    out = {'app/templates/agents.md': _read(TEMPLATE)}
    for fn in sorted(os.listdir(DOCS)):
        if fn.endswith('.md'):
            out[f'docs/agents/{fn}'] = _read(os.path.join(DOCS, fn))
    for mid in sorted(os.listdir(MODULES)):
        p = os.path.join(MODULES, mid, 'agent.md')
        if os.path.isfile(p):
            out[f'app/modules/{mid}/agent.md'] = _read(p)
    return out


def internal():
    """`{токен: (причина, рядок)}` з `_internal.txt`; порожні рядки й `#` — пропуск."""
    out = {}
    for n, line in enumerate(_read(INTERNAL).splitlines(), 1):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        token, _, reason = s.partition(' — ')
        out[token.strip()] = (reason.strip(), n)
    return out


def mentioned(token, text):
    """Токен із межею слова праворуч: `/api/page-new` не зараховує `/api/page`."""
    return re.search(re.escape(token) + r'(?![A-Za-z0-9_-])', text) is not None


class Coverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serve = _read(SERVE)
        cls.routes = sorted(set(re.findall(r"'(/api/[a-z0-9-]+)'", cls.serve)))
        cls.texts = agent_texts()
        cls.all = '\n'.join(cls.texts.values())
        cls.internal = internal()

    def test_internal_entries_have_a_reason(self):
        self.assertTrue(self.internal)
        for tok, (reason, n) in self.internal.items():
            with self.subTest(token=tok):
                self.assertTrue(reason, f'_internal.txt:{n}: `{tok}` needs « — <reason>»')

    def test_every_route_is_described_or_internal(self):
        self.assertGreater(len(self.routes), 50)
        missing = [r for r in self.routes if r not in self.internal and not mentioned(r, self.all)]
        self.assertEqual(missing, [], HOW)

    def test_docs_mention_only_real_routes(self):
        for label, text in {**self.texts, 'docs/agents/_internal.txt': _read(INTERNAL)}.items():
            for r in sorted(set(ROUTE_RE.findall(text))):
                with self.subTest(file=label, route=r):
                    self.assertIn(r, self.routes, f'{label} mentions {r}, which app/serve.py does not have')

    def test_every_bin_tool_is_described_or_internal(self):
        tools = sorted(f for f in os.listdir(BIN)
                       if not f.startswith(('test_', '.')) and os.path.isfile(os.path.join(BIN, f)))
        self.assertIn('inbox.py', tools)
        missing = [f for f in tools if f'bin/{f}' not in self.internal and not mentioned(f'bin/{f}', self.all)]
        self.assertEqual(missing, [], HOW)

    def test_docs_mention_only_real_bin_tools(self):
        for label, text in {**self.texts, 'docs/agents/_internal.txt': _read(INTERNAL)}.items():
            for tok in sorted(set(BIN_RE.findall(text))):
                with self.subTest(file=label, tool=tok):
                    self.assertTrue(os.path.isfile(os.path.join(REPO, tok)), f'{label} mentions {tok}, which does not exist')

    def test_every_inbox_subcommand_is_described(self):
        subs = re.findall(r"add_parser\(\s*'([a-z][a-z-]*)'", _read(os.path.join(BIN, 'inbox.py')))
        self.assertGreaterEqual(len(subs), 2)
        for s in subs:
            with self.subTest(subcommand=s):
                self.assertRegex(self.all, r'inbox\.py[^\n]*\s' + re.escape(s) + r'\s')

    def test_every_module_role_is_in_the_modules_topic(self):
        text = _read(os.path.join(DOCS, 'modules.md'))
        roles = set()
        for mid in os.listdir(MODULES):
            p = os.path.join(MODULES, mid, 'module.json')
            if os.path.isfile(p):
                roles |= set(json.loads(_read(p)).get('roles', []))
        self.assertGreaterEqual(len(roles), 5)
        for r in sorted(roles):
            with self.subTest(role=r):
                self.assertIn(f'`{r}`', text)


if __name__ == '__main__':
    unittest.main()
