"""Агент читає й закриває проєктні коментарі через модуль ролі `comments` (етап 2b-2, Task 4).

`bin/inbox.py` (читання, `resolve`), `bin/state.py` (лічильник відкритих) і маршрут `/comments` вирішують, ЗВІДКИ брати
командні піни, за ПОСТАЧАЛЬНИКОМ ролі `comments` ПРОСТОРУ задачі (`serve.ProjectComments`, простір — явним аргументом), а
не за `spaces.integrations_on()`:

    постачальник     читання                                 закриття
    Module           `list` модуля → форма рядків REST       `resolve` модуля
    'legacy'         як було (зашитий Supabase ЛІГА)         як було (`PATCH`)
    None             «командних коментарів нема» (409)       —
    ModuleError      лише локальні піни + повідомлення       —       (НІКОЛИ не зашитий Supabase)

Що доводиться:
  * `inbox` у просторі з модулем показує його піни (в тій самій формі, що з Supabase) і закриває їх через `resolve`;
  * ЛІГА без модуля, «нікого», зламаний модуль, нечитабельний `space.json` — кожен окремо, і жодного запиту до спільного
    Supabase там, де його бути не може (розтяжка `urllib.request.urlopen` + сокетів 127.0.0.1);
  * зіпсована відповідь модуля (не список, не обʼєкти, дублікати, величезний список, керівні символи й сурогати, чужі типи
    в `fp`/`meta`) не валить `inbox` і не пише в термінал агента керівних послідовностей;
  * маршрут `/comments` — та сама матриця через справжній HTTP;
  * `state.py` — той самий вибір для лічильника відкритих.

⛔ Ізоляція: власні тимчасові `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`; справжній `~/.deai` стереже `spaces_guard`. Мережа — лише
127.0.0.1 (сервіс `memo` у процесі й власний сервер тесту), `urlopen` підмінено на запис.
"""
import contextlib
import http.client
import io
import json
import os
import re
import sys
import threading
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.join(ROOT, 'bin'))
sys.path.insert(0, _HERE)
import deai_modules as dm  # noqa: E402
import inbox  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
import state  # noqa: E402
import test_comments_role as tcr  # noqa: E402  — `PagesEnv` (два простори й сервер), `MemoService`, `loopback_only`
import test_modules as tm  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


# ----------------------------------------------------------------------------------------------- фікстури

def cl(cid, text, status='open', seq=1, **kw):
    """Коментар у формі CommentLayer — те, що віддає `list` модуля."""
    c = {'id': cid, 'author': 'Олена', 'text': text, 'status': status,
         'fp': {'tag': 'button', 'text': text, 'path': ['div[1]', 'button[0]']},
         'htmlSnapshot': {'text': text, 'outerHTML': '<button class="btn primary">Купити</button>'},
         'meta': {'version': '2/me--welcome', 'seq': seq, 'viewport': {'w': 375, 'h': 800},
                  'ctx': {'heading': 'Оплата'}, 'shot': 'data:image/jpeg;base64,' + 'A' * 3000},
         'bornV': 2, 'resolvedV': None, 'resolveReason': None, 'ts': '19.10.2026 10:00'}
    c.update(kw)
    return c


def rest(cid, text, status='open', seq=1):
    """Той самий пін у формі рядка REST ЛІГА (`serve.supabase_pins`): snake_case."""
    return {'id': cid, 'text': text, 'status': status, 'author': 'Олена', 'ts': '19.10.2026 10:00',
            'meta': {'version': '2/me--welcome', 'seq': seq, 'viewport': {'w': 375, 'h': 800},
                     'ctx': {'heading': 'Оплата'}},
            'born_v': 2, 'fp': {'tag': 'button', 'text': text, 'path': ['div[1]', 'button[0]']},
            'html_snapshot': {'text': text, 'outerHTML': '<button class="btn primary">Купити</button>'},
            'resolved_v': None, 'resolve_reason': None}


class _Resp:
    def __init__(self, body=b'', status=200):
        self._body, self.status = body, status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Net:
    """Замість `urllib.request.urlopen` (шлях ЛІГА `supabase_pins`/`patch_project_pin`): пише кожен виклик і віддає рядки.
    Модуль `memo-comments` ходить своїм `build_opener().open`, тож на цю підміну не потрапляє."""

    def __init__(self):
        self.calls, self.rows = [], []

    def __call__(self, req, timeout=None, context=None):
        self.calls.append((req.get_method(), req.full_url))
        if req.get_method() == 'GET':
            return _Resp(json.dumps(self.rows).encode('utf-8'))
        return _Resp(b'', 204)


#: Модуль-фікстура, чия відповідь `list` — довільний JSON із файла `answer.json` у теці простору (а `resolve` пише в
#: `resolved.log`): так відповідь можна зіпсувати як завгодно, а запис модуля лишається справжнім.
ANSWER_SERVER = tm.CHECK_ONLY + (
    'import json, os\n'
    'def client_config(ctx):\n    return {}\n'
    'def list(ctx, channel):\n'
    '    with open(os.path.join(ctx["space"]["path"], "answer.json"), encoding="utf-8") as f:\n'
    '        return json.loads(f.read())\n'
    'def resolve(ctx, channel, id, reason):\n'
    '    with open(os.path.join(ctx["space"]["path"], "resolved.log"), "a", encoding="utf-8") as f:\n'
    '        f.write(json.dumps([channel, id, reason]) + "\\n")\n')

CONTROL = re.compile('[\x00-\x08\x0b-\x1f\x7f-\x9f\u200e\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069]')


def run_cli(main, argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class AgentEnv(tcr.CommentsEnv):
    """Два простори (`plain` без інтеграцій, `liga` з інтеграціями) з РІЗНИМИ задачами (`px`, `lx`: `--task` не мусить бути
    неоднозначним), сервіс `memo` на 127.0.0.1, запис шляху ЛІГА (`Net`). Оточення — власне (шар просторів увімкнено, мережа
    — лише 127.0.0.1, особа машини порожня)."""

    def setUp(self):
        super().setUp()
        for key, val in (('DC_NO_OVERVIEW', '1'), ('DC_IDENTITY_NAME', ''), ('DC_IDENTITY_EMAIL', '')):
            prior = os.environ.get(key)
            os.environ[key] = val
            self.addCleanup(lambda k=key, v=prior: os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v))
        # Простори пишуться в тимчасовий `DEAI_HOME`, а не у справжній `~/.deai`: `Env.setUp` уже виставив його, тут він
        # підтверджений явно (так вимагає охоронець `test_serve.TestsCannotWriteLiveConfig`); оточення відновлює `Env.tearDown`.
        os.environ['DEAI_HOME'] = self.deai
        tcr.loopback_only(self)
        self.plain = self.new_space('Plain')
        self.liga = self.new_space('Liga', integrations=True)
        self.write_task(self.plain, 'px')
        self.write_task(self.liga, 'lx')
        self.net = Net()
        patch = mock.patch('urllib.request.urlopen', self.net)
        patch.start()
        self.addCleanup(patch.stop)
        self.svc = tcr.MemoService()
        self.addCleanup(self.svc.stop)
        self.use(self.plain)

    write_task = staticmethod(tcr.PagesEnv.write_task)

    def use(self, sp):
        spaces.switch_space(sp['id'])
        self.cur = sp

    def enable(self, sp, endpoint='http://127.0.0.1:9', secrets=None):
        """`memo-comments` у `sp` (токен непублічний, ключ публічний). Модуль ставиться один раз на тест."""
        if not os.path.isdir(os.path.join(self.mods, 'memo-comments')):
            self.install_memo()
        dm.write_module_state(sp, 'memo-comments', enabled=True, settings={'endpoint': endpoint})
        dm.write_secrets(sp['id'], 'memo-comments',
                         {'token': tcr.TOKEN, 'pubkey': tcr.PUBKEY} if secrets is None else secrets)
        return dm.provider('comments', sp)

    # --- допоміжне ---
    def inbox(self, argv):
        return run_cli(inbox.main, argv)

    def state(self, argv=()):
        patches = [mock.patch.object(state, '_registry_line', lambda cfg: ''),
                   mock.patch.object(state, 'find_canvas_port', lambda *a, **k: 8766)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return run_cli(state.main, list(argv))

    def chan(self, sp, tid, internal=False):
        return dm.channel_for(sp, tid, internal)

    def pc(self, sp, request=None):
        """`ProjectComments(sp)` так, як його будує запит чи команда CLI: простір запиту ЗАФІКСОВАНО (без цього
        `comments_provider` ігнорує `space` — шлях інструментів ЛІГА без простору). `request` — інший простір запиту."""
        with spaces.request_space(sp['id'] if request is None and sp else request):
            return serve.ProjectComments(sp)

    def seed(self, sp, tid, comments):
        self.svc.comments[self.chan(sp, tid)] = comments

    def enable_memo_in(self, sp):
        return self.enable(sp, self.svc.url)

    def answer(self, sp, obj, raw=None):
        """Модуль `answer` у `sp`; його `list` віддасть `obj` (чи сирий текст `raw`, напр. з `NaN`)."""
        if not os.path.isdir(os.path.join(self.mods, 'answer')):
            self.mkcm('answer', server=ANSWER_SERVER, settings=[])
            dm.write_module_state(sp, 'answer', enabled=True, settings={})
        tcr._write(os.path.join(sp['path'], 'answer.json'), raw if raw is not None else json.dumps(obj))

    def pin_lines(self, out):
        return [ln for ln in out.splitlines() if ln.startswith('      • ') or ln.startswith('          ↳ ')]

    def break_module(self, sp):
        self.enable_memo_in(sp)
        os.remove(os.path.join(self.mods, 'memo-comments', 'adapter.js'))          # оголошений файл зник → `error`
        self.assertEqual(dm.catalog()['memo-comments'].status, 'error')

    def assert_no_legacy(self):
        self.assertEqual(self.net.calls, [], 'запит до зашитого Supabase ЛІГА')

    def set_local(self, sp, tid, pins):
        tcr._write(os.path.join(sp['path'], tid, '.dc-local-comments.json'), json.dumps(pins, ensure_ascii=False))

    def local_pin(self, pid, text, status='open'):
        return {'id': pid, 'author': 'Ольга', 'text': text, 'status': status, 'fp': {}, 'htmlSnapshot': None,
                'meta': {'version': '1'}, 'bornV': 1, 'resolvedV': None, 'resolveReason': None,
                'ts': '19.10.2026 09:00'}


# ------------------------------------------------------------------------------------ inbox: простір із модулем

class InboxModuleTest(AgentEnv):
    def test_inbox_lists_the_project_pins_of_the_module_in_the_same_form_as_supabase_ones(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7),
                                     cl('c0ffee02-bbbb', 'Старе', status='resolved', seq=3, resolvedV=2)])
        rc, out, err = self.inbox([])
        self.assertEqual((rc, err), (0, ''), out)
        self.assertIn('-- ПРОЄКТ (колеги + історія, модуль memo-comments) --', out)
        self.assertIn('• P#7 [2/me--welcome] Кнопку вирівняти  [c0ffee01 · Олена]', out)
        self.assertIn('↳ де: розділ «Оплата»', out)
        self.assertIn('↳ ширина: мобільна · 375×800', out)
        self.assertIn('↳ якір: <button> «Кнопку вирівняти»  · div[1] > button[0]', out)
        self.assertIn('↳ селектор: .btn.primary', out)
        self.assertIn('↳ html: <button class="btn primary">Купити</button>', out)
        self.assertIn('проєкт: (+ 1 вирішених в історії)', out)
        self.assertIn('Разом до відпрацювання: 0 локальних + 1 проєктних', out)
        self.assertNotIn('Старе', out)
        # читання пішло в модуль: канал простору, токен — лише в заголовку, і жодного запиту до Supabase ЛІГА
        method, path, auth, _ = self.svc.log[-1]
        self.assertEqual((method, path, auth), ('GET', f'/c/deai%2F{self.plain["id"]}%2Fpx', 'Bearer ' + tcr.TOKEN))
        self.assert_no_legacy()
        self.assertNotIn(serve.SUPABASE_URL, out)
        self.assertNotIn(tcr.TOKEN, out)

    def test_the_pin_lines_are_identical_to_those_of_the_same_pin_from_supabase(self):
        """Той самий пін: з модуля (форма CommentLayer) і з REST ЛІГА (форма рядка) друкується ПОРЯД ТАК САМО."""
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7)])
        _, module_out, _ = self.inbox([])
        self.use(self.liga)
        self.net.rows = [rest('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7)]
        _, legacy_out, _ = self.inbox([])
        self.assertEqual(len(self.net.calls), 1, 'контроль: ЛІГА питає свій Supabase')
        self.assertTrue(self.pin_lines(module_out))
        self.assertEqual(self.pin_lines(module_out), self.pin_lines(legacy_out))

    def test_resolve_reaches_the_module_and_the_pin_shows_as_resolved(self):
        self.enable_memo_in(self.plain)
        chan = self.chan(self.plain, 'px')
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'Кнопку вирівняти'), cl('c0ffee02-bbbb', 'Інше')])
        rc, out, err = self.inbox(['resolve', 'c0ffee01', '--reason', 'кнопку вирівняно'])
        self.assertEqual((rc, err), (0, ''), out)
        self.assertIn('✓ c0ffee01 закрито (проєкт): «кнопку вирівняно»', out)
        self.assertNotIn('Іт.', out, 'номер ітерації модулю не передається — і про нього не кажемо')
        method, path, auth, body = self.svc.log[-1]
        self.assertEqual((method, path, auth, body),
                         ('POST', f'/c/deai%2F{self.plain["id"]}%2Fpx/resolve', 'Bearer ' + tcr.TOKEN,
                          {'id': 'c0ffee01-aaaa', 'reason': 'кнопку вирівняно'}))
        self.assertEqual([(c['id'], c['status']) for c in self.svc.comments[chan]],
                         [('c0ffee01-aaaa', 'resolved'), ('c0ffee02-bbbb', 'open')])
        self.assert_no_legacy()
        _, out, _ = self.inbox([])
        self.assertIn('проєкт — 1 відкритих', out)
        self.assertIn('проєкт: (+ 1 вирішених в історії)', out)
        self.assertNotIn('Кнопку вирівняти', out)
        # повтор: вже закритий — пропуск, а не друге закриття
        posts = len([e for e in self.svc.log if e[0] == 'POST'])
        rc, out, _ = self.inbox(['resolve', 'c0ffee01', '--reason', 'ще раз'])
        self.assertEqual(rc, 0, out)
        self.assertIn('⏭ c0ffee01: уже закритий («кнопку вирівняно»)', out)
        self.assertEqual(len([e for e in self.svc.log if e[0] == 'POST']), posts)

    def test_resolve_dry_run_writes_nothing_anywhere(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'Кнопку вирівняти')])
        rc, out, _ = self.inbox(['resolve', 'c0ffee01', '--reason', 'готово', '--dry-run'])
        self.assertEqual(rc, 0, out)
        self.assertIn('[dry-run] модуль memo-comments: resolve ' + self.chan(self.plain, 'px') + ' c0ffee01-aaaa', out)
        self.assertEqual([e[0] for e in self.svc.log if e[0] == 'POST'], [])
        self.assert_no_legacy()

    def test_local_pins_are_resolved_without_touching_the_module(self):
        self.enable_memo_in(self.plain)
        self.set_local(self.plain, 'px', [self.local_pin('a1b2c3d4-0000', 'Локальне')])
        rc, out, _ = self.inbox(['resolve', 'a1b2c3', '--reason', 'готово'])
        self.assertEqual(rc, 0, out)
        self.assertIn('закрито (локальний', out)
        self.assertEqual(self.svc.log, [])

    def test_a_dead_module_service_is_a_message_never_the_shared_supabase(self):
        self.enable_memo_in(self.plain)
        self.set_local(self.plain, 'px', [self.local_pin('a1b2c3d4-0000', 'Локальне')])
        self.svc.stop()
        rc, out, _ = self.inbox([])
        self.assertEqual(rc, 0, out)
        self.assertIn('проєкт: (не дістати: module-error', out)
        self.assertIn('Локальне', out)
        self.assertIn('Разом до відпрацювання: 1 локальних + 0 проєктних', out)
        self.assertNotIn(tcr.TOKEN, out)
        self.assert_no_legacy()

    def test_a_module_that_refuses_to_resolve_is_reported_and_exits_nonzero(self):
        self.mkcm('refusing', settings=[], server=tm.CHECK_ONLY + (
            'def client_config(ctx):\n    return {}\n'
            'def list(ctx, channel):\n    return [{"id": "c0ffee01-aaaa", "text": "Кнопку вирівняти"}]\n'
            'def resolve(ctx, channel, id, reason):\n    raise RuntimeError("сервіс відмовив")\n'))
        dm.write_module_state(self.plain, 'refusing', enabled=True, settings={})
        rc, out, _ = self.inbox(['resolve', 'c0ffee01', '--reason', 'готово'])
        self.assertEqual(rc, 1, out)
        self.assertIn('✗ c0ffee01: модуль refusing не прийняв (module-error: RuntimeError: сервіс відмовив)', out)
        self.assertNotIn('✓', out)
        self.assert_no_legacy()

    def test_a_named_task_in_a_module_space_uses_the_module_while_the_current_space_is_the_league_one(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7)])
        self.use(self.liga)                                # поточний простір машини — ЛІГА (шлях Supabase)
        rc, out, err = self.inbox(['--task', 'px'])
        self.assertEqual((rc, err), (0, ''), out)
        self.assertIn('Кнопку вирівняти', out)
        self.assertIn('модуль memo-comments', out)
        self.assert_no_legacy()
        rc, out, _ = self.inbox(['--task', 'px', 'resolve', 'c0ffee01', '--reason', 'готово'])
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.svc.comments[self.chan(self.plain, 'px')][0]['status'], 'resolved')
        self.assert_no_legacy()

    def test_a_league_space_with_an_enabled_module_reads_the_module_not_the_league_service(self):
        self.enable_memo_in(self.liga)
        self.seed(self.liga, 'lx', [cl('c0ffee01-aaaa', 'Кнопку вирівняти')])
        self.use(self.liga)
        rc, out, _ = self.inbox([])
        self.assertEqual(rc, 0, out)
        self.assertIn('модуль memo-comments', out)
        self.assertIn('Кнопку вирівняти', out)
        self.assert_no_legacy()

    def test_a_task_id_with_a_slash_is_a_module_error_not_a_crash(self):
        """Канал будує ядро (`channel_for`): id задачі з `/` каналу не дає — це відмова модуля, а не падіння."""
        self.enable_memo_in(self.plain)
        pc = self.pc(self.plain)
        with self.assertRaises(dm.ModuleError):
            pc.pins({}, 'a/b')
        self.assertEqual(self.svc.log, [])


# ------------------------------------------------------------------------- inbox: ЛІГА, «нікого», зламане

class InboxOtherProvidersTest(AgentEnv):
    def test_the_league_path_is_unchanged_and_never_asks_a_module(self):
        self.use(self.liga)
        self.net.rows = [rest('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7)]
        rc, out, _ = self.inbox([])
        self.assertEqual(rc, 0, out)
        self.assertIn('-- ПРОЄКТ (колеги + історія, Supabase) --', out)
        self.assertIn('• P#7 [2/me--welcome] Кнопку вирівняти  [c0ffee01 · Олена]', out)
        self.assertEqual(self.net.calls, [('GET', f'{serve.SUPABASE_URL}/rest/v1/comments?select=id,text,status,author,'
                                                  'ts,meta,born_v,fp,html_snapshot,resolved_v,resolve_reason'
                                                  '&project_id=eq.dc%2Flx')])
        self.assertEqual(self.svc.log, [])
        rc, out, _ = self.inbox(['resolve', 'c0ffee01', '--reason', 'готово'])
        self.assertEqual(rc, 0, out)
        self.assertIn('✓ c0ffee01 закрито (проєкт, Іт.1): «готово»', out)
        self.assertEqual([m for m, _ in self.net.calls], ['GET', 'GET', 'PATCH'])
        self.assertEqual(self.svc.log, [])

    def test_a_space_without_a_provider_has_no_team_comments_and_asks_nobody(self):
        self.set_local(self.plain, 'px', [self.local_pin('a1b2c3d4-0000', 'Локальне')])
        rc, out, _ = self.inbox([])
        self.assertEqual(rc, 0, out)
        self.assertIn('командних коментарів у цьому просторі нема', out)
        self.assertNotIn('не дістати', out)
        self.assertIn('Локальне', out)
        self.assertIn('Разом до відпрацювання: 1 локальних + 0 проєктних', out)
        self.assertEqual(self.svc.log, [])
        self.assert_no_legacy()
        rc, out, _ = self.inbox(['resolve', 'abcdef12', '--reason', 'r'])
        self.assertEqual(rc, 1)
        self.assertIn('не знайдено серед пінів поточної задачі', out)
        self.assert_no_legacy()

    def assert_local_only(self, sp, tid, code, message=None):
        self.use(sp)
        self.set_local(sp, tid, [self.local_pin('a1b2c3d4-0000', 'Локальне')])
        rc, out, _ = self.inbox([])
        self.assertEqual(rc, 0, out)
        self.assertIn(f'проєкт: (не дістати: {code}', out)
        if message:
            self.assertIn(message, out)
        self.assertIn('Локальне', out)
        self.assertIn('Разом до відпрацювання: 1 локальних + 0 проєктних', out)
        self.assertNotIn(serve.SUPABASE_URL, out)
        self.assert_no_legacy()
        self.assertEqual(self.svc.log, [], 'зламаний модуль не питають')
        # закриття: локальний пін — без жодного проєкту; проєктний префікс — «проєкт недоступний», не Supabase
        rc, out, _ = self.inbox(['resolve', 'a1b2c3', '--reason', 'готово'])
        self.assertEqual(rc, 0, out)
        self.assertIn('закрито (локальний', out)
        rc, out, _ = self.inbox(['resolve', 'ffeedd11', '--reason', 'готово'])
        self.assertEqual(rc, 1, out)
        self.assertIn(f'проєкт недоступний ({code}', out)
        self.assert_no_legacy()

    def test_a_league_space_with_a_lost_module_is_local_only_with_a_message_and_no_shared_request(self):
        self.break_module(self.liga)
        self.assert_local_only(self.liga, 'lx', 'module-error', dm.COMMENTS_MODULE_BROKEN)

    def test_a_league_space_with_an_unreadable_space_json_is_local_only_with_a_message(self):
        tcr._write(self.space_json(self.liga), '{broken')
        self.assert_local_only(self.liga, 'lx', 'space-json-unreadable')

    def test_a_plain_space_with_an_unreadable_space_json_is_local_only_with_a_message(self):
        tcr._write(self.space_json(self.plain), '{broken')
        self.assert_local_only(self.plain, 'px', 'space-json-unreadable')

    def test_a_disabled_entry_in_a_league_space_returns_the_league_path(self):
        """Контроль: людина вимкнула модуль — це вже не помилка, а шлях ЛІГА (як у сторінках)."""
        self.break_module(self.liga)
        dm.write_module_state(self.liga, 'memo-comments', enabled=False)
        self.use(self.liga)
        self.net.rows = [rest('c0ffee01-aaaa', 'Кнопку вирівняти')]
        rc, out, _ = self.inbox([])
        self.assertEqual(rc, 0, out)
        self.assertIn('(колеги + історія, Supabase)', out)
        self.assertEqual(len(self.net.calls), 1)

    def test_a_module_that_does_not_answer_in_time_is_a_message(self):
        self.mkcm('slow', settings=[], server=tm.CHECK_ONLY + (
            'import time\ndef client_config(ctx):\n    return {}\n'
            'def list(ctx, channel):\n    time.sleep(3)\n    return []\n'
            'def resolve(ctx, channel, id, reason):\n    return None\n'))
        dm.write_module_state(self.plain, 'slow', enabled=True, settings={})
        with mock.patch.object(dm, 'COMMENTS_TIMEOUT', 0.3):
            rc, out, _ = self.inbox([])
        self.assertEqual(rc, 0, out)
        self.assertIn('проєкт: (не дістати: check-timeout', out)
        self.assert_no_legacy()


# --------------------------------------------------------------------------- зіпсована відповідь модуля

class MalformedAnswerTest(AgentEnv):
    def run_list(self, obj=None, raw=None):
        self.answer(self.plain, obj, raw)
        rc, out, err = self.inbox([])
        self.assertEqual((rc, err), (0, ''), out)
        self.assertIsNone(CONTROL.search(out), 'керівний символ у виводі агента: ' + repr(CONTROL.search(out)))
        out.encode('utf-8')                                    # сурогат у виводі — `UnicodeEncodeError` у терміналі
        self.assert_no_legacy()
        return out

    def test_an_answer_that_is_not_a_list_is_a_message(self):
        for obj in ({'comments': []}, 'text', None, 42, True):
            with self.subTest(obj=obj):
                out = self.run_list(obj)
                self.assertIn('проєкт: (не дістати: module-error', out)
                self.assertIn('must answer list() with a list', out)
                self.assertIn('Разом до відпрацювання: 0 локальних + 0 проєктних', out)

    def test_items_that_are_not_comments_are_skipped_and_counted(self):
        good = cl('c0ffee01-aaaa', 'Добре', seq=7)
        out = self.run_list([good, 'рядок', 7, None, ['x'], {}, {'id': ''}, {'id': 5, 'text': 'x'},
                             {'id': 'a' * 201, 'text': 'довгий id'}, {'id': 'ab\x1bcd', 'text': 'esc в id'},
                             {'id': '   ', 'text': 'пробіли'}, {'text': 'без id'}])
        self.assertIn('• P#7 [2/me--welcome] Добре  [c0ffee01 · Олена]', out)
        self.assertIn('⚠ відповідь модуля коментарів неповна: пропущено 11 зіпсованих елементів', out)
        self.assertIn('Разом до відпрацювання: 0 локальних + 1 проєктних', out)

    def test_a_duplicate_id_keeps_the_first_pin(self):
        out = self.run_list([cl('c0ffee01-aaaa', 'Перший'), cl('c0ffee01-aaaa', 'Другий')])
        self.assertIn('Перший', out)
        self.assertNotIn('Другий', out)
        self.assertIn('пропущено 1 зіпсованих елементів', out)

    def test_a_huge_list_is_capped_and_counted(self):
        with mock.patch.object(serve, 'MAX_AGENT_COMMENTS', 3):
            out = self.run_list([cl(f'c0ffee0{i}-aaaa', f'Пін {i}', seq=i) for i in range(1, 8)])
        self.assertIn('відкинуто 4 понад межу', out)
        self.assertIn('Разом до відпрацювання: 0 локальних + 3 проєктних', out)

    def test_control_characters_surrogates_and_overlong_text_never_reach_the_terminal(self):
        evil = cl('c0ffee01-aaaa', 'червоний\x1b[31m текст\x1b[0m\x9b2J\u202eфальш\ud800 кінець ' + 'я' * 20000,
                  author='Хакер\x07\x1b]0;title\x07', ts='19.10.2026 10:00\x00')
        out = self.run_list([evil])
        self.assertIn('червоний[31m текст[0m2Jфальш кінець ', out)
        self.assertNotIn('я' * 10001, out, 'текст обрізаний до 10000')
        self.assertIn('Хакер]0;title', out)

    def test_foreign_types_in_the_fields_inbox_dereferences_do_not_crash_it(self):
        weird = cl('c0ffee01-aaaa', 'Дивний', fp={'tag': 7, 'text': 9, 'path': {'a': 1}},
                   meta={'version': {'x': 1}, 'seq': [1], 'viewport': 'wide', 'ctx': 'нічого'},
                   htmlSnapshot='<b>рядок</b>', bornV='abc', resolvedV=[1], status=7)
        weirder = cl('c0ffee02-bbbb', 'Ще', fp={'path': [1, None, 'div[2]'], 'tag': 'a'}, meta=[1, 2],
                     htmlSnapshot={'outerHTML': 5, 'text': None}, ts=12345, author=None)
        out = self.run_list([weird, weirder])
        self.assertIn('Дивний', out)
        self.assertIn('Ще', out)
        self.assertIn('Разом до відпрацювання: 0 локальних + 2 проєктних', out)

    def test_nan_giant_numbers_and_deep_nesting_are_neutralised(self):
        deep = {}
        cur = deep
        for _ in range(40):
            cur['x'] = {}
            cur = cur['x']
        pin = cl('c0ffee01-aaaa', 'Числа', meta={'version': '1', 'nan': 1, 'deep': deep, 'big': 1})
        raw = json.dumps([pin]).replace('"nan": 1', '"nan": NaN').replace('"big": 1', '"big": ' + '9' * 400)
        out = self.run_list(raw=raw)
        self.assertIn('Числа', out)
        pins = serve.agent_pins(json.loads(raw))
        json.dumps(pins, allow_nan=False)                      # те, що піде в JSON, — строгий JSON
        self.assertIsNone(pins[0]['meta']['nan'])
        self.assertIsNone(pins[0]['meta']['big'])

    def test_a_status_other_than_resolved_is_open(self):
        out = self.run_list([cl('c0ffee01-aaaa', 'Відкрите', status='done'),
                             cl('c0ffee02-bbbb', 'Закрите', status='resolved')])
        self.assertIn('проєкт — 1 відкритих', out)
        self.assertIn('Відкрите', out)


class AgentPinUnitTest(unittest.TestCase):
    def test_the_comment_layer_shape_becomes_the_supabase_row_shape(self):
        row = serve.agent_pin(cl('c0ffee01-aaaa', 'Текст', seq=4, resolvedV=3, resolveReason='зроблено',
                                 status='resolved'))
        self.assertEqual(set(row), {'id', 'text', 'status', 'author', 'ts', 'meta', 'born_v', 'fp', 'html_snapshot',
                                    'resolved_v', 'resolve_reason'})
        self.assertEqual((row['id'], row['text'], row['status'], row['author'], row['ts']),
                         ('c0ffee01-aaaa', 'Текст', 'resolved', 'Олена', '19.10.2026 10:00'))
        self.assertEqual((row['born_v'], row['resolved_v'], row['resolve_reason']), (2, 3, 'зроблено'))
        self.assertEqual(row['fp'], {'tag': 'button', 'text': 'Текст', 'path': ['div[1]', 'button[0]']})
        self.assertEqual(row['html_snapshot'], {'text': 'Текст', 'outerHTML': '<button class="btn primary">Купити</button>'})
        self.assertEqual(row['meta'], {'version': '2/me--welcome', 'seq': 4, 'viewport': {'w': 375, 'h': 800},
                                       'ctx': {'heading': 'Оплата'}})
        self.assertNotIn('shot', row['meta'], 'знімок base64 агентові не потрібен')

    def test_versions_are_small_non_negative_integers_or_none(self):
        for given, want in ((2, 2), ('7', 7), ('x', None), (-1, None), (True, None), (2 ** 40, None), (None, None),
                            ('١٢', None)):
            with self.subTest(given=given):
                self.assertEqual(serve.agent_pin(cl('c0ffee01-aaaa', 't', bornV=given))['born_v'], want)

    def test_a_missing_optional_part_is_none_not_a_crash(self):
        row = serve.agent_pin({'id': 'c0ffee01-aaaa'})
        self.assertEqual((row['text'], row['status'], row['author'], row['ts'], row['meta'], row['fp'],
                          row['html_snapshot'], row['born_v'], row['resolve_reason']),
                         ('', 'open', '', '', {}, None, None, None, None))

    def test_the_list_is_validated_as_a_whole(self):
        pins = serve.agent_pins([cl('a1', 'один'), cl('a2', 'два')])
        self.assertIsInstance(pins, serve.ModulePins)
        self.assertEqual([p['id'] for p in pins], ['a1', 'a2'])
        self.assertEqual((pins.skipped, pins.truncated, pins.note()), (0, 0, ''))
        for bad in (None, {}, 'x', (cl('a1', 'x'),)):
            with self.subTest(bad=bad), self.assertRaises(dm.ModuleError) as cm:
                serve.agent_pins(bad)
            self.assertEqual(cm.exception.code, 'module-error')

    def test_the_real_cap_is_5000_pins(self):
        pins = serve.agent_pins([{'id': f'p{i}', 'text': 't'} for i in range(serve.MAX_AGENT_COMMENTS + 3)])
        self.assertEqual((len(pins), pins.truncated), (serve.MAX_AGENT_COMMENTS, 3))
        self.assertEqual(serve.MAX_AGENT_COMMENTS, 5000)

    def test_the_byte_budget_stops_a_list_of_fat_pins(self):
        fat = [{'id': f'p{i}', 'text': 'я' * 10000, 'htmlSnapshot': {'outerHTML': 'x' * 20000}} for i in range(1500)]
        with mock.patch.object(serve, 'MAX_AGENT_BYTES', 1 << 20):
            pins = serve.agent_pins(fat)
        self.assertLess(len(pins), 1500)
        self.assertEqual(len(pins) + pins.truncated, 1500)

    def test_an_item_whose_accessors_raise_is_skipped_not_fatal(self):
        class Evil(dict):
            def get(self, *a):
                raise RuntimeError('boom')
        pins = serve.agent_pins([Evil(id='x'), cl('a1', 'добре')])
        self.assertEqual(([p['id'] for p in pins], pins.skipped), (['a1'], 1))

    def test_a_list_that_cannot_be_iterated_is_a_module_error(self):
        class Evil(list):
            def __iter__(self):
                raise RuntimeError('boom')
        with self.assertRaises(dm.ModuleError):
            serve.agent_pins(Evil([cl('a1', 'x')]))


# ----------------------------------------------------------------------------------------- таблиця рішень

class DecisionTest(AgentEnv):
    """`ProjectComments`: простір — аргумент, а не простір запиту й не `integrations_on()`."""

    def forbid_integrations_on(self):
        p = mock.patch.object(spaces, 'integrations_on', side_effect=AssertionError('integrations_on() у рішенні'))
        p.start()
        self.addCleanup(p.stop)

    def test_the_kinds(self):
        self.enable_memo_in(self.plain)
        self.assertEqual(self.pc(self.plain).kind, 'module')
        self.assertEqual(self.pc(self.liga).kind, 'legacy')
        self.assertEqual(self.pc(self.new_space('Bare')).kind, 'off')
        tcr._write(self.space_json(self.liga), '{broken')
        pc = self.pc(self.liga)
        self.assertEqual((pc.kind, pc.err.code), ('broken', 'space-json-unreadable'))

    def test_the_space_is_the_argument_not_the_space_of_the_request(self):
        self.enable_memo_in(self.plain)
        pc = self.pc(self.plain, request=self.liga['id'])              # запит прикріплений до ІНШОГО простору
        self.assertEqual((pc.kind, pc.prov.id), ('module', 'memo-comments'))
        self.assertEqual(self.pc(self.liga, request=self.plain['id']).kind, 'legacy')

    def test_without_a_request_space_the_league_tools_get_the_league_path(self):
        """Інструменти ЛІГА без простору запиту — як для сторінок: `comments_provider` віддає `'legacy'`, простір не читається."""
        self.enable_memo_in(self.plain)
        self.assertEqual(serve.ProjectComments(self.plain).kind, 'legacy')

    def test_module_and_broken_and_off_never_ask_integrations_on(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'x')])
        self.forbid_integrations_on()
        pc = self.pc(self.plain)
        self.assertEqual([p['id'] for p in pc.pins({}, 'px')], ['c0ffee01-aaaa'])
        pc.resolve({}, 'px', 'c0ffee01-aaaa', 'ok', legacy=lambda: self.fail('legacy'))
        tcr._write(self.space_json(self.liga), '{broken')
        with self.assertRaises(dm.ModuleError):
            self.pc(self.liga).pins({}, 'lx')
        with spaces.request_space(''):
            with self.assertRaises(spaces.IntegrationsOff):
                serve.ProjectComments(None).pins({}, 'zz')

    def test_each_kind_takes_exactly_its_own_branch(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'x')])
        hits = []
        pc = self.pc(self.plain)
        self.assertEqual(len(pc.pins({}, 'px', legacy=lambda ch: hits.append(ch))), 1)
        pc.resolve({}, 'px', 'c0ffee01-aaaa', 'r', legacy=lambda: hits.append('resolve'))
        self.assertEqual(hits, [])
        pc = self.pc(self.liga)
        self.assertEqual(pc.pins({'comment_project': 'dc/custom'}, 'lx', legacy=lambda ch: [ch]), ['dc/custom'])
        pc.resolve({}, 'lx', 'p', 'r', legacy=lambda: hits.append('resolve'))
        self.assertEqual(hits, ['resolve'])
        self.assertEqual(self.net.calls, [])

    def test_resolve_of_a_broken_or_absent_provider_never_runs_the_league_patch(self):
        """`resolve` має власну перевірку: зламане рішення чи «нікого» не падають на `legacy()` (PATCH у спільний Supabase)."""
        hits = []
        tcr._write(self.space_json(self.liga), '{broken')
        with self.assertRaises(dm.ModuleError):
            self.pc(self.liga).resolve({}, 'lx', 'p', 'r', legacy=lambda: hits.append('PATCH'))
        with self.assertRaises(spaces.IntegrationsOff):
            self.pc(self.plain).resolve({}, 'px', 'p', 'r', legacy=lambda: hits.append('PATCH'))
        self.assertEqual(hits, [])

    def test_the_internal_channel_has_its_own_module_channel(self):
        self.enable_memo_in(self.plain)
        pc = self.pc(self.plain)
        self.assertEqual(pc.channel({}, 'px'), f'deai/{self.plain["id"]}/px')
        self.assertEqual(pc.channel({}, 'px', internal=True), f'deai/{self.plain["id"]}/px/internal')
        self.assertEqual(self.pc(self.liga).channel({}, 'lx', internal=True), 'dc/lx/internal')

    def test_a_module_found_without_a_space_record_is_a_refusal_not_a_guess(self):
        """Простір запиту дав модуль, а запису простору викликач не передав: без нього ні `ctx`, ні каналу."""
        self.enable_memo_in(self.plain)
        with spaces.request_space(self.plain['id']):
            pc = serve.ProjectComments(None)
        self.assertEqual((pc.kind, pc.err.code), ('broken', 'module-error'))


# --------------------------------------------------------------------------------------- маршрут /comments

class ServerEnv(AgentEnv):
    """`AgentEnv` + справжній сервер у процесі (для маршруту `/comments`)."""

    def setUp(self):
        super().setUp()
        quiet = mock.patch.object(serve.Handler, 'log_message', lambda *a, **k: None)
        quiet.start()
        self.addCleanup(quiet.stop)
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True).start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)
        self.port = httpd.server_address[1]

    def fetch(self, path):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request('GET', path)
            r = conn.getresponse()
            return r.status, r.read().decode('utf-8')
        finally:
            conn.close()


class CommentsRouteTest(ServerEnv):
    def get(self, ch='internal'):
        st, raw = self.fetch(f'/comments?it=it1&channel={ch}')
        return st, json.loads(raw), raw

    def test_a_module_space_answers_with_the_module_pins_in_the_rest_shape(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7)])
        self.svc.comments[self.chan(self.plain, 'px', True)] = [cl('c0ffee09-zzzz', 'Внутрішній')]
        st, body, raw = self.get('project')
        self.assertEqual(st, 200, raw)
        self.assertEqual(body['project'], f'deai/{self.plain["id"]}/px')
        self.assertEqual(body['comments'], [serve.agent_pin(cl('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7))])
        self.assertNotIn('warning', body)
        st, body, _ = self.get('internal')
        self.assertEqual((st, body['project']), (200, f'deai/{self.plain["id"]}/px/internal'))
        self.assertEqual([c['id'] for c in body['comments']], ['c0ffee09-zzzz'])
        self.assertEqual(self.svc.log[0][2], 'Bearer ' + tcr.TOKEN)
        self.assert_no_legacy()
        self.assertNotIn(tcr.TOKEN, raw)

    def test_the_league_answer_is_the_supabase_rows_untouched(self):
        self.use(self.liga)
        rows = [rest('c0ffee01-aaaa', 'Кнопку вирівняти', seq=7)]
        self.net.rows = rows
        st, body, _ = self.get('project')
        self.assertEqual((st, body), (200, {'project': 'dc/lx', 'comments': rows}))
        self.assertEqual(len(self.net.calls), 1)
        self.assertEqual(self.svc.log, [])
        st, body, _ = self.get('internal')
        self.assertEqual(body['project'], 'dc/lx/internal')

    def test_a_league_service_that_is_down_degrades_like_before(self):
        self.use(self.liga)
        with mock.patch.object(serve, 'supabase_pins', side_effect=OSError('network down')):
            st, body, _ = self.get('project')
        self.assertEqual((st, body), (200, {'project': 'dc/lx', 'comments': [], 'error': 'network down'}))

    def test_a_space_without_a_provider_is_409_as_before(self):
        st, body, _ = self.get('project')
        self.assertEqual((st, body), (409, serve.integrations_off_body(
            'командних коментарів у просторі без інтеграцій нема')))
        self.assert_no_legacy()

    def test_a_league_space_with_a_lost_module_is_the_central_module_error_not_the_shared_service(self):
        self.break_module(self.liga)
        self.use(self.liga)
        st, body, raw = self.get('project')
        self.assertEqual((st, body['ok'], body['code']), (502, False, 'module-error'))
        self.assertEqual(body['error'], dm.COMMENTS_MODULE_BROKEN)
        self.assertNotIn('comments', body)
        self.assertNotIn(serve.SUPABASE_URL, raw)
        self.assert_no_legacy()
        self.assertEqual(self.svc.log, [])

    def test_an_unreadable_space_json_is_the_409_of_the_modules_and_no_shared_request(self):
        tcr._write(self.space_json(self.liga), '{broken')
        self.use(self.liga)
        st, body, _ = self.get('project')
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'space-json-unreadable'))
        self.assert_no_legacy()

    def test_a_module_service_that_is_down_is_an_error_field_with_no_comments(self):
        self.enable_memo_in(self.plain)
        self.svc.stop()
        st, body, raw = self.get('project')
        self.assertEqual(st, 200, raw)
        self.assertEqual(body['comments'], [])
        self.assertIn('module-error', body['error'])
        self.assertEqual(body['project'], f'deai/{self.plain["id"]}/px')
        self.assertNotIn(tcr.TOKEN, raw)
        self.assert_no_legacy()

    def test_a_malformed_module_answer_is_handled(self):
        self.answer(self.plain, {'oops': 1})
        st, body, _ = self.get('project')
        self.assertEqual((st, body['comments']), (200, []))
        self.assertIn('must answer list() with a list', body['error'])
        self.answer(self.plain, [cl('c0ffee01-aaaa', 'Добре\x1b[31m'), 'сміття', {'id': ''}, cl('c0ffee01-aaaa', 'дубль')])
        st, body, raw = self.get('project')
        self.assertEqual(st, 200, raw)
        self.assertEqual([c['text'] for c in body['comments']], ['Добре[31m'])
        self.assertEqual(body['warning'], 'відповідь модуля коментарів неповна: пропущено 3 зіпсованих елементів')
        self.assertNotIn('\\u001b', raw)
        self.assert_no_legacy()


# ------------------------------------------------------------------------------------------------ state.py

class StateTest(AgentEnv):
    def line(self, argv=()):
        rc, out, err = self.state(argv)
        self.assertEqual(rc, 0, err)
        return next(ln for ln in out.splitlines() if ln.startswith('Відкриті коментарі'))

    def test_the_open_counter_comes_from_the_module(self):
        self.enable_memo_in(self.plain)
        self.seed(self.plain, 'px', [cl('c0ffee01-aaaa', 'a'), cl('c0ffee02-bbbb', 'b'),
                                     cl('c0ffee03-cccc', 'c', status='resolved')])
        self.assertEqual(self.line(),
                         'Відкриті коментарі: 0 локальних (мені) + 2 проєктних → python3 bin/inbox.py')
        self.assert_no_legacy()

    def test_a_league_space_with_a_module_counts_from_the_module_not_the_shared_service(self):
        self.enable_memo_in(self.liga)
        self.seed(self.liga, 'lx', [cl('c0ffee01-aaaa', 'a')])
        self.use(self.liga)
        self.assertIn('+ 1 проєктних', self.line())
        self.assert_no_legacy()

    def test_a_lost_module_says_it_cannot_get_them_and_asks_nobody(self):
        self.break_module(self.liga)
        self.use(self.liga)
        self.assertEqual(self.line(), 'Відкриті коментарі: 0 локальних (мені), проєктні: не дістати (module-error)')
        self.assert_no_legacy()

    def test_a_module_that_fails_says_it_cannot_get_them(self):
        self.enable_memo_in(self.plain)
        self.svc.stop()
        self.assertIn('проєктні: не дістати (module-error)', self.line())
        self.assert_no_legacy()

    def test_an_unreadable_registry_is_not_get_at_all_neither_zero_nor_the_shared_service(self):
        with mock.patch.object(state, 'ProjectComments', side_effect=spaces.SpacesError('spaces-unreadable', '/p', 'broken')):
            self.assertEqual(state._team_comments({}, 'px', True), (0, ', проєктні: не дістати (spaces-unreadable)'))
        self.assert_no_legacy()

    def test_the_league_and_the_empty_cases_are_as_before(self):
        self.assertIn(', проєктних нема', self.line())
        self.assert_no_legacy()
        self.use(self.liga)
        self.net.rows = [rest('c0ffee01-aaaa', 'a'), rest('c0ffee02-bbbb', 'b', status='resolved')]
        self.assertIn('+ 1 проєктних', self.line())
        self.assertEqual(len(self.net.calls), 1)


if __name__ == '__main__':
    unittest.main()
