import ast
import contextlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'app'))
import serve  # noqa: E402


def _git(args, cwd):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t',
                           *args], cwd=cwd, capture_output=True, text=True)


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'},
                                 method='POST')
    return urllib.request.urlopen(req)


class ServeTest(unittest.TestCase):
    """Живой сервер + задача-фикстура с одной итерацией it1 (модель «ітерації»)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-task-')
        it1 = os.path.join(cls.tmp, 'iterations', 'it1')
        os.makedirs(it1)
        with open(os.path.join(it1, 'index.html'), 'w') as f:
            f.write('<!DOCTYPE html><html><head><title>t</title></head>'
                    '<body><h1>Мокап</h1></body></html>')
        with open(os.path.join(it1, 'notes.py'), 'w') as f:
            f.write('# службове, не копіюється при форку')
        with open(os.path.join(cls.tmp, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '01.01.2026 10:00',
                                       'note': 'старт', 'published': False}],
                       'publish_url': None}, f)
        # «удалённый» GitLab: локальный bare-репо + сид с веткой main
        cls.remote = tempfile.mkdtemp(prefix='dc-remote-') + '/origin.git'
        subprocess.run(['git', 'init', '--bare', '-b', 'main', cls.remote],
                       capture_output=True)
        seed = tempfile.mkdtemp(prefix='dc-seed-')
        _git(['clone', cls.remote, seed], os.path.dirname(seed))
        open(os.path.join(seed, 'README.md'), 'w').write('# united-design\n')
        _git(['add', '-A'], seed)
        _git(['commit', '-q', '-m', 'seed'], seed)
        _git(['push', '-q', 'origin', 'main'], seed)
        shutil.rmtree(seed, ignore_errors=True)
        cls.mirrors = tempfile.mkdtemp(prefix='dc-mirrors-')
        os.environ['DC_MIRRORS_DIR'] = cls.mirrors
        cls.dwroot = tempfile.mkdtemp(prefix='dc-dwroot-')
        # ⛔ Конфіг задач — у ТИМЧАСОВІЙ теці, а не живий tasks.json. Раніше тут був
        # backup+запис поверх робочого файла: падіння тесту між setUp і tearDown
        # лишало конфіг дизайнера фікстурою, save_tasks() затирав його .bak, а
        # _overview_sync пушив `fixture`/`demo2` на командний дашборд.
        # DC_TASKS_FILE читається serve.tasks_path() на кожен виклик, тому порядок
        # відносно `import serve` не важливий. Сиблінг .bak від save_tasks() теж
        # ляже сюди — живий бекап лишається недоторканим.
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-cfg-')
        cls.tasks_file = os.path.join(cls.cfgdir, 'tasks.json')
        os.environ['DC_TASKS_FILE'] = cls.tasks_file
        os.environ['DC_NO_OVERVIEW'] = '1'   # жодного пуша реєстру в прод-Supabase
        # Особа машини — ФІКСТУРНА, а не git-конфіг того, хто запустив тест:
        # інакше підпис ітерації залежав би від машини, і на раннері без
        # `user.name` перевірка авторства мовчки перевіряла б порожній рядок.
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        with open(cls.tasks_file, 'w') as f:
            json.dump({'current': 'fixture', 'design_work_root': cls.dwroot,
                       'tasks': {'fixture': {
                           'dir': cls.tmp, 'title': 'Фікстура', 'jira': 'TEST-1',
                           'gitlab': {'repo': cls.remote,
                                      'path': 'mockup/fixture'}}}}, f)
        cls.httpd = serve.make_server(0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        # Відновлювати живий tasks.json з бекапа більше НЕ потрібно: ми його не
        # чіпали — уся фікстура жила в cls.cfgdir.
        cls.httpd.shutdown()
        os.environ.pop('DC_MIRRORS_DIR', None)
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        os.environ.pop('DC_IDENTITY_NAME', None)
        os.environ.pop('DC_IDENTITY_EMAIL', None)
        for d in (cls.tmp, cls.mirrors, cls.dwroot, cls.cfgdir,
                  os.path.dirname(cls.remote)):
            shutil.rmtree(d, ignore_errors=True)

    def test_1_task_endpoint(self):
        body = json.load(urllib.request.urlopen(self.base + '/api/task'))
        self.assertEqual(body['id'], 'fixture')
        self.assertEqual([i['id'] for i in body['iterations']], ['it1'])
        # ⛔ Ключ машини потрібен САМОМУ канвасу: git-конфіг браузеру невідомий,
        # і без цього поля «своя/чужа» він порахувати не може взагалі — мітка
        # чужої ітерації тихо не зʼявилась би ніде.
        self.assertEqual(body['my_key'], 'lead@example.com')

    def test_2_new_iteration_forks_copy(self):
        # нова ітерація = копія обраної (from=it1); .py не копіюється
        body = json.load(post(self.base + '/api/iteration', {'from': 'it1', 'note': 'копія'}))
        self.assertEqual(body['iteration']['id'], 'it2')
        self.assertEqual(body['iteration']['from'], 'it1')
        self.assertFalse(body['iteration']['published'])
        it2 = os.path.join(self.tmp, 'iterations', 'it2')
        self.assertTrue(os.path.exists(os.path.join(it2, 'index.html')))
        self.assertFalse(os.path.exists(os.path.join(it2, 'notes.py')))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, '.git')))
        self.assertTrue(body['iteration'].get('git'))
        # ⛔ Підпис автора — саме тут, а не окремим тестом хелпера: `_stamp_author`
        # може бути ідеальним і НЕ покликаним, і тоді ітерації народжувались би
        # безіменними, а юніт хелпера лишався б зеленим.
        self.assertEqual(body['iteration']['author'], 'Lead')
        self.assertEqual(body['iteration']['author_key'], 'lead@example.com')
        # копія містить той самий макет
        self.assertIn('Мокап', open(os.path.join(it2, 'index.html')).read())

    def test_3_commented_comment_modes(self):
        # дефолт — локальний режим (файл, не Supabase)
        html = urllib.request.urlopen(self.base + '/commented?it=it1').read().decode()
        self.assertIn('local-adapter.js', html)
        self.assertIn('/api/local-comments', html)
        self.assertIn('Мокап', html)
        # інспектор — обидва РОБОЧІ канали (у превʼю й у чистому макеті його нема)
        self.assertIn('inspector.js', html)
        # ch=project — канал Supabase на ЗАДАЧУ (не на ітерацію; ітерація йде через version)
        proj = urllib.request.urlopen(self.base + '/commented?it=it1&ch=project').read().decode()
        self.assertIn('CommentLayer.init', proj)
        self.assertIn('dc/fixture', proj)
        self.assertNotIn('dc/fixture/it1', proj)
        # Інспектор — в ОБОХ робочих каналах (правка 02.09.2026): у «Проєкті»
        # він був мертвий, і кнопка смуги тихо нічого не робила. Межа лишилась
        # рівно одна — publish (асерти в test_5_publish_… нижче).
        self.assertIn('inspector.js', proj)
        # Вкладки аудиторій — теж в ОБОХ робочих каналах (правка 02.09.2026):
        # перемикач переїхав зі смуги в панель самого коментатора, і саме
        # РОУТ доводить, що обидва сніпети його везуть. Межа знову одна —
        # publish (асерти в test_5_publish_… нижче).
        self.assertIn('dc-audience', html)
        self.assertIn('dc-audience', proj)
        # bare=1 — без будь-яких коментаторів
        bare = urllib.request.urlopen(self.base + '/commented?it=it1&bare=1').read().decode()
        self.assertNotIn('CommentLayer.init', bare)
        self.assertNotIn('local-adapter.js', bare)
        self.assertNotIn('inspector.js', bare)

    def test_4_commented_unknown_iteration_404(self):
        for it in ('itX', 'current'):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(self.base + f'/commented?it={it}')
            self.assertEqual(ctx.exception.code, 404)

    def test_5_publish_builds_switcher_and_gate(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(self.base + '/api/publish', {'build_only': True})
        self.assertEqual(ctx.exception.code, 400)                 # нічого не позначено
        body = json.load(post(self.base + '/api/publish-toggle', {'id': 'it1'}))
        self.assertTrue(body['published'])
        body = json.load(post(self.base + '/api/publish', {'build_only': True}))
        self.assertTrue(body['ok'])
        pub = body['dir']
        wrapper = open(os.path.join(pub, 'index.html')).read()
        self.assertIn('authgate', wrapper)
        # ⛔ Інспектор — ЛИШЕ локальний канал. Асерти вище стережуть роут
        # /commented, але вимогу спеки «інспектора немає в publish» досі
        # ніхто не перевіряв на самому АРТЕФАКТІ. Сторож саме тут.
        self.assertNotIn('inspector', wrapper)
        # Назви сторінок переїхали з обгортки в `manifest.json` (02.09.2026):
        # обгортка стала тонким каркасом, і назва тепер мусить бути РІВНО в
        # одному місці. Перевіряємо обидва боки — щоб «переїхало» не стало
        # «зникло»: у маніфесті назва є, в каркасі її немає.
        man = json.load(open(os.path.join(pub, 'manifest.json'), encoding='utf-8'))
        self.assertIn('Головна', [p['name'] for p in man['pages']])
        self.assertNotIn('Головна', wrapper)
        it_page = open(os.path.join(pub, 'it1', 'index.html')).read()
        # ⛔ Гейт у ВНУТРІШНІЙ сторінці, не лише в обгортці. Інцидент 03.08.2026:
        # `dc-sample.vercel.app/` пароль просив, а `/it4/` віддавав макет. Цикл,
        # який вставляє гейт, переписаний 04.08.2026 — сторож саме тут.
        self.assertIn('authgate', it_page)
        self.assertNotIn('inspector', it_page)        # і у ВНУТРІШНІЙ сторінці теж
        # ⛔ Вкладки аудиторій — теж лише робоче місце. Сторож стоїть на самому
        # АРТЕФАКТІ, а не на сигнатурі `inject_comment_layer`: `audiences` там
        # прапорець із дефолтом `False`, тож тест функції зеленів би і після
        # `audiences=True`, дописаного у виклик `_publish`. Ціна помилки —
        # робочий фідбек Клоду, запропонований сторонньому глядачеві на
        # чужій машині.
        self.assertNotIn('dc-audience', it_page)
        self.assertNotIn('audiences', it_page)
        self.assertNotIn('dc-audience', wrapper)
        self.assertIn('dc/fixture', it_page)          # канал на задачу
        self.assertNotIn('dc/fixture/it1', it_page)   # ітерація — через version, не в projectId
        self.assertNotIn('/internal', it_page)
        self.assertTrue(os.path.exists(
            os.path.join(pub, 'comment-layer', 'comment-layer.min.js')))

    def test_5b_publish_carries_shared_assets_of_multipage_iteration(self):
        """Багатосторінкова ітерація БЕЗ кореневої сторінки везе спільні assets.

        Інцидент LIGA-7010 (31.08.2026): у publish/<it>/ поїхали теки сторінок
        без `assets/`, кожна сторінка тягнула `../assets/…` у 404 — превʼю
        відкривалось білим. Раніше корінь ітерації копіювався лише як побічний
        ефект сторінки з rel == ''. Сторож саме тут.
        """
        it_dir = os.path.join(self.tmp, 'iterations', 'it1')
        # спільні файли ітерації + дві сторінки, кореневої серед них НЕМА
        os.makedirs(os.path.join(it_dir, 'assets'), exist_ok=True)
        with open(os.path.join(it_dir, 'assets', 'shared.css'), 'w') as fh:
            fh.write('.x{color:red}')
        for name in ('alpha', 'beta'):
            os.makedirs(os.path.join(it_dir, name), exist_ok=True)
            with open(os.path.join(it_dir, name, 'index.html'), 'w') as fh:
                fh.write(f'<link rel="stylesheet" href="../assets/shared.css"><body>{name}</body>')
        with open(os.path.join(it_dir, 'pages.json'), 'w') as fh:
            json.dump({'pages': [{'id': 'alpha', 'name': 'Альфа', 'published': True},
                                 {'id': 'beta', 'name': 'Бета', 'published': False}]}, fh)

        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        was = next(i for i in task['iterations'] if i['id'] == 'it1').get('published')
        if not was:
            json.load(post(self.base + '/api/publish-toggle', {'id': 'it1'}))
        body = json.load(post(self.base + '/api/publish', {'build_only': True}))
        pub = body['dir']
        # спільне доїхало
        self.assertTrue(os.path.exists(os.path.join(pub, 'it1', 'assets', 'shared.css')))
        # опублікована сторінка на місці й з гейтом
        alpha = open(os.path.join(pub, 'it1', 'alpha', 'index.html')).read()
        self.assertIn('authgate', alpha)
        # ⛔ знята з превʼю сторінка НЕ їде, хоч і лежить у корені ітерації
        self.assertFalse(os.path.exists(os.path.join(pub, 'it1', 'beta')))
        if not was:
            json.load(post(self.base + '/api/publish-toggle', {'id': 'it1'}))

    def test_5b2_explicit_main_page_does_not_carry_the_whole_iteration(self):
        """Явна сторінка `main` (page_rel == '') не везе в превʼю ВСЮ ітерацію.

        Її src — уся тека ітерації, а `copy_mockup` копіює її цілком: разом із
        теками інших (зокрема СХОВАНИХ) сторінок, `shots/`, `pages.json`,
        `flow.json` (A4 ревʼю). Для кореня їдуть лише файли кореня; спільні
        теки вже привіз `copy_iteration_shared`.
        """
        it_dir = os.path.join(self.tmp, 'iterations', 'it1')
        pj = os.path.join(it_dir, 'pages.json')
        backup = open(pj, encoding='utf-8').read() if os.path.isfile(pj) else None
        made = []
        for d in ('x', 'shots', 'assets'):
            if not os.path.isdir(os.path.join(it_dir, d)):
                made.append(os.path.join(it_dir, d))
            os.makedirs(os.path.join(it_dir, d), exist_ok=True)
        for rel in ('x/index.html', 'shots/a.webp', 'assets/s.css', 'flow.json'):
            with open(os.path.join(it_dir, rel), 'w') as fh:
                fh.write('x')
        had_index = os.path.isfile(os.path.join(it_dir, 'index.html'))
        with open(os.path.join(it_dir, 'index.html'), 'w') as fh:
            fh.write('<html><body>main</body></html>')
        with open(pj, 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': 'main', 'name': 'Головна', 'kind': 'page'},
                                 {'id': 'x', 'name': 'X', 'kind': 'page',
                                  'published': False}]}, fh)

        def restore():
            for d in made:
                shutil.rmtree(d, ignore_errors=True)
            for f in ('flow.json',) + (() if had_index else ('index.html',)):
                try:
                    os.remove(os.path.join(it_dir, f))
                except OSError:
                    pass
            if backup is None:
                os.remove(pj)
            else:
                with open(pj, 'w', encoding='utf-8') as fh:
                    fh.write(backup)
        self.addCleanup(restore)
        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        was = next(i for i in task['iterations'] if i['id'] == 'it1').get('published')
        if not was:
            json.load(post(self.base + '/api/publish-toggle', {'id': 'it1'}))
            self.addCleanup(lambda: json.load(
                post(self.base + '/api/publish-toggle', {'id': 'it1'})))
        pub = json.load(post(self.base + '/api/publish', {'build_only': True}))['dir']
        self.assertTrue(os.path.isfile(os.path.join(pub, 'it1', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(pub, 'it1', 'assets', 's.css')))
        for leak in ('x', 'shots', 'pages.json', 'flow.json'):
            self.assertFalse(os.path.exists(os.path.join(pub, 'it1', leak)), leak)

    def test_5b3_tree_with_only_main_still_publishes_shared_dirs(self):
        """Дерево з ОДНІЄЮ `main`: спільні теки (assets/) їдуть через
        `copy_iteration_shared`, а не через копію теки сторінки."""
        it_dir = os.path.join(self.tmp, 'iterations', 'it1')
        pj = os.path.join(it_dir, 'pages.json')
        backup = open(pj, encoding='utf-8').read() if os.path.isfile(pj) else None
        assets = os.path.join(it_dir, 'assets')
        made_assets = not os.path.isdir(assets)
        os.makedirs(assets, exist_ok=True)
        with open(os.path.join(assets, 'only.css'), 'w') as fh:
            fh.write('.x{}')
        had_index = os.path.isfile(os.path.join(it_dir, 'index.html'))
        with open(os.path.join(it_dir, 'index.html'), 'w') as fh:
            fh.write('<html><body>main</body></html>')
        with open(pj, 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': 'main', 'name': 'Головна', 'kind': 'page'}]}, fh)

        def restore():
            if made_assets:
                shutil.rmtree(assets, ignore_errors=True)
            else:
                try:
                    os.remove(os.path.join(assets, 'only.css'))
                except OSError:
                    pass
            if not had_index:
                try:
                    os.remove(os.path.join(it_dir, 'index.html'))
                except OSError:
                    pass
            if backup is None:
                os.remove(pj)
            else:
                with open(pj, 'w', encoding='utf-8') as fh:
                    fh.write(backup)
        self.addCleanup(restore)
        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        was = next(i for i in task['iterations'] if i['id'] == 'it1').get('published')
        if not was:
            json.load(post(self.base + '/api/publish-toggle', {'id': 'it1'}))
            self.addCleanup(lambda: json.load(
                post(self.base + '/api/publish-toggle', {'id': 'it1'})))
        pub = json.load(post(self.base + '/api/publish', {'build_only': True}))['dir']
        self.assertTrue(os.path.isfile(os.path.join(pub, 'it1', 'index.html')))
        self.assertTrue(os.path.isfile(os.path.join(pub, 'it1', 'assets', 'only.css')))
        self.assertFalse(os.path.exists(os.path.join(pub, 'it1', 'pages.json')))

    def _fixture_with_shots(self):
        """it1 із двома сторінками (одна знята з превʼю) і кадрами на всі чотири.

        Кадри прибираємо за собою: далі в класі йдуть синк і форк, які возять
        КОРІНЬ ітерації, і 4 фальшиві .webp мандрували б по тестах як справжні.
        """
        it_dir = os.path.join(self.tmp, 'iterations', 'it1')
        for name in ('alpha', 'beta'):
            os.makedirs(os.path.join(it_dir, name), exist_ok=True)
            with open(os.path.join(it_dir, name, 'index.html'), 'w') as fh:
                fh.write(f'<body>{name}</body>')
        with open(os.path.join(it_dir, 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': 'alpha', 'name': 'Альфа', 'published': True},
                                 {'id': 'beta', 'name': 'Бета', 'published': False}]}, fh)
        shots = os.path.join(it_dir, 'shots')
        os.makedirs(shots, exist_ok=True)
        self.addCleanup(shutil.rmtree, shots, True)
        keys = ('alpha', 'alpha@768', 'beta', 'beta@768')
        for k in keys:
            with open(os.path.join(shots, k + '.webp'), 'wb') as fh:
                fh.write(b'webp:' + k.encode())
        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        was = next(i for i in task['iterations'] if i['id'] == 'it1').get('published')
        if not was:
            json.load(post(self.base + '/api/publish-toggle', {'id': 'it1'}))
            self.addCleanup(lambda: json.load(
                post(self.base + '/api/publish-toggle', {'id': 'it1'})))
        return shots, keys

    def test_5c_publish_carries_shell_frames_and_manifest(self):
        """Зовнішня оболонка в артефакті: `shell/`, кадри під фільтром, маніфест.

        ⛔ Кадр знятої з превʼю сторінки перевіряється по ВСЬОМУ дереву publish/,
        а не лише в `_frames/`. Причина заміряна, не вигадана: `shots/` лежить у
        КОРЕНІ ітерації, а `copy_iteration_shared` везе корінь цілком — тобто
        до цієї правки всі кадри, і зняті теж, уже їхали в
        `publish/<it>/shots/` і деплоїлись на Vercel (перевірено на
        boss-interface 02.09.2026: `publish/it3/shots/manifest.json` на диску).
        Фільтр у `publish_frames` без виключення `shots` був би театром: поруч
        лежала б неповна копія без фільтра.
        """
        shots, keys = self._fixture_with_shots()
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            json.dump({'checkedAt': '02.09.2026 15:16',
                       'shots': {k: {'w': 768 if '@' in k else 1280,
                                     'h': 4300 if '@' in k else 6879} for k in keys}}, fh)
        body = json.load(post(self.base + '/api/publish', {'build_only': True}))
        pub = body['dir']

        # спільні модулі — рівно ті, що в константі (свій дубль тут був би
        # переказом константи й не ловив би нового модуля)
        for m in serve.SHELL_MODULES:
            self.assertTrue(os.path.isfile(os.path.join(pub, 'shell', m)),
                            f'publish/shell/{m} — 404 у глядача')

        # PWA («Deai Canvas») — лише локальний інструмент: публікація не везе ні
        # маніфесту застосунку, ні service worker, ні сторінкового боку PWA, і
        # обгортка на них не посилається. Дивимось ВЕСЬ артефакт, а не лише
        # `shell/`: `manifest.json` поруч — інший файл (стан превʼю), його
        # імʼя НЕ збігається з `manifest.webmanifest`.
        for dirpath, _dirs, files in os.walk(pub):
            for fn in files:
                self.assertNotIn(fn, ('manifest.webmanifest', 'sw.js', 'pwa.js', 'pwa-offline.js'),
                                 f'у публікацію приїхав PWA-файл: {os.path.join(dirpath, fn)}')
        with open(os.path.join(pub, 'index.html'), encoding='utf-8') as fh:
            wrapper = fh.read()
        self.assertNotIn('manifest.webmanifest', wrapper)
        self.assertNotIn('serviceWorker', wrapper)

        man = json.load(open(os.path.join(pub, 'manifest.json'), encoding='utf-8'))
        self.assertEqual(man['task'], 'Фікстура')
        self.assertEqual([p['key'] for p in man['pages']], ['alpha'])
        self.assertEqual(sorted(man['frames']['it1']), ['alpha', 'alpha@768'])
        self.assertEqual(man['widths'], [768, serve.CANVAS_W])
        self.assertEqual(body['frames'], 2)
        self.assertNotIn('frames_warnings', body)

        # кадр опублікованої сторінки на місці, за шляхом із маніфеста
        rec = man['frames']['it1']['alpha@768']
        self.assertTrue(os.path.isfile(os.path.join(pub, *rec['path'].split('/'))))
        # ⛔ Розмір, заміряний зʼємкою, доїхав крізь УСЮ публікацію. Юніт на
        # `publish_frames` цього не покриває: між ним і статикою стоїть
        # `publish_manifest` і сам `json.dump` — а оболонка читає саме файл.
        # Без розміру «Огляд» стоїть заглушкою й сідає під справжні пропорції
        # на очах глядача.
        self.assertEqual((rec['w'], rec['h']), (768, 4300))
        self.assertEqual(man['frames']['it1']['alpha'],
                         {'path': 'it1/_frames/alpha.webp', 'w': 1280, 'h': 6879})
        # ⛔ кадру знятої сторінки немає НІДЕ в publish/
        leaked = [os.path.join(r, f) for r, _, fs in os.walk(pub) for f in fs
                  if f.startswith('beta') and f.endswith('.webp')]
        self.assertEqual(leaked, [], 'кадр сторінки, знятої з превʼю, поїхав глядачу')

    def test_5d_broken_shots_manifest_warns_but_publishes(self):
        """Битий `shots/manifest.json` не валить публікацію — але й не мовчить.

        Мовчазна гілка тут була б найгіршою з трьох: превʼю зібралось, посилання
        відправлене, «Огляд» у глядача порожній, і ніде жодного слова про те, що
        кадри не поїхали.
        """
        shots, _ = self._fixture_with_shots()
        with open(os.path.join(shots, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write('{битий')
        body = json.load(post(self.base + '/api/publish', {'build_only': True}))
        self.assertTrue(body['ok'])
        self.assertEqual(body['frames'], 0)
        self.assertTrue(any('it1' in w for w in body['frames_warnings']),
                        body.get('frames_warnings'))
        # сам макет усе одно доїхав
        self.assertTrue(os.path.isfile(
            os.path.join(body['dir'], 'it1', 'alpha', 'index.html')))

    def test_6_comments_endpoint_shape(self):
        # канал на задачу: internal → підканал, external → базовий (comment_project or dc/<tid>)
        body = json.load(urllib.request.urlopen(
            self.base + '/comments?channel=internal'))
        self.assertEqual(body['project'], 'dc/fixture/internal')
        self.assertIsInstance(body['comments'], list)
        ext = json.load(urllib.request.urlopen(self.base + '/comments?channel=external'))
        self.assertEqual(ext['project'], 'dc/fixture')

    def test_7_delete_iteration(self):
        self.assertTrue(json.load(post(self.base + '/api/iteration-delete',
                                       {'id': 'it2'}))['ok'])
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, 'iterations', 'it2')))
        body = json.load(urllib.request.urlopen(self.base + '/api/task'))
        self.assertEqual([i['id'] for i in body['iterations']], ['it1'])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(self.base + '/api/iteration-delete', {'id': 'it9'})
        self.assertEqual(ctx.exception.code, 404)

    def test_8_gitlab_sync_pushes_selected_iteration(self):
        st = json.load(urllib.request.urlopen(self.base + '/api/gitlab-status?it=it1'))
        self.assertTrue(st['configured'] and st['dirty'] and st['behind'] == 0)
        r = json.load(post(self.base + '/api/gitlab-sync', {'it': 'it1'}))
        self.assertTrue(r['ok'] and r['changed'] and r['pushed'])
        co = tempfile.mkdtemp(prefix='dc-check-')
        _git(['clone', '-q', self.remote, co], os.path.dirname(co))
        self.assertTrue(os.path.exists(
            os.path.join(co, 'mockup', 'fixture', 'index.html')))
        self.assertFalse(os.path.exists(
            os.path.join(co, 'mockup', 'fixture', 'notes.py')))
        shutil.rmtree(co, ignore_errors=True)
        st = json.load(urllib.request.urlopen(self.base + '/api/gitlab-status?it=it1'))
        self.assertFalse(st['dirty'])
        r = json.load(post(self.base + '/api/gitlab-sync', {'it': 'it1'}))
        self.assertTrue(r['ok'] and not r['changed'])

    def test_9_gitlab_pull_imports_iteration(self):
        co = tempfile.mkdtemp(prefix='dc-peer-')
        _git(['clone', '-q', self.remote, co], os.path.dirname(co))
        with open(os.path.join(co, 'mockup', 'fixture', 'index.html'), 'a') as f:
            f.write('<!-- правка колеги -->')
        _git(['add', '-A'], co)
        _git(['commit', '-q', '-m', 'peer edit'], co)
        _git(['push', '-q', 'origin', 'main'], co)
        shutil.rmtree(co, ignore_errors=True)
        st = json.load(urllib.request.urlopen(self.base + '/api/gitlab-status?it=it1'))
        self.assertGreaterEqual(st['behind'], 1)
        before = json.load(urllib.request.urlopen(self.base + '/api/task'))['iterations']
        r = json.load(post(self.base + '/api/gitlab-pull', {}))
        self.assertTrue(r['ok'])
        self.assertTrue(r['iteration']['note'].startswith('оновлення з GitLab'))
        self.assertTrue(r['iteration'].get('from_gitlab'))
        after = json.load(urllib.request.urlopen(self.base + '/api/task'))['iterations']
        self.assertEqual(len(after), len(before) + 1)

    def test_a1_sync_blocked_when_behind(self):
        co = tempfile.mkdtemp(prefix='dc-peer2-')
        _git(['clone', '-q', self.remote, co], os.path.dirname(co))
        with open(os.path.join(co, 'mockup', 'fixture', 'index.html'), 'a') as f:
            f.write('<!-- ще правка -->')
        _git(['add', '-A'], co)
        _git(['commit', '-q', '-m', 'peer edit 2'], co)
        _git(['push', '-q', 'origin', 'main'], co)
        shutil.rmtree(co, ignore_errors=True)
        r = json.load(post(self.base + '/api/gitlab-sync', {'it': 'it1'}))
        self.assertFalse(r['ok'])
        self.assertEqual(r['blocked'], 'behind')

    def test_b1_task_new_and_switch(self):
        r = json.load(post(self.base + '/api/task-new',
                           {'id': 'demo2', 'title': 'Demo 2', 'profile': 'tool'}))
        self.assertTrue(r['ok'] and not r['cloned'])
        # bootstrap створює iterations/it1, не корневой index.html
        self.assertTrue(os.path.isfile(
            os.path.join(self.dwroot, 'demo2', 'iterations', 'it1', 'index.html')))
        lst = json.load(urllib.request.urlopen(self.base + '/api/tasks'))
        self.assertEqual(lst['current'], 'demo2')
        self.assertIn('demo2', [t['id'] for t in lst['tasks']])
        body = json.load(urllib.request.urlopen(self.base + '/api/task'))
        self.assertEqual([i['id'] for i in body['iterations']], ['it1'])
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(self.base + '/api/task-new', {'id': 'demo2'})
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(json.load(post(self.base + '/api/task-switch',
                                        {'id': 'fixture'}))['current'], 'fixture')

    # --- автосинк (Stop-хук) + стан публікації, що їде колегам ---

    def _newest_it(self):
        its = json.load(urllib.request.urlopen(self.base + '/api/task'))['iterations']
        return max(its, key=lambda i: serve._dir_mtime(
            os.path.join(self.tmp, 'iterations', i['id'])))['id']

    def _touch_newest(self, mark):
        it = self._newest_it()
        with open(os.path.join(self.tmp, 'iterations', it, 'index.html'), 'a') as f:
            f.write(mark)
        return it

    def test_c1_autosync_respects_pull_first_guard(self):
        """На GitLab новіше → автосинк НЕ пушить поверх (a1 лишив remote попереду)."""
        self._touch_newest('<!-- правка в канвасі -->')
        r = json.load(post(self.base + '/api/autosync', {}))
        self.assertFalse(r['ok'])
        self.assertEqual(r['blocked'], 'behind')

    def test_c2_autosync_pushes_then_goes_quiet(self):
        self.assertTrue(json.load(post(self.base + '/api/gitlab-pull', {}))['ok'])
        it = self._touch_newest('<!-- нове оновлення -->')
        r = json.load(post(self.base + '/api/autosync', {}))
        self.assertTrue(r['ok'] and r['changed'] and r['pushed'])
        self.assertEqual(r['it'], it)          # поїхала саме робоча ітерація
        # Повторний виклик без правок — тиша: хук стріляє після КОЖНОЇ відповіді
        # Claude, тож порожні коміти тут були б катастрофою для історії репо.
        again = json.load(post(self.base + '/api/autosync', {}))
        self.assertTrue(again['ok'])
        self.assertFalse(again['changed'])
        self.assertEqual(again['reason'], 'clean')

    def test_c3_publish_state_travels_to_colleagues(self):
        it = self._newest_it()
        # деплою в тесті немає — кладемо URL у meta так само, як це робить _publish
        p = os.path.join(self.tmp, 'iterations.json')
        meta = json.load(open(p))
        meta['publish_url'] = 'https://pv-12345678.vercel.app'
        meta['published_at'] = '03.08.2026 10:00'
        for i in meta['iterations']:
            if i['id'] == it:
                i['published'] = True
        json.dump(meta, open(p, 'w'), ensure_ascii=False)
        self._touch_newest('<!-- з публікацією -->')
        r = json.load(post(self.base + '/api/autosync', {}))
        self.assertTrue(r['ok'] and r['pushed'])

        co = tempfile.mkdtemp(prefix='dc-state-')
        _git(['clone', '-q', self.remote, co], os.path.dirname(co))
        mock = os.path.join(co, 'mockup', 'fixture')
        state = json.load(open(os.path.join(mock, serve.STATE_FILE)))
        self.assertEqual(state['publish_url'], 'https://pv-12345678.vercel.app')
        self.assertTrue(state['published'])
        # ⛔ Файл стану не має впливати на відбиток макета — інакше кожен синк
        # виглядав би як зміна верстки і hash-порівняння зламалось би.
        h_with = serve.mockup_hash(mock)
        os.remove(os.path.join(mock, serve.STATE_FILE))
        self.assertEqual(h_with, serve.mockup_hash(mock))
        shutil.rmtree(co, ignore_errors=True)

    def test_c4_pull_carries_publish_state(self):
        """Колега тягне макет → бачить, що він опублікований, і має лінк."""
        p = os.path.join(self.tmp, 'iterations.json')
        meta = json.load(open(p))
        meta['publish_url'], meta['published_at'] = None, None   # «чужа» машина
        json.dump(meta, open(p, 'w'), ensure_ascii=False)
        r = json.load(post(self.base + '/api/gitlab-pull', {}))
        self.assertTrue(r['ok'])
        # Вміст на origin тут байт-у-байт наш (щойно запушили автосинком), тому
        # ітерації-копії не заводимо — але позначка «показувати в превью» і
        # лінк публікації мусять приїхати однаково. Раніше цей рядок читав
        # `r['iteration']['published']`; ітерація тепер не створюється, а
        # перевіряти треба те саме: чи бачить колега опублікований макет.
        self.assertTrue(r.get('unchanged'), f'вміст той самий, а pull завів ітерацію: {r}')
        meta = json.load(open(os.path.join(self.tmp, 'iterations.json')))
        same = next(i for i in meta['iterations'] if i['id'] == r['same_as'])
        self.assertTrue(same['published'])   # було b'published': False завжди
        body = json.load(urllib.request.urlopen(self.base + '/api/task'))
        self.assertEqual(body['publish_url'], 'https://pv-12345678.vercel.app')
        self.assertEqual(body['published_at'], '03.08.2026 10:00')

    def test_d1_local_comments_go_through_the_helper(self):
        """Локальні коментарі — четвертий писар стану, і він ходить тим самим хелпером.

        Стереже САМЕ ПРОВІД: шлях, формат, round-trip. Атомарності НЕ стереже —
        повернення рядка на `open('w')` лишає цей тест зеленим, і за неї
        відповідає AtomicWrites. Назва це каже прямо: до 28.08.2026 тут стояло
        `..._write_is_atomic_too`, тобто сторож обіцяв більше, ніж дає.

        Без нього рядок `atomic_write_json(self._local_file(task), ...)` лишався б
        єдиним переведеним писарем, якого не проходить жоден прогін: помилку в
        аргументах побачив би тільки дизайнер, і вже втративши нитку.
        """
        pins = [{'id': 'c1', 'text': 'Кирилиця й "лапки"', 'x': 10}]
        body = json.load(post(self.base + '/api/local-comments', {'comments': pins}))
        self.assertEqual(body['count'], 1)
        got = json.load(urllib.request.urlopen(self.base + '/api/local-comments'))
        self.assertEqual(got['comments'], pins)
        junk = [n for n in os.listdir(self.tmp) if n.startswith('.dc-local-comments')
                and n != '.dc-local-comments.json']
        self.assertEqual(junk, [], f'запис коментарів лишив по собі сміття: {junk}')

    # ---------- Пакет тюнера (Task 16) ----------
    # ⛔ Тюнер НЕ ПИШЕ ні у файл макета, ні в шар коментарів: його вихід —
    # пакет РЕКОМЕНДАЦІЙ, який читає Клод і за яким робить правки в коді.
    # Звідси й межі цих трьох перевірок: канал доносить пакет туди й назад,
    # НЕ чіпає сусідній продукт, і не бере на диск те, за чим правити код
    # неможливо.

    TUNE_PKG = {
        'kind': 'design-canvas.tuner.recommendations', 'version': 1,
        'page': None, 'note': 'картка затісна', 'editCount': 1,
        'instructions': ['Recommendations from the design-canvas tuner.'],
        'elements': [{'page': 'it1/holovna', 'selector': 'body > div.wrap > p.card',
                      'label': 'p.card', 'trail': ['body', 'div.wrap', 'p.card'],
                      'text': 'Картка', 'edits': [
                          {'prop': 'gap', 'from': '8px', 'to': '12px', 'rule': '.card',
                           'raw': 'var(--sp-2)', 'token': '--sp-2', 'tokenValue': '8px',
                           'verdict': 'token', 'hint': []}]}],
    }

    def test_d3_tuner_package_round_trip(self):
        """Пакет лягає у файл задачі й читається назад БЕЗ утрат.

        Порівнюємо пакет ЦІЛКОМ, а не окремі поля: читач приходить в іншій
        сесії, і кожне поле тут для нього несуче — `rule` каже, ДЕ правити,
        `verdict` і `hint` — чи було значення токеном, `instructions` — як усе
        це читати. Перевірка «доїхав note» лишила б решту без охорони, а
        мовчки згублене поле в цьому файлі дорожче за згублений файл: за
        неповним пакетом правку однаково зроблять, тільки не ту.
        """
        r = json.load(post(self.base + '/api/tuner', self.TUNE_PKG))
        self.assertTrue(r['ok'])
        self.assertEqual(r['elements'], 1)
        got = json.load(urllib.request.urlopen(self.base + '/api/tuner'))
        self.assertEqual(got['package'], self.TUNE_PKG)
        # Файл — там, де його шукатиме Клод, і з тим самим імʼям.
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, '.dc-tuner.json')))
        junk = [n for n in os.listdir(self.tmp)
                if n.startswith('.dc-tuner') and n != '.dc-tuner.json']
        self.assertEqual(junk, [], f'запис пакета лишив по собі сміття: {junk}')

    def test_d3_tuner_file_sits_beside_comments_not_inside(self):
        """⛔ Тюнер поруч із коментатором, а не всередині нього.

        `comment-layer` — окремий продукт зі своїм каналом і своїм форматом.
        Спільний файл означав би, що запис тюнера (а він іде на КОЖНУ правку)
        здатен зіпсувати коментарі колег, а «скинути накручене» — чіпати чуже.
        Перевіряємо в обидва боки: ні коментарі не пропали від запису тюнера,
        ні пакет не оселився в їхньому файлі.
        """
        pins = [{'id': 'c1', 'text': 'з коментатора', 'x': 10}]
        post(self.base + '/api/local-comments', {'comments': pins})
        post(self.base + '/api/tuner', self.TUNE_PKG)
        got = json.load(urllib.request.urlopen(self.base + '/api/local-comments'))
        self.assertEqual(got['comments'], pins,
                         'запис пакета тюнера зачепив файл коментатора')
        raw = open(os.path.join(self.tmp, '.dc-local-comments.json'),
                   encoding='utf-8').read()
        self.assertNotIn('tuner', raw,
                         'пакет тюнера заліз у файл коментатора — це окремий продукт')
        # І навпаки: коментарі не поїхали в пакет.
        pkg = json.load(urllib.request.urlopen(self.base + '/api/tuner'))['package']
        self.assertEqual(pkg, self.TUNE_PKG)

    def test_d3_tuner_rejects_a_malformed_package(self):
        """Форму звіряє СЕРВЕР, бо за цим файлом правлять код.

        Пакет із `elements`-рядком чи `note`-обʼєктом ліг би на диск мовчки й
        зіпсував би не інтерфейс, а роботу, яку за ним зроблять. Тому 400 — і
        файл на диску лишається СТАРИМ: відмова не сміє знести те, що вже було
        збережено правильно.
        """
        post(self.base + '/api/tuner', self.TUNE_PKG)      # валідний — лежить
        bad = [
            {'elements': 'не список', 'note': ''},
            {'elements': [{'selector': '.a', 'edits': 'не список'}], 'note': ''},
            {'elements': [], 'note': {'не': 'рядок'}},
            {'elements': ['не обʼєкт'], 'note': ''},
        ]
        for payload in bad:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(self.base + '/api/tuner', payload)
            self.assertEqual(ctx.exception.code, 400, f'прийнято сміття: {payload}')
        got = json.load(urllib.request.urlopen(self.base + '/api/tuner'))
        self.assertEqual(got['package'], self.TUNE_PKG,
                         'відмова перезаписала збережений пакет')

    def test_d3_tuner_clear_is_one_obvious_request(self):
        """Клод, застосувавши пакет, очищає його ОДНИМ очевидним запитом.

        fb-22092026-728266: `{"action":"clear"}` відбивався 400 «elements must
        be a list», а `{"package": null}` (fb-22092026-c11bff) — теж 400, і файл
        лишався цілим, хоча сесія була певна, що очистила. Обидві форми тепер
        прибирають файл, і GET чесно каже «пакета немає»."""
        for form in ({'action': 'clear'}, {'package': None}):
            post(self.base + '/api/tuner', self.TUNE_PKG)
            r = json.load(post(self.base + '/api/tuner', form))
            self.assertTrue(r.get('cleared'), f'{form} не очистив пакет: {r}')
            got = json.load(urllib.request.urlopen(self.base + '/api/tuner'))
            self.assertIsNone(got['package'], f'{form}: GET досі віддає пакет')
            self.assertIsNone(got['rev'])
            self.assertFalse(os.path.exists(os.path.join(self.tmp, '.dc-tuner.json')))
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(self.base + '/api/tuner', {'action': 'wipe'})
        self.assertEqual(ctx.exception.code, 400, 'невідома дія мовчки прийнята')

    def test_d3_tuner_tab_cannot_write_over_claudes_clear(self):
        """⛔ Вкладка не сміє покласти назад пакет, який Клод уже забрав.

        Механізм fb-22092026-c11bff: вкладка читає пакет раз на старті й пише
        повний пакет зі своєї памʼяті. Клод очистив — наступний поворот ручки
        відновлював старий `ready`. Вкладка тепер пише з `base_rev`; ревізія на
        диску інша → 409 і файл НЕ чіпаємо. Перевіряємо і відмову, і те, що
        згода з ревізією пише як завжди (і що `base_rev` у файл не потрапляє)."""
        r = json.load(post(self.base + '/api/tuner', self.TUNE_PKG))
        seen = r['rev']
        self.assertTrue(seen, 'запис не повернув ревізію')
        self.assertEqual(json.load(urllib.request.urlopen(self.base + '/api/tuner'))['rev'], seen)
        post(self.base + '/api/tuner', {'action': 'clear'})            # Клод
        with self.assertRaises(urllib.error.HTTPError) as ctx:          # вкладка
            post(self.base + '/api/tuner', dict(self.TUNE_PKG, base_rev=seen))
        self.assertEqual(ctx.exception.code, 409)
        body = json.load(ctx.exception)
        self.assertIsNone(body['package'], 'відмова не сказала вкладці, що пакета вже немає')
        self.assertFalse(os.path.exists(os.path.join(self.tmp, '.dc-tuner.json')),
                         'відмова все одно відновила очищений пакет')
        # Згода: пише, і `base_rev` лишається в запиті, а не в пакеті.
        r = json.load(post(self.base + '/api/tuner', dict(self.TUNE_PKG, base_rev=None)))
        self.assertTrue(r['ok'])
        got = json.load(urllib.request.urlopen(self.base + '/api/tuner'))
        self.assertEqual(got['package'], self.TUNE_PKG)
        self.assertEqual(got['rev'], r['rev'])

    def test_task_list_recent_first_and_old_tasks_keep_order(self):
        """Перемикач задач: останні відкриті зверху (fb-22092026-ca6975).

        Задачі без мітки (заведені до неї) — у хвіст у ПОРЯДКУ ФАЙЛА, а не
        перемішані: інакше перше ж оновлення переставило б увесь список тим,
        хто нічого ще не відкривав. Мітка ставиться саме перемиканням."""
        cfg = {'tasks': {'old1': {}, 'b': {'opened': '2026-01-20T10:00:00Z'},
                         'old2': {}, 'c': {'opened': '2026-01-27T09:00:00Z'},
                         'old3': {}}}
        self.assertEqual([k for k, _ in serve.tasks_by_recent(cfg)],
                         ['c', 'b', 'old1', 'old2', 'old3'])
        serve.mark_opened(cfg, 'old3')
        self.assertTrue(cfg['tasks']['old3']['opened'] > '2026-01-27T09:00:00Z')
        self.assertEqual([k for k, _ in serve.tasks_by_recent(cfg)][0], 'old3')
        serve.mark_opened(cfg, 'nope')                       # неіснуюча — без падіння
        self.assertNotIn('nope', cfg['tasks'])
        sys.path.insert(0, os.path.join(ROOT, 'bin'))
        import registry
        self.assertNotIn('opened', registry.SHARED,
                         '«що я відкривав» поїхало б у спільний реєстр')

    def test_task_list_ignores_a_hand_written_opened_that_is_not_a_string(self):
        """`opened` — ISO-рядок, але файл правлять і руками: число, список, `true`, `null`, обʼєкт.
        Порівняння `int` із `str` валило сортування (`TypeError`) і з ним увесь `/api/tasks`.
        Не-рядок — «без мітки»: у хвіст, у порядку файла, між собою не порівнюється."""
        cfg = {'tasks': {'n1': {'opened': 5}, 'b': {'opened': '2026-01-20T10:00:00Z'},
                         'n2': {'opened': None}, 'c': {'opened': '2026-01-27T09:00:00Z'},
                         'n3': {'opened': ['2026']}, 'n4': {'opened': True}, 'n5': {'opened': {}},
                         'n6': {'opened': 1.5}, 'n7': {}}}
        self.assertEqual([k for k, _ in serve.tasks_by_recent(cfg)],
                         ['c', 'b', 'n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n7'])

    def test_task_switch_stamps_opened(self):
        # Мітку спершу ЗНІМАЄМО: конфіг класу спільний, і перемикання в
        # попередніх тестах (`test_b1_*`) уже могло її поставити — тоді
        # перевірка зеленіла б і без штампа в `_task_switch`.
        cfg = serve.load_tasks()
        cfg['tasks']['fixture'].pop('opened', None)
        serve.save_tasks(cfg)
        post(self.base + '/api/task-switch', {'id': 'fixture'})
        self.assertIn('opened', serve.load_tasks()['tasks']['fixture'],
                      'перемикання не лишило мітки — сортувати нічим')

    def test_page_move_by_index_and_by_delta(self):
        """Порядок сторінок міняється запитом і лягає в `pages.json`
        (fb-09092026-d4c51b/24e49a: переставляли руками у файлі, бо ні
        функції, ні маршруту не існувало).

        Своя ітерація `it7`, а не спільна `it1`: фікстура класу спільна, і
        переставлені сторінки в `it1` поміняли б умови сусідніх тестів."""
        idir = os.path.join(self.tmp, 'iterations', 'it7')
        os.makedirs(idir, exist_ok=True)
        self.addCleanup(shutil.rmtree, idir, True)
        with open(os.path.join(idir, 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': i, 'name': i, 'published': True}
                                 for i in ('a', 'b', 'c')]}, fh)

        def order():
            with open(os.path.join(idir, 'pages.json'), encoding='utf-8') as fh:
                return [p['id'] for p in json.load(fh)['pages']]

        post(self.base + '/api/page-move', {'it': 'it7', 'page': 'c', 'index': 0})
        self.assertEqual(order(), ['c', 'a', 'b'])
        # delta рахує сервер ВІД ДИСКА, а не від того, що бачила вкладка.
        post(self.base + '/api/page-move', {'it': 'it7', 'page': 'a', 'delta': 1})
        self.assertEqual(order(), ['c', 'b', 'a'])
        post(self.base + '/api/page-move', {'it': 'it7', 'page': 'a', 'delta': -1})
        self.assertEqual(order(), ['c', 'a', 'b'])
        for bad in ({'it': 'it7', 'page': 'zzz', 'index': 0},
                    {'it': 'it7', 'page': 'a', 'delta': 2},
                    {'it': 'it7', 'page': 'a', 'index': 'top'}):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                post(self.base + '/api/page-move', bad)
            self.assertEqual(ctx.exception.code, 400, f'прийнято сміття: {bad}')
        self.assertEqual(order(), ['c', 'a', 'b'], 'відмова зачепила порядок')

    # ---------- Дерево сторінок: rev, нові маршрути, JSON-відмови (A3) ----------

    def _tree_it(self, name, pages):
        """Своя ітерація на тест: спільна it1 змінила б умови сусідів."""
        idir = os.path.join(self.tmp, 'iterations', name)
        os.makedirs(idir, exist_ok=True)
        self.addCleanup(shutil.rmtree, idir, True)
        with open(os.path.join(idir, 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': pages}, fh)
        for f in serve.pm.flatten(pages):
            if f['kind'] != 'folder':
                os.makedirs(os.path.join(idir, f['page']['id']), exist_ok=True)
        return idir

    def _get_pages(self, it):
        with urllib.request.urlopen(f'{self.base}/api/iteration-pages?it={it}') as r:
            return json.load(r)

    def _post_json(self, path, payload):
        """(status, body) — і для 2xx, і для 4xx."""
        try:
            with post(self.base + path, payload) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode())

    @staticmethod
    def _lock_held_elsewhere(idir):
        """True, якщо хтось ІНШИЙ (інший open → інший file description) тримає
        `.pages.lock` цієї ітерації просто зараз. Так тест бачить, ПІД локом
        відбулась дія сервера чи поза ним, не покладаючись на таймінг."""
        import fcntl
        fd = os.open(os.path.join(idir, '.pages.lock'), os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except BlockingIOError:
            return True
        finally:
            os.close(fd)

    TREE = [{'id': 'p', 'name': 'Картка', 'kind': 'page', 'children': [
        {'id': 's1', 'name': 'Порожньо', 'kind': 'state'}]},
        {'id': 'q', 'name': 'Особа', 'kind': 'page'}]

    def test_page_restore_brings_folders_back_and_checks_rev(self):
        """fb-01102026-71980b: «Відновити» в панелі — через той самий лок і rev."""
        prev = [{'id': 'w', 'name': 'Віджет', 'kind': 'folder', 'isGroup': True,
                 'children': [{'id': 'p', 'name': 'Картка', 'kind': 'page'}]},
                {'id': 'q', 'name': 'Особа', 'kind': 'page'}]
        flat = [{'id': 'p', 'name': 'p', 'kind': 'page'}, {'id': 'q', 'name': 'q', 'kind': 'page'}]
        idir = self._tree_it('it30', flat)
        st, body = self._post_json('/api/page-restore', {'it': 'it30', 'prev': prev, 'rev': 'stale-rev'})
        self.assertEqual(st, 409, body)
        rev = self._get_pages('it30')['rev']
        st, body = self._post_json('/api/page-restore', {'it': 'it30', 'prev': prev, 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['restored'], ['w'])
        self.assertRegex(body['rev'], r'^[0-9a-f]{16}$')
        on_disk = serve.pm.read_pages(idir)
        self.assertEqual([n['id'] for n in on_disk], ['w', 'q'])
        st, body = self._post_json('/api/page-restore', {'it': 'it30', 'prev': 'x', 'rev': body['rev']})
        self.assertEqual((st, body['code']), (400, 'bad-prev'))

    def test_it_stamp_moves_on_page_files_only(self):
        """fb-01102026-309e3b: рамка оновлюється, коли змінився ВМІСТ ітерації.
        Дерево (pages.json) перечитує панель, flow.json пише сам канвас на драг
        вузла, shots/ — автозʼємка, dot-файли — службове: жодне не «макет змінився»."""
        idir = self._tree_it('it31', [{'id': 'p', 'name': 'p', 'kind': 'page'}])
        page = os.path.join(idir, 'p', 'index.html')
        with open(page, 'w', encoding='utf-8') as fh:
            fh.write('<h1>1</h1>')
        os.utime(page, (1_000_000, 1_000_000))
        os.utime(os.path.join(idir, 'pages.json'), (1_000_000, 1_000_000))

        def stamp():
            with urllib.request.urlopen(f'{self.base}/api/it-stamp?it=it31') as r:
                return json.load(r)['stamp']
        base = stamp()
        self.assertEqual(base, 1_000_000)
        # `pages.json.bak` — `write_pages` знімає його `copy2` (з mtime попередньої
        # версії) на КОЖНІЙ дії над деревом: без виключення власне перейменування
        # перезавантажувало б рамку (ревʼю батча 1.47, D1). `.tmp` — недописаний запис.
        for name in ('pages.json', 'flow.json', 'shots/p.webp', '.dc-x.json',
                     'pages.json.bak', 'flow.json.bak', 'p.json.tmp'):
            f = os.path.join(idir, name)
            os.makedirs(os.path.dirname(f), exist_ok=True)
            with open(f, 'w') as fh:
                fh.write('{}')
            os.utime(f, (2_000_000, 2_000_000))
            self.assertEqual(stamp(), base, f'{name} зсунув відбиток вмісту')
        os.utime(page, (3_000_000, 3_000_000))
        self.assertEqual(stamp(), 3_000_000)

    def test_it_stamp_missing_iteration_is_zero_and_bad_name_is_400(self):
        with urllib.request.urlopen(f'{self.base}/api/it-stamp?it=ghost9') as r:
            self.assertEqual(json.load(r), {'it': 'ghost9', 'stamp': 0, 'recent': []})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f'{self.base}/api/it-stamp?it=../x')
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()

    def test_claude_status_roundtrip_and_validation(self):
        """Ідея 02.09.2026 / fb-01102026-309e3b п.3: статус Клода на канвасі.
        Мод pipeline-band шле серцебиття; канвас показує лише СВОЮ задачу."""
        tid = serve.load_tasks()['current']
        st, body = self._post_json('/api/claude-status', {
            'task': tid, 'phase': 'design', 'status': 'in_progress', 'note': 'Іт.2', 'session': 's1'})
        self.assertEqual(st, 200, body)
        with urllib.request.urlopen(f'{self.base}/api/claude-status') as r:
            got = json.load(r)
        self.assertEqual((got['state'], got['phase'], got['note']), ('working', 'design', 'Іт.2'))
        self.assertLess(got['age_s'], 5)
        st, _ = self._post_json('/api/claude-status', {'task': 'інша-задача', 'phase': 'dev',
                                                       'status': 'in_progress', 'session': 's2'})
        self.assertEqual(st, 200)
        with urllib.request.urlopen(f'{self.base}/api/claude-status') as r:
            self.assertEqual(json.load(r)['note'], 'Іт.2', 'чужа задача перебила статус')
        for bad in ({'task': tid, 'phase': 'design', 'status': 'працюю'},
                    {'task': tid, 'phase': 'нема', 'status': 'waiting'},
                    {'task': 5, 'phase': 'design', 'status': 'waiting'},
                    {'task': tid, 'phase': 'design', 'status': 'waiting', 'note': 'x' * 500}):
            st, body = self._post_json('/api/claude-status', bad)
            self.assertEqual(st, 400, bad)

    def test_claude_status_refuses_foreign_origin(self):
        """Ревʼю 1.51: будь-яка сторінка в браузері могла простим POST `text/plain`
        намалювати «Claude працює». Браузер ставить Origin на кросс-доменний POST;
        мод Claude Code і CLI його не шлють. Чужий Origin — 403."""
        tid = serve.load_tasks()['current']
        body = json.dumps({'task': tid, 'phase': 'dev', 'status': 'in_progress', 'note': 'forged'}).encode()
        req = urllib.request.Request(f'{self.base}/api/claude-status', data=body, method='POST',
                                     headers={'Content-Type': 'text/plain', 'Origin': 'https://evil.example'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)
        ctx.exception.close()
        with urllib.request.urlopen(f'{self.base}/api/claude-status') as r:
            self.assertNotEqual(json.load(r).get('note'), 'forged')
        own = urllib.request.Request(f'{self.base}/api/claude-status', data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'Origin': self.base})
        with urllib.request.urlopen(own) as r:
            self.assertEqual(r.status, 200, 'власна сторінка канваса не сміє отримати 403')

    def test_claude_status_matches_task_jira(self):
        """Знахідка 12.10.2026: удар із Jira-ключем поточної задачі (фікстура: `TEST-1`)
        світиться на канвасі. Стереже САМ виклик у `GET`: чиста функція з псевдонімами
        не допоможе, якщо `do_GET` їх не передасть."""
        st, body = self._post_json('/api/claude-status', {
            'task': 'TEST-1', 'phase': 'design', 'status': 'in_progress', 'note': 'by-jira', 'session': 'sj'})
        self.assertEqual(st, 200, body)
        with urllib.request.urlopen(f'{self.base}/api/claude-status') as r:
            got = json.load(r)
        self.assertEqual((got['state'], got.get('note')), ('working', 'by-jira'))

    def test_it_stamp_lists_recently_changed_pages(self):
        """«Де саме міняє»: сторінка, чиї файли змінились за останні 2 хв."""
        idir = self._tree_it('it32', [{'id': 'p', 'name': 'p', 'kind': 'page'},
                                      {'id': 'q', 'name': 'q', 'kind': 'page'}])
        for pid, age in (('p', 10), ('q', 3600)):
            f = os.path.join(idir, pid, 'index.html')
            with open(f, 'w') as fh:
                fh.write('x')
            t = time.time() - age
            os.utime(f, (t, t))
        with urllib.request.urlopen(f'{self.base}/api/it-stamp?it=it32') as r:
            self.assertEqual(json.load(r)['recent'], ['p'])

    def test_iteration_pages_carries_rev(self):
        self._tree_it('it21', self.TREE)
        got = self._get_pages('it21')
        self.assertRegex(got['rev'], r'^[0-9a-f]{16}$')

    def test_folder_add_group_ungroup_kind_roundtrip(self):
        idir = self._tree_it('it22', self.TREE)
        rev = self._get_pages('it22')['rev']
        st, body = self._post_json('/api/folder-add', {'it': 'it22', 'parent': 'p', 'name': 'Віджет', 'rev': rev})
        self.assertEqual(st, 200, body)
        fid = body['node']['id']
        st, body = self._post_json('/api/page-move', {'it': 'it22', 'ids': ['s1'], 'parent': fid, 'index': 0, 'rev': body['rev']})
        self.assertEqual(st, 200, body)
        st, body = self._post_json('/api/page-kind', {'it': 'it22', 'id': 'q', 'kind': 'state', 'rev': body['rev']})
        self.assertEqual((st, body['code']), (400, 'state-outside-page'))
        st, body = self._post_json('/api/page-ungroup', {'it': 'it22', 'id': fid, 'rev': self._get_pages('it22')['rev']})
        self.assertEqual(st, 200, body)
        st, body = self._post_json('/api/page-group', {'it': 'it22', 'ids': ['s1'], 'name': 'W', 'rev': body['rev']})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['node']['kind'], 'folder')
        on_disk = serve.pm.read_pages(idir)
        self.assertEqual(on_disk[0]['children'][0]['children'][0]['id'], 's1')

    def test_stale_rev_is_409_and_nothing_written(self):
        idir = self._tree_it('it23', self.TREE)
        before = open(os.path.join(idir, 'pages.json'), encoding='utf-8').read()
        st, body = self._post_json('/api/folder-add', {'it': 'it23', 'name': 'F', 'rev': 'deadbeefdeadbeef'})
        self.assertEqual((st, body['code']), (409, 'stale'))
        self.assertEqual(open(os.path.join(idir, 'pages.json'), encoding='utf-8').read(), before)

    def test_rule_violation_is_json_400_with_code(self):
        self._tree_it('it24', self.TREE)
        rev = self._get_pages('it24')['rev']
        st, body = self._post_json('/api/page-move', {'it': 'it24', 'ids': ['s1'], 'parent': None, 'index': 0, 'rev': rev})
        self.assertEqual((st, body['ok'], body['code']), (400, False, 'state-outside-page'))

    def test_delete_unwrap_keeps_children_and_removes_only_own_dir(self):
        idir = self._tree_it('it25', [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page'}]}])
        rev = self._get_pages('it25')['rev']
        st, body = self._post_json('/api/page-delete', {'it': 'it25', 'page': 'p', 'mode': 'unwrap', 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual([p['id'] for p in serve.pm.read_pages(idir)], ['c'])
        self.assertFalse(os.path.isdir(os.path.join(idir, 'p')))
        self.assertTrue(os.path.isdir(os.path.join(idir, 'c')))

    def test_legacy_move_by_delta_still_works_on_deep_tree(self):
        idir = self._tree_it('it26', [{'id': 'f', 'name': 'F', 'kind': 'folder', 'children': [
            {'id': 'a', 'name': 'A', 'kind': 'page'}, {'id': 'b', 'name': 'B', 'kind': 'page'}]}])
        post(self.base + '/api/page-move', {'it': 'it26', 'page': 'b', 'delta': -1})
        self.assertEqual([c['id'] for c in serve.pm.read_pages(idir)[0]['children']], ['b', 'a'])

    def test_lock_file_is_ignored_by_task_git(self):
        self.assertIn('.pages.lock', serve.TASK_IGNORE)

    def test_ungroup_of_a_page_is_refused(self):
        """Розгрупувати можна лише ТЕКУ. «Розгрупувати» сторінку `p` прибрало б
        її з дерева, не стерши файли, — тиха осиротіла тека. Видаляти сторінку
        — це `page-delete` з явним mode."""
        idir = self._tree_it('it22b', self.TREE)
        before = open(os.path.join(idir, 'pages.json'), encoding='utf-8').read()
        rev = self._get_pages('it22b')['rev']
        st, body = self._post_json('/api/page-ungroup', {'it': 'it22b', 'id': 'p', 'rev': rev})
        self.assertEqual((st, body['code']), (400, 'bad-kind'))
        self.assertEqual(open(os.path.join(idir, 'pages.json'), encoding='utf-8').read(), before)
        self.assertTrue(os.path.isdir(os.path.join(idir, 'p')))

    def test_ungroup_refuses_a_page_even_if_legacy_isgroup_contradicts(self):
        """Вручну зіпсований файл: `kind: page` + `isGroup: true`. Тип для `op_unwrap`
        — явний `kind` (як у `kind_of`), тож і перевірка «це тека» мусить
        дивитись на ТОЙ САМИЙ тип, а не на сирий прапорець: інакше сторінку з
        файлами забрали б із дерева, і теку ніхто б не стер."""
        idir = self._tree_it('it22c', [{'id': 'p', 'name': 'P', 'kind': 'page', 'isGroup': True}])
        rev = self._get_pages('it22c')['rev']
        st, body = self._post_json('/api/page-ungroup', {'it': 'it22c', 'id': 'p', 'rev': rev})
        self.assertEqual((st, body['code']), (400, 'bad-kind'))
        self.assertEqual([p['id'] for p in serve.pm.read_pages(idir)], ['p'])

    def test_iteration_pages_of_a_missing_iteration_is_empty_and_creates_nothing(self):
        """Неіснуюча ітерація — порожній список, як було, і БЕЗ теки-привида:
        лок на ній нічого не створює, а охорона стоїть перед локом."""
        idir = os.path.join(self.tmp, 'iterations', 'ghost1')
        self.assertEqual(self._get_pages('ghost1'), {'it': 'ghost1', 'pages': [], 'rev': ''})
        self.assertFalse(os.path.exists(idir), 'GET створив теку неіснуючої ітерації')

    def test_tree_posts_to_a_missing_iteration_are_404_not_found_and_create_nothing(self):
        idir = os.path.join(self.tmp, 'iterations', 'ghost2')
        for path, payload in (
                ('/api/folder-add', {'name': 'F'}),
                ('/api/page-group', {'ids': ['p'], 'name': 'F'}),
                ('/api/page-ungroup', {'id': 'p'}),
                ('/api/page-kind', {'id': 'p', 'kind': 'state'}),
                ('/api/page-restore', {'prev': []}),
                ('/api/page-move', {'ids': ['p'], 'parent': None, 'index': 0}),
                ('/api/page-delete', {'page': 'p', 'mode': 'all'})):
            # rev '' — законне значення («файла нема»): перевірка форми rev його пропускає
            st, body = self._post_json(path, dict(payload, it='ghost2', rev=''))
            self.assertEqual((st, body.get('code')), (404, 'not-found'), path)
        self.assertFalse(os.path.exists(idir), 'POST створив теку неіснуючої ітерації')

    def test_busy_lock_is_503_for_writers_but_get_still_reads(self):
        """Чужий писар тримає лок довше за LOCK_TIMEOUT → 503 `busy` (клієнт може
        повторити), а не висячий запит і не 400 «ти щось зламав». Читач (GET) лока
        не бере взагалі й відповідає одразу: записи атомарні, тож одне читання —
        узгоджений знімок."""
        idir = self._tree_it('it27', self.TREE)
        with mock.patch.object(serve.pm, 'LOCK_TIMEOUT', 0.2):
            with serve.pm.pages_lock(idir):
                got = self._get_pages('it27')
                self.assertEqual([p['id'] for p in got['pages']], ['p', 'q'])
                st, body = self._post_json('/api/folder-add', {'it': 'it27', 'name': 'F', 'rev': got['rev']})
                self.assertEqual((st, body['code']), (503, 'busy'))
                st, body = self._post_json('/api/page-rename', {'it': 'it27', 'page': 'p', 'name': 'X'})
                self.assertEqual((st, body['code']), (503, 'busy'))
        self.assertEqual([p['id'] for p in serve.pm.read_pages(idir)], ['p', 'q'])

    def test_response_rev_is_read_under_the_lock(self):
        """rev у відповіді — той, що знято ПІД локом разом із записом. Окреме
        `pages_rev` після виходу з локу дало б клієнту відбиток стану, якого він
        не бачив (сусідній запис устигає між ними): наступна його дія або
        пройшла б поверх чужої правки, або марно впала б у 409."""
        idir = self._tree_it('it28', self.TREE)
        rev = self._get_pages('it28')['rev']
        seen = []
        real = serve.pm.pages_rev

        def spy(d):
            seen.append(self._lock_held_elsewhere(idir))
            return real(d)
        with mock.patch.object(serve.pm, 'pages_rev', spy):
            st, body = self._post_json('/api/folder-add', {'it': 'it28', 'name': 'F', 'rev': rev})
            self.assertEqual(st, 200, body)
        self.assertTrue(seen, 'rev нізвідки не знімали')
        self.assertTrue(all(seen), f'pages_rev викликано ПОЗА локом: {seen}')
        self.assertEqual(body['rev'], real(idir))

    def test_delete_removes_dirs_under_the_lock(self):
        """Теки стираємо ПІД тим самим локом (`after` у mutate), а не після
        нього: паралельний `page-new` з тим самим slug інакше встиг би створити
        теку, яку наше видалення потім стерло б разом зі щойно доданою."""
        idir = self._tree_it('it29', self.TREE)
        rev = self._get_pages('it29')['rev']
        seen = []
        real = serve.pm.remove_dirs

        def spy(d, rels):
            seen.append(self._lock_held_elsewhere(idir))
            return real(d, rels)
        with mock.patch.object(serve.pm, 'remove_dirs', spy):
            st, body = self._post_json('/api/page-delete', {'it': 'it29', 'page': 'p', 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual(seen, [True], 'теки стерто поза локом (або не стерто взагалі)')
        self.assertFalse(os.path.isdir(os.path.join(idir, 'p')))
        self.assertNotIn('failed', body)

    def test_delete_reports_dirs_it_could_not_remove(self):
        """Дерево вже записано, а тека не стерлась (права, файл замість теки) —
        це не відмова: відповідь 200 називає теки, що лишились, у `failed`."""
        self._tree_it('it30', self.TREE)
        rev = self._get_pages('it30')['rev']
        with mock.patch.object(serve.pm, 'remove_dirs', return_value=['p']):
            st, body = self._post_json('/api/page-delete', {'it': 'it30', 'page': 'p', 'rev': rev})
        self.assertEqual((st, body['ok'], body['failed']), (200, True, ['p']))

    def test_delete_with_stale_rev_touches_neither_tree_nor_dirs(self):
        idir = self._tree_it('it31', self.TREE)
        before = open(os.path.join(idir, 'pages.json'), encoding='utf-8').read()
        st, body = self._post_json('/api/page-delete', {'it': 'it31', 'page': 'p', 'rev': 'deadbeefdeadbeef'})
        self.assertEqual((st, body['code']), (409, 'stale'))
        self.assertEqual(open(os.path.join(idir, 'pages.json'), encoding='utf-8').read(), before)
        self.assertTrue(os.path.isdir(os.path.join(idir, 'p')))

    def test_delete_of_an_unknown_page_and_bad_mode_are_json_with_code(self):
        self._tree_it('it32', self.TREE)
        rev = self._get_pages('it32')['rev']
        st, body = self._post_json('/api/page-delete', {'it': 'it32', 'page': 'nope'})
        self.assertEqual((st, body['ok'], body['code']), (404, False, 'not-found'))
        st, body = self._post_json('/api/page-delete', {'it': 'it32', 'page': 'p', 'mode': 'shred', 'rev': rev})
        self.assertEqual((st, body['code']), (400, 'bad-mode'))

    def test_get_pages_and_rev_come_from_one_read(self):
        """`pages` і `rev` у GET — з ОДНОГО прочитання файла (`pm.read_pages_rev`).
        Два окремі читання лишали б вікно, де писар устиг між ними: панель мала б
        дерево одного стану з rev іншого, і наступна її дія пройшла б поверх чужої
        правки."""
        self._tree_it('it27b', self.TREE)
        real, calls = serve.pm._read_raw, []

        def counting(d):
            calls.append(d)
            return real(d)
        with mock.patch.object(serve.pm, '_read_raw', counting):
            got = self._get_pages('it27b')
        self.assertEqual(len(calls), 1, 'GET читає pages.json більше за один раз')
        self.assertEqual([p['id'] for p in got['pages']], ['p', 'q'])
        self.assertRegex(got['rev'], r'^[0-9a-f]{16}$')

    def test_get_takes_no_lock_creates_no_lock_file_and_leaves_the_mtime_alone(self):
        """⛔ Перегляд — не робота. `pages_lock` створює `.pages.lock`, а це піднімає
        mtime теки ітерації; автосинк вибирає робочу ітерацію за mtime, тож простий
        перегляд тижневої ітерації робив її «свіжою». Плюс: лок на теці «лише для
        читання» падав би PermissionError."""
        idir = self._tree_it('it27c', self.TREE)
        old = time.time() - 7 * 24 * 3600
        for root, _, names in os.walk(idir):
            for n in names:
                os.utime(os.path.join(root, n), (old, old))
        os.utime(idir, (old, old))
        before = serve._dir_mtime(idir)
        self._get_pages('it27c')
        self.assertFalse(os.path.exists(os.path.join(idir, '.pages.lock')), 'GET створив лок-файл')
        self.assertEqual(os.stat(idir).st_mtime, old, 'GET поворушив теку ітерації')
        self.assertEqual(serve._dir_mtime(idir), before)
        # те саме для теки «лише для читання»: GET мусить відповісти, а не впасти
        os.chmod(idir, 0o555)
        try:
            self.assertEqual([p['id'] for p in self._get_pages('it27c')['pages']], ['p', 'q'])
        finally:
            os.chmod(idir, 0o755)

    def test_get_bad_iteration_is_json_400(self):
        for q in ('', '?it=', '?it=../x', '?it=a/b', '?it=it1%0A'):
            try:
                urllib.request.urlopen(f'{self.base}/api/iteration-pages{q}')
                self.fail(f'прийнято {q!r}')
            except urllib.error.HTTPError as e:
                self.assertEqual((e.code, json.loads(e.read().decode())['code']),
                                 (400, 'bad-iteration'), q)

    def test_dir_mtime_ignores_dot_files(self):
        """Службова dot-файли (`.pages.lock` від справжнього запису, `.DS_Store`)
        не є роботою: `autosync` вибирає ітерацію за `_dir_mtime`, і свіжий
        лок-файл на старій ітерації переставив би вибір. Так само рахує
        `_authored_mtime`."""
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, 'index.html')
            sub = os.path.join(tmp, 'p')
            os.makedirs(sub)
            nested = os.path.join(sub, 'index.html')
            old = time.time() - 7 * 24 * 3600
            for f in (real, nested):
                open(f, 'w').close()
                os.utime(f, (old, old))
            for f in (os.path.join(tmp, '.pages.lock'), os.path.join(sub, '.DS_Store')):
                open(f, 'w').close()            # свіжі: mtime = зараз
            self.assertEqual(serve._dir_mtime(tmp), old)

    def test_tree_routes_reject_a_bad_ids_list_as_json(self):
        """Форма `ids` — вхід, а не правило дерева, але відмова теж JSON із
        `code`: клієнт розбирає тіло однаково. Не-рядок у списку інакше впав би
        TypeError (500) у `set(ids)`."""
        self._tree_it('it33', self.TREE)
        for path, extra in (('/api/page-move', {'index': 0}), ('/api/page-group', {'name': 'F'})):
            for ids in ([], 'p', None, [1], [['p']]):
                st, body = self._post_json(path, dict(extra, it='it33', ids=ids))
                self.assertEqual((st, body.get('code')), (400, 'bad-ids'), f'{path} прийняв ids={ids!r}')

    def test_legacy_page_handlers_write_under_the_pages_lock(self):
        """Старі обробники (`page-new/rename/publish-toggle/reparent/move`) тепер
        теж читають-міняють-пишуть під `pages_lock`: інакше вони гнали б
        паралельну правку нових маршрутів (які за rev+локом) — втрачене оновлення."""
        idir = self._tree_it('it34', [
            {'id': 'a', 'name': 'A', 'kind': 'page'}, {'id': 'b', 'name': 'B', 'kind': 'page'}])
        seen = []
        real = serve.pm.write_pages

        def spy(d, pages):
            seen.append(self._lock_held_elsewhere(idir))
            return real(d, pages)
        calls = (
            ('/api/page-new', {'it': 'it34', 'name': 'Нова', 'parent': 'a'}),
            ('/api/page-rename', {'it': 'it34', 'page': 'a', 'name': 'AA'}),
            ('/api/page-publish-toggle', {'it': 'it34', 'page': 'a'}),
            ('/api/page-reparent', {'it': 'it34', 'page': 'b', 'parent': 'a'}),
            ('/api/page-move', {'it': 'it34', 'page': 'b', 'index': 0}),
            ('/api/page-move', {'it': 'it34', 'page': 'b', 'delta': 1}),
        )
        with mock.patch.object(serve.pm, 'write_pages', spy):
            for path, payload in calls:
                before = len(seen)
                st, body = self._post_json(path, payload)
                self.assertEqual(st, 200, (path, body))
                self.assertEqual(len(seen), before + 1, f'{path}: запису не було (тест нічого не доводить)')
                self.assertTrue(seen[-1], f'{path}: запис pages.json поза pages_lock')

    def test_page_new_can_make_a_state_and_reports_rule_violations_as_json(self):
        self._tree_it('it35', self.TREE)
        st, body = self._post_json('/api/page-new', {'it': 'it35', 'name': 'Стан', 'parent': 'p', 'kind': 'state'})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['page']['kind'], 'state')
        # стан поза сторінкою — правило дерева: JSON із кодом, не обрив з'єднання
        st, body = self._post_json('/api/page-new', {'it': 'it35', 'name': 'Сирота', 'kind': 'state'})
        self.assertEqual((st, body['code']), (400, 'state-outside-page'))
        st, body = self._post_json('/api/page-new', {'it': 'it35', 'name': '   '})
        self.assertEqual(st, 400)

    def test_page_reparent_rule_violation_is_json_with_code(self):
        self._tree_it('it36', self.TREE)
        st, body = self._post_json('/api/page-reparent', {'it': 'it36', 'page': 's1', 'parent': None})
        self.assertEqual((st, body['ok'], body['code']), (400, False, 'state-outside-page'))

    ALL_PAGE_ROUTES = (
        ('/api/page-new', {'name': 'N'}),
        ('/api/page-rename', {'page': 'p', 'name': 'X'}),
        ('/api/page-delete', {'page': 'p'}),
        ('/api/page-delete', {'page': 'p', 'mode': 'all', 'rev': ''}),
        ('/api/page-reparent', {'page': 'p'}),
        ('/api/page-move', {'page': 'p', 'index': 0}),
        ('/api/page-move', {'page': 'p', 'delta': 1}),
        ('/api/page-move', {'ids': ['p'], 'index': 0, 'rev': ''}),
        ('/api/page-publish-toggle', {'page': 'p'}),
        ('/api/folder-add', {'name': 'F', 'rev': ''}),
        ('/api/page-group', {'ids': ['p'], 'name': 'F', 'rev': ''}),
        ('/api/page-ungroup', {'id': 'p', 'rev': ''}),
        ('/api/page-kind', {'id': 'p', 'kind': 'state', 'rev': ''}),
        ('/api/page-restore', {'prev': [], 'rev': ''}))

    def test_iteration_must_be_a_string_name_in_every_page_handler(self):
        """Один перехід на всі обробники сторінок: `it` — рядок за правилом імені,
        інакше JSON 400 `bad-iteration`. Не-рядок (`5`, `null`, список) раніше
        кидав TypeError у `NAME_RE.match` — зʼєднання рвалось без відповіді;
        `it1\\n` проходив `^…$`."""
        for it in (5, None, ['it1'], {'a': 1}, True, '', '../x', 'a/b', 'it1\n'):
            for path, payload in self.ALL_PAGE_ROUTES:
                st, body = self._post_json(path, dict(payload, it=it))
                self.assertEqual((st, body.get('code')), (400, 'bad-iteration'),
                                 f'{path} it={it!r}')
        # ключа `it` немає зовсім — те саме
        for path, payload in self.ALL_PAGE_ROUTES:
            st, body = self._post_json(path, payload)
            self.assertEqual((st, body.get('code')), (400, 'bad-iteration'), path)

    def test_legacy_routes_without_a_page_are_json_bad_page(self):
        """Старі маршрути знають вузол за `page`: порожній чи відсутній — 400
        `bad-page`, а не 404 `not-found` із пошуку вузла з id `''` (це різні
        помилки: перша — у запиті, друга — у дереві). Вступ один — `_legacy_args`."""
        idir = self._tree_it('it37', self.TREE)
        before = open(os.path.join(idir, 'pages.json'), encoding='utf-8').read()
        routes = (('/api/page-rename', {'name': 'X'}),
                  ('/api/page-delete', {}),
                  ('/api/page-publish-toggle', {}),
                  ('/api/page-reparent', {'parent': 'p'}),
                  ('/api/page-move', {'index': 0}))
        for path, payload in routes:
            for extra in ({}, {'page': ''}):
                with self.subTest(path=path, extra=extra):
                    st, body = self._post_json(path, dict(payload, it='it37', **extra))
                    self.assertEqual((st, body.get('ok'), body.get('code')), (400, False, 'bad-page'))
        self.assertEqual(open(os.path.join(idir, 'pages.json'), encoding='utf-8').read(), before)

    def test_a_body_that_is_not_a_json_object_is_json_bad_body_on_every_route(self):
        """`[]`, `"x"`, `5`, `null` — валідний JSON, але не обʼєкт: `payload.get`
        у будь-якому обробнику падав AttributeError, і зʼєднання рвалось без
        відповіді. Одна перевірка у `do_POST` закриває ВСІ маршрути; маршрути й
        їхні обробники беремо з коду `do_POST`, щоб новий маршрут не лишився без неї.

        ⛔ Обробники підмінено: без перевірки частина з них (autosync, gitlab-pull,
        shoot-stop) не читає тіла й відпрацювала б по-справжньому — на червоному
        прогоні вони б поміняли стан фікстури й поклали сусідні тести."""
        import inspect
        src = inspect.getsource(serve.Handler.do_POST)
        routes = re.findall(r"self\.path == '(/api/[a-z-]+)'", src)
        names = sorted(set(re.findall(r"self\.(_\w+)\(payload\)", src)))
        self.assertGreater(len(routes), 20, 'не розібрали маршрути з do_POST')
        self.assertGreaterEqual(len(names), len(routes) - 2, 'не розібрали обробники з do_POST')
        ran = []

        def fake(name):
            def handler(handler_self, payload):
                ran.append(name)
                handler_self._send_json({'ok': True, 'fake': name})
            return handler
        with contextlib.ExitStack() as stack:
            for n in names:
                stack.enter_context(mock.patch.object(serve.Handler, n, fake(n)))
            for path in routes:
                for body in ([], 'x', 5, None, [{'it': 'it1'}]):
                    with self.subTest(path=path, body=body):
                        st, got = self._post_json(path, body)
                        self.assertEqual((st, got.get('ok'), got.get('code')), (400, False, 'bad-body'))
            self.assertEqual(ran, [], 'обробник отримав тіло, що не обʼєкт')
            # і правильний обʼєкт проходить до обробника (перевірка не ріже все підряд)
            st, got = self._post_json('/api/page-new', {})
            self.assertEqual((st, got.get('fake')), (200, '_page_new'))

    def test_deeply_nested_json_body_is_json_bad_body(self):
        """Тіло з глибокою вкладеністю кидає RecursionError у `json.loads` — це не
        ValueError, і зʼєднання рвалось без відповіді."""
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', self.port)
        body = b'[' * 200000 + b']' * 200000
        conn.request('POST', '/api/page-new', body, {'Content-Type': 'application/json'})
        r = conn.getresponse()
        got = json.loads(r.read().decode())
        conn.close()
        self.assertEqual((r.status, got.get('code')), (400, 'bad-body'))

    def test_a_name_that_is_not_a_string_is_json_empty_name(self):
        """`name: 5` падав AttributeError на `.strip()` у моделі (обірване зʼєднання)."""
        idir = self._tree_it('it49', self.TREE)
        before = open(os.path.join(idir, 'pages.json'), encoding='utf-8').read()
        for path, payload in (('/api/page-new', {}), ('/api/page-rename', {'page': 'p'})):
            for name in (5, ['x'], {'a': 1}):
                with self.subTest(path=path, name=name):
                    st, body = self._post_json(path, dict(payload, it='it49', name=name))
                    self.assertEqual((st, body.get('code')), (400, 'empty-name'))
        self.assertEqual(open(os.path.join(idir, 'pages.json'), encoding='utf-8').read(), before)

    def test_page_move_ids_form_lands_at_the_requested_index_under_the_requested_parent(self):
        """Проводка аргументів: `index` і `parent` доходять до `op_move`, а не
        лишаються десь по дорозі (мутант «index ігнорується» виживав)."""
        idir = self._tree_it('it38', [
            {'id': 'a', 'name': 'A', 'kind': 'page'}, {'id': 'b', 'name': 'B', 'kind': 'page'},
            {'id': 'c', 'name': 'C', 'kind': 'page'},
            {'id': 'f', 'name': 'F', 'kind': 'folder'}])

        def ids(nodes):
            return [n['id'] for n in nodes]
        rev = self._get_pages('it38')['rev']
        st, body = self._post_json('/api/page-move', {'it': 'it38', 'ids': ['a'], 'parent': None, 'index': 1, 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual(ids(serve.pm.read_pages(idir)), ['b', 'a', 'c', 'f'])
        st, body = self._post_json('/api/page-move', {'it': 'it38', 'ids': ['c'], 'parent': 'f', 'index': 0, 'rev': body['rev']})
        self.assertEqual(st, 200, body)
        st, body = self._post_json('/api/page-move', {'it': 'it38', 'ids': ['b'], 'parent': 'f', 'index': 1, 'rev': body['rev']})
        self.assertEqual(st, 200, body)
        tree = serve.pm.read_pages(idir)
        self.assertEqual(ids(tree), ['a', 'f'])
        self.assertEqual(ids(tree[1]['children']), ['c', 'b'])

    def test_folder_add_honours_name_parent_and_index(self):
        idir = self._tree_it('it39', self.TREE)
        rev = self._get_pages('it39')['rev']
        st, body = self._post_json('/api/folder-add', {'it': 'it39', 'parent': 'p', 'index': 0, 'name': 'Перша', 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['node']['name'], 'Перша')
        tree = serve.pm.read_pages(idir)
        self.assertEqual([c['id'] for c in tree[0]['children']], [body['node']['id'], 's1'])
        st, body = self._post_json('/api/folder-add', {'it': 'it39', 'index': 1, 'name': 'Друга', 'rev': body['rev']})
        self.assertEqual(st, 200, body)
        self.assertEqual([p['id'] for p in serve.pm.read_pages(idir)], ['p', body['node']['id'], 'q'])

    def test_page_group_names_the_folder_and_wraps_the_ids(self):
        idir = self._tree_it('it40', [{'id': i, 'name': i.upper(), 'kind': 'page'} for i in ('a', 'b', 'c')])
        rev = self._get_pages('it40')['rev']
        st, body = self._post_json('/api/page-group', {'it': 'it40', 'ids': ['a', 'b'], 'name': 'Група', 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual(body['node']['name'], 'Група')
        tree = serve.pm.read_pages(idir)
        self.assertEqual([(n['id'], n['kind']) for n in tree], [(body['node']['id'], 'folder'), ('c', 'page')])
        self.assertEqual((tree[0]['name'], [c['id'] for c in tree[0]['children']]), ('Група', ['a', 'b']))

    def test_page_kind_sets_the_requested_kind_on_the_requested_node(self):
        idir = self._tree_it('it41', [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'page'}]}])
        rev = self._get_pages('it41')['rev']
        st, body = self._post_json('/api/page-kind', {'it': 'it41', 'id': 'c', 'kind': 'state', 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual(serve.pm.read_pages(idir)[0]['children'][0]['kind'], 'state')

    def test_legacy_reparent_puts_the_page_under_the_parent(self):
        idir = self._tree_it('it42', [{'id': 'a', 'name': 'A', 'kind': 'page'}, {'id': 'b', 'name': 'B', 'kind': 'page'}])
        st, body = self._post_json('/api/page-reparent', {'it': 'it42', 'page': 'b', 'parent': 'a'})
        self.assertEqual(st, 200, body)
        tree = serve.pm.read_pages(idir)
        self.assertEqual(([n['id'] for n in tree], [c['id'] for c in tree[0]['children']]), (['a'], ['b']))

    def test_delete_all_removes_the_subtree_and_every_dir_of_it(self):
        idir = self._tree_it('it43', [{'id': 'p', 'name': 'P', 'kind': 'page', 'children': [
            {'id': 'c', 'name': 'C', 'kind': 'state'}]}, {'id': 'q', 'name': 'Q', 'kind': 'page'}])
        rev = self._get_pages('it43')['rev']
        st, body = self._post_json('/api/page-delete', {'it': 'it43', 'page': 'p', 'mode': 'all', 'rev': rev})
        self.assertEqual(st, 200, body)
        self.assertEqual([p['id'] for p in serve.pm.read_pages(idir)], ['q'])
        self.assertEqual(sorted(d for d in os.listdir(idir) if os.path.isdir(os.path.join(idir, d))), ['q'])

    def _git(self, *args):
        return subprocess.run(['git', *args], cwd=self.tmp, capture_output=True, text=True).stdout.strip()

    def test_tree_op_commits_with_its_message_and_a_noop_makes_no_commit(self):
        """Дія над деревом лишає коміт у теці задачі (`git log -1 --format=%s`), а
        «нічого не змінилось» — ні. Порожній рух інакше підмітав би в коміт
        усе стороннє, що лежить у теці (стрей-файл нижче), під чужим повідомленням."""
        ident = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
                 'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}
        with mock.patch.dict(os.environ, ident):
            idir = self._tree_it('it44', [{'id': i, 'name': i.upper(), 'kind': 'page'} for i in ('a', 'b')])
            rev = self._get_pages('it44')['rev']
            st, body = self._post_json('/api/folder-add', {'it': 'it44', 'name': 'F', 'rev': rev})
            self.assertEqual(st, 200, body)
            self.assertEqual(self._git('log', '-1', '--format=%s'), 'folder: add')
            st, body = self._post_json('/api/page-move', {'it': 'it44', 'ids': ['b'], 'parent': None, 'index': 0, 'rev': body['rev']})
            self.assertEqual(st, 200, body)
            self.assertEqual(self._git('log', '-1', '--format=%s'), 'page b: move')
            # порожній рух: `b` уже перша. Стрей-файл дав би коміт, якби автокоміт ішов.
            with open(os.path.join(idir, 'stray.txt'), 'w') as fh:
                fh.write('x')
            head = self._git('rev-parse', 'HEAD')
            st, body2 = self._post_json('/api/page-move', {'it': 'it44', 'ids': ['b'], 'parent': None, 'index': 0, 'rev': body['rev']})
            self.assertEqual((st, body2['rev']), (200, body['rev']), 'порожній рух змінив rev')
            self.assertEqual(self._git('rev-parse', 'HEAD'), head, 'порожній рух зробив коміт')

    def test_new_tree_routes_require_a_string_rev(self):
        """Нові маршрути без `rev` (або з не-рядком) — 400 `missing-rev`: інакше
        клієнт, що забув rev, мовчки втрачав би захист від чужої правки. Порожній
        рядок — законний rev («файла нема»), тож він форму проходить."""
        idir = self._tree_it('it45', self.TREE)
        before = open(os.path.join(idir, 'pages.json'), encoding='utf-8').read()
        routes = (('/api/folder-add', {'name': 'F'}),
                  ('/api/page-group', {'ids': ['q'], 'name': 'F'}),
                  ('/api/page-ungroup', {'id': 'p'}),
                  ('/api/page-kind', {'id': 's1', 'kind': 'page'}),
                  ('/api/page-move', {'ids': ['q'], 'parent': None, 'index': 0}),
                  ('/api/page-delete', {'page': 'q', 'mode': 'all'}))
        for path, payload in routes:
            for extra in ({}, {'rev': None}, {'rev': 5}, {'rev': ['x']}):
                st, body = self._post_json(path, dict(payload, it='it45', **extra))
                self.assertEqual((st, body.get('code')), (400, 'missing-rev'), f'{path} {extra}')
        self.assertEqual(open(os.path.join(idir, 'pages.json'), encoding='utf-8').read(), before)
        st, body = self._post_json('/api/folder-add', {'it': 'it45', 'name': 'F', 'rev': ''})
        self.assertEqual((st, body['code']), (409, 'stale'), "'' — форму rev пройшов")
        # стара форма видалення (без mode) rev не вимагає: так кличе нинішня панель
        st, body = self._post_json('/api/page-delete', {'it': 'it45', 'page': 'q'})
        self.assertEqual(st, 200, body)

    def test_corrupt_pages_json_is_json_500_in_every_page_handler(self):
        """Побитий pages.json — JSON 500 `corrupt` у КОЖНОМУ обробнику сторінок (а не
        обірване зʼєднання з голим JSONDecodeError), і файл не зачеплено."""
        idir = self._tree_it('it46', self.TREE)
        path = os.path.join(idir, 'pages.json')
        with open(path, 'wb') as fh:
            fh.write(b'{oops')
        try:
            urllib.request.urlopen(f'{self.base}/api/iteration-pages?it=it46')
            self.fail('GET прийняв побитий файл')
        except urllib.error.HTTPError as e:
            self.assertEqual((e.code, json.loads(e.read().decode())['code']), (500, 'corrupt'))
        for route, payload in self.ALL_PAGE_ROUTES:
            st, body = self._post_json(route, dict(payload, it='it46'))
            self.assertEqual((st, body.get('code'), body.get('ok')), (500, 'corrupt', False), f'{route} {payload}')
        with open(path, 'rb') as fh:
            self.assertEqual(fh.read(), b'{oops')
        self.assertFalse(os.path.exists(path + '.bak'))

    def test_rename_and_toggle_of_an_unknown_page_are_json_404(self):
        self._tree_it('it47', self.TREE)
        for route, payload in (('/api/page-rename', {'page': 'nope', 'name': 'X'}),
                               ('/api/page-publish-toggle', {'page': 'nope'})):
            st, body = self._post_json(route, dict(payload, it='it47'))
            self.assertEqual((st, body.get('ok'), body.get('code')), (404, False, 'not-found'), route)

    def test_page_move_legacy_form_with_a_parent_is_bad_form(self):
        """`parent` без `ids` — клієнт хотів перенести під батька, але прислав
        стару форму, яка рухає лише серед сусідів: мовчки проігнорувати `parent`
        означало б виконати не те, про що просили."""
        idir = self._tree_it('it48', self.TREE)
        before = open(os.path.join(idir, 'pages.json'), encoding='utf-8').read()
        for extra in ({'parent': 'p'}, {'parent': None}):
            st, body = self._post_json('/api/page-move', dict(extra, it='it48', page='q', index=0))
            self.assertEqual((st, body.get('code')), (400, 'bad-form'), extra)
        self.assertEqual(open(os.path.join(idir, 'pages.json'), encoding='utf-8').read(), before)

    def test_d2_flow_save_keeps_the_file_mode(self):
        """`_flow_save` був ПРООБРАЗОМ хелпера і сам лишався поза його лікуванням.

        flow.json — не внутрішній файл: він не проходить `_is_tool_junk`, тобто
        їде колегам через `copy_mockup`, а `copy2` режим зберігає. Тобто 0600
        поїхав би разом із ним.
        """
        flow = {'nodes': [{'id': 'main', 'pos': {'col': 0, 'row': 0}}]}
        self.assertTrue(json.load(post(self.base + '/api/flow-save',
                                       {'it': 'it1', 'flow': flow}))['ok'])
        fp = os.path.join(self.tmp, 'iterations', 'it1', 'flow.json')
        os.chmod(fp, 0o644)
        flow['nodes'][0]['pos']['col'] = 1
        self.assertTrue(json.load(post(self.base + '/api/flow-save',
                                       {'it': 'it1', 'flow': flow}))['ok'])
        self.assertEqual(stat.S_IMODE(os.stat(fp).st_mode), 0o644,
                         'збереження флоу звузило права файла, який їде колегам')
        junk = [n for n in os.listdir(os.path.dirname(fp))
                if n.startswith('flow.json') and n != 'flow.json']
        self.assertEqual(junk, [], f'лишилось сміття: {junk}')

    def test_e1_publish_warns_when_disk_code_is_newer_than_process(self):
        """Обгортку превʼю збирає САМ процес, тому правка в app/*.py доїжджає лише
        після перезапуску канваса + повторної публікації. 25.08.2026 другий крок
        пропустили — на Vercel лишалась стара обгортка. build_only: у мережу не
        ходимо, а обгортка вже зібрана — саме той момент, коли треба попередити."""
        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        if not any(i.get('published') for i in task['iterations']):
            post(self.base + '/api/publish-toggle', {'id': task['iterations'][0]['id']})
        # Код не чіпали → тиша. Без цього асерту мутація «прибрати порівняння
        # часу» пройшла б: попередження світилось би ЗАВЖДИ і нічого не значило.
        body = json.load(post(self.base + '/api/publish', {'build_only': True}))
        self.assertNotIn('code_stale', body)
        src = os.path.abspath(serve.__file__)
        orig = os.stat(src)
        try:
            os.utime(src, (orig.st_atime, time.time() + 3600))
            body = json.load(post(self.base + '/api/publish', {'build_only': True}))
            self.assertIn('serve.py', body.get('code_stale', ''))
            self.assertIn('перезапуск', body['code_stale'])
            # ⛔ Попередження, а не блокування: дизайнер має право свідомо
            # публікувати зі старого коду, тому збірка мусить пройти.
            self.assertTrue(body['ok'])
            self.assertTrue(os.path.exists(os.path.join(body['dir'], 'index.html')))
        finally:
            os.utime(src, (orig.st_atime, orig.st_mtime))

    def _pw(self, value, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.base + '/api/preview-password',
                                     data=json.dumps({'password': value}).encode(),
                                     headers=headers, method='POST')
        try:
            r = urllib.request.urlopen(req)
            return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_e2_preview_password_from_ui_reaches_every_page(self):
        """Пароль превʼю з інтерфейсу (ідея 02.09.2026). Охоронець ПАСТКИ ротації:
        гейт стоїть і в обгортці, і в кожній внутрішній сторінці, а reseal
        перепечатує лише обгортку. Тест лише на обгортку був би театром."""
        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        it = task['iterations'][0]['id']
        if not task['iterations'][0].get('published'):
            post(self.base + '/api/publish-toggle', {'id': it})
            self.addCleanup(lambda: post(self.base + '/api/publish-toggle', {'id': it}))
        self.addCleanup(lambda: self._pw(''))

        st, body = self._pw('old-1')
        self.assertEqual((st, body['preview_password'], body['preview_password_custom']),
                         (200, 'old-1', True))
        pub = json.load(post(self.base + '/api/publish', {'build_only': True}))['dir']
        gate = json.load(urllib.request.urlopen(self.base + '/api/task'))['preview_gate']
        self.assertEqual(gate['state'], 'current')
        self.assertGreaterEqual(gate['pages'], 2, 'обгортка + хоч одна внутрішня сторінка')

        # Змінили пароль — зібране превʼю ще зі старим, і API це КАЖЕ.
        st, body = self._pw('new-2')
        self.assertEqual(body['preview_gate'], {'state': 'stale', 'stale': gate['pages'],
                                                'ungated': 0, 'inner_stale': gate['pages'] - 1,
                                                'pages': gate['pages']})
        # Пастка reseal: перепечатали ЛИШЕ обгортку — внутрішні сторінки старі.
        with open(os.path.join(pub, 'index.html'), 'w', encoding='utf-8') as fh:
            fh.write(serve.preview_index_html(serve.gate_html('fixture', 'new-2'), 'new-2'))
        gate = json.load(urllib.request.urlopen(self.base + '/api/task'))['preview_gate']
        self.assertEqual((gate['state'], gate['stale'], gate['inner_stale']),
                         ('stale', gate['pages'] - 1, gate['pages'] - 1),
                         'обгортка з новим паролем не робить превʼю «оновленим»')
        # Сторінка БЕЗ гейта — інша причина (TD-37), не «старий пароль».
        inner = [f for f in serve._publish_pages(pub) if f != os.path.join(pub, 'index.html')]
        json.load(post(self.base + '/api/publish', {'build_only': True}))
        with open(inner[0], 'w', encoding='utf-8') as fh:
            fh.write('<html><body>без гейта</body></html>')
        os.utime(os.path.join(pub, 'index.html'))   # скинути кеш, як це робить публікація
        gate = json.load(urllib.request.urlopen(self.base + '/api/task'))['preview_gate']
        self.assertEqual((gate['state'], gate['stale'], gate['ungated']), ('ungated', 0, 1))
        # Повна публікація — новий пароль на КОЖНІЙ сторінці, старого ніде.
        json.load(post(self.base + '/api/publish', {'build_only': True}))
        gate = json.load(urllib.request.urlopen(self.base + '/api/task'))['preview_gate']
        self.assertEqual((gate['state'], gate['stale']), ('current', 0))
        old = f'P={serve.js_literal("old-1")};'
        for f in serve._publish_pages(pub):
            with open(f, encoding='utf-8') as fh:
                self.assertNotIn(old, fh.read(), f)

        # Порожній — назад до спільного типового.
        st, body = self._pw('  ')
        self.assertEqual((body['preview_password'], body['preview_password_custom']),
                         (serve.DEFAULT_PREVIEW_PW, False))

    def test_e3_preview_password_rejects_foreign_origin_and_junk(self):
        self._pw('keep-7')
        self.addCleanup(lambda: self._pw(''))
        st, body = self._pw('evil', origin='https://evil.example')
        self.assertEqual(st, 403)
        for bad in ('a\nb', 'x' * (serve.PREVIEW_PW_MAX + 1), 42, None):
            st, body = self._pw(bad)
            self.assertEqual(st, 400, repr(bad))
        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        self.assertEqual(task['preview_password'], 'keep-7', 'жоден відмовлений запит не писав')
        st, _ = self._pw('ok-8', origin='http://localhost:8765')
        self.assertEqual(st, 200)

    def test_e5_reseal_refuses_when_inner_pages_keep_old_password(self):
        """`ops/reseal_gate.py` перепечатує лише обгортку. Після зміни пароля
        з канваса він мусить ВІДМОВИТИ в деплої, а не видати півправду."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'reseal_gate', os.path.join(ROOT, 'ops', 'reseal_gate.py'))
        rg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rg)
        task = json.load(urllib.request.urlopen(self.base + '/api/task'))
        it = task['iterations'][0]['id']
        if not task['iterations'][0].get('published'):
            post(self.base + '/api/publish-toggle', {'id': it})
            self.addCleanup(lambda: post(self.base + '/api/publish-toggle', {'id': it}))
        self.addCleanup(lambda: self._pw(''))
        self._pw('r-1')
        json.load(post(self.base + '/api/publish', {'build_only': True}))
        deployed = []
        rg.deploy = lambda pub, task=None: deployed.append(pub) or (True, '')

        def run(*args):
            out = io.StringIO()
            with mock.patch.object(sys, 'argv', ['reseal_gate.py', *args]), \
                    contextlib.redirect_stdout(out):
                rg.main()
            return out.getvalue()
        self.assertIn('передеплоєно', run('fixture'), 'пароль той самий — reseal законний')
        self._pw('r-2')
        wrapper = os.path.join(self.tmp, 'publish', 'index.html')
        before = open(wrapper, encoding='utf-8').read()
        out = run('fixture')
        self.assertIn('старим паролем', out)
        self.assertEqual(len(deployed), 1, 'другого деплою бути не мало')
        self.assertEqual(open(wrapper, encoding='utf-8').read(), before,
                         'відмова мусить лишити локальну обгортку такою, як задеплоєна')

    def test_e6_teams_mute_never_touches_prod_from_isolated_config(self):
        """Фікстура (DC_TASKS_FILE) не сміє замовчати живий канал команди: і GET,
        і POST відмовляють ДО мережі, а GET каже «не знаю», а не «увімкнено»."""
        with mock.patch.object(urllib.request, 'urlopen',
                               side_effect=AssertionError('мережа з фікстури')):
            with self.assertRaises(OSError):
                serve.teams_rpc('teams_mute_set', {'p_project': 'x', 'p_muted': True})
        body = json.load(urllib.request.urlopen(self.base + '/api/teams-mute'))
        self.assertEqual(body['channel'], 'dc/fixture')
        self.assertIn('error', body)
        self.assertNotIn('muted', body)

    def test_e7_teams_mute_post_uses_task_channel_and_identity(self):
        calls, db = [], {}

        def fake(name, body):
            calls.append((name, body))
            if name == 'teams_mute_set':
                if body['p_muted']:
                    db[body['p_project']] = body['p_by']
                else:
                    db.pop(body['p_project'], None)
                return body['p_muted']
            return [{'project_id': k, 'muted_by': v, 'muted_at': 't'} for k, v in db.items()]
        with mock.patch.object(serve, 'teams_rpc', fake):
            st, body = self._post_json('/api/teams-mute', {'muted': True})
            sig = serve.mute_signature()
            self.assertRegex(sig, r'^k:[0-9a-f]{12}$')
            self.assertEqual((st, body['muted'], body['muted_by'], body['mine'], body['channel']),
                             (200, True, sig, True, 'dc/fixture'))
            self.assertEqual(calls[0], ('teams_mute_set', {'p_project': 'dc/fixture',
                                                           'p_muted': True, 'p_by': sig}))
            # ⛔ Ні ПІБ, ні пошти в базі: RPC стану читає будь-хто з ключем сторінки.
            self.assertNotIn('Lead', json.dumps(calls))
            self.assertNotIn('ligazakon', json.dumps(calls))
            body = json.load(urllib.request.urlopen(self.base + '/api/teams-mute'))
            self.assertTrue(body['muted'])
            st, body = self._post_json('/api/teams-mute', {'muted': False})
            self.assertEqual((st, body['muted']), (200, False))
            n = len(calls)
            st, _ = self._post_json('/api/teams-mute', {'muted': 'yes'})
            self.assertEqual(st, 400)
            st, _ = self._post_json('/api/teams-mute', {'muted': True}, origin='https://evil.example')
            self.assertEqual(st, 403)
            self.assertEqual(len(calls), n, 'відмовлені запити не дійшли до бази')

    def _post_json(self, path, payload, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.base + path, data=json.dumps(payload).encode(),
                                     headers=headers, method='POST')
        try:
            r = urllib.request.urlopen(req)
            return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_e8_mute_of_a_channel_covers_its_subchannels_only(self):
        rows = [{'project_id': 'dc/blog', 'muted_by': 'S', 'muted_at': 't'}]
        self.assertTrue(serve.teams_mute_view('dc/blog', rows)['muted'])
        self.assertTrue(serve.teams_mute_view('dc/blog/internal', rows)['muted'])
        self.assertFalse(serve.teams_mute_view('dc/blog-x', rows)['muted'])
        self.assertFalse(serve.teams_mute_view('dc/blo', rows)['muted'])

    def test_e4_gate_state_without_publish_is_none(self):
        self.assertEqual(serve.preview_gate_state({'dir': tempfile.gettempdir() + '/nope-dc'}, '1'),
                         {'state': 'none', 'stale': 0, 'ungated': 0, 'inner_stale': 0, 'pages': 0})


def _md5(path):
    import hashlib
    try:
        with open(path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return None


class LiveConfigUntouched(unittest.TestCase):
    """Живий конфіг задач не має змінюватись від прогону тестів.

    Раніше ServeTest підміняв живий tasks.json фікстурою і відновлював із бекапа;
    будь-яке падіння між setUp і tearDown лишало робочий конфіг дизайнера
    тестовими даними, а _overview_sync встигав запушити фікстуру в прод-дашборд.

    ⚠️ Стежимо і за `tasks.json.bak`, не лише за `tasks.json`. Заміряно 03.08.2026
    на прогоні ДО фікса: md5 самого tasks.json не змінювався (tearDownClass
    відновлював його байт-у-байт), а от `.bak` — змінювався щоразу, бо
    save_tasks() робить `copy2(tasks.json, tasks.json.bak)` уже ПОВЕРХ фікстури.
    Тобто бекап робочого конфіга дизайнера затирався тестовими даними назовсім.
    Перевірка лише по tasks.json була б зеленою і до фікса — тобто нічого не
    доводила б.
    """

    def test_live_tasks_config_unchanged_by_suite(self):
        live = os.path.join(ROOT, 'tasks.json')
        if not os.path.isfile(live):
            self.skipTest('живого tasks.json немає — нічого перевіряти')
        watched = (live, live + '.bak')
        before = {p: _md5(p) for p in watched}
        # прогін усього класу, який раніше підміняв конфіг
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ServeTest)
        with open(os.devnull, 'w') as devnull:
            result = unittest.TextTestRunner(stream=devnull, verbosity=0).run(suite)
        after = {p: _md5(p) for p in watched}
        # без цього перевірка була б вакуумно зеленою, якби вкладений прогін
        # взагалі не піднявся (помилка імпорту/setUpClass → 0 тестів)
        self.assertGreater(result.testsRun, 0, 'вкладений прогін ServeTest не відбувся')
        self.assertEqual(before, after, 'прогін тестів змінив живий конфіг задач')


class TestsCannotWriteLiveConfig(unittest.TestCase):
    """Жоден тестовий файл не сміє писати в ЖИВИЙ `tasks.json`.

    ⛔ Це сталось насправді: 15.09.2026 новий тест покликав `serve.task_new()`
    без `DC_TASKS_FILE`, `task_new` → `save_tasks()` → `tasks_path()` → робочий
    конфіг дизайнера. Посеред його робочого дня 21 задача зникла, лишилась одна,
    що вказує в /var/folders, а `.bak` затерся тестовими даними.

    Наявний `LiveConfigUntouched` цього НЕ спіймав, і не міг: він міряє md5
    навколо прогону ОДНОГО класу (`ServeTest`), а `unittest discover` бере файли
    за абеткою — `test_gitlab_sync` іде раніше за `test_serve`, тобто шкода вже
    сталась, коли охоронець знімав свою базову лінію.

    Тому перевірка СТАТИЧНА: якщо файл тестів кличе те, що пише конфіг, він
    мусить у тому ж файлі задавати `DC_TASKS_FILE`. Мутація, якою доводиться:
    прибери рядок `os.environ['DC_TASKS_FILE']` із `tests/test_gitlab_sync.py`
    — цей тест червоніє, не чіпаючи нічийого конфіга.

    Те саме для РЕЄСТРУ просторів `<DEAI_HOME>/spaces.json` (нижче, `SPACE_WRITERS`): файл, що
    пише простори, мусить присвоювати `DEAI_HOME` і підключати `tests/spaces_guard.py` у
    `setUpModule`/`tearDownModule`. Присвоєння й хуки шукає `ast`, а не текст: закоментований
    рядок чи згадка в докстрінгу ізоляцією не вважаються.
    """

    #: Усе, що всередині доходить до `save_tasks()`.
    WRITERS = ('task_new(', 'save_tasks(', 'task_switch(')

    #: Не підрядок `DC_TASKS_FILE`, а САМЕ звернення до нього як до ключа
    #: оточення. Перша редакція шукала підрядок — і мутація
    #: `DC_TASKS_FILE` → `DC_TASKS_FILE_OFF` її не валила, бо старе імʼя
    #: лишається всередині нового. Охоронець, який не може впасти, гірший за
    #: відсутній, тому перевірка звужена до реального виклику.
    ISOLATED = re.compile(r'''DC_TASKS_FILE['"]\s*\]''')

    def test_every_config_writing_test_file_isolates_the_path(self):
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        offenders = []
        for name in sorted(os.listdir(tests_dir)):
            if not (name.startswith('test_') and name.endswith('.py')):
                continue
            with open(os.path.join(tests_dir, name), encoding='utf-8') as fh:
                src = fh.read()
            # Своє власне тіло не рахуємо: імена писарів тут лише як дані.
            if name == os.path.basename(__file__):
                continue
            if any(w in src for w in self.WRITERS) and not self.ISOLATED.search(src):
                offenders.append(name)
        self.assertEqual(offenders, [], 'тести пишуть у ЖИВИЙ tasks.json: '
                                        + ', '.join(offenders))

    def test_guard_sees_the_writers_it_claims_to_see(self):
        """Свідок проти вакууму: перевірка вище зелена й тоді, коли жоден файл
        писарів не кличе взагалі — тобто коли вона не перевіряє нічого."""
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        seen = 0
        for name in sorted(os.listdir(tests_dir)):
            if not (name.startswith('test_') and name.endswith('.py')):
                continue
            if name == os.path.basename(__file__):
                continue
            with open(os.path.join(tests_dir, name), encoding='utf-8') as fh:
                if any(w in fh.read() for w in self.WRITERS):
                    seen += 1
        self.assertGreater(seen, 0, 'жоден тест не кличе писарів конфіга — '
                                    'охоронець вище нічого не стереже')


    # ---- простори (`<DEAI_HOME>/spaces.json`): те саме, але для справжнього РЕЄСТРУ машини ----

    #: Усе, що пише простори: HTTP-маршрути й три мутатори `app/spaces.py`. ОКРЕМИЙ кортеж, не
    #: розширення `WRITERS`: `tests/test_gitlab_sync.py` кличе `task_new(` і ізолює лише
    #: `DC_TASKS_FILE` — він не пише простори, і спільне правило зробило б його хибно червоним.
    #: `/api/task-new` і `/api/task-switch` тут, а не лише в `WRITERS`: з увімкненим шаром обидва
    #: ЗАВЕРШУЮТЬСЯ `spaces.switch_space(...)` — тобто пишуть `current` справжнього реєстру, коли
    #: файл тестів не ізолював `DEAI_HOME` (з вимкненим шаром `switch_space` — no-op, тож
    #: `test_serve.py`, що ганяє їх лише з `DC_TASKS_FILE`, під правило не потрапляє: його тут не скануємо).
    #: Модулі (етап 2а, Task 6) пишуть теж — свідомо в цьому ж кортежі: `write_module_state(` змінює
    #: `<тека простору>/space.json`, `write_secrets(` СТВОРЮЄ `<DEAI_HOME>/secrets.json`, а `/api/module-` (enable,
    #: disable, settings, check) кличе обидва з сервера. Тест, що їх кличе без власного `DEAI_HOME`, створив би
    #: `secrets.json` у справжньому `~/.deai` дизайнера (пароль превʼю!), а `spaces_guard` бачить зміну імен файлів
    #: у теці реєстру. `/api/modules` (читання списку) сюди не входить: `/api/module-` його не збігає.
    SPACE_WRITERS = ('/api/space-', '/api/task-new', '/api/task-switch',
                     'create_space(', 'switch_space(', 'update_space(',
                     'write_secrets(', 'write_module_state(', '/api/module-')

    #: Форми ПРИСВОЄННЯ `DEAI_HOME`, які приймає `_assigns_deai_home`. Лежать окремо, щоб повідомлення
    #: про провал казало автору, що саме охоронець уважає ізоляцією, а не змушувало гадати.
    SPACE_ISOLATION_FORMS = (
        "os.environ['DEAI_HOME'] = …",
        "os.environ.update({…, 'DEAI_HOME': …})  або  os.environ.update(DEAI_HOME=…)",
        "mock.patch.dict(os.environ, {…, 'DEAI_HOME': …})  або  patch.dict(os.environ, DEAI_HOME=…)",
        "subprocess.run/Popen/call/check_call/check_output(…, env={…, 'DEAI_HOME': …})",
    )

    #: Виклики породження процесу, чий `env={…}` приймається як ізоляція.
    _SPAWNERS = ('run', 'Popen', 'call', 'check_call', 'check_output')

    @staticmethod
    def _assigns_deai_home(src):
        """Чи ПРИСВОЮЄ код `DEAI_HOME` (форми — `SPACE_ISOLATION_FORMS`). Розбір через `ast`: коментар,
        докстрінг, читання `os.environ['DEAI_HOME']`, `env(DEAI_HOME=…)` і таблиця випадків
        `({'DEAI_HOME': '/x'}, True)` присвоєнням не є, а текстовий регексп їх приймав (закоментований
        рядок давав зелене для файла без ізоляції).

        ⚠️ Це ПРИСУТНІСТЬ присвоєння у файлі, не доказ, що воно діє на кожен тест (так само, як
        `ISOLATED` вище), а `subprocess(env=…)` ізолює лише дитину. Доказ — динамічний
        `tests/spaces_guard.py`: знімок справжнього `~/.deai` на вході в модуль і звірка на виході."""

        def is_environ(n):
            return ((isinstance(n, ast.Attribute) and n.attr == 'environ'
                     and isinstance(n.value, ast.Name) and n.value.id == 'os')
                    or (isinstance(n, ast.Name) and n.id == 'environ'))

        def has_key(n):
            return isinstance(n, ast.Dict) and any(
                isinstance(k, ast.Constant) and k.value == 'DEAI_HOME' for k in n.keys)

        def passes_it(args, keywords):
            """Позиційний літерал-словник із ключем, `DEAI_HOME=…` або `**{…літерал…}`."""
            return (any(has_key(a) for a in args)
                    or any(k.arg == 'DEAI_HOME' or (k.arg is None and has_key(k.value)) for k in keywords))

        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Assign):
                if any(isinstance(t, ast.Subscript) and is_environ(t.value)
                       and isinstance(t.slice, ast.Constant) and t.slice.value == 'DEAI_HOME'
                       for t in n.targets):
                    return True
            elif isinstance(n, ast.Call):
                f = n.func
                name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
                if name == 'update' and isinstance(f, ast.Attribute) and is_environ(f.value):
                    if passes_it(n.args, n.keywords):
                        return True
                elif name == 'dict' and isinstance(f, ast.Attribute) and n.args and (
                        is_environ(n.args[0])
                        or (isinstance(n.args[0], ast.Constant) and n.args[0].value == 'os.environ')):
                    if passes_it(n.args[1:], n.keywords):
                        return True
                elif name in TestsCannotWriteLiveConfig._SPAWNERS:
                    if any(k.arg == 'env' and has_key(k.value) for k in n.keywords):
                        return True
        return False

    def _space_writer_sources(self):
        """[(імʼя файла, джерело)] тестових файлів, що кличуть писарів просторів (без цього файла:
        тут імена писарів — лише дані)."""
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        out = []
        for name in sorted(os.listdir(tests_dir)):
            if not (name.startswith('test_') and name.endswith('.py')):
                continue
            if name == os.path.basename(__file__):
                continue
            with open(os.path.join(tests_dir, name), encoding='utf-8') as fh:
                src = fh.read()
            if self._is_space_writer(src):
                out.append((name, src))
        return out

    @classmethod
    def _is_space_writer(cls, src):
        """Чи кличе джерело писаря просторів (`SPACE_WRITERS`)."""
        return any(w in src for w in cls.SPACE_WRITERS)

    def test_every_space_writing_test_file_isolates_deai_home(self):
        offenders = [name for name, src in self._space_writer_sources()
                     if not self._assigns_deai_home(src)]
        self.assertEqual(offenders, [], 'тести пишуть простори без власного DEAI_HOME — це справжній '
                                        '~/.deai: ' + ', '.join(offenders) + '. Охоронець приймає присвоєння '
                                        '(коментар і докстрінг не рахуються): '
                                        + '; '.join(self.SPACE_ISOLATION_FORMS))

    def test_space_guard_sees_the_writers_it_claims_to_see(self):
        """Свідок проти вакууму: обидві перевірки просторів зелені й тоді, коли жоден файл не кличе
        писарів, — тобто коли вони не стережуть нічого (перейменували мутатор — і охоронець осліп)."""
        seen = {name for name, _ in self._space_writer_sources()}
        self.assertLessEqual({'test_spaces.py', 'test_spaces_serve.py', 'test_integrations_off.py',
                              'test_modules.py', 'test_modules_api.py'},
                             seen, 'писарі просторів зникли з тестів — SPACE_WRITERS застарів')

    def test_the_task_routes_that_end_in_a_space_switch_count_as_space_writers(self):
        """`task-new`/`task-switch` з увімкненим шаром роблять простір задачі поточним — це запис
        реєстру. Файл, що їх викликає без власного `DEAI_HOME`, мусить бути спійманий; читальні
        маршрути (`/api/task`, `/api/tasks`, `/api/tasks-overview`) — ні."""
        for src in ("self.post('/api/task-new', {'id': 'x'})",
                    'post("/api/task-switch", {"id": "a"})',
                    "urlopen(base + '/api/task-new')",
                    "self.post('/api/space-new', {})",
                    "spaces.switch_space('p')",
                    "self.post('/api/module-enable', {'id': 'css-tokens'})",
                    "post('/api/module-check', {})",
                    "dm.write_module_state(space, 'css-tokens', enabled=True)",
                    "deai_modules.write_secrets('s', 'static-publish', {})"):
            self.assertTrue(self._is_space_writer(src), src)
        for src in ("self.get('/api/task')", "self.get('/api/tasks?all=1')",
                    "self.get('/api/tasks-overview')", "# /api/tasks", "x = 1",
                    "self.get('/api/modules?space=a')", "self.get('/api/ds-tokens')", "dm.read_secrets('s', 'm')"):
            self.assertFalse(self._is_space_writer(src), src)

    def test_the_isolation_check_tells_an_assignment_from_a_mention(self):
        """Охоронець, який не може впасти, гірший за відсутній: перевірка має ловити саме присвоєння в
        оточення і не вестись на згадку імені (коментар, докстрінг, читання, таблиця випадків, `env(…)`)."""
        assigns = {
            'присвоєння': "os.environ['DEAI_HOME'] = tmp",
            'присвоєння без пробілів': 'os.environ["DEAI_HOME"]=tmp',
            'update зі словником': "os.environ.update({'A': f'{x}/h', 'DEAI_HOME': d})",
            'update з kwarg': 'os.environ.update(DEAI_HOME=d)',
            'update з **словник': "os.environ.update(**{'DEAI_HOME': d})",
            'patch.dict зі словником': "mock.patch.dict(os.environ, {'DEAI_HOME': d})",
            'patch.dict з kwarg': 'patch.dict(os.environ, DEAI_HOME=d)',
            'patch.dict зі словником (імʼя рядком)': "mock.patch.dict('os.environ', {'DEAI_HOME': d})",
            'subprocess.run(env=)': "subprocess.run(cmd, env={'DEAI_HOME': d, 'HOME': h})",
            'Popen(env=)': "Popen(cmd, env={'DEAI_HOME': d})",
            'у гілці': "if layer:\n    os.environ['DEAI_HOME'] = tmp",
        }
        mentions = {
            'коментар': "# os.environ['DEAI_HOME'] = tmp\npass",
            'докстрінг': '"""\nos.environ[\'DEAI_HOME\'] = tmp\n"""',
            'читання': "x = os.environ['DEAI_HOME']",
            'порівняння': "os.environ['DEAI_HOME'] == d",
            'pop': "os.environ.pop('DEAI_HOME', None)",
            'del': "del os.environ['DEAI_HOME']",
            'таблиця випадків': "cases = [({'DEAI_HOME': '/x'}, True)]",
            'хелпер env()': 'env(DEAI_HOME=deai)',
            '_ENV-кортеж': "_ENV = ('HOME', 'DEAI_HOME')",
            'не оточення (підскрипт)': "other['DEAI_HOME'] = d",
            'не оточення (update)': "other.update({'DEAI_HOME': d})",
            'словник без присвоєння': "d = {'DEAI_HOME': d}",
            'update без ключа': "os.environ.update({'HOME': h}); d = {'DEAI_HOME': d}",
            'subprocess без ключа': "subprocess.run(cmd, env=os.environ.copy())",
            'patch.dict без ключа': "mock.patch.dict(os.environ, {'X': 1})",
            'словник не в env=': "subprocess.run(cmd, cwd={'DEAI_HOME': d})",
        }
        for what, src in assigns.items():
            self.assertTrue(self._assigns_deai_home(src), f'{what}: {src!r}')
        for what, src in mentions.items():
            self.assertFalse(self._assigns_deai_home(src), f'{what}: {src!r}')

    def test_every_space_writing_module_wires_the_real_registry_guard(self):
        """Файл, що пише простори, мусить на рівні МОДУЛЯ знімати `spaces_guard.snapshot()` (без аргументів)
        і звіряти ЦЕЙ ЖЕ знімок: `spaces_guard.assert_untouched(<знімок>)`. Обидва виклики — ПРЯМІ
        інструкції тіла хука: під `if False:`, у `try`/`except` чи у вкладеній `def` вони існують у
        тексті, але не виконуються (або їхній провал ковтається) — і без охоронця все лишається
        зеленим. Один позиційний аргумент, без keyword-ів: `assert_untouched(snap, homes=())` звіряв би
        порожній список тек. Розбір через `ast`, а не підрядок: закоментований виклик чи перейменований
        хук підрядок би не побачив."""

        def guard_call(node, attr):
            """`spaces_guard.<attr>(…)` → Call, інакше None."""
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attr and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'spaces_guard'):
                return node
            return None

        offenders = []
        for name, src in self._space_writer_sources():
            hooks = {}
            for node in ast.parse(src).body:       # лише верхній рівень; пізніший `def` перекриває
                if isinstance(node, ast.FunctionDef):
                    hooks[node.name] = node
            up, down = hooks.get('setUpModule'), hooks.get('tearDownModule')
            if up is None or down is None:
                offenders.append(f'{name}: нема {"setUpModule" if up is None else "tearDownModule"}')
                continue
            # setUpModule: `global _REAL` + пряма інструкція `_REAL = spaces_guard.snapshot()`
            declared = {n for st in up.body if isinstance(st, ast.Global) for n in st.names}
            stored = set()
            for st in up.body:
                call = guard_call(st.value, 'snapshot') if isinstance(st, ast.Assign) else None
                if call is not None and not call.args and not call.keywords:
                    stored |= {t.id for t in st.targets if isinstance(t, ast.Name)}
            stored &= declared
            if not stored:
                offenders.append(f'{name}: setUpModule не зберігає знімок прямою інструкцією '
                                 '`global X; X = spaces_guard.snapshot()` (без аргументів)')
            # tearDownModule: пряма інструкція `spaces_guard.assert_untouched(X)`
            ok = False
            for st in down.body:
                call = guard_call(st.value, 'assert_untouched') if isinstance(st, ast.Expr) else None
                if (call is not None and not call.keywords and len(call.args) == 1
                        and isinstance(call.args[0], ast.Name) and call.args[0].id in stored):
                    ok = True
            if not ok:
                offenders.append(f'{name}: tearDownModule не звіряє збережений знімок прямою інструкцією '
                                 '`spaces_guard.assert_untouched(X)` (один аргумент, без keyword-ів)')
        self.assertEqual(offenders, [], 'тести пишуть простори без охоронця справжнього реєстру: '
                                        + '; '.join(offenders))


class OverviewSyncGuard(unittest.TestCase):
    """DC_NO_OVERVIEW має повністю глушити пуш реєстру в прод-Supabase.

    Інцидент 03.08.2026: у прод-таблиці `overview_projects` на КОМАНДНОМУ
    дашборді висіли рядки `fixture` (jira=TEST-1 — рівно фікстура цього файла) і
    `demo2`. Механізм: тести підміняли живий tasks.json фікстурою, а
    _overview_sync (його кличуть publish / gitlab-sync / autosync) запускав
    bin/overview_push.py sync підпроцесом з успадкованим оточенням — той читав
    підмінений конфіг і пушив тестові задачі в реальну базу.
    """

    def setUp(self):
        self._saved = os.environ.get('DC_NO_OVERVIEW')

    def tearDown(self):
        if self._saved is None:
            os.environ.pop('DC_NO_OVERVIEW', None)
        else:
            os.environ['DC_NO_OVERVIEW'] = self._saved

    def test_guard_blocks_registry_push(self):
        os.environ['DC_NO_OVERVIEW'] = '1'
        with mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve.Handler._overview_sync(None)   # self не використовується
        self.assertFalse(popen.called,
                         'з DC_NO_OVERVIEW пуш реєстру не має навіть стартувати')

    def test_without_guard_registry_push_runs(self):
        """Контроль: без змінної пуш працює, інакше тест вище зелений задарма."""
        os.environ.pop('DC_NO_OVERVIEW', None)
        with mock.patch.object(serve.subprocess, 'Popen') as popen:
            serve.Handler._overview_sync(None)
        self.assertEqual(popen.call_count, 1)


class OverviewSyncLog(unittest.TestCase):
    """`_overview_sync` відкриває лог синку ДО `Popen` і мусить його закрити сам: дитина вже має
    власну копію дескриптора, а батьківський файловий обʼєкт лишався відкритим — на збої `Popen`
    назавжди (ResourceWarning), на успіху до збирача сміття. ⛔ Лог — у ТИМЧАСОВІЙ домівці: справжній
    `~/.claude/pipeline-feedback/overview-sync.log` тут не відкривається."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='ovsync-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, '.claude', 'pipeline-feedback'))
        saved = os.environ.get('DC_NO_OVERVIEW')
        os.environ.pop('DC_NO_OVERVIEW', None)

        def restore():
            if saved is None:
                os.environ.pop('DC_NO_OVERVIEW', None)
            else:
                os.environ['DC_NO_OVERVIEW'] = saved
        self.addCleanup(restore)

    def sync(self, popen_error=None):
        """Один `_overview_sync` з підміненим `Popen`; повертає файлові обʼєкти, що дістали `stdout`."""
        seen = []

        def popen(*args, **kw):
            seen.append(kw['stdout'])
            self.assertFalse(kw['stdout'].closed, 'до Popen лог мусить бути відкритий')
            if popen_error:
                raise popen_error
            return mock.MagicMock()
        with mock.patch.dict(os.environ, {'HOME': self.tmp}), \
                mock.patch.object(serve.subprocess, 'Popen', side_effect=popen):
            serve.Handler._overview_sync(None)      # self не використовується
        return seen

    def test_the_log_is_closed_when_popen_fails(self):
        seen = self.sync(OSError('no python3'))
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].closed, 'лог лишився відкритим після збою Popen')

    def test_the_log_is_closed_after_a_successful_start_too(self):
        seen = self.sync()
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].closed, 'батьківська копія логу лишилась відкритою (дитина має свою)')

    def test_no_resource_warning_when_popen_fails(self):
        import gc
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always', ResourceWarning)
            self.sync(OSError('no python3'))
            gc.collect()
        self.assertEqual([str(w.message) for w in caught if issubclass(w.category, ResourceWarning)], [])

    def test_a_log_that_fails_to_close_does_not_make_the_best_effort_sync_raise(self):
        """`close()` на файлі з незбереженим буфером (диск повний) кидає `OSError`: метод «ковтаємо
        помилки» не має кидати з `finally`, ні коли `Popen` стартував, ні коли ні."""
        for popen_error in (None, OSError('no python3')):
            fake = mock.MagicMock()
            fake.close.side_effect = OSError('ENOSPC')
            with self.subTest(popen_error=popen_error):
                with mock.patch.dict(os.environ, {'HOME': self.tmp}), \
                        mock.patch.object(serve, 'open', create=True, return_value=fake), \
                        mock.patch.object(serve.subprocess, 'Popen', side_effect=popen_error or mock.DEFAULT):
                    serve.Handler._overview_sync(None)        # не кидає
                fake.close.assert_called_once_with()

    def test_a_log_that_cannot_be_opened_is_swallowed_and_nothing_starts(self):
        """Тека логу відсутня → `open` кидає ще до `Popen`: best-effort метод не має кидати далі
        (закриття в `finally` не сміє впасти на ще не створеному обʼєкті)."""
        shutil.rmtree(os.path.join(self.tmp, '.claude'))
        self.assertEqual(self.sync(), [])


class PreviewGate(unittest.TestCase):
    """Пароль превʼю: гейт на КОЖНІЙ сторінці, і його можна задати на задачу.

    Інцидент 03.08.2026, перевірений живцем: `dc-sample.vercel.app/` пароль просив,
    а `dc-sample.vercel.app/it4/` віддавав макет — гейт вставлявся лише в обгортку.

    ⚠️ Це гейт у DOM, не автентифікація: пароль лежить у джерелі сторінки. Сенс —
    обмежити радіус зливу однією задачею, а не зробити превʼю приватним.
    """

    def test_gate_uses_task_password_when_set(self):
        cfg = {'tasks': {'t1': {'preview_password': '7788'}}}
        self.assertEqual(
            serve.preview_password(cfg, cfg['tasks']['t1']), '7788')

    def test_gate_falls_back_to_shared_default(self):
        self.assertEqual(serve.preview_password({}, {}), serve.DEFAULT_PREVIEW_PW)

    def test_config_level_password_applies_to_all_tasks(self):
        self.assertEqual(serve.preview_password({'preview_password': '4242'}, {}),
                         '4242')

    def test_gate_is_in_logo_palette_without_old_blue(self):
        """Гейт превʼю — окрема сторінка без styles.css, тож палітру несуть літерали.
        Старий синій (#2d6ae3) і сіро-блакитне тло (#eef0f2) не повертаються;
        кнопка — темна з світлим текстом >= 4.5:1."""
        g = serve.gate_html('t1', '1100').lower()
        for old in ('#2d6ae3', '#eef0f2', '#d5d9dd', '#6b7280'):
            self.assertNotIn(old, g, f'у гейті лишився літерал старої палітри {old}')
        self.assertIn('#authform{width:320px', g.replace('{{', '{').replace('}}', '}'))

        def lum(h):
            h = h.lstrip('#')
            c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
            c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
            return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
        import re
        m = re.search(r'#authform button\{+height:44px;background:(#[0-9a-f]{6});color:(#[0-9a-f]{6})', g)
        self.assertIsNotNone(m, 'не знайшов правило кнопки гейта')
        a, b = sorted((lum(m.group(1)), lum(m.group(2))), reverse=True)
        self.assertGreaterEqual((a + .05) / (b + .05), 4.5)

    def test_password_lands_in_generated_gate(self):
        g = serve.gate_html('t1', '7788')
        self.assertIn(f'P={serve.js_literal("7788")}', g)
        self.assertIn(f'KEY={serve.js_literal("t1_auth")}', g)

    def test_inject_gate_adds_gate_before_body_close(self):
        out = serve._inject_gate('<html><body><h1>макет</h1></body></html>',
                                 serve.gate_html('t1', '1100'))
        self.assertIn('id="authgate"', out)
        self.assertLess(out.index('id="authgate"'), out.index('</body>'))

    def test_inject_gate_is_idempotent(self):
        gate = serve.gate_html('t1', '1100')
        once = serve._inject_gate('<html><body>x</body></html>', gate)
        twice = serve._inject_gate(once, gate)
        self.assertEqual(once, twice)
        self.assertEqual(twice.count('id="authgate"'), 1)

    def test_page_without_body_tag_still_gets_gate(self):
        out = serve._inject_gate('<h1>фрагмент без body</h1>',
                                 serve.gate_html('t1', '1100'))
        self.assertIn('id="authgate"', out)

    def test_shell_defers_iframe_until_gate_opens(self):
        """Рамку не вантажимо до пароля, інакше внутрішній гейт видно всередині неї.

        Хук переїхав із шаблону в `app/ext-shell.js` (обгортка стала тонким
        каркасом), тому тест дивиться туди — і це його МЕЖА, названа вголос:
        він доводить лише те, що хук узагалі є, а не що рамка справді чекає.
        Друге доводить живий тест (`tests/live/ext-shell.test.mjs`), який
        відкриває зібране превʼю до пароля й вимагає, щоб `src` рамки був
        порожній. Дешева статична перевірка лишається тут, бо `npm run
        test:live` не стоїть у CI (рішення власника 01.09.2026), і зникнення
        хука інакше побачив би тільки глядач.
        """
        with open(os.path.join(ROOT, 'app', 'ext-shell.js'), encoding='utf-8') as fh:
            shell = fh.read()
        self.assertIn('window.__onGateOpen', shell)
        self.assertIn('window.__gateOpen', shell)

    def test_gate_signals_shell_on_unlock(self):
        self.assertIn('window.__gateOpen=true', serve.gate_html('t1', '1100'))

    def test_title_is_neutralised_until_unlock(self):
        """Назва задачі й тікет не мають світитись у вкладці до пароля."""
        page = ('<html><head><title>Віджет «Суди» · United · LIGA-7003</title>'
                '</head><body>x</body></html>')
        out = serve._inject_gate(page, serve.gate_html('courts', '1100'))
        self.assertIn('<title>Перегляд макета</title>', out)
        self.assertNotIn('<title>Віджет', out)
        self.assertIn('LIGA-7003', out)          # лишається для відновлення
        self.assertIn('window.__origTitle', out)
        # скрипт із заголовком мусить іти ДО гейта, інакше unlock його не побачить
        self.assertLess(out.index('__origTitle'), out.index('id="authgate"'))

    @staticmethod
    def _orig_title(out):
        """Значення `window.__origTitle` з виходу `_inject_gate`: літерал від присвоєння до ПЕРШОГО
        закриття скрипта (`;</script>`). Літерал `js_literal` — сумісний з JSON (`\\uXXXX`)."""
        start = out.index('window.__origTitle=') + len('window.__origTitle=')
        end = out.index(';</script>', start)
        return json.loads(out[start:end])

    def test_a_title_cannot_break_out_of_the_origtitle_script(self):
        """Назву сторінки пише дизайнер: `</script>` у ній рвав скрипт, а в тому ж гейті лежить
        пароль превʼю (той самий клас, що інцидент 04.08.2026) — літерал іде через `js_literal`."""
        evil = '</script><b>x'
        out = serve._inject_gate(f'<html><head><title>{evil}</title></head><body>x</body></html>',
                                 serve.gate_html('t1', '1100'))
        self.assertNotIn(evil, out)
        self.assertNotIn('</script><b>', out)
        self.assertEqual(self._orig_title(out), evil)       # а значення — те саме, що ввели
        # Скрипт із назвою — рівно один, і він закривається ДО гейта: проривайся `</script>`,
        # перед гейтом стояло б два закриття.
        head = out[:out.index('id="authgate"')]
        self.assertEqual(head.count('</script>'), 1)

    # Значення, що ламали б `<script>` чи JS-літерал: закриття/відкриття скрипта й коментаря, амперсанд
    # (сутності в `<script>` не декодуються, але `&` у літералі — ще й «чужа» розмітка для парсерів),
    # роздільники рядків JS U+2028/U+2029 (`ensure_ascii=False` віддає їх СИРИМИ), переводи рядка.
    HOSTILE = ('</script>', '</SCRIPT >', '<!--', '<!-- <script>', '-->', '<script>alert(1)</script>',
               'a&b', '&lt;/script&gt;', '&#60;', '\u2028x\u2029', 'a\u2028', '\u2029', 'l1\nl2\r\nl3',
               'q"uote\\back', "ap'os", '</\u2028script>')

    @staticmethod
    def _assert_inert_literal(case, lit):
        """Літерал годиться всередині `<script>`: жодного сирого `<`, `>`, `&`, U+2028/2029, переводів
        рядка, тож ні `</script>`, ні `<!--`, ні `-->` не можуть ні закрити скрипт, ні відкрити коментар."""
        for ch, name in (('<', '<'), ('>', '>'), ('&', '&'), ('\u2028', 'U+2028'), ('\u2029', 'U+2029'),
                         ('\n', 'LF'), ('\r', 'CR')):
            case.assertNotIn(ch, lit, f'сирий {name} у літералі')
        low = lit.lower()
        case.assertNotIn('</script', low)
        case.assertNotIn('<!--', lit)
        case.assertNotIn('-->', lit)

    def test_js_literal_is_inert_inside_a_script_block(self):
        for value in self.HOSTILE:
            with self.subTest(value=value):
                lit = serve.js_literal(value)
                self._assert_inert_literal(self, lit)
                self.assertEqual(json.loads(lit), value)          # а значення — те саме

    def test_the_origtitle_literal_is_inert_for_any_title(self):
        """Те саме по ДОРОЗІ `_inject_gate`: заголовок сторінки (сутності розекрановуються) → область між
        `window.__origTitle=` і `;</script>` не містить сирого нічого небезпечного."""
        for src in ('&lt;/script&gt;', '&lt;!--', 'a &amp; b', 'x\u2028y', 'x\u2029y', '</script>', '<!-- t', 'l1\nl2'):
            with self.subTest(title=src):
                out = serve._inject_gate(f'<html><head><title>{src}</title></head><body>x</body></html>',
                                         serve.gate_html('t1', '1100'))
                start = out.index('window.__origTitle=') + len('window.__origTitle=')
                lit = out[start:out.index(';</script>', start)]
                self._assert_inert_literal(self, lit)

    def test_an_escaped_title_is_unescaped_for_the_tab(self):
        """У `<title>` сутності — текст (`R&amp;D` у вкладці = «R&D»); `document.title` — тоже текст,
        тож після входу вкладка мусить показати «R&D», а не буквальні `&amp;`."""
        for raw, shown in (('R&amp;D', 'R&D'),
                           ('Тарифи &laquo;Про&raquo; &#39;x&#39;', "Тарифи «Про» 'x'"),
                           ('A &lt;/script&gt; &amp; B', 'A </script> & B'),
                           ('&amp;amp;', '&amp;'),                 # одна розекранівка, не дві
                           ('без сутностей', 'без сутностей')):
            with self.subTest(raw=raw):
                out = serve._inject_gate(f'<html><head><title>{raw}</title></head><body>x</body></html>',
                                         serve.gate_html('t1', '1100'))
                self.assertEqual(self._orig_title(out), shown)
                self.assertNotIn('</script> &', out)
                self.assertIn('<title>Перегляд макета</title>', out)

    def test_page_without_title_still_gated(self):
        out = serve._inject_gate('<html><body>x</body></html>',
                                 serve.gate_html('t1', '1100'))
        self.assertIn('id="authgate"', out)
        # рядок `window.__origTitle` є в самому гейті (відновлення заголовка),
        # тому перевіряємо саме ПРИСВОЄННЯ, якого не має бути без <title>
        self.assertNotIn('window.__origTitle=', out)

    def test_cyrillic_title_does_not_break_injection(self):
        """`json.dumps` дає \\uXXXX для кирилиці, а re.sub трактує бекслеш у рядку
        ЗАМІНИ як escape — через це вставка гейта ламалась цілком (03.08.2026)."""
        page = '<html><head><title>Суди · LIGA-7003</title></head><body>м</body></html>'
        out = serve._inject_gate(page, serve.gate_html('courts', '1100'))
        self.assertIn('id="authgate"', out)
        self.assertIn('window.__origTitle=', out)
        self.assertIn('<title>Перегляд макета</title>', out)

    def test_snippet_with_backslash_is_inserted_literally(self):
        out = serve._insert_before_body('<html><body>x</body></html>',
                                        r'<i>\u0421 \1 \\</i>')
        self.assertIn(r'<i>\u0421 \1 \\</i>', out)


class VercelProjectStability(unittest.TestCase):
    """Публікація не має молча змінювати prod-URL, який уже може бути в менеджера.

    `publish/` затирається щопублікації разом із `.vercel/project.json`, тому
    зв'язок задача→Vercel-проєкт лишається ТІЛЬКИ в `tasks.json`. 03.08.2026
    поля не було у чотирьох задач із живими превʼю — наступна публікація
    сминтила б нове імʼя й видала інше посилання.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='vp-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # Конфіг — тимчасовий: `_vercel_project` читає `load_tasks()`, і без
        # цього тест брав ЖИВИЙ tasks.json дизайнера, а в чистому клоні (колега,
        # CI, git worktree) падав FileNotFoundError (знайдено 27.09.2026).
        cfg = os.path.join(self.tmp, 'tasks.json')
        with open(cfg, 'w', encoding='utf-8') as fh:
            json.dump({'current': None, 'tasks': {}}, fh)
        old = os.environ.get('DC_TASKS_FILE')
        os.environ['DC_TASKS_FILE'] = cfg
        self.addCleanup(lambda: os.environ.pop('DC_TASKS_FILE', None) if old is None
                        else os.environ.__setitem__('DC_TASKS_FILE', old))

    def _task(self, publish_url=None):
        with open(os.path.join(self.tmp, 'iterations.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump({'iterations': [], **({'publish_url': publish_url}
                                            if publish_url else {})}, fh)
        return {'dir': self.tmp, 'title': 'T'}

    def test_existing_field_is_reused(self):
        t = self._task('https://dc-x.vercel.app')
        t['vercel_project'] = 'dc-x'
        self.assertEqual(serve._vercel_project('x', t), 'dc-x')

    def test_published_task_without_field_refuses_loudly(self):
        with self.assertRaises(OSError) as cm:
            serve._vercel_project('x', self._task('https://dc-x.vercel.app'))
        msg = str(cm.exception)
        self.assertIn('vercel_project', msg)
        self.assertIn('dc-x.vercel.app', msg)   # видно, який URL під загрозою

    def test_never_published_task_still_mints(self):
        real_save = serve.save_tasks
        serve.save_tasks = lambda cfg: None
        try:
            name = serve._vercel_project('brand-new', self._task())
        finally:
            serve.save_tasks = real_save
        self.assertTrue(name.startswith('pv-'))
        self.assertEqual(len(name), 11)


class PreviewBelongsToOwner(unittest.TestCase):
    """Превʼю спільної задачі — у ВЛАСНИКА (рішення власника 29.09.2026,
    fb-29092026-69e9c7 + fb-29092026-210ec1). Не-власник публікує у СВОЄ превʼю
    й чує, що це не посилання задачі; його лінк не розʼїжджається колегам."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pvo-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        cfg = os.path.join(self.tmp, 'tasks.json')
        with open(cfg, 'w', encoding='utf-8') as fh:
            json.dump({'current': None, 'tasks': {}}, fh)
        env = {'DC_TASKS_FILE': cfg, 'DC_IDENTITY_NAME': 'Я', 'DC_IDENTITY_EMAIL': 'me@x'}
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None
                                 else os.environ.__setitem__(k, v) for k, v in old.items()])

    def _task(self, owner_key, publish_url=None):
        with open(os.path.join(self.tmp, 'iterations.json'), 'w', encoding='utf-8') as fh:
            json.dump({'iterations': [], **({'publish_url': publish_url}
                                            if publish_url else {})}, fh)
        return {'dir': self.tmp, 'title': 'T', 'owner': 'Власник', 'owner_key': owner_key}

    def test_non_owner_mints_own_project_instead_of_refusing(self):
        """Адресу власника не-власник отримав через «Підтягнути». Відмова «задача
        вже публікувалась» тут хибна: це не ЙОГО посилання він би змінив."""
        real_save = serve.save_tasks
        serve.save_tasks = lambda cfg: None
        try:
            name = serve._vercel_project('boss', self._task('owner@x', 'https://pv-2.vercel.app'))
        finally:
            serve.save_tasks = real_save
        self.assertTrue(name.startswith('pv-'))

    def test_owner_still_refuses_to_change_published_url(self):
        with self.assertRaises(OSError):
            serve._vercel_project('boss', self._task('me@x', 'https://pv-2.vercel.app'))

    def test_not_task_link_names_the_owner_only_for_non_owner(self):
        self.assertEqual(serve._not_task_link(self._task('owner@x')), 'Власник')
        self.assertIsNone(serve._not_task_link(self._task('me@x')))
        self.assertIsNone(serve._not_task_link({'dir': self.tmp}), 'без власника — як було')

    def test_pull_adopts_link_only_from_owner(self):
        task = self._task('owner@x')
        meta = {'publish_url': 'https://pv-2.vercel.app'}
        serve._adopt_publish_state(meta, {'publish_url': 'https://pv-9-x.vercel.app',
                                          'author_key': 'colleague@x'}, task)
        self.assertEqual(meta['publish_url'], 'https://pv-2.vercel.app',
                         'лінк не-власника приїхав як посилання задачі')
        serve._adopt_publish_state(meta, {'publish_url': 'https://pv-3.vercel.app',
                                          'author_key': 'owner@x'}, task)
        self.assertEqual(meta['publish_url'], 'https://pv-3.vercel.app')

    def test_old_state_without_author_is_adopted(self):
        """Стан, записаний версією без підпису автора, — лояльно, як досі."""
        meta = {}
        serve._adopt_publish_state(meta, {'publish_url': 'https://pv-3.vercel.app'},
                                   self._task('owner@x'))
        self.assertEqual(meta['publish_url'], 'https://pv-3.vercel.app')

    def test_adopt_requires_the_task(self):
        """Забутий аргумент мовчки вимикав правило (`task=None` за замовчуванням)."""
        with self.assertRaises(TypeError):
            serve._adopt_publish_state({}, {})

    def test_pull_without_owner_or_author_adopts_as_before(self):
        meta = {}
        serve._adopt_publish_state(meta, {'publish_url': 'https://pv-3.vercel.app'},
                                   {'dir': self.tmp})
        self.assertEqual(meta['publish_url'], 'https://pv-3.vercel.app')

    def test_suffixed_domain_is_named(self):
        """Другий акаунт із тим самим імʼям отримує `pv-XXXX-<суфікс>.vercel.app` —
        і дизайнери не помічають, що в них різні посилання (210ec1)."""
        self.assertIsNone(serve._preview_domain_warning('https://pv-12345678.vercel.app',
                                                        'pv-12345678'))
        w = serve._preview_domain_warning('https://pv-12345678-abc123.vercel.app', 'pv-12345678')
        self.assertIn('pv-12345678-abc123.vercel.app', w)
        self.assertIn('pv-12345678.vercel.app', w)


class VercelScopeBinding(unittest.TestCase):
    """Імʼя проєкту саме по собі посилання не тримає: у ЧУЖОМУ акаунті
    `vercel link --project <те саме імʼя>` створює ІНШИЙ проєкт, і задача
    отримує друге посилання. Прив'язка = пара імʼя+скоуп."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='vs-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pub = os.path.join(self.tmp, 'publish')
        os.makedirs(os.path.join(self.pub, '.vercel'))
        self._saved = []
        real_save, real_load = serve.save_tasks, serve.load_tasks
        serve.save_tasks = self._saved.append
        serve.load_tasks = lambda: {'tasks': {}}
        self.addCleanup(setattr, serve, 'save_tasks', real_save)
        self.addCleanup(setattr, serve, 'load_tasks', real_load)

    def _project_json(self, **kw):
        with open(os.path.join(self.pub, '.vercel', 'project.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump(kw, fh)

    def test_scope_is_remembered_from_project_json(self):
        self._project_json(orgId='team_abc', projectName='pv-1')
        task = {}
        serve._remember_vercel_scope('x', task, self.pub)
        self.assertEqual(task['vercel_scope'], 'team_abc')
        self.assertEqual(self._saved[0]['tasks']['x']['vercel_scope'], 'team_abc')

    def test_existing_scope_is_not_overwritten(self):
        self._project_json(orgId='team_other')
        task = {'vercel_scope': 'team_ours'}
        serve._remember_vercel_scope('x', task, self.pub)
        self.assertEqual(task['vercel_scope'], 'team_ours')
        self.assertEqual(self._saved, [], 'нічого писати не мали')

    def test_missing_file_is_not_a_crash(self):
        """Best-effort: без файлу просто не записуємо — про неповну прив'язку
        скаже інваріант vercel-binding-unshared, а публікацію валити нема за що."""
        task = {}
        serve._remember_vercel_scope('x', task, self.pub)
        self.assertNotIn('vercel_scope', task)

    def test_foreign_scope_error_gets_its_own_hint(self):
        """Помилка про скоуп мусить давати СВОЮ підказку, а не загальну про
        доступ: причина конкретніша, і дія інша."""
        hint = serve._deploy_hint("Error: You don't have access to the team 'x'")
        self.assertIn('ДРУГЕ', hint)
        self.assertIn('vercel_scope', hint)

    def test_plain_permission_error_keeps_generic_hint(self):
        hint = serve._deploy_hint('Error: Forbidden')
        self.assertIn('Немає доступу до Vercel-проєкту', hint)


class RegistryPushGuard(unittest.TestCase):
    """Підмінений конфіг не має права писати у СПІЛЬНУ гілку `registry` на GitLab.

    Інцидент, знайдений після релізу v1.10.0: `test_task_new_*` створює задачу
    `demo2` через /api/task-new, а `_registry_push` пушив її в реєстр КОМАНДИ.
    Кожен прогін сюїти повертав `demo2` — видалив о 16:05, о 16:11 було знову.
    `DC_NO_OVERVIEW` цей шлях не покривав: він про Supabase, а це окремий, git-овий.
    """

    def setUp(self):
        self._saved = {k: os.environ.get(k)
                       for k in ('DC_TASKS_FILE', 'DC_NO_OVERVIEW')}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_substituted_config_blocks_registry_push(self):
        os.environ['DC_TASKS_FILE'] = '/tmp/fixture-tasks.json'
        os.environ.pop('DC_NO_OVERVIEW', None)
        with mock.patch.dict('sys.modules', {'registry': mock.MagicMock()}) as mods:
            self.assertFalse(serve._registry_push('demo2'))
            mods['registry'].push_tasks.assert_not_called()

    def test_no_overview_also_blocks(self):
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ['DC_NO_OVERVIEW'] = '1'
        with mock.patch.dict('sys.modules', {'registry': mock.MagicMock()}) as mods:
            self.assertFalse(serve._registry_push('demo2'))
            mods['registry'].push_tasks.assert_not_called()

    def test_real_config_still_pushes(self):
        """Контроль: без підміни пуш працює, інакше тести вище зелені задарма."""
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        fake = mock.MagicMock()
        with mock.patch.dict('sys.modules', {'registry': fake}):
            self.assertTrue(serve._registry_push('courts'))
            fake.push_tasks.assert_called_once_with(['courts'])

    def test_refused_fixture_is_not_reported_as_registered(self):
        """15.09.2026 конфіг НЕ був підмінений — гвард вище мовчав, і `nova`
        поїхала в реєстр. Тепер її відмовляє сам `push_tasks`, і `task_new`
        не має казати «registered», коли задачу НЕ зареєстровано."""
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        sys.path.insert(0, os.path.join(ROOT, 'bin'))
        import registry as real
        fake = mock.MagicMock()
        fake.push_tasks.return_value = real.PushResult([], {'nova': 'gitlab.repo у /var/folders'})
        with mock.patch.dict('sys.modules', {'registry': fake}):
            self.assertFalse(serve._registry_push('nova'))


class IterationLabel(unittest.TestCase):
    """Підпис ітерації для дропдауна. Правило жило в JS (app.js itLabel), і для
    обгортки превʼю його довелось би вважати ще й у Python — тому воно переїхало
    на сервер, а канвас бере готове поле з /api/task."""

    def test_explicit_label_wins(self):
        self.assertEqual(
            serve.iteration_label({'id': 'it2', 'label': 'Категорія', 'note': 'inne'}),
            'Іт.2 · Категорія')

    def test_note_without_ticket_prefix(self):
        self.assertEqual(
            serve.iteration_label({'id': 'it3', 'note': 'LIGA-7003 · Пошук'}),
            'Іт.3 · Пошук')

    def test_bare_iteration_number(self):
        self.assertEqual(serve.iteration_label({'id': 'it4'}), 'Іт.4')

    def test_number_stays_visible_with_label(self):
        """Номером говорять state.py і синк — він мусить лишатись у підписі."""
        self.assertIn('Іт.7', serve.iteration_label({'id': 'it7', 'label': 'Хаб'}))

    def test_blank_label_falls_through_to_number(self):
        self.assertEqual(serve.iteration_label({'id': 'it1', 'label': '   '}), 'Іт.1')

    def test_note_is_the_cleaned_text_without_any_prefix(self):
        """`iteration_note()` — ДАНІ без презентації: те саме очищення, але без
        «Іт.N». Саме воно їде в `publish/manifest.json`, бо префікс у зовнішній
        оболонці складає словник (`iterTag`) мовою ГЛЯДАЧА."""
        self.assertEqual(
            serve.iteration_note({'id': 'it2', 'label': 'Категорія', 'note': 'inne'}),
            'Категорія')
        self.assertEqual(
            serve.iteration_note({'id': 'it3', 'note': 'LIGA-7003 · Пошук'}), 'Пошук')
        self.assertEqual(serve.iteration_note({'id': 'it4'}), '')
        self.assertEqual(serve.iteration_note({'id': 'it1', 'label': '   '}), '')

    def test_note_and_label_share_one_cleaning_rule(self):
        """Парний інваріант на дві функції, що живуть із одного правила.

        Консументів двоє й вони різні: `/api/task` бере готовий `label_text`
        (`iteration_label`), маніфест превʼю бере `note` (`iteration_note`).
        Якби кожен зрізав «LIGA-1234 · » сам, вони розійшлися б на першій же
        правці формату тікета — і розходження було б видно ЛИШЕ в чужому
        браузері: канвас показує одне, превʼю інше. Тому перевіряємо не два
        результати окремо, а те, що перший СКЛАДАЄТЬСЯ з другого.
        """
        for it in ({'id': 'it2', 'label': 'Категорія', 'note': 'inne'},
                   {'id': 'it3', 'note': 'LIGA-7003 · Пошук'},
                   {'id': 'it4'},
                   {'id': 'it1', 'label': '   '},
                   {'id': 'it9', 'note': 'ABC-1: без крапки'}):
            note = serve.iteration_note(it)
            tag = 'Іт.%s' % serve.iter_num(it['id'])
            self.assertEqual(serve.iteration_label(it),
                             '%s · %s' % (tag, note) if note else tag, it)


class TaskApiFields(unittest.TestCase):
    """Канвасу потрібні: готовий підпис ітерації (щоб не вважати правило вдруге)
    і пароль превʼю (щоб зібрати посилання з кодом для менеджера)."""

    def test_label_text_added_without_touching_meta(self):
        meta = {'iterations': [{'id': 'it1', 'label': 'Головна'}]}
        out = serve.task_api_iterations(meta)
        self.assertEqual(out[0]['label_text'], 'Іт.1 · Головна')
        self.assertNotIn('label_text', meta['iterations'][0],
                         'meta не мутуємо: label_text поїхав би в iterations.json')

    def test_original_fields_survive(self):
        out = serve.task_api_iterations({'iterations': [
            {'id': 'it2', 'date': '04.08.2026', 'published': True}]})
        self.assertEqual(out[0]['date'], '04.08.2026')
        self.assertIs(out[0]['published'], True)

    def test_no_iterations_is_empty_list(self):
        self.assertEqual(serve.task_api_iterations({}), [])


class PublishedPages(unittest.TestCase):
    """Обхід сторінок для публікації був дубльований: свій цикл із власним
    фільтром у serve._publish і в ops/reseal_gate.py. Дві копії того самого
    рішення — рівно та пара, що розходиться молча."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pp-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _task(self, pages_by_it):
        """`None` → стара ітерація БЕЗ pages.json, лише index.html; список → явне
        дерево сторінок.

        ⚠️ Різниця принципова: `pages_model.read_pages` синтезує неявну
        «Головну» ТІЛЬКИ коли `pages.json` відсутній, а `index.html` є. Файл
        `pages.json` зі `{"pages": []}` означає інше — «в ітерації свідомо нуль
        сторінок» (реальний стан після видалення останньої). Фікстура, яка пише
        порожній `pages.json`, неявну main не отримає.
        """
        for it, pages in pages_by_it.items():
            d = os.path.join(self.tmp, 'iterations', it)
            os.makedirs(d, exist_ok=True)
            if pages is None:
                with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as fh:
                    fh.write('<html></html>')
            else:
                with open(os.path.join(d, 'pages.json'), 'w', encoding='utf-8') as fh:
                    json.dump({'pages': pages}, fh)
        return {'dir': self.tmp}

    def test_implicit_main_page_maps_to_iteration_id(self):
        task = self._task({'it1': None})
        out = serve.published_pages(task, [{'id': 'it1'}])
        self.assertEqual([p['out_rel'] for p in out], ['it1'])
        self.assertEqual(out[0]['rel'], '')

    def test_group_organizer_is_not_published(self):
        task = self._task({'it1': [
            {'id': 'grp', 'name': 'Група', 'isGroup': True,
             'children': [{'id': 'a', 'name': 'А'}]}]})
        out = serve.published_pages(task, [{'id': 'it1'}])
        self.assertEqual([p['out_rel'] for p in out], ['it1/a'])

    def test_unpublished_page_is_skipped(self):
        task = self._task({'it1': [
            {'id': 'a', 'name': 'А'},
            {'id': 'b', 'name': 'Б', 'published': False}]})
        out = serve.published_pages(task, [{'id': 'it1'}])
        self.assertEqual([p['name'] for p in out], ['А'])

    def test_hidden_folder_hides_its_pages(self):
        task = self._task({'it1': [
            {'id': 'd', 'name': 'Чернетки', 'kind': 'folder', 'published': False,
             'children': [{'id': 'a', 'name': 'А', 'kind': 'page'}]},
            {'id': 'b', 'name': 'Б', 'kind': 'page'}]})
        out = serve.published_pages(task, [{'id': 'it1'}])
        self.assertEqual([p['out_rel'] for p in out], ['it1/b'])

    def test_state_of_a_hidden_page_is_hidden_too(self):
        """Рішення власника 30.09.2026: приховування — на все піддерево."""
        task = self._task({'it1': [
            {'id': 'a', 'name': 'А', 'published': False, 'children': [
                {'id': 'a1', 'name': 'Стан', 'published': True}]}]})
        self.assertEqual(serve.published_pages(task, [{'id': 'it1'}]), [])

    def test_folder_without_isgroup_is_not_published_as_a_page(self):
        """Нова тека має лише `kind: 'folder'` (без легасі `isGroup`): старий
        фільтр за `isGroup` пустив би її у превʼю як сторінку без файла."""
        task = self._task({'it1': [
            {'id': 'f', 'name': 'Тека', 'kind': 'folder', 'children': [
                {'id': 'a', 'name': 'А', 'kind': 'page'}]}]})
        out = serve.published_pages(task, [{'id': 'it1'}])
        self.assertEqual([(p['out_rel'], p['depth']) for p in out], [('it1/a', 1)])

    def test_pick_page_skips_a_folder_that_has_only_kind(self):
        """`_pick_page` дивився лише на `isGroup`: тека з одним `kind: 'folder'`
        вважалась би відкриваною, і канвас відкрив би теку, якої нема на диску."""
        task = self._task({'it1': [
            {'id': 'f', 'name': 'F', 'kind': 'folder', 'children': [
                {'id': 'a', 'name': 'А', 'kind': 'page'}]}]})
        self.assertEqual(serve._pick_page(task, 'it1', 'f')['id'], 'a')
        self.assertEqual(serve._pick_page(task, 'it1', 'a')['id'], 'a')
        # рішення «відкривається?» — те саме, що дає `openable_pages`, а не паралельна перевірка
        with mock.patch.object(serve.pm, 'openable_pages', lambda pages: []):
            self.assertIsNone(serve._pick_page(task, 'it1', 'a'))
        # легасі-організатор поводиться так само
        legacy = self._task({'it2': [
            {'id': 'g', 'name': 'G', 'isGroup': True, 'children': [
                {'id': 'b', 'name': 'Б'}]}]})
        self.assertEqual(serve._pick_page(legacy, 'it2', 'g')['id'], 'b')

    def _shared_task(self):
        it = os.path.join(self.tmp, 'iterations', 'it1')
        for d, f in (('icons', 'a.svg'), ('assets', 'u.css'), ('fonts', 'f.woff'), ('a', 'index.html')):
            os.makedirs(os.path.join(it, d), exist_ok=True)
            with open(os.path.join(it, d, f), 'w') as fh:
                fh.write('x')
        for f in ('flow.json', 'notes.txt'):
            with open(os.path.join(it, f), 'w') as fh:
                fh.write('{}')
        return self._task({'it1': [
            {'id': 'icons', 'name': 'Icons', 'kind': 'folder', 'children': [
                {'id': 'a', 'name': 'А', 'kind': 'page'}]},
            {'id': 'assets', 'name': 'Assets', 'isGroup': True}]})

    def test_a_folder_named_like_a_shared_dir_does_not_swallow_it(self):
        """Тека — не каталог на диску: її id `icons`/`assets` не сміє виключити
        справжні спільні теки з публікації; а каталоги сторінок виключаються."""
        task = self._shared_task()
        dst = os.path.join(self.tmp, 'out')
        carried = serve.copy_iteration_shared(task, 'it1', dst)
        self.assertIn('icons', carried)
        self.assertIn('assets', carried)
        self.assertIn('fonts', carried)
        self.assertNotIn('a', carried)
        self.assertTrue(os.path.isfile(os.path.join(dst, 'icons', 'a.svg')))

    def test_pages_json_and_flow_json_do_not_ship_in_the_preview(self):
        """pages.json і flow.json виказали б імена й структуру СХОВАНИХ вузлів;
        читача в превʼю нема (оболонка живе з manifest.json)."""
        task = self._shared_task()
        dst = os.path.join(self.tmp, 'out')
        carried = serve.copy_iteration_shared(task, 'it1', dst)
        self.assertNotIn('pages.json', carried)
        self.assertNotIn('flow.json', carried)
        self.assertFalse(os.path.exists(os.path.join(dst, 'pages.json')))
        self.assertFalse(os.path.exists(os.path.join(dst, 'flow.json')))
        self.assertIn('notes.txt', carried)       # решта спільного їде як їхала

    def test_hidden_root_page_html_does_not_ship_as_a_shared_file(self):
        """Знята з превʼю `main` (rel '') — це її `index.html` у КОРЕНІ ітерації.
        Як «спільний файл» він їхав у превʼю завжди, ще й БЕЗ гейта (живе
        превʼю smida-shareholders, 07.10.2026). CSS кореня — спільний і їде."""
        task = self._shared_task()
        it = os.path.join(task['dir'], 'iterations', 'it1')
        for f, body in (('index.html', '<html><body>схована main</body></html>'),
                        ('sample.htm', '<p>x</p>'), ('root.css', '.x{}')):
            with open(os.path.join(it, f), 'w') as fh:
                fh.write(body)
        dst = os.path.join(self.tmp, 'out')
        carried = serve.copy_iteration_shared(task, 'it1', dst)
        self.assertNotIn('index.html', carried)
        self.assertNotIn('sample.htm', carried)
        self.assertFalse(os.path.exists(os.path.join(dst, 'index.html')))
        self.assertIn('root.css', carried)

    def test_given_trees_are_the_only_source_no_second_read(self):
        """Один знімок дерев на збірку: з `trees` жодна з трьох функцій не читає
        pages.json вдруге (між читаннями дизайнер міг змінити дерево, і
        `outline` розійшовся б із `pages`)."""
        task = self._shared_task()
        its = [{'id': 'it1'}]
        trees = {'it1': serve.iteration_pages(task, 'it1')}
        dst = os.path.join(self.tmp, 'pub')
        os.makedirs(dst)
        with mock.patch.object(serve, 'iteration_pages',
                               side_effect=AssertionError('повторне читання дерева')):
            pages = serve.published_pages(task, its, trees)
            serve.copy_iteration_shared(task, 'it1', os.path.join(dst, 'it1'), trees['it1'])
            man = serve.publish_manifest(task, 't', its, pages, {}, dst, trees)
        self.assertEqual([r['key'] for r in man['outline'] if r['kind'] != 'folder'],
                         [p['key'] for p in man['pages']])

    def test_iterations_keep_their_order_and_owner(self):
        task = self._task({'it1': [{'id': 'a', 'name': 'А'}],
                           'it2': [{'id': 'b', 'name': 'Б'}]})
        out = serve.published_pages(task, [{'id': 'it1'}, {'id': 'it2'}])
        self.assertEqual([(p['it'], p['out_rel']) for p in out],
                         [('it1', 'it1/a'), ('it2', 'it2/b')])


class GateKeepsHash(unittest.TestCase):
    """Гейт мусить зʼїдати ЛИШЕ свій k=, бо в тому ж hash їде p=<сторінка> —
    глибоке посилання обгортки."""

    def test_snippet_filters_only_k(self):
        js = serve.gate_html('x', '1100')
        self.assertIn("indexOf('k=')!==0", js,
                      'решта hash мусить фільтруватись, а не зноситись')

    def test_snippet_no_longer_wipes_whole_hash(self):
        js = serve.gate_html('x', '1100')
        self.assertNotIn("history.replaceState(null,'',location.pathname+location.search);",
                         js, 'саме цей рядок і вбивав #p=')

    def test_password_and_key_still_land_in_snippet(self):
        js = serve.gate_html('courts', '4242')
        self.assertIn(f'P={serve.js_literal("4242")}', js)
        self.assertIn(f'KEY={serve.js_literal("courts_auth")}', js)


class PreviewWrapper(unittest.TestCase):
    """Обгортка превʼю — ТОНКИЙ КАРКАС: гейт, точки монтування, один модуль.

    До 02.09.2026 вона несла все сама: перелік ітерацій і сторінок інлайном
    (`var D={…}`), власне дерево шарів із власними каретками, власний дропдаун
    ітерацій і власний CSS — сто з гаком рядків, які повторювали оболонку
    інструмента іншими іменами класів і розходились із нею на кожній правці.
    Тепер стан приходить із `manifest.json`, а малює його ТА САМА оболонка з
    `publish/shell/`.

    Що перевіряють ІНШІ класи — щоб цей не переказував їх словами:
      · склад стану (ітерації, сторінки, глибина, ключі кадрів) —
        `PublishManifest`;
      · перелік спільних модулів і його замкнутість — `ShellModulesList`;
      · «рамка не вантажиться до гейта» з боку ГЕЙТА — `PreviewGate`, а з боку
        поведінки — живий `tests/live/ext-shell.test.mjs`;
      · дерево, екранування назв, глибокі посилання — юніти
        `tests/ext-shell.test.mjs` і `tests/shell-panel.test.mjs`, на чистому
        стані, без збірки артефакта.
    """

    def _html(self, pw='1100'):
        return serve.preview_index_html('<!--gate-->', pw)

    def test_gate_is_embedded(self):
        self.assertIn('<!--gate-->', self._html())

    def test_carries_mount_points_and_exactly_one_module(self):
        """Каркас — це вузли й ОДИН скрипт. Другий `type="module"` означав би,
        що оболонка знову збирається у двох місцях."""
        h = self._html()
        for node in ('id="bar"', 'id="frame"', 'id="sprite"'):
            self.assertIn(node, h, f'{node} — оболонці нікуди монтуватись')
        self.assertIn('shell/ext-shell.js', h)
        self.assertEqual(h.count('type="module"'), 1)

    def test_styles_come_from_the_shared_copy(self):
        """`shell/styles.css`, а не свій CSS у шаблоні: єдине, що робить зовнішню
        оболонку схожою на внутрішню, — ТОЙ САМИЙ файл, а не схожі правила."""
        h = self._html()
        self.assertIn('href="shell/styles.css"', h)
        self.assertNotIn('<style>', h)

    def test_frame_starts_without_src(self):
        """Порожній `src` — половина запобіжника «гейт не всередині рамки»:
        друга (хук `__onGateOpen`) живе в `ext-shell.js` і доводиться живим
        тестом. Тут — те, що видно в самому артефакті: обгортка, зібрана з
        `src`, показала б внутрішній гейт у рамці ще до пароля (03.08.2026)."""
        m = re.search(r'<iframe[^>]*>', self._html())
        self.assertIsNotNone(m, 'рамки в каркасі немає зовсім')
        self.assertNotIn('src=', m.group(0))

    def test_password_goes_as_js_literal_not_html_entities(self):
        """`_html.escape` тут не той інструмент: ентіті в `<script>` не
        декодуються, тому пароль `a'b&c` ставав `a&#x27;b&amp;c` — безшовний вхід
        тихо не збігався з гейтом, а сирий апостроф у гейті взагалі робив
        невалідний JS, після якого оверлей не прибрати ЖОДНИМ паролем.

        Пароль лишається в обгортці й після переїзду стану в маніфест: за ним
        стоїть «Копіювати посилання» (`#k=…`), а маніфест — спільний файл,
        який читає оболонка, і пароль задачі йому знати нізащо."""
        h = self._html(pw="a'b&c")
        self.assertIn(f'__extPw={serve.js_literal("a\'b&c")}', h)
        self.assertNotIn('&#x27;', h, 'HTML-ентіті в <script> не декодуються')
        self.assertIn(f'P={serve.js_literal("a\'b")}', serve.gate_html('t', "a'b"))

    def test_manifest_is_not_inlined(self):
        """⛔ Маніфест вантажиться `fetch('manifest.json')`, а не інлайном, і
        причина не в розмірі: `ops/reseal_gate.py` перезбирає ЛИШЕ `index.html`
        і кадрів не рахує взагалі. Інлайнений стан означав би, що після кожного
        перепечатування гейту обгортка везе НОВИЙ скрипт і СТАРІ дані — тихо,
        без жодної ознаки. Окремий файл пише лише `_publish`, тож reseal не має
        чого зістарити."""
        h = self._html()
        for gone in ('__extManifest', 'var D=', '"pages"', '"iters"'):
            self.assertNotIn(gone, h, f'{gone} в обгортці зістариться після reseal')

    def test_wrapper_has_nowhere_to_take_names_from(self):
        """Структурний запобіжник замість перевірки рядків: сигнатура збирача не
        приймає ні назви задачі, ні сторінок, тому вони не можуть просочитись у
        `index.html` навіть помилково.

        Це закриває цілий клас багів, а не один: рівно так 04.08.2026 назва
        сторінки `</script><img src=x onerror=…>` рвала скрипт обгортки —
        панель умирала, картинка виконувалась, а в тому ж скрипті лежав пароль
        превʼю. Тепер назви живуть у JSON-файлі, який ніхто не вставляє в
        `<script>`, а екранує їх `esc()` у `shell-panel.js`/`ext-bar.js`
        (юніти)."""
        import inspect
        params = list(inspect.signature(serve.preview_index_html).parameters)
        self.assertEqual(params, ['gate', 'pw'])

    def test_title_stays_neutral(self):
        """Правило 30.07.2026: URL превʼю може потрапити кому завгодно, тому до
        пароля ні назви задачі, ні тікета. У каркасі назви немає взагалі
        (тест вище), тож `<title>` не має чого світити — справжній ставить
        оболонка після гейта."""
        self.assertIn('<title>Перегляд макета</title>', self._html())

    def test_old_wrapper_markup_is_gone(self):
        """Прибрано, а не лишено «про всяк випадок»: мертвий CSS і мертвий
        скрипт у шаблоні читаються як робочі, і наступна правка панелі почалась
        би з них. Перелічені імена — рівно ті, що були в старій обгортці."""
        h = self._html()
        for dead in ('id="pp"', 'id="it"', 'id="tg"', 'id="list"', 'id="cp"',
                     'class="r ', 'class="cr', 'class="ttl"', 'dcpp-collapsed'):
            self.assertNotIn(dead, h, f'{dead} — розмітка старої обгортки')

    def test_no_format_placeholders_survive(self):
        """Шаблон іде через str.format: незакрита дужка вилізла б тут."""
        h = self._html()
        self.assertNotIn('{gate}', h)
        self.assertNotIn('{pw_js}', h)



class InspectorDsProfile(unittest.TestCase):
    """Напрямок задачі доїжджає в документ макета — інакше звіряти нема з чим.

    Документ макета про задачу не знає нічого: `profile` лежить у tasks.json, і
    бачить його лише сервер, що вставляє тег інспектора. Без цього параметра
    інспектор лишається без ДС і мовчки не звіряє нічого — тобто виглядає рівно
    так, ніби звірив і не знайшов порушень.
    """

    def test_profile_rides_in_the_module_url(self):
        html = serve.inject_comment_layer(
            "<html><body></body></html>", "p", "/vendor",
            inspector=True, profile="united")
        self.assertIn("inspector.js?ds=united", html)

    def test_local_channel_carries_it_too(self):
        html = serve.inject_local_comment_layer(
            "<html><body></body></html>", "/e", "p", "/vendor", profile="liga360")
        self.assertIn("inspector.js?ds=liga360", html)

    def test_no_profile_means_no_parameter(self):
        """Порожньо — і це ЧЕСНА відповідь: невідомий напрямок вимикає звірку
        (`setDsProfile`), а вигаданий звіряв би макет із чужою ДС."""
        html = serve.inject_comment_layer(
            "<html><body></body></html>", "p", "/vendor", inspector=True)
        self.assertIn('src="/vendor/inspector.js"', html)

    def test_junk_profile_never_reaches_the_markup(self):
        """У параметр URL, що їде в розмітку, не сміє потрапити нічого, крім
        простого імені напрямку."""
        for junk in ('u"><script>x</script>', "../../etc", "a b", "x" * 40):
            html = serve.inject_comment_layer(
                "<html><body></body></html>", "p", "/vendor",
                inspector=True, profile=junk)
            self.assertIn('src="/vendor/inspector.js"', html)
            self.assertNotIn("ds=", html)


class CommentSnippetSelfReports(unittest.TestCase):
    """Шар коментарів, який не піднявся, мусить сказати це на сторінці.

    Сніпет тягне supabase-js з CDN. Без обробки помилки колега на превʼю бачить
    сторінку без пінів і робить висновок, що коментарів немає, — замість
    «коментарі зараз недоступні».

    ⛔ Тести тут чіпляються за КОД, а не за слова. Перша версія перевіряла
    `assertIn('onerror', …)` і `assertIn('catch', …)` по всьому тексту шаблону —
    а половина того тексту це українські коментарі, у яких обидва слова
    трапляються самі по собі. Ревʼю 28.08.2026 зняло ВСІ чотири запобіжники
    одразу (три `onerror=`, гейт `!window.CommentLayerSupabase`, синхронний
    try/catch і `.catch()` на `store.ready`) — весь `tests.test_serve` лишився
    зеленим. Тест, зелений на повністю знятій обробці помилок, обіцяє більше,
    ніж дає, — той самий клас, що весь цей батч.

    Справжній сторож поведінки — два ЖИВІ тести в `tests/live/canvas.test.mjs`
    («мережевий збій CDN Supabase — банер зʼявляється одразу через onerror» і
    «CDN віддав 200 з порожнім тілом — try/catch ловить крах фабрики»): вони
    піднімають браузер на справжньому сніпеті й ріжуть CDN. Ці лишаються як
    дешева регресія, що біжить у кожному `npm test`.
    """

    def _code(self):
        """Готовий до віддачі сніпет, з якого прибрані `/* … */`.

        Шаблон формуємо, а не читаємо сирим: у браузер їде саме результат
        `.format()`, та й подвоєні дужки `{{`/`}}` шаблону інакше довелось би
        тягнути в кожне твердження. Коментарі прибираємо, щоб жодне твердження
        не могло випадково справдитись прозою.
        """
        body = serve.COMMENT_SNIPPET.format(
            project='dc/t1', assets='/vendor', version='it1',
            sb_url='https://x.supabase.co', sb_key='sb_publishable_X',
            # Тег інспектора підставляємо СПРАВЖНІЙ, а не порожній рядок: у
            # робочому каналі в браузер їде саме такий сніпет, і перевірки нижче
            # мусять бачити рівно його. Лічильник «три <script src>» він не
            # зачіпає — регулярка навмисно бере голий `<script src=`, а
            # інспектор іде як `<script type="module" src=`.
            inspector=serve.INSPECTOR_TAG.format(assets='/vendor', ds=''),
            # Аудиторії — теж СПРАВЖНІ, з тієї ж причини, що інспектор: у
            # робочому каналі в браузер їде саме такий `init`, і перевірки
            # нижче мусять бачити рівно його. Порожній рядок тут зробив би
            # цей клас сліпим до найдорожчої з можливих помилок — зайвого
            # `<script>` між банером і трьома тегами коментарів.
            audiences=serve.audiences_arg('project'))
        return re.sub(r'/\*.*?\*/', '', body, flags=re.S)

    def test_every_script_tag_reports_its_own_failure(self):
        """Кожен `<script src>` мусить мати ВЛАСНИЙ `onerror` у банер.

        Саме тег, а не сніпет «десь»: три теги — три різні причини (CDN
        Supabase, наш адаптер, сам шар), і мовчазний серед них дає рівно ту
        сторінку без пінів, від якої написаний банер.
        """
        tags = re.findall(r'<script src=[^>]*>', self._code())
        self.assertEqual(len(tags), 3,
                         f'очікуємо три теги <script src>, знайдено: {tags}')
        for tag in tags:
            self.assertRegex(tag, r'onerror="window\.__clDown\(',
                             f'тег без onerror мовчить при збої: {tag}')

    def test_init_reports_the_failures_the_tags_cannot_see(self):
        """Три запобіжники, повз які `onerror` тегів не бачить нічого.

        `onerror` спрацьовує лише на МЕРЕЖЕВОМУ збої. 200 з порожнім тілом,
        бібліотека, що завантажилась і не оголосила глобалів, база, яка не
        відповіла на вже піднятому адаптері — усе це успішні запити. Кожна з
        трьох гілок мусить закінчуватись банером, інакше сторінка знову мовчить.
        """
        code = self._code()
        # Глобалів немає, хоч усі три файли приїхали (200 з битим тілом).
        self.assertRegex(
            code, r'!window\.CommentLayerSupabase[\s\S]{0,120}?window\.__clDown\(',
            'гейт на глобали мусить вести в банер')
        # СИНХРОННИЙ крах фабрики: `window.supabase` немає, і виклик кидає ДО
        # того, як зʼявився `store.ready`, — промісом це не ловиться в принципі.
        self.assertRegex(
            code, r'try\s*\{\s*store = window\.CommentLayerSupabase\(',
            'виклик фабрики мусить стояти під синхронним try')
        self.assertRegex(
            code, r'\}\s*catch\s*\([^)]*\)\s*\{\s*window\.__clDown\(',
            'catch фабрики мусить вести в банер')
        # База не відповіла вже після вдалого підйому адаптера.
        self.assertRegex(
            code, r'\.catch\(function\s*\([^)]*\)\s*\{\s*window\.__clDown\(',
            '.catch() на store.ready мусить вести в банер')

    def test_down_banner_declared_before_the_cdn_script_tags(self):
        """Підрядковий тест ловить лише ТЕКСТ, а не поведінку — сторожем є живий
        тест у `tests/live/canvas.test.mjs` («CDN Supabase — банер...»). Цей
        лишається як дешева регресія на конкретний баг: банер `window.__clDown`
        мусить визначатись у ПЕРШОМУ тегу, ДО трьох `<script src>` — інакше
        `onerror` цих тегів спрацьовує РАНІШЕ, ніж `__clDown` взагалі існує
        (класичні скрипти виконуються послідовно), і охоронець `&&` мовчки
        гасить виклик на реальному збої CDN. Знайдено ревʼю 27.08.2026.
        """
        import serve
        banner_at = serve.COMMENT_SNIPPET.index('window.__clDown = function')
        first_src_at = serve.COMMENT_SNIPPET.index('<script src=')
        self.assertLess(banner_at, first_src_at,
                        'window.__clDown мусить визначатись ДО перших <script src>')


class InspectorPerAudience(unittest.TestCase):
    """Інспектор ДС їде в ОБА робочі канали — і в жоден зовнішній.

    Вимір 02.09.2026 у живому браузері: при `ch=project`
    `frame.contentWindow.CanvasInspector` === `undefined`, при `ch=local` —
    обʼєкт. Тег `inspector.js` жив лише в `LOCAL_COMMENT_SNIPPET`, а кнопка
    інспектора в смузі не зникала — `inspectorApi()` тихо віддавав `null`.

    ⛔ Прапорець, а не тег просто в шаблоні: `COMMENT_SNIPPET` має ДВОХ
    адресатів — `/commented?ch=project` (робоче місце дизайнера) і `_publish`
    (статика для колег). Тег «у шаблоні назавжди» поїхав би в publish, де
    (а) спека інспектора не хоче — це інструмент дизайнера, і кожен зайвий
    скрипт у статиці це байти й поверхня, (б) `inspector*.js` у
    `publish/comment-layer/` навіть не копіюються, тобто це був би 404 у
    справжньому превʼю. Тому канал вирішує ВИКЛИК, а не шаблон.

    Живий сторож поведінки — `tests/live/inspector-project.test.mjs`; тут
    стережеться те, чого браузером не видно дешево: сам факт межі publish.
    """

    HTML = '<html><body><h1>Мокап</h1></body></html>'
    TAG = '<script type="module" src="/app/vendor/inspector.js">'

    def _project(self, inspector):
        return serve.inject_comment_layer(
            self.HTML, 'dc/t1', '/app/vendor', version='1', inspector=inspector)

    def test_project_channel_carries_inspector(self):
        self.assertIn(self.TAG, self._project(True))

    def test_local_channel_did_not_lose_inspector(self):
        """Парна половина: та сама правка легко з'їла б локальний канал.

        Локальний сніпет ніс інспектор із самого початку, і саме на ньому
        знято 20+ живих перевірок оверлея. Тест без цієї половини зеленів би
        і на «переніс тег із локального в проєктний».
        """
        html = serve.inject_local_comment_layer(
            self.HTML, '/api/local-comments', 'dc/t1/local', '/app/vendor',
            version='1')
        self.assertIn(self.TAG, html)

    def test_external_preview_has_no_inspector(self):
        """Виклик БЕЗ прапорця — це рівно те, що робить `_publish`."""
        self.assertNotIn('inspector', self._project(False))

    def test_inspector_does_not_lie_about_comments(self):
        """Тег інспектора — без `onerror="window.__clDown(…)"`.

        Той банер каже «Коментарі недоступні». Інспектор до коментарів не має
        стосунку: його падіння збрехало б дизайнеру про справні коментарі, і
        він пішов би шукати проблему в Supabase.
        """
        tag = re.search(r'<script[^>]*inspector\.js[^>]*>',
                        self._project(True)).group(0)
        self.assertNotIn('onerror', tag)
        self.assertNotIn('__clDown', tag)

    def test_inspector_stands_after_the_comment_scripts(self):
        """Порядок у цьому сніпеті несучий, і тег інспектора його не рушить.

        Банер `window.__clDown` мусить лишитись у ПЕРШОМУ тегу, а три
        класичні `<script src>` коментарів — виконатись послідовно ДО
        ініціалізації (докстрінг `test_down_banner_declared_before_…`, той
        самий баг ловили живцем). `type="module"` відкладений за визначенням,
        тож стоячи ПІСЛЯ трьох тегів він нічого не затримує; стоячи ПЕРЕД
        банером — зламав би саме той порядок.
        """
        code = self._project(True)
        self.assertLess(code.index('window.__clDown = function'),
                        code.index('inspector.js'),
                        'банер мусить лишитись ПЕРШИМ тегом')
        self.assertGreater(code.index('inspector.js'),
                           code.rindex('<script src='),
                           'тег інспектора мусить стояти ПІСЛЯ трьох скриптів коментарів')


class NoDeadTemplates(unittest.TestCase):
    """Жоден шаблон сторінки в `serve.py` не лежить без споживача.

    Знайдено 03.09.2026: `SWITCHER_PAGE` — перша обгортка превʼю з
    найпершого коміта інструмента (`466b172`) — жила мертвою з версії 1.9.0,
    коли її замінив `PAGES_PREVIEW_PAGE`. Двадцять сім рядків HTML, які ніхто
    не кличе й ніхто не міняє: читач `serve.py` мусив щоразу зʼясовувати,
    котра з двох обгорток справжня.

    Межа перевірки записана свідомо: стережемо саме ВЕЛИКІ ШАБЛОНИ (імена на
    `_PAGE`/`_SNIPPET`/`_TMPL`/`_HTML`), а не всі константи модуля. Для
    звичайної константи «жодного споживача» буває законним станом (публічний
    інтерфейс, значення для тестів), а шаблон сторінки без споживача — це
    завжди або забуте прибирання, або забуте підключення. Обидва варті слова.
    """

    TEMPLATE_SUFFIXES = ('_PAGE', '_SNIPPET', '_TMPL', '_HTML')

    def test_every_page_template_has_a_consumer(self):
        with io.open(os.path.join(ROOT, 'app', 'serve.py'), encoding='utf-8') as fh:
            src = fh.read()
        names = re.findall(r'^([A-Z][A-Z0-9_]*) = ', src, re.M)
        templates = [n for n in names if n.endswith(self.TEMPLATE_SUFFIXES)]
        self.assertGreaterEqual(len(templates), 4,
                                f'шаблонів знайдено {len(templates)} — регексп не працює')
        dead = []
        for name in templates:
            # Згадки МІНУС саме оголошення: споживач — це будь-яке інше вживання
            # (`.format(...)`, підстановка в інший шаблон, аргумент функції).
            uses = len(re.findall(rf'\b{name}\b', src)) - 1
            if uses == 0:
                dead.append(name)
        self.assertEqual(dead, [],
                         'шаблон сторінки без жодного споживача — або забуте '
                         f'прибирання, або забуте підключення: {dead}')


class AudienceLabelsPinned(unittest.TestCase):
    """Підписи вкладок аудиторій існують у ДВОХ місцях, і це неминуче.

    `app/i18n.js` — словник інтерфейсу; `AUDIENCES_TMPL` у `serve.py` — сніпет,
    що їде в рамку. Python не імпортує JS-словник, тож рядки дублюються. Цей
    тест приколює копії одна до одної — той самий підхід, що вже тримає пару
    `comment_layer_src_hash` (JS-збірка проти `bin/doctor.py`).

    Розійдуться — і в англійському інтерфейсі знову зʼявиться «Клод»/«Команда»
    серед `Layout`/`Overview`, рівно як 02.09.2026 до цієї правки.
    """

    KEYS = ('audTabLocal', 'audTabTeam')

    def _dict_values(self):
        """`{('uk'|'en', ключ): значення}` з `app/i18n.js`, без запуску JS.

        Межа записана свідомо: беремо ПЕРШІ два входження кожного ключа в
        порядку файла (uk-словник іде першим, en — другим). Це тримається на
        тому, що словників у файлі рівно два — і тест це перевіряє нижче, а не
        припускає.
        """
        with io.open(os.path.join(ROOT, 'app', 'i18n.js'), encoding='utf-8') as fh:
            src = fh.read()
        out = {}
        for key in self.KEYS:
            found = re.findall(rf"^\s*{key}:\s*'([^']*)'", src, re.M)
            self.assertEqual(len(found), 2,
                             f'{key}: очікував по одному разу в кожному з двох '
                             f'словників, знайшов {len(found)}')
            out[('uk', key)], out[('en', key)] = found
        return out

    def test_audience_labels_match_dictionary(self):
        vals = self._dict_values()
        tmpl = serve.AUDIENCES_TMPL
        for lang, prefix in (('uk', 'uk'), ('en', 'en')):
            loc = vals[(lang, 'audTabLocal')]
            team = vals[(lang, 'audTabTeam')]
            self.assertIn(f"{prefix} = {{{{ local: '{loc}', team: '{team}' }}}}",
                          tmpl,
                          f'{lang}: підписи в AUDIENCES_TMPL розійшлись зі '
                          f'словником (у словнику «{loc}»/«{team}»)')

    def test_snippet_reads_language_from_client(self):
        """Мову бере КЛІЄНТ. Сервер її не знає — і не сміє вгадувати."""
        self.assertIn("localStorage.getItem('dc-lang')", serve.AUDIENCES_TMPL)
        # Падіння читання не сміє забрати вкладки: `uk` лишається за замовчуванням.
        self.assertIn('catch', serve.AUDIENCES_TMPL)


class AudienceTabsPerChannel(unittest.TestCase):
    """Вкладки аудиторій їдуть у ОБА робочі канали — і в жоден зовнішній.

    Перемикач аудиторії до 02.09.2026 жив у дропдауні ітерації смуги
    (`data-act="cmode"`), що суперечило принципу 6 PRODUCT.md: контролів
    коментатора у смузі інструмента бути не має. Новий дім — панель самого
    коментатора, і межу тримає КОНТРАКТ, а не знання коментатора про канали:
    `init({audiences, onAudience})`, немає `audiences` → рядка вкладок немає
    зовсім (сторож — `comment-layer/test/audiences.test.mjs`).

    ⛔ Прапорець на ВИКЛИКУ, як і в інспектора, з тієї ж причини:
    `COMMENT_SNIPPET` має двох адресатів — `/commented?ch=project` і
    `_publish`. Вкладки в publish дали б сторонньому глядачеві кнопку
    «Клод», за якою стоїть локальний файл на машині дизайнера: 404 у нього і
    запрошення слати робочий фідбек у нікуди. Це вимога конфіденційності
    зі спеки, не косметика.

    ⛔ `onAudience` НЕ навігує сам — він лише повідомляє хост
    (`postMessage`). Інакше стан каналу жив би у двох місцях: у
    `commentMode` оболонки й у рамці, — і позначка в смузі розійшлась би з
    тим, що показано. Приймач у `app.js` перевіряє і тип, і джерело
    (`ev.source === frame.contentWindow`).

    Живий сторож поведінки — `tests/live/comment-audience.test.mjs`; тут
    стережеться те, чого браузером не видно дешево: сам факт межі publish
    (він же — на артефакті в `test_5_publish_…`) і симетрія двох сніпетів.
    """

    HTML = '<html><body><h1>Мокап</h1></body></html>'

    def _project(self, audiences):
        return serve.inject_comment_layer(
            self.HTML, 'dc/t1', '/app/vendor', version='1', audiences=audiences)

    def _local(self, audiences=True):
        return serve.inject_local_comment_layer(
            self.HTML, '/api/local-comments', 'dc/t1/local', '/app/vendor',
            version='1', audiences=audiences)

    def test_both_working_channels_offer_both_tabs(self):
        """Дві вкладки в кожному робочому каналі — інакше з одного з них не вийти.

        Односторонній перелік («у проєктному лише «Команда»») зробив би канал
        пасткою: рівно так у Плані B зник вибір ітерації.
        """
        for name, code in (('project', self._project(True)), ('local', self._local())):
            self.assertIn("id: 'local'", code, f'{name}: немає вкладки Клода')
            self.assertIn("id: 'project'", code, f'{name}: немає вкладки команди')

    def test_active_tab_matches_the_channel_of_the_snippet(self):
        """Позначка активності — з САМОГО сніпета, не з клієнтського стану.

        Сніпет знає свій канал точно (його вибрав роут), а `commentMode` в
        `app.js` — лише те, що лежить у localStorage. Розійтись їм тут
        нізащо: підсвічена вкладка «Клод» на сторінці, яка пише в Supabase,
        це фідбек, відправлений не туди, кого дизайнер бачив.
        """
        # Підпис — ПОСИЛАННЯ (`L.local`/`L.team`), а не літерал: мову вибирає
        # клієнт (див. `AudienceLabelsPinned`). Перевіряти тут `'[^']+'` більше
        # нема чого, зате з'явилось, що перевіряти НАТОМІСТЬ: чи не переплутані
        # самі посилання. Вкладка «Команда» з підписом локального каналу — це
        # той самий клас помилки, від якого написаний цей тест, лише з іншого
        # боку: людина бачить одне ім'я, а пише в інший потік.
        proj = self._project(True)
        self.assertRegex(proj, r"id: 'project', label: L\.team, active: true")
        self.assertRegex(proj, r"id: 'local', label: L\.local, active: false")
        loc = self._local()
        self.assertRegex(loc, r"id: 'local', label: L\.local, active: true")
        self.assertRegex(loc, r"id: 'project', label: L\.team, active: false")

    def test_external_preview_gets_no_audiences_at_all(self):
        """Виклик БЕЗ прапорця — це рівно те, що робить `_publish`."""
        code = self._project(False)
        self.assertNotIn('audiences', code)
        self.assertNotIn('dc-audience', code)
        self.assertNotIn('onAudience', code)

    def test_switch_reports_to_the_host_and_navigates_nothing(self):
        """`onAudience` кладе `postMessage` у батька — і не рушить `location`.

        Навігація належить хосту: він тримає `commentMode`, пише його в
        localStorage і малює з нього смугу. Рамка, яка перезавантажує себе
        сама, лишила б хост із застарілим станом.
        """
        for name, code in (('project', self._project(True)), ('local', self._local())):
            body = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
            self.assertRegex(
                body, r"onAudience:[\s\S]{0,200}?window\.parent\.postMessage\(",
                f'{name}: onAudience мусить повідомити хост')
            self.assertRegex(body, r"type: 'dc-audience'",
                             f'{name}: повідомлення без свого типу приймач не візьме')
            hop = re.search(r'onAudience:[\s\S]{0,300}', body).group(0)
            for forbidden in ('location', 'reload', 'href'):
                self.assertNotIn(forbidden, hop,
                                 f'{name}: onAudience не сміє навігувати сам ({forbidden})')

    def test_audiences_do_not_disturb_the_load_order(self):
        """Порядок сніпета Supabase несучий (див. `CommentSnippetSelfReports`).

        `audiences` — аргумент ВСЕРЕДИНІ `init`, тобто жодного нового тега:
        банер `window.__clDown` лишається першим, три `<script src>` —
        трьома. Тест ловить саме це, бо найпростіша реалізація («ще один
        `<script>` із конфігом») зламала б послідовність, і банер знову
        перестав би зʼявлятись при мертвому CDN.
        """
        code = self._project(True)
        tags = re.findall(r'<script src=[^>]*>', code)
        self.assertEqual(len(tags), 3, f'очікуємо три теги <script src>: {tags}')
        self.assertLess(code.index('window.__clDown = function'),
                        code.index('<script src='))
        self.assertLess(code.index('CommentLayer.init'), code.index('audiences'),
                        'audiences мусить бути аргументом init, а не окремим тегом')


class PublishFlagsForeignPreview(unittest.TestCase):
    """`/api/publish` цілком (vercel підмінено): чужа задача → `not_task_link`,
    домен із суфіксом → `domain_warning`. Помічники стережуть юніти вище, а тут —
    що публікація їх справді кличе й віддає (рішення власника 29.09.2026)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-pubflags-')
        it1 = os.path.join(cls.tmp, 'iterations', 'it1')
        os.makedirs(it1)
        with open(os.path.join(it1, 'index.html'), 'w') as f:
            f.write('<html><body><h1>Мокап</h1></body></html>')
        with open(os.path.join(cls.tmp, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '29.09.2026 12:00',
                                       'note': 'ф', 'published': True}]}, f)
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-pubflags-cfg-')
        cls.env = {'DC_TASKS_FILE': os.path.join(cls.cfgdir, 'tasks.json'),
                   'DC_NO_OVERVIEW': '1', 'DC_IDENTITY_NAME': 'Я',
                   'DC_IDENTITY_EMAIL': 'me@x'}
        os.environ.update(cls.env)
        with open(cls.env['DC_TASKS_FILE'], 'w') as f:
            json.dump({'current': 'fixture', 'design_work_root': cls.cfgdir,
                       'tasks': {'fixture': {'dir': cls.tmp, 'title': 'Ф',
                                             'owner': 'Ольга', 'owner_key': 'owner@x',
                                             'vercel_project': 'pv-11111111'}}}, f)
        cls.httpd = serve.make_server(0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        for k in cls.env:
            os.environ.pop(k, None)
        for d in (cls.tmp, cls.cfgdir):
            shutil.rmtree(d, ignore_errors=True)

    def test_foreign_publish_carries_both_warnings(self):
        url = 'https://pv-11111111-abc123.vercel.app'

        class Done:
            returncode = 0
            stdout = f'Production: {url}'
            stderr = ''

        with mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
             mock.patch.object(serve.subprocess, 'run', lambda *a, **kw: Done()), \
             mock.patch.object(serve, '_stable_alias', lambda u, cwd, extra=(): url), \
             mock.patch.object(serve, '_check_published', lambda u: {'verified': True}), \
             mock.patch.object(serve, '_registry_push', lambda tid: False), \
             mock.patch.object(serve, '_remember_vercel_scope', lambda *a: None):
            body = json.load(post(self.base + '/api/publish', {}))
        self.assertEqual(body.get('url'), url, body)
        self.assertEqual(body.get('not_task_link'), 'Ольга')
        self.assertIn('pv-11111111.vercel.app', body.get('domain_warning') or '')


class ShotsEndpoints(unittest.TestCase):
    """Віддача знімків: тільки .webp з теки ітерації, тільки поточної задачі."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-shots-')
        it1 = os.path.join(cls.tmp, 'iterations', 'it1')
        os.makedirs(os.path.join(it1, 'shots'))
        with open(os.path.join(it1, 'index.html'), 'w') as f:
            f.write('<html><body><h1>Мокап</h1></body></html>')
        with open(os.path.join(it1, 'shots', 'main.webp'), 'wb') as f:
            f.write(b'RIFF____WEBPVP8 fake shot bytes')
        # Кадр СТАНУ екрана: ключ це `сторінка~хеш` (див. shotKey у flow-model.js)
        with open(os.path.join(it1, 'shots', 'main~30d36f19.webp'), 'wb') as f:
            f.write(b'RIFF____WEBPVP8 fake state shot')
        with open(os.path.join(it1, 'shots', 'manifest.json'), 'w') as f:
            json.dump({'contract': 'x', 'checkedAt': '24.08.2026 12:00',
                       'shots': {'main': {'w': 1280, 'h': 1400, 'stale': False}}}, f)
        # Геометрія кадру (T-45) — поруч із .webp під тим самим ключем.
        with open(os.path.join(it1, 'shots', 'main.geo.json'), 'w') as f:
            json.dump({'v': 1, 'els': [{'tag': 'h1', 'path': ['h1[0]'], 'x': 0, 'y': 0, 'w': 9, 'h': 9}]}, f)
        # Приманка ПОЗА текою кадрів з тим самим суфіксом: без неї перевірка
        # обходу зеленіла б і без замків (цілі просто не існує — 404 і так).
        with open(os.path.join(it1, 'secret.geo.json'), 'w') as f:
            f.write('{"secret": true}')
        with open(os.path.join(cls.tmp, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '24.08.2026 12:00',
                                       'note': 'ф', 'published': True}]}, f)
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-shots-cfg-')
        os.environ['DC_TASKS_FILE'] = os.path.join(cls.cfgdir, 'tasks.json')
        os.environ['DC_NO_OVERVIEW'] = '1'
        with open(os.environ['DC_TASKS_FILE'], 'w') as f:
            json.dump({'current': 'fixture', 'design_work_root': cls.cfgdir,
                       'tasks': {'fixture': {'dir': cls.tmp, 'title': 'Ф'}}}, f)
        cls.httpd = serve.make_server(0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        for d in (cls.tmp, cls.cfgdir):
            shutil.rmtree(d, ignore_errors=True)

    def test_shot_served_as_webp(self):
        r = urllib.request.urlopen(f'{self.base}/shot?it=it1&node=main')
        self.assertEqual(r.headers['Content-Type'], 'image/webp')
        self.assertIn(b'WEBP', r.read())

    def test_shot_is_cacheable_forever(self):
        """Кадр незмінний під своїм ключем: ключ несе і штамп джерел, і час зйомки.

        no-store тут коштував перекачування ВСІХ кадрів на кожну перебудову
        канваса — а перебудову робить будь-який чекбокс у смузі.

        `get_all`, а НЕ `r.headers['Cache-Control']`: за дублікатів заголовка
        `Message.__getitem__` тихо віддає лише ПЕРШИЙ і не бачить другого —
        рівно тому ця перевірка лишалась би зеленою і на живому багу
        `Handler.end_headers`, який дописував СВІЙ `Cache-Control: no-cache`
        поверх immutable з `_shot` (два заголовки, а не один — браузер читає
        їх як один через кому, і хвостовий no-cache гасив кеш геть). Справжній
        HTTP-клієнт (fetch у браузері) саме так їх і зʼєднує — це і зловив
        живий тест K1 у tests/live/canvas.test.mjs.
        """
        r = urllib.request.urlopen(self.base + '/shot?it=it1&node=main')
        self.assertEqual(r.status, 200)
        cc_all = r.headers.get_all('Cache-Control')
        self.assertEqual(len(cc_all), 1, f'дублікат заголовка Cache-Control: {cc_all}')
        cc = cc_all[0]
        self.assertIn('immutable', cc)
        self.assertIn('max-age=', cc)
        self.assertNotIn('no-store', cc)

    def test_missing_shot_is_404_not_empty_200(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f'{self.base}/shot?it=it1&node=nemaje')
        self.assertEqual(e.exception.code, 404)

    def test_path_traversal_refused(self):
        for node in ('../../../etc/passwd', '..%2F..%2Fserve', 'a/b'):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(f'{self.base}/shot?it=it1&node={node}')
            self.assertIn(e.exception.code, (400, 404))

    # ---------- T-45: геометрія кадру і канал коментарів для «Огляду» ----------

    def test_geo_served_as_json(self):
        r = urllib.request.urlopen(f'{self.base}/shot-geo?it=it1&node=main&v=abc')
        self.assertIn('application/json', r.headers['Content-Type'])
        self.assertEqual(json.load(r)['els'][0]['tag'], 'h1')
        # як кадр: під ключем версії — вічний кеш, і заголовок ОДИН
        self.assertEqual(r.headers.get_all('Cache-Control'), ['public, max-age=31536000, immutable'])

    def test_geo_without_version_is_not_cached_forever(self):
        # Без `v` ключ кешу нічого не каже про вміст — вічний кеш тут віддавав
        # би стару геометрію після перезйомки.
        r = urllib.request.urlopen(f'{self.base}/shot-geo?it=it1&node=main')
        self.assertEqual(r.headers.get_all('Cache-Control'), ['no-store'])

    def test_geo_missing_is_404(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f'{self.base}/shot-geo?it=it1&node=main~30d36f19')
        self.assertEqual(e.exception.code, 404)

    def test_geo_refuses_traversal(self):
        for node in ('../../../etc/passwd', '..%2F..%2Fserve', 'a/b'):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(f'{self.base}/shot-geo?it=it1&node={node}')
            self.assertIn(e.exception.code, (400, 404))

    def test_geo_traversal_to_existing_file_refused(self):
        # Ціль ІСНУЄ (`it1/secret.geo.json`, сусід теки `shots`). Мутаційно:
        # зняти ОБИДВА замки (SHOT_RE і realpath) — червоніє; кожен поодинці
        # прикритий другим, рівно як у `_shot`.
        for node in ('../secret', '..%2Fsecret'):
            try:
                body = urllib.request.urlopen(f'{self.base}/shot-geo?it=it1&node={node}').read()
            except urllib.error.HTTPError as e:
                self.assertIn(e.code, (400, 404))
                continue
            self.fail(f'віддано файл поза текою кадрів: {body!r}')

    def test_geo_is_not_the_shot(self):
        # `/shot-geo` не сміє перехопитись маршрутом `/shot` (і навпаки):
        # звірка точна, не префіксна.
        r = urllib.request.urlopen(f'{self.base}/shot?it=it1&node=main')
        self.assertEqual(r.headers['Content-Type'], 'image/webp')

    def test_comment_config_local(self):
        os.environ['DC_IDENTITY_NAME'] = 'Тест Дизайнер'
        try:
            body = json.load(urllib.request.urlopen(f'{self.base}/api/comment-config?ch=local&it=it1'))
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
        self.assertEqual(body, {'ch': 'local', 'project': 'fixture/local', 'version': '1',
                                'endpoint': '/api/local-comments',
                                'user': {'name': 'Тест Дизайнер'}})

    def test_comment_config_without_identity_has_no_user(self):
        # немає особи — немає поля; коментатор тоді питає імʼя сам (під охороною)
        os.environ['DC_IDENTITY_NAME'] = ''
        os.environ['DC_IDENTITY_EMAIL'] = ''
        try:
            body = json.load(urllib.request.urlopen(f'{self.base}/api/comment-config?ch=local&it=it1'))
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None); os.environ.pop('DC_IDENTITY_EMAIL', None)
        self.assertNotIn('user', body)

    def test_identity_does_not_leak_into_frame_snippet(self):
        # ⛔ сніпет рамки їде і в публікацію: ПІБ туди не йде
        os.environ['DC_IDENTITY_NAME'] = 'Тест Дизайнер'
        try:
            html = urllib.request.urlopen(f'{self.base}/commented?it=it1&ch=local').read().decode('utf-8')
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
        self.assertNotIn('Тест Дизайнер', html)

    def test_comment_config_project(self):
        body = json.load(urllib.request.urlopen(f'{self.base}/api/comment-config?ch=project&it=it1'))
        self.assertEqual(body['ch'], 'project')
        # той самий канал, що `_commented` дає рамці (`comment_channel`)
        self.assertEqual(body['project'], 'dc/fixture')
        self.assertEqual(body['version'], '1')
        self.assertEqual(body['sbUrl'], serve.SUPABASE_URL)
        self.assertEqual(body['sbKey'], serve.SUPABASE_KEY)

    def test_comment_config_refuses_unknown_channel(self):
        for q in ('ch=evil&it=it1', 'ch=local&it=../x'):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(f'{self.base}/api/comment-config?{q}')
            self.assertEqual(e.exception.code, 400)

    def test_manifest_endpoint(self):
        body = json.load(urllib.request.urlopen(f'{self.base}/api/shots?it=it1'))
        self.assertEqual(body['shots']['main']['w'], 1280)
        self.assertEqual(body['it'], 'it1')

    def test_manifest_missing_is_empty_not_error(self):
        body = json.load(urllib.request.urlopen(f'{self.base}/api/shots?it=it9'))
        self.assertEqual(body['shots'], {})

    def test_referer_cannot_hijack_shot_route(self):
        # Файл-приманка з іменем маршруту в корені ітерації
        with open(os.path.join(self.tmp, 'iterations', 'it1', 'shot'), 'w') as f:
            f.write('це не кадр')
        req = urllib.request.Request(
            f'{self.base}/shot?it=it1&node=main',
            headers={'Referer': f'{self.base}/it-assets/it1/index.html'})
        r = urllib.request.urlopen(req)
        self.assertEqual(r.headers['Content-Type'], 'image/webp')
        # bytes-літерал з кирилицею тут теж SyntaxError (той самий клас, що й
        # у fixture-байтах кадру) — кодуємо рядок у runtime замість літерала.
        self.assertNotIn('це не кадр'.encode('utf-8'), r.read())

    def test_state_shot_key_with_tilde_is_served(self):
        """Ключ кадру стану — `сторінка~хеш`. NAME_RE тильву НЕ пускає, тому кадр
        лежав би на диску, а полотно отримувало б 400 і малювало «немає знімка» —
        тиха неправда рівно на шві модуля й сервера. Знайдено ревʼю якості, коли
        викликачів ще не було."""
        r = urllib.request.urlopen(f'{self.base}/shot?it=it1&node=main~30d36f19')
        self.assertEqual(r.headers['Content-Type'], 'image/webp')
        self.assertIn(b'WEBP', r.read())

    def test_shot_key_still_refuses_traversal_and_junk(self):
        """Дозвіл на тильду не сміє відкрити ані слеш, ані `..`, ані довільний хвіст."""
        for node in ('../main', 'a/b', 'main~30d36f19~ff', 'main~ZZZZZZZZ', 'main~ff'):
            with self.subTest(node=node):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(f'{self.base}/shot?it=it1&node={node}')
                self.assertEqual(e.exception.code, 400, f'{node} мусить бути відхилений')

    def test_shot_route_accepts_viewport_keys(self):
        """Ключ кадру може нести ширину суфіксом (`frameKey` у app/viewport.js).

        404, а не 400, — це і є доказ: валідацію ключ пройшов, далі просто немає
        такого файла. Без цього кадри мобільної ширини лежали б на диску, а
        полотно отримувало б 400 і малювало «немає знімка».
        """
        for node in ('holovna@768', 'poshuk~48d0ed7a@390'):
            with self.subTest(node=node):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(f'{self.base}/shot?it=it1&node={node}')
                self.assertEqual(
                    e.exception.code, 404,
                    'ключ мусить пройти валідацію (404 = дійшли до пошуку файла)')

    def test_shot_route_still_rejects_garbage(self):
        """400 = не пройшов SHOT_RE. Ширина в ключі це ЦИФРИ (2–4), тому шлях
        крізь неї не пролізе; realpath-замок у `_shot` лишається другим рубежем."""
        for node in ('holovna@', 'holovna@abc', '../etc@768', 'holovna@99999', 'a@1'):
            with self.subTest(node=node):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(f'{self.base}/shot?it=it1&node={node}')
                self.assertEqual(e.exception.code, 400, node)

    def test_symlink_out_of_task_refused(self):
        outside = os.path.join(self.cfgdir, 'secret.txt')
        with open(outside, 'w') as f:
            f.write('чуже')
        link = os.path.join(self.tmp, 'iterations', 'it1', 'shots', 'evil.webp')
        os.symlink(outside, link)
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f'{self.base}/shot?it=it1&node=evil')
        self.assertEqual(e.exception.code, 404)

    def test_manifest_that_is_not_an_object(self):
        it2 = os.path.join(self.tmp, 'iterations', 'it2', 'shots')
        os.makedirs(it2, exist_ok=True)
        with open(os.path.join(it2, 'manifest.json'), 'w') as f:
            f.write('[1, 2, 3]')
        body = json.load(urllib.request.urlopen(f'{self.base}/api/shots?it=it2'))
        self.assertEqual(body['shots'], {})

    def test_shoot_spawns_node_and_returns_report(self):
        # node не запускаємо по-справжньому: тут перевіряється склейка аргументів
        # і те, що звіт дитини доходить до канваса неспотвореним.
        # Popen, а не run: реалізація перейшла на групу процесів, тож підставний
        # child мусить видавати той самий інтерфейс — pid/poll/wait і ОКРЕМІ труби.
        # Не communicate(): stderr тепер читає фоновий потік порядково (події
        # прогресу), і другий читач тієї ж труби забрав би в нього рядки.
        calls = {}

        class FakeChild:
            returncode = 0
            pid = 12345

            def __init__(self, args, **kw):
                calls['args'] = args
                calls['kw'] = kw
                self.stdout = io.StringIO('{"shot":["main"],"failed":[],"left":[]}')
                self.stderr = io.StringIO('')

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

        with mock.patch.object(serve.subprocess, 'Popen', FakeChild), \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'):
            body = json.load(post(self.base + '/api/shoot', {'it': 'it1', 'all': True}))
        self.assertTrue(body['ok'])
        self.assertEqual(body['report']['shot'], ['main'])
        self.assertIn('--all', calls['args'])
        self.assertIn('--json', calls['args'])
        self.assertIn('shoot.mjs', ' '.join(calls['args']))
        # дитина мусить стукати назад у ЦЕЙ сервер, інакше знімає чужу задачу
        self.assertIn(f'127.0.0.1:{self.httpd.server_address[1]}', ' '.join(calls['args']))
        # своя група процесів — інакше вбити онука (Chromium) на таймауті нічим
        self.assertTrue(calls['kw'].get('start_new_session'))

    def test_shoot_bad_iteration_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            post(self.base + '/api/shoot', {'it': '../etc'})
        self.assertEqual(e.exception.code, 400)

    def test_shoot_passes_viewport_to_child(self):
        """`vp` мусить доїхати до shoot.mjs АРГУМЕНТОМ.

        Без цього сервер знімав би завжди типову ширину, а канвас чекав би
        мобільні кадри — і симптом був би найгіршого сорту: кадри є, вони
        свіжі, вони просто не тієї ширини, і жодна перевірка про це не скаже.
        """
        # Той самий прийом, що вже стоїть у test_guard_blocks_registry_push:
        # мок замість дитини. `side_effect` рве запуск одразу після того, як argv
        # уже зібрано, — доказ у `call_args`, а браузер не піднімається.
        with mock.patch.object(serve.subprocess, 'Popen') as popen, \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'):
            popen.side_effect = OSError('досить, argv уже зібрано')
            post(self.base + '/api/shoot', {'it': 'it1', 'vp': 390})
        argv = popen.call_args[0][0]
        self.assertIn('--vp', argv)
        self.assertEqual(argv[argv.index('--vp') + 1], '390')

    def test_shoot_rejects_bad_viewport_instead_of_silently_defaulting(self):
        """Невалідна ширина — 400, а не тихий дефолт: підміна дала б кадри
        однієї ширини під ключами іншої, тобто мовчазну неправду в манифесті.

        Popen під моком навмисне: перевірка мусить бути зеленою через ВІДМОВУ,
        а не через те, що дитина десь там впала.
        """
        for vp in ('abc', 0, 99999, -390):
            with self.subTest(vp=vp):
                with mock.patch.object(serve.subprocess, 'Popen') as popen, \
                     mock.patch.object(serve, '_node_bin',
                                       lambda name='npx': '/usr/bin/node'):
                    popen.side_effect = OSError('зʼємки бути не мало')
                    with self.assertRaises(urllib.error.HTTPError) as e:
                        post(self.base + '/api/shoot', {'it': 'it1', 'vp': vp})
                self.assertEqual(e.exception.code, 400, repr(vp))
                self.assertFalse(popen.called,
                                 f'на {vp!r} зʼємка не сміє навіть стартувати')

    def test_shoot_without_node_says_so_instead_of_crashing(self):
        with mock.patch.object(serve, '_node_bin', lambda name='npx': None):
            body = json.load(post(self.base + '/api/shoot', {'it': 'it1'}))
        self.assertFalse(body['ok'])
        self.assertIn('node', body['error'])

    def test_shoot_keeps_child_output_when_it_is_not_json(self):
        class Broken:
            returncode = 1
            pid = 12346

            def __init__(self, *a, **kw):
                self.stdout = io.StringIO('Traceback: усе впало')
                # Причина падіння приходить рядками stderr — і саме її мусить
                # донести хвіст, не витіснений подіями прогресу.
                self.stderr = io.StringIO('playwright не знайдено\n')

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

        with mock.patch.object(serve.subprocess, 'Popen', Broken), \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'):
            body = json.load(post(self.base + '/api/shoot', {'it': 'it1'}))
        self.assertFalse(body['ok'])
        self.assertIn('усе впало', body['report']['raw'])
        self.assertIn('playwright', body['stderr'])

    def test_shoot_timeout_kills_the_whole_group(self):
        # Дитина спавнить власного онука й зависає — так само, як node тримає Chromium.
        # Онук пише свій pid у ФАЙЛ, а не в stdout: на таймауті `_shoot` не віддає
        # клієнту ні stdout, ні stderr дитини (лише {'ok': False, 'error': ...}),
        # тож stdout тут для тесту недоступний — тільки файл дає незалежний доказ.
        script = os.path.join(self.cfgdir, 'hang.py')
        pid_file = os.path.join(self.cfgdir, 'grandchild.pid')
        with open(script, 'w') as f:
            f.write('import subprocess, time\n'
                    'g = subprocess.Popen(["sleep", "30"])\n'
                    f'open({pid_file!r}, "w").write(str(g.pid))\n'
                    'time.sleep(30)\n')
        real = serve.subprocess.Popen
        seen = {}

        def fake_popen(args, **kw):
            # підміняємо лише КОМАНДУ, решту (start_new_session) лишаємо як є
            seen['kw'] = kw
            return real([sys.executable, script], **kw)

        with mock.patch.object(serve.subprocess, 'Popen', fake_popen), \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
             mock.patch.object(serve, 'SHOOT_TIMEOUT_S', 2):
            body = json.load(post(self.base + '/api/shoot', {'it': 'it1'}))
        self.assertFalse(body['ok'])
        self.assertIn('не вклалася', body['error'])
        # Головне: група мусила бути своя, інакше вбити онука нічим
        self.assertTrue(seen['kw'].get('start_new_session'))

        # Сильніша перевірка: онук (sleep 30) СПРАВДІ мертвий, а не лише «своя
        # група» на папері. Невеликий поллінг із межею — щоб не бути крихким до
        # таймінгів ОС між SIGTERM/SIGKILL і фактичним прибиранням процесу.
        with open(pid_file) as f:
            grandchild_pid = int(f.read().strip())
        deadline = time.monotonic() + 5
        dead = False
        while time.monotonic() < deadline:
            try:
                os.kill(grandchild_pid, 0)
            except ProcessLookupError:
                dead = True
                break
            time.sleep(0.1)
        self.assertTrue(dead, f'онук (pid {grandchild_pid}) досі живий після вбивства групи')

    # ---------- прогрес зʼємки (події stderr + два маршрути) ----------

    def test_shoot_progress_without_shoot_is_not_running(self):
        """Немає зʼємки — `running: false`, а НЕ 404. Канвас опитує прогрес
        регулярно, і 404 у консолі виглядав би поломкою інструмента."""
        body = json.load(urllib.request.urlopen(
            f'{self.base}/api/shoot-progress?it=it1'))
        self.assertEqual(body['running'], False)

    def test_shoot_progress_rejects_bad_iteration(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f'{self.base}/api/shoot-progress?it=../etc')
        self.assertEqual(e.exception.code, 400)

    def test_shoot_stop_without_shoot_answers_honestly(self):
        """Зупиняти нічого — це не помилка й не «зупинив». Канвас натискає
        «Зупинити» наосліп, і тут мусить бути чесне `stopped: false`."""
        body = json.load(post(self.base + '/api/shoot-stop', {'it': 'it1'}))
        self.assertEqual(body, {'ok': True, 'stopped': False})

    def test_second_shoot_joins_the_live_one_instead_of_doubling_it(self):
        """Автостарт робить паралельну спробу звичайною справою (дві вкладки,
        плюс Stop-хук автосинку). Друга мусить ПРИЄДНАТИСЬ до наявної, а не
        підняти другий Chromium на ту саму ітерацію."""
        class Live:
            pid = 4242

            def poll(self):
                return None

        progress = serve.ShootProgress()
        progress.apply({'ev': 'start', 'total': 8})
        serve._SHOOTS[('fixture', 'it1')] = {'proc': Live(), 'progress': progress}
        self.addCleanup(serve._SHOOTS.pop, ('fixture', 'it1'), None)
        started = []

        def no_second_child(*a, **kw):
            started.append(a)
            raise AssertionError('другу зʼємку тієї ж ітерації запускати не можна')

        with mock.patch.object(serve.subprocess, 'Popen', no_second_child), \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'):
            body = json.load(post(self.base + '/api/shoot', {'it': 'it1'}))
        self.assertEqual(started, [], 'дитину все-таки запустили')
        self.assertTrue(body['already'])
        self.assertEqual(body['progress']['total'], 8)

    def test_shoot_stop_kills_the_group_not_just_the_child(self):
        """Chromium — ОНУК процесу node, тому «Зупинити» мусить бити по ГРУПІ:
        сигнал прямій дитині лишив би headless-браузер жити безстроково."""
        class Live:
            pid = 4242

            def poll(self):
                return None

        progress = serve.ShootProgress()
        entry = {'proc': Live(), 'progress': progress, 'hard': None}
        serve._SHOOTS[('fixture', 'it1')] = entry
        self.addCleanup(serve._SHOOTS.pop, ('fixture', 'it1'), None)
        # Зупинка озброює SIGKILL через HARD_KILL_S — у тесті дитина підставна, і
        # живий таймер полетів би в pid 4242 чужого процесу. Гасимо за собою.
        self.addCleanup(lambda: entry.get('hard') and entry['hard'].cancel())
        killed = []
        with mock.patch.object(serve.os, 'killpg',
                               lambda pid, sig: killed.append((pid, sig))):
            body = json.load(post(self.base + '/api/shoot-stop', {'it': 'it1'}))
        self.assertEqual(body, {'ok': True, 'stopped': True})
        self.assertEqual(killed, [(4242, serve.signal.SIGTERM)])
        self.assertTrue(progress.stopped, 'стан мусить памʼятати, що зупинив дизайнер')

    def test_freshness_check_does_not_join_a_live_shoot(self):
        """`freshen()` у канвасі ходить ЦИМ САМИМ маршрутом, але з `check: true`.

        Поки ключ замка не знав про `--check`, перевірка свіжості під час живої
        зʼємки діставала `{ok: true, already: true}` БЕЗ `report` — і канвас
        записував `stale: []`, тобто «нічого не застаріло» як правду. Друга
        вкладка бачила «Перезняти» без числа при 22 застарілих.
        """
        class Live:
            pid = 4242

            def poll(self):
                return None

        live_entry = {'proc': Live(), 'progress': serve.ShootProgress(),
                      'hard': None}
        serve._SHOOTS[('fixture', 'it1')] = live_entry
        self.addCleanup(serve._SHOOTS.pop, ('fixture', 'it1'), None)
        calls = {}

        class CheckChild:
            returncode = 0
            pid = 777

            def __init__(self, args, **kw):
                calls['args'] = args
                self.stdout = io.StringIO(
                    '{"nodes":22,"stale":["a","b"],"problems":[]}')
                self.stderr = io.StringIO('')

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

        with mock.patch.object(serve.subprocess, 'Popen', CheckChild), \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'):
            body = json.load(post(self.base + '/api/shoot',
                                  {'it': 'it1', 'check': True}))
        self.assertNotIn('already', body, 'перевірка свіжості приєдналась до зʼємки')
        self.assertEqual(body['report']['stale'], ['a', 'b'])
        self.assertIn('--check', calls['args'])
        # І реєстр лишився ЧУЖИЙ: перевірка ані займає ключ, ані виносить живу
        # зʼємку з реєстру своїм прибиранням.
        self.assertIs(serve._SHOOTS.get(('fixture', 'it1')), live_entry)
        self.assertIsInstance(live_entry['proc'], Live)

    def test_racing_shoots_inside_popen_spawn_only_one_child(self):
        """Перевірка «чи є жива» і запис у реєстр мусять бути ОДНИМ входженням
        у замок. Поки між ними лежав Popen, два запити, що розійшлися в межах
        fork+exec, обидва проходили перевірку й піднімали по Chromium на ту саму
        теку. Тут перший запит навмисне спить УСЕРЕДИНІ Popen."""
        entered = threading.Event()
        release = threading.Event()
        spawned = []

        class SlowChild:
            returncode = 0
            pid = 9001

            def __init__(self, args, **kw):
                spawned.append(args)
                entered.set()
                release.wait(5)
                self.stdout = io.StringIO('{"shot":[],"failed":[],"left":[]}')
                self.stderr = io.StringIO('')

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                return self.returncode

        self.addCleanup(serve._SHOOTS.pop, ('fixture', 'it1'), None)
        self.addCleanup(release.set)
        out = {}

        def first():
            try:
                out['body'] = json.load(post(self.base + '/api/shoot', {'it': 'it1'}))
            except Exception as e:            # noqa: BLE001 — доказ у out
                out['error'] = repr(e)

        with mock.patch.object(serve.subprocess, 'Popen', SlowChild), \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'):
            worker = threading.Thread(target=first, daemon=True)
            worker.start()
            self.assertTrue(entered.wait(10), 'перша зʼємка не дійшла до Popen')
            second = json.load(post(self.base + '/api/shoot', {'it': 'it1'}))
            release.set()
            worker.join(15)
        self.assertTrue(second.get('already'),
                        'друга зʼємка не приєдналась, а пішла своїм Popen')
        self.assertEqual(len(spawned), 1,
                         f'на ту саму теку піднято дитин: {len(spawned)}')
        self.assertEqual(out.get('error'), None)
        self.assertTrue(out['body']['ok'])
        # ключ звільнено, інакше наступна зʼємка цієї ітерації неможлива
        self.assertNotIn(('fixture', 'it1'), serve._SHOOTS)

    def test_manual_stop_escalates_to_sigkill(self):
        """Спека: SIGTERM, а через 15 с — SIGKILL. Таймер ескалації існував, але
        стартував ВИКЛЮЧНО зі сторожа на 15 хвилин, тобто ручної зупинки не
        стосувався. Виміряний наслідок: node лишається живим і добігає цикл,
        `child.stdout.read()` тримає потік обробника, запис висить у реєстрі — і
        нову зʼємку в цій вкладці не запустити."""
        class Live:
            pid = 4242

            def poll(self):
                return None

        entry = {'proc': Live(), 'progress': serve.ShootProgress(), 'hard': None}
        serve._SHOOTS[('fixture', 'it1')] = entry
        self.addCleanup(serve._SHOOTS.pop, ('fixture', 'it1'), None)
        self.addCleanup(lambda: entry.get('hard') and entry['hard'].cancel())
        killed = []
        with mock.patch.object(serve.os, 'killpg',
                               lambda pid, sig: killed.append((pid, sig))), \
             mock.patch.object(serve, 'HARD_KILL_S', 0.2):
            body = json.load(post(self.base + '/api/shoot-stop', {'it': 'it1'}))
            self.assertEqual(body, {'ok': True, 'stopped': True})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and len(killed) < 2:
                time.sleep(0.05)
        self.assertEqual(killed, [(4242, serve.signal.SIGTERM),
                                  (4242, serve.signal.SIGKILL)],
                         'ручна зупинка лишилась без ескалації')

    def test_registry_survives_a_thread_that_refuses_to_start(self):
        """Запис у реєстр стояв ДО `try:`, а між ними — `reader.start()`. Виняток
        (класика: `RuntimeError: can't start new thread`) летів повз `finally`:
        запис лишався в реєстрі НАЗАВЖДИ з `running: true`, `progress.finish()`
        не кликався, Chromium працював без нагляду."""
        real_thread = serve.threading.Thread

        class NoPump(real_thread):
            """Падає РІВНО читач stderr: потоки самого серверу мусять жити."""

            def start(self):
                name = getattr(self._target, '__qualname__', '')
                if name.endswith('_shoot.<locals>.pump'):
                    raise RuntimeError("can't start new thread")
                return super().start()

        class FakeChild:
            returncode = 0
            pid = 5150

            def __init__(self, args, **kw):
                self.stdout = io.StringIO('{}')
                self.stderr = io.StringIO('')

            def poll(self):
                return None

            def wait(self, timeout=None):
                return self.returncode

        self.addCleanup(serve._SHOOTS.pop, ('fixture', 'it1'), None)
        killed = []
        with mock.patch.object(serve.subprocess, 'Popen', FakeChild), \
             mock.patch.object(serve, '_node_bin', lambda name='npx': '/usr/bin/node'), \
             mock.patch.object(serve.os, 'killpg',
                               lambda pid, sig: killed.append((pid, sig))), \
             mock.patch.object(serve.threading, 'Thread', NoPump):
            with self.assertRaises(Exception):
                post(self.base + '/api/shoot', {'it': 'it1'})
        self.assertNotIn(('fixture', 'it1'), serve._SHOOTS,
                         'запис лишився в реєстрі назавжди')
        # і дитина не лишилась без нагляду з Chromium-онуком
        self.assertEqual(killed, [(5150, serve.signal.SIGTERM)])


class StderrReader(unittest.TestCase):
    """Рядки з маркером не сміють витіснити справжню причину падіння."""

    def test_marked_lines_do_not_pollute_stderr_tail(self):
        from serve import _consume_stderr_line
        from shoot_progress import MARK, ShootProgress
        progress, tail = ShootProgress(), []
        _consume_stderr_line(MARK + '{"ev":"start","total":8}', progress, tail)
        _consume_stderr_line('Error: chromium is not installed', progress, tail)
        _consume_stderr_line(MARK + '{"ev":"frame","i":1,"key":"a"}', progress, tail)
        self.assertEqual(tail, ['Error: chromium is not installed'])
        self.assertEqual(progress.snapshot()['done'], 1)


class PagesFromIterationsSkipsLock(unittest.TestCase):
    """`_pages_from_iterations` переносить вміст старих ітерацій сирим listdir, без
    предиката `_is_tool_junk`, тож службове мусить відсіяти явно. `.pages.lock`
    лежить у кожній теці, куди хтось писав дерево, і в теці нової сторінки він
    був би порожнім сміттям, що їде колегам."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-pfi-')
        for it in ('it1', 'it2'):
            d = os.path.join(cls.tmp, 'iterations', it)
            os.makedirs(d)
            with open(os.path.join(d, 'index.html'), 'w') as f:
                f.write(f'<html><body><h1>{it}</h1></body></html>')
            open(os.path.join(d, '.pages.lock'), 'w').close()
        with open(os.path.join(cls.tmp, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [
                {'id': it, 'date': '25.08.2026 10:00', 'note': it, 'published': False}
                for it in ('it1', 'it2')]}, f)
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-pfi-cfg-')
        os.environ['DC_TASKS_FILE'] = os.path.join(cls.cfgdir, 'tasks.json')
        os.environ['DC_NO_OVERVIEW'] = '1'
        with open(os.environ['DC_TASKS_FILE'], 'w') as f:
            json.dump({'current': 'fixture', 'design_work_root': cls.cfgdir,
                       'tasks': {'fixture': {'dir': cls.tmp, 'title': 'Ф'}}}, f)
        cls.httpd = serve.make_server(0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        for d in (cls.tmp, cls.cfgdir):
            shutil.rmtree(d, ignore_errors=True)

    def test_the_lock_file_is_not_carried_into_the_new_pages(self):
        body = json.load(post(self.base + '/api/pages-from-iterations', {'itIds': ['it1', 'it2']}))
        self.assertTrue(body['ok'], body)
        new = os.path.join(self.tmp, 'iterations', body['iteration'])
        carried = []
        for root, _, names in os.walk(new):
            carried += [os.path.join(root, n) for n in names if n == '.pages.lock']
        self.assertEqual(carried, [], 'службовий лок-файл поїхав у нові сторінки')
        page_dirs = [d for d in os.listdir(new) if os.path.isdir(os.path.join(new, d))]
        self.assertEqual(len(page_dirs), 2)
        for d in page_dirs:     # сам вміст поїхав — інакше тест нічого б не доводив
            self.assertTrue(os.path.isfile(os.path.join(new, d, 'index.html')))


class FlowEndpoints(unittest.TestCase):
    """Граф юзер-флоу ітерації: читання й запис `<ітерація>/flow.json`."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-flow-')
        cls.it1 = os.path.join(cls.tmp, 'iterations', 'it1')
        os.makedirs(cls.it1)
        with open(os.path.join(cls.it1, 'index.html'), 'w') as f:
            f.write('<html><body><h1>Мокап</h1></body></html>')
        with open(os.path.join(cls.tmp, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '25.08.2026 10:00',
                                       'note': 'ф', 'published': False}]}, f)
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-flow-cfg-')
        os.environ['DC_TASKS_FILE'] = os.path.join(cls.cfgdir, 'tasks.json')
        os.environ['DC_NO_OVERVIEW'] = '1'
        with open(os.environ['DC_TASKS_FILE'], 'w') as f:
            json.dump({'current': 'fixture', 'design_work_root': cls.cfgdir,
                       'tasks': {'fixture': {'dir': cls.tmp, 'title': 'Ф'}}}, f)
        cls.httpd = serve.make_server(0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        for d in (cls.tmp, cls.cfgdir):
            shutil.rmtree(d, ignore_errors=True)

    def setUp(self):
        # Сервер один на клас, а flow.json — СПІЛЬНИЙ файл на диску. Без цього
        # прибирання `test_broken_json_is_loud` (за абеткою йде першим) лишав би
        # побитий файл, і `test_no_file_is_not_an_error` перевіряв би вже не
        # відсутність файла, а биття — зеленів би з неправильної причини.
        for name in os.listdir(self.it1):
            if name.startswith('flow.json'):
                os.remove(os.path.join(self.it1, name))

    def test_no_file_is_not_an_error(self):
        """Флоу ще не описували — це порожньо, а не 404."""
        r = urllib.request.urlopen(f'{self.base}/api/flow?it=it1')
        self.assertEqual(r.status, 200)
        body = json.load(r)
        self.assertIsNone(body['flow'])
        # Саме ВІДСУТНІСТЬ файла, а не биття: без цього рядка тест зеленів би й на
        # чужому побитому flow.json, що лишився від сусіднього тесту.
        self.assertNotIn('error', body)

    def test_reads_what_lies_in_the_iteration(self):
        flow = {'flows': [{'id': 'f', 'nodes': [], 'edges': []}]}
        with open(os.path.join(self.it1, 'flow.json'), 'w', encoding='utf-8') as f:
            json.dump(flow, f)
        body = json.load(urllib.request.urlopen(f'{self.base}/api/flow?it=it1'))
        self.assertEqual(body['flow'], flow)

    def test_broken_json_is_loud(self):
        """Побитий файл мусить сказати про себе, а не прикинутись порожнім."""
        with open(os.path.join(self.it1, 'flow.json'), 'w', encoding='utf-8') as f:
            f.write('{ це не json')
        body = json.load(urllib.request.urlopen(f'{self.base}/api/flow?it=it1'))
        self.assertIsNone(body['flow'])
        self.assertIn('flow.json не читається', body['error'])

    def test_save_writes_and_reads_back(self):
        flow = {'flows': [{'id': 'f', 'nodes': [{'id': 'n', 'page': 'holovna',
                                                 'pos': {'col': 2, 'row': 0}}],
                           'edges': []}]}
        self.assertTrue(json.load(post(f'{self.base}/api/flow-save',
                                       {'it': 'it1', 'flow': flow}))['ok'])
        body = json.load(urllib.request.urlopen(f'{self.base}/api/flow?it=it1'))
        self.assertEqual(body['flow'], flow)

    def test_save_refuses_anything_that_is_not_an_object(self):
        for bad in ([], 'рядок', 42, None):
            with self.subTest(flow=bad):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    post(f'{self.base}/api/flow-save', {'it': 'it1', 'flow': bad})
                self.assertEqual(e.exception.code, 400,
                                 f'{bad!r} мусить бути відхилено')
        # Відхилений запис не сміє лишити по собі ані файла, ані пів-файла .tmp:
        # інакше «не зберегло» виглядало б у теці як «зберегло щось».
        for name in ('flow.json', 'flow.json.tmp'):
            self.assertFalse(os.path.exists(os.path.join(self.it1, name)), name)

    def test_iteration_name_is_checked(self):
        """NAME_RE — єдиний замок від виходу за межі теки задачі."""
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f'{self.base}/api/flow?it=../../etc')
        self.assertEqual(e.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as e:
            post(f'{self.base}/api/flow-save', {'it': '../x', 'flow': {}})
        self.assertEqual(e.exception.code, 400)

    def test_route_cannot_be_hijacked_by_referer(self):
        """У make_server ДРУГИЙ роутер: усе поза HANDLED_PREFIXES — статика.

        Одної перевірки константи мало: вона лишалася б зеленою й тоді, коли
        маршрут насправді перехоплений. Тому ще й приманка на диску — файл
        `api/flow` у корені ітерації, як у test_referer_cannot_hijack_shot_route.
        """
        self.assertTrue(any(p == '/api/' for p in serve.HANDLED_PREFIXES))
        decoy = os.path.join(self.it1, 'api')
        os.makedirs(decoy, exist_ok=True)
        with open(os.path.join(decoy, 'flow'), 'w', encoding='utf-8') as f:
            f.write('це не граф')
        req = urllib.request.Request(
            f'{self.base}/api/flow?it=it1',
            headers={'Referer': f'{self.base}/it-assets/it1/index.html'})
        r = urllib.request.urlopen(req)
        self.assertEqual(r.headers['Content-Type'], 'application/json')
        self.assertIsNone(json.load(r)['flow'])

    def test_directory_instead_of_file_is_reported(self):
        """`flow.json`, що виявився текою, — це IsADirectoryError. Урок сусіда
        (_shots_manifest): тиша належить лише «файла нема», решта мусить бути
        гучною. Але гучність тут — причина у відповіді, а не обрив зʼєднання."""
        d = os.path.join(self.it1, 'flow.json')
        os.makedirs(d, exist_ok=True)
        try:
            body = json.load(urllib.request.urlopen(f'{self.base}/api/flow?it=it1'))
            self.assertIsNone(body['flow'])
            self.assertIn('flow.json', body['error'])
            # І запис туди ж: os.replace у теку падає ВЖЕ ПІСЛЯ того, як тимчасовий
            # файл створено, — єдина гілка, де є що прибирати. Без неї прибирання
            # tmp лишалось би непокритим (жодна інша невдача до mkstemp не доходить).
            saved = json.load(post(f'{self.base}/api/flow-save',
                                   {'it': 'it1', 'flow': {'flows': []}}))
            self.assertFalse(saved['ok'])
            self.assertIn('не вдалося зберегти', saved['error'])
            junk = [n for n in os.listdir(self.it1)
                    if n.startswith('flow.json') and n != 'flow.json']
            self.assertEqual(junk, [], f'невдалий запис лишив сміття: {junk}')
        finally:
            os.rmdir(d)

    def test_valid_json_that_is_not_an_object_is_not_a_graph(self):
        """Асиметрія читання й запису: запис вимагає обʼєкт, читання віддавало що
        завгодно, і список їхав у канвас під виглядом графа. Той самий урок, через
        який у _shots_manifest зʼявився isinstance(data, dict)."""
        with open(os.path.join(self.it1, 'flow.json'), 'w', encoding='utf-8') as f:
            f.write('[1, 2, 3]')
        body = json.load(urllib.request.urlopen(f'{self.base}/api/flow?it=it1'))
        self.assertIsNone(body['flow'])
        self.assertIn('flow.json', body['error'])

    def test_save_into_a_deleted_iteration_answers(self):
        """Теку ітерації прибрали в сусідній вкладці. Клієнт мусить почути
        «не зберіг, і ось чому», а не побачити обірване зʼєднання."""
        body = json.load(post(f'{self.base}/api/flow-save',
                              {'it': 'itZ', 'flow': {'flows': []}}))
        self.assertFalse(body['ok'])
        self.assertIn('не вдалося зберегти', body['error'])

    def test_save_without_write_permission_answers(self):
        """Те саме для прав: PermissionError теж мусить стати відповіддю."""
        if os.geteuid() == 0:
            self.skipTest('root пише куди завгодно — перевірка прав безпредметна')
        ro = os.path.join(self.tmp, 'iterations', 'itro')
        os.makedirs(ro, exist_ok=True)
        os.chmod(ro, 0o500)
        try:
            body = json.load(post(f'{self.base}/api/flow-save',
                                  {'it': 'itro', 'flow': {'flows': []}}))
            self.assertFalse(body['ok'])
            self.assertIn('не вдалося зберегти', body['error'])
        finally:
            os.chmod(ro, 0o700)

    def test_two_tabs_saving_at_once_do_not_mix_graphs(self):
        """Дві вкладки тиснуть «зберегти» одночасно (сервер — ThreadingHTTPServer).
        Виграти може будь-яка, але на диску мусить лежати ЦІЛИЙ граф однієї з них.

        Спільне імʼя `flow.json.tmp` зводило атомарність нанівець: обидва потоки
        відкривали ОДИН шлях на 'w', обрізали одне одного, і os.replace атомарно
        клав на місце вже зіпсоване. Графи великі саме для того, щоб вікно запису
        було ширшим за планувальник і гонка відтворювалась, а не «як пощастить».
        """
        def big(tag):
            return {'flows': [{'id': tag, 'edges': [], 'nodes': [
                {'id': f'{tag}-{i}', 'page': tag * 12, 'pos': {'col': i, 'row': i}}
                for i in range(4000)]}]}

        a, b = big('a'), big('b')
        flow_json = os.path.join(self.it1, 'flow.json')
        for round_ in range(5):
            with self.subTest(round=round_):
                threads = [threading.Thread(
                    target=lambda g: post(f'{self.base}/api/flow-save',
                                          {'it': 'it1', 'flow': g}).read(),
                    args=(g,)) for g in (a, b)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(30)
                with open(flow_json, encoding='utf-8') as f:
                    raw = f.read()
                try:
                    on_disk = json.loads(raw)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    self.fail(f'flow.json побитий після одночасного запису: {e}')
                self.assertTrue(on_disk == a or on_disk == b,
                                'на диску опинилась суміш двох графів')
        # Невдалий чи перерваний запис не сміє лишати по собі тимчасових файлів.
        junk = [n for n in os.listdir(self.it1)
                if n.startswith('flow.json') and n != 'flow.json']
        self.assertEqual(junk, [], f'лишилось сміття: {junk}')

class AtomicWrites(unittest.TestCase):
    """Файл стану або старий валідний, або новий валідний — ніколи обрізаний."""

    def test_failed_write_leaves_previous_content_intact(self):
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "state.json")
            serve.atomic_write_json(p, {"v": 1})
            # Несеріалізовний обʼєкт валить json.dump посеред запису — рівно те,
            # що робить краш процесу. Старий вміст мусить лишитись цілим.
            with self.assertRaises(TypeError):
                serve.atomic_write_json(p, {"bad": object()})
            with open(p, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), {"v": 1})

    def test_no_tmp_garbage_left_behind(self):
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "state.json")
            serve.atomic_write_json(p, {"v": 1})
            with self.assertRaises(TypeError):
                serve.atomic_write_json(p, {"bad": object()})
            self.assertEqual([f for f in os.listdir(tmp) if f != "state.json"], [],
                             "невдалий запис лишив по собі сміття")

    def test_reader_holding_the_old_handle_never_sees_a_torn_file(self):
        """Стереже саме ПІДМІНУ, а не двофазність.

        Решта тестів класу спрацьовує від TypeError у json.dump, тобто ДО
        підміни: заміна os.replace на обрізальний copyfile лишала їх зеленими,
        хоч тема задачі — «обрізаний файл більше неможливий». Відкритий
        дескриптор бачить стару інодину доти, доки її не переписали НА МІСЦІ.
        """
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "state.json")
            serve.atomic_write_json(p, {"v": 1})
            with open(p, encoding="utf-8") as fh:      # читач відкрив СТАРУ версію
                serve.atomic_write_json(p, {"v": 2})
                self.assertEqual(json.load(fh), {"v": 1},
                                 "підміна не атомарна: ціль переписали на місці")

    def test_interrupt_mid_write_leaves_no_garbage(self):
        """Ctrl-C посеред json.dump — це і є «убитий прогін».

        Саме тому except ловить BaseException: KeyboardInterrupt і SystemExit
        не успадковують Exception, тож із вужчим except кожне переривання
        лишало б по файлу — тим гірше, що імʼя в кожного власне.
        """
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "state.json")
            serve.atomic_write_json(p, {"v": 1})
            with mock.patch("json.dump", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    serve.atomic_write_json(p, {"v": 2})
            self.assertEqual([f for f in os.listdir(tmp) if f != "state.json"], [],
                             "переривання лишило по собі сміття")

    def test_tmp_is_created_in_the_target_directory(self):
        """Інваріант «ТА САМА тека» докстрінг підкреслює найгучніше, а стерегти
        його було нікому: через межу файлової системи rename перестає бути
        атомарним і деградує до копіювання."""
        import serve
        seen = {}
        real_mkstemp = tempfile.mkstemp

        def spy(*a, **kw):
            seen["dir"] = kw.get("dir")
            return real_mkstemp(*a, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "task")
            os.makedirs(sub)
            target = os.path.join(sub, "state.json")
            with mock.patch("tempfile.mkstemp", spy):
                serve.atomic_write_json(target, {"v": 1})
            # Порівнюємо з РОЗІМЕНОВАНОЮ текою: писар свідомо йде через realpath
            # (див. симлінк-тест), а на macOS /var сам є лінком на /private/var.
            # Значення має не рядок шляху, а те, що tmp і ціль — на одному томі.
            self.assertEqual(seen["dir"], os.path.dirname(os.path.realpath(target)),
                             "tmp пішов не в теку цілі")
            self.assertEqual(os.stat(seen["dir"]).st_dev,
                             os.stat(os.path.realpath(target)).st_dev,
                             "tmp і ціль на різних томах — rename перестане бути атомарним")

    def test_symlinked_target_stays_a_symlink(self):
        """Старий open(path, 'w') писав НАСКРІЗЬ крізь симлінк.

        os.replace бʼє по самому лінку й мовчки перетворив би його на звичайний
        файл: конфіг, який користувач навмисно виніс кудись і залінкував, тихо
        відʼєднався б від справжнього місця.
        """
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.join(tmp, "real.json")
            link = os.path.join(tmp, "tasks.json")
            with open(real, "w", encoding="utf-8") as fh:
                json.dump({"v": 0}, fh)
            os.symlink(real, link)
            serve.atomic_write_json(link, {"v": 1})
            self.assertTrue(os.path.islink(link), "симлінк став звичайним файлом")
            with open(real, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), {"v": 1}, "запис не пройшов крізь лінк")

    def test_node_writers_use_the_same_tmp_suffix(self):
        """Суфікс живе у двох мовах: константа Python і два літерали в .mjs.

        Розійдуться — осиротілий tmp тихо повернеться у штамп зʼємки і в
        спільне репо, і жоден ОДНОМОВНИЙ тест цього не побачить.
        """
        import atomic_io
        suf = atomic_io.TMP_SUFFIX
        with open(os.path.join(ROOT, "bin", "shots-manifest.mjs"), encoding="utf-8") as fh:
            manifest = fh.read()
        with open(os.path.join(ROOT, "bin", "shots-stamp.mjs"), encoding="utf-8") as fh:
            stamp = fh.read()
        self.assertIn("${++writeSeq}" + suf + "`", manifest,
                      "писар манифеста взяв інший суфікс, ніж відсіює Python")
        self.assertIn(f'endsWith("{suf}")', stamp,
                      "штамп зʼємки фільтрує інший суфікс, ніж відсіює Python")

    def test_write_pages_failure_leaves_previous_tree_intact(self):
        """`pages_model.write_pages` має свою копію патерну — стереже її окремо.

        Хелпер `serve.atomic_write_json` тут не діє: залежність спрямована
        serve → pages_model, тож зворотний імпорт замкнув би цикл, і код у
        pages_model дублюється свідомо. Дубль без власного сторожа — це рівно та
        копія, з якої тихо приберуть os.replace.
        """
        import pages_model as pm
        with tempfile.TemporaryDirectory() as tmp:
            pm.write_pages(tmp, [{"id": "a", "name": "A", "published": True}])
            # `validate` пропускає зайві ключі, тож обʼєкт долітає до json.dump і
            # валить його ПОСЕРЕД запису — те саме, що краш процесу.
            with self.assertRaises(TypeError):
                pm.write_pages(tmp, [{"id": "b", "name": "B", "x": object()}])
            # `kind` дописує materialize при кожному записі (A2)
            self.assertEqual(pm.read_pages(tmp),
                             [{"id": "a", "name": "A", "published": True, "kind": "page"}])
            junk = [f for f in os.listdir(tmp) if f.startswith("pages.json")
                    and f not in ("pages.json", "pages.json.bak")]
            self.assertEqual(junk, [], f"невдалий запис лишив по собі сміття: {junk}")


class WriterLock(unittest.TestCase):
    """`_WRITE_LOCK` серіалізує ТІЛА писарів стану.

    Наслідок, який видно ззовні: `.bak` лишається рівно ОДИН крок назад. Без
    лока два потоки знімають копію з однієї й тієї ж версії, обидва пишуть — і
    `.bak` відстає вже на два кроки, тобто відновлення з нього тихо викидає
    чужу правку.
    """

    def test_bak_is_the_version_immediately_before_current(self):
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "tasks.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump({"v": 0}, fh)
            # Тиск на критичну секцію: писар, який зайшов у copy2, чекає на
            # напарника. Зустрілись усередині — лока немає. З локом другий до
            # бар'єра не дійде, перший відпустить його по таймауту.
            started, gate = threading.Barrier(2), threading.Barrier(2)
            real_copy2 = shutil.copy2

            def slow_copy2(src, dst, *a, **kw):
                real_copy2(src, dst, *a, **kw)
                try:
                    gate.wait(timeout=1.0)
                except threading.BrokenBarrierError:
                    pass

            def writer(n):
                started.wait(timeout=10)
                serve.save_tasks({"v": n})

            with mock.patch.dict(os.environ, {"DC_TASKS_FILE": p}), \
                    mock.patch("shutil.copy2", slow_copy2):
                ts = [threading.Thread(target=writer, args=(n,)) for n in (1, 2)]
                for t in ts:
                    t.start()
                for t in ts:
                    t.join(20)
                self.assertFalse([t for t in ts if t.is_alive()], "писар завис")
            with open(p + ".bak", encoding="utf-8") as fh:
                bak = json.load(fh)
            with open(p, encoding="utf-8") as fh:
                cur = json.load(fh)
            self.assertNotEqual(bak, {"v": 0},
                                ".bak відстав на два кроки: писарі зайшли в copy2 одночасно")
            self.assertNotEqual(bak, cur, ".bak дублює поточний стан — крок назад загублено")


class MockupTmpJunk(unittest.TestCase):
    """Осиротілий tmp — не частина макета: ні у відбитку, ні в тому, що їде колегам.

    Регресія від унікального імені tmp (28.08.2026). Поки писарі брали СПІЛЬНЕ
    `manifest.json.tmp`, убитий прогін лишав рівно один файл, і наступний прогін
    його перезаписував. З унікальним іменем кожен убитий прогін лишає НОВИЙ
    файл — і кожен зсуває mockup_hash та їде в спільне репо.
    """

    def _mockup(self):
        d = tempfile.mkdtemp(prefix='dc-junk-')
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        with open(os.path.join(d, 'index.html'), 'w') as f:
            f.write('<h1>макет</h1>')
        os.makedirs(os.path.join(d, 'shots'))
        with open(os.path.join(d, 'shots', 'manifest.json'), 'w') as f:
            f.write('{}')
        return d

    @staticmethod
    def _strew_tmp(d):
        """tmp обох писарів: у корені (pages.json) і в підтеці (манифест знімків)."""
        open(os.path.join(d, 'pages.json.ab12cd.tmp'), 'w').close()
        open(os.path.join(d, 'shots', 'manifest.json.4242.1.tmp'), 'w').close()

    def test_orphan_tmp_does_not_move_the_fingerprint(self):
        import serve
        d = self._mockup()
        base = serve.mockup_hash(d)
        self._strew_tmp(d)
        self.assertEqual(serve.mockup_hash(d), base,
                         'недописаний tmp зсунув відбиток — канвас покаже «є що синхронізувати» на порожньому місці')

    def test_orphan_tmp_is_not_exported_to_colleagues(self):
        """`copy_mockup` — це РЕАЛЬНИЙ експорт у дзеркало GitLab (gitlab_sync:486).

        Полагодити самий лише mockup_hash було б гірше, ніж не чіпати нічого:
        файл усе одно поїхав би колегам, але вже нечутно для відбитка.
        """
        import serve
        d = self._mockup()
        self._strew_tmp(d)
        dst = tempfile.mkdtemp(prefix='dc-export-')
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        serve.copy_mockup(d, dst)
        got = sorted(os.path.relpath(os.path.join(r, n), dst)
                     for r, _, ns in os.walk(dst) for n in ns)
        self.assertEqual(got, ['index.html', os.path.join('shots', 'manifest.json')],
                         'недописаний tmp поїхав у спільне репо')

    def test_orphan_tmp_directory_is_skipped_by_both(self):
        """Тека з іменем *.tmp теж геть — і однаково в обох.

        ⚠️ Тека ВКЛАДЕНА (`shared/stale.tmp`), і це принципово: у корені її й
        так відсіює `_is_tool_junk`, тож перша редакція цього тесту була зелена
        навіть без фільтра `dirnames` — мутація його не вбивала. Дірка саме в
        обході: `ignore_patterns` матчить і теки, а `os.walk` без окремого рядка
        заходив би всередину, і відбиток бачив би файли, яких експорт не возить.
        """
        import serve
        d = self._mockup()
        nested = os.path.join(d, 'shared', 'stale.tmp')
        os.makedirs(nested)
        open(os.path.join(nested, 'chunk'), 'w').close()
        open(os.path.join(d, 'shared', 'real.css'), 'w').close()
        got = sorted(os.path.relpath(f, d) for f in serve._mockup_files(d))
        self.assertNotIn(os.path.join('shared', 'stale.tmp', 'chunk'), got,
                         'відбиток заліз у вкладену теку *.tmp')
        self.assertIn(os.path.join('shared', 'real.css'), got,
                      'разом із теками *.tmp зникло й потрібне')
        dst = tempfile.mkdtemp(prefix='dc-export-')
        self.addCleanup(shutil.rmtree, dst, ignore_errors=True)
        serve.copy_mockup(d, dst)
        self.assertFalse(os.path.exists(os.path.join(dst, 'shared', 'stale.tmp')),
                         'вкладена тека *.tmp поїхала колегам')
        self.assertTrue(os.path.exists(os.path.join(dst, 'shared', 'real.css')))

    def test_real_mockup_files_in_subfolders_still_travel(self):
        """Фільтр звужений РІВНО до .tmp: усе інше з підтек їде як їхало."""
        import serve
        d = self._mockup()
        os.makedirs(os.path.join(d, 'shared'))
        for n in ('app.js', 'notes.py', 'data.bak'):
            open(os.path.join(d, 'shared', n), 'w').close()
        got = sorted(os.path.relpath(f, d) for f in serve._mockup_files(d))
        self.assertEqual(got, ['index.html',
                               os.path.join('shared', 'app.js'),
                               os.path.join('shared', 'data.bak'),
                               os.path.join('shared', 'notes.py'),
                               os.path.join('shots', 'manifest.json')])


class StateFileMode(unittest.TestCase):
    """Оновлення інструмента не сміє мовчки міняти права на файлах користувача.

    `mkstemp` створює 0600, і `os.replace` переносить цей режим на ціль —
    затираючи режим старого файла. Старий `open(path, 'w')` режим наявного
    файла зберігав.
    """

    @staticmethod
    def _mode(p):
        return stat.S_IMODE(os.stat(p).st_mode)

    def test_existing_file_keeps_its_mode(self):
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'tasks.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'v': 0}, f)
            os.chmod(p, 0o644)
            serve.atomic_write_json(p, {'v': 1})
            self.assertEqual(self._mode(p), 0o644,
                             'запис звузив права наявного файла стану')

    def test_unusual_mode_is_preserved_too(self):
        """Саме РЕЖИМ ФАЙЛА, а не зашита константа 0644."""
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'tasks.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'v': 0}, f)
            os.chmod(p, 0o640)
            serve.atomic_write_json(p, {'v': 1})
            self.assertEqual(self._mode(p), 0o640)

    def test_brand_new_file_stays_owner_only(self):
        """Файла не було — лишаємо 0600 від mkstemp і не розширюємо права самі."""
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, 'tasks.json')
            serve.atomic_write_json(p, {'v': 1})
            self.assertEqual(self._mode(p), 0o600)

    def test_write_pages_keeps_its_mode_too(self):
        import pages_model as pm
        with tempfile.TemporaryDirectory() as tmp:
            pm.write_pages(tmp, [{'id': 'a', 'name': 'A', 'published': True}])
            p = pm.pages_path(tmp)
            os.chmod(p, 0o644)
            pm.write_pages(tmp, [{'id': 'b', 'name': 'B', 'published': True}])
            self.assertEqual(self._mode(p), 0o644)


class GitignoreSeed(unittest.TestCase):
    """`git_autocommit` робить `git add -A`, тож усе, чого немає в .gitignore,
    лягає в історію теки задачі — а за наявності remote і пушиться."""

    def test_seeded_gitignore_covers_orphan_tmp(self):
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, 'index.html'), 'w').close()
            serve.git_autocommit(tmp, 'тест')
            with open(os.path.join(tmp, '.gitignore'), encoding='utf-8') as fh:
                lines = fh.read().split()
            self.assertIn('*.tmp', lines, 'осиротілий tmp поїде в історію задачі')
            self.assertIn('*.bak', lines, 'старе правило зникло разом із новим')

    def test_orphan_tmp_does_not_land_in_the_commit(self):
        """Правило в файлі — ще не доказ. Перевіряємо тим, чим міряє сам git."""
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, 'index.html'), 'w').close()
            open(os.path.join(tmp, 'pages.json.ab12cd.tmp'), 'w').close()
            serve.git_autocommit(tmp, 'тест')
            tracked = subprocess.run(['git', 'ls-files'], cwd=tmp,
                                     capture_output=True, text=True).stdout.split()
            self.assertIn('index.html', tracked)
            self.assertNotIn('pages.json.ab12cd.tmp', tracked)

    # ── робоче листування з Клодом не їде колегам (18.09.2026) ────────────
    #
    # `.dc-tuner.json` (пакет рекомендацій тюнера, з вільним текстом у `note`)
    # і `.dc-local-comments.json` (локальні пін-коментарі) лежать у КОРЕНІ теки
    # задачі — рівно там, куди дивиться `git add -A`. Рішення власника: не
    # пушити ні те, ні те. Перевіряємо тим, чим міряє сам git, а не наявністю
    # рядка у файлі: правило можна написати й помилитись у ньому.

    WORK_FILES = ('.dc-tuner.json', '.dc-local-comments.json')

    def test_working_files_do_not_land_in_the_commit(self):
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, 'index.html'), 'w').close()
            for n in self.WORK_FILES:
                with open(os.path.join(tmp, n), 'w', encoding='utf-8') as fh:
                    fh.write('{"note": "тільки для Клода"}')
            serve.git_autocommit(tmp, 'тест')
            tracked = subprocess.run(['git', 'ls-files'], cwd=tmp,
                                     capture_output=True, text=True).stdout.split()
            self.assertIn('index.html', tracked,
                          'свідок: макет у комміт таки потрапляє')
            for n in self.WORK_FILES:
                self.assertNotIn(n, tracked, f'{n} поїхав би колегам')

    def test_existing_task_dir_gets_the_rule_too(self):
        """Головне в цій правці. Раніше `.gitignore` сіявся ЛИШЕ при `git init`,
        тож у вже заведеної задачі (а такі всі) нове правило не зʼявилось би
        ніколи. Відтворюємо саме це: репо з .gitignore СТАРОГО зразка."""
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q'], cwd=tmp, check=True)
            with open(os.path.join(tmp, '.gitignore'), 'w', encoding='utf-8') as fh:
                fh.write('publish/\n*.bak\n*.tmp\n.DS_Store\n'
                         'comments-for-ai*\n.vercel/\n')
            open(os.path.join(tmp, '.dc-tuner.json'), 'w').close()
            open(os.path.join(tmp, 'index.html'), 'w').close()
            serve.git_autocommit(tmp, 'тест')
            tracked = subprocess.run(['git', 'ls-files'], cwd=tmp,
                                     capture_output=True, text=True).stdout.split()
            self.assertIn('index.html', tracked)
            self.assertNotIn('.dc-tuner.json', tracked)

    def test_top_up_keeps_foreign_lines_and_does_not_duplicate(self):
        """Дописуємо лише СВОЄ і лише те, чого немає: `.gitignore` теки задачі
        належить і дизайнеру теж (`refs/`, чернетки), а другий однаковий рядок
        від кожного автокоміту перетворив би файл на журнал."""
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, '.gitignore'), 'w', encoding='utf-8') as fh:
                fh.write('refs/\n*.bak\n')          # без кінцевого рядка нижче
            first = serve.ensure_task_gitignore(tmp)
            second = serve.ensure_task_gitignore(tmp)
            with open(os.path.join(tmp, '.gitignore'), encoding='utf-8') as fh:
                lines = fh.read().split()
            self.assertIn('refs/', lines, 'чуже правило не сміє зникнути')
            self.assertEqual(second, [], 'другий прохід не дописує нічого')
            self.assertIn('.dc-tuner.json', first)
            for p in serve.TASK_IGNORE:
                self.assertEqual(lines.count(p), 1, f'{p} продубльовано')

    def test_missing_trailing_newline_does_not_glue_rules(self):
        """Файл без кінцевого переносу рядка: без цієї гілки перше дописане
        правило склеїлось би з останнім наявним в одне слово — і обидва
        перестали б діяти, мовчки."""
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, '.gitignore'), 'w', encoding='utf-8') as fh:
                fh.write('refs/')                     # НЕ закінчується \n
            serve.ensure_task_gitignore(tmp)
            with open(os.path.join(tmp, '.gitignore'), encoding='utf-8') as fh:
                lines = fh.read().splitlines()
            self.assertIn('refs/', lines)
            self.assertIn('publish/', lines)

    def test_already_tracked_file_is_NOT_saved_by_the_rule(self):
        """МЕЖА, записана тестом, а не сподіванням. `.gitignore` не знімає з
        обліку те, що вже відстежується: у теках, куди
        `.dc-local-comments.json` уже потрапив (сім задач на 18.09.2026), він
        комітиться далі. Вивести його може тільки `git rm --cached` — рішення
        власника, не тиха правка інструмента. Тест стоїть тут, щоб ніхто не
        прочитав правило вище як «і старі теки вилікувано»."""
        import serve
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q'], cwd=tmp, check=True)
            p = os.path.join(tmp, '.dc-local-comments.json')
            open(p, 'w').close()
            subprocess.run(['git', 'add', '-f', '.dc-local-comments.json'],
                           cwd=tmp, check=True)
            serve.git_autocommit(tmp, 'тест')
            tracked = subprocess.run(['git', 'ls-files'], cwd=tmp,
                                     capture_output=True, text=True).stdout.split()
            self.assertIn('.dc-local-comments.json', tracked,
                          'якщо це впало — git змінив поведінку, і запис про '
                          'межу в serve.py треба переписати, а не радіти')


class PagesWriterLock(unittest.TestCase):
    """`write_pages` — двокрокова пара (копія в .bak + запис), і вона кличеться
    з обробників HTTP у потоках. Без спільного лока два одночасні /api/page-add
    зняли б .bak з ОДНІЄЇ версії — рівно той дефект, який для iterations.json
    закритий. Лок мусить бути ТОЙ САМИЙ, що в serve: окремий одне одного не
    бачив би."""

    def test_bak_is_the_version_immediately_before_current(self):
        import pages_model as pm
        with tempfile.TemporaryDirectory() as tmp:
            pm.write_pages(tmp, [{'id': 'v0', 'name': 'v0', 'published': True}])
            started, gate = threading.Barrier(2), threading.Barrier(2)
            real_copy2 = shutil.copy2

            def slow_copy2(src, dst, *a, **kw):
                real_copy2(src, dst, *a, **kw)
                try:
                    gate.wait(timeout=1.0)   # з локом другий сюди не дійде
                except threading.BrokenBarrierError:
                    pass

            def writer(n):
                started.wait(timeout=10)
                pm.write_pages(tmp, [{'id': f'v{n}', 'name': f'v{n}', 'published': True}])

            with mock.patch('shutil.copy2', slow_copy2):
                ts = [threading.Thread(target=writer, args=(n,)) for n in (1, 2)]
                for t in ts:
                    t.start()
                for t in ts:
                    t.join(20)
                self.assertFalse([t for t in ts if t.is_alive()], 'писар завис')
            with open(pm.pages_path(tmp) + '.bak', encoding='utf-8') as fh:
                bak = json.load(fh)['pages'][0]['id']
            with open(pm.pages_path(tmp), encoding='utf-8') as fh:
                cur = json.load(fh)['pages'][0]['id']
            self.assertNotEqual(bak, 'v0',
                                '.bak відстав на два кроки: писарі зайшли в copy2 одночасно')
            self.assertNotEqual(bak, cur, '.bak дублює поточний стан — крок назад загублено')

    def test_pages_writer_shares_the_lock_with_serve(self):
        """Один обʼєкт, не два однакові. Два незалежні локи пройшли б тест вище
        кожен окремо і все одно не серіалізували б writer-ів між собою."""
        import pages_model as pm
        import serve
        self.assertIs(pm.WRITE_LOCK, serve.WRITE_LOCK)



class ShellModulesList(unittest.TestCase):
    """`SHELL_MODULES` — перелік того, що публікація везе в `publish/shell/`.

    Охоронець тут НЕ дублює перелік, і це принципово. Дубль може лише
    переказати константу своїми словами: він ловить «зі SHELL_MODULES прибрали
    рядок», але не ловить того класу помилки, який справді трапляється — у
    `app/` зʼявився новий модуль, від якого оболонка вже залежить, а в перелік
    його не дописали. Тому перевірок дві, і жодна не зайва:

    • **замкнутість по імпортах** — усе, що імпортує будь-який модуль зі списку,
      теж у списку. Ловить забутий ЛИСТ (`shell-panel.js` тягне `icons.js` та
      `i18n.js`) і ловить його НАПЕРЕД, для модулів, яких сьогодні ще немає.
    • **підлога зі спеки** — модулі, названі в спеці спільними, у списку є.
      Замкнутість сама цього не дає: викинути корінь (`shell-panel.js`) — і
      залишок усе одно замкнутий, тобто мутація «прибрати корінь» пройшла б
      зеленою.

    Ціна забутого модуля платиться не тут, а в браузері ГЛЯДАЧА: 404 на
    `shell/<модуль>`, оболонка не піднімається, і побачить це людина, якій ми
    дали посилання, — бо в інструменті `publish/shell/` не відкривається зовсім.
    """

    #: Названі спільними в спеці 02.09.2026, розділ «Архітектура: що ділиться».
    SPEC_SHARED = ('i18n.js', 'icons.js', 'shell-panel.js', 'viewport.js',
                   'camera.js', 'canvas-geom.js', 'layout.js', 'rows-model.js',
                   'styles.css')

    #: Власне зовнішньої оболонки — не «спільне», а те, чого немає в
    #: інструменті взагалі. Друга підлога, окрема від `SPEC_SHARED`, і не за
    #: симетрію: замкнутість по імпортах тримає ЛИСТИ, а корінь тримати нічим —
    #: викинь `ext-shell.js`, і залишок усе одно замкнутий, тобто мутація
    #: «прибрати корінь» пройшла б зеленою. А ціна саме цього кореня —
    #: оболонка, що не піднялась узагалі: обгортка вантажить рівно один модуль.
    EXT_OWN = ('ext-shell.js', 'ext-bar.js')

    IMPORT_RE = re.compile(r"""from\s+["']\./([\w.-]+)["']""")

    def test_spec_modules_are_all_in_the_constant(self):
        missing = [m for m in self.SPEC_SHARED if m not in serve.SHELL_MODULES]
        self.assertEqual(missing, [], 'спека називає ці модулі спільними')

    def test_external_shell_own_modules_are_in_the_constant(self):
        missing = [m for m in self.EXT_OWN if m not in serve.SHELL_MODULES]
        self.assertEqual(missing, [], 'без них обгортка вантажить 404')

    def test_every_name_exists_in_app(self):
        for name in serve.SHELL_MODULES:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, 'app', name)),
                            f'{name} у переліку є, а файла немає')

    def test_list_is_closed_under_imports(self):
        """Забутий лист = 404 у глядача. Замикання рахуємо, а не переписуємо."""
        for name in serve.SHELL_MODULES:
            if not name.endswith('.js'):
                continue
            with open(os.path.join(ROOT, 'app', name), encoding='utf-8') as fh:
                body = fh.read()
            for dep in self.IMPORT_RE.findall(body):
                self.assertIn(dep, serve.SHELL_MODULES,
                              f'{name} імпортує {dep}, а везти його не збираємось')


class FrameKeyRule(unittest.TestCase):
    """Ключ кадру розбирається ТИМ САМИМ правилом, що в `app/viewport.js`.

    Друге правило тут коштувало б дорожче, ніж виглядає: публікація складала б
    `frames` за одними ключами, а зовнішній «Огляд» шукав би кадри за іншими —
    і розбіжність побачив би не тест, а глядач, у якого замість макетів порожні
    прямокутники. Тому число `CANVAS_W` пришпилене до JS-файла, а не переписане
    в Python «на памʼять».
    """

    def test_canvas_width_matches_viewport_js(self):
        with open(os.path.join(ROOT, 'app', 'viewport.js'), encoding='utf-8') as fh:
            src = fh.read()
        m = re.search(r'export const CANVAS_W = (\d+)', src)
        self.assertIsNotNone(m, 'CANVAS_W зник із viewport.js — тоді й тут інша величина')
        self.assertEqual(serve.CANVAS_W, int(m.group(1)))

    def test_typical_width_has_no_suffix(self):
        self.assertEqual(serve.split_frame_key('main'), ('main', serve.CANVAS_W))

    def test_suffix_is_the_width(self):
        self.assertEqual(serve.split_frame_key('main@768'), ('main', 768))

    def test_state_key_keeps_its_tail(self):
        self.assertEqual(serve.split_frame_key('poshuk~30d36f19@390'),
                         ('poshuk~30d36f19', 390))

    def test_trailing_newline_is_not_a_width_either(self):
        """Пастка Python, якої немає в JS: `$` збігається ПЕРЕД кінцевим
        переносом рядка. Порт мусить бути порт, а не «майже те саме»."""
        self.assertEqual(serve.split_frame_key('main@768\n'),
                         ('main@768\n', serve.CANVAS_W))

    def test_junk_after_at_is_not_a_width(self):
        """Манифест приїжджає з чужої машини — сміття не сміє прикидатись шириною."""
        self.assertEqual(serve.split_frame_key('main@nope'),
                         ('main@nope', serve.CANVAS_W))


# Запис зʼємки в тому вигляді, у якому його справді пише конвейєр (заміряно на
# `boss-interface` 02.09.2026): полів там більше, і це несуче — маніфест превʼю
# мусить забрати РІВНО `w`/`h`, а не перекласти запис цілком. Зайві поля в
# статиці, яку читає чужий браузер, — це і вага, і `sha`/`stamp`, яким там
# нема кого цікавити.
SHOT_REC = {'w': 1280, 'h': 6879, 'bytes': 628214, 'stable': True,
            'stale': False, 'sha': '17ff82add469428e'}


class PublishFrames(unittest.TestCase):
    """Кадри в `publish/<it>/_frames/` — під ТИМ САМИМ фільтром, що й сторінки.

    Це вимога конфіденційності, не косметика: сторінку знімають з превʼю руками,
    і якби її кадр поїхав, зовнішній «Огляд» показав би менеджеру рівно те, що
    від нього прибрали. Фільтр сторінок живе в `published_pages`, тому кадри
    беруть відповідь у неї, а не питають диск.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pf-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dst = tempfile.mkdtemp(prefix='pf-dst-')
        self.addCleanup(shutil.rmtree, self.dst, True)

    def _iter(self, it, pages, shots=None, manifest=None, sizes=None):
        d = os.path.join(self.tmp, 'iterations', it)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': pages}, fh)
        for f in serve.pm.flatten(pages):
            os.makedirs(os.path.join(d, f['page']['id']), exist_ok=True)
            with open(os.path.join(d, f['page']['id'], 'index.html'), 'w') as fh:
                fh.write('<body></body>')
        if shots is None and manifest is None:
            return {'dir': self.tmp}
        sd = os.path.join(d, 'shots')
        os.makedirs(sd, exist_ok=True)
        for k in (shots or ()):
            with open(os.path.join(sd, k + '.webp'), 'wb') as fh:
                fh.write(b'webp:' + k.encode())
        with open(os.path.join(sd, 'manifest.json'), 'w', encoding='utf-8') as fh:
            if manifest is not None:
                fh.write(manifest)
            else:
                # Розміри в записі — те саме, що пише справжня зʼємка
                # (заміряно на `boss-interface`: `main → {w: 1280, h: 6879}`).
                # `sizes` підміняє запис ОДНОГО кадру — ним перевіряється
                # валідація, і саме поштучно: манифест із одним битим записом
                # реальніший за манифест, битий цілком.
                rec = dict(SHOT_REC)
                json.dump({'checkedAt': '02.09.2026 15:16',
                           'shots': {k: (sizes or {}).get(k, rec) for k in shots}},
                          fh)
        return {'dir': self.tmp}

    def _pages(self, task, it):
        return serve.published_pages(task, [{'id': it}])

    def test_published_page_frames_travel_with_their_relative_path(self):
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}],
                          shots=['alpha', 'alpha@768'])
        frames, warn = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertIsNone(warn)
        self.assertEqual(frames, {
            'alpha': {'path': 'it1/_frames/alpha.webp', 'w': 1280, 'h': 6879},
            'alpha@768': {'path': 'it1/_frames/alpha@768.webp', 'w': 1280, 'h': 6879}})
        self.assertTrue(os.path.isfile(os.path.join(self.dst, 'alpha@768.webp')))

    def test_frame_carries_only_path_and_the_two_measured_numbers(self):
        """Запис зʼємки несе десяток полів; у превʼю їде рівно шлях і розмір."""
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}], shots=['alpha'])
        frames, _ = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(sorted(frames['alpha']), ['h', 'path', 'w'],
                         'зайві поля зʼємки поїхали в статику превʼю')

    def test_size_that_is_not_a_positive_int_does_not_reach_the_manifest(self):
        """⛔ Несуча перевірка правки. Розмір читається як ДАНІ, а не обіцянка.

        Манифест зʼємки пише наш же конвейєр, але лежить він на диску й його
        правлять руками. Нуль у знаменнику пропорції дав би `Infinity` у висоті
        картки, рядок — `NaN`, і `rowsLayout` кинув би виняток на світі, який
        глядач мав побачити. Тому непридатний розмір НЕ їде взагалі: оболонка
        тоді спитає пропорцію в самого знімка — робоча дорога, не аварійна.
        Вигаданого числа замість нього теж немає: маніфест не сміє СТВЕРДЖУВАТИ
        розмір, якого ніхто не міряв.
        """
        for bad in ({'w': 1280, 'h': 0}, {'w': 1280, 'h': -1},
                    {'w': 1280, 'h': '6879'}, {'w': 1280, 'h': 6879.0},
                    {'w': 1280, 'h': None}, {'w': 1280},
                    {'w': 0, 'h': 6879}, {'h': 6879},
                    # `True` — це `int` у python: без явного відсіву `bool`
                    # висота картки стала б 1px, і то «за даними».
                    {'w': 1280, 'h': True}, {'w': True, 'h': 6879},
                    {'w': 1280, 'h': [6879]}, 'зовсім не обʼєкт', None):
            with self.subTest(bad=bad):
                task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}],
                                  shots=['alpha'], sizes={'alpha': bad})
                frames, warn = serve.publish_frames(
                    task, 'it1', self._pages(task, 'it1'), self.dst)
                self.assertIsNone(warn, 'битий розмір не сміє валити публікацію')
                self.assertEqual(frames['alpha'], {'path': 'it1/_frames/alpha.webp'},
                                 f'непридатний розмір {bad!r} доїхав у маніфест')

    def test_a_frame_with_a_broken_size_does_not_spoil_its_neighbour(self):
        """Валідація ПОШТУЧНА: один битий запис не сміє знеразмірити ітерацію."""
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'},
                                  {'id': 'beta', 'name': 'Бета'}],
                          shots=['alpha', 'beta'], sizes={'alpha': {'w': 1280, 'h': 0}})
        frames, _ = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(frames['alpha'], {'path': 'it1/_frames/alpha.webp'})
        self.assertEqual(frames['beta'],
                         {'path': 'it1/_frames/beta.webp', 'w': 1280, 'h': 6879})

    def test_frame_of_a_page_taken_off_the_preview_stays_home(self):
        """⛔ Несуча перевірка задачі. Кадр на диску є, сторінки в превʼю немає."""
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'},
                                  {'id': 'beta', 'name': 'Бета', 'published': False}],
                          shots=['alpha', 'beta', 'beta@768'])
        frames, _ = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(sorted(frames), ['alpha'])
        self.assertFalse(os.path.exists(os.path.join(self.dst, 'beta.webp')))
        self.assertFalse(os.path.exists(os.path.join(self.dst, 'beta@768.webp')))

    def test_state_frame_follows_the_publication_of_its_page(self):
        """Стан — та сама сторінка в іншому вигляді (те саме правило, що в
        `rows-model.js`: крапка «у превʼю» успадковується від сторінки)."""
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'},
                                  {'id': 'beta', 'name': 'Бета', 'published': False}],
                          shots=['alpha~30d36f19', 'beta~30d36f19'])
        frames, _ = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(sorted(frames), ['alpha~30d36f19'])

    def test_group_organizer_never_had_a_page_so_its_frame_does_not_travel(self):
        task = self._iter('it1', [{'id': 'grp', 'name': 'Група', 'isGroup': True,
                                   'children': [{'id': 'a', 'name': 'А'}]}],
                          shots=['grp', 'a'])
        frames, _ = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(sorted(frames), ['a'])

    def test_iteration_without_shots_is_empty_not_an_exception(self):
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}])
        frames, warn = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(frames, {})
        self.assertIsNone(warn, 'ітерацію могли просто ще не знімати — це не проблема')

    def test_manifest_that_is_not_json_warns_instead_of_killing_publication(self):
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}],
                          shots=['alpha'], manifest='{битий')
        frames, warn = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(frames, {})
        self.assertIsNotNone(warn)
        self.assertIn('it1', warn)

    def test_manifest_that_is_not_an_object_warns_too(self):
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}],
                          shots=['alpha'], manifest='[1,2,3]')
        frames, warn = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(frames, {})
        self.assertIsNotNone(warn)

    def test_directory_instead_of_manifest_is_a_warning_not_a_crash(self):
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}], shots=['alpha'])
        man = os.path.join(self.tmp, 'iterations', 'it1', 'shots', 'manifest.json')
        os.remove(man)
        os.makedirs(man)
        frames, warn = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(frames, {})
        self.assertIsNotNone(warn)

    def test_key_in_the_manifest_without_a_file_is_skipped(self):
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}], shots=['alpha'])
        os.remove(os.path.join(self.tmp, 'iterations', 'it1', 'shots', 'alpha.webp'))
        frames, warn = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(frames, {})
        self.assertIsNone(warn)

    def test_key_that_is_not_a_frame_key_cannot_name_a_file_in_publish(self):
        """Ключі з манифеста стають ІМЕНАМИ ФАЙЛІВ у publish/ — сміття крізь них
        не пролізає (те саме правило SHOT_RE, що стереже роут /shot)."""
        task = self._iter('it1', [{'id': 'alpha', 'name': 'Альфа'}], shots=['alpha'])
        man = os.path.join(self.tmp, 'iterations', 'it1', 'shots', 'manifest.json')
        with open(man, 'w', encoding='utf-8') as fh:
            json.dump({'shots': {'../../../etc/passwd': {}, 'alpha': {}}}, fh)
        frames, _ = serve.publish_frames(task, 'it1', self._pages(task, 'it1'), self.dst)
        self.assertEqual(sorted(frames), ['alpha'])
        self.assertEqual(sorted(os.listdir(self.dst)), ['alpha.webp'])


class PublishManifest(unittest.TestCase):
    """`publish/manifest.json` — ЄДИНЕ джерело правди зовнішньої оболонки: без
    сервера в неї іншого немає. Тому склад полів стережеться тестом.

    ⚠️ Межа, названа вголос: `manifest.json` лежить у `publish/` статикою, тобто
    читається БЕЗ гейту. Це не новий канал витоку — обгортка превʼю вже сьогодні
    несе і назву задачі, і назви сторінок, і сам пароль у тексті `index.html`
    (гейт — оверлей у браузері, не серверний замок). Але якщо колись гейт стане
    справжнім, цей файл мусить поїхати за нього разом з обгорткою.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pm-')
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _task(self, pages_by_it):
        for it, pages in pages_by_it.items():
            d = os.path.join(self.tmp, 'iterations', it)
            os.makedirs(d, exist_ok=True)
            if pages is None:
                with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as fh:
                    fh.write('<html></html>')
            else:
                with open(os.path.join(d, 'pages.json'), 'w', encoding='utf-8') as fh:
                    json.dump({'pages': pages}, fh)
        return {'dir': self.tmp, 'title': 'Фікстура'}

    def _build(self, task, its, frames=None):
        pages = serve.published_pages(task, its)
        dst = os.path.join(self.tmp, 'publish')
        os.makedirs(dst, exist_ok=True)
        man = serve.publish_manifest(task, 'fixture', its, pages, frames or {}, dst)
        with open(os.path.join(dst, 'manifest.json'), encoding='utf-8') as fh:
            return man, json.load(fh)

    def test_outline_carries_folders_and_kinds(self):
        task = self._task({'it1': [{'id': 'p', 'name': 'Картка', 'kind': 'page', 'children': [
            {'id': 'w', 'name': 'Віджет', 'kind': 'folder', 'children': [
                {'id': 's', 'name': 'Помилка', 'kind': 'state'}]}]}]})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual(man['outline'], [
            {'id': 'it1/p', 'it': 'it1', 'key': 'p', 'name': 'Картка', 'kind': 'page', 'depth': 0, 'path': 'it1/p/index.html'},
            {'id': 'it1/w', 'it': 'it1', 'key': 'w', 'name': 'Віджет', 'kind': 'folder', 'depth': 1},
            {'id': 'it1/s', 'it': 'it1', 'key': 's', 'name': 'Помилка', 'kind': 'state', 'depth': 2, 'path': 'it1/s/index.html'}])
        # pages — без змін: лише відкривані
        self.assertEqual([p['key'] for p in man['pages']], ['p', 's'])

    def test_outline_implicit_main(self):
        task = self._task({'it1': None})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual(man['outline'], [{'id': 'it1', 'it': 'it1', 'key': 'main', 'name': 'Головна',
                                           'kind': 'page', 'depth': 0, 'path': 'it1/index.html'}])

    def test_outline_ids_are_the_page_ids_of_the_manifest(self):
        """Рядок відкриваного вузла в `outline` — тим самим `id`/`path`, що й
        у `pages`: панель шукає сторінку за ним (`pageById`), і розбіжність
        означала б рядок, що не відкривається."""
        task = self._task({'it1': [
            {'id': 'p', 'name': 'П', 'kind': 'page', 'children': [
                {'id': 'f', 'name': 'Ф', 'kind': 'folder', 'children': [
                    {'id': 's', 'name': 'С', 'kind': 'state'}]}]}],
            'it2': None})
        man, _ = self._build(task, [{'id': 'it1'}, {'id': 'it2'}])
        openable = [r for r in man['outline'] if r['kind'] != 'folder']
        self.assertEqual([(r['id'], r['it'], r['key'], r['name'], r['depth'], r['path'])
                          for r in openable],
                         [(p['id'], p['it'], p['key'], p['name'], p['depth'], p['path'])
                          for p in man['pages']])

    def test_outline_follows_the_preview_filter_and_iterations_with_pages(self):
        """У `outline` — те, що й у превʼю: схована тека з усім піддеревом, схована
        сторінка зі станами й порожня тека не їдуть; ітерація без жодної
        відкриваної сторінки рядків не дає (як і в `iters`/`pages`)."""
        task = self._task({
            'it1': [
                {'id': 'p', 'name': 'П', 'kind': 'page'},
                {'id': 'd', 'name': 'Чернетки', 'kind': 'folder', 'published': False,
                 'children': [{'id': 'x', 'name': 'Х', 'kind': 'page'}]},
                {'id': 'e', 'name': 'Порожня', 'kind': 'folder'},
                {'id': 'h', 'name': 'Х', 'kind': 'page', 'published': False,
                 'children': [{'id': 'hs', 'name': 'ХС', 'kind': 'state'}]}],
            'it2': [{'id': 'only', 'name': 'Лише тека', 'kind': 'folder'}]})
        man, _ = self._build(task, [{'id': 'it1'}, {'id': 'it2'}])
        self.assertEqual([r['id'] for r in man['outline']], ['it1/p'])
        self.assertEqual([i['id'] for i in man['iters']], ['it1'])

    def test_outline_folder_id_lives_in_the_out_rel_space_and_has_no_path(self):
        """Теки файла нема: `path` у її рядка був би посиланням у нікуди; `id`
        — у тому ж просторі `<it>/<id>`, що й сторінки, і не колізує з ними."""
        task = self._task({'it1': [{'id': 'f', 'name': 'Ф', 'kind': 'folder', 'children': [
            {'id': 'a', 'name': 'А', 'kind': 'page'}]}]})
        man, _ = self._build(task, [{'id': 'it1'}])
        folder = man['outline'][0]
        self.assertEqual((folder['id'], folder['kind']), ('it1/f', 'folder'))
        self.assertNotIn('path', folder)
        self.assertEqual(man['outline'][1]['id'], 'it1/a')

    def test_outline_folder_named_main_does_not_take_the_iteration_root_id(self):
        """`page_rel` віддає '' для будь-якого вузла з id `main` (неявна «Головна»),
        тож теки `main` без власного правила діставалось би id = самому `it1` — тому
        ж, що має корінь ітерації. Тека id збирає ЗАВЖДИ як `<it>/<id>`."""
        task = self._task({'it1': [{'id': 'main', 'name': 'Головні', 'kind': 'folder', 'children': [
            {'id': 'a', 'name': 'А', 'kind': 'page'}]}]})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual([(r['id'], r['kind']) for r in man['outline']],
                         [('it1/main', 'folder'), ('it1/a', 'page')])

    def test_written_to_the_root_of_publish(self):
        task = self._task({'it1': [{'id': 'alpha', 'name': 'Альфа'}]})
        man, ondisk = self._build(task, [{'id': 'it1'}])
        self.assertEqual(man, ondisk, 'віддане й записане мусять бути одним обʼєктом')

    def test_manifest_carries_no_author_anywhere(self):
        """⛔ Рішення власника 15.09.2026: підпис автора живе лише в інструменті.

        Причина фактична, не обережність: 11.09.2026 заміряно, що
        `GET /manifest.json` віддає 200 БЕЗ пароля — тобто ПІБ і email
        дизайнера лежали б у відкритому файлі на Vercel. Охоронець стоїть тут,
        бо ітерації в маніфест кладуться явним переліком полів, і наступне поле
        легко приїде туди «саме» разом із розширенням запису ітерації.
        Мутація: додай `'author': it.get('author')` у словник `iters` — падає.
        """
        task = self._task({'it1': [{'id': 'alpha', 'name': 'Альфа'}]})
        man, ondisk = self._build(task, [
            {'id': 'it1', 'note': 'правки', 'author': 'Ольга Сидорук',
             'author_key': 'designer2@example.com',
             'origin': {'it': 'it3', 'at': '09.09.2026 14:20'}}])
        raw = json.dumps(ondisk, ensure_ascii=False)
        self.assertNotIn('author', raw)
        self.assertNotIn('designer2@', raw)
        self.assertNotIn('Ольга', raw)
        self.assertNotIn('origin', raw)
        self.assertEqual(set(man['iters'][0].keys()), {'id', 'num', 'note'})

    def test_iterations_carry_number_and_note_apart(self):
        """Маніфест везе НОМЕР і ПРИМІТКУ окремо, а не спечений підпис.

        Префікс «Іт.N» — це ПРЕЗЕНТАЦІЯ, і мову для неї вибирає ГЛЯДАЧ у своєму
        браузері (`dc-lang` у localStorage), а не Python на машині дизайнера.
        Спечений тут підпис приїжджав у смугу кирилицею навіть при `dc-lang=en`
        — заміряно 03.09.2026 на зібраному превʼю: смуга йшла англійською
        («Layout / Overview / Copy link»), а крошка показувала «Іт.1 ·
        фікстура». Той самий клас вади, що вже кусав двічі 02.09.2026 (`Іт.N`
        шаблонним літералом у `app.js`; підписи вкладок аудиторій, спечені
        сервером, який не знає мови клієнта), і лікування те саме — розділити
        ідентифікатор і презентацію.

        Що лишається в Python: ОЧИЩЕННЯ підпису (явний `label` → `note` без
        префікса «LIGA-1234 · »). Це нормалізація ДАНИХ, одна на всі мови, і
        `iteration_note()` тримає її в одному місці для обох консументів.
        """
        task = self._task({'it1': [{'id': 'alpha', 'name': 'Альфа'}]})
        man, _ = self._build(task, [{'id': 'it1', 'note': 'LIGA-1 · старт'}])
        self.assertEqual(man['task'], 'Фікстура')
        # ⛔ Саме СКЛАД запису, не «є потрібні поля»: `label` поруч означав би
        # два джерела підпису — і оболонка взяла б готове, як брала досі.
        self.assertEqual(man['iters'], [{'id': 'it1', 'num': '1', 'note': 'старт'}])

    def test_iteration_without_a_note_carries_an_empty_one(self):
        """Порожній рядок, а не відсутнє поле: оболонка малює примітку ОКРЕМИМ
        вузлом розмітки й не мусить розрізняти «немає ключа» і «немає тексту»."""
        task = self._task({'it1': [{'id': 'alpha', 'name': 'Альфа'}]})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual(man['iters'], [{'id': 'it1', 'num': '1', 'note': ''}])

    def test_only_published_iterations_that_have_pages_are_offered(self):
        """Те саме правило, що в дропдауні обгортки: ітерація без сторінок не
        пропонується — інакше перелік бреше про те, що можна відкрити."""
        task = self._task({'it1': [{'id': 'alpha', 'name': 'Альфа'}],
                           'it2': [{'id': 'beta', 'name': 'Бета', 'published': False}]})
        man, _ = self._build(task, [{'id': 'it1'}, {'id': 'it2'}])
        self.assertEqual([i['id'] for i in man['iters']], ['it1'])
        self.assertEqual(sorted(man['frames']), ['it1'])

    def test_pages_carry_path_depth_and_frame_key(self):
        """`id` — шлях у publish (ним ходить `#p=`), `key` — база ключа КАДРУ.
        Це різні рядки: у неявної «Головної» `id` = `it1`, а кадр лежить під
        `main`. Одне поле на дві ролі означало б «Огляд» без кадрів."""
        task = self._task({'it1': None})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual(man['pages'], [{'id': 'it1', 'it': 'it1', 'key': 'main',
                                         'name': 'Головна', 'depth': 0,
                                         'path': 'it1/index.html'}])

    def test_child_page_keeps_its_depth(self):
        task = self._task({'it1': [{'id': 'a', 'name': 'А', 'children': [
            {'id': 'a--empty', 'name': 'Стан: порожньо'}]}]})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual([(p['id'], p['key'], p['depth']) for p in man['pages']],
                         [('it1/a', 'a', 0), ('it1/a--empty', 'a--empty', 1)])

    def test_unpublished_page_is_absent_from_the_manifest_too(self):
        task = self._task({'it1': [{'id': 'a', 'name': 'А'},
                                   {'id': 'b', 'name': 'Б', 'published': False}]})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual([p['key'] for p in man['pages']], ['a'])

    def test_widths_are_the_ones_frames_actually_exist_for(self):
        task = self._task({'it1': [{'id': 'a', 'name': 'А'}]})
        man, _ = self._build(task, [{'id': 'it1'}], frames={'it1': {
            'a': {'path': 'it1/_frames/a.webp', 'w': 1280, 'h': 6879},
            'a@768': {'path': 'it1/_frames/a@768.webp', 'w': 768, 'h': 4300}}})
        self.assertEqual(man['widths'], [768, serve.CANVAS_W])

    def test_widths_come_from_the_keys_and_never_from_the_measured_w(self):
        """⛔ Нова пастка цієї правки, названа вголос: у кадрі тепер ДВІ ширини.

        `w` у записі — це ширина ЗНІМКА в пікселях, і вона більша за ширину
        вьюпорта, коли кадр знято з подвоєною щільністю (саме тому `onFrameLoad`
        ділить на `naturalWidth`, а не бере `naturalHeight` як є). Ширина
        ВЬЮПОРТА живе тільки в КЛЮЧІ. Порахуй сегмент ширин по `w` — і глядачу
        запропонують «1536», якого не має ні один ключ: кнопка, що не знаходить
        кадрів. Тому `widths` рахує `split_frame_key`, і ця перевірка стоїть тут,
        щоб `w` поруч не спокусив на коротший шлях.
        """
        task = self._task({'it1': [{'id': 'a', 'name': 'А'}]})
        man, _ = self._build(task, [{'id': 'it1'}], frames={'it1': {
            'a@768': {'path': 'it1/_frames/a@768.webp', 'w': 1536, 'h': 8600}}})
        self.assertEqual(man['widths'], [768])

    def test_iteration_without_frames_is_an_empty_map_not_a_hole(self):
        task = self._task({'it1': [{'id': 'a', 'name': 'А'}]})
        man, _ = self._build(task, [{'id': 'it1'}])
        self.assertEqual(man['frames'], {'it1': {}})
        self.assertEqual(man['widths'], [])


class ServerCodeStalenessTest(unittest.TestCase):
    """Детектор «процес старіший за код на диску» (фідбек 25.08.2026)."""

    def test_process_newer_than_code_says_nothing(self):
        # Нормальний стан канваса: свіжо запущений сервер, ніхто нічого не правив.
        self.assertIsNone(serve.server_code_staleness(started_at=time.time() + 3600))

    def test_code_newer_than_process_names_the_files(self):
        msg = serve.server_code_staleness(started_at=0)
        self.assertIn('serve.py', msg)
        self.assertIn('перезапуск', msg)

    def test_warning_says_what_is_stale_and_whether_to_republish(self):
        """fb-22092026-3a9764: попередження «коректне, але з нього не ясно, чи
        опублікований результат валідний і чи треба перевидавати». Текст мусить
        розвести свіже (сторінки з диска) і старе (обгортку) і сказати про
        повторну публікацію та незмінну адресу."""
        msg = serve.server_code_staleness(started_at=0)
        self.assertIn('Сторінки макета взято з диска', msg)
        self.assertIn('обгортку превʼю', msg)
        self.assertIn('опубліковане працює', msg)
        self.assertIn('адреса лишиться та сама', msg)
        # Розкрій сторінок називається лише коли змінено саме його модуль.
        only_serve = [p for p in serve._loaded_app_sources()
                      if os.path.basename(p) == 'serve.py']
        with mock.patch.object(serve, '_loaded_app_sources', return_value=only_serve):
            self.assertNotIn('розкрій сторінок', serve.server_code_staleness(started_at=0))
        self.assertIn('розкрій сторінок', msg)

    def test_unreadable_mtime_is_loud_not_silent(self):
        """«Не знаю» мусить звучати. Мовчазний except тут = та сама тиша, через
        яку правка й не доїхала: сервер сказав би «все свіже», не перевіривши."""
        ghost = os.path.join(serve.APP_DIR, 'знесений.py')
        with mock.patch.object(serve, '_loaded_app_sources', return_value=[ghost]):
            msg = serve.server_code_staleness(started_at=0)
        self.assertIn('знесений.py', msg)
        self.assertIn('невідомо', msg)

    def test_watched_files_cover_everything_the_wrapper_is_built_from(self):
        """Перелік із sys.modules, а не хардкод: обгортка = serve.py + розкрій
        сторінок pages_model. Хардкод мовчки застаріває, а це саме той сорт
        мовчання, від якого попередження й ставилось."""
        names = {os.path.basename(f) for f in serve._loaded_app_sources()}
        self.assertIn('serve.py', names)
        self.assertIn('pages_model.py', names)


class IterAssetRevalidation(unittest.TestCase):
    """Ассети ітерації мусять ПЕРЕЗВІРЯТИСЬ, а не перекачуватись.

    `_send_iter_file` шле рівно Content-Type + Content-Length, а `end_headers`
    дописує `Cache-Control: no-cache`. Разом це означає: валідатора немає,
    отже кожне відкриття макета тягне КОЖЕН файл заново, з кодом 200. Для
    United (e-Ukraine, три-чотири ваги OTF) це переверстка тексту рівно у вікні
    анімації входу — «весь інтерфейс трохи дьоргається» на першому вході, а в
    того, у кого шрифти теплі, не відтворюється взагалі. Дефект виглядає як баг
    макета, хоча це кеш сервера (фідбек 09.09.2026, LIGA-7012).

    ⛔ `no-cache` лишається свідомо: дизайнер править файли постійно, і довгий
    `max-age` віддавав би застаріле — та сама брехня, проти якої цей батч.
    Валідатор дає 304 без тіла, тобто перекачування зникає, а застаріле не
    показується ніколи.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-iterassets-')
        it1 = os.path.join(cls.tmp, 'iterations', 'it1')
        os.makedirs(it1)
        with open(os.path.join(it1, 'index.html'), 'w') as f:
            f.write('<html><body><h1>Мокап</h1></body></html>')
        with open(os.path.join(cls.tmp, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '24.08.2026 12:00',
                                       'note': 'ф', 'published': True}]}, f)
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-iterassets-cfg-')
        os.environ['DC_TASKS_FILE'] = os.path.join(cls.cfgdir, 'tasks.json')
        os.environ['DC_NO_OVERVIEW'] = '1'
        with open(os.environ['DC_TASKS_FILE'], 'w') as f:
            json.dump({'current': 'fixture', 'design_work_root': cls.cfgdir,
                       'tasks': {'fixture': {'dir': cls.tmp, 'title': 'Ф'}}}, f)
        cls.httpd = serve.make_server(0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.httpd.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        for d in (cls.tmp, cls.cfgdir):
            shutil.rmtree(d, ignore_errors=True)

    URL = '/it-assets/it1/index.html'

    def test_asset_carries_validator(self):
        r = urllib.request.urlopen(self.base + self.URL)
        self.assertEqual(r.status, 200)
        self.assertTrue(r.headers['ETag'], 'ассет без валідатора — браузеру нічим перезвіряти')
        # Перезвірка лишається обовʼязковою: застаріле показувати не можна.
        self.assertIn('no-cache', r.headers['Cache-Control'])

    def test_same_etag_gives_304_without_body(self):
        etag = urllib.request.urlopen(self.base + self.URL).headers['ETag']
        req = urllib.request.Request(self.base + self.URL,
                                     headers={'If-None-Match': etag})
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 304)
        self.assertEqual(e.exception.read(), b'', '304 не сміє нести тіло')

    def test_edited_file_gives_200_and_new_etag(self):
        """Зворотний бік: перезвірка не сміє схвалювати застаріле.

        Без цієї половини найпростіша «правка» — віддавати 304 завжди —
        виглядала б як успіх і зробила б макет незмінним на екрані.
        """
        etag = urllib.request.urlopen(self.base + self.URL).headers['ETag']
        path = os.path.join(self.tmp, 'iterations', 'it1', 'index.html')
        with open(path, 'w') as f:
            f.write('<html><body><h1>Мокап 2</h1></body></html>')
        req = urllib.request.Request(self.base + self.URL,
                                     headers={'If-None-Match': etag})
        r = urllib.request.urlopen(req)
        self.assertEqual(r.status, 200)
        self.assertNotEqual(r.headers['ETag'], etag)
        self.assertIn(b'2', r.read())

    def test_missing_iteration_asset_names_the_current_task(self):
        """404 мусить називати ПОТОЧНУ задачу, а не мовчати.

        Коли задача перемкнулась (наприклад, синхронізація реєстру відкотила
        `current` — див. bin/test_registry.py), `/it-assets/<it>/…` починає
        давати 404, а `/api/iteration-pages` — порожньо. Виглядає як зламана
        ітерація, і дизайнер іде шукати поломку в макеті. Назва поточної задачі
        в тілі відповіді перетворює загадку на факт.
        """
        with self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(self.base + '/it-assets/it9/index.html')
        self.assertEqual(e.exception.code, 404)
        body = e.exception.read().decode('utf-8', 'replace')
        self.assertIn('fixture', body, f'404 не назвав поточну задачу: {body[:300]}')


class MachineIdentity(unittest.TestCase):
    """Особа машини і «своя/чужа» ітерація.

    ⛔ Порівнюємо по КЛЮЧУ (email), а не по імені: тезки й перейменування не
    сміють робити мою ітерацію чужою.
    """

    def setUp(self):
        self.env = {k: os.environ.get(k) for k in
                    ('DC_IDENTITY_NAME', 'DC_IDENTITY_EMAIL')}
        os.environ['DC_IDENTITY_NAME'] = 'Ольга Сидорук'
        os.environ['DC_IDENTITY_EMAIL'] = 'designer2@example.com'

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_identity_from_env(self):
        self.assertEqual(serve.machine_identity(),
                         ('Ольга Сидорук', 'designer2@example.com'))

    def test_no_identity_is_empty_not_invented(self):
        """⛔ Нема конфіга — нема підпису. Фолбек на константне імʼя означав би
        приписати роботу конкретній людині."""
        os.environ['DC_IDENTITY_NAME'] = ''
        os.environ['DC_IDENTITY_EMAIL'] = ''
        self.assertEqual(serve.machine_identity(), ('', ''))

    def test_git_config_is_read_once_not_per_request(self):
        """⛔ `/api/task` канвас ПОЛИТЬ, а особа машини за життя процесу не
        міняється. Без кешу кожен опит смуги коштував би двох `git config` —
        два процеси на запит там, де відповідь константна.

        Env-перекриття кешем НЕ накривається: тести в одному процесі грають
        двох дизайнерів, і закешована відповідь зробила б другого першим.
        """
        os.environ.pop('DC_IDENTITY_NAME', None)
        os.environ.pop('DC_IDENTITY_EMAIL', None)
        serve._identity_cache = None
        with mock.patch('serve.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 0, 'Lead\n', '')
            first = serve.machine_identity()
            second = serve.machine_identity()
        self.assertEqual(first, second)
        self.assertEqual(run.call_count, 2, 'git config запущено більше одного разу на ключ')
        serve._identity_cache = None

    def test_failed_git_config_is_not_cached_as_empty(self):
        """⛔ Транзієнтний збій `git config` не сміє осісти в кеші назавжди.

        Канвас живе днями. Закешована порожнеча означала б, що до перезапуску
        всі нові ітерації народжуються без підпису, а всі чужі раптом стають
        своїми — і дизайнер, який полагодив `user.email`, цього не побачить.
        Мутація: кешуй результат безумовно — тест червоніє.
        """
        os.environ.pop('DC_IDENTITY_NAME', None)
        os.environ.pop('DC_IDENTITY_EMAIL', None)
        serve._identity_cache = None
        with mock.patch('serve.subprocess.run') as run:
            run.return_value = subprocess.CompletedProcess([], 1, '', 'fatal')
            self.assertEqual(serve.machine_identity(), ('', ''))
            run.return_value = subprocess.CompletedProcess([], 0, 'Lead\n', '')
            self.assertEqual(serve.machine_identity()[0], 'Lead',
                             'порожню відповідь закешовано — підпис не повернеться')
        serve._identity_cache = None

    def test_commit_identity_uses_one_source_of_truth(self):
        """`_commit_identity` бере особу з `machine_identity`, а не власним
        запитом до git. Константа лишається ЛИШЕ як git-підпис коміта: у дані
        вона потрапити не може, бо туди пише `_stamp_author`, а він на порожній
        особі не пише нічого.

        Мутація: поверни власний цикл `git config` у `_commit_identity` — тест
        червоніє, бо env-перекриття він не побачить.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Ольга Сидорук'
        os.environ['DC_IDENTITY_EMAIL'] = 'designer2@example.com'
        self.assertEqual(serve._commit_identity(),
                         ['-c', 'user.name=Ольга Сидорук',
                          '-c', 'user.email=designer2@example.com'])
        os.environ['DC_IDENTITY_NAME'] = ''
        os.environ['DC_IDENTITY_EMAIL'] = ''
        # Порожня особа: git без user.email не комітить узагалі, тому тут
        # константа — і рівно тут вона нікого не підписує в ДАНИХ.
        self.assertEqual(serve._commit_identity(),
                         ['-c', 'user.name=Designer One',
                          '-c', 'user.email=designer.one@example.com'])
        self.assertEqual(serve._stamp_author({'id': 'it1'}), {'id': 'it1'})

    def test_mine_by_key_not_by_name(self):
        same_name = {'id': 'it1', 'author': 'Ольга Сидорук',
                     'author_key': 'designer2@other.example'}
        self.assertFalse(serve.iteration_is_mine(same_name, 'designer2@example.com'))
        other_name = {'id': 'it2', 'author': 'М. К.',
                      'author_key': 'designer2@example.com'}
        self.assertTrue(serve.iteration_is_mine(other_name, 'designer2@example.com'))

    def test_legacy_iteration_without_author_is_mine(self):
        """Вся наявна історія не сміє раптом стати чужою й read-only."""
        self.assertTrue(serve.iteration_is_mine({'id': 'it1'}, 'designer2@example.com'))

    def test_machine_without_identity_owns_everything(self):
        """Машина без git-конфіга деградує в сьогоднішню поведінку, не в поломку."""
        self.assertTrue(serve.iteration_is_mine(
            {'id': 'it1', 'author_key': 'someone@else'}, ''))


class IterationAuthorStamp(unittest.TestCase):
    """Нова ітерація підписана тим, хто її завів."""

    def setUp(self):
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'

    def tearDown(self):
        os.environ.pop('DC_IDENTITY_NAME', None)
        os.environ.pop('DC_IDENTITY_EMAIL', None)

    def test_stamp_adds_author(self):
        e = serve._stamp_author({'id': 'it2'})
        self.assertEqual(e['author'], 'Lead')
        self.assertEqual(e['author_key'], 'lead@example.com')

    def test_stamp_without_identity_adds_nothing(self):
        """⛔ Порожній підпис — це НЕ поле з порожнім рядком: `author: ''`
        читалось би як «автор відомий і безіменний»."""
        os.environ['DC_IDENTITY_NAME'] = ''
        os.environ['DC_IDENTITY_EMAIL'] = ''
        e = serve._stamp_author({'id': 'it2'})
        self.assertNotIn('author', e)
        self.assertNotIn('author_key', e)


class TaskPerRequest(unittest.TestCase):
    """Задача ЗАПИТУ, а не «поточна машини» (fb-07102026-e627c2).

    Сервер тримав ОДНУ поточну задачу на машину (`tasks.json` → `current`), і
    паралельна сесія Claude, що перемкнула її, відправляла `/it-assets`, синк і
    публікацію ПЕРШОЇ сесії в чужу задачу — без жодного сигналу. Тепер запит
    може назвати задачу сам: заголовок `X-Canvas-Task` або префікс `/t/<id>/`.
    Невідома назва — 404 з назвою, а НЕ тихий відкат на поточну: інакше помилка
    в id знову била б у чужу задачу.

    ⛔ Конфіг — ТИМЧАСОВИЙ (`DC_TASKS_FILE`): охоронці `LiveConfigUntouched` і
    `TestsCannotWriteLiveConfig` стежать, щоб жоден тест не писав у живий.
    Фікстура перестворюється на КОЖЕН тест: тести пишуть (нова ітерація, пароль,
    перемикання `current`), і сусід не сміє успадкувати чужий стан.
    """

    @classmethod
    def setUpClass(cls):
        cls.cfgdir = tempfile.mkdtemp(prefix='dc-taskreq-cfg-')
        cls.root = tempfile.mkdtemp(prefix='dc-taskreq-')
        cls.tasks_file = os.path.join(cls.cfgdir, 'tasks.json')
        os.environ['DC_TASKS_FILE'] = cls.tasks_file
        os.environ['DC_NO_OVERVIEW'] = '1'
        cls.httpd = serve.make_server(0)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.port}'

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        os.environ.pop('DC_TASKS_FILE', None)
        os.environ.pop('DC_NO_OVERVIEW', None)
        for d in (cls.cfgdir, cls.root):
            shutil.rmtree(d, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(self.root, ignore_errors=True)
        self.dirs = {}
        for tid in ('alpha', 'beta'):
            d = os.path.join(self.root, tid)
            it1 = os.path.join(d, 'iterations', 'it1')
            os.makedirs(os.path.join(it1, 'assets'))
            with open(os.path.join(it1, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(f'<!DOCTYPE html><html><body><h1>{tid}</h1></body></html>')
            with open(os.path.join(it1, 'assets', 'x.css'), 'w', encoding='utf-8') as f:
                f.write(f'.mark-{tid}{{color:red}}')
            with open(os.path.join(d, 'iterations.json'), 'w', encoding='utf-8') as f:
                json.dump({'iterations': [{'id': 'it1', 'date': '12.10.2026 10:00',
                                           'note': tid, 'published': False}],
                           'publish_url': None}, f)
            self.dirs[tid] = d
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump({'current': 'alpha', 'design_work_root': self.cfgdir,
                       'tasks': {'alpha': {'dir': self.dirs['alpha'], 'title': 'Альфа'},
                                 'beta': {'dir': self.dirs['beta'], 'title': 'Бета'}}}, f)

    def _cfg(self):
        with open(self.tasks_file, encoding='utf-8') as f:
            return json.load(f)

    def _meta(self, tid):
        with open(os.path.join(self.dirs[tid], 'iterations.json'), encoding='utf-8') as f:
            return json.load(f)

    def get(self, path, headers=None):
        """(статус, тіло як текст) — і для 200, і для відмов."""
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')
        return r.status, r.read().decode('utf-8')

    def send_post(self, path, payload, headers=None):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(), method='POST',
            headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode('utf-8', 'replace')
        return r.status, r.read().decode('utf-8')

    def test_1_header_names_the_task_and_does_not_stick_to_the_connection(self):
        """Заголовок діє на ОДИН запит. Обробник живе, поки живе зʼєднання, тож
        задачу, названу першим запитом, наступний запит БЕЗ заголовка успадкував би.

        Реальний сервер говорить HTTP/1.0 (зʼєднання на кожен запит), і з ним цей
        тест був би вакуумно зеленим. Тому окремий сервер на HTTP/1.1, а що
        зʼєднання таки одне — доводить `conn.sock` до й після."""
        import http.client
        httpd = serve.make_server(0)
        httpd.RequestHandlerClass.protocol_version = 'HTTP/1.1'
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection('127.0.0.1', httpd.server_address[1], timeout=10)
        try:
            def ask(headers):
                conn.request('GET', '/api/task', headers=headers)
                r = conn.getresponse()
                return json.loads(r.read())['id'], r
            plain, r0 = ask({})
            named, r1 = ask({'X-Canvas-Task': 'beta'})
            sock = conn.sock
            after, r2 = ask({})
            self.assertEqual((plain, named, after), ('alpha', 'beta', 'alpha'),
                             'задача з заголовка прилипла до наступного запиту')
            self.assertFalse(r1.will_close, 'сервер закрив зʼєднання — тест не про keep-alive')
            self.assertIs(conn.sock, sock, 'зʼєднання перевідкрите — тест не про keep-alive')
        finally:
            conn.close()
            httpd.shutdown()
            httpd.server_close()

    def test_1b_header_works_on_a_plain_connection_too(self):
        st, body = self.get('/api/task')
        self.assertEqual(json.loads(body)['id'], 'alpha')
        st, body = self.get('/api/task', {'X-Canvas-Task': 'beta'})
        self.assertEqual((st, json.loads(body)['id']), (200, 'beta'))

    def test_2_prefix_names_the_task_for_it_assets(self):
        st, body = self.get('/t/beta/it-assets/it1/index.html')
        self.assertEqual(st, 200)
        self.assertIn('<h1>beta</h1>', body)
        st, body = self.get('/it-assets/it1/index.html')
        self.assertIn('<h1>alpha</h1>', body, 'без префікса — поточна задача машини')
        # хвіст із запитом лишається цілим після зняття префікса
        st, body = self.get('/t/beta/it-assets/it1/assets/x.css?v=3')
        self.assertIn('.mark-beta', body)
        # префікс доходить і до API, не лише до статики
        st, body = self.get('/t/beta/api/task')
        self.assertEqual(json.loads(body)['id'], 'beta')

    def test_3_unknown_task_is_404_naming_it_never_a_fallback(self):
        for path, headers, named in (
                ('/t/nope/it-assets/it1/index.html', None, 'nope'),
                ('/api/task', {'X-Canvas-Task': 'nope'}, 'nope'),
                ('/it-assets/it1/index.html', {'X-Canvas-Task': 'nope'}, 'nope'),
                # обхід теки через id: це не задача з tasks.json
                ('/t/..%2Fx/it-assets/it1/index.html', None, '../x'),
                ('/api/task', {'X-Canvas-Task': '../x'}, '../x')):
            with self.subTest(path=path, headers=headers):
                st, body = self.get(path, headers)
                self.assertEqual(st, 404)
                self.assertIn(named, body)
                self.assertNotIn('alpha', body, 'невідома задача відкотилась на поточну')
        # POST із тілом: відмова не змінює нічого й не губить відповідь
        before = (self._meta('alpha'), self._meta('beta'))
        st, body = self.send_post('/api/iteration', {'from': 'it1', 'note': 'x'},
                                  {'X-Canvas-Task': 'nope'})
        self.assertEqual(st, 404)
        self.assertIn('nope', body)
        self.assertEqual((self._meta('alpha'), self._meta('beta')), before)
        self.assertFalse(os.path.isdir(os.path.join(self.dirs['alpha'], 'iterations', 'it2')))

    def test_4_root_absolute_asset_resolves_through_the_referer_task(self):
        """Angular-збірка просить `/assets/x.css` (корене-абсолютно): шлях не
        каже, чия це ітерація, і до цього її брали з Referer і з ПОТОЧНОЇ задачі.
        Тепер задача береться з префікса в Referer теж."""
        ref = f'{self.base}/t/beta/it-assets/it1/index.html'
        st, body = self.get('/assets/x.css', {'Referer': ref})
        self.assertEqual(st, 200)
        self.assertIn('.mark-beta', body)
        # Referer без префікса — як і раніше, поточна задача
        st, body = self.get('/assets/x.css',
                            {'Referer': f'{self.base}/it-assets/it1/index.html'})
        self.assertIn('.mark-alpha', body)
        # явна задача запиту сильніша за Referer
        st, body = self.get('/assets/x.css', {'Referer': ref, 'X-Canvas-Task': 'alpha'})
        self.assertIn('.mark-alpha', body)

    def test_4c_commented_referer_with_a_prefix_names_the_task_too(self):
        """Сторінка зʼємки відкрита як `/t/beta/commented?it=…&bare=1`: її
        корене-абсолютні ассети мають Referer саме з нею, а не з `/it-assets/`."""
        ref = f'{self.base}/t/beta/commented?it=it1&page=main&bare=1'
        st, body = self.get('/assets/x.css', {'Referer': ref})
        self.assertEqual(st, 200)
        self.assertIn('.mark-beta', body)

    def test_4b_referer_with_unknown_task_is_ignored_not_served_from_current(self):
        """Чужий чи застарілий Referer не сміє тихо віддати ітерацію ПОТОЧНОЇ
        задачі: це та сама брехня, проти якої вся зміна."""
        ref = f'{self.base}/t/nope/it-assets/it1/index.html'
        st, body = self.get('/assets/x.css', {'Referer': ref})
        self.assertEqual(st, 404)
        self.assertNotIn('.mark-alpha', body)

    def test_5_post_goes_to_the_named_task_and_current_stays(self):
        st, body = self.send_post('/api/iteration', {'from': 'it1', 'note': 'нова'},
                                  {'X-Canvas-Task': 'beta'})
        self.assertEqual(st, 200, body)
        self.assertEqual(json.loads(body)['iteration']['id'], 'it2')
        self.assertEqual([i['id'] for i in self._meta('beta')['iterations']], ['it1', 'it2'])
        self.assertEqual([i['id'] for i in self._meta('alpha')['iterations']], ['it1'],
                         'ітерація потрапила в поточну, а не названу задачу')
        self.assertTrue(os.path.isdir(os.path.join(self.dirs['beta'], 'iterations', 'it2')))
        self.assertFalse(os.path.isdir(os.path.join(self.dirs['alpha'], 'iterations', 'it2')))
        self.assertEqual(self._cfg()['current'], 'alpha', 'явна задача запиту перемкнула current')

    def test_6_task_for_is_pure_and_strict(self):
        # Названа задача мусить БУТИ на цій машині — тож у фікстурі справжні теки.
        a = {'title': 'A', 'dir': self.dirs['alpha']}
        b = {'title': 'B', 'dir': self.dirs['beta']}
        cfg = {'current': 'alpha', 'tasks': {'alpha': a, 'beta': b}}
        self.assertEqual(serve.task_for(cfg), ('alpha', a))
        self.assertEqual(serve.task_for(cfg, None), ('alpha', a))
        self.assertEqual(serve.task_for(cfg, 'beta'), ('beta', b))
        for bad in ('nope', '../x', '', 5, ['beta']):
            with self.subTest(bad=bad):
                with self.assertRaises(serve.UnknownTask):
                    serve.task_for(cfg, bad)

    # ---- прямі читачі `cfg['current']`: що мусить слухати запит, а що ні ----

    def test_7_preview_password_lands_in_the_named_task(self):
        """`_preview_password` читав `cfg['current']` напряму, повз `_current_task`
        — заголовок мовчки писав би пароль у поточну задачу."""
        st, body = self.send_post('/api/preview-password', {'password': 'tajne'},
                                  {'X-Canvas-Task': 'beta'})
        self.assertEqual(st, 200, body)
        tasks = self._cfg()['tasks']
        self.assertEqual(tasks['beta'].get('preview_password'), 'tajne')
        self.assertNotIn('preview_password', tasks['alpha'])

    def test_8_registry_endpoints_keep_machine_current_whatever_the_header(self):
        """`task-switch` / `/api/tasks` — про МАШИНУ, а не про запит: заголовок
        сесії не має ні перемикати чужу `current` на свою, ні ховати справжню."""
        st, body = self.get('/api/tasks', {'X-Canvas-Task': 'beta'})
        self.assertEqual(json.loads(body)['current'], 'alpha')
        st, body = self.send_post('/api/task-switch', {'id': 'beta'},
                                  {'X-Canvas-Task': 'alpha'})
        self.assertEqual(st, 200, body)
        self.assertEqual(self._cfg()['current'], 'beta')
        self.assertEqual(json.loads(body)['current'], 'beta')

    def test_9_missing_asset_404_says_named_for_an_explicit_task(self):
        st, body = self.get('/it-assets/it9/index.html')
        self.assertEqual(st, 404)
        self.assertIn('Поточна задача', body)
        self.assertNotIn('Названа задача', body)
        st, body = self.get('/t/beta/it-assets/it9/index.html')
        self.assertEqual(st, 404)
        self.assertIn('Названа задача', body)
        self.assertIn('beta', body)
        self.assertNotIn('перемкнулась', body,
                         'для явної задачі підказка «перемкнулась» — брехня')

    # ---- ревʼю: /commented, зʼємка, Origin, дрібниці ----

    def _base_href(self, html):
        m = re.search(r'<base href="([^"]+)">', html)
        self.assertIsNotNone(m, f'у сторінці нема <base href>: {html[:200]}')
        return m.group(1)

    def test_10_commented_under_a_named_task_is_bare_only(self):
        """`/commented` під названою задачею: коментатор пише піни на
        `/api/local-comments` БЕЗ префікса — тобто в `.dc-local-comments.json`
        ПОТОЧНОЇ задачі, хоч пін поставлено на сторінці названої. Тому дозволено
        лише `bare=1` (шлях зʼємки й pin-where, коментатора там нема), а `<base>`
        мусить нести префікс: відносні ассети сторінки інакше йдуть у ПОТОЧНУ."""
        from urllib.parse import urljoin
        for path, headers in (('/t/beta/commented?it=it1&bare=1', None),
                              ('/commented?it=it1&bare=1', {'X-Canvas-Task': 'beta'})):
            with self.subTest(path=path, headers=headers):
                st, html = self.get(path, headers)
                self.assertEqual(st, 200, html[:200])
                self.assertIn('<h1>beta</h1>', html)
                self.assertNotIn('CommentLayer.init', html)
                self.assertNotIn('local-adapter.js', html)
                base = self._base_href(html)
                self.assertEqual(base, f'{self.base}/t/beta/it-assets/it1/')
                # відносний ассет з `<base>` справді віддає файл названої задачі
                asset = urljoin(base, 'assets/x.css')
                st, css = self.get(asset[len(self.base):])
                self.assertEqual(st, 200)
                self.assertIn('.mark-beta', css)
        # без назви — як було: `<base>` без префікса, поточна задача
        st, html = self.get('/commented?it=it1&bare=1')
        self.assertEqual(self._base_href(html), f'{self.base}/it-assets/it1/')
        self.assertIn('<h1>alpha</h1>', html)

    def test_10b_commented_with_the_layer_is_refused_under_a_named_task(self):
        for path, headers in (('/t/beta/commented?it=it1', None),
                              ('/t/beta/commented?it=it1&bare=0', None),
                              ('/t/beta/commented?it=it1&ch=project', None),
                              ('/commented?it=it1', {'X-Canvas-Task': 'beta'})):
            with self.subTest(path=path, headers=headers):
                st, body = self.get(path, headers)
                self.assertEqual(st, 400)
                self.assertIn('коментування під названою задачею не підтримується', body)
                self.assertNotIn('CommentLayer', body)
                self.assertNotIn('local-adapter.js', body)
                self.assertNotIn('<h1>', body, 'макет віддано, хоч коментатора до нього не додано')
        # без назви коментатор на місці (відмова — лише для названої задачі)
        st, html = self.get('/commented?it=it1')
        self.assertEqual(st, 200)
        self.assertIn('local-adapter.js', html)

    def test_11_shoot_child_gets_the_task_prefix_in_its_url(self):
        """`bin/shoot.mjs` стукає назад за `${url}/api/iteration-pages`,
        `${url}/api/flow` і `${url}/commented?…&bare=1`. Без префікса в `--url`
        він питав би ПОТОЧНУ задачу, а кадри писав би в названу."""
        seen = []
        real_popen = subprocess.Popen

        def fake_popen(args, *a, **kw):
            if isinstance(args, (list, tuple)) and any(str(x).endswith('shoot.mjs') for x in args):
                seen.append(list(args))
                raise OSError('stub')    # далі — гілка «не вийшло запустити»
            return real_popen(args, *a, **kw)
        with mock.patch.object(serve, '_node_bin', return_value='/fake/node'), \
                mock.patch.object(serve.subprocess, 'Popen', fake_popen):
            st, body = self.send_post('/api/shoot', {'it': 'it1', 'check': True},
                                      {'X-Canvas-Task': 'beta'})
            self.assertEqual(st, 200, body)
            st, body = self.send_post('/t/alpha/api/shoot', {'it': 'it1', 'check': True})
            st, body = self.send_post('/api/shoot', {'it': 'it1', 'check': True})
        self.assertEqual(len(seen), 3, f'Popen не викликано як треба: {seen}')

        def arg(args, flag):
            return args[args.index(flag) + 1]
        base = f'http://127.0.0.1:{self.port}'
        self.assertEqual(arg(seen[0], '--url'), f'{base}/t/beta')
        self.assertEqual(arg(seen[0], '--dir'),
                         os.path.join(self.dirs['beta'], 'iterations', 'it1'))
        self.assertEqual(arg(seen[1], '--url'), f'{base}/t/alpha',
                         'названа задача, хоч і збігається з поточною, лишається названою')
        self.assertEqual(arg(seen[2], '--url'), base, 'без назви — адреса без префікса, як було')

    def test_12_foreign_origin_cannot_post_anywhere(self):
        """Префікс робить POST «простим запитом», який чужа вебсторінка шле без
        preflight, а Origin там перевіряли лише три обробники з тридцяти. Тепер
        перевірка одна, на вході `do_POST`: чужий Origin — 403 до будь-якого
        обробника (і до розбору задачі)."""
        before = (self._meta('alpha'), self._meta('beta'))
        evil = {'Origin': 'http://evil.example'}
        for path, headers in (('/t/beta/api/iteration', evil),
                              ('/api/iteration', evil),
                              ('/api/iteration', {**evil, 'X-Canvas-Task': 'beta'}),
                              ('/t/nope/api/iteration', evil),
                              ('/api/iteration', {'Origin': 'null'})):
            with self.subTest(path=path, headers=headers):
                st, body = self.send_post(path, {'from': 'it1'}, headers)
                self.assertEqual(st, 403, body)
                self.assertIn('foreign origin', body)
        self.assertEqual((self._meta('alpha'), self._meta('beta')), before)
        self.assertFalse(os.path.isdir(os.path.join(self.dirs['beta'], 'iterations', 'it2')))
        # свої — як було: без Origin (curl, мод Claude Code) і з локальним
        for origin in (None, 'http://localhost:8765', 'http://127.0.0.1:8765', 'http://[::1]:8765'):
            with self.subTest(origin=origin):
                headers = {'Origin': origin} if origin else {}
                st, body = self.send_post('/t/beta/api/iteration', {'from': 'it1'}, headers)
                self.assertEqual(st, 200, body)

    def test_13_prefix_beats_the_header(self):
        st, body = self.get('/t/beta/api/task', {'X-Canvas-Task': 'alpha'})
        self.assertEqual(json.loads(body)['id'], 'beta')

    def test_14_unknown_task_with_a_big_body_still_gets_its_404(self):
        """Відмова до читання тіла POST лишає його в буфері; закрите з непрочитаним
        — це RST, і клієнт міг би не побачити навіть 404 (ConnectionResetError)."""
        import http.client
        body = b'{"pad":"' + b'x' * 900_000 + b'"}'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request('POST', '/api/iteration', body,
                         {'Content-Type': 'application/json', 'X-Canvas-Task': 'nope'})
            r = conn.getresponse()
            self.assertEqual(r.status, 404)
            self.assertIn('nope', r.read().decode('utf-8', 'replace'))
        finally:
            conn.close()

    def test_15_the_app_ui_is_not_task_scoped(self):
        """`/t/beta/app/` відкрив би той самий канвас ПОТОЧНОЇ задачі під адресою
        beta — адреса брехала б. Інтерфейс не привʼязаний до задачі."""
        st, body = self.get('/app/')
        self.assertEqual(st, 200)
        for path in ('/t/beta/app/', '/t/beta/app/index.html', '/t/beta/app'):
            with self.subTest(path=path):
                st, body = self.get(path)
                self.assertEqual(st, 404)

    def test_16_task_vanishing_mid_request_gives_a_404_not_a_dropped_connection(self):
        """Названу задачу вилучили між входом запиту й текстом 404: збірка тексту
        не сміє впасти (відповіді не було б взагалі) — `who` стає «—», як і в
        випадку зниклої поточної."""
        calls = [('beta', {}), serve.UnknownTask('beta')]
        with mock.patch.object(serve.Handler, '_current_task', side_effect=calls):
            st, body = self.get('/t/beta/it-assets/it1/index.html')
        self.assertEqual(st, 404)
        self.assertIn('Названа задача — —', body)

    def test_17_referer_task_does_not_leak_into_a_request_without_a_prefix(self):
        """Задачу з Referer ставить запиту викликач, і лише для корене-абсолютного
        ассета: звичайний запит із чужим Referer не міняє, чия це задача."""
        ref = f'{self.base}/t/beta/it-assets/it1/index.html'
        st, body = self.get('/api/task', {'Referer': ref})
        self.assertEqual(json.loads(body)['id'], 'alpha')

    # ---- ревʼю ч.2: задача без теки, реєстр, порожній заголовок ----

    def _with_registry_only_tasks(self):
        """Додати до реєстру `nodir` (запису `dir` нема взагалі) і `gone` (`dir`
        є, теки на диску нема). Реєстр їде в git, теки — ні: так виглядає задача
        колеги на цій машині. Повертає шлях `gone`."""
        cfg = self._cfg()
        gone = os.path.join(self.root, 'gone')
        cfg['tasks']['nodir'] = {'title': 'Без теки'}
        cfg['tasks']['gone'] = {'dir': gone, 'title': 'Зникла'}
        with open(self.tasks_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)
        return gone

    def test_18_task_not_on_this_machine_is_a_clean_404_and_creates_nothing(self):
        """Названа задача без `dir` валила обробник `KeyError: 'dir'` і рвала
        зʼєднання; названа з `dir`, якої нема на диску, пропускалась далі — і
        `POST /t/gone/api/iteration` САМ створював дерево теки. Тепер — 404 JSON
        із причиною, а на диску й у реєстрі нічого не змінюється."""
        gone = self._with_registry_only_tasks()
        registry_before = open(self.tasks_file, 'rb').read()
        metas_before = (self._meta('alpha'), self._meta('beta'))
        for tid in ('nodir', 'gone'):
            want = {'ok': False, 'error': f'task not on this machine: {tid}'}
            for path, headers in ((f'/t/{tid}/api/task', None),
                                  ('/api/task', {'X-Canvas-Task': tid}),
                                  (f'/t/{tid}/it-assets/it1/index.html', None),
                                  (f'/t/{tid}/commented?it=it1&bare=1', None),
                                  ('/it-assets/it1/index.html', {'X-Canvas-Task': tid})):
                with self.subTest(method='GET', path=path, headers=headers):
                    st, body = self.get(path, headers)
                    self.assertEqual(st, 404)
                    self.assertEqual(json.loads(body), want)
                    self.assertNotIn('alpha', body, 'відкат на поточну задачу')
            for path, headers in ((f'/t/{tid}/api/iteration', None),
                                  ('/api/iteration', {'X-Canvas-Task': tid}),
                                  (f'/t/{tid}/api/iteration-delete', None)):
                with self.subTest(method='POST', path=path, headers=headers):
                    st, body = self.send_post(path, {'from': 'it1', 'id': 'it1'}, headers)
                    self.assertEqual(st, 404)
                    self.assertEqual(json.loads(body), want)
        self.assertFalse(os.path.exists(gone), 'POST створив теку задачі, якої тут нема')
        self.assertEqual((self._meta('alpha'), self._meta('beta')), metas_before)
        self.assertEqual(open(self.tasks_file, 'rb').read(), registry_before)
        # невідома задача лишається ІНШОЮ відмовою: «нема в реєстрі» ≠ «нема теки»
        st, body = self.get('/t/nope/api/task')
        self.assertEqual(json.loads(body)['error'], 'unknown task: nope')

    def test_18b_not_on_this_machine_with_a_big_body_still_gets_its_404(self):
        """Відмова до читання тіла POST — як і для невідомої: тіло вичитується,
        інакше закрите зʼєднання з ним у буфері — RST замість 404."""
        import http.client
        self._with_registry_only_tasks()
        body = b'{"pad":"' + b'x' * 900_000 + b'"}'
        for path, headers in (('/api/iteration', {'X-Canvas-Task': 'nodir'}),
                              ('/t/gone/api/iteration', {})):
            with self.subTest(path=path):
                conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
                try:
                    conn.request('POST', path, body,
                                 {'Content-Type': 'application/json', **headers})
                    r = conn.getresponse()
                    self.assertEqual(r.status, 404)
                    self.assertIn('task not on this machine', r.read().decode('utf-8'))
                finally:
                    conn.close()

    def test_18c_referer_naming_a_task_not_here_is_ignored_like_an_unknown_one(self):
        self._with_registry_only_tasks()
        ref = f'{self.base}/t/nodir/it-assets/it1/index.html'
        st, body = self.get('/assets/x.css', {'Referer': ref})
        self.assertEqual(st, 404)
        self.assertNotIn('.mark-alpha', body)

    def test_18d_task_for_raises_task_not_here_only_for_a_named_task(self):
        d = self.dirs['alpha']
        cfg = {'current': 'cur', 'tasks': {
            'cur': {'title': 'C'},                      # поточна без dir — як було
            'ok': {'dir': d},
            'nodir': {'title': 'N'},
            'none': {'dir': None}, 'num': {'dir': 5}, 'blank': {'dir': ''},
            'gone': {'dir': os.path.join(self.root, 'no-such-dir')},
            'file': {'dir': os.path.join(d, 'iterations.json')}}}   # файл, не тека
        self.assertTrue(issubclass(serve.TaskNotHere, serve.UnknownTask))
        self.assertEqual(serve.task_for(cfg), ('cur', {'title': 'C'}),
                         'поточна задача (ніхто не названий) змінила поведінку')
        self.assertEqual(serve.task_for(cfg, 'ok'), ('ok', {'dir': d}))
        for tid in ('nodir', 'none', 'num', 'blank', 'gone', 'file'):
            with self.subTest(tid=tid):
                with self.assertRaises(serve.TaskNotHere):
                    serve.task_for(cfg, tid)
        # невідома — НЕ «нема тут»: це різні відмови
        with self.assertRaises(serve.UnknownTask) as ctx:
            serve.task_for(cfg, 'nope')
        self.assertNotIsInstance(ctx.exception, serve.TaskNotHere)

    def test_19_task_new_takes_no_header_the_new_id_is_not_registered_yet(self):
        """`X-Canvas-Task: <новий id>` на `task-new` давав 404 «невідома задача»:
        id ще не в реєстрі, бо саме його й створюють. Реєстр — про машину, а не
        про дані задачі, тож заголовок там не береться й не перевіряється."""
        for tid in ('gamma', 'delta'):
            self.addCleanup(shutil.rmtree, os.path.join(self.cfgdir, tid), True)
        st, body = self.send_post('/api/task-new',
                                  {'id': 'gamma', 'title': 'Гамма', 'profile': 'tool'},
                                  {'X-Canvas-Task': 'gamma'})
        self.assertEqual(st, 200, body)
        self.assertEqual(json.loads(body)['id'], 'gamma')
        self.assertIn('gamma', self._cfg()['tasks'])
        self.assertTrue(os.path.isfile(
            os.path.join(self.cfgdir, 'gamma', 'iterations', 'it1', 'index.html')))
        # заголовок не про створювану задачу — теж не береться
        st, body = self.send_post('/api/task-new',
                                  {'id': 'delta', 'title': 'Дельта', 'profile': 'tool'},
                                  {'X-Canvas-Task': 'nope'})
        self.assertEqual(st, 200, body)
        self.assertIn('delta', self._cfg()['tasks'])

    def test_19b_task_switch_with_a_header_still_switches_to_the_body_id(self):
        for header in ('alpha', 'nope', 'nodir'):
            with self.subTest(header=header):
                cfg = {**self._cfg(), 'current': 'alpha'}   # читаємо ДО відкриття на запис
                with open(self.tasks_file, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f)
                st, body = self.send_post('/api/task-switch', {'id': 'beta'},
                                          {'X-Canvas-Task': header})
                self.assertEqual(st, 200, body)
                self.assertEqual(self._cfg()['current'], 'beta')

    def test_20_the_prefix_form_makes_no_sense_on_registry_routes(self):
        """`/t/x/api/task-new` — безглуздя: реєстр не привʼязаний до задачі.
        Відмова 400 (а не 404 «невідома» чи мовчки виконати без префікса), і
        нічого не створено / не перемкнено."""
        before = open(self.tasks_file, 'rb').read()
        for path in ('/t/x/api/task-new', '/t/alpha/api/task-new',
                     '/t/beta/api/task-switch', '/t/nope/api/task-switch'):
            with self.subTest(path=path):
                st, body = self.send_post(path, {'id': 'beta', 'title': 'T',
                                                 'profile': 'tool'})
                self.assertEqual(st, 400, body)
                self.assertFalse(json.loads(body)['ok'])
                self.assertIn('реєстр задач не привʼязаний', json.loads(body)['error'])
        self.assertEqual(open(self.tasks_file, 'rb').read(), before)
        self.assertFalse(os.path.exists(os.path.join(self.cfgdir, 'x')))
        # звичайні маршрути з префіксом — як було (200 для відомої)
        st, _ = self.get('/t/beta/api/task')
        self.assertEqual(st, 200)

    def test_21_blank_task_header_is_a_400_not_the_current_task(self):
        """`X-Canvas-Task:` порожній — це «назву дали, а вона порожня», а не
        «назви нема». Мовчки читати його як «нема» = бити в поточну задачу, від
        чого весь механізм і захищає."""
        before = (self._meta('alpha'), self._meta('beta'))
        for value in ('', '   '):
            with self.subTest(value=value):
                st, body = self.get('/api/task', {'X-Canvas-Task': value})
                self.assertEqual(st, 400)
                self.assertEqual(json.loads(body),
                                 {'ok': False, 'error': 'empty X-Canvas-Task'})
                st, body = self.send_post('/api/iteration', {'from': 'it1'},
                                          {'X-Canvas-Task': value})
                self.assertEqual(st, 400)
                self.assertEqual(json.loads(body),
                                 {'ok': False, 'error': 'empty X-Canvas-Task'})
        self.assertEqual((self._meta('alpha'), self._meta('beta')), before)
        self.assertFalse(os.path.isdir(os.path.join(self.dirs['alpha'], 'iterations', 'it2')))
        # без заголовка — поточна, як було; префікс сильніший за заголовок
        self.assertEqual(json.loads(self.get('/api/task')[1])['id'], 'alpha')
        st, body = self.get('/t/beta/api/task', {'X-Canvas-Task': ''})
        self.assertEqual((st, json.loads(body)['id']), (200, 'beta'))

    def test_21b_blank_header_with_a_big_body_still_gets_its_400(self):
        import http.client
        body = b'{"pad":"' + b'x' * 900_000 + b'"}'
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request('POST', '/api/iteration', body,
                         {'Content-Type': 'application/json', 'X-Canvas-Task': ''})
            r = conn.getresponse()
            self.assertEqual(r.status, 400)
            self.assertIn('empty X-Canvas-Task', r.read().decode('utf-8'))
        finally:
            conn.close()


def current_reads(source):
    """Усі прямі читання/записи `current` реєстру в тексті модуля: список
    `(рядок, найближча функція, у якому /api/tasks…-блоці)`. Дивиться в AST, а не
    в рядки: `'current'` у докстрінгах, ключах відповіді (`{'current': …}`) і
    значеннях `state` — не звернення до реєстру, а grep їх не відрізнив би.

    Звернення — це `x['current']` (будь-який контекст) і `x.get/pop/setdefault
    ('current', …)`. «Найближча функція» — за іменем; для `do_GET` (один великий
    обробник) додатково — чи стоїть звернення у тілі `if`, що перевіряє шлях
    `/api/tasks` чи `/api/tasks-overview`."""
    import ast

    def is_current(node):
        if isinstance(node, ast.Subscript):
            return isinstance(node.slice, ast.Constant) and node.slice.value == 'current'
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ('get', 'pop', 'setdefault') and node.args):
            return isinstance(node.args[0], ast.Constant) and node.args[0].value == 'current'
        return False

    def lists_tasks(test):
        return any(isinstance(n, ast.Constant) and n.value in ('/api/tasks',
                                                               '/api/tasks-overview')
                   for n in ast.walk(test))

    hits = []

    def visit(node, func, in_listing):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func, in_listing = node.name, False
        if is_current(node):
            hits.append((node.lineno, func, in_listing))
        for field, value in ast.iter_fields(node):
            kids = value if isinstance(value, list) else [value]
            for kid in kids:
                if isinstance(kid, ast.AST):
                    # лише ТІЛО `if` із шляхом реєстру; `else`/`elif` — вже чужі обробники
                    inside = in_listing or (isinstance(node, ast.If) and field == 'body'
                                            and lists_tasks(node.test))
                    visit(kid, func, inside)

    visit(ast.parse(source), None, False)
    return sorted(hits)


def spaces_current_uses(source):
    """Усі звернення до `current` реєстру ПРОСТОРІВ через модуль `spaces`: `spaces.current_id` і
    `spaces.space_current_task` (виклик ЧИ посилання — `cur = spaces.current_id` теж звернення).
    Список `(рядок, найближча функція, імʼя)`. Дивиться в AST: `current_reads` ловить лише ключ
    `'current'`, а ці дві функції віддають його, не називаючи, — і обробник, що кличе їх повз
    `task_for`, б'є в поточну задачу тим самим способом, що й `cfg['current']`."""
    import ast
    hits = []

    def visit(node, func):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node.name
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == 'spaces'
                and node.attr in ('current_id', 'space_current_task')):
            hits.append((node.lineno, func, node.attr))
        for kid in ast.iter_child_nodes(node):
            visit(kid, func)

    visit(ast.parse(source), None)
    return sorted(hits)


class CurrentTaskReadGuard(unittest.TestCase):
    """`tasks.json` → `current` — ОДИН на машину, і паралельна сесія його
    перемикає. Тому читати його напряму не можна ніде, крім реєстру: задачу запиту
    дає `task_for` (через `Handler._current_task()`), інакше обробник мовчки б'є в
    ЧУЖУ задачу — це й була вада fb-07102026-e627c2. Перший прохід пропустив
    `_preview_password`, що читав `cfg['current']` повз `_current_task`; цей
    охоронець ловить наступного такого."""

    #: функції реєстру, що ЗВІДСИ мають право торкатись `current`
    ALLOWED = ('task_for', 'task_new', '_task_switch')

    def _violations(self, source):
        return [(line, func) for line, func, listing in current_reads(source)
                if not (func in self.ALLOWED or (func == 'do_GET' and listing))]

    def test_serve_reads_current_only_through_task_for_and_the_registry_routes(self):
        with open(serve.__file__, encoding='utf-8') as f:
            source = f.read()
        bad = self._violations(source)
        self.assertEqual(
            bad, [],
            'пряме читання `current` поза task_for/task_new/_task_switch і поза '
            'обробниками /api/tasks, /api/tasks-overview (рядок, функція): '
            f'{bad}. Задачу запиту бери через `task_for(cfg, tid)` / '
            '`self._current_task()`: `current` один на машину і міг перемкнутись.')

    def test_the_scan_sees_the_real_registry_reads(self):
        """Охоронець, що нічого не бачить, нічого й не ловить: усі дозволені
        місця серед знайдених, і обидва /api/tasks-обробники теж."""
        with open(serve.__file__, encoding='utf-8') as f:
            hits = current_reads(f.read())
        self.assertEqual({func for _, func, _ in hits if func != 'do_GET'},
                         set(self.ALLOWED))
        self.assertEqual(sum(1 for _, func, listing in hits if func == 'do_GET' and listing), 2)
        self.assertEqual([h for h in hits if h[1] == 'do_GET' and not h[2]], [])

    def test_the_scan_flags_a_direct_read_in_another_handler(self):
        """Самоперевірка сканера на синтетичному коді: кожна форма звернення, у
        будь-якій функції, крім дозволених, — порушення; дозволені — ні."""
        src = (
            "def task_for(cfg):\n    return cfg['current']\n"
            "class H:\n"
            "    def _publish(self):\n        cfg = load()\n        return cfg['current']\n"
            "    def _other(self, cfg):\n        return cfg.get('current')\n"
            "    def _third(self, cfg):\n        cfg['current'] = 'x'\n"
            "    def _fourth(self, cfg):\n        return cfg.pop('current', None)\n"
            "    def _docs(self, cfg):\n"
            "        'current'\n        return {'current': 1, 'state': 'current'}\n"
            "    def do_GET(self):\n"
            "        if self.path == '/api/tasks':\n            return cfg.get('current')\n"
            "        elif self.path == '/api/x':\n            return cfg.get('current')\n"
            "        if self.path == '/api/y':\n            return cfg['current']\n")
        got = {(func, line) for line, func in self._violations(src)}
        self.assertEqual(got, {('_publish', 6), ('_other', 8), ('_third', 10),
                               ('_fourth', 12), ('do_GET', 20), ('do_GET', 22)})

    #: Функції serve.py, яким дозволено питати `spaces` про `current` реєстру, і ЩО саме. Кожна — не
    #: обробник даних задачі: `_pin_current_space` фіксує простір запиту на вході, `task_anywhere`
    #: — CLI-шлях без запиту, `_space_switch` віддає поточну задачу щойно перемкненого простору.
    SPACES_CURRENT_ALLOWED = {('_pin_current_space', 'current_id'), ('task_anywhere', 'current_id'),
                              ('_space_switch', 'space_current_task')}

    def _spaces_violations(self, source):
        return [(line, func, name) for line, func, name in spaces_current_uses(source)
                if (func, name) not in self.SPACES_CURRENT_ALLOWED]

    def test_serve_asks_spaces_for_the_current_only_in_the_allowed_functions(self):
        with open(serve.__file__, encoding='utf-8') as f:
            bad = self._spaces_violations(f.read())
        self.assertEqual(
            bad, [],
            'звернення до `spaces.current_id`/`spaces.space_current_task` поза дозволеними функціями '
            f'(рядок, функція, імʼя): {bad}. Поточну задачу запиту дає `task_for` / '
            '`self._current_task()`, поточний простір запиту — `spaces.active_space()`.')

    def test_the_spaces_scan_sees_exactly_the_allowed_calls(self):
        """Свідок проти вакууму: сканер знаходить кожне дозволене звернення й нічого зайвого."""
        with open(serve.__file__, encoding='utf-8') as f:
            hits = spaces_current_uses(f.read())
        self.assertEqual({(func, name) for _, func, name in hits}, self.SPACES_CURRENT_ALLOWED)

    def test_the_spaces_scan_flags_a_stray_call_or_reference(self):
        src = (
            "def _pin_current_space(self):\n    spaces.current_id()\n"
            "def task_anywhere():\n    spaces.current_id()\n"
            "class H:\n"
            "    def _space_switch(self):\n        return spaces.space_current_task('x')\n"
            "    def _publish(self):\n        return spaces.current_id()\n"
            "    def _other(self):\n        f = spaces.space_current_task\n        return f('x')\n"
            "    def _swapped(self):\n        return spaces.space_current_task('x')\n"
            "    def _pin_current_space(self):\n        return spaces.space_current_task('x')\n"
            "    def _fine(self):\n        return spaces.active_space() or spaces.layer_on() or other.current_id()\n")
        got = {(func, name) for _, func, name in self._spaces_violations(src)}
        self.assertEqual(got, {('_publish', 'current_id'), ('_other', 'space_current_task'),
                               ('_swapped', 'space_current_task'),
                               ('_pin_current_space', 'space_current_task')})


if __name__ == '__main__':
    unittest.main()
