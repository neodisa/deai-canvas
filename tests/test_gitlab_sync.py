"""Синхронізація з GitLab: чесність відбитка «✓» на справжньому git.

Ці тести зʼявились після реального інциденту (03.08.2026): макет `bgSanctions`
12 днів не їхав з машини, а канвас показував «GitLab · Іт.1 ✓». Складались три
бага, кожен окремо виглядав безпечним:

1. `_behind_count` рахував відставання ЛИШЕ по теці задачі → коміт мимо
   `mockup/<tid>` (CI-конфіг, чужа задача) давав behind=0, guard не спрацьовував;
2. `git push` відбивався non-fast-forward, і обробки цього не було;
3. відбиток «синхронізовано» писався по `ok`, а не по факту пуша.

Тести навмисно ганяють РЕАЛЬНИЙ git по локальних теках (без мережі): саме на
стику з git баг і жив, а мок-обʼєкти його б не зловили.

Етап 4a: git тепер виконує модуль `git-sync` (роль `vcs`), а ядро кличе його через старі імена (`gitlab_sync`/
`gitlab_pull`/`gitlab_status`/`autosync`) з ціллю `gl`. Тут — поведінка ЛІГИ (явний запис `git-sync` із `compat = design-canvas`, 4d-4b) на тих
самих сценаріях; внутрішні лічильники й транспорт (`_behind_count`, `ensure_mirror`, `_git`…) переїхали в модуль і
`tests/test_git_sync_module.py`, а лічильники в тестах нижче читає прямий git у теці дзеркала.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from liga_fixture import LigaFixture  # noqa: E402


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


class GitlabSyncHonesty(unittest.TestCase):
    """Кожен тест — свій ізольований origin+дзеркало+задача."""

    #: Оточення git: глобальний конфіг людини (`~/.gitconfig`: підпис комітів, `insteadOf`) тест не читає, мережі нема.
    _GIT_ENV = {'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_SSH_COMMAND': 'false'}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='dc-syncverify-')
        self._saved_git_env = {k: os.environ.get(k) for k in self._GIT_ENV}
        os.environ.update(self._GIT_ENV)
        os.environ['DC_MIRRORS_DIR'] = os.path.join(self.tmp, 'mirrors')
        # ⛔ КОНФІГ ЗАДАЧ — теж у тимчасову теку, і це не перестраховка.
        # 15.09.2026 тест, який кличе `task_new`, записав фікстуру ПОВЕРХ
        # робочого `tasks.json` дизайнера: 21 задача зникла посеред його
        # робочого дня, лишилась одна, що вказує в /var/folders. `task_new`
        # кличе `save_tasks()`, а той пише в `tasks_path()` — тобто в ЖИВИЙ
        # файл, якщо `DC_TASKS_FILE` не заданий. Наявний охоронець
        # `LiveConfigUntouched` цього не спіймав: він стереже конфіг лише
        # навколо `ServeTest`, а `unittest discover` бере файли за абеткою і
        # `test_gitlab_sync` іде ПЕРШИМ.
        os.environ['DC_TASKS_FILE'] = os.path.join(self.tmp, 'tasks.json')
        # Файл мусить ІСНУВАТИ: `save_tasks` спершу робить `.bak` копією
        # наявного, і на порожньому місці падає копіюванням.
        with open(os.environ['DC_TASKS_FILE'], 'w', encoding='utf-8') as fh:
            json.dump({'tasks': {}, 'current': None}, fh)
        # serve читає DC_MIRRORS_DIR на кожен виклик (`_mirrors_base`), тому імпорт тут безпечний
        import serve
        self.serve = serve
        # 4d-4b (R2): неявного постачальника ЛІГИ нема — стенд веде ЯВНИЙ запис `git-sync` (`compat = design-canvas`) у тимчасовому домі
        # (`LigaFixture` підміняє `HOME`/`DEAI_HOME`). Ізоляцію (`DC_TASKS_FILE`) лишаємо: `ctx` фіксований, як був у неявного.
        fx = LigaFixture(self, tmp=self.tmp)
        fx.tasks_path = os.environ['DC_TASKS_FILE']
        fx.env(DC_TASKS_FILE=fx.tasks_path, DC_MIRRORS_DIR=os.environ['DC_MIRRORS_DIR'], **self._GIT_ENV)
        fx.build(roles=('vcs',), overrides={'vcs': {'settings': {'ssh_key': '', 'host_ip': ''}}}).fix_space()
        with open(fx.tasks_path, 'w', encoding='utf-8') as fh:
            json.dump({'tasks': {}, 'current': None}, fh)

        self.origin = os.path.join(self.tmp, 'origin.git')
        os.makedirs(self.origin)
        sh(['git', 'init', '--bare', '-b', 'main', '.'], self.origin)

        # «чужа» робоча копія — нею імітуємо колегу / CI
        self.peer = os.path.join(self.tmp, 'peer')
        os.makedirs(self.peer)
        sh(['git', 'init', '-b', 'main', '.'], self.peer)
        sh(['git', 'config', 'user.email', 'peer@test'], self.peer)
        sh(['git', 'config', 'user.name', 'Peer'], self.peer)
        self._write(os.path.join(self.peer, 'README.md'), 'seed\n')
        sh(['git', 'add', '-A'], self.peer)
        sh(['git', 'commit', '-qm', 'seed'], self.peer)
        sh(['git', 'remote', 'add', 'origin', self.origin], self.peer)
        sh(['git', 'push', '-q', 'origin', 'main'], self.peer)

        self.task_dir = os.path.join(self.tmp, 'task')
        self.it1 = os.path.join(self.task_dir, 'iterations', 'it1')
        os.makedirs(self.it1)
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v1</h1>')
        self._save_meta({'iterations': [{'id': 'it1'}], 'current': 'it1'})
        self.task = {'dir': self.task_dir, 'title': 'Тест'}
        self.gl = {'repo': self.origin, 'path': 'mockup/t1',
                   'branch': 'main', 'ssh_key': None}

    def tearDown(self):
        os.environ.pop('DC_MIRRORS_DIR', None)
        os.environ.pop('DC_TASKS_FILE', None)
        for k, v in self._saved_git_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- хелпери ----
    @staticmethod
    def _write(path, text):
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)

    def _meta_path(self):
        return os.path.join(self.task_dir, 'iterations.json')

    def _save_meta(self, meta):
        with open(self._meta_path(), 'w', encoding='utf-8') as fh:
            json.dump(meta, fh, ensure_ascii=False)

    def _meta(self):
        with open(self._meta_path(), encoding='utf-8') as fh:
            return json.load(fh)

    def _sync(self, it='it1', record=True):
        r = self.serve.gitlab_sync('t1', self.task, self.gl, it)
        if record and r.get('synced'):
            self.serve._record_sync(self.task, it, r.get('sha'))
        return r

    @staticmethod
    def rev_count(md, rng):
        """Скільки комітів у діапазоні — прямий git у теці дзеркала (лічильники ядра переїхали в модуль)."""
        r = sh(['git', 'rev-list', '--count', rng], md)
        assert r.returncode == 0, r.stderr
        return int(r.stdout.strip())

    def _peer_commit(self, rel, text, msg):
        """Коміт колеги/CI в origin. Обовʼязково з pull, інакше push відбʼється."""
        sh(['git', 'pull', '-q', '--ff-only', 'origin', 'main'], self.peer)
        path = os.path.join(self.peer, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._write(path, text)
        sh(['git', 'add', '-A'], self.peer)
        sh(['git', 'commit', '-qm', msg], self.peer)
        p = sh(['git', 'push', '-q', 'origin', 'main'], self.peer)
        self.assertEqual(p.returncode, 0, f'peer push failed: {p.stderr}')

    # ---- тести ----
    def test_first_sync_pushes_and_marks_synced(self):
        r = self._sync()
        self.assertTrue(r['synced'])
        self.assertTrue(r['pushed'])

    def _mirror_readme(self):
        md = self.serve.vcs_mirror_dir(self.gl)
        with open(os.path.join(md, 'mockup/t1', 'README.md'), encoding='utf-8') as fh:
            return fh.read()

    def test_readme_shows_depth_as_indentation_and_folders_as_rows_without_a_dir(self):
        """README мультисторінкового макета — таблиця «Тека | Сторінка»: глибина —
        відступом (`&emsp;`: звичайні пробіли на початку комірки GFM обрізає, і
        глибина зникла б), тека — рядком БЕЗ теки (`—`): на диску її нема, і `p/` у
        колонці «Тека» вів би в нікуди. Раніше стояв `↳ ` на будь-якій глибині й
        тека з `isGroup` випадала зі списку."""
        self._write(os.path.join(self.it1, 'pages.json'), json.dumps({'pages': [
            {'id': 'p', 'name': 'Картка', 'kind': 'page', 'children': [
                {'id': 'w', 'name': 'Віджет', 'kind': 'folder', 'children': [
                    {'id': 's', 'name': 'Помилка', 'kind': 'state'}]}]},
            {'id': 'q', 'name': 'Особа |\n  тест', 'kind': 'page'}]}, ensure_ascii=False))
        for d in ('p', 's', 'q'):
            os.makedirs(os.path.join(self.it1, d))
            self._write(os.path.join(self.it1, d, 'index.html'), '<h1>x</h1>')
        self.assertTrue(self._sync()['synced'])
        readme = self._mirror_readme()
        self.assertIn('| Тека | Сторінка |\n|---|---|\n' + '\n'.join([
            '| `p/` | Картка |',
            '| — | &emsp;📁 Віджет |',
            '| `s/` | &emsp;&emsp;Помилка |',
            '| `q/` | Особа / тест |']) + '\n', readme)
        self.assertNotIn('↳', readme)

    def test_readme_is_not_written_for_a_single_openable_page(self):
        """Тека без сторінок не робить макет «мультисторінковим»: умова — за
        відкриваними вузлами, а не за кількістю рядків."""
        self._write(os.path.join(self.it1, 'pages.json'), json.dumps({'pages': [
            {'id': 'f', 'name': 'Тека', 'kind': 'folder', 'children': [
                {'id': 'a', 'name': 'А', 'kind': 'page'}]}]}, ensure_ascii=False))
        os.makedirs(os.path.join(self.it1, 'a'))
        self._write(os.path.join(self.it1, 'a', 'index.html'), '<h1>x</h1>')
        self.assertTrue(self._sync()['synced'])
        md = self.serve.vcs_mirror_dir(self.gl)
        self.assertFalse(os.path.exists(os.path.join(md, 'mockup/t1', 'README.md')))

    def test_sync_puts_author_into_state_file(self):
        """`.canvas-state.json` — ЗАЯВА автора. Саме її читає канвас колеги.

        ⛔ Не `git log -1 --format=%an`: лог це властивість КОМІТА, і на
        ребейсі, чужому мерджі або пуші з CI він розходиться з тим, хто справді
        робив макет. Лог лишається запасним шляхом для станів старої версії.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Ольга Сидорук'
        os.environ['DC_IDENTITY_EMAIL'] = 'designer2@example.com'
        try:
            self._sync()
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)
        md = self.serve.vcs_mirror_dir(self.gl)
        with open(os.path.join(md, 'mockup/t1', '.canvas-state.json'),
                  encoding='utf-8') as fh:
            state = json.load(fh)
        self.assertEqual(state['author'], 'Ольга Сидорук')
        self.assertEqual(state['author_key'], 'designer2@example.com')

    def test_foreign_commit_outside_our_path_is_caught_up_not_blocked(self):
        """Коміт мимо нашої теки — НЕ привід блокувати, але привід наздогнати.

        Історія в двох кроках. Спершу guard рахував behind лише по теці задачі —
        і CI-коміт у `.gitlab-ci.yml` давав behind=0: дзеркало йшло в
        non-fast-forward, push відбивався НАЗАВЖДИ. Тоді guard розширили на весь
        репозиторій, і блокування стало чесним, але надто широким: 90% блокувань
        казали «тебе обігнали» там, де теку задачі ніхто не чіпав, а перший пуш
        НОВОЇ задачі взагалі заходив у глухий кут (pull падав із
        `path mockup/<id> not found in repo`).

        Тепер два різні стани: «репо попереду» — наздоганяємо дзеркало самі
        (`merge --ff-only`) і пушимо; «ТЕКА ЗАДАЧІ попереду» — блокуємо.
        Інваріант, заради якого guard і писався, лишається той самий і
        перевіряється тут явно: до пуша дзеркало НЕ відстає.
        """
        self._sync()
        self._peer_commit('.gitlab-ci.yml', 'ci: x\n', 'ci: not our path')
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v2</h1>')

        r = self._sync()
        self.assertIsNone(r.get('blocked'), f'чужий коміт мимо теки заблокував пуш: {r}')
        self.assertTrue(r['synced'])
        md = self.serve.vcs_mirror_dir(self.gl)
        self.assertEqual(self.rev_count(md, 'main..origin/main'), 0,
                         'дзеркало лишилось позаду — саме це й ламало push назавжди')

    def test_first_push_of_a_new_task_is_not_deadlocked(self):
        """Глухий кут із фідбеку 04.09.2026 (LIGA-7011).

        Теки задачі на origin ще немає, але в репо є чужі коміти. Старий guard
        блокував пуш («на GitLab новіше»), а `gitlab_pull` падав із
        `path mockup/<id> not found in repo` — вийти можна було ЛИШЕ вручну,
        `git merge --ff-only` у теці дзеркала. Перший пуш нової задачі був
        неможливий у принципі.
        """
        # Дзеркало вже існує й відстало — але нашої теки на origin немає ніколи.
        self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')      # клон + fetch
        self._peer_commit('.gitlab-ci.yml', 'ci: x\n', 'ci: not our path')

        r = self._sync()
        self.assertTrue(r['synced'], f'перший пуш нової задачі заблоковано: {r}')
        self.assertTrue(r.get('pushed'))

    def test_commit_into_our_path_still_blocks(self):
        """Зворотний бік: коли теку задачі СПРАВДІ оновили, пуш поверх —
        це мовчазне затирання чужого макета, і його треба спинити."""
        self._sync()
        self._peer_commit('mockup/t1/index.html', '<h1>чуже</h1>', 'колега правив макет')
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v2</h1>')

        r = self._sync()
        self.assertEqual(r.get('blocked'), 'behind')
        self.assertFalse(r.get('synced'))
        self.assertGreater(r.get('behind_path', 0), 0,
                           'блокування мусить казати, що попереду саме ТЕКА ЗАДАЧІ')

    def test_pull_of_unchanged_content_creates_no_iteration(self):
        """Pull не сміє плодити копію того, що вже лежить локально.

        Кейс lu-home (09.09.2026): вміст `mockup/<id>` на origin був байт-у-байт
        мій, але guard блокував пуш («у репо новіше»), і щоб його зняти,
        доводилось тиснути «Підтягнути». Той створював it2 = точну копію
        СТАРОГО стану, і вона ставала «останньою»: канвас за перезавантаженням
        відкривав саме її, `state.py` писав «ПРОДОВЖУЄМО з Іт.2», а autosync
        вибирає робочу ітерацію за mtime — тобто був шанс відправити старий
        макет. Прибрати артефакт користувач не міг: `iteration-delete`
        справедливо блокує руйнівну дію.
        """
        self._sync()                      # origin = наш it1, байт-у-байт
        before = [i['id'] for i in self._meta()['iterations']]

        r = self.serve.gitlab_pull(self.task, self.gl)

        self.assertTrue(r['ok'])
        self.assertTrue(r.get('unchanged'), f'pull не впізнав власний вміст: {r}')
        self.assertIsNone(r.get('iteration'))
        self.assertEqual([i['id'] for i in self._meta()['iterations']], before,
                         'зʼявилась ітерація-копія того, що вже було')

    def test_pull_of_changed_content_still_creates_an_iteration(self):
        """Зворотний бік: справжнє чуже оновлення мусить приїхати ітерацією.

        Без цієї половини найпростіша «правка» — не створювати ітерацію ніколи —
        виглядала б як успіх, а чужа робота просто не доїжджала б.
        """
        self._sync()
        self._peer_commit('mockup/t1/index.html', '<h1>чуже</h1>', 'колега правив макет')

        r = self.serve.gitlab_pull(self.task, self.gl)

        self.assertTrue(r['ok'])
        self.assertFalse(r.get('unchanged'))
        self.assertEqual(r['iteration']['id'], 'it2')

    def _peer_push_with_state(self, html, author, key, source_it='it3'):
        """Коміт колеги РАЗОМ із його `.canvas-state.json` — так виглядає
        справжня передача, а не просто чужий файл у репо."""
        sh(['git', 'pull', '-q', '--ff-only', 'origin', 'main'], self.peer)
        d = os.path.join(self.peer, 'mockup/t1')
        os.makedirs(d, exist_ok=True)
        self._write(os.path.join(d, 'index.html'), html)
        self._write(os.path.join(d, '.canvas-state.json'), json.dumps(
            {'task': 't1', 'source_it': source_it, 'author': author,
             'author_key': key, 'published': False}))
        sh(['git', 'add', '-A'], self.peer)
        # ⛔ Коміт від ІМЕНІ цього ж автора, а не дефолтного «Peer» із setUp.
        # Інакше два канали авторства (заява в `.canvas-state.json` і git-лог)
        # несуть РІЗНІ імена, і перевірка витоку через примітку стає фікцією:
        # мутація «поверни імʼя в note» підставляє git-лог, тобто зовсім інший
        # рядок, ніж той, що шукає тест. Спіймано мутацією 15.09.2026.
        sh(['git', '-c', f'user.name={author}', '-c', 'user.email=' + key,
            'commit', '-qm', 'колега правив макет'], self.peer)
        p = sh(['git', 'push', '-q', 'origin', 'main'], self.peer)
        self.assertEqual(p.returncode, 0, f'peer push failed: {p.stderr}')

    def test_pull_creates_foreign_iteration_and_my_fork(self):
        """Ланцюг передач: чуже приїжджає СВОЄЮ ітерацією, робота йде у форк.

        Робота ніколи не починається поверх чужої ітерації — рішення власника
        15.09.2026. Дешевше за детектор «почав правити» і не лишає стану, у
        якому частина правок уже лягла в чуже, а переносити її нікому.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            self._sync()
            self._peer_push_with_state('<h1>чуже</h1>', 'Ольга Сидорук',
                                       'designer2@example.com')
            r = self.serve.gitlab_pull(self.task, self.gl)
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

        its = self._meta()['iterations']
        self.assertEqual([i['id'] for i in its], ['it1', 'it2', 'it3'])
        foreign, fork = its[1], its[2]
        self.assertEqual(foreign['author'], 'Ольга Сидорук')
        self.assertEqual(foreign['author_key'], 'designer2@example.com')
        self.assertEqual(foreign['origin']['it'], 'it3',
                         'номер ітерації в автора загубився — саме це й боліло')
        self.assertEqual(fork['author_key'], 'lead@example.com')
        self.assertEqual(fork['from'], 'it2')
        self.assertNotIn('origin', fork, 'форк не має чужого походження')
        self.assertEqual(r['iteration']['id'], 'it2')
        self.assertEqual(r['fork']['id'], 'it3')
        self.assertEqual(
            self.serve.mockup_hash(os.path.join(self.task_dir, 'iterations', 'it2')),
            self.serve.mockup_hash(os.path.join(self.task_dir, 'iterations', 'it3')),
            'форк не дорівнює тому, що передав колега')

    def test_pull_of_my_own_content_does_not_fork(self):
        """Друга машина того самого дизайнера — не привід форкати.

        Ключ у `.canvas-state.json` мій, тобто це та сама людина: форк був би
        копією моєї ж роботи, тобто сміттям у переліку ітерацій. Саме цю межу
        спіймав наявний `test_9_gitlab_pull_imports_iteration` (він чекає рівно
        +1 ітерацію), а не читання коду.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            self._sync()
            self._peer_push_with_state('<h1>з моєї другої машини</h1>', 'Lead',
                                       'lead@example.com')
            r = self.serve.gitlab_pull(self.task, self.gl)
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

        self.assertIsNone(r['fork'], 'форк на власному вмісті — сміття в переліку')
        self.assertEqual([i['id'] for i in self._meta()['iterations']], ['it1', 'it2'])
        # `origin` («в автора це Іт.3») на ВЛАСНІЙ ітерації — беззмістовний
        # підпис про самого себе; спека дозволяє його лише в чужих.
        self.assertNotIn('origin', self._meta()['iterations'][1])

    def test_fork_is_the_freshest_by_mtime(self):
        """⛔ ПАСТКА, заради якої написаний `_touch_tree`.

        `copy_mockup` копіює через `shutil.copy2`, який ЗБЕРІГАЄ mtime джерела.
        Без явного дотику форк успадкував би час файлів дзеркала й міг
        виявитись «старішим» за мою вчорашню роботу — а `autosync` бере
        найсвіжішу за mtime, тобто Stop-хук відправив би НЕ ту ітерацію.
        Мутація: прибери виклик `_touch_tree` — тест червоніє.
        """
        # Особа машини задана явно: без неї (`GIT_CONFIG_GLOBAL` тут порожній) усе «своє», і чужого форку не буде.
        def run():
            self._sync()
            self._peer_push_with_state('<h1>чуже</h1>', 'Ольга', 'designer2@example.com')
            # Моя it1 — свіжа (працював щойно).
            self._write(os.path.join(self.it1, 'index.html'), '<h1>моє сьогодні</h1>')
            # А макет колеги зроблений тиждень тому: зістарюємо дзеркало руками.
            old = time.time() - 7 * 24 * 3600
            md = self.serve.vcs_mirror_dir(self.gl)
            sh(['git', 'pull', '-q', '--ff-only', 'origin', 'main'], md)
            for root, _, names in os.walk(os.path.join(md, 'mockup/t1')):
                for n in names:
                    os.utime(os.path.join(root, n), (old, old))
            return self.serve.gitlab_pull(self.task, self.gl)
        r = self._as_serg(run)

        fork_dir = os.path.join(self.task_dir, 'iterations', r['fork']['id'])
        self.assertGreater(self.serve._dir_mtime(fork_dir),
                           self.serve._dir_mtime(self.it1),
                           'форк не найсвіжіший — autosync відправить стару ітерацію')

    # ---- fb-29092026-d64d35: boss-interface, 29.09.2026 ----

    def _own_push_dated(self, html, days_ago):
        """Мій же пуш з ДРУГОЇ машини, зроблений `days_ago` днів тому."""
        when = time.strftime('%Y-%m-%dT%H:%M:%S',
                             time.localtime(time.time() - days_ago * 24 * 3600))
        os.environ['GIT_COMMITTER_DATE'] = os.environ['GIT_AUTHOR_DATE'] = when
        try:
            self._peer_push_with_state(html, 'Lead', 'lead@example.com')
        finally:
            os.environ.pop('GIT_COMMITTER_DATE', None)
            os.environ.pop('GIT_AUTHOR_DATE', None)

    def _as_serg(self, fn):
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            return fn()
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

    def _age(self, d, days):
        old = time.time() - days * 24 * 3600
        for root, _, names in os.walk(d):
            for n in names:
                os.utime(os.path.join(root, n), (old, old))

    def _working_everywhere(self):
        """Робоча ітерація очима ВСІХ трьох споживачів: `state.py` («продовжуємо
        з…»), `inbox.py` і автосинк (найсвіжіша СВОЯ за mtime)."""
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), 'bin'))
        import inbox
        import state
        its = self._meta()['iterations']
        key = 'lead@example.com'
        mine = [i['id'] for i in its if self.serve.iteration_is_mine(i, key)]
        auto = max(mine, key=lambda i: self.serve._dir_mtime(
            os.path.join(self.task_dir, 'iterations', i)))
        return (state.working_iteration(its, key)['id'],
                inbox.working_iteration(its, key)['id'], auto)

    def test_pull_of_older_own_content_forks_my_latest_work(self):
        """Рівно boss-interface 29.09.2026. Робота на цій машині — сьогодні;
        на GitLab — МОЯ ж версія з другої машини, старша (там пуш падав через
        repo з IP). «Підтягнути» заводив її ОСТАННЬОЮ, і всі три вказівники
        робочої ітерації переїжджали на старе: автосинк о 11:48 тричі обрав
        it6 (Іт.7 від 08.09) замість it5 (Іт.14). Рішення власника 29.09.2026:
        привезене лягає історією, а слідом — форк моєї найсвіжішої роботи."""
        def run():
            self._sync()
            self._own_push_dated('<h1>з другої машини, три дні тому</h1>', 3)
            self._write(os.path.join(self.it1, 'index.html'), '<h1>моє сьогодні</h1>')
            return self.serve.gitlab_pull(self.task, self.gl)
        r = self._as_serg(run)

        its = self._meta()['iterations']
        self.assertEqual([i['id'] for i in its], ['it1', 'it2', 'it3'])
        self.assertEqual(r['iteration']['id'], 'it2', 'привезене — окремою ітерацією')
        self.assertEqual(r['fork']['id'], 'it3')
        self.assertEqual(its[2]['from'], 'it1', 'форк — з МОЄЇ роботи, не з привезеного')
        self.assertEqual(r.get('continue_from'), 'it1')
        self.assertEqual(
            self.serve.mockup_hash(os.path.join(self.task_dir, 'iterations', 'it3')),
            self.serve.mockup_hash(self.it1))
        self.assertEqual(self._working_everywhere(), ('it3', 'it3', 'it3'))

    def test_pull_of_newer_own_content_is_the_work_no_fork(self):
        """Контроль: друга машина справді пішла вперед (моя тут — тиждень тому).
        Привезене і є продовженням, форк був би сміттям."""
        def run():
            self._sync()
            self._age(self.it1, 7)
            self._own_push_dated('<h1>з другої машини, вчора</h1>', 1)
            return self.serve.gitlab_pull(self.task, self.gl)
        r = self._as_serg(run)

        self.assertIsNone(r['fork'])
        self.assertIsNone(r.get('continue_from'))
        self.assertEqual(self._working_everywhere(), ('it2', 'it2', 'it2'))

    def test_reshot_frames_are_not_work(self):
        """Кадри перезнімаються САМІ (автозʼємка при вході в «Огляд», T-34), тож
        свіжий `shots/` не означає, що в ітерації працювали. Інакше «Огляд» на
        тижневій ітерації перетворював би вчорашню роботу з другої машини на
        «старшу» — і форк відвів би мене назад, у тижневу."""
        def run():
            self._sync()
            self._age(self.it1, 7)
            shots = os.path.join(self.it1, 'shots')
            os.makedirs(shots)
            self._write(os.path.join(shots, 'manifest.json'), '{"shots":{}}')
            self._own_push_dated('<h1>з другої машини, вчора</h1>', 1)
            return self.serve.gitlab_pull(self.task, self.gl)
        r = self._as_serg(run)

        self.assertIsNone(r['fork'], 'перезйомка кадрів зійшла за роботу')

    def test_frames_only_commit_on_origin_is_not_work(self):
        """Дзеркальний бік `shots/`: кадри їдуть на GitLab (їх немає в SKIP), і
        свіжий коміт ЛИШЕ кадрів — це перезйомка, а не нова версія. Тоді свій пуш
        трьох днів тому лишається старшим за мою сьогоднішню роботу — форк
        мусить бути. (Ревʼю 29.09.2026: без цього тесту виключення жило даремно.)"""
        def run():
            self._sync()
            self._own_push_dated('<h1>з другої машини, три дні тому</h1>', 3)
            sh(['git', 'pull', '-q', '--ff-only', 'origin', 'main'], self.peer)
            shots = os.path.join(self.peer, 'mockup/t1/shots')
            os.makedirs(shots, exist_ok=True)
            self._write(os.path.join(shots, 'index.webp'), 'кадр')
            sh(['git', 'add', '-A'], self.peer)
            sh(['git', 'commit', '-qm', 'кадри'], self.peer)
            self.assertEqual(sh(['git', 'push', '-q', 'origin', 'main'], self.peer).returncode, 0)
            self._write(os.path.join(self.it1, 'index.html'), '<h1>моє сьогодні</h1>')
            return self.serve.gitlab_pull(self.task, self.gl)
        r = self._as_serg(run)
        self.assertEqual(r.get('continue_from'), 'it1', 'коміт кадрів зійшов за нову версію')

    def test_finder_dotfile_is_not_work(self):
        """`.DS_Store`, який Finder кладе в теку ітерації, — не «працювали сьогодні».
        Інакше тижнева ітерація «молодшала» б і форк відводив би мене від
        справді новішої своєї версії з другої машини."""
        def run():
            self._sync()
            self._age(self.it1, 7)
            self._write(os.path.join(self.it1, '.DS_Store'), 'finder')
            self._own_push_dated('<h1>з другої машини, вчора</h1>', 1)
            return self.serve.gitlab_pull(self.task, self.gl)
        r = self._as_serg(run)
        self.assertIsNone(r['fork'], '.DS_Store зійшов за роботу')

    def test_insteadof_rule_does_not_rewrite_origin_each_time(self):
        """`git remote get-url` розгортає `url.*.insteadOf`, тож на машині з таким
        правилом звірка з ним переписувала б origin на КОЖЕН статус (і
        шуміла). Звіряємо записане значення, а не розгорнуте."""
        gl = dict(self.gl, repo='alias:origin.git')
        md = self.serve.vcs_mirror_dir(gl)
        os.makedirs(os.path.dirname(md), exist_ok=True)
        sh(['git', 'clone', '-q', self.origin, md], self.tmp)
        sh(['git', 'config', f'url.{self.tmp}/.insteadOf', 'alias:'], md)
        sh(['git', 'remote', 'set-url', 'origin', 'alias:origin.git'], md)
        import io
        from contextlib import redirect_stderr
        err = io.StringIO()
        with redirect_stderr(err):
            st = self.serve.gitlab_status(self.task, gl, self._meta(), 'it1')     # звірка origin + fetch
        self.assertNotIn('error', st, st)
        self.assertNotIn('origin', err.getvalue(), 'origin переписано, хоча він збігався')

    def test_mirror_follows_repo_url_from_tasks_json(self):
        """Дзеркало, склоноване зі старою формою адреси (обхід по IP 25.08.2026), тримало її і після того, як `tasks.json`
        полагодили: `git fetch` ішов на origin дзеркала, а не на адресу задачі. Дзеркало мусить іти за конфігом — коли це
        ТОЙ САМИЙ репо в іншій формі (`file://` ↔ шлях)."""
        self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')         # клон дзеркала
        md = self.serve.vcs_mirror_dir(self.gl)
        sh(['git', 'remote', 'set-url', 'origin', 'file://' + self.origin], md)

        self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')         # звірка origin з ціллю

        self.assertEqual(sh(['git', 'remote', 'get-url', 'origin'], md).stdout.strip(),
                         self.origin)
        self.assertTrue(self._sync()['synced'], 'після вирівнювання пуш не пройшов')

    def test_mirror_of_another_repo_is_refused_not_rewritten(self):
        """Інший репозиторій у теці дзеркала: `set-url` мовчки повіз би історію одного репо в remote іншого. Статус
        віддає помилку, відправка — `OSError` (як і інша відмова git); `origin` лишається."""
        self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')
        md = self.serve.vcs_mirror_dir(self.gl)
        gone = os.path.join(self.tmp, 'gone.git')
        sh(['git', 'remote', 'set-url', 'origin', gone], md)

        st = self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')
        self.assertEqual(st['code'], 'vcs-error')
        self.assertIn('another repository', st['error'])
        with self.assertRaises(OSError) as cm:
            self._sync()
        self.assertIn('another repository', str(cm.exception))
        self.assertEqual(sh(['git', 'remote', 'get-url', 'origin'], md).stdout.strip(), gone)

    def test_second_pull_without_changes_creates_nothing(self):
        """Пара не дублюється: чужа ітерація байт-у-байт дорівнює дзеркалу,
        тож наявна перевірка ідемпотентності впізнає її."""
        self._sync()
        self._peer_push_with_state('<h1>чуже</h1>', 'Ольга', 'designer2@example.com')
        self.serve.gitlab_pull(self.task, self.gl)
        before = [i['id'] for i in self._meta()['iterations']]

        r = self.serve.gitlab_pull(self.task, self.gl)

        self.assertTrue(r.get('unchanged'), f'другий pull завів ще пару: {r}')
        self.assertEqual([i['id'] for i in self._meta()['iterations']], before)

    def test_blocked_result_carries_who_and_when(self):
        """Блокування мусить нести ФАКТИ про верхній коміт origin, а не догадку.

        03.08.2026 хук казав «там працював інший дизайнер», а це була та сама
        людина з іншої копії інструменту — діагностика пішла хибним слідом.
        Автор і дата беруться з дзеркала, без мережі.
        """
        self._sync()
        self._peer_commit('mockup/t1/index.html', '<h1>чуже</h1>', 'колега правив макет')
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v2</h1>')

        r = self._sync()
        self.assertEqual(r.get('blocked'), 'behind')
        top = r.get('behind_top') or {}
        self.assertEqual(top.get('author'), 'Peer')
        self.assertEqual(top.get('subject'), 'колега правив макет')
        self.assertTrue(top.get('date'), 'дата верхнього коміту мусить бути')

    def test_blocked_sync_does_not_stamp_fingerprint(self):
        self._sync()
        self._peer_commit('mockup/t1/index.html', '<h1>чуже</h1>', 'колега правив макет')
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v2</h1>')
        self._sync()

        stamped = self._meta()['gitlab']['synced_hashes']['it1']
        self.assertNotEqual(stamped, self.serve.mockup_hash(self.it1),
                            'відбиток не має рухатись, поки макет не поїхав')

    def test_sync_succeeds_after_pull(self):
        self._sync()
        self._peer_commit('mockup/t1/index.html', '<h1>чуже</h1>', 'колега правив макет')
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v2</h1>')
        self.assertEqual(self._sync().get('blocked'), 'behind')

        self.serve.gitlab_pull(self.task, self.gl)
        self.assertTrue(self._sync()['synced'])

    def test_unpushed_commit_is_caught_up_not_reported_as_ok(self):
        """Сценарій bgSanctions: коміт у дзеркалі є, на origin — ні, макет не мінявся.

        Раніше `git status` був чистий → `ok:True, changed:False` → відбиток
        ставився → UI малював «✓», хоча коміт лежав на машині.
        """
        self._sync()
        md = self.serve.vcs_mirror_dir(self.gl)
        orphan = os.path.join(md, 'mockup', 't1', 'index.html')
        self._write(orphan, '<h1>v3-orphan</h1>')
        sh(['git', 'add', '-A'], md)
        sh(['git', '-c', 'user.email=t@t', '-c', 'user.name=T',
            'commit', '-qm', 'orphan, не запушений'], md)

        st = self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')
        self.assertGreater(st['unpushed'], 0, 'статус мусить бачити незапушений коміт')

        # робоча ітерація = вміст дзеркала, отже git status буде чистий
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v3-orphan</h1>')
        r = self._sync()
        self.assertTrue(r.get('catchup'))
        self.assertTrue(r['synced'])
        self.assertEqual(self.rev_count(md, 'origin/main..main'), 0)

    def test_task_absent_on_origin_is_not_reported_as_synced(self):
        """Фідбек 29.07.2026: `behind=0` + чистий локальний стан читались як
        «синхронізовано» для задачі, якої на GitLab узагалі немає."""
        st = self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')
        self.assertEqual(st['behind'], 0, 'наздоганяти справді нічого')
        self.assertIs(st['on_remote'], False, 'але теки задачі на origin НЕМА')

    def test_after_first_sync_task_is_on_remote(self):
        self._sync()
        st = self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')
        self.assertIs(st['on_remote'], True)

    def test_meta_claiming_sync_does_not_override_the_remote_truth(self):
        """Найгірший випадок bgSanctions: мета каже synced_it/synced_at, а теки
        на origin немає. Правду говорить origin, а не власний запис."""
        self._save_meta({**self._meta(),
                         'gitlab': {'synced_at': '22.07.2026 12:07',
                                    'synced_it': 'it1', 'sha': None}})
        st = self.serve.gitlab_status(self.task, self.gl, self._meta(), 'it1')
        self.assertIs(st['on_remote'], False)

    def test_record_sync_without_sha_writes_nothing(self):
        """`sha=None` — це «пуша не було». Відбиток при ньому = готова брехня."""
        before = json.dumps(self._meta().get('gitlab'), sort_keys=True)
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.serve._record_sync(self.task, 'it1', None)
        self.assertEqual(json.dumps(self._meta().get('gitlab'), sort_keys=True), before)
        self.assertIn('немає sha', err.getvalue(), 'мовчати про це не можна')

    def test_fetch_failure_raises_instead_of_silent_zero_behind(self):
        self._sync()
        os.rename(self.origin, self.origin + '-hidden')
        try:
            with self.assertRaises(OSError) as cm:
                self.serve.gitlab_sync('t1', self.task, self.gl, 'it1')
            self.assertIn('fetch failed', str(cm.exception))
        finally:
            os.rename(self.origin + '-hidden', self.origin)

    def test_autosync_offline_stays_quiet_and_keeps_fingerprint(self):
        """Офлайн — не привід сварити дизайнера, але й не привід брехати «✓»."""
        self._sync()
        before = json.dumps(self._meta().get('gitlab'), sort_keys=True)
        self._write(os.path.join(self.it1, 'index.html'), '<h1>v4</h1>')
        os.rename(self.origin, self.origin + '-hidden')
        try:
            r = self.serve.autosync('t1', self.task, self.gl)
        finally:
            os.rename(self.origin + '-hidden', self.origin)

        self.assertEqual(r.get('reason'), 'offline')
        self.assertFalse(r.get('ok'))
        self.assertFalse(r.get('synced'))
        self.assertEqual(json.dumps(self._meta().get('gitlab'), sort_keys=True), before)

    def test_sync_of_a_foreign_iteration_is_blocked_with_the_author_named(self):
        """Ручний «Синхронізувати» на чужій ітерації відмовляє вголос.

        Автосинк її не візьме (перевірка нижче), але кнопка в смузі пушить
        ОБРАНУ — тобто без цього гейта чуже поїхало б у дзеркало під моїм
        підписом одним кліком.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            self._save_meta({'iterations': [
                {'id': 'it1', 'author': 'Ольга Сидорук',
                 'author_key': 'designer2@example.com'}]})
            r = self.serve.gitlab_sync('t1', self.task, self.gl, 'it1')
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

        self.assertFalse(r['ok'])
        self.assertFalse(r.get('synced'))
        self.assertEqual(r.get('blocked'), 'foreign')
        self.assertIn('Ольга Сидорук', r.get('author', ''),
                      'відмова не назвала автора — дизайнер не знає, чия це')

    def test_real_pull_note_carries_no_name_into_public_manifest(self):
        """⛔ Приватність — на РЕАЛЬНІЙ примітці, яку складає `gitlab_pull`.

        Охоронець у `test_serve.py` перевіряє СКЛАД полів маніфеста на
        синтетичній фікстурі — і саме тому пропустив справжній канал витоку:
        імʼя колеги їхало не полем `author`, а текстом усередині `note`
        («оновлення з GitLab · Ольга Сидорук»), а `publish_manifest` везе
        `note` як є. `manifest.json` віддається без пароля (заміряно
        11.09.2026), тобто ПІБ лежало б на Vercel у відкритому файлі.

        Мутація: поверни імʼя в `note` у `gitlab_pull` — тест червоніє.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            self._sync()
            self._peer_push_with_state('<h1>чуже</h1>', 'Ольга Сидорук',
                                       'designer2@example.com')
            self.serve.gitlab_pull(self.task, self.gl)
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

        its = self._meta()['iterations']
        # Свідок: імʼя таки зафіксоване — але ПОЛЕМ, не текстом примітки.
        self.assertTrue(any(i.get('author') == 'Ольга Сидорук' for i in its),
                        'автор не записаний узагалі — перевірка нижче вакуумна')
        pub = os.path.join(self.task_dir, 'publish')
        os.makedirs(pub, exist_ok=True)
        pages = [{'it': i['id'], 'out_rel': i['id'], 'name': 'Головна', 'depth': 0,
                  'page': {'id': 'main'}} for i in its]
        self.serve.publish_manifest(self.task, 't1', its, pages, {}, pub)
        with open(os.path.join(pub, 'manifest.json'), encoding='utf-8') as fh:
            raw = fh.read()
        self.assertNotIn('Ольга', raw, f'ПІБ колеги у публічному маніфесті: {raw}')
        self.assertNotIn('designer2@', raw)

    def test_bootstrap_from_clone_does_not_sign_someone_elses_work(self):
        """⛔ Бутстрап задачі, макет якої вже лежить у репо колеги.

        Саме цей шлях спочатку підписував чужу роботу МОЇМ іменем: `task_new`
        клонує макет і заводить `it1` — а `_stamp_author` ставив туди особу
        машини. Наслідок не косметичний: після синку цей підпис поїхав би
        назад, і справжня авторка дістала б ВЛАСНИЙ макет як чужий — із форком
        і забороною пушу.

        Мутація, якою доводиться: постав `_stamp_author(it1_entry)` у гілці
        `cloned` — тест червоніє на імені.

        Тут же перевіряється ПАРА: клон-бутстрап, як і «Підтягнути», лишає
        чужу ітерацію й форк від неї. Без форку задача починалась без жодної
        СВОЄЇ ітерації, і `bin/state.py` казав про ту саму Іт.1 дві протилежні
        речі — «остання своя» і «чужа, read-only» (знайдено ревʼю 15.09.2026).
        """
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            self._sync()  # у репо тепер лежить макет із підписом Lead
            self._peer_push_with_state('<h1>чуже</h1>', 'Ольга Сидорук',
                                       'designer2@example.com')
            cfg = {'tasks': {}, 'design_work_root': os.path.join(self.tmp, 'dw'),
                   'gitlab': {}}
            r = self.serve.task_new(cfg, 'nova', title='Нова',
                                    gitlab={'repo': self.origin, 'path': 'mockup/t1'})
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

        with open(os.path.join(r['dir'], 'iterations.json'), encoding='utf-8') as fh:
            its = json.load(fh)['iterations']
        self.assertEqual(its[0]['author'], 'Ольга Сидорук',
                         'клонований макет підписаний не тим, хто його зробив')
        self.assertEqual(its[0]['author_key'], 'designer2@example.com')
        self.assertEqual(len(its), 2, 'форку немає — задача без жодної своєї ітерації')
        self.assertEqual(its[1]['author_key'], 'lead@example.com')
        self.assertEqual(its[1]['from'], 'it1')
        self.assertTrue(os.path.isfile(
            os.path.join(r['dir'], 'iterations', 'it2', 'index.html')),
            'теки форку на диску немає')

    def test_a_new_task_with_a_reachable_mirror_but_no_mockup_yet_gets_the_starter_index(self):
        """⛔ Дзеркало ДОСТУПНЕ, а `mockup/<tid>` у ньому ще нема — звичайний випадок для зовсім нової задачі.

        Регресія релізу 0.6.0 (`from` у `task-new`): параметр `src` («тека з наявного макета») затінювався локальним
        `src = os.path.join(md, gl['path'])` гілки GitLab; `cloned` лишався False, гілка «із теки» діставала шлях
        НЕІСНУЮЧОГО макета в дзеркалі й порожній перелік — і `it1` лягала ПОРОЖНЬОЮ, без стартового `index.html`.

        Мутація, якою доводиться: поверни параметр під назвою `src` (чи прибери `adopt_` з імен) — тест червоніє.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            cfg = {'tasks': {}, 'design_work_root': os.path.join(self.tmp, 'dw'), 'gitlab': {}}
            r = self.serve.task_new(cfg, 'fresh', title='Свіжа задача',
                                    gitlab={'repo': self.origin, 'path': 'mockup/never-existed'})
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)
        self.assertFalse(r['cloned'])
        self.assertNotIn('adopted', r)
        index = os.path.join(r['dir'], 'iterations', 'it1', 'index.html')
        self.assertTrue(os.path.isfile(index), 'стартового index.html нема: it1 порожня')
        with open(index, encoding='utf-8') as fh:
            self.assertIn('Свіжа задача', fh.read())

    def test_autosync_never_picks_a_foreign_iteration(self):
        """Чужа ітерація найсвіжіша — і все одно не їде під моїм підписом.

        Мутація: поверни `max(live, …)` замість `max(mine, …)` — тест червоніє.
        """
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            self._sync()
            foreign = os.path.join(self.task_dir, 'iterations', 'it2')
            os.makedirs(foreign)
            self._write(os.path.join(foreign, 'index.html'), '<h1>чуже</h1>')
            self._save_meta({'iterations': [
                {'id': 'it1', 'author': 'Lead', 'author_key': 'lead@example.com'},
                {'id': 'it2', 'author': 'Ольга', 'author_key': 'designer2@example.com'}]})
            self._write(os.path.join(self.it1, 'index.html'), '<h1>моє</h1>')
            os.utime(os.path.join(foreign, 'index.html'), None)  # чужа найсвіжіша

            r = self.serve.autosync('t1', self.task, self.gl)
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

        self.assertEqual(r.get('it'), 'it1', f'автосинк узяв чужу ітерацію: {r}')

    def test_autosync_with_only_foreign_iterations_stays_quiet(self):
        """Своїх немає — мовчимо з названою причиною, а не пушимо «хоч щось»."""
        os.environ['DC_IDENTITY_NAME'] = 'Lead'
        os.environ['DC_IDENTITY_EMAIL'] = 'lead@example.com'
        try:
            self._save_meta({'iterations': [
                {'id': 'it1', 'author': 'Ольга', 'author_key': 'designer2@example.com'}]})
            r = self.serve.autosync('t1', self.task, self.gl)
        finally:
            os.environ.pop('DC_IDENTITY_NAME', None)
            os.environ.pop('DC_IDENTITY_EMAIL', None)

        self.assertFalse(r.get('changed'))
        self.assertEqual(r.get('reason'), 'foreign-only')

    def test_pull_reports_divergence_instead_of_copying_stale_mirror(self):
        """`pull --ff-only` падає при розходженні — раніше відмова ковталась,
        і в нову ітерацію копіювалось ЗАСТАРІЛЕ дзеркало під підписом колеги."""
        self._sync()
        md = self.serve.vcs_mirror_dir(self.gl)
        self._write(os.path.join(md, 'mockup', 't1', 'index.html'), '<h1>local</h1>')
        sh(['git', 'add', '-A'], md)
        sh(['git', '-c', 'user.email=t@t', '-c', 'user.name=T',
            'commit', '-qm', 'локальний коміт'], md)
        self._peer_commit('mockup/t1/index.html', '<h1>peer</h1>', 'колега правив макет')

        its_before = len(self._meta()['iterations'])
        with self.assertRaises(OSError) as cm:
            self.serve.gitlab_pull(self.task, self.gl)
        self.assertIn('pull --ff-only failed', str(cm.exception))
        self.assertEqual(len(self._meta()['iterations']), its_before,
                         'фальшива ітерація «оновлення з GitLab» не має зʼявитись')


if __name__ == '__main__':
    unittest.main()
