"""`bin/inbox.py`: довідка, якір, «станом на» і закриття пінів з CLI.

Чотири записки фідбеку дизайнерів (15.09 і 22.09.2026):
  • fb-22092026-6aed32 — `--help` друкував сам інбокс, CLI закриття не було;
  • fb-22092026-4460ae — якір без класу й розмітки, сесії читали JSON руками;
  • fb-15092026-8221e6 — «показує не всі піни»: насправді вивід не казав,
    станом на коли він, а піни ставили наживо ПІСЛЯ запуску.

⛔ Ізоляція: `DC_TASKS_FILE` — на тимчасову фікстуру, `urlopen` підмінено на
КОЖЕН тест (справжня мережа = падіння тесту), особа машини — з оточення.
Живий `tasks.json` і `.dc-local-comments.json` дизайнера не чіпаються.
"""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
import inbox  # noqa: E402

SHOT = 'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ' + 'A' * 40000
INLINE_IMG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ'


def _pin(pid, text, status='open', ts='20.09.2026 10:00', **kw):
    """Пін у формі, яку пише `local-adapter.js` (`clean()`): ключі
    `resolvedV`/`resolveReason` є завжди, навіть порожні."""
    p = {'id': pid, 'author': 'Ольга', 'text': text, 'status': status,
         'fp': {'tag': 'span', 'text': text, 'path': ['div[4]', 'div[0]', 'span[0]']},
         'htmlSnapshot': None, 'meta': {'version': '3', 'shot': SHOT},
         'bornV': 1, 'resolvedV': None, 'resolveReason': None, 'ts': ts}
    p.update(kw)
    return p


def _proj(pid, text, status='open', ts='20.09.2026 10:00', **kw):
    """Пін у формі рядка Supabase (`supabase_pins`): snake_case."""
    p = {'id': pid, 'text': text, 'status': status, 'author': 'Олег', 'ts': ts,
         'meta': {'version': '3', 'shot': SHOT}, 'born_v': 1,
         'fp': {'tag': 'button', 'text': text, 'path': ['div[1]']},
         'html_snapshot': None, 'resolved_v': None, 'resolve_reason': None}
    p.update(kw)
    return p


class _Resp:
    def __init__(self, body=b'', status=200):
        self._body, self.status = body, status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeNet:
    """Замість мережі: GET віддає фікстуру проєктних пінів, PATCH записується."""

    def __init__(self, project=None, get_error=None):
        self.project = project or []
        self.get_error = get_error
        self.calls = []

    def __call__(self, req, timeout=None, context=None):
        self.calls.append({
            'method': req.get_method(), 'url': req.full_url,
            'body': json.loads(req.data.decode('utf-8')) if req.data else None,
            'headers': {k.lower(): v for k, v in req.header_items()},
            'timeout': timeout, 'context': context})
        if req.get_method() == 'GET':
            if self.get_error:
                raise self.get_error
            return _Resp(json.dumps(self.project).encode('utf-8'))
        return _Resp(b'', 204)

    def patches(self):
        return [c for c in self.calls if c['method'] == 'PATCH']


class InboxCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='dc-inbox-')
        self.task_dir = os.path.join(self.tmp, 'task')
        os.makedirs(self.task_dir)
        self.tasks_file = os.path.join(self.tmp, 'tasks.json')
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump({'current': 'fx', 'tasks': {'fx': {
                'title': 'Фікстура', 'dir': self.task_dir,
                'comment_project': 'dc/fixture-inbox-test'}}}, f)
        self._env = {k: os.environ.get(k) for k in
                     ('DC_TASKS_FILE', 'DC_IDENTITY_NAME', 'DC_IDENTITY_EMAIL')}
        os.environ['DC_TASKS_FILE'] = self.tasks_file
        os.environ['DC_IDENTITY_NAME'] = 'Я'
        os.environ['DC_IDENTITY_EMAIL'] = 'me@example.test'
        self.net = FakeNet()
        p = mock.patch('urllib.request.urlopen', self.net)
        p.start()
        self.addCleanup(p.stop)
        self.set_iterations([{'id': 'it1'}])

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- фікстури ---
    @property
    def local_file(self):
        return os.path.join(self.task_dir, '.dc-local-comments.json')

    def set_local(self, pins):
        with open(self.local_file, 'w', encoding='utf-8') as f:
            json.dump(pins, f, ensure_ascii=False, indent=1)

    def local_bytes(self):
        with open(self.local_file, 'rb') as f:
            return f.read()

    def local_pins(self):
        with open(self.local_file, encoding='utf-8') as f:
            return json.load(f)

    def set_iterations(self, its):
        with open(os.path.join(self.task_dir, 'iterations.json'), 'w', encoding='utf-8') as f:
            json.dump({'iterations': its}, f)

    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = inbox.main(argv)
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue()


class Help(InboxCase):
    """fb-22092026-6aed32: `--help` друкував повний дамп коментарів."""

    def test_help_does_not_print_inbox(self):
        with mock.patch.object(inbox, 'load_tasks',
                               side_effect=AssertionError('--help надрукував інбокс')):
            rc, out, _ = self.run_main(['--help'])
        self.assertEqual(rc, 0)
        self.assertIn('usage', out)
        self.assertNotIn('Inbox задачи', out)

    def test_help_shows_how_to_close_a_pin(self):
        """Довідка мусить відповісти на те питання, з яким по неї прийшли."""
        rc, out, _ = self.run_main(['-h'])
        self.assertEqual(rc, 0)
        self.assertRegex(out, r'resolve \S+ --reason')

    def test_unknown_argument_is_an_error_not_silence(self):
        """Тиха ігноровка аргументів і була вадою: `inbox.py bf360` друкував
        інбокс, наче аргументу не було."""
        with mock.patch.object(inbox, 'load_tasks',
                               side_effect=AssertionError('аргумент проігноровано')):
            rc, _, err = self.run_main(['bf360'])
        self.assertEqual(rc, 2)
        self.assertIn('invalid choice', err)


class Anchor(InboxCase):
    """fb-22092026-4460ae: шлях індексів не збігається з DOM превʼю."""

    HTML = ('<button class="madd-cav  is-open" data-x="a>b">\n'
            '      Додати\n      умову\n    </button>')

    def list_out(self, project=None):
        self.net.project = project or []
        rc, out, _ = self.run_main([])
        self.assertEqual(rc, 0)
        return out

    def test_local_anchor_has_selector_and_collapsed_html(self):
        self.set_local([_pin('aaaaaaaa-1', 'кнопка', htmlSnapshot={
            'outerHTML': self.HTML, 'text': 'Додати умову'})])
        out = self.list_out()
        self.assertIn('↳ селектор: .madd-cav.is-open', out)
        self.assertIn('↳ html: <button class="madd-cav is-open" data-x="a>b"> Додати умову',
                      out)

    def test_html_fragment_is_capped(self):
        long = '<div class="x">' + 'слово ' * 100 + '</div>'
        self.set_local([_pin('aaaaaaaa-1', 'довгий', htmlSnapshot={'outerHTML': long})])
        line = next(ln for ln in self.list_out().splitlines() if '↳ html:' in ln)
        frag = line.split('↳ html: ', 1)[1]
        self.assertLessEqual(len(frag), inbox.HTML_HEAD + 1)
        self.assertTrue(frag.endswith('…'))

    def test_project_anchor_reads_snake_case_snapshot(self):
        """Supabase віддає `html_snapshot`, не `htmlSnapshot`."""
        out = self.list_out([_proj('bbbbbbbb-1', 'проєктний', html_snapshot={
            'text': 'x', 'outerHTML': '<a class="lz-link" href="#">x</a>'})])
        self.assertIn('↳ селектор: .lz-link', out)
        self.assertIn('↳ html: <a class="lz-link" href="#">x</a>', out)

    def test_empty_class_prints_no_selector(self):
        self.set_local([_pin('aaaaaaaa-1', 'порожній клас', htmlSnapshot={
            'outerHTML': '<span class="">x</span>'})])
        out = self.list_out()
        self.assertNotIn('селектор', out)
        self.assertIn('↳ html: <span class="">x</span>', out)

    def test_comment_layer_own_classes_are_not_in_selector(self):
        """Підсвітка comment-layer (`cl-hl`) — не клас макета: у коді її немає."""
        self.set_local([_pin('aaaaaaaa-1', 'підсвічений', htmlSnapshot={
            'outerHTML': '<div class="madd-cav cl-hl">x</div>'})])
        out = self.list_out()
        self.assertIn('↳ селектор: .madd-cav\n', out)
        self.assertIn('↳ html: <div class="madd-cav cl-hl">x</div>', out)

    def test_pin_number_carries_its_channel(self):
        """fb-30092026-e53eaa: `meta.seq` локальних і проєктних пінів незалежні —
        «№91» існує в обох, і дизайнер з Claude говорили про різні піни."""
        self.set_local([_pin('aaaaaaaa-1', 'локальний', meta={'version': '3', 'seq': 91})])
        out = self.list_out([_proj('bbbbbbbb-1', 'проєктний', meta={'version': '3', 'seq': 91})])
        self.assertIn('• L#91 [3] локальний', out)
        self.assertIn('• P#91 [3] проєктний', out)

    def test_pin_context_says_where_it_was(self):
        """fb-06102026-c38f46: пін на іншому кроці SPA — Claude має знати, ДЕ він."""
        self.set_local([_pin('aaaaaaaa-1', 'крок 2', meta={'version': '3', 'seq': 5,
                       'ctx': {'heading': 'Додаткові компанії', 'active': ['Крок 2']}})])
        self.assertIn('↳ де: «Крок 2» · розділ «Додаткові компанії»', self.list_out())

    def test_where_prints_widget_and_twins(self):
        """fb-30092026-e53eaa п.1–2: `--where` каже віджет і скільки таких самих."""
        self.set_local([_pin('aaaaaaaa-1', 'кнопка', meta={'version': '15/me--welcome', 'seq': 7})])
        seen = {}

        def fake(cmd, **kw):
            seen['pins'] = json.loads(kw['input'])
            return mock.Mock(returncode=0, stdout=json.dumps(
                {'aaaaaaaa-1': {'found': True, 'widget': 'Ризики компанії', 'twins': ['Санкції', 'Суди']}}),
                stderr='')
        with mock.patch.object(inbox.subprocess, 'run', side_effect=fake):
            rc, out, _ = self.run_main(['--where'])
        self.assertEqual(rc, 0)
        self.assertEqual(seen['pins'][0]['it'], 'it15')
        self.assertEqual(seen['pins'][0]['page'], 'me--welcome')
        self.assertIn('↳ віджет: Ризики компанії', out)
        self.assertIn('↳ ще 2 таких самих: «Санкції», «Суди»', out)

    def test_where_not_found_and_tool_failure_are_said(self):
        self.set_local([_pin('aaaaaaaa-1', 'зник', meta={'version': '3/holovna', 'seq': 1})])
        with mock.patch.object(inbox.subprocess, 'run', return_value=mock.Mock(
                returncode=0, stdout=json.dumps({'aaaaaaaa-1': {'found': False}}), stderr='')):
            self.assertIn('↳ на сторінці не знайдено', self.run_main(['--where'])[1])
        with mock.patch.object(inbox.subprocess, 'run', return_value=mock.Mock(
                returncode=1, stdout='', stderr='connect ECONNREFUSED')):
            rc, out, _ = self.run_main(['--where'])
        self.assertEqual(rc, 0, '--where не сміє валити inbox')
        self.assertIn('--where не спрацював', out)

    def test_without_where_no_browser_is_started(self):
        self.set_local([_pin('aaaaaaaa-1', 'кнопка', meta={'version': '3/holovna', 'seq': 1})])
        with mock.patch.object(inbox.subprocess, 'run') as run:
            self.list_out()
        run.assert_not_called()

    def test_pin_without_seq_says_so(self):
        self.set_local([_pin('aaaaaaaa-1', 'без номера', meta={'version': '3'})])
        self.assertIn('• L#? [3] без номера', self.list_out())

    def test_no_snapshot_keeps_old_anchor(self):
        self.set_local([_pin('aaaaaaaa-1', 'старий пін')])
        out = self.list_out()
        self.assertIn('↳ якір: <span> «старий пін»  · div[4] > div[0] > span[0]', out)
        self.assertNotIn('↳ html:', out)

    def test_no_base64_in_output(self):
        """⛔ `meta.shot` — base64 на десятки КБ; інлайн-картинка в outerHTML —
        теж base64. Жодне з двох не має потрапити у вивід."""
        html = f'<div class="card"><img src="{INLINE_IMG}"></div>'
        self.set_local([_pin('aaaaaaaa-1', 'з картинкою',
                             htmlSnapshot={'outerHTML': html})])
        out = self.list_out([_proj('bbbbbbbb-1', 'з шотом', html_snapshot={
            'outerHTML': html})])
        self.assertIn('↳ селектор: .card', out)
        self.assertNotIn('base64', out)
        self.assertNotIn('AAAAAAAAAA', out)


class AsOf(InboxCase):
    """fb-15092026-8221e6: два читання розійшлись, бо між ними ставили піни."""

    def test_header_has_time_and_newest_pin_per_channel(self):
        # '02.10' новіше за '15.09', хоча рядком менше; 'не час' — нерозбірне
        # і рядком більше за будь-яку цифру. Обидві пастки для max по рядку.
        self.set_local([_pin('aaaaaaaa-1', 'a', ts='15.09.2026 09:05'),
                        _pin('aaaaaaaa-2', 'b', ts='02.10.2026 08:00', status='resolved'),
                        _pin('aaaaaaaa-3', 'c', ts='не час'),
                        _pin('aaaaaaaa-4', 'd', ts=None)])
        self.net.project = [_proj('bbbbbbbb-1', 'x', ts='01.09.2026 10:00'),
                            _proj('bbbbbbbb-2', 'y', ts='27.09.2026 01:59')]
        rc, out, _ = self.run_main([])
        self.assertEqual(rc, 0)
        head = out.splitlines()[0]
        self.assertRegex(head, r'станом на \d\d:\d\d:\d\d')
        local, project = out.split('-- ПРОЄКТ', 1)
        self.assertIn('найновіший пін: 02.10.2026 08:00', local)
        self.assertIn('найновіший пін: 27.09.2026 01:59', project)

    def test_no_timestamps_says_so(self):
        self.set_local([_pin('aaaaaaaa-1', 'a', ts='')])
        rc, out, _ = self.run_main([])
        self.assertIn('найновіший пін: — (немає пінів із часом)', out.split('-- ПРОЄКТ')[0])


class WorkingIterationPair(unittest.TestCase):
    """Парний інваріант: копія в inbox == `state.working_iteration`.

    Копія, а не `import state`, свідома (див. докстрінг у inbox). Ціна копії —
    розсинхрон, і його ловить рівно цей тест.
    """

    CASES = [
        ([], ''),
        ([{'id': 'it1'}], ''),
        ([{'id': 'it1', 'author_key': 'me'}, {'id': 'it2', 'author_key': 'other'}], 'me'),
        ([{'id': 'it1', 'author_key': 'other'}], 'me'),
        ([{'id': 'it1', 'author_key': 'me'}, {'id': 'it3'}, {'id': 'it4', 'author_key': 'o'}], 'me'),
    ]

    def test_same_answer_as_state(self):
        import state
        for its, key in self.CASES:
            with self.subTest(its=its, key=key):
                self.assertEqual(inbox.working_iteration(its, key),
                                 state.working_iteration(its, key))


class ResolveLocal(InboxCase):
    def fixture(self):
        pins = [_pin('11111111-aaaa', 'перший'),
                _pin('22222222-bbbb', 'другий', htmlSnapshot={'outerHTML': '<b>x</b>'}),
                _pin('33333333-cccc', 'третій')]
        self.set_local(pins)
        return pins

    def test_resolve_writes_exact_fields_and_nothing_else(self):
        before = self.fixture()
        rc, out, _ = self.run_main(['resolve', '222222', '--reason', 'перенесено в шапку',
                                    '--it', '3'])
        self.assertEqual(rc, 0, out)
        after = self.local_pins()
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[2], before[2])
        got = after[1]
        self.assertEqual(got['status'], 'resolved')
        self.assertIs(type(got['resolvedV']), int)
        self.assertEqual(got['resolvedV'], 3)
        self.assertEqual(got['resolveReason'], 'перенесено в шапку')
        self.assertIsInstance(got['meta']['resolvedAt'], int)
        self.assertGreater(got['meta']['resolvedAt'], 1_700_000_000_000)  # мс, не с
        # Решта полів — ті самі, і в тому самому порядку.
        self.assertEqual(list(got), list(before[1]))
        expect = copy.deepcopy(before[1])
        expect.update(status='resolved', resolvedV=3, resolveReason='перенесено в шапку')
        expect['meta']['resolvedAt'] = got['meta']['resolvedAt']
        self.assertEqual(got, expect)
        # Формат — як у serve._local_comments_post (indent=1), інакше діф на весь файл.
        self.assertEqual(self.local_bytes().decode('utf-8'),
                         json.dumps(after, ensure_ascii=False, indent=1))
        self.assertEqual(self.net.calls, [], 'локальний пін не мусить іти в мережу')

    def test_default_iteration_is_the_last_own(self):
        """Без --it — остання СВОЯ ітерація, а не просто остання (чужа it4)."""
        self.fixture()
        self.set_iterations([{'id': 'it1', 'author_key': 'me@example.test'},
                             {'id': 'it3', 'author_key': 'me@example.test'},
                             {'id': 'it4', 'author': 'Ольга', 'author_key': 'designer2@x'}])
        rc, out, _ = self.run_main(['resolve', '111111', '--reason', 'готово'])
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.local_pins()[0]['resolvedV'], 3)

    def test_no_iterations_and_no_it_refuses(self):
        """Номер ітерації не вигадуємо: немає робочої — просимо --it."""
        self.fixture()
        self.set_iterations([])
        raw = self.local_bytes()
        rc, out, _ = self.run_main(['resolve', '111111', '--reason', 'готово'])
        self.assertNotEqual(rc, 0)
        self.assertIn('--it', out)
        self.assertEqual(self.local_bytes(), raw)

    def test_ambiguous_prefix_refuses_without_write(self):
        self.set_local([_pin('abcdef01-x', 'кнопка «Додати» у шапці'),
                        _pin('abcdef02-y', 'відступ між картками')])
        raw = self.local_bytes()
        rc, out, _ = self.run_main(['resolve', 'abcdef', '--reason', 'x', '--it', '1'])
        self.assertNotEqual(rc, 0)
        self.assertIn('неоднозначний', out)
        self.assertIn('abcdef01 «кнопка «Додати» у шапці»', out)
        self.assertIn('abcdef02 «відступ між картками»', out)
        self.assertEqual(self.local_bytes(), raw)
        self.assertEqual(self.net.patches(), [])

    def test_already_closed_is_reported_and_skipped(self):
        self.set_local([_pin('44444444-dddd', 'закритий', status='resolved',
                             resolvedV=2, resolveReason='зроблено раніше')])
        raw = self.local_bytes()
        rc, out, _ = self.run_main(['resolve', '444444', '--reason', 'ще раз', '--it', '5'])
        self.assertEqual(rc, 0, 'уже закритий — у потрібному стані, повтор не падає')
        self.assertIn('уже закритий', out)
        self.assertIn('зроблено раніше', out)
        self.assertEqual(self.local_bytes(), raw)

    def test_not_found_makes_exit_nonzero_but_others_still_close(self):
        self.fixture()
        rc, out, _ = self.run_main(['resolve', '111111', 'ffffff', '--reason', 'готово',
                                    '--it', '1'])
        self.assertEqual(rc, 1)
        self.assertIn('не знайдено', out)
        self.assertEqual(self.local_pins()[0]['status'], 'resolved')

    def test_project_unreachable_is_not_called_not_found(self):
        """«Не знайдено» про пін, якого ми не змогли перевірити, — неправда."""
        self.fixture()
        self.net.get_error = OSError('немає VPN')
        rc, out, _ = self.run_main(['resolve', 'ffffff', '--reason', 'x', '--it', '1'])
        self.assertEqual(rc, 1)
        self.assertIn('проєкт недоступний', out)
        self.assertNotIn('не знайдено', out)

    def test_reason_is_required_and_not_blank(self):
        self.fixture()
        raw = self.local_bytes()
        rc, _, err = self.run_main(['resolve', '111111', '--it', '1'])
        self.assertEqual(rc, 2)
        self.assertIn('--reason', err)
        rc, _, err = self.run_main(['resolve', '111111', '--reason', '   ', '--it', '1'])
        self.assertEqual(rc, 2)
        self.assertIn('--reason', err)
        self.assertEqual(self.local_bytes(), raw)

    def test_short_prefix_is_refused(self):
        self.fixture()
        raw = self.local_bytes()
        rc, _, err = self.run_main(['resolve', '11111', '--reason', 'x', '--it', '1'])
        self.assertEqual(rc, 2)
        self.assertIn('коротший', err)
        self.assertEqual(self.local_bytes(), raw)


class ResolveProject(InboxCase):
    PID = 'b7e1c0d2-5f6a-4b7c-8d9e-0f1a2b3c4d5e'

    def setUp(self):
        super().setUp()
        self.set_local([_pin('11111111-aaaa', 'локальний')])
        self.net.project = [_proj(self.PID, 'текст секції'),
                            _proj('c0ffee00-1111', 'інший')]

    def test_patch_has_exact_body_and_headers(self):
        raw = self.local_bytes()
        rc, out, _ = self.run_main(['resolve', 'b7e1c0', '--reason', 'текст оновлено',
                                    '--it', '2'])
        self.assertEqual(rc, 0, out)
        url, key = inbox.supabase_config()
        [call] = self.net.patches()
        self.assertEqual(call['url'], f'{url}/rest/v1/comments?id=eq.{self.PID}')
        self.assertEqual(call['body'], {'status': 'resolved', 'resolved_v': 2,
                                        'resolve_reason': 'текст оновлено'})
        self.assertIs(type(call['body']['resolved_v']), int)
        h = call['headers']
        self.assertEqual(h['apikey'], key)
        self.assertEqual(h['authorization'], f'Bearer {key}')
        self.assertEqual(h['content-type'], 'application/json')
        self.assertEqual(h['prefer'], 'return=minimal')
        self.assertEqual(call['timeout'], 10)
        self.assertIsNotNone(call['context'])
        self.assertEqual(self.local_bytes(), raw, 'проєктний пін не мусить чіпати локальний файл')

    def test_ambiguous_project_prefix_refuses_without_patch(self):
        self.net.project.append(_proj('b7e1c0ff-0000', 'двійник'))
        rc, out, _ = self.run_main(['resolve', 'b7e1c0', '--reason', 'x', '--it', '2'])
        self.assertNotEqual(rc, 0)
        self.assertIn('неоднозначний', out)
        self.assertEqual(self.net.patches(), [])

    def test_patch_failure_makes_exit_nonzero(self):
        def boom(req, timeout=None, context=None):
            if req.get_method() == 'PATCH':
                raise OSError('503')
            return FakeNet.__call__(self.net, req, timeout, context)
        with mock.patch('urllib.request.urlopen', boom):
            rc, out, _ = self.run_main(['resolve', 'b7e1c0', '--reason', 'x', '--it', '2'])
        self.assertEqual(rc, 1)
        self.assertIn('Supabase не прийняв', out)


class DryRun(InboxCase):
    def test_dry_run_writes_nothing_and_says_what_it_would(self):
        self.set_local([_pin('11111111-aaaa', 'локальний')])
        self.net.project = [_proj('b7e1c0d2-0000', 'проєктний')]
        raw = self.local_bytes()
        rc, out, _ = self.run_main(['resolve', '111111', 'b7e1c0', '--reason', 'готово',
                                    '--it', '4', '--dry-run'])
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.local_bytes(), raw)
        self.assertEqual(self.net.patches(), [])
        self.assertIn('resolvedV=4', out)
        self.assertIn('"resolved_v": 4', out)
        self.assertIn('PATCH', out)
        self.assertNotIn(inbox.supabase_config()[1], out, 'ключ у вивід не друкуємо')
        self.assertNotRegex(out, re.compile(r'^✓', re.M))


class TaskFlag(InboxCase):
    """`--task <id>` (fb-07102026-e627c2): `current` один на машину, а паралельна
    сесія його перемикає — тож без явної задачі inbox і `resolve` читали й ПИСАЛИ
    пін чужої задачі. Тут `current` = fx, а працюємо з `other`."""

    def setUp(self):
        super().setUp()
        self.other_dir = os.path.join(self.tmp, 'other')
        os.makedirs(self.other_dir)
        with open(os.path.join(self.other_dir, 'iterations.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'iterations': [{'id': 'it1'}, {'id': 'it4'}]}, f)
        self.other_local = os.path.join(self.other_dir, '.dc-local-comments.json')
        with open(self.other_local, 'w', encoding='utf-8') as f:
            json.dump([_pin('99999999-oooo', 'пін чужої задачі',
                       meta={'version': '4/holovna', 'seq': 1})], f)
        with open(self.tasks_file, encoding='utf-8') as f:
            cfg = json.load(f)
        cfg['tasks']['other'] = {'title': 'Інша', 'dir': self.other_dir,
                                 'comment_project': 'dc/other-inbox-test'}
        # лише реєстр: запису `dir` нема / `dir` є, а теки на диску немає
        self.gone_dir = os.path.join(self.tmp, 'gone-here')
        cfg['tasks']['nodir'] = {'title': 'Без теки'}
        cfg['tasks']['gone'] = {'title': 'Зникла', 'dir': self.gone_dir}
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        self.set_local([_pin('11111111-aaaa', 'пін поточної',
                             meta={'version': '1/holovna', 'seq': 1})])

    def test_without_flag_it_is_the_current_task(self):
        rc, out, _ = self.run_main([])
        self.assertEqual(rc, 0)
        self.assertIn('«Фікстура»', out)
        self.assertIn('пін поточної', out)
        self.assertNotIn('пін чужої задачі', out)

    def test_list_reads_the_named_task_and_its_channel(self):
        rc, out, _ = self.run_main(['--task', 'other'])
        self.assertEqual(rc, 0)
        self.assertIn('«Інша»', out)
        self.assertIn('пін чужої задачі', out)
        self.assertNotIn('пін поточної', out)
        urls = ' '.join(c['url'] for c in self.net.calls)
        self.assertIn('other-inbox-test', urls, 'канал Supabase — не названої задачі')
        self.assertNotIn('fixture-inbox-test', urls)

    def test_resolve_closes_the_pin_of_the_named_task_only(self):
        current_before = self.local_bytes()
        rc, out, _ = self.run_main(['--task', 'other', 'resolve', '999999',
                                    '--reason', 'готово', '--it', '4'])
        self.assertEqual(rc, 0, out)
        with open(self.other_local, encoding='utf-8') as f:
            got = json.load(f)[0]
        self.assertEqual(got['status'], 'resolved')
        self.assertEqual(got['resolvedV'], 4)
        self.assertEqual(self.local_bytes(), current_before,
                         'пін ПОТОЧНОЇ задачі переписано')

    def test_resolve_default_iteration_is_the_named_tasks(self):
        """Без `--it` номер береться з робочої ітерації НАЗВАНОЇ задачі (it4), а не
        поточної (it1)."""
        rc, out, _ = self.run_main(['--task', 'other', 'resolve', '999999',
                                    '--reason', 'готово'])
        self.assertEqual(rc, 0, out)
        self.assertIn('Іт.4', out)

    def test_resolve_does_not_find_a_pin_of_the_current_task(self):
        """Пін поточної задачі, названий префіксом, коли працюємо в `other`, —
        «не знайдено», а не тихе закриття чужого."""
        raw = self.local_bytes()
        rc, out, _ = self.run_main(['--task', 'other', 'resolve', '111111',
                                    '--reason', 'x', '--it', '1'])
        self.assertEqual(rc, 1)
        self.assertEqual(self.local_bytes(), raw)

    def test_unknown_task_is_exit_2_and_says_nothing_about_current(self):
        raw = self.local_bytes()
        rc, out, err = self.run_main(['--task', 'nope'])
        self.assertEqual(rc, 2)
        self.assertIn("error: немає задачі 'nope' у tasks.json", err)
        self.assertEqual(out, '', 'про поточну задачу не сказано ні слова')
        self.assertEqual(self.net.calls, [], 'мережу чіпали, хоча задачі немає')
        rc, out, err = self.run_main(['--task', 'nope', 'resolve', '111111',
                                      '--reason', 'x', '--it', '1'])
        self.assertEqual(rc, 2)
        self.assertIn("error: немає задачі 'nope' у tasks.json", err)
        self.assertEqual(out, '')
        self.assertEqual(self.net.calls, [])
        self.assertEqual(self.local_bytes(), raw, 'resolve змінив пін поточної задачі')

    def test_task_missing_on_this_machine_is_exit_2_not_a_traceback(self):
        """Задача є в реєстрі, теки тут нема: раніше `KeyError: 'dir'`, а з `dir`
        у нікуди — порожній інбокс, тобто «пінів нема», хоч ми їх просто не
        бачимо. Тепер — окрема помилка, код 2; нічого не читаємо й не пишемо."""
        raw = self.local_bytes()
        for tid in ('nodir', 'gone'):
            for argv in (['--task', tid],
                         ['--task', tid, 'resolve', '111111', '--reason', 'x',
                          '--it', '1']):
                with self.subTest(tid=tid, argv=argv):
                    rc, out, err = self.run_main(argv)
                    self.assertEqual(rc, 2)
                    self.assertIn(f"error: задачі '{tid}' немає на цій машині "
                                  '(є в реєстрі, теки нема)', err)
                    self.assertNotIn('Traceback', err)
                    self.assertEqual(out, '', 'про поточну задачу не сказано ні слова')
                    self.assertEqual(self.net.calls, [], 'мережу чіпали, хоча теки нема')
        self.assertFalse(os.path.exists(self.gone_dir), 'теку створено')
        self.assertEqual(self.local_bytes(), raw)

    def test_where_opens_the_named_task_not_the_current(self):
        """Браузер для `--where` ходить на канвас за `/commented?…` — без префікса
        `/t/<id>/` там відкрилась би ПОТОЧНА задача машини."""
        urls = []

        def fake(cmd, **kw):
            urls.append(cmd[cmd.index('--url') + 1])
            return mock.Mock(returncode=0, stdout='{}', stderr='')
        with mock.patch.object(inbox.subprocess, 'run', side_effect=fake):
            self.run_main(['--task', 'other', '--where'])
            self.run_main(['--where'])
        self.assertTrue(urls[0].endswith('/t/other'), urls[0])
        self.assertNotIn('/t/', urls[1])

    def test_close_hint_repeats_the_flag(self):
        """Підказку «Закрити: …» копіюють дослівно — без `--task` вона закрила б
        пін поточної задачі."""
        _, named, _ = self.run_main(['--task', 'other'])
        self.assertIn('python3 bin/inbox.py --task other resolve <id>', named)
        _, plain, _ = self.run_main([])
        self.assertIn('python3 bin/inbox.py resolve <id>', plain)
        self.assertNotIn('--task', plain)

    def test_flag_is_in_help_before_the_subcommand(self):
        rc, out, _ = self.run_main(['-h'])
        self.assertEqual(rc, 0)
        self.assertIn('--task', out)
        self.assertIn('паралельних сесій', out)

    def test_descriptions_do_not_claim_the_task_is_always_the_current(self):
        """Описи казали «поточної задачі», хоч із `--task` це названа."""
        for argv in (['-h'], ['resolve', '-h']):
            with self.subTest(argv=argv):
                rc, out, _ = self.run_main(argv)
                self.assertEqual(rc, 0)
                flat = ' '.join(out.split())
                self.assertIn('поточної (або названої --task) задачі', flat)
                self.assertNotIn('поточної задачі', flat)

    def test_flag_after_the_subcommand_is_an_error_not_silence(self):
        """`--task` — глобальний, ПЕРЕД підкомандою; після неї argparse відмовляє
        голосно (код 2), а не мовчки закриває пін поточної задачі."""
        raw = self.local_bytes()
        rc, _, err = self.run_main(['resolve', '111111', '--reason', 'x', '--it', '1',
                                    '--task', 'other'])
        self.assertEqual(rc, 2)
        self.assertIn('--task', err)
        self.assertEqual(self.local_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
