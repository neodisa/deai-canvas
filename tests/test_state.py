"""`state.py`: рядок стану GitLab не має права заспокоювати даремно.

Фідбек 29.07.2026: для задачі, якої на GitLab узагалі немає, друкувалось
«синхронізовано» — бо наздоганяти нічого і локально все чисто.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin'))
import state  # noqa: E402


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

    def test_no_live_canvas_gives_advice_not_a_dead_url(self):
        line = state.local_url_line(self.task, self.its, '', None)
        self.assertIn('start.command', line)
        self.assertNotIn('http://', line, 'адреса, яка відкриє 404 чи чужу задачу')

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


if __name__ == '__main__':
    unittest.main()
