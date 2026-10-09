"""ops/canvas-app — точка входу в канвас: launch.sh (клік/автостарт) і install.sh.

Зовнішній світ (curl, open, osascript, launchctl, lsregister, start.command) —
заглушки в PATH: кожна дописує свій виклик у calls.log. Так тест бачить, ЩО
скрипт зробив би з Chrome і launchd, не чіпаючи справжніх.

Спека: docs/superpowers/specs/2026-10-09-canvas-app-design.md
"""
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = os.path.join(ROOT, 'ops', 'canvas-app')
URL = 'http://localhost:8765/app/'

STUBS = {
    # Сервер «живий», коли існує файл $STUB_UP.
    'curl': '[ -f "$STUB_UP" ] && printf 200 || printf 000\n',
    'open': (
        'echo "open $*" >> "$STUB_LOG"\n'
        'if [ "$1" = "-Ra" ]; then [ -n "${STUB_NO_CHROME:-}" ] && exit 1; exit 0; fi\n'
        # Шим застосунку (`….app`) не відкрився — launch.sh мусить упасти в --app.
        'case "$1" in *.app) if [ -n "${STUB_SHIM_FAILS:-}" ]; then exit 1; fi ;; esac\n'
        'exit 0\n'
    ),
    # Spotlight: launch.sh НЕ сміє його кликати (індекс може відставати, а сам
    # `mdfind` не обмежити за часом) — заглушка лише фіксує спробу.
    'mdfind': 'echo "mdfind $*" >> "$STUB_LOG"\n',
    # Алерт і пошук вікна розрізняємо за текстом скрипта зі stdin.
    'osascript': (
        'src="$(cat)"\n'
        'case "$src" in\n'
        '  *"display alert"*) echo "osascript-alert $*" >> "$STUB_LOG" ;;\n'
        '  *) echo "osascript-focus $*" >> "$STUB_LOG"\n'
        '     printf "%s" "$src" > "$STUB_LOG.focus"\n'
        '     [ "${STUB_FOCUS:-none}" = error ] && exit 1\n'
        '     echo "${STUB_FOCUS:-none}" ;;\n'
        'esac\n'
    ),
    'launchctl': (
        'echo "launchctl $*" >> "$STUB_LOG"\n'
        'if [ "$1" = print ]; then [ -n "${STUB_LOADED:-}" ] && exit 0; exit 113; fi\n'
        # Формат macOS 13+: `"мітка" => disabled`.
        'if [ "$1" = print-disabled ] && [ -n "${STUB_DISABLED:-}" ]; then\n'
        '  printf \'disabled services = {\\n\\t"app.deai.designcanvas.autostart" => disabled\\n}\\n\'; fi\n'
        'if [ "$1" = bootstrap ] && [ -n "${STUB_BOOTSTRAP_FAIL:-}" ]; then\n'
        '  echo "Bootstrap failed: 5: Input/output error" >&2; exit 5; fi\n'
        'exit 0\n'
    ),
    'lsregister': 'echo "lsregister $*" >> "$STUB_LOG"\n',
    'start': (
        'echo start >> "$STUB_LOG"\n'
        '[ -n "${STUB_START_BRINGS_UP:-}" ] && touch "$STUB_UP"\n'
        'exit 0\n'
    ),
}


def write_exec(path, body):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('#!/bin/bash\n' + body)
    os.chmod(path, 0o755)


class StubWorld(unittest.TestCase):
    """Тимчасова тека з заглушками; кожен тест — свій світ."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='dc-app-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, 'bin')
        for name, body in STUBS.items():
            write_exec(os.path.join(self.bin, name), body)
        self.home = os.path.join(self.tmp, 'home')
        os.makedirs(self.home)
        self.log = os.path.join(self.tmp, 'calls.log')
        self.up_flag = os.path.join(self.tmp, 'up')
        # python3 і git потрібні install.sh; беремо той python, що ганяє тест.
        self.path = ':'.join([self.bin, os.path.dirname(sys.executable),
                              '/usr/bin', '/bin', '/usr/sbin', '/sbin'])

    def env(self, **extra):
        e = {'PATH': self.path, 'HOME': self.home, 'STUB_LOG': self.log,
             'STUB_UP': self.up_flag, 'CANVAS_START': os.path.join(self.bin, 'start'),
             'CANVAS_WAIT': '1'}
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def run_script(self, script, *args, umask=None, **extra):
        return subprocess.run(['/bin/bash', script, *args], env=self.env(**extra),
                              capture_output=True, text=True, timeout=60,
                              preexec_fn=(lambda: os.umask(umask)) if umask is not None else None)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log, encoding='utf-8') as f:
            return f.read().splitlines()

    def server_up(self):
        open(self.up_flag, 'w').close()


class LaunchTest(StubWorld):
    LAUNCH = os.path.join(OPS, 'launch.sh')
    APP_WINDOW = f'open -na Google Chrome --args --app={URL}'

    def test_live_server_opens_app_window_without_restart(self):
        self.server_up()
        r = self.run_script(self.LAUNCH)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.APP_WINDOW, self.calls())
        self.assertNotIn('start', self.calls())

    def test_dead_server_is_started_once_then_window_opens(self):
        r = self.run_script(self.LAUNCH, STUB_START_BRINGS_UP=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual(calls.count('start'), 1)
        self.assertIn(self.APP_WINDOW, calls)
        self.assertLess(calls.index('start'), calls.index(self.APP_WINDOW))

    def test_server_that_never_answers_alerts_and_opens_nothing(self):
        r = self.run_script(self.LAUNCH)
        self.assertEqual(r.returncode, 1)
        alerts = [c for c in self.calls() if c.startswith('osascript-alert')]
        self.assertEqual(len(alerts), 1, self.calls())
        self.assertIn('Канвас не піднявся', alerts[0])
        self.assertIn('design-canvas.log', alerts[0])
        self.assertFalse([c for c in self.calls() if c.startswith('open -na')])

    def test_existing_canvas_window_is_focused_not_duplicated(self):
        self.server_up()
        r = self.run_script(self.LAUNCH, STUB_FOCUS='focused')
        self.assertEqual(r.returncode, 0, r.stderr)
        # 0 — сервер уже працював: вкладку не перезавантажуємо (там робота).
        self.assertIn(f'osascript-focus - {URL} 0', self.calls())
        self.assertNotIn(self.APP_WINDOW, self.calls())

    def test_focus_acts_on_window_by_id_not_by_position(self):
        # Живий прогін 09.10.2026: `w` з `repeat with w in windows` — це «N-те
        # вікно», і після activate воно вже вказувало на ІНШЕ вікно. Наперед
        # виходило чуже вікно в ~половині прогонів (z-порядок CoreGraphics),
        # а скрипт звітував «focused». Тому все, що змінює вікно, — лише через
        # `window id`.
        self.server_up()
        self.run_script(self.LAUNCH, STUB_FOCUS='focused')
        with open(self.log + '.focus', encoding='utf-8') as f:
            src = f.read()
        self.assertIn('set cw to window id wid', src)
        self.assertIn('set index of cw to 1', src)
        self.assertNotRegex(src, r'set (index|visible|minimized|active tab index) of w\b')

    def test_window_found_after_starting_servers_is_reloaded(self):
        # Ревʼю 09.10.2026: після ребуту Chrome відновлює вікно канваса раніше,
        # ніж піднявся сервер, — наперед вийшла б сторінка помилки.
        r = self.run_script(self.LAUNCH, STUB_START_BRINGS_UP=1, STUB_FOCUS='focused')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f'osascript-focus - {URL} 1', self.calls())
        with open(self.log + '.focus', encoding='utf-8') as f:
            src = f.read()
        self.assertIn('tell active tab of cw to reload', src)

    def test_denied_automation_falls_back_to_new_window(self):
        self.server_up()
        r = self.run_script(self.LAUNCH, STUB_FOCUS='error')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.APP_WINDOW, self.calls())

    def test_without_chrome_uses_default_browser_and_never_asks_chrome(self):
        # Компіляція `tell application "Google Chrome"` без Chrome відкриває
        # діалог «Де Google Chrome?» — тому AppleScript до Chrome взагалі не йде.
        self.server_up()
        r = self.run_script(self.LAUNCH, STUB_NO_CHROME=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f'open {URL}', self.calls())
        self.assertFalse([c for c in self.calls() if c.startswith('osascript')])

    def test_servers_only_never_touches_windows(self):
        r = self.run_script(self.LAUNCH, '--servers-only', STUB_START_BRINGS_UP=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ['start'])

    def test_servers_only_failure_goes_to_log_not_to_a_dialog(self):
        # Автостарт іде з launchd при вході — модальне вікно там нікому не потрібне.
        r = self.run_script(self.LAUNCH, '--servers-only')
        self.assertEqual(r.returncode, 1)
        self.assertIn('Канвас не піднявся', r.stderr)
        self.assertEqual(self.calls(), ['start'])


class LaunchInstalledPwaTest(StubWorld):
    """P2 (спека PWA, «Запускач на Mac»): якщо застосунок «Deai Canvas» (PWA)
    встановлено, клік відкриває САМЕ його — зі своїм значком у Dock і
    `focus-existing` із маніфесту, — а не `--app`-вікно Chrome.

    Іd застосунку Chrome рахує з маніфесту, і тут він ЗАКРІПЛЕНИЙ (`APP_ID`):
    зміна `id` в `app/manifest.webmanifest` осиротила б усі вже встановлені
    застосунки (інший id — інший застосунок), тож тест має червоніти.
    """
    LAUNCH = os.path.join(OPS, 'launch.sh')
    APP_WINDOW = f'open -na Google Chrome --args --app={URL}'
    # SHA-256(SHA-256(`http://localhost:8765/app/`)) → перші 16 байт → hex → a–p.
    APP_ID = 'chgggamegiklgilfhgfenefbepaopcnc'
    # Власний тестовий вектор Chromium (components/webapps/docs/identifiers.md,
    # web_app_helpers unittest): цей URL мусить дати саме цей id.
    CHROMIUM_URL = 'https://www.chromestatus.com/features'
    CHROMIUM_ID = 'fedbieoalmbobgfjapopkghdmhgncnaa'

    def shim_dir(self):
        return os.path.join(self.home, 'Applications', 'Chrome Apps.localized')

    def install_shim(self, app_id=None, name='Deai Canvas', prefix='', base=None):
        """Шим, який Chrome кладе при встановленні PWA: `<імʼя>.app` з Info.plist,
        де `CFBundleIdentifier` = `com.google.Chrome.app.<id>` (у старих збірках з
        префіксом профілю: `…app.Default-<id>`)."""
        app_id = app_id or self.APP_ID
        path = os.path.join(base or self.shim_dir(), f'{name}.app')
        os.makedirs(os.path.join(path, 'Contents'))
        with open(os.path.join(path, 'Contents', 'Info.plist'), 'wb') as f:
            plistlib.dump({
                'CFBundleIdentifier': f'com.google.Chrome.app.{prefix}{app_id}',
                'CrAppModeShortcutID': app_id,
                'CrAppModeShortcutName': name,
                'CrAppModeShortcutURL': URL,
            }, f)
        return path

    def opens(self):
        return [c for c in self.calls() if c.startswith('open ')]

    # ── id застосунку ────────────────────────────────────────────────────────

    def print_id(self, manifest=None, url=URL):
        extra = {'CANVAS_URL': url}
        if manifest is not None:
            path = os.path.join(self.tmp, 'manifest.webmanifest')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(manifest)
            extra['CANVAS_MANIFEST'] = path
        return self.run_script(self.LAUNCH, '--print-pwa-id', **extra)

    def test_app_id_of_the_canvas_is_pinned(self):
        r = self.print_id()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), self.APP_ID)
        # Це печатка, а не запуск: ні серверів, ні вікон.
        self.assertEqual(self.calls(), [])

    def test_app_id_algorithm_matches_chromiums_own_vector(self):
        # Хеш двічі (SHA-256 від SHA-256), а НЕ один раз: одинарний на цьому ж
        # векторі дав би chbclfccioppcmeobikpicoffkehaela. Перевірено ще й на
        # 15 справжніх шимах `~/Applications/Chrome Apps.localized`.
        r = self.print_id('{"id": "/features"}', url='https://www.chromestatus.com/app/')
        self.assertEqual(r.stdout.strip(), self.CHROMIUM_ID, r.stderr)

    def test_manifest_id_is_resolved_against_the_origin_and_loses_its_fragment(self):
        r = self.print_id('{"id": "/features#ignored"}', url='https://www.chromestatus.com/app/')
        self.assertEqual(r.stdout.strip(), self.CHROMIUM_ID)

    def test_relative_manifest_id_is_resolved_against_the_origin_not_the_start_path(self):
        # Chrome розвʼязує `id` відносно ORIGIN start_url (`/app/` тут не береться):
        # `features` → https://www.chromestatus.com/features, а не …/app/features.
        r = self.print_id('{"id": "features", "start_url": "/app/"}',
                          url='https://www.chromestatus.com/app/')
        self.assertEqual(r.stdout.strip(), self.CHROMIUM_ID)

    def test_default_shim_directories_are_the_users_and_the_system_wide_one(self):
        # Системну `/Applications/Chrome Apps.localized` у тесті не підмінити
        # (піддається лише `CANVAS_PWA_DIRS`), тож закріплюємо типовий перелік
        # текстом: Chrome ставить шими в `~/Applications` або, за вибором при
        # встановленні, у `/Applications`.
        with open(self.LAUNCH, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('$HOME/Applications/Chrome Apps.localized', text)
        self.assertIn(':/Applications/Chrome Apps.localized', text)

    def test_without_manifest_id_the_start_url_is_the_id(self):
        # Правило Chrome: нема `id` — ManifestId це start_url (відносно маніфесту).
        r = self.print_id('{"start_url": "/features"}', url='https://www.chromestatus.com/app/')
        self.assertEqual(r.stdout.strip(), self.CHROMIUM_ID)

    def test_default_port_is_dropped_like_gurl_does(self):
        a = self.print_id('{"id": "/features"}', url='https://www.chromestatus.com:443/app/')
        self.assertEqual(a.stdout.strip(), self.CHROMIUM_ID)

    def test_unreadable_manifest_prints_nothing(self):
        r = self.run_script(self.LAUNCH, '--print-pwa-id',
                            CANVAS_MANIFEST=os.path.join(self.tmp, 'нема-такого'))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), '')

    # ── запуск ───────────────────────────────────────────────────────────────

    def test_installed_pwa_is_opened_instead_of_the_app_window(self):
        self.server_up()
        shim = self.install_shim()
        r = self.run_script(self.LAUNCH)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.opens(), [f'open {shim}'])
        # Ні `--app`-вікна, ні пошуку вікна: фокус існуючого — справа самого
        # застосунку (`launch_handler: focus-existing`).
        self.assertNotIn(self.APP_WINDOW, self.calls())
        self.assertFalse([c for c in self.calls() if c.startswith('osascript')])

    def test_not_installed_keeps_the_old_behaviour(self):
        self.server_up()
        r = self.run_script(self.LAUNCH)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.APP_WINDOW, self.calls())

    def test_another_pwa_shim_is_not_ours(self):
        self.server_up()
        self.install_shim(app_id='fmpnliohjhemenmnlpbfagaolkdacoja', name='Claude')
        r = self.run_script(self.LAUNCH)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.APP_WINDOW, self.calls())
        self.assertFalse([c for c in self.opens() if c.endswith('.app') and 'Claude' in c])

    def test_shim_with_a_profile_prefix_is_found(self):
        # Старі збірки Chrome: `com.google.Chrome.app.Default-<id>`.
        self.server_up()
        shim = self.install_shim(prefix='Default-')
        r = self.run_script(self.LAUNCH)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.opens(), [f'open {shim}'])

    def test_system_wide_shim_directory_is_searched_too(self):
        self.server_up()
        sysdir = os.path.join(self.tmp, 'system-apps')
        shim = self.install_shim(base=sysdir)
        r = self.run_script(self.LAUNCH, CANVAS_PWA_DIRS=f'{self.shim_dir()}:{sysdir}')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.opens(), [f'open {shim}'])

    def test_shim_that_fails_to_open_falls_back_to_the_app_window(self):
        # Не блокуємо запуск: відмова шима не лишає людину без вікна.
        self.server_up()
        shim = self.install_shim()
        r = self.run_script(self.LAUNCH, STUB_SHIM_FAILS=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.opens()[0], f'open {shim}')
        self.assertIn(self.APP_WINDOW, self.calls())

    def test_unreadable_manifest_falls_back_to_the_app_window(self):
        self.server_up()
        self.install_shim()
        r = self.run_script(self.LAUNCH, CANVAS_MANIFEST=os.path.join(self.tmp, 'нема-такого'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(self.APP_WINDOW, self.calls())

    def test_spotlight_is_never_asked(self):
        # `mdfind` залежить від індексу, що відстає після встановлення, і його не
        # обмежити за часом — а запуск не сміє зависати. Шукаємо в файловій
        # системі.
        self.server_up()
        self.install_shim()
        self.run_script(self.LAUNCH)
        self.assertFalse([c for c in self.calls() if c.startswith('mdfind')])

    def test_dead_server_is_started_first_then_the_pwa_opens(self):
        shim = self.install_shim()
        r = self.run_script(self.LAUNCH, STUB_START_BRINGS_UP=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.calls()
        self.assertEqual(calls.count('start'), 1)
        self.assertLess(calls.index('start'), calls.index(f'open {shim}'))
        self.assertNotIn(self.APP_WINDOW, calls)

    def test_server_that_never_answers_opens_neither_pwa_nor_window(self):
        self.install_shim()
        r = self.run_script(self.LAUNCH)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.opens(), [])

    def test_servers_only_never_opens_the_pwa(self):
        self.install_shim()
        r = self.run_script(self.LAUNCH, '--servers-only', STUB_START_BRINGS_UP=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), ['start'])

    def test_pwa_does_not_need_chrome_to_be_found_by_open_ra(self):
        # Шим сам знаходить Chrome; `open -Ra "Google Chrome"` на цій гілці не
        # потрібен — застосунок відкривається і там, де його перевірка мовчить.
        self.server_up()
        shim = self.install_shim()
        r = self.run_script(self.LAUNCH, STUB_NO_CHROME=1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.opens(), [f'open {shim}'])

    def test_lookup_is_fast(self):
        # «Не блокує запуск»: пошук шима — python3 + кілька grep, не секунди.
        # Межа щедра (CI буває повільним): ловить регрес на кшталт mdfind чи
        # мережі, а не мікросекунди.
        import time
        self.server_up()
        for n in range(30):
            self.install_shim(app_id=('a' * 31) + chr(ord('a') + n % 16), name=f'Other {n}')
        self.install_shim()
        t0 = time.monotonic()
        r = self.run_script(self.LAUNCH, '--print-pwa-id')
        self.assertLess(time.monotonic() - t0, 1.0, r.stderr)


class AppleScriptCompilesTest(unittest.TestCase):
    """Кожен AppleScript-фрагмент (heredoc <<'OSA') компілюється.

    Скрипти глушать stderr osascript (2>/dev/null) — синтаксична помилка там
    виглядала б як «вікна канваса нема» чи як мовчазний алерт, а заглушки в
    решті тестів AppleScript не виконують зовсім.
    """

    def test_every_osa_heredoc_compiles(self):
        if shutil.which('osacompile') is None:
            self.skipTest('нема osacompile (не macOS)')
        # Без Chrome компіляція `tell application "Google Chrome"` відкриває
        # діалог «Де Google Chrome?» і тест завис би.
        if subprocess.run(['open', '-Ra', 'Google Chrome'], capture_output=True).returncode:
            self.skipTest('нема Google Chrome')
        found = 0
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('launch.sh', 'install.sh'):
                with open(os.path.join(OPS, name), encoding='utf-8') as f:
                    text = f.read()
                for n, chunk in enumerate(text.split("<<'OSA'\n")[1:]):
                    src = chunk.split('\nOSA\n')[0]
                    path = os.path.join(tmp, f'{name}-{n}.applescript')
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(src)
                    r = subprocess.run(['osacompile', '-o', path + '.scpt', path],
                                       capture_output=True, text=True, timeout=30)
                    self.assertEqual(r.returncode, 0, f'{name} #{n}: {r.stderr}\n{src}')
                    found += 1
        self.assertEqual(found, 3)   # launch.sh: алерт + фокус; install.sh: алерт запускача


class InstallTest(StubWorld):
    """install.sh на фікстурі-копії: шлях із пробілом і апострофом, як у
    справжньому `~/Liga Tools/…` (і гірше), launch.sh — заглушка, що записує,
    з яким PATH її запустили."""

    BUNDLE_ID = 'app.deai.designcanvas'
    LABEL = 'app.deai.designcanvas.autostart'

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "Liga Tools's")
        self.ops = os.path.join(self.repo, 'design-canvas', 'ops', 'canvas-app')
        os.makedirs(self.ops)
        shutil.copy(os.path.join(OPS, 'install.sh'), self.ops)
        with open(os.path.join(self.ops, 'DesignCanvas.icns'), 'wb') as f:
            f.write(b'icns-stub')
        self.launch = os.path.join(self.ops, 'launch.sh')
        self.path_seen = os.path.join(self.tmp, 'path-seen')
        write_exec(self.launch, f'echo "$PATH" > "{self.path_seen}"\n')
        with open(os.path.join(self.repo, 'VERSION'), 'w') as f:
            f.write('1.52.0\n')
        self.apps = os.path.join(self.tmp, 'Applications')
        self.agents = os.path.join(self.tmp, 'LaunchAgents')
        self.app = os.path.join(self.apps, 'Design Canvas.app')
        self.info = os.path.join(self.app, 'Contents', 'Info.plist')
        self.exe = os.path.join(self.app, 'Contents', 'MacOS', 'design-canvas')
        self.plist = os.path.join(self.agents, self.LABEL + '.plist')
        self.domain = f'gui/{os.getuid()}'

    def install(self, *args, script=None, **extra):
        extra.setdefault('CANVAS_APP_DIR', self.apps)
        extra.setdefault('CANVAS_AGENTS_DIR', self.agents)
        extra.setdefault('CANVAS_LSREGISTER', os.path.join(self.bin, 'lsregister'))
        return self.run_script(script or os.path.join(self.ops, 'install.sh'),
                               *args, **extra)

    def run_launcher(self):
        # Як із Dock: мінімальний PATH, жодного ~/.zshrc.
        return subprocess.run([self.exe], capture_output=True, text=True, timeout=30,
                              env={'PATH': '/usr/bin:/bin', 'HOME': self.home,
                                   'STUB_LOG': self.log})

    def read_plist(self, path):
        with open(path, 'rb') as f:
            return plistlib.load(f)

    def git_fixture(self):
        """Робить фікстуру git-репо з ворктрі; повертає install.sh у ворктрі."""
        env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null')

        def git(*a, cwd=self.repo):
            subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *a],
                           cwd=cwd, env=env, check=True, capture_output=True)
        git('init', '-q')
        git('add', '-A')
        git('commit', '-qm', 'fixture')
        wt = os.path.join(self.tmp, 'wt')
        git('worktree', 'add', '-q', wt)
        return os.path.join(wt, 'design-canvas', 'ops', 'canvas-app', 'install.sh')

    # --- збирання ---

    def test_builds_app_bundle_with_our_identity(self):
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        info = self.read_plist(self.info)
        self.assertEqual(info['CFBundleIdentifier'], self.BUNDLE_ID)
        self.assertEqual(info['CFBundlePackageType'], 'APPL')
        self.assertEqual(info['CFBundleShortVersionString'], '1.52.0')
        self.assertEqual(info['LigaCanvasLaunch'], self.launch)
        exe = os.path.join(self.app, 'Contents', 'MacOS', info['CFBundleExecutable'])
        self.assertTrue(os.access(exe, os.X_OK))
        icon = os.path.join(self.app, 'Contents', 'Resources', info['CFBundleIconFile'] + '.icns')
        self.assertTrue(os.path.isfile(icon))
        self.assertIn(f'lsregister -f {self.app}', self.calls())

    def test_launcher_brings_install_time_path_to_launch_sh(self):
        # Головна причина застосунку: з Dock нема ~/.zshrc, а з ним node/python.
        self.install()
        r = self.run_launcher()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.path_seen) as f:
            self.assertEqual(f.read().strip(), self.path)

    def test_launcher_without_launch_sh_says_so(self):
        self.install()
        os.remove(self.launch)
        r = self.run_launcher()
        self.assertEqual(r.returncode, 1)
        alerts = [c for c in self.calls() if c.startswith('osascript-alert')]
        self.assertEqual(len(alerts), 1, self.calls())
        self.assertIn(self.launch, alerts[0])

    def test_autostart_agent_runs_servers_only_without_keepalive(self):
        self.install()
        agent = self.read_plist(self.plist)
        self.assertEqual(agent['Label'], self.LABEL)
        self.assertEqual(agent['ProgramArguments'], ['/bin/bash', self.launch, '--servers-only'])
        self.assertEqual(agent['EnvironmentVariables']['PATH'], self.path)
        self.assertIs(agent['RunAtLoad'], True)
        self.assertIs(agent['AbandonProcessGroup'], True)
        # KeepAlive зламав би stop.command і бився б зі start.command за порт.
        self.assertNotIn('KeepAlive', agent)
        self.assertIn(f'launchctl bootstrap {self.domain} {self.plist}', self.calls())

    def test_reinstall_replaces_own_app(self):
        self.assertEqual(self.install().returncode, 0)
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_plist(self.info)['CFBundleIdentifier'], self.BUNDLE_ID)

    def test_warns_when_node_is_not_on_path(self):
        if shutil.which('node', path=self.path):
            self.skipTest('node лежить поруч із python3 — нема як прибрати з PATH')
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('node', r.stdout)

    # --- чуже не чіпаємо ---

    def test_foreign_app_with_same_name_is_left_alone(self):
        os.makedirs(os.path.dirname(self.info))
        with open(self.info, 'wb') as f:
            plistlib.dump({'CFBundleIdentifier': 'com.example.other'}, f)
        r = self.install()
        self.assertEqual(r.returncode, 1)
        self.assertIn('не наш', r.stderr)
        r = self.install('--uninstall')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.read_plist(self.info)['CFBundleIdentifier'], 'com.example.other')

    def test_uninstall_removes_app_and_agent(self):
        self.install()
        r = self.install('--uninstall')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(self.app))
        self.assertFalse(os.path.exists(self.plist))
        self.assertIn(f'launchctl bootout {self.domain}/{self.LABEL}', self.calls())

    # --- --check ---

    def test_check_before_install_fails(self):
        r = self.install('--check', STUB_LOADED=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn('нема', r.stdout)

    def test_check_passes_on_fresh_install(self):
        self.install()
        r = self.install('--check', STUB_LOADED=1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_fails_when_agent_not_loaded(self):
        self.install()
        r = self.install('--check')
        self.assertEqual(r.returncode, 1)
        self.assertIn('автостарт', r.stdout)

    def test_check_fails_when_launch_sh_is_gone(self):
        self.install()
        os.remove(self.launch)
        r = self.install('--check', STUB_LOADED=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn(self.launch, r.stdout)

    # --- ворктрі ---

    def test_refuses_to_install_from_git_worktree(self):
        r = self.install(script=self.git_fixture())
        self.assertEqual(r.returncode, 1)
        self.assertIn('ворктрі', r.stderr)
        self.assertFalse(os.path.exists(self.app))
        self.assertFalse(os.path.exists(self.plist))

    def test_worktree_allowed_explicitly_for_development(self):
        r = self.install(script=self.git_fixture(), CANVAS_ALLOW_WORKTREE=1)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_main_git_checkout_is_fine(self):
        self.git_fixture()
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)

    # --- ревʼю 09.10.2026 ---

    def test_failed_build_leaves_nothing_that_locks_reinstall(self):
        # Збій посеред збирання (тут — нечитабельна іконка) лишав .app без
        # Info.plist: далі і install, і --uninstall відмовлялись — «не наш».
        icon = os.path.join(self.ops, 'DesignCanvas.icns')
        os.chmod(icon, 0)
        r = self.install()
        os.chmod(icon, 0o644)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.app))
        self.assertEqual([n for n in os.listdir(self.apps) if 'Design Canvas' in n], [])
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read_plist(self.info)['CFBundleIdentifier'], self.BUNDLE_ID)

    def test_failed_rebuild_keeps_previous_working_app(self):
        self.install()
        icon = os.path.join(self.ops, 'DesignCanvas.icns')
        os.chmod(icon, 0)
        r = self.install()
        os.chmod(icon, 0o644)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.read_plist(self.info)['CFBundleIdentifier'], self.BUNDLE_ID)
        self.assertEqual(self.run_launcher().returncode, 0)

    def test_agent_plist_is_not_group_writable(self):
        # launchd відкидає plist, у який може писати група (umask 002).
        r = self.install(umask=0o002)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.stat(self.plist).st_mode & 0o022, 0)

    def test_rejected_bootstrap_is_explained(self):
        r = self.install(STUB_BOOTSTRAP_FAIL=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn('launchd не прийняв автостарт', r.stderr)
        self.assertIn('Input/output error', r.stderr)
        self.assertTrue(os.path.isdir(self.app))   # застосунок зібраний і працює

    def test_check_sees_autostart_switched_off_in_login_items(self):
        # macOS 13+: «Об'єкти входу» вимикають агента, а launchctl print його
        # ще бачить — без цієї перевірки --check казав би ✓.
        self.install()
        r = self.install('--check', STUB_LOADED=1, STUB_DISABLED=1)
        self.assertEqual(r.returncode, 1)
        self.assertIn('вимкнено', r.stdout)

    def test_hints_restart_when_server_was_already_running(self):
        # Сервер, піднятий ДО встановлення (напр. подвійним кліком з Finder),
        # живе без вшитого PATH — сам він не перезапуститься.
        self.server_up()
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('stop.command', r.stdout)

    def test_no_restart_hint_when_server_was_down(self):
        r = self.install()
        self.assertNotIn('stop.command', r.stdout)


if __name__ == '__main__':
    unittest.main()
