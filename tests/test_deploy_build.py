"""bin/deploy-build-to-iteration.command — хірургічна чистка теки ітерації.

Фідбек 25.08.2026: скрипт робив `cp -R` без жодної чистки, а Angular дає кожній
збірці нове імʼя з контент-хешем — за сесію в одній ітерації назбиралось 18
старих `main-*.js` по ~800 кБ, і всі вони їхали в GitLab та в publish/.

Сторожимо саме межу «мотлох / робота дизайнера»: у теці ітерації поруч зі
збіркою живуть pages.json, .canvas-state.json, shots/, підтеки сторінок і
рукотворні файли. Тому тест перевіряє ОБИДВІ умови видалення нарізно:
  (а) імʼя схоже на хешований бандл  → інакше під ніж піде pages.json;
  (б) файлу НЕМА в новій збірці      → інакше під ніж піде свіжий бандл.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'bin', 'deploy-build-to-iteration.command')

# Реальні імена з $HOME/deai-work/boss-interface/iterations/it2:
# Angular esbuild дає 8 символів [A-Z0-9]. Хеші фікстури тримаємо в тому ж форматі.
OLD_BUNDLES = ('main-OLD11111.js', 'polyfills-OLD22222.js', 'styles-OLD33333.css')
FRESH_BUNDLE = 'main-NEWHASH1.js'          # хешований, але ПРИЙШОВ цією збіркою
NEW_BUNDLE = 'styles-NEWHASH2.css'         # тільки в збірці, у теці його ще нема
# Усе, що мусить пережити чистку. index.html тут навмисно немає: він рукотворний,
# але збірка кладе свій — його перевіряємо окремо (вміст, а не сам факт).
KEPT_FILES = ('pages.json', '.canvas-state.json', 'theme.css', 'snippet.js',
              'notes.md', FRESH_BUNDLE)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


class DeployBuildCleanupTest(unittest.TestCase):
    """Один прогін скрипта на фікстурі; кожен тест дивиться на свій бік результату."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='dc-deploy-')
        cls.dist = os.path.join(cls.tmp, 'dist')
        cls.it = os.path.join(cls.tmp, 'iterations', 'it1')

        # Нова збірка: index.html із правильним base-href + два бандли.
        write(os.path.join(cls.dist, 'index.html'),
              '<!DOCTYPE html><html><head><base href="/it-assets/it1/">'
              '</head><body>ЗБІРКА</body></html>')
        write(os.path.join(cls.dist, FRESH_BUNDLE), 'x' * 100)
        write(os.path.join(cls.dist, NEW_BUNDLE), 'y' * 100)

        # Тека ітерації ДО деплою: мотлох попередніх збірок + робота дизайнера.
        for b in OLD_BUNDLES:
            write(os.path.join(cls.it, b), 'z' * 4096)
        write(os.path.join(cls.it, FRESH_BUNDLE), 'x' * 100)
        write(os.path.join(cls.it, 'pages.json'), '{"pages":[]}')
        write(os.path.join(cls.it, '.canvas-state.json'), '{"published":true}')
        write(os.path.join(cls.it, 'theme.css'), '/* рукотворний */')
        write(os.path.join(cls.it, 'snippet.js'), '// рукотворний')
        write(os.path.join(cls.it, 'notes.md'), 'нотатки дизайнера')
        write(os.path.join(cls.it, 'index.html'), 'РУКОТВОРНИЙ')
        write(os.path.join(cls.it, 'shots', 'main.webp'), 'кадр канваса')
        write(os.path.join(cls.it, 'home', 'index.html'), 'сторінка home')

        # HOME підмінений: якщо перевизначення теки раптом перестане діяти, скрипт
        # піде за зашитим шляхом і зіпсує ФІКСТУРУ, а не робочу копію дизайнера.
        cls.home = tempfile.mkdtemp(prefix='dc-home-')
        env = dict(os.environ, HOME=cls.home, DC_ITERATION_DIR=cls.it)
        cls.proc = subprocess.run([SCRIPT, cls.dist, 'fixture', 'it1'],
                                 capture_output=True, text=True, env=env)

    @classmethod
    def tearDownClass(cls):
        for d in (cls.tmp, cls.home):
            shutil.rmtree(d, ignore_errors=True)

    def test_1_script_succeeds_and_copies_the_build(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        self.assertIn('base-href ok', self.proc.stdout)
        # Новий бандл приїхав, а рукотворний index.html перекритий збірковим —
        # це і є нормальна робота `cp`, чистка їй не заважає.
        self.assertTrue(os.path.exists(os.path.join(self.it, NEW_BUNDLE)))
        with open(os.path.join(self.it, 'index.html'), encoding='utf-8') as fh:
            self.assertIn('ЗБІРКА', fh.read())

    def test_2_stale_hashed_bundles_are_gone(self):
        for b in OLD_BUNDLES:
            self.assertFalse(os.path.exists(os.path.join(self.it, b)),
                             f'{b} мусив зникнути')

    def test_3_everything_else_survives(self):
        # Умова (а): без фільтра по хешу сюди прилетить pages.json / theme.css.
        for name in KEPT_FILES:
            self.assertTrue(os.path.exists(os.path.join(self.it, name)),
                            f'{name} мусив лишитись')
        with open(os.path.join(self.it, 'notes.md'), encoding='utf-8') as fh:
            self.assertEqual('нотатки дизайнера', fh.read())
        # Кадри канваса й підтеки сторінок — теж робота, не збірка.
        self.assertTrue(os.path.exists(os.path.join(self.it, 'shots', 'main.webp')))
        self.assertTrue(os.path.exists(os.path.join(self.it, 'home', 'index.html')))

    def test_4_fresh_bundle_of_this_build_is_never_touched(self):
        # Умова (б). Спостережуване — ЗВІТ: після `cp` видалений-і-скопійований
        # файл на диску не відрізнити від недоторканого, а звіт відрізняє.
        self.assertNotIn(FRESH_BUNDLE, self.proc.stdout)
        self.assertTrue(os.path.exists(os.path.join(self.it, FRESH_BUNDLE)))

    def test_5_cleanup_reports_what_it_removed_and_how_much(self):
        # Мовчазна чистка гірша за жодну: дизайнер має бачити, що зник мотлох.
        for b in OLD_BUNDLES:
            self.assertIn(b, self.proc.stdout)
        self.assertIn('прибрано застарілих бандлів: 3', self.proc.stdout)
        self.assertIn('звільнено 12 кБ', self.proc.stdout)   # 3 × 4096 Б

    def test_6_real_destination_is_still_the_default(self):
        # Перевизначення — тільки для тестів. Якщо рефакторинг згубить зашитий
        # шлях, реальний вжиток зламається молча: скрипт покладе збірку не туди.
        with open(SCRIPT, encoding='utf-8') as fh:
            src = fh.read()
        self.assertIn('${DC_ITERATION_DIR:-$HOME/deai-work/'
                      '$TASK/iterations/$IT}', src)
        # І зашитий шлях не мусить бути зачеплений прогоном на фікстурі.
        self.assertFalse(os.path.exists(os.path.join(self.home, 'Liga')))


if __name__ == '__main__':
    unittest.main()
