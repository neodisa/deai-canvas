"""Редагування діагностики (0.23, T1): домашній шлях → `~`, ключі/токени → `‹приховано›`, e-mail → `‹e-mail›`, query URL відрізається."""
import os
import sys
import unittest
from unittest import mock

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
                  'iterations/it1/holovna/index.html', 'v0.23.0 at app.js:123 2026-11-11T10:20:30Z 1.2.3 :9999999 (7 digits)'):
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


    # --- 0.23: PII (ЄДРПОУ/ІПН/картка/IBAN), мітки секретів, чужі домівки, шляхи ---
    def test_long_digit_runs_hidden_but_lines_versions_dates_survive(self):
        for s in ('ЄДРПОУ 12345678', 'ІПН 1234567890', 'phone 380441234567', 'card 4111111111111111', 'card 4111 1111 1111 1111', 'card 4111-1111-1111-1111'):
            out = redact.text(s)
            self.assertIn(HIDDEN, out, s)
            self.assertFalse(any(c.isdigit() for c in out.replace('ЄДРПОУ', '')), out)
        for s in ('at x.js:12345', 'version 0.23.0', 'ver 12.345.6789', '2026-11-11', '2026-11-11T10:20:30Z', 'line 1234567', 'ports 8765 4317'):
            self.assertEqual(redact.text(s), s, s)

    def test_iban_hidden_plain_and_spaced(self):
        self.assertEqual(redact.text('pay UA213223130000026007233566001 now'), 'pay %s now' % HIDDEN)
        self.assertEqual(redact.text('pay DE89370400440532013000 now'), 'pay %s now' % HIDDEN)
        self.assertEqual(redact.text('pay UA21 3223 1300 0002 6007 2335 6600 1 now'), 'pay %s now' % HIDDEN)
        self.assertEqual(redact.text('ERROR_CODE and HTTP2 stay'), 'ERROR_CODE and HTTP2 stay')

    def test_labelled_secrets_keep_the_label_hide_the_value(self):
        cases = {'api_key=abc123': 'api_key=%s', 'API-KEY: abc123': 'API-KEY: %s', 'token: tok': 'token: %s', 'secret = s3': 'secret = %s',
                 'password=hunter2': 'password=%s', 'passwd: x': 'passwd: %s', 'Authorization: Bearer zzz.yyy': 'Authorization: %s',
                 '{"token": "ab cd"}': '{"token": %s}', "password='a b'": 'password=%s', 'apikey=k': 'apikey=%s'}
        for src, want in cases.items():
            out = redact.text(src)
            self.assertEqual(out.replace('}', '').replace(HIDDEN, 'H'), (want % 'H').replace('}', ''), src)
            self.assertNotIn('hunter2', out)
            self.assertEqual(redact.text(out), out, 'ідемпотентно: %s' % src)
        self.assertNotIn('zzz', redact.text('Authorization: Bearer zzz.yyy'))
        self.assertNotIn('cd', redact.text('{"token": "ab cd"}').replace('{', ''))

    def test_other_users_homes_become_tilde(self):
        self.assertEqual(redact.text('open /Users/zed/work/a.json'), 'open ~/work/a.json')
        self.assertEqual(redact.text('open /home/zed/work/a.json'), 'open ~/work/a.json')
        self.assertEqual(redact.text('open C:\\Users\\Іван\\proj\\a.py'), 'open ~\\proj\\a.py')
        self.assertEqual(redact.text('open file:///Users/zed/a.json'), 'open file://~/a.json')

    def test_windows_forward_slash_home_is_not_mangled(self):
        self.assertEqual(redact.text('open C:/Users/zed/a.py'), 'open ~/a.py')
        with mock.patch.object(redact, '_homes', return_value=['/Users/me']):
            self.assertEqual(redact.text('open C:/Users/me/a.py'), 'open ~/a.py')
            self.assertEqual(redact.text('open /Users/me/a.py'), 'open ~/a.py')
        self.assertNotIn('C:~', redact.text('C:/Users/zed/a'))
        # домівка Windows у зворотних слешах, а шлях — у прямих: лише форма з `/` його впізнає (правило `Users` тут не рятує)
        with mock.patch.object(redact.os.path, 'expanduser', return_value='C:\\Work\\me'), mock.patch.object(redact, 'pwd', None):
            self.assertEqual(redact.text('open C:/Work/me/a.py'), 'open ~/a.py')
            self.assertEqual(redact.text('open C:\\Work\\me\\a.py'), 'open ~\\a.py')

    def test_every_absolute_path_collapses_to_the_last_segment(self):
        cases = {
            '/Users/me/ClientB-Acme/x/y.json': '…/y.json', '/Volumes/Work/ClientB/z.py:12': '…/z.py:12', 'C:\\Users\\Іван\\proj\\a.py': '…/a.py',
            'C:/proj/ClientB/a.py': '…/a.py', '\\\\srv\\share\\ClientB\\f.txt': '…/f.txt', 'file:///Users/me/ClientB/d.json': '…/d.json',
            '~/ClientB/x/y': '…/y', '%2FUsers%2Fme%2FClientB%2Fx.json': '…/x.json', 'file%3A%2F%2F%2FUsers%2Fme%2FClientB%2Fx.json': '…/x.json',
            '%5CUsers%5Cme%5CClientB%5Cx.json': '…/x.json',
        }
        for src, want in cases.items():
            out = redact.paths('open %s failed' % src)
            self.assertEqual(out, 'open %s failed' % want, src)
            self.assertEqual(redact.paths(out), out, 'ідемпотентно')
        self.assertEqual(redact.paths('File "/a b/Client B/e.py", line 3'), 'File "…/e.py", line 3')
        for keep in ('https://h.example/a', 'http://h.example', '<space>/x/y', '<task>/it1', 'iterations/it1/index.html', './x/y', '../x', 'and/or', 'a / b'):
            self.assertEqual(redact.paths(keep), keep, keep)

    def test_urls_keep_only_scheme_host_and_last_segment(self):
        c = lambda v: redact.text(v, collapse=True)
        self.assertEqual(c('fetch http://localhost:8765/t/acme-corp/it-assets/it1/Клієнт/x.png failed'), 'fetch http://localhost:8765/…/*.png failed')
        out = c('http://localhost:8765/t/acme/it-assets/it1/%D0%9A%D0%BB%D1%96/%D1%84%D0%B0.png?v=1&token=zz')
        self.assertEqual(out, 'http://localhost:8765/…/*.png')
        self.assertNotIn('acme', out)
        self.assertEqual(c('GET https://api.example.com/v1/users/42?token=abc#frag'), 'GET https://api.example.com/…/42')
        for keep in ('https://h.example/a', 'http://h.example'):
            self.assertEqual(c(keep), keep)
        self.assertEqual(c(c('http://localhost:8765/t/a/b/c.png')), 'http://localhost:8765/…/*.png', 'ідемпотентно')

    def test_local_urls_keep_only_the_file_extension(self):
        c = lambda v: redact.text(v, collapse=True)
        out = c('http://localhost:8765/t/acme-corp/it-assets/it1/LIGA-12345-acme-corp.PNG')
        self.assertEqual(out, 'http://localhost:8765/…/*.png')
        for bad in ('acme', 'LIGA-12345'):
            self.assertNotIn(bad, out)
        out = c('x http://127.0.0.1:8765/t/acme-corp y')
        self.assertEqual(out, 'x http://127.0.0.1:8765/…/… y')
        self.assertNotIn('acme', out)
        self.assertNotIn('acme', c('http://[::1]:8765/acme-corp/report.pdf'))
        self.assertEqual(c('https://ext.example/t/acme/x.png'), 'https://ext.example/…/*.png')
        self.assertEqual(c('https://ext.example/v1/acme-corp.png'), 'https://ext.example/…/acme-corp.png')
        self.assertEqual(c(c('http://127.0.0.1:8765/t/acme-corp')), 'http://127.0.0.1:8765/…/…', 'ідемпотентно')

    def test_double_escaped_windows_path_outside_quotes(self):
        self.assertEqual(redact.paths('open C:\\\\Users\\\\bob\\\\Acme\\\\x now'), 'open …/x now')

    def test_text_collapse_flag(self):
        self.assertEqual(redact.text('open /Users/me/ClientB-Acme/x/y.json', collapse=True), 'open …/y.json')
        self.assertEqual(redact.text('open /data/space/a/tasks/x', roots=[('/data/space/a', '<space>')], collapse=True), 'open <space>/tasks/x')
        self.assertIn('ClientB-Acme', redact.text('open /opt/ClientB-Acme/x'), 'без collapse шляхи лишаються (крім домівок)')


if __name__ == '__main__':
    unittest.main()
