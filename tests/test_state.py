"""`state.py`: рядок стану GitLab не має права заспокоювати даремно.

Фідбек 29.07.2026: для задачі, якої на GitLab узагалі немає, друкувалось
«синхронізовано» — бо наздоганяти нічого і локально все чисто.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbconf  # noqa: E402
import state  # noqa: E402
from liga_fixture import LigaFixture  # noqa: E402
from serve import VcsError  # noqa: E402  (`state` уже додав `app` у sys.path)


class GitlabLine(unittest.TestCase):
    def test_never_pushed_is_not_called_synced(self):
        line = state.gitlab_line({'behind': 0, 'dirty': False, 'on_remote': False},
                                 'mockup/dobFilter')
        self.assertIn('ЩЕ НЕ В РЕПО', line)
        self.assertNotIn('синхронізовано', line)

    def test_never_pushed_wins_over_clean_local_state(self):
        """Порядок гілок: «ще не в репо» перевіряється ДО «синхронізовано»."""
        line = state.gitlab_line({'behind': 0, 'dirty': False, 'on_remote': False}, 'p')
        self.assertTrue(line.startswith('GitLab (p): ⚠'))

    def test_present_on_remote_and_clean_is_synced(self):
        line = state.gitlab_line({'behind': 0, 'dirty': False, 'on_remote': True}, 'p')
        self.assertIn('синхронізовано', line)
        self.assertNotIn('⚠', line)

    def test_dirty_iteration_is_named(self):
        line = state.gitlab_line({'behind': 0, 'dirty': True, 'on_remote': True}, 'p')
        self.assertIn('незбережені зміни', line)

    def test_behind_in_our_folder_still_wins_over_dirty(self):
        line = state.gitlab_line({'behind': 2, 'behind_path': 1, 'dirty': True,
                                  'on_remote': True}, 'p')
        self.assertIn('НОВІШЕ (2)', line)

    def test_repo_ahead_is_not_reported_as_someone_editing_our_mockup(self):
        """«Обігнали в РЕПО» і «обігнали в ЗАДАЧІ» — різні новини.

        `_behind_count` свідомо рахує по ВСЬОМУ репо (інакше дзеркало йде в
        non-fast-forward), тому верхній коміт чужої задачі читався як «хтось
        оновив ТВІЙ макет. Спершу Підтягнути!». На lu-home це коштувало двох
        втрат контексту: вміст теки був байт-у-байт свій, а точка входу в задачу
        відправляла тягнути чуже (фідбек 09.09.2026).
        """
        line = state.gitlab_line({'behind': 3, 'behind_path': 0, 'dirty': False,
                                  'on_remote': True}, 'p')
        self.assertNotIn('оновив макет', line)
        self.assertNotIn('Спершу Підтягнути', line)
        self.assertIn('репо', line.lower())

    def test_behind_without_the_breakdown_stays_loud(self):
        """Старий статус (без `behind_path`) не має тихо стати спокійним:
        немає розбивки — немає підстав заспокоювати."""
        line = state.gitlab_line({'behind': 2, 'dirty': False, 'on_remote': True}, 'p')
        self.assertIn('НОВІШЕ (2)', line)

    def test_named_task_hints_carry_the_prefix(self):
        """Ревʼю 12.10.2026: «Спершу Підтягнути!» і «Надіслати» під `--task` без
        префікса вели в ПОТОЧНУ задачу — копія дослівно тягнула б чужу."""
        behind = {'behind': 2, 'behind_path': 1, 'dirty': False, 'on_remote': True}
        line = state.gitlab_line(behind, 'p', tid='beta')
        self.assertIn('Спершу Підтягнути!', line)
        self.assertIn('POST /t/beta/api/gitlab-pull', line)
        never = {'behind': 0, 'dirty': False, 'on_remote': False}
        line = state.gitlab_line(never, 'p', tid='beta')
        self.assertIn('POST /t/beta/api/gitlab-sync', line)
        self.assertIn('діє на поточну задачу канваса, не на названу', line,
                      'кнопка канваса діє на ПОТОЧНУ — під названою про це мовчати не можна')
        # id із керівними символами не ламає шлях
        line = state.gitlab_line(behind, 'p', tid='a b/c')
        self.assertIn('POST /t/a%20b%2Fc/api/gitlab-pull', line)

    def test_unnamed_hints_stay_exactly_as_before(self):
        behind = {'behind': 2, 'behind_path': 1, 'dirty': False, 'on_remote': True}
        line = state.gitlab_line(behind, 'p')
        self.assertTrue(line.endswith('Спершу Підтягнути!'), line)
        line = state.gitlab_line({'behind': 0, 'dirty': False, 'on_remote': False}, 'p')
        self.assertTrue(line.endswith('У канвасі: «↑ Надіслати Іт.N»'), line)
        self.assertNotIn('/t/', line)


class IterationLine(unittest.TestCase):
    """Номер ітерації — з ID, а не з позиції в списку.

    На courts лишилась одна ітерація з id=it4: `state.py` друкував «Іт.1
    (остання)» і «ПРОДОВЖУЄМО з Іт.1», а канвас, `iterations.json` і GitLab-синк
    кажуть it4. Точка входу в задачу називала ітерацію не тим номером, який
    бачить дизайнер і колеги (фідбек 10.09.2026).
    """

    def test_number_comes_from_id_not_position(self):
        line = state.iterations_line([{'id': 'it4'}])
        self.assertIn('Іт.4', line)
        self.assertNotIn('Іт.1', line)

    def test_last_is_marked_and_published_is_shown(self):
        line = state.iterations_line([{'id': 'it2', 'published': True}, {'id': 'it5'}])
        self.assertIn('Іт.2 ✓превью', line)
        self.assertIn('Іт.5 (остання)', line)

    def test_continue_line_names_the_id_number(self):
        self.assertIn('Іт.4', state.continue_line([{'id': 'it4'}]))

    def test_working_iteration_is_the_last_mine(self):
        """Ітерація, ПРО ЯКУ питаємо GitLab, — остання СВОЯ.

        ⚠️ Знайдено ревʼю 15.09.2026 і підтверджено живим прогоном: у `main()`
        статус GitLab запитувався про `last['id']`, а змінної `last` там не
        існувало взагалі — рядок мовчки перетворювався на «GitLab: не дістати
        статус (name 'last' is not defined)». Тобто сигнал «на GitLab новіше»,
        на якому тримається ВЕСЬ сценарій передачі між дизайнерами (і
        інструкція в `references/canvas.md`), був мертвий. Вада існувала до цієї
        задачі, але саме вона робить її безглуздою, тому лікується тут.
        """
        its = [{'id': 'it1', 'author_key': 'lead@example.com'},
               {'id': 'it2', 'author': 'Ольга', 'author_key': 'designer2@example.com'}]
        self.assertEqual(state.working_iteration(its, 'lead@example.com')['id'], 'it1')
        # Своїх немає — краще остання чужа, ніж падіння: статус усе одно про репо.
        self.assertEqual(state.working_iteration(its[1:], 'lead@example.com')['id'], 'it2')
        self.assertIsNone(state.working_iteration([], ''))

    def test_continue_from_my_last_not_foreign(self):
        """Остання ітерація чужа — продовжуємо зі СВОЄЇ, а чужу називаємо.

        Вказати на чужу означало б відправити дизайнера працювати поверх роботи
        колеги — рівно те, від чого рятує пара «чужа + форк» у `gitlab_pull`.
        """
        its = [{'id': 'it1', 'author_key': 'lead@example.com'},
               {'id': 'it2', 'author': 'Ольга', 'author_key': 'designer2@example.com'}]
        line = state.continue_line(its, 'lead@example.com')
        self.assertIn('Іт.1', line)
        self.assertNotIn('ПРОДОВЖУЄМО з Іт.2', line)
        self.assertIn('Ольга', line)

    def test_no_own_iterations_says_so_instead_of_lying(self):
        """⛔ Своїх ітерацій НЕМАЄ — інструмент мусить це сказати, а не вдавати.

        Знайдено ревʼю 15.09.2026: рядок казав про ту саму ітерацію дві
        протилежні речі — «ПРОДОВЖУЄМО з Іт.1 (остання своя)» і поруч «Іт.1 —
        Ольга (підтягнута, read-only)». Це рівно той клас «інструмент бреше»,
        проти якого написана вся хвиля 1.33.
        """
        its = [{'id': 'it1', 'author': 'Ольга', 'author_key': 'designer2@example.com'}]
        line = state.continue_line(its, 'lead@example.com')
        self.assertNotIn('остання своя', line)
        self.assertIn('СВОЇХ ітерацій немає', line)
        self.assertIn('Ольга', line)

    def test_continue_line_endpoint_carries_the_named_task(self):
        """`(POST /api/iteration {"from": …})` копіюють дослівно, і без префікса
        вона форкала б ПОТОЧНУ задачу машини, а не названу (ревʼю 12.10.2026)."""
        its = [{'id': 'it1', 'author': 'Ольга', 'author_key': 'designer2@example.com'}]
        named = state.continue_line(its, 'lead@example.com', tid='beta')
        self.assertIn('POST /t/beta/api/iteration {"from": "it1"}', named)
        plain = state.continue_line(its, 'lead@example.com')
        self.assertIn('POST /api/iteration {"from": "it1"}', plain)
        self.assertNotIn('/t/', plain)
        self.assertIn('POST /t/a%20b/api/iteration',
                      state.continue_line(its, 'lead@example.com', tid='a b'))

    def test_continue_unchanged_without_authors(self):
        """Стара задача без підписів поводиться рівно як раніше."""
        line = state.continue_line([{'id': 'it1'}, {'id': 'it4'}], 'lead@example.com')
        self.assertIn('Іт.4', line)
        self.assertNotIn('read-only', line)

    def test_unknown_remote_is_spoken_not_swallowed(self):
        line = state.gitlab_line({'behind': 0, 'dirty': False, 'on_remote': None}, 'p')
        self.assertIn('невідомий', line)
        self.assertNotIn('синхронізовано', line)

    def test_error_wins_over_everything(self):
        line = state.gitlab_line({'error': 'fetch failed', 'on_remote': False}, 'p')
        self.assertIn('помилка — fetch failed', line)

    def test_without_a_label_the_line_is_the_070_one_word_for_word(self):
        """Без `label` — дослівно 0.7.0 (простір ЛІГА: рядки перевіряють тести й клієнт)."""
        self.assertEqual(state.gitlab_line({'behind': 0, 'dirty': False, 'on_remote': True}, 'p'),
                         'GitLab (p): синхронізовано')
        self.assertEqual(state.gitlab_line({'behind': 2, 'behind_path': 1, 'dirty': False, 'on_remote': True}, 'p'),
                         'GitLab (p): ⚠ на GitLab НОВІШЕ (2) — хтось (інший дизайнер/машина) оновив макет. '
                         'Спершу Підтягнути!')
        self.assertEqual(state.gitlab_line({'error': 'fetch failed', 'on_remote': False}, 'p'),
                         'GitLab (p): помилка — fetch failed')

    def test_the_label_names_the_remote_in_every_line(self):
        """Підпис — з `label` статусу: «GitHub (p)» і «на GitHub НОВІШЕ»; жодного «GitLab» у тексті рядка."""
        cases = {
            'помилка': {'error': 'fetch failed', 'on_remote': False},
            'ще не в репо': {'behind': 0, 'dirty': False, 'on_remote': False},
            'новіше': {'behind': 2, 'behind_path': 1, 'dirty': True, 'on_remote': True},
            'новіше без розбивки': {'behind': 2, 'dirty': False, 'on_remote': True},
            'репо попереду': {'behind': 3, 'behind_path': 0, 'dirty': False, 'on_remote': True},
            'невідомо': {'behind': 0, 'dirty': False, 'on_remote': None},
            'синхронізовано': {'behind': 0, 'dirty': True, 'on_remote': True},
        }
        for what, st in cases.items():
            for tid in (None, 'beta'):
                with self.subTest(what=what, tid=tid):
                    line = state.gitlab_line(st, 'p', tid, label='GitHub')
                    self.assertTrue(line.startswith('GitHub (p): '), line)
                    self.assertNotIn('GitLab', line)
        line = state.gitlab_line(cases['новіше'], 'p', label='GitHub')
        self.assertIn('на GitHub НОВІШЕ (2)', line)

    def test_the_hints_with_an_endpoint_keep_the_old_addresses_under_any_label(self):
        """Підказки з `/api/gitlab-sync` і `/api/gitlab-pull` не міняються: це псевдоніми, і вони діють у будь-якому просторі."""
        never = state.gitlab_line({'behind': 0, 'dirty': False, 'on_remote': False}, 'p', 'beta', label='GitHub')
        self.assertIn('POST /t/beta/api/gitlab-sync', never)
        behind = state.gitlab_line({'behind': 2, 'behind_path': 1, 'dirty': False, 'on_remote': True}, 'p', 'beta', label='GitHub')
        self.assertIn('POST /t/beta/api/gitlab-pull', behind)

    def test_a_busy_mirror_is_asked_again_not_called_an_error(self):
        """Поправка 7: опит під час відправки дає `code: vcs-busy` — це «зайнято, спробуй ще раз», а не «помилка»."""
        for label in ('GitLab', 'Git', 'GitHub'):
            with self.subTest(label=label):
                line = state.gitlab_line({'configured': True, 'error': 'mirror is busy', 'code': 'vcs-busy'}, 'p', label=label)
                self.assertEqual(line, f'{label} (p): зайнято (іде синхронізація), спробуй ще раз')
                self.assertIn('спробуй ще раз', line)
                self.assertNotIn('помилка', line)
                self.assertNotIn('mirror is busy', line)
        other = state.gitlab_line({'configured': True, 'error': 'fetch failed', 'code': 'vcs-offline'}, 'p')
        self.assertIn('помилка — fetch failed', other)

    def test_a_token_in_a_status_error_never_reaches_the_line(self):
        token = 'ghp_SECRETTOKEN123'
        line = state.gitlab_line({'error': f'fetch of https://{token}@github.com/o/r.git failed'}, 'p')
        self.assertNotIn(token, line)
        self.assertIn('помилка — fetch of https://***@github.com/o/r.git failed', line)

    def test_status_without_the_field_is_unknown_not_synced(self):
        """Немає факту — немає й «синхронізовано».

        Єдиний постачальник статусу (`serve.gitlab_status`) кладе `on_remote`
        завжди; відсутність ключа означала б, що стан прийшов нізвідки, і
        видавати його за «все доїхало» — та сама вигадана впевненість.
        """
        line = state.gitlab_line({'behind': 0, 'dirty': False}, 'p')
        self.assertIn('невідомий', line)
        self.assertNotIn('синхронізовано', line)



class LocalUrl(unittest.TestCase):
    """Де відкрити ітерацію в браузері (fb-22092026-79ae76): маршрут
    `/it-assets/` був завжди, але його не називав ніхто, і сесії піднімали
    власний http.server поверх теки ітерацій."""

    def setUp(self):
        import json
        import shutil
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix='st-url-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        it2 = os.path.join(self.tmp, 'iterations', 'it2')
        os.makedirs(os.path.join(it2, 'poshuk'))
        with open(os.path.join(it2, 'pages.json'), 'w', encoding='utf-8') as fh:
            json.dump({'pages': [{'id': 'poshuk', 'name': 'Пошук', 'published': True},
                                 {'id': 'kartka', 'name': 'Картка', 'published': True}]}, fh)
        self.task = {'dir': self.tmp}
        self.its = [{'id': 'it1'}, {'id': 'it2'}]

    def test_names_the_real_route_of_the_working_iteration(self):
        line = state.local_url_line(self.task, self.its, '', 8766)
        self.assertIn('http://127.0.0.1:8766/it-assets/it2/poshuk/index.html', line)
        self.assertIn('/commented?it=it2&page=poshuk&ch=local', line)
        self.assertIn('ще 1', line, 'про інші сторінки ітерації не сказано')
        self.assertNotIn('/preview/', line)

    def test_named_task_prints_only_urls_that_work(self):
        """Під названою задачею `/commented` без `bare=1` сервер відмовляє (пін
        ліг би в локальні коментарі ПОТОЧНОЇ задачі), тож друкувати такий URL —
        вести в 400. Сира сторінка — з префіксом; коментувати — у канвасі."""
        line = state.local_url_line(self.task, self.its, '', 8766, tid='beta')
        self.assertIn('http://127.0.0.1:8766/t/beta/it-assets/it2/poshuk/index.html', line)
        self.assertNotIn('/commented', line, 'адреса, що відповість 400')
        self.assertIn('ще 1: /t/beta/it-assets/it2/<id сторінки>/index.html', line,
                      'підказка про інші сторінки без префікса веде в поточну задачу')
        self.assertIn('http://127.0.0.1:8766/app/', line)
        self.assertIn('поточної задачі', line, 'не сказано, чиє це вікно канваса')
        # без назви — як було, і коментатор на місці
        plain = state.local_url_line(self.task, self.its, '', 8766)
        self.assertIn('/commented?it=it2&page=poshuk&ch=local', plain)

    def test_no_live_canvas_gives_advice_not_a_dead_url(self):
        line = state.local_url_line(self.task, self.its, '', None)
        self.assertIn('start.command', line)
        self.assertNotIn('http://', line, 'адреса, яка відкриє 404 чи чужу задачу')

    def test_named_task_without_a_live_canvas_does_not_ask_to_switch(self):
        """Під `--task` перемикати канвас на задачу НЕ треба (префікс `/t/<id>/`
        відкриває названу за будь-якої поточної): досить, щоб канвас ЖИВ."""
        line = state.local_url_line(self.task, self.its, '', None, tid='beta')
        self.assertIn('start.command', line)
        self.assertNotIn('перемкнись', line)
        self.assertIn('перемикатись на задачу не треба', line)
        self.assertIn('/t/beta/it-assets/<itN>/<сторінка>/index.html', line)
        self.assertNotIn('http://', line, 'адреса, яка відкриє 404 чи чужу задачу')
        # без назви — стара порада: канвас мусить мати ЦЮ задачу поточною
        plain = state.local_url_line(self.task, self.its, '', None)
        self.assertIn('перемкнись на задачу', plain)

    def test_port_is_asked_not_guessed(self):
        """Порт — той, де канвас віддає САМЕ цю задачу. Інша копія інструмента
        з іншою поточною задачею на сусідньому порту — не наш канвас."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({'id': 'bf360'}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = HTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        port = srv.server_address[1]
        old = os.environ.pop('PORT', None)
        self.addCleanup(lambda: old is not None and os.environ.__setitem__('PORT', old))
        self.assertEqual(state.find_canvas_port('bf360', ports=[port]), port)
        self.assertIsNone(state.find_canvas_port('courts', ports=[port]),
                          'канвас з ЧУЖОЮ поточною задачею прийнято за наш')


class TaskFlag(unittest.TestCase):
    """`--task <id>` (fb-07102026-e627c2): `state.py` без нього читає `current`,
    а `current` один на машину — паралельна сесія його перемикає, і «де ми зараз»
    раптом розповідає про ЧУЖУ задачу.

    ⛔ Ізоляція: `DC_TASKS_FILE` — тимчасова фікстура (живий `tasks.json` не
    чіпається); мережа вимкнена — реєстр, Supabase і пошук живого канваса
    (8765…) підмінені, тож тест не питає нічийого сервера.
    """

    def setUp(self):
        import json
        import shutil
        import tempfile
        from unittest import mock
        self.tmp = tempfile.mkdtemp(prefix='st-task-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        dirs = {}
        for tid, its in (('alpha', ['it1']), ('beta', ['it1', 'it2'])):
            dirs[tid] = os.path.join(self.tmp, tid)
            os.makedirs(dirs[tid])
            with open(os.path.join(dirs[tid], 'iterations.json'), 'w', encoding='utf-8') as fh:
                json.dump({'iterations': [{'id': i} for i in its]}, fh)
        # Локальний пін є ЛИШЕ в beta: «Відкриті коментарі» має назвати 1 саме там.
        with open(os.path.join(dirs['beta'], '.dc-local-comments.json'), 'w',
                  encoding='utf-8') as fh:
            json.dump([{'id': 'b1', 'status': 'open', 'text': 'x'}], fh)
        # `theirs` — усі ітерації чужі (для підказки «зроби копію»).
        dirs['theirs'] = os.path.join(self.tmp, 'theirs')
        os.makedirs(dirs['theirs'])
        with open(os.path.join(dirs['theirs'], 'iterations.json'), 'w', encoding='utf-8') as fh:
            json.dump({'iterations': [{'id': 'it1', 'author': 'Ольга',
                                       'author_key': 'designer2@example.test'}]}, fh)
        # `nodir` — лише реєстр (запису `dir` нема); `gone` — `dir` є, теки на
        # диску немає (реєстр їде в git, теки — ні).
        self.gone_dir = os.path.join(self.tmp, 'gone-here')
        tasks_file = os.path.join(self.tmp, 'tasks.json')
        # 4d-4b (R3): адреса й ключ Supabase — ЯВНИЙ запис `supabase-comments` простору ЛІГА (`LigaFixture`, тимчасовий дім), а не
        # `supabase_url`/`supabase_key` у корені файла (рантайм їх не читає). Файл задач пишемо ПІСЛЯ `build` — той переписує корінь.
        fx = LigaFixture(self, tmp=self.tmp)
        fx.tasks_path = tasks_file
        fx.env(DC_TASKS_FILE=tasks_file)
        fx.build(roles=('comments',),
                 overrides={'comments': {'settings': {'url': sbconf.SB_URL}, 'secrets': {'key': sbconf.SB_KEY}}}).fix_space()
        with open(tasks_file, 'w', encoding='utf-8') as fh:
            json.dump({'current': 'alpha', 'tasks': {
                'alpha': {'title': 'Альфа', 'dir': dirs['alpha'], 'profile': 'tool'},
                'beta': {'title': 'Бета', 'dir': dirs['beta'], 'profile': 'tool'},
                'theirs': {'title': 'Чужа', 'dir': dirs['theirs'], 'profile': 'tool'},
                'nodir': {'title': 'Без теки', 'profile': 'tool'},
                'gone': {'title': 'Зникла', 'dir': self.gone_dir, 'profile': 'tool'}}}, fh)
        self.tasks_file = tasks_file
        saved = {k: os.environ.get(k) for k in
                 ('DC_TASKS_FILE', 'DC_IDENTITY_NAME', 'DC_IDENTITY_EMAIL')}
        os.environ['DC_TASKS_FILE'] = tasks_file
        os.environ['DC_IDENTITY_NAME'] = 'Я'
        os.environ['DC_IDENTITY_EMAIL'] = 'me@example.test'

        def restore():
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(restore)
        self.port_calls = []

        def fake_port(tid, ports=None, timeout=0.4, explicit=False):
            self.port_calls.append({'tid': tid, 'explicit': explicit})
            return 8766
        for name, repl in (('_registry_line', lambda cfg: 'Реєстр: тест'),
                           ('find_canvas_port', fake_port)):
            patcher = mock.patch.object(state, name, repl)
            patcher.start()
            self.addCleanup(patcher.stop)
        sbconf.patch_open(self, sbconf.empty_open)           # командні піни ЛІГИ — модулем; мережі нема

    def run_main(self, argv):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = state.main(argv)
            except SystemExit as e:
                rc = e.code
        return rc, out.getvalue(), err.getvalue()

    def test_without_flag_it_is_the_current_task(self):
        rc, out, _ = self.run_main([])
        self.assertEqual(rc, 0)
        self.assertIn('«Альфа» (alpha)', out)
        self.assertIn('Ітерації (1)', out)

    def test_flag_names_the_other_task(self):
        """`current` = alpha, але `--task beta` розповідає про beta: назва, дві
        ітерації (в alpha — одна) і ЛОКАЛЬНИЙ пін, який є лише там."""
        rc, out, _ = self.run_main(['--task', 'beta'])
        self.assertEqual(rc, 0)
        self.assertIn('«Бета» (beta)', out)
        self.assertNotIn('Альфа', out)
        self.assertIn('Ітерації (2)', out)
        self.assertIn('1 локальних', out)

    def test_unknown_task_is_exit_2_and_says_nothing_about_current(self):
        rc, out, err = self.run_main(['--task', 'nope'])
        self.assertEqual(rc, 2)
        self.assertIn("error: немає задачі 'nope' у tasks.json", err)
        self.assertEqual(out, '', 'про поточну задачу не сказано ні слова')
        self.assertEqual(self.port_calls, [], 'мережу чіпали, хоча задачі немає')

    def test_task_missing_on_this_machine_is_exit_2_not_a_traceback(self):
        """Задача є в реєстрі, але теки тут нема (немає `dir` взагалі чи `dir`
        вказує в нікуди): раніше `KeyError: 'dir'` або «нова/порожня задача» — а це
        брехня. Тепер — окрема помилка, код 2, про поточну ні слова, мережі нема."""
        for tid in ('nodir', 'gone'):
            with self.subTest(tid=tid):
                self.port_calls.clear()
                rc, out, err = self.run_main(['--task', tid])
                self.assertEqual(rc, 2)
                self.assertIn(f"error: задачі '{tid}' немає на цій машині "
                              '(є в реєстрі, теки нема)', err)
                self.assertNotIn('Traceback', err)
                self.assertNotIn('нова/порожня', out)
                self.assertEqual(out, '', 'про поточну задачу не сказано ні слова')
                self.assertEqual(self.port_calls, [], 'мережу чіпали, хоча теки нема')
        self.assertFalse(os.path.exists(self.gone_dir), 'теку створено')
        # без назви поточна задача — як було
        rc, out, _ = self.run_main([])
        self.assertEqual(rc, 0)
        self.assertIn('«Альфа» (alpha)', out)

    def test_named_task_hints_with_an_endpoint_carry_the_prefix(self):
        """Через `main()`, а не лише чисті функції: `tid if named else None` має
        дійти до обох підказок із ендпоїнтом."""
        from unittest import mock
        behind = {'behind': 2, 'behind_path': 1, 'dirty': False, 'on_remote': True}
        with mock.patch.object(state, 'vcs_task', lambda tid, task: (None, {}, True, {'path': 'p'})), \
                mock.patch.object(state, 'gitlab_status', lambda *a, **k: behind):
            _, named, _ = self.run_main(['--task', 'theirs'])
            _, plain, _ = self.run_main([])
        self.assertIn('POST /t/theirs/api/gitlab-pull', named)
        self.assertIn('POST /t/theirs/api/iteration {"from": "it1"}', named)
        self.assertNotIn('POST /api/', named, 'підказка без префікса б\'є в поточну')
        self.assertNotIn('/t/', plain)
        self.assertNotIn('gitlab-pull', plain)

    # ---- роль `vcs` (етап 4a): гейт за постачальником, підпис із `label`
    def give(self, tid, **keys):
        """Дописати в запис задачі `tid` файла задач ключі (`gitlab`, `vcs`)."""
        with open(self.tasks_file, encoding='utf-8') as fh:
            cfg = json.load(fh)
        cfg['tasks'][tid].update(keys)
        with open(self.tasks_file, 'w', encoding='utf-8') as fh:
            json.dump(cfg, fh)

    def state_with(self, vcs_task, status=None, argv=('--task', 'alpha')):
        """Вивід `state.main` із підміненим постачальником (`vcs_task`) і статусом (`gitlab_status`)."""
        from unittest import mock
        stub = status if callable(status) else (lambda *a, **k: status)
        with mock.patch.object(state, 'vcs_task', vcs_task), mock.patch.object(state, 'gitlab_status', stub):
            rc, out, err = self.run_main(list(argv))
        self.assertEqual(rc, 0, err)
        return out

    def line_of(self, out, prefix):
        return next((ln for ln in out.splitlines() if ln.startswith(prefix)), None)

    def _track_header(self, **keys):
        """Шапка `state` задачі `alpha` із заданими ключами напрямку (`profile` фікстури `tool` — прибираємо, якщо не задано)."""
        self.give('alpha', **{'profile': None, 'track': None, **keys})
        return self.line_of(self.state_with(lambda tid, task: None), 'Пайплайн v')

    def test_header_shows_the_track_with_the_new_label(self):
        """4d-1: шапка показує напрямок задачі — `track`, інакше «—»; підпис «Напрямок:», не «Профіль:». 4d-4a: `profile` у записі
        більше не читається (було: лише `profile` → «Напрямок: tool»; міграція ЛІГИ дописує `track`, реєстр — на межі пулу)."""
        only_track = self._track_header(track='mobile')
        self.assertIn('Напрямок: mobile ·', only_track)
        self.assertNotIn('Профіль', only_track)
        self.assertIn('Напрямок: — ·', self._track_header(profile='tool'), 'запис лише з `profile` — напрямку нема')
        self.assertIn('Напрямок: mobile ·', self._track_header(track='mobile', profile='tool'), '`track` — єдине джерело')
        self.assertIn('Напрямок: — ·', self._track_header())

    def test_the_label_is_gitlab_in_the_liga_space_and_git_in_another_one(self):
        ok = {'behind': 0, 'dirty': False, 'on_remote': True}
        legacy = self.state_with(lambda tid, task: (None, {}, True, {'path': 'p'}), ok)
        self.assertIn('GitLab (p): синхронізовано', legacy)
        other = self.state_with(lambda tid, task: (None, {}, False, {'path': 'p'}), ok)
        self.assertIn('Git (p): синхронізовано', other)
        self.assertNotIn('GitLab', other)

    def test_the_label_of_the_status_wins_over_the_default(self):
        """Підпис — з `label` статусу (модуль каже «GitHub»); ЛІГА його перекриває сама, у `serve.gitlab_status`."""
        st = {'behind': 2, 'behind_path': 1, 'dirty': False, 'on_remote': True, 'label': 'GitHub'}
        out = self.state_with(lambda tid, task: (None, {}, False, {'path': 'p'}), st)
        self.assertIn('GitHub (p): ⚠ на GitHub НОВІШЕ (2)', out)
        self.assertNotIn('GitLab', out)

    def test_a_space_without_the_role_or_a_task_without_a_target_is_not_set_up(self):
        out = self.state_with(lambda tid, task: None)
        self.assertEqual(self.line_of(out, 'GitLab:'), 'GitLab: не налаштований для задачі')
        out = self.state_with(lambda tid, task: (None, {}, False, None))
        self.assertEqual(self.line_of(out, 'Git:'), 'Git: не налаштований для задачі')

    def test_a_refusing_provider_for_a_task_with_no_target_of_its_own_is_not_set_up(self):
        """Поправка 2: задача без `gitlab` і без `vcs` ніколи нічого не мала — «не дістати статус» їй брехало б (і кричало б
        на кожній задачі при зламаному каталозі)."""
        from unittest import mock

        def refuse(tid, task):
            raise VcsError('vcs-error', 'git-sync module is not loaded')
        out = self.state_with(refuse)
        self.assertEqual(self.line_of(out, 'GitLab:'), 'GitLab: не налаштований для задачі')
        self.assertNotIn('не дістати', out)

    def test_a_refusing_provider_for_a_task_with_a_target_says_it_cannot_get_the_status(self):
        def refuse(tid, task):
            raise VcsError('space-json-unreadable', 'space.json is not readable')
        for key, val in (('gitlab', {'repo': 'git@h:o/r.git', 'path': 'mockup/alpha'}), ('vcs', {'repo': '/x/r.git'})):
            with self.subTest(key=key):
                self.give('alpha', **{key: val})
                out = self.state_with(refuse)
                self.assertEqual(self.line_of(out, 'GitLab:'), 'GitLab: не дістати статус (space.json is not readable)')
                self.give('alpha', **{key: None})

    def test_a_token_in_what_the_status_raises_never_reaches_the_output(self):
        token = 'ghp_SECRETTOKEN123'

        def boom(*a, **k):
            raise OSError(f'clone of https://{token}@github.com/o/r.git failed')
        out = self.state_with(lambda tid, task: (None, {}, False, {'path': 'p'}), boom)
        self.assertNotIn(token, out)
        self.assertIn('Git: не дістати статус (clone of https://***@github.com/o/r.git failed)', out)

    def test_a_token_in_what_the_provider_raises_never_reaches_the_output(self):
        token = 'ghp_SECRETTOKEN123'

        def boom(tid, task):
            raise OSError(f'provider of https://{token}@github.com/o/r.git failed')
        self.give('alpha', vcs={'repo': '/x/r.git'})
        out = self.state_with(boom)
        self.assertNotIn(token, out)
        self.assertIn('GitLab: не дістати статус (provider of https://***@github.com/o/r.git failed)', out)

    def test_a_busy_mirror_in_the_status_says_to_try_again(self):
        """Поправка 7: і коли статус каже `vcs-busy` словником, і коли це летить винятком."""
        busy = {'configured': True, 'error': 'mirror is busy', 'code': 'vcs-busy'}
        out = self.state_with(lambda tid, task: (None, {}, False, {'path': 'p'}), busy)
        self.assertIn('Git (p): зайнято (іде синхронізація), спробуй ще раз', out)
        self.assertNotIn('помилка', out)

        def raises(*a, **k):
            raise VcsError('vcs-busy', 'mirror is busy')
        out = self.state_with(lambda tid, task: (None, {}, False, {'path': 'p'}), raises)
        self.assertIn('Git (p): зайнято', out)
        self.assertNotIn('не дістати', out)

    def test_the_status_is_asked_with_the_provider_triple_and_the_target(self):
        seen = []

        def status(task, gl, meta, it, vcs=None):
            seen.append((gl, it, vcs))
            return {'behind': 0, 'dirty': False, 'on_remote': True}
        triple = (object(), {'k': 1}, False)
        self.state_with(lambda tid, task: (*triple, {'path': 'p'}), status)
        self.assertEqual(seen, [({'path': 'p'}, 'it1', triple)])

    def test_shared_comments_off_in_an_isolated_run_have_a_clear_line(self):
        """n6 (4d-4b): закон ізоляції для справжнього дому дає `ModuleError('comments-isolated')` — раніше рядок був загальним «не дістати
        (comments-isolated)», тепер каже, ЩО це і чому. Дім «справжній» імітуємо підміною `isolation.real_home` (стенд лежить у тимчасовому)."""
        import isolation
        from unittest import mock
        with mock.patch.object(isolation, 'real_home', return_value=True):
            rc, out, _ = self.run_main(['--task', 'alpha'])
        self.assertEqual(rc, 0)
        line = self.line_of(out, 'Відкриті коментарі')
        self.assertIsNotNone(line, out)
        self.assertIn('спільні коментарі вимкнено в ізольованому (тестовому) запуску', line)
        self.assertNotIn('comments-isolated', line, 'код не показуємо замість пояснення')
        self.assertNotIn('не дістати', line)

    def test_empty_id_is_not_the_current_task(self):
        """`--task ''` — це ЯВНА (порожня) назва, а не «не задано»."""
        rc, out, err = self.run_main(['--task', ''])
        self.assertEqual(rc, 2)
        self.assertEqual(out, '')

    def test_flag_is_in_help(self):
        rc, out, _ = self.run_main(['--help'])
        self.assertEqual(rc, 0)
        self.assertIn('--task', out)
        self.assertIn('паралельних сесій', out)

    def test_unknown_argument_is_an_error_not_silence(self):
        rc, _, err = self.run_main(['--tsak', 'beta'])
        self.assertEqual(rc, 2)
        self.assertIn('--tsak', err)

    def test_canvas_is_asked_for_the_named_task(self):
        """Задачу названо — живий канвас питаємо про НЕЇ, а не про його поточну."""
        self.run_main(['--task', 'beta'])
        self.run_main([])
        self.assertEqual(self.port_calls, [{'tid': 'beta', 'explicit': True},
                                           {'tid': 'alpha', 'explicit': False}])

    def test_printed_urls_carry_the_task_prefix_only_when_named(self):
        """Без префікса `/t/<id>/` адреса відкриє ПОТОЧНУ задачу канваса — тобто
        після `--task beta` вела б у чужий макет, коли current інший."""
        _, named, _ = self.run_main(['--task', 'beta'])
        self.assertIn('http://127.0.0.1:8766/t/beta/it-assets/it2/index.html', named)
        self.assertNotIn('/t/beta/commented', named)
        _, plain, _ = self.run_main([])
        self.assertIn('http://127.0.0.1:8766/it-assets/it1/index.html', plain)
        self.assertNotIn('/t/', plain)

    def test_inbox_hint_repeats_the_flag(self):
        """Підказка «→ python3 bin/inbox.py» копіюється дослівно: без `--task`
        вона відкрила б інбокс поточної задачі, а не названої."""
        _, named, _ = self.run_main(['--task', 'beta'])
        self.assertIn('→ python3 bin/inbox.py --task beta', named)


class CanvasProbe(unittest.TestCase):
    """`find_canvas_port`: з `explicit` питає `/t/<id>/api/task` (без заголовка)."""

    def _probe(self, tid='beta', **kw):
        from unittest import mock
        seen = []

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps({'id': tid}).encode()

        def fake(req, timeout=None):
            seen.append({'url': req.full_url,
                         'headers': {k.lower(): v for k, v in req.header_items()}})
            return R()
        with mock.patch('urllib.request.urlopen', fake):
            port = state.find_canvas_port(tid, ports=[9], **kw)
        return port, seen

    def test_named_task_is_probed_through_the_prefix(self):
        """Адреси, які друкує `state.py`, несуть префікс `/t/<id>/`, тож і порт
        перевіряємо ним. Заголовок `X-Canvas-Task` старий (не перезапущений)
        канвас ігнорує й відповідає про ПОТОЧНУ — «підходить», а друковані
        адреси далі дали б йому 404."""
        port, seen = self._probe(explicit=True)
        self.assertEqual(port, 9)
        self.assertEqual(seen[0]['url'], 'http://127.0.0.1:9/t/beta/api/task')
        self.assertNotIn('x-canvas-task', seen[0]['headers'])

    def test_named_task_id_is_quoted_in_the_probe_path(self):
        _, seen = self._probe('a b/c', explicit=True)
        self.assertEqual(seen[0]['url'], 'http://127.0.0.1:9/t/a%20b%2Fc/api/task')

    def test_old_canvas_without_the_prefix_is_not_a_match(self):
        """Старий канвас на `/t/beta/api/task` дає 404 → порт пропущено, хоч
        його поточна задача — саме beta (так «збіг» був би хибним)."""
        from unittest import mock
        import urllib.error

        def fake(req, timeout=None):
            if '/t/' in req.full_url:
                raise urllib.error.HTTPError(req.full_url, 404, 'nf', {}, None)
            raise AssertionError('named probe fell back to the bare path')
        with mock.patch('urllib.request.urlopen', fake):
            self.assertIsNone(state.find_canvas_port('beta', ports=[9], explicit=True))

    def test_current_task_sends_no_header_and_no_prefix(self):
        """Без явної задачі семантика стара: порт підходить, лише якщо ТАМ
        поточна саме ця задача — тож ні заголовок, ні префікс не годяться."""
        port, seen = self._probe()
        self.assertEqual(port, 9)
        self.assertEqual(seen[0]['url'], 'http://127.0.0.1:9/api/task')
        self.assertNotIn('x-canvas-task', seen[0]['headers'])


if __name__ == '__main__':
    unittest.main()
