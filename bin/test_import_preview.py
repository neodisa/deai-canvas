"""Тести `bin/import_preview.py` — імпорт ітерації з ЧУЖОГО опублікованого превʼю.

fb-29092026-210ec1: дві машини публікували одну задачу в різні Vercel-проєкти, і
ітерації колеги довелось переносити руками — зняти сніпет коментатора й гейт,
відновити title з `__origTitle`. Тепер це команда. Перевіряємо:
  · вирізання вставок публікації — КОЛОВИМ тестом на тих самих функціях, якими
    `serve._publish` їх вставляє (розійдуться — тест червоніє);
  · дерево сторінок із `manifest.outline`;
  · збирання файлів за посиланнями (статичний хостинг переліку не віддає);
  · ітерація — ЧУЖА (джерело — превʼю) + моя робоча копія поруч (правило
    15.09.2026: робота не починається поверх чужої ітерації).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'app'))
import import_preview as ip  # noqa: E402
import serve  # noqa: E402

PAGE = ('<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8">'
        '<title>Картка «Ромашка»</title><link rel="stylesheet" href="../assets/app.css">'
        '</head><body><h1>Картка</h1><img src="../icons/a.svg" srcset="../icons/a.svg 1x, ../icons/a@2x.svg 2x">'
        '<script type="module" src="../main.js"></script></body></html>')


def published(html, depth_up='../'):
    """Рівно те, що робить `serve._publish` зі сторінкою."""
    out = serve.inject_comment_layer(html, 'chan', f'{depth_up}comment-layer', version='1/kartka')
    return serve._inject_gate(out, serve.gate_html('t', '1100'))


class Strip(unittest.TestCase):
    def test_roundtrip_restores_page_byte_for_byte(self):
        clean, ok = ip.strip_publish(published(PAGE))
        self.assertTrue(ok)
        self.assertEqual(clean, PAGE)

    def test_page_without_title_roundtrips_too(self):
        page = PAGE.replace('<title>Картка «Ромашка»</title>', '')
        self.assertEqual(ip.strip_publish(published(page)), (page, True))

    def test_page_without_injections_is_untouched_and_said(self):
        self.assertEqual(ip.strip_publish(PAGE), (PAGE, False))


class Outline(unittest.TestCase):
    def test_flat_outline_becomes_tree_of_one_iteration(self):
        outline = [
            {'it': 'it2', 'key': 'w', 'name': 'Віджет', 'kind': 'folder', 'depth': 0},
            {'it': 'it2', 'key': 'kartka', 'name': 'Картка', 'kind': 'page', 'depth': 1},
            {'it': 'it2', 'key': 's-err', 'name': 'Помилка', 'kind': 'state', 'depth': 2},
            {'it': 'it2', 'key': 'osoba', 'name': 'Особа', 'kind': 'page', 'depth': 0},
            {'it': 'it1', 'key': 'old', 'name': 'Стара', 'kind': 'page', 'depth': 0},
        ]
        tree = ip.outline_tree(outline, 'it2')
        self.assertEqual(tree, [
            {'id': 'w', 'name': 'Віджет', 'kind': 'folder', 'children': [
                {'id': 'kartka', 'name': 'Картка', 'kind': 'page', 'children': [
                    {'id': 's-err', 'name': 'Помилка', 'kind': 'state'}]}]},
            {'id': 'osoba', 'name': 'Особа', 'kind': 'page'}])


class Refs(unittest.TestCase):
    def test_html_css_js_references(self):
        self.assertEqual(ip.refs(PAGE, 'html'),
                         {'../assets/app.css', '../icons/a.svg', '../icons/a@2x.svg', '../main.js'})
        self.assertEqual(ip.refs("@import 'base.css'; a{background:url(\"../img/bg.png\")} b{src:url(f.woff2)}", 'css'),
                         {'base.css', '../img/bg.png', 'f.woff2'})
        self.assertEqual(ip.refs('import("./chunk-AB12.js");const i="assets/x.svg";fetch("https://cdn/x.js")', 'js'),
                         {'./chunk-AB12.js', 'assets/x.svg'})

    def test_external_data_and_anchor_refs_are_ignored(self):
        html = '<a href="#top"></a><img src="data:image/png;base64,AA"><script src="https://cdn.x/y.js"></script>'
        self.assertEqual(ip.refs(html, 'html'), set())

    def test_root_relative_and_encoded_anchor_refs_are_not_iteration_files(self):
        """Реальний boss-interface it15: 252 «не знайдено» — шляхи даних від кореня
        сайту (`/trademarks/…jpg`, 404 і в самому превʼю) та `%23n` (закодований якір)."""
        self.assertEqual(ip.refs('const a="/trademarks/1.jpg";', 'js'), set())
        self.assertEqual(ip.refs('<a href="%23n">x</a><img src="img/a%20b.png">', 'html'), {'img/a b.png'})


class ImportIteration(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, 'iterations', 'it1'))
        with open(os.path.join(self.d, 'iterations', 'it1', 'index.html'), 'w') as f:
            f.write('<html><body>моя</body></html>')
        with open(os.path.join(self.d, 'iterations.json'), 'w') as f:
            json.dump({'iterations': [{'id': 'it1', 'date': '01.10.2026 10:00', 'note': 'моя', 'published': True}]}, f)
        base = 'https://pv-x.vercel.app'
        man = {'iters': [{'id': 'it3', 'num': 3, 'note': 'колега'}, {'id': 'it5', 'num': 5, 'note': 'остання'}],
               'pages': [{'id': 'it5/kartka', 'it': 'it5', 'key': 'kartka', 'name': 'Картка', 'depth': 0,
                          'path': 'it5/kartka/index.html'}],
               'outline': [{'it': 'it5', 'key': 'kartka', 'name': 'Картка', 'kind': 'page', 'depth': 0}]}
        self.site = {
            f'{base}/manifest.json': json.dumps(man).encode(),
            f'{base}/it5/kartka/index.html': published(PAGE).encode(),
            f'{base}/it5/assets/app.css': b"@import 'fonts.css';.x{background:url(../icons/bg.png)}",
            f'{base}/it5/assets/fonts.css': b'',
            f'{base}/it5/icons/a.svg': b'<svg/>',
            f'{base}/it5/icons/bg.png': b'PNG',
            f'{base}/it5/main.js': b'import("./chunk-1.js")',
            f'{base}/it5/chunk-1.js': b'export const x=1',
        }
        self.base = base

    def fetch(self, url):
        if url in getattr(self, 'down', ()):
            raise ip.FetchError(f'{url}: timed out')
        if url in self.site:
            return self.site[url]
        raise ip.FetchError(f'404 {url}', code=404)

    def test_404_in_source_is_not_an_import_failure_but_network_is(self):
        """Усе, що превʼю віддає 404, бите й у колеги (на boss-interface it15 — 200
        шрифтів із вшитого beasties CSS, на вигляд не впливає). Справжній збій
        імпорту — лише мережа: його кажемо окремо й гучно."""
        self.down = {f'{self.base}/it5/chunk-1.js'}
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertEqual(rep['broken'], ['icons/a@2x.svg'])
        self.assertEqual(rep['failed'], ['chunk-1.js'])

    def test_imports_latest_iteration_as_foreign_plus_my_working_copy(self):
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertEqual((rep['imported'], rep['working']), ('it2', 'it3'))
        self.assertEqual(rep['source_it'], 'it5')
        self.assertEqual(rep['broken'], ['icons/a@2x.svg'])
        self.assertEqual(rep['failed'], [])
        root = os.path.join(self.d, 'iterations', 'it2')
        with open(os.path.join(root, 'kartka', 'index.html'), encoding='utf-8') as f:
            self.assertEqual(f.read(), PAGE, 'сторінка не очищена від вставок публікації')
        for rel in ('assets/app.css', 'assets/fonts.css', 'icons/bg.png', 'main.js', 'chunk-1.js'):
            self.assertTrue(os.path.isfile(os.path.join(root, rel)), rel)
        self.assertFalse(os.path.exists(os.path.join(root, 'comment-layer')))
        with open(os.path.join(root, 'pages.json'), encoding='utf-8') as f:
            self.assertEqual(json.load(f)['pages'][0]['id'], 'kartka')
        self.assertTrue(os.path.isfile(os.path.join(self.d, 'iterations', 'it3', 'kartka', 'index.html')))
        with open(os.path.join(self.d, 'iterations.json'), encoding='utf-8') as f:
            its = {i['id']: i for i in json.load(f)['iterations']}
        self.assertEqual(its['it2']['from_preview'], f'{self.base} · it5')
        self.assertTrue(its['it2']['author_key'].startswith('preview:'))
        self.assertFalse(serve.iteration_is_mine(its['it2'], 'my-key'), 'імпорт виглядає моїм')
        self.assertEqual(its['it3']['from'], 'it2')
        self.assertFalse(its['it2']['published'])

    def test_explicit_source_iteration_and_unknown_one(self):
        self.site[f'{self.base}/it3/index.html'] = published(PAGE.replace('../', ''), '').encode()
        man = json.loads(self.site[f'{self.base}/manifest.json'])
        man['pages'].append({'id': 'it3', 'it': 'it3', 'key': 'main', 'name': 'Головна', 'depth': 0,
                             'path': 'it3/index.html'})
        self.site[f'{self.base}/manifest.json'] = json.dumps(man).encode()
        rep = ip.import_iteration(self.d, self.base, src_it='it3', fetch=self.fetch)
        self.assertEqual(rep['source_it'], 'it3')
        with self.assertRaises(ip.ImportError_) as ctx:
            ip.import_iteration(self.d, self.base, src_it='it9', fetch=self.fetch)
        self.assertIn('it9', str(ctx.exception))

    def test_hostile_manifest_cannot_write_outside_the_iteration(self):
        """Ревʼю 1.51 (висока): шлях сторінки з manifest.json — чужі дані. `..`,
        абсолютний шлях чи `%2e%2e` не сміють вивести запис за теку ітерації
        (інакше «превʼю колеги» перезаписало б ~/.zshrc)."""
        for bad in ('it5/../../../evil.html', '/etc/evil.html', 'it5/%2e%2e/%2e%2e/evil.html',
                    'it5/kartka/../../../../evil.html'):
            man = json.loads(self.site[f'{self.base}/manifest.json'])
            man['pages'] = [{'id': 'x', 'it': 'it5', 'key': 'x', 'name': 'x', 'depth': 0, 'path': bad}]
            self.site[f'{self.base}/manifest.json'] = json.dumps(man).encode()
            self.site[f'{self.base}/{bad.lstrip("/")}'] = b'<html>evil</html>'
            with self.subTest(path=bad), self.assertRaises(ip.ImportError_):
                ip.import_iteration(self.d, self.base, fetch=self.fetch)
        parent = os.path.dirname(self.d)
        self.assertFalse(any(n == 'evil.html' for n in os.listdir(parent)), 'файл записано поза задачею')

    def test_crawled_links_cannot_leave_the_iteration(self):
        """Посилання зі сторінки на `../../x` не стає файлом поза ітерацією."""
        self.site[f'{self.base}/it5/kartka/index.html'] = published(
            PAGE.replace('../main.js', '../../../../escape.js')).encode()
        self.site[f'{self.base}/escape.js'] = b'evil'
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch)
        self.assertNotIn('escape.js', os.listdir(os.path.dirname(self.d)))
        self.assertFalse(any('..' in p for p in rep['broken'] + rep['failed']))

    def test_oversized_file_is_failed_not_written_and_total_is_capped(self):
        """TD-36: чуже превʼю не сміє закачати гігабайти — файл понад ліміт не
        пишемо (його видно в «не скачано»), сумарний обсяг понад ліміт — відмова."""
        self.site[f'{self.base}/it5/icons/bg.png'] = b'x' * (ip.MAX_FILE + 1)
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertIn('icons/bg.png', rep['failed'])
        old = ip.MAX_TOTAL
        try:
            ip.MAX_TOTAL = 10
            with self.assertRaises(ip.ImportError_):
                ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        finally:
            ip.MAX_TOTAL = old

    def test_redirect_to_another_host_is_refused(self):
        h = ip.SameHostRedirect()
        req = ip.urllib.request.Request('https://pv-1.vercel.app/it5/a.css')
        with self.assertRaises(ip.urllib.error.HTTPError):
            h.redirect_request(req, None, 302, 'Found', {}, 'https://evil.example/a.css')
        self.assertIsNotNone(h.redirect_request(req, None, 302, 'Found', {}, 'https://pv-1.vercel.app/it5/b.css'))

    def test_dry_run_writes_nothing(self):
        before = sorted(os.listdir(os.path.join(self.d, 'iterations')))
        rep = ip.import_iteration(self.d, self.base, fetch=self.fetch, dry_run=True)
        self.assertEqual(sorted(os.listdir(os.path.join(self.d, 'iterations'))), before)
        self.assertGreater(rep['files'], 5)


if __name__ == '__main__':
    unittest.main()
