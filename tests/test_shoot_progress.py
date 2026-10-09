import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from shoot_progress import MARK, ShootProgress, parse_progress_line


class ParseLine(unittest.TestCase):
    def test_marked_line_becomes_event(self):
        ev = parse_progress_line(MARK + '{"ev":"frame","i":2,"total":8}')
        self.assertEqual(ev, {'ev': 'frame', 'i': 2, 'total': 8})

    def test_line_without_marker_is_not_an_event(self):
        # Це текст причини для дизайнера — він мусить лишитись у stderr
        self.assertIsNone(parse_progress_line('Error: chromium is not installed'))

    def test_broken_json_after_marker_does_not_raise(self):
        # Обрізаний рядок буває, коли процес убили посеред запису
        self.assertIsNone(parse_progress_line(MARK + '{"ev":"fra'))

    def test_non_object_after_marker_is_rejected(self):
        self.assertIsNone(parse_progress_line(MARK + '"рядок"'))
        self.assertIsNone(parse_progress_line(MARK + '[1,2]'))

    def test_object_without_ev_is_rejected(self):
        self.assertIsNone(parse_progress_line(MARK + '{"i":1}'))

    def test_trailing_newline_is_tolerated(self):
        self.assertEqual(parse_progress_line(MARK + '{"ev":"done"}\n'), {'ev': 'done'})


class State(unittest.TestCase):
    def test_start_sets_total_and_running(self):
        p = ShootProgress()
        p.apply({'ev': 'start', 'total': 8})
        snap = p.snapshot()
        self.assertTrue(snap['running'])
        self.assertEqual(snap['total'], 8)
        self.assertEqual(snap['done'], 0)

    def test_frames_accumulate_and_carry_what_canvas_needs(self):
        """Канвас підміняє картинку по `sha`, тому подія мусить його донести."""
        p = ShootProgress()
        p.apply({'ev': 'start', 'total': 2})
        p.apply({'ev': 'frame', 'i': 1, 'key': 'holovna', 'sha': 'aa',
                 'stamp': 'st1', 'capturedAt': '01.09.2026 10:00', 'w': 1280, 'h': 900})
        snap = p.snapshot()
        self.assertEqual(snap['done'], 1)
        # ВСІ ТРИ складові ключа кеша, не лише sha — інакше канвас побудує інший
        # URL, ніж наступний повний рендер, і той самий webp поїде вдруге
        self.assertEqual(snap['frames'], [{'key': 'holovna', 'sha': 'aa', 'stamp': 'st1',
                                           'capturedAt': '01.09.2026 10:00',
                                           'w': 1280, 'h': 900}])
        self.assertEqual(snap['current'], 'holovna')

    def test_full_frame_list_survives_missed_polls(self):
        """Опитування може пропустити такт — тому віддаємо ПЕРЕЛІК, не останній кадр."""
        p = ShootProgress()
        p.apply({'ev': 'start', 'total': 3})
        for i, key in enumerate(['a', 'b', 'c'], start=1):
            p.apply({'ev': 'frame', 'i': i, 'key': key, 'sha': key * 2,
                     'stamp': 's', 'capturedAt': 't', 'w': 10, 'h': 20})
        self.assertEqual([f['key'] for f in p.snapshot()['frames']], ['a', 'b', 'c'])

    def test_fail_counts_but_is_not_a_frame(self):
        p = ShootProgress()
        p.apply({'ev': 'start', 'total': 2})
        p.apply({'ev': 'fail', 'i': 1, 'key': 'main', 'problem': 'сторінка віддала 404'})
        snap = p.snapshot()
        self.assertEqual(snap['done'], 1, 'провалений кадр теж пройдено')
        self.assertEqual(snap['frames'], [], 'але картинки для нього немає')
        self.assertEqual(snap['failed'], [{'key': 'main', 'problem': 'сторінка віддала 404'}])

    def test_done_stops_running(self):
        p = ShootProgress()
        p.apply({'ev': 'start', 'total': 1})
        p.apply({'ev': 'done', 'shot': 1, 'failed': 0})
        self.assertFalse(p.snapshot()['running'])

    def test_unknown_event_is_ignored_not_fatal(self):
        """Нова версія shoot.mjs поруч зі старим сервером не сміє валити прогрес."""
        p = ShootProgress()
        p.apply({'ev': 'start', 'total': 1})
        p.apply({'ev': 'щось-нове', 'x': 1})
        self.assertTrue(p.snapshot()['running'])

    def test_finish_marks_not_running_even_without_done(self):
        """Процес убили — події `done` не буде НІКОЛИ, а `running` мусить згаснути."""
        p = ShootProgress()
        p.apply({'ev': 'start', 'total': 5})
        p.finish(stopped=True)
        snap = p.snapshot()
        self.assertFalse(snap['running'])
        self.assertTrue(snap['stopped'])


class MarkerContract(unittest.TestCase):
    def test_marker_matches_node_side(self):
        """⛔ Два боки контракту в різних мовах. Розійдуться — прогрес мовчить,
        і мовчить ПРАВДОПОДІБНО: зʼємка йде, лічильник стоїть на нулі."""
        node = os.path.join(os.path.dirname(__file__), '..', 'bin', 'shots-progress.mjs')
        with open(node, encoding='utf-8') as f:
            src = f.read()
        self.assertIn(f'export const PROGRESS_MARK = "{MARK}"', src)


if __name__ == '__main__':
    unittest.main()
