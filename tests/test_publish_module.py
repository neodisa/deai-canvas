"""Одна збірка превʼю — `serve.build_preview` — для ЛІГА й для модулів публікації.

Етап 2а, Task 3. `Handler._publish` збирав `publish/` у власному тілі, а модуль
`static-publish` (Task 4) мусить зібрати ТЕ САМЕ превʼю в локальну теку — БЕЗ
коментарів (Supabase там нема) і, за бажанням, БЕЗ парольного гейта. Друга копія збірки
розійшлась би з першою мовчки (рівно та пара «джерело / копія», проти якої написана
серія релізів 1.10–1.14), тому збірка винесена в одну функцію, а `_publish` лише кличе її.

Що доводиться:
  * `comments=False` — у дереві нема ні `comment-layer/`, ні жодного рядка `supabase`, ні
    ін'єкції в сторінках; контроль (`comments=True`) ту саму ін'єкцію МАЄ — без контролю «нема»
    нічого б не доводило;
  * `gate_pw=None` — обгортка відкривається сама (`__gateOpen`), `authgate` нема ніде, `<title>`
    сторінок не чіпаний, а в обгортку не їде `'None'` замість пароля;
  * `gate_pw='x'` — гейт і в обгортці, і в КОЖНІЙ внутрішній сторінці (інцидент 03.08.2026);
  * шлях ЛІГА — `/api/publish` кличе `build_preview(comments=True, gate_pw=<preview_password>)`, його
    дерево збігається з прямим викликом, а відповідь має ті самі ключі в тому ж порядку (порядок
    ключів JSON спостережуваний).

⛔ Ізоляція: власні тимчасові `HOME` і `DC_TASKS_FILE` (+ `DC_NO_OVERVIEW`), `DEAI_HOME` прибрано з
оточення на час тесту — шар просторів вимкнено, як у публікаційних тестах `test_serve.py`; справжній
`~/.deai` стереже `spaces_guard` (знімок на вході в модуль, звірка на виході). Мережі нема: усі
публікації тут `build_only`.

Task 4b (`Dispatch`, `ResealModuleBuilds`, один тест у `BuildPreview`) — ДИСПЕТЧЕР ролі `publish` у
`Handler._publish`: `deai_modules.provider('publish')` вирішує, хто публікує. `'legacy'` — зашитий шлях ЛІГА
(збірка + Vercel; його відповіді незмінні), `None` — 409 `no-publish-module`, `Module` (`static-publish`) —
збірка БЕЗ коментатора в локальну теку, без жодного виходу назовні. Світ `Dispatch` — шар просторів УВІМКНЕНО:
свої `HOME`/`DEAI_HOME`/`DC_TASKS_FILE`, два простори (`off` без інтеграцій, `on` з ними), сервер у процесі й
РОЗТЯЖКА (`Tripwire`: будь-яка мережа й будь-який підпроцес — запис і відмова; loopback лише на порт цього
сервера). Розтяжка доводить «нуль записів» разом із шпигунами за точками виходу ЛІГА (`_overview_sync`,
`_registry_push`, `git_autocommit`, `_check_published`…): вони б спрацювали навіть при `DC_NO_OVERVIEW`.
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # пакета `tests` нема — охоронець поруч
import deai_modules as dm  # noqa: E402
import serve  # noqa: E402
import spaces  # noqa: E402
import spaces_guard  # noqa: E402
from atomic_io import atomic_write_json  # noqa: E402

_REAL = None


def setUpModule():
    global _REAL
    _REAL = spaces_guard.snapshot()


def tearDownModule():
    spaces_guard.assert_untouched(_REAL)


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    return urllib.request.urlopen(req)


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


def _bytes(path):
    with open(path, 'rb') as fh:
        return fh.read()


def _tree(root):
    """{відносний шлях: sha256} усього дерева — для порівняння двох збірок байт у байт."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(out.items()))


def _title(html):
    m = re.search(r'<title>(.*?)</title>', html, flags=re.I | re.S)
    return m.group(1) if m else None


#: Сторінки фікстури: відносний шлях у `iterations/` → `<title>` джерела. Заголовки з сутностями й
#: лапками — щоб «не чіпаний» перевірялось на тому, що `_inject_gate` справді переписує.
SOURCE_PAGES = {
    'it1/alpha/index.html': 'Альфа &amp; R&amp;D «Суди»',
    'it1/gamma/index.html': 'Гамма',
    'it2/index.html': 'Друга ітерація',
}


class TaskFixture(unittest.TestCase):
    """Тимчасова задача `fixture` (дві опубліковані ітерації) у світі БЕЗ шару просторів: спільна основа
    `BuildPreview` і `ResealModuleBuilds`. Власних тестів не має."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='dc-bp-task-')
        self.cfgdir = tempfile.mkdtemp(prefix='dc-bp-cfg-')
        self.home = tempfile.mkdtemp(prefix='dc-bp-home-')
        for d in (self.tmp, self.cfgdir, self.home):
            self.addCleanup(shutil.rmtree, d, True)
        env = mock.patch.dict(os.environ, {
            'HOME': self.home, 'DC_TASKS_FILE': os.path.join(self.cfgdir, 'tasks.json'),
            'DC_NO_OVERVIEW': '1', 'DC_IDENTITY_NAME': 'Я', 'DC_IDENTITY_EMAIL': 'me@x'})
        env.start()
        self.addCleanup(env.stop)       # `patch.dict` повертає й прибраний нижче `DEAI_HOME`
        os.environ.pop('DEAI_HOME', None)
        for rel, title in SOURCE_PAGES.items():
            src = os.path.join(self.tmp, 'iterations', rel)
            os.makedirs(os.path.dirname(src), exist_ok=True)
            with open(src, 'w', encoding='utf-8') as fh:
                fh.write(f'<!DOCTYPE html><html><head><title>{title}</title></head>'
                         f'<body><h1>{rel}</h1></body></html>')
        with open(os.path.join(self.tmp, 'iterations', 'it1', 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': 'alpha', 'name': 'Альфа'}, {'id': 'gamma', 'name': 'Гамма'}]}, fh)
        with open(os.path.join(self.tmp, 'iterations.json'), 'w', encoding='utf-8') as fh:
            json.dump({'iterations': [
                {'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'перша', 'published': True},
                {'id': 'it2', 'date': '02.01.2026 10:00', 'note': 'друга', 'published': True}]}, fh)
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'jira': 'TEST-1'})

    def _tasks(self, task):
        with open(os.environ['DC_TASKS_FILE'], 'w', encoding='utf-8') as fh:
            json.dump({'current': 'fixture', 'design_work_root': self.cfgdir,
                       'tasks': {'fixture': task}}, fh)

    def _args(self):
        """(task, tid, its) — те саме, що `_publish` дає збірці: поточна задача й ОПУБЛІКОВАНІ ітерації."""
        tid, task = serve.task_for(serve.load_tasks(), None)
        its = [i for i in serve.load_meta(task).get('iterations', []) if i.get('published')]
        return task, tid, its

    def _build(self, **kw):
        task, tid, its = self._args()
        return serve.build_preview(task, tid, its, **kw)

    def _server(self):
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)
        return f'http://127.0.0.1:{httpd.server_address[1]}'


class BuildPreview(TaskFixture):
    """`serve.build_preview` напряму на тимчасовій задачі + `/api/publish` (build_only) на тій самій."""

    @staticmethod
    def _mentions(root, needle, skip_top=('shell',)):
        """Чи є в файлі дерева `needle` (без урахування регістру). Без `shell/`: це наші ж модулі
        оболонки, їхні коментарі — не артефакт коментатора, і майбутня згадка слова там не мусить
        червонити тест не з тієї причини. Лишаються сторінки, обгортка, маніфест, `comment-layer/`."""
        for dirpath, dirs, files in os.walk(root):
            if os.path.relpath(dirpath, root).split(os.sep)[0] in skip_top:
                dirs[:] = []
                continue
            for fn in files:
                with open(os.path.join(dirpath, fn), 'rb') as fh:
                    if needle in fh.read().lower():
                        return True
        return False

    def _source_title(self, rel):
        return _title(_read(os.path.join(self.tmp, 'iterations', rel)))

    def _inner_pages(self, pub):
        """Шляхи внутрішніх сторінок — з маніфесту: він і є «що поїхало» (а не звірка з нашою ж константою)."""
        man = json.loads(_read(os.path.join(pub, 'manifest.json')))
        paths = [p['path'] for p in man['pages']]
        self.assertEqual(sorted(paths), sorted(SOURCE_PAGES), 'фікстура й маніфест розійшлись')
        return paths

    # ---- форма результату --------------------------------------------------------------------

    def test_result_has_the_publish_shape_without_ok_and_code_stale(self):
        res = self._build(comments=True, gate_pw='x')
        self.assertEqual(list(res), ['dir', 'iterations', 'frames'])
        self.assertEqual(res['dir'], os.path.join(self.tmp, 'publish'))
        self.assertEqual((res['iterations'], res['frames']), (2, 0))
        self.assertTrue(os.path.isfile(os.path.join(res['dir'], 'index.html')))

    def test_broken_shots_manifest_surfaces_as_frames_warnings(self):
        shots = os.path.join(self.tmp, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        res = self._build(comments=True, gate_pw='x')
        self.assertEqual(list(res), ['dir', 'iterations', 'frames', 'frames_warnings'])
        self.assertTrue(any('it1' in w for w in res['frames_warnings']), res['frames_warnings'])
        self.assertTrue(os.path.isfile(os.path.join(res['dir'], 'it1', 'alpha', 'index.html')))

    def test_build_wipes_the_previous_publish_first(self):
        pub = os.path.join(self.tmp, 'publish')
        os.makedirs(os.path.join(pub, 'old'))
        with open(os.path.join(pub, 'old', 'stale.html'), 'w') as fh:
            fh.write('від минулої збірки')
        self._build(comments=False, gate_pw=None)
        self.assertFalse(os.path.exists(os.path.join(pub, 'old')))

    # ---- comments ----------------------------------------------------------------------------

    def test_comments_on_is_the_control_for_the_comments_off_checks(self):
        """Без цього контролю «у дереві нема supabase» могло б бути простою відсутністю фічі."""
        pub = self._build(comments=True, gate_pw='x')['dir']
        for b in serve.BUNDLES:
            self.assertTrue(os.path.isfile(os.path.join(pub, 'comment-layer', b)), b)
        for rel in self._inner_pages(pub):
            html = _read(os.path.join(pub, rel))
            self.assertIn('CommentLayer.init', html, rel)
            self.assertIn('dc/fixture', html, rel)
            depth_up = '../' * rel.count('/')           # `it1/alpha/index.html` → `../../`
            self.assertIn(f'{depth_up}comment-layer/comment-layer.min.js', html, rel)
        self.assertTrue(self._mentions(pub, b'supabase'),
                        'контроль: з коментарями supabase у дереві МАЄ бути')

    def test_comments_off_leaves_no_supabase_no_layer_folder_no_injection(self):
        for gate_pw in ('x', None):
            with self.subTest(gate_pw=gate_pw):
                pub = self._build(comments=False, gate_pw=gate_pw)['dir']
                self.assertFalse(os.path.exists(os.path.join(pub, 'comment-layer')))
                for dirpath, dirs, _files in os.walk(pub):
                    self.assertNotIn('comment-layer', dirs, dirpath)
                self.assertFalse(self._mentions(pub, b'supabase'), 'supabase у дереві без коментарів')
                for rel in self._inner_pages(pub):
                    html = _read(os.path.join(pub, rel))
                    for gone in ('CommentLayer', 'comment-layer', 'supabase', 'dc-audience'):
                        self.assertNotIn(gone, html, f'{rel}: {gone}')

    def test_comments_off_still_carries_everything_else(self):
        """Прапорець вимикає ЛИШЕ коментатор: оболонка, маніфест і сторінки на місці."""
        pub = self._build(comments=False, gate_pw=None)['dir']
        for m in serve.SHELL_MODULES:
            self.assertTrue(os.path.isfile(os.path.join(pub, 'shell', m)), m)
        self.assertTrue(os.path.isfile(os.path.join(pub, 'manifest.json')))
        for rel in self._inner_pages(pub):
            self.assertIn(f'<h1>{rel}</h1>', _read(os.path.join(pub, rel)))

    # ---- gate --------------------------------------------------------------------------------

    def test_no_gate_wrapper_opens_itself_and_pages_are_untouched(self):
        for comments in (True, False):
            with self.subTest(comments=comments):
                pub = self._build(comments=comments, gate_pw=None)['dir']
                wrapper = _read(os.path.join(pub, 'index.html'))
                # ТОЧНИЙ маркер, а не підрядок: у справжнього гейта `window.__gateOpen=true;` теж є
                # (всередині `unlock()`), тож голе `__gateOpen=true` не відрізняло б обгортки з гейтом
                self.assertIn('<script>window.__gateOpen=true;</script>', wrapper)
                self.assertNotIn('authgate', wrapper)
                self.assertIn('<title>Перегляд макета</title>', wrapper)
                # `str(None)` у шаблоні дав би пароль «None», що копіюється в посилання колезі
                self.assertNotIn("__extPw='None'", wrapper)
                self.assertNotIn('__extPw="None"', wrapper)
                self.assertIn('window.__extPw="";', wrapper)
                for rel in self._inner_pages(pub):
                    html = _read(os.path.join(pub, rel))
                    self.assertNotIn('authgate', html, rel)
                    self.assertNotIn('__origTitle', html, rel)
                    self.assertEqual(_title(html), self._source_title(rel), rel)
                    self.assertEqual(html.count('<title>'), 1, rel)

    def test_no_gate_never_touches_the_gate_helpers(self):
        """Гейта нема — отже, `gate_html` не кличеться взагалі, а `_inject_gate` не чіпає сторінок."""
        with mock.patch.object(serve, 'gate_html', side_effect=AssertionError('gate_html')), \
             mock.patch.object(serve, '_inject_gate', side_effect=AssertionError('_inject_gate')):
            self._build(comments=False, gate_pw=None)

    def test_gate_is_in_the_wrapper_and_in_every_inner_page(self):
        pub = self._build(comments=True, gate_pw='x')['dir']
        wrapper = _read(os.path.join(pub, 'index.html'))
        self.assertIn('authgate', wrapper)
        self.assertNotIn('<script>window.__gateOpen=true;</script>', wrapper)   # самовідкриття — лише без гейта
        self.assertIn('window.__extPw="x";', wrapper)
        for rel in self._inner_pages(pub):
            html = _read(os.path.join(pub, rel))
            self.assertIn('id="authgate"', html, rel)
            self.assertEqual(_title(html), 'Перегляд макета', rel)     # до пароля назви нема й у title
            self.assertIn('window.__origTitle=', html, rel)
        # ті самі ключі, що читає `preview_gate_state`: КОЖНА сторінка з гейтом І з цим паролем
        task = self._args()[0]
        st = serve.preview_gate_state(task, 'x')
        self.assertEqual((st['state'], st['stale'], st['ungated']), ('current', 0, 0), st)

    def test_empty_password_is_a_gate_not_the_absence_of_one(self):
        """«Без гейта» — лише `None`. `''` (забутий пароль у викликача) не мусить мовчки відкрити
        превʼю: це гейт, що відчиняється порожнім полем, і він ВИДИМИЙ у дереві."""
        pub = self._build(comments=False, gate_pw='')['dir']
        self.assertIn('id="authgate"', _read(os.path.join(pub, 'index.html')))
        for rel in self._inner_pages(pub):
            self.assertIn('id="authgate"', _read(os.path.join(pub, rel)), rel)

    def test_gate_helpers_are_looked_up_at_call_time(self):
        """`serve.gate_html` лишається підмінюваним: збірка бере його з модуля при виклику, а не
        захоплює значенням за замовчуванням (так само `preview_index_html` — тест нижче)."""
        with mock.patch.object(serve, 'gate_html', lambda tid, pw: f'<!--GATE:{tid}:{pw}-->'):
            pub = self._build(comments=False, gate_pw='pw1')['dir']
        self.assertIn('<!--GATE:fixture:pw1-->', _read(os.path.join(pub, 'index.html')))
        for rel in self._inner_pages(pub):
            self.assertIn('<!--GATE:fixture:pw1-->', _read(os.path.join(pub, rel)), rel)

    def test_preview_index_html_is_looked_up_at_call_time(self):
        """Те саме для обгортки: підміна `serve.preview_index_html` бачить і гейт, і пароль — справжні для
        ЛІГА, `NO_GATE_OPEN` і порожній пароль для превʼю без гейта."""
        seen = lambda gate, pw: f'<!--W:{gate}|{pw}-->'     # noqa: E731
        with mock.patch.object(serve, 'preview_index_html', seen), \
             mock.patch.object(serve, 'gate_html', lambda tid, pw: '<!--G-->'):
            # обидві збірки лягають в ОДНУ `publish/` (кожна її затирає) — читаємо відразу після своєї
            wrapper = os.path.join(self._build(comments=False, gate_pw='pw2')['dir'], 'index.html')
            self.assertEqual(_read(wrapper), '<!--W:<!--G-->|pw2-->')
            wrapper = os.path.join(self._build(comments=False, gate_pw=None)['dir'], 'index.html')
            self.assertEqual(_read(wrapper), f'<!--W:{serve.NO_GATE_OPEN}|-->')

    def test_empty_iteration_list_raises_before_touching_the_disk(self):
        """Порожній `its` — `ValueError` ДО будь-якої зміни: інакше збірка затерла б `publish/` і записала
        порожній маніфест (400 для дизайнера лишається в `_publish`)."""
        pub = os.path.join(self.tmp, 'publish')
        os.makedirs(pub)
        keep = os.path.join(pub, 'keep.txt')
        with open(keep, 'w', encoding='utf-8') as fh:
            fh.write('попередня збірка')
        task, tid, _its = self._args()
        for gate_pw in ('x', None):
            with self.subTest(gate_pw=gate_pw):
                with self.assertRaises(ValueError):
                    serve.build_preview(task, tid, [], comments=True, gate_pw=gate_pw)
                self.assertEqual(os.listdir(pub), ['keep.txt'])
                self.assertEqual(_read(keep), 'попередня збірка')

    # ---- шлях ЛІГА ---------------------------------------------------------------------------

    def test_league_publish_calls_build_preview_with_comments_and_the_preview_password(self):
        base = self._server()
        for custom in (None, "o'k</script>"):
            with self.subTest(preview_password=custom):
                task = {'dir': self.tmp, 'title': 'Фікстура', 'jira': 'TEST-1'}
                if custom:
                    task['preview_password'] = custom
                self._tasks(task)
                want = serve.preview_password(serve.load_tasks(), self._args()[0])
                self.assertEqual(want, custom or serve.DEFAULT_PREVIEW_PW)
                with mock.patch.object(serve, 'build_preview', wraps=serve.build_preview) as bp:
                    body = json.load(_post(base + '/api/publish', {'build_only': True}))
                self.assertTrue(body['ok'], body)
                self.assertEqual(bp.call_count, 1)
                args, kwargs = bp.call_args
                self.assertEqual(kwargs, {'comments': True, 'gate_pw': want})
                self.assertEqual((args[1], [i['id'] for i in args[2]]), ('fixture', ['it1', 'it2']))
                # гейт справді несе саме цей пароль — на КОЖНІЙ сторінці
                self.assertEqual(serve.preview_gate_state(args[0], want)['state'], 'current')

    def test_league_publish_tree_equals_the_direct_build(self):
        base = self._server()
        body = json.load(_post(base + '/api/publish', {'build_only': True}))
        via_http = _tree(body['dir'])
        pw = serve.preview_password(serve.load_tasks(), self._args()[0])
        direct = _tree(self._build(comments=True, gate_pw=pw)['dir'])
        self.assertEqual(via_http, direct)
        self.assertIn('comment-layer/comment-layer.min.js', direct)

    def test_league_publish_response_keeps_keys_and_their_order(self):
        """`ok` першим, далі `dir`/`iterations`/`frames`, потім `frames_warnings`, потім `code_stale`:
        порядок ключів JSON спостережуваний, `_publish` складає відповідь із результату збірки."""
        base = self._server()
        body = json.load(_post(base + '/api/publish', {'build_only': True}))
        self.assertEqual(list(body)[:4], ['ok', 'dir', 'iterations', 'frames'])
        self.assertEqual(body['dir'], os.path.join(self.tmp, 'publish'))
        self.assertEqual((body['ok'], body['iterations'], body['frames']), (True, 2, 0))
        tail = list(body)[4:]
        self.assertEqual(tail, [k for k in ('frames_warnings', 'code_stale') if k in tail])
        # із попередженням кадрів — воно стоїть ПЕРЕД `code_stale`
        shots = os.path.join(self.tmp, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        with mock.patch.object(serve, 'server_code_staleness', lambda: 'код новіший за процес'):
            body = json.load(_post(base + '/api/publish', {'build_only': True}))
        self.assertEqual(list(body), ['ok', 'dir', 'iterations', 'frames', 'frames_warnings', 'code_stale'])
        self.assertEqual(body['code_stale'], 'код новіший за процес')

    def test_league_deploy_still_works_from_the_built_dir(self):
        """Деплой (гілка БЕЗ `build_only`) читає `pub` після збірки: `vercel link/deploy` біжать з `cwd=pub`,
        а `_stable_alias` і `_remember_vercel_scope` отримують його ж. Усі `build_only`-тести цього не
        бачать: вилучення збірки без `pub = built['dir']` ламало б лише справжню публікацію."""
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'vercel_project': 'pv-22222222'})
        base = self._server()
        want = os.path.join(self.tmp, 'publish')
        url = 'https://pv-22222222-abc.vercel.app'
        cwds, seen = [], {}

        class Done:
            returncode = 0
            stdout = f'Production: {url}'
            stderr = ''

        def run(cmd, **kw):
            cwds.append(kw.get('cwd'))
            return Done()

        def alias(u, cwd, extra=()):
            seen['alias'] = cwd
            return url

        with mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
             mock.patch.object(serve.subprocess, 'run', run), \
             mock.patch.object(serve, '_stable_alias', alias), \
             mock.patch.object(serve, '_check_published', lambda u: {'verified': True}), \
             mock.patch.object(serve, '_registry_push', lambda tid: False), \
             mock.patch.object(serve, '_remember_vercel_scope',
                               lambda tid, task, pub: seen.__setitem__('scope', pub)), \
             mock.patch.object(serve, 'git_autocommit', lambda *a, **kw: None):
            body = json.load(_post(base + '/api/publish', {}))
        self.assertEqual(body.get('url'), url, body)
        self.assertEqual(body['dir'], want)
        self.assertEqual(cwds, [want, want])                # `vercel link` і `vercel deploy`
        self.assertEqual(seen, {'alias': want, 'scope': want})

    def test_league_deploy_keeps_a_toggle_made_while_it_was_running(self):
        """Деплой тривав хвилини, а `_publish` тримав `meta`, прочитаний НА ВХОДІ: запис `publish_url` зі старим
        `meta` відкочував би зелену крапку, яку дизайнер перемкнув за цей час (`publish-toggle`). Тому
        `iterations.json` перечитується ПЕРЕД `save_meta`, а записуються лише власні поля публікації.
        Перемикання робить `_check_published` — він кличеться між читанням і записом."""
        self._tasks({'dir': self.tmp, 'title': 'Фікстура', 'vercel_project': 'pv-33333333'})
        base = self._server()
        url = 'https://pv-33333333-abc.vercel.app'

        class Done:
            returncode = 0
            stdout = f'Production: {url}'
            stderr = ''

        def toggled_meanwhile(_url):
            task = self._args()[0]
            meta = serve.load_meta(task)
            for it in meta['iterations']:
                if it['id'] == 'it2':
                    it['published'] = False
            serve.save_meta(task, meta)
            return {'verified': True}

        with mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
             mock.patch.object(serve.subprocess, 'run', lambda cmd, **kw: Done()), \
             mock.patch.object(serve, '_stable_alias', lambda u, cwd, extra=(): url), \
             mock.patch.object(serve, '_check_published', toggled_meanwhile), \
             mock.patch.object(serve, '_registry_push', lambda tid: False), \
             mock.patch.object(serve, '_remember_vercel_scope', lambda tid, task, pub: None), \
             mock.patch.object(serve, 'git_autocommit', lambda *a, **kw: None):
            body = json.load(_post(base + '/api/publish', {}))
        self.assertEqual(body.get('url'), url, body)
        meta = json.loads(_read(os.path.join(self.tmp, 'iterations.json')))
        self.assertEqual(meta['publish_url'], url)
        self.assertTrue(meta['published_at'] and meta['publish_verified'] is True)
        self.assertEqual({i['id']: i['published'] for i in meta['iterations']},
                         {'it1': True, 'it2': False}, 'перемикання під час деплою відкотилось')

    def test_league_publish_without_published_iterations_is_still_a_400(self):
        """«Немає ітерацій» лишилось у `_publish`: збірка отримує вже готовий перелік і не вгадує його."""
        with open(os.path.join(self.tmp, 'iterations.json'), 'w', encoding='utf-8') as fh:
            json.dump({'iterations': [{'id': 'it1', 'date': 'x', 'note': 'н', 'published': False}]}, fh)
        base = self._server()
        with mock.patch.object(serve, 'build_preview', side_effect=AssertionError('build_preview')):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                _post(base + '/api/publish', {'build_only': True})
        self.assertEqual(ctx.exception.code, 400)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'publish')))


# ============================================================================== Task 4b: диспетчер ролі `publish`

MID = 'static-publish'
ISO_UTC = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z')
#: `preview_gate`, яким `/api/task` відповідає, коли публікує модуль: ТА САМА форма, що в `preview_gate_state`
#: (UI читає ті самі ключі), `state: 'module'` і нулі — «без гейта» для локальної збірки не попередження.
MODULE_GATE = {'state': 'module', 'stale': 0, 'ungated': 0, 'inner_stale': 0, 'pages': 0}
LOOPBACK = ('127.0.0.1', 'localhost', '::1')


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)


def _write_task_files(task_dir):
    """Ті самі сторінки й ітерації, що в `TaskFixture` (`SOURCE_PAGES`; обидві ітерації опубліковані)."""
    for rel, title in SOURCE_PAGES.items():
        src = os.path.join(task_dir, 'iterations', rel)
        os.makedirs(os.path.dirname(src), exist_ok=True)
        with open(src, 'w', encoding='utf-8') as fh:
            fh.write(f'<!DOCTYPE html><html><head><title>{title}</title></head>'
                     f'<body><h1>{rel}</h1></body></html>')
    _write_json(os.path.join(task_dir, 'iterations', 'it1', 'pages.json'),
                {'pages': [{'id': 'alpha', 'name': 'Альфа'}, {'id': 'gamma', 'name': 'Гамма'}]})
    _write_json(os.path.join(task_dir, 'iterations.json'), {'iterations': [
        {'id': 'it1', 'date': '01.01.2026 10:00', 'note': 'перша', 'published': True},
        {'id': 'it2', 'date': '02.01.2026 10:00', 'note': 'друга', 'published': True}],
        'publish_url': None})


class Tripwire:
    """Усе, що виходить з машини, — у запис (`hits`) і `OSError('tripwire')`: мережа (`urlopen`,
    `create_connection`) і БУДЬ-ЯКИЙ підпроцес (на шляху модуля нема ні `git`, ні `npx`, ні `overview_push.py`).
    Loopback пускається лише на порти ЦЬОГО тесту (`allow_ports`: сервер у процесі): будь-який інший порт
    (8765 справжнього канваса!) теж «вихід»."""

    def __init__(self):
        self.hits = []
        self.allow_ports = set()
        real_urlopen, real_cc = urllib.request.urlopen, socket.create_connection

        def urlopen(target, *a, **kw):
            u = urllib.parse.urlparse(getattr(target, 'full_url', None) or str(target))
            if u.hostname in LOOPBACK and u.port in self.allow_ports:
                return real_urlopen(target, *a, **kw)
            self.hits.append(('urlopen', getattr(target, 'full_url', str(target))))
            raise OSError('tripwire')

        def create_connection(address, *a, **kw):
            if address[0] in LOOPBACK and address[1] in self.allow_ports:
                return real_cc(address, *a, **kw)
            self.hits.append(('socket', f'{address[0]}:{address[1]}'))
            raise OSError('tripwire')

        def spawn(kind):
            def blocked(args, *a, **kw):
                self.hits.append((kind, args if isinstance(args, str) else ' '.join(map(str, args))))
                raise OSError('tripwire')
            return blocked

        self._stack = contextlib.ExitStack()
        for owner, name, repl in ((urllib.request, 'urlopen', urlopen),
                                  (socket, 'create_connection', create_connection),
                                  (subprocess, 'run', spawn('run')), (subprocess, 'Popen', spawn('popen'))):
            self._stack.enter_context(mock.patch.object(owner, name, repl))

    def stop(self):
        self._stack.close()


class TripwireItself(unittest.TestCase):
    """Охоронець, який не може впасти, нічого не вартий: розтяжка сама доводиться."""

    def test_records_and_blocks_every_way_out_but_the_allowed_loopback_port(self):
        trip = Tripwire()
        self.addCleanup(trip.stop)
        with self.assertRaises(OSError):
            urllib.request.urlopen('https://example.invalid/x')
        with self.assertRaises(OSError):
            socket.create_connection(('example.invalid', 443))
        with self.assertRaises(OSError):
            subprocess.run(['git', 'push'])
        with self.assertRaises(OSError):
            subprocess.Popen(['npx', 'vercel'])
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', 8765), timeout=1)       # порт справжнього канваса
        self.assertEqual([k for k, _ in trip.hits], ['urlopen', 'socket', 'run', 'popen', 'socket'])
        trip.stop()
        self.assertEqual(urllib.request.urlopen.__module__, 'urllib.request')
        self.assertEqual(subprocess.run.__module__, 'subprocess')


class _Stub:
    """Мінімум, який має зовнішня заглушка `Handler` (`boss_autopublish.py`): рівно ті чотири методи, що
    `_publish` кликав ДО диспетчера. Нічого іншого з обробника диспетчер не бере."""

    def __init__(self):
        self.sent = []
        self.overview = 0

    def _current_task(self):
        return serve.task_for(serve.load_tasks(), None)

    def send_error(self, code, message=None):
        self.sent.append(('error', code, message))

    def _send_json(self, obj, status=200):
        self.sent.append((status, obj))

    def _overview_sync(self):
        self.overview += 1


class Dispatch(unittest.TestCase):
    """Світ: шар просторів увімкнено; `off` (без інтеграцій, задача `tx`, поточний) і `on` (з інтеграціями,
    задача `ty`); сервер у процесі; розтяжка; шпигуни за точками виходу ЛІГА."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='dc-disp-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, 'home')
        # DEAI_HOME — у домівці (як у test_static_publish): інакше тимчасова тека macOS (`/var`) дала б
        # `path-system` раніше за `path-deai-home`
        self.deai = os.path.join(self.home, 'stuff', 'deai')
        self.tool = os.path.join(self.home, 'tools', 'dc')
        os.makedirs(self.tool)
        os.makedirs(self.deai, mode=0o700)
        env = mock.patch.dict(os.environ, {
            'HOME': self.home, 'DEAI_HOME': self.deai,
            'DC_TASKS_FILE': os.path.join(self.tmp, 'legacy', 'tasks.json'),     # старого файла нема
            'DC_NO_OVERVIEW': '1', 'DC_IDENTITY_NAME': 'Я', 'DC_IDENTITY_EMAIL': 'me@x'})
        env.start()
        self.addCleanup(env.stop)
        # справжня тека інструмента (репозиторій) не може стати ціллю публікації, навіть якщо правило колись
        # зламається, а `path-tool` перевіряється саме як причина
        tool = mock.patch.object(spaces, 'ROOT', self.tool)
        tool.start()
        self.addCleanup(tool.stop)
        spaces.clear_request_space()
        self.addCleanup(spaces.clear_request_space)
        dm.reset_caches()
        self.addCleanup(dm.reset_caches)
        self.off_path = os.path.join(self.home, 'deai-work', 'off')
        self.on_path = os.path.join(self.home, 'deai-work', 'on')
        self.off = self._space('off', self.off_path, False, 'tx')
        self.on = self._space('on', self.on_path, True, 'ty')
        atomic_write_json(os.path.join(self.deai, 'spaces.json'),
                          {'version': 1, 'current': 'off', 'spaces': [self.off, self.on]})
        self.tx_dir = os.path.join(self.off_path, 'tx')
        self.ty_dir = os.path.join(self.on_path, 'ty')
        self.folder = os.path.join(self.home, 'deai-published', 'off')
        self.dest = os.path.join(self.folder, 'tx')
        # розтяжка ПЕРШОЮ, сервер — після неї (його порт їй дозволяється)
        self.trip = Tripwire()
        self.addCleanup(self.trip.stop)
        self.spies = {}
        for owner, name in ((serve.Handler, '_overview_sync'), (serve, '_registry_push'),
                            (serve, 'git_autocommit'), (serve, '_check_published'), (serve, '_node_bin'),
                            (serve, '_stable_alias'), (serve, '_remember_vercel_scope')):
            patch = mock.patch.object(owner, name)
            self.spies[name] = patch.start()
            self.addCleanup(patch.stop)
        httpd = serve.make_server(0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
        self.addCleanup(stop)
        self.port = httpd.server_address[1]
        self.trip.allow_ports.add(self.port)
        self.base = f'http://127.0.0.1:{self.port}'

    # ---- фікстури ----

    def _space(self, sid, path, integrations, tid):
        """Простір `sid` із задачею `tid`: тека, `space.json`, `tasks.json`, файли задачі. Повертає запис реєстру."""
        _write_json(os.path.join(path, 'space.json'), {'name': sid.title(), 'color': 'space-1'})
        _write_json(os.path.join(path, 'tasks.json'), {
            'design_work_root': path, 'current': tid,
            'tasks': {tid: {'title': f'Задача {tid}', 'dir': os.path.join(path, tid)}}})
        _write_task_files(os.path.join(path, tid))
        return {'id': sid, 'path': path, 'legacy': False, 'integrations': integrations}

    def _register(self, rec):
        """Додати запис простору в реєстр (мимо `create_space`: він відмовив би в повторі id задачі)."""
        path = os.path.join(self.deai, 'spaces.json')
        with open(path, encoding='utf-8') as fh:
            reg = json.load(fh)
        reg['spaces'].append(rec)
        atomic_write_json(path, reg)
        return rec

    def _call(self, method, path, payload=None, headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code, raw = r.status, r.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read().decode('utf-8')
        try:
            return code, json.loads(raw)
        except ValueError:
            return code, raw                    # `send_error` відповідає HTML

    def post(self, path, payload=None, headers=None):
        return self._call('POST', path, {} if payload is None else payload, headers)

    def get(self, path, headers=None):
        return self._call('GET', path, None, headers)

    def meta(self, task_dir=None):
        return json.loads(_read(os.path.join(task_dir or self.tx_dir, 'iterations.json')))

    def set_folder(self, value, space=None):
        dm.write_module_state(space or self.off, MID, settings={'folder': value})

    def assert_quiet(self):
        """Жодного виходу назовні: розтяжка порожня, а жодна точка виходу ЛІГА не кликана."""
        self.assertEqual(self.trip.hits, [])
        for name, spy in self.spies.items():
            self.assertEqual(spy.call_count, 0, f'{name} кликано на шляху модуля')

    def assert_nothing_built(self):
        self.assertFalse(os.path.exists(os.path.join(self.tx_dir, 'publish')), 'publish/ зібрано до відмови')

    # ---- публікація у простір без інтеграцій ----

    def test_publish_lands_in_the_folder_with_a_marker_and_writes_publish_local(self):
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'local', 'iterations', 'frames'])
        self.assertEqual(body['local'], {'path': self.dest, 'url': '/published/off/tx/'})
        self.assertEqual((body['ok'], body['iterations'], body['frames']), (True, 2, 0))
        for rel in ('index.html', 'manifest.json', *SOURCE_PAGES):
            self.assertTrue(os.path.isfile(os.path.join(self.dest, rel)), rel)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, '.deai-published')))
        self.assertEqual(os.listdir(self.folder), ['tx'])                  # ні .tmp-, ні .old-
        meta = self.meta()
        pl = meta['publish_local']
        self.assertEqual((pl['module'], pl['path']), (MID, self.dest))
        self.assertRegex(pl['published_at'], ISO_UTC)
        self.assertEqual(set(pl), {'module', 'path', 'published_at'})
        # поля ВЕРСІЇ ЛІГА не чіпаємо: `publish_url`, `published_at`, `publish_verified`
        self.assertIsNone(meta['publish_url'])
        self.assertNotIn('published_at', meta)
        self.assertNotIn('publish_verified', meta)
        self.assertEqual([i['published'] for i in meta['iterations']], [True, True])
        self.assert_quiet()

    def test_the_build_has_no_comment_layer_and_no_supabase(self):
        self.assertEqual(self.post('/api/publish')[0], 200)
        self.assertFalse(os.path.exists(os.path.join(self.dest, 'comment-layer')))
        for dirpath, _dirs, files in os.walk(self.dest):
            if os.path.relpath(dirpath, self.dest).split(os.sep)[0] == 'shell':
                continue
            for fn in files:
                self.assertNotIn(b'supabase', _bytes(os.path.join(dirpath, fn)).lower(), fn)

    def test_republish_replaces_the_folder_and_refreshes_publish_local(self):
        self.assertEqual(self.post('/api/publish')[0], 200)
        first = self.meta()['publish_local']
        with open(os.path.join(self.dest, 'stale.txt'), 'w') as fh:
            fh.write('від минулої публікації')
        with open(os.path.join(self.tx_dir, 'iterations', 'it2', 'index.html'), 'w', encoding='utf-8') as fh:
            fh.write('<!DOCTYPE html><html><head><title>v2</title></head><body><h1>друга версія</h1></body></html>')
        time.sleep(1.1)                                                     # `published_at` — з точністю до секунди
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertFalse(os.path.exists(os.path.join(self.dest, 'stale.txt')))
        self.assertIn('друга версія', _read(os.path.join(self.dest, 'it2', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, '.deai-published')))
        self.assertEqual(os.listdir(self.folder), ['tx'])
        again = self.meta()['publish_local']
        self.assertEqual(again['path'], first['path'])
        self.assertGreater(again['published_at'], first['published_at'])
        self.assert_quiet()

    def test_build_only_builds_the_task_folder_and_publishes_nothing(self):
        st, body = self.post('/api/publish', {'build_only': True})
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body)[:4], ['ok', 'dir', 'iterations', 'frames'])
        self.assertEqual(body['dir'], os.path.join(self.tx_dir, 'publish'))
        self.assertNotIn('local', body)
        self.assertTrue(os.path.isfile(os.path.join(body['dir'], 'index.html')))
        self.assertFalse(os.path.exists(os.path.join(body['dir'], 'comment-layer')))
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')), 'тека публікації зʼявилась')
        self.assertNotIn('publish_local', self.meta())
        self.assert_quiet()

    def test_response_keys_and_their_order_carry_frames_warnings_and_code_stale(self):
        shots = os.path.join(self.tx_dir, 'iterations', 'it1', 'shots')
        os.makedirs(shots)
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        with mock.patch.object(serve, 'server_code_staleness', lambda: 'код новіший за процес'):
            st, body = self.post('/api/publish', {'build_only': True})
            self.assertEqual(list(body), ['ok', 'dir', 'iterations', 'frames', 'frames_warnings', 'code_stale'])
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(list(body), ['ok', 'local', 'iterations', 'frames', 'frames_warnings', 'code_stale'])
        self.assertTrue(any('it1' in w for w in body['frames_warnings']), body['frames_warnings'])
        self.assertEqual(body['code_stale'], 'код новіший за процес')

    def test_no_iterations_marked_is_the_same_400_before_any_build(self):
        meta = self.meta()
        for it in meta['iterations']:
            it['published'] = False
        _write_json(os.path.join(self.tx_dir, 'iterations.json'), meta)
        st, body = self.post('/api/publish')
        self.assertEqual(st, 400)
        self.assertIn('no iterations marked for publish - toggle the green dot first', body)
        self.assert_nothing_built()
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))
        self.assert_quiet()

    def test_a_custom_folder_setting_is_honoured(self):
        custom = os.path.join(self.home, 'pubs', 'custom')
        self.set_folder(custom)
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(body['local']['path'], os.path.join(custom, 'tx'))
        self.assertTrue(os.path.isfile(os.path.join(custom, 'tx', 'index.html')))
        self.assertFalse(os.path.exists(self.folder))

    # ---- `no-publish-module`, `bad-folder` ----

    def test_a_space_without_integrations_and_without_a_module_gets_409_no_publish_module(self):
        dm.write_module_state(self.off, MID, enabled=False)
        st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'no-publish-module'))
        self.assertTrue(body['error'])
        self.assert_nothing_built()
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))
        self.assert_quiet()

    def test_a_bad_folder_is_409_bad_folder_and_the_build_never_starts(self):
        """Теку перевіряє ДИСПЕТЧЕР до збірки: модуль перевірив би її теж (друга лінія), але `publish/` уже було б
        зібрано (`rmtree` + повна збірка задарма). Відповідь від цього не залежить — тож доводиться саме
        `publish/`, якого нема."""
        folders = {
            'тека задачі': self.tx_dir, 'тека простору': self.off_path, 'домівка': self.home, '~': '~',
            'усередині DEAI_HOME': os.path.join(self.deai, 'pub'), 'тека інструмента': os.path.join(self.tool, 'pub')}
        for what, value in folders.items():
            with self.subTest(what):
                self.set_folder(value)
                st, body = self.post('/api/publish')
                self.assertEqual((st, body.get('ok'), body.get('code')), (409, False, 'bad-folder'), body)
                self.assertTrue(body['error'].startswith('path-'), body)
                self.assert_nothing_built()
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))
        self.assert_quiet()

    # ---- id задачі, який модуль відмовить, і шлях, який він повернув ----

    def _task_space(self, sid, tid):
        """Простір без інтеграцій `sid` із задачею `tid`, зроблений поточним (запис реєстру мимо `switch_space`)."""
        rec = self._register(self._space(sid, os.path.join(self.home, 'deai-work', sid), False, tid))
        path = os.path.join(self.deai, 'spaces.json')
        with open(path, encoding='utf-8') as fh:
            reg = json.load(fh)
        reg['current'] = sid
        atomic_write_json(path, reg)
        return rec

    def test_a_task_id_the_module_would_refuse_is_400_before_any_build(self):
        """`NAME_RE` сервера пускає Unicode, `static-publish` — лише `[A-Za-z0-9_-]{1,128}` і не імена пристроїв
        Windows: раніше такий id давав 502 `module-error` ПІСЛЯ збірки (`rmtree` + повна збірка задарма)."""
        for i, tid in enumerate(('задача', 'x' * 129, 'NUL', 'com1', 'Aux')):
            with self.subTest(tid=tid[:20]):
                rec = self._task_space(f'bad{i}', tid)
                task_dir = os.path.join(rec['path'], tid)
                for payload in ({}, {'build_only': True}):
                    st, body = self.post('/api/publish', payload)
                    self.assertEqual((st, body.get('ok'), body.get('code')), (400, False, 'bad-task-id'), body)
                    self.assertTrue(body['error'])
                    self.assertFalse(os.path.exists(os.path.join(task_dir, 'publish')), 'publish/ зібрано до відмови')
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')), 'тека публікації зачеплена')
        self.assert_quiet()

    def test_task_ids_the_module_accepts_still_publish(self):
        """Контроль до тесту вище: перевірка не різе зайвого (межа 128, великі літери, `_` і `-`)."""
        for i, tid in enumerate(('x' * 128, 'Task_1-b', 'console')):
            with self.subTest(tid=tid[:20]):
                self._task_space(f'ok{i}', tid)
                st, body = self.post('/api/publish')
                self.assertEqual(st, 200, body)
                self.assertEqual(body['local']['path'], os.path.join(self.home, 'deai-published', f'ok{i}', tid))

    def test_a_module_that_returns_a_path_other_than_the_destination_is_502_and_writes_nothing(self):
        """Адреса в `publish_local` і в `local` мусить бути тією, що перевірено й замкнено: `<тека>/<задача>`."""
        module = dm.catalog()[MID]
        other = os.path.join(self.home, 'elsewhere', 'tx')
        with mock.patch.dict(module._fns, {'publish': lambda ctx, build, task: {'path': other}}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body.get('ok'), body.get('code')), (502, False, 'module-error'), body)
        self.assertNotIn('publish_local', self.meta())

    def test_the_destination_through_a_symlinked_folder_is_still_the_destination(self):
        """Порівняння — за `realpath`: модуль, що повернув шлях через посилання на ту саму теку, не відмовляється."""
        real = os.path.join(self.home, 'pubs', 'real')
        os.makedirs(real)
        alias = os.path.join(self.home, 'pubs', 'alias')
        os.symlink(real, alias)
        self.set_folder(real)
        module = dm.catalog()[MID]
        real_publish = module.fn('publish')

        def via_alias(ctx, build, task):
            real_publish(ctx, build, task)
            return {'path': os.path.join(alias, task['id'])}

        with mock.patch.dict(module._fns, {'publish': via_alias}):
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(self.meta()['publish_local']['path'], os.path.join(alias, 'tx'))

    # ---- пароль ----

    def test_a_password_secret_gates_the_wrapper_and_every_page(self):
        dm.write_secrets('off', MID, {'password': 'pw-Ключ-1'})
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        wrapper = _read(os.path.join(self.dest, 'index.html'))
        self.assertIn('id="authgate"', wrapper)
        self.assertIn(f'window.__extPw={json.dumps("pw-Ключ-1", ensure_ascii=False)};', wrapper)
        self.assertNotIn('<script>window.__gateOpen=true;</script>', wrapper)
        for rel in SOURCE_PAGES:
            self.assertIn('id="authgate"', _read(os.path.join(self.dest, rel)), rel)
        # ті самі ключі, що читає `preview_gate_state`: КОЖНА сторінка з гейтом І з цим паролем
        gate = serve.preview_gate_state({'dir': self.tx_dir}, 'pw-Ключ-1')
        self.assertEqual((gate['state'], gate['stale'], gate['ungated']), ('current', 0, 0), gate)
        # пароль у відповіді й у метаданих не світиться (він у сторінках лише ЯК гейт)
        self.assertNotIn('pw-Ключ-1', json.dumps(body, ensure_ascii=False))
        self.assertNotIn('pw-Ключ-1', _read(os.path.join(self.tx_dir, 'iterations.json')))
        self.assertNotIn('pw-Ключ-1', _read(os.path.join(self.off_path, 'space.json')))

    def test_no_secret_means_no_gate_and_the_wrapper_opens_itself(self):
        self.assertEqual(self.post('/api/publish')[0], 200)
        wrapper = _read(os.path.join(self.dest, 'index.html'))
        self.assertIn('<script>window.__gateOpen=true;</script>', wrapper)
        self.assertNotIn('authgate', wrapper)
        for rel in SOURCE_PAGES:
            self.assertNotIn('authgate', _read(os.path.join(self.dest, rel)), rel)

    def test_an_empty_password_secret_is_no_password_not_a_gate_that_opens_with_an_empty_field(self):
        """`''` у секретах — «пароля нема» (`or None`); а `build_preview(gate_pw='')` — гейт, що відчиняється
        порожнім полем (сторінки ЗМІНЕНО, `<title>` переписано). Без пароля сторінки не чіпаються взагалі."""
        dm.write_secrets('off', MID, {'password': ''})
        self.assertEqual(self.post('/api/publish')[0], 200)
        self.assertIn('<script>window.__gateOpen=true;</script>', _read(os.path.join(self.dest, 'index.html')))
        for rel in SOURCE_PAGES:
            html = _read(os.path.join(self.dest, rel))
            self.assertNotIn('authgate', html, rel)
            self.assertEqual(_title(html), _title(_read(os.path.join(self.tx_dir, 'iterations', rel))), rel)

    # ---- помилки модуля: ОДНЕ місце відповіді (`_guarded`) ----

    def test_a_broken_space_json_without_integrations_is_409_space_json_unreadable(self):
        """Простір без інтеграцій потребує явних рішень із `space.json`: `provider` кидає `ModuleError`, а
        `_guarded` відповідає за ВСІ маршрути однаково — JSON із кодом і статусом ядра, а не обірване зʼєднання."""
        with open(os.path.join(self.off_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'space-json-unreadable'), body)
        self.assertIn('space.json', body['error'])
        self.assert_nothing_built()
        self.assert_quiet()

    def test_a_module_error_from_the_module_keeps_its_code_and_status_and_loses_the_secret(self):
        dm.write_secrets('off', MID, {'password': 'S3cr3t-pw'})
        module = dm.catalog()[MID]

        def refuses(ctx, build, task):
            raise ctx['ModuleError']('bad-folder', message='не можу писати з S3cr3t-pw')

        with mock.patch.dict(module._fns, {'publish': refuses}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (409, False, 'bad-folder'), body)
        self.assertNotIn('S3cr3t-pw', json.dumps(body, ensure_ascii=False))
        self.assertIn('***', body['error'])

    def test_a_crashing_module_is_502_module_error_without_the_secret(self):
        dm.write_secrets('off', MID, {'password': 'S3cr3t-pw'})
        module = dm.catalog()[MID]

        def crashes(ctx, build, task):
            raise RuntimeError('впало на S3cr3t-pw')

        with mock.patch.dict(module._fns, {'publish': crashes}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body['ok'], body['code']), (502, False, 'module-error'), body)
        self.assertNotIn('S3cr3t-pw', json.dumps(body, ensure_ascii=False))

    def test_a_module_that_returns_no_path_is_502_and_writes_no_publish_local(self):
        module = dm.catalog()[MID]
        with mock.patch.dict(module._fns, {'publish': lambda ctx, build, task: {}}):
            st, body = self.post('/api/publish')
        self.assertEqual((st, body['code']), (502, 'module-error'), body)
        self.assertNotIn('publish_local', self.meta())

    def test_a_broken_space_json_with_integrations_still_publishes_the_league_way(self):
        """Простір з інтеграціями не потребує `space.json` для вибору шляху: `provider` ковтає
        `space-json-unreadable` і віддає `'legacy'` — ЛІГА-публікація (з коментатором) працює."""
        with open(os.path.join(self.on_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        self.assertEqual(dm.provider('publish', self.on), 'legacy')
        st, body = self.post('/api/publish', {'build_only': True}, {'X-Canvas-Task': 'ty'})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['dir'], os.path.join(self.ty_dir, 'publish'))
        self.assertTrue(os.path.isdir(os.path.join(body['dir'], 'comment-layer')), 'це мав бути шлях ЛІГА')
        self.assertTrue(os.path.isfile(os.path.join(body['dir'], 'comment-layer', serve.BUNDLES[0])))

    # ---- простір ЛІГА, неявний і зафіксований шляхи ----

    def test_a_space_with_integrations_and_no_module_is_the_league_path(self):
        st, body = self.post('/api/publish', {'build_only': True}, {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, list(body)[:4]), (200, ['ok', 'dir', 'iterations', 'frames']), body)
        self.assertTrue(os.path.isdir(os.path.join(body['dir'], 'comment-layer')))
        self.assertNotIn('local', body)
        self.assertNotIn('publish_local', self.meta(self.ty_dir))
        self.assertFalse(os.path.exists(os.path.join(self.home, 'deai-published')))

    def test_an_explicitly_enabled_module_wins_where_integrations_are_on(self):
        dm.write_module_state(self.on, MID, enabled=True)
        st, body = self.post('/api/publish', {}, {'X-Canvas-Task': 'ty'})
        self.assertEqual(st, 200, body)
        want = os.path.join(self.home, 'deai-published', 'on', 'ty')
        self.assertEqual(body['local'], {'path': want, 'url': '/published/on/ty/'})
        self.assertFalse(os.path.exists(os.path.join(self.ty_dir, 'publish', 'comment-layer')))
        self.assertEqual(self.meta(self.ty_dir)['publish_local']['path'], want)
        self.assert_quiet()

    def test_an_unpinned_request_space_is_the_league_path(self):
        """Інструменти ЛІГА й зовнішні заглушки обробника кличуть `_publish` БЕЗ зафіксованого простору запиту:
        `provider` дає `'legacy'` без читання реєстру, і шлях ЛІГА працює як раніше — навіть коли поточний простір
        машини БЕЗ інтеграцій. Заглушка має лише чотири методи, які `_publish` кликав завжди."""
        spaces.clear_request_space()
        self.assertEqual(dm.provider('publish'), 'legacy')
        stub = _Stub()
        serve.Handler._publish(stub, {'build_only': True})
        (st, body), = stub.sent
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(body['dir'], os.path.join(self.tx_dir, 'publish'))
        self.assertTrue(os.path.isdir(os.path.join(body['dir'], 'comment-layer')))
        self.assertEqual(stub.overview, 1, 'шлях ЛІГА лишився як був: дашборд команди штовхається')

    def test_a_request_without_any_space_has_nobody_to_publish(self):
        """`''` — запит прямо сказав «без простору» (просторів нема): це не простір ЛІГА, публікувати нікому."""
        stub = _Stub()
        with spaces.request_space(''):
            serve.Handler._publish(stub, {})
        self.assertEqual(stub.sent, [(409, serve.no_publish_module_body())])
        self.assert_nothing_built()
        self.assert_quiet()

    def test_the_module_path_needs_only_the_four_methods_of_an_external_stub(self):
        stub = _Stub()
        with spaces.request_space('off'):
            serve.Handler._publish(stub, {})
        (st, body), = stub.sent
        self.assertEqual((st, body['ok']), (200, True), body)
        self.assertEqual(body['local']['path'], self.dest)
        self.assertEqual(stub.overview, 0, 'модуль не штовхає дашборд команди')
        stub = _Stub()
        meta = self.meta()
        for it in meta['iterations']:
            it['published'] = False
        _write_json(os.path.join(self.tx_dir, 'iterations.json'), meta)
        with spaces.request_space('off'):
            serve.Handler._publish(stub, {})
        self.assertEqual(stub.sent, [('error', 400, 'no iterations marked for publish - toggle the green dot first')])

    # ---- серіалізація публікацій одного призначення ----

    def _slow(self, owner=dm, name='call'):
        """Патч `owner.name` (типово `deai_modules.call`): перший виклик стоїть, доки `release` не подано; решта
        викликів лише відмічаються й ідуть далі. Повертає `(entered, inside, second, release, kwargs)`."""
        real = getattr(owner, name)
        entered, kwargs = [], []
        inside, second, release = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)                       # тест, що впав, не лишає потік стояти

        def slow(*args, **kw):
            entered.append(args)
            kwargs.append(kw)
            if len(entered) == 1:
                inside.set()
                release.wait(20)
            else:
                second.set()
            return real(*args, **kw)
        patch = mock.patch.object(owner, name, slow)
        patch.start()
        self.addCleanup(patch.stop)
        return entered, inside, second, release, kwargs

    def _concurrent(self, first, second_run, entered, inside, release):
        """Запустити `first`, дочекатись, що вона всередині (стоїть), запустити `second_run` в окремому потоці й
        дати їй 5 с: вона мусить ВІДПОВІСТИ (замок зайнятий — одразу 409, інше призначення — працює), а не чекати.
        Потім відпустити першу. Повертає `(відповідь першої, відповідь другої, скільки викликів увійшло в патч,
        поки перша стояла)`."""
        box = {}
        t1 = threading.Thread(target=lambda: box.__setitem__('first', first()), daemon=True)
        t2 = threading.Thread(target=lambda: box.__setitem__('second', second_run()), daemon=True)
        t1.start()
        self.assertTrue(inside.wait(15), 'перша публікація не дійшла до патча')
        t2.start()
        t2.join(5)
        waited = t2.is_alive()
        seen = len(entered)
        release.set()
        t1.join(30)
        t2.join(30)
        self.assertFalse(t1.is_alive() or t2.is_alive(), 'публікація зависла')
        self.assertFalse(waited, 'друга публікація ЧЕКАЛА (замок мусить відповідати одразу: 409 publish-busy)')
        return box['first'], box['second'], seen

    def _publish_in(self, sid, payload=None):
        """Публікація в просторі `sid` напряму через `Handler._publish` із заглушкою: відповідь — `(статус, тіло)`."""
        def run():
            stub = _Stub()
            with spaces.request_space(sid):
                serve.Handler._publish(stub, {} if payload is None else payload)
            return stub.sent[0]
        return run

    def assert_busy(self, st, body):
        self.assertEqual((st, body.get('ok'), body.get('code')), (409, False, 'publish-busy'), body)
        self.assertTrue(body['error'])

    def test_a_second_publish_of_one_task_is_409_busy_while_the_first_runs(self):
        """Замок БЕЗ очікування: зависла мережева тека не нагромаджує потоки, що чекають, а повторний клік дістає
        чітку відповідь одразу. Коли перша публікація вийшла, замок вільний."""
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(lambda: self.post('/api/publish'), lambda: self.post('/api/publish'),
                                            entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(seen, 1, 'друга публікація тієї ж задачі зайшла в модуль, поки перша ще всередині')
        self.assertEqual(first[0], 200, first)
        self.assertEqual(self.post('/api/publish')[0], 200, 'замок не відпущено після першої публікації')
        # `timeout=` перетворив би виклик на робочий потік: що не вклався, копіював би далі БЕЗ замка
        self.assertEqual(kwargs, [{}, {}], 'publish кликано з timeout')
        self.assertEqual(os.listdir(self.folder), ['tx'])
        self.assertTrue(os.path.isfile(os.path.join(self.dest, '.deai-published')))

    def test_build_only_obeys_the_same_lock(self):
        """`build_only` теж стирає `<задача>/publish/`, з якого перша публікація копіює: те саме 409."""
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(lambda: self.post('/api/publish'),
                                            lambda: self.post('/api/publish', {'build_only': True}),
                                            entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(first[0], 200, first)
        self.assertEqual(self.post('/api/publish', {'build_only': True})[0], 200)

    def test_the_build_runs_under_the_lock_too(self):
        """Збірка стирає й пише `<задача>/publish/`, з якого модуль копіює: друга публікація тієї самої задачі не
        сміє почати збірку, поки перша ще триває (лишила б напівзібрану теку під першою)."""
        entered, inside, second, release, kwargs = self._slow(serve, 'build_preview')
        first, sec, seen = self._concurrent(lambda: self.post('/api/publish'), lambda: self.post('/api/publish'),
                                            entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(seen, 1, 'друга збірка тієї ж задачі почалась, поки перша публікація ще триває')
        self.assertEqual(first[0], 200, first)

    def test_the_lock_is_released_after_a_failed_publish(self):
        """Замок без очікування, який не відпущено після збою, зробив би задачу «зайнятою» назавжди."""
        module = dm.catalog()[MID]

        def crashes(ctx, build, task):
            raise RuntimeError('впало')

        with mock.patch.dict(module._fns, {'publish': crashes}):
            self.assertEqual(self.post('/api/publish')[0], 502)
        st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)

    def test_the_lock_is_keyed_by_the_destination_not_by_the_space(self):
        """Правило `folder_ok` пускає ту саму теку для двох просторів (і тека одного — типова теку іншого): задачі
        `t1` двох просторів ділили б `<тека>/t1` без взаємного виключення, коли замок на (простір, задача)."""
        s1 = self._register(self._space('s1', os.path.join(self.home, 'deai-work', 's1'), False, 't1'))
        s2 = self._register(self._space('s2', os.path.join(self.home, 'deai-work', 's2'), False, 't1'))
        shared = os.path.join(self.home, 'deai-published', 's1')           # типова тека s1
        self.set_folder(shared, s2)
        self.assertEqual(dm.published_root(s1, MID), shared)
        self.assertEqual(dm.published_root(s2, MID), shared)
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(self._publish_in('s1'), self._publish_in('s2'), entered, inside, release)
        self.assert_busy(*sec)
        self.assertEqual(seen, 1, 'публікації двох просторів у ТУ САМУ теку не виключають одна одну')
        self.assertEqual((first[0], first[1]['ok']), (200, True), first)
        self.assertEqual(kwargs, [{}])
        self.assertEqual(self._publish_in('s2')()[0], 200, 'після першої публікації друга проходить')
        self.assertEqual(sorted(os.listdir(shared)), ['t1'])
        self.assertTrue(os.path.isfile(os.path.join(shared, 't1', '.deai-published')))
        for rec in (s1, s2):
            pl = self.meta(os.path.join(rec['path'], 't1'))['publish_local']
            self.assertEqual(pl['path'], os.path.join(shared, 't1'))

    def test_tasks_with_different_destinations_do_not_block_each_other(self):
        """Замок — на призначення, не глобальний: публікація однієї задачі не тримає іншу (ні 409, ні очікування)."""
        self._register(self._space('s1', os.path.join(self.home, 'deai-work', 's1'), False, 't1'))
        entered, inside, second, release, kwargs = self._slow()
        first, sec, seen = self._concurrent(self._publish_in('off'), self._publish_in('s1'), entered, inside, release)
        self.assertEqual((sec[0], sec[1]['ok']), (200, True), sec)
        self.assertEqual(seen, 2, 'різні призначення чекали одне одного')
        self.assertEqual(first[0], 200)

    def test_the_lock_key_is_the_real_folder_and_the_case_folded_task_id(self):
        real = os.path.join(self.tmp, 'real-folder')
        os.makedirs(real)
        alias = os.path.join(self.tmp, 'alias-folder')
        os.symlink(real, alias)
        key = serve._publish_key(real, 'Task-1')
        self.assertEqual(serve._publish_key(alias, 'task-1'), key)         # посилання й регістр — те саме призначення
        self.assertEqual(serve._publish_key(real + '/', 'TASK-1'), key)
        self.assertEqual(serve._publish_key(real.upper(), 'task-1'), key)   # macOS: `Foo` і `foo` — одна тека
        self.assertNotEqual(serve._publish_key(real, 'task-2'), key)
        self.assertNotEqual(serve._publish_key(os.path.join(self.tmp, 'other'), 'task-1'), key)
        self.assertIs(serve._publish_lock(key), serve._publish_lock(serve._publish_key(alias, 'task-1')))
        self.assertIsNot(serve._publish_lock(key), serve._publish_lock(serve._publish_key(real, 'task-2')))

    def test_the_lock_key_folds_nfc_and_nfd_spellings_of_a_cyrillic_folder(self):
        """macOS бачить `й` (U+0439) і `и`+U+0306 як одну теку: ключ нормалізується в NFC (`folder_ok` теж)."""
        nfc = unicodedata.normalize('NFC', 'Тека-й-ї')
        nfd = unicodedata.normalize('NFD', 'Тека-й-ї')
        self.assertNotEqual(nfc, nfd, 'свідок: у тесті справді два різні написання')
        self.assertEqual(serve._publish_key(os.path.join(self.tmp, nfc), 'T'),
                         serve._publish_key(os.path.join(self.tmp, nfd), 'T'))
        self.assertEqual(serve._publish_key(os.path.join(self.tmp, 'p'), nfc),
                         serve._publish_key(os.path.join(self.tmp, 'p'), nfd))

    def test_the_folder_that_is_checked_locked_and_written_is_one_value(self):
        """`ctx` будується ОДИН раз, тека береться з нього: налаштування, змінене між перевіркою `folder_ok` і
        записом, не розводить ключ замка (і перевірену теку) з текою, у яку модуль справді пише."""
        f1, f2 = os.path.join(self.home, 'pubs', 'one'), os.path.join(self.home, 'pubs', 'two')
        self.set_folder(f1)
        real_ok, real_key = dm.folder_ok, serve._publish_key
        checked, keyed = [], []

        def changing(space, folder, **kw):
            checked.append(folder)
            res = real_ok(space, folder, **kw)
            self.set_folder(f2)                                 # налаштування змінили ПІСЛЯ перевірки
            return res

        def spy(folder, tid):
            keyed.append(folder)
            return real_key(folder, tid)

        with mock.patch.object(dm, 'folder_ok', changing), mock.patch.object(serve, '_publish_key', spy):
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        self.assertEqual(body['local']['path'], os.path.join(f1, 'tx'))
        self.assertEqual((set(checked), keyed), ({f1}, [f1]))
        self.assertTrue(os.path.isfile(os.path.join(f1, 'tx', 'index.html')))
        self.assertFalse(os.path.exists(f2), 'модуль писав у теку, якої не перевіряли й не замикали')

    def test_publish_local_is_written_from_a_fresh_read_of_iterations_json(self):
        """Між публікацією (`call`) і записом `publish_local` дизайнер перемкнув зелену крапку: запис зі старого
        `meta` (прочитаного на вході) відкотив би її."""
        real = dm.call

        def toggled_meanwhile(module, fn, ctx, *args, **kw):
            res = real(module, fn, ctx, *args, **kw)
            st, body = self.post('/api/publish-toggle', {'id': 'it2'})
            self.assertEqual((st, body['published']), (200, False), body)
            return res

        with mock.patch.object(dm, 'call', toggled_meanwhile):
            st, body = self.post('/api/publish')
        self.assertEqual(st, 200, body)
        meta = self.meta()
        self.assertEqual({i['id']: i['published'] for i in meta['iterations']}, {'it1': True, 'it2': False})
        self.assertEqual(meta['publish_local']['path'], self.dest)

    # ---- `/api/task` ----

    def test_api_task_shows_publish_local_and_a_module_gate_state(self):
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertEqual(task['preview_gate'], MODULE_GATE)
        self.assertNotIn('publish_local', task)
        self.assertEqual(set(task['preview_gate']), set(serve.preview_gate_state({'dir': self.tx_dir}, 'x')))
        self.assertEqual(self.post('/api/publish')[0], 200)
        st, task = self.get('/api/task')
        self.assertEqual(task['publish_local'], self.meta()['publish_local'])
        self.assertEqual(task['preview_gate'], MODULE_GATE)             # ПІСЛЯ збірки теж: без «ungated»
        self.assertIsNone(task['publish_url'])

    def test_api_task_in_a_league_space_has_the_old_gate_and_no_publish_local(self):
        st, task = self.get('/api/task', {'X-Canvas-Task': 'ty'})
        self.assertEqual(st, 200, task)
        self.assertEqual(task['preview_gate'], serve.preview_gate_state({'dir': self.ty_dir}, task['preview_password']))
        self.assertEqual(task['preview_gate']['state'], 'none')
        self.assertNotIn('publish_local', task)

    def test_api_task_does_not_fail_on_a_broken_space_json(self):
        """`/api/task` питає `capabilities()` (тотальна, не кидає), а не `provider()`: зіпсований `space.json`
        не мусить гасити весь інтерфейс. Модуля при цьому не видно — шлях гейта звичайний."""
        with open(os.path.join(self.off_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, task = self.get('/api/task')
        self.assertEqual(st, 200, task)
        self.assertNotEqual(task['preview_gate']['state'], 'module')

    # ---- пароль превʼю ЛІГА ----

    def test_preview_password_is_refused_unless_the_league_publishes(self):
        tasks = os.path.join(self.off_path, 'tasks.json')
        before = _bytes(tasks)
        st, body = self.post('/api/preview-password', {'password': 'abcd'})
        self.assertEqual((st, body), (409, serve.integrations_off_body('публікація зʼявиться з модулями')))
        self.assertEqual(_bytes(tasks), before, 'пароль записано в простір, де публікує модуль')
        # явно ввімкнений модуль у просторі З інтеграціями — теж не шлях ЛІГА
        dm.write_module_state(self.on, MID, enabled=True)
        st, body = self.post('/api/preview-password', {'password': 'abcd'}, {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, body['code']), (409, 'integrations-off'), body)
        # нечитабельний space.json у просторі без інтеграцій — та сама відповідь, а не `space-json-unreadable`
        with open(os.path.join(self.off_path, 'space.json'), 'w', encoding='utf-8') as fh:
            fh.write('{ це не json')
        st, body = self.post('/api/preview-password', {'password': 'abcd'})
        self.assertEqual((st, body), (409, serve.integrations_off_body('публікація зʼявиться з модулями')))

    def test_preview_password_still_works_for_the_league_path(self):
        dm.write_module_state(self.on, MID, enabled=False)                 # явне «вимкнено» у просторі ЛІГА
        st, body = self.post('/api/preview-password', {'password': 'abcd'}, {'X-Canvas-Task': 'ty'})
        self.assertEqual((st, body['ok'], body['preview_password']), (200, True, 'abcd'), body)
        with open(os.path.join(self.on_path, 'tasks.json'), encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['tasks']['ty']['preview_password'], 'abcd')


class ResealModuleBuilds(TaskFixture):
    """`ops/reseal_gate.py` ніколи не перепечатує й не деплоїть збірку модуля: вона локальна, без `comment-layer/`,
    і її гейт (пароль модуля) — не пароль ЛІГА. Рішення — за АРТЕФАКТОМ (`publish/comment-layer/`), а не за
    `iterations.json`: збірка ЛІГА має коментатор завжди, збірка модуля (`comments=False`) — ніколи."""

    def _reseal(self, *args):
        spec = importlib.util.spec_from_file_location('reseal_gate', os.path.join(ROOT, 'ops', 'reseal_gate.py'))
        rg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rg)
        deployed = []
        rg.deploy = lambda pub, task=None: deployed.append(pub) or (True, '')
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['reseal_gate.py', *args]), contextlib.redirect_stdout(out):
            rg.main()
        return out.getvalue(), deployed

    def _wrapper(self):
        return os.path.join(self.tmp, 'publish', 'index.html')

    def test_a_league_build_is_resealed_and_deployed(self):
        """Контроль: без нього «модуль пропущено» могло б означати, що reseal не робить нічого."""
        task, tid, its = self._args()
        serve.build_preview(task, tid, its, comments=True,
                            gate_pw=serve.preview_password(serve.load_tasks(), task))
        out, deployed = self._reseal('fixture')
        self.assertIn('передеплоєно', out)
        self.assertEqual(deployed, [os.path.join(self.tmp, 'publish')])

    def test_a_module_build_is_skipped_before_anything_is_rewritten_or_deployed(self):
        for gate_pw in (None, 'pw-модуля'):
            for args in (('fixture',), ('--build', 'fixture'), ()):
                with self.subTest(gate_pw=gate_pw, args=args):
                    task, tid, its = self._args()
                    serve.build_preview(task, tid, its, comments=False, gate_pw=gate_pw)
                    before = _bytes(self._wrapper())
                    out, deployed = self._reseal(*args)
                    self.assertIn('локальна збірка модуля', out)
                    self.assertNotIn('передеплоєно', out)
                    self.assertNotIn('перезібрано', out)
                    self.assertEqual(deployed, [], 'збірку модуля відправлено на Vercel')
                    self.assertEqual(_bytes(self._wrapper()), before, 'обгортку модуля перезаписано')

    def test_the_decision_is_made_from_the_artifact_not_from_iterations_json(self):
        """`publish_local` у `iterations.json` нічого не міняє: збірка ЛІГА з ним усе одно деплоїться, а збірка
        модуля БЕЗ нього (метадані втрачено) усе одно пропускається."""
        task, tid, its = self._args()
        meta = serve.load_meta(task)
        meta['publish_local'] = {'module': 'static-publish', 'path': '/x', 'published_at': '2026-10-15T10:00:00Z'}
        serve.save_meta(task, meta)
        serve.build_preview(task, tid, its, comments=True, gate_pw='1100')
        out, deployed = self._reseal('fixture')
        self.assertEqual(len(deployed), 1, out)
        meta.pop('publish_local')
        serve.save_meta(task, meta)
        serve.build_preview(task, tid, its, comments=False, gate_pw=None)
        out, deployed = self._reseal('fixture')
        self.assertIn('локальна збірка модуля', out)
        self.assertEqual(deployed, [])


if __name__ == '__main__':
    unittest.main()
