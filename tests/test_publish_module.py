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
"""
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))     # пакета `tests` нема — охоронець поруч
import serve  # noqa: E402
import spaces_guard  # noqa: E402

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


class BuildPreview(unittest.TestCase):
    """`serve.build_preview` напряму на тимчасовій задачі + `/api/publish` (build_only) на тій самій."""

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


if __name__ == '__main__':
    unittest.main()
