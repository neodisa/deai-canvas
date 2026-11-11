"""Редагування діагностики (0.23, T1): домашній шлях → `~`, ключі/токени → `‹приховано›`, e-mail → `‹e-mail›`, query URL відрізається."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app'))
import redact  # noqa: E402

HIDDEN, MAIL = '‹приховано›', '‹e-mail›'


class Redact(unittest.TestCase):
    def test_home_becomes_tilde_both_forms(self):
        home = os.path.expanduser('~')
        self.assertEqual(redact.text('open %s/work/x.json failed' % home), 'open ~/work/x.json failed')
        self.assertEqual(redact.text('%s' % home), '~')

    def test_roots_are_labelled_longest_first(self):
        roots = [('/data/space/a', '<space>'), ('/data/space/a/tasks', '<tasks>')]
        self.assertEqual(redact.text('x /data/space/a/tasks/it1 y', roots=roots), 'x <tasks>/it1 y')

    def test_key_like_strings(self):
        samples = [
            'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoiYW5vbiJ9.abcDEF123_-xyz',   # JWT
            'sk-' + 'A1b2C3d4E5f6G7h8I9j0',                                                # sk-…
            'sb_publishable_' + 'Abc123Def456Ghi789Jkl',
            'ghp_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8',
            'glpat-' + 'A1b2C3d4E5f6G7h8I9j0',
            'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0',                                     # довгий base64-подібний
            '0123456789abcdef0123456789abcdef01234567',                                    # довгий hex
        ]
        for s in samples:
            with self.subTest(s=s[:12]):
                out = redact.text('token=%s end' % s)
                self.assertNotIn(s, out)
                self.assertIn(HIDDEN, out)

    def test_innocent_long_words_and_paths_survive(self):
        for s in ('internationalization-and-localization-settings',      # лише літери
                  '/very/long/path/segment/that/goes/on/and/on/file.js',
                  'iterations/it1/holovna/index.html', '1234567890'):
            self.assertEqual(redact.text(s), s, s)

    def test_email_and_url_query(self):
        self.assertEqual(redact.text('write alpha@example.com now'), 'write %s now' % MAIL)
        self.assertEqual(redact.text('GET https://h.example/a/b?token=zzz&x=1 failed'), 'GET https://h.example/a/b failed')
        self.assertEqual(redact.text('GET /api/task?it=it1'), 'GET /api/task')

    def test_userinfo_same_as_serve_mask_repo(self):
        import serve
        for s in ('clone https://TOKEN@git.example/o/r.git', 'x ssh://user:p@ss@host/r', 'plain text'):
            self.assertEqual(redact.userinfo(s), serve._mask_repo(s), s)

    def test_limit_and_non_string(self):
        self.assertEqual(len(redact.text('x' * 1000, limit=300)), 300)
        self.assertEqual(redact.text(None), '')
        self.assertEqual(redact.text(5), '5')

    def test_order_secret_before_email_inside_url_and_idempotent(self):
        once = redact.text('https://u:pw@h.example/x?k=1 alpha@example.com ' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0')
        self.assertEqual(redact.text(once), once)
        # userinfo має піти раніше за e-mail: інакше `pw@h.example` стає «e-mail», а `u:` лишається
        self.assertEqual(once, 'https://***@h.example/x %s %s' % (MAIL, HIDDEN))


if __name__ == '__main__':
    unittest.main()
